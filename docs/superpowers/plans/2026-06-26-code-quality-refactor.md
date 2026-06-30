# Code Quality Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 18 identified bugs, design issues, and performance bottlenecks without changing any external behaviour.

**Architecture:** Each task is self-contained and independently testable. Tasks 1–3 must complete before tasks 4–8 because they change signatures that later tasks depend on. Tasks 4–8 are independent of each other and can be done in any order after tasks 1–3.

**Tech Stack:** Python 3.12, FastAPI, psycopg2, pgvector, sentence-transformers, pytest.

## Global Constraints

- Never change public HTTP response shapes or status codes
- Use `.venv/bin/python -m pytest` for all test runs
- All tests must pass after each task before committing
- Do not add new dependencies

---

## File Map

| File | Changes |
|------|---------|
| `src/lawboi/pipeline/context.py` | Task 1: add `done` field; Task 4: add `_DENSE_N`, `_AUGMENT_N`, `_STEPBACK_N` |
| `src/lawboi/pipeline/stages.py` | Task 1: replace `_done`; Task 2: unify `_to_dict`; Task 3: pass `as_of`; Task 4: remove Merge, use constants |
| `src/lawboi/config/composition.py` | Task 1: type `store`; Task 4: remove Merge from pipeline |
| `src/lawboi/adapters/structured/pool.py` | Task 1: use cursor context manager |
| `src/lawboi/adapters/source/parser.py` | Task 1: rename `_parse_effective_date`; Task 6: add `parse_act()` |
| `src/lawboi/ingest/__main__.py` | Task 1: update import; Task 6: use `parse_act()` |
| `src/lawboi/adapters/_util.py` | Task 2: NEW — `build_provision_metadata()` |
| `src/lawboi/adapters/structured/postgres.py` | Task 2: use `build_provision_metadata` |
| `src/lawboi/adapters/vector/pgvector.py` | Task 2: use `build_provision_metadata`; Task 3: add `as_of` filter; Task 7: add `batch_upsert` |
| `src/lawboi/ports/vector_store.py` | Task 3: add `as_of` to `query`; Task 7: add `batch_upsert` |
| `src/lawboi/api/schemas.py` | Task 5: remove `model` field |
| `src/lawboi/answer/prompts.py` | Task 5: remove inline disclaimer from prompt |
| `src/lawboi/ingest/service.py` | Task 7: switch to `embed_passages` + `batch_upsert` |
| `src/lawboi/api/main.py` | Task 8: add ProxyHeadersMiddleware |
| `src/lawboi/api/limiter.py` | Task 8: use `get_ipaddr` |
| `src/lawboi/config/settings.py` | Task 8: add `trusted_proxies` setting |
| `tests/lawboi/fakes.py` | Task 3: add `as_of` to `InMemoryVectorStore.query`; Task 7: add `batch_upsert` |
| `tests/lawboi/pipeline/test_stages.py` | Task 1: fix `_done` assertion; Task 4: remove Merge test |
| `tests/lawboi/adapters/vector/test_pgvector.py` | Task 3: add `as_of` arg; add date-filter test |
| `tests/lawboi/ingest/test_service.py` | Task 7: update StubEmbedder, update vector.query call |

---

## Task 1: Foundational correctness fixes

Four small independent fixes bundled together because they each touch 1–3 lines and share a single test run.

**Fixes:**
- `RetrievalContext._done` → proper dataclass field `done: bool = False`
- `Container.store` typed as `Optional[StructuredStore]` instead of `object`
- `pooled_cursor` leaks cursor → use psycopg2 cursor as context manager
- `_parse_effective_date` is a private function imported across modules → make it public

**Files:**
- Modify: `src/lawboi/pipeline/context.py`
- Modify: `src/lawboi/pipeline/stages.py`
- Modify: `src/lawboi/config/composition.py`
- Modify: `src/lawboi/adapters/structured/pool.py`
- Modify: `src/lawboi/adapters/source/parser.py`
- Modify: `src/lawboi/ingest/__main__.py`
- Test: `tests/lawboi/pipeline/test_stages.py`
- Test: `tests/lawboi/pipeline/test_context.py` (no change needed — existing tests still pass)

**Interfaces produced:**
- `RetrievalContext.done: bool` — replaces `getattr(ctx, "_done", False)` everywhere

---

- [ ] **Step 1: Add `done` field to `RetrievalContext`**

Replace the contents of `src/lawboi/pipeline/context.py`:

```python
from dataclasses import dataclass, field
from datetime import date

_PROCEDURAL_TERMS = "vaidlustamine tähtaeg kaebus kohus hüvitis õiguskaitsevahend"


@dataclass
class RetrievalConfig:
    limit: int = 5
    procedural_terms: str = _PROCEDURAL_TERMS
    step_back_enabled: bool = True


@dataclass
class RetrievalContext:
    query: str
    as_of: date
    candidates: list[dict] = field(default_factory=list)
    config: RetrievalConfig = field(default_factory=RetrievalConfig)
    done: bool = False
    _seen: set[int] = field(default_factory=set)

    def add(self, provision: dict) -> None:
        pid = provision["provision_id"]
        if pid not in self._seen:
            self._seen.add(pid)
            self.candidates.append(provision)

    def add_all(self, provisions: list[dict]) -> None:
        for p in provisions:
            self.add(p)
```

- [ ] **Step 2: Replace `ctx._done` with `ctx.done` in all pipeline stages**

In `src/lawboi/pipeline/stages.py`, make these targeted replacements:

```python
# CitationShortCircuit.__call__ — change the last line of the if-rows block:
ctx.done = True          # was: ctx._done = True

# DenseSearch.__call__ — change the guard:
if ctx.done:             # was: if getattr(ctx, "_done", False):

# SparseSearch.__call__ — change the guard:
if ctx.done:             # was: if getattr(ctx, "_done", False):

# ProceduralAugment.__call__ — change the guard:
if ctx.done:             # was: if getattr(ctx, "_done", False):

# StepBackExpand.__call__ — change the guard:
if ctx.done or not ctx.config.step_back_enabled or self._llm is None:
                         # was: if getattr(ctx, "_done", False) or not ...
```

