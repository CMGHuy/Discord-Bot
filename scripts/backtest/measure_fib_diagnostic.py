#!/usr/bin/env python3
"""v101 Phase A: can a new mechanism lift Fibonacci to WR >= 50 at N >= 30?

TRAIN only (2020-01-01..2023-12-31); never spends VALIDATION. Measures, per
direction, three mechanisms the closed rows never tried:

  #1 structural-stop filter -- drop plans whose stop the max_risk_pct cap
     pulled in from the swing extreme (real v2 backtest outcomes, a pure
     partition of the baseline trades).
  #2 deeper-ratio stop -- stop one buffer beyond the next deeper fib ratio
     instead of the swing extreme, target re-selected for the new risk.
  #4 reclaim entry -- enter on the first close back beyond the signal bar's
     extreme within RECLAIM_WINDOW bars, same stop, target re-selected.

#2 and #4 change the geometry, so they are compared PAIRED against the same
trades' baseline under one first-touch simulator (simulate_first_touch).
Its absolute numbers are not the backtest's; its deltas are the signal.

Mechanism #3 (horizon split) is closed by v31 and the bearish baseline by v93
(docs/claude/backtest-methodology.md). Per-horizon rows are printed as
description only, and the bearish baseline must reproduce v93 exactly.

Run:
  python scripts/backtest/measure_fib_diagnostic.py \\
      --out docs/superpowers/results/<date>-v101-fib-diagnostic.json \\
      --md  docs/superpowers/results/<date>-v101-fib-diagnostic-table.md
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402
from swingbot.core.planning.params import STRUCTURE_BUFFER_ATR  # noqa: E402
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, capped_planned_loss_pct, planned_loss_pct  # noqa: E402
from swingbot.core.backtesting import arm_rule  # noqa: E402
from swingbot.core.backtesting.backtest_wf import ANCHORED_FOLDS  # noqa: E402
from swingbot.core.planning.targets import fib_target_candidates, select_structural_target  # noqa: E402

from measure_bearish_arms import _unmasked_gates, apply_laggard_rule  # noqa: E402
from run_backtest_range import (  # noqa: E402
    TRAIN, _build_asof_map, _tickers_for_run, _with_context, load_cached, window_trades,
)
from swingbot.core.backtesting.backtest import _plan_series, _trade_plan_at, run_backtest  # noqa: E402
from swingbot.core.market.entry_filters import gate_override  # noqa: E402
from swingbot.core.market.strategy_types import STRATEGY_GATES  # noqa: E402
from swingbot.core.marketdata.universe import data_quality_issues, liquidity_reason  # noqa: E402
from swingbot.core.planning.lifecycle import apply_level_lifecycle  # noqa: E402
from swingbot.core.planning.plan_engine import _safe_atr_value  # noqa: E402
from swingbot.scan_params import ScanParams  # noqa: E402

STRATEGY = "Fibonacci"
ENTRY_RATIOS = (0.382, 0.5, 0.618)              # DEFAULT_PARAMS["Fibonacci"]["ratios"]
RATIO_LADDER = (0.382, 0.5, 0.618, 0.786, 1.0)  # fixed before the run; 1.0 == the swing extreme
RECLAIM_WINDOW = 5                              # fixed before the run
WR_FLOOR = 50.0                                 # badge clause, spec "Success bar"
MIN_N = 30                                      # TRAIN decided-trade floor, spec "Success bar"
MAX_SCRATCH_SHARE = 0.5


def fib_level(swing_high, swing_low, ratio, direction):
    """Retracement level of the impulse being traded: measured down from the
    high for a bullish (up-impulse) pullback, up from the low for bearish."""
    rng = swing_high - swing_low
    return swing_high - ratio * rng if direction == "bullish" else swing_low + ratio * rng


def tested_ratio(close, swing_high, swing_low, direction, ratios=ENTRY_RATIOS):
    return min(ratios, key=lambda r: abs(close - fib_level(swing_high, swing_low, r, direction)))


def structural_stop(swing_high, swing_low, atr_val, direction):
    """The stop _fibonacci_plan builds before the risk cap (builders.py)."""
    buf = STRUCTURE_BUFFER_ATR * atr_val
    return swing_low - buf if direction == "bullish" else swing_high + buf


def deeper_ratio_stop(close, swing_high, swing_low, atr_val, direction):
    ratio = tested_ratio(close, swing_high, swing_low, direction)
    deeper = RATIO_LADDER[RATIO_LADDER.index(ratio) + 1]
    level = fib_level(swing_high, swing_low, deeper, direction)
    buf = STRUCTURE_BUFFER_ATR * atr_val
    return level - buf if direction == "bullish" else level + buf


def cap_distance(entry, horizon_key):
    """Max risk per share, the same arithmetic _fibonacci_plan applies."""
    return entry * (capped_planned_loss_pct(HORIZONS[horizon_key]["max_risk_pct"]) / 100)


def apply_cap(entry, stop, direction, cap):
    if abs(entry - stop) > cap:
        return (entry - cap if direction == "bullish" else entry + cap), True
    return stop, False


def simulate_first_touch(high, low, close, start, entry, stop, target, direction, max_hold):
    """Walk bars start+1 .. start+max_hold. The stop is checked before the
    target on the same bar (the conservative ordering the badge uses).
    No scale-out, no trailing: a paired yardstick, not the v2 engine."""
    risk = abs(entry - stop)
    last = min(start + max_hold, len(close) - 1)
    if last <= start or risk <= 0:
        return "open", None
    bull = direction == "bullish"
    for j in range(start + 1, last + 1):
        if bull:
            if low[j] <= stop:
                return "loss", -1.0
            if high[j] >= target:
                return "win", (target - entry) / risk
        else:
            if high[j] >= stop:
                return "loss", -1.0
            if low[j] <= target:
                return "win", (entry - target) / risk
    r = (close[last] - entry) / risk if bull else (entry - close[last]) / risk
    return "timeout", r


def reclaim_bar(high, low, close, i, direction, window=RECLAIM_WINDOW):
    """First bar j in (i, i+window] closing beyond the signal bar's extreme.
    Reads only bars <= j, so an entry at j's close is knowable at j."""
    for j in range(i + 1, min(i + window, len(close) - 1) + 1):
        if direction == "bullish" and close[j] > high[i]:
            return j
        if direction == "bearish" and close[j] < low[i]:
            return j
    return None


