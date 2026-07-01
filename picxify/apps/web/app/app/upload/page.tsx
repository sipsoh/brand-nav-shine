export default function UploadPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-3xl font-bold tracking-tight text-neutral-900">Create a dashboard</h1>
      <p className="mt-2 text-neutral-600">
        Drop a CSV or Excel file, or paste a table. Picxify will clean it, profile it, and build
        the story.
      </p>
      <div className="mt-8 flex h-56 items-center justify-center rounded-xl border-2 border-dashed border-neutral-300 bg-white text-neutral-500">
        Upload flow lands in Milestone 3 (presigned URLs + MinIO/S3).
      </div>
    </div>
  );
}
