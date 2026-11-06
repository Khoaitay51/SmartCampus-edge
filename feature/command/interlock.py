"""Edge FSM Interlock — rào chắn bất biến tại Edge Gateway (pure, không phụ thuộc DB/MQTT).

Nguyên tắc: "LLM đề xuất, FSM tất định quyết định". Mọi lệnh phát sinh từ AI
(source ``ai_agent`` hoặc ``admin_hitl``) — kể cả khi đã được người duyệt — vẫn phải
qua các kiểm tra dưới đây trước khi xuống MQTT:

1. Ma trận quyền theo chế độ phòng (``AI_COMMAND_PERMISSIONS``) — đồng bộ với
   ``MODE_PERMISSIONS`` ở AI Backend nhưng được *thực thi cứng* tại Edge.
2. Bất biến vật lý áp dụng cho MỌI nguồn (không mở cửa khi EXAM/LOCK, không khóa
   cửa thoát hiểm khi EMERGENCY).
3. Kiểm tra "state-substitution" vật lý (TOCTOU): lệnh được duyệt khi phòng ở trạng
   thái X chỉ được chạy nếu phòng vẫn đang ở đúng trạng thái X (cùng ``state_version``).
"""
from __future__ import annotations

import os

_FALSY_FLAGS: frozenset[str] = frozenset({"0", "false", "no", "off"})


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in _FALSY_FLAGS


def is_edge_fsm_enabled() -> bool:
    """Kiểm tra cờ SAFETY_FSM_ENABLED (mặc định True). Khi False: mọi tool chạy global."""
    return _env_flag("SAFETY_FSM_ENABLED", True)


def is_toctou_binding_enabled() -> bool:
    """Kiểm tra cờ SAFETY_TOCTOU_BINDING_ENABLED (mặc định True). Khi False: bỏ qua check_expected_state."""
    return _env_flag("SAFETY_TOCTOU_BINDING_ENABLED", True)


AI_SOURCES: frozenset[str] = frozenset({"ai_agent", "admin_hitl"})

# command_type được phép cho lệnh do AI khởi phát, theo chế độ phòng.
# Ánh xạ tool -> command_type: set_fan->fan, set_door->door, set_mode->mode,
# set_led->light, trigger_buzzer->buzzer (send_alert không có command vật lý trừ
# mức critical, được dịch thành buzzer và do đó cũng phải qua ma trận này).
AI_COMMAND_PERMISSIONS: dict[str, frozenset[str]] = {
    "SAVING": frozenset({"fan", "door", "mode", "light"}),
    "SELF_STUDY": frozenset({"fan", "door", "mode", "light"}),
    "LECTURE": frozenset({"fan", "door", "mode", "light"}),
    "EXAM": frozenset({"fan", "mode", "light"}),
    "LOCK": frozenset({"buzzer", "mode"}),
    "SUSPECTED": frozenset({"fan", "light", "buzzer", "mode"}),
    "EMERGENCY": frozenset({"fan", "door", "mode", "buzzer", "light"}),
}


class InterlockViolation(ValueError):
    """Lệnh bị chặn bởi rào chắn bất biến của FSM (HTTP 403)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class StaleApprovalError(ValueError):
    """Trạng thái vật lý đã đổi giữa lúc duyệt và lúc thực thi (HTTP 409)."""

    def __init__(self, message: str, *, expected: str | None, actual: str | None):
        super().__init__(message)
        self.expected = expected
        self.actual = actual


def check_room_command(
    current_mode: str,
    command_type: str,
    command_value: str,
    source: str,
) -> None:
    """Raise :class:`InterlockViolation` nếu lệnh vi phạm bất biến tại ``current_mode``."""
    mode = (current_mode or "").upper().strip()
    ctype = (command_type or "").lower().strip()
    cvalue = (command_value or "").lower().strip()
    src = (source or "").lower().strip()

    # Bất biến A (mọi nguồn): không mở cửa khi đang THI hoặc KHÓA.
    if mode in ("EXAM", "LOCK") and ctype == "door" and cvalue == "unlocked":
        raise InterlockViolation(
            "INV_A_NO_UNLOCK",
            f"FSM Safety Invariant Violated: Cannot unlock door while room is in {mode} mode.",
        )

    # Bất biến B (mọi nguồn): không khóa cửa thoát hiểm khi KHẨN CẤP.
    if mode == "EMERGENCY" and ctype == "door" and cvalue == "locked":
        raise InterlockViolation(
            "INV_B_NO_LOCK_EXIT",
            "FSM Safety Invariant Violated: Cannot lock exit door during EMERGENCY state.",
        )

    if src not in AI_SOURCES:
        return

    # Ma trận quyền theo mode — chỉ cho nguồn AI. Mode lạ => fail-closed (không quyền gì).
    allowed = AI_COMMAND_PERMISSIONS.get(mode, frozenset())
    if ctype not in allowed:
        raise InterlockViolation(
            "MODE_PERMISSION_DENIED",
            f"FSM Interlock: '{ctype}' command is not permitted for AI-originated source "
            f"'{src}' while room is in {mode or 'UNKNOWN'} mode.",
        )

    # Autopilot (ai_agent) không bao giờ được đổi chế độ FSM; chỉ người duyệt (admin_hitl).
    if ctype == "mode" and src == "ai_agent":
        raise InterlockViolation(
            "AUTOPILOT_NO_MODE_CHANGE",
            "FSM Interlock: autonomous agent may not change room mode; human approval required.",
        )


def check_expected_state(
    current_mode: str,
    current_version: str | None,
    expected_mode: str | None,
    expected_version: str | None,
) -> None:
    """Từ chối nếu phòng không còn ở đúng trạng thái mà người duyệt đã thấy.

    Chỉ kiểm tra những trường mà caller cung cấp. ``expected_version`` được so sánh
    chính xác để bắt cả trường hợp đổi mode rồi quay lại cùng giá trị (A→B→A).
    Nếu ``SAFETY_TOCTOU_BINDING_ENABLED=false`` -> bỏ qua kiểm tra độ tươi trạng thái.
    """
    if not is_toctou_binding_enabled():
        return
    if expected_mode:
        if (current_mode or "").upper().strip() != expected_mode.upper().strip():
            raise StaleApprovalError(
                f"Approval is stale: room mode changed from {expected_mode.upper()} "
                f"to {(current_mode or 'UNKNOWN').upper()} after approval was requested.",
                expected=expected_mode.upper(),
                actual=(current_mode or "").upper(),
            )
    if expected_version:
        if current_version != expected_version:
            raise StaleApprovalError(
                "Approval is stale: room state changed after approval was requested "
                f"(version {expected_version} -> {current_version}).",
                expected=expected_version,
                actual=current_version,
            )
