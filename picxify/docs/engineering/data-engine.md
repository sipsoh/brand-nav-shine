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

- **Units rows** ("USD" / "count" / "%") under the header are skipped.
- **Transposed exports** (fields as rows, records as columns) are detected by
  row-wise type homogeneity and flipped, conservatively (≤8 fields).
- **Merged group labels** (a category written once, blank for its group rows)
  are carried down to every row.
- **Blank leading label columns** (the accounting-export shape) get the human
  default name `Category` instead of `column_1`.
- **Header cells with embedded newlines** (Alt+Enter typed headers like
  "Q1\nRevenue" as one cell) collapse to a single space, in both Excel and
  quoted CSV headers.
- **Uncalculated formula cells** — a live formula with no cached result
  (common when a report-generation library writes formulas but never runs a
  calculation engine) reads as silently blank via pandas' default
  `data_only=True`. Detected by comparing a `data_only=False` load's formula
  text against the already-loaded grid; surfaced as an honest warning
  finding naming the sheet and cell count, rather than an unexplained gap.

## Totals never double-count

- Total/subtotal rows are excluded **anywhere** in the table (financial
  statements carry "Total Income" mid-table), plus derived "Net Income/Profit/
  Loss" lines.
- "Total"/"Grand Total" **columns** beside period columns are dropped before
  unpivoting a crosstab.
- The multi-sheet union's overlap guard (below) refuses to combine sheets that
  share rows.

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
- ISO currency codes (`1,234.56 USD`, `EUR 999`), Swiss apostrophe thousands
  (`1'234.56`), and compact magnitude suffixes (`$1.2M`, `3.4k`, `2B`).
- Numeric date encodings on date-named columns: Excel serials (`46023` →
  2026-01-01) and compact `YYYYMMDD` integers.
- European formats: dot/space thousands + comma decimals (`1 234,56`),
  day-first dates (`13.02.2026`), semicolon CSVs; pipe- and tab-delimited
  text files; quoted fields with embedded newlines; title/metadata preamble
  lines above CSV headers.
- Percent strings stored uniformly as 0–1 fractions ("45%" → 0.45) so percent
  formatting can always multiply by 100. Native numeric columns (never a
  text string — a BI-tool or database export) get the same treatment when
  the name is unambiguously percent-shaped (`%`, `percent`, `pct` — never
  bare `rate`/`ratio`, which are ambiguous with money/other multiples):
  whole-number percents (`15` meaning 15%) are divided by 100, values
  already stored as 0–1 fractions are left alone, either way tagged with
  the `percent` unit so display always shows "15%" instead of a bare `15`
  or `0.15`.
- Placeholder null tokens (`N/A`, `-`, `—`, `none`, `#REF!`, …) become real
  nulls so numeric columns still coerce.
- Repeated header lines inside the data (page-break exports) are dropped.
- Totals/subtotal footer rows are excluded from analysis.
- Text encodings: UTF-8, UTF-8-BOM, UTF-16, cp1252, latin-1. Legacy `.xls`
  supported.

## Semantics

- Non-English money labels map to revenue/cost (Umsatz, ventas, ingresos,
  chiffre, receita, fatturato, omzet; kosten, costes, custos, costi;
  salary/payroll/wage → cost). Bank-statement columns: credit/deposit →
  revenue-side, debit/withdrawal → cost-side.
- OHLC guard: `Open` beside High/Low/Close is a price, never email-open
  engagement — and prices are never summed into a headline.
- Any column whose values carry a currency symbol is a **money measure** even
  with an unrecognized name — semantic `money` is neutral: it counts as a
  strong measure but never implies "sales" for use-case detection.
- Durations and ratings are averaged, never summed; when nothing at all is
  summable, analytics count records instead of summing arbitrary numbers.
