# =============================================================================
# VM Automation - Auth Module Tests
# =============================================================================
"""
Tests for src/common/auth.py:
  - Password hashing / verification
  - JWT token creation / validation / expiration
"""

from datetime import timedelta

import pytest

from src.common.auth import (
    MAX_PASSWORD_BYTES,
    create_access_token,
    create_refresh_token,
    create_tokens,
    decode_token,
    hash_password,
    verify_access_token,
    verify_password,
    verify_refresh_token,
)
from src.common.exceptions import AuthenticationError


# =============================================================================
# Password hashing
# =============================================================================


class TestPasswordHashing:
    """Tests for hash_password / verify_password."""

    def test_hash_and_verify(self):
        password = "MyP@ssw0rd!"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_wrong_password_rejected(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_hash_is_not_plaintext(self):
        password = "secret"
        hashed = hash_password(password)
        assert hashed != password
        assert hashed.startswith("$2")  # bcrypt prefix

    def test_same_password_different_hashes(self):
        password = "repeat"
        h1 = hash_password(password)
        h2 = hash_password(password)
        assert h1 != h2  # different salts
        assert verify_password(password, h1) is True
        assert verify_password(password, h2) is True

    def test_long_password_truncated_at_72_bytes(self):
        """bcrypt silently truncates at 72 bytes; our code does the same."""
        base = "A" * 80  # > 72 bytes
        hashed = hash_password(base)
        # Should still verify because both sides truncate
        assert verify_password(base, hashed) is True
        # A string sharing the first 72 bytes should also match
        assert verify_password(base[:MAX_PASSWORD_BYTES], hashed) is True

    def test_unicode_password(self):
        password = "m\u00f6tp@sse\u00e9"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_empty_password(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("notempty", hashed) is False

    def test_verify_with_invalid_hash_returns_false(self):
        assert verify_password("any", "not-a-bcrypt-hash") is False


# =============================================================================
# JWT token creation
# =============================================================================


class TestTokenCreation:
    """Tests for create_access_token / create_refresh_token / create_tokens."""

    def test_create_access_token_returns_string(self):
        token = create_access_token("user-123")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token_returns_string(self):
        token = create_refresh_token("user-123")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_tokens_returns_pair(self):
        tokens = create_tokens("user-123")
        assert tokens.access_token
        assert tokens.refresh_token
        assert tokens.token_type == "bearer"
        assert tokens.expires_in > 0

    def test_access_token_custom_expiry(self):
        token = create_access_token("user-123", expires_delta=timedelta(minutes=5))
        payload = decode_token(token, expected_type="access")
        assert payload.sub == "user-123"


# =============================================================================
# JWT token validation
# =============================================================================


class TestTokenValidation:
    """Tests for decode_token / verify_access_token / verify_refresh_token."""

    def test_decode_access_token(self):
        token = create_access_token("user-42")
        payload = decode_token(token, expected_type="access")
        assert payload.sub == "user-42"
        assert payload.type == "access"

    def test_decode_refresh_token(self):
        token = create_refresh_token("user-42")
        payload = decode_token(token, expected_type="refresh")
        assert payload.sub == "user-42"
        assert payload.type == "refresh"

    def test_verify_access_token_returns_user_id(self):
        token = create_access_token("uid-99")
        assert verify_access_token(token) == "uid-99"

    def test_verify_refresh_token_returns_user_id(self):
        token = create_refresh_token("uid-99")
        assert verify_refresh_token(token) == "uid-99"

    def test_wrong_token_type_rejected(self):
        """Using a refresh token where an access token is expected should fail."""
        refresh = create_refresh_token("user-1")
        with pytest.raises(AuthenticationError, match="Type de token invalide"):
            decode_token(refresh, expected_type="access")

    def test_access_token_as_refresh_rejected(self):
        access = create_access_token("user-1")
        with pytest.raises(AuthenticationError, match="Type de token invalide"):
            decode_token(access, expected_type="refresh")


# =============================================================================
# Token expiration
# =============================================================================


class TestTokenExpiration:
    """Tests for expired and tampered tokens."""

    def test_expired_token_rejected(self):
        token = create_access_token("user-1", expires_delta=timedelta(seconds=-1))
        with pytest.raises(AuthenticationError, match="Token invalide"):
            decode_token(token, expected_type="access")

    def test_expired_verify_access_token(self):
        token = create_access_token("user-1", expires_delta=timedelta(seconds=-1))
        with pytest.raises(AuthenticationError):
            verify_access_token(token)


# =============================================================================
# Invalid tokens
# =============================================================================


class TestInvalidTokens:
    """Tests for garbage / tampered tokens."""

    def test_garbage_token(self):
        with pytest.raises(AuthenticationError, match="Token invalide"):
            decode_token("not.a.jwt", expected_type="access")

    def test_empty_string_token(self):
        with pytest.raises(AuthenticationError):
            decode_token("", expected_type="access")

    def test_tampered_payload(self):
        """Changing a character in the payload should invalidate the signature."""
        token = create_access_token("user-1")
        parts = token.split(".")
        # Flip a char in the payload
        payload = list(parts[1])
        payload[0] = "A" if payload[0] != "A" else "B"
        tampered = f"{parts[0]}.{''.join(payload)}.{parts[2]}"
        with pytest.raises(AuthenticationError):
            decode_token(tampered, expected_type="access")
