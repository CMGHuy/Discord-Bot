import dataclasses

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting import armed_replay as ar
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.market import levels, reaction as rx
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv

L, T1 = 98.5, 106.0
CELL = ar.Cell("M1", 5, 0.25, 0.10)


def _params(**kw):
    base = dict(min_reward_pct=3.0, min_stop_distance_pct=2.0, max_stop_loss_pct=7.0,
                min_target_confluence_count=2, min_risk_reward_ratio=1.5,
                max_risk_reward_ratio=2.5)
    base.update(kw)
    return dataclasses.replace(ScanParams.from_config(), **base)


def _scenario(direction="bullish", entry=100.0, stop=L, target=T1):
    return levels.Scenario(
        direction=direction, entry=entry, market_price=entry, stop_loss=stop,
        stop_sources=["Rolling S/R"], stop_distance_pct=abs(entry - stop) / entry * 100,
        tight_stop=False, atr_floor_pct=0.0, take_profit=target,
        target_distance_pct=abs(target - entry) / entry * 100,
        target_sources=["Fibonacci"], target2_price=None, target2_distance_pct=None,
        target2_sources=None)


def _cand(index=25, direction="bullish", level=L, target=T1):
    return ar.ArmCandidate(index, direction, level, target,
                           _scenario(direction, stop=level, target=target))


def _frame(overrides, n=30):
    """Flat 100 closes (high 101 / low 99, well clear of L=98.5 at k=0.25),
    with (open, high, low, close) overrides by bar index."""
    rows = [(100.0, 101.0, 99.0, 100.0)] * n
    for idx, row in overrides.items():
        rows[idx] = row
    return make_ohlcv(rows)


def _walk(df, cand=None, cell=CELL):
    return ar.walk_arm(rx.Bars.from_frame(df), np.full(len(df), 1.0), cand or _cand(), cell)


def test_cell_id_format():
    assert ar.Cell("M2", 10, 0.5, 0.25).cell_id == "M2-N10-k0.50-b0.25"


def test_walk_confirms_a_rejection_and_records_the_first_test():
    out = _walk(_frame({27: (99.0, 99.6, 97.6, 99.4)}))
    assert out == ar.ArmOutcome("confirmed", 27, rx.R1, 27)


def test_walk_expires_when_nothing_tests_the_level():
    # arm at 25 with N=5 expires at bar 30, which must exist: 31 bars
    assert _walk(_frame({}, n=31)) == ar.ArmOutcome("expired", 30)


def test_walk_cancels_when_the_target_trades_first():
    out = _walk(_frame({26: (100.0, 106.5, 99.5, 105.0), 27: (99.0, 99.6, 97.6, 99.4)}))
    assert out == ar.ArmOutcome("cancelled_target", 26)


def test_target_reached_on_the_arm_bar_itself_is_ignored():
    out = _walk(_frame({25: (100.0, 106.5, 99.5, 100.0), 27: (99.0, 99.6, 97.6, 99.4)}))
    assert out.status == "confirmed" and out.resolved_index == 27


def test_walk_cancels_a_close_through_that_is_not_reclaimed():
    out = _walk(_frame({26: (98.6, 98.7, 97.9, 98.0),
                        27: (98.0, 98.1, 97.4, 97.5),
                        28: (97.5, 97.6, 96.9, 97.0)}))
    assert out == ar.ArmOutcome("cancelled_closed_through", 28)


def test_walk_is_unresolved_when_the_window_runs_off_the_frame():
    assert _walk(_frame({}, n=28)) == ar.ArmOutcome("unresolved", None)


def test_walk_bearish_mirror_confirms():
    cand = _cand(direction="bearish", level=101.5, target=94.0)
    out = _walk(_frame({27: (101.0, 102.4, 100.4, 100.6)}), cand=cand)
    assert out == ar.ArmOutcome("confirmed", 27, rx.R1, 27)


