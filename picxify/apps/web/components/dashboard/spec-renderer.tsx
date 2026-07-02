"use client";

import { useEffect, useState } from "react";
import { EChartsChart } from "@/components/charts/echarts-chart";
import type {
  DashboardSpec,
  SourceTrace,
  SpecInsight,
  SpecWidget,
} from "@/lib/api-client";

type Overlay =
  | { kind: "none" }
  | { kind: "insights" }
  | { kind: "actions" }
  | { kind: "sources" }
  | { kind: "trace"; title: string; trace: SourceTrace };

/** Pure spec -> UI renderer, shared by the authenticated dashboard page and
 * the public share page. Needs no auth and makes no API calls. */
export function SpecRenderer({
  spec,
  extraHeroButtons,
}: {
  spec: DashboardSpec;
  extraHeroButtons?: React.ReactNode;
}) {
  const [overlay, setOverlay] = useState<Overlay>({ kind: "none" });

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOverlay({ kind: "none" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const totalRows = spec.dataSources.reduce((sum, source) => sum + source.rowCount, 0);

  const kpis: SpecWidget[] = [];
  const chartSections: { title: string; charts: SpecWidget[] }[] = [];
  const inlineInsights: SpecInsight[] = [];
  let execText: SpecWidget | null = null;
  for (const section of spec.sections) {
    const sectionCharts: SpecWidget[] = [];
    for (const widget of section.widgets) {
      if (widget.type === "kpi" && widget.kpi) kpis.push(widget);
      else if (widget.type === "chart" && widget.chart) sectionCharts.push(widget);
      else if (widget.type === "text" && !execText) execText = widget;
      else if (widget.type === "insight_card" && widget.insight)
        inlineInsights.push(widget.insight);
    }
    if (sectionCharts.length > 0) {
      chartSections.push({ title: section.title, charts: sectionCharts });
    }
  }
  const insights = spec.insights.length > 0 ? spec.insights : inlineInsights;
  const openTrace = (title: string, trace: SourceTrace) =>
    setOverlay({ kind: "trace", title, trace });

  return (
    <div className="-mx-6">
      {/* Hero band */}
      <div className="bg-gradient-to-br from-[#0a1410] via-[#0d2419] to-[#11362b] px-6 pb-24 pt-10 text-white">
        <div className="mx-auto max-w-7xl">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-300">
                {spec.dashboard.useCase.replace(/_/g, " ")} · for {spec.dashboard.audience}
              </p>
              <h1 className="mt-2 text-3xl font-extrabold tracking-tight sm:text-4xl">
                {spec.dashboard.title}
              </h1>
              <p className="mt-2 max-w-2xl text-emerald-100/70">{spec.dashboard.subtitle}</p>
              <p className="mt-4 text-xs text-emerald-200/60">
                <span className="font-semibold text-emerald-100">
                  {totalRows.toLocaleString()}
                </span>{" "}
                rows analyzed ·{" "}
                <span className="font-semibold text-emerald-100">{spec.assumptions.length}</span>{" "}
                assumption(s) · every widget source-traced
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <HeroButton onClick={() => setOverlay({ kind: "insights" })}>
                Insights <Count n={insights.length} />
              </HeroButton>
              <HeroButton onClick={() => setOverlay({ kind: "actions" })}>
                Next actions <Count n={spec.actions.length} />
              </HeroButton>
              <HeroButton onClick={() => setOverlay({ kind: "sources" })}>
                Sources &amp; assumptions
              </HeroButton>
              {extraHeroButtons}
            </div>
          </div>
        </div>
      </div>

      {/* Content sheet overlapping the hero */}
      <div className="mx-auto -mt-16 max-w-7xl px-6 pb-24">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {kpis.map((widget) => (
            <KpiCard key={widget.id} widget={widget} onTrace={openTrace} />
          ))}
        </div>

        {execText?.markdown && (
          <div className="mt-4 flex items-baseline gap-3 rounded-2xl border border-emerald-100 bg-gradient-to-r from-emerald-50 to-lime-50 px-6 py-4">
            <span className="text-[11px] font-extrabold uppercase tracking-widest text-emerald-700">
              Summary
            </span>
            <span className="text-sm text-slate-600">
              {execText.markdown.replace(/^- /gm, "").split("\n").join("  ·  ")}
            </span>
          </div>
        )}

        {chartSections.map((chartSection, index) => (
          <ChartSection
            key={chartSection.title + index}
            index={index + 1}
            title={chartSection.title}
            charts={chartSection.charts}
            onTrace={openTrace}
          />
        ))}

        <p className="mt-12 text-center text-xs text-neutral-400">
          Generated by Picxify · {spec.dashboard.generatedAt} · code calculates, AI narrates
        </p>
      </div>

      {overlay.kind !== "none" && (
        <Modal onClose={() => setOverlay({ kind: "none" })}>
          {overlay.kind === "insights" && <InsightsPanel insights={insights} />}
          {overlay.kind === "actions" && <ActionsPanel spec={spec} />}
          {overlay.kind === "sources" && <SourcesPanel spec={spec} />}
          {overlay.kind === "trace" && (
            <TracePanel title={overlay.title} trace={overlay.trace} />
          )}
        </Modal>
      )}
    </div>
  );
}

function HeroButton({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm font-semibold text-white backdrop-blur transition hover:bg-white/20"
    >
      {children}
    </button>
  );
}

function Count({ n }: { n: number }) {
  return (
    <span className="ml-1.5 rounded-full bg-white/20 px-2 py-0.5 text-xs font-bold">{n}</span>
  );
}

function TraceButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      title="View source"
      onClick={onClick}
      className="absolute right-4 top-4 text-neutral-300 transition hover:text-emerald-600"
    >
      ⌕
    </button>
  );
}

