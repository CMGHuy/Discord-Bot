"""NG32 — GET/PUT /api/v1/system/preferences.

NG19 TRIAGE: KEEP unchanged. A v1-only endpoint with no Jinja counterpart;
it survives the cutover untouched.

Server-side rather than localStorage (spec v13): the same person on a laptop
and a desktop should see the same columns, which localStorage silently fails
to deliver. The blob itself is opaque to the server -- it is UI state, and a
server that validated its shape would need editing every time the SPA
remembered one more thing.
"""
import json
import os

import pytest

from swingbot import config

from .api_v1_contract import assert_error, assert_shape

ENDPOINT = "/api/v1/system/preferences"


def stored(app) -> dict:
    path = os.path.join(config.DATA_DIR, "ui_preferences.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_requires_auth(client):
    assert_error(client.get(ENDPOINT), "auth", 401)
    assert_error(client.put(ENDPOINT, json={"preferences": {}}), "auth", 401)


def test_absent_preferences_supply_the_minimum_sample_default(client, auth):
    """A fresh install has no file. That is a state, not a 404 -- the SPA
    boots into it every first run."""
    response = client.get(ENDPOINT, headers=auth)

    assert response.status_code == 200
    assert_shape(response.get_json(), {"preferences": dict})
    assert response.get_json()["preferences"] == {"minSampleN": 30}


def test_saved_preferences_are_returned(client, auth, admin_app):
    columns = {"tables": {"trades": ["ticker", "pnl_pct"]}}

    saved = client.put(ENDPOINT, headers=auth, json={"preferences": columns})
    assert saved.status_code == 200
    assert saved.get_json()["preferences"] == {**columns, "minSampleN": 30}

    assert client.get(ENDPOINT, headers=auth).get_json()["preferences"] == {**columns, "minSampleN": 30}


def test_a_put_replaces_rather_than_merges(client, auth):
    """The client holds the whole object anyway, and a merge would make
    deleting a key impossible without inventing a second verb."""
    client.put(ENDPOINT, headers=auth, json={"preferences": {"a": 1, "b": 2}})
    client.put(ENDPOINT, headers=auth, json={"preferences": {"a": 9}})

    assert client.get(ENDPOINT, headers=auth).get_json()["preferences"] == {"a": 9, "minSampleN": 30}


def test_it_is_written_atomically(client, auth, admin_app):
    """Through jsonio, like every other data/ file that matters -- NG23
    found six that are not, and this is not going to be a seventh."""
    client.put(ENDPOINT, headers=auth, json={"preferences": {"tables": {"x": ["a"]}}})

    assert stored(admin_app) == {"tables": {"x": ["a"]}, "minSampleN": 30}


def test_it_does_not_touch_env(client, auth, admin_app):
    """The reason this is not a config.Field. `_build_env_text` rewrites the
    WHOLE .env from the mapping it is given, so a column toggle would
    rewrite every setting the bot has -- through a writer that is not
    atomic, on a file whose corruption takes the bot down silently."""
    open(config.ENV_PATH, "w", encoding="utf-8").write("DISCORD_TOKEN=keep-me\n")

    client.put(ENDPOINT, headers=auth, json={"preferences": {"tables": {}}})

    assert "keep-me" in open(config.ENV_PATH, encoding="utf-8").read()


@pytest.mark.parametrize("body", [
    {"preferences": "not an object"},
    {"preferences": ["not", "an", "object"]},
    {"preferences": None},
    {},
])
def test_a_non_object_blob_is_rejected(client, auth, body):
    assert_error(client.put(ENDPOINT, headers=auth, json=body), "invalid", 400)


def test_an_oversized_blob_is_rejected(client, auth):
    """Preferences are a handful of column lists. Anything approaching a
    megabyte is a client bug or someone using the admin as a key-value
    store, and both are better refused than persisted."""
    huge = {"junk": "x" * (64 * 1024 + 1)}

    assert_error(client.put(ENDPOINT, headers=auth, json={"preferences": huge}),
                 "invalid", 400)


def test_a_rejected_write_leaves_the_previous_value(client, auth):
    client.put(ENDPOINT, headers=auth, json={"preferences": {"keep": True}})
    client.put(ENDPOINT, headers=auth, json={"preferences": "nonsense"})

    assert client.get(ENDPOINT, headers=auth).get_json()["preferences"] == {"keep": True, "minSampleN": 30}


def test_minimum_sample_round_trips_and_rejects_non_positive_values(client, auth):
    body = client.put(ENDPOINT, headers=auth, json={"preferences": {"minSampleN": 50}}).get_json()
    assert body["preferences"]["minSampleN"] == 50
    assert_error(client.put(ENDPOINT, headers=auth, json={"preferences": {"minSampleN": 0}}), "invalid", 400)
    assert_error(client.put(ENDPOINT, headers=auth, json={"preferences": {"minSampleN": -5}}), "invalid", 400)


# --- watchlist tags (v85 R7-03) ------------------------------------------
#
# Tags are a pure UI/view concern (spec D35): `data/watchlist.json` is read
# by the bot on every scan, and a tag must never reach it. The blob this
# endpoint serves is deliberately opaque (see `get_preferences`'s docstring
# above) -- there is no per-key schema to extend, so `watchlistTags` already
# round-trips through the existing GET/PUT pair with zero server changes.
# These tests prove that, rather than adding a schema that doesn't exist.

def test_watchlist_tags_round_trip_through_preferences(client, auth):
    client.put(ENDPOINT, headers=auth, json={"preferences": {"watchlistTags": {"AAPL": ["Tech"]}}})

    response = client.get(ENDPOINT, headers=auth)
    assert response.get_json()["preferences"]["watchlistTags"] == {"AAPL": ["Tech"]}


def test_watchlist_tags_do_not_reach_the_watchlist_file(client, auth):
    """`swingbot.core.marketdata.watchlist.DEFAULT_PATH` is computed from
    `config.DATA_DIR` at IMPORT time, and `swingbot.core.marketdata.watchlist`
    is deliberately absent from this module's `conftest.py`'s
    `_RELOAD_MODULES` list -- so it does NOT track this test's per-test
    `DATA_DIR` monkeypatch (`tests/admin/test_api_v1_watchlist.py`'s module
    docstring documents this exact trap). That makes `DEFAULT_PATH` the
    bot's real, frozen load path rather than an isolated per-test one --
    which is precisely the file D35 says a tag must never reach, so it is
    the file this test has to check, not a fresh tmp_path stand-in. Reading
    it (never writing) is safe regardless of what it is bound to."""
    from swingbot.core.marketdata import watchlist as watchlist_module

    path = watchlist_module.DEFAULT_PATH
    before = open(path, encoding="utf-8").read() if os.path.exists(path) else None

    client.put(ENDPOINT, headers=auth, json={"preferences": {"watchlistTags": {"AAPL": ["Tech"]}}})

    after = open(path, encoding="utf-8").read() if os.path.exists(path) else None
    assert before == after