- [ ] **Step 3: Fix the `_done` assertion in `test_stages.py`**

In `tests/lawboi/pipeline/test_stages.py`, change the last assertion in `test_citation_shortcircuit_sets_flag`:

```python
def test_citation_shortcircuit_sets_flag():
    ctx = RetrievalContext(query="§ 97 töölepingu seadus", as_of=date(2021, 1, 1))
    out = CitationShortCircuit(_store_with_provision())(ctx)
    assert out.candidates and out.candidates[0]["section_num"] == "97"
    assert out.done is True   # was: assert getattr(out, "_done", False) is True
```

- [ ] **Step 4: Run tests to verify**

```bash
.venv/bin/python -m pytest tests/lawboi/pipeline/ -v
```

Expected: all tests PASS.

- [ ] **Step 5: Type `Container.store` properly**

In `src/lawboi/config/composition.py`, replace the `Container` dataclass and update the import:

```python
from dataclasses import dataclass
from typing import Optional

from lawboi.config.settings import Settings
from lawboi.ports.structured_store import StructuredStore
from lawboi.pipeline.retrieval import RetrievalService
from lawboi.pipeline.stages import (
    CitationShortCircuit, DenseSearch, SparseSearch, ProceduralAugment,
    StepBackExpand, Merge, Rerank,
)
from lawboi.answer.service import AnswerService
from lawboi.ingest.service import IngestService


@dataclass
class Container:
    retrieval: RetrievalService
    answer: AnswerService
    ingest: IngestService
    store: Optional[StructuredStore] = None
```

(Keep the rest of the file — `build_pipeline`, `_build_reranker`, `build_container` — unchanged.)

- [ ] **Step 6: Fix `pooled_cursor` to close the cursor**

Replace `src/lawboi/adapters/structured/pool.py` entirely:

```python
import os
from contextlib import contextmanager
from typing import Optional

from psycopg2.pool import ThreadedConnectionPool


def make_pool(database_url: Optional[str] = None, minconn: int = 1,
              maxconn: int = 10) -> ThreadedConnectionPool:
    dsn = database_url or os.environ["DATABASE_URL"]
    return ThreadedConnectionPool(minconn, maxconn, dsn=dsn)


@contextmanager
def pooled_cursor(pool: ThreadedConnectionPool):
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            yield cur
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
```

- [ ] **Step 7: Make `_parse_effective_date` public**

In `src/lawboi/adapters/source/parser.py`, rename the function:

```python
# Line ~76 — rename from _parse_effective_date to parse_effective_date
def parse_effective_date(xml_bytes: bytes) -> tuple[Optional[date], Optional[date]]:
    ...
```

(The body is unchanged; only the name changes.)

- [ ] **Step 8: Update the import in `ingest/__main__.py`**

```python
from lawboi.adapters.source.parser import (
    parse_act_xml, parse_act_title, parse_effective_date,   # was: _parse_effective_date
)
```

And update the two call sites in that file:

```python
# run_ingest (line ~75):
eff_from_xml, eff_to_xml = parse_effective_date(raw.xml)   # was: _parse_effective_date

# run_corpus (line ~122):
eff_from_xml, eff_to_xml = parse_effective_date(raw.xml)   # was: _parse_effective_date
```

- [ ] **Step 9: Run full test suite**

```bash
.venv/bin/python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 10: Commit**

```bash
git add src/lawboi/pipeline/context.py \
        src/lawboi/pipeline/stages.py \
        src/lawboi/config/composition.py \
        src/lawboi/adapters/structured/pool.py \
        src/lawboi/adapters/source/parser.py \
        src/lawboi/ingest/__main__.py \
        tests/lawboi/pipeline/test_stages.py
git commit -m "fix: use proper done field on RetrievalContext, type Container.store, close cursors, publicise parse_effective_date"
```

---

## Task 2: Eliminate duplicate dict-conversion helpers

**Problem:**
- `_hit_to_dict` and `_rp_to_dict` in `stages.py` are byte-for-byte identical
- `fts_search`, `exact_lookup`, and `PostgresVectorStore.query` each build the same metadata dict inline

**Fix:** One `_to_provision_dict()` function in `stages.py`. One `build_provision_metadata()` helper in a new `adapters/_util.py` used by both adapter files.

**Files:**
- Create: `src/lawboi/adapters/_util.py`
- Modify: `src/lawboi/adapters/structured/postgres.py`
- Modify: `src/lawboi/adapters/vector/pgvector.py`
- Modify: `src/lawboi/pipeline/stages.py`

---

- [ ] **Step 1: Create `adapters/_util.py`**

```python
def build_provision_metadata(
    act_title: str, eli: str, section_num: str, act_version_id: int
) -> dict:
    return {
        "act_title": act_title,
        "eli": eli,
        "section_num": section_num,
        "act_version_id": act_version_id,
        "is_translation": False,
        "context": "",
    }
```

- [ ] **Step 2: Use it in `postgres.py`**

Add the import at the top of `src/lawboi/adapters/structured/postgres.py`:

```python
from lawboi.adapters._util import build_provision_metadata
```

Replace every inline metadata dict literal in `fts_search` and `exact_lookup`. There are four occurrences (one in `fts_search`, three in `exact_lookup`). Each looks like:

```python
# BEFORE (example from fts_search):
metadata={
    "act_title": r[4],
    "eli": r[5],
    "section_num": r[1],
    "act_version_id": r[3],
    "is_translation": False,
    "context": "",
}

