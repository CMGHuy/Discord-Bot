"""v180's descriptive Turtle Soup diagnostics (spec § The funnel, "Reported at every stage that runs").

It joins ``StrategyEngine.turtle_soup_events`` with the live sweep geometry and the screen's own fixed
race, and it scores the stage-3 badge on the added rows. Nothing here gates a stage, and the live bot
reads none of it. A signal row reads the same bars up to ``t`` that the engine read.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from swingbot.core.backtesting import arm_rule
from swingbot.core.backtesting.acceptance import CLOSED
from swingbot.core.backtesting.arms import turtle_soup_research as tsr
from swingbot.core.backtesting.arms.knobs import apply_knobs
from swingbot.core.backtesting.screen.race import race
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import MIN_BARS, TURTLE_SOUP
from swingbot.core.market.turtle_soup import sweep_frame
from swingbot.core.marketdata.pit_membership import is_member
from swingbot.core.planning.turtle_soup_plan import turtle_soup_rejection_reason

EARLY_STOP_SESSIONS = 2
SCREEN_CAP = 10            #: the screen's CAP (screen/ideas/turtle_soup.py), pinned equal by a test
BADGE_MIN_N = 15           #: backtest-methodology.md § Badge scoring, VALIDATION N
STATUSES = ("trade", "risk_cap", "no_level_in_band", "plan_other", "cancelled_open_through_stop",
            "cancelled_risk_cap_fill", "not_triggered", "position_open")
DROPPED_STATUSES = ("risk_cap", "no_level_in_band", "plan_other", "cancelled_open_through_stop",
                    "cancelled_risk_cap_fill")
#: Anything else (acceptance_exit, a data-end timeout) is "other".
EXIT_CATEGORIES = {"tp1": "target", "stop": "stop", "gap_stop": "gap", "gap_target": "gap",
                   "time_exit": "time_cap"}
SCREEN_WINS, SCREEN_LOSSES = ("target", "gap_target"), ("stop", "gap_stop")
_EVENT_BASE = ("ticker", "signal_date", "status")
_EXIT_KEYS = ("target", "stop", "gap", "time_cap", "other")


def screen_outcomes(df, positions) -> dict:
    """The screen's own fixed race per signal position, skipping any race that would read past the frame.
    No overlap thinning: an excluded population was never traded, so each signal races on its own."""
    kept = [int(pos) for pos in positions if int(pos) + SCREEN_CAP <= len(df) - 1]
    if not kept:
        return {}
    raced = race(df, kept, SCREEN_CAP)
    return {int(raced.event_pos[i]): {"screen_outcome": str(raced.outcome[i]), "screen_r": float(raced.r[i])}
            for i in range(len(raced.event_pos))}


def _status(event, df, pos, horizon_key, params) -> str:
    """No event: the one-position slot swallowed it. plan_none: split by the constructor's reason."""
    if event is None:
        return "position_open"
    if event["status"] == "plan_none":
        return turtle_soup_rejection_reason(df.iloc[:pos + 1], pos, horizon_key, scan_params=params)
    return event["status"]


def _signal_row(ticker, df, pos, sweep, atr14, by_date, screen, params, horizon_key) -> dict:
    signal_date = df.index[pos].date().isoformat()
    event = by_date.get(signal_date)
    prior_low, low, atr_t = float(sweep["prior_low"].iloc[pos]), float(df["Low"].iloc[pos]), float(atr14.iloc[pos])
    raced = screen.get(pos, {})
    row = {"ticker": str(ticker), "signal_date": signal_date, "signal_index": int(pos),
           "prior_low": prior_low, "low": low, "atr14": atr_t, "sweep_depth_atr": (prior_low - low) / atr_t,
           "status": str(_status(event, df, pos, horizon_key, params)),
           "screen_outcome": raced.get("screen_outcome"), "screen_r": raced.get("screen_r")}
    if row["status"] == "trade":
        row.update({key: _plain(value) for key, value in event.items() if key not in _EVENT_BASE})
    return row


