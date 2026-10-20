# v168 Motion system, part 2: preference and routing (MO5..MO8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `grep -n "^### Task MO7:" -A 400 docs/superpowers/plans/2026-10-16-v168-motion-system_2-preference-routing.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v168-motion-system-design.md`](../specs/2026-10-16-v168-motion-system-design.md) (its `## Amendments from the plan brief` bind and override earlier sections).
**Index:** [`2026-10-16-v168-motion-system_0-index.md`](2026-10-16-v168-motion-system_0-index.md): `## Global Constraints`, `## Where to work` (`$WT`, `$R`, the narrow-run command, `GATES`), `## Parallelisation` and the `## Task ledger` apply to every task below and are not repeated.

**Scope of this part:** the Motion control and `data-motion` on `<html>` (MO5); the nine Off/Reduced fallback sites and the inverted token test (MO6); `RouteEntryService` and the route host with the CSS stagger (MO7); `[sbCountUp]` on `figure`, `stat-tile`, `metric-card`, `metric-chip` (MO8).

**Consumed from part 1 (contracts from the index ledger, not from the part-1 file):**
- MO3: `frontend/src/styles/motion.css` exists, imported by `styles.css` after the tokens import; it already holds `[data-motion=off] { --motion-scale: 0; }`, the renamed keyframes (`sb-pulse-dim`, `sb-pulse-blink`, `sb-spin`, `sb-route-spin`, `sb-scan-sweep`, `sb-scan-strip-in`, `sb-row-blink`, `sb-tape-slide`, …) and the `.sb-entering` stagger rules. The component files reference the new keyframe names but **still carry their `@media (prefers-reduced-motion: reduce)` blocks** (MO3 moves keyframes only). `frontend/src/app/ui/motion-home.spec.ts` defines `sourceFiles(): { name: string; source: string }[]`; `frontend/src/app/ui/motion-css.spec.ts` exists.
- MO4, from `frontend/src/app/ui/motion/motion.service.ts`: `type MotionMode = 'on' | 'reduced' | 'off'`, `type MotionState = MotionMode | 'pending'`, `MOTION_MODES`, `MOTION_PREF_KEY = 'shell.motion'`, `parseMotion(stored: unknown): MotionMode`, `provideMotion(mode: MotionState | 'live'): Provider`, `MotionService { mode: Signal<MotionState>; full: Signal<boolean>; active: Signal<boolean>; set(mode: MotionMode): void }` (`set` persists through `PreferencesStore.update` under `shell.motion`). From `frontend/src/app/ui/motion/motion-starts.ts`: `type MotionStartKind`, `MotionStarts { record(kind, key); entries(); count(kind); clear() }`. `frontend/src/test-setup.ts` gives every spec `provideMotion('off')` through a global `beforeEach`.

**Line numbers below are pre-v167.** v167 and part 1 move lines around; every edit is anchored on quoted text, never on a line number alone. If an anchor is missing, stop and report it rather than guessing.

---

# Phase 2 -- The preference, the fallbacks, route entry and count-up

### Task MO5: Motion control in the profile menu; `shell.motion` persistence; `data-motion` on `<html>` (cold-load `pending`)

**Model:** sonnet — a shell preference following the `shell.zoom` pattern

**Files:**
- Modify: `frontend/src/index.html`
- Modify: `frontend/src/app/shell/profile-menu.ts`
- Modify: `frontend/src/app/shell/profile-menu.spec.ts`
- Modify: `frontend/src/app/shell/shell.ts`
- Modify: `frontend/src/app/shell/shell.html`
- Modify: `frontend/src/app/shell/shell.spec.ts`

**Interfaces:**
- Consumes (MO4): `MotionService` (`mode`, `set`), `MotionMode`, `parseMotion`, `provideMotion` from `frontend/src/app/ui/motion/motion.service.ts`. `Segmented`, `SegmentOption` from `frontend/src/app/ui/segmented.ts` (exists: `options` required, `label` required, `value = model<string>('')`, roving tabindex plus arrow/Home/End keys, `.segment { min-height: var(--control-h) }`; `--control-h` is already 44px under `(pointer: coarse), (max-width: 639px)` in `tokens.css`).
- Produces: `index.html` `<html lang="en" data-motion="pending">`. `ProfileMenu`: `readonly motion = input<MotionMode>('on')`, `readonly motionChanged = output<MotionMode>()`, an `sb-segmented` with `label="Motion"`, class `motion-control`, options On/Reduced/Off (`value` `on`/`reduced`/`off`). `Shell`: `protected readonly motion = inject(MotionService)`, `protected readonly motionMode: Signal<MotionMode>` (the mode with `pending` shown as `on`), `private readonly applyMotion = effect(...)` writing `document.documentElement.dataset['motion'] = this.motion.mode()`, `protected setMotion(mode: MotionMode): void`. `shell.html`: `<sb-profile-menu ... [motion]="motionMode()" (motionChanged)="setMotion($event)" ...>`.

**Why the shell writes the attribute and nobody else does:** CSS reads only `data-motion`; TS reads only `MotionService` (Global Constraints). The shell exists exactly when a session does, the reasoning `shell.ts` already records for `preferences.load()`. Before `PreferencesStore.isLoaded()`, `MotionService.mode()` is `pending`, so the effect writes `pending`, the value `index.html` starts with: there is no frame in which a user who chose Off sees motion. `PreferencesStore` also sets `loaded` when the GET fails, so `pending` always ends (it falls to `on`).

- [ ] **Step 1: Write the failing ProfileMenu tests**

Append to `frontend/src/app/shell/profile-menu.spec.ts`, inside the existing `describe('ProfileMenu', () => { ... })` block, after its last `it(...)`. The existing `beforeEach`, `fixture`, `el`, `menu()` and `openMenu()` are reused as they are.

```ts
  describe('Motion control (v168 §1)', () => {
    const control = () => el.querySelector('sb-segmented.motion-control');
    const segments = () =>
      Array.from(el.querySelectorAll<HTMLButtonElement>('sb-segmented.motion-control .segment'));

    it('offers On, Reduced and Off under the label "Motion"', () => {
      openMenu();
      expect(control()).not.toBeNull();
      expect(control()!.querySelector('[role=group]')!.getAttribute('aria-label')).toBe('Motion');
      expect(segments().map((b) => b.textContent!.trim())).toEqual(['On', 'Reduced', 'Off']);
    });

    it('marks the current mode from the motion input', () => {
      fixture.componentRef.setInput('motion', 'reduced');
      openMenu();
      const current = segments().filter((b) => b.getAttribute('aria-pressed') === 'true');
      expect(current.map((b) => b.textContent!.trim())).toEqual(['Reduced']);
    });

    it('defaults to On when no mode is bound', () => {
      openMenu();
      const current = segments().find((b) => b.getAttribute('aria-pressed') === 'true');
      expect(current!.textContent!.trim()).toBe('On');
    });

    it('emits the chosen mode and keeps the menu open', () => {
      const chosen: string[] = [];
      fixture.componentInstance.motionChanged.subscribe((mode) => chosen.push(mode));
      openMenu();
      segments()[2].click();
      fixture.detectChanges();
      expect(chosen).toEqual(['off']);
      expect(menu()).not.toBeNull();
    });

    it('is keyboard-operable: ArrowRight moves to the next mode', () => {
      const chosen: string[] = [];
      fixture.componentInstance.motionChanged.subscribe((mode) => chosen.push(mode));
      openMenu();
      control()!.querySelector('[role=group]')!.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }),
      );
      fixture.detectChanges();
      expect(chosen).toEqual(['reduced']);
    });
  });
```

- [ ] **Step 2: Write the failing Shell tests**

