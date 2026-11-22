"""v238 replication ladder, one rung per run (v230 spec Part B; plan v238 Part 5):
replicate_idea.py --idea <name> --rung <1-4> --work-dir <dir>. Rung 1 re-races
the screen through the v1 pipeline on the Alpaca PIT store; rungs 2-4 race the
rung above's events. Refusals exit 2 before any outcome is read. Frames end at
ladder.READ_END (never 2021+). --dry-run writes no doc, row or marker."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, Path(__file__).resolve().parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import screen_idea  # noqa: E402  imported, never edited (index Global Constraints)
from swingbot import config  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.backtesting.screen import indicators, ladder, ladder_bot, ladder_race, race  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS  # noqa: E402

DEFAULT_STORE = Path(config.DATA_DIR) / "market_data_pit" / "daily"
DEFAULT_WORK = ROOT / "logs" / "ladder"
PROGRESS_EVERY = 25
_NO_SHOT = "No row, no shot spent."
FINAL_YEAR = ladder.READ_END[:4]
PRIOR_READS = {"turtle_soup": (
    "a screen-style race on Alpaca 2018-2022 (watchlist) was already read at -0.046R in "
    "docs/superpowers/results/2026-10-23-v180-turtle-soup-result.md; this rung is not blind to it")}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--idea", required=True, choices=list(IDEAS))
    p.add_argument("--rung", required=True, type=int, choices=ladder.RUNGS)
    p.add_argument("--work-dir", type=Path, default=None, help="default logs/ladder/<idea>")
    p.add_argument("--store", type=Path, default=DEFAULT_STORE)
    p.add_argument("--membership", type=Path, default=screen_idea.DEFAULT_MEMBERSHIP)
    p.add_argument("--results-dir", type=Path, default=screen_idea.RESULTS_DIR)
    p.add_argument("--ledger", type=Path, default=stats.LEDGER_PATH)
    p.add_argument("--date", type=screen_idea._iso_day, default=date.today().isoformat())
    p.add_argument("--watchlist", type=Path, default=None,
                   help="tickers, one per line: rung 1 prints that subset, never gating")
    p.add_argument("--tickers", default=None, help="comma list; smoke test, needs --dry-run")
    p.add_argument("--dry-run", action="store_true")
    return p


def _work(args) -> Path:
    return Path(args.work_dir) if args.work_dir else DEFAULT_WORK / args.idea


def _events_path(work_dir, rung: int) -> Path:
    return Path(work_dir) / f"rung{rung}-events.json"


def _tickers(args):
    return args.tickers.split(",") if args.tickers else None


def _store_refusal(args) -> str | None:
    if Path(args.store).is_dir():
        return None
    return f"refused: the PIT store {args.store} does not exist. {_NO_SHOT}"


def _tickers_refusal(args) -> str | None:
    if args.tickers and not args.dry_run:
        return f"refused: --tickers is a smoke test and needs --dry-run. {_NO_SHOT}"
    return None


def _written_refusal(args, name: str) -> str | None:
    results = Path(args.results_dir)
    found = sorted(results.glob(f"*-{ladder.ladder_id(name, args.rung)}.md")) if results.is_dir() else []
    if not found:
        return None
    return f"refused: {found[0].name} exists without a ledger row; the partner decides. {_NO_SHOT}"


def _events_refusal(args) -> str | None:
    path = _events_path(_work(args), args.rung - 1)
    if args.rung == 1 or path.is_file():
        return None
    return f"refused: rung {args.rung} races rung {args.rung - 1}'s events; {path} is missing. {_NO_SHOT}"


def refusals(args, idea, rows) -> str | None:
    """The first reason this rung must not run, or None. Reads no outcome."""
    rows = list(rows)
    checks = (lambda: ladder.input_refusal(idea.name, rows),
              lambda: ladder.rung_refusal(idea.name, args.rung, rows),
              lambda: ladder.shape_refusal(idea, args.rung),
              lambda: _store_refusal(args),
              lambda: ladder.context_refusal(idea, args.store),
              lambda: _tickers_refusal(args),
              lambda: _written_refusal(args, idea.name),
              lambda: _events_refusal(args))
    return next((reason for reason in (check() for check in checks) if reason), None)


@dataclass
class RungRun:
    events: list
    counters: Counter
    gap_count: int = 0
    gap_r: float = 0.0
    survival: dict | None = None
    clamp_share: float | None = None
    attrition: dict | None = None


def _write_json(path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=1), encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def write_events(path, events) -> None:
    _write_json(path, [asdict(event) for event in events])


def read_events(path) -> list:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [ladder.LadderEvent(**row) for row in rows]


def _frame(store, ticker: str):
    """One store frame, STORE_START..READ_END: nothing after READ_END leaves here."""
    return screen_idea.load_frame(Path(store) / f"{ticker}.csv", ladder.STORE_START, ladder.READ_END)


def _stress_bps() -> float:
    return ladder_race.STRESS_FACTOR * screen_idea.base_slippage()


def _gap_totals(events) -> tuple[int, float]:
    gaps = [event.r for event in events if event.outcome in ladder_race.GAP_OUTCOMES]
    return len(gaps), float(sum(gaps))


def _sorted(events) -> list:
    return sorted(events, key=lambda e: (e.signal_date, e.ticker))


def _rung1_rerace(idea, df, signal_pos):
    """The screen's own race at base and stress slippage (next-open entries only)."""
    if idea.entry != "next_open":
        return None, None
    race_fn, cap = race.race_for(idea.race_shape), idea.time_cap_bars
    kw = {"atr": indicators.atr(df)}
    if idea.direction != "long":
        kw["direction"] = idea.direction
    return (race_fn(df, signal_pos, cap, **kw),
            race_fn(df, signal_pos, cap, slippage_bps=_stress_bps(), **kw))


