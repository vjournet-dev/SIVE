"""Authentication domain facade."""

from __future__ import annotations

from .browser import crawl_docs_with_playwright_session
from .session import (
    AuthConfig,
    AuthenticationRequiredError,
    AuthSession,
    capture_authenticated_cookies,
    capture_authenticated_session,
)

__all__ = [
    "AuthConfig",
    "AuthSession",
    "AuthenticationRequiredError",
    "capture_authenticated_cookies",
    "capture_authenticated_session",
    "crawl_docs_with_playwright_session",
]
