# v248 — Open-positions price integrity, part 5: shared cells, pages, closing check

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V248-14" -A 300 <this file>`).

**Spec:** [2026-11-25-v248-open-positions-price-integrity-design.md](../specs/2026-11-25-v248-open-positions-price-integrity-design.md) — § 1d, 1e, 1f, 1g.
**Index:** [2026-11-25-v248-open-positions-price-integrity_0-index.md](2026-11-25-v248-open-positions-price-integrity_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation and the task ledger live there and bind every task below.

Tasks V248-13..V248-16. They consume part 4's client contracts (V248-10:
`PriceKind`, `PREV_CLOSE_LABEL`, `RowQuoteFields.price_kind` /
`price_error_at`; V248-12: `MarketValue.errorAt`, the regular-session error
rule) exactly as the index ledger names them.

**Facts this part relies on (checked on `main` 305b778c):**

- The Dashboard's Open positions table renders the same `tradeColumns()`
  set as Trades (`dashboard.ts:164`, cells map `dashboard.ts:957-967`), so it
  **does** carry a `now` column; today it falls back to the column's plain
  `value: (row) => num(row.current_price)` (`trades.columns.ts:174`) because
  the dashboard wires no `now` cell. After V248-3 that text would print a prev
  close as if it were live (spec anti-goal 1), so V248-14 makes the `now` and
  `r_multiple` column text honest in `trades.columns.ts` (shared by both
  pages), and V248-15 wires the dashboard's `now` cell to `sb-position-price`.
- Both pages colour P&L and R with a page-local `pnlClass(value)`
  (`'pos' | 'neg' | ''`, global `.pos/.neg` in `styles.css:149-150`). V248-13's
  `figureTone` replaces it on the three cells so tone has one source.
- Spec tests read files through `readFileSync(join(process.cwd(), 'src/...'))`
  (`ui/status-cell.spec.ts:157`); the worst-case fixture is read the same way.
- `frontend/scripts/*.test.mjs` run under pytest through
  `tests/scripts/test_node_scripts.py` (suite already covers the directory).

# Phase 5 — Shared cells, pages, closing check

### Task V248-13: Shared position formatter, `StatusCell` prev-close title and `no price yet`; worst-case row fixture

**Model:** sonnet — pure formatters and a renderer tweak on a pinned contract; no cross-package reasoning.

**Files:**
- Create: `frontend/src/app/ui/position-format.ts`, `frontend/src/app/ui/position-format.spec.ts`
- Create: `frontend/src/app/testing/fixtures/v248-worst-case-row.json`
- Modify: `frontend/src/app/ui/status-cell.ts` (`StatusCellRow` l.26-48, template l.80-129, `bar` / `hint` computeds l.190-225), `frontend/src/app/ui/status-cell.spec.ts`

**Interfaces:**
- Consumes: V248-10 — `PriceKind`, `PREV_CLOSE_LABEL` (`frontend/src/app/ui/position-progress.ts`), `RowQuoteFields.price_kind?`, `RowQuoteFields.price_error_at?` (`api/models.ts`); existing `ABSENT`, `num`, `pct`, `signed` (`ui/format.ts`).
- Produces (`position-format.ts`):
  - `export type PositionPriceRow = RowQuoteFields & { status: string }` (V248-13b re-exports it from `position-price.ts`, where the ledger names it)
  - `export const HELD_STATUSES: ReadonlySet<string>` = `ACTIVE`, `PARTIAL`
  - `export const PREV_CLOSE_TAG = 'prev close'`, `PREV_CLOSE_SUFFIX = 'at prev close'`, `NO_PRICE_TEXT = 'no price yet'`, `NO_PRICE_REASON = 'no trade and no daily close cached'`, `PREV_CLOSE_ARIA = 'price is previous close, not live'`
  - `export function positionFigure(value: number | null | undefined, unit: 'pct' | 'r', kind?: PriceKind | null): { text: string; suffix: string | null }` — `pct` → `pct(value)` (`+3.14%`), `r` → `signed(value)` (`−1.65`, no unit: the column header names it); `suffix = PREV_CLOSE_SUFFIX` only when `kind === 'prev_close'` and the value is a number.
  - `export function figureText(value: number | null | undefined, unit: 'pct' | 'r', kind?: PriceKind | null): string` — `text`, plus `' ' + suffix` when there is one (column text fallbacks, V248-14).
  - `export function figureTone(value: number | null | undefined, kind?: PriceKind | null): 'pos' | 'neg' | 'muted' | ''` — `muted` for any non-zero number on a prev-close row, else the sign; `''` for zero or null.
  - `export function closeDateTag(date: string | null | undefined): string` — `'2026-11-24'` → `'11-24'`, null → `''`.
  - `export function positionPriceText(row: PositionPriceRow): string` — the NOW column's text (V248-14).
- Produces (`status-cell.ts`): `StatusCellRow.price_kind?: PriceKind`, `StatusCellRow.current_price?: number | null`, `StatusCellRow.last_close?: number | null` (the last one beyond the ledger, read only here; both pages pass the whole `TradeRow`).
- Produces: `frontend/src/app/testing/fixtures/v248-worst-case-row.json` — `{ "now": ISO, "base": <TradeRow fields>, "rows": { "worst_case", "stale_live", "no_price" } }`; a row is `{ ...base, ...rows[name] }`. V248-13b, V248-14, V248-15 and V248-16 read it.

**Why.** Spec § 1d (prev-close tag and suffix, neutral bar), § 1e (`no price yet` with a reason, never a bare `—` on a held row), § 1f (one formatter for NOW, P&L % and R on both pages), § 1g (the worst case is a named fixture). `StatusCell` stays a renderer (its "computes nothing" contract): on a prev-close row it only forces the bar neutral and still — belt and braces behind V248-2 / V248-11, so a stop-hit or near band never shows while `price_kind = prev_close` — and it picks the hint text. The Dashboard has no other place to say `no price yet` on a phone, so the reason shows in the STATUS cell too.

- [ ] **Step 1: Create the worst-case fixture**

`frontend/src/app/testing/fixtures/v248-worst-case-row.json` (values pinned; `now` is Wednesday 10:00 ET, regular session):

```json
{
  "now": "2026-11-25T15:00:00Z",
  "base": {
    "id": "v248wc", "origin": "plan", "status": "ACTIVE", "ticker": "DOCU", "direction": "bullish",
    "strategy": "Support-Resistance", "horizon": "swing", "tier": "A", "badge": "VALIDATED",
    "confidence_level": 3, "confidence_score": 0.71, "quality_score": 82,
    "entry": 1400, "stop_loss": 1300, "target": 1600, "target2": null,
    "banked_fraction": null, "banked_exit_price": null, "banked_r": null, "risk_reward": 2,
    "shares": 12, "open_shares": 12, "position_value": 16800,
    "current_price": null, "current_price_stale": false, "exit_price": null, "realized_pnl_amount": null,
    "pnl_pct": null, "r_multiple": null, "held_hours": 23.8,
    "opened_at": "2026-11-24T15:10:00Z", "closed_at": null, "has_note": false, "today": false,
    "created_at": "2026-11-24T14:30:00Z", "trigger_price": null, "follow_score": null,
    "progress_pct": null, "entry_pct": null, "progress_band": null, "blink_seconds": null,
    "status_label": "No live price", "target_is_banked_tp1": false, "stop_kind": "risk", "bar_kind": "progress",
    "floor_r": null, "price_r": null, "headroom_r": null, "distance_to_trigger_r": null, "bars_to_expiry": null,
    "leg_index": 0, "leg_total": 1,
    "price_as_of": null, "price_age_s": null, "price_refreshing": false, "price_error": null, "price_error_at": null,
    "last_close": null, "last_close_date": null
  },
  "rows": {
    "worst_case": {
      "current_price": 1234.56, "price_kind": "prev_close", "last_close": 1234.56, "last_close_date": "2026-11-24",
      "price_error": "YFPricesMissingError('possibly delisted; no price data found (period=1d)')",
      "price_error_at": "2026-11-25T14:59:00Z",
      "pnl_pct": -11.82, "r_multiple": -1.65,
      "progress_pct": 0.0, "entry_pct": 33.3, "progress_band": "neutral", "blink_seconds": null,
      "status_label": "At prev close (not live)"
    },
    "stale_live": {
      "id": "v248sl", "ticker": "HOOD", "entry": 120, "stop_loss": 112, "target": 136, "position_value": 1440,
      "current_price": 131.07, "price_kind": "live", "current_price_stale": true,
      "price_as_of": "2026-11-25T14:46:00Z", "price_age_s": 840,
      "price_error": "no quote", "price_error_at": "2026-11-25T14:59:00Z",
      "last_close": 129.4, "last_close_date": "2026-11-24",
      "pnl_pct": 9.23, "r_multiple": 1.38,
      "progress_pct": 79.5, "entry_pct": 33.3, "progress_band": "toward_target", "blink_seconds": 0.9,
      "status_label": "Trending toward target"
    },
    "no_price": {
      "id": "v248np", "ticker": "CRWV", "status": "PARTIAL", "entry": 42, "stop_loss": 39, "target": 48,
      "position_value": 504, "banked_fraction": 0.5,
      "price_error": "no quote", "price_error_at": "2026-11-25T14:58:00Z"
    }
  }
}
```