def test_arm_candidates_widen_past_the_min_stop_gate(monkeypatch):
    """Spec §3.1's widening: a 1.5% stop is refused by today's replay and
    arms here."""
    supports, resistances = [levels.Level(L, ["Rolling S/R"])], [levels.Level(T1, ["Fibonacci"])]
    monkeypatch.setattr(ar, "levels_asof", lambda *a, **k: (supports, resistances))
    monkeypatch.setattr(bs, "levels_asof", lambda *a, **k: (supports, resistances))
    monkeypatch.setattr(levels, "count_confirming_strategies", lambda *a, **k: (3, ["x", "y", "z"]))
    df = make_ohlcv([100.0] * 60)
    params = _params()
    baseline = bs.replay_scenarios("AAPL", df, "4w", params=params)
    assert [p for _, p in baseline if p.direction == "bullish"] == []
    cands = ar.arm_candidates("AAPL", df, "4w", params=params)
    bullish = [c for bar in cands.values() for c in bar if c.direction == "bullish"]
    assert bullish and all(c.level == L and c.target == T1 for c in bullish)
    assert min(cands) == 45          # MIN_BARS["4w"]


from swingbot.core.planning.plan_engine import PlanStatus


def _build(df, outcome, cell=CELL, *, resistances=(T1,), confluence=3, params=None):
    res = [levels.Level(p, ["Fibonacci"]) for p in resistances]
    sup = [levels.Level(90.0, ["Rolling S/R"])]
    return ar.build_armed_plan(
        "AAPL", df, "4w", _cand(), outcome, cell,
        bars=rx.Bars.from_frame(df), atr_values=np.full(len(df), 1.0),
        params=params or _params(),
        level_map_at=lambda j: (sup, res),
        confluence_at=lambda j, entry, target: confluence)


REJECTION = (99.0, 99.6, 97.6, 99.4)


def test_m1_issues_a_stop_entry_above_the_reaction_high():
    df = _frame({26: REJECTION})
    plan, reason = _build(df, ar.ArmOutcome("confirmed", 26, rx.R1, 26))
    assert reason == "issued"
    assert plan.entry_type == "stop_entry" and plan.entry_price is None
    assert plan.trigger_price == pytest.approx(99.6)
    assert plan.expiry_bars == ar.STOP_ENTRY_EXPIRY_BARS
    assert plan.stop_loss == pytest.approx(97.5)              # min(98.5, 97.6) - 0.10 * 1.0
    assert plan.tp1 == pytest.approx(99.6 + 2.1 * 2.5)        # 106 is past the 2.5R cap
    assert plan.status == PlanStatus.PENDING
    assert plan.created_at == df.index[26].date().isoformat()


def test_the_widened_scenario_issues_once_its_stop_is_re_anchored():
    """Today's gates refuse this scenario (1.5% stop); the armed path
    issues it with a stop >= 2% from the entry."""
    assert [s for s in levels.build_scenarios(
        100.0, [levels.Level(L, ["Rolling S/R"])], [levels.Level(T1, ["Fibonacci"])], 3.0,
        min_stop_distance_pct=2.0, max_stop_distance_pct=7.0, min_risk_reward=1.5)
        if s.direction == "bullish"] == []
    plan, reason = _build(_frame({26: REJECTION}), ar.ArmOutcome("confirmed", 26, rx.R1, 26))
    assert reason == "issued"
    assert abs(plan.trigger_price - plan.stop_loss) / plan.trigger_price * 100 >= 2.0


def test_m2_goes_straight_to_market_on_a_follow_through():
    df = _frame({25: (99.2, 99.5, 97.9, 99.2), 26: (99.3, 100.2, 98.6, 100.0)})
    plan, reason = _build(df, ar.ArmOutcome("confirmed", 26, rx.R2, 25),
                          cell=ar.Cell("M2", 5, 0.25, 0.25))
    assert reason == "issued"
    assert plan.entry_type == "market"
    assert plan.entry_price == pytest.approx(100.0) == plan.trigger_price
    assert plan.stop_loss == pytest.approx(97.65)             # min(98.5, 97.9) - 0.25
    assert plan.status == PlanStatus.ACTIVE


def test_m2_keeps_a_rejection_as_a_stop_entry():
    plan, _ = _build(_frame({26: REJECTION}), ar.ArmOutcome("confirmed", 26, rx.R1, 26),
                     cell=ar.Cell("M2", 5, 0.25, 0.10))
    assert plan.entry_type == "stop_entry"


