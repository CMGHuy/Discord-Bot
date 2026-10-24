# v189 — Book integrity and partial-trade truth: Implementation Plan, part 7 of 7 — frontend (part 7b holds the clear replies, docs and release)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier. **Never read this part whole**: `grep -n "^### Task V189-22:" -A 290 <this file>`. V189-25..V189-27 continue in part 7b (`2026-10-23-v189-book-integrity-partial-truth_7b-clear-replies-and-release.md`).

**Spec:** [2026-10-23-v189-book-integrity-partial-truth-design.md](../specs/2026-10-23-v189-book-integrity-partial-truth-design.md) — D5 (B1, B3, B4, B5), D6, D4 A6/A7 (the confirmations), § Testing (frontend banked amount via the store and cell specs); `## Corrections from the code brief` 2 and 10 win over earlier sections.
**Index:** [2026-10-23-v189-book-integrity-partial-truth_0-index.md](2026-10-23-v189-book-integrity-partial-truth_0-index.md) — `## Global Constraints`, `## Spec clarifications` 7, 9, 12 and 13, `## Contracts` § Display and § Account reset, `## Parallelisation`, the task ledger.
**Worktree:** `.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth`. Every path below is relative to it; every command runs from it. Agent shells drop variables between calls, so `cd "$WT"` means `WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth; cd "$WT" && ...` in the same command.

**Consumed from earlier parts (re-read each as merged with `git grep -n` before use):**

- V189-2: `tests/analytics/golden_partial_trade.json` (shape in the index § Golden fixture); `metrics.LABEL_BASIS_SINCE` and `tests/analytics/test_net_outcome.py::test_constants`.
- V189-14 (part 4b): `POST /api/v1/trades/clear-open` → 200 `{"removed": n, "ended": [{"plan_id", "ticker", "status_before", "status_after"}, ...], "notice": str}` (`notice` is `""` when nothing ended); a `LockTimeout` → 409 `conflict`.
- V189-16 (part 5): `POST /api/v1/trades/clear-history` forces on `?force=true` or JSON `{"force": true}`; 200 `{"removed", "removed_plans", "archive", "throttle": {"multiplier", "paused"}, "kill_switch", "notice"}`; 409 `kill_switch_tripped` (message = `account_reset.REFUSED_TEXT`); 500 `archive_failed`. `/trades-clear-history` gains a `force` option.
- V189-18: trades rows carry `entry_shares` (original size) and `banked_contribution_r`; an open PARTIAL's `r_multiple` is the blended figure once priced.
- V189-19: dashboard JSON `heat_enforced_pct`, `risk_of_loss_pct`, `risk_of_loss_amount`, `risk_cap_pct` (`risk_used_pct` is gone); Risk page position rows `risk_of_loss_amount`, `risk_of_loss_pct` (both `None` for a PENDING placeholder).
- V189-20: analytics performance `scratch_n`, `unscored_n`, `label_basis_since` (read the merged `api_v1/analytics.py` for the exact key placement before V189-24).

**Frontend conventions for every task here.** Run `cd frontend && npx ng test --watch=false --include <spec>` while iterating (Vitest 4 through `@angular/build:unit-test`), then the whole `npx ng test --watch=false` and `npm run lint` before the commit. New `TradeRow` / `RiskPosition` / `AnalyticsPerformance` fields are optional (nine spec files build full literals). Every UI change is checked at 390, 768 and 1440 (`docs/claude/ui-design.md` § Checklist): the layout audit runs once for the whole of part 7 and 7b, in V189-25's last step (part 7b), against a local replica, and must exit 0. Frontend commits never carry backend files.

**Decisions this part writes down (within the spec, not new scope):**

1. **The banked clause reads the API's contribution.** The PlanCell tooltip and the Trade-detail Banked tile print `banked +1.00R (TP1 +2.00R on 50%)` from `banked_contribution_r` and `banked_r`; neither multiplies on the client. When `banked_contribution_r` is absent (an old payload) the clause drops the `banked +x.xxR` head and keeps `TP1 +2.00R on 50%`, never the TP1 R alone as "banked".
2. **Risk of loss on Trade detail mirrors `heat.risk_of_loss_amount`** with the row's own numbers: `open_shares` (falling back to `shares`) × the loss-side distance from `entry` to the working stop (`detail.working_stop`, falling back to `stop_loss`), floored at 0. "Open profit to stop" is the same open shares × the distance from the live quote to that stop on the profit side, floored at 0, `null` without a finite `current_price`.
3. **No Dashboard risk card** (index clarification 12): V189-23 changes the Dashboard model and store only; the two figures sit side by side on the Risk page.
4. **The force retry is never automatic** (index clarification 13): a 409 shows the refusal and a button; the button opens its own confirmation, and only its confirm sends `{"force": true}`.

# Phase G — Frontend, docs and release

### Task V189-21: Frontend: banked amount on entry shares; banked label; golden loader

**Model:** sonnet — a parameter rename at two call sites, one new input and one tooltip clause, pinned by a fixture-driven spec; no state, no layout.

**Spec:** D5 B1 (`bankedLegAmount` takes `entry_shares`; `models.ts` adds the field), B3 (the Trades row shows "banked +1.00R (TP1 +2.00R on 50%)", never the TP1 R as the trade's), § Testing (frontend banked amount $500 for the golden TP1 leg, read from the shared fixture); Corrections 10 (optional fields; one JSON read by pytest and Vitest in the `resolved_tokens.json` pattern).

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`TradeRow`, after `banked_r` and after `shares`)
- Modify: `frontend/src/app/ui/plan-cell.ts` (inputs `:132-148`; `tooltip` banked clause `:273-285`; `bankedLegAmount` `:356-371`)
- Modify: `frontend/src/app/ui/plan-cell.spec.ts` (`renderPartial` and the two banked-tooltip expectations `:153-186`; `bankedLegAmount` block `:252-262`)
- Modify: `frontend/src/app/workspaces/trades/trades.ts` (PlanCell bindings `:420-425`)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (PlanCell bindings `:358-363`)
- Create: `frontend/src/app/ui/testing/golden-partial-trade.ts`
- Create: `frontend/src/app/ui/plan-cell.golden.spec.ts`

