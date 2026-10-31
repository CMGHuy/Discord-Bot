# v184 — Stop-monitor liveness, part 1: measurement and core signals

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-21-v184-stop-monitor-liveness-design.md](../specs/2026-10-21-v184-stop-monitor-liveness-design.md)
**Index:** [2026-10-21-v184-stop-monitor-liveness_0-index.md](2026-10-21-v184-stop-monitor-liveness_0-index.md) holds the Goal, the Global Constraints, the Spec clarifications, the Contracts and the `## Parallelisation` table. Every task below obeys them.

This part covers tasks V184-1..V184-4: the worktree and the read-only `stops_unchecked` threshold measurement, the holiday- and half-day-aware NYSE regular-session helper, the per-tick fetch-failed flag, and the poll-demand accessor. All work happens in `.claude/worktrees/2026-10-21-v184-stop-monitor-liveness`. Every path below is relative to that worktree.

# Phase 1 — Measurement

### Task V184-1: Worktree, and the read-only stops_unchecked threshold measurement

**Model:** sonnet — read-only production queries plus a small local analysis script; the only judgement is applying a rule stated in advance.

**Files:**
- Create: `docs/superpowers/results/<run-date>-v184-stops-unchecked-threshold.md` (`<run-date>` is the day you run it, `YYYY-MM-DD`)
- Modify: `docs/superpowers/plans/2026-10-21-v184-stop-monitor-liveness_0-index.md` (one dated line under `## Threshold decision`)
- Scratch (not committed; `<scratchpad>` is your session scratchpad directory): `<scratchpad>/v184_rth_mix.sql`, `<scratchpad>/v184_rth_mix.csv`, `<scratchpad>/v184_monitor_failures.log`, `<scratchpad>/v184_runs.py`, `<scratchpad>/v184_index_line.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the worktree `.claude/worktrees/2026-10-21-v184-stop-monitor-liveness` on branch `2026-10-21-v184-stop-monitor-liveness`, and one dated line under the index's `## Threshold decision` that names the value of `STOPS_UNCHECKED_S`. V184-9 reads that line, and V184-11 refuses to merge without it.

**Why this task exists.** The spec (§ 2 Threshold) starts `stops_unchecked` at 600 s and requires a week of regular-session STOP_MONITOR evidence before the alert code merges. A 600 s threshold means ten consecutive 60 s ticks in which at least one responsible ticker went unpriced or a check raised. Before v184 there is no per-tick "unpriced" record, so this task bounds the base rate from the two read-only sources that do exist: the hourly `market_fetch_counts` rows for `asker = 'stop_monitor'`, and the bot's own log lines for a failed or timed-out monitor batch. The decision rule below is written down **before** the data is read. Do not change it after seeing the numbers.

**Production is read-only here.** Every remote command is a `SELECT`, a `docker compose logs` or a `grep`. Connect only through `bash scripts/ops/ssh-hetzner.sh` (CLAUDE.md). The wrapper expands `$(...)` locally, so none of the remote commands below contains one.

- [ ] **Step 1: Create the worktree**

Run this from the main checkout:

```bash
cd /e/Documents/Private/Projects/Discord-Bot
git worktree list | grep -F "2026-10-21-v184-stop-monitor-liveness" || \
  git worktree add .claude/worktrees/2026-10-21-v184-stop-monitor-liveness \
    -b 2026-10-21-v184-stop-monitor-liveness main
git -C .claude/worktrees/2026-10-21-v184-stop-monitor-liveness log --oneline -1
```

Expected: the last line shows the current `main` HEAD, and the worktree contains `docs/superpowers/plans/2026-10-21-v184-stop-monitor-liveness_0-index.md`. If the worktree already exists, reuse it (the resume rule) and do not create a second one. Every later step, and every later task, runs inside this worktree.

- [ ] **Step 2: Write the decision rule into the results doc before reading any data**

Create `docs/superpowers/results/<run-date>-v184-stops-unchecked-threshold.md` with this content. Fill in the date, and leave `## Data` and `## Verdict` empty for now:

```markdown
# v184 — stops_unchecked threshold measurement

**Plan:** [2026-10-21-v184-stop-monitor-liveness_0-index.md](../plans/2026-10-21-v184-stop-monitor-liveness_0-index.md) · Task V184-1
**Spec:** [2026-10-21-v184-stop-monitor-liveness-design.md](../specs/2026-10-21-v184-stop-monitor-liveness-design.md) § 2 Threshold
**Run:** <run-date>, read-only on production (Hetzner VM)

## Question

During the NYSE regular session, how often does the stop monitor go through a
stretch of consecutive 60 s ticks without pricing its book, for ordinary reasons?
A 600 s `stops_unchecked` threshold fires after ten such ticks in a row.

## Decision rule (written before the data was read)

Sources:
- (A) hourly `market_fetch_counts` rows with `asker = 'stop_monitor'` and
  `kind = 'quote'`, NYSE sessions only, ET hour buckets 09:00-15:59, over the last
  8 calendar days.
- (B) the bot's log lines for a failed or timed-out monitor quote batch, over the
  same 8 days (or the retained part of them), regular session only.

Definitions:
- `U` is the largest per-hour `failed / (all outcomes)` share in (A).
- A *run* is a sequence of monitor-batch failure lines in (B) that are at most
  90 s apart. Its length is `last - first + 60` seconds. A run of 1800 s or more
  is an *incident*, which is exactly what the alert is for: incidents are listed,
  not counted in `L`.
- `L` is the longest non-incident run, in seconds.

Verdict:
1. If `L < 300` and `U < 0.5`, keep `STOPS_UNCHECKED_S = 600`.
2. Otherwise let `T` be the smallest multiple of 300 that is `>= 2 * L`, raised to
   at least 900 when `U >= 0.5`. If `T <= 1800`, set `STOPS_UNCHECKED_S = T`.
3. If `T > 1800`, do not pick a value. Report to the controller, who asks the partner.
4. If either source covers fewer than 3 regular sessions, keep 600, mark the
   measurement *insufficient*, and name V184-12 (post-deploy) as the recheck. Once
   the `unquoted` field ships, it gives the per-tick answer directly.

Limits: (A) is hourly and does not say which ticker went unpriced, and a ticker
with no fresh print may not count as `failed`. (B) sees only whole-batch
failures. Neither source sees a single illiquid ticker that keeps the book
unclean on its own. The post-deploy check in V184-12 is where that becomes
visible.

## Data

## Verdict
```