- **Column coverage — keywords rank, they never gate.** Every numeric measure
  gets a computed total and dashboard representation unless summing it is
  provably meaningless (rates/ratios/percents/per-unit prices are levels, not
  amounts; ratings/durations average; OHLC candles are prices; calendar-year
  columns are ordinals; all-null columns are skipped). Recognized semantics
  decide headline ORDER — tier first, then total magnitude — so a report's
  real headline surfaces even when no keyword rule knows its name
  ('Total AR' on an AR-aging export). Sibling column groups (≥3 summable
  columns sharing a name token: '0-30 Days'…'180+ Days', 'Q1 Revenue'…'Q4
  Revenue') are detected structurally and charted as totals-per-column bars
  in original column order.

## PDF ingestion

- **Digital PDFs**: each page's tables extract from the text layer via
  pdfplumber, converted into the same raw-grid shape as an Excel sheet and
  run through the identical `extract_tables()` structure detector — banners,
  header detection, and merged headers all apply for free.
- **Multi-page tables**: pdfplumber only sees one page at a time, so a long
  table becomes several page-labeled RawTables; they recombine via the same
  union mechanism as per-sheet Excel tabs, but at a lower bar (≥2 pages, not
  ≥3) since a page break is an extraction artifact, not a deliberate split.
- **Scanned pages (OCR fallback)**: a page with no text layer at all is
  rendered to an image and read with tesseract. Rows are reconstructed by
  clustering word y-positions (not tesseract's own block/line grouping,
  which splits wide-gutter tables into separate "blocks" per column);
  columns by clustering word x-positions on gap size. OCR-derived tables
  always carry a heavy confidence penalty (see below) — there is no ground
  truth to check OCR against, so every OCR dashboard is flagged for review
  even when the extraction looks clean.

## Multi-file datasets & relational joins

- A dataset can be built from **several uploaded files at once** (e.g.
  `orders.csv` + `customers.csv`), not just one. Each file's tables merge
  into one candidate pool before structure detection continues exactly as
  for a single file.
- **Relational join detection**: when one table's column is a near-unique
  key (≥95% unique) and another table's matching-named column mostly
  contains those same values (≥80% containment), the fact table gets a join
  candidate enriched with the dimension's columns — a left join that can
  never fan out (the dimension is deduplicated on its key first, and the
  result's row count must exactly match the fact table's).
- **Cardinality guard**: the "dimension" side must have meaningfully fewer
  rows than the fact side (≤50%). This is what stops a *row-aligned
  companion sheet* (a pivot-helper tab built alongside the main sheet, same
  row count, a coincidentally-unique column) from getting joined in as if it
  were a real dimension — a real customer workbook hit exactly this failure
  mode during testing (a 'NEW DATA SHEET' helper tab almost joined into
  'Tickets') before the guard was added.
- Both union and join candidates are pure *additions* to the candidate pool;
  the original tables are always kept, and table scoring (quality × named
  columns × size, with a small bonus for more columns so a genuine
  enrichment can win a tie) picks the dashboard's base table.

## Structure-detection confidence

Every table gets a `structureConfidence` score (0–1) computed from which
structural findings fired on it — no header found, an inferred transpose, a
sheet/page union, a relational join, OCR extraction — each with its own
penalty weight (`app/services/confidence.py`). This is distinct from data
*quality* (nulls, duplicate rows): it answers "how much did the parser have
to guess," not "how clean are the values." Below the threshold (0.6), the
dashboard shows a visible amber banner naming the table and linking to
"Sources & assumptions," and a matching low-confidence assumption is
recorded automatically.

## The feedback loop: corrections become fixtures

When a user rejects an assumption or corrects a column's semantic type via
the assumptions API, that correction is real signal the engine guessed wrong
on that file's specific shape. `apps/api/scripts/promote_fixture.py` (backed
by `app/services/fixture_promotion.py`) pulls a dataset's source file(s) plus
a plain-English account of what was corrected, writes the files into
`packages/sample-data/complex/`, and prints a scaffolded `EXPECTATIONS`
entry for `evals/run_evals.py` — reviewed and finalized by an engineer, never
auto-committed. One customer's confusion becomes a permanent regression test.

## Known gaps (the current frontier)

- OCR quality depends on scan legibility; skewed/low-contrast scans degrade
  gracefully (fewer/no tables extracted) rather than producing garbage rows,
  but there's no image preprocessing (deskew, contrast normalization) yet.
- Tables nested side-by-side within a single column gap of each other.
- Month-only pivots chart as ordered categories, not a true dated trend.
- Unit inference for bare durations (seconds vs minutes) — surfaced raw with
  the column name, never guessed.
- Joins are limited to a single shared key column per table pair (no
  composite keys) and cap at 4 candidates per dataset.
