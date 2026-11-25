"""v245 V245-2/V245-2b: the analysis profiler (spec § Task 0 step 1)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.perf import profile_analysis as pa  # noqa: E402
from swingbot.core.market.indicators import atr  # noqa: E402


def _frame(n: int = 260, seed: int = 5) -> pd.DataFrame:
    """A wave with 2.5x volume on every ±5-bar extreme (the trendline scanner needs it)."""
    rng = np.random.RandomState(seed)
    base = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, n)))
    close = np.round(base * (1.0 + 0.06 * np.sin(2 * np.pi * np.arange(n) / 37.0)), 4)
    volume = np.full(n, 1_000_000.0)
    for i in range(n):
        window = close[max(0, i - 5): i + 6]
        if close[i] in (window.max(), window.min()):
            volume[i] = 2_500_000.0
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                         "Close": close, "Volume": volume},
                        index=pd.bdate_range("2023-01-02", periods=n))


def test_every_candidate_resolves_to_a_function():
    labels = [label for label, _ in pa.CANDIDATES]
    assert len(labels) == len(set(labels))
    for label, target in pa.CANDIDATES:
        assert hasattr(pa.resolve(target), "__code__"), label


def test_synth_forming_bar_appends_one_bar_half_an_atr_wide():
    df = _frame()
    out = pa.synth_forming_bar(df)
    assert len(df) == 260 and len(out) == 261
    assert out.index[-1] == df.index[-1] + pd.offsets.BDay(1)
    close, half = float(df["Close"].iloc[-1]), 0.5 * float(atr(df, 14).iloc[-1])
    row = out.iloc[-1]
    assert row["Open"] == row["Close"] == close
    assert row["High"] == pytest.approx(close + half)
    assert row["Low"] == pytest.approx(close - half)
    assert row["Volume"] == df["Volume"].iloc[-1]
    pd.testing.assert_frame_equal(out.iloc[:-1], df, check_freq=False)


def test_synth_forming_bar_scales_with_atr_mult():
    df = _frame()
    narrow, wide = pa.synth_forming_bar(df, 0.5).iloc[-1], pa.synth_forming_bar(df, 1.0).iloc[-1]
    assert wide["High"] - wide["Close"] == pytest.approx(2 * (narrow["High"] - narrow["Close"]))


def test_profile_scan_counts_one_scan_per_ticker():
    stats, total_s = pa.profile_scan({"T0": _frame(), "T1": _frame(seed=6)}, ["4w"], forming=False)
    rows = {row["label"]: row for row in pa.candidate_shares(stats, total_s)}
    assert rows["_scan_one"]["calls"] == 2
    assert rows["custom_scanner_levels"]["calls"] == 2
    assert rows["_horizon_scenarios"]["calls"] == 2
    assert rows["track_record (journal)"]["calls"] == 0     # QUIET_IO never reads the journal
    assert 0.5 < rows["_scan_one"]["share"] <= 1.05
    assert all(0.0 <= row["share"] <= 1.05 for row in rows.values())


def test_candidate_shares_are_sorted_by_time():
    stats, total_s = pa.profile_scan({"T0": _frame()}, ["4w"], forming=False)
    times = [row["cum_s"] for row in pa.candidate_shares(stats, total_s)]
    assert times == sorted(times, reverse=True)


def test_profile_scan_forming_feeds_the_synthesised_close(monkeypatch):
    seen = []

    def fake(ticker, df, horizons, *args, live_prices=None, io=None, **kwargs):
        seen.append((ticker, len(df), live_prices, io))
        return {}

    monkeypatch.setattr(pa.analyze, "_scan_one", fake)
    df = _frame()
    pa.profile_scan({"T0": df}, ["4w"], forming=True)
    pa.profile_scan({"T0": df}, ["4w"], forming=False, io=pa.JOURNAL_IO)
    assert seen == [("T0", len(df) + 1, {"T0": float(df["Close"].iloc[-1])}, pa.QUIET_IO),
                    ("T0", len(df), None, pa.JOURNAL_IO)]


def test_load_frames_skips_missing_and_empty(monkeypatch):
    from swingbot.core.marketdata import training_data
    frames = {"A": _frame(), "B": None, "C": _frame().iloc[:0]}
    monkeypatch.setattr(training_data, "load_daily", lambda ticker: frames[ticker])
    assert list(pa.load_frames(["A", "B", "C"])) == ["A"]
