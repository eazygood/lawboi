from datetime import date
from lawboi.domain.models import Act, ActVersion, Provision
from lawboi.domain.dto import VectorHit, ActMeta, RawAct
from tests.lawboi.fakes import (
    FakeLLMProvider, InMemoryVectorStore, InMemoryStructuredStore, FakeLawSource,
)


async def test_fake_llm_returns_scripted():
    llm = FakeLLMProvider(responses=["hello"])
    assert await llm.complete("anything") == "hello"
    assert llm.calls == ["anything"]


async def test_inmemory_vector_roundtrip():
    v = InMemoryVectorStore()
    await v.upsert(1, [0.1])
    hits = await v.query([0.1], n_results=5, as_of=date(2021, 1, 1))
    assert hits and isinstance(hits[0], VectorHit) and hits[0].provision_id == 1


async def test_inmemory_structured_write_then_read():
    s = InMemoryStructuredStore()
    act_id = await s.upsert_act(Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus"))
    vid = await s.upsert_act_version(ActVersion(None, act_id, date(2020, 1, 1), None, "u", "h"))
    assert await s.version_fully_indexed(vid) is False
    await s.insert_provision(Provision(None, vid, "5", "section", "tekst reguleerimisala", None))
    assert await s.version_fully_indexed(vid) is True
    assert await s.fts_search("reguleerimisala", date(2021, 1, 1))


def test_fake_law_source():
    src = FakeLawSource(
        acts=[ActMeta(123, "TLS", None, None)],
        raw={123: RawAct(123, b"<x/>", "u")},
    )
    assert src.search("TLS")[0].global_id == 123
    assert src.fetch(123).xml == b"<x/>"
    assert [m.global_id for m in src.iter_corpus(("seadus",))] == [123]


async def test_ingested_global_ids_excludes_versions_without_provisions():
    s = InMemoryStructuredStore()
    act_id = await s.upsert_act(Act(None, "RT I TEST X", "X", None, "general", "seadus"))
    await s.upsert_act_version(ActVersion(None, act_id, date(2020, 1, 1), None, "u", "h",
                                          source_global_id=999))
    assert await s.ingested_global_ids() == set()


async def test_delete_provisions_for_version_removes_matching_only():
    s = InMemoryStructuredStore()
    a1 = await s.upsert_act(Act(None, "RT I TEST Y1", "Y1", None, "general", "seadus"))
    a2 = await s.upsert_act(Act(None, "RT I TEST Y2", "Y2", None, "general", "seadus"))
    v1 = await s.upsert_act_version(ActVersion(None, a1, date(2020, 1, 1), None, "u1", "h1"))
    v2 = await s.upsert_act_version(ActVersion(None, a2, date(2020, 1, 1), None, "u2", "h2"))
    await s.insert_provision(Provision(None, v1, "1", "section", "a", None))
    await s.insert_provision(Provision(None, v2, "1", "section", "b", None))
    await s.delete_provisions_for_version(v1)
    assert await s.version_fully_indexed(v1) is False
    assert await s.version_fully_indexed(v2) is True
