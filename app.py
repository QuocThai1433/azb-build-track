"""Entry point: ``python app.py`` starts AZB Project Hub on http://127.0.0.1:5000 (FastAPI + uvicorn)."""
import os

import uvicorn

from azb_hub.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), log_level="info")
