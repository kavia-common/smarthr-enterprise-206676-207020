import os
from datetime import date, timedelta
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


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


# -----------------------------
# Demo in-memory "auth database"
# -----------------------------
# NOTE: This is intentionally simple so the system boots without a DB.
# It enables the existing frontend signin + dashboard UX.
_DEMO_USERS: Dict[str, Dict[str, object]] = {
    "admin@demo.local": {
        "password": "admin123",
        "roles": ["admin"],
        "user_id": "usr_demo_admin",
        "org_id": "org_demo",
        "employee_id": "emp_demo_admin",
    },
    "hr@demo.local": {
        "password": "hr123",
        "roles": ["hr"],
        "user_id": "usr_demo_hr",
        "org_id": "org_demo",
        "employee_id": "emp_demo_hr",
    },
    "manager@demo.local": {
        "password": "manager123",
        "roles": ["manager"],
        "user_id": "usr_demo_manager",
        "org_id": "org_demo",
        "employee_id": "emp_demo_manager",
    },
    "employee@demo.local": {
        "password": "employee123",
        "roles": ["employee"],
        "user_id": "usr_demo_employee",
        "org_id": "org_demo",
        "employee_id": "emp_demo_employee",
    },
}

# Very small "token" mechanism: token is literally "demo:<email>"
_TOKEN_PREFIX = "demo:"


def _issue_token(email: str) -> str:
    return f"{_TOKEN_PREFIX}{email}"


def _email_from_token(token: str) -> Optional[str]:
    if not token.startswith(_TOKEN_PREFIX):
        return None
    return token[len(_TOKEN_PREFIX) :]


def _parse_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _get_current_user(authorization: Optional[str]) -> Dict[str, object]:
    token = _parse_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    email = _email_from_token(token)
    if not email or email not in _DEMO_USERS:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = _DEMO_USERS[email]
    return {"email": email, **user, "token": token}


