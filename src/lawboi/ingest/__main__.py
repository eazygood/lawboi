import asyncio
import os
import signal
import sys
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from tqdm import tqdm

from lawboi.config.settings import Settings
from lawboi.config.composition import build_container
from lawboi.adapters.source.riigiteataja import RiigiTeatajaSource
from lawboi.adapters.source.parser import parse_act
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


async def run_ingest(query: str, force: bool = False) -> None:
    """Ingest one act by numeric globaalID or by free-text/title search.
    `Act.eli` is always the stable terviktekstID, never a per-version
    globaalID -- using a globaalID as eli would create a second, duplicate
    `act` row the next time this act is re-ingested under a different
    redaktsioon's globaalID. The numeric path recovers the terviktekstID from
    the fetched XML itself (`terviktekstiGrupiID`, see parser.parse_act);
    the search path gets it from RT's search results (`ActMeta.tervik_id`)
    and collapses to one current version per act, exactly like run_corpus."""
    container = await build_container(Settings(database_url=os.getenv("DATABASE_URL", "")))
    source = RiigiTeatajaSource()
    today = date.today()

    if query.isdigit():
        gid = int(query)
        print(f"  Fetching globaalID={gid}...")
        try:
            raw = source.fetch(gid)
        except SourceFetchError as e:
            print(f"    Fetch failed for {gid}: {e} — skipping.")
            return
        source_hash = compute_hash(raw.xml)
        parsed = parse_act(raw.xml, act_version_id=0)
        if not parsed.provisions:
            print(f"    No provisions parsed for {gid} — skipping.")
            return
        if parsed.tervik_id is None:
            print(f"    No terviktekstiGrupiID found for {gid} — skipping to avoid "
                  f"indexing under a per-version globaalID as eli (would create a "
                  f"duplicate act row on next re-ingest).")
            return
        title_xml = parsed.title or str(gid)
        eff_from = parsed.effective_from or today
        eff_to = parsed.effective_to
        eli = str(parsed.tervik_id)
        act = Act(None, eli, title_xml, None, "general", "seadus")
        version = ActVersion(None, 0, eff_from, eff_to, raw.source_url, source_hash,
                             source_global_id=gid)
        chunks = chunk_provisions(parsed.provisions, act_title=title_xml, eli=eli,
                                  source_global_id=gid)
        await container.ingest.index_act(act, version, parsed.provisions, chunks, force=force)
        print(f"    Indexed {title_xml}: {len(parsed.provisions)} provisions.")
        indexed = 1
    else:
        print(f"Searching for '{query}'...")
        acts = source.search(query, limit=500)
        if not acts:
            print("No acts found.")
            return
        current = select_current_versions(acts, today)
        print(f"Found {len(acts)} version(s), {len(current)} distinct act(s). "
              f"Indexing current text of each...")
        indexed = 0
        for tid, m in sorted(current.items()):
            msg = await _ingest_one(container, source, tid, m, today, force=force)
            print(f"  {msg}")
            if msg.endswith("provisions."):
                indexed += 1

    if indexed and container.cache is not None:
        await container.cache.clear()
        print("Cleared answer cache (corpus changed).")


async def _ingest_one(container, source, tid: int, m, today: date, force: bool = False) -> str:
    """Fetch, parse, chunk, and index one act. Returns a human-readable status
    message; does not print — callers own their own progress-line formatting."""
    eli = str(tid)
    try:
        raw = await asyncio.to_thread(source.fetch, m.global_id)
    except SourceFetchError as e:
        return f"{m.title}: fetch failed — {e}"
    source_hash = compute_hash(raw.xml)
    parsed = parse_act(raw.xml, act_version_id=0)
    title = parsed.title or m.title
    eff_from = parsed.effective_from or m.effective_from or today
    eff_to = parsed.effective_to or m.effective_to

    if not parsed.provisions:
        return f"{title}: no provisions parsed — skipping."
    act = Act(None, eli, title, None, "general", m.liik or "seadus")
    version = ActVersion(None, 0, eff_from, eff_to, raw.source_url, source_hash,
                         source_global_id=m.global_id)
    chunks = chunk_provisions(parsed.provisions, act_title=title, eli=eli,
                              source_global_id=m.global_id)
    await container.ingest.index_act(act, version, parsed.provisions, chunks, force=force)
    return f"{title}: {len(parsed.provisions)} provisions."


