# v195 — Graphite, Part 6b: the top-bar cluster

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-17:" -A 400 <this file>`.

**Scope of this part (V195-17; V195-18 is in Part 6c, `2026-10-25-v195-graphite-frontend-redesign_6c-phone-shell.md`):** split from Part 6 for the 1500-line cap, unchanged. V195-17 fills the top bar's right cluster: the killswitch and freshness chips (every device), the scan progress hanging from the bar, the clock, and the profile menu with the Density control; the tape becomes a strip under the bar. It runs after V195-16 (Part 6) and before V195-18: all three rewrite the same four shell files.

**Where commands run.** `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`; `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/`. Frontend runs through `npm --prefix "$WT/frontend" ...`.

**The state earlier tasks leave.** Part 6's "The state earlier tasks leave" list covers everything up to V195-15, and its rule on `title` in new templates binds the new components here too (no `title` binding in any `.ts` template; an icon inside a link sits in an `aria-hidden` span). On top of that, V195-16 left the shell as its **Interfaces** block in Part 6 describes: `nav.rail` with `a.rail-link` entries and anchored hints, `header.topbar` (sticky, 40px, 48px in the touch block) leading with `sb-breadcrumb.topbar-lead`, then `div.topbar-tape`, `div.status-cluster` (`sb-connection-status`, `span.clock`) and `sb-profile-menu`; the killswitch strip; `main.workspace` with `sb-scan-progress` at its top; no `<h1>`; no `viewport` or `titles` field in `shell.ts`; and the new shell spec helpers `Blank`, `shellProviders(routes)` and `readSource(path)` after `FakeEventStream` in `shell.spec.ts`. Re-read each file before editing it; every step names its edit by symbol or exact string, never by line number.

---

# Phase 3 — Shell (rebuilt, continued)

### Task V195-17: Top-bar right cluster: killswitch chip (all devices, links to `/risk`), freshness chip (all devices), scan progress, clock, profile menu with Density; tape strip under the top bar
**Model:** sonnet — two small presentational components, one store field and one menu row, then a re-seat of existing shell parts; the care is in the chips showing nothing before their facts arrive and in the moved pins (tape, killswitch strip, scan progress) asserting the new places, not dropped.

