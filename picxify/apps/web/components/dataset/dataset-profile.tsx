"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getDataset, type DatasetResponse } from "@/lib/api-client";
import { clerkEnabled } from "@/lib/auth";

const TYPE_STYLES: Record<string, string> = {
  integer: "bg-blue-50 text-blue-700",
  float: "bg-blue-50 text-blue-700",
  currency: "bg-emerald-50 text-emerald-700",
  percent: "bg-emerald-50 text-emerald-700",
  date: "bg-purple-50 text-purple-700",
  datetime: "bg-purple-50 text-purple-700",
  category: "bg-amber-50 text-amber-700",
  boolean: "bg-amber-50 text-amber-700",
  id: "bg-neutral-100 text-neutral-600",
  text: "bg-rose-50 text-rose-700",
  unknown: "bg-neutral-100 text-neutral-500",
};

const SEVERITY_STYLES: Record<string, string> = {
  info: "border-neutral-200 bg-neutral-50 text-neutral-700",
  warning: "border-amber-200 bg-amber-50 text-amber-800",
  critical: "border-red-200 bg-red-50 text-red-800",
};

export function DatasetProfile({ datasetId }: { datasetId: string }) {
  if (!clerkEnabled) {
    return (
      <p className="text-sm text-neutral-500">
        Connect Clerk to enable dataset views.
      </p>
    );
  }
  return <LoadedProfile datasetId={datasetId} />;
}

function LoadedProfile({ datasetId }: { datasetId: string }) {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [dataset, setDataset] = useState<DatasetResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) throw new Error("No session token.");
        const result = await getDataset(token, datasetId);
        if (!cancelled) setDataset(result);
      } catch {
        if (!cancelled) setError("Could not load this dataset.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken, datasetId]);

  if (!isLoaded) return <p className="text-sm text-neutral-500">Loading session…</p>;
  if (!isSignedIn) {
    return (
      <p className="text-sm text-neutral-600">
        <Link href="/sign-in" className="font-medium underline">
          Sign in
        </Link>{" "}
        to view this dataset.
      </p>
    );
  }
  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!dataset) return <p className="text-sm text-neutral-500">Loading dataset…</p>;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-neutral-200 bg-white px-5 py-4 text-sm">
        <span className="font-semibold text-neutral-900">{dataset.name}</span>
        <Stat label="rows" value={dataset.rowCount ?? 0} />
        <Stat label={dataset.tableCount === 1 ? "table" : "tables"} value={dataset.tableCount} />
        {dataset.qualityScore !== null && (
          <span className="ml-auto rounded-full bg-neutral-100 px-3 py-1 text-xs font-medium text-neutral-700">
            Quality score: {(dataset.qualityScore * 100).toFixed(0)}%
          </span>
        )}
      </div>

      {dataset.findings.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Data cleanup and quality notes
          </h2>
          <ul className="mt-3 space-y-2">
            {dataset.findings.map((finding, index) => (
              <li
                key={index}
                className={`rounded-lg border px-4 py-2 text-sm ${
                  SEVERITY_STYLES[finding.severity] ?? SEVERITY_STYLES.info
                }`}
              >
                {finding.message}
              </li>
            ))}
          </ul>
        </section>
      )}

      {dataset.tables.map((table) => (
        <section key={table.id}>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
            {table.name} · {table.rowCount} rows · {table.columnCount} columns
          </h2>
          <div className="mt-3 overflow-x-auto rounded-xl border border-neutral-200 bg-white">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-neutral-200 text-xs uppercase tracking-wide text-neutral-500">
                <tr>
                  <th className="px-4 py-3">Column</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3">Missing</th>
                  <th className="px-4 py-3">Examples</th>
                </tr>
              </thead>
              <tbody>
                {table.columns.map((column) => (
                  <tr key={column.id} className="border-b border-neutral-100 last:border-0">
                    <td className="px-4 py-2.5 font-medium text-neutral-900">{column.name}</td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          TYPE_STYLES[column.detectedType] ?? TYPE_STYLES.unknown
                        }`}
                      >
                        {column.detectedType}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-neutral-600">{column.roleHint ?? "—"}</td>
                    <td className="px-4 py-2.5 text-neutral-600">
                      {column.nullableRatio !== null
                        ? `${Math.round(column.nullableRatio * 100)}%`
                        : "—"}
                    </td>
                    <td className="max-w-xs truncate px-4 py-2.5 text-neutral-500">
                      {column.examples.slice(0, 3).map(String).join(", ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <span className="text-neutral-600">
      <span className="font-semibold text-neutral-900">{value.toLocaleString()}</span> {label}
    </span>
  );
}
