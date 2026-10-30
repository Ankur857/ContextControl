import pytest
from fastapi.testclient import TestClient
from main import app
from app.chunking import chunk_file_content, is_file_eligible_for_chunking
from app.embedding_service import (
    DeterministicMockEmbeddingProvider,
    GeminiEmbeddingProvider,
    get_embedding_provider,
)
from app.vector_store import (
    MockVectorStore,
    PgVectorStore,
    ModelDimensionMismatchError,
    get_vector_store,
)
from app.models import CodeChunk, ContextFileSelection, LineRangeSelection

client = TestClient(app)


# 1. Deterministic Chunking and Line-Number Preservation
def test_deterministic_chunking_and_line_preservation():
    python_code = (
        "import os\n"
        "import sys\n"
        "\n"
        "def compute_hash(val: str) -> str:\n"
        "    return val.strip()\n"
        "\n"
        "class WorkerService:\n"
        "    def run(self):\n"
        "        pass\n"
    )

    chunks1 = chunk_file_content(
        project_id="proj_test",
        file_id="file_123",
        relative_path="worker.py",
        raw_content=python_code,
        embedding_model="mock-v1",
        embedding_dimension=768,
        chunk_size=10,
    )
    chunks2 = chunk_file_content(
        project_id="proj_test",
        file_id="file_123",
        relative_path="worker.py",
        raw_content=python_code,
        embedding_model="mock-v1",
        embedding_dimension=768,
        chunk_size=10,
    )

    assert len(chunks1) > 0
    # Determinism: chunks produced on identical content must have identical IDs and bounds
    assert [c.id for c in chunks1] == [c.id for c in chunks2]
    assert [c.content_hash for c in chunks1] == [c.content_hash for c in chunks2]

    # Line numbers preservation
    for c in chunks1:
        assert c.start_line >= 1
        assert c.end_line >= c.start_line
        # Verify content lines match original source slice
        source_lines = python_code.splitlines()[c.start_line - 1 : c.end_line]
        assert c.content == "\n".join(source_lines).strip()


# 2. Empty and Oversized Files Handling
def test_empty_and_oversized_files_handling():
    # Empty string
    empty_chunks = chunk_file_content(
        project_id="p1",
        file_id="f1",
        relative_path="empty.py",
        raw_content="",
        embedding_model="mock-v1",
        embedding_dimension=768,
    )
    assert empty_chunks == []

    # Whitespace only
    ws_chunks = chunk_file_content(
        project_id="p1",
        file_id="f2",
        relative_path="spaces.py",
        raw_content="   \n\n\t  \n  ",
        embedding_model="mock-v1",
        embedding_dimension=768,
    )
    assert ws_chunks == []

    # Forbidden files rejected
    assert not is_file_eligible_for_chunking(".env")[0]
    assert not is_file_eligible_for_chunking("node_modules/pkg/index.js")[0]
    assert not is_file_eligible_for_chunking("app/binary.exe")[0]

    # Oversized file capped safely
    oversized_text = "\n".join([f"line_{i} = {i}" for i in range(6000)])
    oversized_chunks = chunk_file_content(
        project_id="p1",
        file_id="f3",
        relative_path="huge.py",
        raw_content=oversized_text,
        embedding_model="mock-v1",
        embedding_dimension=768,
    )
    assert len(oversized_chunks) > 0
    # Last chunk end line should not exceed MAX_FILE_LINES_FOR_CHUNKING (5000)
    assert max(c.end_line for c in oversized_chunks) <= 5000


