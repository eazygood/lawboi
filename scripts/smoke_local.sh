#!/usr/bin/env bash
#
# Full-stack local smoke test: bring up the db + API and exercise the live
# endpoints (/health, /models, /search, /answer) end-to-end, in one go.
#
#   ./scripts/smoke_local.sh            # start db + API, smoke, tear our API down
#   ./scripts/smoke_local.sh --down     # also stop the db container at the end
#
# Reuses an API already listening on $API_URL instead of starting its own.
# Hard-fails on /health and /models; treats empty /search or 422 /answer as a
# WARN (the app works, the corpus just isn't ingested yet).
set -euo pipefail
cd "$(dirname "$0")/.."

API_URL="${API_URL:-http://localhost:8000}"
PORT="${PORT:-8000}"
PY=.venv/bin/python
UVICORN=.venv/bin/uvicorn
API_LOG=/tmp/lawboi_api.log
DOWN=0
[ "${1:-}" = "--down" ] && DOWN=1

if [ -t 1 ]; then RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; DIM=$'\033[2m'; NC=$'\033[0m'
else RED=; GRN=; YEL=; DIM=; NC=; fi
info() { printf '%s==>%s %s\n' "$DIM" "$NC" "$*"; }
ok()   { printf '%s PASS %s %s\n' "$GRN" "$NC" "$*"; }
warn() { printf '%s WARN %s %s\n' "$YEL" "$NC" "$*"; }
die()  { printf '%s FAIL %s %s\n' "$RED" "$NC" "$*" >&2; exit 1; }

# --- compose flavor -----------------------------------------------------------
if docker compose version >/dev/null 2>&1; then DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then DC=(docker-compose)
else die "Neither 'docker compose' nor 'docker-compose' found."; fi

# --- preflight ----------------------------------------------------------------
docker info >/dev/null 2>&1 || die "Docker daemon unreachable. Using Colima? Run: colima start"
[ -f .env ] || die ".env missing. Copy .env.example and set DATABASE_URL + an LLM key."
[ -x "$UVICORN" ] || die ".venv/bin/uvicorn missing. Run: python -m venv .venv && .venv/bin/pip install -r requirements.txt"

# LLM key check. If LLM_MODEL is pinned, the *matching* provider key must be set;
# otherwise the factory auto-selects among whichever provider keys are present.
env_val() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '"'"'"' '; }
has_key()  { [ -n "$(env_val "$1")" ]; }
pinned=$(env_val LLM_MODEL)
case "$pinned" in
  gemini*)            has_key GEMINI_API_KEY    || warn "LLM_MODEL=$pinned but GEMINI_API_KEY is empty — /search & /answer will 503. Set the key or pin an OpenAI/Anthropic model.";;
  gpt*|o1*|o3*|o4*)   has_key OPENAI_API_KEY    || warn "LLM_MODEL=$pinned but OPENAI_API_KEY is empty — /search & /answer will 503.";;
  claude*)            has_key ANTHROPIC_API_KEY || warn "LLM_MODEL=$pinned but ANTHROPIC_API_KEY is empty — /search & /answer will 503.";;
  "") grep -qE '^(GEMINI|OPENAI|ANTHROPIC)_API_KEY=.+' .env \
        || warn "No LLM API key set in .env — /search & /answer will 503 (the rest still smoke-tests).";;
esac

# --- db -----------------------------------------------------------------------
info "Starting db container..."
"${DC[@]}" up -d db
status=starting
for _ in $(seq 1 30); do
  cid=$("${DC[@]}" ps -q db || true)
  [ -n "$cid" ] && status=$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo starting)
  [ "$status" = healthy ] && break
  sleep 2
done
[ "$status" = healthy ] || { "${DC[@]}" logs --tail 20 db || true; die "db did not become healthy."; }
ok "db healthy"

