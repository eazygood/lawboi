from datetime import date
from typing import Optional

from psycopg.types.json import Jsonb

from lawboi.adapters.structured.pool import pooled_cursor


def _vec(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


class PostgresAnswerCache:
    def __init__(self, pool, min_similarity: float = 0.97, retention_days: int = 30,
                 cache_version: str = ""):
        self._pool = pool
        self._min_similarity = min_similarity
        self._retention_days = retention_days
        self._cache_version = cache_version

    async def find(self, embedding: list[float], as_of: date) -> Optional[dict]:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute(
                """
                SELECT answer_payload, 1 - (cache_embedding <=> %s::vector) AS similarity
                FROM answer_cache
                WHERE as_of = %s AND cache_version = %s
                ORDER BY cache_embedding <=> %s::vector
                LIMIT 1
                """,
                (_vec(embedding), as_of, self._cache_version, _vec(embedding)),
            )
            row = await cur.fetchone()
            if row is None or row[1] < self._min_similarity:
                return None
            return row[0]

    async def store(self, embedding: list[float], as_of: date, query_text: str,
                     cache_key_text: str, answer_payload: dict) -> None:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute(
                """
                INSERT INTO answer_cache
                    (as_of, query_text, cache_key_text, cache_version, cache_embedding,
                     answer_payload)
                VALUES (%s, %s, %s, %s, %s::vector, %s)
                """,
                (as_of, query_text, cache_key_text, self._cache_version, _vec(embedding),
                 Jsonb(answer_payload)),
            )
            await cur.execute(
                "DELETE FROM answer_cache WHERE created_at < now() - %s * interval '1 day'",
                (self._retention_days,),
            )

    async def clear(self) -> None:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute("DELETE FROM answer_cache")
