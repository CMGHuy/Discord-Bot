# v189 — Book integrity and partial-trade truth: Implementation Plan, part 7b of 7 — clear replies on the Trades page, docs and release

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier. **Never read this part whole**: `grep -n "^### Task V189-25:" -A 330 <this file>`.

**Spec:** [2026-10-23-v189-book-integrity-partial-truth-design.md](../specs/2026-10-23-v189-book-integrity-partial-truth-design.md) — D4 A6 (the reset's confirmation names the archive, the throttle and kill-switch state; refused while the kill switch is tripped unless forced), D4 A7 (the delete confirmation names the positions it ends), D6 (`LABEL_BASIS_SINCE` set at release), § Testing (one full-suite run as the final task); `## Corrections from the code brief` 1 (`check_bar` is test-only, recorded in `known-traps.md`).
**Index:** [2026-10-23-v189-book-integrity-partial-truth_0-index.md](2026-10-23-v189-book-integrity-partial-truth_0-index.md) — `## Global Constraints`, `## Spec clarifications` 9, 10 and 13, `## Contracts` § Account reset, `## Parallelisation`, the task ledger.
**Part 7:** [2026-10-23-v189-book-integrity-partial-truth_7-frontend-and-release.md](2026-10-23-v189-book-integrity-partial-truth_7-frontend-and-release.md) holds V189-21..V189-24, the "consumed from earlier parts" list (V189-14's clear-open reply and V189-16's clear-history reply are quoted there) and the frontend conventions every frontend task follows (narrow `ng test --include` runs, then the whole `ng test` and `npm run lint`; optional new model fields; frontend commits never carry backend files).
**Worktree:** `.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth`. Every path below is relative to it; every command runs from it. Agent shells drop variables between calls, so `cd "$WT"` means `WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth; cd "$WT" && ...` in the same command.

# Phase G (continued) — Clear replies, docs and release

### Task V189-25: Frontend: clear-open notice; clear-history force, refusal and archive

**Model:** sonnet — two reply shapes followed through one API method, one store and one page, with a fixed status-to-message mapping and a second confirmation; every branch is pinned by HTTP-level specs.

**Spec:** D4 A6 (the reset's confirmation names the archive and states the throttle and kill-switch state; refused while the kill switch is tripped unless the caller passes an explicit override; a tripped kill switch is never cleared as a side effect), D4 A7 (the delete confirmation names every ACTIVE/PARTIAL position it ends and says monitoring stops); index clarification 13 (partner decision 2026-10-23: the SPA shows the clear-open notice, the refusal text, an explicit confirmed force retry, the archive name and notice on success, and a distinct archive-failed error); `docs/claude/ui-design.md` § Checklist (44px targets, wrapping, no horizontal scroll, layout audit at 390/768/1440).

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`ClearResult` `:326-332`)
- Modify: `frontend/src/app/api/api-client.ts` (imports `:27`; `clearTradeHistory` `:192-194`)
- Modify: `frontend/src/app/stores/trades.store.ts` (`TradesSlice` `:43-49`; initial state `:94-96`; `clearOpen` / `clearHistory` `:180-224`)
- Modify: `frontend/src/app/workspaces/trades/trades.ts` (message block `:156-163`; bulk dialog `:526-535`; `bulkTitle` / `bulkConsequence` / `runBulk` `:1116-1135`; styles `:550-554`)
- Create: `frontend/src/app/stores/trades-clear.fixture.ts`
- Create: `frontend/src/app/stores/trades-clear.spec.ts`
- Create: `frontend/src/app/workspaces/trades/trades-clear.spec.ts`

**Interfaces:**
- Consumes (V189-14, V189-16; quoted in part 7's header): the clear-open 200 body `{removed, ended, notice}`; the clear-history 200 body `{removed, removed_plans, archive, throttle: {multiplier, paused}, kill_switch, notice}`, its 409 `kill_switch_tripped` (message = `REFUSED_TEXT`) and 500 `archive_failed`; force = JSON body `{"force": true}`. `ApiError(code, status, message)` from `errorInterceptor` (`api/interceptors.ts`).
- Produces:
  - `models.ts`: `interface EndedPlanRow { plan_id: string; ticker: string; status_before: string; status_after: string }`; `ClearResult { removed: number; ended?: EndedPlanRow[]; notice?: string }`; `interface ClearHistoryResult { removed: number; removed_plans: number; archive: string; throttle: { multiplier: number; paused: boolean }; kill_switch: boolean; notice: string }`.
  - `ApiClient.clearTradeHistory(force = false): Observable<ClearHistoryResult>` — POSTs `{ force: true }` when forced, `{}` otherwise.
  - `TradesSlice.clearNotice: string | null`, `TradesSlice.clearRefusal: string | null`; `TradesStore.clearHistory(force = false): void`.
  - Exact copy (pinned by the specs): clear-open result `Cleared {n} open position(s).` (unchanged); reset result `Cleared {n} closed trade(s) and {m} finished plan(s). Archived as {archive}.` (singular/plural per count, as today); archive failure `Nothing was cleared: the archive could not be written ({message}).`; other failures `Nothing was cleared — {message}` (unchanged); the force dialog per Step 5.

- [ ] **Step 1: Write the shared reply fixture and the failing store spec**

Create `frontend/src/app/stores/trades-clear.fixture.ts` (test-only, like `workspaces/analytics/tabs/variance-band.fixture.ts`; both specs below import it, so the server's reply shape exists once — a spec file is never imported, which would register its tests twice):

```ts
import { ClearHistoryResult } from '../api/models';

/* v189 A6: the clear-history replies, as V189-16's endpoint sends them. */

export const REFUSED = 'Reset refused: the kill switch is tripped. Release it first, or force the reset '
  + '(`force=true` on the endpoint, `!trades clear history force` or '
  + '`/trades-clear-history force:True`); the kill switch stays on either way.';

export const RESET: ClearHistoryResult = {
  removed: 4, removed_plans: 2, archive: 'account-reset-20261024T101500Z.json',
  throttle: { multiplier: 1, paused: false }, kill_switch: false,
  notice: 'Account reset: removed 4 closed trade(s) and 2 finished plan(s). ...\nArchive: account-reset-20261024T101500Z.json\n...',
};
```

Create `frontend/src/app/stores/trades-clear.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../api/event-stream';
import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { REFUSED, RESET } from './trades-clear.fixture';
import { TradesStore } from './trades.store';

/* v189 A6/A7: what the bulk clears now answer. Clear open names the plans it
 * ended; clear history is an archived reset that is refused while the kill
 * switch is tripped unless forced. */

const OPEN_URL = '/api/v1/trades/clear-open';
const HISTORY_URL = '/api/v1/trades/clear-history';

describe('TradesStore bulk clears (v189)', () => {
  let store: InstanceType<typeof TradesStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: { changes: () => signal(0) } },
        TradesStore,
      ],
    });
    store = TestBed.inject(TradesStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const post = (url: string) => backend.expectOne((r) => r.method === 'POST' && r.url === url);
  const fail = (url: string, status: number, code: string, message: string) =>
    post(url).flush({ error: { code, message } }, { status, statusText: 'x' });

  it('shows the clear-open notice naming the positions it ended', () => {
    const notice = 'Ended 1 open position(s): AAPL (`p1`, was PARTIAL). ...';
    store.clearOpen();
    post(OPEN_URL).flush({ removed: 2, ended: [{ plan_id: 'p1', ticker: 'AAPL', status_before: 'PARTIAL', status_after: 'CLOSED' }], notice });
    expect(store.clearResult()).toBe('Cleared 2 open positions.');
    expect(store.clearNotice()).toBe(notice);
  });

  it.each([{ removed: 1, ended: [], notice: '' }, { removed: 1 }])(
    'keeps no notice when nothing ended or the server sends none: %o', (body) => {
      store.clearOpen();
      post(OPEN_URL).flush(body);
      expect(store.clearResult()).toBe('Cleared 1 open position.');
      expect(store.clearNotice()).toBeNull();
    });

  it('sends no force by default and names the archive on success', () => {
    store.clearHistory();
    const req = post(HISTORY_URL);
    expect(req.request.body).toEqual({});
    req.flush(RESET);
    expect(store.clearResult()).toBe(
      'Cleared 4 closed trades and 2 finished plans. Archived as account-reset-20261024T101500Z.json.');
    expect(store.clearNotice()).toBe(RESET.notice);
    expect(store.clearRefusal()).toBeNull();
    expect(store.clearing()).toBeNull();
  });

  it('singularises one trade and one plan', () => {
    store.clearHistory();
    post(HISTORY_URL).flush({ ...RESET, removed: 1, removed_plans: 1 });
    expect(store.clearResult()).toBe(
      'Cleared 1 closed trade and 1 finished plan. Archived as account-reset-20261024T101500Z.json.');
  });

  it('holds a kill-switch refusal apart from an error, and never retries on its own', () => {
    store.clearHistory();
    fail(HISTORY_URL, 409, 'kill_switch_tripped', REFUSED);
    expect(store.clearRefusal()).toBe(REFUSED);
    expect(store.clearError()).toBeNull();
    expect(store.clearResult()).toBeNull();
    expect(store.clearing()).toBeNull();
    backend.expectNone((r) => r.url === HISTORY_URL);
  });

  it('sends force only when asked, and a forced retry clears the refusal at once', () => {
    store.clearHistory();
    fail(HISTORY_URL, 409, 'kill_switch_tripped', REFUSED);
    store.clearHistory(true);
    expect(store.clearRefusal()).toBeNull();
    const req = post(HISTORY_URL);
    expect(req.request.body).toEqual({ force: true });
    req.flush({ ...RESET, kill_switch: true });
    expect(store.clearResult()).toContain('Archived as');
  });

  it('reads an archive failure as its own error, not as a refusal', () => {
    store.clearHistory();
    fail(HISTORY_URL, 500, 'archive_failed', 'archive write failed: disk full');
    expect(store.clearError()).toBe('Nothing was cleared: the archive could not be written (archive write failed: disk full).');
    expect(store.clearRefusal()).toBeNull();
  });

  it('keeps the generic failure for anything else, on both clears', () => {
    store.clearOpen();
    fail(OPEN_URL, 409, 'conflict', 'another change holds the trade; try again');
    expect(store.clearError()).toBe('Nothing was cleared — another change holds the trade; try again');
    store.clearHistory();
    fail(HISTORY_URL, 503, 'unavailable', 'The admin could not be reached.');
    expect(store.clearError()).toBe('Nothing was cleared — The admin could not be reached.');
    expect(store.clearRefusal()).toBeNull();
  });

  it('starts every clear from a blank slate', () => {
    store.clearHistory();
    fail(HISTORY_URL, 409, 'kill_switch_tripped', REFUSED);
    store.clearOpen();
    expect([store.clearResult(), store.clearNotice(), store.clearRefusal(), store.clearError()])
      .toEqual([null, null, null, null]);
    post(OPEN_URL).flush({ removed: 0, ended: [], notice: '' });
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd "$WT/frontend" && npx ng test --watch=false --include src/app/stores/trades-clear.spec.ts
```

Expected: FAIL — `ClearHistoryResult` is not exported from `../api/models` (the fixture's import) and `store.clearNotice is not a function`.

- [ ] **Step 3: Implement the model, the client and the store**

`frontend/src/app/api/models.ts`: replace the `ClearResult` block (keep its doc comment's point about the count) with

```ts
/** One plan a delete ended (v189 A7): a waiting plan cancelled, or a held
 *  position closed with no P&L. */
export interface EndedPlanRow {
  plan_id: string;
  ticker: string;
  status_before: string;
  status_after: string;
}

/** `POST /trades/clear-open`. The count is what the confirmation reports --
 *  "cleared" without a number cannot be told from "there was nothing to
 *  clear". v189 A7: `ended` lists the plans the delete ended and `notice`
 *  says what that means ("" when nothing ended). Both optional so a reply
 *  from a pre-v189 server still reads. */
export interface ClearResult {
  removed: number;
  ended?: EndedPlanRow[];
  notice?: string;
}

/** `POST /trades/clear-history` since v189 A6: an archived full reset.
 *  `archive` is a file NAME on the server's data volume, never a path. */
export interface ClearHistoryResult {
  removed: number;
  removed_plans: number;
  archive: string;
  throttle: { multiplier: number; paused: boolean };
  kill_switch: boolean;
  notice: string;
}
```

`frontend/src/app/api/api-client.ts`: import `ClearHistoryResult`; replace `clearTradeHistory()` with

```ts
  /** v189 A6: an archived full reset. 409 `kill_switch_tripped` while the
   *  kill switch is on unless `force`; forcing never releases it. */
  clearTradeHistory(force = false): Observable<ClearHistoryResult> {
    return this.http.post<ClearHistoryResult>(`${this.base}/trades/clear-history`, force ? { force: true } : {});
  }
```

`frontend/src/app/stores/trades.store.ts`:

- `TradesSlice` gains, after `clearError`:

```ts
  /** v189: the server's own words after a clear -- the plans a delete ended,
   *  or the reset's archive, throttle and kill-switch lines. Multi-line. */
  clearNotice: string | null;
  /** v189 A6: the reset was refused because the kill switch is tripped.
   *  Not an error: nothing failed, and the page offers a confirmed force. */
  clearRefusal: string | null;
```

  and the initial state gains `clearNotice: null, clearRefusal: null`.
- every clear starts with `patchState(store, { clearing: <kind>, clearResult: null, clearError: null, clearNotice: null, clearRefusal: null });`.
- `clearOpen`'s `next` becomes `({ removed, notice }) => patchState(store, { clearing: null, clearResult: \`Cleared ${removed} open position${removed === 1 ? '' : 's'}.\`, clearNotice: notice || null })`; its `error` is unchanged.
- `clearHistory(force = false)` calls `api.clearTradeHistory(force)`; `next` sets `clearing: null`, `clearResult` from `resetResult(body)` and `clearNotice: body.notice || null`; `error` sets `clearing: null` plus `historyFailure(error)`. Module-level helpers:

```ts
const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? '' : 's'}`;

function resetResult(body: ClearHistoryResult): string {
  return `Cleared ${plural(body.removed, 'closed trade')} and ${plural(body.removed_plans, 'finished plan')}. `
    + `Archived as ${body.archive}.`;
}

/** 409 kill_switch_tripped is a refusal, not a failure; archive_failed says
 *  why nothing was deleted; anything else reads as today. */
function historyFailure(error: ApiError): Partial<TradesSlice> {
  if (error.code === 'kill_switch_tripped') return { clearRefusal: error.message };
  if (error.code === 'archive_failed') {
    return { clearError: `Nothing was cleared: the archive could not be written (${error.message}).` };
  }
  return { clearError: `Nothing was cleared — ${error.message}` };
}
```

  Update `clearHistory`'s doc comment: it is now an archived reset; a refusal is held in `clearRefusal` and never retried here, only by the caller passing `force`.

- [ ] **Step 4: Run the store spec to verify it passes**

```bash
cd "$WT/frontend" && npx ng test --watch=false --include src/app/stores/trades-clear.spec.ts --include src/app/stores/trades.store.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Write the failing page spec**

Create `frontend/src/app/workspaces/trades/trades-clear.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../api/interceptors';
import { ConnectionStore } from '../../stores/connection.store';
import { PreferencesStore } from '../../stores/preferences.store';
import { TradesStore } from '../../stores/trades.store';
import { REFUSED, RESET } from '../../stores/trades-clear.fixture';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { FORCE_RESET_CONSEQUENCE, Trades } from './trades';

/* v189 A6/A7 on the Trades page: the notice after a clear, the refusal with
 * an explicitly confirmed force, and the bulk-dialog wording. */

const HISTORY_URL = '/api/v1/trades/clear-history';

describe('Trades bulk-clear replies (v189)', () => {
  let fixture: ComponentFixture<Trades>;
  let backend: HttpTestingController;
  const el = () => fixture.nativeElement as HTMLElement;
  const forceDialog = () => el().querySelector('sb-confirm-dialog[data-dialog="force-reset"]')!;

  beforeEach(() => {
    installDialogPolyfill();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
        provideHttpClientTesting(),
        TradesStore,
        { provide: ConnectionStore, useValue: { currency: signal('$') } },
        { provide: PreferencesStore, useValue: { values: signal({}), isLoaded: signal(true), update: () => undefined } },
      ],
    });
    fixture = TestBed.createComponent(Trades);
    fixture.detectChanges();
    backend = TestBed.inject(HttpTestingController);
  });

  const patch = (state: Record<string, unknown>) => {
    patchState(unprotected(TestBed.inject(TradesStore)), state);
    fixture.detectChanges();
  };

  it('shows the server notice under the result, in its pre-line block', () => {
    patch({ clearResult: 'Cleared 2 open positions.', clearNotice: 'Ended 1 open position(s): AAPL\nNo more stop or take-profit alerts.' });
    const notice = el().querySelector('[data-testid="clear-notice"]')!;
    expect(notice.getAttribute('role')).toBe('status');
    expect(notice.textContent).toContain('Ended 1 open position(s): AAPL');
    expect(notice.textContent).toContain('No more stop or take-profit alerts.');
    expect(notice.classList).toContain('clear-notice');           // white-space: pre-line keeps the lines
  });

  it('shows a refusal as an alert with a force button, and sends nothing by itself', () => {
    patch({ clearRefusal: REFUSED });
    const refusal = el().querySelector('[data-testid="clear-refusal"]')!;
    expect(refusal.getAttribute('role')).toBe('alert');
    expect(refusal.textContent).toContain('Reset refused: the kill switch is tripped.');
    expect(refusal.querySelector('button')!.textContent!.trim()).toBe('Reset anyway…');
    expect(el().querySelector('.command-error')).toBeNull();
    backend.expectNone((r) => r.url === HISTORY_URL);
  });

  it('forces only after its own confirmation, which says the kill switch stays on', () => {
    patch({ clearRefusal: REFUSED });
    (el().querySelector('[data-testid="clear-refusal"] button') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(forceDialog().textContent).toContain(FORCE_RESET_CONSEQUENCE);
    expect(FORCE_RESET_CONSEQUENCE).toContain('The kill switch stays on');
    backend.expectNone((r) => r.url === HISTORY_URL);

    const buttons = forceDialog().querySelectorAll('button');
    (buttons[buttons.length - 1] as HTMLButtonElement).click();
    fixture.detectChanges();
    const req = backend.expectOne((r) => r.method === 'POST' && r.url === HISTORY_URL);
    expect(req.request.body).toEqual({ force: true });
    req.flush({ ...RESET, kill_switch: true });
    fixture.detectChanges();
    expect(el().querySelector('[data-testid="clear-refusal"]')).toBeNull();
    expect(el().querySelector('.cleared')!.textContent).toContain('Archived as account-reset-20261024T101500Z.json');
  });

  it('cancelling the force dialog sends nothing and keeps the refusal on screen', () => {
    patch({ clearRefusal: REFUSED });
    (el().querySelector('[data-testid="clear-refusal"] button') as HTMLButtonElement).click();
    fixture.detectChanges();
    (forceDialog().querySelectorAll('button')[0] as HTMLButtonElement).click();
    fixture.detectChanges();
    backend.expectNone((r) => r.url === HISTORY_URL);
    expect(el().querySelector('[data-testid="clear-refusal"]')).not.toBeNull();
  });

  it('shows an archive failure as an error, with no force offered', () => {
    patch({ clearError: 'Nothing was cleared: the archive could not be written (disk full).' });
    expect(el().querySelector('.command-error')!.textContent).toContain('the archive could not be written');
    expect(el().querySelector('[data-testid="clear-refusal"]')).toBeNull();
  });
});
```

Run:

```bash
cd "$WT/frontend" && npx ng test --watch=false --include src/app/workspaces/trades/trades-clear.spec.ts
```

Expected: FAIL — `FORCE_RESET_CONSEQUENCE` is not exported from `./trades`, no `[data-testid="clear-notice"]`.

- [ ] **Step 6: Implement the page**

`frontend/src/app/workspaces/trades/trades.ts`:

- module-level, exported beside `TRADES_CONTROLS`:

```ts
/** v189 A6: the second, explicit confirmation a forced reset needs. */
export const FORCE_RESET_CONSEQUENCE =
  'The kill switch is tripped. Forcing the reset still archives every closed trade and finished plan to a file '
  + 'on the server first, then deletes them and restarts realized P&L and the drawdown history from the base '
  + 'balance, which lifts any throttle. The kill switch stays on: release it on the Risk page. New trades are '
  + 'sized off the base balance.';
```

- the message block at the top of the template becomes:

```html
    @if (store.clearResult(); as message) {
      <!-- The count, not just "done": "cleared 0" and "cleared 40" are
           different answers and want different reactions. -->
      <p class="cleared" role="status">{{ message }}</p>
    }
    @if (store.clearNotice(); as notice) {
      <!-- v189: the server's own lines -- the plans a delete ended, or the
           reset's archive, throttle and kill switch. Line breaks kept. -->
      <p class="clear-notice" role="status" data-testid="clear-notice">{{ notice }}</p>
    }
    @if (store.clearRefusal(); as refusal) {
      <!-- v189 A6: a refusal, not a failure. The force is one more explicit
           step, never a retry the page makes on its own. -->
      <div class="clear-refusal" role="alert" data-testid="clear-refusal">
        <p>{{ refusal }}</p>
        <button sb-button variant="danger" type="button" (click)="forceOpen.set(true)">Reset anyway…</button>
      </div>
    }
    @if (store.clearError(); as message) {
      <p class="command-error" role="alert">{{ message }}</p>
    }
```

- after the bulk `<sb-confirm-dialog>` add

```html
    <sb-confirm-dialog
      data-dialog="force-reset"
      [open]="forceOpen()"
      title="Reset while the kill switch is tripped"
      [consequence]="forceResetConsequence"
      confirmLabel="Force reset"
      [working]="store.clearing() !== null"
      (confirmed)="runForceReset()"
      (cancelled)="forceOpen.set(false)"
    />
```

- class members: `protected readonly forceOpen = signal(false);`, `protected readonly forceResetConsequence = FORCE_RESET_CONSEQUENCE;`, and

```ts
  protected runForceReset(): void {
    this.store.clearHistory(true);
    this.forceOpen.set(false);
  }
```

- `bulkTitle`: `'Reset trade history'` for history (the open one is unchanged). `bulkConsequence`:
  - history: `'Clearing history is a full reset. Every closed trade and finished plan is archived to a file on the server, then deleted, and realized P&L and the drawdown history restart from the base balance, which lifts any throttle. New trades are sized off the base balance. Open positions and live plans are untouched. Refused while the kill switch is tripped.'`
  - open: `'Every open position is deleted permanently — the whole book, not just this page or this filter. Linked plans end with it: waiting plans are cancelled, held positions are no longer monitored (no more stop or take-profit alerts), and banked TP1 dollars leave the balance with the trade. Closed history is untouched, and nothing is closed at a price. This cannot be undone.'`
  - update the comment above it: the history clear is an archived reset since v189, not a plain delete.
- styles, after `.command-error`:

```css
    /* v189: the server's multi-line notice; an archive name has no spaces to
       break on, so it may wrap anywhere rather than push the page sideways. */
    .clear-notice {
      margin: 0; white-space: pre-line; overflow-wrap: anywhere;
      color: var(--text-secondary); font-size: var(--text-table);
    }
    .clear-refusal {
      display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-8) var(--space-10);
      color: var(--neg); font-size: var(--text-table);
    }
    .clear-refusal p { margin: 0; flex: 1 1 24rem; min-width: 0; overflow-wrap: anywhere; }
    /* A real target on touch screens; full width on a phone so it never
       shares a cramped line with the refusal text. */
    .clear-refusal button { min-height: var(--control-h); }
    @media (max-width: 639px) { .clear-refusal button { width: 100%; } }
```

Phone (< 640px): the refusal text wraps and the button takes the full width at 44px; tablet (640–1023px) and desktop: text and button share a row and wrap only when the text needs 24rem. The force dialog is `sb-confirm-dialog`, which is already laid out for all three classes. The "Clear history" control itself stays where `TRADES_CONTROLS` puts it (inline from `lg`, in the toolbar sheet below).

- [ ] **Step 7: Run the specs to verify they pass**

```bash
cd "$WT/frontend" && npx ng test --watch=false --include src/app/workspaces/trades/trades-clear.spec.ts --include src/app/stores/trades-clear.spec.ts --include src/app/workspaces/trades/trades.spec.ts --include src/app/ui/controls.spec.ts
```

Expected: PASS.

- [ ] **Step 8: Whole frontend run and lint**

```bash
cd "$WT/frontend" && npx ng test --watch=false && npm run lint
```

Expected: `0 failed`; lint clean.

- [ ] **Step 9: Check every v189 screen at 390, 768 and 1440 (the part's one layout pass)**

Against a local replica (`docs/claude/ui-design.md` § Checklist; the replica is from V189-1's `/replicate-prod-db`, re-run it if this is a new session). From the worktree, with the admin login read from `.env` inside the scripts, never printed:

```bash
cd "$WT/frontend" && npm run build
cd "$WT" && python admin_ui.py            # leave running in a second shell; it serves http://localhost:1234
cd "$WT/frontend" && node scripts/browse.mjs login --base http://localhost:1234
cd "$WT/frontend" && node scripts/layout-audit.mjs --base http://localhost:1234
```

Expected: the audit exits 0 at 390, 768 and 1440 (it covers Trades, Trade detail, Risk and Analytics, the four pages this part touched). A finding is fixed in the task that owns the page, never allow-listed.

Then the refusal state, which the audit cannot reach. Engage the kill switch on the LOCAL replica only (the admin process reads the database named by the worktree's `.env`; confirm it is the local replica before running this):

```bash
cd "$WT" && python -c "from swingbot.core.db.repositories.killswitch import killswitch_repo; killswitch_repo().engage('v189 layout check')"
cd "$WT/frontend" && node scripts/browse.mjs shots --base http://localhost:1234 --out "$TMP/v189-refusal" --path /trades --widths 1440 --click 'button[slot="clear-history"]' --click 'sb-confirm-dialog dialog[open] button:last-of-type' --click '[data-testid="clear-refusal"] button'
cd "$WT/frontend" && node scripts/browse.mjs shots --base http://localhost:1234 --out "$TMP/v189-refusal" --path /trades --widths 768,390 --click '.toolbar-sheet-button' --click 'button[slot="clear-history"]' --click 'sb-confirm-dialog dialog[open] button:last-of-type' --click '[data-testid="clear-refusal"] button'
cd "$WT" && python -c "from swingbot.core.db.repositories.killswitch import killswitch_repo; killswitch_repo().release()"
```

(`$TMP` is the session scratchpad.) Expected: each `trades@<width>.txt` starts with `page-scroll-x: 0`, contains `Reset refused: the kill switch is tripped.` and the force dialog's `The kill switch stays on`; in each PNG the refusal text wraps inside the page and the button is at least 44px tall (full width at 390). **Never click "Force reset"** in this check: it would reset the local replica. The release line runs even if a shot fails.

- [ ] **Step 10: Commit**

```bash
cd "$WT" && git add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/stores/trades.store.ts frontend/src/app/stores/trades-clear.fixture.ts frontend/src/app/stores/trades-clear.spec.ts frontend/src/app/workspaces/trades/trades.ts frontend/src/app/workspaces/trades/trades-clear.spec.ts && git commit -m "feat(ui): clear-open shows the ended plans; clear-history shows its archive, refusal and a confirmed force (v189 A6/A7)"
```

### Task V189-26: Known traps and audit doc record what v189 left

**Model:** haiku — moving one misplaced paragraph and adding fixed text to two docs; no code, the wording is given below.

**Spec:** Corrections 1 (`known-traps.md` records that `check_bar` is test-only), D1 (the inline R formulas outside the code this spec edits are left and recorded in the audit doc), § Known historical records (fix forward only; the metric-definitions spec owns the backfill); index Global Constraints (`known-traps.md` is edited only here, and the `AGENTS.md` mirror is checked).

**Files:**
- Modify: `docs/claude/known-traps.md` (the empty `## \`PlanManager.check_bar()\` is unwired — do not "fix" it` heading `:250`; the stray `check_bar` paragraph at the end of `## Scan parameter and replay gate parity (v74)` `:262`; `## Re-exports, stale prices and plan closes` `:141-184`)
- Modify: `docs/superpowers/results/v187/2026-10-23-repo-audit-findings.md` (status table `:9-15`; `## F. Smells` F1 `:109`)
- Modify: `AGENTS.md` — only if Step 3's mirror test fails

**Interfaces:**
- Consumes: the merged names from earlier tasks, re-checked with `git grep -n` before they are written into a doc: `PlanStore.update` (V189-6), `_persist_fill` / `_persist_partial` / `_persist_terminal` (V189-8), `take_exit_failures` (V189-9), `plan_links.end_linked_plan` (V189-12), `account_reset.reset_closed_history`, `restore_account_reset.py` (V189-15/17), `metrics.leg_contribution_r`, `metrics.net_outcome` (V189-1/2).
- Produces: nothing code reads.

- [ ] **Step 1: Fill the empty `check_bar` section**

In `docs/claude/known-traps.md`, cut the paragraph that begins `` `check_bar` / `_check_bar_active` / `_check_bar_partial` model overnight gap fills `` from the end of `## Scan parameter and replay gate parity (v74)` and paste it, unchanged, under the empty heading `## \`PlanManager.check_bar()\` is unwired — do not "fix" it`. Then append to it:

```markdown

v189 routed every plan write through the guarded `PlanStore.update` (row lock,
stale-terminal refusal, tighter-stop merge) and the `_persist_fill` /
`_persist_partial` / `_persist_terminal` transactions. `check_bar` shares those
helpers, so it inherits the guards, but it has no dedicated tests and its
exit-retry path is reachable from tests only. Wiring it in is still a design
change, not a fix.
```

- [ ] **Step 2: Add the v189 traps to `## Re-exports, stale prices and plan closes`**

Append these bullets at the end of that section's list (same voice and line width as its other bullets):

```markdown
- **Every plan write is one guarded call (v189).** `PlanStore.update` takes
  the plan row `FOR UPDATE`, returns `False` instead of overwriting a CLOSED
  or CANCELLED row with a stale copy, and keeps the tighter of the stored and
  incoming stops. Never write a plan document any other way (a raw repository
  upsert brings back the lost update v189 closed). Lock order is plan row,
  then trade row, then account rows; no `threading.Lock` is held while
  waiting on a row, and network calls happen before any lock.
- **A trade's leg, fill and close commit with the plan, or not at all.** The
  plan manager's `_persist_*` helpers pass one `conn` to `TradeLog` and the
  account balance; only the journal and the snapshot refresh run after
  commit (`run_after_commit`). A new close path passes `conn=` through and
  collects its hooks the same way. A failed exit is retried once and then
  posted to the ops channel (`take_exit_failures`), never dropped silently.
- **Deleting a trade ends its plan.** `clear_open` and `delete_trade` end the
  linked plan in the same transaction (`plan_links.end_linked_plan`): a
  PENDING plan is cancelled (`cancelled_trade_deleted`), an ACTIVE/PARTIAL
  one closed with no P&L. A reversal against an unfilled placeholder cancels
  the plan instead of booking P&L.
- **Clearing history is an archived reset.** `account_reset.reset_closed_history`
  writes `data/archives/account-reset-<UTC>.json` first, then deletes closed
  trades, terminal plans and the balance history and reseeds one point at
  `base_balance`. It is refused while the kill switch is tripped unless
  forced, and never releases it. `scripts/ops/restore_account_reset.py`
  undoes the latest reset (`docs/deploy/DEPLOY_HETZNER.md`).
- **Leg sums use the contribution, labels use the net.** Anything that adds
  legs uses `metrics.leg_contribution_r` (fraction × R); a close with two or
  more legs is labelled by `metrics.net_outcome` (live only — the backtest
  still labels a TP1 touch `win`, pinned by a test). Scaled-out labels before
  `metrics.LABEL_BASIS_SINCE` were not backfilled.
```

- [ ] **Step 3: Check the Codex mirror**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
```

Expected: PASS. If it fails on `known-traps.md`, add the one condensed line it asks for to the matching bullet in `AGENTS.md` (the `known-traps.md:` bullet near `:199`), re-run, and stage `AGENTS.md` below. Do not touch `CLAUDE.md` or `.claude/`.

- [ ] **Step 4: Update the audit doc**

In `docs/superpowers/results/v187/2026-10-23-repo-audit-findings.md`:

- status table: the row `| next: book integrity + partial-trade truth | A, B, F1 | not yet written |` becomes `| **v189** book integrity + partial-trade truth | A, B, F1 (partly) | implemented (plan \`2026-10-23-v189-book-integrity-partial-truth\`) |`.
- on a new paragraph directly after the F1 line, add:

```markdown
*v189:* `retrospective._r_multiple` is gone and `performance.closed_r_multiple`
delegates to `metrics.r_multiple`, so one trade-level R is left; leg sums go
through `metrics.leg_contribution_r`. Only the formulas inside code v189 edited
were migrated. The rest of the ~72 inline R/P&L formulas are left on purpose
(no correctness payoff this spec could measure); a later refactor finds them
with `git grep -n "entry - stop\|stop_loss - entry\|/ risk"`.
```

- immediately before the heading `## B. Partial trades on screen` (the end of section A), add:

```markdown
*v189 fixed these forward only.* The 23 production records counted on
2026-10-23 (2 multi-leg `win` with net R < 0, 10 multi-leg `closed` with net
R > 0, 10 plans missing the manual runner leg, 1 reversal settled on a
never-filled placeholder) were not backfilled. The metric-definitions spec
owns that decision (backfill through a data migration, or state why the mixed
labelling is acceptable).
```

- [ ] **Step 5: Commit**

```bash
cd "$WT" && git add docs/claude/known-traps.md docs/superpowers/results/v187/2026-10-23-repo-audit-findings.md && git commit -m "docs(traps): v189 plan-write guard, one-transaction closes, delete and reset rules; audit doc records what v189 left"
```

(Add `AGENTS.md` to the `git add` only if Step 3 changed it.)

### Task V189-27: Label-basis date, full suite, complexity gate, merge

**Model:** sonnet — one constant and its pinning test, then the plan's single full-suite run, the gate and a merge on a shared `main`; judgement only in reading the run and checking for concurrent work.

**Spec:** D6 (`metrics.LABEL_BASIS_SINCE` records the deploy date, set in the release task); § Testing (the full suite runs once, as the plan's final task); `Panel:` line (staff-engineer, quant-engineer, risk-manager); index clarification 9 (the date is the merge date; if the deploy slips past it, the controller amends it in the deploy commit).

**Files:**
- Modify: `swingbot/core/analytics/metrics.py` (`LABEL_BASIS_SINCE`, added by V189-2)
- Modify: `tests/analytics/test_net_outcome.py` (`test_constants`, created by V189-2)

**Interfaces:**
- Consumes: `metrics.LABEL_BASIS_SINCE: str | None = None` (V189-2); `tests/analytics/test_net_outcome.py::test_constants` (`assert metrics.LABEL_BASIS_SINCE is None`, V189-2); the analytics payload reads the constant at request time (V189-20), so nothing else changes.
- Produces: `LABEL_BASIS_SINCE = "<YYYY-MM-DD>"` (UTC merge date); the branch merged on `main`.

- [ ] **Step 1: Every other task is committed**

```bash
cd "$WT" && git status --short && git log --oneline main..HEAD | wc -l
grep -n "^### Task" E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/plans/2026-10-23-v189-book-integrity-partial-truth_*.md | wc -l
```

Expected: a clean worktree; one commit (at least) per task V189-1..V189-26 on the branch; 27 task headings across the plan's parts. A missing task is implemented first, never skipped.

- [ ] **Step 2: Pin the label-basis date (failing test first)**

```bash
date -u +%F
```

Use that date (call it `<DATE>`) in both edits. In `tests/analytics/test_net_outcome.py`, `test_constants` becomes:

```python
def test_constants():
    assert metrics.SCRATCH_EPS_R == 0.01
    # v189 D6: scaled-out closes are labelled by net R from this date on;
    # earlier ones keep their TP1-touch label (no backfill).
    assert metrics.LABEL_BASIS_SINCE == "<DATE>"
    assert date.fromisoformat(metrics.LABEL_BASIS_SINCE).isoformat() == metrics.LABEL_BASIS_SINCE
```

(add `from datetime import date` to the file's imports if it is not there).

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_net_outcome.py
```

Expected: FAIL on `test_constants` (`None == "<DATE>"`).

In `swingbot/core/analytics/metrics.py` set `LABEL_BASIS_SINCE: str | None = "<DATE>"` and keep its comment, adding: `Set at release (v189 V189-27) to the UTC merge date; the deploy follows the merge. If the deploy slips past it, amend it in the deploy commit.`

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_net_outcome.py
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_analytics_label_basis.py
cd "$WT" && git grep -n "LABEL_BASIS_SINCE is None\|label_basis_since\"\] is None" -- tests frontend/src
```

Expected: both files PASS; the grep prints nothing (V189-20's payload tests compare against the constant, not against `None`).

```bash
cd "$WT" && git add swingbot/core/analytics/metrics.py tests/analytics/test_net_outcome.py && git commit -m "chore(metrics): LABEL_BASIS_SINCE is the v189 release date (D6)"
```

- [ ] **Step 3: The plan's one full-suite run**

If `/replicate-prod-db` has not run in this session, run it first (every test uses the autouse Postgres fixture). Then dispatch the `test-runner` subagent in the worktree with:

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed` and `0 xfailed`. The complexity gate runs inside `full`. A changed pass count is not a failure (`docs/claude/testing-cost.md`).

Then the frontend, once, in the same worktree:

```bash
cd "$WT/frontend" && npx ng test --watch=false && npm run lint && npm run build
```

Expected: `0 failed`, lint clean, the production build succeeds.

A failure is fixed in the task it belongs to (a scoped `fix:` commit) and re-run alone with `python scripts/dev/testrun.py file <test>` or `npx ng test --watch=false --include <spec>`. The full suite is **not** re-run for it.

- [ ] **Step 4: The complexity gate on its own**

Run: `cd "$WT" && python scripts/dev/complexity_gate.py`
Expected: PASS. Watched baselines (may only shrink): `PlanManager._on_event` 15, `PlanManager.poll` 20, `PlanManager._step_active` 21, `api_v1.trades._row_from_plan` 15 (V189-18 takes it to 14), `api_v1.trades.list_trades` 34, `scan_run._sync_run_scan` 96 (strictly lower after V189-12).

If the gate reports a function **below** its baseline, lock the gain in with `python scripts/dev/complexity_gate.py --update` and commit it: `git add scripts/dev/complexity_baseline.json && git commit -m "chore(complexity): lock in v189 gains"`. A function **above** baseline is a defect in its task: fix it there.

- [ ] **Step 5: Merge to `main`**

Follow the `worktree-lifecycle` skill: another session may be on `main`. From the main tree:

```bash
git -C "E:/Documents/Private/Projects/Discord-Bot" status --short
git -C "E:/Documents/Private/Projects/Discord-Bot" merge --no-ff 2026-10-23-v189-book-integrity-partial-truth -m "Merge v189: book integrity and partial-trade truth (one R, net-R labels, locked plan writes, archived reset, partial trades on screen)"
git -C "E:/Documents/Private/Projects/Discord-Bot" log --oneline -3
```

Expected: a clean `main` before the merge (other sessions' uncommitted work is theirs: stop and ask if it touches a file this branch changed), then the merge commit at the top. No full suite after the merge (CLAUDE.md: it ran once, before the merge). If the merge happens on a later UTC day than `<DATE>`, amend `LABEL_BASIS_SINCE` and `test_constants` to the merge day in one `chore(metrics)` commit on `main` and run `python scripts/dev/testrun.py file tests/analytics/test_net_outcome.py`.

- [ ] **Step 6: Panel, then close-out**

On `main`, run `/panel staff-engineer,quant-engineer,risk-manager` over the merged diff (the spec's `Panel:` line), and apply or record its findings. Then run `/close-out` yourself (standing permission). It resolves the **bot patch, ui patch** bump in `VERSION.json`, regenerates `version_history.json`, moves the spec and every plan file of v189 (`_0-index`, `_1` … `_7b`) to `implemented/`, and removes the worktree.

Deployment is outside this plan (index Global Constraints: nothing is deployed here). Put these three deploy notes in the close-out summary, word for word:

1. **Deploy on the label-basis date.** `metrics.LABEL_BASIS_SINCE` is `<DATE>`; if the deploy lands on a later day, amend the constant (and `test_constants`) to the deploy day in the deploy commit (index clarification 9).
2. **Re-sync the slash commands after the deploy.** `/trades-clear-history` gains a `force` option (V189-16), so Discord's global command set changes. `on_ready` syncs once per process start, and a rejected sync is only a WARNING: follow `docs/deploy/DEPLOY_HETZNER.md` § "After every deploy or rollback: check the slash-command sync" — check the log with `bash scripts/ops/ssh-hetzner.sh "grep -i 'slash' /opt/swing-bot/logs/*.log | tail -5"`, and if the sync failed run `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/ops/resync_slash_commands.py"`. Clients may list the old option set for up to an hour.
3. **Rollback.** A plain redeploy of the previous image is safe: there is no schema change. A reset made after the deploy is undone with `scripts/ops/restore_account_reset.py <archive>` (dry run first, `--apply` to write; `DEPLOY_HETZNER.md` § PostgreSQL), and the previous image's SPA still reads `removed` from both clear replies.