def _plain(value):
    """numpy scalars -> Python scalars, so the record is JSON-serialisable."""
    return value.item() if isinstance(value, np.generic) else value


def signal_rows(ticker, df, events, window, *, params, horizon_key=tsr.HORIZON) -> list[dict]:
    """One row per live Turtle Soup signal in ``window``, joined to the engine's event for it."""
    if len(df) < MIN_BARS[horizon_key] + 10:
        return []
    sweep = sweep_frame(df)
    atr14 = atr(df, 14)
    dates = [day.date().isoformat() for day in df.index]
    positions = [pos for pos in np.flatnonzero(sweep["signal"].to_numpy(dtype=bool))
                 if window[0] <= dates[pos] <= window[1]]
    by_date = {e["signal_date"]: e for e in events if e["ticker"] == ticker}
    screen = screen_outcomes(df, positions)
    return [_signal_row(ticker, df, int(pos), sweep, atr14, by_date, screen, params, horizon_key)
            for pos in positions]


def _screen_summary(rows) -> dict:
    raced = [row for row in rows if row.get("screen_outcome") is not None]
    outcomes = Counter(row["screen_outcome"] for row in raced)
    wins = sum(outcomes[o] for o in SCREEN_WINS)
    decided = wins + sum(outcomes[o] for o in SCREEN_LOSSES)
    return {"raced": len(raced),
            "expectancy_r": float(np.mean([row["screen_r"] for row in raced])) if raced else None,
            "win_rate": 100 * wins / decided if decided else None,
            "outcomes": dict(outcomes)}


def drop_shares(rows) -> dict:
    """Count, share and the screen's race for each status (every STATUSES key present)."""
    by_status = {}
    for status in STATUSES:
        members = [row for row in rows if row["status"] == status]
        by_status[status] = {"count": len(members), "share": len(members) / len(rows) if rows else None,
                             "screen": _screen_summary(members)}
    return {"signals": len(rows), "by_status": by_status}


def _distribution(values) -> dict:
    if not values:
        return dict.fromkeys(("n", "mean", "p25", "median", "p75", "max"), None) | {"n": 0}
    arr = np.asarray(values, dtype=float)
    p25, median, p75 = (float(v) for v in np.percentile(arr, [25, 50, 75]))
    return {"n": len(values), "mean": float(np.mean(arr)), "p25": p25, "median": median, "p75": p75,
            "max": float(np.max(arr))}


def sweep_depth_summary(rows) -> dict:
    """Sweep depth in ATR14 for every signal, the kept (traded) ones and the dropped ones."""
    def depths(keep):
        return [row["sweep_depth_atr"] for row in rows if keep(row["status"])]
    return {"all": _distribution(depths(lambda s: True)),
            "kept": _distribution(depths(lambda s: s == "trade")),
            "dropped": _distribution(depths(lambda s: s in DROPPED_STATUSES))}


def _trades(rows) -> list[dict]:
    return [row for row in rows if row["status"] == "trade"]


def _win_rate(rows) -> float | None:
    decided = [row for row in rows if row.get("outcome") in ("win", "loss")]
    if not decided:
        return None
    return 100 * sum(row["outcome"] == "win" for row in decided) / len(decided)


def early_stop_share(rows) -> float | None:
    """Share of trades stopped (or gapped through the stop) within EARLY_STOP_SESSIONS sessions."""
    trades = _trades(rows)
    if not trades:
        return None
    early = sum(row["exit_reason"] in ("stop", "gap_stop") and row["hold_sessions"] <= EARLY_STOP_SESSIONS
                for row in trades)
    return early / len(trades)


def exit_mix(rows) -> dict:
    trades = _trades(rows)
    counts = Counter(EXIT_CATEGORIES.get(row["exit_reason"], "other") for row in trades)
    shares = {key: counts[key] / len(trades) if trades else 0.0 for key in _EXIT_KEYS}
    return {"n": len(trades), "shares": shares, "win_rate": _win_rate(trades)}


