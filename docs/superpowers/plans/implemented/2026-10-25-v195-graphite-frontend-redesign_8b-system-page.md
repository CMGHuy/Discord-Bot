# v195 — Graphite, Part 8b: System on `sb-page`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-24:" -A 400 <this file>`.

**Scope of this part (V195-24):** split from Part 8 (`2026-10-25-v195-graphite-frontend-redesign_8-system-regrouping.md`) for the 1500-line cap, unchanged. V195-24 moves the System workspace onto `sb-page`: the tab bar in the scope bar, the open tab in the primary slot, and the three destructive commands the tabs carried (restart bot, clear log, discard settings) in `[page-actions]`, each `danger-quiet` behind its `sb-confirm-dialog`. It runs after V195-23 (same lane: `system.ts`, `scan-tab.ts`, `scan-tab.spec.ts`, `system.spec.ts`).

**Where commands run.** `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`; `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/`. Frontend runs through `npm --prefix "$WT/frontend" ...`.

**The state earlier tasks leave (read before editing).** Part 8's list binds this task (the `sb-page` contract, V195-8's `danger-quiet` System call sites, the `primitives.spec.ts` button gate, the `title` rule). On top of that, from Part 8:

- `system.store.ts` (V195-22, V195-23): `SYSTEM_TABS = ['scan', 'providers', 'settings', 'logs']`, `systemTabFrom(raw)`, `resolveScan()` reads `/system/scan` only, `resolveProviders()`, `loadProviders()`. Unchanged and used here: `restartAvailable()` (from the settings document's `restart_available`), `restarting()`, `restartBot()`, `logs()`, `logSource()`, `clearLogs()`, `dirty()`, `saving()`, `resetDraft()`, `edit(field, value)`, `fields()`, `loadSettings()`, `loadLogs()`.
- `system.ts` (V195-23): `TABS` in the order Scan · Providers · Settings · Logs, `activeTab = computed(() => systemTabFrom(this.tab()))`, `goToTab(tab)` (navigates `[]` with `queryParams: { tab: tab === 'settings' ? null : tab }`, `queryParamsHandling: 'merge'`, `replaceUrl: true`), a `@switch` over the four tab components, `sb-section-head` with the `Unsaved settings` status.
- `system.spec.ts` (V195-23): helpers `mount(tab?: string)`, `tabLabels(el)`, `selected(el)`; `describe('System tabs (v195 §5.1, correction 4)', ...)`.
- `scan-tab.ts` (V195-23): the Scan panel and the Bot process panel only (Restart bot button `variant="danger-quiet"` with `[loading]="store.restarting()"` and `(click)="asking.set(true)"`, its `sb-confirm-dialog`, `asking`, `restart()`); `scan-tab.spec.ts` ends with `describe('Scan tab after the Providers split (v195 §5.1)', ...)`.
- `logs-tab.ts`: `LOG_CONTROLS` (`source`, `refresh`, `raw`, `clear`), the `slot="clear"` button (`variant="danger-quiet"`), its `sb-confirm-dialog`, `asking`, `consequence()`, `clear()`.
- `settings-tab.ts`: the save bar (`sb-control-row.bar.unsaved`, shown while `store.dirty()`) with `Discard` (`variant="danger-quiet"`, `(click)="confirmDiscard.set(true)"`), `Preview changes` and `Save`; the `Discard unsaved settings?` `sb-confirm-dialog`; `confirmDiscard`, `discardDraft()`. The stale-settings banner's `discard and load the newer values` (`variant="ghost"`, `store.discardDraftAndReload()`) is a recovery choice inside a warning, not a housekeeping command, and stays where it is.

Re-read each file before editing it; every step names its edit by symbol or exact string.

---

# Phase 5 — Workspaces: System (continued)

### Task V195-24: System on `sb-page`: tab bar in the scope bar; restart bot, clear log and discard settings in `[page-actions]` per tab, each `danger-quiet` behind `sb-confirm-dialog`
**Model:** sonnet — one workspace re-laid onto the template, three buttons and their dialogs moved from three tab components into its header, with specs; the care is in each command keeping its old condition (restart only where the deployment can, discard only with a draft) and its dialog wording.

**Files:**
- Modify: `frontend/src/app/workspaces/system/system.ts` (whole file)
- Modify: `frontend/src/app/workspaces/system/system.spec.ts` (imports; `mount`; one appended `describe`)
- Modify: `frontend/src/app/workspaces/system/scan-tab.ts` (Restart bot button, its dialog, `asking`, `restart()`)
- Modify: `frontend/src/app/workspaces/system/scan-tab.spec.ts` (one appended `describe`)
- Modify: `frontend/src/app/workspaces/system/logs-tab.ts` (`LOG_CONTROLS`, the `slot="clear"` button, its dialog, `asking`, `consequence()`, `clear()`)
- Modify: `frontend/src/app/workspaces/system/logs-tab.spec.ts` (one appended `describe`)
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts` (the save bar's `Discard`, its dialog, `confirmDiscard`, `discardDraft()`)
- Modify: `frontend/src/app/workspaces/system/settings-tab.spec.ts` (one appended `describe`)

**Interfaces:**
- Consumes: `Page` (`sb-page`, `ui/page.ts`, V195-21; slots `[page-actions]`, `[page-scope]`, `[page-primary]`, default slot for dialogs; `h1.title` from `RouteTitleService.title()`); `ConfirmDialog` (`sb-confirm-dialog`: `open`, `title`, `consequence`, `confirmLabel`, `working`, `dangerVariant`, outputs `confirmed`, `cancelled`; renders a `<dialog>` that has `open` while shown); `Button` (`button[sb-button]`, `variant`, `loading`; host class = variant); `TabBar`; `RouteTitleService.set(title, subtitle)` (spec only); `installDialogPolyfill` (`testing/dialog-polyfill.ts`, spec only); the `SystemStore` members listed in this part's header; `ProvidersTab` (V195-23).
- Produces (nothing later tasks consume beyond V195-33's `workspace-consistency` check that `system.ts` contains `<sb-page` and imports `Page`):
  - `system.ts`: `type SystemAction = 'restart' | 'clear-log' | 'discard'`; `TAB_ACTION: Readonly<Record<SystemTab, SystemAction | null>>` (`scan` → `restart`, `providers` → `null`, `settings` → `discard`, `logs` → `clear-log`); `clearLogConsequence(path: string | null | undefined, source: LogSource): string`.
  - Markup: `sb-page` > `div.page-actions[page-actions]` (optional `span.dirty[role="status"]`, then at most one `button[sb-button][data-action="restart" | "clear-log" | "discard"]`, `variant="danger-quiet"`), `sb-tab-bar[page-scope]`, `div.tab-body[page-primary]` (the open tab), three `sb-confirm-dialog`s (default slot, `dangerVariant="danger-quiet"`).
  - `LOG_CONTROLS` ids become `source`, `refresh`, `raw`.

**What changes, and what is already there.** Spec Phase 4 and §5.2: every workspace sits on `sb-page`, and destructive actions (restart bot, clear log, discard settings) live only in the header's actions slot and always open the confirm dialog, `danger-quiet` for housekeeping. Today System is `sb-section-head` + `sb-tab-bar` + the tab body, and each destructive command sits inside its tab: Restart bot in the Scan tab's Bot process panel, Clear in the Logs toolbar, Discard in the Settings save bar, each with its own `sb-confirm-dialog`. After this task System renders `sb-page`: the page's one `h1` (the route title, `System`, with its subtitle), the tab bar in the scope bar, the open tab in the primary slot, and in the header's actions slot the command that belongs to the open tab. Each command keeps its condition (Restart only when `restartAvailable()`, as the Scan tab showed it; Discard only while the draft is dirty, as the save bar showed it; Clear log always on Logs), its loading state, and its dialog's title, consequence and confirm label word for word; the Clear dialog still names the file. The `Unsaved settings` status moves from `sb-section-head` into the same actions slot, beside Discard, so it stays visible from every tab. The tabs keep everything else: the Bot process panel keeps its explanation (now pointing at the header button) and its "unavailable in this deployment" text, the Logs toolbar keeps source, Refresh and Raw, and the save bar keeps the count, Preview changes and Save. "Stop current scan" stays with the scan commands: it is a cooperative scan command beside Scan now and Pause (`variant="secondary"`), not a destructive one, and the spec's destructive list does not name it. The Providers tab has no command. Nothing in the store changes.

- [ ] **Step 1: Write the failing tests**

1. In `$WT/frontend/src/app/workspaces/system/system.spec.ts`:
   - Add to the imports: `import { readFileSync } from 'node:fs';` and `import { join } from 'node:path';` at the top; `HttpTestingController` to the `@angular/common/http/testing` import; `beforeAll` to the `vitest` import; and

```ts
import { SettingField } from '../../api/models';
import { RouteTitleService } from '../../routing/route-title.service';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
```

   - In `mount`, directly after `TestBed.configureTestingModule({ ... });`, add `TestBed.inject(RouteTitleService).set('System', 'Settings, logs, scan control and provider health');`.
   - Append at the end of the file:

```ts
/* -- v195 Phase 4 and §5.2 -- System on sb-page, destructive commands in the header -- */

function field(key: string): SettingField {
  return {
    key, label: key, type: 'str', value: 'x', default: 'x', help: '',
    min: null, max: null, step: null, options: [], sensitive: false, hot_reloadable: true,
  };
}

const settingsPayload = (restartAvailable: boolean) => ({
  sections: [{ name: 'Discord', icon: 'settings', description: '', fields: [field('discord')] }],
  audit: [],
  restart_available: restartAvailable,
});

async function settle(fixture: ComponentFixture<System>): Promise<void> {
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
}

const actions = (el: HTMLElement) =>
  [...el.querySelectorAll<HTMLButtonElement>('sb-page header.bar .actions button')];

const openDialog = (el: HTMLElement) => el.querySelector('dialog[open]');

function confirmButton(el: HTMLElement, label: string): HTMLButtonElement {
  return [...openDialog(el)!.querySelectorAll<HTMLButtonElement>('button')]
    .find((button) => button.textContent!.trim() === label)!;
}

describe('System on sb-page (v195 Phase 4, §5.2)', () => {
  beforeAll(() => installDialogPolyfill());

  it('renders the page title as the one h1, the tab bar in the scope bar and the tab as primary', async () => {
    const { el } = await mount();
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('System');
    expect(el.querySelector('sb-page .scope sb-tab-bar')).toBeTruthy();
    expect(el.querySelector('sb-page .primary sb-settings-tab')).toBeTruthy();
    expect(el.querySelector('sb-section-head')).toBeNull();
  });

  it('puts Clear log in the header on Logs, behind a dialog that names the file', async () => {
    const { fixture, el } = await mount('logs');
    const backend = TestBed.inject(HttpTestingController);
    TestBed.inject(SystemStore).loadLogs();
    backend.expectOne((r) => r.method === 'GET' && r.url === '/api/v1/system/logs').flush({
      source: 'bot', lines: 500, path: 'logs/bot.log', content: 'started',
    });
    await settle(fixture);

    const [clear] = actions(el);
    expect(clear.textContent!.trim()).toBe('Clear log');
    expect(clear.dataset['action']).toBe('clear-log');
    expect(clear.classList).toContain('danger-quiet');

    clear.click();
    await settle(fixture);
    expect(openDialog(el)!.textContent).toContain('logs/bot.log will be emptied');

    confirmButton(el, 'Clear').click();
    await settle(fixture);
    const request = backend.expectOne((r) => r.method === 'DELETE' && r.url === '/api/v1/system/logs');
    expect(request.request.params.get('source')).toBe('bot');
    request.flush({ ok: true, message: 'Cleared logs/bot.log' });
    backend.match((r) => r.method === 'GET' && r.url === '/api/v1/system/logs');
    await settle(fixture);
    expect(openDialog(el)).toBeNull();
  });

  it('puts Restart bot in the header on Scan where the deployment can restart, and confirms it', async () => {
    const { fixture, el } = await mount('scan');
    const backend = TestBed.inject(HttpTestingController);
    TestBed.inject(SystemStore).loadSettings();
    backend.expectOne('/api/v1/system/settings').flush(settingsPayload(true));
    await settle(fixture);

    const [restart] = actions(el);
    expect(restart.textContent!.trim()).toBe('Restart bot');
    expect(restart.classList).toContain('danger-quiet');

    restart.click();
    await settle(fixture);
    expect(openDialog(el)!.textContent).toContain('Restart the bot');
    const confirm = confirmButton(el, 'Restart');
    expect(confirm.classList).toContain('danger-quiet');

    confirm.click();
    await settle(fixture);
    backend.expectOne('/api/v1/system/bot/restart').flush({ message: 'Restarting the bot.' });
    await settle(fixture);
    expect(el.textContent).toContain('Restarting the bot.');
  });

  it('offers no restart where the deployment cannot, and says so in the tab', async () => {
    const { fixture, el } = await mount('scan');
    TestBed.inject(SystemStore).loadSettings();
    TestBed.inject(HttpTestingController)
      .expectOne('/api/v1/system/settings').flush(settingsPayload(false));
    await settle(fixture);

    expect(actions(el)).toHaveLength(0);
    expect(el.textContent).toContain('Restarting is unavailable in this deployment');
  });

  it('puts Discard in the header only while there are unsaved settings, and discards on confirm', async () => {
    const { fixture, el } = await mount();
    const store = TestBed.inject(SystemStore);
    store.loadSettings();
    TestBed.inject(HttpTestingController)
      .expectOne('/api/v1/system/settings').flush(settingsPayload(false));
    await settle(fixture);
    expect(actions(el)).toHaveLength(0);
    expect(el.querySelector('.page-actions .dirty')).toBeNull();

    store.edit(store.fields()[0], 'changed');
    await settle(fixture);
    expect(el.querySelector('sb-page header.bar .actions .dirty')!.textContent!.trim())
      .toBe('Unsaved settings');
    const [discard] = actions(el);
    expect(discard.textContent!.trim()).toBe('Discard changes');
    expect(discard.classList).toContain('danger-quiet');

    discard.click();
    await settle(fixture);
    expect(openDialog(el)!.textContent).toContain('Discard unsaved settings?');
    confirmButton(el, 'Discard changes').click();
    await settle(fixture);

    expect(store.dirty()).toBe(false);
    expect(actions(el)).toHaveLength(0);
  });

  it('cancelling a dialog runs nothing', async () => {
    const { fixture, el } = await mount('logs');
    const backend = TestBed.inject(HttpTestingController);
    actions(el)[0].click();
    await settle(fixture);
    confirmButton(el, 'Cancel').click();
    await settle(fixture);

    backend.expectNone((r) => r.method === 'DELETE');
  });

  it('puts no command in the header on Providers', async () => {
    const { el } = await mount('providers');
    expect(actions(el)).toHaveLength(0);
  });

  it('keeps every destructive control and its dialog out of the tab bodies', () => {
    for (const file of ['scan-tab.ts', 'logs-tab.ts', 'settings-tab.ts', 'providers-tab.ts']) {
      const src = readFileSync(join(process.cwd(), 'src/app/workspaces/system', file), 'utf8');
      expect(src, file).not.toMatch(/variant="danger/);
      expect(src, file).not.toContain('<sb-confirm-dialog');
    }
  });
});
```

   The cancel case relies on `sb-confirm-dialog`'s cancel button reading `Cancel` (its `cancelLabel` default).

2. In `$WT/frontend/src/app/workspaces/system/scan-tab.spec.ts`, append:

```ts
describe('Scan tab after System moved onto sb-page (v195 Phase 4)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/system/scan-tab.ts'), 'utf8');

  it('leaves Restart bot to the page header and keeps the explanation and the unavailable text', () => {
    expect(src).not.toContain('asking');
    expect(src).not.toContain('<sb-confirm-dialog');
    expect(src).toContain('Restart bot, in the page header,');
    expect(src).toContain('Restarting is unavailable in this deployment');
  });
});
```

3. In `$WT/frontend/src/app/workspaces/system/logs-tab.spec.ts`, change `import { LogsTab } from './logs-tab';` to `import { LOG_CONTROLS, LogsTab } from './logs-tab';` and append:

```ts
describe('LogsTab after System moved onto sb-page (v195 Phase 4)', () => {
  it('leaves Clear to the page header and keeps source, Refresh and Raw', async () => {
    expect(LOG_CONTROLS.map((control) => control.id)).toEqual(['source', 'refresh', 'raw']);

    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend
      .expectOne((r) => r.url === '/api/v1/system/logs')
      .flush(payload({ content: 'started' }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    const labels = [...el.querySelectorAll('button')].map((b) => b.textContent!.trim());
    expect(labels).toContain('Refresh');
    expect(labels).not.toContain('Clear');
    expect(el.querySelector('sb-confirm-dialog')).toBeNull();
    expect(el.querySelector('a.raw')).toBeTruthy();
  });
});
```

4. In `$WT/frontend/src/app/workspaces/system/settings-tab.spec.ts`, append:

```ts
describe('SettingsTab after System moved onto sb-page (v195 Phase 4)', () => {
  it('leaves Discard to the page header and keeps the count, Preview and Save in the save bar', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/system/settings').flush(payload({ sections: RAIL_SECTIONS }));
    await fixture.whenStable();
    const store = TestBed.inject(SystemStore);
    store.edit(store.fields()[0], 'changed');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    const bar = el.querySelector('.bar.unsaved')!;
    expect(bar.textContent).toContain('1 unsaved change');
    expect([...bar.querySelectorAll('button')].map((b) => b.textContent!.trim()))
      .toEqual(['Preview changes', 'Save']);
    expect(el.querySelector('sb-confirm-dialog')).toBeNull();
  });
});
```

`RAIL_SECTIONS`, `payload` and `seed` are the file's existing top-level declarations.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/system/system.spec.ts --include src/app/workspaces/system/scan-tab.spec.ts --include src/app/workspaces/system/logs-tab.spec.ts --include src/app/workspaces/system/settings-tab.spec.ts
```

Expected: FAIL. `system.spec.ts`'s new cases find no `h1` and no `sb-page header.bar .actions`; the source case finds `variant="danger-quiet"` and `<sb-confirm-dialog` in three tab files; the scan-tab case finds `asking`; `LOG_CONTROLS` still has `clear`; the save bar still lists `Discard`. V195-23's four `System tabs` cases still pass.

- [ ] **Step 3: Rewrite `system.ts` on `sb-page`**

Replace the whole of `$WT/frontend/src/app/workspaces/system/system.ts` with:

```ts
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { Router } from '@angular/router';

import { LogSource, SystemStore, SystemTab, systemTabFrom } from '../../stores/system.store';
import { Button } from '../../ui/button';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { Tab, TabBar } from '../../ui/layout';
import { Page } from '../../ui/page';
import { LogsTab } from './logs-tab';
import { ProvidersTab } from './providers-tab';
import { ScanTab } from './scan-tab';
import { SettingsTab } from './settings-tab';

/** Scan · Providers · Settings · Logs — v195 §5.1, the order of
 *  `SYSTEM_TABS`. Settings stays the landing tab (correction 4). */
const TABS: Tab[] = [
  { id: 'scan', label: 'Scan' },
  { id: 'providers', label: 'Providers' },
  { id: 'settings', label: 'Settings' },
  { id: 'logs', label: 'Logs' },
];

/** The destructive commands the System tabs offer, each in the page header. */
export type SystemAction = 'restart' | 'clear-log' | 'discard';

/** v195 Phase 4: the one header command that belongs to each tab. Providers
 *  is a readout and has none. */
export const TAB_ACTION: Readonly<Record<SystemTab, SystemAction | null>> = {
  scan: 'restart',
  providers: null,
  settings: 'discard',
  logs: 'clear-log',
};

/** Names the file, because "are you sure?" is answered yes reflexively and
 *  these two logs are the only record of what the bot did. Moved from
 *  logs-tab.ts with the button (v195 Phase 4). */
export function clearLogConsequence(path: string | null | undefined, source: LogSource): string {
  return `${path ?? `the ${source} log`} will be emptied. Its contents are not backed up and cannot be recovered.`;
}

/**
 * System — the administrative workspace: configuration, logs, scan control,
 * provider health.
 *
 * A shell over four tab components that each read `SystemStore`. Split by
 * file rather than by store because they share one refetch story and one
 * `settings`/`scan`/`bot` event wiring; splitting the store as well would
 * mean several subscriptions to the same events.
 *
 * **On `sb-page` (v195 Phase 4).** The page title is the one `h1`, the tab
 * bar is the scope bar, the open tab is the primary slot. The tab's one
 * destructive command -- restart the bot, clear the log, discard the
 * settings draft -- sits in the header's actions slot, `danger-quiet`,
 * behind its confirm dialog: never inside a tab body, so a housekeeping
 * command is always in the same place and never beside a routine one.
 * Each keeps the condition it had in its tab: Restart only where the
 * deployment can restart, Discard only while there is a draft to lose.
 *
 * **The active tab is a query parameter**, as on Analytics and for the same
 * reason: a tab held in component state cannot be linked to, does not
 * survive a reload, and makes the back button skip the whole workspace.
 *
 * The tab bodies are rendered with `@switch` rather than kept alive hidden.
 * The one piece of state that must survive switching away is the settings
 * draft, and it lives in the store — which is what makes leaving the tab to
 * check a log safe mid-edit.
 */
@Component({
  selector: 'sb-system',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Page, TabBar, Button, ConfirmDialog, SettingsTab, LogsTab, ScanTab, ProvidersTab],
  // v54 D1: the tabs behind this shell are dense operational surfaces --
  // tight rows, more per screen -- so it defaults to the instrument
  // register. On the host (a static class, not a template wrapper) because
  // :host is the ancestor the register's three variables need to reach.
  host: { class: 'register-instrument' },
  template: `
    <sb-page>
      <div page-actions class="page-actions">
        @if (store.dirty()) {
          <!-- Visible from every tab: the draft survives switching away, and
               unsaved configuration you have forgotten about is worse than
               the reminder. -->
          <span class="dirty" role="status">Unsaved settings</span>
        }
        @switch (action()) {
          @case ('restart') {
            <button
              sb-button
              variant="danger-quiet"
              type="button"
              data-action="restart"
              [loading]="store.restarting()"
              (click)="asking.set('restart')"
            >
              Restart bot
            </button>
          }
          @case ('clear-log') {
            <button
              sb-button
              variant="danger-quiet"
              type="button"
              data-action="clear-log"
              (click)="asking.set('clear-log')"
            >
              Clear log
            </button>
          }
          @case ('discard') {
            <button
              sb-button
              variant="danger-quiet"
              type="button"
              data-action="discard"
              [disabled]="store.saving()"
              (click)="asking.set('discard')"
            >
              Discard changes
            </button>
          }
        }
      </div>

      <sb-tab-bar page-scope [tabs]="tabs" [active]="activeTab()" (activeChange)="goToTab($event)" />

      <div page-primary class="tab-body">
        @switch (activeTab()) {
          @case ('scan') {
            <sb-scan-tab />
          }
          @case ('providers') {
            <sb-providers-tab />
          }
          @case ('logs') {
            <sb-logs-tab />
          }
          @default {
            <sb-settings-tab />
          }
        }
      </div>

      <sb-confirm-dialog
        [open]="asking() === 'restart'"
        title="Restart the bot"
        consequence="The bot container will stop and start again. Any scan in progress is abandoned, and alerts are not delivered until it is back."
        confirmLabel="Restart"
        dangerVariant="danger-quiet"
        [working]="store.restarting()"
        (confirmed)="confirm('restart')"
        (cancelled)="asking.set(null)"
      />
      <sb-confirm-dialog
        [open]="asking() === 'clear-log'"
        title="Clear the log"
        [consequence]="clearConsequence()"
        confirmLabel="Clear"
        dangerVariant="danger-quiet"
        (confirmed)="confirm('clear-log')"
        (cancelled)="asking.set(null)"
      />
      <sb-confirm-dialog
        [open]="asking() === 'discard'"
        title="Discard unsaved settings?"
        consequence="Every unsaved setting change in this form will be lost."
        confirmLabel="Discard changes"
        dangerVariant="danger-quiet"
        (confirmed)="confirm('discard')"
        (cancelled)="asking.set(null)"
      />
    </sb-page>
  `,
  styles: `
    /* sb-page lays out the header, scope bar and primary slot and their
       gaps; this host only carries the register.
       No backticks in here: these styles live in a TS template literal. */
    :host { display: block; }
    .page-actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: flex-end;
      gap: var(--space-8);
    }
    .dirty { color: var(--warn); font-size: var(--text-table); }
    /* minmax(0, 1fr), not the implicit auto track: one un-shrinkable panel in
       a tab must not stretch the workspace past the viewport. */
    .tab-body { display: grid; grid-template-columns: minmax(0, 1fr); }
  `,
})
export class System {
  private readonly router = inject(Router);
  protected readonly store = inject(SystemStore);

  /** Arrives through `withComponentInputBinding`, so this component is
   *  testable without standing up a router. */
  readonly tab = input<string>();

  protected readonly tabs = TABS;

  /** An unknown or absent `?tab=` falls back to Settings rather than
   *  rendering nothing, so a hand-edited URL still shows something. */
  protected readonly activeTab = computed<SystemTab>(() => systemTabFrom(this.tab()));

  /** The dialog showing, if any. Only ever set from a header button, so no
   *  confirmation shows for a command nobody asked for. */
  protected readonly asking = signal<SystemAction | null>(null);

  /** The open tab's header command, under the condition its tab used:
   *  no Restart where the deployment cannot restart (the Bot process panel
   *  says why), no Discard without a draft. */
  protected readonly action = computed<SystemAction | null>(() => {
    const action = TAB_ACTION[this.activeTab()];
    if (action === 'restart' && !this.store.restartAvailable()) return null;
    if (action === 'discard' && !this.store.dirty()) return null;
    return action;
  });

  protected readonly clearConsequence = computed(() =>
    clearLogConsequence(this.store.logs()?.path, this.store.logSource()),
  );

  private readonly run: Record<SystemAction, () => void> = {
    restart: () => this.store.restartBot(),
    'clear-log': () => this.store.clearLogs(),
    discard: () => this.store.resetDraft(),
  };

  protected confirm(action: SystemAction): void {
    this.run[action]();
    this.asking.set(null);
  }

  protected goToTab(tab: string): void {
    // Matching Analytics: `replaceUrl` so flipping tabs does not fill the
    // history, `merge` so nothing else in the URL is dropped, and the
    // default tab drops the parameter rather than pinning `?tab=settings`.
    void this.router.navigate([], {
      queryParams: { tab: tab === 'settings' ? null : tab },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
}
```

