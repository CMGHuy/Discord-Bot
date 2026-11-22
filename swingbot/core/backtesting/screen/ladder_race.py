"""v238 rungs 2-4: the orderable race (v230 spec Part B, index "Rung shapes").

Stop and target are prices known at the signal close, so the alert can rest
them as orders; entry is the open of t+1 and R is measured against the
planned risk |Close[t] - stop|. Bars t+1..t+cap race as race._first_exit:
an open beyond the stop or target exits at that open (on bar t+1 that is
the entry price: gross 0R, net = the costs), then stop/target touches (stop
first), then the close of bar t+cap. No event is dropped for a gap."""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import race, sides
from swingbot.core.backtesting.screen.ladder import LadderEvent

STRESS_FACTOR = 2      # the book re-priced at 2 x slippage; printed, never gating
GAP_OUTCOMES = ("gap_stop", "gap_target")
_OHLC = ("Open", "High", "Low", "Close")
_BAD_LEVELS = ("each stop must sit on the loss side of the signal close and each "
               "target beyond it on the profit side")


def _sign(direction: str) -> float:
    if direction == "long":
        return 1.0
    if direction == "short":
        return -1.0
    raise ValueError(f"unknown direction {direction!r}; expected 'long' or 'short'")


def orderable_levels(df: pd.DataFrame, signal_pos, *, atr, direction: str):
    """(stop, target) at race.STOP_ATR / REWARD_RISK x ATR14[t] from Close[t]."""
    pos = np.asarray(signal_pos, dtype=int)
    sign = _sign(direction)
    close = df["Close"].to_numpy(dtype=float)[pos]
    risk = race.STOP_ATR * pd.Series(atr).to_numpy(dtype=float)[pos]
    return close - sign * risk, close + sign * race.REWARD_RISK * risk


def _oriented_levels(close_o, stop, target, sign):
    stop_o = sign * np.asarray(stop, dtype=float)
    target_o = sign * np.asarray(target, dtype=float)
    risk = close_o - stop_o
    ok = np.isfinite(risk) & (risk > 0) & np.isfinite(target_o) & (target_o > close_o)
    if not ok.all():
        raise ValueError(_BAD_LEVELS)
    return stop_o, target_o, risk


def race_levels(df: pd.DataFrame, signal_pos, cap: int, *, stop, target,
                direction: str = "long", slippage_bps=None,
                commission=None) -> race.RaceResult:
    """Race each signal bar t from the open of t+1 to the given stop/target prices."""
    pos = np.asarray(signal_pos, dtype=int)
    race._check_positions(pos, cap, len(df))
    if pos.size == 0:
        return race.RaceResult.empty()
    sign = _sign(direction)
    o, h, l, c = sides.oriented(*(df[col].to_numpy(dtype=float) for col in _OHLC), direction)
    stop_o, target_o, risk = _oriented_levels(c[pos], stop, target, sign)
    bars = pos[:, None] + 1 + np.arange(cap)[None, :]
    entry = o[pos + 1]
    price, code, offset = race._first_exit(o[bars], h[bars], l[bars], c[bars], stop_o, target_o)
    exit_pos = pos + 1 + offset
    gross = (price - entry) / risk
    entry, price = sign * entry, sign * price            # back to real prices; exact
    net = sides.net_r(entry, price, risk, direction=direction,
                      days=sides.holding_days(df.index, pos + 1, exit_pos),
                      slippage_bps=slippage_bps, commission=commission)
    return race.RaceResult(pos, exit_pos, entry, risk, gross, net,
                           np.asarray(race.OUTCOMES)[code])


def gap_through(result: race.RaceResult) -> tuple[int, float]:
    """Events that exited at a gapped open, and their summed net R."""
    mask = np.isin(result.outcome, GAP_OUTCOMES)
    return int(mask.sum()), float(result.r[mask].sum())


def _same_events(result: race.RaceResult, stress: race.RaceResult) -> None:
    if not (np.array_equal(result.event_pos, stress.event_pos)
            and np.array_equal(result.exit_pos, stress.exit_pos)):
        raise ValueError("the stress book must race the same events to the same exits")


def to_events(ticker: str, df: pd.DataFrame, result: race.RaceResult, *,
              stress: race.RaceResult | None = None) -> list[LadderEvent]:
    """One LadderEvent per raced signal; ``stress`` adds r_stress."""
    if stress is not None:
        _same_events(result, stress)
    day = lambda p: df.index[np.asarray(p, dtype=int)].strftime("%Y-%m-%d")  # noqa: E731
    signal, entry, exit_ = day(result.event_pos), day(result.event_pos + 1), day(result.exit_pos)
    r_stress = [None] * len(result) if stress is None else [float(x) for x in stress.r]
    return [LadderEvent(ticker, signal[i], entry[i], exit_[i], float(result.r[i]),
                        float(result.gross_r[i]), str(result.outcome[i]), r_stress=r_stress[i])
            for i in range(len(result))]