def _check_rerace(ticker: str, base, rows) -> None:
    want = np.array([row["r_event"] for row in rows], dtype=float)
    if base is not None and not np.allclose(base.r, want, rtol=0.0, atol=1e-9):
        raise RuntimeError(f"{ticker}: the rung 1 re-race disagrees with the screen's own net R")


def _rung1_events(idea, screen, store) -> list:
    """One TickerScreen's rows as LadderEvents (signal bar, gross and stress R added)."""
    if not screen.events:
        return []
    df = _frame(store, screen.ticker)
    entry = df.index.get_indexer(pd.to_datetime([row["entry_date"] for row in screen.events]))
    if (entry < 0).any():
        raise RuntimeError(f"{screen.ticker}: a screen entry date is not in the store frame")
    signal = entry - screen_idea._ENTRY_OFFSET[idea.entry]
    base, stress = _rung1_rerace(idea, df, signal)
    _check_rerace(screen.ticker, base, screen.events)
    days = df.index[signal].strftime("%Y-%m-%d")
    return [ladder.LadderEvent(
                screen.ticker, days[i], row["entry_date"], row["exit_date"], float(row["r_event"]),
                math.nan if base is None else float(base.gross_r[i]), row["outcome"],
                r_null=float(row["r_null"]),
                r_stress=None if stress is None else float(stress.r[i]))
            for i, row in enumerate(screen.events)]


def _run_rung1(idea, args, out) -> RungRun:
    universe = screen_idea.load_universe(args.store, args.membership,
                                         ladder.STORE_START, ladder.READ_END)
    cov = ladder.membership_coverage(universe.members, args.store)
    out(f"[{idea.name}] rung 1: {cov['in_store']}/{cov['members']} members in the store; "
        f"missing {cov['missing_count']}: {', '.join(cov['missing']) or 'none'}", flush=True)
    screens, skipped = screen_idea.screen_universe(
        idea, universe, args.store, start=ladder.STORE_START, end=ladder.READ_END,
        tickers=_tickers(args), out=out, event_start=ladder.EVENT_START,
        checkpoint_dir=_work(args) / "rung1" / ("screen-smoke" if args.tickers else "screen"))
    events = _sorted(e for s in screens for e in _rung1_events(idea, s, args.store))
    counters = sum((Counter(s.counters) for s in screens), Counter(skipped))
    return RungRun(events, counters, *_gap_totals(events))


