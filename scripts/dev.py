#!/usr/bin/env python3
"""
Manage the local lawboi dev environment.

  python scripts/dev.py              # bring up full stack (venv, db, migrations, sample ingest, API, UI)
  python scripts/dev.py --full       # full corpus ingest instead of sample (hours)
  python scripts/dev.py --no-ingest  # skip ingest
  python scripts/dev.py --smoke      # run endpoint smoke checks against running API
  python scripts/dev.py --down       # stop API, UI, and db container
"""
import argparse
import glob
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
API_URL = os.environ.get("API_URL", "http://localhost:8000")
UI_URL = os.environ.get("UI_URL", "http://localhost:3000")
PORT = os.environ.get("PORT", "8000")
SAMPLE_LAW = os.environ.get("SAMPLE_LAW", "TLS")
API_LOG = Path("/tmp/lawboi_api.log")
UI_LOG = Path("/tmp/lawboi_ui.log")
API_PIDF = Path("/tmp/lawboi_api.pid")
UI_PIDF = Path("/tmp/lawboi_ui.pid")
PY = ROOT / ".venv/bin/python"
PIP = ROOT / ".venv/bin/pip"
UVICORN = ROOT / ".venv/bin/uvicorn"

# ANSI colors — only when writing to a real terminal
if sys.stdout.isatty():
    RED = "\033[31m"; GRN = "\033[32m"; YEL = "\033[33m"; DIM = "\033[2m"; NC = "\033[0m"
else:
    RED = GRN = YEL = DIM = NC = ""

def info(msg): print(f"{DIM}==>{NC} {msg}", flush=True)
def ok(msg):   print(f"{GRN} PASS {NC} {msg}", flush=True)
def warn(msg): print(f"{YEL} WARN {NC} {msg}", flush=True)
def die(msg):  print(f"{RED} FAIL {NC} {msg}", flush=True); sys.exit(1)


# ---------------------------------------------------------------------------
# subprocess helpers
# ---------------------------------------------------------------------------

def run(cmd, **kw):
    """Run a command from ROOT; raise on non-zero exit."""
    return subprocess.run(cmd, check=True, cwd=ROOT, **kw)


def run_q(cmd, **kw):
    """Run a command, capture all output, never raise."""
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def _detect_compose():
    if run_q(["docker", "compose", "version"]).returncode == 0:
        return ["docker", "compose"]
    if run_q(["docker-compose", "version"]).returncode == 0:
        return ["docker-compose"]
    die("Neither 'docker compose' nor 'docker-compose' found.")


# ---------------------------------------------------------------------------
# .env helpers — mirrors load_dotenv() no-override behaviour
# ---------------------------------------------------------------------------

def _env_file_val(key):
    """Read a key from .env (strips quotes). Returns '' if not found."""
    env_path = ROOT / ".env"
    try:
        for line in env_path.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line[len(key) + 1:].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return ""


def val(key):
    """Shell-exported value wins; fall back to .env."""
    s = os.environ.get(key, "")
    return s if s else _env_file_val(key)


