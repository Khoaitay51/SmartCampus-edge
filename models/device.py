from sqlalchemy import BIGINT, TIMESTAMP, UUID, Column, Enum, String, ForeignKey, func
from database import Base
from .__enum import DeviceStatusEnum
class Device(Base):
    __tablename__ = "device"

    device_id = Column(UUID, primary_key=True, index=True)
    mac_address = Column(String, unique=True, index=True)
    device_name = Column(String, index=True)
    device_firmware_version = Column(String, index=True)
    room_id = Column(UUID, ForeignKey("room.room_id"), unique=True, index=True)
    device_status = Column(Enum(DeviceStatusEnum), nullable=False, default=DeviceStatusEnum.offline, index=True)
    last_seen_timestamp = Column(TIMESTAMP(timezone=True), index=True)
    
class DeviceStatus(Base):
    __tablename__ = "device_status"

    device_id = Column(UUID, ForeignKey("device.device_id"), primary_key=True, index=True)
    device_status = Column(Enum(DeviceStatusEnum), nullable=False, index=True)
    status_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, index=True)
    reason = Column(String)

class DeviceHeartbeat(Base):
    __tablename__ = "device_heartbeat"

    device_heartbeat_id = Column(BIGINT, primary_key=True, index=True, autoincrement=True)
    device_id = Column(UUID, ForeignKey("device.device_id"), nullable=False, index=True)
    message_id = Column(String, unique=True, index=True)
    source_timestamp = Column(TIMESTAMP(timezone=True), index=True)
    gateway_received_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, index=True)
    heartbeat_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, index=True)