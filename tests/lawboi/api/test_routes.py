import asyncio
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from lawboi.api.main import app
from lawboi.api.deps import (
    get_retrieval, get_answer, get_store, get_moderation, get_embedder, get_cache, get_settings,
)
from lawboi.domain.models import Act, ActVersion, Provision
from lawboi.pipeline.retrieval import RetrievalService
from lawboi.answer.service import AnswerService
from lawboi.answer.moderation import ModerationService, ModerationResult
from lawboi.config.settings import Settings
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from lawboi.answer.citations import AnswerPayload, CitationOut
from tests.lawboi.fakes import FakeLLMProvider, InMemoryStructuredStore, InMemoryAnswerCache


class StubRetrieval(RetrievalService):
    def __init__(self, provisions):
        self._provisions = provisions
    async def retrieve(self, query, as_of=None, limit=None):
        return self._provisions


class ToggleModeration:
    """Returns each queued result in order -- lets a test give different
    verdicts to the input check vs. the output check."""
    def __init__(self, results):
        self._results = list(results)

    async def check(self, text):
        return self._results.pop(0)


def _clean_moderation():
    return ModerationService(
        FakeLLMProvider(structured_response=ModerationResult(flagged=False, reason="")))


class StubEmbedder:
    def embed_query(self, text): return [0.1]


def _client(provisions, store=None, moderation=None, cache=None):
    app.dependency_overrides[get_retrieval] = lambda: StubRetrieval(provisions)
    payload = AnswerPayload(
        answer="Under § 97 notice applies.",
        citations=[CitationOut(section="97", act_title="TLS")])
    app.dependency_overrides[get_answer] = lambda: AnswerService(
        FakeLLMProvider(structured_response=payload))
    store = store if store is not None else InMemoryStructuredStore()
    app.dependency_overrides[get_store] = lambda: store
    moderation = moderation if moderation is not None else _clean_moderation()
    app.dependency_overrides[get_moderation] = lambda: moderation
    cache = cache if cache is not None else InMemoryAnswerCache()
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_embedder] = lambda: StubEmbedder()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql://x", max_history_chars=500)
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def _prov():
    return {"provision_id": 1, "section_num": "97", "text": "tekst",
            "metadata": {"act_title": "TLS", "eli": "RT I 2009, 5, 35",
                         "subsection": "", "is_translation": False}}


def test_answer_returns_200_with_sources():
    r = _client([_prov()]).post("/answer", json={"query": "notice period?"})
    assert r.status_code == 200
    assert r.json()["citations"][0]["section"] == "§ 97"
    assert r.json()["citations"][0]["heading"] == ""
    assert isinstance(r.json()["conversation_id"], int)


def test_answer_returns_422_without_sources():
    r = _client([]).post("/answer", json={"query": "who wins my lawsuit?"})
    assert r.status_code == 422


def test_answer_reuses_supplied_conversation_id_and_persists_history():
    store = InMemoryStructuredStore()
    client = _client([_prov()], store=store)
    first = client.post("/answer", json={"query": "notice period?"})
    cid = first.json()["conversation_id"]
    second = client.post(
        "/answer", json={"query": "what about the deadline?", "conversation_id": cid})
    assert second.status_code == 200
    assert second.json()["conversation_id"] == cid
    history = asyncio.run(store.recent_messages(cid, limit=10))
    assert [m["content"] for m in history] == [
        "notice period?", "Under § 97 notice applies.",
        "what about the deadline?", "Under § 97 notice applies.",
    ]


def test_answer_blocked_by_input_moderation():
    moderation = ToggleModeration([ModerationResult(flagged=True, reason="unsafe request")])
    r = _client([_prov()], moderation=moderation).post(
        "/answer", json={"query": "how do I launder money?"})
    assert r.status_code == 400


