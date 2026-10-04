import pytest

from swingbot import config
from swingbot.core.market.indicators import atr
from swingbot.core.planning.exit_sim import _scale_out_exit_walk, runner_structure_frame
from swingbot.core.planning.plan_engine import simulate_exit
from tests.planning.structure_fixtures import WARMUP, sawtooth, sawtooth_closes, stall_frame
from tests.planning.test_exit_sim_scaleout_witness import FIXTURE, witness_hash, witness_rows
from tests.planning.test_exit_sim_single import _plan

E = WARMUP - 1


def _runner_plan(**kw):
    return _plan(stop_loss=95.0, tp1=101.0, tp2=None, trail_atr_mult=50.0, horizon_key="2m", **kw)


def _mode(monkeypatch, mode, b=0.0, c=1.0):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", mode)
    monkeypatch.setattr(config, "RUNNER_HL_TRAIL_ATR_BUFFER", b)
    monkeypatch.setattr(config, "RUNNER_STALL_RANGE_MAX", c)


def test_off_is_byte_identical(monkeypatch):
    _mode(monkeypatch, "off")
    assert witness_hash() == FIXTURE.read_text(encoding="utf-8").strip()


@pytest.mark.parametrize("mode", ["hl_trail", "progress_stall"])
def test_no_outcome_flips(monkeypatch, mode):
    _mode(monkeypatch, "off")
    base = [row[4]["outcome"] for row in witness_rows()]
    _mode(monkeypatch, mode)
    assert [row[4]["outcome"] for row in witness_rows()] == base


def test_hl_stop_moves_only_from_the_bar_after_confirmation(monkeypatch):
    _mode(monkeypatch, "hl_trail", b=0.25)
    df = sawtooth(4)
    frame, atr14, trace = runner_structure_frame(df), atr(df, 14), []
    _scale_out_exit_walk(df, E, 100.0, _runner_plan(), 60, trace=trace)
    stops = dict(trace)
    confirm = WARMUP + 6 + 3                         # first post-entry swing low confirms here
    assert stops[confirm - 1] == pytest.approx(100.0 + 2 / 3 * 1.0)   # still the runner floor
    expected = frame["sl_px"].iloc[confirm] - 0.25 * float(atr14.iloc[confirm])
    assert stops[confirm] == pytest.approx(max(stops[confirm - 1], expected))
    assert all(b >= a for a, b in zip([s for _, s in trace], [s for _, s in trace][1:]))


def test_hl_stop_is_hit_on_a_drop_through_the_swing_low(monkeypatch):
    closes = sawtooth_closes(4)
    # closes[-1] (bar 87) is not yet a confirmed pivot; the last confirmed swing
    # low is cycle 3's (close sl - 5), so the drop must clear it.
    df = sawtooth(4, tail=(closes[-1] - 6.0,))
    _mode(monkeypatch, "off")
    base = _scale_out_exit_walk(df, E, 100.0, _runner_plan(), 60)
    _mode(monkeypatch, "hl_trail")
    arm = _scale_out_exit_walk(df, E, 100.0, _runner_plan(), 60)
    assert base.runner_outcome == "runner_timeout"
    assert arm.runner_outcome == "runner_trail" and arm.exit_index == len(df) - 1
    assert arm.outcome == base.outcome == "win"
    assert arm.legs[1]["exit_price"] == pytest.approx(runner_structure_frame(df)["sl_px"].iloc[-1])


def test_pivot_never_moves_the_stop_its_confirmation_bar_is_checked_against(monkeypatch):
    """Confirmation is non-strict on the right: bar confirm's Low may EQUAL the
    pivot low. With b = 0 the new stop equals that Low, so applying the update
    before bar confirm's own hit check would exit runner_trail there."""
    _mode(monkeypatch, "hl_trail", b=0.0)
    df = sawtooth(4)
    pivot = WARMUP + 6
    confirm = pivot + 3
    df.iloc[confirm, df.columns.get_loc("Low")] = df["Low"].iloc[pivot]
    frame = runner_structure_frame(df)
    assert frame["sl_i"].iloc[confirm] == pivot                       # confirms at this bar
    assert frame["sl_px"].iloc[confirm] == df["Low"].iloc[confirm]    # stop would touch it
    res = _scale_out_exit_walk(df, E, 100.0, _runner_plan(), 60)
    assert not (res.runner_outcome == "runner_trail" and res.exit_index == confirm)
    assert res.exit_index > confirm


