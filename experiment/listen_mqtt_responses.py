import asyncio
import json
import os
import sys
from pathlib import Path
import aiomqtt as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USERNAME", "smartcampus")
MQTT_PASS = os.getenv("MQTT_PASSWORD", "123456")

TOPIC_SUB = "smartcampus/v1/#"


async def listen():
    print("=======================================================")
    print(f"DANG LANG NGHE REALTIME PHAN HOI TU BACKEND ({TOPIC_SUB})...")
    print("   (Mo terminal khac de quet the hoac ban telemetry)")
    print("=======================================================\n")

    async with mqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT, username=MQTT_USER, password=MQTT_PASS) as client:
        await client.subscribe(TOPIC_SUB)
        async for message in client.messages:
            topic = str(message.topic)
            try:
                payload = json.loads(message.payload.decode())
            except Exception:
                payload = message.payload.decode()

            if "command" in topic:
                print(f"[COMMAND PHAT RA TU BACKEND] -> Topic: {topic}")
                print(f"   Payload: {json.dumps(payload, indent=2)}\n")
            elif "state" in topic:
                print(f"[TRANG THAI PHONG DOI (FSM)] -> Topic: {topic}")
                print(f"   Payload: {json.dumps(payload, indent=2)}\n")
            elif "event" in topic or "telemetry" in topic:
                print(f"[DATA SENSOR/RFID VAO] -> Topic: {topic}")
                print(f"   Payload: {json.dumps(payload, indent=2)}\n")
            else:
                print(f"[DATA KHONG XAC DINH] -> Topic: {topic}")
                print(f"   Payload: {json.dumps(payload, indent=2)}\n")


if __name__ == "__main__":
    try:
        asyncio.run(listen())
    except KeyboardInterrupt:
        print("\nDa dung lang nghe.")
