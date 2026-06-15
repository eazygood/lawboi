# Design: Rewrite dev scripts to unified Python script

**Date:** 2026-06-15
**Scope:** Replace `scripts/dev_local.sh` and `scripts/smoke_local.sh` with a single `scripts/dev.py`

## Problem

Two bash scripts manage the local dev environment. Bash is harder to read, test, and maintain than Python, and the project already uses inline Python inside `smoke_local.sh` for HTTP checks. Since the `test-local` Claude skill drives these scripts via Bash tool calls and parses their output, predictability and clean output format are critical.

## Solution

One unified Python script (`scripts/dev.py`) with flag-based interface, pure stdlib, same output contract as the current bash scripts.

## Interface

```
python scripts/dev.py              # bring up full stack (venv, db, migrations, ingest sample, API, UI)
python scripts/dev.py --full       # up with full corpus ingest instead of sample
python scripts/dev.py --no-ingest  # up, skip ingest
python scripts/dev.py --smoke      # run endpoint smoke checks against running API
python scripts/dev.py --down       # stop API, UI, db container
```

Flags parsed via `argparse`. Mutually exclusive group: `--full` and `--no-ingest` cannot be combined.

## Architecture

Single file `scripts/dev.py`, ~250 lines. Logically grouped by concern:

| Section | Responsibility |
|---|---|
| `helpers` | `run()`, `check_output()`, `info/ok/warn/die()` output functions |
| `docker` | `compose_up_db()`, `wait_healthy()`, `apply_migrations()` |
| `python_env` | `ensure_venv()`, `ensure_deps()`, `ensure_package()` |
| `ingest` | `ensure_ingest()` — skip if provisions exist, sample or full |
| `servers` | `start_api()`, `start_ui()`, `wait_for_url()`, `stop_all()` |
| `smoke` | `run_smoke()` — HTTP checks with PASS/FAIL/WARN output |
| `main()` | argparse dispatch |

## Output Contract

The Claude `test-local` skill reads specific output patterns. These must be preserved exactly:

- `PASS  <message>` — green, check succeeded
- `FAIL  <message>` — red, hard failure; script exits 1
- `WARN  <message>` — yellow, soft issue (empty corpus, missing optional key)
- `==>   <message>` — dim, progress info

ANSI codes only when stdout is a TTY (`sys.stdout.isatty()`), same as current scripts.

Exit codes: 0 on success, 1 on any FAIL. No interactive prompts.

## Key Behaviors

**Idempotent `up`:** Reuses a running API/UI (checks `/health` first), skips ingest if `provision` table has rows.

**LLM key check:** Shell-exported value wins over `.env` — mirrors `load_dotenv()` no-override behavior. Check all three providers; warn if none found (don't abort — `/health` and `/models` still smoke-test without a key).

**Subprocess strategy:** `subprocess.run(..., check=True)` for commands that must succeed; `subprocess.run(..., check=False)` with manual return-code inspection for commands with expected non-zero exits (e.g. `docker inspect` when container is starting).

**Pidfiles:** `/tmp/lawboi_api.pid`, `/tmp/lawboi_ui.pid` — same paths as current bash scripts so `--down` works across invocations.

**Logs:** API → `/tmp/lawboi_api.log`, UI → `/tmp/lawboi_ui.log` — same paths.

**Migration:** `db/migrations/*.sql` applied in filename order via `psql` through `docker compose exec -T db`.

**Python bootstrapping:** Script can run with system `python3` before the venv exists — venv creation and dep install happen inside `ensure_venv()` / `ensure_deps()` before anything else in `up`.

## Smoke tests (`--smoke`)

Runs four endpoint checks against `http://localhost:8000` (or `$API_URL`):

1. `GET /health` — must be `{"status": "ok"}` → PASS or FAIL
2. `GET /models` — must return `≥1` model → PASS or FAIL
3. `POST /search` — 200 + hits → PASS; 200 + empty → WARN; else FAIL
4. `POST /answer` — 200 → PASS; 422 (no sources) → WARN; else FAIL

Exit 1 if any FAIL. Identical logic to the inline Python block in current `smoke_local.sh`.

`--smoke` does NOT start or stop the db or API — it checks only. This is the expected usage from the skill: `up` brings the stack up, `--smoke` verifies it.

## Files Changed

| Action | Path |
|---|---|
| Create | `scripts/dev.py` |
| Delete | `scripts/dev_local.sh` |
| Delete | `scripts/smoke_local.sh` |
| Update | `.claude/skills/test-local/SKILL.md` — replace script references |

## What Is Not Changed

- `.env` structure and key sourcing behavior
- Pidfile paths, log paths
- Docker Compose service names (`db`)
- Migration file location (`db/migrations/*.sql`)
- Output line format read by the skill
