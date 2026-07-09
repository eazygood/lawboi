# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Start infrastructure (required for tests and local dev)
docker-compose up -d db

# Run all tests (107 tests, no live LLM or RT API calls)
.venv/bin/python -m pytest

# Run a specific test file or directory
.venv/bin/python -m pytest tests/lawboi/adapters/source/test_parser.py
.venv/bin/python -m pytest tests/lawboi/

# Start API locally (after activating .venv and starting infra)
uvicorn lawboi.api.main:app --reload --port 8000

# Ingest a law by abbreviation, title substring, or numeric globaalID
python -m lawboi.ingest "TLS"
python -m lawboi.ingest "töölepingu seadus"
python -m lawboi.ingest 13198023

# Run evaluation against live API
python eval/run_eval.py --api http://localhost:8000

# Frontend
cd ui && nvm use && npm install && npm run dev
```

Use `.venv/bin/python` explicitly — the project uses Python 3.12+ in a venv.

The package lives under `src/lawboi/` (src layout). After installing requirements, link it once so `import lawboi` resolves: `pip install -e . --no-deps`. Tests work without this step (pytest's `pythonpath = ["src"]` in `pyproject.toml`), but `uvicorn`, `python -m lawboi.ingest`, and `eval/` need the editable install.

## Architecture

Hexagonal-lite: `domain → ports → adapters → application services → interface (API/CLI)`.

```
src/lawboi/
  domain/         models.py  errors.py  dto.py
  ports/          llm.py  vector_store.py  structured_store.py  law_source.py
  adapters/
    llm/          gemini.py  openai.py  anthropic.py  registry.py  factory.py
    structured/   pool.py  postgres.py
    vector/       pgvector.py
    source/       parser.py  riigiteataja.py  riigiteataja_client.py
  pipeline/       context.py  stages.py  retrieval.py
  ingest/         embedder.py  chunker.py  service.py  __main__.py
  answer/         prompts.py  citations.py  moderation.py  service.py
  config/         settings.py  composition.py
  api/            main.py  schemas.py  errors.py  deps.py  limiter.py  routes/
