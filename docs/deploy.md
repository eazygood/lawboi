# Deployment

Target: **DigitalOcean** — Managed Postgres 16 (pgvector) + the API and UI on
App Platform (or a single Droplet). EU region (FRA1) for data residency.

The strategy is **validate locally, ship a known-good dataset**: run ingest and the
eval on your machine, then move the validated database to live with one `pg_dump` /
`pg_restore`. Because embeddings live in the `provision.embedding` column (not a
separate vector store), a single dump captures relational rows, vectors, and indexes
together.

## Two rules you can't break

1. **Enable pgvector on the target before restoring.** The dump declares
   `embedding vector(1024)` columns; without the extension the restore fails on an
   unknown type. Run `CREATE EXTENSION IF NOT EXISTS vector;` on the managed DB first.
   Dump and restore must be the same Postgres major version (16 → 16).
2. **The live API must embed queries with the identical model used for ingest.**
   Pre-computed corpus vectors only match incoming queries if they share a vector
   space. Ingest uses `intfloat/multilingual-e5-large` (`passage:` prefix); the API's
   `DenseSearch` embeds queries with the same model (`query:` prefix). `api/Dockerfile`
   bakes that exact model in. Never let the ingest model and the live query model drift.

---

## 1. Validate locally

```bash
docker-compose up -d db                      # Postgres + pgvector
.venv/bin/python -m lawboi.ingest "TLS"      # embed + write rows and vectors
uvicorn lawboi.api.main:app --reload --port 8000
.venv/bin/python eval/run_eval.py --api http://localhost:8000
```

Iterate until retrieval quality and answers are good. Everything below ships *this*
validated dataset unchanged.

## 2. Provision managed Postgres (DigitalOcean)

- Create a Managed Database → PostgreSQL 16, region FRA1. Note the SSL connection URI.
- Enable pgvector (rule 1):

  ```bash
  psql "$LIVE_DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
  ```

The schema (`db/schema.sql`) does not need to be applied separately — the dump in the
next step recreates it. (For an empty DB without a dump, apply it manually:
`psql "$LIVE_DATABASE_URL" -f db/schema.sql`.)

## 3. Dump locally, restore to live

```bash
# Local: dump the validated DB (custom format)
pg_dump -Fc "postgresql://lawboi:lawboi@localhost:5432/lawboi" -f lawboi.dump

# Live: restore (extension must already exist — see rule 1)
pg_restore --no-owner --no-privileges -d "$LIVE_DATABASE_URL" lawboi.dump
```

Keep `lawboi.dump` out of git — it is large and not source.

## 4. Configure env / secrets

API (App Platform component env, or `.env` on a Droplet):

| Var | Value |
|---|---|
| `DATABASE_URL` | managed Postgres SSL URI (secret) |
| `LLM_MODEL` | e.g. `gemini-2.0-flash` |
| `GEMINI_API_KEY` (or OpenAI/Anthropic) | provider key (secret) |
| `COHERE_API_KEY` | rerank key, optional (secret) |
| `CORS_ORIGINS` | JSON list of the prod UI domain, e.g. `["https://app.example.com"]` |

UI:

| Var | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | public API URL (baked into the browser bundle at build) |
| `API_URL` | API URL for server-side calls |

## 5. Deploy the services

**App Platform (push-to-deploy):** one app, two components built from the existing
Dockerfiles — API from `api/Dockerfile` (size it **8 GB**; it loads the e5 model at
runtime for query embedding), UI from `ui/Dockerfile` (smallest size). Health check →
`/health`. Wire to the GitHub repo for push-to-deploy.

**Droplet alternative (cheaper, slightly more ops):** an 8 GB Droplet running
`docker-compose` for the `api` and `ui` services, pointed at the managed Postgres via
`DATABASE_URL`. Skip the compose `db` service in production.

> The live API box needs ~8 GB because it embeds every query at request time. Dumping
> pre-computed vectors removes the model from *ingest* on the cloud, not from the API.

## 6. Verify

```bash
psql "$LIVE_DATABASE_URL" -c "\dx"                                   # vector extension present
psql "$LIVE_DATABASE_URL" -c "SELECT count(*) FROM provision WHERE embedding IS NOT NULL;"  # > 0
curl https://<api-domain>/health                                    # {"status":"ok"}
curl https://<api-domain>/models                                    # API + DB reachable
curl -XPOST https://<api-domain>/search \
  -H 'content-type: application/json' \
  -d '{"query":"töölepingu ülesütlemine"}'                          # provision hits → pgvector + embedder OK
curl -XPOST https://<api-domain>/answer \
  -H 'content-type: application/json' \
  -d '{"query":"..."}'                                              # cited answer; empty retrieval → 422
```

Open the UI domain → a question returns an answer with the source panel populated.
Confirm the managed DB shows automated daily backups enabled.

---

## Ongoing updates

For new laws or version changes after launch, you don't need another dump. Run ingest
from your laptop pointed at the live DB — only your machine runs the model, and it
writes vectors straight to production:

```bash
DATABASE_URL="$LIVE_DATABASE_URL" .venv/bin/python -m lawboi.ingest "<law>"
```

## Cost & embedding lever (notes)

- Lean DO config (Droplet 8 GB + Managed PG) ≈ **$65/mo**, predictable flat rate.
- The 8 GB box exists for query-time embedding. Moving query embedding to a managed
  embedding API (e.g. Cohere — key already configured) shrinks the API to a <512 MB
  instance (≈ **$30/mo** total) and makes serverless viable. Cost of the switch: a full
  corpus re-embed + validating Estonian quality. Defer past first users.
