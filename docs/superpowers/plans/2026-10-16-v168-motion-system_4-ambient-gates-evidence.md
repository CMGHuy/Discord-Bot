# v168 Motion system, part 4: chart draw-in, ambient cues, the no-replay gate, evidence, full suite (MO15..MO19)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task MO17:" -A 400 docs/superpowers/plans/2026-10-16-v168-motion-system_4-ambient-gates-evidence.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v168-motion-system-design.md`](../specs/2026-10-16-v168-motion-system-design.md) (its `## Amendments from the plan brief` bind and override earlier sections).
**Index:** [`2026-10-16-v168-motion-system_0-index.md`](2026-10-16-v168-motion-system_0-index.md): `## Global Constraints`, `## Where to work` (`$WT`, `$R`, the narrow-run command, `GATES`), `## Parallelisation` and the `## Task ledger` apply here and are not repeated.

**Consumed from earlier tasks (index ledger contracts):**
- MO3 `frontend/src/styles/motion.css`: keyframes `sb-draw-inset`, `sb-draw-circle`, `sb-ping`, `sb-ambient-drift`; classes `.sb-draw-in` / `.sb-draw-in-radial` (both `will-change: clip-path`, fill mode `backwards`, `none` under Reduced, Off and pending); `[data-motion=on] .ambient { animation: sb-ambient-drift 12s ease-in-out infinite alternate; }` (static below 640px); `[data-motion=reduced|off|pending] sb-connection-status .dot.live::after { animation: none; opacity: 0; }`.
- MO4 `frontend/src/app/ui/motion/motion.service.ts` (`MotionService.full`, `provideMotion`, `MotionState`), `frontend/src/app/ui/motion/motion-starts.ts` (`MotionStarts.record/count/entries/clear`), and the global `provideMotion('off')` default in `frontend/src/test-setup.ts`.
- MO7 `frontend/src/app/ui/motion/route-entry.service.ts` (`RouteEntryService.claim/activation`), `frontend/src/app/ui/motion/route-entrance.ts` (`RouteEntrance`, `ENTRANCE_FALLBACK_MS`).
- MO8 `frontend/src/app/ui/motion/count-up.ts` (`CountUp`, keys `figure:<label>`, `stat:<label>`), already wired into `sb-figure` and `sb-stat-tile`.
- MO9 `frontend/src/app/ui/async.ts` (`Async`, unchanged contract for `loading` / `emptyReason` / `emptyTitle`).
- MO10 `chart-container.ts` `.frame` carries `sb-panel sb-lift`; MO11 `shell.html` / `shell.css` carry the nav indicator; MO12 `exit.ts` and the drawer/dialog exits.

**Line numbers are pre-v167**; every edit is anchored on quoted text. If an anchor is missing, stop and report it.

**Ledger note (MO15):** `DrawIn` gains one optional input beyond the ledger shape, `drawReady = input(true)`. No other task consumes it. It exists because `chart-container`'s `.surface` is rendered from the first paint, while the chart is still loading. Without the input, the claim would be spent on the spinner and the chart would never draw in.

---

# Phase 4: draw-in, ambient cues, gates and evidence

### Task MO15: `[sbDrawIn]` clip-path reveal on sparkline, gauge, donut, dot-plot, chart-container

**Model:** sonnet — one directive applied to five primitives

