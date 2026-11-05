# v194 — UI integrity, part 3: risk formatters and sector heat (V194-7..V194-9)

> **For agentic workers:** constraints, `### Standard task close`, `## Handoff` and `## Parallelisation` live in the index: [2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md](2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md). Pull one task at a time: `grep -n "^### Task V194-8:" -A 400 <this file>`.

**Bump:** ui patch, bot patch
**Edge:** none (integrity)
**Spec:** [2026-10-25-v194-ui-tooltips-and-data-truth.md](../specs/2026-10-25-v194-ui-tooltips-and-data-truth.md) — § B4, § B5, § B6

`WT` below is the v194 worktree's absolute path. Line numbers are those on
`main` at plan time; where an earlier task in this part moved them, the task
says "as left by V194-n" and anchors on the quoted snippet.

# Phase 3 — Risk figures that are true

### Task V194-7: B4/B5 — `shareCount` and `riskPct` formatters; unrounded totals; Risk, trade detail and row drawer use them

**Model:** sonnet — two pure formatters and mechanical call-site swaps across known files, specified to the snippet.

**Spec:** § B4, § B5. Today Risk's Exposure table renders 2.72 shares as
`num(row.shares, 0)` = "3", a `risk_pct` of 0.002 as "0.00%", and the Risk %
footer as `num(sum)` with no "%". After this task one share formatter and one
risk-percentage formatter run every such figure; totals are sums of the
unrounded values, formatted once; a tiny non-zero risk reads "<0.01%" with its
exact value in an `sb-hint` (the phone row drawer renders the same cell
template, hint included; the compact row is `inert`); the Exposure panel's
hint says what the share count is and, when rounded rows visibly do not add
up, that totals use unrounded values. `quantity(value, maxDecimals = 2)`
(`ui/format.ts:50-53`, v183) already formats a share count; `shareCount` is
the ledger's named entry point and delegates to it.

**Files:**
- Modify: `frontend/src/app/ui/format.ts:46-53` (add `shareCount`, `riskPct` after `quantity`)
- Modify: `frontend/src/app/ui/format.spec.ts:3` (import; two `describe` blocks appended)
- Modify: `frontend/src/app/workspaces/risk/risk.ts:22-59` (imports, module helpers) and L216-220, L288-293, L306, L331, L447-451, L658-661, L708, L711, L851-852
- Modify: `frontend/src/app/workspaces/risk/risk.spec.ts:20` (import; two `describe` blocks appended after L464)
- Modify: `frontend/src/app/workspaces/trades/position-card.ts:3-25` (`positionRows`)
- Modify: `frontend/src/app/workspaces/trades/why/sizing-panel.ts:3-54` (Shares row)
- Modify: `frontend/src/app/workspaces/trades/trades.columns.ts:4-170` (`tradeColumns` shares column: Trades table and its row drawer)
- Modify: `frontend/src/app/workspaces/trades/position-card.spec.ts:29`, `frontend/src/app/workspaces/trades/why/sizing-panel.spec.ts:27`, `frontend/src/app/workspaces/trades/trades.columns.spec.ts:3`

The three trades `*.spec.ts` files are beyond the ledger's file list:
`sizing-panel.spec.ts:27` pins `'1,234'` for 1234.4 shares, the rounding this
task removes; the other two carry the new call sites' tests. No other v194
task touches them.

**Interfaces:**
- Consumes: `num`, `quantity`, `ABSENT`, `grouped` (private, `ui/format.ts`); `Hint` (`ui/hint.ts`, inputs `text`, `label`; as left by V194-1/V194-2); `riskCell` (`risk.ts:697`).
- Produces: `shareCount(value: number | null | undefined): string`, `riskPct(value: number | null | undefined): string` (`ui/format.ts`). Local to `risk.ts`, exported for its spec: `EXPOSURE_HINT`, `UNROUNDED_TOTALS_NOTE`, `reconciles(values, decimals): boolean`, `exposureHint(rows): string`, `exactRiskText(value): string | null`. V194-9 and V194-11 edit `risk.ts` after this task and keep them.

- [ ] **Step 1: Write the formatter tests**

`frontend/src/app/ui/format.spec.ts` L3: add `riskPct, shareCount` to the
`./format` import (alphabetical: `amount, held, money, quantity, riskPct,
shareCount, signed, timeInZone`). Append at the end of the file:

```ts
describe('shareCount (v194 B4: fractional shares are not rounded to whole)', () => {
  it('renders integers bare and keeps one or two decimals, trailing zeros dropped', () => {
    expect(shareCount(3)).toBe('3');
    expect(shareCount(0.5)).toBe('0.5');
    expect(shareCount(2.7)).toBe('2.7');
    expect(shareCount(2.72)).toBe('2.72');
    expect(shareCount(1234.4)).toBe('1,234.4');
  });

  it('rounds at the third decimal', () => {
    expect(shareCount(1.236)).toBe('1.24');
    expect(shareCount(1.234)).toBe('1.23');
    expect(shareCount(2.999)).toBe('3');
  });

  it('renders a real zero as 0 and absence as the em dash', () => {
    expect(shareCount(0)).toBe('0');
    expect(shareCount(null)).toBe('—');
    expect(shareCount(undefined)).toBe('—');
  });
});

describe('riskPct (v194 B5: a tiny risk never reads as zero)', () => {
  it('renders an exact zero, and -0, as 0.00%', () => {
    expect(riskPct(0)).toBe('0.00%');
    expect(riskPct(-0)).toBe('0.00%');
  });

  it('renders a non-zero value below 0.01 as <0.01%, and 0.01 itself at two decimals', () => {
    expect(riskPct(0.002)).toBe('<0.01%');
    expect(riskPct(0.0099)).toBe('<0.01%');
    expect(riskPct(0.01)).toBe('0.01%');
  });

  it('renders two grouped decimals with the unit, unsigned when positive', () => {
    expect(riskPct(1.234)).toBe('1.23%');
    expect(riskPct(3)).toBe('3.00%');
    expect(riskPct(1234.5)).toBe('1,234.50%');
  });

  it('keeps the sign of a negative value, tiny or not', () => {
    expect(riskPct(-1.234)).toBe('-1.23%');
    expect(riskPct(-0.002)).toBe('-<0.01%');
  });

  it('renders absence as the em dash', () => {
    expect(riskPct(null)).toBe('—');
    expect(riskPct(undefined)).toBe('—');
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/format.spec.ts`
Expected: FAIL — `shareCount` / `riskPct` are not exported from `./format`.

