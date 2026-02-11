"""Unit tests for core modules."""

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.validators import validate_password_strength


class TestPasswordHashing:
    """Tests for password hashing functions."""

    def test_hash_password(self):
        """Test password hashing produces valid bcrypt hash."""
        password = "TestPassword123!"
        hashed = hash_password(password)
        # bcrypt hashes can start with $2a$, $2b$, or $2y$
        assert hashed.startswith("$2")
        assert len(hashed) == 60

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "TestPassword123!"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "TestPassword123!"
        hashed = hash_password(password)
        assert verify_password("WrongPassword456!", hashed) is False


class TestTokens:
    """Tests for JWT token functions."""

    def test_create_access_token(self):
        """Test access token creation."""
        token, jti = create_access_token(subject=1)
        assert isinstance(token, str)
        assert isinstance(jti, str)
        assert len(token) > 0
        assert len(jti) == 36  # UUID format

    def test_create_refresh_token(self):
        """Test refresh token creation."""
        token, jti = create_refresh_token(subject=1)
        assert isinstance(token, str)
        assert isinstance(jti, str)
        assert len(token) > 0

    def test_decode_valid_token(self):
        """Test decoding a valid token."""
        token, _ = create_access_token(subject=123)
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "123"
        assert payload["type"] == "access"

    def test_decode_invalid_token(self):
        """Test decoding an invalid token returns None."""
        result = decode_token("invalid-token")
        assert result is None

    def test_decode_tampered_token(self):
        """Test decoding a tampered token returns None."""
        token, _ = create_access_token(subject=1)
        # Tamper with the token
        tampered = token[:-5] + "XXXXX"
        result = decode_token(tampered)
        assert result is None

    def test_access_token_has_correct_type(self):
        """Test access token has type 'access'."""
        token, _ = create_access_token(subject=1)
        payload = decode_token(token)
        assert payload["type"] == "access"

    def test_refresh_token_has_correct_type(self):
        """Test refresh token has type 'refresh'."""
        token, _ = create_refresh_token(subject=1)
        payload = decode_token(token)
        assert payload["type"] == "refresh"


class TestPasswordValidation:
    """Tests for password strength validation."""

    def test_valid_password(self):
        """Test valid password passes validation."""
        result = validate_password_strength("TestPassword123!")
        assert result == "TestPassword123!"

    def test_password_too_short(self):
        """Test password under 12 characters fails."""
        with pytest.raises(ValueError, match="at least 12 characters"):
            validate_password_strength("Short1!")

    def test_password_no_uppercase(self):
        """Test password without uppercase fails."""
        with pytest.raises(ValueError, match="uppercase"):
            validate_password_strength("testpassword123!")

    def test_password_no_lowercase(self):
        """Test password without lowercase fails."""
        with pytest.raises(ValueError, match="lowercase"):
            validate_password_strength("TESTPASSWORD123!")

    def test_password_no_digit(self):
        """Test password without digit fails."""
        with pytest.raises(ValueError, match="digit"):
            validate_password_strength("TestPasswordABC!")

    def test_password_no_special_char(self):
        """Test password without special character fails."""
        with pytest.raises(ValueError, match="special character"):
            validate_password_strength("TestPassword1234")


class TestSecurityConfig:
    """Tests for security configuration."""

    def test_secret_key_validation_too_short(self):
        """Test SECRET_KEY validation rejects short keys."""
        from pydantic import ValidationError

        from app.core.config import Settings

        with pytest.raises(ValidationError):
            Settings(SECRET_KEY="short")

    def test_secret_key_validation_insecure_default(self):
        """Test SECRET_KEY validation rejects insecure defaults."""
        from pydantic import ValidationError

        from app.core.config import Settings

        with pytest.raises(ValidationError):
            Settings(SECRET_KEY="your-super-secret-key-at-least-32-chars")


class TestSetupLogging:
    """Tests for logging configuration."""

    def test_setup_logging_runs(self):
        """Test setup_logging configures logging without error."""
        from app.core.config import setup_logging

        setup_logging()

    def test_setup_logging_sets_level(self):
        """Test setup_logging applies the configured log level."""
        import logging

        from app.core.config import setup_logging

        setup_logging()
        root_logger = logging.getLogger()
        assert root_logger.level is not None


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Test root endpoint returns project name."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "running" in data["message"]