In `frontend/src/app/shell/shell.spec.ts`, extend the imports at the top. Keep every existing import; add only what is missing:

```ts
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { PreferencesStore } from '../stores/preferences.store';
import { provideMotion } from '../ui/motion/motion.service';
```

(`HttpTestingController` joins the existing `provideHttpClientTesting` import line, one statement with two names. `readFileSync` and `join` are already imported at the top of this file. The `vitest` import line must include `afterEach`: `import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';`.)

Then append a new top-level `describe` at the end of the file. It reuses the module-level `FakeEventStream` class, and it needs `provideMotion('live')` so the real, preference-driven `MotionService` runs instead of the global `'off'` test default:

```ts
describe('shell motion preference (v168 §1)', () => {
  const html = document.documentElement;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        { provide: TapeStore, useValue: { load: vi.fn(), visible: signal(false), rows: signal([]), asOf: signal(null) } },
        provideMotion('live'),
      ],
    });
  });

  afterEach(() => {
    delete html.dataset['motion'];
  });

  function flushPreferences(preferences: Record<string, unknown>): void {
    TestBed.inject(HttpTestingController)
      .expectOne((request) => request.method === 'GET' && request.url.endsWith('/system/preferences'))
      .flush({ preferences });
  }

  async function settle(fixture: { detectChanges(): void; whenStable(): Promise<unknown> }): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('starts the cold load as pending in index.html, before any script runs', () => {
    const source = readFileSync(join(process.cwd(), 'src/index.html'), 'utf8');
    expect(source).toMatch(/<html lang="en" data-motion="pending">/);
  });

  it('keeps <html data-motion> pending until preferences load', async () => {
    const fixture = TestBed.createComponent(Shell);
    await settle(fixture);
    expect(html.dataset['motion']).toBe('pending');
  });

  it('defaults to on once preferences load without a stored mode', async () => {
    const fixture = TestBed.createComponent(Shell);
    await settle(fixture);
    flushPreferences({});
    await settle(fixture);
    expect(html.dataset['motion']).toBe('on');
  });

  it('restores a stored mode onto <html>', async () => {
    const fixture = TestBed.createComponent(Shell);
    await settle(fixture);
    flushPreferences({ 'shell.motion': 'reduced' });
    await settle(fixture);
    expect(html.dataset['motion']).toBe('reduced');
  });

  it('falls back to on for an unknown stored value', async () => {
    const fixture = TestBed.createComponent(Shell);
    await settle(fixture);
    flushPreferences({ 'shell.motion': 'sparkly' });
    await settle(fixture);
    expect(html.dataset['motion']).toBe('on');
  });

  it('writes shell.motion and data-motion when the control is used', async () => {
    const fixture = TestBed.createComponent(Shell);
    await settle(fixture);
    flushPreferences({});
    await settle(fixture);
    const el = fixture.nativeElement as HTMLElement;
    el.querySelector<HTMLButtonElement>('sb-profile-menu .avatar')!.click();
    fixture.detectChanges();
    const off = Array.from(el.querySelectorAll<HTMLButtonElement>('sb-profile-menu .motion-control .segment'))
      .find((button) => button.textContent!.trim() === 'Off')!;
    off.click();
    await settle(fixture);
    expect(html.dataset['motion']).toBe('off');
    expect(TestBed.inject(PreferencesStore).values()['shell.motion']).toBe('off');
  });
});
```

- [ ] **Step 3: Run both specs to verify they fail**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/shell/profile-menu.spec.ts --include src/app/shell/shell.spec.ts`
Expected: FAIL. The new ProfileMenu cases fail with `control()` null; the `index.html` case fails on the regex; the shell cases fail with `expected undefined to be 'pending'` (nothing writes the attribute yet). Every pre-existing case still passes.

- [ ] **Step 4: Start the cold load as `pending`**

In `frontend/src/index.html`, replace:

```html
<html lang="en">
```

with:

```html
<!-- data-motion starts as "pending" (spec v168 §1): no entrance, count-up or
     draw-in runs, and the tape is frozen, until the shell has read the saved
     Motion preference and replaced this value. A user who chose Off never
     sees a burst of motion on a cold load. -->
<html lang="en" data-motion="pending">
```

The comment sits between `<!doctype html>` and `<html ...>`, which is valid HTML.

- [ ] **Step 5: Add the Motion control to `ProfileMenu`**

In `frontend/src/app/shell/profile-menu.ts`:

1. Below `import { Icon } from '../ui/icon';` add:

```ts
import { MotionMode, parseMotion } from '../ui/motion/motion.service';
import { SegmentOption, Segmented } from '../ui/segmented';

/** The three Motion modes, in the order the control shows them (spec v168 §1). */
const MOTION_OPTIONS: SegmentOption[] = [
  { value: 'on', label: 'On' },
  { value: 'reduced', label: 'Reduced' },
  { value: 'off', label: 'Off' },
];
```

(The constant goes above the class's existing doc comment `/** The avatar, and what sits behind it ...`, so that comment still sits directly on `@Component`.)

2. Change the component's `imports: [Button, Icon],` to `imports: [Button, Icon, Segmented],`.

3. In the template, between the closing `</button>` of the `.zoom` button and the `Sign out` button, insert:

```html
        <div class="motion-row" role="none">
          <span class="menu-label" aria-hidden="true">Motion</span>
          <sb-segmented
            class="motion-control"
            label="Motion"
            [options]="motionOptions"
            [value]="motion()"
            (valueChange)="onMotion($event)"
          />
        </div>
```

4. Append to the `styles` string, after the `.menu button { ... }` rule:

```css
    /* The Motion control is a segmented group, not a menu row: it keeps its
       own centred segments. The ".menu button" rule above does not reach
       them (emulated encapsulation scopes it to this template's own
       buttons), so nothing has to be undone here. */
    .motion-row {
      display: flex;
      flex-direction: column;
      gap: var(--space-4);
      padding: var(--space-4) var(--space-6);
    }
    .menu-label {
      font-size: var(--text-chip);
      color: var(--text-secondary);
    }
    /* Spec v168 §1 and §5: 44px targets on touch. --control-h already gives
       the height on coarse pointers; this gives a short label like "On" the
       same width. */
    @media (pointer: coarse) {
      :host ::ng-deep .motion-control .segment { min-width: 44px; justify-content: center; }
    }
```

5. In the class body, after `readonly zoomCycled = output<void>();`, add:

```ts
  /** The current Motion mode, owned by the shell's MotionService. */
  readonly motion = input<MotionMode>('on');
  readonly motionChanged = output<MotionMode>();

  protected readonly motionOptions = MOTION_OPTIONS;

  /** Validated, not trusted: the segmented control hands back a string. */
  protected onMotion(value: string): void {
    this.motionChanged.emit(parseMotion(value));
  }
```

- [ ] **Step 6: Wire the shell**

In `frontend/src/app/shell/shell.ts`:

1. Below `import { ViewportService } from '../ui/breakpoints';` add:

```ts
import { MotionMode, MotionService } from '../ui/motion/motion.service';
```

2. Directly after the `applyStoredSidebar` effect (the block ending `else if (stored === 'expanded') this.userCollapsed.set(false);` then `});` twice), add:

```ts
  /* -- v168: Motion preference --------------------------------------- */

  /**
   * The one TS source of the Motion mode (spec v168 §1). Persisted through
   * `PreferencesStore` under `shell.motion` by `MotionService.set`, never
   * `localStorage` -- the same plan v21 Global Constraint as `shell.zoom`.
   * The OS reduced-motion setting is deliberately not read (spec D2).
   */
  protected readonly motion = inject(MotionService);

  /** Narrowed for the profile menu: `pending` is a load state, not a choice,
   *  so the control shows the default (On) until preferences arrive. */
  protected readonly motionMode = computed<MotionMode>(() => {
    const mode = this.motion.mode();
    return mode === 'pending' ? 'on' : mode;
  });

  /**
   * Written to `<html>` for the same reason as `--text-scale` above: dialogs,
   * the drawer and the toast host sit outside this component. CSS reads only
   * this attribute; TS reads only `MotionService`.
   */
  private readonly applyMotion = effect(() => {
    document.documentElement.dataset['motion'] = this.motion.mode();
  });

  protected setMotion(mode: MotionMode): void {
    this.motion.set(mode);
  }
