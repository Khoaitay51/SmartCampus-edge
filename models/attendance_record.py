from sqlalchemy import BIGINT, TIMESTAMP, UUID, Boolean, Column, ForeignKey, String, UniqueConstraint, func
from database import Base

class AttendanceRecord(Base):
    __table_args__ = (UniqueConstraint("session_id", "user_id", name="uq_attendance_session_user"),)
    __tablename__ = "attendance_records"

    attendance_record_id = Column(BIGINT, primary_key=True, index=True, autoincrement=True)
    card_uid = Column(String,ForeignKey("users.card_uid"), index=True)
    user_id = Column(UUID, ForeignKey("users.user_id"), index=True)
    room_id = Column(UUID, ForeignKey("room.room_id"), index=True)
    session_id = Column(UUID, ForeignKey("room_sessions.session_id"), index=True)
    attendance_timestamp = Column(TIMESTAMP(timezone=True), index=True, server_default=func.now(), nullable=False)
    late = Column(Boolean, nullable=False, default=False, index=True)