**Files:**
- Create: `frontend/src/app/ui/motion/draw-in.ts`
- Create: `frontend/src/app/ui/motion/draw-in.spec.ts`
- Modify: `frontend/src/app/ui/sparkline.ts` (template `<svg ...>` and the `@Component` metadata)
- Modify: `frontend/src/app/ui/gauge.ts` (template `<svg viewBox="0 0 120 66" ...>` and metadata)
- Modify: `frontend/src/app/ui/donut.ts` (the minified template's `<svg viewBox="0 0 160 160" ...>` and `imports`)
- Modify: `frontend/src/app/ui/dot-plot.ts` (the minified template's `<svg [attr.viewBox]=...>`, `imports` and the import line)
- Modify: `frontend/src/app/ui/chart-container.ts` (the `<div #surface class="surface" ...>` line and `imports`)

**Interfaces:**
- Consumes: `RouteEntryService.claim(key: string): boolean` (MO7); `MotionService.full: Signal<boolean>` (MO4, `true` only for `on`); `MotionStarts.record('draw-in', key)` (MO4); `provideMotion` (MO4); the `.sb-draw-in` / `.sb-draw-in-radial` classes in `styles/motion.css` (MO3). This task adds no CSS.
- Produces: `export type DrawShape = 'inset' | 'circle'`; `export const DRAW_FALLBACK_MS = 1400`; `@Directive({ selector: '[sbDrawIn]' }) export class DrawIn { readonly sbDrawIn = input.required<string>(); readonly drawShape = input<DrawShape>('inset'); readonly drawReady = input(true); }`. Keys: `sparkline:<label>`, `gauge:<label>`, `donut`, `dot-plot:<yLabel>`, `chart:<caption or ''>`. MO17 mounts `sb-sparkline` and `sb-chart-container` and counts `'draw-in'` starts.

**Rules (spec §3 #9, §4, Testing):**
- The reveal is a `clip-path` animation on the chart's host element (the `<svg>`, or `chart-container`'s `.surface`). It is never a stroke-dash: no `getTotalLength`, no `stroke-dasharray` animation.
- The directive spends `claim(key)` **once per instance**, in an effect (at first render, never in the constructor), and only once `drawReady()` is `true`. It adds the class only when the claim was fresh **and** `motion.full()`. Under Reduced, Off and pending the claim is still spent and the chart renders unclipped.
- A second element with the same key in the same activation renders unclipped, and so does the same chart re-created by `sb-async` after a refetch. That is the "second claim renders unclipped" case of the Testing section.
- The class comes off on the host's **own** `animationend` (a bubbled child's does not count) or after `DRAW_FALLBACK_MS` (`--dur-draw` 1200ms plus margin), whichever is first, and on destroy. `will-change: clip-path` lives on the class, so it goes with it (§6).
- Two donuts on one page share the key `donut`, so only the first draws in per activation. That is the ledger's key, and it is accepted.

- [ ] **Step 1: Write the failing `DrawIn` spec**

Create `frontend/src/app/ui/motion/draw-in.spec.ts`:

```ts
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { ChartContainer } from '../chart-container';
import { DonutComponent } from '../donut';
import { DotPlot } from '../dot-plot';
import { Gauge } from '../gauge';
import { Sparkline } from '../sparkline';
import { DRAW_FALLBACK_MS, DrawIn, DrawShape } from './draw-in';
import { MotionStarts } from './motion-starts';
import { MotionState, provideMotion } from './motion.service';
import { RouteEntryService } from './route-entry.service';

function configure(mode: MotionState): void {
  TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection(), provideRouter([]), provideMotion(mode)],
  });
}

@Component({
  imports: [DrawIn],
  template: `@if (shown()) {
    <div class="chart" [sbDrawIn]="key()" [drawShape]="shape()" [drawReady]="ready()"><span class="inner"></span></div>
  }`,
})
class Host {
  readonly shown = signal(true);
  readonly key = signal('sparkline:Equity');
  readonly shape = signal<DrawShape>('inset');
  readonly ready = signal(true);
}

function mount(patch: (host: Host) => void = () => undefined) {
  const fixture = TestBed.createComponent(Host);
  patch(fixture.componentInstance);
  fixture.detectChanges();
  const chart = () => (fixture.nativeElement as HTMLElement).querySelector('.chart') as HTMLElement;
  return { fixture, chart, starts: TestBed.inject(MotionStarts), entry: TestBed.inject(RouteEntryService) };
}

describe('DrawIn (spec v168 §3 #9)', () => {
  it('under On clips the chart in with the inset reveal and records the start', () => {
    configure('on');
    const { chart, starts } = mount();
    expect(chart().classList).toContain('sb-draw-in');
    expect(starts.entries()).toContainEqual({ kind: 'draw-in', key: 'sparkline:Equity' });
  });

  it('uses the radial reveal for drawShape circle', () => {
    configure('on');
    const { chart } = mount((host) => host.shape.set('circle'));
    expect(chart().classList).toContain('sb-draw-in-radial');
    expect(chart().classList).not.toContain('sb-draw-in');
  });

  it('a second claim in the same activation renders unclipped', () => {
    configure('on');
    mount();
    const second = mount();
    expect(second.chart().classList).not.toContain('sb-draw-in');
    expect(second.starts.count('draw-in')).toBe(1);
  });

  it('re-created after a refetch, the chart does not draw in again', () => {
    configure('on');
    const { fixture, chart, starts } = mount();
    fixture.componentInstance.shown.set(false);
    fixture.detectChanges();
    fixture.componentInstance.shown.set(true);
    fixture.detectChanges();
    expect(chart().classList).not.toContain('sb-draw-in');
    expect(starts.count('draw-in')).toBe(1);
  });

  for (const mode of ['reduced', 'off', 'pending'] as const) {
    it(`spends the claim but never clips under ${mode}`, () => {
      configure(mode);
      const { chart, starts, entry } = mount();
      expect(chart().classList).not.toContain('sb-draw-in');
      expect(starts.count('draw-in')).toBe(0);
      expect(entry.claim('sparkline:Equity')).toBe(false);
    });
  }

  it('waits for drawReady before it claims, then draws in once ready', () => {
    configure('on');
    const { fixture, chart, starts } = mount((host) => host.ready.set(false));
    expect(chart().classList).not.toContain('sb-draw-in');
    expect(starts.count('draw-in')).toBe(0);
    fixture.componentInstance.ready.set(true);
    fixture.detectChanges();
    expect(chart().classList).toContain('sb-draw-in');
    expect(starts.count('draw-in')).toBe(1);
  });

  it("removes the class on its own animationend, not on a child's", () => {
    configure('on');
    const { chart } = mount();
    chart().querySelector('.inner')!.dispatchEvent(new Event('animationend', { bubbles: true }));
    expect(chart().classList).toContain('sb-draw-in');
    chart().dispatchEvent(new Event('animationend'));
    expect(chart().classList).not.toContain('sb-draw-in');
  });

  it('removes the class after DRAW_FALLBACK_MS when no animationend arrives', async () => {
    configure('on');
    const { chart } = mount();
    expect(chart().classList).toContain('sb-draw-in');
    await new Promise((resolve) => setTimeout(resolve, DRAW_FALLBACK_MS + 50));
    expect(chart().classList).not.toContain('sb-draw-in');
  });

  it('leaves no class behind when destroyed mid-reveal', () => {
    configure('on');
    const { fixture, chart } = mount();
    const element = chart();
    fixture.destroy();
    expect(element.classList).not.toContain('sb-draw-in');
  });
});

describe('the five chart primitives draw in (spec v168 §3 #9)', () => {
  function keys(): string[] {
    return TestBed.inject(MotionStarts).entries().filter((start) => start.kind === 'draw-in').map((start) => start.key);
  }

  it('sb-sparkline reveals its svg left to right', () => {
    configure('on');
    const f = TestBed.createComponent(Sparkline);
    f.componentRef.setInput('points', [1, 3, 2]);
    f.componentRef.setInput('label', 'Equity');
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('svg')!.classList).toContain('sb-draw-in');
    expect(keys()).toEqual(['sparkline:Equity']);
  });

  it('sb-gauge reveals its svg radially', () => {
    configure('on');
    const f = TestBed.createComponent(Gauge);
    f.componentRef.setInput('label', 'Heat utilisation');
    f.componentRef.setInput('value', 62);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('svg')!.classList).toContain('sb-draw-in-radial');
    expect(keys()).toEqual(['gauge:Heat utilisation']);
  });

  it('sb-donut reveals its svg radially', () => {
    configure('on');
    const f = TestBed.createComponent(DonutComponent);
    f.componentRef.setInput('slices', [
      { label: 'Win', count: 3, tone: 'pos' },
      { label: 'Loss', count: 2, tone: 'neg' },
    ]);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('svg')!.classList).toContain('sb-draw-in-radial');
    expect(keys()).toEqual(['donut']);
  });

  it('sb-dot-plot reveals its svg left to right', () => {
    configure('on');
    const f = TestBed.createComponent(DotPlot);
    f.componentRef.setInput('points', [{ label: 'MACD', n: 140, value: 0.2 }]);
    f.componentRef.setInput('floor', 20);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('svg')!.classList).toContain('sb-draw-in');
    expect(keys()).toEqual(['dot-plot:ExpR']);
  });

  it('sb-chart-container waits for the chart to be ready, then reveals the surface', () => {
    configure('on');
    const f = TestBed.createComponent(ChartContainer);
    f.componentRef.setInput('caption', 'Price');
    f.componentRef.setInput('loading', true);
    f.detectChanges();
    const surface = (f.nativeElement as HTMLElement).querySelector('.surface')!;
    expect(surface.classList).not.toContain('sb-draw-in');
    expect(keys()).toEqual([]);
    f.componentRef.setInput('loading', false);
    f.detectChanges();
    expect(surface.classList).toContain('sb-draw-in');
    expect(keys()).toEqual(['chart:Price']);
  });

  it('under the Off test default no primitive clips', () => {
    configure('off');
    const f = TestBed.createComponent(Sparkline);
    f.componentRef.setInput('points', [1, 3, 2]);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('svg')!.classList).not.toContain('sb-draw-in');
    expect(keys()).toEqual([]);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/draw-in.spec.ts`
Expected: FAIL, the build cannot resolve `./draw-in`.

- [ ] **Step 3: Implement `DrawIn`**

Create `frontend/src/app/ui/motion/draw-in.ts`:

```ts
import { DestroyRef, Directive, ElementRef, effect, inject, input, untracked } from '@angular/core';

import { MotionStarts } from './motion-starts';
import { MotionService } from './motion.service';
import { RouteEntryService } from './route-entry.service';

export type DrawShape = 'inset' | 'circle';

/** `--dur-draw` (1200ms) plus margin: the class never outlives a lost animationend by much. */
export const DRAW_FALLBACK_MS = 1400;

const CLASS_FOR: Record<DrawShape, string> = { inset: 'sb-draw-in', circle: 'sb-draw-in-radial' };

/**
 * Chart draw-in (spec v168 §3 #9): a `clip-path` reveal on the chart's host,
 * the same for SVG and canvas. Not a stroke-dash animation: jsdom has no
 * `getTotalLength()`, and the sparkline's non-scaling stroke measures dashes
 * in screen space but lengths in viewBox units.
 *
 * Spends `RouteEntryService.claim(key)` once per instance, after first render
 * and only once `drawReady` is true, whatever the mode; clips only when the
 * claim was fresh and Motion is On. A data update repaints without redrawing,
 * and a chart that `sb-async` re-creates after a refetch finds its claim
 * spent, so it shows at once.
 */
@Directive({ selector: '[sbDrawIn]' })
export class DrawIn {
  /** Stable per chart: `sparkline:<label>`, `gauge:<label>`, `donut`, `dot-plot:<yLabel>`, `chart:<caption>`. */
  readonly sbDrawIn = input.required<string>();
  readonly drawShape = input<DrawShape>('inset');
  /** False while the host shows a placeholder (chart-container loading): the claim waits. */
  readonly drawReady = input(true);

  private readonly host: Element = inject<ElementRef<Element>>(ElementRef).nativeElement;
  private readonly entry = inject(RouteEntryService);
  private readonly motion = inject(MotionService);
  private readonly starts = inject(MotionStarts);
  private spent = false;
  private playing: string | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;

  private readonly onEnd = (event: Event): void => {
    if (event.target === this.host) this.finish();
  };

  constructor() {
    effect(() => {
      if (!this.drawReady() || this.spent) return;
      untracked(() => this.begin());
    });
    inject(DestroyRef).onDestroy(() => this.finish());
  }

  /** The claim is always spent first; the mode only decides whether to clip. */
  private begin(): void {
    this.spent = true;
    const key = this.sbDrawIn();
    if (!this.entry.claim(key) || !this.motion.full()) return;
    this.start(CLASS_FOR[this.drawShape()], key);
  }

  private start(cls: string, key: string): void {
    this.playing = cls;
    this.host.classList.add(cls);
    this.host.addEventListener('animationend', this.onEnd);
    this.starts.record('draw-in', key);
    this.timer = setTimeout(() => this.finish(), DRAW_FALLBACK_MS);
  }

  private finish(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.host.removeEventListener('animationend', this.onEnd);
    if (this.playing !== null) this.host.classList.remove(this.playing);
    this.playing = null;
  }
}
```

- [ ] **Step 4: Run the directive cases to verify they pass**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/draw-in.spec.ts`
Expected: the 11 `DrawIn (spec v168 §3 #9)` cases and the Off primitive case pass. The five other primitive cases still fail, because no `svg` has the class yet.

- [ ] **Step 5: Wire `sb-sparkline`**

In `frontend/src/app/ui/sparkline.ts`:

1. Below `import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';` add:

```ts

import { DrawIn } from './motion/draw-in';
```

2. In the `@Component` metadata, after `changeDetection: ChangeDetectionStrategy.OnPush,` add:

```ts
  imports: [DrawIn],
```

3. In the template, replace:

```html
      <svg
        [attr.viewBox]="viewBox"
        preserveAspectRatio="none"
        role="img"
        [attr.aria-label]="ariaLabel()"
      >
```

with:

```html
      <svg
        [attr.viewBox]="viewBox"
        preserveAspectRatio="none"
        role="img"
        [attr.aria-label]="ariaLabel()"
        [sbDrawIn]="'sparkline:' + label()"
      >
```

- [ ] **Step 6: Wire `sb-gauge`**

In `frontend/src/app/ui/gauge.ts`:

1. Below `import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';` add:

```ts

import { DrawIn } from './motion/draw-in';
```

2. After `changeDetection: ChangeDetectionStrategy.OnPush,` add `  imports: [DrawIn],`.

3. Replace `<svg viewBox="0 0 120 66" width="100%" aria-hidden="true">` with:

```html
      <svg viewBox="0 0 120 66" width="100%" aria-hidden="true" [sbDrawIn]="'gauge:' + label()" [drawShape]="'circle'">
```

- [ ] **Step 7: Wire `sb-donut`**

In `frontend/src/app/ui/donut.ts` (a minified file, edit only these three spots):

1. Below `import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';` add:

```ts
import { DrawIn } from './motion/draw-in';
```

2. Change `imports: [DecimalPipe],` to `imports: [DecimalPipe, DrawIn],`.

3. In the template string replace `<svg viewBox="0 0 160 160" role="img" [attr.aria-label]="summary()">` with:

```html
<svg viewBox="0 0 160 160" role="img" [attr.aria-label]="summary()" [sbDrawIn]="'donut'" [drawShape]="'circle'">
```

- [ ] **Step 8: Wire `sb-dot-plot`**

In `frontend/src/app/ui/dot-plot.ts` (minified, edit only these three spots):

1. On the first line, change the tail `import { ChartTooltip, HoverState, hoverPosition } from './chart-tooltip';` to `import { ChartTooltip, HoverState, hoverPosition } from './chart-tooltip'; import { DrawIn } from './motion/draw-in';` (same line).

2. Change `imports:[ChartTooltip]` to `imports:[ChartTooltip,DrawIn]`.

3. In the template replace `<svg [attr.viewBox]="'0 0 '+w+' '+h" width="100%" [attr.height]="h" role="img" [attr.aria-label]="yLabel()+' against sample size'">` with:

```html
<svg [attr.viewBox]="'0 0 '+w+' '+h" width="100%" [attr.height]="h" role="img" [attr.aria-label]="yLabel()+' against sample size'" [sbDrawIn]="'dot-plot:'+yLabel()">
```

- [ ] **Step 9: Wire `sb-chart-container`**

In `frontend/src/app/ui/chart-container.ts`:

1. Below `import { EmptyStateComponent } from './empty-state';` add:

```ts
import { DrawIn } from './motion/draw-in';
```

2. Change `imports: [EmptyStateComponent],` to `imports: [EmptyStateComponent, DrawIn],`.

3. Replace the line:

```html
      <div #surface class="surface" [class.hidden]="state() !== 'ready'">
```

with:

```html
      <div #surface class="surface" [class.hidden]="state() !== 'ready'"
           [sbDrawIn]="'chart:' + (caption() ?? '')" [drawReady]="state() === 'ready'">
```

The surface is still always rendered (the comment above it says why). The reveal clips the projected canvas and waits for `ready`, so it never spends its claim on the spinner.

- [ ] **Step 10: Run the new spec and every spec that renders the five primitives**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/draw-in.spec.ts --include src/app/ui/gauge.spec.ts --include src/app/ui/dot-plot.spec.ts --include src/app/ui/chart-container.spec.ts --include src/app/ui/stat-tile.spec.ts --include 'src/app/ui/chart/**/*.spec.ts' --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/motion-home.spec.ts`
Expected: PASS, `0 failed`; `draw-in.spec.ts` contributes 17 tests. Quote the verdict line.

If a pre-existing spec fails with a `NullInjectorError` naming `Router` (the directive reaches `RouteEntryService`, which injects the router), add `provideRouter([])` from `@angular/router` to that spec's `configureTestingModule` providers and name the spec in the report. Any other failure is a behaviour change: stop and report it.

Then run the workspaces that draw these charts, still under the Off default:

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include 'src/app/workspaces/dashboard/**/*.spec.ts' --include 'src/app/workspaces/risk/**/*.spec.ts' --include 'src/app/workspaces/trades/**/*.spec.ts' --include 'src/app/workspaces/analytics/**/*.spec.ts' --include 'src/app/workspaces/gallery/**/*.spec.ts'`
Expected: PASS, `0 failed`. Quote the verdict line.

- [ ] **Step 11: Prove the mechanism**

Run: `git -C $WT grep -nE "getTotalLength|getAnimations" -- frontend/src/app ':!*.spec.ts'`
Expected: no output.

Run: `git -C $WT grep -n "sbDrawIn\]" -- frontend/src/app ':!*.spec.ts'`
Expected: exactly five lines, one in each of `sparkline.ts`, `gauge.ts`, `donut.ts`, `dot-plot.ts`, `chart-container.ts`.

- [ ] **Step 12: Commit**

```bash
git -C $WT add frontend/src/app/ui/motion/draw-in.ts frontend/src/app/ui/motion/draw-in.spec.ts frontend/src/app/ui/sparkline.ts frontend/src/app/ui/gauge.ts frontend/src/app/ui/donut.ts frontend/src/app/ui/dot-plot.ts frontend/src/app/ui/chart-container.ts
git -C $WT commit -m "feat(v168): sbDrawIn clip-path reveal on sparkline, gauge, donut, dot-plot and chart-container (MO15)

One directive for SVG and canvas: inset reveal, radial for gauge and donut.
The claim is spent once per instance after first render (chart-container waits
for ready), so data updates and refetches repaint without redrawing. Clips only
under Motion=On; the class comes off on its own animationend or after 1400ms.

Narrow runs: <the Tests verdict lines from Step 10>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task MO16: Ambient live cues: one drifting glow layer moved off `body`, live-dot ping, accent scan sweep

**Model:** sonnet — a stacking change in the shell plus two small CSS restyles and a gate edit

**Files:**
- Modify: `frontend/src/styles.css` (the `body` rule, v167 AN9's `background: var(--glow-ambient), var(--bg);`)
- Modify: `frontend/src/app/ui/elevation.spec.ts` (v167 AN9's case `grounds the page on the ambient glow over --bg`)
- Modify: `frontend/src/app/shell/shell.html` (first child of `div.shell`)
- Modify: `frontend/src/app/shell/shell.css` (the `.shell` rule; a new `.ambient` rule)
- Modify: `frontend/src/app/shell/shell.spec.ts` (one DOM case; a new `describe('ambient live cues (v168 §3 #10)')`)
- Modify: `frontend/src/app/shell/connection-status.ts` (the `.dot` rule; a `.dot.live::after` ring)
- Modify: `frontend/src/app/shell/scan-progress.css` (the `.fill.sweeping` rule)

**Interfaces:**
- Consumes: MO3's `motion.css` rules, unchanged here: `[data-motion=on] .ambient { animation: sb-ambient-drift 12s ease-in-out infinite alternate; }` (and `animation: none` below 640px); `[data-motion=reduced|off|pending] sb-connection-status .dot.live::after { animation: none; opacity: 0; }`; keyframes `sb-ping`, `sb-scan-sweep`. MO6's Off fallbacks for the live dot and the sweep (`width: 100%; opacity: .4`), unchanged. v167 AN8's `--glow-ambient` token and AN11's `allSources()` / `stripComments()` from `frontend/src/app/ui/testing/all-sources.ts`.
- Produces: `styles.css` `body { background: var(--bg); }`; `shell.html` first child `<div class="ambient" aria-hidden="true"></div>`; `shell.css` `.shell { ... isolation: isolate; }` and `.ambient { position: fixed; inset: -10%; z-index: -1; pointer-events: none; background: var(--glow-ambient); }`; `elevation.spec.ts` case `the ambient glow is one shell layer, not the body`; connection-status `.dot.live::after` ring. MO18 shoots the result.

**Rules (spec §3 #10, §5, §6, amendment 9):**
- **Exactly one glow per page.** After this task `var(--glow-ambient)` is painted from `shell.css` only: not `body`, not a panel. The layer is one element in the shell, not one per panel (§6).
- The layer is the shell's **first child**, `position: fixed`, so it takes no grid cell. `z-index: -1` inside the shell's own stacking context (`isolation: isolate` on `.shell`) puts it above `body`'s `--bg` and below every pane. `pointer-events: none`, so it never takes a click.
- It drifts on a 12s alternate `transform` loop under On only, and stays static below 640px (MO3's `motion.css`). `inset: -10%` leaves room for the drift, so no edge comes into view. This task adds no animation to `.ambient` itself: the gate below asserts it has none outside `motion.css`.
- The live-dot ping is a `::after` ring that inherits the dot's colour (so `bot-up` green rings green). It is suppressed when the dot is `resting` (no traffic out of session hours: a ping would claim activity that is not happening) and when the bot is down. `motion.css` stills it under Reduced, Off and pending.
- The scan sweep keeps its keyframe, duration and Off fallback; only its paint becomes an accent gradient. `.strip.stalled .fill` and `.strip.complete .fill` (specificity 0,3,0) still win over `.fill.sweeping` (0,2,0).
- The login page is outside the shell and gets its own glow in v169; nothing here touches it.

- [ ] **Step 1: Rewrite v167's body-glow case**

In `frontend/src/app/ui/elevation.spec.ts`, replace the whole case:

```ts
  it('grounds the page on the ambient glow over --bg', () => {
    expect(GLOBAL).toMatch(/body\s*\{[^}]*background:\s*var\(--glow-ambient\),\s*var\(--bg\);/s);
  });
```

with:

```ts
  /* v168 §3 #10 (amendment 9): the glow moved off body onto one fixed shell
   * layer, so there is exactly one per page and it can drift. */
  it('the ambient glow is one shell layer, not the body', () => {
    expect(GLOBAL).toMatch(/body\s*\{[^}]*background:\s*var\(--bg\);/s);
    expect(stripComments(GLOBAL)).not.toContain('--glow-ambient');
    const painters = allSources()
      .filter(({ source }) => stripComments(source).includes('var(--glow-ambient)'))
      .map(({ name }) => name);
    expect(painters).toEqual(['app/shell/shell.css']);
    const shellHtml = readFileSync(join(process.cwd(), 'src/app/shell/shell.html'), 'utf8');
    expect(shellHtml.match(/class="ambient"/g)).toHaveLength(1);
  });
```

At the top of the file, below the existing `vitest` import, add:

```ts

import { allSources, stripComments } from './testing/all-sources';
```

(If v167 AN11 exported `stripComments` from a different module than `all-sources.ts`, run `git -C $WT grep -n "export function stripComments" -- frontend/src/app` and import it from there. Do not write a second copy.)

- [ ] **Step 2: Add the shell cases**

In `frontend/src/app/shell/shell.spec.ts`, inside `describe('shell navigation', ...)`, after the case `it('overlays the scan progress strip on the workspace rather than reflowing it', ...)`, add:

```ts
  it("paints the ambient glow as the shell's first child, hidden from assistive tech (v168 §3 #10)", () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const shell = (f.nativeElement as HTMLElement).querySelector('.shell') as HTMLElement;

    const first = shell.firstElementChild as HTMLElement;
    expect(first.classList).toContain('ambient');
    expect(first.getAttribute('aria-hidden')).toBe('true');
    expect(first.children).toHaveLength(0);
    expect(shell.querySelectorAll('.ambient')).toHaveLength(1);
  });
```

At the end of the file, after `describe('shell.css breakpoints', ...)`, add:

```ts
describe('ambient live cues (v168 §3 #10)', () => {
  const read = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');

  /** The first `<selector> { ... }` rule, verbatim. */
  function ruleOf(css: string, selector: string): string {
    const at = css.indexOf(`${selector} {`);
    expect(at, selector).toBeGreaterThanOrEqual(0);
    return css.slice(at, css.indexOf('}', at) + 1);
  }

  it('isolates the shell, so the fixed glow layer sits above --bg and under every pane', () => {
    const css = read('src/app/shell/shell.css');
    expect(ruleOf(css, '.shell')).toContain('isolation: isolate;');
    const ambient = ruleOf(css, '.ambient');
    for (const declaration of [
      'position: fixed;',
      'inset: -10%;',
      'z-index: -1;',
      'pointer-events: none;',
      'background: var(--glow-ambient);',
    ]) {
      expect(ambient).toContain(declaration);
    }
    // The drift lives in styles/motion.css, per mode (On only, static on a phone).
    expect(ambient).not.toContain('animation');
  });

  it('rings the live dot with a ping, never while resting or with the bot down', () => {
    const source = read('src/app/shell/connection-status.ts');
    expect(source).toMatch(/\.dot\s*\{[^}]*position:\s*relative;/s);
    expect(source).toMatch(/\.dot\.live::after\s*\{[^}]*animation:\s*sb-ping 2s ease-out infinite;/s);
    expect(source).toMatch(/\.dot\.live::after\s*\{[^}]*background:\s*inherit;/s);
    expect(source).toMatch(
      /\.dot\.live\.resting::after,\s*\.dot\.bot-down::after\s*\{\s*animation:\s*none;\s*opacity:\s*0;\s*\}/s,
    );
  });

  it('sweeps the scan strip with an accent gradient, same keyframe and timing', () => {
    const css = read('src/app/shell/scan-progress.css');
    expect(css).toMatch(/\.fill\.sweeping\s*\{[^}]*background:\s*linear-gradient\(90deg, transparent, var\(--accent\)\);/s);
    expect(css).toMatch(/\.fill\.sweeping\s*\{[^}]*animation:\s*sb-scan-sweep 1\.4s ease-in-out infinite;/s);
  });
});
```

Then check that no existing shell case depends on the old first child:

Run: `git -C $WT grep -nE "firstElementChild|children\[0\]|:first-child" -- frontend/src/app/shell/shell.spec.ts frontend/src/app/shell/shell.css`
Expected: only the new case. If an older case or a `:first-child` rule names `.shell`'s first child (the menu button), stop and report it; do not reorder the shell.

- [ ] **Step 3: Run them to verify they fail**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/elevation.spec.ts --include src/app/shell/shell.spec.ts`
Expected: FAIL in `the ambient glow is one shell layer, not the body` (body still paints the glow), `paints the ambient glow as the shell's first child ...` (no `.ambient`), and all three `ambient live cues` cases. Every other case passes.

- [ ] **Step 4: Take the glow off `body`**

In `frontend/src/styles.css`, in the `body` rule, replace:

```css
  background: var(--glow-ambient), var(--bg);
```

with:

```css
  /* The ambient glow is the shell's one fixed .ambient layer (v168 §3 #10),
   * not this background: a layer can drift without repainting the page, and
   * there is never a second glow. */
  background: var(--bg);
```

- [ ] **Step 5: Add the layer to the shell**

In `frontend/src/app/shell/shell.html`, directly after the opening tag:

```html
<div class="shell" [class.railed]="railed()" [class.overlay]="overlay()"
     [class.overlay-open]="overlayOpen()">
```

insert, before the `<!-- Below sm the sidebar is an overlay, ...` comment:

```html
  <!-- v168 §3 #10: the page's one ambient glow, under everything (shell.css). -->
  <div class="ambient" aria-hidden="true"></div>
```

In `frontend/src/app/shell/shell.css`, in the first `.shell` rule, after the line `transition: grid-template-columns var(--dur-slow) var(--ease-spring);` add:

```css
  /* Its own stacking context, so the .ambient layer's z-index -1 lands
     above body's --bg and below every pane (v168 §3 #10). */
  isolation: isolate;
```

and directly after that `.shell { ... }` rule's closing `}` add:

```css

/* The page's one ambient glow (v168 §3 #10), moved off body. Fixed, so it
   takes no grid cell and stays put while the panes scroll; -10% leaves room
   for the drift, which styles/motion.css runs under Motion=On only (static
   below 640px). The login page is outside the shell and has no glow until
   v169. */
.ambient {
  position: fixed;
  inset: -10%;
  z-index: -1;
  pointer-events: none;
  background: var(--glow-ambient);
}
```

- [ ] **Step 6: Ring the live dot**

In `frontend/src/app/shell/connection-status.ts`, in the styles:

1. In the `.dot { ... }` rule, after `background: var(--text-faint);` add `      position: relative;`.

2. Directly after the line `    .dot.bot-down { background: var(--neg); animation: none; }` add:

```css
    /* v168 §3 #10: a ring spreading out from the live dot. It inherits the
       dot's colour (bot-up rings green). Not while resting: out of session
       hours a ping would claim traffic that is not coming. Not with the bot
       down. styles/motion.css stills it under Reduced, Off and pending. */
    .dot.live::after {
      content: '';
      position: absolute;
      inset: 0;
      border-radius: 50%;
      background: inherit;
      opacity: 0;
      pointer-events: none;
      animation: sb-ping 2s ease-out infinite;
    }
    .dot.live.resting::after, .dot.bot-down::after { animation: none; opacity: 0; }
```

- [ ] **Step 7: Paint the sweep with the accent gradient**

In `frontend/src/app/shell/scan-progress.css`, replace the rule (its `animation` line reads `sb-scan-sweep` since MO3):

```css
.fill.sweeping {
  width: 35% !important;
  transition: none;
  animation: sb-scan-sweep 1.4s ease-in-out infinite;
}
```

with:

```css
.fill.sweeping {
  width: 35% !important;
  transition: none;
  /* v168 §3 #10: a comet rather than a block, fading in from its tail. */
  background: linear-gradient(90deg, transparent, var(--accent));
  animation: sb-scan-sweep 1.4s ease-in-out infinite;
}
```

If MO6 left a different body in that rule, keep it and add only the comment and the `background` line before `animation`.

- [ ] **Step 8: Run the specs and the gates**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/elevation.spec.ts --include src/app/shell/shell.spec.ts --include src/app/shell/connection-status.spec.ts --include src/app/shell/scan-progress.spec.ts --include src/app/ui/motion-css.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/motion-home.spec.ts`
Expected: PASS, `0 failed`. Quote the verdict line. (`motion-home.spec.ts` confirms `sb-ping` is a keyframe that `motion.css` defines; `primitives.spec.ts` confirms the new CSS carries no colour literal and no non-inset shadow.)

- [ ] **Step 9: Prove there is one glow**

Run: `git -C $WT grep -n "glow-ambient" -- frontend/src ':!*.spec.ts'`
Expected: exactly two lines, the definition in `frontend/src/styles/tokens.css` and `background: var(--glow-ambient);` in `frontend/src/app/shell/shell.css`.

Run: `python $WT/scripts/dev/dump_tokens.py --check`
Expected: exit 0 (no token changed).

- [ ] **Step 10: Commit**

```bash
git -C $WT add frontend/src/styles.css frontend/src/app/ui/elevation.spec.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts frontend/src/app/shell/connection-status.ts frontend/src/app/shell/scan-progress.css
git -C $WT commit -m "feat(v168): ambient live cues -- one shell glow layer off body, live-dot ping, accent sweep (MO16)

v167's body glow moves onto one fixed .ambient layer, the shell's first
child, in the shell's own stacking context; motion.css drifts it under
Motion=On only. Exactly one glow per page (elevation.spec). The live dot
gains a ping ring (not while resting or with the bot down); the scan sweep
is painted as an accent gradient.

Narrow run: <the Tests verdict line from Step 8>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task MO17: No-replay gate

**Model:** sonnet — one integration spec over a real router, rules fixed by spec §4

**Files:**
- Create: `frontend/src/app/ui/motion/no-replay.spec.ts`

**Interfaces:**
- Consumes: `RouteEntrance` (MO7, `frontend/src/app/ui/motion/route-entrance.ts`); `RouteEntryService` (MO7); `CountUp` as wired into `sb-figure` (key `figure:<label>`) and `sb-stat-tile` (key `stat:<label>`) (MO8); `DrawIn` as wired into `sb-sparkline` (key `sparkline:<label>`) and `sb-chart-container` (key `chart:<caption>`) (MO15); `Async` (MO9); `MotionStarts.count/entries` and `provideMotion` (MO4). Existing: `RouteRefreshService.requestMutationRefresh()` (`frontend/src/app/routing/route-refresh.service.ts`), `BACKGROUND_REFRESH_INFO` and `LIVE_REFRESH_DEBOUNCE_MS` (`frontend/src/app/routing/route-loading.service.ts:5,15`), `EventStream` (`frontend/src/app/api/event-stream.ts`; the refresh service reads only `.raised`).
- Produces: nothing consumed later. MO19 runs it inside the whole frontend run.

**What the gate proves (spec §4):** nothing re-enters on a push or a refetch. It mounts a workspace under Motion=On behind the real route host and lets the first activation's starts happen. Then it drives **both** replay paths: (a) `RouteRefreshService`'s own background refresh, a real `navigateByUrl` carrying `BACKGROUND_REFRESH_INFO`, and (b) the page's `sb-async` going loading → content, which destroys and re-creates every projected child. It asserts zero new `entrance` (the CSS stagger rides on it), `count-first` or `draw-in` starts. A same-URL reload and a query-only change are held to the same rule. The last case changes the path and asserts that the starts happen again, so the gate cannot pass by never animating at all.

jsdom has no `getAnimations()` and never fires `animationstart`, so the `MotionStarts` log is the observable. `requestAnimationFrame` is stubbed so the count-up never needs a real frame: its start is recorded before the first frame.

- [ ] **Step 1: Write the gate**

Create `frontend/src/app/ui/motion/no-replay.spec.ts`:

```ts
import { Component, Injectable, inject, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, RouterOutlet, provideRouter, withRouterConfig } from '@angular/router';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../../api/event-stream';
import { BACKGROUND_REFRESH_INFO, LIVE_REFRESH_DEBOUNCE_MS } from '../../routing/route-loading.service';
import { RouteRefreshService } from '../../routing/route-refresh.service';
import { Async } from '../async';
import { ChartContainer } from '../chart-container';
import { Figure } from '../figure';
import { Sparkline } from '../sparkline';
import { StatTile } from '../stat-tile';
import { MotionStartKind, MotionStarts } from './motion-starts';
import { provideMotion } from './motion.service';
import { RouteEntrance } from './route-entrance';

/**
 * The no-replay gate (spec v168 §4). Entrance-type motion (route entrance and
 * CSS stagger, first count-up, draw-in) runs once per route activation. A
 * background refresh or an sb-async refetch must never start one again.
 */

/** The page's fetch state: flipping it is what a refetch does to sb-async. */
@Injectable({ providedIn: 'root' })
class PageData {
  readonly loading = signal(false);
}

@Component({
  imports: [Async, Figure, StatTile, Sparkline, ChartContainer],
  template: `
    <div class="sb-stack">
      <sb-async [loading]="data.loading()" emptyReason="no-data-yet" emptyTitle="Nothing yet">
        <sb-figure label="Expectancy" [value]="0.42" />
        <sb-stat-tile label="Win rate" value="54.2%" />
        <sb-sparkline label="Equity" [points]="[1, 3, 2]" />
        <sb-chart-container caption="Price"><canvas></canvas></sb-chart-container>
      </sb-async>
    </div>
  `,
})
class Page {
  protected readonly data = inject(PageData);
}

/** The shell's routed host, as shell.html has it. */
@Component({
  imports: [RouterOutlet, RouteEntrance],
  template: '<div class="workspace-content" sbRouteEntrance><router-outlet /></div>',
})
class Host {}

/** The kinds that must never replay. `count-change` and `flash` are the intended push reactions. */
const ENTRANCE_KINDS: readonly MotionStartKind[] = ['entrance', 'count-first', 'draw-in'];

function tally(starts: MotionStarts): Record<string, number> {
  return Object.fromEntries(ENTRANCE_KINDS.map((kind) => [kind, starts.count(kind)]));
}

interface Rig {
  fixture: ComponentFixture<Host>;
  router: Router;
  starts: MotionStarts;
  data: PageData;
  settle(): Promise<void>;
  go(url: string): Promise<void>;
  query(selector: string): Element | null;
}

function setup(): Rig {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter(
        [{ path: 'a', component: Page }, { path: 'b', component: Page }],
        withRouterConfig({ onSameUrlNavigation: 'reload' }),
      ),
      provideMotion('on'),
      { provide: EventStream, useValue: { raised: new Subject<string>() } },
    ],
  });
  const fixture = TestBed.createComponent(Host);
  fixture.detectChanges();
  const router = TestBed.inject(Router);
  const settle = async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  };
  return {
    fixture,
    router,
    starts: TestBed.inject(MotionStarts),
    data: TestBed.inject(PageData),
    settle,
    async go(url) {
      await router.navigateByUrl(url);
      await settle();
    },
    query: (selector) => (fixture.nativeElement as HTMLElement).querySelector(selector),
  };
}

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', () => 0);
  vi.stubGlobal('cancelAnimationFrame', () => undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('no replay on a push or a refetch (spec v168 §4)', () => {
  it('the first activation starts the entrance, the first count-ups and the draw-ins', async () => {
    const rig = setup();
    await rig.go('/a');
    const entries = rig.starts.entries();
    expect(entries).toContainEqual({ kind: 'entrance', key: 'route' });
    expect(entries).toContainEqual({ kind: 'count-first', key: 'figure:Expectancy' });
    expect(entries).toContainEqual({ kind: 'count-first', key: 'stat:Win rate' });
    expect(entries).toContainEqual({ kind: 'draw-in', key: 'sparkline:Equity' });
    expect(entries).toContainEqual({ kind: 'draw-in', key: 'chart:Price' });
    expect(rig.starts.count('entrance')).toBe(1);
  });

  it("(a) RouteRefreshService's background refresh starts nothing new", async () => {
    const rig = setup();
    const refresh = TestBed.inject(RouteRefreshService);
    await rig.go('/a');
    const before = tally(rig.starts);
    const navigate = vi.spyOn(rig.router, 'navigateByUrl');

    refresh.requestMutationRefresh();
    await new Promise((resolve) => setTimeout(resolve, LIVE_REFRESH_DEBOUNCE_MS + 100));
    expect(navigate).toHaveBeenCalledWith('/a', {
      onSameUrlNavigation: 'reload',
      replaceUrl: true,
      info: BACKGROUND_REFRESH_INFO,
    });
    await navigate.mock.results[0]!.value;
    await rig.settle();

    expect(tally(rig.starts)).toEqual(before);
  });

  it('(b) sb-async going loading -> content re-creates the children but starts nothing new', async () => {
    const rig = setup();
    await rig.go('/a');
    const before = tally(rig.starts);

    rig.data.loading.set(true);
    await rig.settle();
    expect(rig.query('sb-figure')).toBeNull();
    rig.data.loading.set(false);
    await rig.settle();
    expect(rig.query('sb-figure')).not.toBeNull();

    expect(tally(rig.starts)).toEqual(before);
    expect(rig.starts.count('count-change')).toBe(0);
    expect(rig.query('sb-sparkline svg')!.classList).not.toContain('sb-draw-in');
    expect(rig.query('sb-figure .value')!.textContent!.trim()).toBe('0.42');
  });

  it('a same-URL reload and a query-only change start nothing new', async () => {
    const rig = setup();
    await rig.go('/a');
    const before = tally(rig.starts);

    await rig.router.navigateByUrl('/a', { onSameUrlNavigation: 'reload' });
    await rig.settle();
    await rig.go('/a?tab=open');
    await rig.go('/a#top');

    expect(tally(rig.starts)).toEqual(before);
  });

  it('a path change starts every entrance kind again', async () => {
    const rig = setup();
    await rig.go('/a');
    const first = tally(rig.starts);
    for (const kind of ENTRANCE_KINDS) expect(first[kind], kind).toBeGreaterThan(0);

    await rig.go('/b');

    const second = tally(rig.starts);
    for (const kind of ENTRANCE_KINDS) expect(second[kind], kind).toBe(first[kind] * 2);
  });
});
```

- [ ] **Step 2: Run it**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/no-replay.spec.ts`
Expected: PASS, `Tests  5 passed (5)`. The gate is written after MO7, MO8, MO9, MO12 and MO15, so it passes on arrival. Step 3 proves it can fail.

If the first case fails because a key differs (for example `stat-tile` records its count-up under another key), read the wiring in `frontend/src/app/ui/stat-tile.ts` / `figure.ts`. If the ledger key (`stat:<label>`, `figure:<label>`) is what the code uses and the spec text is wrong, fix the spec. If the code deviates from the ledger, stop and report it: the ledger is the contract. If `(a)` reports `navigate` not called, the refresh was skipped. Check that `RouteLoadingService.pending()` is `false` once `/a` has settled, and report what blocked it. Do not replace the real refresh with a direct `navigateByUrl`.

- [ ] **Step 3: Prove the gate bites (two scratch mutations, both reverted)**

Mutation 1, a claim that is never spent. In `$WT/frontend/src/app/ui/motion/route-entry.service.ts`, change the body of `claim` to `return true;`. Run:

`npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/no-replay.spec.ts`
Expected: FAIL in `(b) sb-async going loading -> content ...`, because the re-created figure, tile, sparkline and chart start again.

Revert: `git -C $WT checkout -- frontend/src/app/ui/motion/route-entry.service.ts`

Mutation 2, a background refresh that moves the activation id. In the same file, in `commit`, change `if (background || !moved) return;` to `if (!moved && !background) return;`. Run the same command.
Expected: FAIL in `(a) RouteRefreshService's background refresh ...`, because the route host enters again.

Revert: `git -C $WT checkout -- frontend/src/app/ui/motion/route-entry.service.ts`

Run: `git -C $WT status --short`
Expected: only `?? frontend/src/app/ui/motion/no-replay.spec.ts`.

Quote both FAIL lines in the report. A mutation that still passes means the gate does not see that path: stop and report it.

- [ ] **Step 4: Run it with its neighbours**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/no-replay.spec.ts --include src/app/ui/motion/route-entry.service.spec.ts --include src/app/ui/motion/route-entrance.spec.ts --include src/app/ui/motion/count-up.spec.ts --include src/app/ui/motion/draw-in.spec.ts --include src/app/routing/route-refresh.service.spec.ts`
Expected: PASS, `0 failed`. Quote the verdict line.

- [ ] **Step 5: Commit**

```bash
git -C $WT add frontend/src/app/ui/motion/no-replay.spec.ts
git -C $WT commit -m "test(v168): no-replay gate over a real router and a real background refresh (MO17)

Mounts a workspace behind the route host under Motion=On, then drives
RouteRefreshService's background refresh (navigateByUrl with
BACKGROUND_REFRESH_INFO), an sb-async loading->content cycle, a same-URL
reload and query/fragment changes: zero new entrance, first count-up or
draw-in starts. A path change starts them all again. Two scratch mutations
(claim always true; background refresh moving the id) each fail the gate.

