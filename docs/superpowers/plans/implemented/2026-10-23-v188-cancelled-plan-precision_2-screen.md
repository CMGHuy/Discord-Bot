# v188 — Cancelled-plan precision: Part 2, the Cancels screen and verification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-23-v188-cancelled-plan-precision-design.md](../specs/2026-10-23-v188-cancelled-plan-precision-design.md)
**Index:** [2026-10-23-v188-cancelled-plan-precision_0-index.md](2026-10-23-v188-cancelled-plan-precision_0-index.md) — Goal, Global Constraints, Spec clarifications, **Contracts** (payload shape, every shared name), Review Focus, Parallelisation and the task ledger live there. This part covers V188-6..V188-9 and consumes the `GET /api/v1/cancel-precision` payload that Part 1 (V188-5) serves.

**Worktree:** every command below runs in `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-23-v188-cancelled-plan-precision` (written `$WT` below), created by V188-1. **Never edit the main tree's `frontend/`**: another session may hold uncommitted edits there (dashboard, `ui/layout`, `metric-card`, `spinner`, `panel-help`, `realized-pnl`, `equity-candles.*`). Each task touches only the files its **Files** block lists; `git add` names those files one by one, never `git add -A` or `git add frontend/`. After every task run `git -C E:/Documents/Private/Projects/Discord-Bot status --short -- frontend` and confirm nothing of yours landed in the main tree.

**Narrow runs.** A frontend spec runs alone with `cd $WT/frontend && npx ng test --include <path relative to frontend/>` (vitest through the Angular builder). The full suites run once, in V188-9.

## Screen design (layout A+B, the decisions every V188-7/V188-8 step follows)

The screen is one page, `/cancels`, two stacked sections. All figures come from the payload; the client formats and filters, it never recomputes a rate, an interval or an R sum.

1. **Headline panel** (`CancelsSummary`). Two figures at equal prominence, side by side from tablet up, stacked on phone: **Precision** (`62% of 37`, its 95% CI, `N 37`) and **Net R** (`-3.40R`, its CI, `N 37`, with "R avoided +23.00R · R missed 26.40R" under it). Under them: the frozen caption, the survival line (how many plans reach the precision N, and why the rest do not), the tie count, and the `without risk_cap` figure. Then the **baseline** line (stop-first rate of filled plans), the **data-as-of** stamp with the scored window, the rule-change list and the manual-cancel count.
2. **Reason cards.** `risk_cap` (trigger entry) and `risk_cap` (crossing price) sit in one pair that is never split, then `invalidated`, `expired`, `other`. Each card is a real `<button>` (touch target `min-height: var(--control-h)`, 44px on touch), shows precision `xx% of N`, net R and the small-N marker. The `risk_cap` pair carries `RISK_CAP_LABEL`; the crossing-price card says how many entries are `recorded` and how many `estimated`. `other` says "not in the headline".
3. **Counts strip.** Four buttons: right, wrong, unresolved, untriggered after cancel, each with its count and its R (R avoided, R missed, mark-to-market R, none). They read the figure of the picked card, or `headline.all` when none is picked, and say which. On the `risk_cap` cards the words are "Setup lost" / "Setup reached TP1", never "right/wrong cancel". `TP1_NOTE` sits under the strip.
4. **Splits.** Origin, direction, horizon: one button row per key with `xx% of N`, net R and the small-N marker; the note "Cards pool regular and next-session plans."
5. **Plan table** (`CancelsTable`, `sb-data-table`, client-paged as `cancels-plans`). Columns ticker, strategy, badge tier, horizon, reason (with entry model and `estimated`/`recorded`), cancel date, verdict, R, cap-implied size. Phone compact row: line 1 ticker + verdict, line 2 cancel date + R. Default 10 rows desktop, 5 phone/tablet (`clientPaging`), saved per device class by the table itself; 5 rows or fewer shows no pager.
6. **Filter.** A click on a card, count or split row calls the store, which toggles that key (a second click on the active one clears it). Card and outcome and split combine (AND). With no card picked, an outcome or split narrows the headline population (trigger-entry rows of the three REASONS), so the table lists the rows behind the figure clicked. A "Clear filter" button shows while any filter is on.
7. **Device classes** (`docs/claude/ui-design.md` § Device classes): the summary is a size container (`container-type: inline-size; container-name: cancels`). Below 640px everything is one column. 640–1023px: headline two columns, cards two columns (the `risk_cap` pair takes one full row), splits two columns. From 1024px: headline two columns, cards in one row (`grid-auto-flow: column`), splits three columns via `grid-auto-flow: column`. No `repeat(<digit>` (the workspace-consistency spec forbids fixed counts); no `::ng-deep`; text only through the text tokens.

# Phase 3 — The Cancels screen

### Task V188-6: API types, `CancelsStore` and pure helpers

**Model:** sonnet — typed wire models, a small signal store and pure formatters against a fixed contract; no design judgement left.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (append the four v188 types at the end)
- Create: `frontend/src/app/testing/cancel-fixtures.ts`
- Create: `frontend/src/app/stores/cancels.store.ts`
- Create: `frontend/src/app/stores/cancels.store.spec.ts`
- Create: `frontend/src/app/workspaces/cancels/cancels.helpers.ts`
- Create: `frontend/src/app/workspaces/cancels/cancels.helpers.spec.ts`

**Interfaces:**
- Consumes: the route `GET /api/v1/cancel-precision` (V188-5); its 200 body is the Payload of the index § Contracts, field names verbatim.
- Produces: `CancelOutcome`, `CancelFigure`, `CancelPlanRow`, `CancelPrecision` (models.ts); `CancelsStore`, `CancelCardKey`, `CancelSplit`, `CancelFilter`, `NO_FILTER`, `CANCELS_URL` (store); `figureText`, `ciText`, `rText`, `verdictLabel`, `filterRows` (helpers); `CANCEL_PAYLOAD`, `EMPTY_CANCEL_PAYLOAD`, `fig` (fixtures). V188-7 and V188-8 import these by these names.

- [ ] **Step 1: Confirm the worktree and the untouched main tree**

```bash
cd E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-23-v188-cancelled-plan-precision
git branch --show-current          # 2026-10-23-v188-cancelled-plan-precision
git log --oneline -1 -- swingbot/admin/api_v1/cancel_precision.py   # V188-5's commit is present
git -C E:/Documents/Private/Projects/Discord-Bot status --short -- frontend   # note what is there; never touch it
```

- [ ] **Step 2: Append the wire types to `frontend/src/app/api/models.ts`**

