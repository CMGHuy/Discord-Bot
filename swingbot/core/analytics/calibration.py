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
