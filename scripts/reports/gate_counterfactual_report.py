"""v147: print the gate-counterfactual report and persist it to data/reports/gate-counterfactual.json.

A thin wrapper: every figure comes from
swingbot.core.analytics.gate_counterfactual_report.build_report().

Run on production (the live table and the market_data/ cache live there):
    python scripts/reports/gate_counterfactual_report.py
TRAIN only, nothing written (a reading, never a verdict of record):
    python scripts/reports/gate_counterfactual_report.py --train logs/v147-blocked-confluence.jsonl \
        logs/v147-blocked-compression.jsonl --no-live --no-write --json logs/v147-train-report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from swingbot.core.analytics import gate_counterfactual_inputs as inputs  # noqa: E402
from swingbot.core.analytics import gate_counterfactual_report as report  # noqa: E402


def _num(value, spec: str = "+.2f") -> str:
    return "-" if value is None else format(value, spec)


def _cell_line(cell: dict) -> str:
    head = f"  {cell['gate']:<22}{cell['population']:<6}"
    if cell["note"]:
        return f"{head}{cell['note']}"
    if cell["verdict"] == report.WAITING:
        return f"{head}WAITING ({cell['n']}/{report.VERDICT_FLOOR} distinct filled setups)"
    latest, record = cell["latest"], cell["verdict_of_record"] or {}
    tag = " [in-sample]" if cell["in_sample"] else ""
    return (f"{head}{cell['verdict']}{tag} n={cell['n']} diff={_num(latest['difference'])} "
            f"CI=[{_num(latest['ci_low'])}, {_num(latest['ci_high'])}] q={_num(latest['q'], '.3f')} | "
            f"of record: {record.get('verdict')} ({record.get('date')}, n={record.get('n')})")


def cell_lines(result: dict) -> list[str]:
    return ["Verdicts -- blocked ExpR - taken ExpR, gate x population, never pooled:"] + \
        [_cell_line(cell) for cell in result["cells"]]


ROW_HEADER = (f"  {'gate':<22}{'reason':<24}{'pop':<6}{'N':>5}{'noplan':>7}{'fill':>6}{'blkExpR':>9}"
              f"{'blkWR':>7}{'tknExpR':>9}{'tknWR':>7}{'nearN':>6}{'nearExpR':>9}{'$risk':>7}  labels")


def _row_line(row: dict) -> str:
    labels = [name for name, on in (("over-cap", row["over_cap"]), ("in-sample", row["in_sample"])) if on]
    return (f"  {row['gate']:<22}{str(row['reason']):<24}{row['population']:<6}{row['blocked_n']:>5}"
            f"{row['no_plan_n']:>7}{_num(row['fill_rate'], '.0%'):>6}{_num(row['blocked_exp_r']):>9}"
            f"{_num(row['blocked_win_rate'], '.0%'):>7}{_num(row['taken_exp_r']):>9}"
            f"{_num(row['taken_win_rate'], '.0%'):>7}{_num(row['near_miss_n'], 'd'):>6}"
            f"{_num(row['near_miss_exp_r']):>9}{_num(row['dollar_risk']):>7}  {' '.join(labels)}")


def row_lines(result: dict) -> list[str]:
    return ["Rows -- gate x reason x population (R per trade; $risk in units of the 2% cap):", ROW_HEADER] + \
        [_row_line(row) for row in result["rows"]]


def _parse(argv):
    parser = argparse.ArgumentParser(description="v147 gate-counterfactual report")
    parser.add_argument("--train", nargs="*", type=Path, default=None,
                        help="TRAIN gate-row JSONL files (default: logs/ and data/reports/inputs/)")
    parser.add_argument("--no-live", action="store_true", help="leave the live table out")
    parser.add_argument("--no-write", action="store_true", help="print a reading; write nothing")
    parser.add_argument("--json", type=Path, default=None, help="also dump the result to this path")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse(argv)
    train = None if args.train is None else inputs.load_train_rows(args.train)
    live = ([], []) if args.no_live else (None, None)
    result = report.build_report(train_rows=train, live_blocked=live[0], live_taken=live[1],
                                 write=not args.no_write)
    status = "reading only (--no-write): not a verdict of record" if args.no_write else "written"
    print(f"gate counterfactual {result['generated_at']}  live window {result['live_window']}  [{status}]")
    for line in cell_lines(result) + [""] + row_lines(result) + ["", "Limitations:"]:
        print(line)
    for text in result["limitations"]:
        print(f"  - {text}")
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
