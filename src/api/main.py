# =============================================================================
# VM Automation - FastAPI Application Entry Point
# =============================================================================
"""
Point d'entrée principal de l'API FastAPI.
Configure l'application, les middlewares, et les routes.
"""

import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.common.auth import decode_token
from starlette.middleware.base import BaseHTTPMiddleware

from src.common.config import settings
from src.common.database import close_db, init_db
from src.common.exceptions import VMAutomationError
from src.common.logging import get_logger, setup_logging

# Routers
from src.api.routers import auth, callbacks, console, guacamole, health, hypervisors, vms, deployments, templates, realtime, software_catalog, settings as settings_router, terminal, vnc

logger = get_logger(__name__)


def get_rate_limit_key(request: Request) -> str:
    """
    Use user_id for authenticated requests, fall back to IP for anonymous.

    This prevents a single user from being rate-limited differently when
    behind a shared IP (e.g., corporate NAT), and also prevents one user
    from exhausting the rate limit for all users on the same IP.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            token = auth_header[7:]
            payload = decode_token(token, expected_type="access")
            return f"user:{payload.sub}"
        except Exception:
            pass
    return get_remote_address(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestion du cycle de vie de l'application.
    Startup et shutdown hooks.
    """
    # Startup
    setup_logging()
    logger.info(
        "application_starting",
        app_name=settings.app_name,
        environment=settings.app_env,
        debug=settings.debug,
    )
    
    # Initialisation de la base de données
    try:
        await init_db()
        logger.info("database_initialized")
    except Exception as e:
        logger.error("database_initialization_failed", error=str(e))
        # Ne pas bloquer le démarrage en dev
        if settings.app_env != "development":
            raise
    
    logger.info("application_started", port=settings.api_port)
    
    yield
    
    # Shutdown
    logger.info("application_shutting_down")
    await close_db()
    logger.info("application_stopped")


# =============================================================================
# Middleware
# =============================================================================


def _is_websocket(scope: dict) -> bool:
    """Check if a request scope is a WebSocket connection."""
    return scope.get("type") == "websocket"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response."""

    async def dispatch(self, request: Request, call_next):
        if _is_websocket(request.scope):
            return await call_next(request)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        # Replace server header (uvicorn adds its own, we override after)
        response.headers["Server"] = "VM-Automation"
        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Generate or propagate X-Request-ID for every request."""

    async def dispatch(self, request: Request, call_next):
        if _is_websocket(request.scope):
            return await call_next(request)
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        structlog.contextvars.unbind_contextvars("request_id")
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every completed request with method, path, status and duration."""

    async def dispatch(self, request: Request, call_next):
        if _is_websocket(request.scope):
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        access_logger = structlog.get_logger("api.access")
        access_logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
            client_ip=request.client.host if request.client else None,
        )
        return response


def create_app() -> FastAPI:
    """
    Factory pour créer l'application FastAPI.
    Permet de créer plusieurs instances pour les tests.
    """
    app = FastAPI(
        title="VM Automation API",
        description="API pour l'automatisation du déploiement de machines virtuelles",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )
    
    # Rate limiting (per-user when authenticated, per-IP when anonymous)
    limiter = Limiter(
        key_func=get_rate_limit_key,
        default_limits=["60/minute"],
        storage_uri="memory://",
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # Security headers middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # Observability middleware (added after CORS so they wrap inner handlers)
    # Starlette middleware runs in reverse registration order, so
    # RequestIdMiddleware is registered last to execute first.
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # Exception handlers
    register_exception_handlers(app)
    
    # Routes
    register_routes(app)
    
    return app


def register_exception_handlers(app: FastAPI) -> None:
    """Enregistre les handlers d'exceptions personnalisés."""
    
    @app.exception_handler(VMAutomationError)
    async def vmautomation_error_handler(
        request: Request, exc: VMAutomationError
    ) -> JSONResponse:
        """Handler pour les erreurs métier."""
        logger.warning(
            "business_error",
            error_code=exc.code,
            error_message=exc.message,
            path=str(request.url),
        )
        
        # Mapping des codes d'erreur vers les status HTTP
        status_codes: dict[str, int] = {
            "NOT_FOUND": status.HTTP_404_NOT_FOUND,
            "ALREADY_EXISTS": status.HTTP_409_CONFLICT,
            "VALIDATION_ERROR": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "AUTH_ERROR": status.HTTP_401_UNAUTHORIZED,
            "AUTHZ_ERROR": status.HTTP_403_FORBIDDEN,
            "TOKEN_EXPIRED": status.HTTP_401_UNAUTHORIZED,
            "INVALID_TOKEN": status.HTTP_401_UNAUTHORIZED,
            "RESOURCE_BUSY": status.HTTP_423_LOCKED,
        }
        
        http_status = status_codes.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return JSONResponse(
            status_code=http_status,
            content=exc.to_dict(),
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handler pour les erreurs de validation Pydantic."""
        errors = exc.errors()
        logger.warning(
            "validation_error",
            path=str(request.url),
            errors=errors,
        )
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": {"errors": errors},
            },
        )
    
    @app.exception_handler(Exception)
    async def generic_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handler pour les erreurs non gérées."""
        logger.error(
            "unhandled_error",
            error_type=type(exc).__name__,
            error_message=str(exc),
            path=str(request.url),
            exc_info=True,
        )
        
        # En production, ne pas exposer les détails
        if settings.app_env == "production":
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                },
            )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "INTERNAL_ERROR",
                "message": str(exc),
                "details": {"type": type(exc).__name__},
            },
        )