**Interfaces:**
- Consumes: `tests/analytics/golden_partial_trade.json` (V189-2); row keys `entry_shares`, `banked_contribution_r` (V189-18).
- Produces (V189-22 reads all of them):
  - `TradeRow.entry_shares?: number | null` — the original position size; `shares` stays the API's figure (the remaining count on a priced open PARTIAL).
  - `TradeRow.banked_contribution_r?: number | null` — `Σ fraction × r` over the realized legs.
  - `frontend/src/app/ui/testing/golden-partial-trade.ts`: `GOLDEN_FIXTURE_PATH = '../tests/analytics/golden_partial_trade.json'`, `interface GoldenPartialTrade` (the fixture's shape, keys spelled as in the JSON), `loadGoldenPartialTrade(): GoldenPartialTrade` (memoised `readFileSync(join(process.cwd(), GOLDEN_FIXTURE_PATH))`), `goldenOpenCase(name): GoldenOpenCase`.
  - `bankedLegAmount(entry, bankedEntry, bankedFraction, entryShares, direction): number | null` — same positions as today; the fourth is the ORIGINAL share count.
  - `PlanCell.bankedContributionR = input<number | null>(null)`.

- [ ] **Step 1: Write the golden loader**

Create `frontend/src/app/ui/testing/golden-partial-trade.ts` (test-only, like `resolve-token.ts` beside it; no app code imports it):

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/* v189: the golden scaled-out trade, one JSON shared with pytest
 * (tests/analytics/test_golden_partial_trade_metrics.py and friends), so the
 * backend and the frontend cannot drift. Read from the repo, never copied. */

/** Relative to `process.cwd()`, which is `frontend/` under `ng test`. */
export const GOLDEN_FIXTURE_PATH = '../tests/analytics/golden_partial_trade.json';

export interface GoldenLeg { fraction: number; exit_price: number; r?: number; reason?: string; }

export interface GoldenOpenCase {
  name: string; quote: number | null; shares: number; entry_shares: number;
  r_multiple: number | null; banked_r: number; banked_contribution_r: number;
  banked_amount: number; unrealized_pnl_amount: number | null; working_stop: number;
  risk_of_loss_amount: number; open_profit_to_stop: number | null;
}

export interface GoldenClosedCase {
  name: string; runner_exit: number; runner_r: number; net_r: number;
  realized_pnl_amount: number; pnl_pct: number; status: string; close_reason: string | null;
  backtest_label?: string;
}

export interface GoldenPartialTrade {
  trade: {
    ticker: string; direction: string; shares: number; tp1_fraction: number;
    entry: number; stop_loss: number; tp1: number; tp2: number; risk_per_share: number;
    tp1_leg: GoldenLeg;
  };
  tolerance: number;
  closed_cases: GoldenClosedCase[];
  open_cases: GoldenOpenCase[];
}

let memo: GoldenPartialTrade | null = null;

export function loadGoldenPartialTrade(): GoldenPartialTrade {
  memo ??= JSON.parse(readFileSync(join(process.cwd(), GOLDEN_FIXTURE_PATH), 'utf8')) as GoldenPartialTrade;
  return memo;
}

/** One open case by name; throws on a typo rather than testing nothing. */
export function goldenOpenCase(name: string): GoldenOpenCase {
  const found = loadGoldenPartialTrade().open_cases.find((c) => c.name === name);
  if (!found) throw new Error(`no golden open case "${name}"`);
  return found;
}
```

- [ ] **Step 2: Write the failing golden cell spec**

Create `frontend/src/app/ui/plan-cell.golden.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { PlanCell, bankedLegAmount } from './plan-cell';
import { goldenOpenCase, loadGoldenPartialTrade } from './testing/golden-partial-trade';

/* v189 B1/B3: the golden scaled-out trade (100 sh, f 0.5, entry 100, stop 95,
 * TP1 110) on the Trades row. Banked TP1 = 50 sh x 10 = $500, contributing
 * +1.00R (TP1 +2.00R on 50%). */

describe('PlanCell on the golden partial trade', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  const golden = loadGoldenPartialTrade();
  const t = golden.trade;

  it.each(['quote_113', 'no_quote'])('banks $500 off the ORIGINAL shares (%s)', (name) => {
    const c = goldenOpenCase(name);
    const amount = bankedLegAmount(t.entry, t.tp1_leg.exit_price, t.tp1_leg.fraction, c.entry_shares, t.direction);
    expect(amount).toBeCloseTo(c.banked_amount, 2);
  });

  it('would halve the banked dollars if fed the remaining shares (the bug B1 fixes)', () => {
    const c = goldenOpenCase('quote_113');
    expect(bankedLegAmount(t.entry, t.tp1_leg.exit_price, t.tp1_leg.fraction, c.shares, t.direction))
      .toBeCloseTo(c.banked_amount / 2, 2);
  });

  it('labels the banked part by its contribution, naming the TP1 leg beside it', () => {
    const c = goldenOpenCase('quote_113');
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', t.entry);
    f.componentRef.setInput('target', t.tp2);
    f.componentRef.setInput('stop', c.working_stop);
    f.componentRef.setInput('stopKind', 'trailing');
    f.componentRef.setInput('bankedFraction', t.tp1_leg.fraction);
    f.componentRef.setInput('bankedR', c.banked_r);
    f.componentRef.setInput('bankedContributionR', c.banked_contribution_r);
    f.componentRef.setInput('bankedPct', 10);
    f.componentRef.setInput('bankedAmount', c.banked_amount);
    f.componentRef.setInput('bankedEntry', t.tp1_leg.exit_price);
    f.componentRef.setInput('currency', '$');
    f.detectChanges();
    const title = (f.nativeElement as HTMLElement).querySelector('[title]')!.getAttribute('title')!;
    expect(title).toContain('banked +1.00R (TP1 +2.00R on 50%), +10.00%, +500.00 $ @ 110.00');
    expect(title).not.toContain('banked +2.00R');
  });

  it('reads the fixture from the repo, the same file pytest reads', () => {
    expect(golden.tolerance).toBe(0.005);
    expect(golden.open_cases.map((c) => c.name)).toEqual(['quote_113', 'no_quote']);
  });
});
```

- [ ] **Step 3: Update the existing PlanCell expectations to the new clause**

In `frontend/src/app/ui/plan-cell.spec.ts`:

- `renderPartial`'s override type gains `bankedContributionR: number | null`, and the function adds `f.componentRef.setInput('bankedContributionR', 'bankedContributionR' in overrides ? overrides.bankedContributionR : null);` (default `null` keeps the two existing cases on the fallback head).
- `appends the banked leg to the tooltip once PARTIAL` expects `'Entry 51.00 · Target 150.00 · Trailing stop 118.67 · ' + 'TP1 +0.85R on 50%, +4.10%, +42.00 $ @ 102.00'`.
- `omits the dollar figure when amount or currency is unknown` expects `'Entry 51.00 · Target 150.00 · Trailing stop 118.67 · ' + 'TP1 +0.85R on 50%, +4.10% @ 102.00'`.
- Add after those two:

```ts
  it('leads with the trade-level contribution once the API sends it', () => {
    expect(renderPartial({ bankedContributionR: 0.43 }).querySelector('[title]')!.getAttribute('title'))
      .toBe('Entry 51.00 · Target 150.00 · Trailing stop 118.67 · '
        + 'banked +0.43R (TP1 +0.85R on 50%), +4.10%, +42.00 $ @ 102.00');
  });
```

- In `describe('bankedLegPct / bankedLegAmount')`, rename `computes the dollar amount from shares and fraction` to `computes the dollar amount from the ORIGINAL shares and the fraction` (values unchanged: `bankedLegAmount(100, 110, 0.5, 100, 'bullish')` is 500).

- [ ] **Step 4: Run the specs to verify they fail**

```bash
cd "$WT/frontend" && npx ng test --watch=false --include src/app/ui/plan-cell.golden.spec.ts --include src/app/ui/plan-cell.spec.ts
```

Expected: FAIL — `NG0303` ("Can't set value of the 'bankedContributionR' input") and the two reworded tooltip expectations.

- [ ] **Step 5: Implement**

`frontend/src/app/api/models.ts`, in `TradeRow`:

- after `banked_r: number | null;` add

```ts
  /** v189 B3: the banked legs' share of the TRADE's R -- sum of fraction x
   *  leg R (+1.00R for TP1 +2.00R on 50%). `banked_r` keeps its meaning, the
   *  TP1 leg's own R. Optional so pre-v189 fixtures stay valid. */
  banked_contribution_r?: number | null;
