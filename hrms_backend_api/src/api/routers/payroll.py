from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.db import get_db
from src.deps.auth import Principal, require_permissions
from src.schemas.hrms import PayrollCycleOut

router = APIRouter(prefix="/payroll", tags=["Payroll"])


@router.get(
    "/cycles",
    response_model=list[PayrollCycleOut],
    summary="List payroll cycles",
    description="Lists payroll cycles for the org. Requires employee.read (or a future payroll permission).",
    operation_id="payroll_list_cycles",
)
def list_payroll_cycles(
    principal: Principal = Depends(require_permissions(["employee.read"])),
    db: Session = Depends(get_db),
) -> list[PayrollCycleOut]:
    """List payroll cycles for org."""
    rows = db.execute(
        text(
            """
            SELECT id, org_id, code, start_date, end_date, status, created_at, updated_at
            FROM payroll_cycles
            WHERE org_id = :org_id
            ORDER BY start_date DESC
            LIMIT 200
            """
        ),
        {"org_id": str(principal.org_id)},
    ).fetchall()

    return [
        PayrollCycleOut(
            id=r[0],
            org_id=r[1],
            code=r[2],
            start_date=r[3],
            end_date=r[4],
            status=r[5],
            created_at=r[6],
            updated_at=r[7],
        )
        for r in rows
    ]
