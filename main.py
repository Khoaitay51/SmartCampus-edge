from database import AsyncSession, Base, engine, get_db
import models
import models.telemetry
from sqlalchemy import text
import os
from fastapi import FastAPI, Depends

app = FastAPI()


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
    
    