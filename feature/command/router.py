"""REST endpoints for command execution (HITL tool execution)."""
import logging
import uuid
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from feature.mqtt.mqtt_worker import create_mqtt_client
from .executor import execute_room_command, execute_device_command

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/commands", tags=["commands"])


class RoomCommandRequest(BaseModel):
    room_id: str
    command_type: str               # "door", "fan", "light", "buzzer"
    command_value: str              # "on", "off", "locked", "unlocked"
    reason: str = ""                # AI agent's reason for recommendation
    source: str = "api"             # "ai_agent", "dtwin", "admin"


class DeviceCommandRequest(BaseModel):
    device_id: str
    mac_address: str
    command_type: str               # "ota", "restart"
    command_value: str = ""
    reason: str = ""


@router.post("/room/execute", status_code=202)
async def execute_room_cmd(req: RoomCommandRequest):
    """
    Execute a room command (fan, door, light, buzzer).

    Called by Main Backend (AI agent recommendation after human confirm)
    or DTwin admin panel.

    Returns 202 Accepted with command tracking info.
    """
    try:
        async with create_mqtt_client(identifier=f"edge-cmd-{uuid.uuid4().hex[:8]}") as client:
            result = await execute_room_command(
                room_id=UUID(req.room_id),
                command_type=req.command_type,
                command_value=req.command_value,
                mqtt_client=client,
                reason=req.reason,
                source=req.source,
            )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to execute room command")
        raise HTTPException(status_code=500, detail="Command execution failed")


@router.post("/device/execute", status_code=202)
async def execute_device_cmd(req: DeviceCommandRequest):
    """Execute a device command (OTA, restart)."""
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
