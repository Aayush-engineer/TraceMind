import re
from typing import Any

class PIIRedactor:
    """Redacts PII from text before sending to TraceMind."""

    _PATTERNS = [
        (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), "[EMAIL]"),
        (re.compile(r'\b(\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'), "[PHONE]"),
        (re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'), "[CARD]"),
        (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), "[SSN]"),
        (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), "[IP]"),
        (re.compile(r'\b(sk-|pk-|tm_live_|ef_live_|Bearer\s)[A-Za-z0-9_\-]{20,}'), "[API_KEY]"),
        (re.compile(r'\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b'), "[JWT]"),
    ]

    def __init__(self, custom: list = None):
        self._patterns = list(self._PATTERNS)
        if custom:
            for pattern, replacement in custom:
                if isinstance(pattern, str):
                    pattern = re.compile(pattern)
                self._patterns.append((pattern, replacement))

    def redact(self, text: str) -> str:
        if not isinstance(text, str):
            return text
        for pattern, replacement in self._patterns:
            text = pattern.sub(replacement, text)
        return text

    def redact_dict(self, d: dict) -> dict:
        result = {}
        for k, v in d.items():
            if isinstance(v, str):
                result[k] = self.redact(v)
            elif isinstance(v, dict):
                result[k] = self.redact_dict(v)
            elif isinstance(v, list):
                result[k] = [self.redact(i) if isinstance(i, str) else i for i in v]
            else:
                result[k] = v
        return result