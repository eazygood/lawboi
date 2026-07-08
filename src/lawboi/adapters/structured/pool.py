import os
from contextlib import asynccontextmanager
from typing import Optional

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool


async def make_pool(database_url: Optional[str] = None, min_size: int = 5,
                     max_size: int = 50) -> AsyncConnectionPool[AsyncConnection]:
    dsn = database_url or os.environ["DATABASE_URL"]
    pool: AsyncConnectionPool[AsyncConnection] = AsyncConnectionPool(
        dsn, min_size=min_size, max_size=max_size, open=False)
    await pool.open()
    return pool


@asynccontextmanager
async def pooled_cursor(pool: AsyncConnectionPool):
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            yield cur
