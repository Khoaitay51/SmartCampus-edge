import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import aiomqtt as mqtt
from sqlalchemy import func, insert, select

import models
from models import IRSignalType
from database import async_session
from feature.config.config import (
    BROKER_HOST,
    BROKER_PASSWORD,
    BROKER_PORT,
    BROKER_USERNAME,
    RECONNECT_INTERVAL,
    TOPIC_SUB_HEARTBEAT,
    TOPIC_SUB_PROVISION,
    TOPIC_SUBSCRIBE_ALL,
)
from feature.enum import CommandStatus, RoomCommandType
from feature.FSM import statemachine
from feature.RFID import attendance

logger = logging.getLogger(__name__)


def create_mqtt_client() -> mqtt.Client:
    """Instantiate an aiomqtt Client with configured host/port/auth."""
    kwargs = {
        "hostname": BROKER_HOST,
        "port": BROKER_PORT,
        "identifier": "smartcampus-edge-worker",
    }
    if BROKER_USERNAME and BROKER_PASSWORD:
        kwargs["username"] = BROKER_USERNAME
        kwargs["password"] = BROKER_PASSWORD
    return mqtt.Client(**kwargs)


def _parse_timestamp(ts: str | None) -> datetime:
    """Parse ISO8601 string to datetime, fallback to now(utc)."""
    if ts:
        try:
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc)


def _extract_payload(raw: dict) -> tuple[dict, str | None, str | None]:
    """Support both wrapped envelope and flat JSON payloads."""
    msg_id = raw.get("message_id")
    ts = raw.get("timestamp")
    inner = raw.get("payload", raw)
    return inner, msg_id, ts


async def _handle_provision_request(client: mqtt.Client, payload: dict) -> None:
    """Store auto-provisioning requests from new devices."""
    inner, msg_id, ts = _extract_payload(payload)
    mac = inner.get("mac_address")
    dev_type = inner.get("device_type", "GENERIC")
    fw = inner.get("firmware_version")

    logger.info("Provision request: mac=%s, type=%s, fw=%s", mac, dev_type, fw)

    async with async_session() as db:
        try:
            await db.execute(
                insert(models.DeviceProvision).values(
                    mac_address=mac,
                    device_type=dev_type,
                    firmware_version=fw,
                    status="PENDING",
                    message_id=msg_id,
                    source_timestamp=_parse_timestamp(ts),
                )
            )
            await db.commit()
            logger.info("Recorded provision request for MAC: %s", mac)
        except Exception as e:
            await db.rollback()
            logger.error("Failed to insert provision request for %s: %s", mac, e)


async def _handle_heartbeat(client: mqtt.Client, payload: dict) -> None:
    """Store device heartbeat telemetry."""
    inner, msg_id, ts = _extract_payload(payload)
    device_id = inner.get("device_id")
    alive = inner.get("alive", True)
    firmware_version = inner.get("firmware_version")
    uptime = inner.get("uptime")

    logger.debug("Heartbeat: device=%s, alive=%s, uptime=%s", device_id, alive, uptime)

    async with async_session() as db:
        try:
            await db.execute(
                insert(models.Heartbeat).values(
                    device_id=UUID(str(device_id)) if device_id else None,
                    alive=alive,
                    firmware_version=firmware_version,
                    uptime=uptime,
                    message_id=msg_id,
                    source_timestamp=_parse_timestamp(ts),
                )
            )
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("Failed to insert heartbeat telemetry: %s", e)