# AFTER:
metadata=build_provision_metadata(r[4], r[5], r[1], r[3]),
```

The column mapping for all three queries in this file:
- `r[0]` = `p.id` (provision_id)
- `r[1]` = `p.section_num`
- `r[2]` = `p.text_et`
- `r[3]` = `p.act_version_id`
- `r[4]` = `a.title_et`
- `r[5]` = `a.eli`

So the call is always `build_provision_metadata(r[4], r[5], r[1], r[3])`.

- [ ] **Step 3: Use it in `pgvector.py`**

Add the import and replace the inline dict in `PostgresVectorStore.query`:

```python
from lawboi.adapters._util import build_provision_metadata
```

In `query`, the SELECT is `p.id, p.section_num, p.text_et, a.title_et, a.eli, p.act_version_id` — columns 0–5. Replace:

```python
# BEFORE:
metadata={
    "act_title": r[3],
    "eli": r[4],
    "section_num": r[1],
    "act_version_id": r[5],
    "is_translation": False,
    "context": "",
}

# AFTER:
metadata=build_provision_metadata(r[3], r[4], r[1], r[5]),
```

- [ ] **Step 4: Unify `_hit_to_dict` / `_rp_to_dict` in `stages.py`**

In `src/lawboi/pipeline/stages.py`, delete `_hit_to_dict` and `_rp_to_dict` and replace both with:

```python
def _to_provision_dict(p) -> dict:
    return {"provision_id": p.provision_id, "section_num": p.section_num,
            "text": p.text, "metadata": p.metadata}
```

Update every call site in `stages.py` (five occurrences):

```python
# CitationShortCircuit — no change (it calls _rp_to_dict):
ctx.add_all([_to_provision_dict(r) for r in rows])

# DenseSearch:
ctx.add_all([_to_provision_dict(h) for h in self._vector.query(...)])

# SparseSearch:
ctx.add_all([_to_provision_dict(r) for r in self._store.fts_search(...)])

# ProceduralAugment — two lines:
ctx.add_all([_to_provision_dict(h) for h in self._vector.query(...)])
ctx.add_all([_to_provision_dict(r) for r in self._store.fts_search(...)])

# StepBackExpand — two lines:
ctx.add_all([_to_provision_dict(h) for h in self._vector.query(...)])
ctx.add_all([_to_provision_dict(r) for r in self._store.fts_search(...)])
```

- [ ] **Step 5: Run full test suite**

```bash
.venv/bin/python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/lawboi/adapters/_util.py \
        src/lawboi/adapters/structured/postgres.py \
        src/lawboi/adapters/vector/pgvector.py \
        src/lawboi/pipeline/stages.py
git commit -m "refactor: unify provision dict helpers and extract build_provision_metadata"
```

---

## Task 3: Add `as_of` date filter to `VectorStore.query` (CRITICAL BUG FIX)

**Problem:** `PostgresVectorStore.query` returns provisions from any act version, including expired/superseded versions. Dense search, procedural augment, and step-back expand can all return stale law.

**Fix:** Add `as_of: date` parameter to the `VectorStore` port and all implementations. Filter by `av.effective_from <= as_of AND (av.effective_to IS NULL OR av.effective_to >= as_of)` in SQL.

**Files:**
- Modify: `src/lawboi/ports/vector_store.py`
- Modify: `src/lawboi/adapters/vector/pgvector.py`
- Modify: `src/lawboi/pipeline/stages.py`
- Modify: `tests/lawboi/fakes.py`
- Modify: `tests/lawboi/adapters/vector/test_pgvector.py`
- Modify: `tests/lawboi/ingest/test_service.py`
- Modify: `tests/lawboi/pipeline/test_stages.py`

**Interfaces consumed:** `RetrievalContext.as_of` (from Task 1)

**Interfaces produced:** `VectorStore.query(embedding, n_results, as_of)` — callers must pass date

---

- [ ] **Step 1: Write a failing test for the date filter**

Add to `tests/lawboi/adapters/vector/test_pgvector.py`:

```python
def test_query_excludes_expired_versions(store, vector):
    """A provision from an expired act version must not appear in results."""
    aid = store.upsert_act(Act(None, "RT I VEC 2", "Vananenud seadus", None, "general", "seadus"))
    vid = store.upsert_act_version(
        ActVersion(None, aid, date(2000, 1, 1), date(2010, 12, 31), "u", "h")
    )
    pid = store.insert_provision(Provision(None, vid, "1", "section", "vana tekst", None, None))
    embedding = [0.01] * 1024
    vector.upsert(pid, embedding)

    # Query as of 2020 — this provision's version expired in 2010
    hits = vector.query(embedding, n_results=5, as_of=date(2020, 1, 1))
    assert all(h.provision_id != pid for h in hits), "expired provision should be excluded"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
.venv/bin/python -m pytest tests/lawboi/adapters/vector/test_pgvector.py::test_query_excludes_expired_versions -v
```

Expected: `TypeError` because `query` doesn't accept `as_of` yet.

- [ ] **Step 3: Update the `VectorStore` port**

Replace `src/lawboi/ports/vector_store.py`:

```python
from datetime import date
from typing import Protocol, runtime_checkable
from lawboi.domain.dto import VectorHit


@runtime_checkable
class VectorStore(Protocol):
    def query(self, embedding: list[float], n_results: int, as_of: date) -> list[VectorHit]: ...

    def upsert(self, provision_id: int, embedding: list[float]) -> None: ...

    def batch_upsert(self, pairs: list[tuple[int, list[float]]]) -> None: ...
```

(`batch_upsert` is added here and implemented in Task 7; define it now so the port is complete.)

- [ ] **Step 4: Implement date filter in `PostgresVectorStore.query`**

Replace the `query` method in `src/lawboi/adapters/vector/pgvector.py`:

```python
def query(self, embedding: list[float], n_results: int, as_of: date) -> list[VectorHit]:
    with pooled_cursor(self._pool) as cur:
        cur.execute(
            """
            SELECT p.id, p.section_num, p.text_et, a.title_et, a.eli,
                   p.act_version_id
            FROM provision p
            JOIN act_version av ON p.act_version_id = av.id
            JOIN act a ON av.act_id = a.id
            WHERE p.embedding IS NOT NULL
              AND av.effective_from <= %s
              AND (av.effective_to IS NULL OR av.effective_to >= %s)
            ORDER BY p.embedding <=> %s::vector
            LIMIT %s
            """,
            (as_of, as_of, _vec(embedding), n_results),
        )
        return [
            VectorHit(
                provision_id=r[0],
                section_num=r[1],
                text=r[2],
                metadata=build_provision_metadata(r[3], r[4], r[1], r[5]),
            )
            for r in cur.fetchall()
        ]
