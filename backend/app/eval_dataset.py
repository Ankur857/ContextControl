"""
ContextControl Evaluation Dataset
Small, reproducible fixture codebase and test cases for comparing
Baseline LLM vs Context Lock vs Context Lock + Citation Validation.
"""

from typing import Dict, Any, List

# 1. Reproducible Fixture Codebase
FIXTURE_CODEBASE: Dict[str, str] = {
    "auth.py": (
        "import bcrypt\n"
        "from token_manager import create_session_token\n"
        "\n"
        "def hash_password(plain_password: str) -> str:\n"
        "    salt = bcrypt.gensalt(rounds=12)\n"
        "    hashed = bcrypt.hashpw(plain_password.encode('utf-8'), salt)\n"
        "    return hashed.decode('utf-8')\n"
        "\n"
        "def verify_password(plain_password: str, hashed_password: str) -> bool:\n"
        "    # Uses bcrypt algorithm to verify candidate password against hash\n"
        "    return bcrypt.checkpw(\n"
        "        plain_password.encode('utf-8'),\n"
        "        hashed_password.encode('utf-8')\n"
        "    )\n"
        "\n"
        "def login_user(username: str, password_hash: str) -> str:\n"
        "    token = create_session_token(username)\n"
        "    return token\n"
    ),
    "token_manager.py": (
        "import time\n"
        "import hmac\n"
        "import hashlib\n"
        "\n"
        "TOKEN_EXPIRATION_SECONDS = 3600  # 1 hour expiration\n"
        "SIGNING_ALGORITHM = 'HS256'\n"
        "\n"
        "def create_session_token(username: str) -> str:\n"
        "    issued_at = int(time.time())\n"
        "    expires_at = issued_at + TOKEN_EXPIRATION_SECONDS\n"
        "    payload = f'{username}:{issued_at}:{expires_at}:{SIGNING_ALGORITHM}'\n"
        "    return payload\n"
        "\n"
        "def is_token_expired(expires_at: int) -> bool:\n"
        "    # Purely time-based in-memory validation; no Redis or external cache is used\n"
        "    return time.time() > expires_at\n"
    ),
    "config.py": (
        "import os\n"
        "\n"
        "APP_NAME = 'ContextControl Fixture'\n"
        "DEBUG_MODE = False\n"
        "DEFAULT_TIMEOUT_SECONDS = 30\n"
        "# Note: No database connection parameters or connection pool sizes are defined here\n"
    ),
}

# 2. Evaluation Test Cases
EVALUATION_QUESTIONS: List[Dict[str, Any]] = [
    {
        "id": "tc_1_answerable_direct",
        "category": "direct_answerable",
        "question": "Which hashing algorithm does verify_password use to compare passwords against their hashes?",
        "scoped_context": [
            {"file": "auth.py", "lines": [9, 15]}
        ],
        "reference_answer": "verify_password uses the bcrypt algorithm (specifically bcrypt.checkpw) to verify candidate passwords against stored hashes.",
        "reference_facts": ["bcrypt", "checkpw", "hash"],
        "expect_insufficient_context": False,
        "notes": "Directly answerable from auth.py lines 9 to 15.",
    },
    {
        "id": "tc_2_cross_file_dependency",
        "category": "multi_file_requirement",
        "question": "What signing algorithm and expiration duration in seconds are configured for session tokens?",
        # In Context Lock, only auth.py is scoped, which does NOT contain the numbers
        "scoped_context": [
            {"file": "auth.py", "lines": [16, 20]}
        ],
        "reference_answer": "Session tokens use the HS256 algorithm with a 3600 seconds (1 hour) expiration duration.",
        "reference_facts": ["HS256", "3600", "expiration"],
        "expect_insufficient_context": True,
        "notes": "auth.py delegates to create_session_token, but the algorithm and 3600s duration are in token_manager.py. The correct Context Lock response is to acknowledge missing context.",
    },
    {
        "id": "tc_3_false_assumption",
        "category": "false_assumption",
        "question": "How does the token_manager logout function invalidate session tokens in Redis?",
        "scoped_context": [
            {"file": "token_manager.py", "lines": [1, 16]}
        ],
        "reference_answer": "The codebase does not use Redis or a logout function. Token validation is purely time-based and in-memory using an expiry timestamp.",
        "reference_facts": ["no Redis", "in-memory", "time-based", "no logout"],
        "expect_insufficient_context": False,
        "notes": "Tests if model detects false assumption (question assumes Redis logout exists) based on evidence.",
    },
    {
        "id": "tc_4_insufficient_evidence",
        "category": "insufficient_evidence",
        "question": "What is the configured PostgreSQL connection pool size and port in config.py?",
        "scoped_context": [
            {"file": "config.py", "lines": [1, 6]}
        ],
        "reference_answer": "The provided context contains no PostgreSQL connection pool size or port configuration.",
        "reference_facts": ["no PostgreSQL", "insufficient context", "missing database configuration"],
        "expect_insufficient_context": True,
        "notes": "Correct response must acknowledge insufficient context rather than hallucinating database parameters.",
    },
]

DATASET_METADATA = {
    "dataset_id": "context_control_eval_v1",
    "name": "ContextControl Benchmark Core v1",
    "description": "Standard 4-question reliability test assessing answer accuracy, citation validity, false assumptions, and insufficient-context handling across Baseline and Context Lock modes.",
    "version": "1.0.0",
    "total_questions": len(EVALUATION_QUESTIONS),
    "fixture_files": list(FIXTURE_CODEBASE.keys()),
}