```

- after `shares: number | null;` add

```ts
  /** v189 B1: the ORIGINAL position size, before any leg closed. `shares`
   *  is the remaining count on a priced open PARTIAL, so a banked-leg dollar
   *  figure multiplies this, never `shares`. Optional like `risk_stop`. */
  entry_shares?: number | null;
```

- in `open_shares`' doc comment, replace "`shares` is the ORIGINAL size at open and stays that after a TP1 partial closes part of the position" with "`entry_shares` is the ORIGINAL size at open".

`frontend/src/app/ui/plan-cell.ts`:

- after `readonly bankedR = input<number | null>(null);` add a doc comment `/** v189 B3: the banked legs' contribution to the trade's R (fraction x R). */` and `readonly bankedContributionR = input<number | null>(null);`.
- in `tooltip`, replace the `extraText` line and the `out += ...banked...` line with:

```ts
      const leg = `TP1 ${rMultiple(r)} on ${share(fraction * 100)}`;
      const contribution = this.bankedContributionR();
      const head = contribution === null ? leg : `banked ${rMultiple(contribution)} (${leg})`;
      const extraText = extras.length ? `, ${extras.join(', ')}` : '';
      out += ` · ${head}${extraText} @ ${this.fmt(entry)}`;
```

- `bankedLegAmount`: rename the fourth parameter `shares` to `entryShares` (the body follows the rename). Its doc comment's first sentence becomes: "$-amount for the same leg -- the ORIGINAL share count (`entry_shares`, v189 B1; never the remaining count) times the fraction that leg closed, times the move from entry to its own fill price."

`frontend/src/app/workspaces/trades/trades.ts` and `frontend/src/app/workspaces/dashboard/dashboard.ts` (their `<sb-plan-cell>` blocks), identically:

- after `[bankedR]="row.banked_r"` add `[bankedContributionR]="row.banked_contribution_r ?? null"`;
- in `[bankedAmount]`, replace the argument `row.shares` with `row.entry_shares ?? null` (a payload without the field shows no dollar figure rather than a halved one).

- [ ] **Step 6: Run the specs to verify they pass**

```bash
cd "$WT/frontend" && npx ng test --watch=false --include src/app/ui/plan-cell.golden.spec.ts --include src/app/ui/plan-cell.spec.ts --include src/app/workspaces/trades/trades.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts
```

Expected: PASS.

- [ ] **Step 7: Whole frontend run and lint**

```bash
cd "$WT/frontend" && npx ng test --watch=false && npm run lint
```

Expected: `0 failed`; lint clean.

- [ ] **Step 8: Commit**

```bash
cd "$WT" && git add frontend/src/app/api/models.ts frontend/src/app/ui/plan-cell.ts frontend/src/app/ui/plan-cell.spec.ts frontend/src/app/ui/plan-cell.golden.spec.ts frontend/src/app/ui/testing/golden-partial-trade.ts frontend/src/app/workspaces/trades/trades.ts frontend/src/app/workspaces/dashboard/dashboard.ts && git commit -m "feat(ui): banked TP1 dollars on the original shares; banked label by contribution (v189 B1/B3)"
```

### Task V189-22: Frontend: trade detail banked stats, risk of loss, open profit to stop, T1/T2

**Model:** sonnet — two new computed signals and one corrected multiplier in a signal store, a label pair on the Position card and a tile wording fix, all pinned by the golden fixture and table-driven edge cases.

**Spec:** D5 B1 (`trade-detail.store.ts:425-427` takes `entry_shares`), B3 (Trade detail shows "banked +1.00R (TP1 +2.00R on 50%)"), B5 (the price tile says "to T1" before TP1, "to T2" after; the "$ at risk" tile becomes two labelled figures, "Risk of loss" and "Open profit to stop", the second only with a live quote; golden at 113: $0 and $316.67), B4 (risk of loss: open shares × loss-side distance from entry to the working stop, floored at 0; the gap hint), § Testing (frontend banked amount via the store spec).

**Files:**
- Modify: `frontend/src/app/stores/trade-detail.store.ts` (`bankedStats` `:415-428`; the `dollarAtRisk` block `:550-556`)
- Modify: `frontend/src/app/stores/trade-detail.store.spec.ts` (the `dollarAtRisk` assertions `:365-420`) — outside the ledger row: the tests that pin the replaced signal
- Modify: `frontend/src/app/workspaces/trades/position-card.ts` (`PositionFigures`, `PARTIAL_RISK_SUB`, `positionRows`)
- Modify: `frontend/src/app/workspaces/trades/position-card.spec.ts` (`base`, the label list, the `$ at risk` row checks) — outside the ledger row, same reason
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (`positionFigures` `:621-632`)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (`uses the current stop in the Outcome next block and original risk in Position` `:687-696`) — outside the ledger row, same reason
- Modify: `frontend/src/app/workspaces/trades/outcome-tiles.ts` (`bankedTile` `:66-75`; the price tile `:82-85`)
- Modify: `frontend/src/app/workspaces/trades/outcome-tiles.spec.ts` (`appends the banked leg independently of the remaining position` `:53-59`) — outside the ledger row, same reason
- Create: `frontend/src/app/stores/trade-detail.golden.spec.ts`

**Interfaces:**
- Consumes (V189-21): `TradeRow.entry_shares?`, `TradeRow.banked_contribution_r?`, `loadGoldenPartialTrade()`, `goldenOpenCase(name)`.
- Produces:
  - `TradeDetailStore.riskOfLoss: Signal<number | null>` — `openShares × max(0, (entry − stop) × sign)`, `sign` = −1 for `bearish` else +1; `stop` = `workingStop() ?? stop_loss`; `openShares` = `open_shares ?? shares`; `null` when entry, stop or shares is not a finite number.
  - `TradeDetailStore.openProfitToStop: Signal<number | null>` — `openShares × max(0, (current_price − stop) × sign)`; `null` also when `current_price` is not finite.
  - `dollarAtRisk` is removed (no other reader: `git grep -n dollarAtRisk frontend/src` lists only the files above).
  - `PositionFigures.riskOfLoss: number | null`, `PositionFigures.openProfitToStop: number | null` (replace `dollarAtRisk`); `RISK_OF_LOSS_SUB = 'to the working stop; assumes a fill at the stop, a gap through it loses more'`, `OPEN_PROFIT_SUB = 'open shares, quote to the working stop'` (replace `PARTIAL_RISK_SUB`).

- [ ] **Step 1: Write the failing golden store spec**

Create `frontend/src/app/stores/trade-detail.golden.spec.ts`:

```ts
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ApplicationRef, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { goldenOpenCase, loadGoldenPartialTrade } from '../ui/testing/golden-partial-trade';
import { TradeDetailStore } from './trade-detail.store';

/* v189 B1/B5 on the golden scaled-out trade: TP1 banked 50 of 100 shares at
 * 110 (entry 100), runner floor 106.67. Banked $500; risk of loss $0 (the
 * floor is above entry); open profit to stop at 113 = 50 x 6.33 = $316.67. */

const ID = 'golden0000000000';

