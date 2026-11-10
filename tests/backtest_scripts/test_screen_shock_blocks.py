"""v211 runner wiring of the shock read-outs (spec § Printed alongside each
verdict): TickerScreen.shock for level ideas, the pooled "shock" summary
block, nothing new for any other idea. Printed only, never gating."""
import functools
import sys
import types
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402

from swingbot.core.backtesting.screen import null, shock_readouts, verdict  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS  # noqa: E402
from swingbot.core.backtesting.screen.ideas import _shock_breakdown as sb  # noqa: E402
from tests.backtest_scripts.test_screen_level_context import (  # noqa: E402
    LEVEL, _fake_level_idea, _level_argv, _level_cache)
from tests.backtesting.screen.helpers import random_walk  # noqa: E402

ALWAYS = [("2000-01-01", "9999-12-31")]


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    """500 week resamples instead of 10,000: same code path, test-speed."""
    monkeypatch.setattr(screen_idea.verdict, "decide",
                        functools.partial(verdict.decide, n_resamples=500))


def _fresh_low(df):
    """The fake idea's unconditional control: a close under the prior 20-day low."""
    return df["Close"] < df["Low"].shift(1).rolling(20).min()


@pytest.fixture
def level_idea(monkeypatch):
    idea = _fake_level_idea(control=_fresh_low)
    monkeypatch.setitem(screen_idea.IDEAS, idea.name, idea)
    return idea


def _level_inputs(tmp_path):
    cache = _level_cache(tmp_path)
    frames = screen_idea.load_context(cache, LEVEL, kind="level").frames
    return cache, frames, screen_idea.load_frame(cache / "AAA.csv")


def _capture_publish(monkeypatch) -> dict:
    seen = {}

    def publish(args, idea, universe, summary, rows, data=None):
        seen["summary"] = summary
        return 0

    monkeypatch.setattr(screen_idea, "publish", publish)
    return seen


# --- per ticker ----------------------------------------------------------------

def test_an_idea_without_level_context_carries_no_shock_report():
    df = random_walk(2700, seed=7)
    for name in ("high52w", "range_breakdown_close"):
        assert screen_idea.screen_ticker(IDEAS[name], "AAA", df, ALWAYS).shock is None


def test_a_level_screen_carries_tags_null2_and_stress3(tmp_path, level_idea):
    _cache, frames, df = _level_inputs(tmp_path)
    s = screen_idea.screen_ticker(level_idea, "AAA", df, ALWAYS, context=frames)
    assert set(s.shock) == {"null2", "null2_dropped", "stress3", "tags"}
    assert s.events and len(s.shock["tags"]) == len(s.events)
    for row, tag in zip(s.events, s.shock["tags"]):
        assert tag["signal_date"] < row["entry_date"]
        assert tag["episode_day"] in shock_readouts.EPISODE_DAYS   # events fire on SHOCK days
    stress = s.shock["stress3"]
    assert [r["entry_date"] for r in stress] == [r["entry_date"] for r in s.events]
    assert all(st["r_event"] <= row["r_event"] for st, row in zip(stress, s.events))
    assert any(st["r_event"] < row["r_event"] for st, row in zip(stress, s.events))
    own = {r["entry_date"]: r["r_event"] for r in s.events}
    assert s.shock["null2"]
    assert all(r["r_event"] == own[r["entry_date"]] for r in s.shock["null2"])
    assert len(s.shock["null2"]) + s.shock["null2_dropped"] == len(s.events)


def test_the_shock_null_pool_is_this_tickers_eligible_shock_days(tmp_path, level_idea,
                                                                monkeypatch):
    _cache, frames, df = _level_inputs(tmp_path)
    seen, real = {}, shock_readouts.shock_null

    def spy_null(df_, event_pos, pool, k, seed, **kw):
        seen.update(pool=pool, k=k, seed=seed, kw=kw)
        return real(df_, event_pos, pool, k, seed, **kw)

    monkeypatch.setattr(screen_idea.shock_readouts, "shock_null", spy_null)
    screen_idea.screen_ticker(level_idea, "AAA", df, ALWAYS, context=frames)
    shock = sb.ticker_state(df, frames)["shock"].to_numpy(dtype=bool)
    ctx = screen_idea.ticker_context(level_idea, df, ALWAYS, frames)
    assert seen["pool"].any()
    assert not (seen["pool"] & ~shock).any()
    assert not (seen["pool"] & ~screen_idea._null_pool(level_idea, ctx)).any()
    assert seen["k"] == null.K
    assert seen["seed"] == null.null_seed("fake_level#shock-null", "AAA")
    assert seen["seed"] != null.null_seed("fake_level", "AAA")
    assert (seen["kw"]["cap"], seen["kw"]["shape"], seen["kw"]["direction"]) == (10, "fixed", "short")


def test_the_standard_book_is_the_same_with_and_without_the_shock_report(tmp_path, level_idea,
                                                                        monkeypatch):
    _cache, frames, df = _level_inputs(tmp_path)
    with_report = screen_idea.screen_ticker(level_idea, "AAA", df, ALWAYS, context=frames)
    monkeypatch.setattr(screen_idea, "_shock_report", lambda *a, **k: None)
    without = screen_idea.screen_ticker(level_idea, "AAA", df, ALWAYS, context=frames)
    assert with_report.events == without.events
    assert with_report.counters == without.counters
    assert with_report.control == without.control


