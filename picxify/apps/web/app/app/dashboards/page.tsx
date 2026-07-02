import { DashboardList } from "@/components/dashboard/dashboard-list";

export default function DashboardsPage() {
  return (
    <div className="py-16">
      <h1 className="text-3xl font-bold tracking-tight text-neutral-900">Dashboards</h1>
      <p className="mt-2 text-neutral-600">Everything you have generated in this workspace.</p>
      <div className="mt-8">
        <DashboardList />
      </div>
    </div>
  );
}
