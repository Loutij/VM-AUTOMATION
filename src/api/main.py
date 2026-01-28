# =============================================================================
# VM Automation - FastAPI Application Entry Point
# =============================================================================
"""
Point d'entrée principal de l'API FastAPI.
Configure l'application, les middlewares, et les routes.
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.common.config import settings
from src.common.database import close_db, init_db
from src.common.exceptions import VMAutomationError
from src.common.logging import get_logger, setup_logging

# Routers
from src.api.routers import auth, callbacks, health, hypervisors, vms, deployments, templates, realtime, software_catalog, settings as settings_router

logger = get_logger(__name__)


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
    
    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
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
