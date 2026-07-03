# Picxify Dashboard Design System

Built on a design-system-agnostic data-viz method: form first, color by job,
palettes validated by script (never by eye), fixed mark specs, ink-token text.
Charts are **read by people and executed by code** — the same discipline as our
source-trace rule, applied to pixels.

## Tokens — chrome & ink (light / dark)

| Role | Light | Dark |
|---|---|---|
| Page plane | `#f9f9f7` | `#0d0d0d` |
| Chart surface (cards) | `#fcfcfb` | `#1a1a19` |
| Border (hairline ring) | `rgba(11,11,11,0.10)` | `rgba(255,255,255,0.10)` |
| Primary ink | `#0b0b0b` | `#ffffff` |
| Secondary ink | `#52514e` | `#c3c2b7` |
| Muted ink (axis/labels) | `#898781` | `#898781` |
| Gridline (hairline, solid) | `#e1e0d9` | `#2c2c2a` |
| Baseline / axis | `#c3c2b7` | `#383835` |
| Delta good (success text) | `#006300` | `#0ca30c` |
| Delta bad | `#d03b3b` | `#d03b3b` |

Product brand chrome (the evergreen hero band, nav accents) is UI, not data —
data marks never borrow brand colors and vice versa.

**Status palette** (fixed — never themed, never a categorical slot; same hex
both modes since each already clears 3:1 on both chart surfaces):

```
good #0ca30c   warning #fab219   serious #ec835a   critical #d03b3b
```

A status color never carries meaning alone — pair it with an icon or label
(`warning` is only 1.79:1 on the light surface by design; the label is the
mitigation, same relief rule as the categorical palette below).

## Palettes (validated — do not eyeball changes)

**Categorical** (identity; fixed slot order, never cycled; 8-slot ceiling —
a 9th series folds into "Other"). Both modes are *selected* steps, not an
automatic flip — the dark column is the same eight hues stepped for the dark
surface:

| Slot | Light | Dark |
|---|---|---|
| 1 (blue) | `#2a78d6` | `#3987e5` |
| 2 (aqua) | `#1baf7a` | `#199e70` |
| 3 (yellow) | `#eda100` | `#c98500` |
| 4 (green) | `#008300` | `#008300` |
| 5 (violet) | `#4a3aa7` | `#9085e9` |
| 6 (red) | `#e34948` | `#e66767` |
| 7 (magenta) | `#e87ba4` | `#d55181` |
| 8 (orange) | `#eb6834` | `#d95926` |

Light-surface: worst adjacent CVD ΔE 24.2 (target ≥ 12) — PASS. Three slots
sit below 3:1 contrast (aqua, yellow, magenta): the **relief rule** applies —
legends + tooltips + bar-tip labels are the mitigation and must stay.
Dark-surface: worst adjacent CVD ΔE 10.3 — WARN (floor band, legal with the
same relief rule); all eight clear 3:1.

**Ordinal ramp** (ordered stages — funnels, tiers; single blue hue, light→dark;
darkest = largest):

| Position | Light | Dark |
|---|---|---|
| 1 (lightest) | `#86b6ef` | `#cde2fb` |
| 2 | `#5598e7` | `#9ec5f4` |
| 3 | `#2a78d6` | `#3987e5` |
| 4 | `#1c5cab` | `#256abf` |
| 5 (darkest) | `#104281` | `#184f95` |

The dark ramp stops at sequential step 600 (`#184f95`, 2.15:1 vs the dark
surface) — one step further (`#104281`/`#0d366b`) fails the light-end-contrast
and adjacent-ΔL checks. Position 3's dark target intentionally matches the
categorical slot-1 dark blue (`#3987e5`): the light source hex (`#2a78d6`) is
already shared between the two roles (the ordinal ramp is built on the same
blue hue as categorical slot 1), so the dark target must be too.

Re-validate after any change (from the dataviz skill directory):

