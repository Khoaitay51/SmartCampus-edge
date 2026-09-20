import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Float, cast, func, select

import models
from database import async_session

logger = logging.getLogger("telemetry.summarize")

RawSummarizer = models.RawSummarizer

Env = models.telemetry.Environment

AVG_COLUMNS = (
    Env.temperature,
    Env.humidity,
    Env.smoke_value,
    Env.co2,
    Env.air_quality,
)


async def summarize(hours: int = 1, bucket_minutes: int = 5) -> list[dict]:
    """
    Tổng hợp telemetry theo phòng trong `hours` giờ gần nhất,
    gom nhóm theo bucket `bucket_minutes` phút.
    """
    hours = int(hours)
    bucket_minutes = int(bucket_minutes)

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    width = func.make_interval(0, 0, 0, 0, 0, bucket_minutes)
    bucket = func.time_bucket(width, Env.environment_timestamp)

    stmt = (
        select(
            bucket.label("bucket"),
            Env.room_id,
            func.count().label("samples"),
            func.max(Env.smoke_threshold).label("smoke_threshold"),
            *[
                cast(func.avg(col), Float).label(col.key)
                for col in AVG_COLUMNS
            ],
        )
        .where(Env.environment_timestamp >= since)
        .group_by(bucket, Env.room_id)
        .order_by(bucket.desc(), Env.room_id)
    )

    logger.debug(
        "Truy vấn telemetry: hours=%s bucket_minutes=%s since=%s",
        hours, bucket_minutes, since.isoformat(),
    )

    try:
        async with async_session() as db:
            result = await db.execute(stmt)
            rows = [dict(row) for row in result.mappings().all()]
    except Exception:
        logger.exception(
            "Lỗi khi truy vấn telemetry (hours=%s, bucket_minutes=%s)",
            hours, bucket_minutes,
        )
        raise

    if not rows:
        logger.warning(
            "Không có dữ liệu telemetry trong %s giờ gần nhất (bucket=%s phút).",
            hours, bucket_minutes,
        )
    else:
        logger.info(
            "Tổng hợp thành công: %d dòng (hours=%s, bucket=%s phút).",
            len(rows), hours, bucket_minutes,
        )
        for row in rows:
            logger.info(
                "%s | phòng %s | n=%d | %.1f°C %.0f%% | CO2 %.0f | "
                "smoke=%.0f (ngưỡng=%s) | AQI %.0f",
                row["bucket"].strftime("%Y-%m-%d %H:%M"),
                row["room_id"],
                row["samples"],
                row["temperature"] or 0,
                row["humidity"] or 0,
                row["co2"] or 0,
                row["smoke_value"] or 0,
                row["smoke_threshold"],
                row["air_quality"] or 0,
            )

    return rows


def format_summary_text(row: dict) -> str:
    """
    Ví dụ: "Phòng 101 lúc 14:05 có nhiệt độ 27.3°C, độ ẩm 61%,
    CO2 812ppm, chất lượng không khí 42, khói 3 (ngưỡng 50), dựa trên 12 mẫu."
    """
    return (
        f"Phòng {row['room_id']} lúc {row['bucket'].strftime('%Y-%m-%d %H:%M')} "
        f"có nhiệt độ {row['temperature'] or 0:.1f}°C, "
        f"độ ẩm {row['humidity'] or 0:.0f}%, "
        f"CO2 {row['co2'] or 0:.0f}ppm, "
        f"chất lượng không khí {row['air_quality'] or 0:.0f}, "
        f"khói {row['smoke_value'] or 0:.0f} (ngưỡng {row['smoke_threshold']}), "
        f"dựa trên {row['samples']} mẫu."
    )


def _json_default(value):
    """Xử lý các kiểu dữ liệu không tự serialize được sang JSON (datetime, UUID...)."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


async def save_summaries(rows: list[dict], name: str = "telemetry_summary") -> int:
    """
    Lưu từng dòng tổng hợp vào bảng raw_summarizer:
    - raw_data: JSON của toàn bộ số liệu gốc trong row
    - summary: câu mô tả dễ đọc, dùng cho hiển thị/log/AI đọc lại
    """
    if not rows:
        logger.info("Không có dòng nào để lưu vào raw_summarizer.")
        return 0

    records = [
        RawSummarizer(
            raw_summarizer_id=uuid.uuid4(),
            raw_summarizer_name=name,
            raw_data=json.dumps(row, default=_json_default, ensure_ascii=False),
            summary=format_summary_text(row),
        )
        for row in rows
    ]

    try:
        async with async_session() as db:
            db.add_all(records)
            await db.commit()
    except Exception:
        logger.exception("Lỗi khi lưu %d bản ghi vào raw_summarizer.", len(records))
        raise

    logger.info("Đã lưu %d bản ghi vào raw_summarizer (name=%s).", len(records), name)
    return len(records)


async def main():
    rows = await summarize(hours=1, bucket_minutes=5)
    if not rows:
        logger.info("Thử lại với khoảng thời gian rộng hơn: 6 giờ, bucket 30 phút.")
        rows = await summarize(hours=6, bucket_minutes=30)

    await save_summaries(rows)
    return rows


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    asyncio.run(main())