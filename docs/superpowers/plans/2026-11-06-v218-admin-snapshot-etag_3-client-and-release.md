# v218 — Part 3: idle-tab throttle, release, deploy check and Results (V218-14..V218-16)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v206 — Admin under load](../specs/2026-11-05-v206-admin-under-load-design.md) § Plan 3 (P3-c, P3-d), § Rollout and rollback, § Results "Plan 2 after" (the idle tab at 16.5 per minute "needs a look in Plan 3").
**Index:** [`2026-11-06-v218-admin-snapshot-etag_0-index.md`](2026-11-06-v218-admin-snapshot-etag_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation`, `## Task ledger` and `## Handoff` live there and bind every task below.

Worktree for V218-14 and V218-15 up to the merge: `.claude/worktrees/2026-11-06-v218-admin-snapshot-etag` (branch of the same name), written `<wt>` below. `<main>` is the main checkout (`E:/Documents/Private/Projects/Discord-Bot`), `<scratchpad>` the session's scratchpad directory. Paths without a prefix are relative to `<wt>`.

Symbols this part consumes, created earlier (verify with `git grep -n` before starting):
`MARKET_DATA_MIN_INTERVAL_MS` (exists, `frontend/src/app/api/event-stream.ts:44`), `EventStream.changes(name, { minIntervalMs })` (exists, `event-stream.ts:118`),
`config.ADMIN_STORE_SNAPSHOT` (V218-2), `store_snapshot` / `snapshot_listener` (V218-3, V218-4), `build_identity.build_version()` (V218-7),
`conditional.conditional` and `CONDITIONAL_ATTR` (V218-8), `Server-Timing` `app;dur` and `snap;desc` (V218-9), `trades.closed_only_query` (V218-10b),
the v206 Results subsections `### Plan 3 version() gap (V218-1)`, `### Plan 3 build tag on the VM (V218-7)` and `### Plan 3 route audits (V218-10..12)`.

**Part 2 decisions this part carries:** the `/trades?status=CLOSED` shape is admitted only while `session.market_today() == fx_convert.berlin_today()` (06:00–24:00 Berlin) and the refresher is on; `sort=status` is not an admitted sort; the calendar routes are expected dropped (V218-11/12). The SPA's Trades page sends `/trades?page=1&per_page=10` (no status filter), so **the browser probe never requests the admitted shape**: V218-16 measures the closed view with its own read-only script.

# Phase 3 — the idle tab

### Task V218-14: Idle tab: `/market/updates` on the shared 30 s throttle, poll only when no recent sync

**Model:** sonnet — a contained store change with fake-timer specs; the throttle already exists and is reused, nothing is designed here.

**Files:**
- Modify: `frontend/src/app/stores/live-values.store.ts` (import at :4, `STATUS_POLL_MS` doc at :7-9, class doc at :48-52, `sync()` :130-141, `watchMarketEvents()` :192-201, `startPoll()` :213-218)
- Modify: `frontend/src/app/stores/live-values.store.spec.ts` (imports :7, `FakeEventStream` :11-31, `raiseMarket()` :57-61, test 'refetches on every market event' :88-93; new tests appended inside `describe('LiveValuesStore (v201)')`)

**Interfaces:**
- Consumes: `MARKET_DATA_MIN_INTERVAL_MS = 30_000` and `EventStream.changes(name, { minIntervalMs })` from `frontend/src/app/api/event-stream.ts` (exist, :44 and :118). The real throttle passes the first bump of a burst at once and collapses the rest into one trailing bump (`pass()`/`release()`, :218-233). One throttle is shared by every subscriber of the same event and interval, so the Dashboard, the tape and this store ride the same 30 s clock.
- Produces: nothing another task consumes. `STATUS_POLL_MS` stays exported with the same value.

**Why:** v206 "Plan 2 after" measured 33 idle-tab requests in 120 s (16.5 per minute, target under 10). `/market/updates` was 12 of them: `watchMarketEvents()` re-reads on every `market` event with no throttle, and the 60 s poll fires on top even right after an event-driven read. After this task the store reads at most once per 30 s per burst (plus one trailing read, so the last price of a burst is never lost), and the poll fires only when no read went out in the last 60 s. The poll exists for one case, a dead refresher that raises no events, and it still covers that case.

What stays: the start-up sync, the in-flight `again` coalescing, the hidden-tab skip, `watchStreamState()` (a stream going live still syncs at once), `requestRefresh()`, and every merge path. No template or layout changes, so the three-width check does not apply.

- [ ] **Step 1: Teach the spec's fake stream the real throttle, and space the existing events past it**

In `frontend/src/app/stores/live-values.store.spec.ts`, replace the import of `EventStream` (line 7) with:

```ts
import { EventStream, MARKET_DATA_MIN_INTERVAL_MS } from '../api/event-stream';
```

Replace the whole `FakeEventStream` class (lines 11-31) with this one. Its throttled view mirrors `EventStream.pass()`/`release()`, so the store is tested against the same leading-plus-trailing rule it gets in production, and `requested` records what the store asked for:

```ts
interface FakeThrottle {
  readonly name: string;
  readonly interval: number;
  readonly out: WritableSignal<number>;
  last: number;
  timer: ReturnType<typeof setTimeout> | null;
}

class FakeEventStream {
  readonly state = signal<'connecting' | 'live' | 'degraded'>('connecting');
  /** Every `changes()` call the store made, with its interval or null. */
  readonly requested: Array<{ name: string; minIntervalMs: number | null }> = [];
  private readonly counters = new Map<string, WritableSignal<number>>();
  private readonly throttles: FakeThrottle[] = [];

  private counterFor(name: string): WritableSignal<number> {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = signal(0);
      this.counters.set(name, counter);
    }
    return counter;
  }

  changes(name: string, options?: { minIntervalMs: number }): Signal<number> {
    this.requested.push({ name, minIntervalMs: options?.minIntervalMs ?? null });
    if (!options) return this.counterFor(name).asReadonly();
    const throttle: FakeThrottle = { name, interval: options.minIntervalMs, out: signal(0), last: -Infinity, timer: null };
    this.throttles.push(throttle);
    return throttle.out.asReadonly();
  }

  /** Same rule as EventStream.pass(): the leading bump at once, the rest of
   *  a burst as one trailing bump when the interval has run out. */
  raise(name: string): void {
    this.counterFor(name).update((n) => n + 1);
    for (const throttle of this.throttles) {
      if (throttle.name !== name) continue;
      const wait = throttle.last + throttle.interval - Date.now();
      if (wait <= 0) {
        if (throttle.timer !== null) clearTimeout(throttle.timer);
        this.release(throttle);
      } else if (throttle.timer === null) {
        throttle.timer = setTimeout(() => this.release(throttle), wait);
      }
    }
  }

  private release(throttle: FakeThrottle): void {
    throttle.timer = null;
    throttle.last = Date.now();
    throttle.out.update((n) => n + 1);
  }
}
```

Replace the `raiseMarket()` helper (lines 57-61) with three helpers. `raiseMarket()` now lets one throttle window pass first, so every existing test keeps its meaning (each of its events is a separate, spaced event). `raiseMarketNow()` raises without waiting, for the burst tests:

```ts
  /** One market event, a full throttle window after the last: each call is
   *  a separate, spaced event that the throttle lets through. */
  function raiseMarket(): void {
    vi.advanceTimersByTime(MARKET_DATA_MIN_INTERVAL_MS);
    TestBed.tick();
    raiseMarketNow();
  }

  /** One market event at the current fake time, no spacing. */
  function raiseMarketNow(): void {
    events.raise('market');
    TestBed.tick();
  }

  /** Move fake time on and let any trailing throttle bump reach the effect. */
  function advance(ms: number): void {
    vi.advanceTimersByTime(ms);
    TestBed.tick();
  }
```

The existing tests still hold with `raiseMarket()` spaced by 30 s. Every spaced event passes the throttle as a leading bump, and the poll at 60 s finds a sync less than 60 s old and stays quiet. 'an event during an in-flight sync runs one more sync after it' keeps its counts: the second spaced event arrives while the first request is still pending and sets `again`. 'a failed sync keeps every value and the cursor' keeps `[null, 'c1', 'c1']`.

Rename the test at lines 88-93 and keep its body:

```ts
  it('refetches on each market event spaced past the throttle window', () => {
    make([of(reply('c1'))]);
    raiseMarket();
    raiseMarket();
    expect(api.marketUpdates).toHaveBeenCalledTimes(3);
  });
```

- [ ] **Step 2: Write the failing specs**

Append inside `describe('LiveValuesStore (v201)', ...)`, after the test 'patchRows overlays the stored quote onto each row' (its closing `});` is the last line before the describe's own `});`):

```ts
  /* -- v218: the idle tab ---------------------------------------------- */

  it('asks for market events only through the shared 30 s throttle', () => {
    make([of(reply('c0'))]);
    const market = events.requested.filter((r) => r.name === 'market');
    expect(market).toEqual([{ name: 'market', minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS }]);
  });

  it('a burst of five market events in 30 s sends one leading and one trailing request', () => {
    make([of(reply('c0'))]);
    expect(api.marketUpdates).toHaveBeenCalledTimes(1);
    for (const gapMs of [1_000, 4_000, 5_000, 5_000, 5_000]) {
      advance(gapMs);
      raiseMarketNow();
    }
    // t = 20 s: the start-up sync and the leading request only.
    expect(api.marketUpdates).toHaveBeenCalledTimes(2);
    advance(11_000);
    // t = 31 s: the trailing request, 30 s after the leading one.
    expect(api.marketUpdates).toHaveBeenCalledTimes(3);
    advance(29_000);
    // t = 60 s: the poll finds a sync 29 s old and stays quiet.
    expect(api.marketUpdates).toHaveBeenCalledTimes(3);
  });

  it('a market event at 50 s keeps the 60 s poll from firing', () => {
    make([of(reply('c0'))]);
    advance(50_000);
    raiseMarketNow();
    expect(api.marketUpdates).toHaveBeenCalledTimes(2);
    advance(10_000);
    expect(api.marketUpdates).toHaveBeenCalledTimes(2);
    advance(STATUS_POLL_MS);
    // t = 120 s: the last sync is 70 s old, so the poll reads.
    expect(api.marketUpdates).toHaveBeenCalledTimes(3);
  });

  it('with no events the poll still fires every 60 s (a dead refresher raises none)', () => {
    make([of(reply('c0'))]);
    advance(STATUS_POLL_MS);
    advance(STATUS_POLL_MS);
    advance(STATUS_POLL_MS);
    expect(api.marketUpdates).toHaveBeenCalledTimes(4);
  });

  it('a hidden tab skips the poll', () => {
    make([of(reply('c0'))]);
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    try {
      advance(STATUS_POLL_MS);
      expect(api.marketUpdates).toHaveBeenCalledTimes(1);
    } finally {
      delete (document as unknown as { hidden?: boolean }).hidden;
    }
    advance(STATUS_POLL_MS);
    expect(api.marketUpdates).toHaveBeenCalledTimes(2);
  });

  it('a stream going live still syncs at once, inside the throttle window', () => {
    make([of(reply('c0'))]);
    raiseMarketNow();
    expect(api.marketUpdates).toHaveBeenCalledTimes(2);
    events.state.set('live');
    TestBed.tick();
    expect(api.marketUpdates).toHaveBeenCalledTimes(3);
  });
```

- [ ] **Step 3: Run the spec to see the new tests fail**

```bash
node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/stores/live-values.store.spec.ts > "<wt>/.superpowers/v218-14-red.log" 2>&1; echo "exit $?"
grep -n "FAIL\|Tests \|AssertionError" "<wt>/.superpowers/v218-14-red.log" | tail -20
```

Expected: a non-zero exit. 'asks for market events only through the shared 30 s throttle' fails (`minIntervalMs: null`). The burst test fails (6 calls, not 2). 'a market event at 50 s keeps the 60 s poll from firing' fails (3 calls at t = 60 s). 'with no events the poll still fires', 'a hidden tab skips the poll' and the stream-live test may already pass: they pin behaviour that must survive. Every pre-existing test passes, because Step 1 only spaced its events.

- [ ] **Step 4: Implement in `live-values.store.ts`**

Replace line 4:

```ts
import { EventStream, MARKET_DATA_MIN_INTERVAL_MS } from '../api/event-stream';
```

Replace lines 7-9:

```ts
/** How often status is re-read when no read went out in that time: the only
 *  thing that notices a dead refresher, which raises no events. A tab that
 *  synced within the last STATUS_POLL_MS skips the tick (v218). */
export const STATUS_POLL_MS = 60_000;
```

Replace the class comment at lines 48-52:

```ts
/**
 * v201: the one place live prices live. `/market/updates` is read at start,
 * on a stream going live, on `market` events through the shared 30 s
 * throttle (v218: one leading and one trailing read per burst), and on a 60 s
 * poll that fires only when no read went out in the last 60 s -- so a price
 * reaches every table that shows it without each page refetching.
 */
```

Add one field after `private again = false;` (line 60):

```ts
  /** When this tab last sent `/market/updates` (ms since epoch); the poll defers to it. */
  private lastSyncAt = -Infinity;
```

Replace `sync()` (lines 130-141). The stamp is taken only when a request actually goes out, never on the `again` path:

```ts
  private sync(): void {
    if (this.inFlight) {
      this.again = true;
      return;
    }
    this.inFlight = true;
    this.lastSyncAt = Date.now();
    this.api.marketUpdates(this.cursor).subscribe({
      next: (reply) => this.merge(reply),
      error: () => this.finish(),
      complete: () => this.finish(),
    });
  }
```

Replace `watchMarketEvents()` (lines 192-201):

```ts
  private watchMarketEvents(): void {
    // v218: the refresher raises `market` after every cycle, and an
    // unthrottled read per event was the idle tab's biggest single source
    // (12 of 33 requests in 120 s, v206 "Plan 2 after"). The shared throttle
    // keeps the first event's read immediate and folds the rest of a burst
    // into one trailing read, so the burst's last price still lands.
    const changes = this.events.changes('market', { minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS });
    let seen = untracked(changes);
    effect(() => {
      const n = changes();
      if (n === seen) return;
      seen = n;
      this.sync();
    });
  }
```

Replace `startPoll()` (lines 213-218) with it and one helper:

```ts
  private startPoll(destroyRef: DestroyRef): void {
    const timer = setInterval(() => this.pollIfQuiet(), STATUS_POLL_MS);
    destroyRef.onDestroy(() => clearInterval(timer));
  }

  /** The poll covers silence only: a hidden tab, or a tab that read within
   *  the last STATUS_POLL_MS, has nothing to catch up on. */
  private pollIfQuiet(): void {
    if (typeof document !== 'undefined' && document.hidden) return;
    if (Date.now() - this.lastSyncAt >= STATUS_POLL_MS) this.sync();
  }
```

- [ ] **Step 5: Run the store spec and every spec that wires the store or the market event**

```bash
node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/stores/live-values.store.spec.ts --include src/app/stores/dashboard.store.spec.ts --include src/app/shell/refresher-banner.spec.ts --include src/app/shell/tape/tape.spec.ts --include src/app/shell/shell.spec.ts --include src/app/api/event-stream.spec.ts > "<wt>/.superpowers/v218-14.log" 2>&1 && echo PASS || echo FAIL
grep -n "Tests \|Test Files " "<wt>/.superpowers/v218-14.log" | tail -4
```

Expected: `PASS`, with `0 failed`. `dashboard.store.spec.ts` replaces `LiveValuesStore` with a fake, and its own `FakeEventStream` already accepts `options` (:50), so it only proves nothing else broke. A `FAIL`: read only the failing test names and assertion lines in the log, fix, and rerun that one spec alone.

Then lint the two files:

```bash
cd "<wt>/frontend" && npx eslint src/app/stores/live-values.store.ts src/app/stores/live-values.store.spec.ts > "<wt>/.superpowers/v218-14-lint.log" 2>&1 && echo "PASS lint" || echo "FAIL lint"
```

Expected: `PASS lint`. CI's frontend job builds and type-checks after the push.

- [ ] **Step 6: Commit (in the worktree)**

```bash
git -C "<wt>" add frontend/src/app/stores/live-values.store.ts frontend/src/app/stores/live-values.store.spec.ts
git -C "<wt>" commit -m "perf(ui): /market/updates rides the shared 30 s market throttle, the 60 s poll covers silence only (v218 V218-14)

The idle Dashboard sent 12 of its 33 requests per 120 s to /market/updates:
one per market event, unthrottled, plus the poll on top. Market events now
go through EventStream's shared 30 s throttle (a leading read plus one
trailing read per burst), and the poll fires only when no read went out in
the last 60 s, so it still notices a dead refresher.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 4 — release, deploy check and Results

### Task V218-15: Release: docs, version bump, merge, pipeline watch

**Model:** sonnet — a scripted release and a gated merge; the one prose change is a rollback paragraph whose facts are fixed by V218-2 and `known-traps.md`.

**Files:**
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (§ Rolling back: new paragraph "Switching the v218 admin snapshot off without a rollback", placed after the "The admin's server is chosen inside the image (v148)" paragraph and before "That leaves `main` ahead of production")
- Modify: `VERSION.json` (ui patch, bot patch; index header `Bump: ui patch, bot patch`)
- Modify: `swingbot/admin/version_history.json` (regenerated, never hand-edited)

**Interfaces:**
- Consumes: every task V218-1..V218-14 committed on branch `2026-11-06-v218-admin-snapshot-etag`. Also the v206 Results headings `### Plan 3 version() gap (V218-1)`, `### Plan 3 build tag on the VM (V218-7)` and `### Plan 3 route audits (V218-10..12)`, `config.ADMIN_STORE_SNAPSHOT` (V218-2, Settings section "Admin UI"), `scripts/ops/env_set.py` (exists: edits the VM `.env` in place and appends a missing key), and `config.auto_reload_if_changed()` (exists, `swingbot/config.py:1851`; the admin calls it on every request, `admin/app.py` `_reload_env_if_changed`).
- Produces: the release on `main` (two version commits, the regenerated history, the merge commit) and a green pipeline, which V218-16 deploys and measures.

**Gates (in this order, none skipped):**

1. **Partner approval before anything reaches `main`.** A push to `main` deploys to production by itself (CI → Hetzner, `docs/deploy/DEPLOY_HETZNER.md`). So the merge and the push wait for the partner's explicit yes in Step 7, asked through `AskUserQuestion`. With no yes there is no merge and no push. The branch stays as it is, and the task stops there.
2. **`mirror-prod` rules.** This task touches production not at all. The deploy is the CI pipeline.

No full-suite run: CI runs it after the push (Step 9).

- [ ] **Step 1: Check the preconditions**

```bash
git -C "<wt>" log --oneline main..HEAD > "<scratchpad>/v218-15-log.txt"; wc -l < "<scratchpad>/v218-15-log.txt"
grep -o "V218-[0-9]*b\?" "<scratchpad>/v218-15-log.txt" | sort -u | tr '\n' ' '; echo
grep -n "^### Plan 3 version() gap (V218-1)\|^### Plan 3 build tag on the VM (V218-7)\|^### Plan 3 route audits (V218-10..12)" "<wt>/docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md"
git -C "<wt>" status --short
```

Expected: the id list names every ledger row from V218-1 to V218-14, including `V218-10b` and any `b` row the controller added to the ledger since (`V218-13b` if it was split). All three headings are found and the status is clean. **A missing id or heading: stop and report it.** That task has not landed.

- [ ] **Step 2: Narrow verification of everything this plan touched**

The `admin`, `admin-perf` and `tests/db/` tests reach Postgres, so run `/replicate-prod-db` first if no task in this session has (the shared `swing-db`, port 56789). Then run one file at a time, never the full suite:

```bash
cd "<wt>" && for t in tests/db/test_v218_store_versions.py tests/test_config_v218_keys.py tests/admin/test_snapshot_listener.py tests/admin/test_no_double_watcher.py tests/admin/test_api_v1_cancel_precision.py tests/admin/test_watchlist_rows.py tests/admin/test_build_identity.py tests/scripts/test_admin_endpoint_timing.py; do python scripts/dev/testrun.py file "$t" > "<wt>/.superpowers/v218-$(basename "$t" .py).log" 2>&1 && echo "PASS $t" || echo "FAIL $t"; done
cd "<wt>" && python scripts/dev/testrun.py suite admin-perf > "<wt>/.superpowers/v218-admin-perf.log" 2>&1 && echo "PASS suite admin-perf" || echo "FAIL suite admin-perf"
cd "<wt>" && python scripts/dev/complexity_gate.py > "<wt>/.superpowers/v218-complexity.log" 2>&1 && echo "PASS complexity" || echo "FAIL complexity"
node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/stores/live-values.store.spec.ts > "<wt>/.superpowers/v218-ng.log" 2>&1 && echo "PASS ng" || echo "FAIL ng"
```

The `admin-perf` suite covers every V218 file under `tests/admin_perf/`: `test_store_generation.py`, `test_store_snapshot.py`, `test_memo_isolation.py`, `test_snapshot_goldens.py`, `test_conditional.py`, `test_server_timing.py`, `test_trades_conditional_audit.py`, `test_calendar_conditional_audit.py`, `test_calendar_day_conditional_audit.py`, `test_conditional_routes.py`, and the goldens and budgets they must leave unchanged.

Expected: eight `PASS` file lines, `PASS suite admin-perf`, `PASS complexity`, `PASS ng`. `test_config_v218_keys.py` sits in whichever suite holds the root config tests. If V218-2 also touched a settings-page test (its "count fields per section" check), add that file to the loop. A `FAIL`: read only that log's failing test names and assertion lines, fix, and rerun that one file alone. `list_trades` must still read `32` in `scripts/dev/complexity_baseline.json`, never more.

- [ ] **Step 3: Write the rollback paragraph in `DEPLOY_HETZNER.md`**

In `<wt>/docs/deploy/DEPLOY_HETZNER.md`, § Rolling back, insert this between the paragraph that starts "**The admin's server is chosen inside the image (v148).**" and the line "That leaves `main` ahead of production, which is deliberate":

````markdown
**Switching the v218 admin snapshot off without a rollback.** From v218 the
admin keeps a per-process snapshot of the trade, plan and journal-note
records between requests. It sends `ETag`/304 on the allow-listed `/trades`
closed view, and every `/api` response's `Server-Timing` ends with
`snap;desc=hit|miss|off`. One switch turns both features off and restores the
v205 Layer 1 reads exactly: `ADMIN_STORE_SNAPSHOT=off`. The admin gets no
SIGHUP. It re-reads `.env` on its next request when the file's mtime has
changed (`config.auto_reload_if_changed()`), so no restart is needed. Set it
**in place**, never with `sed -i`: `.env` is a single-file bind mount, and a
rename leaves the containers reading the old inode
(`docs/claude/known-traps.md` § Editing production `.env` with `sed -i`):

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py ADMIN_STORE_SNAPSHOT off"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin grep ADMIN_STORE_SNAPSHOT /app/.env"
```

The Settings page (section "Admin UI") writes the same key in place too.
Check it took: any `/api/v1/health` response's `Server-Timing` now ends
`snap;desc=off`, and `/api/v1/trades?status=CLOSED` carries no `ETag`.
Switch back with the same command and `on`. Like any VM change, record it
per the `mirror-prod` skill. A full image rollback needs none of this: the
build identity in every tag changes with the image, so a browser never gets
a 304 for a body another image produced.
````

Then check the section still reads in order:

```bash
python "<wt>/scripts/dev/doc_section.py" "<wt>/docs/deploy/DEPLOY_HETZNER.md" "Rolling back" > "<scratchpad>/v218-rollback.txt"; grep -n "v148)\|Switching the v218\|That leaves" "<scratchpad>/v218-rollback.txt"
```

Expected: the three markers in that order (v148, then v218, then "That leaves"). Exit 2 from `doc_section.py`: grep the file itself with the same pattern.

```bash
git -C "<wt>" add docs/deploy/DEPLOY_HETZNER.md
git -C "<wt>" commit -m "docs(deploy): switch the v218 admin snapshot and ETags off in place with ADMIN_STORE_SNAPSHOT=off (v218 V218-15)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Bump `ui` and `bot` as two release commits**

`VERSION.json` is checked out with CRLF line endings, and the script keeps whatever the file has. Read the current values, never assume them:

```bash
python - "<wt>/VERSION.json" ui <<'EOF'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
path, line = Path(sys.argv[1]), sys.argv[2]
raw = path.read_bytes()
nl = "\r\n" if b"\r\n" in raw else "\n"
data = json.loads(raw.decode("utf-8"))
major, minor, patch = (int(x) for x in data[line].split("."))
data[line] = f"{major}.{minor}.{patch + 1}"
data[f"{line}_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H-%M-%S")
path.write_bytes((json.dumps(data, indent=2).replace("\n", nl) + nl).encode("utf-8"))
print(line, data[line])
EOF
git -C "<wt>" diff --stat VERSION.json
```

Expected: `ui <x.y.z+1>`, and the diff touches 2 lines. If it shows the whole file, the line endings or indent differ: restore with `git -C "<wt>" checkout VERSION.json` and match the original format. Commit:

```bash
git -C "<wt>" add VERSION.json
git -C "<wt>" commit -m "release(ui): <new ui> -- the idle tab reads /market/updates through the shared 30 s throttle (v218)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Run the same script with `bot` instead of `ui`, then:

```bash
git -C "<wt>" add VERSION.json
git -C "<wt>" commit -m "release(bot): <new bot> -- admin store snapshot, ETag/304 on the closed /trades view, Server-Timing app and snap (v218)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Regenerate the version history and check it**

The generator walks `git log` for `VERSION.json`, so it runs **after** both release commits:

```bash
cd "<wt>" && python scripts/dev/build_version_matrix.py > "<scratchpad>/v218-matrix.log" 2>&1; echo "exit $?"
cd "<wt>" && python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py > "<scratchpad>/v218-matrix-test.log" 2>&1 && echo PASS || echo FAIL
git -C "<wt>" add swingbot/admin/version_history.json
git -C "<wt>" commit -m "chore(ui,bot): <new ui> / <new bot> -- admin snapshot and ETag, quieter idle tab (v218)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C "<wt>" show --stat HEAD | tail -3
```

Expected: `exit 0`, `PASS`. The stat lists only `swingbot/admin/version_history.json`, and its newest pair is the two new versions, never `"commit": "uncommitted"`.

- [ ] **Step 6: Check the release did not break the narrow set**

Version bumps touch `VERSION.json`, which `build_identity.build_version()` hashes (V218-7). Rerun the two files that read it:

```bash
cd "<wt>" && for t in tests/admin/test_build_identity.py tests/admin_perf/test_conditional_routes.py; do python scripts/dev/testrun.py file "$t" > "<wt>/.superpowers/v218-post-bump-$(basename "$t" .py).log" 2>&1 && echo "PASS $t" || echo "FAIL $t"; done
```

Expected: two `PASS` lines. A test that pinned a literal `build_version()` value is a test bug: fix it to compare against `build_version()` computed in the test, commit scoped, rerun that file alone.

- [ ] **Step 7: Deploy gate: ask the partner**

Ask through `AskUserQuestion`, one question, recommended option first:

- Question: "v218 is released on its branch (ui <new ui>, bot <new bot>; narrow tests green). Merging into `main` and pushing deploys it to production through CI. The snapshot is on by default (`ADMIN_STORE_SNAPSHOT=on`) and switches off in place without a redeploy (DEPLOY_HETZNER § Rolling back). Deploy now?"
- Options: "Merge and deploy now (Recommended)" / "Not yet: leave the branch unmerged".

"Not yet": stop here and report the branch head and the two versions. Do not merge, push or probe. Any other answer is not a yes: ask again or stop.

- [ ] **Step 8: Merge into `main` and push (only after the yes)**

Invoke the `worktree-lifecycle` skill for the merge, because another session may be committing on `main`. Then:

```bash
git -C "<main>" fetch origin
git -C "<main>" status --short --branch
git -C "<main>" log --oneline -1 origin/main
```

Expected: `main` is not behind `origin/main` (pull with `--ff-only` first if it is), and no uncommitted change in `<main>` touches a file this plan changed. Uncommitted files of another session stay as they are. Never stash or reset them.

```bash
git -C "<main>" merge --no-ff 2026-11-06-v218-admin-snapshot-etag -m "merge: v218 -- admin store snapshot, ETag/304 on the closed /trades view, Server-Timing app and snap, quieter idle tab (v206 Plan 3)"
git -C "<main>" push origin main
```

A merge conflict: stop, run `git -C "<main>" merge --abort`, and report the conflicting paths. Never resolve a conflict in a file another session owns without asking.

- [ ] **Step 9: Watch the pipeline**

```bash
gh run list --branch main --limit 1 --json databaseId,status,conclusion
```

Then run `gh run watch <id> --exit-status` with `run_in_background` and wait for its exit notification (do not poll). Green: the task is done, and V218-16 starts. Red: `gh run view <id> --log-failed > "<scratchpad>/v218-ci.log"`, read only the failing test names and assertion lines, and fix each in `<main>` (one file at a time with `testrun.py file`). Commit scoped, push, and watch again (`working-conventions.md` § Pipeline watch). Each fix push deploys too, and the Step 7 yes covers fixes to this release only.

### Task V218-16: Deploy check, probe during a scan and idle, Results, close-out

**Model:** sonnet — read-only production checks and a measurement run; every figure is generated by a script, none judged.

**Files:**
- Modify: `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (`## Results` → new `### Plan 3 after (committed probe)`, appended at the end of the file, after every other v218 subsection)

**Interfaces:**
- Consumes: the merged and deployed release from V218-15. The probe CLI `scripts/ops/admin_browser_probe.py` (`--date --out [--image-tag]`) and its helpers `load_credentials`, `default_env_path`, `_login`, `_spread`, `normalise_endpoint` (all exist). Its `probe.json` shape is `{"raw": {meta, pages[{round, route, calls[{url, status, ttfb_ms, server_timing, ...}], scan_running}], idle{calls, window_s}}, "report": {meta, label, goal, endpoints[{endpoint, n, median, p90, max, thin}], idle{rpm}}}`. Plan 2's reference run is `<main>/.superpowers/probe/v217-after-1/probe.json` (label `mixed`, git-ignored). The `Server-Timing` format comes from V218-9: `total;dur=…, db;dur=…;desc="N statements", app;dur=…, snap;desc=hit|miss|off`.
- Produces: the table the spec's Plan 3 result rests on, and the close-out.

**Two facts shape the measurement:**
1. **The admitted shape is open only 06:00–24:00 Berlin, with the refresher on.** `closed_only_query` (V218-10b) also requires `session.market_today() == fx_convert.berlin_today()`, and `sort=status` is not admitted. Every ETag check below runs inside that window. Git Bash has no timezone data, so Berlin is `date -u` plus 1 h in winter (CET, until 2027-03-28). The scan window (15:30–22:00 Berlin) lies inside it.
2. **The browser probe never requests the admitted shape.** The SPA's Trades page sends `/trades?page=1&per_page=10`, which may include open rows, so it carries no ETag. The probe therefore measures the snapshot (`snap;desc` share, the unfiltered `/trades` TTFB) and the idle tab. Step 6's own script measures the closed view and its 304s. Calendar routes are expected dropped (V218-11/12), and the Results say whichever the audits recorded.

**Gates:** production is read-only throughout (`bash scripts/ops/ssh-hetzner.sh`, standing permission). Logging in through the session API is what the probe does too, and nothing else is written. A VM change of any kind (a restart, an `.env` edit, the kill switch) means stop, invoke `mirror-prod`, and record it before this task counts as done. The credentials are read inside scripts and never printed. A probe run counts only when they are absent from its output (Step 5).

- [ ] **Step 1: Confirm production runs the new code (read-only)**

Write `<scratchpad>/v218_check.py`. It runs inside the admin container, logs in over `localhost` with the container's own `ADMIN_USERNAME`/`ADMIN_PASSWORD` (from `env_file`, never printed), and prints only statuses, booleans and the `snap` value:

```python
import http.cookiejar, json, os, re, urllib.error, urllib.request

BASE = f"http://localhost:{os.environ.get('ADMIN_PORT') or 1234}/api/v1"
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(path, method="GET", body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with opener.open(req, timeout=120) as resp:
            return resp.status, resp.headers
    except urllib.error.HTTPError as err:
        return err.code, err.headers


status, _ = call("/session", "POST", {"username": os.environ["ADMIN_USERNAME"],
                                      "password": os.environ["ADMIN_PASSWORD"]})
print("login:", status)
from swingbot import config
print("switch:", config.ADMIN_STORE_SNAPSHOT)
_, health = call("/health")
timing = health.get("Server-Timing") or ""
print("server-timing names:", re.findall(r"(?:^|, )(\w+);", timing),
      "| snap:", (re.search(r"snap;desc=(\w+)", timing) or [None, None])[1])
closed = "/trades?status=CLOSED&page=1&per_page=10"
first, h1 = call(closed)
tag = h1.get("ETag")
print("closed 1st:", first, "| etag:", bool(tag), "| weak:", bool(tag and tag.startswith('W/"')),
      "| cache-control:", h1.get("Cache-Control"))
second, h2 = call(closed, headers={"If-None-Match": tag} if tag else None)
print("closed revalidate:", second, "| same etag:", h2.get("ETag") == tag)
for path in ("/trades?page=1&per_page=10", "/dashboard"):
    code, h = call(path)
    print(path, code, "| etag:", "ETag" in h, "| cache-control:", h.get("Cache-Control"))
```

Then, inside the window (Fact 1):

```bash
date -u +%H:%M
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose ps --format '{{.Image}}' admin"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python -" < "<scratchpad>/v218_check.py"
```

Expected: an image reference (keep it as `<tag>`), then `login: 200` and `switch: on`. The server-timing names are `['total', 'db', 'app', 'snap']` with a `snap` value. Next comes `closed 1st: 200 | etag: True | weak: True | cache-control: private, no-cache` and then `closed revalidate: 304 | same etag: True`. Both the unfiltered `/trades` and `/dashboard` show `etag: False | cache-control: no-store`.

- Names without `app`/`snap`: the deploy has not landed. Wait a few minutes and repeat. Never probe the old image.
- `etag: False` on the closed view: check the three admission inputs read-only before anything else. Is it 06:00–24:00 Berlin? Is the refresher running (`docker compose ps refresher`)? Is the listener connected? A `snap: off` on a second `/health` call a few seconds later means the listener is down. Report the finding to the partner. Never flip a switch.
- `login: 200` and then `401` statuses everywhere: the session cookie is `Secure`-only and urllib will not send it over plain `http://localhost`. Run Step 4's script now instead (it goes through `https://bomeo-capital.com`; its `cold_with_etag` and `revalidate_304` answer the same questions), and take the `Server-Timing` names from any `server_timing` field in the probe's `probe.json` call records (Step 3). Say in the Results which route was used.
- `closed revalidate: 200`: a bump moved the tag between the two calls (a trade write mid-scan does that). Rerun the script once. A second 200 with the same tag is a defect: report it, do not record a result.

- [ ] **Step 2: Wait for a scan, then confirm it**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python -c 'from swingbot.core.scanning.runstate import is_scan_running; print(is_scan_running())'"
```

Expected: `True`. On `False`, check again every few minutes. Never start the run on `False`.

- [ ] **Step 3: Run the probe in the background**

The output goes under `<main>` so it survives `/close-out` removing the worktree (`.superpowers/` is git-ignored). The run takes about an hour, so start it with `run_in_background` and wait for the exit notification:

```bash
python "<main>/scripts/ops/admin_browser_probe.py" --date 2026-11-03 --out "<main>/.superpowers/probe/v218-after" --image-tag "<tag>" > "<main>/.superpowers/probe/v218-after.log" 2>&1
```

Expected: exit 0 and the last log line `probe: <label> run, 36 pages -> ...`. Exit 2 is a failed login (the log names the HTTP status only): fix the cause and rerun from Step 2.

- [ ] **Step 4: Measure the closed view while the scan still runs**

Run this right after the probe, after Step 2's check says `True` again. Write `<scratchpad>/v218_closed_view.py`. It reuses the probe's login (credentials stay inside it) and times 20 rounds of a cold GET followed by a revalidation:

```python
import json, re, sys, time
from pathlib import Path

sys.path.insert(0, sys.argv[1])
import admin_browser_probe as probe
from playwright.sync_api import sync_playwright

BASE, OUT, ROUNDS = probe.DEFAULT_BASE, Path(sys.argv[2]), 20
URL = f"{BASE}/api/v1/trades?status=CLOSED&page=1&per_page=10"


def timed(context, headers=None):
    start = time.perf_counter()
    resp = context.request.get(URL, headers=headers or {}, timeout=120_000)
    ms = round((time.perf_counter() - start) * 1000, 1)
    snap = re.search(r"snap;desc=(\w+)", resp.headers.get("server-timing") or "")
    return {"status": resp.status, "ms": ms, "etag": resp.headers.get("etag"), "snap": snap and snap.group(1)}


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    try:
        context = browser.new_context(service_workers="block")
        probe._login(context, BASE, probe.load_credentials(probe.default_env_path()))
        scan = [probe._scan_sample(context, BASE)]
        cold, warm = [], []
        for _ in range(ROUNDS):
            cold.append(timed(context))
            tag = cold[-1]["etag"]
            warm.append(timed(context, {"If-None-Match": tag}) if tag else {"status": None, "ms": None, "etag": None, "snap": None})
            time.sleep(3)
        scan.append(probe._scan_sample(context, BASE))
    finally:
        browser.close()

summary = {
    "scan_running": scan,
    "cold_200": probe._spread(c["ms"] for c in cold if c["status"] == 200),
    "cold_with_etag": sum(1 for c in cold if c["etag"]),
    "revalidate_304": probe._spread(w["ms"] for w in warm if w["status"] == 304),
    "revalidate_200": sum(1 for w in warm if w["status"] == 200),
    "snap": {k: sum(1 for c in cold + warm if c["snap"] == k) for k in ("hit", "miss", "off")},
}
OUT.write_text(json.dumps({"cold": cold, "warm": warm, "summary": summary}, indent=2), encoding="utf-8")
print(json.dumps(summary))
```

```bash
python "<scratchpad>/v218_closed_view.py" "<main>/scripts/ops" "<main>/.superpowers/probe/v218-closed-view.json"
```

Expected: one JSON line with `scan_running` `[true, true]`, `cold_with_etag: 20`, a `revalidate_304` spread with `n` near 20, and `snap` counts. A `false` in `scan_running`: keep the file, and Step 7 says the closed view was measured partly outside a scan. `cold_with_etag: 0`: go back to Step 1's diagnosis. Nothing is recorded until it is explained.

- [ ] **Step 5: Verify the probe run: label, shape, no credential**

The two `.env` values are read inside the script and only a boolean is printed:

```bash
python - "<main>/.superpowers/probe/v218-after" "<main>/.env" <<'EOF'
import json, re, sys
from pathlib import Path
out, env = Path(sys.argv[1]), Path(sys.argv[2])
pattern = re.compile(r"\s*(?:export\s+)?(ADMIN_USERNAME|ADMIN_PASSWORD)\s*=\s*(.*?)\s*$")
values = [m.group(2).strip('"').strip("'") for m in map(pattern.match, env.read_text(encoding="utf-8").splitlines()) if m]
texts = [(out / "probe.json").read_text(encoding="utf-8"), (out / "probe.md").read_text(encoding="utf-8")]
print("credentials absent:", len(values) == 2 and all(v not in t for v in values for t in texts))
report = json.loads(texts[0])["report"]
print("label:", report["label"], "| pages:", len(report["pages"]), "| idle rpm:", report["idle"]["rpm"])
assert len(report["pages"]) == 36
EOF
```

Expected: `credentials absent: True` and `label: <label> | pages: 36 | idle rpm: <n>`. `credentials absent: False`: delete the run directory and its log at once, tell the partner, and record nothing. Label `scan`: continue. Label `mixed` or `quiet`: rename the directory to `v218-after-<label>-1` and rerun once from Step 2. A second non-`scan` run: ask through `AskUserQuestion` "Two v218 probe runs came out `<label>` (scans run back to back, as in Plan 2). Record the latest one as 'Not a strict scan run', like Plan 2's?" Offer "Record it, labelled as Plan 2's was (Recommended)" / "Rerun during the next scan session". Plan 2's reference was itself `mixed`, so a `mixed` run is the like-for-like comparison.

- [ ] **Step 6: Generate the table from the runs**

No figure is retyped. Write `<scratchpad>/v218_compare.py`:

```python
import json, re, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, sys.argv[1])
import admin_browser_probe as probe

after = json.loads((Path(sys.argv[2]) / "probe.json").read_text(encoding="utf-8"))
ref_file = Path(sys.argv[3]) / "probe.json"
ref = json.loads(ref_file.read_text(encoding="utf-8")) if ref_file.exists() else None
closed = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))["summary"]
WATCHED = ("/trades", "/dashboard", "/live", "/market/updates", "/market/tape", "/system/scan", "/health")


