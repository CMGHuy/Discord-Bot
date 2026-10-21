# v184 — Stop-monitor liveness: alert when open stops stop being checked: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V184-6:" -A 300 docs/superpowers/plans/2026-10-21-v184-stop-monitor-liveness_2-monitor-stamp.md`.

**Bump:** bot patch
**Edge:** none (integrity) — protects the R the book already books: in August a stalled monitor turned four −1R stops into −3.3R to −6.0R fills. No stop, fill or close logic changes, so ExpR is predicted unchanged; the value is the count of hours with stops unchecked and nobody told, which today goes uncounted.
**Screen:** exempt (integrity)
**Spec:** [2026-10-21-v184-stop-monitor-liveness-design.md](../specs/2026-10-21-v184-stop-monitor-liveness-design.md)
**Brief:** `.superpowers/briefs/2026-10-21-v184-stop-monitor-liveness.md`
**Worktree:** implement every task in `.claude/worktrees/2026-10-21-v184-stop-monitor-liveness` (branch of the same name, created in V184-1's first step; `docs/claude/document-lifecycle.md`). The merge to `main` is V184-11's last step. V184-12 runs on production after the normal deploy.

## Goal

On 2026-08-03/04 the bot's 60-second trade monitor stopped evaluating stops
for about 26 hours without anyone noticing. When it came back, 25 trades
closed in 28 seconds at whatever the quote was by then, and four long stops
that should have been −1R filled at −3.3R to −6.0R. The probable hang causes
were fixed later, since today's quote fetch is process-bounded. What was never
fixed is **visibility**. The only liveness stamp is written by the scan loop,
and the out-of-process watch (`scripts/ops/heartbeat_watch.sh`) reads only
that stamp. So a wedged monitor, a dead one, or one that ticks but prices
nothing all look healthy. Plan-linked stops, which are the ones that stalled,
are closed only by the plan manager's `poll()`, so open trade rows alone do not
show what is being watched.

Once this ships, the trade monitor writes its own `monitor` key into the
`bot_heartbeat` row at the end of every tick (throttled to one write per
120 s unless something material changes). The key says when the tick ended,
whether it raised, which tickers the monitor is responsible for (open trades
plus the plans `poll()` actually priced this tick), which of those had no
usable price, whether the shared quote batch failed outright, and which
checks raised. A `priced_at` field moves forward, in process memory, only on
a tick where every responsible ticker was priced and checked cleanly. The
cron watch, which runs every 5 minutes on the VM, gains two incidents that
post to the ops webhook once per incident and once on recovery:
`monitor_stale` (the last tick ended more than 300 s ago, at any hour) and
`stops_unchecked` (during the NYSE regular session, holiday- and
half-day-aware, positions have gone unchecked for longer than the
threshold, counted from the later of the last clean tick and today's 09:30 ET
open).

The plan leaves the rest untouched. There are no stop, target, fill or close
changes: an unpriced ticker is still skipped, and the plan only makes the
skip visible. The stamp adds no quote fetch and no quote-cache read, which
keeps live and replay in parity. The existing heartbeat verdict, its
threshold, its log line and its state file stay byte-identical. Trade
channels never see an ops message. There is no self-healing watchdog; that
is a separate design.

Success is measured by the tests and by production. In the tests, the stamp's
fields come out right for every case in spec § Tests, with no extra provider
call; the closes run unchanged when the stamp raises; every watch verdict
holds in a dry run; and each incident posts once and recovers once through
its own state file. On production, after the deploy, each verdict dry-runs
correctly, one real run logs `monitor verdict=ok` with a tick under 120 s
old, and a single `--test` post arrives, sent only after the partner says so.

## Architecture

```
trade_monitor (loops.py, 60 s)
  rec = TickRecord()                         # every field "unknown", outcome="raised"
  try:  await _monitor_tick(rec)             # existing body, helpers extracted
          plan_manager.reset_monitor_batch_status()
          trade read -> rec.trade_tickers
          _live_price_batch -> rec.live_prices      (monitor_quotes #1; marks failed on _run_bounded None)
          _check_open_tickers -> closes + rec.check_errors
          _run_plan_manager_tick -> events, rec.manager_raised
              poll(): monitor_quotes #2 (shared 15 s cache) + PlanManager.last_poll_demand
          rec.plan_demand = plan_manager.last_poll_demand()
          rec.fetch_failed = plan_manager.monitor_batch_failed()
          posts, equity sample, retries, close notices   (unchanged)
        rec.outcome = "ok"
  finally: await monitor_liveness.stamp_tick(rec)      # never raises; asyncio.to_thread write
              MonitorLiveness.build(rec, now) -> full `monitor` doc, advances priced_at in memory
              due(doc, now)? -> runstate._update_heartbeat({"monitor": doc})

heartbeat_watch.sh (cron */5)
  heartbeat_check   (old main body, now a function; line + state unchanged; sets HB_VERDICT)
  monitor_check     (MONITOR_SQL -> one '|' row; verdict; logs/monitor_watch.state; post/recover)
```

The monitor's state (`started_at`, `priced_at`, last written signature, last
write time) lives in one module object, `monitor_liveness._STATE`, created at
import, which is process start. It is never read back from the row, so a
restart gives `priced_at = null` and the watch counts from `started_at`.

