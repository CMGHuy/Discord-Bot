# v168 Motion system, part 2b: count-up (MO8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull the task with `grep -n "^### Task MO8:" -A 600 docs/superpowers/plans/2026-10-16-v168-motion-system_2b-count-up.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v168-motion-system-design.md`](../specs/2026-10-16-v168-motion-system-design.md) (its `## Amendments from the plan brief` bind and override earlier sections).
**Index:** [`2026-10-16-v168-motion-system_0-index.md`](2026-10-16-v168-motion-system_0-index.md): `## Global Constraints`, `## Where to work` (`$WT`, the narrow-run command), `## Parallelisation` and the `## Task ledger` apply here and are not repeated.

**Why a separate file:** part 2 (`_2-preference-routing.md`, MO5..MO7) reached the 1500-line cap; MO8 is a whole task and is never split or compressed, so it lives here. Ledger, ids, files and contracts are unchanged.

**Consumed from earlier tasks (index ledger contracts):** MO4's `MotionService.full` (`true` only for `on`), `MotionStarts.record/count/entries`, `provideMotion` (`frontend/src/app/ui/motion/motion.service.ts`, `frontend/src/app/ui/motion/motion-starts.ts`), and the global `provideMotion('off')` test default in `frontend/src/test-setup.ts`. MO7's `RouteEntryService.claim(key: string): boolean` (`frontend/src/app/ui/motion/route-entry.service.ts`).

**Line numbers are pre-v167**; every edit is anchored on quoted text. If an anchor is missing, stop and report it.

---

### Task MO8: `[sbCountUp]` on `figure.ts`, `stat-tile`, `metric-card`, `metric-chip` headline values

**Model:** sonnet — one directive and four template swaps, behaviour given by the spec

**Files:**
- Create: `frontend/src/app/ui/motion/count-up.ts`
- Create: `frontend/src/app/ui/motion/count-up.spec.ts`
- Create: `frontend/src/app/ui/motion/figure-text.ts`
- Create: `frontend/src/app/ui/motion/figure-text.spec.ts`
- Modify: `frontend/src/app/ui/figure.ts`
- Modify: `frontend/src/app/ui/stat-tile.ts`
- Modify: `frontend/src/app/ui/metric-card.ts`
- Modify: `frontend/src/app/ui/metric-chip.ts`

**Interfaces:**
- Consumes: `RouteEntryService.claim` (MO7); `MotionService.full`, `MotionStarts`, `provideMotion` (MO4); `ABSENT` and `num` from `frontend/src/app/ui/format.ts` (exist: `ABSENT = '—'`; `num(value, decimals = 2)` groups thousands, en-US).
- Produces: `export const COUNT_MS = 900`; `easeOutCubic(t: number): number`; `@Directive({ selector: '[sbCountUp]' }) class CountUp { sbCountUp = input.required<number | null>(); countFormat = input.required<(value: number) => string>(); countKey = input.required<string>(); countAbsent = input<string>(ABSENT) }`; `interface FigureText { prefix: string; value: number; decimals: number; suffix: string; grouped: boolean }`; `parseFigureText(text: string | null): FigureText | null`; `formatFigureText(parts: FigureText, value: number): string`. Keys: `figure:<label>`, `stat:<label>`, `metric:<label>`, `chip:<label>`. MO17's no-replay gate counts this task's `'count-first'` starts.

