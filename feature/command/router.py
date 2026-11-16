"""REST endpoints for command execution (HITL tool execution)."""
import hmac
import logging
import os
import uuid
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from feature.mqtt.mqtt_worker import create_mqtt_client
from .executor import execute_room_command, execute_device_command
from .interlock import InterlockViolation, StaleApprovalError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/commands", tags=["commands"])

VALID_COMMAND_SOURCES: frozenset[str] = frozenset(
    {"api", "ai_agent", "admin_hitl", "dtwin", "dtwin_admin", "admin"}
)


def _authorize_internal_command(x_edge_internal_token: str | None) -> None:
    """Enforce internal token on command execution endpoints when EDGE_INTERNAL_TOKEN is configured."""
    expected = os.getenv("EDGE_INTERNAL_TOKEN", "").strip()
    if not expected:
        return
    if not x_edge_internal_token or not hmac.compare_digest(x_edge_internal_token, expected):
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED_EDGE_CALLER", "message": "Missing or invalid Edge internal token."},
        )


class RoomCommandRequest(BaseModel):
    room_id: str
    command_type: str               # "door", "fan", "light", "buzzer"
    command_value: str              # "on", "off", "locked", "unlocked"
    reason: str = ""                # AI agent's reason for recommendation
    source: str = "api"             # "ai_agent", "admin_hitl", "dtwin", "admin"
    # Physical-TOCTOU binding: trạng thái phòng mà người duyệt đã nhìn thấy khi bấm Approve.
    expected_mode: str | None = None
    expected_state_version: str | None = None


class DeviceCommandRequest(BaseModel):
    device_id: str
    mac_address: str
    command_type: str               # "ota", "restart"
    command_value: str = ""
    reason: str = ""


def _to_room_uuid(room_id: str) -> UUID:
    try:
        return UUID(room_id)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_DNS, room_id)


@router.get("/room/{room_id}/state-snapshot")
async def room_state_snapshot(room_id: str):
    """Snapshot trạng thái FSM hiện tại (mode + state_version) để bind vào HITL approval."""
    from database import async_session
    from feature.FSM.statemachine import RoomState, get_state_snapshot

    target_uuid = _to_room_uuid(room_id)
    async with async_session() as db:
        state, version = await get_state_snapshot(target_uuid, RoomState, db)
    return {"room_id": str(target_uuid), "mode": state.name, "state_version": version}


@router.post("/room/execute", status_code=202)
async def execute_room_cmd(
    req: RoomCommandRequest,
    x_edge_internal_token: str | None = Header(default=None, alias="X-Edge-Internal-Token"),
):
    """
    Execute a room command (fan, door, light, buzzer).

    Called by Main Backend (AI agent recommendation after human confirm)
    or DTwin admin panel.

    Returns 202 Accepted with command tracking info.
    """
    _authorize_internal_command(x_edge_internal_token)
    normalized_source = (req.source or "").lower().strip()
    if normalized_source not in VALID_COMMAND_SOURCES:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_COMMAND_SOURCE", "message": f"Unsupported command source '{req.source}'."},
        )
    try:
        target_uuid = _to_room_uuid(req.room_id)

        async with create_mqtt_client(identifier=f"edge-cmd-{uuid.uuid4().hex[:8]}") as client:
            result = await execute_room_command(
                room_id=target_uuid,
                command_type=req.command_type,
                command_value=req.command_value,
                mqtt_client=client,
                reason=req.reason,
                source=normalized_source,
                expected_mode=req.expected_mode,
                expected_state_version=req.expected_state_version,
            )
        return result
    except StaleApprovalError as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "STALE_APPROVAL", "message": str(e), "expected": e.expected, "actual": e.actual},
        )
    except InterlockViolation as e:
        raise HTTPException(status_code=403, detail={"code": e.code, "message": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to execute room command")
        raise HTTPException(status_code=500, detail="Command execution failed")


@router.post("/device/execute", status_code=202)
async def execute_device_cmd(
    req: DeviceCommandRequest,
    x_edge_internal_token: str | None = Header(default=None, alias="X-Edge-Internal-Token"),
):
    """Execute a device command (OTA, restart)."""
    _authorize_internal_command(x_edge_internal_token)
    try:
        async with create_mqtt_client(identifier=f"edge-cmd-{uuid.uuid4().hex[:8]}") as client:
            result = await execute_device_command(
                device_id=UUID(req.device_id),
                mac_address=req.mac_address,
                command_type=req.command_type,
                command_value=req.command_value,
                mqtt_client=client,
                reason=req.reason,
            )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to execute device command")
        raise HTTPException(status_code=500, detail="Command execution failed")
