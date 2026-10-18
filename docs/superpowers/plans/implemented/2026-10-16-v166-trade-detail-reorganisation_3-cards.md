# v166 Trade detail reorganisation. Part 3: Overview cards (TD7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task TD8:" -A 400 docs/superpowers/plans/2026-10-16-v166-trade-detail-reorganisation_3-cards.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v166-trade-detail-reorganisation-design.md`](../specs/2026-10-16-v166-trade-detail-reorganisation-design.md) (this part: § 3 Plan, Position and Outcome cards; Edge cases; Amendments 1, 2, 4; Panel review rows on the working stop, resting-stop cue, order side, gap note, $ at risk)
**Index:** [`2026-10-16-v166-trade-detail-reorganisation_0-index.md`](2026-10-16-v166-trade-detail-reorganisation_0-index.md) carries the header, `## Global Constraints`, `## Review Focus`, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation` (created in TD1 Step 1). Never `cd`; use `git -C $WT` and `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec>`. All file paths below are relative to `$WT`.

**`GATES`** (from the index) = `--include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts`.

**Order.** TD7 needs TD2, TD3 and TD4 committed (it imports `reasonLabel`, `orderWording`, `pctFrom`, `outcomeTone`, `Tone`, `StatusGroup` and the store's `Leg`/`StatusEvent` types). TD8 (the Why cards and `whyAreas`) is in `_3b-why-cards.md`, split out so neither file passes the 1500-line cap. TD7 and TD8 create new files only, so they may run beside each other and beside TD5/TD6. Neither mounts anything in `trade-detail.ts`: TD9 (Why tab) and TD10 (Overview tab) do. The two-column `dl` container rule for these cards is added later by TD11; here every `dl` is single-column.

**Shared card styling** (both tasks). Each card is an `sb-panel` (or a stack of them) inside a component whose `:host` is `display: block; min-width: 0` (a stack uses `display: grid; gap: var(--section-gap)`). No card sets an outer margin (spacing between cards is the grid's `gap`, TD11), no file defines `.pos`, `.neg`, `.muted`, `.head`, `.note`, `.chips` or `.row-link` (use the global `.pos`/`.neg`/`.muted`/`.num` classes), no hex literal, only tokens that exist (`--space-4/6/8/10/14/20`, `--section-gap`, `--text-*`, `--surface*`, `--border*`, `--warn`, `--radius`).

---

# Phase 3 — Presentational cards

### Task TD7: Overview cards: `sb-trade-plan-card`, `sb-trade-position-card`, `sb-trade-outcome-card`

**Model:** sonnet — three presentational components with pure row builders

**Files:**
- Create: `frontend/src/app/workspaces/trades/plan-card.ts`
- Create: `frontend/src/app/workspaces/trades/plan-card.spec.ts`
- Create: `frontend/src/app/workspaces/trades/position-card.ts`
- Create: `frontend/src/app/workspaces/trades/position-card.spec.ts`
- Create: `frontend/src/app/workspaces/trades/outcome-card.ts`
- Create: `frontend/src/app/workspaces/trades/outcome-card.spec.ts`

**Interfaces:**
- Consumes (TD2, `exit-reasons.ts`): `reasonLabel(reason: string | null | undefined): string | null` (trim + lower-case lookup; unknown -> trimmed raw text; null/empty -> null).
- Consumes (TD3, `trade-figures.ts`): `type Tone = 'pos' | 'neg' | null`; `outcomeTone(r: number | null): Tone` (null inside ±0.1R); `type StatusGroup = 'closed' | 'open' | 'pending' | 'unfilled'`; `orderWording(entryType: string | null, direction: string | null, price: number | null): string` (`stop_entry` + bullish -> `Buy stop 142.20`; `market` + bearish -> `Market (short)`; null -> `—`); `pctFrom(from: number | null, to: number | null): number | null`.
- Consumes (`main`): `Leg {fraction: number | null; exitPrice: number | null; r: number | null; reason: string | null}` and `StatusEvent {status: string; reason: string | null; at: string | null}` from `frontend/src/app/stores/trade-detail.store.ts`; `PAPER_LINE` from `why/levels-block.ts` (constant import only; the component is not used); `IfItGetsThere` (`sb-if-it-gets-there`, inputs `direction`, `target2`, `stopLoss`) and `OutcomePath` (`sb-outcome-path`, inputs `legs: Leg[]`, `timeline: StatusEvent[]`) from `why/`, unchanged; `Panel` (`sb-panel`), `Chip` (`sb-chip`) and `num`, `pct`, `share`, `rMultiple`, `date`, `text`, `ABSENT` from `ui/`.
- Produces (`plan-card.ts`, consumed by TD10 and TD11): `interface PlanFigures {direction: string | null; status: string; entryType: string | null; trigger: number | null; entry: number | null; riskStop: number | null; stopLoss: number | null; workingStop: number | null; target1: number | null; target2: number | null; acceptance: number | null; riskReward: number | null; riskPerShare: number | null; rewardPerShare: number | null}`; `interface PlanRow {level: string; price: number | null; pctFromEntry: number | null; tone: Tone; note: string | null}`; `planRows(f: PlanFigures): PlanRow[]`; `restingStopLine(f: PlanFigures): string | null`; `rrLine(f: PlanFigures): string | null`; `gapNoteApplies(f: PlanFigures): boolean`; `GAP_NOTE`; component `PlanCard`, selector `sb-trade-plan-card`, `figures = input.required<PlanFigures>()`. DOM: one `sb-panel` headed `Plan`, `table.levels` with one `tr[data-level="<level>"]` per row (`th`, `td.price`, `td.from`), `p.resting-stop`, `p.rr-line`, `p.gap-line`, `p.paper-line`.
- Produces (`position-card.ts`, consumed by TD10 and TD11): `interface PositionFigures {status: string; shares: number | null; positionValue: number | null; dollarAtRisk: number | null; sizingMode: string | null; gapP90Pct: number | null; gapFragile: boolean | null; tp1Pct: number | null; breakevenTriggerPct: number | null; trailAtrMult: number | null; expiresOn: string | null; timeExitOn: string | null; holdCapBars: number | null}`; `interface PositionRow {label: string; value: string; sub: string | null; fragile: boolean}`; `positionRows(f: PositionFigures): PositionRow[]`; `SNAPSHOT_SENTENCE`; `PARTIAL_RISK_SUB = 'open shares, at original stop'`; component `PositionCard`, selector `sb-trade-position-card`, `figures = input.required<PositionFigures>()`. DOM: one `sb-panel` headed `Position`, `dl` with one `div[data-row="<label>"]` per row, `p.section-help` only when `sizingMode` is null.
- Produces (`outcome-card.ts`, consumed by TD10): `interface LegRow {share: string; exit: string; r: string; tone: Tone; reason: string}`; `legRows(legs: readonly Leg[]): LegRow[]`; component `OutcomeCard`, selector `sb-trade-outcome-card`, inputs `group = input.required<StatusGroup>()`, `direction = input<string | null>(null)`, `target2 = input<number | null>(null)`, `stopLoss = input<number | null>(null)`, `legs = input<readonly Leg[]>([])`, `timeline = input<readonly StatusEvent[]>([])`. DOM: `sb-if-it-gets-there` on `open`/`pending`; an `sb-panel` headed `Exit legs` with `table.legs` on `closed` when there is at least one leg; then `sb-outcome-path` fed `[legs]="[]"` (so its own raw-reason "Scale-out" panel never renders) and the timeline.

**Decisions this task fixes** (spec § 3, Edge cases, amendments 2 and 4, panel rows):
- **Plan rows, in order:** `Order` (its price cell carries the order wording, e.g. `Buy stop 142.20`, priced at the trigger, else the entry); `Trigger` only when it differs from entry; `Entry`; `Stop` = `riskStop ?? stopLoss`, tinted `neg`; `Working stop` only when both `workingStop` and `riskStop` are known and differ, with note `(was <risk stop>)` and no tint (a working stop above entry locks profit, so red would mislead); `Target 1` tinted `pos`; `Target 2` (pos) and `Acceptance` only when set. `% from entry` is `pctFrom(entry, price)` on every priced row except Entry and Order.
- **Resting-stop line** `Move your resting stop to <working stop>`: only on `ACTIVE`/`PARTIAL`, and only when the Working stop row shows. `risk_stop` null therefore drops both (edge case).
- **R:R line** `R:R 2.18 · risk 2.49 / reward 5.42 per share`; with risk or reward unknown it is just `R:R 2.18`; with no R:R it is omitted. `riskPerShare` comes from the store's TD4 computed (original stop).
- **Gap note** `A gap through the trigger fills at the open, not at entry.` shows exactly when the Trigger row shows.
- **Position rows**, each hidden when its value is null (a legacy record without detail therefore shows only what its row carries): `Shares` (`Open shares` on PARTIAL), `Deployed`, `$ at risk` (subline `open shares, at original stop` on PARTIAL), `Sizing mode`, `Gap risk (p90)` (+ the `fragile` chip), `TP1 closes`, `Break-even at` (`60% of TP1`), `Trail` (`1.5 × ATR`), `Expires on`, `Time exit on`, `Hold cap` (`<n> bars`). The snapshot sentence shows only when `sizingMode` is null.
- **Outcome card:** Next block (`sb-if-it-gets-there`) on `open` and `pending` only; `Exit legs` on `closed` with one or more legs (single leg -> one row); every group keeps the timeline. A leg without an exit price is listed with `—` in Exit, R and Reason (TD3's average skips it; it is never hidden here). Leg R is tinted by `outcomeTone`, so a scratch leg inside ±0.1R is untinted.
- **Three device classes** (`docs/claude/ui-design.md` § Device classes, § Checklist): the cards hold no controls, so there is no touch target to size; they are not paged data tables (tiny key/value tables, § Tables and pagers: not paged). Every card is the same markup on phone (< 640), tablet (640-1023) and desktop (>= 1024): `min-width: 0` on the host and `overflow-wrap`-safe cells let it shrink to its grid cell, and each `table` sits in a `div.table-scroll` (`overflow-x: auto`) so a narrow phone cell scrolls the table inside its own box, never the page. Columns per class come from the TD11 grid, and the two-column `dl` (cell >= 640 px) is added by TD11; nothing here queries the viewport.

- [ ] **Step 1: Write the failing Plan card spec**

Create `frontend/src/app/workspaces/trades/plan-card.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  GAP_NOTE,
  PlanCard,
  PlanFigures,
  gapNoteApplies,
  planRows,
  restingStopLine,
  rrLine,
} from './plan-card';
import { PAPER_LINE } from './why/levels-block';

