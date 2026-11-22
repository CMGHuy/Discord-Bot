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
from datetime import date
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
from swingbot.core.backtesting.screen import indicators, ladder, ladder_race, race  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS  # noqa: E402

DEFAULT_STORE = Path(config.DATA_DIR) / "market_data_pit" / "daily"
DEFAULT_WORK = ROOT / "logs" / "ladder"
PROGRESS_EVERY = 25
_NO_SHOT = "No row, no shot spent."


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


def run_rung(idea, rung: int, args, *, out=print) -> RungRun:
    """One rung's events and read-outs; nothing is published here."""
    if rung != 1:
        raise NotImplementedError("rungs 2-4 land with V238-15")
    return _run_rung1(idea, args, out)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    screen_idea._utf8_stdout()
    idea = IDEAS[args.idea]
    reason = refusals(args, idea, stats.load_ledger(args.ledger))
    if reason is None and not args.dry_run:     # V238-16: the run marker and publish
        reason = f"refused: ladder-publish-pending (publishing lands with V238-16). {_NO_SHOT}"
    if reason:
        print(reason, file=sys.stderr)
        return 2
    run = run_rung(idea, args.rung, args)
    if not args.tickers:
        write_events(_events_path(_work(args), args.rung), run.events)
    print(f"{ladder.ladder_id(idea.name, args.rung)} (dry run): N={len(run.events)}, "
          f"gap-through {run.gap_count} ({run.gap_r:+.4f}R)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
