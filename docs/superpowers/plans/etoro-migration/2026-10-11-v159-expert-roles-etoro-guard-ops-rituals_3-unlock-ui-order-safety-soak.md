# v159 Four expert seats, a demo-only eToro guard, and the ops/UI rituals. Part 3: unlock UI, order safety, reconciler (ER10–ER12)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task ER11" -A 320 <this file>`.

**Spec:** `docs/superpowers/specs/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals-design.md` (§ B2 "Admin UI unlock path", § B3, § B4). ER13–ER14 (§ C1) are in part 3b, `_3b-soak.md`, split for the 1500-line cap.
**Index:** `docs/superpowers/plans/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_0-index.md`. Its `## Global Constraints`, `## Parallelisation` and `## Task ledger` apply to every task below and win over anything here.

**Conventions for every task in this part** (same as part 2)

- `WT` is the worktree root: `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals` (created in ER1). Every path below is relative to `WT`. Never `cd`: use `git -C "$WT" ...`; run Python tests as `python "$WT/scripts/dev/testrun.py" file <test path relative to WT>` and frontend specs as `npm --prefix "$WT/frontend" test -- --include <spec path relative to frontend/> --watch=false`.
- Hook-rule test code that names a protected branch uses `stable-1.9`, and is written through Edit/Write, never a Bash heredoc.
- Skill and agent tasks: write the source under `.claude/`, then `python "$WT/scripts/dev/sync_codex.py"`, and stage **only** the generated files of the skill or agent the task created or edited (`git -C "$WT" add .agents/skills/<name>` / `.codex/agents/<name>.toml`), never `git add -A .agents`.
- Every new or changed Python function stays below cyclomatic complexity 15: `python -m radon cc -s -n C <files>` prints nothing for the files a task changed.
- Never run the skill eval suites (they cost real money); a task only creates the eval case directories.

# Phase B — eToro demo-only guard (continued: ER10–ER12)

### Task ER10: Typed-date confirm before `ETORO_ALLOW_REAL` turns on

**Model:** sonnet — one new standalone Angular component and a three-method hook into an existing form; the only trap (the `<dialog>` close event firing a cancel after a confirm) is spelled out below.

Spec § B2 "Admin UI unlock path": ticking `ETORO_ALLOW_REAL` on the admin Settings page opens a confirm step that shows "Real money; stage 3; see roadmap" and makes the partner **type** the sign-off date. `sb-confirm-dialog` has no input slot (index Global Constraints), so this is a new component beside the Settings tab; `frontend/src/app/ui/confirm-dialog.ts` is not modified. The SPA check mirrors `guard.signoff_valid` for the partner's sake only: ER9's server rule (`_real_money_problem`, HTTP 400 `real_money_signoff` on preview, save and import) is the real lock, and its message reaches the form through the existing `store.formError()` / `.form-error` path, which this task tests.

Flow, so no state can save the flag without the typed date:
- Ticking the box (server value not already `true`) writes `ETORO_ALLOW_REAL: true` into the draft **and** opens the dialog. The dialog is modal (`showModal()`), so the save bar is inert behind it.
- **Unlock** writes the typed date into the `ETORO_REAL_SIGNOFF` draft and closes the dialog.
- **Cancel**, Escape or any other close puts the flag back (`store.edit(flag, false)`, which drops the draft key when the server value is `false`), so the checkbox repaints unchecked.
- Unticking, or ticking a box the server already reports `true`, opens nothing.

Trap: closing a `<dialog>` fires its `close` event, and the parent closes the dialog right after **Unlock** by setting `open` false. Without a guard that `close` event would emit `cancelled` and undo the unlock. The component remembers that it just confirmed and swallows that one `close`.

**Files:**
- Create: `frontend/src/app/workspaces/system/real-money-unlock-dialog.ts`
- Create: `frontend/src/app/workspaces/system/real-money-unlock-dialog.spec.ts`
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts` (imports l.1-11, `imports:` l.29, the `@case ('checkbox')` block ~l.128-134, after the `<sb-confirm-dialog>` ~l.311-318, class body after `confirmDiscard` ~l.632 and after `discardDraft` ~l.660)
- Modify: `frontend/src/app/workspaces/system/settings-tab.spec.ts` (imports; append a `describe`)

**Interfaces:**
- Consumes (ER9): the server's HTTP 400 `{"error": {"code": "real_money_signoff", "message": ...}}` on `POST /api/v1/system/settings/preview` and `PUT /api/v1/system/settings`. Existing: `SystemStore.edit(field, value)`, `.fields()`, `.draft()`, `.formError()`, `.previewChanges()`; `SettingField` (`frontend/src/app/api/models.ts:899`); `Button`, `FocusTrap`, `TextInput`, `ControlRow`; `installDialogPolyfill` (`frontend/src/app/testing/dialog-polyfill.ts`).
- Produces: `isValidSignoff(value: string, today: string): boolean`; `berlinToday(now?: Date): string` (YYYY-MM-DD in Europe/Berlin); component `RealMoneyUnlockDialog`, selector `sb-real-money-unlock-dialog`, inputs `open: boolean`, `today: string`, outputs `unlocked: string` (the typed date, trimmed), `cancelled: void`; the copy `Real money; stage 3; see roadmap`. No later task consumes these.

- [ ] **Step 0: Frontend dependencies in the worktree**

A fresh worktree has no `frontend/node_modules`. If `ls "$WT/frontend/node_modules/.bin" >/dev/null 2>&1` fails, run:

```bash
npm --prefix "$WT/frontend" ci
```

Expected: exits 0. (`node_modules/` is gitignored; nothing to stage.)

- [ ] **Step 1: Write the failing dialog spec**

Create `frontend/src/app/workspaces/system/real-money-unlock-dialog.spec.ts`:

```ts
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { RealMoneyUnlockDialog, berlinToday, isValidSignoff } from './real-money-unlock-dialog';

