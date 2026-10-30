/**
 * ContextControl Frontend API Client
 * Centralized utility for communicating with the FastAPI backend.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export interface HealthResponse {
  status: string;
  service: string;
}

export interface FileMetadata {
  id: string;
  project_id: string;
  filename: string;
  relative_path: string;
  file_type: string;
  size_bytes: number;
  line_count: number;
  created_at: string;
}

export interface FileContentResponse {
  id: string;
  project_id: string;
  filename: string;
  relative_path: string;
  file_type: string;
  size_bytes: number;
  line_count: number;
  content: string;
  created_at: string;
}

export interface LineRangeSelection {
  start_line: number;
  end_line: number;
}

export interface ContextFileSelection {
  file_id: string;
  selected_all_lines: boolean;
  line_range?: LineRangeSelection | null;
}

export interface SavedContextFile {
  file_id: string;
  relative_path: string;
  filename: string;
  file_type: string;
  total_lines: number;
  selected_all_lines: boolean;
  start_line: number | null;
  end_line: number | null;
  selected_lines_count: number;
}

export interface ContextResponse {
  project_id: string;
  total_selected_files: number;
  total_selected_lines: number;
  selected_files: SavedContextFile[];
  updated_at: string | null;
}

export interface CitationItem {
  source_id: string;
  file_path: string;
  start_line: number;
  end_line: number;
  claim: string;
  verified: boolean;
  verification_reason?: string;
}

export interface ChatResponse {
  project_id: string;
  question: string;
  answer: string;
  citations: CitationItem[];
  insufficient_context: boolean;
  missing_context: string[];
  total_evidence_files: number;
  total_evidence_lines: number;
  model_used: string;
  timestamp: string;
}

export interface Project {
  id: string;
  name: string;
  created_at: string;
  file_count: number;
  total_size_bytes: number;
  files?: FileMetadata[];
}

export interface ProjectListResponse {
  projects: Project[];
  total: number;
}

export interface SkippedFileWarning {
  path: string;
  reason: string;
}

export interface UploadResponse {
  project_id: string;
  ingested_files: FileMetadata[];
  skipped_files: SkippedFileWarning[];
  total_ingested: number;
  total_skipped: number;
  message: string;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

// --- Phase 6: Evaluation Interfaces ---

export interface EvalResultItem {
  id: string;
  run_id: string;
  question_id: string;
  mode: string;
  question: string;
  model_answer: string;
  reference_answer: string;
  context_supplied: string;
  citations: CitationItem[];
  answer_correctness: number;
  citation_validity: number | null;
  evidence_coverage: number;
  unsupported_claim_rate: number;
  insufficient_context_handled: boolean;
  tokens_used: number;
  latency_ms: number;
  error?: string | null;
  reviewer_notes?: string | null;
}

export interface ModeComparisonSummary {
  mode: string;
  total_cases: number;
  avg_correctness: number;
  citation_validity_rate: number | null;
  unsupported_claim_rate: number;
  insufficient_context_accuracy: number;
  avg_latency_ms: number;
  avg_tokens: number;
}

export interface EvalRunResponse {
  id: string;
  dataset_id: string;
  model_name: string;
  status: string;
  modes: string[];
  total_cases: number;
  completed_cases: number;
  comparison: ModeComparisonSummary[];
  results: EvalResultItem[];
  created_at: string;
}

export interface EvalDatasetResponse {
  metadata: {
    dataset_id: string;
    name: string;
    description: string;
    version: string;
    total_questions: number;
    fixture_files: string[];
  };
  questions: Array<{
    id: string;
    category: string;
    question: string;
    scoped_context: Array<{ file: string; lines: number[] }>;
    reference_answer: string;
    reference_facts: string[];
    expect_insufficient_context: boolean;
    notes: string;
  }>;
}

/**
 * Checks the health status of the FastAPI backend.
 */
export async function checkBackendHealth(
  timeoutMs = 4000
): Promise<ApiResponse<HealthResponse>> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: "GET",
      signal: controller.signal,
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      return {
        success: false,
        error: `HTTP ${response.status}: ${response.statusText}`,
      };
    }

    const data: HealthResponse = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    clearTimeout(timeoutId);
    const message =
      err instanceof DOMException && err.name === "AbortError"
        ? "Connection timed out"
        : err instanceof Error
        ? err.message
        : "Failed to connect to backend";
    return { success: false, error: message };
  }
}

/**
 * Create a new project.
 */
