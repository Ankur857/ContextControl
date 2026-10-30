import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import (
    CORS_ALLOWED_ORIGINS,
    ENVIRONMENT,
    GEMINI_API_KEY,
    validate_startup_config,
)
from app.routers.projects import router as projects_router
from app.routers.evaluations import router as evaluations_router
from app.routers.discovery import router as discovery_router

logger = logging.getLogger("contextcontrol")
logging.basicConfig(
    level=logging.INFO if ENVIRONMENT != "development" else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: validate directories and configurations safely
    startup_info = validate_startup_config()
    logger.info(
        f"ContextControl backend starting in '{startup_info['environment']}' environment. "
        f"Storage initialized at '{startup_info['storage_dir']}'. "
        f"Gemini API: {'configured' if startup_info['gemini_api_configured'] else 'unconfigured'}. "
        f"pgvector: {'configured' if startup_info['pgvector_configured'] else 'unconfigured'}."
    )
    yield
    # Shutdown
    logger.info("ContextControl backend shutting down cleanly.")


app = FastAPI(
    title="ContextControl Backend",
    description="Context management backend to reduce unsupported claims in LLM responses.",
    version="1.0.0",
    lifespan=lifespan,
)

# 1. Correlation ID Middleware
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = req_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


# 2. Configurable Production-Ready CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


# 3. Global Exception Handlers (Leak-Proof)
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    req_id = getattr(request.state, "request_id", "unknown")
    detail = exc.detail
    if isinstance(detail, str) and GEMINI_API_KEY:
        detail = detail.replace(GEMINI_API_KEY, "[REDACTED]")

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "request_id": req_id},
        headers={"X-Request-ID": req_id},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", "unknown")
    err_str = str(exc)
    if GEMINI_API_KEY:
        err_str = err_str.replace(GEMINI_API_KEY, "[REDACTED]")

    logger.error(f"[Request {req_id}] Unhandled error: {err_str}", exc_info=False)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal server error occurred.",
            "request_id": req_id,
        },
        headers={"X-Request-ID": req_id},
    )


# Mount API Routers
app.include_router(projects_router)
app.include_router(evaluations_router)
app.include_router(discovery_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "context-control-backend"}


@app.get("/health/details")
def health_details():
    conf = validate_startup_config()
    return {
        "status": "ok",
        "service": "context-control-backend",
        "version": "1.0.0",
        "environment": conf["environment"],
        "gemini_configured": conf["gemini_api_configured"],
        "pgvector_configured": conf["pgvector_configured"],
    }
