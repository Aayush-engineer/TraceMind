import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

_TEST_DB_DIR  = tempfile.mkdtemp(prefix="tracemind_test_")
_TEST_DB_PATH = Path(_TEST_DB_DIR) / f"test_{uuid.uuid4().hex[:8]}.db"

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("GROQ_API_KEY", "gsk_test_placeholder_not_real")

# repo layout: this file lives at <repo_root>/backend/tests/conftest.py
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "sdk" / "python"))


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    from backend.db.database import sync_engine
    from backend.db.models import Base

    Base.metadata.create_all(bind=sync_engine)
    yield
    Base.metadata.drop_all(bind=sync_engine)
    sync_engine.dispose()
    try:
        _TEST_DB_PATH.unlink(missing_ok=True)
        os.rmdir(_TEST_DB_DIR)
    except OSError:
        pass  # best-effort cleanup, never fail the test run over this


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app, raise_server_exceptions=False)