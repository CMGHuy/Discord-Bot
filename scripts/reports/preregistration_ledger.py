#!/usr/bin/env python3
"""Append one pre-registration verdict to the ledger and print its BH q-value.

v136 §4: docs/superpowers/results/preregistration-ledger.jsonl holds one row
per pre-registration. Run this once per new verdict, then commit the ledger
with the results doc. The q-value is REPORTED, NEVER GATING: no acceptance
threshold reads it, and a closed pre-registration is never re-run to move it.

    python scripts/reports/preregistration_ledger.py --id v140-demo \
        --hypothesis "..." --instrument v2 --n 412 --exp-r 0.21 --p 0.03 \
        --verdict FAIL --record docs/superpowers/results/2026-10-20-v140-validation.md
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.instrument import stats  # noqa: E402

_NULLS = ("null", "none", "")


def _optional(cast):
    def parse(text: str):
        return None if text.strip().lower() in _NULLS else cast(text)
    parse.__name__ = cast.__name__   # argparse names the type in its errors
    return parse


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--id", required=True, help="unique, e.g. v140-confluence")
    p.add_argument("--date", default=None, help="YYYY-MM-DD of the verdict; default today")
    p.add_argument("--hypothesis", required=True)
    p.add_argument("--instrument", choices=stats.INSTRUMENTS, required=True)
    p.add_argument("--n", type=_optional(int), default=None, help="int or null")
    p.add_argument("--exp-r", type=_optional(float), default=None, help="float or null")
    p.add_argument("--p", type=_optional(float), default=None, help="float in [0,1] or null")
    p.add_argument("--verdict", choices=stats.VERDICTS, required=True)
    p.add_argument("--record", required=True, help="repo-relative results doc path")
    p.add_argument("--ledger", type=Path, default=stats.LEDGER_PATH)
    return p


def row_from_args(args) -> dict:
    return {"id": args.id, "date": args.date or date.today().isoformat(),
            "hypothesis": args.hypothesis, "instrument": args.instrument,
            "n": args.n, "exp_r": args.exp_r, "p": args.p,
            "verdict": args.verdict, "record": args.record}


def _fmt(value) -> str:
    return "null" if value is None else f"{value:.4f}"


def format_report(row: dict, rows: list) -> str:
    q = stats.ledger_qvalues(rows)[row["id"]]
    m = sum(1 for r in rows if r["p"] is not None)
    q_text = "n/a (no p-value)" if q is None else f"{q:.4f}"
    return (f"{row['id']}: verdict {row['verdict']}, p={_fmt(row['p'])}, "
            f"BH q={q_text} across {m} ledger p-values ({len(rows)} rows). "
            "Reported, not gating.")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    row = row_from_args(args)
    try:
        rows = stats.append_ledger_row(row, path=args.ledger)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(format_report(row, rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
