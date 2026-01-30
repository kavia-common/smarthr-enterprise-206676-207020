import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


def _split_csv(value: Optional[str]) -> List[str]:
    """Split a CSV env var into a list of stripped strings."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _bool_env(name: str, default: bool = False) -> bool:
    """Parse boolean-ish env vars."""
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


# -----------------------------
# Demo in-memory "auth database"
# -----------------------------
# NOTE: This is intentionally simple so the system boots without a DB.
# It enables the existing frontend signin + dashboard UX.
_DEMO_USERS: Dict[str, Dict[str, object]] = {
    "admin@demo.local": {
        "password": "admin123",
        "roles": ["admin"],
        "user_id": "usr_demo_admin",
        "org_id": "org_demo",
        "employee_id": "emp_demo_admin",
    },
    "hr@demo.local": {
        "password": "hr123",
        "roles": ["hr"],
        "user_id": "usr_demo_hr",
        "org_id": "org_demo",
        "employee_id": "emp_demo_hr",
    },
    "manager@demo.local": {
        "password": "manager123",
        "roles": ["manager"],
        "user_id": "usr_demo_manager",
        "org_id": "org_demo",
        "employee_id": "emp_demo_manager",
    },
    "employee@demo.local": {
        "password": "employee123",
        "roles": ["employee"],
        "user_id": "usr_demo_employee",
        "org_id": "org_demo",
        "employee_id": "emp_demo_employee",
    },
}

# Very small "token" mechanism: token is literally "demo:<email>"
_TOKEN_PREFIX = "demo:"


def _issue_token(email: str) -> str:
    return f"{_TOKEN_PREFIX}{email}"


def _email_from_token(token: str) -> Optional[str]:
    if not token.startswith(_TOKEN_PREFIX):
        return None
    return token[len(_TOKEN_PREFIX) :]


def _parse_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _get_current_user(authorization: Optional[str]) -> Dict[str, object]:
    token = _parse_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    email = _email_from_token(token)
    if not email or email not in _DEMO_USERS:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = _DEMO_USERS[email]
    return {"email": email, **user, "token": token}


def _utcnow_iso() -> str:
    """Return UTC now in ISO format with timezone suffix Z."""
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def create_app() -> FastAPI:
    """Create and configure the FastAPI app instance."""
    openapi_tags = [
        {"name": "Health", "description": "Service health and diagnostics endpoints."},
        {"name": "Auth", "description": "Authentication endpoints used by the web app."},
        {"name": "HRMS", "description": "Minimal HRMS endpoints required by the dashboard UI."},
    ]

    app = FastAPI(
        title="SmartHR AI - Backend API",
        description="FastAPI backend for SmartHR AI (HRMS).",
        version="0.1.0",
        openapi_tags=openapi_tags,
    )

    # CORS configuration from env (supports multiple possible env var names present in .env).
    allowed_origins = (
        _split_csv(os.getenv("ALLOWED_ORIGINS"))
        or _split_csv(os.getenv("CORS_ALLOW_ORIGINS"))
        or _split_csv(os.getenv("CORS_ORIGINS"))
        or ["*"]
    )
    allowed_headers = _split_csv(os.getenv("ALLOWED_HEADERS")) or ["*"]
    allowed_methods = _split_csv(os.getenv("ALLOWED_METHODS")) or ["*"]
    cors_max_age = int(os.getenv("CORS_MAX_AGE", "3600"))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=allowed_methods,
        allow_headers=allowed_headers,
        max_age=cors_max_age,
    )

    def _health_payload():
        """Build a resilient health payload, with optional DB connectivity status."""
        db_url = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
        check_db = _bool_env("HEALTHCHECK_DB", default=False)

        payload = {"status": "ok"}

        # Optional DB connectivity check that does not block readiness by default.
        if check_db and db_url:
            try:
                # Lazy import so app can still boot even if DB deps are missing/misconfigured.
                from sqlalchemy import create_engine, text

                engine = create_engine(db_url, pool_pre_ping=True)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                payload["database"] = {"status": "ok"}
            except Exception as exc:  # noqa: BLE001 - health endpoint must be resilient
                payload["database"] = {"status": "error", "detail": str(exc)}

        return payload

    @app.get(
        "/health",
        tags=["Health"],
        summary="Health check",
        description="Returns process liveness and (optionally) basic DB connectivity status.",
        operation_id="getHealth",
    )
    def health():
        """
        Health endpoint used by platform readiness checks.

        Returns:
            JSON payload with status and optional database connectivity details.
        """
        return _health_payload()

    @app.get(
        "/healthz",
        tags=["Health"],
        summary="Health check (alias)",
        description="Alias for `/health` to match platforms that probe `/healthz` by convention.",
        operation_id="getHealthz",
    )
    def healthz():
        """
        Health endpoint alias for platform readiness checks.

        Returns:
            JSON payload with status and optional database connectivity details.
        """
        return _health_payload()

    # -----------------------------
    # Auth endpoints (used by UI)
    # -----------------------------

    class LoginRequest(BaseModel):
        """
        Login payload for the UI.

        Notes:
        - Frontend historically used camelCase `orgSlug`. We accept both `org_slug` and `orgSlug`
          to prevent request/response mismatch regressions.
        - `org_slug` defaults to `demo` to keep the demo flow resilient.
        """

        org_slug: str = Field(
            default="demo",
            validation_alias="orgSlug",
            description="Organization slug (demo uses 'demo'). Accepts both org_slug and orgSlug.",
        )
        email: str = Field(..., description="User email.")
        password: str = Field(..., description="User password.")

    class TokenPair(BaseModel):
        access_token: str = Field(..., description="Access token.")
        refresh_token: str = Field(..., description="Refresh token (demo placeholder).")
        token_type: str = Field("bearer", description="Token type.")

    @app.post(
        "/auth/login",
        tags=["Auth"],
        summary="Login",
        description="Demo login endpoint used by the frontend sign-in page.",
        operation_id="postAuthLogin",
        response_model=TokenPair,
    )
    def auth_login(payload: LoginRequest):
        """
        Authenticate a user and return an access/refresh token pair.

        This demo implementation uses in-memory users so the service works without DB.

        Returns:
            TokenPair: access/refresh token pair.

        Raises:
            HTTPException: 400 for unknown org, 401 for invalid credentials.
        """
        try:
            org = (payload.org_slug or "demo").strip().lower()
            if org != "demo":
                raise HTTPException(status_code=400, detail="Unknown org")

            email = (payload.email or "").strip().lower()
            user = _DEMO_USERS.get(email)
            if not user or str(user["password"]) != payload.password:
                raise HTTPException(status_code=401, detail="Invalid credentials")

            access = _issue_token(email)
            refresh = f"refresh:{access}"
            return TokenPair(access_token=access, refresh_token=refresh, token_type="bearer")
        except HTTPException:
            raise
        except Exception:
            # Never leak unexpected errors as 500 during auth flows; keep UI stable.
            raise HTTPException(status_code=400, detail="Invalid login request")

    class MeResponse(BaseModel):
        user_id: str = Field(..., description="User id.")
        org_id: str = Field(..., description="Org id.")
        roles: List[str] = Field(..., description="Role list.")
        permissions: List[str] = Field(default_factory=list, description="Permission list (demo).")
        employee_id: Optional[str] = Field(default=None, description="Employee id if applicable.")

    @app.get(
        "/auth/me",
        tags=["Auth"],
        summary="Current user",
        description="Return the current user context for the provided bearer token.",
        operation_id="getAuthMe",
        response_model=MeResponse,
    )
    def auth_me(authorization: Optional[str] = Header(default=None)):
        """Return user context for the logged-in user."""
        u = _get_current_user(authorization)
        return MeResponse(
            user_id=str(u["user_id"]),
            org_id=str(u["org_id"]),
            roles=[str(r) for r in (u["roles"] or [])],
            permissions=[],
            employee_id=str(u["employee_id"]) if u.get("employee_id") else None,
        )

    # -----------------------------
    # HRMS endpoints used by dashboard
    # -----------------------------

    # --- Leaves ---

    class LeaveBalanceOut(BaseModel):
        leave_type_id: str = Field(..., description="Leave type id.")
        balance: float = Field(..., description="Remaining balance for the leave type.")

    @app.get(
        "/leaves/balances/me",
        tags=["HRMS"],
        summary="My leave balances",
        description="Return demo leave balances for current user.",
        operation_id="getMyLeaveBalances",
        response_model=List[LeaveBalanceOut],
    )
    def my_leave_balances(authorization: Optional[str] = Header(default=None)):
        """Return leave balances for the current user (demo)."""
        _get_current_user(authorization)
        return [
            LeaveBalanceOut(leave_type_id="annual", balance=12),
            LeaveBalanceOut(leave_type_id="sick", balance=6),
        ]

    class LeaveRequestOut(BaseModel):
        id: str = Field(..., description="Leave request id.")
        org_id: str = Field(..., description="Org id.")
        employee_id: str = Field(..., description="Employee id.")
        leave_type_id: str = Field(..., description="Leave type id.")
        start_date: str = Field(..., description="Start date YYYY-MM-DD.")
        end_date: str = Field(..., description="End date YYYY-MM-DD.")
        unit: str = Field("days", description="Unit (days/hours).")
        quantity: float = Field(..., description="Quantity.")
        reason: Optional[str] = Field(default=None, description="Reason for leave.")
        status: str = Field(..., description="Status: pending/approved/rejected.")
        requested_at: str = Field(..., description="Requested timestamp (ISO).")
        decided_at: Optional[str] = Field(default=None, description="Decision timestamp (ISO).")
        created_at: str = Field(..., description="Created timestamp (ISO).")
        updated_at: str = Field(..., description="Updated timestamp (ISO).")

    class LeaveRequestCreateIn(BaseModel):
        leave_type_id: str = Field(..., description="Leave type id.")
        start_date: str = Field(..., description="Start date YYYY-MM-DD.")
        end_date: str = Field(..., description="End date YYYY-MM-DD.")
        unit: str = Field("days", description="Unit.")
        quantity: float = Field(..., description="Quantity.")
        reason: Optional[str] = Field(default=None, description="Reason.")

    class LeaveDecisionIn(BaseModel):
        decision: str = Field(..., description="Decision: approved|rejected.")
        comment: Optional[str] = Field(default=None, description="Optional comment.")

    # Simple in-memory store (per-process) so UI can create/approve leaves in one session.
    _leave_requests: List[LeaveRequestOut] = []

    @app.post(
        "/leaves/requests",
        tags=["HRMS"],
        summary="Apply leave",
        description="Create a leave request (demo in-memory).",
        operation_id="postLeaveRequest",
        response_model=LeaveRequestOut,
    )
    def apply_leave(payload: LeaveRequestCreateIn, authorization: Optional[str] = Header(default=None)):
        """Create a new leave request for current user (demo)."""
        u = _get_current_user(authorization)
        now = _utcnow_iso()
        lr = LeaveRequestOut(
            id=f"lv_{len(_leave_requests)+1}",
            org_id=str(u["org_id"]),
            employee_id=str(u["employee_id"]),
            leave_type_id=payload.leave_type_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            unit=payload.unit or "days",
            quantity=float(payload.quantity),
            reason=payload.reason,
            status="pending",
            requested_at=now,
            decided_at=None,
            created_at=now,
            updated_at=now,
        )
        _leave_requests.insert(0, lr)
        return lr

    @app.get(
        "/leaves/requests",
        tags=["HRMS"],
        summary="List leave requests",
        description="List leave requests (demo in-memory). Supports optional `status_filter` query.",
        operation_id="listLeaveRequests",
        response_model=List[LeaveRequestOut],
    )
    def list_leave_requests(
        status_filter: Optional[str] = None,
        authorization: Optional[str] = Header(default=None),
    ):
        """List leave requests for current user (demo)."""
        u = _get_current_user(authorization)
        items = [r for r in _leave_requests if r.org_id == str(u["org_id"])]
        if status_filter:
            items = [r for r in items if r.status == status_filter]
        return items

    @app.post(
        "/leaves/requests/{leave_request_id}/decision",
        tags=["HRMS"],
        summary="Decide leave request",
        description="Approve or reject a leave request (demo).",
        operation_id="decideLeaveRequest",
        response_model=LeaveRequestOut,
    )
    def decide_leave(
        leave_request_id: str,
        payload: LeaveDecisionIn,
        authorization: Optional[str] = Header(default=None),
    ):
        """Approve/reject a leave request (demo)."""
        _get_current_user(authorization)

        decision = (payload.decision or "").strip().lower()
        if decision not in {"approved", "rejected"}:
            raise HTTPException(status_code=400, detail="Invalid decision")

        for idx, r in enumerate(_leave_requests):
            if r.id == leave_request_id:
                now = _utcnow_iso()
                updated = r.model_copy(
                    update={
                        "status": decision,
                        "decided_at": now,
                        "updated_at": now,
                    }
                )
                _leave_requests[idx] = updated
                return updated

        raise HTTPException(status_code=404, detail="Leave request not found")

    # --- Holidays ---

    class HolidayOut(BaseModel):
        id: str = Field(..., description="Holiday id.")
        org_id: str = Field(..., description="Org id.")
        calendar_id: str = Field(..., description="Calendar id.")
        holiday_date: str = Field(..., description="Date in YYYY-MM-DD.")
        name: str = Field(..., description="Holiday name.")
        type: str = Field("holiday", description="Type of entry.")

    @app.get(
        "/holidays",
        tags=["HRMS"],
        summary="List holidays",
        description="Return demo holiday list between start_date and end_date.",
        operation_id="listHolidays",
        response_model=List[HolidayOut],
    )
    def list_holidays(
        start_date: str,
        end_date: str,
        authorization: Optional[str] = Header(default=None),
    ):
        """List holidays in a date range (demo)."""
        u = _get_current_user(authorization)

        # Return a couple of deterministic demo holidays within the range window.
        today = date.today()
        items = [
            HolidayOut(
                id="hol_demo_1",
                org_id=str(u["org_id"]),
                calendar_id="cal_demo",
                holiday_date=(today + timedelta(days=7)).isoformat(),
                name="Demo Holiday",
                type="holiday",
            ),
            HolidayOut(
                id="hol_demo_2",
                org_id=str(u["org_id"]),
                calendar_id="cal_demo",
                holiday_date=(today + timedelta(days=30)).isoformat(),
                name="Demo Festival",
                type="holiday",
            ),
        ]
        # Keep filtering simple: frontend already sorts; just return the demo list.
        _ = start_date, end_date
        return items

    # --- Employees ---

    class EmployeeOut(BaseModel):
        id: str
        org_id: str
        user_id: str
        employee_code: str
        first_name: str
        last_name: Optional[str] = None
        work_email: Optional[str] = None
        phone: Optional[str] = None
        job_title: Optional[str] = None
        department: Optional[str] = None
        location: Optional[str] = None
        employment_type: Optional[str] = None
        status: str
        date_of_joining: Optional[str] = None
        manager_employee_id: Optional[str] = None
        created_at: str
        updated_at: str

    @app.get(
        "/employees",
        tags=["HRMS"],
        summary="List employees",
        description="Return a demo employee directory.",
        operation_id="listEmployees",
        response_model=List[EmployeeOut],
    )
    def list_employees(
        limit: int = 50,
        offset: int = 0,
        authorization: Optional[str] = Header(default=None),
    ):
        """List employees (demo)."""
        u = _get_current_user(authorization)
        now = _utcnow_iso()

        # Demo directory (stable ids + fields expected by UI)
        directory = [
            EmployeeOut(
                id="emp_demo_admin",
                org_id=str(u["org_id"]),
                user_id="usr_demo_admin",
                employee_code="A001",
                first_name="Demo",
                last_name="Admin",
                work_email="admin@demo.local",
                phone=None,
                job_title="Administrator",
                department="Admin",
                location="HQ",
                employment_type="full_time",
                status="active",
                date_of_joining="2023-01-01",
                manager_employee_id=None,
                created_at=now,
                updated_at=now,
            ),
            EmployeeOut(
                id="emp_demo_hr",
                org_id=str(u["org_id"]),
                user_id="usr_demo_hr",
                employee_code="H001",
                first_name="Demo",
                last_name="HR",
                work_email="hr@demo.local",
                phone=None,
                job_title="HR Generalist",
                department="HR",
                location="HQ",
                employment_type="full_time",
                status="active",
                date_of_joining="2023-02-01",
                manager_employee_id="emp_demo_admin",
                created_at=now,
                updated_at=now,
            ),
            EmployeeOut(
                id="emp_demo_manager",
                org_id=str(u["org_id"]),
                user_id="usr_demo_manager",
                employee_code="M001",
                first_name="Demo",
                last_name="Manager",
                work_email="manager@demo.local",
                phone=None,
                job_title="Engineering Manager",
                department="Engineering",
                location="Remote",
                employment_type="full_time",
                status="active",
                date_of_joining="2023-03-01",
                manager_employee_id="emp_demo_admin",
                created_at=now,
                updated_at=now,
            ),
            EmployeeOut(
                id="emp_demo_employee",
                org_id=str(u["org_id"]),
                user_id="usr_demo_employee",
                employee_code="E001",
                first_name="Demo",
                last_name="Employee",
                work_email="employee@demo.local",
                phone=None,
                job_title="Software Engineer",
                department="Engineering",
                location="Remote",
                employment_type="full_time",
                status="active",
                date_of_joining="2023-04-01",
                manager_employee_id="emp_demo_manager",
                created_at=now,
                updated_at=now,
            ),
        ]

        sliced = directory[offset : offset + limit]
        return sliced

    # --- Attendance ---

    class AttendanceSessionOut(BaseModel):
        id: str
        org_id: str
        employee_id: str
        session_date: str
        work_mode: str
        clock_in_at: str
        clock_out_at: Optional[str] = None
        minutes_worked: int
        source: str
        notes: Optional[str] = None
        created_at: str
        updated_at: str

    class ClockInIn(BaseModel):
        work_mode: str = Field(..., description="Work mode: remote|onsite|hybrid.")
        source: str = Field("web", description="Source.")
        notes: Optional[str] = Field(default=None, description="Optional notes.")

    class ClockOutIn(BaseModel):
        notes: Optional[str] = Field(default=None, description="Optional notes.")

    _attendance_sessions: List[AttendanceSessionOut] = []

    def _find_open_session(employee_id: str) -> Optional[int]:
        for idx, s in enumerate(_attendance_sessions):
            if s.employee_id == employee_id and s.clock_out_at is None:
                return idx
        return None

    @app.post(
        "/attendance/clock-in",
        tags=["HRMS"],
        summary="Clock in",
        description="Create an attendance session for today (demo in-memory).",
        operation_id="clockIn",
        response_model=AttendanceSessionOut,
    )
    def clock_in(payload: ClockInIn, authorization: Optional[str] = Header(default=None)):
        """Clock-in for current user (demo)."""
        u = _get_current_user(authorization)
        emp_id = str(u["employee_id"])

        open_idx = _find_open_session(emp_id)
        if open_idx is not None:
            # Already clocked-in; return existing open session for idempotency.
            return _attendance_sessions[open_idx]

        now = _utcnow_iso()
        today = date.today().isoformat()
        session = AttendanceSessionOut(
            id=f"att_{len(_attendance_sessions)+1}",
            org_id=str(u["org_id"]),
            employee_id=emp_id,
            session_date=today,
            work_mode=payload.work_mode,
            clock_in_at=now,
            clock_out_at=None,
            minutes_worked=0,
            source=payload.source or "web",
            notes=payload.notes,
            created_at=now,
            updated_at=now,
        )
        _attendance_sessions.insert(0, session)
        return session

    @app.post(
        "/attendance/clock-out",
        tags=["HRMS"],
        summary="Clock out",
        description="Close the open attendance session (demo).",
        operation_id="clockOut",
        response_model=AttendanceSessionOut,
    )
    def clock_out(payload: ClockOutIn, authorization: Optional[str] = Header(default=None)):
        """Clock-out for current user (demo)."""
        u = _get_current_user(authorization)
        emp_id = str(u["employee_id"])

        open_idx = _find_open_session(emp_id)
        if open_idx is None:
            raise HTTPException(status_code=400, detail="No open attendance session")

        now = _utcnow_iso()
        existing = _attendance_sessions[open_idx]

        # Compute minutes worked from timestamps if possible (best-effort).
        minutes = 0
        try:
            # existing.clock_in_at is ISO with Z
            cin = datetime.fromisoformat(existing.clock_in_at.replace("Z", "+00:00"))
            cout = datetime.fromisoformat(now.replace("Z", "+00:00"))
            minutes = max(0, int((cout - cin).total_seconds() // 60))
        except Exception:
            minutes = existing.minutes_worked or 0

        updated = existing.model_copy(
            update={
                "clock_out_at": now,
                "minutes_worked": minutes,
                "notes": payload.notes if payload.notes is not None else existing.notes,
                "updated_at": now,
            }
        )
        _attendance_sessions[open_idx] = updated
        return updated

    @app.get(
        "/attendance/sessions",
        tags=["HRMS"],
        summary="List attendance sessions",
        description="List attendance sessions between start_date and end_date (demo).",
        operation_id="listAttendanceSessions",
        response_model=List[AttendanceSessionOut],
    )
    def list_sessions(
        start_date: str,
        end_date: str,
        authorization: Optional[str] = Header(default=None),
    ):
        """List sessions for current user (demo)."""
        u = _get_current_user(authorization)
        emp_id = str(u["employee_id"])
        _ = start_date, end_date  # demo ignores filtering; UI will show returned rows
        return [s for s in _attendance_sessions if s.employee_id == emp_id]

    # --- Audit ---

    class AuditLogOut(BaseModel):
        id: str
        org_id: str
        actor_user_id: Optional[str] = None
        actor_employee_id: Optional[str] = None
        action: str
        entity_type: str
        entity_id: Optional[str] = None
        ip: Optional[str] = None
        user_agent: Optional[str] = None
        metadata: Dict[str, object] = Field(default_factory=dict)
        created_at: str

    @app.get(
        "/audit/logs",
        tags=["HRMS"],
        summary="List audit logs",
        description="Return demo audit log entries (admin-only in UI; backend allows any authenticated demo user).",
        operation_id="listAuditLogs",
        response_model=List[AuditLogOut],
    )
    def list_audit_logs(
        limit: int = 200,
        authorization: Optional[str] = Header(default=None),
    ):
        """Return demo audit logs."""
        u = _get_current_user(authorization)
        now = _utcnow_iso()
        logs = [
            AuditLogOut(
                id="aud_1",
                org_id=str(u["org_id"]),
                actor_user_id=str(u["user_id"]),
                actor_employee_id=str(u["employee_id"]),
                action="login",
                entity_type="user",
                entity_id=str(u["user_id"]),
                ip=None,
                user_agent=None,
                metadata={"demo": True},
                created_at=now,
            )
        ]
        return logs[: max(0, limit)]

    # --- Payroll ---

    class PayrollCycleOut(BaseModel):
        id: str
        org_id: str
        code: str
        start_date: str
        end_date: str
        status: str
        created_at: str
        updated_at: str

    @app.get(
        "/payroll/cycles",
        tags=["HRMS"],
        summary="List payroll cycles",
        description="Return demo payroll cycle list.",
        operation_id="listPayrollCycles",
        response_model=List[PayrollCycleOut],
    )
    def list_payroll_cycles(authorization: Optional[str] = Header(default=None)):
        """Return demo payroll cycles."""
        u = _get_current_user(authorization)
        now = _utcnow_iso()
        today = date.today()
        start = today.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        return [
            PayrollCycleOut(
                id="pay_1",
                org_id=str(u["org_id"]),
                code=f"{start.strftime('%b').upper()}-{start.year}",
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                status="open",
                created_at=now,
                updated_at=now,
            )
        ]

    return app


# Uvicorn will import `app` by default.
app = create_app()