`no_price` carries no `price_kind` key on purpose (V248-3: a held row with neither price has none). `worst_case` is spec § 1g's row: held, regular session, error text past 60 characters, `prev close` tag, `at prev close` on P&L % and R, a four-digit price.

- [ ] **Step 2: Write the failing formatter tests** — `frontend/src/app/ui/position-format.spec.ts`

```ts
import { describe, expect, it } from 'vitest';

import {
  HELD_STATUSES, NO_PRICE_REASON, NO_PRICE_TEXT, PREV_CLOSE_ARIA, PREV_CLOSE_SUFFIX, PREV_CLOSE_TAG,
  closeDateTag, figureText, figureTone, positionFigure, positionPriceText,
} from './position-format';

const held = (o: Record<string, unknown>) => ({ status: 'ACTIVE', current_price: null, last_close: null, ...o });

describe('positionFigure', () => {
  it('formats P&L % signed with its unit and R signed without one', () => {
    expect(positionFigure(3.14159, 'pct')).toEqual({ text: '+3.14%', suffix: null });
    expect(positionFigure(1.38, 'r', 'live')).toEqual({ text: '+1.38', suffix: null });
  });
  it('suffixes a prev-close figure, with the true minus', () => {
    expect(positionFigure(-11.82, 'pct', 'prev_close')).toEqual({ text: '−11.82%', suffix: 'at prev close' });
    expect(positionFigure(-1.65, 'r', 'prev_close')).toEqual({ text: '−1.65', suffix: PREV_CLOSE_SUFFIX });
  });
  it('a missing value is an em dash and never carries the suffix', () => {
    expect(positionFigure(null, 'pct', 'prev_close')).toEqual({ text: '—', suffix: null });
    expect(positionFigure(undefined, 'r')).toEqual({ text: '—', suffix: null });
  });
  it('a loss that rounds to zero prints unsigned', () => {
    expect(positionFigure(-0.001, 'pct').text).toBe('0.00%');
  });
  it('figureText joins the suffix for text-only renderings', () => {
    expect(figureText(-1.65, 'r', 'prev_close')).toBe('−1.65 at prev close');
    expect(figureText(2, 'pct', 'live')).toBe('+2.00%');
  });
});

describe('figureTone', () => {
  it('is the sign on a live row and muted on a prev-close one', () => {
    expect(figureTone(5, 'live')).toBe('pos');
    expect(figureTone(-1, null)).toBe('neg');
    expect(figureTone(0)).toBe('');
    expect(figureTone(null, 'prev_close')).toBe('');
    expect(figureTone(-1, 'prev_close')).toBe('muted');
    expect(figureTone(4, 'prev_close')).toBe('muted');
  });
});

describe('position constants and text', () => {
  it('held means ACTIVE and PARTIAL only', () => {
    expect([...HELD_STATUSES].sort()).toEqual(['ACTIVE', 'PARTIAL']);
  });
  it('pins the copy the spec fixes', () => {
    expect(PREV_CLOSE_TAG).toBe('prev close');
    expect(NO_PRICE_TEXT).toBe('no price yet');
    expect(NO_PRICE_REASON).toBe('no trade and no daily close cached');
    expect(PREV_CLOSE_ARIA).toBe('price is previous close, not live');
  });
  it('closeDateTag keeps month-day', () => {
    expect(closeDateTag('2026-11-24')).toBe('11-24');
    expect(closeDateTag(null)).toBe('');
  });
  it('positionPriceText says what the price is', () => {
    expect(positionPriceText(held({ current_price: 131.07, price_kind: 'live' }))).toBe('131.07');
    expect(positionPriceText(held({ current_price: 1234.56, price_kind: 'prev_close', last_close: 1234.56 })))
      .toBe('1,234.56 prev close');
    expect(positionPriceText(held({}))).toBe('no price yet');
    expect(positionPriceText(held({ last_close: 36.86, last_close_date: '2026-11-09' }))).toBe('36.86 close 11-09');
    expect(positionPriceText({ status: 'PENDING', current_price: null, last_close: null })).toBe('—');
  });
});
```

