# Milestone 5 — Implementation Notes

## What was built

The semantic layer: after profiling, the pipeline now runs a "Finding the story" step that
infers what each column means (revenue, cost, campaign, rating, comment…), which dashboard
use case the dataset fits, and which of those inferences deserve user review as editable
assumptions. Users can accept, reject, or remap assumptions from the dataset page.

## Tradeoffs and decisions

- **Heuristics first, LLM second.** A deterministic mapper (name patterns gated by detected
  types) always runs and always produces a result. The LLM pass is an *overlay*: its output
  is schema-validated, hallucinated column names are dropped (logged), out-of-range
  confidences are clamped, and any failure falls back to pure heuristics. This means keyless
  dev/CI behave identically to production minus model quality — and the LLM can never
  introduce a column that doesn't exist.
- **The model sees profiles, not data** (§17.2): column names, detected types, unique ratios,
  and at most 3 example values per column. No raw rows.
- **Assumptions belong to datasets for now.** The guide's schema ties assumptions to
  dashboard versions, which don't exist until Milestone 7. Dataset-level assumptions are the
  natural home during profiling; dashboard generation will copy/reference them into specs.
- **`needs_review` is the default status** — ambiguity is shown, not hidden (the milestone's
  definition of done). Only `accepted`/`rejected` can be set through the API; `system` is
  reserved for non-editable pipeline facts.
- **Replacement is the remap primitive.** `PATCH ... {replacement: {column, semanticType}}`
  writes straight to `dataset_columns.semantic_type` and marks the assumption accepted with
  the change recorded in its metadata. Regeneration-on-change arrives with dashboards (M7).
- **Survey vs customer feedback disambiguation** uses rating-column count plus a respondent/
  question signal in column names; single-rating + comment + channel/status reads as customer
  feedback. Tests pin each case.

## Test results

`pytest` in `apps/api`: **63 passed** — mapper heuristics per use case, LLM merge with a fake
client, hallucinated-column dropping, invalid-output fallback, pipeline persistence, and the
assumption review API with membership isolation. Migrations `0001 → 0004` apply cleanly.
`pnpm lint` / `typecheck` / `build` pass.

Not verified here: a live OpenAI call (no key in this environment). The `OpenAILLMClient`
uses Structured Outputs with `strict: true`; first run with a real key should confirm the
schema round-trips.

## Next steps (Milestone 6 — insight engine)

- Computed facts with source traces: trend (MoM/WoW), top contributors, outliers (MAD/IQR),
  composition, funnel when stage/status exists, and data-quality caveats.
- All numeric facts computed by code over the Parquet snapshots (DuckDB), never by the LLM.
- Text theme/sentiment extraction for survey/customer-feedback datasets (LLM, but with
  representative source rows retained).