**Files:**
- Create: `frontend/src/app/shell/killswitch-chip.ts`
- Create: `frontend/src/app/shell/killswitch-chip.spec.ts`
- Create: `frontend/src/app/shell/freshness-chip.ts`
- Create: `frontend/src/app/shell/freshness-chip.spec.ts`
- Modify: `frontend/src/app/stores/connection.store.ts` (`ConnectionStateSlice.botLastSuccess`; its initial value; `refresh()`'s scan patch)
- Modify: `frontend/src/app/stores/connection.store.spec.ts` (two new cases in `describe('ConnectionStore', ...)`)
- Modify: `frontend/src/app/shell/profile-menu.ts` (imports; `DENSITY_OPTIONS`; class docblock; template: a Density row after the Motion row; styles; `density` input, `densityChanged` output, `densityOptions`, `onDensity`)
- Modify: `frontend/src/app/shell/profile-menu.spec.ts` (one new describe inside `describe('ProfileMenu', ...)`)
- Modify: `frontend/src/app/shell/shell.ts` (imports; `imports` array; `clock` becomes protected; new `density` field; `killswitchOn` becomes three-valued)
- Modify: `frontend/src/app/shell/shell.html` (the `div.main` block replaced)
- Modify: `frontend/src/app/shell/shell.css` (the `.topbar-tape` rules replaced by `.tape-strip` and the scan-progress anchor; `.status-cluster` pushed right; the phone block hides `.tape-strip`)
- Modify: `frontend/src/app/shell/shell.spec.ts` (four cases moved; one new describe)
- Modify: `frontend/src/app/shell/tape/tape.css` (one comment: the tape's flex parent is now the shell's `.tape-strip`)

**Interfaces:**
- Consumes: `DensityService` (`density: Signal<RowDensity>`, `set(d: RowDensity): void`), `RowDensity`, `DENSITY_STORAGE`, `DENSITY_PREF_KEY` (`ui/density.service.ts`, V195-6); `Segmented`, `SegmentOption` (`ui/segmented.ts`); `ScanStatus.bot_last_success` (`api/models.ts`, already in the payload `ConnectionStore.refresh()` reads); `ConnectionStore.botLastSeen`; `CLOCK` (`ui/clock.ts`, a `Signal<number>` ticking every 30s); the V195-16 shell markup (`header.topbar`, `sb-breadcrumb.topbar-lead`, `div.status-cluster`).
- Produces (V195-18 and V195-20 rely on these):
  - `KillswitchChip` (`sb-killswitch-chip`): `on = input<boolean | null>(null)`; renders nothing for `null`, else `a.chip.sb-hit[routerLink="/risk"]` reading `Armed` (killswitch off) or `Halted` (killswitch on, class `halted`), with `aria-label` `Killswitch off, trading armed. Open Risk` / `Killswitch on, trading halted. Open Risk`.
  - `FreshnessChip` (`sb-freshness-chip`): `at = input<string | null>(null)`, `now = input.required<number>()`; renders `Scan <age>` (the age in a `<time datetime>`) or `No scan yet`. `scanAge(at: string | null, now: number): string | null` (exported; `'just now'` under a minute, `'12m ago'`, `'3h ago'`, `'2d ago'`; `null` for a missing or unreadable time; never negative).
  - `ConnectionStore.botLastSuccess` (state signal, `string | null`, from `ScanStatus.bot_last_success`).
  - `ProfileMenu.density = input<RowDensity>('dense')`; `ProfileMenu.densityChanged = output<RowDensity>()`; the menu row `sb-segmented.density-control` labelled `Density` with segments `Dense`, `Comfortable`, and a `.menu-note` saying touch screens keep 44px rows.
  - Shell: `protected readonly density = inject(DensityService)`; `protected readonly clock` (was private); `killswitchOn = signal<boolean | null>(null)`.
  - Shell markup: `header.topbar` > `sb-breadcrumb.topbar-lead`, `div.status-cluster` (`sb-killswitch-chip`, `sb-freshness-chip`, `sb-connection-status`, `span.clock`), `sb-profile-menu`, `sb-scan-progress` (last child, hung from the bar's bottom edge); then `div.tape-strip` > `sb-tape`; then the killswitch strip; then `main.workspace` (no `sb-scan-progress` inside it any more). V195-20 inserts the palette trigger between `sb-breadcrumb` and `div.status-cluster`.

**What changes, and what is already there.** Spec Phase 3 puts the killswitch state and the data freshness in the top bar on every device: the killswitch control lives in Risk's page header (V195-25), and Scan health leaves the Risk page (§5.1, V195-23), so without these two chips a phone user could not see from anywhere that trading had stopped or that the bot had gone quiet. The shell already owns the killswitch boolean (`killswitchOn`, refetched on the `risk` event); it becomes three-valued so the chip says nothing until the first answer rather than claim "Armed". The freshness chip reads the bot's last successful tick (`ScanStatus.bot_last_success`, already fetched by `ConnectionStore.refresh()` but not kept), falling back to the last heartbeat (`botLastSeen`), and ages it against the shell's 30s `CLOCK` (plan decision 3). The scan progress bar moves from the top of the workspace into the bar, re-anchored by the shell's stylesheet to hang from the bar's bottom edge, so it shows on every route without ever reflowing one. The tape leaves the bar for a strip under it (behaviour unchanged, no new preference; `tape-prefs` still decides what shows). The profile menu gains a Density row beside Motion, writing through `DensityService` (`ui.density` in `localStorage`, `data-density` on `<html>`), with a note that the touch rules win on phones and tablets (§1.4). The engaged-killswitch strip stays: the chip is the state everywhere, the strip is the alarm.

- [ ] **Step 1: Write the failing chip tests**

Create `$WT/frontend/src/app/shell/killswitch-chip.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { KillswitchChip } from './killswitch-chip';

describe('KillswitchChip (v195 Phase 3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideRouter([])] });
  });

  function render(on: boolean | null): HTMLElement {
    const fixture = TestBed.createComponent(KillswitchChip);
    fixture.componentRef.setInput('on', on);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders nothing until the state is known, never a guessed "Armed"', () => {
    expect(render(null).innerHTML.replace(/<!--[\s\S]*?-->/g, '').trim()).toBe('');
  });

  it('reads Armed while trading runs, and links to Risk', () => {
    const chip = render(false).querySelector('a')!;
    expect(chip.textContent!.trim()).toBe('Armed');
    expect(chip.getAttribute('href')).toBe('/risk');
    expect(chip.classList).not.toContain('halted');
    expect(chip.getAttribute('aria-label')).toBe('Killswitch off, trading armed. Open Risk');
  });

  it('reads Halted when engaged: a word of its own, not only the loss colour', () => {
    const chip = render(true).querySelector('a')!;
    expect(chip.textContent!.trim()).toBe('Halted');
    expect(chip.classList).toContain('halted');
    expect(chip.getAttribute('href')).toBe('/risk');
    expect(chip.getAttribute('aria-label')).toBe('Killswitch on, trading halted. Open Risk');
  });

  it('pads its hit area for touch and explains itself without a title', () => {
    const chip = render(true).querySelector('a')!;
    expect(chip.classList).toContain('sb-hit');
    expect(chip.hasAttribute('title')).toBe(false);
  });
});
```

Create `$WT/frontend/src/app/shell/freshness-chip.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { FreshnessChip, scanAge } from './freshness-chip';

const NOW = Date.parse('2026-10-27T12:00:00Z');

describe('scanAge (v195 Phase 3)', () => {
  it.each([
    ['2026-10-27T11:59:40Z', 'just now'],
    ['2026-10-27T11:59:00Z', '1m ago'],
    ['2026-10-27T11:48:00Z', '12m ago'],
    ['2026-10-27T11:00:00Z', '1h ago'],
    ['2026-10-27T09:00:00Z', '3h ago'],
    ['2026-10-25T12:00:00Z', '2d ago'],
  ])('%s reads %s', (at, text) => {
    expect(scanAge(at, NOW)).toBe(text);
  });

  it('is null for a missing or unreadable time', () => {
    expect(scanAge(null, NOW)).toBeNull();
    expect(scanAge('', NOW)).toBeNull();
    expect(scanAge('not a date', NOW)).toBeNull();
  });

  it('never reads a time from the future as negative', () => {
    expect(scanAge('2026-10-27T12:05:00Z', NOW)).toBe('just now');
  });
});

describe('FreshnessChip (v195 Phase 3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(at: string | null, now = NOW): HTMLElement {
    const fixture = TestBed.createComponent(FreshnessChip);
    fixture.componentRef.setInput('at', at);
    fixture.componentRef.setInput('now', now);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  const text = (el: HTMLElement) => el.textContent!.replace(/\s+/g, ' ').trim();

  it('reads the age of the last scan tick', () => {
    const el = render('2026-10-27T11:48:00Z');
    expect(text(el)).toBe('Scan 12m ago');
    expect(el.querySelector('time')!.getAttribute('datetime')).toBe('2026-10-27T11:48:00Z');
  });

  it('says so when the bot has never reported a tick', () => {
    const el = render(null);
    expect(text(el)).toBe('No scan yet');
    expect(el.querySelector('time')).toBeNull();
    expect(el.querySelector('.chip')!.classList).toContain('unknown');
  });

  it('ages as the clock moves, with no timer of its own', () => {
    const fixture = TestBed.createComponent(FreshnessChip);
    fixture.componentRef.setInput('at', '2026-10-27T11:48:00Z');
    fixture.componentRef.setInput('now', NOW);
    fixture.detectChanges();
    fixture.componentRef.setInput('now', NOW + 60 * 60_000);
    fixture.detectChanges();
    expect(text(fixture.nativeElement as HTMLElement)).toBe('Scan 1h ago');
  });

  it('carries no title', () => {
    expect(render('2026-10-27T11:48:00Z').querySelector('[title]')).toBeNull();
  });
});
```

- [ ] **Step 2: Write the failing store and menu tests**

1. `$WT/frontend/src/app/stores/connection.store.spec.ts`: inside `describe('ConnectionStore', ...)`, after the case `it('leaves bot health null when the bot has never completed a tick', ...)`, add:

```ts

  it('keeps the last successful tick for the freshness chip (v195)', () => {
    tick();
    backend.expectOne('/api/v1/health').flush(HEALTH);
    backend
      .expectOne('/api/v1/system/scan')
      .flush({ ...SCAN, bot_last_success: '2026-08-14T08:55:00Z' });

    expect(store.botLastSuccess()).toBe('2026-08-14T08:55:00Z');
  });

  it('starts with no last successful tick, which is not the same as an old one', () => {
    expect(store.botLastSuccess()).toBeNull();
    tick();
    backend.expectOne('/api/v1/health').flush(HEALTH);
    backend.expectOne('/api/v1/system/scan').flush({ ...SCAN, bot_last_success: null });
    expect(store.botLastSuccess()).toBeNull();
  });
```

2. `$WT/frontend/src/app/shell/profile-menu.spec.ts`: inside `describe('ProfileMenu', ...)`, after the closing `});` of `describe('Motion control (v168 §1)', ...)`, add:

```ts

  describe('Density control (v195 §1.4)', () => {
    const control = () => el.querySelector('sb-segmented.density-control');
    const segments = () =>
      Array.from(el.querySelectorAll<HTMLButtonElement>('sb-segmented.density-control .segment'));

    it('offers Dense and Comfortable under the label "Density"', () => {
      openMenu();
      expect(control()!.querySelector('[role=group]')!.getAttribute('aria-label')).toBe('Density');
      expect(segments().map((b) => b.textContent!.trim())).toEqual(['Dense', 'Comfortable']);
    });

    it('defaults to Dense and marks the density it is given', () => {
      openMenu();
      expect(segments().find((b) => b.getAttribute('aria-pressed') === 'true')!.textContent!.trim()).toBe('Dense');
      fixture.componentRef.setInput('density', 'comfortable');
      fixture.detectChanges();
      expect(segments().find((b) => b.getAttribute('aria-pressed') === 'true')!.textContent!.trim()).toBe('Comfortable');
    });

    it('emits the chosen density and keeps the menu open', () => {
      const chosen: string[] = [];
      fixture.componentInstance.densityChanged.subscribe((density) => chosen.push(density));
      openMenu();
      segments()[1].click();
      fixture.detectChanges();
      expect(chosen).toEqual(['comfortable']);
      expect(menu()).not.toBeNull();
    });

    it('says the touch rules win, so a phone or tablet user is not left guessing', () => {
      openMenu();
      expect(el.querySelector('.density-row .menu-note')!.textContent!.trim())
        .toBe('Desktop only: touch screens keep 44px rows.');
    });
  });
```

- [ ] **Step 3: Write the failing shell tests**

In `$WT/frontend/src/app/shell/shell.spec.ts`:

1. Imports. After `import { CLOCK } from '../ui/clock';` add `import { DENSITY_STORAGE } from '../ui/density.service';`.

2. Inside `describe('shell navigation', ...)`, replace the case `it('carries the tape inside the top bar row, not beneath it', ...)` with:

```ts
  it('runs the tape as a strip under the top bar, not inside it (v195 Phase 3)', () => {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;

    const main = el.querySelector('.main') as HTMLElement;
    expect(Array.from(main.children).map((c) => c.tagName.toLowerCase()))
      .toEqual(['header', 'div', 'main']);
    expect(main.children[1].classList).toContain('tape-strip');
    expect(main.querySelector(':scope > .tape-strip > sb-tape')).not.toBeNull();
    expect(el.querySelector('header.topbar sb-tape')).toBeNull();
  });
```

3. In the case `it('renders the killswitch as a full-width strip below the bar, only when engaged', ...)`, replace its last line `expect(strip.previousElementSibling?.tagName.toLowerCase()).toBe('header');` with `expect(strip.previousElementSibling?.classList.contains('tape-strip')).toBe(true);`.

4. Replace the case `it('overlays the scan progress strip on the workspace rather than reflowing it', ...)` with:

```ts
  it('hangs the scan progress from the top bar, out of the flow (v195 Phase 3)', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;

    const strip = el.querySelector('sb-scan-progress')!;
    expect(el.querySelectorAll('sb-scan-progress')).toHaveLength(1);
    // In the sticky bar, so it shows on every route; the bar's last child,
    // so it paints over its own siblings' edge rather than between them.
    expect(strip.parentElement?.matches('header.topbar')).toBe(true);
    expect(strip.nextElementSibling).toBeNull();
    expect(el.querySelector('.workspace sb-scan-progress')).toBeNull();
    // Absolute (its own :host), re-anchored under the bar's bottom edge: it
    // never takes layout, so a scan every few minutes never shunts the page.
    const css = readSource('src/app/shell/shell.css');
    expect(css.match(/^\.topbar > sb-scan-progress \{[^}]*\}/m)?.[0]).toContain('inset: 100% 0 auto 0;');
  });
```

5. In the case `it('drops the clock and the tape on a phone before it lets the bar overflow', ...)` (V195-16), replace `\.topbar-tape` in its second regex with `\.tape-strip`, so the line reads `expect(css).toMatch(/max-width:\s*639px[\s\S]*\.tape-strip[\s\S]*display:\s*none/);`.

6. At the end of the file, append:

```ts

describe('shell top-bar cluster (v195 Phase 3)', () => {
  const NOW = Date.parse('2026-10-27T12:00:00Z');
  const html = document.documentElement;
  let stored: Map<string, string>;

  beforeEach(() => {
    stored = new Map();
    TestBed.configureTestingModule({
      providers: [
        ...shellProviders(),
        { provide: DENSITY_STORAGE, useValue: { get: (key: string) => stored.get(key) ?? null, set: (key: string, value: string) => stored.set(key, value) } },
      ],
    });
    TestBed.overrideProvider(CLOCK, { useValue: signal(NOW) });
  });

  afterEach(() => {
    delete html.dataset['density'];
  });

  async function mount() {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    await fixture.whenStable();
    return { fixture, el: fixture.nativeElement as HTMLElement, backend: TestBed.inject(HttpTestingController) };
  }

  async function settle(fixture: { detectChanges(): void; whenStable(): Promise<unknown> }): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  const scanStatus = (overrides: Record<string, unknown>) => ({
    pending: false, triggered_at: null, paused: false, paused_at: null, running: false,
    bot_alive: true, bot_last_seen: '2026-10-27T11:57:00Z', bot_healthy: true,
    bot_last_success: '2026-10-27T11:48:00Z', bot_consecutive_failures: 0,
    bot_session_active: true, bot_scan_paused: false, progress: null, ...overrides,
  });

  it('puts the killswitch and freshness chips in the cluster, hidden at no width', async () => {
    const { el } = await mount();
    const cluster = el.querySelector('header.topbar > .status-cluster')!;
    expect(cluster.querySelector('sb-killswitch-chip')).not.toBeNull();
    expect(cluster.querySelector('sb-freshness-chip')).not.toBeNull();
    expect(cluster.querySelector('sb-connection-status')).not.toBeNull();
    const css = readSource('src/app/shell/shell.css').replace(/\/\*[\s\S]*?\*\//g, '');
    expect(css).not.toMatch(/(sb-killswitch-chip|sb-freshness-chip|\.status-cluster)[^{}]*\{[^}]*display:\s*none/);
  });

  it('shows no killswitch state until the risk endpoint answers, then the answer', async () => {
    const { fixture, el, backend } = await mount();
    const chip = () => el.querySelector('sb-killswitch-chip a');
    expect(chip()).toBeNull();
    for (const request of backend.match((r) => r.url.endsWith('/risk/killswitch'))) {
      request.flush({ killswitch: { on: true } });
    }
    await settle(fixture);
    expect(chip()!.textContent!.trim()).toBe('Halted');
    expect(el.querySelector('.killswitch-strip')).not.toBeNull();
  });

  it('ages the freshness chip from the last successful tick, else the last heartbeat', async () => {
    const { fixture, el, backend } = await mount();
    const text = () => el.querySelector('sb-freshness-chip')!.textContent!.replace(/\s+/g, ' ').trim();
    expect(text()).toBe('No scan yet');
    for (const request of backend.match((r) => r.url.endsWith('/system/scan'))) {
      request.flush(scanStatus({}));
    }
    await settle(fixture);
    expect(text()).toBe('Scan 12m ago');

    // A bot that has never completed a tick still has a heartbeat age.
    (TestBed.inject(EventStream) as unknown as FakeEventStream).emit('bot');
    await settle(fixture);
    for (const request of backend.match((r) => r.url.endsWith('/system/scan'))) {
      request.flush(scanStatus({ bot_last_success: null }));
    }
    await settle(fixture);
    expect(text()).toBe('Scan 3m ago');
  });

  it('writes ui.density and data-density from the profile menu', async () => {
    const { fixture, el } = await mount();
    expect(html.dataset['density']).toBe('dense');
    el.querySelector<HTMLButtonElement>('sb-profile-menu .avatar')!.click();
    fixture.detectChanges();
    const comfortable = Array.from(el.querySelectorAll<HTMLButtonElement>('sb-profile-menu .density-control .segment'))
      .find((button) => button.textContent!.trim() === 'Comfortable')!;
    comfortable.click();
    await settle(fixture);
    expect(html.dataset['density']).toBe('comfortable');
    expect(stored.get('ui.density')).toBe('comfortable');
    const pressed = Array.from(el.querySelectorAll<HTMLButtonElement>('sb-profile-menu .density-control .segment'))
      .find((button) => button.getAttribute('aria-pressed') === 'true')!;
    expect(pressed.textContent!.trim()).toBe('Comfortable');
  });
});
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/shell/killswitch-chip.spec.ts --include src/app/shell/freshness-chip.spec.ts --include src/app/stores/connection.store.spec.ts --include src/app/shell/profile-menu.spec.ts --include src/app/shell/shell.spec.ts
```

Expected: FAIL. The two chip specs do not compile (`./killswitch-chip` and `./freshness-chip` do not exist). `connection.store.spec.ts`: `store.botLastSuccess` is not a function. `profile-menu.spec.ts`: no `.density-control`. `shell.spec.ts`: the tape, scan-progress, cluster and density cases fail (the tape is still in the bar; nothing renders the chips).

- [ ] **Step 5: Create `killswitch-chip.ts`**

Create `$WT/frontend/src/app/shell/killswitch-chip.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';

/**
 * The killswitch state, in the top bar on every device -- v195 Phase 3.
 *
 * The control lives in Risk's page header; this chip is the state, visible
 * from every page and two taps from the control on a phone (Risk is a tab).
 * "Armed" means trading runs; "Halted" means the killswitch is engaged and
 * the bot takes no new positions. The word carries the state, the loss
 * colour only repeats it, so it reads the same to a colour-blind eye.
 *
 * Renders nothing while the state is unknown (`null`): a chip that said
 * "Armed" before the first answer would be the one claim on the page that
 * must never be guessed.
 */
@Component({
  selector: 'sb-killswitch-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    @if (on() !== null) {
      <a class="chip sb-hit" routerLink="/risk" [class.halted]="on()" [attr.aria-label]="label()">
        <span class="dot" aria-hidden="true"></span>{{ on() ? 'Halted' : 'Armed' }}
      </a>
    }
  `,
  styles: `
    :host { display: inline-flex; }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      padding: 2px var(--space-6);
      border: 1px solid var(--border-strong);
      border-radius: var(--chip-radius);
      color: var(--text-secondary);
      font-size: var(--text-chip);
      line-height: 1.4;
      text-decoration: none;
      white-space: nowrap;
      transition: color var(--transition), border-color var(--transition);
    }
    .chip:hover { color: var(--text); border-color: var(--text-muted); }
    /* A status dot: the one full-round shape the radius rules allow (§1.5). */
    .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--pos); }
    .chip.halted {
      color: var(--neg);
      border-color: var(--neg);
      background: var(--neg-soft);
      font-weight: 600;
    }
    .chip.halted .dot { background: var(--neg); }
  `,
})
export class KillswitchChip {
  /** `null` until the shell's first `/risk/killswitch` answer. */
  readonly on = input<boolean | null>(null);