```

(`computed`, `effect` and `inject` are already imported from `@angular/core` in `shell.ts`.)

In `frontend/src/app/shell/shell.html`, replace:

```html
      <sb-profile-menu [zoom]="zoom()" (zoomCycled)="cycleZoom()" (signedOut)="logout()" />
```

with:

```html
      <sb-profile-menu [zoom]="zoom()" (zoomCycled)="cycleZoom()"
                       [motion]="motionMode()" (motionChanged)="setMotion($event)"
                       (signedOut)="logout()" />
```

- [ ] **Step 7: Run both specs to verify they pass**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/shell/profile-menu.spec.ts --include src/app/shell/shell.spec.ts`
Expected: PASS, verdict line `Tests  N passed (N)`, `0 failed`. Quote it in the report.

If `writes shell.motion and data-motion when the control is used` fails with `expected 'on' to be 'off'` while `values()['shell.motion']` is `'off'`, `MotionService.mode` is not derived from `PreferencesStore.values()`: that is an MO4 contract defect. Stop and report it; do not patch `MotionService` from this task.

- [ ] **Step 8: Prove the OS setting is still never read**

Run: `git -C $WT grep -n "matchMedia" -- frontend/src/app/shell frontend/src/app/ui/motion ':!*.spec.ts'`
Expected: no output.

- [ ] **Step 9: Commit**

```bash
git -C $WT add frontend/src/index.html frontend/src/app/shell/profile-menu.ts frontend/src/app/shell/profile-menu.spec.ts frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.spec.ts
git -C $WT commit -m "feat(v168): Motion control in the profile menu, shell.motion persistence, data-motion on <html> (MO5)

Cold load starts as data-motion=pending in index.html; the shell replaces it
from MotionService once preferences load. The OS reduced-motion setting is not read.

Narrow run: <the Tests verdict line from Step 7>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task MO6: The nine Off/Reduced fallback sites; delete the global reduced-motion block; invert `tokens.spec`; rewrite the stale comments

**Model:** sonnet — nine fixed CSS migrations and one inverted test, behaviour given by the spec table

**Files:**
- Modify: `frontend/src/styles/tokens.css`
- Modify: `frontend/src/styles/motion.css`
- Modify: `frontend/src/app/ui/tokens.spec.ts`
- Modify: `frontend/src/app/ui/motion-css.spec.ts`
- Modify: `frontend/src/app/ui/motion-home.spec.ts`
- Modify: `tests/charts/resolved_tokens.json`
- Modify: `frontend/src/app/shell/connection-status.ts`
- Modify: `frontend/src/app/shell/scan-progress.css`
- Modify: `frontend/src/app/shell/shell.css`
- Modify: `frontend/src/app/shell/tape/tape.css`
- Modify: `frontend/src/app/ui/data-table/data-table.ts`
- Modify: `frontend/src/app/ui/chart-container.ts`
- Modify: `frontend/src/app/ui/status-indicator.ts`
- Modify: `frontend/src/app/ui/status-cell.ts`
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts`

(`motion-home.spec.ts` is not in the ledger's file column, but the ledger's "Creates" column gives MO6 its new sweep case; no task running in parallel with MO6 touches that file.)

**Interfaces:**
- Consumes: MO3's `motion.css` (already holds `[data-motion=off] { --motion-scale: 0; }`), MO3's `motion-css.spec.ts`, and `sourceFiles(): { name: string; source: string }[]` in `motion-home.spec.ts` (every `.ts`/`.css` under `frontend/src`, `/`-separated names relative to `frontend/src`, `*.spec.ts` excluded). MO2's tier-3 tokens and `calc(... * var(--motion-scale))` durations in `tokens.css`.
- Produces: the `[data-motion=off|reduced|pending]` fallback block at the end of `motion.css`; `tokens.spec.ts` case `ignores the OS reduced-motion setting: no media block; motion.css carries the Off rules` (replaces `honours prefers-reduced-motion`); `motion-css.spec.ts` `describe('Off keeps every fallback (spec v168 §1)')`, one case per site; `motion-home.spec.ts` case `no prefers-reduced-motion outside specs`. After this task no `@media (prefers-reduced-motion ...)` exists anywhere in `frontend/src`.

**The fallback table this task implements** (spec §1, corrected by amendment 6; Global Constraints). Spinners are status, not decoration: **under every mode they keep turning**.

| # | Site | Under `off` | Also under |
|---|---|---|---|
| 1 | `styles/tokens.css` global block | deleted; `[data-motion=off] { --motion-scale: 0; }` (MO3) zeroes every `--dur-*` | — |
| 2 | `shell/connection-status.ts` | live dot steady colour, no pulse | — |
| 3 | `shell/scan-progress.css` | strip appears without sliding, `.fill` transition off, sweep `width: 100%; opacity: .4` | — |
| 4 | `shell/shell.css` | sidebar width snaps; route spinner keeps spinning at 2.4s (**intended change**: today it stops) | — |
| 5 | `shell/tape/tape.css` | track frozen, `.viewport { overflow-x: auto }` | `reduced`, `pending` |
| 6 | `ui/data-table/data-table.ts` | spinner 2.4s; `.blink` row a steady `color-mix(in srgb, var(--warn) 10%, transparent)` | — |
| 7 | `ui/chart-container.ts` | spinner 2.4s | — |
| 8 | `ui/status-indicator.ts` | `.open` steady colour | — |
| 9 | `ui/status-cell.ts` | `.dot` steady colour, `.fill` transition off | — |

**Why every fallback declaration carries `!important`:** Angular's emulated encapsulation qualifies every compound of a component selector with an attribute, so `.shell.overlay .sidebar` in `shell.css` ranks (0,5,0) and `.strip.stalled .fill` (0,5,0); a global `[data-motion=off] sb-shell .shell.overlay .sidebar` ranks only (0,4,1). Specificity cannot be relied on to win from a global file. The deleted global block solved the same problem the same way. The scan sweep's `width` is already `!important` in the component; the global rule wins that tie on specificity ((0,3,1) against (0,3,0)).

- [ ] **Step 1: Look at what MO3 left behind**

Run: `git -C $WT grep -n "prefers-reduced-motion" -- frontend/src`
Expected: the eight component sites and `styles/tokens.css` (each `@media (prefers-reduced-motion: reduce) { ... }`), the three comment mentions (`connection-status.ts` "reduced-motion rule below", `data-table.ts` "Respects prefers-reduced-motion", `watchlist.ts` "prefers-reduced-motion fallback"), `ui/flash.ts`'s doc comment, and `ui/tokens.spec.ts`. If MO3 already removed a site's media block, skip that site's deletion below; its `motion.css` rule is still added.

Run: `git -C $WT grep -n "motion-scale" -- frontend/src/styles/motion.css`
Expected: one line, `[data-motion=off] { --motion-scale: 0; }` (MO3). If it is missing, stop: MO3 is incomplete.

- [ ] **Step 2: Write the failing tests**

(a) In `frontend/src/app/ui/tokens.spec.ts`, replace the whole case:

```ts
  it('honours prefers-reduced-motion', () => {
    expect(CSS).toContain('prefers-reduced-motion: reduce');
  });
```