def _stall_j(df):
    frame = runner_structure_frame(df)
    hits = [j for j in range(E + 1, len(df)) if frame["sh_i"].iloc[j] == j - 3
            and frame["sh_px"].iloc[j] <= frame["sh_prev_px"].iloc[j]]
    assert hits, "fixture must print a failed higher high"
    j = hits[0]
    assert frame["range_trend_10_50"].iloc[j] <= 0.70 and frame["vol_trend_10_50"].iloc[j] <= 1.0
    return j


def test_off_mode_never_stalls(monkeypatch):
    df = stall_frame()
    _stall_j(df)
    _mode(monkeypatch, "off", c=0.70)
    res = _scale_out_exit_walk(df, E, 100.0, _runner_plan(), 60)
    assert res.runner_outcome == "runner_timeout" and res.exit_index == len(df) - 1


def test_stall_exits_at_next_open(monkeypatch):
    df = stall_frame()
    j = _stall_j(df)
    _mode(monkeypatch, "progress_stall", c=0.70)
    res = _scale_out_exit_walk(df, E, 100.0, _runner_plan(), 60)
    assert res.runner_outcome == "runner_progress_stall"
    assert res.exit_index == j + 1
    assert res.legs[1]["exit_price"] == pytest.approx(float(df["Open"].iloc[j + 1]))


def test_stall_exit_takes_a_gapped_open_below_the_stop(monkeypatch):
    df = stall_frame()
    j = _stall_j(df)
    df.iloc[j + 1, df.columns.get_loc("Open")] = 99.0          # below the 100.667 floor
    _mode(monkeypatch, "progress_stall")
    res = _scale_out_exit_walk(df, E, 100.0, _runner_plan(), 60)
    assert res.exit_index == j + 1 and res.legs[1]["exit_price"] == pytest.approx(99.0)


def test_stall_on_the_last_walked_bar_defers_to_timeout(monkeypatch):
    df = stall_frame()
    j = _stall_j(df)
    _mode(monkeypatch, "progress_stall")
    capped = _scale_out_exit_walk(df, E, 100.0, _runner_plan(), j - E)      # end == j
    assert capped.runner_outcome == "runner_timeout" and capped.exit_index == j
    final = _scale_out_exit_walk(df.iloc[:j + 1], E, 100.0, _runner_plan(), 60)   # j == n-1
    assert final.runner_outcome == "runner_timeout"


def test_never_acts_before_tp1(monkeypatch):
    df = stall_frame()
    far = _plan(stop_loss=95.0, tp1=500.0, tp2=None, horizon_key="2m")
    _mode(monkeypatch, "off")
    base = simulate_exit(df, E, far, scale_out=True)
    _mode(monkeypatch, "progress_stall")
    assert simulate_exit(df, E, far, scale_out=True) == base


@pytest.mark.parametrize("mode", ["hl_trail", "progress_stall"])
def test_runner_stops_are_truncation_stable(monkeypatch, mode):
    """no-lookahead: the stop set after bar k is the same whether or not bars
    after k exist."""
    _mode(monkeypatch, mode, b=0.25)
    df = stall_frame()
    full = []
    _scale_out_exit_walk(df, E, 100.0, _runner_plan(), 60, trace=full)
    for k in range(E + 2, len(df)):
        cut = []
        _scale_out_exit_walk(df.iloc[:k + 1], E, 100.0, _runner_plan(), 60, trace=cut)
        assert cut == full[:len(cut)], k
