from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.db import get_db
from src.deps.auth import Principal, require_permissions
from src.schemas.hrms import LeaveApplyRequest, LeaveBalanceOut, LeaveDecisionRequest, LeaveRequestOut
from src.services.audit import write_audit_log

router = APIRouter(prefix="/leaves", tags=["Leaves"])


def _require_employee(principal: Principal) -> UUID:
    if not principal.employee_id:
        raise HTTPException(status_code=400, detail="User has no employee mapping")
    return principal.employee_id


@router.post(
    "/requests",
    response_model=LeaveRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Apply for leave (current user)",
    description="Creates a leave request for the authenticated employee. Requires leave.apply.",
    operation_id="leave_apply",
)
def apply_leave(
    payload: LeaveApplyRequest,
    request: Request,
    principal: Principal = Depends(require_permissions(["leave.apply"])),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    """Apply for leave."""
    employee_id = _require_employee(principal)
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="Invalid date range")

    leave_type = db.execute(
        text("SELECT requires_approval FROM leave_types WHERE org_id = :org_id AND id = :id"),
        {"org_id": str(principal.org_id), "id": str(payload.leave_type_id)},
    ).fetchone()
    if not leave_type:
        raise HTTPException(status_code=400, detail="Invalid leave type")

    requires_approval = bool(leave_type[0])
    status_value = "pending" if requires_approval else "approved"

    lr_id = UUID(db.execute(text("SELECT gen_random_uuid()")).scalar_one())
    now = datetime.now(tz=timezone.utc)

    row = db.execute(
        text(
            """
            INSERT INTO leave_requests (
              id, org_id, employee_id, leave_type_id, start_date, end_date, unit, quantity, reason, status,
              requested_at, decided_at, created_at, updated_at
            )
            VALUES (
              :id, :org_id, :employee_id, :leave_type_id, :start_date, :end_date, :unit, :quantity, :reason, :status,
              :now, :decided_at, :now, :now
            )
            RETURNING id, org_id, employee_id, leave_type_id, start_date, end_date, unit, quantity, reason, status, requested_at, decided_at, created_at, updated_at
            """
        ),
        {
            "id": str(lr_id),
            "org_id": str(principal.org_id),
            "employee_id": str(employee_id),
            "leave_type_id": str(payload.leave_type_id),
            "start_date": payload.start_date,
            "end_date": payload.end_date,
            "unit": payload.unit,
            "quantity": payload.quantity,
            "reason": payload.reason,
            "status": status_value,
            "now": now,
            "decided_at": now if status_value == "approved" else None,
        },
    ).fetchone()
    db.commit()

    write_audit_log(
        db,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        actor_employee_id=employee_id,
        action="leave.apply",
        entity_type="leave_request",
        entity_id=lr_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"status": status_value, "leave_type_id": str(payload.leave_type_id)},
    )

    return LeaveRequestOut(
        id=row[0],
        org_id=row[1],
        employee_id=row[2],
        leave_type_id=row[3],
        start_date=row[4],
        end_date=row[5],
        unit=row[6],
        quantity=float(row[7]),
        reason=row[8],
        status=row[9],
        requested_at=row[10],
        decided_at=row[11],
        created_at=row[12],
        updated_at=row[13],
    )


@router.get(
    "/requests",
    response_model=list[LeaveRequestOut],
    summary="List leave requests (org)",
    description="List leave requests in org. Requires leave.read.",
    operation_id="leave_list_requests",
)
def list_leave_requests(
    status_filter: str | None = None,
    employee_id: UUID | None = None,
    principal: Principal = Depends(require_permissions(["leave.read"])),
    db: Session = Depends(get_db),
) -> list[LeaveRequestOut]:
    """List leave requests by filter."""
    clauses = ["org_id = :org_id"]
    params: dict[str, object] = {"org_id": str(principal.org_id)}
    if status_filter:
        clauses.append("status = :status")
        params["status"] = status_filter
    if employee_id:
        clauses.append("employee_id = :employee_id")
        params["employee_id"] = str(employee_id)

    where_sql = " AND ".join(clauses)
    rows = db.execute(
        text(
            f"""
            SELECT id, org_id, employee_id, leave_type_id, start_date, end_date, unit, quantity, reason, status,
                   requested_at, decided_at, created_at, updated_at
            FROM leave_requests
            WHERE {where_sql}
            ORDER BY requested_at DESC
            LIMIT 500
            """
        ),
        params,
    ).fetchall()

    return [
        LeaveRequestOut(
            id=r[0],
            org_id=r[1],
            employee_id=r[2],
            leave_type_id=r[3],
            start_date=r[4],
            end_date=r[5],
            unit=r[6],
            quantity=float(r[7]),
            reason=r[8],
            status=r[9],
            requested_at=r[10],
            decided_at=r[11],
            created_at=r[12],
            updated_at=r[13],
        )
        for r in rows
    ]


