from datetime import date
from lawboi.pipeline.context import RetrievalContext, RetrievalConfig


def test_context_defaults():
    ctx = RetrievalContext(query="q", as_of=date(2021, 1, 1))
    assert ctx.candidates == []
    assert ctx.config.limit == 5
    assert ctx.config.procedural_terms


def test_seen_tracks_provision_ids():
    ctx = RetrievalContext(query="q", as_of=date(2021, 1, 1))
    ctx.add({"provision_id": 1, "section_num": "5", "text": "t", "metadata": {}})
    ctx.add({"provision_id": 1, "section_num": "5", "text": "t", "metadata": {}})
    assert len(ctx.candidates) == 1  # dedup by provision_id
