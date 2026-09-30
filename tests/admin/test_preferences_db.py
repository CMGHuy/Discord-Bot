"""UI preferences at each stage, with the size cap intact."""
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.preferences import PreferencesRepository


@pytest.fixture
def client_at(admin_app, auth, tmp_path, monkeypatch, db_committed):
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(
        config, "DATABASE_URL",
        db_committed.engine.url.render_as_string(hide_password=False))
    reset_engine()
    client = admin_app.test_client()

    def _make(stage):
        monkeypatch.setattr(config, "DB_STORES", stage)
        return client
    yield _make
    reset_engine()


def _put(client, auth, prefs):
    return client.put("/api/v1/system/preferences", json={"preferences": prefs},
                      headers=auth)


def _get(client, auth):
    return client.get("/api/v1/system/preferences", headers=auth).get_json()["preferences"]


def test_json_stage_writes_the_file(client_at, auth, tmp_path, db_committed):
    c = client_at("")
    _put(c, auth, {"columns": ["ticker", "r"]})
    assert os.path.exists(os.path.join(tmp_path, "ui_preferences.json"))
    assert PreferencesRepository().count(conn=db_committed) == 0


def test_dual_stage_writes_both(client_at, auth, tmp_path, db_committed):
    c = client_at("preferences:dual")
    _put(c, auth, {"columns": ["ticker"]})
    assert os.path.exists(os.path.join(tmp_path, "ui_preferences.json"))
    assert PreferencesRepository().load(conn=db_committed)["columns"] == ["ticker"]


def test_db_stage_round_trips_through_a_row(client_at, auth, tmp_path):
    c = client_at("preferences:db")
    _put(c, auth, {"columns": ["ticker", "r"]})
    assert _get(c, auth)["columns"] == ["ticker", "r"]
    assert not os.path.exists(os.path.join(tmp_path, "ui_preferences.json"))


def test_the_64kb_cap_still_refuses(client_at, auth, db_committed):
    c = client_at("preferences:db")
    resp = _put(c, auth, {"blob": "x" * (64 * 1024 + 1)})
    assert resp.status_code >= 400
    assert PreferencesRepository().load(conn=db_committed) == {}


def test_an_empty_store_reads_as_an_empty_dict(db_conn):
    assert PreferencesRepository().load(conn=db_conn) == {}


def test_saving_twice_keeps_one_row(db_conn):
    repo = PreferencesRepository()
    repo.save({"a": 1}, conn=db_conn)
    repo.save({"a": 2}, conn=db_conn)
    assert repo.count(conn=db_conn) == 1
    assert repo.load(conn=db_conn) == {"a": 2}
