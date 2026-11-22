# v238 — Replication ladder and additive gate: Part 5, ladder run and docs (V238-14..V238-17)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V238-15" -A 400 <this file>`).

**Spec:** [2026-11-16-v230-screen-v2-ladder-additive-gate-design.md](../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md) (`### Part B — the replication ladder`, `### What a screened-shape strategy spec must state`, `### Part C` (docs only), `## Constraints`, `## Testing`)
**Index:** [2026-11-19-v238-replication-ladder-additive-gate_0-index.md](2026-11-19-v238-replication-ladder-additive-gate_0-index.md) — Goal, `## Global Constraints`, `## Handoff` (rulings 1, 7, 8, 9 and the 2026-11-19 `INPUT_INSTRUMENTS` ruling), `## Decisions this index fixes` (rung shapes, one rung per invocation, ladder input, membership check) and `## Parallelisation` bind every task below.

Lane B2: V238-14 → V238-15 → V238-16 (same file `scripts/backtest/replicate_idea.py`); V238-17 joins Lane C (needs V238-8 and V238-16: the docs cite final names and flags).

Conventions every task shares:

- **No task may be split** (the plan is at the 20-task cap).
- Contracts consumed, exactly as Part 4 wrote them (`_4-ladder-core.md`): `ladder` (V238-10: `LadderEvent`, `hold`, `paired_difference`, `input_row`, `input_refusal`, `rung_refusal`, `shape_refusal`, `context_refusal`, `membership_coverage`, `next_step`, `NEXT_STEPS`, `BIASED_NULL_NOTE`, the window constants), `ladder_race` (V238-11: `STRESS_FACTOR`, `GAP_OUTCOMES`, `orderable_levels`, `race_levels`, `to_events`), `ladder_bot` (V238-12/13: `BOT_SHAPE`, `rung3_levels`, `clamp_would_drop`, `rung4_levels`, `ATTRITION`, `book_survival`). Every ladder refusal string already ends `No row, no shot spent.`; the script's own refusals do too.
- `scripts/backtest/screen_idea.py` is imported, never edited: `load_frame`, `load_universe`, `screen_universe` (the **v1** pipeline, called explicitly: index ruling 1), `base_slippage`, `record_path`, `_iso_day`, `_utf8_stdout`, `_ENTRY_OFFSET`, `DEFAULT_MEMBERSHIP`, `RESULTS_DIR`.
- No database, no network. The CLI tests build a three-ticker PIT-store fixture in `tmp_path` from `tests/backtesting/screen/helpers.random_walk` (bars from `ladder.STORE_START`); `tests/backtest_scripts/conftest.py` already puts `scripts/backtest` on `sys.path`.
- New tests in `tests/backtest_scripts/` join suite `backtest-scripts`; after adding them run `python -m pytest tests/dev/test_suites.py -q`; if the suite passes its `max_tests`, split it by feature in `tests/suites.toml` in the same commit, never raise the limit.
- Every new function stays under complexity 15 (`python scripts/dev/complexity_gate.py`).
- **No task runs the ladder on a real idea** (index Handoff item 9): every run below is a fixture in `tmp_path`.

# Phase 5 — Ladder run

### Task V238-14: replicate_idea CLI: refusals, run marker and rung 1

**Model:** opus — the refusal order and rung 1's bridge from the v1 screen pipeline to `LadderEvent`s decide whether a ladder shot is honest.

**Files:**
- Create: `scripts/backtest/replicate_idea.py`
- Create: `tests/backtest_scripts/test_replicate_idea.py` (tests; suite `backtest-scripts`)
- Modify: `tests/backtesting/instrument/test_date_literal_guard.py` (one `ALLOW` entry)

**Interfaces:**
- Consumes: Part 4 contracts; `screen_idea.screen_universe` (`:615`, returns `(screens, skipped)`; a `TickerScreen.events` row is `{"ticker","entry_date","exit_date","r_event","r_null","outcome"}`, `:146`); `race.race_for` (`race.py:249`); `indicators.atr`.
- Produces: the ledger row's symbols (`RunMarker` lands in V238-15 and is wired by V238-16, so this task fits 20 KB), plus `--date` (V238-16 adds `--watchlist`) and `--tickers` (smoke, needs `--dry-run`). Helpers V238-15/16 reuse: `_work`, `_events_path(work_dir, rung)`, `_frame(store, ticker)`, `_stress_bps`, `_tickers`, `_gap_totals(events) -> (int, float)`, `_sorted`, `_write_json`, `PROGRESS_EVERY`, `_NO_SHOT`.

Semantics the code does not say: a results doc without a row means that run wrote a result, so it is no crash to re-run; a `--tickers` smoke checkpoints into `screen-smoke` and writes no events file, so it never claims the real run's manifest; a level-entry idea keeps `gross_r = NaN` (it stops after rung 1); until V238-16 a real run is refused `ladder-publish-pending`.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest_scripts/test_replicate_idea.py`:

```python
"""v238 replicate_idea (V238-14): refusals, the events file and rung 1."""
import json
import math
from types import SimpleNamespace

import pytest

import replicate_idea as ri  # on sys.path via conftest.py
import screen_idea

from swingbot.core.backtesting.screen import ladder
from swingbot.core.backtesting.screen.ideas import IDEAS
from swingbot.core.backtesting.screen.ladder import LadderEvent
from tests.backtesting.screen.helpers import random_walk

IDEA = SimpleNamespace(name="turn_of_month", race_shape="fixed", entry="next_open", context=())
PASS_ROW = {"id": "screen-turn_of_month", "date": "2026-11-01", "hypothesis": "fixture pass",
            "instrument": "screen-v1", "n": 400, "exp_r": 0.2, "p": 0.01,
            "verdict": "SCREEN-PASS", "record": "docs/superpowers/results/fixture.md"}


def _ladder_row(rung, verdict):
    return {**PASS_ROW, "id": ladder.ladder_id("turn_of_month", rung),
            "instrument": "ladder-v1", "verdict": verdict, "data_source": "alpaca"}


def _ledger(path, *rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _store(tmp_path, tickers=("AAA", "BBB", "DDD"), extra_members=()):
    store = tmp_path / "store"
    store.mkdir()
    for seed, ticker in enumerate(tickers, start=1):
        random_walk(1300, seed=seed, start=ladder.STORE_START).rename_axis("Date").to_csv(
            store / f"{ticker}.csv")
    (tmp_path / "membership.csv").write_text("ticker,start_date,end_date\n" + "".join(
        f"{t},2000-01-01,\n" for t in (*tickers, *extra_members)), encoding="utf-8")
    return store


def _argv(tmp_path, *extra, rung=1):
    return ["--idea", "turn_of_month", "--rung", str(rung), "--work-dir", str(tmp_path / "work"),
            "--store", str(tmp_path / "store"), "--membership", str(tmp_path / "membership.csv"),
            "--ledger", str(tmp_path / "ledger.jsonl"), "--results-dir", str(tmp_path / "results"),
            "--date", "2026-11-20", *extra]


def _args(tmp_path, *extra, rung=1):
    return ri.build_parser().parse_args(_argv(tmp_path, *extra, rung=rung))


def _quiet(lines):
    return lambda message, **_kw: lines.append(message)


def test_parser_defaults():
    args = ri.build_parser().parse_args(["--idea", "turn_of_month", "--rung", "1"])
    assert args.store == ri.DEFAULT_STORE and args.store.parts[-2:] == ("market_data_pit", "daily")
    assert ri._work(args).parts[-2:] == ("ladder", "turn_of_month")


def test_input_rung_order_and_one_shot_refusals(tmp_path):
    _store(tmp_path)
    assert "SCREEN-PASS" in ri.refusals(_args(tmp_path, "--dry-run"), IDEA, [])
    assert ri.refusals(_args(tmp_path, "--dry-run"), IDEA, [PASS_ROW]) is None
    spent = [PASS_ROW, _ladder_row(1, ladder.FAIL)]
    assert "one shot per id" in ri.refusals(_args(tmp_path), IDEA, spent)
    above = ri.refusals(_args(tmp_path, "--dry-run", rung=2), IDEA, [PASS_ROW])
    assert "needs LADDER-HOLD on ladder-turn_of_month-r1" in above


def test_shape_store_and_context_refusals(tmp_path):
    assert "does not exist" in ri.refusals(_args(tmp_path, "--dry-run"), IDEA, [PASS_ROW])
    _store(tmp_path)
    trail = SimpleNamespace(**{**vars(IDEA), "race_shape": "trail"})
    rows = [PASS_ROW, _ladder_row(1, ladder.HOLD)]
    assert ri.refusals(_args(tmp_path, "--dry-run", rung=2), trail, rows).startswith(ladder.UNAVAILABLE)
    dollar = SimpleNamespace(**{**vars(IDEA), "context": ("UUP",)})
    reason = ri.refusals(_args(tmp_path, "--dry-run"), dollar, [PASS_ROW])
    assert reason.startswith(ladder.UNAVAILABLE) and "UUP" in reason


def test_smoke_written_result_and_events_refusals(tmp_path):
    _store(tmp_path)
    assert "--dry-run" in ri.refusals(_args(tmp_path, "--tickers", "AAA"), IDEA, [PASS_ROW])
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "2026-11-19-ladder-turn_of_month-r1.md").write_text("x", encoding="utf-8")
    assert "exists without a ledger row" in ri.refusals(_args(tmp_path), IDEA, [PASS_ROW])
    rows, args = [PASS_ROW, _ladder_row(1, ladder.HOLD)], _args(tmp_path, "--dry-run", rung=2)
    assert "rung1-events.json" in ri.refusals(args, IDEA, rows)
    ri.write_events(ri._events_path(tmp_path / "work", 1), [])
    assert ri.refusals(args, IDEA, rows) is None


def test_main_refuses_on_stderr_and_writes_nothing(tmp_path, capsys):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl")
    assert ri.main(_argv(tmp_path, "--dry-run")) == 2
    assert "SCREEN-PASS" in capsys.readouterr().err
    assert not (tmp_path / "work").exists() and not (tmp_path / "results").exists()


def test_a_real_run_waits_for_publishing(tmp_path, capsys):      # V238-16 replaces this test
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    assert ri.main(_argv(tmp_path)) == 2
    assert "ladder-publish-pending" in capsys.readouterr().err


def test_events_round_trip_with_nan_gross_and_no_stress(tmp_path):
    events = [LadderEvent("AAA", "2017-03-01", "2017-03-02", "2017-03-08", -0.5, math.nan,
                          "timeout", r_null=0.1),
              LadderEvent("BBB", "2017-03-01", "2017-03-02", "2017-03-03", 2.0, 2.01,
                          "target", r_stress=1.98)]
    path = tmp_path / "w" / "rung1-events.json"
    ri.write_events(path, events)
    back = ri.read_events(path)
    assert [e.key for e in back] == [e.key for e in events]
    assert math.isnan(back[0].gross_r) and back[1] == events[1]
    assert b"\r" not in path.read_bytes()


def test_rung_one_dry_run_races_the_screen_and_writes_its_events(tmp_path, monkeypatch, capsys):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    ends, real = [], screen_idea.load_frame
    monkeypatch.setattr(screen_idea, "load_frame",
                        lambda path, start, end: ends.append(end) or real(path, start, end))
    assert ri.main(_argv(tmp_path, "--dry-run")) == 0
    events = ri.read_events(tmp_path / "work" / "rung1-events.json")
    assert len(events) > 50 and events == ri._sorted(events)
    assert all(ladder.EVENT_START <= e.signal_date < e.entry_date <= e.exit_date <= ladder.READ_END
               for e in events)
    assert all(e.r_null is not None and math.isfinite(e.gross_r) for e in events)
    assert all(e.r_stress is not None and e.r_stress <= e.r + 1e-12 for e in events)
    assert set(ends) == {ladder.READ_END}
    assert any((tmp_path / "work" / "rung1" / "screen").glob("*.pkl"))
    out = capsys.readouterr().out
    assert "3/3 members in the store" in out and "ladder-turn_of_month-r1 (dry run): N=" in out


def test_a_smoke_run_prints_missing_members_and_keeps_apart(tmp_path):
    _store(tmp_path, extra_members=("ZZZ",))
    lines = []
    run = ri.run_rung(IDEAS["turn_of_month"], 1, _args(tmp_path, "--dry-run", "--tickers", "AAA"),
                      out=_quiet(lines))
    assert {e.ticker for e in run.events} == {"AAA"}
    assert any("missing 1: ZZZ" in line for line in lines)
    assert [p.name for p in (tmp_path / "work" / "rung1").iterdir()] == ["screen-smoke"]


def test_a_re_race_that_disagrees_with_the_screen_stops_the_run():
    ri._check_rerace("AAA", SimpleNamespace(r=[0.25]), [{"r_event": 0.25}])
    with pytest.raises(RuntimeError, match="disagrees"):
        ri._check_rerace("AAA", SimpleNamespace(r=[0.25]), [{"r_event": 0.75}])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_replicate_idea.py`
