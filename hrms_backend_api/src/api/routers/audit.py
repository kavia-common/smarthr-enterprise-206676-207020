from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.db import get_db
from src.deps.auth import Principal, require_permissions
from src.schemas.common import AuditLogOut

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get(
    "/logs",
    response_model=list[AuditLogOut],
    summary="List audit logs",
    description="Lists recent audit logs for the org. Requires employee.read (or future audit.read).",
    operation_id="audit_list_logs",
)
def list_audit_logs(
    limit: int = 200,
    principal: Principal = Depends(require_permissions(["employee.read"])),
    db: Session = Depends(get_db),
) -> list[AuditLogOut]:
    """List audit logs for current org."""
    rows = db.execute(
        text(
            """
            SELECT id, org_id, actor_user_id, actor_employee_id, action, entity_type, entity_id, ip, user_agent, metadata, created_at
            FROM audit_logs
            WHERE org_id = :org_id
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"org_id": str(principal.org_id), "limit": limit},
    ).fetchall()

    return [
        AuditLogOut(
            id=r[0],
            org_id=r[1],
            actor_user_id=r[2],
            actor_employee_id=r[3],
            action=r[4],
            entity_type=r[5],
            entity_id=r[6],
            ip=str(r[7]) if r[7] is not None else None,
            user_agent=r[8],
            metadata=r[9] or {},
            created_at=r[10],
        )
        for r in rows
    ]
