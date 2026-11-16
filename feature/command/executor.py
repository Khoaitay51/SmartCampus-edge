"""Command execution pipeline — validate, persist, publish, track."""
import uuid
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, update

import aiomqtt as mqtt
from models.command import Command, CommandStatusEnum
from database import async_session
from feature.mqtt.publisher import (
    publish_room_command,
    publish_device_command,
    publish_led_strip,
    publish_room_state,
)
from feature.enum import RoomCommandType, CommandStatus, DeviceCommandEnum
from .interlock import check_expected_state, check_room_command

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
    expected_mode: str | None = None,
    expected_state_version: str | None = None,
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

    from feature.FSM.statemachine import (
        transition_to,
        get_current_state,
        get_state_snapshot,
        set_current_state,
        RoomState,
        SmokeState,
        DoorState,
        TransitionError,
        _LED_CONFIG,
    )

    command_id = uuid.uuid4()
    msg_id = str(uuid.uuid4())
    publish_actions: list[tuple] = []

    # 1. Single atomic transaction guarded by per-room PostgreSQL advisory lock
    #    to eliminate DB TOCTOU races and orphan PENDING Command records.
    async with async_session() as db:
        try:
            await db.execute(
                select(func.pg_advisory_xact_lock(func.hashtext(f"room:{room_id}")))
            )
            snapshot_state, state_version = await get_state_snapshot(room_id, RoomState, db)
            current_state = snapshot_state

            try:
                check_expected_state(
                    current_state.name, state_version, expected_mode, expected_state_version,
                    source=source,
                )
                check_room_command(current_state.name, command_type, command_value, source)
            except ValueError as barrier_err:
                logger.warning(
                    "🚨 [EDGE FSM BARRIER BLOCKED] room=%s mode=%s cmd=%s:%s source=%s reason=%s -> %s",
                    room_id, current_state.name, command_type, command_value, source, reason, barrier_err,
                )
                raise

            target_state: RoomState | None = None
            override_from_incident = False
            if command_type == "mode":
                mode_key = command_value.upper().replace("-", "_")
                try:
                    target_state = RoomState[mode_key]
                except KeyError:
                    raise ValueError(
                        f"Unknown room mode '{command_value}'. Valid modes: {[s.name.lower() for s in RoomState]}"
                    )

            db.add(Command(
                command_id=command_id,
                room_id=room_id,
                command_type=command_type,
                command_value=command_value,
                status=CommandStatusEnum.PENDING.value,
                message_id=msg_id,
                error_message=reason,
            ))

            if command_type == "door":
                door_st = DoorState.LOCKED if command_value == "locked" else DoorState.UNLOCKED
                await set_current_state(room_id, door_st, db, mqtt_client=None)

            if command_type == "mode" and target_state is not None:
                if current_state in (RoomState.EMERGENCY, RoomState.SUSPECTED):
                    override_from_incident = True
                    await set_current_state(room_id, target_state, db, mqtt_client=None)
                    await set_current_state(room_id, SmokeState.NORMAL, db, mqtt_client=None)
                    door_st = DoorState.LOCKED if target_state == RoomState.EXAM else DoorState.UNLOCKED
                    await set_current_state(room_id, door_st, db, mqtt_client=None)
                else:
                    try:
                        await transition_to(room_id, target_state, db, mqtt_client=None)
                    except TransitionError as fsm_err:
                        logger.warning("🚨 [FSM TRANSITION BLOCKED] Room %s: %s", room_id, fsm_err)
                        raise ValueError(f"FSM Barrier Violation: {str(fsm_err)}")

            await db.commit()
        except Exception:
            await db.rollback()
            raise

    # 2. Publish MQTT strictly AFTER DB commit so rolled-back/rejected commands emit zero frames.
    if mqtt_client:
        if command_type == "mode" and target_state is not None:
            await publish_room_state(mqtt_client, str(room_id), target_state.name, "online")
            led_color, led_effect = _LED_CONFIG.get(target_state, ("#000000", "static"))
            await publish_led_strip(mqtt_client, str(room_id), led_color, led_effect)
            if override_from_incident:
                await publish_room_command(
                    mqtt_client, str(room_id), RoomCommandType.BUZZER, CommandStatus.OFF,
                )
            elif target_state == RoomState.EMERGENCY:
                await publish_room_command(
                    mqtt_client, str(room_id), RoomCommandType.DOOR, CommandStatus.UNLOCKED,
                )
                await publish_room_command(
                    mqtt_client, str(room_id), RoomCommandType.BUZZER, CommandStatus.ON,
                )
            elif target_state == RoomState.EXAM:
                await publish_room_command(
                    mqtt_client, str(room_id), RoomCommandType.DOOR, CommandStatus.LOCKED,
                )

        try:
            cmd_type_enum = RoomCommandType(command_type)
            cmd_val_enum = CommandStatus(command_value)
            await publish_room_command(
                mqtt_client, str(room_id), cmd_type_enum, cmd_val_enum,
                command_id=str(command_id), message_id=msg_id,
            )
        except (ValueError, KeyError):
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
