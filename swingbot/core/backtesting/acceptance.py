"""The acceptance gate -- what a feature must prove before it ships on.

Read `docs/claude/backtest-methodology.md` before changing anything here.
The clause set and its constants are PRE-REGISTERED: they are the bar, and
a component that fails them is dropped and documented, never re-measured
against a bar moved to fit it.

Win rate is the objective; expectancy is a non-inferiority constraint. The
two move against each other along the *geometry* axis (break-even win rate
at reward:risk X is 1/(1+X), so a nearer target buys win rate and no
profit) and together only along the *discrimination* axis. Clause 3 exists
to force a feature onto the second axis.

numpy only -- scipy is NOT in requirements.txt and is absent from the
Docker image this module ships in.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np

VERSION = 2   # acceptance-procedure version, recorded in every results doc


@dataclass(frozen=True)
class ArmTrade:
    """One trade in one arm, carrying exactly what the clauses read.

    Deliberately not BacktestTrade: that record has no ticker/strategy/
    horizon (they live on its BacktestSummary parent) and the measurement
    scripts each carry their own row dialect. This is the shared shape both
    adapt into.
    """
    ticker: str
    strategy: str
    horizon_key: str
    entry_date: str
    outcome: str                  # win | loss | scratch | timeout | not_triggered
    r_multiple: float | None
    planned_rr: float | None

    @property
    def key(self) -> tuple:
        """Pairing key across arms."""
        return (self.ticker, self.strategy, self.horizon_key, self.entry_date)

    @property
    def stratum(self) -> tuple:
        """Mix-standardisation and per-stratum reporting unit."""
        return (self.strategy, self.horizon_key)


def planned_rr(entry: float, stop: float, target: float) -> float | None:
    """Reward:risk as the plan was written, before the market answered.

    Direction-agnostic by construction (both legs are absolute), so a
    bearish plan and its mirror-image bullish plan return the same number.
    None on zero risk -- a plan that cannot lose cannot be priced.
    """
    risk = abs(entry - stop)
    if not risk:
        return None
    return abs(target - entry) / risk


def arm_trade_from_plan(plan, *, entry_date: str, outcome: str,
                        r_multiple: float | None) -> ArmTrade:
    """Adapt a TradePlanV2 (what replay_scenarios yields) plus its outcome."""
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    return ArmTrade(ticker=plan.ticker, strategy=plan.strategy,
                    horizon_key=plan.horizon_key, entry_date=entry_date,
                    outcome=outcome, r_multiple=r_multiple,
                    planned_rr=planned_rr(entry, plan.stop_loss, plan.tp1))


def arm_trade_from_backtest(trade, *, ticker: str, strategy: str,
                            horizon_key: str) -> ArmTrade:
    """Adapt a BacktestTrade. The three context fields live on the trade's
    BacktestSummary parent, not the trade, so the caller supplies them."""
    return ArmTrade(ticker=ticker, strategy=strategy, horizon_key=horizon_key,
                    entry_date=trade.entry_date, outcome=trade.outcome,
                    r_multiple=trade.r_multiple,
                    planned_rr=planned_rr(trade.entry, trade.stop_loss,
                                          trade.take_profit))


#: Outcomes that count toward the win-rate denominator.
DECIDED = ("win", "loss")
#: Outcomes that count as a closed trade for expectancy.
CLOSED = ("win", "loss", "scratch", "timeout")


def win_rate(trades) -> float | None:
    """Percent, over decided trades only. None when nothing was decided."""
    decided = [t for t in trades if t.outcome in DECIDED]
    if not decided:
        return None
    return 100.0 * sum(1 for t in decided if t.outcome == "win") / len(decided)


def expectancy_r(trades) -> float | None:
    """Mean R over all CLOSED trades -- scratches and timeouts drag it down,
    which is the point: they are capital that was committed and returned
    nothing."""
    rs = [t.r_multiple for t in trades
          if t.outcome in CLOSED and t.r_multiple is not None]
    if not rs:
        return None
    return float(np.mean(rs))


def _by_stratum(trades) -> dict:
    out = defaultdict(list)
    for t in trades:
        out[t.stratum].append(t)
    return out


def stratum_weights(trades) -> dict:
    """Share of DECIDED trades in each (strategy, horizon) stratum."""
    counts = Counter(t.stratum for t in trades if t.outcome in DECIDED)
    total = sum(counts.values())
    if not total:
        return {}
    return {k: v / total for k, v in counts.items()}


def standardised_win_rate(trades, weights: dict) -> float | None:
    """The win rate this arm would show if its stratum mix matched
    `weights` -- i.e. holding composition fixed so only within-stratum
    skill can move the number.

    Strata the arm has no decided trade in are dropped and the remaining
    weights renormalised, rather than imputed: an arm that emptied a
    stratum has no win rate there to standardise, and inventing one would
    reward exactly the mix shift this function exists to neutralise.
    """
    grouped = _by_stratum(trades)
    total = 0.0
    weight_sum = 0.0
    for stratum, weight in weights.items():
        wr = win_rate(grouped.get(stratum, []))
        if wr is None:
            continue
        total += weight * wr
        weight_sum += weight
    if not weight_sum:
        return None
    return total / weight_sum


def stratum_table(baseline, component) -> list:
    """One row per stratum present in EITHER arm, sorted for stable output."""
    b, c = _by_stratum(baseline), _by_stratum(component)
    rows = []
    for stratum in sorted(set(b) | set(c)):
        bt, ct = b.get(stratum, []), c.get(stratum, [])
        rows.append({
            "stratum": stratum,
            "baseline_n": sum(1 for t in bt if t.outcome in DECIDED),
            "component_n": sum(1 for t in ct if t.outcome in DECIDED),
            "baseline_win_rate": win_rate(bt),
            "component_win_rate": win_rate(ct),
            "baseline_expectancy_r": expectancy_r(bt),
            "component_expectancy_r": expectancy_r(ct),
        })
    return rows
