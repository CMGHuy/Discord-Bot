"""v190 §5: the describe-only re-baseline of instrument v3.

Legs (each one or more `run_backtest_range.py --trades-jsonl` files with their
`<file>.provenance.json` sidecar):
  A  --instrument v3 (PIT S&P 500 on the PIT Alpaca store)
  B  --instrument v1 --train on the watchlist store (what the funnel runs today)
  C  leg A's trades on the watchlist tickers that are PIT members (no second run:
     v3 refuses --tickers-file, like v2)
Power columns (N, the A/B and C/B ratios, coverage, first counted dates, MDE) are
the only figures a later spec may cite. WR and ExpR are description only. These
numbers describe an instrument change; never a lift; selects nothing.

  python scripts/reports/v190_rebaseline_report.py --leg "A=OUT/leg-A-*.jsonl" \\
      --leg "B=OUT/leg-B-*.jsonl" --watchlist OUT/watchlist.txt \\
      --integrity data/market_data_pit/_integrity.json --json r.json --md r.md
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting import acceptance  # noqa: E402
from swingbot.core.backtesting.acceptance_harvest import mde_expectancy_r  # noqa: E402
from swingbot.core.backtesting.instrument import folds as folds_mod, stats  # noqa: E402
from swingbot.core.backtesting.instrument.contract import resolve  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402
from swingbot.core.marketdata.pit_membership import normalize_symbol  # noqa: E402
from swingbot.core.marketdata.universe import universe_symbols  # noqa: E402

LEG_NAMES = {"A": "v3, PIT S&P 500", "C": "v3, watchlist PIT members", "B": "v1, watchlist"}
LEG_INSTRUMENT = {"A": "v3", "C": "v3", "B": "v1"}
LEG_STORE = {"A": "pit", "B": "watchlist"}
STANDING_LINE = "describes an instrument change; never a lift; selects nothing"
IN_SAMPLE_NOTE = ("Every v3 fold is in-sample or tainted for today's strategies: test years "
                  "2021-2023 lie inside v1 TRAIN, which tuned every live setting, and 2024-2025 "
                  "is v1 VALIDATION. No out-of-fold figure below is out-of-sample, and the 2021 "
                  "fold has a little under four effective training years (the regime gate's "
                  "~320-bar warm-up eats into 2017).")
CONFLUENCE_NOTE = ("Confluence is not measured on legs A and C: run_backtest_range --scenarios "
                   "is refused under every non-v1 instrument (scan replay is unwired there). "
                   "No v1 figure stands in for it.")
COST_NOTE = ("Leg B uses the v1 cost model (zero commission and financing); legs A and C use "
             "v2/v3 fills and costs. WR and ExpR across legs are not like for like.")
TICKER_BOOTSTRAP_SEED = 190   # the ticker design's own seed; WEEK_BOOTSTRAP_SEED is the week design's
LEDGER_ID = "v190-v3-rebaseline"
RECORD = "docs/superpowers/results/2026-10-v190-v3-rebaseline.md"
CLOSED = acceptance.CLOSED
V1, V3 = resolve("v1"), resolve("v3")


@dataclass(frozen=True)
class Trade:
    ticker: str
    strategy: str
    horizon_key: str
    direction: str
    entry_date: str
    exit_date: str | None
    outcome: str
    r_multiple: float


def parse_leg(text: str) -> tuple[str, list[Path]]:
    label, sep, paths = text.partition("=")
    label = label.strip().upper()
    files = []
    for part in (p.strip() for p in paths.split(",")):
        if part:
            files.extend(Path(p) for p in sorted(glob.glob(part))) if "*" in part else files.append(Path(part))
    if not sep or label not in LEG_STORE or not files:
        raise argparse.ArgumentTypeError(
            f"--leg wants A|B=PATH[,PATH...] (leg C is derived from A), got {text!r}")
    return label, files


def _trade(row: dict, path: Path) -> Trade:
    r = row.get("r_multiple")
    if r is None:
        raise ValueError(f"{path}: closed trade without r_multiple "
                         f"({row.get('ticker')} {row.get('entry_date')})")
    return Trade(str(row["ticker"]), str(row["strategy"]), str(row["horizon_key"]),
                 row.get("direction") or "", str(row["entry_date"])[:10],
                 str(row["exit_date"])[:10] if row.get("exit_date") is not None else None,
                 str(row["outcome"]), float(r))


def load_trades(paths: list[Path]) -> list[Trade]:
    trades = []
    for path in paths:
        with Path(path).open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        trades.extend(_trade(row, path) for row in rows if row.get("outcome") in CLOSED)
    return trades


def _sidecar(path: Path) -> dict:
    side = training_data.provenance_path(path)
    if not side.is_file():
        raise ValueError(f"{path}: no provenance sidecar {side}")
    return json.loads(side.read_text(encoding="utf-8"))


def load_provenance(label: str, paths: list[Path]) -> dict:
    provs = [_sidecar(path) for path in paths]
    if not provs:
        raise ValueError(f"leg {label}: no input files")
    if any(p != provs[0] for p in provs[1:]):
        raise ValueError(f"leg {label}: its files disagree on provenance")
    prov = dict(provs[0])
    if prov.get("data_source") != "alpaca":
        raise ValueError(f"leg {label} must read alpaca, its sidecar says {prov.get('data_source')!r}")
    prov.setdefault("store", "watchlist")
    if prov["store"] != LEG_STORE[label]:
        raise ValueError(f"leg {label} must read the {LEG_STORE[label]} store, "
                         f"its sidecar says {prov['store']!r}")
    return prov


def check_window(label: str, trades: list[Trade]) -> None:
    if label == "A":
        lo, hi = V3.research_span
        outside = [t for t in trades if not lo <= t.entry_date <= hi
                   or (t.exit_date is not None and t.exit_date >= V3.holdout_start)]
        reason = "reach the sealed holdout or leave the research span"
    else:
        lo, hi = V1.train_window
        outside = [t for t in trades if not lo <= t.entry_date <= hi]
        reason = f"outside TRAIN {lo}..{hi}"
    if outside:
        first = outside[0]
        raise ValueError(f"leg {label}: {len(outside)} trade(s) {reason}, "
                         f"first {first.ticker} {first.entry_date}")


def leg_c(trades, watchlist, members) -> list[Trade]:
    keep = {normalize_symbol(s) for s in watchlist} & {normalize_symbol(s) for s in members}
    return [t for t in trades if normalize_symbol(t.ticker) in keep]


def by_ticker(trade) -> str:
    return trade.ticker


def by_week(trade) -> str:
    return stats.iso_week_key(trade.entry_date)


def cluster_draws(trades, key, *, n_resamples: int, seed: int) -> np.ndarray:
    """ExpR over cluster-bootstrap draws, vectorised from per-cluster sums. Same
    cluster order (sorted) and the same rng call as acceptance.cluster_bootstrap /
    stats.week_cluster_bootstrap, so the draws equal theirs draw for draw."""
    sums: dict[str, float] = defaultdict(float)
    counts: Counter = Counter()
    for trade in trades:
        sums[key(trade)] += trade.r_multiple
        counts[key(trade)] += 1
    names = sorted(counts)
    if not names:
        return np.array([])
    s = np.array([sums[n] for n in names])
    c = np.array([counts[n] for n in names], dtype=float)
    picks = np.random.default_rng(seed).integers(0, len(names), size=(n_resamples, len(names)))
    return s[picks].sum(axis=1) / c[picks].sum(axis=1)


def _mde_from_draws(draws) -> float | None:
    if draws.size < 2:
        return None
    z = acceptance._Z_ALPHA_ONE_SIDED[acceptance.ALPHA] + acceptance._Z_POWER[0.80]
    return float(z * np.sqrt(2.0) * np.std(draws, ddof=1))


def power_columns(trades, *, seed=TICKER_BOOTSTRAP_SEED,
                  n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES) -> dict:
    if n_resamples < 2:
        raise ValueError("resamples must be at least 2")
    formula = mde_expectancy_r(trades, target_n=len(trades)) if len(trades) > 1 else None
    ticker = cluster_draws(trades, by_ticker, n_resamples=n_resamples, seed=seed)
    week = cluster_draws(trades, by_week, n_resamples=n_resamples, seed=stats.WEEK_BOOTSTRAP_SEED)
    return {"n": len(trades), "tickers": len({t.ticker for t in trades}),
            "weeks": len({by_week(t) for t in trades}), "mde_r_formula": formula,
            "mde_r_ticker": _mde_from_draws(ticker), "mde_r_week": _mde_from_draws(week),
            "ticker_seed": seed, "week_seed": stats.WEEK_BOOTSTRAP_SEED,
            "n_resamples": n_resamples}


def describe(trades) -> dict:
    evaluated = [t for t in trades if t.outcome in ("win", "loss")]
    wins = sum(t.outcome == "win" for t in evaluated)
    return {"n": len(trades), "n_eval": len(evaluated),
            "win_rate": 100.0 * wins / len(evaluated) if evaluated else None,
            "expectancy_r": float(np.mean([t.r_multiple for t in trades])) if trades else None}


def first_counted(trades) -> dict[str, str]:
    first = {}
    for trade in trades:
        first[trade.strategy] = min(first.get(trade.strategy, trade.entry_date), trade.entry_date)
    return dict(sorted(first.items()))


def by_year(trades) -> dict[str, dict]:
    groups = defaultdict(list)
    for trade in trades:
        groups[trade.entry_date[:4]].append(trade)
    return {year: describe(group) for year, group in sorted(groups.items())}


def fold_train(trades, folds) -> list[Trade]:
    if not folds:
        return []
    return folds_mod.split_fold(trades, folds[-1], embargo_days=V3.embargo_days, purge=V3.purge)[0]


def fold_rows(trades, folds) -> list[dict]:
    rows = []
    for fold in folds:
        train, test = folds_mod.split_fold(trades, fold, embargo_days=V3.embargo_days, purge=V3.purge)
        rows.append({"test_year": int(fold.test_start[:4]), "train_n": len(train),
                     "test_n": len(test), "test": describe(test)})
    return rows


def concentration(trades) -> dict:
    counts = Counter(t.horizon_key for t in trades)
    top = sorted(counts, key=lambda name: (-counts[name], name))[:2]
    total_r = sum(t.r_multiple for t in trades)
    top_r = sum(t.r_multiple for t in trades if t.horizon_key in top)
    return {"top_horizons": top,
            "n_share": sum(counts[name] for name in top) / len(trades) if trades else None,
            "r_share": top_r / total_r if trades and total_r else None}


def cells(legs) -> dict:
    occupied = {(label, t.strategy, t.direction, t.horizon_key)
                for label, trades in legs.items() for t in trades}
    sizes = {"strategies": len({c[1] for c in occupied}),
             "directions": len({c[2] for c in occupied}),
             "horizons": len({c[3] for c in occupied}), "legs": len(legs)}
    return {**sizes, "product": int(np.prod(list(sizes.values()))), "non_empty": len(occupied)}


def coverage_summary(doc) -> dict:
    tickers = list(doc["tickers"].values())
    reasons = Counter(t["reason"] for t in tickers if not t["admitted"])
    trims = [t.get("trim") or {} for t in tickers]
    return {"tickers": len(tickers), "admitted": sum(bool(t["admitted"]) for t in tickers),
            "excluded": dict(sorted(reasons.items())), "no_bars": len(doc.get("no_bars") or []),
            "trimmed": sum(bool(t.get("keep_from") or t.get("keep_before")) for t in trims),
            "with_signal_cuts": sum(bool(t.get("signal_cuts")) for t in tickers)}


def _leg_block(label, trades, prov, folds, *, n_resamples, seed) -> dict:
    if label in ("A", "C"):
        population = fold_train(trades, folds)
        title = f"fold-train {V3.research_start}..{folds[-1].train_end} (purged)"
        rows = fold_rows(trades, folds)
    else:
        population, rows = trades, []
        title = f"TRAIN {V1.train_window[0]}..{V1.train_window[1]}"
    return {"name": LEG_NAMES[label], "instrument": LEG_INSTRUMENT[label], "population": title,
            "power": power_columns(population, seed=seed, n_resamples=n_resamples),
            "describe": describe(population), "describe_all": describe(trades),
            "first_counted": first_counted(trades), "by_year": by_year(trades), "folds": rows,
            "concentration": concentration(population),
            "tickers_traded": sorted({t.ticker for t in trades}), "provenance": prov}


def build_report(legs, provenance, *, folds, integrity_sha, integrity_doc,
                 n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES, seed=TICKER_BOOTSTRAP_SEED) -> dict:
    check_window("A", legs["A"])
    check_window("B", legs["B"])
    if provenance["A"].get("integrity_sha256") != integrity_sha:
        raise ValueError("leg A ran on another integrity freeze: "
                         f"sidecar {provenance['A'].get('integrity_sha256')} vs --integrity {integrity_sha}")
    if not folds:
        raise ValueError("v3 report requires anchored folds")
    blocks = {label: _leg_block(label, legs[label], provenance["A" if label == "C" else label],
                               folds, n_resamples=n_resamples, seed=seed) for label in LEG_NAMES}
    n_b = blocks["B"]["power"]["n"]
    return {"standing_line": STANDING_LINE, "in_sample_note": IN_SAMPLE_NOTE,
            "confluence_note": CONFLUENCE_NOTE, "cost_note": COST_NOTE,
            "integrity_sha256": integrity_sha, "coverage": coverage_summary(integrity_doc),
            "cells": cells(legs), "legs": blocks,
            "ratios": {f"{label}/B": blocks[label]["power"]["n"] / n_b if n_b else None
                       for label in ("A", "C")},
            "seeds": {"ticker": seed, "week": stats.WEEK_BOOTSTRAP_SEED}, "n_resamples": n_resamples}


def _fmt(value, fmt="+.3f") -> str:
    return "n/a" if value is None else format(value, fmt)


def _table(headers, rows) -> list[str]:
    return ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |",
            *("| " + " | ".join(str(v) for v in row) + " |" for row in rows), ""]


def _power_markdown(report) -> list[str]:
    rows = []
    for label, block in report["legs"].items():
        p = block["power"]
        rows.append([label, block["population"], p["n"], p["tickers"], p["weeks"],
                     _fmt(p["mde_r_formula"]), f"{_fmt(p['mde_r_ticker'])} (seed {p['ticker_seed']})",
                     f"{_fmt(p['mde_r_week'])} (seed {p['week_seed']})"])
    c = report["cells"]
    return ["## Power (citable)", "", f"Bootstrap resamples: {report['n_resamples']}.", "",
            *_table(["Leg", "Population", "N", "Tickers", "Weeks", "mde_r_formula",
                     "mde_r_ticker", "mde_r_week"], rows),
            "Population N ratios: " + "; ".join(f"{key} = {_fmt(value, '.3f')}"
                                              for key, value in report["ratios"].items()) + ".", "",
            f"cells: {c['strategies']} strategies × {c['directions']} directions × "
            f"{c['horizons']} horizons × {c['legs']} legs = {c['product']} ({c['non_empty']} non-empty)", ""]


def _coverage_markdown(report) -> list[str]:
    c = report["coverage"]
    rows = [[label, strategy, day] for label, block in report["legs"].items()
            for strategy, day in block["first_counted"].items()]
    return ["### Coverage", "", f"Integrity SHA-256: `{report['integrity_sha256']}`.", "",
            f"Tickers: {c['tickers']}; admitted: {c['admitted']}; no bars: {c['no_bars']}; "
            f"trimmed: {c['trimmed']}; with signal cuts: {c['with_signal_cuts']}.", "",
            *_table(["Exclusion reason", "N"], list(c["excluded"].items())),
            "### First counted entry", "", *_table(["Leg", "Strategy", "First entry"], rows)]


def _description_row(label, population, values) -> list:
    return [label, population, values["n"], values["n_eval"],
            _fmt(values["win_rate"], ".1f"), _fmt(values["expectancy_r"])]


def _description_markdown(report) -> list[str]:
    rows, years, folds, concentration_rows = [], [], [], []
    for label, block in report["legs"].items():
        rows.append(_description_row(label, block["population"], block["describe"]))
        rows.append(_description_row(label, "all trades", block["describe_all"]))
        years.extend(_description_row(label, year, values) for year, values in block["by_year"].items())
        folds.extend(_description_row(label, f"{f['test_year']} test", f["test"]) for f in block["folds"])
        c = block["concentration"]
        concentration_rows.append([label, block["population"], ", ".join(c["top_horizons"]) or "n/a",
                                   _fmt(c["n_share"], ".3f"), _fmt(c["r_share"], "+.3f")])
    headers = ["Leg", "Population", "N", "N evaluated", "WR (%)", "ExpR"]
    return ["## WR and ExpR (description only)", "", *_table(headers, rows),
            "### Entry year (all trades)", "", *_table(headers, years),
            "### Fold test side", "", *_table(headers, folds),
            "### Top two horizons", "",
            *_table(["Leg", "Population", "Horizons", "N share", "R share"], concentration_rows)]


def render_markdown(report) -> str:
    folds = [[label, f["test_year"], f["train_n"], f["test_n"]]
             for label in ("A", "C") for f in report["legs"][label]["folds"]]
    lines = ["# v190 re-baseline: instrument v3", "", f"*{report['standing_line']}*", "",
             report["in_sample_note"], "", report["confluence_note"], "", report["cost_note"], "",
             *_table(["Leg", "Instrument / universe"], list(LEG_NAMES.items())),
             *_power_markdown(report), *_coverage_markdown(report),
             "## Folds (legs A and C)", "",
             *_table(["Leg", "Test year", "Effective fold-train N", "Fold-test N"], folds),
             *_description_markdown(report)]
    return "\n".join(lines) + "\n"


def ledger_row(report, *, date) -> dict:
    row = {"id": LEDGER_ID, "date": date,
           "hypothesis": "Instrument v3 re-baseline (PIT S&P 500 on Alpaca bars, research 2017-2025): "
                         + STANDING_LINE,
           "instrument": "v3", "n": report["legs"]["A"]["power"]["n"], "exp_r": None, "p": None,
           "verdict": "DESCRIPTION", "record": RECORD, "data_source": "alpaca"}
    stats.validate_ledger_row(row)
    return row


def read_watchlist(path) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [value.upper() for line in lines if (value := line.split("#", 1)[0].strip())]


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leg", type=parse_leg, action="append", required=True)
    for name in ("watchlist", "integrity", "json", "md"):
        ap.add_argument(f"--{name}", type=Path, required=True)
    ap.add_argument("--resamples", type=int, default=stats.WEEK_BOOTSTRAP_RESAMPLES)
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args(argv)
    if sorted(label for label, _paths in args.leg) != ["A", "B"]:
        ap.error("--leg requires exactly A and B, once each")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        files = dict(args.leg)
        legs = {label: load_trades(paths) for label, paths in files.items()}
        provenance = {label: load_provenance(label, paths) for label, paths in files.items()}
        raw = args.integrity.read_bytes()
        legs["C"] = leg_c(legs["A"], read_watchlist(args.watchlist), universe_symbols("sp500_pit"))
        report = build_report(legs, provenance, folds=folds_mod.anchored_folds(V3),
                              integrity_sha=hashlib.sha256(raw).hexdigest(),
                              integrity_doc=json.loads(raw), n_resamples=args.resamples)
        row = ledger_row(report, date=args.date)
        document = json.dumps(report, indent=1, sort_keys=True, allow_nan=False) + "\n"
        markdown = render_markdown(report)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(document, encoding="utf-8")
        args.md.write_text(markdown, encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(markdown)
    print("LEDGER ROW: " + json.dumps(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
