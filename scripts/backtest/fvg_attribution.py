#!/usr/bin/env python3
"""v128 FVG provenance, attribution and the frozen clause-6 reading (script layer).

Nothing under swingbot/ imports this file, and provenance.code_hash() hashes
swingbot/ only, so editing it never invalidates an arm stamp.

record   replay the BASELINE confluence arm a stamped arms file describes, and for
         every accepted plan store, per frozen candidate, whether it loses the FVG
         vote (signal bar) or the stop/TP1 level it was built on (level-map bar).
report   join one candidate's arms with that record: attribution buckets,
         per-direction split, top-2 horizon share, and the frozen clause-6
         ClauseResult as JSON for validate_component.py --mechanism-json.
context  Stage 1 diagnostic: baseline confluence trades sliced by FVG-in-families.

Run: python scripts/backtest/fvg_attribution.py record --arms logs/v128/pilot-off.json --out logs/v128/provenance-pilot.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import uuid
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot import config  # noqa: E402
from swingbot.core.backtesting import backtest_scenarios as bs  # noqa: E402
from swingbot.core.backtesting.acceptance import ArmTrade, ClauseResult, expectancy_r, win_rate  # noqa: E402
from swingbot.core.backtesting.arms.confluence_engine import ConfluenceEngine  # noqa: E402
from swingbot.core.backtesting.arms.provenance import code_hash  # noqa: E402
from swingbot.core.market import fvg, levels  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402
from swingbot.scan_params import ScanParams  # noqa: E402

#: The frozen v128 candidates: id -> (FVG_LEVELS_MODE, FVG_DISPLACEMENT_ATR_K).
CANDIDATES = {"off": ("off", 1.5), "disp-1.0": ("displacement", 1.0),
              "disp-1.5": ("displacement", 1.5), "disp-2.0": ("displacement", 2.0)}
#: replay_scenarios' target-confluence tolerance (pinned by a source test).
VOTE_TOLERANCE_PCT = 5.0
BUCKETS = ("vote_only", "price_only", "both", "unaffected")
_BUCKET_OF = {(True, False): "vote_only", (False, True): "price_only",
              (True, True): "both", (False, False): "unaffected"}
LOG_DIR = ROOT / "logs"


def knob_delta(cid: str) -> dict:
    """The exact measure_arms --knob delta for a candidate."""
    mode, k = CANDIDATES[cid]
    return {"FVG_LEVELS_MODE": mode} if mode == "off" else {"FVG_LEVELS_MODE": mode, "FVG_DISPLACEMENT_ATR_K": k}


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


def cluster_members(candidates, tolerance_pct: float = levels.CLUSTER_TOLERANCE_PCT) -> list:
    """levels._cluster_levels, but keeping each member's own price: [(mean, [(price, label), ...])]."""
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda c: c[0])
    clusters, bucket = [], [ordered[0]]
    for price, label in ordered[1:]:
        mean = sum(p for p, _ in bucket) / len(bucket)
        if mean > 0 and abs(price - mean) / mean * 100 <= tolerance_pct:
            bucket.append((price, label))
        else:
            clusters.append((sum(p for p, _ in bucket) / len(bucket), bucket))
            bucket = [(price, label)]
    clusters.append((sum(p for p, _ in bucket) / len(bucket), bucket))
    return clusters


def filtered_mids(window, gaps, mode: str, k: float) -> list:
    """Mids of the gaps `mode` drops at this window (all unfilled gaps minus the kept ones)."""
    kept = {id(gap) for gap in fvg.filter_gaps(window, gaps, mode, k)}
    return [gap["mid"] for gap in gaps if id(gap) not in kept]


def _is_filtered(price: float, label: str, mids) -> bool:
    return label.startswith("FVG") and any(_close(price, mid) for mid in mids)


def _families(candidates, target: float) -> list:
    return levels.count_confirming_strategies(None, None, None, target, VOTE_TOLERANCE_PCT,
                                              candidates=candidates)[1]


