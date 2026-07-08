import os
import sys
import json
import time
import pytest
import tempfile
import importlib
from pathlib import Path
from unittest.mock import patch, MagicMock, call


def _make_project_response(name: str = "test-project") -> dict:
    return {
        "id":      "abc123def456",
        "name":    name,
        "api_key": "ef_live_testkey1234567890",
    }


def _make_httpx_response(data: dict, status_code: int = 201) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


class TestDetectProjectName:

    def test_extracts_name_from_https_remote(self):
        from tracemind.auto import _detect_project_name
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="https://github.com/user/my-project.git\n",
            )
            assert _detect_project_name() == "my-project"

    def test_extracts_name_from_ssh_remote(self):
        from tracemind.auto import _detect_project_name
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="git@github.com:user/tracemind.git\n",
            )
            assert _detect_project_name() == "tracemind"

    def test_falls_back_to_directory_when_no_git(self):
        from tracemind.auto import _detect_project_name
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            with patch("os.getcwd", return_value="/home/user/my-llm-app"):
                result = _detect_project_name()
                assert result == "my-llm-app"

    def test_falls_back_to_directory_when_git_times_out(self):
        from tracemind.auto import _detect_project_name
        with patch("subprocess.run", side_effect=Exception("timeout")):
            with patch("os.getcwd", return_value="/projects/evalforge"):
                result = _detect_project_name()
                assert result == "evalforge"

    def test_handles_empty_git_output(self):
        from tracemind.auto import _detect_project_name
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="\n")
            with patch("os.getcwd", return_value="/projects/fallback-project"):
                result = _detect_project_name()
                assert result == "fallback-project"


class TestLoadOrCreateApiKey:

    def test_returns_existing_key_from_environment(self):
        from tracemind.auto import _load_or_create_api_key
        with patch.dict(os.environ, {
            "TRACEMIND_API_KEY":    "ef_live_existing",
            "TRACEMIND_PROJECT_ID": "proj_existing",
        }):
            api_key, project_id = _load_or_create_api_key("test", "http://localhost:8000")
            assert api_key    == "ef_live_existing"
            assert project_id == "proj_existing"

    def test_creates_project_and_writes_env_when_no_key(self, tmp_path):
        from tracemind.auto import _load_or_create_api_key

        # Ensure env vars not set
        env = {k: v for k, v in os.environ.items()
               if k not in ("TRACEMIND_API_KEY", "TRACEMIND_PROJECT_ID")}

        project_data = _make_project_response("new-project")

        with patch.dict(os.environ, env, clear=True):
            with patch("httpx.post", return_value=_make_httpx_response(project_data)):
                with patch("tracemind.auto.Path", return_value=tmp_path / ".env"):
                    # Mock dotenv functions
                    with patch("tracemind.auto._write_to_env") as mock_write:
                        api_key, project_id = _load_or_create_api_key(
                            "new-project", "http://localhost:8000"
                        )

        assert api_key    == project_data["api_key"]
        assert project_id == project_data["id"]

    def test_writes_env_file(self, tmp_path):
        """Verifies (a): .env is written with api_key and project_id."""
        from tracemind.auto import _write_to_env

        env_path = tmp_path / ".env"
        _write_to_env.__wrapped__ if hasattr(_write_to_env, "__wrapped__") else None

        # Use the manual fallback (no dotenv dependency in test)
        with patch("tracemind.auto.Path") as mock_path_cls:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = ""
            mock_path_cls.return_value = mock_path

            # Actual write using tmp file
            env_path.touch()
            _write_to_env(env_path, "ef_live_testkey", "proj_abc123")

        content = env_path.read_text()
        assert "TRACEMIND_API_KEY" in content and "ef_live_testkey" in content
        assert "TRACEMIND_PROJECT_ID" in content and "proj_abc123" in content

    def test_returns_empty_strings_when_server_unreachable(self):
        from tracemind.auto import _load_or_create_api_key
        env = {k: v for k, v in os.environ.items()
               if k not in ("TRACEMIND_API_KEY", "TRACEMIND_PROJECT_ID")}
        with patch.dict(os.environ, env, clear=True):
            with patch("httpx.post", side_effect=Exception("connection refused")):
                api_key, project_id = _load_or_create_api_key(
                    "test", "http://localhost:8000"
                )
        assert api_key    == ""
        assert project_id == ""


