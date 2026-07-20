import os

import pytest

from lawboi.adapters.structured.pool import make_pool

requires_live_postgres = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="requires live Postgres (TEST_DATABASE_URL)",
)

_TABLES_IN_FK_ORDER = [
    "provision", "act_version", "act", "message", "conversation", "answer_cache",
]


@pytest.fixture
async def pool():
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("requires live Postgres (TEST_DATABASE_URL)")
    pool = await make_pool(os.environ["TEST_DATABASE_URL"], min_size=1, max_size=2)
    yield pool

    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                for table in _TABLES_IN_FK_ORDER:
                    await cur.execute(f"DELETE FROM {table}")
            await conn.commit()
    finally:
        await pool.close()