async def _handle_environment_telemetry(client: mqtt.Client, payload: dict) -> None:
    """Store environment sensor readings (temp, humidity, smoke, CO2, air_quality)."""
    inner, msg_id, ts = _extract_payload(payload)
    room_id = inner.get("room_id")
    temperature = inner.get("temperature")
    humidity = inner.get("humidity")
    smoke_detected = inner.get("smoke_detected", False)
    smoke_value = inner.get("smoke_value")
    smoke_threshold = inner.get("smoke_threshold")
    smoke_state = inner.get("smoke_state", "NORMAL")
    co2 = inner.get("co2")
    air_quality = inner.get("air_quality")

    logger.info(
        "Environment: room=%s, temp=%s, humidity=%s, smoke=%s, co2=%s, air_quality=%s",
        room_id, temperature, humidity, smoke_state, co2, air_quality,
    )

    async with async_session() as db:
        try:
            await db.execute(
                insert(models.Environment).values(
                    room_id=UUID(str(room_id)) if room_id else None,
                    temperature=temperature,
                    humidity=humidity,
                    smoke_detected=smoke_detected,
                    smoke_value=smoke_value,
                    smoke_threshold=smoke_threshold,
                    smoke_state=smoke_state,
                    co2=co2,
                    air_quality=air_quality,
                    message_id=msg_id,
                    source_timestamp=_parse_timestamp(ts),
                )
            )
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("Failed to insert environment telemetry: %s", e)

    if smoke_state in ("SUSPECTED", "EMERGENCY") and room_id:
        async with async_session() as db:
            try:
                new_smoke, new_room = await statemachine.handle_smoke_event(
                    UUID(str(room_id)), smoke_state, db, mqtt_client=client,
                )
                await db.commit()
                logger.info(
                    "Room %s: smoke FSM updated -> smoke=%s, room=%s",
                    room_id, new_smoke.name,
                    new_room.name if new_room else "unchanged",
                )
            except Exception as e:
                await db.rollback()
                logger.error("Failed to update smoke FSM for room %s: %s", room_id, e)


async def _handle_occupancy_telemetry(client: mqtt.Client, payload: dict) -> None:
    """Store occupancy count changes from IR sensors."""
    inner, msg_id, ts = _extract_payload(payload)
    room_id = inner.get("room_id")
    occupancy_type = inner.get("occupancy_type")

    logger.info("Occupancy: room=%s, type=%s", room_id, occupancy_type)

    if occupancy_type == IRSignalType.IN.name:
        delta = 1
    elif occupancy_type == IRSignalType.OUT.name:
        delta = -1
    else:
        logger.warning("Invalid occupancy_type: %s", occupancy_type)
        return

    if not room_id:
        logger.warning("Missing room_id in occupancy telemetry")
        return

    room_uuid = UUID(str(room_id))

    async with async_session() as db:
        try:
            async with db.begin():
                result = await db.execute(
                    select(models.Occupancy.occupancy_count)
                    .where(models.Occupancy.room_id == room_uuid)
                    .order_by(models.Occupancy.occupancy_timestamp.desc())
                    .limit(1)
                    .with_for_update()
                )
                last_count = result.scalar()
                new_count = (last_count + delta) if last_count is not None else max(delta, 0)
                if new_count == 0:
                    try:
                        await statemachine.transition_to(
                            room_uuid, statemachine.RoomState.SAVING, db, mqtt_client=client
                        )
                    except Exception as e:
                        logger.warning("Transition to SAVING state skipped for room %s: %s", room_id, e)

                await db.execute(
                    insert(models.Occupancy).values(
                        room_id=room_uuid,
                        occupancy_type=occupancy_type,
                        occupancy_count=new_count,
                        message_id=msg_id,
                        source_timestamp=_parse_timestamp(ts),
                        occupancy_timestamp=func.now(),
                    )
                )

            # Publish discrepancy update if an active session exists
            await attendance.check_and_publish_discrepancy(
                client, room_uuid, db, current_occupancy=new_count
            )
        except Exception as e:
            logger.error("Failed to insert occupancy telemetry: %s", e)