NO_STOP = "no_stop"
RUNNING_FILE = "running.json"
CRASH_FILE = "crash.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RunMarker:
    """One shot per id; a crashed run that wrote no result may run once more."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.running = self.directory / RUNNING_FILE
        self.crash = self.directory / CRASH_FILE

    def start(self) -> str | None:
        if self.running.is_file():
            if self.crash.is_file():
                return (f"refused: {self.directory} records a crashed run whose re-run "
                        f"crashed too; the partner decides. {_NO_SHOT}")
            crashed = json.loads(self.running.read_text(encoding="utf-8"))
            _write_json(self.crash, {"crashed_run": crashed, "rerun_started": _now()})
        _write_json(self.running, {"started": _now()})
        return None

    def finish(self) -> None:
        self.running.unlink(missing_ok=True)

    def crash_note(self) -> str | None:
        if not self.crash.is_file():
            return None
        crashed = json.loads(self.crash.read_text(encoding="utf-8"))["crashed_run"]
        return (f"re-run once after a crash: the first run started {crashed.get('started')} "
                f"and wrote no result ({self.crash.as_posix()})")


def _ticker_checkpoint(work_dir, rung: int, ticker: str) -> Path:
    return Path(work_dir) / f"rung{rung}" / f"{ticker}.json"


def _arrays(levels) -> tuple:
    """[(stop, target, reason)] -> stop and target arrays (NaN when absent), reasons."""
    stop = np.array([np.nan if s is None else s for s, _, _ in levels], dtype=float)
    target = np.array([np.nan if t is None else t for _, t, _ in levels], dtype=float)
    return stop, target, [reason for _, _, reason in levels]


def _rung2_levels(df, pos, direction: str) -> tuple:
    stop, target = ladder_race.orderable_levels(df, pos, atr=indicators.atr(df), direction=direction)
    return np.asarray(stop, dtype=float), np.asarray(target, dtype=float), [None] * len(pos)


def _rung3_levels(df, pos, direction: str) -> tuple:
    pairs = [ladder_bot.rung3_levels(df, int(p), direction=direction) for p in pos]
    return _arrays([(s, t, NO_STOP if s is None else None) for s, t in pairs])


def _rung4_levels(df, pos, direction: str) -> tuple:
    return _arrays([ladder_bot.rung4_levels(df, int(p), direction=direction) for p in pos])


_LEVELS = {2: _rung2_levels, 3: _rung3_levels, 4: _rung4_levels}


def _clamp_count(df, pos, stop, direction: str) -> int:
    close = df["Close"].to_numpy(dtype=float)[pos]
    return int(sum(ladder_bot.clamp_would_drop(c, s, direction=direction)
                   for c, s in zip(close, stop)))


def _race_ticker(idea, rung: int, ticker: str, signals: list, args) -> dict:
    """One ticker's rung: levels from the signal bar, then the orderable race."""
    df = _frame(args.store, ticker)
    pos = df.index.get_indexer(pd.to_datetime(signals))
    if (pos < 0).any():
        raise RuntimeError(f"{ticker}: a rung {rung - 1} signal bar is not in the store frame")
    stop, target, reasons = _LEVELS[rung](df, pos, idea.direction)
    keep = np.array([reason is None for reason in reasons], dtype=bool)
    kw = {"stop": stop[keep], "target": target[keep], "direction": idea.direction}
    base = ladder_race.race_levels(df, pos[keep], idea.time_cap_bars, **kw)
    stress = ladder_race.race_levels(df, pos[keep], idea.time_cap_bars,
                                     slippage_bps=_stress_bps(), **kw)
    clamp = _clamp_count(df, pos[keep], stop[keep], idea.direction) if rung == 3 else 0
    return {"signals": list(signals),
            "events": [asdict(e) for e in ladder_race.to_events(ticker, df, base, stress=stress)],
            "reasons": dict(Counter(r for r in reasons if r is not None)), "clamp": clamp}


def _ticker_rung(idea, rung: int, ticker: str, upper: list, args) -> dict:
    """A finished checkpoint for exactly these signals, else race and checkpoint."""
    signals = [event.signal_date for event in upper]
    path = _ticker_checkpoint(_work(args), rung, ticker)
    if path.is_file():
        blob = json.loads(path.read_text(encoding="utf-8"))
        if blob["signals"] != signals:
            raise RuntimeError(f"{path} was written for other rung {rung - 1} events; "
                               "move it away to re-run")
        return blob
    blob = _race_ticker(idea, rung, ticker, signals, args)
    _write_json(path, blob)
    return blob


