from lawboi.adapters.structured.pool import pooled_cursor
from lawboi.adapters.structured.postgres import PostgresStore
from lawboi.domain.models import Act

from tests.lawboi.adapters.conftest import requires_live_postgres

pytestmark = requires_live_postgres


async def test_truncate_after_removes_rows_between_tests(pool):
    store = PostgresStore(pool)
    await store.upsert_act(Act(None, "RT I ISOLATION 1", "Testact", None, "general", "seadus"))
    async with pooled_cursor(pool) as cur:
        await cur.execute("SELECT count(*) FROM act")
        row = await cur.fetchone()
    assert row[0] == 1


async def test_previous_test_rows_are_gone(pool):
    async with pooled_cursor(pool) as cur:
        await cur.execute("SELECT count(*) FROM act")
        row = await cur.fetchone()
    assert row[0] == 0