def vote_lost(candidates, target: float, mids) -> bool:
    """FVG votes for `target` with every gap, and stops voting once the filtered gaps are gone."""
    if not mids or "FVG" not in _families(candidates, target):
        return False
    remaining = [(p, s) for p, s in candidates if not _is_filtered(p, s, mids)]
    return "FVG" not in _families(remaining, target)


def _members_at(clusters, price: float) -> list:
    return next((members for mean, members in clusters if _close(mean, price)), [])


def _touches(members, mids) -> bool:
    return any(_is_filtered(p, s, mids) for p, s in members)


def _snapshot(memo: dict, df, index: int, horizon_key: str) -> dict:
    """Candidates, clusters and detailed gaps at df.iloc[:index + 1], under baseline config."""
    key = (horizon_key, index)
    if key not in memo:
        window = df.iloc[:index + 1]
        price = float(window["Close"].iloc[-1])
        candidates = levels.collect_candidate_levels(window, HORIZONS[horizon_key], price,
                                                     params=ScanParams.from_config())
        memo[key] = {"window": window, "candidates": candidates, "clusters": cluster_members(candidates),
                     "gaps": fvg.find_fair_value_gaps_detailed(window)}
    return memo[key]


def _candidate_flags(record: dict, signal: dict, level: dict) -> dict:
    stop = _members_at(level["clusters"], record["stop_level"])
    tp1 = _members_at(level["clusters"], record["tp1"])
    out = {}
    for cid, (mode, k) in CANDIDATES.items():
        signal_mids = filtered_mids(signal["window"], signal["gaps"], mode, k)
        level_mids = filtered_mids(level["window"], level["gaps"], mode, k)
        out[cid] = {"vote": vote_lost(signal["candidates"], record["take_profit"], signal_mids),
                    "price": bool(level_mids) and (_touches(stop, level_mids) or _touches(tp1, level_mids))}
    return out


