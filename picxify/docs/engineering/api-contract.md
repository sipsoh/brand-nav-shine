# API Contract

Canonical contract lives in SETUP.md §8. Implemented endpoints are listed here as they ship.

## Implemented (Milestone 1)

| Endpoint | Response |
|---|---|
| `GET /health` (FastAPI) | `{ "ok": true, "service": "picxify-api", "version": "0.1.0" }` |
| `GET /api/health` (Next.js) | `{ "ok": true, "service": "picxify-web", "version": "0.1.0" }` |

## Implemented (Milestone 2)

All endpoints below require a Clerk-issued bearer JWT (verified against `CLERK_JWKS_URL`).

| Endpoint | Behavior |
|---|---|
| `POST /users/sync` | Upserts the authenticated user from token claims; creates a default workspace with an `owner` membership on first sync. Returns `{ user, workspaces, created }`. |
| `GET /workspaces` | Lists workspaces the current user is a member of, with their role. |
| `POST /workspaces` | Creates a workspace and an `owner` membership. Returns 201. |
| `GET /workspaces/{id}` | Returns the workspace if the user is a member; otherwise 404 (non-members must not be able to confirm a workspace exists). |

## Implemented (Milestone 3)

| Endpoint | Behavior |
|---|---|
| `POST /uploads/presign` | Validates membership (editor+), file type (CSV/TSV/TXT/XLSX/XLS; macro formats rejected), and size against plan limits; creates a `pending` file record; returns `{ fileId, uploadUrl, objectKey, expiresInSeconds }`. |
| `POST /uploads/{fileId}/complete` | Verifies the object actually landed in storage (and its real size); marks the record `uploaded`. 409 if storage never received the file; idempotent on retry. |

## Implemented (Milestone 4)

| Endpoint | Behavior |
|---|---|
| `POST /datasets/from-file` | Creates a dataset + `parse_dataset` job for an uploaded file (must be `uploaded`); dispatches to Celery (inline fallback in keyless dev). Returns `{ datasetId, jobId, status }`. |
| `GET /jobs/{jobId}` | Job status/progress/current step; membership-checked via the job's workspace. |
| `GET /datasets/{datasetId}` | Full profile: tables, columns (types, roles, null/unique ratios, stats, examples), sample rows, and data-quality findings. |

## Implemented (Milestone 5)

| Endpoint | Behavior |
|---|---|
| `GET /datasets/{id}` (extended) | Now includes `useCaseCandidates`, per-column `semanticType`, and the dataset's `assumptions`. |
| `PATCH /datasets/{datasetId}/assumptions/{assumptionId}` | Accept/reject an assumption, or apply a `replacement` (`{column, semanticType}`) that remaps a column's meaning. Editor+ role; 409 for non-editable assumptions. |

## Implemented (Milestone 6)

| Endpoint | Behavior |
|---|---|
| `GET /datasets/{id}/insights` | Computes facts and insights from the Parquet snapshots on demand: overview totals, trend (MoM/WoW), top contributors, composition, MAD outliers, funnel/win rate, data-quality caveats, and (for survey/feedback datasets with an LLM configured) text themes. Every fact and insight carries a `sourceTrace`. |

## Implemented (Milestone 7)

| Endpoint | Behavior |
|---|---|
| `POST /dashboards/generate` | Creates a dashboard + `generate_dashboard` job for a parsed dataset (`{workspaceId, datasetId, audience?, useCaseHint?, titleHint?}`). Editor+ role; 409 for unparsed datasets. |
| `GET /dashboards?workspaceId=` | Lists workspace dashboards with visibility and version status. |
| `GET /dashboards/{id}` | Dashboard with its current version's validated DashboardSpec and generation metadata (planner used, prompt version, template code). |

## Rules

- All routes require authenticated workspace access unless explicitly public.
- Never accept `workspaceId` alone as proof of access — always verify membership.
- Typed request/response models (Pydantic on the API, TypeScript in `apps/web/lib/api-client.ts`).
