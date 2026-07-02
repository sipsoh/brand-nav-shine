"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { generateDashboard, getDataset, getJob, syncUser } from "@/lib/api-client";
import { clerkEnabled } from "@/lib/auth";

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 180_000;

export function GenerateDashboardButton({ datasetId }: { datasetId: string }) {
  if (!clerkEnabled) return null;
  return <GenerateInner datasetId={datasetId} />;
}

function GenerateInner({ datasetId }: { datasetId: string }) {
  const { isSignedIn, getToken } = useAuth();
  const router = useRouter();
  const [label, setLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tables, setTables] = useState<{ id: string; name: string; rowCount: number }[]>([]);
  const [tableId, setTableId] = useState<string>("");

  useEffect(() => {
    if (!isSignedIn) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const dataset = await getDataset(token, datasetId);
        if (!cancelled) {
          setTables(
            dataset.tables.map((t) => ({ id: t.id, name: t.name, rowCount: t.rowCount })),
          );
        }
      } catch {
        // Sheet picker is optional; generation works without it.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isSignedIn, getToken, datasetId]);

  if (!isSignedIn) return null;

  async function run() {
    setError(null);
    setLabel("Starting generation…");
    try {
      const token = await getToken();
      if (!token) throw new Error("No session token.");
      const synced = await syncUser(token);
      const workspaceId = synced.workspaces[0]?.id;
      if (!workspaceId) throw new Error("No workspace.");
      const started = await generateDashboard(token, {
        workspaceId,
        datasetId,
        ...(tableId ? { tableId } : {}),
      });
      const begunAt = Date.now();
      for (;;) {
        const pollToken = await getToken();
        if (!pollToken) throw new Error("No session token.");
        const job = await getJob(pollToken, started.jobId);
        if (job.status === "succeeded") {
          router.push(`/app/dashboards/${started.dashboardId}`);
          return;
        }
        if (job.status === "failed" || job.status === "cancelled") {
          throw new Error(job.errorMessage ?? "Generation failed.");
        }
        setLabel(job.currentStep ?? "Generating…");
        if (Date.now() - begunAt > POLL_TIMEOUT_MS) {
          throw new Error("Generation is taking longer than expected.");
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      }
    } catch (caught) {
      setLabel(null);
      setError(caught instanceof Error ? caught.message : "Generation failed.");
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex items-center gap-3">
        {tables.length > 1 && (
          <select
            value={tableId}
            onChange={(event) => setTableId(event.target.value)}
            disabled={label !== null}
            className="max-w-56 rounded-lg border border-neutral-300 bg-white px-3 py-2.5 text-sm text-neutral-700"
          >
            <option value="">Sheet: auto-pick best</option>
            {tables.map((table) => (
              <option key={table.id} value={table.id}>
                {table.name} ({table.rowCount.toLocaleString()} rows)
              </option>
            ))}
          </select>
        )}
        <button
          type="button"
          onClick={() => void run()}
          disabled={label !== null}
          className="rounded-lg bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-60"
        >
          {label ?? "Generate dashboard"}
        </button>
      </div>
      {error && <span className="text-sm text-red-600">{error}</span>}
    </div>
  );
}
