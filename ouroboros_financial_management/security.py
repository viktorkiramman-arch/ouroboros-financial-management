from __future__ import annotations

import secrets
from collections import defaultdict, deque
from collections.abc import Callable
from functools import wraps
from ipaddress import ip_address, ip_network
from time import monotonic
from typing import Any, TypeVar

from flask import abort, current_app, g, redirect, request, session, url_for

F = TypeVar("F", bound=Callable[..., Any])
_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_LOOPBACKS = (ip_network("127.0.0.0/8"), ip_network("::1/128"))


def _client_key() -> str:
    user_part = str(session.get("user_id") or "anon")
    remote = request.remote_addr or "unknown"
    return f"{remote}:{user_part}"


def is_loopback(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = ip_address(value)
    except ValueError:
        return False
    return any(parsed in network for network in _LOOPBACKS)


def enforce_localhost() -> None:
    if not current_app.config.get("LOCAL_ONLY", True):
        return
    remote = request.remote_addr or ""
    host = (request.host or "").split(":", 1)[0].lower().strip("[]")
    allowed_host = host in {"127.0.0.1", "localhost", "::1"} or host.endswith(".localhost")
    if not is_loopback(remote) or not allowed_host:
        abort(403)


def apply_security_headers(response):
    response.headers["Content-Security-Policy"] = current_app.config["CONTENT_SECURITY_POLICY"]
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if current_app.config.get("SESSION_COOKIE_SECURE"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def login_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]


def rate_limit(*, limit: int, window_seconds: int, label: str) -> Callable[[F], F]:
    def decorator(view: F) -> F:
        @wraps(view)
        def wrapped(*args, **kwargs):
            key = f"{label}:{_client_key()}"
            now = monotonic()
            bucket = _RATE_BUCKETS[key]
            while bucket and now - bucket[0] > window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                abort(429)
            bucket.append(now)
            return view(*args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator


def load_logged_in_user() -> None:
    from .extensions import db
    from .models import User

    user_id = session.get("user_id")
    g.user = db.session.get(User, user_id) if user_id else None


def current_user_id() -> int:
    if not g.get("user"):
        abort(401)
    return int(g.user.id)


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return str(token)


def validate_csrf() -> None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    expected = session.get("csrf_token")
    submitted = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not expected or not submitted or not secrets.compare_digest(str(expected), str(submitted)):
        abort(400)
