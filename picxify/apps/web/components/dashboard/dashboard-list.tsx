"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";
import { listDashboards, syncUser, type DashboardListItem } from "@/lib/api-client";
import { clerkEnabled } from "@/lib/auth";

export function DashboardList() {
  if (!clerkEnabled) {
    return (
      <p className="text-sm text-neutral-500">Connect Clerk to see your dashboards.</p>
    );
  }
  return <LoadedList />;
}

function LoadedList() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [items, setItems] = useState<DashboardListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const synced = await syncUser(token);
        const workspaceId = synced.workspaces[0]?.id;
        if (!workspaceId) return;
        const result = await listDashboards(token, workspaceId);
        if (!cancelled) setItems(result.dashboards);
      } catch {
        if (!cancelled) setError("Could not load dashboards.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken]);

  if (!isLoaded) return <p className="text-sm text-neutral-500">Loading session…</p>;
  if (!isSignedIn) {
    return (
      <p className="text-sm text-neutral-600">
        <Link href="/sign-in" className="font-medium underline">
          Sign in
        </Link>{" "}
        to see your dashboards.
      </p>
    );
  }
  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (items === null) return <p className="text-sm text-neutral-500">Loading dashboards…</p>;
  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-neutral-200 bg-white p-12 text-center text-neutral-500">
        No dashboards yet.{" "}
        <Link href="/app/upload" className="font-medium text-neutral-900 underline">
          Upload data
        </Link>{" "}
        to create your first one.
      </div>
    );
  }
  return (
    <ul className="space-y-2">
      {items.map((item) => (
        <li key={item.dashboardId}>
          <Link
            href={`/app/dashboards/${item.dashboardId}`}
            className="flex items-center justify-between rounded-xl border border-neutral-200 bg-white px-5 py-4 hover:border-neutral-400"
          >
            <span className="font-medium text-neutral-900">{item.title}</span>
            <span className="flex items-center gap-3 text-xs text-neutral-500">
              {!item.hasVersion && <span className="text-amber-600">generating…</span>}
              <span className="rounded-full bg-neutral-100 px-2.5 py-0.5">{item.visibility}</span>
              {new Date(item.createdAt).toLocaleDateString()}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
