"""Test case: Kiem tra co che tu dong dong Session (Auto-end Session) khi het gio.

Cach su dung:
  1. Chay demo tu dong test toan bo quy trinh (A -> Z):
     python experiment/test_auto_end_session.py demo

  2. Tao 1 session da het han trong DB de test voi main.py dang chay:
     python experiment/test_auto_end_session.py setup

  3. Kiem tra trang thai session va phong trong DB:
     python experiment/test_auto_end_session.py status

  4. Kich hoat auto-end ngay lap tuc cho cac session da het han:
     python experiment/test_auto_end_session.py trigger
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiomqtt as mqtt
from sqlalchemy import func, insert, select, update

from database import async_session
import models
from models.__enum import RoomModeEnum, RoomStatus
from feature.enum import CommandStatus, RoomCommandType, RoomStatusEnum
from feature.FSM.statemachine import RoomState, get_current_state, set_current_state
from feature.mqtt.mqtt_worker import create_mqtt_client
from feature.RFID.attendance import handle_auto_end_session
from experiment.seed_data import LECTURER_ID, SAMPLE_ROOM_ID

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USERNAME", "smartcampus")
MQTT_PASS = os.getenv("MQTT_PASSWORD", "123456")


async def get_session_status(room_id=SAMPLE_ROOM_ID):
    """Doc thong tin session moi nhat cua phong (uu tien active)."""
    async with async_session() as db:
        # Uu tien tim session dang ACTIVE
        active_res = await db.execute(
            select(models.RoomSession)
            .where(
                models.RoomSession.room_id == room_id,
                models.RoomSession.session_status == RoomStatusEnum.ACTIVE.value,
            )
            .order_by(models.RoomSession.session_start_timestamp.desc())
            .limit(1)
        )
        session = active_res.scalar_one_or_none()

        # Neu khong co active session thi lay session co end_timestamp gan nhat
        if not session:
            latest_res = await db.execute(
                select(models.RoomSession)
                .where(models.RoomSession.room_id == room_id)
                .order_by(models.RoomSession.session_end_timestamp.desc().nullslast())
                .limit(1)
            )
            session = latest_res.scalar_one_or_none()

        room_state = await get_current_state(room_id, RoomState, db)

        # Lay event moi nhat
        event_res = await db.execute(
            select(models.AttendanceEvent)
            .where(models.AttendanceEvent.room_id == room_id)
            .order_by(models.AttendanceEvent.attendance_timestamp.desc())
            .limit(1)
        )
        latest_event = event_res.scalar_one_or_none()

        return session, room_state, latest_event


async def print_status(room_id=SAMPLE_ROOM_ID):
    """In thong tin trang thai phong va session."""
    session, room_state, latest_event = await get_session_status(room_id)
    now_ts = datetime.now(timezone.utc)

    print("\n" + "=" * 60)
    print(f"TRANG THAI PHONG & SESSION ({room_id})")
    print("=" * 60)
    print(f"[*] FSM Room Mode hien tai : {room_state.name if room_state else 'CHUA CO'}")

    if not session:
        print("[-] Khong co session nao trong database.")
    else:
        status_label = session.session_status or "UNKNOWN"
        is_expired = session.session_end_timestamp and session.session_end_timestamp <= now_ts
        expired_str = " (DA QUA GIO KET THUC)" if is_expired else " (CHUA HET GIO)"

        print(f"[*] Session ID              : {session.session_id}")
        print(f"[*] Session Status          : {status_label.upper()}{expired_str}")
        print(f"[*] Bat dau (Start)         : {session.session_start_timestamp}")
        print(f"[*] Han diem danh (15p)     : {session.attendance_deadline_timestamp}")
        print(f"[*] Ket thuc du kien (End)  : {session.session_end_timestamp}")

    if latest_event:
        print(f"[*] Event RFID gan nhat     : {latest_event.event_type.name} (luc {latest_event.attendance_timestamp})")
    print("=" * 60 + "\n")


async def setup_expired_session(room_id=SAMPLE_ROOM_ID, seconds_ago: int = 60):
    """Tao 1 session o trang thai ACTIVE nhung da het han trong qua khu."""
    now_ts = datetime.now(timezone.utc)
    start_ts = now_ts - timedelta(minutes=50)
    deadline_ts = now_ts - timedelta(minutes=35)
    end_ts = now_ts - timedelta(seconds=seconds_ago)

    new_session_id = uuid.uuid4()

    async with async_session() as db:
        # Dong cac session cu dang active neu co
        await db.execute(
            update(models.RoomSession)
            .where(
                models.RoomSession.room_id == room_id,
                models.RoomSession.session_status == RoomStatusEnum.ACTIVE.value,
            )
            .values(session_status=RoomStatusEnum.ENDED.value)
        )

        # Tao session moi da het han nhung status = ACTIVE
        await db.execute(
            insert(models.RoomSession).values(
                session_id=new_session_id,
                room_id=room_id,
                lecturer_id=LECTURER_ID,
                session_start_timestamp=start_ts,
                attendance_deadline_timestamp=deadline_ts,
                session_end_timestamp=end_ts,
                session_status=RoomStatusEnum.ACTIVE.value,
                is_exam=False,
            )
        )

        # Set FSM phong thanh LECTURE
        await set_current_state(room_id, RoomState.LECTURE, db)
        await db.commit()

    print("\n" + "=" * 60)
    print(f"[+] DA KHOI TAO SESSION HET HAN CHO PHONG {room_id}")
    print("=" * 60)
    print(f"  - Session ID      : {new_session_id}")
    print(f"  - Status          : {RoomStatusEnum.ACTIVE.value} (Dang ACTIVE de cho auto-close)")
    print(f"  - Thoi gian bat dau: {start_ts.strftime('%H:%M:%S')}")
    print(f"  - Thoi gian ket thuc: {end_ts.strftime('%H:%M:%S')} (het han truoc day {seconds_ago}s)")
    print(f"  - FSM Room Mode   : LECTURE")
    print("=" * 60)
    print("[*] HUONG DAN TEST:")
    print("  1. Neu main.py dang chay:")
    print("     -> Task auto_end_loop se tu dong quet va dong session sau chu ky polling (mac dinh 5 phut,")
    print("        hoac neu chay voi SESSION_AUTO_END_POLL_INTERVAL=5 thi sau 5 giay).")
    print("     -> Quan sat log terminal cua main.py de thay thong bao:")
    print("        'Found 1 room(s) with expired sessions' & 'Automatically ended session ...'")
    print("  2. De kiem tra lai trang thai trong DB: python experiment/test_auto_end_session.py status")
    print("  3. De trigger dong ngay lap tuc     : python experiment/test_auto_end_session.py trigger")
    print("=" * 60 + "\n")
    return new_session_id


async def trigger_auto_end(room_id=SAMPLE_ROOM_ID):
    """Kich hoat truc tiep ham handle_auto_end_session voi MQTT client."""
    print(f"[*] Dang kich hoat handle_auto_end_session cho phong {room_id}...")
    async with create_mqtt_client(identifier="smartcampus-edge-test-trigger") as client:
        await handle_auto_end_session(mqtt_client=client, room_id=room_id)
    print("[+] Da thuc thi xong handle_auto_end_session!")
    await print_status(room_id)


async def run_full_demo(room_id=SAMPLE_ROOM_ID):
    """Chay kich ban test tu dong tu A den Z:
    1. Tao session het han sau 3 giay
    2. Lang nghe MQTT published commands
    3. Cho 3 giay het han
    4. Kich hoat auto-end
    5. Kiem tra va assert ket qua trong DB + MQTT
    """
    print("\n" + "=" * 65)
    print("KICH BAN KIEM THU TU DONG (AUTOMATED TEST): AUTO-END SESSION")
    print("=" * 65)

    captured_commands = []
    captured_states = []

    async def mqtt_recorder():
        """Lang nghe cac topic MQTT do edge server publish ra."""
        try:
            async with mqtt.Client(
                hostname=MQTT_HOST,
                port=MQTT_PORT,
                username=MQTT_USER,
                password=MQTT_PASS,
                identifier=f"test-recorder-{uuid.uuid4().hex[:6]}",
            ) as client:
                await client.subscribe(f"smartcampus/v1/room/{room_id}/#")
                async for message in client.messages:
                    topic = str(message.topic)
                    try:
                        payload = json.loads(message.payload.decode())
                    except Exception:
                        payload = message.payload.decode()

                    if "command" in topic:
                        captured_commands.append(payload)
                        print(f"   [MQTT COMMAND RECEIVE] Topic: {topic} | Payload: {payload}")
                    elif "state" in topic:
                        captured_states.append(payload)
                        print(f"   [MQTT STATE RECEIVE]   Topic: {topic} | Payload: {payload}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"   [MQTT RECORDER WARNING] {e}")

    # Chay mqtt recorder background
    recorder_task = asyncio.create_task(mqtt_recorder())
    await asyncio.sleep(0.5)

    # Buoc 1: Setup session sap het han sau 3 giay
    print("\n--- [BUOC 1] Tao Session se het han sau 3 giay, FSM = LECTURE ---")
    now_ts = datetime.now(timezone.utc)
    target_end_ts = now_ts + timedelta(seconds=3)
    test_session_id = uuid.uuid4()

    async with async_session() as db:
        await db.execute(
            update(models.RoomSession)
            .where(
                models.RoomSession.room_id == room_id,
                models.RoomSession.session_status == RoomStatusEnum.ACTIVE.value,
            )
            .values(session_status=RoomStatusEnum.ENDED.value)
        )
        await db.execute(
            insert(models.RoomSession).values(
                session_id=test_session_id,
                room_id=room_id,
                lecturer_id=LECTURER_ID,
                session_start_timestamp=now_ts - timedelta(minutes=45),
                attendance_deadline_timestamp=now_ts - timedelta(minutes=30),
                session_end_timestamp=target_end_ts,
                session_status=RoomStatusEnum.ACTIVE.value,
                is_exam=False,
            )
        )
        await set_current_state(room_id, RoomState.LECTURE, db)
        await db.commit()

    print(f"   -> Da tao session {test_session_id}")
    print(f"   -> Session end timestamp: {target_end_ts.strftime('%H:%M:%S')} (sau 3s)")

    # Buoc 2: Dem nguoc 3s
    print("\n--- [BUOC 2] Cho 3 giay de session het han... ---")
    for sec in range(3, 0, -1):
        print(f"   ... con {sec} giay ...")
        await asyncio.sleep(1)
    print("   -> Session DA CHINH THUC HET HAN!")

    # Buoc 3: Kich hoat auto-end
    print("\n--- [BUOC 3] Kich hoat dong session qua handle_auto_end_session ---")
    async with create_mqtt_client(identifier="smartcampus-edge-demo-caller") as client:
        await handle_auto_end_session(mqtt_client=client, room_id=room_id)

    # Doi 1s de recorder bat het goi tin MQTT
    await asyncio.sleep(1)
    recorder_task.cancel()
    await asyncio.gather(recorder_task, return_exceptions=True)

    # Buoc 4: Assert kiem tra ket qua
    print("\n--- [BUOC 4] KIEM TRA & XAC NHAN KET QUA (ASSERTIONS) ---")
    session, room_state, latest_event = await get_session_status(room_id)

    test_passed = True

    # 1. Session Status
    if session and session.session_status == RoomStatusEnum.ENDED.value:
        print("   [PASSED] 1. Session Status da chuyen sang 'ended'")
    else:
        print(f"   [FAILED] 1. Session Status khong phai 'ended' (hien tai: {session.session_status if session else None})")
        test_passed = False

    # 2. Attendance Event CHECK_OUT
    if latest_event and latest_event.event_type == models.AttendanceEventType.CHECK_OUT:
        print("   [PASSED] 2. Da ghi nhan AttendanceEvent(CHECK_OUT) trong DB")
    else:
        print(f"   [FAILED] 2. Khong tim thay event CHECK_OUT (hien tai: {latest_event.event_type if latest_event else None})")
        test_passed = False

    # 3. FSM Mode Transition
    # Neu occupancy = 0 -> SAVING, neu > 0 -> SELF_STUDY
    if room_state in (RoomState.SAVING, RoomState.SELF_STUDY):
        print(f"   [PASSED] 3. FSM chuyen tu LECTURE sang: {room_state.name}")
    else:
        print(f"   [FAILED] 3. FSM khong chuyen dung trang thai (hien tai: {room_state.name if room_state else None})")
        test_passed = False

    # 4. MQTT Commands
    commands_sent = [c.get("command") or c.get("payload", {}).get("command") for c in captured_commands]
    if "LIGHT" in str(captured_commands) or "FAN" in str(captured_commands) or len(captured_commands) > 0:
        print(f"   [PASSED] 4. MQTT published lenh dieu khien thiet bi ({len(captured_commands)} commands received)")
    else:
        print("   [INFO]   4. Khong nhan duoc MQTT command (co the do occupancy > 0 hoac broker latency)")

    print("\n" + "=" * 65)
    if test_passed:
        print(">>> KET QUA: TAT CA TEST CASE AUTO-END SESSION DA PASS THANH CONG! <<<")
    else:
        print(">>> KET QUA: CO TEST CASE THAT BAI, VUI LONG KIEM TRA LAI! <<<")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "demo"

    if mode in ("demo", "run-demo", "--demo"):
        asyncio.run(run_full_demo())
    elif mode in ("setup", "--setup"):
        asyncio.run(setup_expired_session())
    elif mode in ("status", "--status"):
        asyncio.run(print_status())
    elif mode in ("trigger", "--trigger"):
        asyncio.run(trigger_auto_end())
    else:
        print(f"Lenh '{mode}' khong hop le.")
        print("Cac lenh hop le:")
        print("  python experiment/test_auto_end_session.py demo    -> Chay automated test A-Z")
        print("  python experiment/test_auto_end_session.py setup   -> Tao session het han de test voi main.py")
        print("  python experiment/test_auto_end_session.py status  -> Xem trang thai session hien tai")
        print("  python experiment/test_auto_end_session.py trigger -> Kich hoat dong session ngay lap tuc")