async def _run_workers(container, source, items: list, today: date,
                       concurrency: int, shutdown: asyncio.Event) -> tuple[int, int]:
    """Drains `items` through `concurrency` workers pulling from a shared
    queue. Workers check `shutdown` before pulling their next item, so
    whatever's already in flight finishes normally instead of being
    cancelled — the caller is responsible for setting `shutdown`.
    Returns (done, remaining)."""
    queue: asyncio.Queue = asyncio.Queue()
    for tid, m in items:
        queue.put_nowait((tid, m))
    queued = queue.qsize()
    done = 0

    with tqdm(total=queued, desc="Ingesting", unit="act") as pbar:
        async def worker():
            nonlocal done
            while not shutdown.is_set():
                try:
                    tid, m = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                msg = await _ingest_one(container, source, tid, m, today)
                done += 1
                pbar.write(f"  [{done}/{queued}] {msg}")
                pbar.update(1)

        await asyncio.gather(*(worker() for _ in range(concurrency)))
    return done, queue.qsize()


async def run_corpus(doc_types=CORPUS_DOC_TYPES, force: bool = False,
                     concurrency: int = 5) -> None:
    """Crawl the full corpus for the given document types and ingest the
    current in-force text of each distinct act. Incremental by default:
    redaktsioonid whose globaalID is already ingested are skipped before the
    XML fetch, so re-runs only download new or amended acts. Pass force=True to
    re-fetch every act (e.g. after a parser or embedding change). Runs
    `concurrency` acts through fetch+index at once; Ctrl-C stops handing out
    new work but lets whatever's in flight finish before exiting."""
    container = await build_container(Settings(database_url=os.getenv("DATABASE_URL", "")))
    if container.store is None:
        raise RuntimeError("Store is not configured")
    source = RiigiTeatajaSource()
    today = date.today()

    print(f"Crawling corpus index for {list(doc_types)}...")
    current = select_current_versions(source.iter_corpus(doc_types), today)
    total = len(current)
    seen = set() if force else await container.store.ingested_global_ids()
    items = [(tid, m) for tid, m in sorted(current.items())
             if force or m.global_id not in seen]
    skipped = total - len(items)
    print(f"{total} distinct acts after dedup. Ingesting current text of each...")

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, shutdown.set)
    try:
        done, remaining = await _run_workers(container, source, items, today,
                                             concurrency, shutdown)
    finally:
        loop.remove_signal_handler(signal.SIGINT)

    if done and container.cache is not None:
        await container.cache.clear()
        print("Cleared answer cache (corpus changed).")

    if shutdown.is_set():
        print(f"Interrupted — {done} ingested this run, {remaining} remaining queued for next run.")
    else:
        print(f"Done. Ingested {done}, skipped {skipped} unchanged.")


async def run_clear_cache() -> None:
    """Manually invalidate the semantic answer cache, e.g. after a manual DB
    fix or backfill that run_ingest/run_corpus didn't perform themselves."""
    container = await build_container(Settings(database_url=os.getenv("DATABASE_URL", "")))
    if container.cache is None:
        print("No answer cache configured — nothing to clear.")
        return
    await container.cache.clear()
    print("Cleared answer cache.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: python -m lawboi.ingest <query|globaalID> [--force] | --all [--force] [--concurrency N] [--doc-type seadus|määrus] | --clear-cache")
        sys.exit(1)
    if args[0] == "--clear-cache":
        asyncio.run(run_clear_cache())
    elif args[0] == "--all":
        concurrency = 5
        if "--concurrency" in args[1:]:
            concurrency = int(args[args.index("--concurrency") + 1])
        doc_types = CORPUS_DOC_TYPES
        if "--doc-type" in args[1:]:
            doc_type = args[args.index("--doc-type") + 1]
            if doc_type not in CORPUS_DOC_TYPES:
                print(f"Unknown doc type '{doc_type}' — choose from {CORPUS_DOC_TYPES}.")
                sys.exit(1)
            doc_types = (doc_type,)
        asyncio.run(run_corpus(doc_types=doc_types, force="--force" in args[1:], concurrency=concurrency))
    else:
        asyncio.run(run_ingest(args[0], force="--force" in args[1:]))