- [ ] **Step 3: Implement the formatters**

`frontend/src/app/ui/format.ts`: insert after `quantity` (after L53):

```ts
/** v194 B4: the one share-count formatter for Risk, trade detail and the
 *  row drawer. The paper book sizes positions unrounded under the 2%
 *  dollar-risk cap, so 2.72 shares is a real figure and "3" overstated it.
 *  `quantity` at its two-decimal ceiling, named for what it formats. */
export function shareCount(value: number | null | undefined): string {
  return quantity(value, 2);
}

/** v194 B5: the one percentage formatter for portfolio heat, per-position
 *  risk and their totals. Unsigned like `share` (a budget is a level, not a
 *  movement), sign kept on a negative. A non-zero value under 0.01 renders
 *  "<0.01%": at two decimals it printed "0.00%", claiming no risk where
 *  there is some. An exact zero (or -0) is "0.00%". */
export function riskPct(value: number | null | undefined): string {
  if (value === null || value === undefined) return ABSENT;
  if (value === 0) return '0.00%';
  if (Math.abs(value) < 0.01) return `${value < 0 ? '-' : ''}<0.01%`;
  return `${grouped(value, 2)}%`;
}
```

Run the Step 2 command again. Expected: PASS.

- [ ] **Step 4: Write the Risk page tests**

`frontend/src/app/workspaces/risk/risk.spec.ts` L20, old → new:
`import { Risk } from './risk';` →
`import { EXPOSURE_HINT, Risk, UNROUNDED_TOTALS_NOTE, exactRiskText, reconciles } from './risk';`

Append after the phone block (after L464). It uses the file's own `render`,
`installDialogPolyfill`, `phoneViewport` and `openRowDrawer`:

```ts
/* -- v194 B4/B5 -- shares and risk percentages that are true -- */

const FRACTIONAL_BOOK = [
  { trade_id: 'a', ticker: 'AAA', strategy: 'VWAP', shares: 2.72, entry: 100, stop_loss: 95, risk_pct: 0.004 },
  { trade_id: 'b', ticker: 'BBB', strategy: 'VWAP', shares: 3, entry: 50, stop_loss: 49, risk_pct: 0.004 },
  { trade_id: 'c', ticker: 'CCC', strategy: 'VWAP', shares: 0.5, entry: 10, stop_loss: 9, risk_pct: 0.004 },
];

describe('Risk exposure figures (v194 B4/B5)', () => {
  async function phone(): Promise<{ fixture: ComponentFixture<Risk>; table: HTMLElement }> {
    installDialogPolyfill();
    const fixture = await render({ positions: FRACTIONAL_BOOK }, [phoneViewport()]);
    return { fixture, table: (fixture.nativeElement as HTMLElement).querySelector('sb-data-table') as HTMLElement };
  }
  const drawerField = (table: HTMLElement, key: string) =>
    table.querySelector(`sb-drawer.row-drawer dl.drawer-fields > [data-col="${key}"]`)!;
  const exposureTip = (fixture: ComponentFixture<Risk>) =>
    (fixture.nativeElement as HTMLElement)
      .querySelector('sb-panel[heading="Exposure by position"] header sb-hint [role="tooltip"]')!.textContent ?? '';

  it('renders fractional shares in the drawer and totals the unrounded values', async () => {
    const { fixture, table } = await phone();
    // 2.72 + 3 + 0.5 = 6.22 -- not 3 + 3 + 1 = 7.
    expect(table.querySelector('.compact-footer [data-col="shares"]')!.textContent).toContain('6.22');
    openRowDrawer(table);
    fixture.detectChanges();
    expect(drawerField(table, 'shares').textContent).toContain('2.72');
  });

  it('renders a tiny non-zero risk as <0.01%, never 0.00%, and the total with its unit', async () => {
    const { table } = await phone();
    const cell = table.querySelector('.compact-cell[data-col="risk_pct"]')!;
    expect(cell.textContent).toContain('<0.01%');
    expect(cell.textContent).not.toContain('0.00%');
    // 3 x 0.004 = 0.012 -> "0.01%", with the "%" the old footer dropped.
    expect(table.querySelector('.compact-footer [data-col="risk_pct"]')!.textContent).toContain('0.01%');
  });

  it('puts the exact tiny value in an sb-hint, reachable in the row drawer', async () => {
    const { fixture, table } = await phone();
    openRowDrawer(table);
    fixture.detectChanges();
    const hint = drawerField(table, 'risk_pct').querySelector('sb-hint')!;
    expect(hint.querySelector('[role="tooltip"]')!.textContent).toContain('0.004%');
    expect(hint.querySelector('button')!.getAttribute('aria-label')).toBe('Exact risk for AAA');
  });

  it('says totals use unrounded values only when the rounded rows do not add up', async () => {
    const mismatch = exposureTip(await render({ positions: FRACTIONAL_BOOK }));
    expect(mismatch).toContain('paper book');
    expect(mismatch).toContain('2% dollar-risk cap');
    expect(mismatch).toContain(UNROUNDED_TOTALS_NOTE);
    const reconciled = exposureTip(await render());
    expect(reconciled.trim()).toBe(EXPOSURE_HINT);
  });

  it('formats the heat figure, the budget and sector heat through the same formatter', async () => {
    const el = (await render({
      heat: { open_pct: 0.003, cap_pct: 6, utilisation_pct: 0.1 },
      sector_heat: [{ sector: 'Technology', heat_pct: 0.003 }],
    })).nativeElement as HTMLElement;
    expect(el.querySelector('.heat-figure')!.textContent).toContain('<0.01%');
    expect(el.querySelector('.risk-budget')!.textContent).toContain('<0.01%');
    expect(el.querySelector('.sectors dd')!.textContent!.trim()).toBe('<0.01%');
  });
});

describe('Risk exposure helpers (v194 B4/B5)', () => {
  it('reconciles when the rounded rows add up to the rounded total', () => {
    expect(reconciles([2.72, 3.5], 2)).toBe(true);
    expect(reconciles([], 2)).toBe(true);
    expect(reconciles([null, 1], 2)).toBe(true);
    expect(reconciles([0.004, 0.004, 0.004], 2)).toBe(false);
  });

  it('gives an exact value only for a tiny non-zero risk', () => {
    expect(exactRiskText(0.002)).toContain('0.002%');
    expect(exactRiskText(-0.002)).toContain('-0.002%');
    for (const shown of [0, 0.01, 3, null]) expect(exactRiskText(shown)).toBeNull();
  });
});
```

