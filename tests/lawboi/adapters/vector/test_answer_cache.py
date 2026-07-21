from datetime import date

import pytest

from lawboi.adapters.structured.pool import pooled_cursor
from lawboi.adapters.vector.answer_cache import PostgresAnswerCache

from tests.lawboi.adapters.conftest import requires_live_postgres

pytestmark = requires_live_postgres


@pytest.fixture
def cache(pool):
    return PostgresAnswerCache(pool, min_similarity=0.99, retention_days=30,
                                cache_version="v1")


def _vec(x: float) -> list[float]:
    return [x] * 1024


async def test_store_then_find_matches_same_as_of(cache):
    as_of = date(2026, 7, 17)
    payload = {"answer": "Under § 97 notice applies.", "citations": []}
    await cache.store(_vec(0.5), as_of, "notice period?", "notice period?", payload)

    found = await cache.find(_vec(0.5), as_of)
    assert found == payload


async def test_find_returns_none_for_different_as_of(cache):
    payload = {"answer": "x", "citations": []}
    await cache.store(_vec(0.5), date(2026, 7, 17), "q", "q", payload)

    found = await cache.find(_vec(0.5), date(2026, 7, 18))
    assert found is None


async def test_find_returns_none_below_similarity_threshold(cache):
    as_of = date(2026, 7, 17)
    payload = {"answer": "x", "citations": []}
    orthogonal = [1.0] + [0.0] * 1023
    other = [0.0, 1.0] + [0.0] * 1022
    await cache.store(orthogonal, as_of, "q", "q", payload)

    found = await cache.find(other, as_of)
    assert found is None


async def test_store_prunes_rows_older_than_retention_days(pool, cache):
    old_as_of = date(2000, 1, 1)
    async with pooled_cursor(pool) as cur:
        await cur.execute(
            """
            INSERT INTO answer_cache
                (as_of, query_text, cache_key_text, cache_version, cache_embedding,
                 answer_payload, created_at)
            VALUES (%s, 'old', 'old', 'v1', %s::vector, '{}'::jsonb, now() - interval '60 days')
            """,
            (old_as_of, "[" + ",".join(str(x) for x in _vec(0.1)) + "]"),
        )

    await cache.store(_vec(0.5), date(2026, 7, 17), "q", "q", {"answer": "x", "citations": []})

    async with pooled_cursor(pool) as cur:
        await cur.execute("SELECT count(*) FROM answer_cache WHERE as_of = %s", (old_as_of,))
        row = await cur.fetchone()
    assert row[0] == 0


async def test_find_ignores_row_stored_under_different_version(pool):
    as_of = date(2026, 7, 17)
    payload = {"answer": "x", "citations": []}
    writer = PostgresAnswerCache(pool, min_similarity=0.99, retention_days=30,
                                  cache_version="v1")
    await writer.store(_vec(0.5), as_of, "q", "q", payload)

    reader = PostgresAnswerCache(pool, min_similarity=0.99, retention_days=30,
                                  cache_version="v2")
    found = await reader.find(_vec(0.5), as_of)
    assert found is None


async def test_clear_wipes_rows_regardless_of_version(pool):
    as_of = date(2026, 7, 17)
    payload = {"answer": "x", "citations": []}
    v1 = PostgresAnswerCache(pool, min_similarity=0.99, retention_days=30, cache_version="v1")
    v2 = PostgresAnswerCache(pool, min_similarity=0.99, retention_days=30, cache_version="v2")
    await v1.store(_vec(0.5), as_of, "q", "q", payload)
    await v2.store(_vec(0.6), as_of, "q2", "q2", payload)

    await v1.clear()

    async with pooled_cursor(pool) as cur:
        await cur.execute("SELECT count(*) FROM answer_cache")
        row = await cur.fetchone()
    assert row[0] == 0