describe('TradeDetailStore on the golden partial trade', () => {
  let store: InstanceType<typeof TradeDetailStore>;
  let backend: HttpTestingController;
  const golden = loadGoldenPartialTrade();
  const t = golden.trade;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideHttpClient(), provideHttpClientTesting(), TradeDetailStore],
    });
    store = TestBed.inject(TradeDetailStore);
    backend = TestBed.inject(HttpTestingController);
  });

  function open(name: string): void {
    const c = goldenOpenCase(name);
    store.setId(ID);
    TestBed.inject(ApplicationRef).tick();
    backend.expectOne(`/api/v1/trades/${ID}`).flush({
      id: ID, ticker: t.ticker, direction: t.direction, status: 'PARTIAL',
      entry: t.entry, stop_loss: c.working_stop, risk_stop: t.stop_loss, target: t.tp2,
      shares: c.shares, open_shares: c.shares, entry_shares: c.entry_shares,
      current_price: c.quote, r_multiple: c.r_multiple,
      banked_fraction: t.tp1_leg.fraction, banked_exit_price: t.tp1_leg.exit_price,
      banked_r: c.banked_r, banked_contribution_r: c.banked_contribution_r,
      detail: { trade_id: ID, note: null, working_stop: c.working_stop, legs_realized: [t.tp1_leg] },
    });
    backend.expectOne(`/api/v1/trades/${ID}/journal`).flush({ journaled: false, entry: null });
    backend.verify();
  }

  it.each(['quote_113', 'no_quote'])('banks $500 off the ORIGINAL shares (%s)', (name) => {
    open(name);
    expect(store.bankedStats()?.amount).toBeCloseTo(goldenOpenCase(name).banked_amount, 2);
    expect(store.bankedStats()?.pct).toBeCloseTo(10, 6);
  });

  it.each(['quote_113', 'no_quote'])('has no risk of loss once the runner floor sits above entry (%s)', (name) => {
    open(name);
    expect(store.riskOfLoss()).toBe(goldenOpenCase(name).risk_of_loss_amount);
  });

  it('shows the open profit to the stop only with a live quote', () => {
    open('quote_113');
    expect(store.openProfitToStop()).toBeCloseTo(goldenOpenCase('quote_113').open_profit_to_stop!, 2);
  });

  it('has no open profit to stop without a quote', () => {
    open('no_quote');
    expect(store.openProfitToStop()).toBeNull();
  });
});
```

- [ ] **Step 2: Replace the `dollarAtRisk` assertions in the existing store spec**

In `frontend/src/app/stores/trade-detail.store.spec.ts` (the `describe` whose `open(row, detail)` helper flushes `status: 'ACTIVE', shares: 10` over `detailResponse()`'s entry 100 / stop_loss 95):

- `measures ACTIVE risk and plan figures from their recorded values` (working stop 97): replace `expect(store.dollarAtRisk()).toBe(50);` with `expect(store.riskOfLoss()).toBe(30);` (10 × (100 − 97)).
- Rename `uses remaining open shares and original risk for a PARTIAL position` to `has no risk of loss once a PARTIAL stop sits at entry`, and replace its assertion with `expect(store.riskOfLoss()).toBe(0);` (stop_loss 100, shares 4).
- In the `it.each` table rename the `dollars` column to `loss` and the title to `'narrows original risk and risk of loss: $row'`; every `loss` equals the old `dollars` except `{ row: { risk_stop: 95, stop_loss: null }, stop: 95, risk: 5, loss: null }` (risk of loss reads the working stop, never the original risk stop). The assertion line becomes `expect(store.riskOfLoss()).toBe(loss);`.
- `keeps figures unknown before a response arrives`: replace `dollarAtRisk` with `riskOfLoss` and add `expect(store.openProfitToStop()).toBeNull();`.
- Add after the table:

```ts
  it.each([
    { row: { open_shares: 4 }, loss: 20 },                                         // remaining shares win over shares
    { row: { direction: 'bearish', stop_loss: 105 }, loss: 50 },                   // short: stop above entry
    { row: { direction: 'bearish', stop_loss: 98 }, loss: 0 },                     // short with a locked-in stop
    { row: { stop_loss: 101 }, loss: 0 },                                          // long stop above entry
  ])('measures risk of loss on the loss side, floored at 0: $row', ({ row, loss }) => {
    open(row);
    expect(store.riskOfLoss()).toBe(loss);
  });

  it.each([
    { row: { current_price: 103 }, profit: 80 },                                   // 10 x (103 - 95)
    { row: { current_price: 94 }, profit: 0 },                                     // quote through the stop
    { row: { direction: 'bearish', stop_loss: 105, current_price: 101 }, profit: 40 },
    { row: { current_price: null }, profit: null },
    { row: { current_price: NaN }, profit: null },
    { row: { current_price: '103' }, profit: null },
  ])('measures open profit to the stop only with a finite quote: $row', ({ row, profit }) => {
    open(row);
    expect(store.openProfitToStop()).toBe(profit);
  });
```

- [ ] **Step 3: Run the store specs to verify they fail**

```bash
cd "$WT/frontend" && npx ng test --watch=false --include src/app/stores/trade-detail.golden.spec.ts --include src/app/stores/trade-detail.store.spec.ts
```

Expected: FAIL — `store.riskOfLoss is not a function`, and the golden banked amount reads 250 (the remaining 50 shares × 0.5 × 10).

- [ ] **Step 4: Implement the store**

In `frontend/src/app/stores/trade-detail.store.ts`:

- `bankedStats`: the amount multiplies the ORIGINAL size: `const entryShares = asNumber(trade.entry_shares);` and `const amount = entryShares === null ? null : entryShares * leg.fraction * (leg.exitPrice - trade.entry) * sign;`. Update its doc comment: "`amount` is null when `entry_shares` is unknown (a legacy record or a pre-v189 payload) -- never computed off `shares`, which is the remaining count on a priced PARTIAL (v189 B1)."
- Replace the `withComputed(({ data, riskPerShare, gates }) => ({ dollarAtRisk: ... }))` block's `dollarAtRisk` entry with two signals (the block now destructures `({ data, workingStop, gates })`; `earningsDays` stays):

```ts
    /** v189 B4/B5: what a fill at the working stop would still lose below
     *  entry, on the open shares, floored at 0 -- a PARTIAL at its runner
     *  floor or a break-even stop risks nothing. The server's
     *  `heat.risk_of_loss_amount`, from the row's own numbers. */
    riskOfLoss: computed(() => stopDistance(data(), workingStop(), asNumber(data()?.entry))),
    /** v189 B5: the open profit a fill at the working stop would give back;
     *  null without a live quote. */
    openProfitToStop: computed(() => stopDistance(data(), workingStop(), asNumber(data()?.current_price))),
```

- Add the module-level helper beside `originalRiskPerShare`:

```ts
/** Open shares x the distance from `from` down to the stop (long) or up to it
 *  (short), floored at 0. `from` = entry gives the risk of loss, `from` =
 *  the quote gives the open profit to the stop. Null on any unknown input. */
