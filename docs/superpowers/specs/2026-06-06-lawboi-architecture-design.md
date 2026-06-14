# Lawboi Architecture Redesign — Design Spec

**Date:** 2026-06-06
**Status:** Approved (pending spec review)
**Supersedes structure of:** the MVP implementation under `ingest/`, `retrieval/`, `answer/`, `api/`, `db/`

## Goal & Driver

Restructure the working MVP into a **properly structured, build-to-last** architecture
that absorbs growth along four axes the project will actually expand on:

1. **Data scale** — from a handful of laws to a large corpus (full Riigi Teataja).
2. **LLM providers/models** — frequently adding/swapping models and providers.
3. **Retrieval strategies** — experimenting with stages, rerankers, query expansion, A/B.
4. **Data sources / jurisdictions** — beyond the RT API; other sources, formats, jurisdictions.

### Explicit non-goals (anti-over-engineering boundaries)

- **NOT "apply every design pattern."** Patterns are applied only where a named growth
  axis creates real change pressure. Components with one stable implementation get no
  interface (chunker, embedder, prompt formatting).
- **NOT full hexagonal (Approach B).** One port per axis-of-change, not per class.
- **NOT config/plugin-driven (Approach C).** No YAML-wired pipelines. Declarative style is
  used only for the two things that genuinely *are* configuration (model registry,
  retrieval pipeline), kept as type-checked Python.

Chosen approach: **A — Hexagonal-lite + declarative where it is genuinely config.**

## Architecture

Layers, with imports pointing only inward (adapters depend on ports, never the reverse):
`domain → ports → adapters → application services → interface (API/CLI)`.

