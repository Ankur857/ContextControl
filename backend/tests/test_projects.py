import io
import os
import zipfile
import pytest
from fastapi.testclient import TestClient
from main import app
from app.config import PROJECTS_DIR

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "context-control-backend"}


def test_create_and_list_projects():
    # 1. Create project
    create_res = client.post("/api/projects", json={"name": "Test Auth System"})
    assert create_res.status_code == 201
    project_data = create_res.json()
    assert "id" in project_data
    assert project_data["name"] == "Test Auth System"
    assert project_data["file_count"] == 0

    project_id = project_data["id"]

    # 2. List projects
    list_res = client.get("/api/projects")
    assert list_res.status_code == 200
    projects = list_res.json()["projects"]
    assert any(p["id"] == project_id for p in projects)

    # 3. Retrieve single project
    get_res = client.get(f"/api/projects/{project_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == project_id
    assert get_res.json()["name"] == "Test Auth System"


def test_upload_individual_files():
    create_res = client.post("/api/projects", json={"name": "Upload Test Project"})
    project_id = create_res.json()["id"]

    py_content = b"def hello():\n    print('Hello ContextControl')\n"
    md_content = b"# Readme\nLine 2\nLine 3\n"

    files = [
        ("files", ("main.py", py_content, "text/x-python")),
        ("files", ("notes.md", md_content, "text/markdown")),
    ]

    upload_res = client.post(f"/api/projects/{project_id}/upload", files=files)
    assert upload_res.status_code == 200
    body = upload_res.json()
    assert body["total_ingested"] == 2
    assert body["total_skipped"] == 0

    # Verify project files endpoint
    files_res = client.get(f"/api/projects/{project_id}/files")
    assert files_res.status_code == 200
    file_list = files_res.json()
    filenames = [f["filename"] for f in file_list]
    assert "main.py" in filenames
    assert "notes.md" in filenames

    # Verify line count
    main_file = next(f for f in file_list if f["filename"] == "main.py")
    assert main_file["line_count"] == 2
    assert main_file["file_type"] == "py"


def test_upload_valid_zip():
    create_res = client.post("/api/projects", json={"name": "ZIP Test Project"})
    project_id = create_res.json()["id"]

    # Create in-memory zip archive
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("src/service.ts", "export const service = () => 'ok';\n")
        zf.writestr("config/settings.json", '{"debug": true}\n')
        zf.writestr("README.md", "# Documentation\n")

    zip_bytes = zip_buffer.getvalue()

    files = [
        ("files", ("bundle.zip", zip_bytes, "application/zip")),
    ]

    upload_res = client.post(f"/api/projects/{project_id}/upload", files=files)
    assert upload_res.status_code == 200
    data = upload_res.json()
    assert data["total_ingested"] == 3
    assert data["total_skipped"] == 0

    # Verify physical file existence in storage directory
    project_storage = os.path.join(PROJECTS_DIR, project_id, "files")
    assert os.path.exists(os.path.join(project_storage, "src", "service.ts"))
    assert os.path.exists(os.path.join(project_storage, "config", "settings.json"))


def test_path_traversal_zip_rejected():
    create_res = client.post("/api/projects", json={"name": "Security Traversal Test"})
    project_id = create_res.json()["id"]

    # Attempt to write outside target folder using ../ and absolute path
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../../evil_escape.txt", "MALICIOUS CONTENT")
        zf.writestr("safe_file.py", "print('safe')\n")

    zip_bytes = zip_buffer.getvalue()

    files = [
        ("files", ("exploit.zip", zip_bytes, "application/zip")),
    ]

    upload_res = client.post(f"/api/projects/{project_id}/upload", files=files)
    assert upload_res.status_code == 200
    data = upload_res.json()

    # Traversal entry should be in skipped_files, safe file should be ingested
    assert data["total_ingested"] == 1
    assert data["total_skipped"] == 1
    assert any("evil_escape.txt" in s["path"] for s in data["skipped_files"])

    # Ensure the malicious file does NOT exist outside the project directory
    project_storage = os.path.join(PROJECTS_DIR, project_id, "files")
    parent_dir = os.path.abspath(os.path.join(project_storage, "..", ".."))
    escaped_file = os.path.join(parent_dir, "evil_escape.txt")
    assert not os.path.exists(escaped_file)


def test_forbidden_directories_and_secrets_skipped():
    create_res = client.post("/api/projects", json={"name": "Filter Test Project"})
    project_id = create_res.json()["id"]

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("node_modules/express/index.js", "ignored code")
        zf.writestr(".git/HEAD", "ref: refs/heads/main")
        zf.writestr(".env", "SECRET_KEY=supersecret123")
        zf.writestr("id_rsa", "FAKE PRIVATE KEY")
        zf.writestr("program.exe", b"\x4d\x5a\x90\x00")
        zf.writestr(".env.example", "SAFE_PUBLIC_CONFIG=sample")
        zf.writestr("src/app.py", "print('allowed')\n")

    zip_bytes = zip_buffer.getvalue()

    files = [
        ("files", ("mixed.zip", zip_bytes, "application/zip")),
    ]

    upload_res = client.post(f"/api/projects/{project_id}/upload", files=files)
    assert upload_res.status_code == 200
    data = upload_res.json()

    # .env.example and src/app.py are ingested (2 files)
    # node_modules, .git, .env, id_rsa, program.exe are skipped (5 files)
    assert data["total_ingested"] == 2
    assert data["total_skipped"] == 5

    ingested_paths = [f["relative_path"] for f in data["ingested_files"]]
    assert "src/app.py" in ingested_paths
    assert ".env.example" in ingested_paths


def test_malformed_zip_handled_gracefully():
    create_res = client.post("/api/projects", json={"name": "Corrupt ZIP Project"})
    project_id = create_res.json()["id"]

    corrupt_bytes = b"NOT_A_VALID_ZIP_HEADER_CORRUPTED_STREAM"

    files = [
        ("files", ("corrupt.zip", corrupt_bytes, "application/zip")),
    ]

    upload_res = client.post(f"/api/projects/{project_id}/upload", files=files)
    # Malformed zip returns a clean HTTP 400 Bad Request
    assert upload_res.status_code == 400
    assert "Invalid or corrupted ZIP" in upload_res.json()["detail"]