with:

```ts
  /* Inverted by v168 (spec D2): the OS reduced-motion setting is ignored by
   * design, and the shell's Motion control drives data-motion instead. The
   * media-feature name must not come back into this file, comments included. */
  it('ignores the OS reduced-motion setting: no media block; motion.css carries the Off rules', () => {
    expect(CSS).not.toContain('prefers-reduced-motion');
    const motion = readFileSync(join(process.cwd(), 'src/styles/motion.css'), 'utf8');
    expect(motion).toMatch(/\[data-motion="?off"?\]\s*\{\s*--motion-scale:\s*0;\s*\}/);
  });
```

(`readFileSync` and `join` are already imported at the top of `tokens.spec.ts`.)

(b) Append to the end of `frontend/src/app/ui/motion-css.spec.ts`. The file must import `readFileSync` from `node:fs`, `join` from `node:path` and `describe, expect, it` from `vitest`; add any of those that MO3's version does not import yet (one import statement per module, no duplicates).

```ts
describe('Off keeps every fallback (spec v168 §1)', () => {
  /* Whitespace-flattened, so a rule is asserted by its text whatever the line
   * breaks. Read from disk, never `?raw` (see tokens.spec.ts's header). */
  const fallbackCss = readFileSync(join(process.cwd(), 'src/styles/motion.css'), 'utf8')
    .replace(/\s+/g, ' ');
  const readSource = (path: string) => readFileSync(join(process.cwd(), 'src', path), 'utf8');
  const frozen = ':is([data-motion=off], [data-motion=reduced], [data-motion=pending])';

  const fallbackSites: { site: string; file: string; rules: string[] }[] = [
    {
      site: 'tokens.css global block',
      file: 'styles/tokens.css',
      rules: ['[data-motion=off] { --motion-scale: 0; }'],
    },
    {
      site: 'connection-status live dot',
      file: 'app/shell/connection-status.ts',
      rules: ['[data-motion=off] sb-connection-status .dot.live { animation: none !important; }'],
    },
    {
      site: 'scan-progress strip and sweep',
      file: 'app/shell/scan-progress.css',
      rules: [
        '[data-motion=off] sb-scan-progress .strip { animation: none !important; }',
        '[data-motion=off] sb-scan-progress .fill { transition: none !important; }',
        '[data-motion=off] sb-scan-progress .fill.sweeping { animation: none !important; width: 100% !important; opacity: .4 !important; }',
      ],
    },
    {
      site: 'shell sidebar width and route spinner',
      file: 'app/shell/shell.css',
      rules: [
        '[data-motion=off] sb-shell .shell, [data-motion=off] sb-shell .shell.overlay .sidebar { transition: none !important; }',
        '[data-motion=off] sb-shell .route-loading-mark { animation-duration: 2.4s !important; }',
      ],
    },
    {
      site: 'tape track',
      file: 'app/shell/tape/tape.css',
      rules: [
        `${frozen} sb-tape .track { animation: none !important; }`,
        `${frozen} sb-tape .viewport { overflow-x: auto !important; }`,
      ],
    },
    {
      site: 'data-table spinner and blinking row',
      file: 'app/ui/data-table/data-table.ts',
      rules: [
        '[data-motion=off] sb-data-table .loading-spinner { animation-duration: 2.4s !important; }',
        '[data-motion=off] sb-data-table .blink { animation: none !important; background: color-mix(in srgb, var(--warn) 10%, transparent) !important; }',
      ],
    },
    {
      site: 'chart-container spinner',
      file: 'app/ui/chart-container.ts',
      rules: ['[data-motion=off] sb-chart-container .spinner { animation-duration: 2.4s !important; }'],
    },
    {
      site: 'status-indicator open dot',
      file: 'app/ui/status-indicator.ts',
      rules: ['[data-motion=off] sb-status-indicator .open { animation: none !important; }'],
    },
    {
      site: 'status-cell dot and fill',
      file: 'app/ui/status-cell.ts',
      rules: [
        '[data-motion=off] sb-status-cell .dot { animation: none !important; }',
        '[data-motion=off] sb-status-cell .fill { transition: none !important; }',
      ],
    },
  ];

  for (const { site, file, rules } of fallbackSites) {
    it(`${site}: carries its [data-motion] fallback and no OS media block`, () => {
      for (const rule of rules) expect(fallbackCss).toContain(rule);
      expect(readSource(file)).not.toContain('prefers-reduced-motion');
    });
  }

  it('never stops a spinner: loading spinners only slow down', () => {
    const stops = /(?:spinner|route-loading-mark)[^{}]*\{[^}]*animation:\s*none/;
    expect(fallbackCss).not.toMatch(stops);
  });
});
```

(c) Append to the end of `frontend/src/app/ui/motion-home.spec.ts`:

```ts
describe('the OS reduced-motion setting (spec v168 D2)', () => {
  /* Matches the media feature as a query uses it -- "(prefers-reduced-motion"
   * in an @media rule or a matchMedia() string -- so prose that names the
   * feature is not an offence. flash.ts's doc comment still names it until
   * MO14 rewrites that comment; that is prose, not a query. */
  it('no prefers-reduced-motion outside specs', () => {
    const offenders = sourceFiles()
      .filter(({ source }) => /\(\s*prefers-reduced-motion\b/.test(source))
      .map(({ name }) => name);
    expect(offenders).toEqual([]);
  });
});
```

- [ ] **Step 3: Run the three specs to verify they fail**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/tokens.spec.ts --include src/app/ui/motion-css.spec.ts --include src/app/ui/motion-home.spec.ts`
Expected: FAIL: the inverted `tokens.spec` case (`expected ... not to contain 'prefers-reduced-motion'`), every site case except `tokens.css global block`'s rule half (each fails on its missing rule or on the media block still in the component), and `no prefers-reduced-motion outside specs` (offenders list the nine files).

- [ ] **Step 4: Append the fallback block to `motion.css`**

Append to the end of `frontend/src/styles/motion.css`, exactly as written (the spec cases above assert this text, whitespace-flattened):

```css
/* ===== Off / Reduced fallbacks for the pre-v168 motion sites (spec v168 §1) =====
 *
 * These replace the eight component-level reduced-motion media blocks and the
 * global one tokens.css used to carry. The OS setting is no longer read (spec
 * D2): the shell's Motion control writes data-motion on <html>, and these rules
 * key on it. Each site keeps the fallback it had before, so Off means "no
 * decorative motion", never "status disappears".
 *
 * Why !important: emulated encapsulation qualifies every compound of a
 * component selector with an attribute, so `.shell.overlay .sidebar` in
 * shell.css out-ranks any global selector this file could write. The old
 * global block solved the same problem the same way.
 *
 * Spinners are status, not decoration: under Off they slow to 2.4s, and no
 * mode ever stops one. (The route spinner used to stop under the OS setting;
 * slowing it instead is an intended change, spec amendment 6.)
 */

/* connection-status: the live dot keeps its colour and drops the pulse. */
[data-motion=off] sb-connection-status .dot.live { animation: none !important; }

/* scan-progress: the strip appears without sliding in; the indeterminate sweep
   becomes a static full-width bar at .4 opacity, still told apart from a
   determinate one. */
[data-motion=off] sb-scan-progress .strip { animation: none !important; }
[data-motion=off] sb-scan-progress .fill { transition: none !important; }
[data-motion=off] sb-scan-progress .fill.sweeping { animation: none !important; width: 100% !important; opacity: .4 !important; }

/* shell: the sidebar width snaps; the route spinner keeps turning, slowly. */
[data-motion=off] sb-shell .shell,
[data-motion=off] sb-shell .shell.overlay .sidebar { transition: none !important; }
[data-motion=off] sb-shell .route-loading-mark { animation-duration: 2.4s !important; }