def test_regates_refuse_rather_than_bend():
    shallow = _frame({26: (99.0, 99.6, 98.4, 99.4)})
    assert _build(shallow, ar.ArmOutcome("confirmed", 26, rx.R1, 26)) == (None, "regate_stop_distance")
    df = _frame({26: REJECTION})
    ok = ar.ArmOutcome("confirmed", 26, rx.R1, 26)
    assert _build(df, ok, resistances=()) == (None, "regate_no_target")
    assert _build(df, ok, params=_params(min_reward_pct=6.0)) == (None, "regate_reward")
    assert _build(df, ok, confluence=1) == (None, "regate_confluence")


def test_nan_atr_refuses():
    df = _frame({26: REJECTION})
    plan, reason = ar.build_armed_plan(
        "AAPL", df, "4w", _cand(), ar.ArmOutcome("confirmed", 26, rx.R1, 26), CELL,
        bars=rx.Bars.from_frame(df), atr_values=np.full(len(df), np.nan), params=_params(),
        level_map_at=lambda j: ([], []), confluence_at=lambda *a: 3)
    assert (plan, reason) == (None, "regate_invalid_atr")


def _replay(df, candidates, cell=CELL):
    res = [levels.Level(T1, ["Fibonacci"])]
    sup = [levels.Level(90.0, ["Rolling S/R"])]
    out = ar.replay_armed("AAPL", df, "4w", [cell], params=_params(), candidates=candidates,
                          level_map_at=lambda j: (sup, res),
                          confluence_at=lambda j, entry, target: 3)
    return out[cell.cell_id]


def test_one_live_arm_per_direction_and_cooldown_after_issuance(monkeypatch):
    # real ATR on this flat frame is ~2, which would make every 99.0 low a
    # test at k=0.25; pin it at 1.0 so only the rejection bar tests the level
    monkeypatch.setattr(ar, "atr", lambda df, period=14: pd.Series(1.0, index=df.index))
    df = _frame({27: REJECTION}, n=45)
    cands = {i: [_cand(index=i)] for i in (25, 26, 27, 28, 31, 32, 33)}
    result = _replay(df, cands)
    # 25 arms and confirms at 27; 26 and 27 are skipped (busy through 27);
    # 28 and 31 fall inside the 5-bar cooldown from 27; 32 arms and expires at 37;
    # 33 is skipped (busy through 37).
    assert [j for j, _, _ in result.issued] == [27]
    assert result.counts["armed"] == 2
    assert result.counts["issued"] == 1
    assert result.counts["expired"] == 1
    assert len(result.confirmed) == 1


def test_confluence_at_is_memoised(monkeypatch):
    calls = []
    monkeypatch.setattr(levels, "count_confirming_strategies",
                        lambda *a, **k: (calls.append(a) or 2, []))
    f = ar.make_confluence_at(make_ohlcv([100.0] * 30), "4w")
    assert f(20, 100.0, 105.0) == 2 and f(20, 100.0, 105.0) == 2
    assert len(calls) == 1


def _structured_df():
    """Trend up, then a 60-bar consolidation between ~95 and ~105 -- the
    fixture family tests/backtesting/test_backtest_scenarios.py uses, copied
    so the two files stay independent."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


@pytest.mark.slow
def test_replay_armed_never_reads_past_the_confirmation_bar():
    """NO-LOOKAHEAD: every plan issued at j <= t is identical on the full
    frame and on the frame truncated at t."""
    df = _structured_df()
    params = _params(min_target_confluence_count=1, min_stop_distance_pct=0.5,
                     max_stop_loss_pct=15.0, min_reward_pct=1.0)
    cells = [ar.Cell("M1", 10, 0.5, 0.10), ar.Cell("M2", 10, 0.5, 0.10)]
    t = len(df) - 15

    def signature(result):
        return sorted((j, kind, p.direction, p.entry_type, round(p.trigger_price, 6),
                       round(p.stop_loss, 6), round(p.tp1, 6))
                      for j, p, kind in result.issued if j <= t)

    full = ar.replay_armed("AAPL", df, "4w", cells, params=params)
    trunc = ar.replay_armed("AAPL", df.iloc[:t + 1], "4w", cells, params=params)
    assert any(r.counts["armed"] for r in full.values()), "fixture must arm at least once"
    for cell in cells:
        assert signature(full[cell.cell_id]) == signature(trunc[cell.cell_id])
