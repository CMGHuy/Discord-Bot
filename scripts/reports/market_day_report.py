#!/usr/bin/env python3
"""v141 descriptive report: LONG win rate, ExpR and alert volume by SPY's daily move.

DESCRIPTIVE ONLY. Four fixed buckets x three market forms x two directions is
a grid, not a test: some cells will look significant by chance. It selects
nothing, registers nothing and moves no badge. A rule on a lagged form is a
separate pre-registered plan.

The backtest half is TRAIN-only (2020-01-01..2023-12-31) and re-uses plan
v51's sweep. The live half reads a dump made on production by
market_day_live_dump.py; it overlaps the 2026 holdout that open
pre-registrations wait on, so it is monitoring only and prints no interval
and no correlation.

    BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache \
        python scripts/reports/market_day_report.py --backtest \
        --live-json data/market_day_live.json --out docs/superpowers/results/<date>-v141-market-day.md
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest"),
                str(ROOT / "scripts" / "reports")]

from swingbot.core.analytics import market_day as md  # noqa: E402
from swingbot.core.market import entry_filters  # noqa: E402
from swingbot.core.market.session import US_MARKET_TZ  # noqa: E402

TRAIN = ("2020-01-01", "2023-12-31")
DIRECTIONS = (("bullish", "LONG"), ("bearish", "SHORT"))
REGIMES = ((None, "all days"), ("bull", "bull regime"), ("bear", "bear regime"))
FORM_NOTE = {
    "same_day": "same_day -- DESCRIPTIVE ONLY, not known at alert time",
    "prior_day": "prior_day -- known before the scan",
    "trailing_5d": "trailing_5d -- known before the scan",
}
GRID_WARNING = ("> Descriptive grid: 4 buckets x 3 forms x 2 directions x 3 regime cuts. "
                "Some cells will look significant by chance. Nothing here is a selection.")
LIVE_WARNING = ("> Live book: overlaps the 2026 holdout that open pre-registrations wait on. "
                "Monitoring only -- no inferential statistic is printed.")
LEDGER_NOTE = ("The live tables include both ledgers (main and weak): the dump records no "
               "ledger field, so they cannot be told apart here.")


# -- adapters ----------------------------------------------------------------

def et_day(iso: str | None) -> str | None:
    """US/Eastern calendar date of an ISO timestamp; None when unparseable."""
    if not iso:
        return None
    try:
        stamp = datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return str(stamp.date())
    return str(stamp.astimezone(US_MARKET_TZ).date())


def sweep_row(row: dict) -> dict:
    return {"day": row["opened_at"], "closed_day": row.get("closed_at"),
            "direction": row.get("direction"), "outcome": row["outcome"],
            "r": row["r_multiple"], "strategy": row["strategy"], "source": row["source"]}


def live_row(record: dict) -> dict:
    status = record.get("status")
    return {"day": et_day(record.get("opened_at")), "closed_day": et_day(record.get("closed_at")),
            "direction": record.get("direction"),
            "outcome": status if status in ("win", "loss") else "scratch",
            "r": record.get("r"), "strategy": record.get("strategy"), "source": "live"}


def counts_by_day(rows: list[dict], *, direction: str = "bullish",
                  strategy: str | None = None) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        if row.get("direction") != direction or not row.get("day"):
            continue
        if strategy is not None and row.get("strategy") != strategy:
            continue
        out[row["day"]] = out.get(row["day"], 0) + 1
    return out


def _bullish_days(frame, strategy, horizon, date_from: str, date_to: str) -> list[str]:
    bullish, _ = entry_filters.entries_for(strategy, frame, horizon)
    hits = bullish.index[bullish.fillna(False).to_numpy(dtype=bool)]
    return [day for day in (str(ts.date()) for ts in hits) if date_from <= day <= date_to]


def raw_signal_counts(frames: dict, strategies, horizons, date_from: str, date_to: str) -> dict[str, int]:
    """{day: bullish entry signals fired} across the universe, before the
    one-position-at-a-time rule turns some of them into trades."""
    out: dict[str, int] = {}
    for ticker, df in frames.items():
        for horizon in horizons:
            for strategy in strategies:
                try:
                    hits = _bullish_days(df, strategy, horizon, date_from, date_to)
                except Exception as error:               # one bad pair must not kill the count
                    print(f"    ! {ticker} {strategy}/{horizon}: {error}", flush=True)
                    continue
                for day in hits:
                    out[day] = out.get(day, 0) + 1
    return out


def scan_days(scans: list[dict]) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """(alerts per ET day, per-day sums of signals/alerts/funnel stage counts)."""
    alerts: dict[str, int] = {}
    sums: dict[str, dict[str, int]] = {}
    for scan in scans:
        day = et_day(scan.get("at"))
        if day is None:
            continue
        alerts[day] = alerts.get(day, 0) + int(scan.get("alerts") or 0)
        cell = sums.setdefault(day, {"signals": 0, "alerts": 0})
        cell["signals"] += int(scan.get("signals") or 0)
        cell["alerts"] += int(scan.get("alerts") or 0)
        for key, count in md.funnel_stage_counts(scan.get("funnel") or {}).items():
            cell[key] = cell.get(key, 0) + count
    return alerts, sums


def load_live_dump(path) -> dict:
    """The dump's JSON line; anything docker printed around it is ignored."""
    for line in reversed(Path(path).read_text(encoding="utf-8").splitlines()):
        if line.startswith('{"trades"'):
            return json.loads(line)
    raise SystemExit(f"{path}: no dump line found (expected one starting with {{\"trades\")")