- [ ] **Step 3: Query (A), the hourly outcome mix for the stop monitor during the regular session**

Write `<scratchpad>/v184_rth_mix.sql`:

```sql
WITH rows AS (
  SELECT (hour AT TIME ZONE 'America/New_York') AS hour_et, outcome, sum(n) AS n
  FROM market_fetch_counts
  WHERE asker = 'stop_monitor' AND kind = 'quote'
    AND hour >= now() - interval '8 days'
    AND extract(isodow FROM hour AT TIME ZONE 'America/New_York') < 6
    AND (hour AT TIME ZONE 'America/New_York')::time >= time '09:00'
    AND (hour AT TIME ZONE 'America/New_York')::time <  time '16:00'
  GROUP BY 1, 2
)
SELECT hour_et,
       sum(n) FILTER (WHERE outcome = 'failed')          AS failed,
       sum(n) FILTER (WHERE outcome = 'budget-deferred') AS deferred,
       sum(n)                                            AS total,
       round(coalesce(sum(n) FILTER (WHERE outcome = 'failed'), 0)::numeric
             / nullif(sum(n), 0), 4)                     AS failed_share
FROM rows
GROUP BY hour_et
ORDER BY hour_et;
```

Feed it to psql on stdin, which avoids nested quoting:

```bash
cd /e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -X -U swingbot -d swingbot -v ON_ERROR_STOP=1 -A -F ','" \
  < "<scratchpad>/v184_rth_mix.sql" > "<scratchpad>/v184_rth_mix.csv"
wc -l "<scratchpad>/v184_rth_mix.csv"
```

Expected: a header line, then one line per regular-session hour that had monitor traffic. The SQL already drops weekends; also drop any row whose ET date is in `swingbot.core.market.session.NYSE_HOLIDAYS`. Note that the 09:00 bucket includes the half hour before the open. In `## Data`, record the number of distinct ET dates covered, `U` (the largest `failed_share`) with its hour, and the total failed count against the total count.

- [ ] **Step 4: Source (B), the bot's monitor-batch failure lines**

```bash
cd /e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose logs --no-color --timestamps --since 192h bot 2>&1 | grep -E 'stop monitor: shared quote batch|plan manager: live-price batch|trade_monitor: live-price batch|trade_monitor: batch price fetch failed'" \
  > "<scratchpad>/v184_monitor_failures.log" || true
wc -l "<scratchpad>/v184_monitor_failures.log"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose logs --no-color --timestamps bot 2>&1 | head -n 1"
```

The grep patterns are the `_run_bounded` labels (`monitor_quotes` and `_legacy_price_batch` in `swingbot/core/planning/plan_manager.py`, `_legacy_live_price_batch` in `swingbot/commands/scanning/loops.py`) plus the `_live_price_batch` warning text. `_run_bounded` logs a line carrying the label only when the child raised or timed out (`swingbot/core/scanning/fetch.py`, swallowed key `scan.run_bounded`). The last command prints the oldest retained log line: record its date in `## Data` as the start of the log window, because log retention may be shorter than 8 days.

Then record the process-lifetime swallowed counters, read-only:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -X -U swingbot -d swingbot -tA -c \"SELECT doc->'swallowed' FROM bot_heartbeat WHERE key = 'bot'\""
```

In `## Data`, note the `scan.run_bounded` and `scan.loops.monitor_prices` counts and the `since` field.

- [ ] **Step 5: Compute the runs and L**

Write `<scratchpad>/v184_runs.py`. It only reads the scratch log; run it with the worktree on `sys.path`:

```python
"""Longest regular-session run of monitor-batch failures (V184-1, source B)."""
import datetime as dt
import re
import sys

from swingbot.core.market.session import NYSE_HOLIDAYS, RTH_OPEN, now_et, session_close

STAMP = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")
GAP_S = 90
INCIDENT_S = 1800


def _in_rth(ts: dt.datetime) -> bool:
    et = now_et(ts)
    d = et.date()
    return et.weekday() < 5 and d not in NYSE_HOLIDAYS and RTH_OPEN <= et.time() < session_close(d)


def _stamps(path: str) -> list:
    out = set()
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = STAMP.search(line)
            if not m:
                continue
            ts = dt.datetime.fromisoformat(m.group(1)).replace(tzinfo=dt.timezone.utc)
            if _in_rth(ts):
                out.add(ts)
    return sorted(out)


def _runs(stamps: list) -> list:
    runs, start, last = [], None, None
    for ts in stamps:
        if last is not None and (ts - last).total_seconds() <= GAP_S:
            last = ts
            continue
        if start is not None:
            runs.append((start, int((last - start).total_seconds()) + 60))
        start = last = ts
    if start is not None:
        runs.append((start, int((last - start).total_seconds()) + 60))
    return runs


def main(path: str) -> None:
    runs = _runs(_stamps(path))
    normal = [n for _, n in runs if n < INCIDENT_S]
    dates = sorted({now_et(s).date() for s, _ in runs})
    print(f"runs={len(runs)} incidents={len(runs) - len(normal)} rth_dates_with_failures={len(dates)}")
    print(f"L={max(normal, default=0)}")
    for start, n in sorted(runs, key=lambda r: -r[1])[:10]:
        print(f"{start.isoformat()} {n}s{' INCIDENT' if n >= INCIDENT_S else ''}")


if __name__ == "__main__":
    main(sys.argv[1])
```

