# =============================================================================
# VM Automation - JWT Authentication
# =============================================================================
"""
Module d'authentification JWT.
Gère la création et validation des tokens JWT.
"""

import time
import uuid
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
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1 heure
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
    jti: str = ""  # JWT ID for token revocation


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
    try:
        # Tronquer à 72 bytes (limite bcrypt) pour cohérence avec hash_password
        password_bytes = plain_password.encode('utf-8')[:MAX_PASSWORD_BYTES]
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


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
    username: str = "",
    role: str = "user",
    expires_delta: timedelta | None = None,
) -> str:
    """
    Crée un token d'accès JWT.

    Args:
        user_id: ID de l'utilisateur
        username: Nom d'utilisateur
        role: Rôle de l'utilisateur (admin/user)
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
        "username": username,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
        "jti": str(uuid.uuid4()),
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
        "jti": str(uuid.uuid4()),
    }

    return jwt.encode(payload, settings.api_secret_key.get_secret_value(), algorithm=ALGORITHM)


def create_tokens(user_id: str, username: str = "", role: str = "user") -> Token:
    """
    Crée une paire de tokens (access + refresh).

    Args:
        user_id: ID de l'utilisateur
        username: Nom d'utilisateur
        role: Rôle de l'utilisateur

    Returns:
        Token avec access_token et refresh_token
    """
    return Token(
        access_token=create_access_token(user_id, username=username, role=role),
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
            jti=payload.get("jti", ""),
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


# =============================================================================
# Token Blacklist (Redis-backed with in-memory fallback)
# =============================================================================

_redis_client = None


async def _get_redis():
    """Get or create a Redis client for token blacklisting."""
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis
            _redis_client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
            # Test connectivity
            await _redis_client.ping()
        except Exception:
            _redis_client = None
    return _redis_client


# In-memory fallback when Redis is unavailable
_blacklisted_tokens: dict[str, float] = {}  # jti -> expiry timestamp


def _cleanup_expired_tokens() -> None:
    """Remove expired entries from the in-memory blacklist."""
    now = time.time()
    expired = [jti for jti, exp in _blacklisted_tokens.items() if now > exp]
    for jti in expired:
        del _blacklisted_tokens[jti]


async def blacklist_token(token_jti: str, expires_in: int) -> None:
    """
    Add a token JTI to the blacklist until it naturally expires.

    Uses Redis if available, falls back to in-memory dict.

    Args:
        token_jti: The JWT ID to blacklist
        expires_in: Seconds until the token naturally expires
    """
    if not token_jti:
        return

    r = await _get_redis()
    if r is not None:
        try:
            await r.setex(f"blacklist:{token_jti}", expires_in, "1")
            return
        except Exception:
            pass

    # Fallback: in-memory
    _blacklisted_tokens[token_jti] = time.time() + expires_in
    _cleanup_expired_tokens()


async def is_token_blacklisted(token_jti: str) -> bool:
    """
    Check if a token JTI has been blacklisted.

    Args:
        token_jti: The JWT ID to check

    Returns:
        True if the token is blacklisted
    """
    if not token_jti:
        return False

    r = await _get_redis()
    if r is not None:
        try:
            return await r.exists(f"blacklist:{token_jti}") > 0
        except Exception:
            pass

    # Fallback: in-memory
    exp = _blacklisted_tokens.get(token_jti)
    if exp is None:
        return False
    if time.time() > exp:
        del _blacklisted_tokens[token_jti]
        return False
    return True


# =============================================================================
# WebSocket Token Verification
# =============================================================================


async def verify_ws_token(token: str | None) -> dict | None:
    """
    Verify JWT token for WebSocket connections.

    Unlike HTTP endpoints that raise exceptions, this returns None on failure
    so the WebSocket handler can close the connection with a proper code.

    Args:
        token: JWT access token (from query parameter)

    Returns:
        User dict with user_id and token_type, or None if invalid
    """
    if not token:
        return None
    try:
        payload = decode_token(token, expected_type="access")
        # Check if token has been revoked
        if payload.jti and await is_token_blacklisted(payload.jti):
            return None
        return {"user_id": payload.sub, "token_type": payload.type}
    except (AuthenticationError, Exception):
        return None