  protected readonly label = computed(() =>
    this.on() ? 'Killswitch on, trading halted. Open Risk' : 'Killswitch off, trading armed. Open Risk',
  );
}
```

- [ ] **Step 6: Create `freshness-chip.ts`**

Create `$WT/frontend/src/app/shell/freshness-chip.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

const MINUTE_MS = 60_000;

/**
 * How long ago the bot last completed a scan tick, at minute resolution --
 * v195 Phase 3. `format.ts`'s `age()` reads in hours ("<1h"), which is the
 * right unit for a plan's age and the wrong one for a bot that ticks every
 * few minutes. A time from the future (clock skew) reads "just now", never
 * a negative age. `null` when there is no readable time.
 */
export function scanAge(at: string | null, now: number): string | null {
  if (!at) return null;
  const then = Date.parse(at);
  if (Number.isNaN(then)) return null;
  const minutes = Math.floor(Math.max(0, now - then) / MINUTE_MS);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

/**
 * Data freshness, in the top bar on every device -- v195 Phase 3.
 *
 * Scan health leaves the Risk page for System (§5.1), so this chip is what
 * keeps "is the bot still scanning" in view from every page, phone
 * included. Pure inputs, like `sb-connection-status` beside it: the shell
 * passes the time and its 30s clock, so every state is a two-line test.
 * It answers "when did the bot last finish a tick"; each panel's own
 * `sb-freshness` still answers "how old are these numbers".
 */
@Component({
  selector: 'sb-freshness-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="chip" [class.unknown]="age() === null">
      @if (age(); as text) {
        Scan <time [attr.datetime]="at()">{{ text }}</time>
      } @else {
        No scan yet
      }
    </span>
  `,
  styles: `
    :host { display: inline-flex; }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      padding: 2px var(--space-6);
      border: 1px solid var(--border);
      border-radius: var(--chip-radius);
      color: var(--text-muted);
      font-size: var(--text-chip);
      line-height: 1.4;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    time { color: var(--text-secondary); }
    /* Before the first answer and when the bot never ticked: dashed, not
       warn-coloured, so every page load does not flash an alarm. */
    .chip.unknown { border-style: dashed; }
  `,
})
export class FreshnessChip {
  /** ISO time of the bot's last successful tick (or, failing that, its last
   *  heartbeat); `null` when it has never reported one. */
  readonly at = input<string | null>(null);
  /** The shell's clock, in ms. */
  readonly now = input.required<number>();

  protected readonly age = computed(() => scanAge(this.at(), this.now()));
}
```

- [ ] **Step 7: Keep `bot_last_success` in `ConnectionStore`**

In `$WT/frontend/src/app/stores/connection.store.ts`:

1. In `interface ConnectionStateSlice`, after `botLastSeen: string | null;` add:

```ts
  /**
   * When the bot last completed a tick successfully -- v195's top-bar
   * freshness chip. Already in the `/system/scan` payload this store reads;
   * kept now because Scan health leaves the Risk page (spec §5.1) and the
   * chip is what keeps it in view everywhere. Null until the bot has ever
   * completed one, distinct from an old time.
   */
  botLastSuccess: string | null;
```

2. In `withState<ConnectionStateSlice>({ ... })`, after `botLastSeen: null,` add `botLastSuccess: null,`.

3. In `refresh()`, in the `api.scanStatus()` `next` patch, after `botLastSeen: scan.bot_last_seen,` add `botLastSuccess: scan.bot_last_success,`.

- [ ] **Step 8: The Density row in `profile-menu.ts`**

In `$WT/frontend/src/app/shell/profile-menu.ts`:

1. After `import { MotionMode, parseMotion } from '../ui/motion/motion.service';` add `import { RowDensity } from '../ui/density.service';`.

2. After the `MOTION_OPTIONS` constant, add:

```ts

/** The two row densities, in the order the control shows them (v195 §1.4). */
const DENSITY_OPTIONS: SegmentOption[] = [
  { value: 'dense', label: 'Dense' },
  { value: 'comfortable', label: 'Comfortable' },
];
```

3. In the class docblock, after the paragraph that ends `strands a keyboard user at the top of the document.`, add:

```ts
 *
 * Density (v195 §1.4) sits beside Motion: a per-device choice the shell
 * writes through `DensityService`. It changes rows only on a desktop with a
 * fine pointer; the note under it says so, because on a phone or tablet the
 * 44px touch rules win and the control would otherwise seem broken.
```

4. In the template, directly after the closing `</div>` of `<div class="motion-row" role="none">`, add:

```html
        <div class="density-row" role="none">
          <span class="menu-label" aria-hidden="true">Density</span>
          <sb-segmented
            class="density-control"
            label="Density"
            [options]="densityOptions"
            [value]="density()"
            (valueChange)="onDensity($event)"
          />
          <span class="menu-note">Desktop only: touch screens keep 44px rows.</span>
        </div>
```

5. In `styles`, replace the selector line `    .motion-row {` with the two lines

```css
    .motion-row,
    .density-row {
```

   after the `.menu-label { ... }` rule add

```css
    .menu-note {
      font-size: var(--text-micro);
      color: var(--text-muted);
      max-width: 22ch;
    }
```

   and in the touch block replace `      :host ::ng-deep .motion-control .segment { min-width: 44px; justify-content: center; }` with

```css
      :host ::ng-deep .motion-control .segment,
      :host ::ng-deep .density-control .segment { min-width: 44px; justify-content: center; }
```

6. In the class, after `protected onMotion(value: string): void { ... }`, add:

```ts

  /** The current row density, owned by the shell's DensityService. */
  readonly density = input<RowDensity>('dense');
  readonly densityChanged = output<RowDensity>();

  protected readonly densityOptions = DENSITY_OPTIONS;

  /** Validated, not trusted: anything but 'comfortable' is the default. */
  protected onDensity(value: string): void {
    this.densityChanged.emit(value === 'comfortable' ? 'comfortable' : 'dense');
  }
```

- [ ] **Step 9: Seat the cluster in the shell**

1. `$WT/frontend/src/app/shell/shell.ts`:
   - After `import { CLOCK } from '../ui/clock';` add `import { DensityService } from '../ui/density.service';`. After `import { Breadcrumb } from './breadcrumb';` add `import { FreshnessChip } from './freshness-chip';` and `import { KillswitchChip } from './killswitch-chip';`.
   - In the `imports` array, after `Breadcrumb,` add `KillswitchChip, FreshnessChip,`.
   - Replace `private readonly clock = inject(CLOCK);` with `protected readonly clock = inject(CLOCK);` (the freshness chip ages against it).
   - Directly before `protected setMotion(mode: MotionMode): void {`, add:

```ts
  /** Row density for this device (v195 §1.4): read by the profile menu,
   *  written through DensityService, which owns `ui.density` and the
   *  `data-density` attribute on <html>. */
  protected readonly density = inject(DensityService);

```

   - Replace `protected readonly killswitchOn = signal(false);` with:

```ts
  protected readonly killswitchOn = signal<boolean | null>(null);
```

     and add, as the last paragraph of its docblock (before the closing ` */`):

```ts
   *
   * Three-valued (v195): `null` until the first answer, so the top bar's
   * killswitch chip says nothing rather than a guessed "Armed".
```

2. `$WT/frontend/src/app/shell/shell.html`: replace the whole `<div class="main"> ... </div>` block (from `  <div class="main">` through its closing `  </div>`, the line before `  <sb-toast-host />`) with:

```html
  <div class="main">
    <header class="topbar">
      <!-- A labelled list, never a heading: the page's one <h1> belongs to
           sb-page (correction 9), which route-focus.ts finds inside .workspace. -->
      <sb-breadcrumb class="topbar-lead" />
      <!-- v195 Phase 3: the right cluster. The killswitch and freshness chips
           show on every device, phone included: the halt control is on Risk,
           one tap from the chip, and Scan health has left the Risk page
           (§5.1). The dot answers only "is the event stream connected" (D30). -->
      <div class="status-cluster">
        <sb-killswitch-chip [on]="killswitchOn()" />
        <sb-freshness-chip [at]="connection.botLastSuccess() ?? connection.botLastSeen()" [now]="clock()" />
        <sb-connection-status
          [state]="connection.state()"
          [botAlive]="connection.botAlive()"
          [botHealthy]="connection.botHealthy()"
          [marketActive]="connection.marketActive()"
        />
        <span class="clock">
          <sb-icon name="clock" />
          {{ now() }}
        </span>
      </div>
      <sb-profile-menu [zoom]="zoom()" [state]="connection.state()"
                       [botAlive]="connection.botAlive()" [marketActive]="connection.marketActive()" (zoomCycled)="cycleZoom()"
                       [motion]="motionMode()" (motionChanged)="setMotion($event)"
                       [density]="density.density()" (densityChanged)="density.set($event)"
                       (signedOut)="logout()" />
      <!-- Hung from the bar's bottom edge (shell.css), never in the flow: an
           automatic scan runs every SCAN_INTERVAL_MINUTES all session, and a
           strip that took layout would shunt the page down and back. In the
           sticky bar it shows on every route. -->
      <sb-scan-progress
        [running]="connection.scanRunning()"
        [progress]="connection.scanProgress()"
      />
    </header>

    <!-- The ticker tape, a strip under the bar (spec Phase 3); what it shows
         is still tape-prefs' call. -->
    <div class="tape-strip">
      <sb-tape />
    </div>

    <!-- Engaged killswitch: the chip above is the state on every page; this
         strip is the alarm, full width and never truncated. -->
    @if (killswitchOn()) {
      <div class="killswitch-strip" role="alert">KILLSWITCH ENGAGED</div>
    }

    <main class="workspace" [class.route-pending]="routeLoading.visible()" [attr.aria-busy]="routeLoading.visible() ? 'true' : null">
      <div class="workspace-content" [attr.inert]="routeLoading.visible() ? '' : null"><router-outlet /></div>
      @if (routeLoading.visible()) {
        <div class="route-loading-overlay" role="status" aria-live="polite"><span class="route-loading-mark" aria-hidden="true"></span><span>{{ routeLoading.label() }}</span></div>
      }
    </main>
  </div>
```

3. `$WT/frontend/src/app/shell/shell.css`:
   - Replace the comment `/* Grows to fill the gap between the breadcrumb and the status cluster, and` / `   scrolls within it when more symbols arrive than fit. */`, the `.topbar-tape { ... }` rule and the `.topbar-tape::-webkit-scrollbar { display: none; }` line with:

```css
/* The ticker tape, a strip under the bar (v195 Phase 3). Its lane draws its
   own hairline and surface, so an empty strip takes no space. Not sticky:
   it scrolls away with the page, the chips above it do not. */
.tape-strip {
  display: flex;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
}
.tape-strip::-webkit-scrollbar { display: none; }

/* scan-progress.css's :host is absolute at the top of its container; here
   it hangs from the sticky bar's bottom edge instead, over the tape and the
   page and never in the flow. Out-ranks the :host rule (two classes and two
   attributes against one). */
.topbar > sb-scan-progress {
  inset: 100% 0 auto 0;
}
```

   - In the `.status-cluster` rule, add `margin-left: auto;` after `gap: var(--space-6);` and replace its comment with `/* The right cluster: chips, dot and clock as one group, pushed to the bar's right edge and tighter than the bar's own gap. */`.
   - In the `@media (max-width: 639px)` block, replace `  .topbar-tape { display: none; }` with `  .tape-strip { display: none; }`.

4. `$WT/frontend/src/app/shell/tape/tape.css`: in the opening comment, replace `child of .topbar-tape and shoves the other one out past the visible` with `child of the shell's .tape-strip and shoves the other one out past the visible`. No rule changes: `:host { display: flex; flex: 1 1 0%; min-width: 0; }` fills the strip the way it filled the bar, and the lane's own `border-bottom` and `background: var(--surface)` draw the strip.

- [ ] **Step 10: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/shell/killswitch-chip.spec.ts --include src/app/shell/freshness-chip.spec.ts --include src/app/stores/connection.store.spec.ts --include src/app/shell/profile-menu.spec.ts --include src/app/shell/shell.spec.ts --include src/app/shell/tape/tape.spec.ts --include src/app/shell/scan-progress.spec.ts --include src/app/ui/title-usage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/hit-area.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `title-usage.spec.ts` finds no new site (the two chips bind no `title`; the profile menu's one allow-listed `[attr.title]="haloTitle()"` is unchanged). If the density case finds `data-density` still `dense`, the segmented control's click did not reach the shell: check the `(densityChanged)` binding on `sb-profile-menu`, not the service. If a freshness case reads `No scan yet` after the flush, the `/system/scan` request was flushed before the shell's effect fired: `mount()` awaits `whenStable()` first so the request exists; do not flush by exact URL from a hand-built string.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green.

- [ ] **Step 11: Check it in a browser**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard`. At 1440, 768 and 390: the bar shows the breadcrumb left and, right-aligned, the killswitch chip (`Armed` on a dev book), the freshness chip (`Scan <n>m ago`), the clock (hidden at 390) and the avatar; nothing wraps or overflows (`document.querySelector('header.topbar').scrollWidth <= clientWidth`); tapping the killswitch chip opens Risk; the tape (flag one symbol on the Watchlist first) runs as a strip under the bar at 1440 and 768 and is absent at 390; trigger a scan from System and the progress hairline runs along the bar's bottom edge on Dashboard while the page does not move. At 1440 open the avatar menu, pick Comfortable: Trades rows grow to 44px and `localStorage.getItem('ui.density')` is `comfortable`; pick Dense back. At 768 the menu's note reads `Desktop only: touch screens keep 44px rows.` and rows stay 44px either way. Save the PNGs under the session scratchpad.

- [ ] **Step 12: Close**

Close: standard (test: `frontend/src/app/shell/shell.spec.ts`), plus `frontend/src/app/shell/killswitch-chip.spec.ts`, `frontend/src/app/shell/freshness-chip.spec.ts`, `frontend/src/app/stores/connection.store.spec.ts` and `frontend/src/app/shell/profile-menu.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/shell/killswitch-chip.ts frontend/src/app/shell/killswitch-chip.spec.ts frontend/src/app/shell/freshness-chip.ts frontend/src/app/shell/freshness-chip.spec.ts frontend/src/app/stores/connection.store.ts frontend/src/app/stores/connection.store.spec.ts frontend/src/app/shell/profile-menu.ts frontend/src/app/shell/profile-menu.spec.ts frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts frontend/src/app/shell/tape/tape.css
git -C "$WT" commit -m "feat(v195): top-bar cluster with killswitch and freshness chips, Density in the profile menu (V195-17)" -m "Spec Phase 3 and §1.4: sb-killswitch-chip (Armed / Halted, links to Risk, nothing until known) and sb-freshness-chip (the bot's last successful tick, else its heartbeat, aged at minute resolution) sit in the top bar on every device. ConnectionStore keeps bot_last_success. The scan progress hangs from the sticky bar's bottom edge; the tape is a strip under the bar. The profile menu gains a Dense / Comfortable control written through DensityService, noting that touch screens keep 44px rows." -m "Moved, not dropped (shell.spec.ts): the tape, killswitch-strip and scan-progress cases now pin the strip under the bar and the bar's bottom edge." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

