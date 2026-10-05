import asyncio
import json
import logging
import uuid
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
    TOPIC_COMMAND_ACK,
    TOPIC_DEVICE_HEARTBEAT,
    TOPIC_ENV_TELEMETRY,
    TOPIC_OCCUPANCY_TELEMETRY,
    TOPIC_ROOM_RFID_EVENT,
    TOPIC_SCENARIO,
    TOPIC_SUB_HEARTBEAT,
    TOPIC_SUB_PROVISION,
    TOPIC_SUBSCRIBE_ALL,
    TOPIC_CARD_REGISTRATION_REQUEST,
)
from feature.enum import CommandStatus, RoomCommandType
from feature.FSM import statemachine
from feature.mqtt import publisher
from feature.RFID import attendance
from feature.command.executor import update_command_status

logger = logging.getLogger(__name__)


def create_mqtt_client(identifier: str | None = None) -> mqtt.Client:
    """Instantiate an aiomqtt Client with configured host/port/auth."""
    kwargs = {
        "hostname": BROKER_HOST,
        "port": BROKER_PORT,
        "identifier": identifier or "smartcampus-edge-worker",
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

    logger.info("Heartbeat: device=%s, alive=%s, uptime=%s", device_id, alive, uptime)

    if not device_id:
        logger.warning("Missing device_id in heartbeat: %s", inner)
        return

    dev_uuid: UUID | None = None
    try:
        dev_uuid = UUID(str(device_id))
    except (ValueError, TypeError):
        dev_uuid = None

    ts_dt = _parse_timestamp(ts)

    async with async_session() as db:
        try:
            existing_dev = None
            if dev_uuid:
                existing_dev = (await db.execute(
                    select(models.Device).where(models.Device.device_id == dev_uuid)
                )).scalar_one_or_none()

            if not existing_dev:
                mac_candidate = inner.get("mac_address") or str(device_id)
                dev_res = await db.execute(
                    select(models.Device).where(models.Device.mac_address == mac_candidate)
                )
                existing_dev = dev_res.scalar_one_or_none()

            if existing_dev:
                dev_uuid = existing_dev.device_id
            else:
                if dev_uuid is None:
                    dev_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(device_id))
                mac_str = inner.get("mac_address") or str(device_id)
                new_dev = models.Device(
                    device_id=dev_uuid,
                    mac_address=mac_str,
                    device_name=f"esp32_{mac_str.replace(':', '')[-4:]}",
                    device_status=models.DeviceStatusEnum.online if alive else models.DeviceStatusEnum.offline,
                    last_seen_timestamp=ts_dt,
                )
                db.add(new_dev)
                await db.flush()

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

    # -- Notable event detection (Edge -> AI Agent) -----------------------
    if room_id and client:
        # 1. Cảnh báo khói / Nghi ngờ cháy
        if smoke_state in ("SUSPECTED", "EMERGENCY"):
            try:
                await publisher.publish_notable_event(
                    client=client,
                    room_id=str(room_id),
                    event_type="smoke_detected",
                    severity="critical" if smoke_state == "EMERGENCY" else "warning",
                    title=f"Phát hiện cảnh báo khói ({smoke_state})",
                    description=f"Cảm biến MQ2 phát hiện nồng độ khói bất thường tại phòng {room_id} (giá trị: {smoke_value}, ngưỡng: {smoke_threshold}).",
                    event_data={
                        "smoke_state": smoke_state,
                        "smoke_value": smoke_value,
                        "smoke_threshold": smoke_threshold,
                    },
                )
            except Exception as exc:
                logger.error("Failed to publish smoke notable event: %s", exc)

        # 2. Nhiệt độ bất thường
        if temperature is not None:
            try:
                temp_val = float(temperature)
                if temp_val > 38.0 or temp_val < 15.0:
                    await publisher.publish_notable_event(
                        client=client,
                        room_id=str(room_id),
                        event_type="temperature_anomaly",
                        severity="critical" if temp_val >= 42.0 else "warning",
                        title=f"Nhiệt độ phòng bất thường ({temp_val}°C)",
                        description=f"Nhiệt độ đo được tại phòng {room_id} là {temp_val}°C, vượt ngưỡng an toàn (15°C - 38°C).",
                        event_data={
                            "temperature": temp_val,
                            "humidity": humidity,
                        },
                    )
            except (ValueError, TypeError):
                pass
            except Exception as exc:
                logger.error("Failed to publish temperature notable event: %s", exc)

        # 3. Nồng độ CO2 cao / chất lượng không khí kém
        if co2 is not None:
            try:
                co2_val = float(co2)
                if co2_val > 1000.0:
                    await publisher.publish_notable_event(
                        client=client,
                        room_id=str(room_id),
                        event_type="co2_hazard",
                        severity="critical" if co2_val >= 1500.0 else "warning",
                        title=f"Nồng độ CO2 vượt ngưỡng an toàn ({co2_val} ppm)",
                        description=f"Nồng độ CO2 tại phòng {room_id} đạt {co2_val} ppm, không khí ngột ngạt cần bật quạt/thông gió.",
                        event_data={
                            "co2": co2_val,
                            "air_quality": air_quality,
                        },
                    )
            except (ValueError, TypeError):
                pass
            except Exception as exc:
                logger.error("Failed to publish CO2 notable event: %s", exc)


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

    # Update command status in DB
    success = inner.get("success", True)
    cmd_id = inner.get("command_id")
    new_status = "acked" if success else "failed"

    updated = await update_command_status(
        command_id=UUID(cmd_id) if cmd_id else None,
        message_id=msg_id,
        new_status=new_status,
    )
    if updated:
        logger.info("Command status updated to %s (cmd=%s)", new_status, cmd_id or msg_id)