export async function createProject(name: string): Promise<ApiResponse<Project>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/projects`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ name }),
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorBody.detail || `Failed to create project (HTTP ${response.status})`,
      };
    }

    const data: Project = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error creating project";
    return { success: false, error: message };
  }
}

/**
 * List all projects.
 */
export async function listProjects(): Promise<ApiResponse<ProjectListResponse>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/projects`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    if (!response.ok) {
      return {
        success: false,
        error: `Failed to fetch projects (HTTP ${response.status})`,
      };
    }

    const data: ProjectListResponse = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error fetching projects";
    return { success: false, error: message };
  }
}

/**
 * Retrieve a project by ID with its file metadata.
 */
export async function getProject(projectId: string): Promise<ApiResponse<Project>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorBody.detail || `Failed to fetch project (HTTP ${response.status})`,
      };
    }

    const data: Project = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error fetching project";
    return { success: false, error: message };
  }
}

/**
 * Delete a project and all associated files and context.
 */
export async function deleteProject(
  projectId: string
): Promise<ApiResponse<{ status: string; message: string }>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}`, {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorBody.detail || `Failed to delete project (HTTP ${response.status})`,
      };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error deleting project";
    return { success: false, error: message };
  }
}

/**
 * Retrieve a single file's content and line information.
 */
export async function getFileContent(
  projectId: string,
  fileId: string
): Promise<ApiResponse<FileContentResponse>> {
  try {
    const response = await fetch(
      `${API_BASE_URL}/api/projects/${projectId}/files/${fileId}`,
      {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
      }
    );

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorBody.detail || `Failed to fetch file content (HTTP ${response.status})`,
      };
    }

    const data: FileContentResponse = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error fetching file content";
    return { success: false, error: message };
  }
}

/**
 * Upload one or multiple files or a ZIP archive to a project.
 */
export async function uploadProjectFiles(
  projectId: string,
  files: File[]
): Promise<ApiResponse<UploadResponse>> {
  try {
    const formData = new FormData();
    for (const file of files) {
      formData.append("files", file);
    }

    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/upload`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorBody.detail || `Upload failed (HTTP ${response.status})`,
      };
    }

    const data: UploadResponse = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error during upload";
    return { success: false, error: message };
  }
}

/**
 * Save manual context selection for a project.
 */
export async function saveProjectContext(
  projectId: string,
  files: ContextFileSelection[]
): Promise<ApiResponse<ContextResponse>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/context`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ files }),
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorBody.detail || `Failed to save context (HTTP ${response.status})`,
      };
    }

    const data: ContextResponse = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error saving context";
    return { success: false, error: message };
  }
}

/**
 * Get saved context selection for a project.
 */
export async function getProjectContext(
  projectId: string
): Promise<ApiResponse<ContextResponse>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/context`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorBody.detail || `Failed to fetch context (HTTP ${response.status})`,
      };
    }

    const data: ContextResponse = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error fetching context";
    return { success: false, error: message };
  }
}

/**
 * Clear saved context selection for a project.
 */
export async function clearProjectContext(
  projectId: string
): Promise<ApiResponse<{ status: string; message: string }>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/context`, {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorBody.detail || `Failed to clear context (HTTP ${response.status})`,
      };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error clearing context";
    return { success: false, error: message };
  }
}

/**
 * Ask Gemini a question with strictly locked context evidence.
 */
export async function askProjectQuestion(
  projectId: string,
  question: string,
  files?: ContextFileSelection[]
): Promise<ApiResponse<ChatResponse>> {
  try {
    const body: Record<string, any> = { question };
    if (files && files.length > 0) {
      body.files = files;
    }

    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorBody.detail || `AI reasoning failed (HTTP ${response.status})`,
      };
    }

    const data: ChatResponse = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error communicating with AI service";
    return { success: false, error: message };
  }
}

// --- Phase 6: Evaluation API Functions ---

/**
 * Fetch benchmark evaluation dataset.
 */
export async function getEvaluationDataset(): Promise<ApiResponse<EvalDatasetResponse>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/evaluations/dataset`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    if (!response.ok) {
      return {
        success: false,
        error: `Failed to fetch dataset (HTTP ${response.status})`,
      };
    }

    const data: EvalDatasetResponse = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error fetching dataset";
    return { success: false, error: message };
  }
}

/**
 * Run evaluation suite across selected modes.
 */
export async function runEvaluation(payload: {
  dataset_id?: string;
  modes: string[];
  use_mock: boolean;
}): Promise<ApiResponse<EvalRunResponse>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/evaluations/run`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorBody.detail || `Evaluation run failed (HTTP ${response.status})`,
      };
    }

    const data: EvalRunResponse = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error running evaluation";
    return { success: false, error: message };
  }
}

/**
 * List all historical evaluation runs.
 */
export async function listEvaluationRuns(): Promise<ApiResponse<any[]>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/evaluations/runs`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    if (!response.ok) {
      return {
        success: false,
        error: `Failed to fetch runs (HTTP ${response.status})`,
      };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error fetching evaluation runs";
    return { success: false, error: message };
  }
}

