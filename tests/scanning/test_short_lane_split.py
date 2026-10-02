"""V118-3: the SHORT extra lane is built beside the base scan, never inside it."""
import datetime as dt
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata.universe import ShortSnapshot
from swingbot.core.scanning import analyze, fetch, scan_run
from swingbot.core.scanning.short_candidates import (ShortCandidate,
                                                     ShortReference,
                                                     extra_symbols)

BEAR = SimpleNamespace(trend="bearish")
END = pd.Timestamp("2026-09-18")
AFTER_CLOSE = dt.datetime(2026, 9, 18, 22, 0, tzinfo=dt.timezone.utc)
PANEL = (-0.20, -0.10, 0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35)


def frame(first, last, n=260):
    idx = pd.bdate_range(end=END, periods=n)
    close = np.full(n, float(first))
    close[-1] = last
    return pd.DataFrame({"Close": close, "Open": close, "High": close,
                         "Low": close, "Volume": 1e6}, index=idx)


def reference(frames, regime=BEAR):
    return ShortReference(frames=frames, spy=frame(100, 99), sector_frames={},
                          spy_regime=regime, reference_rels=PANEL,
                          now=AFTER_CLOSE, reference_id="ref-1")


SNAP = ShortSnapshot(("AAA", "BBB", "CCC"), "2026-09-01", {})


def test_extra_symbols_drop_base_tickers():
    assert extra_symbols(SNAP, ["BBB"]) == ("AAA", "CCC")


def test_duplicate_of_base_is_never_an_extra_candidate():
    frames = {"AAA": frame(100, 70), "BBB": frame(100, 70), "CCC": frame(100, 120)}
    got = scan_run.build_extra_candidates(
        ["BBB"], decision_date="2026-09-18", snapshot=SNAP, reference=reference(frames))
    assert got == [ShortCandidate("AAA", "broad", "short_universe", "2026-09-18",
                                  "2026-09-01", "ref-1")]


@pytest.mark.parametrize("snapshot, ref_frames, regime, reason", [
    (None, {"AAA": frame(100, 70)}, BEAR, "no_snapshot"),
    (SNAP, None, BEAR, "no_reference"),
    (SNAP, {"AAA": frame(100, 70)}, None, "missing_regime"),
])
def test_missing_inputs_give_empty_list_with_named_reason(snapshot, ref_frames, regime, reason, caplog):
    ref = None if ref_frames is None else reference(ref_frames, regime)
    with caplog.at_level("INFO"):
        got = scan_run.build_extra_candidates(
            [], decision_date="2026-09-18", snapshot=snapshot, reference=ref)
    assert got == []
    assert reason in caplog.text


def test_symbol_without_data_is_skipped_not_raised():
    got = scan_run.build_extra_candidates(
        [], decision_date="2026-09-18", snapshot=SNAP, reference=reference({}))
    assert got == []


# --- base invariance through the real _sync_run_scan -------------------------

_FIXTURE_SNAPSHOT = object()


