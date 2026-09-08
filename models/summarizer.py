from database import Base
from sqlalchemy import Column, String, UUID, func

class RawSummarizer(Base):
    __tablename__ = "raw_summarizer"

    raw_summarizer_id = Column(UUID, primary_key=True, nullable=False)
    raw_summarizer_timestamp = Column(String, primary_key=True, nullable=False, server_default=func.now())
    raw_summarizer_name = Column(String, nullable=False)