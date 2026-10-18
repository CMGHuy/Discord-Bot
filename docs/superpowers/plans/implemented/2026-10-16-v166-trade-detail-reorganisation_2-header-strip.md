# v166 Trade detail reorganisation. Part 2: outcome strip and identity line

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task TD5:" -A 400 <this file>`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v166-trade-detail-reorganisation-design.md`](../specs/2026-10-16-v166-trade-detail-reorganisation-design.md) (§ 1 Header; `## Amendments from the plan brief` 2 and 7)
**Index:** [`2026-10-16-v166-trade-detail-reorganisation_0-index.md`](2026-10-16-v166-trade-detail-reorganisation_0-index.md) — Global Constraints, `## Where to work` (`$WT`, `$R`, `GATES`), `## Parallelisation` and the task ledger apply to every task here.

Tasks: TD5 (outcome strip), TD6 (identity line and header actions). Both edit `trade-detail.ts` and `trade-detail.spec.ts`, so they run in order: TD5, then TD6. TD5 needs TD2, TD3 and TD4 committed (it imports `exitReasonLabel`, the `trade-figures.ts` helpers and the store's changed `riskPerShare`).

`GATES` below stands for `--include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts` (index § Where to work). Write it out in full in the command.

# Phase 2: header

### Task TD5: Outcome strip: pure `outcomeTiles` per status group, `sb-outcome-strip`, mounted under the header

**Model:** sonnet — one pure builder and one presentational component, groups fixed by the spec table

**Files:**
- Create: `frontend/src/app/workspaces/trades/outcome-tiles.ts`
- Create: `frontend/src/app/workspaces/trades/outcome-tiles.spec.ts`
- Create: `frontend/src/app/workspaces/trades/outcome-strip.ts`
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (imports :1-38, `imports:` array :89-112, template right after `</header>` :171, class body after `whySections` :811-813)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (delete the two stale-flag cases :222-235 from describe A; add a new describe block after describe A)

**Interfaces:**
- Consumes (TD2, `exit-reasons.ts`): `exitReasonLabel(legs: readonly Leg[], history: readonly StatusEvent[], r: number | null): string`.
- Consumes (TD3, `trade-figures.ts`): `type Tone = 'pos' | 'neg' | null`; `outcomeTone(r: number | null): Tone`; `averageExit(legs: readonly Leg[], exitPrice: number | null): number | null`; `type StatusGroup = 'closed' | 'open' | 'pending' | 'unfilled'`; `statusGroup(status: string, exitPrice: number | null): StatusGroup`; `pctFrom(from: number | null, to: number | null): number | null`; `legRsLine(legs: readonly Leg[]): string | null`; `lastHistoryReason(history: readonly StatusEvent[]): string | null`; `daysUntil(iso: string | null, now: Date): number | null`.
- Consumes (TD4, `TradeDetailStore`): `riskPerShare()` now `|entry - (risk_stop ?? stop_loss)|`. Existing store signals used unchanged: `trade()`, `legs()`, `timeline()`, `bankedLeg()`, `bankedStats()`, `expiresOn()`, `timeExitOn()`.
- Consumes (TD1): `TradeRow.risk_stop?: number | null` (only through the store and test fixtures).
- Produces (`outcome-tiles.ts`): `COST_CAPTION = 'before fees & tax'`; `PAPER_FILLS_LINE = 'Paper fills at plan levels; real fills and slippage may differ.'`; `STALE_FLAG = 'delayed'`; `interface StripIndicator {status: string; current: number | null; entry: number | null; stop: number | null; target: number | null}`; `interface OutcomeTile {id: string; label: string; value: string; sub: string | null; tone: Tone; costCaption: boolean; stale: boolean; indicator: StripIndicator | null}`; `interface StripContext {trade: TradeRow; legs: readonly Leg[]; history: readonly StatusEvent[]; riskPerShare: number | null; banked: Leg | null; bankedStats: {pct: number; amount: number | null} | null; expiresOn: string | null; timeExitOn: string | null; now: Date}`; `outcomeTiles(ctx: StripContext): OutcomeTile[]`.
- Produces (`outcome-strip.ts`): component `OutcomeStrip`, selector `sb-outcome-strip`, `tiles = input.required<readonly OutcomeTile[]>()`; each tile renders as `div.tile[data-tile="<id>"]` with `.tile-value`, `.tile-sub`, `.tile-caption`, `.stale-flag`; one `p.strip-foot` footer.
- Produces (`trade-detail.ts`): `TradeDetail.stripTiles: Signal<readonly OutcomeTile[]>`; the strip is the element right after `header.head` (`header.head + sb-outcome-strip`). TD6, TD10 and TD11 keep that position.

**Tile ids per group** (later tasks and the visual pass rely on these exact ids):

| Group | Tile ids, in order |
|---|---|
| closed | `result`, `pnl`, `entry-exit`, `held`, `exit` |
| open | `price`, `unrealised`, `progress`, `held`, then `banked` on PARTIAL with a banked leg |
| pending | `trigger`, `distance`, `expires`, `created` |
| unfilled | `status`, `created`, `trigger`, `fill` |

Decisions this task fixes (from spec § 1 and amendment 2):
- The cost caption sits on the tiles that state P&L in $ or %: `pnl`, `unrealised`, `banked`. Price, Result (an R figure) and the date tiles carry no caption.
- `%` subline: `on position` on CLOSED/ACTIVE (and any other closed-group status), `on open shares` on PARTIAL.
- Tint: `result` and `pnl` use `outcomeTone(r_multiple)`; `unrealised` uses `outcomeTone(r_multiple)` (on an open row that is the unrealised R); `banked` uses `outcomeTone(banked.r)`. Every other tile has `tone: null`.
- P&L amounts use `signed()` from `ui/format.ts` (explicit `+`, U+2212 minus).
- The Price subline measures from the current price to the live `stop_loss` (the working stop on PARTIAL, the level that would actually be hit) and to `target`.
- The history passed to the builder is `store.timeline()` minus its synthetic `CREATED` entry (that entry's reason is the plan source, not a status reason).

- [ ] **Step 1: Write the failing pure-function spec**

Create `frontend/src/app/workspaces/trades/outcome-tiles.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { TradeRow } from '../../api/models';
import { Leg, StatusEvent } from '../../stores/trade-detail.store';
import { date, dateTime } from '../../ui/format';
import {
  COST_CAPTION,
  OutcomeTile,
  PAPER_FILLS_LINE,
  STALE_FLAG,
  StripContext,
  outcomeTiles,
} from './outcome-tiles';

/* SPCX f48c80e2, the trade the spec was written from: closed in two legs,
 * entry 142.01, original stop 139.52 (risk 2.49 per share), 7 shares,
 * 0.5 @ 147.54 (+2.23R) and 0.5 @ 145.56 (+1.43R), blended +1.83R. */
const NOW = new Date('2026-10-16T12:00:00Z');

function row(overrides: Partial<TradeRow> = {}): TradeRow {
  return {
    id: 'f48c80e2',
    origin: 'plan',
    status: 'CLOSED',
    ticker: 'SPCX',
    direction: 'bullish',
    entry: 142.01,
    stop_loss: 139.52,
    risk_stop: 139.52,
    target: 147.43,
    target2: 150,
    shares: 7,
    current_price: null,
    current_price_stale: false,
    exit_price: 146.55,
    realized_pnl_amount: 31.78,
    pnl_pct: 3.2,
    r_multiple: 1.83,
    held_hours: 123,
    created_at: '2026-10-01T13:30:00Z',
    trigger_price: 142.2,
    distance_to_trigger_r: null,
    bars_to_expiry: null,
    ...overrides,
  } as unknown as TradeRow;
}

const SPCX_LEGS: Leg[] = [
  { fraction: 0.5, exitPrice: 147.54, r: 2.23, reason: 'tp1' },
  { fraction: 0.5, exitPrice: 145.56, r: 1.43, reason: 'tp1_runner_be' },
];

function ctx(overrides: Partial<StripContext> = {}): StripContext {
  return {
    trade: row(),
    legs: SPCX_LEGS,
    history: [],
    riskPerShare: 2.49,
    banked: null,
    bankedStats: null,
    expiresOn: null,
    timeExitOn: null,
    now: NOW,
    ...overrides,
  };
}

function byId(tiles: OutcomeTile[], id: string): OutcomeTile {
  const found = tiles.find((tile) => tile.id === id);
  if (!found) throw new Error(`no tile "${id}" in ${tiles.map((tile) => tile.id).join(',')}`);
  return found;
}

const ids = (tiles: OutcomeTile[]) => tiles.map((tile) => tile.id);

const CLOSED_IDS = ['result', 'pnl', 'entry-exit', 'held', 'exit'];
const OPEN_IDS = ['price', 'unrealised', 'progress', 'held'];
const PENDING_IDS = ['trigger', 'distance', 'expires', 'created'];
const UNFILLED_IDS = ['status', 'created', 'trigger', 'fill'];

describe('outcome strip copy', () => {
  it('pins the verbatim captions', () => {
    expect(COST_CAPTION).toBe('before fees & tax');
    expect(PAPER_FILLS_LINE).toBe('Paper fills at plan levels; real fills and slippage may differ.');
    expect(STALE_FLAG).toBe('delayed');
  });
});

describe('outcomeTiles — closed group (SPCX)', () => {
  const tiles = outcomeTiles(ctx());

  it('shows Result, P&L, Entry → exit, Held and Exit', () => {
    expect(ids(tiles)).toEqual(CLOSED_IDS);
  });

  it('shows the blended R as sent, with 1R in dollars and the leg Rs', () => {
    const result = byId(tiles, 'result');
    expect(result.value).toBe('+1.83R');
    expect(result.sub).toBe('1R = $17.43 · +2.23R / +1.43R');
    expect(result.tone).toBe('pos');
    expect(result.costCaption).toBe(false);
  });

  it('states the P&L basis and the cost caveat', () => {
    const pnl = byId(tiles, 'pnl');
    expect(pnl.value).toBe('+31.78');
    expect(pnl.sub).toBe('+3.20% on position');
    expect(pnl.costCaption).toBe(true);
    expect(pnl.tone).toBe('pos');
  });

  it('shows entry to the fraction-weighted average exit', () => {
    expect(byId(tiles, 'entry-exit').value).toBe('142.01 → 146.55');
  });

  it('prints the holding period in days', () => {
    expect(byId(tiles, 'held').value).toBe('5d 3h 0m');
  });

  it('labels a two-leg exit with both reasons', () => {
    expect(byId(tiles, 'exit').value).toBe('TP1 + Runner at breakeven');
  });

  it('carries the cost caption on P&L only', () => {
    expect(tiles.filter((tile) => tile.costCaption).map((tile) => tile.id)).toEqual(['pnl']);
  });

  it('flags nothing as stale on a closed trade', () => {
    expect(tiles.some((tile) => tile.stale)).toBe(false);
  });
});

describe('outcomeTiles — closed edge cases', () => {
  it('shows "—" for a missing R and never computes a stand-in', () => {
    const tiles = outcomeTiles(ctx({ trade: row({ r_multiple: null }) }));
    expect(byId(tiles, 'result').value).toBe('—');
    expect(byId(tiles, 'result').tone).toBeNull();
    expect(byId(tiles, 'pnl').tone).toBeNull();
  });

  it('shows no leg Rs and no "+" for a single leg', () => {
    const legs: Leg[] = [{ fraction: 1, exitPrice: 146.55, r: 1.83, reason: 'tp1' }];
    const tiles = outcomeTiles(ctx({ legs }));
    expect(byId(tiles, 'result').sub).toBe('1R = $17.43');
    expect(byId(tiles, 'exit').value).toBe('TP1');
  });

  it('drops the 1R subline when the risk per share is unknown', () => {
    const legs: Leg[] = [{ fraction: 1, exitPrice: 146.55, r: 1.83, reason: 'tp1' }];
    expect(byId(outcomeTiles(ctx({ legs, riskPerShare: null })), 'result').sub).toBeNull();
  });

  it('leaves a result inside ±0.1R untinted', () => {
    const tiles = outcomeTiles(ctx({ trade: row({ r_multiple: 0.05, realized_pnl_amount: 0.87 }) }));
    expect(byId(tiles, 'result').tone).toBeNull();
    expect(byId(tiles, 'pnl').tone).toBeNull();
    expect(byId(tiles, 'pnl').value).toBe('+0.87');
  });

  it('tints a loss negative and signs it with a minus', () => {
    const tiles = outcomeTiles(ctx({
      trade: row({ r_multiple: -1, realized_pnl_amount: -17.43, pnl_pct: -1.75 }),
      legs: [{ fraction: 1, exitPrice: 139.52, r: -1, reason: 'stop' }],
    }));
    expect(byId(tiles, 'result').tone).toBe('neg');
    expect(byId(tiles, 'pnl').value).toBe('−17.43');
    expect(byId(tiles, 'pnl').sub).toBe('-1.75% on position');
    expect(byId(tiles, 'exit').value).toBe('Stop');
  });

  it('marks a stop that gapped past -1.05R', () => {
    const tiles = outcomeTiles(ctx({
      trade: row({ r_multiple: -1.4 }),
      legs: [{ fraction: 1, exitPrice: 138.5, r: -1.4, reason: 'stop' }],
    }));
    expect(byId(tiles, 'exit').value).toBe('Stop (gapped)');
  });

  it('falls back to exit_price and the status history with no legs', () => {
    const history: StatusEvent[] = [{ status: 'CLOSED', reason: 'stall_exit', at: '2026-10-06T15:00:00Z' }];
    const tiles = outcomeTiles(ctx({ legs: [], history }));
    expect(byId(tiles, 'entry-exit').value).toBe('142.01 → 146.55');
    expect(byId(tiles, 'exit').value).toBe('Stall exit');
  });

  it('skips a leg with no exit price in the average', () => {
    const legs: Leg[] = [
      { fraction: 0.5, exitPrice: 147.54, r: 2.23, reason: 'tp1' },
      { fraction: 0.5, exitPrice: null, r: null, reason: null },
    ];
    expect(byId(outcomeTiles(ctx({ legs })), 'entry-exit').value).toBe('142.01 → 147.54');
  });
});

describe('outcomeTiles — status decides the group first', () => {
  it('keeps CLOSED in the closed group even with no exit price', () => {
    const tiles = outcomeTiles(ctx({ trade: row({ exit_price: null }), legs: [] }));
    expect(ids(tiles)).toEqual(CLOSED_IDS);
    expect(byId(tiles, 'entry-exit').value).toBe('142.01 → —');
  });

  it('puts a CANCELLED row with an exit price in the closed group', () => {
    expect(ids(outcomeTiles(ctx({ trade: row({ status: 'CANCELLED' }) })))).toEqual(CLOSED_IDS);
  });

  it('puts a CANCELLED row without an exit price in the unfilled group', () => {
    const trade = row({ status: 'CANCELLED', exit_price: null });
    expect(ids(outcomeTiles(ctx({ trade, legs: [] })))).toEqual(UNFILLED_IDS);
  });

  it('keeps an ACTIVE row in the open group whatever exit_price says', () => {
    const trade = row({ status: 'ACTIVE', exit_price: 146, current_price: 145 });
    expect(ids(outcomeTiles(ctx({ trade, legs: [] })))).toEqual(OPEN_IDS);
  });
});

describe('outcomeTiles — open group', () => {
  const active = row({
    status: 'ACTIVE',
    exit_price: null,
    current_price: 145,
    realized_pnl_amount: 20.93,
    pnl_pct: 2.11,
    r_multiple: 1.2,
    held_hours: 30,
  });

  it('shows Price, Unrealised, Progress and Held on ACTIVE', () => {
    expect(ids(outcomeTiles(ctx({ trade: active, legs: [] })))).toEqual(OPEN_IDS);
  });

  it('measures the distance to the stop and to T1 from the current price', () => {
    const price = byId(outcomeTiles(ctx({ trade: active, legs: [] })), 'price');
    expect(price.value).toBe('145.00');
    expect(price.sub).toBe('to stop -3.78% · to T1 +1.68%');
    expect(price.costCaption).toBe(false);
  });

  it('labels the unrealised % "on position" on ACTIVE', () => {
    const unrealised = byId(outcomeTiles(ctx({ trade: active, legs: [] })), 'unrealised');
    expect(unrealised.value).toBe('+20.93');
    expect(unrealised.sub).toBe('+2.11% on position');
    expect(unrealised.costCaption).toBe(true);
    expect(unrealised.tone).toBe('pos');
  });

  it('feeds the progress indicator the live levels', () => {
    expect(byId(outcomeTiles(ctx({ trade: active, legs: [] })), 'progress').indicator).toEqual({
      status: 'ACTIVE',
      current: 145,
      entry: 142.01,
      stop: 139.52,
      target: 147.43,
    });
  });

  it('flags a stale price on both the Price and the Unrealised tile', () => {
    const tiles = outcomeTiles(ctx({ trade: row({ ...active, current_price_stale: true }), legs: [] }));
    expect(tiles.filter((tile) => tile.stale).map((tile) => tile.id)).toEqual(['price', 'unrealised']);
  });

  it('adds the days to the time exit under Held', () => {
    const tiles = outcomeTiles(ctx({ trade: active, legs: [], timeExitOn: '2026-10-20' }));
    expect(byId(tiles, 'held').sub).toBe('time exit in 4d');
  });

  it('shows no Held subline without a time exit', () => {
    expect(byId(outcomeTiles(ctx({ trade: active, legs: [] })), 'held').sub).toBeNull();
  });

  it('labels the % "on open shares" on PARTIAL and keeps Banked separate', () => {
    const tiles = outcomeTiles(ctx({
      trade: row({ ...active, status: 'PARTIAL', stop_loss: 145.62 }),
      banked: { fraction: 0.5, exitPrice: 147.54, r: 2.23, reason: 'tp1' },
      bankedStats: { pct: 3.89, amount: 13.62 },
    }));
    expect(ids(tiles)).toEqual([...OPEN_IDS, 'banked']);
    expect(byId(tiles, 'unrealised').sub).toBe('+2.11% on open shares');
    expect(byId(tiles, 'unrealised').value).toBe('+20.93');
    const banked = byId(tiles, 'banked');
    expect(banked.value).toBe('50% @ 147.54');
    expect(banked.sub).toBe('+2.23R · +3.89% · +13.62');
    expect(banked.costCaption).toBe(true);
    expect(banked.tone).toBe('pos');
  });

  it('measures the PARTIAL distance to the working stop', () => {
    const tiles = outcomeTiles(ctx({ trade: row({ ...active, status: 'PARTIAL', stop_loss: 145.62 }) }));
    expect(byId(tiles, 'price').sub).toBe('to stop +0.43% · to T1 +1.68%');
  });

  it('shows no Banked tile on PARTIAL before anything has banked', () => {
    const tiles = outcomeTiles(ctx({ trade: row({ ...active, status: 'PARTIAL' }) }));
    expect(ids(tiles)).toEqual(OPEN_IDS);
  });

  it('shows no Banked tile outside PARTIAL', () => {
    const banked: Leg = { fraction: 0.5, exitPrice: 147.54, r: 2.23, reason: 'tp1' };
    expect(ids(outcomeTiles(ctx({ trade: active, banked })))).toEqual(OPEN_IDS);
  });
});

describe('outcomeTiles — pending group', () => {
  const pending = row({
    status: 'PENDING',
    exit_price: null,
    current_price: 141,
    realized_pnl_amount: null,
    pnl_pct: null,
    r_multiple: null,
    distance_to_trigger_r: 0.48,
    bars_to_expiry: 3,
  });

  it('shows Trigger, Distance, Expires and Created', () => {
    expect(ids(outcomeTiles(ctx({ trade: pending, legs: [] })))).toEqual(PENDING_IDS);
  });

  it('shows the trigger with the current price and the % to it', () => {
    const trigger = byId(outcomeTiles(ctx({ trade: pending, legs: [] })), 'trigger');
    expect(trigger.value).toBe('142.20');
    expect(trigger.sub).toBe('now 141.00 · +0.85% to trigger');
  });

  it('omits the trigger subline without a current price', () => {
    const trade = row({ ...pending, current_price: null });
    expect(byId(outcomeTiles(ctx({ trade, legs: [] })), 'trigger').sub).toBeNull();
  });

  it('shows the distance in R and the expiry date with the bars left', () => {
    const tiles = outcomeTiles(ctx({ trade: pending, legs: [], expiresOn: '2026-10-21' }));
    expect(byId(tiles, 'distance').value).toBe('0.48R');
    expect(byId(tiles, 'expires').value).toBe(date('2026-10-21'));
    expect(byId(tiles, 'expires').sub).toBe('3 bars left');
    expect(byId(tiles, 'created').value).toBe(dateTime('2026-10-01T13:30:00Z'));
  });

  it('shows "—" for a missing distance and no bars subline', () => {
    const trade = row({ ...pending, distance_to_trigger_r: null, bars_to_expiry: null });
    const tiles = outcomeTiles(ctx({ trade, legs: [] }));
    expect(byId(tiles, 'distance').value).toBe('—');
    expect(byId(tiles, 'expires').sub).toBeNull();
  });

  it('carries no cost caption on a plan that has not filled', () => {
    expect(outcomeTiles(ctx({ trade: pending, legs: [] })).some((tile) => tile.costCaption)).toBe(false);
  });
});

describe('outcomeTiles — unfilled group', () => {
  it('says a cancelled plan never filled, with the last recorded reason', () => {
    const history: StatusEvent[] = [
      { status: 'PENDING', reason: null, at: '2026-10-01T13:30:00Z' },
      { status: 'CANCELLED', reason: 'invalidated before trigger', at: '2026-10-02T15:00:00Z' },
    ];
    const tiles = outcomeTiles(ctx({ trade: row({ status: 'CANCELLED', exit_price: null }), legs: [], history }));
    expect(ids(tiles)).toEqual(UNFILLED_IDS);
    expect(byId(tiles, 'status').value).toBe('Cancelled');
    expect(byId(tiles, 'status').sub).toBe('invalidated before trigger');
    expect(byId(tiles, 'trigger').value).toBe('142.20');
    expect(byId(tiles, 'fill').value).toBe('Never filled');
  });

  it('shows an expired plan with no subline when no reason was recorded', () => {
    const tiles = outcomeTiles(ctx({ trade: row({ status: 'EXPIRED', exit_price: null }), legs: [] }));
    expect(byId(tiles, 'status').value).toBe('Expired');
    expect(byId(tiles, 'status').sub).toBeNull();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/outcome-tiles.spec.ts`
Expected: FAIL, the build cannot resolve `./outcome-tiles`.

- [ ] **Step 3: Write `outcome-tiles.ts`**

Create `frontend/src/app/workspaces/trades/outcome-tiles.ts`:

```ts
import { TradeRow } from '../../api/models';
import { Leg, StatusEvent } from '../../stores/trade-detail.store';
import { ABSENT, date, dateTime, held, num, pct, rMultiple, share, signed } from '../../ui/format';
import { exitReasonLabel } from './exit-reasons';
import {
  StatusGroup,
  Tone,
  averageExit,
  daysUntil,
  lastHistoryReason,
  legRsLine,
  outcomeTone,
  pctFrom,
  statusGroup,
} from './trade-figures';

/* The outcome strip under the trade page's identity line (v166 spec § 1).
 * Status decides the group first; `exit_price` is consulted only for a
 * terminal status other than CLOSED (`statusGroup`). Every builder here is
 * pure, so the per-group copy is pinned without mounting the page. */

/** On every tile that states P&L in $ or %. Paper fills carry no costs. */
export const COST_CAPTION = 'before fees & tax';

/** The strip's one muted footer line. */
export const PAPER_FILLS_LINE = 'Paper fills at plan levels; real fills and slippage may differ.';

/** The word the Live tab's Now panel used since the MRNA incident (2026-09-18). */
export const STALE_FLAG = 'delayed';

/** Inputs for the existing `sb-status-indicator` on the Progress tile. */
export interface StripIndicator {
  status: string;
  current: number | null;
  entry: number | null;
  stop: number | null;
  target: number | null;
}

export interface OutcomeTile {
  id: string;
  label: string;
  value: string;
  sub: string | null;
  tone: Tone;
  costCaption: boolean;
  stale: boolean;
  indicator: StripIndicator | null;
}

export interface StripContext {
  trade: TradeRow;
  legs: readonly Leg[];
  /** `status_history` only -- never the timeline's synthetic CREATED entry. */
  history: readonly StatusEvent[];
  /** |entry - (risk_stop ?? stop_loss)| -- the original risk (amendment 2). */
  riskPerShare: number | null;
  banked: Leg | null;
  bankedStats: { pct: number; amount: number | null } | null;
  expiresOn: string | null;
  timeExitOn: string | null;
  now: Date;
}

type Builder = (ctx: StripContext) => OutcomeTile[];

function tile(id: string, label: string, value: string, extra: Partial<OutcomeTile> = {}): OutcomeTile {
  return {
    id,
    label,
    value,
    sub: null,
    tone: null,
    costCaption: false,
    stale: false,
    indicator: null,
    ...extra,
  };
}

/** Non-empty parts joined with a middle dot; null when nothing is left. */
function joinParts(parts: readonly (string | null)[]): string | null {
  const kept = parts.filter((part): part is string => part !== null && part !== '');
  return kept.length ? kept.join(' · ') : null;
}

function oneR(ctx: StripContext): string | null {
  const shares = ctx.trade.shares;
  if (shares === null || shares === undefined || ctx.riskPerShare === null) return null;
  return `1R = $${num(shares * ctx.riskPerShare)}`;
}

/** Amendment 2: on PARTIAL every figure on the row is about the open runner. */
function pnlSub(trade: TradeRow): string | null {
  if (trade.pnl_pct === null || trade.pnl_pct === undefined) return null;
  const basis = trade.status === 'PARTIAL' ? 'on open shares' : 'on position';
  return `${pct(trade.pnl_pct)} ${basis}`;
}

function closedTiles(ctx: StripContext): OutcomeTile[] {
  const trade = ctx.trade;
  const r = trade.r_multiple ?? null;
  const exit = averageExit(ctx.legs, trade.exit_price ?? null);
  return [
    tile('result', 'Result', rMultiple(r), {
      sub: joinParts([oneR(ctx), legRsLine(ctx.legs)]),
      tone: outcomeTone(r),
    }),
    tile('pnl', 'P&L', signed(trade.realized_pnl_amount), {
      sub: pnlSub(trade),
      tone: outcomeTone(r),
      costCaption: true,
    }),
    tile('entry-exit', 'Entry → exit', `${num(trade.entry)} → ${num(exit)}`),
    tile('held', 'Held', held(trade.held_hours)),
    tile('exit', 'Exit', exitReasonLabel(ctx.legs, ctx.history, r)),
  ];
}

function distanceSub(trade: TradeRow): string | null {
  const current = trade.current_price ?? null;
  const toStop = pctFrom(current, trade.stop_loss ?? null);
  const toTarget = pctFrom(current, trade.target ?? null);
  return joinParts([
    toStop === null ? null : `to stop ${pct(toStop)}`,
    toTarget === null ? null : `to T1 ${pct(toTarget)}`,
  ]);
}

function timeExitSub(ctx: StripContext): string | null {
  const days = daysUntil(ctx.timeExitOn, ctx.now);
  return days === null ? null : `time exit in ${days}d`;
}

function bankedMoney(stats: StripContext['bankedStats']): string | null {
  if (!stats) return null;
  return joinParts([pct(stats.pct), stats.amount === null ? null : signed(stats.amount)]);
}

function bankedTile(ctx: StripContext): OutcomeTile | null {
  const leg = ctx.banked;
  if (ctx.trade.status !== 'PARTIAL' || leg === null) return null;
  const fraction = leg.fraction === null ? '' : `${share(leg.fraction * 100)} `;
  return tile('banked', 'Banked', `${fraction}@ ${num(leg.exitPrice)}`, {
    sub: joinParts([leg.r === null ? null : rMultiple(leg.r), bankedMoney(ctx.bankedStats)]),
    tone: outcomeTone(leg.r),
    costCaption: true,
  });
}

function openTiles(ctx: StripContext): OutcomeTile[] {
  const trade = ctx.trade;
  const stale = trade.current_price_stale === true;
  const tiles = [
    tile('price', 'Price', num(trade.current_price), { sub: distanceSub(trade), stale }),
    tile('unrealised', 'Unrealised', signed(trade.realized_pnl_amount), {
      sub: pnlSub(trade),
      tone: outcomeTone(trade.r_multiple ?? null),
      costCaption: true,
      stale,
    }),
    tile('progress', 'Progress', '', {
      indicator: {
        status: trade.status,
        current: trade.current_price ?? null,
        entry: trade.entry ?? null,
        stop: trade.stop_loss ?? null,
        target: trade.target ?? null,
      },
    }),
    tile('held', 'Held', held(trade.held_hours), { sub: timeExitSub(ctx) }),
  ];
  const banked = bankedTile(ctx);
  return banked ? [...tiles, banked] : tiles;
}

function triggerSub(trade: TradeRow): string | null {
  const current = trade.current_price ?? null;
  if (current === null) return null;
  const gap = pctFrom(current, trade.trigger_price ?? null);
  return joinParts([`now ${num(current)}`, gap === null ? null : `${pct(gap)} to trigger`]);
}

function pendingTiles(ctx: StripContext): OutcomeTile[] {
  const trade = ctx.trade;
  const distance = trade.distance_to_trigger_r ?? null;
  const bars = trade.bars_to_expiry ?? null;
  return [
    tile('trigger', 'Trigger', num(trade.trigger_price), { sub: triggerSub(trade) }),
    tile('distance', 'Distance', distance === null ? ABSENT : `${num(distance)}R`),
    tile('expires', 'Expires', date(ctx.expiresOn), { sub: bars === null ? null : `${bars} bars left` }),
    tile('created', 'Created', dateTime(trade.created_at)),
  ];
}

function statusWord(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
}

function unfilledTiles(ctx: StripContext): OutcomeTile[] {
  const trade = ctx.trade;
  return [
    tile('status', 'Status', statusWord(trade.status), { sub: lastHistoryReason(ctx.history) }),
    tile('created', 'Created', dateTime(trade.created_at)),
    tile('trigger', 'Trigger', num(trade.trigger_price)),
    tile('fill', 'Fill', 'Never filled'),
  ];
}

const BUILDERS: Record<StatusGroup, Builder> = {
  closed: closedTiles,
  open: openTiles,
  pending: pendingTiles,
  unfilled: unfilledTiles,
};

export function outcomeTiles(ctx: StripContext): OutcomeTile[] {
  return BUILDERS[statusGroup(ctx.trade.status, ctx.trade.exit_price ?? null)](ctx);
}
```

The `?? null` guards exist because the page's spec fixtures (and rows built before v166) omit `trigger_price`, `distance_to_trigger_r`, `bars_to_expiry` and `risk_stop` entirely; `undefined` must read as absent, never as "undefined bars left".

- [ ] **Step 4: Run the pure spec to verify it passes**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/outcome-tiles.spec.ts`
Expected: PASS. If `to stop -3.78%` reads differently, check that `pctFrom` (TD3) is `(to - from) / from * 100` and `pct` prints 2 dp; do not change the expected strings.

- [ ] **Step 5: Write the `sb-outcome-strip` component**

Create `frontend/src/app/workspaces/trades/outcome-strip.ts`:

```ts
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { StatusIndicator } from '../../ui/status-indicator';
import { COST_CAPTION, OutcomeTile, PAPER_FILLS_LINE, STALE_FLAG } from './outcome-tiles';

/**
 * The trade page's outcome strip (v166 spec § 1): one row of KPI tiles under
 * the identity line, on every tab.
 *
 * Flex, not grid auto-fit: `flex: 1 1 120px` makes a short last row stretch
 * across the width instead of leaving an empty slot -- 5 across on a desktop,
 * 3 + 2 on a tablet, 2 + 2 + 1 on a phone with the last tile full width.
 * The sign and the words carry the meaning; the tint (global .pos/.neg) only
 * repeats it, and only outside the neutral band (`outcomeTone`).
 */
@Component({
  selector: 'sb-outcome-strip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [StatusIndicator],
  template: `
    <div class="strip">
      @for (tile of tiles(); track tile.id) {
        <div class="tile" [attr.data-tile]="tile.id">
          <span class="sb-label">{{ tile.label }}</span>
          @if (tile.indicator; as indicator) {
            <sb-status-indicator
              [status]="indicator.status"
              [current]="indicator.current"
              [entry]="indicator.entry"
              [stop]="indicator.stop"
              [target]="indicator.target"
            />
          } @else {
            <span
              class="tile-value num"
              [class.pos]="tile.tone === 'pos'"
              [class.neg]="tile.tone === 'neg'"
            >{{ tile.value }}</span>
          }
          @if (tile.stale) {
            <span
              class="stale-flag"
              title="This position's price could not be freshly fetched -- the number shown may be delayed."
            >{{ staleFlag }}</span>
          }
          @if (tile.sub) {
            <span class="tile-sub num">{{ tile.sub }}</span>
          }
          @if (tile.costCaption) {
            <span class="tile-caption muted">{{ costCaption }}</span>
          }
        </div>
      }
    </div>
    <p class="strip-foot muted">{{ paperFills }}</p>
  `,
  styles: `
    :host { display: grid; gap: var(--space-8); min-width: 0; }
    .strip {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-10);
    }
    .tile {
      flex: 1 1 120px;
      min-width: 0;
      display: grid;
      align-content: start;
      gap: var(--space-4);
      padding: var(--space-10) var(--space-14);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
    }
    .tile-value {
      font-size: var(--text-title);
      font-weight: 600;
      overflow-wrap: anywhere;
    }
    .tile-sub {
      font-size: var(--text-chip);
      color: var(--text-secondary);
      overflow-wrap: anywhere;
    }
    .tile-caption {
      font-size: var(--text-chip);
    }
    /* --warn is the designated stale-data token (tokens.css legend). */
    .stale-flag {
      font-size: var(--text-chip);
      color: var(--warn);
    }
    .strip-foot {
      margin: 0;
      font-size: var(--text-chip);
    }
  `,
})
export class OutcomeStrip {
  readonly tiles = input.required<readonly OutcomeTile[]>();

  protected readonly costCaption = COST_CAPTION;
  protected readonly paperFills = PAPER_FILLS_LINE;
  protected readonly staleFlag = STALE_FLAG;
}
```

The file defines no `.pos`, `.neg`, `.muted`, `.head`, `.note` or `.chips` rule (it uses the global classes), has no hex literal, no margin on a panel-level selector, and only tokens from the allowed spacing scale.

- [ ] **Step 6: Write the failing page cases**

In `frontend/src/app/workspaces/trades/trade-detail.spec.ts`, delete these two cases from describe A (`TradeDetail — the fields that rendered nowhere`), together with the MRNA comment above the first; the comment moves into the new block below:

```ts
  it('flags a stale current price on the Now panel', () => {
    const text = render('live', DETAIL, 'ACTIVE', { current_price_stale: true });
    expect(text).toContain('delayed');
  });

  it('does not flag a fresh current price on the Now panel', () => {
    const text = render('live', DETAIL, 'ACTIVE', { current_price_stale: false });
    expect(text).not.toContain('delayed');
  });
```

Then add this describe block directly after describe A's closing `});`:

```ts
describe('TradeDetail — outcome strip (v166)', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        TradeDetailStore,
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  /** Mount (default tab unless one is named) and settle the detail request. */
  function mount(status: string, overrides: object = {}, detail: object = DETAIL, tab = '') {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', tab);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(detail, status, overrides));
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  function tile(el: HTMLElement, id: string): HTMLElement {
    const found = el.querySelector<HTMLElement>(`sb-outcome-strip .tile[data-tile="${id}"]`);
    if (!found) throw new Error(`no strip tile "${id}"`);
    return found;
  }

  const tileIds = (el: HTMLElement) =>
    [...el.querySelectorAll('sb-outcome-strip .tile')].map((node) => node.getAttribute('data-tile'));

  /* SPCX f48c80e2: closed in two legs, +1.83R blended. */
  const SPCX_CLOSED = {
    entry: 142.01,
    stop_loss: 139.52,
    risk_stop: 139.52,
    shares: 7,
    current_price: null,
    exit_price: 146.55,
    realized_pnl_amount: 31.78,
    pnl_pct: 3.2,
    r_multiple: 1.83,
    closed_at: '2026-10-06T15:00:00Z',
  };
  const SPCX_DETAIL = {
    ...DETAIL,
    legs_realized: [
      { fraction: 0.5, exit_price: 147.54, r: 2.23, reason: 'tp1' },
      { fraction: 0.5, exit_price: 145.56, r: 1.43, reason: 'tp1_runner_be' },
    ],
  };

  it('sits right under the header on every tab', () => {
    for (const tab of ['', 'notes']) {
      const el = mount('ACTIVE', {}, DETAIL, tab);
      expect(el.querySelector('header.head + sb-outcome-strip')).not.toBeNull();
    }
  });

  // 2026-09-18 -- the MRNA incident. A fast_info fallback echoed yesterday's
  // close during premarket; the price must say it is not necessarily a live
  // tick instead of rendering with full confidence. v166: both tiles that
  // mark to that price carry the flag.
  it('flags a stale current price on the Price and the Unrealised tile', () => {
    const el = mount('ACTIVE', { current_price_stale: true });
    expect(tile(el, 'price').textContent).toContain('delayed');
    expect(tile(el, 'unrealised').textContent).toContain('delayed');
    expect(tile(el, 'held').textContent).not.toContain('delayed');
  });

  it('does not flag a fresh current price', () => {
    const el = mount('ACTIVE', { current_price_stale: false });
    expect(el.querySelector('sb-outcome-strip .stale-flag')).toBeNull();
  });

  it('shows the outcome of a closed two-leg trade', () => {
    const el = mount('CLOSED', SPCX_CLOSED, SPCX_DETAIL);
    expect(tileIds(el)).toEqual(['result', 'pnl', 'entry-exit', 'held', 'exit']);
    expect(tile(el, 'result').textContent).toContain('+1.83R');
    expect(tile(el, 'result').textContent).toContain('1R = $17.43');
    expect(tile(el, 'result').textContent).toContain('+2.23R / +1.43R');
    expect(tile(el, 'entry-exit').textContent).toContain('142.01 → 146.55');
    expect(tile(el, 'exit').textContent).toContain('TP1 + Runner at breakeven');
  });

  it('states the P&L basis and the cost caveat', () => {
    const el = mount('CLOSED', SPCX_CLOSED, SPCX_DETAIL);
    const pnl = tile(el, 'pnl').textContent ?? '';
    expect(pnl).toContain('+31.78');
    expect(pnl).toContain('+3.20% on position');
    expect(pnl).toContain('before fees & tax');
    expect(el.querySelector('sb-outcome-strip .strip-foot')?.textContent).toContain(
      'Paper fills at plan levels; real fills and slippage may differ.',
    );
  });

  it('tints a clear result', () => {
    const el = mount('CLOSED', SPCX_CLOSED, SPCX_DETAIL);
    expect(tile(el, 'result').querySelector('.tile-value')?.classList.contains('pos')).toBe(true);
  });

  it('leaves a result inside ±0.1R untinted', () => {
    const el = mount('CLOSED', { ...SPCX_CLOSED, r_multiple: 0.05, realized_pnl_amount: 0.87 }, SPCX_DETAIL);
    const value = tile(el, 'result').querySelector('.tile-value');
    expect(value?.classList.contains('pos')).toBe(false);
    expect(value?.classList.contains('neg')).toBe(false);
  });

  it('decides the group by status before exit_price', () => {
    expect(tileIds(mount('CANCELLED', { exit_price: 101 }))).toEqual([
      'result', 'pnl', 'entry-exit', 'held', 'exit',
    ]);
  });

  it('says a cancelled plan never filled', () => {
    const el = mount('CANCELLED', { exit_price: null, current_price: null }, {
      ...DETAIL,
      legs: [],
      status_history: [
        { status: 'CANCELLED', reason: 'invalidated before trigger', at: '2026-08-02T14:05:00Z' },
      ],
    });
    expect(tileIds(el)).toEqual(['status', 'created', 'trigger', 'fill']);
    expect(tile(el, 'status').textContent).toContain('invalidated before trigger');
    expect(tile(el, 'fill').textContent).toContain('Never filled');
  });

  it('shows the trigger tiles on a pending plan', () => {
    const el = mount('PENDING', { trigger_price: 101.5, distance_to_trigger_r: 0.3, bars_to_expiry: 2 });
    expect(tileIds(el)).toEqual(['trigger', 'distance', 'expires', 'created']);
    expect(tile(el, 'trigger').textContent).toContain('101.50');
    expect(tile(el, 'expires').textContent).toContain('2 bars left');
  });

  it('labels the runner\'s % "on open shares" and banks TP1 separately on PARTIAL', () => {
    const el = mount('PARTIAL', { risk_stop: 95, stop_loss: 101.33 }, {
      ...DETAIL,
      legs_realized: [{ fraction: 0.5, exit_price: 110, r: 2.0, reason: 'tp1' }],
      working_stop: 101.33,
    });
    expect(tile(el, 'unrealised').textContent).toContain('+5.00% on open shares');
    const banked = tile(el, 'banked').textContent ?? '';
    expect(banked).toContain('50% @ 110.00');
    expect(banked).toContain('+2.00R');
    expect(banked).toContain('+10.00%');
    expect(banked).toContain('+50.00');
  });
});
```

The fixture numbers: `tradeResponse()` defaults are entry 100, shares 10, `pnl_pct` 5, so the banked leg is (110 - 100) / 100 = +10.00 % and 10 x 0.5 x 10 = +50.00 (`store.bankedStats()`).

- [ ] **Step 7: Run the page spec to verify the new cases fail**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts`
Expected: FAIL in `TradeDetail — outcome strip (v166)` (`no strip tile ...` / `expected null not to be null`); every other case still passes.

