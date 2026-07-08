from datetime import date
from types import SimpleNamespace

from lawboi.domain.dto import ActMeta, RawAct
from lawboi.domain.errors import SourceFetchError
from lawboi.ingest.__main__ import _ingest_one
from lawboi.ingest.service import IngestService
from tests.lawboi.fakes import InMemoryStructuredStore, InMemoryVectorStore, FakeLawSource

SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<akt>
  <metaandmed>
    <pealkiri keel="et">Testseadus</pealkiri>
  </metaandmed>
  <sisu>
    <paragrahv nr="1">
      <loige nr="1">
        <tekst>Testtekst uhe paragrahvi kohta.</tekst>
      </loige>
    </paragrahv>
  </sisu>
</akt>"""


class StubEmbedder:
    def embed_passages(self, texts):
        return [[0.1] for _ in texts]


def _container():
    store, vector = InMemoryStructuredStore(), InMemoryVectorStore()
    return SimpleNamespace(ingest=IngestService(store, vector, StubEmbedder())), store


async def test_ingest_one_indexes_successfully():
    container, store = _container()
    source = FakeLawSource(acts=[], raw={1: RawAct(1, SAMPLE_XML, "http://example/1")})
    m = ActMeta(1, "Testseadus", date(2020, 1, 1), None)
    msg = await _ingest_one(container, source, tid=1, m=m, today=date(2024, 1, 1))
    assert "1 provisions" in msg or "1 provision" in msg
    assert await store.provisions_as_of("1", date(2024, 1, 1))


async def test_ingest_one_reports_fetch_failure():
    container, _ = _container()

    class FailingSource:
        def fetch(self, global_id):
            raise SourceFetchError("boom")

    m = ActMeta(1, "Testseadus", date(2020, 1, 1), None)
    msg = await _ingest_one(container, FailingSource(), tid=1, m=m, today=date(2024, 1, 1))
    assert "fetch failed" in msg
    assert "boom" in msg


async def test_ingest_one_reports_no_provisions_parsed():
    container, _ = _container()
    empty_xml = b'<?xml version="1.0"?><akt><metaandmed></metaandmed><sisu></sisu></akt>'
    source = FakeLawSource(acts=[], raw={1: RawAct(1, empty_xml, "http://example/1")})
    m = ActMeta(1, "Tuhi", date(2020, 1, 1), None)
    msg = await _ingest_one(container, source, tid=1, m=m, today=date(2024, 1, 1))
    assert "no provisions parsed" in msg


import asyncio

from lawboi.ingest.__main__ import _run_workers


async def test_run_workers_processes_all_items():
    container, store = _container()
    source = FakeLawSource(acts=[], raw={
        1: RawAct(1, SAMPLE_XML, "http://example/1"),
        2: RawAct(2, SAMPLE_XML, "http://example/2"),
    })
    items = [(1, ActMeta(1, "Act One", date(2020, 1, 1), None)),
             (2, ActMeta(2, "Act Two", date(2020, 1, 1), None))]
    shutdown = asyncio.Event()
    done, remaining = await _run_workers(container, source, items, date(2024, 1, 1),
                                         concurrency=2, shutdown=shutdown)
    assert done == 2
    assert remaining == 0
    assert await store.provisions_as_of("1", date(2024, 1, 1))
    assert await store.provisions_as_of("2", date(2024, 1, 1))


async def test_run_workers_stops_pulling_new_items_after_shutdown():
    container, _ = _container()
    shutdown = asyncio.Event()
    calls = []

    class ShutdownTriggeringSource:
        def fetch(self, global_id):
            calls.append(global_id)
            if global_id == 1:
                shutdown.set()
            return RawAct(global_id, SAMPLE_XML, f"http://example/{global_id}")

    items = [(1, ActMeta(1, "Act One", date(2020, 1, 1), None)),
             (2, ActMeta(2, "Act Two", date(2020, 1, 1), None))]
    done, remaining = await _run_workers(container, ShutdownTriggeringSource(), items,
                                         date(2024, 1, 1), concurrency=1, shutdown=shutdown)
    assert calls == [1]
    assert done == 1
    assert remaining == 1
