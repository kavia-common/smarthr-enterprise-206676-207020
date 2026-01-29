from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    postgres_url: str

    jwt_secret_key: str
    jwt_algorithm: str
    access_token_ttl_minutes: int
    refresh_token_ttl_minutes: int

    cors_allow_origins: list[str]


# PUBLIC_INTERFACE
def get_settings() -> Settings:
    """Load and return application Settings from environment variables.

    Required env vars:
      - POSTGRES_URL
      - JWT_SECRET_KEY

    Optional env vars:
      - JWT_ALGORITHM (default: HS256)
      - ACCESS_TOKEN_TTL_MINUTES (default: 30)
      - REFRESH_TOKEN_TTL_MINUTES (default: 43200 (30 days))
      - CORS_ALLOW_ORIGINS (default: "*")
    """
    postgres_url = os.getenv("POSTGRES_URL", "").strip()
    if not postgres_url:
        raise RuntimeError("Missing required env var POSTGRES_URL")

    jwt_secret_key = os.getenv("JWT_SECRET_KEY", "").strip()
    if not jwt_secret_key:
        raise RuntimeError("Missing required env var JWT_SECRET_KEY")

    jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256").strip() or "HS256"

    def _int_env(name: str, default: int) -> int:
        raw = os.getenv(name, "").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError as exc:
            raise RuntimeError(f"Invalid int env var {name}={raw!r}") from exc

    access_ttl = _int_env("ACCESS_TOKEN_TTL_MINUTES", 30)
    refresh_ttl = _int_env("REFRESH_TOKEN_TTL_MINUTES", 60 * 24 * 30)

    origins_raw = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
    if origins_raw == "*":
        origins = ["*"]
    else:
        origins = [o.strip() for o in origins_raw.split(",") if o.strip()]

    return Settings(
        postgres_url=postgres_url,
        jwt_secret_key=jwt_secret_key,
        jwt_algorithm=jwt_algorithm,
        access_token_ttl_minutes=access_ttl,
        refresh_token_ttl_minutes=refresh_ttl,
        cors_allow_origins=origins,
    )
