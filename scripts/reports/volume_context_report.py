#!/usr/bin/env python3
"""v121 descriptive report: closed trades bucketed by entry-structure features.

DESCRIPTIVE ONLY. v125 adds plan-provenance, location, leg-phase and zone keys; they must
not be used to choose the structure-break entry spec's grid values (frozen in that spec
before this report exists). It must not be used to choose v122's or v123's grid values --
both grids are frozen in their own specs. ``--source replay`` is TRAIN-only
(2020-01-01..2023-12-31) and refuses any other window. ``--source live`` reads
the production book, which overlaps the 2026 holdout other pre-registrations
(v104) are waiting on: monitoring only, and no inferential statistic is printed.

Production (the real book lives on the Hetzner VM, not this machine)::

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot \
        python scripts/reports/volume_context_report.py --source live"

(needs data/v121_train_quintiles.json from a TRAIN replay run inside that container;
the header labels the book "local TradeLog book" -- local to wherever it runs.)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot.core.backtesting import acceptance  # noqa: E402

TRAIN_START, TRAIN_END = "2020-01-01", "2023-12-31"
DEFAULT_EDGES = ROOT / "data" / "v121_train_quintiles.json"
PROGRESS = ROOT / "logs" / "volume_context_report.progress"
CATEGORICAL = ("structure_state", "structure_aligned", "last_pivot_held", "hh_failed",
               "absorption_bar", "absorption_count_10",
               # v125: plan provenance and leg / zone labels
               "target_capped", "stop_clamped", "leg_phase", "zone_state")
CONTINUOUS = ("swing_high_atr", "swing_low_atr", "vol_trend_10_50", "range_trend_10_50",
              "progress_atr_10", "pullback_vol_ratio", "pullback_depth_frac", "pullback_bars_ratio",
              "impulse_atr_per_bar", "impulse_range_decay",
              # v125: location and zone quality
              "zone_dist_atr", "room_atr", "range_pos", "zone_touches", "zone_departure_atr")
QUINTILES = (0.2, 0.4, 0.6, 0.8)
HEADER = ("v121 volume-in-context report -- DESCRIPTIVE ONLY. Not for choosing v122/v123 "
          "grid values (both frozen in their specs). No inferential statistic is printed.")
V125_NOTE = ("v125 keys (plan provenance, location, leg phase, zone): not to be used to choose "
             "the structure-break entry spec's grid values (frozen in that spec before this report exists).")
PROVENANCE_CELL = ("target_capped", "stop_clamped")
LIVE_WARNING = ("source: local TradeLog book. --source live overlaps the 2026 holdout that open pre-registrations (v104) "
                "are waiting on: monitoring only. Live volume features may come from an in-progress (forming) bar, while "
                "the TRAIN edges are built from completed bars.")


@dataclass(frozen=True)
class ReportRow:
    source: str
    direction: str
    outcome: str
    r_multiple: float | None
    context: dict = field(default_factory=dict)


def window_refusal(start: str, end: str) -> str | None:
    """Replay may only read TRAIN; anything touching 2024-01-01+ is refused."""
    try:
        date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return f"refused: replay window {start}..{end} is not a pair of ISO dates"
    if start < TRAIN_START or end > TRAIN_END or start > end:
        return (f"refused: replay window {start}..{end} is outside TRAIN "
                f"{TRAIN_START}..{TRAIN_END}")
    return None


def quintile_edges(rows, key: str) -> list[float] | None:
    values = [float(v) for v in (row.context.get(key) for row in rows) if v is not None]
    if len(values) < len(QUINTILES) + 1:
        return None
    return [round(float(edge), 6) for edge in np.quantile(values, QUINTILES)]


def all_edges(rows) -> dict:
    return {key: quintile_edges(rows, key) for key in CONTINUOUS}


def bucket_of(value, edges, *, continuous: bool = False) -> str:
    if value is None:
        return "None"
    if edges is None:
        return "no-edges" if continuous else str(value)
    return f"Q{int(np.searchsorted(edges, float(value), side='right')) + 1}"


def bucket_table(rows, key: str, edges) -> list[dict]:
    """One line per (source, direction, bucket): N, win rate, ExpR."""
    groups: dict[tuple, list] = {}
    for row in rows:
        bucket = bucket_of(row.context.get(key), edges, continuous=key in CONTINUOUS)
        groups.setdefault((row.source, row.direction, bucket), []).append(row)
    return [{"feature": key, "source": source, "direction": direction, "bucket": bucket,
             "n": len(members), "win_rate": acceptance.win_rate(members),
             "expectancy_r": acceptance.expectancy_r(members)}
            for (source, direction, bucket), members in sorted(groups.items())]


def _fmt(value, spec: str) -> str:
    return "  n/a" if value is None else format(value, spec)


def _sum_r(members) -> float | None:
    """Total R over closed rows -- the same population acceptance.expectancy_r averages."""
    rs = [row.r_multiple for row in members
          if row.outcome in acceptance.CLOSED and row.r_multiple is not None]
    return round(float(sum(rs)), 4) if rs else None


def provenance_table(rows) -> list[dict]:
    """v125 cross-table: one line per (source, direction, target_capped, stop_clamped)."""
    groups: dict[tuple, list] = {}
    for row in rows:
        cell = tuple(bucket_of(row.context.get(key), None) for key in PROVENANCE_CELL)
        groups.setdefault((row.source, row.direction, *cell), []).append(row)
    return [{"source": source, "direction": direction, "target_capped": capped, "stop_clamped": clamped,
             "n": len(members), "win_rate": acceptance.win_rate(members),
             "expectancy_r": acceptance.expectancy_r(members), "sum_r": _sum_r(members)}
            for (source, direction, capped, clamped), members in sorted(groups.items())]


def _provenance_lines(rows) -> list[str]:
    lines = ["\n== target_capped x stop_clamped =="]
    for line in provenance_table(rows):
        lines.append(f"{line['source']:<10} {line['direction']:<8} capped={line['target_capped']:<5} "
                     f"clamped={line['stop_clamped']:<5} N={line['n']:>5}  "
                     f"WR {_fmt(line['win_rate'], '6.2f')}%  ExpR {_fmt(line['expectancy_r'], '+.4f')}  "
                     f"sumR {_fmt(line['sum_r'], '+.2f')}")
    return lines


def render(rows, edges: dict, *, source: str) -> str:
    lines = [HEADER, V125_NOTE] + ([LIVE_WARNING] if source == "live" else []) + [f"closed trades: {len(rows)}"]
    for key in CATEGORICAL + CONTINUOUS:
        lines.append(f"\n== {key} ==  edges={edges.get(key)}")
        for line in bucket_table(rows, key, edges.get(key) if key in CONTINUOUS else None):
            lines.append(f"{line['source']:<10} {line['direction']:<8} {line['bucket']:<7} "
                         f"N={line['n']:>5}  WR {_fmt(line['win_rate'], '6.2f')}%  "
                         f"ExpR {_fmt(line['expectancy_r'], '+.4f')}")
    lines.extend(_provenance_lines(rows))
    return "\n".join(lines)


def _live_outcome(status: str) -> str:
    return status if status in acceptance.DECIDED else "scratch"


def live_rows(trades) -> list[ReportRow]:
    from swingbot.core.analytics.metrics import r_multiple
    from swingbot.core.analytics.scope import closed_only
    return [ReportRow(source=trade.get("source") or "unknown",
                      direction=trade.get("direction") or "unknown",
                      outcome=_live_outcome(trade.get("status")), r_multiple=r_multiple(trade),
                      context=trade.get("entry_context") or {})
            for trade in closed_only(trades)]


def load_live_trades() -> list[dict]:
    from swingbot.core.tracking.performance import TradeLog
    return TradeLog().get_trades(status=None, limit=None)


def _row(plan, result) -> ReportRow:
    return ReportRow(source=plan.source or "unknown", direction=plan.direction,
                     outcome=result.outcome, r_multiple=result.r_total,
                     context=dict(plan.entry_context or {}))


def confluence_rows(ticker, df, horizons, window, params) -> list[ReportRow]:
    """Mirrors ConfluenceEngine.run_ticker, keeping each plan's stamped snapshot."""
    from swingbot.core.backtesting.arms.confluence_engine import SKIPPED
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    from swingbot.core.planning.plan_engine import simulate_exit
    start, end = window
    out = []
    for horizon_key in horizons:
        for index, plan in replay_scenarios(ticker, df.loc[:end], horizon_key, params=params):
            if str(df.index[index].date()) < start:
                continue
            result = simulate_exit(df, index, plan, scale_out=True)
            if result.outcome not in SKIPPED:
                out.append(_row(plan, result))
    return out


