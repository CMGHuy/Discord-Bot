"""Live-trade calibration checks: does the quality score actually predict
win rate (score_deciles), does each tier land in its design band
(tier_calibration), and has a VALIDATED strategy's live win rate drifted
below its out-of-sample number (badge_drift)? Pure functions, no I/O --
callers supply `closed` and (for badge_drift) the already-loaded registry
list."""
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


EXPECTED_BAND = {"A": ">=80", "B": "70-80", "C": "<70"}
MIN_N_FOR_CALIBRATION_VERDICT = 10  # below this, "ok" is None (insufficient data), not False


def _meets_band(win_rate: float, band: str) -> bool:
    if band == ">=80":
        return win_rate >= 80
    if band == "<70":
        return win_rate < 70
    lo, hi = (float(x) for x in band.split("-"))
    return lo <= win_rate <= hi


def tier_calibration(closed: list[dict]) -> list[dict]:
    """One row per design tier (A/B/C, always all three regardless of
    whether any trades exist yet) comparing live win rate against the
    fixed design band that tier is SUPPOSED to land in. `ok` is a
    three-valued signal, not a boolean pass/fail: None means "not enough
    live data to judge yet" (win_rate is None, or n < 10), which is a
    very different message from "judged and it's missing its band"."""
    rows = []
    for tier, band in EXPECTED_BAND.items():
        trades = [t for t in closed if t.get("tier") == tier]
        n = len(trades)
        wr = metrics.win_rate(trades)
        er = metrics.expectancy_r(trades)
        ok = None if (wr is None or n < MIN_N_FOR_CALIBRATION_VERDICT) else _meets_band(wr, band)
        rows.append({"tier": tier, "n": n, "win_rate": wr, "expectancy_r": er,
                     "expected_band": band, "ok": ok})
    return rows


DRIFT_LIVE_N_FLOOR = 20         # below this, live win rate is too noisy to judge decay from
DRIFT_THRESHOLD_POINTS = 10.0   # live WR must fall more than this many points below OOS WR

# Method keywords from chart_style.METHOD_PRIORITY -- used to match trades with
# registry strategies by their indicator type (e.g. "Fib 61.8%" matches "Fibonacci")
_METHOD_KEYWORDS = ["FVG", "Volume Profile", "Trendline", "Fib", "VWAP", "EMA",
                    "Bollinger", "Donchian", "Rolling", "Floor", "Swing", "Pivot"]


def _extract_method(label: str) -> str | None:
    """Extract the base method keyword from a label or strategy name."""
    for keyword in _METHOD_KEYWORDS:
        if label.startswith(keyword):
            return keyword
    return None


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
    from swingbot.core.performance import primary_strategy_label

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

        # Match trades by strategy name or by matching the underlying method
        # (e.g. "Fibonacci" matches trades with target_sources containing "Fib 61.8%")
        strat_method = _extract_method(strat)
        live = []
        for t in closed:
            # Direct match by strategy field
            if t.get("strategy") == strat:
                live.append(t)
                continue
            # Match by primary_strategy_label (handles both strategy field and target_sources)
            if primary_strategy_label(t) == strat:
                live.append(t)
                continue
            # Match by underlying method keyword (for trades with sources but no direct strategy)
            if strat_method:
                sources = t.get("target_sources") or t.get("stop_sources") or []
                if any(_extract_method(src) == strat_method for src in sources):
                    live.append(t)

        live_n = len(live)
        live_wr = metrics.win_rate(live)
        delta = (live_wr - oos_wr) if live_wr is not None else None
        alert = bool(live_n >= DRIFT_LIVE_N_FLOOR and live_wr is not None
                     and live_wr < oos_wr - DRIFT_THRESHOLD_POINTS)

        rows.append({"strategy": strat, "oos_n": oos_n, "oos_wr": oos_wr,
                     "live_n": live_n, "live_wr": live_wr, "delta_wr": delta,
                     "drift_alert": alert})
    return rows