The existing `'keeps the shares and Risk % totals as a compact totals line'`
(L450-454) keeps passing: `shareCount(10)` is "10", `riskPct(3)` is "3.00%".

- [ ] **Step 5: Run them to see them fail**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/risk/risk.spec.ts`
Expected: FAIL — the new `./risk` exports do not exist.

- [ ] **Step 6: Implement the Risk page changes** (`frontend/src/app/workspaces/risk/risk.ts`)

Imports: L22 adds `riskPct` and `shareCount` to the `../../ui/format` import;
add `import { Hint } from '../../ui/hint';` after it; the component
`imports:` array (L59) gains `Hint` after `Freshness`.

Insert after the `tablePerPage` import (after L31, above the class doc comment):

```ts
/** v194 B4/B5: what the Exposure table's figures are, shown as the panel's
 *  hint. Copy rules (index Global Constraints): paper, no recommendation. */
export const EXPOSURE_HINT =
  "Shares are the paper book's size, computed unrounded under the 2% dollar-risk cap; " +
  "a broker may fill whole shares or another fraction. Risk % is each position's risk " +
  'to its stop as a share of the account balance; a figure under 0.01% shows as "<0.01%", ' +
  'its exact value in the hint beside it.';

export const UNROUNDED_TOTALS_NOTE =
  'Totals add the unrounded values, so they can differ from the sum of the rounded rows.';

/** True when the rows, each rounded to `decimals`, add up to the rounded
 *  total of the unrounded values: the footer visibly reconciles. Integer
 *  units of the last decimal, so float noise cannot flip it. */
export function reconciles(values: readonly (number | null | undefined)[], decimals: number): boolean {
  const factor = 10 ** decimals;
  const roundedRows = values.reduce<number>((sum, value) => sum + Math.round((value ?? 0) * factor), 0);
  const total = values.reduce<number>((sum, value) => sum + (value ?? 0), 0);
  return roundedRows === Math.round(total * factor);
}

/** The Exposure panel's hint for the rows on screen: the base text, plus the
 *  unrounded-totals note only when shares or Risk % visibly fail to add up. */
export function exposureHint(rows: readonly RiskPosition[]): string {
  const ok = reconciles(rows.map((row) => row.shares), 2) && reconciles(rows.map((row) => row.risk_pct), 2);
  return ok ? EXPOSURE_HINT : `${EXPOSURE_HINT} ${UNROUNDED_TOTALS_NOTE}`;
}

/** The exact value behind a "<0.01%" cell; null when the cell already shows it. */
export function exactRiskText(value: number | null | undefined): string | null {
  if (value === null || value === undefined || value === 0 || Math.abs(value) >= 0.01) return null;
  return `Exact risk: ${value}% of the account balance.`;
}
```

Template swaps, each old → new (the `{{ fmt(store.heatCapPct(), 1) }}% cap`
line at L220 keeps `fmt`: a configured cap, not a risk figure):

- L218: `{{ fmt(store.openHeatPct()) }}%` → `{{ fmtRisk(store.openHeatPct()) }}`
- L291, L292, L293: `{{ fmt(budget.cap) }}%`, `{{ fmt(budget.used) }}%`,
  `{{ fmt(budget.remaining) }}%` → `{{ fmtRisk(budget.cap) }}`,
  `{{ fmtRisk(budget.used) }}`, `{{ fmtRisk(budget.remaining) }}`; the
  comment above them (L288-290) now reads: `riskPct, like the heat figure
  above (v194 B5): two places, and "<0.01%" for a used budget too small to
  print -- 1 place once rounded 0.03% used to a flat "0.0%".`
- L306: `<sb-panel heading="Exposure by position" [flush]="true">` →
  `<sb-panel heading="Exposure by position" [flush]="true" [description]="exposureAbout()">`
- L331: `{{ fmt(row.heat_pct) }}%` → `{{ fmtRisk(row.heat_pct) }}`

L447-451 (`#riskCell`), new body (the existing "Plain, not red" comment stays):

```html
    <ng-template #riskCell let-row>
      <!-- Plain, not red. This is risk budget, not a loss -- painting it red
           would claim money that has not been lost. v194 B5: a tiny risk
           reads "<0.01%" with its exact value in a hint; the row drawer
           renders this same template, hint included. -->
      <span class="num" [sbFlash]="row.risk_pct">{{ fmtRisk(row.risk_pct) }}</span>
      @if (exactRisk(row.risk_pct); as exact) {
        <sb-hint [text]="exact" [label]="'Exact risk for ' + row.ticker" />
      }
    </ng-template>
```

After `exposurePage` (after L661):

```ts
  /** v194 B4/B5: the hint reads the rows the footer sums (the visible page). */
  protected readonly exposureAbout = computed(() => exposureHint(this.exposurePage.visible()));
```

Columns, old → new:

- L708 shares: `value: (row) => num(row.shares, 0)` → `value: (row) => shareCount(row.shares)`, and
  `footer: (rows) => num(rows.reduce((sum, row) => sum + (row.shares ?? 0), 0), 0)` →
  `footer: (rows) => shareCount(rows.reduce((sum, row) => sum + (row.shares ?? 0), 0))`
- L711 risk_pct: `footer: (rows) => num(rows.reduce((sum, row) => sum + (row.risk_pct ?? 0), 0))` →
  `footer: (rows) => riskPct(rows.reduce((sum, row) => sum + (row.risk_pct ?? 0), 0))`