- [ ] **Step 4: Take the commands out of the three tabs**

1. `$WT/frontend/src/app/workspaces/system/scan-tab.ts`:
   - Replace the `@if (store.restartAvailable()) { … }` branch's body (the `<p class="explain">Restarts the bot container. …</p>` and the `Restart bot` button) with:

```html
        <p class="explain">
          Restart bot, in the page header, restarts the bot container. Open
          positions are unaffected — they live in the data files, not in the
          process.
        </p>
```

     The `@else` branch (`Restarting is unavailable in this deployment …`) and the `store.restartMessage()` paragraph stay as they are.
   - Delete the `<sb-confirm-dialog [open]="asking()" title="Restart the bot" … />` element.
   - In the class, delete `protected readonly asking = signal(false);` and the `restart()` method; in the `@angular/core` import drop `signal`; delete `import { ConfirmDialog } from '../../ui/confirm-dialog';` and remove `ConfirmDialog` from the `imports` array (it becomes `[Panel, Button, Toolbar, Freshness]`).
   - In the component doc comment, replace `` `restart_available` `` / `says so ahead of time and hides the button;` with `` `restart_available` `` / `says so ahead of time and hides the page header's Restart bot;` (the rest of the paragraph is unchanged).

2. `$WT/frontend/src/app/workspaces/system/logs-tab.ts`:
   - Replace `LOG_CONTROLS` and the comment above it with:

