"""The four sources that stay files raise their SSE concern themselves (v116)."""
import threading

from swingbot.core.db import events, notify


def _capture(db_engine, channel, action):
    got, stop = [], threading.Event()

    def on_listening():
        action()

    def on_event(name):
        if name == channel:
            got.append(name)
            stop.set()

    timer = threading.Timer(3.0, stop.set)
    timer.start()
    notify.listen((channel,), on_event, stop, poll=0.05,
                  dsn=db_engine.url.render_as_string(hide_password=False),
                  on_listening=on_listening)
    timer.cancel()
    return got


def test_publish_raises_a_notify(db_engine):
    assert _capture(db_engine, "analytics", lambda: notify.publish("analytics")) == ["analytics"]


def test_publish_never_raises_without_a_database(monkeypatch):
    from swingbot.core.db import engine
    monkeypatch.setattr(engine, "get_engine", lambda: (_ for _ in ()).throw(OSError("down")))
    notify.publish("scan")


def test_the_analytics_snapshot_writer_publishes(db_engine, tmp_path):
    from swingbot.core.analytics.snapshots import save_snapshot
    got = _capture(db_engine, "analytics",
                   lambda: save_snapshot({"x": 1}, str(tmp_path / "snap.json")))
    assert got == ["analytics"]


def test_the_telemetry_writer_publishes(db_engine, tmp_path):
    from swingbot.core.scanning.telemetry import log_scan_telemetry
    got = _capture(db_engine, "scan",
                   lambda: log_scan_telemetry({"duration_s": 1.0}, str(tmp_path / "t.jsonl")))
    assert got == ["scan"]


def test_the_scan_snapshot_writer_publishes(db_engine, tmp_path, monkeypatch):
    from swingbot.core.scanning import snapshots
    monkeypatch.setattr(snapshots, "_SNAPSHOT_PATH", str(tmp_path / "s.json"))
    got = _capture(db_engine, "scan", lambda: snapshots._save_scan_snapshots({"x": 1}))
    assert got == ["scan"]


def test_the_env_writer_publishes(db_engine, tmp_path, monkeypatch):
    from swingbot.admin import helpers
    monkeypatch.setattr(helpers, "ENV_PATH", str(tmp_path / ".env"))
    got = _capture(db_engine, "settings", lambda: helpers._write_env_text("A=1\n"))
    assert got == ["settings"]


def test_every_sse_event_has_a_table_or_a_file_publisher():
    raised = set(events.TABLE_CHANNELS.values()) | set(events.FILE_PUBLISHERS.values())
    assert raised == set(events.SSE_EVENTS)


def test_the_refresher_cycle_publishes_market(db_engine, monkeypatch):
    """v201: not a file, but the same rule -- a cycle that changed something
    raises `market` itself through notify.publish (no table trigger)."""
    from swingbot.refresher import loop
    from swingbot.refresher.symbols import SymbolSet
    from tests.refresher.test_loop import FakeBeat, FakeQueue

    def changed(ctx):
        ctx.report.changed = True
    monkeypatch.setattr(loop, "refresh_queue_repo", FakeQueue)
    monkeypatch.setattr(loop, "refresher_heartbeat_repo", FakeBeat)
    monkeypatch.setattr(loop, "symbol_set", lambda: SymbolSet((), ()))
    monkeypatch.setattr(loop, "_scan_running", lambda: False)
    # The cycle idles under the ADMIN_REFRESHER / MARKETDATA_LAYER kill switch.
    monkeypatch.setattr(loop.config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(loop.config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(loop, "STEPS", [changed])
    assert "market" in events.FILE_PUBLISHERS.values()
    assert _capture(db_engine, "market", loop.run_cycle) == ["market"]