@contextmanager
def _recording(log: list, level_bars: dict):
    """Observe replay_scenarios without changing it: which bar each level map was built
    on, and the scenario/plan behind every accepted confluence plan."""
    real_asof, real_build = bs.levels_asof, bs.build_confluence_plan

    def asof(ticker, df, bar_index, horizon_key, cache):
        key = (ticker, horizon_key, bar_index // bs.LEVEL_REFRESH_BARS)
        if key not in cache:
            level_bars[key] = bar_index
        return real_asof(ticker, df, bar_index, horizon_key, cache)

    def build(scenario, window, **kwargs):
        plan = real_build(scenario, window, **kwargs)
        if plan is not None:
            log.append({"signal_index": len(window) - 1, "horizon_key": kwargs["horizon_key"],
                        "take_profit": scenario.take_profit, "stop_level": scenario.stop_loss,
                        "tp1": plan.tp1, "strategy": plan.strategy, "direction": plan.direction})
        return plan

    with mock.patch.object(bs, "levels_asof", asof), mock.patch.object(bs, "build_confluence_plan", build):
        yield


def _provenance_row(ticker, df, record, level_bars, memo) -> dict:
    index, horizon = record["signal_index"], record["horizon_key"]
    level_index = level_bars[(ticker, horizon, index // bs.LEVEL_REFRESH_BARS)]
    signal = _snapshot(memo, df, index, horizon)
    level = _snapshot(memo, df, level_index, horizon)
    key = [ticker, record["strategy"], horizon, str(df.index[index].date()), "confluence", record["direction"]]
    return {"key": key, "fvg_family": "FVG" in _families(signal["candidates"], record["take_profit"]),
            "candidates": _candidate_flags(record, signal, level)}


def record_ticker(ticker, df, horizons, signal_window) -> list:
    """Every accepted baseline confluence plan for one ticker, with its FVG provenance."""
    log, level_bars, memo = [], {}, {}
    with _recording(log, level_bars):
        ConfluenceEngine().run_ticker(ticker, df, tuple(horizons), tuple(signal_window), ScanParams.from_config())
    return [_provenance_row(ticker, df, record, level_bars, memo) for record in log]


def _record_worker(task):
    ticker, horizons, window = task
    from measure_arms import load_frame
    frame = load_frame(ticker)
    if frame is None:
        raise RuntimeError(f"{ticker}: no cached frame")
    return ticker, record_ticker(ticker, frame, horizons, window)


def _progress(path, done, total):
    print(f"  [record] {done}/{total} tickers ({done / total * 100:.0f}%)", flush=True)
    try:
        path.write_text(f"{done}/{total} tickers ({done / total * 100:.0f}%)\n", encoding="utf-8")
    except OSError:
        pass


def _run_tasks(tasks, workers: int, progress_path) -> list:
    rows, done = [], 0
    if workers <= 1:
        results = (_record_worker(task) for task in tasks)
        for _, ticker_rows in results:
            rows.extend(ticker_rows); done += 1; _progress(progress_path, done, len(tasks))
        return rows
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(_record_worker, task) for task in tasks]):
            rows.extend(future.result()[1]); done += 1; _progress(progress_path, done, len(tasks))
    return rows


def _record_refusal(stamp: dict) -> str | None:
    if code_hash() != stamp["engine_hash"]["baseline"]:
        return "refused:code-mismatch -- swingbot/ changed since these arms were produced."
    if config.FVG_LEVELS_MODE != "all":
        return "refused:not-baseline -- the recorder replays the baseline arm; FVG_LEVELS_MODE must be all."
    return None


def cmd_record(args) -> int:
    stamp = json.loads(Path(args.arms).read_text(encoding="utf-8"))["provenance"]
    refusal = _record_refusal(stamp)
    if refusal:
        print(refusal, file=sys.stderr); return 1
    tasks = [(ticker, tuple(stamp["horizons"]), tuple(stamp["signal_window"])) for ticker in stamp["universe"]]
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"fvg_attribution.{uuid.uuid4().hex[:8]}.progress"
    workers = bs._resolve_replay_workers(args.workers)       # the same pool sizing measure_arms uses
    rows = sorted(_run_tasks(tasks, workers, progress), key=lambda row: row["key"])
    progress.unlink(missing_ok=True)
    out = {"arms": str(args.arms), "signal_window": stamp["signal_window"],
           "engine_hash": stamp["engine_hash"]["baseline"], "rows": rows}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out), encoding="utf-8")
    print(f"recorded {len(rows)} baseline confluence plans -> {args.out}")
    return 0


def load_rows(path) -> tuple:
    """(baseline, component) ArmTrades; a walk-forward blob pools its three disjoint test folds."""
    blob = json.loads(Path(path).read_text(encoding="utf-8"))
    pairs = [(blob["baseline"], blob["component"])] if "baseline" in blob else \
        [(fold["baseline"], fold["component"]) for fold in blob["folds"]]
    return ([ArmTrade(**row) for base, _ in pairs for row in base],
            [ArmTrade(**row) for _, comp in pairs for row in comp])


def index_provenance(rows) -> dict:
    out = {}
    for row in rows:
        key = tuple(row["key"])
        if key in out:
            raise ValueError(f"duplicate provenance key {key}")
        out[key] = row
    return out


def _same_r(a, b) -> bool:
    return a == b if a is None or b is None else _close(a, b)


def _strategy_changed(trade, component_by_key) -> bool:
    other = component_by_key.get(trade.key)
    return other is None or other.outcome != trade.outcome or not _same_r(trade.r_multiple, other.r_multiple)


def _flags(trade, provenance, cid, component_by_key) -> tuple:
    if trade.source != "confluence":
        return False, _strategy_changed(trade, component_by_key)
    row = provenance.get(trade.key)
    if row is None:
        raise KeyError(f"no provenance for baseline confluence trade {trade.key} -- re-run record on these arms")
    flags = row["candidates"][cid]
    return flags["vote"], flags["price"]


