"""Probe the real Riigi Teataja API to verify the endpoints the ingest code assumes.

Read-only. Makes a handful of GET requests to riigiteataja.ee and reports what
actually comes back, so we can decide:
  1. Does the search endpoint work, and does a result carry a STABLE act-level id
     (distinct from the per-redaktsioon globaalID) and any change signal
     (hash / modified timestamp) we could diff against?
  2. Does it paginate the full corpus (total count / page fields)?
  3. Does the act-XML fetch work, and what is its root element / namespaces / tags?

Usage:
    python scripts/probe_rt.py            # defaults to query "TLS"
    python scripts/probe_rt.py põhiseadus
"""
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter

import requests

BASE = "https://www.riigiteataja.ee"
SEARCH_URL = f"{BASE}/api/oigusakt_otsing/1/otsi"
TIMEOUT = 15


def rule(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def show_response(resp: requests.Response) -> None:
    print(f"  GET {resp.url}")
    print(f"  -> {resp.status_code} {resp.reason}  "
          f"content-type={resp.headers.get('content-type', '?')}  "
          f"bytes={len(resp.content)}")


def probe_search(query: str) -> list[dict]:
    rule(f"1. SEARCH  query={query!r}")
    # Mirror the params the existing client sends (riigiteataja_client.search_acts).
    params = {
        "leht": 1, "limiit": 5, "dokument": "seadus",
        "kehtivKehtetus": "false", "mitteJoustunud": "false", "lyhend": query,
    }
    try:
        resp = requests.get(SEARCH_URL, params=params, timeout=TIMEOUT)
    except Exception as e:
        print(f"  REQUEST FAILED: {type(e).__name__}: {e}")
        return []
    show_response(resp)
    if resp.status_code != 200:
        print("  Body (first 800 chars):")
        print("  " + resp.text[:800].replace("\n", "\n  "))
        return []
    try:
        data = resp.json()
    except Exception as e:
        print(f"  NOT JSON: {e}")
        print("  " + resp.text[:800].replace("\n", "\n  "))
        return []

    print(f"  Top-level keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
    # Look for total-count / pagination hints anywhere at the top level.
    if isinstance(data, dict):
        for k, v in data.items():
            if not isinstance(v, (list, dict)):
                print(f"    {k!r}: {v!r}")
        if isinstance(data.get("metaandmed"), dict):
            print(f"  metaandmed (pagination/total?): "
                  f"{json.dumps(data['metaandmed'], ensure_ascii=False)}")

    acts = data.get("aktid", []) if isinstance(data, dict) else []
    print(f"  len(aktid) = {len(acts)}")
    if acts:
        first = acts[0]
        print("  --- first act: all keys -> value (truncated) ---")
        for k, v in first.items():
            sval = json.dumps(v, ensure_ascii=False)
            print(f"    {k!r}: {sval[:160]}")
        print("  --- fields that look like a STABLE id / change signal ---")
        for k in first:
            kl = k.lower()
            if any(t in kl for t in ("id", "hash", "aeg", "muut", "redakt", "versioon", "eli", "akti")):
                print(f"    candidate: {k!r} = {json.dumps(first[k], ensure_ascii=False)[:120]}")
    return acts


def probe_pagination(query: str) -> None:
    rule("2. PAGINATION  (can we enumerate the full corpus?)")
    # Empty query — does the API list everything, or require a search term?
    for label, extra in [("no query term", {}), ("wildcard '*'", {"lyhend": "*"})]:
        params = {"leht": 1, "limiit": 1, "dokument": "seadus",
                  "kehtivKehtetus": "false", "mitteJoustunud": "false", **extra}
        try:
            resp = requests.get(SEARCH_URL, params=params, timeout=TIMEOUT)
            data = resp.json() if resp.status_code == 200 else {}
        except Exception as e:
            print(f"  [{label}] FAILED: {type(e).__name__}: {e}")
            continue
        total_keys = {k: v for k, v in (data.items() if isinstance(data, dict) else [])
                      if not isinstance(v, (list, dict))}
        n = len(data.get("aktid", [])) if isinstance(data, dict) else 0
        print(f"  [{label}] {resp.status_code}  scalar/meta fields={total_keys}  aktid_on_page={n}")


def probe_fetch(acts: list[dict]) -> None:
    rule("3. FETCH ACT XML")
    if not acts:
        print("  No acts from search — cannot pick an id to fetch. Skipping.")
        return
    first = acts[0]
    gid = first.get("globaalID")
    ttid = first.get("terviktekstID")
    # The `/akt/<gid>.xml` route returns the SPA HTML shell, so hunt for the real
    # content API the SPA must call. Try a battery and flag anything non-HTML.
    candidates = [
        f"{BASE}/public-api/api/v1/akt/{gid}/blob-xml",   # discovered in the SPA bundle
        f"{BASE}/public-api/api/v1/akt/{gid}/blob-html",
        f"{BASE}/public-api/api/v1/en/akt/{gid}/blob-xml",
    ]
    print(f"  globaalID={gid}  terviktekstID={ttid}")
    found = None
    for url in candidates:
        headers = {"Accept": "application/xml, application/json, text/xml"}
        try:
            resp = requests.get(url, headers=headers, timeout=30)
        except Exception as e:
            print(f"  {url}\n      FAILED: {type(e).__name__}: {e}")
            continue
        ct = resp.headers.get("content-type", "?")
        flag = "  <-- NON-HTML!" if resp.status_code == 200 and "html" not in ct else ""
        print(f"  [{resp.status_code}] {ct:40s} {len(resp.content):>8d}b  {url}{flag}")
        if resp.status_code == 200 and "html" not in ct and found is None:
            found = resp
    if found is None:
        print("  No content endpoint returned non-HTML. The SPA likely calls an")
        print("  endpoint we haven't guessed — next step is to capture its XHR.")
        return
    rule("3b. PARSE the content endpoint that worked")
    show_response(found)
    body = found.content
    if "json" in found.headers.get("content-type", ""):
        try:
            data = found.json()
            print("  JSON keys: " + str(list(data.keys()) if isinstance(data, dict) else type(data)))
            print("  " + json.dumps(data, ensure_ascii=False)[:1200])
        except Exception as e:
            print(f"  JSON parse failed: {e}")
        return
    try:
        root = ET.fromstring(body)
    except Exception as e:
        print(f"  Not parseable XML ({e}). First 400 chars:")
        print("  " + body[:400].decode("utf-8", "replace").replace("\n", "\n  "))
        return
    tags = Counter(el.tag for el in root.iter())
    print(f"  XML root tag: {root.tag!r}")
    ns = sorted({t.split('}')[0].strip('{') for t in tags if t.startswith('{')})
    print(f"  Namespaces: {ns or '(none)'}")
    print("  Most common tags (local name -> count):")
    for tag, c in tags.most_common(25):
        print(f"    {tag.split('}')[-1]!r}: {c}")


def probe_spa_api(acts: list[dict]) -> None:
    """Discover the real content API by grepping the SPA's JS bundles for /api/ URLs."""
    import re
    rule("4. DISCOVER content API from SPA JS bundles")
    gid = acts[0].get("globaalID") if acts else 111012023013
    shell_url = f"{BASE}/akt/{gid}.xml"
    try:
        html = requests.get(shell_url, timeout=TIMEOUT).text
    except Exception as e:
        print(f"  shell fetch failed: {e}")
        return
    scripts = re.findall(r'src="([^"]+\.js)"', html)
    print(f"  SPA shell references {len(scripts)} script(s): {scripts}")
    api_pat = re.compile(r'["\'`](/?api/[A-Za-z0-9_./{}$:-]+)')
    seen: set[str] = set()
    for s in scripts:
        url = s if s.startswith("http") else f"{BASE}/{s.lstrip('/')}"
        try:
            js = requests.get(url, timeout=TIMEOUT).text
        except Exception as e:
            print(f"  [skip] {url}: {e}")
            continue
        for m in api_pat.findall(js):
            seen.add(m)
    print("  Distinct /api/ path fragments found in JS:")
    for frag in sorted(seen):
        print(f"    {frag}")
    if not seen:
        print("    (no literal /api/ strings — URLs are built dynamically)")

    # Runtime config (API base) often lives in assets/env.js.
    try:
        env = requests.get(f"{BASE}/assets/env.js", timeout=TIMEOUT).text
        print("  --- assets/env.js (first 1000 chars) ---")
        print("  " + env[:1000].replace("\n", "\n  "))
    except Exception as e:
        print(f"  env.js fetch failed: {e}")

    # Extract full URL path templates (incl. /public-api/...) from the main bundle.
    main_js = next((s for s in scripts if "main" in s), None)
    if main_js:
        url = main_js if main_js.startswith("http") else f"{BASE}/{main_js.lstrip('/')}"
        js = requests.get(url, timeout=TIMEOUT).text
        url_pat = re.compile(r'(/(?:public-api/)?api/v?\d*/?[A-Za-z0-9_./${}-]+)')
        paths = sorted(set(url_pat.findall(js)))
        print("  --- URL path templates found in main.js ---")
        for p in paths:
            print(f"    {p}")
        for tok in ("sisu", "terviktekst", "oigusakt"):
            for m in re.finditer(re.escape(tok), js):
                seg = js[max(0, m.start() - 70):m.start() + 30]
                if "/" in seg and ("api" in seg or "${" in seg or "`" in seg):
                    print(f"  ctx {tok!r}: …{seg.replace(chr(10), ' ')}…")
                    break


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "TLS"
    print(f"Probing {BASE}  (search={SEARCH_URL})")
    acts = probe_search(query)
    probe_pagination(query)
    probe_fetch(acts)
    probe_spa_api(acts)
    print("\nDone.")


if __name__ == "__main__":
    main()
