from sqlalchemy import UUID, Column, Enum, Integer, String
from database import Base
from .__enum import UserRole

class User(Base):
    __tablename__ = "users"

    user_id = Column(UUID, primary_key=True, index=True)
    card_uid = Column(String, unique=True, index=True)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.UNKNOWN, index=True)
    username = Column(String, unique=True, index=True)
    full_name = Column(String)
    hashed_password = Column(String)
    is_active = Column(Integer, default=1)  # 1 for active, 0 for inactive
    
    