import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np

from swingbot.core.gate.registry import CHECKS
from swingbot.core.gate.setup_quality import check_signal_confirmed, check_confluence
from tests.conftest import make_ohlcv
from tests.fixtures.gate import uptrend_daily
from tests.fixtures.gate.plans import make_plan

ET = ZoneInfo("America/New_York")


def test_closed_bar_passes():
    plan = make_plan(created_at="2026-07-13")            # yesterday's bar
    now = dt.datetime(2026, 7, 14, 15, 0, tzinfo=ET)     # mid-session today
    assert check_signal_confirmed(uptrend_daily(), plan, None, now=now).status == "pass"


def test_same_day_forming_bar_scores_against_but_does_not_hard_block():
    # V8/2026-08-06: every candidate the live scanner builds during RTH has
    # created_at == today (created_at is the last bar's date, and the live
    # frame carries today's forming bar), so hard-blocking here was a
    # market-hours blackout, not a screen. It stays a 10-point penalty.
    plan = make_plan(created_at="2026-07-14")
    now = dt.datetime(2026, 7, 14, 15, 0, tzinfo=ET)     # Tuesday, session open
    result = check_signal_confirmed(uptrend_daily(), plan, None, now=now)
    assert result.status == "fail"
    assert result.hard_block is False
    # after the close the same plan is fine
    evening = dt.datetime(2026, 7, 14, 17, 30, tzinfo=ET)
    assert check_signal_confirmed(uptrend_daily(), plan, None, now=evening).status == "pass"


def test_forming_bar_does_not_force_tier_c():
    """The override has to survive run_checklist's hard_blocks assembly --
    asserting it on the CheckResult alone would pass even if the
    orchestrator ignored the field."""
    from swingbot.core.gate import run_checklist

    plan = make_plan(created_at="2026-07-14")
    now = dt.datetime(2026, 7, 14, 15, 0, tzinfo=ET)
    result = run_checklist("AAA", "Fibonacci", plan, uptrend_daily(), now=now)
    failed = {c.check_id for c in result.checks if c.status == "fail"}
    assert "signal_confirmed" in failed          # still counted against the score
    assert "signal_confirmed" not in result.hard_blocks


def test_breakout_close_back_inside_fails_hard():
    # market-entry breakout plan whose signal bar poked above the level
    # intrabar (high 100.5) but closed back inside (99.5). This branch keeps
    # the hard block: it is a statement about a CLOSED bar, not about the
    # clock, so no amount of waiting changes it.
    df = make_ohlcv(np.concatenate([np.full(59, 97.0), [99.5]]), spread_pct=2.0)
    plan = make_plan(strategy="Break & Retest", entry_type="market",
                     trigger_price=100.0, created_at="2026-07-13")
    now = dt.datetime(2026, 7, 14, 17, 30, tzinfo=ET)
    result = check_signal_confirmed(df, plan, None, now=now)
    assert result.status == "fail" and "inside" in result.detail
    assert result.hard_block is None            # registry policy applies

    checklist = run_checklist_for(df, plan, now)
    assert "signal_confirmed" in checklist.hard_blocks


def run_checklist_for(df, plan, now):
    from swingbot.core.gate import run_checklist
    return run_checklist("AAA", plan.strategy, plan, df, now=now)


def test_registered_as_hard_block():
    assert CHECKS["signal_confirmed"].hard_block is True


def test_confluence_bands(monkeypatch):
    import swingbot.core.gate.setup_quality as sq
    df, plan = uptrend_daily(), make_plan()
    # deterministic factor control: patch the factor probe directly
    def factors(n):
        return {"at_swing_level": n >= 1, "near_round": n >= 2,
                "sma_support": n >= 3, "volume": n >= 4,
                "momentum": n >= 5, "with_htf": n >= 6}
    monkeypatch.setattr(sq, "_confluence_factors", lambda d, p, m, **c: factors(4))
    assert check_confluence(df, plan, None).status == "pass"      # >= 3
    monkeypatch.setattr(sq, "_confluence_factors", lambda d, p, m, **c: factors(2))
    assert check_confluence(df, plan, None).status == "warn"      # exactly 2
    monkeypatch.setattr(sq, "_confluence_factors", lambda d, p, m, **c: factors(0))
    assert check_confluence(df, plan, None).status == "fail"      # < 2
    monkeypatch.setattr(sq, "_confluence_factors", lambda d, p, m, **c: factors(4))
    fired = check_confluence(df, plan, None).evidence["factors"]
    assert fired == ["at_swing_level", "near_round", "sma_support", "volume"]


