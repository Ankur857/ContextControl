from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Project name")


class FileMetadata(BaseModel):
    id: str
    project_id: str
    filename: str
    relative_path: str
    file_type: str
    size_bytes: int
    line_count: int
    created_at: str


class FileContentResponse(BaseModel):
    id: str
    project_id: str
    filename: str
    relative_path: str
    file_type: str
    size_bytes: int
    line_count: int
    content: str
    created_at: str


class LineRangeSelection(BaseModel):
    start_line: int = Field(..., ge=1, description="Start line (1-indexed, inclusive)")
    end_line: int = Field(..., ge=1, description="End line (1-indexed, inclusive)")


class ContextFileSelection(BaseModel):
    file_id: str
    selected_all_lines: bool = True
    line_range: Optional[LineRangeSelection] = None


class ContextSaveRequest(BaseModel):
    files: List[ContextFileSelection] = Field(default_factory=list)


class SavedContextFile(BaseModel):
    file_id: str
    relative_path: str
    filename: str
    file_type: str
    total_lines: int
    selected_all_lines: bool
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    selected_lines_count: int


class ContextResponse(BaseModel):
    project_id: str
    total_selected_files: int
    total_selected_lines: int
    selected_files: List[SavedContextFile]
    updated_at: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    created_at: str
    file_count: int = 0
    total_size_bytes: int = 0
    files: Optional[List[FileMetadata]] = None


class ProjectListResponse(BaseModel):
    projects: List[ProjectResponse]
    total: int


class SkippedFileWarning(BaseModel):
    path: str
    reason: str


class UploadResponse(BaseModel):
    project_id: str
    ingested_files: List[FileMetadata]
    skipped_files: List[SkippedFileWarning]
    total_ingested: int
    total_skipped: int
    message: str


# --- Phase 5: Chat & Gemini Models ---


class ChatRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The developer question regarding the scoped codebase",
    )
    files: Optional[List[ContextFileSelection]] = Field(
        default=None,
        description="Optional explicit context selection override; if omitted, saved context is used",
    )


class CitationItem(BaseModel):
    source_id: str
    file_path: str
    start_line: int
    end_line: int
    claim: str
    verified: bool = False
    verification_reason: Optional[str] = None


class ChatResponse(BaseModel):
    project_id: str
    question: str
    answer: str
    citations: List[CitationItem]
    insufficient_context: bool
    missing_context: List[str]
    total_evidence_files: int
    total_evidence_lines: int
    model_used: str
    timestamp: str


# --- Phase 6: Evaluation Models ---


class EvalRunRequest(BaseModel):
    dataset_id: str = Field(
        default="context_control_eval_v1",
        description="Dataset identifier to run evaluation on",
    )
    modes: List[str] = Field(
        default=["baseline", "context_lock", "context_lock_citations"],
        description="Modes to execute and compare",
    )
    use_mock: bool = Field(
        default=False,
        description="If True, runs deterministic mock evaluations without live Gemini API costs",
    )


class EvalResultItem(BaseModel):
    id: str
    run_id: str
    question_id: str
    mode: str
    question: str
    model_answer: str
    reference_answer: str
    context_supplied: str
    citations: List[CitationItem]
    answer_correctness: float
    citation_validity: Optional[float] = None
    evidence_coverage: float
    unsupported_claim_rate: float
    insufficient_context_handled: bool
    tokens_used: int
    latency_ms: int
    error: Optional[str] = None
    reviewer_notes: Optional[str] = None


class ModeComparisonSummary(BaseModel):
    mode: str
    total_cases: int
    avg_correctness: float
    citation_validity_rate: Optional[float] = None
    unsupported_claim_rate: float
    insufficient_context_accuracy: float
    avg_latency_ms: float
    avg_tokens: float


class EvalRunResponse(BaseModel):
    id: str
    dataset_id: str
    model_name: str
    status: str
    modes: List[str]
    total_cases: int
    completed_cases: int
    comparison: List[ModeComparisonSummary]
    results: List[EvalResultItem]
    created_at: str


# --- Phase 7: Semantic Context Discovery & pgvector Models ---


class CodeChunk(BaseModel):
    id: str
    project_id: str
    file_id: str
    relative_path: str
    start_line: int
    end_line: int
    content: str
    content_hash: str
    embedding_model: str
    embedding_dimension: int
    created_at: str


class IndexRequest(BaseModel):
    force_reindex: bool = Field(
        default=False,
        description="Force recomputation of embeddings even if content hashes match",
    )
    use_mock: bool = Field(
        default=False,
        description="Use deterministic mock embeddings and storage for testing without external API or pgvector requirements",
    )


class IndexResponse(BaseModel):
    project_id: str
    status: str
    total_files: int
    indexed_chunks: int
    skipped_chunks: int
    failed_chunks: int
    embedding_model: str
    embedding_dimension: int
    pgvector_enabled: bool
    message: str


class IndexStatusResponse(BaseModel):
    project_id: str
    configured: bool
    pgvector_enabled: bool
    is_mock: bool = False
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    total_indexed_files: int
    total_chunks: int
    last_indexed_at: Optional[str] = None
    setup_guidance: Optional[str] = None


class SemanticSearchRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=2,
        max_length=1000,
        description="Natural language question or code description to search for",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of candidate chunks to return",
    )
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum vector similarity score threshold",
    )
    use_mock: bool = Field(
        default=False,
        description="Use deterministic mock embeddings for testing",
    )


class SearchResultItem(BaseModel):
    chunk_id: str
    file_id: str
    relative_path: str
    start_line: int
    end_line: int
    similarity_score: float
    preview: str
    source_text: str


class SemanticSearchResponse(BaseModel):
    project_id: str
    query: str
    results: List[SearchResultItem]
    total_results: int
    model_used: str
    disclaimer: str = (
        "Similarity scores are vector proximity metrics, not probabilities of factual correctness. "
        "Semantic search only suggests candidate context; it does not automatically authorize or lock context for AI requests."
    )


class IndexDeleteResponse(BaseModel):
    project_id: str
    deleted_chunks_count: int
    status: str
    message: str