def fmt(s):
    if s is None or not s["n"]:
        return "-"
    tail = f"max {s['max']} (thin)" if s["thin"] else f"p90 {s['p90']} / max {s['max']}"
    return f"{tail} ms (n {s['n']}, median {s['median']})"


def endpoint(doc, name):
    return fmt(next((r for r in doc["report"]["endpoints"] if r["endpoint"] == name), None)) if doc else "-"


def calls(doc):
    return [c for p in doc["raw"]["pages"] for c in p["calls"]]


def snap_share(doc):
    seen = Counter((re.search(r"snap;desc=(\w+)", c.get("server_timing") or "") or [None, "absent"])[1]
                   for c in calls(doc))
    total = sum(seen.values()) or 1
    return ", ".join(f"{k} {round(100 * v / total)}%" for k, v in sorted(seen.items()))


def idle_counts(doc):
    if doc is None:
        return "-"
    n = Counter(probe.normalise_endpoint(c["url"]) for c in doc["raw"]["idle"]["calls"])
    return ", ".join(f"`{k}` {v}" for k, v in n.most_common())


rows = [("Label", ref["report"]["label"] if ref else "-", after["report"]["label"])]
rows += [(f"`{name}` TTFB", endpoint(ref, name), endpoint(after, name)) for name in WATCHED]
rows += [("`snap;desc` share, all /api calls", "-", snap_share(after)),
         ("304 responses seen by the probe", "-", sum(1 for c in calls(after) if c.get("status") == 304)),
         ("Idle tab, requests per minute", ref["report"]["idle"]["rpm"] if ref else "-", after["report"]["idle"]["rpm"]),
         ("Idle tab, calls by endpoint (120 s)", idle_counts(ref), idle_counts(after)),
         ("Closed view `/trades?status=CLOSED`, cold 200", "11.1 s p90 / 11.4 s max (unfiltered `/trades`, Plan 2)", fmt(closed["cold_200"])),
         ("Closed view, revalidation 304", "-", fmt(closed["revalidate_304"])),
         ("Closed view, ETag on cold / 200 on revalidate", "-", f"{closed['cold_with_etag']} of 20 / {closed['revalidate_200']}"),
         ("Closed view, `snap;desc`", "-", ", ".join(f"{k} {v}" for k, v in closed["snap"].items())),
         ("Closed view, scan running at start / end", "-", " / ".join(str(s) for s in closed["scan_running"]))]
