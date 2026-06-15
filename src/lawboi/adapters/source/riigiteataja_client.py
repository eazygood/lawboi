import hashlib
import os
import time
from pathlib import Path
from typing import Iterable, Iterator

import requests

RT_BASE_URL = os.getenv("RT_BASE_URL", "https://www.riigiteataja.ee")
RAW_DATA_DIR = Path(os.getenv("RAW_DATA_DIR", "data/raw"))
REQUEST_DELAY = 1.0
_SEARCH_URL = f"{RT_BASE_URL}/api/oigusakt_otsing/1/otsi"

# Document types crawled by the full-corpus ingest. määrus (~91k version-rows,
# mostly off-domain for accountants) is intentionally excluded for now — adding
# it later is a one-element change here.
CORPUS_DOC_TYPES = ("seadus", "määrus")


def compute_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def search_acts(query: str, limit: int = 10, effective_date: str = "") -> list[dict]:
    """Search for acts by title or abbreviation. Returns list of act metadata dicts."""
    params: dict = {
        "leht": 1,
        "limiit": limit,
        "dokument": "seadus",
        "kehtivKehtetus": "false",
        "mitteJoustunud": "false",
    }
    if effective_date:
        params["kehtiv"] = effective_date

    # Try abbreviation first, fall back to title substring
    resp = requests.get(_SEARCH_URL, params={**params, "lyhend": query}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    acts = data.get("aktid", [])

    if not acts:
        resp = requests.get(_SEARCH_URL, params={**params, "pealkiri": query}, timeout=10)
        resp.raise_for_status()
        acts = resp.json().get("aktid", [])

    return acts


def fetch_act_xml(global_id) -> tuple[bytes, str]:
    """Fetch consolidated act XML by globaalID via the public content API.

    Returns (xml_bytes, source_url). The endpoint serves the act as
    Content-Type application/xml (root <oigusakt>), not the SPA HTML shell.
    """
    url = f"{RT_BASE_URL}/public-api/api/v1/akt/{global_id}/blob-xml"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return resp.content, url


def iter_corpus(
    doc_types: Iterable[str] = CORPUS_DOC_TYPES,
    page_size: int = 200,
    effective_date: str = "",
) -> Iterator[dict]:
    """Yield every act-version row for each document type, paginating the full
    result set (leht/limiit up to metaandmed.kokku). Politeness-delayed between
    pages. Rows include multiple redaktsioonid per act — the caller dedups by
    terviktekstID.
    """
    for doc in doc_types:
        leht = 1
        seen = 0
        while True:
            params: dict = {
                "leht": leht,
                "limiit": page_size,
                "dokument": doc,
                "kehtivKehtetus": "false",
                "mitteJoustunud": "false",
            }
            if effective_date:
                params["kehtiv"] = effective_date
            resp = requests.get(_SEARCH_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("aktid", [])
            if not rows:
                break
            yield from rows
            seen += len(rows)
            total = data.get("metaandmed", {}).get("kokku", 0)
            if seen >= total:
                break
            leht += 1
            time.sleep(REQUEST_DELAY)


def store_raw(global_id: int, content: bytes, raw_dir: Path = RAW_DATA_DIR) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{global_id}.xml"
    path.write_bytes(content)
    return path


def has_changed(known_hash: str, content: bytes) -> bool:
    return compute_hash(content) != known_hash