Narrow runs: <the Tests verdict lines from Steps 2 and 4; the two mutation FAIL lines>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task MO18: Evidence: Playwright at 390 / 768 / 1440 and a before/after performance trace

**Model:** sonnet — runs two local stacks and judges shots and traces against the pass criterion

**Files:**
- Create: `docs/superpowers/results/v168/motion-evidence.cjs` (the evidence script, kept beside its output so the run can be repeated)
- Create: `docs/superpowers/results/v168/*.png` (route, drawer and Off shots per width), `docs/superpowers/results/v168/animations.json` (the running-animation samples), `docs/superpowers/results/v168/trace-before.json`, `docs/superpowers/results/v168/trace-after.json`, `docs/superpowers/results/v168/README.md`
- Modify: `docs/superpowers/plans/2026-10-16-v168-motion-system_0-index.md` (`## Progress`; the branch copy in `$WT`)

**Interfaces:**
- Consumes: the finished motion (MO2-MO17 committed on the branch); `main` in the main tree `$R` as the "before" (v167 merged, no v168); `frontend/scripts/browse.mjs login` (existing) for the one sign-in, and its persistent profile directory (`%LOCALAPPDATA%/swingbot-playwright/profile`); `playwright` from `$WT/frontend/node_modules`.
- Produces: the evidence `/close-out` and the partner read. Nothing later consumes it in code.

