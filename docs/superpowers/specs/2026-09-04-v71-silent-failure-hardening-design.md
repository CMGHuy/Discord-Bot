# v71 — Silent-failure hardening: the retrospective crash and the health signal that hid it

**Version:** ui 1.11.0 · bot 1.6.0
**Bump:** ui patch (1.11.0 → 1.11.1) · bot patch (1.6.0 → 1.6.1)
**Edge:** none (integrity)

## The problem

Two defects, one live and one latent, plus the reason neither reached a human.

### A — `build_daily_retrospective` crashes every evening

Production `bot.log`, 2026-09-02 21:15 and 2026-09-03 21:15, identical both days:

```
[ERROR] daily_recap: failed to post retrospective: unsupported format string passed to NoneType.__format__
  File "/app/swingbot/core/tracking/retrospective.py", line 612, in build_daily_retrospective
    f"• Level {r['level']} at {r['win_rate']:.0f}% WR (n={r['n']})."
TypeError: unsupported format string passed to NoneType.__format__
```

The end-of-session retrospective has not posted since this began. `daily_recap`
catches the exception and logs it, so the only symptom is an absence.

**Root cause.** `calibration.level_calibration()` builds each row as:

```python
n  = len(trades)                 # every trade at this confidence level
wr = metrics.win_rate(trades)    # None when zero win/loss trades
```

`metrics.win_rate()` counts only `status == "win"` / `status == "loss"` and
returns `None`, never `0.0`, when that denominator is empty — manual closes,
scratches and timeouts are excluded **by design** (`metrics.py:206-217`, and its
docstring: *"'no data yet' and '0% win rate' must never look the same on a UI"*).

The call site guards on `r["n"] > 0` and then formats `{r['win_rate']:.0f}`.
So **`n > 0` is being used as a proxy for "win_rate is computable", and it is
not.** Any day whose only closed trades at a level are manual closes, scratches
or timeouts produces `n > 0` with `win_rate is None`. The v70 extended-hours and
manual-close work is what started generating those trades routinely.

Blast radius is disproportionate: one unformattable line aborts the **entire**
retrospective — all ten parts — not just the calibration section.

### B — The same defect, copy-pasted, not yet fired

`insights.py:88-92` has the identical guard and the identical unguarded format,
in the weekly insights report:

```python
level_rows = [r for r in calibration.level_calibration(week_closed) if r["n"] > 0]
...
f"Lv{r['level']}: {r['win_rate']:.0f}% (n={r['n']})" for r in level_rows
```

It will fail on the same condition, over a weekly window instead of a daily one.
`analyze.py:189` formats `plan.badge_stats['win_rate']:.1f` guarding only that
the dict exists, not that the value is non-`None`; it sits inside a `try/except`
so it degrades rather than crashes, but the guard is still wrong.

A sweep of every format spec applied to a nullable metric field found seven
sites. Four are already correct (`trades.py:390,405,408`, `insights.py:104`) and
guard with `is not None`, rendering `n/a`. **The fix is to make three outliers
match a convention the codebase already has**, not to invent one.

### C — Why it ran for days without anyone knowing

`_write_heartbeat()` runs at the *top* of `_session_scan_tick` (`loops.py:59`),
before any real work. `admin/app.py:343-356` derives `bot_alive` purely from that
file's mtime age. A tick that dies on its first real line still stamps a fresh
heartbeat, so **the dashboard reads green while the bot is doing nothing.**

This is not hypothetical. Commit `6a4ed5f6` records a five-day alert blackout
(2026-08-28 → 09-02, 890 consecutive failed ticks in `bot.log.1`) during which
the dashboard showed green the entire time. There is no last-*successful*-scan
concept anywhere in the codebase. `bot_alive` means "the process is looping",
not "the bot works".

### D — The prevention gap

Both crashes that caused the blackout (`_send_alerts`, `_MANUAL_CLOSE_QUEUE`)
were undefined names. `pyflakes` is already installed and detects that class in
about a second. Nothing runs it. `make check` is `py_compile`, which does not
catch `NameError`.

The full suite is green (2672 passed, 0 failed) with every one of these defects
present, so tests alone are not the missing net.

