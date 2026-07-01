export default async function DashboardPage({
  params,
}: {
  params: Promise<{ dashboardId: string }>;
}) {
  const { dashboardId } = await params;
  return (
    <div className="mx-auto max-w-6xl px-6 py-16">
      <h1 className="text-3xl font-bold tracking-tight text-neutral-900">Dashboard</h1>
      <p className="mt-2 text-neutral-600">
        Renderer for validated DashboardSpec JSON lands in Milestones 7–8.
      </p>
      <p className="mt-4 font-mono text-sm text-neutral-400">id: {dashboardId}</p>
    </div>
  );
}
