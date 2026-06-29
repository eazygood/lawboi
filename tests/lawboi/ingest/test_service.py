from datetime import date
from lawboi.ingest.service import IngestService
from lawboi.domain.models import Act, ActVersion, Provision, Chunk
from tests.lawboi.fakes import InMemoryStructuredStore, InMemoryVectorStore


class StubEmbedder:
    def embed_passage(self, text): return [0.1]


def test_index_act_writes_store_and_vector():
    store, vector = InMemoryStructuredStore(), InMemoryVectorStore()
    svc = IngestService(store, vector, StubEmbedder())
    act = Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus")
    version = ActVersion(None, 0, date(2020, 1, 1), None, "u", "h")
    provisions = [Provision(None, 0, "1", "section", "reguleerimisala", None, None)]
    chunks = [Chunk(None, 0, "1", "reguleerimisala", {"eli": "RT I 2009, 5, 35"})]
    svc.index_act(act, version, provisions, chunks)
    assert store.fts_search("reguleerimisala", date(2021, 1, 1))
    assert vector.query([0.1], 5, date(2021, 1, 1))


def test_index_act_skips_when_version_already_populated():
    store, vector = InMemoryStructuredStore(), InMemoryVectorStore()
    svc = IngestService(store, vector, StubEmbedder())
    act = Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus")
    version = ActVersion(None, 0, date(2020, 1, 1), None, "u", "h")
    p = [Provision(None, 0, "1", "section", "x", None, None)]
    c = [Chunk(None, 0, "1", "x", {})]
    svc.index_act(act, version, p, c)
    svc.index_act(act, version, p, c)  # second call must be a no-op
    assert len(store.fts_search("x", date(2021, 1, 1))) == 1


def test_index_act_records_global_id_in_skip_set():
    store, vector = InMemoryStructuredStore(), InMemoryVectorStore()
    svc = IngestService(store, vector, StubEmbedder())
    act = Act(None, "13198023", "TLS", None, "general", "seadus")
    version = ActVersion(None, 0, date(2020, 1, 1), None, "u", "h",
                         source_global_id=13198023)
    p = [Provision(None, 0, "1", "section", "x", None, None)]
    c = [Chunk(None, 0, "1", "x", {})]
    svc.index_act(act, version, p, c)
    assert store.ingested_global_ids() == {13198023}


def test_new_version_closes_prior_open_version():
    store, vector = InMemoryStructuredStore(), InMemoryVectorStore()
    svc = IngestService(store, vector, StubEmbedder())
    act = Act(None, "13198023", "TLS", None, "general", "seadus")
    old = ActVersion(None, 0, date(2020, 1, 1), None, "u", "h1",
                     source_global_id=100)
    new = ActVersion(None, 0, date(2024, 6, 1), None, "u", "h2",
                     source_global_id=200)
    svc.index_act(act, old, [Provision(None, 0, "1", "section", "old text", None, None)],
                  [Chunk(None, 0, "1", "old text", {})])
    svc.index_act(act, new, [Provision(None, 0, "1", "section", "new text", None, None)],
                  [Chunk(None, 0, "1", "new text", {})])
    # As of today only the new version is in force.
    asof = store.provisions_as_of("13198023", date(2024, 7, 1))
    assert [p.text_et for p in asof] == ["new text"]
    versions = {v.source_global_id: v for v in store.list_act_versions("13198023")}
    assert versions[100].effective_to == date(2024, 5, 31)
    assert versions[200].effective_to is None
