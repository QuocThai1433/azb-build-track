import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# The app reads AZB_DB_PATH when azb_hub.db is first imported, so set it before anything else.
_TMP = tempfile.mkdtemp(prefix="azb_test_")
os.environ["AZB_DB_PATH"] = str(Path(_TMP) / "test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from azb_hub.main import app

    with TestClient(app, follow_redirects=False) as c:
        yield c
