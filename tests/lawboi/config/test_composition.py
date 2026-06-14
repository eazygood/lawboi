from lawboi.config.composition import Container, build_pipeline
from lawboi.pipeline.stages import (
    CitationShortCircuit, DenseSearch, SparseSearch, ProceduralAugment,
    StepBackExpand, Merge, Rerank,
)
from tests.lawboi.fakes import (
    FakeLLMProvider, InMemoryVectorStore, InMemoryStructuredStore,
)


class StubEmbedder:
    def embed_query(self, text): return [0.1]
    def embed_passage(self, text): return [0.1]


def test_build_pipeline_order():
    stages = build_pipeline(
        store=InMemoryStructuredStore(), vector=InMemoryVectorStore(),
        embedder=StubEmbedder(), llm=FakeLLMProvider(), reranker=None)
    types = [type(s) for s in stages]
    assert types == [CitationShortCircuit, DenseSearch, SparseSearch,
                     ProceduralAugment, StepBackExpand, Merge, Rerank]


def test_container_holds_services():
    from lawboi.pipeline.retrieval import RetrievalService
    from lawboi.answer.service import AnswerService
    from lawboi.ingest.service import IngestService
    c = Container(
        retrieval=RetrievalService([], default_limit=5),
        answer=AnswerService(FakeLLMProvider()),
        ingest=IngestService(InMemoryStructuredStore(), InMemoryVectorStore(), StubEmbedder()),
    )
    assert c.retrieval and c.answer and c.ingest