def _by_ticker(events) -> dict:
    groups: dict = {}
    for event in sorted(events, key=lambda e: (e.ticker, e.signal_date)):
        groups.setdefault(event.ticker, []).append(event)
    return groups


def _readouts(rung: int, blobs: list, events: list, reasons: Counter) -> dict:
    """Rung 3's clamp share; rung 4's attrition and book survival. Never gating."""
    if rung == 3:
        clamp = sum(blob["clamp"] for blob in blobs)
        return {"clamp_share": clamp / len(events) if events else None}
    if rung == 4:
        return {"attrition": {name: reasons.get(name, 0) for name in ladder_bot.ATTRITION},
                "survival": ladder_bot.book_survival(events, max_open=int(config.MAX_OPEN_POSITIONS))}
    return {}


def _race_tickers(idea, rung: int, args, out) -> list:
    """Every wanted ticker's checkpoint blob, with a percent every PROGRESS_EVERY tickers."""
    groups = _by_ticker(read_events(_events_path(_work(args), rung - 1)))
    wanted = _tickers(args)
    names = [t for t in groups if wanted is None or t in wanted]
    blobs = []
    for i, ticker in enumerate(names, start=1):
        blobs.append(_ticker_rung(idea, rung, ticker, groups[ticker], args))
        if i % PROGRESS_EVERY == 0 or i == len(names):
            out(f"[{idea.name}] rung {rung}: {i}/{len(names)} tickers "
                f"({100.0 * i / len(names):.0f}%)", flush=True)
    return blobs


def _run_later(idea, rung: int, args, out) -> RungRun:
    blobs = _race_tickers(idea, rung, args, out)
    events = _sorted(ladder.LadderEvent(**row) for blob in blobs for row in blob["events"])
    reasons = sum((Counter(blob["reasons"]) for blob in blobs), Counter())
    counters = Counter(events_in=sum(len(blob["signals"]) for blob in blobs), raced=len(events))
    counters.update(reasons)
    return RungRun(events, counters, *_gap_totals(events),
                   **_readouts(rung, blobs, events, reasons))


def results_path(results_dir, name: str, rung: int, day: str) -> Path:
    return Path(results_dir) / f"{day}-{ladder.ladder_id(name, rung)}.md"


def _f(value, spec: str = "+.4f") -> str:
    return "n/a" if value is None else format(value, spec)


def _summary(values) -> dict:
    values = list(values)
    return {"n": len(values), "mean": float(np.mean(values)) if values else None}


def _diff_line(label: str, diff) -> str:
    below = "; wholly below zero" if diff.wholly_below_zero else ""
    return (f"- {label} on {diff.n} shared events: {_f(diff.mean)}R "
            f"[{_f(diff.lo)}, {_f(diff.hi)}]{below}.")


def _head(idea, rung, hold, day, input_instrument) -> list:
    lines = [f"# {ladder.ladder_id(idea.name, rung)}: rung {rung} ({ladder.RUNG_NAMES[rung]}) "
             f"-- {hold.verdict}", "",
             f"- Date {day}; instrument `{ladder.LADDER_INSTRUMENT}`; Alpaca PIT S&P 500 store; "
             f"events {ladder.EVENT_START}..{ladder.READ_END}, frames from {ladder.STORE_START}; "
             "nothing later is read.",
             f"- Idea `{idea.name}`: {idea.direction}, race {idea.race_shape}, entry {idea.entry}, "
             f"cap {idea.time_cap_bars}; {idea.summary}",
             f"- Input: the governing screen row, instrument `{input_instrument}`."]
    if input_instrument == "screen-v1":
        lines.append(f"- **Input flag:** the screen pass rests on the v1 null: {ladder.BIASED_NULL_NOTE}.")
    return lines


def _hold_lines(rung, hold) -> list:
    extra = "; rung 1 also needs a positive dExpR against the v1 null" if rung == 1 else ""
    lines = ["", "## Hold rule", "",
             f"- Week-clustered lower 95% bound of net mean R > 0 with N >= {ladder.HOLD_N}{extra}.",
             f"- N = {hold.n}; net mean R {_f(hold.mean)} [{_f(hold.lo)}, {_f(hold.hi)}], "
             f"one-sided p {_f(hold.p, '.4f')}: **{hold.verdict}**."]
    if rung == 1:
        lines.append(f"- dExpR against the v1 null {_f(hold.delta_null)}R; {ladder.BIASED_NULL_NOTE}.")
    return lines


