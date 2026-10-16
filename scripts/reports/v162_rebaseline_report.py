"""v162 §5: the three-leg re-baseline report for one window.

Each leg is one or more `run_backtest_range.py --trades-jsonl` files, each with
its provenance sidecar (<file>.provenance.json):
  a  yfinance, full history     (BACKTEST_CACHE_DIR = the v162 snapshot)
  b  yfinance from 2016-01-01   (BACKTEST_CACHE_DIR = the truncated snapshot)
  c  the Alpaca SIP store       (--data-source alpaca)
a -> b isolates the shorter warm-up, b -> c the vendor. Every ExpR and win-rate
difference carries its paired week-clustered bootstrap 95% interval. These
numbers describe a data change. They are never a lift and select nothing.

  python scripts/reports/v162_rebaseline_report.py --leg a=A.jsonl --leg b=B.jsonl \\
      --leg c=C.jsonl --window train --out rebaseline.json [--md train.md]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402

LEG_SOURCES = {"a": "yfinance", "b": "yfinance", "c": "alpaca"}
LEG_NAMES = {"a": "yfinance, full history", "b": "yfinance from 2016-01-01",
             "c": "Alpaca SIP store"}
COMPARISONS = (("a", "b", "warm-up"), ("b", "c", "vendor"), ("a", "c", "total"))
WINDOWS = {"train": ("2020-01-01", "2023-12-31"), "fold-train": ("2018-06-01", "2022-12-31")}
CLOSED = ("win", "loss", "scratch", "timeout")
SNAPSHOT_HASHES = "_hashes.json"
TOP_TICKERS = 15


@dataclass(frozen=True)
class Trade:
    ticker: str
    strategy: str
    entry_date: str
    outcome: str
    r_multiple: float


def parse_leg(text: str) -> tuple[str, list[Path]]:
    label, sep, paths = text.partition("=")
    label = label.strip().lower()
    files = [Path(p.strip()) for p in paths.split(",") if p.strip()]
    if not sep or label not in LEG_SOURCES or not files:
        raise argparse.ArgumentTypeError(f"--leg wants a|b|c=PATH[,PATH...], got {text!r}")
    return label, files


def _trade(row: dict, path: Path) -> Trade:
    r = row.get("r_multiple")
    if r is None:
        raise ValueError(f"{path}: closed trade without r_multiple "
                         f"({row.get('ticker')} {row.get('entry_date')})")
    return Trade(str(row["ticker"]), str(row["strategy"]), str(row["entry_date"])[:10],
                 str(row["outcome"]), float(r))


def load_trades(paths: list[Path]) -> list[Trade]:
    """Every closed trade of a leg's files (other outcomes are not trades)."""
    trades: list[Trade] = []
    for path in paths:
        with Path(path).open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        trades += [_trade(row, path) for row in rows if row.get("outcome") in CLOSED]
    return trades


def _sidecar(path: Path) -> dict:
    side = training_data.provenance_path(path)
    if not side.is_file():
        raise ValueError(f"{path}: no provenance sidecar {side.name}; "
                         f"re-run the leg with the v162 runner")
    return json.loads(side.read_text(encoding="utf-8"))


def _snapshot_hash(prov: dict) -> str | None:
    hashes = Path(prov.get("store_dir") or "") / SNAPSHOT_HASHES
    if not hashes.is_file():
        return None
    return json.loads(hashes.read_text(encoding="utf-8")).get("hash")


def load_provenance(label: str, paths: list[Path]) -> dict:
    """The leg's provenance: one for all its files, of the leg's fixed source;
    a yfinance leg must read a hashed snapshot."""
    provs = [_sidecar(Path(p)) for p in paths]
    if any(p != provs[0] for p in provs[1:]):
        raise ValueError(f"leg {label}: its files disagree on provenance")
    prov = dict(provs[0])
    want = LEG_SOURCES[label]
    if prov.get("data_source") != want:
        raise ValueError(f"leg {label} must be {want}, its sidecar says "
                         f"{prov.get('data_source')!r}")
    if want == "yfinance":
        prov["snapshot_hash"] = _snapshot_hash(prov)
        if prov["snapshot_hash"] is None:
            raise ValueError(f"leg {label}: {prov.get('store_dir')} is not a v162 snapshot "
                             f"(no {SNAPSHOT_HASHES})")
    return prov


