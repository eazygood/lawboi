import logging
import re
from datetime import date
from typing import Optional, Protocol, runtime_checkable

from lawboi.pipeline.context import RetrievalContext
from lawboi.ports.vector_store import VectorStore
from lawboi.ports.structured_store import StructuredStore
from lawboi.ports.llm import LLMProvider

log = logging.getLogger(__name__)


@runtime_checkable
class RetrievalStage(Protocol):
    def __call__(self, ctx: RetrievalContext) -> RetrievalContext: ...


def is_citation_query(query: str) -> bool:
    return bool(re.search(r"§\s*\d+", query))


def _extract_eli(query: str) -> Optional[str]:
    m = re.search(r"RT\s+[IVX]+[\s,][\d\s,\.]+", query)
    return m.group().strip() if m else None


def _extract_title_query(query: str) -> str:
    cleaned = re.sub(r"§\s*\d+[a-z]?", "", query)
    cleaned = re.sub(r"\d{4}-\d{2}-\d{2}", "", cleaned)
    return cleaned.strip()


def _hit_to_dict(hit) -> dict:
    return {"provision_id": hit.provision_id, "section_num": hit.section_num,
            "text": hit.text, "metadata": hit.metadata}


def _rp_to_dict(rp) -> dict:
    return {"provision_id": rp.provision_id, "section_num": rp.section_num,
            "text": rp.text, "metadata": rp.metadata}


class CitationShortCircuit:
    """Exact §-lookup; if it matches, mark the context done so later stages skip."""
    def __init__(self, store: StructuredStore):
        self._store = store

    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if not is_citation_query(ctx.query):
            return ctx
        m = re.search(r"§\s*(\d+[a-z]?)", ctx.query)
        if not m:
            return ctx
        rows = self._store.exact_lookup(
            section_num=m.group(1), as_of=ctx.as_of, limit=ctx.config.limit,
            eli=_extract_eli(ctx.query), title_query=_extract_title_query(ctx.query) or None)
        ctx.add_all([_rp_to_dict(r) for r in rows])
        ctx._done = True
        return ctx


class DenseSearch:
    def __init__(self, vector: VectorStore, embedder):
        self._vector = vector
        self._embedder = embedder

    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if getattr(ctx, "_done", False):
            return ctx
        emb = self._embedder.embed_query(ctx.query)
        ctx.add_all([_hit_to_dict(h) for h in self._vector.query(emb, n_results=20)])
        return ctx


class SparseSearch:
    def __init__(self, store: StructuredStore):
        self._store = store

    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if getattr(ctx, "_done", False):
            return ctx
        ctx.add_all([_rp_to_dict(r) for r in self._store.fts_search(ctx.query, ctx.as_of)])
        return ctx


class ProceduralAugment:
    """Second pass over a query augmented with procedural terms (remedies/deadlines)."""
    def __init__(self, vector: VectorStore, embedder, store: StructuredStore):
        self._vector = vector
        self._embedder = embedder
        self._store = store

    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if getattr(ctx, "_done", False):
            return ctx
        q = f"{ctx.query} {ctx.config.procedural_terms}"
        emb = self._embedder.embed_query(q)
        ctx.add_all([_hit_to_dict(h) for h in self._vector.query(emb, n_results=10)])
        ctx.add_all([_rp_to_dict(r) for r in self._store.fts_search(q, ctx.as_of)])
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
    """Generate an abstracted query via the LLM and retrieve against it."""
    def __init__(self, vector: VectorStore, embedder, store: StructuredStore,
                 llm: Optional[LLMProvider]):
        self._vector = vector
        self._embedder = embedder
        self._store = store
        self._llm = llm

    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if getattr(ctx, "_done", False) or not ctx.config.step_back_enabled or self._llm is None:
            return ctx
        try:
            step_back = self._llm.complete(_STEP_BACK_PROMPT.format(query=ctx.query)).strip()
        except Exception:
            log.warning("Step-back generation failed, skipping", exc_info=True)
            return ctx
        if not step_back or step_back == ctx.query:
            return ctx
        log.info("Step-back query: %s -> %s", ctx.query, step_back)
        emb = self._embedder.embed_query(step_back)
        ctx.add_all([_hit_to_dict(h) for h in self._vector.query(emb, n_results=10)])
        ctx.add_all([_rp_to_dict(r) for r in self._store.fts_search(step_back, ctx.as_of)])
        return ctx


class Merge:
    """Dedup is already handled by RetrievalContext.add; Merge is the explicit
    ordering boundary and a hook for future scoring."""
    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        return ctx


class Rerank:
    def __init__(self, reranker=None):
        self._reranker = reranker

    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if self._reranker is None or not ctx.candidates:
            return ctx
        from llama_index.core.schema import NodeWithScore, TextNode, QueryBundle
        nodes = [NodeWithScore(node=TextNode(text=c["text"], id_=str(c["provision_id"])))
                 for c in ctx.candidates]
        ranked = self._reranker.postprocess_nodes(nodes, QueryBundle(ctx.query))
        order = {int(n.node.id_): i for i, n in enumerate(ranked)}
        ctx.candidates.sort(key=lambda c: order.get(c["provision_id"], len(order)))
        return ctx
