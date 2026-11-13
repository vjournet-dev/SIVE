from __future__ import annotations

import json
import logging
import time
from base64 import b64encode
from collections.abc import Iterable
from typing import Any, TypedDict
from urllib.parse import parse_qs, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)

_AUTH_REQUIRED_STATUS_CODES = {401, 407}
_LOGIN_URL_MARKERS = (
    "login",
    "signin",
    "sign-in",
    "adfs",
    "saml",
)
_LOGIN_HTML_MARKERS = (
    'type="password"',
    'name="password"',
    "sign in",
)
_PROTECTED_SHELL_HTML_MARKERS = (
    "sso",
    "oauth",
    "openid",
    "saml",
    "adfs",
    "auth0",
    "okta",
    "keycloak",
)
_LOGIN_TITLE_MARKERS = (
    "sign in",
    "log in",
    "login",
    "single sign-on",
    "access denied",
    "authentication required",
)


class AuthenticationRequiredError(RuntimeError):
    def __init__(self, message: str, *, login_url: str | None = None) -> None:
        super().__init__(message)
        self.login_url = login_url


class AuthSession(TypedDict, total=False):
    cookies: dict[str, str]
    headers: dict[str, str]
    storage_state: dict[str, Any]


class AuthConfig(TypedDict, total=False):
    type: str
    login_url: str
    username: str
    password: str
    selectors: dict[str, str]
    cookies: Any
    token: str
    token_type: str
    headers: dict[str, str]


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    cleaned = parsed._replace(fragment="", query="")
    return urlunparse(cleaned)


def _get_sync_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for interactive authentication.") from exc

    return sync_playwright


def _build_playwright_cookie_entries(cookies: dict[str, str], allowed_host: str) -> list[dict[str, str]]:
    origin = f"https://{allowed_host}"
    entries: list[dict[str, str]] = []
    for key, value in cookies.items():
        name = str(key).strip()
        if not name:
            continue
        entries.append(
            {
                "name": name,
                "value": str(value),
                "url": origin,
            }
        )
    return entries


def _inject_cookies_into_context(context: Any, cookies: dict[str, str], allowed_host: str) -> None:
    entries = _build_playwright_cookie_entries(cookies, allowed_host)
    if not entries:
        return

    try:
        context.add_cookies(entries)
    except Exception:  # noqa: BLE001 - Playwright cookie APIs vary by cookie shape/domain handling
        fallback_entries = [
            {
                "name": item["name"],
                "value": item["value"],
                "domain": allowed_host,
                "path": "/",
            }
            for item in entries
        ]
        context.add_cookies(fallback_entries)


def _extract_storage_state(context: Any) -> dict[str, Any]:
    try:
        raw = context.storage_state()
    except Exception:  # noqa: BLE001 - storage_state may fail in restricted browser contexts
        return {}

    return raw if isinstance(raw, dict) else {}


def _looks_like_login_url(url: str) -> bool:
    parsed = urlparse(url or "")
    lowered = parsed.path.lower()
    segments = [segment for segment in lowered.split("/") if segment]
    if any(segment in _LOGIN_URL_MARKERS for segment in segments):
        return True

    query = {str(key).lower(): values for key, values in parse_qs(parsed.query).items()}
    if any(key in query for key in ("samlrequest", "samlresponse", "wreply", "wa")):
        return True

    # OAuth/OIDC authorize endpoints are login-like, unlike generic docs pages mentioning oauth.
    return lowered.endswith("/authorize") and any(token in lowered for token in ("oauth", "oidc", "openid"))


def _looks_like_login_html(html: str) -> bool:
    lowered = (html or "")[:12000].lower()
    if any(marker in lowered for marker in _LOGIN_HTML_MARKERS):
        return True

    soup = BeautifulSoup(html or "", "lxml")
    if soup.find("input", attrs={"type": "password"}) is not None:
        return True

    for form in soup.find_all("form"):
        action = str(form.get("action", "")).lower()
        if any(token in action for token in ("login", "signin", "saml", "adfs", "auth", "authorize")):
            return True

    return False


def _detect_login_page(response: httpx.Response) -> str | None:
    effective_url = _normalize_url(str(response.url))
    if response.status_code in _AUTH_REQUIRED_STATUS_CODES:
        return effective_url

    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type:
        return None

    html = response.text or ""
    if _looks_like_login_url(effective_url) and _looks_like_login_html(html):
        return effective_url

    if response.status_code == 403 and _looks_like_login_html(html):
        return effective_url

    return None


