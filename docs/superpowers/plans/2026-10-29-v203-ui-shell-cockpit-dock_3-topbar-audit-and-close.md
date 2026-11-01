# UI shell cockpit (v203), part 3: the top bar and alarm chip, the layout audit, the full suite

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [UI redesign Phase 1: six-destination IA and the cockpit shell](../specs/2026-10-29-v202-ui-shell-cockpit-design.md)
**Index:** [`_0-index.md`](2026-10-29-v203-ui-shell-cockpit-dock_0-index.md). The Goal, Global Constraints, Review Focus, Parallelisation and every cross-task contract are there, and they bind the tasks below.

Part scope: V203-9 and V203-9b (the alarm chip, then the top bar: wordmark, divider, breadcrumb, alarm and killswitch chips only), V203-10 and V203-10b (the layout audit's new routes and its `dock` check, then the three-width run and its results file) and V203-11 (the full suite, once). `<wt>` is the implementation worktree's absolute path. These tasks run in order, after V203-8b: each edits what the one before it finished.

# Phase 5: Top bar

### Task V203-9: `sb-alarm-chip` in the cluster; freshness, connection and the clock leave the bar

**Model:** sonnet — one small pure-input component over V203-3's `alarmFor`, mounted in the cluster, plus named spec retirements; every word and test given here.

Ledger task V203-9 is split in two to stay under 20 KB. This half builds the alarm chip, mounts it in the cluster and takes the freshness chip, the connection dot and the clock out of the bar. V203-9b brings back the wordmark and sets the final bar order, and it runs straight after this task.

**Files:**
- Create: `frontend/src/app/shell/alarm-chip.ts`, `frontend/src/app/shell/alarm-chip.spec.ts`
- Modify: `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/shell.css`, `frontend/src/app/shell/shell.ts`, `frontend/src/app/shell/shell.spec.ts`. The chip's `hit-area.spec.ts` PADDED row is V203-9b's, beside the wordmark's.

**Interfaces:**
- Consumes: `Alarm` and `alarmFor` (V203-3, `shell/live/live-state.ts`: `interface Alarm { kind: 'bot-down' | 'disconnected' | 'stale'; text: string }`). `DockState.reveal()` (V203-3b). The shell members V203-7b added (`dock`, `liveNow`) and the existing `connection`.
- Produces (index ledger, final): `AlarmChip` (`sb-alarm-chip`), input `alarm: Alarm | null` (default `null`), output `reveal: void`. `div.status-cluster` holds exactly `sb-alarm-chip` then `sb-killswitch-chip`. `Shell` gains `protected readonly alarm: Signal<Alarm | null>` and loses `now`; `clock` stays, because `liveNow` reads it. V203-9b keeps the cluster as it is and moves the elements around it.

Behaviour pinned here (spec v202 §3 "Alarm chip", D5, §8 "Shell"). The words (`Bot down`, `Disconnected`, `Data stale 12 min`, plain `Data stale`) are `alarmFor`'s; the chip never words a state itself.
- `null` renders nothing, so a healthy bar carries no alarm and no empty box. `alarmFor` returns `null` before `/health` answers, so a cold load raises no alarm.
- An alarm renders one `button.alarm-chip`: a dot and the alarm's text, in the warning tone (`--warn` on `--warn-soft`, today's tokens; never the loss red). Its accessible name is the text plus `. Open the live dock`. A tap emits `reveal`, and the shell calls `dock.reveal()`: the docked column from 1024 px, the sheet below.
- The host is a `role="status"` region, so a screen reader hears the alarm when it appears without the focus moving.
- Below 640 px the words hide and the dot stays (the accessible name keeps them). A phone bar cannot hold the wordmark, `Data stale 12 min`, the killswitch chip, the search icon and the avatar in 390 px. The live strip right under the bar (V203-8b) names the same state in its warning tone and with its scan age.
- The freshness chip, the connection dot and the clock leave the bar: the dock's Bot section (V203-4) and the strip (V203-8) carry them.

`shell.spec.ts` assertion changes, by test title (the v195 `fdf6b78a` precedent):
- Retired: `'shows the date and time from the ambient clock'` → `'keeps no clock in the bar: times live in the dock and the strip'`.
- Moved: `'drops the clock and the tape on a phone before it lets the bar overflow'` → `'drops the tape on a phone before it lets the bar overflow'`, without the `.clock` line.
- Retired: `'puts the killswitch and freshness chips in the cluster, hidden at no width'` → `'keeps only the alarm and killswitch chips in the cluster, hidden at no width'`.
- Retired: `'ages the freshness chip from the last successful tick, else the last heartbeat'`. Its words are the dock's Data row now, pinned by V203-4's `botRows` freshness tests (`Scan 5h ago`, `Scan 2m ago` from the heartbeat, `No scan yet`).
- Moved: in `'collapses the bar to the title, the two chips, a search icon and the avatar'` (phone), `.status-cluster sb-freshness-chip` becomes `.status-cluster sb-alarm-chip`. V203-9b replaces the whole test.

- [ ] **Step 1: Write the failing chip spec**

Create `frontend/src/app/shell/alarm-chip.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { AlarmChip } from './alarm-chip';
import { Alarm } from './live/live-state';

describe('AlarmChip (v203, spec v202 §3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function render(alarm: Alarm | null) {
    const fixture = TestBed.createComponent(AlarmChip);
    fixture.componentRef.setInput('alarm', alarm);
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it('renders nothing when nothing is wrong', () => {
    const { el } = render(null);
    expect(el.querySelector('button')).toBeNull();
    expect(el.innerHTML.replace(/<!--[\s\S]*?-->/g, '').trim()).toBe('');
  });

  it.each<[Alarm, string]>([
    [{ kind: 'bot-down', text: 'Bot down' }, 'Bot down. Open the live dock'],
    [{ kind: 'disconnected', text: 'Disconnected' }, 'Disconnected. Open the live dock'],
    [{ kind: 'stale', text: 'Data stale 12 min' }, 'Data stale 12 min. Open the live dock'],
    [{ kind: 'stale', text: 'Data stale' }, 'Data stale. Open the live dock'],
  ])('names %o in words and in its accessible name', (alarm, label) => {
    const button = render(alarm).el.querySelector('button.alarm-chip')!;
    expect(button.querySelector('.text')!.textContent!.trim()).toBe(alarm.text);
    expect(button.getAttribute('aria-label')).toBe(label);
    expect(button.getAttribute('data-kind')).toBe(alarm.kind);
  });

  it('opens the dock on a tap', () => {
    const { fixture, el } = render({ kind: 'stale', text: 'Data stale 20 min' });
    let revealed = 0;
    fixture.componentInstance.reveal.subscribe(() => (revealed += 1));
    el.querySelector<HTMLButtonElement>('button.alarm-chip')!.click();
    expect(revealed).toBe(1);
  });

  it('goes away when the condition clears', () => {
    const { fixture, el } = render({ kind: 'bot-down', text: 'Bot down' });
    fixture.componentRef.setInput('alarm', null);
    fixture.detectChanges();
    expect(el.querySelector('button')).toBeNull();
  });

  it('is a polite status region holding a real button, padded for touch, with no title', () => {
    const { el } = render({ kind: 'disconnected', text: 'Disconnected' });
    expect(el.getAttribute('role')).toBe('status');
    const button = el.querySelector('button')!;
    expect(button.getAttribute('type')).toBe('button');
    expect(button.classList).toContain('sb-hit');
    expect(button.hasAttribute('title')).toBe(false);
  });

  it('takes the warning tone, never the loss red, and keeps only the dot on a phone', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/shell/alarm-chip.ts'), 'utf8');
    expect(source).toContain('background: var(--warn-soft);');
    expect(source).toContain('color: var(--warn);');
    expect(source).not.toMatch(/var\(--neg/);
    expect(source).toMatch(/@media \(max-width: 639px\) \{ \.text \{ display: none; \} \}/);
  });
});
```

- [ ] **Step 2: Retire the old bar assertions and write the failing shell tests**

In `shell/shell.spec.ts`:

In `describe('shell navigation')`, replace the whole clock test with:

```ts
  it('keeps no clock in the bar: times live in the dock and the strip', () => {
    // v203 Retired 'shows the date and time from the ambient clock' (spec v202 D5).
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('header.topbar .clock')).toBeNull();
    expect(readSource('src/app/shell/shell.css').replace(/\/\*[\s\S]*?\*\//g, '')).not.toMatch(/\.clock\b/);
    const code = readSource('src/app/shell/shell.ts').replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
    expect(code).not.toMatch(/readonly now\b/);
  });
```

Rename `'drops the clock and the tape on a phone before it lets the bar overflow'` to `'drops the tape on a phone before it lets the bar overflow'` and delete its line `expect(css).toMatch(/max-width:\s*639px[\s\S]*\.clock[\s\S]*display:\s*none/);`.

In `describe('shell top-bar cluster (v195 Phase 3)')`, replace the cluster test and the freshness-ageing test with:

```ts
  it('keeps only the alarm and killswitch chips in the cluster, hidden at no width', async () => {
    // v203 Retired 'puts the killswitch and freshness chips in the cluster' and
    // 'ages the freshness chip …' (spec v202 D5: freshness, connection and the clock
    // live in the dock and strip; V203-4's botRows pins the freshness words).
    const { el } = await mount();
    const cluster = el.querySelector('header.topbar > .status-cluster')!;
    expect([...cluster.children].map((c) => c.tagName.toLowerCase())).toEqual(['sb-alarm-chip', 'sb-killswitch-chip']);
    expect(el.querySelector('header.topbar sb-freshness-chip, header.topbar sb-connection-status')).toBeNull();
    const css = readSource('src/app/shell/shell.css').replace(/\/\*[\s\S]*?\*\//g, '');
    expect(css).not.toMatch(/(sb-killswitch-chip|sb-alarm-chip|\.status-cluster)[^{}]*\{[^}]*display:\s*none/);
  });

  const alarmText = (el: HTMLElement) =>
    el.querySelector('header.topbar > .status-cluster > sb-alarm-chip button.alarm-chip .text')?.textContent?.trim() ?? null;

  it('raises no alarm before /health answers, nor while all is well', async () => {
    const { fixture, el, backend } = await mount();
    expect(alarmText(el)).toBeNull();                  // botAlive still null: a cold load is no alarm
    for (const request of backend.match((r) => r.url.endsWith('/system/scan'))) request.flush(scanStatus({}));
    await settle(fixture);
    expect(alarmText(el)).toBeNull();                  // last success 12 min ago, under the 900 s rule
  });

  it.each([
    ['the bot is not alive', { bot_alive: false }, 'Bot down'],
    ['the last success is older than 900 s', { bot_last_success: '2026-10-27T11:40:00Z' }, 'Data stale 20 min'],
    ['no tick ever succeeded', { bot_last_success: null }, 'Data stale'],
  ])('raises the alarm chip when %s', async (_, overrides, text) => {
    const { fixture, el, backend } = await mount();
    for (const request of backend.match((r) => r.url.endsWith('/system/scan'))) request.flush(scanStatus(overrides));
    await settle(fixture);
    expect(alarmText(el)).toBe(text);
  });

  it('raises Disconnected when the event stream degrades', async () => {
    class DegradedStream extends FakeEventStream {
      override state(): 'degraded' {
        return 'degraded';
      }
    }
    TestBed.overrideProvider(EventStream, { useValue: new DegradedStream() });
    const { el } = await mount();
    expect(alarmText(el)).toBe('Disconnected');
  });
```

In `describe('shell on a phone (v195 Phase 3)')`, in `'collapses the bar to the title, the two chips, a search icon and the avatar'`, change `'.status-cluster sb-freshness-chip'` to `'.status-cluster sb-alarm-chip'` (Moved; V203-9b replaces the test).

In `describe('shell live dock (v203)', …)` (V203-7b), add at the end:

```ts
  it('opens the collapsed dock from the alarm chip', async () => {
    const { fixture, el, backend } = await mount('/trades');
    for (const request of backend.match((r) => r.url.endsWith('/system/scan'))) request.flush(scan(false));
    await settle(fixture);
    el.querySelector<HTMLButtonElement>('sb-alarm-chip button.alarm-chip')!.click();
    await settle(fixture);
    expect(el.querySelector('aside.live-column > sb-live-dock')).not.toBeNull();
  });

  it('opens the sheet from the alarm chip below 1024 px', async () => {
    narrow.set(true);
    const { fixture, el, backend } = await mount('/trades');
    for (const request of backend.match((r) => r.url.endsWith('/system/scan'))) request.flush(scan(false));
    await settle(fixture);
    el.querySelector<HTMLButtonElement>('sb-alarm-chip button.alarm-chip')!.click();
    await settle(fixture);
    expect(el.querySelector('sb-live-sheet [role=dialog] sb-live-dock')).not.toBeNull();
  });
```

- [ ] **Step 3: Run them to verify they fail**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/alarm-chip.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts
```

Expected: FAIL. `./alarm-chip` does not exist, and the cluster still holds the freshness chip, the connection dot and the clock.

- [ ] **Step 4: Write the chip**

Create `frontend/src/app/shell/alarm-chip.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { Alarm } from './live/live-state';

/**
 * The top bar's alarm -- v203 (spec v202 §3 "Alarm chip", D5).
 *
 * The one live-state signal that must not depend on the dock being open:
 * it shows only while the bot is down, the event stream is dead or
 * degraded, or data is stale (the 900 s rule). The words are `alarmFor`'s
 * (live-state.ts), so the bar, the edge tab and the strip name a state the
 * same way. When nothing is wrong it renders nothing and the bar stays
 * clean. A tap opens the dock (DockState.reveal: the docked column from
 * 1024px, the sheet below).
 *
 * The warning tone, never the loss red: Phase 1 adds no colours, and red is
 * the engaged killswitch's. The host is a status region, so the alarm is
 * announced when it appears. Below 640px only the dot shows: the phone bar
 * has no room for the words, and the live strip directly under it names
 * the same state. The accessible name always carries the words.
 */
@Component({
  selector: 'sb-alarm-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { role: 'status' },
  template: `
    @if (alarm(); as current) {
      <button type="button" class="alarm-chip sb-hit" [attr.data-kind]="current.kind" [attr.aria-label]="label()"
              (click)="reveal.emit()">
        <span class="dot" aria-hidden="true"></span><span class="text">{{ current.text }}</span>
      </button>
    }
  `,
  styles: `
    :host { display: inline-flex; }
    .alarm-chip {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      padding: 2px var(--space-6);
      border: 1px solid var(--warn);
      border-radius: var(--chip-radius);
      background: var(--warn-soft);
      color: var(--warn);
      font: inherit;
      font-size: var(--text-chip);
      font-weight: 600;
      line-height: 1.4;
      white-space: nowrap;
      cursor: pointer;
    }
    /* A status dot: the one full-round shape the radius rules allow (§1.5). */
    .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--warn); }
    @media (max-width: 639px) { .text { display: none; } }
  `,
})
export class AlarmChip {
  /** `alarmFor(...)`: null while nothing is wrong. */
  readonly alarm = input<Alarm | null>(null);
  /** Asks the shell to open the Live dock. */
  readonly reveal = output<void>();

  protected readonly label = computed(() => {
    const current = this.alarm();
    return current ? `${current.text}. Open the live dock` : '';
  });
}
```

- [ ] **Step 5: Mount it in the cluster and take the chips and the clock out**

In `shell/shell.ts`:
- Delete `import { FreshnessChip } from './freshness-chip';` and `import { ConnectionStatus } from './connection-status';`, and delete `ConnectionStatus` and `FreshnessChip` from the component's `imports` array.
- Add `import { AlarmChip } from './alarm-chip';` beside the shell imports, and `AlarmChip` to the `imports` array.
- Change V203-7b's `import { heatStripText, liveWarnings } from './live/live-state';` to `import { alarmFor, heatStripText, liveWarnings } from './live/live-state';`.
- Delete the `now` computed and its doc comment (`` /** `Thu, Sep 11, 2026 16:58` -- one string, … */ ``). Keep `protected readonly clock = inject(CLOCK);`.
- After V203-7b's `awaitingCount`, add:

```ts
  /** The top bar's alarm (spec v202 §3): bot down, stream down or stale data,
   *  worded once by alarmFor. Null while all is well and before /health
   *  answers, so a healthy bar carries no alarm. */
  protected readonly alarm = computed(() => alarmFor({
    lastSuccess: this.connection.botLastSuccess(),
    now: this.liveNow(),
    streamState: this.connection.state(),
    botAlive: this.connection.botAlive(),
  }));
