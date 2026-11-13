"""v227: GET /api/v1/feed-posts (paging after an id) and /feed-posts/kinds."""
from datetime import datetime, timezone

import pytest

from swingbot.core.db.engine import DatabaseUnavailable
from tests.admin.api_v1_contract import NULLABLE_STR, assert_error, assert_shape

URL = "/api/v1/feed-posts"
KINDS_URL = "/api/v1/feed-posts/kinds"
T0 = datetime(2026, 11, 12, 14, 30, tzinfo=timezone.utc)
_ITEM = {"id": int, "posted_at": str, "kind": str, "family": NULLABLE_STR,
         "ticker": NULLABLE_STR, "headline": str}


def _row(row_id, kind="FILLED", ticker="MSFT", headline="Order filled, MSFT"):
    return {"id": row_id, "posted_at": T0, "kind": kind, "ticker": ticker, "headline": headline}


@pytest.fixture
def feed(client, monkeypatch):
    # `client` first: it loads swingbot.admin.app, which registers the endpoints.
    from swingbot.admin.api_v1 import feed_posts as mod
    state = {"rows": [], "latest": 0, "pages": [], "order": []}

    def page(after, limit):
        state["pages"].append((after, limit))
        state["order"].append("page")
        return [r for r in state["rows"] if r["id"] > after][:limit]

    def latest():
        state["order"].append("latest")
        return state["latest"]

    monkeypatch.setattr(mod, "_page", page)
    monkeypatch.setattr(mod, "_latest", latest)
    return state


def test_unauthenticated_is_401(client, feed):
    assert_error(client.get(URL), "auth", 401)
    assert_error(client.get(KINDS_URL), "auth", 401)


def test_without_after_only_the_latest_id_comes_back(client, auth, feed):
    feed["rows"], feed["latest"] = [_row(1), _row(2)], 2
    body = client.get(URL, headers=auth).get_json()
    assert body == {"items": [], "latest_id": 2}
    assert feed["pages"] == []


def test_an_empty_table_is_latest_zero(client, auth, feed):
    assert client.get(URL, headers=auth).get_json() == {"items": [], "latest_id": 0}
    assert client.get(URL + "?after=0", headers=auth).get_json() == {"items": [], "latest_id": 0}


def test_after_pages_oldest_first_with_the_family(client, auth, feed):
    feed["rows"] = [_row(1), _row(2, "MOVE_STOP", "AMD", "Move stop loss, AMD"),
                    _row(3, "LEGACY_GONE", None, "gone")]
    feed["latest"] = 3
    body = client.get(URL + "?after=1", headers=auth).get_json()
    assert_shape(body, {"items": list, "latest_id": int})
    for item in body["items"]:
        assert_shape(item, _ITEM, where="item")
    assert [i["id"] for i in body["items"]] == [2, 3]
    assert body["items"][0] == {"id": 2, "posted_at": "2026-11-12T14:30:00+00:00",
                                "kind": "MOVE_STOP", "family": "MANAGE", "ticker": "AMD",
                                "headline": "Move stop loss, AMD"}
    assert body["items"][1]["family"] is None and body["items"][1]["ticker"] is None
    assert feed["pages"] == [(1, 20)]


def test_the_latest_id_is_read_before_the_page(client, auth, feed):
    client.get(URL + "?after=0", headers=auth)
    assert feed["order"] == ["latest", "page"]


@pytest.mark.parametrize("limit,passed", [("1", 1), ("50", 50), ("99", 50)])
def test_limit_is_used_up_to_fifty(client, auth, feed, limit, passed):
    client.get(f"{URL}?after=0&limit={limit}", headers=auth)
    assert feed["pages"] == [(0, passed)]


@pytest.mark.parametrize("query", ["?after=abc", "?after=1.5", "?after=0&limit=0",
                                   "?after=0&limit=-3", "?after=0&limit=ten"])
def test_bad_parameters_are_400(client, auth, feed, query):
    assert_error(client.get(URL + query, headers=auth), "invalid", 400)
    assert feed["pages"] == []


def test_an_unreachable_database_is_503(client, auth, monkeypatch, feed):
    from swingbot.admin.api_v1 import feed_posts as mod

    def down():
        raise DatabaseUnavailable("side engine backing off")

    monkeypatch.setattr(mod, "_latest", down)
    assert_error(client.get(URL + "?after=0", headers=auth), "unavailable", 503)


def test_a_viewer_may_read_both(viewer_client, feed):
    client, _row_ = viewer_client
    assert client.get(URL).status_code == 200
    assert client.get(KINDS_URL).status_code == 200


def test_kinds_lists_the_five_families_in_order_with_watch_off(client, auth, feed):
    body = client.get(KINDS_URL, headers=auth).get_json()
    families = body["families"]
    assert [f["family"] for f in families] == ["NEW_SETUP", "ENTRY", "MANAGE", "WATCH", "RESULT"]
    assert [f["label"] for f in families] == ["New setup", "Entry", "Manage", "Watch", "Result"]
    assert {f["family"]: f["default_on"] for f in families} == {
        "NEW_SETUP": True, "ENTRY": True, "MANAGE": True, "WATCH": False, "RESULT": True}
    for family in families:
        assert_shape(family, {"family": str, "label": str, "default_on": bool, "kinds": list})
        for kind in family["kinds"]:
            assert_shape(kind, {"kind": str, "label": str, "phrase": str, "sample": str})


def test_kinds_carry_label_phrase_and_sample_in_registry_order(client, auth, feed):
    from swingbot.core.presentation.kinds import Family, Kind
    families = client.get(KINDS_URL, headers=auth).get_json()["families"]
    entry = next(f for f in families if f["family"] == "ENTRY")
    assert [k["kind"] for k in entry["kinds"]] == [k.name for k in Kind if k.family is Family.ENTRY]
    filled = next(k for k in entry["kinds"] if k["kind"] == "FILLED")
    assert filled == {"kind": "FILLED", "label": "FILLED", "phrase": "Order filled",
                      "sample": "Order filled, AAPL"}
    setup = next(f for f in families if f["family"] == "NEW_SETUP")
    simple = next(k for k in setup["kinds"] if k["kind"] == "SETUP_SIMPLE")
    assert simple["phrase"] == "New alert"
    assert simple["sample"] == "New long alert, AAPL, buy at 187.50"


def test_kinds_never_lists_system_or_book(client, auth, feed):
    from swingbot.core.presentation.kinds import Family, Kind
    families = client.get(KINDS_URL, headers=auth).get_json()["families"]
    listed = {k["kind"] for f in families for k in f["kinds"]}
    assert not listed & {k.name for k in Kind if k.family in (Family.SYSTEM, Family.BOOK)}
