# v151 Plan detail page and the shared "Why" panel: Part 2b, If-it-gets-there and Sizing panels

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V151-12:" -A 400 docs/superpowers/plans/2026-10-10-v151-plan-detail-why-panel_2b-gets-there-and-sizing.md`.

**Bump:** ui minor · bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v151-plan-detail-why-panel-design.md`](../specs/2026-10-09-v151-plan-detail-why-panel-design.md)

This file continues Part 2 ([`_2-store-and-why-components`](2026-10-10-v151-plan-detail-why-panel_2-store-and-why-components.md)): Part 2 reached the 1500-line cap after V151-10, and a task is never split or compressed to fit. V151-11 and V151-12 are the last two tasks of Phase 5 (Group A, parallel after V151-8). Global constraints, decisions, the wire contract, the task ledger and `## Parallelisation` live in the index: [`2026-10-10-v151-plan-detail-why-panel_0-index.md`](2026-10-10-v151-plan-detail-why-panel_0-index.md). The short version:

- These components are **not** mounted on any page here. V151-15 (trade page) and V151-16 (plan page) compose them.
- Do not define `.pos`, `.neg`, `.muted`, `.head`, `.row-link`, `.note` or `.chips` in a component's `styles` (`ui/primitives.spec.ts`); use the globals from `styles.css`. No hex colours, no outer margin on an `sb-panel` selector (`ui/spacing.spec.ts`), and only CSS custom properties that already exist.
- Narrow verification per task: `npm --prefix frontend test -- --include <spec> --watch=false`. **Never `cd` in Bash.** Stage files by name, never `git add -A`. Do not bump `VERSION.json`.

# Phase 5 (continued): the Why components

### Task V151-11: `sb-if-it-gets-there`

**Model:** haiku — a verbatim extraction of one small panel with its two direction words; the code and tests are given in full.

**Files:**
- Create: `frontend/src/app/workspaces/trades/why/if-it-gets-there.ts`
- Test: `frontend/src/app/workspaces/trades/why/if-it-gets-there.spec.ts`

**Interfaces:**
- Consumes: `Panel` (`ui/layout`), `num` (`ui/format`). Extracted from `trade-detail.ts:253-272` (the `[heading]="ifItGetsThereHeading()"` panel) and its `levelWord` / `oppositeWord` / `ifItGetsThereHeading` computeds (~:1015-1024). `trade-detail.ts` itself is not edited here; V151-15 swaps the panel for this component.
- Produces: `export class IfItGetsThere` (selector `sb-if-it-gets-there`); inputs `direction: string | null`, `target2: number | null`, `stopLoss: number | null`, all defaulting to `null`.

Behaviour is the trade page's, unchanged: heading `If it gets there`; "Continues past resistance 1 → next stop <target2>" (or `no further level found`), "Reverses at resistance 1 → pulls back toward support at <stop>". A short (`bearish`) swaps the words: support / resistance.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/workspaces/trades/why/if-it-gets-there.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { IfItGetsThere } from './if-it-gets-there';

function render(direction: string | null, target2: number | null, stopLoss: number | null): string {
  const fixture = TestBed.createComponent(IfItGetsThere);
  fixture.componentRef.setInput('direction', direction);
  fixture.componentRef.setInput('target2', target2);
  fixture.componentRef.setInput('stopLoss', stopLoss);
  fixture.detectChanges();
  return ((fixture.nativeElement as HTMLElement).textContent ?? '').replace(/\s+/g, ' ');
}

