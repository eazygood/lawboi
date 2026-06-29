from datetime import date
from lawboi.domain.models import Act, ActVersion, Provision
from lawboi.domain.dto import VectorHit, ActMeta, RawAct
from tests.lawboi.fakes import (
    FakeLLMProvider, InMemoryVectorStore, InMemoryStructuredStore, FakeLawSource,
)


def test_fake_llm_returns_scripted():
    llm = FakeLLMProvider(responses=["hello"])
    assert llm.complete("anything") == "hello"
    assert llm.calls == ["anything"]


def test_inmemory_vector_roundtrip():
    v = InMemoryVectorStore()
    v.upsert(1, [0.1])
    hits = v.query([0.1], n_results=5, as_of=date(2021, 1, 1))
    assert hits and isinstance(hits[0], VectorHit) and hits[0].provision_id == 1


def test_inmemory_structured_write_then_read():
    s = InMemoryStructuredStore()
    act_id = s.upsert_act(Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus"))
    vid = s.upsert_act_version(ActVersion(None, act_id, date(2020, 1, 1), None, "u", "h"))
    assert s.version_has_provisions(vid) is False
    s.insert_provision(Provision(None, vid, "5", "section", "tekst reguleerimisala", None))
    assert s.version_has_provisions(vid) is True
    assert s.fts_search("reguleerimisala", date(2021, 1, 1))


def test_fake_law_source():
    src = FakeLawSource(
        acts=[ActMeta(123, "TLS", None, None)],
        raw={123: RawAct(123, b"<x/>", "u")},
    )
    assert src.search("TLS")[0].global_id == 123
    assert src.fetch(123).xml == b"<x/>"
    assert [m.global_id for m in src.iter_corpus(("seadus",))] == [123]