function stopDistance(trade: TradeDetail | null, workingStop: number | null, from: number | null): number | null {
  const stop = workingStop ?? asNumber(trade?.stop_loss);
  const shares = asNumber(trade?.open_shares) ?? asNumber(trade?.shares);
  if (!trade || from === null || stop === null || shares === null) return null;
  const sign = trade.direction === 'bearish' ? -1 : 1;
  return shares * Math.max(0, (from - stop) * sign);
}
```

(`asNumber` already rejects strings, `NaN` and `±Infinity`, which the tables above pin.)

- [ ] **Step 5: Run the store specs to verify they pass**

```bash
cd "$WT/frontend" && npx ng test --watch=false --include src/app/stores/trade-detail.golden.spec.ts --include src/app/stores/trade-detail.store.spec.ts
```

Expected: PASS.

- [ ] **Step 6: Update the card, tile and page specs (failing)**

`frontend/src/app/workspaces/trades/position-card.spec.ts`:

- `base`: replace `dollarAtRisk: 7.47,` with `riskOfLoss: 7.47, openProfitToStop: 12.5,`.
- the label list becomes `['Open shares', 'Deployed', 'Risk of loss', 'Open profit to stop', 'Sizing mode', 'Gap risk (p90)', 'TP1 closes', 'Break-even at', 'Trail', 'Expires on', 'Time exit on', 'Hold cap']`; every later index shifts by one (`rows[5]` → gap risk, … `rows[11]` → hold cap).
- `expect(rows[2]).toMatchObject({ value: '7.47', sub: RISK_OF_LOSS_SUB });` and `expect(rows[3]).toMatchObject({ value: '12.50', sub: OPEN_PROFIT_SUB });` (import both constants).
- `positionRows({ ...base, status: 'ACTIVE' })[2].sub` is `RISK_OF_LOSS_SUB` too (the hint is not PARTIAL-only any more).
- `hides null rows while retaining real zeros`: `{ ...absent, shares: 0, riskOfLoss: 0, tp1Pct: 0, holdCapBars: 0 }` maps to `['0', '0.00', '0%', '0 bars']` (open profit stays hidden when null).
- the DOM check reads `[data-row="Risk of loss"]` and expects `RISK_OF_LOSS_SUB`; add `expect(el.querySelector('[data-row="Open profit to stop"]')?.textContent).toContain('12.50');`.

`frontend/src/app/workspaces/trades/trade-detail.spec.ts`, `uses the current stop in the Outcome next block and original risk in Position`: replace the `$ at risk` line with `expect(position.querySelector('[data-row="Risk of loss"]')?.textContent).toContain('0.00');` (5 open shares, stop 101 above the fixture's entry 100), and rename the test to `uses the current stop in the Outcome next block and in Position's risk of loss`.

`frontend/src/app/workspaces/trades/outcome-tiles.spec.ts`:

- `appends the banked leg independently of the remaining position` expects `sub: 'TP1 +2.00R on 50% · +10.00% · +50.00'` (no contribution on that row).
- add:

```ts
  it('leads the banked tile with the trade-level contribution (v189 B3)', () => {
    const ctx = context('PARTIAL', { banked_contribution_r: 1 });
    ctx.banked = { fraction: 0.5, exitPrice: 110, r: 2, reason: 'tp1' };
    ctx.bankedStats = { pct: 10, amount: 500 };
    expect(outcomeTiles(ctx).at(-1)?.sub).toBe('banked +1.00R (TP1 +2.00R on 50%) · +10.00% · +500.00');
  });

  it.each([['ACTIVE', 'to T1'], ['PARTIAL', 'to T2']])('names the target the %s price tile measures to', (status, word) => {
    const price = outcomeTiles(context(status, { target: 120 })).find((tile) => tile.id === 'price')!;
    expect(price.sub).toContain(word);
    expect(price.sub).not.toContain(word === 'to T1' ? 'to T2' : 'to T1');
  });
```

Run:

```bash
cd "$WT/frontend" && npx ng test --watch=false --include src/app/workspaces/trades/position-card.spec.ts --include src/app/workspaces/trades/outcome-tiles.spec.ts --include src/app/workspaces/trades/trade-detail.spec.ts
```

Expected: FAIL on the new labels, the banked sub and `to T2`.

- [ ] **Step 7: Implement the card, the page wiring and the tiles**

`frontend/src/app/workspaces/trades/position-card.ts`:

- `PositionFigures`: replace `dollarAtRisk: number | null;` with `riskOfLoss: number | null; openProfitToStop: number | null;`.
- replace `PARTIAL_RISK_SUB` with

```ts
/** v189 B4/B5: two labelled figures so neither reads as the other. */
export const RISK_OF_LOSS_SUB = 'to the working stop; assumes a fill at the stop, a gap through it loses more';
export const OPEN_PROFIT_SUB = 'open shares, quote to the working stop';
```

- in `positionRows`, replace the `$ at risk` line with

```ts
  add('Risk of loss', f.riskOfLoss, num(f.riskOfLoss), RISK_OF_LOSS_SUB);
  add('Open profit to stop', f.openProfitToStop, num(f.openProfitToStop), OPEN_PROFIT_SUB);
```

The card's `dl` already wraps: one column below a 640px container, two above, and `overflow-wrap: anywhere` on the host keeps the longer sub inside a phone-width row; no style change.

`frontend/src/app/workspaces/trades/trade-detail.ts`, `positionFigures`: replace `dollarAtRisk: this.store.dollarAtRisk(),` with `riskOfLoss: this.store.riskOfLoss(), openProfitToStop: this.store.openProfitToStop(),`.

`frontend/src/app/workspaces/trades/outcome-tiles.ts`:

- in `bankedTile`, the `sub` becomes `joined([bankedHead(ctx.trade, leg), stats ? pct(stats.pct) : null, stats ? signed(stats.amount) : null])`, with the module-level helper

```ts
/** v189 B3: the banked part is the trade's contribution, never the TP1 leg's own R. */
function bankedHead(trade: TradeRow, leg: Leg): string {
  const legText = `TP1 ${rMultiple(leg.r ?? null)} on ${share(leg.fraction == null ? null : leg.fraction * 100)}`;
  const contribution = trade.banked_contribution_r ?? null;
  return contribution === null ? legText : `banked ${rMultiple(contribution)} (${legText})`;
}
```

- in `openTiles`, the price tile's `sub` reads the target it measures to: `const targetWord = t.status === 'PARTIAL' ? 'T2' : 'T1';` and `` sub: `to stop ${pct(pctFrom(current, t.stop_loss ?? null))} · to ${targetWord} ${pct(pctFrom(current, t.target ?? null))}` `` (`t.target` is TP2 once PARTIAL; the server already sends it).

- [ ] **Step 8: Run the specs to verify they pass**

```bash
cd "$WT/frontend" && npx ng test --watch=false --include src/app/workspaces/trades/position-card.spec.ts --include src/app/workspaces/trades/outcome-tiles.spec.ts --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/stores/trade-detail.golden.spec.ts --include src/app/stores/trade-detail.store.spec.ts
```

Expected: PASS.

- [ ] **Step 9: Whole frontend run and lint**

```bash
cd "$WT/frontend" && git grep -n "dollarAtRisk\|PARTIAL_RISK_SUB" -- src ; npx ng test --watch=false && npm run lint
```

Expected: the grep prints nothing; `0 failed`; lint clean.

- [ ] **Step 10: Commit**

```bash
cd "$WT" && git add frontend/src/app/stores/trade-detail.store.ts frontend/src/app/stores/trade-detail.store.spec.ts frontend/src/app/stores/trade-detail.golden.spec.ts frontend/src/app/workspaces/trades/position-card.ts frontend/src/app/workspaces/trades/position-card.spec.ts frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts frontend/src/app/workspaces/trades/outcome-tiles.ts frontend/src/app/workspaces/trades/outcome-tiles.spec.ts && git commit -m "feat(ui): trade detail banks on original shares; risk of loss and open profit to stop; T1/T2 (v189 B1/B3/B5)"
```

### Task V189-23: Frontend: enforced heat and risk of loss in the dashboard store and on the Risk page

