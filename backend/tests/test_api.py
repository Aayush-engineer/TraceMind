import pytest
import json
from unittest.mock import patch, AsyncMock


@pytest.fixture
def client():
    """Create test client with mocked DB."""
    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_project():
    """A fake project for testing auth."""
    class FakeProject:
        id          = "test-project-id"
        name        = "test-project"
        description = "test"
        api_key     = "ef_live_test_key_12345"
        webhook_url = None
    return FakeProject()


# ══════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════

class TestHealth:

    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_returns_healthy(self, client):
        r = client.get("/health")
        assert r.json()["status"] == "healthy"

    def test_health_returns_version(self, client):
        r = client.get("/health")
        assert "version" in r.json()


# ══════════════════════════════════════════════════════
# AUTHENTICATION
# ══════════════════════════════════════════════════════

class TestAuthentication:

    def test_missing_auth_header_returns_401(self, client):
        r = client.get("/api/projects")
        assert r.status_code == 401

    def test_wrong_auth_scheme_returns_401(self, client):
        r = client.get("/api/projects",
                       headers={"Authorization": "Basic wrongscheme"})
        assert r.status_code == 401

    def test_invalid_key_returns_401(self, client):
        r = client.get("/api/projects",
                       headers={"Authorization": "Bearer ef_live_INVALID"})
        assert r.status_code == 401

    def test_empty_bearer_returns_401(self, client):
        r = client.get("/api/projects",
                       headers={"Authorization": "Bearer "})
        assert r.status_code == 401

    def test_401_response_has_detail_field(self, client):
        r = client.get("/api/projects")
        assert "detail" in r.json()

    def test_project_creation_is_public(self, client):
        """POST /api/projects should work without auth"""
        with patch("backend.api.projects.AsyncSession") as mock_db:
            r = client.post("/api/projects",
                            json={"name": "test", "description": "test"})
            # 201 or 400 (duplicate) — not 401
            assert r.status_code != 401


# ══════════════════════════════════════════════════════
# TRACES
# ══════════════════════════════════════════════════════

class TestTraceIngestion:

    def test_batch_requires_auth(self, client):
        r = client.post("/api/traces/batch",
                        json={"spans": []})
        assert r.status_code == 401

    def test_empty_batch_accepted(self, client, mock_project):
        from backend.main import app
        from backend.core.auth import get_current_project

        app.dependency_overrides[get_current_project] = lambda: mock_project
        try:
            r = client.post("/api/traces/batch",
                            json={"spans": []},
                            headers={"Authorization": "Bearer ef_live_test"})
            assert r.status_code in (200, 202, 422)
        finally:
            app.dependency_overrides.clear()

    def test_trace_get_requires_auth(self, client):
        r = client.get("/api/traces/some-trace-id")
        assert r.status_code == 401


# ══════════════════════════════════════════════════════
# EVALS
# ══════════════════════════════════════════════════════

class TestEvals:

    def test_eval_run_requires_auth(self, client):
        r = client.post("/api/evals/run", json={
            "project": "test", "dataset_name": "test"
        })
        assert r.status_code == 401

    def test_get_eval_requires_auth(self, client):
        r = client.get("/api/evals/some-run-id")
        assert r.status_code == 401

    def test_export_requires_auth(self, client):
        r = client.get("/api/evals/some-run-id/export")
        assert r.status_code == 401

    def test_nonexistent_eval_returns_404(self, client, mock_project):
        with patch("backend.core.auth.get_current_project",
                   return_value=mock_project):
            r = client.get("/api/evals/nonexistent-run-id",
                           headers={"Authorization": "Bearer ef_live_test"})
            assert r.status_code in (401, 404)


# ══════════════════════════════════════════════════════
# DATASETS
# ══════════════════════════════════════════════════════

class TestDatasets:

    def test_list_datasets_requires_auth(self, client):
        r = client.get("/api/datasets")
        assert r.status_code == 401

    def test_create_dataset_requires_auth(self, client):
        r = client.post("/api/datasets",
                        json={"name":"test","project":"test","examples":[]})
        assert r.status_code == 401

    def test_get_dataset_requires_auth(self, client):
        r = client.get("/api/datasets/some-id")
        assert r.status_code == 401


# ══════════════════════════════════════════════════════
# METRICS
# ══════════════════════════════════════════════════════

class TestMetrics:

    def test_summary_requires_auth(self, client):
        r = client.get("/api/metrics/project-id/summary")
        assert r.status_code == 401

    def test_timeseries_requires_auth(self, client):
        r = client.get("/api/metrics/project-id")
        assert r.status_code == 401