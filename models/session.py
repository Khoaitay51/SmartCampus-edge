import uuid
from sqlalchemy import TIMESTAMP, UUID, Boolean, Column, ForeignKey, String, func
from database import Base


class RoomSession(Base):
    __tablename__ = "room_sessions"

    session_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    room_id = Column(UUID(as_uuid=True), ForeignKey("room.room_id"), nullable=False, index=True)
    lecturer_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), index=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.class_id"), index=True)
    class_code = Column(String, index=True)
    session_start_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, index=True)
    attendance_deadline_timestamp = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    session_end_timestamp = Column(TIMESTAMP(timezone=True), index=True)
    is_exam = Column(Boolean, nullable=False, default=False, index=True)
    session_status = Column(String, nullable=True, default="active", index=True)  # active, ended, canceled