describe('IfItGetsThere (v151 extraction)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('keeps the heading', () => {
    expect(render('bullish', 120, 95)).toContain('If it gets there');
  });

  it('words a long against resistance, with the next level and the stop', () => {
    const text = render('bullish', 120, 95);
    expect(text).toContain('Continues past resistance 1');
    expect(text).toContain('next stop 120.00');
    expect(text).toContain('Reverses at resistance 1');
    expect(text).toContain('pulls back toward support at 95.00');
  });

  it('words a short against support', () => {
    const text = render('bearish', 80, 105);
    expect(text).toContain('Continues past support 1');
    expect(text).toContain('pulls back toward resistance at 105.00');
  });

  it('says so when there is no further level', () => {
    expect(render('bullish', null, 95)).toContain('no further level found');
  });

  it('renders a dash for an unknown stop', () => {
    expect(render(null, 120, null)).toContain('pulls back toward support at —');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/why/if-it-gets-there.spec.ts --watch=false`
Expected: FAIL, `Cannot find module './if-it-gets-there'`.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/workspaces/trades/why/if-it-gets-there.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { num } from '../../../ui/format';
import { Panel } from '../../../ui/layout';

/**
 * SR60 "If it gets there", extracted from the trade page (v151) so the plan
 * page can show it for a PENDING plan before the trigger fires. Derived from
 * target2 and the stop, both shown elsewhere; what this adds is the sentence
 * saying what they MEAN if price reaches TP1.
 */
@Component({
  selector: 'sb-if-it-gets-there',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <sb-panel heading="If it gets there">
      <dl>
        <div>
          <dt>Continues past {{ levelWord() }} 1</dt>
          <dd class="num">
            @if (target2() !== null) {
              next stop {{ fmt(target2()) }}
            } @else {
              <span class="absent">no further level found</span>
            }
          </dd>
        </div>
        <div>
          <dt>Reverses at {{ levelWord() }} 1</dt>
          <dd class="num">
            pulls back toward {{ oppositeWord() }} at {{ fmt(stopLoss()) }}
          </dd>
        </div>
      </dl>
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    dl { display: grid; gap: var(--space-6); }
    dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }
    dt { color: var(--text-secondary); font-size: var(--text-table); }
    dd { color: var(--text); font-size: var(--text-table); }
  `,
})
export class IfItGetsThere {
  readonly direction = input<string | null>(null);
  readonly target2 = input<number | null>(null);
  readonly stopLoss = input<number | null>(null);

  protected readonly fmt = num;

  /** `admin/app.py:691` -- Resistance for a long, Support for a short. "next
   *  stop 210" reads differently above and below price. */
  protected readonly levelWord = computed(() =>
    this.direction() === 'bearish' ? 'support' : 'resistance',
  );
  protected readonly oppositeWord = computed(() =>
    this.direction() === 'bearish' ? 'resistance' : 'support',
  );
}
```

`.absent` is the class the trade page uses for the same span; if `git grep -n "\.absent" -- frontend/src/styles.css` finds no global rule, it is an unstyled marker there too, and stays one here.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/why/if-it-gets-there.spec.ts --watch=false`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/trades/why/if-it-gets-there.ts frontend/src/app/workspaces/trades/why/if-it-gets-there.spec.ts
git commit -m "feat(ui): v151 extract the If-it-gets-there panel (V151-11)"
```

### Task V151-12: `sb-sizing-panel` + gap-risk row

**Model:** sonnet — extraction plus one new row whose absent/false/true states must each read correctly.

**Files:**
- Create: `frontend/src/app/workspaces/trades/why/sizing-panel.ts`
- Test: `frontend/src/app/workspaces/trades/why/sizing-panel.spec.ts`

**Interfaces:**
- Consumes: `Panel` (`ui/layout`), `Chip` (`ui/chip`), `num`, `share`, `text` (`ui/format`). Extracted from `trade-detail.ts:274-298` (the `Sizing` panel). The gap inputs come from V151-8's `TradeDetailStore.gapP90Pct()` (a percent of price, e.g. `1.85`) and `gapFragile()` (`boolean | null`); V151-15 / V151-16 do the binding.
- Produces: `export class SizingPanel` (selector `sb-sizing-panel`); inputs, all defaulting to `null`: `shares: number | null`, `positionValue: number | null`, `sizingMode: string | null`, `workingStop: number | null`, `gapP90Pct: number | null`, `gapFragile: boolean | null`.

**Rules (spec § Sizing panel — gap risk):** the trade page's panel unchanged (heading `Sizing`, the snapshot help line, Shares with 0 decimals, Deployed, Sizing mode, Working stop), plus one last row `Gap risk (p90)` showing `gap_p90_pct` as a percentage with 2 decimals, `—` when absent. A `fragile` chip (tone `warn`) follows the figure only when `gapFragile` is exactly `true`: the stop sits inside 90th-percentile gap noise (`swingbot/core/edge/context.py`). No max-chase figure exists in the codebase, so none is shown.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/workspaces/trades/why/sizing-panel.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { SizingPanel } from './sizing-panel';

const BASE: Record<string, unknown> = {
  shares: 120,
  positionValue: 12000,
  sizingMode: 'risk_pct',
  workingStop: 99,
  gapP90Pct: 1.85,
  gapFragile: false,
};

function render(overrides: Record<string, unknown> = {}): HTMLElement {
  const fixture = TestBed.createComponent(SizingPanel);
  for (const [key, value] of Object.entries({ ...BASE, ...overrides })) {
    fixture.componentRef.setInput(key, value);
  }
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

const gapRow = (el: HTMLElement) => el.querySelector<HTMLElement>('.gap-row')!;

describe('SizingPanel (v151)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('keeps the trade page rows and help line', () => {
    const text = render().textContent ?? '';
    expect(text).toContain('Sizing');
    expect(text).toContain('Position size is snapshotted when the trade opens.');
    expect(text).toContain('Shares');
    expect(text).toContain('120');
    expect(text).toContain('Deployed');
    expect(text).toContain('12,000.00');
    expect(text).toContain('risk_pct');
    expect(text).toContain('Working stop');
    expect(text).toContain('99.00');
  });

  it('adds the p90 gap as the last row', () => {
    const el = render();
    const labels = [...el.querySelectorAll('dt')].map((dt) => (dt.textContent ?? '').trim());
    expect(labels.at(-1)).toBe('Gap risk (p90)');
    expect(gapRow(el).textContent).toContain('1.85%');
  });

  it('chips a fragile stop', () => {
    const row = gapRow(render({ gapFragile: true }));
    expect(row.querySelector('sb-chip')).not.toBeNull();
    expect(row.textContent).toContain('fragile');
  });

  it('shows no chip when the stop clears gap noise, or when it is unknown', () => {
    expect(gapRow(render()).querySelector('sb-chip')).toBeNull();
    expect(gapRow(render({ gapFragile: null })).querySelector('sb-chip')).toBeNull();
  });

  it('renders a dash when the gap was never recorded', () => {
    const row = gapRow(render({ gapP90Pct: null, gapFragile: null }));
    expect(row.textContent).toContain('—');
    expect(row.textContent).not.toContain('%');
  });

  it('renders dashes for a record with no sizing snapshot', () => {
    const el = render({ shares: null, positionValue: null, sizingMode: null, workingStop: null });
    expect((el.textContent ?? '').match(/—/g)?.length).toBeGreaterThanOrEqual(4);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/why/sizing-panel.spec.ts --watch=false`
