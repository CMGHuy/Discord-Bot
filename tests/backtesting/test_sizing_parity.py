"""Task 13: full-corpus sizing-parity harness (pytest side).

Compares `backtest._v1_plan_levels` (CURRENT -- it already delegates to
`plan_engine`, see swingbot/core/backtesting/backtest.py) against
`tests.fixtures.legacy_trade_plan_at.legacy_trade_plan_at`, a FROZEN copy of
`_trade_plan_at` (now `_v1_plan_levels`) as it stood pre-extraction (commit ac91654, before Task 14
rewired it to call plan_engine). That frozen copy is the only remaining
independent "old" implementation -- tests/test_plan_engine_sizing.py already
compares plan_engine against the *current* (post-delegation)
`backtest._v1_plan_levels`, which is plan_engine calling itself through one
layer of indirection and can no longer prove extraction correctness on its
own.

STOP ONLY as of plan v31 (docs/superpowers/plans/implemented/2026-08-16-v31-structural-targets.md,
Task 15): the frozen reference's target arithmetic is now permanently stale
-- plan_engine prices every target off a real structural level instead of a
fixed per-strategy reward:risk ratio, and the frozen module (deliberately;
see its own docstring) was never taught the new selector. Comparing tp1
would just assert a known, designed-in divergence forever. Stop derivation
is genuinely unchanged by v31 and remains a real, meaningful check. A bar
where the new selector finds no qualifying target (`_v1_plan_levels` returns
None) is skipped, not compared -- the frozen side has no such concept.

Runs on the frozen fixture cases in tests/fixtures/ohlcv_parity.py -- every
strategy x {"4w", "3m"} pair the scanner can emit, on committed OHLCV so CI
runs it too; `scripts/reports/parity_sizing.py` runs the same comparison over
every cached ticker, every strategy, every horizon, every TRAIN-window entry bar.
"""
import numpy as np
import pytest

from swingbot.core.backtesting import backtest
from swingbot.core.market.strategy_types import HORIZONS, MIN_BARS
from swingbot.core.risk_limits import capped_planned_loss_pct

from tests.fixtures.legacy_trade_plan_at import legacy_trade_plan_at
from tests.fixtures.ohlcv_parity import PARITY_CASES, load_ohlcv

TOLERANCE = 1e-6


@pytest.fixture(autouse=True)
def _lifecycle_off(monkeypatch):
    """Pin the level-lifecycle flag OFF for this module.

    This harness compares the CURRENT `_v1_plan_levels` against
    `legacy_trade_plan_at`, a frozen pre-extraction copy. The level lifecycle
    (P1) is a deliberate behaviour change made long after that freeze -- the
    frozen copy cannot have it and must never be taught it, or it stops being
    an independent witness to the extraction.

    So with LEVEL_LIFECYCLE_STOPS_ENABLED default-on (2026-08-08) the two sides
    diverge by design, on exactly the entry bars where a tested level moves the
    stop. Pinning the flag keeps this harness answering its own question --
    "did the Task-14 extraction change sizing?" -- rather than re-detecting a
    feature that is already measured in
    docs/superpowers/results/2026-08-08-level-lifecycle-*.md. (Its
    stops-only sibling, the "pull TP1 back inside a blocking level" flag,
    was measured inert and removed by v31 Task 14 -- there is only the one
    flag to pin now.)

    scripts/reports/parity_sizing.py (the full-corpus version of this comparison)
    forces the same flag off in main(), for the same reason.
    """
    monkeypatch.setattr("swingbot.config.LEVEL_LIFECYCLE_STOPS_ENABLED", False,
                        raising=False)


@pytest.mark.parametrize(("ticker", "strategy", "horizon_key"), PARITY_CASES)
def test_sizing_parity(ticker, strategy, horizon_key):
    df = load_ohlcv(ticker)
    min_bars = MIN_BARS[horizon_key]

    bullish, bearish = backtest._vectorized_entries(df, strategy, horizon_key)
    atr_series, swing_high_series, swing_low_series, volume_ratio_series, entry_levels = (
        backtest._plan_series(df, strategy, horizon_key)
    )

    entry_idx = np.where(bullish.values | bearish.values)[0]
    checked = 0
    none_count = 0
    for i in entry_idx:
        if i < min_bars:
            continue
        direction = "bullish" if bullish.values[i] else "bearish"

        entry, old_stop, old_tp = legacy_trade_plan_at(
            df, i, direction, strategy, horizon_key, atr_series,
            swing_high_series, swing_low_series, volume_ratio_series, entry_levels,
        )
        new_plan = backtest._v1_plan_levels(
            df, i, direction, strategy, horizon_key, atr_series,
            swing_high_series, swing_low_series, volume_ratio_series, entry_levels,
        )
        if new_plan is None:
            # v31: a real "no qualifying target" answer -- no level clears
            # MIN_RISK_REWARD_RATIO against this bar's risk. Not a parity
            # failure (the frozen legacy side has no such concept and always
            # returns a tuple); just not comparable at this bar.
            none_count += 1
            continue
        _, new_stop, new_tp = new_plan

        # 2026-09-21: another known, designed-in divergence, same treatment
        # as tp1 below -- HARD_MAX_PLANNED_LOSS_PCT (2%) now clamps every
        # sizing builder's stop distance, tighter than the frozen legacy
        # side's uncapped (or horizon-max_risk_pct-capped) formula on any
        # bar where that formula alone would have sat further than 2% from
        # entry. Re-deriving the same clamp against the legacy stop keeps
        # this a real extraction check (still catches drift on every OTHER
        # bar) instead of a permanent, meaningless failure on every bar the
        # new cap actually bites.
        is_bull = direction == "bullish"
        max_risk_amount = entry * (capped_planned_loss_pct(HORIZONS[horizon_key]["max_risk_pct"]) / 100)
        expected_stop = old_stop
        if abs(entry - old_stop) > max_risk_amount:
            expected_stop = entry - max_risk_amount if is_bull else entry + max_risk_amount

        assert expected_stop == pytest.approx(new_stop, abs=TOLERANCE), (
            f"{ticker}/{strategy}/{horizon_key} bar {i} ({direction}): "
            f"stop mismatch old={old_stop!r} expected(capped)={expected_stop!r} new={new_stop!r}"
        )
        # tp1 is NOT compared. It diverges from the frozen reference BY
        # DESIGN as of plan v31 (docs/superpowers/plans/implemented/2026-08-16-v31-structural-targets.md):
        # plan_engine now prices every target off a real structural level
        # (plan_engine.select_structural_target) instead of the frozen
        # module's fixed per-strategy reward:risk arithmetic. A tp1
        # mismatch here is expected, not a regression -- do not add this
        # assertion back.
        checked += 1

    assert checked, (
        f"no comparable entry bar for {ticker}/{strategy}/{horizon_key} "
        f"({none_count} bar(s) had no qualifying v31 target); "
        "swap in another ticker in tests/fixtures/ohlcv_parity.py")