```

In `shell/shell.html`, replace the cluster's comment (`<!-- v195 Phase 3: the right cluster. …-->`) and the whole `<div class="status-cluster">…</div>` with:

```html
      <!-- v203 (spec v202 D5): only the killswitch chip stays, plus the alarm
           chip while the bot is down, the stream is down or data is stale.
           Freshness, connection and the clock live in the Live dock and the
           strip. The alarm opens the dock (DockState.reveal). -->
      <div class="status-cluster">
        <sb-alarm-chip [alarm]="alarm()" (reveal)="dock.reveal()" />
        <sb-killswitch-chip [on]="killswitchOn()" [stale]="killswitchStale()" />
      </div>
```

In `shell/shell.css`:
- Replace the `.status-cluster` comment with `/* The right cluster: the alarm and killswitch chips (v203), pushed to the bar's right edge and tighter than the bar's own gap. */`.
- Delete the whole `.clock { … }` rule, and `.clock { display: none; }` inside `@media (max-width: 639px)`.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/alarm-chip.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean. `freshness-chip.ts` and `connection-status.ts` stay with their specs: `scanAge` feeds `live-state.ts` and the Bot section, and removing the components is not this plan's scope. If lint flags an unused import left in `shell.ts`, delete it. If the degraded-stream test hangs on `whenStable`, the connection store's fallback poll is keeping it busy. In that case replace `await mount()` there with a bare `TestBed.createComponent(Shell)` plus one `detectChanges()`, and keep the assertion. `639px` is already a declared breakpoint (the shell's phone block), so a breakpoint guard that scans component styles needs no change.

Complexity: `label` 2, `alarm` 1.

Layout, at all three widths: build and serve the SPA locally with the `.env` admin credentials (loaded inside the script, never printed), then run `node <wt>/frontend/scripts/layout-audit.mjs --base <local> --widths 390,768,1440`. Report: no horizontal scroll at any width with the bar healthy. Then make the alarm show (stop the local bot, or wait past 900 s) and check again. At 390 the alarm is a dot with a 44 px hit area and the bar still fits; at 768 and 1440 its words show. A tap opens the dock, docked at 1440 and as the sheet at 768 and 390. Report that the alarm and killswitch chips meet 44 px under touch and that nothing overlaps.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add frontend/src/app/shell/alarm-chip.ts frontend/src/app/shell/alarm-chip.spec.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.spec.ts
git -C <wt> commit -m "feat(v203): sb-alarm-chip; freshness, connection and the clock leave the bar

The cluster keeps the killswitch chip and gains the alarm chip, which
shows only while the bot is down, the stream is down or data is stale
(alarmFor's words), in the warning tone, and opens the Live dock. Below
640px only its dot shows. The freshness chip, connection dot and clock
now live in the dock and strip.

Retired: the clock test, the freshness-cluster and ageing tests. Moved:
the phone tape test and the phone cluster assertion.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V203-9b: The wordmark leads the bar; divider, breadcrumb and the Ctrl K trigger after the cluster

**Model:** sonnet — markup and CSS moves in the shell, plus named spec retirements; every edit and test given here.

The second half of ledger task V203-9, split to stay under 20 KB. It runs straight after V203-9, and V203-10 follows it.

**Files:**
- Modify: `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/shell.css`, `frontend/src/app/shell/shell.spec.ts`, `frontend/src/app/ui/hit-area.spec.ts` (the wordmark's and the alarm chip's PADDED rows)

**Interfaces:**
- Consumes: V203-9's cluster (`div.status-cluster` holding `sb-alarm-chip` and `sb-killswitch-chip`, and `Shell.alarm`); the existing `isPhone`, `paletteOpen()`, `openPalette()`, `paletteShortcut` and `onSearchRequested()`.
- Produces (index ledger, final): the top-bar order. Desktop and tablet: `a.brand` (wordmark) · `span.topbar-divider` · `sb-breadcrumb.topbar-lead` · flex · `div.status-cluster` · the Ctrl K trigger · `sb-profile-menu` · `sb-scan-progress`. Phone: `a.brand` (diamond + wordmark) · flex · `div.status-cluster` · `button.search-trigger` · `sb-profile-menu` · `sb-scan-progress`. The ledger writes the desktop Ctrl K trigger as `button.search-trigger`. It stays today's `button.palette-trigger` ("Search or jump…", `kbd` Ctrl K), because `button.search-trigger` is the phone's icon and the "shell above phone width" spec pins its absence. V203-10's audit reads this bar.

Behaviour pinned here (spec v202 §3 "Top bar", D2, §8 "Shell"):
- The two-tone `BomeoCapital` wordmark leads the bar on every device and links to the Dashboard. It is the pre-v195 `.brand .word` rule from `fdf6b78a^`: JetBrains Mono bold at `-0.02em`, "Bomeo" in `--text` and "Capital" in `--accent`. On a phone the diamond sits before it, because the rail that carries the diamond elsewhere is hidden there.
- Desktop and tablet: a hairline divider and the breadcrumb follow the wordmark. A phone has neither, so the wordmark, the cluster, the search icon and the avatar fit 390 px.
- The Ctrl K trigger moves from mid-bar to after the cluster. The cluster's auto left margin takes the free space.
- Unchanged: the killswitch strips, the scan-progress bar hung from the bar, the tape strip, the palette and its shortcuts.

`shell.spec.ts` assertion changes, by test title (the v195 `fdf6b78a` precedent):
- Moved: `'leads the bar with the breadcrumb and renders no heading of its own'`: its first-child assertion becomes the wordmark · divider · breadcrumb order.
- Moved: the gone-list in `'has no expanded, collapsed or overlay state, …'`: `'.brand .word'` becomes `'nav.rail .word'`. The wordmark is back in the bar, never in the rail.
- Retired: `'collapses the bar to the title, the two chips, a search icon and the avatar'` → `'leads the phone bar with the diamond and the wordmark, then the cluster, the search icon and the avatar'`.
- Moved: `'puts the trigger between the breadcrumb and the cluster, and opens the palette from it'` → `'puts the trigger after the cluster, before the avatar, and opens the palette from it'`.

- [ ] **Step 1: Move and retire the old bar assertions**

In `shell/shell.spec.ts`:

In `'has no expanded, collapsed or overlay state, …'`, change `'.brand .word'` in the gone-list to `'nav.rail .word'`.

Rename `'leads the bar with the breadcrumb and renders no heading of its own'` to `'leads the bar with the wordmark, the divider and the breadcrumb, and renders no heading of its own'`. Then replace `expect(bar.firstElementChild!.tagName.toLowerCase()).toBe('sb-breadcrumb');` with:

```ts
    // v203 Moved: the wordmark leads the bar; the breadcrumb follows the divider.
    ['a.brand', 'span.topbar-divider', 'sb-breadcrumb.topbar-lead'].forEach((selector, index) =>
      expect(bar.children[index].matches(selector), selector).toBe(true));
```

In `describe('shell on a phone (v195 Phase 3)')`, replace `'collapses the bar to the title, the two chips, a search icon and the avatar'` (V203-9 already changed one line in it) with:

```ts
  it('leads the phone bar with the diamond and the wordmark, then the cluster, the search icon and the avatar', async () => {
    // v203 Retired 'collapses the bar to the title, the two chips, …' (spec v202 §3).
    const { el } = await mount();
    const bar = el.querySelector('header.topbar')!;
    const order = ['a.brand', 'div.status-cluster', 'button.search-trigger', 'sb-profile-menu', 'sb-scan-progress'];
    expect(bar.children).toHaveLength(order.length);
    order.forEach((selector, index) => expect(bar.children[index].matches(selector), selector).toBe(true));
    const brand = bar.querySelector('a.brand')!;
    expect(brand.firstElementChild!.matches('sb-icon')).toBe(true);
    expect(brand.querySelectorAll('.word span')).toHaveLength(2);
    expect(bar.querySelector('sb-breadcrumb, span.topbar-divider, button.palette-trigger')).toBeNull();
    const search = bar.querySelector('button.search-trigger')!;
    expect(search.getAttribute('aria-label')).toBe('Search or jump to a page');
    // The magnifier: sb-icon's default label for 'search' (V195-14).
    expect(search.querySelector('sb-icon')!.getAttribute('title')).toBe('Search');
    expect(bar.querySelector('.status-cluster sb-killswitch-chip')).not.toBeNull();
    expect(bar.querySelector('.status-cluster sb-alarm-chip')).not.toBeNull();
  });
