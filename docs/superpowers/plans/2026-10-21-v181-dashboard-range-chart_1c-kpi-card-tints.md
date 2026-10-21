# v181 — Dashboard range chart: Part 1c — KPI card tints (V181-9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V181-9:" -A 400 <this file>`.

**Spec:** [2026-10-21-v181-dashboard-range-chart-design.md](../specs/2026-10-21-v181-dashboard-range-chart-design.md)
**Index:** [2026-10-21-v181-dashboard-range-chart_0-index.md](2026-10-21-v181-dashboard-range-chart_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there and bind this task.

V181-9 is a ledger row of part 1b; it moved to this file because part 1b (`2026-10-21-v181-dashboard-range-chart_1b-palette-chart-and-cards.md`, V181-5..V181-8) would otherwise pass the 1500-line limit. Ids, files and contracts are the ledger's, unchanged.

Work in the worktree `.claude/worktrees/2026-10-21-v181-dashboard-range-chart`. Frontend commands run from `frontend/`. The runner is `npx ng test --watch=false --include <spec> …`, never bare `npx vitest run` (it skips `TestBed.initTestEnvironment()`); a run that dies after exactly 60 s with `Timeout waiting for worker to respond` ran nothing — re-run it.

---

# Phase 5 — The cards

### Task V181-9: KPI card tones, tints and the account caption

**Model:** sonnet — three components and a new spec, all wiring V181-4's tone helpers into templates; a pinned source-text marker constrains how the tint is applied.

**Files:**
- Modify: `frontend/src/app/ui/metric-card.ts`
- Create: `frontend/src/app/ui/metric-card.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/portfolio-value.spec.ts`

**Interfaces:**
- Consumes: V181-4 (`equity-range.model.ts`) `PnlTone`, `signTone(value: number | null): PnlTone`, `breakevenPairTone(winRatePct: number | null, payoff: number | null, closes: number | null): PnlTone`, `riskTone(usedPct: number | null, capPct: number | null): PnlTone`; V181-5 `--pos-soft` / `--neg-soft` (passing the contrast gate as a blend over `--surface`); `ACCOUNT_LABEL` from `equity-candles.model.ts` (text unchanged).
- Produces: `MetricCard` input `tint = input<PnlTone | null>(null)` — `'pos'`/`'neg'` tint the card and colour the figure, `'warn'` colours the figure only, `'neutral'` is plain, a null value (the em dash) is never coloured or tinted; `null` keeps the v80 `tone` rule. `TradingPerformance` computeds `openPnlTone`, `winPairTone`, `payoffTone` (the same pair), `expectancyTone`, `realizedTone`, `riskTone`, `changeTone`. V181-14 edits `trading-performance.ts` next and keeps these names.

Rules (spec §5, index Global Constraints): sign for Open P&L, Expectancy, Realised and the day change; win rate and payoff judged **as a pair** against break-even (`closes` = `winRateN`, the number of closes in scope); risk used against its cap; Open trades and Avg confidence neutral. The phone summary rows take the same tint. `ACCOUNT_LABEL` is repeated under the KPI grid (one wording, spec §4).

`ui/` never imports from `workspaces/`, so `metric-card.ts` declares `CardTint`, the same four-member union as `PnlTone`; TypeScript's structural typing makes the two interchangeable, which is what lets `[tint]="winPairTone()"` bind without a cast. `ui/primitives.spec.ts:322` pins the literal `<div class="card sb-lift">`, so the tint goes on the **host** element (`host: { '[class.tint-pos]': … }`), never as an attribute on that div.

- [ ] **Step 1: Write the failing card spec**

Create `frontend/src/app/ui/metric-card.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { MetricCard } from './metric-card';

describe('sb-metric-card tint (v181 §5)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(MetricCard);
    f.componentRef.setInput('label', 'Figure');
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    const host = f.nativeElement as HTMLElement;
    return { host, value: host.querySelector('.value')! };
  }

  it('tints the card and colours the figure for a good or bad figure', () => {
    const good = render({ value: 1.2, tint: 'pos' });
    expect(good.host.classList.contains('tint-pos')).toBe(true);
    expect(good.value.classList.contains('pos')).toBe(true);
    const bad = render({ value: 1.2, tint: 'neg' });
    expect(bad.host.classList.contains('tint-neg')).toBe(true);
    expect(bad.value.classList.contains('neg')).toBe(true);
  });

  it('colours a warning figure without tinting the card', () => {
    const { host, value } = render({ value: 5, tint: 'warn' });
    expect(value.classList.contains('warn')).toBe(true);
    expect(host.classList.contains('tint-pos') || host.classList.contains('tint-neg')).toBe(false);
  });

  it('leaves a neutral card plain, whatever the sign', () => {
    const { host, value } = render({ value: -3, tint: 'neutral', tone: 'pnl' });
    expect(['pos', 'neg', 'warn'].some((c) => value.classList.contains(c))).toBe(false);
    expect(host.classList.contains('tint-neg')).toBe(false);
  });

  it('never colours or tints the dash of a missing figure', () => {
    const { host, value } = render({ value: null, tint: 'pos' });
    expect(value.classList.contains('absent')).toBe(true);
    expect(value.classList.contains('pos')).toBe(false);
    expect(host.classList.contains('tint-pos')).toBe(false);
  });

  it('keeps the v80 tone rule when no tint is given', () => {
    const { host, value } = render({ value: -2, tone: 'pnl' });
    expect(value.classList.contains('neg')).toBe(true);
    expect(host.classList.contains('tint-neg')).toBe(false);
  });
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/metric-card.spec.ts`
Expected: FAIL — `NG0303: Can't set value of the 'tint' input` (no such input) on every tint test; the last test passes.

- [ ] **Step 3: Add the tint to `MetricCard`**

In `frontend/src/app/ui/metric-card.ts`, below `MetricTone`:

```ts
/** v181 §5: how a figure is judged — the same union as `PnlTone` in
 *  `equity-range.model.ts` (ui/ does not import from workspaces/; the two
 *  are structurally one type). pos/neg tint the card, warn colours only. */
export type CardTint = 'pos' | 'neg' | 'warn' | 'neutral';

const TINT_CLASS: Record<CardTint, string> = { pos: 'pos', neg: 'neg', warn: 'warn', neutral: '' };

/** The v80 rule, used when no tint is given. */
function toneClass(tone: MetricTone, value: number): string {
  if (tone === 'caution') return 'warn';
  if (tone !== 'pnl') return '';
  // Exactly zero is neither a profit nor a loss, and colouring it green
  // would overstate a flat position.
  if (value > 0) return 'pos';
  if (value < 0) return 'neg';
  return '';
}
```

In the `@Component` metadata add (the template's `<div class="card sb-lift">` stays byte for byte):

```ts
  host: {
    '[class.tint-pos]': "cardTint() === 'pos'",
    '[class.tint-neg]': "cardTint() === 'neg'",
  },
```

Append to `styles` (the soft tint is laid over `--surface`, exactly the blend `contrast.spec.ts` measures):

```css
    :host(.tint-pos) .card { background: linear-gradient(var(--pos-soft), var(--pos-soft)), var(--surface); }
    :host(.tint-neg) .card { background: linear-gradient(var(--neg-soft), var(--neg-soft)), var(--surface); }
```

In the class, add the input after `subPnl` and replace `valueClass`:

```ts
  /** v181 §5: the judged tone of the figure (see `CardTint`). Wins over
   *  `tone`; null keeps the v80 `tone` rule. */
  readonly tint = input<CardTint | null>(null);

  /** Only a present figure judged good or bad tints its card. */
  protected readonly cardTint = computed(() => {
    const tint = this.tint();
    return this.value() !== null && (tint === 'pos' || tint === 'neg') ? tint : null;
  });

  protected readonly valueClass = computed(() => {
    const value = this.value();
    if (value === null) return 'absent';
    const tint = this.tint();
    return tint !== null ? TINT_CLASS[tint] : toneClass(this.tone(), value);
  });
```

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/metric-card.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/motion/count-up.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 4: Write the failing panel tests**

In `trading-performance.spec.ts`, add `import { ACCOUNT_LABEL } from './equity-candles.model';` and, inside the first `describe` after `render`, the helpers:

```ts
  function card(el: HTMLElement, label: string): HTMLElement {
    return [...el.querySelectorAll<HTMLElement>('sb-metric-card')]
      .find((c) => c.querySelector('.label')?.textContent?.trim() === label)!;
  }

  function tint(c: HTMLElement): 'pos' | 'neg' | null {
    if (c.classList.contains('tint-pos')) return 'pos';
    return c.classList.contains('tint-neg') ? 'neg' : null;
  }

  function row(el: HTMLElement, label: string): HTMLElement {
    return [...el.querySelectorAll<HTMLElement>('.mobile-summary > div')]
      .find((d) => d.querySelector('span')?.textContent?.trim() === label)!;
  }
```

and the tests:

```ts
  it('judges win rate and payoff together against break-even', () => {
    // payoff 1.0 -> break-even 50%; the band is +/-0.5 pp.
    const pair = (winRate: number, winRateN = 12) => {
      const el = render({ winRate, winRateN, payoffRatio: 1, currency: '€', scope: 'today' });
      return [tint(card(el, 'Win rate')), tint(card(el, 'Payoff ratio'))];
    };
    expect(pair(60)).toEqual(['pos', 'pos']);
    expect(pair(40)).toEqual(['neg', 'neg']);
    expect(pair(50.3)).toEqual([null, null]);
    expect(pair(60, 4)).toEqual([null, null]);
  });

  it('tints open P&L, expectancy and realised by sign, and never a dash', () => {
    const el = render({ openPnlPct: 1.2, expectancyR: -0.16, realizedAmount: null,
                        currency: '€', scope: 'today' });
    expect(tint(card(el, 'Open P&L'))).toBe('pos');
    expect(tint(card(el, 'Expectancy'))).toBe('neg');
    const realised = card(el, 'Realised today');
    expect(tint(realised)).toBeNull();
    expect(realised.querySelector('.value')!.classList.contains('absent')).toBe(true);
  });

  it('warns on risk used near the cap and marks it bad at the cap', () => {
    const risk = (riskUsedPct: number) => card(
      render({ riskUsedPct, riskCapPct: 6, currency: '€', scope: 'today' }), 'Risk used');
    expect(risk(3).querySelector('.value')!.className).not.toMatch(/\b(pos|neg|warn)\b/);
    expect(risk(5).querySelector('.value')!.classList.contains('warn')).toBe(true);
    expect(tint(risk(5))).toBeNull();
    expect(tint(risk(6))).toBe('neg');
  });

  it('never judges open trades or average confidence', () => {
    const el = render({ openTrades: 3, avgConfidence: 4.5, currency: '€', scope: 'today' });
    for (const label of ['Open trades', 'Avg confidence']) {
      expect(tint(card(el, label))).toBeNull();
      expect(card(el, label).querySelector('.value')!.className).not.toMatch(/\b(pos|neg|warn)\b/);
    }
  });

  it('gives the phone summary rows the same tones', () => {
    const el = render({ changePct: -0.4, winRate: 60, winRateN: 12, payoffRatio: 1, expectancyR: 0.2,
                        realizedAmount: 15, riskUsedPct: 5, riskCapPct: 6, openTrades: 2,
                        realizedLabel: 'Realised today', currency: '€', scope: 'today' });
    expect(row(el, 'Today').getAttribute('data-tone')).toBe('neg');
    expect(row(el, 'Win rate').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Payoff').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Expectancy').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Realised today').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Risk').getAttribute('data-tone')).toBe('warn');
    expect(row(el, 'Open').getAttribute('data-tone')).toBeNull();
  });

  it('states what the account is under the KPI grid, in the chart caption\'s words', () => {
    const el = render({ currency: '€', scope: 'today' });
    const captions = [...el.querySelectorAll('.account')]
      .map((p) => p.textContent?.trim());
    expect(captions.filter((text) => text === ACCOUNT_LABEL).length).toBe(2);
    expect(el.querySelector('.mobile-summary + .account')).not.toBeNull();
  });
```

(Two captions: the chart's own, under its readout (V181-7), and the KPI grid's; the second follows the phone summary so it reads under the figures at every width.)

In `portfolio-value.spec.ts`, append inside the `describe`:

```ts
  it('leaves a flat day uncoloured', () => {
    const change = render({ balance: 1, changePct: 0, currency: '€' }).querySelector('.change')!;
    expect(change.classList.contains('pos') || change.classList.contains('neg')).toBe(false);
  });
```

- [ ] **Step 5: Run them to see them fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --include src/app/workspaces/dashboard/panels/portfolio-value.spec.ts`
Expected: FAIL — no `tint-*` classes, no `data-tone` on the summary rows, one `.account` caption instead of two. (`'leaves a flat day uncoloured'` already passes; it guards the `signTone` swap below.)

- [ ] **Step 6: Wire the tones into the panel**

In `trading-performance.ts`, add the imports:

```ts
import { ACCOUNT_LABEL } from './equity-candles.model';
import { breakevenPairTone, riskTone as riskToneOf, signTone } from './equity-range.model';
```

Replace the `.grid` block of the template:

```html
        <div class="grid">
          <sb-metric-card label="Open P&L" [value]="openPnlPct()" [tint]="openPnlTone()" unit="%" [sub]="openPnlSub()" [subPnl]="openPnlAmount()" />
          <sb-metric-card label="Win rate" [value]="winRate()" [tint]="winPairTone()" unit="%" [decimals]="1" [sub]="sample(winRateN())" />
          <sb-metric-card label="Expectancy" [value]="expectancyR()" [tint]="expectancyTone()" unit="R" [sub]="sample(expectancyN())" />
          <sb-metric-card label="Payoff ratio" [value]="payoffRatio()" [tint]="payoffTone()" [decimals]="2" [sub]="noCloseHint(payoffRatio())" />
          <sb-metric-card [label]="realizedLabel()" [value]="realizedAmount()" [tint]="realizedTone()"
                          [unit]="currencyUnit()" [sub]="noCloseHint(realizedAmount())" />
          <sb-metric-card label="Open trades" [value]="openTrades()" [decimals]="0" />
          <sb-metric-card label="Avg confidence" [value]="avgConfidence()" [decimals]="1" />
          <sb-metric-card label="Risk used" [value]="riskUsedPct()" [tint]="riskTone()" unit="%" [sub]="riskSub()" />
        </div>
```

Replace the `.mobile-summary` block and add the caption after it (still inside `<sb-panel>`):

```html
      <div class="mobile-summary" aria-label="Portfolio summary">
        <div><span>Portfolio</span><strong>{{ fmtAmount(balance()) }}</strong></div>
        <div [attr.data-tone]="tinted(changeTone())"><span>Today</span><strong>{{ fmtPct(changePct()) }}</strong></div>
        <div><span>Open</span><strong>{{ openTrades() }}</strong></div>
        <div [attr.data-tone]="tinted(riskTone())"><span>Risk</span><strong>{{ fmtPct(riskUsedPct()) }}</strong></div>
        <div [attr.data-tone]="tinted(winPairTone())"><span>Win rate</span><strong>{{ fmtFigure(winRate(), '%', 1) }}</strong></div>
        <div [attr.data-tone]="tinted(expectancyTone())"><span>Expectancy</span><strong>{{ fmtFigure(expectancyR(), 'R', 2) }}</strong></div>
        <div [attr.data-tone]="tinted(payoffTone())"><span>Payoff</span><strong>{{ fmtFigure(payoffRatio(), '', 2) }}</strong></div>
        <div [attr.data-tone]="tinted(realizedTone())"><span>{{ realizedLabel() }}</span><strong>{{ fmtFigure(realizedAmount(), currencyUnit(), 2) }}</strong></div>
      </div>
      <p class="account">{{ accountLabel }}</p>
```

Styles — in the `max-width: 639px` block replace the two `.mobile-summary .pos/.neg` rules and give rows side padding so a tint has room:

```css
      .mobile-summary div { display: flex; justify-content: space-between; gap: var(--space-8); padding: var(--space-6); border-bottom: 1px solid var(--border); font-size: var(--text-table); }
      .mobile-summary [data-tone='pos'] { background: var(--pos-soft); }
      .mobile-summary [data-tone='neg'] { background: var(--neg-soft); }
      .mobile-summary [data-tone='pos'] strong { color: var(--pos); }
      .mobile-summary [data-tone='neg'] strong { color: var(--neg); }
      .mobile-summary [data-tone='warn'] strong { color: var(--warn); }
```

and, outside the media blocks, after `.mobile-summary { display: none; }`:

```css
    /* v181 §4: every figure here is simulated, before costs and tax. */
    .account { margin: var(--space-10) 0 0; font-size: var(--text-chip); color: var(--text-muted); }
```

In the class, add below `riskSub`:

```ts
  protected readonly accountLabel = ACCOUNT_LABEL;
  protected readonly changeTone = computed(() => signTone(this.changePct()));
  protected readonly openPnlTone = computed(() => signTone(this.openPnlPct()));
  protected readonly expectancyTone = computed(() => signTone(this.expectancyR()));
  protected readonly realizedTone = computed(() => signTone(this.realizedAmount()));
  /** v181 §5: win rate and payoff are judged as a pair against break-even
   *  (100 / (1 + payoff)), never alone; neutral under 5 closes in scope. */
  protected readonly winPairTone = computed(() =>
    breakevenPairTone(this.winRate(), this.payoffRatio(), this.winRateN()));
  protected readonly payoffTone = computed(() => this.winPairTone());
  protected readonly riskTone = computed(() => riskToneOf(this.riskUsedPct(), this.riskCapPct()));
  /** A summary row carries a tone attribute only when it is judged. */
  protected tinted(tone: string): string | null {
    return tone === 'neutral' ? null : tone;
  }
```

In `portfolio-value.ts`, add `import { signTone } from './equity-range.model';`, the computed `protected readonly changeTone = computed(() => signTone(this.changePct()));`, and change the change paragraph to:

```html
      <p class="change" [class.pos]="changeTone() === 'pos'" [class.neg]="changeTone() === 'neg'">
```

- [ ] **Step 7: Run the cards, the panel and the dashboard**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/metric-card.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/motion/count-up.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --include src/app/workspaces/dashboard/panels/portfolio-value.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/ui/metric-card.ts frontend/src/app/ui/metric-card.spec.ts \
  frontend/src/app/workspaces/dashboard/panels/trading-performance.ts \
  frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts \
  frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts \
  frontend/src/app/workspaces/dashboard/panels/portfolio-value.spec.ts
git commit -m "feat(v181): KPI cards judged and tinted (break-even pair, risk vs cap), account caption on the grid" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

