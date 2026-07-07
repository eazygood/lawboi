# Design: Concurrent, interrupt-safe full-corpus ingest

**Date:** 2026-07-07
**Scope:** `run_corpus()` in `src/lawboi/ingest/__main__.py`, plus a resume-correctness fix in `src/lawboi/adapters/structured/postgres.py` and `src/lawboi/ingest/service.py`

## Problem

A full Riigi Teataja corpus ingest (`python -m lawboi.ingest --all`) covers 60,422
distinct current acts. `run_corpus()` fetches and indexes them one at a time in a
plain `for` loop, and `fetch_act_xml()` (`riigiteataja_client.py:50-60`) does a
synchronous `requests.get()` plus a hardcoded `time.sleep(1.0)` politeness delay per
call. That sleep alone accounts for ~17 hours regardless of network speed, making a
full run impractical.

Separately, `run_corpus()`'s skip-check for "already ingested" acts
(`ingested_global_ids()`, `postgres.py:89-94`) only checks that an `act_version` row
exists — not that it has provisions, or that those provisions are embedded. An
interrupted or crashed run can leave an act_version row with zero provisions, or
provisions with `embedding IS NULL`. Today that act is then marked "done" forever:
future runs skip it, silently leaving it broken (invisible to `PostgresVectorStore`,
whose queries filter `WHERE p.embedding IS NOT NULL`). Adding concurrency increases
how many acts can be mid-write at any interrupt point, so this gap needs to close
alongside the concurrency change, not after it.

## Solution

1. Run the corpus fetch+index pipeline through a bounded worker pool instead of a
   sequential loop, cutting wall-clock time roughly in proportion to concurrency.
2. Handle `SIGINT` gracefully: stop handing out new work, let in-flight acts finish
   naturally, exit with a summary instead of a stack trace.
3. Redefine "ingested" as "fully indexed" (provisions exist and all are embedded),
   so a partially-written act is correctly retried — never silently stuck — on the
   next run.

## Concurrency model

Worker-pool over an `asyncio.Queue`, not a semaphore wrapped around `asyncio.gather`:
a queue lets workers stop pulling new items on shutdown while whatever they're
already processing runs to completion, which a `gather`-of-all-tasks-up-front
doesn't give us as naturally.

```python
async def run_corpus(doc_types=CORPUS_DOC_TYPES, force=False, concurrency=5):
    ...
    queue = asyncio.Queue()
    for tid, m in sorted(current.items()):
        if not force and m.global_id in seen:
            skipped += 1
            continue
        queue.put_nowait((tid, m))
    queued = queue.qsize()

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, shutdown.set)

    done = 0
    async def worker():
        nonlocal done
        while not shutdown.is_set():
            try:
                tid, m = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            await _ingest_one(container, source, tid, m, today)  # existing fetch/parse/chunk/index_act body
            done += 1
            print(f"  [{done}/{queued}] {m.title}: indexed.")

    try:
        await asyncio.gather(*(worker() for _ in range(concurrency)))
    finally:
        loop.remove_signal_handler(signal.SIGINT)

    if shutdown.is_set():
        print(f"Interrupted — {done}/{queued} ingested this run, "
              f"{queue.qsize()} remaining queued for next run.")
    else:
        print(f"Done. Ingested {done}, skipped {skipped} unchanged.")
```

- `source.fetch(m.global_id)` inside `_ingest_one` moves from a direct call to
  `await asyncio.to_thread(source.fetch, m.global_id)` — same pattern already used
  for the embedder in `stages.py`. This is what actually lets fetches (including
  their 1s politeness sleep) overlap; without it, only DB/embedding work would
  overlap and the sleep would still serialize everything.