def _run_base_scan(monkeypatch, short_on, snapshot=_FIXTURE_SNAPSHOT):
    base = {"BASE": frame(100, 110), "SPY": frame(100, 99), "BBB": frame(100, 104),
            "B1": frame(100, 105), "B2": frame(100, 120), "B3": frame(100, 130)}
    seen = {"tickers": [], "rs_rels": None, "breadth": None, "strategy": None}

    def fake_scan_one(ticker, df, *_a, rs_cache=None, breadth=None, **_k):
        seen["tickers"].append(ticker)
        seen["rs_rels"] = dict(rs_cache["rels"]) if rs_cache else None
        seen["breadth"] = breadth
        return None

    def fake_strategy(**kw):
        seen["strategy"] = (tuple(kw["tickers"]), tuple(kw["fresh_data"]))
        kw["alerts"].append(("LONG", tuple(kw["tickers"])))
        return {"strategy_plans": 0, "strategy_opened": 0}

    extra_frames = {"AAA": frame(100, 70)}
    snap = ShortSnapshot(("AAA", "BBB"), "2026-09-01", {}) if snapshot is _FIXTURE_SNAPSHOT else snapshot
    monkeypatch.setattr(config, "SHORT_UNIVERSE_ENABLED", short_on)
    monkeypatch.setattr(config, "SCAN_UNIVERSE", "watchlist")
    monkeypatch.setattr(scan_run, "_reload_config_before_scan", lambda: {})
    monkeypatch.setattr(scan_run, "load_watchlist", lambda: ["BASE", "BBB", "B1", "B2", "B3"])
    monkeypatch.setattr(fetch, "_crawl_latest_data",
                        lambda t, p=None: {s: base[s] for s in [*t, "SPY"] if s in base}
                        | {s: extra_frames[s] for s in t if s in extra_frames})
    monkeypatch.setattr(fetch, "_fetch_live_prices", lambda *a: {})
    monkeypatch.setattr(fetch, "_fetch_frames", lambda syms: {})
    monkeypatch.setattr(fetch, "_sector_etfs_for_tickers", lambda t: ({}, []))
    monkeypatch.setattr(analyze, "_scan_one", fake_scan_one)
    monkeypatch.setattr(scan_run, "_maybe_run_strategy_pass", fake_strategy)
    monkeypatch.setattr(scan_run.universe, "short_snapshot", lambda day, live: snap)
    monkeypatch.setattr(scan_run, "_short_now", lambda: AFTER_CLOSE)
    monkeypatch.setattr(scan_run, "load_account_config", lambda: {})
    monkeypatch.setattr(scan_run.heat_mod, "open_heat", lambda *a: 0.0)
    monkeypatch.setattr(scan_run.telemetry, "log_scan_telemetry", lambda s: None)
    monkeypatch.setattr(scan_run.telemetry, "scan_slowdown", lambda: False)
    monkeypatch.setattr(scan_run, "TradeLog", lambda: SimpleNamespace(get_trades=lambda **k: []))
    alerts, _closed, _warn = scan_run._sync_run_scan("all", False)
    return SimpleNamespace(tickers=sorted(seen["tickers"]), breadth=seen["breadth"],
                           rs_rels=seen["rs_rels"], strategy=seen["strategy"],
                           long_payloads=list(alerts))


def test_base_inputs_are_identical_with_flag_off_and_on(monkeypatch, caplog):
    base_off = _run_base_scan(monkeypatch, False)
    with caplog.at_level("INFO"):
        base_on = _run_base_scan(monkeypatch, True)
    assert "SHORT extra lane: 1 candidate(s)" in caplog.text   # AAA only; BBB is base
    assert base_off.tickers == base_on.tickers == ["B1", "B2", "B3", "BASE", "BBB"]
    assert base_off.breadth == base_on.breadth
    assert base_off.rs_rels == base_on.rs_rels
    assert base_off.strategy == base_on.strategy
    assert base_off.long_payloads == base_on.long_payloads
    assert "AAA" not in base_on.tickers and "AAA" not in base_on.strategy[1]
    assert "AAA" not in (base_on.rs_rels or {})


def test_flag_defaults_off():
    assert config.SHORT_UNIVERSE_ENABLED is False


def test_stale_snapshot_records_no_snapshot_and_leaves_base_alone(monkeypatch, caplog):
    base_off = _run_base_scan(monkeypatch, False)
    with caplog.at_level("INFO"):
        base_on = _run_base_scan(monkeypatch, True, snapshot=None)
    assert "no_snapshot" in caplog.text
    assert "SHORT extra lane failed" not in caplog.text
    assert "SHORT extra lane: 0 candidate(s)" in caplog.text
    assert base_off.tickers == base_on.tickers
    assert base_off.strategy == base_on.strategy
    assert base_off.long_payloads == base_on.long_payloads
