import io
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_file_content_and_context_workflow():
    # 1. Create a project
    create_res = client.post("/api/projects", json={"name": "Context Workflow Project"})
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # 2. Upload sample files with multi-line content
    python_code = "line1 = 1\nline2 = 2\nline3 = 3\nline4 = 4\nline5 = 5\n"
    readme_text = "# Header\nFirst paragraph\nSecond paragraph\n"

    files = [
        ("files", ("calculator.py", python_code.encode("utf-8"), "text/x-python")),
        ("files", ("guide.md", readme_text.encode("utf-8"), "text/markdown")),
    ]

    upload_res = client.post(f"/api/projects/{project_id}/upload", files=files)
    assert upload_res.status_code == 200
    ingested = upload_res.json()["ingested_files"]
    assert len(ingested) == 2

    calc_file = next(f for f in ingested if f["filename"] == "calculator.py")
    guide_file = next(f for f in ingested if f["filename"] == "guide.md")
    assert calc_file["line_count"] == 5
    assert guide_file["line_count"] == 3

    # 3. Test GET file content endpoint
    content_res = client.get(f"/api/projects/{project_id}/files/{calc_file['id']}")
    assert content_res.status_code == 200
    file_data = content_res.json()
    assert file_data["filename"] == "calculator.py"
    assert file_data["line_count"] == 5
    assert "line3 = 3" in file_data["content"]

    # 4. Save Context: calc_file with custom lines 2 to 4, guide_file all lines
    context_payload = {
        "files": [
            {
                "file_id": calc_file["id"],
                "selected_all_lines": False,
                "line_range": {"start_line": 2, "end_line": 4},
            },
            {
                "file_id": guide_file["id"],
                "selected_all_lines": True,
            },
        ]
    }

    save_ctx_res = client.post(f"/api/projects/{project_id}/context", json=context_payload)
    assert save_ctx_res.status_code == 200
    ctx_data = save_ctx_res.json()
    assert ctx_data["total_selected_files"] == 2
    # 3 lines from calculator (2, 3, 4) + 3 lines from guide (all) = 6 lines
    assert ctx_data["total_selected_lines"] == 6

    # 5. Retrieve Context via GET
    get_ctx_res = client.get(f"/api/projects/{project_id}/context")
    assert get_ctx_res.status_code == 200
    saved_ctx = get_ctx_res.json()
    assert saved_ctx["total_selected_files"] == 2
    assert saved_ctx["total_selected_lines"] == 6

    # Verify custom lines record
    saved_calc = next(f for f in saved_ctx["selected_files"] if f["file_id"] == calc_file["id"])
    assert saved_calc["selected_all_lines"] is False
    assert saved_calc["start_line"] == 2
    assert saved_calc["end_line"] == 4
    assert saved_calc["selected_lines_count"] == 3

    # 6. Clear Context via DELETE
    del_ctx_res = client.delete(f"/api/projects/{project_id}/context")
    assert del_ctx_res.status_code == 200
    assert del_ctx_res.json()["status"] == "ok"

    # Verify context is now empty
    empty_ctx_res = client.get(f"/api/projects/{project_id}/context")
    assert empty_ctx_res.status_code == 200
    assert empty_ctx_res.json()["total_selected_files"] == 0
    assert empty_ctx_res.json()["total_selected_lines"] == 0


def test_context_validation_rejections():
    # Create two projects
    p1 = client.post("/api/projects", json={"name": "Project 1"}).json()["id"]
    p2 = client.post("/api/projects", json={"name": "Project 2"}).json()["id"]

    # Upload file to Project 1 (3 lines)
    code = "line1\nline2\nline3\n"
    upload = client.post(
        f"/api/projects/{p1}/upload",
        files=[("files", ("app.py", code.encode("utf-8"), "text/x-python"))],
    ).json()
    file_id = upload["ingested_files"][0]["id"]

    # Case A: Try to add Project 1's file into Project 2's context
    cross_res = client.post(
        f"/api/projects/{p2}/context",
        json={"files": [{"file_id": file_id, "selected_all_lines": True}]},
    )
    assert cross_res.status_code == 400
    assert "does not belong to project" in cross_res.json()["detail"]

    # Case B: start_line > end_line
    invalid_range_1 = client.post(
        f"/api/projects/{p1}/context",
        json={
            "files": [
                {
                    "file_id": file_id,
                    "selected_all_lines": False,
                    "line_range": {"start_line": 3, "end_line": 1},
                }
            ]
        },
    )
    assert invalid_range_1.status_code == 400
    assert "cannot exceed end_line" in invalid_range_1.json()["detail"]

    # Case C: end_line > file.line_count (3)
    invalid_range_2 = client.post(
        f"/api/projects/{p1}/context",
        json={
            "files": [
                {
                    "file_id": file_id,
                    "selected_all_lines": False,
                    "line_range": {"start_line": 1, "end_line": 99},
                }
            ]
        },
    )
    assert invalid_range_2.status_code == 400
    assert "exceeds total lines" in invalid_range_2.json()["detail"]

    # Case D: Non-existent file content lookup
    missing_file_res = client.get(f"/api/projects/{p1}/files/non-existent-uuid")
    assert missing_file_res.status_code == 404

