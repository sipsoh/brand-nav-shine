# Changelog

## Milestone 7 — Dashboard generation (2026-07-02)

- Six dashboard template definitions in source control (client report, marketing, sales,
  survey, customer feedback, generic snapshot) with a use-case selector.
- Query runner: validated querySpec → pandas execution (group by dimensions and/or date
  grain, sum/avg/median/min/max/count/count_distinct, sort, limit) with unknown-column and
  unsupported-aggregation errors.
- Chart builder: ECharts options built entirely in code from query results (line, area, bar,
  horizontal_bar, stacked_bar, pie, donut, funnel).
- Deterministic fallback planner that fills the template from computed facts/insights: hero
  KPIs (rows, totals, trend with direction, win rate), trend + breakdown + funnel charts,
  insight cards, executive summary, assumption/source panels, derived actions.
- Guarded LLM planner: schema-constrained generation against the canonical DashboardSpec,
  one repair attempt on validation failure, then hard guards — insights swapped back to the
  code-computed versions by id, KPI values must match a computed fact or the widget is
  dropped, echartsOptions always rebuilt by code. Any failure falls back to the
  deterministic planner.
- Spec validator: canonical JSON-schema validation plus a Picxify-specific source-trace
  completeness check on every KPI/chart/insight.
- `dashboards` + `dashboard_versions` models and migration `0005`; generate/list/get
  endpoints; `picxify.generate_dashboard` Celery task with inline fallback.
- Web: full DashboardSpec renderer (`spec → UI`, no LLM calls) — KPI cards, ECharts widgets,
  insight cards, text/assumption/source panels, safe fallback for unknown widget types,
  "View source" on every widget, trust bar, and recommended actions. "Generate dashboard"
  button on the dataset page with live job progress; dashboards list page.
- Tests: 18 new pytest cases (92 total) — query/chart correctness, fallback spec validating
  against the canonical schema end-to-end, broken charts dropped not rendered, hallucinated
  KPIs/insights stripped from LLM plans, and the full upload→parse→generate→read flow.

## Milestone 6 — Insight engine (2026-07-02)

- Insight engine (`app/services/insight_engine.py`): all numeric facts computed by code
  over the normalized data, each with a full source trace (table, columns, filters,
  calculation, row count, generatedBy="code").
- Insight types: overview totals per measure; trend (monthly grain for spans ≥ 70 days,
  weekly below, cost-aware severity); top contributors with composition facts; outliers via
  median-absolute-deviation robust z-score; funnel stage counts + win rate when won/lost
  values exist; warning/critical quality findings promoted to insights.
- Text themes for survey/customer-feedback datasets: the LLM clusters comments by index,
  code validates the indexes, derives the counts, and keeps representative quotes —
  generatedBy="model_supported_by_code". Skipped cleanly when keyless.
- Versioned `text_themes_v1` prompt + output schema in source control.
- `GET /datasets/{id}/insights` computes per-table facts/insights from Parquet snapshots.
- Web: "Notable patterns" section on the dataset page with severity styling and an
  expandable "How this was calculated" source-trace drawer on every insight.
- Tests: 11 new pytest cases (74 total) — exact trend/share/win-rate values, MAD outliers,
  clean-data non-detection, a source-trace completeness invariant over all outputs, and
  text-theme count derivation (duplicate/out-of-range indexes handled, ghost themes dropped).

## Milestone 5 — Semantic mapping and assumptions (2026-07-02)

- Semantic mapper (SETUP.md §9.5): deterministic heuristic core (name patterns + detected
  types) that always runs, plus an optional schema-constrained LLM pass. LLM output is
  validated against the real columns — hallucinated columns are dropped, invalid output
  falls back to heuristics entirely.
- Use-case detection: marketing / sales / survey / customer_feedback / finance / generic,
  from semantic signals plus filename hints; candidates stored on the dataset profile.
- LLM provider behind an interface (`app/services/llm.py`); OpenAI Structured Outputs when
  `OPENAI_API_KEY` is set, `None` otherwise — keyless dev stays fully functional.
- Versioned prompt in source control (`semantic_mapper_v1`) with its JSON output schema;
  prompt version recorded in the dataset profile.
- `assumptions` model + migration `0004`; the pipeline now has a "Finding the story" step
  that persists semantic types, use-case candidates, and reviewable assumptions.
- `PATCH /datasets/{id}/assumptions/{id}`: accept/reject, or remap a column's semantic type
  via `replacement`; dataset response now carries assumptions and use-case candidates.
- Web: assumption panel on the dataset page with confidence, accept/reject actions, and a
  "Looks like: marketing (90%)" use-case badge; columns table shows the inferred meaning.
- Tests: 13 new pytest cases (63 total) — heuristics per use case, LLM merge/hallucination/
  fallback behavior with fake clients, and the full assumption review flow with isolation.

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
