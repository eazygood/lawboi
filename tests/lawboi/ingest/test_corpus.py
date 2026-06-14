from datetime import date

from lawboi.domain.dto import ActMeta
from lawboi.ingest.__main__ import select_current_versions, _active_on


def _meta(gid, tid, frm, to):
    return ActMeta(global_id=gid, title=f"act-{tid}", effective_from=frm,
                   effective_to=to, tervik_id=tid, liik="seadus")


TODAY = date(2026, 6, 10)


def test_active_on_window():
    assert _active_on(_meta(1, 1, date(2020, 1, 1), None), TODAY) is True
    assert _active_on(_meta(1, 1, date(2020, 1, 1), date(2021, 1, 1)), TODAY) is False
    assert _active_on(_meta(1, 1, date(2030, 1, 1), None), TODAY) is False


def test_dedup_keeps_current_version_per_act():
    old = _meta(100, 7, date(2005, 1, 1), date(2005, 6, 1))
    current = _meta(200, 7, date(2024, 1, 1), None)
    chosen = select_current_versions([old, current], TODAY)
    assert set(chosen) == {7}
    assert chosen[7].global_id == 200


def test_dedup_ignores_row_order():
    old = _meta(100, 7, date(2005, 1, 1), date(2005, 6, 1))
    current = _meta(200, 7, date(2024, 1, 1), None)
    assert select_current_versions([current, old], TODAY)[7].global_id == 200


def test_dedup_falls_back_to_latest_when_none_active_today():
    # Two superseded versions, neither in force today — keep the newest.
    v1 = _meta(100, 7, date(2005, 1, 1), date(2005, 6, 1))
    v2 = _meta(200, 7, date(2010, 1, 1), date(2011, 1, 1))
    assert select_current_versions([v1, v2], TODAY)[7].global_id == 200


def test_dedup_distinct_acts_kept_separate():
    a = _meta(1, 10, date(2020, 1, 1), None)
    b = _meta(2, 20, date(2020, 1, 1), None)
    assert set(select_current_versions([a, b], TODAY)) == {10, 20}


def test_dedup_skips_rows_without_tervik_id():
    no_tid = ActMeta(global_id=9, title="x", effective_from=date(2020, 1, 1),
                     effective_to=None, tervik_id=None)
    assert select_current_versions([no_tid], TODAY) == {}