/* tape: frozen under Off, Reduced and the cold-load pending state; without a
   scroll affordance every tile past the first viewport-width would be
   unreachable. Hover and focus still pause it under On (tape.css). */
:is([data-motion=off], [data-motion=reduced], [data-motion=pending]) sb-tape .track { animation: none !important; }
:is([data-motion=off], [data-motion=reduced], [data-motion=pending]) sb-tape .viewport { overflow-x: auto !important; }

/* data-table: the spinner slows; the earnings-week row keeps its meaning as a
   steady warn tint instead of a pulse. */
[data-motion=off] sb-data-table .loading-spinner { animation-duration: 2.4s !important; }
[data-motion=off] sb-data-table .blink { animation: none !important; background: color-mix(in srgb, var(--warn) 10%, transparent) !important; }

/* chart-container: the spinner slows. */
[data-motion=off] sb-chart-container .spinner { animation-duration: 2.4s !important; }

/* status-indicator and status-cell: the colour carries the state; the pulse
   only ever carried liveliness. */
[data-motion=off] sb-status-indicator .open { animation: none !important; }
[data-motion=off] sb-status-cell .dot { animation: none !important; }
[data-motion=off] sb-status-cell .fill { transition: none !important; }
```

- [ ] **Step 5: Delete the component media blocks and rewrite their comments**

Each block below is deleted whole, including its closing brace. Text is quoted from today's files; MO3 renamed only keyframe names inside `animation:` values, so the media blocks themselves are unchanged.

1. `frontend/src/app/shell/connection-status.ts`: delete

```css
    @media (prefers-reduced-motion: reduce) {
      .dot.live { animation: none; }
    }
```

and replace the comment above `.dot.live.resting` (it begins `/* Out of session hours the stream is still up` and ends `the colour carries the state, the animation only ever carried the liveliness. */`) with:

```css
    /* Out of session hours the stream is still up but nothing is coming down
       it, and a pulse in that state claims activity that is not happening --
       it reads as "prices are moving" on an evening when they are not. The
       dot stays lit, because the connection genuinely is live; it just stops
       announcing traffic. Same reasoning as Motion = Off in
       styles/motion.css: the colour carries the state, the animation only
       ever carried the liveliness. */
```

Replace the comment above `/* Greyscale and amber base case` that reads

```css
    /* The blinking dot survives from the current UI; the card-flash does
       not. With push, "something changed" is continuous rather than a
       5-second event, so a flash would be a permanent flicker. */
```

with:

```css
    /* The blinking dot survives from the old UI; a card-wide flash on every
       push still does not -- with push, "something changed" is continuous,
       so it would be a permanent flicker. v168's motion is scoped instead:
       entrances once per route, flashes on the changed cell only. */
```

2. `frontend/src/app/shell/scan-progress.css`: delete

```css
@media (prefers-reduced-motion: reduce) {
  .strip { animation: none; }
  .fill { transition: none; }
  /* Still distinguishable from a determinate bar -- it just does not travel. */
  .fill.sweeping { animation: none; width: 100% !important; opacity: 0.4; }
}
```

3. `frontend/src/app/shell/shell.css`: delete

```css
@media (prefers-reduced-motion: reduce) {
  .shell, .shell.overlay .sidebar { transition: none; }
}
```

and the one-line

```css
@media (prefers-reduced-motion: reduce) { .route-loading-mark { animation: none; } }
```

4. `frontend/src/app/shell/tape/tape.css`: delete

```css
@media (prefers-reduced-motion: reduce) {
  .track { animation: none; }
  /* The track freezes at translateX(0); without a scroll affordance every
     name past the first viewport-width would be permanently unreachable. */
  .viewport { overflow-x: auto; }
}
```

5. `frontend/src/app/ui/data-table/data-table.ts`: delete

```css
    @media (prefers-reduced-motion: reduce) {
      .loading-spinner { animation-duration: 2.4s; }
    }
```

and

```css
    @media (prefers-reduced-motion: reduce) {
      .blink { animation: none; background: color-mix(in srgb, var(--warn) 10%, transparent); }
    }
```

and replace the comment above `.blink { animation: ...` that ends `Respects prefers-reduced-motion -- the row still needs telling apart, so it falls back to a steady tint rather than losing the signal entirely. */` with:

```css
    /* A pulse, not a hard on/off flash: WCAG's flash-rate guidance exists
       for a reason, and an opacity/background fade reads as "attention"
       without the seizure risk of a true blink. Under Motion = Off the row
       still needs telling apart, so styles/motion.css falls it back to a
       steady tint rather than losing the signal entirely. */
```

6. `frontend/src/app/ui/chart-container.ts`: delete

```css
    @media (prefers-reduced-motion: reduce) {
      .spinner {
        animation-duration: 2.4s;
      }
    }
```

7. `frontend/src/app/ui/status-indicator.ts`: delete

```css
    @media (prefers-reduced-motion: reduce) {
      .open { animation: none; }
    }
```

8. `frontend/src/app/ui/status-cell.ts`: delete the comment and block

```css
    /* The pulse says "this is live right now", which is exactly the kind of
       motion someone with vestibular sensitivity has asked the OS to stop. */
    @media (prefers-reduced-motion: reduce) {
      .dot { animation: none; }
      .fill { transition: none; }
    }
```

and put this one-line comment where they were:

```css
    /* Motion = Off steadies the dot and the fill: styles/motion.css. */
```

9. `frontend/src/app/workspaces/watchlist/watchlist.ts`: in the HTML comment, replace

```html
             uses) -- a gentle pulse, not a hard flash; see data-table.ts's
             .blink rule and its prefers-reduced-motion fallback. -->
```

with:

```html
             uses) -- a gentle pulse, not a hard flash; see data-table.ts's
             .blink rule and its Motion = Off fallback in styles/motion.css. -->
```

- [ ] **Step 6: Delete the global block and rewrite the decision comment in `tokens.css`**

In `frontend/src/styles/tokens.css`, delete the whole block (it sits after the `/* Breakpoints are 640 / 1024 / 1440 / 1920.` comment and before v167's `/* ===== Tier 3: component tokens (spec v167 §3) ===== */` banner):

```css
@media (prefers-reduced-motion: reduce) {
  :root {
    --dur-instant: 0ms;
    --dur-base: 0ms;
    --dur-slow: 0ms;
  }

  *,
  *::before,
  *::after {
    animation-duration: 0ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0ms !important;
    scroll-behavior: auto !important;
  }
}
```

(`scroll-behavior: auto !important` needs no replacement: `git grep scroll-behavior -- frontend/src` finds no `smooth` anywhere, so the line was guarding nothing.)

Then replace the "radii, motion" block comment, from `/* -- radii, motion ---` down to its closing ` */` (the line before `/* v80 D3: 2px, was 4px / 3px`), with:

```css
  /* -- radii, motion ---------------------------------------------------
   * Tight radii: terminal, not consumer app.
   *
   * Motion (spec v168). Entrances run once per route activation and never on
   * a push or a refetch -- the permanent flicker the old "nothing on
   * entrance" rule guarded against; RouteEntryService.claim() enforces it
   * now. The two push reactions that do run are scoped to the value that
   * changed: the cell flash and the count-up on a change.
   *
   *   --dur-instant  hover, press, focus ring
   *   --dur-base     state change, value flash, bar easing, Reduced fades
   *   --dur-slow     layout: sidebar, panel reflow
   *   --dur-enter, --dur-count, --dur-draw (tier 3): entrance, count-up, draw-in
   *
   * Every duration is multiplied by --motion-scale (tier 3): 1 normally, 0
   * under the shell's Motion = Off, which styles/motion.css sets.
   *
   * The OS reduced-motion setting is deliberately ignored (spec v168 D2).
   * Windows reports it whenever "Animation effects" is off, which is common
   * on laptops, and honouring it left this admin with no motion and no way
   * back. The shell's Motion control (On / Reduced / Off, persisted as
   * shell.motion) is the one switch; every Off and Reduced fallback lives in
   * styles/motion.css.
   */
