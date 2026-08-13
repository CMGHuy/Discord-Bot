"""NG3 — self-tests for the contract assertions in api_v1_contract.py.

A contract helper that cannot fail is worse than no helper: every endpoint
test built on it would pass regardless of what the endpoint returned. Each
assertion here is exercised in both directions — once on conforming data,
once on the specific violation it exists to catch.

The bool/int case is the subtle one and the reason `_matches` exists at all:
`isinstance(True, int)` is True in Python, so a naive numeric check would
accept a boolean where a price is expected. That is exactly the float-to-
something-else drift spec v11 Decision 6 names as its residual risk.
"""
import pytest

from tests.admin.api_v1_contract import (
    NULLABLE_NUMBER,
    NUMBER,
    assert_collection,
    assert_error,
    assert_shape,
)


# --- assert_shape --------------------------------------------------------

def test_shape_accepts_conforming_body():
    assert_shape({"id": "abc", "pnl": 1.5}, {"id": str, "pnl": NUMBER})


def test_shape_rejects_missing_key():
    with pytest.raises(AssertionError, match="missing key"):
        assert_shape({"id": "abc"}, {"id": str, "pnl": NUMBER})


def test_shape_rejects_undeclared_key():
    """An endpoint growing a field nobody declared is a contract change."""
    with pytest.raises(AssertionError, match="undeclared key"):
        assert_shape({"id": "abc", "surprise": 1}, {"id": str})


def test_shape_rejects_wrong_type():
    with pytest.raises(AssertionError, match="expected int \\| float"):
        assert_shape({"pnl": "1.5"}, {"pnl": NUMBER})


def test_shape_rejects_bool_where_number_expected():
    """isinstance(True, int) is True -- the check has to exclude bool itself,
    or a boolean silently satisfies a numeric field."""
    with pytest.raises(AssertionError):
        assert_shape({"pnl": True}, {"pnl": NUMBER})


def test_shape_accepts_bool_where_bool_expected():
    assert_shape({"ok": True}, {"ok": bool})


def test_shape_accepts_none_only_where_declared_nullable():
    assert_shape({"pnl": None}, {"pnl": NULLABLE_NUMBER})
    with pytest.raises(AssertionError):
        assert_shape({"pnl": None}, {"pnl": NUMBER})


def test_shape_rejects_non_object():
    with pytest.raises(AssertionError, match="expected an object"):
        assert_shape(["not", "an", "object"], {"id": str})


# --- assert_error --------------------------------------------------------

def test_error_accepts_spec_shaped_failure(client):
    assert_error(client.get("/api/v1/nope"), "not_found", 404)


def test_error_rejects_wrong_status(client):
    with pytest.raises(AssertionError, match="expected HTTP 400"):
        assert_error(client.get("/api/v1/nope"), "not_found", 400)


def test_error_rejects_wrong_code(client):
    with pytest.raises(AssertionError, match="expected error code"):
        assert_error(client.get("/api/v1/nope"), "invalid", 404)


def test_error_rejects_html_error_page(client):
    """The regression that matters most: a non-JSON body a fetch() caller
    cannot parse. The Jinja UI's 404s are exactly that, by design."""
    with pytest.raises(AssertionError, match="must be JSON"):
        assert_error(client.get("/no-such-page"), "not_found", 404)


# --- assert_collection ---------------------------------------------------

_ITEM = {"id": str}


def test_collection_accepts_conforming_envelope():
    assert_collection(
        {"items": [{"id": "a"}], "total": 1, "page": 1, "per_page": 25}, _ITEM
    )


def test_collection_allows_total_greater_than_page_length():
    """The normal paged case: 25 rows on screen out of 137."""
    assert_collection(
        {"items": [{"id": "a"}], "total": 137, "page": 1, "per_page": 25}, _ITEM
    )


def test_collection_rejects_total_smaller_than_items():
    """Catches `total=len(items)` being passed for a sliced page -- the
    mistake that silently turns a 137-row result into a 1-page one."""
    with pytest.raises(AssertionError, match="count after filtering"):
        assert_collection(
            {"items": [{"id": "a"}, {"id": "b"}], "total": 1, "page": 1, "per_page": 25},
            _ITEM,
        )


def test_collection_rejects_missing_envelope_key():
    with pytest.raises(AssertionError, match="missing key"):
        assert_collection({"items": [], "total": 0, "page": 1}, _ITEM)


def test_collection_checks_every_item():
    with pytest.raises(AssertionError, match=r"items\[1\]"):
        assert_collection(
            {"items": [{"id": "a"}, {"id": 2}], "total": 2, "page": 1, "per_page": 25},
            _ITEM,
        )
