"""v147 T1: TRAIN compression gate rows through StrategyEngine (in-sample).

The world is v119's compression-short fixture (tests/backtesting/test_measure_compression_short.py):
one bearish 2w candidate on SIGNAL_DAY whose resting sell-stop fills next bar and time-exits on the
tenth session. A clear earnings snapshot admits it (taken); no snapshot rejects it as
earnings_unknown (blocked). The sink is record-only: trades and counters never change.
"""
from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from swingbot.core.backtesting import gate_counterfactual
from swingbot.core.backtesting.arms import compression_research as cr
from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.scan_params import ScanParams
from tests.backtesting.test_measure_compression_short import (  # noqa: F401  (pins: autouse fixture)
    FULL_PATH, SIGNAL_DAY, SIGNAL_POS, WINDOW, _context, pins)


def _padded(frame, extra=3):
    """FULL_PATH plus `extra` flat sessions repeating its last close.

    The v119 world ends 12 sessions after the signal (the engine's time stop closes it on the
    tenth); `simulate_blocked` waits for expiry_bars + the 2w hold (1 + 14 = 15) before it walks,
    so the unpadded frame is `pending`. The padding lies after the engine's exit and changes
    nothing it reads."""
    last = frame.iloc[-1]
    index = pd.bdate_range(start=frame.index[-1] + pd.offsets.BDay(1), periods=extra)
    flat = pd.DataFrame({column: [float(last["Close"]) if column != "Volume" else float(last["Volume"])] * extra
                         for column in frame.columns}, index=index)
    return pd.concat([frame, flat])


PADDED_PATH = _padded(FULL_PATH)


def _unknown(ticker, decided_at):
    return None                                       # no as-of archive -> earnings_unknown


def _run(context, *, sink=None, allowlist=None):
    engine = StrategyEngine((COMPRESSION_SHORT,), compression_context=context,
                            blocked_sink=sink, compression_allowlist=allowlist)
    trades = engine.run_ticker("ABC", FULL_PATH, ("2w",), WINDOW, ScanParams.from_config())
    return engine, trades


@pytest.mark.parametrize("snapshot_of", [None, _unknown])
def test_the_sink_is_record_only(snapshot_of):
    context = _context() if snapshot_of is None else _context(snapshot_of=snapshot_of)
    plain_engine, plain = _run(context)
    sunk_engine, sunk = _run(context, sink=[])
    assert [dataclasses.asdict(t) for t in sunk] == [dataclasses.asdict(t) for t in plain]
    assert sunk_engine.compression_reasons == plain_engine.compression_reasons
    assert sunk_engine.compression_excluded == plain_engine.compression_excluded


def test_a_rejected_candidate_is_a_blocked_candidate_without_a_plan():
    sink: list = []
    _, trades = _run(_context(snapshot_of=_unknown), sink=sink)
    assert trades == []
    ((arm, candidate),) = sink
    assert arm == "blocked"
    assert (candidate.gate, candidate.reason, candidate.source) == ("compression", "earnings_unknown", "strategy")
    assert (candidate.strategy, candidate.horizon, candidate.direction) == (COMPRESSION_SHORT, "2w", "bearish")
    assert candidate.signal_date == SIGNAL_DAY.isoformat()
    assert candidate.plan is None and candidate.margin is None
    assert candidate.scan_params["stop_mult"] is None and candidate.scan_params["params"]   # the engine's call
    assert candidate.signal_close == pytest.approx(float(FULL_PATH["Close"].iloc[SIGNAL_POS]))


def test_a_passed_candidate_is_a_taken_candidate_carrying_the_engines_plan():
    sink: list = []
    _, trades = _run(_context(), sink=sink)
    assert len(trades) == 1
    ((arm, candidate),) = sink
    assert arm == "taken" and candidate.reason is None
    assert candidate.plan["strategy"] == COMPRESSION_SHORT
    assert candidate.plan["entry_context"]["compression_mode"] == "broad"


def test_the_research_membership_mask_is_never_a_row():
    sink: list = []
    engine, _ = _run(_context(member_on=lambda ticker, day: False), sink=sink)
    assert sink == [] and engine.compression_reasons == {"not_pit_member": 1}


def test_the_allowlist_override_decides_instead_of_the_research_knob():
    sink: list = []
    _run(_context(), sink=sink, allowlist=("isolated",))       # falling SPY: a broad candidate
    ((arm, candidate),) = sink
    assert (arm, candidate.reason) == ("blocked", "mode_not_allowed")


def test_record_blocked_compression_walks_both_arms_through_one_instrument():
    taken_rows = cr.record_blocked_compression({"ABC": PADDED_PATH}, WINDOW, context=_context())
    blocked_rows = cr.record_blocked_compression({"ABC": PADDED_PATH}, WINDOW,
                                                 context=_context(snapshot_of=_unknown))
    (taken,) = taken_rows
    (blocked,) = blocked_rows
    for row in (taken, blocked):
        assert (row["population"], row["gate"], row["source"]) == ("train", "compression", "strategy")
        assert row["in_sample"] is True and row["margin"] is None
        assert row["signal_date"] == SIGNAL_DAY.isoformat() and row["horizon"] == "2w"
        assert row["cf_status"] == "filled"
    assert (taken["arm"], taken["reason"]) == ("taken", None)
    assert (blocked["arm"], blocked["reason"]) == ("blocked", "earnings_unknown")
    _, (trade,) = _run(_context())
    assert taken["cf_r"] == pytest.approx(trade.r_multiple)
    # The truncated rebuild of the rejected candidate is the same constructor on the same bars:
    # a mismatch here is a real divergence between simulate_blocked and the engine -- stop and
    # report it, never loosen the assertion.
    assert blocked["cf_r"] == pytest.approx(taken["cf_r"])


def test_a_pending_simulation_is_written_as_no_data(monkeypatch):
    pending = gate_counterfactual.CounterfactualResult(
        cf_status="pending", cf_r=None, win=None, exit_index=None, last_bar_date=None,
        bars_sha256=None, reanchored=False, plan=None)
    monkeypatch.setattr(gate_counterfactual, "simulate_blocked", lambda candidate, bars, **kw: pending)
    (row,) = cr.record_blocked_compression({"ABC": FULL_PATH}, WINDOW, context=_context(snapshot_of=_unknown))
    assert row["cf_status"] == "no-data" and row["cf_r"] is None and row["win"] is None


def test_a_signal_before_the_window_start_is_never_a_row():
    late_window = ("2019-03-04", "2020-12-31")                # SIGNAL_DAY (2019-03-01) is warm-up
    assert cr.record_blocked_compression({"ABC": FULL_PATH}, late_window, context=_context()) == []