def buckets_for(baseline, provenance, cid, component) -> list:
    component_by_key = {trade.key: trade for trade in component}
    return [_BUCKET_OF[_flags(trade, provenance, cid, component_by_key)] for trade in baseline]


def mechanism_clause(baseline, buckets) -> ClauseResult:
    """v128 frozen clause 6, on the BASELINE arm: removed = vote or price affected."""
    removed = [t for t, b in zip(baseline, buckets) if b != "unaffected"]
    retained = [t for t, b in zip(baseline, buckets) if b == "unaffected"]
    r_wr, k_wr, r_exp = win_rate(removed), win_rate(retained), expectancy_r(removed)
    if r_wr is None or k_wr is None or r_exp is None:
        return ClauseResult("mechanism", "FAIL", "v128 frozen reading: removed or retained baseline "
                            "population has no decided trades to compare", None, None)
    ok = r_wr < k_wr and r_exp <= 0.0
    return ClauseResult("mechanism", "PASS" if ok else "FAIL",
                        f"v128 frozen reading (baseline arm): removed {len(removed)} WR {r_wr:.2f}% vs "
                        f"retained {len(retained)} WR {k_wr:.2f}%, removed ExpR {r_exp:+.4f}R (must be <= 0)",
                        r_wr, k_wr)


def _stats(trades) -> dict:
    return {"n": len(trades), "win_rate": win_rate(trades), "expectancy_r": expectancy_r(trades)}


def top2_share(trades):
    if not trades:
        return None
    return sum(count for _, count in Counter(t.horizon_key for t in trades).most_common(2)) / len(trades)


def _per_direction(removed, retained) -> dict:
    return {d: {"removed": _stats([t for t in removed if t.direction == d]),
                "retained": _stats([t for t in retained if t.direction == d])}
            for d in ("bullish", "bearish")}


def attribution(baseline, buckets, component) -> dict:
    by_bucket = {name: [t for t, b in zip(baseline, buckets) if b == name] for name in BUCKETS}
    removed = [t for t, b in zip(baseline, buckets) if b != "unaffected"]
    keys = {t.key for t in baseline}
    return {"buckets": {name: _stats(ts) for name, ts in by_bucket.items()}, "removed": _stats(removed),
            "retained": _stats(by_bucket["unaffected"]),
            "per_direction": _per_direction(removed, by_bucket["unaffected"]),
            "top2_horizon_share": top2_share(removed),
            "replacements": sum(1 for t in component if t.key not in keys)}


def _fmt(stats) -> str:
    wr = "n/a" if stats["win_rate"] is None else f"{stats['win_rate']:.2f}%"
    exp = "n/a" if stats["expectancy_r"] is None else f"{stats['expectancy_r']:+.4f}R"
    return f"{stats['n']} | {wr} | {exp}"


def render_attribution(cid, info) -> str:
    lines = [f"### Attribution -- {cid} (diagnostic, never a gate)", "", "| Population | N | WR | ExpR |",
             "|---|---|---|---|"]
    lines += [f"| {name} | {_fmt(info['buckets'][name])} |" for name in BUCKETS]
    lines.append(f"| removed (vote or price) | {_fmt(info['removed'])} |")
    for direction, pair in info["per_direction"].items():
        lines.append(f"| removed, {direction} | {_fmt(pair['removed'])} |")
        lines.append(f"| retained, {direction} | {_fmt(pair['retained'])} |")
    share = info["top2_horizon_share"]
    lines += ["", f"Top-2 horizon share of removed: {'n/a' if share is None else f'{share:.1%}'}"
              + (" -- OVER 80%: the removed population sits in two horizons." if share and share > 0.8 else ""),
              f"Replacement trades (in the candidate arm, not in baseline): {info['replacements']}", ""]
    return "\n".join(lines)