/** SPCX-shaped figures (spec § 3): a PARTIAL long whose working stop has
 *  moved above entry after TP1. Risk 142.01 - 139.52 = 2.49, reward
 *  147.43 - 142.01 = 5.42. */
const SPCX: PlanFigures = {
  direction: 'bullish',
  status: 'PARTIAL',
  entryType: 'stop_entry',
  trigger: 142.2,
  entry: 142.01,
  riskStop: 139.52,
  stopLoss: 145.62,
  workingStop: 145.62,
  target1: 147.43,
  target2: 150,
  acceptance: null,
  riskReward: 2.18,
  riskPerShare: 2.49,
  rewardPerShare: 5.42,
};

function figures(overrides: Partial<PlanFigures> = {}): PlanFigures {
  return { ...SPCX, ...overrides };
}

describe('planRows', () => {
  it('lists the levels in reading order, with the working stop under the original stop', () => {
    expect(planRows(SPCX).map((row) => row.level)).toEqual([
      'Order', 'Trigger', 'Entry', 'Stop', 'Working stop', 'Target 1', 'Target 2',
    ]);
  });

  it('names the order side and type with its price', () => {
    expect(planRows(SPCX)[0]).toEqual({
      level: 'Order', price: null, pctFromEntry: null, tone: null, note: 'Buy stop 142.20',
    });
    expect(planRows(figures({ entryType: 'limit', direction: 'bearish' }))[0].note).toBe('Sell limit 142.20');
    expect(planRows(figures({ entryType: 'market', direction: 'bearish' }))[0].note).toBe('Market (short)');
    expect(planRows(figures({ entryType: null }))[0].note).toBe('—');
  });

  it('prices the order at the entry when there is no trigger', () => {
    expect(planRows(figures({ trigger: null }))[0].note).toBe('Buy stop 142.01');
  });

  it('shows the original risk stop tinted negative and the working stop untinted with "(was ...)"', () => {
    const rows = planRows(SPCX);
    const stop = rows.find((row) => row.level === 'Stop')!;
    const working = rows.find((row) => row.level === 'Working stop')!;
    expect(stop.price).toBe(139.52);
    expect(stop.tone).toBe('neg');
    expect(stop.pctFromEntry).toBeCloseTo(-1.7534, 3);
    expect(working).toMatchObject({ price: 145.62, tone: null, note: '(was 139.52)' });
    expect(working.pctFromEntry).toBeCloseTo(2.5421, 3);
  });

  it('tints the targets positive and measures them from entry', () => {
    const rows = planRows(SPCX);
    const t1 = rows.find((row) => row.level === 'Target 1')!;
    expect(t1.tone).toBe('pos');
    expect(t1.pctFromEntry).toBeCloseTo(3.8166, 3);
    expect(rows.find((row) => row.level === 'Target 2')!.tone).toBe('pos');
  });

  it('gives Entry no % from entry', () => {
    expect(planRows(SPCX).find((row) => row.level === 'Entry')).toEqual({
      level: 'Entry', price: 142.01, pctFromEntry: null, tone: null, note: null,
    });
  });

  it('falls back to stop_loss and drops the working-stop row when risk_stop is null', () => {
    const rows = planRows(figures({ riskStop: null }));
    expect(rows.find((row) => row.level === 'Stop')!.price).toBe(145.62);
    expect(rows.some((row) => row.level === 'Working stop')).toBe(false);
  });

  it('drops the working-stop row when the working stop equals the risk stop or is unknown', () => {
    expect(planRows(figures({ workingStop: 139.52 })).some((row) => row.level === 'Working stop')).toBe(false);
    expect(planRows(figures({ workingStop: null })).some((row) => row.level === 'Working stop')).toBe(false);
  });

  it('drops the Trigger row when the trigger equals entry or is unknown', () => {
    expect(planRows(figures({ trigger: 142.01 })).some((row) => row.level === 'Trigger')).toBe(false);
    expect(planRows(figures({ trigger: null })).some((row) => row.level === 'Trigger')).toBe(false);
  });

  it('shows Target 2 and Acceptance only when set', () => {
    const levels = planRows(figures({ target2: null, acceptance: 141.4 })).map((row) => row.level);
    expect(levels).not.toContain('Target 2');
    expect(levels.at(-1)).toBe('Acceptance');
  });
});

