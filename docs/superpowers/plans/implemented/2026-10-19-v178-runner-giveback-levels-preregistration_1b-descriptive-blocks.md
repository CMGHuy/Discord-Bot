# v178 — Runner give-back levels: Implementation Plan, part 1b (descriptive blocks)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V178-4:" -A 400 <this file>`.

**Spec:** [2026-10-19-v178-runner-giveback-levels-preregistration-design.md](../specs/2026-10-19-v178-runner-giveback-levels-preregistration-design.md)
**Index:** [2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md](2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md) — Goal, Architecture, `## Global Constraints`, the row / funnel / blocks / simulator contracts, `## Parallelisation` and the task ledger live there and bind every task below.

**Tasks in this part:** V178-4 (descriptive blocks).

**Where to work:** every task here runs in the worktree
`.claude/worktrees/2026-10-19-v178-runner-giveback-levels-preregistration`
(branch `2026-10-19-v178-runner-giveback-levels-preregistration`, created in
V178-1 Step 1). All paths below are relative to that worktree's root; run every
command from it (absolute path, never `cd` in a Bash call that also runs a
hook-checked command). Commits go on the worktree branch, one scoped commit per
task.

# Phase 2 (cont.) — Descriptive blocks

### Task V178-4: Descriptive blocks

**Model:** sonnet — pure, well-specified statistics over the row contract; reported, never gating

**Files:**
- Create: `swingbot/core/backtesting/giveback_levels_blocks.py`
- Create: `tests/backtesting/test_giveback_levels_blocks.py` (suite `backtesting-a-k` by its `test_g*` name; no manifest edit)

**Interfaces:**
- Consumes: the index's row contract only (no import of `giveback_levels_funnel`); `ALL_HORIZONS` (`swingbot/core/backtesting/arms/windows.py:15`, `('2w', '4w', '2m', '3m', ..., '9m')`). Rows may carry only some arms (V178-6's validation rows hold `A`, `B` and one arm): each function reads `arm`, `A` and, where named, `B` / `R1.00`.
- Produces (blocks contract in the index, consumed by V178-6): the four constants and the fifteen functions with the exact signatures listed there; `describe_arm` returns `seven_blocks(...)` plus keys `per_horizon`, `concentration`, `versus_b`, `near_duplicate`, `regime`, `flips` (V178-6 drops `regime` for non-regime arms).

**Readings fixed here (spec § The seven descriptive blocks, Near-duplicate arms, Counting):** a *runner* is a row whose `arms[arm]["tp1_index"]` is not None; a *runner stop exit* is a runner whose `gap_r` is not None. ΔR on a row is `arms[arm]["r_net"] - arms[against]["r_net"]`. Given-back R per runner = `max(0, (best - exit_price) * sign) / risk * runner_fraction` (sign +1 bullish, −1 bearish); dollars = R × `risk_dollars`. "Outcome differs from R k = 1.0" is read as the exit `(exit_index, exit_price)` differing, since a post-TP1 rule cannot change `outcome`. Concentration's top-2 = the two horizons with the largest summed ΔR in the total's direction, share = their sum / the total (None when `abs(total) < 1e-12`). The worst week is the ISO week (`YYYY-Www` of `exit_date`) with the largest summed give-back dollars.

- [ ] **Step 1: Write the failing tests** — create `tests/backtesting/test_giveback_levels_blocks.py`:

```python
"""v178 V178-4: the seven descriptive blocks and the side readings on hand-built rows."""
import pytest

from swingbot.core.backtesting import giveback_levels_blocks as bl


def _res(r, *, runner=True, exit_index=20, exit_price=110.0, best=112.0, best_index=18,
         stop=True, gap=0.0, new_best=False, shock=False, moves=3, allowance=0.02,
         floor=None, outcome="win", exit_date="2021-03-05"):
    run = dict(tp1_index=10, best=best, best_index=best_index, allowance_pct=allowance,
               floor_bound=floor, stop_moves=moves, shock=shock,
               gap_r=gap if stop else None, new_best_within_10=new_best if stop else None)
    return {"outcome": outcome, "r_net": r, "exit_index": exit_index, "exit_price": exit_price,
            "exit_date": exit_date, **(run if runner else dict.fromkeys(run))}


def _row(arms, *, hk="4w", direction="bullish", regime="trend", risk=5.0):
    return {"ticker": "AAA", "horizon_key": hk, "direction": direction, "regime": regime,
            "risk": risk, "runner_fraction": 0.5, "arms": arms}


LOSS = dict(runner=False, outcome="loss")
ROWS = [
    _row({"A": _res(1.0, exit_price=108.0), "B": _res(0.8, runner=False),
          "R1.00": _res(1.2, new_best=True, best_index=19, shock=True),
          "S0.33": _res(1.2, floor=True)}),
    _row({arm: _res(-1.0, **LOSS) for arm in ("A", "B", "R1.00", "S0.33")},
         hk="3m", regime="chop"),
    _row({"A": _res(0.5, exit_index=30, exit_date="2021-03-12"), "B": _res(0.6, runner=False),
          "R1.00": _res(0.3, exit_index=25, exit_price=105.0, gap=-0.1, best_index=10,
                        exit_date="2021-03-12"),
          "S0.33": _res(0.3, exit_index=26, exit_price=105.0, floor=False)},
         hk="6m", direction="bearish", regime=None),
]


def test_constants_are_frozen():
    assert (bl.SHAKEOUT_BARS, bl.QUICK_STOP_BARS, bl.TR_SHOCK_ATR, bl.ADX_TREND_MIN) == (10, 3, 2.0, 20.0)


def test_book_sets_arm_and_control_side_by_side_at_fixed_risk():
    out = bl.book(ROWS, "R1.00", risk_dollars=100.0)
    assert out["arm"]["n"] == out["A"]["n"] == 3
    assert out["arm"]["dollars"] == pytest.approx(50.0) and out["A"]["dollars"] == pytest.approx(50.0)
    assert out["arm"]["max_drawdown_dollars"] == pytest.approx(100.0)   # +120, then -100


def test_allowance_share_percentiles_and_none_without_runners():
    out = bl.allowance_share(ROWS, "R1.00")
    assert out["n"] == 2 and out["p10"] == out["p50"] == out["p90"] == pytest.approx(0.02)
    assert bl.allowance_share(ROWS, "B") is None


def test_shakeouts_count_new_best_and_quick_stops():
    out = bl.shakeouts(ROWS, "R1.00")
    assert (out["stop_exits"], out["new_best_10"], out["quick_stops"]) == (2, 1, 1)
    assert out["new_best_share"] == pytest.approx(0.5)


def test_given_back_signs_by_direction_and_counts_gaps():
    out = bl.given_back(ROWS, "R1.00", risk_dollars=100.0)
    # bullish: (112 - 110) / 5 * 0.5 = 0.2R; bearish: max(0, (112 - 105) * -1) = 0
    assert out["max_r"] == pytest.approx(0.2) and out["max_dollars"] == pytest.approx(20.0)
    assert out["gapped"] == 1 and out["gap_r_total"] == pytest.approx(-0.1)


def test_stop_moves_and_worst_week():
    assert bl.stop_moves(ROWS, "R1.00")["max"] == 3
    assert bl.stop_moves(ROWS, "B") is None
    assert bl.worst_week(ROWS, "R1.00", risk_dollars=100.0) == {
        "week": "2021-W09", "dollars": pytest.approx(20.0), "runners": 1}


def test_shock_split_and_regime_split_pair_against_control_a():
    out = bl.shock_split(ROWS, "R1.00")
    assert out["shock"] == {"n": 1, "delta_r": pytest.approx(0.2)}
    assert out["calm"] == {"n": 1, "delta_r": pytest.approx(-0.2)}
    reg = bl.regime_split(ROWS, "R1.00")
    assert reg["trend"]["delta_r"] == pytest.approx(0.2) and reg["chop"]["n"] == 1
    assert reg["unknown"] == 1


def test_horizon_concentration_versus_b_and_flips():
    assert list(bl.per_horizon(ROWS, "R1.00")) == ["4w", "3m", "6m"]     # ALL_HORIZONS order
    conc = bl.concentration(ROWS, "R1.00")
    assert conc["top2_horizon_share"] is None                           # total ΔR is ~0
    assert conc["long"]["n"] == 2 and conc["short"]["delta_r"] == pytest.approx(-0.2)
    assert bl.versus_b(ROWS, "R1.00")["delta_r"] == pytest.approx((0.4 + 0.0 - 0.3) / 3)
    assert bl.flips(ROWS, "R1.00") == 0


def test_near_duplicate_only_for_s_arms_with_r100_present():
    assert bl.near_duplicate(ROWS, "S0.33") == {"floor_bound_share": pytest.approx(0.5),
                                                "differs_from_r100": 1}
    assert bl.near_duplicate(ROWS, "R1.00") is None
    no_r = [{**r, "arms": {k: r["arms"][k] for k in ("A", "S0.33")}} for r in ROWS]
    assert bl.near_duplicate(no_r, "S0.33") is None                    # validation rows


def test_describe_arm_carries_seven_blocks_and_side_readings():
    out = bl.describe_arm(ROWS, "S0.33", risk_dollars=100.0)
    assert list(out)[:7] == ["1_book", "2_allowance", "3_shakeouts", "4_given_back",
                             "5_stop_moves", "6_worst_week", "7_shock"]
    assert {"per_horizon", "concentration", "versus_b", "near_duplicate", "regime", "flips"} <= set(out)


def test_top2_share_and_empty_blocks():
    rows = [_row({"A": _res(0.0), "R1.00": _res(1.0)}, hk="2w"),
            _row({"A": _res(0.0), "R1.00": _res(0.5)}, hk="4w"),
            _row({"A": _res(0.0), "R1.00": _res(-0.5)}, hk="3m")]
    assert bl.concentration(rows, "R1.00")["top2_horizon_share"] == pytest.approx(1.5)
    none = [_row({"A": _res(0.0, **LOSS), "B": _res(0.0, **LOSS)})]
    assert bl.worst_week(none, "B", risk_dollars=1.0) == {"week": None, "dollars": 0.0, "runners": 0}
    assert bl.given_back(none, "B", risk_dollars=1.0)["max_r"] is None
```

