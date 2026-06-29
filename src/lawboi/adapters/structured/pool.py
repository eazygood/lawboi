import os
from contextlib import contextmanager
from typing import Optional

from psycopg2.pool import ThreadedConnectionPool


def make_pool(database_url: Optional[str] = None, minconn: int = 1,
              maxconn: int = 10) -> ThreadedConnectionPool:
    dsn = database_url or os.environ["DATABASE_URL"]
    return ThreadedConnectionPool(minconn, maxconn, dsn=dsn)


@contextmanager
def pooled_cursor(pool: ThreadedConnectionPool):
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            yield cur
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
