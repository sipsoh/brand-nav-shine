"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { generateDashboard, getJob, syncUser } from "@/lib/api-client";
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
      const started = await generateDashboard(token, { workspaceId, datasetId });
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
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={() => void run()}
        disabled={label !== null}
        className="rounded-lg bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-60"
      >
        {label ?? "Generate dashboard"}
      </button>
      {error && <span className="text-sm text-red-600">{error}</span>}
    </div>
  );
}
