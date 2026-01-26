# =============================================================================
# VM Automation - JWT Authentication
# =============================================================================
"""
Module d'authentification JWT.
Gère la création et validation des tokens JWT.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel

from src.common.config import settings
from src.common.exceptions import AuthenticationError

# =============================================================================
# Configuration
# =============================================================================

# Limite bcrypt
MAX_PASSWORD_BYTES = 72

# Configuration JWT
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 heures
REFRESH_TOKEN_EXPIRE_DAYS = 7


# =============================================================================
# Schemas
# =============================================================================


class Token(BaseModel):
    """Réponse d'authentification avec tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    """Contenu décodé d'un token JWT."""

    sub: str  # user_id
    exp: datetime
    iat: datetime
    type: str  # "access" ou "refresh"


class UserAuth(BaseModel):
    """Données d'authentification utilisateur."""

    id: str
    username: str
    email: str
    is_active: bool
    is_superuser: bool


# =============================================================================
# Password Functions
# =============================================================================


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Vérifie si un mot de passe correspond au hash.

    Args:
        plain_password: Mot de passe en clair
        hashed_password: Hash du mot de passe

    Returns:
        True si le mot de passe est correct
    """
    # Tronquer à 72 bytes (limite bcrypt) pour cohérence avec hash_password
    password_bytes = plain_password.encode('utf-8')[:MAX_PASSWORD_BYTES]
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def hash_password(password: str) -> str:
    """
    Hash un mot de passe avec bcrypt.

    Args:
        password: Mot de passe en clair

    Returns:
        Hash du mot de passe
    
    Note:
        bcrypt a une limite de 72 bytes. Les mots de passe plus longs sont tronqués.
    """
    # Tronquer à 72 bytes (limite bcrypt) pour éviter l'erreur
    password_bytes = password.encode('utf-8')[:MAX_PASSWORD_BYTES]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


# =============================================================================
# Token Functions
# =============================================================================


def create_access_token(
    user_id: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Crée un token d'accès JWT.

    Args:
        user_id: ID de l'utilisateur
        expires_delta: Durée de validité personnalisée

    Returns:
        Token JWT encodé
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    return jwt.encode(payload, settings.api_secret_key.get_secret_value(), algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """
    Crée un token de rafraîchissement JWT.

    Args:
        user_id: ID de l'utilisateur

    Returns:
        Token JWT encodé
    """
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }

    return jwt.encode(payload, settings.api_secret_key.get_secret_value(), algorithm=ALGORITHM)


def create_tokens(user_id: str) -> Token:
    """
    Crée une paire de tokens (access + refresh).

    Args:
        user_id: ID de l'utilisateur

    Returns:
        Token avec access_token et refresh_token
    """
    return Token(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # en secondes
    )


def decode_token(token: str, expected_type: str = "access") -> TokenPayload:
    """
    Décode et valide un token JWT.

    Args:
        token: Token JWT à décoder
        expected_type: Type de token attendu ("access" ou "refresh")

    Returns:
        Payload du token

    Raises:
        AuthenticationError: Si le token est invalide ou expiré
    """
    try:
        payload = jwt.decode(token, settings.api_secret_key.get_secret_value(), algorithms=[ALGORITHM])

        # Vérification du type
        token_type = payload.get("type")
        if token_type != expected_type:
            raise AuthenticationError(
                f"Type de token invalide: attendu {expected_type}, reçu {token_type}"
            )

        return TokenPayload(
            sub=payload["sub"],
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
            iat=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
            type=token_type,
        )

    except JWTError as e:
        raise AuthenticationError(f"Token invalide: {str(e)}") from e


def verify_access_token(token: str) -> str:
    """
    Vérifie un token d'accès et retourne l'ID utilisateur.

    Args:
        token: Token JWT à vérifier

    Returns:
        ID de l'utilisateur

    Raises:
        AuthenticationError: Si le token est invalide
    """
    payload = decode_token(token, expected_type="access")
    return payload.sub


def verify_refresh_token(token: str) -> str:
    """
    Vérifie un token de rafraîchissement et retourne l'ID utilisateur.

    Args:
        token: Token JWT à vérifier

    Returns:
        ID de l'utilisateur

    Raises:
        AuthenticationError: Si le token est invalide
    """
    payload = decode_token(token, expected_type="refresh")
    return payload.sub