## Goals

1. The retrospective posts every evening, including on days with only manual
   closes.
2. A future formatting bug in one section costs that section, not the report.
3. The dashboard distinguishes "process alive" from "bot working", and a
   sustained failure reaches the user without them opening the dashboard.
4. The undefined-name class fails the gate before it can ship.

## Non-goals

Deferred to v72 (see *Out of scope*): the 248-handler audit, the 125 unused
imports, and the yfinance false-delisted noise. Keeping this spec to the live
crash and the net that should have caught it is what lets it ship tonight.

## Design

### Part 1 — Guard on the value, not on the row count

At all three sites, guard on `win_rate is not None` and render `n/a`, matching
`trades.py:390` and `insights.py:104`.

A level with trades but no win/loss **still renders**, as `n/a` — it is not
dropped. `metrics.py` already establishes the principle that "no data yet" and
"0%" must not look alike; the same holds for "three manual closes" versus "no
trades at this level". Dropping the row would hide that trading happened.

- `retrospective.py:611-613` — keep `n > 0` as the row filter, add the value
  guard at format time.
- `insights.py:88-92` — same change.
- `analyze.py:189` — guard `badge_stats.get("win_rate") is not None`.

This is deliberately a fix at each call site rather than changing
`level_calibration()` to coerce `None → 0.0`. Coercing would destroy the
distinction `metrics.win_rate()` exists to preserve and would silently corrupt
every other consumer of that row.

### Part 2 — Isolate each retrospective section

`build_daily_retrospective` composes **ten** independent parts
(`retrospective.py:448-672`). The guard pattern already exists there twice —
around `get_daily_summary()` (`479-488`) and around `edge_decay_report`
(`614-618`), both `try/except` + `log.exception` + skip — **it simply was not
applied consistently.**

Extend it so each part is composed under its own guard: a part that raises logs
with `log.exception` and contributes nothing, and the remaining parts still post.

Implemented as a small `_section(name, failures)` **context manager** wrapping
each part in place, not by extracting the parts into functions. The parts share
roughly fifteen locals computed in the partition block above them
(`closed_today`, `win_rate`, `avg_r`, `still_open`, …); a `with` block keeps
them in scope, whereas extraction would mean threading all of them through ten
new signatures — a far larger diff and a real regression risk for a P0 fix.
Most parts build a local list and append once at the end, so a mid-part failure
contributes nothing rather than half a section.
A `⚠️ One section of this report failed to build` line is appended when any part
was dropped, so a degraded report is visibly degraded rather than quietly short.

This is the change that matters beyond this bug: it converts "one bad value
destroys the report" into "one bad value costs one section".

### Part 3 — An honest health signal, and escalation

**Heartbeat schema** (`runstate.py:_write_heartbeat`) keeps stamping liveness at
the top of the tick — that genuinely *is* "process alive" — and gains three
fields describing tick outcome:

| Field | Meaning |
|---|---|
| `last_success` | ISO timestamp of the last tick that returned without raising |
| `consecutive_failures` | Count since the last success; reset to 0 on success |
| `alert_active` | Whether an escalation has already been posted for this outage |

`consecutive_failures` and `alert_active` persist in the file rather than in
memory, so a crash-looping container that restarts does not reset its own
outage counter.

**Where success is recorded.** `_session_scan_tick` has several legitimate early
returns (paused, outside session, channel unconfigured) — those are successful
ticks; the tick did its job. Rather than instrument each path, the success stamp
goes in `session_scan` immediately after `await _session_scan_tick()` returns
normally (`loops.py:36-41`), and the failure increment goes in its `except`.
One place, and it means exactly "the tick completed without raising".

**Admin health** (`admin/app.py:312 scan_status_payload()`) keeps `bot_alive` as
process liveness and adds `bot_healthy` (derived from `last_success` age),
`bot_last_success` and `bot_consecutive_failures`.

