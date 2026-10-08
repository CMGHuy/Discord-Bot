"""v129 replay: one entry, simulated under today's exit (baseline) and under
each grid cell. Hand-built bars; ATR is passed in as 2.0 so every number is
checkable by hand. entry 100 (market, bar 0), level 99, tp1 104.
Cell m0.5_b0: disaster stop max(99 - 1, 98) = 98, close threshold 99."""
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.backtesting.acceptance_replay import (
    B_STEPS, CELLS, M_STEPS, UNTRIGGERED, cell_key, entry_row, replay_entries,
)
from swingbot.core.backtesting.backtest import run_backtest
from swingbot.core.planning.exit_sim import simulate_exit
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df
from tests.fixtures.ohlcv_parity import load_ohlcv
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_single import _plan

ATR = 2.0


def _zplan(**kw):
    base = dict(source="confluence", direction="bullish", stop_loss=99.0, tp1=104.0,
                acceptance_level=99.0)
    base.update(kw)
    return _plan(**base)


def test_grid_and_cell_keys():
    assert M_STEPS == (0.5, 1.0, 1.5) and B_STEPS == (0.0, 0.25)
    assert [cell_key(m, b) for m, b in CELLS["Z"]] == [
        "m0.5_b0", "m0.5_b0.25", "m1_b0", "m1_b0.25", "m1.5_b0", "m1.5_b0.25"]
    assert [cell_key(m, b) for m, b in CELLS["B"]] == ["b0", "b0.25"]


def test_sweep_and_reclaim_flips_a_baseline_loss():
    # Bar 1 wicks to 98.6 (through the level, not the disaster stop) and
    # closes back above 99. Bar 2 reaches TP1.
    df = make_ohlcv([100.0, (99.5, 100.0, 98.6, 99.6), (99.6, 104.5, 99.5, 104.2)])
    row = entry_row("Z", df, 0, _zplan(), ATR, CELLS["Z"])
    assert row["eligible"] is True
    assert row["baseline"]["outcome"] == "loss"
    assert row["baseline"]["r_multiple"] == -1.0
    assert row["baseline"]["exit_mix"] == "stop"
    assert row["baseline"]["planned_rr"] == pytest.approx(4.0)
    cell = row["cells"]["m0.5_b0"]
    assert cell["outcome"] == "win"
    assert cell["exit_mix"].startswith("tp1+")
    assert cell["planned_rr"] == pytest.approx(2.0)   # 1R is entry -> disaster stop


def test_close_through_exits_with_the_acceptance_reason_and_buffer_defers_it():
    df = make_ohlcv([100.0, (99.5, 99.8, 98.4, 98.7)])
    row = entry_row("Z", df, 0, _zplan(), ATR, CELLS["Z"])
    tight = row["cells"]["m0.5_b0"]            # threshold 99: 98.7 closes through
    assert tight["outcome"] == "loss"
    assert tight["exit_mix"] == "acceptance_exit"
    assert tight["r_multiple"] == pytest.approx(-0.65)
    buffered = row["cells"]["m0.5_b0.25"]      # threshold 98.5: 98.7 does not
    assert buffered["exit_mix"] == "timeout"
    assert buffered["r_multiple"] == pytest.approx(-0.65)


def test_not_eligible_plan_keeps_todays_exit_in_every_cell():
    # Level 97 is 3% from entry: beyond the 2% cap, so the clamp moved the stop.
    df = make_ohlcv([100.0, (99.5, 99.8, 98.0, 98.4)])
    row = entry_row("Z", df, 0, _zplan(stop_loss=98.25, acceptance_level=97.0), ATR, CELLS["Z"])
    assert row["eligible"] is False
    assert all(record == row["baseline"] for record in row["cells"].values())
    assert row["baseline"]["exit_mix"] == "stop"


def test_gap_through_the_disaster_stop_is_flagged_and_still_books_minus_one():
    df = make_ohlcv([100.0, (97.0, 97.5, 96.5, 97.2)])
    row = entry_row("Z", df, 0, _zplan(), ATR, CELLS["Z"])
    cell = row["cells"]["m0.5_b0"]
    assert cell["r_multiple"] == -1.0
    assert cell["gap_through"] is True
    assert row["baseline"]["gap_through"] is True


def _stop_entry_plan():
    return _zplan(entry_type="stop_entry", trigger_price=100.0, expiry_bars=3)


