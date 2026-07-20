# ParagrahvAI

A source-cited Estonian law RAG chatbot for accountants. Ask questions about Estonian tax, employment, and company law — every answer cites the exact legal provision from Riigi Teataja.

## Architecture

Hexagonal-lite: `domain → ports → adapters → application services → interface (API/CLI)`.
Application code lives under `src/lawboi/` (src layout):

```
src/lawboi/
  domain/      models, errors, DTOs
  ports/       Protocols: llm, vector_store, structured_store, law_source
  adapters/    llm/ (gemini, openai, anthropic, registry, factory)
               structured/ (pool, postgres)   vector/ (pgvector)
               source/ (parser, riigiteataja)
  pipeline/    retrieval stages + RetrievalService
  ingest/      offline pipeline: parse XML → chunk → embed → write (PG + vectors)
  answer/      prompts, structured citations, LLM-based moderation, AnswerService
  config/      settings, composition root
  api/         FastAPI app: /answer, /models, /search, /acts/:eli, /health
ui/            Next.js 15 chat interface with source panel and model selector
eval/          gold set (30 Q&As) + evaluation runner
db/            schema.sql (Postgres + pgvector) + migrations/ for existing databases
```

Embeddings are stored in the `provision.embedding` `vector(1024)` column — there is no
separate vector store. Retrieval reads dense (pgvector) and sparse (Postgres FTS) from
the same database.

## Tech Stack

| Layer | Choice |
|---|---|
| LLM | Configurable — default Gemini 2.0 Flash; also GPT-4o, GPT-4o Mini, Claude Sonnet |
| Embeddings | `intfloat/multilingual-e5-large` (local, via sentence-transformers), 1024-dim |
| Vector search | pgvector (HNSW, cosine) — in Postgres |
| Structured DB | PostgreSQL 16 |
| LLM / rerank framework | LlamaIndex |
| Backend | FastAPI (Python 3.12) |
| Frontend | Next.js 15 (TypeScript, App Router, Tailwind) |
| Infra | Docker Compose |
| Reranker | Cohere Rerank (optional — no-op when `COHERE_API_KEY` is unset) |
| DB driver | psycopg3, fully async (`AsyncConnectionPool`) end-to-end, including ingest |

## Running locally

**Requirements:** Docker, Python 3.12+, Node.js 22+ (use `nvm use` if you have `.nvmrc`)

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` — set at least one LLM key (Cohere is optional, used for reranking):

```
GEMINI_API_KEY=...       # generativeai.google.com
OPENAI_API_KEY=...       # platform.openai.com
ANTHROPIC_API_KEY=...    # console.anthropic.com
COHERE_API_KEY=...       # cohere.com (optional)
```

`LLM_MODEL` defaults to the first provider with a configured key (Gemini → OpenAI → Anthropic). Pin a specific model explicitly:

```
LLM_MODEL=gpt-4o
```

### 2. Option A — full stack via Docker Compose

```bash
docker-compose up --build
```

| Service    | URL                        |
|------------|----------------------------|
| UI         | http://localhost:3000      |
| API        | http://localhost:8000      |
| API docs   | http://localhost:8000/docs |
| PostgreSQL | localhost:5432             |

### 2. Option B — infrastructure in Docker, services run locally

```bash
# Start Postgres (with pgvector)
docker-compose up -d db

# Python backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e . --no-deps          # link the src/lawboi package so `import lawboi` resolves
uvicorn lawboi.api.main:app --reload --port 8000

