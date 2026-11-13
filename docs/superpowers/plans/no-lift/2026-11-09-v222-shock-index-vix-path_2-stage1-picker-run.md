# v222 — Market-shock detector: index + VIX entry path — Part 2: Stage 2 day picker, forward long-book, Stage 1 run and gate 1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`](../specs/2026-11-09-v222-shock-index-vix-path-design.md)
**Index:** [`2026-11-09-v222-shock-index-vix-path_0-index.md`](2026-11-09-v222-shock-index-vix-path_0-index.md) — Goal, Global Constraints, plan-time readings, Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks V222-4, V222-4b, V222-5: the frozen Stage 2 day picker (8 counted shock
days, 4 quiet slots, 4 near-miss days, reserves), the descriptive forward
long-book table, then the one Stage 1 run, its Results and gate 1. Nothing here
builds or reads an intraday replay, and nothing here edits the detector.

**Paths used in every task.**

```bash
M=E:/Documents/Private/Projects/Discord-Bot                                   # main tree
W=$M/.claude/worktrees/2026-11-09-v222-shock-index-vix-path                   # worktree (all code)
D=$M/data/v222                                                                 # stage data (gitignored, main tree)
```

`scripts/dev/testrun.py` resolves test paths against its own checkout, so
`python "$W/scripts/dev/testrun.py" file tests/...` runs the worktree's tests.
Never `cd`; use `git -C "$W"` and absolute paths.

# Phase 2 — Stage 2 day picker, forward long-book, Stage 1 run

### Task V222-4: Stage 2 day picker, part 1: frozen constants, A1 days, Alpaca date, quiet slots

**Model:** opus — the quiet-slot calendars (nearest-date ties, month roll-over, post-holiday and DST tests across the 2018 calendar seam) silently change which days decide the quiet gate if read loosely.

> Split at plan time (task over 20 KB): V222-4 holds the constants, the A1 and
> Alpaca readers and the quiet slots; **V222-4c** (after V222-4b) holds the shock
> ranking, the near-miss ranking, `stage2_days` and the report/CLI wiring. Both
> rows are in the index ledger.

**Files:**
- Modify: `scripts/backtest/shock_index_screen.py`
- Modify: `tests/backtest_scripts/test_shock_index_screen.py`

**Interfaces:**
- Consumes: `EPISODE_GAP`, `MOVE_COLUMNS` (V222-2); the module's `session` import (V222-3b); test-file names `sis`, `json`, `date`, `Path`, `pd`, `pytest` (V222-1b..V222-3b); `swingbot.core.market.session` (`NYSE_FIRST_DATE`, `nyse_calendar()` with `.sessions(start, end)`, `is_early_close`).
- Produces: `N_SHOCK = 8`, `N_QUIET = 4`, `N_NEAR = 4`, `RESERVE = 3`, `EXCLUDE = (date(2026, 11, 5),)`, `A1_DAYS_FILE = Path("tests/fixtures/shock_replay/validation_days.json")`, `A1_SHOCK_DAYS` (the six ISO days), `A1_FIXTURES = 26`, `QUIET_SLOTS = ("calendar", "calendar", "holiday", "dst")`, `NEG_CLASSES = ("calm", "rotation", "hard")`; `a1_fixture_days(path: Path) -> dict[str, list[date]]`; `first_alpaca_date(pit_spy: Path) -> date`; `_eligible(day: pd.Timestamp, alpaca_from: date) -> bool`; `quiet_days(moves, fires, ranked: list[date], sessions: pd.DatetimeIndex, *, alpaca_from: date = date.min) -> list[list[date]]`; test helpers `A1_SIX`, `_a1_file(tmp_path, shock=A1_SIX, n_calm=12)`, `_nyse(start, end)`, which V222-4c reuses.

