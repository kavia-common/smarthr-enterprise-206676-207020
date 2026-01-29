from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from src.models.hrms import AuditLog


# PUBLIC_INTERFACE
def write_audit_log(
    db: Session,
    *,
    org_id: UUID | None,
    actor_user_id: UUID | None,
    actor_employee_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    ip: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist an audit log entry to the database."""
    log = AuditLog(
        org_id=org_id,
        actor_user_id=actor_user_id,
        actor_employee_id=actor_employee_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip=ip,
        user_agent=user_agent,
        metadata=metadata or {},
    )
    db.add(log)
    db.commit()
