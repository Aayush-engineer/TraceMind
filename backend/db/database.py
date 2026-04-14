import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from typing import AsyncGenerator

from .models import Base

_raw_url = os.getenv("DATABASE_URL", "").strip()

if not _raw_url:
    _data_dir = Path(__file__).parent.parent / "data"
    _data_dir.mkdir(parents=True, exist_ok=True)
    _raw_url = f"sqlite:///{_data_dir / 'TraceMind.db'}"

DATABASE_URL = _raw_url

def _import_all_models():
    from ..api import agent  

try:
    _import_all_models()
except ImportError:
    pass  

from ..core.config import DATABASE_URL, SQLITE_PATH as _sqlite_path
_is_sqlite = DATABASE_URL.startswith("sqlite")

if DATABASE_URL.startswith("sqlite"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
else:
    ASYNC_DATABASE_URL = DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

sync_engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,      
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
)

if DATABASE_URL.startswith("sqlite"):
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
        echo=False,
    )

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  
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
    """
    Run Alembic migrations on startup instead of create_all.
    This is the production-correct approach — tracks schema versions,
    supports rollback, never drops existing data.
    """
    import subprocess
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).parent.parent
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(backend_dir),
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print(f"  DB migrations applied successfully")
        else:
            # Fall back to create_all if alembic fails
            print(f"  Alembic warning: {result.stderr[:200]}")
            print(f"  Falling back to create_all")
            if _is_sqlite:
                Base.metadata.create_all(bind=sync_engine)
            else:
                async with async_engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        print(f"  Migration error: {e} — using create_all fallback")
        if _is_sqlite:
            Base.metadata.create_all(bind=sync_engine)

    print(f"  DB ready: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")