# Next.js frontend (separate terminal — ensure port 3000 is free)
cd ui && nvm use && npm install && npm run dev
```

### 3. Ingest laws

With Postgres running, ingest a single act by abbreviation, title substring, or numeric globaalID:

```bash
python -m lawboi.ingest "TLS"
python -m lawboi.ingest "töölepingu seadus"
python -m lawboi.ingest 13198023
```

Or crawl the whole corpus and ingest the current in-force text of every act. By default
this covers acts (`seadus`) and regulations/decrees (`määrus`) — the binding primary and
secondary legislation (configurable via `CORPUS_DOC_TYPES`):

```bash
python -m lawboi.ingest --all
python -m lawboi.ingest --all --concurrency 10   # default is 5
python -m lawboi.ingest --all --doc-type seadus  # crawl+ingest only one doc type
```

> `määrus` is a large category (many thousands of regulations), so the first full crawl
> takes hours and produces a large embedding set. Run it once locally, then back it up
> with `python scripts/corpus_dump.py export` (writes `db/corpus.dump`, gitignored — see
> [Corpus backup](#corpus-backup)) and let incremental re-runs keep it current.

> `--all` runs `--concurrency` acts through fetch+index at once. Ctrl-C stops handing out
> new work but lets in-flight acts finish before exiting — safe to interrupt, since
> already-ingested acts are skipped on the next run anyway.

**Incremental by default.** Each act's ingested Riigi Teataja redaktsioon is tracked by
its `globaalID` (`act_version.source_global_id`). On re-runs, `--all` pages the corpus
index but **skips already-ingested acts before downloading their XML**, so only new or
amended acts are fetched and embedded. It prints `ingested N, skipped M unchanged`. This
makes `--all` safe and cheap to run on a schedule (e.g. a nightly cron). When a new
redaktsioon is ingested, the prior version's `effective_to` is closed automatically so
date-filtered retrieval returns only the current text.

Use `--all --force` to re-fetch and re-embed every act regardless of the skip set — only
needed after a parser or embedding change.

> **Existing databases:** the skip set relies on the `act_version.source_global_id`
> column. Fresh installs get it from `db/schema.sql`; apply it to an already-initialised
> DB before ingesting with `psql "$DATABASE_URL" -f db/migrations/001_source_global_id.sql`.

> **Existing databases, multi-turn support:** fresh installs get the `conversation`/
> `message` tables from `db/schema.sql`; apply them to an already-initialised DB with
> `psql "$DATABASE_URL" -f db/migrations/002_conversations.sql`.

> **Note:** The RT API endpoint format (`RT_BASE_URL` in `.env`) should be verified against real Riigiteataja responses before running at scale.

### Semantic answer cache

`/answer` checks a semantic cache (`answer_cache` table, pgvector cosine similarity
≥0.97, scoped to the request's `as_of` date) before calling the LLM — repeated or
near-duplicate questions skip retrieval and generation entirely. See
`src/lawboi/adapters/vector/answer_cache.py`.

**The cache is invalidated automatically whenever the corpus changes.** `run_ingest`
and `run_corpus` (i.e. any `python -m lawboi.ingest ...` call that actually indexes at
least one act) clear the entire cache on completion, so a citation/data fix or a fresh
ingest can never keep serving a stale cached answer. Cached rows also expire on their
own after `cache_retention_days` (default 30).

To invalidate manually — e.g. after a direct DB fix that didn't go through `run_ingest`
(as happened once while fixing the citation-link bug) — run:

```bash
python -m lawboi.ingest --clear-cache
```

### 4. Try it

```bash
# Semantic question (Estonian)
curl -s -X POST http://localhost:8000/answer \
  -H "Content-Type: application/json" \
  -d '{"query": "Mis on katseaja kestus töölepingus?"}' | jq .

# Citation-style query with historical date
curl -s -X POST http://localhost:8000/answer \
  -H "Content-Type: application/json" \
  -d '{"query": "Töölepingu seadus § 86", "as_of_date": "2022-01-01"}' | jq .

# Search provisions directly
curl -s -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "puhkus", "limit": 5}' | jq .

# Multi-turn: pass back the conversation_id from a prior /answer response to continue
# the thread (the last 5 turns are sent to the LLM verbatim as context)
curl -s -X POST http://localhost:8000/answer \
  -H "Content-Type: application/json" \
  -d '{"query": "Ja mis saab, kui tööandja seda ei järgi?", "conversation_id": 1}' | jq .
```

## Running tests

Tests require Postgres running (no live LLM or RT API calls):

```bash
docker-compose up -d db
```

```bash
# All tests
.venv/bin/python -m pytest

# Verbose
.venv/bin/python -m pytest -v

# Specific module
.venv/bin/python -m pytest tests/lawboi/adapters/source/test_parser.py
.venv/bin/python -m pytest tests/lawboi/

# With coverage
.venv/bin/python -m pytest --cov=lawboi --cov-report=term-missing
```

Integration tests under `tests/lawboi/adapters/` need a live Postgres and run against an
isolated test DB, never the dev DB — see [Isolated test DB](#isolated-test-db) below.
They're skipped automatically when `TEST_DATABASE_URL` is unset.

### Isolated test DB

`tests/lawboi/adapters/` reads `TEST_DATABASE_URL` — a distinct env var from the app's
`DATABASE_URL` — so it can never write into the dev/manual-testing database. Start the
dedicated container and point the suite at it:

```bash
docker-compose -f docker-compose.test.yml up -d db-test
TEST_DATABASE_URL=postgresql://lawboi:lawboi@localhost:5433/lawboi \
  .venv/bin/python -m pytest tests/lawboi/adapters/ -v
