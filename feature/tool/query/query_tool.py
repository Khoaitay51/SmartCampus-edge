import logging
from datetime import datetime, timezone

from sqlalchemy import select

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
