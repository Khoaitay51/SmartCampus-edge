from sqlalchemy import BIGINT, TIMESTAMP, Boolean, Column, Enum, Float, ForeignKey, Integer, String, UUID, func
from models.__enum import RoomModeEnum, SmokeState
from database import Base


class Environment(Base):
    __tablename__ = "environment"

    environment_id = Column(BIGINT, primary_key=True, autoincrement=True)
    room_id = Column(UUID, ForeignKey("room.room_id"), index=True)
    temperature = Column(Float)
    humidity = Column(Float)
    smoke_detected = Column(Boolean, nullable=False, default=False)
    smoke_value = Column(Float)
    smoke_threshold = Column(Float)
    smoke_state = Column(Enum(SmokeState), nullable=False, default=SmokeState.NORMAL, index=True)
    co2 = Column(Integer)
    air_quality = Column(Integer)
    room_mode = Column(Enum(RoomModeEnum))
    message_id = Column(String)
    source_timestamp = Column(TIMESTAMP(timezone=True))
    gateway_received_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    environment_timestamp = Column(TIMESTAMP(timezone=True), primary_key=True, server_default=func.now(), nullable=False)
