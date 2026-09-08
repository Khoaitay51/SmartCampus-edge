import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
import aiomqtt as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiment.seed_data import SAMPLE_ROOM_ID

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USERNAME", "smartcampus")
MQTT_PASS = os.getenv("MQTT_PASSWORD", "123456")


async def send_environment(room_id=SAMPLE_ROOM_ID, temp=26.8, humidity=60.5, co2=480, air_q=92, smoke_state="NORMAL"):
    topic = f"smartcampus/v1/telemetry/room/{room_id}/environment"
    payload = {
        "message_id": str(uuid.uuid4()),
        "source_timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "room_id": str(room_id),
            "temperature": temp,
            "humidity": humidity,
            "co2": co2,
            "air_quality": air_q,
            "smoke_state": smoke_state,
        }
    }
    async with mqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT, username=MQTT_USER, password=MQTT_PASS) as client:
        await client.publish(topic, json.dumps(payload))
        print(f"[MQTT] Da gui telemetry moi truong toi: {topic}")
        print(f"   -> Temp: {temp}C, Hum: {humidity}%, CO2: {co2}, AQI: {air_q}, Smoke: {smoke_state}")


async def send_occupancy(room_id=SAMPLE_ROOM_ID, direction="IN"):
    topic = f"smartcampus/v1/telemetry/room/{room_id}/occupancy"
    payload = {
        "message_id": str(uuid.uuid4()),
        "source_timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "room_id": str(room_id),
            "occupancy_type": direction.upper(),
        }
    }
    async with mqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT, username=MQTT_USER, password=MQTT_PASS) as client:
        await client.publish(topic, json.dumps(payload))
        print(f"[MQTT] Da gui Occupancy ({direction}) toi: {topic}")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "env"
    
    if action == "env":
        asyncio.run(send_environment())
    elif action == "smoke":
        print("[!] Gui canh bao khoi EMERGENCY...")
        asyncio.run(send_environment(smoke_state="EMERGENCY"))
    elif action == "in":
        asyncio.run(send_occupancy(direction="IN"))
    elif action == "out":
        asyncio.run(send_occupancy(direction="OUT"))
    else:
        print("Cach dung:")
        print("  python publish_telemetry.py env     -> Gui do luong moi truong")
        print("  python publish_telemetry.py smoke   -> Gia lap phat hien khoi (EMERGENCY)")
        print("  python publish_telemetry.py in      -> Gia lap nguoi vao phong")
        print("  python publish_telemetry.py out     -> Gia lap nguoi ra khoi phong")