function KpiCard({
  widget,
  onTrace,
}: {
  widget: SpecWidget;
  onTrace: (title: string, trace: SourceTrace) => void;
}) {
  // Stat-tile contract: label / value (semibold, proportional figures) /
  // delta in success/danger ink. The number is the design — no decoration.
  const kpi = widget.kpi!;
  return (
    <div className="relative rounded-2xl border border-[rgba(11,11,11,0.10)] bg-[#fcfcfb] p-5 shadow-sm">
      {kpi.sourceTrace && (
        <TraceButton onClick={() => onTrace(kpi.label, kpi.sourceTrace!)} />
      )}
      <p className="text-xs font-medium text-[#52514e]">{kpi.label}</p>
      <p className="mt-1.5 text-3xl font-semibold tracking-[-0.01em] text-[#0b0b0b]">
        {typeof kpi.value === "number" ? kpi.value.toLocaleString() : kpi.value}
        {kpi.direction === "up" && <span className="ml-1 text-lg text-[#006300]">▲</span>}
        {kpi.direction === "down" && <span className="ml-1 text-lg text-[#d03b3b]">▼</span>}
      </p>
      {kpi.changeLabel && <p className="mt-0.5 text-xs text-[#898781]">{kpi.changeLabel}</p>}
    </div>
  );
}

function ChartSection({
  index,
  title,
  charts,
  onTrace,
}: {
  index: number;
  title: string;
  charts: SpecWidget[];
  onTrace: (title: string, trace: SourceTrace) => void;
}) {
  const isWide = (widget: SpecWidget) => widget.size === "xl" || widget.size === "full";
  const wide = charts.filter(isWide);
  const rest = charts.filter((widget) => !isWide(widget));
  // Uniform spans inside a section so rows stay aligned.
  const restSpan =
    rest.length === 1
      ? "col-span-12"
      : rest.length % 3 === 0
        ? "col-span-12 lg:col-span-4"
        : "col-span-12 lg:col-span-6";

  return (
    <section className="mt-10">
      <div className="mb-3.5 flex items-baseline gap-3.5">
        <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-emerald-600">
          {String(index).padStart(2, "0")}
        </span>
        <h2 className="whitespace-nowrap text-xl font-extrabold tracking-tight text-neutral-900">
          {title}
        </h2>
        <span className="h-px flex-1 bg-gradient-to-r from-neutral-200 to-transparent" />
      </div>
      <div className="grid grid-cols-12 gap-4">
        {wide.map((widget) => (
          <ChartPanel key={widget.id} widget={widget} span="col-span-12" tall onTrace={onTrace} />
        ))}
        {rest.map((widget) => (
          <ChartPanel key={widget.id} widget={widget} span={restSpan} onTrace={onTrace} />
        ))}
      </div>
    </section>
  );
}

function ChartPanel({
  widget,
  span,
  tall,
  onTrace,
}: {
  widget: SpecWidget;
  span: string;
  tall?: boolean;
  onTrace: (title: string, trace: SourceTrace) => void;
}) {
  const chart = widget.chart!;
  const option = chart.echartsOption;
  return (
    <div className={`relative rounded-2xl border border-[rgba(11,11,11,0.10)] bg-[#fcfcfb] p-5 shadow-sm ${span}`}>
      {chart.sourceTrace && (
        <TraceButton onClick={() => onTrace(widget.title, chart.sourceTrace!)} />
      )}
      <p className="pr-8 text-sm font-semibold text-[#0b0b0b]">{widget.title}</p>
      <div className="mt-2">
        {option && Object.keys(option).length > 0 ? (
          <EChartsChart option={option} height={tall ? 380 : 310} />
        ) : (
          <p className="py-16 text-center text-sm text-neutral-400">Chart data unavailable.</p>
        )}
      </div>
    </div>
  );
}