def test_confluence_factors_run_on_real_frame():
    # smoke: the real factor probe runs end-to-end without raising
    result = check_confluence(uptrend_daily(), make_plan(), None)
    assert result.status in ("pass", "warn", "fail")


def _vol_df(last_ratio):
    vols = np.full(60, 1_000_000.0)
    vols[-1] = 1_000_000.0 * last_ratio
    return make_ohlcv(np.linspace(95, 100, 60), volumes=vols)


def test_volume_bands_for_breakout_family():
    from swingbot.core.gate.setup_quality import check_volume
    breakout = make_plan(strategy="Break & Retest")
    assert check_volume(_vol_df(1.5), breakout, None).status == "pass"   # >= 1.3x
    assert check_volume(_vol_df(1.0), breakout, None).status == "warn"   # 0.8-1.3x
    assert check_volume(_vol_df(0.5), breakout, None).status == "fail"   # < 0.8x: the #1 trap


def test_dead_volume_is_warn_only_for_meanrev():
    from swingbot.core.gate.setup_quality import check_volume
    meanrev = make_plan(strategy="RSI Divergence")
    assert check_volume(_vol_df(0.5), meanrev, None).status == "warn"


def test_no_volume_history_unknown():
    from swingbot.core.gate.setup_quality import check_volume
    df = make_ohlcv(np.linspace(95, 100, 10))
    assert check_volume(df, make_plan(), None).status == "unknown"


def _choppy_downtrend(n=260, start_price=100.0):
    """Local downtrend helper with oscillations to prevent RSI slope convergence.

    Used only by test_momentum_three_outcomes to generate sufficient momentum
    indicator divergence for pass/warn/fail assertions. Intentionally separate
    from the shared downtrend_daily() fixture to avoid changing its smooth
    geometric-decay character that other tests depend on.
    """
    base_trend = np.linspace(start_price, start_price * 0.35, n)
    oscillations = np.sin(np.arange(n) * 0.5) * (start_price * 0.03)
    closes = base_trend + oscillations
    return make_ohlcv(closes, spread_pct=2.0)


def test_momentum_three_outcomes():
    from swingbot.core.gate.setup_quality import check_momentum
    import pandas as pd
    bull = make_plan(direction="bullish")
    # steady uptrend: RSI slope up, MACD hist > 0 -> pass
    assert check_momentum(uptrend_daily(), bull, None).status == "pass"
    # choppy downtrend against a bullish plan: both momentum indicators against -> fail
    assert check_momentum(_choppy_downtrend(), bull, None).status == "fail"
    # choppy downtrend with a fresh 3-bar pop: RSI slope turns up while the MACD
    # histogram is still negative -> exactly one against -> warn
    df = _choppy_downtrend()
    pop = df["Close"].iloc[-1] * np.array([1.02, 1.04, 1.06])
    extra = make_ohlcv(pop, start=str((df.index[-1]
                                       + pd.tseries.offsets.BDay(1)).date()))
    mixed = pd.concat([df, extra])
    assert check_momentum(mixed, bull, None).status == "warn"


from swingbot.core.gate.setup_quality import check_divergence_against


def _hh_price_lh_rsi():
    """Three higher price highs on successively weaker legs -> RSI lower
    highs. Trailing pullback makes the last peak a detectable pivot."""
    closes = list(np.linspace(95, 100, 60))
    closes += list(np.linspace(100, 110, 5))          # sharp leg, RSI hot
    closes += list(np.linspace(110, 104, 4))[1:]
    closes += list(np.linspace(104, 112, 12))         # slower leg, RSI cooler
    closes += list(np.linspace(112, 106, 4))[1:]
    closes += list(np.linspace(106, 113, 18))         # crawl, RSI cooler still
    closes += list(np.linspace(113, 109, 4))[1:]
    return make_ohlcv(np.asarray(closes), spread_pct=0.5)


def test_divergence_against_move():
    df = _hh_price_lh_rsi()
    momentum_plan = make_plan(strategy="MACD", direction="bullish")
    result = check_divergence_against(df, momentum_plan, None)
    assert result.status == "fail"        # 2-swing confirmed + non-divergence strategy
    assert result.evidence["divergent_pairs"] >= 2
    div_plan = make_plan(strategy="RSI Divergence", direction="bullish")
    assert check_divergence_against(df, div_plan, None).status == "warn"
    assert check_divergence_against(uptrend_daily(), momentum_plan, None).status == "pass"
