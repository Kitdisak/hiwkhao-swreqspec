from __future__ import annotations

import secrets
import threading
import time

from .models import User
from .service import find_user_by_username

SESSION_COOKIE = "library_session"
SESSION_TIMEOUT_SECONDS = 600

_sessions: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = (username, time.monotonic() + SESSION_TIMEOUT_SECONDS)
    return token


def get_session_user(token: str | None) -> User | None:
    if not token:
        return None
    now = time.monotonic()
    with _lock:
        session = _sessions.get(token)
        if session is None:
            return None
        username, expires_at = session
        if expires_at <= now:
            del _sessions[token]
            return None
        _sessions[token] = (username, now + SESSION_TIMEOUT_SECONDS)
    return find_user_by_username(username)