print("| Measure | Plan 2 after (v217-after-1) | Plan 3 after (v218) |")
print("|---|---|---|")
for name, before, now in rows:
    print(f"| {name} | {before} | {now} |")
print()
print("reference:", "v217-after-1" if ref else "none found")
```

```bash
python "<scratchpad>/v218_compare.py" "<main>/scripts/ops" "<main>/.superpowers/probe/v218-after" "<main>/.superpowers/probe/v217-after-1" "<main>/.superpowers/probe/v218-closed-view.json" > "<main>/.superpowers/probe/v218-compare.md"
cat "<main>/.superpowers/probe/v218-compare.md"
```

Expected: a markdown table of about 18 rows and a last line naming the reference. A `KeyError` means the shape differs from the contract: fix the script to read the field that exists, and never edit `probe.json`. The Plan 2 column for the closed view quotes the spec's own "Plan 2 after" `/trades` figure, the unfiltered view and the only `/trades` figure Plan 2 has. The Results text says so.

- [ ] **Step 7: Record the result in the spec**

In `<main>/docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md`, append at the end of the file (below `### Plan 3 route audits (V218-10..12)` and anything after it):

```markdown
### Plan 3 after (committed probe)

After plan v218 deployed (ui <new ui>, bot <new bot>), with
`scripts/ops/admin_browser_probe.py` at `<probe_sha>`, against image `<tag>`,
`<berlin_time>` Berlin, `--date 2026-11-03`, 3 rounds × 12 pages, cap 90 s,
quiet 2 s. Label **<label>**<, recorded as "Not a strict scan run" like Plan 2's | >.
Reference: Plan 2's `v217-after-1` run (label `mixed`). Closed view: 20 cold GETs
and 20 revalidations of `/api/v1/trades?status=CLOSED&page=1&per_page=10` from
the dev machine through Cloudflare, `<closed_time>` Berlin. Credentials were absent from every output.

<the table from v218-compare.md, pasted unchanged, without its "reference:" line>

**What the figures can and cannot show.** The probe's `/trades` row is the
Trades page's unfiltered request (`page=1&per_page=10`). It may include open
rows, so it gets no ETag, and its change is the snapshot alone (`snap;desc`
share). The ETag saving shows only in the closed-view rows, measured by a
script because no SPA page requests that shape. The closed view is admitted
06:00–24:00 Berlin with the refresher on (V218-10b), and both held here. The
calendar routes stayed off the allow-list (`### Plan 3 route audits
(V218-10..12)`). The idle tab's `/market/updates` count is V218-14's measure:
it was 12 in 120 s before.

<one sentence per measure that moved the wrong way or missed the Plan 1 idle
target of under 10 per minute, with its figure; "none" if none did>
```