## Global Constraints

- No stop, target, fill or close logic changes; an unpriced ticker is still skipped (spec § What does not change).
- The stamp adds **no** `monitor_quotes` call and **no** quote-cache read; `test_monitor_and_manager_share_one_provider_call_per_tick` stays green (`layer_on.calls == 1`).
- The stamp write goes through `asyncio.to_thread`; a failed write is counted by `swallowed(log, "ops.monitor_stamp", ...)` and never raises into the tick.
- `_update_heartbeat` merges `doc || fields` shallowly: every write carries the **full** `monitor` object (additive JSONB key, no migration; `docs/claude/schema-evolution.md`).
- Complexity < 15 for every function written or changed; `loops.trade_monitor` (C 13, unbaselined) must not reach 15; `PlanManager.poll` (baselined 20) must not grow: its bookkeeping is one reset statement plus one helper call, no new branch.
- `heartbeat_watch.sh`: the existing heartbeat verdict line, `logs/heartbeat_watch.state`, `MIN_STALE_S=900` and `doc->>'timestamp'` query stay byte-identical; `set -euo pipefail`, LF only, no `sed -i`, `.env` grepped never sourced; bare `--dry-run` still exits 2.
- Thresholds are script constants, no `.env` knob: `MONITOR_STALE_S=300`; `STOPS_UNCHECKED_S=600` unless V184-1's measurement sets it (§ Threshold decision).
- Ops alerts go only to `OPS_ALERT_WEBHOOK_URL`; production steps are read-only except the one `--test` post, which the controller sends only after asking the partner (`AskUserQuestion`).
- Tests that hit the DB need `/replicate-prod-db` run once before the first DB test run (CLAUDE.md); per-task runs are `python scripts/dev/testrun.py file <test>`; one full suite, in V184-11.
- No Codex mirror change (no `CLAUDE.md`, `docs/claude/` or `.claude/` edit).

## Spec clarifications (controller decisions, 2026-10-21)

