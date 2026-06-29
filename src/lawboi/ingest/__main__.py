import sys
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from lawboi.config.settings import Settings
from lawboi.config.composition import build_container
from lawboi.adapters.source.riigiteataja import RiigiTeatajaSource
from lawboi.adapters.source.parser import (
    parse_act_xml, parse_act_title, parse_effective_date,
)
from lawboi.ingest.chunker import chunk_provisions
from lawboi.domain.models import Act, ActVersion
from lawboi.domain.dto import ActMeta
from lawboi.domain.errors import SourceFetchError
from lawboi.adapters.source.riigiteataja_client import compute_hash, CORPUS_DOC_TYPES


def _active_on(m: ActMeta, on: date) -> bool:
    return (m.effective_from is not None and m.effective_from <= on
            and (m.effective_to is None or m.effective_to >= on))


def select_current_versions(metas, on: date) -> dict[int, ActMeta]:
    """Collapse crawled version-rows to one current act per terviktekstID.

    The search returns every redaktsioon; we keep the one in force on `on`,
    tie-breaking by latest effective_from so amended acts resolve to their
    newest text even when effective dates are missing.
    """
    chosen: dict[int, ActMeta] = {}
    for m in metas:
        tid = m.tervik_id
        if tid is None:
            continue
        incumbent = chosen.get(tid)
        if incumbent is None or _is_better(m, incumbent, on):
            chosen[tid] = m
    return chosen


def _is_better(candidate: ActMeta, incumbent: ActMeta, on: date) -> bool:
    c_active, i_active = _active_on(candidate, on), _active_on(incumbent, on)
    if c_active != i_active:
        return c_active
    return (candidate.effective_from or date.min) > (incumbent.effective_from or date.min)


def run_ingest(query: str) -> None:
    container = build_container(Settings())
    source = RiigiTeatajaSource()

    if query.isdigit():
        gid = int(query)
        ids = [gid]
        titles = {gid: str(gid)}
        froms, tos = {gid: None}, {gid: None}
    else:
        print(f"Searching for '{query}'...")
        acts = source.search(query, limit=500)
        if not acts:
            print("No acts found.")
            return
        print(f"Found {len(acts)} version(s). Indexing all...")
        ids = [a.global_id for a in acts]
        titles = {a.global_id: a.title for a in acts}
        froms = {a.global_id: a.effective_from for a in acts}
        tos = {a.global_id: a.effective_to for a in acts}

    for gid in ids:
        print(f"  Fetching globaalID={gid} ({titles[gid]})...")
        raw = source.fetch(gid)
        source_hash = compute_hash(raw.xml)
        eff_from_xml, eff_to_xml = parse_effective_date(raw.xml)
        title_xml = parse_act_title(raw.xml) or titles[gid]
        eff_from = eff_from_xml or froms.get(gid) or date.today()
        eff_to = eff_to_xml or tos.get(gid)
        eli = str(gid)

        provisions = parse_act_xml(raw.xml, act_version_id=0,
                                   effective_from=eff_from, effective_to=eff_to)
        if not provisions:
            print(f"    No provisions parsed for {gid} — skipping.")
            continue
        act = Act(None, eli, title_xml, None, "general", "seadus")
        version = ActVersion(None, 0, eff_from, eff_to, raw.source_url, source_hash,
                             source_global_id=gid)
        chunks = chunk_provisions(provisions, act_title=title_xml, eli=eli)
        container.ingest.index_act(act, version, provisions, chunks)
        print(f"    Indexed {len(provisions)} provisions.")


def run_corpus(doc_types=CORPUS_DOC_TYPES, force: bool = False) -> None:
    """Crawl the full corpus for the given document types and ingest the
    current in-force text of each distinct act. Incremental by default:
    redaktsioonid whose globaalID is already ingested are skipped before the
    XML fetch, so re-runs only download new or amended acts. Pass force=True to
    re-fetch every act (e.g. after a parser or embedding change)."""
    container = build_container(Settings())
    source = RiigiTeatajaSource()
    today = date.today()

    print(f"Crawling corpus index for {list(doc_types)}...")
    current = select_current_versions(source.iter_corpus(doc_types), today)
    total = len(current)
    seen = set() if force else container.store.ingested_global_ids()
    skipped = 0
    print(f"{total} distinct acts after dedup. Ingesting current text of each...")

    for i, (tid, m) in enumerate(sorted(current.items()), 1):
        if not force and m.global_id in seen:
            skipped += 1
            continue
        eli = str(tid)
        try:
            raw = source.fetch(m.global_id)
        except SourceFetchError as e:
            print(f"  [{i}/{total}] {m.title}: fetch failed — {e}")
            continue
        source_hash = compute_hash(raw.xml)
        eff_from_xml, eff_to_xml = parse_effective_date(raw.xml)
        title = parse_act_title(raw.xml) or m.title
        eff_from = eff_from_xml or m.effective_from or today
        eff_to = eff_to_xml or m.effective_to

        provisions = parse_act_xml(raw.xml, act_version_id=0,
                                   effective_from=eff_from, effective_to=eff_to)
        if not provisions:
            print(f"  [{i}/{total}] {title}: no provisions parsed — skipping.")
            continue
        act = Act(None, eli, title, None, "general", m.liik or "seadus")
        version = ActVersion(None, 0, eff_from, eff_to, raw.source_url, source_hash,
                             source_global_id=m.global_id)
        chunks = chunk_provisions(provisions, act_title=title, eli=eli)
        container.ingest.index_act(act, version, provisions, chunks)
        print(f"  [{i}/{total}] {title}: {len(provisions)} provisions.")

    print(f"Done. Ingested {total - skipped}, skipped {skipped} unchanged.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: python -m lawboi.ingest <query|globaalID> | --all [--force]")
        sys.exit(1)
    if args[0] == "--all":
        run_corpus(force="--force" in args[1:])
    else:
        run_ingest(args[0])
