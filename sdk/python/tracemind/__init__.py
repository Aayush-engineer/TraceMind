"""
TraceMind SDK — LLM quality monitoring.

Quick start (zero-config):
    import tracemind
    tracemind.auto()

    from openai import OpenAI
    client = OpenAI()
    client.chat.completions.create(...)  # traced automatically
"""

__version__ = "0.3.0"
__author__  = "Aayush Kumar"
__license__ = "MIT"

from .client import TraceMind
from .auto   import auto, _NoOpTraceMind

# Optional — only if response_control.py exists
try:
    from .response_control import (
        HallucinationPolicy,
        HallucinationEvent,
        HallucinationBlocked,
    )
except ImportError:
    pass

# Optional — only if llamaindex is installed
try:
    from .integrations.llamaindex import TraceMindLlamaIndexObserver
except ImportError:
    TraceMindLlamaIndexObserver = None

# Optional — only if dspy is installed
try:
    from .integrations.dspy import TraceMindDSPyCallback, patch_dspy
except ImportError:
    TraceMindDSPyCallback = None
    patch_dspy = None

# Module-level singleton — set by auto()
_auto_instance = None

__all__ = [
    "TraceMind",
    "auto",
    "_NoOpTraceMind",
    "_auto_instance",
    "TraceMindLlamaIndexObserver",
    "TraceMindDSPyCallback",
    "patch_dspy",
]