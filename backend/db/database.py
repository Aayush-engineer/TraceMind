import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import (
    create_async_engine, AsyncSession, async_sessionmaker
)
from typing import AsyncGenerator
from .models import Base

_raw_url = os.getenv("DATABASE_URL", "").strip()

if not _raw_url:
    _data_dir = Path(__file__).parent.parent / "data"
    _data_dir.mkdir(parents=True, exist_ok=True)
    _raw_url = f"sqlite:///{_data_dir / 'TraceMind.db'}"

DATABASE_URL = _raw_url
_is_sqlite   = DATABASE_URL.startswith("sqlite")

def _make_sync_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url

def _make_async_url(url: str) -> str:
    # Strip query params asyncpg can't handle in the URL string
    import re
    url = re.sub(r'[?&]sslmode=[^&]*', '', url)
    url = re.sub(r'[?&]channel_binding=[^&]*', '', url)
    url = re.sub(r'[?&]connect_timeout=[^&]*', '', url)
    # Clean up trailing ? if all params were stripped
    url = url.rstrip('?').rstrip('&')

    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url

SYNC_DATABASE_URL  = _make_sync_url(DATABASE_URL)
ASYNC_DATABASE_URL = _make_async_url(DATABASE_URL)

connect_args = {"check_same_thread": False} if _is_sqlite else {}

sync_engine = create_engine(
    SYNC_DATABASE_URL,
    connect_args  = connect_args,
    pool_pre_ping = True,
    pool_size     = 5 if not _is_sqlite else 1,
    max_overflow  = 10 if not _is_sqlite else 0,
    pool_timeout  = 10, 
    pool_recycle  = 300,
)

SessionLocal = sessionmaker(
    bind       = sync_engine,
    autocommit = False,
    autoflush  = False,
)

if _is_sqlite:
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        echo=False,
    )
else:
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=300,
        echo=False,
        connect_args={"ssl": "require"},
    )

AsyncSessionLocal = async_sessionmaker(
    bind           = async_engine,
    class_         = AsyncSession,
    autocommit     = False,
    autoflush      = False,
    expire_on_commit = False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_db() -> Session:
    return SessionLocal()


async def init_db():
    if _is_sqlite:
        Base.metadata.create_all(bind=sync_engine)
        print(f"  DB ready (SQLite): {DATABASE_URL}")
        return

    try:
        async with async_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        db_display = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
        print(f"  DB ready: {db_display}")
    except Exception as e:
        print(f"  DB connection failed: {e}")
        print("  Check DATABASE_URL in Render environment variables")
        raise