# Core User Flows

## Create a dashboard (the core loop)

1. Drop file or paste data (`/app/upload`).
2. Optionally choose audience/use case.
3. Upload goes to object storage via presigned URL.
4. Parse/profile job runs; progress steps stream to the UI
   (Reading file → Cleaning data → Detecting columns → Finding the story → Building dashboard → Validating sources).
5. Dashboard appears; user reviews assumptions.
6. User edits, exports, or shares.

## Share

Publish creates an unguessable slug at `/share/[slug]` — read-only, fast, no account needed.

## Refresh (post-MVP)

Recurring schedule re-runs generation against updated source data and compares periods.

See SETUP.md §11 and §20 for details and funnel metrics.
