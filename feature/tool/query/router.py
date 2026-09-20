from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import UUID

from .query_tool import get_environment, get_raw_summaries

router = APIRouter(prefix="/tool/reasoning", tags=["reasoning_tool"])


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

