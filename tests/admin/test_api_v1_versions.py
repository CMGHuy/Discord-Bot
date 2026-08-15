"""GET /api/v1/versions — the ui/bot pairing history behind the Versions page.

The endpoint reads a COMMITTED file (`swingbot/admin/version_history.json`)
rather than live git, because the deployed container has no history to walk.
That makes two things worth pinning: the payload keeps its shape when the file
is missing entirely, and `stale` notices when someone bumps VERSION.json without
re-running `scripts/dev/build_version_matrix.py`.

These tests deliberately do NOT assert specific version numbers from the real
committed file. That file changes on every release, and a test that hardcodes
"1.2.4" turns each version bump into a failing test for no defect.
"""
import json

import pytest

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def test_requires_auth(client):
    assert client.get("/api/v1/versions").status_code == 401


def test_payload_shape(logged_in):
    body = logged_in.get("/api/v1/versions").get_json()
    for key in ("generated_at", "basis", "live", "stale",
                "ui_versions", "bot_versions", "pairs", "ranges"):
        assert key in body, f"missing {key}"
    assert isinstance(body["ui_versions"], list)
    assert isinstance(body["pairs"], list)
    assert isinstance(body["stale"], bool)


def test_live_versions_come_from_version_json(logged_in):
    """`live` is read per-request, so the page can never disagree with the
    sidebar — which reads the same helper."""
    from swingbot.admin import helpers

    body = logged_in.get("/api/v1/versions").get_json()
    assert body["live"]["ui"] == helpers.get_versions()["ui"]
    assert body["live"]["bot"] == helpers.get_versions()["bot"]


def test_every_pair_is_covered_by_a_range(logged_in):
    """Each ui version's range must actually span the pairs recorded for it.

    This is the property the page's bars rely on: a bar drawn from bot_min to
    bot_max is a lie if some pair for that ui sits outside it.
    """
    body = logged_in.get("/api/v1/versions").get_json()
    if not body["pairs"]:
        pytest.skip("no frozen history in this checkout")

    order = {v: i for i, v in enumerate(body["bot_versions"])}
    spans = {r["ui"]: (order[r["bot_min"]], order[r["bot_max"]]) for r in body["ranges"]}

    for pair in body["pairs"]:
        lo, hi = spans[pair["ui"]]
        assert lo <= order[pair["bot"]] <= hi, (
            f"ui {pair['ui']} shipped with bot {pair['bot']}, outside its own range")


def test_ranges_cover_every_ui_version_exactly_once(logged_in):
    body = logged_in.get("/api/v1/versions").get_json()
    if not body["pairs"]:
        pytest.skip("no frozen history in this checkout")
    assert sorted(r["ui"] for r in body["ranges"]) == sorted(body["ui_versions"])


def test_missing_history_file_still_renders(logged_in, monkeypatch):
    """A checkout where the generator was never run must not 500 the page."""
    from swingbot.admin.api_v1 import versions

    monkeypatch.setattr(versions, "HISTORY_PATH", "/nonexistent/version_history.json")
    resp = logged_in.get("/api/v1/versions")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["pairs"] == []
    assert body["generated_at"] is None
    # Live versions still resolve, so the page can say what is running now.
    assert body["live"]["ui"]


def test_corrupt_history_file_still_renders(logged_in, monkeypatch, tmp_path):
    bad = tmp_path / "version_history.json"
    bad.write_text("{not json", encoding="utf-8")

    from swingbot.admin.api_v1 import versions

    monkeypatch.setattr(versions, "HISTORY_PATH", str(bad))
    body = logged_in.get("/api/v1/versions").get_json()
    assert body["pairs"] == []


def test_stale_flag_set_when_frozen_file_lags_version_json(logged_in, monkeypatch, tmp_path):
    """The case this flag exists for: a release bump with no regeneration."""
    frozen = tmp_path / "version_history.json"
    frozen.write_text(json.dumps({
        "generated_at": "2020-01-01 00:00:00 UTC",
        "basis": "test",
        "current": {"ui": "0.0.1", "bot": "0.0.1"},
        "ui_versions": ["0.0.1"], "bot_versions": ["0.0.1"],
        "pairs": [{"ui": "0.0.1", "bot": "0.0.1",
                   "first_seen": "2020-01-01", "last_seen": "2020-01-01"}],
        "ranges": [{"ui": "0.0.1", "bot_min": "0.0.1", "bot_max": "0.0.1",
                    "bot_count": 1, "first_seen": "2020-01-01",
                    "last_seen": "2020-01-01"}],
    }), encoding="utf-8")

    from swingbot.admin.api_v1 import versions

    monkeypatch.setattr(versions, "HISTORY_PATH", str(frozen))
    body = logged_in.get("/api/v1/versions").get_json()
    assert body["stale"] is True
    assert body["live"]["ui"] != "0.0.1"


def test_not_stale_when_frozen_file_matches(logged_in, monkeypatch, tmp_path):
    from swingbot.admin import helpers
    from swingbot.admin.api_v1 import versions

    live = helpers.get_versions()
    frozen = tmp_path / "version_history.json"
    frozen.write_text(json.dumps({
        "generated_at": "2026-01-01 00:00:00 UTC",
        "basis": "test",
        "current": {"ui": live["ui"], "bot": live["bot"]},
        "ui_versions": [], "bot_versions": [], "pairs": [], "ranges": [],
    }), encoding="utf-8")

    monkeypatch.setattr(versions, "HISTORY_PATH", str(frozen))
    assert logged_in.get("/api/v1/versions").get_json()["stale"] is False
