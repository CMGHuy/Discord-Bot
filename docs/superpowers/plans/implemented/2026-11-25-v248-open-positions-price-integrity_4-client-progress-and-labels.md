# v248 — Open-positions price integrity — Part 4: client progress and R, overlay recompute, session-aware labels

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V248-11" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-25-v248-open-positions-price-integrity-design.md](../specs/2026-11-25-v248-open-positions-price-integrity-design.md) § 1a (client half: progress and R follow the shown price), § 1b (client half: the error clears when a newer price exists), § 1c (session-aware age wording), § 2 (the overlay never downgrades), and the § Testing rows for 1a, 1b, 1c and the parity fixture.
**Index:** [2026-11-25-v248-open-positions-price-integrity_0-index.md](2026-11-25-v248-open-positions-price-integrity_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation, the task ledger and the binding "Decisions the spec left open" live there; every task below implicitly includes them.
**Brief:** `.superpowers/briefs/2026-11-25-v248-open-positions-price-integrity.md` (§ 3a overlay, § 3b server progress, § 3g–3h `sb-market-value` and `marketAgeLabel`, § 4 frontend test patterns).

Tasks: V248-10 (`position-progress.ts` + models, held to the shared fixture), V248-11 (`overlayQuote` recomputes from the shown price), V248-12 (age wording and the error rule). V248-10 runs first: V248-11 consumes its exports and both V248-11 and V248-12 compile against its `models.ts` fields. V248-11 ∥ V248-12 is safe (disjoint files).

Frontend only: no task here reaches Postgres, so no `/replicate-prod-db`. Every `ng test` command runs from `frontend/`; the parity spec reads `../tests/fixtures/v248/progress_cases.json` (written by V248-2), so that file must be on the branch before V248-10 starts.

---

# Phase 4 — The client computes what the server computes

### Task V248-10: Client models + `position-progress.ts` (`positionProgress`, `liveR`) with the shared parity fixture

**Model:** sonnet — a line-for-line port of three small Python functions, fully determined by the shared fixture and the code given below; one models edit.

**Files:**
- Create: `frontend/src/app/ui/position-progress.ts`
- Create: `frontend/src/app/ui/position-progress.spec.ts`
- Modify: `frontend/src/app/api/models.ts:47-53` (`QuoteUpdate`), `:80-90` (`RowQuoteFields`), new `PriceKind` type directly above `RowQuoteFields`
- Modify (compile fallout of the now-required `QuoteUpdate.error_at`, nothing else): `frontend/src/app/stores/live-values.store.ts:125` (`resolve`), `frontend/src/app/testing/fake-live-values.ts:50-52` (`set` defaults), `frontend/src/app/stores/live-values.store.spec.ts:74-75` (`q` helper) and `:170` (`toEqual` literal)

**Interfaces:**
- Consumes: `tests/fixtures/v248/progress_cases.json` (V248-2) — a **top-level JSON array** of 16 `{name, row, price, price_kind, expected: {progress_pct, entry_pct, progress_band, blink_seconds, status_label, r_multiple}}`; `row` carries only the `ProgressInput` keys. `expected.r_multiple` follows `_attach_unrealized_pnl`: null when `price` or `entry` is null, or the status is terminal or `PENDING`; otherwise `_live_r(row, price)`.
- Produces (`frontend/src/app/api/models.ts`):
  - `export type PriceKind = 'live' | 'prev_close';`
  - `QuoteUpdate.error_at: string | null` (ISO UTC; the server sends it from V248-1).
  - `RowQuoteFields.price_error_at?: string | null`, `RowQuoteFields.price_kind?: PriceKind` (`TradeRow extends RowQuoteFields`, so `TradeRow.price_kind?` comes with it).
- Produces (`frontend/src/app/ui/position-progress.ts`):
  - `export type { PriceKind }` (re-export, so part 5 may import it from either file);
  - `export const PREV_CLOSE_LABEL = 'At prev close (not live)';`
  - `export interface ProgressInput { status: string; direction: string | null; entry: number | null; stop_loss: number | null; target: number | null; bar_kind?: string | null; runner_best?: number | null; banked_exit_price?: number | null; risk_stop?: number | null; banked_fraction?: number | null; banked_r?: number | null; }`
  - `export interface ProgressFields { progress_pct: number | null; entry_pct: number | null; progress_band: 'toward_stop' | 'neutral' | 'toward_target' | null; blink_seconds: number | null; status_label: string; }`
  - `export function positionProgress(row: ProgressInput, price: number | null, kind: PriceKind = 'live'): ProgressFields` — mirrors `trade_progress.row_progress`.
  - `export function liveR(row: ProgressInput, price: number): number | null` — mirrors `trades._live_r`.
  - `export function livePnl(row: Pick<ProgressInput, 'entry' | 'direction'>, price: number): number | null` — mirrors `dashboard.unrealized_pnl` (the server's `pnl_pct` for an open row). Additive beyond the ledger, consumed by V248-11 only.
  - `export function hasPosition(status: string): boolean` — not `CLOSED`/`CANCELLED` and not `PENDING`: the rows `_attach_unrealized_pnl` prices. Additive, consumed by V248-11.
  - `export function pyRound(x: number, nd: number): number` — Python's `round(x, nd)` (exact binary ties to even). Exported for its own tests.

**Why.** Spec § 1a: `StatusCell` showed `no price` beside a priced NOW cell because only the server computed the bar; the overlay (V248-11) must recompute it, and R with it, from the price the row shows. Index Decision 1: `trade_proximity` stays the Python source of the band; this port is held to it by the fixture both suites read, so they cannot drift. `pyRound` exists because `toFixed` and `Math.round` break exact ties away from zero (`0.125` → `0.13`) where Python goes to even (`0.12`).

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/ui/position-progress.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  PREV_CLOSE_LABEL, PriceKind, ProgressFields, ProgressInput,
  hasPosition, livePnl, liveR, positionProgress, pyRound,
} from './position-progress';

interface Case {
  name: string;
  row: ProgressInput;
  price: number | null;
  price_kind: PriceKind;
  expected: ProgressFields & { r_multiple: number | null };
}

/** Written by V248-2; tests/admin/test_v248_progress_parity.py reads the same file. */
const CASES: Case[] = JSON.parse(
  readFileSync(join(process.cwd(), '..', 'tests', 'fixtures', 'v248', 'progress_cases.json'), 'utf8'));
const BAR_KEYS = ['progress_pct', 'entry_pct', 'progress_band', 'blink_seconds', 'status_label'] as const;

/** The R `_attach_unrealized_pnl` puts on the row at `price`. */
function shownR(row: ProgressInput, price: number | null): number | null {
  if (price === null || row.entry === null || !hasPosition(row.status)) return null;
  return liveR(row, price);
}

describe('position-progress parity with trade_progress.py (v248)', () => {
  it('reads the 16 shared cases', () => {
    expect(Array.isArray(CASES)).toBe(true);
    expect(new Set(CASES.map((c) => c.name)).size).toBe(16);
  });

  for (const c of CASES) {
    it(c.name, () => {
      const row = structuredClone(c.row);
      const got = positionProgress(row, c.price, c.price_kind);
      expect(Object.keys(got).sort()).toEqual([...BAR_KEYS].sort());
      expect(got).toEqual(Object.fromEntries(BAR_KEYS.map((k) => [k, c.expected[k]])));
      expect(shownR(row, c.price)).toEqual(c.expected.r_multiple);
      expect(row).toEqual(c.row);                                   // pure
    });
  }
});

describe('positionProgress (v248)', () => {
  const bull = CASES.find((c) => c.name === 'bull_live_toward_target')!.row;

  it('a prev-close bar never claims a stop, a target or urgency', () => {
    for (const price of [80, 92, 105, 119, 140]) {
      const got = positionProgress(bull, price, 'prev_close');
      const live = positionProgress(bull, price);
      expect(got).toMatchObject({ progress_band: 'neutral', blink_seconds: null, status_label: PREV_CLOSE_LABEL });
      expect([got.progress_pct, got.entry_pct]).toEqual([live.progress_pct, live.entry_pct]);
    }
  });

  it('defaults to a live price', () =>
    expect(positionProgress(bull, 92).progress_band).toBe('toward_stop'));

  it('a null direction reads as bullish, like the server', () =>
    expect(positionProgress({ ...bull, direction: null }, 110)).toEqual(positionProgress(bull, 110)));

  it('an EXPIRED row is not terminal on the server, so it keeps a bar', () =>
    expect(positionProgress({ ...bull, status: 'EXPIRED' }, 110).progress_pct).toBe(66.7));
});

describe('liveR / livePnl (v248)', () => {
  const row: ProgressInput = { status: 'ACTIVE', direction: 'bullish', entry: 100, stop_loss: 95,
    target: 120, risk_stop: 90, banked_fraction: null, banked_r: null };

  it('measures R against the original stop', () => expect(liveR(row, 110)).toBe(1));
  it('mirrors the short side', () =>
    expect(liveR({ ...row, direction: 'bearish', risk_stop: 110 }, 95)).toBe(0.5));
  it('is null without a risk basis or a price', () => {
    expect(liveR({ ...row, risk_stop: null }, 110)).toBeNull();
    expect(liveR({ ...row, risk_stop: 100 }, 110)).toBeNull();
    expect(liveR(row, 0)).toBeNull();
  });
  it('blends a banked TP1 leg, and is null when the leg has no R', () => {
    const banked = { ...row, banked_fraction: 0.5, banked_r: 2 };
    expect(liveR(banked, 105)).toBe(1.25);
    expect(liveR({ ...banked, banked_r: null }, 105)).toBeNull();
    expect(liveR({ ...banked, direction: 'long' }, 105)).toBeNull();
  });
  it('P&L % follows the direction', () => {
    expect(livePnl(row, 110)).toBe(10);
    expect(livePnl({ entry: 50, direction: 'bearish' }, 45)).toBe(10);
    expect(livePnl({ entry: null, direction: 'bullish' }, 45)).toBeNull();
  });
  it('hasPosition is the server rule', () => {
    expect(['ACTIVE', 'PARTIAL', 'EXPIRED'].map(hasPosition)).toEqual([true, true, true]);
    expect(['PENDING', 'CLOSED', 'CANCELLED'].map(hasPosition)).toEqual([false, false, false]);
  });
});

describe('pyRound (v248)', () => {
  it('rounds like Python, exact ties to even', () => {
    expect(pyRound(0.125, 2)).toBe(0.12);
    expect(pyRound(0.375, 2)).toBe(0.38);
    expect(pyRound(-0.125, 2)).toBe(-0.12);
    expect(pyRound(12.25, 1)).toBe(12.2);
    expect(pyRound(2.675, 2)).toBe(2.67);       // 2.67499999… in binary: not a tie
    expect(pyRound(66.66666, 1)).toBe(66.7);
    expect(pyRound(2.2 - 1.6 * 0.8, 2)).toBe(0.92);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/position-progress.spec.ts`
Expected: FAIL — the build cannot resolve `./position-progress`.

- [ ] **Step 3: Add the model fields**

In `frontend/src/app/api/models.ts`:
- `QuoteUpdate` gains, after `error`: `error_at: string | null;` with the doc comment `v248: when the error was recorded (ISO UTC), null when none; compared with the price's as_of.`
- directly above `RowQuoteFields`: `export type PriceKind = 'live' | 'prev_close';` with the doc comment `v248: prev_close = a held row priced from the last daily close (no live trade yet); absent means live.`
- `RowQuoteFields` gains `price_error_at?: string | null;` (doc: when `price_error` was recorded) and `price_kind?: PriceKind;` (doc: sent on held door rows only).

Then fix the four literals that stop compiling, adding `error_at: null` and nothing else: `live-values.store.ts:125` (`{ symbol: sym, price: null, as_of: null, error: null, error_at: null }`), the `fake-live-values.ts` `set` defaults, the `q` helper in `live-values.store.spec.ts` (`({ symbol, price, as_of, refreshing, error, error_at: null })`) and the `requestRefresh` `toEqual` at `:170`.

- [ ] **Step 4: Create `position-progress.ts`**

Header comment: one paragraph naming `swingbot/admin/api_v1/trade_progress.py` (`row_progress`), `trades._live_r` and `dashboard.unrealized_pnl` as the sources, `tests/fixtures/v248/progress_cases.json` as the contract, and "change both sides and the fixture together". Pure, no Angular imports. The code below is the port; keep its arithmetic order (it matters for float parity):

```ts
import { PriceKind } from '../api/models';

export type { PriceKind } from '../api/models';

export const PREV_CLOSE_LABEL = 'At prev close (not live)';
const TERMINAL: ReadonlySet<string> = new Set(['CLOSED', 'CANCELLED']);   // trades._TERMINAL

// ProgressInput / ProgressFields exactly as in the Interfaces block.

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const clampPct = (v: number): number => Math.max(0, Math.min(100, v));
const noBar = (label: string): ProgressFields =>
  ({ progress_pct: null, entry_pct: null, progress_band: null, blink_seconds: null, status_label: label });

export function pyRound(x: number, nd: number): number {
  const exact = Math.abs(x).toFixed(nd + 21);                 // toFixed reads the exact binary value
  if (!exact.endsWith('5' + '0'.repeat(20))) return Number(x.toFixed(nd));
  const kept = exact.slice(0, -21);                           // truncated to nd decimals
  const even = Number(kept.replace('.', '').slice(-1)) % 2 === 0;
  const mag = even ? Number(kept) : Number((Number(kept) + 10 ** -nd).toFixed(nd));
  return x < 0 ? -mag : mag;
}

export function hasPosition(status: string): boolean {
  return !TERMINAL.has(status) && status !== 'PENDING';
}

/** trade_proximity (core/tracking/performance.py): the band reads the 4-dp proximity, the label the raw one. */
function proximity(direction: string, entry: number, stop: number, target: number, price: number) {
  const risk = Math.abs(entry - stop) || 1e-9;
  const reward = Math.abs(target - entry) || 1e-9;
  const delta = direction === 'bullish' ? price - entry : entry - price;
  const p = Math.max(-1, Math.min(1, delta >= 0 ? delta / reward : delta / risk));
  const label = p >= 0
    ? (p > 0.66 ? 'Near target' : p > 0.15 ? 'Trending toward target' : 'Near entry')
    : (p < -0.66 ? 'Near stop-loss' : p < -0.15 ? 'Trending toward stop' : 'Near entry');
  return { score: pyRound(p, 4), blink: pyRound(2.2 - 1.6 * Math.abs(p), 2), label };
}

function standardBar(row: ProgressInput, price: number | null): ProgressFields {
  const { entry, stop_loss: sl, target: tp } = row;
  if (price === null || !isNum(entry) || !isNum(sl) || !isNum(tp)) return noBar('No live price');
  const direction = row.direction || 'bullish';
  const isBull = direction === 'bullish';
  const span = isBull ? tp - sl : sl - tp;
  if (span <= 0) return noBar('No live price');
  const prox = proximity(direction, entry, sl, tp, price);
  const pos = (isBull ? price - sl : sl - price) / span * 100;
  const ent = (isBull ? entry - sl : sl - entry) / span * 100;
  const band = prox.score > 0.15 ? 'toward_target' : prox.score < -0.15 ? 'toward_stop' : 'neutral';
  return { progress_pct: clampPct(pyRound(pos, 1)), entry_pct: clampPct(pyRound(ent, 1)),
    progress_band: band, blink_seconds: prox.blink, status_label: prox.label };
}

function trailingBar(row: ProgressInput, price: number | null): ProgressFields {
  const stop = row.stop_loss, best = row.runner_best;
  if (price === null || !isNum(stop) || !isNum(best)) return noBar(row.status);
  const isBull = row.direction !== 'bearish';
  const span = isBull ? best - stop : stop - best;
  if (span <= 0) return noBar(row.status);
  const pos = clampPct((isBull ? price - stop : stop - price) / span * 100);
  const leg = row.banked_exit_price;
  const ent = isNum(leg) ? (isBull ? leg - stop : stop - leg) / span * 100 : 0;
  const band = pos >= 66 ? 'toward_target' : pos <= 33 ? 'toward_stop' : 'neutral';
  const label = band === 'toward_stop' ? 'Near trailing stop' : band === 'toward_target' ? 'Near best price' : 'Trailing';
  const urgency = Math.max(0, 1 - pos / 50);
  return { progress_pct: pyRound(pos, 1), entry_pct: clampPct(pyRound(ent, 1)),
    progress_band: band, blink_seconds: pyRound(2.2 - 1.6 * urgency, 2), status_label: label };
}

/** Index Decision 2: a bar drawn from yesterday's close is never urgent. */
function prevCloseBar(fields: ProgressFields, kind: PriceKind): ProgressFields {
  if (kind !== 'prev_close' || fields.progress_pct === null) return fields;
  return { ...fields, progress_band: 'neutral', blink_seconds: null, status_label: PREV_CLOSE_LABEL };
}

export function positionProgress(row: ProgressInput, price: number | null, kind: PriceKind = 'live'): ProgressFields {
  if (row.bar_kind === 'trailing' && !TERMINAL.has(row.status)) return prevCloseBar(trailingBar(row, price), kind);
  if (!hasPosition(row.status)) return noBar(row.status);
  return prevCloseBar(standardBar(row, price), kind);
}
```

`liveR(row, price)`: when `row.banked_fraction` is null or undefined, port `dashboard.unrealized_r` — null if `!price || !row.entry || !row.risk_stop`, or if `Math.abs(entry - risk_stop)` is 0; else `pyRound((direction === 'bullish' ? price - entry : entry - price) / risk, 2)`. Otherwise a private `blendedR(row, price)` ports `metrics.open_trade_r` over the one leg `{fraction: banked_fraction, r: banked_r}`: null when `price` is not finite, `entry` or `risk_stop` is null, `direction` is neither `'bullish'` nor `'bearish'`, the risk is 0, or `banked_r` is null; else `pyRound(fraction * banked_r + Math.max(0, 1 - fraction) * (signed move / risk), 2)`.

`livePnl(row, price)`: null if `!price || !row.entry`; else `raw = (price - entry) / entry * 100` and `pyRound(direction === 'bullish' ? raw : -raw, 2)`.

- [ ] **Step 5: Run the spec and the spec whose literals changed**

Run each from `frontend/`:
- `npx ng test --watch=false --include src/app/ui/position-progress.spec.ts`
- `npx ng test --watch=false --include src/app/stores/live-values.store.spec.ts`

Expected: both green (`0 failed`). Then `npx tsc -p tsconfig.spec.json --noEmit` — Expected: no errors (a `QuoteUpdate` literal missed in Step 3 shows up here; add `error_at: null` to it and nothing else).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ui/position-progress.ts frontend/src/app/ui/position-progress.spec.ts frontend/src/app/api/models.ts frontend/src/app/stores/live-values.store.ts frontend/src/app/stores/live-values.store.spec.ts frontend/src/app/testing/fake-live-values.ts
git commit -m "feat(v248): client position-progress port held to the shared parity fixture"
```

### Task V248-11: `overlayQuote` recomputes progress and R from the shown price, sets `price_kind = 'live'`, never downgrades, patches `price_error_at`

**Model:** sonnet — one pure function in one store file gains a guarded recompute through V248-10's port; the tests pin every branch, including the non-trade consumers.

**Files:**
- Modify: `frontend/src/app/stores/live-values.store.ts:18-47` (`isNewer`, `quotePatch`, `overlayQuote` and two new private helpers beside them)
- Modify: `frontend/src/app/stores/live-values.store.spec.ts` (imports at `:1-9`; new `describe` after the `overlayQuote (v201)` block that ends near `:408`)

**Interfaces:**
- Consumes: V248-10 — `positionProgress(row, price, kind)`, `liveR(row, price)`, `livePnl(row, price)`, `hasPosition(status)`, `PREV_CLOSE_LABEL`, `ProgressInput`, `ProgressFields` from `frontend/src/app/ui/position-progress.ts`; `QuoteUpdate.error_at`, `RowQuoteFields.price_error_at` / `price_kind` from `api/models.ts`; the fixture `tests/fixtures/v248/progress_cases.json` (V248-2, top-level array).
- Produces: none new — `overlayQuote<T extends RowQuoteFields>(row: T, update: QuoteUpdate | null): T` keeps its signature. New behaviour part 5 relies on: a trade row (one that carries `progress_pct`) leaves the overlay with its five bar keys, `r_multiple` and `pnl_pct` computed from the `current_price` it shows, and `price_kind: 'live'` once a priced update replaced a prev-close price.

**Why.** Spec § 1a: after the 12:30 UTC deploy HOOD, AMAT and GLW had live prices again but STATUS kept reading `no price`, because the overlay replaced `current_price` and nothing else; R stayed the server's figure too. Spec § 2: a priceless update must never downgrade a prev-close row; a priced one upgrades it. Index Decision 3: a prev-close row has `price_as_of = null`, so `isNewer` takes any priced update (Review Focus 2: even one whose `as_of` is older than the bid/ask `quote_at` that left the row unpriced). `pnl_pct` is recomputed with R because V248-3 sets it from the prev close: left alone, a row upgraded to live would show a prev-close P&L % without its `at prev close` suffix. Review Focus 5: watchlist, tape and ticker rows share `overlayQuote`; they gain no progress, R or `price_kind` key and stay referentially equal when nothing changes.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/stores/live-values.store.spec.ts`, add `import { readFileSync } from 'node:fs';` and `import { join } from 'node:path';` at the top, and `import { PREV_CLOSE_LABEL, ProgressFields, ProgressInput, PriceKind, positionProgress } from '../ui/position-progress';`. Append after the `overlayQuote (v201)` block:

```ts
describe('overlayQuote on position rows (v248)', () => {
  type Held = RowQuoteFields & ProgressInput & ProgressFields & { r_multiple: number | null; pnl_pct: number | null };
  const BAR = { progress_pct: null, entry_pct: null, progress_band: null, blink_seconds: null } as const;
  const held: Held = {
    status: 'ACTIVE', direction: 'bullish', entry: 100, stop_loss: 90, target: 120, risk_stop: 90,
    bar_kind: 'none', banked_fraction: null, banked_r: null,
    current_price: null, price_as_of: null, price_age_s: null, price_refreshing: false,
    price_error: null, price_error_at: null, price_kind: 'live',
    ...BAR, status_label: 'No live price', r_multiple: null, pnl_pct: null,
  };
  const prevClose: Held = {
    ...held, current_price: 92, price_kind: 'prev_close', price_as_of: null,
    progress_pct: 6.7, entry_pct: 33.3, progress_band: 'neutral', blink_seconds: null,
    status_label: PREV_CLOSE_LABEL, r_multiple: -0.8, pnl_pct: -8,
  };
  const withError = (u: QuoteUpdate, error_at: string | null): QuoteUpdate => ({ ...u, error_at });

  it('a price arriving for a no-price row draws the bar, R and P&L %', () => {
    const out = overlayQuote(held, q('X', 110, A));
    expect(out).toMatchObject({
      current_price: 110, progress_pct: 66.7, entry_pct: 33.3, progress_band: 'toward_target',
      blink_seconds: 1.4, status_label: 'Trending toward target', r_multiple: 1, pnl_pct: 10, price_kind: 'live',
    });
  });

  it('a price crossing the stop turns the bar and the label', () => {
    const priced = overlayQuote(held, q('X', 110, A));
    expect(overlayQuote(priced, q('X', 89, B))).toMatchObject({
      progress_pct: 0, progress_band: 'toward_stop', status_label: 'Near stop-loss', r_multiple: -1.1, pnl_pct: -11,
    });
  });

  it('a row without a stop keeps "No live price" and no R', () => {
    const out = overlayQuote({ ...held, stop_loss: null, risk_stop: null }, q('X', 110, A));
    expect(out).toMatchObject({ current_price: 110, ...BAR, status_label: 'No live price', r_multiple: null });
  });

  it('a prev-close row upgrades to live on any priced update, even one older than its bid/ask', () => {
    const out = overlayQuote(prevClose, q('X', 95, '2026-10-29T20:00:00Z'));
    expect(out).toMatchObject({
      current_price: 95, price_kind: 'live', progress_band: 'toward_stop',
      status_label: 'Trending toward stop', blink_seconds: 1.4, r_multiple: -0.5, pnl_pct: -5,
    });
  });

  it('a priceless update never downgrades a prev-close row', () => {
    expect(overlayQuote(prevClose, q('X', null, null))).toBe(prevClose);
    const marked = overlayQuote(prevClose, q('X', null, null, true, 'no quote'));
    expect(marked).toMatchObject({ current_price: 92, price_kind: 'prev_close', status_label: PREV_CLOSE_LABEL,
      price_refreshing: true, price_error: 'no quote' });
  });

  it('a PENDING row keeps its chip; R, P&L % and price_kind stay untouched', () => {
    const pending = { ...held, status: 'PENDING', status_label: 'PENDING', price_kind: undefined };
    delete pending.price_kind;
    const out = overlayQuote(pending, q('X', 110, A));
    expect(out).toMatchObject({ current_price: 110, ...BAR, status_label: 'PENDING', r_multiple: null, pnl_pct: null });
    expect('price_kind' in out).toBe(false);
  });

  it('a row that has no price_kind never gains one', () => {
    const legacy = { ...held };
    delete legacy.price_kind;
    expect('price_kind' in overlayQuote(legacy, q('X', 110, A))).toBe(false);
  });

  it('an update that is not newer returns the row itself', () => {
    const priced = overlayQuote(held, q('X', 110, A));
    expect(overlayQuote(priced, q('X', 110, A))).toBe(priced);
  });

  it('patches price_error_at from the update, on every kind of row', () => {
    expect(overlayQuote(held, withError(q('X', null, null, false, 'no quote'), B)).price_error_at).toBe(B);
    const watch: RowQuoteFields = { current_price: 100, price_as_of: A };
    expect(overlayQuote(watch, withError(q('X', null, null, false, 'no quote'), B)).price_error_at).toBe(B);
  });

  it('a watchlist row gains no progress, R or price_kind key', () => {
    const watch: RowQuoteFields = { current_price: 100, price_as_of: A };
    expect(Object.keys(overlayQuote(watch, q('X', 105, B))).sort()).toEqual(['current_price', 'price_as_of']);
  });

  it('an update from an older server without error_at changes nothing', () => {
    const watch: RowQuoteFields = { current_price: 100, price_as_of: B };
    const old = { symbol: 'X', price: null, as_of: null, refreshing: false, error: null } as unknown as QuoteUpdate;
    expect(overlayQuote(watch, old)).toBe(watch);
  });

  describe('agrees with the shared fixture for every live case', () => {
    const cases: { name: string; row: ProgressInput; price: number | null; price_kind: PriceKind;
      expected: ProgressFields & { r_multiple: number | null } }[] = JSON.parse(readFileSync(
      join(process.cwd(), '..', 'tests', 'fixtures', 'v248', 'progress_cases.json'), 'utf8'));
    for (const c of cases.filter((x) => x.price_kind === 'live' && x.price !== null)) {
      it(c.name, () => {
        const row = { ...c.row, current_price: null, price_as_of: null, ...BAR, status_label: '', r_multiple: null, pnl_pct: null };
        const out = overlayQuote(row, q('X', c.price, A));
        expect(positionProgress(c.row, c.price)).toEqual({
          progress_pct: out.progress_pct, entry_pct: out.entry_pct, progress_band: out.progress_band,
          blink_seconds: out.blink_seconds, status_label: out.status_label });
        expect(out.r_multiple).toEqual(c.expected.r_multiple);
      });
    }
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/stores/live-values.store.spec.ts`
Expected: FAIL — the new position-row tests (`progress_pct` stays null, `price_error_at` undefined); every pre-existing test still passes.

- [ ] **Step 3: Implement the recompute in `live-values.store.ts`**

Import `hasPosition, liveR, livePnl, positionProgress, ProgressFields, ProgressInput` from `'../ui/position-progress'`. Keep `isNewer` as it is. Add, above `quotePatch`:

```ts
type PositionRow = RowQuoteFields & ProgressInput & ProgressFields & { r_multiple?: number | null; pnl_pct?: number | null };

/** A row that carries the server's status bar: a trade row. Watchlist, tape and ticker rows never do. */
function isPositionRow(row: RowQuoteFields): row is PositionRow {
  return 'progress_pct' in row && 'status' in row;
}

/**
 * v248 § 1a: what a trade row shows, recomputed from the live price that just
 * replaced its own -- the bar, and R and P&L % where `_attach_unrealized_pnl`
 * would set them. A prev-close row becomes live. Only changed keys come back.
 */
function positionPatch(row: PositionRow, price: number): Record<string, unknown> {
  const next: Record<string, unknown> = { ...positionProgress(row, price, 'live') };
  if (hasPosition(row.status) && row.entry != null) {
    next['r_multiple'] = liveR(row, price);
    next['pnl_pct'] = livePnl(row, price);
  }
  if (row.price_kind === 'prev_close') next['price_kind'] = 'live';
  const current = row as Record<string, unknown>;
  return Object.fromEntries(Object.entries(next).filter(([key, value]) => current[key] !== value));
}
```

Split `quotePatch` so each part stays small: a `pricePatch(row, update)` holding today's `isNewer` block plus, at its end, `if (isPositionRow(row)) Object.assign(patch, positionPatch(row, update.price as number));`, and `quotePatch` composing it with the two existing mark lines plus:

```ts
  const errorAt = update.error_at ?? null;
  if ((row.price_error_at ?? null) !== errorAt) patch.price_error_at = errorAt;
```

`quotePatch`'s return type widens to `RowQuoteFields & Record<string, unknown>`; `overlayQuote` keeps its body (`{ ...row, ...patch }` is cast `as T`). Extend `overlayQuote`'s doc comment with one sentence: "v248: on a trade row a newer price also recomputes the status bar, R and P&L % (`ui/position-progress.ts`) and turns a prev-close row live; a priceless update never touches them."

- [ ] **Step 4: Run the store spec and its consumers**

Run each from `frontend/`:
- `npx ng test --watch=false --include src/app/stores/live-values.store.spec.ts`
- `npx ng test --watch=false --include src/app/stores/trades.store.spec.ts`
- `npx ng test --watch=false --include src/app/workspaces/dashboard/positions-table.spec.ts`

Expected: each `0 failed`. A pre-existing trades-store or positions-table assertion that pinned the old server-only `r_multiple` / `progress_*` after an overlay is now wrong by design: update its expected value to the recomputed one and say so in the commit's task report.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/stores/live-values.store.ts frontend/src/app/stores/live-values.store.spec.ts
git commit -m "feat(v248): live overlay recomputes status bar, R and P&L from the shown price"
```

### Task V248-12: Session-aware age wording (`pre-market` / `after hours` / `market closed`, days unit) and the `sb-market-value` error rule (`errorAt`)

**Model:** sonnet — two small UI files with a fixed copy table and one boolean rule (index Decision 5); the session comes from the server, so no calendar logic lands on the client.

**Files:**
- Modify: `frontend/src/app/ui/age-hint.ts:14-19` (`ageText`), `:30-49` (ET helpers; `closedLabel` goes), `:51-64` (`marketAgeLabel`)
- Modify: `frontend/src/app/ui/age-hint.spec.ts` (`ageText` block `:19-33`; `marketAgeLabel (v201)` block `:73-91`)
- Modify: `frontend/src/app/ui/market-value.ts` (doc comment, template, styles, inputs, computeds)
- Modify: `frontend/src/app/ui/market-value.spec.ts` (status signal, `Host`, the `error stops the spinner` test at `:104-109`, new tests)

**Interfaces:**
- Consumes: `MarketStatus.session` (`'regular' | 'extended' | 'closed'`, the server's `session_state()` via `status_block()`; index Decision 4) and `MarketStatus.stale_price_s` from `LiveValuesStore.status`; nothing from V248-10/11 beyond the compiled `models.ts`.
- Produces:
  - `ageText(ageS)` reads `N d ago` (floor) from 24 h on, everywhere it is used (index Decision 6).
  - `marketAgeLabel(asOf, nowMs, status, opts)` for a price outside the regular session: `{ text: '<pre-market | after hours | market closed> · last trade <ageText>', tone: 'closed' }` (`text: null` when `asOf` is null). `pre-market` vs `after hours` is the ET hour of `nowMs` (< 12 → pre-market). A stalled heartbeat still wins (`tone: 'stalled'`); the regular branch and the snapshot path are unchanged.
  - `MarketValue.errorAt = input<string | null>(null)` (`sb-market-value [errorAt]`), consumed by V248-13's `sb-position-price`.
  - `export function errorIsCurrent(errorAt: string | null, asOf: string | null): boolean` — true when `errorAt` is null, `asOf` is null, or `Date.parse(errorAt) >= Date.parse(asOf)`.
  - `export const ERROR_TEXT_MAX = 60;` — the error text is cut to at most 60 characters (59 + `…`); the full text is the span's `title`.
  - Price error rule (index Decision 5): the error shows only when `status.session === 'regular'` **and** (`asOf` is null **or** its age exceeds `status.stale_price_s`) **and** `errorIsCurrent(errorAt, asOf)`. It reads `· refresh failed: <error>` after an age, `refresh failed: <error>` with no age, in `--neg`; the age turns `--neg` with it (`data-tone="failed"`). A `kind="snapshot"` value keeps today's rule and text (`refresh failed` whenever `error` is set).

**Why.** Spec § 1b and § 1c: before the open every healthy ticker read `15 h ago`, and `refresh failed` sat beside good prices because the old error outlived them. The age now says which part of the day it is and reads grey outside the regular session; the error shows only when the shown price is actually stale (or missing) and the failure is newer than the price. The stale limit stays the server's `stale_price_s` (`admin_refresh.stale_after_s("price", …)`); no new constant. Spec § Testing 1c asks for holiday and half-day cases "via the session calendar": the calendar is the server's, so the client tests pin that the wording follows `status.session`, never the client's own clock. Note on index Review Focus 3: on a half-day afternoon the server's `session_state()` returns `extended` (the tape stays open to 20:00 ET, `session.py:56-78`), so the panel reads `after hours · last trade …` in grey, never red; it reads `market closed` once the tape closes. That is the tested behaviour below.

- [ ] **Step 1: Write the failing `age-hint` tests**

In `frontend/src/app/ui/age-hint.spec.ts`:
- in `describe('ageText (v171 D2)')`, add:

```ts
  it('reads whole days from 24 h on (v248)', () => {
    expect(ageText(86_399)).toBe('23 h ago');
    expect(ageText(86_400)).toBe('1 d ago');
    expect(ageText(2 * 86_400 + 7_200)).toBe('2 d ago');
  });
```

- in `describe('marketAgeLabel (v201)')`, replace the two closed-market tests (`'closed market reads last close, not stale'`, `'closed market with a price older than the close shows its own time'`) with:

```ts
  it('closed market reads "market closed · last trade <age>", grey (v248)', () =>
    expect(marketAgeLabel('2026-10-30T19:59:58Z', NOW, st('closed')))
      .toEqual({ text: 'market closed · last trade 19 h ago', tone: 'closed' }));
  it('closed market counts days for an older price (v248)', () =>
    expect(marketAgeLabel('2026-10-28T19:40:00Z', NOW, st('closed')))
      .toEqual({ text: 'market closed · last trade 2 d ago', tone: 'closed' }));
  it('pre-market reads its last trade in grey, never stale (v248)', () =>
    expect(marketAgeLabel('2026-10-29T20:00:00Z', Date.parse('2026-10-30T12:00:00Z'), st('extended')))
      .toEqual({ text: 'pre-market · last trade 16 h ago', tone: 'closed' }));
  it('after hours reads its last trade in grey (v248)', () =>
    expect(marketAgeLabel('2026-10-30T20:00:00Z', Date.parse('2026-10-30T21:30:00Z'), st('extended')))
      .toEqual({ text: 'after hours · last trade 1 h ago', tone: 'closed' }));
  it('a holiday is whatever the server calls it: closed on a weekday morning (v248)', () =>
    expect(marketAgeLabel('2026-11-25T21:00:00Z', Date.parse('2026-11-26T16:00:00Z'), st('closed')))
      .toEqual({ text: 'market closed · last trade 19 h ago', tone: 'closed' }));
  it('a half-day afternoon follows the server: extended reads after hours, not stale (v248)', () =>
    expect(marketAgeLabel('2026-11-27T18:00:00Z', Date.parse('2026-11-27T19:00:00Z'), st('extended')))
      .toEqual({ text: 'after hours · last trade 1 h ago', tone: 'closed' }));
  it('stalled feed wins over extended (v248)', () =>
    expect(marketAgeLabel('2026-10-29T20:00:00Z', Date.parse('2026-10-30T12:00:00Z'), st('extended', true)).tone)
      .toBe('stalled'));
  it('no as-of outside the session gives no text (v248)', () =>
    expect(marketAgeLabel(null, NOW, st('extended'))).toEqual({ text: null, tone: 'closed' }));
```

(`NOW` is `2026-10-31T15:00:00Z`, a Saturday; `st(session, stalled)` is the block's existing helper. `2026-10-30T12:00:00Z` is 08:00 EDT, `21:30Z` is 17:30 EDT; `2026-11-26T16:00:00Z` is 11:00 EST on Thanksgiving; `2026-11-27T19:00:00Z` is 14:00 EST on the 13:00 half-day.) The snapshot block stays untouched.

- [ ] **Step 2: Write the failing `sb-market-value` tests**

In `frontend/src/app/ui/market-value.spec.ts`:
- import `errorIsCurrent` beside `MarketValue`;
- add `let status: WritableSignal<MarketStatus>;` next to `clock`, set `status = signal(regular);` in `beforeEach`, and provide `{ provide: LiveValuesStore, useValue: { status } }` there **and** in the re-configure inside `'stays visible with no as-of while refreshing or failed'`;
- `Host`'s template gains `[errorAt]="errAt"` and the class `errAt: string | null = null;`;
- replace `'error stops the spinner'` with the tests below, and add the `errorIsCurrent` block after the `describe`:

```ts
  const err = (el: HTMLElement) => el.querySelector('.mv-err');
  const tone = (el: HTMLElement) => el.querySelector('.mv')?.getAttribute('data-tone');

  it('a fresh price hides an error: the spinner keeps running (v248)', () => {
    const el = render({ r: true, e: 'no quote', errAt: ago(5) });
    expect(err(el)).toBeNull();
    expect(el.querySelector('sb-spinner')).not.toBeNull();
    expect(tone(el)).toBe('fresh');
  });

  it('a stale price shows a current error in red, with its text (v248)', () => {
    const el = render({ a: ago(840), r: true, e: 'no quote', errAt: ago(30) });
    expect(err(el)?.textContent?.trim()).toBe('· refresh failed: no quote');
    expect(err(el)?.getAttribute('title')).toBe('no quote');
    expect(el.querySelector('.mv-age')?.textContent?.trim()).toBe('14 min ago');
    expect(tone(el)).toBe('failed');
    expect(el.querySelector('sb-spinner')).toBeNull();
  });

  it('an error older than the price stays hidden; the age stays merely stale (v248)', () => {
    const el = render({ a: ago(840), e: 'no quote', errAt: ago(900) });
    expect(err(el)).toBeNull();
    expect(tone(el)).toBe('stale');
  });

  it('an error recorded at the price time still shows (v248)', () => {
    const at = ago(840);
    expect(err(render({ a: at, e: 'no quote', errAt: at }))).not.toBeNull();
  });

  it('no price at all shows the error without a separator (v248)', () => {
    const el = render({ a: null, e: 'timeout' });
    expect(err(el)?.textContent?.trim()).toBe('refresh failed: timeout');
    expect((el.querySelector('sb-market-value') as HTMLElement).classList).not.toContain('mv-empty');
  });

  it('a consumer that passes no errorAt (watchlist, tape) shows a current error on a stale price (v248)', () =>
    expect(err(render({ a: ago(840), e: 'no quote' }))).not.toBeNull());

  it('outside the regular session the error never shows and the age is grey (v248)', () => {
    status.set({ ...regular, session: 'extended' });
    const el = render({ a: ago(840), e: 'no quote', errAt: ago(30) });
    expect(err(el)).toBeNull();
    expect(tone(el)).toBe('closed');
    expect(el.querySelector('.mv-age')?.textContent?.trim()).toBe('pre-market · last trade 14 min ago');
  });

  it('cuts a long error to 60 characters, the full text in its title (v248)', () => {
    const long = 'x'.repeat(80);
    const shown = err(render({ a: null, e: long }))!;
    const text = shown.textContent!.trim().replace('refresh failed: ', '');
    expect(text.length).toBe(60);
    expect(text.endsWith('…')).toBe(true);
    expect(shown.getAttribute('title')).toBe(long);
  });

  it('a snapshot error shows as before (v248 leaves snapshots alone)', () => {
    const el = render({ kind: 'snapshot', a: '2026-10-28', computedAt: ago(180), e: 'build failed' });
    expect(err(el)?.textContent?.trim()).toBe('refresh failed');
  });
```

```ts
describe('errorIsCurrent (v248)', () => {
  const A = '2026-10-30T14:00:00Z';
  const B = '2026-10-30T14:05:00Z';
  it('is current with no error time, no price time, or an error at or after the price', () => {
    expect(errorIsCurrent(null, A)).toBe(true);
    expect(errorIsCurrent(B, null)).toBe(true);
    expect(errorIsCurrent(B, A)).toBe(true);
    expect(errorIsCurrent(A, A)).toBe(true);
  });
  it('is not current when the price is newer than the error', () =>
    expect(errorIsCurrent(A, B)).toBe(false));
});
```

(`NOW` in this file is `2026-10-30T15:00:00Z`, 11:00 EDT, so the extended case reads `pre-market`; `regular.stale_price_s` is 120.)

- [ ] **Step 3: Run both specs to verify they fail**

Run each from `frontend/`:
- `npx ng test --watch=false --include src/app/ui/age-hint.spec.ts`
- `npx ng test --watch=false --include src/app/ui/market-value.spec.ts`

Expected: FAIL — `1 d ago` reads `24 h ago`, the closed text is `last close · Fri 16:00 ET`, the extended cases read a bare age, `errorAt` is not a known input of `sb-market-value`.

- [ ] **Step 4: Implement the wording in `age-hint.ts`**

- `ageText`: after the hours line's guard, `if (ageS < 86_400)` keeps `N h ago`; otherwise `` `${Math.floor(ageS / 86_400)} d ago` ``.
- Add `const ET_HOUR = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: '2-digit', hourCycle: 'h23' });` and a private `etHour(ms: number): number` reading the `hour` part through `formatToParts` (as `etStamp` does).
- Add a private `offHoursText(session: 'extended' | 'closed', age: string | null, nowMs: number): string | null` returning null for a null age, else `` `${prefix} · last trade ${age}` `` with `prefix` = `'market closed'` for `closed`, `'pre-market'` when `etHour(nowMs) < 12`, else `'after hours'`.
- In `marketAgeLabel`'s price path, replace the `closed` branch with `if (status && status.session !== 'regular') return { text: offHoursText(status.session, ageText(age), nowMs), tone: 'closed' };` (after the stalled check, before the stale limit). Delete `closedLabel` (now unused; `etStamp` stays for `snapshotLabel`).
- Update `marketAgeLabel`'s doc comment: "v248: outside the regular session the age says which part of the day it is (`pre-market` / `after hours` / `market closed · last trade …`) in grey; the session is the server's, never this clock's."

- [ ] **Step 5: Implement the error rule in `market-value.ts`**

- Exports: `ERROR_TEXT_MAX = 60` and `errorIsCurrent(errorAt, asOf)` as in the Interfaces block; a private `shortError(error: string): string` (`error.length <= ERROR_TEXT_MAX ? error : error.slice(0, ERROR_TEXT_MAX - 1) + '…'`); a private `priceErrorVisible(asOf: string | null, errorAt: string | null, nowMs: number, status: MarketStatus | null): boolean` implementing the rule (stale = `asOf === null` or `(nowMs - Date.parse(asOf)) / 1000 > status.stale_price_s`, with a null limit meaning not stale).
- `readonly errorAt = input<string | null>(null);`
- `protected readonly showError = computed(() => this.error() !== null && (this.kind() === 'snapshot' || priceErrorVisible(this.asOf(), this.errorAt(), this.clock(), this.live.status())));`
- `protected readonly errorText = computed(...)`: `'refresh failed'` for a snapshot; otherwise `(this.label().text ? '· ' : '') + 'refresh failed: ' + shortError(error)`.
- `tone`: `this.showError() && this.kind() === 'price' ? 'failed' : this.label().tone`; `spinning` and `empty` read `showError()` instead of `error()`.
- Template: the error span becomes `@if (showError()) {<span class="mv-err" [attr.title]="error()">{{ errorText() }}</span>}`.
- Styles: add `[data-tone=failed] .mv-age { color: var(--neg); }` beside the stale rule. The muted meta colour stays `var(--text-muted)` (the existing contrast-checked token); no new token.
- Doc comment: replace "and "refresh failed" when it was not answered" with "and, in the regular session only, `refresh failed: <error>` when the shown price is stale or missing and the failure is newer than it (v248 § 1b)".

- [ ] **Step 6: Run the two specs and the consumers that render ages**

Run each from `frontend/`:
- `npx ng test --watch=false --include src/app/ui/age-hint.spec.ts`
- `npx ng test --watch=false --include src/app/ui/market-value.spec.ts`
- `npx ng test --watch=false --include src/app/shell/tape/tape.spec.ts`
- `npx ng test --watch=false --include src/app/workspaces/watchlist/watchlist.spec.ts`
- `npx ng test --watch=false --include src/app/workspaces/dashboard/dashboard.spec.ts`
- `npx ng test --watch=false --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts`

Expected: each `0 failed`. A consumer assertion that pinned the old closed wording (`last close · …`) or `refresh failed` beside a fresh price is wrong by design now: change its expected text to the new wording, never the rule, and list it in the task report.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/age-hint.ts frontend/src/app/ui/age-hint.spec.ts frontend/src/app/ui/market-value.ts frontend/src/app/ui/market-value.spec.ts
git commit -m "feat(v248): session-aware price ages and refresh-failed only when the shown price is stale"
```

(Add any consumer spec changed in Step 6 to the same commit.)
