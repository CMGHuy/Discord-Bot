"""PITR alarms: one alert and one recovery per episode (v116 Phase 0)."""
import datetime as dt

from swingbot import config
from swingbot.core.infra import pitr_watch as pw

T = dt.datetime(2026, 10, 1, 10, 0, tzinfo=dt.timezone.utc)
OK = pw.ArchiverSample(0, None, T)


def test_growth_in_failed_count_is_failing():
    assert pw.archiver_failing(OK, pw.ArchiverSample(1, T, T - dt.timedelta(minutes=5))) is True


def test_a_failure_newer_than_the_last_success_is_failing_without_history():
    assert pw.archiver_failing(None, pw.ArchiverSample(3, T, T - dt.timedelta(minutes=1))) is True


def test_an_old_failure_followed_by_success_is_healthy():
    assert pw.archiver_failing(None, pw.ArchiverSample(3, T - dt.timedelta(hours=1), T)) is False


def test_archiver_alarm_fires_once_then_recovers_once():
    watch = pw.PitrWatch()
    assert watch.tick(OK, 10.0) == []
    failing = pw.ArchiverSample(1, T, T - dt.timedelta(minutes=5))
    first = watch.tick(failing, 10.0)
    assert [n.recovered for n in first] == [False]
    assert watch.tick(pw.ArchiverSample(2, T + dt.timedelta(minutes=1), T), 10.0) == []
    healed = watch.tick(pw.ArchiverSample(2, T, T + dt.timedelta(minutes=2)), 10.0)
    assert [n.recovered for n in healed] == [True]


def test_disk_alarm_is_strictly_above_eighty_percent():
    watch = pw.PitrWatch()
    assert watch.tick(None, 80.0) == []
    alert = watch.tick(None, 80.1)
    assert len(alert) == 1 and not alert[0].recovered and "80%" in alert[0].detail
    assert watch.tick(None, 95.0) == []
    assert [n.recovered for n in watch.tick(None, 50.0)] == [True]


def test_an_unreadable_archiver_changes_nothing():
    watch = pw.PitrWatch()
    watch.tick(pw.ArchiverSample(1, T, None), 10.0)
    assert watch.archiver_alarm is True
    assert watch.tick(None, 10.0) == []
    assert watch.archiver_alarm is True


def test_disk_used_pct_is_a_percentage(tmp_path):
    assert 0.0 <= pw.disk_used_pct(str(tmp_path)) <= 100.0


def test_read_archiver_reads_the_real_view(db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db.engine import reset_engine
    reset_engine()
    sample = pw.read_archiver()
    reset_engine()
    assert sample is not None and sample.failed_count >= 0
