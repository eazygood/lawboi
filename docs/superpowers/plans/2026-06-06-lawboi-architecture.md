# Lawboi Architecture Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the working MVP into a hexagonal-lite architecture (domain → ports → adapters → services → interface) with a declarative model registry and a composable retrieval pipeline, while keeping behavior identical and tests green.

**Architecture:** All code consolidates under a `lawboi/` package. External systems (LLM, vector store, structured store, law source) are reached only through four `Protocol` ports, each with a real adapter and an in-memory fake. Application services depend on ports, not concrete libraries. A composition root wires everything; FastAPI `Depends` injects it.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2 + pydantic-settings, psycopg2 (ThreadedConnectionPool), ChromaDB, sentence-transformers, llama-index LLM adapters, Cohere rerank, pytest.

---

## Conventions used in this plan

- **New structural code is shown in full.** Ports, registry, pipeline, services, composition, deps, exception handlers, and fakes appear as complete code blocks.
- **Pure relocations cite the source.** Where a task moves already-tested logic unchanged, the step says `port verbatim from <path:lines>` rather than re-transcribing it — the existing module is the behavioral spec, and re-typing risks silent transcription bugs. The engineer copies the cited code into the new file and only adjusts imports.
- **Old code stays runnable until Task 20.** Nothing under `ingest/`, `retrieval/`, `answer/`, `api/`, `db/` is deleted until parity is proven. New code lives under `lawboi/` alongside it.
- **TDD throughout.** Write the failing test, see it fail, implement, see it pass, commit.
- **Commits** use no JIRA prefix here because this is a personal repo and none was supplied; if the engineer is on a ticket, prefix accordingly.

## File structure (target)

```
lawboi/
  __init__.py
  domain/
    __init__.py
    models.py            # Act, ActVersion, Provision, Chunk
    errors.py            # typed domain exceptions
    dto.py               # VectorHit, ActMeta, RawAct, RetrievedProvision
  ports/
    __init__.py
    llm.py               # LLMProvider Protocol
    vector_store.py      # VectorStore Protocol
    structured_store.py  # StructuredStore Protocol
    law_source.py        # LawSource Protocol
  adapters/
    __init__.py
    llm/
      __init__.py
      registry.py        # ModelSpec + REGISTRY (declarative)
      factory.py         # build_llm / available_models
      gemini.py openai.py anthropic.py
    vector/
      __init__.py
      chroma.py          # ChromaVectorStore
    structured/
      __init__.py
      pool.py            # make_pool
      postgres.py        # PostgresStore (repository + pooled cursor)
    source/
      __init__.py
      parser.py          # relocated XML parsing
      riigiteataja.py    # RiigiTeatajaSource (scraper behind LawSource)
  pipeline/
    __init__.py
    context.py           # RetrievalContext, RetrievalConfig
    stages.py            # RetrievalStage Protocol + concrete stages
    retrieval.py         # build_pipeline + run
  ingest/
    __init__.py
    embedder.py          # relocated
    chunker.py           # relocated
    service.py           # IngestService
  answer/
    __init__.py
    prompts.py           # relocated
    citations.py         # extract_citations, detect_language (relocated)
    service.py           # AnswerService
  config/
    __init__.py
    settings.py          # pydantic-settings
    composition.py       # Container + build_container
  api/
    __init__.py
    main.py
    schemas.py
    deps.py
    errors.py            # exception handlers
    routes/
      __init__.py
      answer.py search.py acts.py
tests/lawboi/...         # mirrors the package; fakes live in tests/lawboi/fakes.py
```

---

## Phase 1 — Scaffold, settings, domain

### Task 1: Package scaffold + dependency

**Files:**
- Create: `lawboi/__init__.py` (empty)
- Create: `lawboi/domain/__init__.py`, `lawboi/ports/__init__.py`, `lawboi/adapters/__init__.py`, `lawboi/adapters/llm/__init__.py`, `lawboi/adapters/vector/__init__.py`, `lawboi/adapters/structured/__init__.py`, `lawboi/adapters/source/__init__.py`, `lawboi/pipeline/__init__.py`, `lawboi/ingest/__init__.py`, `lawboi/answer/__init__.py`, `lawboi/config/__init__.py`, `lawboi/api/__init__.py`, `lawboi/api/routes/__init__.py` (all empty)
- Create: `tests/lawboi/__init__.py` (empty)
- Modify: `requirements.txt`

- [ ] **Step 1: Create the package tree**

```bash
mkdir -p lawboi/domain lawboi/ports lawboi/adapters/llm lawboi/adapters/vector \
  lawboi/adapters/structured lawboi/adapters/source lawboi/pipeline lawboi/ingest \
  lawboi/answer lawboi/config lawboi/api/routes tests/lawboi
for d in lawboi lawboi/domain lawboi/ports lawboi/adapters lawboi/adapters/llm \
  lawboi/adapters/vector lawboi/adapters/structured lawboi/adapters/source \
  lawboi/pipeline lawboi/ingest lawboi/answer lawboi/config lawboi/api \
  lawboi/api/routes tests/lawboi; do touch "$d/__init__.py"; done
```

- [ ] **Step 2: Add pydantic-settings to requirements**

In `requirements.txt`, under the `# Core` block (after the `pydantic>=2.0` line), add:

```
pydantic-settings>=2.0
```

- [ ] **Step 3: Install it**

Run: `.venv/bin/python -m pip install pydantic-settings`
Expected: `Successfully installed pydantic-settings-...`

- [ ] **Step 4: Verify the package imports**

Run: `.venv/bin/python -c "import lawboi; import lawboi.domain; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add lawboi tests/lawboi requirements.txt
git commit -m "scaffold lawboi package + add pydantic-settings"
```

---

### Task 2: Domain models

**Files:**
- Create: `lawboi/domain/models.py`
- Test: `tests/lawboi/domain/test_models.py`

- [ ] **Step 1: Create test dir + failing test**

```bash
mkdir -p tests/lawboi/domain && touch tests/lawboi/domain/__init__.py
```

`tests/lawboi/domain/test_models.py`:

```python
from datetime import date
from lawboi.domain.models import Act, ActVersion, Provision, Chunk


def test_provision_holds_hierarchy_fields():
    p = Provision(id=1, act_version_id=2, section_num="5", level="section",
                  text_et="tekst", text_en=None, parent_id=None)
    assert p.section_num == "5"
    assert p.level == "section"


def test_chunk_carries_metadata_dict():
    c = Chunk(provision_id=1, act_version_id=2, section_num="5",
              text="t", metadata={"eli": "RT I 2009, 5, 35"})
    assert c.metadata["eli"] == "RT I 2009, 5, 35"


def test_act_version_optional_end_date():
    v = ActVersion(id=None, act_id=1, effective_from=date(2020, 1, 1),
                   effective_to=None, source_url="u", source_hash="h")
    assert v.effective_to is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/domain/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.domain.models'`

- [ ] **Step 3: Create the models**

Port verbatim from `ingest/models.py:1-43` into `lawboi/domain/models.py` (the four dataclasses `Act`, `ActVersion`, `Provision`, `Chunk` are unchanged). No edits needed — they have no internal imports.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/domain/test_models.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/domain/models.py tests/lawboi/domain
git commit -m "add domain models"
```

---

### Task 3: Domain errors

**Files:**
- Create: `lawboi/domain/errors.py`
- Test: `tests/lawboi/domain/test_errors.py`

- [ ] **Step 1: Write the failing test**

`tests/lawboi/domain/test_errors.py`:

```python
import pytest
from lawboi.domain.errors import (
    LawboiError, NoSourcesFoundError, UnsupportedModelError,
    NoModelConfiguredError, SourceFetchError, ParseError,
)


def test_all_inherit_base():
    for exc in (NoSourcesFoundError, UnsupportedModelError, NoModelConfiguredError,
                SourceFetchError, ParseError):
        assert issubclass(exc, LawboiError)


def test_unsupported_model_carries_name():
    err = UnsupportedModelError("gpt-5")
    assert "gpt-5" in str(err)


def test_raisable():
    with pytest.raises(NoSourcesFoundError):
        raise NoSourcesFoundError("no provisions")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/domain/test_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.domain.errors'`

- [ ] **Step 3: Implement the errors**

`lawboi/domain/errors.py`:

```python
class LawboiError(Exception):
    """Base for all domain errors."""


class NoSourcesFoundError(LawboiError):
    """Retrieval returned no provisions; an answer must not be produced."""


class UnsupportedModelError(LawboiError):
    def __init__(self, model: str):
        super().__init__(f"Unsupported model: {model}")
        self.model = model


class NoModelConfiguredError(LawboiError):
    """No LLM provider key is configured in the environment."""


class SourceFetchError(LawboiError):
    """A law source failed to fetch or search."""


class ParseError(LawboiError):
    """Source content could not be parsed into provisions."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/domain/test_errors.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/domain/errors.py tests/lawboi/domain/test_errors.py
git commit -m "add domain errors"
```

---

### Task 4: Shared DTOs

**Files:**
- Create: `lawboi/domain/dto.py`
- Test: `tests/lawboi/domain/test_dto.py`

These are the plain data shapes passed across ports, so adapters and services agree on structure without leaking library types. `RetrievedProvision` mirrors the dict shape used today (`provision_id`, `section_num`, `text`, `metadata`) so the retrieval contract is preserved.

- [ ] **Step 1: Write the failing test**

`tests/lawboi/domain/test_dto.py`:

```python
from lawboi.domain.dto import VectorHit, ActMeta, RawAct, RetrievedProvision


def test_retrieved_provision_shape():
    rp = RetrievedProvision(provision_id=1, section_num="5", text="t",
                            metadata={"eli": "RT I 2009, 5, 35", "act_title": "TLS"})
    assert rp.provision_id == 1
    assert rp.metadata["act_title"] == "TLS"


def test_vector_hit():
    h = VectorHit(provision_id=1, section_num="5", text="t", metadata={})
    assert h.provision_id == 1


def test_act_meta_and_raw_act():
    m = ActMeta(global_id=123, title="TLS", effective_from=None, effective_to=None)
    r = RawAct(global_id=123, xml=b"<x/>", source_url="u")
    assert m.global_id == 123 and r.xml == b"<x/>"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/domain/test_dto.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.domain.dto'`

- [ ] **Step 3: Implement the DTOs**

