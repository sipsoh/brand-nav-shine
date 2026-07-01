import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-24">
      <div className="max-w-3xl">
        <h1 className="text-5xl font-bold tracking-tight text-neutral-900">
          Drop in messy data. <span className="text-neutral-500">Get the story.</span>
        </h1>
        <p className="mt-6 text-lg leading-relaxed text-neutral-600">
          Upload a CSV, Excel file, or pasted table. Picxify cleans and profiles it, detects the
          likely story, and builds a polished, client-ready dashboard — with KPIs, charts,
          insights, editable assumptions, a source trace for every number, and a shareable link.
        </p>
        <div className="mt-10 flex gap-4">
          <Link
            href="/app/upload"
            className="rounded-lg bg-neutral-900 px-6 py-3 font-medium text-white hover:bg-neutral-700"
          >
            Turn data into a dashboard
          </Link>
          <Link
            href="/pricing"
            className="rounded-lg border border-neutral-300 px-6 py-3 font-medium text-neutral-700 hover:border-neutral-400"
          >
            See pricing
          </Link>
        </div>
      </div>
      <div className="mt-24 grid gap-8 sm:grid-cols-3">
        {[
          {
            title: "Code calculates. AI narrates.",
            body: "Every metric is computed deterministically. The AI only plans layouts and writes narrative grounded in computed facts.",
          },
          {
            title: "Trust is a feature.",
            body: "Every KPI, chart, and insight carries a source trace: columns used, filters applied, calculation, and rows included.",
          },
          {
            title: "Built to be shared.",
            body: "One click publishes a fast, read-only dashboard link your client, investor, or team can open without an account.",
          },
        ].map((f) => (
          <div key={f.title} className="rounded-xl border border-neutral-200 bg-white p-6">
            <h2 className="font-semibold text-neutral-900">{f.title}</h2>
            <p className="mt-2 text-sm leading-relaxed text-neutral-600">{f.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
