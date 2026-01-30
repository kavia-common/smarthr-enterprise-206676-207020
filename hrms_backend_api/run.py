import os
import subprocess
import sys

# Note: uvicorn is imported lazily after we ensure dependencies are available.
# This makes the container more resilient in environments where Python deps may
# not be preinstalled (common in preview/restart scenarios).


def _ensure_dependencies() -> None:
    """
    Ensure required Python dependencies are installed.

    The preview platform sometimes restarts containers in an environment where
    site-packages are not present. If importing FastAPI fails, we install the
    requirements at runtime (non-interactive) and proceed.

    This is intentionally minimal and safe:
    - Uses the pinned requirements.txt already in the repo.
    - Only triggers install when needed.
    """
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ModuleNotFoundError:
        # Best-effort runtime install.
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", "requirements.txt"]
        )


if __name__ == "__main__":
    _ensure_dependencies()

    import uvicorn  # noqa: E402

    host = os.getenv("UVICORN_HOST", os.getenv("HOST", "0.0.0.0"))
    port = int(os.getenv("PORT", "3001"))
    workers = int(os.getenv("UVICORN_WORKERS", "1"))

    uvicorn.run("app.main:app", host=host, port=port, workers=workers, reload=False)
