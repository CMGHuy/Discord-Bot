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


EV = pd.Series(False, index=pd.bdate_range("2010-01-04", periods=5))


def test_wilson_interval_known_values():
    assert cal.wilson_interval(10, 200) == pytest.approx((0.027382, 0.089579), abs=1e-6)
    assert cal.wilson_interval(6, 200) == pytest.approx((0.013820, 0.063895), abs=1e-6)
    assert cal.wilson_interval(1, 4) == pytest.approx((0.045586, 0.699364), abs=1e-6)
    low, high = cal.wilson_interval(0, 200)
    assert low == 0.0 and high == pytest.approx(0.018846, abs=1e-6)


def test_wilson_interval_refuses_no_trials():
    with pytest.raises(ValueError):
        cal.wilson_interval(0, 0)


def test_doc_name_per_mode():
    assert cal.doc_name("long", "next_open", "2026-10-21") == "2026-10-21-trail-race-calibration.md"
    assert cal.doc_name("short", "next_open", "2026-10-21") == "2026-10-21-short-race-calibration.md"
    assert (cal.doc_name("short", "level", "2026-10-21")
            == "2026-10-21-short-level-race-calibration.md")
    with pytest.raises(ValueError):
        cal.doc_name("long", "level", "2026-10-21")


def test_the_long_idea_is_still_the_v163_trail_idea():
    idea = cal._idea(EV)
    assert (idea.name, idea.time_cap_bars, idea.race_shape, idea.direction, idea.entry) == (
        "aa_trail_calibration", 60, "trail", "long", "next_open")


def test_the_short_idea_is_fixed_cap_20_short():
    idea = cal._idea(EV, direction="short")
    assert cal.SHORT_CAP == 20
    assert (idea.name, idea.time_cap_bars, idea.race_shape, idea.direction, idea.entry) == (
        "aa_short_calibration", 20, "fixed", "short", "next_open")
    assert idea.events(None) is EV
    assert cal.CAL_IDEA_NAMES[("short", "level")] == "aa_short_level_calibration"
    with pytest.raises(ValueError):
        cal._idea(EV, direction="long", entry="level")


def test_a_short_replicate_races_the_fixed_shape_short(monkeypatch):
    seen = []
    real = cal.screen_idea.race.run_book

    def spy(*args, **kwargs):
        seen.append((kwargs.get("shape"), kwargs.get("direction")))
        return real(*args, **kwargs)

    monkeypatch.setattr(cal.screen_idea.race, "run_book", spy)
    v = cal.replicate(5, tickers=1, n_resamples=100, direction="short")
    assert isinstance(v, verdict.Verdict)
    assert seen and set(seen) == {("fixed", "short")}


def test_a_short_replicate_sees_the_long_replicates_frames_and_events(monkeypatch):
    seen = {"long": [], "short": []}
    real = cal.screen_idea.screen_ticker

    def spy(idea, name, df, spans, **kwargs):
        seen[idea.direction].append((name, df["Close"].to_numpy().copy(),
                                     idea.events(df).to_numpy().copy()))
        return real(idea, name, df, spans, **kwargs)

    monkeypatch.setattr(cal.screen_idea, "screen_ticker", spy)
    cal.replicate(7, tickers=2, n_resamples=100)
    cal.replicate(7, tickers=2, n_resamples=100, direction="short")
    assert len(seen["long"]) == len(seen["short"]) == 2
    for (n1, c1, e1), (n2, c2, e2) in zip(seen["long"], seen["short"]):
        assert n1 == n2 and np.array_equal(c1, c2) and np.array_equal(e1, e2)


def test_calibrate_hands_the_mode_to_every_replicate(monkeypatch):
    seen = []
    feed = iter(FAKE)

    def fake(seed, **kwargs):
        seen.append((seed, kwargs["direction"], kwargs["entry"]))
        return next(feed)

    monkeypatch.setattr(cal, "replicate", fake)
    cal.calibrate(4, seed=0, direction="short", **QUIET)
    assert seen == [(0, "short", "next_open"), (1, "short", "next_open"),
                    (2, "short", "next_open"), (3, "short", "next_open")]


