import asyncio
from datetime import date
from typing import TypeVar

from pydantic import BaseModel

from lawboi.pipeline.context import RetrievalConfig, RetrievalContext
from lawboi.pipeline.stages import (
    CitationShortCircuit, DenseSearch, SparseSearch, ParallelSearch, StepBackExpand,
    Rerank, is_citation_query,
)
from lawboi.domain.models import Act, ActVersion, Provision
from tests.lawboi.fakes import InMemoryVectorStore, InMemoryStructuredStore


Model = TypeVar("Model", bound=BaseModel)


class StubEmbedder:
    def embed_query(self, text): return [0.1]


async def _store_with_provision():
    s = InMemoryStructuredStore()
    aid = await s.upsert_act(Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus"))
    vid = await s.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h"))
    await s.insert_provision(Provision(None, vid, "97", "section", "etteteatamise tähtaeg", None))
    return s


def test_is_citation_query():
    assert is_citation_query("§ 97 töölepingu seadus")
    assert not is_citation_query("notice period")


async def test_dense_search_populates_candidates():
    v = InMemoryVectorStore()
    await v.upsert(1, [0.1])
    ctx = RetrievalContext(query="notice", as_of=date(2021, 1, 1))
    hits = await DenseSearch(v, StubEmbedder())(ctx)
    assert hits[0]["provision_id"] == 1


async def test_sparse_search_uses_fts():
    ctx = RetrievalContext(query="tähtaeg", as_of=date(2021, 1, 1))
    hits = await SparseSearch(await _store_with_provision())(ctx)
    assert any(c["section_num"] == "97" for c in hits)


async def test_rerank_noop_without_reranker():
    ctx = RetrievalContext(query="q", as_of=date(2021, 1, 1))
    ctx.add({"provision_id": 1, "section_num": "1", "text": "t", "metadata": {}})
    await Rerank(reranker=None)(ctx)
    assert len(ctx.candidates) == 1


async def test_citation_shortcircuit_sets_flag():
    ctx = RetrievalContext(query="§ 97 töölepingu seadus", as_of=date(2021, 1, 1))
    out = await CitationShortCircuit(await _store_with_provision())(ctx)
    assert out.candidates and out.candidates[0]["section_num"] == "97"
    assert out.done is True


async def test_parallel_search_merges_hits_from_all_stages():
    v = InMemoryVectorStore()
    await v.upsert(1, [0.1])
    ctx = RetrievalContext(query="tähtaeg", as_of=date(2021, 1, 1))
    stage = ParallelSearch([
        DenseSearch(v, StubEmbedder()),
        SparseSearch(await _store_with_provision()),
    ])
    out = await stage(ctx)
    ids = {c["provision_id"] for c in out.candidates}
    assert 1 in ids
    assert any(c["section_num"] == "97" for c in out.candidates)


async def test_parallel_search_skips_when_done():
    ctx = RetrievalContext(query="q", as_of=date(2021, 1, 1), done=True)
    stage = ParallelSearch([DenseSearch(InMemoryVectorStore(), StubEmbedder())])
    out = await stage(ctx)
    assert out.candidates == []


def _hit(pid):
    return {"provision_id": pid, "section_num": str(pid), "text": "t", "metadata": {}}


class _StubStage:
    def __init__(self, hits):
        self._hits = hits

    async def __call__(self, ctx):
        return self._hits


async def test_parallel_search_ranks_hits_found_by_multiple_stages_higher():
    # P1 is top-ranked by one stage only; P2 is second-ranked by both stages.
    # Without rank fusion, insertion order would put P1 before P2 since P1 is
    # rank 0 of the first stage. RRF should rank P2 above P1: it's corroborated
    # by both stages, which is exactly the signal SparseSearch/ProceduralAugment
    # are meant to contribute when there's no reranker to otherwise combine them.
    ctx = RetrievalContext(query="q", as_of=date(2021, 1, 1))
    stage = ParallelSearch([
        _StubStage([_hit(1), _hit(2)]),
        _StubStage([_hit(3), _hit(2)]),
    ])
    out = await stage(ctx)
    ids = [c["provision_id"] for c in out.candidates]
    assert ids.index(2) < ids.index(1)


class SlowLLM:
    name = "slow"

    async def complete(self, prompt: str) -> str:
        await asyncio.sleep(10)
        return "never"

    async def complete_structured(self, prompt: str, output_cls: type[Model]) -> Model:
        await asyncio.sleep(10)
        return None  # type: ignore[return-value]


async def test_step_back_expand_times_out_and_returns_ctx():
    config = RetrievalConfig(step_back_timeout_s=0.01)
    ctx = RetrievalContext(query="q", as_of=date(2021, 1, 1), config=config)
    stage = StepBackExpand(InMemoryVectorStore(), StubEmbedder(),
                            await _store_with_provision(), SlowLLM())
    out = await stage(ctx)
    assert out.candidates == []
    assert out.done is False
