import os
from typing import List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _split_csv(value: Optional[str]) -> List[str]:
    """Split a CSV env var into a list of stripped strings."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _bool_env(name: str, default: bool = False) -> bool:
    """Parse boolean-ish env vars."""
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def create_app() -> FastAPI:
    """Create and configure the FastAPI app instance."""
    openapi_tags = [
        {"name": "Health", "description": "Service health and diagnostics endpoints."},
    ]

    app = FastAPI(
        title="SmartHR AI - Backend API",
        description="FastAPI backend for SmartHR AI (HRMS).",
        version="0.1.0",
        openapi_tags=openapi_tags,
    )

    # CORS configuration from env (supports multiple possible env var names present in .env).
    allowed_origins = (
        _split_csv(os.getenv("ALLOWED_ORIGINS"))
        or _split_csv(os.getenv("CORS_ALLOW_ORIGINS"))
        or _split_csv(os.getenv("CORS_ORIGINS"))
        or ["*"]
    )
    allowed_headers = _split_csv(os.getenv("ALLOWED_HEADERS")) or ["*"]
    allowed_methods = _split_csv(os.getenv("ALLOWED_METHODS")) or ["*"]
    cors_max_age = int(os.getenv("CORS_MAX_AGE", "3600"))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=allowed_methods,
        allow_headers=allowed_headers,
        max_age=cors_max_age,
    )

    @app.get(
        "/health",
        tags=["Health"],
        summary="Health check",
        description="Returns process liveness and (optionally) basic DB connectivity status.",
        operation_id="getHealth",
    )
    def health():
        """
        Health endpoint used by platform readiness checks.

        Returns:
            JSON payload with status and optional database connectivity details.
        """
        db_url = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
        check_db = _bool_env("HEALTHCHECK_DB", default=False)

        payload = {"status": "ok"}

        # Optional DB connectivity check that does not block readiness by default.
        if check_db and db_url:
            try:
                # Lazy import so app can still boot even if DB deps are missing/misconfigured.
                from sqlalchemy import text
                from sqlalchemy import create_engine

                engine = create_engine(db_url, pool_pre_ping=True)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                payload["database"] = {"status": "ok"}
            except Exception as exc:  # noqa: BLE001 - health endpoint must be resilient
                payload["database"] = {"status": "error", "detail": str(exc)}

        return payload

    return app


# Uvicorn will import `app` by default.
app = create_app()