L851-852: keep `protected fmt = num;` (cap, throttle, scan latency use it)
and `fmtText`; add between them:

```ts
  protected fmtRisk = riskPct;
  protected exactRisk = exactRiskText;
```

Run the Step 5 command again. Expected: PASS (new blocks and every existing Risk test).

- [ ] **Step 7: Write the trade-detail and Trades-column tests**

`frontend/src/app/workspaces/trades/position-card.spec.ts`: insert after the
`'hides null rows while retaining real zeros'` test (after L29):

```ts
  it('renders a fractional share count with its decimals (v194 B4)', () => {
    expect(positionRows({ ...base, shares: 2.72 })[0].value).toBe('2.72');
    expect(positionRows({ ...base, status: 'ACTIVE', shares: 0.5 })[0]).toMatchObject({ label: 'Shares', value: '0.5' });
  });
```

`frontend/src/app/workspaces/trades/why/sizing-panel.spec.ts` L27:
`['Shares', '1,234']` → `['Shares', '1,234.4']` (1234.4 shares is 1,234.4
shares); append inside `describe('SizingPanel', ...)`, before its closing `});`:

```ts
  it('keeps a fractional share count, two decimals at most (v194 B4)', () => {
    expect(rows(mount({ shares: 2.72 }))[0]).toEqual(['Shares', '2.72']);
    expect(rows(mount({ shares: 3 }))[0]).toEqual(['Shares', '3']);
  });
```

`frontend/src/app/workspaces/trades/trades.columns.spec.ts` L3:
`import { TRADE_SORTABLE } from '../../api/models';` →
`import { TRADE_SORTABLE, TradeRow } from '../../api/models';`; append inside
`describe('trade column sets', ...)` (opens at L105), before its closing `});`:

```ts
  it('renders the shares column, and so its row drawer, with fractional shares (v194 B4)', () => {
    const shares = tradeColumns().find((column) => column.key === 'shares')!;
    expect(shares.value!({ shares: 2.72 } as TradeRow)).toBe('2.72');
    expect(shares.value!({ shares: 3 } as TradeRow)).toBe('3');
    expect(shares.value!({ shares: null } as TradeRow)).toBe('—');
  });
```

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/trades/position-card.spec.ts --include src/app/workspaces/trades/why/sizing-panel.spec.ts --include src/app/workspaces/trades/trades.columns.spec.ts`
Expected: FAIL — '3' / '1,234' / '3' where '2.72' / '1,234.4' / '2.72' are expected.

- [ ] **Step 8: Swap the three trade call sites to `shareCount`**

Each file adds `shareCount` to its `ui/format` import, then, old → new:

- `position-card.ts` L25: `num(f.shares, 0)` → `shareCount(f.shares)` (`num` stays: Deployed, $ at risk, Trail, Hold cap)
- `why/sizing-panel.ts` L17: `{{ fmtNum(shares(), 0) }}` → `{{ fmtShares(shares()) }}`, and add
  `protected readonly fmtShares = shareCount;` after `fmtNum` (L52)
- `trades.columns.ts` L170: `value: (row) => num(row.shares, 0)` → `value: (row) => shareCount(row.shares)`;
  drop `num` from L4's import only if `git -C "$WT" grep -n "num(" -- frontend/src/app/workspaces/trades/trades.columns.ts` finds no other use

Then confirm no share count elsewhere still rounds to whole:
`git -C "$WT" grep -n "shares[^)]*, 0)" -- frontend/src/app`. Every hit left
must be a non-share figure; a share count left on Risk, trade detail or a
row drawer is swapped the same way and named in the commit.

Run the Step 7 command again. Expected: PASS.

- [ ] **Step 9: Close**

Close: standard (test: frontend/src/app/ui/format.spec.ts) — the narrow run
also takes `--include` for `risk.spec.ts`, `position-card.spec.ts`,
`sizing-panel.spec.ts` and `trades.columns.spec.ts`, then the whole frontend
and lint. One frontend commit:
`fix(v194): fractional shares and tiny risk percentages render true, totals unrounded (V194-7)`.

### Task V194-8: B6 backend — `prod-inspector` cause check; warning logs; `unmapped_count` through extracted helpers; `/risk` field and docstring

**Model:** opus — the production finding decides the scope (spec B6.3), and the change sits in a CC-22 collector feeding `!portfolio`, the admin API and the replay-adjacent universe data.

**Spec:** § B6 (acceptance 1–4; 5 is V194-9). Production's `/api/v1/risk`
serves `sector_heat: []` over 8 open positions. `collect_portfolio_state`
(`swingbot/core/edge/portfolio_state.py:16-106`) builds the map from
`universe.sector_map(SCAN_UNIVERSE)` and swallows every exception into `{}`;
`heat.sector_heat` (`swingbot/core/edge/heat.py:40-46`) then drops any ticker
without a sector. A missing map and a real zero look the same, and the page
says "No sector exposure". After this task the two swallows log at warning
with the exception text, and the collector and `/risk` carry
`unmapped_count`: the open positions `sector_heat` left out for want of a
sector. Hypothesis to test, not assume: `universe.load()`
(`swingbot/core/marketdata/universe.py:93-117`) returns `[]` for a missing
universe file without raising, and `SCAN_UNIVERSE` defaults to `"watchlist"`,
which has no universe file — an empty map, no exception.

**Out of scope, hard (index Global Constraints):** `universe.sector_map`,
`universe.load` and the universe data files are not changed; they feed
`swingbot/core/backtesting/backtest_wf.py:427,545` and
`swingbot/core/tracking/retrospective.py:305,762`. Production is read-only.

**Files:**
- Modify: `swingbot/core/edge/portfolio_state.py:10-55` (logger, two helpers, sector section of `collect_portfolio_state`)
- Modify: `swingbot/admin/api_v1/risk.py:360-402` (`get_risk`: docstring, `unmapped_count`)
- Modify: `tests/admin/test_api_v1_risk.py:125-136` (`test_risk_shape` key set) and append after L580
- Create: `tests/edge/test_portfolio_state_sectors.py` (suite `edge-analytics`, which already lists `tests/edge/`)

**Interfaces:**
- Consumes: `collect_portfolio_state`, `heat.sector_heat`, `universe.sector_map`, `get_risk`, `_cached`, `portfolio_report` (`swingbot/commands/growth.py:128-146`).
- Produces: `_load_sector_map() -> dict` and `_unmapped_count(open_trades: list, sectors: dict) -> int` (in `portfolio_state.py`); `state["unmapped_count"]: int`; `/api/v1/risk` top-level key `unmapped_count: int` (V194-9 reads it).

- [ ] **Step 1: Establish the cause on production, read-only (spec B6.1)**

Write this script to the session scratchpad as `b6_inspect.py` (it prints
config names, file names, counts and tickers, never a secret):

```python
import os

