"""
Manhua Translation System - FastAPI Application.

Main entry point for the web API.
"""

from contextlib import asynccontextmanager
import asyncio
import os
from pathlib import Path
import logging
from uuid import uuid4

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .deps import get_settings
from .routes import translate, manga, scraper, parser
from .routes import settings as settings_router
from .routes import system
from fastapi.staticfiles import StaticFiles

# 初始化日志系统
from core.logging_config import init_default_logging
from core.model_setup import ModelRegistry, ModelWarmupService

init_default_logging()
logger = logging.getLogger(__name__)


def _get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return request_id
    request_id = str(uuid4())
    request.state.request_id = request_id
    return request_id


def _build_error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    detail,
) -> JSONResponse:
    request_id = _get_request_id(request)
    response = JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
            },
        },
    )
    response.headers["X-Request-Id"] = request_id
    return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    settings = get_settings()

    # Create required directories
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.temp_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.static_dir).mkdir(parents=True, exist_ok=True)

    registry = ModelRegistry()
    app.state.model_registry = registry
    auto_setup = os.getenv("AUTO_SETUP_MODELS", "on").lower() not in {
        "0",
        "false",
        "off",
    }
    if auto_setup:
        service = ModelWarmupService(registry)
        app.state.model_warmup_task = asyncio.create_task(service.warmup())

    yield

    print("👋 Shutting down...")


app = FastAPI(
    title="Manhua Translation API",
    description="AI-powered manga/manhua translation system",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(translate.router, prefix="/api/v1")
app.include_router(manga.router, prefix="/api/v1")
app.include_router(scraper.router, prefix="/api/v1")
app.include_router(parser.router, prefix="/api/v1")
app.include_router(settings_router.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")

# Mount static files
settings = get_settings()
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
app.mount(
    "/data", StaticFiles(directory=Path(settings.data_dir).resolve()), name="data"
)
app.mount(
    "/output", StaticFiles(directory=Path(settings.output_dir).resolve()), name="output"
)

from fastapi.responses import FileResponse, HTMLResponse


def _should_serve_frontend() -> bool:
    return os.getenv("SERVE_FRONTEND", "").lower() == "dev"


dist_dir = Path("app/static/dist")
if _should_serve_frontend() and (dist_dir / "assets").exists():
    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if _should_serve_frontend():

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def catch_all(request: Request, full_path: str):
        """Serve the frontend SPA."""
        # Allow API endpoints to pass through (handled by previous routes)
        # But if no API matched (404), they usually fall through here unless processed.
        # Actually, FastAPI matches specific routes first.
        # We just need to ensure we don't capture /api/ if it wasn't matched?
        # No, API routers are included above. If they don't match, it falls here (if this is last).

        # We should exclude /data and /output explicitly just in case, though they are mounted.
        if (
            full_path.startswith("api")
            or full_path.startswith("data")
            or full_path.startswith("output")
        ):
            # Let default 404 handler take it (or return 404 manually)
            # But since we are IN a route handler, we return response.
            return JSONResponse(status_code=404, content={"detail": "Not Found"})

        index_file = dist_dir / "index.html"
        if not index_file.exists():
            return HTMLResponse(
                "Frontend build not found. Please run 'npm run build'.", status_code=500
            )

        # Serve static files that live alongside index.html (manifest, service worker, icons, etc).
        # This keeps the SPA fallback, while allowing root-level assets generated by Vite.
        if full_path:
            candidate = dist_dir / full_path
            try:
                dist_root = dist_dir.resolve()
                resolved = candidate.resolve()
            except FileNotFoundError:
                resolved = None
            if resolved and resolved.is_file():
                try:
                    resolved.relative_to(dist_root)
                except ValueError:
                    pass
                else:
                    return FileResponse(resolved)

        return FileResponse(index_file)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    message = detail if isinstance(detail, str) else f"HTTP {exc.status_code}"
    return _build_error_response(
        request,
        status_code=exc.status_code,
        code=f"HTTP_{exc.status_code}",
        message=message,
        detail=detail,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return _build_error_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        detail=exc.errors(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.exception(
        "[%s] Unhandled exception on %s %s",
        _get_request_id(request),
        request.method,
        request.url.path,
    )
    return _build_error_response(
        request,
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="Internal server error",
        detail="Internal server error",
    )


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