- [ ] **Step 8: Mount the strip in `trade-detail.ts`**

Add the imports after the `./trade-actions` import block:

```ts
import { OutcomeStrip } from './outcome-strip';
import { OutcomeTile, outcomeTiles } from './outcome-tiles';
```

Add `OutcomeStrip,` to the `@Component` `imports:` array (after `PlanChart,`).

In the template, directly after `</header>` and before `<sb-tab-bar ...>`, insert:

```html
    <!-- v166 -- the outcome strip, on every tab: status decides which tiles
         (outcome-tiles.ts). Hidden until the trade has loaded; the header's
         own Loading/error line covers that moment. -->
    @if (stripTiles().length) {
      <sb-outcome-strip [tiles]="stripTiles()" />
    }
```

In the class, after the `whySections` computed, add:

```ts
  /** The strip's tiles. `timeline()` minus its synthetic CREATED entry is the
   *  record's own status_history -- CREATED's reason is the plan source, which
   *  would read as a cancellation reason on an unfilled plan. */
  protected readonly stripTiles = computed<readonly OutcomeTile[]>(() => {
    const trade = this.store.trade();
    if (!trade) return [];
    return outcomeTiles({
      trade,
      legs: this.store.legs(),
      history: this.store.timeline().filter((event) => event.status !== 'CREATED'),
      riskPerShare: this.store.riskPerShare(),
      banked: this.store.bankedLeg(),
      bankedStats: this.store.bankedStats(),
      expiresOn: this.store.expiresOn(),
      timeExitOn: this.store.timeExitOn(),
      now: new Date(),
    });
  });
```