```

In `describe('shell command palette (v195 §3.1)')`, rename `'puts the trigger between the breadcrumb and the cluster, and opens the palette from it'` to `'puts the trigger after the cluster, before the avatar, and opens the palette from it'`, and replace its two sibling assertions with:

```ts
    // v203 Moved (spec v202 §3): the Ctrl K trigger follows the cluster.
    expect(trigger.previousElementSibling!.matches('div.status-cluster')).toBe(true);
    expect(trigger.nextElementSibling!.matches('sb-profile-menu')).toBe(true);
```

- [ ] **Step 2: Write the failing new tests**

Append to `shell/shell.spec.ts`:

```ts
describe('shell top bar (v203, spec v202 §3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: shellProviders([{ path: 'trades', component: Blank }]) });
    TestBed.overrideProvider(ViewportService, { useValue: { isPhone: signal(false), isNarrow: signal(false), viewport: signal('lg') } });
  });

  function render(): HTMLElement {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('orders the bar: wordmark, divider, breadcrumb, cluster, search, avatar', () => {
    const bar = render().querySelector('header.topbar')!;
    const order = ['a.brand', 'span.topbar-divider', 'sb-breadcrumb.topbar-lead', 'div.status-cluster',
      'button.palette-trigger', 'sb-profile-menu', 'sb-scan-progress'];
    expect(bar.children).toHaveLength(order.length);
    order.forEach((selector, index) => expect(bar.children[index].matches(selector), selector).toBe(true));
    expect(bar.querySelector('span.topbar-divider')!.getAttribute('aria-hidden')).toBe('true');
  });

  it('renders the two-tone wordmark as two spans, not one coloured string', () => {
    // Restored from fdf6b78a^ (spec v202 D2).
    expect(render().querySelectorAll('.brand .word span').length).toBe(2);
  });

  it('gives the wordmark the pre-v195 treatment, Capital in the accent, linking to the Dashboard', () => {
    const brand = render().querySelector('header.topbar > a.brand')!;
    expect([...brand.querySelectorAll('.word span')].map((s) => s.textContent)).toEqual(['Bomeo', 'Capital']);
    expect(brand.getAttribute('href')).toBe('/dashboard');
    expect(brand.getAttribute('aria-label')).toContain('Bomeo Capital');
    expect(brand.querySelector('sb-icon')).toBeNull();          // the diamond heads the rail above phone width
    const css = readSource('src/app/shell/shell.css').replace(/\/\*[\s\S]*?\*\//g, '');
    const rule = (selector: string) => css.match(new RegExp(`^${selector.replace(/[.]/g, '\\.')} \\{[^}]*\\}`, 'm'))?.[0] ?? '';
    for (const declaration of ['font-family: var(--font-mono);', 'font-size: var(--text-body);', 'font-weight: 700;',
      'letter-spacing: -0.02em;', 'white-space: nowrap;']) {
      expect(rule('.brand .word')).toContain(declaration);
    }
    expect(rule('.brand .word span:last-child')).toContain('color: var(--accent);');
  });
});
```

In `ui/hit-area.spec.ts`, in the `PADDED` table of `describe('v179: controls that keep their look and take .sb-hit')`, add after the rail-brand row (`/<a class="rail-brand sb-hit" routerLink="\/dashboard"/`, from V203-1):

```ts
    // v203: the top bar's wordmark link and its alarm chip keep their size and pad with .sb-hit.
    ['src/app/shell/shell.html', /<a class="brand sb-hit" routerLink="\/dashboard"/],
    ['src/app/shell/alarm-chip.ts', /<button type="button" class="alarm-chip sb-hit"/],
```

- [ ] **Step 3: Run them to verify they fail**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/ui/hit-area.spec.ts
```

Expected: FAIL. The bar still leads with the breadcrumb, and there is no `a.brand` and no divider. The alarm-chip PADDED row passes already, because V203-9 wrote that markup.

- [ ] **Step 4: Rewrite the bar**

In `shell/shell.html`, replace everything from `<header class="topbar">` up to the `<!-- Hung from the bar's bottom edge …` comment with the block below. The cluster is V203-9's, unchanged. The profile menu keeps its bindings exactly as they stand, and the scan-progress comment and element after it stay unchanged.

```html
    <header class="topbar">
      <!-- v203 (spec v202 §3, D2): the two-tone BomeoCapital wordmark leads
           the bar on every device. On a phone the diamond sits before it (the
           rail that carries it elsewhere is hidden there). A link, never a
           heading: the page's one <h1> belongs to sb-page (correction 9). -->
      <a class="brand sb-hit" routerLink="/dashboard" aria-label="Bomeo Capital — go to the Dashboard">
        @if (isPhone()) {
          <sb-icon name="brand" title="" />
        }
        <span class="word"><span>Bomeo</span><span>Capital</span></span>
      </a>
      @if (!isPhone()) {
        <span class="topbar-divider" aria-hidden="true"></span>
        <sb-breadcrumb class="topbar-lead" />
      }
      <!-- v203 (spec v202 D5): only the killswitch chip stays, plus the alarm
           chip while the bot is down, the stream is down or data is stale.
           Freshness, connection and the clock live in the Live dock and the
           strip. The alarm opens the dock (DockState.reveal). -->
      <div class="status-cluster">
        <sb-alarm-chip [alarm]="alarm()" (reveal)="dock.reveal()" />
        <sb-killswitch-chip [on]="killswitchOn()" [stale]="killswitchStale()" />
      </div>
      <!-- v195 §3.1: the command palette's trigger (Ctrl K), after the cluster
           from v203. A phone uses the search icon instead. -->
      @if (!isPhone()) {
        <button sb-button variant="ghost" type="button" class="palette-trigger"
                aria-haspopup="dialog" [attr.aria-expanded]="paletteOpen()"
                aria-keyshortcuts="Control+K Meta+K /" (click)="openPalette()">
          <span class="glyph" aria-hidden="true"><sb-icon name="search" /></span>
          <span class="trigger-text">Search or jump…</span>
          <kbd class="shortcut" aria-hidden="true">{{ paletteShortcut }}</kbd>
        </button>
      } @else {
        <button sb-button variant="icon" type="button" class="search-trigger"
                aria-label="Search or jump to a page" (click)="onSearchRequested()">
          <sb-icon name="search" />
        </button>
      }
      <sb-profile-menu [zoom]="zoom()" [state]="connection.state()"
                       [botAlive]="connection.botAlive()" [marketActive]="connection.marketActive()" (zoomCycled)="cycleZoom()"
                       [motion]="motionMode()" (motionChanged)="setMotion($event)"
                       [density]="density.density()" (densityChanged)="density.set($event)"
                       (signedOut)="logout()" />
```

In `shell/shell.css`:
- After `.topbar-lead { flex: 0 1 auto; min-width: 0; }`, add:

```css
/* v203 (spec v202 D2): the two-tone wordmark leads the bar again, the
   pre-v195 .brand .word treatment. On a phone the diamond sits before it. */
.brand {
  display: flex;
  align-items: center;
  gap: var(--space-6);
  flex: none;
  color: inherit;
  text-decoration: none;
}
.brand sb-icon { flex: none; color: var(--accent); }
.brand .word {
  font-family: var(--font-mono);
  font-size: var(--text-body);
  font-weight: 700;
  letter-spacing: -0.02em;
  white-space: nowrap;
}
.brand .word span:last-child { color: var(--accent); }

/* A hairline between the wordmark and the breadcrumb. */
.topbar-divider { flex: none; width: 1px; height: 20px; background: var(--border); }
```

