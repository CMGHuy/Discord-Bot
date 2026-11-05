#!/usr/bin/env python3
"""v192: the gap-reclaim report -- every spec § Reporting number for one stamped arm pair.

    python scripts/reports/gap_reclaim_report.py --arms <arms.json> [--basis <basis-arms.json>]
        --out-json <path> --out-md <path> [--resamples N] [--seed N]
        [--reference-account USD] [--risk-pct P] [--data-source alpaca]

--arms is a whole-window measure_arms file (selection or validation) with its census
<stem>.gap_reclaim.json beside it. --basis is the fold-train next-open basis pair (component
MARKET_ENTRY_NEXT_OPEN=true against an empty baseline); it is refused on a validation stamp,
because next-open vs close fill is read on fold-train only (spec § On a pass). The regime cut is
descriptive (regime2 state of SPY on the signal date); there is no earnings cut (no as-of
earnings archive). Descriptive: nothing here decides a stage.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data")]

from swingbot.core.backtesting.acceptance import (BOOTSTRAP_RESAMPLES, ArmTrade,  # noqa: E402
                                                  delta_expectancy_r, delta_standardised_win_rate,
                                                  expectancy_r, win_rate)
from swingbot.core.backtesting.arms import gap_reclaim_census, gap_reclaim_clauses  # noqa: E402
from swingbot.core.edge.regime2 import regime_series  # noqa: E402

BASIS_DELTA = {"MARKET_ENTRY_NEXT_OPEN": True}


class Refused(Exception):
    """A refusal token and its reason; the CLI prints it and exits 1."""


def _parser() -> argparse.ArgumentParser:
    from fetch_backtest_data import add_data_source_arg
    p = argparse.ArgumentParser(description="v192 gap-reclaim report")
    p.add_argument("--arms", required=True, type=Path)
    p.add_argument("--basis", type=Path, default=None)
    p.add_argument("--out-json", required=True, type=Path)
    p.add_argument("--out-md", required=True, type=Path)
    p.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--reference-account", type=float, default=100_000.0)
    p.add_argument("--risk-pct", type=float, default=1.0)
    add_data_source_arg(p)
    return p


def _load_pair(path) -> tuple:
    blob = json.loads(Path(path).read_text(encoding="utf-8"))
    if "baseline" not in blob or "component" not in blob:
        raise Refused(f"refused:no-whole-window -- {path} has no whole-window rows (a fold-only file?).")
    return blob, [ArmTrade(**r) for r in blob["baseline"]], [ArmTrade(**r) for r in blob["component"]]


def _arm(trades) -> dict:
    return {"n": len(trades), "win_rate": win_rate(trades), "expectancy_r": expectancy_r(trades)}


def _pair(baseline, component) -> dict:
    return {"n_baseline": len(baseline), "n_component": len(component),
            "baseline_win_rate": win_rate(baseline), "component_win_rate": win_rate(component),
            "delta_win_rate_pp": delta_standardised_win_rate(baseline, component),
            "delta_expectancy_r": delta_expectancy_r(baseline, component)}


def basis_section(path) -> dict:
    """Next-open baseline vs today's v1 close fill, fold-train only (disclosure)."""
    blob, baseline, component = _load_pair(path)
    stamp = blob.get("provenance") or {}
    if stamp.get("stage") == "validation":
        raise Refused("refused:basis-on-validation -- next-open vs close fill is read on fold-train only.")
    if stamp.get("knob_delta") != BASIS_DELTA or stamp.get("baseline_knob_delta"):
        raise Refused("refused:not-a-basis-pair -- the basis pair is component MARKET_ENTRY_NEXT_OPEN=true "
                      "against an empty baseline.")
    return {"stage": stamp.get("stage"), "close_fill": _arm(baseline), "next_open": _arm(component),
            "delta_win_rate_pp": delta_standardised_win_rate(baseline, component),
            "delta_expectancy_r": delta_expectancy_r(baseline, component),
            "note": "disclosure only; decides nothing (spec § Replay basis)"}


def _spy_frame():
    from swingbot import config
    from swingbot.core.marketdata import training_data
    return training_data.load_daily(config.MARKET_REGIME_TICKER)


def regime_section(baseline, component, spy) -> dict:
    """Descriptive regime2 cut: SPY's state on each trade's signal date ('unknown' when absent)."""
    if spy is None:
        return {"unavailable": "no SPY frame in the selected training data"}
    states = {str(ts.date()): str(state) for ts, state in regime_series(spy).items()}
    label = {t.key: states.get(t.entry_date, "unknown") for t in [*baseline, *component]}
    values = sorted(set(label.values()))
    return {value: _pair([t for t in baseline if label[t.key] == value],
                         [t for t in component if label[t.key] == value]) for value in values}


