"""Render a DashboardSpec to a standalone HTML file (ECharts via CDN).

Executive-style layout: dark hero band with title + KPI row, a 12-column chart
grid driven by widget `size`, and insights / assumptions / next actions in
overlay panels so they never consume dashboard real estate.

    python -m evals.render_spec_html <output_dir>
"""

import html
import json
import sys
from pathlib import Path

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ — Picxify</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #f6f6f2; --card: #ffffff; --line: #e8e8e0; --ink: #101613;
    --muted: #5f6c64; --faint: #96a29a; --accent: #0d9668; --accent2: #34d399;
    --accent-soft: #e7f6ef; --hero1: #0a1410; --hero2: #10352a;
    --radius: 18px; --shadow: 0 1px 2px rgba(12,20,16,.04), 0 8px 24px rgba(12,20,16,.06);
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink);
         font-family: Inter, -apple-system, "Segoe UI", sans-serif; font-size: 14px; }

  /* Top bar */
  .topbar { background: rgba(255,255,255,.85); backdrop-filter: blur(8px);
            border-bottom: 1px solid var(--line); position: sticky; top: 0; z-index: 20; }
  .topbar-in { max-width: 1240px; margin: 0 auto; padding: 12px 28px;
               display: flex; align-items: center; gap: 22px; }
  .logo { font-weight: 800; letter-spacing: -.02em; font-size: 16px;
          background: linear-gradient(90deg, var(--accent), var(--accent2));
          -webkit-background-clip: text; background-clip: text; color: transparent; }
  .topnav { display: flex; gap: 4px; }
  .topnav span { padding: 6px 14px; border-radius: 999px; color: var(--muted);
                 font-weight: 500; font-size: 13px; }
  .topnav span.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
  .topbar .spacer { flex: 1; }
  .pillbtn { border: 1px solid var(--line); background: var(--card); border-radius: 999px;
             padding: 7px 16px; font: inherit; font-size: 13px; font-weight: 600;
             color: var(--ink); cursor: pointer; }
  .pillbtn:hover { border-color: #bccdc2; }
  .pillbtn .n { display: inline-block; min-width: 18px; text-align: center; margin-left: 6px;
                background: var(--accent-soft); color: var(--accent); border-radius: 999px;
                font-size: 11px; padding: 1px 5px; }

  /* Hero */
  .hero { background: radial-gradient(1100px 480px at 88% -12%, rgba(52,211,153,.35) 0%, transparent 60%),
                       radial-gradient(700px 380px at 8% 110%, rgba(163,230,53,.14) 0%, transparent 60%),
                       linear-gradient(135deg, var(--hero1), var(--hero2));
          color: #fff; padding: 42px 0 88px; }
  .hero-in { max-width: 1240px; margin: 0 auto; padding: 0 28px; }
  .crumbs { font-size: 12px; color: #6ee7b7; font-weight: 600;
            text-transform: uppercase; letter-spacing: .12em; }
  h1 { font-size: 34px; font-weight: 800; letter-spacing: -.03em; margin: 10px 0 6px; }
  .sub { color: #a7d9c4; max-width: 720px; }
  .meta { margin-top: 14px; display: flex; gap: 14px; flex-wrap: wrap;
          color: #7fb59d; font-size: 12.5px; }
  .meta b { color: #d1fae5; font-weight: 600; }

  .sheet { max-width: 1240px; margin: -56px auto 0; padding: 0 28px 90px; }

  /* KPI row */
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(215px, 1fr)); gap: 16px; }
  .kpi { background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
         box-shadow: var(--shadow); padding: 20px 22px; position: relative; overflow: hidden; }
  .kpi::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 4px;
                 background: linear-gradient(180deg, var(--accent), #a3e635); }
  .kpi-label { font-size: 11px; font-weight: 700; letter-spacing: .09em;
               text-transform: uppercase; color: var(--faint); }
  .kpi-value { font-size: 30px; font-weight: 800; letter-spacing: -.02em; margin-top: 8px; }
  .kpi-change { font-size: 12px; color: var(--faint); margin-top: 2px; }
  .up { color: #10b981; } .down { color: #ef4444; }
  .src { position: absolute; top: 14px; right: 14px; border: 0; background: transparent;
         color: #c3c6d9; cursor: pointer; font-size: 14px; padding: 2px; }
  .src:hover { color: var(--accent); }

  /* Exec summary strip */
  .exec { margin-top: 16px; background: linear-gradient(90deg, #e9f7f0, #f3f9e8);
          border: 1px solid #d9eede; border-radius: var(--radius); padding: 16px 22px;
          display: flex; gap: 14px; align-items: baseline; }
  .exec .tag { font-size: 11px; font-weight: 800; letter-spacing: .1em; color: var(--accent);
               text-transform: uppercase; white-space: nowrap; }
  .exec .lines { color: #3f4c45; font-size: 13.5px; }

  /* Chart sections */
  .section-head { margin: 40px 0 14px; display: flex; align-items: baseline; gap: 14px; }
  .section-eyebrow { font-size: 11px; font-weight: 800; letter-spacing: .14em;
                     text-transform: uppercase; color: var(--accent); white-space: nowrap; }
  .section-title { font-size: 20px; font-weight: 800; letter-spacing: -.02em; white-space: nowrap; }
  .section-rule { flex: 1; height: 1px; background: linear-gradient(90deg, var(--line), transparent); }
  .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px; }
  .panel { background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
           box-shadow: var(--shadow); padding: 20px 22px; position: relative; }
  .span-12 { grid-column: span 12; } .span-8 { grid-column: span 8; }
  .span-6 { grid-column: span 6; } .span-4 { grid-column: span 4; }
  @media (max-width: 900px) { .grid > * { grid-column: span 12 !important; } }
  .panel-title { font-weight: 700; font-size: 14.5px; letter-spacing: -.01em; padding-right: 30px; }
  .chart-box { height: 310px; margin-top: 10px; }
  .span-12 .chart-box { height: 380px; }

  /* Overlay */
  .overlay { position: fixed; inset: 0; background: rgba(15,18,34,.45);
             backdrop-filter: blur(3px); display: none; z-index: 50; }
  .overlay.open { display: flex; align-items: flex-start; justify-content: center; }
  .sheet-modal { background: var(--card); border-radius: 20px; box-shadow: var(--shadow);
                 width: min(680px, calc(100vw - 32px)); max-height: 82vh; overflow: auto;
                 margin-top: 8vh; padding: 26px 30px; }
  .sheet-modal h3 { margin: 0 0 4px; font-size: 19px; letter-spacing: -.02em; }
  .sheet-modal .hint { color: var(--faint); font-size: 12.5px; margin-bottom: 16px; }
  .close { float: right; border: 0; background: #f1f2f8; border-radius: 999px;
           width: 30px; height: 30px; cursor: pointer; font-size: 14px; color: var(--muted); }
  .insight { border: 1px solid var(--line); border-left-width: 4px; border-radius: 12px;
             padding: 13px 16px; margin-bottom: 10px; }
  .insight.positive { border-left-color: #10b981; } .insight.negative { border-left-color: #ef4444; }
  .insight.warning { border-left-color: #f59e0b; } .insight.neutral { border-left-color: #a5b4fc; }
  .insight b { display: block; font-size: 13.5px; }
  .insight p { margin: 3px 0 0; color: var(--muted); font-size: 13px; }
  details { margin-top: 6px; } summary { cursor: pointer; font-size: 11.5px; color: var(--faint); }
  .trace { font-size: 12px; color: var(--muted); background: #f7f8fc; border-radius: 8px;
           padding: 9px 12px; margin-top: 6px; }
  .action { display: flex; gap: 10px; align-items: baseline; border: 1px solid var(--line);
            border-radius: 12px; padding: 11px 14px; margin-bottom: 8px; }
  .prio { font-size: 10.5px; font-weight: 800; border-radius: 999px; padding: 2px 9px;
          text-transform: uppercase; letter-spacing: .06em; }
  .prio.high { background: #fef2f2; color: #b91c1c; }
  .prio.medium { background: #fffbeb; color: #b45309; }
  .prio.low { background: #f1f2f8; color: var(--muted); }
  ul.plain { margin: 0; padding-left: 18px; color: var(--muted); font-size: 13px; }
  ul.plain li { margin-bottom: 6px; }
  footer { text-align: center; color: var(--faint); font-size: 12px; margin-top: 48px; }
</style>
</head>
<body>
<div class="topbar"><div class="topbar-in">
  <span class="logo">Picxify</span>
  <nav class="topnav">
    <span>Home</span><span>Upload</span><span class="active">Dashboards</span><span>Settings</span>
  </nav>
  <span class="spacer"></span>
  <button class="pillbtn" data-open="insights">Insights<span class="n" id="n-insights"></span></button>
  <button class="pillbtn" data-open="actions">Next actions<span class="n" id="n-actions"></span></button>
  <button class="pillbtn" data-open="sources">Sources &amp; assumptions</button>
</div></div>

<div class="hero"><div class="hero-in" id="hero"></div></div>
<div class="sheet" id="sheet"></div>

<div class="overlay" id="ov-insights"><div class="sheet-modal">
  <button class="close" data-close>✕</button><h3>Insights</h3>
  <div class="hint">Every number below was computed by deterministic code.</div>
  <div id="insights-body"></div>
</div></div>
<div class="overlay" id="ov-actions"><div class="sheet-modal">
  <button class="close" data-close>✕</button><h3>Recommended next actions</h3>
  <div class="hint">Derived from the computed insights.</div>
  <div id="actions-body"></div>
</div></div>
<div class="overlay" id="ov-sources"><div class="sheet-modal">
  <button class="close" data-close>✕</button><h3>Sources &amp; assumptions</h3>
  <div class="hint">What this dashboard was built from, and what Picxify inferred.</div>
  <div id="sources-body"></div>
</div></div>
<div class="overlay" id="ov-trace"><div class="sheet-modal">
  <button class="close" data-close>✕</button><h3>How this was calculated</h3>
  <div class="hint" id="trace-title"></div>
  <div class="trace" id="trace-body"></div>
</div></div>

<script id="spec" type="application/json">__SPEC__</script>
<script>
const spec = JSON.parse(document.getElementById('spec').textContent);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};
const fmtTrace = (trace) =>
  'Calculation: ' + trace.calculation +
  '\\nColumns: ' + trace.columns.join(', ') +
  (trace.filters && trace.filters.length ? '\\nFilters: ' + trace.filters.join('; ') : '') +
  '\\nRows included: ' + trace.rowCount.toLocaleString() +
  '\\nGenerated by: ' + (trace.generatedBy === 'code' ? 'deterministic code' : trace.generatedBy);
const srcButton = (title, trace) => {
  const button = el('button', 'src', '⌕');
  button.title = 'View source';
  button.onclick = () => {
    document.getElementById('trace-title').textContent = title;
    const body = document.getElementById('trace-body');
    body.textContent = fmtTrace(trace);
    body.style.whiteSpace = 'pre-wrap';
    document.getElementById('ov-trace').classList.add('open');
  };
  return button;
};

// ---- hero ----
const hero = document.getElementById('hero');
hero.appendChild(el('div', 'crumbs',
  spec.dashboard.useCase.replace(/_/g, ' ') + ' · for ' + spec.dashboard.audience));
hero.appendChild(el('h1', null, spec.dashboard.title));
hero.appendChild(el('div', 'sub', spec.dashboard.subtitle));
const rows = spec.dataSources.reduce((sum, source) => sum + source.rowCount, 0);
const meta = el('div', 'meta');
const addMeta = (label, value) => {
  const item = el('span');
  item.appendChild(el('b', null, value));
  item.appendChild(document.createTextNode(' ' + label));
  meta.appendChild(item);
};
addMeta('rows analyzed', rows.toLocaleString());
addMeta('assumptions', String(spec.assumptions.length));
addMeta('· every widget source-traced', '');
hero.appendChild(meta);

// ---- collect widgets ----
const kpis = [], insightsInline = [], chartSections = [];
let execText = null;
for (const section of spec.sections) {
  const sectionCharts = [];
  for (const widget of section.widgets) {
    if (widget.type === 'kpi') kpis.push(widget);
    else if (widget.type === 'chart') sectionCharts.push(widget);
    else if (widget.type === 'text' && !execText) execText = widget;
    else if (widget.type === 'insight_card' && widget.insight) insightsInline.push(widget.insight);
  }
  if (sectionCharts.length) chartSections.push({ title: section.title, charts: sectionCharts });
}
const allInsights = spec.insights.length ? spec.insights : insightsInline;

// ---- KPI row ----
const sheet = document.getElementById('sheet');
const kpiGrid = el('div', 'kpis');
for (const widget of kpis) {
  const kpi = widget.kpi;
  const card = el('div', 'kpi');
  if (kpi.sourceTrace) card.appendChild(srcButton(kpi.label, kpi.sourceTrace));
  card.appendChild(el('div', 'kpi-label', kpi.label));
  const value = el('div', 'kpi-value',
    typeof kpi.value === 'number' ? kpi.value.toLocaleString() : String(kpi.value));
  if (kpi.direction === 'up') value.appendChild(el('span', 'up', ' ▲'));
  if (kpi.direction === 'down') value.appendChild(el('span', 'down', ' ▼'));
  card.appendChild(value);
  if (kpi.changeLabel) card.appendChild(el('div', 'kpi-change', kpi.changeLabel));
  kpiGrid.appendChild(card);
}
sheet.appendChild(kpiGrid);

// ---- exec summary strip ----
if (execText && execText.markdown) {
  const strip = el('div', 'exec');
  strip.appendChild(el('span', 'tag', 'Summary'));
  strip.appendChild(el('span', 'lines',
    execText.markdown.replace(/^- /gm, '').split('\\n').join('  ·  ')));
  sheet.appendChild(strip);
}

// ---- chart sections: header + uniform aligned grid ----
const pending = [];
let chartIndex = 0;
let sectionIndex = 0;
for (const chartSection of chartSections) {
  sectionIndex += 1;
  const head = el('div', 'section-head');
  head.appendChild(el('span', 'section-eyebrow', String(sectionIndex).padStart(2, '0')));
  head.appendChild(el('span', 'section-title', chartSection.title));
  head.appendChild(el('span', 'section-rule'));
  sheet.appendChild(head);

  // Full-width charts stack; the rest share a uniform span so rows align.
  const wide = chartSection.charts.filter(w => w.size === 'xl' || w.size === 'full');
  const rest = chartSection.charts.filter(w => !(w.size === 'xl' || w.size === 'full'));
  const restSpan = rest.length === 1 ? 'span-12'
    : rest.length % 3 === 0 ? 'span-4' : 'span-6';

  const grid = el('div', 'grid');
  const addPanel = (widget, span) => {
    const panel = el('div', 'panel ' + span);
    if (widget.chart.sourceTrace) {
      panel.appendChild(srcButton(widget.title, widget.chart.sourceTrace));
    }
    panel.appendChild(el('div', 'panel-title', widget.title));
    const box = el('div', 'chart-box');
    box.id = 'chart-' + chartIndex++;
    panel.appendChild(box);
    grid.appendChild(panel);
    pending.push([box.id, widget.chart.echartsOption]);
  };
  for (const widget of wide) addPanel(widget, 'span-12');
  for (const widget of rest) addPanel(widget, restSpan);
  sheet.appendChild(grid);
}
sheet.appendChild(el('footer', null,
  'Generated by Picxify · ' + spec.dashboard.generatedAt + ' · code calculates, AI narrates'));

// ---- overlays ----
document.getElementById('n-insights').textContent = allInsights.length;
document.getElementById('n-actions').textContent = spec.actions.length;
const insightsBody = document.getElementById('insights-body');
for (const insight of allInsights) {
  const card = el('div', 'insight ' + insight.severity);
  card.appendChild(el('b', null, insight.headline));
  card.appendChild(el('p', null, insight.detail));
  const details = el('details');
  details.appendChild(el('summary', null, 'View source'));
  const trace = el('div', 'trace', fmtTrace(insight.sourceTrace));
  trace.style.whiteSpace = 'pre-wrap';
  details.appendChild(trace);
  card.appendChild(details);
  insightsBody.appendChild(card);
}
const actionsBody = document.getElementById('actions-body');
for (const action of spec.actions) {
  const row = el('div', 'action');
  row.appendChild(el('span', 'prio ' + action.priority, action.priority));
  const body = el('span');
  body.appendChild(el('b', null, action.label + '  '));
  body.appendChild(el('span', null, action.rationale));
  row.appendChild(body);
  actionsBody.appendChild(row);
}
const sourcesBody = document.getElementById('sources-body');
sourcesBody.appendChild(el('h3', null, ''));
const sourceList = el('ul', 'plain');
for (const source of spec.dataSources) {
  sourceList.appendChild(el('li', null, source.displayName + ' — ' +
    source.rowCount.toLocaleString() + ' rows, ' + source.columnCount + ' columns'));
}
sourcesBody.appendChild(sourceList);
if (spec.assumptions.length) {
  const assumptionList = el('ul', 'plain');
  assumptionList.style.marginTop = '14px';
  for (const assumption of spec.assumptions) {
    assumptionList.appendChild(el('li', null,
      assumption.label + ' (' + assumption.status.replace('_', ' ') + ')'));
  }
  sourcesBody.appendChild(assumptionList);
}

for (const button of document.querySelectorAll('[data-open]')) {
  button.onclick = () =>
    document.getElementById('ov-' + button.dataset.open).classList.add('open');
}
for (const overlay of document.querySelectorAll('.overlay')) {
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay || event.target.hasAttribute('data-close')) {
      overlay.classList.remove('open');
    }
  });
}
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    for (const overlay of document.querySelectorAll('.overlay')) overlay.classList.remove('open');
  }
});

// ---- charts ----
for (const [id, option] of pending) {
  if (option && Object.keys(option).length) {
    echarts.init(document.getElementById(id)).setOption(option);
  }
}
window.addEventListener('resize', () => {
  for (const [id] of pending) {
    const chart = echarts.getInstanceByDom(document.getElementById(id));
    if (chart) chart.resize();
  }
});
</script>
</body>
</html>
"""


def render(spec: dict) -> str:
    return PAGE.replace("__TITLE__", html.escape(spec["dashboard"]["title"])).replace(
        "__SPEC__", json.dumps(spec).replace("</", "<\\/")
    )


def main() -> None:
    from evals.run_evals import EXPECTATIONS, FIXTURES, run_fixture

    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dashboard-previews")
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename in EXPECTATIONS:
        result = run_fixture(filename, (FIXTURES / filename).read_bytes())
        if "error" in result:
            print(f"skip {filename}: {result['error']}")
            continue
        target = out_dir / (filename.rsplit(".", 1)[0] + "_dashboard.html")
        target.write_text(render(result["spec"]))
        print("wrote", target)


if __name__ == "__main__":
    main()
