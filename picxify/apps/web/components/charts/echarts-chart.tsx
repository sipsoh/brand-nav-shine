"use client";

import { useEffect, useRef } from "react";
import { applyChartTheme } from "@/lib/chart-theme";
import { useColorScheme } from "@/lib/use-color-scheme";

function compact(value: unknown): string {
  if (typeof value !== "number") return String(value ?? "");
  const magnitude = Math.abs(value);
  if (magnitude >= 1e9) return (value / 1e9).toFixed(1) + "B";
  if (magnitude >= 1e6) return (value / 1e6).toFixed(1) + "M";
  if (magnitude >= 1e4) return (value / 1e3).toFixed(1) + "K";
  return value.toLocaleString();
}

/** Human-scale axis labels and tooltip values, applied at render time so the
 * spec stays pure JSON. */
function withCompactFormatting(option: Record<string, unknown>): Record<string, unknown> {
  const clone = JSON.parse(JSON.stringify(option)) as Record<string, unknown>;
  for (const key of ["xAxis", "yAxis"]) {
    const axis = clone[key];
    const axes = Array.isArray(axis) ? axis : axis ? [axis] : [];
    for (const item of axes as Record<string, unknown>[]) {
      if (item.type === "value") {
        item.axisLabel = { ...((item.axisLabel as object) ?? {}), formatter: compact };
      }
    }
  }
  clone.tooltip = { ...((clone.tooltip as object) ?? {}), valueFormatter: compact };
  const series = Array.isArray(clone.series) ? (clone.series as Record<string, unknown>[]) : [];
  for (const item of series) {
    const label = item.label as { show?: boolean; formatter?: unknown } | undefined;
    // Bars carry value-at-the-tip labels; other forms (funnel, pie) label identity.
    if (item.type === "bar" && label?.show && !label.formatter) {
      label.formatter = (params: { value: unknown }) => compact(params.value);
    }
  }
  return clone;
}

export function EChartsChart({
  option,
  height = 320,
}: {
  option: Record<string, unknown>;
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const scheme = useColorScheme();

  useEffect(() => {
    let disposed = false;
    let chart: import("echarts").ECharts | null = null;
    let observer: ResizeObserver | null = null;

    (async () => {
      const echarts = await import("echarts");
      if (disposed || !containerRef.current) return;
      chart = echarts.init(containerRef.current);
      chart.setOption(applyChartTheme(withCompactFormatting(option), scheme));
      observer = new ResizeObserver(() => chart?.resize());
      observer.observe(containerRef.current);
    })();

    return () => {
      disposed = true;
      observer?.disconnect();
      chart?.dispose();
    };
  }, [option, scheme]);

  return <div ref={containerRef} style={{ height, width: "100%" }} />;
}
