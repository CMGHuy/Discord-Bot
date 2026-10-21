"""v178 descriptive blocks -- reported, never thresholds (spec § The seven descriptive blocks).

Pure functions over the v178 row contract (one row per entry, the result of
every arm under ``row["arms"][arm_id]``; plan v178 index, "Row contract").
Nothing here gates: the funnel (``giveback_levels_funnel``) decides, these
blocks only describe what an arm did to the runners it managed. Rows may carry
only some arms (the VALIDATION rows hold ``A``, ``B`` and one arm); every
function reads ``arm``, ``A`` and, where named, ``B`` / ``R1.00``.

Readings (plan v178 V178-4): a *runner* is a row whose
``arms[arm]["tp1_index"]`` is not None; a *runner stop exit* is a runner whose
``gap_r`` is not None. Delta-R on a row is
``arms[arm]["r_net"] - arms[against]["r_net"]``.
"""
from __future__ import annotations

from datetime import date

import numpy as np

from swingbot.core.backtesting.arms.windows import ALL_HORIZONS

#: A runner stop exit "shook out" when a new best close followed within this many bars.
SHAKEOUT_BARS = 10
#: A stop exit within this many bars of the best close counts as a quick stop.
QUICK_STOP_BARS = 3
#: A bar whose true range is at least this many ATR marks a runner as a shock (V178-5 fills it).
TR_SHOCK_ATR = 2.0
#: ADX(14) at entry at or above this reads as trend, below as chop (V178-5 fills it).
ADX_TREND_MIN = 20.0

_GIVEN_BACK_KEYS = ("mean_r", "p95_r", "max_r", "mean_dollars", "p95_dollars", "max_dollars")


def _res(row: dict, arm: str) -> dict:
    return row["arms"][arm]


def _runners(rows: list[dict], arm: str) -> list[dict]:
    """Rows on which ``arm`` reached TP1 and managed a runner."""
    return [r for r in rows if _res(r, arm).get("tp1_index") is not None]


def _stop_exits(rows: list[dict], arm: str) -> list[dict]:
    """Runners that ``arm`` closed on its give-back stop (``gap_r`` set)."""
    return [r for r in _runners(rows, arm) if _res(r, arm).get("gap_r") is not None]


def _delta(rows: list[dict], arm: str, against: str = "A") -> dict:
    """Mean paired delta-R of ``arm`` against ``against``; ``delta_r`` None on no rows."""
    diffs = [_res(r, arm)["r_net"] - _res(r, against)["r_net"] for r in rows]
    return {"n": len(diffs), "delta_r": float(np.mean(diffs)) if diffs else None}


def _given_back_r(row: dict, arm: str) -> float:
    """Open runner profit handed back from the best close to the exit, in R of the entry."""
    res = _res(row, arm)
    sign = 1.0 if row["direction"] == "bullish" else -1.0
    move = max(0.0, (res["best"] - res["exit_price"]) * sign)
    return move / row["risk"] * row["runner_fraction"]


def _pcts(values: list[float]) -> dict | None:
    """p10 / p50 / p90 of ``values``; None when empty."""
    if not values:
        return None
    p10, p50, p90 = np.percentile(values, [10, 50, 90])
    return {"n": len(values), "p10": float(p10), "p50": float(p50), "p90": float(p90)}


def _share(count: int, total: int) -> float | None:
    return count / total if total else None


def _book_side(rows: list[dict], side: str, risk_dollars: float) -> dict:
    """Equity at fixed dollar risk for one side, ordered by that side's exit (stable)."""
    ordered = sorted(rows, key=lambda r: (_res(r, side)["exit_date"], r["ticker"]))
    equity = peak = drawdown = 0.0
    for row in ordered:
        equity += _res(row, side)["r_net"] * risk_dollars
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    r_nets = [_res(r, side)["r_net"] for r in ordered]
    return {"n": len(ordered), "exp_r": float(np.mean(r_nets)) if r_nets else None,
            "dollars": equity, "max_drawdown_dollars": drawdown}


def book(rows: list[dict], arm: str, *, risk_dollars: float) -> dict:
    """Block 1: the arm's book and control A's, side by side at fixed dollar risk."""
    return {"arm": _book_side(rows, arm, risk_dollars),
            "A": _book_side(rows, "A", risk_dollars)}


