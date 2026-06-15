---
name: test-local
description: Use when the user wants to set up and run the whole app locally for manual end-to-end testing — installs deps, configures .env, starts the db, applies migrations, ingests a sample law, and launches the API (:8000) and UI (:3000), leaving everything running.
---

# Test Local (full environment bring-up)

Takes a checkout to a running, manually-testable stack in one command: Python env,
`.env`, Postgres (pgvector) + migrations, a sample ingest, and the API + UI left
running. The work lives in `scripts/dev.py`; this skill runs it, verifies the
endpoints, and hands the user what to try by hand.

## Steps

0. **Ensure an LLM key is available in the shell environment.** Keys are read from the
   shell (export them in `~/.zshrc`), **not** from `.env`. Check:

   ```bash
   env | grep -qE '^(GEMINI|OPENAI|ANTHROPIC)_API_KEY=.' && echo "key present" || echo "no key"
   ```

   - If a key is present, continue — the API inherits it.
   - If none is present, **ask the user once** for their key (and which provider), then
     pass it inline on the run command in step 1 (env vars don't persist across separate
     shell invocations), e.g. `OPENAI_API_KEY=sk-... python3 scripts/dev.py`. Do **not**
     write the key into `.env`.

1. Bring the environment up from the repo root:

   ```bash
   python3 scripts/dev.py
   ```

   It is idempotent and safe to re-run. What it does:
   - Creates `.venv`, installs `requirements.txt`, and links the package (`pip install -e .`) — only on first run.
   - Creates `.env` from `.env.example` if missing (warns you to add an LLM key).
   - Starts the `db` container, waits until healthy, applies every `db/migrations/*.sql`.
   - Ingests the sample law `TLS` **only if the corpus is empty**, so `/search` and `/answer` return real results.
   - Starts the API (`uvicorn` on :8000) and UI (`next dev` on :3000) in the background and waits for `/health`.

   Flags:
   - `--full` — ingest the entire corpus (`--all`, **hours**) instead of the sample.
   - `--no-ingest` — leave the corpus as-is.
   - `--down` — stop the API, UI, and db container.
   - `--smoke` — run smoke tests only.

2. Verify the live endpoints (reuses the running API, won't restart it):

   ```bash
   python3 scripts/dev.py --smoke
   ```

   Read the PASS / WARN / FAIL lines:
   - **`/health` or `/models` FAIL** → app or config broken. Surface the tail of
     `/tmp/lawboi_api.log` and stop.
   - **`/search` WARN (0 hits)** or **`/answer` WARN (422)** → app works, corpus
     empty. Suggest `python -m lawboi.ingest "TLS"` (sample) or `python3 scripts/dev.py --full`.
   - **All PASS** → report the model in use and the citation count.

3. Report the result and hand the user the manual-test cheatsheet below. Do **not**
   declare success if either script exits non-zero — relay the failing check and the
   relevant log lines.

## Manual test cheatsheet

Once up, the user can test by hand:

- **UI**: open http://localhost:3000 and ask a question (e.g. *"Mis on katseaja kestus töölepingus?"*); check the source panel populates and the model selector works.
- **API docs**: http://localhost:8000/docs
- **Answer**: `curl -s -XPOST localhost:8000/answer -H 'content-type: application/json' -d '{"query":"Töölepingu seadus § 86"}' | jq .`
- **Search**: `curl -s -XPOST localhost:8000/search -H 'content-type: application/json' -d '{"query":"puhkus","limit":5}' | jq .`
- **Ingest more**: `python -m lawboi.ingest "<abbreviation or title>"` (incremental; re-runs skip unchanged acts).
- **Tear down**: `python3 scripts/dev.py --down`.

## Notes

- LLM keys come from the **shell environment** (`export OPENAI_API_KEY=...` in
  `~/.zshrc`), not `.env` — the app calls `load_dotenv()` without override, so exported
  vars win. `.env` only holds non-secret config (`DATABASE_URL`, etc.). Without any key
  exported, `/search` & `/answer` 503 while the rest still comes up. Leave `LLM_MODEL`
  unset to auto-select the first provider whose key is exported.
- Colima is the Docker runtime here — if Docker is unreachable, `colima start`.
- Logs: API → `/tmp/lawboi_api.log`, UI → `/tmp/lawboi_ui.log`. The `db` volume and
  ingested data persist between runs.
- Servers are left running on purpose (for manual testing) and are **not** killed on
  script exit — always stop them with `python3 scripts/dev.py --down`.