class TestAutoFunction:

    def _mock_auto_deps(self, project_name="test-repo", api_key="ef_live_test",
                        project_id="proj_test"):
        """Returns a context manager that mocks all auto() dependencies."""
        import contextlib

        @contextlib.contextmanager
        def ctx():
            with patch("tracemind.auto._detect_project_name", return_value=project_name), \
                 patch("tracemind.auto._load_or_create_api_key",
                       return_value=(api_key, project_id)), \
                 patch("tracemind.auto._patch_openai"), \
                 patch("tracemind.auto._patch_anthropic"), \
                 patch("tracemind.auto._patch_groq"), \
                 patch("tracemind.auto._patch_langchain"), \
                 patch("importlib.util.find_spec", return_value=None):
                yield
        return ctx()

    def test_returns_tracemind_instance(self):
        """Verifies (c): auto() returns a TraceMind instance."""
        from tracemind.auto import auto
        from tracemind.client import TraceMind

        with self._mock_auto_deps():
            with patch("tracemind.auto.TraceMind") as mock_tm_cls:
                mock_instance       = MagicMock()
                mock_tm_cls.return_value = mock_instance
                result = auto(base_url="http://localhost:8000")

        from tracemind.client import TraceMind
        assert isinstance(result, TraceMind)

    def test_returns_noop_when_server_unreachable(self):
        """Verifies (d): falls back to _NoOpTraceMind when server unreachable."""
        from tracemind.auto import auto, _NoOpTraceMind

        with patch("tracemind.auto._detect_project_name", return_value="test"):
            with patch("tracemind.auto._load_or_create_api_key", return_value=("", "")):
                with patch("importlib.util.find_spec", return_value=None):
                    result = auto(base_url="http://localhost:8000")

        assert isinstance(result, _NoOpTraceMind)

    def test_noop_never_raises(self):
        """_NoOpTraceMind must not raise on any method call."""
        from tracemind.auto import _NoOpTraceMind
        noop = _NoOpTraceMind()

        # None of these should raise
        noop.trace("test")(lambda: "ok")()
        noop.log(name="test", input="q", output="a")
        noop.flush()
        noop._buffer_span(name="x", input_text="q", output_text="a")

    def test_auto_never_raises_on_bad_url(self):
        """auto() must NEVER raise — even with completely broken inputs."""
        from tracemind.auto import auto

        # Should not raise even with garbage URL
        try:
            result = auto(base_url="http://definitely-does-not-exist-12345.invalid")
        except Exception as exc:
            pytest.fail(f"auto() raised an exception: {exc}")

    def test_dev_mode_detected_from_environment_variable(self):
        """Verifies (e): dev mode auto-detected from ENVIRONMENT env var."""
        from tracemind.auto import auto

        with self._mock_auto_deps():
            with patch("tracemind.auto.TraceMind") as mock_tm_cls:
                mock_tm_cls.return_value = MagicMock()
                with patch("tracemind.auto._enable_dev_mode") as mock_dev:
                    with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
                        auto(base_url="http://localhost:8000", dev_mode=None)
                    mock_dev.assert_called_once()

    def test_dev_mode_disabled_in_production(self):
        """dev_mode=False when ENVIRONMENT=production."""
        from tracemind.auto import auto

        with self._mock_auto_deps():
            with patch("tracemind.auto.TraceMind") as mock_tm_cls:
                mock_tm_cls.return_value = MagicMock()
                with patch("tracemind.auto._enable_dev_mode") as mock_dev:
                    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                        auto(base_url="http://localhost:8000", dev_mode=None)
                    mock_dev.assert_not_called()

    def test_stores_singleton_on_module(self):
        """auto() stores instance as tracemind._auto_instance."""
        from tracemind.auto import auto
        import tracemind

        with self._mock_auto_deps():
            with patch("tracemind.auto.TraceMind") as mock_tm_cls:
                instance = MagicMock()
                mock_tm_cls.return_value = instance
                auto(base_url="http://localhost:8000")

        from tracemind.client import TraceMind
        assert isinstance(tracemind._auto_instance, TraceMind)
        assert tracemind._auto_instance is not None


