from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from dotenv import load_dotenv
from sqlalchemy.orm import declarative_base
import os

load_dotenv()

database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL is required. Copy .env.example to .env and set its values.")

engine = create_async_engine(database_url, echo=False)
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

