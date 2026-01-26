# =============================================================================
# VM Automation - Auth Router
# =============================================================================
"""
Routes d'authentification API.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.common.auth import (
    Token,
    UserAuth,
    create_tokens,
    hash_password,
    verify_access_token,
    verify_password,
    verify_refresh_token,
)
from src.common.exceptions import AuthenticationError
from src.domain.user_model import User

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Security scheme
security = HTTPBearer(auto_error=False)


# =============================================================================
# Schemas
# =============================================================================


class UserCreate(BaseModel):
    """Schéma pour créer un utilisateur."""

    username: str
    email: EmailStr
    password: str
    full_name: str | None = None


class UserResponse(BaseModel):
    """Schéma de réponse utilisateur."""

    id: str
    username: str
    email: str
    full_name: str | None
    is_active: bool
    is_superuser: bool
    created_at: datetime

    class Config:
        from_attributes = True


class RefreshTokenRequest(BaseModel):
    """Schéma pour rafraîchir un token."""

    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """Schéma pour changer de mot de passe."""

    current_password: str
    new_password: str


# =============================================================================
# Dependencies
# =============================================================================


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dépendance pour obtenir l'utilisateur courant à partir du token JWT.

    Args:
        credentials: Credentials HTTP Bearer
        db: Session de base de données

    Returns:
        Utilisateur authentifié

    Raises:
        HTTPException: Si non authentifié ou utilisateur inactif
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token d'authentification requis",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = verify_access_token(credentials.credentials)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    # Récupérer l'utilisateur
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouvé",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé",
        )

    return user


async def get_current_superuser(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Dépendance pour vérifier que l'utilisateur est superuser.

    Args:
        current_user: Utilisateur courant

    Returns:
        Utilisateur superuser

    Raises:
        HTTPException: Si l'utilisateur n'est pas superuser
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Droits administrateur requis",
        )
    return current_user


# =============================================================================
# Routes
# =============================================================================


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Enregistre un nouvel utilisateur.

    Args:
        user_data: Données du nouvel utilisateur
        db: Session de base de données

    Returns:
        Utilisateur créé
    """
    # Vérifier si username existe
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce nom d'utilisateur est déjà pris",
        )

    # Vérifier si email existe
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cet email est déjà utilisé",
        )

    # Créer l'utilisateur
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Authentifie un utilisateur et retourne les tokens JWT.

    Args:
        form_data: Credentials (username/password)
        db: Session de base de données

    Returns:
        Tokens d'accès et de rafraîchissement
    """
    # Récupérer l'utilisateur
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé",
        )

    # Mettre à jour last_login
    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    # Créer les tokens
    return create_tokens(str(user.id))


@router.post("/refresh", response_model=Token)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Rafraîchit les tokens avec un refresh token valide.

    Args:
        request: Refresh token
        db: Session de base de données

    Returns:
        Nouveaux tokens
    """
    try:
        user_id = verify_refresh_token(request.refresh_token)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e

    # Vérifier que l'utilisateur existe et est actif
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur invalide ou désactivé",
        )

    return create_tokens(str(user.id))


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Retourne les informations de l'utilisateur courant.

    Args:
        current_user: Utilisateur authentifié

    Returns:
        Informations utilisateur
    """
    return current_user


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Change le mot de passe de l'utilisateur courant.

    Args:
        request: Ancien et nouveau mot de passe
        current_user: Utilisateur authentifié
        db: Session de base de données

    Returns:
        Message de confirmation
    """
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mot de passe actuel incorrect",
        )

    current_user.hashed_password = hash_password(request.new_password)
    await db.commit()

    return {"message": "Mot de passe modifié avec succès"}


@router.post("/logout")
async def logout() -> dict:
    """
    Déconnexion (côté client, invalider le token).

    Note: Avec JWT stateless, la déconnexion se fait côté client
    en supprimant le token. Pour une vraie invalidation, il faudrait
    un système de blacklist (Redis).

    Returns:
        Message de confirmation
    """
    return {"message": "Déconnexion réussie"}