`lawboi/domain/dto.py`:

```python
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class RetrievedProvision:
    provision_id: int
    section_num: str
    text: str
    metadata: dict = field(default_factory=dict)


# VectorHit is the vector-store's view of a result; structurally identical to
# RetrievedProvision but kept distinct so the port contract is explicit.
@dataclass
class VectorHit:
    provision_id: int
    section_num: str
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ActMeta:
    global_id: int
    title: str
    effective_from: Optional[date]
    effective_to: Optional[date]


@dataclass
class RawAct:
    global_id: int
    xml: bytes
    source_url: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/domain/test_dto.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/domain/dto.py tests/lawboi/domain/test_dto.py
git commit -m "add shared DTOs"
```

---

### Task 5: Settings

**Files:**
- Create: `lawboi/config/settings.py`
- Test: `tests/lawboi/config/test_settings.py`

- [ ] **Step 1: Create test dir + failing test**

```bash
mkdir -p tests/lawboi/config && touch tests/lawboi/config/__init__.py
```

`tests/lawboi/config/test_settings.py`:

```python
from lawboi.config.settings import Settings


def test_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    s = Settings()
    assert s.chroma_host == "localhost"
    assert s.chroma_port == 8001
    assert s.db_pool_min == 1
    assert s.db_pool_max == 10
    assert s.llm_model is None


def test_env_override(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("CHROMA_PORT", "9999")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    s = Settings()
    assert s.chroma_port == 9999
    assert s.llm_model == "gpt-4o"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/config/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.config.settings'`

- [ ] **Step 3: Implement settings**

`lawboi/config/settings.py`:

```python
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    cohere_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    db_pool_min: int = 1
    db_pool_max: int = 10
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/config/test_settings.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/config/settings.py tests/lawboi/config
git commit -m "add pydantic settings"
```

---

## Phase 2 — Ports + fakes

### Task 6: Define the four ports

**Files:**
- Create: `lawboi/ports/llm.py`, `lawboi/ports/vector_store.py`, `lawboi/ports/structured_store.py`, `lawboi/ports/law_source.py`
- Test: `tests/lawboi/ports/test_protocols.py`

Ports are `typing.Protocol` (structural typing — adapters need not subclass). The test asserts the protocols are runtime-checkable and that a minimal stub satisfies them.

- [ ] **Step 1: Create test dir + failing test**

```bash
mkdir -p tests/lawboi/ports && touch tests/lawboi/ports/__init__.py
```

`tests/lawboi/ports/test_protocols.py`:

```python
from datetime import date
from lawboi.ports.llm import LLMProvider
from lawboi.ports.vector_store import VectorStore
from lawboi.ports.structured_store import StructuredStore
from lawboi.ports.law_source import LawSource


def test_llm_protocol_satisfied():
    class Stub:
        name = "stub"
        def complete(self, prompt: str) -> str: return "x"
    assert isinstance(Stub(), LLMProvider)


def test_vector_protocol_satisfied():
    class Stub:
        def query(self, embedding, n_results): return []
        def upsert(self, provision_id, embedding, document, metadata): ...
    assert isinstance(Stub(), VectorStore)


def test_structured_protocol_has_methods():
    assert hasattr(StructuredStore, "fts_search")
    assert hasattr(StructuredStore, "exact_lookup")


def test_law_source_protocol_has_methods():
    assert hasattr(LawSource, "search")
    assert hasattr(LawSource, "fetch")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/ports/test_protocols.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.ports.llm'`

- [ ] **Step 3: Implement the ports**

`lawboi/ports/llm.py`:

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def complete(self, prompt: str) -> str: ...
```

`lawboi/ports/vector_store.py`:

```python
from typing import Protocol, runtime_checkable
from lawboi.domain.dto import VectorHit


@runtime_checkable
class VectorStore(Protocol):
    def query(self, embedding: list[float], n_results: int) -> list[VectorHit]: ...

    def upsert(self, provision_id: int, embedding: list[float],
               document: str, metadata: dict) -> None: ...
```

`lawboi/ports/structured_store.py`:

```python
from datetime import date
from typing import Optional, Protocol, runtime_checkable
from lawboi.domain.models import Act, ActVersion, Provision
from lawboi.domain.dto import RetrievedProvision


@runtime_checkable
class StructuredStore(Protocol):
    # write side (ingest)
    def upsert_act(self, act: Act) -> int: ...
    def upsert_act_version(self, version: ActVersion) -> int: ...
    def insert_provision(self, provision: Provision) -> int: ...
    def version_has_provisions(self, act_version_id: int) -> bool: ...

    # read side (retrieval)
    def fts_search(self, query: str, effective_date: date) -> list[RetrievedProvision]: ...
    def exact_lookup(self, section_num: str, as_of: date, limit: int,
                     eli: Optional[str], title_query: Optional[str]) -> list[RetrievedProvision]: ...
```

`lawboi/ports/law_source.py`:

```python
from typing import Protocol, runtime_checkable
from lawboi.domain.dto import ActMeta, RawAct


@runtime_checkable
class LawSource(Protocol):
    def search(self, query: str, limit: int = 10) -> list[ActMeta]: ...

    def fetch(self, global_id: int) -> RawAct: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/ports/test_protocols.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/ports tests/lawboi/ports
git commit -m "define the four ports"
```

---

### Task 7: In-memory fakes for every port

**Files:**
- Create: `tests/lawboi/fakes.py`
- Test: `tests/lawboi/test_fakes.py`

Fakes let every downstream service test run without Docker. They are deliberately simple and live under `tests/` (not shipped).

- [ ] **Step 1: Write the failing test**

`tests/lawboi/test_fakes.py`:

```python
from datetime import date
from lawboi.domain.models import Act, ActVersion, Provision
from lawboi.domain.dto import VectorHit, ActMeta, RawAct
from tests.lawboi.fakes import (
    FakeLLMProvider, InMemoryVectorStore, InMemoryStructuredStore, FakeLawSource,
)


def test_fake_llm_returns_scripted():
    llm = FakeLLMProvider(responses=["hello"])
    assert llm.complete("anything") == "hello"
    assert llm.calls == ["anything"]


def test_inmemory_vector_roundtrip():
    v = InMemoryVectorStore()
    v.upsert(1, [0.1], "doc", {"section_num": "5"})
    hits = v.query([0.1], n_results=5)
    assert hits and isinstance(hits[0], VectorHit) and hits[0].provision_id == 1


