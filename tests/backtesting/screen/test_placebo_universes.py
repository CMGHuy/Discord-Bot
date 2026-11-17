"""v230 A1: the placebo universes reproduce from their seeds and carry no
serial structure (shuffled) or drift (gbm) by construction."""
import hashlib
import json
import zlib

import numpy as np
import pandas as pd
import pytest

from scripts.backtest import screen_idea
from swingbot.core.backtesting.screen import indicators, placebo
from tests.backtesting.screen.helpers import random_walk

CAL = pd.bdate_range("2010-01-04", periods=600)


def _source(tmp_path, n=600, tickers=("AAA", "BBB", "CCC")):
    """A fake cache: three tickers, SPY, two context-only stems, a coverage file."""
    src = tmp_path / "src"
    src.mkdir()
    for seed, t in enumerate(tickers, start=1):
        random_walk(n, seed=seed).to_csv(src / f"{t}.csv", index_label="Date")
    random_walk(n, seed=99).to_csv(src / "SPY.csv", index_label="Date")
    for stem in ("^VIX", "BREADTH_ATR1"):
        random_walk(n, seed=98).to_csv(src / f"{stem}.csv", index_label="Date")
    (src / "_coverage_sp500_pit.json").write_text("{}", encoding="utf-8")
    return src


def test_ticker_seed_is_the_base_and_the_crc_of_the_name():
    assert placebo.ticker_seed("G001") == [42, zlib.crc32(b"G001")]
    assert placebo.ticker_seed("G001", base=7) == [7, zlib.crc32(b"G001")]


def test_trading_calendar_cuts_and_sorts(tmp_path):
    src = _source(tmp_path)
    cal = placebo.trading_calendar(src / "SPY.csv", "2010-02-01", "2010-03-31")
    assert cal[0] == pd.Timestamp("2010-02-01") and cal[-1] == pd.Timestamp("2010-03-31")
    assert cal.is_monotonic_increasing and cal.is_unique
    with pytest.raises(ValueError, match="no session"):
        placebo.trading_calendar(src / "SPY.csv", "2030-01-01", "2030-12-31")


def test_read_frame_keeps_ohlcv_sorted_and_unique(tmp_path):
    df = random_walk(5, seed=1)
    shuffled = pd.concat([df.iloc[[3, 1, 0, 2, 4]], df.iloc[[1]]])
    shuffled.assign(Extra=1).to_csv(tmp_path / "X.csv", index_label="Date")
    out = placebo.read_frame(tmp_path / "X.csv")
    assert list(out.columns) == list(placebo.OHLCV)
    assert out.index.is_monotonic_increasing and out.index.is_unique and len(out) == 5


def test_market_states_are_seeded_and_switch():
    cal = pd.bdate_range("2010-01-04", periods=2516)
    a, b = placebo.market_states(cal, 42), placebo.market_states(cal, 42)
    assert a.dtype == bool and np.array_equal(a, b)
    assert not np.array_equal(a, placebo.market_states(cal, 43))
    assert 0.05 < a.mean() < 0.35


def test_gbm_frame_is_seeded_per_ticker_and_consistent():
    stressed = np.zeros(len(CAL), dtype=bool)
    one = placebo.gbm_frame("G001", CAL, level=0.02, stressed=stressed)
    pd.testing.assert_frame_equal(one, placebo.gbm_frame("G001", CAL, level=0.02,
                                                         stressed=stressed))
    other = placebo.gbm_frame("G002", CAL, level=0.02, stressed=stressed)
    assert not one["Close"].equals(other["Close"])
    assert not one["Close"].equals(
        placebo.gbm_frame("G001", CAL, level=0.02, stressed=stressed, seed=7)["Close"])
    assert list(one.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert (one["High"] >= one[["Open", "Close"]].max(axis=1)).all()
    assert (one["Low"] <= one[["Open", "Close"]].min(axis=1)).all()
    assert one.index.equals(CAL)


def test_gbm_median_atr_pct_lands_on_its_level():
    cal = pd.bdate_range("2010-01-04", periods=2516)
    stressed = placebo.market_states(cal, 42)
    ratios = []
    for i in range(10):
        df = placebo.gbm_frame(f"G{i:03d}", cal, level=0.02, stressed=stressed)
        ratios.append(np.nanmedian(indicators.atr(df) / df["Close"]) / 0.02)
    assert 0.85 < np.mean(ratios) < 1.15


def test_gbm_is_driftless():
    cal = pd.bdate_range("2010-01-04", periods=2516)
    stressed = np.zeros(len(cal), dtype=bool)
    gross = [df["Close"].iloc[-1] / df["Close"].iloc[0]
             for df in (placebo.gbm_frame(f"G{i:03d}", cal, level=0.015, stressed=stressed)
                        for i in range(60))]
    assert abs(np.mean(gross) - 1.0) < 0.25


def test_atr_pct_quartiles_skip_index_and_context_files(tmp_path):
    src = _source(tmp_path)
    assert [p.stem for p in placebo._source_files(src)] == ["AAA", "BBB", "CCC"]
    q = placebo.atr_pct_quartiles(src, CAL)
    assert len(q) == 4 and list(q) == sorted(q) and all(v > 0 for v in q)
    only = placebo.atr_pct_quartiles(src, CAL, tickers=["AAA"])
    assert len(set(only)) == 1
    with pytest.raises(ValueError, match="no ATR%"):
        placebo.atr_pct_quartiles(src, CAL, tickers=["ZZZ"])


def _digest(directory):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.iterdir())}


