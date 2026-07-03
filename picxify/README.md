# Picxify

**Drop in messy data. Get the story.**

Picxify turns messy business data (CSV, Excel, pasted tables/text) into polished, trustworthy,
client-ready dashboards — with KPIs, charts, insights, editable assumptions, source traces for
every widget, and a shareable link.

See [SETUP.md](./SETUP.md) for the original architecture and milestone plan, and
[docs/engineering/data-engine.md](./docs/engineering/data-engine.md) for what the ingestion
engine currently detects and guarantees (CSV/Excel/PDF/scanned-image ingestion, structure
detection, multi-file joins, confidence scoring — see `CHANGELOG.md` for the full history).

## Repository layout

```txt
picxify/
  apps/
    web/        Next.js App Router + TypeScript + Tailwind (port 3000)
    api/        FastAPI + Pydantic + SQLAlchemy + Alembic + Celery (port 8000)
  packages/
    schemas/    Shared DashboardSpec JSON schema
    sample-data/  Fixture datasets for parsing/profiling/eval tests
  docs/         Product and engineering docs
  docker-compose.yml  Postgres, Redis, MinIO for local dev
  dev-up.sh / dev-down.sh  One-command local dev without Docker (see below)
```

## Local development

### The fast path: no Docker, one command

If you don't have Docker, `./dev-up.sh` runs everything off a local Postgres
(via Homebrew) and stores uploads as plain files on disk — no Redis, no
MinIO/S3 needed at all.

**One-time setup:**

```bash
brew install postgresql@16                 # add: brew install tesseract  (only for scanned-PDF/OCR uploads)
cd apps/api && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
cd ../web && pnpm install
cd ../api && cp .env.example .env           # paste your Clerk JWKS URL — see comments inside
cd ../web && cp .env.local.example .env.local   # paste your two Clerk keys — see comments inside
```

**Every time after that:**

```bash
./dev-up.sh      # starts Postgres, runs migrations, starts API + web in the background
```

Open **http://localhost:3000** and leave it running — close the terminal, come
back later, it's still up. Run `./dev-down.sh` to stop the API/web (Postgres,
a system service, keeps running; `brew services stop postgresql@16` if you
want it off too). Logs land in `.dev/api.log` and `.dev/web.log`.

Re-run `./dev-up.sh` any time you pull new code — it reapplies migrations and
restarts anything that isn't already running; it won't spawn duplicates.

### The full path: Docker + real object storage

Use this if you want the production-shaped stack (real S3-compatible storage,
a separate Celery worker process) rather than the local-disk/inline-job
shortcuts above.

#### 1. Prerequisites

- Docker
- Node.js LTS + pnpm
- Python 3.11+

#### 2. Start infrastructure

```bash
cp .env.example .env
docker compose up -d
```

This starts Postgres (5432), Redis (6379), and MinIO (9000, console on 9001,
`minioadmin`/`minioadmin`). Then create the dev bucket once — either in the MinIO
console at http://localhost:9001, or from the CLI:

```bash
docker run --rm --network host minio/mc:latest \
  /bin/sh -c "mc alias set local http://localhost:9000 minioadmin minioadmin && mc mb --ignore-existing local/picxify-dev"
```

#### 3. Run the API

```bash
cd apps/api
cp .env.example .env    # then paste your Clerk JWKS URL into .env (see comments inside)
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head    # creates all tables
uvicorn app.main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/health`

Note: the API loads `.env` from `apps/api/` (its working directory), not the repo root.

#### 4. Run the Celery worker

```bash
cd apps/api
source .venv/bin/activate
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

#### 5. Run the web app

```bash
cd apps/web
cp .env.local.example .env.local   # then paste your two Clerk keys (see comments inside)
pnpm install
pnpm dev
```

Open http://localhost:3000. Web health check: http://localhost:3000/api/health

## Tests

```bash
# API smoke tests
cd apps/api && source .venv/bin/activate && pytest

# Web lint + typecheck + build
cd apps/web && pnpm lint && pnpm typecheck && pnpm build
```

## Hard constraints (from SETUP.md)

- Every resource is scoped to `workspace_id`; membership is always verified.
- Dashboards render from validated `DashboardSpec` JSON (`packages/schemas/dashboard_spec.schema.json`).
- LLMs never calculate final metrics — code computes, AI narrates/plans.
- Every generated chart, KPI, and insight carries a `sourceTrace`.