from swingbot import config
from swingbot.core.marketdata import universe
from swingbot.core.tracking.performance import TradeLog

name = getattr(config, "SCAN_UNIVERSE", "watchlist") or "watchlist"
print("SCAN_UNIVERSE:", repr(name))
print("universe dir:", universe.UNIVERSE_DIR, "exists:", os.path.isdir(universe.UNIVERSE_DIR))
if os.path.isdir(universe.UNIVERSE_DIR):
    print("universe files:", sorted(os.listdir(universe.UNIVERSE_DIR)))
for part in name.split("+"):
    path = os.path.join(universe.UNIVERSE_DIR, f"{part}.json")
    print(f"  {part}: file exists={os.path.exists(path)} rows={len(universe.load(part))}")
try:
    sectors = universe.sector_map(name)
    print("sector_map size:", len(sectors))
except Exception as exc:  # the collector swallows this; the inspection must not
    print("sector_map raised:", type(exc).__name__, exc)
    sectors = {}
open_trades = TradeLog().get_trades(status="open", limit=None)
print("open positions:", len(open_trades))
print("unmapped tickers:", sorted({t.get("ticker") for t in open_trades if not sectors.get(t.get("ticker"))}))
```

Dispatch the `prod-inspector` agent to run it in **both** containers (the
admin process serves `/risk`; the bot serves `!portfolio`):

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python -" < "$SCRATCHPAD/b6_inspect.py"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < "$SCRATCHPAD/b6_inspect.py"
```

Record the output (both containers) in the task notes. Classify the cause:

- **(a) missing universe data** — the `SCAN_UNIVERSE` name has no universe
  file, or its file lacks the open tickers. This task then ships only the
  warning logs and `unmapped_count` (Steps 2–7); the commit body records
  the cause and that the data fix is its own spec, reviewed by
  quant-engineer (spec B6.3).
- **(b) an exception** inside `sector_map` or `sector_heat` — Steps 2–7 make
  it visible in the log and in `unmapped_count`. Record the exception text.
- **(c) anything else** (e.g. the map is populated and the tickers match,
  yet `/risk` serves `[]`) — stop and report to the controller with the
  output; a further read-side fix is the partner's call, not this task's.

Steps 2–7 are the same for (a) and (b).

- [ ] **Step 2: Write the collector tests**

Create `tests/edge/test_portfolio_state_sectors.py`:

```python
"""v194 B6: sector heat that tells "no sector data" from "no exposure".

`collect_portfolio_state` over a fixed open book, with the account, trade
log, kill switch and daily bars stubbed so no database, file or network sits
behind it. The sector map is the variable under test."""
import logging

import pytest

from swingbot.commands.growth import portfolio_report
from swingbot.core.edge import heat, portfolio_state
from swingbot.core.marketdata import universe

BALANCE = 10_000.0
# Risk to stop: AAPL 2*10 = $20, MSFT 4*5 = $20, XYZ 1*20 = $20 -> 0.2% each.
OPEN = [
    {"ticker": "AAPL", "entry": 100.0, "stop_loss": 98.0, "shares": 10},
    {"ticker": "MSFT", "entry": 200.0, "stop_loss": 196.0, "shares": 5},
    {"ticker": "XYZ", "entry": 10.0, "stop_loss": 9.0, "shares": 20},
]
FULL_MAP = {"AAPL": "Technology", "MSFT": "Technology", "XYZ": "Industrials"}
LOGGER = "swingbot.core.edge.portfolio_state"


@pytest.fixture
def book(monkeypatch):
    from swingbot.core.edge import throttle
    from swingbot.core.marketdata import data as data_module
    from swingbot.core.planning import account as account_module
    from swingbot.core.tracking.performance import TradeLog

    monkeypatch.setattr(account_module, "load_account_config", lambda: {"balance": BALANCE})
    monkeypatch.setattr(account_module, "get_balance_history_points", lambda: [])
    monkeypatch.setattr(TradeLog, "get_trades", lambda self, status=None, limit=None: [dict(t) for t in OPEN])
    monkeypatch.setattr(throttle, "kill_state", lambda: {"on": False, "reason": None})

    def _no_bars(ticker):
        raise LookupError("no daily bars in this test")

    monkeypatch.setattr(data_module, "get_daily_data", _no_bars)

    def with_map(sectors):
        monkeypatch.setattr(universe, "sector_map", lambda name: dict(sectors))
        return portfolio_state.collect_portfolio_state()

    return with_map


def test_populated_map_heats_every_sector_and_leaves_none_unmapped(book):
    state = book(FULL_MAP)
    assert state["sector_heat"] == {"Technology": pytest.approx(0.4), "Industrials": pytest.approx(0.2)}
    assert state["unmapped_count"] == 0


def test_empty_map_counts_every_open_position_as_unmapped(book):
    state = book({})
    assert state["sector_heat"] == {}
    assert state["unmapped_count"] == 3


def test_map_missing_some_tickers_counts_only_those(book):
    state = book({"AAPL": "Technology"})
    assert state["sector_heat"] == {"Technology": pytest.approx(0.2)}
    assert state["unmapped_count"] == 2


def test_a_failing_sector_map_logs_a_warning_with_the_exception_text(book, monkeypatch, caplog):
    def _boom(name):
        raise ValueError("universe file is corrupt")

    monkeypatch.setattr(universe, "sector_map", _boom)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        state = portfolio_state.collect_portfolio_state()
    assert state["sector_heat"] == {}
    assert state["unmapped_count"] == 3
    assert any(r.levelno == logging.WARNING and "universe file is corrupt" in r.getMessage()
               for r in caplog.records if r.name == LOGGER)


def test_a_failing_sector_heat_logs_a_warning_with_the_exception_text(book, monkeypatch, caplog):
    def _boom(open_trades, balance, sectors):
        raise ZeroDivisionError("heat blew up")

    monkeypatch.setattr(heat, "sector_heat", _boom)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        state = book(FULL_MAP)
    assert state["sector_heat"] == {}
    assert any(r.levelno == logging.WARNING and "heat blew up" in r.getMessage()
               for r in caplog.records if r.name == LOGGER)


def test_unmapped_count_uses_the_same_test_as_sector_heat():
    # `sector_heat` skips a falsy sector; so does the count, so the two agree.
    sectors = {"AAPL": "Technology", "BLANK": ""}
    trades = [{"ticker": "AAPL"}, {"ticker": "BLANK"}, {"ticker": "NOPE"}, {}]
    assert portfolio_state._unmapped_count(trades, sectors) == 3
    assert portfolio_state._unmapped_count([], {}) == 0


def test_growth_portfolio_report_is_unchanged_for_a_populated_map(book):
    """`!portfolio` reads `sector_heat` as a dict and ignores the new key."""
    state = book(FULL_MAP)
    before = {k: v for k, v in state.items() if k != "unmapped_count"}
    out = portfolio_report(state)
    assert out == portfolio_report(before)
    assert "Technology" in out and "Industrials" in out
```

