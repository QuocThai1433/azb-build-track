"""Entry point: ``python app.py`` starts AZB Project Hub on http://127.0.0.1:5000 (FastAPI + uvicorn)."""
import logging
import os
from pathlib import Path

import uvicorn


def load_dotenv(path: Path = Path(__file__).with_name(".env")) -> None:
    """Load KEY=VALUE lines from ``.env`` into os.environ without overriding variables already set."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_dotenv()

from azb_hub.main import app  # noqa: E402  (must import after .env is loaded)


class QuietAccessLogFilter(logging.Filter):
    """Hide noisy access-log lines: DevTools probes (/json...) and successful static-file loads.

    Debuggers and browser tools scan localhost ports for a remote-debugging endpoint (GET /json/version);
    the app correctly answers 404, but the lines clutter the log. Static files answered 200/304 are
    routine too. Real 404s/500s of the app, static files included, are still logged.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn.access args: (client_addr, method, full_path, http_version, status_code)
        args = record.args
        if isinstance(args, tuple) and len(args) >= 5:
            path, status = str(args[2]), args[4]
            if path == "/json" or path.startswith(("/json/", "/json?")):
                return False
            if path.startswith("/static/") and status in (200, 304):
                return False
        return True


if __name__ == "__main__":
    config = uvicorn.Config(app, host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), log_level="info")
    # uvicorn.Config sets up logging, so the filter is attached afterwards.
    logging.getLogger("uvicorn.access").addFilter(QuietAccessLogFilter())
    uvicorn.Server(config).run()