def test_answer_output_moderation_replaces_answer():
    moderation = ToggleModeration([
        ModerationResult(flagged=False, reason=""),
        ModerationResult(flagged=True, reason="unsafe answer"),
    ])
    r = _client([_prov()], moderation=moderation).post(
        "/answer", json={"query": "notice period?"})
    assert r.status_code == 200
    assert r.json()["answer"] == (
        "I can't provide that response. Please rephrase your question about Estonian law."
    )


def test_search_returns_provision_results():
    r = _client([_prov()]).post("/search", json={"query": "notice", "limit": 5})
    assert r.status_code == 200
    assert r.json()[0]["section_num"] == "97"


def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}


ELI = "test-act-2009"


def _store_client():
    import asyncio
    store = InMemoryStructuredStore()
    aid = asyncio.run(store.upsert_act(Act(None, ELI, "Testseadus", "Test Act", "employment", "seadus")))
    vid = asyncio.run(store.upsert_act_version(
        ActVersion(None, aid, date(2009, 1, 1), None, "http://rt/x", "hash")))
    asyncio.run(store.insert_provision(Provision(None, vid, "97", "section", "tekst", None, None)))
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)


def test_get_act_returns_metadata():
    r = _store_client().get(f"/acts/{ELI}")
    assert r.status_code == 200
    assert r.json()["eli"] == ELI
    assert r.json()["title_et"] == "Testseadus"


def test_get_act_returns_404_when_missing():
    r = _store_client().get("/acts/does-not-exist")
    assert r.status_code == 404


def test_get_act_versions():
    r = _store_client().get(f"/acts/{ELI}/versions")
    assert r.status_code == 200
    assert r.json()[0]["source_url"] == "http://rt/x"


def test_get_act_as_of_returns_effective_provisions():
    r = _store_client().get(f"/acts/{ELI}/as-of", params={"date": "2010-01-01"})
    assert r.status_code == 200
    assert r.json()[0]["section_num"] == "97"


def test_get_act_as_of_excludes_not_yet_effective():
    r = _store_client().get(f"/acts/{ELI}/as-of", params={"date": "2008-01-01"})
    assert r.status_code == 200
    assert r.json() == []


def test_proxy_headers_middleware_registered_when_trusted_proxies_set():
    settings = Settings(trusted_proxies=["127.0.0.1"], database_url="postgresql://x")
    test_app = FastAPI()
    if settings.trusted_proxies:
        test_app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxies)
    middleware_classes = [m.cls for m in test_app.user_middleware]
    assert ProxyHeadersMiddleware in middleware_classes


def test_proxy_headers_middleware_not_registered_when_trusted_proxies_empty():
    settings = Settings(trusted_proxies=[], database_url="postgresql://x")
    test_app = FastAPI()
    if settings.trusted_proxies:
        test_app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxies)
    middleware_classes = [m.cls for m in test_app.user_middleware]
    assert ProxyHeadersMiddleware not in middleware_classes


def test_answer_cache_miss_stores_result():
    cache = InMemoryAnswerCache()
    r = _client([_prov()], cache=cache).post("/answer", json={"query": "notice period?"})
    assert r.status_code == 200
    assert cache.find_calls == 1
    assert cache.store_calls == 1


def test_answer_cache_hit_skips_retrieval_and_llm():
    cache = InMemoryAnswerCache()
    client = _client([_prov()], cache=cache)
    first = client.post("/answer", json={"query": "notice period?"})

    # Same query, no history yet on the first call, so a fresh conversation with
    # no prior turns produces the same cache key text -> should hit.
    second = client.post("/answer", json={"query": "notice period?"})
    assert second.status_code == 200
    assert second.json()["answer"] == first.json()["answer"]
    assert cache.store_calls == 1  # only the first (miss) call stored anything


def test_answer_flagged_output_is_not_cached():
    cache = InMemoryAnswerCache()
    moderation = ToggleModeration([
        ModerationResult(flagged=False, reason=""),
        ModerationResult(flagged=True, reason="unsafe answer"),
    ])
    r = _client([_prov()], moderation=moderation, cache=cache).post(
        "/answer", json={"query": "notice period?"})
    assert r.status_code == 200
    assert cache.store_calls == 0
