import os

import uvicorn

if __name__ == "__main__":
    host = os.getenv("UVICORN_HOST", os.getenv("HOST", "0.0.0.0"))
    port = int(os.getenv("PORT", "3001"))
    workers = int(os.getenv("UVICORN_WORKERS", "1"))

    uvicorn.run("app.main:app", host=host, port=port, workers=workers, reload=False)