# 3. Content-Hash-Based Re-indexing (Deduplication)
def test_content_hash_based_reindexing():
    store = MockVectorStore(model="mock-v1", dimension=768)
    provider = DeterministicMockEmbeddingProvider(dimension=768)

    code = "def authenticate():\n    return True\n"
    chunks = chunk_file_content(
        project_id="proj_hash",
        file_id="f_auth",
        relative_path="auth.py",
        raw_content=code,
        embedding_model="mock-v1",
        embedding_dimension=768,
    )
    embeddings = provider.embed_texts([c.content for c in chunks])

    # First indexing
    indexed1, skipped1 = store.index_chunks(
        "proj_hash", chunks, embeddings, "mock-v1", 768, force_reindex=False
    )
    assert indexed1 == len(chunks)
    assert skipped1 == 0

    # Second indexing without changes: should skip all chunks based on matching content hashes
    indexed2, skipped2 = store.index_chunks(
        "proj_hash", chunks, embeddings, "mock-v1", 768, force_reindex=False
    )
    assert indexed2 == 0
    assert skipped2 == len(chunks)

    # Force reindex bypasses deduplication
    indexed3, skipped3 = store.index_chunks(
        "proj_hash", chunks, embeddings, "mock-v1", 768, force_reindex=True
    )
    assert indexed3 == len(chunks)
    assert skipped3 == 0


# 4. Embedding Provider Error Handling and Safe Retries
def test_embedding_provider_error_handling():
    # Missing API key on live Gemini provider must raise clear error without leaking secrets
    provider = GeminiEmbeddingProvider(api_key="")
    with pytest.raises(ValueError, match="GEMINI_API_KEY is not configured"):
        provider.embed_texts(["hello world"])

    # Mock provider succeeds reliably
    mock_prov = DeterministicMockEmbeddingProvider(dimension=768)
    vec = mock_prov.embed_query("search query")
    assert len(vec) == 768
    # Check L2 unit normalization
    import math

    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-4


# 5. Model and Dimension Mismatch Detection
def test_model_and_dimension_mismatch_handling():
    store = MockVectorStore(model="mock-v1", dimension=768)
    provider = DeterministicMockEmbeddingProvider(dimension=768)

    chunk = CodeChunk(
        id="c1",
        project_id="proj_dim",
        file_id="f1",
        relative_path="main.py",
        start_line=1,
        end_line=5,
        content="x = 1",
        content_hash="h1",
        embedding_model="mock-v1",
        embedding_dimension=768,
        created_at="2026-01-01T00:00:00Z",
    )
    store.index_chunks("proj_dim", [chunk], [[0.1] * 768], "mock-v1", 768)

    # Attempt to index with different dimension (e.g. 1536) must raise ModelDimensionMismatchError
    with pytest.raises(ModelDimensionMismatchError, match="Model/Dimension mismatch"):
        store.index_chunks(
            "proj_dim",
            [chunk],
            [[0.1] * 1536],
            "different-model",
            1536,
        )


# 6. Project-Scoped Retrieval (Isolation)
def test_project_scoped_retrieval_isolation():
    store = MockVectorStore(model="mock-v1", dimension=768)
    provider = DeterministicMockEmbeddingProvider(dimension=768)

    # Index chunk in Project A
    chunk_a = CodeChunk(
        id="chunk_a",
        project_id="project_alpha",
        file_id="fa",
        relative_path="secret_alpha.py",
        start_line=1,
        end_line=3,
        content="def alpha_secret(): return 'classified'",
        content_hash="hash_a",
        embedding_model="mock-v1",
        embedding_dimension=768,
        created_at="2026-01-01T00:00:00Z",
    )
    store.index_chunks(
        "project_alpha",
        [chunk_a],
        provider.embed_texts([chunk_a.content]),
        "mock-v1",
        768,
    )

    # Index chunk in Project B
    chunk_b = CodeChunk(
        id="chunk_b",
        project_id="project_beta",
        file_id="fb",
        relative_path="public_beta.py",
        start_line=1,
        end_line=3,
        content="def beta_public(): return 'open'",
        content_hash="hash_b",
        embedding_model="mock-v1",
        embedding_dimension=768,
        created_at="2026-01-01T00:00:00Z",
    )
    store.index_chunks(
        "project_beta",
        [chunk_b],
        provider.embed_texts([chunk_b.content]),
        "mock-v1",
        768,
    )

    # Search in Project Beta for 'classified' or 'alpha'
    q_vec = provider.embed_query("classified secret")
    results_beta = store.search("project_beta", q_vec, top_k=5)

    # Project Alpha's chunk must NEVER leak into Project Beta results
    for r in results_beta:
        assert r.chunk_id != "chunk_a"
        assert "classified" not in r.source_text