```

Each test that touches the DB truncates its tables afterward, so runs are repeatable with
no manual cleanup. Never set `TEST_DATABASE_URL` to the same value as `DATABASE_URL`.

## Corpus backup

Ingest can take hours for a full crawl, so back up the ingested corpus (`act`,
`act_version`, `provision`, including embeddings) once you have a good dataset, rather
than re-ingesting from scratch after a DB reset:

```bash
python scripts/corpus_dump.py export   # dev db (lawboi-db-1) -> db/corpus.dump
python scripts/corpus_dump.py import   # db/corpus.dump -> dev db (lawboi-db-1)
```

`db/corpus.dump` is gitignored — it's a large binary and fully regenerable from Riigi
Teataja, so it isn't committed. Keep your own copy (local disk, cloud storage, etc.)
if you want to avoid re-ingesting. `import` warns rather than overwrites if the dev DB
already has rows — `pg_restore` errors on conflicting primary keys instead of
duplicating, so restore into a freshly-reset DB (`db/schema.sql` applied, tables empty).

## Evaluation

Run the gold-set eval against a live API:

```bash
python eval/run_eval.py --api http://localhost:8000
```

Targets: citation precision ≥85%, citation recall ≥75%, refusal accuracy 100%.

## Deployment

See [`docs/deploy.md`](docs/deploy.md) for the DigitalOcean deployment guide — managed
Postgres + pgvector, embedding the corpus locally and shipping it with a single
`pg_dump`/`pg_restore`, env configuration, and verification.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/answer` | Ask a legal question, get a cited answer |
| `GET` | `/models` | List available LLM models |
| `POST` | `/search` | Search provisions directly |
| `GET` | `/acts/{eli}` | Get act metadata by ELI |
| `GET` | `/acts/{eli}/versions` | List all versions of an act |
| `GET` | `/acts/{eli}/as-of?date=` | Get provisions effective on a date |
| `GET` | `/health` | Health check |

`/answer` is rate limited to 10/min and `/search` to 30/min per IP (configurable via the
`ANSWER_RATE_LIMIT`/`SEARCH_RATE_LIMIT` env vars). The production image runs
`uvicorn --workers 4`; slowapi's rate-limit counters are in-memory per worker, so
effective per-IP limits multiply across workers — not exact under multi-worker.

## TODO

- **Schedule automated corpus ingest.** `--all` is already safe to re-run (see
  [Ingest laws](#3-ingest-laws)) — it re-crawls the full Riigi Teataja index, skips
  already-ingested `globaalID`s, and closes out superseded versions without losing any
  historical text/embeddings. Nothing currently triggers it automatically though. Add a
  weekly job (weekend night, low-traffic window — e.g. Sunday ~02:00 UTC) running
  `python -m lawboi.ingest --all --concurrency 5` against the live `DATABASE_URL`, e.g.
  via a GitHub Actions scheduled workflow or a cron/systemd timer on the deploy box (see
  [Deployment](#deployment)). Note: `build_container` always constructs an LLM client
  even for ingest, so the job needs an LLM API key secret configured even though ingest
  itself never calls the LLM.

## Important Notes

- **No answer without sources** — if no relevant provisions are found, the API returns 422
- **Estonian is authoritative** — English translations are assistive only
- **Not legal advice** — every response includes a disclaimer; this tool provides legal information only
- **Multi-turn conversations** — omit `conversation_id` to start a new thread (every response
  returns one); pass it back on the next call to continue. History is the last 5 turns, sent
  to the LLM verbatim — no summarization.
- **Citations are enforced, not parsed** — the LLM returns structured output (answer +
  citations) rather than free text; any citation that doesn't match a provision actually
  retrieved for the request is dropped before the response is sent.
- **Content moderation** — both the question and the generated answer are checked via an
  LLM-based classifier. Flagged input is rejected (400); a flagged answer is replaced with a
  generic refusal message rather than returned as-is.
- XML tag names in `src/lawboi/adapters/source/parser.py` (`TAGS` dict) may need adjustment after verifying against real RT XML
