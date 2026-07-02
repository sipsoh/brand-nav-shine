"use client";

import { useEffect, useRef } from "react";

export function EChartsChart({
  option,
  height = 320,
}: {
  option: Record<string, unknown>;
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let disposed = false;
    let chart: import("echarts").ECharts | null = null;
    let observer: ResizeObserver | null = null;

    (async () => {
      const echarts = await import("echarts");
      if (disposed || !containerRef.current) return;
      chart = echarts.init(containerRef.current);
      chart.setOption(option);
      observer = new ResizeObserver(() => chart?.resize());
      observer.observe(containerRef.current);
    })();

    return () => {
      disposed = true;
      observer?.disconnect();
      chart?.dispose();
    };
  }, [option]);

  return <div ref={containerRef} style={{ height, width: "100%" }} />;
}