**Model:** sonnet — a JSON key rename followed through one store, two optional row fields, one table column and one labelled figure beside an existing one; the risk definition itself lives server-side (V189-19).

**Spec:** D5 B4 ("Risk of loss (to stop)" never shown as a gauge against the cap; "Heat (enforced)" beside it; both carry the hint "assumes a fill at the stop; a gap through it loses more"; Risk page rows keep summing to enforced heat and gain a Risk of loss column; display only); index clarifications 7 (JSON rename) and 12 (no Dashboard card: the partner removed it in `ce43c07a`).

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`Dashboard` `:407`; `RiskPosition` `:1357-1365`)
- Modify: `frontend/src/app/stores/dashboard.store.ts` (`riskUsedPct` `:201`; `riskUtilisation` `:286-295`)
- Modify: `frontend/src/app/stores/dashboard.store.spec.ts` (fixture `:66`; the three utilisation tests `:239-272`)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (fixture `:80`)
- Modify: `frontend/src/app/stores/risk.store.ts` (exposure block `:113-121`)
- Modify: `frontend/src/app/workspaces/risk/risk.ts` (class doc `:40-43`; heat panel `:212-250`; `visible` and `columns` `:702-714`; `gapRiskNote` neighbourhood `:783`)
- Modify: `frontend/src/app/workspaces/risk/risk.spec.ts` (new `describe`; the drawer column list in `Risk exposure on a phone`)

**Interfaces:**
- Consumes (V189-19): dashboard JSON `heat_enforced_pct`, `risk_of_loss_pct`, `risk_of_loss_amount`, `risk_cap_pct`; Risk page rows `risk_of_loss_amount`, `risk_of_loss_pct` (`null` for a PENDING placeholder).
- Produces:
  - `Dashboard.heat_enforced_pct: number | null`, `Dashboard.risk_of_loss_pct: number | null`, `Dashboard.risk_of_loss_amount: number | null` (`risk_used_pct` removed).
  - `DashboardStore.heatEnforcedPct`, `riskOfLossPct`, `riskOfLossAmount` signals; `riskUtilisation` = `heat_enforced_pct / risk_cap_pct` (`riskUsedPct` removed; `git grep -n riskUsedPct frontend/src` finds no reader outside the store).
  - `RiskPosition.risk_of_loss_amount?: number | null`, `RiskPosition.risk_of_loss_pct?: number | null`.
  - `RiskStore.riskOfLossTotal: Signal<number | null>`, `RiskStore.riskOfLossPctTotal: Signal<number | null>` — sums over rows with a figure; `null` when no row has one.

- [ ] **Step 1: Write the failing store tests**

`frontend/src/app/stores/dashboard.store.spec.ts`:

- in the fixture at `:66` replace `risk_used_pct: 4,` with `heat_enforced_pct: 4, risk_of_loss_pct: 1.5, risk_of_loss_amount: 150,`;
- in `computes risk utilisation as a fraction of the cap`, `reports unknown utilisation as null, not zero` and `survives a zero cap without dividing by it`, rename the key `risk_used_pct` to `heat_enforced_pct` (values unchanged);
- add:

```ts
  it('reads enforced heat and risk of loss as two figures, never one (v189 B4)', () => {
    tick();
    respond({ heat_enforced_pct: 8, risk_of_loss_pct: 0, risk_of_loss_amount: 0, risk_cap_pct: 10 });
    expect(store.heatEnforcedPct()).toBe(8);
    expect(store.riskOfLossPct()).toBe(0);
    expect(store.riskOfLossAmount()).toBe(0);
    // Utilisation stays on the figure the scanner gates on.
    expect(store.riskUtilisation()).toBeCloseTo(0.8);
  });

  it('keeps an unknown risk of loss null, not zero', () => {
    tick();
    respond({ risk_of_loss_pct: null, risk_of_loss_amount: null });
    expect(store.riskOfLossPct()).toBeNull();
    expect(store.riskOfLossAmount()).toBeNull();
  });
```

`frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, fixture at `:80`: replace `risk_used_pct: 3,` with `heat_enforced_pct: 3, risk_of_loss_pct: 1, risk_of_loss_amount: 100,`. `has no Risk used card and no Paper account caption` stays as it is and must stay green (index clarification 12).

- [ ] **Step 2: Write the failing Risk page tests**

`frontend/src/app/workspaces/risk/risk.spec.ts`:

- in `Risk exposure on a phone (v179 §3.1)` › `reaches every column ...`, the sorted key list becomes `['entry', 'risk_of_loss', 'risk_pct', 'shares', 'stop_loss', 'strategy', 'ticker']` (the new column sits in the drawer; the compact row is unchanged and its test must stay green).
- add a new block after `Risk gauge, budget and correlation matrix`:

```ts
/* -- v189 B4: risk of loss beside enforced heat, never instead of it -------- */

describe('Risk of loss beside enforced heat (v189 B4)', () => {
  const rows = [
    { trade_id: 't1', ticker: 'AAPL', strategy: 'VWAP', shares: 10, entry: 100, stop_loss: 95,
      risk_pct: 3, risk_of_loss_amount: 50, risk_of_loss_pct: 0.5 },
    { trade_id: 't2', ticker: 'MSFT', strategy: 'RSI', shares: 50, entry: 100, stop_loss: 106.67,
      risk_pct: 2.5, risk_of_loss_amount: 0, risk_of_loss_pct: 0 },          // the golden runner at its floor
    { trade_id: 't3', ticker: 'NVDA', strategy: 'RSI', shares: 20, entry: 50, stop_loss: 48,
      risk_pct: 0.4, risk_of_loss_amount: null, risk_of_loss_pct: null },    // a PENDING placeholder
  ];
  const heat = { open_pct: 5.9, cap_pct: 6, utilisation_pct: 98 };
  const el = async () => (await render({ positions: rows, heat })).nativeElement as HTMLElement;

  it('labels the gauge figure as the enforced heat and keeps it on open_pct', async () => {
    const page = await el();
    const figure = page.querySelector('.heat')!;
    expect(figure.textContent).toContain('Heat (enforced)');
    expect(figure.textContent).toContain('5.90%');
  });

  it('shows the risk of loss to the stop as its own figure, summed over the rows that have one', async () => {
    const line = (await el()).querySelector('[data-testid="risk-of-loss"]')!;
    expect(line.closest('sb-panel')!.getAttribute('heading')).toBe('Portfolio heat');
    expect(line.textContent).toContain('Risk of loss (to stop)');
    expect(line.textContent).toContain('50');
    expect(line.textContent).toContain('0.50%');
    expect(line.querySelector('[role="meter"]')).toBeNull();               // never a gauge against the cap
  });

  it('says both figures assume a fill at the stop', async () => {
    expect((await el()).querySelector('[data-testid="stop-fill-hint"]')!.textContent)
      .toContain('assume a fill at the stop; a gap through it loses more');
  });

  it('adds a Risk of loss column whose footer sums the rows, beside the Risk % that sums to heat', async () => {
    // sb-data-table puts no data-col on desktop th/td: read header and footer cells by index.
    const table = (await el()).querySelector('sb-data-table')!;
    const headers = [...table.querySelectorAll('thead th')].map((th) => th.textContent!.trim());
    const footer = [...table.querySelectorAll('tfoot td')].map((td) => td.textContent!.trim());
    const at = (label: string) => footer[headers.findIndex((h) => h.startsWith(label))];
    expect(headers.some((h) => h.startsWith('Risk of loss'))).toBe(true);
    expect(at('Risk of loss')).toBe('50.00');
    expect(at('Risk %')).toBe('5.90');
  });

  it('reads no figure as no figure, not zero', async () => {
    const fixture = await render({ positions: [rows[2]], heat });
    const line = (fixture.nativeElement as HTMLElement).querySelector('[data-testid="risk-of-loss"]')!;
    expect(line.textContent).toContain('—');
  });
});
```

- [ ] **Step 3: Run the specs to verify they fail**

```bash
cd "$WT/frontend" && npx ng test --watch=false --include src/app/stores/dashboard.store.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/risk/risk.spec.ts
```

Expected: FAIL — TypeScript errors on the unknown `heat_enforced_pct` key, `store.heatEnforcedPct is not a function`, no `[data-testid="risk-of-loss"]`.

- [ ] **Step 4: Implement models and stores**

`frontend/src/app/api/models.ts`:

- in `Dashboard`, replace `risk_used_pct: number | null;` with

```ts
  /** v189 B4: `heat.open_heat` -- the figure the scanner gates new alerts on
   *  (was `risk_used_pct`). */
  heat_enforced_pct: number | null;
  /** v189 B4: what fills at the current working stops would still lose below
   *  entry, filled positions only, floored at 0 per position. Display only;
   *  never a gauge against `risk_cap_pct`. Null when unknown. */
  risk_of_loss_pct: number | null;
  risk_of_loss_amount: number | null;