```

Also add the `date` import and a stub `batch_upsert` that raises `NotImplementedError` (Task 7 will fill it in):

```python
from datetime import date

# at the end of the class:
def batch_upsert(self, pairs: list[tuple[int, list[float]]]) -> None:
    raise NotImplementedError("implemented in Task 7")
```

- [ ] **Step 5: Update `InMemoryVectorStore` fake to accept `as_of`**

In `tests/lawboi/fakes.py`, update `InMemoryVectorStore.query`:

```python
def query(self, embedding: list[float], n_results: int, as_of: date) -> list[VectorHit]:
    return [
        VectorHit(provision_id=pid, section_num="", text="", metadata={})
        for pid in list(self._embeddings.keys())[:n_results]
    ]
```

Also add `batch_upsert` stub (Task 7 will complete it):

```python
def batch_upsert(self, pairs: list[tuple[int, list[float]]]) -> None:
    for pid, emb in pairs:
        self._embeddings[pid] = emb
```

Add `from datetime import date` import if not already present.

- [ ] **Step 6: Update all stages that call `vector.query`**

In `src/lawboi/pipeline/stages.py`, every call to `self._vector.query(emb, n_results=N)` must become `self._vector.query(emb, n_results=N, as_of=ctx.as_of)`.

There are three call sites:

```python
# DenseSearch.__call__:
ctx.add_all([_to_provision_dict(h) for h in self._vector.query(emb, n_results=20, as_of=ctx.as_of)])

# ProceduralAugment.__call__:
ctx.add_all([_to_provision_dict(h) for h in self._vector.query(emb, n_results=10, as_of=ctx.as_of)])

# StepBackExpand.__call__:
ctx.add_all([_to_provision_dict(h) for h in self._vector.query(emb, n_results=10, as_of=ctx.as_of)])
```

- [ ] **Step 7: Update `test_pgvector.py` existing test signature**

In `tests/lawboi/adapters/vector/test_pgvector.py`, update `test_upsert_then_query`:

```python
def test_upsert_then_query(store, vector):
    aid = store.upsert_act(Act(None, "RT I VEC 1", "Vektorseadus", None, "general", "seadus"))
    vid = store.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h"))
    pid = store.insert_provision(Provision(None, vid, "77", "section", "vektorikatse tekst", None, None))

    embedding = [0.01] * 1024
    vector.upsert(pid, embedding)

    hits = vector.query(embedding, n_results=5, as_of=date(2020, 1, 1))  # added as_of
    assert hits and isinstance(hits[0], VectorHit)
    assert any(h.provision_id == pid for h in hits)
    match = next(h for h in hits if h.provision_id == pid)
    assert match.section_num == "77"
    assert match.text == "vektorikatse tekst"
    assert match.metadata["eli"] == "RT I VEC 1"
```

- [ ] **Step 8: Update `test_service.py` — `vector.query` call**

In `tests/lawboi/ingest/test_service.py`, the test directly calls `vector.query`. Update all such calls:

```python
# test_index_act_writes_store_and_vector — change:
assert vector.query([0.1], 5, date(2021, 1, 1))   # was: vector.query([0.1], 5)
```

- [ ] **Step 9: Update `test_stages.py` — `DenseSearch` test**

In `tests/lawboi/pipeline/test_stages.py`, the `DenseSearch` test calls `v.upsert` then checks that the stage ran. The `InMemoryVectorStore.query` now requires `as_of` but the stage passes it automatically via `ctx.as_of`. No change needed to the test itself since `DenseSearch` passes `ctx.as_of` now. Verify by running:

```bash
.venv/bin/python -m pytest tests/lawboi/pipeline/test_stages.py::test_dense_search_populates_candidates -v
```

Expected: PASS.

- [ ] **Step 10: Run full test suite**

```bash
.venv/bin/python -m pytest -v
```

Expected: all tests PASS, including the new `test_query_excludes_expired_versions` if `DATABASE_URL` is set (skipped otherwise).

- [ ] **Step 11: Commit**

```bash
git add src/lawboi/ports/vector_store.py \
        src/lawboi/adapters/vector/pgvector.py \
        src/lawboi/pipeline/stages.py \
        tests/lawboi/fakes.py \
        tests/lawboi/adapters/vector/test_pgvector.py \
        tests/lawboi/ingest/test_service.py \
        tests/lawboi/pipeline/test_stages.py
git commit -m "fix: add as_of date filter to VectorStore.query — prevents stale law versions in dense search"
```

---

## Task 4: Remove `Merge` no-op and move per-stage fetch counts to module constants

**Problem:**
- `Merge` stage is documented as a no-op and is misleading — it implies work is happening
- `DenseSearch`, `ProceduralAugment`, `StepBackExpand` hardcode `n_results` values inside the stage class bodies, making them invisible to anyone reading the pipeline config

**Fix:** Delete `Merge` class; move fetch counts to named module-level constants in `stages.py`; remove `Merge` from `composition.py`.

**Files:**
- Modify: `src/lawboi/pipeline/stages.py`
- Modify: `src/lawboi/config/composition.py`
- Modify: `tests/lawboi/pipeline/test_stages.py`

---

- [ ] **Step 1: Add module-level constants to `stages.py`**

Near the top of `src/lawboi/pipeline/stages.py` (after imports, before class definitions), add:

```python
_DENSE_N = 20      # candidates fetched by DenseSearch
_AUGMENT_N = 10    # candidates fetched by ProceduralAugment and StepBackExpand
```

- [ ] **Step 2: Replace hardcoded `n_results` values in stages**

```python
# DenseSearch.__call__:
ctx.add_all([_to_provision_dict(h) for h in self._vector.query(emb, n_results=_DENSE_N, as_of=ctx.as_of)])