def _check_window(label: str, trades: list[Trade], window: str) -> None:
    lo, hi = WINDOWS[window]
    outside = [t for t in trades if not lo <= t.entry_date <= hi]
    if outside:
        raise ValueError(f"leg {label}: {len(outside)} trade(s) outside {window} {lo}..{hi}, "
                         f"first {outside[0].entry_date}")


def _evaluated(trades: list[Trade]) -> list[Trade]:
    return [t for t in trades if t.outcome in ("win", "loss")]


def win_rate(trades: list[Trade]) -> float | None:
    """Wins over win+loss, in percent (run_backtest_range.pool)."""
    ev = _evaluated(trades)
    return 100.0 * sum(t.outcome == "win" for t in ev) / len(ev) if ev else None


def expectancy(trades: list[Trade]) -> float | None:
    """Mean R over every closed trade (run_backtest_range.pool)."""
    return float(np.mean([t.r_multiple for t in trades])) if trades else None


def leg_stats(trades: list[Trade]) -> dict:
    ev = _evaluated(trades)
    return {"trades": len(trades), "n_eval": len(ev), "wins": sum(t.outcome == "win" for t in ev),
            "win_rate": win_rate(trades), "expectancy_r": expectancy(trades),
            "tickers": len({t.ticker for t in trades})}


def _delta(metric):
    def statistic(base, comp):
        b, c = metric(base), metric(comp)
        return None if b is None or c is None else c - b
    return statistic


def difference(base: list[Trade], comp: list[Trade], metric, *, n_resamples: int,
               seed: int = stats.WEEK_BOOTSTRAP_SEED) -> dict:
    """comp minus base, with the paired week-clustered bootstrap 95% interval."""
    draws = stats.week_cluster_bootstrap(base, comp, _delta(metric),
                                         n_resamples=n_resamples, seed=seed)
    ci = ([float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))]
          if draws.size else None)
    return {"point": _delta(metric)(base, comp), "ci95": ci, "draws": int(draws.size)}


def ticker_counts(legs: dict[str, list[Trade]]) -> dict[str, dict[str, int]]:
    counts = {label: Counter(t.ticker for t in trades) for label, trades in legs.items()}
    names = sorted(set().union(*counts.values())) if counts else []
    return {name: {label: counts[label][name] for label in sorted(legs)} for name in names}


def build_report(legs: dict[str, list[Trade]], provenance: dict[str, dict], window: str, *,
                 n_resamples: int = stats.WEEK_BOOTSTRAP_RESAMPLES,
                 seed: int = stats.WEEK_BOOTSTRAP_SEED) -> dict:
    for label, trades in legs.items():
        _check_window(label, trades, window)
    comparisons = [{"base": base, "comp": comp, "what": what,
                    "expectancy_r": difference(legs[base], legs[comp], expectancy,
                                               n_resamples=n_resamples, seed=seed),
                    "win_rate": difference(legs[base], legs[comp], win_rate,
                                           n_resamples=n_resamples, seed=seed)}
                   for base, comp, what in COMPARISONS]
    lo, hi = WINDOWS[window]
    return {"window": window, "from": lo, "to": hi, "n_resamples": n_resamples, "seed": seed,
            "legs": {label: {"name": LEG_NAMES[label], **leg_stats(legs[label]),
                             "provenance": provenance[label]} for label in sorted(legs)},
            "comparisons": comparisons, "per_ticker": ticker_counts(legs)}


def _fmt(value, spec: str) -> str:
    return "n/a" if value is None else format(value, spec)


