"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  completeUpload,
  createDatasetFromFile,
  getJob,
  presignUpload,
  putToPresignedUrl,
  syncUser,
} from "@/lib/api-client";
import { clerkEnabled } from "@/lib/auth";

const ACCEPTED = ".csv,.tsv,.txt,.xlsx,.xls,.pdf";
const POLL_INTERVAL_MS = 1200;
const POLL_TIMEOUT_MS = 120_000;

type Phase =
  | { step: "idle" }
  | { step: "uploading"; label: string }
  | { step: "done"; datasetId: string; filename: string }
  | { step: "error"; message: string };

function summarizeNames(files: File[]): string {
  if (files.length === 1) return files[0].name;
  return `${files.length} files (${files.map((f) => f.name).join(", ")})`;
}

async function pollJobUntilDone(
  getToken: () => Promise<string | null>,
  jobId: string,
  onStep: (label: string) => void,
): Promise<void> {
  const startedAt = Date.now();
  for (;;) {
    const token = await getToken();
    if (!token) throw new Error("No session token.");
    const job = await getJob(token, jobId);
    if (job.status === "succeeded") return;
    if (job.status === "failed" || job.status === "cancelled") {
      throw new Error(job.errorMessage ?? "Processing failed. Please try again.");
    }
    onStep(job.currentStep ?? "Processing…");
    if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
      throw new Error("Processing is taking longer than expected. Check back shortly.");
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
}

export function UploadDropzone() {
  if (!clerkEnabled) {
    return (
      <div className="flex h-56 items-center justify-center rounded-xl border-2 border-dashed border-neutral-300 bg-white px-8 text-center text-sm text-neutral-500">
        Connect Clerk (set NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY in .env.local) to enable uploads.
      </div>
    );
  }
  return <AuthedDropzone />;
}

function AuthedDropzone() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>({ step: "idle" });
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const result = await syncUser(token);
        if (!cancelled && result.workspaces.length > 0) {
          setWorkspaceId(result.workspaces[0].id);
        }
      } catch {
        if (!cancelled) {
          setPhase({
            step: "error",
            message: "Could not reach the Picxify API. Is it running on port 8000?",
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken]);

  const handleFiles = useCallback(
    async (files: File[]) => {
      if (!workspaceId || files.length === 0) return;
      const label = summarizeNames(files);
      try {
        const fileIds: string[] = [];
        for (const [index, file] of files.entries()) {
          const prefix = files.length > 1 ? `File ${index + 1}/${files.length}: ` : "";
          setPhase({ step: "uploading", label: `${prefix}Requesting upload slot…` });
          const token = await getToken();
          if (!token) throw new Error("No session token.");
          const presigned = await presignUpload(token, {
            workspaceId,
            filename: file.name,
            mimeType: file.type || "application/octet-stream",
            sizeBytes: file.size,
          });
          setPhase({ step: "uploading", label: `${prefix}Uploading to secure storage…` });
          await putToPresignedUrl(presigned.uploadUrl, file);
          setPhase({ step: "uploading", label: `${prefix}Confirming upload…` });
          const completed = await completeUpload(token, presigned.fileId);
          fileIds.push(completed.fileId);
        }
        setPhase({ step: "uploading", label: "Reading file…" });
        const token = await getToken();
        if (!token) throw new Error("No session token.");
        const dataset = await createDatasetFromFile(token, {
          workspaceId,
          fileId: fileIds[0],
          fileIds,
          name: files.length === 1 ? files[0].name.replace(/\.[^.]+$/, "") : label,
        });
        await pollJobUntilDone(getToken, dataset.jobId, (step) =>
          setPhase({ step: "uploading", label: step }),
        );
        setPhase({ step: "done", datasetId: dataset.datasetId, filename: label });
      } catch (error) {
        const message =
          error instanceof Error && error.message
            ? error.message
            : "Upload failed. Please try again.";
        setPhase({ step: "error", message });
      }
    },
    [workspaceId, getToken],
  );

  if (!isLoaded) {
    return <p className="text-sm text-neutral-500">Loading session…</p>;
  }
  if (!isSignedIn) {
    return (
      <div className="rounded-xl border border-neutral-200 bg-white p-6 text-sm text-neutral-600">
        <Link href="/sign-in" className="font-medium text-neutral-900 underline">
          Sign in
        </Link>{" "}
        to upload data.
      </div>
    );
  }

  if (phase.step === "done") {
    return (
      <div className="rounded-xl border border-green-200 bg-green-50 p-8 text-center">
        <p className="font-medium text-green-900">
          {phase.filename} was parsed and profiled successfully.
        </p>
        <div className="mt-4 flex justify-center gap-3">
          <Link
            href={`/app/datasets/${phase.datasetId}`}
            className="rounded-lg bg-green-700 px-4 py-2 text-sm font-medium text-white hover:bg-green-800"
          >
            See what Picxify detected
          </Link>
          <button
            type="button"
            onClick={() => setPhase({ step: "idle" })}
            className="rounded-lg border border-green-300 px-4 py-2 text-sm font-medium text-green-900 hover:bg-green-100"
          >
            Upload another file
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const files = Array.from(event.dataTransfer.files ?? []);
          if (files.length) void handleFiles(files);
        }}
        className={`flex h-56 cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed bg-white px-8 text-center transition-colors ${
          dragging ? "border-neutral-900 bg-neutral-50" : "border-neutral-300"
        }`}
      >
        {phase.step === "uploading" ? (
          <p className="text-sm font-medium text-neutral-700">{phase.label}</p>
        ) : (
          <>
            <p className="font-medium text-neutral-900">
              Drop CSV or Excel files here, or click to browse
            </p>
            <p className="text-sm text-neutral-500">
              CSV, TSV, TXT, XLSX, XLS, PDF — up to 10 MB each. Drop several related files
              (e.g. orders + customers) to combine or join them automatically.
            </p>
          </>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED}
        multiple
        className="hidden"
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          if (files.length) void handleFiles(files);
          event.target.value = "";
        }}
      />
      {phase.step === "error" && (
        <p className="mt-3 text-sm text-red-600">{phase.message}</p>
      )}
      {!workspaceId && phase.step === "idle" && (
        <p className="mt-3 text-sm text-neutral-500">Preparing your workspace…</p>
      )}
    </div>
  );
}
