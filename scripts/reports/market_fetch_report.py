"""v171 D9: the market-fetch success-week report (plan v171, V171-34).

Read-only. Measures what the shared market-data layer changed: provider calls
per in-session hour (from the hourly counter table), scan error rate, quote
age of posted plans, blank tape minutes, and the plan-rebuild telemetry. Prints
one table and six check rows; always exits 0 (a report, not a gate).

Definitions (fixed before any count exists; the source of record, never retuned):

* Provider calls = counter rows with outcome ``fetched`` or ``failed``; ``hit``,
  ``shared-wait`` and ``budget-deferred`` made no call. The layer counts per
  symbol in both ``count`` and ``on`` mode, so the baseline and the week are
  counted alike. ``mean`` = calls / in-session hours that have at least one row
  (an hour with the bot down has no rows and drops out of both). ``days`` = per
  UTC date, the number of in-session hours with rows. ``by_provider``,
  ``by_kind`` and ``by_asker`` sum provider calls; ``by_outcome`` sums every
  outcome (hits included); all of them over in-session hours only.
* Quote-age miss = a plan whose ``issued_at`` (else ``created_at``) is in the
  window, ``quote_age_s`` is not None and ``quote_age_s > QUOTE_AGE_LIMIT_S``
  (5.0, a module constant, never read from config).
* Errors per ticker = (sum ``errors`` + sum ``data_skips``) / sum ``tickers``
  over telemetry rows in the window that carry ``tickers`` (scan rows; deploy
  markers carry none).
* Blank tape minute = an in-session sample whose ``blank`` list is non-empty.
  ``coverage`` = in-session samples / in-session minutes of the window.
* Verdicts: ``quote_age`` PASS when stamped > 0 and misses == 0, MISS when
  misses > 0, else UNMEASURED; ``blank_tape`` MISS when blank_minutes > 0, PASS
  when 0 with coverage >= 0.95 and no sample error, else UNMEASURED;
  ``errors_per_ticker`` PASS when the week's value <= the baseline's, MISS when
  above, UNMEASURED without a baseline or scans; ``calls_per_hour`` PASS when
  the week's mean <= 0.5 x the baseline's mean, MISS when above, UNMEASURED
  when either mean is None; ``provider_429s`` and ``delta_parity`` are always
  UNMEASURED here (value "see V171-39").

Dates are UTC and inclusive. Run from the repo or piped into the bot container:

    python scripts/reports/market_fetch_report.py --since 2026-10-19 --until 2026-10-23 \\
        [--baseline-since D --baseline-until D] [--tape-samples PATH] [--json OUT]
    docker compose exec -T bot python - <args> < scripts/reports/market_fetch_report.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

QUOTE_AGE_LIMIT_S = 5.0
PROVIDER_OUTCOMES = ("fetched", "failed")
COVERAGE_MIN = 0.95
CALLS_RATIO = 0.5
_UTC = timezone.utc


def window(since: date, until: date) -> tuple[datetime, datetime]:
    """[since 00:00 UTC, until + 1 day 00:00 UTC)."""
    start = datetime(since.year, since.month, since.day, tzinfo=_UTC)
    last = datetime(until.year, until.month, until.day, tzinfo=_UTC)
    return start, last + timedelta(days=1)


def _session_minute(moment: datetime) -> bool:
    from swingbot.core.market.session import is_regular_session, is_tape_open
    return is_regular_session(moment) and is_tape_open(moment)


def in_session_hour(hour: datetime) -> bool:
    """A counter hour is in session when its midpoint is."""
    return _session_minute(hour + timedelta(minutes=30))


def _parse(value) -> datetime | None:
    if isinstance(value, datetime):
        stamp = value
    elif isinstance(value, str) and value:
        try:
            stamp = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    return stamp.replace(tzinfo=_UTC) if stamp.tzinfo is None else stamp.astimezone(_UTC)


def _in_window(value, start: datetime, end: datetime) -> bool:
    stamp = _parse(value)
    return stamp is not None and start <= stamp < end


def calls_per_hour(rows: list[dict]) -> dict:
    by = {name: defaultdict(int) for name in ("provider", "kind", "asker", "outcome")}
    hours: set[datetime] = set()
    days: dict[str, set] = defaultdict(set)
    calls = 0
    for row in rows:
        hour = _parse(row["hour"])
        if hour is None or not in_session_hour(hour):
            continue
        hours.add(hour)
        days[hour.date().isoformat()].add(hour)
        by["outcome"][row["outcome"]] += row["n"]
        if row["outcome"] in PROVIDER_OUTCOMES:
            calls += row["n"]
            for name in ("provider", "kind", "asker"):
                by[name][row[name]] += row["n"]
    return {"hours": len(hours), "calls": calls, "mean": calls / len(hours) if hours else None,
            "by_provider": dict(by["provider"]), "by_kind": dict(by["kind"]),
            "by_asker": dict(by["asker"]), "by_outcome": dict(by["outcome"]),
            "days": {day: len(found) for day, found in sorted(days.items())}}


def scan_quality(rows: list[dict], start: datetime, end: datetime) -> dict:
    scans = tickers = errors = skips = 0
    for row in rows:
        if row.get("tickers") is None or not _in_window(row.get("at"), start, end):
            continue
        scans += 1
        tickers += row["tickers"]
        errors += row.get("errors") or 0
        skips += row.get("data_skips") or 0
    per_ticker = round((errors + skips) / tickers, 6) if tickers else None
    return {"scans": scans, "tickers": tickers, "errors": errors,
            "data_skips": skips, "per_ticker": per_ticker}


def quote_ages(plans: list[dict], start: datetime, end: datetime) -> dict:
    stamped = 0
    max_s = None
    miss_ids: list[str] = []
    for plan in plans:
        age = plan.get("quote_age_s")
        if age is None or not _in_window(plan.get("issued_at") or plan.get("created_at"), start, end):
            continue
        stamped += 1
        max_s = age if max_s is None else max(max_s, age)
        if age > QUOTE_AGE_LIMIT_S:
            miss_ids.append(plan.get("plan_id"))
    return {"stamped": stamped, "misses": len(miss_ids), "max_s": max_s, "miss_ids": miss_ids}


def rebuild_totals(rows: list[dict], start: datetime, end: datetime) -> dict:
    totals = {"kept": 0, "dropped": 0, "misses": 0}
    for row in rows:
        block = row.get("rebuild")
        if isinstance(block, dict) and _in_window(row.get("at"), start, end):
            for name in totals:
                totals[name] += block.get(name) or 0
    return totals


def _session_minutes(start: datetime, end: datetime) -> int:
    total = 0
    moment = start
    while moment < end:
        total += _session_minute(moment)
        moment += timedelta(minutes=1)
    return total


def blank_tape(samples: list[dict], start: datetime, end: datetime) -> dict:
    minutes: dict[datetime, dict] = {}
    for sample in samples:
        stamp = _parse(sample.get("at"))
        if stamp and sample.get("in_session") and start <= stamp < end:
            minutes[stamp.replace(second=0, microsecond=0)] = sample
    session = _session_minutes(start, end)
    blank = sum(1 for s in minutes.values() if s.get("blank"))
    errors = sum(1 for s in minutes.values() if s.get("error"))
    return {"samples": len(minutes), "session_minutes": session,
            "coverage": round(len(minutes) / session, 4) if session else 0.0,
            "blank_minutes": blank, "errors": errors}


def _row(check: str, threshold: str, value, verdict: str) -> dict:
    return {"check": check, "threshold": threshold, "value": value, "verdict": verdict}


def _quote_check(quotes: dict) -> dict:
    if quotes["misses"] > 0:
        verdict = "MISS"
    else:
        verdict = "PASS" if quotes["stamped"] > 0 else "UNMEASURED"
    return _row("quote_age", f"0 plans over {QUOTE_AGE_LIMIT_S:g} s",
                f"{quotes['misses']} of {quotes['stamped']}", verdict)


def _tape_check(tape: dict) -> dict:
    if tape["blank_minutes"] > 0:
        verdict = "MISS"
    elif tape["coverage"] >= COVERAGE_MIN and not tape["errors"]:
        verdict = "PASS"
    else:
        verdict = "UNMEASURED"
    return _row("blank_tape", f"0 blank minutes, coverage >= {COVERAGE_MIN:.0%}",
                f"{tape['blank_minutes']} blank, coverage {tape['coverage']:.1%}", verdict)


def _ratio_check(name: str, threshold: str, week, base, factor: float) -> dict:
    if week is None or base is None:
        verdict = "UNMEASURED"
    else:
        verdict = "PASS" if week <= factor * base else "MISS"
    return _row(name, threshold, {"week": week, "baseline": base}, verdict)


def _errors_check(week: dict, baseline: dict | None) -> dict:
    base = baseline["scan"] if baseline else {"scans": 0, "per_ticker": None}
    measured = week["scan"]["scans"] > 0 and base["scans"] > 0
    return _ratio_check("errors_per_ticker", "week <= baseline",
                        week["scan"]["per_ticker"] if measured else None,
                        base["per_ticker"] if measured else None, 1.0)


def checks(week: dict, baseline: dict | None) -> list[dict]:
    base_mean = baseline["calls"]["mean"] if baseline else None
    return [
        _quote_check(week["quotes"]),
        _tape_check(week["tape"]),
        _row("provider_429s", "none new", "see V171-39", "UNMEASURED"),
        _errors_check(week, baseline),
        _ratio_check("calls_per_hour", "week <= 0.5 x baseline", week["calls"]["mean"], base_mean, CALLS_RATIO),
        _row("delta_parity", "zero diffs", "see V171-39", "UNMEASURED"),
    ]


def _quality(count_rows, telemetry_rows, since: date, until: date) -> dict:
    start, end = window(since, until)
    return {"calls": calls_per_hour(count_rows(start, end)),
            "scan": scan_quality(telemetry_rows, start, end)}


def build_report(*, since: date, until: date, baseline=None, count_rows, telemetry_rows,
                 plans, samples) -> dict:
    start, end = window(since, until)
    week = _quality(count_rows, telemetry_rows, since, until)
    week.update(quotes=quote_ages(plans, start, end),
                rebuild=rebuild_totals(telemetry_rows, start, end),
                tape=blank_tape(samples, start, end))
    base = _quality(count_rows, telemetry_rows, *baseline) if baseline else None
    return {"since": since.isoformat(), "until": until.isoformat(), "week": week,
            "baseline": base, "checks": checks(week, base)}


def _load_counts(start: datetime, end: datetime) -> list[dict]:
    from swingbot.core.db.engine import transaction
    from swingbot.core.db.repositories.market_shared import market_shared_repo
    with transaction() as conn:
        return market_shared_repo().count_rows(start, end, conn=conn)


def _load_telemetry() -> list[dict]:
    from swingbot.core.scanning import telemetry
    rows: list[dict] = []
    if not os.path.exists(telemetry.TELEMETRY_PATH):
        return rows
    with open(telemetry.TELEMETRY_PATH, encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def _load_plans() -> list[dict]:
    from swingbot.core.planning.plan_store import PlanStore
    return PlanStore().records()


def _load_samples(path: str | None) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def _fmt_map(values: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(values.items())) or "-"


def _print_quality(label: str, block: dict) -> None:
    calls = block["calls"]
    mean = "n/a" if calls["mean"] is None else f"{calls['mean']:.1f}"
    print(f"{label:<10} in-session hours={calls['hours']} calls={calls['calls']} mean/h={mean}")
    for key in ("by_provider", "by_kind", "by_asker", "by_outcome", "days"):
        print(f"  {key:<12} {_fmt_map(calls[key])}")
    print(f"  {'scan':<12} {_fmt_map(block['scan'])}")


def _print_report(report: dict) -> None:
    _print_quality("week", report["week"])
    if report["baseline"]:
        _print_quality("baseline", report["baseline"])
    for key in ("quotes", "rebuild", "tape"):
        print(f"{key:<10} {_fmt_map({k: v for k, v in report['week'][key].items() if k != 'miss_ids'})}")
    print(f"{'check':<18} {'verdict':<11} {'threshold':<36} value")
    for row in report["checks"]:
        print(f"{row['check']:<18} {row['verdict']:<11} {row['threshold']:<36} {row['value']}")


def _date(text: str) -> date:
    return date.fromisoformat(text)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", type=_date, required=True)
    ap.add_argument("--until", type=_date, required=True)
    ap.add_argument("--baseline-since", type=_date)
    ap.add_argument("--baseline-until", type=_date)
    ap.add_argument("--tape-samples")
    ap.add_argument("--json")
    return ap


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    baseline = None
    if args.baseline_since and args.baseline_until:
        baseline = (args.baseline_since, args.baseline_until)
    report = build_report(since=args.since, until=args.until, baseline=baseline,
                          count_rows=_load_counts, telemetry_rows=_load_telemetry(),
                          plans=_load_plans(), samples=_load_samples(args.tape_samples))
    _print_report(report)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