class TestOpenAIPatch:

    def test_openai_is_patched_when_installed(self):
        """Verifies (b): OpenAI is monkey-patched after auto()."""
        from tracemind.auto import _patch_openai

        # Create a mock OpenAI class
        mock_openai_module = MagicMock()
        mock_openai_class  = MagicMock()

        # Store original __init__
        original_init = mock_openai_class.__init__
        mock_openai_module.OpenAI = mock_openai_class

        mock_tm = MagicMock()
        mock_tm.wrapOpenAI.return_value = mock_openai_class

        with patch.dict(sys.modules, {"openai": mock_openai_module}):
            _patch_openai(mock_tm)

        # __init__ should have been replaced
        assert mock_openai_class.__init__ is not original_init

    def test_patch_openai_silent_on_import_error(self):
        """OpenAI patch must not raise if openai not installed."""
        from tracemind.auto import _patch_openai

        mock_tm = MagicMock()
        with patch.dict(sys.modules, {"openai": None}):
            # Should not raise
            try:
                _patch_openai(mock_tm)
            except Exception as exc:
                pytest.fail(f"_patch_openai raised: {exc}")

    def test_patch_openai_silent_on_wrap_failure(self):
        """OpenAI patch must not raise if wrapOpenAI fails."""
        from tracemind.auto import _patch_openai
        mock_tm = MagicMock()
        mock_tm.wrapOpenAI.side_effect = RuntimeError("wrap failed")

        import types
        mock_openai = types.ModuleType("openai")

        class FakeOpenAI:
            def __init__(self, *a, **kw):
                pass

        mock_openai.OpenAI = FakeOpenAI

        with patch.dict(sys.modules, {"openai": mock_openai}):
            # _patch_openai should not raise even when wrapOpenAI fails
            try:
                result = _patch_openai(mock_tm)
                # Try instantiating the patched class — should not raise
                obj = FakeOpenAI()
            except Exception as exc:
                pytest.fail(f"_patch_openai raised unexpectedly: {exc}")


class TestLibraryDetection:

    def test_patches_only_installed_libraries(self):
        """Only detected libraries should be patched."""
        from tracemind.auto import auto

        with patch("tracemind.auto._detect_project_name", return_value="test"), \
             patch("tracemind.auto._load_or_create_api_key",
                   return_value=("ef_live_key", "proj_id")), \
             patch("tracemind.auto.TraceMind") as mock_tm_cls, \
             patch("tracemind.auto._patch_openai")    as mock_oai, \
             patch("tracemind.auto._patch_anthropic") as mock_ant, \
             patch("tracemind.auto._patch_groq")      as mock_grq, \
             patch("tracemind.auto._patch_langchain") as mock_lc:

            mock_tm_cls.return_value = MagicMock()

            # Only openai is "installed"
            def fake_find_spec(name):
                return MagicMock() if name == "openai" else None

            with patch("importlib.util.find_spec", side_effect=fake_find_spec):
                auto(base_url="http://localhost:8000")

        mock_oai.assert_called_once()
        mock_ant.assert_not_called()
        mock_grq.assert_not_called()
        mock_lc.assert_not_called()

    def test_no_libraries_is_not_an_error(self):
        """auto() works fine even if no LLM libraries are installed."""
        from tracemind.auto import auto

        with patch("tracemind.auto._detect_project_name", return_value="test"), \
             patch("tracemind.auto._load_or_create_api_key",
                   return_value=("ef_live_key", "proj_id")), \
             patch("tracemind.auto.TraceMind") as mock_tm_cls, \
             patch("importlib.util.find_spec", return_value=None):

            mock_tm_cls.return_value = MagicMock()
            try:
                result = auto(base_url="http://localhost:8000")
            except Exception as exc:
                pytest.fail(f"auto() raised with no libraries: {exc}")


class TestEndToEnd:

    def test_full_happy_path(self, tmp_path, monkeypatch):
        from tracemind.auto import auto

        env_file = tmp_path / ".env"

        project_data = {
            "id":      "proj_abc",
            "name":    "my-repo",
            "api_key": "ef_live_abc123",
        }

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = project_data
        mock_response.raise_for_status.return_value = None

        monkeypatch.delenv("TRACEMIND_API_KEY",    raising=False)
        monkeypatch.delenv("TRACEMIND_PROJECT_ID", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")

        with patch("subprocess.run") as mock_git, \
             patch("httpx.post",           return_value=mock_response), \
             patch("tracemind.auto.TraceMind") as mock_tm_cls, \
             patch("importlib.util.find_spec", return_value=None), \
             patch("tracemind.auto.Path",      return_value=env_file):

            mock_git.return_value = MagicMock(
                returncode=0,
                stdout="https://github.com/user/my-repo.git\n",
            )
            mock_instance = MagicMock()
            mock_tm_cls.return_value = mock_instance

            result = auto(base_url="http://localhost:8000")

        # Returns a real TraceMind instance with correct config
        from tracemind.client import TraceMind
        assert isinstance(result, TraceMind)
        assert result.project == "my-repo"
        assert result.api_key == "ef_live_abc123"
        assert result.base_url == "http://localhost:8000"