@router.post(
    "/requests/{leave_request_id}/decision",
    response_model=LeaveRequestOut,
    summary="Approve or reject a leave request",
    description="Approves/rejects a leave request. Requires leave.approve.",
    operation_id="leave_decide",
)
def decide_leave(
    leave_request_id: UUID,
    payload: LeaveDecisionRequest,
    request: Request,
    principal: Principal = Depends(require_permissions(["leave.approve"])),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    """Approve/reject a leave request."""
    if payload.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid decision")

    now = datetime.now(tz=timezone.utc)

    lr = db.execute(
        text(
            """
            SELECT id, employee_id, status
            FROM leave_requests
            WHERE org_id = :org_id AND id = :id
            """
        ),
        {"org_id": str(principal.org_id), "id": str(leave_request_id)},
    ).fetchone()
    if not lr:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if lr[2] != "pending":
        raise HTTPException(status_code=400, detail="Leave request is not pending")

    if not principal.employee_id:
        raise HTTPException(status_code=400, detail="Approver must be mapped to an employee")

    db.execute(
        text(
            """
            UPDATE leave_requests
            SET status = :status,
                decided_at = :now,
                updated_at = :now
            WHERE id = :id
            """
        ),
        {"status": payload.decision, "now": now, "id": str(leave_request_id)},
    )

    db.execute(
        text(
            """
            INSERT INTO leave_approvals (id, org_id, leave_request_id, approver_employee_id, decision, comment, decided_at)
            VALUES (gen_random_uuid(), :org_id, :lr_id, :approver_id, :decision, :comment, :now)
            """
        ),
        {
            "org_id": str(principal.org_id),
            "lr_id": str(leave_request_id),
            "approver_id": str(principal.employee_id),
            "decision": payload.decision,
            "comment": payload.comment,
            "now": now,
        },
    )
    db.commit()

    write_audit_log(
        db,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        actor_employee_id=principal.employee_id,
        action="leave.decide",
        entity_type="leave_request",
        entity_id=leave_request_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"decision": payload.decision},
    )

    row = db.execute(
        text(
            """
            SELECT id, org_id, employee_id, leave_type_id, start_date, end_date, unit, quantity, reason, status,
                   requested_at, decided_at, created_at, updated_at
            FROM leave_requests
            WHERE id = :id
            """
        ),
        {"id": str(leave_request_id)},
    ).fetchone()

    return LeaveRequestOut(
        id=row[0],
        org_id=row[1],
        employee_id=row[2],
        leave_type_id=row[3],
        start_date=row[4],
        end_date=row[5],
        unit=row[6],
        quantity=float(row[7]),
        reason=row[8],
        status=row[9],
        requested_at=row[10],
        decided_at=row[11],
        created_at=row[12],
        updated_at=row[13],
    )


@router.get(
    "/balances/me",
    response_model=list[LeaveBalanceOut],
    summary="Get my leave balances",
    description="Returns leave balances for the authenticated employee. Requires leave.read.",
    operation_id="leave_my_balances",
)
def my_balances(
    principal: Principal = Depends(require_permissions(["leave.read"])),
    db: Session = Depends(get_db),
) -> list[LeaveBalanceOut]:
    """Return current user's leave balances."""
    employee_id = _require_employee(principal)

    rows = db.execute(
        text(
            """
            SELECT leave_type_id, balance
            FROM leave_balances
            WHERE org_id = :org_id AND employee_id = :employee_id
            ORDER BY leave_type_id
            """
        ),
        {"org_id": str(principal.org_id), "employee_id": str(employee_id)},
    ).fetchall()

    return [LeaveBalanceOut(leave_type_id=r[0], balance=float(r[1])) for r in rows]
