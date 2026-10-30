import os
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status
from app.models import (
    ProjectCreate,
    ProjectResponse,
    ProjectListResponse,
    FileMetadata,
    FileContentResponse,
    UploadResponse,
    SkippedFileWarning,
    ContextSaveRequest,
    ContextResponse,
    ContextFileSelection,
    LineRangeSelection,
    ChatRequest,
    ChatResponse,
)
from app.storage import storage
from app.config import PROJECTS_DIR
from app.file_manager import (
    process_single_file,
    process_zip_archive,
    FileValidationError,
)
from app.gemini_service import execute_context_locked_chat, GeminiServiceError

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate):
    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project name cannot be empty",
        )
    project = storage.create_project(name=name)
    return project


@router.get("", response_model=ProjectListResponse)
def list_projects():
    projects = storage.list_projects()
    return {"projects": projects, "total": len(projects)}


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str):
    project = storage.get_project(project_id=project_id, include_files=True)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )
    return project


@router.delete("/{project_id}", status_code=status.HTTP_200_OK)
def delete_project(project_id: str):
    """
    Deletes an entire project workspace:
    - Removes project record, file metadata, and saved context from SQLite.
    - Removes stored files directory from disk.
    - Removes indexed vector chunks for this project from the vector store.
    """
    project = storage.get_project(project_id=project_id, include_files=False)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    # 1. Delete from SQLite database
    storage.delete_project(project_id)

    # 2. Delete files from disk storage
    import shutil
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir, ignore_errors=True)

    # 3. Clean up any vector chunks for this project
    try:
        from app.vector_store import get_vector_store
        store = get_vector_store(use_mock=False)
        store.delete_project_index(project_id)
        mock_store = get_vector_store(use_mock=True)
        mock_store.delete_project_index(project_id)
    except Exception:
        pass

    return {
        "status": "deleted",
        "project_id": project_id,
        "message": f"Project '{project['name']}' ({project_id}) and all associated files and context were deleted.",
    }


@router.get("/{project_id}/files", response_model=List[FileMetadata])
def get_project_files(project_id: str):
    project = storage.get_project(project_id=project_id, include_files=False)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )
    return storage.get_project_files(project_id=project_id)


@router.get("/{project_id}/files/{file_id}", response_model=FileContentResponse)
def get_file_content(project_id: str, file_id: str):
    project = storage.get_project(project_id=project_id, include_files=False)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    file_record = storage.get_file(project_id=project_id, file_id=file_id)
    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{file_id}' not found in project '{project_id}'",
        )

    stored_path = file_record["stored_path"]
    if not os.path.exists(stored_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored file content not found on disk",
        )

    try:
        with open(stored_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(stored_path, "r", encoding="latin-1") as f:
                content = f.read()
        except Exception:
            with open(stored_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed reading file content: {str(e)}",
        )

    return FileContentResponse(
        id=file_record["id"],
        project_id=file_record["project_id"],
        filename=file_record["filename"],
        relative_path=file_record["relative_path"],
        file_type=file_record["file_type"],
        size_bytes=file_record["size_bytes"],
        line_count=file_record["line_count"],
        content=content,
        created_at=file_record["created_at"],
    )


@router.post("/{project_id}/upload", response_model=UploadResponse)
async def upload_files(
    project_id: str,
    files: List[UploadFile] = File(...),
):
    project = storage.get_project(project_id=project_id, include_files=False)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    target_dir = os.path.join(PROJECTS_DIR, project_id, "files")
    os.makedirs(target_dir, exist_ok=True)

    ingested_records: List[FileMetadata] = []
    skipped_warnings: List[SkippedFileWarning] = []

    for upload in files:
        filename = upload.filename or "unnamed_file"
        try:
            content = await upload.read()
        except Exception as e:
            skipped_warnings.append(
                SkippedFileWarning(path=filename, reason=f"Failed reading upload stream: {str(e)}")
            )
            continue

        is_zip = (
            filename.lower().endswith(".zip")
            or upload.content_type in {"application/zip", "application/x-zip-compressed"}
        )

        if is_zip:
            try:
                saved_files, skipped_entries = process_zip_archive(content, target_dir)
                for sf in saved_files:
                    rec = storage.save_file_record(
                        project_id=project_id,
                        filename=sf["filename"],
                        relative_path=sf["relative_path"],
                        file_type=sf["file_type"],
                        size_bytes=sf["size_bytes"],
                        line_count=sf["line_count"],
                        stored_path=sf["stored_path"],
                    )
                    ingested_records.append(FileMetadata(**rec))

                for sk in skipped_entries:
                    skipped_warnings.append(
                        SkippedFileWarning(path=sk["path"], reason=sk["reason"])
                    )
            except FileValidationError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e),
                )
        else:
            saved_file, skipped_entry = process_single_file(
                content=content,
                filename=filename,
                target_base_dir=target_dir,
            )
            if saved_file:
                rec = storage.save_file_record(
                    project_id=project_id,
                    filename=saved_file["filename"],
                    relative_path=saved_file["relative_path"],
                    file_type=saved_file["file_type"],
                    size_bytes=saved_file["size_bytes"],
                    line_count=saved_file["line_count"],
                    stored_path=saved_file["stored_path"],
                )
                ingested_records.append(FileMetadata(**rec))
            elif skipped_entry:
                skipped_warnings.append(
                    SkippedFileWarning(path=skipped_entry["path"], reason=skipped_entry["reason"])
                )

    msg = f"Processed upload: {len(ingested_records)} files ingested, {len(skipped_warnings)} files skipped/rejected."
    return UploadResponse(
        project_id=project_id,
        ingested_files=ingested_records,
        skipped_files=skipped_warnings,
        total_ingested=len(ingested_records),
        total_skipped=len(skipped_warnings),
        message=msg,
    )


