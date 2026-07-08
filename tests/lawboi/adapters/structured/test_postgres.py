import os
from datetime import date
import pytest
from lawboi.adapters.structured.pool import make_pool
from lawboi.adapters.structured.postgres import PostgresStore
from lawboi.adapters.vector.pgvector import PostgresVectorStore
from lawboi.domain.models import Act, ActVersion, Provision

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="requires live Postgres")


@pytest.fixture
async def store():
    return PostgresStore(await make_pool(min_size=1, max_size=2))


@pytest.fixture
async def vector():
    return PostgresVectorStore(await make_pool(min_size=1, max_size=2))


async def test_write_then_fts_search(store):
    aid = await store.upsert_act(Act(None, "RT I TEST 1", "Testseadus", None, "general", "seadus"))
    vid = await store.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h"))
    await store.insert_provision(Provision(None, vid, "99", "section", "unikaalmärksõna", None, None))
    hits = await store.fts_search("unikaalmärksõna", date(2021, 1, 1))
    assert any(h.section_num == "99" for h in hits)


async def test_exact_lookup_by_section(store):
    aid = await store.upsert_act(Act(None, "RT I TEST 2", "Teine", None, "general", "seadus"))
    vid = await store.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h"))
    await store.insert_provision(Provision(None, vid, "203", "section", "äriühing", None, None))
    rows = await store.exact_lookup("203", date(2021, 1, 1), limit=5, eli="RT I TEST 2", title_query=None)
    assert rows and rows[0].section_num == "203"


async def test_get_act_roundtrip(store):
    await store.upsert_act(Act(None, "RT I TEST 3", "Kolmas", "Third", "tax", "seadus"))
    act = await store.get_act("RT I TEST 3")
    assert act is not None and act.title_et == "Kolmas" and act.act_type == "seadus"
    assert await store.get_act("RT I MISSING") is None


async def test_list_act_versions_newest_first(store):
    aid = await store.upsert_act(Act(None, "RT I TEST 4", "Neljas", None, "general", "seadus"))
    await store.upsert_act_version(ActVersion(None, aid, date(2010, 1, 1), date(2014, 12, 31), "u1", "h1"))
    await store.upsert_act_version(ActVersion(None, aid, date(2015, 1, 1), None, "u2", "h2"))
    versions = await store.list_act_versions("RT I TEST 4")
    assert [v.effective_from for v in versions] == [date(2015, 1, 1), date(2010, 1, 1)]


async def test_provisions_as_of_filters_by_effective_window(store):
    aid = await store.upsert_act(Act(None, "RT I TEST 5", "Viies", None, "general", "seadus"))
    vid = await store.upsert_act_version(ActVersion(None, aid, date(2015, 1, 1), None, "u", "h"))
    await store.insert_provision(Provision(None, vid, "5", "section", "kehtiv", None, None))
    assert [p.section_num for p in await store.provisions_as_of("RT I TEST 5", date(2016, 1, 1))] == ["5"]
    assert await store.provisions_as_of("RT I TEST 5", date(2014, 1, 1)) == []


async def test_conversation_history_roundtrip_in_order(store):
    cid = await store.create_conversation()
    await store.append_message(cid, "user", "notice period?")
    await store.append_message(cid, "assistant", "30 days.")
    await store.append_message(cid, "user", "and severance?")
    history = await store.recent_messages(cid, limit=10)
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "notice period?"),
        ("assistant", "30 days."),
        ("user", "and severance?"),
    ]


async def test_recent_messages_respects_limit(store):
    cid = await store.create_conversation()
    for i in range(5):
        await store.append_message(cid, "user", f"msg {i}")
    history = await store.recent_messages(cid, limit=2)
    assert [m["content"] for m in history] == ["msg 3", "msg 4"]


async def test_version_fully_indexed_requires_embedding(store, vector):
    aid = await store.upsert_act(Act(None, "RT I TEST 6", "Kuues", None, "general", "seadus"))
    vid = await store.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h"))
    pid = await store.insert_provision(Provision(None, vid, "6", "section", "embeditav", None, None))
    assert await store.version_fully_indexed(vid) is False
    await vector.upsert(pid, [0.01] * 1024)
    assert await store.version_fully_indexed(vid) is True


async def test_ingested_global_ids_requires_full_indexing(store, vector):
    aid = await store.upsert_act(Act(None, "RT I TEST 7", "Seitsmes", None, "general", "seadus"))
    vid = await store.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h",
                                                     source_global_id=555777))
    pid = await store.insert_provision(Provision(None, vid, "7", "section", "seitse", None, None))
    assert 555777 not in await store.ingested_global_ids()
    await vector.upsert(pid, [0.02] * 1024)
    assert 555777 in await store.ingested_global_ids()


async def test_delete_provisions_for_version_clears_rows(store):
    aid = await store.upsert_act(Act(None, "RT I TEST 8", "Kaheksas", None, "general", "seadus"))
    vid = await store.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h"))
    await store.insert_provision(Provision(None, vid, "8", "section", "kaheksa", None, None))
    await store.delete_provisions_for_version(vid)
    assert await store.provisions_as_of("RT I TEST 8", date(2021, 1, 1)) == []


async def test_index_act_self_heals_partial_previous_attempt(store, vector):
    from lawboi.ingest.service import IngestService
    from lawboi.domain.models import Chunk

    class StubEmbedder:
        def embed_passages(self, texts):
            return [[0.03] * 1024 for _ in texts]

    svc = IngestService(store, vector, StubEmbedder())
    act = Act(None, "RT I TEST 9", "Uheksas", None, "general", "seadus")
    version = ActVersion(None, 0, date(2000, 1, 1), None, "u", "h")

    # Simulate a prior run interrupted right after the act_version was
    # created and one provision inserted, before any embedding was written.
    act_id = await store.upsert_act(act)
    version.act_id = act_id
    version_id = await store.upsert_act_version(version)
    await store.insert_provision(Provision(None, version_id, "stale", "section", "vana", None, None))

    provisions = [Provision(None, 0, "9", "section", "uus", None, None)]
    chunks = [Chunk(None, 0, "9", "uus", {"eli": "RT I TEST 9"})]
    await svc.index_act(act, version, provisions, chunks)

    remaining = await store.provisions_as_of("RT I TEST 9", date(2021, 1, 1))
    assert [p.section_num for p in remaining] == ["9"]
    assert await store.version_fully_indexed(version_id) is True