The Live tab's own Now panel (with its stale flag) stays until TD10 replaces the tab.

- [ ] **Step 9: Run the page spec, the pure spec and the UI gates**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/trades/outcome-tiles.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts`
Expected: PASS, 0 failed. A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once.

- [ ] **Step 10: Commit**

```bash
git -C $WT add frontend/src/app/workspaces/trades/outcome-tiles.ts frontend/src/app/workspaces/trades/outcome-tiles.spec.ts frontend/src/app/workspaces/trades/outcome-strip.ts frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts
git -C $WT commit -m "feat(v166): TD5 outcome strip -- status-driven tiles under the trade header

Closed: Result (R as sent, 1R in dollars, leg Rs), P&L with its basis and
the before-fees caption, entry to average exit, held, exit-reason label.
Open: price with distance to stop and T1, unrealised (on open shares on
PARTIAL), progress, held, Banked on PARTIAL. Pending and unfilled groups.
Stale flag on both price tiles; tint only outside +/-0.1R.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task TD6: Identity line: Long/Short text, badge and earnings chips, origin tag, id, action buttons in the header; Actions card removed

**Model:** sonnet — header markup in one component, rules fixed by the spec

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (imports :19-38, `imports:` array :89-112, header template :114-171, Live tab Actions panel :403-421, styles `.tags` :638-643 and `.commands` comment :705-706, class body after `cohortTooltip`)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (delete the `offers Close on a live position` case :287-291 from describe A; add a new describe block after the TD5 outcome-strip block)