**Rules pinned here (spec § Frozen "Stage 2 day list" and index § plan-time readings, copied).**
- *Quiet slots.* Candidates: scored sessions on or after the Alpaca date, 2026-11-05 excluded, with **no winner upper-bound fire within 5 sessions** (session-position distance `<= EPISODE_GAP`, the day itself included). Slots 1 and 2 (from counted shock days 1 and 2): next calendar month, same weekday, nearest the same day of month (clamped to the month's length); a month with no candidate rolls to the next month. Slot 3 (from shock day 3): nearest early-close (`session.is_early_close`) or post-holiday session; slot 4 (from shock day 4): nearest first session after a US DST change. "Nearest" for slots 3 and 4 = fewest calendar days from that slot's base-rule date (same day of month, next month), either direction, ties to the earlier date. Post-holiday = the previous session lies more than one weekday back (`np.busday_count` over the gap > 0), the previous session read from `session.nyse_calendar()` on or after `NYSE_FIRST_DATE` and from the scored session index before it. DST: the UTC offset of New York noon differs between a session and its previous session. A quiet pick is never reused by a later slot; each slot keeps `[pick, *up to RESERVE reserves]`. Fewer than 4 base days, or a slot with no candidate, raises `ValueError`: the frozen list is never shortened.
- *Alpaca date.* `first_alpaca_date` = the first data row of `data/market_data_pit/daily/SPY.csv` (2016-01-04 today); V222-5 writes it into Results before the list is drawn.
- *A1 days.* `a1_fixture_days` refuses a file whose shock class is not the six frozen days or whose total is not 26. The file is read, never edited. V222-4c drops every episode whose representative is any of the 26 days and lists the 20 non-shock days per class for the A1-days false-fire gate.

This task reads only daily bars the screen already reads; no intraday value of any candidate day is read (index § Data hygiene).

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtest_scripts/test_shock_index_screen.py`:

```python
from swingbot.core.market import session as mkt_session  # noqa: E402

A1_SIX = ["2024-08-05", "2024-12-18", "2025-03-10", "2025-04-04", "2025-04-21", "2025-10-10"]


def test_stage2_constants_are_the_spec_values():
    assert (sis.N_SHOCK, sis.N_QUIET, sis.N_NEAR, sis.RESERVE) == (8, 4, 4, 3)
    assert sis.EXCLUDE == (date(2026, 11, 5),)
    assert list(sis.A1_SHOCK_DAYS) == A1_SIX and sis.A1_FIXTURES == 26
    assert sis.QUIET_SLOTS == ("calendar", "calendar", "holiday", "dst")
    assert sis.A1_DAYS_FILE == Path("tests/fixtures/shock_replay/validation_days.json")


def _a1_file(tmp_path, shock=A1_SIX, n_calm=12):
    calm = [f"2023-01-{i + 2:02d}" for i in range(n_calm)]
    classes = {"shock": shock, "hard": ["2023-02-21"] * 4, "rotation": ["2023-07-20"] * 4,
               "calm": calm}
    path = tmp_path / "validation_days.json"
    path.write_text(json.dumps({"classes": classes, "days": {}}), encoding="utf-8")
    return path


def test_a1_fixture_days_reads_classes_and_refuses_drift(tmp_path):
    days = sis.a1_fixture_days(_a1_file(tmp_path))
    assert [d.isoformat() for d in days["shock"]] == A1_SIX
    assert sum(len(v) for v in days.values()) == 26
    with pytest.raises(ValueError, match="six frozen"):
        sis.a1_fixture_days(_a1_file(tmp_path, shock=A1_SIX[:5]))
    with pytest.raises(ValueError, match="26"):
        sis.a1_fixture_days(_a1_file(tmp_path, n_calm=11))


def test_first_alpaca_date_is_the_first_data_row(tmp_path):
    path = tmp_path / "SPY.csv"
    path.write_text("Date,Open,High,Low,Close,Volume\n2016-01-04,1,1,1,1,1\n"
                    "2016-01-05,1,1,1,1,1\n", encoding="utf-8")
    assert sis.first_alpaca_date(path) == date(2016, 1, 4)
    path.write_text("Date,Open,High,Low,Close,Volume\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no data row"):
        sis.first_alpaca_date(path)


def _nyse(start, end):
    return pd.DatetimeIndex(mkt_session.nyse_calendar().sessions(start, end), name="Date")


def test_calendar_helpers_post_holiday_and_dst():
    s = _nyse(date(2018, 1, 2), date(2019, 6, 28))
    assert sis._post_holiday(date(2018, 12, 6), s) is True       # after the 2018-12-05 closure
    assert sis._post_holiday(date(2018, 11, 26), s) is False     # a plain Monday
    assert sis._after_dst_change(date(2018, 11, 5), s) is True   # clocks moved 2018-11-04
    assert sis._after_dst_change(date(2018, 11, 6), s) is False
    old = pd.DatetimeIndex(["2017-06-30", "2017-07-03", "2017-07-05", "2017-07-06"])
    assert sis._post_holiday(date(2017, 7, 5), old) is True      # before NYSE_FIRST_DATE
    assert sis._post_holiday(date(2017, 7, 6), old) is False
    assert sis._month_target(date(2019, 1, 31), 1) == date(2019, 2, 28)


def test_quiet_slots_follow_the_frozen_rules():
    s = _nyse(date(2018, 1, 2), date(2019, 6, 28))
    moves = pd.DataFrame(0.0, index=s, columns=list(sis.MOVE_COLUMNS))
    fires = [pd.Timestamp(d) for d in
             ("2018-03-07", "2018-04-10", "2018-06-12", "2018-08-20", "2018-10-15")]
    ranked = [date(2018, 3, 7), date(2018, 6, 12), date(2018, 8, 20), date(2018, 10, 15)]
    slots = [[d.isoformat() for d in slot] for slot in sis.quiet_days(moves, fires, ranked, s)]
    # slot 1: April Wednesdays nearest 04-07; 04-04 and 04-11 sit within 5 sessions of the
    # 04-10 fire; the reserves roll into May (nearest 05-07)
    assert slots[0] == ["2018-04-18", "2018-04-25", "2018-05-09", "2018-05-02"]
    assert slots[1] == ["2018-07-10", "2018-07-17", "2018-07-03", "2018-07-24"]
    # slot 3: early-close or post-holiday nearest 2018-09-20 (2018-12-06 ties 07-05 at 77
    # days and loses to the earlier date)
    assert slots[2] == ["2018-09-04", "2018-11-23", "2018-07-05", "2018-12-06"]
    # slot 4: first session after a DST change nearest 2018-11-15; 2018-03-12 is 3
    # sessions from the 03-07 fire
    assert slots[3] == ["2018-11-05", "2019-03-11"]
    with pytest.raises(ValueError, match="4 counted shock days"):
        sis.quiet_days(moves, fires, ranked[:3], s)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_screen.py`
Expected: FAIL — `AttributeError: module 'shock_index_screen' has no attribute 'N_SHOCK'`.

- [ ] **Step 3: Implement the constants, the readers and the quiet slots**

In `scripts/backtest/shock_index_screen.py`, extend the imports: `import calendar` beside `import argparse`; the datetime line becomes `from datetime import date, datetime, time, timedelta, timezone`; add `from zoneinfo import ZoneInfo`; below the `sys.path` block add `import numpy as np  # noqa: E402` beside the pandas import. Then add after `descriptive_arms`:

```python
# Stage 2 day list (spec § Frozen "Stage 2 day list"; copied, never re-chosen).
N_SHOCK = 8                               # counted shock days (representative has no A1 fixture)
N_QUIET = 4                               # quiet slots from counted shock days 1-4
N_NEAR = 4                                # near-miss days
RESERVE = 3                               # replacements kept per ranking (unbuildable days)
EXCLUDE = (date(2026, 11, 5),)            # in-sample, decides nothing
A1_DAYS_FILE = Path("tests/fixtures/shock_replay/validation_days.json")
A1_SHOCK_DAYS = ("2024-08-05", "2024-12-18", "2025-03-10", "2025-04-04", "2025-04-21",
                 "2025-10-10")
A1_FIXTURES = 26
QUIET_SLOTS = ("calendar", "calendar", "holiday", "dst")
NEG_CLASSES = ("calm", "rotation", "hard")
NEW_YORK = ZoneInfo("America/New_York")


def a1_fixture_days(path: Path) -> dict[str, list[date]]:
    """Class -> sorted days of A1's frozen fixtures; refuses a list that drifted."""
    classes = json.loads(Path(path).read_text(encoding="utf-8"))["classes"]
    out = {c: sorted(date.fromisoformat(d) for d in days) for c, days in classes.items()}
    if [d.isoformat() for d in out.get("shock", [])] != list(A1_SHOCK_DAYS):
        raise ValueError("A1 shock fixtures differ from the six frozen days")
    if sum(len(days) for days in out.values()) != A1_FIXTURES:
        raise ValueError(f"A1 holds {A1_FIXTURES} fixtures; this file lists another count")
    return out


def first_alpaca_date(pit_spy: Path) -> date:
    """First row of the point-in-time Alpaca SPY daily file."""
    with open(pit_spy, encoding="utf-8") as fh:
        fh.readline()
        first = fh.readline().strip()
    if not first:
        raise ValueError(f"{pit_spy} has no data row")
    return date.fromisoformat(first.split(",")[0][:10])


def _eligible(day: pd.Timestamp, alpaca_from: date) -> bool:
    return day.date() >= alpaca_from and day.date() not in EXCLUDE


def _month_target(d: date, months: int) -> date:
    """Same day of the month `months` later, clamped to that month's length."""
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _prev_session(d: date, sessions: pd.DatetimeIndex) -> date | None:
    """NYSE calendar on or after NYSE_FIRST_DATE, else the SPY session index."""
    if d >= session.NYSE_FIRST_DATE:
        before = session.nyse_calendar().sessions(d - timedelta(days=14), d - timedelta(days=1))
        if before:
            return before[-1]
    pos = int(sessions.searchsorted(pd.Timestamp(d)))
    return sessions[pos - 1].date() if pos > 0 else None


def _post_holiday(d: date, sessions: pd.DatetimeIndex) -> bool:
    prev = _prev_session(d, sessions)
    return prev is not None and int(np.busday_count(prev + timedelta(days=1), d)) > 0


def _noon_offset(d: date):
    return datetime.combine(d, time(12), tzinfo=NEW_YORK).utcoffset()


def _after_dst_change(d: date, sessions: pd.DatetimeIndex) -> bool:
    prev = _prev_session(d, sessions)
    return prev is not None and _noon_offset(prev) != _noon_offset(d)


def _quiet_candidates(moves: pd.DataFrame, fires, alpaca_from: date) -> list[date]:
    """Scored sessions with no fire within EPISODE_GAP sessions (the day included)."""
    fire_pos = np.asarray(moves.index.get_indexer(pd.DatetimeIndex(fires)))
    out = []
    for pos, day in enumerate(moves.index):
        far = not len(fire_pos) or int(np.abs(fire_pos - pos).min()) > EPISODE_GAP
        if far and _eligible(day, alpaca_from):
            out.append(day.date())
    return out


def _calendar_order(base: date, cands: list[date]) -> list[date]:
    """Next month, same weekday, nearest the same day of month; empty months roll on."""
    out = []
    for months in range(1, 13):
        target = _month_target(base, months)
        month = [d for d in cands if (d.year, d.month) == (target.year, target.month)
                 and d.weekday() == base.weekday()]
        out += sorted(month, key=lambda d: (abs((d - target).days), d))
    return out


def _nearest_order(base: date, cands: list[date], keep) -> list[date]:
    target = _month_target(base, 1)
    return sorted((d for d in cands if keep(d)), key=lambda d: (abs((d - target).days), d))


def _slot_order(kind: str, base: date, cands: list[date],
                sessions: pd.DatetimeIndex) -> list[date]:
    if kind == "calendar":
        return _calendar_order(base, cands)
    if kind == "holiday":
        return _nearest_order(base, cands, lambda d: session.is_early_close(d)
                              or _post_holiday(d, sessions))
    return _nearest_order(base, cands, lambda d: _after_dst_change(d, sessions))


def quiet_days(moves: pd.DataFrame, fires, ranked: list[date], sessions: pd.DatetimeIndex, *,
               alpaca_from: date = date.min) -> list[list[date]]:
    """Four slots `[pick, *reserves]` from counted shock days 1-4; a pick is never reused."""
    if len(ranked) < N_QUIET:
        raise ValueError(f"quiet slots need {N_QUIET} counted shock days, got {len(ranked)}")
    cands = _quiet_candidates(moves, fires, alpaca_from)
    slots, used = [], set()
    for kind, base in zip(QUIET_SLOTS, ranked[:N_QUIET]):
        order = [d for d in _slot_order(kind, base, cands, sessions) if d not in used]
        if not order:
            raise ValueError(f"quiet slot {kind} for {base} has no candidate")
        used.add(order[0])
        slots.append(order[:1 + RESERVE])
    return slots
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_screen.py`
Expected: 41 passed (36 earlier + 5 new).

- [ ] **Step 5: Complexity check**

Run: `python "$W/scripts/dev/complexity_gate.py"`
Expected: no new offender (the largest new function, `a1_fixture_days`, scores 7).

- [ ] **Step 6: Commit**

```bash
git -C "$W" add scripts/backtest/shock_index_screen.py tests/backtest_scripts/test_shock_index_screen.py
git -C "$W" commit -m "feat(v222): shock_index_screen -- Stage 2 constants, A1/Alpaca readers, quiet slots"
```

Nothing here touches `data/v222/`; V222-5 runs Stage 1 once.

### Task V222-4b: Forward long-book: prod dump and descriptive forward table

**Model:** sonnet — a read-only dump modelled on `market_day_live_dump.py` and a small descriptive table over an existing bootstrap; nothing here decides a cell or a gate.

**Files:**
- Create: `scripts/reports/shock_longbook_dump.py`
- Create: `scripts/backtest/shock_index_forward.py`
- Create: `tests/scripts/test_shock_longbook_dump.py` (suite `tooling`)
- Create: `tests/backtest_scripts/test_shock_index_forward.py` (suite `backtest-scripts`)

**Interfaces:**
- Consumes: `swingbot.core.analytics.scope` (`closed_only(trades)`, `select(closed, BookScope)`, `BookScope(direction="bullish")`: default `ledger="main"`, `origin=None` = the regular lane); `swingbot.core.analytics.metrics.r_multiple(trade) -> float | None`; `swingbot.core.tracking.performance.TradeLog().get_trades(status=None, limit=None)` (prod only); `swingbot.core.backtesting.instrument.stats.week_cluster_bootstrap(baseline, component, statistic, *, n_resamples=10_000, seed=42) -> np.ndarray` (groups by each item's `entry_date` attribute, ISO week; drops `None` draws). The stage1.json shape of V222-3 (`winner: [k, v] | None`, `episodes: {"k,v": [[iso, ...], ...]}`), read from the file only, so this task has no code dependency on V222-3 and may run beside V222-1b..V222-4c.
- Produces: `shock_longbook_dump.longbook_record(trade: dict) -> dict | None` (`{"opened_at", "r"}`), `build_dump(trades) -> {"trades": [...]}`, `main()` (prints one JSON line); `shock_index_forward.HORIZONS = (1, 3, 5)`, `cell_key(k, v) -> str` (same text as `shock_index_screen.cell_key`), `open_session(opened_at: str) -> str`, `forward_longbook(episodes: list[list[str]], trades: list[dict], sessions: list[str], horizons=HORIZONS) -> list[dict]` (per horizon `horizon, n_trades, n_episodes, exp_r, total_r, ci_low, ci_high`), `render_md(rows, cell) -> str`, `main(argv=None) -> int` (CLI `--screen-json --longbook --data-dir --out-md`). V222-5 runs both on real data.

**Readings pinned here (index § plan-time readings "Forward long-book", copied).** Descriptive only: it decides no cell and no gate and is never cited for the release. Population: closed (`win`/`loss`/`closed`) `bullish` main-ledger regular-lane trades with an R and an open time. A trade's open session is the New York calendar date of `opened_at` (a naive timestamp reads as UTC). Horizon *h* covers the first *h* sessions of an episode, session 1 = the episode's first fire day, sessions read from `data/v222/SPY.csv`; episodes are at least 5 sessions apart, so the 1/3/5-session windows of two episodes never overlap. `n_episodes` counts episodes holding at least one such trade (N per episode beside N per trade: trades inside one episode are not independent). The 95 % interval is the 2.5/97.5 percentile of `week_cluster_bootstrap` with an empty baseline and the mean R as the statistic; no trades means no interval. The dump carries no ticker, size or price, writes nothing on the box and imports only modules production already runs (it is piped over ssh; the v222 branch is not deployed).

- [ ] **Step 1: Write the failing dump tests**

Create `tests/scripts/test_shock_longbook_dump.py`:

```python
"""v222: the read-only production long-book dump. No network, no DB."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "reports") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "reports"))

import shock_longbook_dump as dump  # noqa: E402


def _trade(**over):
    trade = {"id": "a" * 16, "ticker": "AAPL", "direction": "bullish", "status": "win",
             "entry": 100.0, "stop_loss": 95.0, "exit_price": 110.0,
             "opened_at": "2026-09-01T14:35:00+00:00", "closed_at": "2026-09-04T19:00:00+00:00",
             "strategies": ["RSI"]}
    return {**trade, **over}


def test_a_closed_bullish_main_regular_trade_keeps_only_time_and_r():
    record = dump.longbook_record(_trade())
    assert record == {"opened_at": "2026-09-01T14:35:00+00:00", "r": pytest.approx(2.0)}


@pytest.mark.parametrize("over", [
    {"direction": "bearish"},                 # shorts are not the long book
    {"ledger": "weak"},                       # weak ledger
    {"origin": "next_session"},               # a cohort, not the regular lane
    {"status": "open"},                       # not closed
    {"stop_loss": 100.0},                     # zero risk: no R
    {"opened_at": None},                      # no open time
])
def test_everything_else_is_dropped(over):
    assert dump.longbook_record(_trade(**over)) is None


def test_build_dump_is_one_json_object_without_tickers():
    out = dump.build_dump([_trade(), _trade(direction="bearish"), _trade(ledger="main")])
    assert len(out["trades"]) == 2
    assert "AAPL" not in json.dumps(out)
```

- [ ] **Step 2: Write the failing forward tests**

Create `tests/backtest_scripts/test_shock_index_forward.py`:

```python
"""v222 Stage 1: the descriptive forward long-book table."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import shock_index_forward as fwd  # noqa: E402

SESSIONS = [d.date().isoformat() for d in pd.bdate_range("2026-01-02", "2026-02-27")]
EPISODES = [["2026-01-07", "2026-01-08"], ["2026-02-02"]]
TRADES = [
    {"opened_at": "2026-01-07T15:00:00+00:00", "r": 1.0},    # episode 1, session 1
    {"opened_at": "2026-01-09T14:40:00+00:00", "r": -1.0},   # episode 1, session 3
    {"opened_at": "2026-01-13T15:00:00+00:00", "r": 2.0},    # episode 1, session 5
    {"opened_at": "2026-02-02T20:30:00+00:00", "r": 0.5},    # episode 2, session 1
    {"opened_at": "2026-02-03T02:00:00+00:00", "r": -0.5},   # 21:00 ET on 02-02: session 1
    {"opened_at": "2026-01-20T15:00:00+00:00", "r": 3.0},    # in no episode window
    {"opened_at": "2026-01-07T16:00:00+00:00", "r": None},   # no R: skipped
]


def test_horizons_and_key_are_frozen():
    assert fwd.HORIZONS == (1, 3, 5)
    assert fwd.cell_key(1.5, 20.0) == "1.5,20"


def test_open_session_is_the_new_york_date():
    assert fwd.open_session("2026-02-03T02:00:00+00:00") == "2026-02-02"
    assert fwd.open_session("2026-02-03T15:00:00") == "2026-02-03"     # naive reads as UTC


def test_forward_counts_trades_and_episodes_per_horizon():
    rows = {r["horizon"]: r for r in fwd.forward_longbook(EPISODES, TRADES, SESSIONS)}
    assert (rows[1]["n_trades"], rows[1]["n_episodes"]) == (3, 2)
    assert rows[1]["total_r"] == pytest.approx(1.0) and rows[1]["exp_r"] == pytest.approx(1 / 3)
    assert (rows[3]["n_trades"], rows[3]["total_r"], rows[3]["exp_r"]) == (4, 0.0, 0.0)
    assert (rows[5]["n_trades"], rows[5]["n_episodes"]) == (5, 2)
    assert rows[5]["exp_r"] == pytest.approx(0.4)
    for row in rows.values():
        assert row["ci_low"] <= row["exp_r"] <= row["ci_high"]


def test_no_trades_or_an_unknown_first_fire_gives_empty_rows():
    rows = fwd.forward_longbook([["2025-06-02"]], TRADES, SESSIONS)
    assert [(r["n_trades"], r["exp_r"], r["total_r"], r["ci_low"]) for r in rows] == \
        [(0, None, 0.0, None)] * 3


def test_cli_writes_the_table_and_says_no_lift_without_a_winner(tmp_path):
    pd.DataFrame({"Date": SESSIONS, "Close": 1.0}).to_csv(tmp_path / "SPY.csv", index=False)
    (tmp_path / "longbook.json").write_text(json.dumps({"trades": TRADES}), encoding="utf-8")
    screen = tmp_path / "stage1.json"
    screen.write_text(json.dumps({"winner": [1.5, 20.0], "episodes": {"1.5,20": EPISODES}}),
                      encoding="utf-8")
    out = tmp_path / "forward.md"
    argv = ["--screen-json", str(screen), "--longbook", str(tmp_path / "longbook.json"),
            "--data-dir", str(tmp_path), "--out-md", str(out)]
    assert fwd.main(argv) == 0
    md = out.read_text(encoding="utf-8")
    assert "Cell k = 1.5, v = 20" in md and "| 1 | 3 | 2 | +0.33 | +1.00 |" in md
    assert "never cited for the release" in md
    screen.write_text(json.dumps({"winner": None, "episodes": {}}), encoding="utf-8")
    assert fwd.main(argv) == 0
    assert "No winner (NO-LIFT)" in out.read_text(encoding="utf-8")
```

- [ ] **Step 3: Run both to see them fail**

Run: `python "$W/scripts/dev/testrun.py" file tests/scripts/test_shock_longbook_dump.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'shock_longbook_dump'`.
Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_forward.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'shock_index_forward'`.

- [ ] **Step 4: Implement the dump**

Create `scripts/reports/shock_longbook_dump.py`:

```python
#!/usr/bin/env python3
"""v222: dump the closed bullish main-ledger regular trades as ONE JSON line. Read-only.

Standalone on purpose: it imports only modules production already runs and is
piped over ssh (the v222 branch is not deployed)::

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" \
        < scripts/reports/shock_longbook_dump.py > data/v222/longbook.json

It writes nothing on the box and carries no ticker, size or price: only the
open time and the R each trade made, for the descriptive forward table of
scripts/backtest/shock_index_forward.py.
"""
from __future__ import annotations

import json


def longbook_record(trade: dict) -> dict | None:
    """{opened_at, r} for a closed bullish main-ledger regular trade, else None."""
    from swingbot.core.analytics import scope
    from swingbot.core.analytics.metrics import r_multiple
    kept = scope.select(scope.closed_only([trade]), scope.BookScope(direction="bullish"))
    r = r_multiple(trade) if kept else None
    if r is None or not trade.get("opened_at"):
        return None
    return {"opened_at": trade["opened_at"], "r": float(r)}


def build_dump(trades: list[dict]) -> dict:
    return {"trades": [rec for t in trades if (rec := longbook_record(t)) is not None]}


def main() -> None:
    from swingbot.core.tracking.performance import TradeLog
    print(json.dumps(build_dump(TradeLog().get_trades(status=None, limit=None))))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Implement the forward table**

Create `scripts/backtest/shock_index_forward.py`:

```python
#!/usr/bin/env python3
"""v222 Stage 1: the forward long-book table after the winner cell's episodes.

Descriptive only (spec § Stage 1): it decides no cell and no gate and is never
cited for the release. Closed bullish main-ledger regular trades (dumped from
production by scripts/reports/shock_longbook_dump.py) whose open session falls
in the first 1, 3 or 5 sessions of an episode (session 1 = first fire day).
N per trade and per episode, Total R beside ExpR, week-clustered bootstrap.

    python scripts/backtest/shock_index_forward.py --screen-json data/v222/stage1.json \
        --longbook data/v222/longbook.json --data-dir data/v222 --out-md data/v222/forward.md
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from swingbot.core.backtesting.instrument import stats  # noqa: E402

HORIZONS = (1, 3, 5)
MARKET_TZ = "America/New_York"


@dataclass(frozen=True)
class _Trade:
    entry_date: str          # ISO open session (ET); stats.group_by_week reads this name
    r: float


def cell_key(k: float, v: float) -> str:
    """Same text as shock_index_screen.cell_key (the stage1.json episodes key)."""
    return f"{k:g},{v:g}"


def open_session(opened_at: str) -> str:
    """New York calendar date of an ISO timestamp; a naive one reads as UTC."""
    ts = pd.Timestamp(opened_at)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(MARKET_TZ).date().isoformat()


def _mean_r(_baseline, component):
    return float(np.mean([t.r for t in component])) if component else None


def _window(episode: list[str], position: dict, sessions: list[str], horizon: int) -> set:
    start = position.get(episode[0])
    return set() if start is None else set(sessions[start:start + horizon])


def _row(horizon: int, inside: list[_Trade], n_episodes: int) -> dict:
    rs = [t.r for t in inside]
    draws = stats.week_cluster_bootstrap([], inside, _mean_r)
    low, high = ((float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))
                 if draws.size else (None, None))
    return {"horizon": horizon, "n_trades": len(rs), "n_episodes": n_episodes,
            "exp_r": float(np.mean(rs)) if rs else None, "total_r": float(sum(rs)),
            "ci_low": low, "ci_high": high}


def _opened(trades: list[dict]) -> list[_Trade]:
    return [_Trade(open_session(t["opened_at"]), float(t["r"])) for t in trades
            if t.get("r") is not None and t.get("opened_at")]


def _groups(episodes, position: dict, sessions: list[str], horizon: int,
            opened: list[_Trade]) -> list[list[_Trade]]:
    windows = [_window(ep, position, sessions, horizon) for ep in episodes]
    return [[t for t in opened if t.entry_date in w] for w in windows]


def forward_longbook(episodes: list[list[str]], trades: list[dict], sessions: list[str],
                     horizons=HORIZONS) -> list[dict]:
    """Per horizon: trades opened in the first `horizon` sessions of an episode."""
    position = {s: i for i, s in enumerate(sessions)}
    opened = _opened(trades)
    rows = []
    for horizon in horizons:
        groups = _groups(episodes, position, sessions, horizon, opened)
        inside = [t for group in groups for t in group]
        rows.append(_row(horizon, inside, sum(1 for group in groups if group)))
    return rows


def _fmt(x) -> str:
    return "-" if x is None else f"{x:+.2f}"


def render_md(rows: list[dict] | None, cell) -> str:
    head = ["# v222 Stage 1 — forward long-book (descriptive only)", "",
            "Decides no cell and no gate; never cited for the release. Trades inside one "
            "episode are not independent: read N per episode beside N per trade.", ""]
    if rows is None:
        return "\n".join(head + ["No winner (NO-LIFT): no forward table."]) + "\n"
    lines = head + [f"Cell k = {cell[0]:g}, v = {cell[1]:g}; closed bullish main-ledger "
                    "regular trades opened in the first N sessions of an episode.", "",
                    "| sessions | trades | episodes | ExpR | Total R | 95% CI (week bootstrap) |",
                    "|---|---|---|---|---|---|"]
    for r in rows:
        ci = "-" if r["ci_low"] is None else f"{_fmt(r['ci_low'])} .. {_fmt(r['ci_high'])}"
        lines.append(f"| {r['horizon']} | {r['n_trades']} | {r['n_episodes']} "
                     f"| {_fmt(r['exp_r'])} | {_fmt(r['total_r'])} | {ci} |")
    return "\n".join(lines) + "\n"


def _sessions(data_dir: Path) -> list[str]:
    dates = pd.read_csv(Path(data_dir) / "SPY.csv", usecols=["Date"])["Date"]
    return sorted(str(d)[:10] for d in dates)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="v222 forward long-book table (descriptive)")
    ap.add_argument("--screen-json", required=True, type=Path)
    ap.add_argument("--longbook", required=True, type=Path)
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--out-md", required=True, type=Path)
    args = ap.parse_args(argv)
    report = json.loads(args.screen_json.read_text(encoding="utf-8"))
    winner = report.get("winner")
    rows = None
    if winner:
        trades = json.loads(args.longbook.read_text(encoding="utf-8"))["trades"]
        rows = forward_longbook(report["episodes"][cell_key(*winner)], trades,
                                _sessions(args.data_dir))
    args.out_md.write_text(render_md(rows, winner), encoding="utf-8")
    print("forward table: " + ("no winner" if rows is None else f"{len(rows)} rows"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `python "$W/scripts/dev/testrun.py" file tests/scripts/test_shock_longbook_dump.py`
Expected: 8 passed.
Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_forward.py`
Expected: 5 passed.

- [ ] **Step 7: Complexity check**

Run: `python "$W/scripts/dev/complexity_gate.py"`
Expected: no new offender (`forward_longbook` scores 7).

- [ ] **Step 8: Commit (two scoped commits)**

```bash
git -C "$W" add scripts/reports/shock_longbook_dump.py tests/scripts/test_shock_longbook_dump.py
git -C "$W" commit -m "feat(v222): read-only prod dump of the closed bullish main-ledger long book"
git -C "$W" add scripts/backtest/shock_index_forward.py tests/backtest_scripts/test_shock_index_forward.py
git -C "$W" commit -m "feat(v222): descriptive forward long-book table after shock episodes"
```

Do **not** run the dump against production here: V222-5 runs it once, read-only.

### Task V222-4c: Stage 2 day picker, part 2: shock ranking, near-miss, `stage2_days`, report and CLI

**Model:** opus — the shock ranking and the A1 exclusion draw the counted population every Stage 2 gate is judged on; a wrong sort key, a representative chosen before the Alpaca restriction, or a silently shortened list changes the verdict.

> Second half of the V222-4 split (task over 20 KB); runs after V222-4 (same
> module and test file). V222-4b sits between them in id order only: its files
> are disjoint.

**Files:**
- Modify: `scripts/backtest/shock_index_screen.py`
- Modify: `tests/backtest_scripts/test_shock_index_screen.py`

**Interfaces:**
- Consumes: `ROOT` (V222-1b); `MOVE_COLUMNS`, `fire_days`, `representative` (V222-2); `upper_episodes`, `load`, `screen_grid`, `pick_winner`, `qualifying`, `prior_report`, `cell_json`, `cell_key`, `_isos`, `CELL_HEADER`, `_cell_row`, `_year_table`, `_verdict`, `BUDGET_PER_YEAR`, `EPISODE_GAP` (V222-2/V222-3); `descriptive_arms`, `_arms_md`, `_day_path` and the V222-3b forms of `build_report`, `render_md`, `_parser`, `main` (V222-3b); `N_SHOCK`, `N_NEAR`, `RESERVE`, `A1_DAYS_FILE`, `QUIET_SLOTS`, `NEG_CLASSES`, `a1_fixture_days`, `first_alpaca_date`, `_eligible`, `quiet_days` and test helpers `A1_SIX`, `_a1_file`, `_nyse` (V222-4).
- Produces: `rank_shock_days(moves, eps, *, alpaca_from: date, a1_days: set[date]) -> list[date]`; `near_miss_days(moves, k, v, counted: list[date], *, alpaca_from: date) -> list[date]`; `stage2_days(moves, winner, eps, *, a1_days: dict[str, list[date]], alpaca_from: date) -> dict` with exactly the ledger keys `cell, alpaca_from, shock, shock_reserve, quiet, quiet_reserve, near_miss, near_miss_reserve, a1_shock, a1_negative` (`a1_negative` keys `calm, rotation, hard`; every day an ISO string); `stage2_section(moves, winner, a1_days: Path | None, pit_spy: Path | None) -> dict | None`; `build_report(data_dir, vix_1m=None, a1_days: Path | None = None, pit_spy: Path | None = None)` adding key `stage2_days` (`None` without a winner or without `pit_spy`); CLI `--a1-days PATH` (default `ROOT / A1_DAYS_FILE`) and `--pit-spy PATH`; markdown section `## Stage 2 day list (frozen before any replay is built)` opening with `First Alpaca-buildable date: <iso>.` V222-5 writes `report["stage2_days"]` to `data/v222/stage2_days.json`; V222-7b, V222-7c and V222-8 read that dict.

**Rules pinned here (spec § Frozen "Stage 2 day list", copied).**
- *Population.* The winner cell's **upper-bound** episodes (`upper_episodes`). Each episode's sessions are restricted first (on or after the Alpaca date, 2026-11-05 excluded: `_eligible`); its representative is the restricted session with the largest upper-bound SPY drop in ATR (`representative`: min `spy_low_atr`, ties earlier). An episode with no restricted session drops out.
- *Counted shock days.* Representatives ranked deepest first (`spy_low_atr` ascending, ties earlier). An episode whose representative is **any** of the 26 A1 fixture days is dropped whole (spec: "whose representative session has no A1 validation fixture"); it is not replaced by another session of the same episode. The first 8 are counted, the next `RESERVE` are the replacements for unbuildable days, in order. The quiet slots are drawn from counted shock days 1-4 (V222-4's `quiet_days`) against every winner upper-bound fire.
- *Near-miss days.* Winner upper-bound fire sessions the close series did not fire, Alpaca-restricted, counted shock days excluded, ranked by the smallest close-to-close SPY drop in ATR first (`spy_close_atr` descending, ties earlier). First 4 counted, next `RESERVE` reserves.
- *Too few days.* Fewer than 8 counted shock days or fewer than 4 near-miss days raises `ValueError`: the frozen list is never shortened and no rule is relaxed. V222-5 puts that case to gate 1.
- *A1 lists.* `a1_shock` (the six, replayed and reported, never counted) and `a1_negative` (the 20 non-shock days per class, the A1-days false-fire gate) come straight from `a1_fixture_days`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtest_scripts/test_shock_index_screen.py`:

```python
def _picker_moves():
    """18 one-day events, six a year (every cell in budget); events 4, 9, 13 and 16
    are near misses (upper fires, close does not), the rest shocks with deeper lows."""
    idx = _nyse(date(2018, 1, 2), date(2020, 12, 31))
    moves = pd.DataFrame(0.0, index=idx, columns=list(sis.MOVE_COLUMNS))
    days = [idx[idx >= pd.Timestamp(y, mo, 15)][0]
            for y in (2018, 2019, 2020) for mo in (1, 3, 5, 7, 9, 11)]
    for i, day in enumerate(days):
        if i in (4, 9, 13, 16):
            moves.loc[day] = (-0.1 * (i % 5), -1.6, 0.0, 5.0, 30.0)
        else:
            moves.loc[day] = (-2.5, -2.0 - 0.1 * i, -0.5, 25.0, 30.0)
    return moves


def test_stage2_days_draws_the_frozen_list():
    moves = _picker_moves()
    a1 = {"shock": [date(2020, 11, 16)], "hard": [date(2023, 2, 21)], "rotation": [],
          "calm": []}
    out = sis.stage2_days(moves, (1.0, 10.0), sis.upper_episodes(moves, 1.0, 10.0),
                          a1_days=a1, alpaca_from=date(2018, 3, 1))
    assert out["cell"] == [1.0, 10.0] and out["alpaca_from"] == "2018-03-01"
    # 2018-01-16 is before alpaca_from; 2020-11-16 (deepest) has an A1 fixture
    assert out["shock"] == ["2020-07-15", "2020-05-15", "2020-01-15", "2019-11-15",
                            "2019-09-16", "2019-05-15", "2019-03-15", "2019-01-15"]
    assert out["shock_reserve"] == ["2018-11-15", "2018-07-16", "2018-05-15"]
    assert out["quiet"] == ["2020-08-12", "2020-06-12", "2020-02-18", "2019-11-04"]
    assert out["quiet_reserve"][2] == ["2020-01-02", "2019-12-26", "2019-12-24"]
    assert out["quiet_reserve"][3] == ["2020-11-02", "2018-11-05"]
    assert out["near_miss"] == ["2020-09-15", "2020-03-16", "2018-09-17", "2019-07-15"]
    assert out["near_miss_reserve"] == []
    assert out["a1_shock"] == ["2020-11-16"]
    assert out["a1_negative"] == {"calm": [], "rotation": [], "hard": ["2023-02-21"]}


def test_too_few_days_refuses_rather_than_shrinking_the_list():
    moves = _picker_moves()
    with pytest.raises(ValueError, match="counted shock"):
        sis.stage2_days(moves, (1.0, 10.0), sis.upper_episodes(moves, 1.0, 10.0),
                        a1_days={}, alpaca_from=date(2020, 1, 1))


def test_build_report_and_cli_write_the_stage2_list(tmp_path, monkeypatch):
    moves = _picker_moves()
    window = {"start": "2018-01-02", "end": "2020-12-31", "years": 3,
              "sessions": len(moves)}
    monkeypatch.setattr(sis, "load", lambda data_dir: (window, moves))
    pit = tmp_path / "pit_spy.csv"
    pit.write_text("Date,Open,High,Low,Close,Volume\n2018-03-01,1,1,1,1,1\n", encoding="utf-8")
    a1 = _a1_file(tmp_path)
    assert sis.build_report(tmp_path)["stage2_days"] is None            # no --pit-spy
    out_json, out_md = tmp_path / "s1.json", tmp_path / "s1.md"
    assert sis.main(["--data-dir", str(tmp_path), "--out-json", str(out_json),
                     "--out-md", str(out_md), "--a1-days", str(a1),
                     "--pit-spy", str(pit)]) == 0
    days = json.loads(out_json.read_text(encoding="utf-8"))["stage2_days"]
    assert days["cell"] == [1.0, 10.0] and days["shock"][0] == "2020-11-16"
    assert len(days["shock"]) == 8 and len(days["quiet"]) == 4 and len(days["near_miss"]) == 4
    assert days["a1_shock"] == A1_SIX
    md = out_md.read_text(encoding="utf-8")
    assert "First Alpaca-buildable date: 2018-03-01." in md
    assert "| quiet slot 4 (dst) |" in md and "| A1 calm (false-fire gate) |" in md
```

- [ ] **Step 2: Run them to see them fail**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_screen.py`
Expected: FAIL — `AttributeError: module 'shock_index_screen' has no attribute 'stage2_days'`.

- [ ] **Step 3: Implement the rankings and the list**

Add to `scripts/backtest/shock_index_screen.py` after `quiet_days`:

```python
def rank_shock_days(moves: pd.DataFrame, eps, *, alpaca_from: date,
                    a1_days: set[date]) -> list[date]:
    """Episode representatives (sessions restricted first), deepest upper-bound
    SPY move first, ties earlier; episodes whose representative has an A1
    fixture are dropped whole."""
    reps = []
    for ep in eps:
        kept = [d for d in ep if _eligible(d, alpaca_from)]
        if kept:
            reps.append(representative(kept, moves))
    reps.sort(key=lambda d: (moves.loc[d, "spy_low_atr"], d))
    return [d.date() for d in reps if d.date() not in a1_days]


def near_miss_days(moves: pd.DataFrame, k: float, v: float, counted: list[date], *,
                   alpaca_from: date) -> list[date]:
    """Upper-bound fires the close series missed, most recovered close first."""
    close = set(fire_days(moves, k, v, "close"))
    skip = set(counted)
    days = [d for d in fire_days(moves, k, v, "upper")
            if d not in close and _eligible(d, alpaca_from) and d.date() not in skip]
    days.sort(key=lambda d: (-moves.loc[d, "spy_close_atr"], d))
    return [d.date() for d in days]


def _iso_list(days) -> list[str]:
    return [d.isoformat() for d in days]


def _take(ranking: list[date], n: int, what: str) -> tuple[list[date], list[date]]:
    if len(ranking) < n:
        raise ValueError(f"only {len(ranking)} {what} days; the frozen list needs {n}")
    return ranking[:n], ranking[n:n + RESERVE]


def stage2_days(moves: pd.DataFrame, winner, eps, *, a1_days: dict[str, list[date]],
                alpaca_from: date) -> dict:
    """The frozen Stage 2 day list for the Stage 1 winner (spec § Frozen)."""
    k, v = winner
    every_a1 = {d for days in a1_days.values() for d in days}
    shock, shock_res = _take(rank_shock_days(moves, eps, alpaca_from=alpaca_from,
                                             a1_days=every_a1), N_SHOCK, "counted shock")
    slots = quiet_days(moves, fire_days(moves, k, v, "upper"), shock, moves.index,
                       alpaca_from=alpaca_from)
    near, near_res = _take(near_miss_days(moves, k, v, shock, alpaca_from=alpaca_from),
                           N_NEAR, "near-miss")
    return {"cell": [k, v], "alpaca_from": alpaca_from.isoformat(),
            "shock": _iso_list(shock), "shock_reserve": _iso_list(shock_res),
            "quiet": [slot[0].isoformat() for slot in slots],
            "quiet_reserve": [_iso_list(slot[1:]) for slot in slots],
            "near_miss": _iso_list(near), "near_miss_reserve": _iso_list(near_res),
            "a1_shock": _iso_list(a1_days.get("shock", [])),
            "a1_negative": {c: _iso_list(a1_days.get(c, [])) for c in NEG_CLASSES}}


def stage2_section(moves: pd.DataFrame, winner, a1_days: Path | None,
                   pit_spy: Path | None) -> dict | None:
    if winner is None or a1_days is None or pit_spy is None:
        return None
    return stage2_days(moves, tuple(winner), upper_episodes(moves, *winner),
                       a1_days=a1_fixture_days(a1_days), alpaca_from=first_alpaca_date(pit_spy))
```

- [ ] **Step 4: Wire the list into the report, the markdown and the CLI**

Replace `build_report`, `render_md`, `_parser` and `main` with the forms below (only the `stage2_days` lines, the `_stage2_md` call and the two flags are new) and add `_stage2_rows` and `_stage2_md` beside the other markdown helpers:

```python
def build_report(data_dir: Path, vix_1m: dict[str, Path] | None = None,
                 a1_days: Path | None = None, pit_spy: Path | None = None) -> dict:
    window, moves = load(data_dir)
    years = range(int(window["start"][:4]), int(window["end"][:4]) + 1)
    cells = screen_grid(moves, years)
    winner = pick_winner(cells)
    report = {"window": window, "scored_from": moves.index[0].date().isoformat(),
              "cells": [cell_json(c) for c in cells],
              "qualifying": [list(q) for q in qualifying(cells)],
              "winner": list(winner) if winner else None,
              "prior": prior_report(cells, winner),
              "episodes": {cell_key(c.k, c.v): _isos(upper_episodes(moves, c.k, c.v))
                           for c in cells}}
    report.update(descriptive_arms(moves, years, winner, vix_1m or {}))
    report["stage2_days"] = stage2_section(moves, winner, a1_days, pit_spy)
    return report


def _stage2_rows(days: dict) -> list[tuple[str, list[str], list[str]]]:
    rows = [("counted shock", days["shock"], days["shock_reserve"])]
    rows += [(f"quiet slot {i + 1} ({kind})", [pick], reserve) for i, (kind, pick, reserve)
             in enumerate(zip(QUIET_SLOTS, days["quiet"], days["quiet_reserve"]))]
    rows += [("near-miss", days["near_miss"], days["near_miss_reserve"]),
             ("A1 shock (replayed, reported, never counted)", days["a1_shock"], [])]
    rows += [(f"A1 {c} (false-fire gate)", isos, []) for c, isos in days["a1_negative"].items()]
    return rows


def _stage2_md(days: dict | None) -> list[str]:
    head = "## Stage 2 day list (frozen before any replay is built)"
    if not days:
        return [head, "", "Not drawn: no winner, or no `--pit-spy`."]
    lines = [head, "", f"First Alpaca-buildable date: {days['alpaca_from']}.",
             f"Cell: k = {days['cell'][0]:g}, v = {days['cell'][1]:g}. 2026-11-05 excluded.",
             "", "| role | days (rank order) | reserves (in order) |", "|---|---|---|"]
    lines += [f"| {role} | {', '.join(picks) or '-'} | {', '.join(res) or '-'} |"
              for role, picks, res in _stage2_rows(days)]
    return lines


def render_md(report: dict) -> str:
    w = report["window"]
    prior = {(r["k"], r["v"]): r for r in report["prior"]["cells"]}
    lines = ["# v222 Stage 1 — daily screen", "",
             f"Window {w['start']} to {w['end']} ({w['years']} calendar years, "
             f"{w['sessions']} sessions); scored from {report['scored_from']}. Budget: at most "
             f"{BUDGET_PER_YEAR} upper-bound episodes in every calendar year; episode gap "
             f"{EPISODE_GAP} sessions.", "", *CELL_HEADER]
    lines += [_cell_row(c, prior[(c["k"], c["v"])]) for c in report["cells"]]
    lines += ["", *_year_table(report["cells"]), "", *_verdict(report)]
    lines += ["", *_arms_md(report)]
    lines += ["", *_stage2_md(report.get("stage2_days"))]
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="v222 Stage 1 daily screen")
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-md", required=True, type=Path)
    ap.add_argument("--vix-1m", action="append", default=[], type=_day_path,
                    metavar="DAY=PATH", help="one-minute ^VIX CSV for a session (repeatable)")
    ap.add_argument("--a1-days", type=Path, default=ROOT / A1_DAYS_FILE,
                    help="A1 validation_days.json (read only)")
    ap.add_argument("--pit-spy", type=Path, default=None,
                    help="data/market_data_pit/daily/SPY.csv; without it no Stage 2 list")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_report(args.data_dir, vix_1m=dict(args.vix_1m), a1_days=args.a1_days,
                          pit_spy=args.pit_spy)
    args.out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.out_md.write_text(render_md(report), encoding="utf-8")
    print("winner: " + (cell_key(*report["winner"]) if report["winner"] else "NO-LIFT"))
    print("stage 2 list: " + ("drawn" if report["stage2_days"] else "not drawn"))
    return 0
```

`--a1-days` defaults to the A1 file inside the checkout running the script (read only); without `--pit-spy` no list is drawn, so the earlier CLI tests keep passing unchanged.

- [ ] **Step 5: Run the tests to see them pass**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_screen.py`
Expected: 44 passed (41 earlier + 3 new).

- [ ] **Step 6: Complexity check**

Run: `python "$W/scripts/dev/complexity_gate.py"`
Expected: no new offender (`rank_shock_days` scores 7, the rest less).

- [ ] **Step 7: Commit**

```bash
git -C "$W" add scripts/backtest/shock_index_screen.py tests/backtest_scripts/test_shock_index_screen.py
git -C "$W" commit -m "feat(v222): shock_index_screen -- frozen Stage 2 day list (8 shock, 4 quiet, 4 near-miss) in the report and CLI"
```

Do **not** run the CLI on `data/v222/` here: V222-5 runs Stage 1 once.


### Task V222-5: Run Stage 1, write Results, freeze the Stage 2 day list, gate 1

**Model:** sonnet — runs committed scripts once and copies their output into Results; no code. The **controller runs it in the main session**: gate 1 is an `AskUserQuestion`, which a subagent cannot ask, and the Results commits land on `main`.

**Files:**
- Modify: `docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md` (**main tree**, `## Results` § `### Stage 1 — screen` and § `### Stage 2 day list`; committed on `main` here, in separate commits)
- Outputs (main tree, gitignored): `data/v222/stage1.json`, `data/v222/stage1.md`, `data/v222/stage1.log`, `data/v222/stage2_days.json`, `data/v222/longbook.json`, `data/v222/forward.md`

**Interfaces:**
- Consumes: `data/v222/{SPY.csv,^VIX.csv,provenance.json}` and the Results window block (V222-1, V222-1b); the `shock_index_screen.py` CLI with `--vix-1m`, `--a1-days`, `--pit-spy`, and `first_alpaca_date` (V222-3b, V222-4, V222-4c); `shock_longbook_dump.py` and `shock_index_forward.py` (V222-4b); `tests/fixtures/vix_2026_11_05_1m.csv` (on `main`, `b253ef36`); `tests/fixtures/shock_replay/validation_days.json` (read only); `$M/data/market_data_pit/daily/SPY.csv` (gitignored, so read from the main tree); `bash "$M/scripts/ops/ssh-hetzner.sh"` (uncommitted, main tree; read-only production access is a standing permission).
- Produces: Results § Stage 1 (the window is already there; the 16-cell table on both series, per-year episodes, years over the cap against the prior, qualifying cells, the winner or **NO-LIFT**, SPY-only arm, gap/intraday and macro splits, VIX-high timing, the descriptive forward table); Results § Stage 2 day list (the first Alpaca-buildable date **committed first**, then the drawn list); `data/v222/stage2_days.json` = `report["stage2_days"]` (the dict V222-7b, V222-7c and V222-8 read); the gate 1 answer.

**Order is the rule here (spec § Frozen, index § Data hygiene).** The window is already in Results (V222-1b). The first Alpaca-buildable date is written and **committed on `main` before** the screen runs. The day list is committed in Results before any Stage 2 replay is built or any intraday value of a candidate day is read (V222-6d onward). Stage 1 runs **once**; it is never re-run to change a cell, a rule or the list, and no gate re-opens a frozen rule.

- [ ] **Step 1: Preconditions**

```bash
git -C "$W" log --oneline main..HEAD
ls "$D"
grep -n "^### Stage 1 — window\|^### Stage 1 — screen\|^### Stage 2 day list" "$M/docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md"
```

Expected: the worktree log holds the V222-1..V222-4c commits; `$D` lists `SPY.csv`, `^VIX.csv`, `provenance.json`; all three Results headings exist and the two later ones still read `Pending V222-5.` Anything else: stop and report.

Run the three narrow test files once (no full suite):

```bash
python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_screen.py
python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_forward.py
python "$W/scripts/dev/testrun.py" file tests/scripts/test_shock_longbook_dump.py
```

Expected: 44, 5 and 8 passed.

- [ ] **Step 2: Write down the first Alpaca-buildable date and commit it first**

```bash
python -c "import sys; sys.path.insert(0, r'$W/scripts/backtest'); import shock_index_screen as s; print(s.first_alpaca_date(r'$M/data/market_data_pit/daily/SPY.csv'))"
```

Expected: `2016-01-04` (record whatever the first row says). In the spec, replace the `Pending V222-5.` line under `### Stage 2 day list` with:

```markdown
- First Alpaca-buildable date (first row of `data/market_data_pit/daily/SPY.csv`,
  written before the list is drawn): <printed date>.
- List: pending (drawn by the Stage 1 run below).
```

```bash
git -C "$M" add docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md
git -C "$M" commit -m "docs(v222): results -- first Alpaca-buildable date, before the Stage 2 list"
```

- [ ] **Step 3: Run Stage 1 once**

```bash
python "$W/scripts/backtest/shock_index_screen.py" --data-dir "$D" \
  --out-json "$D/stage1.json" --out-md "$D/stage1.md" \
  --vix-1m "2026-11-05=$W/tests/fixtures/vix_2026_11_05_1m.csv" \
  --a1-days "$W/tests/fixtures/shock_replay/validation_days.json" \
  --pit-spy "$M/data/market_data_pit/daily/SPY.csv" > "$D/stage1.log" 2>&1
tail -3 "$D/stage1.log"
```

Expected, one of:
- `winner: <k>,<v>` and `stage 2 list: drawn` — carry on.
- `winner: NO-LIFT` and `stage 2 list: not drawn` — skip Steps 4 to 6.
- A `ValueError` traceback from the picker (`only N counted shock days; the frozen list needs 8`, the near-miss variant, or a quiet slot without a candidate): the frozen list cannot be drawn and is never shortened. Rerun the same command **without** `--pit-spy` (same outputs, the list simply not drawn) so Results still hold the screen, skip Steps 4 to 6, and put the case to gate 1 in Step 8.

- [ ] **Step 4: Freeze the day list file**

```bash
python -c "import json; r = json.load(open(r'$D/stage1.json', encoding='utf-8')); d = r['stage2_days']; d and json.dump(d, open(r'$D/stage2_days.json', 'w', encoding='utf-8'), indent=2); print('written' if d else 'no list')"
```

Expected: `written`. The file is the frozen list; nothing edits it afterwards (V222-8 copies it into `tests/fixtures/shock_replay_v222/days.json`).

- [ ] **Step 5: Dump the live long book (production, read-only)**

```bash
bash "$M/scripts/ops/ssh-hetzner.sh" "cd /opt/swing-bot && docker compose exec -T bot python -" \
  < "$W/scripts/reports/shock_longbook_dump.py" > "$D/longbook.json"
python -c "import json; print(len(json.load(open(r'$D/longbook.json', encoding='utf-8'))['trades']), 'trades')"
```

Expected: one JSON object and a trade count. It writes nothing on the box. A failure here (VM unreachable) does not block gate 1: Step 7 then writes `Not run: no winner, or the dump failed.` in place of the table.

- [ ] **Step 6: Forward long-book table (descriptive)**

```bash
python "$W/scripts/backtest/shock_index_forward.py" --screen-json "$D/stage1.json" \
  --longbook "$D/longbook.json" --data-dir "$D" --out-md "$D/forward.md"
```

Expected: `forward table: 3 rows`. Most episodes predate the live book, so N is small; that is the honest answer. It is descriptive only and never cited for the release.

- [ ] **Step 7: Write Results and commit**

Save this splice helper as `$D/splice_stage1.py` (gitignored; it only edits the spec's two pending blocks) and run it:

```python
"""v222 V222-5: splice stage1.md and forward.md into the spec's Results."""
import sys
from pathlib import Path

spec, stage1, forward = (Path(p) for p in sys.argv[1:4])
text = stage1.read_text(encoding="utf-8")
body, _, days = text.partition("## Stage 2 day list (frozen before any replay is built)")
body = "\n".join(l for l in body.split("\n") if not l.startswith("# v222 Stage 1")).strip()
body = body.replace("\n## ", "\n#### ")
if forward.exists():
    fwd = forward.read_text(encoding="utf-8").replace(
        "# v222 Stage 1 — forward long-book (descriptive only)",
        "#### Forward long-book (descriptive only)")
else:
    fwd = "#### Forward long-book (descriptive only)\n\nNot run: no winner, or the dump failed."
doc = spec.read_text(encoding="utf-8")
pending = "### Stage 1 — screen\n\nPending V222-5."
assert pending in doc, "Stage 1 heading is not pending"
doc = doc.replace(pending, "### Stage 1 — screen\n\n" + body + "\n\n" + fwd.strip())
list_line = "- List: pending (drawn by the Stage 1 run below)."
assert list_line in doc, "day-list line missing: Step 2 not done"
drawn = days.strip() or "Not drawn: no winner (NO-LIFT), or the frozen rule could not be met."
doc = doc.replace(list_line, "- Drawn by the Stage 1 run (`data/v222/stage2_days.json`):\n\n" + drawn)
spec.write_text(doc, encoding="utf-8")
print("results written")
```

```bash
python "$D/splice_stage1.py" "$M/docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md" "$D/stage1.md" "$D/forward.md"
grep -n "^### Stage 1 — screen" -A 90 "$M/docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md" | head -120
```

Check the spliced text once: the window line, 16 cell rows, the year table, the verdict line (`Winner: k = …` or `**NO-LIFT**`), the prior line, the three arms, the forward table, and under the day list the Alpaca date, 8 counted shock days, 4 quiet slots, 4 near-miss days, the six A1 shock days and the 20 A1 non-shock days. If the picker raised in Step 3, add one line under the day list: `Frozen rule not met: <the ValueError message>.`

```bash
git -C "$M" add docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md
git -C "$M" commit -m "docs(v222): results -- Stage 1 screen and the frozen Stage 2 day list"
git -C "$M" status --short
```

Expected: the commit lands; status shows nothing of v222 beyond plan files the controller has open.

- [ ] **Step 8: Gate 1 (partner, `AskUserQuestion`, one question, recommended option first)**

Ask exactly one question, matching the Step 3 outcome:
- **Winner and list drawn:** "Stage 1 picked k = <k>, v = <v> (Results § Stage 1); the Stage 2 day list is frozen in Results. Go on to Stage 2 with this cell only?" Options: **"Go on to Stage 2 (Recommended)"**: Stage 2 replays only this cell on the frozen list; **"Stop and close v222 as NO-LIFT"**: nothing ships.
- **NO-LIFT:** "Stage 1 found no in-budget cell whose every existing neighbour is in budget: NO-LIFT (Results § Stage 1). Close v222 to `no-lift/`?" Options: **"Close as NO-LIFT (Recommended)"**; **"Hold the plan open while I read Results"**.
- **Frozen list could not be drawn:** "Stage 1 picked k = <k>, v = <v>, but the frozen day rule yields <the ValueError message>; the list is never shortened. Close v222 as NO-LIFT?" Options: **"Close as NO-LIFT (Recommended)"**; **"Hold the plan open while I read Results"**.

No option changes a frozen rule, the grid, the budget, the winner rule or the list. Append the answer under the day list (`Gate 1 (<date>): <answer>.`) and commit it on `main` (`docs(v222): results -- gate 1`). Go on: Part 3 (V222-6d, V222-7..V222-8). NO-LIFT: the plan stops here; the controller closes it with `/close-out` to `no-lift/` and nothing is deployed.