def have_llm_key():
    return any(val(k) for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"))


def check_llm_key():
    pinned = val("LLM_MODEL")
    if pinned.startswith("gemini"):
        if not val("GEMINI_API_KEY"):
            warn(f"LLM_MODEL={pinned} but GEMINI_API_KEY is empty — /search & /answer will 503.")
    elif pinned.startswith(("gpt", "o1", "o3", "o4")):
        if not val("OPENAI_API_KEY"):
            warn(f"LLM_MODEL={pinned} but OPENAI_API_KEY is empty — /search & /answer will 503.")
    elif pinned.startswith("claude"):
        if not val("ANTHROPIC_API_KEY"):
            warn(f"LLM_MODEL={pinned} but ANTHROPIC_API_KEY is empty — /search & /answer will 503.")
    else:
        if not have_llm_key():
            warn("No LLM API key set (.env or shell env) — /search & /answer will 503 (the rest still smoke-tests).")


# ---------------------------------------------------------------------------
# Docker / db
# ---------------------------------------------------------------------------

def compose_up_db(dc):
    run(dc + ["up", "-d", "db"])


def wait_healthy(dc, timeout=60):
    for _ in range(timeout // 2):
        cid = run_q(dc + ["ps", "-q", "db"]).stdout.strip()
        if cid:
            status = run_q(
                ["docker", "inspect", "-f", "{{.State.Health.Status}}", cid]
            ).stdout.strip()
            if status == "healthy":
                return
        time.sleep(2)
    run_q(dc + ["logs", "--tail", "20", "db"])
    die("db did not become healthy.")


def apply_migrations(dc):
    migration_files = sorted(glob.glob(str(ROOT / "db/migrations/*.sql")))
    for f in migration_files:
        info(f"Applying migration {Path(f).name}...")
        sql = Path(f).read_bytes()
        run(dc + ["exec", "-T", "db", "psql", "-U", "lawboi", "-d", "lawboi", "-q"],
            input=sql)
    if migration_files:
        ok("migrations applied")


# ---------------------------------------------------------------------------
# Python environment
# ---------------------------------------------------------------------------

def ensure_venv():
    if not PY.exists():
        info("Creating virtualenv (.venv)...")
        run(["python3", "-m", "venv", ".venv"])


def ensure_deps():
    if not UVICORN.exists():
        info("Installing requirements (first run, slow)...")
        run([str(PIP), "install", "-q", "-r", "requirements.txt"])


def ensure_package():
    if run_q([str(PY), "-c", "import lawboi"]).returncode != 0:
        info("Linking the lawboi package (pip install -e .)...")
        run([str(PIP), "install", "-q", "-e", ".", "--no-deps"])


def ensure_dotenv():
    env_path = ROOT / ".env"
    if not env_path.exists():
        run(["cp", ".env.example", ".env"])
        warn(".env created from .env.example — set an LLM key (in .env or your shell rc) before /search & /answer work.")


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def _provision_count(dc):
    r = run_q(dc + ["exec", "-T", "db", "psql", "-U", "lawboi", "-d", "lawboi",
                    "-tAc", "SELECT count(*) FROM provision"])
    try:
        return int(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0


def ensure_ingest(dc, mode):
    """mode: 'sample' | 'full' | 'none'"""
    count = _provision_count(dc)
    if mode == "none":
        info(f"Skipping ingest (--no-ingest). Provisions in db: {count}.")
        return
    if mode == "full":
        info("Ingesting the FULL corpus (--all). This takes hours; leave it running.")
        run([str(PY), "-m", "lawboi.ingest", "--all"])
        return
    # sample
    if count > 0:
        info(f"db already has {count} provisions — skipping sample ingest. (--full re-crawls everything.)")
    else:
        info(f"Ingesting sample law '{SAMPLE_LAW}' so /search & /answer return real results...")
        r = subprocess.run([str(PY), "-m", "lawboi.ingest", SAMPLE_LAW], cwd=ROOT)
        if r.returncode != 0:
            warn("sample ingest failed (LLM/RT/network?) — API still starts.")


# ---------------------------------------------------------------------------
# Server management
# ---------------------------------------------------------------------------

def _pid_running(pidf):
    """Return PID if process is alive, else None."""
    if pidf.exists():
        try:
            pid = int(pidf.read_text().strip())
            os.kill(pid, 0)
            return pid
        except (ValueError, ProcessLookupError, PermissionError):
            pidf.unlink(missing_ok=True)
    return None


def _stop_pid(pidf, label):
    pid = _pid_running(pidf)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            info(f"stopped {label}")
        except ProcessLookupError:
            pass
    pidf.unlink(missing_ok=True)


def stop_all(dc):
    _stop_pid(UI_PIDF, "UI")
    _stop_pid(API_PIDF, "API")
    subprocess.run(dc + ["stop", "db"], capture_output=True, cwd=ROOT)
    ok("Environment stopped.")


def _check_url(url):
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
    except Exception:
        return False


def _wait_for_url(url, timeout=180):
    for _ in range(timeout // 2):
        if _check_url(url):
            return True
        time.sleep(2)
    return False


def start_api():
    if _check_url(f"{API_URL}/health"):
        info(f"API already up at {API_URL} — reusing it.")
        return
    info(f"Starting API (uvicorn :{PORT}) -> {API_LOG}")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    with open(API_LOG, "w") as log:
        p = subprocess.Popen(
            [str(UVICORN), "lawboi.api.main:app", "--port", PORT],
            cwd=ROOT, env=env, stdout=log, stderr=log,
            start_new_session=True,
        )
    API_PIDF.write_text(str(p.pid))
    info("Waiting for /health (first run loads the e5 model, ~30s)...")
    if not _wait_for_url(f"{API_URL}/health"):
        try:
            lines = API_LOG.read_text().splitlines()[-30:]
            print("\n".join(lines), file=sys.stderr)
        except Exception:
            pass
        die("/health never came up.")
    ok(f"API healthy at {API_URL}")


def start_ui():
    if not (ROOT / "ui/package.json").exists():
        return
    if _check_url(UI_URL):
        info(f"UI already up at {UI_URL} — reusing it.")
        return
    if subprocess.run(["which", "npm"], capture_output=True).returncode != 0:
        warn("npm not found — skipping UI. Start it manually: cd ui && nvm use && npm install && npm run dev")
        return
    if not (ROOT / "ui/node_modules").exists():
        info("Installing UI deps (npm install)...")
        subprocess.run(["npm", "install", "--silent"], cwd=ROOT / "ui", check=True)
    info(f"Starting UI (next dev :3000) -> {UI_LOG}")
    with open(UI_LOG, "w") as log:
        p = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=ROOT / "ui", stdout=log, stderr=log,
            start_new_session=True,
        )
    UI_PIDF.write_text(str(p.pid))
    if _wait_for_url(UI_URL, timeout=60):
        ok(f"UI up at {UI_URL}")
    else:
        warn(f"UI not responding yet — check {UI_LOG}")


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(API_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read() or "null")
        except Exception:
            payload = None
        return e.code, payload


def run_smoke():
    fails = 0

    def pas(m): print(f"{GRN} PASS {NC} {m}", flush=True)
    def war(m): print(f"{YEL} WARN {NC} {m}", flush=True)
    def bad(m):
        nonlocal fails; fails += 1
        print(f"{RED} FAIL {NC} {m}", flush=True)

    st, body = _req("GET", "/health")
    if st == 200 and body == {"status": "ok"}:
        pas("/health ok")
    else:
        bad(f"/health -> {st} {body}")

    st, body = _req("GET", "/models")
    models = (body or {}).get("models") if isinstance(body, dict) else None
    if st == 200 and models:
        pas(f"/models -> {len(models)} model(s): {', '.join(map(str, models))}")
    else:
        bad(f"/models -> {st} {body}")

    st, body = _req("POST", "/search", {"query": "töölepingu ülesütlemine", "limit": 5})
    if st == 200 and isinstance(body, list) and body:
        top = body[0]
        pas(f"/search -> {len(body)} hit(s); top: {top.get('act_title', '?')} {top.get('section_num', '?')}")
    elif st == 200 and body == []:
        war("/search -> 200 but 0 hits (corpus not ingested? run: python -m lawboi.ingest --all)")
    else:
        bad(f"/search -> {st} {body}")

    st, body = _req("POST", "/answer",
                    {"query": "Kui pikk on töölepingu ülesütlemise etteteatamise tähtaeg?"})
    if st == 200 and isinstance(body, dict):
        cites = body.get("citations", [])
        pas(f"/answer -> 200, model={body.get('model_used', '?')}, {len(cites)} citation(s)")
    elif st == 422:
        war("/answer -> 422 NoSourcesFound (expected with no ingested data; the gate works)")
    else:
        bad(f"/answer -> {st} {body}")

    print()
    if fails:
        print(f"{RED}{fails} check(s) failed.{NC}", flush=True)
        sys.exit(1)
    print(f"{GRN}All hard checks passed.{NC}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Manage the local lawboi dev environment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--full", action="store_true",
                       help="Ingest full corpus instead of sample (hours)")
    group.add_argument("--no-ingest", action="store_true", dest="no_ingest",
                       help="Skip ingest entirely")
    parser.add_argument("--smoke", action="store_true",
                        help="Run endpoint smoke checks against the running API")
    parser.add_argument("--down", action="store_true",
                        help="Stop API, UI, and db container")
    args = parser.parse_args()

    dc = _detect_compose()

    if args.down:
        stop_all(dc)
        return

    if args.smoke:
        run_smoke()
        return

    # --- up ---
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        die("Docker daemon unreachable. Using Colima? Run: colima start")

    ensure_venv()
    ensure_deps()
    ensure_package()
    ok("Python env ready")

    ensure_dotenv()
    check_llm_key()

    info("Starting db container...")
    compose_up_db(dc)
    wait_healthy(dc)
    ok("db healthy")

    apply_migrations(dc)

    ingest_mode = "full" if args.full else ("none" if args.no_ingest else "sample")
    ensure_ingest(dc, ingest_mode)

    start_api()
    start_ui()

    print(f"\n{GRN}Environment ready for manual testing.{NC}")
    print(f"  API : {API_URL}   (docs: {API_URL}/docs, logs: {API_LOG})")
    print(f"  UI  : {UI_URL}   (logs: {UI_LOG})")
    print(f"  Stop everything: python scripts/dev.py --down")


if __name__ == "__main__":
    main()
