"""SQLAlchemy 2 async engine and sessions (asyncpg)."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(url: str) -> AsyncEngine:
    # hide_parameters: a logged SQL error copies no bound value (I12).
    return create_async_engine(url, pool_pre_ping=True, hide_parameters=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
