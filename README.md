# Eesti Õigusabi

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
  answer/      prompts, citation extraction, AnswerService
  config/      settings, composition root
  api/         FastAPI app: /answer, /models, /search, /acts/:eli, /health
ui/            Next.js 15 chat interface with source panel and model selector
eval/          gold set (30 Q&As) + evaluation runner
db/            schema.sql (Postgres + pgvector)
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

With Postgres running, ingest an act by abbreviation, title substring, or numeric globaalID:

```bash
python -m lawboi.ingest "TLS"
python -m lawboi.ingest "töölepingu seadus"
python -m lawboi.ingest 13198023
```

Re-running the same act is safe — existing versions are skipped.

> **Note:** The RT API endpoint format (`RT_BASE_URL` in `.env`) should be verified against real Riigiteataja responses before running at scale.

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

Integration tests that need a live Postgres are skipped automatically when `DATABASE_URL` is unset.

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

`/answer` is rate limited to 10/min and `/search` to 30/min per IP.

## Important Notes

- **No answer without sources** — if no relevant provisions are found, the API returns 422
- **Estonian is authoritative** — English translations are assistive only
- **Not legal advice** — every response includes a disclaimer; this tool provides legal information only
- XML tag names in `src/lawboi/adapters/source/parser.py` (`TAGS` dict) may need adjustment after verifying against real RT XML
