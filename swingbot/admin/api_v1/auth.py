"""The v1 auth decorator.

Spec v11 Decision 5. This is NOT a second auth mechanism: the predicate --
a valid session cookie, or Basic credentials matching ADMIN_USERNAME /
ADMIN_PASSWORD -- is the same one `app.require_auth` applies, and
`_session_authenticated` is reused rather than reimplemented.

What differs is only how failure is *rendered*. `app.require_auth` redirects
a browser into the SPA; a v1 endpoint must answer JSON in the contract's
shape (Decision 3), `{"error": {"code", "message"}}`. A legacy JSON
decorator in the deleted `api.py` answered `{"error": "auth"}` with `error`
as a bare string; reusing it would have leaked that shape into this
namespace, which the contract assertions caught immediately.

v148: the Basic comparison is `_app.credentials_match` (constant time), and
every attempt goes through `login_limiter.attempt`, shared with
`app.require_auth` and POST /api/v1/session. A locked client gets
`rate_limited` (429) with a Retry-After header.
"""
from __future__ import annotations

from functools import wraps

from flask import request

# The app MODULE, not names out of it. conftest reloads swingbot.admin.app
# between tests, which rebinds ADMIN_USERNAME/ADMIN_PASSWORD and rebuilds
# _session_authenticated; names bound here at import time would go stale and
# this decorator would authenticate against the previous test's credentials.
from swingbot.admin import app as _app

from swingbot.admin import login_limiter

from . import error


def rate_limited(retry_after: int):
    """The v1 429 (v148): the one error body, plus a Retry-After header."""
    body, status = error("rate_limited", login_limiter.rate_limited_message(retry_after), 429)
    body.headers["Retry-After"] = str(retry_after)
    return body, status


def require_auth(view):
    """Guard a v1 endpoint. 401s carry the v1 error body, never HTML."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if _app._session_authenticated():
            return view(*args, **kwargs)
        auth = request.authorization
        if auth:
            # v148: constant-time, gated by the limiter app.require_auth and
            # POST /session share. A request with no credentials never counts.
            outcome = login_limiter.attempt(auth.username or "", auth.password or "",
                                            _app.credentials_match)
            if outcome.ok:
                return view(*args, **kwargs)
            if outcome.retry_after is not None:
                return rate_limited(outcome.retry_after)
        # No WWW-Authenticate header: it would make a browser throw up its
        # native Basic Auth dialog over the SPA, which is not the login UI.
        # Scripted Basic callers already know their credentials failed.
        return error("auth", "Authentication required.", 401)

    return wrapped