The last test pins two readings the shared fixture cannot reach: the top-2
share when the total ΔR is not ~0 (horizons 2w +1.0, 4w +0.5, 3m −0.5, total
+1.0 → the two largest in the total's direction sum to 1.5 → share 1.5), and
the empty-runner returns of blocks 4 and 6.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_giveback_levels_blocks.py`
Expected: FAIL — `ImportError: cannot import name 'giveback_levels_blocks' from 'swingbot.core.backtesting'`.

- [ ] **Step 3: Write the module** — create `swingbot/core/backtesting/giveback_levels_blocks.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_giveback_levels_blocks.py`
Expected: PASS, `11 passed`, `0 failed`.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: no finding (every function above is under 10; the empty-row branches live in `_given_back_stats`, `_gap_stats` and `_top2_share` to keep `given_back` and `concentration` flat).

- [ ] **Step 6: Commit** (on the worktree branch)

```bash
git add swingbot/core/backtesting/giveback_levels_blocks.py tests/backtesting/test_giveback_levels_blocks.py
git commit -m "feat(v178): give-back levels descriptive blocks

The seven pre-registered blocks per arm (book at fixed risk, allowance share,
shake-outs, open profit given back with gaps, stop moves, worst week, shock
split) plus per-horizon, concentration, versus-B, near-duplicate, regime split
and win flips. Reported, never thresholds.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