def create_app() -> FastAPI:
    """Create and configure the FastAPI app instance."""
    openapi_tags = [
        {"name": "Health", "description": "Service health and diagnostics endpoints."},
        {"name": "Auth", "description": "Authentication endpoints used by the web app."},
        {"name": "HRMS", "description": "Minimal HRMS endpoints required by the dashboard UI."},
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

    def _health_payload():
        """Build a resilient health payload, with optional DB connectivity status."""
        db_url = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
        check_db = _bool_env("HEALTHCHECK_DB", default=False)

        payload = {"status": "ok"}

        # Optional DB connectivity check that does not block readiness by default.
        if check_db and db_url:
            try:
                # Lazy import so app can still boot even if DB deps are missing/misconfigured.
                from sqlalchemy import create_engine, text

                engine = create_engine(db_url, pool_pre_ping=True)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                payload["database"] = {"status": "ok"}
            except Exception as exc:  # noqa: BLE001 - health endpoint must be resilient
                payload["database"] = {"status": "error", "detail": str(exc)}

        return payload

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
        return _health_payload()

    @app.get(
        "/healthz",
        tags=["Health"],
        summary="Health check (alias)",
        description="Alias for `/health` to match platforms that probe `/healthz` by convention.",
        operation_id="getHealthz",
    )
    def healthz():
        """
        Health endpoint alias for platform readiness checks.

        Returns:
            JSON payload with status and optional database connectivity details.
        """
        return _health_payload()

    # -----------------------------
    # Auth endpoints (used by UI)
    # -----------------------------

    class LoginRequest(BaseModel):
        org_slug: str = Field(..., description="Organization slug (demo uses 'demo').")
        email: str = Field(..., description="User email.")
        password: str = Field(..., description="User password.")

    class TokenPair(BaseModel):
        access_token: str = Field(..., description="Access token.")
        refresh_token: str = Field(..., description="Refresh token (demo placeholder).")
        token_type: str = Field("bearer", description="Token type.")

    @app.post(
        "/auth/login",
        tags=["Auth"],
        summary="Login",
        description="Demo login endpoint used by the frontend sign-in page.",
        operation_id="postAuthLogin",
        response_model=TokenPair,
    )
    def auth_login(payload: LoginRequest):
        """
        Authenticate a user and return an access/refresh token pair.

        This demo implementation uses in-memory users so the service works without DB.
        """
        if payload.org_slug.strip().lower() != "demo":
            raise HTTPException(status_code=400, detail="Unknown org")

        user = _DEMO_USERS.get(payload.email.lower())
        if not user or str(user["password"]) != payload.password:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        access = _issue_token(payload.email.lower())
        refresh = f"refresh:{access}"
        return TokenPair(access_token=access, refresh_token=refresh, token_type="bearer")

    class MeResponse(BaseModel):
        user_id: str = Field(..., description="User id.")
        org_id: str = Field(..., description="Org id.")
        roles: List[str] = Field(..., description="Role list.")
        permissions: List[str] = Field(default_factory=list, description="Permission list (demo).")
        employee_id: Optional[str] = Field(default=None, description="Employee id if applicable.")

    @app.get(
        "/auth/me",
        tags=["Auth"],
        summary="Current user",
        description="Return the current user context for the provided bearer token.",
        operation_id="getAuthMe",
        response_model=MeResponse,
    )
    def auth_me(authorization: Optional[str] = Header(default=None)):
        """Return user context for the logged-in user."""
        u = _get_current_user(authorization)
        return MeResponse(
            user_id=str(u["user_id"]),
            org_id=str(u["org_id"]),
            roles=[str(r) for r in (u["roles"] or [])],
            permissions=[],
            employee_id=str(u["employee_id"]) if u.get("employee_id") else None,
        )

    # -----------------------------
    # HRMS endpoints used by dashboard
    # -----------------------------

    class LeaveBalanceOut(BaseModel):
        leave_type_id: str = Field(..., description="Leave type id.")
        balance: float = Field(..., description="Remaining balance for the leave type.")

    @app.get(
        "/leaves/balances/me",
        tags=["HRMS"],
        summary="My leave balances",
        description="Return demo leave balances for current user.",
        operation_id="getMyLeaveBalances",
        response_model=List[LeaveBalanceOut],
    )
    def my_leave_balances(authorization: Optional[str] = Header(default=None)):
        """Return leave balances for the current user (demo)."""
        _get_current_user(authorization)
        return [
            LeaveBalanceOut(leave_type_id="annual", balance=12),
            LeaveBalanceOut(leave_type_id="sick", balance=6),
        ]

    class HolidayOut(BaseModel):
        id: str = Field(..., description="Holiday id.")
        org_id: str = Field(..., description="Org id.")
        calendar_id: str = Field(..., description="Calendar id.")
        holiday_date: str = Field(..., description="Date in YYYY-MM-DD.")
        name: str = Field(..., description="Holiday name.")
        type: str = Field("holiday", description="Type of entry.")

    @app.get(
        "/holidays",
        tags=["HRMS"],
        summary="List holidays",
        description="Return demo holiday list between start_date and end_date.",
        operation_id="listHolidays",
        response_model=List[HolidayOut],
    )
    def list_holidays(
        start_date: str,
        end_date: str,
        authorization: Optional[str] = Header(default=None),
    ):
        """List holidays in a date range (demo)."""
        u = _get_current_user(authorization)

        # Return a couple of deterministic demo holidays within the range window.
        today = date.today()
        items = [
            HolidayOut(
                id="hol_demo_1",
                org_id=str(u["org_id"]),
                calendar_id="cal_demo",
                holiday_date=(today + timedelta(days=7)).isoformat(),
                name="Demo Holiday",
                type="holiday",
            ),
            HolidayOut(
                id="hol_demo_2",
                org_id=str(u["org_id"]),
                calendar_id="cal_demo",
                holiday_date=(today + timedelta(days=30)).isoformat(),
                name="Demo Festival",
                type="holiday",
            ),
        ]
        # Keep filtering simple: frontend already sorts; just return the demo list.
        _ = start_date, end_date
        return items

    return app


# Uvicorn will import `app` by default.
app = create_app()