```

- in `RiskPosition`, after `risk_pct: number | null;` add

```ts
  /** v189 B4: risk of loss to the working stop for this row; null for a
   *  PENDING placeholder. `risk_pct` still sums to `heat.open_pct`.
   *  Optional so pre-v189 fixtures stay valid. */
  risk_of_loss_amount?: number | null;
  risk_of_loss_pct?: number | null;
```

`frontend/src/app/stores/dashboard.store.ts`: replace `riskUsedPct: computed(() => data()?.risk_used_pct ?? null),` with

```ts
    heatEnforcedPct: computed(() => data()?.heat_enforced_pct ?? null),
    riskOfLossPct: computed(() => data()?.risk_of_loss_pct ?? null),
    riskOfLossAmount: computed(() => data()?.risk_of_loss_amount ?? null),
```

and in `riskUtilisation` read `data()?.heat_enforced_pct` instead of `risk_used_pct`; its doc comment says "Enforced heat as a fraction of the cap".

`frontend/src/app/stores/risk.store.ts`, after `positions`:

```ts
    /** v189 B4: summed risk of loss to the stop over the rows that carry one
     *  (a PENDING placeholder carries none). Null when no row has a figure,
     *  so "nothing known" never reads as "nothing at risk". */
    riskOfLossTotal: computed(() => sumKnown((data()?.positions ?? []).map((row) => row.risk_of_loss_amount))),
    riskOfLossPctTotal: computed(() => sumKnown((data()?.positions ?? []).map((row) => row.risk_of_loss_pct))),
```

with the module-level helper

```ts
function sumKnown(values: readonly (number | null | undefined)[]): number | null {
  const known = values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  return known.length ? known.reduce((sum, v) => sum + v, 0) : null;
}
```

- [ ] **Step 5: Implement the Risk page**

`frontend/src/app/workspaces/risk/risk.ts`:

- class doc: replace the paragraph starting `**"Risk used" appears here and on the Dashboard.` with: `**Two risk figures, never one (v189 B4).** "Heat (enforced)" is \`heat.open_pct\`, the sum of the \`trade_risk_pct\` rows below and the figure the scanner gates on; the gauge and the budget read it. "Risk of loss (to stop)" is what fills at the current working stops would still lose below entry, floored at 0 per position, so a de-risked runner counts 0. It is shown beside heat, never as headroom against the cap.`
- in the `.heat` block, before the figure span, add `<span class="heat-label">Heat (enforced)</span>`.
- after the `gap-risk` paragraph add

```html
      <!-- v189 B4: display only. Never a meter: the scanner gates on heat above. -->
      <p class="gap-risk" data-testid="risk-of-loss">
        <span class="gap-risk-label">Risk of loss (to stop)</span>
        <span class="num">{{ riskOfLossNote() }}</span>
      </p>
      <p class="section-help" data-testid="stop-fill-hint">
        Heat and risk of loss both assume a fill at the stop; a gap through it loses more.
      </p>
```

- styles: `.heat-label { color: var(--text-muted); font-size: var(--register-label); }` next to `.heat-cap` (the `.heat` row is already `align-items: baseline` and `flex`; add `flex-wrap: wrap;` to `.heat` so the label, figure and cap wrap at 390px instead of overflowing).
- component: `protected readonly riskOfLossNote = computed(() => { const value = this.store.riskOfLossTotal(); const pctTotal = this.store.riskOfLossPctTotal(); if (value === null) return ABSENT; return pctTotal === null ? amount(value, this.connection.currency(), 0) : \`${amount(value, this.connection.currency(), 0)} · ${this.fmt(pctTotal)}% of balance\`; });` (import `ABSENT` from `../../ui/format` if the file does not already).
- `visible` becomes `['ticker', 'strategy', 'shares', 'entry', 'stop_loss', 'risk_pct', 'risk_of_loss']`; in `columns` add, after `risk_pct`:

```ts
    { key: 'risk_of_loss', header: 'Risk of loss', numeric: true, sortable: true,
      value: (row) => num(row.risk_of_loss_amount ?? null),
      footer: (rows) => num(rows.reduce((sum, row) => sum + (row.risk_of_loss_amount ?? 0), 0)) },
```

No `compact` slot: the phone row keeps ticker, Risk %, stop and entry (v179 money floor, pinned by the phone test); the new column is reached through the row drawer. Update the `visible` comment to "a seven-column table".

- [ ] **Step 6: Run the specs to verify they pass**

```bash
cd "$WT/frontend" && npx ng test --watch=false --include src/app/stores/dashboard.store.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/risk/risk.spec.ts --include src/app/stores/risk.store.spec.ts
```

Expected: PASS.

- [ ] **Step 7: Whole frontend run and lint**

```bash
cd "$WT/frontend" && git grep -n "risk_used_pct\|riskUsedPct" -- src ; npx ng test --watch=false && npm run lint
```

Expected: the grep prints nothing; `0 failed`; lint clean. (The three-width layout audit for this page runs in V189-25's last step.)

- [ ] **Step 8: Commit**

```bash
cd "$WT" && git add frontend/src/app/api/models.ts frontend/src/app/stores/dashboard.store.ts frontend/src/app/stores/dashboard.store.spec.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts frontend/src/app/stores/risk.store.ts frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/risk/risk.spec.ts && git commit -m "feat(ui): enforced heat beside risk of loss to the stop on the Risk page; dashboard store follows the rename (v189 B4)"
```

### Task V189-24: Frontend: win-rate tile shows the label basis and scratch/unscored counts

**Model:** sonnet — three optional payload fields and one hint string on an existing tile, with the empty and pre-deploy cases pinned.

**Spec:** D6 (the Analytics win-rate tile shows the `scratch` and `unscored` counts beside the rate and carries the hint "scaled-out trades are labelled by net R from <date>; earlier ones by TP1 touch"; ExpR is unaffected); Corrections 2 (the Dashboard chip counts legs and is not touched).

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`AnalyticsPerformance` `:584-590`)
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.ts` (`kpiTiles` win-rate tile `:271`; new exported helper)
- Create: `frontend/src/app/workspaces/analytics/tabs/overview-label-basis.spec.ts`

**Interfaces:**
- Consumes (V189-20): `/api/v1/analytics/performance` top-level `scratch_n: int`, `unscored_n: int`, `label_basis_since: str | None` (`None` until V189-27 sets the date).
- Produces:
  - `AnalyticsPerformance.scratch_n?: number`, `unscored_n?: number`, `label_basis_since?: string | null`.
  - `winRateHint(performance: Pick<AnalyticsPerformance, 'scratch_n' | 'unscored_n' | 'label_basis_since'> | null): string | undefined` exported from `overview.ts`.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/workspaces/analytics/tabs/overview-label-basis.spec.ts`:

