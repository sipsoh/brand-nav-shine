# API Contract

Canonical contract lives in SETUP.md §8. Implemented endpoints are listed here as they ship.

## Implemented (Milestone 1)

| Endpoint | Response |
|---|---|
| `GET /health` (FastAPI) | `{ "ok": true, "service": "picxify-api", "version": "0.1.0" }` |
| `GET /api/health` (Next.js) | `{ "ok": true, "service": "picxify-web", "version": "0.1.0" }` |

## Rules

- All routes require authenticated workspace access unless explicitly public.
- Never accept `workspaceId` alone as proof of access — always verify membership.
- Typed request/response models (Pydantic on the API, TypeScript in `apps/web/lib/api-client.ts`).
