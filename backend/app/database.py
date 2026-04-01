from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base

engine = create_async_engine(settings.database_url, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # SQLite: add review_status on DBs created before this column existed
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "ALTER TABLE clip_candidates ADD COLUMN review_status VARCHAR(16) DEFAULT 'pending'"
                )
            )
    except Exception:
        pass
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE clip_candidates SET review_status = 'pending' WHERE review_status IS NULL")
            )
    except Exception:
        pass


async def get_session():
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
