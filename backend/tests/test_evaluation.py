import json
import pytest
from fastapi.testclient import TestClient
from main import app
from app.eval_dataset import DATASET_METADATA, EVALUATION_QUESTIONS

client = TestClient(app)


def test_evaluation_dataset_loading():
    res = client.get("/api/evaluations/dataset")
    assert res.status_code == 200
    data = res.json()
    assert data["metadata"]["dataset_id"] == "context_control_eval_v1"
    assert len(data["questions"]) == len(EVALUATION_QUESTIONS)
    # Check that required categories are present
    categories = [q["category"] for q in data["questions"]]
    assert "direct_answerable" in categories
    assert "multi_file_requirement" in categories
    assert "false_assumption" in categories
    assert "insufficient_evidence" in categories


def test_reproducible_mock_evaluation_run():
    payload = {
        "dataset_id": "context_control_eval_v1",
        "modes": ["baseline", "context_lock", "context_lock_citations"],
        "use_mock": True,
    }
    res = client.post("/api/evaluations/run", json=payload)
    assert res.status_code == 200
    run_data = res.json()
    assert run_data["status"] == "completed"
    assert run_data["total_cases"] == 4 * 3  # 4 questions * 3 modes = 12
    assert len(run_data["comparison"]) == 3
    assert len(run_data["results"]) == 12

    run_id = run_data["id"]

    # Verify run persistence in SQLite via GET /runs/{run_id}
    get_res = client.get(f"/api/evaluations/runs/{run_id}")
    assert get_res.status_code == 200
    saved_run = get_res.json()
    assert saved_run["id"] == run_id
    assert len(saved_run["results"]) == 12


def test_metric_calculation_and_unavailable_metrics():
    payload = {
        "dataset_id": "context_control_eval_v1",
        "modes": ["baseline", "context_lock_citations"],
        "use_mock": True,
    }
    res = client.post("/api/evaluations/run", json=payload).json()
    comparison = {c["mode"]: c for c in res["comparison"]}

    # Baseline mode: citation validity should be None (unavailable, not fabricated)
    assert comparison["baseline"]["citation_validity_rate"] is None

    # Context Lock + Citations: citation validity should be high (> 0.9)
    assert comparison["context_lock_citations"]["citation_validity_rate"] is not None
    assert comparison["context_lock_citations"]["citation_validity_rate"] >= 0.9

    # Context Lock mode should have 100% insufficient context accuracy on the mock dataset
    assert comparison["context_lock_citations"]["insufficient_context_accuracy"] == 1.0


def test_evaluation_obeys_context_lock():
    payload = {
        "dataset_id": "context_control_eval_v1",
        "modes": ["context_lock"],
        "use_mock": True,
    }
    res = client.post("/api/evaluations/run", json=payload).json()
    # Check tc_1 context
    tc1_res = next(r for r in res["results"] if r["question_id"] == "tc_1_answerable_direct")
    # Must only contain auth.py lines 9 to 15
    assert "LINES_SCOPED: 9 to 15" in tc1_res["context_supplied"]
    # Must NOT contain token_manager.py
    assert "token_manager.py" not in tc1_res["context_supplied"]


def test_secrets_never_in_evaluation_results(monkeypatch):
    secret_key = "AIzaSySuperSecretNeverExposeInEvalResults"
    monkeypatch.setenv("GEMINI_API_KEY", secret_key)

    payload = {
        "dataset_id": "context_control_eval_v1",
        "modes": ["baseline", "context_lock"],
        "use_mock": True,
    }
    res = client.post("/api/evaluations/run", json=payload)
    assert res.status_code == 200
    raw_text = res.text
    assert secret_key not in raw_text