def context_slice(baseline, provenance) -> dict:
    confluence = [t for t in baseline if t.source == "confluence"]
    tagged = [t for t in confluence if provenance[t.key]["fvg_family"]]
    untagged = [t for t in confluence if not provenance[t.key]["fvg_family"]]
    return {"fvg_in_families": _stats(tagged), "fvg_not_in_families": _stats(untagged),
            "strategy_rows_excluded": len(baseline) - len(confluence)}


def _load_pair(args):
    blob = json.loads(Path(args.arms).read_text(encoding="utf-8"))
    provenance = json.loads(Path(args.provenance).read_text(encoding="utf-8"))
    return blob["provenance"], provenance


def _pair_refusal(stamp, provenance) -> str | None:
    if provenance["engine_hash"] != stamp["engine_hash"]["baseline"]:
        return "refused:code-mismatch -- provenance and arms were produced on different swingbot/ code."
    if list(provenance["signal_window"]) != list(stamp["signal_window"]):
        return "refused:window-mismatch -- provenance covers a different signal window."
    return None


def _write(path, text):
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(text, encoding="utf-8")


def cmd_report(args) -> int:
    stamp, provenance = _load_pair(args)
    refusal = _pair_refusal(stamp, provenance)
    if refusal is None and stamp["knob_delta"] != knob_delta(args.candidate):
        refusal = f"refused:candidate-mismatch -- arms carry {stamp['knob_delta']}, not {args.candidate}."
    if refusal:
        print(refusal, file=sys.stderr); return 1
    baseline, component = load_rows(args.arms)
    buckets = buckets_for(baseline, index_provenance(provenance["rows"]), args.candidate, component)
    info, clause = attribution(baseline, buckets, component), mechanism_clause(baseline, buckets)
    text = render_attribution(args.candidate, info) + f"\nFrozen clause 6: **{clause.verdict}** -- {clause.detail}\n"
    print(text)
    _write(args.out_md, text)
    _write(args.out_json, json.dumps({"candidate": args.candidate, "attribution": info, "mechanism": asdict(clause)}, indent=1))
    _write(args.mechanism_json, json.dumps(asdict(clause), indent=1))
    return 0


def cmd_context(args) -> int:
    stamp, provenance = _load_pair(args)
    refusal = _pair_refusal(stamp, provenance)
    if refusal:
        print(refusal, file=sys.stderr); return 1
    baseline, _ = load_rows(args.arms)
    info = context_slice(baseline, index_provenance(provenance["rows"]))
    text = ("### Context slice -- baseline `all` arm, by FVG in confluence families\n\n"
            "**Confounded, diagnostic only:** FVG-tagged setups carry more families by construction. "
            "It explains; it never selects.\n\n| Slice | N | WR | ExpR |\n|---|---|---|---|\n"
            f"| FVG in families | {_fmt(info['fvg_in_families'])} |\n"
            f"| FVG not in families | {_fmt(info['fvg_not_in_families'])} |\n\n"
            f"Strategy-source rows excluded (no confluence families): {info['strategy_rows_excluded']}\n")
    print(text)
    _write(args.out_md, text)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record"); record.add_argument("--arms", required=True); record.add_argument("--out", required=True)
    record.add_argument("--workers", type=int, default=None)
    report = sub.add_parser("report"); report.add_argument("--arms", required=True); report.add_argument("--provenance", required=True)
    report.add_argument("--candidate", required=True, choices=sorted(CANDIDATES))
    for flag in ("--out-md", "--out-json", "--mechanism-json"):
        report.add_argument(flag, default=None)
    context = sub.add_parser("context"); context.add_argument("--arms", required=True); context.add_argument("--provenance", required=True)
    context.add_argument("--out-md", default=None)
    args = parser.parse_args(argv)
    return {"record": cmd_record, "report": cmd_report, "context": cmd_context}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
