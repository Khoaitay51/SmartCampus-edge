from sqlalchemy import BIGINT, TIMESTAMP, UUID, Boolean, Column, ForeignKey, String, UniqueConstraint, func
from database import Base

class CourseClass(Base):
    __tablename__ = "classes"

    class_id = Column(UUID, primary_key=True, index=True)
    class_code = Column(String, unique=True, nullable=False, index=True)
    class_name = Column(String, index=True)
    lecturer_id = Column(UUID, ForeignKey("users.user_id"), index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    class_created_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, index=True)

class ClassEnrollment(Base):
    __table_args__ = (UniqueConstraint("class_id", "student_id", name="uq_class_enrollment_student"),)
    __tablename__ = "class_enrollments"

    enrollment_id = Column(BIGINT, primary_key=True, index=True, autoincrement=True)
    class_id = Column(UUID, ForeignKey("classes.class_id"), nullable=False, index=True)
    student_id = Column(UUID, ForeignKey("users.user_id"), nullable=False, index=True)
    enrollment_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
