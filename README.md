# ContextControl

**ContextControl** is a developer-focused context management tool that aims to reduce unsupported claims ("hallucinations") in LLM responses. Developers manually select code files or documentation that the AI is permitted to use. The AI answers strictly using the selected evidence, provides file and line references, and explicitly acknowledges when available context is insufficient.

---

## Tech Stack

- **Frontend**: Next.js 16 (App Router), TypeScript, Tailwind CSS v4, ESLint
- **Backend**: Python 3.14, FastAPI, Uvicorn, SQLite persistence layer
- **AI Integration**: Google Gemini API via official `google-genai` SDK (`gemini-2.5-flash`)
- **Testing**: pytest, HTTPX
- **Database (Later phase)**: PostgreSQL / Supabase with pgvector

---

## Project Structure

```text
hactoberfest/
├── frontend/                 # Next.js frontend application
│   ├── src/
│   │   ├── app/              # App router pages & layouts
│   │   └── lib/              # Centralized API client (`api.ts`)
│   ├── public/               # Static assets
│   ├── package.json          # Frontend dependencies & scripts
│   ├── tsconfig.json         # TypeScript configuration
│   └── next.config.ts        # Next.js configuration
├── backend/                  # Python FastAPI backend
│   ├── app/
│   │   ├── config.py         # Configurable limits, allowed extensions & filters
│   │   ├── models.py         # Pydantic schemas (Projects, Files, Context, Chat, Evaluations, Discovery)
│   │   ├── storage.py        # Modular SQLite persistence layer
│   │   ├── file_manager.py   # Safe ZIP extraction & path traversal defense
│   │   ├── gemini_service.py # Context Lock prompt policy & citation verification
│   │   ├── chunking.py       # Deterministic code chunking & line-boundary preservation
│   │   ├── embedding_service.py# Embedding providers (Gemini text-embedding-004 & Mock)
│   │   ├── vector_store.py   # PostgreSQL pgvector & test mock vector stores
│   │   ├── eval_dataset.py   # Built-in fixture codebase & evaluation test cases
│   │   ├── eval_service.py   # Evaluation engine (Baseline vs Context Lock vs Citations vs Semantic)
│   │   └── routers/
│   │       ├── projects.py   # Project, upload, file viewer, and context-locked chat APIs
│   │       ├── evaluations.py# Evaluation run, dataset inspection, and historical runs APIs
│   │       └── discovery.py  # Code chunk indexing, status, semantic search, and index deletion
│   ├── tests/
│   │   ├── test_projects.py  # Automated tests for projects and file uploads
│   │   ├── test_context.py   # Automated tests for file inspection & context selection
│   │   ├── test_chat.py      # Automated tests for Gemini Context Lock & citations
│   │   ├── test_evaluation.py# Automated tests for evaluation metrics & reproducible runs
│   │   └── test_semantic_discovery.py# Automated tests for pgvector, chunking, and Context Lock preservation
│   ├── storage/              # SQLite DB and project upload directories (Git-ignored)
│   ├── .venv/                # Python virtual environment (Git-ignored)
│   ├── main.py               # FastAPI application entrypoint
│   ├── requirements.txt      # Python dependencies
│   └── .env.example          # Environment variables template
├── .gitignore                # Workspace ignore file for Git
└── README.md                 # Project documentation and guide
```

---

## API Endpoints

### Health Check
- `GET /health` &rarr; `{"status": "ok", "service": "context-control-backend"}`

### Project Management & Safe Uploads
- `POST /api/projects` &rarr; Create a new project workspace.
- `GET /api/projects` &rarr; List all existing projects with file counts and total sizes.
- `GET /api/projects/{project_id}` &rarr; Retrieve project details and its indexed files.
- `GET /api/projects/{project_id}/files` &rarr; List indexed file metadata for a project.
- `POST /api/projects/{project_id}/upload` &rarr; Safely upload source code files or extract a `.zip` archive.

### File Viewer & Context Selection
- `GET /api/projects/{project_id}/files/{file_id}` &rarr; Retrieve text content and line metadata for a specific file.
- `POST /api/projects/{project_id}/context` &rarr; Save user's manual context selection (file IDs, whole-file vs custom line ranges).
- `GET /api/projects/{project_id}/context` &rarr; Retrieve saved context scope for a project.
- `DELETE /api/projects/{project_id}/context` &rarr; Clear saved context selections for a project.

### Gemini Context-Locked Chat (Phase 5)
- `POST /api/projects/{project_id}/chat` &rarr; Query Gemini with backend-enforced Context Lock. Reconstructs exact selected source lines strictly from server storage and validates citations against ground-truth line bounds.

