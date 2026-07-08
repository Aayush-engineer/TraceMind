from __future__ import annotations
from .client import TraceMind
import importlib.util
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def _detect_project_name() -> str:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output = True,
            text           = True,
            timeout        = 3,
        )
        if result.returncode == 0:
            url  = result.stdout.strip()
            # Handles both formats:
            # git@github.com:user/repo.git
            # https://github.com/user/repo.git
            name = url.split("/")[-1].replace(".git", "").strip()
            if name:
                return name
    except Exception:
        pass

    return os.path.basename(os.getcwd())


def _load_or_create_api_key(
    project_name: str,
    base_url:     str,
) -> tuple[str, str]:
    env_path = Path(".env")
    try:
        from dotenv import load_dotenv, set_key
        load_dotenv(env_path, override=False)
    except ImportError:
        _load_env_file_manually(env_path)

    api_key    = os.getenv("TRACEMIND_API_KEY",    "")
    project_id = os.getenv("TRACEMIND_PROJECT_ID", "")

    if api_key and project_id:
        return api_key, project_id

    try:
        import httpx
        resp = httpx.post(
            f"{base_url}/api/projects",
            json    = {
                "name":        project_name,
                "description": "Auto-created by tracemind.auto()",
            },
            timeout = 10,
        )
        resp.raise_for_status()
        data = resp.json()

        api_key    = data["api_key"]
        project_id = data["id"]

        _write_to_env(env_path, api_key, project_id)

        return api_key, project_id

    except Exception as exc:
        logger.debug("TraceMind: could not create project: %s", exc)
        return "", ""


def _load_env_file_manually(env_path: Path) -> None:
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


def _write_to_env(env_path: Path, api_key: str, project_id: str) -> None:
    try:
        from dotenv import set_key
        env_path.touch(exist_ok=True)
        set_key(str(env_path), "TRACEMIND_API_KEY",    api_key)
        set_key(str(env_path), "TRACEMIND_PROJECT_ID", project_id)
    except ImportError:
        try:
            env_path.touch(exist_ok=True)
            existing = env_path.read_text()
            lines    = existing.splitlines()

            lines = [l for l in lines
                     if not l.startswith("TRACEMIND_API_KEY=")
                     and not l.startswith("TRACEMIND_PROJECT_ID=")]

            lines.append(f"TRACEMIND_API_KEY={api_key}")
            lines.append(f"TRACEMIND_PROJECT_ID={project_id}")
            env_path.write_text("\n".join(lines) + "\n")
        except Exception as exc:
            logger.debug("TraceMind: could not write .env: %s", exc)
    except Exception as exc:
        logger.debug("TraceMind: could not write .env: %s", exc)

class _NoOpTraceMind:
    _dev_mode  = True
    _threshold = 7.0

    def trace(self, name: str = "llm_call"):
        def decorator(fn):
            import functools
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                t0     = time.time()
                result = fn(*args, **kwargs)
                ms     = round((time.time() - t0) * 1000)
                print(f"[tracemind:offline] {name} completed in {ms}ms (no server)")
                return result
            return wrapper
        return decorator

    def log(self, name: str = "", input: str = "", output: str = "",
            **kwargs) -> None:
        print(f"[tracemind:offline] {name}: {input[:50]}... → {output[:50]}...")

    def flush(self) -> None:
        pass

    def wrapOpenAI(self, client):
        return client

    def _buffer_span(self, **kwargs) -> None:
        pass


def _patch_openai(tm) -> None:
    try:
        import openai as _oai

        original_init = _oai.OpenAI.__init__

        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            try:
                wrapped   = tm.wrapOpenAI(self)
                self.chat = wrapped.chat
            except Exception as exc:
                logger.debug("TraceMind: OpenAI patch failed: %s", exc)

        _oai.OpenAI.__init__ = patched_init

    except Exception as exc:
        logger.debug("TraceMind: could not patch OpenAI: %s", exc)


