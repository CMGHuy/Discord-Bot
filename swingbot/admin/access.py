"""v207: who may call which /api/v1 route -- one pure, default-deny rule.

Spec: docs/superpowers/specs/2026-11-05-v207-viewer-accounts-design.md
§ Access check. Enforced by api_v1/access_hook.py (an api_v1.before_request),
so a route added later without @require_auth is still covered. The tables are
data; tests/admin/access_expectations.py classifies every Flask rule and
test_access_contract.py fails when this module disagrees with it.

Imports nothing from swingbot.admin: it is pure, and the hook imports it.
"""
from __future__ import annotations

from typing import Callable, Mapping

#: A viewer may call nothing under these, matched on segment boundaries
#: (`/api/v1/jobs` and `/api/v1/jobs/...`, never `/api/v1/jobsite`).
ADMIN_ONLY_PREFIXES: tuple[str, ...] = (
    "/api/v1/system",
    "/api/v1/users",
    "/api/v1/jobs",
    "/api/v1/analytics/tuning",
    "/api/v1/versions",
)

#: System reads the shell makes on every page: the freshness chip, scan strip
#: and live bot section (/system/scan) and the shared layout record
#: (/system/preferences, spec Decision 5). GET/HEAD only, exact paths.
VIEWER_GET_ALLOWLIST: frozenset[str] = frozenset({
    "/api/v1/system/scan",
    "/api/v1/system/preferences",
})

#: The sign-in door: every principal (and none) may read, open and close it.
EXEMPT_PATHS: frozenset[str] = frozenset({"/api/v1/session"})

READ_METHODS: frozenset[str] = frozenset({"GET", "HEAD"})


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def is_admin_only(path: str) -> bool:
    return any(_under(path, prefix) for prefix in ADMIN_ONLY_PREFIXES)


def _viewer_may(method: str, path: str) -> bool:
    if method.upper() not in READ_METHODS:
        return False
    return path in VIEWER_GET_ALLOWLIST or not is_admin_only(path)


def _admin_may(method: str, path: str) -> bool:
    return True


_ROLE_RULES: Mapping[str, Callable[[str, str], bool]] = {
    "admin": _admin_may,
    "viewer": _viewer_may,
}


def check_access(principal: Mapping | None, method: str, path: str) -> bool:
    """True when `principal` may call `method path`.

    No principal is not a refusal: the hook steps aside and `require_auth`
    answers 401 (or lets a Basic admin through). A role this table does not
    know is refused -- default deny."""
    if principal is None or path in EXEMPT_PATHS:
        return True
    rule = _ROLE_RULES.get(principal.get("role"))
    return rule is not None and rule(method, path)