Expected: FAIL at collection, `ModuleNotFoundError: No module named 'replicate_idea'`.

- [ ] **Step 3: Write the script**

Create `scripts/backtest/replicate_idea.py`:

```python
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
```

In `tests/backtesting/instrument/test_date_literal_guard.py`, add to `ALLOW` (alphabetical, directly above `run_confluence_validation.py`):

```python
    "scripts/backtest/replicate_idea.py": "v238 replication ladder; its rung windows are frozen ladder.py constants, takes no --instrument",
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_replicate_idea.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/testrun.py file tests/backtesting/instrument/test_date_literal_guard.py`, `python scripts/dev/complexity_gate.py`, `python -m pytest tests/dev/test_suites.py -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/replicate_idea.py tests/backtest_scripts/test_replicate_idea.py tests/backtesting/instrument/test_date_literal_guard.py
git commit -m "feat(backtest): v238 replicate_idea -- refusals and rung 1 on the v1 screen"
```

### Task V238-15: replicate_idea: rungs 2–4 with per-ticker checkpoints

**Model:** opus — wires the orderable race and both bot adapters into a resumable per-ticker loop, and adds the crash marker that enforces one shot per rung.

**Files:**
- Modify: `scripts/backtest/replicate_idea.py` (imports; `run_rung`; new helpers below `_run_rung1`; `RunMarker`)
- Test: `tests/backtest_scripts/test_replicate_idea_rungs.py` (create; suite `backtest-scripts`)

**Interfaces:**
- Consumes: V238-14's `RungRun`, `read_events`, `_work`, `_events_path`, `_frame`, `_stress_bps`, `_tickers`, `_gap_totals`, `_sorted`, `_write_json`, `PROGRESS_EVERY`; `ladder_race.orderable_levels`, `race_levels`, `to_events` (V238-11); `ladder_bot.rung3_levels`, `clamp_would_drop`, `rung4_levels`, `ATTRITION`, `book_survival` (V238-12/13); `config.MAX_OPEN_POSITIONS` (account default 30).
- Produces (index ledger): `run_rung` branches for rungs 2, 3, 4; `_ticker_checkpoint(work_dir, rung, ticker) -> Path` (`<work-dir>/rung<N>/<TICKER>.json`). `RungRun` read-outs set here: rung 3 `clamp_share` (share of raced events whose bot stop the 2% price-distance cap would have dropped; sized down, never dropped); rung 4 `attrition` (`{name: count}` over `ladder_bot.ATTRITION`) and `survival` (`book_survival(events, max_open=config.MAX_OPEN_POSITIONS)`). `counters` gain `events_in`, `raced` and, at rung 3, `no_stop` (a bot stop that cannot be computed). Also `RunMarker(directory)` with `start() -> str | None`, `finish()`, `crash_note() -> str | None`, `RUNNING_FILE`, `CRASH_FILE` (the index ledger puts it in V238-14; it lands here, same file and signature, so V238-14 and V238-16 each fit 20 KB; V238-16 wires it into `main`).

Semantics (index "One rung per invocation", "Rung shapes"; Global Constraints "Long runs checkpoint per ticker"): rung N reads `<work-dir>/rung<N-1>-events.json` (the rung above's events; rung 2 races every rung 1 event), groups them by ticker, and per ticker loads the store frame once (`_frame`, cut at `READ_END`), finds each signal bar, takes the rung's levels (rung 2 `orderable_levels` on `indicators.atr(df)`; rung 3 `rung3_levels`; rung 4 `rung4_levels`, whose `reason` drops the event as attrition), races the kept events with `race_levels` at base and at `_stress_bps()` slippage, and writes one checkpoint `{"signals", "events", "reasons", "clamp"}`. A restart reuses a checkpoint only when its `signals` equal the current ticker's signal dates; any other checkpoint raises (it belongs to another run). Progress prints every `PROGRESS_EVERY` tickers with a percent. A `--tickers` smoke races only those tickers and (V238-14's `main`) writes no events file. **Run marker** (`<work-dir>/rung<N>/`, Global Constraints "One shot per id"): `start()` writes `running.json`; one left behind means that run crashed, so the first restart records `crash.json` and runs (the one re-run allowed), a second is refused; `finish()` removes `running.json`; `crash_note()` is the results-doc line.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest_scripts/test_replicate_idea_rungs.py`:

```python
"""v238 replicate_idea (V238-15): rungs 2-4 race the rung above's events, per ticker, resumably."""
import json

import pytest

import replicate_idea as ri  # on sys.path via conftest.py
import screen_idea

from swingbot.core.backtesting.screen import ladder, ladder_race
from swingbot.core.backtesting.screen.ideas import IDEAS
from swingbot.core.backtesting.screen.ladder import LadderEvent
from tests.backtest_scripts.test_replicate_idea import PASS_ROW, _args, _argv, _ladder_row, _ledger, _store

IDEA = IDEAS["turn_of_month"]            # fixed race, next-open entry, cap 4, long
POSITIONS = range(300, 1000, 35)         # 20 signal bars per ticker, all inside READ_END


def _upper(tmp_path, rung_above, tickers=("AAA", "BBB"), positions=POSITIONS):
    """A hand-made events file for the rung above (keys only matter to rungs 2-4)."""
    events = []
    for ticker in tickers:
        index = ri._frame(tmp_path / "store", ticker).index
        day = lambda p: index[p].strftime("%Y-%m-%d")  # noqa: E731
        events += [LadderEvent(ticker, day(p), day(p + 1), day(p + 4), 0.1, 0.1, "timeout",
                               r_null=0.0) for p in positions]
    ri.write_events(ri._events_path(tmp_path / "work", rung_above), events)
    return ri._sorted(events)


def _run(tmp_path, rung, *extra):
    return ri.run_rung(IDEA, rung, _args(tmp_path, "--dry-run", *extra, rung=rung),
                       out=lambda *_a, **_k: None)


def test_rung_two_races_every_rung_one_event_from_the_signal_close(tmp_path):
    _store(tmp_path)
    upper = _upper(tmp_path, 1)
    run = _run(tmp_path, 2)
    assert [e.key for e in run.events] == [e.key for e in upper]
    assert run.counters["events_in"] == run.counters["raced"] == len(upper)
    gaps = [e for e in run.events if e.outcome in ladder_race.GAP_OUTCOMES]
    assert (run.gap_count, run.gap_r) == (len(gaps), pytest.approx(sum(e.r for e in gaps)))
    assert all(e.r_stress is not None and e.r_stress <= e.r + 1e-12 for e in run.events)
    assert run.survival is None and run.clamp_share is None and run.attrition is None


