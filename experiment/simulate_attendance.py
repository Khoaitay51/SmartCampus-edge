import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
import aiomqtt as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiment.seed_data import (
    SAMPLE_ROOM_ID,
    LECTURER_CARD,
    STUDENT_CARD_1,
    STUDENT_CARD_2,
    ADMIN_CARD,
)

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USERNAME", "smartcampus")
MQTT_PASS = os.getenv("MQTT_PASSWORD", "123456")


async def tap_card(card_uid: str, room_id=SAMPLE_ROOM_ID, event_type="check_in"):
    topic = f"smartcampus/v1/event/room/{room_id}/rfid"
    payload = {
        "message_id": str(uuid.uuid4()),
        "source_timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "room_id": str(room_id),
            "card_uid": card_uid,
            "event_type": event_type,
        }
    }
    async with mqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT, username=MQTT_USER, password=MQTT_PASS) as client:
        await client.publish(topic, json.dumps(payload))
        print(f"[RFID TAP] Da quet the [{card_uid}] tai phong {room_id}")


if __name__ == "__main__":
    who = sys.argv[1] if len(sys.argv) > 1 else "gv"
    
    if who == "gv":
        print("[*] Giang vien quet the mo session + FSM LECTURE + bat thiet bi...")
        asyncio.run(tap_card(LECTURER_CARD))
    elif who == "sv1":
        print("[*] Sinh vien 1 quet the diem danh...")
        asyncio.run(tap_card(STUDENT_CARD_1))
    elif who == "sv2":
        print("[*] Sinh vien 2 quet the diem danh...")
        asyncio.run(tap_card(STUDENT_CARD_2))
    elif who == "admin":
        print("[*] Quan tri vien quet the mo cua...")
        asyncio.run(tap_card(ADMIN_CARD))
    elif who == "unknown":
        print("[*] Quet the la chua dang ky (REJECT + coi bao)...")
        asyncio.run(tap_card("THE_LA_999999"))
    else:
        print("Cach dung:")
        print("  python simulate_attendance.py gv      -> Giang vien mo session")
        print("  python simulate_attendance.py sv1     -> Sinh vien 1 diem danh")
        print("  python simulate_attendance.py sv2     -> Sinh vien 2 diem danh")
        print("  python simulate_attendance.py admin   -> Admin quet the")
        print("  python simulate_attendance.py unknown -> Quet the la")
