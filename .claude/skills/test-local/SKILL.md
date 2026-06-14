---
name: test-local
description: Use when the user wants to test the running app locally end-to-end — spins up the db + API and runs full-stack smoke checks (/health, /models, /search, /answer) in one command.
---

# Test Local (full-stack smoke)

Brings up the local stack and exercises the live API in one go. The actual work
lives in `scripts/smoke_local.sh`; this skill runs it and interprets the result.

## Steps

1. Run the smoke script from the repo root:

   ```bash
   ./scripts/smoke_local.sh
   ```

   - It checks Docker/Colima is up, starts the `db` container and waits until
     healthy, then reuses an API already on `http://localhost:8000` or starts
     `uvicorn` itself (first run loads the e5 model, ~30s).
   - Pass `--down` to also stop the `db` container at the end:
     `./scripts/smoke_local.sh --down`.

2. Read the PASS / WARN / FAIL lines and report the outcome:
   - **`/health` or `/models` FAIL** → the app or its config is broken. Surface
     the tail of `/tmp/lawboi_api.log` and stop.
   - **`/search` WARN (0 hits)** or **`/answer` WARN (422)** → the app works but
     the corpus isn't ingested. Tell the user to run `python -m lawboi.ingest --all`
     (or a single law, e.g. `python -m lawboi.ingest "TLS"`).
   - **All PASS** → report the model in use and a sample citation count.

3. If the script exits non-zero, do **not** declare success — relay the failing
   check and the relevant log lines.

## Notes

- Needs `.env` with `DATABASE_URL` and at least one LLM key (`GEMINI_API_KEY` /
  `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`); without a key, `/answer` will FAIL while
  the rest still smoke-tests.
- Colima is the Docker runtime here — if Docker is unreachable, `colima start`.
- The script is safe to re-run; the `db` volume persists between runs.