def test_equal_weight_index_averages_returns_and_ratios():
    idx = pd.bdate_range("2010-01-04", periods=2)
    up = pd.DataFrame({"Open": [10.0, 11.0], "High": [10.5, 11.5], "Low": [9.5, 10.5],
                       "Close": [10.0, 11.0], "Volume": [1.0, 1.0]}, index=idx)
    flat = pd.DataFrame({"Open": [20.0, 20.0], "High": [21.0, 22.0], "Low": [19.0, 18.0],
                         "Close": [20.0, 20.0], "Volume": [2.0, 2.0]}, index=idx)
    out = placebo.equal_weight_index({"A": up, "B": flat})
    assert out["Close"].tolist() == pytest.approx([100.0, 105.0])
    assert out["High"].iloc[1] == pytest.approx(105.0 * (11.5 / 11.0 + 22.0 / 20.0) / 2)
    assert out["Volume"].tolist() == [3.0, 3.0]
    assert (out["High"] >= out[["Open", "Close"]].max(axis=1)).all()


def test_write_universe_lays_out_a_screen_cache(tmp_path):
    calm = np.zeros(len(CAL), dtype=bool)
    frames = {"B": placebo.gbm_frame("B", CAL, level=0.02, stressed=calm),
              "A": placebo.gbm_frame("A", CAL, level=0.02, stressed=calm)}
    out = placebo.write_universe(tmp_path / "u", frames, kind="test", meta={"extra": 1})
    assert sorted(p.name for p in out.iterdir()) == [
        "A.csv", "B.csv", "SPY.csv", "membership.csv", "universe.json"]
    assert (out / "membership.csv").read_text(encoding="utf-8") == (
        "ticker,start_date,end_date\nA,2010-01-04,\nB,2010-01-04,\n")
    manifest = json.loads((out / "universe.json").read_text(encoding="utf-8"))
    assert manifest == {"kind": "test", "seed": 42, "tickers": ["A", "B"],
                        "calendar_start": "2010-01-04",
                        "calendar_end": CAL[-1].strftime("%Y-%m-%d"), "extra": 1}
    head = (out / "A.csv").read_text(encoding="utf-8").splitlines()[0]
    assert head == "Date,Open,High,Low,Close,Volume"
    assert b"\r\n" not in (out / "A.csv").read_bytes()
    assert placebo.read_frame(out / "SPY.csv").index.equals(CAL)
    with pytest.raises(ValueError, match="SPY"):
        placebo.write_universe(tmp_path / "v", {"SPY": frames["A"]}, kind="test", meta={})


