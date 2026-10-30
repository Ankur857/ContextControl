import os
import io
import zipfile
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from app.config import (
    SUPPORTED_EXTENSIONS,
    FORBIDDEN_DIR_NAMES,
    FORBIDDEN_FILE_EXACT_NAMES,
    FORBIDDEN_FILE_EXTENSIONS,
    MAX_FILE_COUNT_PER_UPLOAD,
    MAX_SINGLE_FILE_SIZE_BYTES,
    MAX_ZIP_SIZE_BYTES,
)


class FileValidationError(Exception):
    pass


def is_safe_relative_path(rel_path: str, base_dir: str) -> bool:
    """
    Verifies that a relative path does not escape base_dir via directory traversal,
    absolute paths, or drive letters.
    """
    # Reject empty or null byte
    if not rel_path or "\0" in rel_path:
        return False

    # Normalize slashes
    normalized = rel_path.replace("\\", "/").strip()

    # Reject absolute paths or Windows drive letters
    if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
        return False

    # Check for path traversal elements
    parts = [p for p in normalized.split("/") if p]
    if ".." in parts:
        return False

    # Resolve target and check containment
    try:
        base_abs = os.path.abspath(base_dir)
        target_abs = os.path.abspath(os.path.join(base_abs, *parts))
        common = os.path.commonpath([base_abs, target_abs])
        return common == base_abs and target_abs != base_abs
    except (ValueError, Exception):
        return False


def is_forbidden_directory(rel_path: str) -> Optional[str]:
    """
    Checks if any segment of rel_path is an ignored/forbidden directory.
    Returns the forbidden directory name if found, else None.
    """
    normalized = rel_path.replace("\\", "/").strip("/")
    parts = normalized.split("/")
    for part in parts[:-1]:  # check parent folders
        if part in FORBIDDEN_DIR_NAMES or part.startswith(".git"):
            return part
    return None


def is_secret_file(filename: str) -> Optional[str]:
    """
    Detects potential secrets, private keys, or environment files.
    Allowed exception: .env.example
    """
    lower = filename.lower()
    if lower == ".env.example":
        return None

    if lower.startswith(".env") or lower in FORBIDDEN_FILE_EXACT_NAMES:
        return f"Secret/environment file not permitted: '{filename}'"

    ext = Path(filename).suffix.lower()
    if ext in {".pem", ".key", ".p12", ".pfx", ".kdbx"}:
        return f"Private key/credential certificate not permitted: '{filename}'"

    if lower.startswith("id_rsa") or lower.startswith("id_ed25519"):
        return f"SSH private key file not permitted: '{filename}'"

    return None


def is_supported_file(filename: str) -> Tuple[bool, Optional[str]]:
    """
    Checks whether the file extension is supported for text evidence.
    """
    ext = Path(filename).suffix.lower()
    lower_name = filename.lower()

    # Special case for .env.example
    if lower_name == ".env.example":
        return True, None

    if ext in FORBIDDEN_FILE_EXTENSIONS:
        return False, f"Unsupported binary or restricted file type '{ext}'"

    if ext not in SUPPORTED_EXTENSIONS:
        return False, f"File extension '{ext or 'none'}' is not in allowed source extensions list"

    return True, None


def count_lines_safely(content_bytes: bytes) -> int:
    """
    Decodes text bytes and counts lines without executing or choking on encoding.
    """
    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content_bytes.decode("latin-1")
        except Exception:
            text = content_bytes.decode("utf-8", errors="replace")

    return max(1, len(text.splitlines()))


