import { DatasetProfile } from "@/components/dataset/dataset-profile";
import { GenerateDashboardButton } from "@/components/dashboard/generate-button";

export default async function DatasetPage({
  params,
}: {
  params: Promise<{ datasetId: string }>;
}) {
  const { datasetId } = await params;
  return (
    <div className="py-16">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-neutral-900">
            What Picxify detected
          </h1>
          <p className="mt-2 text-neutral-600">
            Columns, types, cleanup decisions, and quality notes from profiling your data.
          </p>
        </div>
        <GenerateDashboardButton datasetId={datasetId} />
      </div>
      <div className="mt-8">
        <DatasetProfile datasetId={datasetId} />
      </div>
    </div>
  );
}
