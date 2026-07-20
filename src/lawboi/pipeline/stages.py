import asyncio
import logging
import re
from datetime import date
from typing import Optional, Protocol, runtime_checkable

from lawboi.answer.citations import detect_language
from lawboi.pipeline.context import RetrievalContext
from lawboi.ports.vector_store import VectorStore
from lawboi.ports.structured_store import StructuredStore
from lawboi.ports.llm import LLMProvider

log = logging.getLogger(__name__)

_DENSE_N = 20      # candidates fetched by DenseSearch
_AUGMENT_N = 10    # candidates fetched by ProceduralAugment and StepBackExpand


@runtime_checkable
class RetrievalStage(Protocol):
    async def __call__(self, ctx: RetrievalContext) -> RetrievalContext: ...


def is_citation_query(query: str) -> bool:
    return bool(re.search(r"§\s*\d+", query))


def _extract_eli(query: str) -> Optional[str]:
    m = re.search(r"RT\s+[IVX]+[\s,][\d\s,\.]+", query)
    return m.group().strip() if m else None


def _extract_title_query(query: str) -> str:
    cleaned = re.sub(r"§\s*\d+[a-z]?", "", query)
    cleaned = re.sub(r"\d{4}-\d{2}-\d{2}", "", cleaned)
    return cleaned.strip()


def _to_provision_dict(p) -> dict:
    return {"provision_id": p.provision_id, "section_num": p.section_num,
            "text": p.text, "metadata": p.metadata}


class CitationShortCircuit:
    """Exact §-lookup; if it matches, mark the context done so later stages skip."""
    def __init__(self, store: StructuredStore):
        self._store = store

    async def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if not is_citation_query(ctx.query):
            return ctx
        m = re.search(r"§\s*(\d+[a-z]?)", ctx.query)
        if not m:
            return ctx
        rows = await self._store.exact_lookup(
            section_num=m.group(1), as_of=ctx.as_of, limit=ctx.config.limit,
            eli=_extract_eli(ctx.query), title_query=_extract_title_query(ctx.query) or None)
        ctx.add_all([_to_provision_dict(r) for r in rows])
        ctx.done = True
        return ctx


_TRANSLATE_PROMPT = (
    "Translate the following legal question into Estonian. "
    "Preserve section references (e.g. \"§ 299\") and numbers exactly. "
    "Reply with ONLY the Estonian translation, nothing else.\n\n"
    "Input: {query}"
)


class QueryTranslation:
    """Translates a non-Estonian query into Estonian before retrieval, since
    the corpus (FTS index and passage embeddings) is Estonian-only and
    multilingual dense search alone is not reliable enough to rank the
    correct provision for a non-Estonian query (verified: an English query
    ranked the correct provision 1462nd out of ~160k candidates). Runs
    best-effort like StepBackExpand: on timeout or LLM error, leaves
    ctx.query unchanged rather than failing the request.
    """
    def __init__(self, llm: Optional[LLMProvider]):
        self._llm = llm

    async def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if ctx.done or self._llm is None or detect_language(ctx.query) == "et":
            return ctx
        try:
            raw = await asyncio.wait_for(
                self._llm.complete(_TRANSLATE_PROMPT.format(query=ctx.query)),
                timeout=ctx.config.query_translation_timeout_s)
            translated = raw.strip()
            if translated:
                ctx.query = translated
        except asyncio.TimeoutError:
            log.warning("Query translation timed out after %.1fs, skipping",
                        ctx.config.query_translation_timeout_s)
        except Exception:
            log.warning("Query translation failed, skipping", exc_info=True)
        return ctx


class DenseSearch:
    """Returns its hits rather than mutating ctx, so ParallelSearch can run
    it concurrently with the other search stages."""
    def __init__(self, vector: VectorStore, embedder):
        self._vector = vector
        self._embedder = embedder

    async def __call__(self, ctx: RetrievalContext) -> list[dict]:
        if ctx.done:
            return []
        emb = await asyncio.to_thread(self._embedder.embed_query, ctx.query)
        hits = await self._vector.query(emb, n_results=_DENSE_N, as_of=ctx.as_of)
        return [_to_provision_dict(h) for h in hits]


class SparseSearch:
    def __init__(self, store: StructuredStore):
        self._store = store

    async def __call__(self, ctx: RetrievalContext) -> list[dict]:
        if ctx.done:
            return []
        rows = await self._store.fts_search(ctx.query, ctx.as_of)
        return [_to_provision_dict(r) for r in rows]