# ProceduralAugment.__call__:
ctx.add_all([_to_provision_dict(h) for h in self._vector.query(emb, n_results=_AUGMENT_N, as_of=ctx.as_of)])

# StepBackExpand.__call__:
ctx.add_all([_to_provision_dict(h) for h in self._vector.query(emb, n_results=_AUGMENT_N, as_of=ctx.as_of)])
```

- [ ] **Step 3: Delete the `Merge` class from `stages.py`**

Remove the entire `Merge` class:

```python
# DELETE this entire block:
class Merge:
    """Dedup is already handled by RetrievalContext.add; Merge is the explicit
    ordering boundary and a hook for future scoring."""
    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        return ctx
```

- [ ] **Step 4: Remove `Merge` from `composition.py`**

In `src/lawboi/config/composition.py`, remove `Merge` from the import and from `build_pipeline`:

```python
# Update import — remove Merge:
from lawboi.pipeline.stages import (
    CitationShortCircuit, DenseSearch, SparseSearch, ProceduralAugment,
    StepBackExpand, Rerank,
)

# Update build_pipeline — remove Merge() from the list:
def build_pipeline(store, vector, embedder, llm, reranker):
    return [
        CitationShortCircuit(store),
        DenseSearch(vector, embedder),
        SparseSearch(store),
        ProceduralAugment(vector, embedder, store),
        StepBackExpand(vector, embedder, store, llm),
        Rerank(reranker),
    ]
```

- [ ] **Step 5: Update `test_stages.py` to remove `Merge` test and import**

In `tests/lawboi/pipeline/test_stages.py`:

```python
# Remove Merge from import:
from lawboi.pipeline.stages import (
    CitationShortCircuit, DenseSearch, SparseSearch, Rerank, is_citation_query,
)

# Delete test_merge_is_dedup_passthrough entirely.
```

- [ ] **Step 6: Run full test suite**

```bash
.venv/bin/python -m pytest -v
```

Expected: all tests PASS. `test_merge_is_dedup_passthrough` is gone.

- [ ] **Step 7: Commit**

```bash
git add src/lawboi/pipeline/stages.py \
        src/lawboi/config/composition.py \
        tests/lawboi/pipeline/test_stages.py
git commit -m "refactor: remove Merge no-op stage, centralise fetch count constants"
```

---

## Task 5: Fix `AnswerRequest.model` dead field and `DISCLAIMER` duplication

**Problem:**
- `AnswerRequest.model` is accepted by the API but silently ignored — the LLM is fixed at startup
- `SYSTEM_PROMPT` instructs the LLM to append the disclaimer AND the server returns `DISCLAIMER` in the structured response — the disclaimer appears twice in the rendered answer

**Fix:** Remove the `model` field from `AnswerRequest`. Remove the disclaimer instruction block from `SYSTEM_PROMPT` — the server's structured `disclaimer` field is the canonical source; the frontend should render it separately, not rely on the LLM echoing it.

**Files:**
- Modify: `src/lawboi/api/schemas.py`
- Modify: `src/lawboi/answer/prompts.py`
- Test: `tests/lawboi/answer/test_service.py` — verify no test relies on `model` field or doubled disclaimer

---

- [ ] **Step 1: Verify no test uses `AnswerRequest.model`**

```bash
grep -r "AnswerRequest" tests/ src/
```

Expected: no test passes a `model=` kwarg to `AnswerRequest`. If any test does, update it to remove that kwarg.

- [ ] **Step 2: Remove `model` from `AnswerRequest`**

In `src/lawboi/api/schemas.py`, replace:

```python
class AnswerRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    model: Optional[str] = None
    as_of_date: Optional[date] = None
```

With:

```python
class AnswerRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    as_of_date: Optional[date] = None
```

Also remove the `Optional` import if it's now unused (check: `AnswerResponse` uses `Optional` implicitly via `list[Citation]` — keep if used elsewhere, otherwise remove). The `Optional` import is also used by `SearchRequest.domain`, so keep it.

- [ ] **Step 3: Remove the disclaimer instruction from `SYSTEM_PROMPT`**

In `src/lawboi/answer/prompts.py`, remove the DISCLAIMER section from `SYSTEM_PROMPT` and the instruction to append it:

```python
SYSTEM_PROMPT = """\
You are Eesti Õigusabi, a legal information assistant for Estonian law.
You answer questions strictly based on the legal provisions provided below.

RULES:
1. Only use information from the provided provisions. Do not use prior knowledge.
2. Every factual claim must cite its source as: [Act Name § Section lg Subsection].
3. If the provided provisions do not contain enough information to answer, say so explicitly.
4. Never speculate, infer beyond what is written, or fill gaps with assumptions.
5. If the user's question requires specific legal advice for their situation, state
   that this tool provides legal information only, not legal advice.
6. Respond in the same language as the user's question (Estonian or English).
   When responding in English, note if the source text is an unofficial translation.

ACTIONABLE OPTIONS:
After answering what the law says, add a section titled "Mida saate teha?"
(or "What you can do?" if responding in English) that lists the concrete steps
available under the retrieved provisions. Include, where present in the provisions:
- Applicable deadlines for taking action
- Which body handles the matter (court, relevant inspectorate, commission, etc.)
- Required form (written notice, formal complaint, application, etc.)
- Any right to compensation or remedy and how it is calculated
If the retrieved provisions contain no procedural or remedy information, omit this
section entirely — do not speculate or invent steps.

RETRIEVED PROVISIONS:
{context}

USER QUESTION:
{query}"""