All modules consolidate under a top-level `lawboi/` package (today's flat top-level packages).
Import paths change accordingly (`ingest.embedder` → `lawboi.ingest.embedder`), and the
CLAUDE.md command examples (`python -m ingest.indexer`, `uvicorn api.main:app`) update to the
`lawboi.` prefix. `eval/` stays at repo root and imports from `lawboi.*`.

```
lawboi/
  domain/
    models.py          # Act, ActVersion, Provision, Chunk (existing dataclasses)
    errors.py          # NoSourcesFoundError, UnsupportedModelError, NoModelConfiguredError,
                       # SourceFetchError, ParseError
  ports/               # the 4 boundaries — one Protocol each
    llm.py             # LLMProvider:        complete(prompt) -> str
    vector_store.py    # VectorStore:        query(emb, k) -> [Hit];  upsert(...)
    structured_store.py# StructuredStore:    repository methods (acts, versions, provisions, fts_search)
    law_source.py      # LawSource:          search(q) -> [ActMeta];  fetch(id) -> RawAct
  adapters/
    llm/               # gemini.py openai.py anthropic.py + registry.py + factory.py
    vector/chroma.py   # ChromaVectorStore
    structured/postgres.py   # owns the connection POOL + repositories
    source/riigiteataja.py   # today's scraper, behind LawSource
  pipeline/
    stages.py          # RetrievalStage protocol + concrete stages
    retrieval.py       # composes stages into a runnable pipeline
  ingest/              # parser.py chunker.py embedder.py service.py  (ingest use-case)
  answer/              # prompts.py service.py  (answer use-case; seam for faithfulness verifier)
  config/
    settings.py        # pydantic-settings — all env access centralized
    composition.py     # composition root: reads settings, builds the object graph
  api/
    main.py schemas.py deps.py routes/   # deps.py wires via FastAPI Depends -> composition root
  eval/                # unchanged (run_eval.py, retrieval_eval.py)
```

### The four ports (= the four growth axes)

| Port | Axis served | Adapter(s) |
|---|---|---|
| `LLMProvider` | 2 (models) | Gemini / OpenAI / Anthropic |
| `VectorStore` | 1 (scale; swap Chroma later) | ChromaVectorStore |
| `StructuredStore` | 1 & 4 (repository layer, one home for SQL + pooling) | PostgresStore |
| `LawSource` | 4 (sources/jurisdictions) | RiigiTeatajaSource |

Application services (`ingest`, `answer`, `pipeline`) reach external systems **only**
through these ports — they never import `chromadb`, `psycopg2`, or a model SDK. This makes
them unit-testable with fakes and **breaks the current import cycle** (retrieval → answer.pipeline),
because the step-back stage receives an `LLMProvider` rather than importing the answer module.

## Declarative pieces

### Model registry (replaces 4-place provider duplication)

Today provider knowledge is spread across `SUPPORTED_MODELS`, `_default_model()`,
`available_models()`, and `api_key_map`. Replace with one data table:

```python
# adapters/llm/registry.py
@dataclass(frozen=True)
class ModelSpec:
    name: str                                  # "gemini-2.0-flash"
    provider: str                              # "google"
    api_key_env: str                           # "GEMINI_API_KEY"
    build: Callable[[str, str], LLMProvider]   # (model_name, api_key) -> adapter
    priority: int                              # default auto-selection order

REGISTRY: tuple[ModelSpec, ...] = (
    ModelSpec("gemini-2.0-flash", "google",    "GEMINI_API_KEY",    GeminiAdapter,    1),
    ModelSpec("gemini-1.5-pro",   "google",    "GEMINI_API_KEY",    GeminiAdapter,    1),
    ModelSpec("gpt-4o",           "openai",    "OPENAI_API_KEY",    OpenAIAdapter,    2),
    ModelSpec("gpt-4o-mini",      "openai",    "OPENAI_API_KEY",    OpenAIAdapter,    2),
    ModelSpec("claude-sonnet-4-5","anthropic", "ANTHROPIC_API_KEY", AnthropicAdapter, 3),
)
```

`available_models()`, default selection, and `get_llm()` all derive from `REGISTRY`.
**Adding a model = one line.** The CLAUDE.md gotcha ("update both X and Y") disappears.

### Retrieval pipeline (dissolves the monolithic `retrieve()`)

Each step becomes a stage with a uniform interface; the pipeline is a composed list:

```python
# pipeline/stages.py
class RetrievalStage(Protocol):
    def __call__(self, ctx: RetrievalContext) -> RetrievalContext: ...

@dataclass
class RetrievalContext:
    query: str
    as_of: date
    candidates: list[Provision]
    config: RetrievalConfig
```

Concrete stages: `CitationShortCircuit`, `EmbedQuery`, `DenseSearch`, `SparseSearch`,
`ProceduralAugment`, `StepBackExpand`, `Merge`, `Rerank`.

```python
DEFAULT_PIPELINE = [
    CitationShortCircuit(store),       # exact §-lookup bypasses the rest
    DenseSearch(vector, embedder),
    SparseSearch(store),
    ProceduralAugment(vector, embedder),
    StepBackExpand(vector, embedder, llm),
    Merge(),
    Rerank(reranker),                  # no-op stage if COHERE_API_KEY unset
]
```

A/B-ing retrieval = reorder/swap the list. Adding a stage = one class + one entry. Each
stage is independently unit-testable. `StepBackExpand` takes `llm` via its port, so retrieval
no longer imports `answer.pipeline`.

**Boundary:** the pipeline stays a type-checked Python list. No YAML config layer (that buys
runtime reconfiguration we don't need on a solo codebase and loses type safety).

## Cross-cutting concerns

### Settings (one place for env)

`config/settings.py` via `pydantic-settings`. Every scattered `os.getenv(...)` (in `engine.py`,
`indexer.py`, `connection.py`, `pipeline.py`) moves here. Validated once at startup — fail fast
on misconfiguration instead of a mid-request `KeyError`.

```python
class Settings(BaseSettings):
    database_url: str
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    cohere_api_key: str | None = None
    llm_model: str | None = None
    db_pool_min: int = 1
    db_pool_max: int = 10
```

### Composition root (single wiring point)

`config/composition.py` is the only place that knows which concrete adapters exist. It reads
`Settings`, builds the pool, instantiates adapters, assembles the pipeline, returns services:

```python
def build_container(settings: Settings) -> Container:
    store    = PostgresStore(pool=make_pool(settings))
    vector   = ChromaVectorStore(settings.chroma_host, settings.chroma_port)
    llm      = build_llm(settings.llm_model)          # from registry
    pipeline = build_pipeline(store, vector, embedder, llm, reranker)
    return Container(retrieval=RetrievalService(pipeline),
                     answer=AnswerService(llm), ingest=IngestService(...))
```

### Dependency injection (FastAPI `Depends`, not module globals)

`api/deps.py` exposes the container via `Depends`, replacing the duplicated `_get_engine()`
singletons in `answer.py` and `search.py`. Trivially overridable in tests via
`app.dependency_overrides`.

### Connection pooling (the blocking fix)

`PostgresStore` owns a `ThreadedConnectionPool` sized from settings. `db_cursor()` borrows/returns
from the pool instead of opening a fresh connection per call. Same context-manager API
(commit/rollback/return-to-pool), so call sites barely change.

### Error handling (domain exceptions + one mapping layer)

Domain raises typed errors; the API maps them centrally via `@app.exception_handler`, so routes
stop hand-rolling `HTTPException`.

| Domain error | HTTP | Notes |
|---|---|---|
| `NoSourcesFoundError` | 422 | preserves the "no answer without sources" invariant |
| `UnsupportedModelError` | 400 | |
| `NoModelConfiguredError` | 503 | |
| `SourceFetchError` / `ParseError` | (ingest CLI) | surfaced in the script, not HTTP |

The 422 invariant moves from an inline `if not provisions` in the route into `AnswerService`
raising `NoSourcesFoundError` — same guarantee, enforced at the service boundary.

## Testing strategy

Ports make most tests container-free. Each port gets a fake: `FakeLLMProvider`,
`InMemoryVectorStore`, `InMemoryStructuredStore`, `FakeLawSource`.

- **Service tests** (answer, retrieval, ingest): wire fakes via the container — no Docker.
  Replaces today's "mock chromadb / CohereRerank / llama-index path" gotchas with injected fakes.
- **Stage tests**: each `RetrievalStage` in isolation against fakes.
- **Registry test**: every `ModelSpec` builds; `available_models()` derives correctly.
- **Adapter/integration tests**: the only ones needing real PG + Chroma (existing Colima setup),
  marked so fast runs can skip them.
- **API tests**: `app.dependency_overrides` swaps the container for fakes — full route tests, no infra.

The 48 tests' behaviors are preserved; most migrate from "mock the world" to "inject a fake."
The container-dependent set shrinks to just the adapter layer.

## Migration sequencing (staying green through a big-bang rewrite)

Dependency-safe order so a runnable, tested core exists before any adapter/container — the one
real risk of big-bang (flying blind) is removed. Old code stays in place and working until step 7.

1. **Scaffold + settings + domain models + errors** — pure, no infra.
2. **Ports defined + all four fakes written** — everything downstream becomes testable.
3. **Application services TDD'd against fakes** — `AnswerService`, `RetrievalService`
   (pipeline + stages), `IngestService`. Existing tests' behavioral assertions are ported here.
   Green = logic correct, no containers.
4. **Real adapters + integration tests** — `PostgresStore` (pooling), `ChromaVectorStore`,
   LLM adapters + registry, `RiigiTeataja` source.
5. **Composition root + API (Depends) wired** — end-to-end runnable; port API tests.
6. **Eval unchanged** — `run_eval.py` / `retrieval_eval.py` point at the new API; the
   faithfulness judge work carries over untouched.
7. **Delete old modules** in one commit once parity is proven (eval + tests pass).

## Risks & mitigations

- **Big-bang loses the test safety net mid-flight.** Mitigation: existing tests are treated as
  a behavioral spec; steps 1–3 deliver a fully unit-tested core before adapters exist; old code
  remains runnable until step 7.
- **Untested ingest paths persist** (numeric `globaalID` ELI faking, RT XML tag names, RT API
  URL format — all flagged in CLAUDE.md). The rewrite does not fix these; it isolates them behind
  `LawSource` so they can be corrected and tested in one place later. Out of scope for this spec.

## Preserved invariants

- No answer without sources (now `AnswerService` → `NoSourcesFoundError` → 422).
- Two ChromaDB queries per retrieval (original + procedural augmentation) — now explicit stages.
- Reranker skipped when `COHERE_API_KEY` unset — now a no-op `Rerank` stage.
- Parser strips XML namespaces; section numbers from `nr` attribute — unchanged, moves behind `LawSource`.
