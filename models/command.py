from sqlalchemy import BIGINT, TIMESTAMP, UUID, Boolean, Column, Enum, String, ForeignKey, func
from database import Base


class CommandStatusEnum:
    """Not a DB enum — just constants for the status column."""
    PENDING = "pending"
    ACKED = "acked"
    FAILED = "failed"
    TIMEOUT = "timeout"


class Command(Base):
    __tablename__ = "command"

    command_id = Column(UUID, primary_key=True)
    device_id = Column(UUID, ForeignKey("device.device_id"), nullable=True, index=True)
    room_id = Column(UUID, ForeignKey("room.room_id"), nullable=True, index=True)
    command_type = Column(String, nullable=False)         # "mode", "door", "fan", "light", "buzzer", "ota", "restart"
    command_value = Column(String)                        # JSON-encoded value
    status = Column(String, nullable=False, default=CommandStatusEnum.PENDING, index=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    acked_at = Column(TIMESTAMP(timezone=True), nullable=True)
    error_message = Column(String, nullable=True)
    message_id = Column(String)                           # MQTT message_id for tracing
