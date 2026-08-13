"""NG2 — the /api/v1 blueprint's shared machinery.

Spec `docs/superpowers/specs/2026-08-08-v11-admin-rest-api-design.md`
Decision 3. Every v1 endpoint is built on these four things, so they are
tested once here rather than re-asserted per endpoint:

  error()       one error body shape, `{"error": {"code", "message"}}`
  collection()  one collection envelope, `{items, total, page, per_page}`
  iso()         one timestamp format, ISO-8601 UTC *with* offset
  parse_collection_params()  paging/sort/filter parsing, and its 400s

The 404-returns-JSON test is the one that catches the regression the spec
cares most about: a fetch() caller that receives Flask's HTML error page has
nothing it can parse, which is why `require_auth_json` exists in the first
place. Unmatched URLs never reach a blueprint, so this needs an app-level
handler, and it is easy to leave out.
"""
import pytest

# Imported as a MODULE, not as names. conftest's admin_app fixture reloads
# swingbot.admin.api_v1, and importlib.reload mutates the module dict in
# place: functions that survive the reload see the NEW ApiError class via
# their globals, while a `from ... import ApiError` here would still hold the
# OLD one -- so pytest.raises(ApiError) silently stops matching, and only
# when a test in the same file has used the `client` fixture first.
# Attribute access re-reads the current object every time.
from swingbot.admin import api_v1 as v1


# --- error shape ---------------------------------------------------------

def test_unknown_v1_route_returns_json_not_html(client):
    r = client.get("/api/v1/no-such-endpoint")
    assert r.status_code == 404
    assert r.mimetype == "application/json"
    assert r.get_json() == {
        "error": {"code": "not_found", "message": "/api/v1/no-such-endpoint"}
    }


def test_unknown_non_v1_route_is_left_alone(client):
    """The handler must scope itself to /api/v1 -- the Jinja UI's own 404s
    stay HTML until cutover, and hijacking them would be a live-UI change."""
    r = client.get("/no-such-page")
    assert r.status_code == 404
    assert r.mimetype != "application/json"


def test_api_error_carries_code_message_and_status():
    e = v1.ApiError("invalid", "bad thing", 400)
    assert e.code == "invalid"
    assert e.message == "bad thing"
    assert e.status == 400


# --- collection envelope -------------------------------------------------

def test_collection_envelope_shape():
    body = v1.collection([{"a": 1}], total=7, page=2, per_page=25)
    assert body == {"items": [{"a": 1}], "total": 7, "page": 2, "per_page": 25}


# --- timestamps ----------------------------------------------------------

def test_iso_renders_utc_with_offset():
    from datetime import datetime, timezone
    dt = datetime(2026, 8, 8, 14, 3, 11, tzinfo=timezone.utc)
    assert v1.iso(dt) == "2026-08-08T14:03:11+00:00"


def test_iso_treats_naive_datetimes_as_utc():
    """Naive datetimes exist in this codebase's older records. Rendering one
    without an offset would hand the SPA a string it must guess about."""
    from datetime import datetime
    assert v1.iso(datetime(2026, 8, 8, 14, 3, 11)).endswith("+00:00")


def test_iso_passes_none_through():
    assert v1.iso(None) is None


# --- collection params ---------------------------------------------------

def _parse(**args):
    return v1.parse_collection_params(
        args, allowed_filters={"status", "ticker"}, sortable={"opened_at"}
    )


def test_defaults_when_nothing_supplied():
    p = _parse()
    assert p.page == 1
    assert p.per_page == 25
    assert p.sort is None
    assert p.filters == {}


def test_per_page_caps_at_200():
    assert _parse(per_page="5000").per_page == 200


def test_recognised_filters_are_collected():
    assert _parse(status="ACTIVE", ticker="AAPL").filters == {
        "status": "ACTIVE", "ticker": "AAPL"
    }


def test_blank_filter_is_treated_as_absent():
    assert _parse(status="").filters == {}


def test_unknown_filter_is_rejected():
    """Spec v11: an unrecognised filter is a 400, never a silent ignore --
    a silently ignored filter is how a filter that stopped working survives
    to production."""
    with pytest.raises(v1.ApiError) as exc:
        _parse(tikcer="AAPL")
    assert exc.value.status == 400
    assert exc.value.code == "invalid"
    assert "tikcer" in exc.value.message


def test_descending_sort_is_parsed():
    p = _parse(sort="-opened_at")
    assert p.sort == ("opened_at", "desc")


def test_ascending_sort_is_parsed():
    assert _parse(sort="opened_at").sort == ("opened_at", "asc")


def test_unsortable_field_is_rejected():
    with pytest.raises(v1.ApiError) as exc:
        _parse(sort="whatever")
    assert exc.value.status == 400
    assert exc.value.code == "invalid"


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "1.5"])
def test_non_positive_page_is_rejected(bad):
    with pytest.raises(v1.ApiError) as exc:
        _parse(page=bad)
    assert exc.value.status == 400
