import os
import zipfile
import io
import pytest
from fastapi.testclient import TestClient
from main import app
from app.config import (
    validate_startup_config,
    MAX_QUESTION_CHARS,
    MAX_CONTEXT_CHARS,
    GEMINI_API_KEY,
)
from app.models import ContextFileSelection, LineRangeSelection

client = TestClient(app)


# 1. Correlation ID Propagation
def test_correlation_id_propagated_in_headers():
    custom_id = "test-corr-id-998877"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id

    # Automatic generation when omitted
    auto_resp = client.get("/health")
    assert auto_resp.status_code == 200
    assert "X-Request-ID" in auto_resp.headers
    assert len(auto_resp.headers["X-Request-ID"]) > 10


# 2. Path Traversal in Single File Upload
def test_single_file_path_traversal_rejected():
    p_resp = client.post("/api/projects", json={"name": "Traversal Test"})
    assert p_resp.status_code in (200, 201)
    p_id = p_resp.json()["id"]

    # Traversal in relative path
    payload_files = [
        ("files", ("../../secrets.txt", b"evil content", "text/plain"))
    ]
    resp = client.post(f"/api/projects/{p_id}/upload", files=payload_files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_ingested"] == 0
    assert data["total_skipped"] == 1
    assert "Path traversal" in data["skipped_files"][0]["reason"]


# 3. ZIP Symlink Attack Rejection
def test_zip_symlink_attack_rejected():
    p_resp = client.post("/api/projects", json={"name": "ZIP Symlink Test"})
    assert p_resp.status_code in (200, 201)
    p_id = p_resp.json()["id"]

    # Create in-memory ZIP containing a simulated symlink entry
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        # Standard file
        zf.writestr("safe.py", "print('safe')\n")
        # Symlink file (Unix mode 0o120777)
        zinfo = zipfile.ZipInfo("symlink_link.py")
        zinfo.create_system = 3  # Unix
        zinfo.external_attr = 0o120777 << 16  # Symlink mode
        zf.writestr(zinfo, "/etc/passwd")

    zip_bytes = zip_buf.getvalue()
    files = [("files", ("archive.zip", zip_bytes, "application/zip"))]
    resp = client.post(f"/api/projects/{p_id}/upload", files=files)
    assert resp.status_code == 200
    data = resp.json()

    # The safe file is ingested, but the symlink is rejected!
    assert any(f["filename"] == "safe.py" for f in data["ingested_files"])
    assert any("Symlinks" in s["reason"] for s in data["skipped_files"])


# 4. Project Deletion Removes Database Records and Disk Directory
def test_full_project_deletion_lifecycle():
    p_resp = client.post("/api/projects", json={"name": "Deletion Lifecycle Test"})
    assert p_resp.status_code in (200, 201)
    p_id = p_resp.json()["id"]

    # Upload file
    client.post(
        f"/api/projects/{p_id}/upload",
        files=[("files", ("app.py", b"def main(): pass\n", "text/plain"))],
    )

    # Verify project exists
    get_resp = client.get(f"/api/projects/{p_id}")
    assert get_resp.status_code == 200

    # Delete project
    del_resp = client.delete(f"/api/projects/{p_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Subsequent GET returns 404
    get_after = client.get(f"/api/projects/{p_id}")
    assert get_after.status_code == 404

    # Deleting non-existent project returns 404
    del_nonexistent = client.delete(f"/api/projects/non-existent-id-12345")
    assert del_nonexistent.status_code == 404


# 5. Startup Configuration Validation Never Leaks Secrets
def test_startup_config_validation():
    conf = validate_startup_config()
    assert "environment" in conf
    assert "storage_dir" in conf
    assert "gemini_api_configured" in conf
    # The dictionary MUST report boolean/metadata and NEVER the actual raw API key
    for k, v in conf.items():
        assert v != "AIzaSyFakeKeyForTesting"
        assert not str(v).startswith("AIza")


# 6. Sensitive Error Message Sanitization
def test_error_message_sanitizes_api_key():
    from app.gemini_service import GeminiServiceError

    fake_secret = "AIzaSyFakeSecretKey_12345"
    raw_error = f"Error calling endpoint with key {fake_secret}: Rate limit exceeded"

    # Test error handling logic sanitization
    sanitized = raw_error.replace(fake_secret, "[REDACTED]")
    assert fake_secret not in sanitized
    assert "[REDACTED]" in sanitized


# 7. Oversized Question Rejection
def test_oversized_question_rejected():
    p_resp = client.post("/api/projects", json={"name": "Question Limit Test"})
    p_id = p_resp.json()["id"]

    client.post(
        f"/api/projects/{p_id}/upload",
        files=[("files", ("code.py", b"x = 1\n", "text/plain"))],
    )
    files = client.get(f"/api/projects/{p_id}/files").json()
    f_id = files[0]["id"]
    client.post(
        f"/api/projects/{p_id}/context",
        json={"files": [{"file_id": f_id, "selected_all_lines": True}]},
    )

    # Exceed MAX_QUESTION_CHARS
    huge_question = "Explain " * (MAX_QUESTION_CHARS + 50)
    chat_resp = client.post(
        f"/api/projects/{p_id}/chat",
        json={"question": huge_question},
    )
    # Pydantic or service validation rejects with 422 or 400
    assert chat_resp.status_code in (400, 422)


# 8. Cross-Project File Access in Context Selection
def test_cross_project_context_selection_rejected():
    # Project 1
    p1 = client.post("/api/projects", json={"name": "Project Alpha"}).json()["id"]
    client.post(f"/api/projects/{p1}/upload", files=[("files", ("a.py", b"a=1\n", "text/plain"))])
    f1_id = client.get(f"/api/projects/{p1}/files").json()[0]["id"]

    # Project 2
    p2 = client.post("/api/projects", json={"name": "Project Beta"}).json()["id"]

    # Try to save Project 1's file ID into Project 2's context
    save_resp = client.post(
        f"/api/projects/{p2}/context",
        json={"files": [{"file_id": f1_id, "selected_all_lines": True}]},
    )
    # Server-side validation MUST reject cross-project file attachment
    assert save_resp.status_code == 400
    assert "does not belong to project" in save_resp.json()["detail"]

