# ContextControl

**ContextControl** is a developer-focused context management tool that aims to reduce unsupported claims ("hallucinations") in LLM responses. Developers manually select code files or documentation that the AI is permitted to use. The AI answers strictly using the selected evidence, provides file and line references, and explicitly acknowledges when available context is insufficient.

---

## Tech Stack

- **Frontend**: Next.js (App Router), TypeScript, Tailwind CSS, ESLint
- **Backend**: Python 3.14, FastAPI, Uvicorn
- **AI Integration (Later phase)**: Google Gemini API
- **Database (Later phase)**: PostgreSQL / Supabase with pgvector

---

## Project Structure

```text
hactoberfest/
├── frontend/             # Next.js frontend application
│   ├── src/
│   │   └── app/          # App router pages & layouts
│   ├── public/           # Static assets
│   ├── package.json      # Frontend dependencies & scripts
│   ├── tsconfig.json     # TypeScript configuration
│   └── next.config.ts    # Next.js configuration
├── backend/              # Python FastAPI backend
│   ├── .venv/            # Python virtual environment (ignored by Git)
│   ├── main.py           # FastAPI entrypoint and endpoints
│   ├── requirements.txt  # Python package dependencies
│   └── .env.example      # Environment variables template
├── .gitignore            # Workspace ignore file for Git
└── README.md             # Project documentation and guide
```

---

## Getting Started

### Prerequisites

Ensure you have installed:
- **Node.js** (v20+ recommended) and **npm**
- **Python** (v3.10+ recommended)
- **Git**

---

### 1. Frontend Setup (Next.js)

Open a terminal at the project root (`hactoberfest/`):

```bash
# Navigate to the frontend directory
cd frontend

# Install dependencies (already initialized)
npm install

# Start the Next.js development server
npm run dev
```

The frontend will be live at:
- URL: [http://localhost:3000](http://localhost:3000)

**To stop the frontend server**: Press `Ctrl + C` in the terminal running `npm run dev`.

---

### 2. Backend Setup (FastAPI)

Open a second terminal at the project root (`hactoberfest/`):

```bash
# Navigate to the backend directory
cd backend

# Create virtual environment (if not already created)
python -m venv .venv

# Activate the virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Windows (Command Prompt):
.\.venv\Scripts\activate.bat
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the FastAPI development server with hot-reload
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The backend API will be live at:
- Health check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- Interactive OpenAPI Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

**To stop the backend server**: Press `Ctrl + C` in the terminal running Uvicorn.

---

## Health Verification

You can verify that both services are healthy:

1. **Frontend**: Open [http://localhost:3000](http://localhost:3000) in your browser. You should see the default Next.js starter page.
2. **Backend**:
   - In browser: Visit [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
   - In PowerShell:
     ```powershell
     (Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing).Content
     ```
   - Expected response:
     ```json
     {"status": "ok", "service": "context-control-backend"}
     ```

