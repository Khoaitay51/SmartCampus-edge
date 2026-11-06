"""TOCTOU / Verdict-Staleness tests cho Edge interlock + cờ SAFETY_TOCTOU_BINDING_ENABLED.

Bám kịch bản T8 (Benign Self-Recovery Staleness) trong LITERATURE_REVIEW_AGENTIC_IOT_SAFETY.md:
đề xuất được tạo khi phòng ở trạng thái X (version v1), môi trường tự hồi phục sang Y (v2)
trước khi người duyệt bấm Approve. Lớp M3 (FSM tĩnh) KHÔNG bắt được vì lệnh vẫn hợp lệ ở Y;
chỉ lớp M4 (state-version binding) mới chặn được.

Chạy:  cd edge && python -m unittest tests.test_toctou -v
"""
import os
import unittest
from unittest import mock

from feature.command.interlock import (
    InterlockViolation,
    StaleApprovalError,
    check_expected_state,
    check_room_command,
    compute_composite_state_version,
    is_toctou_binding_enabled,
)

ENV = "SAFETY_TOCTOU_BINDING_ENABLED"


def _env(value):
    """Patch biến môi trường; value=None nghĩa là xóa biến (dùng mặc định)."""
    if value is None:
        env = {k: v for k, v in os.environ.items() if k != ENV}
        return mock.patch.dict(os.environ, env, clear=True)
    return mock.patch.dict(os.environ, {ENV: value})


class ToctouFlagParsingTests(unittest.TestCase):
    def test_default_is_enabled_when_unset(self):
        with _env(None):
            self.assertTrue(is_toctou_binding_enabled())

    def test_truthy_values_enable(self):
        for raw in ("true", "TRUE", "1", "yes", "on", " True "):
            with self.subTest(raw=raw), _env(raw):
                self.assertTrue(is_toctou_binding_enabled())

    def test_falsy_values_disable(self):
        for raw in ("false", "False", "0", "no", "off", " OFF "):
            with self.subTest(raw=raw), _env(raw):
                self.assertFalse(is_toctou_binding_enabled())

    def test_flag_is_read_at_call_time_not_import_time(self):
        with _env("true"):
            self.assertTrue(is_toctou_binding_enabled())
        with _env("false"):
            self.assertFalse(is_toctou_binding_enabled())


class BenignSelfRecoveryT8Tests(unittest.TestCase):
    """SUSPECTED(v1) --khói tự tan--> SAVING(v2) --Admin approve trễ--> lệnh cũ."""

    PROPOSED_MODE, PROPOSED_VER = "SUSPECTED", "2026-11-06T07:00:00+00:00"
    CURRENT_MODE, CURRENT_VER = "SAVING", "2026-11-06T07:00:30+00:00"

    def test_m3_static_fsm_alone_does_not_catch_t8(self):
        # Ở SAVING, các lệnh này đều hợp lệ theo ma trận quyền tĩnh => M3 cho qua.
        for ctype, val in (("fan", "on"), ("mode", "emergency"), ("light", "on")):
            with self.subTest(cmd=f"{ctype}:{val}"):
                check_room_command(self.CURRENT_MODE, ctype, val, "admin_hitl")

    def test_m4_blocks_t8_when_toctou_enabled(self):
        with _env("true"):
            with self.assertRaises(StaleApprovalError) as ctx:
                check_expected_state(
                    self.CURRENT_MODE, self.CURRENT_VER, self.PROPOSED_MODE, self.PROPOSED_VER,
                )
        self.assertEqual(ctx.exception.expected, "SUSPECTED")
        self.assertEqual(ctx.exception.actual, "SAVING")

    def test_t8_slips_through_when_toctou_disabled(self):
        # Cấu hình M4(No-TOCTOU): tái hiện lỗ hổng — duyệt trễ vẫn được thực thi.
        with _env("false"):
            check_expected_state(
                self.CURRENT_MODE, self.CURRENT_VER, self.PROPOSED_MODE, self.PROPOSED_VER,
            )


class VersionBindingTests(unittest.TestCase):
    def test_a_b_a_cycle_blocked_when_enabled(self):
        with _env("true"), self.assertRaises(StaleApprovalError):
            check_expected_state("LECTURE", "v3", "LECTURE", "v1")

    def test_a_b_a_cycle_allowed_when_disabled(self):
        with _env("false"):
            check_expected_state("LECTURE", "v3", "LECTURE", "v1")

    def test_version_only_binding_when_enabled(self):
        with _env("true"), self.assertRaises(StaleApprovalError):
            check_expected_state("LECTURE", "v2", None, "v1")

    def test_fresh_state_passes_in_both_configs(self):
        for raw in ("true", "false"):
            with self.subTest(flag=raw), _env(raw):
                check_expected_state("EXAM", "v7", "exam", "v7")

    def test_default_unset_behaves_as_enabled(self):
        with _env(None), self.assertRaises(StaleApprovalError):
            check_expected_state("SAVING", "v2", "SUSPECTED", "v1")


class LayerIndependenceTests(unittest.TestCase):
    """Tắt TOCTOU KHÔNG được làm yếu FSM interlock (M3) — hai lớp độc lập."""

    def test_disabling_toctou_keeps_fsm_invariants(self):
        with _env("false"):
            with self.assertRaises(InterlockViolation) as ctx:
                check_room_command("EXAM", "door", "unlocked", "admin_hitl")
            self.assertEqual(ctx.exception.code, "INV_A_NO_UNLOCK")
            with self.assertRaises(InterlockViolation) as ctx:
                check_room_command("EMERGENCY", "door", "locked", "ai_agent")
            self.assertEqual(ctx.exception.code, "INV_B_NO_LOCK_EXIT")


class CompositeStateVersionTests(unittest.TestCase):
    """Kiểm tra composite hash sửa điểm yếu W1 (smoke/door đổi nhưng room_mode giữ nguyên)."""

    def test_returns_none_when_all_timestamps_empty(self):
        self.assertIsNone(compute_composite_state_version("SAVING", None, "LOCKED", None, "NORMAL", None))

    def test_smoke_self_recovery_in_locked_room_changes_version(self):
        # Phòng đang LOCK (transition bị chặn), khói từ SUSPECTED tự tan về NORMAL:
        v_suspected = compute_composite_state_version(
            "LOCK", "t1", "LOCKED", "t1", "SUSPECTED", "t2"
        )
        v_recovered = compute_composite_state_version(
            "LOCK", "t1", "LOCKED", "t1", "NORMAL", "t3"
        )
        self.assertNotEqual(v_suspected, v_recovered)
        with _env("true"), self.assertRaises(StaleApprovalError):
            check_expected_state("LOCK", v_recovered, "LOCK", v_suspected)

    def test_manual_door_change_changes_version(self):
        v1 = compute_composite_state_version("LECTURE", "t1", "UNLOCKED", "t1", "NORMAL", "t1")
        v2 = compute_composite_state_version("LECTURE", "t1", "LOCKED", "t2", "NORMAL", "t1")
        self.assertNotEqual(v1, v2)


if __name__ == "__main__":
    unittest.main()