def window_days(days: dict, date_from: str, date_to: str) -> dict:
    return {day: market for day, market in days.items() if date_from <= day <= date_to}


# -- rendering ---------------------------------------------------------------

def _rate(value, suffix="") -> str:
    return "—" if value is None else f"{value:.2f}{suffix}"


def _ci(value) -> str:
    return "—" if value is None else f"{value[0]:.2f} .. {value[1]:.2f}"


def _trade_lines(title: str, table: list[dict], intervals: bool) -> list[str]:
    head = "| bucket | trades | days | win rate | ExpR |"
    rule = "|---|---|---|---|---|"
    if intervals:
        head += " win rate 95% interval | ExpR 95% interval |"
        rule += "---|---|"
    lines = [f"**{title}**", "", head, rule]
    for row in table:
        line = (f"| {row['bucket']} | {row['n']} | {row['days']} | "
                f"{_rate(row['win_rate'], '%')} | {_rate(row['exp_r'], 'R')} |")
        if intervals:
            line += f" {_ci(row['win_rate_ci'])} | {_ci(row['exp_r_ci'])} |"
        lines.append(line)
    return lines + [""]


def _volume_lines(title: str, table: list[dict]) -> list[str]:
    lines = [f"**{title}**", "", "| bucket | days | mean / day | median / day | zero days |",
             "|---|---|---|---|---|"]
    for row in table:
        lines.append(f"| {row['bucket']} | {row['days']} | {_rate(row['mean'])} | "
                     f"{_rate(row['median'])} | {_rate(row['zero_share'], '%')} |")
    return lines + [""]


def _share(numer, denom) -> str:
    return "—" if not denom else f"{numer / denom * 100:.1f}%"


def _share_for_days(numer, denom, days: int) -> str:
    return _share(numer, denom) if days >= md.MIN_DAYS else "—"


def _direction_form_lines(rows, days, direction: str, label: str, form: str,
                          intervals: bool) -> list[str]:
    lines = [f"### {label} by open day -- {FORM_NOTE[form]}", ""]
    if intervals:
        rho = md.day_rank_correlation(rows, days, form, direction=direction)
        lines += [f"Spearman rho, day return vs day mean R: {'—' if rho is None else rho}", ""]
    for regime, regime_label in REGIMES:
        table = md.trade_table(rows, days, form, direction=direction, regime=regime,
                               intervals=intervals)
        lines += _trade_lines(regime_label, table, intervals)
    return lines


def _trade_block(rows, days, *, intervals: bool) -> list[str]:
    lines: list[str] = []
    for direction, label in DIRECTIONS:
        for form in md.FORMS:
            lines += _direction_form_lines(rows, days, direction, label, form, intervals)
    return lines


def _close_day_block(rows, days, *, intervals: bool, population: str) -> list[str]:
    closed = [{**row, "day": row["closed_day"]} for row in rows if row.get("closed_day")]
    lines = [f"### LONG by CLOSE day ({population}) -- same_day, MECHANICAL", "",
             "Stops are hit when the market falls, so a red close day shows a low win rate "
             "by construction. Shown for contrast with the open-day tables; not evidence.", ""]
    return lines + _trade_lines("all days", md.trade_table(closed, days, "same_day",
                                                           intervals=intervals), intervals)


