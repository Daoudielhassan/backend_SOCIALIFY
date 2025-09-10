import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv

load_dotenv()

# Use centralized settings for database configuration
from config.settings import settings

# Use the centralized DATABASE_URL from settings
DATABASE_URL = settings.DATABASE_URL

engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Disable SQLAlchemy engine logs
    future=True,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True  # Verify connections before use
)

from sqlalchemy.ext.asyncio import async_sessionmaker

SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# Function for dependency injection
from typing import AsyncGenerator

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session"""
    async with SessionLocal() as session:
        yield session 