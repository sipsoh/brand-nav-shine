const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    throw new ApiError(response.status, `API request failed: ${response.status} ${path}`);
  }
  return (await response.json()) as T;
}

export interface HealthResponse {
  ok: boolean;
  service: string;
  version: string;
}

export function getApiHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  slug: string | null;
  role: string;
}

export interface UserSyncResponse {
  user: { id: string; email: string; name: string | null };
  workspaces: WorkspaceSummary[];
  created: boolean;
}

export function syncUser(token: string): Promise<UserSyncResponse> {
  return apiFetch<UserSyncResponse>("/users/sync", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function listWorkspaces(token: string): Promise<{ workspaces: WorkspaceSummary[] }> {
  return apiFetch<{ workspaces: WorkspaceSummary[] }>("/workspaces", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export interface PresignResponse {
  fileId: string;
  uploadUrl: string;
  objectKey: string;
  expiresInSeconds: number;
}

export function presignUpload(
  token: string,
  input: { workspaceId: string; filename: string; mimeType: string; sizeBytes: number },
): Promise<PresignResponse> {
  return apiFetch<PresignResponse>("/uploads/presign", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(input),
  });
}

export function completeUpload(
  token: string,
  fileId: string,
): Promise<{ fileId: string; status: string }> {
  return apiFetch<{ fileId: string; status: string }>(`/uploads/${fileId}/complete`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export interface DatasetFromFileResponse {
  datasetId: string;
  jobId: string;
  status: string;
}

export function createDatasetFromFile(
  token: string,
  input: { workspaceId: string; fileId: string; name: string },
): Promise<DatasetFromFileResponse> {
  return apiFetch<DatasetFromFileResponse>("/datasets/from-file", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(input),
  });
}

export interface JobResponse {
  jobId: string;
  jobType: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  currentStep: string | null;
  errorMessage: string | null;
  output: Record<string, unknown>;
}

export function getJob(token: string, jobId: string): Promise<JobResponse> {
  return apiFetch<JobResponse>(`/jobs/${jobId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export interface DatasetColumn {
  id: string;
  name: string;
  normalizedName: string;
  detectedType: string;
  semanticType: string | null;
  roleHint: string | null;
  nullableRatio: number | null;
  uniqueRatio: number | null;
  stats: Record<string, unknown>;
  examples: unknown[];
  confidence: number | null;
}

export interface DatasetTable {
  id: string;
  name: string;
  normalizedName: string;
  rowCount: number;
  columnCount: number;
  sampleRows: Record<string, unknown>[];
  columns: DatasetColumn[];
}

export interface AssumptionSummary {
  id: string;
  label: string;
  status: "accepted" | "needs_review" | "rejected" | "system";
  confidence: number | null;
  editable: boolean;
  source: string;
  affectedColumns: string[];
}

export interface DatasetResponse {
  id: string;
  name: string;
  sourceType: string;
  rowCount: number | null;
  tableCount: number;
  qualityScore: number | null;
  useCaseCandidates: { useCase: string; confidence: number }[];
  tables: DatasetTable[];
  findings: { severity: string; findingType: string; message: string }[];
  assumptions: AssumptionSummary[];
}

export function updateAssumption(
  token: string,
  datasetId: string,
  assumptionId: string,
  patch: { status?: "accepted" | "rejected"; replacement?: { column: string; semanticType: string } },
): Promise<AssumptionSummary> {
  return apiFetch<AssumptionSummary>(`/datasets/${datasetId}/assumptions/${assumptionId}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(patch),
  });
}

export function getDataset(token: string, datasetId: string): Promise<DatasetResponse> {
  return apiFetch<DatasetResponse>(`/datasets/${datasetId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function putToPresignedUrl(uploadUrl: string, file: File): Promise<void> {
  const response = await fetch(uploadUrl, {
    method: "PUT",
    body: file,
    headers: file.type ? { "Content-Type": file.type } : undefined,
  });
  if (!response.ok) {
    throw new ApiError(response.status, "Upload to storage failed.");
  }
}