Expected: FAIL, `Cannot find module './sizing-panel'`.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/workspaces/trades/why/sizing-panel.ts`:

```ts
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { Chip } from '../../../ui/chip';
import { num, share, text } from '../../../ui/format';
import { Panel } from '../../../ui/layout';

/**
 * The trade page's Sizing panel (SR60), extracted in v151 so the plan page can
 * show it for a PENDING plan, plus one row: gap risk. A stop inside the
 * 90th-percentile overnight gap can be jumped on the open, so the plan's
 * dollar risk is a floor, not a cap — the "fragile" chip says so.
 */
@Component({
  selector: 'sb-sizing-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Chip, Panel],
  template: `
    <sb-panel heading="Sizing">
      <p class="section-help">
        Position size is snapshotted when the trade opens. A trade with
        no sizing snapshot was logged before that feature existed.
      </p>
      <dl>
        <div>
          <dt>Shares</dt>
          <dd class="num">{{ fmt(shares(), 0) }}</dd>
        </div>
        <div>
          <dt>Deployed</dt>
          <dd class="num">{{ fmt(positionValue()) }}</dd>
        </div>
        <div>
          <dt>Sizing mode</dt>
          <dd>{{ fmtText(sizingMode()) }}</dd>
        </div>
        <div>
          <dt>Working stop</dt>
          <dd class="num">{{ fmt(workingStop()) }}</dd>
        </div>
        <div class="gap-row">
          <dt>Gap risk (p90)</dt>
          <dd class="num">
            {{ fmtShare(gapP90Pct(), 2) }}
            @if (gapFragile() === true) {
              <sb-chip label="fragile" tone="warn" [title]="fragileTooltip" />
            }
          </dd>
        </div>
      </dl>
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    dl { display: grid; gap: var(--space-6); }
    dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }
    dt { color: var(--text-secondary); font-size: var(--text-table); }
    dd { color: var(--text); font-size: var(--text-table); }
    .gap-row dd { display: inline-flex; align-items: center; gap: var(--space-6); }
  `,
})
export class SizingPanel {
  readonly shares = input<number | null>(null);
  readonly positionValue = input<number | null>(null);
  readonly sizingMode = input<string | null>(null);
  readonly workingStop = input<number | null>(null);
  readonly gapP90Pct = input<number | null>(null);
  readonly gapFragile = input<boolean | null>(null);

  protected readonly fragileTooltip =
    'The stop sits inside 90th-percentile gap noise: an overnight gap can jump it.';
  protected readonly fmt = num;
  protected readonly fmtText = text;
  protected readonly fmtShare = share;
}
```

`share(value, 2)` is the unsigned percentage formatter (`ui/format.ts:30`): a gap size is a magnitude, not a movement, so it carries no `+`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/why/sizing-panel.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/spacing.spec.ts --watch=false`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/trades/why/sizing-panel.ts frontend/src/app/workspaces/trades/why/sizing-panel.spec.ts
git commit -m "feat(ui): v151 extract the Sizing panel and add the gap-risk row (V151-12)"
```
