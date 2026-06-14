# Eesti Õigusabi — MVP Design Spec

**Date:** 2026-03-31
**Status:** Approved
**Scope:** Phase 0 + Phase 1 implementation

---

## 1. Goal

Build a source-cited Estonian law assistant targeting accountants (tax, employment, company law). Users ask questions in Estonian or English; the system retrieves provisions from Riigi Teataja, generates grounded answers with exact citations, and never produces uncited claims.

---

## 2. Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| LLM | Configurable (default: Gemini 2.0 Flash) | Swappable via env var; Gemini 2.0 Flash is cheapest default |
| Embeddings | `multilingual-e5-large` (local) | Runs locally, strong Estonian support, ~2GB RAM |
| Vector DB | ChromaDB | Simple, Python-native, embedded or server mode |
| Structured DB | PostgreSQL 16 | Matches existing phase docs; rich query support |
| RAG framework | LlamaIndex | Built for document hierarchies; good hybrid retrieval |
| Backend | FastAPI (Python) | Lightweight, async, matches phase-1 API surface |
| Frontend | Next.js (TypeScript) | Production-grade UI with source panel and citation display |
| Infra | Docker Compose | Single command local dev; all services declared |
| Evaluation | Custom `run_eval.py` | Loops gold set against `/answer` endpoint |

---

## 3. Architecture

### Runtime Phases

```
INGEST (offline script, run on demand / weekly cron)
  scraper → parser → chunker → embedder → indexer
      │
      ├── writes to PostgreSQL (structured metadata)
      └── writes to ChromaDB (provision vectors)

QUERY (online, per request)
  Next.js UI
    → FastAPI backend
        → LlamaIndex QueryEngine
            → hybrid retrieval (ChromaDB + PG tsvector)
            → metadata date filter
            → reranker
            → Gemini 2.0 Flash
            → citation extractor + disclaimer injector
    → JSON response with citations
```

### Project Layout

```
lawboi/
├── notebooks/              ← validation stages (scraping, parsing, retrieval)
├── ingest/
│   ├── scraper.py          ← fetches RT acts via open data API
│   ├── parser.py           ← XML → structured Provision nodes
│   ├── chunker.py          ← hierarchical chunking
│   └── indexer.py          ← embeds + writes to Chroma + PG
├── retrieval/
│   └── engine.py           ← LlamaIndex QueryEngine + reranker
├── answer/
│   └── pipeline.py         ← prompt builder + Gemini call + citation attach
├── api/
│   └── main.py             ← FastAPI app
├── ui/                     ← Next.js (TypeScript)
│   ├── app/
│   └── components/
├── db/
│   └── schema.sql
├── eval/
│   ├── gold_set.json
│   └── run_eval.py
├── docker-compose.yml
└── .env.example
```

---

## 4. Data Pipeline

### Acquisition
- Source: Riigi Teataja XML bulk export via open data API (verify exact endpoint at `https://www.riigiteataja.ee/api/` — confirm in week-1 notebook)
- Rate limit: 1 request/second
- Raw files stored locally with hash + source URL per document
- Priority acts: `MaksukorraldusSeadus`, `KäibemaksuSeadus`, `TöölepinguSeadus`, `ÄriSeadustik`

### Parsing
Each act XML is walked top-down:

```
Act → Part (osa) → Chapter (peatükk) → Section (§) → Subsection (lõige) → Clause (punkt)
```

Each `Provision` node carries: `act_id`, `version_id`, `eli`, `section_number`, `level`, `text_et`, `text_en`, `effective_from`, `effective_to`, `parent_id`.

### Chunking Strategy

| Level | Size | Purpose |
|---|---|---|
| Provision (§ + subsections) | 300–600 tokens | Primary retrieval unit |
| Context window (provision ± 1 neighbour) | 800–1200 tokens | Sent to LLM for generation |
| Act summary | ~200 tokens | Act-level keyword queries |

### Freshness
`publication_event` table records last-seen hash per act. Ingest script re-parses and re-indexes only changed acts when hash differs.

---

## 5. PostgreSQL Schema

