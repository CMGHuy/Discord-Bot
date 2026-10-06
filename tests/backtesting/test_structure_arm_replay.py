import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting import armed_replay as ar
from swingbot.core.backtesting import structure_arm as sa
from swingbot.core.market import levels, reaction as rx
from swingbot.core.planning.plan_engine import PlanStatus
from tests.backtesting.structure_arm_fixtures import (
    HOVER, L, MSB_FRAME, RELEASE, RETEST, T1, TEST, cand, frame, params, structured_df,
)

MSB5 = sa.StructCell(sa.MSB, 5, 0.25)


@pytest.fixture
def flat_atr(monkeypatch):
    """Pin ATR14 at 1.0 so the fixture geometry is exact."""
    monkeypatch.setattr(sa, "atr", lambda df, period=14: pd.Series(1.0, index=df.index))


def _replay(df, candidates, cell=MSB5, resistances=(T1,), confluence=3):
    res = [levels.Level(p, ["Fibonacci"]) for p in resistances]
    sup = [levels.Level(90.0, ["Rolling S/R"])]
    out = sa.replay_structure("AAPL", df, "4w", [cell], params=params(), candidates=candidates,
                              level_map_at=lambda j: (sup, res),
                              confluence_at=lambda j, entry, target: confluence)
    return out[cell.cell_id]


def _episode_frame(release=True):
    """Arm at 25 expires at 30; 31 re-tests L (no release yet); 33 closes
    100.2, releasing L; 38 re-tests L. HOVER bars never test, never release."""
    overrides = {i: HOVER for i in range(25, 50)}
    overrides.update({25: TEST, 31: RETEST, 33: RELEASE if release else HOVER, 38: RETEST})
    return frame(overrides, n=50)


def test_released_needs_a_close_beyond_k_plus_one_atr_in_the_trades_favour():
    df = _episode_frame()
    bars, atr_values = rx.Bars.from_frame(df), np.full(len(df), 1.0)
    assert not sa.released(bars, atr_values, L, "bullish", 0.25, 31, 33)   # [31, 33) misses 33
    assert sa.released(bars, atr_values, L, "bullish", 0.25, 31, 34)
    assert not sa.released(bars, atr_values, L, "bullish", 0.25, 34, 34)   # empty range
    bear = frame({i: HOVER for i in range(25, 50)} | {33: RELEASE}, n=50, bearish=True)
    bear_bars = rx.Bars.from_frame(bear)
    assert not sa.released(bear_bars, atr_values, 200.0 - L, "bearish", 0.25, 31, 33)
    assert sa.released(bear_bars, atr_values, 200.0 - L, "bearish", 0.25, 31, 34)


def test_touch_episode_blocks_an_immediate_retest_and_releases_after_a_departure(flat_atr):
    other = cand(31, level=98.8)
    cands = {25: [cand(25)], 31: [cand(31), other], 38: [cand(38)]}
    result = _replay(_episode_frame(), cands)
    # 31 (same level, no release yet) is blocked; the different level at 31
    # arms on its own; 38 re-arms L after bar 33's release close.
    assert result.arms == [(25, 30, "expired"), (31, 36, "expired"), (38, 43, "expired")]
    assert result.counts["armed"] == 3 and result.counts["expired"] == 3


def test_without_a_release_close_the_level_never_re_arms(flat_atr):
    cands = {25: [cand(25)], 31: [cand(31), cand(31, level=98.8)], 38: [cand(38)]}
    result = _replay(_episode_frame(release=False), cands)
    assert result.arms == [(25, 30, "expired"), (31, 36, "expired")]


def test_cooldown_bars_is_not_consulted(flat_atr):
    """v88 would skip an arm 2 bars after an issuance (COOLDOWN_BARS = 5).
    Here a different level arms at 30, two bars after the plan at 28."""
    result = _replay(frame(MSB_FRAME), {25: [cand(25)], 30: [cand(30, level=98.8)]})
    assert result.arms == [(25, 28, "issued"), (30, 35, "expired")]


def test_one_live_arm_per_direction_and_directions_are_independent(flat_atr):
    df = _episode_frame()
    busy = _replay(df, {25: [cand(25)], 27: [cand(27, level=98.8)]})
    assert busy.arms == [(25, 30, "expired")]
    both = _replay(df, {25: [cand(25)],
                        27: [cand(27, direction="bearish", level=99.7, target=90.0)]})
    assert both.arms == [(25, 30, "expired"), (27, 32, "expired")]


