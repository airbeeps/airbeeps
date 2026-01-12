from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,  # Keep 10 connections ready
    max_overflow=20,  # Allow up to 30 total connections under load
    pool_pre_ping=True,  # Check connection health before use
    pool_recycle=3600,  # Recycle connections after 1 hour
    echo=False,  # Set to True for SQL debugging
)

async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_maker() as session:
        yield session


@asynccontextmanager
async def get_async_session_context() -> AsyncGenerator[AsyncSession]:
    """
    Context manager for async sessions.

    Use this when you need a session outside of FastAPI dependency injection,
    e.g., in background workers or scheduled tasks.
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