def _ci(diff: dict, spec: str) -> str:
    if diff["ci95"] is None:
        return "n/a"
    return f"{format(diff['ci95'][0], spec)}..{format(diff['ci95'][1], spec)}"


def _sentence(report: dict, cmp: dict) -> str:
    base, comp = report["legs"][cmp["base"]], report["legs"][cmp["comp"]]
    span = f"window {report['window']} {report['from']}..{report['to']}"
    e, w = cmp["expectancy_r"], cmp["win_rate"]
    return (f"- {cmp['what']} ({cmp['base']} -> {cmp['comp']}): ExpR {_fmt(e['point'], '+.3f')} R "
            f"(week-clustered 95% CI {_ci(e, '+.3f')}), {span}, "
            f"N {base['trades']} -> {comp['trades']} trades; win rate "
            f"{_fmt(w['point'], '+.1f')} pp (95% CI {_ci(w, '+.1f')}), {span}, "
            f"N {base['n_eval']} -> {comp['n_eval']} win+loss.")


def _leg_row(label: str, leg: dict) -> str:
    prov = leg["provenance"]
    digest = prov.get("snapshot_hash") or prov.get("manifest_hash") or "-"
    wr = "n/a" if leg["win_rate"] is None else f"{leg['win_rate']:.1f}%"
    return (f"| {label} | {leg['name']} | {leg['trades']} | {leg['n_eval']} | {wr} | "
            f"{_fmt(leg['expectancy_r'], '+.3f')} | {leg['tickers']} | `{str(digest)[:12]}` |")


def _ticker_rows(per_ticker: dict) -> list[str]:
    def change(item):
        name, n = item
        return (-abs(n.get("c", 0) - n.get("a", 0)), name)
    rows = sorted(per_ticker.items(), key=change)[:TOP_TICKERS]
    return [f"| {name} | {n.get('a', 0)} | {n.get('b', 0)} | {n.get('c', 0)} | "
            f"{n.get('c', 0) - n.get('a', 0):+d} |" for name, n in rows]


def render_markdown(report: dict) -> str:
    lines = [f"### Window {report['window']} ({report['from']}..{report['to']})", "",
             "| leg | data | trades | win+loss | win rate | ExpR | tickers traded | input hash |",
             "|---|---|---|---|---|---|---|---|"]
    lines += [_leg_row(label, leg) for label, leg in report["legs"].items()]
    lines += ["", "These differences describe a data change; each is not a lift and selects "
                  "nothing.", ""]
    lines += [_sentence(report, cmp) for cmp in report["comparisons"]]
    lines += ["", f"Largest per-ticker trade-count changes, a -> c (top {TOP_TICKERS}):", "",
              "| ticker | a | b | c | c - a |", "|---|---|---|---|---|"]
    lines += _ticker_rows(report["per_ticker"])
    return "\n".join(lines) + "\n"


def merge_into(out: Path, report: dict) -> None:
    """Add (or replace) this window's block in the JSON at `out`."""
    out = Path(out)
    doc = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    doc.setdefault("windows", {})[report["window"]] = report
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--leg", type=parse_leg, action="append", required=True)
    ap.add_argument("--window", choices=sorted(WINDOWS), required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--md", type=Path, default=None, help="also write the markdown section here")
    ap.add_argument("--resamples", type=int, default=stats.WEEK_BOOTSTRAP_RESAMPLES)
    args = ap.parse_args(argv)
    labels = [label for label, _ in args.leg]
    if sorted(labels) != ["a", "b", "c"]:
        ap.error(f"give --leg a=, b= and c= exactly once each (got {labels})")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        legs = {label: load_trades(paths) for label, paths in args.leg}
        provenance = {label: load_provenance(label, paths) for label, paths in args.leg}
        report = build_report(legs, provenance, args.window, n_resamples=args.resamples)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    merge_into(args.out, report)
    markdown = render_markdown(report)
    if args.md:
        args.md.write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
