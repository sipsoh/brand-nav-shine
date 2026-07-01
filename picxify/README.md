# Picxify

**Drop in messy data. Get the story.**

Picxify turns messy business data (CSV, Excel, pasted tables/text) into polished, trustworthy,
client-ready dashboards — with KPIs, charts, insights, editable assumptions, source traces for
every widget, and a shareable link.

See [SETUP.md](./SETUP.md) for the full architecture and milestone plan. This repo currently
implements **Milestone 1: monorepo and infrastructure**.

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
```

## Local development

### 1. Prerequisites

- Docker
- Node.js LTS + pnpm
- Python 3.11+

### 2. Start infrastructure

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

### 3. Run the API

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/health`

### 4. Run the Celery worker

```bash
cd apps/api
source .venv/bin/activate
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

### 5. Run the web app

```bash
cd apps/web
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
