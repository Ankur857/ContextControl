import os
from pathlib import Path

# Base storage directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file automatically if present
env_file = BASE_DIR / ".env"
if env_file.is_file():
    with open(env_file, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            _k = _k.strip()
            _v = _v.strip().strip("'\"")
            if _k and _k not in os.environ:
                os.environ[_k] = _v
DEFAULT_STORAGE_DIR = str(BASE_DIR / "storage")
STORAGE_DIR = os.environ.get("STORAGE_DIR", DEFAULT_STORAGE_DIR)
DB_PATH = os.path.join(STORAGE_DIR, "context_control.db")
PROJECTS_DIR = os.path.join(STORAGE_DIR, "projects")

# Upload limits
MAX_ZIP_SIZE_BYTES = int(os.environ.get("MAX_ZIP_SIZE_BYTES", 20 * 1024 * 1024))  # 20 MB
MAX_SINGLE_FILE_SIZE_BYTES = int(os.environ.get("MAX_SINGLE_FILE_SIZE_BYTES", 2 * 1024 * 1024))  # 2 MB
MAX_FILE_COUNT_PER_UPLOAD = int(os.environ.get("MAX_FILE_COUNT_PER_UPLOAD", 500))

# Gemini API Configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview").strip()
MAX_CONTEXT_CHARS = int(os.environ.get("MAX_CONTEXT_CHARS", 100_000))
MAX_QUESTION_CHARS = int(os.environ.get("MAX_QUESTION_CHARS", 2000))

# Supported text extensions for ContextControl source evidence
SUPPORTED_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".txt",
    ".css",
    ".html",
    ".sql",
    ".java",
    ".cpp",
    ".h",
    ".c",
    ".hpp",
    ".go",
    ".rs",
    ".yaml",
    ".yml",
    ".toml",
    ".sh",
    ".xml",
    ".env.example",
}

# Directories that should never be ingested into AI context
FORBIDDEN_DIR_NAMES = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    "out",
    "target",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "ENV",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
    ".turbo",
}

# Obvious secrets, credentials, or private keys to strictly reject
FORBIDDEN_FILE_EXACT_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
    "id_rsa",
    "id_dsa",
    "id_ed25519",
    "credentials.json",
    "token.json",
    "secrets.json",
    "master.key",
}

FORBIDDEN_FILE_EXTENSIONS = {
    # Binaries / Executables
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".msi",
    ".bat",
    ".cmd",
    ".jar",
    ".war",
    ".class",
    ".pyc",
    ".o",
    ".a",
    # Keys & Certificates
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
    ".cer",
    ".kdbx",
    # Media & Archives
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
    ".pdf",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
}

# --- Phase 7: Semantic Context Discovery & pgvector Configuration ---
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "gemini").strip().lower()
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-004").strip()
EMBEDDING_DIMENSION = int(os.environ.get("EMBEDDING_DIMENSION", 768))
ALLOW_TEST_VECTOR_STORE = os.environ.get("ALLOW_TEST_VECTOR_STORE", "false").strip().lower() in ("true", "1", "yes")

# Chunking settings
CHUNK_SIZE_LINES = int(os.environ.get("CHUNK_SIZE_LINES", 35))
CHUNK_OVERLAP_LINES = int(os.environ.get("CHUNK_OVERLAP_LINES", 5))
MAX_EMBEDDING_BATCH_SIZE = int(os.environ.get("MAX_EMBEDDING_BATCH_SIZE", 25))
MAX_FILE_LINES_FOR_CHUNKING = int(os.environ.get("MAX_FILE_LINES_FOR_CHUNKING", 5000))

# --- Phase 8: Security, Reliability & Production Hardening ---
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").strip().lower()
GEMINI_REQUEST_TIMEOUT_SECONDS = int(os.environ.get("GEMINI_REQUEST_TIMEOUT_SECONDS", 60))

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
]
raw_cors = os.environ.get("CORS_ORIGINS", "").strip()
if raw_cors:
    CORS_ALLOWED_ORIGINS = [orig.strip() for orig in raw_cors.split(",") if orig.strip()]
else:
    CORS_ALLOWED_ORIGINS = DEFAULT_CORS_ORIGINS


def validate_startup_config() -> dict:
    """
    Validates server environment and storage directories at startup.
    Returns status dictionary reporting configuration state safely without leaking secrets.
    """
    os.makedirs(STORAGE_DIR, exist_ok=True)
    os.makedirs(PROJECTS_DIR, exist_ok=True)

    has_gemini_key = bool(GEMINI_API_KEY)
    has_postgres_url = bool(DATABASE_URL)

    status_report = {
        "environment": ENVIRONMENT,
        "storage_dir": STORAGE_DIR,
        "projects_dir": PROJECTS_DIR,
        "gemini_api_configured": has_gemini_key,
        "gemini_model": GEMINI_MODEL,
        "gemini_timeout_seconds": GEMINI_REQUEST_TIMEOUT_SECONDS,
        "pgvector_configured": has_postgres_url,
        "embedding_provider": EMBEDDING_PROVIDER,
        "cors_origins_count": len(CORS_ALLOWED_ORIGINS),
    }

    return status_report