def allowance_share(rows: list[dict], arm: str) -> dict | None:
    """Block 2: the allowance as a share of the best close, over runners; None without one."""
    values = [_res(r, arm)["allowance_pct"] for r in _runners(rows, arm)
              if _res(r, arm)["allowance_pct"] is not None]
    return _pcts(values)


def shakeouts(rows: list[dict], arm: str) -> dict:
    """Block 3: stop exits followed by a new best close, and stops hit soon after the best."""
    stops = _stop_exits(rows, arm)
    new_best = sum(_res(r, arm)["new_best_within_10"] is True for r in stops)
    quick = sum(_res(r, arm)["exit_index"] - _res(r, arm)["best_index"] <= QUICK_STOP_BARS
                for r in stops)
    return {"stop_exits": len(stops), "new_best_10": new_best,
            "new_best_share": _share(new_best, len(stops)),
            "quick_stops": quick, "quick_share": _share(quick, len(stops))}


def _given_back_stats(values: list[float], risk_dollars: float) -> dict:
    if not values:
        return dict.fromkeys(_GIVEN_BACK_KEYS)
    mean_r = float(np.mean(values))
    p95_r = float(np.percentile(values, 95))
    max_r = float(max(values))
    return {"mean_r": mean_r, "p95_r": p95_r, "max_r": max_r,
            "mean_dollars": mean_r * risk_dollars, "p95_dollars": p95_r * risk_dollars,
            "max_dollars": max_r * risk_dollars}


def _gap_stats(stops: list[dict], arm: str) -> dict:
    gaps = [_res(r, arm)["gap_r"] for r in stops]
    gapped = sum(g < 0 for g in gaps)
    return {"gapped": gapped, "gapped_share": _share(gapped, len(gaps)),
            "gap_r_total": float(sum(gaps))}


def given_back(rows: list[dict], arm: str, *, risk_dollars: float) -> dict:
    """Block 4: open runner profit given back, and the gaps through the stop.

    ``gap_r_total`` is already inside ``r_net``; it is reported as the loss it is.
    """
    values = [_given_back_r(r, arm) for r in _runners(rows, arm)]
    return {"n": len(values), **_given_back_stats(values, risk_dollars),
            **_gap_stats(_stop_exits(rows, arm), arm)}


def stop_moves(rows: list[dict], arm: str) -> dict | None:
    """Block 5: how often the give-back stop ratcheted per runner; None without one."""
    moves = [_res(r, arm)["stop_moves"] for r in _runners(rows, arm)
             if _res(r, arm)["stop_moves"] is not None]
    if not moves:
        return None
    return {"n": len(moves), "mean": float(np.mean(moves)), "p50": float(np.median(moves)),
            "max": int(max(moves))}


def _iso_week(day: str) -> str:
    year, week, _ = date.fromisoformat(day).isocalendar()
    return f"{year}-W{week:02d}"


def worst_week(rows: list[dict], arm: str, *, risk_dollars: float) -> dict:
    """Block 6: the ISO week of exit with the most given-back dollars (tie: earliest)."""
    weeks: dict[str, tuple[float, int]] = {}
    for row in _runners(rows, arm):
        key = _iso_week(_res(row, arm)["exit_date"])
        dollars, count = weeks.get(key, (0.0, 0))
        weeks[key] = (dollars + _given_back_r(row, arm) * risk_dollars, count + 1)
    if not weeks:
        return {"week": None, "dollars": 0.0, "runners": 0}
    key = max(sorted(weeks), key=lambda k: weeks[k][0])
    return {"week": key, "dollars": weeks[key][0], "runners": weeks[key][1]}


def shock_split(rows: list[dict], arm: str) -> dict:
    """Block 7: delta-R against A on runners with and without a true-range shock."""
    runners = _runners(rows, arm)
    return {"shock": _delta([r for r in runners if _res(r, arm)["shock"] is True], arm),
            "calm": _delta([r for r in runners if _res(r, arm)["shock"] is False], arm)}