(`num(1234.56)` groups to `1,234.56` through `ui/format.ts`'s `grouped`; if `grouped` prints otherwise, pin what `num` prints — the NOW cell, V248-13b, uses the same `num`.)

- [ ] **Step 3: Write the failing StatusCell tests** — append to `frontend/src/app/ui/status-cell.spec.ts` (import `PREV_CLOSE_LABEL` from `./position-progress`, `NO_PRICE_REASON` from `./position-format`)

```ts
describe('StatusCell v248', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('a prev-close bar is neutral, still, and titled as not live, whatever band arrives', () => {
    const el = render({ ...live, price_kind: 'prev_close', current_price: 92, progress_pct: 0,
      progress_band: 'toward_stop', blink_seconds: 0.5, status_label: 'Near stop-loss' });
    expect(el.querySelector('.fill')!.classList).toContain('neutral');
    expect(el.querySelector('.fill')!.classList).not.toContain('toward_stop');
    expect(el.querySelector('.dot')!.hasAttribute('data-still')).toBe(true);
    expect(el.querySelector('.track')!.getAttribute('title')).toBe(PREV_CLOSE_LABEL);
    expect(el.querySelector('.track')!.getAttribute('aria-label')).toBe(PREV_CLOSE_LABEL);
  });
  it('a live bar keeps its band, pulse and label', () => {
    const el = render({ ...live, price_kind: 'live', current_price: 110 });
    expect(el.querySelector('.fill')!.classList).toContain('toward_target');
    expect(el.querySelector('.dot')!.hasAttribute('data-still')).toBe(false);
    expect(el.querySelector('.track')!.getAttribute('title')).toBe('Trending toward target');
  });
  const unpriced = { ...live, progress_pct: null, progress_band: null, blink_seconds: null, status_label: 'No live price' };
  it('a held row with neither price nor close says "no price yet" and why', () => {
    for (const status of ['ACTIVE', 'PARTIAL']) {
      const el = render({ ...unpriced, status, current_price: null, last_close: null });
      expect(el.querySelector('.hint')!.textContent!.trim()).toBe('no price yet');
      expect(el.querySelector('.reason')!.textContent!.trim()).toBe(NO_PRICE_REASON);
    }
  });
  it('"no price yet" wins over "trailing" for a runner with no price at all', () => {
    const el = render({ ...unpriced, status: 'PARTIAL', bar_kind: 'trailing', current_price: null, last_close: null });
    expect(el.querySelector('.hint')!.textContent!.trim()).toBe('no price yet');
  });
  it('a held row with a cached close, or with no current_price field, keeps "no price"', () => {
    expect(render({ ...unpriced, current_price: null, last_close: 36.86 }).querySelector('.hint')!.textContent!.trim()).toBe('no price');
    expect(render(unpriced).querySelector('.hint')!.textContent!.trim()).toBe('no price');
    expect(render(unpriced).querySelector('.reason')).toBeNull();
  });
  it('a PENDING row with no price stays a bare chip', () => {
    expect(render({ ...unpriced, status: 'PENDING', current_price: null, last_close: null }).querySelector('.hint')).toBeNull();
  });
});
```

- [ ] **Step 4: Run the specs to see them fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/position-format.spec.ts --include src/app/ui/status-cell.spec.ts`
Expected: FAIL — `./position-format` cannot be resolved; the v248 StatusCell cases fail on band, title and hint.

- [ ] **Step 5: Implement `position-format.ts`**

Pure module: imports `ABSENT`, `num`, `pct`, `signed` from `./format`, `type PriceKind` from `./position-progress`, `type RowQuoteFields` from `../api/models`. Behaviour as in Interfaces. `positionPriceText` branches in this order: a price → `num(current_price)` plus `' prev close'` when `price_kind === 'prev_close'`; held (`HELD_STATUSES`) with `last_close == null` → `NO_PRICE_TEXT`; `last_close != null` → `` `${num(last_close)} close ${closeDateTag(last_close_date)}`.trim() ``; else `ABSENT`. One doc line per export citing spec § 1d / 1e / 1f.

- [ ] **Step 6: Implement the StatusCell change** (`status-cell.ts`)

- `StatusCellRow` gains `price_kind?: PriceKind`, `current_price?: number | null`, `last_close?: number | null` (one doc line each, spec § 1d / 1e).
- `bar` computed: `const prev = r.price_kind === 'prev_close'`; returns `band: prev ? 'neutral' : r.progress_band`, plus `still: prev` and `title: prev ? PREV_CLOSE_LABEL : r.status_label`.
- Template: `.dot` gets `[attr.data-still]="b.still ? '' : null"`; the track's `[attr.aria-label]` and `[title]` read `b.title`. CSS: `.dot[data-still] { animation: none; }`.
- `hint` returns `{ text: string; reason: string | null } | null`. New module function `noPriceYet(r: StatusCellRow): boolean` = `HELD_STATUSES.has(r.status) && r.current_price === null && (r.last_close ?? null) === null`, checked right after `NO_POSITION_YET` and before the trailing test → `{ text: NO_PRICE_TEXT, reason: NO_PRICE_REASON }`; otherwise today's `'no price'` / `'trailing'` with `reason: null`. Template: `<span class="hint">{{ h.text }}</span>@if (h.reason) {<span class="reason">{{ h.reason }}</span>}`; the chip branch's `.cell` gets `flex-wrap: wrap`; `.reason { font-size: var(--text-micro); color: var(--text-muted); }`.
- The class doc's "It computes nothing" paragraph gains one sentence: on a prev-close row it only forces the band neutral and the dot still (spec § 1d); the arithmetic still arrives on the row.

`current_price === null` is strict on purpose: a fixture row without the field keeps `no price` (existing test l.43-47).

- [ ] **Step 7: Run the specs to see them pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/position-format.spec.ts --include src/app/ui/status-cell.spec.ts`
Expected: `0 failed`, the existing StatusCell tests unchanged.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/ui/position-format.ts frontend/src/app/ui/position-format.spec.ts frontend/src/app/testing/fixtures/v248-worst-case-row.json frontend/src/app/ui/status-cell.ts frontend/src/app/ui/status-cell.spec.ts
git commit -m "feat(ui): v248 position formatter, prev-close and no-price-yet status (V248-13)"
```

### Task V248-13b: Shared cells: `sb-position-price` (NOW) and `sb-position-figure` (P&L % / R)

**Model:** sonnet — two standalone presentational components on contracts V248-12 and V248-13 pin.

**Files:**
- Create: `frontend/src/app/ui/position-price.ts` (both components: `PositionPrice` and `PositionFigure`), `frontend/src/app/ui/position-price.spec.ts`

**Interfaces:**
- Consumes: V248-13 — `PositionPriceRow`, `HELD_STATUSES`, `PREV_CLOSE_TAG`, `NO_PRICE_TEXT`, `NO_PRICE_REASON`, `PREV_CLOSE_ARIA`, `positionFigure`, `closeDateTag` (`ui/position-format.ts`), fixture `src/app/testing/fixtures/v248-worst-case-row.json`; V248-10 — `PriceKind`; V248-12 — `MarketValue.errorAt = input<string | null>(null)` and its rule (the error shows only in the regular session, when the price is stale or absent, and when `errorIsCurrent(errorAt, asOf)`); existing `num` (`ui/format.ts`), `BREAKPOINTS` (`ui/breakpoints.ts`), `CLOCK` (`ui/clock.ts`), `LiveValuesStore.status`.
- Produces: `export type { PositionPriceRow } from './position-format'` (re-export, the ledger's home); `PositionPrice` (`sb-position-price`, `row = input.required<PositionPriceRow>()`); `PositionFigure` (`sb-position-figure`, `value = input<number | null>(null)`, `unit = input.required<'pct' | 'r'>()`, `kind = input<PriceKind | null>(null)`). V248-14 and V248-15 use both.

**Why.** Spec § 1f: the `prev close` tag, the age wording and the P&L % / R format come from one component, so one position never reads differently on Trades and on the Dashboard. § 1d: the NOW cell of a prev-close row shows its value with a dated `prev close` tag instead of an age (index Decision 3); § 1e: a held row with neither price shows `no price yet` and the reason; § 1g: tags wrap under the value on a phone, values never truncate, each tag has an accessible name, nothing in the cell is focusable so a live update never moves focus.

- [ ] **Step 1: Write the failing component tests** — `frontend/src/app/ui/position-price.spec.ts`

Host-less, like `status-cell.spec.ts`: `TestBed.createComponent(PositionPrice)` + `setInput('row', row)`; providers `provideZonelessChangeDetection()`, `{ provide: CLOCK, useValue: signal(NOW) }`, `{ provide: LiveValuesStore, useValue: { status: signal(status) } }` (pattern of `ui/market-value.spec.ts`).

```ts
const FIX = JSON.parse(readFileSync(join(process.cwd(), 'src/app/testing/fixtures/v248-worst-case-row.json'), 'utf8'));
const rowOf = (name: string, o: Record<string, unknown> = {}) => ({ ...FIX.base, ...FIX.rows[name], ...o });
const NOW = Date.parse(FIX.now);
const regular: MarketStatus = { session: 'regular', last_close_at: '2026-11-24T21:00:00Z', stale_price_s: 120,
  stale_snapshot_s: 600, heartbeat: { beat_at: null, cadence_s: 30, stalled: false } };
// renderPrice(row, status = regular) and renderFigure(value, unit, kind) configure TestBed, render, return nativeElement.

it('a prev-close row shows its value, a dated prev close tag with an accessible name, and no age', () => {
  const el = renderPrice(rowOf('worst_case'));
  expect(el.querySelector('.pp-value')!.textContent!.trim()).toBe('1,234.56');
  const tag = el.querySelector('.pp-tag')!;
  expect(tag.textContent!.trim()).toBe('prev close 11-24');
  expect(tag.getAttribute('aria-label')).toBe(PREV_CLOSE_ARIA);
  expect(el.querySelector('.pp')!.getAttribute('title')).toBe('Previous close, 2026-11-24 -- not a live price');
  expect(el.querySelector('.mv-age')).toBeNull();
});
it('the worst case keeps its error in the regular session', () => {
  expect(renderPrice(rowOf('worst_case')).querySelector('.mv-err')?.textContent).toContain('refresh failed');
});
it('outside the regular session the same row shows no error', () => {
  const el = renderPrice(rowOf('worst_case'), { ...regular, session: 'extended' });
  expect(el.querySelector('.mv-err')).toBeNull();
  expect(el.querySelector('.pp-tag')).not.toBeNull();
});
it('a stale live row shows its price through sb-market-value with the error and no prev close tag', () => {
  const el = renderPrice(rowOf('stale_live'));
  expect(el.querySelector('sb-market-value')!.textContent).toContain('131.07');
  expect(el.querySelector('.mv-err')).not.toBeNull();
  expect(el.querySelector('.pp-tag')).toBeNull();
});
it('a fresh live row shows price and age only', () => {
  const asOf = new Date(NOW - 12_000).toISOString();
  const el = renderPrice(rowOf('stale_live', { price_as_of: asOf, price_error: null, price_error_at: null, current_price_stale: false }));
  expect(el.querySelector('.mv-age')!.textContent!.trim()).toBe('12 s ago');
  expect(el.querySelector('.mv-err')).toBeNull();
});
it('a held row with no price at all says so and why, never a bare dash', () => {
  const el = renderPrice(rowOf('no_price'));
  expect(el.querySelector('.pp-none')!.textContent!.trim()).toBe('no price yet');
  expect(el.querySelector('.pp-reason')!.textContent!.trim()).toBe(NO_PRICE_REASON);
  expect(el.textContent).not.toContain('—');
});
it('a held row with no live price but a cached close keeps the dated last-close note', () => {
  const el = renderPrice(rowOf('no_price', { last_close: 36.86, last_close_date: '2026-11-09' }));
  expect(el.querySelector('.last-close')!.textContent).toContain('36.86');
  expect(el.querySelector('.last-close')!.textContent).toContain('close 11-09');
  expect(el.querySelector('.pp-none')).toBeNull();
});
it('a PENDING row with no price shows no no-price note', () => {
  expect(renderPrice(rowOf('no_price', { status: 'PENDING', price_error: null })).querySelector('.pp-none')).toBeNull();
});
it('holds nothing focusable, so a live update cannot move focus', () => {
  for (const name of ['worst_case', 'stale_live', 'no_price'])
    expect(renderPrice(rowOf(name)).querySelectorAll('button, a, [tabindex]').length).toBe(0);
});
it('sb-position-figure renders the figure and a labelled suffix on prev close only', () => {
  const prev = renderFigure(-11.82, 'pct', 'prev_close');
  expect(prev.querySelector('.fig')!.textContent!.trim()).toBe('−11.82%');
  expect(prev.querySelector('.fig-suffix')!.textContent!.trim()).toBe('at prev close');
  expect(prev.querySelector('.fig-suffix')!.getAttribute('aria-label')).toBe(PREV_CLOSE_ARIA);
  expect(renderFigure(1.38, 'r', 'live').querySelector('.fig-suffix')).toBeNull();
  expect(renderFigure(null, 'r', 'prev_close').querySelector('.fig')!.textContent!.trim()).toBe('—');
});
```

The `.mv-err` assertions rest on V248-12's rule; they check presence and `refresh failed`, never V248-12's exact wording.

- [ ] **Step 2: Run it to see it fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/position-price.spec.ts`
Expected: FAIL — `./position-price` cannot be resolved.

- [ ] **Step 3: Implement `PositionPrice`** in `frontend/src/app/ui/position-price.ts`

Standalone, `OnPush`, `imports: [MarketValue]`. The template keys on a computed `mode(): 'live' | 'prev' | 'close' | 'none' | 'empty'` — `live`: a price, not prev close; `prev`: a price with `price_kind === 'prev_close'`; `close`: no price, `last_close` set; `none`: no price, no close, status in `HELD_STATUSES`; `empty`: anything else. Every branch keeps one `sb-market-value` so the spinner and the error rule stay in one place:

```html
@switch (mode()) {
  @case ('live') {
    <sb-market-value [asOf]="row().price_as_of ?? null" [refreshing]="row().price_refreshing ?? false"
      [error]="row().price_error ?? null" [errorAt]="row().price_error_at ?? null">{{ price() }}</sb-market-value>
  }
  @case ('prev') {
    <span class="pp prev" [title]="prevTitle()"><span class="pp-value">{{ price() }}</span>
      <span class="pp-tag" [attr.aria-label]="prevAria">{{ prevTag() }}</span></span>
    <sb-market-value [asOf]="null" [refreshing]="row().price_refreshing ?? false"
      [error]="row().price_error ?? null" [errorAt]="row().price_error_at ?? null" />
  }
  @case ('close') {
    <span class="last-close" [title]="'No live quote -- last close, ' + (row().last_close_date ?? 'date unknown')"><span
      class="last-close-value">{{ closePrice() }}</span> <span class="last-close-tag">close {{ closeTag() }}</span></span>
    <sb-market-value [asOf]="null" [refreshing]="row().price_refreshing ?? false"
      [error]="row().price_error ?? null" [errorAt]="row().price_error_at ?? null" />
  }
  @case ('none') {
    <span class="pp none"><span class="pp-none">{{ noPriceText }}</span> <span class="pp-reason">{{ noPriceReason }}</span></span>
    <sb-market-value [asOf]="null" [refreshing]="row().price_refreshing ?? false"
      [error]="row().price_error ?? null" [errorAt]="row().price_error_at ?? null" />
  }
  @default {
    <sb-market-value [asOf]="null" [refreshing]="row().price_refreshing ?? false"
      [error]="row().price_error ?? null" [errorAt]="row().price_error_at ?? null" />
  }
}
```

`price()` = `num(row().current_price)`; `closePrice()` = `num(row().last_close)`; `closeTag()` = `closeDateTag(row().last_close_date)`; `prevTag()` = `` `${PREV_CLOSE_TAG} ${closeDateTag(row().last_close_date)}`.trim() ``; `prevTitle()` = `` `Previous close, ${row().last_close_date ?? 'date unknown'} -- not a live price` ``; `prevAria = PREV_CLOSE_ARIA`, `noPriceText = NO_PRICE_TEXT`, `noPriceReason = NO_PRICE_REASON`. The `close` branch keeps today's classes and title (`trades.ts:458-461`) so `trades.spec.ts:500-512` keep passing once V248-14 swaps the cell. A doc comment above the class names spec § 1d / 1e / 1f and why the prev-close branch passes `asOf = null` (index Decision 3: the date replaces the age, and the error rule treats it as priceless).

Styles (tokens only):

```css
:host { display: inline-flex; flex-wrap: wrap; align-items: baseline; column-gap: var(--space-4); max-width: 100%; }
.pp, .last-close { color: var(--text-muted); display: inline-flex; flex-wrap: wrap; align-items: baseline; column-gap: var(--space-4); }
.pp-value, .last-close-value { font-family: var(--font-mono); font-variant-numeric: tabular-nums; white-space: nowrap; }
.pp-tag, .last-close-tag, .pp-reason { font-size: var(--text-micro); }
.pp-none { white-space: nowrap; }
@media (max-width: ${BREAKPOINTS.sm - 1}px) { :host, .pp { flex-direction: column; align-items: flex-start; } }
```

`--text-muted` is the token `.last-close` already uses for the same not-live grey (`trades.ts:693`), so the contrast is the one the Trades page already ships.

- [ ] **Step 4: Implement `PositionFigure`** in the same file

`sb-position-figure`, standalone, `OnPush`. `fig = computed(() => positionFigure(this.value(), this.unit(), this.kind()))`; template:

```html
<span class="fig">{{ fig().text }}</span>@if (fig().suffix; as s) {<span class="fig-suffix" [attr.aria-label]="aria">{{ s }}</span>}
```

with `aria = PREV_CLOSE_ARIA`. Styles: `:host { display: inline-flex; flex-wrap: wrap; align-items: baseline; column-gap: var(--space-4); }`, `.fig { white-space: nowrap; font-variant-numeric: tabular-nums; }`, `.fig-suffix { font-size: var(--text-micro); color: var(--text-muted); }`, below `BREAKPOINTS.sm` `:host { flex-direction: column; align-items: flex-start; }`. `.fig` sets no colour: the page wrapper carries `figureTone` (V248-14 / V248-15), so the money amount beside the figure takes the same tone.

- [ ] **Step 5: Run it to see it pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/position-price.spec.ts --include src/app/ui/position-format.spec.ts`
Expected: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ui/position-price.ts frontend/src/app/ui/position-price.spec.ts
git commit -m "feat(ui): v248 sb-position-price and sb-position-figure shared cells (V248-13b)"
```

### Task V248-14: Trades page: NOW, P&L % and R cells use the shared cells (three widths)

**Model:** sonnet — template swaps in one page plus two column text renderers, on components V248-13b already tests.

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.ts` (`#nowCell` l.453-463, `#pnlCell` l.528-533, `#rMultipleCell` l.538-541, `imports` l.165-195, styles l.693-695, `pnlClass` l.1123-1128)
- Modify: `frontend/src/app/workspaces/trades/trades.columns.ts` (`now` l.174, `pnl_pct` l.175, `r_multiple` l.194 column `value`s) — beyond the ledger's file list, see Why
- Test: `frontend/src/app/workspaces/trades/trades.spec.ts`, `frontend/src/app/workspaces/trades/trades.columns.spec.ts`

**Interfaces:**
- Consumes: V248-13b — `PositionPrice` (`sb-position-price`, `[row]`), `PositionFigure` (`sb-position-figure`, `[value]`, `unit`, `[kind]`); V248-13 — `figureTone(value, kind)`, `figureText(value, unit, kind)`, `positionPriceText(row)`, fixture `src/app/testing/fixtures/v248-worst-case-row.json`; V248-10 — `TradeRow.price_kind?`.
- Produces: none. `tradeColumns()` keeps its signature; only the three `value` renderers change, and the Dashboard (which renders the same `tradeColumns()`) inherits them.

**Why.** Spec § 1f: NOW, P&L % and R read the same on every screen, through one component and formatter. Today the Trades NOW cell inlines its own last-close span, P&L % and R print raw server figures with `pnlClass`, and nothing says a figure is at the prev close (§ 1d). The column `value` renderers in `trades.columns.ts` are the text both pages fall back to wherever a rich cell is not rendered — the expansion's "Hidden in this view" list (`trades.ts:994-999`), the data-table's text cells and row labels (`data-table.ts:941, 973`) and the Dashboard's `now` column, which has no rich cell today. Left alone they would print a prev close as a bare live-looking `1,234.56` (spec anti-goal 1), so they move to the shared text formatters here. `pnl_pct` has no `value` today (it falls back to the raw number); it gains one.

**Partner decision (2026-11-25): the Trades phone row matches the Dashboard.** Below 640 px the collapsed Trades row keeps NOW in the drawer (v95 C2), but its P&L % cell shows the current refresh error the same way V248-15 puts it in the Dashboard's P&L cell: the `· refresh failed: <error>` tag from `sb-market-value` (V248-12's `errorIsCurrent(errorAt, asOf)` rule, so only a current error shows), wrapping under the figure, never truncating it. Tablet and desktop are unchanged (the error already sits beside NOW). Add a page test at a phone width: a row whose `price_error` is current shows `refresh failed` in the collapsed row's P&L cell; a row whose error is older than its price shows none. V248-16's `expectedText` no longer drops `'refresh failed'` for Trades below 640 px.