- In `.palette-trigger { … }`, delete `margin-left: auto;`. Replace its comment with `/* v195 §3.1: the palette trigger, a field-shaped quiet button. From v203 it follows the cluster at the bar's right edge (spec v202 §3): the cluster's auto left margin takes the free space. */`.
- In `@media (max-width: 639px) { … }`, delete `.topbar-lead { flex: 1 1 auto; }` (a phone bar has no breadcrumb now). Replace the block's leading comment with `/* Everything here is a removal: the bar never wraps to a second row, which would change the height of every page's content area. On a phone the bar drops the breadcrumb and the divider (the wordmark leads, spec v202 §3), and the rail gives way to the bottom tab bar. */`.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/ui/hit-area.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/breadcrumb.spec.ts
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean. If another shell test reads `header.topbar`'s first child or counts its children, update it as **Moved** (name `a.brand` in a comment), never delete it, and list it in the report.

Complexity: no new function.

Layout, at all three widths: build and serve the SPA locally with the `.env` admin credentials (loaded inside the script, never printed), then run `node <wt>/frontend/scripts/layout-audit.mjs --base <local> --widths 390,768,1440`. Report: no horizontal scroll at any width. At 1440 and 768 the bar reads wordmark · divider · breadcrumb … alarm (when it applies) · killswitch · search · avatar, and the wordmark and the rail diamond centre on one line. The breadcrumb, then the trigger's text, ellipsise before anything wraps. At 390 the diamond, the wordmark, the alarm dot (when it applies), the killswitch chip, the search icon and the avatar share one row. Report that the wordmark link, the alarm and killswitch chips and the trigger meet 44 px under touch, and that nothing overlaps.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts frontend/src/app/ui/hit-area.spec.ts
git -C <wt> commit -m "feat(v203): the top bar leads with the two-tone wordmark again

BomeoCapital returns (the pre-v195 .brand .word rule), then a divider
and the breadcrumb; on a phone the diamond leads it and the breadcrumb
goes. The Ctrl K trigger follows the cluster, before the avatar.

Retired: the old phone-bar order test. Moved: the bar-lead, gone-list
and trigger-sibling assertions.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 6: Layout audit and verification

### Task V203-10: Layout audit: the v202 routes and a `dock` check

**Model:** sonnet — a pure verdict plus one Playwright probe on the audit's existing pattern; every line given here.

Ledger task V203-10 is split in two to stay under 20 KB. This half changes the audit. V203-10b runs it at the three widths and writes the results file, straight after this task.

**Files:**
- Modify: `frontend/scripts/layout-audit-lib.mjs` (`ROUTES`, `CHECKS`, new `DOCK_MIN_WIDTH`, `DOCK_SELECTORS`, `dockVerdict`), `frontend/scripts/layout-audit-lib.test.mjs`, `frontend/scripts/layout-audit.mjs` (new `measureDock`, `measureSheet`, `openSheet`, `auditDock`; `auditWidth`; the header comment)

**Interfaces:**
- Consumes: the final shell (V203-1 … V203-9b): `nav.rail`, `main.workspace` inside `.workspace-row`, `aside.live-column` from 1024 px, `sb-live-strip button.live-strip` and `sb-live-sheet [role=dialog]` below it, and the top bar. The v202 routes (`trades/calendar`, `trades/calendar/:date`, `trades/cancels`, `insights/analytics|research|reports`, `system/versions`) from v202 (merged). V203-1b's `railLabelVerdict` and `auditRailLabels` stay as they are.
- Produces (index ledger, final): `ROUTES` on the new paths only (29). `CHECKS` ends `…, 'hint', 'rail-label', 'dock'`. `DOCK_MIN_WIDTH = 1024`. `DOCK_SELECTORS: Readonly<Record<DockReason, string>>`. `dockVerdict({ width, column, workspace, strip, sheet, viewport }) -> { ok: boolean; reason: DockReason | null }`, where `DockReason` is one of `'no-column' | 'overlaps-workspace' | 'strip-when-docked' | 'docked-below-1024' | 'no-strip' | 'sheet-not-opened' | 'sheet-off-screen'`.

Behaviour pinned here (spec v202 §8 "Layout", §3, §4):
- **Routes.** The audit visits the v202 paths and none of the old ones. The old ones are redirects now, so visiting them audits the same page twice under a name the app no longer links. The count stays 29: every old route has exactly one new twin.
- **`dock` check, from 1024 px.** `aside.live-column` exists, and it never intersects `main.workspace`'s content box (the box inside its padding; a shared edge within 0.5 px is not an overlap). No live strip shows.
- **`dock` check, below 1024 px.** There is no column and the live strip shows. A real tap on it opens `sb-live-sheet [role=dialog]`, and that dialog lies wholly inside the viewport (0.5 px slack). Escape then closes it, so the next route starts with it shut.
- The first failing rule is the reason, and `DOCK_SELECTORS` names the element the finding points at. Like `hint` and `rail-label`, a `dock` finding is fixed, never allowed.

**Retired or moved, explicitly** (`layout-audit-lib.test.mjs`, by title):
- Retired: `'ROUTES visits every route and tab once (spec §2, v188 /cancels and v195 ?tab=providers: 29)'` → `'ROUTES visits every destination, section and tab once, on the v202 paths only (29)'`.
- Moved: `'CHECKS are the spec six plus vcenter, hint (v194 A2) and rail-label (v195 Phase 7), in order'` → `'… rail-label (v195 Phase 7) and dock (v203), in order'`, with `'dock'` appended.
- Unchanged: `'ROUTES: the providers tab sits with the other System tabs'`.

- [ ] **Step 1: Write the failing lib tests**

In `frontend/scripts/layout-audit-lib.test.mjs`, add `DOCK_MIN_WIDTH, DOCK_SELECTORS, dockVerdict` to the import list from `./layout-audit-lib.mjs`. Replace the ROUTES test with:

```js
test('ROUTES visits every destination, section and tab once, on the v202 paths only (29)', () => {
  assert.equal(ROUTES.length, 29);
  assert.equal(new Set(ROUTES).size, ROUTES.length);
  assert.ok(ROUTES.every((route) => route.startsWith('/')));
  for (const tab of ['attribution', 'execution', 'edge', 'pipeline', 'tuning', 'partials']) {
    assert.ok(ROUTES.includes(`/insights/analytics?tab=${tab}`), tab);
  }
  for (const route of ['/dashboard', '/trades', '/trades/:id', '/trades/:id?tab=journal', '/trades/calendar',
    '/trades/calendar/:date', '/trades/cancels', '/plans/:plan', '/insights/analytics', '/insights/research',
    '/insights/reports', '/insights/reports?tab=gates', '/watchlist/:symbol', '/risk', '/system?tab=logs',
    '/system?tab=scan', '/system?tab=providers', '/system/versions', '/ui']) {
    assert.ok(ROUTES.includes(route), route);
  }
  // The six old names redirect (v202 §2): an audit of them would visit the same page twice.
  const old = /^\/(analytics|calendar|cancels|research|reports|versions)(\/|\?|$)/;
  assert.deepEqual(ROUTES.filter((route) => old.test(route)), []);
});
```

In the CHECKS test, rename it as listed above and change the expected list to `['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline', 'vcenter', 'hint', 'rail-label', 'dock']`.

Append:

```js
// dockVerdict (v203, spec v202 §8 "Layout"): the docked column beside the workspace from 1024px,
// the strip and a sheet inside the viewport below it. Rects are {left, right, top, bottom}.
const box = (left, right, top = 0, bottom = 900) => ({ left, right, top, bottom });
const docked = (over = {}) => ({
  width: 1440, column: box(1120, 1440), workspace: box(94, 1106), strip: false, sheet: null,
  viewport: { width: 1440, height: 900 }, ...over,
});
const narrow = (over = {}) => ({
  width: 768, column: null, workspace: box(94, 754), strip: true, sheet: box(408, 768),
  viewport: { width: 768, height: 900 }, ...over,
});

test('dockVerdict: an open or collapsed column beside the workspace passes', () => {
  assert.deepEqual(dockVerdict(docked()), { ok: true, reason: null });
  assert.deepEqual(dockVerdict(docked({ column: box(1400, 1440), workspace: box(94, 1386) })), { ok: true, reason: null });
  // Meeting at one edge, within half a pixel, is not an overlap.
  assert.deepEqual(dockVerdict(docked({ workspace: box(94, 1120.4) })), { ok: true, reason: null });
});

