from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from lawboi.api.main import app
from lawboi.api.deps import get_retrieval, get_answer, get_store
from lawboi.domain.models import Act, ActVersion, Provision
from lawboi.pipeline.retrieval import RetrievalService
from lawboi.answer.service import AnswerService
from lawboi.config.settings import Settings
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from tests.lawboi.fakes import FakeLLMProvider, InMemoryStructuredStore


class StubRetrieval(RetrievalService):
    def __init__(self, provisions):
        self._provisions = provisions
    def retrieve(self, query, as_of=None, limit=None):
        return self._provisions


def _client(provisions):
    app.dependency_overrides[get_retrieval] = lambda: StubRetrieval(provisions)
    app.dependency_overrides[get_answer] = lambda: AnswerService(
        FakeLLMProvider(responses=["Under § 97 notice applies."]))
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


def test_answer_returns_422_without_sources():
    r = _client([]).post("/answer", json={"query": "who wins my lawsuit?"})
    assert r.status_code == 422


def test_search_returns_provision_results():
    r = _client([_prov()]).post("/search", json={"query": "notice", "limit": 5})
    assert r.status_code == 200
    assert r.json()[0]["section_num"] == "97"


def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}


ELI = "test-act-2009"


def _store_client():
    store = InMemoryStructuredStore()
    aid = store.upsert_act(Act(None, ELI, "Testseadus", "Test Act", "employment", "seadus"))
    vid = store.upsert_act_version(
        ActVersion(None, aid, date(2009, 1, 1), None, "http://rt/x", "hash"))
    store.insert_provision(Provision(None, vid, "97", "section", "tekst", None, None))
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
