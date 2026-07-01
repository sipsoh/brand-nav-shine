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

## Rules

- All routes require authenticated workspace access unless explicitly public.
- Never accept `workspaceId` alone as proof of access — always verify membership.
- Typed request/response models (Pydantic on the API, TypeScript in `apps/web/lib/api-client.ts`).