```ts
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { AnalyticsStore } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { OverviewTab, winRateHint } from './overview';

/* v189 D6: scaled-out closes are labelled by net R from the deploy date and
 * not backfilled, so the win rate steps at deploy. The tile says so, and
 * shows the closes the rate leaves out. */

const BASIS = { label_basis_since: '2026-10-24', scratch_n: 3, unscored_n: 1 };

describe('winRateHint', () => {
  it('names the label basis date and the excluded counts', () => {
    expect(winRateHint(BASIS)).toBe(
      'Scaled-out trades are labelled by net R from 2026-10-24; earlier ones by TP1 touch. '
      + 'Not in the rate: 3 scratch, 1 unscored.');
  });

  it('shows zero counts as zero once the basis date exists', () => {
    expect(winRateHint({ ...BASIS, scratch_n: 0, unscored_n: 0 })).toBe(
      'Scaled-out trades are labelled by net R from 2026-10-24; earlier ones by TP1 touch. '
      + 'Not in the rate: 0 scratch, 0 unscored.');
  });

  it('keeps the counts without a basis date (before the release sets it)', () => {
    expect(winRateHint({ ...BASIS, label_basis_since: null })).toBe('Not in the rate: 3 scratch, 1 unscored.');
  });

  it('adds no hint for a payload without the fields (an older server)', () => {
    expect(winRateHint({})).toBeUndefined();
    expect(winRateHint(null)).toBeUndefined();
  });
});

describe('OverviewTab win-rate tile', () => {
  beforeEach(() => TestBed.resetTestingModule());

  function tileText(performanceOver: Record<string, unknown>): string {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        { provide: AnalyticsStore, useValue: {
          unit: signal('r'), scopeN: signal(34), tableOpen: signal({}),
          performance: signal({
            totals: {}, win_rate: 53.5, win_rate_n: 34, expectancy_r: -0.136, expectancy_n: 34,
            derived: {}, distributions: { returns: [], r_multiples: [] }, calendar: [],
            rolling_wr: [], rolling_exp_r: [], relocated: {}, by_confidence: {}, scope: {}, n: 34,
            ...performanceOver,
          }),
          performanceError: signal(null), equityCurve: signal(null), equityCurveError: signal(null),
          varianceBand: signal(null), varianceBandError: signal(null),
          setTableOpen: () => {}, reload: () => {},
        } },
        { provide: ConnectionStore, useValue: { currency: signal('$') } },
        { provide: PreferencesStore, useValue: { values: () => ({}), update: () => {} } },
      ],
    });
    const fixture = TestBed.createComponent(OverviewTab);
    fixture.detectChanges();
    const tile = [...(fixture.nativeElement as HTMLElement).querySelectorAll('sb-stat-tile')]
      .find((el) => el.textContent?.includes('Win rate'))!;
    return tile.textContent!.replace(/\s+/g, ' ');
  }

  it('carries the label-basis hint and the counts under the rate', () => {
    const text = tileText(BASIS);
    expect(text).toContain('53.50%');
    expect(text).toContain('labelled by net R from 2026-10-24');
    expect(text).toContain('3 scratch, 1 unscored');
  });

  it('renders as before when the payload has no label-basis fields', () => {
    expect(tileText({})).not.toContain('scratch');
  });
});
```

If `OverviewTab` reads a store signal the stub above lacks (compare with `storeStub` in `overview.spec.ts`), copy that signal from `storeStub` with the same value; the assertions do not change.

- [ ] **Step 2: Run the spec to verify it fails**

```bash
cd "$WT/frontend" && npx ng test --watch=false --include src/app/workspaces/analytics/tabs/overview-label-basis.spec.ts
```

Expected: FAIL — `winRateHint` is not exported from `./overview`.

- [ ] **Step 3: Implement**

`frontend/src/app/api/models.ts`, in `AnalyticsPerformance` after `win_rate_n: number;`:

```ts
  /** v189 D6: closes the win rate leaves out -- scaled-out closes inside
   *  +-0.01R (`scratch`) and closes whose net R could not be computed
   *  (`unscored`). Optional so pre-v189 fixtures stay valid. */
  scratch_n?: number;
  unscored_n?: number;
  /** v189 D6: ISO date from which scaled-out trades are labelled by net R
   *  (`metrics.LABEL_BASIS_SINCE`); null before the release sets it. */
  label_basis_since?: string | null;
```

`frontend/src/app/workspaces/analytics/tabs/overview.ts`:

- module-level, exported:

```ts
/** v189 D6: the win-rate tile's hint -- the label basis date and the closes
 *  the rate leaves out. Undefined when the server sends neither (an older
 *  payload), so the tile renders exactly as before. */
export function winRateHint(
  performance: Pick<AnalyticsPerformance, 'scratch_n' | 'unscored_n' | 'label_basis_since'> | null,
): string | undefined {
  if (!performance) return undefined;
  const { scratch_n: scratch, unscored_n: unscored, label_basis_since: since } = performance;
  const counts = scratch === undefined && unscored === undefined
    ? null : `Not in the rate: ${scratch ?? 0} scratch, ${unscored ?? 0} unscored.`;
  const basis = since ? `Scaled-out trades are labelled by net R from ${since}; earlier ones by TP1 touch.` : null;
  const parts = [basis, counts].filter((part): part is string => part !== null);
  return parts.length ? parts.join(' ') : undefined;
}
```

(import `AnalyticsPerformance` as a type from `../../../api/models` if the file does not already).

- the win-rate tile becomes `fixedTile('Win rate', share(winRate, 2), performance?.win_rate_n ?? null, this.winRateTrend(), winRateHint(performance ?? null)),`. The hint renders through `sb-stat-tile`'s existing `.hint` block, which wraps as prose at every width; no style change.

- [ ] **Step 4: Run the specs to verify they pass**

```bash
cd "$WT/frontend" && npx ng test --watch=false --include src/app/workspaces/analytics/tabs/overview-label-basis.spec.ts --include src/app/workspaces/analytics/tabs/overview.spec.ts
```

Expected: PASS (the existing six-tile and money-line tests are unchanged: their payload has no label-basis fields).

- [ ] **Step 5: Whole frontend run and lint**

```bash
cd "$WT/frontend" && npx ng test --watch=false && npm run lint
```

Expected: `0 failed`; lint clean.

- [ ] **Step 6: Commit**

```bash
cd "$WT" && git add frontend/src/app/api/models.ts frontend/src/app/workspaces/analytics/tabs/overview.ts frontend/src/app/workspaces/analytics/tabs/overview-label-basis.spec.ts && git commit -m "feat(ui): win-rate tile names the label basis and the scratch/unscored counts (v189 D6)"
```

