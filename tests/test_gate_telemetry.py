"""Gate telemetry counters (G135)."""
import datetime as dt

import swingbot.core.gate.telemetry as telemetry


def _tmp_telemetry(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "TELEMETRY_PATH",
                        str(tmp_path / "telemetry.jsonl"))


def test_count_then_summary_roundtrip(tmp_path, monkeypatch):
    _tmp_telemetry(tmp_path, monkeypatch)
    at = dt.datetime(2026, 7, 14, 15, 0)
    for _ in range(3):
        telemetry.count("evaluated", at=at)
    telemetry.count("blocked", at=at, reason="rf_fake_breakout")
    telemetry.count("blocked", at=at, reason="tier C < A")
    telemetry.count("downgraded", at=at)
    telemetry.count("held_for_event", at=at)
    s = telemetry.summary()
    assert s["evaluated"] == 3 and s["blocked"] == 2
    assert s["blocked_reasons"] == ["rf_fake_breakout", "tier C < A"]
    assert s["downgraded"] == 1 and s["held_for_event"] == 1


def test_summary_since_filters_by_date(tmp_path, monkeypatch):
    _tmp_telemetry(tmp_path, monkeypatch)
    telemetry.count("evaluated", at=dt.datetime(2026, 7, 13, 10, 0))
    telemetry.count("evaluated", at=dt.datetime(2026, 7, 14, 10, 0))
    assert telemetry.summary(since="2026-07-14")["evaluated"] == 1
    assert telemetry.summary()["evaluated"] == 2


def test_unknown_rate_per_provider(tmp_path, monkeypatch):
    _tmp_telemetry(tmp_path, monkeypatch)
    at = dt.datetime(2026, 7, 14, 10, 0)
    telemetry.count("provider_answer", at=at, provider="fred", unknown=False)
    telemetry.count("provider_answer", at=at, provider="fred", unknown=True)
    telemetry.count("provider_answer", at=at, provider="finnhub", unknown=False)
    rates = telemetry.summary()["unknown_rate"]
    assert rates == {"fred": 0.5, "finnhub": 0.0}


def test_count_never_raises(tmp_path, monkeypatch):
    # unwritable path → count swallows; telemetry must never cost an alert
    monkeypatch.setattr(telemetry, "TELEMETRY_PATH",
                        str(tmp_path / "no_such_dir" / "x" / "t.jsonl"))
    monkeypatch.setattr(telemetry.os, "makedirs",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("ro")))
    telemetry.count("evaluated")                           # no exception
    assert telemetry.summary(since=None)["evaluated"] == 0


def test_summary_skips_corrupt_lines(tmp_path, monkeypatch):
    _tmp_telemetry(tmp_path, monkeypatch)
    telemetry.count("evaluated", at=dt.datetime(2026, 7, 14, 10, 0))
    with open(telemetry.TELEMETRY_PATH, "a", encoding="utf-8") as fh:
        fh.write("{corrupt\n")
    assert telemetry.summary()["evaluated"] == 1


def test_recheck_held_is_a_counter_event(tmp_path, monkeypatch):
    _tmp_telemetry(tmp_path, monkeypatch)
    telemetry.count("recheck_held", at=dt.datetime(2026, 7, 14, 10, 0))
    assert telemetry.summary()["recheck_held"] == 1