def test_rung_two_checkpoints_each_ticker_and_resumes(tmp_path, monkeypatch):
    _store(tmp_path)
    _upper(tmp_path, 1)
    first = _run(tmp_path, 2)
    blob = json.loads(ri._ticker_checkpoint(tmp_path / "work", 2, "AAA").read_text(encoding="utf-8"))
    assert len(blob["signals"]) == len(POSITIONS) and blob["reasons"] == {}
    monkeypatch.setattr(ri, "_race_ticker", lambda *a, **k: pytest.fail("a finished ticker re-raced"))
    assert _run(tmp_path, 2).events == first.events


def test_a_checkpoint_from_other_events_is_refused(tmp_path):
    _store(tmp_path)
    _upper(tmp_path, 1)
    _run(tmp_path, 2)
    _upper(tmp_path, 1, positions=range(300, 1000, 70))
    with pytest.raises(RuntimeError, match="other rung 1 events"):
        _run(tmp_path, 2)


def test_a_signal_bar_missing_from_the_store_stops_the_run(tmp_path):
    _store(tmp_path, tickers=("AAA",))
    ri.write_events(ri._events_path(tmp_path / "work", 1), [LadderEvent(
        "AAA", "2017-03-04", "2017-03-06", "2017-03-09", 0.1, 0.1, "timeout")])   # a Saturday
    with pytest.raises(RuntimeError, match="not in the store frame"):
        _run(tmp_path, 2)


def test_rung_three_counts_no_stop_and_the_clamp_share(tmp_path, monkeypatch):
    _store(tmp_path, tickers=("AAA",))
    upper = _upper(tmp_path, 2, tickers=("AAA",))
    first = ri._frame(tmp_path / "store", "AAA").index.get_loc(upper[0].signal_date)

    def wide(df, pos, *, direction):            # 5% stops: sized down, never dropped
        close = float(df["Close"].iloc[pos])
        return (None, None) if pos == first else (close * 0.95, close * 1.10)

    monkeypatch.setattr(ri.ladder_bot, "rung3_levels", wide)
    run = _run(tmp_path, 3)
    assert run.counters["no_stop"] == 1 and run.counters["raced"] == len(upper) - 1
    assert run.clamp_share == pytest.approx(1.0)


def test_rung_three_live_adapter_keeps_every_event(tmp_path):
    _store(tmp_path, tickers=("AAA",))
    upper = _upper(tmp_path, 2, tickers=("AAA",))
    run = _run(tmp_path, 3)
    assert [e.key for e in run.events] == [e.key for e in upper]
    assert 0.0 <= run.clamp_share <= 1.0


def test_rung_four_reports_attrition_and_book_survival(tmp_path, monkeypatch):
    _store(tmp_path, tickers=("AAA",))
    upper = _upper(tmp_path, 3, tickers=("AAA",))
    index = ri._frame(tmp_path / "store", "AAA").index
    cut = {index.get_loc(upper[0].signal_date): "risk_cap",
           index.get_loc(upper[1].signal_date): "no_level_in_band"}

    def band(df, pos, *, direction):
        close = float(df["Close"].iloc[pos])
        if pos in cut:
            return close * 0.99, None, cut[pos]
        return close * 0.99, close * 1.02, None

    monkeypatch.setattr(ri.ladder_bot, "rung4_levels", band)
    run = _run(tmp_path, 4)
    assert run.attrition == {"no_level_in_band": 1, "risk_cap": 1}
    assert run.counters["raced"] == len(upper) - 2 == len(run.events)
    assert set(run.survival) == {"one_per_ticker_share", "concurrent_share",
                                 "signals_per_day_p95", "signals_per_day_max"}


def test_rung_four_live_adapter_accounts_for_every_event(tmp_path):
    _store(tmp_path, tickers=("AAA",))
    upper = _upper(tmp_path, 3, tickers=("AAA",), positions=range(300, 1000, 70))
    run = _run(tmp_path, 4)
    assert run.counters["raced"] + sum(run.attrition.values()) == len(upper)


def test_later_rungs_never_read_past_read_end(tmp_path, monkeypatch):
    _store(tmp_path)
    _upper(tmp_path, 1)
    ends, real = [], screen_idea.load_frame
    monkeypatch.setattr(screen_idea, "load_frame",
                        lambda path, start, end: ends.append(end) or real(path, start, end))
    _run(tmp_path, 2)
    assert ends and set(ends) == {ladder.READ_END}


def test_run_marker_allows_one_rerun_after_a_crash(tmp_path):
    directory = tmp_path / "rung1"
    first = ri.RunMarker(directory)
    assert first.start() is None and first.crash_note() is None
    again = ri.RunMarker(directory)                 # the first process died: running.json stays
    assert again.start() is None and "re-run once after a crash" in again.crash_note()
    crash = json.loads((directory / ri.CRASH_FILE).read_text(encoding="utf-8"))
    assert crash["crashed_run"]["started"]
    assert ri.RunMarker(directory).start().startswith("refused:")
    again.finish()
    assert not (directory / ri.RUNNING_FILE).exists()


def test_main_dry_run_rung_two_writes_its_events(tmp_path, capsys):
    _store(tmp_path)
    upper = _upper(tmp_path, 1)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW, _ladder_row(1, ladder.HOLD))
    assert ri.main(_argv(tmp_path, "--dry-run", rung=2)) == 0
    assert len(ri.read_events(tmp_path / "work" / "rung2-events.json")) == len(upper)
    assert "ladder-turn_of_month-r2 (dry run)" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_replicate_idea_rungs.py`
Expected: FAIL — `NotImplementedError: rungs 2-4 land with V238-15` and `AttributeError: ... has no attribute '_ticker_checkpoint'` / `'RunMarker'`.

- [ ] **Step 3: Implement rungs 2–4**

In `scripts/backtest/replicate_idea.py`, change the screen import line to:

```python
from swingbot.core.backtesting.screen import indicators, ladder, ladder_bot, ladder_race, race  # noqa: E402
```

Change `from datetime import date` to `from datetime import date, datetime, timezone`. Add below `_run_rung1`:

```python
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