async def _handle_scenario(client: mqtt.Client, payload: dict) -> None:
    """Handle automation scenario triggers."""
    inner, msg_id, ts = _extract_payload(payload)
    logger.info(
        "Scenario: id=%s, action=%s, triggered_by=%s",
        inner.get("scenario_id"), inner.get("action"), inner.get("triggered_by"),
    )


async def _handle_card_registration_request(client: mqtt.Client, payload: dict) -> None:
    """Process card registration request from Corridor Node (or other RFID nodes)."""
    inner, msg_id, ts = _extract_payload(payload)
    mac_address = inner.get("mac_address")
    card_uid = inner.get("card_uid")
    room_id_str = inner.get("room_id")
    note = inner.get("note", "Scanned at Corridor RFID Node")

    logger.info(
        "Card registration request: mac=%s, card=%s, room=%s",
        mac_address, card_uid, room_id_str,
    )

    if not card_uid or not mac_address:
        logger.warning("Missing card_uid or mac_address in registration request: %s", inner)
        return

    room_uuid = None
    if room_id_str:
        try:
            room_uuid = UUID(str(room_id_str))
        except (ValueError, TypeError):
            pass

    async with async_session() as db:
        try:
            # 1. Kiem tra xem the da duoc gan cho user nao chua (bang users)
            user_res = await db.execute(
                select(models.User).where(models.User.card_uid == card_uid)
            )
            existing_user = user_res.scalar_one_or_none()

            if existing_user:
                logger.info(
                    "Card %s is already assigned to user %s (%s)",
                    card_uid, existing_user.username, existing_user.user_id,
                )
                await publisher.publish_card_registration_response(
                    client,
                    mac_address,
                    {
                        "request_id": str(uuid.uuid4()),
                        "card_uid": card_uid,
                        "status": "approved",
                        "assigned_user_id": str(existing_user.user_id),
                        "assigned_user_name": existing_user.full_name or existing_user.username,
                        "message": "Thẻ đã được đăng ký và kích hoạt",
                    },
                )
                return

            # 2. Kiem tra xem the da co request PENDING truoc do chua (tranh duplicate spam)
            req_res = await db.execute(
                select(models.CardRegistrationRequest).where(
                    models.CardRegistrationRequest.card_uid == card_uid,
                    models.CardRegistrationRequest.status == models.CardRegistrationStatus.PENDING,
                ).limit(1)
            )
            existing_req = req_res.scalar_one_or_none()

            if existing_req:
                req_id = str(existing_req.request_id)
                logger.info("Pending registration request already exists for card %s (id=%s)", card_uid, req_id)
            else:
                # 3. Tao moi ban ghi CardRegistrationRequest voi status PENDING
                new_req = models.CardRegistrationRequest(
                    card_uid=card_uid,
                    mac_address=mac_address,
                    room_id=room_uuid,
                    status=models.CardRegistrationStatus.PENDING,
                    note=note,
                )
                db.add(new_req)
                await db.commit()
                await db.refresh(new_req)
                req_id = str(new_req.request_id)
                logger.info("Saved new CardRegistrationRequest: id=%s, card=%s, status=PENDING", req_id, card_uid)

            # 4. Phan hoi ve Node Hanh lang qua MQTT
            await publisher.publish_card_registration_response(
                client,
                mac_address,
                {
                    "request_id": req_id,
                    "card_uid": card_uid,
                    "status": "pending",
                    "assigned_user_id": None,
                    "assigned_user_name": None,
                    "message": "Thẻ chưa đăng ký - Yêu cầu đang chờ Admin duyệt",
                },
            )

        except Exception as e:
            await db.rollback()
            logger.error("Failed to process card registration request: %s", e)