describe('restingStopLine', () => {
  it('tells an open position to move its resting stop', () => {
    expect(restingStopLine(SPCX)).toBe('Move your resting stop to 145.62');
    expect(restingStopLine(figures({ status: 'ACTIVE' }))).toBe('Move your resting stop to 145.62');
  });

  it('says nothing on a closed or pending trade', () => {
    expect(restingStopLine(figures({ status: 'CLOSED' }))).toBeNull();
    expect(restingStopLine(figures({ status: 'PENDING' }))).toBeNull();
  });

  it('says nothing when there is no distinct working stop or no risk stop', () => {
    expect(restingStopLine(figures({ workingStop: 139.52 }))).toBeNull();
    expect(restingStopLine(figures({ riskStop: null }))).toBeNull();
  });
});

describe('rrLine and gapNoteApplies', () => {
  it('prints R:R with risk and reward per share', () => {
    expect(rrLine(SPCX)).toBe('R:R 2.18 · risk 2.49 / reward 5.42 per share');
  });

  it('prints R:R alone when risk or reward is unknown, and nothing without R:R', () => {
    expect(rrLine(figures({ riskPerShare: null }))).toBe('R:R 2.18');
    expect(rrLine(figures({ riskReward: null }))).toBeNull();
  });

  it('applies the gap note exactly when the trigger differs from entry', () => {
    expect(gapNoteApplies(SPCX)).toBe(true);
    expect(gapNoteApplies(figures({ trigger: 142.01 }))).toBe(false);
    expect(gapNoteApplies(figures({ trigger: null }))).toBe(false);
  });
});

function mount(f: PlanFigures): ComponentFixture<PlanCard> {
  const fixture = TestBed.createComponent(PlanCard);
  fixture.componentRef.setInput('figures', f);
  fixture.detectChanges();
  return fixture;
}

function squash(el: Element | null | undefined): string {
  return (el?.textContent ?? '').replace(/\s+/g, ' ').trim();
}

function row(fixture: ComponentFixture<PlanCard>, level: string): Element {
  return (fixture.nativeElement as HTMLElement).querySelector(`tr[data-level="${level}"]`)!;
}

function cells(fixture: ComponentFixture<PlanCard>, level: string): string[] {
  return [...row(fixture, level).children].map((cell) => squash(cell));
}