```

The comment must not contain the media-feature name (the inverted `tokens.spec` case asserts it is absent from the whole file).

- [ ] **Step 7: Regenerate the token fixture**

Run: `python $WT/scripts/dev/dump_tokens.py`
Then: `python $WT/scripts/dev/dump_tokens.py --check`
Expected: the second command exits 0. The fixture may come out byte-identical (the resolver never read `@media` blocks); `git -C $WT diff --stat tests/charts/resolved_tokens.json` tells you. Stage it either way in Step 10; `git add` of an unchanged file is a no-op.

- [ ] **Step 8: Run the specs and the gates to verify they pass**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/motion-home.spec.ts --include src/app/ui/motion-css.spec.ts`
Expected: PASS, `0 failed`. Quote the `Tests  N passed (N)` line.

Run the component specs of every touched site: `npm --prefix $WT/frontend exec -- ng test --watch=false --include 'src/app/shell/**/*.spec.ts' --include 'src/app/ui/data-table/*.spec.ts' --include src/app/ui/chart-container.spec.ts --include src/app/ui/status-cell.spec.ts --include 'src/app/workspaces/watchlist/*.spec.ts'`
Expected: PASS, `0 failed`. Quote the verdict line.

Run the fixture's Python twin: `python $WT/scripts/dev/testrun.py file tests/dev/test_dump_tokens.py`
Expected: PASS. (v167 created this test; if the path differs, `git -C $WT grep -ln "resolved_tokens.json" -- tests` names it.)

- [ ] **Step 9: Prove the OS media feature is gone**

Run: `git -C $WT grep -n "(prefers-reduced-motion" -- frontend/src ':!*.spec.ts'`
Expected: no output.

Run: `git -C $WT grep -n "prefers-reduced-motion" -- frontend/src ':!*.spec.ts'`
Expected: one line only, `frontend/src/app/ui/flash.ts` (its doc comment; MO14 rewrites it). Anything else is a leftover from this task.

- [ ] **Step 10: Commit**

```bash
git -C $WT add frontend/src/styles/tokens.css frontend/src/styles/motion.css frontend/src/app/ui/tokens.spec.ts frontend/src/app/ui/motion-css.spec.ts frontend/src/app/ui/motion-home.spec.ts tests/charts/resolved_tokens.json frontend/src/app/shell/connection-status.ts frontend/src/app/shell/scan-progress.css frontend/src/app/shell/shell.css frontend/src/app/shell/tape/tape.css frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/chart-container.ts frontend/src/app/ui/status-indicator.ts frontend/src/app/ui/status-cell.ts frontend/src/app/workspaces/watchlist/watchlist.ts
git -C $WT commit -m "feat(v168): Motion=Off keeps every pre-v168 fallback; the OS reduced-motion setting is no longer read (MO6)

The global tokens.css media block and the eight component media blocks become
[data-motion=off] rules in styles/motion.css (tape also frozen under reduced and
pending). Spinners slow to 2.4s and never stop; the route spinner used to stop
(intended change, spec amendment 6). tokens.spec's reduced-motion case is inverted.

Narrow runs: <the Tests verdict lines from Step 8>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task MO7: `RouteEntryService` and the `[sbRouteEntrance]` route host on `div.workspace-content` (entrance plus CSS stagger)

**Model:** sonnet — router-event bookkeeping and one directive, rules given by the spec amendments

**Files:**
- Create: `frontend/src/app/ui/motion/route-entry.service.ts`
- Create: `frontend/src/app/ui/motion/route-entry.service.spec.ts`
- Create: `frontend/src/app/ui/motion/route-entrance.ts`
- Create: `frontend/src/app/ui/motion/route-entrance.spec.ts`
- Modify: `frontend/src/app/shell/shell.html`
- Modify: `frontend/src/app/shell/shell.ts`

**Interfaces:**
- Consumes (MO4): `MotionService.active` (`true` for `on` and `reduced`), `MotionStarts.record/count`, `provideMotion`. `BACKGROUND_REFRESH_INFO` from `frontend/src/app/routing/route-loading.service.ts` (exists, line 15: `{ backgroundRefresh: true } as const`). MO3's CSS: `.sb-entering` on the route host animates the host and staggers the direct children of the workspace's top-level `.sb-stack`, `.sb-row`, `sb-panel-grid`, `.sb-stagger` (60ms steps, cap 8; 40ms, cap 4 below 640px); `[data-motion=reduced]` turns it into a plain fade. This task adds no CSS.
- Produces: `pathOf(url: string): string`; `@Injectable({ providedIn: 'root' }) class RouteEntryService { readonly activation: Signal<number>; claim(key: string): boolean }`; `@Directive({ selector: '[sbRouteEntrance]' }) class RouteEntrance`; `export const ENTRANCE_FALLBACK_MS = 1000`. MO8, MO15 and MO17 call `claim(key)`; MO17 drives `activation` through a real router.

**The rules (spec §3, §4, amendment 3):**
- The activation id moves only when the **path** changes. A navigation whose `info` is `BACKGROUND_REFRESH_INFO`, a same-URL reload, and a query- or fragment-only change never move it.
- `info` is read while the navigation is in flight (`NavigationStart`, again at `RoutesRecognized`) through `router.currentNavigation()`, because `currentNavigation()` is null by `NavigationEnd`. The id commits at `NavigationEnd`, comparing `pathOf(urlAfterRedirects)` with the last committed path. A background refresh still records its path, without moving the id.
- Moving the id clears every spent claim. `claim(key)` is `true` the first time per key per activation, then `false`.
- If the service is created after the router has already navigated (the shell appears only once the session resolves), the current path is taken as committed, so the first real navigation is the first entrance.
- `RouteEntrance` spends `claim('route')` on every new activation, **then** animates only when `motion.active()`. Restart is remove, reflow, add. It records `'entrance'` with key `'route'`. The class is removed after `ENTRANCE_FALLBACK_MS`, sized to cover the longest stagger (8 × 60ms delay + 420ms `--dur-enter` = 900ms). It is **not** removed on the host's own `animationend`: that fires at 420ms, while staggered children are still running, and removing `.sb-entering` then would snap them to their final state. The class is inert once its animations end (fill mode `backwards`), so leaving it until the timer is harmless.
- Activation 0 (before any committed navigation) never animates: the cold-load first paint has no entrance (spec §1, "route transitions animate from the next navigation").

- [ ] **Step 1: Write the failing `RouteEntryService` spec**

Create `frontend/src/app/ui/motion/route-entry.service.spec.ts`:

```ts
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter, withRouterConfig } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { BACKGROUND_REFRESH_INFO } from '../../routing/route-loading.service';
import { RouteEntryService, pathOf } from './route-entry.service';

@Component({ template: '' })
class Blank {}

describe('pathOf', () => {
  it('drops the query string and the fragment', () => {
    expect(pathOf('/trades?tab=open')).toBe('/trades');
    expect(pathOf('/trades#top')).toBe('/trades');
    expect(pathOf('/trades/42?x=1#y')).toBe('/trades/42');
  });

  it('reads an empty URL as the root path', () => {
    expect(pathOf('')).toBe('/');
  });
});