DISCLAIMER = (
    "⚠️ See vastus on üldine õiguslik teave, mitte õigusabi. / "
    "This is general legal information, not legal advice. "
    "Consult a qualified lawyer for your specific situation. "
    "Official source: riigiteataja.ee"
)
```

Key changes from original:
- Removed rule 7 ("Always append the disclaimer block below at the end of every response")
- Removed the `DISCLAIMER:` block embedded inside `SYSTEM_PROMPT`

- [ ] **Step 4: Run full test suite**

```bash
.venv/bin/python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lawboi/api/schemas.py \
        src/lawboi/answer/prompts.py
git commit -m "fix: remove dead AnswerRequest.model field, fix disclaimer duplication in system prompt"
```

---

## Task 6: Consolidate XML parsing into a single pass

**Problem:** `ingest/__main__.py` calls `parse_effective_date(raw.xml)`, `parse_act_title(raw.xml)`, and `parse_act_xml(raw.xml, ...)` — three separate calls that each re-parse the full XML document from bytes. For a large act this is 3× wasted work.

**Fix:** Add a `parse_act()` function to `parser.py` that returns all three pieces of data in one parse. `__main__.py` calls `parse_act()` instead of three separate functions.

**Files:**
- Modify: `src/lawboi/adapters/source/parser.py`
- Modify: `src/lawboi/ingest/__main__.py`
- Test: `tests/lawboi/adapters/source/test_parser.py`

---

- [ ] **Step 1: Write a failing test for `parse_act`**

Add to `tests/lawboi/adapters/source/test_parser.py`:

```python
from lawboi.adapters.source.parser import parse_act

FULL_SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<akt>
  <metaandmed>
    <pealkiri keel="et">Toolepingu seadus</pealkiri>
    <kehtivus>
      <kehtivuseAlgus>2009-07-01</kehtivuseAlgus>
    </kehtivus>
  </metaandmed>
  <sisu>
    <paragrahv nr="1">
      <loige nr="1"><tekst>Kaeesolev seadus reguleerib toolepingu.</tekst></loige>
    </paragrahv>
  </sisu>