def test_the_shock_null_pool_never_holds_an_event_bar(tmp_path, level_idea, monkeypatch):
    """A pool that would contain an event bar must not yield it (V211-10 advisory)."""
    _cache, frames, df = _level_inputs(tmp_path)
    seen = {}
    real = shock_readouts.shock_null

    def spy_null(df_, event_pos, pool, k, seed, **kw):
        seen["pool"] = pool.copy()
        return real(df_, event_pos, pool, k, seed, **kw)

    monkeypatch.setattr(screen_idea.shock_readouts, "shock_null", spy_null)
    real_pool = screen_idea._null_pool
    monkeypatch.setattr(screen_idea, "_null_pool",
                        lambda idea, ctx, exclude=None: real_pool(idea, ctx, exclude) | ctx["raw"])
    ctx = screen_idea.ticker_context(level_idea, df, ALWAYS, frames)
    kept, _, _ = screen_idea._books(level_idea, "AAA", df, ctx, {"slippage_bps": None, "commission": None})
    assert ctx["raw"][kept.event_pos].all()
    screen_idea._shock_report(level_idea, "AAA", df, ctx,
                              {"slippage_bps": None, "commission": None}, kept)
    assert not (seen["pool"] & ctx["raw"]).any()
    assert not seen["pool"][kept.event_pos].any()


# --- pooled --------------------------------------------------------------------

def test_with_shock_blocks_leaves_every_other_idea_untouched():
    summary = {"counters": Counter()}
    for name in ("high52w", "range_breakdown_close", "dollar_drop"):
        assert screen_idea.with_shock_blocks(summary, [], IDEAS[name]) is summary


def _row(day, r_event, r_null):
    return {"entry_date": day, "r_event": r_event, "r_null": r_null}


def _tag(bucket, day):
    return {"signal_date": "x", "gap_pct": 0.0, "gap_bucket": bucket, "episode_day": day}


def test_with_shock_blocks_pools_the_tickers_and_splits_by_bucket(level_idea):
    a = types.SimpleNamespace(
        events=[_row("2011-03-02", 1.0, 0.2), _row("2011-03-10", -0.5, 0.1)],
        shock={"tags": [_tag("<= -1%", "peak"), _tag("<= -1%", "later")],
               "null2": [_row("2011-03-02", 1.0, -0.2)], "null2_dropped": 1,
               "stress3": [_row("2011-03-02", 0.9, 0.1), _row("2011-03-10", -0.6, 0.0)]})
    b = types.SimpleNamespace(
        events=[_row("2012-05-07", 2.0, 0.0)],
        shock={"tags": [_tag(None, "later")], "null2": [], "null2_dropped": 1,
               "stress3": [_row("2012-05-07", 1.9, 0.0)]})
    summary = {"counters": Counter(skipped_overlap=4)}
    out = screen_idea.with_shock_blocks(summary, [a, b], level_idea)
    assert out is not summary and "shock" not in summary
    block = out["shock"]
    assert block["null2"].n == 1 and block["null2"].delta_exp_r == pytest.approx(1.2)
    assert block["null2_dropped"] == 2
    assert block["stress3"].n == 3
    assert block["skipped_overlap"] == 4
    gap = block["gap"]
    assert gap["<= -1%"] == {"n": 2, "exp_r_event": pytest.approx(0.25),
                             "delta_exp_r": pytest.approx(0.1)}
    assert gap["-1% .. +1%"] == {"n": 0, "exp_r_event": None, "delta_exp_r": None}
    assert gap[">= +1%"]["n"] == 0 and gap["missing"] == 1
    day = block["episode_day"]
    assert (day["peak"]["n"], day["later"]["n"], day["missing"]) == (1, 2, 0)
    assert day["later"]["delta_exp_r"] == pytest.approx(0.7)


def test_with_shock_blocks_of_no_screen_has_empty_books(level_idea):
    block = screen_idea.with_shock_blocks({"counters": Counter()}, [], level_idea)["shock"]
    assert block["null2"].n == 0 and block["stress3"].n == 0
    assert block["skipped_overlap"] == 0 and block["gap"]["missing"] == 0


# --- through main --------------------------------------------------------------

def test_a_level_run_hands_publish_the_shock_block(tmp_path, monkeypatch, level_idea):
    cache = _level_cache(tmp_path)
    seen = _capture_publish(monkeypatch)
    assert screen_idea.main(_level_argv(tmp_path, cache, "--dry-run")) == 0
    assert set(seen["summary"]["shock"]) == {"null2", "null2_dropped", "stress3", "gap",
                                             "episode_day", "skipped_overlap"}
    assert "short" in seen["summary"]


def test_a_plain_run_has_no_shock_block(tmp_path, monkeypatch):
    cache = _level_cache(tmp_path)
    seen = _capture_publish(monkeypatch)
    argv = _level_argv(tmp_path, cache, "--dry-run")
    argv[1] = "turn_of_month"
    assert screen_idea.main(argv) == 0
    assert "shock" not in seen["summary"]