Fill `<probe_sha>` and `<berlin_time>` from the run's `probe.json` `report.meta`, `<tag>` from Step 1, the versions from `VERSION.json`, and `<closed_time>` from the closed-view file's modification time (UTC +1 h). Change no code here. Any `mixed`/`quiet` run that Step 5 set aside goes below as `#### Not evidence: <label> run, <berlin_time>`, with its idle rpm only.

- [ ] **Step 8: Check the section reads back, then commit on `main`**

```bash
python "<main>/scripts/dev/doc_section.py" "<main>/docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md" "Plan 3 after (committed probe)" | head -30
git -C "<main>" add docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md
git -C "<main>" commit -m "docs(v206): Plan 3 after-probe and closed-view revalidation (v218 V218-16)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C "<main>" push origin main
```

Expected: the provenance paragraph and the table print. Exit 2 from `doc_section.py` means: read the file at `## Results` directly. The push is docs-only. Watch its run as in V218-15 Step 9.

- [ ] **Step 9: Close out**

Run `/close-out` for v218 (standing permission, `document-lifecycle.md`). Its Step 5b skill alignment for this plan:

```bash
git -C "<main>" grep -ln "read_memo\|request_timing\|Server-Timing\|ADMIN_STORE_SNAPSHOT\|market/updates" -- .claude/skills .claude/agents docs/claude
```

`alert-surface` is not affected (no alert or embed code changed). For each hit, align the cited fact with what shipped. `docs/claude/architecture.md` cites `read_memo`: add one line saying the admin installs `store_snapshot` as its backing, so the bot and refresher never see it. In `docs/claude/known-traps.md` § Legacy shims and silent no-ops, add a short entry: a disconnected snapshot listener silently falls back to Layer 1, visible only as `snap;desc=off` on every `/api` response. A `docs/claude/` change ships its condensed `AGENTS.md` mirror in the same commit, and a `.claude/skills|agents` change runs `python scripts/dev/sync_codex.py` (CLAUDE.md § Codex mirror). Commit each alignment scoped, push, and watch the run.