test('dockVerdict: from 1024px a missing column, a column over the content, or a strip fails', () => {
  assert.deepEqual(dockVerdict(docked({ column: null })), { ok: false, reason: 'no-column' });
  assert.deepEqual(dockVerdict(docked({ workspace: box(94, 1300) })), { ok: false, reason: 'overlaps-workspace' });
  assert.deepEqual(dockVerdict(docked({ strip: true })), { ok: false, reason: 'strip-when-docked' });
  assert.deepEqual(dockVerdict(docked({ width: 1024, column: null })), { ok: false, reason: 'no-column' });
});

test('dockVerdict: below 1024px a right sheet on a tablet and a bottom sheet on a phone pass', () => {
  assert.deepEqual(dockVerdict(narrow()), { ok: true, reason: null });
  const phone = { width: 390, workspace: box(10, 380), sheet: box(0, 390, 300, 788), viewport: { width: 390, height: 844 } };
  assert.deepEqual(dockVerdict(narrow(phone)), { ok: true, reason: null });
});

test('dockVerdict: below 1024px a column, no strip, an unopened or an off-screen sheet fails, first rule first', () => {
  assert.deepEqual(dockVerdict(narrow({ column: box(448, 768) })), { ok: false, reason: 'docked-below-1024' });
  assert.deepEqual(dockVerdict(narrow({ strip: false, sheet: null })), { ok: false, reason: 'no-strip' });
  assert.deepEqual(dockVerdict(narrow({ sheet: null })), { ok: false, reason: 'sheet-not-opened' });
  assert.deepEqual(dockVerdict(narrow({ sheet: box(408, 800) })), { ok: false, reason: 'sheet-off-screen' });
  assert.deepEqual(dockVerdict(narrow({ sheet: box(408, 768, 0, 960) })), { ok: false, reason: 'sheet-off-screen' });
  assert.deepEqual(dockVerdict(narrow({ sheet: box(408.2, 768.4) })), { ok: true, reason: null });
});

test('DOCK_MIN_WIDTH docks at 1440 only of the three widths, and every reason names its element', () => {
  assert.equal(DOCK_MIN_WIDTH, 1024);
  assert.deepEqual(FULL_WIDTHS.filter((width) => width >= DOCK_MIN_WIDTH), [1440]);
  assert.deepEqual(Object.keys(DOCK_SELECTORS).sort(), ['docked-below-1024', 'no-column', 'no-strip', 'overlaps-workspace',
    'sheet-not-opened', 'sheet-off-screen', 'strip-when-docked']);
  assert.ok(Object.values(DOCK_SELECTORS).every((selector) => selector.length > 0));
});
```

- [ ] **Step 2: Run them to verify they fail**

```bash
node --test <wt>/frontend/scripts/layout-audit-lib.test.mjs
```

Expected: FAIL. `dockVerdict`, `DOCK_MIN_WIDTH` and `DOCK_SELECTORS` are not exported, ROUTES still lists `/analytics`, and CHECKS has no `'dock'`.

- [ ] **Step 3: Implement the lib half**

In `frontend/scripts/layout-audit-lib.mjs`, replace the `ROUTES` comment and constant with:

```js
/** Every route and tab (29) on the v202 paths (spec v202 §2): the old names are redirects and are
 *  not visited. `:id` is a trade id, `:plan` an open (else pending) trade's id, `:symbol` a
 *  watchlist symbol with trades, `:date` the day a closed trade closed -- resolved from the API at
 *  run time. A route or tab added to the app is added here in the same commit. */
export const ROUTES = Object.freeze([
  '/dashboard',
  '/trades', '/trades/:id', '/trades/:id?tab=why', '/trades/:id?tab=chart', '/trades/:id?tab=journal',
  '/trades/calendar', '/trades/calendar/:date', '/trades/cancels',
  '/plans/:plan',
  '/insights/analytics', '/insights/analytics?tab=attribution', '/insights/analytics?tab=execution',
  '/insights/analytics?tab=edge', '/insights/analytics?tab=pipeline', '/insights/analytics?tab=tuning',
  '/insights/analytics?tab=partials',
  '/insights/research', '/insights/reports', '/insights/reports?tab=gates',
  '/watchlist', '/watchlist/:symbol',
  '/risk',
  '/system', '/system?tab=logs', '/system?tab=scan', '/system?tab=providers', '/system/versions',
  '/ui',
]);
```

Change `CHECKS` to `Object.freeze(['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline', 'vcenter', 'hint', 'rail-label', 'dock'])`.

After `railLabelVerdict`, add:

```js
/** The width the Live dock docks from (ui/breakpoints.ts md, DockState.docked). Below it the live
 *  strip opens the dock as a sheet (spec v202 §3). */
export const DOCK_MIN_WIDTH = 1024;
/** Sub-pixel slack: rects meeting at a shared edge, or a sheet at -0.4px, are rounding, not a defect. */
const DOCK_EDGE_SLACK_PX = 0.5;

const overlapPx = (a, b) => Math.min(a.right, b.right) - Math.max(a.left, b.left);
const outsideViewport = (r, v) => r.left < -DOCK_EDGE_SLACK_PX || r.top < -DOCK_EDGE_SLACK_PX
  || r.right > v.width + DOCK_EDGE_SLACK_PX || r.bottom > v.height + DOCK_EDGE_SLACK_PX;
const isDocked = (f) => f.width >= DOCK_MIN_WIDTH;

/** One rule per reason, in the order they are judged; the first that fails is the finding. */
const DOCK_RULES = Object.freeze([
  ['no-column', (f) => isDocked(f) && !f.column],
  ['overlaps-workspace', (f) => isDocked(f) && Boolean(f.workspace) && overlapPx(f.column, f.workspace) > DOCK_EDGE_SLACK_PX],
  ['strip-when-docked', (f) => isDocked(f) && f.strip],
  ['docked-below-1024', (f) => !isDocked(f) && Boolean(f.column)],
  ['no-strip', (f) => !isDocked(f) && !f.strip],
  ['sheet-not-opened', (f) => !isDocked(f) && !f.sheet],
  ['sheet-off-screen', (f) => !isDocked(f) && outsideViewport(f.sheet, f.viewport)],
]);

/** The element each dock finding points at (layout-audit.mjs prints it as the selector). */
export const DOCK_SELECTORS = Object.freeze({
  'no-column': 'aside.live-column',
  'overlaps-workspace': 'aside.live-column',
  'strip-when-docked': 'sb-live-strip',
  'docked-below-1024': 'aside.live-column',
  'no-strip': 'sb-live-strip',
  'sheet-not-opened': 'sb-live-sheet [role=dialog]',
  'sheet-off-screen': 'sb-live-sheet [role=dialog]',
});

/**
 * The dock check's verdict (spec v202 §8 "Layout", v203) on one page's measured facts:
 * `{ width, column, workspace, strip, sheet, viewport }`. `column` is aside.live-column's rect,
 * `workspace` main.workspace's content box, `strip` whether the live strip shows, `sheet` the opened
 * sheet dialog's rect (null when none opened); rects are {left, right, top, bottom} or null. Runs in
 * Node on the measured numbers, never shipped into the page.
 */
export function dockVerdict(facts) {
  const broken = DOCK_RULES.find(([, fails]) => fails(facts));
  return broken ? { ok: false, reason: broken[0] } : { ok: true, reason: null };
}
```

- [ ] **Step 4: Run the lib tests to verify they pass**

```bash
node --test <wt>/frontend/scripts/layout-audit-lib.test.mjs
```

Expected: PASS, every test including the checked-in allow-list test (its `entries` is empty, so no entry names an old route).

- [ ] **Step 5: Add the browser half**

In `frontend/scripts/layout-audit.mjs`, add `DOCK_MIN_WIDTH, DOCK_SELECTORS, dockVerdict` to the import from `./layout-audit-lib.mjs`. In the header comment, change "reports nine checks" to "reports ten checks" and add under the `rail-label` lines:

```js
 *   dock       from 1024px the docked Live column (aside.live-column) missing, over main.workspace's
 *              content box, or a live strip beside it; below 1024px a docked column, no live strip,
 *              or a sheet that a tap on the strip does not open inside the viewport (spec v202 §8).
 *              Never allowed.
