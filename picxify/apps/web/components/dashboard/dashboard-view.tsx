"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";
import { EChartsChart } from "@/components/charts/echarts-chart";
import {
  getDashboard,
  type DashboardDetail,
  type DashboardSpec,
  type SourceTrace,
  type SpecInsight,
  type SpecWidget,
} from "@/lib/api-client";
import { clerkEnabled } from "@/lib/auth";

export function DashboardView({ dashboardId }: { dashboardId: string }) {
  if (!clerkEnabled) {
    return <p className="py-16 text-sm text-neutral-500">Connect Clerk to view dashboards.</p>;
  }
  return <LoadedDashboard dashboardId={dashboardId} />;
}

type Overlay =
  | { kind: "none" }
  | { kind: "insights" }
  | { kind: "actions" }
  | { kind: "sources" }
  | { kind: "trace"; title: string; trace: SourceTrace };

function LoadedDashboard({ dashboardId }: { dashboardId: string }) {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [dashboard, setDashboard] = useState<DashboardDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [overlay, setOverlay] = useState<Overlay>({ kind: "none" });

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) throw new Error("No session token.");
        const result = await getDashboard(token, dashboardId);
        if (!cancelled) setDashboard(result);
      } catch {
        if (!cancelled) setError("Could not load this dashboard.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken, dashboardId]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOverlay({ kind: "none" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!isLoaded) return <p className="py-16 text-sm text-neutral-500">Loading session…</p>;
  if (!isSignedIn) {
    return (
      <p className="py-16 text-sm text-neutral-600">
        <Link href="/sign-in" className="font-medium underline">
          Sign in
        </Link>{" "}
        to view this dashboard.
      </p>
    );
  }
  if (error) return <p className="py-16 text-sm text-red-600">{error}</p>;
  if (!dashboard) return <p className="py-16 text-sm text-neutral-500">Loading dashboard…</p>;
  if (!dashboard.currentVersion) {
    return (
      <p className="py-16 text-sm text-neutral-500">
        This dashboard has no generated version yet. Generation may still be running.
      </p>
    );
  }

  const spec = dashboard.currentVersion.spec;
  const totalRows = spec.dataSources.reduce((sum, source) => sum + source.rowCount, 0);

  const kpis: SpecWidget[] = [];
  const charts: SpecWidget[] = [];
  const inlineInsights: SpecInsight[] = [];
  let execText: SpecWidget | null = null;
  for (const section of spec.sections) {
    for (const widget of section.widgets) {
      if (widget.type === "kpi" && widget.kpi) kpis.push(widget);
      else if (widget.type === "chart" && widget.chart) charts.push(widget);
      else if (widget.type === "text" && !execText) execText = widget;
      else if (widget.type === "insight_card" && widget.insight)
        inlineInsights.push(widget.insight);
    }
  }
  const insights = spec.insights.length > 0 ? spec.insights : inlineInsights;
  const openTrace = (title: string, trace: SourceTrace) =>
    setOverlay({ kind: "trace", title, trace });

  return (
    <div className="-mx-6">
      {/* Hero band */}
      <div className="bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 px-6 pb-24 pt-10 text-white">
        <div className="mx-auto max-w-7xl">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-indigo-300">
                {spec.dashboard.useCase.replace(/_/g, " ")} · for {spec.dashboard.audience}
              </p>
              <h1 className="mt-2 text-3xl font-extrabold tracking-tight sm:text-4xl">
                {spec.dashboard.title}
              </h1>
              <p className="mt-2 max-w-2xl text-indigo-200">{spec.dashboard.subtitle}</p>
              <p className="mt-4 text-xs text-indigo-300/80">
                <span className="font-semibold text-indigo-100">
                  {totalRows.toLocaleString()}
                </span>{" "}
                rows analyzed ·{" "}
                <span className="font-semibold text-indigo-100">{spec.assumptions.length}</span>{" "}
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
          <div className="mt-4 flex items-baseline gap-3 rounded-2xl border border-indigo-100 bg-gradient-to-r from-indigo-50 to-violet-50 px-6 py-4">
            <span className="text-[11px] font-extrabold uppercase tracking-widest text-indigo-600">
              Summary
            </span>
            <span className="text-sm text-slate-600">
              {execText.markdown.replace(/^- /gm, "").split("\n").join("  ·  ")}
            </span>
          </div>
        )}

        <div className="mt-4 grid grid-cols-12 gap-4">
          {charts.map((widget) => (
            <ChartPanel key={widget.id} widget={widget} onTrace={openTrace} />
          ))}
        </div>

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
      className="absolute right-4 top-4 text-neutral-300 transition hover:text-indigo-500"
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
  const kpi = widget.kpi!;
  return (
    <div className="relative overflow-hidden rounded-2xl border border-neutral-200 bg-white p-5 shadow-sm">
      <span className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-indigo-500 to-violet-500" />
      {kpi.sourceTrace && (
        <TraceButton onClick={() => onTrace(kpi.label, kpi.sourceTrace!)} />
      )}
      <p className="text-[11px] font-bold uppercase tracking-wider text-neutral-400">
        {kpi.label}
      </p>
      <p className="mt-1.5 text-2xl font-extrabold tracking-tight text-neutral-900 lg:text-3xl">
        {typeof kpi.value === "number" ? kpi.value.toLocaleString() : kpi.value}
        {kpi.direction === "up" && <span className="ml-1 text-lg text-emerald-500">▲</span>}
        {kpi.direction === "down" && <span className="ml-1 text-lg text-red-500">▼</span>}
      </p>
      {kpi.changeLabel && <p className="text-xs text-neutral-400">{kpi.changeLabel}</p>}
    </div>
  );
}

const SPANS: Record<string, string> = {
  xl: "col-span-12",
  full: "col-span-12",
  lg: "col-span-12 lg:col-span-8",
  md: "col-span-12 lg:col-span-6",
  sm: "col-span-12 lg:col-span-4",
};

function ChartPanel({
  widget,
  onTrace,
}: {
  widget: SpecWidget;
  onTrace: (title: string, trace: SourceTrace) => void;
}) {
  const chart = widget.chart!;
  const option = chart.echartsOption;
  return (
    <div
      className={`relative rounded-2xl border border-neutral-200 bg-white p-5 shadow-sm ${
        SPANS[widget.size ?? "md"] ?? SPANS.md
      }`}
    >
      {chart.sourceTrace && (
        <TraceButton onClick={() => onTrace(widget.title, chart.sourceTrace!)} />
      )}
      <p className="pr-8 text-sm font-bold tracking-tight text-neutral-900">{widget.title}</p>
      <div className="mt-2">
        {option && Object.keys(option).length > 0 ? (
          <EChartsChart option={option} height={widget.size === "xl" ? 340 : 300} />
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
  opportunity: "border-l-indigo-500",
  neutral: "border-l-indigo-300",
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
