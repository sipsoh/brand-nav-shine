# Changelog

## Milestone 4 — Parsing and profiling (2026-07-01)

- Parser: CSV/TSV/TXT via DuckDB auto-detection; Excel via openpyxl with one table per
  non-empty sheet; friendly `ParseError`s for empty/undetectable files.
- Normalization with an audit trail: blank row/column removal, duplicate column renaming,
  footer/total row exclusion, currency/percent/number string coercion, multi-format date
  parsing, whitespace trimming — every non-obvious transform becomes a data-quality finding.
- Column profiler: detected type (integer/float/currency/percent/date/datetime/boolean/
  category/text/id), role hints (measure/dimension/date/id/text), null/unique ratios,
  per-type stats, examples, and confidence; JSON-safe sample rows; dataset quality score.
- Parquet snapshots of normalized tables written to object storage per table.
- Models + migration `0003`: `datasets`, `dataset_tables`, `dataset_columns`,
  `data_quality_findings`, `generation_jobs`.
- Endpoints: `POST /datasets/from-file`, `GET /jobs/{id}`, `GET /datasets/{id}`; Celery
  `picxify.parse_dataset` task with inline fallback when no broker is reachable.
- Web: upload now chains into dataset creation, polls the parse job with live step labels,
  and lands on `/app/datasets/[id]` — the "what Picxify detected" profile view with type
  chips, missing-value percentages, examples, and cleanup/quality notes.
- Tests: 16 new pytest cases (50 total) — normalization units, pipeline runs against the
  real sample CSV, a messy CSV (blank rows, footer totals, currency strings, mixed dates,
  missing values), multi-sheet Excel, empty-file failure, and the full API flow with
  isolation checks. Fixed a pandas 3.x `str`-dtype incompatibility found by these tests.

## Milestone 3 — Upload and storage (2026-07-01)

- API: `uploaded_files` model + migration `0002`, with a `pending → uploaded` lifecycle and a
  status CHECK constraint.
- API: S3/MinIO storage service (presigned PUT/GET, object stat) behind a FastAPI dependency.
- API: `POST /uploads/presign` — membership (editor+), file-type allowlist (macro-enabled Office
  formats rejected), size limit, filename sanitization against path traversal; object keys are
  scoped as `workspaces/{workspaceId}/uploads/{fileId}/{filename}`.
- API: `POST /uploads/{fileId}/complete` — verifies the object exists in storage, re-checks the
  real object size (a client-declared size is not trusted), idempotent on retry.
- Web: drag-and-drop upload on `/app/upload` running the full presign → PUT → complete flow
  with step-by-step progress, success, and friendly error states.
- Tests: 10 new pytest cases (34 total) covering validation, traversal, tenancy isolation on
  both endpoints, missing-object 409, and size-lie rejection at completion time.

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
