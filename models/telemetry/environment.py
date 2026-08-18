from sqlalchemy import BIGINT, TIMESTAMP, Boolean, Column, Enum, Float, ForeignKey, Integer, String, UUID, func
from models.__enum import RoomModeEnum, SmokeState
from database import Base

class Environment(Base):
    __tablename__ = "environment"

    environment_id = Column(BIGINT, primary_key=True, index=True, autoincrement=True)
    room_id = Column(UUID, ForeignKey("room.room_id"), index=True)
    temperature = Column(Float, index=True)
    humidity = Column(Float, index=True)
    smoke_detected = Column(Boolean, nullable=False, default=False, index=True)
    smoke_value = Column(Float, index=True)
    smoke_threshold = Column(Float, index=True)
    smoke_state = Column(Enum(SmokeState), nullable=False, default=SmokeState.NORMAL, index=True)
    co2 = Column(Integer, index=True)
    air_quality = Column(Integer, index=True)
    room_mode = Column(Enum(RoomModeEnum), index=True)
    message_id = Column(String, index=True)
    source_timestamp = Column(TIMESTAMP(timezone=True), index=True)
    gateway_received_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, index=True)
    environment_timestamp = Column(TIMESTAMP(timezone=True), primary_key=True, server_default=func.now(), nullable=False, index=True)