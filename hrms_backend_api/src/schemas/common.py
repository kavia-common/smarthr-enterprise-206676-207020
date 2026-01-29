from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class APIMessage(BaseModel):
    message: str = Field(..., description="Human-readable message.")


class UUIDResponse(BaseModel):
    id: UUID = Field(..., description="Resource UUID identifier.")


class Pagination(BaseModel):
    limit: int = Field(50, ge=1, le=200, description="Maximum number of records to return.")
    offset: int = Field(0, ge=0, description="Number of records to skip.")


class DateRange(BaseModel):
    start_date: date = Field(..., description="Start date (inclusive).")
    end_date: date = Field(..., description="End date (inclusive).")


class AuditLogOut(BaseModel):
    id: UUID
    org_id: UUID | None
    actor_user_id: UUID | None
    actor_employee_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID | None
    ip: str | None
    user_agent: str | None
    metadata: dict
    created_at: datetime