**Needs the partner.** They type the local admin login into the headed Playwright window once. `browse.mjs` never fills, asks for or stores a credential; never read `.env` for one. The cookie is per host, not per port, so one sign-in on `localhost` serves both dev servers.

**What a real browser can show that jsdom cannot.** `document.getAnimations()` lists every running CSS animation with its `animationName`. The script samples it at the moments that matter, so "the entrance ran", "the drawer slid / rose" and "Off left only the spinners turning" are read from data, not judged from a still frame.

**Pass criterion (spec Testing → Evidence, §5, §6), all of it from the after stack:**
1. **Route change**, at each of 390 / 768 / 1440: the sample taken just after the URL changes contains `sb-enter`. The settled sample, 1.5s later, contains no `sb-enter`, `sb-fade-in` or `sb-draw-*` (nothing lingers or replays). The settled shot shows no leftover blur or offset.
2. **Drawer**, open then closed: at 390 the open sample contains `sb-sheet-in` and the close sample `sb-sheet-out` (a bottom sheet). At 768 and 1440 they contain `sb-drawer-in` / `sb-drawer-out` (from the right). The 390 open shot shows the sheet at the bottom with its drag handle; the 768 shot shows `85vw` from the right.
3. **Motion = Off**, at each width, during a slowed navigation: the running set contains `sb-route-spin` with a 2400ms duration (spinners still turn, slowed), and **nothing else** except `sb-spin`. The settled Off sample is empty, or `sb-spin` only.
4. **Trace** (§6), dashboard → trades → dashboard at 1440: every long task (> 50ms) in the after trace is listed with its three heaviest child events. None may be attributable to motion. A long task counts as attributable when it has no counterpart in the before trace at the same step **and** its heaviest children are style, layout or paint work (`UpdateLayoutTree`, `Layout`, `Paint`, `PrePaint`, `Animation*`), or a script frame from `count-up` / `draw-in` / `route-entrance`. A long task present in both traces is the page's own and is listed, not counted.