# 7. Empty Search Results Handling
def test_empty_search_results_handling():
    store = MockVectorStore(model="mock-v1", dimension=768)
    provider = DeterministicMockEmbeddingProvider(dimension=768)

    q_vec = provider.embed_query("unrelated database migration")
    # Search in empty project
    results = store.search("empty_proj", q_vec, top_k=5)
    assert results == []

    # High min_score threshold yields empty list gracefully without throwing
    chunk = CodeChunk(
        id="c_low",
        project_id="p_thresh",
        file_id="f1",
        relative_path="test.py",
        start_line=1,
        end_line=2,
        content="pass",
        content_hash="h_pass",
        embedding_model="mock-v1",
        embedding_dimension=768,
        created_at="2026-01-01T00:00:00Z",
    )
    store.index_chunks("p_thresh", [chunk], provider.embed_texts(["pass"]), "mock-v1", 768)
    strict_results = store.search("p_thresh", q_vec, top_k=5, min_score=0.999)
    assert isinstance(strict_results, list)


# 8. Retrieval Ranking using Deterministic Mock Embeddings
def test_retrieval_ranking_with_mock_embeddings():
    store = MockVectorStore(model="mock-v1", dimension=768)
    provider = DeterministicMockEmbeddingProvider(dimension=768)

    chunks = [
        CodeChunk(
            id="c_jwt",
            project_id="p_rank",
            file_id="f_jwt",
            relative_path="jwt_auth.py",
            start_line=1,
            end_line=5,
            content="def verify_jwt_token(token): return jwt.decode(token)",
            content_hash="h_jwt",
            embedding_model="mock-v1",
            embedding_dimension=768,
            created_at="2026-01-01T00:00:00Z",
        ),
        CodeChunk(
            id="c_db",
            project_id="p_rank",
            file_id="f_db",
            relative_path="database.py",
            start_line=1,
            end_line=5,
            content="def connect_postgres(): return psycopg.connect(url)",
            content_hash="h_db",
            embedding_model="mock-v1",
            embedding_dimension=768,
            created_at="2026-01-01T00:00:00Z",
        ),
    ]

    embeddings = provider.embed_texts([c.content for c in chunks])
    store.index_chunks("p_rank", chunks, embeddings, "mock-v1", 768)

    # Search for JWT verification
    jwt_query = provider.embed_query("verify jwt token decode")
    jwt_results = store.search("p_rank", jwt_query, top_k=2)

    assert len(jwt_results) == 2
    # The top ranked result must be jwt_auth.py with highest similarity score
    assert jwt_results[0].chunk_id == "c_jwt"
    assert jwt_results[0].similarity_score > jwt_results[1].similarity_score


# 9. Index Deletion Without Deleting Original Files
def test_index_deletion_preserves_original_files():
    # Create project and upload file via API
    p_resp = client.post("/api/projects", json={"name": "Preserve Files Test"})
    assert p_resp.status_code in (200, 201)
    p_id = p_resp.json()["id"]

    files = [("files", ("service.py", b"def calculate(): return 42\n", "text/plain"))]
    up_resp = client.post(f"/api/projects/{p_id}/upload", files=files)
    assert up_resp.status_code == 200
    assert up_resp.json()["total_ingested"] == 1

    # Index in mock mode
    idx_resp = client.post(f"/api/projects/{p_id}/index", json={"use_mock": True})
    assert idx_resp.status_code == 200
    assert idx_resp.json()["indexed_chunks"] > 0

    # Delete index
    del_resp = client.delete(f"/api/projects/{p_id}/index?use_mock=true")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Original project file MUST still exist in project storage
    files_resp = client.get(f"/api/projects/{p_id}/files")
    assert files_resp.status_code == 200
    file_list = files_resp.json()
    assert len(file_list) == 1
    assert file_list[0]["filename"] == "service.py"

    # Reading file content still succeeds
    f_id = file_list[0]["id"]
    content_resp = client.get(f"/api/projects/{p_id}/files/{f_id}")
    assert content_resp.status_code == 200
    assert "calculate" in content_resp.json()["content"]


