import asyncio
import json
import aiomqtt as mqtt
import logging
import os

from dotenv import load_dotenv
from sqlalchemy import insert, select
from database import async_session
import models
from models.__enum import IRSignalType

from feature.config.config import (
    TOPIC_PROVISIONING_REQUEST,
    TOPIC_DEVICE_HEARTBEAT,
    TOPIC_ENV_TELEMETRY,
    TOPIC_OCCUPANCY_TELEMETRY,
    TOPIC_ROOM_RFID_EVENT,
    TOPIC_COMMAND_ACK,
    TOPIC_SCENARIO,
    TOPIC_SUBSCRIBE_ALL,
    MQTT_KEEPALIVE,
)

load_dotenv()
logger = logging.getLogger(__name__)

RECONNECT_INTERVAL = 5  


def get_mqtt_config():
    """Read the MQTT connection settings used by the worker."""
    username = os.getenv("MQTT_USERNAME")
    password = os.getenv("MQTT_PASSWORD")

    if not username or not password:
        raise RuntimeError("MQTT_USERNAME and MQTT_PASSWORD must be set.")

    return {
        "hostname": os.getenv("MQTT_HOST", os.getenv("MQTT_BROKER", "localhost")),
        "port": int(os.getenv("MQTT_PORT", "1883")),
        "username": username,
        "password": password,
    }


def create_mqtt_client() -> mqtt.Client:
    """Create an authenticated MQTT client for use with ``async with``."""
    return mqtt.Client(**get_mqtt_config(), keepalive=MQTT_KEEPALIVE, client_id="smartcampus-edge-worker")



