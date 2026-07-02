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

export interface SourceTrace {
  tableId: string;
  columns: string[];
  filters: string[];
  calculation: string;
  rowCount: number;
  generatedBy: "code" | "model_supported_by_code" | "user";
}

export interface ComputedFact {
  id: string;
  label: string;
  value: string | number | boolean | null;
  unit: string | null;
  sourceTrace: SourceTrace;
}

export interface ComputedInsight {
  id: string;
  headline: string;
  detail: string;
  insightType: string;
  severity: "positive" | "negative" | "neutral" | "warning" | "opportunity";
  confidence: number;
  facts: ComputedFact[];
  sourceTrace: SourceTrace;
}

export interface DatasetInsightsResponse {
  datasetId: string;
  tables: {
    tableId: string;
    tableName: string;
    facts: ComputedFact[];
    insights: ComputedInsight[];
  }[];
}

export function getDatasetInsights(
  token: string,
  datasetId: string,
): Promise<DatasetInsightsResponse> {
  return apiFetch<DatasetInsightsResponse>(`/datasets/${datasetId}/insights`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

// --- DashboardSpec (rendered subset of packages/schemas/dashboard_spec.schema.json) ---

export interface SpecWidget {
  id: string;
  type: string;
  title: string;
  subtitle?: string;
  size?: string;
  kpi?: {
    value: string | number;
    label: string;
    changeLabel?: string | null;
    direction?: "up" | "down" | "flat" | null;
    sourceTrace?: SourceTrace;
  } | null;
  chart?: {
    chartType: string;
    querySpec: Record<string, unknown>;
    takeaway?: string;
    echartsOption?: Record<string, unknown>;
    sourceTrace?: SourceTrace;
  } | null;
  insight?: SpecInsight | null;
  markdown?: string | null;
}

export interface SpecInsight {
  id: string;
  headline: string;
  detail: string;
  severity: string;
  confidence: number;
  facts: { label: string; value: string | number | boolean; unit?: string | null; sourceTrace: SourceTrace }[];
  recommendedAction?: string | null;
  sourceTrace: SourceTrace;
}

export interface DashboardSpec {
  version: string;
  dashboard: {
    title: string;
    subtitle: string;
    useCase: string;
    audience: string;
    theme: { name: string; tone: string };
    generatedAt: string;
  };
  dataSources: {
    datasetId: string;
    tableId: string;
    displayName: string;
    rowCount: number;
    columnCount: number;
  }[];
  assumptions: AssumptionSummary[];
  sections: { id: string; title: string; subtitle?: string; layout: string; widgets: SpecWidget[] }[];
  insights: SpecInsight[];
  actions: { label: string; priority: string; rationale: string; sourceInsightId?: string | null }[];
}

export interface DashboardDetail {
  dashboardId: string;
  title: string;
  subtitle: string | null;
  visibility: string;
  datasetId: string | null;
  currentVersion: {
    versionId: string;
    versionNumber: number;
    spec: DashboardSpec;
    generationMetadata: Record<string, unknown>;
  } | null;
}

export function generateDashboard(
  token: string,
  input: {
    workspaceId: string;
    datasetId: string;
    audience?: string;
    useCaseHint?: string;
    titleHint?: string;
  },
): Promise<{ dashboardId: string; jobId: string; status: string }> {
  return apiFetch("/dashboards/generate", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(input),
  });
}

export function getDashboard(token: string, dashboardId: string): Promise<DashboardDetail> {
  return apiFetch<DashboardDetail>(`/dashboards/${dashboardId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export interface DashboardListItem {
  dashboardId: string;
  title: string;
  visibility: string;
  createdAt: string;
  hasVersion: boolean;
}

export function listDashboards(
  token: string,
  workspaceId: string,
): Promise<{ dashboards: DashboardListItem[] }> {
  return apiFetch(`/dashboards?workspaceId=${workspaceId}`, {
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
