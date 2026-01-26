# =============================================================================
# VM Automation - FastAPI Dependencies
# =============================================================================
"""
Dépendances injectables pour FastAPI.
Inclut l'authentification, les sessions DB, et les services.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.config import settings
from src.common.database import get_db_session
from src.common.exceptions import InvalidTokenError, TokenExpiredError
from src.common.logging import get_logger

logger = get_logger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)


# =============================================================================
# Database Session
# =============================================================================

# Type alias pour injection de session DB
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


# =============================================================================
# Authentication
# =============================================================================


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(security)
    ] = None,
) -> dict:
    """
    Extrait et valide l'utilisateur depuis le token JWT.
    
    Returns:
        Dictionnaire avec les informations de l'utilisateur
        
    Raises:
        HTTPException: Si le token est invalide ou expiré
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    try:
        payload = jwt.decode(
            token,
            settings.api_secret_key.get_secret_value(),
            algorithms=[settings.api_algorithm],
        )
        
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise InvalidTokenError()
        
        return {
            "user_id": user_id,
            "username": payload.get("username", ""),
            "roles": payload.get("roles", []),
        }
        
    except jwt.ExpiredSignatureError:
        logger.warning("token_expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        logger.warning("invalid_token", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Type alias pour utilisateur authentifié
CurrentUser = Annotated[dict, Depends(get_current_user)]


async def get_optional_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(security)
    ] = None,
) -> dict | None:
    """
    Extrait l'utilisateur si un token est fourni, sinon retourne None.
    Utile pour les endpoints publics avec fonctionnalités optionnelles pour les utilisateurs connectés.
    """
    if credentials is None:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


OptionalUser = Annotated[dict | None, Depends(get_optional_user)]


def require_role(required_role: str):
    """
    Dependency factory pour vérifier qu'un utilisateur a un rôle spécifique.
    
    Usage:
        @router.post("/admin/action")
        async def admin_action(user: CurrentUser = Depends(require_role("admin"))):
            ...
    """
    async def role_checker(user: CurrentUser) -> dict:
        if required_role not in user.get("roles", []):
            logger.warning(
                "insufficient_permissions",
                user_id=user.get("user_id"),
                required_role=required_role,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required",
            )
        return user
    
    return role_checker


# =============================================================================
# Request Context
# =============================================================================


async def get_request_id(
    x_request_id: Annotated[str | None, Header()] = None,
) -> str:
    """
    Récupère ou génère un ID de requête pour le tracing.
    """
    import uuid
    return x_request_id or str(uuid.uuid4())


RequestId = Annotated[str, Depends(get_request_id)]


# =============================================================================
# Pagination
# =============================================================================


class PaginationParams:
    """Paramètres de pagination communs."""
    
    def __init__(
        self,
        page: int = 1,
        page_size: int = 20,
        max_page_size: int = 100,
    ) -> None:
        self.page = max(1, page)
        self.page_size = min(max(1, page_size), max_page_size)
        self.offset = (self.page - 1) * self.page_size


Pagination = Annotated[PaginationParams, Depends()]
