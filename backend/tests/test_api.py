import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app, raise_server_exceptions=False)


# ══════════════════════════════════════════════════
# Health — 3 tests
# ══════════════════════════════════════════════════

class TestHealth:

    def test_returns_200(self, client):
        assert client.get("/health").status_code == 200

    def test_returns_healthy_status(self, client):
        assert client.get("/health").json()["status"] == "healthy"

    def test_returns_version_field(self, client):
        assert "version" in client.get("/health").json()


# ══════════════════════════════════════════════════
# Authentication — 7 tests
# ══════════════════════════════════════════════════

class TestAuthentication:

    def test_no_header_returns_401(self, client):
        assert client.get("/api/projects").status_code == 401

    def test_wrong_scheme_returns_401(self, client):
        r = client.get("/api/projects",
                       headers={"Authorization": "Basic wrongscheme"})
        assert r.status_code == 401

    def test_invalid_key_returns_401(self, client):
        r = client.get("/api/projects",
                       headers={"Authorization": "Bearer ef_live_INVALID_KEY"})
        assert r.status_code == 401

    def test_empty_bearer_returns_401(self, client):
        r = client.get("/api/projects",
                       headers={"Authorization": "Bearer "})
        assert r.status_code == 401

    def test_401_has_detail_field(self, client):
        r = client.get("/api/projects")
        assert "detail" in r.json()

    def test_401_detail_mentions_authorization(self, client):
        r = client.get("/api/projects")
        assert "Authorization" in r.json()["detail"] or "header" in r.json()["detail"].lower()

    def test_project_creation_is_public_no_auth_needed(self, client):
        """POST /api/projects must work without auth for bootstrapping."""
        r = client.post("/api/projects",
                        json={"name": "__test_public__", "description": "test"})
        assert r.status_code not in (401, 403)


# ══════════════════════════════════════════════════
# Traces — 3 tests
# ══════════════════════════════════════════════════

class TestTraces:

    def test_batch_without_auth_returns_401(self, client):
        r = client.post("/api/traces/batch", json={"spans": []})
        assert r.status_code == 401

    def test_get_trace_without_auth_returns_401(self, client):
        assert client.get("/api/traces/some-trace-id").status_code == 401

    def test_project_spans_without_auth_returns_401(self, client):
        assert client.get("/api/traces/project/some-id").status_code == 401


# ══════════════════════════════════════════════════
# Evals — 4 tests
# ══════════════════════════════════════════════════

class TestEvals:

    def test_run_without_auth_returns_401(self, client):
        r = client.post("/api/evals/run",
                        json={"project":"test","dataset_name":"test"})
        assert r.status_code == 401

    def test_get_eval_without_auth_returns_401(self, client):
        assert client.get("/api/evals/some-run-id").status_code == 401

    def test_export_without_auth_returns_401(self, client):
        assert client.get("/api/evals/some-run-id/export").status_code == 401

    def test_nonexistent_eval_returns_404_or_401(self, client):
        r = client.get("/api/evals/this-does-not-exist-xyz",
                       headers={"Authorization": "Bearer bad_key"})
        assert r.status_code in (401, 404)


# ══════════════════════════════════════════════════
# Datasets — 4 tests
# ══════════════════════════════════════════════════

class TestDatasets:

    def test_list_without_auth_returns_401(self, client):
        assert client.get("/api/datasets").status_code == 401

    def test_create_without_auth_returns_401(self, client):
        r = client.post("/api/datasets",
                        json={"name":"test","project":"test","examples":[]})
        assert r.status_code == 401

    def test_get_by_id_without_auth_returns_401(self, client):
        assert client.get("/api/datasets/some-id").status_code == 401

    def test_delete_without_auth_returns_401(self, client):
        assert client.delete("/api/datasets/some-id").status_code == 401