**The indicator must not introduce green or red.** `shell/connection-status.ts`
carries an explicit, reasoned colour rule from NG52's colour review —
*"Greyscale and amber, never green or red: connection state is not money. Green
here made 'the stream is up' and 'this position is in profit' the same colour in
the same chrome, and red made a fallback to polling look like a loss."* The same
component also establishes how two severities of the same caution are told
apart: *"the colour carries the state, the animation only ever carried the
liveliness"*, with `.dot.degraded` and `.dot.dead` both `var(--warn)` and the
**label** distinguishing them.

So this follows the existing vocabulary rather than adding a traffic light. The
component already renders `bot offline` (amber) when `botAlive() === false`; it
gains a `botHealthy` input and renders a second amber label:

| Condition | Label |
|---|---|
| `botAlive() === false` | `bot offline` (unchanged) |
| `botAlive() && botHealthy() === false` | `bot failing` |
| otherwise | nothing (unchanged) |

Both amber, both `null`-tolerant in the same three-valued way `botAlive` already
is. "Bot failing" is the state that did not exist and that would have surfaced
the blackout on day one.

**Escalation.** After `HEALTH_ALERT_AFTER_FAILURES` consecutive failures
(default 3 ≈ 15 min at the 5-minute interval), post **once** — `alert_active`
guards against repeating every tick — and post once more on recovery. The
message carries the failure count, the last success time and the exception type.

**Channel.** New optional `DISCORD_CHANNEL_OPS_ID`, **falling back to
`DISCORD_CHANNEL_TRADES_ID` when unset.** A safety net that requires
configuration before it works is one that will not be armed when it matters; the
fallback means every existing deployment gets the net on upgrade with no `.env`
edit. Setting a dedicated channel moves the notices out of the alert stream.

### Part 4 — Gate the undefined-name class

Add a pyflakes pass to `scripts/dev/testrun.py`, failing on **undefined names
only**. It runs in about a second over the tracked Python, and it would have
caught both outages at authoring time.

Scoped deliberately narrow: the 125 unused imports are real debt but they are
not a crash class, and gating them now would either block this spec behind a
cleanup or force a blanket suppression. Undefined names alone can land green
today. Widening the rule set is v72's decision, made once the cleanup is done.

The four existing `"ScanProgress"` forward references (`analyze.py:384`,
`fetch.py:169,250,333`) are the only current violations and are fixed here by
importing the symbol, since the gate cannot land red.

## Data and schema changes

`data/bot_heartbeat.json` gains `last_success`, `consecutive_failures` and
`alert_active`. Readers must tolerate their absence — an upgraded admin container
will read a heartbeat written by a not-yet-restarted bot, and the first tick
after deploy writes a file with no prior success recorded. Absent `last_success`
is treated as "unknown, not yet failing", so a fresh deploy does not open amber.

**This is JSON persistence under `data/`, so v67 must be updated** — per the
standing rule that a parallel plan changing `data/` JSON updates v67 before it
closes. That update is a task in this plan.

The owning part is `_3a-operational-flags` (Alembic revision `p3_001`), which
defines both tables involved. Its `bot_heartbeat` table is deliberately minimal:

```python
sa.Column("key",  sa.Text, nullable=False, unique=True),
sa.Column("ts",   sa.TIMESTAMP(timezone=True), nullable=False),
```

A `(key, ts)` shape, carrying no payload. The three new fields therefore do not
all belong in one place, and the mapping is chosen to fit v67's existing design
rather than to widen its schema:

| New field | v67 destination | Why |
|---|---|---|
| `last_success` | second `bot_heartbeat` row, `key='last_success'` | It is a timestamp; the table is already keyed for exactly this |
| `consecutive_failures` | `runtime_flags` | An integer, not a timestamp |
| `alert_active` | `runtime_flags` | A boolean, not a timestamp |

Both tables live in `_3a` under the same revision, so this is one part and one
migration, with **no new Alembic revision and no schema widening required**.

Note for whoever executes that task: `_3a`'s `bot_heartbeat` also does not carry
the *existing* `session_active` / `scan_paused` booleans from today's JSON. That
is a pre-existing gap in v67's model, not one this spec introduces — flag it in
the v67 task rather than silently fixing it here.

## Config additions

Both new fields go in `swingbot/config.py`'s schema (hot-reloadable via SIGHUP,
like the rest):

