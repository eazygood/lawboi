from datetime import date
from lawboi.ingest.service import IngestService
from lawboi.domain.models import Act, ActVersion, Provision, Chunk
from tests.lawboi.fakes import InMemoryStructuredStore, InMemoryVectorStore


class StubEmbedder:
    def embed_passage(self, text): return [0.1]
    def embed_passages(self, texts): return [[0.1]] * len(texts)


async def test_index_act_writes_store_and_vector():
    store, vector = InMemoryStructuredStore(), InMemoryVectorStore()
    svc = IngestService(store, vector, StubEmbedder())
    act = Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus")
    version = ActVersion(None, 0, date(2020, 1, 1), None, "u", "h")
    provisions = [Provision(None, 0, "1", "section", "reguleerimisala", None, None)]
    chunks = [Chunk(None, 0, "1", "reguleerimisala", {"eli": "RT I 2009, 5, 35"})]
    await svc.index_act(act, version, provisions, chunks)
    assert await store.fts_search("reguleerimisala", date(2021, 1, 1))
    assert await vector.query([0.1], 5, date(2021, 1, 1))


async def test_index_act_skips_when_version_already_populated():
    store, vector = InMemoryStructuredStore(), InMemoryVectorStore()
    svc = IngestService(store, vector, StubEmbedder())
    act = Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus")
    version = ActVersion(None, 0, date(2020, 1, 1), None, "u", "h")
    p = [Provision(None, 0, "1", "section", "x", None, None)]
    c = [Chunk(None, 0, "1", "x", {})]
    await svc.index_act(act, version, p, c)
    await svc.index_act(act, version, p, c)  # second call must be a no-op
    assert len(await store.fts_search("x", date(2021, 1, 1))) == 1


async def test_index_act_records_global_id_in_skip_set():
    store, vector = InMemoryStructuredStore(), InMemoryVectorStore()
    svc = IngestService(store, vector, StubEmbedder())
    act = Act(None, "13198023", "TLS", None, "general", "seadus")
    version = ActVersion(None, 0, date(2020, 1, 1), None, "u", "h",
                         source_global_id=13198023)
    p = [Provision(None, 0, "1", "section", "x", None, None)]
    c = [Chunk(None, 0, "1", "x", {})]
    await svc.index_act(act, version, p, c)
    assert await store.ingested_global_ids() == {13198023}


async def test_new_version_closes_prior_open_version():
    store, vector = InMemoryStructuredStore(), InMemoryVectorStore()
    svc = IngestService(store, vector, StubEmbedder())
    act = Act(None, "13198023", "TLS", None, "general", "seadus")
    old = ActVersion(None, 0, date(2020, 1, 1), None, "u", "h1",
                     source_global_id=100)
    new = ActVersion(None, 0, date(2024, 6, 1), None, "u", "h2",
                     source_global_id=200)
    await svc.index_act(act, old, [Provision(None, 0, "1", "section", "old text", None, None)],
                        [Chunk(None, 0, "1", "old text", {})])
    await svc.index_act(act, new, [Provision(None, 0, "1", "section", "new text", None, None)],
                        [Chunk(None, 0, "1", "new text", {})])
    # As of today only the new version is in force.
    asof = await store.provisions_as_of("13198023", date(2024, 7, 1))
    assert [p.text_et for p in asof] == ["new text"]
    versions = {v.source_global_id: v for v in await store.list_act_versions("13198023")}
    assert versions[100].effective_to == date(2024, 5, 31)
    assert versions[200].effective_to is None


async def test_index_act_force_reinserts_when_fully_indexed():
    store, vector = InMemoryStructuredStore(), InMemoryVectorStore()
    svc = IngestService(store, vector, StubEmbedder())
    act = Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus")
    version = ActVersion(None, 0, date(2020, 1, 1), None, "u", "h")
    p_old = [Provision(None, 0, "1", "section", "old text", None, None)]
    c_old = [Chunk(None, 0, "1", "old text", {})]
    await svc.index_act(act, version, p_old, c_old)

    p_new = [Provision(None, 0, "1", "section", "new text", None, None, heading="Katseaeg")]
    c_new = [Chunk(None, 0, "1", "new text", {})]
    await svc.index_act(act, version, p_new, c_new, force=True)

    results = await store.fts_search("new", date(2021, 1, 1))
    assert len(results) == 1
    assert not await store.fts_search("old", date(2021, 1, 1))


async def test_index_act_uses_batch_embedding():
    """IngestService must call embed_passages (batch) not embed_passage (single)."""
    store, vector = InMemoryStructuredStore(), InMemoryVectorStore()

    class BatchTrackingEmbedder:
        def __init__(self):
            self.single_calls = 0
            self.batch_calls = 0

        def embed_passage(self, text):
            self.single_calls += 1
            return [0.1]

        def embed_passages(self, texts):
            self.batch_calls += 1
            return [[0.1]] * len(texts)

    embedder = BatchTrackingEmbedder()
    svc = IngestService(store, vector, embedder)
    act = Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus")
    version = ActVersion(None, 0, date(2020, 1, 1), None, "u", "h")
    provisions = [
        Provision(None, 0, str(i), "section", f"tekst {i}", None, None)
        for i in range(5)
    ]
    chunks = [Chunk(None, 0, str(i), f"tekst {i}", {}) for i in range(5)]
    await svc.index_act(act, version, provisions, chunks)

    assert embedder.single_calls == 0, "embed_passage (single) should not be called"
    assert embedder.batch_calls == 1, "embed_passages should be called exactly once"