async def _handle_card_registration_response(client: mqtt.Client, payload: dict) -> None:
    """Sync approved card registration from Web UI / AI Backend into Edge DB."""
    inner, msg_id, ts = _extract_payload(payload)
    card_uid = inner.get("card_uid")
    status = str(inner.get("status", "")).lower()
    assigned_user_id_str = inner.get("assigned_user_id")
    assigned_name = inner.get("assigned_user_name") or "Người dùng"
    role_str = str(inner.get("role", "student")).lower()
    username = inner.get("username") or f"user_{card_uid}"

    if status != "approved" or not card_uid:
        return

    logger.info("Auto-sync: Nhận phản hồi duyệt thẻ %s cho user %s (role: %s) -> Đồng bộ Edge DB", card_uid, assigned_name, role_str)

    role_enum = models.UserRole.LECTURER if ("lecturer" in role_str or "giang" in role_str) else (
        models.UserRole.ADMIN if "admin" in role_str else models.UserRole.STUDENT
    )

    try:
        assigned_uuid = UUID(str(assigned_user_id_str)) if assigned_user_id_str else uuid.uuid4()
    except (ValueError, TypeError):
        assigned_uuid = uuid.uuid4()

    async with async_session() as db:
        try:
            # 1. Update existing user holding this card if any (ix_users_card_uid is unique)
            existing_by_card = (await db.execute(select(models.User).where(models.User.card_uid == card_uid))).scalar_one_or_none()
            if existing_by_card and existing_by_card.user_id != assigned_uuid:
                existing_by_card.card_uid = None

            # 2. Insert or update User
            existing_user = (await db.execute(select(models.User).where(models.User.user_id == assigned_uuid))).scalar_one_or_none()
            if existing_user:
                existing_user.card_uid = card_uid
                existing_user.role = role_enum
                existing_user.full_name = assigned_name
                if username:
                    existing_user.username = username
            else:
                new_user = models.User(
                    user_id=assigned_uuid,
                    card_uid=card_uid,
                    role=role_enum,
                    username=username,
                    full_name=assigned_name,
                )
                db.add(new_user)

            # 3. Update CardRegistrationRequest
            req = (await db.execute(
                select(models.CardRegistrationRequest).where(models.CardRegistrationRequest.card_uid == card_uid)
            )).scalar_one_or_none()
            if req:
                req.status = models.CardRegistrationStatus.APPROVED
                req.assigned_user_id = assigned_uuid

            await db.commit()
            logger.info("Auto-sync: Đã đồng bộ thành công thẻ %s (%s - %s) vào Edge DB", card_uid, assigned_name, role_enum.value)
        except Exception as e:
            await db.rollback()
            logger.error("Auto-sync: Lỗi khi đồng bộ thẻ %s vào Edge DB: %s", card_uid, e)