```
node scripts/validate_palette.js "<hex,...>" --mode light
node scripts/validate_palette.js "<hex,...>" --mode dark
node scripts/validate_palette.js "<hex,...>" --ordinal --mode light
node scripts/validate_palette.js "<hex,...>" --ordinal --mode dark
```

## Form rules (what chart for what job)

- Magnitude across nominal categories → **single-hue horizontal bar** (slot 1),
  values at bar tips. Never a hue per bar; never darker-where-bigger.
- Trend over time → line; split-by-dimension → stacked bar/area, ≤ 6 series
  then "Other".
- Ordered stages → funnel on the ordinal ramp — **only** for true pipeline
  semantics (`stage`, not `status`) whose counts decline like a flow (second
  stage ≥ 25% of the first). Status columns (Open/Closed/Pending) and
  one-value-dominates distributions degrade to the horizontal bar: the planner
  guard is `_funnel_reads_as_flow` in `dashboard_planner.py`.
- Part-to-whole *at a glance* → donut, ≤ 6 segments + "Other" (never for
  comparing close values — that's a bar).
- A single number → **stat tile**, not a chart. One hero figure per view.
- **Never dual-axis.** Two measures of different scale → two charts.

## Mark specs (fixed)

- Bars ≤ 24px thick; 4px rounded **data-end**, square at the baseline.
- Stacked segments and touching marks separated by a **surface gap** (border in
  `#fcfcfb`), never a stroke.
- Lines 2px, round cap/join; markers ≥ 8px with a **2px surface ring**.
- Area fills at ~10% opacity.
- Grid/axes: solid hairlines, one step off the surface, recessive. Never dashed.
- Legend present for ≥ 2 series (icon: 9px circle); none for a single series.
- Labels selective: bar tips yes, a number on every point never. On horizontal
  bars the tip labels carry the exact values, so the **value axis stays silent**
  (no tick labels, no gridlines) and long category names ellipsize at 200px.
- **Text wears ink tokens, never series colors.**

## Stat tile (KPI) contract

`label` (sentence case, secondary ink, 12px) · `value` (32px **semibold**,
proportional figures — never tabular-nums, never extrabold display styling) ·
`delta` (arrow + changeLabel; success/danger ink). No decorative stripes or
gradients — the number is the design.

## Layout

- Dark evergreen hero band (brand chrome): eyebrow → title → subtitle → trust
  bar; overlay actions (Insights / Next actions / Sources) as pills.
- KPI row overlaps the hero (4-up desktop).
- Numbered chart sections ("01 Performance over time", "02 Breakdowns") with a
  fading rule; time charts full-width (380px), breakdown grids uniform
  (1 → full, 3 → thirds, else halves).
- Insights/assumptions/actions live in overlays, not page real estate.

## Dark mode (wired)

Charts are generated server-side once, in light-mode hex (`chart_builder.py`),
and the spec stays pure light-mode JSON — dark mode is a presentational
transform applied at render time, the same pattern `EChartsChart` already uses
for compact axis/tooltip formatting:

- `apps/web/lib/chart-theme.ts` holds the light→dark hex map for every chrome,
  categorical, and ordinal token above, plus explicit dark tooltip styling
  (ECharts' tooltip has no ambient theme, so it needs its own background/
  border/text colors set per mode).
- `apps/web/lib/use-color-scheme.ts` tracks `prefers-color-scheme` so canvas
  charts (which can't read CSS) know which map to apply.
- `EChartsChart` runs `applyChartTheme(withCompactFormatting(option), scheme)`
  before `setOption`.
- UI chrome (KPI cards, chart panels, modals, panels) uses Tailwind `dark:`
  variants directly against the same token values, and `app/globals.css` sets
  the page-plane/foreground CSS variables under the same media query.

## Known gaps (deliberate, tracked)

- **Texture channel** (CVD/print/forced-colors fill): deferred.
- Table-view twin for every chart: partially covered by source-trace drawers;
  full table view deferred to the analyst-audience work (the schema's
  `data_table` widget type has no data payload defined yet).