1. **Plan-ticker demand.** Plan tickers join `positions` only on ticks where `poll()` actually demanded quotes, meaning the manager is on and `poll()` passed its quiet-hours gate. When `run_manager_tick` is a no-op (`INTRADAY_MANAGER_V2` off, or `poll()`'s quiet-hours early return), plan tickers are "not demanded": they are in neither `positions` nor `unquoted`. Trade tickers always count. The serial test seam (`price_batch_fn is None`) records no demand either. When `run_manager_tick` raised, `positions` is `null` (unknown) and `check_errors` carries `"<plan manager>"`. This narrows spec § 1 `positions` ("union with `open_plans()` tickers") to the tickers the monitor is in fact responsible for pricing on that tick, and it needs no second `open_plans()` read.
2. **fetch_failed** comes from a module-level, per-tick sticky flag in `plan_manager` (`reset_monitor_batch_status` / `mark_monitor_batch_failed` / `monitor_batch_failed`), set whenever `_run_bounded` returns `None` in `monitor_quotes`, `_legacy_price_batch` or loops' `_legacy_live_price_batch`, or when `monitor_quotes` raises into `_live_price_batch`. Return types are unchanged.
3. **market_open** uses a new `session.is_nyse_regular_session(now)` that adds the weekday test the spec formula omits.
4. **SSE**: the admin `bot` handler does not debounce (`connection.store.ts` uses unthrottled `events.changes('bot')`), so the bot throttles: at most one write per 120 s, plus an immediate write when `outcome`, `unquoted`, `fetch_failed` or `check_errors` changes.
5. **Watch message `<n>`** in `stops_unchecked` is `unquoted_count + len(check_errors)`, or the word `unknown` when `positions` is `null`. The watch also needs a recovery message and an `unreadable` message for the monitor; their exact wording is in § Contracts.

## Threshold decision

V184-1 appends its measured verdict here (a dated line: kept 600 s, or the new value with its reason) and in its results doc. V184-9 reads this line before it writes `STOPS_UNCHECKED_S`. V184-11 refuses to merge if the line is missing.

## Contracts

### Session helper (V184-2)

`swingbot/core/market/session.py`:

```python
def is_nyse_regular_session(now: dt.datetime | None = None) -> bool:
    """NYSE regular session at ``now``: a weekday, not in NYSE_HOLIDAYS, and
    RTH_OPEN <= t < session_close(d) in ET. Holiday- and half-day-aware,
    unlike is_regular_session (and unlike bot_core.in_session, the Berlin
    scan window)."""
```

### Batch status (V184-3)

`swingbot/core/planning/plan_manager.py`, module level:

```python
_MONITOR_BATCH: dict[str, bool] = {"failed": False}

def reset_monitor_batch_status() -> None: ...   # sets failed False; trade_monitor calls it first thing each tick
def mark_monitor_batch_failed() -> None: ...    # sets failed True (sticky until the next reset)
def monitor_batch_failed() -> bool: ...
```

Set by `monitor_quotes` (when `fetch._run_bounded(...)` returns `None`), by
`_legacy_price_batch` (same), by loops' `_legacy_live_price_batch` (when its
`_run_bounded` returns `None`, or it raises) and by loops' `_live_price_batch`
(when `monitor_quotes` raises). An empty but successful result does **not**
set it.

### Poll demand (V184-4)

`swingbot/core/planning/plan_manager.py`:

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
        # prices is None (serial seam) with plans open -> leaves None; otherwise
        # PollDemand(tickers, priced) with the same filter as poll's `if not price or price <= 0`

def last_poll_demand() -> PollDemand | None: ...
    # None when config.INTRADAY_MANAGER_V2 is off or _MANAGER is None; else _MANAGER.last_poll_demand
```

`poll()` sets `self.last_poll_demand = None` as its first statement (before
the quiet-hours return) and calls `self._record_poll_demand(open_plans, prices)`
right after its batch block.

### Monitor checks (V184-5)

`swingbot/commands/scanning/loops.py`:

```python
async def _check_open_ticker(ticker: str, live: float) -> tuple[list, bool]:
    # (closed trades, errored) -- close_if_live_price_hit then check_near_tp_timeout,
    # same logs and same skip-on-raise as today
async def _check_open_tickers(tickers: list, live_prices: dict) -> tuple[list, list[str]]:
    # (all newly closed, check_errors) -- skips `not live or live <= 0` exactly as today
async def _run_plan_manager_tick() -> tuple[list, bool]:
    # (plan events, raised) -- same warning log as today; [] on raise
```

### Monitor stamp (V184-6, wired in V184-7)

New module `swingbot/commands/scanning/monitor_liveness.py`:

```python
WRITE_INTERVAL_S = 120
UNQUOTED_CAP = 20
PLAN_MANAGER_ERROR = "<plan manager>"