```

After `auditRailLabels`, add:

```js
/** How long the opened live sheet gets for its entrance before it is measured. */
const SHEET_SETTLE_MS = 400;

/** Runs inside the page (page.evaluate): the dock check's DOM facts. Self-contained. */
function measureDock() {
  const rect = (el) => {
    const r = el?.getBoundingClientRect();
    return r && r.width > 0 && r.height > 0 ? { left: r.left, right: r.right, top: r.top, bottom: r.bottom } : null;
  };
  const workspace = document.querySelector('main.workspace');
  const outer = rect(workspace);
  const s = workspace ? getComputedStyle(workspace) : null;
  const content = outer && s ? {
    ...outer,
    left: outer.left + parseFloat(s.borderLeftWidth) + parseFloat(s.paddingLeft),
    right: outer.right - parseFloat(s.borderRightWidth) - parseFloat(s.paddingRight),
  } : null;
  const root = document.documentElement;
  return {
    column: rect(document.querySelector('aside.live-column')),
    workspace: content,
    strip: Boolean(rect(document.querySelector('sb-live-strip button.live-strip'))),
    viewport: { width: root.clientWidth, height: root.clientHeight },
  };
}

/** Runs inside the page: the open live sheet's dialog rect, or null. Self-contained. */
function measureSheet() {
  const r = document.querySelector('sb-live-sheet [role=dialog]')?.getBoundingClientRect();
  return r && r.width > 0 && r.height > 0 ? { left: r.left, right: r.right, top: r.top, bottom: r.bottom } : null;
}

/** Tap the live strip, measure the sheet it opens, then close it with Escape. */
async function openSheet(page, width) {
  try {
    await page.locator('sb-live-strip button.live-strip').tap({ timeout: 2000 });
  } catch (error) {
    console.error(`  live strip @${width}: cannot tap (${String(error).split('\n')[0]})`);
    return null;
  }
  await page.waitForTimeout(SHEET_SETTLE_MS);
  const sheet = await page.evaluate(measureSheet);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(SHEET_SETTLE_MS);
  return sheet;
}

/**
 * The dock check (spec v202 §8 "Layout"): from DOCK_MIN_WIDTH the docked column sits beside the
 * workspace, never over its content; below it the live strip opens the dock as a sheet inside the
 * viewport. Judged by dockVerdict on measured facts.
 */
async function auditDock(page, width) {
  const facts = { ...(await page.evaluate(measureDock)), width, sheet: null };
  if (width < DOCK_MIN_WIDTH && facts.strip) facts.sheet = await openSheet(page, width);
  const verdict = dockVerdict(facts);
  if (verdict.ok) return [];
  return [{ check: 'dock', selector: DOCK_SELECTORS[verdict.reason], text: '', detail: `live dock ${verdict.reason} at ${width}px` }];
}
```

In `auditWidth`, after `const rails = await auditRailLabels(page, width);`, add `const docks = await auditDock(page, width);`. Change the next two lines to `findings.push(...[...hints, ...rails, ...docks].map((f) => ({ route, width, ...f })));` and `console.error(`${route} @${width}: ${raw.length + hints.length + rails.length + docks.length} raw finding(s)`);`.

- [ ] **Step 6: Verify the script parses and the lib still passes**

```bash
node --check <wt>/frontend/scripts/layout-audit.mjs
node --test <wt>/frontend/scripts/layout-audit-lib.test.mjs
```

Expected: no syntax error, PASS. `complexity_gate.py` measures Python only, so these `.mjs` functions are held under 15 by hand. Complexity: `dockVerdict` 2, `auditDock` 3, `openSheet` 2, `measureDock` 5. Each rule lambda is at most 3.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add frontend/scripts/layout-audit-lib.mjs frontend/scripts/layout-audit-lib.test.mjs frontend/scripts/layout-audit.mjs
git -C <wt> commit -m "feat(v203): layout audit visits the v202 paths and checks the Live dock

ROUTES moves to the new paths (29; the old names are redirects). A new
dock check fails a docked column over the workspace's content box from
1024px, and below it a docked column, a missing strip, or a sheet the
strip does not open inside the viewport.

Retired: the old ROUTES test. Moved: CHECKS gains dock.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V203-10b: Layout audit run at 390 / 768 / 1440 and its results

**Model:** sonnet — a real audit run against the replica, reading screenshots against the spec, and a written result.

The second half of ledger task V203-10, split to stay under 20 KB. It runs straight after V203-10, and V203-11 follows it.

**Files:**
- Create: `docs/superpowers/results/2026-10-29-v203-layout-audit.md`
- Modify only when the run finds something: the owning task's files from the index ledger (the finding's element names the task), never the allow-list.

**Interfaces:**
- Consumes: V203-10's audit (`ROUTES` on the v202 paths, `CHECKS` with `'dock'`), and the finished shell from V203-1 … V203-9b.
- Produces: the results file. V203-11 checks that it exists and records exit 0.

- [ ] **Step 1: Run the audit at three widths**

Run `/replicate-prod-db` first if this session has not (the one shared `swing-db` container): `pickIds` needs a closed trade, an open or pending plan and a symbol with trades. Then `npm --prefix <wt>/frontend run build`, serve it with `python <wt>/admin_ui.py` on `.env`'s own settings (the credentials are loaded inside the processes and never printed), and sign in once with `node <wt>/frontend/scripts/browse.mjs login --base http://localhost:1234`. Then run:

```bash
node <wt>/frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440
```

Expected: exit 0, with every check count at 0 (`overflow=0 … rail-label=0 dock=0`). Any finding is fixed in the task that owns the element (the index ledger names it), then this run repeats. Nothing is added to the allow-list: a shell finding is never a third-party internal.

- [ ] **Step 2: Write the results file**

Create `docs/superpowers/results/2026-10-29-v203-layout-audit.md` from the run, with every figure copied from `<out>/audit.json` and the console summary line. Its first line is the title `# v203 UI shell cockpit — results: layout audit`, then a blank line, then:

```markdown
**Spec:** [2026-10-29-v202-ui-shell-cockpit-design.md](../specs/2026-10-29-v202-ui-shell-cockpit-design.md) §8 "Layout"
**Plan:** [2026-10-29-v203-ui-shell-cockpit-dock_0-index.md](../plans/2026-10-29-v203-ui-shell-cockpit-dock_0-index.md) — V203-10, V203-10b

## Run

- Branch and commit: `<branch>` @ `<short sha>`; base `http://localhost:1234` on the replica synced `<date>`.
- Command: `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440`; exit code `<0>`.
- Routes: 29 (the v202 paths), at 390, 768 and 1440.

## Findings per check

| Check | 390 | 768 | 1440 |
|---|---|---|---|
| overflow | | | |
| offscreen | | | |
| clipped | | | |
| tap | | | |
| text | | | |
| baseline | | | |
| vcenter | | | |
| hint | | | |
| rail-label | | | |
| dock | | | |

Allowed: none. Stale allow-list entries: none.

## Read off the screenshots

- 1440: the rail is 80 px with six labelled entries, System at the foot. The bar reads wordmark · divider · breadcrumb … killswitch · search · avatar. The dock is open (320 px) on `/dashboard` and `/risk`, and it is the 40 px edge tab elsewhere.
- 768: the 80 px rail. The live strip sits under the tape; a tap opens the right-hand sheet.
- 390: no rail. The diamond and wordmark lead the bar, the strip sits under it, and the sheet rises from the bottom above the tab bar.

## Notes

- (Any fix made during the run: the finding, the owning task, the commit.)
```

Fill each table cell with that check's count at that width (0 on a clean run) and the bracketed values from the run. Replace each bullet under "Read off the screenshots" with what the screenshots show; where it differs from the text above, write what you saw and fix the shell first.

- [ ] **Step 3: Commit**

```bash
git -C <wt> add docs/superpowers/results/2026-10-29-v203-layout-audit.md
git -C <wt> commit -m "docs(v203): layout audit results at 390, 768 and 1440

All 29 v202 routes, ten checks, the dock check included: <the summary
line, e.g. exit 0, every count 0>.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

A fix made during the run is committed on its own first, under its owning task's files, as `fix(v203): <the finding>`.

### Task V203-10c: Retire the shell's orphaned chips; document the rail-label and dock checks

**Model:** sonnet — usage-driven deletion (keep anything still referenced) plus a doc change with its Codex mirror.

