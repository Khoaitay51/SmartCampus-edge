"""Command execution pipeline — validate, persist, publish, track."""
import uuid
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import update

import aiomqtt as mqtt
from models.command import Command, CommandStatusEnum
from database import async_session
from feature.mqtt.publisher import publish_room_command, publish_device_command
from feature.enum import RoomCommandType, CommandStatus, DeviceCommandEnum

logger = logging.getLogger(__name__)

# Valid room command types and their allowed values
_VALID_ROOM_COMMANDS: dict[str, list[str]] = {
    "mode": ["saving", "self_study", "lecture", "exam", "lock", "suspected", "emergency"],
    "door": ["locked", "unlocked"],
    "fan": ["on", "off"],
    "light": ["on", "off"],
    "buzzer": ["on", "off"],
}

_VALID_DEVICE_COMMANDS = {"ota", "restart"}


async def execute_room_command(
    room_id: UUID,
    command_type: str,
    command_value: str,
    mqtt_client: mqtt.Client | None = None,
    reason: str = "",
    source: str = "api",
) -> dict:
    """
    Execute a room command: validate -> persist to DB -> publish MQTT.

    Returns dict with command_id and status for the caller.
    """
    command_type = command_type.lower().strip()
    command_value = command_value.lower().strip()

    # Validate command type
    if command_type not in _VALID_ROOM_COMMANDS:
        raise ValueError(
            f"Invalid command_type '{command_type}'. "
            f"Valid: {list(_VALID_ROOM_COMMANDS.keys())}"
        )

    # Validate command value
    valid_values = _VALID_ROOM_COMMANDS[command_type]
    if valid_values is not None and len(valid_values) > 0 and command_value not in valid_values:
        raise ValueError(
            f"Invalid command_value '{command_value}' for '{command_type}'. "
            f"Valid: {valid_values}"
        )

    command_id = uuid.uuid4()
    msg_id = str(uuid.uuid4())

    async with async_session() as db:
        try:
            db.add(Command(
                command_id=command_id,
                room_id=room_id,
                command_type=command_type,
                command_value=command_value,
                status=CommandStatusEnum.PENDING.value,
                message_id=msg_id,
                error_message=reason,
            ))
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("Failed to persist command: %s", e)
            raise

    # Publish to MQTT
    if mqtt_client:
        try:
            cmd_type_enum = RoomCommandType(command_type)
            cmd_val_enum = CommandStatus(command_value)
            await publish_room_command(
                mqtt_client, str(room_id), cmd_type_enum, cmd_val_enum,
                command_id=str(command_id), message_id=msg_id,
            )
        except (ValueError, KeyError):
            # Not a standard enum value — publish raw
            await publish_room_command(
                mqtt_client, str(room_id), command_type, command_value,
                command_id=str(command_id), message_id=msg_id,
            )

    logger.info(
        "Executed room command: id=%s, room=%s, type=%s, value=%s, source=%s",
        command_id, room_id, command_type, command_value, source,
    )

    return {
        "command_id": str(command_id),
        "room_id": str(room_id),
        "command_type": command_type,
        "command_value": command_value,
        "status": CommandStatusEnum.PENDING.value,
        "message_id": msg_id,
    }


async def execute_device_command(
    device_id: UUID,
    mac_address: str,
    command_type: str,
    command_value: str = "",
    mqtt_client: mqtt.Client | None = None,
    reason: str = "",
) -> dict:
    """Execute a device-level command (OTA, restart)."""
    command_type = command_type.lower().strip()

    if command_type not in _VALID_DEVICE_COMMANDS:
        raise ValueError(
            f"Invalid device command_type '{command_type}'. "
            f"Valid: {list(_VALID_DEVICE_COMMANDS)}"
        )

    command_id = uuid.uuid4()
    msg_id = str(uuid.uuid4())

    async with async_session() as db:
        try:
            db.add(Command(
                command_id=command_id,
                device_id=device_id,
                command_type=command_type,
                command_value=command_value,
                status=CommandStatusEnum.PENDING.value,
                message_id=msg_id,
                error_message=reason,
            ))
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("Failed to persist device command: %s", e)
            raise

    if mqtt_client:
        await publish_device_command(mqtt_client, mac_address, command_type, command_value)

    logger.info(
        "Executed device command: id=%s, device=%s, type=%s",
        command_id, device_id, command_type,
    )

    return {
        "command_id": str(command_id),
        "device_id": str(device_id),
        "command_type": command_type,
        "command_value": command_value,
        "status": CommandStatusEnum.PENDING.value,
        "message_id": msg_id,
    }


async def update_command_status(
    command_id: UUID | None = None,
    message_id: str | None = None,
    new_status: str = CommandStatusEnum.ACKED.value,
) -> bool:
    """Update command status when ACK received. Lookup by command_id or message_id."""
    async with async_session() as db:
        try:
            if command_id:
                stmt = (
                    update(Command)
                    .where(Command.command_id == command_id)
                    .values(
                        status=new_status,
                        acked_at=datetime.now(timezone.utc),
                    )
                )
            elif message_id:
                stmt = (
                    update(Command)
                    .where(Command.message_id == message_id)
                    .values(
                        status=new_status,
                        acked_at=datetime.now(timezone.utc),
                    )
                )
            else:
                return False

            result = await db.execute(stmt)
            await db.commit()
            return result.rowcount > 0
        except Exception as e:
            await db.rollback()
            logger.error("Failed to update command status: %s", e)
            return False
