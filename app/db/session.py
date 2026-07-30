from __future__ import annotations

from collections.abc import AsyncGenerator
from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import (
    DATABASE_URL,
    INITIAL_ADMIN_PASSWORD,
    INITIAL_ADMIN_USER,
    logger,
)
from app.crud.bucket import crud_create_bucket
from app.crud.user import crud_create_user
from app.db.tables import Base
from app.models.bucket import BucketInCreate
from app.models.user import User, UserInCreate

engine: AsyncEngine | None = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None


class Database:
    """Holds the async engine after startup (used by health / GC)."""

    engine: AsyncEngine | None = None


db = Database()


def normalize_database_url(url: str) -> str:
    if url.startswith("mysql://"):
        return "mysql+aiomysql://" + url[len("mysql://") :]
    if url.startswith("mysql+pymysql://"):
        return "mysql+aiomysql://" + url[len("mysql+pymysql://") :]
    if url.startswith("mysql+asyncmy://"):
        return "mysql+aiomysql://" + url[len("mysql+asyncmy://") :]
    return url


def build_database_url() -> str:
    raw = (DATABASE_URL or "").strip()
    if raw:
        return normalize_database_url(raw)
    from app.core.config import (
        MYSQL_DATABASE,
        MYSQL_HOST,
        MYSQL_PASSWORD,
        MYSQL_PORT,
        MYSQL_USER,
    )

    user = quote_plus(MYSQL_USER or "")
    password = quote_plus(MYSQL_PASSWORD or "")
    host = MYSQL_HOST or "localhost"
    port = MYSQL_PORT or 3306
    database = MYSQL_DATABASE or "TelezonS3"
    auth = f"{user}:{password}@" if password or user else ""
    return f"mysql+aiomysql://{auth}{host}:{port}/{database}"


async def init_db(session: AsyncSession) -> None:
    logger.info("Initializing database")
    from app.crud.user import crud_get_user_by_username

    if INITIAL_ADMIN_USER and INITIAL_ADMIN_PASSWORD:
        admin_user = await crud_get_user_by_username(session, INITIAL_ADMIN_USER)
        if not admin_user:
            user = UserInCreate(
                username=INITIAL_ADMIN_USER,
                password=INITIAL_ADMIN_PASSWORD,
                email="admin@telezon.dev",
            )
            admin_user = await crud_create_user(session, user, admin=True)
            await session.commit()
            logger.info("Admin user created")
            logger.info("Admin user: %s", INITIAL_ADMIN_USER)
            logger.info("Your bucket is the same as your username")
            bucket = BucketInCreate(
                name=admin_user.username, owner_username=admin_user.username
            )
            await crud_create_bucket(session, bucket, User(**admin_user.model_dump()))
            await session.commit()


async def connect_to_database() -> None:
    global engine, async_session_factory
    url = build_database_url()
    engine = create_async_engine(url, pool_pre_ping=True)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    db.engine = engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_factory() as session:
        await init_db(session)
    logger.info("Connected to MySQL")


async def close_database_connection() -> None:
    global engine, async_session_factory
    if engine is not None:
        await engine.dispose()
    engine = None
    async_session_factory = None
    db.engine = None
    logger.info("Disconnected from MySQL")


async def get_database() -> AsyncGenerator[AsyncSession, None]:
    if async_session_factory is None:
        raise RuntimeError("Database is not connected")
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def ping_database() -> None:
    if engine is None:
        raise RuntimeError("Database engine not initialized")
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