async def _dispatch_message(message: mqtt.Message) -> None:
    """Dispatch incoming MQTT messages to the appropriate handler."""
    topic = message.topic

    try:
        payload = json.loads(message.payload.decode(errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("Invalid JSON on %s: %s", topic, message.payload[:200])
        return

    # --- Device provisioning ---
    if topic.matches(TOPIC_PROVISIONING_REQUEST):
        await _handle_provisioning_request(payload)

    # --- Device heartbeat ---
    elif topic.matches(TOPIC_DEVICE_HEARTBEAT):
        await _handle_heartbeat(payload)

    # --- Environment telemetry (temperature, humidity, smoke, CO2) ---
    elif topic.matches(TOPIC_ENV_TELEMETRY):
        await _handle_environment_telemetry(payload)

    # --- Occupancy telemetry (IR motion sensors) ---
    elif topic.matches(TOPIC_OCCUPANCY_TELEMETRY):
        await _handle_occupancy_telemetry(payload)

    # --- RFID card tap event ---
    elif topic.matches(TOPIC_ROOM_RFID_EVENT):
        await _handle_rfid_event(payload)

    # --- Command acknowledgement from device ---
    elif topic.matches(TOPIC_COMMAND_ACK):
        await _handle_command_ack(payload)

    # --- Automation scenario ---
    elif topic.matches(TOPIC_SCENARIO):
        await _handle_scenario(payload)

    else:
        logger.debug("Unhandled topic: %s", topic)


async def _handle_provisioning_request(payload: dict) -> None:
    """Register a newly booted ESP32 device."""
    inner = payload.get("payload", {})
    logger.info("Provisioning request: mac=%s", inner.get("mac_address"))
    # TODO: look up / create device in DB, publish provisioning_response


async def _handle_heartbeat(payload: dict) -> None:
    """Update device last-seen timestamp."""
    inner = payload.get("payload", {})
    device_id = inner.get("device_id")
    alive = inner.get("alive")
    firmware_version = inner.get("firmware_version")
    uptime = inner.get("uptime")
    
    logger.info("Heartbeat: device=%s, uptime=%s", inner.get("device_id"), inner.get("uptime"))
    # TODO: update device.last_seen in DB
    async with async_session() as db:
        try:
            await db.execute(
                insert(models.DeviceHeartbeat).values(
                    device_id=device_id,
                    alive=alive,
                    firmware_version=firmware_version,
                    uptime=uptime,
                    message_id=payload.get("message_id"),
                    source_timestamp=payload.get("source_timestamp")

                )
            )
            await db.commit()

        except Exception as e:
            await db.rollback()
            logger.error("Failed to insert heartbeat telemetry: %s", e)


async def _handle_environment_telemetry(payload: dict) -> None:
    """Store environment sensor readings (temp, humidity, smoke, CO2)."""
    inner = payload.get("payload", {})
    logger.info(
        "Environment: room=%s, temp=%s, humidity=%s, smoke=%s",
        inner.get("room_id"),
        inner.get("temperature"),
        inner.get("humidity"),
        inner.get("smoke_state", "unknown"),
    )
    # TODO: insert into telemetry hypertable
    # TODO: if smoke_state == "emergency" -> trigger FSM state change


async def _handle_occupancy_telemetry(payload: dict) -> None:
    """Store occupancy count changes from IR sensors."""
    inner = payload.get("payload", {})
    room_id = inner.get("room_id")
    occupancy_type = inner.get("occupancy_type")
    logger.info(
        "Occupancy: room=%s, type=%s",
        room_id,
        occupancy_type,
    )
    # Bug-3 fix: compare occupancy_type (not occupancy_count) with IRSignalType
    if occupancy_type == IRSignalType.IN.name:
        delta = 1
    elif occupancy_type == IRSignalType.OUT.name:
        delta = -1
    else:
        logger.warning("Invalid occupancy_type: %s", occupancy_type)
        return
    # Bug-4 fix: use begin() for explicit transaction + with_for_update()
    # to prevent race conditions on concurrent messages for the same room
    async with async_session() as db:
        try:
            async with db.begin():
                result = await db.execute(
                    select(models.Occupancy.occupancy_count)
                    .where(models.Occupancy.room_id == room_id)
                    .order_by(models.Occupancy.occupancy_timestamp.desc())
                    .limit(1)
                    .with_for_update()
                )
                last_count = result.scalar()
                new_count = (last_count + delta) if last_count is not None else max(delta, 0)
                await db.execute(
                    insert(models.Occupancy).values(
                        room_id=room_id,
                        occupancy_type=occupancy_type,
                        occupancy_count=new_count,
                        message_id=payload.get("message_id"),
                        source_timestamp=payload.get("source_timestamp"),
                    )
                )
        except Exception as e:
            logger.error("Failed to insert occupancy telemetry: %s", e)


async def _handle_rfid_event(payload: dict) -> None:
    """Process RFID card tap for attendance tracking."""
    inner = payload.get("payload", {})
    logger.info(
        "RFID event: room=%s, card=%s, event=%s",
        inner.get("room_id"),
        inner.get("card_uid"),
        inner.get("event_type"),
    )
    # TODO: validate card, record attendance


async def _handle_command_ack(payload: dict) -> None:
    """Handle device acknowledgement of a command."""
    inner = payload.get("payload", {})
    logger.info(
        "Command ACK: device=%s, cmd=%s, success=%s",
        inner.get("mac_address"),
        inner.get("command_id"),
        inner.get("success"),
    )
    # TODO: update command status in DB


async def _handle_scenario(payload: dict) -> None:
    """Handle automation scenario triggers."""
    inner = payload.get("payload", {})
    logger.info(
        "Scenario: id=%s, action=%s, triggered_by=%s",
        inner.get("scenario_id"),
        inner.get("action"),
        inner.get("triggered_by"),
    )
    # TODO: execute or cancel scenario


async def mqtt_listener() -> None:
    """Listen for incoming MQTT messages and dispatch them to handlers."""
    while True:
        try:
            async with create_mqtt_client() as client:
                await client.subscribe(TOPIC_SUBSCRIBE_ALL, qos=1)
                logger.info("MQTT listener subscribed to %s", TOPIC_SUBSCRIBE_ALL)

                async for message in client.messages:
                    try:
                        await _dispatch_message(message)
                    except Exception:
                        logger.exception(
                            "Error handling message on %s", message.topic,
                        )

        except mqtt.MqttError as err:
            logger.warning(
                "MQTT connection lost: %s. Reconnecting in %ds...",
                err,
                RECONNECT_INTERVAL,
            )
            await asyncio.sleep(RECONNECT_INTERVAL)