async def _handle_device_status(client: mqtt.Client, payload: dict, topic: str) -> None:
    """Handle device status updates and LWT offline messages (FR-DM-05)."""
    inner, msg_id, ts = _extract_payload(payload)
    device_id = inner.get("device_id")
    if not device_id:
        parts = topic.split("/")
        if len(parts) >= 4:
            device_id = parts[3]
    status_str = inner.get("device_status", "offline")
    status_enum = models.DeviceStatusEnum.online if status_str == "online" else models.DeviceStatusEnum.offline
    ts_dt = _parse_timestamp(ts)

    async with async_session() as db:
        try:
            dev_uuid = None
            try:
                dev_uuid = UUID(str(device_id))
            except (ValueError, TypeError):
                pass

            if dev_uuid:
                await db.execute(
                    update(models.Device)
                    .where(models.Device.device_id == dev_uuid)
                    .values(device_status=status_enum, last_seen_timestamp=ts_dt)
                )
            else:
                await db.execute(
                    update(models.Device)
                    .where(models.Device.mac_address == str(device_id))
                    .values(device_status=status_enum, last_seen_timestamp=ts_dt)
                )
            await db.commit()
            logger.info("Updated device status: device=%s, status=%s", device_id, status_str)
        except Exception as e:
            await db.rollback()
            logger.error("Failed to update device status: %s", e)


async def _dispatch_message(client: mqtt.Client, message: mqtt.Message) -> None:
    """Route an incoming message to the proper handler based on its topic."""
    topic = str(message.topic)
    try:
        payload = json.loads(message.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("Failed to decode message on %s: %s", topic, message.payload)
        return

    # Skip messages published by this Edge server itself (self-subscribe via wildcard)
    if (
        "/command/room/" in topic
        or "/command/device/" in topic
        or topic.endswith("/state")
        or topic.endswith("/discrepancy")
    ):
        return

    logger.info("Received message on %s: %s", topic, payload)

    if message.topic.matches(TOPIC_SUB_PROVISION):
        await _handle_provision_request(client, payload)
    elif message.topic.matches(TOPIC_DEVICE_HEARTBEAT):
        await _handle_heartbeat(client, payload)
    elif message.topic.matches(TOPIC_ENV_TELEMETRY):
        await _handle_environment_telemetry(client, payload)
    elif message.topic.matches(TOPIC_OCCUPANCY_TELEMETRY):
        await _handle_occupancy_telemetry(client, payload)
    elif message.topic.matches(TOPIC_ROOM_RFID_EVENT) or "/telemetry/rfid" in topic or "/event/rfid" in topic:
        await _handle_rfid_event(client, payload)
    elif message.topic.matches(TOPIC_CARD_REGISTRATION_REQUEST) or "/card/registration/request" in topic:
        await _handle_card_registration_request(client, payload)
    elif "/card/registration/response" in topic:
        await _handle_card_registration_response(client, payload)
    elif message.topic.matches(TOPIC_COMMAND_ACK) or "/response/command_ack" in topic:
        await _handle_command_ack(client, payload)
    elif message.topic.matches(TOPIC_SCENARIO):
        await _handle_scenario(client, payload)
    elif "/device/" in topic and topic.endswith("/status"):
        await _handle_device_status(client, payload, topic)
    else:
        logger.warning("Unhandled topic received on %s", topic)


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
