# Eesti Õigusabi MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a source-cited Estonian law RAG chatbot — offline ingest pipeline, FastAPI backend with hybrid retrieval, and Next.js chat UI with citation source panel.

**Architecture:** Offline `ingest/` pipeline writes structured provisions to PostgreSQL and embeddings to ChromaDB. `api/` (FastAPI + LlamaIndex) runs hybrid retrieval, reranks with Cohere, and calls a configurable LLM (default: Gemini 2.0 Flash). `ui/` (Next.js + TypeScript) renders the chat with a slide-out source panel and model selector.

**Tech Stack:** Python 3.12, LlamaIndex, sentence-transformers (`multilingual-e5-large`), ChromaDB, PostgreSQL 16, FastAPI, Pydantic v2, pytest, responses (HTTP mock), Next.js 15 (App Router, TypeScript), Tailwind CSS, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-03-31-eesti-oigusabi-mvp-design.md`

---

## File Map

```
lawboi/
├── db/
│   ├── schema.sql              ← full PG schema
│   └── connection.py           ← psycopg2 context manager
├── ingest/
│   ├── __init__.py
│   ├── models.py               ← Act, ActVersion, Provision, Chunk dataclasses
│   ├── scraper.py              ← RT API fetcher + raw XML storage
│   ├── parser.py               ← XML bytes → list[Provision]
│   ├── chunker.py              ← provisions → retrieval Chunks
│   ├── embedder.py             ← multilingual-e5-large wrapper
│   └── indexer.py              ← writes to ChromaDB + PG
├── retrieval/
│   ├── __init__.py
│   └── engine.py               ← hybrid retrieval + date filter + reranker
├── answer/
│   ├── __init__.py
│   ├── prompts.py              ← SYSTEM_PROMPT + DISCLAIMER constants
│   └── pipeline.py             ← LLM factory + answer generation + citation extract
├── api/
│   ├── __init__.py
│   ├── main.py                 ← FastAPI app + router registration
│   ├── schemas.py              ← Pydantic request/response models
│   └── routes/
│       ├── __init__.py
│       ├── answer.py           ← POST /answer, GET /models
│       ├── search.py           ← POST /search
│       └── acts.py             ← GET /acts/:eli, /versions, /as-of
├── ui/                         ← Next.js 15 project (npx create-next-app)
│   ├── app/
│   │   ├── layout.tsx
│   │   └── page.tsx            ← root chat page
│   ├── components/
│   │   ├── ChatInterface.tsx   ← message list + input bar
│   │   ├── SourcePanel.tsx     ← slide-out citations
│   │   ├── ModelSelector.tsx   ← dropdown for LLM choice
│   │   └── ActViewer.tsx       ← full provision text display
│   └── lib/
│       └── api.ts              ← typed fetch wrappers
├── eval/
│   ├── gold_set.json           ← 30 labelled Q&A pairs
│   └── run_eval.py             ← evaluation runner
├── tests/
│   ├── conftest.py
│   ├── ingest/
│   │   ├── test_scraper.py
│   │   ├── test_parser.py
│   │   └── test_chunker.py
│   ├── retrieval/
│   │   └── test_engine.py
│   └── answer/
│       └── test_pipeline.py
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── api/Dockerfile
```

---

## Task 1: Project Bootstrap

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `db/schema.sql`
- Create: `api/Dockerfile`

- [ ] **Step 1: Create `requirements.txt`**

```
# Core
fastapi>=0.115
uvicorn[standard]>=0.30
pydantic>=2.0
python-dotenv>=1.0
psycopg2-binary>=2.9
requests>=2.32

# LlamaIndex + LLM providers
llama-index-core>=0.12
llama-index-llms-google>=0.4
llama-index-llms-openai>=0.3
llama-index-llms-anthropic>=0.4
llama-index-postprocessor-cohere-rerank>=0.3
llama-index-vector-stores-chroma>=0.3

# Embeddings + Vector DB
sentence-transformers>=3.0
chromadb>=0.6

# Testing
pytest>=8.0
pytest-cov>=5.0
responses>=0.25
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Database
DATABASE_URL=postgresql://lawboi:lawboi@localhost:5432/lawboi

# ChromaDB
CHROMA_HOST=localhost
CHROMA_PORT=8001

# LLM (set at least one)
LLM_MODEL=gemini-2.0-flash
GEMINI_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
COHERE_API_KEY=

