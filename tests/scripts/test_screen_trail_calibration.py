"""v163 A/A calibration script: generator, replicate smoke test, CLI."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_trail_calibration as cal  # noqa: E402

from swingbot.core.backtesting.screen import verdict  # noqa: E402

SMALL = {"tickers": 2, "n_resamples": 200}
QUIET = {"out": lambda *a, **k: None}


def _v(label, n, delta, low, high):
    return verdict.Verdict(label, n, delta, low, high, None, 0, {}, {})


FAKE = [_v(verdict.SCREEN_PASS, 400, 0.2, 0.05, 0.3),
        _v(verdict.SCREEN_FAIL, 380, 0.01, -0.05, 0.07),
        _v(verdict.SCREEN_UNDERPOWERED, 0, None, None, None),
        _v(verdict.SCREEN_FAIL, 350, -0.02, -0.08, 0.04)]


def _fake_replicates(monkeypatch, verdicts):
    seeds = []
    feed = iter(verdicts)

    def fake(seed, **kwargs):
        seeds.append(seed)
        return next(feed)

    monkeypatch.setattr(cal, "replicate", fake)
    return seeds


def test_synthetic_frame_is_valid_ohlcv_inside_the_window():
    df = cal.synthetic_frame(np.random.default_rng(1))
    assert len(df) == cal.BARS
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    prices = df[["Open", "High", "Low", "Close"]]
    assert not df.isna().any().any() and (prices > 0).all().all()
    assert (df["High"] >= df[["Open", "Close"]].max(axis=1)).all()
    assert (df["Low"] <= df[["Open", "Close"]].min(axis=1)).all()
    assert df.index[0] == pd.Timestamp("2010-01-04")
    assert df.index[-1] <= pd.Timestamp("2019-12-31") and df.index.year.max() == 2019


def test_synthetic_returns_are_fat_tailed_and_volatility_clustered():
    df = cal.synthetic_frame(np.random.default_rng(2), bars=20_000)
    r = np.diff(np.log(df["Close"].to_numpy()))
    z = (r - r.mean()) / r.std()
    assert np.mean(z ** 4) > 4.0                       # a Gaussian's kurtosis is 3
    ranks = np.argsort(np.argsort(np.abs(r)))          # rank autocorrelation of |r|
    assert np.corrcoef(ranks[:-1], ranks[1:])[0, 1] > 0.03


def test_random_events_carry_the_rate_and_the_index():
    idx = pd.bdate_range("2010-01-04", periods=10_000)
    events = cal.random_events(idx, np.random.default_rng(3))
    assert events.index.equals(idx) and events.dtype == bool
    assert abs(events.mean() - cal.EVENT_RATE) < 0.005


def test_a_replicate_runs_the_real_screen_and_verdict_deterministically():
    a = cal.replicate(11, **SMALL)
    assert isinstance(a, verdict.Verdict) and a.n > 0
    assert cal.replicate(11, **SMALL) == a
    assert cal.replicate(12, **SMALL).delta_exp_r != a.delta_exp_r


def test_a_replicate_races_the_trail_shape(monkeypatch):
    shapes = []
    real = cal.screen_idea.race.run_book

    def spy(*args, **kwargs):
        shapes.append(kwargs.get("shape"))
        return real(*args, **kwargs)

    monkeypatch.setattr(cal.screen_idea.race, "run_book", spy)
    cal.replicate(5, tickers=1, n_resamples=100)
    assert shapes and set(shapes) == {"trail"}


def test_calibrate_counts_false_passes_and_coverage(monkeypatch):
    seeds = _fake_replicates(monkeypatch, FAKE)
    out = cal.calibrate(4, seed=100, **QUIET)
    assert seeds == [100, 101, 102, 103]
    assert out["replicates"] == 4 and len(out["verdicts"]) == 4
    assert out["false_pass"] == 1 and out["false_pass_rate"] == 0.25
    assert out["covered"] == 2 and out["coverage"] == 0.5     # no interval never covers
    assert out["mean_n"] == pytest.approx((400 + 380 + 0 + 350) / 4)


def test_calibrate_refuses_zero_replicates():
    with pytest.raises(ValueError):
        cal.calibrate(0, **QUIET)


def test_render_states_the_rate_the_rule_the_generator_and_every_seed(monkeypatch):
    _fake_replicates(monkeypatch, FAKE)
    result = cal.calibrate(4, seed=100, **QUIET)
    params = {"replicates": 4, "seed": 100, "tickers": 2, "resamples": 200}
    text = cal.render(result, params, "2026-10-15")
    assert text.startswith("# v163 trail race A/A calibration -> **over** the 5% false-pass limit")
    for needle in ("1 of 4 = 25.0%", "≤ 5% (gating)", "2 of 4 = 50.0%", "reported, not gated",
                   "df = 3", "0.01 / 0.025", "seed 100", "--replicates 4 --seed 100",
                   "SCREEN-PASS 1, SCREEN-FAIL 2, SCREEN-UNDERPOWERED 1", "| 103 |",
                   "no cached price file"):
        assert needle in text, needle


def test_dry_run_prints_the_doc_and_writes_nothing(tmp_path, capsys):
    code = cal.main(["--replicates", "1", "--tickers", "1", "--resamples", "100",
                     "--date", "2026-10-15", "--out-dir", str(tmp_path / "out"), "--dry-run"])
    assert code in (0, 1)
    assert "# v163 trail race A/A calibration" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()


def test_a_run_writes_the_dated_doc_and_the_exit_code_follows_the_rate(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    argv = ["--replicates", "2", "--date", "2026-10-15", "--out-dir", str(out_dir)]
    _fake_replicates(monkeypatch, [FAKE[1], FAKE[3]])
    assert cal.main(argv) == 0
    doc = out_dir / "2026-10-15-trail-race-calibration.md"
    assert "within the 5% false-pass limit" in doc.read_text(encoding="utf-8")
    _fake_replicates(monkeypatch, [FAKE[0], FAKE[1]])
    assert cal.main(argv) == 1
    assert "**over**" in doc.read_text(encoding="utf-8")


def test_the_script_never_names_a_price_cache():
    source = (ROOT / "scripts" / "backtest" / "screen_trail_calibration.py").read_text(
        encoding="utf-8")
    for forbidden in ("backtest_cache", "load_frame", "DEFAULT_CACHE", "read_csv"):
        assert forbidden not in source, forbidden