Run it:

```bash
cd /e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness
PYTHONPATH=. python "<scratchpad>/v184_runs.py" "<scratchpad>/v184_monitor_failures.log"
```

Expected: `runs=…`, then `L=…`, then up to ten of the longest runs. An empty log prints `runs=0 …` and `L=0`. Copy the output into `## Data`.

- [ ] **Step 6: Apply the rule and write the verdict**

Apply the Step 2 rule to `U`, `L` and the session counts without changing it. Write `## Verdict` in three to six lines: which case applied (1-4), the chosen `STOPS_UNCHECKED_S`, any incidents (date and length), and one sentence on what V184-12 should recheck. If case 3 applies, stop here, leave the index alone, and report `BLOCKED: T=<value>s exceeds 1800 s; the partner must choose the threshold` to the controller.

- [ ] **Step 7: Record the threshold line in the index**

Insert exactly one dated line at the end of `## Threshold decision`, just before `## Contracts`. Use a script so the rest of the index stays untouched. Write `<scratchpad>/v184_index_line.py`, putting your own values in `LINE`. This example is for case 1:

```python
import pathlib
import sys

INDEX = pathlib.Path("docs/superpowers/plans/2026-10-21-v184-stop-monitor-liveness_0-index.md")
LINE = ("- **<run-date>:** kept `STOPS_UNCHECKED_S=600` (case 1: L=<L>s, U=<U>, <k> sessions; "
        "[results](../results/<run-date>-v184-stops-unchecked-threshold.md)).\n\n")
MARKER = "## Contracts\n"

text = INDEX.read_text(encoding="utf-8")
section = text.split("## Threshold decision", 1)[1].split(MARKER, 1)[0]
if text.count(MARKER) != 1 or "STOPS_UNCHECKED_S=" in section:
    sys.exit("index already carries a threshold line, or its layout changed")
INDEX.write_text(text.replace(MARKER, LINE + MARKER, 1), encoding="utf-8", newline="\n")
```

For case 2 the line reads ``set `STOPS_UNCHECKED_S=<T>` (case 2: …)``. For case 4 it reads ``kept `STOPS_UNCHECKED_S=600` (case 4, insufficient: …; recheck in V184-12)``.

```bash
cd /e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness
python "<scratchpad>/v184_index_line.py"
grep -n "STOPS_UNCHECKED_S=" docs/superpowers/plans/2026-10-21-v184-stop-monitor-liveness_0-index.md
git status --short
```

Expected: the grep lists the pre-existing Global Constraints and Contracts mentions plus exactly one new dated line (it starts with `- **<run-date>:**`) inside `## Threshold decision`, and `git status` shows only the index and the new results doc.

- [ ] **Step 8: Commit on the worktree branch**

```bash
cd /e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness
git add docs/superpowers/results/*-v184-stops-unchecked-threshold.md docs/superpowers/plans/2026-10-21-v184-stop-monitor-liveness_0-index.md
git commit -m "docs(v184): stops_unchecked threshold measured on a week of regular sessions"
```

# Phase 2 — Core signals

### Task V184-2: Holiday- and half-day-aware NYSE regular-session helper

**Model:** sonnet — a small pure function, but calendar edge cases (holidays, half-days, the weekday test the spec formula omits) need care.

**Files:**
- Modify: `swingbot/core/market/session.py` (new function placed directly after `session_close`, which sits at about line 229)
- Create: `tests/market/test_session_nyse_regular.py` (suite `market-data`; `tests/market/` is already in `tests/suites.toml`, so no suites edit)

**Interfaces:**
- Consumes: existing `now_et`, `RTH_OPEN`, `NYSE_HOLIDAYS`, `session_close` in `swingbot/core/market/session.py` (verified: lines 30, 19, 126, 229).
- Produces: `is_nyse_regular_session(now: dt.datetime | None = None) -> bool`. V184-6 calls it to set the `monitor` doc's `market_open` field.

**Why.** The spec's `market_open` is the NYSE regular session at `tick_at`, holiday- and half-day-aware. `is_regular_session` ignores holidays and half-days, and `bot_core.in_session` is the Berlin scan window, so neither fits. The spec's formula (`d not in NYSE_HOLIDAYS and RTH_OPEN <= t < session_close(d)`) has no weekday test, and `NYSE_HOLIDAYS` holds no weekends, so a Saturday at 10:00 ET would read as open. Spec clarification 3 adds the weekday test.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_session_nyse_regular.py`:

```python
"""v184: is_nyse_regular_session -- the NYSE regular session, holiday- and
half-day-aware, which the monitor stamp's market_open field reads."""
import datetime as dt

import pytest

from swingbot.core.market import session
from swingbot.core.market.session import US_MARKET_TZ, is_nyse_regular_session


def _et(y, m, d, hh, mm, ss=0):
    return dt.datetime(y, m, d, hh, mm, ss, tzinfo=US_MARKET_TZ)


@pytest.mark.parametrize("when, expected", [
    (_et(2026, 10, 21, 10, 0), True),        # ordinary Wednesday
    (_et(2026, 10, 21, 9, 29, 59), False),   # one second before the open
    (_et(2026, 10, 21, 9, 30), True),        # the open is inclusive
    (_et(2026, 10, 21, 15, 59, 59), True),
    (_et(2026, 10, 21, 16, 0), False),       # the close is exclusive
    (_et(2026, 10, 21, 20, 0), False),       # after hours
])
def test_ordinary_weekday_follows_rth(when, expected):
    assert is_nyse_regular_session(when) is expected


def test_weekend_is_closed_even_inside_rth_hours():
    # NYSE_HOLIDAYS holds no weekends: without the weekday test this read open.
    assert is_nyse_regular_session(_et(2026, 10, 24, 11, 0)) is False   # Saturday
    assert is_nyse_regular_session(_et(2026, 10, 25, 11, 0)) is False   # Sunday