def _cause_lines(title: str, table: list[dict], pairs) -> list[str]:
    """`pairs` is [(column label, numerator key, denominator key)]."""
    lines = [f"**{title}**", "", "| bucket | days | " + " | ".join(p[0] for p in pairs) + " |",
             "|---|---|" + "---|" * len(pairs)]
    for row in table:
        totals = row["totals"]
        cells = [f"{totals.get(num, 0)} / {totals.get(den, 0)} = "
                 f"{_share_for_days(totals.get(num, 0), totals.get(den, 0), row['days'])}" for _, num, den in pairs]
        lines.append(f"| {row['bucket']} | {row['days']} | " + " | ".join(cells) + " |")
    return lines + [""]


def _opened_per_day_block(rows, days) -> list[str]:
    lines = ["### LONG trades opened per day", ""]
    for form in md.FORMS:
        lines += _volume_lines(f"all populations -- {FORM_NOTE[form]}",
                               md.volume_table(counts_by_day(rows), days, form))
    for strategy in sorted({row["strategy"] for row in rows if row["direction"] == "bullish"}):
        lines += _volume_lines(f"{strategy} -- prior_day",
                               md.volume_table(counts_by_day(rows, strategy=strategy),
                                               days, "prior_day"))
    return lines


def _backtest_cause_block(rows, days, raw) -> list[str]:
    taken = counts_by_day([r for r in rows if r["source"] == "strategy"])
    values = {day: {"signals": raw.get(day, 0), "taken": taken.get(day, 0)}
              for day in set(raw) | set(taken)}
    lines = ["### Cause: fewer setups, or the same setups and fewer taken?", "",
             "Covers named strategies only -- the confluence replay has no separate "
             "pre-trade signal count. `signals` are raw bullish entry signals; `taken` "
             "are trades opened under the one-position-at-a-time rule.", ""]
    for form in md.FORMS:
        table = md.sum_by_bucket(values, days, form)
        lines += _cause_lines(FORM_NOTE[form], table, [("taken / signals", "taken", "signals")])
        lines += _volume_lines(f"raw signals per day -- {form}", md.volume_table(raw, days, form))
    return lines


def backtest_section(rows: list[dict], days: dict, raw: dict[str, int]) -> list[str]:
    lines = ["## Backtest, TRAIN 2020-01-01..2023-12-31", "",
             "Both populations: named strategies and the confluence replay. `day` is the "
             "signal bar's date. Intervals are a 95% interval from a day-level bootstrap "
             "(2000 draws, seed 42).", ""]
    lines += _trade_block(rows, days, intervals=True)
    lines += _close_day_block([r for r in rows if r["source"] == "strategy"], days,
                              intervals=True, population="named strategies")
    lines += _opened_per_day_block(rows, days)
    return lines + _backtest_cause_block(rows, days, raw)


def _stage_pairs(sums: dict[str, dict[str, int]]) -> list[tuple[str, str, str]]:
    """One (label, ok key, reached key) per funnel stage present in the data."""
    from swingbot.core.scanning.short_funnel import STAGES
    present = {key.split(":")[0] for cell in sums.values() for key in cell if ":" in key}
    return [(f"{stage} pass", f"{stage}:ok", f"{stage}:reached")
            for stage in STAGES if stage in present]


