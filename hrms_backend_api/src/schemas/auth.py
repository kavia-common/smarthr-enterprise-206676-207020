from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    org_slug: str = Field("demo", description="Organization slug (tenant identifier).")
    email: str = Field(..., description="User email.")
    password: str = Field(..., min_length=6, description="User password.")


class TokenPair(BaseModel):
    access_token: str = Field(..., description="JWT access token.")
    refresh_token: str = Field(..., description="JWT refresh token.")
    token_type: str = Field("bearer", description="Token type for Authorization header.")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="JWT refresh token.")


class MeResponse(BaseModel):
    user_id: UUID = Field(..., description="Authenticated user id.")
    org_id: UUID = Field(..., description="Authenticated org id.")
    roles: list[str] = Field(..., description="Role names for the authenticated user.")
    permissions: list[str] = Field(..., description="Permission keys derived from roles.")
    employee_id: UUID | None = Field(None, description="Employee id (if mapped to a user).")