@dataclass
class TickRecord:
    outcome: str = "raised"                     # set to "ok" only after the tick body returns
    trade_tickers: list[str] | None = None      # None = trade read did not complete
    live_prices: dict[str, float] | None = None
    plan_demand: PollDemand | None = None       # plan_manager.PollDemand
    manager_raised: bool = False
    check_errors: list[str] = field(default_factory=list)
    fetch_failed: bool = False

def positions_of(rec: TickRecord) -> list[str] | None
    # None when trade_tickers is None or manager_raised; else sorted(trade ∪ plan_demand.demanded)
def unquoted_of(rec: TickRecord) -> list[str]
    # sorted, uncapped: trade tickers with `not live or live <= 0` (live_prices None = {}) ∪ plan_demand.unpriced
def check_errors_of(rec: TickRecord) -> list[str]
    # rec.check_errors + [PLAN_MANAGER_ERROR] when manager_raised

class MonitorLiveness:
    def __init__(self, started_at: dt.datetime | None = None) -> None
        # started_at defaults to now (UTC); priced_at None; _signature None; _written_at None
    def build(self, rec: TickRecord, now: dt.datetime) -> dict
        # the full `monitor` doc below; advances self.priced_at to `now` when
        # outcome == "ok" and positions is not None and unquoted == [] and check_errors == []
    def due(self, doc: dict, now: dt.datetime) -> bool
        # True on first write, when now - _written_at >= WRITE_INTERVAL_S, or when
        # (outcome, tuple(unquoted), fetch_failed, tuple(check_errors)) differs from the last write
    def written(self, doc: dict, now: dt.datetime) -> None

_STATE = MonitorLiveness()                      # process start; tests replace it via monkeypatch

def _write(doc: dict) -> None                   # runstate._update_heartbeat({"monitor": doc})
async def stamp_tick(rec: TickRecord, *, now: dt.datetime | None = None) -> bool
    # build -> due? -> await asyncio.to_thread(_write, doc) -> written; True when written.
    # Any exception: swallowed(log, "ops.monitor_stamp", ...) and False.
```

The `monitor` doc (JSON, UTC ISO via `isoformat(timespec="seconds")`):

```json
{"started_at": "...", "tick_at": "...", "outcome": "ok|raised",
 "positions": ["AAPL", "..."] | null, "unquoted": ["<= 20 sorted"], "unquoted_count": 0,
 "fetch_failed": false, "check_errors": [], "priced_at": "..." | null, "market_open": false}
```

`market_open = session.is_nyse_regular_session(now)`.

`trade_monitor` (V184-7) becomes:

```python
async def trade_monitor():
    rec = monitor_liveness.TickRecord()
    try:
        await _monitor_tick(rec)
        rec.outcome = "ok"
    finally:
        await monitor_liveness.stamp_tick(rec)

