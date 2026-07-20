from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from lawboi.config.settings import Settings
from lawboi.pipeline.retrieval import RetrievalService
from lawboi.pipeline.stages import (
    CitationShortCircuit, DenseSearch, SparseSearch, ProceduralAugment,
    ParallelSearch, QueryTranslation, StepBackExpand, Rerank,
)
from lawboi.answer.service import AnswerService
from lawboi.answer.moderation import ModerationService
from lawboi.ingest.service import IngestService
from lawboi.ports.structured_store import StructuredStore
from lawboi.ports.answer_cache import AnswerCache

if TYPE_CHECKING:
    from lawboi.ingest.embedder import Embedder


@dataclass
class Container:
    retrieval: RetrievalService
    answer: AnswerService
    ingest: IngestService
    moderation: Optional[ModerationService] = None
    store: Optional[StructuredStore] = None
    embedder: Optional["Embedder"] = None
    cache: Optional[AnswerCache] = None
    settings: Optional[Settings] = None


def build_pipeline(store, vector, embedder, llm, reranker, llm_fast=None):
    return [
        CitationShortCircuit(store),
        QueryTranslation(llm_fast or llm),
        ParallelSearch([
            DenseSearch(vector, embedder),
            SparseSearch(store),
            ProceduralAugment(vector, embedder, store),
        ]),
        StepBackExpand(vector, embedder, store, llm_fast or llm),
        Rerank(reranker),
    ]


def _build_reranker(settings: Settings):
    if not settings.cohere_api_key:
        return None
    try:
        from llama_index.postprocessor.cohere_rerank import CohereRerank
    except ImportError:
        return None
    return CohereRerank(api_key=settings.cohere_api_key, top_n=5)


async def build_container(settings: Settings) -> Container:
    from lawboi.adapters.structured.pool import make_pool
    from lawboi.adapters.structured.postgres import PostgresStore
    from lawboi.adapters.vector.pgvector import PostgresVectorStore
    from lawboi.adapters.vector.answer_cache import PostgresAnswerCache
    from lawboi.adapters.llm.factory import build_llm, resolve_fast_model
    from lawboi.ingest.embedder import Embedder

    pool = await make_pool(settings.database_url, settings.db_pool_min, settings.db_pool_max)
    store = PostgresStore(pool)
    vector = PostgresVectorStore(pool)
    embedder = Embedder()
    cache = PostgresAnswerCache(
        pool, min_similarity=settings.cache_similarity_threshold,
        retention_days=settings.cache_retention_days,
    )
    llm = build_llm(settings.llm_model, max_tokens=settings.answer_max_tokens)
    fast_name = resolve_fast_model(settings.llm_fast_model)
    llm_fast = (
        build_llm(fast_name, max_tokens=settings.fast_max_tokens) if fast_name else llm
    )
    reranker = _build_reranker(settings)

    stages = build_pipeline(store, vector, embedder, llm, reranker, llm_fast=llm_fast)
    return Container(
        retrieval=RetrievalService(stages, default_limit=5),
        answer=AnswerService(
            llm,
            timeout_s=settings.answer_timeout_s,
            max_provision_chars=settings.max_provision_chars,
            max_history_chars=settings.max_history_chars,
        ),
        ingest=IngestService(store, vector, embedder),
        moderation=ModerationService(llm_fast, timeout_s=settings.moderation_timeout_s),
        store=store,
        embedder=embedder,
        cache=cache,
        settings=settings,
    )