### Evaluation & Reliability Benchmarks (Phase 6)
- `GET /api/evaluations/dataset` &rarr; Retrieve the reproducible fixture codebase and test questions.
- `POST /api/evaluations/run` &rarr; Execute a benchmark across selectable modes (`baseline`, `context_lock`, `context_lock_citations`) with optional deterministic mock execution.
- `GET /api/evaluations/runs` &rarr; List historical evaluation runs and aggregate metrics.
- `GET /api/evaluations/runs/{run_id}` &rarr; Retrieve details, per-mode metrics, and per-question test results for a specific run.

### Semantic Context Discovery & pgvector (Phase 7)
- `POST /api/projects/{project_id}/index` &rarr; Chunks eligible files, computes embeddings, and indexes them in pgvector.
- `GET /api/projects/{project_id}/index/status` &rarr; Reports vector index status, chunk counts, model metadata, and pgvector configuration guidance.
- `POST /api/projects/{project_id}/search-context` &rarr; Searches project code chunks semantically using vector cosine similarity. Returns advisory candidates with line ranges and proximity scores without automatically authorizing code for AI requests.
- `DELETE /api/projects/{project_id}/index` &rarr; Deletes vector index data from pgvector while leaving original uploaded source files safe and intact.

---

## Getting Started

### Prerequisites

