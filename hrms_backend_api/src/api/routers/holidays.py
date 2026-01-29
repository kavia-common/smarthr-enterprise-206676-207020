from __future__ import annotations

from datetime import date


from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.db import get_db
from src.deps.auth import Principal, require_permissions
from src.schemas.hrms import HolidayOut

router = APIRouter(prefix="/holidays", tags=["Holidays"])


@router.get(
    "",
    response_model=list[HolidayOut],
    summary="List holidays by date range",
    description="Lists holidays for the org within a date range. Requires employee.read.",
    operation_id="holidays_list",
)
def list_holidays(
    start_date: date,
    end_date: date,
    principal: Principal = Depends(require_permissions(["employee.read"])),
    db: Session = Depends(get_db),
) -> list[HolidayOut]:
    """List holidays for org."""
    rows = db.execute(
        text(
            """
            SELECT id, org_id, calendar_id, holiday_date, name, type
            FROM holidays
            WHERE org_id = :org_id AND holiday_date BETWEEN :start AND :end
            ORDER BY holiday_date ASC
            """
        ),
        {"org_id": str(principal.org_id), "start": start_date, "end": end_date},
    ).fetchall()

    return [
        HolidayOut(
            id=r[0],
            org_id=r[1],
            calendar_id=r[2],
            holiday_date=r[3],
            name=r[4],
            type=r[5],
        )
        for r in rows
    ]
