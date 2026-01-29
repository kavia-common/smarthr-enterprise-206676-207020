from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.db import get_db
from src.core.jwt import decode_token
from src.models.hrms import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@dataclass(frozen=True)
class Principal:
    """Authenticated principal extracted from JWT + database."""

    user_id: UUID
    org_id: UUID
    roles: list[str]
    permissions: list[str]
    employee_id: UUID | None


def _load_roles_and_permissions(db: Session, user_id: UUID) -> tuple[list[str], list[str]]:
    # Roles
    roles_rows = db.execute(
        text(
            """
            SELECT r.name
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = :user_id
            """
        ),
        {"user_id": str(user_id)},
    ).fetchall()
    roles = [r[0] for r in roles_rows]

    # Permissions derived from roles
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
        {"user_id": str(user_id)},
    ).fetchall()
    permissions = [p[0] for p in perm_rows]
    return roles, permissions


def _load_employee_id(db: Session, user_id: UUID) -> UUID | None:
    row = db.execute(
        text("SELECT id FROM employees WHERE user_id = :user_id LIMIT 1"),
        {"user_id": str(user_id)},
    ).fetchone()
    return UUID(row[0]) if row else None


# PUBLIC_INTERFACE
def get_current_principal(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Principal:
    """Resolve current authenticated principal from Bearer token."""
    try:
        payload: dict[str, Any] = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")

    sub = payload.get("sub")
    org_id = payload.get("org_id")
    if not sub or not org_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")

    user = db.get(User, UUID(sub))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or not found")

    roles, permissions = _load_roles_and_permissions(db, UUID(sub))
    employee_id = _load_employee_id(db, UUID(sub))

    return Principal(
        user_id=UUID(sub),
        org_id=UUID(org_id),
        roles=roles,
        permissions=permissions,
        employee_id=employee_id,
    )


# PUBLIC_INTERFACE
def require_permissions(required: list[str]):
    """Dependency factory that enforces permission checks."""
    def _checker(principal: Principal = Depends(get_current_principal)) -> Principal:
        missing = [p for p in required if p not in principal.permissions]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {', '.join(missing)}",
            )
        return principal

    return _checker