def _with_reached(sums: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    out = {}
    for day, cell in sums.items():
        stages = {key.split(":")[0] for key in cell if ":" in key}
        reached = {f"{stage}:reached": cell.get(f"{stage}:ok", 0) + cell.get(f"{stage}:rejected", 0)
                   for stage in stages}
        out[day] = {**cell, **reached}
    return out


def _live_volume_block(alerts, observed, days) -> list[str]:
    lines = ["### Scan alerts per scanned day (all directions)", "",
             "Denominator: trading days with at least one scan. A day with no scan is an "
             "outage and is left out.", ""]
    for form in md.FORMS:
        lines += _volume_lines(FORM_NOTE[form],
                               md.volume_table(alerts, days, form, observed=observed))
    return lines


def _live_cause_block(sums, days) -> list[str]:
    lines = ["### Scan totals (all directions) and bullish stages", ""]
    staged = _with_reached(sums)
    stage_days = {day: cell for day, cell in staged.items()
                  if any(":" in key for key in cell)}
    pairs = _stage_pairs(sums)
    for form in md.FORMS:
        table = md.sum_by_bucket(staged, days, form)
        lines += _cause_lines(f"all-direction alerts / signals -- {FORM_NOTE[form]}", table,
                              [("alerts / signals", "alerts", "signals")])
        if pairs:
            stage_table = md.sum_by_bucket(stage_days, days, form)
            lines += _cause_lines(f"bullish stage pass rates -- {form}", stage_table, pairs)
    return lines


def live_section(rows: list[dict], scans: list[dict], days: dict) -> list[str]:
    alerts, sums = scan_days(scans)
    funnel_days = sum(1 for cell in sums.values() if any(":" in key for key in cell))
    lines = ["## Live paper book", "", LIVE_WARNING, "", LEDGER_NOTE, "",
             "Scan signals and alerts count all directions; funnel stages below select "
             "bullish stages only.", "",
             f"Closed trades: {len(rows)}. Scanned trading days: {len(alerts)}. "
             f"Days with bullish stages: {funnel_days}.", ""]
    lines += _trade_block(rows, days, intervals=False)
    lines += _close_day_block(rows, days, intervals=False, population="live book")
    lines += _live_volume_block(alerts, set(alerts), days)
    return lines + _live_cause_block(sums, days)


# -- loading and CLI ---------------------------------------------------------

def _spy_days(spy_df) -> dict:
    from swingbot.core.edge.regime2 import regime_series
    return md.market_days(spy_df["Close"], regime_series(spy_df))


def _backtest_inputs(limit: int | None, workers: int | None):
    import measure_alert_density as mad
    import run_backtest_range as rbr
    from runner_headroom import cache_universe
    from swingbot.core.backtesting.backtest import ALL_STRATEGIES
    from swingbot.core.backtesting.backtest_scenarios import CONFLUENCE_GATES
    from swingbot.core.market.strategy_types import LEGACY_HORIZONS

    spy = rbr._market_frame()
    if spy is None:
        raise SystemExit("benchmark not in the backtest cache -- run scripts/data/fetch_backtest_data.py")
    spy = spy.loc[:TRAIN[1]]
    tickers = cache_universe()[:limit] if limit else cache_universe()
    frames, _ = mad.load_frames(tickers, date_to=TRAIN[1])
    swept = mad.sweep(frames, *TRAIN, horizons=list(LEGACY_HORIZONS), gates=CONFLUENCE_GATES,
                      scale_out=True, strategies=list(ALL_STRATEGIES), workers=workers)
    print("counting raw entry signals...", flush=True)
    raw = raw_signal_counts(frames, ALL_STRATEGIES, LEGACY_HORIZONS, *TRAIN)
    return [sweep_row(row) for row in swept], window_days(_spy_days(spy), *TRAIN), raw


def _live_inputs(path):
    from swingbot import config
    from swingbot.core.marketdata import backtest_cache

    dump = load_live_dump(path)
    spy = backtest_cache.fetch(config.MARKET_REGIME_TICKER)      # live dates run past the CSV cache
    if spy is None:
        raise SystemExit("could not fetch the benchmark for the live half")
    rows = [live_row(record) for record in dump["trades"]]
    return rows, dump["scans"], _spy_days(spy)


def _parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="v141 market-day report (descriptive only).")
    ap.add_argument("--backtest", action="store_true", help="run the TRAIN half (slow)")
    ap.add_argument("--live-json", dest="live_json", default=None,
                    help="dump from market_day_live_dump.py")
    ap.add_argument("--out", default=None, help="write markdown here (default: stdout)")
    ap.add_argument("--limit", type=int, default=None,
                    help="first N cached tickers -- smoke runs, never the reported answer")
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args(argv)
    if not args.backtest and not args.live_json:
        ap.error("need --backtest and/or --live-json")
    return args


def main() -> None:
    args = _parse_args()
    lines = ["# v141 -- market-day report", "", GRID_WARNING, ""]
    if args.limit:
        lines += [f"> SMOKE RUN: first {args.limit} tickers only. Not a result.", ""]
    if args.backtest:
        lines += backtest_section(*_backtest_inputs(args.limit, args.workers))
    if args.live_json:
        lines += live_section(*_live_inputs(args.live_json))
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", flush=True)
    else:
        print(text)


if __name__ == "__main__":
    main()