def test_gbm_universe_reproduces_and_ignores_the_ticker_count(tmp_path):
    q = (0.01, 0.015, 0.02, 0.03)
    a = placebo.gbm_universe(tmp_path / "a", CAL, q, n_tickers=5)
    b = placebo.gbm_universe(tmp_path / "b", CAL, q, n_tickers=5)
    c = placebo.gbm_universe(tmp_path / "c", CAL, q, n_tickers=3)
    assert _digest(a) == _digest(b)
    for t in ("G000", "G001", "G002"):
        assert (a / f"{t}.csv").read_bytes() == (c / f"{t}.csv").read_bytes()
    manifest = json.loads((a / "universe.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "gbm" and manifest["tickers"] == [f"G{i:03d}" for i in range(5)]
    assert manifest["quartiles"] == list(q) and manifest["seed"] == 42
    d = placebo.gbm_universe(tmp_path / "d", CAL, q, n_tickers=3, seed=7)
    assert (d / "G000.csv").read_bytes() != (c / "G000.csv").read_bytes()


def test_day_permutation_keeps_day_zero():
    perm = placebo.day_permutation(50, 42)
    assert perm[0] == 0 and sorted(perm) == list(range(50))
    assert np.array_equal(perm, placebo.day_permutation(50, 42))
    assert not np.array_equal(perm, placebo.day_permutation(50, [42, 1]))


def test_shuffle_frame_moves_whole_days():
    df = random_walk(40, seed=3)
    perm = placebo.day_permutation(40, 42)
    out = placebo.shuffle_frame(df, perm)
    ret = df["Close"].pct_change().to_numpy()
    new = out["Close"].pct_change().to_numpy()
    assert out["Close"].iloc[0] == df["Close"].iloc[0]
    assert np.allclose(new[1:], ret[perm][1:])
    assert np.allclose((out["Open"] / out["Close"]).to_numpy(),
                       (df["Open"] / df["Close"]).to_numpy()[perm])
    assert np.array_equal(out["Volume"].to_numpy(), df["Volume"].to_numpy()[perm])
    assert out.index.equals(df.index)


def test_shuffled_universe_keeps_cross_sections_and_reproduces(tmp_path):
    src = _source(tmp_path)
    random_walk(500, seed=5).to_csv(src / "DDD.csv", index_label="Date")   # short: dropped
    a = placebo.shuffled_universe(tmp_path / "a", src, CAL)
    b = placebo.shuffled_universe(tmp_path / "b", src, CAL)
    assert _digest(a) == _digest(b)
    manifest = json.loads((a / "universe.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "shuffled" and manifest["tickers"] == ["AAA", "BBB", "CCC"]
    assert sorted(manifest["source_sha256"]) == ["AAA.csv", "BBB.csv", "CCC.csv"]
    assert manifest["source_sha256"]["AAA.csv"] == hashlib.sha256(
        (src / "AAA.csv").read_bytes()).hexdigest()
    rets = {t: placebo.read_frame(a / f"{t}.csv")["Close"].pct_change() for t in ("AAA", "BBB")}
    orig = {t: placebo.read_frame(src / f"{t}.csv")["Close"].pct_change() for t in ("AAA", "BBB")}
    pairs = sorted(zip(rets["AAA"].round(4)[1:], rets["BBB"].round(4)[1:]))
    assert pairs == sorted(zip(orig["AAA"].round(4)[1:], orig["BBB"].round(4)[1:]))


def test_shuffled_copies_add_suffixed_tickers(tmp_path):
    src = _source(tmp_path)
    out = placebo.shuffled_universe(tmp_path / "u", src, CAL, copies=2)
    manifest = json.loads((out / "universe.json").read_text(encoding="utf-8"))
    assert manifest["tickers"] == ["AAA", "AAA_C1", "BBB", "BBB_C1", "CCC", "CCC_C1"]
    assert manifest["copies"] == 2
    assert (out / "AAA.csv").read_bytes() != (out / "AAA_C1.csv").read_bytes()


def test_shuffled_universe_refuses_a_cache_without_full_tickers(tmp_path):
    src = _source(tmp_path, n=500)
    with pytest.raises(ValueError, match="every calendar session"):
        placebo.shuffled_universe(tmp_path / "u", src, CAL)


@pytest.mark.parametrize("existing", [False, True])
def test_write_universe_manifest_is_atomic_and_last(tmp_path, monkeypatch, existing):
    out = tmp_path / "u"
    out.mkdir()
    manifest = out / "universe.json"
    if existing:
        manifest.write_text('{"old": true}', encoding="utf-8")

    def interrupt_publish(source, target):
        assert source.parent == target.parent == out
        assert target == manifest
        assert not manifest.exists()
        assert json.loads(source.read_text(encoding="utf-8"))["tickers"] == ["A"]
        assert (out / "membership.csv").is_file()
        assert placebo.read_frame(out / "SPY.csv").index.equals(CAL)
        assert placebo.read_frame(out / "A.csv").index.equals(CAL)
        raise OSError("interrupted publication")

    monkeypatch.setattr(type(out), "replace", interrupt_publish)
    with pytest.raises(OSError, match="interrupted publication"):
        placebo.write_universe(out, {"A": random_walk(len(CAL))}, kind="test", meta={})
    assert not manifest.exists()


def test_write_universe_failed_rewrite_removes_completion_marker(tmp_path, monkeypatch):
    out = tmp_path / "u"
    out.mkdir()
    manifest = out / "universe.json"
    manifest.write_text('{"old": true}', encoding="utf-8")

    def fail_csv(path, frame):
        path.write_text("Date,Open", encoding="utf-8")
        raise OSError("interrupted CSV")

    monkeypatch.setattr(placebo, "_write_csv", fail_csv, raising=False)
    with pytest.raises(OSError, match="interrupted CSV"):
        placebo.write_universe(out, {"A": random_walk(len(CAL))}, kind="test", meta={})
    assert not manifest.exists()


@pytest.mark.parametrize("frames", [{}, {"A": pd.DataFrame(columns=placebo.OHLCV)}])
def test_write_universe_refuses_empty_data(tmp_path, frames):
    with pytest.raises(ValueError, match="empty"):
        placebo.write_universe(tmp_path / "u", frames, kind="test", meta={})
    assert not (tmp_path / "u" / "universe.json").exists()


def test_shuffled_copies_round_trip_through_screen_universe_reader(tmp_path):
    src = _source(tmp_path)
    out = placebo.shuffled_universe(tmp_path / "u", src, CAL, copies=3)
    universe = screen_idea.load_universe(
        out, out / "membership.csv", CAL[0].strftime("%Y-%m-%d"),
        CAL[-1].strftime("%Y-%m-%d"))
    ticker_stems = {path.stem for path in out.glob("*.csv")}
    ticker_stems -= {"SPY", "membership"}
    # Exact names detect case mismatches even on a case-insensitive filesystem.
    assert set(universe.members) == ticker_stems
    assert universe.cached == universe.members
    assert universe.missing == []
