import os
from lawboi.adapters.structured.pool import make_pool, pooled_cursor

from tests.lawboi.adapters.conftest import requires_live_postgres

pytestmark = requires_live_postgres


async def test_pooled_cursor_executes_and_returns_connection():
    pool = await make_pool(os.environ["TEST_DATABASE_URL"], min_size=1, max_size=2)
    async with pooled_cursor(pool) as cur:
        await cur.execute("SELECT 1")
        row = await cur.fetchone()
        assert row is not None and row[0] == 1
    async with pooled_cursor(pool) as cur:
        await cur.execute("SELECT 2")
        row = await cur.fetchone()
        assert row is not None and row[0] == 2
