from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.db import get_db
from src.deps.auth import Principal, get_current_principal, require_permissions
from src.schemas.hrms import AttendanceClockInRequest, AttendanceClockOutRequest, AttendanceSessionOut
from src.services.audit import write_audit_log

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def _require_employee(principal: Principal) -> UUID:
    if not principal.employee_id:
        raise HTTPException(status_code=400, detail="User has no employee mapping")
    return principal.employee_id


@router.post(
    "/clock-in",
    response_model=AttendanceSessionOut,
    summary="Clock in (current user)",
    description="Creates/updates today's attendance session for current employee. Requires auth.",
    operation_id="attendance_clock_in",
)
def clock_in(
    payload: AttendanceClockInRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> AttendanceSessionOut:
    """Clock in for current user (employee)."""
    employee_id = _require_employee(principal)
    today = date.today()
    now = datetime.now(tz=timezone.utc)

    existing = db.execute(
        text(
            """
            SELECT id, clock_in_at, clock_out_at, minutes_worked
            FROM attendance_sessions
            WHERE org_id = :org_id AND employee_id = :employee_id AND session_date = :d
            """
        ),
        {"org_id": str(principal.org_id), "employee_id": str(employee_id), "d": today},
    ).fetchone()

    if existing and existing[1]:
        raise HTTPException(status_code=400, detail="Already clocked in")

    if existing:
        row = db.execute(
            text(
                """
                UPDATE attendance_sessions
                SET clock_in_at = :now,
                    work_mode = :work_mode,
                    source = :source,
                    notes = COALESCE(:notes, notes),
                    updated_at = :now
                WHERE id = :id
                RETURNING id, org_id, employee_id, session_date, work_mode, clock_in_at, clock_out_at, minutes_worked, source, notes, created_at, updated_at
                """
            ),
            {
                "id": str(existing[0]),
                "now": now,
                "work_mode": payload.work_mode,
                "source": payload.source,
                "notes": payload.notes,
            },
        ).fetchone()
    else:
        session_id = UUID(db.execute(text("SELECT gen_random_uuid()")).scalar_one())
        row = db.execute(
            text(
                """
                INSERT INTO attendance_sessions (
                  id, org_id, employee_id, session_date, work_mode, clock_in_at, minutes_worked, source, notes, created_at, updated_at
                )
                VALUES (:id, :org_id, :employee_id, :d, :work_mode, :now, 0, :source, :notes, :now, :now)
                RETURNING id, org_id, employee_id, session_date, work_mode, clock_in_at, clock_out_at, minutes_worked, source, notes, created_at, updated_at
                """
            ),
            {
                "id": str(session_id),
                "org_id": str(principal.org_id),
                "employee_id": str(employee_id),
                "d": today,
                "work_mode": payload.work_mode,
                "now": now,
                "source": payload.source,
                "notes": payload.notes,
            },
        ).fetchone()

    db.commit()

    write_audit_log(
        db,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        actor_employee_id=employee_id,
        action="attendance.clock_in",
        entity_type="attendance_session",
        entity_id=row[0],
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"session_date": str(today), "work_mode": payload.work_mode},
    )

    return AttendanceSessionOut(
        id=row[0],
        org_id=row[1],
        employee_id=row[2],
        session_date=row[3],
        work_mode=row[4],
        clock_in_at=row[5],
        clock_out_at=row[6],
        minutes_worked=row[7],
        source=row[8],
        notes=row[9],
        created_at=row[10],
        updated_at=row[11],
    )


@router.post(
    "/clock-out",
    response_model=AttendanceSessionOut,
    summary="Clock out (current user)",
    description="Clock out of today's session for current employee; computes minutes_worked. Requires auth.",
    operation_id="attendance_clock_out",
)
def clock_out(
    payload: AttendanceClockOutRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> AttendanceSessionOut:
    """Clock out for current user (employee)."""
    employee_id = _require_employee(principal)
    today = date.today()
    now = datetime.now(tz=timezone.utc)

    existing = db.execute(
        text(
            """
            SELECT id, clock_in_at, clock_out_at
            FROM attendance_sessions
            WHERE org_id = :org_id AND employee_id = :employee_id AND session_date = :d
            """
        ),
        {"org_id": str(principal.org_id), "employee_id": str(employee_id), "d": today},
    ).fetchone()

    if not existing or not existing[1]:
        raise HTTPException(status_code=400, detail="Not clocked in")
    if existing[2]:
        raise HTTPException(status_code=400, detail="Already clocked out")

    clock_in_at: datetime = existing[1]
    minutes = int(max(0, (now - clock_in_at).total_seconds() // 60))

    row = db.execute(
        text(
            """
            UPDATE attendance_sessions
            SET clock_out_at = :now,
                minutes_worked = :minutes,
                notes = COALESCE(:notes, notes),
                updated_at = :now
            WHERE id = :id
            RETURNING id, org_id, employee_id, session_date, work_mode, clock_in_at, clock_out_at, minutes_worked, source, notes, created_at, updated_at
            """
        ),
        {"id": str(existing[0]), "now": now, "minutes": minutes, "notes": payload.notes},
    ).fetchone()
    db.commit()

    write_audit_log(
        db,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        actor_employee_id=employee_id,
        action="attendance.clock_out",
        entity_type="attendance_session",
        entity_id=row[0],
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"session_date": str(today), "minutes_worked": minutes},
    )

    return AttendanceSessionOut(
        id=row[0],
        org_id=row[1],
        employee_id=row[2],
        session_date=row[3],
        work_mode=row[4],
        clock_in_at=row[5],
        clock_out_at=row[6],
        minutes_worked=row[7],
        source=row[8],
        notes=row[9],
        created_at=row[10],
        updated_at=row[11],
    )


@router.get(
    "/sessions",
    response_model=list[AttendanceSessionOut],
    summary="List attendance sessions (org)",
    description="Lists attendance sessions for org by date range; requires employee.read.",
    operation_id="attendance_list_sessions",
)
def list_sessions(
    start_date: date,
    end_date: date,
    employee_id: UUID | None = None,
    principal: Principal = Depends(require_permissions(["employee.read"])),
    db: Session = Depends(get_db),
) -> list[AttendanceSessionOut]:
    """List attendance sessions with filters."""
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="Invalid date range")

    params = {"org_id": str(principal.org_id), "start": start_date, "end": end_date}
    employee_clause = ""
    if employee_id:
        employee_clause = " AND employee_id = :employee_id"
        params["employee_id"] = str(employee_id)

    rows = db.execute(
        text(
            f"""
            SELECT id, org_id, employee_id, session_date, work_mode, clock_in_at, clock_out_at, minutes_worked, source, notes, created_at, updated_at
            FROM attendance_sessions
            WHERE org_id = :org_id
              AND session_date BETWEEN :start AND :end
              {employee_clause}
            ORDER BY session_date DESC
            LIMIT 500
            """
        ),
        params,
    ).fetchall()

    return [
        AttendanceSessionOut(
            id=r[0],
            org_id=r[1],
            employee_id=r[2],
            session_date=r[3],
            work_mode=r[4],
            clock_in_at=r[5],
            clock_out_at=r[6],
            minutes_worked=r[7],
            source=r[8],
            notes=r[9],
            created_at=r[10],
            updated_at=r[11],
        )
        for r in rows
    ]
