#!/usr/bin/env python3
"""v173: manual overrides against the engine left alone (spec §4-§5). Read-only.

Replays every manual close from its real fill through the v2 exit engine and
prints one row per override with exactly one status, the descriptive summary
and the verdict state. Reads plans, linked trades, the live scan's bar cache
(market_data/daily, never fetched) and the stored verdict in the Postgres
table preregistration_verdicts.

This script never evaluates the verdict and never writes it: the bot's daily
job (override_io.run_daily_check) is the only evaluator. --production only
drops the dev banner. --mirror-row prints the stored verdict as one jsonl
ledger line for the standing mirror procedure
(docs/superpowers/results/v173-override-fidelity.md).

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot \
        python scripts/reports/execution_fidelity_report.py --production"
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot import config  # noqa: E402
from swingbot.core.analytics import override_fidelity as of  # noqa: E402
from swingbot.core.analytics import override_io as oio  # noqa: E402
from swingbot.core.analytics import override_verdict as ov  # noqa: E402
from swingbot.core.analytics import runner_path as rp  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402

DEV_BANNER = "DEV DATABASE: fixture data, not the real book. This report never writes a verdict."
NO_VERDICT = "no verdict recorded"


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="v173 manual overrides vs the engine (read-only)")
    parser.add_argument("--production", action="store_true",
                        help="the real book on the VM: drops the dev banner, still read-only")
    parser.add_argument("--json", metavar="PATH", help="also write the payload (the API body)")
    parser.add_argument("--mirror-row", action="store_true",
                        help="print the stored verdict as one ledger JSON line, then stop")
    return parser.parse_args(argv)


def mirror_line(record: dict | None) -> tuple[str, dict]:
    """The stored record as one validated jsonl ledger line, or NO_VERDICT."""
    if record is None:
        return NO_VERDICT, {}
    row = ov.mirror_ledger_row(record)
    stats.validate_ledger_row(row)
    return json.dumps(row, ensure_ascii=False), row


# -- rendering ---------------------------------------------------------------------

def _num(value, fmt: str) -> str:
    return "—" if value is None else format(value, fmt)


def _pair(row: dict, key: str, currency: str) -> str:
    usd = row[f"{key}_usd"]
    money = "—" if usd is None else f"{usd:+.2f}{currency}"
    return f"{_num(row[f'{key}_r'], '+.3f')}R/{money}"


def _row_line(row: dict, currency: str) -> str:
    flags = " ".join(name for name, on in (("bulk", row["bulk"]), ("approx", row["approx"])) if on)
    return (f"{row['close_date'] or '—'}  {row['ticker']:<6} {row['horizon']:<3} "
            f"{row['state_at_close']:<7} actual {_pair(row, 'actual', currency)}  "
            f"engine {_pair(row, 'engine', currency)}  delta {_pair(row, 'delta', currency)}  "
            f"exit {row['engine_exit_reason'] or '—'}  {row['status']}  {flags}").rstrip()


def _split_lines(splits: dict, currency: str) -> list[str]:
    return [f"split {key}={value}: n={cell['n']} "
            f"{cell['sum_delta_r']:+.3f}R / {cell['sum_delta_usd']:+.2f}{currency}"
            for key, groups in splits.items() for value, cell in groups.items()]


def _summary_lines(summary: dict, currency: str) -> list[str]:
    lines = [f"counted rows: {summary['counted_n']}  sum delta {summary['sum_delta_r']:+.3f}R"
             f" / {summary['sum_delta_usd']:+.2f}{currency}, before costs "
             f"{summary['sum_delta_r_gross']:+.3f}R"
             f"  (counted rows without dollars: {summary['usd_missing_n']})",
             f"helped / hurt / neutral: {summary['helped']} / {summary['hurt']} / "
             f"{summary['neutral']}  (counts ignore size)"]
    lines += [f"bulk clear {day}: {n} (not decisions, left out)"
              for day, n in summary["bulk_dates"].items()]
    if summary["approx_n"]:
        lines.append(f"approx (estimated exit): {summary['approx_n']} (shown, not counted)")
    lines += [f"{status}: {n}" for status, n in summary["n_by_status"].items() if n]
    return lines + _split_lines(summary["splits"], currency)


def _recorded_tail(verdict: dict) -> str:
    return (f"; recorded {verdict['recorded_on']} from {verdict['n']} overrides over "
            f"{verdict['weeks']} weeks, mean delta {_num(verdict['mean_delta_r'], '+.3f')}R "
            f"(before costs {_num(verdict['mean_delta_r_gross'], '+.3f')}R), "
            f"95% CI {verdict['ci']}, sum {_num(verdict['sum_delta_r'], '+.3f')}R / "
            f"{_num(verdict['sum_delta_usd'], '+.2f')}, bar_close {verdict['bar_close_n']}")


def _verdict_line(verdict: dict) -> str:
    line = (f"verdict {verdict['state']}: {verdict['n']} of {verdict['needed']} counted rows, "
            f"{verdict['weeks']} of {verdict['week_floor']} weeks, open {verdict['open_n']}, "
            f"excluded share {verdict['excluded_share']:.1%}, evaluable {verdict['evaluable']}")
    if verdict["waiting_on"]:
        line += "; waiting on " + ", ".join(verdict["waiting_on"])
    return line + (_recorded_tail(verdict) if verdict["recorded"] else "")


def render(payload: dict) -> list[str]:
    """The printed report: flags, rows, summary and splits, verdict."""
    currency = payload["currency_symbol"]
    flags = " ".join(f"{key}={value}" for key, value in payload["engine_flags"].items())
    lines = [f"v173 overrides vs engine, asof {payload['asof']}  engine flags: {flags}", ""]
    lines += [_row_line(r, currency) for r in payload["rows"]] or ["No manual overrides in scope."]
    lines += ["", *_summary_lines(payload["summary"], currency), "",
              _verdict_line(payload["verdict"])]
    return lines


def main(argv: list[str] | None = None, *, inputs_fn=None, bars_fn=None,
         now: datetime | None = None, verdict_fn=None) -> dict:
    args = _parse(argv)
    if not args.production:
        print(DEV_BANNER)
    recorded = (verdict_fn or oio.stored_verdict)()
    if args.mirror_row:
        line, row = mirror_line(recorded)
        print(line)
        return row
    now = now or datetime.now(timezone.utc)
    plans, trades = (inputs_fn or oio.load_inputs)()
    payload = ov.build_report(plans, trades, bars_fn or rp.cached_daily_bars,
                              of.latest_completed_session(now), recorded,
                              config.CURRENCY_SYMBOL)
    print("\n".join(render(payload)))
    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
    return payload


if __name__ == "__main__":
    main()
