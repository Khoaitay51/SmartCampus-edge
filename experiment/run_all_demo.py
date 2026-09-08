import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiment.seed_data import seed
from experiment.publish_telemetry import send_environment, send_occupancy
from experiment.simulate_attendance import tap_card, LECTURER_CARD, STUDENT_CARD_1, STUDENT_CARD_2, ADMIN_CARD
from experiment.check_database import inspect_db


async def main():
    print("===============================================================")
    print("BAT DAU CHAY TOAN BO KICH BAN DEMO SMART CAMPUS EDGE")
    print("===============================================================\n")

    # Buoc 1: Seed du lieu
    print("--- [BUOC 1] Khoi tao phong hoc va nguoi dung mau ---")
    await seed()
    await asyncio.sleep(1)

    # Buoc 2: Gui Telemetry Moi Truong
    print("\n--- [BUOC 2] ESP32 gui cam bien moi truong (Nhiet do, Do am, CO2, AQI) ---")
    await send_environment(temp=25.4, humidity=58.0, co2=450, air_q=95)
    await asyncio.sleep(1)

    # Buoc 3: Giang vien quet the lan 1 de mo lop hoc (Check-in)
    print("\n--- [BUOC 3] Giang vien quet the lan 1 (Check-in) bat dau buoi hoc ---")
    print("   -> He thong: Tao RoomSession, chuyen FSM sang LECTURE, bat Den/Quat/Coi")
    await tap_card(LECTURER_CARD)
    await asyncio.sleep(2)

    # Buoc 4: 2 nguoi di qua cam bien IR vao phong (Occupancy = 2)
    print("\n--- [BUOC 4] Cam bien IR phat hien 2 nguoi vao phong (Occupancy = 2) ---")
    await send_occupancy(direction="IN")
    await asyncio.sleep(1)
    await send_occupancy(direction="IN")
    await asyncio.sleep(2)

    # Buoc 5: Sinh vien 1 quet the diem danh
    print("\n--- [BUOC 5] Sinh vien 1 quet the diem danh (Attendance = 1, Diff = 1) ---")
    await tap_card(STUDENT_CARD_1)
    await asyncio.sleep(2)

    # Buoc 6: Sinh vien 2 quet the diem danh
    print("\n--- [BUOC 6] Sinh vien 2 quet the diem danh (Attendance = 2, Diff = 0) ---")
    await tap_card(STUDENT_CARD_2)
    await asyncio.sleep(2)

    # Buoc 7: Nguoi thu 3 vao phong khong quet the (Occupancy = 3, Attendance = 2, Diff = 1)
    print("\n--- [BUOC 7] Nguoi thu 3 vao phong nhung khong quet the (Occupancy = 3, Diff = 1) ---")
    await send_occupancy(direction="IN")
    await asyncio.sleep(2)

    # Buoc 8: The la chua dang ky quet the vao
    print("\n--- [BUOC 8] The la chua dang ky quet the vao phong (REJECT + Coi bao) ---")
    await tap_card("UNKNOWN_CARD_999")
    await asyncio.sleep(2)

    # Buoc 9: Giang vien quet the lan 2 ket thuc buoi hoc (Check-out)
    print("\n--- [BUOC 9] Giang vien quet the lan 2 (Check-out) ket thuc buoi hoc ---")
    print("   -> He thong: Dong RoomSession (luu session_end_timestamp), FSM sang SAVING, tat Den/Quat")
    await tap_card(LECTURER_CARD)
    await asyncio.sleep(2)

    # Buoc 10: Kiem tra co so du lieu
    print("\n--- [BUOC 10] Truy van co so du lieu TimescaleDB kiem tra ket qua toan dien ---")
    await inspect_db()

    print("DEMO HOAN TAT THANH CONG!")


if __name__ == "__main__":
    asyncio.run(main())