def test_render_short_states_direction_rule_wilson_and_seeds(monkeypatch):
    _fake_replicates(monkeypatch, FAKE)
    result = cal.calibrate(4, seed=0, direction="short", **QUIET)
    params = {"replicates": 4, "seed": 0, "tickers": 2, "resamples": 200,
              "direction": "short", "entry": "next_open"}
    text = cal.render(result, params, "2026-10-21")
    assert text.startswith("# v182 short race A/A calibration (next-open entry) -> **over** "
                           "the 5% false-pass limit")
    for needle in ("1 of 4 = 25.0%", "≤ 5% (gating)",
                   "| Wilson 95% interval of the false-pass rate | 4.6% .. 69.9% | reported, not gated |",
                   "--direction short --entry next_open", "seed 0", "cap 20 bars",
                   "borrow 0.5% a year", "10 of 200", "df = 3", "| 3 |",
                   "no cached price file"):
        assert needle in text, needle


def test_the_long_render_ignores_the_new_params_and_has_no_wilson_row(monkeypatch):
    _fake_replicates(monkeypatch, FAKE)
    result = cal.calibrate(4, seed=100, **QUIET)
    base = {"replicates": 4, "seed": 100, "tickers": 2, "resamples": 200}
    plain = cal.render(result, base, "2026-10-15")
    assert cal.render(result, {**base, "direction": "long", "entry": "next_open"},
                      "2026-10-15") == plain
    assert "Wilson" not in plain


