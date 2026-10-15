"""v146 I3: the confluence replay's detailed hits, the TRAIN-only
neutral-expectancy switch, and the per-trade TRAIN row with a confidence
score computed exactly as the live scan computes it -- on the as-of window."""
import copy
import json

import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.backtesting import scenario_rows
from swingbot.core.market import levels
from swingbot.core.market.levels import Scenario
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.scanning import confidence
from swingbot.core.scanning.confidence import score_confidence
from swingbot.core.scanning.regime import get_market_regime
from tests.helpers import make_ohlcv

# The replay is the slow part (same tier as test_backtest_scenarios.py).
pytestmark = pytest.mark.slow

GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def _structured_df():
    """Trend up, then a 60-bar box -- the fixture family of
    tests/backtesting/test_backtest_scenarios.py, copied so the files stay
    independent."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


@pytest.fixture(autouse=True)
def _legacy_scorer(monkeypatch):
    # Production runs the legacy scorer (UNIFIED_CONFIDENCE defaults false).
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", False)


@pytest.fixture(scope="module")
def df():
    return _structured_df()


@pytest.fixture(scope="module")
def spy():
    # Starts a year before the stock frame, so every signal bar has 220+
    # SPY bars behind it and get_market_regime returns a trend.
    return make_ohlcv([300.0 + 0.1 * k for k in range(500)], start="2023-01-02")


@pytest.fixture(scope="module")
def hits(df):
    out = bs.replay_scenarios_detailed("AAPL", df, "4w", gates=GATES)
    assert out, "fixture must produce at least one hit"
    return out


def _fingerprint(i, plan):
    return (i, plan.direction, plan.trigger_price, plan.stop_loss, plan.tp1, plan.tp2)


# --- replay_scenarios_detailed ----------------------------------------------

def test_replay_scenarios_is_the_projection_of_the_detailed_hits(df, hits):
    legacy = bs.replay_scenarios("AAPL", df, "4w", gates=GATES)
    assert [_fingerprint(i, p) for i, p in legacy] == [_fingerprint(h.i, h.plan) for h in hits]


def test_a_hit_reads_like_the_legacy_pair_and_carries_its_scenario(df, hits):
    for hit in hits:
        assert (hit[0], hit[1]) == (hit.i, hit.plan)
        assert hit.scenario.direction == hit.plan.direction
        window = df.iloc[:hit.i + 1]
        price = float(window["Close"].iloc[-1])
        assert hit.target_confluence == levels.count_confirming_strategies(
            window, HORIZONS["4w"], price, hit.scenario.take_profit,
            tolerance_pct=bs.REPLAY_CONFLUENCE_TOLERANCE_PCT)
        assert hit.target_confluence[0] >= GATES["min_confluence"]


# --- neutral_expectancy -------------------------------------------------------

def _scenario():
    return Scenario(direction="bullish", entry=100.0, market_price=100.0, stop_loss=98.0,
                    stop_sources=["EMA", "VWAP"], stop_distance_pct=2.0, tight_stop=False,
                    atr_floor_pct=1.5, take_profit=110.0, target_distance_pct=10.0,
                    target_sources=["EMA", "VWAP"], target2_price=None,
                    target2_distance_pct=None, target2_sources=None)


def test_neutral_expectancy_never_runs_the_track_record_step(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("_expectancy_adjustment must not run when neutralised")
    monkeypatch.setattr(confidence, "_expectancy_adjustment", boom)
    result = score_confidence(_scenario(), target_confluence=(2, ["EMA", "VWAP"]),
                              neutral_expectancy=True)
    assert result.breakdown["Track record (expectancy)"] == confidence.NEUTRAL_EXPECTANCY_DETAIL


def test_the_default_keeps_the_live_expectancy_step(monkeypatch):
    monkeypatch.setattr(confidence, "_expectancy_adjustment", lambda rr, record: (1, "forced +1"))
    live = score_confidence(_scenario(), target_confluence=(2, ["EMA", "VWAP"]))
    neutral = score_confidence(_scenario(), target_confluence=(2, ["EMA", "VWAP"]),
                               neutral_expectancy=True)
    assert live.breakdown["Track record (expectancy)"] == "forced +1"
    # base Level 2, quality nudges -1..+1, so neither side clamps at 1 or 5
    assert live.level == neutral.level + 1


# --- signal_fields / scenario_trade_row --------------------------------------

def _late_hit(df, hits):
    return next(h for h in hits if h.i < len(df) - 5)


def test_the_score_is_the_live_scorer_on_the_as_of_window(df, hits, spy):
    hit = _late_hit(df, hits)
    window = df.iloc[:hit.i + 1]
    price = float(window["Close"].iloc[-1])
    stop_confluence = levels.count_confirming_strategies(
        window, HORIZONS["4w"], price, hit.scenario.stop_loss,
        tolerance_pct=bs.REPLAY_CONFLUENCE_TOLERANCE_PCT)
    trend = get_market_regime(spy[spy.index <= window.index[-1]]).trend
    expected = score_confidence(copy.deepcopy(hit.scenario), regime_trend=trend, df=window,
                                target_confluence=hit.target_confluence,
                                stop_confluence=stop_confluence, track_record=None,
                                neutral_expectancy=True)
    fields = scenario_rows.signal_fields("4w", df, hit, spy)
    assert scenario_rows.TRAIN_NEUTRAL_EXPECTANCY is True
    assert fields["confidence_score"] == expected.score
    assert fields["confidence_level"] == expected.level
    assert fields["confidence_points"] == expected.points
    assert fields["confidence_unevaluated"] == expected.unevaluated
    assert fields["confidence_points"], "the legacy scorer stamps points (V146-2)"


def test_signal_fields_ignore_every_bar_after_the_signal(df, hits, spy):
    hit = _late_hit(df, hits)
    signal_ts = df.index[hit.i]
    full = scenario_rows.signal_fields("4w", df, hit, spy)
    truncated = scenario_rows.signal_fields("4w", df.iloc[:hit.i + 1], hit, spy[spy.index <= signal_ts])
    assert truncated == full
    spiked, spy_spiked = df.copy(), spy.copy()
    prices = ["Open", "High", "Low", "Close"]
    spiked.loc[spiked.index > signal_ts, prices] *= 3.0
    spy_spiked.loc[spy_spiked.index > signal_ts, prices] *= 0.2
    assert scenario_rows.signal_fields("4w", spiked, hit, spy_spiked) == full


def test_no_spy_or_short_spy_scores_without_a_regime(df, hits, spy):
    hit = _late_hit(df, hits)
    window = df.iloc[:hit.i + 1]
    price = float(window["Close"].iloc[-1])
    stop_confluence = levels.count_confirming_strategies(
        window, HORIZONS["4w"], price, hit.scenario.stop_loss,
        tolerance_pct=bs.REPLAY_CONFLUENCE_TOLERANCE_PCT)
    expected = score_confidence(copy.deepcopy(hit.scenario), regime_trend=None, df=window,
                                target_confluence=hit.target_confluence,
                                stop_confluence=stop_confluence, track_record=None,
                                neutral_expectancy=True)
    for spy_df in (None, spy.iloc[:100]):
        fields = scenario_rows.signal_fields("4w", df, hit, spy_df)
        assert (fields["confidence_score"], fields["confidence_level"]) == (expected.score, expected.level)


def test_scoring_never_mutates_the_replayed_scenario(df, hits, spy):
    hit = _late_hit(df, hits)
    before = (list(hit.scenario.target_sources), list(hit.scenario.stop_sources))
    scenario_rows.signal_fields("4w", df, hit, spy)
    assert (list(hit.scenario.target_sources), list(hit.scenario.stop_sources)) == before


def test_the_row_carries_every_documented_key(df, hits, spy):
    hit = _late_hit(df, hits)
    result = bs.simulate_exit(df, hit.i, hit.plan, scale_out=True)
    row = scenario_rows.scenario_trade_row("AAPL", "4w", df, hit, result, spy)
    assert tuple(row) == scenario_rows.ROW_KEYS
    assert row["ticker"] == "AAPL" and row["horizon_key"] == "4w"
    assert row["signal_date"] == str(df.index[hit.i].date())
    assert row["direction"] == hit.plan.direction
    assert (row["entry"], row["stop_loss"], row["take_profit"]) == (
        hit.plan.trigger_price, hit.plan.stop_loss, hit.plan.tp1)
    risk = abs(hit.plan.trigger_price - hit.plan.stop_loss)
    assert row["risk_reward_ratio"] == round(abs(hit.plan.tp1 - hit.plan.trigger_price) / risk, 2)
    assert (row["outcome"], row["runner_outcome"], row["r_total"]) == (
        result.outcome, result.runner_outcome, result.r_total)
    assert row["legs"] == result.legs
    assert row["entry_context"] == (hit.plan.entry_context or {})
    assert row["confluence_count"] == hit.target_confluence[0]
    json.loads(json.dumps(row, default=str))      # JSON-able with the writer's fallback
