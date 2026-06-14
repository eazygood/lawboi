import os
import pytest
from lawboi.adapters.structured.pool import make_pool, pooled_cursor

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="requires live Postgres")


def test_pooled_cursor_executes_and_returns_connection():
    pool = make_pool(minconn=1, maxconn=2)
    with pooled_cursor(pool) as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
    with pooled_cursor(pool) as cur:
        cur.execute("SELECT 2")
        assert cur.fetchone()[0] == 2
