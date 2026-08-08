"""The v1 auth decorator.

Spec v11 Decision 5. This is NOT a second auth mechanism: the predicate --
a valid session cookie, or Basic credentials matching ADMIN_USERNAME /
ADMIN_PASSWORD -- is the same one `app.require_auth` and
`api.require_auth_json` apply, and `_session_authenticated` is imported
rather than reimplemented.

What differs is only how failure is *rendered*. The legacy JSON blueprint
answers `{"error": "auth"}`, where `error` is a bare string; v1's contract
(Decision 3) is `{"error": {"code", "message"}}`. Reusing
`require_auth_json` directly would have leaked the old shape into the new
namespace, which the contract assertions caught immediately.

The old decorator is deliberately left untouched -- `dashboard.js` and the
Plans board branch on its body today, and changing it would be a live-UI
change this migration does not make.
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