def _looks_like_protected_shell(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    title_text = ((soup.title.string or "") if soup.title else "").strip().lower()
    if any(marker in title_text for marker in _LOGIN_TITLE_MARKERS):
        return True

    password_input = soup.find("input", attrs={"type": "password"})
    if password_input is not None:
        return True

    provider_hint = False
    for script in soup.find_all("script"):
        src = str(script.get("src", "")).lower()
        inline = (script.get_text(" ", strip=True) or "")[:500].lower()
        if any(marker in src or marker in inline for marker in _PROTECTED_SHELL_HTML_MARKERS):
            provider_hint = True
            break

    if not provider_hint:
        for form in soup.find_all("form"):
            action = str(form.get("action", "")).lower()
            if any(marker in action for marker in _PROTECTED_SHELL_HTML_MARKERS):
                provider_hint = True
                break

    script_count = len(soup.find_all("script"))
    main_like = soup.find("main") or soup.find("article")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    visible_text = soup.get_text(" ", strip=True)

    if provider_hint and not main_like and len(visible_text) < 120 and script_count >= 2:
        return True

    return script_count >= 3 and not main_like and len(visible_text) < 48


def _is_authenticated_page(url: str, html: str, allowed_host: str) -> bool:
    parsed = urlparse(url)
    host_ok = parsed.netloc == allowed_host
    return host_ok and (not _looks_like_login_url(url)) and (not _looks_like_login_html(html))


def _extract_allowed_host_cookies(cookies: Iterable[Any], allowed_host: str) -> dict[str, str]:
    captured: dict[str, str] = {}
    normalized_allowed = (allowed_host or "").lower().strip(".")
    for cookie in cookies:
        domain = str(cookie.get("domain", "")).lower().lstrip(".")
        if not domain:
            continue

        domain_allowed = (
            domain == normalized_allowed
            or domain.endswith("." + normalized_allowed)
            or normalized_allowed.endswith("." + domain)
        )
        if domain_allowed:
            name = str(cookie.get("name", "")).strip()
            value = str(cookie.get("value", ""))
            if name:
                captured[name] = value
    return captured


def _has_strong_auth_cookie(cookies: dict[str, str]) -> bool:
    keys = {key.lower() for key in cookies}
    return any(marker in key for key in keys for marker in ("auth", "token", "session", "id"))


def _extract_session_headers_from_storage(page: Any) -> dict[str, str]:
    script = """
        () => {
            const out = {};
            const readStore = (store) => {
                for (let i = 0; i < store.length; i++) {
                    const key = store.key(i);
                    if (!key) continue;
                    const value = store.getItem(key);
                    if (!value) continue;
                    out[key] = value;
                }
            };
            try { readStore(window.localStorage); } catch (e) {}
            try { readStore(window.sessionStorage); } catch (e) {}
            return out;
        }
    """
    try:
        raw = page.evaluate(script)
    except Exception:  # noqa: BLE001 - storage access can fail on some origins; treat as no session header
        return {}

    if not isinstance(raw, dict):
        return {}

    token_candidates: list[str] = []
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        lowered = key.lower()
        if any(marker in lowered for marker in ("access_token", "id_token", "bearer", "auth", "session")):
            token_candidates.append(value)

    for candidate in token_candidates:
        token = candidate.strip()
        if token and " " not in token and len(token) > 20:
            return {"Authorization": f"Bearer {token}"}
    return {}


def _parse_cookie_payload(raw_cookies: Any, allowed_host: str) -> dict[str, str]:
    if isinstance(raw_cookies, str):
        try:
            parsed = json.loads(raw_cookies)
        except json.JSONDecodeError:
            return {}
    else:
        parsed = raw_cookies

    if isinstance(parsed, dict):
        return {str(k): str(v) for k, v in parsed.items() if str(k).strip()}

    if isinstance(parsed, list):
        return _extract_allowed_host_cookies(parsed, allowed_host)

    return {}


def _build_auth_session_from_config(auth_config: AuthConfig | None, allowed_host: str) -> AuthSession:
    if not auth_config:
        return {"cookies": {}, "headers": {}}

    auth_type = str(auth_config.get("type", "")).strip().lower()
    session_cookies: dict[str, str] = {}
    session_headers: dict[str, str] = {}

    if auth_type == "cookie":
        session_cookies = _parse_cookie_payload(auth_config.get("cookies"), allowed_host)
    elif auth_type == "oauth":
        token = str(auth_config.get("token", "")).strip()
        if token:
            token_type = str(auth_config.get("token_type", "Bearer")).strip() or "Bearer"
            session_headers["Authorization"] = f"{token_type} {token}"
    elif auth_type == "basic":
        username = str(auth_config.get("username", "")).strip()
        password = str(auth_config.get("password", ""))
        if username:
            raw = f"{username}:{password}".encode()
            session_headers["Authorization"] = f"Basic {b64encode(raw).decode('ascii')}"

    for key, value in (auth_config.get("headers") or {}).items():
        normalized_key = str(key).strip()
        if normalized_key:
            session_headers[normalized_key] = str(value)

    return {"cookies": session_cookies, "headers": session_headers}


def _apply_form_authentication(page: Any, auth_config: AuthConfig) -> None:
    login_url = str(auth_config.get("login_url", "")).strip()
    username = str(auth_config.get("username", "")).strip()
    password = str(auth_config.get("password", ""))
    selectors = dict(auth_config.get("selectors") or {})

    username_selector = selectors.get(
        "username",
        'input[type="email"], input[name="email"], input[name="username"]',
    )
    password_selector = selectors.get("password", 'input[type="password"]')
    submit_selector = selectors.get("submit", 'button[type="submit"], input[type="submit"]')

    if login_url:
        page.goto(login_url, wait_until="domcontentloaded", timeout=30000)

    if username:
        page.fill(username_selector, username)
    if password:
        page.fill(password_selector, password)
    page.click(submit_selector)

    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:  # noqa: BLE001 - networkidle may never settle; fallback to fixed wait
        page.wait_for_timeout(1200)


def capture_authenticated_cookies(
    *,
    start_url: str,
    allowed_host: str,
    timeout_seconds: float = 300.0,
) -> dict[str, str]:
    deadline = time.monotonic() + timeout_seconds
    with _get_sync_playwright()() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(start_url, wait_until="domcontentloaded", timeout=30000)

            while time.monotonic() < deadline:
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=1500)
                except Exception:
                    _LOGGER.debug("domcontentloaded wait did not settle during interactive auth", exc_info=True)

                current_url = _normalize_url(page.url or start_url)
                parsed_url = urlparse(current_url)

                html = ""
                html_available = False
                try:
                    html = page.content()
                    html_available = True
                except Exception:  # noqa: BLE001 - page content may be unavailable transiently
                    html_available = False

                cookies = context.cookies()
                captured = _extract_allowed_host_cookies(cookies, allowed_host)

                host_matches_target = parsed_url.netloc == allowed_host
                if captured and _has_strong_auth_cookie(captured):
                    return captured

                if (
                    captured
                    and host_matches_target
                    and (not _looks_like_login_url(current_url))
                    and (not html_available or (not _looks_like_login_html(html)))
                ):
                    return captured

                if html_available and _is_authenticated_page(current_url, html, allowed_host=allowed_host) and captured:
                    return captured

                page.wait_for_timeout(1000)
        finally:
            browser.close()

    raise TimeoutError(
        "Authentication timed out. Complete login in the browser window and retry authenticate_ingest_job."
    )