- [ ] **Step 1: Write the failing page tests** — append to `frontend/src/app/workspaces/trades/trades.spec.ts`

Reuse `renderPriced` (l.479) and `cellText`; load the fixture as V248-13b's spec does:

```ts
const FIX = JSON.parse(readFileSync(join(process.cwd(), 'src/app/testing/fixtures/v248-worst-case-row.json'), 'utf8'));
const wc = (name: string, o: Partial<TradeRow> = {}) => ({ ...FIX.base, ...FIX.rows[name], ...o }) as TradeRow;

describe('Trades - shared position cells (v248)', () => {
  it('the NOW cell of a prev-close row is sb-position-price with a dated prev close tag', () => {
    const el = renderPriced([wc('worst_case')]);
    const now = el.querySelector('tbody sb-position-price')!;
    expect(now.querySelector('.pp-value')!.textContent!.trim()).toBe('1,234.56');
    expect(cellText(now.querySelector('.pp-tag')!)).toBe('prev close 11-24');
  });

  it('P&L % and R carry "at prev close" and read grey, not red', () => {
    const el = renderPriced([wc('worst_case')]);
    const figs = [...el.querySelectorAll('tbody sb-position-figure')];
    const texts = figs.map((f) => f.querySelector('.fig')!.textContent!.trim());
    expect(texts).toContain('−11.82%');
    expect(texts).toContain('−1.65');
    for (const f of figs) {
      expect(f.querySelector('.fig-suffix')!.textContent!.trim()).toBe('at prev close');
      expect(f.parentElement!.classList).toContain('muted');
      expect(f.parentElement!.classList).not.toContain('neg');
    }
  });

  it('a live row keeps its sign colour and no suffix', () => {
    const el = renderPriced([wc('stale_live')]);
    const figs = [...el.querySelectorAll('tbody sb-position-figure')];
    expect(figs.map((f) => f.querySelector('.fig')!.textContent!.trim())).toEqual(expect.arrayContaining(['+9.23%', '+1.38']));
    for (const f of figs) {
      expect(f.querySelector('.fig-suffix')).toBeNull();
      expect(f.parentElement!.classList).toContain('pos');
    }
  });

  it('a held row with no price at all says "no price yet" in NOW, never a bare dash', () => {
    const el = renderPriced([wc('no_price')]);
    const now = el.querySelector('tbody sb-position-price')!;
    expect(cellText(now)).toContain('no price yet');
    expect(cellText(now)).not.toBe('—');
  });

  it('the P&L amount stays beside the figure', () => {
    const el = renderPriced([wc('stale_live', { realized_pnl_amount: 132.84 })]);
    expect(el.querySelector('tbody .pnl-amount')).not.toBeNull();
  });
});
```