def _book_lines(run, year, stress, watchlist) -> list:
    counters = ", ".join(f"{k} {v}" for k, v in sorted(run.counters.items())) or "none"
    lines = ["", "## Book", "",
             f"- {FINAL_YEAR} alone: N = {year['n']}, net mean R {_f(year['mean'])}.",
             f"- Gap-through fills, priced never dropped: {run.gap_count} events, summed net R "
             f"{run.gap_r:+.4f}.",
             f"- Costs: {screen_idea.base_slippage()} bps a side plus commission (shorts: borrow); "
             f"at {ladder_race.STRESS_FACTOR} x slippage (never gating) N = {stress['n']}, "
             f"net mean R {_f(stress['mean'])}.",
             f"- Counters: {counters}."]
    if watchlist is not None:
        lines.append(f"- Watchlist subset (never gating): N = {watchlist['n']}, net mean R "
                     f"{_f(watchlist['mean'])}.")
    return lines


def _rung1_lines(idea) -> list:
    lines = ["", "## A robustness check", "",
             f"- Not an independent replication: the years before {FINAL_YEAR} lie inside the "
             f"screen's window on the same universe; only the data source and {FINAL_YEAR} are new."]
    if idea.name in PRIOR_READS:
        lines.append(f"- Prior read: {PRIOR_READS[idea.name]}.")
    return lines


def _bot_lines(run) -> list:
    lines = ["", "## Bot shape (builder's stand-ins, plan v238 ruling 7)", ""]
    lines += [f"- `{key}`: {value}" for key, value in ladder_bot.BOT_SHAPE.items()]
    if run.clamp_share is not None:
        lines.append(f"- Fixed dollar risk; the 2% price-distance cap would have dropped "
                     f"{run.clamp_share:.1%} of events (never gating).")
    if run.attrition is not None:
        lines.append("- Attrition: " + ", ".join(f"{k} {v}" for k, v in run.attrition.items()) + ".")
    if run.survival is not None:
        s = run.survival
        lines.append(f"- Book survival (never gating): one position per ticker "
                     f"{_f(s['one_per_ticker_share'], '.1%')}; with the {config.MAX_OPEN_POSITIONS}-"
                     f"position limit {_f(s['concurrent_share'], '.1%')}; signals per day p95 "
                     f"{_f(s['signals_per_day_p95'], '.1f')}, max {s['signals_per_day_max']}.")
    return lines


def render_rung(idea, rung, run, hold, *, diff=None, year_2020=None, watchlist=None, stress=None,
                date, input_instrument=None) -> str:
    year_2020 = year_2020 or _summary(e.r for e in run.events if e.entry_date.startswith(FINAL_YEAR))
    stress = stress or _summary(e.r_stress for e in run.events if e.r_stress is not None)
    lines = _head(idea, rung, hold, date, input_instrument) + _hold_lines(rung, hold)
    lines += _book_lines(run, year_2020, stress, watchlist)
    if rung == 1:
        lines += _rung1_lines(idea)
    if diff is not None:
        lines += ["", "## Paired difference to the rung above", "",
                  _diff_line(f"Rung {rung} minus rung {rung - 1}", diff)]
    if rung >= 3:
        lines += _bot_lines(run)
    return "\n".join(lines) + "\n"


def _hypothesis(idea, rung, input_instrument) -> str:
    extra = " and a positive dExpR against the v1 null" if rung == 1 else ""
    text = (f"{idea.name} replication ladder rung {rung} ({ladder.RUNG_NAMES[rung]}): week-clustered "
            f"lower 95% bound of net mean R > 0 with N >= {ladder.HOLD_N}{extra}; Alpaca PIT S&P 500 "
            f"store, events {ladder.EVENT_START}..{ladder.READ_END}, after costs (v238).")
    if rung == 1:
        text += f" Null v1: {ladder.BIASED_NULL_NOTE}."
    if input_instrument == "screen-v1":
        text += " Input: a screen-v1 SCREEN-PASS, flagged biased null (v230 placebo)."
    return text


