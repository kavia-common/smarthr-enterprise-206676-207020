import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _ensure_import_path() -> None:
    """
    Ensure this project root is importable regardless of the process working directory.

    Some hosting platforms start the process with a working directory other than the
    container WORKDIR (e.g. `/`). In that case, importing `app.main` would fail and
    uvicorn would never bind to the port, causing readiness timeouts.

    We defensively add the directory containing this file (expected `/app`) to
    `sys.path` so `import app` always works.
    """
    project_root = str(Path(__file__).resolve().parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


# PUBLIC_INTERFACE
def main() -> None:
    """
    Entrypoint for running the FastAPI app via Uvicorn.

    This is used by the container CMD (`python run.py`) and is intentionally
    deterministic:
    - No runtime dependency installation (avoids slow/failed readiness).
    - Loads environment variables from a local `.env` if present.
    - Binds to HOST/PORT (defaults: 0.0.0.0:3001) so the platform can probe
      `/healthz` successfully.
    """
    load_dotenv(override=False)

    import uvicorn  # imported after dotenv so env is available

    host = os.getenv("UVICORN_HOST", os.getenv("HOST", "0.0.0.0"))
    port = int(os.getenv("PORT", "3001"))

    # Default to a single worker for preview/readiness stability.
    workers = int(os.getenv("UVICORN_WORKERS", "1"))

    uvicorn.run("app.main:app", host=host, port=port, workers=workers, reload=False)


if __name__ == "__main__":
    main()
