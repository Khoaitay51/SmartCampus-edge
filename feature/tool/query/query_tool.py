import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_, text

import models
from database import async_session

logger = logging.getLogger(__name__)


async def get_environment(room_id: str, since: datetime) -> list:
    """Fetch all environment telemetry rows for *room_id* recorded on or after *since*."""
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    now_ts = datetime.now(timezone.utc)

    stmt = (
        select(models.Environment)
        .where(
            models.Environment.room_id == room_id,
            models.Environment.environment_timestamp >= since,
            models.Environment.environment_timestamp < now_ts,
        )
        .order_by(models.Environment.environment_timestamp)
    )

    async with async_session() as db:
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def get_raw_summaries(limit: int = 50) -> list:
    """Fetch the most recent raw summarizer records."""
    stmt = (
        select(models.RawSummarizer)
        .order_by(models.RawSummarizer.raw_summarizer_timestamp.desc())
        .limit(limit)
    )

    async with async_session() as db:
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def get_schedule(room_id: str | None = None, date: str | None = None) -> dict:
    """Return active/upcoming room session (schedule) for a given room and date."""
    async with async_session() as db:
        # Determine date range
        if date:
            try:
                day = datetime.fromisoformat(date).replace(tzinfo=timezone(timedelta(hours=7)))
            except ValueError:
                day = datetime.now(timezone(timedelta(hours=7)))
        else:
            day = datetime.now(timezone(timedelta(hours=7)))

        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end   = day.replace(hour=23, minute=59, second=59, microsecond=0)
        now_ts    = datetime.now(timezone.utc)

        stmt = select(models.RoomSession).where(
            models.RoomSession.session_start_timestamp >= day_start,
            models.RoomSession.session_start_timestamp <= day_end,
        )
        if room_id:
            stmt = stmt.where(models.RoomSession.room_id == room_id)
        stmt = stmt.order_by(models.RoomSession.session_start_timestamp)

        rows = (await db.execute(stmt)).scalars().all()

        active_session = None
        classes_today = []
        for s in rows:
            end_ts = s.session_end_timestamp
            is_active = (
                s.session_status == "active"
                and s.session_start_timestamp <= now_ts
                and (end_ts is None or end_ts >= now_ts)
            )
            entry = {
                "session_id": str(s.session_id),
                "class_code": s.class_code,
                "start": s.session_start_timestamp.astimezone(timezone(timedelta(hours=7))).strftime("%H:%M"),
                "end": end_ts.astimezone(timezone(timedelta(hours=7))).strftime("%H:%M") if end_ts else None,
                "status": "active" if is_active else ("ended" if s.session_status == "ended" else "scheduled"),
                "is_exam": s.is_exam,
            }
            classes_today.append(entry)
            if is_active:
                active_session = entry

        return {
            "room_id": room_id,
            "date": day.strftime("%Y-%m-%d"),
            "active_session": active_session,
            "classes_today": classes_today,
        }


async def get_room_history(room_id: str, hours: int = 24) -> dict:
    """Return room state transition history for the last N hours."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with async_session() as db:
        # State transitions from room_state table
        stmt = (
            select(models.RoomState)
            .where(
                models.RoomState.room_id == room_id,
                models.RoomState.room_state_timestamp >= since,
            )
            .order_by(models.RoomState.room_state_timestamp)
        )
        states = (await db.execute(stmt)).scalars().all()

        transitions = [
            {
                "timestamp": s.room_state_timestamp.isoformat(),
                "mode": s.room_mode.value if hasattr(s.room_mode, "value") else str(s.room_mode),
                "status": s.room_status.value if hasattr(s.room_status, "value") else str(s.room_status),
            }
            for s in states
        ]

        # Current mode = latest transition
        current_mode = transitions[-1]["mode"] if transitions else "UNKNOWN"

        return {
            "room_id": room_id,
            "hours": hours,
            "current_mode": current_mode,
            "transitions": transitions,
        }

