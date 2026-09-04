from sqlalchemy import BIGINT, Boolean, TIMESTAMP, UUID, Column, Enum, String, ForeignKey, func
from database import Base
from .__enum import DeviceStatusEnum


class Device(Base):
    __tablename__ = "device"

    device_id = Column(UUID, primary_key=True)
    mac_address = Column(String, unique=True, index=True)
    device_name = Column(String)
    device_firmware_version = Column(String)
    room_id = Column(UUID, ForeignKey("room.room_id"), index=True)  # removed unique=True
    device_status = Column(Enum(DeviceStatusEnum), nullable=False, default=DeviceStatusEnum.offline, index=True)
    last_seen_timestamp = Column(TIMESTAMP(timezone=True))


class DeviceStatus(Base):
    __tablename__ = "device_status"

    device_id = Column(UUID, ForeignKey("device.device_id"), primary_key=True)
    device_status = Column(Enum(DeviceStatusEnum), nullable=False, index=True)
    status_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    reason = Column(String)



class DeviceHeartbeat(Base):
    __tablename__ = "device_heartbeat"

    device_heartbeat_id = Column(BIGINT, primary_key=True, autoincrement=True)
    device_id = Column(UUID, ForeignKey("device.device_id"), nullable=False, index=True)
    alive = Column(Boolean, nullable=False, default=True)
    message_id = Column(String)
    source_timestamp = Column(TIMESTAMP(timezone=True))
    firmware_version = Column(String)
    uptime = Column(BIGINT)
    gateway_received_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    heartbeat_timestamp = Column(TIMESTAMP(timezone=True), primary_key=True, server_default=func.now(), nullable=False)