# --- API (reuse if already running, else start uvicorn) -----------------------
STARTED_API=0
cleanup() { [ "$STARTED_API" = 1 ] && kill "$API_PID" 2>/dev/null || true
            [ "$DOWN" = 1 ] && "${DC[@]}" stop db >/dev/null 2>&1 || true; }
trap cleanup EXIT

if curl -sf "$API_URL/health" >/dev/null 2>&1; then
  info "API already up at $API_URL — reusing it."
else
  info "Starting API (uvicorn on :$PORT)... logs -> $API_LOG"
  PYTHONPATH=src "$UVICORN" lawboi.api.main:app --port "$PORT" >"$API_LOG" 2>&1 &
  API_PID=$!
  STARTED_API=1
fi

info "Waiting for /health (first run loads the e5 model, ~30s)..."
up=0
for _ in $(seq 1 90); do
  curl -sf "$API_URL/health" >/dev/null 2>&1 && { up=1; break; }
  if [ "$STARTED_API" = 1 ] && ! kill -0 "$API_PID" 2>/dev/null; then
    tail -30 "$API_LOG" >&2; die "API process exited during startup."
  fi
  sleep 2
done
[ "$up" = 1 ] || { [ "$STARTED_API" = 1 ] && tail -30 "$API_LOG" >&2; die "/health never came up."; }

# --- endpoint checks ----------------------------------------------------------
info "Running endpoint smoke checks against $API_URL"
"$PY" - "$API_URL" <<'PY'
import json, sys, urllib.error, urllib.request

base = sys.argv[1]
RED, GRN, YEL, NC = "\033[31m", "\033[32m", "\033[33m", "\033[0m"
fails = 0

def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    hdr = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(base + path, data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        try:    payload = json.loads(e.read() or "null")
        except Exception: payload = None
        return e.code, payload

def line(tag, color, msg):
    print(f"{color} {tag} {NC} {msg}")

def pas(m): line("PASS", GRN, m)
def war(m): line("WARN", YEL, m)
def bad(m):
    global fails; fails += 1; line("FAIL", RED, m)

# 1. /health
st, body = _req("GET", "/health")
pas("/health ok") if st == 200 and body == {"status": "ok"} else bad(f"/health -> {st} {body}")

# 2. /models
st, body = _req("GET", "/models")
models = (body or {}).get("models") if isinstance(body, dict) else None
if st == 200 and models:
    pas(f"/models -> {len(models)} model(s): {', '.join(map(str, models))}")
else:
    bad(f"/models -> {st} {body}")

# 3. /search  (empty result = corpus not ingested, not a failure)
st, body = _req("POST", "/search", {"query": "töölepingu ülesütlemine", "limit": 5})
if st == 200 and isinstance(body, list) and body:
    top = body[0]
    pas(f"/search -> {len(body)} hit(s); top: {top.get('act_title','?')} {top.get('section_num','?')}")
elif st == 200 and body == []:
    war("/search -> 200 but 0 hits (corpus not ingested? run: python -m lawboi.ingest --all)")
else:
    bad(f"/search -> {st} {body}")

# 4. /answer  (422 = no sources found, expected on an empty corpus)
st, body = _req("POST", "/answer",
                {"query": "Kui pikk on töölepingu ülesütlemise etteteatamise tähtaeg?"})
if st == 200 and isinstance(body, dict):
    cites = body.get("citations", [])
    pas(f"/answer -> 200, model={body.get('model_used','?')}, {len(cites)} citation(s)")
elif st == 422:
    war("/answer -> 422 NoSourcesFound (expected with no ingested data; the gate works)")
else:
    bad(f"/answer -> {st} {body}")

print()
if fails:
    print(f"{RED}{fails} check(s) failed.{NC}"); sys.exit(1)
print(f"{GRN}All hard checks passed.{NC}")
PY

ok "Smoke complete."
[ "$DOWN" = 0 ] && info "db left running. Stop it with: ${DC[*]} stop db"