def _patch_anthropic(tm) -> None:
    try:
        import anthropic as _ant

        original_init = _ant.Anthropic.__init__

        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            try:
                original_create = self.messages.create

                def traced_create(**call_kwargs):
                    t0  = time.time()
                    inp = str(call_kwargs.get("messages", ""))[:300]

                    result = original_create(**call_kwargs)

                    output = ""
                    if hasattr(result, "content") and result.content:
                        output = getattr(result.content[0], "text", str(result.content[0]))

                    tm._buffer_span(
                        name        = "anthropic.messages",
                        input_text  = inp,
                        output_text = output[:2000],
                        latency_ms  = round((time.time() - t0) * 1000, 1),
                        metadata    = {
                            "model":  call_kwargs.get("model", "unknown"),
                            "tokens": getattr(result, "usage", {}).get("output_tokens", 0)
                            if hasattr(getattr(result, "usage", None), "get") else 0,
                        },
                    )
                    return result

                self.messages.create = traced_create

            except Exception as exc:
                logger.debug("TraceMind: Anthropic message patch failed: %s", exc)

        _ant.Anthropic.__init__ = patched_init

    except Exception as exc:
        logger.debug("TraceMind: could not patch Anthropic: %s", exc)


def _patch_langchain(tm) -> None:
    try:
        import langchain_core.callbacks as _lc_callbacks

        class _AutoHandler(_lc_callbacks.BaseCallbackHandler):
            def on_llm_start(self, serialized, prompts, **kwargs):
                self._t0    = time.time()
                self._input = str(prompts[0])[:500] if prompts else ""

            def on_llm_end(self, response, **kwargs):
                output = ""
                try:
                    gen = response.generations
                    if gen and gen[0]:
                        output = gen[0][0].text if hasattr(gen[0][0], "text") else str(gen[0][0])
                except Exception:
                    pass

                tm._buffer_span(
                    name        = "langchain.llm",
                    input_text  = getattr(self, "_input", ""),
                    output_text = output[:2000],
                    latency_ms  = round((time.time() - getattr(self, "_t0", time.time())) * 1000, 1),
                )

            def on_llm_error(self, error, **kwargs):
                tm._buffer_span(
                    name        = "langchain.llm",
                    input_text  = getattr(self, "_input", ""),
                    output_text = "",
                    status      = "error",
                    error       = str(error)[:500],
                    latency_ms  = round((time.time() - getattr(self, "_t0", time.time())) * 1000, 1),
                )

        from langchain_core.callbacks import set_handler
        set_handler(_AutoHandler())

    except ImportError:
        try:
            from langchain.callbacks import get_callback_manager
            import langchain

            class _LegacyHandler:
                def on_llm_start(self, serialized, prompts, **kwargs):
                    self._t0    = time.time()
                    self._input = str(prompts[0])[:500] if prompts else ""

                def on_llm_end(self, response, **kwargs):
                    tm._buffer_span(
                        name        = "langchain.llm",
                        input_text  = getattr(self, "_input", ""),
                        output_text = str(response)[:500],
                        latency_ms  = round((time.time() - getattr(self, "_t0", time.time())) * 1000, 1),
                    )

            mgr = get_callback_manager()
            mgr.add_handler(_LegacyHandler())
        except Exception as exc:
            logger.debug("TraceMind: legacy LangChain patch failed: %s", exc)

    except Exception as exc:
        logger.debug("TraceMind: could not patch LangChain: %s", exc)


def _patch_groq(tm) -> None:
    try:
        import groq as _groq

        original_init = _groq.Groq.__init__

        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            try:
                original_create = self.chat.completions.create

                def traced_create(**call_kwargs):
                    t0  = time.time()
                    msgs = call_kwargs.get("messages", [])
                    inp  = str(msgs[-1].get("content", ""))[:300] if msgs else ""

                    result = original_create(**call_kwargs)

                    output = ""
                    try:
                        output = result.choices[0].message.content or ""
                    except Exception:
                        pass

                    tm._buffer_span(
                        name        = "groq.chat",
                        input_text  = inp,
                        output_text = output[:2000],
                        latency_ms  = round((time.time() - t0) * 1000, 1),
                        metadata    = {"model": call_kwargs.get("model", "unknown")},
                    )
                    return result

                self.chat.completions.create = traced_create
            except Exception as exc:
                logger.debug("TraceMind: Groq completions patch failed: %s", exc)

        _groq.Groq.__init__ = patched_init

    except Exception as exc:
        logger.debug("TraceMind: could not patch Groq: %s", exc)