```ts
/**
 * v95 D4 — `sb-control-row` force-stacks below 640px, turning short
 * controls into screen-wide blocks above the log. `source` and `refresh` are
 * how you pick and load what you're reading, so they stay put; `raw` is a
 * convenience link and steps back first. Clearing the log is destructive
 * and lives in the page header since v195 (Phase 4).
 */
export const LOG_CONTROLS: ToolbarControl[] = [
  { id: 'source', label: 'Log source', inlineFrom: 'xs' },
  { id: 'refresh', label: 'Refresh', inlineFrom: 'xs' },
  { id: 'raw', label: 'Raw log', inlineFrom: 'sm' },
];
```

   - In the template delete the `<button slot="clear" sb-button variant="danger-quiet" type="button" (click)="asking.set(true)">` … `</button>` element and the `<sb-confirm-dialog [open]="asking()" title="Clear the log" … />` element.
   - In the class delete `protected readonly asking = signal(false);`, `consequence()` with its doc comment, and `clear()`; drop `signal` from the `@angular/core` import if nothing else in the file uses it (as of v194 nothing does; lint flags a leftover); delete `import { ConfirmDialog } from '../../ui/confirm-dialog';` and `ConfirmDialog` from the `imports` array.
   - In the component doc comment replace `The log tail — bot or admin, with a raw view and a clear action.` with `The log tail — bot or admin, with a raw view. Clearing it is the page header's (v195 Phase 4).`