def test_full_day_holiday_is_closed():
    thanksgiving = _et(2026, 11, 26, 11, 0)
    assert dt.date(2026, 11, 26) in session.NYSE_HOLIDAYS
    assert is_nyse_regular_session(thanksgiving) is False
    # The pre-existing helper ignores holidays; that is why this one exists.
    assert session.is_regular_session(thanksgiving) is True


@pytest.mark.parametrize("when, expected", [
    (_et(2026, 11, 27, 12, 59, 59), True),   # day after Thanksgiving, before 13:00
    (_et(2026, 11, 27, 13, 0), False),       # half-day close is exclusive
    (_et(2026, 11, 27, 14, 30), False),      # after the half-day close, before 16:00
    (_et(2026, 12, 24, 13, 30), False),      # Christmas Eve (a Thursday in 2026)
])
def test_half_day_closes_at_one_pm(when, expected):
    assert is_nyse_regular_session(when) is expected


def test_utc_input_is_converted_to_new_york_time():
    # 13:30 UTC on 2026-10-21 is 09:30 EDT.
    open_utc = dt.datetime(2026, 10, 21, 13, 30, tzinfo=dt.timezone.utc)
    assert is_nyse_regular_session(open_utc) is True
    assert is_nyse_regular_session(open_utc - dt.timedelta(seconds=1)) is False


def test_naive_input_is_read_as_new_york_wall_clock():
    assert is_nyse_regular_session(dt.datetime(2026, 10, 21, 10, 0)) is True


def test_default_reads_the_clock(monkeypatch):
    monkeypatch.setattr(session, "now_et",
                        lambda now=None: _et(2026, 11, 26, 11, 0) if now is None else now)
    assert is_nyse_regular_session() is False
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness
python scripts/dev/testrun.py file tests/market/test_session_nyse_regular.py
```

Expected: collection error, `ImportError: cannot import name 'is_nyse_regular_session'`.

- [ ] **Step 3: Write the implementation**

In `swingbot/core/market/session.py`, insert directly after `def session_close(d: dt.date) -> dt.time:` and its body (before `@functools.lru_cache(maxsize=1)` / `def nyse_calendar()`):

```python
def is_nyse_regular_session(now: dt.datetime | None = None) -> bool:
    """NYSE regular session at ``now``: a weekday, not in NYSE_HOLIDAYS, and
    RTH_OPEN <= t < session_close(d) in ET. Holiday- and half-day-aware,
    unlike is_regular_session (and unlike bot_core.in_session, the Berlin
    scan window). v184: the stop-monitor stamp's ``market_open``."""
    et = now_et(now)
    d = et.date()
    if et.weekday() >= 5 or d in NYSE_HOLIDAYS:
        return False
    return RTH_OPEN <= et.time() < session_close(d)
```

`now_et` is looked up through the module globals at call time, which is what `test_default_reads_the_clock` patches.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness
python scripts/dev/testrun.py file tests/market/test_session_nyse_regular.py
python scripts/dev/testrun.py file tests/market/test_session.py
python scripts/dev/complexity_gate.py
```

Expected: both files `0 failed`, `0 xfailed`; the gate exits 0.

- [ ] **Step 5: Commit**

```bash
cd /e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness
git add swingbot/core/market/session.py tests/market/test_session_nyse_regular.py
git commit -m "feat(v184): holiday- and half-day-aware NYSE regular-session helper"
```

### Task V184-3: Per-tick fetch-failed flag out of the bounded quote batch

**Model:** sonnet — small edits in four existing functions across two modules; the trap is keeping every return value byte-identical while surfacing the swallowed `None`.

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (new module-level flag and three functions beside `_MANAGER` at about line 1501; `_legacy_price_batch` at about line 1512; `monitor_quotes` at about line 1552)
- Modify: `swingbot/commands/scanning/loops.py` (`_live_price_batch` at about line 573, `_legacy_live_price_batch` at about line 591)
- Create: `tests/planning/test_monitor_batch_status.py` (suite `planning`; `tests/planning/` is already listed in `tests/suites.toml`)

**Interfaces:**
- Consumes: existing `fetch._run_bounded(fn, args, timeout_seconds, label)`, which returns `None` when the child raised or timed out (`swingbot/core/scanning/fetch.py:184`); existing `plan_manager.monitor_quotes`, `plan_manager._legacy_price_batch`, `loops._live_price_batch`, `loops._legacy_live_price_batch` (all verified in the brief).
- Produces, in `swingbot/core/planning/plan_manager.py`:
  - `_MONITOR_BATCH: dict[str, bool] = {"failed": False}`
  - `reset_monitor_batch_status() -> None` — sets `failed` to False. V184-7's `_monitor_tick` calls it first thing each tick; this task does **not** wire it into `trade_monitor`.
  - `mark_monitor_batch_failed() -> None` — sets `failed` to True, sticky until the next reset.
  - `monitor_batch_failed() -> bool`
  V184-7 reads `monitor_batch_failed()` into `TickRecord.fetch_failed`.

**Why.** Spec § 1 `fetch_failed` must say "the shared quote batch failed or timed out" as distinct from "no fresh print". Today both come back as `{}`: `monitor_quotes` does `if not out: return {}`, `_legacy_price_batch` and `_legacy_live_price_batch` do `... or {}`, and `_live_price_batch` swallows an exception into `{}`. Spec clarification 2 chooses a module-level sticky flag, so no return type changes and no caller changes shape. One tick can make two batch calls (trade tickers through `_live_price_batch`, then plan tickers through `poll()` → `_price_batch_fn` → `monitor_quotes`, normally served from the 15 s shared cache); either failing marks the tick. An empty but successful result does **not** set the flag.

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_monitor_batch_status.py`:

```python
"""v184: the per-tick fetch-failed flag. A failed or timed-out bounded quote batch
(_run_bounded returned None, or the call raised) marks the tick; an empty but
successful batch does not. Return values are unchanged."""
import asyncio