def test_replay_keeps_rows_where_only_a_cell_triggered():
    # Bar 1 closes at 98.7: through today's stop (99, pending invalidated) but
    # not through the disaster stop (98). Bar 2 triggers, bar 3 reaches TP1.
    df = make_ohlcv([(99.5, 99.8, 99.3, 99.6), (99.5, 99.7, 98.5, 98.7),
                     (98.8, 100.6, 98.7, 100.4), (100.4, 104.5, 100.2, 104.2)])
    row = entry_row("Z", df, 0, _stop_entry_plan(), ATR, CELLS["Z"])
    assert row is not None
    assert row["baseline"] is None
    assert row["cells"]["m0.5_b0"]["outcome"] == "win"


def test_entry_row_is_none_when_nothing_triggered():
    df = make_ohlcv([(99.5, 99.8, 99.3, 99.6), (99.5, 99.7, 98.5, 98.7)])
    assert entry_row("Z", df, 0, _stop_entry_plan(), ATR, CELLS["Z"]) is None


def test_arm_b_adds_the_close_exit_and_leaves_the_stop_alone():
    plan = _plan(strategy="Break & Retest", direction="bullish", stop_loss=96.0,
                 tp1=108.0, acceptance_level=99.0)
    df = make_ohlcv([100.0, (99.5, 99.8, 98.4, 98.7)])
    row = entry_row("B", df, 0, plan, ATR, CELLS["B"])
    assert set(row["cells"]) == {"b0", "b0.25"}
    assert row["baseline"]["exit_mix"] == "timeout"
    assert row["cells"]["b0"]["exit_mix"] == "acceptance_exit"
    assert row["cells"]["b0"]["outcome"] == "loss"
    assert row["cells"]["b0"]["r_multiple"] == pytest.approx(-0.325)
    assert row["cells"]["b0.25"] == row["baseline"]          # 98.7 is above 98.5
    assert row["cells"]["b0"]["planned_rr"] == row["baseline"]["planned_rr"] == pytest.approx(2.0)


def test_entry_row_does_not_mutate_the_shared_plan():
    plan = _zplan()
    entry_row("Z", make_ohlcv([100.0, (99.5, 100.0, 98.6, 99.6)]), 0, plan, ATR, CELLS["Z"])
    assert plan.stop_loss == 99.0 and plan.acceptance_close_below is None


def test_replay_refuses_to_run_with_the_flag_on(monkeypatch):
    monkeypatch.setattr(config, "ACCEPTANCE_EXIT_ENABLED", True)
    monkeypatch.setattr(config, "ACCEPTANCE_EXIT_ARMS", "Z,B")
    with pytest.raises(RuntimeError, match="ACCEPTANCE_EXIT_ENABLED"):
        replay_entries("Z", "AAPL", make_ohlcv([100.0] * 5), ("4w",))


@pytest.mark.slow
def test_confluence_replay_baseline_is_todays_exit():
    df = _structured_df()
    rows = replay_entries("Z", "AAPL", df, ("4w",), gates=GATES)
    assert rows
    by_key = {(row["entry_date"], row["direction"]): row for row in rows}
    keys = {cell_key(m, b) for m, b in CELLS["Z"]}
    for i, plan in bs.replay_scenarios("AAPL", df, "4w", gates=GATES):
        res = simulate_exit(df, i, plan, scale_out=True)
        row = by_key.get((str(df.index[i].date()), plan.direction))
        if res.outcome in UNTRIGGERED:
            assert row is None or row["baseline"] is None
            continue
        assert row["baseline"]["outcome"] == res.outcome
        assert row["baseline"]["r_multiple"] == res.r_total
        assert set(row["cells"]) == keys


@pytest.mark.slow
def test_break_retest_replay_baseline_matches_run_backtest():
    df = load_ohlcv("DELL")
    summary = run_backtest("DELL", df, "Break & Retest", "2m",
                           exit_model="v2", scale_out=True, tp2_mode="levels")
    rows = replay_entries("B", "DELL", df, ("2m",))
    assert summary.trades, "fixture must trade"
    assert [(r["entry_date"], r["baseline"]["outcome"], round(r["baseline"]["r_multiple"], 3))
            for r in rows] == [(t.entry_date, t.outcome, t.r_multiple) for t in summary.trades]
    assert all(set(r["cells"]) == {"b0", "b0.25"} for r in rows)


def test_window_filters_on_the_signal_date():
    df = load_ohlcv("DELL")
    everything = replay_entries("B", "DELL", df, ("2m",))
    first = everything[0]["entry_date"]
    only_first = replay_entries("B", "DELL", df, ("2m",), start=first, end=first)
    assert [r["entry_date"] for r in only_first] == [first]