def test_inmemory_structured_write_then_read():
    s = InMemoryStructuredStore()
    act_id = s.upsert_act(Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus"))
    vid = s.upsert_act_version(ActVersion(None, act_id, date(2020, 1, 1), None, "u", "h"))
    assert s.version_has_provisions(vid) is False
    s.insert_provision(Provision(None, vid, "5", "section", "tekst reguleerimisala", None))
    assert s.version_has_provisions(vid) is True
    assert s.fts_search("reguleerimisala", date(2021, 1, 1))


def test_fake_law_source():
    src = FakeLawSource(
        acts=[ActMeta(123, "TLS", None, None)],
        raw={123: RawAct(123, b"<x/>", "u")},
    )
    assert src.search("TLS")[0].global_id == 123
    assert src.fetch(123).xml == b"<x/>"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/test_fakes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tests.lawboi.fakes'`

- [ ] **Step 3: Implement the fakes**

`tests/lawboi/fakes.py`:

```python
from datetime import date
from typing import Optional

from lawboi.domain.models import Act, ActVersion, Provision
from lawboi.domain.dto import VectorHit, ActMeta, RawAct, RetrievedProvision


class FakeLLMProvider:
    name = "fake"

    def __init__(self, responses: Optional[list[str]] = None):
        self._responses = list(responses or ["FAKE ANSWER"])
        self.calls: list[str] = []

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


class InMemoryVectorStore:
    def __init__(self):
        self._docs: dict[int, dict] = {}

    def upsert(self, provision_id, embedding, document, metadata):
        self._docs[provision_id] = {"document": document, "metadata": metadata}

    def query(self, embedding, n_results):
        return [
            VectorHit(provision_id=pid, section_num=d["metadata"].get("section_num", ""),
                      text=d["document"], metadata=d["metadata"])
            for pid, d in list(self._docs.items())[:n_results]
        ]


class InMemoryStructuredStore:
    def __init__(self):
        self._acts: dict[str, int] = {}
        self._versions: dict[int, ActVersion] = {}
        self._provisions: list[Provision] = []
        self._next = 1

    def _id(self):
        n = self._next
        self._next += 1
        return n

    def upsert_act(self, act: Act) -> int:
        if act.eli not in self._acts:
            self._acts[act.eli] = self._id()
        return self._acts[act.eli]

    def upsert_act_version(self, version: ActVersion) -> int:
        vid = self._id()
        version.id = vid
        self._versions[vid] = version
        return vid

    def insert_provision(self, provision: Provision) -> int:
        pid = self._id()
        provision.id = pid
        self._provisions.append(provision)
        return pid

    def version_has_provisions(self, act_version_id: int) -> bool:
        return any(p.act_version_id == act_version_id for p in self._provisions)

    def _to_rp(self, p: Provision) -> RetrievedProvision:
        return RetrievedProvision(
            provision_id=p.id, section_num=p.section_num, text=p.text_et,
            metadata={"section_num": p.section_num, "act_version_id": p.act_version_id,
                      "is_translation": False, "context": ""},
        )

    def fts_search(self, query: str, effective_date: date) -> list[RetrievedProvision]:
        terms = query.lower().split()
        return [self._to_rp(p) for p in self._provisions
                if any(t in p.text_et.lower() for t in terms)]

    def exact_lookup(self, section_num, as_of, limit, eli, title_query):
        return [self._to_rp(p) for p in self._provisions
                if p.section_num == section_num][:limit]


class FakeLawSource:
    def __init__(self, acts: list[ActMeta], raw: dict[int, RawAct]):
        self._acts = acts
        self._raw = raw

    def search(self, query: str, limit: int = 10) -> list[ActMeta]:
        return self._acts[:limit]

    def fetch(self, global_id: int) -> RawAct:
        return self._raw[global_id]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/test_fakes.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add tests/lawboi/fakes.py tests/lawboi/test_fakes.py
git commit -m "add in-memory fakes for all ports"
```

---

## Phase 3 — Application services (TDD against fakes)

### Task 8: Declarative model registry + factory

**Files:**
- Create: `lawboi/adapters/llm/registry.py`, `lawboi/adapters/llm/factory.py`
- Create: `lawboi/adapters/llm/gemini.py`, `openai.py`, `anthropic.py`
- Test: `tests/lawboi/adapters/llm/test_registry.py`

The adapters are thin wrappers exposing `name` + `complete()` (the `LLMProvider` port). They lazily import their llama-index backend so a missing optional dependency doesn't break import of the registry. The factory derives everything from `REGISTRY` — adding a model is one tuple entry.

- [ ] **Step 1: Create test dirs + failing test**

```bash
mkdir -p tests/lawboi/adapters/llm && touch tests/lawboi/adapters/__init__.py \
  tests/lawboi/adapters/llm/__init__.py
```

`tests/lawboi/adapters/llm/test_registry.py`:

```python
import pytest
from lawboi.adapters.llm.registry import REGISTRY, ModelSpec, find_spec
from lawboi.adapters.llm.factory import available_models, resolve_model
from lawboi.domain.errors import UnsupportedModelError, NoModelConfiguredError


def test_registry_entries_well_formed():
    assert REGISTRY
    for spec in REGISTRY:
        assert isinstance(spec, ModelSpec)
        assert spec.name and spec.provider and spec.api_key_env
        assert callable(spec.build)


def test_available_models_derives_from_env(monkeypatch):
    for var in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    models = available_models()
    assert "gpt-4o" in models
    assert "gemini-2.0-flash" not in models


def test_resolve_picks_priority_default(monkeypatch):
    for var in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert resolve_model(None) == "gpt-4o"


def test_resolve_rejects_unknown(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with pytest.raises(UnsupportedModelError):
        resolve_model("gpt-5")


def test_resolve_raises_when_nothing_configured(monkeypatch):
    for var in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(NoModelConfiguredError):
        resolve_model(None)


def test_find_spec():
    assert find_spec("gpt-4o").provider == "openai"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/adapters/llm/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.adapters.llm.registry'`

- [ ] **Step 3a: Implement the adapters**

`lawboi/adapters/llm/gemini.py`:

```python
class GeminiAdapter:
    def __init__(self, model: str, api_key: str):
        self.name = model
        from llama_index.llms.gemini import Gemini
        self._llm = Gemini(model=model, api_key=api_key)

    def complete(self, prompt: str) -> str:
        return str(self._llm.complete(prompt))
```

`lawboi/adapters/llm/openai.py`:

```python
class OpenAIAdapter:
    def __init__(self, model: str, api_key: str):
        self.name = model
        from llama_index.llms.openai import OpenAI
        self._llm = OpenAI(model=model, api_key=api_key)

    def complete(self, prompt: str) -> str:
        return str(self._llm.complete(prompt))
```

`lawboi/adapters/llm/anthropic.py`:

```python
class AnthropicAdapter:
    def __init__(self, model: str, api_key: str):
        self.name = model
        from llama_index.llms.anthropic import Anthropic
        self._llm = Anthropic(model=model, api_key=api_key)

    def complete(self, prompt: str) -> str:
        return str(self._llm.complete(prompt))
```

- [ ] **Step 3b: Implement the registry**

`lawboi/adapters/llm/registry.py`:

```python
from dataclasses import dataclass
from typing import Callable, Optional

from lawboi.ports.llm import LLMProvider
from lawboi.adapters.llm.gemini import GeminiAdapter
from lawboi.adapters.llm.openai import OpenAIAdapter
from lawboi.adapters.llm.anthropic import AnthropicAdapter


@dataclass(frozen=True)
class ModelSpec:
    name: str
    provider: str
    api_key_env: str
    build: Callable[[str, str], LLMProvider]
    priority: int


REGISTRY: tuple[ModelSpec, ...] = (
    ModelSpec("gemini-2.0-flash", "google", "GEMINI_API_KEY", GeminiAdapter, 1),
    ModelSpec("gemini-1.5-pro", "google", "GEMINI_API_KEY", GeminiAdapter, 1),
    ModelSpec("gpt-4o", "openai", "OPENAI_API_KEY", OpenAIAdapter, 2),
    ModelSpec("gpt-4o-mini", "openai", "OPENAI_API_KEY", OpenAIAdapter, 2),
    ModelSpec("claude-sonnet-4-5", "anthropic", "ANTHROPIC_API_KEY", AnthropicAdapter, 3),
)


def find_spec(name: str) -> Optional[ModelSpec]:
    return next((s for s in REGISTRY if s.name == name), None)
```

- [ ] **Step 3c: Implement the factory**

`lawboi/adapters/llm/factory.py`:

```python
import os
from typing import Optional

from lawboi.ports.llm import LLMProvider
from lawboi.adapters.llm.registry import REGISTRY, find_spec
from lawboi.domain.errors import UnsupportedModelError, NoModelConfiguredError


def available_models() -> list[str]:
    return [s.name for s in REGISTRY if os.getenv(s.api_key_env)]


def resolve_model(model: Optional[str]) -> str:
    model = model or os.getenv("LLM_MODEL")
    if model:
        spec = find_spec(model)
        if spec is None:
            raise UnsupportedModelError(model)
        if not os.getenv(spec.api_key_env):
            raise NoModelConfiguredError(
                f"Model '{model}' requires {spec.api_key_env} to be set")
        return model
    for spec in sorted(REGISTRY, key=lambda s: s.priority):
        if os.getenv(spec.api_key_env):
            return spec.name
    raise NoModelConfiguredError(
        "No LLM API key configured. Set one of: "
        + ", ".join(sorted({s.api_key_env for s in REGISTRY})))


def build_llm(model: Optional[str] = None) -> LLMProvider:
    name = resolve_model(model)
    spec = find_spec(name)
    api_key = os.getenv(spec.api_key_env)
    return spec.build(name, api_key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/adapters/llm/test_registry.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/adapters/llm tests/lawboi/adapters
git commit -m "add declarative LLM model registry + factory"
```

---

### Task 9: Answer citations + language detection (relocate)

**Files:**
- Create: `lawboi/answer/prompts.py`, `lawboi/answer/citations.py`
- Test: `tests/lawboi/answer/test_citations.py`

- [ ] **Step 1: Create test dir + failing test**

```bash
mkdir -p tests/lawboi/answer && touch tests/lawboi/answer/__init__.py
```

`tests/lawboi/answer/test_citations.py`:

```python
from lawboi.answer.citations import extract_citations, detect_language, format_context


def _prov(section, eli, title):
    return {"section_num": section, "text": "t",
            "metadata": {"act_title": title, "eli": eli, "subsection": ""}}


def test_extract_citations_matches_section_in_answer():
    provs = [_prov("97", "RT I 2009, 5, 35", "TLS")]
    cites = extract_citations("Per § 97 the notice period applies.", provs)
    assert len(cites) == 1
    assert cites[0]["section"] == "§ 97"
    assert cites[0]["eli"] == "RT I 2009, 5, 35"


def test_extract_citations_ignores_unmentioned():
    provs = [_prov("5", "RT I 2009, 5, 35", "TLS")]
    assert extract_citations("No section here.", provs) == []


def test_detect_language():
    assert detect_language("Mis on tööõigus ja töötaja õigused?") == "et"
    assert detect_language("What is the rate?") == "en"


def test_format_context_includes_section_and_eli():
    out = format_context([_prov("97", "RT I 2009, 5, 35", "TLS")])
    assert "§ 97" in out and "RT I 2009, 5, 35" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/answer/test_citations.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.answer.citations'`

- [ ] **Step 3a: Relocate prompts**

Port verbatim from `answer/prompts.py:1-43` into `lawboi/answer/prompts.py` (the `SYSTEM_PROMPT` and `DISCLAIMER` constants, unchanged).

- [ ] **Step 3b: Relocate citation/format/language helpers**

Create `lawboi/answer/citations.py` containing `format_context`, `extract_citations`, and `detect_language` ported verbatim from `answer/pipeline.py:70-121` (functions `format_context` lines 70-78, `extract_citations` lines 81-115, `detect_language` lines 118-121). Add the required imports at the top:

```python
import re
from collections import defaultdict
```

No logic changes.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/answer/test_citations.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/answer/prompts.py lawboi/answer/citations.py tests/lawboi/answer
git commit -m "relocate answer prompts + citation helpers"
```

---

### Task 10: AnswerService

**Files:**
- Create: `lawboi/answer/service.py`
- Test: `tests/lawboi/answer/test_service.py`

`AnswerService` takes an `LLMProvider` (port) and produces the answer dict. It enforces the **no-answer-without-sources** invariant by raising `NoSourcesFoundError` when given no provisions — moving the guard out of the route.

- [ ] **Step 1: Write the failing test**

`tests/lawboi/answer/test_service.py`:

```python
import pytest
from lawboi.answer.service import AnswerService
from lawboi.domain.errors import NoSourcesFoundError
from tests.lawboi.fakes import FakeLLMProvider


def _prov(section="97", eli="RT I 2009, 5, 35", title="TLS", is_translation=False):
    return {"section_num": section, "text": "tekst",
            "metadata": {"act_title": title, "eli": eli, "subsection": "",
                         "is_translation": is_translation}}


def test_raises_when_no_provisions():
    svc = AnswerService(FakeLLMProvider())
    with pytest.raises(NoSourcesFoundError):
        svc.answer("query", provisions=[])


def test_returns_answer_dict_with_citations():
    llm = FakeLLMProvider(responses=["Under § 97 notice applies."])
    svc = AnswerService(llm)
    result = svc.answer("notice period?", provisions=[_prov()])
    assert result["answer"] == "Under § 97 notice applies."
    assert result["model_used"] == "fake"
    assert result["citations"][0]["section"] == "§ 97"
    assert result["language_detected"] == "en"
    assert result["disclaimer"]


def test_translation_warning_flag():
    llm = FakeLLMProvider(responses=["§ 97 ..."])
    svc = AnswerService(llm)
    result = svc.answer("q", provisions=[_prov(is_translation=True)])
    assert result["translation_warning"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/answer/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.answer.service'`

- [ ] **Step 3: Implement AnswerService**

`lawboi/answer/service.py`:

```python
from lawboi.ports.llm import LLMProvider
from lawboi.domain.errors import NoSourcesFoundError
from lawboi.answer.prompts import SYSTEM_PROMPT, DISCLAIMER
from lawboi.answer.citations import format_context, extract_citations, detect_language


class AnswerService:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def answer(self, query: str, provisions: list[dict]) -> dict:
        if not provisions:
            raise NoSourcesFoundError("No relevant provisions found")
        prompt = SYSTEM_PROMPT.format(context=format_context(provisions), query=query)
        answer_text = self._llm.complete(prompt)
        citations = extract_citations(answer_text, provisions)
        translation_warning = any(
            p.get("metadata", {}).get("is_translation", False) for p in provisions)
        return {
            "answer": answer_text,
            "model_used": self._llm.name,
            "citations": citations,
            "language_detected": detect_language(query),
            "translation_warning": translation_warning,
            "disclaimer": DISCLAIMER,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/answer/test_service.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/answer/service.py tests/lawboi/answer/test_service.py
git commit -m "add AnswerService with no-sources guard"
```

---

### Task 11: Retrieval context + config

**Files:**
- Create: `lawboi/pipeline/context.py`
- Test: `tests/lawboi/pipeline/test_context.py`

- [ ] **Step 1: Create test dir + failing test**

```bash
mkdir -p tests/lawboi/pipeline && touch tests/lawboi/pipeline/__init__.py
```

`tests/lawboi/pipeline/test_context.py`:

```python
from datetime import date
from lawboi.pipeline.context import RetrievalContext, RetrievalConfig


def test_context_defaults():
    ctx = RetrievalContext(query="q", as_of=date(2021, 1, 1))
    assert ctx.candidates == []
    assert ctx.config.limit == 5
    assert ctx.config.procedural_terms


def test_seen_tracks_provision_ids():
    ctx = RetrievalContext(query="q", as_of=date(2021, 1, 1))
    ctx.add({"provision_id": 1, "section_num": "5", "text": "t", "metadata": {}})
    ctx.add({"provision_id": 1, "section_num": "5", "text": "t", "metadata": {}})
    assert len(ctx.candidates) == 1  # dedup by provision_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/pipeline/test_context.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.pipeline.context'`

- [ ] **Step 3: Implement context**

`lawboi/pipeline/context.py`:

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

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/pipeline/test_context.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/pipeline/context.py tests/lawboi/pipeline
git commit -m "add retrieval context + config"
```

---

### Task 12: Retrieval stages

**Files:**
- Create: `lawboi/pipeline/stages.py`
- Test: `tests/lawboi/pipeline/test_stages.py`

Each stage takes the dependencies it needs (ports) and mutates the context. The dense/sparse/procedural/step-back/citation logic is the same as today's `engine.py`, repackaged. `Rerank` is a no-op when no reranker is supplied (preserves the "skip if no COHERE_API_KEY" behavior).

- [ ] **Step 1: Write the failing test**

`tests/lawboi/pipeline/test_stages.py`:

```python
from datetime import date
from lawboi.pipeline.context import RetrievalContext
from lawboi.pipeline.stages import (
    CitationShortCircuit, DenseSearch, SparseSearch, Merge, Rerank, is_citation_query,
)
from lawboi.domain.models import Act, ActVersion, Provision
from tests.lawboi.fakes import InMemoryVectorStore, InMemoryStructuredStore


class StubEmbedder:
    def embed_query(self, text): return [0.1]


def _store_with_provision():
    s = InMemoryStructuredStore()
    aid = s.upsert_act(Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus"))
    vid = s.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h"))
    s.insert_provision(Provision(None, vid, "97", "section", "etteteatamise tähtaeg", None))
    return s


def test_is_citation_query():
    assert is_citation_query("§ 97 töölepingu seadus")
    assert not is_citation_query("notice period")


def test_dense_search_populates_candidates():
    v = InMemoryVectorStore()
    v.upsert(1, [0.1], "doc", {"section_num": "97"})
    ctx = RetrievalContext(query="notice", as_of=date(2021, 1, 1))
    DenseSearch(v, StubEmbedder())(ctx)
    assert ctx.candidates[0]["provision_id"] == 1


def test_sparse_search_uses_fts():
    ctx = RetrievalContext(query="tähtaeg", as_of=date(2021, 1, 1))
    SparseSearch(_store_with_provision())(ctx)
    assert any(c["section_num"] == "97" for c in ctx.candidates)


def test_merge_is_dedup_passthrough():
    ctx = RetrievalContext(query="q", as_of=date(2021, 1, 1))
    ctx.add({"provision_id": 1, "section_num": "1", "text": "t", "metadata": {}})
    Merge()(ctx)
    assert len(ctx.candidates) == 1


def test_rerank_noop_without_reranker():
    ctx = RetrievalContext(query="q", as_of=date(2021, 1, 1))
    ctx.add({"provision_id": 1, "section_num": "1", "text": "t", "metadata": {}})
    Rerank(reranker=None)(ctx)
    assert len(ctx.candidates) == 1


def test_citation_shortcircuit_sets_flag():
    ctx = RetrievalContext(query="§ 97 töölepingu seadus", as_of=date(2021, 1, 1))
    out = CitationShortCircuit(_store_with_provision())(ctx)
    assert out.candidates and out.candidates[0]["section_num"] == "97"
    assert out.config  # short-circuit marks done via _done flag
    assert getattr(out, "_done", False) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/pipeline/test_stages.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.pipeline.stages'`

- [ ] **Step 3: Implement stages**

`lawboi/pipeline/stages.py`:

```python
import logging
import re
from datetime import date
from typing import Optional, Protocol, runtime_checkable

from lawboi.pipeline.context import RetrievalContext
from lawboi.ports.vector_store import VectorStore
from lawboi.ports.structured_store import StructuredStore
from lawboi.ports.llm import LLMProvider

log = logging.getLogger(__name__)


@runtime_checkable
class RetrievalStage(Protocol):
    def __call__(self, ctx: RetrievalContext) -> RetrievalContext: ...


def is_citation_query(query: str) -> bool:
    return bool(re.search(r"§\s*\d+", query))


def _extract_eli(query: str) -> Optional[str]:
    m = re.search(r"RT\s+[IVX]+[\s,][\d\s,\.]+", query)
    return m.group().strip() if m else None


def _extract_title_query(query: str) -> str:
    cleaned = re.sub(r"§\s*\d+[a-z]?", "", query)
    cleaned = re.sub(r"\d{4}-\d{2}-\d{2}", "", cleaned)
    return cleaned.strip()


def _hit_to_dict(hit) -> dict:
    return {"provision_id": hit.provision_id, "section_num": hit.section_num,
            "text": hit.text, "metadata": hit.metadata}


def _rp_to_dict(rp) -> dict:
    return {"provision_id": rp.provision_id, "section_num": rp.section_num,
            "text": rp.text, "metadata": rp.metadata}


class CitationShortCircuit:
    """Exact §-lookup; if it matches, mark the context done so later stages skip."""
    def __init__(self, store: StructuredStore):
        self._store = store

    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if not is_citation_query(ctx.query):
            return ctx
        m = re.search(r"§\s*(\d+[a-z]?)", ctx.query)
        if not m:
            return ctx
        rows = self._store.exact_lookup(
            section_num=m.group(1), as_of=ctx.as_of, limit=ctx.config.limit,
            eli=_extract_eli(ctx.query), title_query=_extract_title_query(ctx.query) or None)
        ctx.add_all([_rp_to_dict(r) for r in rows])
        ctx._done = True
        return ctx


class DenseSearch:
    def __init__(self, vector: VectorStore, embedder):
        self._vector = vector
        self._embedder = embedder

    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if getattr(ctx, "_done", False):
            return ctx
        emb = self._embedder.embed_query(ctx.query)
        ctx.add_all([_hit_to_dict(h) for h in self._vector.query(emb, n_results=20)])
        return ctx


class SparseSearch:
    def __init__(self, store: StructuredStore):
        self._store = store

    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if getattr(ctx, "_done", False):
            return ctx
        ctx.add_all([_rp_to_dict(r) for r in self._store.fts_search(ctx.query, ctx.as_of)])
        return ctx


class ProceduralAugment:
    """Second pass over a query augmented with procedural terms (remedies/deadlines)."""
    def __init__(self, vector: VectorStore, embedder, store: StructuredStore):
        self._vector = vector
        self._embedder = embedder
        self._store = store

    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if getattr(ctx, "_done", False):
            return ctx
        q = f"{ctx.query} {ctx.config.procedural_terms}"
        emb = self._embedder.embed_query(q)
        ctx.add_all([_hit_to_dict(h) for h in self._vector.query(emb, n_results=10)])
        ctx.add_all([_rp_to_dict(r) for r in self._store.fts_search(q, ctx.as_of)])
        return ctx


_STEP_BACK_PROMPT = (
    "You are a legal research assistant for Estonian law. "
    "Given the user's specific question, generate a single broader, more abstract "
    "legal query that would retrieve the general legal provisions governing this topic. "
    "Reply with ONLY the abstracted query, nothing else. "
    "Write the query in the same language as the input.\n\n"
    "Example:\n"
    "Input: Kas tööandja võib mind haiguslehe ajal vallandada?\n"
    "Output: Töölepingu ülesütlemise piirangud ja keelud\n\n"
    "Input: What happens if I don't pay corporate income tax on time?\n"
    "Output: Consequences and penalties for late payment of corporate income tax\n\n"
    "Input: {query}"
)


class StepBackExpand:
    """Generate an abstracted query via the LLM and retrieve against it."""
    def __init__(self, vector: VectorStore, embedder, store: StructuredStore,
                 llm: Optional[LLMProvider]):
        self._vector = vector
        self._embedder = embedder
        self._store = store
        self._llm = llm

    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if getattr(ctx, "_done", False) or not ctx.config.step_back_enabled or self._llm is None:
            return ctx
        try:
            step_back = self._llm.complete(_STEP_BACK_PROMPT.format(query=ctx.query)).strip()
        except Exception:
            log.warning("Step-back generation failed, skipping", exc_info=True)
            return ctx
        if not step_back or step_back == ctx.query:
            return ctx
        log.info("Step-back query: %s -> %s", ctx.query, step_back)
        emb = self._embedder.embed_query(step_back)
        ctx.add_all([_hit_to_dict(h) for h in self._vector.query(emb, n_results=10)])
        ctx.add_all([_rp_to_dict(r) for r in self._store.fts_search(step_back, ctx.as_of)])
        return ctx


class Merge:
    """Dedup is already handled by RetrievalContext.add; Merge is the explicit
    ordering boundary and a hook for future scoring."""
    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        return ctx


class Rerank:
    def __init__(self, reranker=None):
        self._reranker = reranker

    def __call__(self, ctx: RetrievalContext) -> RetrievalContext:
        if self._reranker is None or not ctx.candidates:
            return ctx
        from llama_index.core.schema import NodeWithScore, TextNode, QueryBundle
        nodes = [NodeWithScore(node=TextNode(text=c["text"], id_=str(c["provision_id"])))
                 for c in ctx.candidates]
        ranked = self._reranker.postprocess_nodes(nodes, QueryBundle(ctx.query))
        order = {int(n.node.id_): i for i, n in enumerate(ranked)}
        ctx.candidates.sort(key=lambda c: order.get(c["provision_id"], len(order)))
        return ctx
```

> Note: the original `engine.py` did not invoke the Cohere reranker in `retrieve()` even though it constructed one. This task wires it in as a stage. If you must preserve byte-identical ranking behavior instead, make `Rerank.__call__` a pure pass-through and revisit when adding rerank coverage to the retrieval eval. Default here: wire it, because the spec lists reranking as an explicit stage.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/pipeline/test_stages.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/pipeline/stages.py tests/lawboi/pipeline/test_stages.py
git commit -m "add composable retrieval stages"
```

---

### Task 13: Pipeline builder + RetrievalService

**Files:**
- Create: `lawboi/pipeline/retrieval.py`
- Test: `tests/lawboi/pipeline/test_retrieval.py`

- [ ] **Step 1: Write the failing test**

`tests/lawboi/pipeline/test_retrieval.py`:

```python
from datetime import date
from lawboi.pipeline.retrieval import RetrievalService, run_pipeline
from lawboi.pipeline.context import RetrievalContext
from lawboi.pipeline.stages import DenseSearch, Merge
from tests.lawboi.fakes import InMemoryVectorStore


class StubEmbedder:
    def embed_query(self, text): return [0.1]


def test_run_pipeline_threads_context():
    v = InMemoryVectorStore()
    v.upsert(1, [0.1], "doc", {"section_num": "5"})
    stages = [DenseSearch(v, StubEmbedder()), Merge()]
    ctx = run_pipeline(stages, query="q", as_of=date(2021, 1, 1))
    assert ctx.candidates[0]["provision_id"] == 1


def test_service_returns_limited_dicts():
    v = InMemoryVectorStore()
    for i in range(10):
        v.upsert(i, [0.1], f"doc{i}", {"section_num": str(i)})
    svc = RetrievalService([DenseSearch(v, StubEmbedder()), Merge()], default_limit=5)
    out = svc.retrieve("q")
    assert len(out) == 5
    assert out[0]["provision_id"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/pipeline/test_retrieval.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.pipeline.retrieval'`

- [ ] **Step 3: Implement pipeline + service**

`lawboi/pipeline/retrieval.py`:

```python
from datetime import date
from typing import Optional

from lawboi.pipeline.context import RetrievalContext, RetrievalConfig
from lawboi.pipeline.stages import RetrievalStage


def run_pipeline(stages: list[RetrievalStage], query: str, as_of: date,
                 config: Optional[RetrievalConfig] = None) -> RetrievalContext:
    ctx = RetrievalContext(query=query, as_of=as_of, config=config or RetrievalConfig())
    for stage in stages:
        ctx = stage(ctx)
    return ctx


class RetrievalService:
    def __init__(self, stages: list[RetrievalStage], default_limit: int = 5):
        self._stages = stages
        self._default_limit = default_limit

    def retrieve(self, query: str, as_of: Optional[date] = None,
                 limit: Optional[int] = None) -> list[dict]:
        limit = limit or self._default_limit
        config = RetrievalConfig(limit=limit)
        ctx = run_pipeline(self._stages, query, as_of or date.today(), config)
        return ctx.candidates[:limit]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/pipeline/test_retrieval.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/pipeline/retrieval.py tests/lawboi/pipeline/test_retrieval.py
git commit -m "add pipeline runner + RetrievalService"
```

---

### Task 14: Ingest helpers (relocate) + IngestService

**Files:**
- Create: `lawboi/ingest/embedder.py`, `lawboi/ingest/chunker.py`, `lawboi/ingest/service.py`
- Test: `tests/lawboi/ingest/test_chunker.py`, `tests/lawboi/ingest/test_service.py`

- [ ] **Step 1: Create test dir + failing chunker test**

```bash
mkdir -p tests/lawboi/ingest && touch tests/lawboi/ingest/__init__.py
```

`tests/lawboi/ingest/test_chunker.py`:

```python
from lawboi.ingest.chunker import chunk_provisions
from lawboi.domain.models import Provision


def test_chunk_includes_neighbour_context():
    provs = [
        Provision(1, 10, "1", "section", "esimene", None, None),
        Provision(2, 10, "2", "section", "teine", None, None),
        Provision(3, 10, "3", "section", "kolmas", None, None),
    ]
    chunks = chunk_provisions(provs, act_title="TLS", eli="RT I 2009, 5, 35")
    assert len(chunks) == 3
    assert "esimene" in chunks[1].metadata["context"]
    assert "kolmas" in chunks[1].metadata["context"]
    assert chunks[1].metadata["eli"] == "RT I 2009, 5, 35"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/ingest/test_chunker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.ingest.chunker'`

- [ ] **Step 3a: Relocate embedder + chunker**

- Port verbatim from `ingest/embedder.py:1-22` into `lawboi/ingest/embedder.py` (unchanged).
- Port verbatim from `ingest/chunker.py:1-37` into `lawboi/ingest/chunker.py`, changing only the import line 1 to `from lawboi.domain.models import Provision, Chunk`.

- [ ] **Step 3b: Run chunker test**

Run: `.venv/bin/python -m pytest tests/lawboi/ingest/test_chunker.py -v`
Expected: 1 passed

- [ ] **Step 4a: Write the failing IngestService test**

`tests/lawboi/ingest/test_service.py`:

```python
from datetime import date
from lawboi.ingest.service import IngestService
from lawboi.domain.models import Act, ActVersion, Provision, Chunk
from tests.lawboi.fakes import InMemoryStructuredStore, InMemoryVectorStore


class StubEmbedder:
    def embed_passage(self, text): return [0.1]


def test_index_act_writes_store_and_vector():
    store, vector = InMemoryStructuredStore(), InMemoryVectorStore()
    svc = IngestService(store, vector, StubEmbedder())
    act = Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus")
    version = ActVersion(None, 0, date(2020, 1, 1), None, "u", "h")
    provisions = [Provision(None, 0, "1", "section", "reguleerimisala", None, None)]
    chunks = [Chunk(None, 0, "1", "reguleerimisala", {"eli": "RT I 2009, 5, 35"})]
    svc.index_act(act, version, provisions, chunks)
    assert store.fts_search("reguleerimisala", date(2021, 1, 1))
    assert vector.query([0.1], 5)


def test_index_act_skips_when_version_already_populated():
    store, vector = InMemoryStructuredStore(), InMemoryVectorStore()
    svc = IngestService(store, vector, StubEmbedder())
    act = Act(None, "RT I 2009, 5, 35", "TLS", None, "general", "seadus")
    version = ActVersion(None, 0, date(2020, 1, 1), None, "u", "h")
    p = [Provision(None, 0, "1", "section", "x", None, None)]
    c = [Chunk(None, 0, "1", "x", {})]
    svc.index_act(act, version, p, c)
    svc.index_act(act, version, p, c)  # second call must be a no-op
    assert len(store.fts_search("x", date(2021, 1, 1))) == 1
```

- [ ] **Step 4b: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/ingest/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.ingest.service'`

- [ ] **Step 5: Implement IngestService**

`lawboi/ingest/service.py`:

```python
from lawboi.domain.models import Act, ActVersion, Provision, Chunk
from lawboi.ports.structured_store import StructuredStore
from lawboi.ports.vector_store import VectorStore


class IngestService:
    """Writes act metadata to the structured store and provision embeddings to
    the vector store, keeping the two in sync (mirrors index_act in indexer.py)."""

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
            embedding = self._embedder.embed_passage(chunk.text)
            self._vector.upsert(chunk.provision_id, embedding, chunk.text, chunk.metadata)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/ingest -v`
Expected: chunker (1) + service (2) = 3 passed

- [ ] **Step 7: Commit**

```bash
git add lawboi/ingest tests/lawboi/ingest
git commit -m "relocate embedder/chunker + add IngestService"
```

---

## Phase 4 — Real adapters + integration tests

> Integration tests in this phase need live Postgres + Chroma. Start them first:
> `docker-compose up -d db chroma`. If containers fail, check `colima status`.

### Task 15: Postgres connection pool

**Files:**
- Create: `lawboi/adapters/structured/pool.py`
- Test: `tests/lawboi/adapters/structured/test_pool.py` (integration)

- [ ] **Step 1: Create test dirs + failing test**

```bash
mkdir -p tests/lawboi/adapters/structured && touch tests/lawboi/adapters/structured/__init__.py
```

`tests/lawboi/adapters/structured/test_pool.py`:

```python
import os
import pytest
from lawboi.adapters.structured.pool import make_pool, pooled_cursor

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="requires live Postgres")


def test_pooled_cursor_executes_and_returns_connection():
    pool = make_pool("test", minconn=1, maxconn=2)
    with pooled_cursor(pool) as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
    # borrowing again must succeed (connection was returned)
    with pooled_cursor(pool) as cur:
        cur.execute("SELECT 2")
        assert cur.fetchone()[0] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/adapters/structured/test_pool.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.adapters.structured.pool'` (or SKIPPED if `DATABASE_URL` unset — set it from your `.env` to run this)

- [ ] **Step 3: Implement the pool**

`lawboi/adapters/structured/pool.py`:

```python
import os
from contextlib import contextmanager

from psycopg2.pool import ThreadedConnectionPool


def make_pool(database_url: Optional_str := None, minconn: int = 1,
              maxconn: int = 10) -> ThreadedConnectionPool:
    dsn = database_url or os.environ["DATABASE_URL"]
    return ThreadedConnectionPool(minconn, maxconn, dsn=dsn)


@contextmanager
def pooled_cursor(pool: ThreadedConnectionPool):
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
```

Correct the signature — Python has no `Optional_str` token. Use:

```python
from typing import Optional
...
def make_pool(database_url: Optional[str] = None, minconn: int = 1,
              maxconn: int = 10) -> ThreadedConnectionPool:
    dsn = database_url or os.environ["DATABASE_URL"]
    return ThreadedConnectionPool(minconn, maxconn, dsn=dsn)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DATABASE_URL=$(grep -E '^DATABASE_URL' .env | cut -d= -f2-) .venv/bin/python -m pytest tests/lawboi/adapters/structured/test_pool.py -v`
Expected: 1 passed (or skipped if no DB)

- [ ] **Step 5: Commit**

```bash
git add lawboi/adapters/structured/pool.py tests/lawboi/adapters/structured/test_pool.py
git commit -m "add postgres connection pool"
```

---

### Task 16: PostgresStore adapter

**Files:**
- Create: `lawboi/adapters/structured/postgres.py`
- Test: `tests/lawboi/adapters/structured/test_postgres.py` (integration)

This adapter implements `StructuredStore`. Write-side methods are ported from `ingest/indexer.py:21-75` (the `upsert_act`/`upsert_act_version`/`insert_provision` SQL). Read-side methods are ported from `retrieval/engine.py`: `fts_search` from `_pg_fts_search` (lines 124-160) and `exact_lookup` from `_exact_lookup` (lines 162-237), returning `RetrievedProvision` instead of dicts.

- [ ] **Step 1: Write the failing test**

`tests/lawboi/adapters/structured/test_postgres.py`:

```python
import os
from datetime import date
import pytest
from lawboi.adapters.structured.pool import make_pool
from lawboi.adapters.structured.postgres import PostgresStore
from lawboi.domain.models import Act, ActVersion, Provision

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="requires live Postgres")


@pytest.fixture
def store():
    return PostgresStore(make_pool(minconn=1, maxconn=2))


def test_write_then_fts_search(store):
    aid = store.upsert_act(Act(None, "RT I TEST 1", "Testseadus", None, "general", "seadus"))
    vid = store.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h"))
    store.insert_provision(Provision(None, vid, "99", "section", "unikaalmärksõna", None, None))
    hits = store.fts_search("unikaalmärksõna", date(2021, 1, 1))
    assert any(h.section_num == "99" for h in hits)


def test_exact_lookup_by_section(store):
    aid = store.upsert_act(Act(None, "RT I TEST 2", "Teine", None, "general", "seadus"))
    vid = store.upsert_act_version(ActVersion(None, aid, date(2000, 1, 1), None, "u", "h"))
    store.insert_provision(Provision(None, vid, "203", "section", "äriühing", None, None))
    rows = store.exact_lookup("203", date(2021, 1, 1), limit=5, eli="RT I TEST 2", title_query=None)
    assert rows and rows[0].section_num == "203"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/adapters/structured/test_postgres.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.adapters.structured.postgres'`

- [ ] **Step 3: Implement PostgresStore**

Create `lawboi/adapters/structured/postgres.py`. Structure:

```python
from datetime import date
from typing import Optional

from lawboi.adapters.structured.pool import pooled_cursor
from lawboi.domain.models import Act, ActVersion, Provision
from lawboi.domain.dto import RetrievedProvision


class PostgresStore:
    def __init__(self, pool):
        self._pool = pool

    # --- write side: port SQL from ingest/indexer.py:21-75 ---
    def upsert_act(self, act: Act) -> int: ...
    def upsert_act_version(self, version: ActVersion) -> int: ...
    def insert_provision(self, provision: Provision) -> int: ...

    def version_has_provisions(self, act_version_id: int) -> bool:
        with pooled_cursor(self._pool) as cur:
            cur.execute("SELECT 1 FROM provision WHERE act_version_id=%s LIMIT 1",
                        (act_version_id,))
            return cur.fetchone() is not None

    # --- read side: port SQL from retrieval/engine.py:124-237 ---
    def fts_search(self, query: str, effective_date: date) -> list[RetrievedProvision]: ...
    def exact_lookup(self, section_num: str, as_of: date, limit: int,
                     eli: Optional[str], title_query: Optional[str]) -> list[RetrievedProvision]: ...
```

Implementation rules for the engineer:
- Each method opens `with pooled_cursor(self._pool) as cur:` instead of the old `db_cursor()`.
- `upsert_act`, `upsert_act_version`, `insert_provision`: copy the exact SQL + params from `indexer.py:22-75`, returning `cur.fetchone()[0]`.
- `fts_search`: copy the SQL from `engine.py:126-143`; map each row to `RetrievedProvision(provision_id=r[0], section_num=r[1], text=r[2], metadata={"act_title": r[4], "eli": r[5], "section_num": r[1], "act_version_id": r[3], "is_translation": False, "context": ""})` (same dict the old code built at lines 144-159, wrapped in the DTO).
- `exact_lookup`: copy the branching SQL logic from `engine.py:162-237` verbatim, but take `eli`/`title_query` as parameters (the old code extracted them internally — that extraction now lives in `CitationShortCircuit`). Return `RetrievedProvision` objects with the same metadata mapping as above.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/adapters/structured/test_postgres.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/adapters/structured/postgres.py tests/lawboi/adapters/structured/test_postgres.py
git commit -m "add PostgresStore adapter (pooled repository)"
```

---

### Task 17: ChromaVectorStore adapter

**Files:**
- Create: `lawboi/adapters/vector/chroma.py`
- Test: `tests/lawboi/adapters/vector/test_chroma.py` (integration)

Implements `VectorStore`. `upsert` mirrors `indexer.py:upsert_provision_to_chroma` (lines 78-85). `query` wraps `collection.query(...)` and maps Chroma's nested result arrays into `VectorHit` objects (the mapping logic in `engine.py:_merge_into` lines 247-261).

- [ ] **Step 1: Create test dir + failing test**

```bash
mkdir -p tests/lawboi/adapters/vector && touch tests/lawboi/adapters/vector/__init__.py
```

`tests/lawboi/adapters/vector/test_chroma.py`:

```python
import os
import pytest
from lawboi.adapters.vector.chroma import ChromaVectorStore
from lawboi.domain.dto import VectorHit

pytestmark = pytest.mark.skipif(
    not os.getenv("CHROMA_HOST"), reason="requires live Chroma")


def test_upsert_then_query():
    store = ChromaVectorStore(os.getenv("CHROMA_HOST", "localhost"),
                              int(os.getenv("CHROMA_PORT", "8001")))
    store.upsert(424242, [0.01] * 1024, "test document körges",
                 {"section_num": "1", "eli": "RT I TEST"})
    hits = store.query([0.01] * 1024, n_results=5)
    assert hits and isinstance(hits[0], VectorHit)
    assert any(h.provision_id == 424242 for h in hits)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/adapters/vector/test_chroma.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.adapters.vector.chroma'`

- [ ] **Step 3: Implement ChromaVectorStore**

`lawboi/adapters/vector/chroma.py`:

```python
import chromadb

from lawboi.domain.dto import VectorHit


class ChromaVectorStore:
    def __init__(self, host: str, port: int, collection: str = "provisions"):
        self._collection = chromadb.HttpClient(host=host, port=port) \
            .get_or_create_collection(collection)

    def upsert(self, provision_id: int, embedding: list[float],
               document: str, metadata: dict) -> None:
        self._collection.upsert(
            ids=[f"provision_{provision_id}"],
            embeddings=[embedding],
            documents=[document],
            metadatas=[metadata],
        )

    def query(self, embedding: list[float], n_results: int) -> list[VectorHit]:
        res = self._collection.query(query_embeddings=[embedding], n_results=n_results)
        hits: list[VectorHit] = []
        if res.get("ids") and res["ids"][0]:
            for i, doc_id in enumerate(res["ids"][0]):
                pid = int(doc_id.replace("provision_", ""))
                meta = res["metadatas"][0][i]
                hits.append(VectorHit(
                    provision_id=pid,
                    section_num=meta.get("section_num", ""),
                    text=res["documents"][0][i],
                    metadata=meta,
                ))
        return hits
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/adapters/vector/test_chroma.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/adapters/vector/chroma.py tests/lawboi/adapters/vector/test_chroma.py
git commit -m "add ChromaVectorStore adapter"
```

---

### Task 18: RiigiTeataja law source (parser relocate + adapter)

**Files:**
- Create: `lawboi/adapters/source/parser.py`, `lawboi/adapters/source/riigiteataja.py`
- Test: `tests/lawboi/adapters/source/test_parser.py`

The parser is pure (no network) and already tested today; relocate it verbatim. The `RiigiTeatajaSource` adapter wraps the existing `scraper.py` network functions behind the `LawSource` port, converting to `ActMeta`/`RawAct`.

- [ ] **Step 1: Create test dir + failing test**

```bash
mkdir -p tests/lawboi/adapters/source && touch tests/lawboi/adapters/source/__init__.py
```

`tests/lawboi/adapters/source/test_parser.py`:

```python
from datetime import date
from lawboi.adapters.source.parser import parse_act_xml, parse_act_title

SAMPLE = b"""<?xml version="1.0"?>
<akt>
  <pealkiri>Testseadus</pealkiri>
  <paragrahv nr="1"><pealkiri>Reguleerimisala</pealkiri>
    <loige>Kaesolev seadus reguleerib.</loige>
  </paragrahv>
</akt>"""


def test_parse_title():
    assert parse_act_title(SAMPLE) == "Testseadus"


def test_parse_provisions():
    provs = parse_act_xml(SAMPLE, act_version_id=0,
                          effective_from=date(2020, 1, 1), effective_to=None)
    assert provs
    assert provs[0].section_num == "1"
```

> If these field/tag expectations don't match the relocated parser's behavior, that's a pre-existing parser issue flagged in CLAUDE.md (RT XML tag names unverified) — not introduced by this task. Adjust the sample to match the parser's actual `TAGS`, or port the assertions from the existing `tests/ingest/test_parser.py` which already pass against the current parser.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/adapters/source/test_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.adapters.source.parser'`

- [ ] **Step 3a: Relocate the parser**

Port verbatim from `ingest/parser.py` into `lawboi/adapters/source/parser.py`, changing only the model import to `from lawboi.domain.models import Provision`. Keep all functions and the `TAGS` dict unchanged.

- [ ] **Step 3b: Port the existing parser tests as the safety net**

Copy the test bodies from `tests/ingest/test_parser.py` into `tests/lawboi/adapters/source/test_parser.py` (replacing the SAMPLE-based sketch above), updating imports to `lawboi.adapters.source.parser`. These already encode the parser's real behavior.

- [ ] **Step 3c: Implement the adapter**

`lawboi/adapters/source/riigiteataja.py`:

```python
from datetime import date
from typing import Optional

from lawboi.domain.dto import ActMeta, RawAct
from lawboi.domain.errors import SourceFetchError
# scraper still lives at repo root until cutover; import it directly
from ingest.scraper import search_acts, fetch_act_xml


def _to_date(v: Optional[str]) -> Optional[date]:
    return date.fromisoformat(v) if v else None


class RiigiTeatajaSource:
    def search(self, query: str, limit: int = 10) -> list[ActMeta]:
        try:
            raw = search_acts(query, limit=limit)
        except Exception as e:
            raise SourceFetchError(f"search failed: {e}") from e
        out = []
        for m in raw:
            k = m.get("kehtivus", {})
            out.append(ActMeta(
                global_id=m["globaalID"],
                title=m.get("pealkiri", str(m["globaalID"])),
                effective_from=_to_date(k.get("algus")),
                effective_to=_to_date(k.get("lopp")),
            ))
        return out

    def fetch(self, global_id: int) -> RawAct:
        try:
            xml_bytes, source_url = fetch_act_xml(global_id)
        except Exception as e:
            raise SourceFetchError(f"fetch failed for {global_id}: {e}") from e
        return RawAct(global_id=global_id, xml=xml_bytes, source_url=source_url)
```

> Note: this preserves the existing (CLAUDE.md-flagged, untested) numeric-globaalID fetch path exactly. Isolating it behind `LawSource` is the point — fixing the RT API URL format is out of scope for this plan and tracked separately.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/adapters/source/test_parser.py -v`
Expected: all passed (count = number ported from the original parser tests)

- [ ] **Step 5: Commit**

```bash
git add lawboi/adapters/source tests/lawboi/adapters/source
git commit -m "relocate parser + add RiigiTeataja law source adapter"
```

---

## Phase 5 — Composition root + API

### Task 19: Composition root

**Files:**
- Create: `lawboi/config/composition.py`
- Test: `tests/lawboi/config/test_composition.py`

The container is built two ways: `build_container(settings)` for production (real adapters) and a direct `Container(...)` for tests (fakes). The test verifies the test-construction path and that `build_pipeline` assembles stages in the documented order.

- [ ] **Step 1: Write the failing test**

`tests/lawboi/config/test_composition.py`:

```python
from lawboi.config.composition import Container, build_pipeline
from lawboi.pipeline.stages import (
    CitationShortCircuit, DenseSearch, SparseSearch, ProceduralAugment,
    StepBackExpand, Merge, Rerank,
)
from tests.lawboi.fakes import (
    FakeLLMProvider, InMemoryVectorStore, InMemoryStructuredStore,
)


class StubEmbedder:
    def embed_query(self, text): return [0.1]
    def embed_passage(self, text): return [0.1]


def test_build_pipeline_order():
    stages = build_pipeline(
        store=InMemoryStructuredStore(), vector=InMemoryVectorStore(),
        embedder=StubEmbedder(), llm=FakeLLMProvider(), reranker=None)
    types = [type(s) for s in stages]
    assert types == [CitationShortCircuit, DenseSearch, SparseSearch,
                     ProceduralAugment, StepBackExpand, Merge, Rerank]


def test_container_holds_services():
    from lawboi.pipeline.retrieval import RetrievalService
    from lawboi.answer.service import AnswerService
    from lawboi.ingest.service import IngestService
    c = Container(
        retrieval=RetrievalService([], default_limit=5),
        answer=AnswerService(FakeLLMProvider()),
        ingest=IngestService(InMemoryStructuredStore(), InMemoryVectorStore(), StubEmbedder()),
    )
    assert c.retrieval and c.answer and c.ingest
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/config/test_composition.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.config.composition'`

- [ ] **Step 3: Implement composition**

`lawboi/config/composition.py`:

```python
from dataclasses import dataclass
from typing import Optional

from lawboi.config.settings import Settings
from lawboi.ingest.embedder import Embedder
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


def build_pipeline(store, vector, embedder, llm, reranker):
    return [
        CitationShortCircuit(store),
        DenseSearch(vector, embedder),
        SparseSearch(store),
        ProceduralAugment(vector, embedder, store),
        StepBackExpand(vector, embedder, store, llm),
        Merge(),
        Rerank(reranker),
    ]


def _build_reranker(settings: Settings):
    if not settings.cohere_api_key:
        return None
    try:
        from llama_index.postprocessor.cohere_rerank import CohereRerank
    except ImportError:
        return None
    return CohereRerank(api_key=settings.cohere_api_key, top_n=5)


def build_container(settings: Settings) -> Container:
    from lawboi.adapters.structured.pool import make_pool
    from lawboi.adapters.structured.postgres import PostgresStore
    from lawboi.adapters.vector.chroma import ChromaVectorStore
    from lawboi.adapters.llm.factory import build_llm

    store = PostgresStore(make_pool(settings.database_url,
                                    settings.db_pool_min, settings.db_pool_max))
    vector = ChromaVectorStore(settings.chroma_host, settings.chroma_port)
    embedder = Embedder()
    llm = build_llm(settings.llm_model)
    reranker = _build_reranker(settings)

    stages = build_pipeline(store, vector, embedder, llm, reranker)
    return Container(
        retrieval=RetrievalService(stages, default_limit=5),
        answer=AnswerService(llm),
        ingest=IngestService(store, vector, embedder),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/config/test_composition.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/config/composition.py tests/lawboi/config/test_composition.py
git commit -m "add composition root"
```

---

### Task 20: API schemas + exception handlers + deps

**Files:**
- Create: `lawboi/api/schemas.py`, `lawboi/api/errors.py`, `lawboi/api/deps.py`
- Test: `tests/lawboi/api/test_errors.py`

- [ ] **Step 1: Create test dir + failing test**

```bash
mkdir -p tests/lawboi/api && touch tests/lawboi/api/__init__.py
```

`tests/lawboi/api/test_errors.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient
from lawboi.api.errors import register_exception_handlers
from lawboi.domain.errors import NoSourcesFoundError, UnsupportedModelError


def _app():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom-422")
    def boom_422():
        raise NoSourcesFoundError("none")

    @app.get("/boom-400")
    def boom_400():
        raise UnsupportedModelError("gpt-5")

    return TestClient(app)


def test_no_sources_maps_to_422():
    assert _app().get("/boom-422").status_code == 422


def test_unsupported_model_maps_to_400():
    r = _app().get("/boom-400")
    assert r.status_code == 400
    assert "gpt-5" in r.json()["detail"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/api/test_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.api.errors'`

- [ ] **Step 3a: Implement schemas**

Port verbatim from `api/schemas.py:1-42` into `lawboi/api/schemas.py` (unchanged — `AnswerRequest`, `Citation`, `AnswerResponse`, `SearchRequest`, `ProvisionResult`).

- [ ] **Step 3b: Implement exception handlers**

`lawboi/api/errors.py`:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lawboi.domain.errors import (
    NoSourcesFoundError, UnsupportedModelError, NoModelConfiguredError,
)

_STATUS = {
    NoSourcesFoundError: 422,
    UnsupportedModelError: 400,
    NoModelConfiguredError: 503,
}


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type, status in _STATUS.items():
        app.add_exception_handler(exc_type, _make_handler(status))


def _make_handler(status: int):
    async def handler(request: Request, exc: Exception):
        return JSONResponse(status_code=status, content={"detail": str(exc)})
    return handler
```

- [ ] **Step 3c: Implement deps**

`lawboi/api/deps.py`:

```python
from functools import lru_cache

from lawboi.config.settings import Settings
from lawboi.config.composition import build_container, Container


@lru_cache
def get_container() -> Container:
    return build_container(Settings())


def get_retrieval():
    return get_container().retrieval


def get_answer():
    return get_container().answer
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/api/test_errors.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/api/schemas.py lawboi/api/errors.py lawboi/api/deps.py tests/lawboi/api/test_errors.py
git commit -m "add API schemas, exception handlers, and DI deps"
```

---

### Task 21: API routes + app

**Files:**
- Create: `lawboi/api/routes/answer.py`, `lawboi/api/routes/search.py`, `lawboi/api/routes/acts.py`, `lawboi/api/main.py`
- Test: `tests/lawboi/api/test_routes.py`

Routes use `Depends` and let domain errors bubble to the handlers. The 422 guard is no longer in the route — `AnswerService.answer` raises `NoSourcesFoundError`.

- [ ] **Step 1: Write the failing test**

`tests/lawboi/api/test_routes.py`:

```python
from fastapi.testclient import TestClient
from lawboi.api.main import app
from lawboi.api.deps import get_retrieval, get_answer
from lawboi.pipeline.retrieval import RetrievalService
from lawboi.answer.service import AnswerService
from tests.lawboi.fakes import FakeLLMProvider


class StubRetrieval(RetrievalService):
    def __init__(self, provisions):
        self._provisions = provisions
    def retrieve(self, query, as_of=None, limit=None):
        return self._provisions


def _client(provisions):
    app.dependency_overrides[get_retrieval] = lambda: StubRetrieval(provisions)
    app.dependency_overrides[get_answer] = lambda: AnswerService(
        FakeLLMProvider(responses=["Under § 97 notice applies."]))
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def _prov():
    return {"provision_id": 1, "section_num": "97", "text": "tekst",
            "metadata": {"act_title": "TLS", "eli": "RT I 2009, 5, 35",
                         "subsection": "", "is_translation": False}}


def test_answer_returns_200_with_sources():
    r = _client([_prov()]).post("/answer", json={"query": "notice period?"})
    assert r.status_code == 200
    assert r.json()["citations"][0]["section"] == "§ 97"


def test_answer_returns_422_without_sources():
    r = _client([]).post("/answer", json={"query": "who wins my lawsuit?"})
    assert r.status_code == 422


def test_search_returns_provision_results():
    r = _client([_prov()]).post("/search", json={"query": "notice", "limit": 5})
    assert r.status_code == 200
    assert r.json()[0]["section_num"] == "97"


def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/lawboi/api/test_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lawboi.api.main'`

- [ ] **Step 3a: Implement answer route**

`lawboi/api/routes/answer.py`:

```python
from fastapi import APIRouter, Depends

from lawboi.api.schemas import AnswerRequest, AnswerResponse
from lawboi.api.deps import get_retrieval, get_answer
from lawboi.adapters.llm.factory import available_models

router = APIRouter()


@router.post("/answer", response_model=AnswerResponse)
def answer(req: AnswerRequest, retrieval=Depends(get_retrieval), answerer=Depends(get_answer)):
    provisions = retrieval.retrieve(req.query, as_of=req.as_of_date)
    result = answerer.answer(req.query, provisions)  # raises NoSourcesFoundError -> 422
    return AnswerResponse(**result)


@router.get("/models")
def models():
    return {"models": available_models()}
```

- [ ] **Step 3b: Implement search route**

`lawboi/api/routes/search.py`:

```python
from fastapi import APIRouter, Depends

from lawboi.api.schemas import ProvisionResult, SearchRequest
from lawboi.api.deps import get_retrieval

router = APIRouter()


@router.post("/search", response_model=list[ProvisionResult])
def search(req: SearchRequest, retrieval=Depends(get_retrieval)):
    provisions = retrieval.retrieve(req.query, as_of=req.as_of_date, limit=req.limit)
    return [
        ProvisionResult(
            provision_id=p["provision_id"],
            section_num=p["section_num"],
            text_et=p["text"],
            act_title=p.get("metadata", {}).get("act_title", ""),
            eli=p.get("metadata", {}).get("eli", ""),
        )
        for p in provisions
    ]
```

- [ ] **Step 3c: Implement acts route**

Port the three endpoints from `api/routes/acts.py:1-58` into `lawboi/api/routes/acts.py`, but replace the `db_cursor()` usage with the pooled cursor via the container. Concretely, change the import and each `with db_cursor() as cur:` to use a dependency:

```python
from datetime import date
from fastapi import APIRouter, Depends, HTTPException

from lawboi.api.deps import get_container
from lawboi.adapters.structured.pool import pooled_cursor

router = APIRouter()


def _cursor(container=Depends(get_container)):
    # PostgresStore exposes its pool for read-only act queries
    return container


# Each endpoint body: keep the exact SQL from api/routes/acts.py, but open
#   with pooled_cursor(container.retrieve_pool()) as cur:
# To support this, add a `pool` property to PostgresStore (Task 16) OR expose
# the pool on the container. Simplest: add `pool` to Container.
```

> Decision for the engineer: the acts route needs raw DB access that isn't part of any service. Cleanest minimal option: add a read-only method set to `StructuredStore` later, but that's scope creep. For now, expose the pool on `Container` (add `pool` field in Task 19's `Container` and set it in `build_container`) and use `pooled_cursor(container.pool)` with the verbatim SQL from `api/routes/acts.py:11-58`. Keep the `404` for missing act.

If you took the "expose pool on Container" option, update Task 19's `Container` dataclass to include `pool` and pass it in `build_container` — re-run `tests/lawboi/config/test_composition.py` (update `Container(...)` construction in that test to pass `pool=None`).

- [ ] **Step 3d: Implement main app**

`lawboi/api/main.py`:

```python
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lawboi.api.errors import register_exception_handlers

app = FastAPI(title="Eesti Õigusabi API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/lawboi/api/test_routes.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add lawboi/api tests/lawboi/api/test_routes.py
git commit -m "add API routes + app with DI and exception mapping"
```

---

### Task 22: Ingest CLI entrypoint

**Files:**
- Create: `lawboi/ingest/__main__.py`
- Test: manual (network-dependent; covered by service tests already)

Replaces `python -m ingest.indexer` with `python -m lawboi.ingest`. Reuses `run_ingest` orchestration from `indexer.py:88-144` but built on the new services/source.

- [ ] **Step 1: Implement the entrypoint**

`lawboi/ingest/__main__.py`:

```python
import sys
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from lawboi.config.settings import Settings
from lawboi.config.composition import build_container
from lawboi.adapters.source.riigiteataja import RiigiTeatajaSource
from lawboi.adapters.source.parser import (
    parse_act_xml, parse_act_title, _parse_effective_date,
)
from lawboi.ingest.chunker import chunk_provisions
from lawboi.domain.models import Act, ActVersion
from ingest.scraper import compute_hash  # still at repo root until cutover


def run_ingest(query: str) -> None:
    container = build_container(Settings())
    source = RiigiTeatajaSource()

    if query.isdigit():
        metas = source.search(query, limit=1) if not query.isdigit() else None
        ids = [int(query)]
        titles = {int(query): str(query)}
        froms, tos = {int(query): None}, {int(query): None}
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
        eff_from_xml, eff_to_xml = _parse_effective_date(raw.xml)
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
        version = ActVersion(None, 0, eff_from, eff_to, raw.source_url, source_hash)
        chunks = chunk_provisions(provisions, act_title=title_xml, eli=eli)
        container.ingest.index_act(act, version, provisions, chunks)
        print(f"    Indexed {len(provisions)} provisions.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m lawboi.ingest <query|globaalID>")
        sys.exit(1)
    run_ingest(sys.argv[1])
```

- [ ] **Step 2: Smoke-test the CLI help path**

Run: `.venv/bin/python -m lawboi.ingest`
Expected: prints `Usage: python -m lawboi.ingest <query|globaalID>` and exits 1.

- [ ] **Step 3: Commit**

```bash
git add lawboi/ingest/__main__.py
git commit -m "add lawboi.ingest CLI entrypoint"
```

---

## Phase 6 — Eval + cutover

### Task 23: Point eval at the new package

**Files:**
- Modify: `eval/retrieval_eval.py:21-22`

`run_eval.py` is black-box (HTTP) and needs no change. `retrieval_eval.py` imports the engine directly and must switch to the new service via the container.

- [ ] **Step 1: Update retrieval_eval imports + engine construction**

In `eval/retrieval_eval.py`, replace lines 21-22:

```python
from ingest.embedder import Embedder
from retrieval.engine import RetrievalEngine
```

with:

```python
from lawboi.config.settings import Settings
from lawboi.config.composition import build_container
```

and replace line 86 (`engine = RetrievalEngine(Embedder())`) with:

```python
engine = build_container(Settings()).retrieval
```

`engine.retrieve(case["query"], limit=max(k, 20))` still works — `RetrievalService.retrieve` has the same signature.

- [ ] **Step 2: Smoke-test it imports (needs infra to actually run)**

Run: `.venv/bin/python -c "import eval.retrieval_eval; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add eval/retrieval_eval.py
git commit -m "point retrieval eval at lawboi container"
```

---

### Task 24: Full parity run + delete old modules

**Files:**
- Delete: `ingest/` (except keep nothing), `retrieval/`, `answer/`, `api/`, `db/` old packages — but **keep `ingest/scraper.py`** until its network logic is relocated, OR relocate it now (see step 2).
- Modify: `CLAUDE.md` command examples
- Delete: old `tests/answer`, `tests/api`, `tests/retrieval`, `tests/ingest` (superseded by `tests/lawboi`)

- [ ] **Step 1: Run the full new test suite green**

Run: `docker-compose up -d db chroma && .venv/bin/python -m pytest tests/lawboi -v`
Expected: all pass (unit tests always; integration tests pass with infra up).

- [ ] **Step 2: Relocate the remaining scraper network code**

Move `ingest/scraper.py` to `lawboi/adapters/source/riigiteataja_client.py` (verbatim), and update the two imports that reference it (`lawboi/adapters/source/riigiteataja.py` and `lawboi/ingest/__main__.py`) from `ingest.scraper` to `lawboi.adapters.source.riigiteataja_client`.

Run: `.venv/bin/python -c "import lawboi.adapters.source.riigiteataja; import lawboi.ingest.__main__; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Delete the old top-level packages and their tests**

```bash
git rm -r ingest retrieval answer api db
git rm -r tests/ingest tests/retrieval tests/answer tests/api
```

- [ ] **Step 4: Update CLAUDE.md command examples**

In `CLAUDE.md`, change:
- `python -m ingest.indexer "TLS"` → `python -m lawboi.ingest "TLS"` (and the other two examples)
- `uvicorn api.main:app --reload --port 8000` → `uvicorn lawboi.api.main:app --reload --port 8000`
- Update the "48 tests" count note and the architecture/invariants sections to reference the new module paths (`lawboi/answer/service.py`, `lawboi/pipeline/`, etc.).

- [ ] **Step 5: Final full run + parity check**

Run: `.venv/bin/python -m pytest -v`
Expected: all pass, no references to deleted modules.

Run (with API up): `uvicorn lawboi.api.main:app --port 8000 &` then `python eval/run_eval.py --api http://localhost:8000`
Expected: eval completes; citation precision/recall/refusal numbers in the same ballpark as before the rewrite.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "cut over to lawboi package; remove legacy modules; update docs"
```

---

## Self-review notes (gaps & decisions surfaced for the executor)

- **Reranker behavior change:** old `engine.py` built a Cohere reranker but never called it in `retrieve()`. Task 12 wires it as a real stage. Flagged inline with a fallback to pass-through if byte-identical ranking is required.
- **`acts` route raw DB access:** doesn't belong to a service. Task 21 chooses "expose pool on Container" as the minimal option and notes the Task 19 `Container` update it requires. If you prefer, add read methods to `StructuredStore` instead (cleaner, more work).
- **Untested ingest paths preserved, not fixed:** numeric-globaalID fetch and RT XML tag names remain as-is behind `LawSource`/parser (CLAUDE.md-flagged). Out of scope; isolation is the deliverable.
- **Parser test sample is a sketch:** Task 18 step 3b ports the real existing parser tests as the authoritative safety net rather than trusting the illustrative SAMPLE.
- **`.venv` may be absent** in a fresh checkout (pyrightconfig references it). If `.venv/bin/python` doesn't exist, create it: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
```
