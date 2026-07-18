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
