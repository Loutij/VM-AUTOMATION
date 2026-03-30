# =============================================================================
# VM Automation - Password Encryption (Fernet)
# =============================================================================
"""
Chiffrement / déchiffrement des mots de passe hyperviseurs avec Fernet.
La clé est lue depuis settings.encryption_key.
"""

from cryptography.fernet import Fernet, InvalidToken

from src.common.config import settings


def _get_fernet() -> Fernet:
    """Retourne une instance Fernet initialisée avec la clé de configuration."""
    key = settings.encryption_key
    if not key:
        raise RuntimeError(
            "encryption_key n'est pas configurée. "
            "Définissez ENCRYPTION_KEY dans votre fichier .env."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_password(plain: str) -> str:
    """
    Chiffre un mot de passe en clair avec Fernet.

    Args:
        plain: Mot de passe en clair.

    Returns:
        Mot de passe chiffré (base64 url-safe).
    """
    f = _get_fernet()
    return f.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_password(encrypted: str) -> str:
    """
    Déchiffre un mot de passe chiffré avec Fernet.

    Si la valeur n'est pas un token Fernet valide (ancien mot de passe
    stocké en clair avant la migration), elle est retournée telle quelle.

    Args:
        encrypted: Mot de passe chiffré (ou en clair pour rétro-compatibilité).

    Returns:
        Mot de passe en clair.
    """
    f = _get_fernet()
    try:
        return f.decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        # Rétro-compatibilité : le mot de passe n'était pas encore chiffré
        return encrypted
