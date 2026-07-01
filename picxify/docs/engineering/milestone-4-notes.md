# Milestone 4 — Implementation Notes

## What was built

The deterministic half of the data pipeline (SETUP.md §9 steps C–F): parse → normalize →
profile → snapshot → persist, running as a `parse_dataset` job with live progress, plus the
"what Picxify detected" UI. Everything here is code — no AI is involved yet, which is exactly
the point: the profiles produced here are the compact representation the AI layer will consume
in Milestone 5.

## Tradeoffs and decisions

- **pandas as the DataFrame engine, DuckDB for CSV sniffing only.** DuckDB's auto-detection
  handles delimiters/headers/types well, then hands off a DataFrame. Polars was dropped from
  the dependency set for now — one DataFrame API keeps normalization/profiling simple, and
  Parquet snapshots keep the door open for DuckDB-over-Parquet querying in Milestone 7.
- **pandas 3.x gotcha:** string columns are now `str` dtype, not `object`. All text-detection
  paths go through one `_is_text_dtype()` helper covering both. The unit tests caught this
  immediately — worth keeping them strict.
- **Every non-obvious transform is a finding.** Footer-row exclusion, currency conversion,
  date parsing, duplicate-column renames — each lands in `data_quality_findings` and surfaces
  in the UI. This is the §21.7 "Data Cleanup Preview" trust feature, built into the pipeline
  from day one rather than bolted on.
- **Jobs are testable without Celery.** The Celery task is a thin wrapper over
  `run_parse_dataset(db, storage, ...)`; tests call the function directly with a test session
  and fake storage. The API's dispatcher is a FastAPI dependency that enqueues to Celery and
  falls back to inline execution when no broker is reachable, so keyless local dev still works
  end to end.
- **Coercion threshold is 90%.** A column converts to numbers/dates only if ≥90% of non-null
  values parse; below that it stays text rather than silently destroying data. Unparseable
  values in a converted column become findings, not silent NaNs.
- **Quality score is a simple penalty model** (warnings −0.05, criticals −0.15, clamped to
  [0, 1]). Good enough to power the trust bar; can be refined once real messy files arrive.
- **Progress polling, not SSE.** The web app polls `GET /jobs/{id}` at 1.2s intervals with the
  job's own step labels. The optional SSE endpoint from §8.5 can replace this later without
  changing the job model.

## Test results

`pytest` in `apps/api`: **50 passed** — including the full flow test (upload → dataset →
parse job → profile read) and cross-user isolation on datasets and jobs. Migrations
`0001 → 0002 → 0003` apply cleanly. `pnpm lint`, `pnpm typecheck`, `pnpm build` pass.

## Next steps (Milestone 5)

- Semantic mapper service (LLM behind an interface, schema-constrained output): column →
  semantic type/role mappings, use-case candidates, editable assumptions.
- Deterministic fallback mapper for keyless dev (name/type heuristics).
- `assumptions` persistence and the assumption panel UI with accept/edit flows.
- Use-case detection feeding template selection in Milestone 7.