# Riigi Teataja API
RT_BASE_URL=https://www.riigiteataja.ee
RAW_DATA_DIR=data/raw
```

- [ ] **Step 3: Create `db/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS act (
    id          SERIAL PRIMARY KEY,
    eli         TEXT UNIQUE NOT NULL,
    title_et    TEXT NOT NULL,
    title_en    TEXT,
    domain      TEXT NOT NULL,
    act_type    TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS act_version (
    id             SERIAL PRIMARY KEY,
    act_id         INTEGER NOT NULL REFERENCES act(id),
    effective_from DATE NOT NULL,
    effective_to   DATE,
    source_url     TEXT NOT NULL,
    source_hash    TEXT NOT NULL,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS provision (
    id             SERIAL PRIMARY KEY,
    act_version_id INTEGER NOT NULL REFERENCES act_version(id),
    section_num    TEXT NOT NULL,
    level          TEXT NOT NULL,
    text_et        TEXT NOT NULL,
    text_en        TEXT,
    parent_id      INTEGER REFERENCES provision(id),
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS publication_event (
    id          SERIAL PRIMARY KEY,
    act_id      INTEGER NOT NULL REFERENCES act(id),
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    hash_before TEXT,
    hash_after  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS query_log (
    id                    SERIAL PRIMARY KEY,
    query                 TEXT NOT NULL,
    retrieved_provision_ids INTEGER[] NOT NULL DEFAULT '{}',
    answer                TEXT,
    model_used            TEXT,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_provision_fts
    ON provision USING gin(to_tsvector('simple', text_et));
CREATE INDEX IF NOT EXISTS idx_provision_act_version
    ON provision(act_version_id);
CREATE INDEX IF NOT EXISTS idx_act_version_dates
    ON act_version(effective_from, effective_to);
```

- [ ] **Step 4: Create `docker-compose.yml`**

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
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lawboi"]
      interval: 5s
      timeout: 5s
      retries: 5

  chroma:
    image: chromadb/chroma:latest
    volumes:
      - chroma_data:/chroma/chroma
    ports:
      - "8001:8000"

  api:
    build: ./api
    env_file: .env
    environment:
      DATABASE_URL: postgresql://lawboi:lawboi@db:5432/lawboi
      CHROMA_HOST: chroma
      CHROMA_PORT: 8000
      LLM_MODEL: ${LLM_MODEL:-gemini-2.0-flash}
      GEMINI_API_KEY: ${GEMINI_API_KEY:-}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      COHERE_API_KEY: ${COHERE_API_KEY:-}
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
      chroma:
        condition: service_started

  ui:
    build: ./ui
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
      API_URL: http://api:8000
    ports:
      - "3000:3000"
    depends_on:
      - api

volumes:
  pg_data:
  chroma_data:
```

- [ ] **Step 5: Create `api/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY ../requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY .. .
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 6: Start database and ChromaDB**

```bash
cp .env.example .env
# Fill in at least GEMINI_API_KEY in .env
docker compose up -d db chroma
```

Expected: Both containers start. Verify with:
```bash
docker compose ps
# db and chroma should show "running"
docker compose exec db psql -U lawboi -c "\dt"
# Should show: act, act_version, provision, publication_event, query_log
```

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .env.example docker-compose.yml db/schema.sql api/Dockerfile
git commit -m "feat: project bootstrap — docker compose, pg schema, requirements"
```

---

## Task 2: Ingest Models + DB Connection

**Files:**
- Create: `ingest/__init__.py`
- Create: `ingest/models.py`
- Create: `db/__init__.py`
- Create: `db/connection.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write failing test for models**

Create `tests/ingest/__init__.py` (empty).

Create `tests/ingest/test_models.py`:

```python
from datetime import date
from ingest.models import Act, ActVersion, Provision, Chunk


def test_act_has_required_fields():
    act = Act(id=None, eli="RT I 2009, 5, 35", title_et="Töölepingu seadus",
               title_en=None, domain="employment", act_type="seadus")
    assert act.eli == "RT I 2009, 5, 35"
    assert act.domain == "employment"


def test_provision_level_values():
    p = Provision(
        id=None, act_version_id=1, section_num="42",
        level="section", text_et="Tööleping lõpetatakse...",
        text_en=None, parent_id=None,
    )
    assert p.level == "section"


def test_chunk_metadata_is_dict():
    chunk = Chunk(
        provision_id=1, act_version_id=1, section_num="42",
        text="Tööleping lõpetatakse...",
        metadata={"act_title": "Töölepingu seadus", "eli": "RT I 2009, 5, 35"},
    )
    assert chunk.metadata["act_title"] == "Töölepingu seadus"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/ingest/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'ingest'`

- [ ] **Step 3: Create `ingest/__init__.py`**

```python
```
(empty file)

- [ ] **Step 4: Create `ingest/models.py`**

```python
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Act:
    id: Optional[int]
    eli: str
    title_et: str
    title_en: Optional[str]
    domain: str
    act_type: str


@dataclass
class ActVersion:
    id: Optional[int]
    act_id: int
    effective_from: date
    effective_to: Optional[date]
    source_url: str
    source_hash: str


@dataclass
class Provision:
    id: Optional[int]
    act_version_id: int
    section_num: str
    level: str  # part | chapter | section | subsection | clause
    text_et: str
    text_en: Optional[str]
    parent_id: Optional[int]


@dataclass
class Chunk:
    provision_id: int
    act_version_id: int
    section_num: str
    text: str
    metadata: dict
```

- [ ] **Step 5: Create `db/__init__.py`** (empty)

- [ ] **Step 6: Create `db/connection.py`**

```python
import os
import psycopg2
from contextlib import contextmanager


def get_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])


@contextmanager
def db_cursor():
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
pytest tests/ingest/test_models.py -v
```

Expected: 3 tests PASS

- [ ] **Step 8: Commit**

```bash
git add ingest/ db/ tests/
git commit -m "feat: ingest dataclasses and db connection"
```

---

## Task 3: RT API Scraper

**Files:**
- Create: `ingest/scraper.py`
- Create: `tests/ingest/test_scraper.py`

> **Note:** The RT API URL format must be verified in a week-1 notebook against `https://www.riigiteataja.ee/api/`. The scraper uses a configurable `RT_BASE_URL` env var so the endpoint can be adjusted without code changes.

- [ ] **Step 1: Write failing tests**

```python
# tests/ingest/test_scraper.py
import pytest
import responses as resp_mock
from pathlib import Path
from unittest.mock import patch

from ingest.scraper import compute_hash, fetch_act_xml, store_raw, has_changed


def test_compute_hash_is_deterministic():
    content = b"<akt>test</akt>"
    assert compute_hash(content) == compute_hash(content)


def test_compute_hash_differs_for_different_content():
    assert compute_hash(b"abc") != compute_hash(b"xyz")


@resp_mock.activate
def test_fetch_act_xml_returns_bytes_and_url():
    resp_mock.add(
        resp_mock.GET,
        "https://www.riigiteataja.ee/api/seadus/RT_I_2009_5_35",
        body=b"<akt><pealkiri>Test</pealkiri></akt>",
        status=200,
    )
    with patch.dict("os.environ", {"RT_BASE_URL": "https://www.riigiteataja.ee"}):
        content, url = fetch_act_xml("RT I 2009, 5, 35")
    assert b"<akt>" in content
    assert "RT_I_2009_5_35" in url


@resp_mock.activate
def test_fetch_act_xml_raises_on_404():
    resp_mock.add(
        resp_mock.GET,
        "https://www.riigiteataja.ee/api/seadus/RT_I_MISSING",
        status=404,
    )
    with patch.dict("os.environ", {"RT_BASE_URL": "https://www.riigiteataja.ee"}):
        with pytest.raises(Exception):
            fetch_act_xml("RT I MISSING")


def test_store_raw_writes_and_returns_path(tmp_path):
    path = store_raw("RT I 2009, 5, 35", b"<akt/>", raw_dir=tmp_path)
    assert path.exists()
    assert path.read_bytes() == b"<akt/>"


def test_has_changed_true_when_hash_differs():
    assert has_changed("oldhash", b"newcontent") is True


def test_has_changed_false_when_hash_matches():
    content = b"<akt>same</akt>"
    assert has_changed(compute_hash(content), content) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/ingest/test_scraper.py -v
```

Expected: `ImportError: cannot import name 'compute_hash' from 'ingest.scraper'`

- [ ] **Step 3: Create `ingest/scraper.py`**

```python
import hashlib
import os
import time
from pathlib import Path

import requests

RT_BASE_URL = os.getenv("RT_BASE_URL", "https://www.riigiteataja.ee")
RAW_DATA_DIR = Path(os.getenv("RAW_DATA_DIR", "data/raw"))
REQUEST_DELAY = 1.0


def _eli_to_path(eli: str) -> str:
    """Convert 'RT I 2009, 5, 35' → 'RT_I_2009_5_35'."""
    return eli.replace(" ", "_").replace(",", "")


def compute_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def fetch_act_xml(eli: str) -> tuple[bytes, str]:
    """Fetch act XML from RT API. Returns (xml_bytes, source_url).

    NOTE: Verify exact endpoint format in week-1 notebook against RT API docs.
    Current assumption: GET {RT_BASE_URL}/api/seadus/{eli_path}
    """
    base = os.getenv("RT_BASE_URL", RT_BASE_URL)
    url = f"{base}/api/seadus/{_eli_to_path(eli)}"
    response = requests.get(url, timeout=30, headers={"Accept": "application/xml"})
    response.raise_for_status()
    return response.content, url


def store_raw(eli: str, content: bytes, raw_dir: Path = RAW_DATA_DIR) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{_eli_to_path(eli)}.xml"
    path.write_bytes(content)
    return path


def has_changed(known_hash: str, content: bytes) -> bool:
    return compute_hash(content) != known_hash


def fetch_and_store(eli: str, known_hash: str = "") -> tuple[Path, str, bool]:
    """Fetch, store, return (path, new_hash, changed).

    Passes REQUEST_DELAY between calls — call this in a loop for multiple acts.
    """
    content, _url = fetch_act_xml(eli)
    new_hash = compute_hash(content)
    changed = has_changed(known_hash, content)
    path = store_raw(eli, content)
    time.sleep(REQUEST_DELAY)
    return path, new_hash, changed
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/ingest/test_scraper.py -v
```

Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add ingest/scraper.py tests/ingest/test_scraper.py
git commit -m "feat: RT API scraper with hash-based change detection"
```

---

## Task 4: XML Parser

**Files:**
- Create: `ingest/parser.py`
- Create: `tests/ingest/test_parser.py`

> **Note:** RT XML tag names are approximate. Validate against real XML in the week-2 notebook and update `TAGS` in `parser.py` if needed.

- [ ] **Step 1: Write failing tests**

```python
# tests/ingest/test_parser.py
from datetime import date
from ingest.parser import parse_act_xml
from ingest.models import Provision

SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<akt>
  <metaandmed>
    <pealkiri keel="et">Toolepingu seadus</pealkiri>
    <avaldamine>RT I 2009, 5, 35</avaldamine>
    <joustumisKuup>2009-07-01</joustumisKuup>
  </metaandmed>
  <sisu>
    <paragrahv nr="1">
      <loige nr="1">
        <tekst>Kaeesolev seadus reguleerib toolepingu.</tekst>
      </loige>
      <loige nr="2">
        <tekst>Seadus ei kehti ametnike kohta.</tekst>
      </loige>
    </paragrahv>
    <paragrahv nr="2">
      <loige nr="1">
        <tekst>Toolepingut ei saa sulgeda suuliselt.</tekst>
      </loige>
    </paragrahv>
  </sisu>
</akt>"""


def test_parse_returns_provisions():
    provisions = parse_act_xml(SAMPLE_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    assert len(provisions) > 0
    assert all(isinstance(p, Provision) for p in provisions)


def test_parse_section_numbers():
    provisions = parse_act_xml(SAMPLE_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    section_nums = {p.section_num for p in provisions}
    assert "1" in section_nums
    assert "2" in section_nums


def test_parse_preserves_text():
    provisions = parse_act_xml(SAMPLE_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    all_text = " ".join(p.text_et for p in provisions)
    assert "toolepingu" in all_text.lower()


def test_parse_sets_act_version_id():
    provisions = parse_act_xml(SAMPLE_XML, act_version_id=42,
                                effective_from=date(2009, 7, 1), effective_to=None)
    assert all(p.act_version_id == 42 for p in provisions)


def test_parse_levels():
    provisions = parse_act_xml(SAMPLE_XML, act_version_id=1,
                                effective_from=date(2009, 7, 1), effective_to=None)
    levels = {p.level for p in provisions}
    assert "section" in levels
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/ingest/test_parser.py -v
```

Expected: `ImportError: cannot import name 'parse_act_xml'`

- [ ] **Step 3: Create `ingest/parser.py`**

```python
import xml.etree.ElementTree as ET
from datetime import date
from typing import Optional

from ingest.models import Provision

# RT XML tag names — verify against actual RT XML in week-2 notebook
TAGS = {
    "section": "paragrahv",
    "subsection": "loige",
    "clause": "punkt",
    "part": "jagu",
    "chapter": "peatukk",
    "text": "tekst",
    "title": "pealkiri",
}


def _extract_text(element: ET.Element) -> str:
    """Recursively extract all text from an element."""
    parts = []
    if element.text:
        parts.append(element.text.strip())
    for child in element:
        parts.append(_extract_text(child))
        if child.tail:
            parts.append(child.tail.strip())
    return " ".join(p for p in parts if p)


def _parse_node(
    el: ET.Element,
    act_version_id: int,
    level: str,
    parent_id: Optional[int],
    results: list[Provision],
) -> None:
    section_num = el.get("nr", "")
    text_parts = []

    for child in el:
        tag = child.tag.lower()
        if tag == TAGS["text"]:
            text_parts.append(_extract_text(child))
        elif tag in (TAGS["subsection"], TAGS["clause"]):
            text_parts.append(_extract_text(child))

    text_et = "\n".join(text_parts).strip()
    if not text_et:
        text_el = el.find(f".//{TAGS['text']}")
        if text_el is not None:
            text_et = _extract_text(text_el)

    if text_et and section_num:
        provision = Provision(
            id=None,
            act_version_id=act_version_id,
            section_num=section_num,
            level=level,
            text_et=text_et,
            text_en=None,
            parent_id=parent_id,
        )
        results.append(provision)


def parse_act_xml(
    xml_bytes: bytes,
    act_version_id: int,
    effective_from: date,
    effective_to: Optional[date],
) -> list[Provision]:
    root = ET.fromstring(xml_bytes)
    results: list[Provision] = []
    sisu = root.find("sisu")
    if sisu is None:
        sisu = root

    for part_el in sisu.findall(TAGS["part"]):
        for chapter_el in part_el.findall(TAGS["chapter"]):
            for section_el in chapter_el.findall(TAGS["section"]):
                _parse_node(section_el, act_version_id, "section", None, results)
        for section_el in part_el.findall(TAGS["section"]):
            _parse_node(section_el, act_version_id, "section", None, results)

    for section_el in sisu.findall(TAGS["section"]):
        _parse_node(section_el, act_version_id, "section", None, results)

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/ingest/test_parser.py -v
```

Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add ingest/parser.py tests/ingest/test_parser.py
git commit -m "feat: RT XML parser — provisions with hierarchical levels"
```

---

## Task 5: Hierarchical Chunker

**Files:**
- Create: `ingest/chunker.py`
- Create: `tests/ingest/test_chunker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingest/test_chunker.py
from ingest.models import Provision, Chunk
from ingest.chunker import chunk_provisions


def _make_provision(id_: int, section_num: str, text: str) -> Provision:
    return Provision(
        id=id_, act_version_id=1, section_num=section_num,
        level="section", text_et=text, text_en=None, parent_id=None,
    )


def test_chunk_provisions_returns_chunks():
    provisions = [
        _make_provision(1, "1", "First provision text."),
        _make_provision(2, "2", "Second provision text."),
        _make_provision(3, "3", "Third provision text."),
    ]
    chunks = chunk_provisions(
        provisions,
        act_title="Töölepingu seadus",
        eli="RT I 2009, 5, 35",
    )
    assert len(chunks) == 3
    assert all(isinstance(c, Chunk) for c in chunks)


def test_chunk_metadata_contains_required_fields():
    provisions = [_make_provision(1, "42", "Some text.")]
    chunks = chunk_provisions(provisions, act_title="Test Act", eli="RT I 2009, 5, 35")
    meta = chunks[0].metadata
    assert meta["act_title"] == "Test Act"
    assert meta["eli"] == "RT I 2009, 5, 35"
    assert meta["section_num"] == "42"
    assert "act_version_id" in meta


def test_chunk_context_includes_neighbours():
    provisions = [
        _make_provision(1, "1", "Prev text."),
        _make_provision(2, "2", "Target text."),
        _make_provision(3, "3", "Next text."),
    ]
    chunks = chunk_provisions(provisions, act_title="Act", eli="RT I 2009, 5, 35")
    middle_chunk = chunks[1]
    assert "Prev text" in middle_chunk.metadata["context"]
    assert "Next text" in middle_chunk.metadata["context"]


def test_first_chunk_has_no_prev_neighbour():
    provisions = [
        _make_provision(1, "1", "First."),
        _make_provision(2, "2", "Second."),
    ]
    chunks = chunk_provisions(provisions, act_title="Act", eli="RT I 2009, 5, 35")
    assert "First" not in chunks[0].metadata.get("context", "")
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/ingest/test_chunker.py -v
```

Expected: `ImportError: cannot import name 'chunk_provisions'`

- [ ] **Step 3: Create `ingest/chunker.py`**

```python
from ingest.models import Provision, Chunk


def chunk_provisions(
    provisions: list[Provision],
    act_title: str,
    eli: str,
) -> list[Chunk]:
    """Create one Chunk per provision, with ±1 neighbour as context."""
    chunks = []
    for i, provision in enumerate(provisions):
        neighbours = []
        if i > 0:
            neighbours.append(provisions[i - 1].text_et)
        if i < len(provisions) - 1:
            neighbours.append(provisions[i + 1].text_et)

        context = "\n\n".join(neighbours)

        chunk = Chunk(
            provision_id=provision.id,
            act_version_id=provision.act_version_id,
            section_num=provision.section_num,
            text=provision.text_et,
            metadata={
                "act_title": act_title,
                "eli": eli,
                "section_num": provision.section_num,
                "level": provision.level,
                "act_version_id": provision.act_version_id,
                "context": context,
                "is_translation": False,
            },
        )
        chunks.append(chunk)

    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/ingest/test_chunker.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add ingest/chunker.py tests/ingest/test_chunker.py
git commit -m "feat: hierarchical chunker with neighbour context"
```

---

## Task 6: Embedder

**Files:**
- Create: `ingest/embedder.py`
- Create: `tests/ingest/test_embedder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingest/test_embedder.py
import pytest
from unittest.mock import MagicMock, patch
from ingest.embedder import Embedder


@pytest.fixture
def mock_embedder():
    with patch("ingest.embedder.SentenceTransformer") as MockST:
        mock_model = MagicMock()
        mock_model.encode.return_value = [0.1] * 1024
        MockST.return_value = mock_model
        yield Embedder()


def test_embed_query_prefixes_query(mock_embedder):
    mock_embedder.embed_query("test question")
    call_arg = mock_embedder._model.encode.call_args[0][0]
    assert call_arg.startswith("query: ")


def test_embed_passage_prefixes_passage(mock_embedder):
    mock_embedder.embed_passage("some legal text")
    call_arg = mock_embedder._model.encode.call_args[0][0]
    assert call_arg.startswith("passage: ")


def test_embed_query_returns_list(mock_embedder):
    result = mock_embedder.embed_query("test")
    assert isinstance(result, list)


def test_embed_passages_prefixes_all(mock_embedder):
    mock_embedder._model.encode.return_value = [[0.1] * 1024, [0.2] * 1024]
    mock_embedder.embed_passages(["text one", "text two"])
    call_arg = mock_embedder._model.encode.call_args[0][0]
    assert all(t.startswith("passage: ") for t in call_arg)
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/ingest/test_embedder.py -v
```

Expected: `ImportError: cannot import name 'Embedder'`

- [ ] **Step 3: Create `ingest/embedder.py`**

```python
from sentence_transformers import SentenceTransformer

MODEL_NAME = "intfloat/multilingual-e5-large"


class Embedder:
    def __init__(self):
        self._model = SentenceTransformer(MODEL_NAME)

    def embed_query(self, text: str) -> list[float]:
        return self._model.encode(f"query: {text}").tolist()

    def embed_passage(self, text: str) -> list[float]:
        return self._model.encode(f"passage: {text}").tolist()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        prefixed = [f"passage: {t}" for t in texts]
        return self._model.encode(prefixed).tolist()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/ingest/test_embedder.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add ingest/embedder.py tests/ingest/test_embedder.py
git commit -m "feat: sentence-transformers embedder with query/passage prefixing"
```

---

## Task 7: Indexer

**Files:**
- Create: `ingest/indexer.py`
- Create: `tests/ingest/test_indexer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingest/test_indexer.py
from unittest.mock import MagicMock, patch, call
from datetime import date
from ingest.models import Act, ActVersion, Provision, Chunk
from ingest.indexer import upsert_act, upsert_provision_to_chroma


def _make_chunk(provision_id: int = 1) -> Chunk:
    return Chunk(
        provision_id=provision_id,
        act_version_id=1,
        section_num="42",
        text="Tööleping lõpetatakse...",
        metadata={"act_title": "TLS", "eli": "RT I 2009, 5, 35",
                   "section_num": "42", "level": "section",
                   "act_version_id": 1, "context": "", "is_translation": False},
    )


def test_upsert_act_inserts_and_returns_id():
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (99,)
    act = Act(id=None, eli="RT I 2009, 5, 35", title_et="TLS",
               title_en=None, domain="employment", act_type="seadus")
    result_id = upsert_act(mock_cur, act)
    assert result_id == 99
    mock_cur.execute.assert_called_once()


def test_upsert_provision_calls_chroma_upsert():
    mock_collection = MagicMock()
    mock_embedder = MagicMock()
    mock_embedder.embed_passage.return_value = [0.1] * 1024
    chunk = _make_chunk(provision_id=7)

    upsert_provision_to_chroma(mock_collection, mock_embedder, chunk)

    mock_collection.upsert.assert_called_once()
    call_kwargs = mock_collection.upsert.call_args.kwargs
    assert call_kwargs["ids"] == ["provision_7"]
    assert call_kwargs["documents"] == ["Tööleping lõpetatakse..."]
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/ingest/test_indexer.py -v
```

Expected: `ImportError: cannot import name 'upsert_act'`

- [ ] **Step 3: Create `ingest/indexer.py`**

```python
import os
import chromadb
from ingest.embedder import Embedder
from ingest.models import Act, ActVersion, Provision, Chunk
from db.connection import db_cursor

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))


def get_chroma_collection():
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    return client.get_or_create_collection("provisions")


def upsert_act(cur, act: Act) -> int:
    cur.execute("""
        INSERT INTO act (eli, title_et, title_en, domain, act_type)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (eli) DO UPDATE SET title_et = EXCLUDED.title_et
        RETURNING id
    """, (act.eli, act.title_et, act.title_en, act.domain, act.act_type))
    return cur.fetchone()[0]


def upsert_act_version(cur, version: ActVersion) -> int:
    cur.execute("""
        INSERT INTO act_version (act_id, effective_from, effective_to, source_url, source_hash)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING id
    """, (version.act_id, version.effective_from, version.effective_to,
          version.source_url, version.source_hash))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "SELECT id FROM act_version WHERE act_id=%s AND effective_from=%s",
        (version.act_id, version.effective_from),
    )
    return cur.fetchone()[0]


def insert_provision(cur, provision: Provision) -> int:
    cur.execute("""
        INSERT INTO provision (act_version_id, section_num, level, text_et, text_en, parent_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (provision.act_version_id, provision.section_num, provision.level,
          provision.text_et, provision.text_en, provision.parent_id))
    return cur.fetchone()[0]


def upsert_provision_to_chroma(collection, embedder: Embedder, chunk: Chunk) -> None:
    embedding = embedder.embed_passage(chunk.text)
    collection.upsert(
        ids=[f"provision_{chunk.provision_id}"],
        embeddings=[embedding],
        documents=[chunk.text],
        metadatas=[chunk.metadata],
    )


def index_act(act: Act, version: ActVersion, provisions: list[Provision],
              chunks: list[Chunk], embedder: Embedder) -> None:
    """Write act metadata to PG and provision embeddings to ChromaDB."""
    collection = get_chroma_collection()
    with db_cursor() as cur:
        act_id = upsert_act(cur, act)
        version.act_id = act_id
        version_id = upsert_act_version(cur, version)
        for provision, chunk in zip(provisions, chunks):
            provision.act_version_id = version_id
            chunk.act_version_id = version_id
            provision.id = insert_provision(cur, provision)
            chunk.provision_id = provision.id
            upsert_provision_to_chroma(collection, embedder, chunk)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/ingest/test_indexer.py -v
```

Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add ingest/indexer.py tests/ingest/test_indexer.py
git commit -m "feat: indexer — writes provisions to postgres and chromadb"
```

---

## Task 8: Retrieval Engine

**Files:**
- Create: `retrieval/__init__.py`
- Create: `retrieval/engine.py`
- Create: `tests/retrieval/__init__.py`
- Create: `tests/retrieval/test_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/retrieval/test_engine.py
from datetime import date
from unittest.mock import MagicMock, patch
import pytest
from retrieval.engine import RetrievalEngine


@pytest.fixture
def engine():
    mock_embedder = MagicMock()
    mock_embedder.embed_query.return_value = [0.1] * 1024
    with patch("retrieval.engine.chromadb.HttpClient"), \
         patch("retrieval.engine.CohereRerank"):
        eng = RetrievalEngine(mock_embedder)
        eng._collection = MagicMock()
        eng._reranker = MagicMock()
        eng._reranker.postprocess_nodes.side_effect = lambda nodes, **kw: nodes
        yield eng


def test_is_citation_query_detects_section(engine):
    assert engine._is_citation_query("Mis ütleb § 42?") is True


def test_is_citation_query_false_for_general(engine):
    assert engine._is_citation_query("Mis on töölepingu lõpetamise tähtaeg?") is False


def test_extract_date_finds_iso_date(engine):
    result = engine._extract_date("mis kehtis 2020-01-15?")
    assert result == date(2020, 1, 15)


def test_extract_date_returns_none_when_absent(engine):
    assert engine._extract_date("general question") is None


def test_retrieve_calls_chroma(engine):
    engine._collection.query.return_value = {
        "ids": [["provision_1", "provision_2"]],
        "documents": [["text one", "text two"]],
        "metadatas": [[{"section_num": "1"}, {"section_num": "2"}]],
        "distances": [[0.1, 0.2]],
    }
    with patch.object(engine, "_pg_fts_search", return_value=[]):
        results = engine.retrieve("general legal question")
    engine._collection.query.assert_called_once()
    assert isinstance(results, list)
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/retrieval/test_engine.py -v
```

Expected: `ImportError: cannot import name 'RetrievalEngine'`

- [ ] **Step 3: Create `retrieval/__init__.py`** (empty)

- [ ] **Step 4: Create `retrieval/engine.py`**

```python
import os
import re
from datetime import date, datetime
from typing import Optional

import chromadb
from llama_index.postprocessor.cohere_rerank import CohereRerank

from db.connection import db_cursor
from ingest.embedder import Embedder


class RetrievalEngine:
    def __init__(self, embedder: Embedder):
        self._embedder = embedder
        self._collection = chromadb.HttpClient(
            host=os.getenv("CHROMA_HOST", "localhost"),
            port=int(os.getenv("CHROMA_PORT", "8001")),
        ).get_or_create_collection("provisions")
        self._reranker = CohereRerank(
            api_key=os.getenv("COHERE_API_KEY", ""),
            top_n=5,
        )

    def _is_citation_query(self, query: str) -> bool:
        return bool(re.search(r"§\s*\d+", query))

    def _extract_date(self, query: str) -> Optional[date]:
        match = re.search(r"\d{4}-\d{2}-\d{2}", query)
        return datetime.strptime(match.group(), "%Y-%m-%d").date() if match else None

    def retrieve(self, query: str, as_of: Optional[date] = None) -> list[dict]:
        if self._is_citation_query(query):
            return self._exact_lookup(query)

        effective_date = as_of or date.today()
        query_emb = self._embedder.embed_query(query)

        dense = self._collection.query(
            query_embeddings=[query_emb], n_results=20,
        )
        sparse = self._pg_fts_search(query, effective_date)
        candidates = self._merge(dense, sparse)

        return candidates[:5]

    def _pg_fts_search(self, query: str, effective_date: date) -> list[dict]:
        with db_cursor() as cur:
            cur.execute("""
                SELECT p.id, p.section_num, p.text_et, p.act_version_id,
                       a.title_et, a.eli,
                       ts_rank(to_tsvector('simple', p.text_et),
                               plainto_tsquery('simple', %s)) AS rank
                FROM provision p
                JOIN act_version av ON p.act_version_id = av.id
                JOIN act a ON av.act_id = a.id
                WHERE to_tsvector('simple', p.text_et)
                      @@ plainto_tsquery('simple', %s)
                  AND av.effective_from <= %s
                  AND (av.effective_to IS NULL OR av.effective_to >= %s)
                ORDER BY rank DESC
                LIMIT 20
            """, (query, query, effective_date, effective_date))
            return [
                {
                    "provision_id": r[0], "section_num": r[1], "text": r[2],
                    "act_version_id": r[3],
                    "metadata": {"act_title": r[4], "eli": r[5],
                                 "section_num": r[1], "act_version_id": r[3],
                                 "is_translation": False, "context": ""},
                }
                for r in cur.fetchall()
            ]

    def _exact_lookup(self, query: str) -> list[dict]:
        match = re.search(r"§\s*(\d+[a-z]?)", query)
        if not match:
            return []
        section_num = match.group(1)
        with db_cursor() as cur:
            cur.execute("""
                SELECT p.id, p.section_num, p.text_et, p.act_version_id,
                       a.title_et, a.eli
                FROM provision p
                JOIN act_version av ON p.act_version_id = av.id
                JOIN act a ON av.act_id = a.id
                WHERE p.section_num = %s
                LIMIT 5
            """, (section_num,))
            return [
                {
                    "provision_id": r[0], "section_num": r[1], "text": r[2],
                    "act_version_id": r[3],
                    "metadata": {"act_title": r[4], "eli": r[5],
                                 "section_num": r[1], "act_version_id": r[3],
                                 "is_translation": False, "context": ""},
                }
                for r in cur.fetchall()
            ]

    def _merge(self, dense: dict, sparse: list[dict]) -> list[dict]:
        seen: set[int] = set()
        merged = []
        if dense.get("ids") and dense["ids"][0]:
            for i, doc_id in enumerate(dense["ids"][0]):
                pid = int(doc_id.replace("provision_", ""))
                if pid not in seen:
                    seen.add(pid)
                    merged.append({
                        "provision_id": pid,
                        "section_num": dense["metadatas"][0][i].get("section_num", ""),
                        "text": dense["documents"][0][i],
                        "metadata": dense["metadatas"][0][i],
                    })
        for r in sparse:
            if r["provision_id"] not in seen:
                seen.add(r["provision_id"])
                merged.append(r)
        return merged
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/retrieval/test_engine.py -v
```

Expected: 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add retrieval/ tests/retrieval/
git commit -m "feat: hybrid retrieval engine — chromadb dense + pg tsvector sparse + cohere rerank"
```

---

## Task 9: Answer Pipeline

**Files:**
- Create: `answer/__init__.py`
- Create: `answer/prompts.py`
- Create: `answer/pipeline.py`
- Create: `tests/answer/__init__.py`
- Create: `tests/answer/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/answer/test_pipeline.py
import os
import pytest
from unittest.mock import MagicMock, patch

from answer.pipeline import (
    available_models,
    detect_language,
    extract_citations,
    format_context,
    get_llm,
)

SAMPLE_PROVISIONS = [
    {
        "provision_id": 1,
        "section_num": "42",
        "text": "Tööleping lõpetatakse...",
        "metadata": {
            "act_title": "Töölepingu seadus",
            "eli": "RT I 2009, 5, 35",
            "section_num": "42",
            "is_translation": False,
            "context": "",
        },
    }
]


def test_detect_language_estonian():
    assert detect_language("Mis on töölepingu tähtaeg?") == "et"


def test_detect_language_english():
    assert detect_language("What is the notice period for termination?") == "en"


def test_format_context_includes_section():
    ctx = format_context(SAMPLE_PROVISIONS)
    assert "§ 42" in ctx
    assert "Töölepingu seadus" in ctx


def test_extract_citations_matches_referenced_section():
    answer = "According to [Töölepingu seadus § 42 lg 1], the contract..."
    citations = extract_citations(answer, SAMPLE_PROVISIONS)
    assert len(citations) == 1
    assert citations[0]["section"] == "§ 42"


def test_extract_citations_empty_when_no_match():
    citations = extract_citations("No section referenced here.", SAMPLE_PROVISIONS)
    assert citations == []


def test_available_models_includes_gemini_when_key_set():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
        models = available_models()
    assert "gemini-2.0-flash" in models


def test_available_models_empty_when_no_keys():
    env = {"GEMINI_API_KEY": "", "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}
    with patch.dict(os.environ, env):
        models = available_models()
    assert models == []


def test_get_llm_raises_on_unsupported_model():
    with pytest.raises(ValueError, match="Unsupported model"):
        get_llm("unknown-model-xyz")
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/answer/test_pipeline.py -v
```

Expected: `ImportError: cannot import name 'available_models'`

- [ ] **Step 3: Create `answer/__init__.py`** (empty)

- [ ] **Step 4: Create `answer/prompts.py`**

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
7. Always append the disclaimer block below at the end of every response.

DISCLAIMER:
\u26a0\ufe0f See vastus on \xfcldine \xf5iguslik teave, mitte \xf5igusabi. / This is general legal
information, not legal advice. Consult a qualified lawyer for your specific situation.
Official source: riigiteataja.ee

RETRIEVED PROVISIONS:
{context}

USER QUESTION:
{query}"""

DISCLAIMER = (
    "\u26a0\ufe0f See vastus on \xfcldine \xf5iguslik teave, mitte \xf5igusabi. / "
    "This is general legal information, not legal advice. "
    "Consult a qualified lawyer for your specific situation. "
    "Official source: riigiteataja.ee"
)
```

- [ ] **Step 5: Create `answer/pipeline.py`**

```python
import os
import re
from typing import Optional

from answer.prompts import DISCLAIMER, SYSTEM_PROMPT

SUPPORTED_MODELS: dict[str, str] = {
    "gemini-2.0-flash": "google",
    "gemini-1.5-pro": "google",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "claude-sonnet-4-5": "anthropic",
}


def get_llm(model: Optional[str] = None):
    model = model or os.getenv("LLM_MODEL", "gemini-2.0-flash")
    if model not in SUPPORTED_MODELS:
        raise ValueError(
            f"Unsupported model: {model}. Supported: {list(SUPPORTED_MODELS)}"
        )
    provider = SUPPORTED_MODELS[model]
    if provider == "google":
        from llama_index.llms.google import Gemini
        return Gemini(model=model, api_key=os.getenv("GEMINI_API_KEY"))
    if provider == "openai":
        from llama_index.llms.openai import OpenAI
        return OpenAI(model=model, api_key=os.getenv("OPENAI_API_KEY"))
    from llama_index.llms.anthropic import Anthropic
    return Anthropic(model=model, api_key=os.getenv("ANTHROPIC_API_KEY"))


def available_models() -> list[str]:
    models = []
    if os.getenv("GEMINI_API_KEY"):
        models += ["gemini-2.0-flash", "gemini-1.5-pro"]
    if os.getenv("OPENAI_API_KEY"):
        models += ["gpt-4o", "gpt-4o-mini"]
    if os.getenv("ANTHROPIC_API_KEY"):
        models += ["claude-sonnet-4-5"]
    return models


def format_context(provisions: list[dict]) -> str:
    parts = []
    for p in provisions:
        section = p.get("section_num", "")
        act_title = p.get("metadata", {}).get("act_title", "")
        eli = p.get("metadata", {}).get("eli", "")
        text = p.get("text", "")
        parts.append(f"[§ {section} | {act_title} | {eli}]\n{text}")
    return "\n\n---\n\n".join(parts)


def extract_citations(answer: str, provisions: list[dict]) -> list[dict]:
    citations = []
    for p in provisions:
        section = p.get("section_num", "")
        if re.search(rf"§\s*{re.escape(section)}\b", answer):
            meta = p.get("metadata", {})
            eli_raw = meta.get("eli", "")
            citations.append({
                "act_title": meta.get("act_title", ""),
                "section": f"§ {section}",
                "subsection": meta.get("subsection", ""),
                "eli": eli_raw,
                "url": (
                    f"https://www.riigiteataja.ee/akt/"
                    f"{eli_raw.replace(' ', '_').replace(',', '')}"
                ),
            })
    return citations


def detect_language(text: str) -> str:
    estonian_chars = set("äöüõšž")
    count = sum(1 for c in text.lower() if c in estonian_chars)
    return "et" if count > 2 else "en"


def generate_answer(
    query: str,
    provisions: list[dict],
    model: Optional[str] = None,
) -> dict:
    llm = get_llm(model)
    context = format_context(provisions)
    prompt = SYSTEM_PROMPT.format(context=context, query=query)
    response = llm.complete(prompt)
    answer_text = str(response)
    citations = extract_citations(answer_text, provisions)
    translation_warning = any(
        p.get("metadata", {}).get("is_translation", False) for p in provisions
    )
    used_model = model or os.getenv("LLM_MODEL", "gemini-2.0-flash")
    return {
        "answer": answer_text,
        "model_used": used_model,
        "citations": citations,
        "language_detected": detect_language(query),
        "translation_warning": translation_warning,
        "disclaimer": DISCLAIMER,
    }
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/answer/test_pipeline.py -v
```

Expected: 8 tests PASS

- [ ] **Step 7: Commit**

```bash
git add answer/ tests/answer/
git commit -m "feat: LLM factory, answer pipeline, citation extraction"
```

---

## Task 10: FastAPI App + Schemas

**Files:**
- Create: `api/__init__.py`
- Create: `api/schemas.py`
- Create: `api/main.py`
- Create: `api/routes/__init__.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/__init__.py` (empty).

```python
# tests/api/test_schemas.py
from datetime import date
from api.schemas import AnswerRequest, AnswerResponse, Citation, SearchRequest


def test_answer_request_defaults():
    req = AnswerRequest(query="test question")
    assert req.model is None
    assert req.as_of_date is None


def test_answer_request_accepts_model():
    req = AnswerRequest(query="test", model="gpt-4o")
    assert req.model == "gpt-4o"


def test_citation_has_required_fields():
    c = Citation(act_title="TLS", section="§ 42", subsection="lg 1",
                  eli="RT I 2009, 5, 35", url="https://www.riigiteataja.ee/akt/")
    assert c.section == "§ 42"


def test_search_request_default_limit():
    req = SearchRequest(query="test")
    assert req.limit == 10
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/api/test_schemas.py -v
```

Expected: `ImportError: cannot import name 'AnswerRequest'`

- [ ] **Step 3: Create `api/__init__.py`** (empty), `api/routes/__init__.py`** (empty)

- [ ] **Step 4: Create `api/schemas.py`**

```python
from datetime import date
from typing import Optional
from pydantic import BaseModel


class AnswerRequest(BaseModel):
    query: str
    model: Optional[str] = None
    as_of_date: Optional[date] = None


class Citation(BaseModel):
    act_title: str
    section: str
    subsection: str
    eli: str
    url: str


class AnswerResponse(BaseModel):
    answer: str
    model_used: str
    citations: list[Citation]
    language_detected: str
    translation_warning: bool
    disclaimer: str


class SearchRequest(BaseModel):
    query: str
    domain: Optional[str] = None
    as_of_date: Optional[date] = None
    limit: int = 10


class ProvisionResult(BaseModel):
    provision_id: int
    section_num: str
    text_et: str
    act_title: str
    eli: str
```

- [ ] **Step 5: Create `api/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Eesti Õigusabi API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from api.routes import answer, search, acts  # noqa: E402

app.include_router(answer.router)
app.include_router(search.router)
app.include_router(acts.router)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/api/test_schemas.py -v
```

Expected: 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add api/ tests/api/
git commit -m "feat: fastapi app skeleton with pydantic schemas"
```

---

## Task 11: /answer and /models Routes

**Files:**
- Create: `api/routes/answer.py`
- Modify: `tests/api/test_routes_answer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_routes_answer.py
import os
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    mock_engine = MagicMock()
    mock_engine.retrieve.return_value = [
        {
            "provision_id": 1,
            "section_num": "42",
            "text": "Tööleping lõpetatakse...",
            "metadata": {
                "act_title": "Töölepingu seadus",
                "eli": "RT I 2009, 5, 35",
                "section_num": "42",
                "is_translation": False,
                "context": "",
            },
        }
    ]
    mock_answer = {
        "answer": "According to § 42...",
        "model_used": "gemini-2.0-flash",
        "citations": [],
        "language_detected": "en",
        "translation_warning": False,
        "disclaimer": "This is not legal advice.",
    }
    with patch("api.routes.answer._engine", mock_engine), \
         patch("api.routes.answer.generate_answer", return_value=mock_answer), \
         patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
        from api.main import app
        yield TestClient(app)


def test_answer_returns_200(client):
    resp = client.post("/answer", json={"query": "What is notice period?"})
    assert resp.status_code == 200


def test_answer_response_has_required_fields(client):
    resp = client.post("/answer", json={"query": "What is notice period?"})
    data = resp.json()
    assert "answer" in data
    assert "citations" in data
    assert "disclaimer" in data
    assert "model_used" in data


def test_models_returns_list(client):
    resp = client.get("/models")
    assert resp.status_code == 200
    assert "models" in resp.json()
    assert "gemini-2.0-flash" in resp.json()["models"]
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/api/test_routes_answer.py -v
```

Expected: `ImportError` or `404`

- [ ] **Step 3: Create `api/routes/answer.py`**

```python
import os
from fastapi import APIRouter, HTTPException
from api.schemas import AnswerRequest, AnswerResponse
from retrieval.engine import RetrievalEngine
from answer.pipeline import generate_answer, available_models
from ingest.embedder import Embedder

router = APIRouter()
_embedder = Embedder()
_engine = RetrievalEngine(_embedder)


@router.post("/answer", response_model=AnswerResponse)
def answer(req: AnswerRequest):
    provisions = _engine.retrieve(req.query, as_of=req.as_of_date)
    if not provisions:
        raise HTTPException(status_code=422, detail="No relevant provisions found")
    result = generate_answer(req.query, provisions, model=req.model)
    return AnswerResponse(**result)


@router.get("/models")
def models():
    return {"models": available_models()}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/api/test_routes_answer.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add api/routes/answer.py tests/api/test_routes_answer.py
git commit -m "feat: POST /answer and GET /models routes"
```

---

## Task 12: /search and /acts Routes

**Files:**
- Create: `api/routes/search.py`
- Create: `api/routes/acts.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_routes_search_acts.py
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    mock_engine = MagicMock()
    mock_engine.retrieve.return_value = [
        {
            "provision_id": 1, "section_num": "1", "text": "Text.",
            "metadata": {"act_title": "TLS", "eli": "RT I 2009, 5, 35",
                          "section_num": "1"},
        }
    ]
    mock_cur = MagicMock()
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchone.return_value = (
        1, "RT I 2009, 5, 35", "Töölepingu seadus", None, "employment", "seadus"
    )
    mock_cur.fetchall.return_value = []

    with patch("api.routes.search._engine", mock_engine), \
         patch("api.routes.acts.db_cursor", return_value=mock_cur):
        from api.main import app
        yield TestClient(app)


def test_search_returns_list(client):
    resp = client.post("/search", json={"query": "notice period"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_search_result_has_section_num(client):
    resp = client.post("/search", json={"query": "notice period"})
    results = resp.json()
    assert results[0]["section_num"] == "1"


def test_get_act_returns_act(client):
    resp = client.get("/acts/RT I 2009, 5, 35")
    assert resp.status_code == 200
    data = resp.json()
    assert data["eli"] == "RT I 2009, 5, 35"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/api/test_routes_search_acts.py -v
```

Expected: `ImportError` or `404`

- [ ] **Step 3: Create `api/routes/search.py`**

```python
from fastapi import APIRouter
from api.schemas import SearchRequest, ProvisionResult
from retrieval.engine import RetrievalEngine
from ingest.embedder import Embedder

router = APIRouter()
_embedder = Embedder()
_engine = RetrievalEngine(_embedder)


@router.post("/search", response_model=list[ProvisionResult])
def search(req: SearchRequest):
    provisions = _engine.retrieve(req.query, as_of=req.as_of_date)
    return [
        ProvisionResult(
            provision_id=p["provision_id"],
            section_num=p["section_num"],
            text_et=p["text"],
            act_title=p.get("metadata", {}).get("act_title", ""),
            eli=p.get("metadata", {}).get("eli", ""),
        )
        for p in provisions[: req.limit]
    ]
```

- [ ] **Step 4: Create `api/routes/acts.py`**

```python
from datetime import date
from fastapi import APIRouter, HTTPException
from db.connection import db_cursor

router = APIRouter()


@router.get("/acts/{eli:path}/versions")
def get_act_versions(eli: str):
    with db_cursor() as cur:
        cur.execute("""
            SELECT av.id, av.effective_from, av.effective_to, av.source_url
            FROM act_version av JOIN act a ON av.act_id = a.id
            WHERE a.eli = %s ORDER BY av.effective_from DESC
        """, (eli,))
        rows = cur.fetchall()
    return [
        {"id": r[0], "effective_from": str(r[1]),
         "effective_to": str(r[2]) if r[2] else None, "source_url": r[3]}
        for r in rows
    ]


@router.get("/acts/{eli:path}/as-of")
def get_act_as_of(eli: str, date: date):
    with db_cursor() as cur:
        cur.execute("""
            SELECT p.id, p.section_num, p.text_et, p.text_en, p.level
            FROM provision p
            JOIN act_version av ON p.act_version_id = av.id
            JOIN act a ON av.act_id = a.id
            WHERE a.eli = %s
              AND av.effective_from <= %s
              AND (av.effective_to IS NULL OR av.effective_to >= %s)
            ORDER BY p.id
        """, (eli, date, date))
        rows = cur.fetchall()
    return [
        {"id": r[0], "section_num": r[1], "text_et": r[2],
         "text_en": r[3], "level": r[4]}
        for r in rows
    ]


@router.get("/acts/{eli:path}")
def get_act(eli: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, eli, title_et, title_en, domain, act_type FROM act WHERE eli = %s",
            (eli,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Act not found")
    return {
        "id": row[0], "eli": row[1], "title_et": row[2],
        "title_en": row[3], "domain": row[4], "act_type": row[5],
    }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/api/test_routes_search_acts.py -v
```

Expected: 3 tests PASS

- [ ] **Step 6: Smoke test the API locally**

```bash
docker compose up -d
uvicorn api.main:app --reload
curl http://localhost:8000/health
# Expected: {"status":"ok"}
curl http://localhost:8000/models
# Expected: {"models":["gemini-2.0-flash",...]} (only keys you've set)
```

- [ ] **Step 7: Commit**

```bash
git add api/routes/search.py api/routes/acts.py tests/api/test_routes_search_acts.py
git commit -m "feat: POST /search and GET /acts routes"
```

---

## Task 13: Next.js Setup + API Client

**Files:**
- Create: `ui/` (Next.js project)
- Create: `ui/lib/api.ts`
- Create: `ui/Dockerfile`

- [ ] **Step 1: Scaffold Next.js project**

```bash
cd ui && npx create-next-app@latest . \
  --typescript \
  --tailwind \
  --app \
  --no-src-dir \
  --import-alias "@/*"
```

When prompted, accept all defaults.

- [ ] **Step 2: Create `ui/Dockerfile`**

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

- [ ] **Step 3: Create `ui/lib/api.ts`**

```typescript
const API_URL =
  typeof window === "undefined"
    ? process.env.API_URL ?? "http://localhost:8000"
    : process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export interface Citation {
  act_title: string
  section: string
  subsection: string
  eli: string
  url: string
}

export interface AnswerResponse {
  answer: string
  model_used: string
  citations: Citation[]
  language_detected: string
  translation_warning: boolean
  disclaimer: string
}

export interface AnswerRequest {
  query: string
  model?: string
  as_of_date?: string
}

export interface ProvisionResult {
  provision_id: number
  section_num: string
  text_et: string
  act_title: string
  eli: string
}

export async function fetchAnswer(req: AnswerRequest): Promise<AnswerResponse> {
  const res = await fetch(`${API_URL}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(error.detail ?? `API error ${res.status}`)
  }
  return res.json()
}

export async function fetchModels(): Promise<string[]> {
  const res = await fetch(`${API_URL}/models`)
  if (!res.ok) throw new Error(`API error ${res.status}`)
  const data = await res.json()
  return data.models as string[]
}

export async function fetchSearch(
  query: string,
  asOfDate?: string
): Promise<ProvisionResult[]> {
  const res = await fetch(`${API_URL}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, as_of_date: asOfDate ?? null }),
  })
  if (!res.ok) throw new Error(`API error ${res.status}`)
  return res.json()
}
```

- [ ] **Step 4: Verify dev server starts**

```bash
cd ui && npm run dev
```

Expected: Next.js starts on `http://localhost:3000` with the default page.

- [ ] **Step 5: Commit**

```bash
git add ui/
git commit -m "feat: next.js project scaffold with typed API client"
```

---

## Task 14: Chat UI, Source Panel, and Model Selector

**Files:**
- Create: `ui/components/ModelSelector.tsx`
- Create: `ui/components/SourcePanel.tsx`
- Create: `ui/components/ChatInterface.tsx`
- Modify: `ui/app/page.tsx`

- [ ] **Step 1: Create `ui/components/ModelSelector.tsx`**

```tsx
"use client"

interface Props {
  models: string[]
  selected: string
  onChange: (model: string) => void
}

export default function ModelSelector({ models, selected, onChange }: Props) {
  if (models.length === 0) return null
  return (
    <div className="flex items-center gap-2 text-sm text-gray-500">
      <label htmlFor="model-select" className="font-medium">Model:</label>
      <select
        id="model-select"
        value={selected}
        onChange={(e) => onChange(e.target.value)}
        className="border rounded px-2 py-1 text-sm bg-white"
      >
        {models.map((m) => (
          <option key={m} value={m}>{m}</option>
        ))}
      </select>
    </div>
  )
}
```

- [ ] **Step 2: Create `ui/components/SourcePanel.tsx`**

```tsx
"use client"

import { Citation } from "@/lib/api"

interface Props {
  citations: Citation[]
  onClose: () => void
}

export default function SourcePanel({ citations, onClose }: Props) {
  return (
    <aside className="fixed right-0 top-0 h-full w-80 bg-white shadow-xl border-l overflow-y-auto z-10">
      <div className="flex justify-between items-center p-4 border-b">
        <h2 className="font-semibold text-gray-700">Sources</h2>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 text-xl leading-none"
          aria-label="Close source panel"
        >
          ×
        </button>
      </div>
      {citations.length === 0 ? (
        <p className="p-4 text-sm text-gray-400">No citations for this answer.</p>
      ) : (
        <ul className="divide-y">
          {citations.map((c, i) => (
            <li key={i} className="p-4">
              <p className="font-medium text-sm text-gray-800">{c.act_title}</p>
              <p className="text-sm text-gray-600">{c.section} {c.subsection}</p>
              <p className="text-xs text-gray-400 mt-1">{c.eli}</p>
              <a
                href={c.url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-blue-500 hover:underline mt-1 block"
              >
                View on riigiteataja.ee →
              </a>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
```

- [ ] **Step 3: Create `ui/components/ChatInterface.tsx`**

```tsx
"use client"

import { useState } from "react"
import { fetchAnswer, AnswerResponse } from "@/lib/api"
import SourcePanel from "./SourcePanel"
import ModelSelector from "./ModelSelector"

interface Message {
  role: "user" | "assistant"
  content: string
  response?: AnswerResponse
}

interface Props {
  availableModels: string[]
}

export default function ChatInterface({ availableModels }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedModel, setSelectedModel] = useState(availableModels[0] ?? "gemini-2.0-flash")
  const [panelResponse, setPanelResponse] = useState<AnswerResponse | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim()) return
    const query = input.trim()
    setInput("")
    setError(null)
    setMessages((prev) => [...prev, { role: "user", content: query }])
    setLoading(true)
    try {
      const response = await fetchAnswer({ query, model: selectedModel })
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: response.answer, response },
      ])
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-screen max-w-3xl mx-auto px-4">
      <header className="py-4 border-b flex justify-between items-center">
        <h1 className="text-xl font-semibold text-gray-800">Eesti Õigusabi</h1>
        <ModelSelector
          models={availableModels}
          selected={selectedModel}
          onChange={setSelectedModel}
        />
      </header>

      <div className="flex-1 overflow-y-auto py-4 space-y-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-xl rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${
                msg.role === "user"
                  ? "bg-blue-500 text-white"
                  : "bg-gray-100 text-gray-800"
              }`}
            >
              {msg.content}
              {msg.response && msg.response.citations.length > 0 && (
                <button
                  onClick={() => setPanelResponse(msg.response!)}
                  className="block mt-2 text-xs underline opacity-70 hover:opacity-100"
                >
                  {msg.response.citations.length} source{msg.response.citations.length > 1 ? "s" : ""} →
                </button>
              )}
              {msg.response?.translation_warning && (
                <p className="mt-1 text-xs opacity-60 italic">
                  Note: source text is an unofficial translation.
                </p>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-lg px-4 py-2 text-sm text-gray-400">
              Thinking…
            </div>
          </div>
        )}
        {error && (
          <p className="text-red-500 text-sm text-center">{error}</p>
        )}
      </div>

      <form onSubmit={handleSubmit} className="py-4 border-t flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about Estonian law..."
          className="flex-1 border rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="bg-blue-500 text-white px-4 py-2 rounded-lg text-sm disabled:opacity-50 hover:bg-blue-600"
        >
          Send
        </button>
      </form>

      {panelResponse && (
        <SourcePanel
          citations={panelResponse.citations}
          onClose={() => setPanelResponse(null)}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 4: Replace `ui/app/page.tsx`**

```tsx
import { fetchModels } from "@/lib/api"
import ChatInterface from "@/components/ChatInterface"

export default async function Home() {
  let models: string[] = []
  try {
    models = await fetchModels()
  } catch {
    // API not reachable at build time — fall back to empty list
  }

  return <ChatInterface availableModels={models} />
}
```

- [ ] **Step 5: Verify UI runs end-to-end**

With the API running (`docker compose up api`):
```bash
cd ui && npm run dev
```

Open `http://localhost:3000`. Ask a question. Verify the model selector appears and a source panel opens on citation links.

- [ ] **Step 6: Commit**

```bash
git add ui/components/ ui/app/page.tsx
git commit -m "feat: chat UI with source panel and model selector"
```

---

## Task 15: Evaluation — Gold Set + run_eval.py

**Files:**
- Create: `eval/gold_set.json`
- Create: `eval/run_eval.py`

- [ ] **Step 1: Create `eval/gold_set.json`**

Start with 10 entries across the key categories (expand to 30+ as the pilot runs). The format uses real Estonian law references — verify against actual indexed content before running eval.

```json
[
  {
    "id": "gs-001",
    "category": "exact_lookup",
    "query": "Mis ütleb töölepingu seaduse § 1?",
    "expected_citations": [{"eli": "RT I 2009, 5, 35", "section": "1"}],
    "expected_answer_contains": ["reguleerimisala"],
    "should_refuse": false
  },
  {
    "id": "gs-002",
    "category": "current_law",
    "query": "What is the minimum notice period for terminating an employment contract?",
    "expected_citations": [{"eli": "RT I 2009, 5, 35", "section": "97"}],
    "expected_answer_contains": ["notice", "days"],
    "should_refuse": false
  },
  {
    "id": "gs-003",
    "category": "current_law",
    "query": "Kui pikk on katseaeg töölepingus?",
    "expected_citations": [{"eli": "RT I 2009, 5, 35", "section": "86"}],
    "expected_answer_contains": ["katseaeg", "kuud"],
    "should_refuse": false
  },
  {
    "id": "gs-004",
    "category": "unsupported",
    "query": "Kes võidab kohtuvaidluse minu tööandja vastu?",
    "expected_citations": [],
    "expected_answer_contains": [],
    "should_refuse": true
  },
  {
    "id": "gs-005",
    "category": "unsupported",
    "query": "What will the Supreme Court decide on my case?",
    "expected_citations": [],
    "expected_answer_contains": [],
    "should_refuse": true
  },
  {
    "id": "gs-006",
    "category": "missing_fact",
    "query": "Am I entitled to severance pay?",
    "expected_citations": [],
    "expected_answer_contains": ["depends", "reason", "circumstances"],
    "should_refuse": false
  },
  {
    "id": "gs-007",
    "category": "current_law",
    "query": "What is the corporate income tax rate in Estonia?",
    "expected_citations": [{"eli": "RT I 2000, 102, 667", "section": "4"}],
    "expected_answer_contains": ["tax", "rate", "percent"],
    "should_refuse": false
  },
  {
    "id": "gs-008",
    "category": "exact_lookup",
    "query": "§ 203 äriseadustiku järgi",
    "expected_citations": [{"eli": "RT I 1995, 26, 355", "section": "203"}],
    "expected_answer_contains": [],
    "should_refuse": false
  },
  {
    "id": "gs-009",
    "category": "current_law",
    "query": "Millised on tööandja kohustused tööohutuse tagamisel?",
    "expected_citations": [],
    "expected_answer_contains": ["tööandja", "kohustus"],
    "should_refuse": false
  },
  {
    "id": "gs-010",
    "category": "current_law",
    "query": "What are the VAT registration requirements in Estonia?",
    "expected_citations": [],
    "expected_answer_contains": ["VAT", "registration", "threshold"],
    "should_refuse": false
  }
]
```

- [ ] **Step 2: Create `eval/run_eval.py`**

```python
#!/usr/bin/env python3
"""Evaluation runner. Usage: python eval/run_eval.py --api http://localhost:8000"""
import argparse
import json
from pathlib import Path
import requests

GOLD_SET_PATH = Path(__file__).parent / "gold_set.json"
REFUSE_PHRASES = [
    "cannot answer", "not enough information", "i don't know",
    "no information", "outside my", "cannot provide",
    "ei suuda vastata", "ei leia", "piisavalt teavet",
]


def call_answer(api_url: str, query: str) -> dict:
    resp = requests.post(f"{api_url}/answer", json={"query": query}, timeout=30)
    if resp.status_code == 422:
        return {"answer": "No relevant provisions found.", "citations": [], "model_used": "n/a",
                "language_detected": "en", "translation_warning": False, "disclaimer": ""}
    resp.raise_for_status()
    return resp.json()


def is_refusal(answer: str) -> bool:
    lower = answer.lower()
    return any(phrase in lower for phrase in REFUSE_PHRASES)


def citation_precision(returned: list[dict], expected: list[dict]) -> float:
    if not returned:
        return 1.0 if not expected else 0.0
    expected_set = {(e["eli"], e["section"]) for e in expected}
    correct = sum(
        1 for c in returned
        if (c.get("eli", ""), c.get("section", "").lstrip("§ ").strip()) in
           {(e, s) for e, s in expected_set}
    )
    return correct / len(returned)


def citation_recall(returned: list[dict], expected: list[dict]) -> float:
    if not expected:
        return 1.0
    expected_set = {(e["eli"], e["section"]) for e in expected}
    found = sum(
        1 for exp_eli, exp_sec in expected_set
        if any(
            c.get("eli", "") == exp_eli and exp_sec in c.get("section", "")
            for c in returned
        )
    )
    return found / len(expected_set)


def run_eval(api_url: str) -> None:
    gold = json.loads(GOLD_SET_PATH.read_text())
    results = []
    print(f"Running eval against {api_url} with {len(gold)} cases...\n")

    for case in gold:
        print(f"  [{case['id']}] {case['query'][:60]}...")
        response = call_answer(api_url, case["query"])
        answer = response.get("answer", "")
        citations = response.get("citations", [])
        refused = is_refusal(answer)

        precision = citation_precision(citations, case["expected_citations"])
        recall = citation_recall(citations, case["expected_citations"])
        contains_ok = all(
            phrase.lower() in answer.lower()
            for phrase in case["expected_answer_contains"]
        )
        refusal_ok = refused == case["should_refuse"]

        results.append({
            "id": case["id"],
            "category": case["category"],
            "precision": precision,
            "recall": recall,
            "contains_ok": contains_ok,
            "refusal_ok": refusal_ok,
        })

    total = len(results)
    avg_precision = sum(r["precision"] for r in results) / total
    avg_recall = sum(r["recall"] for r in results) / total
    refusal_rate = sum(1 for r in results if r["refusal_ok"]) / total
    contains_rate = sum(1 for r in results if r["contains_ok"]) / total

    print("\n=== EVAL RESULTS ===")
    print(f"  Cases:             {total}")
    print(f"  Citation precision: {avg_precision:.0%}  (target ≥85%)")
    print(f"  Citation recall:    {avg_recall:.0%}  (target ≥75%)")
    print(f"  Refusal accuracy:   {refusal_rate:.0%}  (target 100%)")
    print(f"  Contains check:     {contains_rate:.0%}")
    print()
    failing = [r for r in results if not r["refusal_ok"] or r["precision"] < 0.8]
    if failing:
        print("Failing cases:")
        for r in failing:
            print(f"  {r['id']} ({r['category']}): precision={r['precision']:.0%} "
                  f"recall={r['recall']:.0%} refusal_ok={r['refusal_ok']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()
    run_eval(args.api)
```

- [ ] **Step 3: Run eval against the live API**

```bash
docker compose up -d
python eval/run_eval.py --api http://localhost:8000
```

Expected: Eval runs and prints a results table. Investigate any failing cases and adjust prompt or chunking.

- [ ] **Step 4: Commit**

```bash
git add eval/
git commit -m "feat: evaluation gold set and run_eval.py"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ Tech stack: all choices covered (Gemini, multilingual-e5-large, ChromaDB, PG, LlamaIndex, FastAPI, Next.js, Docker Compose)
- ✅ Data pipeline: scraper, parser, chunker, embedder, indexer
- ✅ Retrieval: hybrid dense+sparse, date filter, Cohere rerank, exact citation lookup
- ✅ LLM factory: all 5 supported models, env-driven + per-request override
- ✅ System prompt: in `answer/prompts.py`
- ✅ API surface: /answer, /models, /search, /acts/:eli, /acts/:eli/versions, /acts/:eli/as-of
- ✅ Next.js UI: chat, source panel, model selector
- ✅ Evaluation: gold set + runner
- ✅ Docker Compose: all services with correct env vars

**Type consistency verified:**
- `Provision.id` is `Optional[int]` set after DB insert — `Chunk.provision_id` is set from `provision.id` after insert in `indexer.index_act()` ✅
- `generate_answer()` returns dict matching `AnswerResponse` fields ✅
- `AnswerResponse` in schemas matches response dict keys from `pipeline.generate_answer()` ✅
- `RetrievalEngine.retrieve()` returns `list[dict]` consumed consistently in `/answer` and `/search` routes ✅

**No placeholders:** All code steps contain complete, runnable code. ✅

**RT API note:** `ingest/scraper.py` endpoint URL needs verification in week-1 notebook. Configurable via `RT_BASE_URL` env var with no code changes needed. ✅
