from database import AsyncSession, Base, engine, get_db
import models
import models.telemetry
from sqlalchemy import text
import os
from fastapi import FastAPI, Depends

app = FastAPI()

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))
        await conn.run_sync(Base.metadata.create_all)
        
        # Create hypertables for timeseries telemetry
        await conn.execute(text("SELECT create_hypertable('attendance_events', 'attendance_timestamp', if_not_exists => true);"))
        await conn.execute(text("SELECT create_hypertable('environment', 'environment_timestamp', if_not_exists => true);"))
        await conn.execute(text("SELECT create_hypertable('occupancy', 'occupancy_timestamp', if_not_exists => true);"))
        await conn.execute(text("SELECT create_hypertable('device_heartbeat', 'heartbeat_timestamp', if_not_exists => true);"))
        await conn.execute(text("SELECT create_hypertable('room_state', 'room_state_timestamp', if_not_exists => true);"))
        await conn.execute(text("SELECT create_hypertable('room_event', 'room_event_timestamp', if_not_exists => true);"))

@app.get("/")
async def read_root():
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT hypertable_name FROM timescaledb_information.hypertables")
        )

        hypertables = [row[0] for row in result.fetchall()]

    return {
        "message": "Welcome to the SmartCampus Edge API!\n",
        "hypertables": hypertables,
    }
    
    