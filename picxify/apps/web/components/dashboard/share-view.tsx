"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SpecRenderer } from "@/components/dashboard/spec-renderer";
import { getShare, type ShareResponse } from "@/lib/api-client";

/** Public, read-only dashboard view. No auth, no Clerk — just the spec. */
export function ShareView({ slug }: { slug: string }) {
  const [share, setShare] = useState<ShareResponse | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await getShare(slug);
        if (!cancelled) setShare(result);
      } catch {
        if (!cancelled) setNotFound(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (notFound) {
    return (
      <div className="mx-auto max-w-xl px-6 py-32 text-center">
        <h1 className="text-2xl font-bold text-neutral-900">
          This dashboard isn&apos;t available
        </h1>
        <p className="mt-2 text-neutral-500">
          The link may have been unpublished, or it never existed.
        </p>
        <Link
          href="/"
          className="mt-6 inline-block rounded-full bg-neutral-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-neutral-700"
        >
          Make your own with Picxify
        </Link>
      </div>
    );
  }
  if (!share) {
    return <p className="px-6 py-32 text-center text-sm text-neutral-500">Loading dashboard…</p>;
  }

  return (
    <div className="px-6">
      <SpecRenderer spec={share.spec} />
      <div className="pb-12 text-center">
        <Link
          href="/"
          className="text-xs font-semibold text-emerald-700 hover:text-emerald-800"
        >
          Powered by Picxify — drop in messy data, get the story →
        </Link>
      </div>
    </div>
  );
}