def _run_later(idea, rung: int, args, out) -> RungRun:
    groups = _by_ticker(read_events(_events_path(_work(args), rung - 1)))
    wanted = _tickers(args)
    names = [t for t in groups if wanted is None or t in wanted]
    blobs = []
    for i, ticker in enumerate(names, start=1):
        blobs.append(_ticker_rung(idea, rung, ticker, groups[ticker], args))
        if i % PROGRESS_EVERY == 0 or i == len(names):
            out(f"[{idea.name}] rung {rung}: {i}/{len(names)} tickers "
                f"({100.0 * i / len(names):.0f}%)", flush=True)
    events = _sorted(ladder.LadderEvent(**row) for blob in blobs for row in blob["events"])
    reasons = sum((Counter(blob["reasons"]) for blob in blobs), Counter())
    counters = Counter(events_in=sum(len(blob["signals"]) for blob in blobs), raced=len(events))
    counters.update(reasons)
    return RungRun(events, counters, *_gap_totals(events),
                   **_readouts(rung, blobs, events, reasons))
```

Replace the body of `run_rung`:

```python
def run_rung(idea, rung: int, args, *, out=print) -> RungRun:
    """One rung's events and read-outs; nothing is published here."""
    if rung == 1:
        return _run_rung1(idea, args, out)
    return _run_later(idea, rung, args, out)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_replicate_idea_rungs.py`, then `python scripts/dev/testrun.py file tests/backtest_scripts/test_replicate_idea.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/complexity_gate.py` and `python -m pytest tests/dev/test_suites.py -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/replicate_idea.py tests/backtest_scripts/test_replicate_idea_rungs.py
git commit -m "feat(backtest): v238 replicate_idea rungs 2-4 -- orderable race, bot adapters, per-ticker checkpoints, crash marker"
```

### Task V238-16: replicate_idea: results docs, ledger row and next step

**Model:** sonnet — rendering and ledger plumbing over rules Part 4 and V238-15 already decide.

**Files:**
- Modify: `scripts/backtest/replicate_idea.py` (constants, `--watchlist`, publishing helpers, `main`)
- Test: `tests/backtest_scripts/test_replicate_idea_publish.py` (create; suite `backtest-scripts`)
- Modify: `tests/backtest_scripts/test_replicate_idea.py` (delete `test_a_real_run_waits_for_publishing`; this task replaces that refusal)

**Interfaces:**
- Consumes: V238-14/15's helpers and `RunMarker`; Part 4's `ladder` (`hold`, `paired_difference`, `input_row`, `next_step`, `NEXT_STEPS`, `BIASED_NULL_NOTE`) and `ladder_bot.BOT_SHAPE`; `stats.validate_ledger_row` / `append_ledger_row`; `screen_idea.record_path`.
- Produces (index ledger): `results_path`, `render_rung`, `ledger_row`, `publish`, and `--watchlist`. `render_rung` and `ledger_row` take one extra keyword, `input_instrument=None` (the governing screen row's instrument), so a `screen-v1` input is flagged in the doc and the row's `hypothesis` (the ledger has no description field; index ruling 2026-11-19).

Semantics beyond the code: the doc is written before the row (the ledger never points at a missing doc); rung 1 docs and rows always name the v1 null (index ruling 1); `main` starts the marker before a real run and finishes it after the row; a dry run keeps V238-14's summary line.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest_scripts/test_replicate_idea_publish.py`:

```python
"""v238 replicate_idea (V238-16): results docs, ledger rows, the run marker and the next step."""
from collections import Counter
from pathlib import Path

import pandas as pd

import replicate_idea as ri  # on sys.path via conftest.py

from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import ladder
from swingbot.core.backtesting.screen.ideas import IDEAS
from swingbot.core.backtesting.screen.ladder import LadderEvent
from tests.backtest_scripts.test_replicate_idea import PASS_ROW, _args, _argv, _ladder_row, _ledger, _store

IDEA = IDEAS["turn_of_month"]
DAY = pd.Timedelta(days=1)


def _events(r=0.5):
    """320 events: eight tickers on 40 Mondays, 2019-09 into 2020."""
    mondays = pd.date_range("2019-09-02", periods=40, freq="W-MON")
    return [LadderEvent(f"T{i}", d.strftime("%Y-%m-%d"), (d + DAY).strftime("%Y-%m-%d"),
                        (d + 3 * DAY).strftime("%Y-%m-%d"), r, r, "timeout", r_null=0.0,
                        r_stress=r - 0.01) for i in range(8) for d in mondays]


def _run(r=0.5, **readouts):
    return ri.RungRun(_events(r), Counter(raced=320), **readouts)


def test_results_path_names_the_rung():
    assert ri.results_path(Path("r"), "turn_of_month", 3, "2026-11-20").name == \
        "2026-11-20-ladder-turn_of_month-r3.md"


def test_ledger_row_is_valid_and_flags_the_v1_null():
    hold = ladder.hold(_events(), rung=1, n_resamples=500)
    row = ri.ledger_row(IDEA, 1, hold, Path("x.md"), "2026-11-20", input_instrument="screen-v1")
    stats.validate_ledger_row(row)
    assert (row["instrument"], row["data_source"], row["verdict"]) == ("ladder-v1", "alpaca", ladder.HOLD)
    assert (row["n"], row["exp_r"], row["p"]) == (320, 0.5, 0.0)
    assert ladder.BIASED_NULL_NOTE in row["hypothesis"] and "screen-v1 SCREEN-PASS" in row["hypothesis"]
    later = ri.ledger_row(IDEA, 2, ladder.hold(_events(), rung=2, n_resamples=500), Path("x.md"),
                          "2026-11-20", input_instrument="screen-v2")
    assert "biased" not in later["hypothesis"]


def test_rung_one_doc_prints_the_year_alone_the_null_and_the_disclaimers():
    hold = ladder.hold(_events(), rung=1, n_resamples=500)
    text = ri.render_rung(IDEA, 1, _run(), hold, watchlist={"n": 40, "mean": 0.5},
                          date="2026-11-20", input_instrument="screen-v1")
    for needle in (f"{ri.FINAL_YEAR} alone: N = ", ladder.BIASED_NULL_NOTE, "Input flag",
                   "Watchlist subset", "Not an independent replication", "Gap-through fills",
                   "2 x slippage", "LADDER-HOLD"):
        assert needle in text
    soup = ri.render_rung(IDEAS["turtle_soup"], 1, _run(), hold, date="2026-11-20")
    assert "-0.046R" in soup


def test_rung_three_and_four_docs_print_the_bot_shape_and_readouts():
    events = _events()
    hold = ladder.hold(events, rung=3, n_resamples=500)
    diff = ladder.paired_difference(events, events, n_resamples=200)
    three = ri.render_rung(IDEA, 3, _run(clamp_share=0.25), hold, diff=diff, date="2026-11-20")
    assert ri.ladder_bot.BOT_SHAPE["stop_entry_point"] in three and "25.0%" in three
    assert "Paired difference to the rung above" in three
    survival = {"one_per_ticker_share": 0.5, "concurrent_share": 0.4,
                "signals_per_day_p95": 8.0, "signals_per_day_max": 8}
    four = ri.render_rung(IDEA, 4, _run(attrition={"no_level_in_band": 3, "risk_cap": 1},
                                        survival=survival), hold, diff=diff, date="2026-11-20")
    assert "no_level_in_band 3, risk_cap 1" in four and "Book survival" in four


def test_publish_dry_run_prints_and_writes_nothing(tmp_path, capsys):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    (tmp_path / "watch.txt").write_text("T0\n", encoding="utf-8")
    assert ri.publish(_args(tmp_path, "--dry-run", "--watchlist", str(tmp_path / "watch.txt")),
                      IDEA, 1, _run()) == 0
    out = capsys.readouterr().out
    assert "# ladder-turn_of_month-r1" in out and ladder.NEXT_STEPS["pending"] in out
    assert "Watchlist subset (never gating): N = 40" in out and "3/3 members in the store" in out
    assert not (tmp_path / "results").exists()
    assert len(stats.load_ledger(tmp_path / "ledger.jsonl")) == 1


def test_publish_writes_the_doc_before_the_row(tmp_path, monkeypatch):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    doc = ri.results_path(tmp_path / "results", "turn_of_month", 1, "2026-11-20")
    seen, real = [], stats.append_ledger_row
    monkeypatch.setattr(ri.stats, "append_ledger_row",
                        lambda row, path: seen.append(doc.is_file()) or real(row, path=path))
    assert ri.publish(_args(tmp_path), IDEA, 1, _run()) == 0
    assert seen == [True]
    assert stats.load_ledger(tmp_path / "ledger.jsonl")[-1]["id"] == "ladder-turn_of_month-r1"


def test_a_failed_rung_one_closes_the_idea(tmp_path, capsys):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    ri.publish(_args(tmp_path, "--dry-run"), IDEA, 1, _run(r=-0.1))
    assert ladder.NEXT_STEPS["non_replication"] in capsys.readouterr().out


def test_rung_four_names_the_shape_from_its_difference_to_rung_two(tmp_path, capsys):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW, *(_ladder_row(r, ladder.HOLD) for r in (1, 2, 3)))
    for rung in (2, 3):
        ri.write_events(ri._events_path(tmp_path / "work", rung), _events(0.6))
    args = _args(tmp_path, "--dry-run", rung=4)
    assert ri.publish(args, IDEA, 4, _run(0.6)) == 0
    out = capsys.readouterr().out
    assert ladder.NEXT_STEPS["bot_shape"] in out and "Rung 4 minus rung 2 on 320 shared events" in out
    assert ri.publish(args, IDEA, 4, _run(0.4)) == 0           # holds, but wholly below rung 2
    assert ladder.NEXT_STEPS["orderable_shape"] in capsys.readouterr().out


def test_main_publishes_records_the_crash_and_spends_the_shot(tmp_path, monkeypatch, capsys):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    monkeypatch.setattr(ri, "run_rung", lambda idea, rung, args: _run())
    ri._write_json(tmp_path / "work" / "rung1" / ri.RUNNING_FILE, {"started": "earlier"})
    assert ri.main(_argv(tmp_path)) == 0
    doc = ri.results_path(tmp_path / "results", "turn_of_month", 1, "2026-11-20")
    assert "re-run once after a crash" in doc.read_text(encoding="utf-8")
    assert not (tmp_path / "work" / "rung1" / ri.RUNNING_FILE).exists()
    assert (tmp_path / "work" / "rung1-events.json").is_file()
    assert ri.main(_argv(tmp_path)) == 2
    assert "one shot per id" in capsys.readouterr().err
```

In `tests/backtest_scripts/test_replicate_idea.py`, delete `test_a_real_run_waits_for_publishing` (the whole function).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_replicate_idea_publish.py`
Expected: FAIL — `AttributeError: module 'replicate_idea' has no attribute 'results_path'`.

- [ ] **Step 3: Implement publishing**

In `scripts/backtest/replicate_idea.py`, below `_NO_SHOT` add:

```python
FINAL_YEAR = ladder.READ_END[:4]
PRIOR_READS = {"turtle_soup": (
    "a screen-style race on Alpaca 2018-2022 (watchlist) was already read at -0.046R in "
    "docs/superpowers/results/2026-10-23-v180-turtle-soup-result.md; this rung is not blind to it")}
```

In `build_parser`, above `--tickers`:

```python
    p.add_argument("--watchlist", type=Path, default=None,
                   help="tickers, one per line: rung 1 prints that subset, never gating")
```

Add below `_run_later`:

```python
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
```

Replace `main`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_replicate_idea_publish.py`, then for `test_replicate_idea.py` and `test_replicate_idea_rungs.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/complexity_gate.py` and `python -m pytest tests/dev/test_suites.py -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/replicate_idea.py tests/backtest_scripts/test_replicate_idea_publish.py tests/backtest_scripts/test_replicate_idea.py
git commit -m "feat(backtest): v238 replicate_idea publishes -- results doc, ladder ledger row, next step, crash marker"
```

### Task V238-17: Methodology, conventions, screen skill and Codex mirror

**Model:** sonnet — documentation of names and rules the earlier tasks already fixed, pinned by doc tests.

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (new `## Additive gate`; a ladder paragraph inside `## Funnel stages` Stage −2)
- Modify: `docs/claude/document-conventions.md` (the strategy-spec ladder-citation rule)
- Modify: `tests/hooks/test_doc_sections.py`
- Modify: `.claude/skills/screen/SKILL.md`; `.agents/skills/screen/SKILL.md` (regenerated by `python scripts/dev/sync_codex.py`, never hand-edited)
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes (final names, cited verbatim): V238-1 `frictions.net_r_legs`; V238-3 `provenance["r_basis"]`, `refused:r-basis`; V238-3b `measure_arms.py --r-basis`; V238-4..6b clause names, `ADDITIVE_GATE_MISUSE`, `refused:additive-mde`, disclosures; V238-7/8 `validate_component.py --gate additive`, `--expected-own-r`, `--expected-sd-r`, `--grid-arms`, `--knob`, `--folds-arms`; V238-9/10 `ladder-v1`, `LADDER-HOLD` / `LADDER-FAIL` / `LADDER-UNDERPOWERED`, `LADDER-UNAVAILABLE`, `ladder.INPUT_INSTRUMENTS`; V238-14..16 `scripts/backtest/replicate_idea.py --idea --rung --work-dir`, the `<work-dir>/rung<N>/` checkpoints and `crash.json`.
- Produces (index ledger): `## Additive gate` (after `## Harvest gate`, before `## Frozen constants`), opening `- **Additive-strategy gate (v238`; the paragraph `  **Replication ladder (v238` as the last paragraph of the Stage −2 bullet; the `**Ladder citation (v238).**` rule in `document-conventions.md`.