class ProceduralAugment:
    """Second pass over a query augmented with procedural terms (remedies/deadlines)."""
    def __init__(self, vector: VectorStore, embedder, store: StructuredStore):
        self._vector = vector
        self._embedder = embedder
        self._store = store

    async def __call__(self, ctx: RetrievalContext) -> list[dict]:
        if ctx.done:
            return []
        q = f"{ctx.query} {ctx.config.procedural_terms}"
        emb = await asyncio.to_thread(self._embedder.embed_query, q)
        hits, rows = await asyncio.gather(
            self._vector.query(emb, n_results=_AUGMENT_N, as_of=ctx.as_of),
            self._store.fts_search(q, ctx.as_of),
        )
        return [_to_provision_dict(h) for h in hits] + [_to_provision_dict(r) for r in rows]


def _rrf_merge(ranked_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion: combine several independently-ranked hit lists
    into one, using each hit's rank within its own list rather than raw scores
    (which aren't comparable across a vector store's cosine similarity and a
    full-text search's ts_rank). Needed because Rerank is a no-op without a
    configured reranker, making this the only ranking signal in that case."""
    scores: dict[int, float] = {}
    first_seen: dict[int, dict] = {}
    for hits in ranked_lists:
        for rank, hit in enumerate(hits):
            pid = hit["provision_id"]
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank + 1)
            first_seen.setdefault(pid, hit)
    return sorted(first_seen.values(), key=lambda h: scores[h["provision_id"]], reverse=True)


class ParallelSearch:
    """Runs independent hit-returning stages concurrently, then merges their
    results into ctx in a single-threaded step once all have completed."""
    def __init__(self, stages: list):
        self._stages = stages

    async def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if ctx.done:
            return ctx
        results = await asyncio.gather(*(stage(ctx) for stage in self._stages))
        ctx.add_all(_rrf_merge(results))
        return ctx


_STEP_BACK_PROMPT = (
    "You are a legal research assistant for Estonian law. "
    "Given the user's specific question, generate a single broader, more abstract "
    "legal query that would retrieve the general legal provisions governing this topic. "
    "Reply with ONLY the abstracted query, nothing else. "
    "Write the query in the same language as the input.\n\n"
    "Example:\n"
    "Input: Kas tööandja võib mind haiguslehe ajal vallandada?\n"
    "Output: Töölepingu ülesütlemise piirangud ja keelud\n\n"
    "Input: What happens if I don't pay corporate income tax on time?\n"
    "Output: Consequences and penalties for late payment of corporate income tax\n\n"
    "Input: {query}"
)


class StepBackExpand:
    """Generate an abstracted query via the LLM and retrieve against it.

    Bounded by ctx.config.step_back_timeout_s: on timeout or LLM error, logs
    and returns ctx unchanged so a slow/unavailable LLM never blocks the
    final answer on this optional expansion step.
    """
    def __init__(self, vector: VectorStore, embedder, store: StructuredStore,
                 llm: Optional[LLMProvider]):
        self._vector = vector
        self._embedder = embedder
        self._store = store
        self._llm = llm

    async def _generate_and_search(self, ctx: RetrievalContext) -> None:
        assert self._llm is not None  # __call__ already returned early if None
        raw = await self._llm.complete(_STEP_BACK_PROMPT.format(query=ctx.query))
        step_back = raw.strip()
        if not step_back or step_back == ctx.query:
            return
        log.info("Step-back query: %s -> %s", ctx.query, step_back)
        emb = await asyncio.to_thread(self._embedder.embed_query, step_back)
        hits = await self._vector.query(emb, n_results=_AUGMENT_N, as_of=ctx.as_of)
        ctx.add_all([_to_provision_dict(h) for h in hits])
        rows = await self._store.fts_search(step_back, ctx.as_of)
        ctx.add_all([_to_provision_dict(r) for r in rows])

    async def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if ctx.done or not ctx.config.step_back_enabled or self._llm is None:
            return ctx
        try:
            await asyncio.wait_for(
                self._generate_and_search(ctx), timeout=ctx.config.step_back_timeout_s)
        except asyncio.TimeoutError:
            log.warning("Step-back timed out after %.1fs, skipping",
                       ctx.config.step_back_timeout_s)
        except Exception:
            log.warning("Step-back generation failed, skipping", exc_info=True)
        return ctx


class Rerank:
    def __init__(self, reranker=None):
        self._reranker = reranker

    async def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if self._reranker is None or not ctx.candidates:
            return ctx
        from llama_index.core.schema import NodeWithScore, TextNode, QueryBundle
        nodes = [NodeWithScore(node=TextNode(text=c["text"], id_=str(c["provision_id"])))
                 for c in ctx.candidates]
        ranked = self._reranker.postprocess_nodes(nodes, QueryBundle(ctx.query))
        order = {int(n.node.id_): i for i, n in enumerate(ranked)}
        ctx.candidates.sort(key=lambda c: order.get(c["provision_id"], len(order)))
        return ctx