def seven_blocks(rows: list[dict], arm: str, *, risk_dollars: float) -> dict:
    """The spec's seven blocks for one arm, keys ``"1_book"`` .. ``"7_shock"`` in order."""
    return {"1_book": book(rows, arm, risk_dollars=risk_dollars),
            "2_allowance": allowance_share(rows, arm),
            "3_shakeouts": shakeouts(rows, arm),
            "4_given_back": given_back(rows, arm, risk_dollars=risk_dollars),
            "5_stop_moves": stop_moves(rows, arm),
            "6_worst_week": worst_week(rows, arm, risk_dollars=risk_dollars),
            "7_shock": shock_split(rows, arm)}


def per_horizon(rows: list[dict], arm: str) -> dict:
    """Delta-R against A per horizon present, in ``ALL_HORIZONS`` order."""
    present = {r["horizon_key"] for r in rows}
    return {hk: _delta([r for r in rows if r["horizon_key"] == hk], arm)
            for hk in ALL_HORIZONS if hk in present}


def _top2_share(rows: list[dict], arm: str) -> float | None:
    """Share of the total delta-R carried by the two horizons pulling hardest its way."""
    sums: dict[str, float] = {}
    for row in rows:
        diff = _res(row, arm)["r_net"] - _res(row, "A")["r_net"]
        sums[row["horizon_key"]] = sums.get(row["horizon_key"], 0.0) + diff
    total = sum(sums.values())
    if abs(total) < 1e-12:
        return None
    sign = 1.0 if total > 0 else -1.0
    top2 = sorted(sums.values(), key=lambda v: v * sign, reverse=True)[:2]
    return sum(top2) / total


def concentration(rows: list[dict], arm: str) -> dict:
    """Top-2 horizon share of delta-R, and delta-R split long / short."""
    return {"top2_horizon_share": _top2_share(rows, arm),
            "long": _delta([r for r in rows if r["direction"] == "bullish"], arm),
            "short": _delta([r for r in rows if r["direction"] == "bearish"], arm)}


def versus_b(rows: list[dict], arm: str) -> dict:
    """Delta-R of the arm against B, with A against B for reference."""
    return {**_delta(rows, arm, "B"), "a_vs_b": _delta(rows, "A", "B")["delta_r"]}


def _exit_key(row: dict, arm: str) -> tuple:
    return (_res(row, arm)["exit_index"], _res(row, arm)["exit_price"])


def near_duplicate(rows: list[dict], arm: str) -> dict | None:
    """S arms with R1.00 on every row: floor-bound share and exits differing from R1.00."""
    if not arm.startswith("S") or not all("R1.00" in r["arms"] for r in rows):
        return None
    floors = [_res(r, arm)["floor_bound"] for r in _runners(rows, arm)
              if _res(r, arm)["floor_bound"] is not None]
    differs = sum(_exit_key(r, arm) != _exit_key(r, "R1.00") for r in rows)
    return {"floor_bound_share": _share(sum(f is True for f in floors), len(floors)),
            "differs_from_r100": differs}


def regime_split(rows: list[dict], arm: str) -> dict:
    """Delta-R against A on trend and chop entries; entries without a regime are counted."""
    return {"trend": _delta([r for r in rows if r["regime"] == "trend"], arm),
            "chop": _delta([r for r in rows if r["regime"] == "chop"], arm),
            "unknown": sum(r["regime"] is None for r in rows)}


def flips(rows: list[dict], arm: str) -> int:
    """Entries A wins and the arm does not (expected 0; disclosed per spec § Gate clauses)."""
    return sum(_res(r, "A")["outcome"] == "win" and _res(r, arm)["outcome"] != "win"
               for r in rows)


def describe_arm(rows: list[dict], arm: str, *, risk_dollars: float) -> dict:
    """The seven blocks plus the side readings V178-6 writes into the results doc."""
    return {**seven_blocks(rows, arm, risk_dollars=risk_dollars),
            "per_horizon": per_horizon(rows, arm),
            "concentration": concentration(rows, arm),
            "versus_b": versus_b(rows, arm),
            "near_duplicate": near_duplicate(rows, arm),
            "regime": regime_split(rows, arm),
            "flips": flips(rows, arm)}
