from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from src.core.config import get_settings

settings = get_settings()


# PUBLIC_INTERFACE
def create_access_token(*, subject: str, org_id: str, claims: dict[str, Any] | None = None) -> str:
    """Create a signed JWT access token.

    Args:
        subject: User ID (UUID as string).
        org_id: Organization ID (UUID as string).
        claims: Additional claims (e.g., roles, permissions).

    Returns:
        Encoded JWT string.
    """
    to_encode: dict[str, Any] = {
        "sub": subject,
        "org_id": org_id,
        "type": "access",
        "iat": int(datetime.now(tz=timezone.utc).timestamp()),
        "exp": int((datetime.now(tz=timezone.utc) + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
    }
    if claims:
        to_encode.update(claims)
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# PUBLIC_INTERFACE
def create_refresh_token(*, subject: str, org_id: str) -> str:
    """Create a signed JWT refresh token."""
    to_encode: dict[str, Any] = {
        "sub": subject,
        "org_id": org_id,
        "type": "refresh",
        "iat": int(datetime.now(tz=timezone.utc).timestamp()),
        "exp": int((datetime.now(tz=timezone.utc) + timedelta(minutes=settings.refresh_token_ttl_minutes)).timestamp()),
    }
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# PUBLIC_INTERFACE
def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token.

    Raises:
        jose.JWTError if invalid/expired.
    """
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


# PUBLIC_INTERFACE
def assert_token_type(payload: dict[str, Any], token_type: str) -> None:
    """Validate token payload contains a specific 'type'."""
    if payload.get("type") != token_type:
        raise JWTError(f"Invalid token type; expected {token_type!r}")
