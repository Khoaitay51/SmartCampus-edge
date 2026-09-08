import json
import uuid
from datetime import datetime, timezone
import aiomqtt as mqtt
import logging

from feature.config.config import (
    TOPIC_PUB_PROVISIONING_RESPONSE,
    TOPIC_PUB_ROOM_STATE,
    TOPIC_PUB_ROOM_COMMAND,
    TOPIC_PUB_DEVICE_COMMAND,
    TOPIC_PUB_DEVICE_STATUS,
    TOPIC_PUB_ROOM_DISCREPANCY,
)
from feature.enum import RoomCommandType, CommandStatus, DeviceCommandEnum, DeviceStatusEnum

logger = logging.getLogger(__name__)


def _build_envelope(payload: dict) -> dict:
    return {
        "message_id": str(uuid.uuid4()),
        "source_timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


def _get_enum_value(val: object) -> str:
    if hasattr(val, "value"):
        return str(val.value)
    return str(val).lower()


async def publish_provisioning_response(
    client: mqtt.Client | None, device_id: str, response: dict
) -> None:
    if client is None:
        logger.warning("publish_provisioning_response called with mqtt_client=None")
        return
    topic = TOPIC_PUB_PROVISIONING_RESPONSE.format(mac_address=device_id)
    message = _build_envelope(response)
    await client.publish(topic, json.dumps(message), retain=True)
    logger.info("Published provisioning response to %s", topic)


async def publish_room_state(
    client: mqtt.Client | None,
    room_id: str,
    room_mode: str,
    room_status: str,
) -> None:
    if client is None:
        logger.warning("publish_room_state called with mqtt_client=None")
        return
    topic = TOPIC_PUB_ROOM_STATE.format(room_id=room_id)
    message = _build_envelope({
        "room_id": room_id,
        "room_mode": room_mode.lower() if isinstance(room_mode, str) else _get_enum_value(room_mode),
        "room_status": room_status.lower() if isinstance(room_status, str) else _get_enum_value(room_status),
    })
    await client.publish(topic, json.dumps(message), retain=True)
    logger.info("Published room state to %s: mode=%s, status=%s", topic, room_mode, room_status)


async def publish_room_command(
    client: mqtt.Client | None,
    room_id: str,
    command_type: RoomCommandType | str,
    command_value: CommandStatus | str,
) -> None:
    if client is None:
        logger.warning("publish_room_command called with mqtt_client=None")
        return
    type_str = _get_enum_value(command_type)
    val_str = _get_enum_value(command_value)
    topic = TOPIC_PUB_ROOM_COMMAND.format(room_id=room_id)
    message = _build_envelope({
        "room_id": room_id,
        "command_type": type_str,
        "command_value": val_str,
    })
    await client.publish(topic, json.dumps(message))
    logger.info("Published room command to %s: %s=%s", topic, type_str, val_str)


async def publish_device_command(
    client: mqtt.Client | None,
    mac_address: str,
    command_type: DeviceCommandEnum | str,
    command_value: str = "",
) -> None:
    if client is None:
        logger.warning("publish_device_command called with mqtt_client=None")
        return
    type_str = _get_enum_value(command_type)
    topic = TOPIC_PUB_DEVICE_COMMAND.format(mac_address=mac_address)
    message = _build_envelope({
        "mac_address": mac_address,
        "command_type": type_str,
        "command_value": command_value,
    })
    await client.publish(topic, json.dumps(message))
    logger.info("Published device command to %s: %s", topic, type_str)


async def publish_device_status(
    client: mqtt.Client | None,
    device_id: str,
    mac_address: str,
    device_status: DeviceStatusEnum | str,
    reason: str = "",
) -> None:
    if client is None:
        logger.warning("publish_device_status called with mqtt_client=None")
        return
    status_str = _get_enum_value(device_status)
    topic = TOPIC_PUB_DEVICE_STATUS.format(mac_address=mac_address)
    message = _build_envelope({
        "device_id": device_id,
        "mac_address": mac_address,
        "device_status": status_str,
        "reason": reason,
    })
    await client.publish(topic, json.dumps(message), retain=True)
    logger.info("Published device status to %s: %s", topic, status_str)


async def publish_room_discrepancy(
    client: mqtt.Client | None,
    room_id: str,
    session_id: str | None,
    occupancy_count: int,
    attendance_count: int,
    discrepancy: int,
) -> None:
    if client is None:
        logger.warning("publish_room_discrepancy called with mqtt_client=None")
        return
    topic = TOPIC_PUB_ROOM_DISCREPANCY.format(room_id=room_id)
    status = "MATCH" if discrepancy == 0 else ("EXTRA_PEOPLE" if discrepancy > 0 else "MISSING_PEOPLE")
    message = _build_envelope({
        "room_id": str(room_id),
        "session_id": str(session_id) if session_id else None,
        "occupancy_count": occupancy_count,
        "attendance_count": attendance_count,
        "discrepancy": discrepancy,
        "status": status,
    })
    await client.publish(topic, json.dumps(message))
    logger.info("Published room discrepancy to %s: occ=%d, att=%d, diff=%d (%s)", topic, occupancy_count, attendance_count, discrepancy, status)
