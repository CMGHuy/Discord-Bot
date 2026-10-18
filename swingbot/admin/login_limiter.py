"""Login limiter (v148, spec O2).

Five failed sign-ins from one client address inside a sliding 15-minute window
lock that address out of all three credential checks: the SPA login form
(POST /api/v1/session), Basic auth on /api/v1/*, and Basic auth on
app.require_auth. The lock lifts when the oldest of those failures ages out.

One module-level instance, LIMITER, is valid because the admin runs ONE
worker (deploy/gunicorn.conf.py). Two workers would each keep their own count
and double the allowance.

The key is the CF-Connecting-IP header when present. Behind the Cloudflare
tunnel every request arrives from the cloudflared container, so
request.remote_addr is the same for everyone. The header is spoofable only by
someone who can reach port 1234 directly, which the VM firewall forbids
(docs/deploy/DEPLOY_HETZNER.md, "Accessing the admin UI").

Only attempts count: a request carrying no credentials is never a failure.
This module imports nothing from swingbot.admin. The credential check is
passed in, so app.py and the api_v1 modules can both import it without a cycle.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

from flask import request

MAX_FAILURES = 5
WINDOW_S = 900.0


class LoginLimiter:
    """Failure timestamps per key over a sliding window, behind one lock.

    Every call prunes timestamps older than the window and drops keys left
    empty, so memory is bounded by the addresses that failed recently."""

    def __init__(self, max_failures: int = MAX_FAILURES, window_s: float = WINDOW_S,
                 clock: Callable[[], float] = time.monotonic):
        self._max = max_failures
        self._window = window_s
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: dict[str, deque[float]] = {}

    def __len__(self) -> int:
        """Keys currently tracked (for the memory-bound test)."""
        with self._lock:
            return len(self._failures)

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        for key in list(self._failures):
            stamps = self._failures[key]
            while stamps and stamps[0] <= cutoff:
                stamps.popleft()
            if not stamps:
                del self._failures[key]

    def check(self, key: str) -> int | None:
        """Whole seconds until `key` may try again, or None when not locked."""
        with self._lock:
            now = self._clock()
            self._prune(now)
            stamps = self._failures.get(key)
            if stamps is None or len(stamps) < self._max:
                return None
            # The lock lifts when the max-th most recent failure leaves the window.
            return max(1, math.ceil(stamps[-self._max] + self._window - now))

    def fail(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            self._prune(now)
            self._failures.setdefault(key, deque()).append(now)

    def succeed(self, key: str) -> None:
        with self._lock:
            self._prune(self._clock())
            self._failures.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


LIMITER = LoginLimiter()


def client_key() -> str:
    """CF-Connecting-IP when present, else the socket peer, else "unknown"."""
    forwarded = (request.headers.get("CF-Connecting-IP") or "").strip()
    return forwarded or request.remote_addr or "unknown"


def rate_limited_message(seconds: int) -> str:
    """The 429 text all three paths send, in whole minutes rounded up (min 1)."""
    minutes = max(1, math.ceil(seconds / 60))
    unit = "minute" if minutes == 1 else "minutes"
    return f"Too many failed sign-ins. Try again in {minutes} {unit}."


@dataclass(frozen=True)
class Attempt:
    """One gated credential check. `retry_after` is set only when locked."""
    ok: bool
    retry_after: int | None = None


def attempt(username: str, password: str, match: Callable[[str, str], bool]) -> Attempt:
    """Gate one credential check through LIMITER (read at call time).

    A locked key is refused before the credentials are compared. Empty
    username AND password is not an attempt and is never counted."""
    key = client_key()
    wait = LIMITER.check(key)
    if wait is not None:
        return Attempt(False, wait)
    if not username and not password:
        return Attempt(False)
    if match(username, password):
        LIMITER.succeed(key)
        return Attempt(True)
    LIMITER.fail(key)
    return Attempt(False)
