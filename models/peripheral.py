from sqlalchemy import Column, String, ForeignKey, UUID
from database import Base

class Peripheral(Base):
    __tablename__ = "peripheral"

    peripheral_id = Column(UUID, primary_key=True, nullable=False)
    peripheral_name = Column(String, nullable=False)

class PeripheralAction(Base):
    __tablename__ = "peripheral_action"

    peripheral_action_id = Column(UUID, primary_key=True, nullable=False)
    peripheral_id = Column(UUID, ForeignKey("peripheral.peripheral_id"), nullable=False)
    peripheral_action_name = Column(String, nullable=False)