@router.post("/{project_id}/context", response_model=ContextResponse)
def save_project_context(project_id: str, payload: ContextSaveRequest):
    project = storage.get_project(project_id=project_id, include_files=False)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    formatted_selections = []
    seen_file_ids = set()

    for item in payload.files:
        if item.file_id in seen_file_ids:
            continue
        seen_file_ids.add(item.file_id)

        file_rec = storage.get_file(project_id=project_id, file_id=item.file_id)
        if not file_rec:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File ID '{item.file_id}' does not belong to project '{project_id}'",
            )

        start = None
        end = None
        all_lines = item.selected_all_lines

        if not all_lines and item.line_range:
            start = item.line_range.start_line
            end = item.line_range.end_line

            if start > end:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid line range for '{file_rec['relative_path']}': start_line ({start}) cannot exceed end_line ({end})",
                )
            if start < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid line range for '{file_rec['relative_path']}': start_line ({start}) must be >= 1",
                )
            if end > file_rec["line_count"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid line range for '{file_rec['relative_path']}': end_line ({end}) exceeds total lines ({file_rec['line_count']})",
                )
        else:
            all_lines = True

        formatted_selections.append({
            "file_id": item.file_id,
            "selected_all_lines": all_lines,
            "start_line": start,
            "end_line": end,
        })

    return storage.save_project_context(project_id=project_id, selections=formatted_selections)


@router.get("/{project_id}/context", response_model=ContextResponse)
def get_project_context(project_id: str):
    project = storage.get_project(project_id=project_id, include_files=False)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )
    return storage.get_project_context(project_id=project_id)


@router.delete("/{project_id}/context")
def clear_project_context(project_id: str):
    project = storage.get_project(project_id=project_id, include_files=False)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )
    storage.clear_project_context(project_id=project_id)
    return {
        "status": "ok",
        "message": "Context selection cleared successfully",
        "project_id": project_id,
    }


@router.post("/{project_id}/chat", response_model=ChatResponse)
async def chat_with_context(project_id: str, payload: ChatRequest):
    project = storage.get_project(project_id=project_id, include_files=False)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found",
        )

    # Reconstruct selections: use payload.files if provided, otherwise fallback to saved context
    selections: List[ContextFileSelection] = []

    if payload.files is not None and len(payload.files) > 0:
        selections = payload.files
    else:
        saved_context = storage.get_project_context(project_id)
        for sf in saved_context.get("selected_files", []):
            lr = None
            if not sf["selected_all_lines"] and sf["start_line"] and sf["end_line"]:
                lr = LineRangeSelection(
                    start_line=sf["start_line"], end_line=sf["end_line"]
                )
            selections.append(
                ContextFileSelection(
                    file_id=sf["file_id"],
                    selected_all_lines=sf["selected_all_lines"],
                    line_range=lr,
                )
            )

    if not selections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No context selected. Please select files or line ranges to lock context before asking a question.",
        )

    try:
        response = await execute_context_locked_chat(
            project_id=project_id,
            question=payload.question,
            selections=selections,
        )
        return response
    except GeminiServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while communicating with Gemini: {str(e)}",
        )
