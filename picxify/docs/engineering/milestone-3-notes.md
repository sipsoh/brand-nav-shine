# Milestone 3 — Implementation Notes

## What was built

The upload pipeline's front half: presigned-URL uploads to MinIO/S3 with an `uploaded_files`
ledger in Postgres, validation at both ends of the flow, and a drag-and-drop upload UI that
walks presign → direct PUT to storage → completion confirmation.

## Tradeoffs and decisions

- **A `pending` status precedes the guide's `file_status` enum.** The presign/complete flow has
  a window where a DB record exists but the bytes may never arrive; `pending` makes that state
  explicit instead of pretending the file is `uploaded` at presign time. Abandoned `pending`
  rows can be garbage-collected later.
- **The declared size is not trusted.** Presign validates the client-declared `sizeBytes` for
  fast feedback, but `/complete` re-checks the *actual* object size via `HEAD` — a client that
  lies at presign and uploads something huge gets the record marked `failed` and a 413.
- **Filename sanitization keeps the original name readable.** Path components and unsafe
  characters are stripped (`../../etc/passwd.csv` → `passwd.csv`), and the object key is always
  server-constructed under `workspaces/{workspaceId}/uploads/{fileId}/`, so a hostile filename
  can never place an object outside the workspace prefix.
- **Storage is a dependency, not a global.** `get_storage()` lets tests substitute an in-memory
  fake, so the entire flow (including the storage-missing 409) is tested without MinIO running.
- **Viewers cannot upload.** Presign and complete both require an owner/admin/editor membership;
  everyone is on the free plan's 10 MB limit until billing lands in Milestone 10.
- **MIME allowlist includes `application/octet-stream`** because browsers commonly send it for
  CSVs; the extension allowlist is the real gate, and macro-enabled formats (`.xlsm`, `.xlsb`)
  are rejected outright per SETUP.md §17.4.

## Test results

`pytest` in `apps/api`: **34 passed**. Both migrations (`0001` → `0002`) apply cleanly to a
scratch database. `pnpm lint`, `pnpm typecheck`, and `pnpm build` pass.

Not verifiable in this environment: a real browser PUT to MinIO (no Docker daemon here). On a
local machine: `docker compose up -d`, create the `picxify-dev` bucket, run both migrations,
start the API and web app, and drop a CSV on `/app/upload`.

## Next steps (Milestone 4)

- Install the `[data]` extra (DuckDB, Polars/pandas, PyArrow, openpyxl) as core deps.
- `datasets`, `dataset_tables`, `dataset_columns`, `data_quality_findings` models + migration.
- `POST /datasets/from-file` creating a parse job; Celery `parse_dataset_job` task.
- CSV parser (DuckDB auto-detect), Excel parser, normalization, column profiler,
  quality findings, Parquet snapshot to object storage.
- Dataset profile UI ("what Picxify detected").
