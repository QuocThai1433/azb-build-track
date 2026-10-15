import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# The app reads AZB_DB_PATH when azb_hub.db is first imported, so set it before anything else.
_TMP = tempfile.mkdtemp(prefix="azb_test_")
os.environ["AZB_DB_PATH"] = str(Path(_TMP) / "test.db")
ADMIN_PASSWORD = "Admin-test-123"
os.environ["AZB_ADMIN_PASSWORD"] = ADMIN_PASSWORD
os.environ["AZB_ADMIN_USERNAME"] = "admin"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from azb_hub.main import app

    with TestClient(app, follow_redirects=False) as c:
        r = c.post("/login", data={"username": "admin", "password": ADMIN_PASSWORD})
        assert r.status_code == 303, r.text[:200]
        yield c           # signed in as admin, so the existing tests run unchanged
