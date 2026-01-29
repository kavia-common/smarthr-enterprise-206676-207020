from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


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
    """Persist an audit log entry to the database.

    We intentionally use a direct SQL INSERT to:
    - rely on database defaults (created_at)
    - avoid ORM model mismatches if the schema evolves
    """
    db.execute(
        text(
            """
            INSERT INTO audit_logs (
              id, org_id, actor_user_id, actor_employee_id, action, entity_type, entity_id,
              ip, user_agent, metadata, created_at
            )
            VALUES (
              gen_random_uuid(), :org_id, :actor_user_id, :actor_employee_id, :action, :entity_type, :entity_id,
              :ip, :user_agent, :metadata, :created_at
            )
            """
        ),
        {
            "org_id": str(org_id) if org_id else None,
            "actor_user_id": str(actor_user_id) if actor_user_id else None,
            "actor_employee_id": str(actor_employee_id) if actor_employee_id else None,
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id else None,
            "ip": ip,
            "user_agent": user_agent,
            "metadata": metadata or {},
            "created_at": datetime.now(tz=timezone.utc),
        },
    )
    db.commit()
