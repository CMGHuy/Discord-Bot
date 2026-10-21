"""v180 A2 (the v119 amendment A2, adopted verbatim): the circular entry-shift null for an
ADDITIVE arm.

``scripts/backtest/permutation_test.py``'s circular entry shift -- n = 200, seed 42, shifts
drawn from ``SHIFT_RANGE`` -- scored with the A1 statistic (``acceptance.win_rate_statistic``).

Why a second null: ``permutation_test.arm_pair_permutation`` rolls the *removal* labels of the
baseline. An arm that removes nothing (a new entry strategy added on top of the book) has no
removal labels, so its null equals the component for every shift and p == 1.0 -- it cannot
see an additive arm at all.

This null keeps the real baseline fixed and replays only the added strategy with
``bt.ENTRY_SHIFT`` rolled, severing that strategy's signal/price-future link while keeping its
entry count, autocorrelation and exit engine.

``bt.ENTRY_SHIFT`` and the knob deltas are process-global: offline scripts only, never the
live bot.
"""
from typing import Callable

import numpy as np

from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting.acceptance import population_split
from swingbot.core.backtesting.arms.knobs import apply_knobs
from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine

SHIFT_RANGE = (20, 200)   # == permutation_test.SHIFT_RANGE: >= 20 bars, nothing 'almost' aligns


class NotAdditive(ValueError):
    """The component removes or changes baseline rows; the shift null needs a pure addition."""


class ReplayMismatch(ValueError):
    """Shift 0 of the replay does not reproduce the rows the arm added."""


def additive_added(baseline, component) -> list:
    """The component's added rows; raises NotAdditive on any removed or changed baseline row."""
    split = population_split(baseline, component)
    removed, changed = split["removed"], split["changed"]
    if removed or changed:
        raise NotAdditive(f"{len(removed)} removed, {len(changed)} changed")
    return split["added"]


def _verify_shift_zero(added, replay_added) -> None:
    replayed = {trade.key for trade in replay_added(0)}
    if replayed != {trade.key for trade in added}:
        raise ReplayMismatch(f"shift 0 replayed {len(replayed)} rows, the arm added {len(added)}")


def _shifted_null(baseline, replay_added, statistic, shifts, progress) -> list:
    null, total = [], len(shifts)
    for done, shift in enumerate(shifts, start=1):
        null.append(statistic(baseline, list(baseline) + list(replay_added(int(shift)))))
        if progress is not None:
            progress(done, total)
    return null


def shift_permutation(baseline, component, replay_added: Callable[[int], list], statistic, *,
                      n_perm: int = 200, seed: int = 42, verify_zero: bool = True,
                      progress: Callable[[int, int], None] | None = None) -> dict:
    """P-value of ``statistic(baseline, component)`` against the shifted-replay null."""
    added = additive_added(baseline, component)
    if verify_zero:
        _verify_shift_zero(added, replay_added)
    observed = statistic(baseline, component)
    shifts = np.random.default_rng(seed).integers(*SHIFT_RANGE, size=n_perm)
    null = _shifted_null(baseline, replay_added, statistic, shifts, progress)
    valid = [value for value in null if value is not None]
    p = None if observed is None or not valid else float(np.mean([v >= observed for v in valid]))
    return {"observed": observed, "p_value": p, "n": int(n_perm), "n_valid": len(valid),
            "seed": seed, "shift_range": list(SHIFT_RANGE), "added": len(added),
            "statistic": getattr(statistic, "__name__", str(statistic))}


def strategy_shift_replay(frames: dict, strategy: str, horizons, window: tuple[str, str],
                          delta: dict, *, instrument=None) -> Callable[[int], list]:
    """A ``replay(shift)`` that runs ``strategy`` alone over ``frames`` with entries rolled."""
    from swingbot.scan_params import ScanParams

    def replay(shift: int) -> list:
        rows = []
        bt.ENTRY_SHIFT = int(shift)
        try:
            with apply_knobs(delta):
                params = ScanParams.from_config()
                engine = StrategyEngine(strategies=(strategy,), instrument=instrument)
                for ticker in sorted(frames):
                    rows.extend(engine.run_ticker(ticker, frames[ticker], tuple(horizons),
                                                  tuple(window), params))
        finally:
            bt.ENTRY_SHIFT = 0
        return [row for row in rows if window[0] <= row.entry_date <= window[1]]
    return replay