**Interfaces:**
- Consumes (TD3, `trade-figures.ts`): `sideLabel(direction: string | null): 'Long' | 'Short' | null`; `statusGroup(status: string, exitPrice: number | null): StatusGroup`.
- Consumes (TD4, `TradeDetailStore`): `earningsDays(): number | null` (the `earnings` gate row's numeric `value`, else null).
- Consumes (TD5): the strip stays the element right after `header.head`; this task changes only what is inside the header.
- Consumes (existing): `availableActions(status)`, `ACTION_LABELS` (`trade-actions.ts`), `ask(kind)`, `actionsFor`, `actionLabels` (`TradeDetail`), `QualityChip`, `Chip` (`ui/chip.ts`).
- Produces (header DOM contract, ledger TD6): `header.head > .identity` holds `.trade-title` (`.ticker`, `.side`, `sb-status-indicator`), `.tags` (horizon `.tag`, strategy `.tag`, tier and Lv `sb-quality-chip`, badge `sb-quality-chip`, cohort `sb-chip` as a direct child, earnings `span.earnings > sb-chip`, `span.origin` when origin is not `plan`, `span.trade-id`) and `.actions` (one `button[sb-button]` per `availableActions(status)`, Delete with `variant="danger"`). No `sb-control-row` and no "Actions" panel anywhere on the page.
- Produces (`TradeDetail`): `side: Signal<'Long' | 'Short' | null>`, `earningsChip: Signal<string | null>` (`Earnings in <N>d` on the open and pending groups only).

Rules (spec § 1, amendment 7):
- The badge renders as `sb-quality-chip` (the tier/Lv precedent), and the earnings chip sits inside `span.earnings`. So `.tags > sb-chip` still means "the cohort chip" to the six v86 cohort cases, whose fixture carries `badge: 'VALIDATED'`.
- The earnings chip shows on the open (`ACTIVE`, `PARTIAL`) and pending (`PENDING`) groups only, and only when the earnings gate recorded a number. A `null` gate value ("not recorded") shows no chip.
- `origin` values on the wire are `plan` and `legacy` (`trades.py:265`, `:470`); the tag shows for anything but `plan`.
- `.head` stays defined in `trade-detail.ts`, so the `PROMOTED_ALLOWLIST` entry in `ui/primitives.spec.ts` stays as it is. No new class is named `.note`, `.chips`, `.head` or `.row-link`.

- [ ] **Step 1: Write the failing identity-line cases**

In `frontend/src/app/workspaces/trades/trade-detail.spec.ts`, delete this case from describe A (`TradeDetail — the fields that rendered nowhere`); its intent moves to the header below:

```ts
  it('offers Close on a live position (SR48, through the real component)', () => {
    // SR48 fixed availableActions; this is the same fix seen from the screen,
    // which is where the absence was invisible for a whole phase.
    expect(render('live')).toContain('Close');
  });
```

Then add this describe block directly after the `TradeDetail — outcome strip (v166)` block (TD5):

```ts
describe('TradeDetail — identity line (v166)', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        TradeDetailStore,
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  /** Mount (default tab unless one is named) and settle the detail request. */
  function mount(status = 'ACTIVE', overrides: object = {}, detail: object = DETAIL, tab = '') {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', tab);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(detail, status, overrides));
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  /* The earnings gate as `why_view.py` `_earnings_row` sends it: `value` is
   * the days to earnings recorded at plan time, or null when not recorded. */
  function earningsGate(value: number | null) {
    return {
      key: 'earnings',
      label: 'Earnings',
      value,
      threshold: value === null ? null : 5,
      margin: value === null ? null : value - 5,
      applies: value !== null,
      parts: [],
      note: value === null ? 'not recorded' : null,
    };
  }

  const withEarnings = (value: number | null) => ({ ...DETAIL, gates: [earningsGate(value)] });

  const actionTexts = (el: HTMLElement) =>
    [...el.querySelectorAll('header.head .identity .actions button[sb-button]')].map(
      (button) => button.textContent?.trim(),
    );

  it('names the side in words, next to the ticker', () => {
    expect(mount('ACTIVE').querySelector('.trade-title .side')?.textContent?.trim()).toBe('Long');
  });

  it('names a short side "Short"', () => {
    const el = mount('ACTIVE', { direction: 'bearish' });
    expect(el.querySelector('.trade-title .side')?.textContent?.trim()).toBe('Short');
  });

  it('shows the badge as a quality chip', () => {
    const chips = [...mount('ACTIVE').querySelectorAll('.tags sb-quality-chip')].map((chip) =>
      chip.textContent?.trim(),
    );
    expect(chips).toContain('VALIDATED');
  });

  it('shows no badge chip when the badge is null', () => {
    const el = mount('ACTIVE', { badge: null });
    expect(el.querySelector('.tags')?.textContent).not.toContain('VALIDATED');
  });

  it('keeps the cohort chip the only direct sb-chip of the tags', () => {
    // Badge VALIDATED and an earnings chip are both present; neither may be
    // mistaken for the cohort chip by `.tags > sb-chip` (spec amendment 7).
    const el = mount('ACTIVE', {}, withEarnings(19));
    expect(el.querySelector('.tags > sb-chip')).toBeNull();
    expect(el.querySelector('.tags .earnings sb-chip')).not.toBeNull();
  });

  it('shows the days to earnings on an open trade', () => {
    const el = mount('ACTIVE', {}, withEarnings(19));
    expect(el.querySelector('.tags .earnings')?.textContent?.trim()).toBe('Earnings in 19d');
  });

  it('shows the days to earnings on a partial trade and a pending plan', () => {
    expect(mount('PARTIAL', {}, withEarnings(7)).querySelector('.tags .earnings')).not.toBeNull();
    expect(mount('PENDING', {}, withEarnings(7)).querySelector('.tags .earnings')).not.toBeNull();
  });

  it('shows no earnings chip on a closed trade', () => {
    const el = mount('CLOSED', { exit_price: 110, r_multiple: 2 }, withEarnings(19));
    expect(el.querySelector('.tags .earnings')).toBeNull();
  });

  it('shows no earnings chip when the gate did not record the date', () => {
    expect(mount('ACTIVE', {}, withEarnings(null)).querySelector('.tags .earnings')).toBeNull();
  });

  it('tags a legacy record with its origin', () => {
    expect(mount('ACTIVE', { origin: 'legacy' }).querySelector('.tags .origin')?.textContent?.trim()).toBe(
      'legacy',
    );
  });

  it('shows no origin tag for a plan', () => {
    expect(mount('ACTIVE').querySelector('.tags .origin')).toBeNull();
  });

  it('keeps the trade id in the tags', () => {
    expect(mount('ACTIVE').querySelector('.tags .trade-id')?.textContent?.trim()).toBe(ID);
  });

  // SR48 fixed availableActions; this is the same fix seen from the screen,
  // which is where the absence was invisible for a whole phase. v166 moves
  // the buttons from the Live tab's Actions card into the header.
  it('offers Close and Delete in the header on a live position', () => {
    expect(actionTexts(mount('ACTIVE'))).toEqual(['Close', 'Delete']);
  });

  it('offers Cancel plan and Delete on a pending plan', () => {
    expect(actionTexts(mount('PENDING'))).toEqual(['Cancel plan', 'Delete']);
  });

  it('offers only Delete on a closed trade', () => {
    expect(actionTexts(mount('CLOSED', { exit_price: 110 }))).toEqual(['Delete']);
  });

  it('keeps Delete on the danger variant', () => {
    const buttons = [...mount('ACTIVE').querySelectorAll<HTMLElement>('.identity .actions button[sb-button]')];
    const del = buttons.find((button) => button.textContent?.trim() === 'Delete');
    expect(del?.classList.contains('danger')).toBe(true);
  });

  it('shows the actions on every tab, and no Actions card', () => {
    for (const tab of ['', 'live', 'notes']) {
      const el = mount('ACTIVE', {}, DETAIL, tab);
      expect(actionTexts(el)).toEqual(['Close', 'Delete']);
      expect(el.querySelector('sb-control-row')).toBeNull();
      const headings = [...el.querySelectorAll('sb-panel h2')].map((h) => h.textContent?.trim());
      expect(headings).not.toContain('Actions');
    }
  });
});
```

- [ ] **Step 2: Run the page spec to verify the new cases fail**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts`
Expected: FAIL in `TradeDetail — identity line (v166)` (no `.side`, no `.identity .actions`, an Actions panel on `live`). The six cohort-chip cases and every other block still pass.

- [ ] **Step 3: Rewrite the header in `trade-detail.ts`**

Imports: change

```ts
import { ControlRow, Panel, Tab, TabBar } from '../../ui/layout';
```

to

```ts
import { Panel, Tab, TabBar } from '../../ui/layout';
```

and add after the `./outcome-tiles` import (TD5):

```ts
import { sideLabel, statusGroup } from './trade-figures';
```

In the `@Component` `imports:` array, delete the `ControlRow,` line.

Replace the whole `@if (store.trade(); as trade) { ... }` branch inside `<header class="head">` (from `@if (store.trade(); as trade) {` down to, not including, `} @else if (store.error(); as message) {`) with:

```html
      @if (store.trade(); as trade) {
        <!-- v166 -- the identity line: who the trade is (ticker, side,
             status), how it is classed (chips), and what can be done to it
             (the actions, at the right end -- they wrap under the chips on a
             narrow screen instead of taking a row of their own, which is
             what the old Actions card did at 390 px). -->
        <div class="identity">
          <div class="trade-title" role="heading" aria-level="2">
            <span class="ticker">{{ trade.ticker }}</span>
            @if (side(); as sideText) {
              <span class="side">{{ sideText }}</span>
            }
            <sb-status-indicator
              [status]="trade.status"
              [current]="trade.current_price"
              [entry]="trade.entry"
              [stop]="trade.stop_loss"
              [target]="trade.target"
            />
          </div>
          <div class="tags">
            @if (trade.horizon) {
              <span class="tag">{{ trade.horizon }}</span>
            }
            @if (trade.strategy) {
              <span class="tag">{{ trade.strategy }}</span>
            }
            @if (trade.tier) {
              <sb-quality-chip [value]="trade.tier" [label]="'Tier ' + trade.tier" />
            }
            @if (trade.confidence_level !== null) {
              <sb-quality-chip
                [value]="trade.confidence_level"
                [label]="'Lv' + trade.confidence_level"
              />
            }
            <!-- v166 -- the badge, as a quality chip like tier and Lv. Never a
                 bare sb-chip here: .tags > sb-chip means "the cohort chip"
                 (spec amendment 7). -->
            @if (trade.badge) {
              <sb-quality-chip [value]="trade.badge" [label]="trade.badge" />
            }
            <!-- v86 -- the cohort risk verdict. COHORT_TYPICAL renders no
                 chip at all (the brief's own token guidance): "typical" is
                 the silent default every other label is judged against, and a
                 chip for it would just be visual noise on every ordinary
                 trade. -->
            @if (cohortTone(); as tone) {
              <sb-chip [label]="cohortChipLabel()" [tone]="tone" [title]="cohortTooltip()" />
            }
            <!-- v166 -- days to earnings as the earnings gate recorded them,
                 on open and pending trades only. Wrapped in a span for the
                 same reason as the badge above. -->
            @if (earningsChip(); as label) {
              <span class="earnings">
                <sb-chip [label]="label" tone="warn" [caps]="false" />
              </span>
            }
            @if (trade.origin !== 'plan') {
              <span class="origin muted">{{ trade.origin }}</span>
            }
            <!-- The id a Discord command (!trade ID) or the API needs to name
                 this exact trade -- previously only visible in the Trades
                 list's # column (and truncated there, see shortId()), so
                 reaching this page by clicking a row lost the one thing
                 someone might come here to copy. -->
            <span class="trade-id" [title]="'Trade ID: ' + trade.id">{{ trade.id }}</span>
          </div>
          <div class="actions">
            @for (kind of actionsFor(trade.status); track kind) {
              <button
                sb-button
                [variant]="kind === 'delete' ? 'danger' : 'secondary'"
                type="button"
                (click)="ask(kind)"
              >
                {{ actionLabels[kind] }}
              </button>
            }
          </div>
        </div>
```

In the Live tab (`@case ('live')`), delete the whole Actions panel, from `<sb-panel heading="Actions">` through its closing `</sb-panel>`:

```html
            <sb-panel heading="Actions">
              <sb-control-row class="commands">
                @for (kind of actionsFor(trade.status); track kind) {
                  <button
                    sb-button
                    [variant]="kind === 'delete' ? 'danger' : 'secondary'"
                    type="button"
                    (click)="ask(kind)"
                  >
                    {{ actionLabels[kind] }}
                  </button>
                }
              </sb-control-row>
            </sb-panel>
```

The `<sb-confirm-dialog>` at the end of the template, `ask()`, `runPending()` and the confirm computeds stay unchanged.

- [ ] **Step 4: Add the two computeds**

In the `TradeDetail` class, after `cohortTooltip`, add:

```ts
  /* -- v166: the identity line ------------------------------------------ */

  /** Long / Short as words -- the arrow-only direction read as decoration. */
  protected readonly side = computed(() => sideLabel(this.store.trade()?.direction ?? null));

  /** "Earnings in 19d" on an open or pending trade whose earnings gate
   *  recorded a number; null otherwise (closed and unfilled trades, and a gate
   *  that says "not recorded"). */
  protected readonly earningsChip = computed<string | null>(() => {
    const trade = this.store.trade();
    const days = this.store.earningsDays();
    if (!trade || days === null) return null;
    const group = statusGroup(trade.status, trade.exit_price ?? null);
    return group === 'open' || group === 'pending' ? `Earnings in ${days}d` : null;
  });
```

- [ ] **Step 5: Update the header styles**

Replace the `.tags` rule:

```css
    .tags {
      display: flex;
      align-items: center;
      gap: var(--space-6);
      flex-wrap: wrap;
    }
```

with:

```css
    /* v166 -- ticker/side/status, the chips, and the actions on one line
       that wraps: the chips take the free width, the actions keep to the
       right end and drop under the chips on a narrow screen. */
    .identity {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-8) var(--space-14);
    }
    .tags {
      flex: 1 1 240px;
      min-width: 0;
      display: flex;
      align-items: center;
      gap: var(--space-6);
      flex-wrap: wrap;
    }
    .side {
      font-size: var(--text-table);
      font-weight: 600;
      color: var(--text-secondary);
    }
    .origin {
      font-size: var(--text-chip);
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-8);
      margin-left: auto;
    }
```

Delete the now orphaned comment:

```css
    /* .commands keeps its class as a marker only -- sb-control-row supplies
       display, alignment, wrap and gap. */
```

(`margin-left: auto` is not one of the outer margins `spacing.spec.ts` bans, and `.actions` is not a panel-level selector.)

- [ ] **Step 6: Run the page spec and the UI gates**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/trades/outcome-tiles.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts`
Expected: PASS, 0 failed, including the six `TradeDetail — the cohort risk chip (v86 C8)` cases unchanged. A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once.

Then check nothing else still imports or styles the removed pieces:

Run: `git -C $WT grep -n -E "ControlRow|sb-control-row|\.commands" -- frontend/src/app/workspaces/trades/trade-detail.ts`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git -C $WT add frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts
git -C $WT commit -m "feat(v166): TD6 identity line -- side, badge and earnings chips, header actions

Ticker, Long/Short and status; horizon, strategy, tier, Lv, badge (quality
chip), cohort, earnings-in-Nd (open and pending only), origin when not a
plan, trade id; Close/Cancel/Delete at the right end of the line. The Live
tab's Actions card and its control row are gone.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