async def _handle_rfid_event(client: mqtt.Client, payload: dict) -> None:
    """Process RFID card tap for attendance tracking."""
    inner, msg_id, ts = _extract_payload(payload)
    room_id = inner.get("room_id")
    card_uid = inner.get("card_uid")
    event_type = inner.get("event_type")

    logger.info(
        "RFID event: room=%s, card=%s, event=%s",
        room_id, card_uid, event_type,
    )

    if not room_id or not card_uid:
        logger.warning("Missing room_id or card_uid in RFID event: %s", inner)
        return

    async with async_session() as db:
        try:
            result = await db.execute(
                select(models.User.user_id).where(models.User.card_uid == card_uid)
            )
            user_id = result.scalar()
        except Exception as e:
            logger.error("Failed to query user for card %s: %s", card_uid, e)
            return

    try:
        if user_id:
            await attendance.handle_signed_user(client, card_uid, UUID(str(room_id)), user_id)
        else:
            await attendance.handle_unsigned_user(client, UUID(str(room_id)), card_uid=card_uid)
    except Exception as e:
        logger.error("Failed to process RFID attendance: %s", e)


async def _handle_command_ack(client: mqtt.Client, payload: dict) -> None:
    """Handle device acknowledgement of a command."""
    inner, msg_id, ts = _extract_payload(payload)
    logger.info(
        "Command ACK: device=%s, cmd=%s, success=%s",
        inner.get("mac_address"), inner.get("command_id"), inner.get("success"),
    )


async def _handle_scenario(client: mqtt.Client, payload: dict) -> None:
    """Handle automation scenario triggers."""
    inner, msg_id, ts = _extract_payload(payload)
    logger.info(
        "Scenario: id=%s, action=%s, triggered_by=%s",
        inner.get("scenario_id"), inner.get("action"), inner.get("triggered_by"),
    )


async def _dispatch_message(client: mqtt.Client, message: mqtt.Message) -> None:
    """Route an incoming message to the proper handler based on its topic."""
    topic = str(message.topic)
    try:
        payload = json.loads(message.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("Failed to decode message on %s: %s", topic, message.payload)
        return

    logger.debug("Received message on %s: %s", topic, payload)

    if topic == TOPIC_SUB_PROVISION:
        await _handle_provision_request(client, payload)
    elif topic == TOPIC_SUB_HEARTBEAT:
        await _handle_heartbeat(client, payload)
    elif "/telemetry/environment" in topic:
        await _handle_environment_telemetry(client, payload)
    elif "/telemetry/occupancy" in topic:
        await _handle_occupancy_telemetry(client, payload)
    elif "/telemetry/rfid" in topic or "/event/rfid" in topic or "/event/room/" in topic:
        await _handle_rfid_event(client, payload)
    elif "/response/command_ack" in topic or "/ack/device/" in topic:
        await _handle_command_ack(client, payload)
    elif "/scenario" in topic:
        await _handle_scenario(client, payload)
    else:
        logger.debug("Unhandled topic: %s", topic)


async def mqtt_listener() -> None:
    """Listen for incoming MQTT messages and dispatch them to handlers."""
    logger.info("MQTT listener starting loop...")
    while True:
        try:
            async with create_mqtt_client() as client:
                await client.subscribe(TOPIC_SUBSCRIBE_ALL, qos=1)
                logger.info("MQTT listener subscribed to %s", TOPIC_SUBSCRIBE_ALL)

                async for message in client.messages:
                    try:
                        await _dispatch_message(client, message)
                    except Exception:
                        logger.exception(
                            "Error handling message on %s", message.topic,
                        )

        except mqtt.MqttError as err:
            logger.warning(
                "MQTT connection lost: %s. Reconnecting in %ds...",
                err, RECONNECT_INTERVAL,
            )
            await asyncio.sleep(RECONNECT_INTERVAL)
        except Exception as err:
            logger.exception(
                "Unexpected error in MQTT listener: %s. Retrying in %ds...",
                err, RECONNECT_INTERVAL,
            )
            await asyncio.sleep(RECONNECT_INTERVAL)
