# =============================================================================
# VM Automation - Auth Router
# =============================================================================
"""
Routes d'authentification API.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db, RequireAdmin
from src.common.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    Token,
    UserAuth,
    blacklist_token,
    create_tokens,
    decode_token,
    hash_password,
    is_token_blacklisted,
    verify_access_token,
    verify_password,
    verify_refresh_token,
)
from src.common.exceptions import AuthenticationError
from src.domain.models import UserRole
from src.domain.user_model import User

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Rate limiter for auth endpoints (10 requests/minute)
limiter = Limiter(key_func=get_remote_address)

# Security scheme
security = HTTPBearer(auto_error=False)


# =============================================================================
# Schemas
# =============================================================================


class UserCreate(BaseModel):
    """Schéma pour créer un utilisateur."""

    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", description="Nom d'utilisateur (alphanumérique, 3-50 caractères)")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128, description="Mot de passe (minimum 8 caractères)")
    full_name: str | None = None


class UserResponse(BaseModel):
    """Schéma de réponse utilisateur."""

    id: str
    username: str
    email: str
    full_name: str | None
    is_active: bool
    is_superuser: bool
    role: str
    created_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        """Convertit l'objet ORM en réponse avec id comme string."""
        return cls(
            id=str(obj.id),
            username=obj.username,
            email=obj.email,
            full_name=obj.full_name,
            is_active=obj.is_active,
            is_superuser=obj.is_superuser,
            role=obj.role.value if hasattr(obj.role, 'value') else obj.role,
            created_at=obj.created_at,
        )


class UserUpdate(BaseModel):
    """Schéma pour modifier un utilisateur (admin)."""

    full_name: str | None = None
    is_active: bool | None = None
    role: str | None = None


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
        payload = decode_token(credentials.credentials, expected_type="access")
        user_id = payload.sub

        # Check if token has been revoked (logout)
        if payload.jti and await is_token_blacklisted(payload.jti):
            raise AuthenticationError("Token has been revoked")
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
@limiter.limit("10/minute")
async def register(
    request: Request,
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
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

    return UserResponse.from_orm(user)


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(
    request: Request,
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

    # Créer les tokens avec username et rôle
    role = user.role.value if hasattr(user.role, 'value') else (user.role or "user")
    return create_tokens(str(user.id), username=user.username, role=role)


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

    role = user.role.value if hasattr(user.role, 'value') else (user.role or "user")
    return create_tokens(str(user.id), username=user.username, role=role)


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """
    Retourne les informations de l'utilisateur courant.

    Args:
        current_user: Utilisateur authentifié

    Returns:
        Informations utilisateur
    """
    return UserResponse.from_orm(current_user)


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
async def logout(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict:
    """
    Déconnexion - blackliste le token JWT courant.

    Le token est ajouté à la blacklist Redis (ou in-memory) pour la durée
    restante de sa validité, empêchant toute réutilisation.

    Returns:
        Message de confirmation
    """
    if credentials:
        try:
            payload = decode_token(credentials.credentials, expected_type="access")
            if payload.jti:
                # Calculate remaining lifetime in seconds
                remaining = int((payload.exp - datetime.now(timezone.utc)).total_seconds())
                if remaining > 0:
                    await blacklist_token(payload.jti, remaining)
        except AuthenticationError:
            pass  # Token already invalid, nothing to blacklist

    return {"message": "Déconnexion réussie"}


# =============================================================================
# Admin Routes - Gestion des utilisateurs
# =============================================================================


@router.get("/admin/users", response_model=list[UserResponse])
async def list_users(
    admin: RequireAdmin,
    db: AsyncSession = Depends(get_db),
) -> list[UserResponse]:
    """Liste tous les utilisateurs (admin uniquement)."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [UserResponse.from_orm(u) for u in users]


@router.get("/admin/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    admin: RequireAdmin,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Récupère un utilisateur par ID (admin uniquement)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )
    return UserResponse.from_orm(user)


@router.post("/admin/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    user_data: UserCreate,
    admin: RequireAdmin,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Crée un utilisateur (admin uniquement). Le rôle par défaut est 'user'."""
    # Vérifier unicité
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce nom d'utilisateur est déjà pris",
        )
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cet email est déjà utilisé",
        )

    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        role=UserRole.USER,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse.from_orm(user)


@router.patch("/admin/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    updates: UserUpdate,
    admin: RequireAdmin,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Met à jour un utilisateur (admin uniquement)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    if updates.full_name is not None:
        user.full_name = updates.full_name
    if updates.is_active is not None:
        user.is_active = updates.is_active
    if updates.role is not None:
        try:
            user.role = UserRole(updates.role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rôle invalide: {updates.role}. Valeurs acceptées: admin, user",
            )

    await db.commit()
    await db.refresh(user)
    return UserResponse.from_orm(user)


@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: str,
    admin: RequireAdmin,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Supprime un utilisateur (admin uniquement)."""
    # Empêcher l'auto-suppression
    if user_id == admin.get("user_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de supprimer votre propre compte",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    await db.delete(user)
    await db.commit()
    return {"message": f"Utilisateur '{user.username}' supprimé"}


class ResetPasswordRequest(BaseModel):
    """Schéma pour réinitialiser un mot de passe (admin)."""

    new_password: str


@router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_password(
    user_id: str,
    request: ResetPasswordRequest,
    admin: RequireAdmin,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Réinitialise le mot de passe d'un utilisateur (admin uniquement)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    new_password = request.new_password
    if not new_password or len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le mot de passe doit contenir au moins 8 caractères",
        )

    user.hashed_password = hash_password(new_password)
    await db.commit()
    return {"message": f"Mot de passe de '{user.username}' réinitialisé"}