```sql
act            (id, eli, title_et, title_en, domain, act_type)
act_version    (id, act_id, effective_from, effective_to, source_url, hash)
provision      (id, act_version_id, section_num, level, text_et, text_en, parent_id)
publication_event (id, act_id, detected_at, hash_before, hash_after)
query_log      (id, query, retrieved_provision_ids, answer, created_at)
```

---

## 6. Retrieval Pipeline

### Flow

```
User query
  │
  ├─► Query classifier (LlamaIndex router)
  │       ├─ Citation ref (e.g. "§ 42") → exact PG lookup
  │       ├─ Date reference → apply effective_date filter
  │       └─ General → hybrid retrieval
  │
  ├─► Hybrid retrieval
  │       ├─ Dense: ChromaDB cosine similarity (multilingual-e5-large)
  │       └─ Sparse: PostgreSQL tsvector over provision text
  │       → merge + deduplicate top-20 candidates
  │
  ├─► Hard metadata filter
  │       └─ effective_from ≤ query_date ≤ effective_to
  │
  └─► Reranker (LlamaIndex CohereRerank — free tier sufficient for MVP)
          └─ top-5 provisions → context window expansion → LLM
```

### Embeddings
`intfloat/multilingual-e5-large` via `sentence-transformers`.
Prefix convention: `"query: "` for queries, `"passage: "` for indexed provisions.

---

## 7. Answer Generation

### LLM Provider Factory

`answer/pipeline.py` resolves the LLM from environment config, keeping the rest of the pipeline unchanged:

```python
# Supported models
SUPPORTED_MODELS = {
    "gemini-2.0-flash":  "google",
    "gemini-1.5-pro":    "google",
    "gpt-4o":            "openai",
    "gpt-4o-mini":       "openai",
    "claude-sonnet-4-5": "anthropic",
}

def get_llm():
    model = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    provider = SUPPORTED_MODELS[model]
    if provider == "google":
        return Gemini(model=model, api_key=os.getenv("GEMINI_API_KEY"))
    elif provider == "openai":
        return OpenAI(model=model, api_key=os.getenv("OPENAI_API_KEY"))
    elif provider == "anthropic":
        return Anthropic(model=model, api_key=os.getenv("ANTHROPIC_API_KEY"))
    raise ValueError(f"Unsupported model: {model}")
```

The `/answer` endpoint optionally accepts `"model"` in the request body to override the server default, enabling per-request model selection from the UI.

### System Prompt

```
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
7. Always append the disclaimer block below at the end of every response.

DISCLAIMER:
⚠️ See vastus on üldine õiguslik teave, mitte õigusabi. / This is general legal
information, not legal advice. Consult a qualified lawyer for your specific situation.
Official source: riigiteataja.ee

RETRIEVED PROVISIONS:
{context}

USER QUESTION:
{query}
```

### Answer Request (Next.js → FastAPI)

```json
{
  "query": "string",
  "model": "gemini-2.0-flash",
  "as_of_date": "YYYY-MM-DD | null"
}
```

### Response Object (FastAPI → Next.js)

```json
{
  "answer": "string",
  "model_used": "gemini-2.0-flash",
  "citations": [
    {
      "act_title": "Töölepingu seadus",
      "section": "§ 42",
      "subsection": "lg 1",
      "eli": "RT I 2009, 5, 35",
      "url": "https://www.riigiteataja.ee/akt/..."
    }
  ],
  "language_detected": "et | en",
  "translation_warning": true,
  "disclaimer": "string"
}
```

---

## 8. MVP API Surface

Matches phase-1 docs:

| Method | Endpoint | Description |
|---|---|---|
| POST | `/answer` | Hybrid retrieval + grounded answer (accepts optional `model` field) |
| POST | `/search` | Provision search, returns ranked results |
| GET | `/acts/:eli` | Full act metadata |
| GET | `/acts/:eli/versions` | All versions of an act |
| GET | `/acts/:eli/as-of?date=YYYY-MM-DD` | Versioned text at a given date |
| GET | `/models` | Returns list of available models (those with a configured API key) |

---

## 9. Next.js UI (MVP Pages)

