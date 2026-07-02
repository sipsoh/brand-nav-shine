# The Picxify data engine

What the ingestion engine detects and guarantees. Every rule below is locked in
by a fixture in `packages/sample-data/complex/` that the eval harness
(`apps/api/evals/run_evals.py`) runs end-to-end, plus unit tests in
`apps/api/tests/test_messy_structures.py`. **Robustness only ratchets up:** a
new mess we learn to read becomes a fixture before the fix ships.

## Principles

1. **Code calculates.** No LLM ever computes a number; structure detection is
   deterministic and testable.
2. **Every decision is a visible finding.** Skipped a banner, split a sheet,
   reshaped a pivot, excluded a totals row — each is recorded and surfaces in
   "Sources & assumptions".
3. **Never double-count.** Aggressive about capturing data, conservative about
   combining it.

## Structure detection (Excel)

Sheets are read as raw cell grids (`header=None`) and reconstructed:

- **Banner rows** (report titles, export stamps) above the table are skipped.
- **The real header row is detected** — row 1 is never assumed. Crosstab
  headers made of years/months ("Region | 2024 | 2025 | 2026") are recognized.
- **Stacked merged-cell headers** flatten to single names, up to three levels
  ("Region | 2025 H1 Revenue | …"). A single blank header cell is NOT treated
  as a merged span — string-heavy data rows are never eaten as header labels.
- **Blank header cells** are named (`column_3`); duplicates deduped
  (`Cost_2`).
- **Headerless blocks** get auto-named columns and a warning finding.
- **Scattered tables**: stacked blocks (≥2 blank rows apart), side-by-side
  tables (blank-column gaps), and a *single* blank row followed by a
  header-shaped row all split into separate tables ("Sheet (block 2)").
  Grouped reports with blank spacer rows between data groups stay one table —
  the row after the blank must look like a header (labels only, no
  currency/date/number strings) to trigger a split.
- **Tiny loose-cell blocks** are skipped with a note.
- **Same-schema sheet union**: when ≥3 sheets share an identical column
  signature (per-month/per-region tabs), a combined table with a
  `Source Sheet` column is added as an extra candidate. **Overlap guard:** if
  the sheets share rows (a master sheet plus filtered category views), no
  union is built — that would double-count. Disjoint slices combine; table
  scoring decides what the dashboard is built from.

## Reshaping

- **Wide period columns unpivot to long form** ("Region | Jan 2026 … Dec
  2026", quarters, ISO months, years) so trends and MoM math work on
  pivot-shaped exports. The value column is named from the sheet
  ("Revenue by Region" → `Revenue`).
- **Month-only headers** (no year anywhere) still unpivot; periods stay as
  month-name strings — the engine never invents dates.

## Value normalization

- Currency strings (`$1,234.56`), accounting negatives (`($500)`), SAP-style
  trailing minus (`1.234,56-`), unicode minus.
- European formats: dot/space thousands + comma decimals (`1 234,56`),
  day-first dates (`13.02.2026`), semicolon CSVs.
- Percent strings stored uniformly as 0–1 fractions ("45%" → 0.45) so percent
  formatting can always multiply by 100.
- Placeholder null tokens (`N/A`, `-`, `—`, `none`, `#REF!`, …) become real
  nulls so numeric columns still coerce.
- Repeated header lines inside the data (page-break exports) are dropped.
- Totals/subtotal footer rows are excluded from analysis.
- Text encodings: UTF-8, UTF-8-BOM, UTF-16, cp1252, latin-1. Legacy `.xls`
  supported.

## Semantics

- Non-English money labels map to revenue/cost (Umsatz, ventas, ingresos,
  chiffre, receita, fatturato, omzet; kosten, costes, custos, costi;
  salary/payroll/wage → cost).
- Any column whose values carry a currency symbol is a **money measure** even
  with an unrecognized name — semantic `money` is neutral: it counts as a
  strong measure but never implies "sales" for use-case detection.
- Durations and ratings are averaged, never summed; without a strong measure,
  analytics count records instead of summing arbitrary numbers.

## Known gaps (the current frontier)

- No OCR path: numbers living in images/PDF scans.
- Tables nested side-by-side within a single column gap of each other.
- Month-only pivots chart as ordered categories, not a true dated trend.
- Unit inference for bare durations (seconds vs minutes) — surfaced raw with
  the column name, never guessed.
