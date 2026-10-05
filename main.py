import asyncio
import logging
from contextlib import asynccontextmanager

from database import engine, async_session
import models
import models.telemetry
from sqlalchemy import text
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from feature.mqtt import mqtt_worker
from feature.RFID.attendance import auto_end_loop
from feature.summary import save_summaries, summarize
import feature.tool.query.router as tool_router
import feature.command.router as command_router
import feature.RFID.sync_router as card_sync_router





SUMMARY_INTERVAL_SECONDS = 60*60


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


async def summary_loop():
    logger.info("Starting summary loop")
    while True:
        try:
            rows = await summarize(hours=1, bucket_minutes=5)
            await save_summaries(rows)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Lỗi 1 lần chạy không nên giết chết cả vòng lặp — log rồi thử lại ở chu kỳ sau.
            logger.exception("Lỗi khi chạy summary định kỳ, sẽ thử lại sau %ss.", SUMMARY_INTERVAL_SECONDS)
 
        await asyncio.sleep(SUMMARY_INTERVAL_SECONDS)
    


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run the MQTT listener and background tasks for the lifetime of the FastAPI application."""
    logger.info("Starting MQTT listener task...")
    mqtt_task = asyncio.create_task(mqtt_worker.mqtt_listener())
    summary_task = asyncio.create_task(summary_loop())

    logger.info("Starting session auto-end polling task...")
    session_task = asyncio.create_task(
        auto_end_loop(lambda: mqtt_worker.create_mqtt_client(identifier="smartcampus-edge-autoend"))
    )
    try:
        yield
    finally:
        logger.info("Stopping background tasks (MQTT listener & session auto-end)...")
        mqtt_task.cancel()
        summary_task.cancel()
        session_task.cancel()
        await asyncio.gather(mqtt_task, summary_task, session_task, return_exceptions=True)
        logger.info("All background tasks stopped.")


app = FastAPI(lifespan=lifespan, title="SmartCampus Edge API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router=tool_router.router)
app.include_router(command_router.router)
app.include_router(card_sync_router.router)

@app.get("/health", tags=["system"])
async def health_check():
    """Check that the API can reach PostgreSQL/TimescaleDB."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    return {"status": "ok"}


@app.get("/")
async def read_root():
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT hypertable_name FROM timescaledb_information.hypertables")
        )

        hypertables = [row[0] for row in result.fetchall()]

    return {
        "message": "Welcome to the SmartCampus Edge API!",
        "hypertable": hypertables,
    }


@app.get("/mqtt_check", tags=["system"])
async def mqtt_check():
    try:
        async with mqtt_worker.create_mqtt_client(identifier="smartcampus-edge-healthcheck"):
            return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MQTT broker is unavailable") from exc
