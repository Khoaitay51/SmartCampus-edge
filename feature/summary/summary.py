import asyncio
import models
from database import async_session
from sqlalchemy import select, func, text


async def summarize(hours: int = 1):
    """
    Summarize the telemetry data per room for the past `hours`.
    """
    Env = models.telemetry.Environment

    bucket = func.time_bucket(text(f"INTERVAL '{hours} hour'"), Env.environment_timestamp)
    time_limit = text(f"NOW() - INTERVAL '{hours} hour'")

    columns_to_avg = [
        Env.temperature,
        Env.humidity,
        Env.smoke_value,
        Env.smoke_threshold,
        Env.co2,
        Env.air_quality,
    ]

    stmt = (
        select(
            bucket.label("bucket"),
            Env.room_id,
            *[func.avg(col).label(col.name) for col in columns_to_avg]
        )
        .where(Env.environment_timestamp >= time_limit)
        .group_by(bucket, Env.room_id)
        .order_by(bucket.desc(), Env.room_id)
    )

    async with async_session() as db:
        result = await db.execute(stmt)
        rows = result.all()
        if not rows:
            print(f"Không có dữ liệu telemetry nào trong {hours} giờ gần nhất.")
        else:
            print(f"Đã tìm thấy {len(rows)} bản ghi tổng hợp ({hours} giờ qua):")
            for row in rows:
                print("Summary row:", row)
        return rows


async def summarize_1hour():
    return await summarize(hours=1)


if __name__ == "__main__":
    # Thử chạy mặc định 1 giờ, nếu không có dữ liệu thì thử 6 giờ gần nhất để kiểm tra
    async def main():
        rows = await summarize(hours=1)
        if not rows:
            print("--- Thử truy vấn 6 giờ gần nhất để kiểm tra dữ liệu cũ: ---")
            await summarize(hours=6)

    asyncio.run(main())
