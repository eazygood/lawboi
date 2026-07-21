from lawboi.config.composition import Container, build_pipeline, _compute_cache_version
from lawboi.pipeline.stages import (
    CitationShortCircuit, ParallelSearch, QueryTranslation, StepBackExpand, Rerank,
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
    assert types == [
        CitationShortCircuit, QueryTranslation, ParallelSearch, StepBackExpand, Rerank,
    ]


def test_container_holds_services():
    from lawboi.pipeline.retrieval import RetrievalService
    from lawboi.answer.service import AnswerService
    from lawboi.ingest.service import IngestService
    c = Container(
        retrieval=RetrievalService([], default_limit=5),
        answer=AnswerService(FakeLLMProvider()),
        ingest=IngestService(InMemoryStructuredStore(), InMemoryVectorStore(), StubEmbedder()),
        embedder=StubEmbedder(),
        cache=None,
        settings=None,
    )
    assert c.retrieval and c.answer and c.ingest
    assert c.embedder is not None


def test_compute_cache_version_is_deterministic():
    v1 = _compute_cache_version("prompt text", "gpt-4o", "")
    v2 = _compute_cache_version("prompt text", "gpt-4o", "")
    assert v1 == v2


def test_compute_cache_version_changes_with_prompt():
    v1 = _compute_cache_version("prompt A", "gpt-4o", "")
    v2 = _compute_cache_version("prompt B", "gpt-4o", "")
    assert v1 != v2


def test_compute_cache_version_changes_with_model():
    v1 = _compute_cache_version("prompt", "gpt-4o", "")
    v2 = _compute_cache_version("prompt", "claude-opus", "")
    assert v1 != v2


def test_compute_cache_version_changes_with_suffix():
    v1 = _compute_cache_version("prompt", "gpt-4o", "")
    v2 = _compute_cache_version("prompt", "gpt-4o", "bump-1")
    assert v1 != v2
