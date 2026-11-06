# v206 Plan 1, part 2 — the client stops polling on `scan`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v206 — Admin under load](../specs/2026-11-05-v206-admin-under-load-design.md)
**Index:** [`2026-11-05-v206-admin-under-load_0-index.md`](2026-11-05-v206-admin-under-load_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there and bind every task below.

Tasks V206-7..V206-12 (index groups D, E, F, G). V206-13 (group H, release and the after-probe) is in [`_2b-release.md`](2026-11-05-v206-admin-under-load_2b-release.md): this file would otherwise pass the 1500-line cap. `<wt>` is the implementation worktree, `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v206-admin-under-load`; every command names that path, never the main tree. Frontend specs run narrow with `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include <spec>` (the path after `--include` is relative to `<wt>/frontend`); no task runs the full suite (CI does after V206-13 pushes).

The one cross-language contract this part consumes is the `scan` SSE frame V206-6 sends: `{"seq": int, "at": str, "progress": {"running": bool, "progress": ScanProgressRecord | null}}`, where `progress` is **absent** (never `null`) when the broker's read failed, and absent on every other event and on an older server.

TypeScript has no complexity gate; every function touched here stays well under 15 by inspection (index Global Constraints). The connection store's effect gets a named helper (`_onEventTick`) rather than new branches.

# Phase D — the client reads the payload instead of refetching

### Task V206-7: `parseScanEventProgress` validator

**Model:** sonnet — one pure function and its table of inputs; a new file plus one interface, no shared state.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (after `export interface ScanStatus`, ~line 1721)
- Create: `frontend/src/app/api/scan-event-progress.ts`
- Create: `frontend/src/app/api/scan-event-progress.spec.ts`

**Interfaces:**
- Consumes: `ScanProgressRecord` (exists, `models.ts:1704`); the `scan` frame shape from V206-6 (top of this file).
- Produces (V206-8, V206-9): `export interface ScanEventProgress { running: boolean; progress: ScanProgressRecord | null }` in `models.ts`; `export function parseScanEventProgress(frame: unknown): ScanEventProgress | null` in `api/scan-event-progress.ts`. It reads `frame.progress`; anything absent or malformed is `null`, never a partial object.

Spec P1-c: "A pure validator, `parseScanEventProgress(data): ScanEventProgress | null`, with its own spec, treats anything malformed as absent." Error handling: "A malformed payload is treated as absent, never patched partially." The function returns a **new** object holding only the known fields, so an extra server field never leaks into the store.

- [ ] **Step 1: Write the failing spec**

Create `<wt>/frontend/src/app/api/scan-event-progress.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { parseScanEventProgress } from './scan-event-progress';

/* v206 P1-c — the `scan` frame's payload, validated.
 *
 * The broker sends `{seq, at, progress: {running, progress}}` on a `scan`
 * event when its read worked, and a thin `{seq, at}` when it did not. A
 * malformed payload is treated as absent: the connection store then falls
 * back to fetching `/system/scan`, which is always right, instead of
 * patching half a record into the progress strip.
 */

const RECORD = {
  at: '2026-11-05T15:40:00+00:00', pct: 66, stage: 'analyzing',
  current_ticker: 'AAPL', done: 50, total: 100, qualifying_found: 3,
};

const frame = (progress: unknown) => ({ seq: 7, at: '2026-11-05T15:40:00+00:00', progress });

const without = (key: keyof typeof RECORD): Record<string, unknown> => {
  const copy: Record<string, unknown> = { ...RECORD };
  delete copy[key];
  return copy;
};

describe('parseScanEventProgress', () => {
  it('reads a running scan and its record', () => {
    expect(parseScanEventProgress(frame({ running: true, progress: RECORD }))).toEqual({
      running: true, progress: RECORD,
    });
  });

  it('reads an idle scan with no record as running false, progress null', () => {
    expect(parseScanEventProgress(frame({ running: false, progress: null }))).toEqual({
      running: false, progress: null,
    });
  });

  it('accepts a record whose current ticker is null', () => {
    const record = { ...RECORD, current_ticker: null };
    expect(parseScanEventProgress(frame({ running: true, progress: record }))?.progress)
      .toEqual(record);
  });

  it('is null for a thin frame with no progress key (failed read, older server)', () => {
    expect(parseScanEventProgress({ seq: 7, at: '2026-11-05T15:40:00+00:00' })).toBeNull();
  });

  it('is null for progress: null, which the server never sends', () => {
    expect(parseScanEventProgress(frame(null))).toBeNull();
  });

  it.each([
    ['a null frame', null],
    ['a string frame', 'scan'],
    ['a number frame', 7],
    ['an array frame', [frame({ running: true, progress: RECORD })]],
    ['undefined', undefined],
  ])('is null for %s', (_label, input) => {
    expect(parseScanEventProgress(input)).toBeNull();
  });

  it.each([
    ['running missing', { progress: RECORD }],
    ['running as a string', { running: 'true', progress: RECORD }],
    ['progress missing', { running: true }],
    ['progress as a string', { running: true, progress: '66%' }],
    ['progress as an array', { running: true, progress: [RECORD] }],
  ])('is null when %s', (_label, payload) => {
    expect(parseScanEventProgress(frame(payload))).toBeNull();
  });

  it.each([
    ['at missing', without('at')],
    ['pct as a string', { ...RECORD, pct: '66' }],
    ['pct not finite', { ...RECORD, pct: Number.POSITIVE_INFINITY }],
    ['stage as a number', { ...RECORD, stage: 3 }],
    ['current_ticker as a number', { ...RECORD, current_ticker: 1 }],
    ['current_ticker missing', without('current_ticker')],
    ['done missing', without('done')],
    ['total as null', { ...RECORD, total: null }],
    ['qualifying_found as a string', { ...RECORD, qualifying_found: '3' }],
  ])('is null, never partial, when the record has %s', (_label, record) => {
    expect(parseScanEventProgress(frame({ running: true, progress: record }))).toBeNull();
  });

  it('keeps only the known fields, so nothing extra reaches the store', () => {
    const parsed = parseScanEventProgress(frame({
      running: true, extra: 'x', progress: { ...RECORD, note: 'server-only' },
    }));
    expect(parsed).toEqual({ running: true, progress: RECORD });
    expect(Object.keys(parsed!.progress!).sort()).toEqual(Object.keys(RECORD).sort());
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/api/scan-event-progress.spec.ts`
Expected: FAIL — the import `./scan-event-progress` cannot be resolved.

- [ ] **Step 3: Add the interface to `models.ts`**

In `<wt>/frontend/src/app/api/models.ts`, directly after the closing `}` of `export interface ScanStatus`, add:

```ts

/** v206 P1-c: the payload a `scan` SSE frame carries -- the two fields of
 *  `ScanStatus` the progress strip reads. Absent (never null) on the wire
 *  when the server's read failed; `parseScanEventProgress` turns absent or
 *  malformed into `null`. */
export interface ScanEventProgress {
  running: boolean;
  progress: ScanProgressRecord | null;
}
```

- [ ] **Step 4: Write the validator**

Create `<wt>/frontend/src/app/api/scan-event-progress.ts`:

```ts
import { ScanEventProgress, ScanProgressRecord } from './models';

type Fields = Record<string, unknown>;

function isObject(value: unknown): value is Fields {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/** A complete `ScanProgressRecord` holding only its own fields, or null. */
function parseRecord(value: unknown): ScanProgressRecord | null {
  if (!isObject(value)) return null;
  const { at, pct, stage, current_ticker, done, total, qualifying_found } = value;
  const ticker = current_ticker === null || typeof current_ticker === 'string';
  if (typeof at !== 'string' || typeof stage !== 'string' || !ticker) return null;
  if (!isNumber(pct) || !isNumber(done) || !isNumber(total) || !isNumber(qualifying_found)) return null;
  return { at, pct, stage, current_ticker: current_ticker as string | null, done, total, qualifying_found };
}

/**
 * The validated payload of a `scan` SSE frame (v206 P1-c), or null.
 *
 * `frame` is the parsed JSON body, `{seq, at, progress?}`. Null means
 * "nothing usable": a thin frame (the server's read failed, or an older
 * server), or anything malformed. Never partial -- a record missing one
 * field is null as a whole, so the store falls back to `/system/scan`
 * instead of patching half a bar.
 */
export function parseScanEventProgress(frame: unknown): ScanEventProgress | null {
  const payload = isObject(frame) ? frame['progress'] : undefined;
  if (!isObject(payload)) return null;
  const { running, progress } = payload;
  if (typeof running !== 'boolean' || progress === undefined) return null;
  if (progress === null) return { running, progress: null };
  const record = parseRecord(progress);
  return record === null ? null : { running, progress: record };
}
```

A missing `current_ticker` is caught because a destructured absent key is `undefined`, which is neither `null` nor a string.

- [ ] **Step 5: Run it to verify it passes**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/api/scan-event-progress.spec.ts`
Expected: PASS, every case green, 0 failed.

- [ ] **Step 6: Commit**

```bash
git -C "<wt>" add frontend/src/app/api/models.ts frontend/src/app/api/scan-event-progress.ts frontend/src/app/api/scan-event-progress.spec.ts
git -C "<wt>" commit -m "feat(v206): parseScanEventProgress validates the scan frame's payload (V206-7)"
```

### Task V206-8: `EventStream.payload('scan')` + invariant doc

**Model:** sonnet — one new signal in an existing service with clear clearing rules and a fake-timer spec; contained to two files.

**Files:**
- Modify: `frontend/src/app/api/event-stream.ts`
- Modify: `frontend/src/app/api/event-stream.spec.ts`

**Interfaces:**
- Consumes (V206-7): `ScanEventProgress` (`api/models.ts`), `parseScanEventProgress(frame: unknown): ScanEventProgress | null` (`api/scan-event-progress.ts`).
- Produces (V206-9): `EventStream.payload(name: 'scan'): Signal<ScanEventProgress | null>` — **unthrottled**, the last validated payload of a `scan` frame, or `null`. Rules V206-9 relies on:
  - set from every `scan` frame (a thin or malformed frame sets `null`), **before** the `scan` counters bump, so anything reacting to `changes('scan', …)` reads the payload that came with the frame;
  - set to `null` by every refetch-everything path (`resync`, the 5 s poll tick, the visible catch-up while polling: all go through `bumpAll()`), by `degrade()` and by `connect()` (a reconnect);
  - `changes(name, options?)` and `raised` are unchanged for every event.

Spec P1-c retires the class doc's v12 invariant ("the reaction to an event is always a refetch, never a patch") **for `scan` only**, and the doc changes in the same task. The payload is a separate signal from the counters: `changes('scan')` stays a counter, and the store decides what to do with the two. The degraded 5 s poll bumps every counter through `bumpAll()`; clearing the payload there is what stops a poll tick from re-patching stale progress (brief trap 5).

- [ ] **Step 1: Give the spec's fake source a body parameter and a raw frame**

In `<wt>/frontend/src/app/api/event-stream.spec.ts`, replace `FakeEventSource.emit` with the two methods below (existing callers `emit(name)` and `emit(name, seq)` keep working):

```ts
  /** Deliver a frame the way the server sends it: named event, thin body,
   *  plus any extra keys (v206: `progress` on `scan`). */
  emit(name: string, seq = 1, body: object = {}): void {
    this.emitRaw(name, JSON.stringify({ seq, at: '2026-08-12T00:00:00+00:00', ...body }));
  }

  /** Deliver a frame whose data is exactly `data`, parseable or not. */
  emitRaw(name: string, data: string): void {
    const event = new MessageEvent(name, { data });
    for (const handler of this.listeners.get(name) ?? []) handler(event);
  }
```

- [ ] **Step 2: Write the failing tests**

In the same file, inside `describe('EventStream', …)`, directly before the `/* -- throttled subscription (v132) */` comment, add:

```ts
  /* -- the scan payload (v206 P1-c) ------------------------------------- */

  const RECORD = {
    at: '2026-11-05T15:40:00+00:00', pct: 66, stage: 'analyzing',
    current_ticker: 'AAPL', done: 50, total: 100, qualifying_found: 3,
  };
  const PAYLOAD = { running: true, progress: RECORD };
  const scanFrame = (seq = 1) => FakeEventSource.latest().emit('scan', seq, { progress: PAYLOAD });
  const degradeNow = () => {
    const source = FakeEventSource.latest();
    source.fail();
    source.fail();
    source.fail();
  };

  it('holds nothing before the first scan frame', () => {
    expect(stream.payload('scan')()).toBeNull();
  });

  it('holds the last validated payload of a scan frame', () => {
    scanFrame(1);
    FakeEventSource.latest().emit('scan', 2, { progress: { running: true, progress: { ...RECORD, pct: 70 } } });
    expect(stream.payload('scan')()).toEqual({ running: true, progress: { ...RECORD, pct: 70 } });
  });

  it('a thin scan frame sets it back to null, so the store falls back to fetching', () => {
    scanFrame(1);
    FakeEventSource.latest().emit('scan', 2);
    expect(stream.payload('scan')()).toBeNull();
  });

  it('a malformed payload is null, and the counter still bumps', () => {
    const scan = stream.changes('scan');
    scanFrame(1);
    FakeEventSource.latest().emit('scan', 2, { progress: { running: 'yes', progress: RECORD } });
    expect(stream.payload('scan')()).toBeNull();
    expect(scan()).toBe(2);
  });

  it('an unparseable frame is null, and the counter still bumps', () => {
    const scan = stream.changes('scan');
    scanFrame(1);
    FakeEventSource.latest().emitRaw('scan', '{not json');
    expect(stream.payload('scan')()).toBeNull();
    expect(scan()).toBe(2);
  });

  it('is set before the counters move, so a reaction reads the payload it came with', () => {
    const seen: unknown[] = [];
    stream.raised.subscribe(() => seen.push(stream.payload('scan')()));
    scanFrame(1);
    expect(seen).toEqual([PAYLOAD]);
  });

  it('is cleared on resync: the client refetches everything', () => {
    scanFrame(1);
    FakeEventSource.latest().emit('resync');
    expect(stream.payload('scan')()).toBeNull();
  });

  it('is cleared on degrade, and a 5 s poll tick never brings it back', () => {
    const scan = stream.changes('scan');
    scanFrame(1);
    degradeNow();
    expect(stream.payload('scan')()).toBeNull();
    vi.advanceTimersByTime(POLL_INTERVAL_MS * 2);
    expect(scan()).toBe(3); // the frame, then two poll ticks
    expect(stream.payload('scan')()).toBeNull();
  });

  it('is cleared when the stream reconnects', () => {
    scanFrame(1);
    stream.disconnect();
    stream.connect();
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(stream.payload('scan')()).toBeNull();
  });

  it('is left alone by every other event, and no other counter moves on a scan frame', () => {
    const trades = stream.changes('trades');
    const bot = stream.changes('bot');
    const scan = stream.changes('scan');
    scanFrame(1);
    FakeEventSource.latest().emit('trades', 2);
    FakeEventSource.latest().emit('ping', 3);
    expect(stream.payload('scan')()).toEqual(PAYLOAD);
    expect([trades(), bot(), scan()]).toEqual([1, 0, 1]);
  });

  it('feeds the throttled scan view exactly as before', () => {
    const slow = stream.changes('scan', { minIntervalMs: 5_000 });
    for (let i = 0; i < 5; i++) scanFrame(i + 1);
    expect(slow()).toBe(1);
    vi.advanceTimersByTime(5_000);
    expect(slow()).toBe(2);
    expect(stream.payload('scan')()).toEqual(PAYLOAD);
  });
```

- [ ] **Step 3: Run them to verify they fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/api/event-stream.spec.ts`
Expected: FAIL — `stream.payload is not a function` in the new tests; every pre-existing test still passes.

- [ ] **Step 4: Implement the payload signal**

In `<wt>/frontend/src/app/api/event-stream.ts`:

(a) Add the imports below the existing `rxjs` import:

```ts
import { ScanEventProgress } from './models';
import { parseScanEventProgress } from './scan-event-progress';
```

(b) Replace the class-doc paragraph that begins `**The reaction to an event is always a refetch, never a patch.**` (through `...second, slowly diverging copy of the server's data.`) with:

```ts
 * **The reaction to an event is a refetch, never a patch -- except `scan`.**
 * The events are thin by design (`{seq, at}`, no payload), so there is
 * nothing here to merge into anything. That is the property that stops a
 * store becoming a second, slowly diverging copy of the server's data.
 *
 * `scan` is the one exception (v206 P1-c). It fires about once a second
 * while a scan runs, and refetching `/system/scan` on each one, from every
 * open tab, was most of the admin's load. So a `scan` frame carries the two
 * fields the progress strip reads, and {@link payload} exposes them,
 * validated, as a signal separate from the counter. A thin or malformed
 * frame sets it to null, and so does every path that refetches everything
 * (resync, the polling fallback, a reconnect), so a store never patches
 * from a payload older than its last refetch.
```

(c) Add the field after `private readonly throttles = new Map<string, Throttle>();`:

```ts
  /** v206: the last validated `scan` payload; null whenever the store must fetch. */
  private readonly scanPayload = signal<ScanEventProgress | null>(null);
  private readonly scanPayloadView = this.scanPayload.asReadonly();
```

(d) Add the public method directly after `changes(...)`:

```ts
  /**
   * The last validated payload of a `scan` frame, or null (v206 P1-c).
   *
   * Unthrottled: it moves on every `scan` frame, before the counters do. A
   * thin frame (the server's read failed, or an older server) and anything
   * malformed read as null -- the store's cue to fetch `/system/scan`
   * through its throttled fallback instead.
   */
  payload(_name: 'scan'): Signal<ScanEventProgress | null> {
    return this.scanPayloadView;
  }
```

(e) In `connect()`, after `this.source = source;` add `this.scanPayload.set(null);` (with the comment `// A reconnect starts from nothing: the resync that follows refetches.`), and replace the per-name listener loop with:

```ts
    for (const name of EVENT_NAMES) {
      source.addEventListener(name, (event) => this.receive(name, event as MessageEvent));
    }
```

(f) Add `receive` above `private counterFor`, inside the `/* -- internals */` section:

```ts
  private receive(name: EventName, event: MessageEvent): void {
    const frame = this.markLive(event);
    // Set before the bump: a reaction to the counter reads the payload that
    // arrived with it, never the one before.
    if (name === 'scan') this.scanPayload.set(parseScanEventProgress(frame));
    this.bump(name);
  }
```

(g) Make `markLive` return the parsed frame:

```ts
  private markLive(event: MessageEvent): unknown {
    // A message arriving is proof the connection works, so the failure
    // window resets here rather than on `onopen`: EventSource reports open
    // before the server has necessarily said anything.
    this.failures = [];
    this.state.set('live');
    this.stopPolling();
    try {
      const data = JSON.parse(event.data) as { seq?: number } | null;
      if (typeof data?.seq === 'number') this.lastSeq.set(data.seq);
      return data;
    } catch {
      // A frame we cannot parse is not worth failing over: the event's
      // meaning is its NAME, which we already have.
      return null;
    }
  }
```

(h) Clear the payload on every refetch-everything path and on degrade:

```ts
  private bumpAll(): void {
    // Everything is refetched, so no store may patch from an older payload.
    this.scanPayload.set(null);
    for (const name of EVENT_NAMES) this.bump(name);
  }
```

and in `degrade()`, after `this.state.set('degraded');`, add `this.scanPayload.set(null);`.

The `resync` and `ping` listeners keep calling `this.markLive(...)` and ignore its return value.

- [ ] **Step 5: Run the spec to verify it passes**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/api/event-stream.spec.ts --include src/app/api/scan-event-progress.spec.ts`
Expected: PASS, 0 failed, including every pre-v206 test in the file (the throttle, polling and hidden-tab cases are unchanged).

- [ ] **Step 6: Commit**

```bash
git -C "<wt>" add frontend/src/app/api/event-stream.ts frontend/src/app/api/event-stream.spec.ts
git -C "<wt>" commit -m "feat(v206): EventStream.payload('scan') carries the validated scan payload; never-a-patch invariant now excepts scan (V206-8)"
```

### Task V206-9: ConnectionStore: patch from payload, throttled fallback, health timer

**Model:** sonnet — rewires one store's effect and adds a timer, with fake-timer specs against both a fake and the real EventStream; contained, but the spec fakes in two other files need a one-line method.

**Files:**
- Modify: `frontend/src/app/stores/connection.store.ts`
- Modify: `frontend/src/app/stores/connection.store.spec.ts`
- Modify: `frontend/src/app/shell/shell.spec.ts` and `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (test-only: their `FakeEventStream` gains `payload()`, because both build the real `ConnectionStore`; not in the index ledger's file list)

**Interfaces:**
- Consumes (V206-8): `EventStream.payload('scan'): Signal<ScanEventProgress | null>`, set before the `scan` counters bump and cleared by `bumpAll()`/`degrade()`/`connect()`. `EventStream.changes(name, { minIntervalMs })` (exists). `ScanEventProgress` (V206-7, `api/models.ts`).
- Produces: `export const SCAN_FALLBACK_MIN_INTERVAL_MS = 5000;` and `export const HEALTH_INTERVAL_MS = 300_000;` in `stores/connection.store.ts`. Public store methods `refresh()` (both requests, unchanged) and `refreshHealth()`.

Spec P1-c and Global Constraints:
- a non-null `payload('scan')` patches `scanRunning` and `scanProgress` and **sends no request**;
- a `scan` tick whose payload is `null` is the fallback: `/system/scan`, throttled through `changes('scan', { minIntervalMs: 5000 })`;
- `/system/scan` and `/health` are fetched at boot, on `bot` and on `resync` (a resync bumps every counter, `bot` included), and `/health` also on a 5-minute timer that skips while `document.hidden`, plus one catch-up fetch on visible when more than 5 minutes have passed since the last. `/health` never reacts to `scan`;
- `botAlive`, `botHealthy`, `botLastSeen`, `botLastSuccess` now refresh on `bot`/boot/`resync` only (spec P1-b: heartbeat facts).

`bot` and the throttled `scan` view stay in **one** effect, as today, so a resync (which bumps both in the same task) fetches `/system/scan` once, not twice. The effect calls one named helper, `_onEventTick(botTick)`: a changed `bot` counter means a full refresh; otherwise it is a `scan` tick, which fetches only when the payload is null. The payload patch is a second, separate effect.

- [ ] **Step 1: Write the failing tests**

In `<wt>/frontend/src/app/stores/connection.store.spec.ts`:

(a) Change the imports: `import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';` plus `import type { MockInstance } from 'vitest';`, and add `import { ScanEventProgress } from '../api/models';` and `HEALTH_INTERVAL_MS, SCAN_FALLBACK_MIN_INTERVAL_MS` to the `./connection.store` import.

(b) Give `FakeEventStream` a payload and record the throttle it is asked for (it still ignores the option; the real-stream block below covers the throttle itself):

```ts
  readonly scanPayload = signal<ScanEventProgress | null>(null);
  readonly requested: [string, unknown][] = [];

  changes(name: string, options?: { minIntervalMs: number }): Signal<number> {
    this.requested.push([name, options]);
    return this.counterFor(name).asReadonly();
  }

  payload(_name: 'scan'): Signal<ScanEventProgress | null> {
    return this.scanPayload.asReadonly();
  }

  /** A `scan` frame as V206-8 delivers it: payload first, then the counter. */
  send(payload: ScanEventProgress | null): void {
    this.scanPayload.set(payload);
    this.raise('scan');
  }
```

(c) In `describe('ConnectionStore scan progress', …)`, replace the three tests `'refetches on the scan event, not only on the bot event'`, `'clears the record when the scan ends so no bar outlives it'` and `'a failed scan read leaves the bar alone rather than freezing it'` with:

```ts
  it('asks for the scan counter throttled to 5 s', () => {
    expect(SCAN_FALLBACK_MIN_INTERVAL_MS).toBe(5000);
    expect(events.requested).toContainEqual(['scan', { minIntervalMs: 5000 }]);
  });

  it('patches the strip from the scan payload and sends no request (v206)', () => {
    tick();
    respond({ ...SCAN, running: false, progress: null });

    events.send({ running: true, progress: PROGRESS });
    tick();

    backend.expectNone('/api/v1/system/scan');
    backend.expectNone('/api/v1/health');
    expect(store.scanRunning()).toBe(true);
    expect(store.scanProgress()?.current_ticker).toBe('AAPL');
  });

  it('a scan tick with no payload falls back to /system/scan, never /health', () => {
    // An older server, a failed broker read or degraded mode: fetch instead.
    tick();
    respond({ ...SCAN, running: false, progress: null });

    events.send(null);
    tick();

    backend.expectNone('/api/v1/health');
    backend.expectOne('/api/v1/system/scan').flush({ ...SCAN, running: true, progress: PROGRESS });
    expect(store.scanProgress()?.pct).toBe(66);
  });

  it('clears the record when the scan ends so no bar outlives it', () => {
    tick();
    respond({ ...SCAN, running: true, progress: PROGRESS });

    events.send({ running: false, progress: null });
    tick();

    expect(store.scanRunning()).toBe(false);
    expect(store.scanProgress()).toBeNull();
  });

  it('a failed fallback read leaves the bar alone rather than freezing it', () => {
    tick();
    respond({ ...SCAN, running: true, progress: PROGRESS });

    events.send(null);
    tick();
    backend.expectOne('/api/v1/system/scan').error(new ProgressEvent('error'), { status: 0 });

    // One failed poll is a blip; the next event corrects it.
    expect(store.scanProgress()?.pct).toBe(66);
  });

  it('a bot event still refetches both, so the heartbeat facts move', () => {
    tick();
    respond({ ...SCAN, bot_last_seen: '2026-08-14T09:00:00Z' });

    events.raise('bot');
    tick();
    respond({ ...SCAN, bot_last_seen: '2026-08-14T09:05:00Z' });

    expect(store.botLastSeen()).toBe('2026-08-14T09:05:00Z');
  });
```

(d) Append two new `describe` blocks at the end of the file:

```ts
/* --- the 5-minute /health timer (v206) ----------------------------------- */

describe('ConnectionStore health timer', () => {
  let backend: HttpTestingController;
  let hidden: MockInstance<() => boolean> | null = null;

  beforeEach(() => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    TestBed.inject(ConnectionStore);
    backend = TestBed.inject(HttpTestingController);
    TestBed.inject(ApplicationRef).tick();
    backend.expectOne('/api/v1/health').flush(HEALTH);
    backend.expectOne('/api/v1/system/scan').flush(SCAN);
  });

  afterEach(() => {
    hidden?.mockRestore();
    hidden = null;
    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  const setHidden = (value: boolean) => {
    hidden ??= vi.spyOn(document, 'hidden', 'get');
    hidden.mockReturnValue(value);
    document.dispatchEvent(new Event('visibilitychange'));
  };

  it('refreshes /health every 5 minutes while visible, and nothing else', () => {
    expect(HEALTH_INTERVAL_MS).toBe(300_000);
    vi.advanceTimersByTime(HEALTH_INTERVAL_MS - 1);
    backend.expectNone('/api/v1/health');
    vi.advanceTimersByTime(1);
    backend.expectOne('/api/v1/health').flush(HEALTH);
    backend.expectNone('/api/v1/system/scan');
  });

  it('skips the timer while hidden and catches up once when the tab is visible again', () => {
    setHidden(true);
    vi.advanceTimersByTime(HEALTH_INTERVAL_MS * 2);
    backend.expectNone('/api/v1/health');

    setHidden(false);
    backend.expectOne('/api/v1/health').flush(HEALTH);
    setHidden(false);
    backend.expectNone('/api/v1/health');
  });

  it('does not catch up on visible when the last fetch is recent', () => {
    vi.advanceTimersByTime(60_000);
    setHidden(true);
    setHidden(false);
    backend.expectNone('/api/v1/health');
  });

  it('stops the timer and the visibility listener when the store is destroyed', () => {
    const clear = vi.spyOn(globalThis, 'clearInterval');
    const remove = vi.spyOn(document, 'removeEventListener');
    TestBed.resetTestingModule();
    expect(clear).toHaveBeenCalled();
    expect(remove.mock.calls.some(([type]) => type === 'visibilitychange')).toBe(true);
    clear.mockRestore();
    remove.mockRestore();
  });
});

/* --- against the real EventStream: the throttle is real (v206) ----------- */

class FakeEventSource {
  static latest: FakeEventSource | null = null;
  readonly listeners = new Map<string, ((event: MessageEvent) => void)[]>();
  onerror: (() => void) | null = null;
  constructor(readonly url: string) { FakeEventSource.latest = this; }
  addEventListener(name: string, handler: (event: MessageEvent) => void): void {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), handler]);
  }
  close(): void { /* no-op */ }
  emit(name: string, body: object = {}): void {
    const event = new MessageEvent(name, { data: JSON.stringify({ seq: 1, at: '2026-11-05T15:40:00+00:00', ...body }) });
    for (const handler of this.listeners.get(name) ?? []) handler(event);
  }
}

describe('ConnectionStore on the real EventStream', () => {
  let store: InstanceType<typeof ConnectionStore>;
  let backend: HttpTestingController;
  const PROGRESS = {
    at: '2026-11-05T15:40:00+00:00', pct: 40, stage: 'analyzing',
    current_ticker: 'MSFT', done: 4, total: 10, qualifying_found: 1,
  };

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('EventSource', FakeEventSource);
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    store = TestBed.inject(ConnectionStore);
    backend = TestBed.inject(HttpTestingController);
    tick();
    backend.expectOne('/api/v1/health').flush(HEALTH);
    backend.expectOne('/api/v1/system/scan').flush(SCAN);
  });

  afterEach(() => {
    TestBed.resetTestingModule();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();
  const scans = () => backend.match('/api/v1/system/scan');

  it('thin scan frames every 500 ms make at most one fallback call per 5 s, and no /health', () => {
    FakeEventSource.latest!.emit('scan');
    tick();
    expect(scans()).toHaveLength(1);
    for (let ms = 500; ms < 5000; ms += 500) {
      vi.advanceTimersByTime(500);
      FakeEventSource.latest!.emit('scan');
      tick();
    }
    expect(scans()).toHaveLength(0);
    vi.advanceTimersByTime(500); // t = 5 s: the trailing bump
    tick();
    expect(scans()).toHaveLength(1);
    backend.expectNone('/api/v1/health');
  });

  it('scan frames that carry progress send no request at all', () => {
    for (let i = 0; i < 10; i++) {
      FakeEventSource.latest!.emit('scan', { progress: { running: true, progress: { ...PROGRESS, done: i } } });
      tick();
      vi.advanceTimersByTime(1000);
      tick();
    }
    backend.verify();
    expect(store.scanProgress()?.done).toBe(9);
  });

  it('a resync refetches health and scan status once each, not twice', () => {
    FakeEventSource.latest!.emit('resync');
    tick();
    backend.expectOne('/api/v1/health').flush(HEALTH);
    expect(scans()).toHaveLength(1);
  });
});
```

The `scan progress` describe's `respond` helper and every boot assertion stay as they are: boot is still exactly one `/health` and one `/system/scan`.

- [ ] **Step 2: Run them to verify they fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/stores/connection.store.spec.ts`
Expected: FAIL — the constants are not exported; `patches the strip from the scan payload` sees two requests (today's store fetches both on `scan`); the health-timer tests see no request at 5 minutes; the real-stream burst sees one `/system/scan` per frame.

- [ ] **Step 3: Implement**

In `<wt>/frontend/src/app/stores/connection.store.ts`:

(a) Imports: `import { DestroyRef, computed, effect, inject, untracked } from '@angular/core';` and `import { Health, ScanEventProgress, ScanProgressRecord } from '../api/models';`.

(b) Below the `ConnectionState` type, add:

```ts
/** v206: a `scan` tick with no payload (older server, failed broker read,
 *  degraded mode) fetches `/system/scan` at most once per this window. */
export const SCAN_FALLBACK_MIN_INTERVAL_MS = 5000;

/** v206: `/health` is read at boot, on `bot`, and on this timer -- never on
 *  `scan`, which fires about once a second while a scan runs. */
export const HEALTH_INTERVAL_MS = 300_000;

/** The 5-minute `/health` timer: skipped while the tab is hidden, plus one
 *  catch-up when it becomes visible and the last fetch is older than that. */
function startHealthTimer(
  store: { refreshHealth(): void; _healthDue(): boolean },
  destroyRef: DestroyRef,
): void {
  if (typeof document === 'undefined') return;
  const timer = setInterval(() => {
    if (!document.hidden) store.refreshHealth();
  }, HEALTH_INTERVAL_MS);
  const onVisibility = () => {
    if (!document.hidden && store._healthDue()) store.refreshHealth();
  };
  document.addEventListener('visibilitychange', onVisibility);
  destroyRef.onDestroy(() => {
    clearInterval(timer);
    document.removeEventListener('visibilitychange', onVisibility);
  });
}
```

(c) Replace the whole `withMethods(...)` block with:

```ts
  withMethods((store, api = inject(ApiClient), events = inject(EventStream)) => {
    let seenBot: number | null = null;
    let lastHealthAt = Number.NEGATIVE_INFINITY;

    // Its own request and its own silence on failure: a failed health read
    // must not flip the connection indicator, which is answering a
    // different question and has its own signal for it.
    const refreshHealth = (): void => {
      lastHealthAt = Date.now();
      api.health().subscribe({
        next: (health) => patchState(store, { health }),
        error: () => undefined,
      });
    };

    const refreshScan = (): void => {
      api.scanStatus().subscribe({
        next: (scan) =>
          patchState(store, {
            botAlive: scan.bot_alive,
            botHealthy: scan.bot_healthy,
            botLastSeen: scan.bot_last_seen,
            botLastSuccess: scan.bot_last_success,
            scanRunning: scan.running,
            scanProgress: scan.progress,
            unreachable: false,
          }),
        // The strip is deliberately left as it was: one failed poll while the
        // stream is live is a blip the next event corrects, and blanking the
        // bar on it would make it flicker through every scan.
        error: () => patchState(store, { unreachable: true }),
      });
    };

    const refresh = (): void => {
      refreshHealth();
      refreshScan();
    };

    return {
      refresh,
      refreshHealth,
      _healthDue: (): boolean => Date.now() - lastHealthAt > HEALTH_INTERVAL_MS,
      /** One run of the event effect. A moved `bot` counter (boot, a
       *  heartbeat, a resync) refreshes everything; otherwise it was a
       *  throttled `scan` tick, which fetches only when no payload came. */
      _onEventTick(botTick: number): void {
        if (botTick !== seenBot) {
          seenBot = botTick;
          refresh();
          return;
        }
        if (events.payload('scan')() === null) refreshScan();
      },
      /** The strip's two facts straight from a `scan` frame (v206 P1-c). */
      _patchProgress(payload: ScanEventProgress | null): void {
        if (payload) patchState(store, { scanRunning: payload.running, scanProgress: payload.progress });
      },
    };
  }),
```

(d) Replace the whole `withHooks({...})` block with:

```ts
  withHooks({
    onInit(store, events = inject(EventStream), destroyRef = inject(DestroyRef)) {
      events.connect();

      // `bot` is the heartbeat moving; the throttled `scan` view is the
      // fallback for a `scan` frame that carried no payload. They share ONE
      // effect, as before v206: its first run is the boot load, and a resync
      // (which bumps both at once) fetches `/system/scan` once, not twice.
      const bot = events.changes('bot');
      const scanTick = events.changes('scan', { minIntervalMs: SCAN_FALLBACK_MIN_INTERVAL_MS });
      effect(() => {
        const botTick = bot();
        scanTick();
        untracked(() => store._onEventTick(botTick));
      });

      // v206: the progress strip moves with every `scan` frame, from the
      // frame itself -- no request. This is what used to cost ~2 requests a
      // second per open tab.
      const payload = events.payload('scan');
      effect(() => {
        const value = payload();
        untracked(() => store._patchProgress(value));
      });

      startHealthTimer(store, destroyRef);
    },
  }),
```

Update the `health` field's doc comment in `ConnectionStateSlice`: replace `the shell already refetches this store on the \`bot\` event.` with `the shell already refetches this store on the \`bot\` event (and, since v206, on a 5-minute timer; never on \`scan\`).`

- [ ] **Step 4: Run the store spec to verify it passes**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/stores/connection.store.spec.ts`
Expected: PASS, 0 failed. If `'stops the timer and the visibility listener when the store is destroyed'` fails, `destroyRef.onDestroy` is not clearing them: fix the store, not the test.

- [ ] **Step 5: Give the other fakes that build the real store a `payload()`**

`shell.spec.ts` and `trade-detail.spec.ts` both build the real `ConnectionStore` against their own `FakeEventStream`. In each class add (with `ScanEventProgress` imported from the spec's relative path to `api/models`, e.g. `'../api/models'` in `shell/`, `'../../api/models'` in `workspaces/trades/`):

```ts
  /** v206: ConnectionStore patches the strip from this; null = fetch instead. */
  payload(_name: 'scan'): Signal<ScanEventProgress | null> {
    return signal<ScanEventProgress | null>(null).asReadonly();
  }
```

Then run every spec that fakes the stream, so no other fake is missed:

```bash
SPECS=$(git -C "<wt>" grep -l "provide: EventStream" -- 'frontend/src/app/*.spec.ts' | sed 's#^frontend/#--include #')
node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" $SPECS
```

Expected: PASS, 0 failed. A failure reading `events.payload is not a function` names another spec whose fake reaches `ConnectionStore`: give that fake the same method and rerun. A shell test that raised `scan` and expected `/health` is now wrong by design (spec P1-c): make it expect only the fallback `/system/scan`.

- [ ] **Step 6: Commit**

```bash
git -C "<wt>" add frontend/src/app/stores/connection.store.ts frontend/src/app/stores/connection.store.spec.ts frontend/src/app/shell/shell.spec.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts
git -C "<wt>" commit -m "feat(v206): connection store patches the strip from the scan payload; throttled fallback; /health on a 5-minute visible-tab timer (V206-9)"
```

(Add any further spec file Step 5 touched to the `git add`.)

# Phase E — fewer reloads and duplicate requests

### Task V206-10: RouteRefreshService per-event minimum interval

**Model:** sonnet — a small rate limit inside one service with a fake-timer spec; no contract beyond one exported constant.

**Files:**
- Modify: `frontend/src/app/routing/route-refresh.service.ts`
- Modify: `frontend/src/app/routing/route-refresh.service.spec.ts`

**Interfaces:**
- Consumes: `EventStream.raised` (exists, unthrottled `Observable<EventName>`), `EventName` (exists).
- Produces: `export const EVENT_MIN_INTERVAL_MS: Partial<Record<EventName, number>> = { scan: 5000 };` in `routing/route-refresh.service.ts`.

Spec P1-c "Route reloads on `scan`": the System workspace (`refreshOnSystem`, tabs `scan` and `providers`) and ticker detail (`onEvents('scan', 'trades', 'watchlist')`) reload their whole route on every `scan` through this service, which listens to the **unthrottled** `raised` stream with a 300 ms debounce, so throttling `changes()` never reached them (brief trap 1). This task gives `scan` a 5 s minimum interval **inside the service**: the first `scan` passes at once, the rest of a burst collapse into one trailing `scan` at the end of the window (so the last state of a scan is never lost), and every other event keeps the 300 ms debounce unchanged. Neither route file changes.

- [ ] **Step 1: Write the failing tests**

Replace `<wt>/frontend/src/app/routing/route-refresh.service.spec.ts` with:

```ts
import { Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EventName, EventStream } from '../api/event-stream';
import { RouteLoadingService, BACKGROUND_REFRESH_INFO } from './route-loading.service';
import { RefreshPredicate, routeData } from './route-metadata';
import { EVENT_MIN_INTERVAL_MS, RouteRefreshService } from './route-refresh.service';

describe('RouteRefreshService', () => {
  let raised: Subject<EventName>;
  let navigateByUrl: ReturnType<typeof vi.fn>;

  const start = (refreshOn: RefreshPredicate, url = '/dashboard') => {
    raised = new Subject<EventName>();
    navigateByUrl = vi.fn();
    const router = { url, events: new Subject(), navigateByUrl,
      routerState: { snapshot: { root: { data: {}, firstChild: { data: routeData('Page', refreshOn), firstChild: null } } } } };
    TestBed.configureTestingModule({ providers: [
      { provide: Router, useValue: router },
      { provide: EventStream, useValue: { raised } },
      { provide: RouteLoadingService, useValue: { pending: () => false } },
    ] });
    TestBed.inject(RouteRefreshService);
  };

  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('coalesces relevant events and reloads the current URL once', () => {
    start((event) => event === 'trades' || event === 'account');
    raised.next('trades'); raised.next('account');
    vi.advanceTimersByTime(299);
    expect(navigateByUrl).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(navigateByUrl).toHaveBeenCalledWith('/dashboard', { onSameUrlNavigation: 'reload', replaceUrl: true, info: BACKGROUND_REFRESH_INFO });
  });

  it('limits only scan, to 5 s (v206)', () => {
    expect(EVENT_MIN_INTERVAL_MS).toEqual({ scan: 5000 });
  });

  it('reloads a scan-driven route at most once per 5 s while a scan raises scan every second', () => {
    start((event) => event === 'scan', '/system/scan');
    const at: number[] = [];
    navigateByUrl.mockImplementation(() => at.push(Date.now()));
    const t0 = Date.now();
    for (let second = 0; second < 10; second++) {
      raised.next('scan');
      vi.advanceTimersByTime(1000);
    }
    vi.advanceTimersByTime(10_000);
    // Leading at 0 s, then one trailing reload per 5 s window: 0.3, 5.3, 10.3 s.
    expect(at.map((t) => t - t0)).toEqual([300, 5300, 10_300]);
  });

  it('never drops the last scan of a burst: it lands at the end of the window', () => {
    start((event) => event === 'scan', '/system/scan');
    raised.next('scan');
    vi.advanceTimersByTime(1000);
    raised.next('scan');
    vi.advanceTimersByTime(4299);
    expect(navigateByUrl).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1);
    expect(navigateByUrl).toHaveBeenCalledTimes(2);
  });

  it('keeps the plain 300 ms debounce for every other event', () => {
    start((event) => event === 'trades', '/trades');
    raised.next('trades');
    vi.advanceTimersByTime(1000);
    raised.next('trades');
    vi.advanceTimersByTime(300);
    expect(navigateByUrl).toHaveBeenCalledTimes(2);
  });

  it('a held-back scan does not hold back another event', () => {
    start((event) => event === 'scan' || event === 'bot', '/system/providers');
    raised.next('scan');
    vi.advanceTimersByTime(1000);
    raised.next('scan'); // held until 5 s
    raised.next('bot');
    vi.advanceTimersByTime(300);
    expect(navigateByUrl).toHaveBeenCalledTimes(2); // 0.3 s (scan) and 1.3 s (bot)
  });

  it('cancels a pending scan when the service is destroyed', () => {
    start((event) => event === 'scan', '/system/scan');
    raised.next('scan');
    vi.advanceTimersByTime(1000);
    raised.next('scan');
    TestBed.resetTestingModule();
    vi.advanceTimersByTime(10_000);
    expect(navigateByUrl).toHaveBeenCalledTimes(1);
  });
});
```

`RefreshPredicate` is exported by `routing/route-metadata.ts:4` (verified).

- [ ] **Step 2: Run them to verify they fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/routing/route-refresh.service.spec.ts`
Expected: FAIL — `EVENT_MIN_INTERVAL_MS` is not exported; the scan-burst test sees ten reloads instead of three. The two pre-existing-behaviour tests (`coalesces…`, `plain 300 ms debounce`) pass.

- [ ] **Step 3: Implement**

Replace `<wt>/frontend/src/app/routing/route-refresh.service.ts` with:

```ts
import { DestroyRef, Injectable, inject } from '@angular/core';
import { NavigationCancel, NavigationEnd, NavigationError, Router } from '@angular/router';
import { Subject, debounceTime, filter } from 'rxjs';

import { EventName, EventStream } from '../api/event-stream';
import { BACKGROUND_REFRESH_INFO, RouteLoadingService } from './route-loading.service';
import { RESOLVER_ROUTE_DATA, ResolverRouteData, resolvedRoute } from './route-metadata';

/**
 * v206: the least time between two reloads a given event may cause.
 *
 * `scan` fires about once a second while a scan runs, and the System
 * workspace (`scan`/`providers` tabs) and ticker detail reload their whole
 * route on it -- a full resolve a second, per tab. The System page's own
 * `paused`/`pending` facts change only through `runtime_flags`, so 5 s is
 * enough. Every event not listed keeps the plain 300 ms debounce.
 */
export const EVENT_MIN_INTERVAL_MS: Partial<Record<EventName, number>> = { scan: 5000 };

@Injectable({ providedIn: 'root' })
export class RouteRefreshService {
  private readonly router = inject(Router);
  private readonly loading = inject(RouteLoadingService);
  private readonly settle = new Subject<void>();
  private readonly events = new Set<EventName>();
  private readonly lastAccepted = new Map<EventName, number>();
  private readonly held = new Map<EventName, ReturnType<typeof setTimeout>>();
  private mutationPending = false;

  constructor() {
    inject(EventStream).raised.subscribe((event) => this.accept(event));
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd || event instanceof NavigationCancel || event instanceof NavigationError),
    ).subscribe(() => this.settle.next());
    this.settle.pipe(debounceTime(300)).subscribe(() => this.refresh());
    inject(DestroyRef).onDestroy(() => {
      for (const timer of this.held.values()) clearTimeout(timer);
      this.held.clear();
    });
  }

  requestMutationRefresh(): void {
    this.mutationPending = true;
    this.settle.next();
  }

  /** Leading edge at once; the rest of a burst inside the event's minimum
   *  interval becomes one trailing event at the end of it. */
  private accept(event: EventName): void {
    const interval = EVENT_MIN_INTERVAL_MS[event];
    if (interval === undefined) return this.queue(event);
    const wait = (this.lastAccepted.get(event) ?? Number.NEGATIVE_INFINITY) + interval - Date.now();
    if (wait <= 0) return this.release(event);
    if (this.held.has(event)) return;
    this.held.set(event, setTimeout(() => this.release(event), wait));
  }

  private release(event: EventName): void {
    this.held.delete(event);
    this.lastAccepted.set(event, Date.now());
    this.queue(event);
  }

  private queue(event: EventName): void {
    this.events.add(event);
    this.settle.next();
  }

  private refresh(): void {
    if (this.loading.pending()) return;

    const route = resolvedRoute(this.router.routerState.snapshot.root);
    const meta = route?.data[RESOLVER_ROUTE_DATA] as ResolverRouteData | undefined;
    const shouldRefresh = this.mutationPending || [...this.events].some((event) => meta?.refreshOn(event, route!) ?? false);
    this.events.clear();
    this.mutationPending = false;
    if (!shouldRefresh) return;
    void this.router.navigateByUrl(this.router.url, { onSameUrlNavigation: 'reload', replaceUrl: true, info: BACKGROUND_REFRESH_INFO });
  }
}
```

`refresh()` is byte-for-byte unchanged; only the subscription now goes through `accept`.

- [ ] **Step 4: Run the spec, and the specs that build the real service, to verify they pass**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/routing/route-refresh.service.spec.ts --include src/app/shell/shell.spec.ts --include src/app/stores/system.store.spec.ts`
Expected: PASS, 0 failed (`shell.spec.ts` wires the real `RouteRefreshService`; `system.store.spec.ts` pins `refreshOnSystem`, which this task leaves alone).

- [ ] **Step 5: Commit**

```bash
git -C "<wt>" add frontend/src/app/routing/route-refresh.service.ts frontend/src/app/routing/route-refresh.service.spec.ts
git -C "<wt>" commit -m "feat(v206): route reloads on scan at most once per 5 s; other events keep the 300 ms debounce (V206-10)"
```

### Task V206-11: `/live` stops reacting to `scan` + field table

**Model:** sonnet — one constant, a documentation table checked against the `/live` route, and spec updates; one store, no shared contract.

**Files:**
- Modify: `frontend/src/app/stores/live.store.ts`
- Modify: `frontend/src/app/stores/live.store.spec.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `export const LIVE_REFRESH_EVENTS = ['trades', 'bot', 'risk'] as const;` (Global Constraints: exactly this; `scan` is never added back).

Spec P1-d: the `/live` task lists every field of the `/live` payload and its trigger as a table in a comment beside `LIVE_REFRESH_EVENTS`; a field that changes during a scan through anything other than `trades`, `bot` or `risk` gets its own named trigger, never `scan`. The table below was built from `swingbot/admin/api_v1/live.py` (`heat_section`, `awaiting_section`, `killswitch_section`, `_events`), `swingbot/admin/api_v1/live_events.py:192` (`EVENT_KINDS`) and the table-to-event map in `swingbot/core/db/events.py` (`TABLE_CHANNELS`). What a scan writes that `/live` shows is new plans, and the `plans` table raises `trades`, so no field needs a new trigger. Before writing the comment, re-check the three files have not gained a section: `git -C "<wt>" grep -n "def .*_section\|EventKind(" swingbot/admin/api_v1/live.py swingbot/admin/api_v1/live_events.py`. Expected: `heat_section`, `awaiting_section`, `killswitch_section` and five `EventKind(` rows (`plan_alerted`, `paper_filled`, `tp1_hit`, `trade_closed`, `killswitch`). A new one gets a row; if its table raises an event outside the three, add that event (never `scan`) and say so in the commit message.

- [ ] **Step 1: Write the failing tests**

In `<wt>/frontend/src/app/stores/live.store.spec.ts`:

(a) Replace the test `'refreshes on exactly the trades, scan, bot and risk events, 2 s apart'` with:

```ts
  it('refreshes on exactly the trades, bot and risk events, 2 s apart (v206: never scan)', () => {
    expect(LIVE_REFRESH_EVENTS).toEqual(['trades', 'bot', 'risk']);
    expect(LIVE_REFRESH_DEBOUNCE_MS).toBe(2000);
  });

  it('sends no /live request for a scan event, however many arrive', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    for (let second = 0; second < 10; second += 1) {
      events.raise('scan');
      tick();
      vi.advanceTimersByTime(1000);
    }
    expect(pending()).toHaveLength(0);
  });
```

(b) In `'folds a burst of events into one request, 2 s after the first'`, change `events.raise('scan');` to `events.raise('bot');`.

(c) Replace `'still refreshes every 2 s while a scan raises scan every second'` with:

```ts
  it('still refreshes every 2 s while trades events arrive every second', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    for (let second = 0; second < 4; second += 1) {
      events.raise('trades');
      tick();
      vi.advanceTimersByTime(1000);
    }
    // A resetting debounce would still be waiting. The fixed window fired at
    // 2 s and at 4 s, and the second load cancelled the first, unanswered one.
    const requests = pending();
    expect(requests.map((r) => r.cancelled)).toEqual([true, false]);
    requests[1].flush(SNAPSHOT);
  });
```

(d) In `'ignores every other event'`, add `events.raise('scan');` after `events.raise('watchlist');`.

- [ ] **Step 2: Run them to verify they fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/stores/live.store.spec.ts`
Expected: FAIL — the exact-array test (`scan` still present), `sends no /live request for a scan event` (a request goes out at 2 s) and `ignores every other event` (scan schedules one).

- [ ] **Step 3: Implement**

In `<wt>/frontend/src/app/stores/live.store.ts`, replace the doc comment and the constant at lines 9-11 with:

```ts
/**
 * The events that can move a dock figure (v206 P1-d: `scan` is not one).
 *
 * `scan` fires about once a second while a scan runs and used to cost a
 * `/live` request every 2 s per tab. Nothing `/live` returns is written by
 * the scan progress itself: what a scan adds that the dock shows is new
 * plans, and the `plans` table raises `trades`. Every field, its source
 * and the event that announces it:
 *
 * | `/live` field                                  | Source (table / input)                     | Trigger                        |
 * |------------------------------------------------|--------------------------------------------|--------------------------------|
 * | heat.open_pct, open_amount, utilisation_pct,   | open trades and resting plans              | `trades` (trades, plans)       |
 * |   headroom_pct, headroom_amount                |   (`open_heat_state`)                      |                                |
 * | heat.balance                                   | account config                             | `account`; a close moves it    |
 * |                                                |                                            |   with `trades`; no scan write |
 * | heat.cap_pct, cap_amount                       | the heat-cap setting                       | `settings`; no scan write      |
 * | heat.includes_resting, availability, reason    | the same read                              | as above                       |
 * | awaiting.count, next_expiry                    | PENDING plans                              | `trades` (plans)               |
 * | killswitch.engaged, since, detail              | killswitch row                             | `risk` (killswitch)            |
 * | events[]: plan_alerted, paper_filled, tp1_hit  | plans                                      | `trades` (plans)               |
 * | events[]: trade_closed                         | trades                                     | `trades` (trades)              |
 * | events[]: killswitch                           | killswitch                                 | `risk` (killswitch)            |
 * | events_meta.availability, missing              | the same reads as events[]                 | as events[]                    |
 * | every `as_of`                                  | the request's clock                        | none (any refresh)             |
 *
 * `bot` (the heartbeat) moves no field itself; it stays from v203 as the
 * once-per-heartbeat catch-up that keeps every `as_of` current. `account` and
 * `settings` are not listed because neither changes during a scan and
 * neither was listed before v206. A field that starts changing during a scan
 * through another table gets that table's own event here -- never `scan`.
 */
export const LIVE_REFRESH_EVENTS = ['trades', 'bot', 'risk'] as const;
```

In the `LiveStore` doc comment, replace `It is a fixed window, not a resetting debounce: a running scan raises \`scan\` about once a second, and a timer that restarted on each one would never fire.` with `It is a fixed window, not a resetting debounce: a busy book raises \`trades\` in bursts, and a timer that restarted on each one would never fire.`

- [ ] **Step 4: Run the spec to verify it passes**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/stores/live.store.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 5: Commit**

```bash
git -C "<wt>" add frontend/src/app/stores/live.store.ts frontend/src/app/stores/live.store.spec.ts
git -C "<wt>" commit -m "feat(v206): /live no longer refetches on scan; field-to-trigger table beside LIVE_REFRESH_EVENTS (V206-11)"
```

### Task V206-12: TapeFeed: failing double-request repro, then in-flight guard

**Model:** sonnet — a reproduction spec that must fail first, then a small guard in one service; the hypothesis is named in the spec.

**Files:**
- Modify: `frontend/src/app/stores/tape-feed.ts`
- Modify: `frontend/src/app/stores/tape-feed.spec.ts`

**Interfaces:**
- Consumes: nothing new. `TapeFeed.register(owner, symbols)` and `TapeFeed.refresh()` keep their signatures.
- Produces: nothing other tasks consume.

Spec P1-e: the probe saw the same 60-symbol `/market/tape` request go out twice within 30 ms at boot. Same-tick callers already coalesce through the `queued` microtask, so the task first writes a spec that **fails on today's code**. Leading hypothesis (brief § 8): `TapeFeed.fetch()` has no in-flight de-duplication, and `TapeStore.load()` (`stores/tape.store.ts:53`) and `MarketIndexStore.load()` (`stores/market-index.store.ts:38`) each call `feed.refresh()` from a later tick than the registration effect, so each sends its own request while the first is still in flight. The fix: a request for the **same** symbol set as the one in flight is not sent again; a different set still goes out (and the older reply is dropped, as today). Trade-off, stated in the code: an event arriving while the same request is in flight joins that request; the next `scan`/`market` tick (30 s throttle) fetches again.

If Step 3 does **not** fail on today's code, the hypothesis is wrong: stop, do not add the guard, record in the commit message which callers were checked and that the double request stays until the probe can tell the cases apart (spec P1-e), commit only the spec (with the reproduction marked `it.skip` and a comment naming what it ruled out), and report it.

- [ ] **Step 1: Confirm the callers the hypothesis names**

Run: `git -C "<wt>" grep -n "feed.refresh()\|\.load()" -- frontend/src/app/stores/tape.store.ts frontend/src/app/stores/market-index.store.ts frontend/src/app/shell`
Expected: `load: (): void => feed.refresh()` in both stores, and at least one `.load()` call on them from the shell (the strip / tape components). Note the callers for the commit message.

- [ ] **Step 2: Write the reproduction and the guard's tests**

In `<wt>/frontend/src/app/stores/tape-feed.spec.ts`:

(a) Replace `'a late reply from an older request is dropped'` (it relied on a second request for the same symbols, which the guard now stops) with the same check driven by a symbol change:

```ts
  it('a late reply from an older request is dropped', async () => {
    const pending: Subject<TapeResponse>[] = [];
    api.tape.mockImplementation(() => { const s = new Subject<TapeResponse>(); pending.push(s); return s; });
    const symbols = signal(['A']);
    feed.register('tape', symbols);
    await flush();
    symbols.set(['B']);
    await flush();
    expect(pending.length).toBe(2);
    pending[1].next({ as_of: 'fresh', rows: [row('B')] });
    pending[0].next({ as_of: 'stale', rows: [row('A')] });
    expect(Object.keys(feed.rows())).toEqual(['B']);
    expect(feed.asOf()).toBe('fresh');
  });
```

(b) Append, inside the `describe('TapeFeed', …)` block:

```ts
  /* -- v206 P1-e: one boot request, not two ------------------------------ */

  const holdRequests = () => {
    const pending: Subject<TapeResponse>[] = [];
    api.tape.mockImplementation(() => { const s = new Subject<TapeResponse>(); pending.push(s); return s; });
    return pending;
  };

  it('a store load() in a later tick, while the same request is in flight, sends nothing more', async () => {
    // The 2026-11-05 probe: the same 60-symbol request twice within 30 ms at
    // boot. Registration's effect fetches in one tick; TapeStore.load() and
    // MarketIndexStore.load() call refresh() from later ones.
    holdRequests();
    feed.register('index', signal(['^GSPC']));
    feed.register('tape', signal(['NVDA']));
    await flush();
    expect(api.tape).toHaveBeenCalledTimes(1);

    feed.refresh(); // TapeStore.load()
    await flush();
    feed.refresh(); // MarketIndexStore.load()
    await flush();

    expect(api.tape).toHaveBeenCalledTimes(1);
  });

  it('once the reply lands, the next refresh fetches again', async () => {
    const pending = holdRequests();
    feed.register('tape', signal(['NVDA']));
    await flush();
    pending[0].next({ as_of: 'a', rows: [row('NVDA')] });
    pending[0].complete();
    feed.refresh();
    await flush();
    expect(api.tape).toHaveBeenCalledTimes(2);
  });

  it('a failed request releases the guard', async () => {
    const pending = holdRequests();
    feed.register('tape', signal(['NVDA']));
    await flush();
    pending[0].error(new Error('down'));
    feed.refresh();
    await flush();
    expect(api.tape).toHaveBeenCalledTimes(2);
  });

  it('a different symbol set is never held back by an in-flight request', async () => {
    holdRequests();
    const symbols = signal(['NVDA']);
    feed.register('tape', symbols);
    await flush();
    symbols.set(['NVDA', 'AMD']);
    await flush();
    expect(api.tape).toHaveBeenCalledTimes(2);
    expect(api.tape).toHaveBeenLastCalledWith(['NVDA', 'AMD']);
  });

  it('an event during the same in-flight request joins it (the next tick refetches)', async () => {
    holdRequests();
    feed.register('tape', signal(['NVDA']));
    await flush();
    events.raise('market');
    await flush();
    expect(api.tape).toHaveBeenCalledTimes(1);
  });
```

- [ ] **Step 3: Run them to verify the reproduction fails on today's code**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/stores/tape-feed.spec.ts`
Expected: FAIL — `a store load() in a later tick…` expects 1 call and sees 3, and `an event during the same in-flight request joins it` sees 2. The rewritten late-reply test and the release tests pass on today's code (they pin behaviour the guard must keep). If the reproduction passes here, follow the "hypothesis is wrong" paragraph above.

- [ ] **Step 4: Implement the in-flight guard**

In `<wt>/frontend/src/app/stores/tape-feed.ts`:

(a) Add the field after `private queued = false;`:

```ts
  /** The symbol set of the request in flight, or null (v206 P1-e). */
  private inflight: string | null = null;
```

(b) Add to the class doc comment, after the coalescing sentence: ` A refresh from a later tick while the same request is still in flight joins it (v206: the boot fired the same 60-symbol request twice within 30 ms, from the registration effect and a store's load()); an event that lands meanwhile is caught by the next throttled tick.`

(c) Replace `private fetch()` with:

```ts
  private fetch(): void {
    const symbols = this.merged();
    const key = symbols.join(',');
    if (symbols.length && this.inflight === key) return;
    const request = ++this.latestRequest;
    if (!symbols.length) {
      this.inflight = null;
      this._rows.set({});
      this._loading.set(false);
      return;
    }
    this.inflight = key;
    this._loading.set(true);
    this.api.tape(symbols).subscribe({
      next: (response) => {
        if (request !== this.latestRequest) return;
        if (!response || !Array.isArray(response.rows)) return;
        this._rows.set(Object.fromEntries(response.rows.map((r) => [r.symbol.toUpperCase(), r])));
        this._asOf.set(response.as_of ?? null);
        this._loading.set(false);
      },
      // Silent and non-destructive: see the class comment.
      error: () => {
        this.settle(request);
        if (request === this.latestRequest) this._loading.set(false);
      },
      complete: () => this.settle(request),
    });
  }

  /** The newest request has ended: the next refresh may send again. An
   *  older request ending says nothing about the one now in flight. */
  private settle(request: number): void {
    if (request === this.latestRequest) this.inflight = null;
  }
```

`inflight` is set **before** `subscribe`, because a synchronous observable (the spec's `of(...)`) completes inside `subscribe`.

- [ ] **Step 5: Run the spec and the stores built on the feed to verify they pass**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/stores/tape-feed.spec.ts --include src/app/shell/tape/tape.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 6: Commit**

```bash
git -C "<wt>" add frontend/src/app/stores/tape-feed.ts frontend/src/app/stores/tape-feed.spec.ts
git -C "<wt>" commit -m "fix(v206): one boot /market/tape request -- a later-tick refresh joins the same in-flight request (V206-12)"
```