describe('RouteEntryService (spec v168 §3)', () => {
  let router: Router;
  let entry: RouteEntryService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter(
          [
            { path: 'a', component: Blank },
            { path: 'b', component: Blank },
            { path: 'old', redirectTo: 'b' },
          ],
          withRouterConfig({ onSameUrlNavigation: 'reload' }),
        ),
      ],
    });
    router = TestBed.inject(Router);
    entry = TestBed.inject(RouteEntryService);
  });

  it('starts at 0 and moves on the first navigation', async () => {
    expect(entry.activation()).toBe(0);
    await router.navigateByUrl('/a');
    expect(entry.activation()).toBe(1);
  });

  it('moves on a path change', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/b');
    expect(entry.activation()).toBe(2);
  });

  it('does not move on a same-URL reload', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/a', { onSameUrlNavigation: 'reload' });
    expect(entry.activation()).toBe(1);
  });

  it('does not move on a query-only or a fragment-only change', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/a?tab=open');
    await router.navigateByUrl('/a#top');
    expect(entry.activation()).toBe(1);
  });

  it('does not move on a background refresh', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/a', {
      onSameUrlNavigation: 'reload',
      replaceUrl: true,
      info: BACKGROUND_REFRESH_INFO,
    });
    expect(entry.activation()).toBe(1);
  });

  it('compares the path after redirects', async () => {
    await router.navigateByUrl('/b');
    await router.navigateByUrl('/old');
    expect(entry.activation()).toBe(1);
  });

  it('a navigation after a background refresh is judged on its own info', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/a', { onSameUrlNavigation: 'reload', info: BACKGROUND_REFRESH_INFO });
    await router.navigateByUrl('/b');
    expect(entry.activation()).toBe(2);
  });

  it('claim() is true once per key per activation', async () => {
    await router.navigateByUrl('/a');
    expect(entry.claim('figure:Expectancy')).toBe(true);
    expect(entry.claim('figure:Expectancy')).toBe(false);
    expect(entry.claim('figure:Win rate')).toBe(true);
  });

  it('a background refresh keeps spent claims spent', async () => {
    await router.navigateByUrl('/a');
    entry.claim('route');
    await router.navigateByUrl('/a', { onSameUrlNavigation: 'reload', info: BACKGROUND_REFRESH_INFO });
    expect(entry.claim('route')).toBe(false);
  });

  it('a path change frees every claim again', async () => {
    await router.navigateByUrl('/a');
    entry.claim('route');
    await router.navigateByUrl('/b');
    expect(entry.claim('route')).toBe(true);
  });
});

describe('RouteEntryService created after the first navigation', () => {
  it('takes the current path as committed, so the same path does not count as new', async () => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{ path: 'a', component: Blank }, { path: 'b', component: Blank }],
          withRouterConfig({ onSameUrlNavigation: 'reload' })),
      ],
    });
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/a');
    const entry = TestBed.inject(RouteEntryService);
    await router.navigateByUrl('/a', { onSameUrlNavigation: 'reload' });
    expect(entry.activation()).toBe(0);
    await router.navigateByUrl('/b');
    expect(entry.activation()).toBe(1);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/route-entry.service.spec.ts`
Expected: FAIL, the build cannot resolve `./route-entry.service`.

- [ ] **Step 3: Implement `RouteEntryService`**

Create `frontend/src/app/ui/motion/route-entry.service.ts`:

```ts
import { Injectable, Signal, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  Event as RouterEvent,
  NavigationCancel,
  NavigationEnd,
  NavigationError,
  NavigationStart,
  Router,
  RoutesRecognized,
} from '@angular/router';