def _cohort(rows) -> dict:
    closed = [row["r_net"] for row in rows if row.get("outcome") in CLOSED]
    return {"n": len(rows), "expectancy_r": float(np.mean(closed)) if closed else None,
            "win_rate": _win_rate(rows)}


def _regime_of(signal_date, close, sma) -> str:
    """SPY close vs its 200-day SMA on the last bar <= the signal day (never a later bar)."""
    idx = close.index.searchsorted(pd.Timestamp(signal_date), side="right") - 1
    if idx < 0 or pd.isna(sma.iloc[idx]):
        return "unknown"
    return "above" if close.iloc[idx] > sma.iloc[idx] else "below"


def regime_split(rows, spy) -> dict:
    trades = _trades(rows)
    if spy is None:
        labels = ["unknown"] * len(trades)
    else:
        close = spy["Close"]
        sma = close.rolling(200, min_periods=200).mean()
        labels = [_regime_of(row["signal_date"], close, sma) for row in trades]
    return {regime: _cohort([row for row, label in zip(trades, labels) if label == regime])
            for regime in ("above", "below", "unknown")}


def clustering(rows) -> dict:
    counts = list(Counter(row["signal_date"] for row in rows).values())
    return {"days": len(counts), "max": max(counts) if counts else 0,
            "p95": float(np.percentile(counts, 95)) if counts else None}


def universe_share(rows, intervals) -> dict:
    """Trades whose ticker sat outside the PIT S&P 500 on the signal day. Unknown (None) without data."""
    trades = _trades(rows)
    if not intervals:
        return {"n": len(trades), "outside_sp500": None, "share": None}
    outside = sum(not is_member(row["signal_date"], intervals.get(row["ticker"], [])) for row in trades)
    return {"n": len(trades), "outside_sp500": outside, "share": outside / len(trades) if trades else None}


def _at_least(value, floor) -> bool:
    return value is not None and value >= floor


def badge_check(trades, *, min_n: int = BADGE_MIN_N) -> dict:
    """The badge floor on the added rows: WR >= 50 over win+loss, ExpR > 0, N >= min_n decided,
    scratches + timeouts <= 50% of closed (time-cap exits are timeouts)."""
    stats = arm_rule.pooled_stats(trades)
    share = stats["scratch_timeout_share"]
    clauses = {"win_rate": _at_least(stats["win_rate"], arm_rule.WR_FLOOR),
               "expectancy_r": stats["expectancy_r"] is not None and stats["expectancy_r"] > 0,
               "n": stats["n"] >= min_n,
               "scratch_timeout_share": share is not None and share <= arm_rule.MAX_SCRATCH_SHARE}
    return {**stats, "min_n": min_n, "clauses": clauses, "verdict": "PASS" if all(clauses.values()) else "FAIL"}


def measure(frames: dict, window, params, *, spy, intervals) -> dict:
    """Every block for one stage, through a Turtle-Soup-only engine (V180-7: the same rows as the
    component arm) under the structural knob."""
    from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
    rows: list[dict] = []
    with apply_knobs({tsr.RESEARCH_KNOB: "structural"}):
        for ticker in sorted(frames):
            engine = StrategyEngine(strategies=(TURTLE_SOUP,))
            list(engine.run_ticker(ticker, frames[ticker], (tsr.HORIZON,), window, params))
            rows += signal_rows(ticker, frames[ticker], engine.turtle_soup_events, window, params=params)
    return {"signal_window": list(window), "signals": len(rows), "trades": len(_trades(rows)),
            "drops": drop_shares(rows), "sweep_depth": sweep_depth_summary(rows),
            "early_stop_share": early_stop_share(rows), "exit_mix": exit_mix(rows),
            "regime": regime_split(rows, spy), "clustering": clustering(rows),
            "universe": universe_share(rows, intervals), "rows": rows}
