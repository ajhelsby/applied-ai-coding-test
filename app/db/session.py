import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

_database_url = os.getenv("DATABASE_URL")
if not _database_url:
    raise RuntimeError("DATABASE_URL environment variable is required")

if os.getenv("INTEGRATION_TEST") == "1":
    engine = create_async_engine(_database_url, poolclass=NullPool)
else:
    engine = create_async_engine(_database_url, pool_pre_ping=True)
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionFactory() as session:
        yield session


async def close_database_connections() -> None:
    await engine.dispose()
