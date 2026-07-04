# The Coverage Contract

**Invariant: every column that survives parsing is represented on the
dashboard, or carries a machine-readable exclusion reason. There is no third
state.**

This is the product promise ("drop in messy data, get THE story — not a
story about one column"), enforced architecturally rather than achieved by
heuristic quality. Planner heuristics decide *how well* a column is shown
(a KPI beats a table row); the contract guarantees *that* it is shown.

## Why a contract, not smarter heuristics

The planner works by enumeration: rules list what to include. Enumeration
can be improved forever and never reaches a guarantee — every novel dataset
shape finds a new hole (real case: an AR-aging report lost its seven bucket
columns, Total AR, Prepayments, Property, and Entity ID across three
successive "fixes"). Inverting the burden — nothing may be *left out*
without a reason — is the only shape of the fix that holds for datasets
nobody has seen yet.

## The pieces

1. **Auditor stage** (`app/services/coverage.py`, runs after chart
   execution, before validation): walks the finished spec and accounts for
   every source column as one of:
   - `represented`: appears as a KPI fact column, chart measure, chart
     dimension, date axis, or text-theme source;
   - `excluded(reason)`: `all_null`, `constant`, `duplicate_identity_of:X`,
     `free_text_themed`, `lineage_metadata` — each reason is computed, never
     hand-waved.
   Anything unaccounted **self-heals**: the auditor appends it to the
   appendix data table and marks it `represented(table)`. The audit result
   (per-column ledger + coverage ratio) lands in `generation_metadata` and
   in the spec for rendering.
2. **Backstop widget**: the `data_table` widget type gets a real payload
   (column list + top rows by the primary measure, capped) so free-text and
   identity columns have somewhere honest to live. The web renderer renders
   it (today it silently drops the type).
3. **Corpus-wide enforcement**: the eval harness asserts the invariant on
   EVERY fixture — a universal check, not per-fixture expectations — so any
   engine change that drops a column anywhere fails CI.
4. **Visible trust**: the hero band shows "N/N columns represented"; the
   Sources & assumptions panel lists exclusions with their reasons.

## Non-goals

Coverage ≠ forcing every column into a chart. A rate is averaged, never
summed; free text is themed or tabled, never bar-charted; an identity code
duplicating a human label is excluded *with that reason on record*. Honest
representation, not decoration.
