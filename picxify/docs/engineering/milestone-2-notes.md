# Milestone 2 — Implementation Notes

## What was built

Auth and tenancy: Clerk on the web side, JWKS-based JWT verification in FastAPI, the first
three database tables (`users`, `workspaces`, `memberships`) with an Alembic migration, a
user-sync endpoint that provisions a default workspace on first sign-in, workspace CRUD with
membership-verified access, and the authenticated app shell with sidebar navigation.

## Tradeoffs and decisions

- **Clerk is feature-flagged by the publishable key.** With no `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`,
  the provider and middleware no-op and the sign-in pages show setup instructions. This keeps
  keyless CI builds and fresh clones green while making activation a pure env change. The Clerk
  SDK installed as v7, which dropped `SignedIn`/`SignedOut` — header state uses `useAuth()`
  in a client component instead, which is stable across versions.
- **Portable column types instead of Postgres-native ones.** Models use `sa.Uuid`, `sa.JSON`,
  and a `VARCHAR` role with a CHECK constraint rather than PG `UUID`/`JSONB`/`ENUM`. This lets
  the whole API test suite (and the migration itself) run against SQLite in-memory with no
  Docker dependency; Postgres still gets correct DDL. Native JSONB variants can be layered on
  when profiling data lands in Milestone 4.
- **Membership failures read as 404, not 403.** Per the SETUP.md security rule, holding a
  workspace ID must not confirm the workspace exists. Role failures (member but insufficient
  role) do return 403.
- **JWT tests use a real RSA key pair, not mocks of the verifier.** Tests generate a key,
  serve its JWK through a stubbed JWKS fetch, and run the actual verification path — covering
  expiry, forged signatures, unknown `kid`s, and missing subjects. Route tests override only
  the `get_principal` dependency, so permission logic stays fully exercised.
- **`/users/sync` is the provisioning point.** The web app calls it after sign-in rather than
  relying on Clerk webhooks. Simpler for MVP (no webhook endpoint/secret yet) and idempotent;
  a webhook-based sync can be added later for org events.

## Test results

`pytest` in `apps/api`: **24 passed** (health, worker, schema, JWT verification, user sync,
workspace isolation). `pnpm lint`, `pnpm typecheck`, `pnpm build` pass; 12 routes + middleware
compile. `alembic upgrade head` verified against a scratch database.

## Next steps (Milestone 3)

- Upload UI with drag-and-drop on `/app/upload`.
- `POST /uploads/presign` + `POST /uploads/{fileId}/complete` with size/type validation.
- `uploaded_files` model + migration; MinIO/S3 storage service using presigned PUT URLs.
- Plan-based upload size limits from env (`MAX_UPLOAD_MB_FREE`, `MAX_UPLOAD_MB_CREATOR`).
