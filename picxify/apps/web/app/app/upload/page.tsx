import { UploadDropzone } from "@/components/upload/upload-dropzone";

export default function UploadPage() {
  return (
    <div className="py-16">
      <h1 className="text-3xl font-bold tracking-tight text-neutral-900">Create a dashboard</h1>
      <p className="mt-2 max-w-2xl text-neutral-600">
        Drop a CSV or Excel file. Picxify stores it securely, then cleans, profiles, and turns it
        into a client-ready dashboard.
      </p>
      <div className="mt-8 max-w-2xl">
        <UploadDropzone />
      </div>
      <p className="mt-4 max-w-2xl text-xs text-neutral-400">
        Files are private to your workspace and only accessible through signed URLs. Your data is
        never used for model training.
      </p>
    </div>
  );
}
