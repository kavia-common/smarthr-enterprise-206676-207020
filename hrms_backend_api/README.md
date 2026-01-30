# hrms_backend_api

FastAPI backend container for SmartHR AI.

## Endpoints

- `GET /health` — readiness/liveness endpoint (used by the platform to mark the container ready)

## Configuration (env vars)

- `PORT` (default `3001`)
- `HOST` or `UVICORN_HOST` (default `0.0.0.0`)
- `POSTGRES_URL` or `DATABASE_URL` — SQLAlchemy/psycopg compatible connection string
- CORS:
  - `ALLOWED_ORIGINS` or `CORS_ALLOW_ORIGINS` or `CORS_ORIGINS` (CSV)
  - `ALLOWED_METHODS` (CSV)
  - `ALLOWED_HEADERS` (CSV)
  - `CORS_MAX_AGE`

### Optional DB check in health

Set `HEALTHCHECK_DB=true` to have `/health` also attempt `SELECT 1` against the configured database.
Default is `false` so readiness does not fail if the DB is still starting.
