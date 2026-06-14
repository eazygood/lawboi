from datetime import date
from lawboi.pipeline.retrieval import RetrievalService, run_pipeline
from lawboi.pipeline.context import RetrievalContext
from lawboi.pipeline.stages import DenseSearch, Merge
from tests.lawboi.fakes import InMemoryVectorStore


class StubEmbedder:
    def embed_query(self, text): return [0.1]


def test_run_pipeline_threads_context():
    v = InMemoryVectorStore()
    v.upsert(1, [0.1])
    stages = [DenseSearch(v, StubEmbedder()), Merge()]
    ctx = run_pipeline(stages, query="q", as_of=date(2021, 1, 1))
    assert ctx.candidates[0]["provision_id"] == 1


def test_service_returns_limited_dicts():
    v = InMemoryVectorStore()
    for i in range(10):
        v.upsert(i, [0.1])
    svc = RetrievalService([DenseSearch(v, StubEmbedder()), Merge()], default_limit=5)
    out = svc.retrieve("q")
    assert len(out) == 5
    assert out[0]["provision_id"] == 0
