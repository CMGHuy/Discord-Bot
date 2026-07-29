"""Snapshot tests, adapted to the post-audit sections.

The plan's version asserted inflation/labor/rates/expectations/credit/news/
fear_greed sections; every one of those provider tasks was cut by the
win-rate audit (see the G38 audit note), so the snapshot now carries VIX,
breadth, sector RS/rotation, composite, events and session.
"""
import datetime as dt

import numpy as np
import pytest

import swingbot.core.macro.snapshot as snap_mod
from tests.conftest import make_ohlcv


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(snap_mod, "SNAPSHOT_PATH", str(tmp_path / "macro_snapshot.json"))
    monkeypatch.setattr(snap_mod, "HISTORY_PATH", str(tmp_path / "snapshot_history.jsonl"))
    return tmp_path


@pytest.fixture
def all_stubbed(monkeypatch):
    """Every provider returns healthy fixture data — no network anywhere."""
    monkeypatch.setattr(snap_mod.httpcache, "LAST_SERVED_STALE", False)
    monkeypatch.setattr(snap_mod.vix, "vix_state",
                        lambda loader=None: {"level": 14.0, "percentile_1y": 30.0,
                                             "regime": "calm", "term_structure": "contango"})
    bars = {t: make_ohlcv(100.0 * (1 + 0.002) ** np.arange(220))
            for t in list(snap_mod.sectors.SECTOR_ETFS) + ["SPY"]}
    bars["XLK"] = make_ohlcv(100.0 * (1 + 0.004) ** np.arange(220))   # growth leads
    bars["XLY"] = make_ohlcv(100.0 * (1 + 0.0035) ** np.arange(220))
    bars["XLC"] = make_ohlcv(100.0 * (1 + 0.003) ** np.arange(220))
    monkeypatch.setattr(snap_mod.sectors, "sector_bars", lambda loader=None: bars)
    monkeypatch.setattr(snap_mod.calendar_events, "load_events", lambda: [
        {"date": "2026-07-15", "time_et": "08:30", "kind": "cpi",
         "label": "CPI release", "importance": 3}])
    return {"universe": lambda: bars}


def test_full_shape(paths, all_stubbed):
    now = dt.datetime(2026, 7, 14, 12, 0, tzinfo=dt.timezone.utc)
    snap = snap_mod.build_snapshot(loaders=all_stubbed, now=now)
    for section in ("risk", "composite", "sectors", "breadth", "events",
                    "session", "quality_warnings"):
        assert section in snap, section
    assert snap["stale"] is False
    assert snap["quality_warnings"] == []
    assert snap["risk"]["vix"]["regime"] == "calm"
    assert snap["events"]["next_high_impact"]["kind"] == "cpi"
    assert len(snap["sectors"]["rs_rows"]) == 11
    assert snap["composite"]["label"] == "risk_on"     # calm VIX + growth rotation + breadth


def test_event_within_24h_window(paths, all_stubbed):
    # CPI prints 2026-07-15 08:30 ET = 12:30 UTC; from 14:00 UTC the day
    # before that is 22.5h away -> inside the window.
    now = dt.datetime(2026, 7, 14, 14, 0, tzinfo=dt.timezone.utc)
    snap = snap_mod.build_snapshot(loaders=all_stubbed, now=now)
    assert [e["kind"] for e in snap["events"]["within_24h"]] == ["cpi"]
    earlier = dt.datetime(2026, 7, 13, 12, 0, tzinfo=dt.timezone.utc)
    snap2 = snap_mod.build_snapshot(loaders=all_stubbed, now=earlier)
    assert snap2["events"]["within_24h"] == []         # 48h out


def test_total_darkness_skeleton(paths, monkeypatch):
    monkeypatch.setattr(snap_mod.httpcache, "LAST_SERVED_STALE", False)
    monkeypatch.setattr(snap_mod.vix, "vix_state", lambda loader=None: None)
    monkeypatch.setattr(snap_mod.sectors, "sector_bars", lambda loader=None: {})
    monkeypatch.setattr(snap_mod.calendar_events, "load_events", lambda: [])
    snap = snap_mod.build_snapshot()
    assert snap["stale"] is True                       # the G43 contract starts here
    assert snap["composite"]["label"] == "unknown"
    assert snap["risk"]["vix"] is None
    assert snap["sectors"]["rs_rows"] == []
    assert snap["sectors"]["rotation"]["posture"] == "unknown"
    assert snap["events"]["next_high_impact"] is None
    assert snap["breadth"]["n"] == 0
    assert len(snap["quality_warnings"]) == 4


def test_provider_exception_does_not_break_build(paths, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("provider exploded")
    monkeypatch.setattr(snap_mod.httpcache, "LAST_SERVED_STALE", False)
    monkeypatch.setattr(snap_mod.vix, "vix_state", boom)
    monkeypatch.setattr(snap_mod.sectors, "sector_bars", boom)
    monkeypatch.setattr(snap_mod.calendar_events, "load_events", boom)
    snap = snap_mod.build_snapshot()                   # must not raise
    assert snap["stale"] is True and snap["risk"]["vix"] is None


def test_stale_flag_follows_httpcache(paths, all_stubbed, monkeypatch):
    monkeypatch.setattr(snap_mod.httpcache, "LAST_SERVED_STALE", False)

    def stale_vix(loader=None):
        snap_mod.httpcache.LAST_SERVED_STALE = True    # a provider served stale
        return {"level": 14.0, "percentile_1y": 30.0, "regime": "calm",
                "term_structure": "contango"}
    monkeypatch.setattr(snap_mod.vix, "vix_state", stale_vix)
    snap = snap_mod.build_snapshot(loaders=all_stubbed)
    assert snap["stale"] is True and snap["quality_warnings"] == []


def test_save_load_round_trip_and_history_line(paths, all_stubbed):
    snap = snap_mod.build_snapshot(loaders=all_stubbed)
    snap_mod.save_snapshot(snap)
    assert snap_mod.load_snapshot() == snap
    with open(snap_mod.HISTORY_PATH, encoding="utf-8") as fh:
        lines = fh.readlines()
    assert len(lines) == 1 and '"composite"' in lines[0]


def test_max_age_gate(paths, all_stubbed):
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=90)
    snap_mod.save_snapshot(snap_mod.build_snapshot(loaders=all_stubbed, now=old))
    assert snap_mod.load_snapshot(max_age_min=30) is None
    assert snap_mod.load_snapshot(max_age_min=240) is not None
