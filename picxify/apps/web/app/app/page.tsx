import Link from "next/link";

export default function AppHomePage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-16">
      <h1 className="text-3xl font-bold tracking-tight text-neutral-900">Home</h1>
      <p className="mt-2 text-neutral-600">
        Workspace auth arrives in Milestone 2. For now, start from an upload.
      </p>
      <div className="mt-8 flex gap-4">
        <Link
          href="/app/upload"
          className="rounded-lg bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-700"
        >
          New dashboard
        </Link>
        <Link
          href="/app/dashboards"
          className="rounded-lg border border-neutral-300 px-5 py-2.5 text-sm font-medium text-neutral-700 hover:border-neutral-400"
        >
          My dashboards
        </Link>
      </div>
    </div>
  );
}
