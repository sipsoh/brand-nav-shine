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
