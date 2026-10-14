"""Entry point: ``python app.py`` starts AZB Project Hub on http://127.0.0.1:5000 (FastAPI + uvicorn)."""
import logging
import os

import uvicorn

from azb_hub.main import app


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