3. `$WT/frontend/src/app/workspaces/system/settings-tab.ts`:
   - In the save bar (`<sb-control-row class="bar-actions">`), delete the `Discard` button (the `sb-button` with `variant="danger-quiet"` and `(click)="confirmDiscard.set(true)"`); `Preview changes` and `Save` stay, in that order.
   - Delete the `<sb-confirm-dialog [open]="confirmDiscard()" title="Discard unsaved settings?" … />` element.
   - In the class delete `protected readonly confirmDiscard = signal(false);` and the `discardDraft()` method; delete `import { ConfirmDialog } from '../../ui/confirm-dialog';` and `ConfirmDialog` from the `imports` array. `signal` stays imported (`importText`, `activeCategory`, `railFades` use it).
   - Directly above `<!-- the save bar ---` add one comment line: `<!-- v195 Phase 4: Discard is the page header's; the bar keeps Preview and Save. -->`.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/system/system.spec.ts --include src/app/workspaces/system/scan-tab.spec.ts --include src/app/workspaces/system/logs-tab.spec.ts --include src/app/workspaces/system/settings-tab.spec.ts --include src/app/workspaces/system/providers-tab.spec.ts --include src/app/ui/parity.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `workspace-consistency.spec.ts` stays green: `system.ts` writes no `<h1`, `sb-page` renders it. If the h1 case finds two headings, a tab still renders an `h1` (only `sb-section-head` did, and it is gone from `system.ts`). If a dialog case finds no `dialog[open]`, `beforeAll(() => installDialogPolyfill())` is not running before the first render. If the Clear case reports an unmatched GET after the DELETE, that is the store reloading the log after a successful clear: the `backend.match(...)` line drains it. If the Restart case finds no button, `restartAvailable()` is false: the settings flush must carry `restart_available: true` before `settle`. If the h1 reads empty, the `RouteTitleService.set(...)` line is missing from `mount`.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green.

