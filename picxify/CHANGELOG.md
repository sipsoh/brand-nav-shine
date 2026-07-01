# Changelog

## Milestone 2 — Auth, workspace, and navigation (2026-07-01)

- API: Clerk JWT verification via JWKS (`app/auth.py`) with key-rotation refresh, expiry and
  signature checks, and `Principal` extraction from claims.
- API: `users`, `workspaces`, `memberships` SQLAlchemy models and the first Alembic migration
  (`0001`), verified end-to-end against a scratch database.
- API: `POST /users/sync` upserts the user and creates a default workspace + owner membership
  on first sign-in; `GET/POST /workspaces` and `GET /workspaces/{id}` with membership checks.
- API: workspace permission service — membership always verified, non-members get 404 so
  workspace IDs are not enumerable.
- Web: Clerk integration that activates when `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` is set
  (provider, middleware protecting `/app(.*)`, sign-in/sign-up routes, header auth controls);
  builds stay green without keys.
- Web: app shell with sidebar navigation (Home/Upload/Dashboards/Settings) and a workspace
  bootstrap component that calls `/users/sync` after sign-in and lists workspaces.
- Tests: 24 pytest cases including real RS256 JWT verification against a locally generated
  key pair (valid/expired/forged/unknown-kid tokens) and cross-user workspace isolation.

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