**Off is forced through the attribute, not the control.** The script sets `<html data-motion="off">` in the page after preferences load. That drives every CSS rule exactly as the control would. It writes nothing to the preferences store: the local `admin_ui.py` may share a database with real preferences, and an evidence run must not change them. TS-side Off behaviour (no count-up, no draw-in class, no flash class) is proven by the unit specs (MO8, MO14, MO15). The README says so.

- [ ] **Step 1: Write the evidence script**

Create `docs/superpowers/results/v168/motion-evidence.cjs`:

```js
#!/usr/bin/env node
/**
 * v168 motion evidence (plan MO18). CommonJS so NODE_PATH can point it at
 * frontend/node_modules from outside the frontend tree:
 *
 *   NODE_PATH=<tree>/frontend/node_modules node motion-evidence.cjs motion --base http://localhost:4124 --out <dir>
 *   NODE_PATH=<tree>/frontend/node_modules node motion-evidence.cjs trace --base http://localhost:4123 --out <dir> --label before
 *
 * Reuses browse.mjs's persistent profile, so sign in once with
 * `node frontend/scripts/browse.mjs login --base <base>` first. Never fills a
 * credential. Off is forced through <html data-motion>, never the Motion
 * control, so no preference is written.
 */
const { chromium } = require('playwright');
const { mkdirSync, writeFileSync } = require('node:fs');
const { homedir } = require('node:os');
const { join } = require('node:path');

const PROFILE = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'swingbot-playwright', 'profile');
const WIDTHS = [390, 768, 1440];
const LONG_TASK_US = 50_000;
const STEP_PAUSE_MS = 2500;

function parseArgs(argv) {
  const opts = { cmd: argv[0], base: null, out: null, label: 'after' };
  for (let i = 1; i < argv.length; i += 2) {
    const [flag, value] = [argv[i], argv[i + 1]];
    if (flag === '--base') opts.base = value.replace(/\/$/, '');
    else if (flag === '--out') opts.out = value;
    else if (flag === '--label') opts.label = value;
    else throw new Error(`unknown flag ${flag}`);
  }
  if (!opts.base || !opts.out || !['motion', 'trace'].includes(opts.cmd)) {
    throw new Error('usage: motion-evidence.cjs motion|trace --base URL --out DIR [--label before|after]');
  }
  return opts;
}

/** Every running CSS animation: name, duration, and the element it runs on. */
function running(page) {
  return page.evaluate(() => document.getAnimations()
    .filter((animation) => animation.playState === 'running' && 'animationName' in animation)
    .map((animation) => {
      const target = animation.effect?.target;
      const where = target ? `${target.tagName.toLowerCase()}.${[...target.classList].join('.')}` : '?';
      return { name: animation.animationName, ms: Number(animation.effect.getTiming().duration), on: where };
    }));
}

const names = (samples) => [...new Set(samples.map((sample) => sample.name))].sort();

/** Preferences loaded (data-motion left `pending`) and the page has content. */
async function ready(page, path) {
  await page.waitForFunction(() => {
    const mode = document.documentElement.dataset.motion;
    const main = document.querySelector('main') ?? document.body;
    return mode !== undefined && mode !== 'pending' && main.innerText.trim().length > 200;
  }, null, { timeout: 30_000 }).catch(() => console.error(`not ready after 30s: ${path}`));
  await page.waitForTimeout(1500);
}

async function open(page, base, path, width) {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(`${base}${path}`, { waitUntil: 'load' });
  await ready(page, path);
}

/** Below 640px the nav is an overlay: summon it first. */
async function clickNav(page, path) {
  const menu = page.locator('.menu-button');
  if (await menu.isVisible()) await menu.click();
  await page.locator(`.sidebar a[href="${path}"]`).first().click();
}

async function shot(page, out, name) {
  await page.screenshot({ path: join(out, `${name}.png`) });
  console.error(join(out, `${name}.png`));
}

async function routeChange(page, opts, width) {
  await open(page, opts.base, '/dashboard', width);
  await clickNav(page, '/trades');
  await page.waitForURL('**/trades', { timeout: 30_000 });
  await page.waitForTimeout(60);
  const mid = await running(page);
  await shot(page, opts.out, `route@${width}-mid`);
  await page.waitForTimeout(1500);
  const settled = await running(page);
  await shot(page, opts.out, `route@${width}-settled`);
  return { mid: names(mid), settled: names(settled) };
}

async function drawer(page, opts, width) {
  await open(page, opts.base, '/calendar', width);
  const day = page.locator('button.value').first();
  if ((await day.count()) === 0) return { error: 'no button.value on /calendar (see Step 4)' };
  await day.click();
  await page.waitForTimeout(80);
  const opening = await running(page);
  await shot(page, opts.out, `drawer@${width}-opening`);
  await page.waitForTimeout(800);
  await shot(page, opts.out, `drawer@${width}-open`);
  await page.locator('sb-drawer .close').first().click();
  await page.waitForTimeout(60);
  const closing = await running(page);
  await shot(page, opts.out, `drawer@${width}-closing`);
  await page.waitForTimeout(600);
  return { opening: names(opening), closing: names(closing) };
}

/** Off, with the network slowed so the route spinner shows. */
async function offMode(page, opts, width) {
  await open(page, opts.base, '/dashboard', width);
  await page.evaluate(() => { document.documentElement.dataset.motion = 'off'; });
  await page.waitForTimeout(400);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 4000, downloadThroughput: -1, uploadThroughput: -1 });
  await clickNav(page, '/trades');
  await page.waitForTimeout(1400);
  const loading = await running(page);
  await shot(page, opts.out, `off@${width}-loading`);
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  await page.waitForURL('**/trades', { timeout: 30_000 });
  await page.waitForTimeout(2000);
  const settled = await running(page);
  await shot(page, opts.out, `off@${width}-settled`);
  await cdp.detach();
  return { loading, settled: names(settled) };
}

async function motion(page, opts) {
  const result = {};
  for (const width of WIDTHS) {
    result[width] = {
      route: await routeChange(page, opts, width),
      drawer: await drawer(page, opts, width),
      off: await offMode(page, opts, width),
    };
  }
  writeFileSync(join(opts.out, 'animations.json'), `${JSON.stringify(result, null, 2)}\n`);
  console.log(JSON.stringify(result, null, 2));
}

/** Metadata plus complete events of 1ms or more: small enough to commit, still loadable. */
function slim(events) {
  return events.filter((event) => event.ph === 'M' || (event.ph === 'X' && event.dur >= 1000));
}

function heaviestChildren(events, task) {
  return events
    .filter((event) => event.ph === 'X' && event.tid === task.tid && event.pid === task.pid && event !== task
      && event.ts >= task.ts && event.ts + event.dur <= task.ts + task.dur && event.name !== 'RunTask')
    .sort((a, b) => b.dur - a.dur)
    .slice(0, 3)
    .map((event) => `${event.name} ${(event.dur / 1000).toFixed(1)}ms ${event.args?.data?.url ?? event.args?.data?.functionName ?? ''}`.trim());
}

function longTasks(events) {
  const start = Math.min(...events.filter((event) => event.ts > 0).map((event) => event.ts));
  return events
    .filter((event) => event.ph === 'X' && event.name === 'RunTask' && event.dur > LONG_TASK_US)
    .map((task) => ({ atMs: Math.round((task.ts - start) / 1000), durMs: Math.round(task.dur / 1000), top: heaviestChildren(events, task) }));
}

async function trace(page, opts) {
  await open(page, opts.base, '/dashboard', 1440);
  const cdp = await page.context().newCDPSession(page);
  const events = [];
  cdp.on('Tracing.dataCollected', ({ value }) => events.push(...value));
  const done = new Promise((resolve) => cdp.once('Tracing.tracingComplete', resolve));
  await cdp.send('Tracing.start', { categories: 'devtools.timeline,disabled-by-default-devtools.timeline', transferMode: 'ReportEvents' });
  await clickNav(page, '/trades');
  await page.waitForTimeout(STEP_PAUSE_MS);
  await clickNav(page, '/dashboard');
  await page.waitForTimeout(STEP_PAUSE_MS);
  await cdp.send('Tracing.end');
  await done;
  const kept = slim(events);
  writeFileSync(join(opts.out, `trace-${opts.label}.json`), JSON.stringify({ traceEvents: kept }));
  console.log(JSON.stringify({ label: opts.label, events: kept.length, longTasks: longTasks(kept) }, null, 2));
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  mkdirSync(opts.out, { recursive: true });
  const context = await chromium.launchPersistentContext(PROFILE, { headless: false, viewport: { width: 1440, height: 900 } });
  try {
    const page = context.pages()[0] ?? (await context.newPage());
    await (opts.cmd === 'motion' ? motion(page, opts) : trace(page, opts));
  } finally {
    await context.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
```

