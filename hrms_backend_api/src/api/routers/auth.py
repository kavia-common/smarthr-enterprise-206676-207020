from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.db import get_db
from src.core.jwt import assert_token_type, create_access_token, create_refresh_token, decode_token
from src.core.security import verify_password
from src.deps.auth import Principal, get_current_principal
from src.schemas.auth import LoginRequest, MeResponse, RefreshRequest, TokenPair
from src.services.audit import write_audit_log

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Login and receive access/refresh tokens",
    description="Authenticates a user against the users table (org scoped) and returns JWT access/refresh tokens.",
    operation_id="auth_login",
)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenPair:
    """Authenticate a user and issue JWT tokens."""
    org_row = db.execute(
        text("SELECT id FROM organizations WHERE slug = :slug LIMIT 1"),
        {"slug": payload.org_slug},
    ).fetchone()
    if not org_row:
        raise HTTPException(status_code=400, detail="Invalid org")

    org_id = UUID(org_row[0])

    user_row = db.execute(
        text("SELECT id, password_hash, is_active FROM users WHERE org_id = :org_id AND lower(email) = lower(:email) LIMIT 1"),
        {"org_id": str(org_id), "email": payload.email},
    ).fetchone()

    if not user_row or not user_row[2]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user_id = UUID(user_row[0])
    password_hash = user_row[1]

    if not verify_password(payload.password, password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    db.execute(
        text("UPDATE users SET last_login_at = :now, updated_at = :now WHERE id = :id"),
        {"now": datetime.now(tz=timezone.utc), "id": str(user_id)},
    )
    db.commit()

    access = create_access_token(subject=str(user_id), org_id=str(org_id))
    refresh = create_refresh_token(subject=str(user_id), org_id=str(org_id))

    write_audit_log(
        db,
        org_id=org_id,
        actor_user_id=user_id,
        actor_employee_id=None,
        action="auth.login",
        entity_type="user",
        entity_id=user_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"email": payload.email},
    )

    return TokenPair(access_token=access, refresh_token=refresh)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Refresh tokens",
    description="Exchanges a refresh token for a new access/refresh pair.",
    operation_id="auth_refresh",
)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    """Refresh access/refresh tokens."""
    try:
        decoded = decode_token(payload.refresh_token)
        assert_token_type(decoded, "refresh")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = UUID(decoded["sub"])
    org_id = UUID(decoded["org_id"])

    user_row = db.execute(
        text("SELECT is_active FROM users WHERE id = :id AND org_id = :org_id LIMIT 1"),
        {"id": str(user_id), "org_id": str(org_id)},
    ).fetchone()
    if not user_row or not user_row[0]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or not found")

    access = create_access_token(subject=str(user_id), org_id=str(org_id))
    refresh_tok = create_refresh_token(subject=str(user_id), org_id=str(org_id))
    return TokenPair(access_token=access, refresh_token=refresh_tok)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get current user context",
    description="Returns the authenticated user's org, roles and permissions derived from RBAC tables.",
    operation_id="auth_me",
)
def me(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)) -> MeResponse:
    """Return authenticated context for frontend dashboards and RBAC."""
    # Reload roles/permissions via DB for accuracy
    roles_rows = db.execute(
        text(
            """
            SELECT r.name
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = :user_id
            """
        ),
        {"user_id": str(principal.user_id)},
    ).fetchall()
    roles = [r[0] for r in roles_rows]

    perm_rows = db.execute(
        text(
            """
            SELECT DISTINCT p.key
            FROM user_roles ur
            JOIN role_permissions rp ON rp.role_id = ur.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE ur.user_id = :user_id
            """
        ),
        {"user_id": str(principal.user_id)},
    ).fetchall()
    permissions = [p[0] for p in perm_rows]

    return MeResponse(
        user_id=principal.user_id,
        org_id=principal.org_id,
        roles=roles,
        permissions=permissions,
        employee_id=principal.employee_id,
    )
