import { DashboardView } from "@/components/dashboard/dashboard-view";

export default async function DashboardPage({
  params,
}: {
  params: Promise<{ dashboardId: string }>;
}) {
  const { dashboardId } = await params;
  return (
    <div className="py-12">
      <DashboardView dashboardId={dashboardId} />
    </div>
  );
}