</akt>"""


def test_parse_act_returns_all_fields():
    result = parse_act(FULL_SAMPLE_XML, act_version_id=7)
    assert result.title == "Toolepingu seadus"
    assert result.effective_from is not None
    assert result.effective_to is None
    assert len(result.provisions) == 1
    assert result.provisions[0].act_version_id == 7
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
.venv/bin/python -m pytest tests/lawboi/adapters/source/test_parser.py::test_parse_act_returns_all_fields -v
```

Expected: `ImportError` — `parse_act` does not exist yet.

- [ ] **Step 3: Add `ParsedAct` dataclass and `parse_act()` to `parser.py`**

Add these at the end of `src/lawboi/adapters/source/parser.py`, after the existing functions:

```python
from dataclasses import dataclass


@dataclass
class ParsedAct:
    title: str
    effective_from: Optional[date]
    effective_to: Optional[date]
    provisions: list[Provision]


def parse_act(xml_bytes: bytes, act_version_id: int) -> ParsedAct:
    """Parse a raw act XML document in a single pass. Returns title, effective
    dates, and provisions. Replaces three separate parse calls in the ingest path."""
    root = _parse_xml(xml_bytes)

    # title
    title_el = root.find(".//pealkiri")
    title = title_el.text.strip() if title_el is not None and title_el.text else ""

    # effective dates
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    meta = root.find("metaandmed")
    if meta is not None:
        kehtivus = meta.find("kehtivus")
        if kehtivus is not None:
            def _d(tag: str) -> Optional[date]:
                el = kehtivus.find(tag)
                if el is None or not el.text:
                    return None
                try:
                    return datetime.fromisoformat(el.text[:10]).date()
                except ValueError:
                    return None
            effective_from = _d("kehtivuseAlgus")
            effective_to = _d("kehtivuseLopp")

    # provisions — reuse the existing tree walk logic
    results: list[Provision] = []
    sisu = root.find("sisu")
    if sisu is None:
        sisu = root

    for part_el in sisu.findall(TAGS["part"]):
        for chapter_el in part_el.findall(TAGS["chapter"]):
            for section_el in chapter_el.findall(TAGS["section"]):
                _parse_section(section_el, act_version_id, None, results)
        for section_el in part_el.findall(TAGS["section"]):
            _parse_section(section_el, act_version_id, None, results)

    for chapter_el in sisu.findall(TAGS["chapter"]):
        for section_el in chapter_el.findall(TAGS["section"]):
            _parse_section(section_el, act_version_id, None, results)

    for section_el in sisu.findall(TAGS["section"]):
        _parse_section(section_el, act_version_id, None, results)

    return ParsedAct(
        title=title,
        effective_from=effective_from,
        effective_to=effective_to,
        provisions=results,
    )
```

Note: the `dataclass` import must be added at the top of parser.py if not already there.

- [ ] **Step 4: Run the new test**

```bash
.venv/bin/python -m pytest tests/lawboi/adapters/source/test_parser.py::test_parse_act_returns_all_fields -v
```

Expected: PASS.

- [ ] **Step 5: Update `ingest/__main__.py` to use `parse_act`**

Add `parse_act` to the import and replace the three-parse pattern in both `run_ingest` and `run_corpus`.

Update import:

```python
from lawboi.adapters.source.parser import (
    parse_act_xml, parse_act_title, parse_effective_date, parse_act,
)
```

Replace in `run_ingest` (the block starting at `raw = source.fetch(gid)`):

```python
for gid in ids:
    print(f"  Fetching globaalID={gid} ({titles[gid]})...")
    raw = source.fetch(gid)
    source_hash = compute_hash(raw.xml)
    parsed = parse_act(raw.xml, act_version_id=0)
    title_xml = parsed.title or titles[gid]
    eff_from = parsed.effective_from or froms.get(gid) or date.today()
    eff_to = parsed.effective_to or tos.get(gid)
    eli = str(gid)

    if not parsed.provisions:
        print(f"    No provisions parsed for {gid} — skipping.")
        continue
    act = Act(None, eli, title_xml, None, "general", "seadus")
    version = ActVersion(None, 0, eff_from, eff_to, raw.source_url, source_hash,
                         source_global_id=gid)
    chunks = chunk_provisions(parsed.provisions, act_title=title_xml, eli=eli)
    container.ingest.index_act(act, version, parsed.provisions, chunks)
    print(f"    Indexed {len(parsed.provisions)} provisions.")
```

Replace in `run_corpus` (the inner loop body):

```python
        try:
            raw = source.fetch(m.global_id)
        except SourceFetchError as e:
            print(f"  [{i}/{total}] {m.title}: fetch failed — {e}")
            continue
        source_hash = compute_hash(raw.xml)
        parsed = parse_act(raw.xml, act_version_id=0)
        title = parsed.title or m.title
        eff_from = parsed.effective_from or m.effective_from or today
        eff_to = parsed.effective_to or m.effective_to

        if not parsed.provisions:
            print(f"  [{i}/{total}] {title}: no provisions parsed — skipping.")
            continue
        act = Act(None, eli, title, None, "general", m.liik or "seadus")
        version = ActVersion(None, 0, eff_from, eff_to, raw.source_url, source_hash,
                             source_global_id=m.global_id)
        chunks = chunk_provisions(parsed.provisions, act_title=title, eli=eli)
        container.ingest.index_act(act, version, parsed.provisions, chunks)
        print(f"  [{i}/{total}] {title}: {len(parsed.provisions)} provisions.")
```

Remove the now-unused imports `parse_act_title`, `parse_effective_date` from `__main__.py` if they are no longer used. Keep `parse_act_xml` only if it is used elsewhere; if not, remove it too.

- [ ] **Step 6: Run full test suite**

```bash
.venv/bin/python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/lawboi/adapters/source/parser.py \
        src/lawboi/ingest/__main__.py \
        tests/lawboi/adapters/source/test_parser.py
git commit -m "perf: consolidate XML parsing into single parse_act() — removes 3x re-parse per ingest"
```

---

## Task 7: Batch embeddings and batch vector upsert in IngestService

**Problem:** `IngestService.index_act` calls `self._embedder.embed_passage(text)` inside a loop — one model inference call per provision. `SentenceTransformer.encode()` batches internally for GPU/SIMD acceleration; calling it one-by-one bypasses this. Also, each `vector.upsert()` is a separate SQL `UPDATE`.

**Fix:** Collect all chunk texts after inserting provisions, call `embed_passages(texts)` once for a batched model pass, then call `batch_upsert(pairs)` once for a single SQL operation.

**Files:**
- Modify: `src/lawboi/ingest/service.py`
- Modify: `src/lawboi/adapters/vector/pgvector.py`
- Modify: `tests/lawboi/fakes.py`
- Modify: `tests/lawboi/ingest/test_service.py`

**Interfaces consumed:** `VectorStore.batch_upsert` (port stub added in Task 3), `Embedder.embed_passages` (already exists in `ingest/embedder.py`)

---

- [ ] **Step 1: Write a failing test for batched ingest**

Add to `tests/lawboi/ingest/test_service.py`:

```python
def test_index_act_uses_batch_embedding():
    """IngestService must call embed_passages (batch) not embed_passage (single)."""
    store, vector = InMemoryStructuredStore(), InMemoryVectorStore()

    class BatchTrackingEmbedder:
        def __init__(self):
            self.single_calls = 0
            self.batch_calls = 0

        def embed_passage(self, text):
            self.single_calls += 1
            return [0.1]

        def embed_passages(self, texts):
            self.batch_calls += 1
            return [[0.1]] * len(texts)

    embedder = BatchTrackingEmbedder()
    svc = IngestService(store, vector, embedder)
    act = Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus")
    version = ActVersion(None, 0, date(2020, 1, 1), None, "u", "h")
    provisions = [
        Provision(None, 0, str(i), "section", f"tekst {i}", None, None)
        for i in range(5)
    ]
    chunks = [Chunk(None, 0, str(i), f"tekst {i}", {}) for i in range(5)]
    svc.index_act(act, version, provisions, chunks)

    assert embedder.single_calls == 0, "embed_passage (single) should not be called"
    assert embedder.batch_calls == 1, "embed_passages should be called exactly once"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
.venv/bin/python -m pytest tests/lawboi/ingest/test_service.py::test_index_act_uses_batch_embedding -v
```

Expected: FAIL — `AssertionError: embed_passage (single) should not be called` (currently called 5 times).

- [ ] **Step 3: Update `IngestService.index_act` to use batch path**

Replace `src/lawboi/ingest/service.py`:

```python
from lawboi.domain.models import Act, ActVersion, Provision, Chunk
from lawboi.ports.structured_store import StructuredStore
from lawboi.ports.vector_store import VectorStore


class IngestService:
    """Writes act metadata to the structured store and provision embeddings to
    the vector store, keeping the two in sync."""

    def __init__(self, store: StructuredStore, vector: VectorStore, embedder):
        self._store = store
        self._vector = vector
        self._embedder = embedder

    def index_act(self, act: Act, version: ActVersion,
                  provisions: list[Provision], chunks: list[Chunk]) -> None:
        act_id = self._store.upsert_act(act)
        version.act_id = act_id
        version_id = self._store.upsert_act_version(version)
        if self._store.version_has_provisions(version_id):
            return

        for provision, chunk in zip(provisions, chunks):
            provision.act_version_id = version_id
            chunk.act_version_id = version_id
            provision.id = self._store.insert_provision(provision)
            chunk.provision_id = provision.id

        embeddings = self._embedder.embed_passages([c.text for c in chunks])
        self._vector.batch_upsert(list(zip([p.id for p in provisions], embeddings)))
```

- [ ] **Step 4: Implement `batch_upsert` in `PostgresVectorStore`**

Replace the `NotImplementedError` stub added in Task 3 with the real implementation in `src/lawboi/adapters/vector/pgvector.py`:

```python
def batch_upsert(self, pairs: list[tuple[int, list[float]]]) -> None:
    if not pairs:
        return
    with pooled_cursor(self._pool) as cur:
        from psycopg2.extras import execute_values
        execute_values(
            cur,
            """
            UPDATE provision SET embedding = data.emb::vector
            FROM (VALUES %s) AS data(id, emb)
            WHERE provision.id = data.id::int
            """,
            [(pid, _vec(emb)) for pid, emb in pairs],
        )
```

- [ ] **Step 5: Update `StubEmbedder` in `test_service.py` to expose `embed_passages`**

The existing `StubEmbedder` in `tests/lawboi/ingest/test_service.py` only has `embed_passage`. Add `embed_passages`:

```python
class StubEmbedder:
    def embed_passage(self, text): return [0.1]
    def embed_passages(self, texts): return [[0.1]] * len(texts)
```

- [ ] **Step 6: Run full test suite**

```bash
.venv/bin/python -m pytest -v
```

Expected: all tests PASS including `test_index_act_uses_batch_embedding`.

- [ ] **Step 7: Commit**

```bash
git add src/lawboi/ingest/service.py \
        src/lawboi/adapters/vector/pgvector.py \
        tests/lawboi/fakes.py \
        tests/lawboi/ingest/test_service.py
git commit -m "perf: batch embeddings and vector upsert in IngestService — single model call per act"
```

---

## Task 8: Fix rate limiter proxy trust

**Problem:** `slowapi` uses `get_remote_address` which returns the direct TCP peer address. Behind nginx or a cloud load balancer, all requests appear to come from the proxy IP, making the rate limit apply to the proxy rather than individual users.

**Fix:** Use `uvicorn`'s `--proxy-headers` flag for forwarded IP extraction at the ASGI level, and switch the limiter to `get_ipaddr` which reads `X-Forwarded-For`. Add a configurable `trusted_proxies` setting.

**Files:**
- Modify: `src/lawboi/api/limiter.py`
- Modify: `src/lawboi/api/main.py`
- Modify: `src/lawboi/config/settings.py`
- Test: `tests/lawboi/api/test_routes.py` — smoke test that the rate limiter still initialises

---

- [ ] **Step 1: Add `trusted_proxies` to `Settings`**

In `src/lawboi/config/settings.py`:

```python
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    cohere_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    db_pool_min: int = 1
    db_pool_max: int = 10
    cors_origins: list[str] = ["http://localhost:3000"]
    answer_rate_limit: str = "10/minute"
    search_rate_limit: str = "30/minute"
    trusted_proxies: list[str] = []   # e.g. ["10.0.0.0/8"] for internal load balancer


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 2: Switch limiter key function to `get_ipaddr`**

Replace `src/lawboi/api/limiter.py`:

```python
from slowapi import Limiter
from slowapi.util import get_ipaddr

limiter = Limiter(key_func=get_ipaddr)
```

`get_ipaddr` reads `X-Forwarded-For` header first (honoring the proxy header), then falls back to `REMOTE_ADDR`. This is the standard `slowapi` recommendation for deployments behind a proxy.

- [ ] **Step 3: Add `ProxyHeadersMiddleware` to `main.py`**

In `src/lawboi/api/main.py`, add the middleware so FastAPI/Starlette propagates `X-Forwarded-For` to the request object:

```python
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.proxy_headers import ProxyHeadersMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from lawboi.api.errors import register_exception_handlers
from lawboi.api.limiter import limiter
from lawboi.config.settings import load_settings

_settings = load_settings()

app = FastAPI(title="Eesti Õigusabi API", version="0.2.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

if _settings.trusted_proxies:
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=_settings.trusted_proxies)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

from lawboi.api.routes import answer, search, acts  # noqa: E402

app.include_router(answer.router)
app.include_router(search.router)
app.include_router(acts.router)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Run full test suite**

```bash
.venv/bin/python -m pytest -v
```

Expected: all tests PASS. The health check and rate-limited route tests should still pass since behaviour is unchanged when `trusted_proxies` is empty.

- [ ] **Step 5: Commit**

```bash
git add src/lawboi/api/limiter.py \
        src/lawboi/api/main.py \
        src/lawboi/config/settings.py
git commit -m "fix: switch rate limiter to get_ipaddr and add ProxyHeadersMiddleware for proxy deployments"
```

---

## Self-Review

**Spec coverage check** — all 18 identified issues mapped to tasks:

| Issue | Task |
|-------|------|
| `ctx._done` runtime attribute | Task 1 |
| `Container.store: object` | Task 1 |
| Cursor not closed | Task 1 |
| `_parse_effective_date` private import | Task 1 |
| `_hit_to_dict` / `_rp_to_dict` identical | Task 2 |
| Metadata dict duplicated in two adapters | Task 2 |
| Dense search ignores effective date | Task 3 |
| `Merge` is a no-op | Task 4 |
| Fetch counts hardcoded in stage bodies | Task 4 |
| `AnswerRequest.model` silently ignored | Task 5 |
| `DISCLAIMER` duplicated in prompt | Task 5 |
| XML parsed 3× per ingest call | Task 6 |
| Embeddings not batched | Task 7 |
| `batch_upsert` missing | Task 7 |
| Rate limiter IP-blind behind proxy | Task 8 |
| `detect_language` naive heuristic | (deferred — out of scope, not a bug) |
| `domain` always "general" | (deferred — requires RT API data; not a code quality issue) |
| pgvector vector string encoding | (deferred — requires `psycopg3` migration; too invasive) |

**Placeholder scan:** All steps contain actual code. No TBDs or "similar to task N" patterns.

**Type consistency:** `VectorStore.query(embedding, n_results, as_of)` is defined in Task 3 and used consistently in all later task references. `batch_upsert` stub is added in Task 3 and completed in Task 7. `parse_act()` returns `ParsedAct` with `.title`, `.effective_from`, `.effective_to`, `.provisions` — all used correctly in Task 6's `__main__.py` update.
