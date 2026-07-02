# Milestone 7 — Implementation Notes

## What was built

The full generation path: uploaded sample data now produces a complete, validated dashboard.
`POST /dashboards/generate` runs template selection → fact computation → planning → chart
execution → validation → versioned persistence, and the web app renders the resulting
DashboardSpec with zero LLM involvement at render time (the milestone's definition of done).

## Tradeoffs and decisions

- **The fallback planner is the product's floor, the LLM is the ceiling.** A deterministic
  planner fills the selected template from computed facts and insights and always produces a
  schema-valid spec. The LLM planner can produce richer layouts, but its output goes through
  validation → one repair attempt → hard guards; any failure lands on the fallback. Keyless
  environments (like CI) therefore exercise the exact code path production falls back to.
- **Three hard guards on LLM plans:** (1) embedded insights are replaced with the
  code-computed versions by id — unknown ids drop the widget; (2) a KPI value must string-match
  a computed fact value (raw or formatted) or the widget is dropped; (3) `echartsOption` from
  the model is discarded unconditionally — charts are always rebuilt by `execute_charts`.
  This makes "every numeric claim must be backed by a computed fact" mechanical, not aspirational.
- **Charts that fail, disappear.** If a querySpec references a missing column or returns no
  data, the widget is dropped (and logged) rather than rendered wrong or crashing the spec.
  Sections that end up empty are removed; the spec re-validates after execution.
- **Templates live in code, not the DB.** They version with the planner that fills them;
  `dashboard_templates` can be added when runtime editing matters. `dashboards.template_code`
  records which was used.
- **`current_version_id` is a plain column, not an FK**, avoiding the circular
  dashboards↔versions constraint that complicates SQLite tests and Alembic ordering.
  `dashboard_versions` rows are append-only; version numbers are per-dashboard sequences.
- **The canonical schema is the single contract.** The validator loads
  `packages/schemas/dashboard_spec.schema.json` directly, and a path bug caught by tests is a
  reminder the schema is shared by the API, tests, and (conceptually) the frontend renderer.
- **Renderer safety rules** (§7.2/§11.3): unknown widget types render a fallback card; a
  chart with an empty option shows an empty state; every widget exposes "View source".

## Test results

`pytest` in `apps/api`: **92 passed** — query runner semantics, chart option shapes, the
fallback spec validating against the canonical schema with executed charts, sabotaged charts
dropped cleanly, a schema-valid-but-hallucinating fake LLM having its invented KPI and
insight stripped while legitimate widgets survive, and the end-to-end
upload → parse → generate → read flow with tenancy isolation. Migrations `0001 → 0005`
apply cleanly. `pnpm lint` / `typecheck` / `build` pass.

## Next steps (Milestone 8 — polished renderer)

- Visual pass on the renderer: responsive layout polish, loading/skeleton states,
  print-friendly styles, empty/error states everywhere.
- Source trace drawer and assumption drawer as proper overlays.
- Then Milestone 9: publish/unpublish, unguessable share slugs, and the public read-only
  `/share/[slug]` route.
