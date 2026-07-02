"""Render a DashboardSpec to a standalone HTML file (ECharts via CDN).

Used by the eval harness to produce shareable previews of generated
dashboards without running the web app:

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
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #fafafa; color: #171717;
         font: 15px/1.55 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 40px 24px 80px; }
  h1 { font-size: 30px; margin: 0; letter-spacing: -0.02em; }
  .sub { color: #525252; margin-top: 6px; }
  .chips { margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }
  .chip { background: #eef2ff; color: #4338ca; border-radius: 999px;
          padding: 3px 12px; font-size: 12px; font-weight: 600; }
  .chip.gray { background: #f5f5f5; color: #525252; }
  .trust { color: #a3a3a3; font-size: 12px; margin-top: 12px; }
  h2 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em;
       color: #737373; margin: 40px 0 12px; }
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; }
  .card { background: #fff; border: 1px solid #e5e5e5; border-radius: 14px; padding: 18px 20px; }
  .kpi-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: #737373; }
  .kpi-value { font-size: 26px; font-weight: 700; margin-top: 4px; }
  .kpi-change { font-size: 12px; color: #a3a3a3; }
  .up { color: #16a34a; } .down { color: #dc2626; }
  .charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 14px; }
  .chart-title { font-weight: 600; font-size: 14px; margin-bottom: 8px; }
  .chart-box { height: 320px; }
  .insight { border-radius: 12px; border: 1px solid #e5e5e5; background: #fff;
             padding: 14px 18px; margin-bottom: 10px; }
  .insight.positive { border-color: #bbf7d0; background: #f0fdf4; }
  .insight.negative { border-color: #fecaca; background: #fef2f2; }
  .insight.warning { border-color: #fde68a; background: #fffbeb; }
  .insight b { display: block; margin-bottom: 2px; }
  .insight p { margin: 0; color: #525252; font-size: 14px; }
  details { margin-top: 8px; }
  summary { cursor: pointer; font-size: 12px; color: #a3a3a3; }
  .trace { font-size: 12px; color: #525252; background: #fafafa; border-radius: 8px;
           padding: 10px 12px; margin-top: 6px; }
  .exec { white-space: pre-wrap; }
  .action { display: flex; gap: 10px; align-items: baseline; background: #fff;
            border: 1px solid #e5e5e5; border-radius: 12px; padding: 12px 16px; margin-bottom: 8px; }
  .prio { font-size: 11px; font-weight: 700; border-radius: 999px; padding: 2px 10px; }
  .prio.high { background: #fef2f2; color: #b91c1c; }
  .prio.medium { background: #fffbeb; color: #b45309; }
  .prio.low { background: #f5f5f5; color: #525252; }
  ul.plain { margin: 6px 0 0; padding-left: 18px; color: #525252; font-size: 14px; }
  footer { margin-top: 56px; color: #a3a3a3; font-size: 12px; }
</style>
</head>
<body>
<div class="wrap" id="app"></div>
<script id="spec" type="application/json">__SPEC__</script>
<script>
const spec = JSON.parse(document.getElementById('spec').textContent);
const app = document.getElementById('app');
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};
const traceBlock = (trace) => {
  if (!trace) return document.createDocumentFragment();
  const details = el('details');
  details.appendChild(el('summary', null, 'View source'));
  const box = el('div', 'trace');
  box.textContent = 'Calculation: ' + trace.calculation +
    ' · Columns: ' + trace.columns.join(', ') +
    (trace.filters && trace.filters.length ? ' · Filters: ' + trace.filters.join('; ') : '') +
    ' · Rows: ' + trace.rowCount.toLocaleString() +
    ' · By: ' + (trace.generatedBy === 'code' ? 'deterministic code' : trace.generatedBy);
  details.appendChild(box);
  return details;
};

// Header
app.appendChild(el('h1', null, spec.dashboard.title));
app.appendChild(el('div', 'sub', spec.dashboard.subtitle));
const chips = el('div', 'chips');
chips.appendChild(el('span', 'chip', spec.dashboard.useCase.replace(/_/g, ' ')));
chips.appendChild(el('span', 'chip gray', 'for ' + spec.dashboard.audience));
app.appendChild(chips);
const rows = spec.dataSources.reduce((s, d) => s + d.rowCount, 0);
app.appendChild(el('div', 'trust',
  'Trust bar: ' + rows.toLocaleString() + ' rows analyzed · ' +
  spec.assumptions.length + ' assumption(s) · every widget carries a source trace'));

let chartIndex = 0;
const pendingCharts = [];
for (const section of spec.sections) {
  app.appendChild(el('h2', null, section.title));
  const kpis = section.widgets.filter(w => w.type === 'kpi');
  const charts = section.widgets.filter(w => w.type === 'chart');
  const others = section.widgets.filter(w => !['kpi', 'chart'].includes(w.type));

  for (const widget of others) {
    if (widget.type === 'text') {
      const card = el('div', 'card');
      card.appendChild(el('div', 'chart-title', widget.title));
      card.appendChild(el('div', 'exec', (widget.markdown || '').replace(/^- /gm, '• ')));
      app.appendChild(card);
    } else if (widget.type === 'insight_card' && widget.insight) {
      const insight = widget.insight;
      const card = el('div', 'insight ' + insight.severity);
      card.appendChild(el('b', null, insight.headline));
      card.appendChild(el('p', null, insight.detail));
      card.appendChild(traceBlock(insight.sourceTrace));
      app.appendChild(card);
    } else if (widget.type === 'assumption_panel' && spec.assumptions.length) {
      const card = el('div', 'card');
      card.appendChild(el('div', 'chart-title', 'Assumptions'));
      const list = el('ul', 'plain');
      for (const assumption of spec.assumptions) {
        list.appendChild(el('li', null,
          assumption.label + ' (' + assumption.status.replace('_', ' ') + ')'));
      }
      card.appendChild(list);
      app.appendChild(card);
    } else if (widget.type === 'source_panel') {
      const card = el('div', 'card');
      card.appendChild(el('div', 'chart-title', 'Data sources'));
      const list = el('ul', 'plain');
      for (const source of spec.dataSources) {
        list.appendChild(el('li', null, source.displayName + ' — ' +
          source.rowCount.toLocaleString() + ' rows, ' + source.columnCount + ' columns'));
      }
      card.appendChild(list);
      app.appendChild(card);
    }
  }

  if (kpis.length) {
    const grid = el('div', 'kpis');
    for (const widget of kpis) {
      const kpi = widget.kpi;
      const card = el('div', 'card');
      card.appendChild(el('div', 'kpi-label', kpi.label));
      const value = el('div', 'kpi-value',
        typeof kpi.value === 'number' ? kpi.value.toLocaleString() : String(kpi.value));
      if (kpi.direction === 'up') value.appendChild(el('span', 'up', ' ▲'));
      if (kpi.direction === 'down') value.appendChild(el('span', 'down', ' ▼'));
      card.appendChild(value);
      if (kpi.changeLabel) card.appendChild(el('div', 'kpi-change', kpi.changeLabel));
      card.appendChild(traceBlock(kpi.sourceTrace));
      grid.appendChild(card);
    }
    app.appendChild(grid);
  }

  if (charts.length) {
    const grid = el('div', 'charts');
    for (const widget of charts) {
      const card = el('div', 'card');
      card.appendChild(el('div', 'chart-title', widget.title));
      const box = el('div', 'chart-box');
      box.id = 'chart-' + chartIndex++;
      card.appendChild(box);
      card.appendChild(traceBlock(widget.chart.sourceTrace));
      grid.appendChild(card);
      pendingCharts.push([box.id, widget.chart.echartsOption]);
    }
    app.appendChild(grid);
  }
}

if (spec.actions.length) {
  app.appendChild(el('h2', null, 'Recommended next actions'));
  for (const action of spec.actions) {
    const row = el('div', 'action');
    row.appendChild(el('span', 'prio ' + action.priority, action.priority));
    const body = el('span');
    body.appendChild(el('b', null, action.label + ' '));
    body.appendChild(el('span', null, action.rationale));
    row.appendChild(body);
    app.appendChild(row);
  }
}
app.appendChild(el('footer', null,
  'Generated by Picxify · ' + spec.dashboard.generatedAt +
  ' · every number computed by deterministic code'));

for (const [id, option] of pendingCharts) {
  if (option && Object.keys(option).length) {
    echarts.init(document.getElementById(id)).setOption(option);
  }
}
window.addEventListener('resize', () => {
  for (const [id] of pendingCharts) {
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