Ensure you have installed:
- **Node.js** (v20+ recommended) and **npm**
- **Python** (v3.10+ recommended)
- **Git**
- **Gemini API Key**: Obtain a free key at [https://aistudio.google.com/](https://aistudio.google.com/)

---

### 1. Backend Configuration & Setup

1. Open `backend/.env` (create from `backend/.env.example` if not present):
   ```env
   HOST=127.0.0.1
   PORT=8000
   ENVIRONMENT=development
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   GEMINI_MODEL=gemini-2.5-flash
   ```
2. Activate the virtual environment and install dependencies:
   ```powershell
   cd backend
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Start the FastAPI server:
   ```powershell
   python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```
   API Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

### 2. Frontend Setup

Open a second terminal at the project root (`hactoberfest/`):

```bash
cd frontend
npm install
npm run dev
```

The frontend will be live at: [http://localhost:3000](http://localhost:3000)

---

## Manual Verification Guide

### 1. Testing Context Lock in Project Chat
1. Open the UI at [http://localhost:3000](http://localhost:3000).
2. Click **Create Project** and name it `Demo Service`.
3. In the project workspace, upload a small codebase or multiple source files (e.g. `auth.py`, `models.py`).
4. **Scope Evidence**: In the **Files & Line Scope** tab, check the files to include. For one file, check **Scope Custom Lines** and pick a narrow range (e.g. Lines 5 to 15).
5. Click **Lock Context** to persist the scope.
6. Switch to the **Context-Locked Chat** tab.
7. Ask a question regarding the scoped lines (e.g. *"What does the helper function do?"*).
8. **Observe Verification**:
   - The response includes structured citations indicating the exact file and lines (`auth.py:L5–L15`).
   - Click the citation to immediately highlight and open that line range in the code viewer.
   - If you ask about something *not* in the scoped lines (e.g. *"How is the database connected?"*), Gemini will flag **Insufficient Context Acknowledged** and identify what evidence is missing instead of fabricating an answer.

### 2. Running Evaluation Benchmarks (Phase 6)
1. In the sidebar, click **Evaluation**.
2. Select the evaluation modes to compare:
   - **Mode A (Baseline)**: Normal prompt with question only (simulating standard LLM interaction without scoped context).
   - **Mode B (Context Lock)**: Scoped strictly to the selected source lines reconstructed server-side.
   - **Mode C (Context Lock + Citations)**: Scoped strictly with mandatory structured citation validation.
3. Check **Deterministic Mock Run** for zero-cost, instant offline verification, or uncheck to run against live Gemini API (`GEMINI_API_KEY` required).
4. Click **Run Benchmark**.
5. Inspect the **Comparative Metrics Table**:
   - **Citation Validity**: Validated citations / total citations (Baseline shows `N/A`).
   - **Unsupported Claim Rate**: Invalid citations / total citations.
   - **Insufficient Context Handling**: Success rate when the question cannot be answered from the provided context.
   - **Latency & Token Usage**: Side-by-side performance comparison.
6. Review the **Question Audit** section to inspect model responses, expected reference facts, and citation verification outcomes for each test case.

---

## Evaluation Dataset & Metric Heuristics

The evaluation suite uses a reproducible test dataset defined in `backend/app/eval_dataset.py`:
- **Codebase**: A 3-file authentication microservice (`auth.py`, `token_manager.py`, `config.py`).
- **Test Scenarios**:
  - `EVAL-001`: Direct answerable query within scoped lines.
  - `EVAL-002`: Multi-file dependency question where evidence in a second file is intentionally withheld.
  - `EVAL-003`: Question with false premise (asking about Redis session invalidation when only stateless JWTs are used).
  - `EVAL-004`: Question about database migration history which is completely absent from the codebase.

> **Note on Evaluation Metrics**: Automated metrics for citation validity and insufficient context detection are computed deterministically. Heuristic answer correctness uses keyword/fact matching and is flagged for human review to avoid false claims of automated perfection. ContextControl aims to bound evidence and verify citations, not eliminate LLM hallucinations entirely.

### 3. Testing Semantic Context Discovery (Phase 7)
1. In the project workspace, click the **Find Relevant Context** tab.
2. If PostgreSQL/pgvector is not yet configured, a setup notice is clearly shown. Check **Mock Mode (Offline)** for zero-setup deterministic testing.
3. Click **Index Codebase**. Observe that eligible source files are split along deterministic boundaries into line-bounded chunks with SHA-256 deduplication.
4. In the search box, enter a concept query (e.g. *"JWT token expiration validation"* or *"password check"*).
5. Click **Find Relevant Code**.
6. Inspect the surfaced candidate chunks:
   - Relative file path and exact line numbers (`token_manager.py:L13–L16`).
   - Vector cosine similarity score.
   - Code snippet preview.
7. Click **Inspect in Viewer** to immediately jump to the source file and view the lines.
8. Click **+ Approve & Add** to explicitly add the candidate snippet into your **Selected Context Scope**.
9. Notice the strict boundary:
   - **Suggested Context:** Discovered by semantic search (advisory only).
   - **Selected Context:** Explicitly approved by the developer.
   - **Locked Context:** Reconstructed and verified strictly by the FastAPI backend for the AI request.

---

## PostgreSQL / Supabase and pgvector Setup Guide

ContextControl supports semantic search via PostgreSQL and the `pgvector` extension.

### 1. Local PostgreSQL Setup
1. Install PostgreSQL (v15+) and the `pgvector` extension:
   ```bash
   # Debian / Ubuntu
   sudo apt install postgresql-16-pgvector

   # Homebrew (macOS)
   brew install pgvector
   ```
2. Create database and enable the vector extension:
   ```sql
   CREATE DATABASE contextcontrol;
   \c contextcontrol
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Set `DATABASE_URL` in `backend/.env`:
   ```env
   DATABASE_URL=postgresql://postgres:password@localhost:5432/contextcontrol
   EMBEDDING_PROVIDER=gemini
   EMBEDDING_MODEL=text-embedding-004
   EMBEDDING_DIMENSION=768
   ```

### 2. Supabase Setup
1. Create a project at [supabase.com](https://supabase.com).
2. In the Supabase SQL Editor, run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Copy your project connection string and set `DATABASE_URL` in `backend/.env`.

### 3. Unconfigured Fallback Guarantee
If `DATABASE_URL` is not configured or PostgreSQL is offline:
- ContextControl **never silently substitutes an in-memory store and claims pgvector is running**.
- The API reports `pgvector_enabled: false` and displays actionable setup guidance.
- Developers can check **Mock Mode (Offline)** for zero-cost offline test ranking.
- All manual file inspection, Context Lock, citation validation, and evaluation features remain **100% operational**.

---

## Security Hardening & Reliability (Phase 8)

ContextControl includes production-grade security and reliability guardrails:
- **Correlation ID Tracking**: Every HTTP request receives an `X-Request-ID` header, propagated through all error logs and JSON responses for clean tracing.
- **Leak-Proof Error Sanitization**: API keys, internal paths, and raw credentials are automatically redacted (`[REDACTED]`) from error payloads and logs before reaching the client.
- **ZIP Symlink & Traversal Protections**: Rejects Unix symlinks (`0o120000`), device nodes, directory traversal (`../`), and absolute paths within archives and single file uploads.
- **Distinct Deletion Lifecycles**:
  - `DELETE /api/projects/{id}`: Permanently deletes the project, SQLite records, stored files on disk, and vector chunks.
  - `DELETE /api/projects/{id}/index`: Deletes generated vector embeddings while leaving original uploaded source files completely intact.
  - `DELETE /api/projects/{id}/context`: Clears active context scope without deleting files or index data.
- **Request Limits & Timeouts**:
  - Configurable timeouts on external Gemini calls (`GEMINI_REQUEST_TIMEOUT_SECONDS=60`).
  - Limits on upload sizes (20MB ZIP, 2MB single file), question lengths, and context character sizes.
- **Startup Configuration Validation**:
  - Validates directories, storage permissions, and configuration keys at startup, logging status safely without exposing secrets.

---

## Production Deployment Checklist

Before deploying ContextControl to a staging or production server:

1. **Environment Configuration**:
   - Set `ENVIRONMENT=production` in `backend/.env`.
   - Set `CORS_ORIGINS` to your exact frontend domain(s) (e.g. `https://contextcontrol.yourdomain.com`). Never leave open (`*`) in production.
   - Configure `GEMINI_API_KEY` exclusively on the backend server. Never expose in frontend builds.
2. **Storage & Backups**:
   - Mount persistent storage for `backend/storage/` if using containers (Docker/Kubernetes).
   - Regularly backup `backend/storage/context_control.db` and `backend/storage/projects/`.
3. **Database (pgvector)**:
   - For PostgreSQL/Supabase, use SSL connection strings: `postgresql://user:password@host:5432/dbname?sslmode=require`.
4. **Reverse Proxy & HTTPS**:
   - Terminate TLS/HTTPS via Nginx, Caddy, or Cloudflare.
   - Forward `X-Forwarded-For` and `X-Request-ID` headers to Uvicorn.
5. **Access Control Notice**:
   > [!IMPORTANT]
   > ContextControl is architected as an engineering team developer tool without built-in end-user authentication or multi-tenant RBAC. For public web deployment, place the application behind an authenticating gateway (e.g., Cloudflare Zero Trust, Tailscale, OAuth2 Proxy, or VPN).

---

## Troubleshooting Guide

| Issue | Likely Cause | Resolution |
| :--- | :--- | :--- |
| **HTTP 503: GEMINI_API_KEY is not configured** | Missing `.env` setting | Add `GEMINI_API_KEY=AIzaSy...` to `backend/.env` and restart backend. |
| **HTTP 401: Invalid GEMINI_API_KEY** | Invalid or revoked key | Verify key at [Google AI Studio](https://aistudio.google.com/). |
| **HTTP 429: Rate limit exceeded** | Quota or RPM limit reached | Wait for quota reset, or use Mock Mode (`use_mock=True`) for benchmarks. |
| **HTTP 504: Request timed out** | Slow response from upstream AI | Increase `GEMINI_REQUEST_TIMEOUT_SECONDS` in `backend/.env`. |
| **HTTP 503: pgvector is not configured** | PostgreSQL not connected | Check `DATABASE_URL` or enable Mock Mode for offline testing. |
| **Files skipped with "Symlinks or special Unix file types rejected"** | Unsafe archive contents | Normal security behavior; archives containing symlinks are sanitized. |

---

## Documentation & Demo Resources

Comprehensive Phase 9 technical documentation, presentation materials, and demo assets:

- [Demo Walkthrough Guide](file:///e:/hactoberfest/docs/demo-guide.md): Step-by-step 3-scenario walkthrough with the synthetic demo codebase.
- [System Architecture](file:///e:/hactoberfest/docs/architecture.md): Deep-dive into Context Lock enforcement, 3-tier security boundaries, and Mermaid diagrams.
- [Evaluation & Reliability Report](file:///e:/hactoberfest/docs/evaluation-report.md): Empirical benchmark findings, token metrics, citation rates, and boundary disclaimers.
- [Presentation Outline & Pitch](file:///e:/hactoberfest/docs/presentation-outline.md): 10-point presentation, 60-second pitch, technical interview deep-dives, and judge Q&As.
- [Verification & Readiness Report](file:///e:/hactoberfest/docs/verification-report.md): Audit of test suites (41/41 passing), builds, and feature checklist.
- [Synthetic Demo Codebase](file:///e:/hactoberfest/demo_codebase/README.md): Pre-packaged demo repository with double-charge bug and reference ground truth ([`demo_codebase.zip`](file:///e:/hactoberfest/demo_codebase.zip)).

---

## Running Automated Tests

Run the full pytest suite (41 unit, security, context lock, evaluation, and semantic discovery tests):

```powershell
cd backend
.\.venv\Scripts\pytest -v
```

Run the Next.js production build check:

```powershell
cd frontend
npm run build
```
