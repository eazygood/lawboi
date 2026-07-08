from datetime import date
from lawboi.ports.llm import LLMProvider
from lawboi.ports.vector_store import VectorStore
from lawboi.ports.structured_store import StructuredStore
from lawboi.ports.law_source import LawSource


def test_llm_protocol_satisfied():
    class Stub:
        name = "stub"
        async def complete(self, prompt: str) -> str: return "x"
        async def complete_structured(self, prompt: str, output_cls): return output_cls()
    assert isinstance(Stub(), LLMProvider)


def test_vector_protocol_satisfied():
    class Stub:
        async def query(self, embedding, n_results, as_of): return []
        async def upsert(self, provision_id, embedding): ...
        async def batch_upsert(self, pairs): ...
    assert isinstance(Stub(), VectorStore)


def test_structured_protocol_has_methods():
    assert hasattr(StructuredStore, "fts_search")
    assert hasattr(StructuredStore, "exact_lookup")


def test_law_source_protocol_has_methods():
    assert hasattr(LawSource, "search")
    assert hasattr(LawSource, "fetch")
    assert hasattr(LawSource, "iter_corpus")
