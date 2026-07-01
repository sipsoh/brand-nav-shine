export default async function SharePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return (
    <div className="mx-auto max-w-6xl px-6 py-16">
      <h1 className="text-3xl font-bold tracking-tight text-neutral-900">Shared dashboard</h1>
      <p className="mt-2 text-neutral-600">
        Public, read-only dashboard view ships in Milestone 9.
      </p>
      <p className="mt-4 font-mono text-sm text-neutral-400">slug: {slug}</p>
    </div>
  );
}
