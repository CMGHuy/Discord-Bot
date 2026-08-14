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
"""
from __future__ import annotations

from functools import wraps

from flask import request

# The app MODULE, not names out of it. conftest reloads swingbot.admin.app
# between tests, which rebinds ADMIN_USERNAME/ADMIN_PASSWORD and rebuilds
# _session_authenticated; names bound here at import time would go stale and
# this decorator would authenticate against the previous test's credentials.
from swingbot.admin import app as _app

from . import error


def require_auth(view):
    """Guard a v1 endpoint. 401s carry the v1 error body, never HTML."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if _app._session_authenticated():
            return view(*args, **kwargs)
        auth = request.authorization
        if (auth and auth.username == _app.ADMIN_USERNAME
                and auth.password == _app.ADMIN_PASSWORD):
            return view(*args, **kwargs)
        # No WWW-Authenticate header: it would make a browser throw up its
        # native Basic Auth dialog over the SPA, which is not the login UI.
        # Scripted Basic callers already know their credentials failed.
        return error("auth", "Authentication required.", 401)

    return wrapped
