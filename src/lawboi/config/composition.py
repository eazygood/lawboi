from dataclasses import dataclass
from typing import Optional

from lawboi.config.settings import Settings
from lawboi.pipeline.retrieval import RetrievalService
from lawboi.pipeline.stages import (
    CitationShortCircuit, DenseSearch, SparseSearch, ProceduralAugment,
    StepBackExpand, Merge, Rerank,
)
from lawboi.answer.service import AnswerService
from lawboi.ingest.service import IngestService


@dataclass
class Container:
    retrieval: RetrievalService
    answer: AnswerService
    ingest: IngestService
    store: object = None   # StructuredStore, exposed for the read-only acts route


def build_pipeline(store, vector, embedder, llm, reranker):
    return [
        CitationShortCircuit(store),
        DenseSearch(vector, embedder),
        SparseSearch(store),
        ProceduralAugment(vector, embedder, store),
        StepBackExpand(vector, embedder, store, llm),
        Merge(),
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


def build_container(settings: Settings) -> Container:
    from lawboi.adapters.structured.pool import make_pool
    from lawboi.adapters.structured.postgres import PostgresStore
    from lawboi.adapters.vector.pgvector import PostgresVectorStore
    from lawboi.adapters.llm.factory import build_llm
    from lawboi.ingest.embedder import Embedder

    pool = make_pool(settings.database_url, settings.db_pool_min, settings.db_pool_max)
    store = PostgresStore(pool)
    vector = PostgresVectorStore(pool)
    embedder = Embedder()
    llm = build_llm(settings.llm_model)
    reranker = _build_reranker(settings)

    stages = build_pipeline(store, vector, embedder, llm, reranker)
    return Container(
        retrieval=RetrievalService(stages, default_limit=5),
        answer=AnswerService(llm),
        ingest=IngestService(store, vector, embedder),
        store=store,
    )
