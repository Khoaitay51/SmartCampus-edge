from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from sqlalchemy import UUID

from .query_tool import get_environment, get_raw_summaries, get_schedule, get_room_history

router = APIRouter(prefix="/api/tool/reasoning", tags=["reasoning_tool"])


@router.get("/environment")
async def get_environment_api(room_id: str, since: datetime):
    """Return raw environment telemetry for a room since a given timestamp."""
    rows = await get_environment(room_id, since)
    return rows


@router.get("/summaries")
async def get_summaries_api(limit: int = 50):
    """Return the most recent telemetry summary records."""
    rows = await get_raw_summaries(limit=limit)
    return rows


# ── Additional endpoints called by AI Agent RAG tools ──────────────────────

@router.get("/schedule")
async def get_schedule_api(room_id: Optional[str] = None, date: Optional[str] = None):
    """Return current/upcoming class session (schedule) for a room."""
    return await get_schedule(room_id=room_id, date=date)


@router.get("/history/{room_id}")
async def get_room_history_api(room_id: str, hours: int = 24):
    """Return room state transition history for the last N hours."""
    return await get_room_history(room_id=room_id, hours=hours)
