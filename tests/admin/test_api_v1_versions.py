"""GET /api/v1/versions — the component release timeline behind the Versions page.

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


def test_live_versions_come_from_version_json(logged_in):
    """`live` is read per-request, so the page can never disagree with the
    sidebar — which reads the same helper."""
    from swingbot.admin import helpers

    body = logged_in.get("/api/v1/versions").get_json()
    assert body["live"]["ui"] == helpers.get_versions()["ui"]
    assert body["live"]["bot"] == helpers.get_versions()["bot"]


def test_missing_history_file_still_renders(logged_in, monkeypatch):
    """A checkout where the generator was never run must not 500 the page."""
    from swingbot.admin.api_v1 import versions

    monkeypatch.setattr(versions, "HISTORY_PATH", "/nonexistent/version_history.json")
    resp = logged_in.get("/api/v1/versions")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["components"] == []
    assert body["releases"] == []
    assert body["generated_at"] is None
    # Live versions still resolve, so the page can say what is running now.
    assert body["live"]["ui"]


def test_corrupt_history_file_still_renders(logged_in, monkeypatch, tmp_path):
    bad = tmp_path / "version_history.json"
    bad.write_text("{not json", encoding="utf-8")

    from swingbot.admin.api_v1 import versions

    monkeypatch.setattr(versions, "HISTORY_PATH", str(bad))
    body = logged_in.get("/api/v1/versions").get_json()
    assert body["components"] == []
    assert body["releases"] == []


def test_stale_flag_set_when_frozen_file_lags_version_json(logged_in, monkeypatch, tmp_path):
    """The case this flag exists for: a release bump with no regeneration."""
    frozen = tmp_path / "version_history.json"
    frozen.write_text(json.dumps({
        "generated_at": "2020-01-01 00:00:00 UTC",
        "basis": "test",
        "current": {"ui": "0.0.1", "bot": "0.0.1"},
        "components": ["ui", "bot"],
        "releases": [{"sha": "abc123", "date": "2020-01-01",
                      "versions": {"ui": "0.0.1", "bot": "0.0.1"}, "changed": ["ui", "bot"]}],
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
        "components": ["ui", "bot"], "releases": [],
    }), encoding="utf-8")

    monkeypatch.setattr(versions, "HISTORY_PATH", str(frozen))
    assert logged_in.get("/api/v1/versions").get_json()["stale"] is False


def test_payload_shape(logged_in):
    body = logged_in.get("/api/v1/versions").get_json()
    for key in ("generated_at", "basis", "live", "stale",
                "components", "current", "releases"):
        assert key in body, f"missing {key}"
    assert isinstance(body["components"], list)
    assert isinstance(body["releases"], list)
    assert isinstance(body["stale"], bool)
    for dead in ("ui_versions", "bot_versions", "pairs", "ranges"):
        assert dead not in body, f"{dead} is a matrix artefact and must be gone"


def test_stale_is_true_when_a_component_set_differs(logged_in, monkeypatch):
    """Adding a component to VERSION.json without regenerating leaves a page
    that looks complete and is missing a whole lane. That must read as stale."""
    from swingbot.admin.api_v1 import versions as mod
    monkeypatch.setattr(mod._helpers, "get_component_versions",
                        lambda: {"ui": "9.9.9", "bot": "9.9.9", "worker": "0.1.0"})
    assert logged_in.get("/api/v1/versions").get_json()["stale"] is True


def test_stale_is_false_when_live_matches_frozen(logged_in, monkeypatch):
    import json as _json
    from swingbot.admin.api_v1 import versions as mod
    frozen = mod._load_history()["current"]
    monkeypatch.setattr(mod._helpers, "get_component_versions", lambda: dict(frozen))
    assert logged_in.get("/api/v1/versions").get_json()["stale"] is False
