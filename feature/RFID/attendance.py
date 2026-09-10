import logging
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from database import async_session
import models
from feature.enum import CommandStatus, RoomCommandType , RoomStatusEnum
from feature.FSM.statemachine import RoomState, transition_to
from feature.mqtt.publisher import publish_room_command, publish_room_discrepancy

import aiomqtt as mqtt

logger = logging.getLogger(__name__)


async def check_and_publish_discrepancy(
    mqtt_client: mqtt.Client | None,
    room_id: UUID,
    db: AsyncSession,
    current_occupancy: int | None = None,
) -> None:
    """Calculate and publish discrepancy between sensor occupancy and RFID attendance."""
    if not mqtt_client:
        return

    try:
        now_ts = datetime.now(timezone.utc)
        result = await db.execute(
            select(models.RoomSession)
            .where(
                models.RoomSession.room_id == room_id,
                models.RoomSession.session_status == RoomStatusEnum.ACTIVE.value,
                (models.RoomSession.session_end_timestamp.is_(None))
                | (models.RoomSession.session_end_timestamp > now_ts),
            )
            .order_by(models.RoomSession.session_start_timestamp.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()
        if not session:
            return

        att_res = await db.execute(
            select(func.count(func.distinct(models.AttendanceRecord.user_id)))
            .where(models.AttendanceRecord.session_id == session.session_id)
        )
        attendance_count = att_res.scalar() or 0

        if current_occupancy is None:
            occ_res = await db.execute(
                select(models.Occupancy.occupancy_count)
                .where(models.Occupancy.room_id == room_id)
                .order_by(models.Occupancy.occupancy_timestamp.desc())
                .limit(1)
            )
            occupancy_count = occ_res.scalar() or 0
        else:
            occupancy_count = current_occupancy

        if occupancy_count == 0 and attendance_count == 0:
            discrepancy = 0
        else:
            has_lecturer_checked_in = session.lecturer_id is not None
            expected_lecturer_count = 1 if has_lecturer_checked_in else 0
            discrepancy = occupancy_count - attendance_count - expected_lecturer_count

        await publish_room_discrepancy(
            mqtt_client,
            str(room_id),
            str(session.session_id),
            occupancy_count,
            attendance_count,
            discrepancy,
        )
        logger.info(
            "Discrepancy for room %s (session %s): occ=%d, att=%d, diff=%d",
            room_id, session.session_id, occupancy_count, attendance_count, discrepancy,
        )
    except Exception as e:
        logger.error("Failed to check and publish discrepancy for room %s: %s", room_id, e)


async def handle_unsigned_user(
    mqtt_client: mqtt.Client | None,
    room_id: UUID,
    card_uid: str | None = None,
) -> None:
    """Handle RFID tap from an unregistered card."""
    logger.warning("Unregistered RFID card tapped: room=%s, card=%s", room_id, card_uid)

    async with async_session() as db:
        try:
            await db.execute(
                insert(models.AttendanceEvent).values(
                    room_id=room_id,
                    card_uid=card_uid,
                    event_type=models.AttendanceEventType.REJECT,
                )
            )
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("Failed to record unsigned user event: %s", e)
            raise

    if mqtt_client:
        await publish_room_command(
            mqtt_client, str(room_id), RoomCommandType.BUZZER, CommandStatus.ON
        )


async def session_initialization(
    mqtt_client: mqtt.Client | None,
    room_id: UUID,
    session_id: UUID,
    session_start: datetime,
) -> None:
    """Initialize session deadlines and end time."""
    session_deadline = session_start + timedelta(minutes=15)
    session_end = session_start + timedelta(minutes=45)

    async with async_session() as db:
        try:
            await db.execute(
                update(models.RoomSession)
                .where(models.RoomSession.session_id == session_id)
                .values(
                    room_id=room_id,
                    session_start_timestamp=session_start,
                    attendance_deadline_timestamp=session_deadline,
                    session_end_timestamp=session_end,
                )
            )
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("Failed to initialize session %s: %s", session_id, e)
            raise
        



async def handle_signed_user(
    mqtt_client: mqtt.Client | None,
    card_id: str,
    room_id: UUID,
    user_id: UUID,
) -> None:
    """Process attendance event for a registered user according to their role."""
    now_ts = datetime.now(timezone.utc)

    async with async_session() as db:
        try:
            result = await db.execute(
                select(models.User.role).where(models.User.user_id == user_id)
            )
            role = result.scalar()

            if role == models.UserRole.LECTURER:
                active_sess_res = await db.execute(
                    select(models.RoomSession)
                    .where(
                        models.RoomSession.room_id == room_id,
                        (models.RoomSession.session_end_timestamp.is_(None))
                        | (models.RoomSession.session_end_timestamp > now_ts),
                        models.RoomSession.lecturer_id == user_id,
                        models.RoomSession.session_status == RoomStatusEnum.ACTIVE.value,
                    )
                    .order_by(models.RoomSession.session_start_timestamp.desc())
                    .limit(1)
                    .with_for_update()
                )
                active_session = active_sess_res.scalar_one_or_none()

                if active_session is None:
                    await transition_to(room_id, RoomState.LECTURE, db, mqtt_client=mqtt_client)

                    new_session_id = uuid.uuid4()
                    session_deadline = now_ts + timedelta(minutes=15)
                    session_end = now_ts + timedelta(minutes=45)

                    await db.execute(
                        insert(models.RoomSession).values(
                            session_id=new_session_id,
                            room_id=room_id,
                            lecturer_id=user_id,
                            session_start_timestamp=now_ts,
                            attendance_deadline_timestamp=session_deadline,
                            session_end_timestamp=session_end,
                            session_status=RoomStatusEnum.ACTIVE.value
                        )
                    )
                    await db.execute(
                        insert(models.AttendanceEvent).values(
                            room_id=room_id,
                            user_id=user_id,
                            card_uid=card_id,
                            event_type=models.AttendanceEventType.CHECK_IN,
                        )
                    )
                    await db.commit()

                    if mqtt_client:
                        await publish_room_command(mqtt_client, str(room_id), RoomCommandType.BUZZER, CommandStatus.ON)
                        await publish_room_command(mqtt_client, str(room_id), RoomCommandType.LIGHT, CommandStatus.ON)
                        await publish_room_command(mqtt_client, str(room_id), RoomCommandType.FAN, CommandStatus.ON)
                    logger.info("Lecturer %s started session %s in room %s", user_id, new_session_id, room_id)
                else:
                    await db.execute(
                        update(models.RoomSession)
                        .where(models.RoomSession.session_id == active_session.session_id)
                        .values(
                            session_status=RoomStatusEnum.ENDED.value,
                            session_end_timestamp=now_ts,
                        )
                    )
                    await db.execute(
                        insert(models.AttendanceEvent).values(
                            room_id=room_id,
                            user_id=user_id,
                            card_uid=card_id,
                            event_type=models.AttendanceEventType.CHECK_OUT,
                        )
                    )
                    count = await db.execute(select(models.Occupancy.occupancy_count).where(models.Occupancy.room_id==room_id).order_by(models.Occupancy.occupancy_timestamp.desc()).limit(1))
                    current_occupancy = count.scalar() or 0
                    
                    if current_occupancy > 0:
                        await transition_to(room_id, RoomState.SELF_STUDY, db, mqtt_client=mqtt_client)
                        await db.commit()
                        if mqtt_client:
                            await publish_room_command(mqtt_client, str(room_id), RoomCommandType.BUZZER, CommandStatus.ON)
                    else:
                        await transition_to(room_id, RoomState.SAVING, db, mqtt_client=mqtt_client)
                        await db.commit()
                        if mqtt_client:
                            await publish_room_command(mqtt_client, str(room_id), RoomCommandType.BUZZER, CommandStatus.ON)
                            await publish_room_command(mqtt_client, str(room_id), RoomCommandType.LIGHT, CommandStatus.OFF)
                            await publish_room_command(mqtt_client, str(room_id), RoomCommandType.FAN, CommandStatus.OFF)
                    
                    logger.info("Lecturer %s ended session %s in room %s", user_id, active_session.session_id, room_id)

            elif role == models.UserRole.STUDENT:
                result = await db.execute(
                    select(models.RoomSession)
                    .where(
                        models.RoomSession.room_id == room_id,
                        models.RoomSession.session_status == RoomStatusEnum.ACTIVE.value,
                        (models.RoomSession.session_end_timestamp.is_(None))
                        | (models.RoomSession.session_end_timestamp > now_ts),
                    )
                    .order_by(models.RoomSession.session_start_timestamp.desc())
                    .limit(1)
                )
                session = result.scalar_one_or_none()

                if session is not None:
                    is_late = now_ts > session.attendance_deadline_timestamp

                    existing_rec = (await db.execute(
                        select(models.AttendanceRecord)
                        .where(
                            models.AttendanceRecord.session_id == session.session_id,
                            models.AttendanceRecord.user_id == user_id,
                        )
                    )).scalar_one_or_none()

                    if not existing_rec:
                        await db.execute(
                            insert(models.AttendanceRecord).values(
                                session_id=session.session_id,
                                card_uid=card_id,
                                room_id=room_id,
                                user_id=user_id,
                                late=is_late,
                                attendance_timestamp=now_ts,
                            )
                        )
                    else:
                        logger.info("Student %s already recorded for session %s", user_id, session.session_id)

                    await db.execute(
                        insert(models.AttendanceEvent).values(
                            room_id=room_id,
                            user_id=user_id,
                            card_uid=card_id,
                            event_type=models.AttendanceEventType.CHECK_IN,
                        )
                    )
                    await db.commit()

                    if mqtt_client:
                        await publish_room_command(
                            mqtt_client, str(room_id), RoomCommandType.BUZZER, CommandStatus.ON
                        )
                        await check_and_publish_discrepancy(mqtt_client, room_id, db)
                else:
                    logger.warning(
                        "Student %s tapped card in room %s but no active session found",
                        user_id, room_id,
                    )
                    await db.execute(
                        insert(models.AttendanceEvent).values(
                            room_id=room_id,
                            user_id=user_id,
                            card_uid=card_id,
                            event_type=models.AttendanceEventType.REJECT,
                        )
                    )
                    await db.commit()

                    if mqtt_client:
                        await publish_room_command(
                            mqtt_client, str(room_id), RoomCommandType.BUZZER, CommandStatus.ON
                        )

            elif role == models.UserRole.ADMIN:
                await db.execute(
                    insert(models.AttendanceEvent).values(
                        room_id=room_id,
                        user_id=user_id,
                        card_uid=card_id,
                        event_type=models.AttendanceEventType.CHECK_IN,
                    )
                )
                await db.commit()

                if mqtt_client:
                    await publish_room_command(
                        mqtt_client, str(room_id), RoomCommandType.DOOR, CommandStatus.UNLOCKED
                    )
                    await publish_room_command(
                        mqtt_client, str(room_id), RoomCommandType.BUZZER, CommandStatus.ON
                    )

            else:
                logger.warning("User %s with unhandled role %s tapped card", user_id, role)
                await db.execute(
                    insert(models.AttendanceEvent).values(
                        room_id=room_id,
                        user_id=user_id,
                        card_uid=card_id,
                        event_type=models.AttendanceEventType.REJECT,
                    )
                )
                await db.commit()

                if mqtt_client:
                    await publish_room_command(
                        mqtt_client, str(room_id), RoomCommandType.BUZZER, CommandStatus.ON
                    )

        except Exception as e:
            await db.rollback()
            logger.error("Failed to handle signed user attendance: %s", e)
            raise


async def handle_auto_end_session(
    mqtt_client: mqtt.Client | None,
    room_id: UUID,
) -> None:
    """Automatically end the active session if it has passed its end timestamp."""
    now_ts = datetime.now(timezone.utc)

    async with async_session() as db:
        try:
            result = await db.execute(
                select(models.RoomSession)
                .where(
                    models.RoomSession.room_id == room_id,
                    models.RoomSession.session_end_timestamp <= now_ts,
                    models.RoomSession.session_end_timestamp.isnot(None),
                    models.RoomSession.session_status == RoomStatusEnum.ACTIVE.value,
                )
                .order_by(models.RoomSession.session_start_timestamp.desc())
                .limit(1)
            )
            session = result.scalar_one_or_none()

            if session:
                await db.execute(
                    update(models.RoomSession)
                    .where(models.RoomSession.session_id == session.session_id)
                    .values(session_status=RoomStatusEnum.ENDED.value)
                )
                await db.execute(
                    insert(models.AttendanceEvent).values(
                        room_id=room_id,
                        event_type=models.AttendanceEventType.CHECK_OUT,
                    )
                )
                await db.commit()

                count = await db.execute(select(models.Occupancy.occupancy_count).where(models.Occupancy.room_id == room_id).order_by(models.Occupancy.occupancy_timestamp.desc()).limit(1))
                current_occupancy = count.scalar() or 0
                
                if current_occupancy > 0:
                    await transition_to(room_id, RoomState.SELF_STUDY, db, mqtt_client=mqtt_client)
                    await db.commit()
                else:
                    await transition_to(room_id, RoomState.SAVING, db, mqtt_client=mqtt_client)
                    await db.commit()
                    if mqtt_client:
                        await publish_room_command(mqtt_client, str(room_id), RoomCommandType.LIGHT, CommandStatus.OFF)
                        await publish_room_command(mqtt_client, str(room_id), RoomCommandType.FAN, CommandStatus.OFF)
                
                logger.info("Automatically ended session %s in room %s", session.session_id, room_id)

        except Exception as e:
            await db.rollback()
            logger.error("Failed to auto-end session for room %s: %s", room_id, e)
            raise
        
async def auto_end_loop(create_client=None, poll_interval: int | None = None) -> None:
    """Polling task: check and close expired sessions every 5 minutes (or via SESSION_AUTO_END_POLL_INTERVAL)."""
    import asyncio
    import os
    POLL_INTERVAL = poll_interval if poll_interval is not None else int(os.getenv("SESSION_AUTO_END_POLL_INTERVAL", "300"))

    if create_client is None:
        from feature.mqtt.mqtt_worker import create_mqtt_client
        create_client = lambda: create_mqtt_client(identifier="smartcampus-edge-autoend")

    logger.info("Started session auto-end polling loop (interval=%ds)", POLL_INTERVAL)

    while True:
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(models.RoomSession.room_id)
                    .where(
                        models.RoomSession.session_end_timestamp <= func.now(),
                        models.RoomSession.session_end_timestamp.isnot(None),
                        models.RoomSession.session_status == RoomStatusEnum.ACTIVE.value,
                    )
                    .distinct()
                )
                expired_room_ids = result.scalars().all()

            if expired_room_ids:
                logger.info("Found %d room(s) with expired sessions: %s", len(expired_room_ids), expired_room_ids)
                async with create_client() as client:
                    for room_id in expired_room_ids:
                        try:
                            await handle_auto_end_session(mqtt_client=client, room_id=room_id)
                        except Exception as e:
                            logger.error("Failed to auto-end session for room %s: %s", room_id, e)

        except asyncio.CancelledError:
            logger.info("Session auto-end polling loop cancelled.")
            break
        except Exception as e:
            logger.error("Error in auto_end_loop: %s", e)

        try:
            await asyncio.sleep(POLL_INTERVAL)
        except asyncio.CancelledError:
            logger.info("Session auto-end polling loop cancelled during sleep.")
            break