/* v159 ER10 -- the stage-3 lock's typed-date confirm. The server re-checks
 * the same rule (system.py _real_money_problem); this spec pins the SPA half. */

describe('isValidSignoff', () => {
  const today = '2026-10-11';

  it.each([
    ['2026-10-11', true],     // today itself
    ['2026-01-01', true],
    [' 2026-01-01 ', true],   // trimmed, as the server strips
    ['2026-10-12', false],    // future
    ['2026-13-01', false],    // no such month
    ['2026-02-30', false],    // no such day
    ['2026-1-01', false],     // not ISO
    ['soon', false],
    ['', false],
  ])('%s -> %s', (value, expected) => {
    expect(isValidSignoff(value, today)).toBe(expected);
  });

  it('refuses everything when today itself is not an ISO date', () => {
    expect(isValidSignoff('2026-01-01', '')).toBe(false);
  });
});

describe('berlinToday', () => {
  it('rolls over at Berlin midnight, not UTC midnight', () => {
    // 22:30 UTC in October is 00:30 CEST the next day.
    expect(berlinToday(new Date('2026-10-10T22:30:00Z'))).toBe('2026-10-11');
    // 23:30 UTC on New Year's Eve is 00:30 CET on 1 January.
    expect(berlinToday(new Date('2026-12-31T23:30:00Z'))).toBe('2027-01-01');
    expect(berlinToday(new Date('2026-10-11T08:00:00Z'))).toBe('2026-10-11');
  });
});

@Component({
  imports: [RealMoneyUnlockDialog],
  template: `
    <sb-real-money-unlock-dialog
      [open]="open()"
      today="2026-10-11"
      (unlocked)="onUnlocked($event)"
      (cancelled)="onCancelled()"
    />
  `,
})
class Host {
  readonly open = signal(false);
  readonly unlockedWith: string[] = [];
  cancelled = 0;

  onUnlocked(date: string): void {
    this.unlockedWith.push(date);
    this.open.set(false);   // what SettingsTab does
  }

  onCancelled(): void {
    this.cancelled += 1;
    this.open.set(false);
  }
}

