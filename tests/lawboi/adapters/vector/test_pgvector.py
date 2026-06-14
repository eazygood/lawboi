import os
from datetime import date
import pytest
from lawboi.adapters.structured.pool import make_pool
from lawboi.adapters.structured.postgres import PostgresStore
from lawboi.adapters.vector.pgvector import PostgresVectorStore
from lawboi.domain.models import Act, ActVersion, Provision
from lawboi.domain.dto import VectorHit

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="requires live Postgres")


@pytest.fixture
def pool():
    return make_pool(minconn=1, maxconn=2)


@pytest.fixture
def store(pool):
    return PostgresStore(pool)


@pytest.fixture
def vector(pool):
    return PostgresVectorStore(pool)


def test_upsert_then_query(store, vector):
    aid = store.upsert_act(Act(None, "RT I VEC 1", "Vektorseadus", None, "general", "seadus"))
    vid = store.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h"))
    pid = store.insert_provision(Provision(None, vid, "77", "section", "vektorikatse tekst", None, None))

    embedding = [0.01] * 1024
    vector.upsert(pid, embedding)

    hits = vector.query(embedding, n_results=5)
    assert hits and isinstance(hits[0], VectorHit)
    assert any(h.provision_id == pid for h in hits)
    match = next(h for h in hits if h.provision_id == pid)
    assert match.section_num == "77"
    assert match.text == "vektorikatse tekst"
    assert match.metadata["eli"] == "RT I VEC 1"
