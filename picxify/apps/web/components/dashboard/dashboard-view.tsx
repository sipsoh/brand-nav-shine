"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";
import { SpecRenderer } from "@/components/dashboard/spec-renderer";
import {
  getDashboard,
  publishDashboard,
  type DashboardDetail,
} from "@/lib/api-client";
import { clerkEnabled } from "@/lib/auth";

export function DashboardView({ dashboardId }: { dashboardId: string }) {
  if (!clerkEnabled) {
    return <p className="py-16 text-sm text-neutral-500">Connect Clerk to view dashboards.</p>;
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

  return (
    <SpecRenderer
      spec={dashboard.currentVersion.spec}
      extraHeroButtons={
        <ShareControl
          dashboardId={dashboardId}
          initialVisibility={dashboard.visibility}
          getToken={getToken}
        />
      }
    />
  );
}

function ShareControl({
  dashboardId,
  initialVisibility,
  getToken,
}: {
  dashboardId: string;
  initialVisibility: string;
  getToken: () => Promise<string | null>;
}) {
  const [open, setOpen] = useState(false);
  const [visibility, setVisibility] = useState(initialVisibility);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function setLevel(level: "private" | "unlisted" | "public") {
    setBusy(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("No session token.");
      const result = await publishDashboard(token, dashboardId, level);
      setVisibility(result.visibility);
      setShareUrl(result.shareUrl);
      setCopied(false);
    } catch {
      setError("Could not update sharing.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-full bg-emerald-400 px-4 py-2 text-sm font-bold text-emerald-950 transition hover:bg-emerald-300"
      >
        Share
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/45 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        >
          <div
            className="mt-[10vh] w-[min(520px,calc(100vw-32px))] rounded-3xl bg-white p-7 text-neutral-900 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 className="text-lg font-bold tracking-tight">Share this dashboard</h3>
            <p className="mb-5 text-xs text-neutral-400">
              Viewers open a read-only page — no account needed. Links are unguessable.
            </p>
            <div className="space-y-2">
              {(
                [
                  ["private", "Private", "Only workspace members can see it."],
                  ["unlisted", "Unlisted link", "Anyone with the link can view."],
                  ["public", "Public", "Anyone with the link can view; may be indexed."],
                ] as const
              ).map(([level, label, hint]) => (
                <button
                  key={level}
                  type="button"
                  disabled={busy}
                  onClick={() => void setLevel(level)}
                  className={`flex w-full items-baseline justify-between rounded-xl border px-4 py-3 text-left text-sm transition ${
                    visibility === level
                      ? "border-emerald-500 bg-emerald-50"
                      : "border-neutral-200 hover:border-neutral-300"
                  }`}
                >
                  <span className="font-semibold">{label}</span>
                  <span className="text-xs text-neutral-400">{hint}</span>
                </button>
              ))}
            </div>
            {visibility !== "private" && shareUrl && (
              <div className="mt-4 flex items-center gap-2 rounded-xl bg-neutral-50 px-3 py-2.5">
                <code className="min-w-0 flex-1 truncate text-xs text-neutral-600">
                  {shareUrl}
                </code>
                <button
                  type="button"
                  onClick={() => {
                    void navigator.clipboard.writeText(shareUrl);
                    setCopied(true);
                  }}
                  className="rounded-lg bg-neutral-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-neutral-700"
                >
                  {copied ? "Copied!" : "Copy link"}
                </button>
              </div>
            )}
            {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="mt-5 w-full rounded-xl border border-neutral-200 py-2 text-sm font-semibold text-neutral-600 hover:bg-neutral-50"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </>
  );
}
