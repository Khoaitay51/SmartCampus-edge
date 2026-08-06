from sqlalchemy import BIGINT, UUID, Column, Enum, String, ForeignKey, TIMESTAMP, func
from database import Base
from models.__enum import AttendanceEventType

class AttendanceStatus(Base):
    __tablename__ = "attendance_statuses"

    attendance_status_id = Column(String, primary_key=True, index=True)
    status_name = Column(String, index=True)
    description = Column(String, index=True)

class AttendanceEvent(Base):
    __tablename__ = "attendance_events"

    attendance_event_id = Column(BIGINT, primary_key=True, index=True, autoincrement=True)
    room_id = Column(UUID, ForeignKey("room.room_id"), index=True)
    user_id = Column(UUID, ForeignKey("users.user_id"), index=True)
    card_uid = Column(String, ForeignKey("users.card_uid"), index=True)
    event_type = Column(Enum(AttendanceEventType), index=True)
    attendance_timestamp = Column(TIMESTAMP(timezone=True),server_default=func.now(), nullable = False, index=True)
    attendance_status_id = Column(String, ForeignKey("attendance_statuses.attendance_status_id"))
    message_id = Column(String, unique=True, index=True)
    source_timestamp = Column(TIMESTAMP(timezone=True), index=True)
    gateway_received_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, index=True)
    