describe('RealMoneyUnlockDialog', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    installDialogPolyfill();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const el = (): HTMLElement => fixture.nativeElement;
  const dialog = () => el().querySelector('dialog') as HTMLDialogElement;
  const button = (text: string) =>
    [...el().querySelectorAll('button')].find((b) => b.textContent!.includes(text)) as HTMLButtonElement;

  function openIt(): void {
    host.open.set(true);
    fixture.detectChanges();
  }

  function type(value: string): void {
    const input = el().querySelector('dialog input') as HTMLInputElement;
    input.value = value;
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  it('names real money, stage 3 and the roadmap', () => {
    openIt();
    expect(dialog().hasAttribute('open')).toBe(true);
    expect(el().textContent).toContain('Real money; stage 3; see roadmap');
  });

  it('keeps Unlock disabled until a date no later than today is typed', () => {
    openIt();
    expect(button('Unlock real money').disabled).toBe(true);
    type('2026-10-12');
    expect(button('Unlock real money').disabled).toBe(true);
    type('2026-10-11');
    expect(button('Unlock real money').disabled).toBe(false);
  });

  it('emits the typed date once, and no cancel, when unlocked', () => {
    openIt();
    type(' 2026-10-01 ');
    button('Unlock real money').click();
    fixture.detectChanges();   // host closes it; the close event must not cancel
    expect(host.unlockedWith).toEqual(['2026-10-01']);
    expect(host.cancelled).toBe(0);
    expect(dialog().hasAttribute('open')).toBe(false);
  });

  it('emits cancelled and no date on Cancel', () => {
    openIt();
    type('2026-10-01');
    button('Cancel').click();
    fixture.detectChanges();
    expect(host.cancelled).toBe(1);
    expect(host.unlockedWith).toEqual([]);
  });

  it('starts empty every time it opens', () => {
    openIt();
    type('2026-10-01');
    button('Cancel').click();
    fixture.detectChanges();
    openIt();
    expect((el().querySelector('dialog input') as HTMLInputElement).value).toBe('');
    expect(button('Unlock real money').disabled).toBe(true);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix "$WT/frontend" test -- --include src/app/workspaces/system/real-money-unlock-dialog.spec.ts --watch=false`
Expected: FAIL — the build cannot resolve `./real-money-unlock-dialog`. (A "Timeout waiting for worker to respond" before any test runs is the known load flake, `docs/claude/testing-cost.md` § Frontend: re-run.)

- [ ] **Step 3: Write the component**

Create `frontend/src/app/workspaces/system/real-money-unlock-dialog.ts`:

```ts
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';

import { Button } from '../../ui/button';
import { FocusTrap } from '../../ui/focus-trap';
import { TextInput } from '../../ui/form-controls';
import { ControlRow } from '../../ui/layout';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * v159 -- an ISO date (YYYY-MM-DD) that exists on the calendar and is no
 * later than `today` (YYYY-MM-DD, Europe/Berlin). Mirrors
 * `swingbot/core/broker/guard.py:signoff_valid`. The SPA check is for the
 * partner's sake only; the server refuses the save on its own
 * (`swingbot/admin/api_v1/system.py:_real_money_problem`).
 */
export function isValidSignoff(value: string, today: string): boolean {
  const text = value.trim();
  if (!ISO_DATE.test(text) || !ISO_DATE.test(today)) return false;
  const [year, month, day] = text.split('-').map(Number);
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);   // setUTCFullYear: no 19xx remap of years < 100
  const exists =
    year >= 1 &&
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day;
  return exists && text <= today;
}

/** Today in Europe/Berlin as YYYY-MM-DD, the zone the server's check uses. */
export function berlinToday(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Berlin',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const part = (type: string): string => parts.find((p) => p.type === type)?.value ?? '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}

/**
 * The confirm step in front of the stage-3 real-money unlock
 * (`ETORO_ALLOW_REAL`, docs/claude/etoro-roadmap.md).
 *
 * Not `sb-confirm-dialog`: that one has no input, and the point here is that
 * the partner TYPES the sign-off date rather than clicking through. Built on
 * `<dialog>` for the same reasons ConfirmDialog is (top layer, backdrop,
 * Escape, inert background).
 */
@Component({
  selector: 'sb-real-money-unlock-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, ControlRow, FocusTrap, TextInput],
  template: `
    <dialog #dialog class="elev-overlay" (close)="onClose()">
      @if (open()) {
        <div sbFocusTrap>
          <h2>Turn on real money?</h2>
          <p class="consequence">
            Real money; stage 3; see roadmap (docs/claude/etoro-roadmap.md).
            This lifts the demo-only lock on the eToro account. Type the
            sign-off date to confirm.
          </p>
          <sb-text-input
            class="signoff"
            label="Sign-off date (YYYY-MM-DD)"
            placeholder="YYYY-MM-DD"
            [(value)]="typed"
          />
          <p class="hint">An ISO date no later than today ({{ today() }}, Europe/Berlin).</p>

          <sb-control-row class="actions">
            <button sb-button variant="ghost" type="button" (click)="close()">Cancel</button>
            <button sb-button variant="danger" type="button" [disabled]="!valid()" (click)="confirm()">
              Unlock real money
            </button>
          </sb-control-row>
        </div>
      }
    </dialog>
  `,
  styles: `
    :host { display: contents; }
    dialog {
      max-width: 420px;
      padding: var(--space-20);
      color: var(--text);
    }
    dialog::backdrop { background: var(--scrim); }
    [sbFocusTrap] { display: contents; }
    h2 { font-size: var(--text-subhead); font-weight: 600; }
    .consequence {
      margin-top: var(--space-8);
      color: var(--text-secondary);
      font-size: var(--text-body);
      line-height: 1.5;
    }
    .signoff { display: flex; margin-top: var(--space-14); }
    .hint {
      margin-top: var(--space-4);
      color: var(--text-muted);
      font-size: var(--text-table);
    }
    .actions {
      display: flex;
      justify-content: flex-end;
      margin-top: var(--space-20);
    }
  `,
})
export class RealMoneyUnlockDialog {
  readonly open = input(false);
  /** YYYY-MM-DD, Europe/Berlin -- passed in so a test can pin it. */
  readonly today = input('');

  readonly unlocked = output<string>();
  readonly cancelled = output<void>();

  protected readonly typed = signal('');
  protected readonly valid = computed(() => isValidSignoff(this.typed(), this.today()));

  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  /** Set by confirm(): the parent closes the dialog right after `unlocked`,
   *  and that close event must not be reported as a cancel. */
  private confirming = false;

  constructor() {
    effect(() => {
      const element = this.dialog().nativeElement;
      if (this.open() && !element.open) {
        this.typed.set('');
        element.showModal();
      } else if (!this.open() && element.open) {
        element.close();
      }
    });
  }

  protected confirm(): void {
    if (!this.valid()) return;
    this.confirming = true;
    this.unlocked.emit(this.typed().trim());
  }

  protected close(): void {
    // Cancel and Escape both end in the dialog's own close event.
    this.dialog().nativeElement.close();
  }

  protected onClose(): void {
    if (this.confirming) {
      this.confirming = false;
      return;
    }
    this.cancelled.emit();
  }
}
```

- [ ] **Step 4: Run the dialog spec to verify it passes**

Run: `npm --prefix "$WT/frontend" test -- --include src/app/workspaces/system/real-money-unlock-dialog.spec.ts --watch=false`
Expected: PASS, all tests.

- [ ] **Step 5: Write the failing Settings-tab tests**

In `frontend/src/app/workspaces/system/settings-tab.spec.ts`, change the models import to `import { SettingField, Settings } from '../../api/models';` and add after the `SystemStore` import:

```ts
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
```

Append at the end of the file:

```ts
/* -- v159 ER10 -- the real-money unlock needs a typed sign-off date --------- */

function lockField(key: string, type: string, value: unknown, label: string): SettingField {
  return {
    key, label, type, value,
    default: type === 'checkbox' ? 'false' : '',
    help: '', min: null, max: null, step: null, options: [],
    sensitive: false, hot_reloadable: true,
  };
}

function etoroPayload(unlocked: boolean): Settings {
  return payload({
    sections: [{
      name: 'eToro Paper Trading',
      icon: '',
      description: '',
      fields: [
        lockField('ETORO_ALLOW_REAL', 'checkbox', unlocked, 'Allow real money (stage 3)'),
        lockField('ETORO_REAL_SIGNOFF', 'text', unlocked ? '2026-01-01' : '', 'Real-money sign-off date'),
      ],
    }],
  });
}

describe('SettingsTab real-money unlock', () => {
  async function seedEtoro(unlocked = false) {
    installDialogPolyfill();
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/system/settings').flush(etoroPayload(unlocked));
    await fixture.whenStable();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const store = TestBed.inject(SystemStore);
    const box = () =>
      [...el.querySelectorAll('sb-checkbox')]
        .find((c) => c.textContent!.includes('Allow real money'))!
        .querySelector('input') as HTMLInputElement;
    const tick = (checked: boolean) => {
      box().checked = checked;
      box().dispatchEvent(new Event('change'));
      fixture.detectChanges();
    };
    const unlockDialog = () =>
      el.querySelector('sb-real-money-unlock-dialog dialog') as HTMLDialogElement;
    const button = (text: string) =>
      [...el.querySelectorAll('sb-real-money-unlock-dialog button')]
        .find((b) => b.textContent!.includes(text)) as HTMLButtonElement;
    const type = (value: string) => {
      const input = el.querySelector('sb-real-money-unlock-dialog input') as HTMLInputElement;
      input.value = value;
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
    };
    return { fixture, backend, el, store, box, tick, unlockDialog, button, type };
  }

  it('ticking the flag opens the typed-date confirm', async () => {
    const { el, tick, unlockDialog } = await seedEtoro();
    tick(true);
    expect(unlockDialog().hasAttribute('open')).toBe(true);
    expect(el.textContent).toContain('Real money; stage 3; see roadmap');
  });

  it('Unlock puts the flag and the typed date in the draft together', async () => {
    const { fixture, store, tick, type, button, unlockDialog } = await seedEtoro();
    tick(true);
    type('2026-01-01');
    button('Unlock real money').click();
    fixture.detectChanges();
    expect(store.draft()).toEqual({ ETORO_ALLOW_REAL: true, ETORO_REAL_SIGNOFF: '2026-01-01' });
    expect(unlockDialog().hasAttribute('open')).toBe(false);
  });

  it('Cancel puts the flag back and repaints the box unchecked', async () => {
    const { fixture, store, tick, button, box } = await seedEtoro();
    tick(true);
    button('Cancel').click();
    fixture.detectChanges();
    expect(store.draft()).toEqual({});
    expect(box().checked).toBe(false);
  });

  it('turning real money off asks nothing', async () => {
    const { store, tick, unlockDialog } = await seedEtoro(true);
    tick(false);
    expect(unlockDialog().hasAttribute('open')).toBe(false);
    expect(store.draft()).toEqual({ ETORO_ALLOW_REAL: false });
  });

  it("shows the server's real_money_signoff refusal", async () => {
    const { fixture, backend, el, store, tick, type, button } = await seedEtoro();
    tick(true);
    type('2026-01-01');
    button('Unlock real money').click();
    fixture.detectChanges();
    store.previewChanges();
    backend.expectOne('/api/v1/system/settings/preview').flush(
      { error: { code: 'real_money_signoff', message: 'Real money is stage 3 (docs/claude/etoro-roadmap.md).' } },
      { status: 400, statusText: 'Bad Request' },
    );
    await fixture.whenStable();
    fixture.detectChanges();
    expect(el.querySelector('.form-error')!.textContent).toContain('Real money is stage 3');
  });
});
```

Run: `npm --prefix "$WT/frontend" test -- --include src/app/workspaces/system/settings-tab.spec.ts --watch=false`
Expected: FAIL — the new tests that query `sb-real-money-unlock-dialog` (it is not in the tab yet, so `unlockDialog()` and `button(...)` are `null`). The pre-existing tests still pass.

- [ ] **Step 6: Wire the dialog into the Settings tab**

In `frontend/src/app/workspaces/system/settings-tab.ts`:

6a. Add after `import { controlOf, groupByControl, settingsCategories } from './settings-grouping';`:

```ts
import { RealMoneyUnlockDialog, berlinToday } from './real-money-unlock-dialog';

/** v159: the stage-3 real-money lock (docs/claude/etoro-roadmap.md). Ticking
 *  the flag opens the typed-date confirm; the server refuses a save without a
 *  valid sign-off either way (system.py `_real_money_problem`). */
const REAL_MONEY_KEY = 'ETORO_ALLOW_REAL';
const SIGNOFF_KEY = 'ETORO_REAL_SIGNOFF';
```

6b. The component `imports:` line becomes:

```ts
  imports: [Panel, Button, TextInput, Select, Checkbox, ControlRow, ConfirmDialog, RealMoneyUnlockDialog, Async],
```

6c. In the `@case ('checkbox')` block, change only the output binding:

```html
                    (checkedChange)="onCheckbox(field, $event)"
```

6d. Directly after the closing `/>` of the existing `<sb-confirm-dialog ... (cancelled)="confirmDiscard.set(false)"` element, add:

```html

    <sb-real-money-unlock-dialog
      [open]="unlockOpen()"
      [today]="unlockToday()"
      (unlocked)="confirmUnlock($event)"
      (cancelled)="cancelUnlock()"
    />
```

6e. In the class, after `protected readonly confirmDiscard = signal(false);`:

```ts
  /** v159 -- the real-money confirm is open; `unlockToday` is fixed when it
   *  opens, so the rule cannot move under the partner while they type. */
  protected readonly unlockOpen = signal(false);
  protected readonly unlockToday = signal('');
```

6f. In the class, after the `discardDraft()` method:

```ts
  /** Every checkbox edits the draft. The real-money flag also opens the
   *  typed-date confirm when it goes from off to on; the dialog is modal, so
   *  nothing can be saved until it is answered. */
  protected onCheckbox(field: SettingField, checked: boolean): void {
    this.store.edit(field, checked);
    if (field.key === REAL_MONEY_KEY && checked && field.value !== true) {
      this.unlockToday.set(berlinToday());
      this.unlockOpen.set(true);
    }
  }

  protected confirmUnlock(date: string): void {
    const signoff = this.store.fields().find((f) => f.key === SIGNOFF_KEY);
    if (signoff) this.store.edit(signoff, date);
    this.unlockOpen.set(false);
  }

  /** Cancel, Escape or any close without Unlock: the flag goes back. */
  protected cancelUnlock(): void {
    if (!this.unlockOpen()) return;
    const flag = this.store.fields().find((f) => f.key === REAL_MONEY_KEY);
    if (flag) this.store.edit(flag, false);
    this.unlockOpen.set(false);
  }
```

`cancelUnlock` returns early when the dialog is already closed, so the `close` event that follows a confirmed unlock (if one ever reached it) cannot undo the flag.

- [ ] **Step 7: Run both specs, the whole frontend suite and the build**

Run: `npm --prefix "$WT/frontend" test -- --include src/app/workspaces/system/settings-tab.spec.ts --watch=false`
Expected: PASS, every test.

Run: `npm --prefix "$WT/frontend" test -- --include src/app/workspaces/system/real-money-unlock-dialog.spec.ts --watch=false`
Expected: PASS.

Run: `npm --prefix "$WT/frontend" test -- --watch=false`
Expected: PASS. This covers the convention specs (`ui/spacing.spec.ts`, `ui/contrast.spec.ts`, `workspaces/workspace-gaps.spec.ts`), which scan component sources. If a convention spec flags the new file (for example a spacing value off the token scale), change the style in `real-money-unlock-dialog.ts` to the token it asks for; never loosen the convention spec.

Run: `npm --prefix "$WT/frontend" run build`
Expected: exits 0 (the AOT template type-check covers the new bindings).

- [ ] **Step 8: Commit**

`dist/` and `node_modules/` are gitignored; stage only these four files.

```bash
git -C "$WT" add frontend/src/app/workspaces/system/real-money-unlock-dialog.ts frontend/src/app/workspaces/system/real-money-unlock-dialog.spec.ts frontend/src/app/workspaces/system/settings-tab.ts frontend/src/app/workspaces/system/settings-tab.spec.ts
git -C "$WT" commit -m "feat(v159): ER10 -- typed-date confirm before real money turns on

Ticking ETORO_ALLOW_REAL on the Settings page opens a modal that reads
'Real money; stage 3; see roadmap' and unlocks only once the partner types
an ISO sign-off date no later than today (Europe/Berlin). Cancel or Escape
puts the flag back. The server's real_money_signoff refusal (ER9) shows in
the form error. sb-confirm-dialog is unchanged.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task ER11: `order-safety` skill, stage renumber in `CLAUDE.md`, roadmap open items

**Model:** sonnet — a model-invocable skill in the v96 shape plus three doc edits with exact text; the line budget on `CLAUDE.md` is the one thing to measure.

Spec § B3 (the skill and its eight-step checklist), § "Codex mirror" (the `CLAUDE.md` eToro section: "Stage 1 (near)"/"Stage 2 (far)" become "Stage 2 (near)"/"Stage 3 (far)", plus "`broker/guard.py:assert_demo` guards every eToro call; `order-safety` fires first") and § "Open roadmap items" (two entries in `etoro-roadmap.md`). `CLAUDE.md` is 199 lines after ER1 and must stay ≤ 199: the eToro section is rewritten **in place, six lines for six lines**.

The skill is Tier 1 (an integrity gate: it blocks a real-money or unchecked order), so it is model-invocable with a `## Trigger table`, and it must **not** contain `\n## Lens\n` (that would make it a role). It names v160's `broker/sizing.py` and `broker/pre_open.py` as the only way to build an order; neither exists after this plan, so step 4 says to stop when they are missing (index Global Constraints: order-risk checks are v160's).

**Files:**
- Create: `.claude/skills/order-safety/SKILL.md`
- Create: `.claude/skills/order-safety/evals/fire-demo-order/prompt.md`, `.claude/skills/order-safety/evals/fire-demo-order/graders/skill-fired.md`
- Create: `.claude/skills/order-safety/evals/no-fire-paper-journal/prompt.md`, `.claude/skills/order-safety/evals/no-fire-paper-journal/graders/skill-fired.md`
- Modify: `tests/hooks/test_skill_shape.py` (`TIER_1_AND_3`; two tests appended)
- Modify: `docs/claude/skills-tools.md` (skill-tier table after the `worktree-lifecycle` row, ~l.103; the Tier 1 sentence ~l.120)
- Modify: `CLAUDE.md` (§ "eToro roadmap: demo next, real money much later", l.27-32)
- Modify: `AGENTS.md` (the `**eToro roadmap:**` paragraph ~l.69-76; the situation table row after `etoro-public-api-operations` ~l.248)
- Modify: `docs/claude/etoro-roadmap.md` (one `Rules` bullet; new `## Open items` section at the end)
- Generated: `.agents/skills/order-safety/SKILL.md` (by `sync_codex.py`)

**Interfaces:**
- Consumes (ER7): `swingbot/core/broker/guard.py:assert_demo` (named, not called); (ER6) `_rule_etoro_real_account` (named). Existing: `test_skill_shape._read_skill`, `TIER_1_AND_3`, `_REPO_ROOT`, `re`.
- Produces: skill `order-safety` (Tier 1, model-invocable, steps numbered `1.`–`8.`); `etoro-roadmap.md` `## Open items` with entries `1.` (CFD vs real shares) and `2.` (stage-3 criteria). ER12's `reconciler` names `order-safety` in its body.

- [ ] **Step 1: Write the failing tests**

In `tests/hooks/test_skill_shape.py`, add `"order-safety"` to `TIER_1_AND_3` (append it to the last line of the set, before the closing brace):

```python
                "staff-engineer", "quant-engineer", "senior-engineer",
                "order-safety"}   # each skill task appends its own name
```

(Keep any names ER1/ER2 appended on that line; only add `"order-safety"`.)

Append at the end of the file:

```python
# --- v159: order-safety, and the stage numbering it relies on ---------------

def test_order_safety_carries_the_eight_steps_and_names_the_guard():
    meta, body = _read_skill("order-safety")
    for phrase in ("assert_demo", "_rule_etoro_real_account", "broker/sizing.py",
                   "broker/pre_open.py", "etoro-public-api-operations",
                   "idempotency key", "CFD", "only ever tightens",
                   "explicit partner approval", "`cap`"):
        assert phrase in body, phrase
    assert re.findall(r"^(\d)\. ", body, re.MULTILINE) == [str(n) for n in range(1, 9)]
    assert "\n## Lens\n" not in body, "a Lens section would make it a role"
    assert "Not for" in meta["description"]


def test_real_money_is_stage_three_everywhere():
    root = _REPO_ROOT
    claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Stage 2 (near)" in claude and "Stage 3 (far)" in claude
    assert "Stage 1 (near)" not in claude
    assert "broker/guard.py:assert_demo" in claude and "`order-safety`" in claude
    assert len(claude.splitlines()) <= 199
    roadmap = (root / "docs" / "claude" / "etoro-roadmap.md").read_text(encoding="utf-8")
    section = roadmap.split("## Open items", 1)[1]
    assert "1. **CFD vs real shares" in section
    assert "2. **The stage-3 unlock criteria" in section
```

`_REPO_ROOT` (l.13) and `re` (l.8) already exist in this file.

- [ ] **Step 2: Run them to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py`
Expected: FAIL — `test_model_invocable_skills_carry_a_trigger_table` and the new tests (`FileNotFoundError` on `.claude/skills/order-safety/SKILL.md`), and `test_every_skill_is_registered_in_exactly_one_tier`.

- [ ] **Step 3: Write the skill**

Create `.claude/skills/order-safety/SKILL.md`:

```markdown
---
name: order-safety
description: "Use before any eToro operation -- an MCP call, a script or code that talks to the eToro Public API, read or write. Demo only, one prepare-trade then place-trade per partner approval, stop and target attached at order time. Not for swingbot's own paper journal."
---

# Order safety

## Step 1 — Read the authority

Read `docs/claude/etoro-roadmap.md` whole (it is short), then load the
`etoro-public-api-operations` skill for the API itself: routes, tools and
request shapes. This skill restates neither; it is the order of operations.

## Step 2 — The checklist, in order, every time

1. **Demo account only, and say so** in the message before the call. In code,
   `swingbot/core/broker/guard.py:assert_demo` refuses any other account; in a
   session, the hook rule `_rule_etoro_real_account` denies it. Neither is a
   reason to skip saying it.
2. **One prepare-trade, then place-trade, per explicit partner approval**
   (`etoro-roadmap.md` § Rules). Never batch, and never place on an earlier
   approval.
3. **A read call first:** the portfolio, then the instrument by symbol. Record
   the instrument type (CFD or real share), its leverage and its overnight
   financing.
4. **Build the order through v160's `broker/sizing.py` and
   `broker/pre_open.py`.** A by-hand check of the 2% rule is never a
   substitute. If those modules do not exist yet, stop: no order is placed.
   Stop loss and take profit are attached at order time.
5. **Send with an idempotency key.**
6. **Write a journal entry for every order sent or rejected.** A rejection
   records the `cap` that refused it.
7. **Never retry a write blind:** read the order and portfolio state first.
8. **A stop only ever tightens.** Never move it away from price after entry.

## The gate

Before the write call, the message names: the account (`demo`), the partner
approval it acts on, the instrument type read in step 3, and the idempotency
key. A call without all four is not made.

## Known wrong turns

| Tempting | Reality |
|---|---|
| "The hook would block real, so the account check is done" | The hook only sees this session. Code paths go through `assert_demo`; say the account anyway. |
| "The partner approved this plan yesterday" | One approval, one trade. A new order needs a new approval. |
| "The 2% maths checks out by hand" | Sizing goes through `broker/sizing.py` and `broker/pre_open.py`, tested; prose is not a guard. |
| "The place call timed out, send it again" | Read state first; a blind retry can double the position. |
| "Widen the stop a little so it is not hit" | Stops only tighten (`execution-specialist` red flag). |

## Trigger table

Should fire: preparing, placing or closing a trade on the eToro demo account
through the eToro MCP server.
Should fire: writing or editing code or a script that calls an eToro Public
API trading route.
Should fire: reading the eToro portfolio before sending a plan's order.
Should not fire: closing a trade in swingbot's own paper journal, with no
eToro call.
Should not fire: changing the value of a risk or heat cap in config
(`risk-manager`).
Should not fire: looking up what an eToro route does without calling it
(`etoro-public-api-operations`).
```

- [ ] **Step 4: Write the two eval cases**

`.claude/skills/order-safety/evals/fire-demo-order/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Put today's AAPL plan on the eToro demo account: buy at the plan's entry with its stop and target.
```

`.claude/skills/order-safety/evals/fire-demo-order/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: order-safety
min: 1
---

The `order-safety` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

`.claude/skills/order-safety/evals/no-fire-paper-journal/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Close my paper trade on MSFT in the swingbot journal at today's close.
```

`.claude/skills/order-safety/evals/no-fire-paper-journal/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: order-safety
min: 0
max: 0
---

The `order-safety` skill must not load for this prompt: it is a should-not-fire row of that skill's trigger table.
```

- [ ] **Step 5: Renumber the stages in `CLAUDE.md`, in place**

Replace the six text lines under `## eToro roadmap: demo next, real money much later` (from `Stage 1 (near): issue trade plans` through `Detail: \`docs/claude/etoro-roadmap.md\`.`) with exactly these six lines:

```markdown
Stage 2 (near): issue trade plans to an **eToro demo account** via the Public API
alongside the bomeo-capital.com page. Stage 3 (far): real trades, only after
consecutive profitable months and better win rate / profit / loss. Until the
partner says otherwise: **demo only, never `account: real`**; `broker/guard.py:assert_demo`
guards every eToro call and `order-safety` fires first. Keys: `ETORO_USER_KEY`,
`ETORO_API_KEY` in `.env`. Skill: `etoro-public-api-operations`. Detail: `docs/claude/etoro-roadmap.md`.
```

Run: `wc -l "$WT/CLAUDE.md"`
Expected: `199` (unchanged by this task).

- [ ] **Step 6: `etoro-roadmap.md` — the guard in the rules, and the open items**

In the `Rules until stage 3 is explicitly unlocked:` list, add as its second bullet (after `- Always \`account: "demo"\`; ...`):

```markdown
- In code, `swingbot/core/broker/guard.py:assert_demo` refuses any account but
  `demo` unless `ETORO_ALLOW_REAL` is on **and** `ETORO_REAL_SIGNOFF` is an ISO
  date no later than today (Europe/Berlin). Only the partner sets them, on the
  admin Settings page (typed-date confirm) or by hand on the VM. In a session,
  the `order-safety` skill runs before any eToro operation.
```

Append at the end of the file:

```markdown

## Open items

Recorded by v159; answering them is the partner's call, in a later spec.

1. **CFD vs real shares decides whether demo evidence counts.** A CFD demo
   fill carries spread, overnight financing, leverage and the EU retail
   loss-disclosure regime; a real-share fill does not. Answer this **before**
   demo performance is used as a gate for stage 3, not in the stage-3 spec.
2. **The stage-3 unlock criteria are led by win rate** ("consecutive
   profitable months, better win rate"), with no minimum N, no drawdown bound
   and no cost or tax netting. The v159 panel suggests ExpR with a sample
   floor, a maximum drawdown in dollars, and results net of costs and tax;
   `quant-researcher` should judge the statistics. The `ETORO_REAL_SIGNOFF`
   date is a lock, not a performance test.
```

- [ ] **Step 7: Registries and the Codex mirror**

`docs/claude/skills-tools.md`, skill-tier table, after the `worktree-lifecycle` row:

```markdown
| `order-safety` | 1 | model-invocable | `etoro-roadmap.md` — Step 1 reads it whole |
```

In the Tier 1/Tier 3 paragraph below the table, change `Tier 1 blocks an integrity violation (backtest re-runs, lookahead, pooled numbers, unmirrored prod changes)` to:

```markdown
Tier 1 blocks an integrity violation (backtest re-runs, lookahead, pooled
numbers, unmirrored prod changes, an eToro order outside the demo-only
checklist)
```

`AGENTS.md`: replace the paragraph that starts `**eToro roadmap:** next, trade plans may be issued` and ends ``Detail:\n`docs/claude/etoro-roadmap.md`.`` with:

```markdown
**eToro roadmap** (stages in `docs/claude/etoro-roadmap.md`: 1 keys, done;
2 demo; 3 real): stage 2 issues trade plans to an eToro **demo** account via
the Public API alongside bomeo-capital.com; stage 3, real money, comes only
much later, after consecutive profitable months and better win
rate/profit/loss, and only when the partner says so. eToro stays the broker
for both stages (decided 2026-10-11; IBKR, Trading 212, Saxo, Alpaca compared
and not chosen). Until then demo only, never `account: real`:
`swingbot/core/broker/guard.py:assert_demo` guards every eToro call in code,
`order-safety` runs before any eToro operation, and only the partner unlocks
stage 3 (admin Settings page, typed sign-off date). Keys are `ETORO_USER_KEY` /
`ETORO_API_KEY` in `.env`. Detail: `docs/claude/etoro-roadmap.md`.
```

In the situation table, after the `etoro-public-api-operations` row, add:

```markdown
| Before any eToro operation -- an MCP call, a script or code on the Public API (demo only; one prepare then place per approval) | `order-safety` |
```

Then regenerate the Codex copy:

```bash
python "$WT/scripts/dev/sync_codex.py"
```

Expected: writes `.agents/skills/order-safety/SKILL.md` (no `agents/openai.yaml`: the skill is model-invocable). `git -C "$WT" status --short .agents` may also list unrelated skills; do not stage those.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py`
Expected: PASS (`order-safety` is backtick-mentioned in `AGENTS.md`; the generated copy is fresh).

Run: `wc -l "$WT/.claude/skills/order-safety/SKILL.md" "$WT/CLAUDE.md"`
Expected: the skill ≤ 80 lines; `CLAUDE.md` 199.

- [ ] **Step 9: Commit**

```bash
git -C "$WT" add .claude/skills/order-safety .agents/skills/order-safety tests/hooks/test_skill_shape.py docs/claude/skills-tools.md CLAUDE.md AGENTS.md docs/claude/etoro-roadmap.md
git -C "$WT" commit -m "feat(v159): ER11 -- order-safety skill; real money is stage 3

order-safety fires before any eToro operation: demo only, one prepare then
place per explicit approval, a read first (instrument type, leverage,
financing), orders built only through v160's broker/sizing.py and
broker/pre_open.py, idempotency key, a journal entry per order or
rejection, no blind retry, stops only tighten. CLAUDE.md renumbers the
eToro stages to the roadmap's 2 (demo) and 3 (real) and names assert_demo,
in place. etoro-roadmap.md records the two open items.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task ER12: `reconciler` agent contract

**Model:** haiku — one markdown agent file, two registry rows and a shape test, all with exact text below; no judgement left open.

Spec § B4. The `reconciler` compares the VM journal with the eToro **demo** portfolio and returns mismatches only. It is read-only and **dormant until stage 2** places demo orders: this task fixes its contract, nothing calls it yet. Tools are pinned to `Bash, Read, Grep` (ledger): Bash goes through `scripts/ops/ssh-hetzner.sh` for the VM journal, and the demo book comes either from a portfolio export the controller hands it or from a read-only demo route on the VM. Any path without `/demo/` is denied by ER6's hook rule anyway.

**Files:**
- Create: `.claude/agents/reconciler.md`
- Modify: `tests/hooks/test_agent_shape.py` (`EXPECTED` entry; one test appended)
- Modify: `docs/claude/skills-tools.md` (`## Which agent for what` table, after the `prod-inspector` row)
- Modify: `AGENTS.md` (the role-agents sentence ~l.396-397)
- Generated: `.codex/agents/reconciler.toml` (by `sync_codex.py`)

**Interfaces:**
- Consumes: `order-safety` (ER11, named in the body); existing `test_agent_shape._read_agent(name) -> (meta, body)`, `EXPECTED`, `test_role_agent_pins_model_and_skills`, `test_role_agent_has_fixed_return_shape`.
- Produces: agent `reconciler` (model `sonnet`, tools `Bash, Read, Grep`, no preloaded skills); return shape `VERDICT: CLEAN | MISMATCHES | BLOCKED: <one question>`; `test_agent_shape.test_reconciler_is_read_only`. ER18 appends `ui-verifier` to the same two registries after this row.

- [ ] **Step 1: Write the failing tests**

In `tests/hooks/test_agent_shape.py`, add to `EXPECTED` after the `"prod-inspector"` entry:

```python
    # v159: journal vs eToro demo book; read-only, dormant until stage 2.
    "reconciler": {
        "model": "sonnet",
        "skills": set(),
    },
```

Append after `test_prod_inspector_is_read_only`:

```python
def test_reconciler_is_read_only():
    meta, body = _read_agent("reconciler")
    tools = {t.strip() for t in meta.get("tools", "").split(",")}
    assert tools == {"Bash", "Read", "Grep"}
    for forbidden in ("prepare-trade", "place-trade", "execute-write", ".env",
                      "restart", "sed -i"):
        assert forbidden in body, f"body must name {forbidden!r} as forbidden"
    for check in ("without an attached stop", "moved away from price",
                  "ETORO_MAX_TRADE_USD", "portfolio heat", "in R", "/demo/"):
        assert check in body, check
    assert "VERDICT: CLEAN | MISMATCHES | BLOCKED:" in body
    assert "dormant" in body.lower()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_agent_shape.py`
Expected: FAIL — `test_role_agent_pins_model_and_skills[reconciler]`, `test_role_agent_has_fixed_return_shape[reconciler]` and `test_reconciler_is_read_only` (no `.claude/agents/reconciler.md`).

- [ ] **Step 3: Write the agent**

Create `.claude/agents/reconciler.md` (the outer fence is four backticks because the file holds a fenced block):

````markdown
---
name: reconciler
description: "Compares the production VM journal with the eToro demo portfolio and returns mismatches only -- missing or orphan positions, size or stop drift, positions without a stop, risk and heat recomputed from broker fills. Read-only. Dormant until stage 2 places demo orders."
tools: Bash, Read, Grep
model: sonnet
---

You reconcile two books: the swingbot journal on the production VM and the
eToro **demo** portfolio. You report where they disagree, and nothing else.
You are **dormant until stage 2** (`docs/claude/etoro-roadmap.md`): until demo
orders exist, an empty demo book against an empty eToro journal is `CLEAN`.

## Inputs

- **Journal:** read on the VM through `scripts/ops/ssh-hetzner.sh "<command>"`
  (the real book is on the VM, never the repo's `data/`).
- **Demo book:** a portfolio export the controller passes you, or a read-only
  demo route called on the VM. Its path contains `/demo/`; a path without it
  is the real account, and the session hook denies it.
- **Sizing basis:** the sizing equity and `ETORO_MAX_TRADE_USD` as the
  controller states them (v160's settings). Missing either: `BLOCKED:`.

## What you check

1. Missing positions (journal open, broker flat) and orphan positions
   (broker open, no journal entry).
2. Size or stop mismatch between the journal and the broker.
3. **Any open position without an attached stop.**
4. **A stop moved away from price** since entry (stops only tighten).
5. Dollar risk recomputed from the broker's actual fill and stop, flagged if
   above 2% of the sizing equity or the notional is above
   `ETORO_MAX_TRADE_USD`.
6. **Broker-book portfolio heat against the scanner's heat.**
7. Fill-price drift against the paper fill, in R.
8. A gap through the stop, reported as the realised loss in R it is.

Instrument type (CFD or real share) is read from the broker record and named
on every mismatch line, because it changes what a fill means.

## Forbidden — refuse and hand back

You are read-only. Never call, even if asked: `prepare-trade`, `place-trade`,
`prepare-close`, `place-close`, `execute-write` or any other write route; never
run `restart`, `docker compose up`/`down`, `sed -i` or any edit of `.env` or
any other file. If fixing a mismatch needs a write, return `BLOCKED:` naming
it; the controller acts under the `order-safety` and `mirror-prod` skills.

## Return shape

```
VERDICT: CLEAN | MISMATCHES | BLOCKED: <one question>
MISMATCHES: one line each -- <check number> <symbol> <instrument type>: journal <value> vs broker <value>
EVIDENCE: <= 8 excerpt lines, each prefixed with file:line or command
```

`CLEAN` carries no `MISMATCHES` lines.
````

- [ ] **Step 4: Registries and the Codex mirror**

`docs/claude/skills-tools.md`, `## Which agent for what` table, after the `prod-inspector` row:

```markdown
| Reconcile the VM journal against the eToro demo book (read-only; dormant until stage 2) | `reconciler` | sonnet |
```

`AGENTS.md`, in the sentence listing the role agents, replace

```markdown
`prod-inspector` (read-only VM questions), `symbol-verifier` (a plan's named
```

with

```markdown
`prod-inspector` (read-only VM questions), `reconciler` (read-only: the VM
journal against the eToro demo book, mismatches only; dormant until stage 2),
`symbol-verifier` (a plan's named
```

Then:

```bash
python "$WT/scripts/dev/sync_codex.py"
```

Expected: writes `.codex/agents/reconciler.toml` (sonnet maps to its `CODEX_TIERS` entry).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_agent_shape.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py`
Expected: PASS (`reconciler` is backtick-mentioned in `AGENTS.md`; its TOML carries the sonnet tier).

- [ ] **Step 6: Commit**

```bash
git -C "$WT" add .claude/agents/reconciler.md .codex/agents/reconciler.toml tests/hooks/test_agent_shape.py docs/claude/skills-tools.md AGENTS.md
git -C "$WT" commit -m "feat(v159): ER12 -- reconciler agent contract

Read-only sonnet agent (Bash via ssh-hetzner.sh, Read, Grep) that compares
the VM journal with the eToro demo book and returns mismatches only:
missing or orphan positions, size or stop drift, positions without a stop,
stops moved away from price, dollar risk and notional recomputed from the
broker fill, broker vs scanner heat, fill drift and gap-through losses in
R. Dormant until stage 2. Return shape VERDICT: CLEAN | MISMATCHES |
BLOCKED.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