import pytest

from swingbot import config
from swingbot.commands.scanning import loops
from swingbot.core.marketdata.shared.kinds import QuoteDetail
from swingbot.core.planning import plan_manager as pm
from swingbot.core.scanning import fetch


@pytest.fixture(autouse=True)
def _clear_flag():
    pm.reset_monitor_batch_status()
    yield
    pm.reset_monitor_batch_status()


def _quiet_counters(monkeypatch):
    from swingbot.core.marketdata.shared import counters
    monkeypatch.setattr(counters, "merge", lambda rows: None)
    monkeypatch.setattr(counters, "flush", lambda **k: 0)


def _q(price=190.0):
    return QuoteDetail(symbol="AAPL", price=price, trade_at=None, bid=None, ask=None,
                       quote_at=None, source="alpaca-iex")


# -- the flag itself ---------------------------------------------------------

def test_flag_is_clear_after_reset_and_sticky_until_the_next_reset():
    assert pm.monitor_batch_failed() is False
    pm.mark_monitor_batch_failed()
    assert pm.monitor_batch_failed() is True
    pm.mark_monitor_batch_failed()
    assert pm.monitor_batch_failed() is True
    pm.reset_monitor_batch_status()
    assert pm.monitor_batch_failed() is False


# -- plan_manager.monitor_quotes (layer on/count) ----------------------------

def test_monitor_quotes_marks_failed_when_the_bounded_batch_returns_none(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: None)
    assert pm.monitor_quotes(["AAPL"]) == {}
    assert pm.monitor_batch_failed() is True


def test_monitor_quotes_empty_success_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    _quiet_counters(monkeypatch)
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: ({}, []))
    assert pm.monitor_quotes(["AAPL"]) == {}
    assert pm.monitor_batch_failed() is False


def test_monitor_quotes_success_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    _quiet_counters(monkeypatch)
    q = _q()
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: ({"AAPL": q.to_doc()}, []))
    assert pm.monitor_quotes(["AAPL"])["AAPL"].price == 190.0
    assert pm.monitor_batch_failed() is False


def test_monitor_quotes_with_no_tickers_never_marks(monkeypatch):
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: pytest.fail("no fetch"))
    assert pm.monitor_quotes([]) == {}
    assert pm.monitor_batch_failed() is False


# -- plan_manager._legacy_price_batch (layer off) ----------------------------

def test_legacy_price_batch_marks_failed_on_none(monkeypatch):
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: None)
    assert pm._legacy_price_batch(["AAPL"]) == {}
    assert pm.monitor_batch_failed() is True


def test_legacy_price_batch_empty_success_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: {})
    assert pm._legacy_price_batch(["AAPL"]) == {}
    assert pm.monitor_batch_failed() is False


def test_off_mode_monitor_quotes_marks_through_the_legacy_batch(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: None)
    assert pm.monitor_quotes(["AAPL"]) == {}
    assert pm.monitor_batch_failed() is True


# -- loops._live_price_batch / _legacy_live_price_batch ----------------------

