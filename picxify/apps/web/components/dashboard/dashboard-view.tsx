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
    return <p className="text-sm text-neutral-500">Connect Clerk to view dashboards.</p>;
  }
  return <LoadedDashboard dashboardId={dashboardId} />;
}

function LoadedDashboard({ dashboardId }: { dashboardId: string }) {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [dashboard, setDashboard] = useState<DashboardDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  if (!isLoaded) return <p className="text-sm text-neutral-500">Loading session…</p>;
  if (!isSignedIn) {
    return (
      <p className="text-sm text-neutral-600">
        <Link href="/sign-in" className="font-medium underline">
          Sign in
        </Link>{" "}
        to view this dashboard.
      </p>
    );
  }
  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!dashboard) return <p className="text-sm text-neutral-500">Loading dashboard…</p>;
  if (!dashboard.currentVersion) {
    return (
      <p className="text-sm text-neutral-500">
        This dashboard has no generated version yet. Generation may still be running.
      </p>
    );
  }

  const spec = dashboard.currentVersion.spec;
  const totalRows = spec.dataSources.reduce((sum, source) => sum + source.rowCount, 0);

  return (
    <div className="space-y-10">
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-3xl font-bold tracking-tight text-neutral-900">
            {spec.dashboard.title}
          </h1>
          <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">
            {spec.dashboard.useCase.replace(/_/g, " ")}
          </span>
          <span className="rounded-full bg-neutral-100 px-3 py-1 text-xs font-medium text-neutral-600">
            for {spec.dashboard.audience}
          </span>
        </div>
        <p className="mt-2 text-neutral-600">{spec.dashboard.subtitle}</p>
        <p className="mt-3 text-xs text-neutral-400">
          Trust bar: {totalRows.toLocaleString()} rows analyzed · {spec.assumptions.length}{" "}
          assumption(s) · every widget carries a source trace
        </p>
      </header>

      {spec.sections.map((section) => (
        <section key={section.id}>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
            {section.title}
          </h2>
          <div
            className={
              section.layout === "hero"
                ? "mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
                : section.layout === "grid"
                  ? "mt-3 grid gap-4 lg:grid-cols-2"
                  : "mt-3 space-y-4"
            }
          >
            {section.widgets.map((widget) => (
              <WidgetRenderer key={widget.id} widget={widget} spec={spec} />
            ))}
          </div>
        </section>
      ))}

      {spec.actions.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Recommended next actions
          </h2>
          <ul className="mt-3 space-y-2">
            {spec.actions.map((action, index) => (
              <li
                key={index}
                className="flex items-start gap-3 rounded-lg border border-neutral-200 bg-white px-4 py-3 text-sm"
              >
                <span
                  className={`mt-0.5 rounded-full px-2 py-0.5 text-xs font-medium ${
                    action.priority === "high"
                      ? "bg-red-50 text-red-700"
                      : action.priority === "medium"
                        ? "bg-amber-50 text-amber-700"
                        : "bg-neutral-100 text-neutral-600"
                  }`}
                >
                  {action.priority}
                </span>
                <span>
                  <span className="font-medium text-neutral-900">{action.label}</span>
                  <span className="block text-neutral-600">{action.rationale}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function WidgetRenderer({ widget, spec }: { widget: SpecWidget; spec: DashboardSpec }) {
  switch (widget.type) {
    case "kpi":
      return widget.kpi ? <KpiWidget widget={widget} /> : <FallbackWidget widget={widget} />;
    case "chart":
      return widget.chart ? <ChartWidget widget={widget} /> : <FallbackWidget widget={widget} />;
    case "insight_card":
      return widget.insight ? (
        <InsightCard insight={widget.insight} />
      ) : (
        <FallbackWidget widget={widget} />
      );
    case "text":
      return <TextWidget widget={widget} />;
    case "assumption_panel":
      return <AssumptionPanelWidget assumptions={spec.assumptions} />;
    case "source_panel":
      return <SourcePanelWidget sources={spec.dataSources} />;
    default:
      // Unknown widget types render a safe fallback, never crash (SETUP.md §7.2).
      return <FallbackWidget widget={widget} />;
  }
}

function KpiWidget({ widget }: { widget: SpecWidget }) {
  const kpi = widget.kpi!;
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">{kpi.label}</p>
      <p className="mt-1 text-2xl font-bold text-neutral-900">
        {typeof kpi.value === "number" ? kpi.value.toLocaleString() : kpi.value}
        {kpi.direction === "up" && <span className="ml-1 text-green-600">▲</span>}
        {kpi.direction === "down" && <span className="ml-1 text-red-600">▼</span>}
      </p>
      {kpi.changeLabel && <p className="text-xs text-neutral-400">{kpi.changeLabel}</p>}
      {kpi.sourceTrace && <TraceDetails trace={kpi.sourceTrace} />}
    </div>
  );
}

function ChartWidget({ widget }: { widget: SpecWidget }) {
  const chart = widget.chart!;
  const option = chart.echartsOption;
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-5">
      <p className="text-sm font-semibold text-neutral-900">{widget.title}</p>
      {chart.takeaway && <p className="mt-0.5 text-xs text-neutral-500">{chart.takeaway}</p>}
      <div className="mt-3">
        {option && Object.keys(option).length > 0 ? (
          <EChartsChart option={option} />
        ) : (
          <p className="py-12 text-center text-sm text-neutral-400">
            Chart data unavailable.
          </p>
        )}
      </div>
      {chart.sourceTrace && <TraceDetails trace={chart.sourceTrace} />}
    </div>
  );
}

const SEVERITY_STYLES: Record<string, string> = {
  positive: "border-green-200 bg-green-50",
  negative: "border-red-200 bg-red-50",
  warning: "border-amber-200 bg-amber-50",
  opportunity: "border-indigo-200 bg-indigo-50",
  neutral: "border-neutral-200 bg-white",
};

function InsightCard({ insight }: { insight: SpecInsight }) {
  return (
    <div
      className={`rounded-xl border p-5 ${SEVERITY_STYLES[insight.severity] ?? SEVERITY_STYLES.neutral}`}
    >
      <p className="text-sm font-semibold text-neutral-900">{insight.headline}</p>
      <p className="mt-1 text-sm text-neutral-600">{insight.detail}</p>
      <TraceDetails trace={insight.sourceTrace} />
    </div>
  );
}

function TextWidget({ widget }: { widget: SpecWidget }) {
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-5 sm:col-span-2 lg:col-span-4">
      <p className="text-sm font-semibold text-neutral-900">{widget.title}</p>
      <div className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-neutral-700">
        {(widget.markdown ?? "").replace(/^- /gm, "• ")}
      </div>
    </div>
  );
}

function AssumptionPanelWidget({
  assumptions,
}: {
  assumptions: { id: string; label: string; status: string }[];
}) {
  if (assumptions.length === 0) return null;
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-5">
      <p className="text-sm font-semibold text-neutral-900">Assumptions</p>
      <ul className="mt-2 space-y-1 text-sm text-neutral-600">
        {assumptions.map((assumption) => (
          <li key={assumption.id}>
            • {assumption.label}{" "}
            <span className="text-xs text-neutral-400">({assumption.status.replace("_", " ")})</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SourcePanelWidget({
  sources,
}: {
  sources: { tableId: string; displayName: string; rowCount: number; columnCount: number }[];
}) {
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-5">
      <p className="text-sm font-semibold text-neutral-900">Data sources</p>
      <ul className="mt-2 space-y-1 text-sm text-neutral-600">
        {sources.map((source) => (
          <li key={source.tableId}>
            • {source.displayName} — {source.rowCount.toLocaleString()} rows,{" "}
            {source.columnCount} columns
          </li>
        ))}
      </ul>
    </div>
  );
}

function FallbackWidget({ widget }: { widget: SpecWidget }) {
  return (
    <div className="rounded-xl border border-dashed border-neutral-300 bg-neutral-50 p-5 text-sm text-neutral-500">
      Unsupported widget type &ldquo;{widget.type}&rdquo; — skipped safely.
    </div>
  );
}

function TraceDetails({ trace }: { trace: SourceTrace }) {
  return (
    <details className="mt-3">
      <summary className="cursor-pointer text-xs font-medium text-neutral-400 hover:text-neutral-600">
        View source
      </summary>
      <div className="mt-2 space-y-1 rounded-md bg-neutral-50 p-3 text-xs text-neutral-600">
        <p>
          <span className="font-medium">Calculation:</span> {trace.calculation}
        </p>
        <p>
          <span className="font-medium">Columns:</span> {trace.columns.join(", ")}
        </p>
        {trace.filters.length > 0 && (
          <p>
            <span className="font-medium">Filters:</span> {trace.filters.join("; ")}
          </p>
        )}
        <p>
          <span className="font-medium">Rows:</span> {trace.rowCount.toLocaleString()} ·{" "}
          <span className="font-medium">By:</span>{" "}
          {trace.generatedBy === "code" ? "deterministic code" : trace.generatedBy}
        </p>
      </div>
    </details>
  );
}
