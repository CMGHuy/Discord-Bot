"""Live-trade calibration checks: does the quality score actually predict
win rate (score_deciles), how does each confidence level's live win rate
compare (level_calibration), and has a VALIDATED strategy's live win rate
drifted below its out-of-sample number (badge_drift)? Pure functions, no
I/O -- callers supply `closed` and (for badge_drift) the already-loaded
registry list.

v32 Task 11: tier_calibration() (A/B/C tier, quality.py's own 0-100
quality_score bands) is retired in favour of level_calibration() (1-5
confidence level, the number that actually gates whether an alert fires).
Unlike tier, level has no design-band-vs-live-win-rate "ok" verdict here:
tier's EXPECTED_BAND came from quality.py's own pre-v32 design; there is no
equivalent measured expected-win-rate-per-level in this codebase (v32's own
VALIDATION run measured legacy vs unified gating, not a per-level band), so
inventing one would be exactly the kind of ungrounded number this repo's
TRAIN-derived-weights discipline exists to prevent. level_calibration()
reports n/win_rate/expectancy per level, same shape as score_deciles(),
without a pass/fail column."""
from __future__ import annotations

from collections import defaultdict

from swingbot.core.analytics import metrics


def _decile_label(score: float) -> str:
    idx = min(int(score) // 10, 9)
    lo = idx * 10
    hi = 100 if idx == 9 else lo + 9
    return f"{lo}-{hi}"


def _decile_floor(label: str) -> int:
    return int(label.split("-")[0])


def score_deciles(closed: list[dict]) -> list[dict]:
    """Bucket closed trades with a known quality_score into 10-wide score
    deciles (0-9 .. 80-89, plus a combined 90-100) and report each
    bucket's win rate/expectancy -- the live counterpart to whatever
    offline backtest calibration produced the score in the first place.
    Trades without a quality_score (legacy rows, or any trade logged
    without a plan in hand) are silently excluded, not bucketed as
    "unknown" -- there is no decile for "no score"."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in closed:
        score = t.get("quality_score")
        if score is None:
            continue
        groups[_decile_label(score)].append(t)

    rows = [
        {"decile": label, "n": len(trades),
         "win_rate": metrics.win_rate(trades), "expectancy_r": metrics.expectancy_r(trades)}
        for label, trades in groups.items()
    ]
    rows.sort(key=lambda r: _decile_floor(r["decile"]))
    return rows


LEVELS = (1, 2, 3, 4, 5)


def level_calibration(closed: list[dict]) -> list[dict]:
    """One row per confidence level (1-5, always all five regardless of
    whether any trades exist yet) reporting live win rate and expectancy --
    the level-based successor to tier_calibration(), with no expected-band
    verdict (see this module's docstring for why)."""
    rows = []
    for level in LEVELS:
        trades = [t for t in closed if t.get("confidence_level") == level]
        n = len(trades)
        wr = metrics.win_rate(trades)
        er = metrics.expectancy_r(trades)
        rows.append({"level": level, "n": n, "win_rate": wr, "expectancy_r": er})
    return rows


DRIFT_LIVE_N_FLOOR = 20         # below this, live win rate is too noisy to judge decay from
DRIFT_THRESHOLD_POINTS = 10.0   # live WR must fall more than this many points below OOS WR


def badge_drift(closed: list[dict], registry_entries: list[dict]) -> list[dict]:
    """Compare each VALIDATED strategy's committed out-of-sample win rate
    against its live win rate so far, flagging real edge decay.

    The alert rule below is PRE-REGISTERED (Global Constraint / design
    decision #5 in the cockpit-v3 plan): live_n >= 20 and
    live_wr < oos_wr - 10.0. This threshold must never be loosened or
    tightened after actually observing live drift -- that would be
    tuning on the very data the rule exists to police. If it needs to
    change, that is a deliberate, documented design decision made BEFORE
    looking at what triggered it, not a reaction to it.

    One row per distinct strategy name across `registry_entries` that has
    at least one VALIDATED-status record -- WEAK-status rows are excluded
    entirely (there is no "decay" concept for a strategy that was never
    validated to begin with), and duplicate strategy names (e.g. one row
    per horizon) collapse to the first VALIDATED occurrence encountered.
    """
    from swingbot.core.market.levels import strategy_family

    rows = []
    seen: set[str] = set()
    for r in registry_entries:
        if r.get("status") != "VALIDATED":
            continue
        strat = r["strategy"]
        if strat in seen:
            continue
        seen.add(strat)

        oos_n = r.get("n", 0)
        oos_wr = r.get("win_rate", 0.0)

        # Match trades by strategy name, or by the canonical family of any
        # source that contributed to the trade's target/stop (e.g. "Fibonacci"
        # matches a trade with target_sources containing "Fib 61.8%").
        live = []
        for t in closed:
            if t.get("strategy") == strat:
                live.append(t)
                continue
            sources = (t.get("target_sources") or []) + (t.get("stop_sources") or [])
            if any(strategy_family(src) == strat for src in sources):
                live.append(t)

        live_n = len(live)
        live_wr = metrics.win_rate(live)
        delta = (live_wr - oos_wr) if live_wr is not None else None
        alert = bool(live_n >= DRIFT_LIVE_N_FLOOR and live_wr is not None
                     and live_wr < oos_wr - DRIFT_THRESHOLD_POINTS)

        rows.append({"strategy": strat, "oos_n": oos_n, "oos_wr": oos_wr,
                     "oos_run_date": r.get("run_date", ""),
                     "live_n": live_n, "live_wr": live_wr, "delta_wr": delta,
                     "drift_alert": alert})
    return rows