/**
 * Retrieve an evaluation run with its detailed results.
 */
export async function getEvaluationRun(runId: string): Promise<ApiResponse<EvalRunResponse>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/evaluations/runs/${runId}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorBody.detail || `Failed to fetch run (HTTP ${response.status})`,
      };
    }

    const data: EvalRunResponse = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Network error fetching run details";
    return { success: false, error: message };
  }
}

// ==========================================
// Phase 7: Semantic Discovery & pgvector
// ==========================================

export interface IndexStatusResponse {
  project_id: string;
  configured: boolean;
  pgvector_enabled: boolean;
  is_mock: boolean;
  embedding_provider: string;
  embedding_model: string;
  embedding_dimension: number;
  total_indexed_files: number;
  total_chunks: number;
  last_indexed_at: string | null;
  setup_guidance: string | null;
}

export interface IndexResponse {
  project_id: string;
  status: string;
  total_files: number;
  indexed_chunks: number;
  skipped_chunks: number;
  failed_chunks: number;
  embedding_model: string;
  embedding_dimension: number;
  pgvector_enabled: boolean;
  message: string;
}

export interface SearchResultItem {
  chunk_id: string;
  file_id: string;
  relative_path: string;
  start_line: number;
  end_line: number;
  similarity_score: number;
  preview: string;
  source_text: string;
}

export interface SemanticSearchResponse {
  project_id: string;
  query: string;
  results: SearchResultItem[];
  total_results: number;
  model_used: string;
  disclaimer: string;
}

export interface IndexDeleteResponse {
  project_id: string;
  deleted_chunks_count: number;
  status: string;
  message: string;
}

/**
 * Fetch indexing and vector store status for a project.
 */
export async function getIndexStatus(
  projectId: string,
  useMock: boolean = false
): Promise<ApiResponse<IndexStatusResponse>> {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/projects/${projectId}/index/status?use_mock=${useMock}`,
      {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return {
        success: false,
        error: err.detail || `Failed to fetch index status (HTTP ${res.status})`,
      };
    }
    const data: IndexStatusResponse = await res.json();
    return { success: true, data };
  } catch (err: unknown) {
    return {
      success: false,
      error: err instanceof Error ? err.message : "Failed to load index status",
    };
  }
}

/**
 * Trigger code chunking and vector indexing for a project.
 */
export async function indexProjectCodebase(
  projectId: string,
  forceReindex: boolean = false,
  useMock: boolean = false
): Promise<ApiResponse<IndexResponse>> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/projects/${projectId}/index`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ force_reindex: forceReindex, use_mock: useMock }),
    });

    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detailMsg =
        typeof body.detail === "object"
          ? body.detail.error || JSON.stringify(body.detail)
          : body.detail;
      return {
        success: false,
        error: detailMsg || `Failed to index project (HTTP ${res.status})`,
      };
    }
    return { success: true, data: body };
  } catch (err: unknown) {
    return {
      success: false,
      error: err instanceof Error ? err.message : "Error triggering indexing",
    };
  }
}

/**
 * Search indexed project chunks semantically.
 */
export async function searchProjectContext(
  projectId: string,
  query: string,
  topK: number = 5,
  minScore: number = 0.0,
  useMock: boolean = false
): Promise<ApiResponse<SemanticSearchResponse>> {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/projects/${projectId}/search-context`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          query,
          top_k: topK,
          min_score: minScore,
          use_mock: useMock,
        }),
      }
    );

    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detailMsg =
        typeof body.detail === "object"
          ? body.detail.error || JSON.stringify(body.detail)
          : body.detail;
      return {
        success: false,
        error: detailMsg || `Semantic search failed (HTTP ${res.status})`,
      };
    }
    return { success: true, data: body };
  } catch (err: unknown) {
    return {
      success: false,
      error: err instanceof Error ? err.message : "Network error during search",
    };
  }
}

/**
 * Delete project index from vector store without deleting original source files.
 */
export async function deleteProjectIndex(
  projectId: string,
  useMock: boolean = false
): Promise<ApiResponse<IndexDeleteResponse>> {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/projects/${projectId}/index?use_mock=${useMock}`,
      {
        method: "DELETE",
        headers: { Accept: "application/json" },
      }
    );
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      return {
        success: false,
        error: body.detail || `Failed to delete index (HTTP ${res.status})`,
      };
    }
    return { success: true, data: body };
  } catch (err: unknown) {
    return {
      success: false,
      error: err instanceof Error ? err.message : "Error deleting index",
    };
  }
}