| Field | Default | Purpose |
|---|---|---|
| `DISCORD_CHANNEL_OPS_ID` | unset → falls back to trades channel | Where health escalations post |
| `HEALTH_ALERT_AFTER_FAILURES` | `3` | Consecutive failed ticks before escalating |

## Testing

Every test below must be confirmed **failing against current code** before its
fix lands — these are regressions, and a test that passes before the fix is not
testing the bug.

1. **Retrospective, manual closes only.** A level whose only closed trades are
   manual closes → `level_calibration` yields `n > 0, win_rate is None` →
   assert the report still builds, posts, and shows `n/a` for that level.
   Reproduces the exact production traceback against current code.
2. **Weekly insights, same shape.** Same fixture through
   `insights.weekly_digest()`.
3. **Section isolation.** Force one part of `build_daily_retrospective` to
   raise; assert the other parts still post and the degraded-report notice
   appears.
4. **Heartbeat outcome tracking.** A tick that raises increments
   `consecutive_failures` and leaves `last_success` unchanged; a tick that
   returns resets the counter and stamps `last_success`; an early-return tick
   (paused / off-session) counts as success.
5. **Escalation.** N failures post exactly one message; further failures post
   none; recovery posts exactly one; `DISCORD_CHANNEL_OPS_ID` unset routes to
   the trades channel.
6. **Admin health payload.** Fresh deploy with no `last_success` →
   `bot_healthy` is not `False` (unknown, not yet failing); stale
   `last_success` with fresh heartbeat mtime → `bot_alive` true,
   `bot_healthy` false; stale mtime → `bot_alive` false.
7. **Frontend.** `connection-status.spec` — `botHealthy === false` with
   `botAlive === true` renders `bot failing`; `botAlive === false` still
   renders `bot offline` and not both; `null` renders neither. Assert the
   label text, **not** a colour, and assert no green/red class is
   introduced. Run via `cd frontend && npm test`.
8. **Gate.** A fixture module with an undefined name fails the pyflakes pass.

## Parallelisation

- **Group 1 (parallel):** Part 1's three call-site fixes — `retrospective.py`,
  `insights.py`, `analyze.py` are one file each, no shared file, no shared
  symbol introduced.
- **Group 2 (parallel, after Group 1):** Part 3's admin/Flask work
  (`admin/app.py`) and Part 3's frontend work (`frontend/`) — disjoint trees,
  connected only by the health payload's field names, which Part 3's config
  task fixes first.
- **Sequential:**
  - Part 2 after Part 1's `retrospective.py` fix — both edit
    `build_daily_retrospective`, and the isolation wrapper should go around
    already-correct code so a failure in test 3 means the wrapper, not the
    formatting.
  - Part 3's heartbeat-schema task before its admin and frontend tasks (they
    consume the fields it introduces) and before the v67 update (which
    migrates them).
  - Part 4 last — the gate must run against the finished tree, and it fails
    until the `ScanProgress` imports land.
  - Final full-suite verification alone at the end: `python
    scripts/dev/testrun.py full` **and** `cd frontend && npm test`, once each.

## Out of scope — deferred to v72

Carried out of the investigation, deliberately not fixed here:

- **248 `except Exception` handlers**, ~61 swallowing via bare
  `pass`/`continue`/`return`, against only 24 `log.exception` sites. Needs
  per-site triage of which may hide a programming error; genuinely plan-sized.
- **125 unused imports**, and the dead-and-shadowed `alerts` module import at
  `loops.py:17` — unused, and shadowed by locals named `alerts` at lines 89 and
  412, so the next `alerts.foo()` written in either function is an
  `UnboundLocalError`. The 1.5.1 fix worked around this rather than removing it.
- **f-string with no placeholders**, `scripts/backtest/measure_alert_density.py:590`.
- **yfinance false "possibly delisted"** for live tickers (SOFI, PYPL, PLTR,
  GLW, SHOP, NBIS) and 8 empty `[ERROR]` log lines.

**Checked and explicitly not carried forward:** the `COVERAGE REGRESSION` cache
history-loss errors are historical only — 0 occurrences in the current log, all
in rotated logs predating the v59 cache-basis work that fixed them.