/** The path of a router URL: query string and fragment dropped. */
export function pathOf(url: string): string {
  const path = url.split(/[?#]/)[0];
  return path === '' ? '/' : path;
}

/** Same test as `RouteLoadingService`'s private one: the refresh passes
 *  `BACKGROUND_REFRESH_INFO` (`{ backgroundRefresh: true }`) as `info`. */
function isBackgroundRefresh(info: unknown): boolean {
  return typeof info === 'object' && info !== null
    && (info as { backgroundRefresh?: unknown }).backgroundRefresh === true;
}

/**
 * Once-per-route-activation bookkeeping for entrance motion (spec v168 §3, §4).
 *
 * `RouteRefreshService` re-runs the current route with a real `navigateByUrl`
 * on every relevant push, and `sb-async` destroys and re-creates its content on
 * every refetch. Either would replay an entrance if "first render" were the
 * trigger -- the permanent flicker the old "nothing on entrance" rule was
 * written against. So an entrance is keyed to an **activation id** that moves
 * only when the path changes, and every entrance consumer spends a
 * once-per-activation `claim(key)` before it animates. A re-created element
 * finds its claim already spent and renders its final state at once.
 *
 * `info` is read while the navigation is in flight: `currentNavigation()` is
 * null by `NavigationEnd`, where the id is committed.
 */
@Injectable({ providedIn: 'root' })
export class RouteEntryService {
  private readonly router = inject(Router);
  private readonly id = signal(0);
  private readonly claimed = new Set<string>();
  private committedPath: string | null = this.router.navigated ? pathOf(this.router.url) : null;
  private background = false;

  /** Moves by one per real path change; 0 until the first one. */
  readonly activation: Signal<number> = this.id.asReadonly();

  constructor() {
    this.router.events.pipe(takeUntilDestroyed()).subscribe((event) => this.onRouterEvent(event));
  }

  /** `true` the first time `key` asks within this activation, then `false`. */
  claim(key: string): boolean {
    if (this.claimed.has(key)) return false;
    this.claimed.add(key);
    return true;
  }

  private onRouterEvent(event: RouterEvent): void {
    if (event instanceof NavigationStart) this.background = false;
    if (event instanceof NavigationStart || event instanceof RoutesRecognized) {
      this.background ||= isBackgroundRefresh(this.router.currentNavigation()?.extras.info);
    } else if (event instanceof NavigationEnd) {
      this.commit(pathOf(event.urlAfterRedirects));
    } else if (event instanceof NavigationCancel || event instanceof NavigationError) {
      this.background = false;
    }
  }

  private commit(path: string): void {
    const background = this.background;
    const moved = path !== this.committedPath;
    this.background = false;
    this.committedPath = path;
    if (background || !moved) return;
    this.claimed.clear();
    this.id.update((n) => n + 1);
  }
}
```

If the compiler rejects `this.router.currentNavigation()` (a pre-signal router API), use the form `RouteLoadingService` already uses, `this.router.currentNavigation?.()?.extras.info`, and say so in the report.

- [ ] **Step 4: Run it to verify it passes**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/route-entry.service.spec.ts`
Expected: PASS, `Tests  13 passed (13)`.

- [ ] **Step 5: Write the failing `RouteEntrance` spec**

Create `frontend/src/app/ui/motion/route-entrance.spec.ts`:

```ts
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NavigationBehaviorOptions, Router, RouterOutlet, provideRouter, withRouterConfig } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { BACKGROUND_REFRESH_INFO } from '../../routing/route-loading.service';
import { MotionStarts } from './motion-starts';
import { MotionState, provideMotion } from './motion.service';
import { ENTRANCE_FALLBACK_MS, RouteEntrance } from './route-entrance';
import { RouteEntryService } from './route-entry.service';

@Component({ template: '<p>page</p>' })
class Page {}

@Component({
  imports: [RouterOutlet, RouteEntrance],
  template: '<div class="workspace-content" sbRouteEntrance><router-outlet /></div>',
})
class Host {}

interface Rig {
  fixture: ComponentFixture<Host>;
  host: HTMLElement;
  starts: MotionStarts;
  go(url: string, extras?: NavigationBehaviorOptions): Promise<void>;
}

function setup(mode: MotionState): Rig {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter(
        [{ path: 'a', component: Page }, { path: 'b', component: Page }],
        withRouterConfig({ onSameUrlNavigation: 'reload' }),
      ),
      provideMotion(mode),
    ],
  });
  const fixture = TestBed.createComponent(Host);
  fixture.detectChanges();
  const router = TestBed.inject(Router);
  return {
    fixture,
    host: (fixture.nativeElement as HTMLElement).querySelector('.workspace-content') as HTMLElement,
    starts: TestBed.inject(MotionStarts),
    async go(url, extras = {}) {
      await router.navigateByUrl(url, extras);
      fixture.detectChanges();
      await fixture.whenStable();
    },
  };
}

const BACKGROUND: NavigationBehaviorOptions = {
  onSameUrlNavigation: 'reload',
  replaceUrl: true,
  info: BACKGROUND_REFRESH_INFO,
};

describe('RouteEntrance (spec v168 §3 #1, #2)', () => {
  it('enters on a new path under On: adds sb-entering and records one entrance', async () => {
    const rig = setup('on');
    await rig.go('/a');
    expect(rig.host.classList).toContain('sb-entering');
    expect(rig.starts.count('entrance')).toBe(1);
    expect(rig.starts.entries()).toContainEqual({ kind: 'entrance', key: 'route' });
  });

  it('does not re-enter on a background refresh, a same-URL reload or a query change', async () => {
    const rig = setup('on');
    await rig.go('/a');
    await rig.go('/a', BACKGROUND);
    await rig.go('/a', { onSameUrlNavigation: 'reload' });
    await rig.go('/a?tab=open');
    expect(rig.starts.count('entrance')).toBe(1);
  });

  it('enters again on a path change', async () => {
    const rig = setup('on');
    await rig.go('/a');
    await rig.go('/b');
    expect(rig.starts.count('entrance')).toBe(2);
    expect(rig.host.classList).toContain('sb-entering');
  });

  it('still enters under Reduced (motion.css makes it a plain fade)', async () => {
    const rig = setup('reduced');
    await rig.go('/a');
    expect(rig.host.classList).toContain('sb-entering');
    expect(rig.starts.count('entrance')).toBe(1);
  });

  it('spends the claim but never animates under Off', async () => {
    const rig = setup('off');
    await rig.go('/a');
    expect(rig.host.classList).not.toContain('sb-entering');
    expect(rig.starts.count('entrance')).toBe(0);
    expect(TestBed.inject(RouteEntryService).claim('route')).toBe(false);
  });

  it('spends the claim but never animates while preferences are pending', async () => {
    const rig = setup('pending');
    await rig.go('/a');
    expect(rig.host.classList).not.toContain('sb-entering');
    expect(rig.starts.count('entrance')).toBe(0);
    expect(TestBed.inject(RouteEntryService).claim('route')).toBe(false);
  });

  it('has no entrance before the first committed navigation', () => {
    const rig = setup('on');
    expect(rig.host.classList).not.toContain('sb-entering');
    expect(rig.starts.count('entrance')).toBe(0);
  });

  it('removes sb-entering once the entrance window has passed', async () => {
    const rig = setup('on');
    await rig.go('/a');
    expect(rig.host.classList).toContain('sb-entering');
    await new Promise((resolve) => setTimeout(resolve, ENTRANCE_FALLBACK_MS + 50));
    expect(rig.host.classList).not.toContain('sb-entering');
  });
});
```

- [ ] **Step 6: Run it to verify it fails**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/route-entrance.spec.ts`
Expected: FAIL, the build cannot resolve `./route-entrance`.

- [ ] **Step 7: Implement `RouteEntrance`**

Create `frontend/src/app/ui/motion/route-entrance.ts`:

```ts
import { DestroyRef, Directive, ElementRef, effect, inject, untracked } from '@angular/core';

import { MotionStarts } from './motion-starts';
import { MotionService } from './motion.service';
import { RouteEntryService } from './route-entry.service';

/**
 * How long the route host keeps `.sb-entering`: the longest stagger delay
 * (8 children x 60ms) plus `--dur-enter` (420ms) is 900ms, rounded up.
 */
export const ENTRANCE_FALLBACK_MS = 1000;

const ENTERING = 'sb-entering';

/**
 * The route host (spec v168 §3 #1 and #2, amendment 2).
 *
 * Sits on the shell's persistent `div.workspace-content`, so the class has to
 * be re-triggered on each activation: remove, reflow, add. The entrance and the
 * CSS stagger of the workspace's top-level layout children both hang off
 * `.sb-entering` in `styles/motion.css`; this directive only decides *when*.
 *
 * It animates via `animation`, not the host's existing `.route-pending`
 * opacity `transition`, which stays as it is.
 *
 * The class is removed by the timer only. The host's own `animationend`
 * arrives at 420ms while staggered children are still running; removing the
 * class then would snap them to their final state.
 */
@Directive({ selector: '[sbRouteEntrance]' })
export class RouteEntrance {
  private readonly host: HTMLElement = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private readonly entry = inject(RouteEntryService);
  private readonly motion = inject(MotionService);
  private readonly starts = inject(MotionStarts);
  private seen = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    effect(() => {
      const id = this.entry.activation();
      untracked(() => this.onActivation(id));
    });
    inject(DestroyRef).onDestroy(() => this.finish());
  }

  /** The claim is always spent first; the mode only decides whether to play. */
  private onActivation(id: number): void {
    if (id === 0 || id === this.seen) return;
    this.seen = id;
    if (!this.entry.claim('route')) return;
    if (this.motion.active()) this.start();
  }

  private start(): void {
    this.finish();
    void this.host.offsetWidth;
    this.host.classList.add(ENTERING);
    this.starts.record('entrance', 'route');
    this.timer = setTimeout(() => this.finish(), ENTRANCE_FALLBACK_MS);
  }

  private finish(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.host.classList.remove(ENTERING);
  }
}
```

- [ ] **Step 8: Run it to verify it passes**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/route-entrance.spec.ts`
Expected: PASS, `Tests  8 passed (8)`.

- [ ] **Step 9: Put the route host on the shell**

In `frontend/src/app/shell/shell.html`, replace:

```html
      <div class="workspace-content" [attr.inert]="routeLoading.visible() ? '' : null"><router-outlet /></div>
```

with:

```html
      <div class="workspace-content" sbRouteEntrance [attr.inert]="routeLoading.visible() ? '' : null"><router-outlet /></div>
```

In `frontend/src/app/shell/shell.ts`, add the import below the `MotionService` import MO5 added:

```ts
import { RouteEntrance } from '../ui/motion/route-entrance';
```

and add `RouteEntrance` to the component's `imports` array, after `Tape`:

```ts
    Button, Icon, ProfileMenu, Tape, RouteEntrance,
```

- [ ] **Step 10: Run the motion specs and the shell spec**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/route-entry.service.spec.ts --include src/app/ui/motion/route-entrance.spec.ts --include src/app/shell/shell.spec.ts`
Expected: PASS, `0 failed`. Quote the verdict line. (Shell specs run under the global `provideMotion('off')`, so the host never gains the class there.)

- [ ] **Step 11: Commit**

```bash
git -C $WT add frontend/src/app/ui/motion/route-entry.service.ts frontend/src/app/ui/motion/route-entry.service.spec.ts frontend/src/app/ui/motion/route-entrance.ts frontend/src/app/ui/motion/route-entrance.spec.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.ts
git -C $WT commit -m "feat(v168): RouteEntryService activation id and the sbRouteEntrance route host (MO7)

The id moves only on a path change (not a background refresh, same-URL reload or
query/fragment change); claim() is once per key per activation. The shell's
workspace-content gains .sb-entering for the entrance and the CSS stagger.

Narrow run: <the Tests verdict line from Step 10>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