Check the syntax:

```bash
node --check $WT/docs/superpowers/results/v168/motion-evidence.cjs
```
Expected: no output, exit 0.

- [ ] **Step 2: Start the local stacks**

Each of these is a long-running process: start it with the Bash tool's `run_in_background`, never with `&`, and watch its output for the ready line.

```bash
test -d $WT/frontend/node_modules || npm --prefix $WT/frontend ci
python $R/admin_ui.py
npm --prefix $R/frontend exec -- ng serve --port 4123
npm --prefix $WT/frontend exec -- ng serve --port 4124
```

- `admin_ui.py` is the one API both dev servers proxy to (`frontend/proxy.conf.json` → `http://localhost:1234`). Run it from `$R`; the backend is the same in both trees. If it exits (no database reachable from this machine, a missing setting), stop here and report `BLOCKED:` with its last log lines. Do not point the proxy anywhere else.
- `:4123` serves `main` (the before), `:4124` the worktree (the after). Ready when each `ng serve` prints `Local: http://localhost:412x/`.

- [ ] **Step 3: Sign in once**

```bash
node $WT/frontend/scripts/browse.mjs login --base http://localhost:4124
```
Tell the controller the window is waiting; the partner types the local admin login. `Signed in.` on stderr ends the step.

- [ ] **Step 4: Record the motion evidence on the after stack**

