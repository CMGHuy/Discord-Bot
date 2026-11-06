"""v207: enforce swingbot.admin.access on every /api/v1 request.

A blueprint before_request, not a check inside require_auth: it runs for every
route routed to api_v1 -- decorated or not -- before the view. It lives here,
not in api_v1/__init__.py, because that module may import nothing from
swingbot.admin; register() imports this module before register_blueprint().
"""
from __future__ import annotations

from flask import request

from swingbot.admin import access
from swingbot.admin import app as _app  # module, not names: tests reload app

from . import api_v1, error

FORBIDDEN_MESSAGE = "Read-only account."


@api_v1.before_request
def enforce_access():
    """None lets the request through; a viewer outside its rights gets 403."""
    if access.check_access(_app.resolve_principal(), request.method, request.path):
        return None
    return error("forbidden", FORBIDDEN_MESSAGE, 403)