**Behaviour (spec §3 #3, amendment 1; Global Constraints):**
- **The directive owns its host's `textContent`.** Each primitive's headline element loses its `{{ ... }}` interpolation; the directive writes the text.
- First non-null value: spend `claim(countKey)` (always, whatever the mode), then if the claim was fresh **and** `motion.full()`, count 0 → value over `COUNT_MS` with `easeOutCubic`, recording `'count-first'`. Otherwise write the final text at once.
- A later change of value under `full()` eases old → new, recording `'count-change'` (an intended push reaction, spec §4). Under any other mode it writes the final text at once.
- `null` writes `countAbsent` at once, no count.
- Frames run through `requestAnimationFrame` inside `NgZone.runOutsideAngular` (a no-op in this zoneless app, kept for the spec's guarantee). The frame is cancelled on destroy and on every new value. If `requestAnimationFrame` is undefined, the final text is written synchronously.
- **`stat-tile` takes a pre-formatted string** (`'68%'`, `'+$1,240'`, `'+1.23R'`, `'12 / 20'`), so it counts through `parseFigureText`/`formatFigureText`: the first number in the string is the value, everything before it is `prefix` (including any sign or currency), everything after it `suffix`. Text with no digits (`'n/a'`) is shown as it is, through `countAbsent`. A sign flip between two values eases the magnitude under the new prefix; that is a 900ms cosmetic oddity on a rare event, accepted rather than adding sign logic.
- Under the global test default `off`, every existing spec that reads `.value` text after one `detectChanges` keeps passing, because `off` writes the final text synchronously in the directive's effect.

- [ ] **Step 1: Write the failing `figure-text` spec**

Create `frontend/src/app/ui/motion/figure-text.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { formatFigureText, parseFigureText } from './figure-text';

describe('parseFigureText', () => {
  it('splits prefix, number and suffix', () => {
    expect(parseFigureText('+$1,240.50 today')).toEqual({
      prefix: '+$', value: 1240.5, decimals: 2, suffix: ' today', grouped: true,
    });
  });

  it('reads a bare percentage and an R multiple', () => {
    expect(parseFigureText('68%')).toEqual({ prefix: '', value: 68, decimals: 0, suffix: '%', grouped: false });
    expect(parseFigureText('-0.42R')).toEqual({ prefix: '-', value: 0.42, decimals: 2, suffix: 'R', grouped: false });
  });

  it('takes only the first number; the rest is suffix', () => {
    expect(parseFigureText('12 / 20')).toEqual({ prefix: '', value: 12, decimals: 0, suffix: ' / 20', grouped: false });
  });

  it('returns null when there is nothing to count', () => {
    expect(parseFigureText(null)).toBeNull();
    expect(parseFigureText('')).toBeNull();
    expect(parseFigureText('—')).toBeNull();
    expect(parseFigureText('n/a')).toBeNull();
  });
});

describe('formatFigureText', () => {
  it('round-trips every shape a stat tile is given', () => {
    for (const text of ['68%', '+1.23R', '+$1,240', '-$12.50', '1.80', '12 / 20', '−0.42R', '1,234,567.8 €']) {
      const parts = parseFigureText(text)!;
      expect(formatFigureText(parts, parts.value)).toBe(text);
    }
  });

  it('formats an intermediate value in the same shape', () => {
    const parts = parseFigureText('+$1,240.50')!;
    expect(formatFigureText(parts, 0)).toBe('+$0.00');
    expect(formatFigureText(parts, 1085.4375)).toBe('+$1,085.44');
  });

  it('keeps an ungrouped number ungrouped', () => {
    expect(formatFigureText(parseFigureText('12345')!, 2000)).toBe('2000');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/figure-text.spec.ts`
Expected: FAIL, the build cannot resolve `./figure-text`.

- [ ] **Step 3: Implement `figure-text.ts`**

Create `frontend/src/app/ui/motion/figure-text.ts`:

```ts
/**
 * A pre-formatted figure taken apart so it can be counted (spec v168 §3 #3).
 *
 * `StatTile` receives its value already formatted by the page (`'68%'`,
 * `'+$1,240'`, `'+1.23R'`) and deliberately never formats a number itself.
 * Counting it up needs the number back out: the first number in the text is
 * the value, everything before it (sign, currency) the prefix, everything after
 * it the suffix. `formatFigureText(parts, parts.value)` returns the original
 * text exactly.
 */
export interface FigureText {
  prefix: string;
  value: number;
  decimals: number;
  suffix: string;
  grouped: boolean;
}

/** Lazy non-digit prefix; comma-grouped or plain integer part; optional
 *  fraction; the rest. `s` so a suffix may hold a line break. */
const FIGURE_RE = /^(\D*?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(.*)$/s;

export function parseFigureText(text: string | null): FigureText | null {
  if (text === null) return null;
  const match = FIGURE_RE.exec(text);
  if (!match) return null;
  const [, prefix, whole, fraction = '', suffix] = match;
  const digits = whole.replaceAll(',', '');
  return {
    prefix,
    value: Number(fraction ? `${digits}.${fraction}` : digits),
    decimals: fraction.length,
    suffix,
    grouped: whole.includes(','),
  };
}

export function formatFigureText(parts: FigureText, value: number): string {
  const body = value.toLocaleString('en-US', {
    minimumFractionDigits: parts.decimals,
    maximumFractionDigits: parts.decimals,
    useGrouping: parts.grouped,
  });
  return `${parts.prefix}${body}${parts.suffix}`;
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/figure-text.spec.ts`
Expected: PASS, `Tests  7 passed (7)`.

- [ ] **Step 5: Write the failing `CountUp` spec**

Create `frontend/src/app/ui/motion/count-up.spec.ts`. It stubs `requestAnimationFrame` with a manual queue, so every frame time is chosen by the test and nothing depends on the machine's clock:

```ts
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PreferencesStore } from '../../stores/preferences.store';
import { Figure } from '../figure';
import { MetricCard } from '../metric-card';
import { MetricChip } from '../metric-chip';
import { StatTile } from '../stat-tile';
import { COUNT_MS, CountUp, easeOutCubic } from './count-up';
import { MotionStarts } from './motion-starts';
import { MotionState, provideMotion } from './motion.service';

let frames: FrameRequestCallback[] = [];

/** Runs every queued frame at time `at` (ms); frames they queue wait for the next call. */
function frame(at: number): void {
  const due = frames;
  frames = [];
  for (const callback of due) callback(at);
}

function configure(mode: MotionState): void {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideMotion(mode),
      { provide: PreferencesStore, useValue: { values: () => ({}) } },
    ],
  });
}

@Component({
  imports: [CountUp],
  template: `<span class="value" [sbCountUp]="value()" [countFormat]="format" countKey="figure:Expectancy"
    [countAbsent]="absent()"></span>`,
})
class Host {
  readonly value = signal<number | null>(100);
  readonly absent = signal('—');
  readonly format = (value: number) => value.toFixed(1);
}

function mount() {
  const fixture = TestBed.createComponent(Host);
  fixture.detectChanges();
  const span = (fixture.nativeElement as HTMLElement).querySelector('.value') as HTMLElement;
  return { fixture, span, text: () => span.textContent };
}

beforeEach(() => {
  frames = [];
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => frames.push(callback));
  vi.stubGlobal('cancelAnimationFrame', () => {
    frames = [];
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('easeOutCubic', () => {
  it('runs 0 to 1 and is past three quarters at the midpoint', () => {
    expect(easeOutCubic(0)).toBe(0);
    expect(easeOutCubic(0.5)).toBe(0.875);
    expect(easeOutCubic(1)).toBe(1);
  });
});

describe('CountUp (spec v168 §3 #3)', () => {
  it('under On counts 0 to the value through intermediate values and settles on the formatted value', () => {
    configure('on');
    const { text } = mount();
    expect(text()).toBe('0.0');
    frame(0);
    frame(COUNT_MS / 2);
    expect(text()).toBe('87.5');
    frame(COUNT_MS);
    expect(text()).toBe('100.0');
    expect(frames).toHaveLength(0);
    expect(TestBed.inject(MotionStarts).entries()).toEqual([{ kind: 'count-first', key: 'figure:Expectancy' }]);
  });

  it('under On eases a later change from A to B', () => {
    configure('on');
    const { fixture, text } = mount();
    frame(0);
    frame(COUNT_MS);
    fixture.componentInstance.value.set(200);
    fixture.detectChanges();
    expect(text()).toBe('100.0');
    frame(1000);
    frame(1000 + COUNT_MS / 2);
    expect(text()).toBe('187.5');
    frame(1000 + COUNT_MS);
    expect(text()).toBe('200.0');
    expect(TestBed.inject(MotionStarts).count('count-change')).toBe(1);
  });

  it('shows the absent text at once for null, with no count', () => {
    configure('on');
    TestBed.overrideTemplate(Host, `<span class="value" [sbCountUp]="null" [countFormat]="format"
      countKey="figure:Expectancy"></span>`);
    const { text } = mount();
    expect(text()).toBe('—');
    expect(frames).toHaveLength(0);
    expect(TestBed.inject(MotionStarts).entries()).toEqual([]);
  });

  it('uses countAbsent for null when one is given', () => {
    configure('on');
    const { fixture, text } = mount();
    fixture.componentInstance.absent.set('n/a');
    fixture.componentInstance.value.set(null);
    fixture.detectChanges();
    expect(text()).toBe('n/a');
  });

  for (const mode of ['off', 'reduced', 'pending'] as const) {
    it(`under ${mode} renders the final value synchronously, first value and changes alike`, () => {
      configure(mode);
      const { fixture, text } = mount();
      expect(text()).toBe('100.0');
      fixture.componentInstance.value.set(42);
      fixture.detectChanges();
      expect(text()).toBe('42.0');
      expect(frames).toHaveLength(0);
      expect(TestBed.inject(MotionStarts).entries()).toEqual([]);
    });
  }

  it('does not replay: a re-created element with a spent claim renders its final value', () => {
    configure('on');
    const first = mount();
    first.fixture.destroy();
    const second = mount();
    expect(second.text()).toBe('100.0');
    expect(TestBed.inject(MotionStarts).count('count-first')).toBe(1);
  });

  it('cancels its frame on destroy', () => {
    configure('on');
    const { fixture } = mount();
    expect(frames).toHaveLength(1);
    fixture.destroy();
    expect(frames).toHaveLength(0);
  });

  it('writes the final value when requestAnimationFrame does not exist', () => {
    vi.stubGlobal('requestAnimationFrame', undefined);
    configure('on');
    const { text } = mount();
    expect(text()).toBe('100.0');
  });
});

describe('CountUp wired into the KPI primitives (spec amendment 1)', () => {
  function finish(): void {
    frame(0);
    frame(COUNT_MS);
  }

  it('sb-figure counts its value and settles on the unit-formatted text', () => {
    configure('on');
    const f = TestBed.createComponent(Figure);
    f.componentRef.setInput('label', 'Expectancy');
    f.componentRef.setInput('value', 1234.5);
    f.componentRef.setInput('unit', '%');
    f.componentRef.setInput('decimals', 1);
    f.detectChanges();
    const value = (f.nativeElement as HTMLElement).querySelector('.value')!;
    expect(value.textContent).toBe('0.0%');
    finish();
    expect(value.textContent).toBe('1,234.5%');
    expect(TestBed.inject(MotionStarts).entries()).toEqual([{ kind: 'count-first', key: 'figure:Expectancy' }]);
  });

  it('sb-stat-tile counts the number inside its pre-formatted text', () => {
    configure('on');
    const f = TestBed.createComponent(StatTile);
    f.componentRef.setInput('label', 'Total P&L');
    f.componentRef.setInput('value', '+$1,240');
    f.detectChanges();
    const value = (f.nativeElement as HTMLElement).querySelector('.value')!;
    expect(value.textContent).toBe('+$0');
    finish();
    expect(value.textContent).toBe('+$1,240');
    expect(TestBed.inject(MotionStarts).entries()).toEqual([{ kind: 'count-first', key: 'stat:Total P&L' }]);
  });

  it('sb-stat-tile shows text with no number as it is', () => {
    configure('on');
    const f = TestBed.createComponent(StatTile);
    f.componentRef.setInput('label', 'Status');
    f.componentRef.setInput('value', 'n/a');
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('.value')!.textContent).toBe('n/a');
    expect(frames).toHaveLength(0);
  });

  it('sb-metric-card counts with toFixed and its unit', () => {
    configure('on');
    const f = TestBed.createComponent(MetricCard);
    f.componentRef.setInput('label', 'Balance');
    f.componentRef.setInput('value', 50);
    f.componentRef.setInput('unit', ' €');
    f.detectChanges();
    const value = (f.nativeElement as HTMLElement).querySelector('.value')!;
    finish();
    expect(value.textContent).toBe('50.00 €');
    expect(TestBed.inject(MotionStarts).entries()).toEqual([{ kind: 'count-first', key: 'metric:Balance' }]);
  });

  it('sb-metric-chip counts with toFixed and its unit', () => {
    configure('on');
    const f = TestBed.createComponent(MetricChip);
    f.componentRef.setInput('label', 'Win rate');
    f.componentRef.setInput('value', 61);
    f.componentRef.setInput('unit', '%');
    f.componentRef.setInput('decimals', 0);
    f.detectChanges();
    const value = (f.nativeElement as HTMLElement).querySelector('.value')!;
    finish();
    expect(value.textContent).toBe('61%');
    expect(TestBed.inject(MotionStarts).entries()).toEqual([{ kind: 'count-first', key: 'chip:Win rate' }]);
  });

  it('sb-figure shows its final value at once under the Off test default', () => {
    configure('off');
    const f = TestBed.createComponent(Figure);
    f.componentRef.setInput('label', 'Expectancy');
    f.componentRef.setInput('value', 54.23);
    f.componentRef.setInput('unit', '%');
    f.componentRef.setInput('decimals', 1);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('.value')!.textContent).toBe('54.2%');
  });
});
```

- [ ] **Step 6: Run it to verify it fails**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/count-up.spec.ts`
Expected: FAIL, the build cannot resolve `./count-up`.

- [ ] **Step 7: Implement `CountUp`**

Create `frontend/src/app/ui/motion/count-up.ts`:

```ts
import { DestroyRef, Directive, ElementRef, NgZone, effect, inject, input, untracked } from '@angular/core';

import { ABSENT } from '../format';
import { MotionStartKind, MotionStarts } from './motion-starts';
import { MotionService } from './motion.service';
import { RouteEntryService } from './route-entry.service';

/** `--dur-count` (spec v168 §1), held in TS because frames are timed here. */
export const COUNT_MS = 900;

export function easeOutCubic(t: number): number {
  const rest = 1 - t;
  return 1 - rest * rest * rest;
}

type Format = (value: number) => string;
type CountKind = Extract<MotionStartKind, 'count-first' | 'count-change'>;

/**
 * Number count-up (spec v168 §3 #3). **Owns its host's text**: the host
 * element has no interpolation of its own, and this directive writes
 * `textContent`.
 *
 * The first value spends `RouteEntryService.claim(countKey)` whatever the
 * mode, and counts from 0 only when the claim was fresh and Motion is On, so
 * a refetch that re-creates the element shows the value at once. A later
 * change eases from the old value under On -- an intended push reaction,
 * scoped to the number that changed. Everything else writes the final text
 * synchronously, which is what keeps every spec under the Off test default
 * reading `.textContent` straight after one `detectChanges`.
 */
@Directive({ selector: '[sbCountUp]' })
export class CountUp {
  readonly sbCountUp = input.required<number | null>();
  readonly countFormat = input.required<Format>();
  readonly countKey = input.required<string>();
  readonly countAbsent = input<string>(ABSENT);

  private readonly host: HTMLElement = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private readonly entry = inject(RouteEntryService);
  private readonly motion = inject(MotionService);
  private readonly starts = inject(MotionStarts);
  private readonly zone = inject(NgZone);
  private target: number | null = null;
  private claimed = false;
  private frame: number | null = null;

  constructor() {
    effect(() => {
      const value = this.sbCountUp();
      const format = this.countFormat();
      const absent = this.countAbsent();
      untracked(() => this.render(value, format, absent));
    });
    inject(DestroyRef).onDestroy(() => this.cancel());
  }

  private render(value: number | null, format: Format, absent: string): void {
    this.cancel();
    const previous = this.target;
    this.target = value;
    if (value === null) {
      this.write(absent);
      return;
    }
    const kind = this.kindFor(previous, value);
    if (kind === null || typeof requestAnimationFrame === 'undefined') {
      this.write(format(value));
      return;
    }
    this.play(kind === 'count-first' ? 0 : (previous ?? 0), value, format, kind);
  }

  /** The first value spends the claim; only On ever counts. */
  private kindFor(previous: number | null, value: number): CountKind | null {
    if (!this.claimed) {
      this.claimed = true;
      const fresh = this.entry.claim(this.countKey());
      return fresh && this.motion.full() ? 'count-first' : null;
    }
    if (previous === null || previous === value) return null;
    return this.motion.full() ? 'count-change' : null;
  }

  private play(from: number, to: number, format: Format, kind: CountKind): void {
    this.starts.record(kind, this.countKey());
    this.write(format(from));
    let start: number | null = null;
    const step = (now: number): void => {
      start ??= now;
      const t = Math.min(1, (now - start) / COUNT_MS);
      this.write(format(t < 1 ? from + (to - from) * easeOutCubic(t) : to));
      this.frame = t < 1 ? requestAnimationFrame(step) : null;
    };
    this.zone.runOutsideAngular(() => {
      this.frame = requestAnimationFrame(step);
    });
  }

  private cancel(): void {
    if (this.frame !== null && typeof cancelAnimationFrame !== 'undefined') cancelAnimationFrame(this.frame);
    this.frame = null;
  }

  private write(text: string): void {
    if (this.host.textContent !== text) this.host.textContent = text;
  }
}
```

- [ ] **Step 8: Wire `sb-figure`**

In `frontend/src/app/ui/figure.ts`:

1. Add the import below `import { ABSENT, num } from './format';`:

```ts
import { CountUp } from './motion/count-up';
```

and change `import { ABSENT, num } from './format';` to `import { num } from './format';` (the `display` computed replaced in item 4 was `ABSENT`'s only user). `computed` stays in the `@angular/core` import (used by `toneClass` and the new `format`).

2. Add `imports: [CountUp],` to the `@Component` of `Figure` (the `sb-figure` one, not `sb-figure-strip`), right after `changeDetection: ChangeDetectionStrategy.OnPush,`.

3. In the `sb-figure` template, replace:

```html
<span class="value num" [class]="toneClass()">{{ display() }}</span>
```

with:

```html
<span class="value num" [class]="toneClass()" [sbCountUp]="value()" [countFormat]="format()" [countKey]="'figure:' + label()"></span>
```

4. In the `Figure` class, replace the `display` computed:

```ts
  protected readonly display = computed(() => { const value = this.value(); return value === null ? ABSENT : `${num(value, this.decimals())}${this.unit()}`; });
```

with:

```ts
  /** The value's text for any number, counted or final; `null` is CountUp's ABSENT. */
  protected readonly format = computed(() => { const decimals = this.decimals(); const unit = this.unit(); return (value: number) => `${num(value, decimals)}${unit}`; });
```

- [ ] **Step 9: Wire `sb-stat-tile`**

In `frontend/src/app/ui/stat-tile.ts`:

1. Add imports below `import { Sparkline } from './sparkline';`:

```ts
import { CountUp } from './motion/count-up';
import { formatFigureText, parseFigureText } from './motion/figure-text';
```

2. Change `imports: [Sparkline],` to `imports: [Sparkline, CountUp],`.

3. Replace the template line:

```html
      <div class="value">{{ value() ?? '—' }}</div>
```

with:

```html
      <div class="value" [sbCountUp]="countValue()" [countFormat]="countFormat()"
           [countKey]="'stat:' + label()" [countAbsent]="value() ?? '—'"></div>
```

4. Add to the class body, after the `trend` input:

```ts
  /**
   * v168 count-up. `value` arrives pre-formatted (this component never formats
   * a number, see the class comment), so the number is read back out of the
   * text and the text rebuilt around each counted value. Text with no number
   * in it has nothing to count and shows as it is, through `countAbsent`.
   */
  private readonly parsed = computed(() => parseFigureText(this.value()));
  protected readonly countValue = computed(() => this.parsed()?.value ?? null);
  protected readonly countFormat = computed(() => {
    const parts = this.parsed();
    return (value: number) => (parts ? formatFigureText(parts, value) : String(value));
  });
```

- [ ] **Step 10: Wire `sb-metric-card` and `sb-metric-chip`**

In `frontend/src/app/ui/metric-card.ts`:

1. Add below the `@angular/core` import:

```ts
import { CountUp } from './motion/count-up';
```

2. Add `imports: [CountUp],` after `changeDetection: ChangeDetectionStrategy.OnPush,`.

3. Replace the template's value span:

```html
      <span class="value num" [class]="valueClass()">
        {{ display() }}
      </span>
```

with:

```html
      <span class="value num" [class]="valueClass()" [sbCountUp]="value()"
            [countFormat]="format()" [countKey]="'metric:' + label()"></span>
```

4. In the `.value` CSS rule, replace the comment

```css
      /* No transition on the value: with push, numbers change whenever the
         bot moves, and an animated number is unreadable at a glance --
         which is the only way this card is ever read. */
```

with:

```css
      /* v168: the number counts up once when the route is entered, and eases
         to a new value when a push changes it -- 900ms, scoped to this one
         number, and only under Motion = On (CountUp). It never re-counts on a
         refetch, so a glance still reads a settled number. */
```

5. Replace the `display` computed and its doc comment:

```ts
  /** An em dash, not "0" or "—%": a metric with no value yet is not a
   *  metric that is zero, and on a balance those differ by everything. */
  protected readonly display = computed(() => {
    const value = this.value();
    if (value === null) return '—';
    return `${value.toFixed(this.decimals())}${this.unit()}`;
  });
```

with:

```ts
  /** The value's text for any number. `null` is CountUp's em dash, not "0"
   *  or "—%": a metric with no value yet is not a metric that is zero, and on
   *  a balance those differ by everything. */
  protected readonly format = computed(() => {
    const decimals = this.decimals();
    const unit = this.unit();
    return (value: number) => `${value.toFixed(decimals)}${unit}`;
  });
```

In `frontend/src/app/ui/metric-chip.ts`:

1. Add below the `@angular/core` import (above `import { MetricTone } from './metric-card';`):

```ts
import { CountUp } from './motion/count-up';
```

2. Add `imports: [CountUp],` after `changeDetection: ChangeDetectionStrategy.OnPush,`.

3. Replace:

```html
      <span class="value num" [class]="valueClass()">{{ display() }}</span>
```

with:

```html
      <span class="value num" [class]="valueClass()" [sbCountUp]="value()"
            [countFormat]="format()" [countKey]="'chip:' + label()"></span>
```

4. Replace the `display` computed and its doc comment:

```ts
  /** An em dash, matching `MetricCard`: a metric with no value yet is not a
   *  metric that is zero. */
  protected readonly display = computed(() => {
    const value = this.value();
    if (value === null) return '—';
    return `${value.toFixed(this.decimals())}${this.unit()}`;
  });
```

with:

```ts
  /** The value's text for any number; `null` is CountUp's em dash, matching
   *  `MetricCard`: a metric with no value yet is not a metric that is zero. */
  protected readonly format = computed(() => {
    const decimals = this.decimals();
    const unit = this.unit();
    return (value: number) => `${value.toFixed(decimals)}${unit}`;
  });
```

- [ ] **Step 11: Run the new specs to verify they pass**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/count-up.spec.ts --include src/app/ui/motion/figure-text.spec.ts`
Expected: PASS, `Tests  24 passed (24)` (count-up 17, figure-text 7).

- [ ] **Step 12: Re-run every spec that renders the four primitives**

The brief's re-count (amendment 1): `<sb-figure>` is rendered by `figure.ts` and `gallery.ts`; `stat-tile`, `metric-card`, `metric-chip` by calendar, trading-performance, risk, trade-detail, gallery, analytics overview and partials; `display.spec.ts` renders the metric pair. Under the global `off` default they must pass unchanged.

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/figure.spec.ts --include src/app/ui/stat-tile.spec.ts --include src/app/ui/display.spec.ts --include 'src/app/workspaces/gallery/**/*.spec.ts' --include 'src/app/workspaces/calendar/**/*.spec.ts' --include 'src/app/workspaces/risk/**/*.spec.ts' --include 'src/app/workspaces/trades/**/*.spec.ts' --include 'src/app/workspaces/analytics/**/*.spec.ts' --include 'src/app/workspaces/dashboard/**/*.spec.ts'`
Expected: PASS, `0 failed`. Quote the verdict line.

If a spec fails only because it compared the old untrimmed metric-card text (`'\n        12.00\n      '` style whitespace from the removed interpolation), the new text is the trimmed value: fix the assertion to the exact value and name the spec in the report. Any other failure is a behaviour change: stop and report it.

- [ ] **Step 13: Prove the interpolations are gone**

Run: `git -C $WT grep -n "display()" -- frontend/src/app/ui/figure.ts frontend/src/app/ui/metric-card.ts frontend/src/app/ui/metric-chip.ts`
Expected: no output.

Run: `git -C $WT grep -n "requestAnimationFrame" -- frontend/src/app ':!*.spec.ts'`
Expected: only `frontend/src/app/ui/motion/count-up.ts`, each use behind the `typeof requestAnimationFrame === 'undefined'` check or inside `play` (reached only after it).

- [ ] **Step 14: Commit**

```bash
git -C $WT add frontend/src/app/ui/motion/count-up.ts frontend/src/app/ui/motion/count-up.spec.ts frontend/src/app/ui/motion/figure-text.ts frontend/src/app/ui/motion/figure-text.spec.ts frontend/src/app/ui/figure.ts frontend/src/app/ui/stat-tile.ts frontend/src/app/ui/metric-card.ts frontend/src/app/ui/metric-chip.ts
git -C $WT commit -m "feat(v168): sbCountUp on figure, stat-tile, metric-card and metric-chip headline values (MO8)

The directive owns the text node: first value counts 0->value once per route
activation under Motion=On (claim spent first), a later change eases A->B, null
shows ABSENT at once, every other mode writes the final text synchronously.
stat-tile counts the number inside its pre-formatted text via parseFigureText.

Narrow runs: <the Tests verdict lines from Steps 11 and 12>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

