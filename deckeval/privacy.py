"""Redact identifiers that must not appear in logs or error strings."""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def public_error(exc: BaseException, limit: int = 300) -> str:
    """Return a short error string with emails and URLs removed."""
    detail = str(exc).strip()
    text = type(exc).__name__ if not detail else f"{type(exc).__name__}: {detail}"
    text = _EMAIL_RE.sub("[redacted-email]", text)
    text = _URL_RE.sub("[redacted-url]", text)
    return text[:limit]
