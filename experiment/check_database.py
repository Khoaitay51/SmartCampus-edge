import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import async_session
from sqlalchemy import select, func
import models
from experiment.seed_data import SAMPLE_ROOM_ID


async def inspect_db():
    print("\n=======================================================")
    print(f"KIEM TRA TRANG THAI DU LIEU PHONG ({SAMPLE_ROOM_ID})")
    print("=======================================================")

    async with async_session() as db:
        # 1. Trang thai phong hien tai (FSM)
        states = (await db.execute(
            select(models.RoomState)
            .where(models.RoomState.room_id == SAMPLE_ROOM_ID)
            .order_by(models.RoomState.room_state_timestamp.desc())
            .limit(5)
        )).scalars().all()
        print("\n--- [FSM] 5 Trang thai phong gan nhat ---")
        for s in states:
            print(f"   - Mode: {s.room_mode.name:<12} | Status: {s.room_status.name:<8} | Luc: {s.room_state_timestamp}")

        # 2. Session hien tai
        sessions = (await db.execute(
            select(models.RoomSession)
            .where(models.RoomSession.room_id == SAMPLE_ROOM_ID)
            .order_by(models.RoomSession.session_start_timestamp.desc())
            .limit(2)
        )).scalars().all()
        print("\n--- [SESSION] Cac buoi hoc (RoomSession) ---")
        for se in sessions:
            status_str = "DANG MO" if se.session_end_timestamp is None else f"DA DONG ({se.session_end_timestamp})"
            print(f"   - Session ID: {se.session_id}")
            print(f"     Lecturer:   {se.lecturer_id}")
            print(f"     Bat dau:    {se.session_start_timestamp}")
            print(f"     Han DD 15p: {se.attendance_deadline_timestamp}")
            print(f"     Ket thuc:   {status_str}")

        # 3. Ban ghi diem danh sinh vien (AttendanceRecord)
        records = (await db.execute(
            select(models.AttendanceRecord, models.User.full_name)
            .join(models.User, models.AttendanceRecord.user_id == models.User.user_id)
            .where(models.AttendanceRecord.room_id == SAMPLE_ROOM_ID)
            .order_by(models.AttendanceRecord.attendance_timestamp.desc())
            .limit(5)
        )).all()
        print("\n--- [ATTENDANCE] Danh sach diem danh sinh vien ---")
        for r, name in records:
            late_str = "DI MUON" if r.late else "DUNG GIO"
            print(f"   - {name:<20} | The: {r.card_uid:<12} | {late_str:<10} | Luc: {r.attendance_timestamp}")

        # 4. Lich su quet the (AttendanceEvent)
        events = (await db.execute(
            select(models.AttendanceEvent)
            .where(models.AttendanceEvent.room_id == SAMPLE_ROOM_ID)
            .order_by(models.AttendanceEvent.attendance_timestamp.desc())
            .limit(6)
        )).scalars().all()
        print("\n--- [EVENTS] 6 Su kien quet the gan nhat ---")
        for ev in events:
            print(f"   - Event: {ev.event_type.name:<10} | The: {str(ev.card_uid):<14} | Luc: {ev.attendance_timestamp}")

        # 5. Du lieu moi truong gan nhat
        envs = (await db.execute(
            select(models.Environment)
            .where(models.Environment.room_id == SAMPLE_ROOM_ID)
            .order_by(models.Environment.environment_timestamp.desc())
            .limit(2)
        )).scalars().all()
        print("\n--- [ENVIRONMENT] Du lieu cam bien moi nhat ---")
        for e in envs:
            print(f"   - Nhiet do: {e.temperature}C | Do am: {e.humidity}% | CO2: {e.co2} ppm | AQI: {e.air_quality} | Khoi: {e.smoke_state.name}")

        # 6. Du lieu so nguoi (Occupancy)
        occs = (await db.execute(
            select(models.Occupancy)
            .where(models.Occupancy.room_id == SAMPLE_ROOM_ID)
            .order_by(models.Occupancy.occupancy_timestamp.desc())
            .limit(5)
        )).scalars().all()
        print("\n--- [OCCUPANCY] Dem nguoi gan nhat ---")
        for o in occs:
            print(f"   - Huong: {o.occupancy_type.name} | So nguoi trong phong: {o.occupancy_count} | Luc: {o.occupancy_timestamp}")

    print("\n=======================================================\n")


if __name__ == "__main__":
    asyncio.run(inspect_db())
