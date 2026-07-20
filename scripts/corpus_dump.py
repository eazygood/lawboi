#!/usr/bin/env python3
"""
Export/import the ingested corpus (act/act_version/provision, incl. embeddings)
to/from db/corpus.dump, so you don't have to re-run ingest after a DB reset.

  python scripts/corpus_dump.py export   # dev db (lawboi-db-1) -> db/corpus.dump
  python scripts/corpus_dump.py import   # db/corpus.dump -> dev db (lawboi-db-1)
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONTAINER = "lawboi-db-1"
DUMP_PATH = ROOT / "db/corpus.dump"
CONTAINER_TMP = "/tmp/corpus.dump"
TABLES = ["act", "act_version", "provision"]

if sys.stdout.isatty():
    RED = "\033[31m"; GRN = "\033[32m"; YEL = "\033[33m"; DIM = "\033[2m"; NC = "\033[0m"
else:
    RED = GRN = YEL = DIM = NC = ""

def info(msg): print(f"{DIM}==>{NC} {msg}", flush=True)
def ok(msg):   print(f"{GRN} PASS {NC} {msg}", flush=True)
def die(msg):  print(f"{RED} FAIL {NC} {msg}", flush=True); sys.exit(1)


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, cwd=ROOT, **kw)


def run_q(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def ensure_container_running():
    r = run_q(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER])
    if r.returncode != 0 or r.stdout.strip() != "true":
        die(f"{CONTAINER} is not running. Start it: docker-compose up -d db")


def act_count():
    r = run_q(["docker", "exec", CONTAINER, "psql", "-U", "lawboi", "-d", "lawboi",
               "-tAc", "SELECT count(*) FROM act"])
    try:
        return int(r.stdout.strip())
    except (ValueError, AttributeError):
        return None


def export_corpus():
    ensure_container_running()
    count = act_count()
    info(f"Dumping {', '.join(TABLES)} from {CONTAINER} ({count if count is not None else '?'} act(s))...")
    run(["docker", "exec", CONTAINER, "pg_dump", "-U", "lawboi", "-d", "lawboi",
         "--data-only", "--format=custom",
         *[arg for t in TABLES for arg in ("-t", t)],
         "-f", CONTAINER_TMP])
    run(["docker", "cp", f"{CONTAINER}:{CONTAINER_TMP}", str(DUMP_PATH)])
    size_kb = DUMP_PATH.stat().st_size // 1024
    ok(f"Wrote {DUMP_PATH.relative_to(ROOT)} ({size_kb} KB)")


def import_corpus():
    if not DUMP_PATH.exists():
        die(f"{DUMP_PATH.relative_to(ROOT)} not found. Run 'export' first, or check it out from wherever it's backed up.")
    ensure_container_running()
    before = act_count()
    if before:
        info(f"{CONTAINER} already has {before} act(s) — pg_restore will error on any conflicting primary keys "
             f"rather than duplicate rows, so this is safe to attempt but may need a clean db first.")
    info(f"Restoring {DUMP_PATH.relative_to(ROOT)} into {CONTAINER}...")
    run(["docker", "cp", str(DUMP_PATH), f"{CONTAINER}:{CONTAINER_TMP}"])
    run(["docker", "exec", CONTAINER, "pg_restore", "-U", "lawboi", "-d", "lawboi",
         "--data-only", "--disable-triggers", CONTAINER_TMP])
    after = act_count()
    ok(f"Restored. act count: {before if before is not None else '?'} -> {after if after is not None else '?'}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["export", "import"])
    args = parser.parse_args()

    if args.action == "export":
        export_corpus()
    else:
        import_corpus()


if __name__ == "__main__":
    main()
