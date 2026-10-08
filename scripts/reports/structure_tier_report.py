#!/usr/bin/env python3
"""v130 descriptive report: does structure read off MAJOR swings separate closed trades better than k=3 structure?

DESCRIPTIVE ONLY. Its one verdict decides whether a follow-on expectancy spec
is written; it must never pick that spec's thresholds. ``--source replay`` is
TRAIN-only (2020-01-01..2023-12-31) and refuses any other window.
``--source live`` reads the production book, which overlaps the 2026 holdout:
monitoring only -- no verdict and no inferential statistic is printed.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "reports")]

import volume_context_report as vcr  # noqa: E402  (v121's bucketing helpers: imported, not copied)

THIN_N = 30
DEFAULT_EDGES = ROOT / "data" / "v130_train_quintiles.json"
ALIGN_KEYS = ("structure_aligned", "structure_aligned_major")       # k=3 (v121) vs major (v130)
ALIGN_BUCKETS = ("True", "False", "None")
EVENT_AGES = ((5, "0-5"), (20, "6-20"))                              # anything older is "21+"
REACTION_KEY = {"bullish": "last_sl_reaction_atr", "bearish": "last_sh_reaction_atr"}
MORE, NOT_MORE = "major tier more informative", "not more informative"
HEADER = ("v130 structure-tier report -- DESCRIPTIVE ONLY. The verdict decides whether a follow-on "
          "spec is written, never its thresholds. No inferential statistic is printed.")


def event_bucket(context: dict) -> str | None:
    """``struct_event_last`` x the fixed age buckets 0-5 / 6-20 / 21+."""
    kind, age = context.get("struct_event_last"), context.get("struct_event_bars_ago")
    if kind is None or age is None:
        return None
    label = next((name for limit, name in EVENT_AGES if age <= limit), "21+")
    return f"{kind} {label}"


def derived(rows) -> list:
    """Rows with the two report-only keys added: ``event_bucket`` and the
    direction's own ``reaction_atr`` (swing low for bullish, swing high for bearish)."""
    return [replace(row, context={**row.context, "event_bucket": event_bucket(row.context),
                                  "reaction_atr": row.context.get(REACTION_KEY.get(row.direction, ""))})
            for row in rows]


def reaction_edges(rows) -> dict:
    """TRAIN quintile edges of ``reaction_atr``, one set per trade direction."""
    return {direction: vcr.quintile_edges([row for row in rows if row.direction == direction], "reaction_atr")
            for direction in REACTION_KEY}


def _stats(line: dict | None) -> str:
    """N, then win rate and ExpR -- or ``thin`` (no ExpR) under N = 30."""
    count = line["n"] if line else 0
    if count < THIN_N:
        return f"N={count:>5}  thin"
    return (f"N={count:>5}  WR {vcr._fmt(line['win_rate'], '6.2f')}%  "
            f"ExpR {vcr._fmt(line['expectancy_r'], '+.4f')}")


def table_lines(rows, key: str, edges=None) -> list[str]:
    return [f"{line['source']:<10} {line['direction']:<8} {line['bucket']:<18} {_stats(line)}"
            for line in vcr.bucket_table(rows, key, edges)]


def alignment_lines(rows) -> list[str]:
    """Table 1: per (source, direction, bucket), the k=3 cell beside the major cell."""
    tables = [{(line["source"], line["direction"], line["bucket"]): line
               for line in vcr.bucket_table(rows, key, None)} for key in ALIGN_KEYS]
    groups = sorted({key[:2] for table in tables for key in table})
    return [f"{source:<10} {direction:<8} {bucket:<6} k3 {_stats(tables[0].get((source, direction, bucket))):<42}"
            f"| major {_stats(tables[1].get((source, direction, bucket)))}"
            for source, direction in groups for bucket in ALIGN_BUCKETS]


def spread(rows, key: str) -> dict:
    """ExpR(aligned) - ExpR(not aligned) and the N of each bucket."""
    aligned = [row for row in rows if row.context.get(key) is True]
    opposed = [row for row in rows if row.context.get(key) is False]
    thin = min(len(aligned), len(opposed)) < THIN_N
    exp_a, exp_o = vcr.acceptance.expectancy_r(aligned), vcr.acceptance.expectancy_r(opposed)
    value = None if thin or exp_a is None or exp_o is None else round(exp_a - exp_o, 6)
    return {"n_aligned": len(aligned), "n_not_aligned": len(opposed), "thin": thin, "spread": value}


def _same_sign(bullish: dict, bearish: dict) -> bool:
    if bearish["thin"]:
        return True
    if bullish["spread"] is None or bearish["spread"] is None:
        return False
    return bool(np.sign(bullish["spread"]) == np.sign(bearish["spread"]))


