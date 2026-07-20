from datetime import date
import pytest
from lawboi.adapters.structured.postgres import PostgresStore
from lawboi.adapters.vector.pgvector import PostgresVectorStore
from lawboi.domain.models import Act, ActVersion, Provision
from lawboi.domain.dto import VectorHit

from tests.lawboi.adapters.conftest import requires_live_postgres

pytestmark = requires_live_postgres


@pytest.fixture
def store(pool):
    return PostgresStore(pool)


@pytest.fixture
def vector(pool):
    return PostgresVectorStore(pool)


async def test_upsert_then_query(store, vector):
    aid = await store.upsert_act(Act(None, "RT I VEC 1", "Vektorseadus", None, "general", "seadus"))
    vid = await store.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h"))
    pid = await store.insert_provision(Provision(None, vid, "77", "section", "vektorikatse tekst", None, None))

    embedding = [0.01] * 1024
    await vector.upsert(pid, embedding)

    hits = await vector.query(embedding, n_results=5, as_of=date(2020, 1, 1))  # added as_of
    assert hits and isinstance(hits[0], VectorHit)
    assert any(h.provision_id == pid for h in hits)
    match = next(h for h in hits if h.provision_id == pid)
    assert match.section_num == "77"
    assert match.text == "vektorikatse tekst"
    assert match.metadata["eli"] == "RT I VEC 1"


async def test_query_excludes_expired_versions(store, vector):
    """A provision from an expired act version must not appear in results."""
    aid = await store.upsert_act(Act(None, "RT I VEC 2", "Vananenud seadus", None, "general", "seadus"))
    vid = await store.upsert_act_version(
        ActVersion(None, aid, date(2000, 1, 1), date(2010, 12, 31), "u", "h")
    )
    pid = await store.insert_provision(Provision(None, vid, "1", "section", "vana tekst", None, None))
    embedding = [0.01] * 1024
    await vector.upsert(pid, embedding)

    # Query as of 2020 — this provision's version expired in 2010
    hits = await vector.query(embedding, n_results=5, as_of=date(2020, 1, 1))
    assert all(h.provision_id != pid for h in hits), "expired provision should be excluded"