def ledger_row(idea, rung, hold, path, date, *, input_instrument=None) -> dict:
    return {"id": ladder.ladder_id(idea.name, rung), "date": date,
            "hypothesis": _hypothesis(idea, rung, input_instrument),
            "instrument": ladder.LADDER_INSTRUMENT, "n": hold.n,
            "exp_r": None if hold.mean is None else round(hold.mean, 4),
            "p": None if hold.p is None else round(hold.p, 4),
            "verdict": hold.verdict, "record": screen_idea.record_path(path),
            "data_source": "alpaca"}


def _holds(name, rung, rows, verdict) -> dict:
    ids = {ladder.ladder_id(name, r): r for r in ladder.RUNGS if r < rung}
    return {**{ids[row["id"]]: row["verdict"] for row in rows if row["id"] in ids}, rung: verdict}


def _diff_to(args, rung_above, run):
    return ladder.paired_difference(read_events(_events_path(_work(args), rung_above)), run.events)


def _watch_summary(args, rung, events) -> dict | None:
    if rung != 1 or args.watchlist is None:
        return None
    text = Path(args.watchlist).read_text(encoding="utf-8").replace(",", "\n")
    watch = {t.strip().upper() for t in text.splitlines() if t.strip()}
    return _summary(e.r for e in events if e.ticker in watch)


def _tail(args, rung, step, diff42) -> str:
    lines = ["", "## Next step", "", f"- {ladder.NEXT_STEPS[step]}."]
    if diff42 is not None:
        lines.append(_diff_line("Rung 4 minus rung 2", diff42))
    if rung == 1:
        universe = screen_idea.load_universe(args.store, args.membership,
                                             ladder.STORE_START, ladder.READ_END)
        cov = ladder.membership_coverage(universe.members, args.store)
        lines.append(f"- Membership: {cov['in_store']}/{cov['members']} members in the store; "
                     f"missing {cov['missing_count']}: {', '.join(cov['missing']) or 'none'}.")
    crash = RunMarker(_work(args) / f"rung{rung}").crash_note()
    if crash:
        lines.append(f"- Crash record: {crash}.")
    return "\n".join(lines) + "\n"


def publish(args, idea, rung, run) -> int:
    """Results doc first, then the ledger row; --dry-run only prints."""
    rows = stats.load_ledger(args.ledger)
    instrument = (ladder.input_row(idea.name, rows) or {}).get("instrument")
    hold = ladder.hold(run.events, rung=rung)
    path = results_path(args.results_dir, idea.name, rung, args.date)
    row = ledger_row(idea, rung, hold, path, args.date, input_instrument=instrument)
    stats.validate_ledger_row(row)
    diff42 = _diff_to(args, 2, run) if rung == 4 and hold.verdict == ladder.HOLD else None
    text = render_rung(idea, rung, run, hold, diff=None if rung == 1 else _diff_to(args, rung - 1, run),
                       watchlist=_watch_summary(args, rung, run.events), date=args.date,
                       input_instrument=instrument)
    text += _tail(args, rung, ladder.next_step(_holds(idea.name, rung, rows, hold.verdict), diff42), diff42)
    if args.dry_run:
        print(text)
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    stats.append_ledger_row(row, path=args.ledger)
    print(f"{row['id']}: {hold.verdict}, N={hold.n}, mean {_f(hold.mean)}R, "
          f"lower95 {_f(hold.lo)}R -> {row['record']}")
    return 0


def run_rung(idea, rung: int, args, *, out=print) -> RungRun:
    """One rung's events and read-outs; nothing is published here."""
    if rung == 1:
        return _run_rung1(idea, args, out)
    return _run_later(idea, rung, args, out)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    screen_idea._utf8_stdout()
    idea = IDEAS[args.idea]
    reason = refusals(args, idea, stats.load_ledger(args.ledger))
    marker = RunMarker(_work(args) / f"rung{args.rung}")
    if reason is None and not args.dry_run:
        reason = marker.start()
    if reason:
        print(reason, file=sys.stderr)
        return 2
    run = run_rung(idea, args.rung, args)
    if not args.tickers:
        write_events(_events_path(_work(args), args.rung), run.events)
    code = publish(args, idea, args.rung, run)
    if args.dry_run:
        print(f"{ladder.ladder_id(idea.name, args.rung)} (dry run): N={len(run.events)}, "
              f"gap-through {run.gap_count} ({run.gap_r:+.4f}R)")
    else:
        marker.finish()
    return code


if __name__ == "__main__":
    sys.exit(main())
