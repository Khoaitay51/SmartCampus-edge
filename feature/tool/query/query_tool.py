import logging
from datetime import datetime, timezone, timedelta, date as date_type
from typing import Any

from sqlalchemy import select, and_, text

import models
from database import async_session

logger = logging.getLogger(__name__)


async def get_environment(room_id: str, since: datetime, limit: int = 200) -> list:
    """Fetch raw environment telemetry rows for *room_id* recorded on or after *since*."""
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
        .limit(limit)
    )

    async with async_session() as db:
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "temperature": r.temperature,
                "humidity": r.humidity,
                "co2": r.co2,
                "smoke_value": r.smoke_value,
                "environment_timestamp": r.environment_timestamp.isoformat() if r.environment_timestamp else None,
            }
            for r in rows
        ]


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


async def get_schedule(room_id: str | None = None, date: str | None = None) -> dict[str, Any]:
    """Query lịch học (RoomSession) theo phòng hoặc theo ngày."""
    async with async_session() as db:
        conditions = []

        if room_id:
            conditions.append(models.RoomSession.room_id == room_id)

        # Filter theo date (mặc định hôm nay)
        try:
            target_date = date_type.fromisoformat(date) if date else date_type.today()
        except ValueError:
            target_date = date_type.today()

        from datetime import timedelta
        day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        conditions.append(models.RoomSession.session_start_timestamp >= day_start)
        conditions.append(models.RoomSession.session_start_timestamp < day_end)

        stmt = (
            select(models.RoomSession)
            .where(and_(*conditions))
            .order_by(models.RoomSession.session_start_timestamp)
        )
        result = await db.execute(stmt)
        sessions = result.scalars().all()

        now = datetime.now(timezone.utc)
        active_session = None
        classes_today = []

        for s in sessions:
            sess_dict = {
                "session_id": str(s.session_id),
                "class_code": s.class_code,
                "start": s.session_start_timestamp.isoformat() if s.session_start_timestamp else None,
                "end": s.session_end_timestamp.isoformat() if s.session_end_timestamp else None,
                "status": s.session_status,
                "is_exam": s.is_exam,
            }
            classes_today.append(sess_dict)
            # Session đang diễn ra
            if (
                s.session_status == "active"
                and s.session_start_timestamp
                and s.session_start_timestamp <= now
                and (s.session_end_timestamp is None or s.session_end_timestamp > now)
            ):
                active_session = sess_dict

        return {
            "room_id": room_id,
            "date": target_date.isoformat(),
            "classes_today": classes_today,
            "active_session": active_session,
        }


async def get_room_history(room_id: str, hours: int = 24) -> dict[str, Any]:
    """Lịch sử RoomState transitions của phòng trong N giờ gần nhất."""
    from datetime import timedelta

    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with async_session() as db:
        stmt = (
            select(models.RoomState)
            .where(
                and_(
                    models.RoomState.room_id == room_id,
                    models.RoomState.room_state_timestamp >= since,
                )
            )
            .order_by(models.RoomState.room_state_timestamp)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        transitions = [
            {
                "timestamp": r.room_state_timestamp.isoformat(),
                "mode": r.room_mode.value if r.room_mode else None,
                "status": r.room_status.value if r.room_status else None,
            }
            for r in rows
        ]

        return {
            "room_id": room_id,
            "hours": hours,
            "transitions": transitions,
            "current_state": transitions[-1] if transitions else None,
        }


async def get_attendance(
    room_id: str | None = None,
    session_id: str | None = None,
    class_code: str | None = None,
) -> dict[str, Any]:
    """Query attendance records theo phòng / session / lớp."""
    import uuid

    async with async_session() as db:
        conditions = []

        if session_id:
            try:
                conditions.append(models.AttendanceRecord.session_id == uuid.UUID(session_id))
            except ValueError:
                pass

        if class_code:
            # Join qua RoomSession để lọc class_code
            stmt = (
                select(models.AttendanceRecord)
                .join(models.RoomSession, models.AttendanceRecord.session_id == models.RoomSession.session_id)
                .where(models.RoomSession.class_code == class_code)
            )
            if room_id:
                stmt = stmt.where(models.RoomSession.room_id == room_id)
        else:
            if room_id:
                # Filter qua session của phòng
                subq = select(models.RoomSession.session_id).where(
                    models.RoomSession.room_id == room_id
                )
                conditions.append(models.AttendanceRecord.session_id.in_(subq))
            stmt = select(models.AttendanceRecord).where(and_(*conditions) if conditions else True)

        result = await db.execute(stmt)
        records = result.scalars().all()

        total = len(records)
        checked_in = sum(1 for r in records if getattr(r, "attendance_status", None) in ("present", "late"))

        return {
            "room_id": room_id,
            "session_id": session_id,
            "class_code": class_code,
            "enrolled_count": total,
            "checked_in_count": checked_in,
            "attendance_rate": round(checked_in / total, 2) if total > 0 else 0.0,
            "status": "ok",
        }


async def compare_rooms(room_ids: list[str], metric: str, window: str = "1h") -> dict[str, Any]:
    """So sánh 1 metric giữa nhiều phòng trong window gần nhất."""
    from datetime import timedelta

    hours = 1 if window == "1h" else (6 if window == "6h" else 0.25)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    comparisons = []
    for room_id in room_ids:
        rows = await get_environment(room_id, since)
        if rows:
            vals = [
                r.get("smoke_value") if metric == "smoke" else r.get(metric)
                for r in rows
                if (r.get("smoke_value") if metric == "smoke" else r.get(metric)) is not None
            ]
            if vals:
                latest = vals[-1]
                comparisons.append({
                    "room_id": room_id,
                    "value": latest,
                    "avg": round(sum(vals) / len(vals), 1),
                    "samples": len(vals),
                    "status": "ok",
                })
                continue
        comparisons.append({"room_id": room_id, "value": None, "status": "no_data"})

    return {
        "metric": metric,
        "window": window,
        "comparisons": comparisons,
    }
