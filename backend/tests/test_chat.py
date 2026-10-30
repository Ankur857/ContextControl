import os
import json
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient
from main import app
from app.gemini_service import reconstruct_trusted_context
from app.models import ContextFileSelection, LineRangeSelection

client = TestClient(app)


@pytest.fixture
def test_setup():
    # Create project
    p = client.post("/api/projects", json={"name": "Gemini Test Project"}).json()
    project_id = p["id"]

    # Upload file: 5 lines
    content = "def add(a, b):\n    # Calculate sum\n    result = a + b\n    return result\n# End\n"
    res = client.post(
        f"/api/projects/{project_id}/upload",
        files=[("files", ("math.py", content.encode("utf-8"), "text/x-python"))],
    ).json()
    file_id = res["ingested_files"][0]["id"]

    return project_id, file_id


def test_missing_api_key_returns_clear_error(test_setup, monkeypatch):
    project_id, file_id = test_setup
    monkeypatch.setenv("GEMINI_API_KEY", "")

    # Save context
    client.post(
        f"/api/projects/{project_id}/context",
        json={"files": [{"file_id": file_id, "selected_all_lines": True}]},
    )

    response = client.post(
        f"/api/projects/{project_id}/chat",
        json={"question": "What does add do?"},
    )
    assert response.status_code == 503
    assert "GEMINI_API_KEY is not configured" in response.json()["detail"]


def test_empty_context_selection_rejected(test_setup):
    project_id, _ = test_setup
    # Clear any context
    client.delete(f"/api/projects/{project_id}/context")

    response = client.post(
        f"/api/projects/{project_id}/chat",
        json={"question": "Explain this code."},
    )
    assert response.status_code == 400
    assert "No context selected" in response.json()["detail"]


def test_cross_project_file_id_rejected(test_setup):
    p1_id, f1_id = test_setup
    p2_id = client.post("/api/projects", json={"name": "Second Project"}).json()["id"]

    # Try to chat in p2 using p1's file_id
    response = client.post(
        f"/api/projects/{p2_id}/chat",
        json={
            "question": "What is here?",
            "files": [{"file_id": f1_id, "selected_all_lines": True}],
        },
    )
    assert response.status_code == 400
    assert "does not belong to project" in response.json()["detail"]


def test_context_construction_exact_lines(test_setup):
    project_id, file_id = test_setup

    # Select lines 2 to 4
    selection = [
        ContextFileSelection(
            file_id=file_id,
            selected_all_lines=False,
            line_range=LineRangeSelection(start_line=2, end_line=4),
        )
    ]

    context_text, trusted_evidence, count, total_lines = reconstruct_trusted_context(
        project_id, selection
    )

    assert count == 1
    assert total_lines == 3
    # Check that line 2, 3, 4 are present with line numbers
    assert "2:     # Calculate sum" in context_text
    assert "3:     result = a + b" in context_text
    assert "4:     return result" in context_text
    # Line 1 and 5 must NOT be in the constructed context!
    assert "1: def add" not in context_text
    assert "5: # End" not in context_text


def test_valid_citations_verified(test_setup, monkeypatch):
    project_id, file_id = test_setup
    monkeypatch.setenv("GEMINI_API_KEY", "test-fake-gemini-key")

    mock_gemini_response = {
        "answer": "The add function calculates the sum of two parameters a and b.",
        "citations": [
            {
                "source_id": file_id,
                "file_path": "math.py",
                "start_line": 1,
                "end_line": 4,
                "claim": "Calculates sum of a and b",
            }
        ],
        "insufficient_context": False,
        "missing_context": [],
    }

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(mock_gemini_response)
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        res = client.post(
            f"/api/projects/{project_id}/chat",
            json={
                "question": "Explain add()",
                "files": [{"file_id": file_id, "selected_all_lines": True}],
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["answer"] == mock_gemini_response["answer"]
        assert len(data["citations"]) == 1
        citation = data["citations"][0]
        assert citation["verified"] is True
        assert citation["source_id"] == file_id
        assert citation["file_path"] == "math.py"


def test_invalid_citations_outside_selected_line_ranges(test_setup, monkeypatch):
    project_id, file_id = test_setup
    monkeypatch.setenv("GEMINI_API_KEY", "test-fake-gemini-key")

    # Scoped only to lines 2 to 3
    mock_gemini_response = {
        "answer": "There is a return statement on line 4.",
        "citations": [
            {
                "source_id": file_id,
                "file_path": "math.py",
                "start_line": 4,  # Out of permitted scope (2 to 3)!
                "end_line": 4,
                "claim": "Return statement",
            }
        ],
        "insufficient_context": False,
        "missing_context": [],
    }

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(mock_gemini_response)
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        res = client.post(
            f"/api/projects/{project_id}/chat",
            json={
                "question": "What is returned?",
                "files": [
                    {
                        "file_id": file_id,
                        "selected_all_lines": False,
                        "line_range": {"start_line": 2, "end_line": 3},
                    }
                ],
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data["citations"]) == 1
        citation = data["citations"][0]
        # Must be flagged as NOT verified because line 4 is outside permitted lines 2-3
        assert citation["verified"] is False
        assert "exceed permitted evidence scope" in citation["verification_reason"]


def test_insufficient_context_response(test_setup, monkeypatch):
    project_id, file_id = test_setup
    monkeypatch.setenv("GEMINI_API_KEY", "test-fake-gemini-key")

    mock_gemini_response = {
        "answer": "I cannot find database connection logic in the provided code.",
        "citations": [],
        "insufficient_context": True,
        "missing_context": ["database.py or connection configuration"],
    }

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(mock_gemini_response)
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        res = client.post(
            f"/api/projects/{project_id}/chat",
            json={
                "question": "How does this code connect to Postgres?",
                "files": [{"file_id": file_id, "selected_all_lines": True}],
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["insufficient_context"] is True
        assert "database.py or connection configuration" in data["missing_context"]


def test_malformed_model_response_handled_gracefully(test_setup, monkeypatch):
    project_id, file_id = test_setup
    monkeypatch.setenv("GEMINI_API_KEY", "test-fake-gemini-key")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "NOT_VALID_JSON_AT_ALL_HERE"
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        res = client.post(
            f"/api/projects/{project_id}/chat",
            json={
                "question": "Describe function",
                "files": [{"file_id": file_id, "selected_all_lines": True}],
            },
        )
        assert res.status_code == 502
        assert "malformed or unparseable" in res.json()["detail"]


def test_api_key_never_leaked_in_response(test_setup, monkeypatch):
    project_id, file_id = test_setup
    secret_key = "AIzaSySecretNeverExposeToClient12345"
    monkeypatch.setenv("GEMINI_API_KEY", secret_key)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "answer": "This is the answer.",
        "citations": [],
        "insufficient_context": False,
        "missing_context": [],
    })
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        res = client.post(
            f"/api/projects/{project_id}/chat",
            json={
                "question": "General question",
                "files": [{"file_id": file_id, "selected_all_lines": True}],
            },
        )
        assert res.status_code == 200
        raw_body = res.text
        # Assert secret key is nowhere in response body or headers
        assert secret_key not in raw_body
        for k, v in res.headers.items():
            assert secret_key not in str(v)

