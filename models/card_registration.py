import uuid
from sqlalchemy import Column, Enum, ForeignKey, String, TIMESTAMP, UUID, func
from database import Base
from .__enum import CardRegistrationStatus


class CardRegistrationRequest(Base):
    """
    Model lưu trữ các yêu cầu đăng ký thẻ RFID mới (quét tại node Hành lang).
    Khi thẻ chưa có trong bảng `users`, hệ thống sẽ lưu ở trạng thái PENDING để
    người quản trị (Admin) kiểm duyệt và gán cho User (Sinh viên/Giảng viên).
    """
    __tablename__ = "card_registration_requests"

    request_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_uid = Column(String, nullable=False, index=True)
    device_id = Column(UUID(as_uuid=True), ForeignKey("device.device_id"), nullable=True, index=True)
    room_id = Column(UUID(as_uuid=True), ForeignKey("room.room_id"), nullable=True, index=True)
    mac_address = Column(String, index=True)
    status = Column(Enum(CardRegistrationStatus), nullable=False, default=CardRegistrationStatus.PENDING, index=True)
    assigned_user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True, index=True)
    note = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now(), nullable=True)
    processed_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
