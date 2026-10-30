import sqlite3
import uuid
import json
from datetime import datetime, timezone
import os
from typing import List, Optional, Dict, Any
from app.config import DB_PATH, STORAGE_DIR, PROJECTS_DIR


class StorageManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        os.makedirs(STORAGE_DIR, exist_ok=True)
        os.makedirs(PROJECTS_DIR, exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS project_files (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    line_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    UNIQUE(project_id, relative_path)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_project_files_project_id
                ON project_files(project_id)
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS project_context_selections (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    file_id TEXT NOT NULL REFERENCES project_files(id) ON DELETE CASCADE,
                    selected_all_lines INTEGER NOT NULL DEFAULT 1,
                    start_line INTEGER,
                    end_line INTEGER,
                    created_at TEXT NOT NULL,
                    UNIQUE(project_id, file_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_project_context_project_id
                ON project_context_selections(project_id)
                """
            )
            # Phase 6: Evaluation Tables
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS evaluation_runs (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    modes_json TEXT NOT NULL,
                    total_cases INTEGER NOT NULL,
                    completed_cases INTEGER NOT NULL DEFAULT 0,
                    summary_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS evaluation_results (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
                    question_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    question TEXT NOT NULL,
                    model_answer TEXT NOT NULL,
                    reference_answer TEXT NOT NULL,
                    context_supplied TEXT,
                    citations_json TEXT,
                    answer_correctness REAL NOT NULL,
                    citation_validity REAL,
                    evidence_coverage REAL NOT NULL,
                    unsupported_claim_rate REAL NOT NULL,
                    insufficient_context_handled INTEGER NOT NULL,
                    tokens_used INTEGER NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    error TEXT,
                    reviewer_notes TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_eval_results_run_id
                ON evaluation_results(run_id)
                """
            )
            conn.commit()

    def create_project(self, name: str) -> Dict[str, Any]:
        project_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        project_dir = os.path.join(PROJECTS_DIR, project_id, "files")
        os.makedirs(project_dir, exist_ok=True)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
                (project_id, name, created_at),
            )
            conn.commit()

        return {
            "id": project_id,
            "name": name,
            "created_at": created_at,
            "file_count": 0,
            "total_size_bytes": 0,
            "files": [],
        }

    def list_projects(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    p.id, 
                    p.name, 
                    p.created_at,
                    COUNT(f.id) as file_count,
                    COALESCE(SUM(f.size_bytes), 0) as total_size_bytes
                FROM projects p
                LEFT JOIN project_files f ON p.id = f.project_id
                GROUP BY p.id
                ORDER BY p.created_at DESC
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "created_at": row["created_at"],
                    "file_count": row["file_count"],
                    "total_size_bytes": row["total_size_bytes"],
                }
                for row in rows
            ]

    def get_project(self, project_id: str, include_files: bool = True) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    p.id, 
                    p.name, 
                    p.created_at,
                    COUNT(f.id) as file_count,
                    COALESCE(SUM(f.size_bytes), 0) as total_size_bytes
                FROM projects p
                LEFT JOIN project_files f ON p.id = f.project_id
                WHERE p.id = ?
                GROUP BY p.id
                """,
                (project_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            files = []
            if include_files:
                files = self.get_project_files(project_id)

            return {
                "id": row["id"],
                "name": row["name"],
                "created_at": row["created_at"],
                "file_count": row["file_count"],
                "total_size_bytes": row["total_size_bytes"],
                "files": files,
            }

    def save_file_record(
        self,
        project_id: str,
        filename: str,
        relative_path: str,
        file_type: str,
        size_bytes: int,
        line_count: int,
        stored_path: str,
    ) -> Dict[str, Any]:
        file_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO project_files (
                    id, project_id, filename, relative_path, file_type, 
                    size_bytes, line_count, created_at, stored_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, relative_path) DO UPDATE SET
                    filename = excluded.filename,
                    file_type = excluded.file_type,
                    size_bytes = excluded.size_bytes,
                    line_count = excluded.line_count,
                    created_at = excluded.created_at,
                    stored_path = excluded.stored_path
                """,
                (
                    file_id,
                    project_id,
                    filename,
                    relative_path,
                    file_type,
                    size_bytes,
                    line_count,
                    created_at,
                    stored_path,
                ),
            )
            conn.commit()

        return {
            "id": file_id,
            "project_id": project_id,
            "filename": filename,
            "relative_path": relative_path,
            "file_type": file_type,
            "size_bytes": size_bytes,
            "line_count": line_count,
            "created_at": created_at,
        }

    def get_project_files(self, project_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    id, project_id, filename, relative_path, 
                    file_type, size_bytes, line_count, created_at, stored_path
                FROM project_files
                WHERE project_id = ?
                ORDER BY relative_path ASC
                """,
                (project_id,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "project_id": row["project_id"],
                    "filename": row["filename"],
                    "relative_path": row["relative_path"],
                    "file_type": row["file_type"],
                    "size_bytes": row["size_bytes"],
                    "line_count": row["line_count"],
                    "created_at": row["created_at"],
                    "stored_path": row["stored_path"],
                }
                for row in rows
            ]

    def get_file(self, project_id: str, file_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    id, project_id, filename, relative_path, 
                    file_type, size_bytes, line_count, created_at, stored_path
                FROM project_files
                WHERE project_id = ? AND id = ?
                """,
                (project_id, file_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "project_id": row["project_id"],
                "filename": row["filename"],
                "relative_path": row["relative_path"],
                "file_type": row["file_type"],
                "size_bytes": row["size_bytes"],
                "line_count": row["line_count"],
                "created_at": row["created_at"],
                "stored_path": row["stored_path"],
            }

    def save_project_context(
        self, project_id: str, selections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM project_context_selections WHERE project_id = ?",
                (project_id,),
            )

            for sel in selections:
                sel_id = str(uuid.uuid4())
                cursor.execute(
                    """
                    INSERT INTO project_context_selections (
                        id, project_id, file_id, selected_all_lines, start_line, end_line, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sel_id,
                        project_id,
                        sel["file_id"],
                        1 if sel.get("selected_all_lines", True) else 0,
                        sel.get("start_line"),
                        sel.get("end_line"),
                        now,
                    ),
                )
            conn.commit()

        return self.get_project_context(project_id)

    def get_project_context(self, project_id: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    s.file_id,
                    s.selected_all_lines,
                    s.start_line,
                    s.end_line,
                    s.created_at,
                    f.filename,
                    f.relative_path,
                    f.file_type,
                    f.line_count
                FROM project_context_selections s
                JOIN project_files f ON s.file_id = f.id
                WHERE s.project_id = ?
                ORDER BY f.relative_path ASC
                """,
                (project_id,),
            )
            rows = cursor.fetchall()

            selected_files = []
            total_lines = 0
            updated_at = None

            for r in rows:
                is_all = bool(r["selected_all_lines"])
                start = r["start_line"]
                end = r["end_line"]
                file_lines = r["line_count"]

                if is_all or start is None or end is None:
                    lines_count = file_lines
                    start = 1
                    end = file_lines
                else:
                    lines_count = max(0, end - start + 1)

                total_lines += lines_count
                updated_at = r["created_at"]

                selected_files.append({
                    "file_id": r["file_id"],
                    "relative_path": r["relative_path"],
                    "filename": r["filename"],
                    "file_type": r["file_type"],
                    "total_lines": file_lines,
                    "selected_all_lines": is_all,
                    "start_line": start if not is_all else None,
                    "end_line": end if not is_all else None,
                    "selected_lines_count": lines_count,
                })

            return {
                "project_id": project_id,
                "total_selected_files": len(selected_files),
                "total_selected_lines": total_lines,
                "selected_files": selected_files,
                "updated_at": updated_at,
            }

    def clear_project_context(self, project_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM project_context_selections WHERE project_id = ?",
                (project_id,),
            )
            conn.commit()
            return True

    def delete_project(self, project_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()
            return cursor.rowcount > 0

    # --- Phase 6: Evaluation Persistence Methods ---

    def create_evaluation_run(
        self,
        run_id: str,
        dataset_id: str,
        model_name: str,
        modes: List[str],
        total_cases: int,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO evaluation_runs (
                    id, dataset_id, model_name, status, modes_json, 
                    total_cases, completed_cases, summary_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    run_id,
                    dataset_id,
                    model_name,
                    "running",
                    json.dumps(modes),
                    total_cases,
                    json.dumps([]),
                    now,
                ),
            )
            conn.commit()

        return {
            "id": run_id,
            "dataset_id": dataset_id,
            "model_name": model_name,
            "status": "running",
            "modes": modes,
            "total_cases": total_cases,
            "completed_cases": 0,
            "comparison": [],
            "results": [],
            "created_at": now,
        }

    def record_evaluation_result(
        self,
        result_id: str,
        run_id: str,
        question_id: str,
        mode: str,
        question: str,
        model_answer: str,
        reference_answer: str,
        context_supplied: str,
        citations: List[Dict[str, Any]],
        answer_correctness: float,
        citation_validity: Optional[float],
        evidence_coverage: float,
        unsupported_claim_rate: float,
        insufficient_context_handled: bool,
        tokens_used: int,
        latency_ms: int,
        error: Optional[str] = None,
        reviewer_notes: Optional[str] = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO evaluation_results (
                    id, run_id, question_id, mode, question, model_answer,
                    reference_answer, context_supplied, citations_json,
                    answer_correctness, citation_validity, evidence_coverage,
                    unsupported_claim_rate, insufficient_context_handled,
                    tokens_used, latency_ms, error, reviewer_notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    run_id,
                    question_id,
                    mode,
                    question,
                    model_answer,
                    reference_answer,
                    context_supplied,
                    json.dumps(citations),
                    answer_correctness,
                    citation_validity,
                    evidence_coverage,
                    unsupported_claim_rate,
                    1 if insufficient_context_handled else 0,
                    tokens_used,
                    latency_ms,
                    error,
                    reviewer_notes,
                    now,
                ),
            )
            cursor.execute(
                "UPDATE evaluation_runs SET completed_cases = completed_cases + 1 WHERE id = ?",
                (run_id,),
            )
            conn.commit()

    def finish_evaluation_run(
        self, run_id: str, status: str, summary: List[Dict[str, Any]]
    ):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE evaluation_runs SET status = ?, summary_json = ? WHERE id = ?",
                (status, json.dumps(summary), run_id),
            )
            conn.commit()

    def list_evaluation_runs(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, dataset_id, model_name, status, modes_json, 
                       total_cases, completed_cases, summary_json, created_at
                FROM evaluation_runs
                ORDER BY created_at DESC
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": r["id"],
                    "dataset_id": r["dataset_id"],
                    "model_name": r["model_name"],
                    "status": r["status"],
                    "modes": json.loads(r["modes_json"]),
                    "total_cases": r["total_cases"],
                    "completed_cases": r["completed_cases"],
                    "comparison": json.loads(r["summary_json"] or "[]"),
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    def get_evaluation_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, dataset_id, model_name, status, modes_json, 
                       total_cases, completed_cases, summary_json, created_at
                FROM evaluation_runs
                WHERE id = ?
                """,
                (run_id,),
            )
            run_row = cursor.fetchone()
            if not run_row:
                return None

            cursor.execute(
                """
                SELECT id, run_id, question_id, mode, question, model_answer,
                       reference_answer, context_supplied, citations_json,
                       answer_correctness, citation_validity, evidence_coverage,
                       unsupported_claim_rate, insufficient_context_handled,
                       tokens_used, latency_ms, error, reviewer_notes, created_at
                FROM evaluation_results
                WHERE run_id = ?
                ORDER BY created_at ASC
                """,
                (run_id,),
            )
            res_rows = cursor.fetchall()

            results = []
            for r in res_rows:
                results.append({
                    "id": r["id"],
                    "run_id": r["run_id"],
                    "question_id": r["question_id"],
                    "mode": r["mode"],
                    "question": r["question"],
                    "model_answer": r["model_answer"],
                    "reference_answer": r["reference_answer"],
                    "context_supplied": r["context_supplied"],
                    "citations": json.loads(r["citations_json"] or "[]"),
                    "answer_correctness": r["answer_correctness"],
                    "citation_validity": r["citation_validity"],
                    "evidence_coverage": r["evidence_coverage"],
                    "unsupported_claim_rate": r["unsupported_claim_rate"],
                    "insufficient_context_handled": bool(r["insufficient_context_handled"]),
                    "tokens_used": r["tokens_used"],
                    "latency_ms": r["latency_ms"],
                    "error": r["error"],
                    "reviewer_notes": r["reviewer_notes"],
                })

            return {
                "id": run_row["id"],
                "dataset_id": run_row["dataset_id"],
                "model_name": run_row["model_name"],
                "status": run_row["status"],
                "modes": json.loads(run_row["modes_json"]),
                "total_cases": run_row["total_cases"],
                "completed_cases": run_row["completed_cases"],
                "comparison": json.loads(run_row["summary_json"] or "[]"),
                "results": results,
                "created_at": run_row["created_at"],
            }


# Singleton instance
storage = StorageManager()
