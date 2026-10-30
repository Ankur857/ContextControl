import math
import logging
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Dict, Any
from app.models import CodeChunk, SearchResultItem, IndexStatusResponse
from app.config import (
    DATABASE_URL,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    ALLOW_TEST_VECTOR_STORE,
)

logger = logging.getLogger("contextcontrol.vector_store")

PGVECTOR_SETUP_GUIDANCE = (
    "PostgreSQL with pgvector is not configured. "
    "To enable semantic context discovery:\n"
    "1. Ensure PostgreSQL (>= 15) and pgvector are installed, or create a Supabase project.\n"
    "2. Enable the extension: CREATE EXTENSION IF NOT EXISTS vector;\n"
    "3. Set DATABASE_URL in backend/.env (e.g. postgresql://user:password@localhost:5432/dbname).\n"
    "4. Restart the backend.\n\n"
    "Note: Manual file inspection, Context Lock, and citations remain 100% operational without semantic search."
)


class ModelDimensionMismatchError(Exception):
    """Raised when indexing with a model or dimension that conflicts with existing project data."""

    pass


class BaseVectorStore(ABC):
    @abstractmethod
    def is_available(self) -> Tuple[bool, str]:
        """Returns (is_available, status_or_error_message)."""
        pass

    @abstractmethod
    def initialize(self) -> None:
        """Initializes tables and extensions."""
        pass

    @abstractmethod
    def index_chunks(
        self,
        project_id: str,
        chunks: List[CodeChunk],
        embeddings: List[List[float]],
        model: str,
        dimension: int,
        force_reindex: bool = False,
    ) -> Tuple[int, int]:
        """Indexes chunks and their embeddings. Returns (indexed_count, skipped_count)."""
        pass

    @abstractmethod
    def search(
        self,
        project_id: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> List[SearchResultItem]:
        """Performs vector similarity search restricted to project_id."""
        pass

    @abstractmethod
    def delete_project_index(self, project_id: str) -> int:
        """Removes all indexed chunks for project_id without deleting original files."""
        pass

    @abstractmethod
    def get_status(self, project_id: str) -> Dict[str, Any]:
        """Retrieves index status and counts for project_id."""
        pass


class PgVectorStore(BaseVectorStore):
    """
    Production vector store connecting to PostgreSQL/Supabase with pgvector.
    Enforces strict project isolation, model dimension validation, and cosine similarity.
    """

    def __init__(
        self,
        conn_url: str = DATABASE_URL,
        model: str = EMBEDDING_MODEL,
        dimension: int = EMBEDDING_DIMENSION,
    ):
        self.conn_url = conn_url.strip() if conn_url else ""
        self.model = model
        self.dimension = dimension
        self.is_mock = False

    def is_available(self) -> Tuple[bool, str]:
        if not self.conn_url:
            return False, PGVECTOR_SETUP_GUIDANCE

        try:
            import psycopg

            with psycopg.connect(self.conn_url, connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
            return True, "PostgreSQL connected and responsive"
        except Exception as e:
            return (
                False,
                f"Cannot connect to PostgreSQL at configured DATABASE_URL: {e}\n\n{PGVECTOR_SETUP_GUIDANCE}",
            )

    def initialize(self) -> None:
        if not self.conn_url:
            raise RuntimeError(PGVECTOR_SETUP_GUIDANCE)

        import psycopg
        from pgvector.psycopg import register_vector

        with psycopg.connect(self.conn_url) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            register_vector(conn)
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS project_code_chunks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    file_id TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    start_line INT NOT NULL,
                    end_line INT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding_dimension INT NOT NULL,
                    embedding vector({self.dimension}) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_code_chunks_project_id ON project_code_chunks(project_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_code_chunks_content_hash ON project_code_chunks(project_id, content_hash);"
            )
            conn.commit()

    def index_chunks(
        self,
        project_id: str,
        chunks: List[CodeChunk],
        embeddings: List[List[float]],
        model: str,
        dimension: int,
        force_reindex: bool = False,
    ) -> Tuple[int, int]:
        if not chunks:
            return 0, 0

        self.initialize()
        import psycopg
        from pgvector.psycopg import register_vector

        with psycopg.connect(self.conn_url) as conn:
            register_vector(conn)
            with conn.cursor() as cur:
                # Detect model or dimension mismatch with existing project data
                cur.execute(
                    """
                    SELECT embedding_model, embedding_dimension 
                    FROM project_code_chunks 
                    WHERE project_id = %s 
                    LIMIT 1;
                    """,
                    (project_id,),
                )
                row = cur.fetchone()
                if row:
                    existing_model, existing_dim = row[0], row[1]
                    if existing_dim != dimension or existing_model != model:
                        raise ModelDimensionMismatchError(
                            f"Model/Dimension mismatch: Project has existing chunks indexed with "
                            f"{existing_model} (dim {existing_dim}), but attempted to index with "
                            f"{model} (dim {dimension}). Please delete or reindex the project index."
                        )

                # Query existing content hashes for deduplication
                existing_hashes = set()
                if not force_reindex:
                    cur.execute(
                        "SELECT content_hash FROM project_code_chunks WHERE project_id = %s;",
                        (project_id,),
                    )
                    existing_hashes = {r[0] for r in cur.fetchall()}

                indexed_count = 0
                skipped_count = 0

                for chunk, vec in zip(chunks, embeddings):
                    if not force_reindex and chunk.content_hash in existing_hashes:
                        skipped_count += 1
                        continue

                    cur.execute(
                        """
                        INSERT INTO project_code_chunks (
                            id, project_id, file_id, relative_path, start_line, end_line,
                            content, content_hash, embedding_model, embedding_dimension, embedding
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            content = EXCLUDED.content,
                            content_hash = EXCLUDED.content_hash,
                            embedding = EXCLUDED.embedding;
                        """,
                        (
                            chunk.id,
                            chunk.project_id,
                            chunk.file_id,
                            chunk.relative_path,
                            chunk.start_line,
                            chunk.end_line,
                            chunk.content,
                            chunk.content_hash,
                            model,
                            dimension,
                            vec,
                        ),
                    )
                    indexed_count += 1

                conn.commit()
                return indexed_count, skipped_count

    def search(
        self,
        project_id: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> List[SearchResultItem]:
        self.initialize()
        import psycopg
        from pgvector.psycopg import register_vector

        with psycopg.connect(self.conn_url) as conn:
            register_vector(conn)
            with conn.cursor() as cur:
                # Cosine distance: 1 - cosine_distance gives cosine similarity
                cur.execute(
                    """
                    SELECT 
                        id, file_id, relative_path, start_line, end_line, content,
                        1.0 - (embedding <=> %s::vector) AS similarity_score
                    FROM project_code_chunks
                    WHERE project_id = %s
                    ORDER BY embedding <=> %s::vector ASC
                    LIMIT %s;
                    """,
                    (query_embedding, project_id, query_embedding, top_k * 2),
                )
                rows = cur.fetchall()

        results: List[SearchResultItem] = []
        for r in rows:
            score = float(r[6])
            # Clamp between 0.0 and 1.0
            norm_score = max(0.0, min(1.0, score))
            if norm_score >= min_score:
                content = r[5]
                preview_lines = content.splitlines()[:4]
                preview = "\n".join(preview_lines)
                if len(preview) > 200:
                    preview = preview[:200] + "..."

                results.append(
                    SearchResultItem(
                        chunk_id=r[0],
                        file_id=r[1],
                        relative_path=r[2],
                        start_line=r[3],
                        end_line=r[4],
                        similarity_score=round(norm_score, 4),
                        preview=preview,
                        source_text=content,
                    )
                )
            if len(results) >= top_k:
                break

        return results

    def delete_project_index(self, project_id: str) -> int:
        if not self.conn_url:
            return 0

        import psycopg

        with psycopg.connect(self.conn_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM project_code_chunks WHERE project_id = %s;",
                    (project_id,),
                )
                deleted = cur.rowcount
                conn.commit()
                return deleted

    def get_status(self, project_id: str) -> Dict[str, Any]:
        avail, msg = self.is_available()
        if not avail:
            return {
                "configured": False,
                "pgvector_enabled": False,
                "is_mock": False,
                "total_chunks": 0,
                "total_indexed_files": 0,
                "embedding_model": self.model,
                "embedding_dimension": self.dimension,
                "last_indexed_at": None,
                "setup_guidance": msg,
            }

        import psycopg

        try:
            with psycopg.connect(self.conn_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 
                            COUNT(*), 
                            COUNT(DISTINCT file_id),
                            COALESCE(MAX(embedding_model), %s),
                            COALESCE(MAX(embedding_dimension), %s),
                            MAX(created_at)
                        FROM project_code_chunks
                        WHERE project_id = %s;
                        """,
                        (self.model, self.dimension, project_id),
                    )
                    row = cur.fetchone()
                    return {
                        "configured": True,
                        "pgvector_enabled": True,
                        "is_mock": False,
                        "total_chunks": row[0] or 0,
                        "total_indexed_files": row[1] or 0,
                        "embedding_model": row[2] or self.model,
                        "embedding_dimension": row[3] or self.dimension,
                        "last_indexed_at": row[4].isoformat() if row[4] else None,
                        "setup_guidance": None,
                    }
        except Exception as e:
            return {
                "configured": False,
                "pgvector_enabled": False,
                "is_mock": False,
                "total_chunks": 0,
                "total_indexed_files": 0,
                "embedding_model": self.model,
                "embedding_dimension": self.dimension,
                "last_indexed_at": None,
                "setup_guidance": f"Error querying pgvector: {e}",
            }


class MockVectorStore(BaseVectorStore):
    """
    Deterministic in-memory vector store for testing and offline evaluation.
    Clearly identifies itself as a mock so users are never misled into believing
    pgvector is running when it is not.
    """

    def __init__(
        self,
        model: str = "mock-embedding-v1",
        dimension: int = EMBEDDING_DIMENSION,
    ):
        self.model = model
        self.dimension = dimension
        self.is_mock = True
        # project_id -> list of (CodeChunk, vector)
        self._storage: Dict[str, List[Tuple[CodeChunk, List[float]]]] = {}

    def is_available(self) -> Tuple[bool, str]:
        return True, "Mock test vector store active"

    def initialize(self) -> None:
        pass

    def index_chunks(
        self,
        project_id: str,
        chunks: List[CodeChunk],
        embeddings: List[List[float]],
        model: str,
        dimension: int,
        force_reindex: bool = False,
    ) -> Tuple[int, int]:
        if not chunks:
            return 0, 0

        if project_id not in self._storage:
            self._storage[project_id] = []

        existing = self._storage[project_id]

        # Check model/dimension mismatch
        if existing:
            first_chunk = existing[0][0]
            if (
                first_chunk.embedding_dimension != dimension
                or first_chunk.embedding_model != model
            ):
                raise ModelDimensionMismatchError(
                    f"Model/Dimension mismatch: Project has existing chunks indexed with "
                    f"{first_chunk.embedding_model} (dim {first_chunk.embedding_dimension}), "
                    f"but attempted to index with {model} (dim {dimension})."
                )

        existing_hashes = (
            {c.content_hash for c, _ in existing} if not force_reindex else set()
        )
        indexed_count = 0
        skipped_count = 0

        # Create updated store
        new_list = [item for item in existing]

        for chunk, vec in zip(chunks, embeddings):
            if not force_reindex and chunk.content_hash in existing_hashes:
                skipped_count += 1
                continue

            # Remove existing chunk with same id if any
            new_list = [item for item in new_list if item[0].id != chunk.id]
            new_list.append((chunk, vec))
            indexed_count += 1

        self._storage[project_id] = new_list
        return indexed_count, skipped_count

    def search(
        self,
        project_id: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> List[SearchResultItem]:
        items = self._storage.get(project_id, [])
        if not items:
            return []

        scored: List[Tuple[float, CodeChunk]] = []
        for chunk, vec in items:
            # Cosine similarity
            dot = sum(a * b for a, b in zip(query_embedding, vec))
            norm_q = math.sqrt(sum(a * a for a in query_embedding))
            norm_v = math.sqrt(sum(b * b for b in vec))
            if norm_q > 1e-9 and norm_v > 1e-9:
                sim = dot / (norm_q * norm_v)
            else:
                sim = 0.0

            # Normalize to 0..1 range
            sim_score = max(0.0, min(1.0, (sim + 1.0) / 2.0 if sim < 0 else sim))
            if sim_score >= min_score:
                scored.append((sim_score, chunk))

        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)

        results: List[SearchResultItem] = []
        for sim_score, chunk in scored[:top_k]:
            preview_lines = chunk.content.splitlines()[:4]
            preview = "\n".join(preview_lines)
            if len(preview) > 200:
                preview = preview[:200] + "..."

            results.append(
                SearchResultItem(
                    chunk_id=chunk.id,
                    file_id=chunk.file_id,
                    relative_path=chunk.relative_path,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    similarity_score=round(sim_score, 4),
                    preview=preview,
                    source_text=chunk.content,
                )
            )

        return results

    def delete_project_index(self, project_id: str) -> int:
        if project_id in self._storage:
            count = len(self._storage[project_id])
            del self._storage[project_id]
            return count
        return 0

    def get_status(self, project_id: str) -> Dict[str, Any]:
        items = self._storage.get(project_id, [])
        file_ids = {c.file_id for c, _ in items}
        last_ts = items[-1][0].created_at if items else None
        return {
            "configured": True,
            "pgvector_enabled": False,
            "is_mock": True,
            "total_chunks": len(items),
            "total_indexed_files": len(file_ids),
            "embedding_model": items[0][0].embedding_model if items else self.model,
            "embedding_dimension": (
                items[0][0].embedding_dimension if items else self.dimension
            ),
            "last_indexed_at": last_ts,
            "setup_guidance": "Running in deterministic mock vector mode for testing and offline development.",
        }


# Singleton mock store instance for test suite and dev mock requests
_GLOBAL_MOCK_STORE = MockVectorStore()


def get_vector_store(use_mock: bool = False) -> BaseVectorStore:
    """
    Factory returning either the production PgVectorStore or the testing MockVectorStore.
    Never silently substitutes a mock as pgvector: if PgVectorStore is returned when
    PostgreSQL is not configured, is_available() returns False and explains setup steps.
    """
    if use_mock or ALLOW_TEST_VECTOR_STORE:
        return _GLOBAL_MOCK_STORE
    return PgVectorStore()

