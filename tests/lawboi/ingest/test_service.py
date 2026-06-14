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
    assert vector.query([0.1], 5)


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
