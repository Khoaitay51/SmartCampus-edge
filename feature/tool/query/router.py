from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter

from .query_tool import (
    get_environment,
    get_raw_summaries,
    get_schedule,
    get_room_history,
    get_attendance,
    compare_rooms,
)

router = APIRouter(prefix="/api/tool/reasoning", tags=["reasoning_tool"])


@router.get("/environment")
async def get_environment_api(room_id: str, since: datetime, limit: int = 200):
    """Return raw environment telemetry for a room since a given timestamp."""
    rows = await get_environment(room_id, since, limit=limit)
    return {"rows": rows}


@router.get("/summaries")
async def get_summaries_api(limit: int = 50):
    """Return the most recent telemetry summary records."""
    rows = await get_raw_summaries(limit=limit)
    return rows


@router.get("/schedule")
async def get_schedule_api(room_id: str | None = None, date: str | None = None):
    """Return class schedule for a room or date (YYYY-MM-DD). Defaults to today."""
    return await get_schedule(room_id=room_id, date=date)


@router.get("/history/{room_id}")
async def get_room_history_api(room_id: str, hours: int = 24):
    """Return RoomState transition history for a room over the last N hours."""
    return await get_room_history(room_id=room_id, hours=hours)


@router.get("/attendance")
async def get_attendance_api(
    room_id: str | None = None,
    session_id: str | None = None,
    class_code: str | None = None,
):
    """Return attendance summary for a room / session / class."""
    return await get_attendance(room_id=room_id, session_id=session_id, class_code=class_code)


@router.post("/compare")
async def compare_rooms_api(body: dict):
    """Compare a metric across multiple rooms. Body: {room_ids, metric, window}."""
    room_ids: List[str] = body.get("room_ids", [])
    metric: str = body.get("metric", "temperature")
    window: str = body.get("window", "1h")
    return await compare_rooms(room_ids=room_ids, metric=metric, window=window)