The existing `'an unpriced row shows its last close greyed and dated…'` and `'a priced row shows no last-close note'` tests (l.500-512) stay as they are and must keep passing: V248-13b's `close` branch keeps the `.last-close` markup.

- [ ] **Step 2: Write the failing column text tests** — append to `frontend/src/app/workspaces/trades/trades.columns.spec.ts`

```ts
describe('tradeColumns text renderers (v248)', () => {
  const cols = tradeColumns();
  const val = (key: string, row: Partial<TradeRow>) => cols.find((c) => c.key === key)!.value!(row as TradeRow);
  const held = { status: 'ACTIVE', current_price: null, last_close: null } as Partial<TradeRow>;

  it('NOW says prev close or no price yet instead of a live-looking number', () => {
    expect(val('now', { ...held, current_price: 1234.56, price_kind: 'prev_close', last_close: 1234.56 })).toBe('1,234.56 prev close');
    expect(val('now', held)).toBe('no price yet');
    expect(val('now', { ...held, current_price: 131.07, price_kind: 'live' })).toBe('131.07');
  });
  it('P&L % and R carry the suffix on a prev-close row only', () => {
    expect(val('pnl_pct', { pnl_pct: -11.82, price_kind: 'prev_close' })).toBe('−11.82% at prev close');
    expect(val('r_multiple', { r_multiple: -1.65, price_kind: 'prev_close' })).toBe('−1.65 at prev close');
    expect(val('r_multiple', { r_multiple: 2, status: 'CLOSED' })).toBe('+2.00');
    expect(val('pnl_pct', { pnl_pct: null })).toBe('—');
  });
});
```

(`tradeColumns` is already exported from `trades.columns.ts`; import it with `TradeRow` if the spec does not yet.)

- [ ] **Step 3: Run them to see them fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/trades/trades.spec.ts --include src/app/workspaces/trades/trades.columns.spec.ts`
Expected: FAIL — no `sb-position-price` / `sb-position-figure` in the rows; `now` prints `1,234.56`, `pnl_pct` has no `value`.

- [ ] **Step 4: Swap the cells in `trades.ts`**

- `#nowCell`: the whole `@if … @else …` body (l.454-462) becomes `<sb-position-price [row]="row" />`; delete the old comment about the last close and keep the v201 one, now saying the NOW cell is the shared `sb-position-price` (spec v248 § 1f).
- `#pnlCell`:

```html
<span [sbFlash]="row.pnl_pct" [class]="tone(row.pnl_pct, row.price_kind)">
  <sb-position-figure [value]="row.pnl_pct" unit="pct" [kind]="row.price_kind ?? null" />
  <span class="pnl-amount"> ({{ fmtMoney(row.realized_pnl_amount) }})</span>
</span>
```

- `#rMultipleCell`:

```html
<span [sbFlash]="row.r_multiple" [class]="tone(row.r_multiple, row.price_kind)"><sb-position-figure [value]="row.r_multiple" unit="r" [kind]="row.price_kind ?? null" /></span>
<sb-magnitude [value]="row.r_multiple" [max]="maxRMultiple()" />
```