function Modal({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/45 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="mt-[8vh] max-h-[82vh] w-[min(680px,calc(100vw-32px))] overflow-auto rounded-3xl bg-white p-7 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="float-right flex h-8 w-8 items-center justify-center rounded-full bg-neutral-100 text-sm text-neutral-500 hover:bg-neutral-200"
        >
          ✕
        </button>
        {children}
      </div>
    </div>
  );
}

const SEVERITY_BORDERS: Record<string, string> = {
  positive: "border-l-emerald-500",
  negative: "border-l-red-500",
  warning: "border-l-amber-500",
  opportunity: "border-l-emerald-600",
  neutral: "border-l-emerald-300",
};

function TraceDetails({ trace }: { trace: SourceTrace }) {
  return (
    <div className="mt-2 space-y-0.5 rounded-lg bg-neutral-50 px-3 py-2.5 text-xs text-neutral-600">
      <p>
        <b>Calculation:</b> {trace.calculation}
      </p>
      <p>
        <b>Columns:</b> {trace.columns.join(", ")}
      </p>
      {trace.filters.length > 0 && (
        <p>
          <b>Filters:</b> {trace.filters.join("; ")}
        </p>
      )}
      <p>
        <b>Rows:</b> {trace.rowCount.toLocaleString()} · <b>By:</b>{" "}
        {trace.generatedBy === "code" ? "deterministic code" : trace.generatedBy}
      </p>
    </div>
  );
}

function InsightsPanel({ insights }: { insights: SpecInsight[] }) {
  return (
    <div>
      <h3 className="text-lg font-bold tracking-tight">Insights</h3>
      <p className="mb-4 text-xs text-neutral-400">
        Every number below was computed by deterministic code.
      </p>
      {insights.map((insight) => (
        <details
          key={insight.id}
          className={`mb-2.5 rounded-xl border border-l-4 border-neutral-200 px-4 py-3 ${
            SEVERITY_BORDERS[insight.severity] ?? SEVERITY_BORDERS.neutral
          }`}
        >
          <summary className="cursor-pointer">
            <span className="text-sm font-semibold text-neutral-900">{insight.headline}</span>
            <span className="mt-0.5 block text-xs text-neutral-500">{insight.detail}</span>
          </summary>
          <TraceDetails trace={insight.sourceTrace} />
        </details>
      ))}
      {insights.length === 0 && (
        <p className="text-sm text-neutral-500">No notable patterns detected.</p>
      )}
    </div>
  );
}

function ActionsPanel({ spec }: { spec: DashboardSpec }) {
  return (
    <div>
      <h3 className="text-lg font-bold tracking-tight">Recommended next actions</h3>
      <p className="mb-4 text-xs text-neutral-400">Derived from the computed insights.</p>
      {spec.actions.map((action, index) => (
        <div
          key={index}
          className="mb-2 flex items-baseline gap-3 rounded-xl border border-neutral-200 px-4 py-3"
        >
          <span
            className={`rounded-full px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wide ${
              action.priority === "high"
                ? "bg-red-50 text-red-700"
                : action.priority === "medium"
                  ? "bg-amber-50 text-amber-700"
                  : "bg-neutral-100 text-neutral-500"
            }`}
          >
            {action.priority}
          </span>
          <span className="text-sm">
            <b className="text-neutral-900">{action.label}</b>{" "}
            <span className="text-neutral-500">{action.rationale}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

function SourcesPanel({ spec }: { spec: DashboardSpec }) {
  return (
    <div>
      <h3 className="text-lg font-bold tracking-tight">Sources &amp; assumptions</h3>
      <p className="mb-4 text-xs text-neutral-400">
        What this dashboard was built from, and what Picxify inferred.
      </p>
      <ul className="list-disc space-y-1.5 pl-5 text-sm text-neutral-600">
        {spec.dataSources.map((source) => (
          <li key={source.tableId}>
            {source.displayName} — {source.rowCount.toLocaleString()} rows,{" "}
            {source.columnCount} columns
          </li>
        ))}
      </ul>
      {spec.assumptions.length > 0 && (
        <ul className="mt-4 list-disc space-y-1.5 pl-5 text-sm text-neutral-600">
          {spec.assumptions.map((assumption) => (
            <li key={assumption.id}>
              {assumption.label}{" "}
              <span className="text-xs text-neutral-400">
                ({assumption.status.replace("_", " ")})
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TracePanel({ title, trace }: { title: string; trace: SourceTrace }) {
  return (
    <div>
      <h3 className="text-lg font-bold tracking-tight">How this was calculated</h3>
      <p className="mb-3 text-xs text-neutral-400">{title}</p>
      <TraceDetails trace={trace} />
    </div>
  );
}
