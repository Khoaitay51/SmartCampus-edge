from sqlalchemy import BIGINT, UUID, Column, Enum, String, ForeignKey, TIMESTAMP, func
from database import Base
from models.__enum import AttendanceEventType


class AttendanceStatus(Base):
    __tablename__ = "attendance_statuses"

    attendance_status_id = Column(String, primary_key=True)
    status_name = Column(String)
    description = Column(String)


class AttendanceEvent(Base):
    __tablename__ = "attendance_events"

    attendance_event_id = Column(BIGINT, primary_key=True, autoincrement=True)
    room_id = Column(UUID, ForeignKey("room.room_id"), index=True)
    user_id = Column(UUID, ForeignKey("users.user_id"), nullable=True, index=True)
    card_uid = Column(String, index=True)
    event_type = Column(Enum(AttendanceEventType), index=True)
    attendance_timestamp = Column(TIMESTAMP(timezone=True), primary_key=True, server_default=func.now(), nullable=False)
    attendance_status_id = Column(String, ForeignKey("attendance_statuses.attendance_status_id"))
    message_id = Column(String)
    source_timestamp = Column(TIMESTAMP(timezone=True))
    gateway_received_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