- `imports`: add `PositionPrice`, `PositionFigure` (from `../../ui/position-price`); keep `MarketValue` (the page header's prices-as-of still uses it).
- Class: `protected readonly tone = figureTone;` (import from `../../ui/position-format`). Delete `pnlClass` (l.1123-1128) once `git grep -n "pnlClass" frontend/src/app/workspaces/trades/` shows no other use, and update the style comment at l.705-706 that names it to name `tone()` (`figureTone`).
- Styles: delete `.last-close`, `.last-close-value`, `.last-close-tag` (l.693-695: the markup now lives in `sb-position-price`, whose encapsulated styles carry them); add `.muted { color: var(--text-muted); }` beside the page's other tone rules. `.pos` / `.neg` stay global (`styles.css:149-150`).
- Delete `fmtNum` only if nothing else in the template uses it (the expansion's Quality row at l.596 does — keep it).

- [ ] **Step 5: Change the three column renderers in `trades.columns.ts`**

- `now`: `value: (row) => positionPriceText(row)`.
- `pnl_pct`: add `value: (row) => figureText(row.pnl_pct, 'pct', row.price_kind)`.
- `r_multiple`: `value: (row) => figureText(row.r_multiple, 'r', row.price_kind)`; keep the v54 comment (no unit, the header names it) and add one line: v248 § 1f, a prev-close figure says so in text too.
- Import `figureText`, `positionPriceText` from `../../ui/position-format`; drop `num` / `signed` from the `../../ui/format` import only if no other column still uses them (`entry`, `stop_loss`, … use `num` — keep it).

- [ ] **Step 6: Run the specs to see them pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/trades/trades.spec.ts --include src/app/workspaces/trades/trades.columns.spec.ts --include src/app/ui/position-price.spec.ts`
Expected: `0 failed`. A pre-existing assertion that pinned the old raw `pnl_pct` / `r_multiple` text of a hidden field or a `pnlClass` class name is now wrong by design: update it to the shared formatter's output (`+10.00%`, `+2.00`, class from `figureTone`) and name it in the task report.

- [ ] **Step 7: Check the three widths**

With the local admin and `ng serve` up (`docs/claude/ui-design.md` § Checklist; log in with `.env`'s `ADMIN_USERNAME` / `ADMIN_PASSWORD`, loaded in-process, never printed), run `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440` and read the `/trades` findings in `<out>/audit.json`.
Expected: no new unallowed finding on `/trades` (exit 0, or only findings that also exist on `main` before this task). V248-16 repeats this with the worst-case rows forced in.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/workspaces/trades/trades.ts frontend/src/app/workspaces/trades/trades.columns.ts frontend/src/app/workspaces/trades/trades.spec.ts frontend/src/app/workspaces/trades/trades.columns.spec.ts
git commit -m "feat(ui): v248 Trades NOW, P&L % and R through the shared position cells (V248-14)"
```

### Task V248-15: Dashboard Open positions: NOW, P&L % and R through the shared cells, `errorAt` passed (three widths)

**Model:** sonnet — template swaps in one page on components V248-13b already tests; the one judgement (where a prev-close row's error shows when NOW is off-screen) is pinned below.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (`#pnlCell` l.474-517, `#rMultipleCell` l.530-542, new `#nowCell` beside them, `viewChild`s l.866-884, `columns` cells map l.957-967, `imports` l.177+, `pnlClass` l.1059)
- Test: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

**Interfaces:**
- Consumes: V248-13b — `PositionPrice` (`sb-position-price`, `[row]`), `PositionFigure` (`sb-position-figure`, `[value]`, `unit`, `[kind]`); V248-13 — `figureTone`, `NO_PRICE_REASON`, fixture `src/app/testing/fixtures/v248-worst-case-row.json`, StatusCell's `no price yet`; V248-12 — `MarketValue.errorAt`; V248-14 — the `now` / `pnl_pct` / `r_multiple` column text (`tradeColumns()`, shared).
- Produces: none.

**Why.** Spec § 1f names the Dashboard's positions table as the third screen that must read like the other two. The table renders the shared `tradeColumns()` set, `now` included (default `COMPACT_COLUMNS`), but wires no `now` cell, so today NOW is the plain column text; it gets `sb-position-price` here. P&L % and R move to `sb-position-figure` with `figureTone`, so a prev-close row reads `−11.82% at prev close` in grey, as on Trades. Every `sb-market-value` on this page gets `[errorAt]` so V248-12's rule (error only when newer than the price) applies here too. A prev-close row has `price_as_of = null`, so its P&L figure cannot sit inside `sb-market-value` (it hides a value with no as-of, `market-value.ts` `valueHidden`); on a phone the NOW column is not inline (v95 C2: ticker, plan, P&L %), so the P&L cell adds an empty `sb-market-value` after the figure on a prev-close row — the same pattern `sb-position-price` uses — and the regular-session error stays visible on the phone row.

- [ ] **Step 1: Write the failing tests** — append to `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

Reuse `seed()`, `payload()` and `tradeRow()`; the helper is the v201 `withActiveRow` (l.719-729) widened to several rows:

```ts
describe('Dashboard - shared position cells (v248)', () => {
  const FIX = JSON.parse(readFileSync(join(process.cwd(), 'src/app/testing/fixtures/v248-worst-case-row.json'), 'utf8'));
  const wc = (name: string, o: Partial<TradeRow> = {}) => ({ ...FIX.base, ...FIX.rows[name], status: 'ACTIVE', ...o }) as TradeRow;
  const regular = { session: 'regular', last_close_at: '2026-11-24T21:00:00Z', stale_price_s: 120, stale_snapshot_s: 600,
    heartbeat: { beat_at: null, cadence_s: 30, stalled: false } } as const;

  async function withActive(rows: TradeRow[]) {
    const { fixture, backend } = seed();
    (TestBed.inject(LiveValuesStore) as unknown as FakeLiveValues).status.set({ ...regular });
    fixture.detectChanges();
    for (const req of backend.match((r) => r.url === '/api/v1/trades')) {
      const active = req.request.params.get('status') === 'ACTIVE';
      req.flush({ items: active ? rows : [], total: active ? rows.length : 0, page: 1, per_page: 20 });
    }
    backend.expectOne('/api/v1/dashboard?mode=today').flush(payload({ lifecycle: { ACTIVE: rows.length } as never }));
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }
  const cellOf = (el: Element) => el.closest('td, [role="cell"]')!;
  const figs = (el: HTMLElement) => [...el.querySelectorAll('sb-positions-table tbody sb-position-figure')];

  it('the NOW column is sb-position-price with the dated prev close tag', async () => {
    const el = await withActive([wc('worst_case')]);
    const now = el.querySelector('sb-positions-table tbody sb-position-price')!;
    expect(now.querySelector('.pp-tag')!.textContent!.trim()).toBe('prev close 11-24');
  });

  it('P&L % and R read "at prev close" in grey on a prev-close row', async () => {
    const el = await withActive([wc('worst_case')]);
    expect(figs(el).map((f) => f.querySelector('.fig')!.textContent!.trim())).toEqual(expect.arrayContaining(['−11.82%', '−1.65']));
    for (const f of figs(el)) {
      expect(f.querySelector('.fig-suffix')!.textContent!.trim()).toBe('at prev close');
      expect(f.parentElement!.classList).toContain('muted');
    }
  });

  it("a prev-close row's current error shows in its P&L cell, so the phone row carries it", async () => {
    const el = await withActive([wc('worst_case')]);
    const pnl = figs(el).find((f) => f.querySelector('.fig')!.textContent!.includes('%'))!;
    expect(cellOf(pnl).querySelector('.mv-err')?.textContent).toContain('refresh failed');
  });

  it("a stale live row's P&L sits in sb-market-value and shows the newer error", async () => {
    const el = await withActive([wc('stale_live')]);
    const pnl = figs(el).find((f) => f.querySelector('.fig')!.textContent!.includes('%'))!;
    expect(pnl.closest('sb-market-value')).not.toBeNull();
    expect(cellOf(pnl).querySelector('.mv-err')).not.toBeNull();
    expect(pnl.parentElement!.classList).toContain('pos');
  });

  it('an error older than the price is not shown', async () => {
    const asOf = new Date(Date.now() - 30_000).toISOString();
    const el = await withActive([wc('stale_live', { price_as_of: asOf, price_age_s: 30, current_price_stale: false,
      price_error_at: new Date(Date.now() - 600_000).toISOString() })]);
    expect(el.querySelector('sb-positions-table tbody .mv-err')).toBeNull();
  });

  it('a held row with no price at all says "no price yet" in NOW and in STATUS, with the reason', async () => {
    const el = await withActive([wc('no_price')]);
    expect(el.querySelector('sb-positions-table tbody sb-position-price .pp-none')!.textContent!.trim()).toBe('no price yet');
    const status = el.querySelector('sb-positions-table tbody sb-status-cell')!;
    expect(status.querySelector('.hint')!.textContent!.trim()).toBe('no price yet');
    expect(status.querySelector('.reason')!.textContent!.trim()).toBe(NO_PRICE_REASON);
  });

  it('a PENDING row keeps its projected P&L and R, with no suffix', async () => {
    const el = await withActive([wc('stale_live', { status: 'PENDING', pnl_pct: null, r_multiple: null, price_kind: undefined })]);
    expect(el.querySelector('sb-positions-table tbody .pnl-plan sb-market-value')).not.toBeNull();
    expect(el.querySelector('sb-positions-table tbody .fig-suffix')).toBeNull();
    expect(el.querySelector('sb-positions-table tbody .expected')).not.toBeNull();
  });
});
```

Add the imports the block needs (`readFileSync`, `join`, `LiveValuesStore`, `FakeLiveValues`, `NO_PRICE_REASON`) if the spec lacks them. If `seed()` provides `LiveValuesStore` with something other than `FakeLiveValues`, set the status through whatever stub it provides (its `status` signal), not a new provider.

- [ ] **Step 2: Run it to see it fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: FAIL — no `sb-position-price` / `sb-position-figure` in the positions table.

- [ ] **Step 3: Wire the NOW cell**

Add beside `#statusCell` (l.388):

```html
<!-- v248 § 1f: NOW reads as on Trades -- the shared sb-position-price. -->
<ng-template #nowCell let-row>
  <sb-position-price [row]="row" />
</ng-template>
```

Add `private readonly nowCell = viewChild.required<TemplateRef<RowContext<TradeRow>>>('nowCell');` beside the others (l.866-884) and `now: this.nowCell(),` to the `cells` map in `columns` (l.957-967).

- [ ] **Step 4: Swap P&L % and R**

`#pnlCell`, first branch (`row.pnl_pct !== null`):

```html
@if (row.price_as_of || row.price_refreshing) {
  <sb-market-value [asOf]="row.price_as_of ?? null" [refreshing]="row.price_refreshing ?? false"
    [error]="row.price_error ?? null" [errorAt]="row.price_error_at ?? null">
    <span [sbFlash]="row.pnl_pct" [class]="tone(row.pnl_pct, row.price_kind)">
      <sb-position-figure [value]="row.pnl_pct" unit="pct" [kind]="row.price_kind ?? null" />
      <span class="pnl-amount"> ({{ fmtMoney(row.realized_pnl_amount) }})</span>
    </span>
  </sb-market-value>
} @else {
  <span [sbFlash]="row.pnl_pct" [class]="tone(row.pnl_pct, row.price_kind)">
    <sb-position-figure [value]="row.pnl_pct" unit="pct" [kind]="row.price_kind ?? null" />
    <span class="pnl-amount"> ({{ fmtMoney(row.realized_pnl_amount) }})</span>
  </span>
  @if (row.price_kind === 'prev_close') {
    <!-- A prev close has no as-of, so the figure cannot sit inside sb-market-value (it hides a
         value with no as-of); this empty one carries the spinner and the current error, so a
         phone row, where NOW is not inline, still shows a real failure (spec v248 § 1g). -->
    <sb-market-value [asOf]="null" [refreshing]="row.price_refreshing ?? false"
      [error]="row.price_error ?? null" [errorAt]="row.price_error_at ?? null" />
  }
}
```

Projected branch (`.pnl-plan`): the `sb-market-value` gains `[errorAt]="row.price_error_at ?? null"`; the live figure becomes `<span [sbFlash]="livePnlPct(row)" [class]="tone(livePnlPct(row), null)"><sb-position-figure [value]="livePnlPct(row)" unit="pct" /> …amount as today…</span>`; the `→ TP - SL` projections keep `fmtPct`.

`#rMultipleCell`: the real branch becomes `<span [sbFlash]="row.r_multiple" [class]="tone(row.r_multiple, row.price_kind)"><sb-position-figure [value]="row.r_multiple" unit="r" [kind]="row.price_kind ?? null" /></span>` + the existing `sb-magnitude`; the projected branch keeps `class="expected"` and becomes `<span class="expected" [sbFlash]="expectedR(row)" [class]="tone(expectedR(row), null)"><sb-position-figure [value]="expectedR(row)" unit="r" /></span>` + `sb-magnitude`.

Class: `protected readonly tone = figureTone;`; `imports` gains `PositionPrice`, `PositionFigure`. Keep `pnlClass` only if `git grep -n "pnlClass" frontend/src/app/workspaces/dashboard/dashboard.ts` still shows a use outside these three cells (the Closed table, l.625's comment); otherwise delete it and fix that comment to name `tone()`. Add `.muted { color: var(--text-muted); }` to the page styles if no rule matches it yet. Every other `sb-market-value` in the file that shows a price with `[error]` gains `[errorAt]="… .price_error_at ?? null"` from the same row (`git grep -n "sb-market-value" frontend/src/app/workspaces/dashboard/dashboard.ts`).

- [ ] **Step 5: Run the specs to see them pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/dashboard/positions-table.spec.ts`
Expected: `0 failed`. The v201 `'Dashboard price age'` tests (l.715-760) keep passing unchanged; a pre-existing assertion on the old `pnlClass` class of a P&L or R span updates to `figureTone`'s class and is named in the task report.

- [ ] **Step 6: Check the three widths**

With the local admin and `ng serve` up (log in with `.env`'s `ADMIN_USERNAME` / `ADMIN_PASSWORD`, in-process, never printed), run `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440` and read the `/dashboard` findings in `<out>/audit.json`.
Expected: no new unallowed finding on `/dashboard` (exit 0, or only findings that also exist on `main` before this task). V248-16 repeats this with the worst-case rows forced in.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git commit -m "feat(ui): v248 Dashboard open positions NOW, P&L % and R through the shared cells (V248-15)"
```

### Task V248-16: Closing check: worst-case rows on `/dashboard` and `/trades` at 390/768/1440 (route-intercepted) + `layout-audit.mjs`; CI green

**Model:** sonnet — a Playwright script cloned from the `v246-bar-alignment-check` precedent, with its pure helpers under `node --test`.

**Files:**
- Create: `frontend/scripts/v248-price-rows-check-lib.mjs` (pure helpers, no browser)
- Create: `frontend/scripts/v248-price-rows-check-lib.test.mjs` (`node --test`; picked up by `tests/scripts/test_node_scripts.py`, which globs `frontend/scripts/*.test.mjs` — no suite edit)
- Create: `frontend/scripts/v248-price-rows-check.mjs` (the Playwright driver)

**Interfaces:**
- Consumes: V248-13 — `frontend/src/app/testing/fixtures/v248-worst-case-row.json` (`now`, `base`, `rows.worst_case | stale_live | no_price`) and the copy in `ui/position-format.ts`; V248-13b / V248-14 / V248-15 — the rendered classes `.pp-value`, `.pp-tag`, `.pp-none`, `.fig`, `.fig-suffix`, `.last-close-value`, `.mv-err`; `exitCode`, `formatResult` from `frontend/scripts/shell-nav-check-lib.mjs`; the layout audit's `audit.json` (`unallowed: [{ route, width, check, selector, detail }]`).
- Produces: none (a gate, not an API).

**Why.** Spec § 1g: the gate is the layout audit at the three widths, driven by Playwright, with the worst-case row as a named fixture; the NOW, P&L % and R values are never truncated, and the table scrolls inside its own container, never the page. `layout-audit.mjs` visits live routes and has no way to seed a row (brief § 4), so this check forces the fixture rows in by intercepting the two reads the pages make — `GET /api/v1/trades` (both pages, the Dashboard's positions table through its own `TradesStore`) and `GET /api/v1/market/updates` (the session the age wording and the error rule read) — while the real audit run supplies the overflow/tap/text/baseline findings for the same routes. Index Goal: "renders the worst-case row at 390, 768 and 1440 with no value truncated, and `layout-audit.mjs` reports nothing new on `/dashboard` and `/trades`; CI is green after the push". This is the plan's last task, so it also owns the CI watch: no plan task runs the full suite.

- [ ] **Step 1: Write the failing helper tests** — `frontend/scripts/v248-price-rows-check-lib.test.mjs`

```js
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  DEFAULT_BASE, EXPECTED_TEXT, FIXTURE, PAGES, VIEWPORTS,
  auditVerdict, clipVerdict, expectedText, fixtureRows, isMarketUpdates, isTradesList,
  marketUpdatesBody, pageOverflowVerdict, parseArgs, tradesBody,
} from './v248-price-rows-check-lib.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const fix = JSON.parse(readFileSync(FIXTURE, 'utf8'));

test('parseArgs defaults to the local admin and takes --out and --audit', () => {
  assert.deepEqual(parseArgs([]), { base: DEFAULT_BASE, out: null, audit: null });
  assert.deepEqual(parseArgs(['--base', 'http://localhost:4123/', '--audit', 'a.json']),
    { base: 'http://localhost:4123', out: null, audit: 'a.json' });
  assert.throws(() => parseArgs(['--widths', '390']), /unknown or incomplete flag --widths/);
});

test('checks phone, tablet and desktop on the two pages', () => {
  assert.deepEqual(VIEWPORTS.map((v) => v.width), [390, 768, 1440]);
  assert.deepEqual(PAGES.map((p) => p.path), ['/dashboard', '/trades']);
});

test('fixtureRows merges base and rows and moves the timestamps to now, keeping nulls', () => {
  const now = Date.parse(fix.now) + 3_600_000;
  const rows = fixtureRows(fix, now);
  assert.deepEqual(rows.map((r) => r.ticker), ['DOCU', 'HOOD', 'CRWV']);
  const [wc, live, none] = rows;
  assert.equal(wc.price_as_of, null);
  assert.equal(wc.price_error_at, '2026-11-25T15:59:00.000Z');
  assert.equal(live.price_as_of, '2026-11-25T15:46:00.000Z');
  assert.equal(wc.price_kind, 'prev_close');
  assert.equal('price_kind' in none, false);
  assert.equal(fix.rows.stale_live.price_as_of, '2026-11-25T14:46:00Z');   // input untouched
});

test('intercepts exactly the trades list and the market updates reads', () => {
  assert.equal(isTradesList(new URL('http://x/api/v1/trades?status=ACTIVE&page=1')), true);
  assert.equal(isTradesList(new URL('http://x/api/v1/trades/abc')), false);
  assert.equal(isTradesList(new URL('http://x/api/v1/trades/cancels')), false);
  assert.equal(isMarketUpdates(new URL('http://x/api/v1/market/updates?since=1')), true);
  assert.equal(isMarketUpdates(new URL('http://x/api/v1/market/refresh')), false);
});

test('tradesBody serves the held rows to a held or unfiltered query and nothing to the others', () => {
  const rows = fixtureRows(fix, Date.parse(fix.now));
  const body = tradesBody(rows, new URL('http://x/api/v1/trades?status=ACTIVE&per_page=12'));
  assert.equal(body.items.length, 3);
  assert.equal(body.total, 3);
  assert.equal(body.per_page, 12);
  assert.equal(body.market_meta.incomplete, true);
  assert.equal(tradesBody(rows, new URL('http://x/api/v1/trades')).items.length, 3);
  assert.equal(tradesBody(rows, new URL('http://x/api/v1/trades?status=CLOSED')).items.length, 0);
  assert.equal(tradesBody(rows, new URL('http://x/api/v1/trades?status=PENDING')).total, 0);
});

test('marketUpdatesBody is a regular session with no quotes', () => {
  const body = marketUpdatesBody(Date.parse(fix.now));
  assert.deepEqual(body.quotes, []);
  assert.equal(body.status.session, 'regular');
  assert.equal(body.status.stale_price_s, 120);
  assert.equal(body.status.heartbeat.stalled, false);
});

test('expected text matches the component copy, minus the error on the Trades phone row', () => {
  const src = readFileSync(join(HERE, '..', 'src', 'app', 'ui', 'position-format.ts'), 'utf8');
  for (const copy of ['no trade and no daily close cached', 'at prev close', 'no price yet', 'prev close'])
    assert.ok(src.includes(`'${copy}'`) && EXPECTED_TEXT.includes(copy), copy);
  assert.ok(expectedText('dashboard', 390).includes('refresh failed'));
  assert.ok(!expectedText('trades', 390).includes('refresh failed'));
  assert.ok(expectedText('trades', 768).includes('refresh failed'));
});

test('verdicts name what failed and pass a clean page', () => {
  assert.deepEqual(clipVerdict([{ name: '.fig −11.82%', clippedBy: null }]), []);
  assert.deepEqual(clipVerdict([{ name: '.pp-value 1,234.56', clippedBy: 'td.cell overflow:hidden' }]),
    ['.pp-value 1,234.56 clipped by td.cell overflow:hidden']);
  assert.equal(pageOverflowVerdict(390, 390), null);
  assert.match(pageOverflowVerdict(512, 390), /page is 512px wide at 390/);
  const unallowed = [
    { route: '/trades', width: 390, check: 'clipped', selector: 'td', detail: 'x' },
    { route: '/risk', width: 390, check: 'tap', selector: 'a', detail: 'y' },
  ];
  assert.deepEqual(auditVerdict(unallowed), ['/trades @390 clipped td -- x']);
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `node --test frontend/scripts/v248-price-rows-check-lib.test.mjs`
Expected: FAIL — `Cannot find module './v248-price-rows-check-lib.mjs'`.

- [ ] **Step 3: Implement `v248-price-rows-check-lib.mjs`**

Header comment: v248 V248-16, spec § 1g, "pure helpers, no browser, so `node --test` covers all of it" (as `v246-bar-alignment-check-lib.mjs`). Exports:

- `export { exitCode, formatResult } from './shell-nav-check-lib.mjs';`
- `DEFAULT_BASE = 'http://localhost:1234'`; `VIEWPORTS` = `phone 390×844`, `tablet 768×1024`, `desktop 1440×900` (frozen, `{ name, width, height }`); `PAGES` = `[{ name: 'dashboard', path: '/dashboard', scope: 'sb-positions-table' }, { name: 'trades', path: '/trades', scope: 'main' }]`.
- `FIXTURE` = absolute path of `../src/app/testing/fixtures/v248-worst-case-row.json` from this file (`fileURLToPath(new URL(…, import.meta.url))`).
- `parseArgs(argv)` — same contract as v246's (`--base`, `--out`, `--audit`; trailing slashes stripped from `--base`; anything else throws `unknown or incomplete flag <flag>`).
- `fixtureRows(fixture, nowMs)` — `['worst_case', 'stale_live', 'no_price'].map((n) => ({ ...fixture.base, ...fixture.rows[n] }))`, then each non-null `price_as_of` / `price_error_at` moved by `nowMs - Date.parse(fixture.now)` and written with `toISOString()`; never mutates `fixture`.
- `isTradesList(url)` → `url.pathname === '/api/v1/trades'`; `isMarketUpdates(url)` → `url.pathname === '/api/v1/market/updates'`.
- `tradesBody(rows, url)` — the `status` query (comma list, upper-cased) absent or naming `ACTIVE` or `PARTIAL` → all `rows`, else `[]`; returns `{ items, total: items.length, page: 1, per_page: Number(url.searchParams.get('per_page')) || 20, market_meta: { as_of: null, refreshing: false, stale_count: 1, missing_count: 1, incomplete: true, source: 'request' } }`. Serving every held row to the Active tab puts the PARTIAL `no_price` row on the Dashboard's default tab too.
- `marketUpdatesBody(nowMs)` → `{ cursor: 'v248-check', quotes: [], snapshots: [], status: { session: 'regular', last_close_at: <nowMs − 18 h ISO>, stale_price_s: 120, stale_snapshot_s: 600, heartbeat: { beat_at: <nowMs ISO>, cadence_s: 30, stalled: false } } }`.
- `EXPECTED_TEXT` (frozen) = `['prev close', 'at prev close', 'refresh failed', 'no price yet', 'no trade and no daily close cached']`; `expectedText(pageName, width)` returns the full list for every page and width: the Trades phone row shows the current error in its P&L % cell (partner decision 2026-11-25, V248-14), while NOW stays one tap away in the drawer (v95 C2).
- `clipVerdict(items)` → `${name} clipped by ${clippedBy}` for each item with a non-null `clippedBy`.
- `pageOverflowVerdict(docWidth, viewportWidth)` → null when `docWidth <= viewportWidth`, else `` `page is ${docWidth}px wide at ${viewportWidth}: the table must scroll inside its container` ``.
- `auditVerdict(unallowed, routes = PAGES.map((p) => p.path))` → `` `${route} @${width} ${check} ${selector} -- ${detail}` `` for every unallowed finding on those routes (every check: the index Goal says "nothing new").

- [ ] **Step 4: Run the helper tests to see them pass**

Run: `node --test frontend/scripts/v248-price-rows-check-lib.test.mjs` then `python scripts/dev/testrun.py file tests/scripts/test_node_scripts.py`
Expected: all `node --test` cases pass; pytest `0 failed`.

- [ ] **Step 5: Implement the driver** — `frontend/scripts/v248-price-rows-check.mjs`

Clone `v246-bar-alignment-check.mjs`'s skeleton: shebang; header comment (what it checks, usage `node frontend/scripts/v248-price-rows-check.mjs [--base http://localhost:1234] [--out DIR] [--audit FILE]`, ".env ADMIN_USERNAME/ADMIN_PASSWORD stay in this process, never printed", exit 0 / 1 failed / 2 cannot run); `check(name, ok, detail)` recording into `results`; `signedInState(browser, base)` copied verbatim (loads `.env` with `process.loadEnvFile`, posts `/api/v1/session` from the page, never logs the values); `main()` writing `<out>/results.json` and returning `exitCode(results)`; default out `join(tmpdir(), 'swingbot-v248-price-rows')`.

Per viewport, one context (`storageState`, `viewport`, `serviceWorkers: 'block'`, `hasTouch: width < 1024`, `isMobile: width < 640`) and, before any navigation:

```js
const fixture = JSON.parse(readFileSync(FIXTURE, 'utf8'));
await context.route((url) => isTradesList(url), (route) =>
  route.fulfill({ json: tradesBody(fixtureRows(fixture, Date.now()), new URL(route.request().url())) }));
await context.route((url) => isMarketUpdates(url), (route) => route.fulfill({ json: marketUpdatesBody(Date.now()) }));
```

Per page (`PAGES`): `goto(base + path, { waitUntil: 'domcontentloaded' })`; wait up to 60 s for `page.locator(scope).getByText('DOCU').first()` to be visible (on failure: `check('render-<page>@<width>', false, <first line of the error>)` and move on); `await page.evaluate(() => document.fonts.ready.then(() => undefined))`; then:

- `render-<page>@<width>`: all three tickers (`DOCU`, `HOOD`, `CRWV`) visible inside `scope`.
- `text-<page>@<width>`: every string of `expectedText(page.name, width)` appears in `scope`'s `innerText`; detail lists the missing ones.
- `clip-<page>@<width>`: `clipVerdict(await page.evaluate(measureClips, scope))` is empty. `measureClips(scope)` runs in the page, self-contained: for each element matching `.pp-value, .pp-none, .fig, .last-close-value` inside `scope` that has a non-zero rect, walk `parentElement` up to and including the nearest `td` / `[role="cell"]` / `dd`; the first ancestor whose computed `overflow-x` is `hidden` or `clip` and whose rect does not contain the element's (±1 px), or whose `text-overflow` is `ellipsis` with `scrollWidth > clientWidth + 1`, is reported as `clippedBy` (`tag.class overflow:<value>`); otherwise `null`. `name` = `` `${el.className} ${el.textContent.trim()}` ``. A horizontal scroll box (`overflow-x: auto | scroll`) is not a clip: the spec allows the table to scroll inside its container.
- `page-overflow-<page>@<width>`: `pageOverflowVerdict(document.documentElement.scrollWidth, window.innerWidth)` is null.
- a screenshot of `scope` to `<out>/<page>@<width>.png`.

With `--audit FILE`: read its `unallowed` (exit 2 via `CannotRun` if it is not an array) and `check('layout-audit-v248-pages', found.length === 0, found.join('; '))` with `auditVerdict`; without it, print `no --audit file: the layout-audit findings were not checked` (as v246 does).

- [ ] **Step 6: Run the closing check**

With the local admin serving the built SPA at `http://localhost:1234` (as for V246-18; log in with `.env`'s `ADMIN_USERNAME` / `ADMIN_PASSWORD`, loaded in-process, never printed):

```bash
node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440 --out "$TEMP/v248-audit"
node frontend/scripts/v248-price-rows-check.mjs --base http://localhost:1234 --audit "$TEMP/v248-audit/audit.json"
```

Expected: the second command ends `N/N passed` (2 pages × 3 widths × 4 checks + 1 audit check = 25) and exits 0. A failure is fixed in the page or component that owns it (V248-13b / V248-14 / V248-15 files) and the check re-run; open the `<page>@<width>.png` shots to confirm by eye that the `prev close` tag and the `refresh failed` meta wrap under the value at 390 and sit inline at 768 and 1440. Never add a `layout-audit.allow.json` entry for a finding on these two pages to make the gate pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/scripts/v248-price-rows-check-lib.mjs frontend/scripts/v248-price-rows-check-lib.test.mjs frontend/scripts/v248-price-rows-check.mjs
git commit -m "test(ui): v248 closing check, worst-case rows at three widths plus layout audit (V248-16)"
```

- [ ] **Step 8: CI is the full suite — watch it to green**

No task in this plan runs the full suite locally (index Global Constraints). After the controller merges and pushes, watch the pipeline: `gh run list --branch main --limit 3`, then `gh run watch <id> --exit-status`.
Expected: every job green — the `ng test` job (all frontend specs, the shared parity fixture spec of V248-10 included), the Python suite jobs from `tests/suites.toml` (the V248-2 parity test, `tests/scripts/test_node_scripts.py` running this task's helper tests), and `scripts/dev/complexity_gate.py`. A failing test is fixed and re-run alone (`python scripts/dev/testrun.py file <test>` or `cd frontend && npx ng test --watch=false --include <spec>`), committed as a scoped fix, pushed, and the run watched again until it is green. Then the plan is ready for `/close-out` (version bump, spec § Rollout checks after deploy).