- Per-item `try/except SourceFetchError` moves inside the worker loop body (one
  failure logs and continues to the next queue item, doesn't kill the worker).
- `--concurrency N` CLI flag, default `5`. The existing `if __name__ == "__main__"`
  block parses flags manually via `sys.argv` (no `argparse` today); extend that same
  style rather than introducing `argparse` for one new flag:

  ```python
  if args[0] == "--all":
      concurrency = 5
      if "--concurrency" in args[1:]:
          concurrency = int(args[args.index("--concurrency") + 1])
      asyncio.run(run_corpus(force="--force" in args[1:], concurrency=concurrency))
  ```

  Usage: `python -m lawboi.ingest --all --concurrency 8`.
- `run_ingest()` (single-law path) is unchanged — it handles at most dozens of
  versions, where sequential fetching is already fast enough.

## Graceful shutdown

`loop.add_signal_handler(signal.SIGINT, shutdown.set)` intercepts Ctrl-C at the
asyncio level instead of letting a `KeyboardInterrupt` propagate. This matters
because `asyncio.run()`'s default behavior on an uncaught `KeyboardInterrupt` is to
cancel all outstanding tasks as part of its cleanup — which would abort a worker
mid-DB-write, reintroducing the exact partial-state problem this design otherwise
closes. By handling the signal ourselves, no `KeyboardInterrupt` is ever raised;
workers simply stop pulling new items and let their current item finish normally.

A second Ctrl-C is not specially handled — Python's default `KeyboardInterrupt`
behavior applies (immediate, potentially mid-write). This is an accepted edge case:
one Ctrl-C is the documented, safe way to stop; a forced second interrupt is a
deliberate "I know what I'm doing" override, and the resume-correctness fix (below)
bounds the damage even then.

## Resume-correctness fix

**`ingested_global_ids()` → require full indexing, not just row existence.** Change
the query in `postgres.py` to only return global_ids whose act_version has
provisions and none of them are missing an embedding:

```sql
SELECT av.source_global_id
FROM act_version av
WHERE av.source_global_id IS NOT NULL
  AND EXISTS (SELECT 1 FROM provision p WHERE p.act_version_id = av.id)
  AND NOT EXISTS (
      SELECT 1 FROM provision p
      WHERE p.act_version_id = av.id AND p.embedding IS NULL
  )
```

**`IngestService.index_act` → same "fully indexed" guard, with self-healing.**
Replace the `version_has_provisions` early-return check with a `version_fully_indexed`
check (same definition as above, scoped to one `act_version_id`). If the version
exists but isn't fully indexed — the partial-interrupt case — delete its existing
provisions first, then fall through to the normal insert+embed path:

```python
async def index_act(self, act, version, provisions, chunks) -> None:
    act_id = await self._store.upsert_act(act)
    version.act_id = act_id
    version_id = await self._store.upsert_act_version(version)
    if await self._store.version_fully_indexed(version_id):
        return
    await self._store.delete_provisions_for_version(version_id)  # no-op if none exist

    for provision, chunk in zip(provisions, chunks):
        ...  # unchanged
```

`delete_provisions_for_version` is a new store method: `DELETE FROM provision WHERE
act_version_id = %s`. Embeddings live as a column on `provision`
(`pgvector.py`), not a separate table, so deleting the provision rows removes any
partial embeddings with them — no separate cleanup needed.

This makes retries redo a partial act's indexing from scratch rather than trying to
patch in just the missing pieces (e.g. only the missing embeddings). Simpler, and
the partial-write window is narrow enough that redone work is rare and cheap.

**Method rename:** `version_has_provisions` → `version_fully_indexed` (same call
site, same port signature shape, different SQL and different meaning). Update the
`StructuredStore` port, `PostgresStore`, and `InMemoryStructuredStore` fakes together.

## Error handling

- `SourceFetchError` from `source.fetch()`: caught per-item inside the worker loop,
  logs `"{title}: fetch failed — {e}"`, continues to the next queue item. Same
  behavior as today, just relocated from the `for` loop into the worker coroutine.
- Any other exception inside `_ingest_one` (parse failure, DB error) is **not**
  caught here — it propagates out of the worker, `asyncio.gather` cancels the
  sibling workers, and the process exits non-zero. This matches today's behavior
  (unhandled exceptions already crash `run_corpus()`) and is intentional: only
  `SourceFetchError` is expected/routine; anything else indicates a real bug worth
  surfacing loudly rather than silently skipping.

## Testing

- Unit test for `version_fully_indexed`/`delete_provisions_for_version` against
  `InMemoryStructuredStore`: seed a version with provisions missing embeddings,
  confirm the guard returns `False` and a second `index_act` call cleans up and
  redoes the insert rather than skipping.
- Unit test for the new `ingested_global_ids` SQL shape (or its `InMemoryStructuredStore`
  equivalent) confirming a provisions-less or partially-embedded act_version is
  excluded from the returned set.
- Manual: run `--all --concurrency 5` against the real corpus for ~30s, Ctrl-C once,
  confirm the printed summary, confirm re-running resumes without re-fetching
  already-fully-indexed acts (check log output / `ingested_global_ids()` count
  before and after).
- No existing test asserts exact iteration order of `run_corpus()`'s loop — worth
  double-checking `tests/lawboi/ingest/test_service.py` for any such assumption
  before landing, since worker-pool completion order is not the queue's insertion
  order.

## What is not changed

- `run_ingest()` (single-law/query path) — sequential, as today.
- `fetch_act_xml()`'s 1-second politeness delay — kept as-is; concurrency overlaps
  multiple delays across workers rather than removing the delay itself.
- No transactional wrapping of `index_act`'s multiple DB writes — the delete-and-redo
  approach handles the partial-state problem without needing a cross-call
  transaction spanning `upsert_act`, `upsert_act_version`, provision inserts, and the
  embeddings batch upsert.
- `iter_corpus()`'s pagination/crawl phase (`riigiteataja_client.py:63-98`) — still
  sequential; it's a small, fast, one-time crawl relative to the 60k-act fetch+index
  phase, not worth the added complexity.