- [ ] **Step 6: Check it in a browser**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard`, then click through the rail to System. At 1440, 768 and 390: `document.querySelectorAll('h1').length` is 1 and reads `System`, with the description under it; the tab bar sits under the header and scrolls sideways on its own at 390 rather than widening the page (`document.documentElement.scrollWidth <= innerWidth`). Settings tab: no header button; edit any field and `Unsaved settings` plus `Discard changes` appear at the header's right (wrapping under the title at 390, nothing clipped), and Discard → Cancel keeps the edit. Logs tab: `Clear log` in the header, the toolbar shows source, Refresh and Raw; open and cancel its dialog, which names the log file. Scan tab: `Restart bot` in the header on a deployment with the Docker socket (or none, with the Bot process panel's "unavailable" text), the scan commands unchanged in the Scan panel; open and cancel the dialog (do not confirm a restart). Providers: no header button. Every header button is at least 44px tall at 768 and 390. Press Tab from the top bar: focus reaches the header button before the tab bar. Save the PNGs under the session scratchpad.

- [ ] **Step 7: Close**

Close: standard (test: `frontend/src/app/workspaces/system/system.spec.ts`), plus `frontend/src/app/workspaces/system/scan-tab.spec.ts`, `frontend/src/app/workspaces/system/logs-tab.spec.ts` and `frontend/src/app/workspaces/system/settings-tab.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/workspaces/system/system.ts frontend/src/app/workspaces/system/system.spec.ts frontend/src/app/workspaces/system/scan-tab.ts frontend/src/app/workspaces/system/scan-tab.spec.ts frontend/src/app/workspaces/system/logs-tab.ts frontend/src/app/workspaces/system/logs-tab.spec.ts frontend/src/app/workspaces/system/settings-tab.ts frontend/src/app/workspaces/system/settings-tab.spec.ts
git -C "$WT" commit -m "feat(v195): System on sb-page, destructive commands in the header (V195-24)" -m "Spec Phase 4 and §5.2: System renders sb-page (the route title as the one h1, the tab bar as the scope bar, the open tab as primary). Restart bot, Clear log and Discard changes move out of the Scan, Logs and Settings tabs into the header's actions slot, one per tab, each danger-quiet behind its unchanged confirm dialog, with the condition it had (restart only where the deployment can, discard only with a draft). The Unsaved settings status sits beside them. Stop current scan stays with the scan commands: it is not destructive." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

