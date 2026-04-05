from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,       # True — logs all SQL queries to the console during development
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,        # checks the connection before using it
    pool_recycle=3600,         # recycles the connection every hour
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,    # objects remain available after commit
)

@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for getting a database session"""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def close_db() -> None:
    """Close all connections — call when stopping the bot."""
    await engine.dispose()