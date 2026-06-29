from datetime import date
from lawboi.pipeline.context import RetrievalContext
from lawboi.pipeline.stages import (
    CitationShortCircuit, DenseSearch, SparseSearch, Merge, Rerank, is_citation_query,
)
from lawboi.domain.models import Act, ActVersion, Provision
from tests.lawboi.fakes import InMemoryVectorStore, InMemoryStructuredStore


class StubEmbedder:
    def embed_query(self, text): return [0.1]


def _store_with_provision():
    s = InMemoryStructuredStore()
    aid = s.upsert_act(Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus"))
    vid = s.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h"))
    s.insert_provision(Provision(None, vid, "97", "section", "etteteatamise tähtaeg", None))
    return s


def test_is_citation_query():
    assert is_citation_query("§ 97 töölepingu seadus")
    assert not is_citation_query("notice period")


def test_dense_search_populates_candidates():
    v = InMemoryVectorStore()
    v.upsert(1, [0.1])
    ctx = RetrievalContext(query="notice", as_of=date(2021, 1, 1))
    DenseSearch(v, StubEmbedder())(ctx)
    assert ctx.candidates[0]["provision_id"] == 1


def test_sparse_search_uses_fts():
    ctx = RetrievalContext(query="tähtaeg", as_of=date(2021, 1, 1))
    SparseSearch(_store_with_provision())(ctx)
    assert any(c["section_num"] == "97" for c in ctx.candidates)


def test_merge_is_dedup_passthrough():
    ctx = RetrievalContext(query="q", as_of=date(2021, 1, 1))
    ctx.add({"provision_id": 1, "section_num": "1", "text": "t", "metadata": {}})
    Merge()(ctx)
    assert len(ctx.candidates) == 1


def test_rerank_noop_without_reranker():
    ctx = RetrievalContext(query="q", as_of=date(2021, 1, 1))
    ctx.add({"provision_id": 1, "section_num": "1", "text": "t", "metadata": {}})
    Rerank(reranker=None)(ctx)
    assert len(ctx.candidates) == 1


def test_citation_shortcircuit_sets_flag():
    ctx = RetrievalContext(query="§ 97 töölepingu seadus", as_of=date(2021, 1, 1))
    out = CitationShortCircuit(_store_with_provision())(ctx)
    assert out.candidates and out.candidates[0]["section_num"] == "97"
    assert out.done is True
