# Picxify Dashboard Design System

Built on a design-system-agnostic data-viz method: form first, color by job,
palettes validated by script (never by eye), fixed mark specs, ink-token text.
Charts are **read by people and executed by code** — the same discipline as our
source-trace rule, applied to pixels.

## Tokens — chrome & ink (light)

| Role | Value |
|---|---|
| Page plane | `#f9f9f7` |
| Chart surface (cards) | `#fcfcfb` |
| Border (hairline ring) | `rgba(11,11,11,0.10)` |
| Primary ink | `#0b0b0b` |
| Secondary ink | `#52514e` |
| Muted ink (axis/labels) | `#898781` |
| Gridline (hairline, solid) | `#e1e0d9` |
| Baseline / axis | `#c3c2b7` |
| Delta good (success text) | `#006300` |
| Delta bad | `#d03b3b` |

Product brand chrome (the evergreen hero band, nav accents) is UI, not data —
data marks never borrow brand colors and vice versa.

## Palettes (validated — do not eyeball changes)

**Categorical** (identity; fixed slot order, never cycled; 8-slot ceiling —
a 9th series folds into "Other"):

```
#2a78d6  #1baf7a  #eda100  #008300  #4a3aa7  #e34948  #e87ba4  #eb6834
```

Light-surface validation: worst adjacent CVD ΔE 24.2 (target ≥ 12) — PASS.
Three slots sit below 3:1 contrast (aqua, yellow, magenta): the **relief rule**
applies — legends + tooltips + bar-tip labels are the mitigation and must stay.

**Ordinal ramp** (ordered stages — funnels, tiers; single blue hue, light→dark;
darkest = largest):

```
#86b6ef  #5598e7  #2a78d6  #1c5cab  #104281
```

Re-validate after any change (from the dataviz skill directory):

```
node scripts/validate_palette.js "<hex,...>" --mode light
node scripts/validate_palette.js "<hex,...>" --ordinal --mode light
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

## Known gaps (deliberate, tracked)

- **Dark mode**: must be *selected* steps from the same ramps validated against
  the dark surface (`#1a1a19`) — not an automatic flip. Dark categorical steps
  are validated and documented in the dataviz reference; wiring deferred.
- **Texture channel** (CVD/print/forced-colors fill): deferred.
- Table-view twin for every chart: partially covered by source-trace drawers;
  full table view deferred to the analyst-audience work.
