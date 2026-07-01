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
