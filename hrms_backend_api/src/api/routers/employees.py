from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.db import get_db
from src.deps.auth import Principal, require_permissions
from src.schemas.hrms import EmployeeCreate, EmployeeOut
from src.services.audit import write_audit_log

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.get(
    "",
    response_model=list[EmployeeOut],
    summary="List employees",
    description="List employees in the current org. Requires employee.read.",
    operation_id="employees_list",
)
def list_employees(
    limit: int = 50,
    offset: int = 0,
    principal: Principal = Depends(require_permissions(["employee.read"])),
    db: Session = Depends(get_db),
) -> list[EmployeeOut]:
    """List employees for current org."""
    rows = db.execute(
        text(
            """
            SELECT id, org_id, user_id, employee_code, first_name, last_name, work_email, phone,
                   job_title, department, location, employment_type, status,
                   date_of_joining, manager_employee_id, created_at, updated_at
            FROM employees
            WHERE org_id = :org_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"org_id": str(principal.org_id), "limit": limit, "offset": offset},
    ).fetchall()

    return [
        EmployeeOut(
            id=r[0],
            org_id=r[1],
            user_id=r[2],
            employee_code=r[3],
            first_name=r[4],
            last_name=r[5],
            work_email=r[6],
            phone=r[7],
            job_title=r[8],
            department=r[9],
            location=r[10],
            employment_type=r[11],
            status=r[12],
            date_of_joining=r[13],
            manager_employee_id=r[14],
            created_at=r[15],
            updated_at=r[16],
        )
        for r in rows
    ]


@router.post(
    "",
    response_model=EmployeeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create employee",
    description="Create a new employee record. Requires employee.write.",
    operation_id="employees_create",
)
def create_employee(
    payload: EmployeeCreate,
    request: Request,
    principal: Principal = Depends(require_permissions(["employee.write"])),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    """Create an employee in current org."""
    new_id = UUID(db.execute(text("SELECT gen_random_uuid()")).scalar_one())
    row = db.execute(
        text(
            """
            INSERT INTO employees (
              id, org_id, employee_code, first_name, last_name, work_email, personal_email, phone,
              job_title, department, location, employment_type, status, date_of_joining, manager_employee_id,
              created_at, updated_at
            )
            VALUES (
              :id, :org_id, :employee_code, :first_name, :last_name, :work_email, :personal_email, :phone,
              :job_title, :department, :location, :employment_type, :status, :date_of_joining, :manager_employee_id,
              now(), now()
            )
            RETURNING id, org_id, user_id, employee_code, first_name, last_name, work_email, phone,
                      job_title, department, location, employment_type, status, date_of_joining, manager_employee_id, created_at, updated_at
            """
        ),
        {
            "id": str(new_id),
            "org_id": str(principal.org_id),
            "employee_code": payload.employee_code,
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "work_email": payload.work_email,
            "personal_email": payload.personal_email,
            "phone": payload.phone,
            "job_title": payload.job_title,
            "department": payload.department,
            "location": payload.location,
            "employment_type": payload.employment_type,
            "status": payload.status,
            "date_of_joining": payload.date_of_joining,
            "manager_employee_id": str(payload.manager_employee_id) if payload.manager_employee_id else None,
        },
    ).fetchone()
    db.commit()

    if not row:
        raise HTTPException(status_code=500, detail="Failed to create employee")

    write_audit_log(
        db,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        actor_employee_id=principal.employee_id,
        action="employee.create",
        entity_type="employee",
        entity_id=new_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"employee_code": payload.employee_code},
    )

    return EmployeeOut(
        id=row[0],
        org_id=row[1],
        user_id=row[2],
        employee_code=row[3],
        first_name=row[4],
        last_name=row[5],
        work_email=row[6],
        phone=row[7],
        job_title=row[8],
        department=row[9],
        location=row[10],
        employment_type=row[11],
        status=row[12],
        date_of_joining=row[13],
        manager_employee_id=row[14],
        created_at=row[15],
        updated_at=row[16],
    )


@router.get(
    "/{employee_id}/reportees",
    response_model=list[EmployeeOut],
    summary="List direct reportees",
    description="Returns direct reportees (employees whose manager_employee_id is the given employee). Requires employee.read.",
    operation_id="employees_reportees",
)
def list_reportees(
    employee_id: UUID,
    principal: Principal = Depends(require_permissions(["employee.read"])),
    db: Session = Depends(get_db),
) -> list[EmployeeOut]:
    """List direct reportees for an employee."""
    rows = db.execute(
        text(
            """
            SELECT id, org_id, user_id, employee_code, first_name, last_name, work_email, phone,
                   job_title, department, location, employment_type, status,
                   date_of_joining, manager_employee_id, created_at, updated_at
            FROM employees
            WHERE org_id = :org_id AND manager_employee_id = :manager_id
            ORDER BY created_at DESC
            """
        ),
        {"org_id": str(principal.org_id), "manager_id": str(employee_id)},
    ).fetchall()

    return [
        EmployeeOut(
            id=r[0],
            org_id=r[1],
            user_id=r[2],
            employee_code=r[3],
            first_name=r[4],
            last_name=r[5],
            work_email=r[6],
            phone=r[7],
            job_title=r[8],
            department=r[9],
            location=r[10],
            employment_type=r[11],
            status=r[12],
            date_of_joining=r[13],
            manager_employee_id=r[14],
            created_at=r[15],
            updated_at=r[16],
        )
        for r in rows
    ]