Exact copy (the field names are the Python payload's, so they stay snake_case):

```ts
/* v188 -- cancelled-plan precision (`GET /api/v1/cancel-precision`).
 * A hypothetical replay of every bot-cancelled plan; the server computes
 * every figure and the SPA only formats and filters. Fractions are 0..1,
 * R values 2 dp. */

/** The four replay outcomes. Frozen names: never `never_triggered`, which
 *  is an existing session_expiry reason code. */
export type CancelOutcome = 'right' | 'wrong' | 'unresolved' | 'untriggered_after_cancel';

/** One group's figure. `n` = right + wrong (the precision N); `total`
 *  counts every row of the group, excluded ones included. */
export interface CancelFigure {
  n: number;
  total: number;
  excluded: number;
  precision: number | null;
  precision_ci: [number, number] | null;
  r_avoided: number;
  r_missed: number;
  net_r: number;
  net_r_ci: [number, number] | null;
  counts: Record<CancelOutcome, number>;
  unresolved_r: number;
  ties: number;
  small_n: boolean;
}

/** One replayed cancel. A `risk_cap` plan yields two rows with the same
 *  `plan_id`: `entry_model` 'trigger' and 'cancel_fill'. `outcome`, `r`
 *  and `exit_date` are null on an excluded row. */
export interface CancelPlanRow {
  plan_id: string;
  ticker: string;
  strategy: string;
  horizon_key: string;
  direction: 'long' | 'short';
  origin: 'regular' | 'next_session';
  reason: 'risk_cap' | 'invalidated' | 'expired' | 'other';
  raw_reason: string | null;
  cancel_date: string;
  entry_model: 'trigger' | 'cancel_fill';
  entry_source: 'estimated' | 'recorded' | null;
  entry: number | null;
  stop: number | null;
  tp1: number | null;
  badge: string | null;
  stop_ceiling_pct: number | null;
  cap_size_pct: number | null;
  outcome: CancelOutcome | null;
  r: number | null;
  tie: boolean;
  exit_date: string | null;
  excluded: string | null;
}

/** The whole payload. A split key is present only when it has a row. */
export interface CancelPrecision {
  generated_at: string;
  data_as_of: string | null;
  caption: string;
  risk_cap_label: string;
  tp1_note: string;
  small_n_threshold: number;
  window: { first: string | null; last: string | null };
  rule_changes: { date: string; label: string }[];
  out_of_scope: { manual: number };
  headline: { all: CancelFigure; without_risk_cap: CancelFigure };
  baseline: CancelFigure;
  cards: {
    risk_cap: CancelFigure;
    risk_cap_fill: CancelFigure;
    invalidated: CancelFigure;
    expired: CancelFigure;
    other: CancelFigure;
  };
  splits: {
    origin: Partial<Record<'regular' | 'next_session', CancelFigure>>;
    direction: Partial<Record<'long' | 'short', CancelFigure>>;
    horizon: Record<string, CancelFigure>;
  };
  rows: CancelPlanRow[];
}
```

- [ ] **Step 3: Write the fixtures `frontend/src/app/testing/cancel-fixtures.ts`**

Shared by every Cancels spec, so the store, the summary, the table and the page are tested against one idea of the wire. Export `fig(over: Partial<CancelFigure> = {}): CancelFigure` (defaults: every number 0, both intervals and `precision` null, counts all 0, `small_n: true`), `CANCEL_PAYLOAD: CancelPrecision` and `EMPTY_CANCEL_PAYLOAD: CancelPrecision`. The figures are internally consistent on purpose (headline = the three reason cards; `without_risk_cap` = invalidated + expired), so a page that summed them would get the numbers it is handed:

| Group | n | total | excl | precision | precision_ci | r_avoided | r_missed | net_r | net_r_ci | right/wrong/unres/untrig | unresolved_r | ties | small_n |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `headline.all` | 37 | 52 | 2 | 0.6216 | [0.45, 0.78] | 23 | 26.4 | -3.4 | [-9.1, 2.3] | 23/14/9/4 | 1.35 | 3 | false |
| `headline.without_risk_cap` | 8 | 12 | 1 | 0.75 | [0.4, 1] | 6 | 4.2 | 1.8 | [-2, 5.1] | 6/2/2/1 | 0.4 | 1 | true |
| `baseline` | 120 | 140 | 0 | 0.5833 | [0.5, 0.66] | 70 | 98.5 | -28.5 | [-40.2, -15.1] | 70/50/20/0 | 2.1 | 4 | false |
| `cards.risk_cap` | 29 | 40 | 1 | 0.5862 | [0.4, 0.76] | 17 | 22.2 | -5.2 | [-11, 1.4] | 17/12/7/3 | 0.95 | 2 | false |
| `cards.risk_cap_fill` | 26 | 40 | 2 | 0.6923 | [0.5, 0.86] | 18 | 13.1 | 4.9 | [-1.2, 10.3] | 18/8/8/4 | 0.6 | 1 | false |
| `cards.invalidated` | 6 | 9 | 1 | 0.8333 | [0.5, 1] | 5 | 1.9 | 3.1 | [0.2, 5] | 5/1/2/0 | 0.4 | 1 | true |
| `cards.expired` | 2 | 3 | 0 | 0.5 | [0, 1] | 1 | 2.3 | -1.3 | [-2.3, 1] | 1/1/0/1 | 0 | 0 | true |
| `cards.other` | 0 | 2 | 0 | null | null | 0 | 0 | 0 | null | 0/0/0/2 | 0 | 0 | true |
| `splits.origin.regular` | 30 | 42 | 2 | 0.6 | [0.42, 0.77] | 18 | 22.1 | -4.1 | [-9.8, 1.6] | 18/12/8/2 | 1.1 | 2 | false |
| `splits.origin.next_session` | 7 | 10 | 0 | 0.7143 | [0.29, 1] | 5 | 4.3 | 0.7 | [-3, 4] | 5/2/1/2 | 0.25 | 1 | true |
| `splits.direction.long` | 33 | 46 | 2 | 0.6061 | [0.44, 0.77] | 20 | 24.2 | -4.2 | [-9.9, 1.5] | 20/13/8/3 | 1.2 | 3 | false |
| `splits.direction.short` | 4 | 6 | 0 | 0.75 | [0.25, 1] | 3 | 2.2 | 0.8 | [-2.2, 3] | 3/1/1/1 | 0.15 | 0 | true |
| `splits.horizon['4w']` | 25 | 35 | 1 | 0.64 | [0.44, 0.84] | 16 | 17.3 | -1.3 | [-6.5, 3.9] | 16/9/6/3 | 0.9 | 2 | false |
| `splits.horizon['2m']` | 12 | 17 | 1 | 0.5833 | [0.3, 0.86] | 7 | 9.1 | -2.1 | [-6, 1.8] | 7/5/3/1 | 0.45 | 1 | false |

Top level: `generated_at: '2026-10-23T09:00:00+00:00'`, `data_as_of: '2026-10-22'`, `caption: 'Hypothetical replay, before commissions, slippage and tax'`, `risk_cap_label: 'Outcome of the skipped setup, unaffordable at the cap'`, `tp1_note: 'A TP1 hit counts the full target R with no partial exit; the bot does not bank winners in full.'`, `small_n_threshold: 10`, `window: { first: '2026-07-27', last: '2026-10-22' }`, `rule_changes: [{ date: '2026-09-28', label: 'v104 structural stops and stop-ceiling scope' }]`, `out_of_scope: { manual: 1 }`.

`rows`: six, newest first (more than five, so the table pages; any card filter leaves five or fewer):

| # | plan_id | ticker | strategy | horizon_key | direction | origin | reason | raw_reason | cancel_date | entry_model | entry_source | entry | stop | tp1 | badge | stop_ceiling_pct | cap_size_pct | outcome | r | tie | exit_date | excluded |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `P-AAPL` | AAPL | EMA20 | 4w | long | regular | risk_cap | risk_cap | 2026-10-20 | trigger | null | 100 | 94 | 111 | VALIDATED | 6 | 72.5 | right | -1 | true | 2026-10-21 | null |
| 2 | `P-AAPL` | AAPL | EMA20 | 4w | long | regular | risk_cap | risk_cap | 2026-10-20 | cancel_fill | estimated | 102.5 | 94 | 111 | VALIDATED | 6 | 72.5 | wrong | 1 | false | 2026-10-22 | null |
| 3 | `P-MSFT` | MSFT | RSI | 2m | long | regular | invalidated | invalidated | 2026-10-14 | trigger | null | 400 | 390 | 421 | WEAK | 6 | null | wrong | 2.1 | false | 2026-10-17 | null |
| 4 | `P-NVDA` | NVDA | EMA20 | 4w | long | regular | expired | expired | 2026-10-10 | trigger | null | 180 | 172 | 196 | VALIDATED | 6 | null | unresolved | 0.35 | false | null | null |
| 5 | `P-TSLA` | TSLA | Fibonacci | 4w | short | next_session | invalidated | invalidated | 2026-09-30 | trigger | null | 250 | 262 | 226 | WEAK | 6 | null | untriggered_after_cancel | null | false | null | null |
| 6 | `P-XOM` | XOM | RSI | 2m | long | regular | other | never_triggered | 2026-09-02 | trigger | null | 110 | 105 | 120 | null | null | null | null | null | false | null | split_guard |

`EMPTY_CANCEL_PAYLOAD`: the same top-level copy, `data_as_of: null`, `window: { first: null, last: null }`, `rule_changes: []`, `out_of_scope: { manual: 0 }`, every figure `fig()`, `splits: { origin: {}, direction: {}, horizon: {} }`, `rows: []`.

- [ ] **Step 4: Write the failing helper tests `frontend/src/app/workspaces/cancels/cancels.helpers.spec.ts`**

```ts
import { describe, expect, it } from 'vitest';

import { CancelPlanRow } from '../../api/models';
import { CancelFilter, NO_FILTER } from '../../stores/cancels.store';
import { CANCEL_PAYLOAD, fig } from '../../testing/cancel-fixtures';
import { ciText, figureText, filterRows, rText, verdictLabel } from './cancels.helpers';

const ROWS = CANCEL_PAYLOAD.rows;
const ids = (rows: CancelPlanRow[]): string[] => rows.map((r) => `${r.ticker}:${r.entry_model}`);
const only = (over: Partial<CancelFilter>): CancelFilter => ({ ...NO_FILTER, ...over });
const row = (i: number, over: Partial<CancelPlanRow> = {}): CancelPlanRow => ({ ...ROWS[i], ...over });

describe('figureText', () => {
  it('prints precision as a whole percent of N', () => {
    expect(figureText(fig({ n: 37, precision: 0.6216 }))).toBe('62% of 37');
    expect(figureText(fig({ n: 3, precision: 1 }))).toBe('100% of 3');
  });
  it('prints a dash when there is no precision, never 0%', () => {
    expect(figureText(fig())).toBe('— of 0');
  });
});

describe('ciText', () => {
  it('prints the 95% interval in whole percent', () => {
    expect(ciText([0.45, 0.78])).toBe('95% CI 45–78%');
  });
  it('prints a dash without an interval', () => {
    expect(ciText(null)).toBe('95% CI —');
  });
});

describe('rText', () => {
  it('signs and fixes R to two places', () => {
    expect(rText(1.85)).toBe('+1.85R');
    expect(rText(-3.4)).toBe('-3.40R');
    expect(rText(0)).toBe('0.00R');
  });
  it('prints a dash for a missing R', () => {
    expect(rText(null)).toBe('—');
  });
});

describe('verdictLabel', () => {
  it('names an invalidated or expired verdict a right or wrong cancel', () => {
    expect(verdictLabel(row(2))).toBe('Wrong cancel');
    expect(verdictLabel(row(2, { outcome: 'right' }))).toBe('Right cancel');
    expect(verdictLabel(row(3))).toBe('Unresolved');
    expect(verdictLabel(row(4))).toBe('Untriggered after cancel');
  });
  it('never calls a risk_cap verdict a wrong cancel', () => {
    expect(verdictLabel(row(1))).toBe('Setup reached TP1');
    expect(verdictLabel(row(0, { tie: false }))).toBe('Setup lost');
    expect(verdictLabel(row(1))).not.toContain('cancel');
  });
  it('marks a verdict decided by a same-bar tie', () => {
    expect(verdictLabel(row(0))).toBe('Setup lost (tie)');
  });
  it('names the exclusion on an excluded row', () => {
    expect(verdictLabel(row(5))).toBe('Excluded: split in window');
    expect(verdictLabel(row(5, { excluded: 'no_cancel_entry' }))).toBe('Excluded: no cancel-day bar');
    expect(verdictLabel(row(5, { excluded: 'something_new' }))).toBe('Excluded: something_new');
  });
});

describe('filterRows', () => {
  it('returns every row, in order, with no filter', () => {
    expect(ids(filterRows(ROWS, NO_FILTER))).toEqual([
      'AAPL:trigger', 'AAPL:cancel_fill', 'MSFT:trigger', 'NVDA:trigger', 'TSLA:trigger', 'XOM:trigger',
    ]);
  });
  it('keeps the two risk_cap entry models apart', () => {
    expect(ids(filterRows(ROWS, only({ card: 'risk_cap' })))).toEqual(['AAPL:trigger']);
    expect(ids(filterRows(ROWS, only({ card: 'risk_cap_fill' })))).toEqual(['AAPL:cancel_fill']);
    expect(ids(filterRows(ROWS, only({ card: 'other' })))).toEqual(['XOM:trigger']);
  });
  it('narrows an outcome or split with no card to the headline population', () => {
    // AAPL's crossing-price row is wrong too, but it is not in the headline.
    expect(ids(filterRows(ROWS, only({ outcome: 'wrong' })))).toEqual(['MSFT:trigger']);
    expect(ids(filterRows(ROWS, only({ split: { dim: 'origin', value: 'next_session' } })))).toEqual(['TSLA:trigger']);
    expect(ids(filterRows(ROWS, only({ split: { dim: 'horizon', value: '2m' } })))).toEqual(['MSFT:trigger']);
  });
  it('combines card, outcome and split', () => {
    expect(ids(filterRows(ROWS, only({ card: 'invalidated', outcome: 'wrong' })))).toEqual(['MSFT:trigger']);
    expect(ids(filterRows(ROWS, only({ outcome: 'right', split: { dim: 'direction', value: 'long' } }))))
      .toEqual(['AAPL:trigger']);
    expect(filterRows(ROWS, only({ card: 'expired', outcome: 'wrong' }))).toEqual([]);
  });
  it('never mutates its input', () => {
    const copy = [...ROWS];
    filterRows(ROWS, only({ card: 'risk_cap' }));
    expect(ROWS).toEqual(copy);
  });
  it('handles an empty book', () => {
    expect(filterRows([], only({ outcome: 'right' }))).toEqual([]);
  });
});
```

- [ ] **Step 5: Write the failing store tests `frontend/src/app/stores/cancels.store.spec.ts`**

Providers as `workspaces/reports/gates-tab.spec.ts`: `provideZonelessChangeDetection()`, `provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor]))`, `provideHttpClientTesting()`. The store is `providedIn: 'root'`, so `TestBed.resetTestingModule()` plus `configureTestingModule` in a `beforeEach` gives each test a fresh one. Key lists, pinned against the index § Contracts:

```ts
const keys = (value: object): string[] => Object.keys(value).sort();
// What `cancel_precision.precision_payload` emits (index § Contracts). A fixture
// that drifts from the wire fails here, before a screen spec passes against it.
const PAYLOAD_KEYS = ['baseline', 'caption', 'cards', 'data_as_of', 'generated_at', 'headline',
  'out_of_scope', 'risk_cap_label', 'rows', 'rule_changes', 'small_n_threshold', 'splits', 'tp1_note', 'window'];
const FIGURE_KEYS = ['counts', 'excluded', 'n', 'net_r', 'net_r_ci', 'precision', 'precision_ci',
  'r_avoided', 'r_missed', 'small_n', 'ties', 'total', 'unresolved_r'];
const ROW_KEYS = ['badge', 'cancel_date', 'cap_size_pct', 'direction', 'entry', 'entry_model', 'entry_source',
  'excluded', 'exit_date', 'horizon_key', 'origin', 'outcome', 'plan_id', 'r', 'raw_reason', 'reason',
  'stop', 'stop_ceiling_pct', 'strategy', 'ticker', 'tie', 'tp1'];
```

Tests (name: assertions):
- `fixtures carry the v188 wire shape`: `keys(CANCEL_PAYLOAD)` and `keys(EMPTY_CANCEL_PAYLOAD)` equal `PAYLOAD_KEYS`; every figure in `headline`, `baseline`, `cards` and every split of `CANCEL_PAYLOAD` has `FIGURE_KEYS`, and its `counts` has exactly `['right', 'unresolved', 'untriggered_after_cancel', 'wrong']`; every row has `ROW_KEYS`; `keys(CANCEL_PAYLOAD.cards)` equals `['expired', 'invalidated', 'other', 'risk_cap', 'risk_cap_fill']`.
- `loads the payload once from /api/v1/cancel-precision`: `CANCELS_URL === '/api/v1/cancel-precision'`; `store.load().subscribe()`; `loading()` is true before the flush; `http.expectOne(CANCELS_URL)` has `request.method === 'GET'`; after `flush(CANCEL_PAYLOAD)`: `data()` equals the payload, `loading()` false, `error()` null, `rows().length` 6; `http.verify()` passes.
- `keeps the figures on screen when a reload fails`: load and flush `CANCEL_PAYLOAD`, then `store.load().subscribe({ error: () => undefined })` and flush `{ error: { code: 'internal', message: 'boom' } }` with `{ status: 500, statusText: 'Server Error' }`; `data()` is still the payload, `error()` is a non-empty string, `loading()` false.
- `toggles a card, an outcome and a split`: `pickCard('risk_cap')` gives `filter().card === 'risk_cap'`, again gives null; `pickCard('expired')` then `pickCard('invalidated')` gives `'invalidated'`; `pickOutcome('wrong')` twice gives null; `pickSplit({ dim: 'origin', value: 'regular' })` then a new object `{ dim: 'origin', value: 'regular' }` gives null; `{ dim: 'origin', value: 'regular' }` then `{ dim: 'origin', value: 'next_session' }` gives the second; `pickCard(null)` clears the card and leaves outcome and split.
- `filters rows through filterRows`: after the load, `pickCard('risk_cap_fill')` gives `rows().map((r) => r.entry_model)` equal to `['cancel_fill']`; `clearFilter()` gives `filter()` equal to `NO_FILTER` and `rows().length` 6.
- `has no rows before the first load`: `rows()` equals `[]`, `data()` null, `filter()` equals `NO_FILTER`.

- [ ] **Step 6: Run both specs and watch them fail**

```bash
cd $WT/frontend && npx ng test --include src/app/workspaces/cancels/cancels.helpers.spec.ts --include src/app/stores/cancels.store.spec.ts
```
Expected: FAIL, the modules `./cancels.helpers` and `../../stores/cancels.store` do not exist yet.

- [ ] **Step 7: Implement `frontend/src/app/workspaces/cancels/cancels.helpers.ts`**

Pure, no Angular imports. `import type { CancelFilter } from '../../stores/cancels.store'` (type-only: the store imports `filterRows` from here, and a type import is erased, so there is no runtime cycle).

- `figureText(f: CancelFigure): string`: `` `${Math.round(f.precision * 100)}% of ${f.n}` ``, or `` `— of ${f.n}` `` when `precision` is null.
- `ciText(ci: [number, number] | null): string`: `'95% CI 45–78%'` (en dash, each bound `Math.round(x * 100)`), `'95% CI —'` for null. Used for precision intervals only; the summary formats R intervals with `rText`.
- `rText(r: number | null): string`: `'—'` for null; else `+` for > 0, nothing for 0, the number's own `-` for < 0, `toFixed(2)`, suffix `R` (the same output as `formatR` in `workspaces/reports/attribution-tab.ts`; not imported across workspaces).
- `verdictLabel(row: CancelPlanRow): string`, table-driven so it stays far under complexity 15:

```ts
const EXCLUDED: Record<string, string> = {
  no_bars: 'no bars', split_guard: 'split in window', bad_levels: 'bad levels',
  unknown_horizon: 'unknown horizon', no_cancel_entry: 'no cancel-day bar',
};
const CANCEL_WORDS: Record<CancelOutcome, string> = {
  right: 'Right cancel', wrong: 'Wrong cancel',
  unresolved: 'Unresolved', untriggered_after_cancel: 'Untriggered after cancel',
};
// risk_cap: the cap limits dollar risk, so a TP1 hit is the outcome of a
// skipped setup, never a mistaken cancel (spec § What risk_cap precision means).
const SETUP_WORDS: Record<CancelOutcome, string> = {
  ...CANCEL_WORDS, right: 'Setup lost', wrong: 'Setup reached TP1',
};
```
A row with `excluded` set (or a null outcome) gives `` `Excluded: ${EXCLUDED[code] ?? code}` ``; otherwise the word from `SETUP_WORDS` when `reason === 'risk_cap'`, else from `CANCEL_WORDS`, plus `' (tie)'` when `row.tie`.

- `filterRows(rows: CancelPlanRow[], f: CancelFilter): CancelPlanRow[]`: no filter at all gives `[...rows]`. Otherwise the population is the card's rows when `f.card` is set (`risk_cap_fill` = `reason 'risk_cap'` with `entry_model 'cancel_fill'`; any other card = that `reason` with `entry_model 'trigger'`), else the headline population (`reason` in `risk_cap | invalidated | expired` with `entry_model 'trigger'`); then keep `row.outcome === f.outcome` when set, and the split's field (`origin` reads `row.origin`, `direction` reads `row.direction`, `horizon` reads `row.horizon_key`) equal to `f.split.value` when set. Returns a new array.

- [ ] **Step 8: Implement `frontend/src/app/stores/cancels.store.ts`**

```ts
export const CANCELS_URL = '/api/v1/cancel-precision';
export type CancelCardKey = 'risk_cap' | 'risk_cap_fill' | 'invalidated' | 'expired' | 'other';
export interface CancelSplit { dim: 'origin' | 'direction' | 'horizon'; value: string }
export interface CancelFilter { card: CancelCardKey | null; outcome: CancelOutcome | null; split: CancelSplit | null }
export const NO_FILTER: CancelFilter = Object.freeze({ card: null, outcome: null, split: null });
```

`export const CancelsStore = signalStore({ providedIn: 'root' }, withState<CancelsSlice>({ data: null, loading: false, error: null, filter: NO_FILTER }), withComputed(({ data, filter }) => ({ rows: computed(() => filterRows(data()?.rows ?? [], filter())) })), withMethods((store, http = inject(HttpClient)) => ({ ... })))` with `CancelsSlice = { data: CancelPrecision | null; loading: boolean; error: string | null; filter: CancelFilter }`.

Root-provided on purpose: the server memoises the payload for an hour, and keeping it across visits gives stale-while-revalidate (a revisit shows the last figures while the reload runs). It uses `HttpClient` directly rather than a new `ApiClient` method, so this task never edits the shared `api/api-client.ts`; the interceptors still apply.

- `load(): Observable<CancelPrecision>`: `defer(() => { patchState(store, { loading: true, error: null }); return http.get<CancelPrecision>(CANCELS_URL); })` piped through `tap({ next: (data) => patchState(store, { data, loading: false }), error: (e) => patchState(store, { loading: false, error: messageOf(e) }) })`. It never clears `data`. `messageOf`: an `ApiError` (`../api/api-error`) with `code === 'unavailable'` gives `'The admin is not responding -- these figures may be stale.'`; any other `ApiError` gives its `message`; anything else gives `'The cancel replay could not be loaded.'`.
- `pickCard(card: CancelCardKey | null)` and `pickOutcome(o: CancelOutcome | null)`: set the key; the same non-null key again sets it to null.
- `pickSplit(s: CancelSplit | null)`: toggles off when `dim` and `value` both match the current split, otherwise replaces it.
- `clearFilter()`: `filter: NO_FILTER`.

- [ ] **Step 9: Run both specs green**

```bash
cd $WT/frontend && npx ng test --include src/app/workspaces/cancels/cancels.helpers.spec.ts --include src/app/stores/cancels.store.spec.ts
```
Expected: PASS, 0 failed.

- [ ] **Step 10: Commit**

```bash
cd $WT
git add frontend/src/app/api/models.ts frontend/src/app/testing/cancel-fixtures.ts \
  frontend/src/app/stores/cancels.store.ts frontend/src/app/stores/cancels.store.spec.ts \
  frontend/src/app/workspaces/cancels/cancels.helpers.ts frontend/src/app/workspaces/cancels/cancels.helpers.spec.ts
git commit -m "feat(ui): v188 cancel-precision types, store and helpers" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short -- frontend   # unchanged from Step 1
```

### Task V188-7: Summary — headline, baseline, reason cards, counts, splits

**Model:** sonnet — one presentational component whose DOM, copy and CSS this task pins; the judgement (labelling, equal prominence, small-N) is already made.

**Files:**
- Create: `frontend/src/app/workspaces/cancels/cancels-summary.ts`
- Create: `frontend/src/app/workspaces/cancels/cancels-summary.spec.ts`

**Interfaces:**
- Consumes: `CancelPrecision`, `CancelFigure`, `CancelOutcome` (`api/models.ts`, V188-6); `CancelCardKey`, `CancelSplit`, `CancelFilter`, `NO_FILTER` (`stores/cancels.store.ts`, V188-6); `figureText`, `ciText`, `rText` (`cancels.helpers.ts`, V188-6); `CANCEL_PAYLOAD`, `EMPTY_CANCEL_PAYLOAD`, `fig` (`testing/cancel-fixtures.ts`, V188-6); `Panel` (`ui/layout`, existing).
- Produces: `CancelsSummary`, selector `sb-cancels-summary`, `input.required<CancelPrecision>()` `data`, `input.required<CancelFilter>()` `filter`, `output<CancelCardKey | null>()` `card`, `output<CancelOutcome | null>()` `outcome`, `output<CancelSplit | null>()` `split`. It emits the key clicked; the store (V188-6) owns the toggle. V188-8 binds it.

- [ ] **Step 1: Write the failing spec `frontend/src/app/workspaces/cancels/cancels-summary.spec.ts`**

```ts
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { CancelPrecision, CancelOutcome } from '../../api/models';
import { CancelCardKey, CancelFilter, CancelSplit, NO_FILTER } from '../../stores/cancels.store';
import { CANCEL_PAYLOAD, EMPTY_CANCEL_PAYLOAD, fig } from '../../testing/cancel-fixtures';
import { CancelsSummary } from './cancels-summary';

const CAPTION = 'Hypothetical replay, before commissions, slippage and tax';

function create(data: CancelPrecision = CANCEL_PAYLOAD, filter: CancelFilter = NO_FILTER): ComponentFixture<CancelsSummary> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection(), provideHttpClient(), provideHttpClientTesting()],
  });
  const fixture = TestBed.createComponent(CancelsSummary);
  fixture.componentRef.setInput('data', data);
  fixture.componentRef.setInput('filter', filter);
  fixture.detectChanges();
  return fixture;
}

const host = (f: ComponentFixture<CancelsSummary>): HTMLElement => f.nativeElement;
const q = (f: ComponentFixture<CancelsSummary>, sel: string): HTMLElement | null => host(f).querySelector(sel);
const text = (el: Element | null): string => el?.textContent?.replace(/\s+/g, ' ').trim() ?? '';

describe('CancelsSummary', () => {
  it('puts precision and net R side by side at equal prominence, N beside both', () => {
    const f = create();
    const precision = q(f, '[data-figure="precision"]')!;
    const net = q(f, '[data-figure="net-r"]')!;
    expect(text(precision)).toContain('62% of 37');
    expect(text(precision)).toContain('N 37');
    expect(text(net)).toContain('-3.40R');
    expect(text(net)).toContain('N 37');
    expect(precision.querySelector('.value')!.className).toBe(net.querySelector('.value')!.className);
  });

  it('shows R avoided, R missed and both intervals', () => {
    const f = create();
    expect(text(q(f, '[data-figure="net-r"]'))).toContain('R avoided +23.00R · R missed -26.40R');
    expect(text(q(f, '[data-figure="precision"]'))).toContain('95% CI 45–78%');
    expect(text(q(f, '[data-figure="net-r"]'))).toContain('95% CI [-9.10R, +2.30R]');
  });

  it('carries the hypothetical-replay caption on the headline and on the cards', () => {
    const f = create();
    expect(text(q(f, '.headline-block .caption'))).toBe(CAPTION);
    expect(text(q(f, '.cards-block .caption'))).toBe(CAPTION);
  });

  it('says how many cancels reach the precision N, and how many verdicts were ties', () => {
    const f = create();
    expect(text(q(f, '.survival'))).toBe(
      '37 of 52 cancels reach the precision N: 9 unresolved (MTM +1.35R), 4 untriggered after cancel, 2 excluded.');
    expect(text(q(f, '.ties'))).toBe('3 verdicts decided by a same-bar stop and TP1 touch, counted as the stop.');
  });

  it('marks every figure under N 10, and only those', () => {
    const f = create();
    expect(text(q(f, '[data-card="expired"] .small-n'))).toBe('N < 10');
    expect(q(f, '[data-card="invalidated"] .small-n')).not.toBeNull();
    expect(q(f, '[data-card="other"] .small-n')).not.toBeNull();
    expect(q(f, '.without-risk-cap .small-n')).not.toBeNull();
    expect(q(f, '[data-split="origin:next_session"] .small-n')).not.toBeNull();
    expect(q(f, '[data-split="direction:short"] .small-n')).not.toBeNull();
    expect(q(f, '[data-card="risk_cap"] .small-n')).toBeNull();
    expect(q(f, '[data-card="risk_cap_fill"] .small-n')).toBeNull();
    expect(q(f, '[data-figure="precision"] .small-n')).toBeNull();
    expect(q(f, '.baseline .small-n')).toBeNull();
    expect(q(f, '[data-split="origin:regular"] .small-n')).toBeNull();
  });

  it('labels risk_cap a skipped setup and keeps both entry models together', () => {
    const f = create();
    const pair = q(f, '.pair')!;
    expect(pair.querySelector('[data-card="risk_cap"]')).not.toBeNull();
    expect(pair.querySelector('[data-card="risk_cap_fill"]')).not.toBeNull();
    expect(text(pair)).toContain('Outcome of the skipped setup, unaffordable at the cap');
    expect(text(pair)).not.toMatch(/wrong cancel/i);
    expect(text(q(f, '[data-card="risk_cap_fill"]'))).toContain('recorded 0 · estimated 1');
  });

  it('shows the baseline stop-first rate of filled plans', () => {
    const f = create();
    const baseline = text(q(f, '.baseline'));
    expect(baseline).toContain('Filled plans, same window, strategy and horizon');
    expect(baseline).toContain('stop first 58% of 120');
    expect(baseline).toContain('95% CI 50–66%');
  });

  it('stamps the data date, the window, the rule changes and the manual count', () => {
    const f = create();
    expect(text(q(f, '.as-of'))).toBe('Bars as of 2026-10-22 · cancels 2026-07-27 to 2026-10-22');
    const changes = host(f).querySelectorAll('.rule-changes li');
    expect(changes.length).toBe(1);
    expect(text(changes[0])).toBe('2026-09-28 v104 structural stops and stop-ceiling scope');
    expect(text(q(f, '.manual'))).toBe('Manual cancels are your decisions and stay out of every figure: 1.');
  });

  it('emits the card, outcome or split that was clicked', () => {
    const f = create();
    const cards: (CancelCardKey | null)[] = [];
    const outcomes: (CancelOutcome | null)[] = [];
    const splits: (CancelSplit | null)[] = [];
    f.componentInstance.card.subscribe((v) => cards.push(v));
    f.componentInstance.outcome.subscribe((v) => outcomes.push(v));
    f.componentInstance.split.subscribe((v) => splits.push(v));
    q(f, '[data-card="risk_cap"]')!.click();
    q(f, '[data-outcome="wrong"]')!.click();
    q(f, '[data-split="origin:next_session"]')!.click();
    expect(cards).toEqual(['risk_cap']);
    expect(outcomes).toEqual(['wrong']);
    expect(splits).toEqual([{ dim: 'origin', value: 'next_session' }]);
  });

  it('reads the headline counts with no card, in cancel words', () => {
    const f = create();
    expect(text(q(f, '.counts-head'))).toBe('All three reasons, trigger entry');
    expect(text(q(f, '[data-outcome="right"]'))).toBe('Right cancels 23 +23.00R avoided');
    expect(text(q(f, '[data-outcome="wrong"]'))).toBe('Wrong cancels 14 -26.40R missed');
    expect(text(q(f, '[data-outcome="unresolved"]'))).toBe('Unresolved 9 MTM +1.35R');
    expect(text(q(f, '[data-outcome="untriggered_after_cancel"]'))).toBe('Untriggered after cancel 4 no R');
  });

  it("switches the counts to the picked card's figure and words, and presses that card", () => {
    const f = create(CANCEL_PAYLOAD, { ...NO_FILTER, card: 'risk_cap', outcome: 'right' });
    expect(text(q(f, '.counts-head'))).toBe('risk_cap · from the trigger');
    expect(text(q(f, '[data-outcome="right"]'))).toBe('Setup lost 17 +17.00R avoided');
    expect(text(q(f, '[data-outcome="wrong"]'))).toBe('Setup reached TP1 12 -22.20R missed');
    expect(q(f, '[data-card="risk_cap"]')!.getAttribute('aria-pressed')).toBe('true');
    expect(q(f, '[data-card="invalidated"]')!.getAttribute('aria-pressed')).toBe('false');
    expect(q(f, '[data-outcome="right"]')!.getAttribute('aria-pressed')).toBe('true');
    expect(q(f, '.counts .small-n')).toBeNull();
  });

  it('presses the picked split row', () => {
    const f = create(CANCEL_PAYLOAD, { ...NO_FILTER, split: { dim: 'horizon', value: '2m' } });
    expect(q(f, '[data-split="horizon:2m"]')!.getAttribute('aria-pressed')).toBe('true');
    expect(q(f, '[data-split="horizon:4w"]')!.getAttribute('aria-pressed')).toBe('false');
  });

  it('states that cards pool both origins, and the full-target TP1 rule', () => {
    const f = create();
    expect(text(host(f))).toContain('Cards pool regular and next-session plans.');
    expect(text(q(f, '.tp1-note'))).toBe(CANCEL_PAYLOAD.tp1_note);
  });

  it('renders an empty book as — of 0 with the small-N marker, never an error', () => {
    const f = create(EMPTY_CANCEL_PAYLOAD);
    expect(text(q(f, '[data-figure="precision"]'))).toContain('— of 0');
    expect(q(f, '[data-figure="precision"] .small-n')).not.toBeNull();
    expect(text(q(f, '[data-figure="precision"]'))).toContain('95% CI —');
    expect(text(q(f, '.as-of'))).toBe('Bars as of — · no scored cancels');
    expect(text(q(f, '[data-outcome="right"]'))).toBe('Right cancels 0 0.00R avoided');
    expect(q(f, '.rule-changes')).toBeNull();
    expect(host(f).querySelectorAll('.split-empty').length).toBe(3);
    expect(host(f).querySelector('[role="alert"]')).toBeNull();
  });

  it('renders a book where every plan is unresolved', () => {
    const all = fig({ total: 5, counts: { right: 0, wrong: 0, unresolved: 5, untriggered_after_cancel: 0 }, unresolved_r: 0.8 });
    const f = create({ ...EMPTY_CANCEL_PAYLOAD, headline: { all, without_risk_cap: all } });
    expect(text(q(f, '[data-figure="precision"]'))).toContain('— of 0');
    expect(text(q(f, '[data-outcome="unresolved"]'))).toBe('Unresolved 5 MTM +0.80R');
    expect(text(q(f, '.survival'))).toBe(
      '0 of 5 cancels reach the precision N: 5 unresolved (MTM +0.80R), 0 untriggered after cancel, 0 excluded.');
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd $WT/frontend && npx ng test --include src/app/workspaces/cancels/cancels-summary.spec.ts
```
Expected: FAIL, `./cancels-summary` does not exist.

- [ ] **Step 3: Implement `CancelsSummary` in `frontend/src/app/workspaces/cancels/cancels-summary.ts`**

`@Component({ selector: 'sb-cancels-summary', changeDetection: ChangeDetectionStrategy.OnPush, imports: [Panel] })`, inputs and outputs as in **Interfaces**. Renders and decides nothing beyond which server figure to show; every number comes from `data()`. The only client-side count is the crossing-price card's `recorded N · estimated M`, a tally of `entry_source` over the `cancel_fill` rows (a label count, not a statistic).

Constants in the file:

```ts
const CARDS: readonly { key: CancelCardKey; title: string; note: string | null }[] = [
  { key: 'risk_cap', title: 'risk_cap · from the trigger', note: null },
  { key: 'risk_cap_fill', title: 'risk_cap · from the crossing price', note: null },
  { key: 'invalidated', title: 'invalidated', note: null },
  { key: 'expired', title: 'expired', note: null },
  { key: 'other', title: 'other', note: 'not in the headline' },
];
const OUTCOMES: readonly CancelOutcome[] = ['right', 'wrong', 'unresolved', 'untriggered_after_cancel'];
const CANCEL_WORDS: Record<CancelOutcome, string> = {
  right: 'Right cancels', wrong: 'Wrong cancels',
  unresolved: 'Unresolved', untriggered_after_cancel: 'Untriggered after cancel',
};
const SETUP_WORDS: Record<CancelOutcome, string> = { ...CANCEL_WORDS, right: 'Setup lost', wrong: 'Setup reached TP1' };
const SPLIT_DIMS: readonly { dim: CancelSplit['dim']; title: string }[] = [
  { dim: 'origin', title: 'Origin' }, { dim: 'direction', title: 'Direction' }, { dim: 'horizon', title: 'Horizon' },
];
const SPLIT_LABEL: Record<string, string> = { regular: 'Regular', next_session: 'Next session', long: 'Long', short: 'Short' };
```

Computed signals: `active = computed(() => { const c = filter().card; return c ? data().cards[c] : data().headline.all; })`, `activeTitle` (the card's `title`, or `'All three reasons, trigger entry'`), `words` (`SETUP_WORDS` when the card is `risk_cap` or `risk_cap_fill`, else `CANCEL_WORDS`), `fillSources` (`recorded ${r} · estimated ${e}` over `data().rows` with `entry_model === 'cancel_fill'`), `splitGroups` (for each `SPLIT_DIMS` entry, `Object.entries(data().splits[dim])` as `{ key, label: SPLIT_LABEL[key] ?? key, figure }`). Methods: `countR(o: CancelOutcome, f: CancelFigure): string` (right `` `${rText(f.r_avoided)} avoided` ``, wrong `` `${rText(-f.r_missed)} missed` ``, unresolved `` `MTM ${rText(f.unresolved_r)}` ``, untriggered `'no R'`), `rCi(ci)` (`'95% CI —'` or `` `95% CI [${rText(lo)}, ${rText(hi)}]` ``), `isSplit(dim, key)`.

Template, in this order (class names and `data-*` attributes are what the spec reads):

1. `<sb-panel heading="Were the bot's cancels right?">` wrapping `.headline-block`:
   - `.headline` holding two `.figure` blocks: `[data-figure="precision"]` (label "Precision", `.value` = `figureText(all)`, `.n` = `N {{ all.n }}`, the marker, `ciText(all.precision_ci)`) and `[data-figure="net-r"]` (label "Net R", `.value` = `rText(all.net_r)`, `.n`, the marker, `rCi(all.net_r_ci)`, and `R avoided {{ rText(all.r_avoided) }} · R missed {{ rText(-all.r_missed) }}`). Both `.value` elements carry exactly `class="value num"`: equal prominence is the same class, which the spec checks.
   - `<p class="caption">{{ data().caption }}</p>`.
   - `<p class="survival">`: `{n} of {total} cancels reach the precision N: {unresolved} unresolved (MTM {rText(unresolved_r)}), {untriggered} untriggered after cancel, {excluded} excluded.`
   - `<p class="ties">`: `{ties} verdicts decided by a same-bar stop and TP1 touch, counted as the stop.`
   - `<p class="without-risk-cap">`: `Without risk_cap: {figureText} · net {rText(net_r)}` plus the marker.
   - `<p class="baseline">`: `Filled plans, same window, strategy and horizon: stop first {figureText(baseline)} · {ciText(baseline.precision_ci)}` plus the marker.
   - `<p class="as-of">`: `Bars as of {data_as_of ?? '—'} · ` then `cancels {first} to {last}` when `window.first` is set, else `no scored cancels`.
   - `@if (data().rule_changes.length)` a `<div class="rule-changes">` with the line "Rules changed inside this window, so a pooled figure spans more than one rule:" and a `<ul>` of `<li>{{ date }} {{ label }}</li>`.
   - `<p class="manual">Manual cancels are your decisions and stay out of every figure: {{ data().out_of_scope.manual }}.</p>`
2. `<sb-panel heading="By cancel reason">` wrapping `.cards-block`: `.cards` grid; the first two `CARDS` inside `<div class="pair">` headed by `<p class="pair-label">{{ data().risk_cap_label }}</p>`, the other three directly in `.cards`. Each card is `<button type="button" class="card" [attr.data-card]="key" [attr.aria-pressed]="filter().card === key" (click)="card.emit(key)">` with the title, `figureText`, `N {{ n }}`, `net {{ rText(net_r) }}`, `ciText`, the marker, the `note` when set, and on `risk_cap_fill` the `fillSources()` line. Then `<p class="note">Cards pool regular and next-session plans.</p>` and `<p class="caption">{{ data().caption }}</p>`.
3. `<sb-panel heading="Right, wrong, unresolved">` wrapping `.counts`: `<p class="counts-head">{{ activeTitle() }}</p>`, the marker for `active()`, a `.counts-row` of four `<button type="button" class="count" [attr.data-outcome]="o" [attr.aria-pressed]="filter().outcome === o" (click)="outcome.emit(o)">` each `<span class="word">{{ words()[o] }}</span> <span class="num">{{ active().counts[o] }}</span> <span class="r num">{{ countR(o, active()) }}</span>`, then `<p class="tp1-note">{{ data().tp1_note }}</p>`.
4. `<sb-panel heading="Splits">` wrapping `.splits`: one `<section class="split-group">` per `splitGroups()` entry with its title, then per key `<button type="button" class="split-row" [attr.data-split]="dim + ':' + key" [attr.aria-pressed]="isSplit(dim, key)" (click)="split.emit({ dim, value: key })">` holding the label, `figureText`, `net {{ rText(net_r) }}` and the marker; a group with no keys shows `<p class="split-empty">No rows yet.</p>`.

The small-N marker, everywhere: `@if (fig.small_n) { <span class="small-n" title="Fewer than {{ data().small_n_threshold }} resolved plans: an anecdote, not a rate">N &lt; {{ data().small_n_threshold }}</span> }`. On `.counts` it reads `active().small_n`, so a filtered view's figure is marked too.

Styles (exact; the three device classes of the part header § Screen design, item 7):

```css
:host { display: grid; gap: var(--space-14); container-type: inline-size; container-name: cancels; }
.headline, .cards, .splits, .pair { display: grid; gap: var(--space-10); grid-template-columns: minmax(0, 1fr); }
.counts-row { display: grid; gap: var(--space-8); grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
.figure { display: grid; gap: var(--space-4); align-content: start; }
.figure-line { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-8); }
.value { font-size: var(--text-hero); line-height: 1.1; }
.num { font-family: var(--font-num); }
.card, .count, .split-row {
  min-height: var(--control-h); display: grid; gap: var(--space-4); align-content: start;
  padding: var(--space-8) var(--space-10); text-align: left; font: inherit; color: inherit;
  background: var(--surface-raised); border: 1px solid var(--border); border-radius: var(--radius-sm); cursor: pointer;
}
.card[aria-pressed='true'], .count[aria-pressed='true'], .split-row[aria-pressed='true'] {
  border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent);
}
.small-n { color: var(--warn); font-size: var(--text-micro); }
.caption, .note, .as-of, .tp1-note, .pair-label, .survival, .ties, .manual, .split-empty {
  margin: 0; color: var(--text-faint); font-size: var(--text-micro);
}
.baseline, .without-risk-cap { margin: 0; font-size: var(--text-body); }
@container cancels (min-width: 640px) {
  .headline, .cards, .splits { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .pair { grid-column: 1 / -1; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .counts-row { grid-template-columns: none; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); }
}
@container cancels (min-width: 1024px) {
  .cards, .splits { grid-template-columns: none; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); }
  .pair { grid-column: span 2; }
}
```

Phone: one column throughout, the counts two by two. Tablet: headline, cards and splits two columns, the `risk_cap` pair one full row of two, the counts one row of four. Desktop: the pair plus the three other cards in one row, the three split groups in one row. No `repeat(<digit>`, no `::ng-deep`, no `<h1>` (all three are workspace-consistency rules). Keep every method far under complexity 15: the template's branches live in the constant tables above, not in `if` chains.

- [ ] **Step 4: Run it green, then the workspace-consistency spec**

```bash
cd $WT/frontend && npx ng test --include src/app/workspaces/cancels/cancels-summary.spec.ts
cd $WT/frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```
Expected: PASS, 0 failed, on both. The consistency spec now also reads `workspaces/cancels/cancels-summary.ts`.

- [ ] **Step 5: Commit**

```bash
cd $WT
git add frontend/src/app/workspaces/cancels/cancels-summary.ts frontend/src/app/workspaces/cancels/cancels-summary.spec.ts
git commit -m "feat(ui): v188 cancels summary -- precision beside net R, reason cards, counts, splits" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short -- frontend   # unchanged
```

### Task V188-8: Plan table, page, route, nav and SPA registration

**Model:** sonnet — declared table columns, a page that composes two components, and four one-line registrations, each pinned by a test.

**Files:**
- Create: `frontend/src/app/workspaces/cancels/cancels-table.ts`
- Create: `frontend/src/app/workspaces/cancels/cancels-table.spec.ts`
- Create: `frontend/src/app/workspaces/cancels/cancels.ts`
- Create: `frontend/src/app/workspaces/cancels/cancels.spec.ts`
- Create: `frontend/src/app/workspaces/cancels/cancels.routes.ts`
- Modify: `frontend/src/app/app.routes.ts` (one route object after `calendar`)
- Modify: `frontend/src/app/shell/shell.ts` (one REVIEW nav entry)
- Modify: `swingbot/admin/spa.py` (`WORKSPACES` gains `"cancels"`)
- Modify: `tests/admin/test_spa_serving.py` (`SPA_WORKSPACES` gains `"cancels"`)
- Modify: `frontend/scripts/layout-audit-lib.mjs` (`ROUTES` gains `'/cancels'`)
- Modify: `frontend/scripts/layout-audit-lib.test.mjs` (route count 27 to 28)

The last two are not in the index ledger's file list: `docs/claude/ui-design.md` § Checklist requires a route added to the app to join the audit's `ROUTES` in the same commit, and the audit's own test pins the count. Neither file is shared with any other task.

**Interfaces:**
- Consumes: `CancelsStore`, `CancelFilter`, `NO_FILTER`, `CANCELS_URL` (V188-6); `verdictLabel`, `rText` (V188-6); `CancelsSummary` (V188-7); `CancelPlanRow`, `CancelPrecision` (V188-6); fixtures `CANCEL_PAYLOAD`, `EMPTY_CANCEL_PAYLOAD` (V188-6). Existing: `DataTable` and `ColumnDef` (`ui/data-table/`), `Async` and `asyncInputs` (`ui/async`), `Button` (`ui/button`), `Panel` (`ui/layout`), `routeData`, `onEvents` (`routing/route-metadata`), `resolveRoute` (`routing/route-resolver`), `routeRequest`, `RouteRequestHandlers` (`routing/route-request`), `authGuard`.
- Produces: `CancelsTable` (`sb-cancels-table`, `input.required<CancelPlanRow[]>()` `rows`), `Cancels` (`sb-cancels`), `cancelsRoutes`; the route `/cancels`; `spa.WORKSPACES` contains `"cancels"`. V188-9 audits `/cancels`.

- [ ] **Step 1: Write the failing table spec `frontend/src/app/workspaces/cancels/cancels-table.spec.ts`**

Providers: `provideZonelessChangeDetection()`, `provideHttpClient()`, `provideHttpClientTesting()`, `provideRouter([])` (the table's preferences and drawer link need them). `create(rows)` sets the `rows` input with `fixture.componentRef.setInput` and runs `detectChanges()`. `bodyRows(f)` = `sb-data-table tbody tr` without `.expansion` (as `gates-tab.spec.ts`'s `cellRows`).

```ts
describe('CancelsTable', () => {
  it('lists one row per replayed cancel, a risk_cap plan twice', () => {
    const f = create(CANCEL_PAYLOAD.rows);
    expect(bodyRows(f).length).toBe(6);
    expect(text(bodyRows(f)[0])).toContain('risk_cap · trigger');
    expect(text(bodyRows(f)[0])).toContain('Setup lost (tie)');
    expect(text(bodyRows(f)[0])).toContain('-1.00R');
    expect(text(bodyRows(f)[1])).toContain('risk_cap · crossing (estimated)');
    expect(text(bodyRows(f)[1])).toContain('Setup reached TP1');
    expect(text(bodyRows(f)[1])).toContain('+1.00R');
  });

  it('shows ticker, strategy, badge tier, horizon, cancel date and cap-implied size', () => {
    const row = text(bodyRows(create(CANCEL_PAYLOAD.rows))[0]);
    for (const part of ['AAPL', 'EMA20', 'VALIDATED', '4w', '2026-10-20', '72.5%']) expect(row).toContain(part);
    expect(text(bodyRows(create(CANCEL_PAYLOAD.rows))[2])).toContain('Wrong cancel');
  });

  it('names an exclusion and shows no R for an excluded row', () => {
    const xom = text(bodyRows(create(CANCEL_PAYLOAD.rows))[5]);
    expect(xom).toContain('Excluded: split in window');
    expect(xom).toContain('other (never_triggered)');
    expect(xom).toContain('—');
    expect(xom).not.toMatch(/[+-]\d+\.\d{2}R/);
  });

  it('pages six rows and shows no pager at five or fewer', () => {
    expect(host(create(CANCEL_PAYLOAD.rows)).querySelector('sb-pagination')).not.toBeNull();
    expect(host(create(CANCEL_PAYLOAD.rows.slice(0, 5))).querySelector('sb-pagination')).toBeNull();
  });

  it('says so when the filter matches nothing', () => {
    expect(text(host(create([])))).toContain('No cancelled plans match this filter');
  });

  it('declares its phone compact row', () => {
    const cols = (create([]).componentInstance as unknown as { columns: () => ColumnDef<CancelPlanRow>[] }).columns();
    const slot = (key: string) => cols.find((c) => c.key === key)?.compact;
    expect(slot('ticker')).toEqual({ line: 1, order: 1 });
    expect(slot('verdict')).toEqual({ line: 1, order: 2 });
    expect(slot('cancel_date')).toEqual({ line: 2, order: 1 });
    expect(slot('r')).toEqual({ line: 2, order: 2 });
  });
});
```

- [ ] **Step 2: Write the failing page spec `frontend/src/app/workspaces/cancels/cancels.spec.ts`**

Providers as `gates-tab.spec.ts` plus `provideRouter([])`. `create(body, init?)`: reset and configure the module, `TestBed.createComponent(Cancels)`, then `TestBed.inject(CancelsStore).load().subscribe({ error: () => undefined })` and `TestBed.inject(HttpTestingController).expectOne(CANCELS_URL).flush(body, init)`, then `detectChanges()`. Tests:

- `renders the summary and the table from one request`: `sb-cancels-summary` present; 6 body rows in `sb-cancels-table`; `HttpTestingController.verify()` passes.
- `filters the table from a card and clears it on a second click`: click `[data-card="risk_cap"]`, `detectChanges()`: 1 body row containing `AAPL`; `.filter-line` text contains `risk_cap` and `1 of 6 rows`; click it again: 6 rows and no `.filter-line`.
- `filters from a count and from a split, and Clear filter resets both`: click `[data-outcome="wrong"]`: 1 row containing `MSFT`; click `[data-split="direction:long"]`: still that 1 row; click the `.filter-line` button whose text is `Clear filter`: 6 rows, `TestBed.inject(CancelsStore).filter()` equals `NO_FILTER`.
- `shows an empty book as figures, never as an empty state`: flush `EMPTY_CANCEL_PAYLOAD`: `[data-figure="precision"]` contains `— of 0`; the host text does not contain `Nothing to replay` (the `sb-async` empty title, which must never show); the table says `No cancelled plans match this filter`.
- `shows the error and no figures when the first load fails`: flush `{ error: { code: 'internal', message: 'boom' } }` with `{ status: 500, statusText: 'Server Error' }`: `sb-cancels-summary` is absent and `TestBed.inject(CancelsStore).error()` is a non-empty string.
- `keeps the figures when a reload fails`: after a good first load, `store.load().subscribe({ error: () => undefined })`, flush a 500, `detectChanges()`: `sb-cancels-summary` still present.

- [ ] **Step 3: Run both specs and watch them fail**

```bash
cd $WT/frontend && npx ng test --include src/app/workspaces/cancels/cancels-table.spec.ts --include src/app/workspaces/cancels/cancels.spec.ts
```
Expected: FAIL, `./cancels-table` and `./cancels` do not exist.

- [ ] **Step 4: Implement `CancelsTable` in `frontend/src/app/workspaces/cancels/cancels-table.ts`**

`@Component({ selector: 'sb-cancels-table', changeDetection: ChangeDetectionStrategy.OnPush, imports: [DataTable] })`, template:

```html
<sb-data-table [rows]="rows()" [columns]="columns()" [visible]="visible" [rowKey]="rowKey"
  clientPaging="cancels-plans" [fillPage]="false" [emptyState]="empty" />
```

- `rows = input.required<CancelPlanRow[]>()`.
- `rowKey`: `` (row) => `${row.plan_id}:${row.entry_model}` `` (a `risk_cap` plan has two rows with one `plan_id`). Excluded rows are not restyled: the verdict text already says "Excluded".
- `empty: EmptyState = { title: 'No cancelled plans match this filter', hint: 'Clear the filter, or wait for the bot to cancel a plan.' }`.
- `visible = ['ticker', 'strategy', 'badge', 'horizon', 'reason', 'cancel_date', 'verdict', 'r', 'cap_size']`.
- `protected readonly columns = computed<ColumnDef<CancelPlanRow>[]>(() => [...])`, in that order:
  - `ticker` "Ticker", `value: (r) => r.ticker`, `compact: { line: 1, order: 1 }`
  - `strategy` "Strategy", `value: (r) => r.strategy`
  - `badge` "Badge tier", `value: (r) => r.badge` (null renders an em dash)
  - `horizon` "Horizon", `value: (r) => r.horizon_key`
  - `reason` "Reason", `value: reasonText`
  - `cancel_date` "Cancelled", `value: (r) => r.cancel_date`, `compact: { line: 2, order: 1 }`
  - `verdict` "Verdict", `value: verdictLabel`, `compact: { line: 1, order: 2 }`
  - `r` "R", `numeric: true`, `value: (r) => (r.r === null ? null : rText(r.r))`, `compact: { line: 2, order: 2 }`
  - `cap_size` "Cap-implied size", `numeric: true`, `` value: (r) => (r.cap_size_pct === null ? null : `${r.cap_size_pct.toFixed(1)}%`) ``
- `reasonText(row)`: `risk_cap` with `trigger` gives `'risk_cap · trigger'`; with `cancel_fill` gives `` `risk_cap · crossing (${row.entry_source ?? 'estimated'})` ``; `other` gives `` `other (${row.raw_reason ?? 'unknown'})` ``; anything else gives `row.reason`. A lookup on `row.reason`, not an `if` chain.

Rows arrive in the server's order (newest cancel first) and the table never sorts them. Device defaults come from `clientPaging`: 10 rows per page on desktop, 5 on tablet and phone, saved per device class by the table (`ui/table-prefs.ts`); five rows or fewer shows no pager (`DataTable.MIN_PAGEABLE`). On a phone the declared compact row shows ticker and verdict, then cancel date and R; every other column is in the row drawer.

- [ ] **Step 5: Implement the page `Cancels` in `frontend/src/app/workspaces/cancels/cancels.ts`**

`@Component({ selector: 'sb-cancels', changeDetection: ChangeDetectionStrategy.OnPush, imports: [Async, Button, Panel, CancelsSummary, CancelsTable], host: { class: 'register-instrument' } })`. `protected readonly store = inject(CancelsStore)`. A file comment says: read-only; the screen shows a hypothetical replay and changes no cancel rule; the store is root-provided, so a revisit shows the last figures while the reload runs.

```html
<sb-async [loading]="async().loading" [error]="async().error" [empty]="async().empty"
  [staleAsOf]="async().staleAsOf" emptyReason="measured-zero" emptyTitle="Nothing to replay"
  shape="panel" (retry)="reload()">
  @if (store.data(); as data) {
    <sb-cancels-summary [data]="data" [filter]="store.filter()"
      (card)="store.pickCard($event)" (outcome)="store.pickOutcome($event)" (split)="store.pickSplit($event)" />
    <sb-panel heading="Cancelled plans">
      @if (filterText(); as label) {
        <p class="filter-line" role="status">
          Showing {{ label }} · {{ store.rows().length }} of {{ data.rows.length }} rows
          <button sb-button type="button" variant="ghost" (click)="store.clearFilter()">Clear filter</button>
        </p>
      }
      <sb-cancels-table [rows]="store.rows()" />
    </sb-panel>
  }
</sb-async>
```

- `async = computed(() => asyncInputs(this.store, { isEmpty: () => false }))`: an empty book is a measured answer, shown as `— of 0` by the summary, never as an empty state (`docs/claude/known-traps.md`, empty tables are measured answers).
- `filterText = computed(() => ...)`: `''` with no filter; otherwise the picked parts joined by `' · '`: the card key, the outcome, and `` `${split.dim} ${split.value}` ``.
- `reload(): void`: `this.store.load().subscribe({ error: () => undefined })`.
- Styles: `:host { display: grid; gap: var(--space-14); }` and `.filter-line { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-8); margin: 0 0 var(--space-8); font-size: var(--text-body); }`. The `sb-button` keeps its own `min-height: var(--control-h)`, so the Clear filter target is 44px on touch.

- [ ] **Step 6: Write `frontend/src/app/workspaces/cancels/cancels.routes.ts`**

```ts
import { inject } from '@angular/core';
import { Routes } from '@angular/router';

import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { RouteRequestHandlers, routeRequest } from '../../routing/route-request';
import { CancelsStore } from '../../stores/cancels.store';

/** The store records loading, data and error itself; routeRequest only keeps
 *  a non-auth failure from failing the navigation, so the page renders its
 *  error. */
const STORE_OWNS_STATE: RouteRequestHandlers<unknown> = {
  start: () => undefined, next: () => undefined, error: () => undefined,
};

/** No server event refreshes this page. Each visit reloads; the server
 *  memoises the replay until the next plan write or the next UTC hour. */
export const cancelsRoutes: Routes = [{
  path: '',
  runGuardsAndResolvers: 'always',
  data: routeData('Cancels', onEvents()),
  resolve: { ready: resolveRoute(() => routeRequest(inject(CancelsStore).load(), STORE_OWNS_STATE)) },
  loadComponent: () => import('./cancels').then((m) => m.Cancels),
}];
```

- [ ] **Step 7: Register the route, the nav entry and the server workspace**

`frontend/src/app/app.routes.ts`, after the `calendar` object:

```ts
  {
    path: 'cancels',
    canMatch: [authGuard],
    title: 'Cancels',
    data: { subtitle: "Were the bot's own cancels right?" },
    loadChildren: () => import('./workspaces/cancels/cancels.routes').then((m) => m.cancelsRoutes),
  },
```

`frontend/src/app/shell/shell.ts`, in the `nav-review` entries after `/reports`: `{ path: '/cancels', label: 'Cancels', icon: 'cancelled' },` (the `cancelled` icon already exists in `ui/icon.ts`).

`swingbot/admin/spa.py`: `WORKSPACES` gains `"cancels"` after `"reports"`. `tests/admin/test_spa_serving.py`: `SPA_WORKSPACES` gains `"cancels"`, so `/cancels` is served on reload; `test_every_angular_route_is_served_on_reload` already parses `app.routes.ts` and fails without the `spa.py` change.

`frontend/scripts/layout-audit-lib.mjs`: `ROUTES` gains `'/cancels'` after `'/reports', '/reports?tab=gates',`. `frontend/scripts/layout-audit-lib.test.mjs`: the test `'ROUTES visits every route and tab once (spec §2: 27)'` becomes `'... (spec §2 plus v188 /cancels: 28)'` with `assert.equal(ROUTES.length, 28)`, plus `assert.ok(ROUTES.includes('/cancels'))`.

- [ ] **Step 8: Run everything this task touched, green**

```bash
cd $WT/frontend && npx ng test --include src/app/workspaces/cancels/cancels-table.spec.ts --include src/app/workspaces/cancels/cancels.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/shell/shell.spec.ts
cd $WT/frontend && node --test scripts/layout-audit-lib.test.mjs
cd $WT && python scripts/dev/testrun.py file tests/admin/test_spa_serving.py
cd $WT/frontend && npx ng build
```
Expected: every spec PASS, 0 failed; `node --test` 0 failures; the spa file 0 failed (the `built` cases may skip when no build is present, which is not a failure); `ng build` completes with no error (strict template type-checking of the new components).

- [ ] **Step 9: Commit**

```bash
cd $WT
git add frontend/src/app/workspaces/cancels/cancels-table.ts frontend/src/app/workspaces/cancels/cancels-table.spec.ts \
  frontend/src/app/workspaces/cancels/cancels.ts frontend/src/app/workspaces/cancels/cancels.spec.ts \
  frontend/src/app/workspaces/cancels/cancels.routes.ts frontend/src/app/app.routes.ts frontend/src/app/shell/shell.ts \
  frontend/scripts/layout-audit-lib.mjs frontend/scripts/layout-audit-lib.test.mjs
git commit -m "feat(ui): v188 Cancels workspace -- plan table, page, route and nav" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git add swingbot/admin/spa.py tests/admin/test_spa_serving.py
git commit -m "feat(admin): serve /cancels on reload (v188)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short -- frontend   # unchanged
```

# Phase 4 — Verification and merge

### Task V188-9: Full suites, complexity gate, production-replica count check, merge

**Model:** sonnet — runs fixed commands, compares counts and merges; a red result goes back to its owning task, never patched here by guesswork.

**Files:**
- none created or modified by design. A failure found here is fixed in the file of the task that owns it, re-run alone (`testrun.py file …` or `npx ng test --include …`), and committed as a scoped fix on the branch. The merge commit body records the build-time counts.

**Interfaces:**
- Consumes: every symbol of V188-1..V188-8; the endpoint `GET /api/v1/cancel-precision`; `PlanStore().records()` (`swingbot/core/planning/plan_store.py`); the admin `app` (`swingbot/admin/app.py:74`).
- Produces: branch `2026-10-23-v188-cancelled-plan-precision` merged into `main`; the build-time reason counts and headline figures in the merge commit body. After it the controller runs `/panel staff-engineer,quant-researcher,financial-advisor` and `/close-out` on `main` (ui patch + bot patch, `version_history.json`).

- [ ] **Step 1: Bring the branch up to date with `main` and confirm both trees**

```bash
cd $WT
git status --short                                   # empty: every task committed
git log --oneline main..HEAD                         # the V188-1..V188-8 commits
git merge main                                       # test the merged state; resolve only conflicts in this branch's own files
git -C E:/Documents/Private/Projects/Discord-Bot status --short   # another session's edits: note them, never touch them
```
If `git merge main` conflicts in a file this plan did not create or list, stop and hand the conflict to the controller.

- [ ] **Step 2: Sync the production data into the local replica**

Run `/replicate-prod-db` (Skill tool, `replicate-prod-db`) before the first database-backed run. Expected: the skill reports matching row counts for `plans`.

- [ ] **Step 3: Full Python suite, once, through the `test-runner` agent**

Dispatch the `test-runner` subagent with: "In `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-23-v188-cancelled-plan-precision`, run `python scripts/dev/testrun.py full` and report the pass/fail/xfail counts and any failing test ids." Expected: `0 failed`, `0 xfailed` (a changed pass count is not a failure, `docs/claude/testing-cost.md`). `testrun.py full` also runs `scripts/dev/complexity_gate.py` against `complexity_baseline.json`. A failure is fixed in its owning task's file and re-run alone with `python scripts/dev/testrun.py file <test>`; the full suite is not re-run for it.

- [ ] **Step 4: Complexity gate on its own, so its verdict is in this task's record**

```bash
cd $WT && python scripts/dev/complexity_gate.py
```
Expected: exit 0, no function at complexity >= 15 in `cancel_replay.py`, `cancel_rows.py`, `cancel_precision.py`, `api_v1/cancel_precision.py`, and `PlanManager._step_pending` no worse than its baseline. Never run `--update` to pass.

- [ ] **Step 5: Full frontend suite and the audit-library test**

```bash
cd $WT/frontend && npx ng test --watch=false
cd $WT/frontend && node --test scripts/layout-audit-lib.test.mjs
cd $WT/frontend && npm run build
```
Expected: vitest `0 failed`; `node --test` 0 failures; the build completes and writes `swingbot/admin/static/app/`.

- [ ] **Step 6: Re-derive the reason counts on the replica and compare them with the screen**

Write the script to the session scratchpad (never into the repo) and run it from `$WT`. It reads `.env` for the admin login inside the script and never prints, logs or echoes a value from it. The counts are recomputed here from `status_history`, independently of `cancel_rows`, and checked against what the route serves:

```python
"""v188 V188-9: re-derive the cancel reason counts and check the screen's."""
from collections import Counter

from dotenv import dotenv_values

from swingbot.admin.app import app
from swingbot.core.planning.plan_store import PlanStore

REASONS = ("risk_cap", "invalidated", "expired")


def last_cancel_reason(record: dict) -> str | None:
    for entry in reversed(record.get("status_history") or []):
        if entry.get("status") == "CANCELLED":
            return entry.get("reason")
    return None


env = dotenv_values(".env")
client = app.test_client()
login = client.post("/api/v1/session",
                    json={"username": env["ADMIN_USERNAME"], "password": env["ADMIN_PASSWORD"]})
assert login.status_code == 200, f"login failed: {login.status_code}"
response = client.get("/api/v1/cancel-precision")
assert response.status_code == 200, response.status_code
body = response.get_json()

records = [r for r in PlanStore().records() if r.get("status") == "CANCELLED"]
reasons = Counter(last_cancel_reason(r) for r in records)
other = sum(n for code, n in reasons.items() if code not in REASONS and code != "manual")
expected = {**{code: reasons[code] for code in REASONS}, "risk_cap_fill": reasons["risk_cap"], "other": other}
served = {key: body["cards"][key]["total"] for key in expected}
print("cancelled plans:", len(records), dict(reasons))
print("expected card totals:", expected)
print("served card totals:  ", served)
print("manual:", reasons["manual"], "served:", body["out_of_scope"]["manual"])
assert served == expected, "card totals differ from the re-derived reason counts"
assert body["out_of_scope"]["manual"] == reasons["manual"]
assert body["headline"]["all"]["total"] == sum(reasons[code] for code in REASONS)
assert len(body["rows"]) == sum(reasons[code] for code in REASONS) + reasons["risk_cap"] + other
for name, fig in (("all", body["headline"]["all"]), ("without_risk_cap", body["headline"]["without_risk_cap"]),
                  ("baseline", body["baseline"])):
    print(f"{name}: n={fig['n']} total={fig['total']} precision={fig['precision']} "
          f"ci={fig['precision_ci']} net_r={fig['net_r']} counts={fig['counts']} ties={fig['ties']} small_n={fig['small_n']}")
print("data_as_of:", body["data_as_of"], "window:", body["window"], "rule_changes:", body["rule_changes"])
```

```bash
cd $WT && python "<scratchpad>/v188_count_check.py"
```
Expected: every assertion holds. Copy the printed counts and figures (no credential is in them) into the merge message in Step 8. The spec-time counts (76 / 49 / 22 / 5) are context only: a different build-time number is expected and is the number of record.

- [ ] **Step 7: Layout audit at phone, tablet and desktop widths**

Per `docs/claude/ui-design.md` § Checklist, from `$WT` with the build from Step 5 and the replica from Step 2:

```bash
cd $WT && python admin_ui.py            # run_in_background; serves http://localhost:1234
cd $WT && node frontend/scripts/browse.mjs login --base http://localhost:1234
cd $WT && node frontend/scripts/layout-audit.mjs --base http://localhost:1234
```
Expected: exit 0 at 390, 768 and 1440 for `/cancels` (overflow, off-screen, clipped, sub-44px targets on phone and tablet, sub-11px text, baseline offsets, table-cell centring). A `/cancels` finding is fixed in `cancels-summary.ts`, `cancels-table.ts` or `cancels.ts`, re-run with that file's spec, committed as a scoped fix, and the audit re-run. Never add an allow-list entry for an app control on this screen. A finding on another route that also fails on `main` before this branch is reported to the controller and left alone. Stop the background admin process afterwards.

- [ ] **Step 8: Merge into `main`**

Follow the `worktree-lifecycle` skill (Skill tool) for the merge checks. Then:

```bash
cd E:/Documents/Private/Projects/Discord-Bot
git status --short       # another session's uncommitted edits stay where they are
git merge --no-ff 2026-10-23-v188-cancelled-plan-precision \
  -m "Merge v188 cancelled-plan precision" \
  -m "Build-time counts on the replicated production database (<date>): <cancelled N> cancelled plans; risk_cap <n>, invalidated <n>, expired <n>, other <n>, manual <n>. Headline all: <precision> of <n> (95% CI <lo>-<hi>), net R <net_r>; without risk_cap: <...>; baseline stop-first <...>. Data as of <data_as_of>." \
  -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git log --oneline -3
```
Every `<...>` is filled from Step 6's output before the command runs. If git refuses because a file this branch changes (`frontend/src/app/api/models.ts`, `app.routes.ts`, `shell/shell.ts`, `swingbot/admin/spa.py`, …) carries another session's uncommitted edit in the main tree, stop and hand it to the controller: never stash, reset or overwrite another session's work. No full suite after the merge (it ran once, in Step 3).

- [ ] **Step 9: Hand back**

Report to the controller: the merge commit, the Step 3 and Step 5 counts, the complexity-gate verdict, the Step 6 counts and figures, and the audit verdict. The controller runs `/panel staff-engineer,quant-researcher,financial-advisor` over the merged diff and then `/close-out` (ui patch, bot patch; the worktree is removed there, never here).