def test_a_candidate_whose_bar_does_not_test_never_arms(flat_atr):
    assert _replay(_episode_frame(), {26: [cand(26)]}).arms == []


def test_an_arm_running_off_the_frame_is_unresolved_and_holds_the_direction(flat_atr):
    """Review focus: the last arm of a frame never resolves."""
    result = _replay(frame({25: TEST}, n=28), {25: [cand(25)], 27: [cand(27, level=98.8)]})
    assert result.arms == [(25, None, "unresolved")]
    assert result.counts["unresolved"] == 1


def test_a_nan_atr_frame_arms_nothing(monkeypatch):
    """Review focus: reaction.is_test refuses a NaN ATR, so no arm opens."""
    monkeypatch.setattr(sa, "atr", lambda df, period=14: pd.Series(np.nan, index=df.index))
    assert _replay(_episode_frame(), {25: [cand(25)]}).arms == []


def test_a_trigger_issues_a_stop_entry_at_the_trigger_bar_high(flat_atr, monkeypatch):
    # Pins the pre-clamp geometry; the clamp's own effect is the next test.
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
    df = frame(MSB_FRAME)
    result = _replay(df, {25: [cand(25)]})
    assert result.counts["issued"] == 1 and len(result.confirmed) == 1
    j, plan, trigger = result.issued[0]
    assert (j, trigger) == (28, "MSB")
    assert plan.entry_type == "stop_entry" and plan.entry_price is None
    assert plan.trigger_price == pytest.approx(101.9)              # High[28]
    assert plan.expiry_bars == ar.STOP_ENTRY_EXPIRY_BARS == 2
    assert plan.stop_loss == pytest.approx(98.4)                   # min(98.5, 98.6) - 0.10 * 1.0
    assert plan.tp1 == pytest.approx(108.0)                        # 1.74R, inside [1.5, 2.5]
    assert plan.status == PlanStatus.PENDING and plan.status_history == []
    assert plan.created_at == df.index[28].date().isoformat()


def test_the_live_hard_cap_clamp_applies_unchanged(flat_atr, monkeypatch):
    """Spec §3.1: the clamp applies exactly as live -- a 3.4% stop is
    clamped to 1.75% under the 101.9 trigger."""
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    _, plan, _ = _replay(frame(MSB_FRAME), {25: [cand(25)]}).issued[0]
    assert plan.stop_loss == pytest.approx(101.9 * (1 - 0.0175))


def test_regates_are_counted_and_still_count_as_triggered(flat_atr, monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
    result = _replay(frame(MSB_FRAME), {25: [cand(25)]}, confluence=1)
    assert result.arms == [(25, 28, "regate_confluence")]
    assert result.issued == [] and len(result.confirmed) == 1      # the permutation population
    assert _replay(frame(MSB_FRAME), {25: [cand(25)]}, resistances=()).arms == [
        (25, 28, "regate_no_target")]


def test_replay_never_reads_past_the_deciding_bar():
    """NO-LOOKAHEAD on the real pipeline (arm_candidates, levels_asof,
    confirmed_pivots, plan_at): every arm resolved and every plan issued at
    j <= t is identical on the full frame and on full.iloc[:t + 1]."""
    df = structured_df()
    p = params(min_target_confluence_count=1, min_stop_distance_pct=0.5,
               max_stop_loss_pct=15.0, min_reward_pct=1.0)
    cells = [sa.StructCell(sa.MSB, 10, 0.5), sa.StructCell(sa.HL, 15, 0.5)]
    full = sa.replay_structure("AAPL", df, "4w", cells, params=p)
    assert full["MSB-N10-k0.50"].counts["issued"] >= 1, "fixture must issue at least once"

    def signature(result, t):
        plans = sorted((j, k, pl.direction, round(pl.trigger_price, 6), round(pl.stop_loss, 6),
                        round(pl.tp1, 6)) for j, pl, k in result.issued if j <= t)
        return plans, [a for a in result.arms if a[1] is not None and a[1] <= t]

    for t in (len(df) - 2, len(df) - 15, len(df) - 30):
        trunc = sa.replay_structure("AAPL", df.iloc[:t + 1], "4w", cells, params=p)
        for cell in cells:
            assert signature(full[cell.cell_id], t) == signature(trunc[cell.cell_id], t), (t, cell)