Written by the controller from part 3's open item: after V203-9, `sb-freshness-chip` and `sb-connection-status` no longer render in the shell, and `docs/claude/ui-design.md` (with its `AGENTS.md` mirror) still describes the hint-based `rail-label` check and knows nothing of the `dock` check.

**Files:**
- Modify or delete: `frontend/src/app/shell/freshness-chip.ts`, `freshness-chip.spec.ts`, `connection-status.ts`, `connection-status.spec.ts`
- Modify: `frontend/src/app/shell/scan-progress.ts` (doc comment only, line 37 names `sb-connection-status`)
- Modify: `docs/claude/ui-design.md` (§ the layout-audit paragraph), `AGENTS.md` (its condensed mirror, same commit)

**Interfaces:**
- Consumes: V203-9's shell (the cluster holds only `sb-alarm-chip` and `sb-killswitch-chip`), V203-10's `dock` check and V203-1b's visible-label `rail-label` check.
- Produces: no new symbol. `scanAge` (exported from `freshness-chip.ts`, imported by `shell/live/live-state.ts` since V203-3) must keep working from wherever it lives.

- [ ] **Step 1: Find what still uses each chip**

```bash
git -C <wt> grep -n -E "sb-freshness-chip|FreshnessChip|sb-connection-status|ConnectionStatus|from '\./freshness-chip'|from '\.\./freshness-chip'|connection-status'" -- frontend/src
```

Rule: a component class with no template or import user left outside its own spec is deleted, with its spec cases. A file that still exports something used (`scanAge`, any shared type) keeps that export and loses only the dead component. If `freshness-chip.ts` would hold only `scanAge`, leave it there: moving it would churn `live-state.ts` for nothing.

- [ ] **Step 2: Delete the dead parts and fix the comment**

Delete per Step 1. Reword `scan-progress.ts:37` so it no longer names a component that is gone (for example "Like the shell's other status pieces"). No behaviour changes.

Run: `npm --prefix <wt>/frontend test -- --include src/app/shell` and `npm --prefix <wt>/frontend run build`.
Expected: both green; no import of a deleted symbol remains.

- [ ] **Step 3: Document the two audit checks**

In `docs/claude/ui-design.md`, the layout-audit paragraph (it starts "`node frontend/scripts/layout-audit.mjs`… must exit 0 at 390, 768 and 1440"):
- Replace the `(rail-label, v195)` sentence with the v203 rule: every rail entry (`nav.rail a.rail-link`, at 768 and 1440) has an accessible name and a visible `.rail-label` (the labelled rail has no hint per link).
- Add `(dock, v203)`: at 1024 px and wider the docked `aside.live-column` never intersects `main.workspace`'s content box, and at smaller widths the live sheet stays inside the viewport.

In `AGENTS.md`, update the matching condensed sentence (it ends "…its `rail-label` check fails an icon-rail entry with no accessible name or no visible label on keyboard focus; fix either, never allow it)") to the same two rules, condensed.

Run: `python -m pytest tests/hooks/test_codex_mirror.py -q`
Expected: pass.

- [ ] **Step 4: Commit (two scoped commits)**

```bash
git -C <wt> add frontend/src/app/shell/freshness-chip.ts frontend/src/app/shell/freshness-chip.spec.ts frontend/src/app/shell/connection-status.ts frontend/src/app/shell/connection-status.spec.ts frontend/src/app/shell/scan-progress.ts
git -C <wt> commit -m "refactor(v203): retire the shell chips the live dock replaced

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <wt> add docs/claude/ui-design.md AGENTS.md
git -C <wt> commit -m "docs(v203): the layout audit's rail-label and dock checks, with the Codex mirror

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Stage only the files Step 1 actually touched (`git add` of a deleted path records the deletion).

### Task V203-11: Full suite once (the bump is `/close-out`'s)

**Model:** haiku — runs the gates once and routes any failure back to its owning task; no design judgement.

**Files:**
- Modify only when a check below fails: the owning task's files from the index ledger (V203-1 … V203-10b, the `b` rows included), never a file outside the ledger. No new files. `VERSION.json` is not touched: `/close-out` resolves `Bump: ui minor` and regenerates `swingbot/admin/version_history.json`.

**Interfaces:**
- Consumes: every task of v203. The rail (V203-1, V203-1b), `LiveStore` (V203-2), the live-state rules (V203-3), `DockState` (V203-3b), the four dock sections (V203-4 … V203-6b), the dock, edge tab, strip and sheet (V203-7 … V203-8b), the top bar and alarm chip (V203-9, V203-9b) and the layout audit and its run (V203-10, V203-10b).
- Produces: the green full-suite verdict line for `/close-out`.

- [ ] **Step 1: Check the branch is complete and clean**

Run: `git -C <wt> status --porcelain` and `git -C <wt> log --oneline main..HEAD`
Expected: status prints nothing. The log shows at least one commit for each of V203-1, V203-1b, V203-2, V203-3, V203-3b, V203-4, V203-5, V203-5b, V203-6, V203-6b, V203-7, V203-7b, V203-8, V203-8b, V203-9, V203-9b, V203-10 and V203-10b (19 tasks; more if a reviewer fix-up landed). `docs/superpowers/results/2026-10-29-v203-layout-audit.md` exists and records exit 0.

- [ ] **Step 2: Sync the database replica**

The Python full suite includes the Postgres tier. If this session has not synced it yet, the controller runs `/replicate-prod-db` into the one shared `swing-db` container first. No per-task container or database.

- [ ] **Step 3: Complexity and plan gates**

Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: exit 0. This plan changes no Python, so the baseline is untouched.

Run: `python <wt>/scripts/dev/plan_lint.py <wt>/docs/superpowers/plans/2026-10-29-v203-ui-shell-cockpit-dock_0-index.md`
Expected: `PASS`.

- [ ] **Step 4: SPA lint, build and the whole SPA suite**

Run: `npm --prefix <wt>/frontend run lint`
Expected: exit 0. No `eslint-suppressions.json` entry is left for `NAV_GROUPS` (V203-1b deleted it).

Run: `npm --prefix <wt>/frontend run build`
Expected: exit 0, no new warnings (in particular no budget warning for the new `shell/live/` components).

Run: `npm --prefix <wt>/frontend test -- --watch=false`
Expected: every co-located `*.spec.ts` passes, `0 failed`. That covers `shell.spec.ts`, the `shell/live/` specs, `alarm-chip.spec.ts`, `stores/live.store.spec.ts`, `api/api-client.spec.ts`, `ui/hit-area.spec.ts` and `ui/motion-css.spec.ts`.

Run: `node --test <wt>/frontend/scripts/layout-audit-lib.test.mjs`
Expected: PASS.

- [ ] **Step 5: Python full suite once**

Dispatch the `test-runner` subagent with: `python <wt>/scripts/dev/testrun.py full`
Expected: `0 failed` and `0 xfailed`. A changed pass count is not a failure (`testing-cost.md`). This plan adds no Python test. The run still guards `tests/admin/test_spa_serving.py` (the route parity v202 set up) and the Codex mirror.

- [ ] **Step 6: On a failure, fix in the owning task and re-run alone**

Find the task whose ledger row lists the failing file. Fix it there, then re-run only that test: `npm --prefix <wt>/frontend test -- --watch=false --include <spec path relative to frontend/>`, `node --test <file>`, or `python <wt>/scripts/dev/testrun.py file <test path>`. Never re-run the whole suite, and never edit a file outside the ledger. If a fix crosses two tasks' files, stop and report it to the controller. A fix that changes markup or CSS repeats V203-10's audit run, `node <wt>/frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440`, and updates its results file.

- [ ] **Step 7: Record the verdict**

Append one line to `.superpowers/sdd/progress.md` (append only, never rewrite):

```text
2026-10-29 v203 V203-11 full suite: <passed> passed, 0 failed, 0 xfailed (<duration>); SPA <spec count> specs green; audit exit 0 on <wt branch> @ <short sha>
```

- [ ] **Step 8: Commit (only if Step 6 changed files)**

```bash
git -C <wt> add <each fixed path, explicitly>
git -C <wt> commit -m "fix(v203): <what the full suite caught>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

With no fix, there is nothing to commit. The controller runs `/close-out`.
