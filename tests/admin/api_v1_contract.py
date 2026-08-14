"""NG3 — assertions that pin the /api/v1 contract.

Spec `docs/superpowers/specs/implemented/2026-08-08-v11-admin-rest-api-design.md`
Decision 6: there is no OpenAPI document. The Angular client's TypeScript
interfaces are hand-written, and *these assertions are what keeps them
honest*. If a field is renamed, removed, or changes type on the Python
side, a test here fails and someone updates the TS to match.

That only works if the assertions check **types, not merely key presence** —
the spec's own stated risk is a field quietly changing from float to str,
which a key-presence check sails straight past. So `assert_shape` takes a
type per key and enforces both directions of the key set:

    assert_shape(body, {
        "id":        str,
        "ticker":    str,
        "pnl_pct":   NULLABLE_NUMBER,
        "opened_at": str,
    })

Extra keys fail as loudly as missing ones. An endpoint that starts
returning a field nobody declared is an undocumented contract change, and
the SPA will grow a dependency on it.

This module is NOT named test_*.py: it holds no tests of its own, only
helpers imported by the per-endpoint contract tests. Its own self-tests
live in tests/admin/test_api_v1_contract.py.
"""
from __future__ import annotations

from typing import Any, Mapping

# Booleans are ints in Python, so `bool` must be excluded explicitly wherever
# a number is expected -- otherwise `True` satisfies an `int` annotation and a
# genuine type regression passes.
NUMBER = (int, float)
NULLABLE_NUMBER = (int, float, type(None))
NULLABLE_STR = (str, type(None))


def _type_name(expected) -> str:
    if isinstance(expected, tuple):
        return " | ".join(t.__name__ for t in expected)
    return expected.__name__


def _matches(value: Any, expected) -> bool:
    types = expected if isinstance(expected, tuple) else (expected,)
    # bool is a subclass of int: never let it satisfy a numeric contract.
    if isinstance(value, bool) and bool not in types:
        return False
    return isinstance(value, types)


def assert_shape(body: Mapping[str, Any], spec: Mapping[str, Any], *, where: str = "body") -> None:
    """Assert `body` has exactly `spec`'s keys, each of the declared type."""
    assert isinstance(body, Mapping), f"{where}: expected an object, got {type(body).__name__}"

    actual, expected = set(body), set(spec)
    missing, extra = expected - actual, actual - expected
    assert not missing, f"{where}: missing key(s) {sorted(missing)}"
    assert not extra, (
        f"{where}: undeclared key(s) {sorted(extra)} -- an endpoint returning a "
        f"field the contract does not declare is an undocumented change"
    )

    for key, want in spec.items():
        value = body[key]
        assert _matches(value, want), (
            f"{where}[{key!r}]: expected {_type_name(want)}, "
            f"got {type(value).__name__} ({value!r})"
        )


def assert_error(response, code: str, status: int) -> None:
    """Assert a failure response matches the spec's one error shape."""
    assert response.status_code == status, (
        f"expected HTTP {status}, got {response.status_code}"
    )
    assert response.mimetype == "application/json", (
        f"error responses must be JSON, got {response.mimetype!r} -- a fetch() "
        f"caller cannot parse an HTML error page"
    )
    body = response.get_json()
    assert_shape(body, {"error": dict}, where="error body")
    assert_shape(body["error"], {"code": str, "message": str}, where="error")
    assert body["error"]["code"] == code, (
        f"expected error code {code!r}, got {body['error']['code']!r}"
    )


def assert_collection(body: Mapping[str, Any], item_spec: Mapping[str, Any]) -> None:
    """Assert the collection envelope, then every item against `item_spec`."""
    assert_shape(
        body,
        {"items": list, "total": int, "page": int, "per_page": int},
        where="collection",
    )
    assert body["total"] >= len(body["items"]), (
        f"total ({body['total']}) < len(items) ({len(body['items'])}) -- `total` is "
        f"the count after filtering but BEFORE slicing; passing len(items) here "
        f"silently produces a single-page result set"
    )
    for i, item in enumerate(body["items"]):
        assert_shape(item, item_spec, where=f"items[{i}]")
