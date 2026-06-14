import os
from datetime import date
import pytest
from lawboi.adapters.structured.pool import make_pool
from lawboi.adapters.structured.postgres import PostgresStore
from lawboi.domain.models import Act, ActVersion, Provision

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="requires live Postgres")


@pytest.fixture
def store():
    return PostgresStore(make_pool(minconn=1, maxconn=2))


def test_write_then_fts_search(store):
    aid = store.upsert_act(Act(None, "RT I TEST 1", "Testseadus", None, "general", "seadus"))
    vid = store.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h"))
    store.insert_provision(Provision(None, vid, "99", "section", "unikaalmärksõna", None, None))
    hits = store.fts_search("unikaalmärksõna", date(2021, 1, 1))
    assert any(h.section_num == "99" for h in hits)


def test_exact_lookup_by_section(store):
    aid = store.upsert_act(Act(None, "RT I TEST 2", "Teine", None, "general", "seadus"))
    vid = store.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h"))
    store.insert_provision(Provision(None, vid, "203", "section", "äriühing", None, None))
    rows = store.exact_lookup("203", date(2021, 1, 1), limit=5, eli="RT I TEST 2", title_query=None)
    assert rows and rows[0].section_num == "203"


def test_get_act_roundtrip(store):
    store.upsert_act(Act(None, "RT I TEST 3", "Kolmas", "Third", "tax", "seadus"))
    act = store.get_act("RT I TEST 3")
    assert act is not None and act.title_et == "Kolmas" and act.act_type == "seadus"
    assert store.get_act("RT I MISSING") is None


def test_list_act_versions_newest_first(store):
    aid = store.upsert_act(Act(None, "RT I TEST 4", "Neljas", None, "general", "seadus"))
    store.upsert_act_version(ActVersion(None, aid, date(2010, 1, 1), date(2014, 12, 31), "u1", "h1"))
    store.upsert_act_version(ActVersion(None, aid, date(2015, 1, 1), None, "u2", "h2"))
    versions = store.list_act_versions("RT I TEST 4")
    assert [v.effective_from for v in versions] == [date(2015, 1, 1), date(2010, 1, 1)]


def test_provisions_as_of_filters_by_effective_window(store):
    aid = store.upsert_act(Act(None, "RT I TEST 5", "Viies", None, "general", "seadus"))
    vid = store.upsert_act_version(ActVersion(None, aid, date(2015, 1, 1), None, "u", "h"))
    store.insert_provision(Provision(None, vid, "5", "section", "kehtiv", None, None))
    assert [p.section_num for p in store.provisions_as_of("RT I TEST 5", date(2016, 1, 1))] == ["5"]
    assert store.provisions_as_of("RT I TEST 5", date(2014, 1, 1)) == []
