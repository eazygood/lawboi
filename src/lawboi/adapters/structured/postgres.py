from datetime import date, timedelta
from typing import Optional

from lawboi.adapters.structured.pool import pooled_cursor
from lawboi.domain.models import Act, ActVersion, Provision
from lawboi.domain.dto import RetrievedProvision


class PostgresStore:
    def __init__(self, pool):
        self._pool = pool

    def upsert_act(self, act: Act) -> int:
        with pooled_cursor(self._pool) as cur:
            cur.execute(
                """
                INSERT INTO act (eli, title_et, title_en, domain, act_type)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (eli) DO UPDATE SET title_et = EXCLUDED.title_et
                RETURNING id
            """,
                (act.eli, act.title_et, act.title_en, act.domain, act.act_type),
            )
            return cur.fetchone()[0]

    def upsert_act_version(self, version: ActVersion) -> int:
        with pooled_cursor(self._pool) as cur:
            cur.execute(
                "SELECT id FROM act_version WHERE act_id=%s AND effective_from=%s",
                (version.act_id, version.effective_from),
            )
            row = cur.fetchone()
            if row:
                return row[0]
            cur.execute(
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
            version_id = cur.fetchone()[0]
            cur.execute(
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

    def insert_provision(self, provision: Provision) -> int:
        with pooled_cursor(self._pool) as cur:
            cur.execute(
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
            return cur.fetchone()[0]

    def ingested_global_ids(self) -> set[int]:
        with pooled_cursor(self._pool) as cur:
            cur.execute("SELECT source_global_id FROM act_version "
                        "WHERE source_global_id IS NOT NULL")
            return {r[0] for r in cur.fetchall()}

    def version_has_provisions(self, act_version_id: int) -> bool:
        with pooled_cursor(self._pool) as cur:
            cur.execute("SELECT 1 FROM provision WHERE act_version_id=%s LIMIT 1",
                        (act_version_id,))
            return cur.fetchone() is not None

    def get_act(self, eli: str) -> Optional[Act]:
        with pooled_cursor(self._pool) as cur:
            cur.execute(
                "SELECT id, eli, title_et, title_en, domain, act_type FROM act WHERE eli = %s",
                (eli,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return Act(id=row[0], eli=row[1], title_et=row[2], title_en=row[3],
                   domain=row[4], act_type=row[5])

    def list_act_versions(self, eli: str) -> list[ActVersion]:
        with pooled_cursor(self._pool) as cur:
            cur.execute(
                """
                SELECT av.id, av.act_id, av.effective_from, av.effective_to,
                       av.source_url, av.source_hash, av.source_global_id
                FROM act_version av JOIN act a ON av.act_id = a.id
                WHERE a.eli = %s ORDER BY av.effective_from DESC
            """,
                (eli,),
            )
            rows = cur.fetchall()
        return [
            ActVersion(id=r[0], act_id=r[1], effective_from=r[2], effective_to=r[3],
                       source_url=r[4], source_hash=r[5], source_global_id=r[6])
            for r in rows
        ]

    def provisions_as_of(self, eli: str, on: date) -> list[Provision]:
        with pooled_cursor(self._pool) as cur:
            cur.execute(
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
            rows = cur.fetchall()
        return [
            Provision(id=r[0], act_version_id=r[1], section_num=r[2], level=r[3],
                      text_et=r[4], text_en=r[5], parent_id=r[6])
            for r in rows
        ]

    def fts_search(self, query: str, effective_date: date) -> list[RetrievedProvision]:
        with pooled_cursor(self._pool) as cur:
            cur.execute(
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
            return [
                RetrievedProvision(
                    provision_id=r[0],
                    section_num=r[1],
                    text=r[2],
                    metadata={
                        "act_title": r[4],
                        "eli": r[5],
                        "section_num": r[1],
                        "act_version_id": r[3],
                        "is_translation": False,
                        "context": "",
                    },
                )
                for r in cur.fetchall()
            ]

    def exact_lookup(self, section_num: str, as_of: date, limit: int,
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
        with pooled_cursor(self._pool) as cur:
            if eli:
                cur.execute(
                    base_sql + " AND a.eli ILIKE %s LIMIT %s",
                    (section_num, as_of, as_of, f"%{eli}%", limit),
                )
            elif title_query:
                cur.execute(
                    base_sql
                    + """
                      AND to_tsvector('simple', a.title_et)
                          @@ plainto_tsquery('simple', %s)
                    LIMIT %s
                    """,
                    (section_num, as_of, as_of, title_query, limit),
                )
                rows = cur.fetchall()
                if not rows:
                    cur.execute(
                        base_sql + " LIMIT %s", (section_num, as_of, as_of, limit)
                    )
                    rows = cur.fetchall()
                return [
                    RetrievedProvision(
                        provision_id=r[0],
                        section_num=r[1],
                        text=r[2],
                        metadata={
                            "act_title": r[4],
                            "eli": r[5],
                            "section_num": r[1],
                            "act_version_id": r[3],
                            "is_translation": False,
                            "context": "",
                        },
                    )
                    for r in rows
                ]
            else:
                cur.execute(base_sql + " LIMIT %s", (section_num, as_of, as_of, limit))
            return [
                RetrievedProvision(
                    provision_id=r[0],
                    section_num=r[1],
                    text=r[2],
                    metadata={
                        "act_title": r[4],
                        "eli": r[5],
                        "section_num": r[1],
                        "act_version_id": r[3],
                        "is_translation": False,
                        "context": "",
                    },
                )
                for r in cur.fetchall()
            ]
