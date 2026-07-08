import os
import pytest
from lawboi.adapters.structured.pool import make_pool, pooled_cursor

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="requires live Postgres")


async def test_pooled_cursor_executes_and_returns_connection():
    pool = await make_pool(min_size=1, max_size=2)
    async with pooled_cursor(pool) as cur:
        await cur.execute("SELECT 1")
        row = await cur.fetchone()
        assert row is not None and row[0] == 1
    async with pooled_cursor(pool) as cur:
        await cur.execute("SELECT 2")
        row = await cur.fetchone()
        assert row is not None and row[0] == 2
