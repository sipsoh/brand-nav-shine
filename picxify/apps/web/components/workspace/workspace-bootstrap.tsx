"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";
import { syncUser, type WorkspaceSummary } from "@/lib/api-client";
import { clerkEnabled } from "@/lib/auth";

export function WorkspaceBootstrap() {
  if (!clerkEnabled) {
    return (
      <div className="rounded-xl border border-dashed border-neutral-300 bg-white p-6 text-sm text-neutral-500">
        Connect Clerk (set <code>NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY</code> in{" "}
        <code>.env.local</code>) to enable sign-in and workspaces.
      </div>
    );
  }
  return <SyncedWorkspaces />;
}

function SyncedWorkspaces() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) {
          throw new Error("No session token available.");
        }
        const result = await syncUser(token);
        if (!cancelled) {
          setWorkspaces(result.workspaces);
        }
      } catch {
        if (!cancelled) {
          setError("Could not reach the Picxify API. Is it running on port 8000?");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken]);

  if (!isLoaded) {
    return <p className="text-sm text-neutral-500">Loading session…</p>;
  }
  if (!isSignedIn) {
    return (
      <div className="rounded-xl border border-neutral-200 bg-white p-6 text-sm text-neutral-600">
        <Link href="/sign-in" className="font-medium text-neutral-900 underline">
          Sign in
        </Link>{" "}
        to see your workspaces.
      </div>
    );
  }
  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }
  if (workspaces === null) {
    return <p className="text-sm text-neutral-500">Setting up your workspace…</p>;
  }
  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Your workspaces
      </h2>
      {workspaces.map((workspace) => (
        <div
          key={workspace.id}
          className="flex items-center justify-between rounded-xl border border-neutral-200 bg-white p-4"
        >
          <span className="font-medium text-neutral-900">{workspace.name}</span>
          <span className="rounded-full bg-neutral-100 px-3 py-1 text-xs text-neutral-600">
            {workspace.role}
          </span>
        </div>
      ))}
    </div>
  );
}