The spec owes the methodology section (`### Part C`, last line), the conventions rule ("What a ladder buys", last paragraph) and the screened-shape obligations (`### What a screened-shape strategy spec must state`); `## Testing` owes the doc tests and the Codex mirror in the same commit (Global Constraints "Codex mirror").

- [ ] **Step 1: Write the failing doc tests**

In `tests/hooks/test_doc_sections.py`, in `INSERTED["backtest-methodology.md"]`, insert between the `## Harvest gate` and `## Frozen constants` tuples:

```python
        ("## Additive gate", "- **Additive-strategy gate (v238"),
```

Append at the end of the file:

```python
def _section(doc: str, heading: str, next_heading: str) -> str:
    lines = _lines(doc)
    return "\n".join(lines[lines.index(heading):lines.index(next_heading)])


def test_the_ladder_paragraph_closes_the_stage_minus_two_bullet():
    lines = _lines("backtest-methodology.md")
    funnel, harvest = lines.index("## Funnel stages"), lines.index("## Harvest gate")
    stage = [i for i, line in enumerate(lines) if line.startswith(STAGE_MINUS_TWO)][0]
    acceptance = lines.index("- **The acceptance funnel.** Selection never touches scoring data, and two")
    ladder = [i for i, line in enumerate(lines) if line.startswith("  **Replication ladder (v238")]
    assert len(ladder) == 1 and funnel < stage < ladder[0] < acceptance < harvest
    body = "\n".join(lines[ladder[0]:acceptance])
    for token in ("scripts/backtest/replicate_idea.py", "ladder-v1", "LADDER-HOLD",
                  "LADDER-UNDERPOWERED", "LADDER-UNAVAILABLE", "v1 null", "signal close",
                  "one rung per", "2021"):
        assert token in body, token


def test_the_additive_gate_names_its_clauses_basis_and_refusals():
    text = _section("backtest-methodology.md", "## Additive gate", "## Frozen constants")
    for token in ("own_expectancy", "win_rate_above_breakeven", "book_net_gain", "stability",
                  "ADDITIVE_GATE_MISUSE", "refused:r-basis", "refused:additive-mde",
                  "frictions.net_r_legs", "--r-basis net", "--gate additive", "week",
                  "--expected-own-r", "--expected-sd-r", "--folds-arms"):
        assert token in text, token


def test_conventions_carry_the_ladder_citation_rule():
    text = (DOCS / "document-conventions.md").read_text(encoding="utf-8")
    rule = text[text.index("**Ladder citation (v238).**"):]
    rule = rule[:rule.index("\n\n")]
    for token in ("ladder-<name>-r<N>", "bot's shape", "orderable screened shape",
                  "market-on-open", "time-cap", "realised risk", "not a header line"):
        assert token in rule, token
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py`
Expected: FAIL — `ValueError: '## Additive gate' is not in list` and the three new tests.

- [ ] **Step 3: Write the docs**

In `docs/claude/backtest-methodology.md`, insert directly above the line `- **The acceptance funnel.** Selection never touches scoring data, and two` (so the paragraph closes the Stage −2 bullet, after its avoid-mode paragraph that ends `the unchanged funnel on the bot's own replay.`):

```markdown
  **Replication ladder (v238, `scripts/backtest/replicate_idea.py`, core
  `screen/ladder.py`, `ladder_race.py`, `ladder_bot.py`).** A screen pass
  is raced on one shape; the ladder changes one thing per rung, so a failure
  names its cause. Input: the idea's governing `SCREEN-PASS` row
  (`screen2-<name>` over `screen-<name>`, instrument in
  `ladder.INPUT_INSTRUMENTS`; a `screen-v1` input is flagged biased null,
  v230 placebo). One rung per `backtest-runner` dispatch
  (`--idea <name> --rung <N> --work-dir <dir>`), each a one-shot
  `ladder-<name>-r<N>` ledger row, instrument `ladder-v1`, data source
  alpaca. Rung 1 (robustness) re-races the screen's own trigger and shape
  through the v1 screen pipeline on the PIT S&P 500 Alpaca store, events
  2017-03-01..2020-12-31: a robustness check, not an independent
  replication (only the data source and 2020 are new; 2020 is printed
  alone). Rung 1 runs on the v1 null (v234 stop gate 2), whose known bias
  every rung 1 doc and row quotes. Rung 2 (orderable) anchors the same ATR
  stop and target on the **signal close**, so the alert can rest them as
  orders, entry still the next open; rung 3 swaps in the bot's stop (rung
  2's events, target distance in R held), rung 4 the bot's target band
  (1.5–2.5 R:R, no level means no trade); the stand-ins are recorded in
  `ladder_bot.BOT_SHAPE`. Hold rule, every rung: week-clustered lower 95%
  bound of net mean R > 0 with N ≥ 300 (`LADDER-HOLD`), N < 300
  `LADDER-UNDERPOWERED`, anything else `LADDER-FAIL`; rung 1 also needs a
  positive ΔExpR against the null. Rung N is refused without `LADDER-HOLD`
  on rung N−1; an idea whose context series is missing from the store is
  refused `LADDER-UNAVAILABLE` before any outcome is read (no row, no shot
  spent); rungs 2–4 need the fixed next-open shape. Gap fills are priced,
  never dropped; costs 5 bps a side plus commission (shorts: borrow), with
  2 × slippage printed beside, never gating. Runs checkpoint per ticker under
  `<work-dir>/rung<N>/`; a crashed run that wrote no result may be re-run
  once (`crash.json`). The ladder never reads 2021 or later. Outcome:
  rung 1 failing or underpowered closes the idea as a non-replication;
  rungs 1–4 holding with rung 4's paired difference to rung 2 not wholly
  below zero licenses a strategy spec in the bot's shape; rungs 1 and 2
  holding otherwise license the orderable screened shape (rung 2) at the 2%
  dollar-risk rule; rung 1 holding and rung 2 failing goes to the partner.
  The spec then cites its ladder rows (`document-conventions.md`, Ladder
  citation) and an added strategy is judged by `## Additive gate`.
```

In the same file, insert directly above the line `## Frozen constants` (with one blank line above and below the heading, as the other `##` headings):