| Page | Description |
|---|---|
| `/` | Chat interface with message history |
| Source panel | Slide-out panel showing cited provisions with RT links |
| Act viewer | Full provision text for a cited act |
| As-of selector | Date picker to query historical wording |
| Model selector | Dropdown to choose LLM (Gemini 2.0 Flash / Gemini 1.5 Pro / GPT-4o / GPT-4o Mini / Claude Sonnet); only shows models with a configured API key |

---

## 10. Docker Compose

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: lawboi
      POSTGRES_USER: lawboi
      POSTGRES_PASSWORD: lawboi
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./db/schema.sql:/docker-entrypoint-initdb.d/schema.sql

  chroma:
    image: chromadb/chroma:latest
    volumes:
      - chroma_data:/chroma/chroma
    ports:
      - "8001:8000"

  api:
    build: ./api
    environment:
      DATABASE_URL: postgresql://lawboi:lawboi@db:5432/lawboi
      CHROMA_HOST: chroma
      CHROMA_PORT: 8000
      LLM_MODEL: ${LLM_MODEL:-gemini-2.0-flash}   # default, overridable
      GEMINI_API_KEY: ${GEMINI_API_KEY:-}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
    ports:
      - "8000:8000"
    depends_on:
      - db
      - chroma

  ui:
    build: ./ui
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000   # browser → API (public)
      API_URL: http://api:8000                     # server-side Next.js → API (internal)
    ports:
      - "3000:3000"
    depends_on:
      - api

volumes:
  pg_data:
  chroma_data:
```

Ingest script runs outside Compose: `python -m ingest.indexer`

---

## 11. Evaluation

### Gold Test Set (30–50 entries in `eval/gold_set.json`)

| Category | Count |
|---|---|
| Exact section lookup | 10 |
| Current-law applicability | 10 |
| Historical-law query | 5 |
| Missing-fact / clarification needed | 5 |
| Unsupported / should refuse | 5 |
| Cross-act reasoning | 5 |

Each entry: `query`, `expected_citations` (ELI + section list), `expected_answer_contains`, `should_refuse`.

### Metrics (MVP targets)

| Metric | Target |
|---|---|
| Citation precision | ≥ 85% |
| Citation recall | ≥ 75% |
| Faithfulness (LLM-as-judge) | ≥ 90% |
| Refusal on unsupported queries | 100% |
| Language match | ≥ 98% |

### Observability
Every query written to `query_log` with `retrieved_provision_ids` and raw answer. Forms replay dataset for Phase 2 reviewer queue.

---

## 12. 8-Week Roadmap

| Week | Focus | Deliverables |
|---|---|---|
| 1 | Data pipeline | RT API scraper, raw XML stored, PG schema running |
| 2 | Parser + chunker | Provision nodes in PG, hierarchy validated in notebook |
| 3 | Embeddings + indexing | ChromaDB populated, similarity search working |
| 4 | Retrieval pipeline | LlamaIndex QueryEngine, hybrid search, date filtering |
| 5 | Answer generation | Gemini integration, system prompt, citation extraction |
| 6 | FastAPI + Next.js UI | `/answer` + `/search` endpoints, chat UI with source panel |
| 7 | Evaluation | Gold set built, `run_eval.py` passing, top failures fixed |
| 8 | Polish + demo | Docker Compose, README, disclaimers, pilot-ready |

---

## 13. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| RT API structure changes | Store raw XML snapshots; parser is isolated module |
| Estonian tokenization quality | Validate embedding recall on gold set in week 3 |
| Gemini hallucination | Strict grounding prompt + faithfulness eval gate |
| Historical date bugs | Dedicated gold set category; hard filter before LLM |
| EU AI Act transparency | Disclaimer on every response; no legal advice claim |
| Data freshness lag | `publication_event` hash check; weekly cron alert |

---

## 14. Out of Scope (MVP)

- Case law and court decisions (Phase 2)
- Secondary regulations (Phase 2)
- Fine-tuning (Phase 2, only after retrieval is stable)
- Multi-tenancy (Phase 3)
- User document upload (Phase 3)
