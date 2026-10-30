import os
import logging
from fastapi import APIRouter, HTTPException, Query, status
from app.storage import storage
from app.config import PROJECTS_DIR
from app.chunking import chunk_file_content, is_file_eligible_for_chunking
from app.embedding_service import get_embedding_provider
from app.vector_store import (
    get_vector_store,
    ModelDimensionMismatchError,
    PGVECTOR_SETUP_GUIDANCE,
)
from app.models import (
    IndexRequest,
    IndexResponse,
    IndexStatusResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
    IndexDeleteResponse,
)

logger = logging.getLogger("contextcontrol.discovery")

router = APIRouter(prefix="/api/projects/{project_id}", tags=["Semantic Discovery"])


@router.post("/index", response_model=IndexResponse)
def index_project_codebase(project_id: str, request: IndexRequest = IndexRequest()):
    """
    Splits eligible project source files into bounded chunks, computes embeddings,
    and indexes them in pgvector (or mock store for testing).
    """
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    store = get_vector_store(use_mock=request.use_mock)
    available, msg = store.is_available()
    if not available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "Vector storage is not configured or unavailable",
                "pgvector_enabled": False,
                "setup_guidance": msg,
            },
        )

    try:
        provider = get_embedding_provider(use_mock=request.use_mock)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize embedding provider: {e}",
        )

    files = storage.get_project_files(project_id)
    project_dir = os.path.join(PROJECTS_DIR, project_id, "files")

    all_chunks = []
    total_eligible_files = 0

    for f in files:
        eligible, _ = is_file_eligible_for_chunking(f["relative_path"])
        if not eligible:
            continue

        file_disk_path = f.get("stored_path") or os.path.join(project_dir, f["relative_path"])
        if not os.path.isfile(file_disk_path):
            continue

        try:
            with open(file_disk_path, "r", encoding="utf-8", errors="replace") as fh:
                raw_text = fh.read()
        except Exception:
            continue

        total_eligible_files += 1
        chunks = chunk_file_content(
            project_id=project_id,
            file_id=f["id"],
            relative_path=f["relative_path"],
            raw_content=raw_text,
            embedding_model=provider.get_model_name(),
            embedding_dimension=provider.get_dimension(),
        )
        all_chunks.extend(chunks)

    if not all_chunks:
        return IndexResponse(
            project_id=project_id,
            status="empty",
            total_files=total_eligible_files,
            indexed_chunks=0,
            skipped_chunks=0,
            failed_chunks=0,
            embedding_model=provider.get_model_name(),
            embedding_dimension=provider.get_dimension(),
            pgvector_enabled=not getattr(store, "is_mock", False),
            message="No eligible source code found to index",
        )

    # Generate embeddings
    try:
        chunk_texts = [c.content for c in all_chunks]
        embeddings = provider.embed_texts(chunk_texts)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate embeddings: {e}",
        )

    # Store in vector store
    try:
        indexed, skipped = store.index_chunks(
            project_id=project_id,
            chunks=all_chunks,
            embeddings=embeddings,
            model=provider.get_model_name(),
            dimension=provider.get_dimension(),
            force_reindex=request.force_reindex,
        )
    except ModelDimensionMismatchError as mde:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(mde),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save vectors in storage: {e}",
        )

    return IndexResponse(
        project_id=project_id,
        status="completed",
        total_files=total_eligible_files,
        indexed_chunks=indexed,
        skipped_chunks=skipped,
        failed_chunks=0,
        embedding_model=provider.get_model_name(),
        embedding_dimension=provider.get_dimension(),
        pgvector_enabled=not getattr(store, "is_mock", False),
        message=f"Indexed {indexed} chunks, skipped {skipped} unchanged chunks",
    )


@router.get("/index/status", response_model=IndexStatusResponse)
def get_project_index_status(
    project_id: str,
    use_mock: bool = Query(default=False),
):
    """Returns indexing and vector store status for the project."""
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    store = get_vector_store(use_mock=use_mock)
    st = store.get_status(project_id)

    from app.config import EMBEDDING_PROVIDER

    return IndexStatusResponse(
        project_id=project_id,
        configured=st.get("configured", False),
        pgvector_enabled=st.get("pgvector_enabled", False),
        is_mock=st.get("is_mock", False),
        embedding_provider="mock" if use_mock else EMBEDDING_PROVIDER,
        embedding_model=st.get("embedding_model", "unknown"),
        embedding_dimension=st.get("embedding_dimension", 768),
        total_indexed_files=st.get("total_indexed_files", 0),
        total_chunks=st.get("total_chunks", 0),
        last_indexed_at=st.get("last_indexed_at"),
        setup_guidance=st.get("setup_guidance"),
    )


@router.post("/search-context", response_model=SemanticSearchResponse)
def search_project_context(
    project_id: str,
    request: SemanticSearchRequest,
):
    """
    Performs semantic vector search against indexed code chunks for a project.
    Returns ranked candidate snippets with proximity scores.
    Core Rule: Does NOT lock, select, or authorize code for AI chat requests.
    """
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    store = get_vector_store(use_mock=request.use_mock)
    available, msg = store.is_available()
    if not available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "Vector storage is not configured",
                "pgvector_enabled": False,
                "setup_guidance": msg,
            },
        )

    try:
        provider = get_embedding_provider(use_mock=request.use_mock)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize embedding provider: {e}",
        )

    # Generate query embedding
    try:
        query_vec = provider.embed_query(request.query)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate query embedding: {e}",
        )

    # Search vector store strictly scoped to project_id
    try:
        results = store.search(
            project_id=project_id,
            query_embedding=query_vec,
            top_k=request.top_k,
            min_score=request.min_score,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vector search execution failed: {e}",
        )

    return SemanticSearchResponse(
        project_id=project_id,
        query=request.query,
        results=results,
        total_results=len(results),
        model_used=provider.get_model_name(),
    )


@router.delete("/index", response_model=IndexDeleteResponse)
def delete_project_index(
    project_id: str,
    use_mock: bool = Query(default=False),
):
    """
    Deletes all vector embeddings and chunks for this project from vector storage.
    Original uploaded source files in project storage remain intact.
    """
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    store = get_vector_store(use_mock=use_mock)
    deleted_count = store.delete_project_index(project_id)

    return IndexDeleteResponse(
        project_id=project_id,
        deleted_chunks_count=deleted_count,
        status="deleted",
        message=f"Deleted {deleted_count} indexed chunks for project '{project_id}'. Original files are preserved.",
    )
