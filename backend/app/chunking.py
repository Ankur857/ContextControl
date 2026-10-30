import re
import hashlib
from typing import List, Optional, Tuple
from app.config import (
    CHUNK_SIZE_LINES,
    CHUNK_OVERLAP_LINES,
    MAX_FILE_LINES_FOR_CHUNKING,
    FORBIDDEN_DIR_NAMES,
    FORBIDDEN_FILE_EXACT_NAMES,
    FORBIDDEN_FILE_EXTENSIONS,
)
from app.models import CodeChunk


# Regex patterns for identifying top-level logical boundaries in common languages
PYTHON_BOUNDARY = re.compile(r"^(?:async\s+)?def\s+[a-zA-Z0-9_]+|class\s+[a-zA-Z0-9_]+")
JS_TS_BOUNDARY = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+[a-zA-Z0-9_]+|"
    r"^(?:export\s+)?class\s+[a-zA-Z0-9_]+|"
    r"^(?:export\s+)?(?:const|let|var)\s+[a-zA-Z0-9_]+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"
)
MARKDOWN_BOUNDARY = re.compile(r"^#{1,3}\s+\S+")


def is_file_eligible_for_chunking(relative_path: str) -> Tuple[bool, str]:
    """
    Validates whether a file should be chunked and indexed.
    Rejects forbidden directories, secret file names, binaries, and unsupported extensions.
    """
    clean_path = relative_path.replace("\\", "/").strip("/")
    parts = clean_path.split("/")
    filename = parts[-1] if parts else ""
    basename = filename.lower()

    # Reject forbidden directory trees
    for part in parts[:-1]:
        if part in FORBIDDEN_DIR_NAMES:
            return False, f"Directory '{part}' is in forbidden directories"

    # Reject forbidden exact filenames (.env, id_rsa, etc.)
    if basename in FORBIDDEN_FILE_EXACT_NAMES or any(
        basename.startswith(prefix) for prefix in [".env"]
    ):
        return False, f"File '{filename}' is a forbidden credentials/environment file"

    # Reject binary / dangerous extensions
    lower_ext = "." + filename.split(".")[-1].lower() if "." in filename else ""
    if lower_ext in FORBIDDEN_FILE_EXTENSIONS:
        return False, f"Extension '{lower_ext}' is forbidden"

    return True, "Eligible"


def compute_content_hash(text: str) -> str:
    """Computes a deterministic SHA-256 hash prefix for chunk content deduplication."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def detect_logical_split_points(lines: List[str], file_extension: str) -> List[int]:
    """
    Detects 0-indexed line indices where logical structures begin.
    Returns a sorted list of line start indices.
    """
    ext = file_extension.lower()
    split_indices = [0]

    pattern: Optional[re.Pattern] = None
    if ext == ".py":
        pattern = PYTHON_BOUNDARY
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        pattern = JS_TS_BOUNDARY
    elif ext in (".md", ".markdown"):
        pattern = MARKDOWN_BOUNDARY

    if pattern:
        for idx, line in enumerate(lines):
            if idx > 0 and pattern.search(line):
                split_indices.append(idx)

    return sorted(list(set(split_indices)))


def chunk_file_content(
    project_id: str,
    file_id: str,
    relative_path: str,
    raw_content: str,
    embedding_model: str,
    embedding_dimension: int,
    chunk_size: int = CHUNK_SIZE_LINES,
    chunk_overlap: int = CHUNK_OVERLAP_LINES,
) -> List[CodeChunk]:
    """
    Splits file content into deterministic, line-bounded CodeChunks.
    Respects logical boundaries where feasible, with line-based windowing fallback.
    Preserves exact 1-indexed line numbers and content hashes.
    """
    eligible, reason = is_file_eligible_for_chunking(relative_path)
    if not eligible:
        return []

    # Handle empty files safely
    if not raw_content or not raw_content.strip():
        return []

    # Split lines preserving exact line text without modifying code
    lines = raw_content.splitlines(keepends=False)
    total_lines = len(lines)

    if total_lines == 0:
        return []

    # Oversized file handling: cap at max lines to prevent unbounded resource consumption
    if total_lines > MAX_FILE_LINES_FOR_CHUNKING:
        lines = lines[:MAX_FILE_LINES_FOR_CHUNKING]
        total_lines = MAX_FILE_LINES_FOR_CHUNKING

    ext = "." + relative_path.split(".")[-1].lower() if "." in relative_path else ""
    logical_starts = detect_logical_split_points(lines, ext)

    windows: List[Tuple[int, int]] = []  # (start_line_1_indexed, end_line_1_indexed)

    if len(logical_starts) > 1:
        # Build chunks from logical boundaries
        for i in range(len(logical_starts)):
            start_0 = logical_starts[i]
            end_0 = logical_starts[i + 1] if i + 1 < len(logical_starts) else total_lines
            section_len = end_0 - start_0

            if section_len <= chunk_size * 2:
                windows.append((start_0 + 1, end_0))
            else:
                # Subdivide oversized logical sections into overlapping sub-windows
                curr = start_0
                step = max(1, chunk_size - chunk_overlap)
                while curr < end_0:
                    win_end = min(end_0, curr + chunk_size)
                    windows.append((curr + 1, win_end))
                    if win_end == end_0:
                        break
                    curr += step
    else:
        # Line-based fallback sliding window
        step = max(1, chunk_size - chunk_overlap)
        curr = 0
        while curr < total_lines:
            end_0 = min(total_lines, curr + chunk_size)
            windows.append((curr + 1, end_0))
            if end_0 == total_lines:
                break
            curr += step

    chunks: List[CodeChunk] = []
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()

    for start_line, end_line in windows:
        # Extract lines for this chunk (1-indexed to 0-indexed slice)
        chunk_lines = lines[start_line - 1 : end_line]
        chunk_text = "\n".join(chunk_lines).strip()
        if not chunk_text:
            continue

        c_hash = compute_content_hash(chunk_text)
        chunk_id = f"{file_id}_L{start_line}_L{end_line}_{c_hash}"

        chunk = CodeChunk(
            id=chunk_id,
            project_id=project_id,
            file_id=file_id,
            relative_path=relative_path,
            start_line=start_line,
            end_line=end_line,
            content=chunk_text,
            content_hash=c_hash,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
            created_at=now_iso,
        )
        chunks.append(chunk)

    return chunks

