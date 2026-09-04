import asyncio
import json
import uuid
from datetime import datetime, timezone
import aiomqtt as mqtt
import logging
import os
from dotenv import load_dotenv
from database import async_session
from feature.config.config import (
    TOPIC_PUB_PROVISIONING_RESPONSE,
    TOPIC_PUB_ROOM_STATE,
    TOPIC_PUB_ROOM_COMMAND,
    TOPIC_PUB_DEVICE_COMMAND,
    TOPIC_PUB_DEVICE_STATUS,
)
from feature.enum import RoomCommandType, CommandStatus, DeviceCommandEnum, DeviceStatusEnum


def _build_envelope(payload: dict) -> dict:

    return {
        "message_id": str(uuid.uuid4()),
        "source_timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


def publish_provisioning_response(
    client: mqtt.Client, device_id: str, response: dict
) -> None:
    topic = TOPIC_PUB_PROVISIONING_RESPONSE.format(mac_address=device_id)
    message = _build_envelope(response)
    asyncio.create_task(client.publish(topic, json.dumps(message)))
    logging.info("Published provisioning response to %s", topic)


def publish_room_state(
    client: mqtt.Client,
    room_id: str,
    room_mode: str,
    room_status: str,
) -> None:
    topic = TOPIC_PUB_ROOM_STATE.format(room_id=room_id)
    message = _build_envelope({
        "room_id": room_id,
        "room_mode": room_mode,
        "room_status": room_status,
    })
    asyncio.create_task(client.publish(topic, json.dumps(message)))
    logging.info("Published room state to %s: mode=%s, status=%s", topic, room_mode, room_status)


def publish_room_command(
    client: mqtt.Client,
    room_id: str,
    command_type: RoomCommandType,
    command_value: CommandStatus,
) -> None:
    topic = TOPIC_PUB_ROOM_COMMAND.format(room_id=room_id)
    message = _build_envelope({
        "room_id": room_id,
        "command_type": command_type.value,
        "command_value": command_value.value,
    })
    asyncio.create_task(client.publish(topic, json.dumps(message)))
    logging.info("Published room command to %s: %s=%s", topic, command_type.value, command_value.value)


def publish_device_command(
    client: mqtt.Client,
    mac_address: str,
    command_type: DeviceCommandEnum,
    command_value: str = "",
) -> None:
    topic = TOPIC_PUB_DEVICE_COMMAND.format(mac_address=mac_address)
    message = _build_envelope({
        "mac_address": mac_address,
        "command_type": command_type.value,
        "command_value": command_value,
    })
    asyncio.create_task(client.publish(topic, json.dumps(message)))
    logging.info("Published device command to %s: %s", topic, command_type.value)


def publish_device_status(
    client: mqtt.Client,
    device_id: str,
    mac_address: str,
    device_status: str,
    reason: str = "",
) -> None:
    topic = TOPIC_PUB_DEVICE_STATUS.format(mac_address=mac_address)
    message = _build_envelope({
        "device_id": device_id,
        "mac_address": mac_address,
        "device_status": device_status,
        "reason": reason,
    })
    asyncio.create_task(client.publish(topic, json.dumps(message)))
    logging.info("Published device status to %s: %s", topic, device_status)