def strategy_rows(ticker, df, horizons, window, params) -> list[ReportRow]:
    """StrategyEngine plans are unstamped; stamp at the SIGNAL bar, as live does."""
    from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
    from swingbot.core.planning.params import stamp_entry_context
    engine, out = StrategyEngine(), []
    for horizon_key in horizons:
        for strategy in engine.strategies:
            for date, plan, result in engine.iter_trades(ticker, df, strategy, horizon_key, window, params):
                index = int(df.index.searchsorted(pd.Timestamp(date)))
                stamp_entry_context(plan, df.iloc[:index + 1], None)
                out.append(_row(plan, result))
    return out


def load_frame(ticker):
    from measure_arms import load_frame as _load
    return _load(ticker)


def cached_universe() -> list[str]:
    from measure_arms import cached_universe as _universe
    return _universe()


def replay_ticker(task) -> list[ReportRow]:
    ticker, horizons, window = task
    from swingbot.scan_params import ScanParams
    df = load_frame(ticker)
    if df is None:
        return []
    params = ScanParams.from_config()
    return (confluence_rows(ticker, df, horizons, window, params)
            + strategy_rows(ticker, df, horizons, window, params))


def _progress(done: int, total: int) -> None:
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(f"{100.0 * done / total:.1f}% ({done}/{total})\n", encoding="utf-8")
    print(f"[{done}/{total}] {100.0 * done / total:.1f}%", flush=True)