DIRECTIONS = ("bullish", "bearish")
ALL_HZ = tuple(HORIZONS)


def _lifecycle_arm(frame, idx, entry, stop, target, atr_val, direction, horizon_key, candidates):
    """Run one arm's (stop, target) through the same apply_level_lifecycle
    step production applies at plan-build time, so #2/#4 are compared
    against a lifecycle-aware baseline rather than a pre-lifecycle one. A
    no-op (returns the pair unchanged) when there is no target to widen for,
    or when LEVEL_LIFECYCLE_STOPS_ENABLED is off. NO-LOOKAHEAD: this calls
    the same apply_level_lifecycle the backtest calls, which slices df to
    idx before building its own level map (lifecycle.py's
    _lifecycle_levels/classify_levels both slice first) -- reads only bars
    <= idx, same as the caller's own geometry."""
    if target is None:
        return stop, target
    stop, target, _ = apply_level_lifecycle(
        frame, idx, entry=entry, stop=stop, tp1=target, atr_val=atr_val,
        direction=direction, strategy=STRATEGY, horizon_key=horizon_key,
        candidate_levels=candidates)
    return stop, target


def trade_features(frame, i, horizon_key, trade, atr_val, swing_high, swing_low, cap, min_rr, max_rr,
                   stop_mismatch):
    """Everything the three mechanisms need about one baseline trade.

    Geometry (cap flag, ratio, stop distance, re-selected targets) reads bars
    <= i, or <= j for the reclaim entry. Only simulate_first_touch walks
    forward, which is an exit, the same as run_backtest.

    `stop_mismatch` is computed by the caller (_features_for) against
    _trade_plan_at's own (stop, target) -- the full production pipeline
    including apply_level_lifecycle -- and passed in so this function stays
    free of the series plumbing _trade_plan_at needs."""
    h = HORIZONS[horizon_key]
    direction, entry = trade.direction, trade.entry
    is_bull = direction == "bullish"
    high, low, close = frame["High"].values, frame["Low"].values, frame["Close"].values
    hold = h["max_holding_days"]

    struct = structural_stop(swing_high, swing_low, atr_val, direction)
    expected_stop, capped = apply_cap(entry, struct, direction, cap)
    # trade.stop_loss vs the pre-lifecycle stop _fibonacci_plan itself would
    # build: True whenever apply_level_lifecycle widened the stop onto a
    # tested S/R level. Not a diagnostic-geometry bug (see stop_mismatch
    # above) -- this is the mechanism that produces the difference.
    lifecycle_adjusted = abs(trade.stop_loss - expected_stop) > 1e-6 * entry
    # apply_level_lifecycle's own widening ceiling is entry * h["max_risk_pct"]
    # / 100 (lifecycle.py), not run through capped_planned_loss_pct like
    # _fibonacci_plan's cap is -- so a widened stop can land past the hard
    # safety ceiling. Live plan_manager cancels such stop-entry plans at fill.
    # 1e-9 tolerance: a trade sitting exactly at the cap (not lifecycle-
    # widened) can read back a hair over HARD_MAX_PLANNED_LOSS_PCT from
    # entry/cap floating-point round-trip -- far below any real breach.
    over_hard_cap = planned_loss_pct(trade.entry, trade.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT + 1e-9

    base = simulate_first_touch(high, low, close, i, entry, trade.stop_loss,
                                trade.take_profit, direction, hold)

    # #2: stop beyond the next deeper ratio (still risk-capped), new target,
    # then the same lifecycle widening production would apply at this bar.
    candidates_i = fib_target_candidates(frame, i, h, entry)
    deep_stop, _ = apply_cap(entry, deeper_ratio_stop(close[i], swing_high, swing_low, atr_val, direction),
                             direction, cap)
    deep_target = select_structural_target(entry, deep_stop, is_bull, candidates_i, min_rr, max_rr)
    deep_stop, deep_target = _lifecycle_arm(frame, i, entry, deep_stop, deep_target, atr_val,
                                            direction, horizon_key, candidates_i)
    deeper = (simulate_first_touch(high, low, close, i, entry, deep_stop, deep_target, direction, hold)
              if deep_target is not None else ("no_target", None))

    # #4: enter on the reclaim close, same stop, target re-selected at j,
    # then lifecycle-adjusted at j (its own bar, its own tested levels).
    j = reclaim_bar(high, low, close, i, direction)
    if j is None:
        reclaim = ("no_reclaim", None)
    else:
        entry_j = float(close[j])
        still_valid = entry_j > trade.stop_loss if is_bull else entry_j < trade.stop_loss
        candidates_j = fib_target_candidates(frame, j, h, entry_j)
        target_j = (select_structural_target(entry_j, trade.stop_loss, is_bull, candidates_j, min_rr, max_rr)
                    if still_valid else None)
        stop_j, target_j = _lifecycle_arm(frame, j, entry_j, trade.stop_loss, target_j, atr_val,
                                          direction, horizon_key, candidates_j)
        reclaim = (simulate_first_touch(high, low, close, j, entry_j, stop_j, target_j, direction, hold)
                   if target_j is not None else ("no_target", None))

    return {
        "capped": bool(capped),
        "stop_mismatch": bool(stop_mismatch),
        "lifecycle_adjusted": bool(lifecycle_adjusted),
        "over_hard_cap": bool(over_hard_cap),
        "tested_ratio": tested_ratio(close[i], swing_high, swing_low, direction),
        "stop_atr": abs(entry - trade.stop_loss) / atr_val if atr_val else None,
        "base_simple": base,
        "deeper": deeper,
        "reclaim": reclaim,
    }


def simple_stats(pairs):
    closed = [(o, r) for o, r in pairs if o in ("win", "loss", "timeout")]
    decided = [o for o, _ in closed if o in ("win", "loss")]
    wins = sum(o == "win" for o in decided)
    returns = [r for _, r in closed if r is not None]
    return {"n": len(decided),
            "win_rate": wins / len(decided) * 100 if decided else None,
            "expectancy_r": sum(returns) / len(returns) if returns else None,
            "closed": len(closed),
            "dropped": len(pairs) - len(closed)}


def _real(rows):
    """Real v2 backtest outcomes, pooled plus the anchored test-year folds
    the v93 Stage 1 rule reads."""
    trades = [r["trade"] for r in rows]
    pooled = arm_rule.pooled_stats(trades)
    folds = [{"test_year": start[:4],
              "stats": arm_rule.pooled_stats([r["trade"] for r in rows
                                              if start <= r["trade"].entry_date <= end])}
             for _, _, start, end in ANCHORED_FOLDS]
    return {"pooled": pooled, "folds": folds, "verdict": arm_rule.stage1_verdict(pooled, folds)}


def _deeper_stop_summary(rows):
    """Mechanism #2 metrics: base_simple from all rows, arm from deeper stops."""
    return {
        "base_simple": simple_stats([r["features"]["base_simple"] for r in rows]),
        "arm": simple_stats([r["features"]["deeper"] for r in rows]),
    }


def _reclaim_summary(rows):
    """Mechanism #4 metrics: reclaim entry rate and paired stats."""
    reclaimed = [r for r in rows if r["features"]["reclaim"][0] != "no_reclaim"]
    return {
        "reclaim_rate": len(reclaimed) / len(rows) if rows else None,
        "base_simple": simple_stats([r["features"]["base_simple"] for r in reclaimed]),
        "arm": simple_stats([r["features"]["reclaim"] for r in reclaimed]),
    }


def _horizons_summary(rows, structural):
    """Per-horizon baseline and structural-only pooled stats."""
    return {h: {"baseline": arm_rule.pooled_stats([r["trade"] for r in rows if r["horizon_key"] == h]),
                "structural_only": arm_rule.pooled_stats([r["trade"] for r in structural
                                                          if r["horizon_key"] == h])}
            for h in ALL_HZ}


def direction_summary(rows):
    structural = [r for r in rows if not r["features"]["capped"]]
    capped = [r for r in rows if r["features"]["capped"]]
    return {
        "n_rows": len(rows),
        "baseline": _real(rows),
        "cap_rate": len(capped) / len(rows) if rows else None,
        "lifecycle_rate": (sum(r["features"]["lifecycle_adjusted"] for r in rows) / len(rows)) if rows else None,
        "over_hard_cap_rate": (sum(r["features"]["over_hard_cap"] for r in rows) / len(rows)) if rows else None,
        "structural_only": _real(structural),
        "capped_only": _real(capped),
        "deeper_stop": _deeper_stop_summary(rows),
        "reclaim": _reclaim_summary(rows),
        "stop_mismatch": sum(r["features"]["stop_mismatch"] for r in rows),
        "horizons": _horizons_summary(rows, structural),
    }


def _clears(stats):
    return (stats.get("win_rate") is not None and stats["win_rate"] >= WR_FLOOR
            and (stats.get("n") or 0) >= MIN_N)


def phase_a_candidates(summary):
    """The spec's Phase A exit rule: pooled per-direction cells only."""
    out = []
    for d in DIRECTIONS:
        s = summary[d]
        cells = {"#1 structural_only": s["structural_only"]["pooled"],
                 "#2 deeper_stop": s["deeper_stop"]["arm"],
                 "#4 reclaim": s["reclaim"]["arm"]}
        out.extend({"direction": d, "mechanism": k, "stats": v} for k, v in cells.items() if _clears(v))
    return out


def summarise(records):
    out = {d: direction_summary([r for r in records if r["trade"].direction == d]) for d in DIRECTIONS}
    out["candidates"] = phase_a_candidates(out)
    return out


# v93's bearish Fibonacci row (results/2026-09-17-v93-bearish-arms-train.md).
# Same universe filter, same unmasked pass, same laggard rule: must match exactly.
V93_BEARISH = {"before_rs": 226, "after_rs": 107, "n": 89, "win_rate": 21.3, "expectancy_r": -0.255}
# Registry row (run_backtest_range universe, which filters differently): approximate only.
REGISTRY_BULLISH = {"n": 246, "win_rate": 35.4, "expectancy_r": 0.232}


def _stop_mismatch(trade, plan_at):
    """True reproduction check: does the trade carry _trade_plan_at's own
    (stop, target) -- the full production pipeline including
    apply_level_lifecycle -- not just the pre-lifecycle structural geometry.
    None means _trade_plan_at found no qualifying target at this bar, which
    itself is a mismatch against a trade that did happen.

    Tolerance is 1e-6*entry OR 1e-4 absolute, whichever is larger: run_backtest's
    v2 branch stores trade.stop_loss/take_profit as round(x, 4) (backtest.py),
    so a low-priced ticker (e.g. NVDA ~$13) can read back up to 5e-5 off
    _trade_plan_at's unrounded value on a genuine exact match -- 1e-6*entry
    alone (~1.3e-5 there) is tighter than that rounding step and flags false
    mismatches. 1e-4 is 2x the rounding error and still two-plus orders of
    magnitude below any real lifecycle-widening delta observed (dimes to
    dollars, not fractions of a cent)."""
    if plan_at is None:
        return True
    _, plan_stop, plan_target = plan_at
    tol = max(1e-4, 1e-6 * trade.entry)
    return abs(trade.stop_loss - plan_stop) > tol or abs(trade.take_profit - plan_target) > tol


def _features_for(frame, horizon_key, trade, series, rr):
    atr_s, sh_s, sl_s = series
    i = frame.index.get_loc(pd.Timestamp(trade.entry_date))
    atr_val = _safe_atr_value(trade.entry, float(atr_s.iloc[i]))
    plan_at = _trade_plan_at(frame, i, trade.direction, STRATEGY, horizon_key, atr_s, sh_s, sl_s)
    return trade_features(frame, i, horizon_key, trade, atr_val, float(sh_s.iloc[i]), float(sl_s.iloc[i]),
                          cap_distance(trade.entry, horizon_key), *rr, _stop_mismatch(trade, plan_at))


def collect(frames, asof_map, *, horizons=ALL_HZ, run_fn=None):
    """Two passes. Bullish trades come from the LIVE gate, so an unmasked
    bearish trade never blocks a bullish one under one_at_a_time. Bearish
    trades come from v93's unmasked pass plus its laggard rule."""
    run_fn = run_fn or run_backtest
    params = ScanParams.from_config()
    rr = (params.min_risk_reward_ratio, params.max_risk_reward_ratio)
    total = len(frames) * len(horizons) * len(DIRECTIONS)
    done, records, meta = 0, [], {}
    for direction in DIRECTIONS:
        ctx = (gate_override(STRATEGY, _unmasked_gates(STRATEGY)) if direction == "bearish"
               else contextlib.nullcontext())
        rows = []
        with ctx:
            for ticker, frame in sorted(frames.items()):
                for h in horizons:
                    done += 1
                    print(f"[{done}/{total}] {done / total * 100:.0f}% {direction} {ticker} {h}", flush=True)
                    summary = run_fn(ticker, frame, STRATEGY, h, one_at_a_time=True, exit_model="v2",
                                     scale_out=True, tp2_mode="levels", frictions=True,
                                     asof=asof_map.get(ticker))
                    trades = [t for t in window_trades(summary, *TRAIN) if t.direction == direction]
                    if not trades:
                        continue
                    atr_s, sh_s, sl_s, _, _ = _plan_series(frame, STRATEGY, h)
                    rows.extend({"ticker": ticker, "horizon_key": h, "trade": t,
                                 "features": _features_for(frame, h, t, (atr_s, sh_s, sl_s), rr)}
                                for t in trades)
        if direction == "bearish":
            meta["bearish_before_rs"] = len(rows)
            rows = apply_laggard_rule(rows)
            meta["bearish_after_rs"] = len(rows)
        records.extend(rows)
    return records, meta


def reproduction_report(summary, meta):
    bear = summary["bearish"]["baseline"]["pooled"]
    observed = {"before_rs": meta.get("bearish_before_rs"), "after_rs": meta.get("bearish_after_rs"),
                "n": bear.get("n"),
                "win_rate": None if bear.get("win_rate") is None else round(bear["win_rate"], 1),
                "expectancy_r": None if bear.get("expectancy_r") is None else round(bear["expectancy_r"], 3)}
    return {"v93_expected": V93_BEARISH, "v93_observed": observed, "v93_exact": observed == V93_BEARISH,
            "registry_bullish_expected": REGISTRY_BULLISH,
            "bullish_observed": summary["bullish"]["baseline"]["pooled"],
            "note": "bullish uses the v93 universe filter, not run_backtest_range's; expect an approximate match"}


def _fmt(s):
    wr = "—" if s.get("win_rate") is None else f"{s['win_rate']:.1f}%"
    er = "—" if s.get("expectancy_r") is None else f"{s['expectancy_r']:+.3f}"
    return f"{s.get('n', 0)} | {wr} | {er}"


def _render_pooled_table(result):
    lines = ["| Direction | Cell | N (decided) | WR | ExpR |", "|---|---|---:|---:|---:|"]
    for d in DIRECTIONS:
        s = result[d]
        cells = [("baseline (v2)", s["baseline"]["pooled"]),
                 ("#1 structural_only (v2)", s["structural_only"]["pooled"]),
                 ("#1 capped_only (v2)", s["capped_only"]["pooled"]),
                 ("#2 deeper_stop base (simple)", s["deeper_stop"]["base_simple"]),
                 ("#2 deeper_stop arm (simple)", s["deeper_stop"]["arm"]),
                 ("#4 reclaim base (simple)", s["reclaim"]["base_simple"]),
                 ("#4 reclaim arm (simple)", s["reclaim"]["arm"])]
        lines += [f"| {d} | {name} | {_fmt(st)} |" for name, st in cells]
    return lines


def _render_rate_table(result):
    lines = ["", "| Direction | cap rate | lifecycle rate | over-hard-cap rate | reclaim rate | stop mismatches |",
              "|---|---:|---:|---:|---:|---:|"]
    for d in DIRECTIONS:
        s = result[d]
        cap = "—" if s["cap_rate"] is None else f"{s['cap_rate'] * 100:.1f}%"
        lc = "—" if s["lifecycle_rate"] is None else f"{s['lifecycle_rate'] * 100:.1f}%"
        ohc = "—" if s["over_hard_cap_rate"] is None else f"{s['over_hard_cap_rate'] * 100:.1f}%"
        rec = "—" if s["reclaim"]["reclaim_rate"] is None else f"{s['reclaim']['reclaim_rate'] * 100:.1f}%"
        lines.append(f"| {d} | {cap} | {lc} | {ohc} | {rec} | {s['stop_mismatch']} |")
    return lines


def _render_horizon_table(result):
    lines = ["", "Per-horizon rows (description only; #3 is closed):", "",
              "| Direction | Horizon | baseline N / WR / ExpR | #1 structural N / WR / ExpR |",
              "|---|---|---|---|"]
    for d in DIRECTIONS:
        for h, row in result[d]["horizons"].items():
            lines.append(f"| {d} | {h} | {_fmt(row['baseline'])} | {_fmt(row['structural_only'])} |")
    return lines


def _render_reproduction(result):
    rep = result["reproduction"]
    lines = ["", f"**v93 reproduction:** exact={rep['v93_exact']} "
                 f"observed={rep['v93_observed']} expected={rep['v93_expected']}", "",
              "**Candidates** (pooled per-direction cells with WR >= 50 and N >= 30):", ""]
    lines += ([f"- {c['direction']} {c['mechanism']}: {_fmt(c['stats'])}" for c in result["candidates"]]
              or ["- none"])
    return lines


def render_markdown(result):
    lines = _render_pooled_table(result)
    lines += _render_rate_table(result)
    lines += _render_horizon_table(result)
    lines += _render_reproduction(result)
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="v101 Phase A Fibonacci diagnostic (TRAIN only)")
    ap.add_argument("--out", required=True, help="JSON output path")
    ap.add_argument("--md", help="markdown table output path")
    ap.add_argument("--universe")
    ap.add_argument("--tickers", help="comma-separated subset, for smoke runs only")
    args = ap.parse_args(argv)
    started = time.monotonic()
    tickers = args.tickers.split(",") if args.tickers else _tickers_for_run(args.universe)
    frames = {t: _with_context(load_cached(t)) for t in tickers}
    frames = {t: f for t, f in frames.items()
              if f is not None and liquidity_reason(f) is None and not data_quality_issues(f, t)}
    records, meta = collect(frames, _build_asof_map(list(frames), frames, args.universe))
    result = summarise(records)
    result.update(meta=meta, universe_n=len(frames), elapsed_s=round(time.monotonic() - started, 1),
                  reproduction=reproduction_report(result, meta))
    Path(args.out).write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    if args.md:
        Path(args.md).write_text(render_markdown(result), encoding="utf-8")
    print(f"v93_exact={result['reproduction']['v93_exact']} candidates={len(result['candidates'])} -> {args.out}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