def verdict(rows) -> dict:
    """The pre-registered verdict on the confluence-sourced population."""
    confluence = [row for row in rows if row.source == "confluence"]
    k3, major = (spread(confluence, key) for key in ALIGN_KEYS)
    by_direction = {direction: spread([row for row in confluence if row.direction == direction], ALIGN_KEYS[1])
                    for direction in ("bullish", "bearish")}
    conditions = {
        "all_four_buckets_n30": not (k3["thin"] or major["thin"]),
        "major_spread_larger": (k3["spread"] is not None and major["spread"] is not None
                                and major["spread"] > k3["spread"]),
        "same_sign_both_directions": _same_sign(by_direction["bullish"], by_direction["bearish"]),
    }
    return {"verdict": MORE if all(conditions.values()) else NOT_MORE, "conditions": conditions,
            "k3": k3, "major": major, "major_by_direction": by_direction}


def census_of(df, window) -> tuple[int, list[int]]:
    """Confirmed k=3 pivots formed inside ``window`` and, for those that became
    major, the bars from pivot to major bar. Reads no bar after ``window``'s end."""
    from swingbot.core.market.structure import pivot_tiers
    start, end = window
    frame = df.loc[:end]
    tiers = pivot_tiers(frame)
    dates = frame.index[tiers["pos"].to_numpy(int)]
    inside = tiers[np.asarray(dates >= start)]
    major = inside[inside["major_pos"].notna()]
    return len(inside), (major["major_pos"] - major["pos"]).astype(int).tolist()


def census_all(tickers, window) -> dict:
    pivots, lags = 0, []
    for ticker in tickers:
        df = vcr.load_frame(ticker)
        if df is None or df.empty:
            continue
        count, ticker_lags = census_of(df, window)
        pivots, lags = pivots + count, lags + ticker_lags
    return {"pivots": pivots, "major": len(lags),
            "major_share_pct": round(100.0 * len(lags) / pivots, 2) if pivots else None,
            "median_bars_to_major": float(np.median(lags)) if lags else None}


def _verdict_lines(result: dict) -> list[str]:
    lines = [f"\n== VERDICT (confluence-sourced, pre-registered): {result['verdict']} =="]
    lines += [f"{name}: {'PASS' if passed else 'FAIL'}" for name, passed in result["conditions"].items()]
    lines += [f"spread k3    {result['k3']}", f"spread major {result['major']}"]
    lines += [f"spread major {direction} {value}" for direction, value in result["major_by_direction"].items()]
    return lines


def render(rows, edges: dict, census: dict | None, *, source: str) -> str:
    rows = derived(rows)
    lines = [HEADER] + ([vcr.LIVE_WARNING] if source == "live" else []) + [f"closed trades: {len(rows)}"]
    lines += ["\n== Table 1: structure_aligned (k=3) vs structure_aligned_major =="] + alignment_lines(rows)
    lines += ["\n== Table 2: struct_event_last x bars ago =="] + table_lines(rows, "event_bucket")
    for direction, key in REACTION_KEY.items():
        lines.append(f"\n== Table 3: {key} ({direction} trades)  edges={edges.get(direction)} ==")
        lines += table_lines([row for row in rows if row.direction == direction], "reaction_atr",
                             edges.get(direction))
    if census is not None:
        lines += ["\n== Table 4: tier census (daily frames; identical for every horizon) ==", str(census)]
    if source == "replay":
        lines += _verdict_lines(verdict(rows))
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", choices=("replay", "live"), required=True)
    ap.add_argument("--start", default=vcr.TRAIN_START)
    ap.add_argument("--end", default=vcr.TRAIN_END)
    ap.add_argument("--tickers", default=None, help="comma list; default every cached ticker")
    ap.add_argument("--edges", default=str(DEFAULT_EDGES),
                    help="TRAIN reaction quintile edges: written by replay, required by live")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--json", default=None, help="replay only: also write verdict + census here")
    return ap


def _run_replay(args):
    refusal = vcr.window_refusal(args.start, args.end)
    if not refusal and args.json and Path(args.json).exists():
        refusal = f"refused: {args.json} already holds the recorded verdict; the measurement runs once"
    if refusal:
        print(refusal)
        return None
    from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
    window = (args.start, args.end)
    tickers = args.tickers.split(",") if args.tickers else vcr.cached_universe()
    rows = vcr.replay_all(tickers, ALL_HORIZONS, window, workers=args.workers)
    edges, census = reaction_edges(derived(rows)), census_all(tickers, window)
    path = Path(args.edges)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"window": list(window), "edges": edges}, indent=1), encoding="utf-8")
    if args.json:
        blob = {"window": list(window), "closed": len(rows), "census": census, **verdict(derived(rows))}
        Path(args.json).write_text(json.dumps(blob, indent=1), encoding="utf-8")
    return rows, edges, census


def _run_live(args):
    path = Path(args.edges)
    if not path.exists():
        print(f"refused: live needs TRAIN reaction edges at {path}; run --source replay first")
        return None
    edges = json.loads(path.read_text(encoding="utf-8"))["edges"]
    return vcr.live_rows(vcr.load_live_trades()), edges, None


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    result = (_run_replay if args.source == "replay" else _run_live)(args)
    if result is None:
        return 1
    rows, edges, census = result
    print(render(rows, edges, census, source=args.source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

