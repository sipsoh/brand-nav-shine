# Milestone 1 — Implementation Notes

## What was built

The monorepo foundation: Next.js web app, FastAPI API, Celery worker skeleton, Docker Compose
infrastructure (Postgres/Redis/MinIO), the canonical DashboardSpec schema with tests, sample
datasets, and health endpoints on both services. No dashboard generation yet, by design.

## Tradeoffs and decisions

- **Hand-scaffolded Next.js instead of `create-next-app`.** Gives an exact match to the SETUP.md
  route structure with no generator boilerplate to delete. Uses Next 15 + React 19 + Tailwind v4
  (CSS-first config via `@tailwindcss/postcss`; no `tailwind.config.ts` needed).
- **Canonical bundle files adopted verbatim.** `SETUP.md`, `docker-compose.yml`, `.env.example`,
  and `dashboard_spec.schema.json` come from the implementation-guide bundle unmodified, so the
  repo matches the spec author's contract. Schema tests were written against that schema.
- **Single Python package for API + worker.** The Celery worker imports from the same `app`
  package as FastAPI (`apps/api/pyproject.toml`). Simpler for MVP; they can be split into
  separate deployables later since the worker entrypoint is already its own process.
- **Data/AI dependencies are an optional extra** (`pip install -e ".[data]"`). Milestone 1 does
  not need DuckDB/pandas/polars/openai, so the default install stays fast; Milestone 4 flips
  them into the core dependency list.
- **Alembic is wired but has no migrations.** `Base.metadata` is empty until models land in
  Milestone 2; `env.py` already resolves `DATABASE_URL` from settings, so the first
  autogenerate is a one-liner.
- **MinIO bucket creation is a documented one-liner, not automated in compose**, to keep the
  canonical `docker-compose.yml` untouched.

## Test results

`pytest` in `apps/api`: **11 passed** (health contract, Celery config, ping task, DashboardSpec
schema acceptance/rejection cases). `pnpm lint`, `pnpm typecheck`, and `pnpm build` pass in
`apps/web`. `uvicorn` serves `/health` matching the SETUP.md §8.1 contract exactly.

## Next steps (Milestone 2)

- Clerk auth in the web app; JWT verification against Clerk JWKS in FastAPI.
- `users`, `workspaces`, `memberships` models + first Alembic migration.
- User sync endpoint and default-workspace creation on signup.
- Workspace-scoped permission checks as a reusable dependency.
