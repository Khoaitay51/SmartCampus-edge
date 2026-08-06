import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from dotenv import load_dotenv
from sqlalchemy.orm import declarative_base
import os

load_dotenv()

engine = create_async_engine(os.getenv("DATABASE_URL"), echo=True)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

Base = declarative_base()

async def get_db():
    async with async_session() as db:
        try:
            yield db
        except Exception:
            await db.rollback()
            raise
        finally:
            await db.close()


