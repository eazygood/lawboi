from datetime import date, timedelta
from typing import Optional

from lawboi.adapters.structured.pool import pooled_cursor
from lawboi.adapters._util import build_provision_metadata
from lawboi.domain.models import Act, ActVersion, Provision
from lawboi.domain.dto import RetrievedProvision


class PostgresStore:
    def __init__(self, pool):
        self._pool = pool

    async def upsert_act(self, act: Act) -> int:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute(
                """
                INSERT INTO act (eli, title_et, title_en, domain, act_type)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (eli) DO UPDATE SET title_et = EXCLUDED.title_et
                RETURNING id
            """,
                (act.eli, act.title_et, act.title_en, act.domain, act.act_type),
            )
            row = await cur.fetchone()
            assert row is not None  # INSERT ... RETURNING always yields a row
            return row[0]

    async def upsert_act_version(self, version: ActVersion) -> int:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute(
                "SELECT id FROM act_version WHERE act_id=%s AND effective_from=%s",
                (version.act_id, version.effective_from),
            )
            row = await cur.fetchone()
            if row:
                return row[0]
            await cur.execute(
                """
                INSERT INTO act_version (act_id, effective_from, effective_to,
                                         source_url, source_hash, source_global_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """,
                (
                    version.act_id,
                    version.effective_from,
                    version.effective_to,
                    version.source_url,
                    version.source_hash,
                    version.source_global_id,
                ),
            )
            row = await cur.fetchone()
            assert row is not None  # INSERT ... RETURNING always yields a row
            version_id = row[0]
            await cur.execute(
                """
                UPDATE act_version SET effective_to = %s
                 WHERE act_id = %s AND effective_to IS NULL
                   AND effective_from < %s
            """,
                (
                    version.effective_from - timedelta(days=1),
                    version.act_id,
                    version.effective_from,
                ),
            )
            return version_id

    async def insert_provision(self, provision: Provision) -> int:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute(
                """
                INSERT INTO provision (act_version_id, section_num, level, text_et, text_en, parent_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """,
                (
                    provision.act_version_id,
                    provision.section_num,
                    provision.level,
                    provision.text_et,
                    provision.text_en,
                    provision.parent_id,
                ),
            )
            row = await cur.fetchone()
            assert row is not None  # INSERT ... RETURNING always yields a row
            return row[0]

    async def ingested_global_ids(self) -> set[int]:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute(
                """
                SELECT av.source_global_id
                FROM act_version av
                WHERE av.source_global_id IS NOT NULL
                  AND EXISTS (SELECT 1 FROM provision p WHERE p.act_version_id = av.id)
                  AND NOT EXISTS (
                      SELECT 1 FROM provision p
                      WHERE p.act_version_id = av.id AND p.embedding IS NULL
                  )
            """
            )
            rows = await cur.fetchall()
            return {r[0] for r in rows}

    async def version_fully_indexed(self, act_version_id: int) -> bool:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM provision WHERE act_version_id = %s
                ) AND NOT EXISTS (
                    SELECT 1 FROM provision
                    WHERE act_version_id = %s AND embedding IS NULL
                )
            """,
                (act_version_id, act_version_id),
            )
            row = await cur.fetchone()
            assert row is not None  # SELECT EXISTS(...) AND NOT EXISTS(...) always yields a row
            return bool(row[0])

    async def delete_provisions_for_version(self, act_version_id: int) -> None:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute("DELETE FROM provision WHERE act_version_id = %s",
                              (act_version_id,))

    async def get_act(self, eli: str) -> Optional[Act]:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute(
                "SELECT id, eli, title_et, title_en, domain, act_type FROM act WHERE eli = %s",
                (eli,),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return Act(id=row[0], eli=row[1], title_et=row[2], title_en=row[3],
                   domain=row[4], act_type=row[5])

    async def list_act_versions(self, eli: str) -> list[ActVersion]:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute(
                """
                SELECT av.id, av.act_id, av.effective_from, av.effective_to,
                       av.source_url, av.source_hash, av.source_global_id
                FROM act_version av JOIN act a ON av.act_id = a.id
                WHERE a.eli = %s ORDER BY av.effective_from DESC
            """,
                (eli,),
            )
            rows = await cur.fetchall()
        return [
            ActVersion(id=r[0], act_id=r[1], effective_from=r[2], effective_to=r[3],
                       source_url=r[4], source_hash=r[5], source_global_id=r[6])
            for r in rows
        ]

    async def provisions_as_of(self, eli: str, on: date) -> list[Provision]:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute(
                """
                SELECT p.id, p.act_version_id, p.section_num, p.level,
                       p.text_et, p.text_en, p.parent_id
                FROM provision p
                JOIN act_version av ON p.act_version_id = av.id
                JOIN act a ON av.act_id = a.id
                WHERE a.eli = %s
                  AND av.effective_from <= %s
                  AND (av.effective_to IS NULL OR av.effective_to >= %s)
                ORDER BY p.id
            """,
                (eli, on, on),
            )
            rows = await cur.fetchall()
        return [
            Provision(id=r[0], act_version_id=r[1], section_num=r[2], level=r[3],
                      text_et=r[4], text_en=r[5], parent_id=r[6])
            for r in rows
        ]

    async def fts_search(self, query: str, effective_date: date) -> list[RetrievedProvision]:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute(
                """
                SELECT p.id, p.section_num, p.text_et, p.act_version_id,
                       a.title_et, a.eli,
                       ts_rank(to_tsvector('simple', p.text_et),
                               plainto_tsquery('simple', %s)) AS rank
                FROM provision p
                JOIN act_version av ON p.act_version_id = av.id
                JOIN act a ON av.act_id = a.id
                WHERE to_tsvector('simple', p.text_et)
                      @@ plainto_tsquery('simple', %s)
                  AND av.effective_from <= %s
                  AND (av.effective_to IS NULL OR av.effective_to >= %s)
                ORDER BY rank DESC
                LIMIT 20
            """,
                (query, query, effective_date, effective_date),
            )
            rows = await cur.fetchall()
            return [
                RetrievedProvision(
                    provision_id=r[0],
                    section_num=r[1],
                    text=r[2],
                    metadata=build_provision_metadata(r[4], r[5], r[1], r[3]),
                )
                for r in rows
            ]

    async def create_conversation(self) -> int:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute("INSERT INTO conversation DEFAULT VALUES RETURNING id")
            row = await cur.fetchone()
            assert row is not None  # INSERT ... RETURNING always yields a row
            return row[0]

    async def append_message(self, conversation_id: int, role: str, content: str) -> None:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute(
                "INSERT INTO message (conversation_id, role, content) VALUES (%s, %s, %s)",
                (conversation_id, role, content),
            )

    async def recent_messages(self, conversation_id: int, limit: int = 10) -> list[dict]:
        async with pooled_cursor(self._pool) as cur:
            await cur.execute(
                "SELECT role, content FROM message WHERE conversation_id = %s "
                "ORDER BY id DESC LIMIT %s",
                (conversation_id, limit),
            )
            rows = await cur.fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    async def exact_lookup(self, section_num: str, as_of: date, limit: int,
                           eli: Optional[str], title_query: Optional[str]) -> list[RetrievedProvision]:
        base_sql = """
            SELECT p.id, p.section_num, p.text_et, p.act_version_id,
                   a.title_et, a.eli
            FROM provision p
            JOIN act_version av ON p.act_version_id = av.id
            JOIN act a ON av.act_id = a.id
            WHERE p.section_num = %s
              AND av.effective_from <= %s
              AND (av.effective_to IS NULL OR av.effective_to >= %s)
        """
        async with pooled_cursor(self._pool) as cur:
            if eli:
                await cur.execute(
                    base_sql + " AND a.eli ILIKE %s LIMIT %s",
                    (section_num, as_of, as_of, f"%{eli}%", limit),
                )
                rows = await cur.fetchall()
            elif title_query:
                await cur.execute(
                    base_sql
                    + """
                      AND to_tsvector('simple', a.title_et)
                          @@ plainto_tsquery('simple', %s)
                    LIMIT %s
                    """,
                    (section_num, as_of, as_of, title_query, limit),
                )
                rows = await cur.fetchall()
                if not rows:
                    await cur.execute(
                        base_sql + " LIMIT %s", (section_num, as_of, as_of, limit)
                    )
                    rows = await cur.fetchall()
            else:
                await cur.execute(base_sql + " LIMIT %s", (section_num, as_of, as_of, limit))
                rows = await cur.fetchall()
            return [
                RetrievedProvision(
                    provision_id=r[0],
                    section_num=r[1],
                    text=r[2],
                    metadata=build_provision_metadata(r[4], r[5], r[1], r[3]),
                )
                for r in rows
            ]
