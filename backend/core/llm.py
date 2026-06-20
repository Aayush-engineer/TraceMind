import os
import logging
import time
import hashlib
from abc import ABC, abstractmethod
from typing import Optional, Any

logger = logging.getLogger(__name__)

MODEL_MAP: dict[str, dict[str, str]] = {
    "groq": {
        "fast":  os.getenv("GROQ_FAST_MODEL",  "llama-3.1-8b-instant"),
        "smart": os.getenv("GROQ_SMART_MODEL", "llama-3.3-70b-versatile"),
    },
    "openai": {
        "fast":  os.getenv("OPENAI_FAST_MODEL",  "gpt-4o-mini"),
        "smart": os.getenv("OPENAI_SMART_MODEL", "gpt-4o"),
    },
    "anthropic": {
        "fast":  os.getenv("ANTHROPIC_FAST_MODEL",  "claude-haiku-4-5-20251001"),
        "smart": os.getenv("ANTHROPIC_SMART_MODEL", "claude-sonnet-4-6"),
    },
}


class _Provider(ABC):
    name: str

    @abstractmethod
    def complete(self, messages: list[dict], system: str,
                 model: str, max_tokens: int, json_mode: bool) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...


class _GroqProvider(_Provider):
    name = "groq"
    def __init__(self) -> None:
        self._client: Any = None
    def is_available(self) -> bool:
        return bool(os.getenv("GROQ_API_KEY"))
    def _get_client(self):
        if self._client is None:
            import groq
            self._client = groq.Groq(api_key=os.getenv("GROQ_API_KEY"))
        return self._client
    def complete(self, messages, system, model, max_tokens, json_mode) -> str:
        client = self._get_client()
        model_name = MODEL_MAP["groq"].get(model, model)
        all_msgs = ([{"role": "system", "content": system}] + messages) if system else messages
        kwargs: dict = {"model": model_name, "messages": all_msgs, "max_tokens": max_tokens}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""


class _OpenAIProvider(_Provider):
    name = "openai"
    def __init__(self) -> None:
        self._client: Any = None
    def is_available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))
    def _get_client(self):
        if self._client is None:
            import openai
            self._client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return self._client
    def complete(self, messages, system, model, max_tokens, json_mode) -> str:
        client = self._get_client()
        model_name = MODEL_MAP["openai"].get(model, model)
        all_msgs = ([{"role": "system", "content": system}] + messages) if system else messages
        kwargs: dict = {"model": model_name, "messages": all_msgs, "max_tokens": max_tokens}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""


class _AnthropicProvider(_Provider):
    name = "anthropic"
    def __init__(self) -> None:
        self._client: Any = None
    def is_available(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        return self._client
    def complete(self, messages, system, model, max_tokens, json_mode) -> str:
        client = self._get_client()
        model_name = MODEL_MAP["anthropic"].get(model, model)
        kwargs: dict = {"model": model_name, "messages": messages, "max_tokens": max_tokens}
        if system:
            kwargs["system"] = system
        resp = client.messages.create(**kwargs)
        content = resp.content[0]
        return content.text if hasattr(content, "text") else ""


class _CircuitBreaker:
    def __init__(self, max_failures: int = 3, reset_timeout: float = 60.0) -> None:
        self.max_failures  = max_failures
        self.reset_timeout = reset_timeout
        self._failures     = 0
        self._opened_at: Optional[float] = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.time() - self._opened_at > self.reset_timeout:
            self._opened_at = None
            self._failures  = 0
            return False
        return True

    def record_success(self) -> None:
        self._failures  = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.max_failures:
            self._opened_at = time.time()
            logger.warning("Circuit breaker opened after %d failures", self._failures)


class _ProviderChain:
    MAX_RETRIES = 2

    def __init__(self) -> None:
        primary = os.getenv("LLM_PROVIDER", "groq").lower()
        all_providers: list[_Provider] = [_GroqProvider(), _OpenAIProvider(), _AnthropicProvider()]
        available = [p for p in all_providers if p.is_available()]
        available.sort(key=lambda p: (0 if p.name == primary else 1))
        if not available:
            raise RuntimeError("No LLM provider configured. Set GROQ_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY.")
        self._providers = available
        self._breakers  = {p.name: _CircuitBreaker() for p in available}
        logger.info("LLM provider chain: %s", " → ".join(p.name for p in available))

    def complete(self, messages: list[dict], system: str = "", model: str = "fast",
                 max_tokens: int = 500, json_mode: bool = False) -> str:
        last_error: Optional[Exception] = None
        for provider in self._providers:
            breaker = self._breakers[provider.name]
            if breaker.is_open:
                continue
            for attempt in range(self.MAX_RETRIES):
                try:
                    result = provider.complete(messages, system, model, max_tokens, json_mode)
                    breaker.record_success()
                    return result
                except Exception as exc:
                    last_error = exc
                    breaker.record_failure()
                    logger.warning("Provider %s attempt %d failed: %s", provider.name, attempt + 1, exc)
                    if attempt < self.MAX_RETRIES - 1:
                        time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")


_chain: Optional[_ProviderChain] = None

def _get_chain() -> _ProviderChain:
    global _chain
    if _chain is None:
        _chain = _ProviderChain()
    return _chain


def chat(messages: list[dict], system: str = "", model: str = "fast",
         max_tokens: int = 500, json_mode: bool = False) -> str:
    return _get_chain().complete(messages=messages, system=system, model=model,
                                  max_tokens=max_tokens, json_mode=json_mode)



_embed_model = None
_embedding_cache: dict[str, list[float]] = {}
_MAX_CACHE = 500


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading sentence-transformers model...")
        _embed_model = SentenceTransformer(os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2"))
    return _embed_model


def embed(texts: list[str]) -> list[list[float]]:
    model = _get_embed_model()
    result: list[Optional[list[float]]] = [None] * len(texts)
    to_compute: list[str] = []
    compute_idx: list[int] = []

    for i, text in enumerate(texts):
        key = hashlib.md5(text.encode()).hexdigest()
        if key in _embedding_cache:
            result[i] = _embedding_cache[key]
        else:
            to_compute.append(text)
            compute_idx.append(i)

    if to_compute:
        computed = model.encode(to_compute, show_progress_bar=False, batch_size=32).tolist()
        for idx, embedding, text in zip(compute_idx, computed, to_compute):
            key = hashlib.md5(text.encode()).hexdigest()
            result[idx] = embedding
            _embedding_cache[key] = embedding
            if len(_embedding_cache) > _MAX_CACHE:
                del _embedding_cache[next(iter(_embedding_cache))]

    return [r for r in result if r is not None]