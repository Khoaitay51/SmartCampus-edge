import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import aiomqtt as mqtt
from sqlalchemy import func, insert, select, update

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
from feature.mqtt import publisher
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
    """Store auto-provisioning requests and respond if device is already configured."""
    inner, msg_id, ts = _extract_payload(payload)
    mac = inner.get("mac_address")
    dev_type = inner.get("device_type", "GENERIC")
    fw = inner.get("firmware_version")

    logger.info("Provision request: mac=%s, type=%s, fw=%s", mac, dev_type, fw)
    if not mac:
        logger.warning("Missing mac_address in provision request: %s", inner)
        return

    async with async_session() as db:
        try:
            result = await db.execute(
                select(models.Device).where(models.Device.mac_address == mac)
            )
            device = result.scalar_one_or_none()

            if device is not None:
                device.device_firmware_version = fw
                device.last_seen_timestamp = _parse_timestamp(ts)
                await db.commit()
                logger.info("Updated existing device for MAC: %s", mac)

                if device.room_id and client:
                    room_res = await db.execute(
                        select(models.Room).where(models.Room.room_id == device.room_id)
                    )
                    room = room_res.scalar_one_or_none()
                    room_type = room.room_type.name.lower() if (room and hasattr(room.room_type, "name")) else "classroom"
                    await publisher.publish_provisioning_response(
                        client,
                        mac,
                        {
                            "device_id": str(device.device_id),
                            "device_name": device.device_name or f"{dev_type}_{mac.replace(':', '')[-4:]}",
                            "room_id": str(device.room_id),
                            "room_type": room_type,
                            "firmware_version": fw or device.device_firmware_version or "1.0.0",
                            "heartbeat_interval": 30,
                        },
                    )
            else:
                import uuid as _uuid
                new_dev = models.Device(
                    device_id=_uuid.uuid4(),
                    mac_address=mac,
                    device_name=f"{dev_type}_{mac.replace(':', '')[-4:]}",
                    device_firmware_version=fw,
                    device_status=models.DeviceStatusEnum.offline,
                    last_seen_timestamp=_parse_timestamp(ts),
                )
                db.add(new_dev)
                await db.commit()
                logger.info("Registered new pending device with MAC: %s", mac)
        except Exception as e:
            await db.rollback()
            logger.error("Failed to process provision request for %s: %s", mac, e)


async def _handle_heartbeat(client: mqtt.Client, payload: dict) -> None:
    """Store device heartbeat telemetry and update device status."""
    inner, msg_id, ts = _extract_payload(payload)
    device_id = inner.get("device_id")
    alive = inner.get("alive", True)
    firmware_version = inner.get("firmware_version")
    uptime = inner.get("uptime")

    logger.debug("Heartbeat: device=%s, alive=%s, uptime=%s", device_id, alive, uptime)

    if not device_id:
        logger.warning("Missing device_id in heartbeat: %s", inner)
        return

    dev_uuid = UUID(str(device_id))
    ts_dt = _parse_timestamp(ts)

    async with async_session() as db:
        try:
            await db.execute(
                insert(models.DeviceHeartbeat).values(
                    device_id=dev_uuid,
                    alive=alive,
                    firmware_version=firmware_version,
                    uptime=uptime,
                    message_id=msg_id,
                    source_timestamp=ts_dt,
                )
            )
            await db.execute(
                update(models.Device)
                .where(models.Device.device_id == dev_uuid)
                .values(
                    device_status=models.DeviceStatusEnum.online if alive else models.DeviceStatusEnum.offline,
                    last_seen_timestamp=ts_dt,
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
    smoke_state_raw = inner.get("smoke_state", "NORMAL")
    smoke_state = str(smoke_state_raw).upper() if smoke_state_raw else "NORMAL"
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
                    smoke_state=models.SmokeState[smoke_state] if smoke_state in models.SmokeState.__members__ else models.SmokeState.NORMAL,
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

    if smoke_state in ("NORMAL", "SUSPECTED", "EMERGENCY") and room_id:
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
    """Store occupancy count changes from IR sensors with clamp and mode protection."""
    inner, msg_id, ts = _extract_payload(payload)
    room_id = inner.get("room_id")
    occupancy_type_raw = inner.get("occupancy_type")
    occupancy_type = str(occupancy_type_raw).upper() if occupancy_type_raw else ""

    logger.info("Occupancy: room=%s, type=%s", room_id, occupancy_type)

    if occupancy_type == IRSignalType.IN.name:
        delta = 1
    elif occupancy_type == IRSignalType.OUT.name:
        delta = -1
    else:
        logger.warning("Invalid occupancy_type: %s", occupancy_type_raw)
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
                new_count = max(0, (last_count + delta)) if last_count is not None else max(delta, 0)

                current_room_state = await statemachine.get_current_state(room_uuid, statemachine.RoomState, db)

                if new_count == 0:
                    if current_room_state == statemachine.RoomState.SELF_STUDY:
                        try:
                            await statemachine.transition_to(
                                room_uuid, statemachine.RoomState.SAVING, db, mqtt_client=client
                            )
                        except Exception as e:
                            logger.warning("Transition to SAVING state skipped for room %s: %s", room_id, e)
                elif new_count > 0:
                    # Auto-transition to SELF_STUDY only if room was in SAVING
                    if current_room_state == statemachine.RoomState.SAVING:
                        try:
                            await statemachine.transition_to(
                                room_uuid, statemachine.RoomState.SELF_STUDY, db, mqtt_client=client
                            )
                        except Exception as e:
                            logger.warning("Transition to SELF_STUDY state skipped for room %s: %s", room_id, e)

                await db.execute(
                    insert(models.Occupancy).values(
                        room_id=room_uuid,
                        occupancy_type=IRSignalType[occupancy_type],
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
