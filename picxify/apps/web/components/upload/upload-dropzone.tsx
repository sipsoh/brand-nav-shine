"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  completeUpload,
  presignUpload,
  putToPresignedUrl,
  syncUser,
} from "@/lib/api-client";
import { clerkEnabled } from "@/lib/auth";

const ACCEPTED = ".csv,.tsv,.txt,.xlsx,.xls";

type Phase =
  | { step: "idle" }
  | { step: "uploading"; label: string }
  | { step: "done"; fileId: string; filename: string }
  | { step: "error"; message: string };

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

  const handleFile = useCallback(
    async (file: File) => {
      if (!workspaceId) return;
      try {
        setPhase({ step: "uploading", label: "Requesting upload slot…" });
        const token = await getToken();
        if (!token) throw new Error("No session token.");
        const presigned = await presignUpload(token, {
          workspaceId,
          filename: file.name,
          mimeType: file.type || "application/octet-stream",
          sizeBytes: file.size,
        });
        setPhase({ step: "uploading", label: "Uploading to secure storage…" });
        await putToPresignedUrl(presigned.uploadUrl, file);
        setPhase({ step: "uploading", label: "Confirming upload…" });
        const completed = await completeUpload(token, presigned.fileId);
        setPhase({ step: "done", fileId: completed.fileId, filename: file.name });
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
          {phase.filename} uploaded successfully.
        </p>
        <p className="mt-1 text-sm text-green-800">
          Parsing and profiling arrive in Milestone 4 — your file is stored and ready.
        </p>
        <button
          type="button"
          onClick={() => setPhase({ step: "idle" })}
          className="mt-4 rounded-lg border border-green-300 px-4 py-2 text-sm font-medium text-green-900 hover:bg-green-100"
        >
          Upload another file
        </button>
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
          const file = event.dataTransfer.files?.[0];
          if (file) void handleFile(file);
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
              Drop a CSV or Excel file here, or click to browse
            </p>
            <p className="text-sm text-neutral-500">CSV, TSV, TXT, XLSX, XLS — up to 10 MB</p>
          </>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED}
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void handleFile(file);
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
