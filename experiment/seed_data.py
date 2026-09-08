import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import async_session
from sqlalchemy import select, insert
import models
from models.__enum import RoomType, UserRole

# Fixed UUIDs for predictable testing
SAMPLE_ROOM_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
LECTURER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
STUDENT_ID_1 = uuid.UUID("33333333-3333-3333-3333-333333333333")
STUDENT_ID_2 = uuid.UUID("44444444-4444-4444-4444-444444444444")
ADMIN_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")

LECTURER_CARD = "CARD_GV_01"
STUDENT_CARD_1 = "CARD_SV_01"
STUDENT_CARD_2 = "CARD_SV_02"
ADMIN_CARD = "CARD_ADMIN"


async def seed():
    print("=== SEEDING SAMPLE DATA ===")
    async with async_session() as db:
        # 1. Create Room if not exists
        room = (await db.execute(select(models.Room).where(models.Room.room_id == SAMPLE_ROOM_ID))).scalar_one_or_none()
        if not room:
            await db.execute(
                insert(models.Room).values(
                    room_id=SAMPLE_ROOM_ID,
                    room_name="Phong Hoc Thong Minh 402",
                    room_type=RoomType.CLASSROOM,
                )
            )
            print(f"[+] Da tao phong: Phong 402 ({SAMPLE_ROOM_ID})")
        else:
            print(f"[-] Phong 402 da ton tai: {SAMPLE_ROOM_ID}")

        # 2. Insert Users
        users = [
            (LECTURER_ID, LECTURER_CARD, UserRole.LECTURER, "gv_nguyenvana", "TS. Nguyen Van A"),
            (STUDENT_ID_1, STUDENT_CARD_1, UserRole.STUDENT, "sv_tranthib", "Tran Thi B (SV 1)"),
            (STUDENT_ID_2, STUDENT_CARD_2, UserRole.STUDENT, "sv_lequangc", "Le Quang C (SV 2)"),
            (ADMIN_ID, ADMIN_CARD, UserRole.ADMIN, "admin_quantri", "Quan Tri Vien"),
        ]

        for u_id, card, role, uname, fullname in users:
            existing = (await db.execute(select(models.User).where(models.User.card_uid == card))).scalar_one_or_none()
            if not existing:
                await db.execute(
                    insert(models.User).values(
                        user_id=u_id,
                        card_uid=card,
                        role=role,
                        username=uname,
                        full_name=fullname,
                    )
                )
                print(f"[+] Da tao User: {fullname} | Role: {role.name} | Card: {card}")
            else:
                print(f"[-] User {fullname} ({card}) da ton tai.")

        await db.commit()
    print("=== HOAN TAT SEED DU LIEU ===")


if __name__ == "__main__":
    asyncio.run(seed())