# 10. Ensuring Retrieved But Unapproved Chunks NEVER Enter Gemini Requests
def test_retrieved_unapproved_chunks_never_enter_gemini_requests(monkeypatch):
    """
    CRITICAL CONTEXT LOCK REQUIREMENT:
    Semantic search is strictly an advisory recommendation tool.
    Even if search-context finds top-scoring candidate chunks,
    they are NEVER automatically authorized or included in chat context
    without explicit user context selection and lock.
    """
    from unittest.mock import patch, MagicMock
    import json

    monkeypatch.setenv("GEMINI_API_KEY", "test-fake-key")

    p_resp = client.post("/api/projects", json={"name": "Context Lock Guard Test"})
    assert p_resp.status_code in (200, 201)
    p_id = p_resp.json()["id"]

    # Upload two files
    files = [
        ("files", ("auth.py", b"def login():\n    return 'auth_token'\n", "text/plain")),
        ("files", ("secret.py", b"def db_password():\n    return 'super_secret_123'\n", "text/plain")),
    ]
    client.post(f"/api/projects/{p_id}/upload", files=files)

    # Index codebase in mock mode
    client.post(f"/api/projects/{p_id}/index", json={"use_mock": True})

    # Search returns candidate snippet from secret.py
    search_resp = client.post(
        f"/api/projects/{p_id}/search-context",
        json={"query": "super_secret_123 db_password", "use_mock": True},
    )
    assert search_resp.status_code == 200
    search_items = search_resp.json()["results"]
    assert any("secret.py" in r["relative_path"] for r in search_items)

    # Get file IDs
    files_list = client.get(f"/api/projects/{p_id}/files").json()
    auth_file = next(f for f in files_list if f["filename"] == "auth.py")
    secret_file = next(f for f in files_list if f["filename"] == "secret.py")

    # Developer ONLY selects and locks auth.py, deliberately excluding secret.py!
    lock_resp = client.post(
        f"/api/projects/{p_id}/context",
        json={"files": [{"file_id": auth_file["id"], "selected_all_lines": True}]},
    )
    assert lock_resp.status_code == 200

    # Mock Gemini response
    mock_model_response = {
        "answer": "Context does not contain db_password; missing secret.py evidence.",
        "citations": [],
        "insufficient_context": True,
        "missing_context": ["secret.py"],
    }
    mock_client = MagicMock()
    mock_res = MagicMock()
    mock_res.text = json.dumps(mock_model_response)
    mock_client.models.generate_content.return_value = mock_res

    with patch("google.genai.Client", return_value=mock_client):
        # Query chat regarding secret.py
        chat_resp = client.post(
            f"/api/projects/{p_id}/chat",
            json={"question": "What is the db_password defined in secret.py?"},
        )
        assert chat_resp.status_code == 200
        body = chat_resp.json()

        # Verify that Gemini was called with LOCKED context containing ONLY auth.py
        call_args = mock_client.models.generate_content.call_args
        prompt_sent = call_args.kwargs.get("contents", "")
        evidence_section = prompt_sent.split("DEVELOPER QUESTION:")[0]
        assert "auth.py" in evidence_section
        # secret.py was NOT approved/locked, so it MUST NEVER be in the evidence section!
        assert "secret.py" not in evidence_section
        assert "super_secret_123" not in prompt_sent

        # The secret.py file was never approved, so total_evidence_files MUST be 1 (only auth.py)
        assert body["total_evidence_files"] == 1
        assert body["insufficient_context"] is True
        assert "super_secret_123" not in body["answer"]
