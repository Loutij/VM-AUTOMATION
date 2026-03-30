# =============================================================================
# VM Automation - Settings Router
# =============================================================================
"""
Endpoints pour la gestion des paramètres de l'application.
"""

from pydantic import BaseModel, Field, EmailStr
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import CurrentUser, RequireAdmin, get_db
from src.common.config import settings
from src.common.email import email_service
from src.common.logging import get_logger
from src.domain.user_model import User

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================


class SMTPConfig(BaseModel):
    """Configuration SMTP."""
    host: str = Field(..., description="Serveur SMTP")
    port: int = Field(..., ge=1, le=65535, description="Port SMTP")
    use_ssl: bool = Field(default=True, description="Utiliser SSL")
    user: str = Field(default="", description="Utilisateur SMTP")
    password: str = Field(default="", description="Mot de passe SMTP")
    from_addr: str = Field(default="", description="Adresse d'expédition")
    enabled: bool = Field(default=False, description="Activer les notifications")


class SMTPConfigResponse(BaseModel):
    """Réponse configuration SMTP (sans mot de passe)."""
    host: str
    port: int
    use_ssl: bool
    user: str
    from_addr: str
    enabled: bool


class TestEmailRequest(BaseModel):
    """Requête pour envoyer un email de test."""
    email: EmailStr = Field(..., description="Adresse email de test")


class TestEmailResponse(BaseModel):
    """Réponse de test email."""
    success: bool
    message: str


class AppSettingsResponse(BaseModel):
    """Paramètres généraux de l'application."""
    app_name: str
    app_env: str
    debug: bool
    smtp_enabled: bool
    ad_enabled: bool
    max_concurrent_deployments: int


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=AppSettingsResponse,
    summary="Obtenir les paramètres",
    description="Retourne les paramètres généraux de l'application.",
)
async def get_settings(current_user: CurrentUser) -> AppSettingsResponse:
    """Récupère les paramètres de l'application."""
    return AppSettingsResponse(
        app_name=settings.app_name,
        app_env=settings.app_env,
        debug=settings.debug,
        smtp_enabled=settings.smtp_enabled,
        ad_enabled=settings.ad_enabled,
        max_concurrent_deployments=settings.max_concurrent_deployments,
    )


@router.get(
    "/smtp",
    response_model=SMTPConfigResponse,
    summary="Obtenir la configuration SMTP",
    description="Retourne la configuration SMTP actuelle (sans le mot de passe).",
)
async def get_smtp_config(current_user: RequireAdmin) -> SMTPConfigResponse:
    """Récupère la configuration SMTP."""
    return SMTPConfigResponse(
        host=settings.smtp_host,
        port=settings.smtp_port,
        use_ssl=settings.smtp_ssl,
        user=settings.smtp_user,
        from_addr=settings.smtp_from or settings.smtp_user,
        enabled=settings.smtp_enabled,
    )


@router.post(
    "/smtp/test",
    response_model=TestEmailResponse,
    summary="Tester la configuration SMTP",
    description="Envoie un email de test pour vérifier la configuration SMTP.",
)
async def test_smtp(request: TestEmailRequest, current_user: RequireAdmin) -> TestEmailResponse:
    """Envoie un email de test."""
    logger.info("testing_smtp", email=request.email)
    
    # Vérifier que SMTP est configuré
    if not settings.smtp_host or not settings.smtp_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La configuration SMTP n'est pas complète. Veuillez configurer les variables SMTP_HOST et SMTP_USER.",
        )
    
    try:
        success = email_service.send_test_email(request.email)
        
        if success:
            return TestEmailResponse(
                success=True,
                message=f"Email de test envoyé avec succès à {request.email}",
            )
        else:
            return TestEmailResponse(
                success=False,
                message="L'envoi a échoué. Vérifiez les logs pour plus de détails.",
            )
    except Exception as e:
        logger.error("smtp_test_failed", email=request.email, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'envoi: {str(e)}",
        )


@router.post(
    "/smtp/test-me",
    response_model=TestEmailResponse,
    summary="Tester la configuration SMTP (envoi à mon email)",
    description="Envoie un email de test à l'adresse email du compte connecté.",
)
async def test_smtp_me(
    current_user: RequireAdmin,
    db: AsyncSession = Depends(get_db),
) -> TestEmailResponse:
    """Envoie un email de test à l'utilisateur connecté."""
    # Récupérer l'email du user depuis la DB
    result = await db.execute(select(User).where(User.id == current_user["user_id"]))
    user = result.scalar_one_or_none()

    if not user or not user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de récupérer votre adresse email.",
        )

    if not settings.smtp_host or not settings.smtp_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La configuration SMTP n'est pas complète.",
        )

    logger.info("testing_smtp_me", email=user.email, user_id=current_user["user_id"])

    try:
        success = email_service.send_test_email(user.email)
        if success:
            return TestEmailResponse(
                success=True,
                message=f"Email de test envoyé à {user.email}",
            )
        return TestEmailResponse(
            success=False,
            message="L'envoi a échoué. Vérifiez les logs pour plus de détails.",
        )
    except Exception as e:
        logger.error("smtp_test_me_failed", email=user.email, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'envoi: {str(e)}",
        )
