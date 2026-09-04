from sqlalchemy import BIGINT, Column, Enum, TIMESTAMP, String, ForeignKey, UUID, func
from database import Base
from .__enum import RoomType, RoomStatus, RoomModeEnum, DoorStateEnum, SmokeState


class EmergencyStateSource(Base):
    __tablename__ = "emergency_state_source"

    emergency_state_source_id = Column(BIGINT, primary_key=True, nullable=False, autoincrement=True)
    emergency_state_source_name = Column(String, nullable=False)


class Room(Base):
    __tablename__ = "room"

    room_id = Column(UUID, primary_key=True, nullable=False)
    room_name = Column(String, nullable=False)
    room_type = Column(Enum(RoomType), nullable=False)


class RoomState(Base):
    __tablename__ = "room_state"

    room_state_id = Column(BIGINT, primary_key=True, nullable=False, autoincrement=True)
    room_state_timestamp = Column(TIMESTAMP(timezone=True), primary_key=True, server_default=func.now(), nullable=False)
    room_id = Column(UUID, ForeignKey("room.room_id"), nullable=False, index=True)
    room_mode = Column(Enum(RoomModeEnum), nullable=False, index=True)
    room_emergency_state_source_id = Column(BIGINT, ForeignKey("emergency_state_source.emergency_state_source_id"), nullable=True)
    room_status = Column(Enum(RoomStatus), nullable=False)


class RoomEvent(Base):
    __tablename__ = "room_event"

    room_event_id = Column(BIGINT, primary_key=True, nullable=False, autoincrement=True)
    room_event_timestamp = Column(TIMESTAMP(timezone=True), primary_key=True, server_default=func.now(), nullable=False)
    room_id = Column(UUID, ForeignKey("room.room_id"), nullable=False, index=True)
    room_mode = Column(Enum(RoomModeEnum), nullable=False)
    peripheral_action_id = Column(UUID, ForeignKey("peripheral_action.peripheral_action_id"), nullable=False)


class RoomDoorState(Base):
    __tablename__ = "room_door_state"

    room_door_state_id = Column(BIGINT, primary_key=True, nullable=False, autoincrement=True)
    room_door_state_timestamp = Column(TIMESTAMP(timezone=True), primary_key=True, server_default=func.now(), nullable=False)
    room_id = Column(UUID, ForeignKey("room.room_id"), nullable=False, index=True)
    door_state = Column(Enum(DoorStateEnum), nullable=False)


class RoomSmokeState(Base):
    __tablename__ = "room_smoke_state"

    room_smoke_state_id = Column(BIGINT, primary_key=True, nullable=False, autoincrement=True)
    room_smoke_state_timestamp = Column(TIMESTAMP(timezone=True), primary_key=True, server_default=func.now(), nullable=False)
    room_id = Column(UUID, ForeignKey("room.room_id"), nullable=False, index=True)
    smoke_state = Column(Enum(SmokeState), nullable=False)