```bash
NODE_PATH=$WT/frontend/node_modules node $WT/docs/superpowers/results/v168/motion-evidence.cjs motion --base http://localhost:4124 --out $WT/docs/superpowers/results/v168
```
Expected: 21 PNGs (`route@<w>-mid`, `route@<w>-settled`, `drawer@<w>-opening`, `drawer@<w>-open`, `drawer@<w>-closing`, `off@<w>-loading`, `off@<w>-settled` for each of 390 / 768 / 1440), plus `animations.json`, whose content is also printed.

If a `drawer` entry reads `no button.value on /calendar`, the current month has no closed trades locally, or v165 renamed the day control. Read `$WT/frontend/src/app/workspaces/calendar/calendar.ts` for the control that opens the day `sb-drawer`. Change the `button.value` selector in the script's `drawer()` (and, if needed, add a `button[aria-label="Previous month"]` click before it), say so in the commit body, and re-run. The spec asks for an open drawer, so a run without one is not evidence.

If `off@<w>-loading` shows no spinner, the slowed navigation finished inside 1.4s (a cached route). Raise `latency` in `offMode` to 8000 and re-run.

- [ ] **Step 5: Record the before and after traces**

```bash
NODE_PATH=$WT/frontend/node_modules node $WT/docs/superpowers/results/v168/motion-evidence.cjs trace --base http://localhost:4123 --out $WT/docs/superpowers/results/v168 --label before
NODE_PATH=$WT/frontend/node_modules node $WT/docs/superpowers/results/v168/motion-evidence.cjs trace --base http://localhost:4124 --out $WT/docs/superpowers/results/v168 --label after
```
Expected: `trace-before.json` and `trace-after.json` written, and a summary printed for each (`events`, `longTasks`). Keep both summaries for Step 6.