async def _monitor_tick(rec: "monitor_liveness.TickRecord") -> None: ...   # the old body, filling rec
```

### Watch script (V184-8, V184-9)

`scripts/ops/heartbeat_watch.sh` after both tasks:

- `heartbeat_check` (V184-8): the old main body as a function, `return` in place of each `exit 0`; sets global `HB_VERDICT`. Output and state are byte-identical to today.
- Flags (V184-9): `--monitor-age <s|absent|''>`, `--priced-age <s>`, `--market-open <true|false>`, `--positions <n|null>`; any of them sets `MON_GIVEN=1` and requires `--dry-run`. `--age` requires `--dry-run`, and `--dry-run` requires `--age` or a monitor flag, so bare `--dry-run` still exits 2. Dry-run defaults: priced age `0`, market open `false`, positions `0`, monitor age `0`.
- Main: `--test` unchanged; `HB_VERDICT=""`; run `heartbeat_check` unless (dry-run and no `--age`); run `monitor_check || record "$(now_iso) monitor verdict=error action=none"` unless (dry-run and `MON_GIVEN=0`); `exit 0`.
- Constants: `MONITOR_STATE_FILE="$ROOT/logs/monitor_watch.state"`, `MONITOR_STALE_S=300`, `STOPS_UNCHECKED_S=600` (or § Threshold decision), `MONITOR_SQL` on one line (formatted here for reading):

```sql
SELECT CASE WHEN NOT (doc ? 'monitor') THEN 'absent' ELSE concat_ws('|',
  coalesce(floor(extract(epoch FROM now() - (doc->'monitor'->>'tick_at')::timestamptz))::bigint::text, ''),
  coalesce(floor(extract(epoch FROM now() - greatest(coalesce((doc->'monitor'->>'priced_at')::timestamptz, (doc->'monitor'->>'started_at')::timestamptz), ((now() AT TIME ZONE 'America/New_York')::date + time '09:30') AT TIME ZONE 'America/New_York')))::bigint::text, ''),
  coalesce(doc->'monitor'->>'market_open', ''),
  CASE WHEN jsonb_typeof(doc->'monitor'->'positions') = 'array' THEN jsonb_array_length(doc->'monitor'->'positions')::text ELSE 'null' END,
  coalesce(doc->'monitor'->>'unquoted_count', '0'),
  coalesce((SELECT string_agg(value, ',') FROM jsonb_array_elements_text(coalesce(doc->'monitor'->'unquoted', '[]'::jsonb))), ''),
  coalesce(doc->'monitor'->>'fetch_failed', 'false'),
  coalesce((SELECT string_agg(value, ',') FROM jsonb_array_elements_text(coalesce(doc->'monitor'->'check_errors', '[]'::jsonb))), '')
) END FROM bot_heartbeat WHERE key = 'bot'
```

  Row fields: `tick_age|priced_age|market_open|positions|unquoted_count|unquoted|fetch_failed|check_errors`; the literal `absent` when the key is missing; empty output when the query fails.
- Functions: `read_monitor` (psql like `read_age`, `-tA`, returns the row or nothing), `monitor_verdict_for tick_age priced_age market_open positions` gives `not_deployed` (tick_age `absent`), then `unreadable` (tick_age not an integer), then `monitor_stale` (tick_age > `MONITOR_STALE_S`), then `stops_unchecked` (market_open `true` and positions `null` or > 0 and priced_age > `STOPS_UNCHECKED_S`; a non-integer priced_age in that case is `unreadable`), else `ok`. Also `monitor_message_for action verdict tick_age priced_age n tickers fetch_failed check_errors previous` and `monitor_check`.
- Log line: `<iso> monitor verdict=<v> tick_age_s=<a|none> priced_age_s=<p|none> market_open=<b|none> positions=<n|null|none> previous=<prev|none> action=<alert|recover|none>`, then one suffix: ` dry_run=1`, ` delivered=yes|failed|no-webhook`, ` suppressed=heartbeat-unreadable`.
- State machine: `action_for` reused against `logs/monitor_watch.state`. `not_deployed` logs only (action `none`, state untouched). `unreadable` while `HB_VERDICT=unreadable` logs ` suppressed=heartbeat-unreadable`, posts nothing and leaves state untouched. Otherwise it works like the heartbeat block: write state on action `none` or a delivered post; leave it untouched on no-webhook or a failed post.
- Messages (`<host>` = `${HOSTNAME:-the VM}`):
  - `alert:monitor_stale`: `[swingbot ops] Stop monitor STALE on <host>: last tick ended <tick_age>s ago (threshold 300s). Open stops are not being checked.` (`300` printed from `$MONITOR_STALE_S`)
  - `alert:stops_unchecked`: `[swingbot ops] Stops UNCHECKED on <host>: <n> position(s) not checked for <priced_age>s during the regular session (<tickers>; fetch_failed=<bool>; check_errors=<list>).`
  - `alert:unreadable`: `[swingbot ops] Stop monitor UNREADABLE on <host>: cannot read the monitor key from bot_heartbeat. Check docker compose ps (is db up?).`
  - `recover`: `[swingbot ops] Stop monitor RECOVERED on <host>: last tick ended <tick_age>s ago and stops are being checked (was <previous>).`

### Rollback (V184-10)

`scripts/ops/rollback_to.sh` echoes, after the "Scanning is PAUSED" line:
`REMINDER (v184): if the restored image predates v184, clear the stale monitor key: docker compose exec -T db psql -U swingbot -d swingbot -v ON_ERROR_STOP=1 -c "UPDATE bot_heartbeat SET doc = doc - 'monitor' WHERE key = 'bot'"`.

## Review Focus

- V184-4 and V184-7: an unknown never reads as zero. A raised tick or a raised manager must not advance `priced_at` and must not report `positions: []`.
- V184-7: the closes, `run_manager_tick`, the equity sample and the posts run in the same order with the same arguments as before; the parity test still counts one provider call.
- V184-8: a pure refactor; every pre-existing script test passes unmodified.
- V184-9: the monitor check can never change the heartbeat line, its state or its exit code.

## Parallelisation

| Task | May run alongside | Sequential edge and why |
|---|---|---|
| V184-1 | V184-2, V184-8, V184-10 (after V184-1's worktree step) | first task: creates the worktree; its threshold line is read by V184-9 (contract dependency) |
| V184-2 | V184-3, V184-8, V184-10 | disjoint file `session.py`; no contract dependency |
| V184-3 | V184-2, V184-8, V184-10 | after V184-1's worktree step only; owns `plan_manager.py` and `loops.py` while it runs |
| V184-4 | V184-8, V184-10 | after V184-3: same file `plan_manager.py` |
| V184-5 | V184-8, V184-10 | after V184-3: same file `loops.py` |
| V184-6 | V184-8, V184-10 | after V184-2 (`is_nyse_regular_session`) and V184-4 (`PollDemand`); new files only |
| V184-7 | V184-8, V184-10 | after V184-3, V184-4, V184-5, V184-6: wires all of them into `loops.py` |
| V184-8 | any of V184-2..V184-7, V184-10 | disjoint files `heartbeat_watch.sh` and its test; no contract dependency |
| V184-9 | V184-2..V184-7, V184-10 | after V184-8 (same file) and V184-1 (threshold value) |
| V184-10 | anything before V184-11 | disjoint files `rollback_to.sh`, `DEPLOY_HETZNER.md`, `test_rollback_to_shape.py` |
| V184-11 | none | after every code task: bump, the plan's single full-suite run, merge |
| V184-12 | none | after V184-11's merge and the normal production deploy; read-only on the VM |

At most 2 implementers at once (shared tree, CPU). Suggested pairs: V184-2 + V184-8 (while V184-1's measurement runs), V184-3 + V184-10, V184-4 + V184-9 (once V184-1 is done), V184-5 + V184-6.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-21-v184-stop-monitor-liveness_1-measurement-and-core-signals.md` | V184-1..V184-4 | worktree and the read-only threshold measurement, the NYSE regular-session helper, the per-tick fetch-failed flag, the poll-demand accessor |
| 2 | `2026-10-21-v184-stop-monitor-liveness_2-monitor-stamp.md` | V184-5..V184-7 | extract the monitor's check helpers, the `monitor_liveness` stamp module with throttle, wiring the stamp into `trade_monitor` with parity tests |
| 3 | `2026-10-21-v184-stop-monitor-liveness_3-watch-rollback-and-release.md` | V184-8..V184-12 | heartbeat block into a function, the monitor check and its verdicts, rollback docs and reminder, bump plus full suite plus merge, post-deploy verification |

