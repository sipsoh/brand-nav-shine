# Evals

Strategy per SETUP.md §18. For every sample dataset in `packages/sample-data/` we will maintain:

- expected use case
- expected key columns
- expected top 3 chart types
- prohibited claims
- expected data quality caveats

Automated checks (from Milestone 6 on):

- no insight without `sourceTrace`
- no numeric claim without a computed fact
- spec validates against `packages/schemas/dashboard_spec.schema.json`
- all referenced columns exist
- all querySpecs execute
- no chart has empty data unless intentional

Currently implemented: DashboardSpec schema validation tests in
`apps/api/tests/test_dashboard_spec_schema.py`.