```

**Offline ingest pipeline** (`src/lawboi/ingest/`): entry point `python -m lawboi.ingest`. Writes to PostgreSQL (structured store + pgvector) via `IngestService`.

**Online API** (`src/lawboi/api/`): FastAPI app. `RetrievalService` (pipeline of stages) reads from both stores; `AnswerService` calls the LLM. Services only read — they never write. Wired via `build_container(Settings())` in `src/lawboi/config/composition.py`.

**Frontend** (`ui/`): Next.js 15 App Router app. Reads the Next.js docs from `node_modules/next/dist/docs/` before writing any code (see `ui/AGENTS.md`).

## Data Model

Single PostgreSQL database (using the `pgvector/pgvector:pg16` image), two logical layers:

- **Structured store** (`adapters/structured/postgres.py`): `act` → `act_version` → `provision` hierarchy. `act_version` tracks historical versions via `effective_from`/`effective_to` dates. FTS index on `provision.text_et` using the `simple` dictionary (language-agnostic tokenisation, correct for Estonian).
- **Vector store** (`adapters/vector/pgvector.py`): `PostgresVectorStore` stores 1024-dim `multilingual-e5-large` embeddings as pgvector columns on the `provision` table. Both stores share the same connection pool.
- **Conversation history** (`db/migrations/002_conversations.sql`, included in fresh `db/schema.sql`): flat `conversation` → `message` tables for multi-turn support. Port methods on `StructuredStore`: `create_conversation()`, `append_message(conversation_id, role, content)`, `recent_messages(conversation_id, limit=10)`. No summarization — history is passed to the LLM verbatim.

## Key Invariants

**No answer without sources.** `POST /answer` returns 422 if retrieval returns an empty list. `AnswerService.answer()` raises `NoSourcesFoundError` → mapped to 422 by `src/lawboi/api/errors.py`. Don't break this gate.

**Retrieval pipeline stages are async; the three search stages run concurrently.** `build_pipeline` in `composition.py` wires: `CitationShortCircuit` (exact §-lookup, sets `ctx.done = True` to skip remaining stages) → `ParallelSearch([DenseSearch, SparseSearch, ProceduralAugment])` → `StepBackExpand` (LLM-abstracted query) → `Rerank`. `ParallelSearch` runs its three stages via `asyncio.gather` and merges their independently-ranked hit lists with Reciprocal Rank Fusion (`stages.py:_rrf_merge`) — RRF is the only ranking signal when no reranker is configured. Because they run concurrently, `DenseSearch`/`SparseSearch`/`ProceduralAugment` must not mutate shared `ctx` state: each returns its own `list[dict]`; only `ParallelSearch` writes into `ctx`. `StepBackExpand` is bounded by `RetrievalConfig.step_back_timeout_s` — on timeout or LLM error it logs and returns `ctx` unchanged rather than failing the request. Tests must not assert that any embedder or store method is called exactly once.

**Reranker is a no-op stage when `COHERE_API_KEY` is unset.** `Rerank` stage in `src/lawboi/pipeline/stages.py` skips reranking when `self._reranker is None`. Built in `src/lawboi/config/composition.py:_build_reranker`.

**Citations are forced structured output, not parsed from free text.** `AnswerService.answer()` calls `LLMProvider.complete_structured(prompt, AnswerPayload)` (`ports/llm.py`) rather than `complete()` + regex. `validate_citations()` (`answer/citations.py`) drops any citation whose section doesn't match a provision actually retrieved for the request — this is the only defense against hallucinated citations; don't reintroduce free-text extraction.

**Moderation runs on both input and output, via the active LLM.** `ModerationService.check()` (`answer/moderation.py`) reuses `complete_structured()` with a classification prompt — there's no dedicated moderation endpoint since only LlamaIndex wrapper packages are installed. The input check runs concurrently with retrieval (`asyncio.gather` in `api/routes/answer.py`) so it doesn't add a blocking round-trip before real work starts; a flagged input raises `ContentBlockedError` → 400 (`api/errors.py`). The output check is necessarily sequential (it needs the generated answer); a flagged answer is replaced with a generic refusal message rather than returned or raised.

**DB access is fully async, via psycopg3 — including ingest.** `adapters/structured/pool.py:make_pool()` returns a `psycopg_pool.AsyncConnectionPool[AsyncConnection]`; every `StructuredStore`/`VectorStore` port method, both online and in the offline ingest path, is `async def`. There is no separate sync path for ingest.

**Corpus ingest (`--all`) is concurrency-bounded and interrupt-safe.** `ingest/__main__.py:run_corpus()` drains a work queue through `--concurrency` workers (default 5) via `asyncio.gather`. Ctrl-C (`SIGINT`) sets a `shutdown` event that stops workers from pulling new items but lets in-flight fetch+index calls finish — safe to interrupt, since the next run's `ingested_global_ids()` skip-set picks up wherever it left off.

**Parser strips XML namespaces.** `src/lawboi/adapters/source/parser.py:_parse_xml()` uses `iterparse` to strip all `{namespace}` prefixes before matching. `TAGS` uses bare local names (`paragrahv`, `loige`, etc.). Section numbers are read from the `nr` attribute. The actual RT API namespace is unverified — the `TAGS` dict may need updating after testing against real XML.

**`fetch_act_xml` accepts a string ELI** (e.g. `"RT I 2009, 5, 35"`) and converts it to a slug for the `/api/seadus/RT_I_2009_5_35` endpoint. The ingest CLI passes numeric globaalID as a string — this path is untested against the real API.

**LLM model selection** in `src/lawboi/adapters/llm/factory.py`: auto-selects by priority (Gemini → OpenAI → Anthropic), or pinned via `LLM_MODEL` env var. **Adding a model = one `ModelSpec` tuple in `src/lawboi/adapters/llm/registry.py:REGISTRY`** — no other files need updating.