def process_single_file(
    content: bytes,
    filename: str,
    target_base_dir: str,
    relative_path: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
    """
    Validates and writes a single file into target_base_dir.
    Returns (saved_file_dict, None) or (None, skipped_warning_dict).
    """
    rel_path = relative_path or filename
    rel_path = rel_path.replace("\\", "/").strip("/")

    # Check path safety
    if not is_safe_relative_path(rel_path, target_base_dir):
        return None, {"path": rel_path, "reason": "Path traversal or unsafe path rejected"}

    # Check forbidden directory
    forbidden_dir = is_forbidden_directory(rel_path)
    if forbidden_dir:
        return None, {"path": rel_path, "reason": f"Ignored directory '{forbidden_dir}'"}

    # Check secrets
    basename = os.path.basename(rel_path)
    secret_reason = is_secret_file(basename)
    if secret_reason:
        return None, {"path": rel_path, "reason": secret_reason}

    # Check supported extension
    supported, ext_reason = is_supported_file(basename)
    if not supported:
        return None, {"path": rel_path, "reason": ext_reason or "Unsupported file type"}

    # Check size limit
    file_size = len(content)
    if file_size > MAX_SINGLE_FILE_SIZE_BYTES:
        return None, {
            "path": rel_path,
            "reason": f"File size ({file_size} bytes) exceeds {MAX_SINGLE_FILE_SIZE_BYTES} bytes limit",
        }

    # Safe to write
    dest_path = os.path.join(target_base_dir, *rel_path.split("/"))
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(content)

    line_count = count_lines_safely(content)
    ext = Path(basename).suffix.lstrip(".").lower() or "text"

    return {
        "filename": basename,
        "relative_path": rel_path,
        "file_type": ext,
        "size_bytes": file_size,
        "line_count": line_count,
        "stored_path": dest_path,
    }, None


def process_zip_archive(
    zip_bytes: bytes,
    target_base_dir: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """
    Safely validates and extracts entries from a ZIP archive into target_base_dir.
    Returns (list_of_saved_files, list_of_skipped_warnings).
    """
    if len(zip_bytes) > MAX_ZIP_SIZE_BYTES:
        raise FileValidationError(
            f"ZIP archive size ({len(zip_bytes)} bytes) exceeds maximum limit of {MAX_ZIP_SIZE_BYTES} bytes"
        )

    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except (zipfile.BadZipFile, Exception) as e:
        raise FileValidationError(f"Invalid or corrupted ZIP archive: {str(e)}")

    entries = archive.infolist()
    if len(entries) > MAX_FILE_COUNT_PER_UPLOAD:
        raise FileValidationError(
            f"ZIP archive contains {len(entries)} entries, exceeding the maximum limit of {MAX_FILE_COUNT_PER_UPLOAD} files"
        )

    saved_files: List[Dict[str, Any]] = []
    skipped_files: List[Dict[str, str]] = []

    for entry in entries:
        # Ignore folder entries
        if entry.is_dir() or entry.filename.endswith("/"):
            continue

        rel_path = entry.filename.replace("\\", "/").strip("/")

        # Check for Unix symlinks or FIFO/device special files in ZIP attributes
        unix_mode = entry.external_attr >> 16
        if unix_mode and (unix_mode & 0o120000 == 0o120000 or unix_mode & 0o020000 == 0o020000):
            skipped_files.append({
                "path": rel_path,
                "reason": "Symlinks, devices, or special Unix files in ZIP entries are rejected",
            })
            continue

        # 1. Path traversal check on entry name
        if not is_safe_relative_path(rel_path, target_base_dir):
            skipped_files.append({
                "path": rel_path,
                "reason": "Path traversal or unsafe path rejected in ZIP entry",
            })
            continue

        # 2. Check forbidden directories (.git, node_modules, etc.)
        forbidden_dir = is_forbidden_directory(rel_path)
        if forbidden_dir:
            skipped_files.append({
                "path": rel_path,
                "reason": f"Ignored directory '{forbidden_dir}'",
            })
            continue

        # 3. Check secrets
        basename = os.path.basename(rel_path)
        secret_reason = is_secret_file(basename)
        if secret_reason:
            skipped_files.append({
                "path": rel_path,
                "reason": secret_reason,
            })
            continue

        # 4. Check supported file extension
        supported, ext_reason = is_supported_file(basename)
        if not supported:
            skipped_files.append({
                "path": rel_path,
                "reason": ext_reason or "Unsupported file type",
            })
            continue

        # 5. Check uncompressed size
        if entry.file_size > MAX_SINGLE_FILE_SIZE_BYTES:
            skipped_files.append({
                "path": rel_path,
                "reason": f"Uncompressed file size exceeds {MAX_SINGLE_FILE_SIZE_BYTES} bytes limit",
            })
            continue

        # Read content safely
        try:
            content = archive.read(entry)
        except Exception as e:
            skipped_files.append({
                "path": rel_path,
                "reason": f"Failed reading entry from ZIP: {str(e)}",
            })
            continue

        # Write to target
        dest_path = os.path.join(target_base_dir, *rel_path.split("/"))
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(content)

        line_count = count_lines_safely(content)
        ext = Path(basename).suffix.lstrip(".").lower() or "text"

        saved_files.append({
            "filename": basename,
            "relative_path": rel_path,
            "file_type": ext,
            "size_bytes": len(content),
            "line_count": line_count,
            "stored_path": dest_path,
        })

    return saved_files, skipped_files

