from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.api.storage.database import Database
from app.api.storage.redis import RedisManager

db = Database()
cache = RedisManager()


async def get_database() -> Database:
    """
    Dependency для получения объекта базы данных.

    Returns:
        Database: Объект базы данных.
    """
    if not db.pool:
        await db.connect()
    return db


async def get_cache() -> RedisManager:
    """
    Dependency для получения объекта кэша.

    Returns:
        RedisManager: Объект кэша.
    """
    if not cache.client:
        await cache.connect()
    return cache


@asynccontextmanager
async def lifespan(app) -> AsyncGenerator[None, None]:
    """
    Настройка жизненного цикла приложения.

    Args:
        app (FastAPI): FastAPI-приложение.

    Yields:
        None: Управление жизненным циклом.
    """
    await db.connect()
    await cache.connect()

    yield

    await db.close()
    await cache.close()