def capture_authenticated_session(
    *,
    start_url: str,
    allowed_host: str,
    auth_config: AuthConfig | None = None,
    timeout_seconds: float = 300.0,
) -> AuthSession:
    baseline = _build_auth_session_from_config(auth_config, allowed_host)
    baseline_cookies = dict(baseline.get("cookies") or {})
    baseline_headers = dict(baseline.get("headers") or {})

    auth_type = str((auth_config or {}).get("type", "")).strip().lower()
    if auth_type in {"basic", "oauth", "cookie"} and (baseline_cookies or baseline_headers):
        return {"cookies": baseline_cookies, "headers": baseline_headers}

    deadline = time.monotonic() + timeout_seconds
    with _get_sync_playwright()() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            if baseline_headers:
                context.set_extra_http_headers(baseline_headers)
            if baseline_cookies:
                _inject_cookies_into_context(context, baseline_cookies, allowed_host)

            page = context.new_page()
            page.goto(start_url, wait_until="domcontentloaded", timeout=30000)

            if auth_type == "form" and auth_config is not None:
                _apply_form_authentication(page, auth_config)

            while time.monotonic() < deadline:
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=1500)
                except Exception:
                    _LOGGER.debug("domcontentloaded wait did not settle during interactive auth", exc_info=True)

                current_url = _normalize_url(page.url or start_url)
                parsed_url = urlparse(current_url)

                html = ""
                html_available = False
                try:
                    html = page.content()
                    html_available = True
                except Exception:  # noqa: BLE001 - page content may be unavailable transiently
                    html_available = False

                captured = _extract_allowed_host_cookies(context.cookies(), allowed_host)
                merged_cookies = dict(baseline_cookies)
                merged_cookies.update(captured)

                merged_headers = dict(baseline_headers)
                merged_headers.update(_extract_session_headers_from_storage(page))
                storage_state = _extract_storage_state(context)

                host_matches_target = parsed_url.netloc == allowed_host
                if merged_cookies and _has_strong_auth_cookie(merged_cookies):
                    return {"cookies": merged_cookies, "headers": merged_headers, "storage_state": storage_state}

                if merged_headers.get("Authorization") and host_matches_target:
                    return {"cookies": merged_cookies, "headers": merged_headers, "storage_state": storage_state}

                if (
                    merged_cookies
                    and host_matches_target
                    and (not _looks_like_login_url(current_url))
                    and (not html_available or (not _looks_like_login_html(html)))
                ):
                    return {"cookies": merged_cookies, "headers": merged_headers, "storage_state": storage_state}

                if (
                    html_available
                    and _is_authenticated_page(current_url, html, allowed_host=allowed_host)
                    and (merged_cookies or merged_headers)
                ):
                    return {"cookies": merged_cookies, "headers": merged_headers, "storage_state": storage_state}

                page.wait_for_timeout(1000)
        finally:
            browser.close()

    raise TimeoutError(
        "Authentication timed out. Complete login in the browser window and retry authenticate_ingest_job."
    )
