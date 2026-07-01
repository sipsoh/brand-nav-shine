# Changelog

## Milestone 1 — Monorepo and infrastructure (2026-07-01)

- Monorepo structure: `apps/web`, `apps/api`, `packages/schemas`, `packages/sample-data`, `docs/`.
- `apps/web`: Next.js App Router + TypeScript + Tailwind, with landing, pricing, app shell,
  upload, dashboards, dashboard detail, and share routes plus a `/api/health` endpoint.
- `apps/api`: FastAPI + Pydantic settings + SQLAlchemy session skeleton + Alembic scaffolding,
  `GET /health` endpoint, CORS wired to the web origin.
- Celery worker skeleton connected to Redis with a `picxify.ping` task.
- `docker-compose.yml` for Postgres 16, Redis 7, and MinIO.
- Canonical `DashboardSpec` JSON schema at `packages/schemas/dashboard_spec.schema.json`
  plus validation tests (valid spec accepted; unknown widget types, missing source traces,
  wrong versions, and extra top-level keys rejected).
- `.env.example`, four sample datasets, product/engineering doc stubs.
- Smoke tests: 11 pytest cases covering health endpoint, Celery config/task, and schema.