## Task ledger

| Task | Title | Part | Model | Files created / modified | Creates (consumed later) |
|---|---|---|---|---|---|
| V184-1 | Worktree, and the read-only stops_unchecked threshold measurement | 1 | sonnet | C `docs/superpowers/results/<run-date>-v184-stops-unchecked-threshold.md`; M `docs/superpowers/plans/2026-10-21-v184-stop-monitor-liveness_0-index.md` (§ Threshold decision line) | worktree branch; the threshold value for `STOPS_UNCHECKED_S` |
| V184-2 | Holiday- and half-day-aware NYSE regular-session helper | 1 | sonnet | M `swingbot/core/market/session.py`; C `tests/market/test_session_nyse_regular.py` | `is_nyse_regular_session(now: dt.datetime \| None = None) -> bool` |
| V184-3 | Per-tick fetch-failed flag out of the bounded quote batch | 1 | sonnet | M `swingbot/core/planning/plan_manager.py`, `swingbot/commands/scanning/loops.py`; C `tests/planning/test_monitor_batch_status.py` | `reset_monitor_batch_status() -> None`, `mark_monitor_batch_failed() -> None`, `monitor_batch_failed() -> bool` |
| V184-4 | Poll-demand accessor: plan tickers poll() priced and did not price | 1 | opus | M `swingbot/core/planning/plan_manager.py`; C `tests/planning/test_poll_demand.py` | `PollDemand(demanded, priced)` with `.unpriced`; `PlanManager.last_poll_demand`; `PlanManager._record_poll_demand(open_plans, prices)`; module `last_poll_demand() -> PollDemand \| None` |
| V184-5 | Extract trade_monitor's per-ticker checks and manager tick (behaviour-preserving) | 2 | sonnet | M `swingbot/commands/scanning/loops.py`; C `tests/commands/test_trade_monitor_checks.py` | `_check_open_ticker(ticker, live) -> tuple[list, bool]`, `_check_open_tickers(tickers, live_prices) -> tuple[list, list[str]]`, `_run_plan_manager_tick() -> tuple[list, bool]` |
| V184-6 | monitor_liveness module: tick record, doc builder, priced_at, write throttle | 2 | sonnet | C `swingbot/commands/scanning/monitor_liveness.py`, `tests/commands/test_monitor_liveness.py` | `TickRecord`, `positions_of`, `unquoted_of`, `check_errors_of`, `MonitorLiveness(started_at=None)` with `build/due/written`, `_STATE`, `_write(doc)`, `stamp_tick(rec, *, now=None) -> bool`, `WRITE_INTERVAL_S`, `UNQUOTED_CAP`, `PLAN_MANAGER_ERROR` |
| V184-7 | Wire the stamp into trade_monitor: unknown defaults, finally stamp, parity | 2 | opus | M `swingbot/commands/scanning/loops.py`, `tests/commands/test_trade_monitor_shared_quote.py`; C `tests/commands/test_trade_monitor_liveness.py` | `_monitor_tick(rec) -> None`; the `monitor` heartbeat key in production |
| V184-8 | heartbeat_watch.sh: heartbeat block into a function (refactor) | 3 | sonnet | M `scripts/ops/heartbeat_watch.sh`, `tests/scripts/test_heartbeat_watch.py` | `heartbeat_check`, global `HB_VERDICT` |
| V184-9 | heartbeat_watch.sh: monitor check, verdicts, state file, dry-run flags | 3 | sonnet | M `scripts/ops/heartbeat_watch.sh`, `tests/scripts/test_heartbeat_watch.py`; C `tests/scripts/test_heartbeat_watch_monitor.py`, `tests/scripts/test_heartbeat_watch_monitor_sql.py` | `MONITOR_SQL`, `MONITOR_STALE_S`, `STOPS_UNCHECKED_S`, `MONITOR_STATE_FILE`, `read_monitor`, `monitor_verdict_for`, `monitor_message_for`, `monitor_check`; flags `--monitor-age --priced-age --market-open --positions` |
| V184-10 | Rollback: key-removal step in DEPLOY_HETZNER and rollback_to.sh reminder | 3 | haiku | M `scripts/ops/rollback_to.sh`, `docs/deploy/DEPLOY_HETZNER.md`, `tests/scripts/test_rollback_to_shape.py` | — |
| V184-11 | Bot patch bump, full suite, merge | 3 | sonnet | M `VERSION.json`, `swingbot/admin/version_history.json` (regenerated) | merged branch on `main` |
| V184-12 | Post-deploy read-only verification on production | 3 | sonnet | C `docs/superpowers/results/<run-date>-v184-post-deploy-verification.md` | — |