def register_routes(app: FastAPI) -> None:
    """Enregistre tous les routers."""
    
    # Health check (sans préfixe)
    app.include_router(health.router, tags=["Health"])
    
    # API v1
    api_prefix = "/api/v1"
    
    # Authentication (sans préfixe /auth car déjà dans le router)
    app.include_router(
        auth.router,
        prefix=api_prefix,
        tags=["Authentication"],
    )
    
    app.include_router(
        hypervisors.router,
        prefix=f"{api_prefix}/hypervisors",
        tags=["Hypervisors"],
    )
    
    app.include_router(
        vms.router,
        prefix=f"{api_prefix}/vms",
        tags=["Virtual Machines"],
    )
    
    app.include_router(
        templates.router,
        prefix=f"{api_prefix}/templates",
        tags=["OS Templates"],
    )
    
    app.include_router(
        deployments.router,
        prefix=f"{api_prefix}/deployments",
        tags=["Deployments"],
    )
    
    app.include_router(
        callbacks.router,
        prefix=f"{api_prefix}/callbacks",
        tags=["Callbacks"],
    )
    
    app.include_router(
        realtime.router,
        prefix=f"{api_prefix}/realtime",
        tags=["Realtime"],
    )
    
    app.include_router(
        software_catalog.router,
        prefix=f"{api_prefix}/software-catalog",
        tags=["Software Catalog"],
    )
    
    app.include_router(
        settings_router.router,
        prefix=f"{api_prefix}/settings",
        tags=["Settings"],
    )

    app.include_router(
        console.router,
        prefix=f"{api_prefix}/console",
        tags=["Console"],
    )

    app.include_router(
        terminal.router,
        prefix=f"{api_prefix}/terminal",
        tags=["Terminal"],
    )

    app.include_router(
        vnc.router,
        prefix=f"{api_prefix}/vnc",
        tags=["VNC"],
    )

    app.include_router(
        guacamole.router,
        prefix=f"{api_prefix}/guacamole",
        tags=["Guacamole"],
    )

    # Serve frontend static files (production build)
    frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        # Serve static assets (JS, CSS, images)
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="static-assets")

        # Serve other static files at root (favicon, etc.)
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            """Serve SPA - return index.html for all non-API routes."""
            file_path = frontend_dist / full_path
            if full_path and file_path.is_file():
                return FileResponse(str(file_path))
            return FileResponse(str(frontend_dist / "index.html"))


# Instance de l'application
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