- [ ] **Step 3: Run them to see them fail**

Run: `python scripts/dev/testrun.py file tests/edge/test_portfolio_state_sectors.py`
Expected: FAIL — `KeyError: 'unmapped_count'`, no warning records, and
`AttributeError: ... has no attribute '_unmapped_count'`.

- [ ] **Step 4: Implement the collector change**

`swingbot/core/edge/portfolio_state.py`. Above L10 (`from swingbot import
config`) add `import logging` and a blank line; after L13 (the `TradeLog`
import) add:

```python

log = logging.getLogger(__name__)


def _load_sector_map() -> dict:
    """v194 B6: the scan universe's ticker -> sector map, or {} when it
    cannot be read. A failure logs at warning with the exception text; an
    empty map, raised or not, shows up as `unmapped_count`.

    Read side only: `universe.sector_map` and the files behind it also feed
    the walk-forward replay's sector cap and the weekly risk report, so they
    are not this module's to change."""
    from swingbot.core.marketdata import universe

    name = getattr(config, "SCAN_UNIVERSE", "watchlist") or "watchlist"
    try:
        return universe.sector_map(name)
    except Exception as exc:
        log.warning("sector map for SCAN_UNIVERSE=%r unavailable: %s", name, exc)
        return {}


def _unmapped_count(open_trades: list, sectors: dict) -> int:
    """v194 B6: open positions `heat.sector_heat` leaves out for want of a
    sector. The same test it applies (`sectors.get(ticker)` falsy), so the
    count and the heat never disagree about which positions were skipped."""
    return sum(1 for trade in open_trades if not sectors.get(trade.get("ticker")))
```

L23: delete `from swingbot.core.marketdata import universe` (the helper
imports it now; nothing else in the function uses it).

L46-55, old → new:

```python
    sectors: dict = {}
    try:
        sectors = universe.sector_map(getattr(config, "SCAN_UNIVERSE", "watchlist") or "watchlist")
    except Exception:
        sectors = {}

    try:
        state["sector_heat"] = heat.sector_heat(open_trades, balance, sectors)
    except Exception:
        state["sector_heat"] = {}
```
```python
    sectors = _load_sector_map()

    try:
        state["sector_heat"] = heat.sector_heat(open_trades, balance, sectors)
    except Exception as exc:
        log.warning("sector heat unavailable: %s", exc)
        state["sector_heat"] = {}
    # v194 B6: with this, `sector_heat == {}` over open positions reads as
    # "no sector data", never as "no exposure".
    state["unmapped_count"] = _unmapped_count(open_trades, sectors)
```

`collect_portfolio_state` loses one `try/except` (CC 22 → 21); no new
branch is added inline. `clusters` below still receives `sectors`.

Run the Step 3 command again. Expected: PASS. Then
`python scripts/dev/testrun.py file tests/edge/test_edge_heat.py` — still
green (its degrade test asserts `sector_heat == {}` with a failing account
config; unaffected).

- [ ] **Step 5: Write the endpoint tests**

