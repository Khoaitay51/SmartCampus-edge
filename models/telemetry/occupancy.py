from sqlalchemy import BIGINT, TIMESTAMP, UUID, Column, Enum, Integer, String, ForeignKey, func
from database import Base
from models.__enum import IRSignalType

class Occupancy(Base):
    __tablename__ = "occupancy"

    occupancy_id = Column(BIGINT, primary_key=True, index=True, autoincrement=True)
    room_id = Column(UUID, ForeignKey("room.room_id"), index=True)
    occupancy_type = Column(Enum(IRSignalType), index=True)
    occupancy_count = Column(Integer, index=True)
    message_id = Column(String, unique=True, index=True)
    source_timestamp = Column(TIMESTAMP(timezone=True), index=True)
    gateway_received_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, index=True)
    occupancy_timestamp = Column(TIMESTAMP(timezone=True), index=True)
    