from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EmployeeCreate(BaseModel):
    employee_code: str = Field(..., description="Unique employee code within the org.")
    first_name: str = Field(..., description="First name.")
    last_name: str | None = Field(None, description="Last name.")
    work_email: str | None = Field(None, description="Work email address.")
    personal_email: str | None = Field(None, description="Personal email address.")
    phone: str | None = Field(None, description="Phone number.")
    job_title: str | None = Field(None, description="Job title.")
    department: str | None = Field(None, description="Department.")
    location: str | None = Field(None, description="Location.")
    employment_type: str = Field("full_time", description="Employment type.")
    status: str = Field("active", description="Employment status.")
    date_of_joining: date | None = Field(None, description="Joining date.")
    manager_employee_id: UUID | None = Field(None, description="Manager employee id.")


class EmployeeOut(BaseModel):
    id: UUID
    org_id: UUID
    user_id: UUID | None
    employee_code: str
    first_name: str
    last_name: str | None
    work_email: str | None
    phone: str | None
    job_title: str | None
    department: str | None
    location: str | None
    employment_type: str
    status: str
    date_of_joining: date | None
    manager_employee_id: UUID | None
    created_at: datetime
    updated_at: datetime


class AttendanceClockInRequest(BaseModel):
    work_mode: str = Field("onsite", description="Work mode: onsite/remote/hybrid.")
    source: str = Field("web", description="Source: web/mobile/api/import.")
    notes: str | None = Field(None, description="Optional notes.")


class AttendanceClockOutRequest(BaseModel):
    notes: str | None = Field(None, description="Optional notes.")


class AttendanceSessionOut(BaseModel):
    id: UUID
    org_id: UUID
    employee_id: UUID
    session_date: date
    work_mode: str
    clock_in_at: datetime | None
    clock_out_at: datetime | None
    minutes_worked: int
    source: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class LeaveApplyRequest(BaseModel):
    leave_type_id: UUID = Field(..., description="Leave type id.")
    start_date: date = Field(..., description="Leave start date.")
    end_date: date = Field(..., description="Leave end date.")
    unit: str = Field("day", description="Unit: day/hour.")
    quantity: float = Field(1, gt=0, description="Quantity in days/hours.")
    reason: str | None = Field(None, description="Optional reason.")


class LeaveRequestOut(BaseModel):
    id: UUID
    org_id: UUID
    employee_id: UUID
    leave_type_id: UUID
    start_date: date
    end_date: date
    unit: str
    quantity: float
    reason: str | None
    status: str
    requested_at: datetime
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LeaveDecisionRequest(BaseModel):
    decision: str = Field(..., description="Decision: approved/rejected.")
    comment: str | None = Field(None, description="Optional comment.")


class LeaveBalanceOut(BaseModel):
    leave_type_id: UUID
    balance: float


class HolidayOut(BaseModel):
    id: UUID
    org_id: UUID
    calendar_id: UUID
    holiday_date: date
    name: str
    type: str


class PayrollCycleOut(BaseModel):
    id: UUID
    org_id: UUID
    code: str
    start_date: date
    end_date: date
    status: str
    created_at: datetime
    updated_at: datetime