def _enable_dev_mode(tm, threshold: float) -> None:
    original_buffer = tm._buffer_span

    RESET  = "\033[0m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    GRAY   = "\033[90m"
    BOLD   = "\033[1m"

    def dev_buffer_span(name: str = "", input_text: str = "",
                        output_text: str = "", **kwargs):
        original_buffer(name=name, input_text=input_text,
                        output_text=output_text, **kwargs)

        status = kwargs.get("status", "success")
        error  = kwargs.get("error", "")
        ms     = kwargs.get("latency_ms", 0)

        if status == "error":
            color  = RED
            symbol = "✗"
            note   = f"ERROR: {error[:60]}"
        else:
            symbol = "◈"
            color  = GRAY
            note   = f"{ms:.0f}ms → scoring in background..."

        inp_preview = (input_text[:60] + "…") if len(input_text) > 60 else input_text
        out_preview = (output_text[:60] + "…") if len(output_text) > 60 else output_text

        print(
            f"{color}{BOLD}[tracemind]{RESET} {symbol} {name}\n"
            f"  {GRAY}in:  {inp_preview}{RESET}\n"
            f"  {GRAY}out: {out_preview}{RESET}\n"
            f"  {GRAY}{note}{RESET}"
        )

    tm._buffer_span = dev_buffer_span


def auto(
    base_url:  str   = "https://tracemind.onrender.com",
    dev_mode:  Optional[bool] = None,
    threshold: float = 7.0,
):
    try:
        from .client import TraceMind
    except ImportError:
        return _NoOpTraceMind()

    project_name = _detect_project_name()

    api_key, project_id = _load_or_create_api_key(project_name, base_url)

    if dev_mode is None:
        env_val  = os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower()
        dev_mode = env_val in ("development", "dev", "local", "test", "")

    if not api_key:
        tm = _NoOpTraceMind()
        print(
            f"[tracemind] ⚠ Server unreachable — running in offline mode.\n"
            f"  Traces will print to terminal only.\n"
            f"  Start server: docker-compose up"
        )
    else:
        try:
            tm = TraceMind(
                api_key  = api_key,
                project  = project_name,
                base_url = base_url,
            )
            tm._dev_mode  = dev_mode
            tm._threshold = threshold
        except Exception as exc:
            logger.debug("TraceMind: client init failed: %s", exc)
            tm = _NoOpTraceMind()

    if dev_mode and not isinstance(tm, _NoOpTraceMind):
        try:
            _enable_dev_mode(tm, threshold)
        except Exception as exc:
            logger.debug("TraceMind: dev mode setup failed: %s", exc)

    patched: list[str] = []
    patches = [
        ("openai",    _patch_openai),
        ("anthropic", _patch_anthropic),
        ("groq",      _patch_groq),
        ("langchain", _patch_langchain),
    ]

    for lib_name, patch_fn in patches:
        if importlib.util.find_spec(lib_name) is not None:
            try:
                patch_fn(tm)
                patched.append(lib_name)
            except Exception as exc:
                logger.debug("TraceMind: %s patch raised: %s", lib_name, exc)

    try:
        import tracemind as _tm_module
        _tm_module._auto_instance = tm
    except Exception:
        pass

    mode_str = "dev" if dev_mode else "production"
    libs_str = ", ".join(patched) if patched else "none detected"
    offline  = isinstance(tm, _NoOpTraceMind)

    if not offline:
        print(
            f"[tracemind] ✓ Ready\n"
            f"  Project:   {project_name}\n"
            f"  Mode:      {mode_str}\n"
            f"  Libraries: {libs_str}\n"
            f"  Dashboard: {base_url.rstrip('/')}/project/{project_id}"
        )

    return tm