Run: `ls -l $WT/docs/superpowers/results/v168/trace-*.json`
Expected: each under 5 MB (the script keeps only metadata and events of 1ms or more). If one is larger, report its size rather than committing it, and ask the controller.

- [ ] **Step 6: Judge against the pass criterion**

Read `animations.json` and the two trace summaries, and check criteria 1-4 above one by one. Then open every PNG with the Read tool and note, per shot, anything wrong: leftover blur or offset in a settled shot, a drawer at the wrong edge, clipped text, a second glow.

A failed criterion is a defect in the task that owns it: route entrance MO7, drawer MO12, Off fallbacks MO6, draw-in MO15, ambient MO16. Fix it in that task's files with a `fix(v168): ... (MO18)` commit and the narrow run of that file's spec, then re-run Steps 4-5. Never loosen the criterion. A long task attributable to motion goes to the controller as a finding before any fix, because the remedy (dropping the blur from `sb-enter`, capping the stagger lower) changes the spec's design.

- [ ] **Step 7: Write the README**

Create `docs/superpowers/results/v168/README.md`:

```markdown
# v168 motion system: evidence (MO18)

Recorded <YYYY-MM-DD> against local stacks: before = `main` at <short sha> (:4123), after = branch `2026-10-16-v168-motion-system` at <short sha> (:4124). Script: `motion-evidence.cjs` (this directory); raw samples: `animations.json`.

## 1. Route change (`route@<w>-mid.png`, `route@<w>-settled.png`)

| Width | Running just after the URL changed | Running 1.5s later |
|---|---|---|
| 390 | <names> | <names> |
| 768 | <names> | <names> |
| 1440 | <names> | <names> |

## 2. Drawer (`drawer@<w>-opening|open|closing.png`)

| Width | Opening | Closing | Geometry seen |
|---|---|---|---|
| 390 | <names> | <names> | bottom sheet, drag handle |
| 768 | <names> | <names> | from the right, 85vw |
| 1440 | <names> | <names> | from the right, 480px |

## 3. Motion = Off (`off@<w>-loading.png`, `off@<w>-settled.png`)

Forced through `<html data-motion="off">` after preferences loaded; no preference was written. TS-side Off (no count-up, draw-in or flash class) is proven by `count-up.spec.ts`, `draw-in.spec.ts` and `flash.spec.ts`.

| Width | Running while the route loads (name, ms) | Running once settled |
|---|---|---|
| 390 | <e.g. sb-route-spin 2400> | <names or none> |
| 768 | ... | ... |
| 1440 | ... | ... |

## 4. Performance trace (`trace-before.json`, `trace-after.json`, 1440, dashboard → trades → dashboard)

Slimmed to metadata plus events of 1ms or more; both load in Chrome DevTools → Performance → Load profile.

| Trace | Long tasks > 50ms (at ms, duration, heaviest children) |
|---|---|
| before | <list or none> |
| after | <list or none> |

**Attributable to motion:** <none | which, and why>.

## Verdict

<Pass on all four criteria | what failed and the fix commit>. Shot notes: <per-shot notes from Step 6, or "none">.
```

Fill every `<...>` from Steps 4-6. Leave no placeholder.

- [ ] **Step 8: Record progress and stop the stacks**

In `$WT/docs/superpowers/plans/2026-10-16-v168-motion-system_0-index.md`, replace the `## Progress` body (`Not started. Update this block when a phase closes.`, or whatever an earlier task left) with:

```markdown
- **MO1-MO17:** done on branch `2026-10-16-v168-motion-system`.
- **Evidence (MO18), <YYYY-MM-DD>:** `docs/superpowers/results/v168/` -- route entrance seen at 390 / 768 / 1440 and nothing left running 1.5s later; drawer is a bottom sheet at 390 and slides from the right at 768 / 1440; under Off only the spinners turn (route spinner at 2400ms); <N> long tasks in the after trace, none attributable to motion.
- **Next:** MO19, the full suite.
```

Stop the three background processes (`admin_ui.py`, both `ng serve`).

- [ ] **Step 9: Commit**

```bash
git -C $WT add docs/superpowers/results/v168 docs/superpowers/plans/2026-10-16-v168-motion-system_0-index.md
git -C $WT commit -m "test(v168): motion evidence at 390/768/1440 and a before/after trace (MO18)

Running-animation samples from a real browser: the route entrance runs and
nothing lingers; the drawer is a bottom sheet on phone and slides from the
right on tablet and desktop; under Off only the spinners turn. The
dashboard trace shows no long task attributable to motion. Script, samples,
21 shots, both traces and a README under docs/superpowers/results/v168/.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task MO19: Full Python suite and whole frontend run

**Model:** haiku — runs commands, no code

**Files:** none. This task changes nothing unless a check fails (see Step 5).

**Interfaces:**
- Consumes: every commit MO1-MO18 on the branch.
- Produces: the verdict lines `/close-out` needs: full Python suite, whole frontend run, `dump_tokens.py --check`, and the two source sweeps.

This is the plan's single full-suite run ("Naming specs and plans" in `CLAUDE.md`). Nothing after it re-runs the suite: not the merge back to `main`, not `/close-out`.

- [ ] **Step 1: Confirm the branch is clean**

```bash
git -C $WT status --short
```
Expected: no output. Anything listed belongs to an earlier task: stop and report it rather than committing it here.

- [ ] **Step 2: Full Python suite**

Dispatch the `test-runner` subagent, so the output stays out of the controller's context, with:
```bash
python $WT/scripts/dev/testrun.py full
```
Expected: `0 failed` and `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`). v168 changes no Python, so this run guards the token fixture (`tests/charts/resolved_tokens.json`, regenerated by MO2 and MO6) and the Codex/hook gates. Quote the verdict line.

- [ ] **Step 3: Whole frontend spec run**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false
```
Expected: `Tests  N passed (N)`, 0 failed. A 60 s `Timeout waiting for worker ... no tests` before anything ran is machine load: re-run once. Quote the verdict line.

- [ ] **Step 4: Fixture and source sweeps**

```bash
python $WT/scripts/dev/dump_tokens.py --check
git -C $WT grep -n "prefers-reduced-motion" -- frontend/src ':!*.spec.ts'
git -C $WT grep -n "@keyframes" -- frontend/src ':!*.spec.ts' ':!frontend/src/styles/motion.css'
git -C $WT grep -n "localStorage" -- frontend/src/app/ui/motion frontend/src/app/shell/shell.ts
```
Expected: `--check` exits 0. Each of the three greps prints nothing: the OS setting is never read (spec D2, Global Constraints), `motion.css` is the one keyframe home (spec §2), and `shell.motion` lives only in `PreferencesStore` (plan v21). Quote the outputs.

- [ ] **Step 5: On a failure**

A failed test is fixed and re-run alone, never by re-running the suite. Find the task whose files own the failure and fix it in those files with a `fix(v168): ... (MO19)` commit on the branch. Then run only that test (`python $WT/scripts/dev/testrun.py file <test>` or `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec>`) and quote its verdict line. Do not loosen a gate (`motion-home`, G3, the colour gate, `no-replay`) to get green. A no-replay failure reopens MO7/MO8/MO15, never the gate.

- [ ] **Step 6: Report**

No commit when Steps 2-4 were green on the first run. Report to the controller: the four verdicts (Python full, frontend whole, `--check`, the three sweeps) and any Step 5 fix commits with their single-test verdicts. The controller then runs `/close-out` (the `**Bump:**` is `ui minor; bot none`; no task edits `VERSION.json`) and `/panel` for the plan (`senior-engineer`, the spec's `**Panel:**`).
