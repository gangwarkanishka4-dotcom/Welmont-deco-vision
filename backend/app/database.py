from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """DateTime(timezone=True), made reliable on SQLite too.

    Real bug found live (2026-09-15): SQLite has no native timezone-aware
    datetime type, so even with DateTime(timezone=True) declared correctly,
    SQLite silently drops the tzinfo on write and hands back a naive
    datetime on read. Every write in this codebase is UTC in practice
    (datetime.now(timezone.utc), or SQLite's own func.now(), which is also
    UTC) — only the marker saying so was missing. That naive value then
    serializes to JSON without a trailing 'Z'/offset, and the frontend's
    `new Date(...)` reads a marker-less string as *local browser time*
    instead of UTC — confirmed against a real alert whose displayed time was
    off by exactly the IST/UTC gap (5.5 hours). Postgres (production)
    doesn't have this problem — asyncpg preserves tzinfo correctly — so this
    is a no-op there; it only matters for the SQLite deployment this is
    actually running on right now. Use this in place of DateTime(timezone=True)
    on every model column."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