describe('PlanCard', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('renders one Plan table with level, price and % from entry', () => {
    const f = mount(SPCX);
    const el = f.nativeElement as HTMLElement;
    expect(squash(el.querySelector('h2'))).toBe('Plan');
    expect(el.querySelectorAll('table.levels tbody tr')).toHaveLength(7);
    expect(cells(f, 'Order')).toEqual(['Order', 'Buy stop 142.20', '']);
    expect(cells(f, 'Trigger')).toEqual(['Trigger', '142.20', '+0.13%']);
    expect(cells(f, 'Entry')).toEqual(['Entry', '142.01', '']);
    expect(cells(f, 'Target 1')).toEqual(['Target 1', '147.43', '+3.82%']);
  });

  it('shows "Working stop 145.62 (was 139.52)" after the original stop', () => {
    const f = mount(SPCX);
    expect(cells(f, 'Stop').slice(0, 2)).toEqual(['Stop', '139.52']);
    expect(cells(f, 'Stop')[2]).toContain('1.75%');
    expect(cells(f, 'Working stop')).toEqual(['Working stop', '145.62 (was 139.52)', '+2.54%']);
  });

  it('tints the stop negative, the targets positive and the working stop not at all', () => {
    const f = mount(SPCX);
    expect(row(f, 'Stop').querySelector('td.price')!.classList).toContain('neg');
    expect(row(f, 'Target 1').querySelector('td.price')!.classList).toContain('pos');
    const working = row(f, 'Working stop').querySelector('td.price')!.classList;
    expect(working).not.toContain('pos');
    expect(working).not.toContain('neg');
  });

  it('highlights the resting-stop move on an open position', () => {
    const el = mount(SPCX).nativeElement as HTMLElement;
    expect(squash(el.querySelector('.resting-stop'))).toBe('Move your resting stop to 145.62');
  });

  it('shows no resting-stop line on a closed trade', () => {
    const el = mount(figures({ status: 'CLOSED' })).nativeElement as HTMLElement;
    expect(el.querySelector('.resting-stop')).toBeNull();
  });

  it('prints the R:R line, the gap note and the paper footnote', () => {
    const el = mount(SPCX).nativeElement as HTMLElement;
    expect(squash(el.querySelector('.rr-line'))).toBe('R:R 2.18 · risk 2.49 / reward 5.42 per share');
    expect(squash(el.querySelector('.gap-line'))).toBe(GAP_NOTE);
    expect(GAP_NOTE).toBe('A gap through the trigger fills at the open, not at entry.');
    expect(squash(el.querySelector('.paper-line'))).toBe(PAPER_LINE);
  });

  it('omits the gap note and the Trigger row when the trigger is the entry', () => {
    const el = mount(figures({ trigger: 142.01 })).nativeElement as HTMLElement;
    expect(el.querySelector('.gap-line')).toBeNull();
    expect(el.querySelector('tr[data-level="Trigger"]')).toBeNull();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/plan-card.spec.ts
```

Expected: FAIL — the build cannot resolve `./plan-card`.

- [ ] **Step 3: Write `plan-card.ts`**

Create `frontend/src/app/workspaces/trades/plan-card.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { ABSENT, num, pct } from '../../ui/format';
import { Panel } from '../../ui/layout';
import { Tone, orderWording, pctFrom } from './trade-figures';
import { PAPER_LINE } from './why/levels-block';

/** Everything the Plan card prints, flattened from the trade row, its detail
 *  and the store's TD4 computeds by the page (TD10). */
export interface PlanFigures {
  direction: string | null;
  status: string;
  entryType: string | null;
  trigger: number | null;
  entry: number | null;
  /** The plan's original stop (`risk_stop`); null on a row from before v166. */
  riskStop: number | null;
  /** The row's live stop: the working (trailing) stop once PARTIAL. */
  stopLoss: number | null;
  /** `detail.working_stop`. */
  workingStop: number | null;
  target1: number | null;
  target2: number | null;
  acceptance: number | null;
  riskReward: number | null;
  riskPerShare: number | null;
  rewardPerShare: number | null;
}

export interface PlanRow {
  level: string;
  price: number | null;
  pctFromEntry: number | null;
  tone: Tone;
  /** The Order row's wording, or the Working stop's "(was ...)". */
  note: string | null;
}

export const GAP_NOTE = 'A gap through the trigger fills at the open, not at entry.';

const OPEN_STATUSES = new Set(['ACTIVE', 'PARTIAL']);
const SAME_PRICE = 1e-9;

function differs(a: number | null, b: number | null): boolean {
  return a !== null && b !== null && Math.abs(a - b) > SAME_PRICE;
}

function levelRow(level: string, price: number | null, entry: number | null, tone: Tone): PlanRow {
  return { level, price, pctFromEntry: pctFrom(entry, price), tone, note: null };
}

function optionalRow(level: string, price: number | null, entry: number | null, tone: Tone): PlanRow[] {
  return price === null ? [] : [levelRow(level, price, entry, tone)];
}

function hasWorkingStop(f: PlanFigures): boolean {
  return differs(f.workingStop, f.riskStop);
}

function workingStopRows(f: PlanFigures): PlanRow[] {
  if (!hasWorkingStop(f)) return [];
  // Untinted on purpose: after TP1 the working stop sits above entry for a
  // long, so the stop's red would say "loss" about a level that locks a gain.
  return [{ ...levelRow('Working stop', f.workingStop, f.entry, null), note: `(was ${num(f.riskStop)})` }];
}

/** A trigger away from entry means a gap through it fills at the open. */
export function gapNoteApplies(f: PlanFigures): boolean {
  return differs(f.trigger, f.entry);
}

/**
 * The Plan card's table (spec § 3): Order, Trigger (when it differs from
 * entry), Entry, Stop (the ORIGINAL risk stop), Working stop (when it has
 * moved), Target 1, Target 2 and Acceptance (when set).
 */
export function planRows(f: PlanFigures): PlanRow[] {
  const order: PlanRow = {
    level: 'Order',
    price: null,
    pctFromEntry: null,
    tone: null,
    note: orderWording(f.entryType, f.direction, f.trigger ?? f.entry),
  };
  const trigger = gapNoteApplies(f) ? [levelRow('Trigger', f.trigger, f.entry, null)] : [];
  return [
    order,
    ...trigger,
    { level: 'Entry', price: f.entry, pctFromEntry: null, tone: null, note: null },
    levelRow('Stop', f.riskStop ?? f.stopLoss, f.entry, 'neg'),
    ...workingStopRows(f),
    levelRow('Target 1', f.target1, f.entry, 'pos'),
    ...optionalRow('Target 2', f.target2, f.entry, 'pos'),
    ...optionalRow('Acceptance', f.acceptance, f.entry, null),
  ];
}

/** The follow-up cue a resting order needs once the stop has moved (panel,
 *  veteran-trader BLOCKING): only while the position is open. */
export function restingStopLine(f: PlanFigures): string | null {
  if (!OPEN_STATUSES.has(f.status.trim().toUpperCase()) || !hasWorkingStop(f)) return null;
  return `Move your resting stop to ${num(f.workingStop)}`;
}

export function rrLine(f: PlanFigures): string | null {
  if (f.riskReward === null) return null;
  const head = `R:R ${num(f.riskReward)}`;
  if (f.riskPerShare === null || f.rewardPerShare === null) return head;
  return `${head} · risk ${num(f.riskPerShare)} / reward ${num(f.rewardPerShare)} per share`;
}

/** The Overview tab's Plan card: the levels once, as they would be entered.
 *  Replaces `LevelsBlock` on the trade page (amendment 4); the plan page
 *  keeps `LevelsBlock`. */
@Component({
  selector: 'sb-trade-plan-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <sb-panel heading="Plan">
      <div class="table-scroll">
      <table class="levels">
        <thead>
          <tr><th scope="col">Level</th><th scope="col">Price</th><th scope="col">From entry</th></tr>
        </thead>
        <tbody>
          @for (row of rows(); track row.level) {
            <tr [attr.data-level]="row.level">
              <th scope="row">{{ row.level }}</th>
              <td class="price num" [class.pos]="row.tone === 'pos'" [class.neg]="row.tone === 'neg'">
                @if (row.price === null) {
                  {{ row.note ?? absent }}
                } @else {
                  {{ fmt(row.price) }} @if (row.note) { <span class="was muted">{{ row.note }}</span> }
                }
              </td>
              <td class="from num">{{ row.pctFromEntry === null ? '' : fmtPct(row.pctFromEntry) }}</td>
            </tr>
          }
        </tbody>
      </table>
      </div>
      @if (restingStop(); as line) {
        <p class="resting-stop" role="note">{{ line }}</p>
      }
      @if (rr(); as line) {
        <p class="rr-line num">{{ line }}</p>
      }
      @if (showGapNote()) {
        <p class="gap-line muted">{{ gapNote }}</p>
      }
      <p class="paper-line muted">{{ paperLine }}</p>
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    /* docs/claude/ui-design.md: a table never scrolls the page sideways. */
    .table-scroll { overflow-x: auto; }
    .levels { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    .levels th, .levels td { padding: var(--space-4) 0; font-weight: 400; text-align: right; }
    .levels th[scope='row'] { color: var(--text-secondary); text-align: left; }
    .levels thead th { color: var(--text-muted); font-size: var(--text-chip); }
    .levels thead th:first-child { text-align: left; }
    .levels td.from { padding-left: var(--space-10); }
    .was { margin-left: var(--space-6); }
    .resting-stop {
      margin-top: var(--space-10);
      padding: var(--space-6) var(--space-10);
      border-left: 2px solid var(--warn);
      background: var(--warn-soft);
      color: var(--text);
      font-size: var(--text-table);
      font-weight: 600;
    }
    .rr-line, .gap-line, .paper-line {
      margin-top: var(--space-10);
      font-size: var(--text-table);
      line-height: 1.6;
    }
  `,
})
export class PlanCard {
  readonly figures = input.required<PlanFigures>();

  protected readonly rows = computed(() => planRows(this.figures()));
  protected readonly restingStop = computed(() => restingStopLine(this.figures()));
  protected readonly rr = computed(() => rrLine(this.figures()));
  protected readonly showGapNote = computed(() => gapNoteApplies(this.figures()));

  protected readonly gapNote = GAP_NOTE;
  protected readonly paperLine = PAPER_LINE;
  protected readonly absent = ABSENT;
  protected readonly fmt = num;
  protected readonly fmtPct = pct;
}
```

Keep `{{ fmt(row.price) }}` and its `@if (row.note)` block on one line, separated by a single space: the Working stop cell must read `145.62 (was 139.52)` once whitespace is collapsed. If the DOM case gets `145.62(was 139.52)`, the space was lost in the template, not in `planRows`.

- [ ] **Step 4: Run the Plan card spec and the UI gates**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/plan-card.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts
```

Expected: all green. A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once. The Stop row's `% from entry` is asserted with `toContain('1.75%')` because `pct()` owns the minus sign; do not change `pct`.

- [ ] **Step 5: Write the failing Position card spec**

Create `frontend/src/app/workspaces/trades/position-card.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { date } from '../../ui/format';
import {
  PARTIAL_RISK_SUB,
  PositionCard,
  PositionFigures,
  SNAPSHOT_SENTENCE,
  positionRows,
} from './position-card';

/** SPCX-shaped: 7 shares x 2.49 risk per share = $17.43 at risk. */
const FULL: PositionFigures = {
  status: 'ACTIVE',
  shares: 7,
  positionValue: 994.07,
  dollarAtRisk: 17.43,
  sizingMode: 'risk_pct',
  gapP90Pct: 1.234,
  gapFragile: true,
  tp1Pct: 50,
  breakevenTriggerPct: 60,
  trailAtrMult: 1.5,
  expiresOn: '2026-10-20',
  timeExitOn: '2026-11-02',
  holdCapBars: 20,
};

const EMPTY: PositionFigures = {
  status: 'CLOSED',
  shares: null,
  positionValue: null,
  dollarAtRisk: null,
  sizingMode: null,
  gapP90Pct: null,
  gapFragile: null,
  tp1Pct: null,
  breakevenTriggerPct: null,
  trailAtrMult: null,
  expiresOn: null,
  timeExitOn: null,
  holdCapBars: null,
};

describe('positionRows', () => {
  it('lists every sizing and exit-rule row when the record has them', () => {
    expect(positionRows(FULL).map((row) => [row.label, row.value])).toEqual([
      ['Shares', '7'],
      ['Deployed', '994.07'],
      ['$ at risk', '17.43'],
      ['Sizing mode', 'risk_pct'],
      ['Gap risk (p90)', '1.23%'],
      ['TP1 closes', '50%'],
      ['Break-even at', '60% of TP1'],
      ['Trail', '1.5 × ATR'],
      ['Expires on', date('2026-10-20')],
      ['Time exit on', date('2026-11-02')],
      ['Hold cap', '20 bars'],
    ]);
  });

  it('flags a fragile gap risk on its row only', () => {
    expect(positionRows(FULL).filter((row) => row.fragile).map((row) => row.label)).toEqual(['Gap risk (p90)']);
    expect(positionRows({ ...FULL, gapFragile: false }).some((row) => row.fragile)).toBe(false);
  });

  it('labels shares and $ at risk for the open runner on PARTIAL', () => {
    const rows = positionRows({ ...FULL, status: 'PARTIAL', shares: 3, dollarAtRisk: 7.47 });
    expect(rows[0]).toEqual({ label: 'Open shares', value: '3', sub: null, fragile: false });
    expect(rows[2]).toEqual({ label: '$ at risk', value: '7.47', sub: PARTIAL_RISK_SUB, fragile: false });
    expect(PARTIAL_RISK_SUB).toBe('open shares, at original stop');
  });

  it('hides each row whose value is null', () => {
    expect(positionRows(EMPTY)).toEqual([]);
    expect(positionRows({ ...EMPTY, shares: 10, holdCapBars: 15 }).map((row) => row.label))
      .toEqual(['Shares', 'Hold cap']);
  });

  it('prints the TP1 and break-even fractions unsigned', () => {
    const values = positionRows(FULL).map((row) => row.value);
    expect(values).not.toContain('+50%');
    expect(values).toContain('50%');
  });
});

function mount(f: PositionFigures): ComponentFixture<PositionCard> {
  const fixture = TestBed.createComponent(PositionCard);
  fixture.componentRef.setInput('figures', f);
  fixture.detectChanges();
  return fixture;
}

function squash(el: Element | null | undefined): string {
  return (el?.textContent ?? '').replace(/\s+/g, ' ').trim();
}

describe('PositionCard', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('renders the Position panel with one row per known value', () => {
    const el = mount(FULL).nativeElement as HTMLElement;
    expect(squash(el.querySelector('h2'))).toBe('Position');
    expect(el.querySelectorAll('dl > div')).toHaveLength(11);
    expect(squash(el.querySelector('div[data-row="$ at risk"] dd'))).toBe('17.43');
  });

  it('shows the fragile chip beside the gap risk', () => {
    const el = mount(FULL).nativeElement as HTMLElement;
    expect(el.querySelector('div[data-row="Gap risk (p90)"] sb-chip')).not.toBeNull();
  });

  it('prints the PARTIAL basis under $ at risk', () => {
    const el = mount({ ...FULL, status: 'PARTIAL' }).nativeElement as HTMLElement;
    expect(squash(el.querySelector('div[data-row="$ at risk"] dt'))).toBe('$ at risk open shares, at original stop');
  });

  it('shows the snapshot sentence only when the sizing mode is unknown', () => {
    expect((mount(FULL).nativeElement as HTMLElement).querySelector('.section-help')).toBeNull();
    const el = mount({ ...FULL, sizingMode: null }).nativeElement as HTMLElement;
    expect(squash(el.querySelector('.section-help'))).toBe(SNAPSHOT_SENTENCE);
    expect(SNAPSHOT_SENTENCE).toBe(
      'Position size is snapshotted when the trade opens. A trade with no sizing snapshot was logged before that feature existed.',
    );
  });
});
```

- [ ] **Step 6: Run it to verify it fails**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/position-card.spec.ts
```

Expected: FAIL — the build cannot resolve `./position-card`.

- [ ] **Step 7: Write `position-card.ts`**

Create `frontend/src/app/workspaces/trades/position-card.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { Chip } from '../../ui/chip';
import { date, num, share, text } from '../../ui/format';
import { Panel } from '../../ui/layout';

/** Everything the Position card prints, flattened by the page (TD10). */
export interface PositionFigures {
  status: string;
  /** On PARTIAL the API sends the OPEN share count here (amendment 2). */
  shares: number | null;
  positionValue: number | null;
  /** Store TD4: shares x |entry - (risk_stop ?? stop_loss)|. */
  dollarAtRisk: number | null;
  sizingMode: string | null;
  gapP90Pct: number | null;
  gapFragile: boolean | null;
  tp1Pct: number | null;
  breakevenTriggerPct: number | null;
  trailAtrMult: number | null;
  expiresOn: string | null;
  timeExitOn: string | null;
  holdCapBars: number | null;
}

export interface PositionRow {
  label: string;
  value: string;
  sub: string | null;
  fragile: boolean;
}

export const SNAPSHOT_SENTENCE =
  'Position size is snapshotted when the trade opens. A trade with no sizing snapshot was logged before that feature existed.';

/** Amendment 2: on PARTIAL, `shares` is the runner and the risk is measured
 *  to the original stop, so the figure says so. */
export const PARTIAL_RISK_SUB = 'open shares, at original stop';

function isPartial(f: PositionFigures): boolean {
  return f.status.trim().toUpperCase() === 'PARTIAL';
}

function shown(
  label: string,
  raw: unknown,
  value: () => string,
  sub: string | null = null,
  fragile = false,
): PositionRow | null {
  return raw === null || raw === undefined ? null : { label, value: value(), sub, fragile };
}

type RowSpec = (f: PositionFigures) => PositionRow | null;

/* One entry per row, in reading order. A row whose source is null is hidden
 * (spec § 3), which is also what makes a legacy record without detail show
 * only the figures its row carries. */
const ROWS: readonly RowSpec[] = [
  (f) => shown(isPartial(f) ? 'Open shares' : 'Shares', f.shares, () => num(f.shares, 0)),
  (f) => shown('Deployed', f.positionValue, () => num(f.positionValue)),
  (f) => shown('$ at risk', f.dollarAtRisk, () => num(f.dollarAtRisk), isPartial(f) ? PARTIAL_RISK_SUB : null),
  (f) => shown('Sizing mode', f.sizingMode, () => text(f.sizingMode)),
  (f) => shown('Gap risk (p90)', f.gapP90Pct, () => share(f.gapP90Pct, 2), null, f.gapFragile === true),
  (f) => shown('TP1 closes', f.tp1Pct, () => share(f.tp1Pct)),
  (f) => shown('Break-even at', f.breakevenTriggerPct, () => `${share(f.breakevenTriggerPct)} of TP1`),
  (f) => shown('Trail', f.trailAtrMult, () => `${num(f.trailAtrMult, 1)} × ATR`),
  (f) => shown('Expires on', f.expiresOn, () => date(f.expiresOn)),
  (f) => shown('Time exit on', f.timeExitOn, () => date(f.timeExitOn)),
  (f) => shown('Hold cap', f.holdCapBars, () => `${f.holdCapBars} bars`),
];

export function positionRows(f: PositionFigures): PositionRow[] {
  return ROWS.flatMap((spec) => {
    const row = spec(f);
    return row === null ? [] : [row];
  });
}

/** The Overview tab's Position card. Replaces `SizingPanel` on the trade
 *  page because that one always prints the snapshot sentence (amendment 4);
 *  the plan page keeps `SizingPanel`. */
@Component({
  selector: 'sb-trade-position-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Chip],
  template: `
    <sb-panel heading="Position">
      @if (figures().sizingMode === null) {
        <p class="section-help">{{ snapshot }}</p>
      }
      <dl>
        @for (row of rows(); track row.label) {
          <div [attr.data-row]="row.label">
            <dt>{{ row.label }} @if (row.sub) { <span class="row-sub muted">{{ row.sub }}</span> }</dt>
            <dd class="num">
              <span>{{ row.value }}</span>
              @if (row.fragile) {
                <sb-chip label="fragile" tone="warn" [caps]="false"
                  title="The stop sits inside 90th-percentile gap noise: an overnight gap can jump it." />
              }
            </dd>
          </div>
        }
      </dl>
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    dl { display: grid; gap: var(--space-6); margin: 0; }
    dl > div { display: flex; justify-content: space-between; align-items: baseline; gap: var(--space-10); }
    dt { color: var(--text-secondary); font-size: var(--text-table); }
    dd {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      align-items: center;
      gap: var(--space-6);
      margin: 0;
      color: var(--text);
      font-size: var(--text-table);
      text-align: right;
    }
    .row-sub { display: block; font-size: var(--text-chip); }
  `,
})
export class PositionCard {
  readonly figures = input.required<PositionFigures>();

  protected readonly rows = computed(() => positionRows(this.figures()));
  protected readonly snapshot = SNAPSHOT_SENTENCE;
}
```

- [ ] **Step 8: Run the Position card spec and the UI gates**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/position-card.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts
```

Expected: all green. If the `$ at risk` `dt` reads `$ at riskopen shares, at original stop`, the single space between `{{ row.label }}` and the `@if` on the same line was lost: restore it in the template rather than changing the assertion.

- [ ] **Step 9: Write the failing Outcome card spec**

Create `frontend/src/app/workspaces/trades/outcome-card.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Leg, StatusEvent } from '../../stores/trade-detail.store';
import { OutcomeCard, legRows } from './outcome-card';
import { StatusGroup } from './trade-figures';

/** SPCX's two legs (spec § 1): 0.5 @ 147.54 +2.23R TP1, 0.5 @ 145.56 +1.43R
 *  runner at breakeven. */
const SPCX_LEGS: Leg[] = [
  { fraction: 0.5, exitPrice: 147.54, r: 2.23, reason: 'tp1' },
  { fraction: 0.5, exitPrice: 145.56, r: 1.43, reason: 'tp1_runner_be' },
];

const TIMELINE: StatusEvent[] = [
  { status: 'CREATED', reason: 'scan', at: '2026-10-01T13:30:00Z' },
  { status: 'ACTIVE', reason: 'trigger filled', at: '2026-10-02T14:05:00Z' },
];

describe('legRows', () => {
  it('maps each leg to fraction, exit, R, tint and reason label', () => {
    expect(legRows(SPCX_LEGS)).toEqual([
      { share: '50%', exit: '147.54', r: '+2.23R', tone: 'pos', reason: 'TP1' },
      { share: '50%', exit: '145.56', r: '+1.43R', tone: 'pos', reason: 'Runner at breakeven' },
    ]);
  });

  it('lists a leg with no exit price with dashes rather than hiding it', () => {
    expect(legRows([{ fraction: 0.5, exitPrice: null, r: null, reason: null }])).toEqual([
      { share: '50%', exit: '—', r: '—', tone: null, reason: '—' },
    ]);
  });

  it('leaves a scratch leg inside ±0.1R untinted and shows an unknown reason raw', () => {
    expect(legRows([{ fraction: 1, exitPrice: 100.1, r: -0.05, reason: 'manual close' }])[0])
      .toEqual({ share: '100%', exit: '100.10', r: '-0.05R', tone: null, reason: 'manual close' });
  });

  it('prints a dash for a leg with no fraction', () => {
    expect(legRows([{ fraction: null, exitPrice: 101, r: 0.4, reason: 'stop' }])[0].share).toBe('—');
  });
});

interface Inputs {
  group: StatusGroup;
  direction?: string | null;
  target2?: number | null;
  stopLoss?: number | null;
  legs?: readonly Leg[];
  timeline?: readonly StatusEvent[];
}

function mount(inputs: Inputs): ComponentFixture<OutcomeCard> {
  const fixture = TestBed.createComponent(OutcomeCard);
  for (const [name, value] of Object.entries(inputs)) fixture.componentRef.setInput(name, value);
  fixture.detectChanges();
  return fixture;
}

function el(fixture: ComponentFixture<OutcomeCard>): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function legCells(fixture: ComponentFixture<OutcomeCard>): string[][] {
  return [...el(fixture).querySelectorAll('table.legs tbody tr')].map((tr) =>
    [...tr.children].map((cell) => (cell.textContent ?? '').replace(/\s+/g, ' ').trim()));
}

describe('OutcomeCard', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('shows the Next block and the timeline on an open trade', () => {
    const f = mount({ group: 'open', direction: 'bullish', target2: 150, stopLoss: 145.62, legs: SPCX_LEGS, timeline: TIMELINE });
    const text = el(f).textContent ?? '';
    expect(el(f).querySelector('sb-if-it-gets-there')).not.toBeNull();
    expect(text).toContain('next stop 150.00');
    expect(text).toContain('145.62');
    expect(text).toContain('Timeline');
    expect(text).toContain('trigger filled');
    expect(el(f).querySelector('table.legs')).toBeNull();
  });

  it('shows the Next block on a pending plan', () => {
    const f = mount({ group: 'pending', direction: 'bearish', target2: null, stopLoss: 105, timeline: TIMELINE });
    expect(el(f).querySelector('sb-if-it-gets-there')).not.toBeNull();
    expect(el(f).textContent).toContain('no further level found');
  });

  it('shows the labelled exit legs above the timeline on a closed trade, and no Next block', () => {
    const f = mount({ group: 'closed', legs: SPCX_LEGS, timeline: TIMELINE });
    expect(el(f).querySelector('sb-if-it-gets-there')).toBeNull();
    expect(el(f).textContent).toContain('Exit legs');
    expect(legCells(f)).toEqual([
      ['50%', '147.54', '+2.23R', 'TP1'],
      ['50%', '145.56', '+1.43R', 'Runner at breakeven'],
    ]);
    const legs = el(f).querySelector('table.legs')!;
    const path = el(f).querySelector('sb-outcome-path')!;
    expect(legs.compareDocumentPosition(path) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("never prints the shared component's raw-reason Scale-out panel", () => {
    const f = mount({ group: 'closed', legs: SPCX_LEGS, timeline: TIMELINE });
    expect(el(f).textContent).not.toContain('Scale-out');
    expect(el(f).textContent).not.toContain('tp1_runner_be');
  });

  it('lists a leg without an exit price with dashes', () => {
    const f = mount({ group: 'closed', legs: [SPCX_LEGS[0], { fraction: 0.5, exitPrice: null, r: null, reason: null }] });
    expect(legCells(f)[1]).toEqual(['50%', '—', '—', '—']);
  });

  it('shows one leg row for a single-leg close', () => {
    const f = mount({ group: 'closed', legs: [{ fraction: 1, exitPrice: 98, r: -1, reason: 'stop' }] });
    expect(legCells(f)).toEqual([['100%', '98.00', '-1.00R', 'Stop']]);
  });

  it('tints a winning leg R and nothing else in the row', () => {
    const f = mount({ group: 'closed', legs: SPCX_LEGS });
    const cells = el(f).querySelectorAll('table.legs tbody tr:first-child td');
    expect(cells[2].classList).toContain('pos');
    expect(cells[1].classList).not.toContain('pos');
  });

  it('shows no legs table on a closed trade with no legs', () => {
    const f = mount({ group: 'closed', legs: [], timeline: TIMELINE });
    expect(el(f).querySelector('table.legs')).toBeNull();
    expect(el(f).textContent).toContain('Timeline');
  });

  it('shows only the timeline on a cancelled or expired plan', () => {
    const f = mount({ group: 'unfilled', legs: SPCX_LEGS, timeline: TIMELINE });
    expect(el(f).querySelector('sb-if-it-gets-there')).toBeNull();
    expect(el(f).querySelector('table.legs')).toBeNull();
    expect(el(f).textContent).toContain('Timeline');
  });
});
```

- [ ] **Step 10: Run it to verify it fails**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/outcome-card.spec.ts
```

Expected: FAIL — the build cannot resolve `./outcome-card`.

- [ ] **Step 11: Write `outcome-card.ts`**

Create `frontend/src/app/workspaces/trades/outcome-card.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { Leg, StatusEvent } from '../../stores/trade-detail.store';
import { ABSENT, num, rMultiple, share } from '../../ui/format';
import { Panel } from '../../ui/layout';
import { reasonLabel } from './exit-reasons';
import { StatusGroup, Tone, outcomeTone } from './trade-figures';
import { IfItGetsThere } from './why/if-it-gets-there';
import { OutcomePath } from './why/outcome-path';

export interface LegRow {
  share: string;
  exit: string;
  r: string;
  tone: Tone;
  reason: string;
}

/** One printed row per leg. A leg with no exit price stays listed with
 *  dashes (the runner still open, or a record that never stored the fill). */
export function legRows(legs: readonly Leg[]): LegRow[] {
  return legs.map((leg) => ({
    share: leg.fraction === null ? ABSENT : share(leg.fraction * 100),
    exit: num(leg.exitPrice),
    r: rMultiple(leg.r),
    tone: outcomeTone(leg.r),
    reason: reasonLabel(leg.reason) ?? ABSENT,
  }));
}

const NEXT_GROUPS: ReadonlySet<StatusGroup> = new Set<StatusGroup>(['open', 'pending']);

/**
 * The Overview tab's Outcome card (spec § 3): what happens next while the
 * trade is live or pending, how it ended once closed, and the timeline.
 *
 * `OutcomePath` is reused for its Timeline only and fed no legs: its own
 * Scale-out panel prints the raw reason text, and this card prints the
 * labelled legs instead (amendment 4).
 */
@Component({
  selector: 'sb-trade-outcome-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, IfItGetsThere, OutcomePath],
  template: `
    @if (showNext()) {
      <sb-if-it-gets-there [direction]="direction()" [target2]="target2()" [stopLoss]="stopLoss()" />
    }
    @if (showLegs()) {
      <sb-panel heading="Exit legs">
        <div class="table-scroll">
        <table class="legs">
          <thead>
            <tr>
              <th scope="col">Size</th><th scope="col">Exit</th><th scope="col">R</th><th scope="col">Reason</th>
            </tr>
          </thead>
          <tbody>
            @for (leg of rows(); track $index) {
              <tr>
                <td class="num">{{ leg.share }}</td>
                <td class="num">{{ leg.exit }}</td>
                <td class="num" [class.pos]="leg.tone === 'pos'" [class.neg]="leg.tone === 'neg'">{{ leg.r }}</td>
                <td class="reason">{{ leg.reason }}</td>
              </tr>
            }
          </tbody>
        </table>
        </div>
      </sb-panel>
    }
    <sb-outcome-path [legs]="noLegs" [timeline]="events()" />
  `,
  styles: `
    :host {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      align-content: start;
      gap: var(--section-gap);
      min-width: 0;
    }
    /* docs/claude/ui-design.md: a table never scrolls the page sideways. */
    .table-scroll { overflow-x: auto; }
    .legs { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    .legs th, .legs td { padding: var(--space-4) 0; font-weight: 400; text-align: right; }
    .legs thead th { color: var(--text-muted); font-size: var(--text-chip); }
    .legs th:last-child, .legs td.reason {
      padding-left: var(--space-10);
      color: var(--text-secondary);
      text-align: left;
    }
  `,
})
export class OutcomeCard {
  readonly group = input.required<StatusGroup>();
  readonly direction = input<string | null>(null);
  readonly target2 = input<number | null>(null);
  /** The stop that applies now: the working stop on PARTIAL. */
  readonly stopLoss = input<number | null>(null);
  readonly legs = input<readonly Leg[]>([]);
  readonly timeline = input<readonly StatusEvent[]>([]);

  protected readonly showNext = computed(() => NEXT_GROUPS.has(this.group()));
  protected readonly showLegs = computed(() => this.group() === 'closed' && this.legs().length > 0);
  protected readonly rows = computed(() => legRows(this.legs()));
  /** `OutcomePath.timeline` is typed as a mutable `StatusEvent[]`. */
  protected readonly events = computed(() => [...this.timeline()]);
  protected readonly noLegs: Leg[] = [];
}
```

- [ ] **Step 12: Run all three card specs, the shared `why/` specs and the UI gates**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/plan-card.spec.ts --include src/app/workspaces/trades/position-card.spec.ts --include src/app/workspaces/trades/outcome-card.spec.ts --include src/app/workspaces/trades/why/if-it-gets-there.spec.ts --include src/app/workspaces/trades/why/outcome-path.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts
```

Expected: all green (the `why/` specs are unchanged and stay green). A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once.

Confirm no shared file was touched:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation status --short -- frontend/src/app/workspaces/trades/why frontend/src/app/ui
```

Expected: no output.

- [ ] **Step 13: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation add frontend/src/app/workspaces/trades/plan-card.ts frontend/src/app/workspaces/trades/plan-card.spec.ts frontend/src/app/workspaces/trades/position-card.ts frontend/src/app/workspaces/trades/position-card.spec.ts frontend/src/app/workspaces/trades/outcome-card.ts frontend/src/app/workspaces/trades/outcome-card.spec.ts
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation commit -m "feat(ui): trade page Plan, Position and Outcome cards -- working stop, resting-stop cue, dollars at risk, labelled exit legs"
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation status --short
```

Expected: the status command lists no file this task touched.