Database-backed: if `/replicate-prod-db` has not yet run for this plan
(V194-4's diagnosis step), run it now into the shared `swing-db` container.

`tests/admin/test_api_v1_risk.py` L125-129, `test_risk_shape`'s key set
gains `"unmapped_count": int`:

```python
    assert_shape(body, {
        "heat": dict, "positions": list, "sector_heat": list, "unmapped_count": int,
        "clusters": list, "throttle": dict, "killswitch": dict,
        "scan_health": dict, "metrics": dict, "correlation": dict,
    })
```

Append after `test_sector_heat_is_a_sorted_list_not_a_map` (after L580):

```python
def test_unmapped_count_carries_the_collectors_count(logged_in, monkeypatch):
    """v194 B6: `sector_heat: []` over open positions is "no sector data for
    N positions", and the response says N."""
    monkeypatch.setattr("swingbot.core.edge.portfolio_state.collect_portfolio_state",
                        lambda: {"sector_heat": {}, "unmapped_count": 8})
    body = logged_in.get("/api/v1/risk").get_json()
    assert body["sector_heat"] == []
    assert body["unmapped_count"] == 8


def test_unmapped_count_is_zero_when_the_collector_has_none(logged_in, monkeypatch):
    monkeypatch.setattr("swingbot.core.edge.portfolio_state.collect_portfolio_state", lambda: {})
    assert logged_in.get("/api/v1/risk").get_json()["unmapped_count"] == 0


def test_unmapped_count_from_a_real_book_with_a_partial_sector_map(open_book, client, monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.universe.sector_map",
                        lambda name: {"AAPL": "Technology"})
    open_book(["AAPL", "ZZZZ"])
    body = client.get("/api/v1/risk").get_json()
    assert body["unmapped_count"] == 1
    assert [row["sector"] for row in body["sector_heat"]] == ["Technology"]
```

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py`
Expected: FAIL — `unmapped_count` missing from the response.

- [ ] **Step 6: Implement the endpoint change**

`swingbot/admin/api_v1/risk.py`, `get_risk` (L360-415). Insert as the first
line of the function body (after `def get_risk():`, L362):

```python
    """The Risk page in one read; the shape is `Risk` in
    `frontend/src/app/api/models.ts`.

    Top-level keys: `heat`, `positions`, `sector_heat`, `unmapped_count`,
    `clusters`, `throttle`, `killswitch`, `scan_health`, `metrics`,
    `correlation`.

    `unmapped_count` (v194 B6): open positions with no sector in the scan
    universe's sector map, and therefore absent from `sector_heat`. With it,
    an empty `sector_heat` over open positions reads as "no sector data for
    N of M positions", never as "no exposure". A response field, not a
    stored record; cached with the rest of `collect_portfolio_state`
    (`_cached`, `_RISK_TTL_S`); 0 when the collector produced none.
    """
```

After the `"sector_heat": [...]` entry (after L402), add:

```python
        "unmapped_count": int(state.get("unmapped_count") or 0),
```

`get_risk` goes from CC 11 to 12 (one `or`).

Run the Step 5 command again. Expected: PASS. Then confirm `!portfolio`
still renders: `python scripts/dev/testrun.py file tests/commands/test_growth_command.py`
— green, `portfolio_report` untouched.

- [ ] **Step 7: Close**

Close: standard (test: tests/edge/test_portfolio_state_sectors.py) — the
narrow run also covers `tests/admin/test_api_v1_risk.py`,
`tests/edge/test_edge_heat.py` and `tests/commands/test_growth_command.py`.
The complexity gate must show `collect_portfolio_state` at or below its
baseline (21 expected). One backend commit:
`fix(v194): sector heat logs its failures and reports unmapped positions (V194-8)`;
the body states the Step 1 cause, (a) or (b), with the inspected
`SCAN_UNIVERSE`, universe files and unmapped tickers, and for (a) that the
universe-data fix is a separate spec for quant-engineer review.

### Task V194-9: B6 frontend — "Sector concentration cannot be assessed" banner vs true-zero state

**Model:** sonnet — one optional interface field, one store computed and one template branch on an existing panel input.

**Spec:** § B6 acceptance 4 (the TypeScript interface) and 5 (the banner).
Today the Sector heat panel (`frontend/src/app/workspaces/risk/risk.ts:325-337`)
renders "No sector exposure." whenever `sector_heat` is empty, so 8 open
positions with no sector data read as a reassuring zero. After this task,
when `unmapped_count` (V194-8) is above zero the panel shows a visible
warning — "Sector concentration cannot be assessed: no sector data for N of
M open positions." — through `sb-panel`'s existing `problem` input (rendered
as `<p class="panel-problem" role="status">` in the warn colour,
`frontend/src/app/ui/layout.ts:72-74,152`), keeps any sectors that are
mapped, and never says "No sector exposure". With `unmapped_count` 0 (or
absent, an older server) the true-zero text is unchanged.

**Files:**
- Modify: `frontend/src/app/api/models.ts:1440-1450` (`Risk` interface)
- Modify: `frontend/src/app/stores/risk.store.ts:123` (after `sectorHeat`)
- Modify: `frontend/src/app/workspaces/risk/risk.ts:325-337` (Sector heat panel, as left by V194-7) and the module helpers V194-7 added above the class doc comment, and the class body (a computed beside `exposureAbout`)
- Modify: `frontend/src/app/workspaces/risk/risk.spec.ts:20` (import) and append after the V194-7 blocks at the end of the file

**Interfaces:**
- Consumes: `/api/v1/risk` key `unmapped_count: int` (V194-8); `RiskStore.sectorHeat`, `RiskStore.positions` (`risk.store.ts:121-123`); `Panel.problem` (`ui/layout.ts:195`); `riskPct` via `fmtRisk` in the sector cell (V194-7).
- Produces: `Risk.unmapped_count?: number`; `RiskStore.unmappedCount` (computed, `data()?.unmapped_count ?? 0`); local to `risk.ts`, exported for its spec: `unmappedNote(unmapped: number, open: number): string | null`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/app/workspaces/risk/risk.spec.ts` L20: add `unmappedNote` to
the `./risk` import (as left by V194-7:
`import { EXPOSURE_HINT, Risk, UNROUNDED_TOTALS_NOTE, exactRiskText, reconciles, unmappedNote } from './risk';`).

Append at the end of the file:

```ts
/* -- v194 B6 -- no sector data is not no exposure -- */

const openPositions = (count: number) => Array.from({ length: count }, (_, i) => ({
  trade_id: `t${i}`, ticker: `T${i}`, strategy: 'VWAP', shares: 1, entry: 10, stop_loss: 9, risk_pct: 0.1,
}));

describe('Risk sector heat: no data vs no exposure (v194 B6)', () => {
  const sectorPanel = (fixture: ComponentFixture<Risk>) =>
    (fixture.nativeElement as HTMLElement).querySelector('sb-panel[heading="Sector heat"]') as HTMLElement;
  const squash = (text: string | null | undefined) => (text ?? '').replace(/\s+/g, ' ').trim();

  it('shows the cannot-be-assessed banner, never "No sector exposure", when no position has sector data', async () => {
    const panel = sectorPanel(await render({ positions: openPositions(8), sector_heat: [], unmapped_count: 8 }));
    const banner = panel.querySelector('.panel-problem[role="status"]');
    expect(squash(banner?.textContent))
      .toBe('Sector concentration cannot be assessed: no sector data for 8 of 8 open positions.');
    expect(panel.textContent).not.toContain('No sector exposure');
    expect(panel.querySelector('.sectors')).toBeNull();
  });

  it('keeps the mapped sectors beside the banner when only some positions lack data', async () => {
    const panel = sectorPanel(await render({
      positions: openPositions(2),
      sector_heat: [{ sector: 'Technology', heat_pct: 0.1 }],
      unmapped_count: 1,
    }));
    expect(squash(panel.querySelector('.panel-problem')?.textContent))
      .toBe('Sector concentration cannot be assessed: no sector data for 1 of 2 open positions.');
    expect(panel.querySelector('.sectors dt')!.textContent).toContain('Technology');
  });

  it('shows the true-zero state, and no banner, when every position is mapped', async () => {
    const panel = sectorPanel(await render({ sector_heat: [], unmapped_count: 0 }));
    expect(panel.querySelector('.panel-problem')).toBeNull();
    expect(squash(panel.querySelector('.none')?.textContent)).toBe('No sector exposure.');
  });

  it('reads a response without the field as fully mapped', async () => {
    const panel = sectorPanel(await render({ sector_heat: [] }));
    expect(panel.querySelector('.panel-problem')).toBeNull();
    expect(squash(panel.querySelector('.none')?.textContent)).toBe('No sector exposure.');
  });

  it('exposes the count through the store', async () => {
    await render({ positions: openPositions(3), unmapped_count: 3 });
    expect(TestBed.inject(RiskStore).unmappedCount()).toBe(3);
  });
});

describe('unmappedNote (v194 B6)', () => {
  it('says nothing when every position is mapped', () => {
    expect(unmappedNote(0, 5)).toBeNull();
    expect(unmappedNote(0, 0)).toBeNull();
  });

  it('names N of M, singular for one position', () => {
    expect(unmappedNote(8, 8)).toBe('Sector concentration cannot be assessed: no sector data for 8 of 8 open positions.');
    expect(unmappedNote(1, 1)).toBe('Sector concentration cannot be assessed: no sector data for 1 of 1 open position.');
  });

  it('never claims fewer open positions than unmapped ones', () => {
    // positions and the collector read the book separately; a failed read on
    // one side must not print "3 of 0".
    expect(unmappedNote(3, 0)).toBe('Sector concentration cannot be assessed: no sector data for 3 of 3 open positions.');
  });
});
```

`render`'s `overrides: Partial<RiskData>` accepts `unmapped_count` once Step 3
adds it to the interface; `RiskStore` (L21) and `TestBed` (L9) are already imported.

- [ ] **Step 2: Run them to see them fail**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/risk/risk.spec.ts`
Expected: FAIL — `unmappedNote` is not exported, `unmapped_count` is not on `Risk`.

- [ ] **Step 3: Add the field and the store computed**

`frontend/src/app/api/models.ts`, `Risk` (L1440-1450): after
`sector_heat: SectorHeat[];` (L1443) add:

```ts
  /** v194 B6: open positions with no sector in the scan universe's map, so
   *  absent from `sector_heat`. Above zero, an empty `sector_heat` means "no
   *  sector data", not "no exposure". Optional: specs build full `Risk`
   *  literals, and an older server omits it. */
  unmapped_count?: number;
```

`frontend/src/app/stores/risk.store.ts`: after the `sectorHeat` line (L123) add:

```ts

    /** v194 B6: how many open positions `sectorHeat` leaves out for want of
     *  sector data. 0 when the server sends none. */
    unmappedCount: computed<number>(() => data()?.unmapped_count ?? 0),
```

- [ ] **Step 4: Render the banner**

`frontend/src/app/workspaces/risk/risk.ts`. Below `exactRiskText` (the last
module helper V194-7 added above the class doc comment) add:

```ts
/** v194 B6: the Sector heat panel's warning, or null when every open
 *  position has sector data. M is never below N: the positions table and
 *  the collector read the book separately. */
export function unmappedNote(unmapped: number, open: number): string | null {
  if (unmapped <= 0) return null;
  const total = Math.max(open, unmapped);
  return `Sector concentration cannot be assessed: no sector data for ${unmapped} of ${total} open position${total === 1 ? '' : 's'}.`;
}
```

In the class, after `exposureAbout` (V194-7) add:

```ts
  /** v194 B6: shown through the panel's `problem` slot, which renders it as a
   *  visible status line and never lets the panel fold it away. */
  protected readonly sectorProblem = computed(() =>
    unmappedNote(this.store.unmappedCount(), this.store.positions().length),
  );
```

The Sector heat panel (L325-337 on `main`; L331's cell already reads
`fmtRisk` after V194-7), old → new:

```html
    <sb-panel heading="Sector heat">
      @if (store.sectorHeat().length) {
```
```html
    <sb-panel heading="Sector heat" [problem]="sectorProblem()">
      @if (store.sectorHeat().length) {
```

and the else branch:

```html
      } @else {
        <p class="none">No sector exposure.</p>
      }
```
```html
      } @else if (!sectorProblem()) {
        <!-- A true zero only: with unmapped positions an empty list means
             no sector data, and the panel's problem line says so. -->
        <p class="none">No sector exposure.</p>
      }
```

No new CSS: `.panel-problem` is `sb-panel`'s own warn line, and it wraps at
390 (plain text in a block paragraph, `layout.ts:152`).

- [ ] **Step 5: Run them to see them pass**

Run the Step 2 command again. Expected: PASS (new blocks and every existing Risk test).

- [ ] **Step 6: Check the three widths**

With the replica running (`/replicate-prod-db` already ran in V194-4 or
V194-8) and a build served locally per `docs/claude/ui-design.md`
§ Checklist, take a Playwright screenshot of `/risk` at 390, 768 and 1440
with `/api/v1/risk` routed to a fixture whose `unmapped_count` is 8 and
`sector_heat` is `[]` (`page.route`, no server change). Log in with `.env`'s
`ADMIN_USERNAME`/`ADMIN_PASSWORD`, loaded inside the script, never printed.
The banner is fully visible and wraps inside the panel at each width; no
horizontal scroll. Save the screenshots in the session scratchpad and name
them in the task notes; they are not committed.

- [ ] **Step 7: Close**

Close: standard (test: frontend/src/app/workspaces/risk/risk.spec.ts). One
frontend commit:
`fix(v194): Risk says when sector concentration cannot be assessed (V194-9)`.