def test_a_short_run_writes_the_short_doc(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    _fake_replicates(monkeypatch, [FAKE[1], FAKE[3]])
    argv = ["--direction", "short", "--replicates", "2", "--seed", "0",
            "--date", "2026-10-21", "--out-dir", str(out_dir)]
    assert cal.main(argv) == 0
    assert (out_dir / "2026-10-21-short-race-calibration.md").exists()
    assert not (out_dir / "2026-10-21-trail-race-calibration.md").exists()


def test_long_level_is_refused_for_good():
    with pytest.raises(SystemExit) as exc:
        cal.main(["--entry", "level", "--replicates", "1", "--dry-run"])
    assert exc.value.code == 2


from swingbot.core.backtesting.screen import indicators  # noqa: E402
from tests.backtesting.screen.helpers import assert_prefix_stable  # noqa: E402


def _synthetic(bars=400, seed=1):
    return cal.synthetic_frame(np.random.default_rng(seed), bars=bars)


def test_level_mode_is_enabled_and_its_constants_are_pinned():
    assert cal.ENABLED_ENTRIES == ("next_open", "level")
    assert cal.LEVEL_OFFSET_ATR == 0.5 and cal.LEVEL_RATE_SCALE == 2.5


def test_level_events_are_random_bars_whose_order_fills():
    df = _synthetic()
    events, levels = cal.level_events(df, np.random.default_rng(3), 0.3)
    draw = cal.random_events(df.index, np.random.default_rng(3), 0.3)
    expected = (df["Close"].shift(1) - 0.5 * indicators.atr(df).shift(1)).to_numpy()
    assert np.array_equal(levels.to_numpy(), expected, equal_nan=True)
    assert events.tolist() == (draw & (df["Low"] < levels)).tolist()
    assert 0 < events.sum() < draw.sum()                              # non-vacuous


def test_level_events_consume_the_rng_like_random_events():
    df = _synthetic()
    a, b = np.random.default_rng(5), np.random.default_rng(5)
    cal.level_events(df, a, 0.02)
    cal.random_events(df.index, b, 0.02)
    assert a.random() == b.random()


def test_levels_read_no_later_bar():
    df = _synthetic(bars=120)
    assert_prefix_stable(lambda d: cal.level_events(d, np.random.default_rng(0), 0.0)[1],
                         df, [30, 60, 90, 119])


def test_the_short_level_idea_is_fixed_cap_20_short_level():
    lv = pd.Series(1.0, index=EV.index)
    idea = cal._idea(EV, direction="short", entry="level", levels=lv)
    assert (idea.name, idea.time_cap_bars, idea.race_shape, idea.direction, idea.entry) == (
        "aa_short_level_calibration", 20, "fixed", "short", "level")
    assert idea.levels(None) is lv


def test_a_long_level_replicate_is_refused():
    with pytest.raises(ValueError):
        cal.replicate(1, tickers=1, n_resamples=100, direction="long", entry="level")


def test_a_short_level_replicate_races_level_mode(monkeypatch):
    seen = []
    real = cal.screen_idea.race.run_book

    def spy(*args, **kwargs):
        seen.append((kwargs.get("shape"), kwargs.get("direction"),
                     kwargs.get("levels") is not None))
        return real(*args, **kwargs)

    monkeypatch.setattr(cal.screen_idea.race, "run_book", spy)
    v = cal.replicate(5, tickers=1, n_resamples=100, direction="short", entry="level")
    assert isinstance(v, verdict.Verdict)
    assert seen and set(seen) == {("fixed", "short", True)}


def test_a_level_replicate_sees_open_anchored_frames(monkeypatch):
    """The level A/A races open-anchored frames (Close = Open x exp(sigma x t)),
    the next-open A/A the default prior-close-anchored ones."""
    seen = {"next_open": [], "level": []}
    real = cal.screen_idea.screen_ticker

    def spy(idea, name, df, spans, **kwargs):
        seen[idea.entry].append((name, df["Close"].to_numpy().copy()))
        return real(idea, name, df, spans, **kwargs)

    monkeypatch.setattr(cal.screen_idea, "screen_ticker", spy)
    cal.replicate(7, tickers=2, n_resamples=100)
    cal.replicate(7, tickers=2, n_resamples=100, direction="short", entry="level")
    assert len(seen["next_open"]) == len(seen["level"]) == 2
    first = cal.synthetic_frame(np.random.default_rng(7), cal.BARS)
    anchored = cal.synthetic_frame(np.random.default_rng(7), cal.BARS, anchored=True)
    assert np.array_equal(seen["next_open"][0][1], first["Close"].to_numpy())
    assert np.array_equal(seen["level"][0][1], anchored["Close"].to_numpy())
    assert not np.array_equal(seen["level"][0][1], seen["next_open"][0][1])


def test_render_short_level_states_the_order_the_null_and_the_limit(monkeypatch):
    _fake_replicates(monkeypatch, FAKE)
    result = cal.calibrate(4, seed=0, direction="short", entry="level", **QUIET)
    params = {"replicates": 4, "seed": 0, "tickers": 2, "resamples": 200,
              "direction": "short", "entry": "level"}
    text = cal.render(result, params, "2026-10-21")
    assert text.startswith("# v182 short race A/A calibration (level entry) -> **over** "
                           "the 5% false-pass limit")
    for needle in ("§ Part B (calibration item 4)", "--direction short --entry level",
                   "sell-stop at Close[t-1] - 0.5 x ATR14[t-1]", "entry slippage 2.0 x base",
                   "only the stop counts on the fill bar", "copies each event's fill depth",
                   "probability 0.05", "borrow 0.5% a year", "10 of 200",
                   "cannot show that the depth-copy null is fair",
                   "| Wilson 95% interval of the false-pass rate | 4.6% .. 69.9% | reported, not gated |"):
        assert needle in text, needle


def test_a_short_level_run_writes_the_level_doc(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    _fake_replicates(monkeypatch, [FAKE[1], FAKE[3]])
    argv = ["--direction", "short", "--entry", "level", "--replicates", "2", "--seed", "0",
            "--date", "2026-10-21", "--out-dir", str(out_dir)]
    assert cal.main(argv) == 0
    assert (out_dir / "2026-10-21-short-level-race-calibration.md").exists()
    assert not (out_dir / "2026-10-21-short-race-calibration.md").exists()


# --- open-anchored generator for the level A/A (ad-hoc v182 fix) ---
import hashlib  # noqa: E402

DEFAULT_FRAME_SHA = "ad55a3274886536fe94b47a4dad08e01f0426eabfaa5fd07e791ee8c3095a274"


def _ohlc_sha(df):
    return hashlib.sha256(df[["Open", "High", "Low", "Close"]].to_numpy().tobytes()).hexdigest()


def test_the_default_frame_is_byte_identical_to_the_pre_fix_generator():
    df = cal.synthetic_frame(np.random.default_rng(11), 300)
    assert _ohlc_sha(df) == DEFAULT_FRAME_SHA
    assert df["Close"].iloc[0] == pytest.approx(99.72178016305347, rel=0, abs=0)
    assert _ohlc_sha(cal.synthetic_frame(np.random.default_rng(11), 300, anchored=False)) \
        == DEFAULT_FRAME_SHA


def test_the_anchored_frame_is_valid_ohlcv():
    df = cal.synthetic_frame(np.random.default_rng(3), anchored=True)
    assert len(df) == cal.BARS
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert (df["High"] >= df[["Open", "Close"]].max(axis=1)).all()
    assert (df["Low"] <= df[["Open", "Close"]].min(axis=1)).all()
    assert (df[["Open", "High", "Low", "Close"]] > 0).all().all()
    assert df.index[0] == pd.Timestamp(cal.START)


def test_the_anchored_close_is_anchored_to_its_own_open():
    """Close = Open x exp(sigma x t) and Open = prior Close x gap, drawn from the
    same rng calls in the same order as the default frame."""
    bars = 400
    rng = np.random.default_rng(5)
    sigma = np.asarray(cal.VOL_STATES)[cal._regimes(rng, bars)]
    unit_t = rng.standard_t(cal.T_DF, bars) / np.sqrt(cal.T_DF / (cal.T_DF - 2))
    gap = np.exp(0.3 * sigma * rng.standard_normal(bars))
    df = cal.synthetic_frame(np.random.default_rng(5), bars, anchored=True)
    close, open_ = df["Close"].to_numpy(), df["Open"].to_numpy()
    assert np.allclose(np.log(close / open_), sigma * unit_t)
    assert np.allclose(open_, np.r_[100.0, close[:-1]] * gap)


def test_a_next_open_replicate_never_asks_for_the_anchored_frame(monkeypatch):
    flags = []
    real = cal.synthetic_frame

    def spy(rng, bars=cal.BARS, start=cal.START, **kwargs):
        flags.append(kwargs.get("anchored", False))
        return real(rng, bars, start, **kwargs)

    monkeypatch.setattr(cal, "synthetic_frame", spy)
    cal.replicate(2, tickers=2, n_resamples=100)
    cal.replicate(2, tickers=2, n_resamples=100, direction="short")
    assert flags == [False] * 4
    flags.clear()
    cal.replicate(2, tickers=2, n_resamples=100, direction="short", entry="level")
    assert flags == [True] * 2


def test_the_level_doc_states_the_open_anchored_generator(monkeypatch):
    _fake_replicates(monkeypatch, FAKE)
    result = cal.calibrate(4, seed=0, direction="short", entry="level", **QUIET)
    params = {"replicates": 4, "seed": 0, "tickers": 2, "resamples": 200,
              "direction": "short", "entry": "level"}
    text = cal.render(result, params, "2026-10-21")
    assert "Close = Open x exp(sigma x t)" in text


def test_the_next_open_docs_keep_the_old_generator_wording(monkeypatch):
    for direction in ("long", "short"):
        _fake_replicates(monkeypatch, FAKE)
        result = cal.calibrate(4, seed=0, direction=direction, **QUIET)
        params = {"replicates": 4, "seed": 0, "tickers": 2, "resamples": 200,
                  "direction": direction, "entry": "next_open"}
        text = cal.render(result, params, "2026-10-21")
        assert "Close = Open x exp" not in text
        assert cal._generator_paragraph() in text