```markdown
## Additive gate

- **Additive-strategy gate (v238, `swingbot/core/backtesting/acceptance_additive.py`,
  `validate_component.py --gate additive`).** For a component arm that only
  **adds rows** to the baseline (apart from displaced baseline rows); any
  other arm is refused `ADDITIVE_GATE_MISUSE` and belongs to v72 or v92.
  Own net ExpR is the objective. The book's pooled win rate is not a clause:
  a strategy adding rows at reward:risk 2 breaks even at 33%, lowers the
  pooled win rate while paying, and v180 died on that (−0.21pp pooled ΔWR).

  | # | Clause | Instrument | Threshold |
  |---|---|---|---|
  | 1 | `own_expectancy` (objective) | added rows' net ExpR, week-cluster bootstrap | lower 95% bound > 0 (one-sided p reported) |
  | 2 | `win_rate_above_breakeven` | added rows' decided win rate against their realised break-even `avg loss / (avg win + avg loss)` | lower 95% bound > break-even |
  | 3 | `book_net_gain` | paired change in the book's total R, strategy on vs off | point > 0 and lower 95% bound > −10% of the added rows' total R; `SKIPPED` when no baseline row is displaced |
  | 4 | `stability` | per-fold net ExpR of the added rows, folds 2021 / 2022 / 2023 | > 0 in ≥ 2 of 3, no fold below −0.10R, per-fold N ≥ 30 |

  Week clusters (10,000 resamples, seed 42), not ticker clusters: an added
  strategy's signals bunch on market days, so one bad week is one bet. A
  displaced row is a baseline key absent from the component arm; every
  other baseline row must be identical, and the results doc lists each
  displaced row (cause `not exposed by the replay` until the replay exposes
  one). **Both arms are net:** produce them with `measure_arms.py
  --r-basis net`, which books every row through `frictions.net_r_legs`
  (entry and exits slipped against the trade, one round-trip commission,
  shorts pay `frictions.borrow_r` over calendar days held, longs never) and
  stamps `provenance["r_basis"]`; `--gate additive` refuses a missing, gross
  or malformed stamp with `refused:r-basis` (under `--bespoke-instrument`
  too); no other gate reads the stamp, and the default booking stays gross
  and byte-identical. Stages: `reachability` (−1: stamp, basis, add-only
  split); `mde` (0: an MDE precheck against an effect frozen in the
  pre-registration, `--expected-own-r` = half the selected ladder rung's
  net mean R and `--expected-sd-r` = that rung's per-event SD, N = closed
  added rows, no R read; refused `refused:additive-mde`, budget intact);
  `selection` (1: clauses 1–3 per `--grid-arms` cell, the adopted cell the
  best own net ExpR among passing cells, `plateau_report()` printed with
  two or more cells, `--knob` naming the axis); `walkforward` (2: clause
  4); `validation` (3:
  one shot, all four, clause 4 from `--folds-arms`). Disclosures, never
  gating: maximum drawdown in R, longest losing streak, the five best
  weeks' share of total R, signals per day at p95 and maximum, and the
  same-week correlation with the baseline book. No geometry lock and no
  pooled win-rate clause; the badge threshold (`win_rate >= 50`) is
  untouched. Ledger verdicts are the funnel's `PASS` / `FAIL` / `NO-LIFT`.
```

In `docs/claude/document-conventions.md`, after the paragraph that ends `pass rule and its one-shot discipline: \`backtest-methodology.md\` § Stage −2.`, insert one blank line and:

```markdown
**Ladder citation (v238).** From v238's merge, a strategy spec whose
`Screen:` cites a `SCREEN-PASS` also cites, in its body, its
`ladder-<name>-r<N>` ledger rows and names the shape the ladder selected:
the bot's shape (rungs 1–4 hold and rung 4's paired difference to rung 2 is
not wholly below zero) or the orderable screened shape (rungs 1 and 2 hold).
A spec shipping the orderable screened shape also states the order set
placed at the alert (a market-on-open entry, a stop order and a limit target
at the alert's prices, the share count from the close-anchored risk, and the
broker's market-on-open cut-off); the time-cap exit (a closing order on
session `CAP` that the partner places or the bot pings, never a resting
order left to outlive the plan); that a `trail` idea is not shippable until
a nightly stop-update path exists; and the realised risk when the open gaps,
with its distribution. A documentation rule, not a header line
(`backtest-methodology.md` § Funnel stages, the replication ladder).
```

In `.claude/skills/screen/SKILL.md`, append at the end of the file:

```markdown

## After a pass

A `SCREEN-PASS` is not a strategy licence. Its next step is the replication ladder: `scripts/backtest/replicate_idea.py --idea <idea> --rung <N> --work-dir <dir>`, one rung per `backtest-runner` dispatch, in order (rung N is refused without `LADDER-HOLD` on rung N-1), each a one-shot `ladder-<idea>-r<N>` ledger row. A `screen-v1` pass is a valid input, flagged biased null. An idea whose context series is missing from the PIT store is refused `LADDER-UNAVAILABLE`, no shot spent. The strategy spec then cites its ladder rows and the shape selected (`document-conventions.md`, Ladder citation); an added strategy is judged by `validate_component.py --gate additive` (`backtest-methodology.md` § Additive gate).
```

In `AGENTS.md`, replace `` `preregistration-ledger.jsonl`. Clauses, thresholds and `` with (re-wrapping the paragraph at about 80 columns):

```markdown
`preregistration-ledger.jsonl`. A screen pass then runs the replication
ladder (`scripts/backtest/replicate_idea.py`, four one-shot
`ladder-<name>-r<N>` rungs, instrument `ladder-v1`, never reading 2021+)
before a strategy spec, which cites its ladder rows and the shape selected;
an added strategy is judged by `validate_component.py --gate additive` (own
net ExpR the objective, win rate above its own realised break-even, both
arms net and stamped `r_basis`). Clauses, thresholds and
```

Then regenerate the Codex skill copy:

Run: `python scripts/dev/sync_codex.py`
Expected: `.agents/skills/screen/SKILL.md` rewritten from the Claude skill; no other file changes (`git status --short` shows only the files listed above).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py`, then `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py` and `python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/doc_section.py docs/claude/backtest-methodology.md "## Additive gate"`
Expected: prints the new section only.

- [ ] **Step 5: Commit**

```bash
git add docs/claude/backtest-methodology.md docs/claude/document-conventions.md tests/hooks/test_doc_sections.py .claude/skills/screen/SKILL.md .agents/skills/screen/SKILL.md AGENTS.md
git commit -m "docs(v238): additive gate and replication ladder in the methodology, ladder citation rule, screen skill, Codex mirror"
```

