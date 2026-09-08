import asyncio
import logging
from contextlib import asynccontextmanager

from database import engine
import models
import models.telemetry
from sqlalchemy import text
from fastapi import FastAPI, HTTPException
from feature.mqtt import mqtt_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run the MQTT listener for the lifetime of the FastAPI application."""
    logger.info("Starting MQTT listener task...")
    task = asyncio.create_task(mqtt_worker.mqtt_listener())
    try:
        yield
    finally:
        logger.info("Stopping MQTT listener task...")
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(lifespan=lifespan, title="SmartCampus Edge API", version="0.1.0")


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
        async with mqtt_worker.create_mqtt_client():
            return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MQTT broker is unavailable") from exc
