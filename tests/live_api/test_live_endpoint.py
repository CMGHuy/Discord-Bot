"""v202: GET /api/v1/live -- auth, shape, ?limit=, sections, DB-only."""
# V202-1b adds `from tests.store_seed import seed_store` with its section tests.
import pytest

from tests.admin.api_v1_contract import NULLABLE_NUMBER, NULLABLE_STR, assert_error, assert_shape
SECTION = {"availability": str, "as_of": str, "reason": NULLABLE_STR}
HEAT = {**SECTION, "open_pct": NULLABLE_NUMBER, "cap_pct": NULLABLE_NUMBER,
        "utilisation_pct": NULLABLE_NUMBER, "open_amount": NULLABLE_NUMBER,
        "cap_amount": NULLABLE_NUMBER, "headroom_pct": NULLABLE_NUMBER,
        "headroom_amount": NULLABLE_NUMBER, "balance": NULLABLE_NUMBER,
        "includes_resting": bool}


def _live(client, query=""):
    response = client.get(f"/api/v1/live{query}")
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_requires_auth(client):
    assert_error(client.get("/api/v1/live"), "auth", 401)


def test_live_top_level_and_heat_shape(logged_in):
    body = _live(logged_in)
    assert_shape(body, {"heat": dict, "awaiting": dict, "killswitch": dict,
                        "events": list, "events_meta": dict})
    assert_shape(body["heat"], HEAT, where="heat")


@pytest.mark.parametrize("raw, expected", [
    (None, 8), ("", 8), ("1", 1), ("8", 8), ("50", 50), ("51", 50), ("1000", 50),
    ("0", None), ("-3", None), ("abc", None), ("2.5", None),
])
def test_parse_limit(admin_app, raw, expected):
    from swingbot.admin.api_v1 import live
    assert live.parse_limit(raw) == expected


@pytest.mark.parametrize("query", ["?limit=0", "?limit=-1", "?limit=abc", "?limit=2.5"])
def test_a_bad_limit_is_a_400(logged_in, query):
    assert_error(logged_in.get(f"/api/v1/live{query}"), "invalid", 400)


def test_events_are_not_wired_until_v202_3(logged_in):
    body = _live(logged_in)
    assert body["events"] == []
    assert body["events_meta"]["availability"] == "unavailable"
    assert body["events_meta"]["reason"] == "not wired"