def _results(tasks, workers: int):
    if workers <= 1:
        yield from map(replay_ticker, tasks)
        return
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(replay_ticker, tasks)


def replay_all(tickers, horizons, window, *, workers: int = 1) -> list[ReportRow]:
    tasks = [(ticker, tuple(horizons), window) for ticker in tickers]
    rows: list[ReportRow] = []
    for done, chunk in enumerate(_results(tasks, workers), start=1):
        rows.extend(chunk)
        _progress(done, len(tasks))
    PROGRESS.unlink(missing_ok=True)
    return rows


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", choices=("replay", "live"), required=True)
    ap.add_argument("--start", default=TRAIN_START)
    ap.add_argument("--end", default=TRAIN_END)
    ap.add_argument("--tickers", default=None, help="comma list; default every cached ticker")
    ap.add_argument("--edges", default=str(DEFAULT_EDGES),
                    help="TRAIN quintile edges: written by replay, required by live")
    ap.add_argument("--workers", type=int, default=1)
    return ap


def _run_replay(args) -> tuple[list, dict] | None:
    refusal = window_refusal(args.start, args.end)
    if refusal:
        print(refusal)
        return None
    partial = bool(args.tickers) or (args.start, args.end) != (TRAIN_START, TRAIN_END)
    if partial and Path(args.edges).resolve() == DEFAULT_EDGES.resolve():
        print("refused: a --tickers subset or a TRAIN sub-window needs an explicit --edges path other than "
              f"the default {DEFAULT_EDGES.name} (it must not overwrite the full-TRAIN edges)")
        return None
    from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
    tickers = args.tickers.split(",") if args.tickers else cached_universe()
    rows = replay_all(tickers, ALL_HORIZONS, (args.start, args.end), workers=args.workers)
    edges = all_edges(rows)
    path = Path(args.edges)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"window": [args.start, args.end], "edges": edges}, indent=1),
                    encoding="utf-8")
    return rows, edges


def _run_live(args) -> tuple[list, dict] | None:
    path = Path(args.edges)
    if not path.exists():
        print(f"refused: live needs TRAIN quintile edges at {path}; run --source replay first")
        return None
    blob = json.loads(path.read_text(encoding="utf-8"))
    if list(blob.get("window") or ()) != [TRAIN_START, TRAIN_END]:
        print(f"refused: edges at {path} were built from window {blob.get('window')}, "
              f"not the full TRAIN {TRAIN_START}..{TRAIN_END}")
        return None
    return live_rows(load_live_trades()), blob["edges"]


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    result = (_run_replay if args.source == "replay" else _run_live)(args)
    if result is None:
        return 1
    rows, edges = result
    print(render(rows, edges, source=args.source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
