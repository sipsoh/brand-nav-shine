# Milestone 6 — Implementation Notes

## What was built

The insight engine — the layer that makes "code calculates, AI narrates" enforceable.
Every fact (totals, trends, shares, outlier counts, win rates) is computed by pandas over
the normalized Parquet snapshots and carries a complete source trace. The dashboard planner
in Milestone 7 will only be allowed to cite these facts.

## Tradeoffs and decisions

- **Facts are the API between code and AI.** `ComputedFact` and `ComputedInsight` are plain
  dataclasses serializing to the shapes in the DashboardSpec schema (`fact`, `insight` defs),
  so Milestone 7 can drop them into specs without translation.
- **Trend grain is span-driven**: ≥ 70 days of data → month-over-month, otherwise
  week-over-week. Severity is cost-aware — spend going up is `negative`, revenue going up is
  `positive`.
- **MAD, not z-score, for outliers.** Median absolute deviation with the 0.6745 scaling
  constant and a 3.5 threshold is robust to the very outliers being hunted; plain z-scores
  get dragged by them. Requires ≥ 8 values and non-zero MAD to fire at all.
- **Text themes: the model groups, code counts.** The LLM returns comment *indexes*, never
  counts. Code deduplicates and drops out-of-range indexes, derives the count from what
  survives, and keeps up to 3 verbatim quotes. A theme pointing only at nonexistent comments
  disappears entirely. This is the concrete meaning of `model_supported_by_code`.
- **Insights are computed on demand, not persisted.** For MVP file sizes (≤ 10 MB) the
  computation is sub-second, and recomputing avoids invalidation bugs when assumptions are
  edited. Dashboard generation (M7) will snapshot the facts it uses into the spec, which is
  the durable record that matters.
- **Primary-measure priority** (revenue > cost > conversion > engagement > rating) picks
  which measure gets the trend; top-contributor pairs are capped at 3 dimensions to keep the
  result focused rather than exhaustive.

## Test results

`pytest` in `apps/api`: **74 passed** — including exact-value assertions (MoM +100%, top
share 81.25%, win rate 60%), a completeness invariant asserting every fact and insight
carries a non-empty trace with `generatedBy="code"`, and text-theme tests proving counts are
code-derived. `pnpm lint` / `typecheck` / `build` pass.

## Next steps (Milestone 7 — dashboard generation)

- Dashboard template definitions (client report, marketing, sales, survey, feedback,
  generic snapshot) as JSON.
- Planner prompt (schema-constrained to DashboardSpec) fed by profile + semantic map +
  computed facts; validation + repair loop; deterministic fallback planner for keyless dev.
- Chart query execution over Parquet (querySpec → data) and ECharts option building in code.
- `dashboards`/`dashboard_versions` models, `POST /dashboards/generate`, and spec persistence.
