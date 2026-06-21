import sys
import os
import warnings
import tempfile
import pytest

sdk_path = os.path.join(os.path.dirname(__file__), "..", "..", "sdk", "python")
sys.path.insert(0, os.path.abspath(sdk_path))

_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "tracemind_test.db")
if os.path.exists(_TEST_DB_PATH):
    os.remove(_TEST_DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"


@pytest.fixture(autouse=True)
def silence_async_warnings():
    warnings.filterwarnings(
        "ignore",
        message="coroutine.*was never awaited",
        category=RuntimeWarning,
    )
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app) as c:   
        yield c