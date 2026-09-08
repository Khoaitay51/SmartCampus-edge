from sqlalchemy import BIGINT, TIMESTAMP, UUID, Column, Enum, Integer, String, ForeignKey, func
from database import Base
from models.__enum import IRSignalType


class Occupancy(Base):
    __tablename__ = "occupancy"

    occupancy_id = Column(BIGINT, primary_key=True, autoincrement=True)
    room_id = Column(UUID(as_uuid=True), ForeignKey("room.room_id"), index=True)
    occupancy_type = Column(Enum(IRSignalType))
    occupancy_count = Column(Integer, default=0, nullable=False)
    message_id = Column(String)
    source_timestamp = Column(TIMESTAMP(timezone=True))
    gateway_received_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), default=func.now(), nullable=False)
    occupancy_timestamp = Column(TIMESTAMP(timezone=True), primary_key=True, server_default=func.now(), default=func.now(), nullable=False)