def test_live_price_batch_marks_failed_when_monitor_quotes_raises(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")

    def boom(tickers):
        raise TimeoutError("hung")
    monkeypatch.setattr(pm, "monitor_quotes", boom)
    assert asyncio.run(loops._live_price_batch(["AAPL"])) == {}
    assert pm.monitor_batch_failed() is True


def test_live_price_batch_empty_quotes_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(pm, "monitor_quotes", lambda tickers: {})
    assert asyncio.run(loops._live_price_batch(["AAPL"])) == {}
    assert pm.monitor_batch_failed() is False


def test_legacy_live_price_batch_marks_failed_on_none(monkeypatch):
    monkeypatch.setattr(loops, "_run_bounded", lambda fn, args, timeout, label: None)
    assert asyncio.run(loops._legacy_live_price_batch(["AAPL"])) == {}
    assert pm.monitor_batch_failed() is True


def test_legacy_live_price_batch_marks_failed_when_it_raises(monkeypatch):
    def boom(fn, args, timeout, label):
        raise RuntimeError("spawn failed")
    monkeypatch.setattr(loops, "_run_bounded", boom)
    assert asyncio.run(loops._legacy_live_price_batch(["AAPL"])) == {}
    assert pm.monitor_batch_failed() is True


def test_legacy_live_price_batch_success_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(loops, "_run_bounded", lambda fn, args, timeout, label: {"AAPL": 1.0})
    assert asyncio.run(loops._legacy_live_price_batch(["AAPL"])) == {"AAPL": 1.0}
    assert pm.monitor_batch_failed() is False


def test_legacy_live_price_batch_with_no_tickers_never_marks(monkeypatch):
    monkeypatch.setattr(loops, "_run_bounded", lambda *a: pytest.fail("no fetch"))
    assert asyncio.run(loops._legacy_live_price_batch([])) == {}
    assert pm.monitor_batch_failed() is False
```

`QuoteDetail.to_doc()` / `QuoteDetail.from_doc()` are the existing round-trip used by `_monitor_quote_worker` and `monitor_quotes` (`swingbot/core/marketdata/shared/kinds.py`).

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness
python scripts/dev/testrun.py file tests/planning/test_monitor_batch_status.py
```

Expected: FAIL, `AttributeError: module 'swingbot.core.planning.plan_manager' has no attribute 'reset_monitor_batch_status'` (raised by the autouse fixture in every test).

- [ ] **Step 3: Add the flag and its three functions to plan_manager**

In `swingbot/core/planning/plan_manager.py`, directly after the line `_MANAGER: PlanManager | None = None`, insert:

```python


# -- v184: per-tick "the shared quote batch failed" flag ---------------------
# monitor_quotes / _price_batch_fn return {} both for a failed or timed-out
# batch (_run_bounded -> None) and for an empty one; the stop-monitor stamp
# needs the difference. trade_monitor resets the flag first thing each tick;
# any bounded batch that fails in that tick marks it. Sticky until the next
# reset. Return types are deliberately unchanged.
_MONITOR_BATCH: dict[str, bool] = {"failed": False}


def reset_monitor_batch_status() -> None:
    """Start a monitor tick with no batch failure recorded."""
    _MONITOR_BATCH["failed"] = False


def mark_monitor_batch_failed() -> None:
    """Record that a monitor quote batch failed or timed out this tick."""
    _MONITOR_BATCH["failed"] = True


def monitor_batch_failed() -> bool:
    """Whether any monitor quote batch failed since the last reset."""
    return _MONITOR_BATCH["failed"]
```

- [ ] **Step 4: Mark the flag in `_legacy_price_batch` and `monitor_quotes`**

In `_legacy_price_batch`, replace the last line

```python
    return result or {}
```

with

```python
    if result is None:  # v184: failed or timed out, not merely empty
        mark_monitor_batch_failed()
    return result or {}
```

In `monitor_quotes`, replace

```python
    if not out:
        return {}
    docs, rows = out
```

with

```python
    if out is None:  # v184: failed or timed out, not merely empty
        mark_monitor_batch_failed()
        return {}
    if not out:
        return {}
    docs, rows = out
```

Nothing else in either function changes.

- [ ] **Step 5: Mark the flag in loops' two monitor batch helpers**

In `swingbot/commands/scanning/loops.py`, `_live_price_batch` already imports `plan_manager` lazily. Change its `except` block from

```python
    except Exception as exc:
        swallowed(log, "scan.loops.monitor_prices", exc,
                  "trade_monitor: batch price fetch failed: %s", exc, exc_info=True)
        return {}
```

to

```python
    except Exception as exc:
        swallowed(log, "scan.loops.monitor_prices", exc,
                  "trade_monitor: batch price fetch failed: %s", exc, exc_info=True)
        plan_manager.mark_monitor_batch_failed()
        return {}
```

Replace the body of `_legacy_live_price_batch` after its docstring (keep the docstring as it is) with:

```python
    if not tickers:
        return {}
    from swingbot.core.planning import plan_manager
    try:
        result = await asyncio.to_thread(
            _run_bounded, functools.partial(get_current_price_batch, allow_stale=False),
            (tickers,), float(getattr(config, "LIVE_PRICE_TIMEOUT_SECONDS", 60)),
            f"trade_monitor: live-price batch of {len(tickers)} ticker(s)")
    except Exception as exc:
        log.warning("trade_monitor: batch price fetch failed: %s", exc, exc_info=True)
        plan_manager.mark_monitor_batch_failed()
        return {}
    if result is None:  # v184: _run_bounded failed or timed out, not merely empty
        plan_manager.mark_monitor_batch_failed()
    return result or {}
```

The import stays inside the function, like the other `plan_manager` imports in `loops.py`. The call arguments, the label and the warning text are unchanged, so the existing `test_off_mode_keeps_the_legacy_monitor_path` and `test_on_mode_monitor_failure_is_a_warning_and_empty` (which pins exactly one WARNING record) keep passing.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd /e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness
python scripts/dev/testrun.py file tests/planning/test_monitor_batch_status.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_shared_quote.py
python scripts/dev/testrun.py file tests/commands/test_trade_monitor_shared_quote.py
python scripts/dev/testrun.py file tests/scanning/test_log_levels_v111.py
python scripts/dev/complexity_gate.py
```

Expected: every file `0 failed`, `0 xfailed`; the gate exits 0 (`monitor_quotes` goes from B 7 to B 8, `_legacy_live_price_batch` stays well under 15). `test_trade_monitor_shared_quote.py` uses the `shared_db` fixture: if `/replicate-prod-db` has not run in this session yet, run it once first (Global Constraints).

- [ ] **Step 7: Commit**

```bash
cd /e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness
git add swingbot/core/planning/plan_manager.py swingbot/commands/scanning/loops.py tests/planning/test_monitor_batch_status.py
git commit -m "feat(v184): per-tick fetch-failed flag from the bounded monitor quote batch"
```

### Task V184-4: Poll-demand accessor: plan tickers poll() priced and did not price

**Model:** opus — touches `PlanManager.poll`, the only path that closes plan-linked trades, under a frozen complexity baseline (20), and "unknown" must never read as "nothing demanded".

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py`: new `PollDemand` dataclass after `class QuotePrices` (about line 74); `PlanManager.__init__` (about lines 458-485); `PlanManager.poll` (about line 589); new `PlanManager._record_poll_demand`; new module function `last_poll_demand()` after `run_manager_tick` (about line 1629)
- Create: `tests/planning/test_poll_demand.py` (suite `planning`)

**Interfaces:**
- Consumes: existing `PlanManager(store, price_fn, ..., price_batch_fn=None, ...)`, `PlanManager.poll(now=None)`, `QuotePrices(prices, details)`, module `_MANAGER`, `config.INTRADAY_MANAGER_V2`, `config.INTRADAY_RTH_ONLY` (all verified in `plan_manager.py`). Nothing from V184-2 or V184-3.
- Produces, in `swingbot/core/planning/plan_manager.py`:

```python
@dataclass(frozen=True)
class PollDemand:
    demanded: tuple[str, ...]          # unique open-plan tickers, store order
    priced: frozenset[str]             # subset with a usable price: truthy and > 0

    @property
    def unpriced(self) -> tuple[str, ...]: ...   # demanded minus priced, demanded order

class PlanManager:
    last_poll_demand: PollDemand | None          # None = nothing demanded this poll
    def _record_poll_demand(self, open_plans, prices) -> None: ...

def last_poll_demand() -> PollDemand | None: ...
    # None when config.INTRADAY_MANAGER_V2 is off or _MANAGER is None; else _MANAGER.last_poll_demand
```

  V184-6's `TickRecord.plan_demand` holds this object; `positions_of` reads `.demanded` and `unquoted_of` reads `.unpriced`. V184-7 sets `rec.plan_demand = plan_manager.last_poll_demand()` after the manager tick.

**Why.** Spec § 1 requires `positions` and `unquoted` to cover open plans, because `poll()` is the only path that closes a plan-linked trade and the August stall was in plan stops. The plan side must come from the prices `poll()` itself fetched, with no extra `monitor_quotes` call and no quote-cache read. Spec clarification 1 narrows it: plan tickers count only on a poll that actually demanded quotes. When the manager is off, when `poll()` returns early in quiet hours, or on the serial test seam (`price_batch_fn is None`), the answer is `None` ("not demanded"), never an empty or all-unpriced set. Otherwise `unquoted` would fire through every quiet night. The "usable price" filter is exactly the one `poll()` applies before stepping a plan: `if not price or price <= 0: continue`.

**Complexity.** `PlanManager.poll` is baselined at 20 in `scripts/dev/complexity_baseline.json` and the gate fails on any change in either direction. The edit adds one assignment and one method call, and no branch, boolean operator or comprehension; every condition lives in `_record_poll_demand`.

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_poll_demand.py`:

```python
"""v184: PlanManager.last_poll_demand -- the open-plan tickers one poll() asked
the quote batch for and the subset it priced, with no extra fetch. Unknown or
not-demanded is None, never an empty or all-unpriced demand."""
import datetime as dt
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_manager import PlanManager, PollDemand, QuotePrices

SATURDAY = dt.datetime(2026, 10, 24, 12, 0, tzinfo=dt.timezone.utc)   # always quiet hours


class _Store:
    """open_plans() hands out the given plans; get() returns None, so poll()
    skips every step after the price filter. No notices to resend."""

    def __init__(self, tickers):
        self._plans = [SimpleNamespace(ticker=t, plan_id=f"p{i}") for i, t in enumerate(tickers)]

    def all(self):
        return []

    def open_plans(self):
        return list(self._plans)

    def get(self, plan_id):
        return None


def _no_serial(ticker):
    raise AssertionError("the serial price_fn must not run beside a batch fn")


def _manager(tickers, batch):
    return PlanManager(_Store(tickers), _no_serial, price_batch_fn=batch)


@pytest.fixture(autouse=True)
def _every_hour_is_a_poll_hour(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)


def test_unpriced_is_demanded_minus_priced_in_demanded_order():
    d = PollDemand(("MSFT", "AAPL", "NVDA"), frozenset({"AAPL"}))
    assert d.unpriced == ("MSFT", "NVDA")
    assert PollDemand((), frozenset()).unpriced == ()


def test_a_new_manager_has_demanded_nothing():
    assert _manager(["AAPL"], lambda t: {}).last_poll_demand is None


def test_poll_records_unique_tickers_and_the_close_filter():
    asked = []

    def batch(tickers):
        asked.append(list(tickers))
        return {"AAPL": 190.0, "MSFT": 0.0, "NVDA": -1.0, "TSLA": None}
    mgr = _manager(["AAPL", "MSFT", "AAPL", "NVDA", "TSLA", "AMD"], batch)
    assert mgr.poll() == []
    assert asked == [["AAPL", "MSFT", "NVDA", "TSLA", "AMD"]]       # one batch call, unchanged
    assert mgr.last_poll_demand == PollDemand(
        ("AAPL", "MSFT", "NVDA", "TSLA", "AMD"), frozenset({"AAPL"}))
    assert mgr.last_poll_demand.unpriced == ("MSFT", "NVDA", "TSLA", "AMD")


def test_quote_prices_from_the_shared_batch_are_read_as_a_dict():
    mgr = _manager(["AAPL", "MSFT"], lambda t: QuotePrices({"AAPL": 190.0}, {}))
    mgr.poll()
    assert mgr.last_poll_demand == PollDemand(("AAPL", "MSFT"), frozenset({"AAPL"}))


@pytest.mark.parametrize("result", [None, {}])
def test_an_empty_or_none_batch_leaves_every_ticker_unpriced(result):
    mgr = _manager(["AAPL", "MSFT"], lambda t: result)
    mgr.poll()
    assert mgr.last_poll_demand.unpriced == ("AAPL", "MSFT")


def test_a_raising_batch_leaves_every_ticker_unpriced():
    def boom(tickers):
        raise TimeoutError("hung")
    mgr = _manager(["AAPL"], boom)
    mgr.poll()
    assert mgr.last_poll_demand == PollDemand(("AAPL",), frozenset())


def test_no_open_plans_is_a_known_empty_demand_and_fetches_nothing():
    mgr = _manager([], lambda t: pytest.fail("no fetch with no open plans"))
    mgr.poll()
    assert mgr.last_poll_demand == PollDemand((), frozenset())


def test_the_serial_seam_records_no_demand():
    mgr = PlanManager(_Store(["AAPL"]), lambda t: 190.0)        # price_batch_fn is None
    mgr.poll()
    assert mgr.last_poll_demand is None


def test_quiet_hours_clear_the_previous_demand(monkeypatch):
    mgr = _manager(["AAPL"], lambda t: {"AAPL": 190.0})
    mgr.poll()
    assert mgr.last_poll_demand is not None
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    assert mgr.poll(now=SATURDAY) == []
    assert mgr.last_poll_demand is None


def test_module_accessor_is_none_while_the_manager_is_off(monkeypatch):
    mgr = _manager(["AAPL"], lambda t: {"AAPL": 190.0})
    mgr.poll()
    monkeypatch.setattr(pm, "_MANAGER", mgr)
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", False)
    assert pm.last_poll_demand() is None


def test_module_accessor_never_builds_the_manager(monkeypatch):
    monkeypatch.setattr(pm, "_MANAGER", None)
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(pm, "_manager", lambda: pytest.fail("must not build the manager"))
    assert pm.last_poll_demand() is None
    assert pm._MANAGER is None


def test_module_accessor_returns_the_managers_last_demand(monkeypatch):
    mgr = _manager(["AAPL", "MSFT"], lambda t: {"MSFT": 410.0})
    mgr.poll()
    monkeypatch.setattr(pm, "_MANAGER", mgr)
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    assert pm.last_poll_demand() == PollDemand(("AAPL", "MSFT"), frozenset({"MSFT"}))
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness
python scripts/dev/testrun.py file tests/planning/test_poll_demand.py
```

Expected: collection error, `ImportError: cannot import name 'PollDemand'`.

- [ ] **Step 3: Add `PollDemand`**

In `swingbot/core/planning/plan_manager.py`, directly after the `class QuotePrices(dict)` definition (it ends with `self.details = details`), insert:

```python


@dataclass(frozen=True)
class PollDemand:
    """v184: the open-plan tickers one poll() asked the shared quote batch for,
    in store order and de-duplicated, and the subset that came back with a
    usable price -- truthy and > 0, the filter poll() applies before stepping a
    plan. The stop-monitor stamp reads it instead of fetching again."""
    demanded: tuple[str, ...]
    priced: frozenset[str]

    @property
    def unpriced(self) -> tuple[str, ...]:
        """Demanded tickers with no usable price, in demanded order."""
        return tuple(t for t in self.demanded if t not in self.priced)
```

`dataclass` is already imported (`from dataclasses import dataclass, field`), and the module has `from __future__ import annotations`.

- [ ] **Step 4: Add the attribute and the recorder to `PlanManager`**

In `PlanManager.__init__`, after the last assignment `self.hourly_frame_fn = hourly_frame_fn`, add:

```python
        # v184: what the last poll() demanded from the quote batch and what it
        # priced. None = nothing demanded (quiet hours, serial seam, not polled).
        self.last_poll_demand: PollDemand | None = None
```

Add this method to `PlanManager`, directly before `def poll(self, now=None)`:

```python
    def _record_poll_demand(self, open_plans, prices) -> None:
        """v184: remember what this poll() demanded and priced. ``prices`` is
        poll()'s own batch result (no second fetch); None with plans open is the
        serial seam, which demands nothing from the batch, so the record stays
        None. No open plans is a known, empty demand."""
        if prices is None and open_plans:
            return
        tickers = tuple(dict.fromkeys(plan.ticker for plan in open_plans))
        got = prices or {}
        self.last_poll_demand = PollDemand(
            tickers, frozenset(t for t in tickers if (got.get(t) or 0) > 0))
```

`(got.get(t) or 0) > 0` is true exactly when poll's `not price or price <= 0` is false: a falsy price becomes `0`, which fails `> 0`.

- [ ] **Step 5: Wire the two statements into `poll()`**

Make `self.last_poll_demand = None` the first statement of `poll`, before the long comment and the quiet-hours return. The method header becomes:

```python
    def poll(self, now=None) -> list[PlanEvent]:
        self.last_poll_demand = None  # v184: unknown until this poll demands quotes
        # One gate, and only one (2026-09-14, on direct request): the
```

(the rest of the comment block and the code follow unchanged). Then, right after the batch block and before `details = getattr(prices, "details", {})`, add one call, so that stretch reads:

```python
        open_plans = self.store.open_plans()
        prices: dict[str, float] | None = None
        if self.price_batch_fn is not None and open_plans:
            tickers = list(dict.fromkeys(plan.ticker for plan in open_plans))
            try:
                prices = self.price_batch_fn(tickers) or {}
            except Exception as exc:
                # No per-plan fallback here: the point of batching is to
                # bound the tick, and a failed fresh batch must not turn into
                # stale or serial quote requests that delay every plan.
                log.debug("poll: batch price fetch failed: %s", exc)
                prices = {}
        self._record_poll_demand(open_plans, prices)
        details = getattr(prices, "details", {})
```

Nothing else in `poll` changes.

- [ ] **Step 6: Add the module accessor**

Directly after `def run_manager_tick()` and its body, insert:

```python


def last_poll_demand() -> PollDemand | None:
    """v184: what the live manager's last poll() demanded and priced, for the
    stop-monitor stamp. None while INTRADAY_MANAGER_V2 is off or the manager was
    never built (the plan side demanded nothing). Never builds the manager and
    never fetches."""
    if not config.INTRADAY_MANAGER_V2 or _MANAGER is None:
        return None
    return _MANAGER.last_poll_demand
```

`config` here is the module-level `from swingbot import config` import at the top of the file. Tests patch attributes on that same module object.

- [ ] **Step 7: Run the tests and the complexity gate**

```bash
cd /e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness
python scripts/dev/testrun.py file tests/planning/test_poll_demand.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_shared_quote.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_concurrent_close.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_active.py
python scripts/dev/testrun.py file tests/planning/test_trade_monitor_wiring.py
python scripts/dev/testrun.py file tests/planning/test_manager_singleton_staleness_repro.py
python scripts/dev/complexity_gate.py
```

Expected: every file `0 failed`, `0 xfailed`. The gate exits 0, which proves `PlanManager.poll` is still exactly 20: the gate reports any baselined function whose score moved in either direction. If it reports `poll`, move the offending expression into `_record_poll_demand`; never edit the baseline.

- [ ] **Step 8: Commit**

```bash
cd /e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness
git add swingbot/core/planning/plan_manager.py tests/planning/test_poll_demand.py
git commit -m "feat(v184): poll-demand accessor for the plan tickers poll() priced"
```