def build(args) -> dict:
    blob, baseline, component = _load_pair(args.arms)
    side = gap_reclaim_census.load_sidecar(args.arms)
    if side is None:
        raise Refused("refused:no-gap-reclaim-sidecar -- the report needs <arms stem>.gap_reclaim.json.")
    out = {"arms": str(args.arms), "provenance": blob.get("provenance"),
           "census_health": {key: side.get(key) for key in ("repriced_in_component",
                                                            "repriced_absent_from_component")},
           **gap_reclaim_clauses.report(baseline, component, side["rows"], n_resamples=args.resamples,
                                        seed=args.seed, reference_account=args.reference_account,
                                        risk_pct=args.risk_pct),
           "regime": regime_section(baseline, component, _spy_frame())}
    if args.basis:
        out["basis"] = basis_section(args.basis)
    return out


def _fmt(value, spec: str = "+.4f") -> str:
    return "n/a" if value is None else format(value, spec)


def _interval_line(name: str, block: dict, spec: str) -> str:
    return (f"- {name}: {_fmt(block['point'], spec)} [{_fmt(block['lo'], spec)}, {_fmt(block['hi'], spec)}] "
            f"(week-cluster bootstrap)")


def _strata_lines(rows) -> list[str]:
    lines = ["| Stratum | N | Decided | WR | ExpR | Baseline WR | Baseline ExpR |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['stratum']} | {r['n']} | {r['decided']} | {_fmt(r['win_rate'], '.2f')} | "
                     f"{_fmt(r['expectancy_r'])} | {_fmt(r['baseline_win_rate'], '.2f')} | "
                     f"{_fmt(r['baseline_expectancy_r'])} |")
    return lines


def _split_lines(title: str, block: dict) -> list[str]:
    lines = [f"### {title}", "", "| Value | Base N | Comp N | dWR pp | dExpR |", "|---|---|---|---|---|"]
    for value, row in block.items():
        lines.append(f"| {value} | {row['n_baseline']} | {row['n_component']} | "
                     f"{_fmt(row['delta_win_rate_pp'], '+.2f')} | {_fmt(row['delta_expectancy_r'])} |")
    return lines + [""]


def _census_lines(census: dict) -> list[str]:
    lines = ["| Horizon | Direction | Market plans | Armed | Reclaimed | Ambiguous | Open through stop | Risk cap |",
             "|---|---|---|---|---|---|---|---|"]
    for c in census["cells"]:
        lines.append(f"| {c['horizon_key']} | {c['direction']} | {c['market_plans']} | {c['armed']} | "
                     f"{c['reclaimed']} | {c['ambiguous']} | {c['open_through_stop']} | {c['risk_cap']} |")
    return lines


def render_markdown(report: dict) -> str:
    dollars, amb = report["repriced_dollars"], report["ambiguous_sensitivity"]
    lines = ["# v192 gap-reclaim report", "", f"Arms: `{report['arms']}`", "",
             f"- N: baseline {report['n']['baseline']}, component {report['n']['component']}",
             _interval_line("dWR (pp, standardised)", report["delta_win_rate_pp"], "+.2f"),
             _interval_line("dExpR (R)", report["delta_expectancy_r"], "+.4f"),
             f"- outcome flips: {report['outcome_flips']}", "", "## Strata", "",
             *_strata_lines(report["strata"]), "", "## Re-priced trades in dollars", "",
             f"- n {dollars['n']}, risk ${dollars['risk_dollars']:.0f} per trade: baseline "
             f"${dollars['baseline_dollars']:.2f}, component ${dollars['component_dollars']:.2f}, "
             f"delta ${dollars['delta_dollars']:.2f}", "", "## Ambiguous-bar sensitivity", "",
             f"- ambiguous fills: {amb['ambiguous_n']}; dWR as fills {_fmt(amb['as_fills']['delta_win_rate_pp'], '+.2f')}pp, "
             f"as cancels {_fmt(amb['as_cancels']['delta_win_rate_pp'], '+.2f')}pp", "", "## Census", "",
             *_census_lines(report["census"]), "", "## Splits (descriptive)", ""]
    for field, block in report["splits"].items():
        lines += _split_lines(field, block)
    lines += ["## Regime (descriptive)", "", f"```\n{json.dumps(report['regime'], indent=1)}\n```", "",
              f"Earnings proximity: {report['earnings_proximity']}", ""]
    if "basis" in report:
        lines += ["## Next-open basis (fold-train, disclosure)", "", f"```\n{json.dumps(report['basis'], indent=1)}\n```", ""]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    from fetch_backtest_data import apply_data_source
    apply_data_source(args)
    try:
        report = build(args)
    except Refused as exc:
        print(f"{exc} Budget intact.", file=sys.stderr)
        return 1
    for path in (args.out_json, args.out_md):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    args.out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {args.out_json}\nwrote {args.out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
