from lawboi.adapters.structured.pool import pooled_cursor
from lawboi.domain.dto import VectorHit


def _vec(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


class PostgresVectorStore:
    def __init__(self, pool):
        self._pool = pool

    def upsert(self, provision_id: int, embedding: list[float]) -> None:
        with pooled_cursor(self._pool) as cur:
            cur.execute(
                "UPDATE provision SET embedding = %s::vector WHERE id = %s",
                (_vec(embedding), provision_id),
            )

    def query(self, embedding: list[float], n_results: int) -> list[VectorHit]:
        with pooled_cursor(self._pool) as cur:
            cur.execute(
                """
                SELECT p.id, p.section_num, p.text_et, a.title_et, a.eli,
                       p.act_version_id
                FROM provision p
                JOIN act_version av ON p.act_version_id = av.id
                JOIN act a ON av.act_id = a.id
                WHERE p.embedding IS NOT NULL
                ORDER BY p.embedding <=> %s::vector
                LIMIT %s
                """,
                (_vec(embedding), n_results),
            )
            return [
                VectorHit(
                    provision_id=r[0],
                    section_num=r[1],
                    text=r[2],
                    metadata={
                        "act_title": r[3],
                        "eli": r[4],
                        "section_num": r[1],
                        "act_version_id": r[5],
                        "is_translation": False,
                        "context": "",
                    },
                )
                for r in cur.fetchall()
            ]
