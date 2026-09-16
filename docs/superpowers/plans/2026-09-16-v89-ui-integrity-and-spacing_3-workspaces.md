# v89 Admin UI Integrity and Spacing — Part 3: workspaces

> Header, global constraints, parallelisation and the task index live in `2026-09-16-v89-ui-integrity-and-spacing_0-index.md`. Every task here implicitly includes that file's Global Constraints.

**How the spacing rule is applied in every task below (spec §4.2).** Each rule has a verification step in its task.

1. A workspace host that is a grid uses `gap: var(--section-gap)`, not `var(--register-pad)` or `var(--space-20)`.
2. When an `<sb-async>` wraps **more than one** panel-level child, its content goes inside `<div class="sb-stack">…</div>`. `sb-async`'s own `.content` div is a plain block, so its children otherwise touch (this is the measured 0px on Risk and Trade detail).
3. A row of side-by-side panels keeps its own grid class but sets `gap: var(--section-gap)` and `align-items: start`.
4. Delete `margin-top`/`margin-bottom` from any panel-level selector, and remove that selector's entry from `PENDING_MARGIN_RULES` in `frontend/src/app/ui/spacing.spec.ts`.

# Phase 3 — Workspaces (worktree)

### Task UA8: Dashboard — N on the rate tiles, outcome-coloured activity, positions freshness, spacing

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`interface Dashboard`; add `TradeCollection`)
- Modify: `frontend/src/app/api/api-client.ts:119-124` (`trades()` return type)
- Modify: `frontend/src/app/stores/trades.store.ts` (slice type; `pricesAsOf`)
- Modify: `frontend/src/app/stores/dashboard.store.ts:111-113` (`winRateN`, `expectancyN`)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (inputs at ~150; styles ~420–436)
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/activity.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/recent-activity.ts`
- Modify: `frontend/src/app/workspaces/dashboard/positions-table.ts:72-74`
- Modify: `frontend/src/app/ui/spacing.spec.ts` (remove two dashboard entries)
- Test: `frontend/src/app/stores/trades.store.spec.ts`, `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`, `frontend/src/app/workspaces/dashboard/panels/activity.spec.ts`, `frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts`

**Interfaces:**
- Consumes:
  - UA4: `Dashboard.win_rate_n`, `Dashboard.expectancy_n`.
  - UA7: the `prices_as_of` body key.
  - UA1: `--section-gap`.
- Produces:
  - `export interface TradeCollection extends Collection<TradeRow> { prices_as_of?: string | null }`
  - `TradesStore.pricesAsOf: Signal<string | null>`
  - `DashboardStore.winRateN`, `DashboardStore.expectancyN: Signal<number | null>`
  - `TradingPerformance` inputs `winRateN`, `expectancyN: number | null`
  - `ActivityEvent.r: number | null`

- [ ] **Step 1: Write the failing tests**

`frontend/src/app/stores/trades.store.spec.ts`, inside `describe('TradesStore', …)` after `'loads as soon as setQuery is called…'`:

```ts
  it('exposes when the page\'s live prices were fetched (v89)', () => {
    store.setQuery({ page: 1, per_page: 25 });
    tick();
    expectRequest().flush({ ...COLLECTION, prices_as_of: '2026-09-16T10:44:00+00:00' });

    expect(store.pricesAsOf()).toBe('2026-09-16T10:44:00+00:00');
  });

  it('reports no price time before anything has loaded', () => {
    expect(store.pricesAsOf()).toBeNull();
  });
```

`frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`, append inside the `describe`:

```ts
  it('shows the sample beside win rate and expectancy (v89: "100% win rate" with no N)', () => {
    const el = render({ winRate: 100, winRateN: 1, expectancyR: 0, expectancyN: 2, riskCapPct: 6, currency: '€', scope: 'today' });
    const card = (label: string) => [...el.querySelectorAll('sb-metric-card')].find((c) => c.textContent?.includes(label))!;
    expect(card('Win rate').textContent).toContain('N=1');
    expect(card('Expectancy').textContent).toContain('N=2');
  });
```

`frontend/src/app/workspaces/dashboard/panels/activity.spec.ts`, append inside the `describe`:

```ts
  it('carries the closed trade\'s R so the feed can colour the outcome (v89)', () => {
    const events = deriveActivity([row({ status: 'CLOSED', closed_at: '2026-09-11T16:20:00Z', r_multiple: -1 })]);
    expect(events.find((e) => e.kind === 'closed')!.r).toBe(-1);
    expect(events.find((e) => e.kind === 'opened')!.r).toBeNull();
  });
```

`frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts`, append inside the `describe`:

```ts
  it('colours the outcome by R, not by trade direction (v89: green ▲ beside "-1.00R")', () => {
    const el = render({ events: [
      { kind: 'closed', at: '2026-09-11T15:00:00Z', ticker: 'INTU', direction: 'bullish', status: 'CLOSED', detail: 'Closed at -1.00R', r: -1, id: 'a:closed' },
    ]});
    const detail = el.querySelector('.detail')!;
    expect(detail.classList.contains('neg')).toBe(true);
    expect(detail.classList.contains('pos')).toBe(false);
  });
```

In the same file, add `r: null,` to each existing inline event object literal, so the `ActivityEvent` type-checks.

- [ ] **Step 2: Run them to verify they fail**

Run each with `npm --prefix frontend test -- --include <path>` for the four spec files. Expected: FAIL. `pricesAsOf` is not a function, `N=1` is absent, `r` is undefined, and `.detail` has no `neg`.

- [ ] **Step 3: Models, client and stores**

`frontend/src/app/api/models.ts`, in `interface Dashboard` directly after `payoff_ratio: number | null;`:

```ts
  /** v89: the sample each rate was computed over. win_rate_n counts win/loss
   *  trades; expectancy_n counts trades with a computable R (scratches in). */
  win_rate_n: number;
  expectancy_n: number;
```

Directly after `interface Collection<T> { … }`:

```ts
/** GET /trades. `prices_as_of` is when this page's live prices were fetched,
 *  null when no row on the page was priced (v89). */
export interface TradeCollection extends Collection<TradeRow> {
  prices_as_of?: string | null;
}
```

`frontend/src/app/api/api-client.ts`: change `trades(query: TradeQuery = {}): Observable<Collection<TradeRow>>` to `Observable<TradeCollection>`, and change `this.http.get<Collection<TradeRow>>` to `this.http.get<TradeCollection>`. Add `TradeCollection` to that file's models import.

`frontend/src/app/stores/trades.store.ts`: change `data: Collection<TradeRow> | null;` to `data: TradeCollection | null;` (import `TradeCollection`), and add to `withComputed`, after `rows`:

```ts
    /** v89: when this page's live prices were fetched -- Open Positions' freshness. */
    pricesAsOf: computed(() => data()?.prices_as_of ?? null),
```

`frontend/src/app/stores/dashboard.store.ts`, after `payoffRatio: computed(…)`:

```ts
    winRateN: computed(() => data()?.win_rate_n ?? null),
    expectancyN: computed(() => data()?.expectancy_n ?? null),
```

- [ ] **Step 4: Tiles**

`frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`: add inputs after `readonly expectancyR = input<number | null>(null);`:

```ts
  readonly winRateN = input<number | null>(null);
  readonly expectancyN = input<number | null>(null);
  /** v89: a rate without its sample reads as a finding; "N=1" says it is not one. */
  protected sample(n: number | null): string | null {
    return n === null ? null : `N=${n}`;
  }
```

Change the two cards to:

```html
          <sb-metric-card label="Win rate" [value]="winRate()" unit="%" [decimals]="1" [sub]="sample(winRateN())" />
          <sb-metric-card label="Expectancy" [value]="expectancyR()" tone="pnl" unit="R" [sub]="sample(expectancyN())" />
```

`frontend/src/app/workspaces/dashboard/dashboard.ts` (~line 150), after `[expectancyR]="store.expectancyR()"`:

```html
      [winRateN]="store.winRateN()"
      [expectancyN]="store.expectancyN()"
```

- [ ] **Step 5: Activity outcome**

`frontend/src/app/workspaces/dashboard/panels/activity.ts`: add to `ActivityEvent` after `detail: string;`:

```ts
  /** The closed trade's R, so the feed colours the OUTCOME. Null for opened
   *  and cancelled events, which have no outcome. v89. */
  r: number | null;
```

In the closed/cancelled `events.push({ … })`, add `r: cancelled ? null : (row.r_multiple ?? null),`. In the opened push, add `r: null,`.

`frontend/src/app/workspaces/dashboard/panels/recent-activity.ts`: change the detail span to

```html
              <span class="detail" [class.pos]="(event.r ?? 0) > 0" [class.neg]="(event.r ?? 0) < 0">{{ event.detail }}</span>
```

and add to its styles, after `.detail { … }`:

```css
    .detail.pos { color: var(--pos); }
    .detail.neg { color: var(--neg); }
    /* v89: the triangle is trade DIRECTION. Beside an outcome it read as the
       result -- a green up-arrow next to "-1.00R". Kept, but muted, so the
       coloured text is the only green/red on the row. */
    sb-direction-arrow { filter: grayscale(1); opacity: 0.6; }
```

- [ ] **Step 6: Positions freshness and spacing**

`frontend/src/app/workspaces/dashboard/positions-table.ts`: replace

```html
        <!-- The trades collection has no source timestamp. Mark that fact
             rather than implying the arrival time is market-data freshness. -->
        <sb-freshness [at]="null" />
```

with

```html
        <!-- v89: the list's live prices are fetched during the request, so the
             API's prices_as_of is their real age. Null (closed-only pages, or
             a failed price fetch) still reads "age unknown", honestly. -->
        <sb-freshness [at]="trades.pricesAsOf()" />
```

`frontend/src/app/workspaces/dashboard/dashboard.ts` styles:
- In `:host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--register-pad); }`, change the gap to `var(--section-gap)`, and replace the v54 comment above it with: `v89: --section-gap, the one gap between panels (spec §4.2).`
- Replace the `.bottom-row { … }` and `.positions-panel { … }` rules, and the comment above them, with:

```css
    /* v89: no margins -- the host grid's --section-gap is the only space
       between panels. The row keeps its own columns and the same gap. */
    .bottom-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      align-items: start;
      gap: var(--section-gap);
    }
```

`frontend/src/app/ui/spacing.spec.ts`: delete the entries `'app/workspaces/dashboard/dashboard.ts|.bottom-row'` and `'app/workspaces/dashboard/dashboard.ts|.positions-panel'`.

- [ ] **Step 7: Run to verify it passes**

Run the four specs from Step 2, plus:
- `npm --prefix frontend test -- --include src/app/workspaces/dashboard/dashboard.spec.ts`
- `npm --prefix frontend test -- --include src/app/workspaces/dashboard/positions-table.spec.ts`
- `npm --prefix frontend test -- --include src/app/ui/spacing.spec.ts`

Expected: PASS for all.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/stores/trades.store.ts frontend/src/app/stores/trades.store.spec.ts frontend/src/app/stores/dashboard.store.ts frontend/src/app/workspaces/dashboard frontend/src/app/ui/spacing.spec.ts
git commit -m "fix(v89): dashboard shows N on rates, colours activity by outcome, dates its prices, and spaces panels by the section gap"
```

---

### Task UA9: Risk — precision, money at risk, sector-unknown, scan-health absent state, one heat reading, spacing

**Files:**
- Modify: `frontend/src/app/workspaces/risk/risk.ts`
- Test: `frontend/src/app/workspaces/risk/risk.spec.ts`

**Interfaces:**
- Consumes: UA1 `.sb-stack`, `--section-gap`.
- Produces: `Risk.fmtRisk(value: number | null): string` (protected); column key `risk_amount`.

- [ ] **Step 1: Replace the gauge tests with the new expectations (failing)**

In `frontend/src/app/workspaces/risk/risk.spec.ts`, delete the two tests `'drives the gauge from heat utilisation'` and `'shows a utilisation past the cap truthfully rather than pinned at 100'`, and add in their place:

```ts
  it('reads heat once, as figure, bar and one utilisation line -- no gauge (v89)', async () => {
    const el = (await render({ heat: { open_pct: 0.01, cap_pct: 6, utilisation_pct: 0.2 } }))
      .nativeElement as HTMLElement;
    expect(el.querySelector('sb-gauge')).toBeNull();
    // Was "0% of the risk budget in use" beside a gauge reading 0.2%.
    expect(el.querySelector('.heat-note')!.textContent).toContain('0.2% of the 6.0% cap in use');
  });

  it('keeps saying so in words when heat is past the cap', async () => {
    const el = (await render({ heat: { open_pct: 7.8, cap_pct: 6, utilisation_pct: 130 } }))
      .nativeElement as HTMLElement;
    expect(el.querySelector('.heat-note')!.textContent).toContain('130% of the cap');
  });

  it('shows a tiny position risk to a precision that is not zero (v89)', async () => {
    const el = (await render({
      positions: [{ trade_id: 't1', ticker: 'AXON', strategy: 'FVG', shares: 2, entry: 440.44, stop_loss: 425.76, risk_pct: 0.0029 }],
    })).nativeElement as HTMLElement;
    expect(el.textContent).toContain('0.003%');
    // Not a bare "0.00%" anywhere (the budget's "20.00%" is fine: digit before it).
    expect(el.textContent).not.toMatch(/(^|[^0-9])0\.00%/);
    // Money at risk to the stop: |440.44 - 425.76| x 2 = 29.36.
    expect(el.textContent).toContain('29.36');
  });

  it('says sectors are unknown rather than claiming no exposure (v89)', async () => {
    const el = (await render({ sector_heat: [] })).nativeElement as HTMLElement;
    const text = el.textContent ?? '';
    expect(text).not.toContain('No sector exposure.');
    expect(text).toContain('Sector unknown for 1 open position');
  });

  it('renders an absent scan duration as words, not "—s" (v89)', async () => {
    const el = (await render({ scan_health: { latest_s: null, slowdown: false } } as never))
      .nativeElement as HTMLElement;
    expect(el.textContent).toContain('No scan recorded');
    expect(el.textContent).not.toContain('—s');
  });
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm --prefix frontend test -- --include src/app/workspaces/risk/risk.spec.ts`
Expected: FAIL on all five new tests.

- [ ] **Step 3: Heat — remove the gauge, one utilisation line**

In `risk.ts`:
- Delete the `<sb-gauge … />` element, and its comment block that begins `<!-- The gauge IS heat utilisation`. Keep the `<div class="gauge-budget">` wrapper and the `@if (riskBudget(); as budget)` block inside it.
- Remove `Gauge` from the `imports` array and delete `import { Gauge } from '../../ui/gauge';`.
- In styles, delete `.gauge-budget sb-gauge { … }`, and change `.risk-budget { display: grid; gap: 2px; …` to `gap: var(--space-4);`.
- Replace `heatNote`'s body with:

```ts
  protected readonly heatNote = computed(() => {
    const utilisation = this.store.heatUtilisationPct();
    const cap = this.store.heatCapPct();
    if (utilisation === null) return 'Portfolio heat is not available.';
    // v89: one precision rule for the utilisation, so the note cannot round
    // 0.2% to "0%" beside a figure that says otherwise.
    const used = num(utilisation, utilisation >= 10 ? 0 : 1);
    if (this.store.heatOverCap()) {
      // Over the cap is a real state, not an impossible one: the cap gates
      // new entries, and open positions can drift past it as stops move.
      return `${used}% of the cap — over budget. New entries are blocked until heat falls.`;
    }
    return cap === null ? `${used}% of the risk budget in use.` : `${used}% of the ${num(cap, 1)}% cap in use.`;
  });
```

- [ ] **Step 4: Position risk precision and money at risk**

Add to the class, beside `fmt`/`fmtText`:

```ts
  /** v89: risk to a precision that shows it. Two decimals printed 0.00% for
   *  every position on a ~1M account, where each carries ~0.003%. */
  protected fmtRisk(value: number | null): string {
    if (value === null) return ABSENT;
    const abs = Math.abs(value);
    if (abs === 0) return num(0, 2);
    if (abs >= 0.1) return num(value, 2);
    if (abs >= 0.001) return num(value, 3);
    return '<0.001';
  }

  /** Money lost if the stop fills: |entry - stop| x shares, in account currency. */
  private riskAmount(row: RiskPosition): number | null {
    if (row.entry === null || row.stop_loss === null || row.shares === null) return null;
    return Math.abs(row.entry - row.stop_loss) * row.shares;
  }
```

Import `ABSENT` from `../../ui/format` (extend the existing import).

In the `#riskCell` template, change `{{ fmt(row.risk_pct) }}%` to `{{ fmtRisk(row.risk_pct) }}%`.

Change `visible` to `['ticker', 'strategy', 'shares', 'entry', 'stop_loss', 'risk_amount', 'risk_pct']`, and in `columns`, insert before the `risk_pct` column (and change that column's footer):

```ts
    { key: 'risk_amount', header: 'At risk', numeric: true, value: (row) => num(this.riskAmount(row)), footer: (rows) => num(rows.reduce((sum, row) => sum + (this.riskAmount(row) ?? 0), 0)) },
    { key: 'risk_pct', header: 'Risk %', numeric: true, cell: this.riskCell(), sortable: true, footer: (rows) => this.fmtRisk(rows.reduce((sum, row) => sum + (row.risk_pct ?? 0), 0)) },
```

- [ ] **Step 5: Sector heat and scan health**

Replace `<p class="none">No sector exposure.</p>` with:

```html
        @if (store.positions().length) {
          <!-- v89: sector_heat is empty when no sector map resolves for the
               open tickers -- "no exposure" claimed the opposite of the truth. -->
          <p class="none">
            Sector unknown for {{ store.positions().length }} open
            {{ store.positions().length === 1 ? 'position' : 'positions' }} — no sector
            map resolved for these tickers, so sector heat is not being measured.
          </p>
        } @else {
          <p class="none">No open positions, so no sector exposure.</p>
        }
```

Replace the scan figures block

```html
        <div class="scan-figures">
          <span class="scan-latest num">{{ fmt(store.scanLatestS(), 1) }}s</span>
          <span class="scan-label">last scan</span>
        </div>
```

with

```html
        <div class="scan-figures">
          @if (store.scanLatestS() !== null) {
            <span class="scan-latest num">{{ fmt(store.scanLatestS(), 1) }}s</span>
            <span class="scan-label">last scan</span>
          } @else {
            <span class="scan-label">No scan recorded</span>
          }
        </div>
```

- [ ] **Step 6: Spacing**

- `:host { … gap: var(--register-pad); }` → `gap: var(--section-gap);`. Replace the v54 comment above it with `v89: --section-gap between panels in both registers (spec §4.2).`
- In the `<sb-async>` that opens at ~line 191 (`emptyTitle="No open risk"`), insert `<div class="sb-stack">` directly after its opening tag's closing `>`, and `</div>` directly before its `</sb-async>` (~line 380).
- `.split { … gap: var(--register-pad); }` → `align-items: start; gap: var(--section-gap);`.

- [ ] **Step 7: Run to verify it passes**

Run: `npm --prefix frontend test -- --include src/app/workspaces/risk/risk.spec.ts` → PASS.
Run: `npm --prefix frontend test -- --include src/app/ui/spacing.spec.ts` → PASS.
If `'breaks the risk budget into cap, used and remaining'` still passes unchanged, good. It should, because the budget block was kept.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/risk/risk.spec.ts
git commit -m "fix(v89): risk shows real precision and money at risk, says when sectors are unknown, reads heat once, and stacks its panels"
```

---

### Task UA10: Trades and Trade detail — one count, rendered bold, spacing

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.ts` (`countText` ~line 794; styles)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (explanation ~line 336; `@case` bodies; styles)
- Modify: `frontend/src/app/ui/spacing.spec.ts` (remove the trade-detail entry)
- Test: `frontend/src/app/workspaces/trades/trades.spec.ts`, `frontend/src/app/workspaces/trades/trade-detail.spec.ts`

**Interfaces:**
- Consumes: UA3 `InlineMd` (`sb-inline-md`) and the one-count pager; UA1 `.sb-stack`, `--section-gap`.
- Produces: nothing new.

- [ ] **Step 1: Write the failing tests**

`frontend/src/app/workspaces/trades/trades.spec.ts`, in `describe('Trades — the count footer', …)`, replace the two tests `'reports the visible slice and the filtered total'` and `'reports the last page without overrunning the total'` with:

```ts
  it('leaves a non-empty range to the table pager, printed once (v89)', () => {
    const el = render({ total: 142, page: 1, perPage: 12 }).nativeElement as HTMLElement;
    // "1–12 of 142" printed three times before: pager top, pager bottom, footer.
    expect(el.querySelector('p.count')).toBeNull();
    expect(el.querySelectorAll('.pager .range')).toHaveLength(1);
    expect(el.querySelector('.pager .range')!.textContent).toContain('1–12 of 142');
  });
```

Keep the two zero-state tests (`'No trades match'`, `'No trades yet'`) unchanged.

`frontend/src/app/workspaces/trades/trade-detail.spec.ts`, after `'renders the explanation on the Plan tab'`:

```ts
  it('renders the explanation\'s bold without its asterisks (v89)', () => {
    const text = render('plan', { ...DETAIL, explanation: 'Stop at **425.76** (-3.3%)' });
    expect(text).toContain('Stop at 425.76 (-3.3%)');
    expect(text).not.toContain('**');
  });
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/trades.spec.ts` → FAIL (`p.count` is present).
Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/trade-detail.spec.ts` → FAIL (`**` present).

- [ ] **Step 3: Trades**

In `countText`, replace the last three lines

```ts
    const from = (current - 1) * perPage + 1;
    const to = Math.min(current * perPage, total);
    return `Showing ${from}–${to} of ${total}`;
```

with

```ts
    // v89: a non-empty range is the table pager's to print, once, above the
    // table. Only the two zero states -- which the pager cannot distinguish --
    // stay here.
    return null;
```

Remove the now-unused `current`/`perPage` destructuring from that function. Update its docstring's first line to `R6-05 / v89: the two zero states only.`

Styles: add as the first rule

```css
    /* v89: the page is one stack; --section-gap is the only space between its
       blocks (spec §4.2). */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; gap: var(--section-gap); }
```

and change `.count { … margin: var(--space-4) 0; }` to `.count { color: var(--text-secondary); font-size: var(--text-table); margin: 0; }`.

- [ ] **Step 4: Trade detail**

- Change `<p class="prose">{{ why }}</p>` to `<p class="prose"><sb-inline-md [text]="why" /></p>`, add `InlineMd` to the component `imports`, and add `import { InlineMd } from '../../ui/inline-md';`.
- Styles: add as the first rule `:host { display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; gap: var(--section-gap); }`.
- In `@case ('plan') { @if (store.trade(); as trade) {`, wrap everything inside that `@if` block in `<div class="sb-stack">` … `</div>`. Do the same inside `@case ('live') { @if (store.trade(); as trade) {`.
- `.panels { … gap: var(--space-14); margin-top: var(--space-14); }` → `gap: var(--section-gap); align-items: start;` with no margin.
- Delete `margin-top: var(--space-14);` from `.no-detail`, `.chart`, and `.notes, .strategy` (the host gap now separates them from the tab bar).

`frontend/src/app/ui/spacing.spec.ts`: delete `'app/workspaces/trades/trade-detail.ts|.panels'`.

- [ ] **Step 5: Run to verify they pass**

Run both specs from Step 2 → PASS.
Run: `npm --prefix frontend test -- --include src/app/ui/spacing.spec.ts` → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/trades frontend/src/app/ui/spacing.spec.ts
git commit -m "fix(v89): trades prints its range once, trade detail renders bold, both stack by the section gap"
```

---

### Task UA11: Calendar — the future is blank, today is marked, the weekday table lines up

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/calendar.helpers.ts` (add `localIsoDate`)
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts`
- Test: `frontend/src/app/workspaces/calendar/calendar.helpers.spec.ts`, `frontend/src/app/workspaces/calendar/calendar.spec.ts`

**Interfaces:**
- Consumes: UA1 `.sb-stack`, `--section-gap`.
- Produces: `export function localIsoDate(date: Date): string` (`YYYY-MM-DD` in local time).

- [ ] **Step 1: Write the failing tests**

`calendar.helpers.spec.ts`, append:

```ts
describe('localIsoDate', () => {
  it('formats the LOCAL calendar day, zero-padded like the grid keys', () => {
    expect(localIsoDate(new Date(2026, 8, 6, 23, 30))).toBe('2026-09-06');
  });
});
```

(Add `localIsoDate` to that file's import from `./calendar.helpers`.)

`calendar.spec.ts`: add `vi` to the vitest import, and add `afterEach` if the file lacks it. Then append inside the main `describe` that holds `'renders the weekend as inert…'`:

```ts
  it('leaves days after today blank and marks today (v89: the future read as flat days)', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(2026, 7, 5, 12, 0));   // Wed 2026-08-05, local
    try {
      const fixture = seed();
      await fixture.whenStable();
      fixture.detectChanges();

      const today = el(fixture).querySelector('.cell[data-date="2026-08-05"]')!;
      const tomorrow = el(fixture).querySelector('.cell[data-date="2026-08-06"]')!;
      expect(today.classList.contains('today')).toBe(true);
      expect(today.querySelector('button')).not.toBeNull();
      expect(tomorrow.querySelector('button')).toBeNull();
      expect(tomorrow.textContent!.trim()).toBe('6');
    } finally {
      vi.useRealTimers();
    }
  });

  it('right-aligns the numeric weekday headers over their columns and left-aligns the day (v89)', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/workspaces/calendar/calendar.ts'), 'utf8');
    // The header rule `.dow thead th { text-align: left }` out-specified
    // `.dow .num` under emulated encapsulation, and the body's row <th> took
    // the UA's centre -- measured on production: header left, values right.
    expect(source).toContain('.dow thead th.num { text-align: right; }');
    expect(source).toContain('.dow tbody th { text-align: left; font-weight: 600; }');
  });
```

Add `import { readFileSync } from 'node:fs';` and `import { join } from 'node:path';` at the top.

- [ ] **Step 2: Run to verify they fail**

Run: `npm --prefix frontend test -- --include src/app/workspaces/calendar/calendar.helpers.spec.ts` → FAIL (no export).
Run: `npm --prefix frontend test -- --include src/app/workspaces/calendar/calendar.spec.ts` → FAIL.

- [ ] **Step 3: Implement**

`calendar.helpers.ts`, after `iso()`:

```ts
/** Today's (or any instant's) calendar day in LOCAL time, keyed like the grid.
 *  Not toISOString(): that is UTC, and after 22:00 in Berlin it is tomorrow. */
export function localIsoDate(date: Date): string {
  return iso(date.getFullYear(), date.getMonth() + 1, date.getDate());
}
```

`calendar.ts`:
- Import `localIsoDate`. Add a class field: `protected readonly today = localIsoDate(new Date());`
- On the cell `<div class="cell" …>`, add `[class.today]="cell.date === today"`.
- Change `@if (cell.inMonth && !cell.weekend) {` to `@if (cell.inMonth && !cell.weekend && cell.date <= today) {`. Above it, replace the `2026-09-14` comment's first line with: `v89: a day that has not happened yet renders date-only -- "0" there read as a real flat day.`
- Styles: after `.cell.selected { … }` add `.cell.today { box-shadow: inset 0 0 0 1px var(--border-strong); }`. After `.dow .num { … }` add:

```css
    .dow thead th.num { text-align: right; }
    .dow tbody th { text-align: left; font-weight: 600; }
```

- Spacing: `:host { … gap: var(--register-pad); }` → `gap: var(--section-gap);`. In the `<sb-async>` at ~line 82, insert `<div class="sb-stack">` right after its opening tag's `>`, and `</div>` right before its `</sb-async>` (~line 164). Set the `.totals` rule's `gap` to `var(--space-10)`, with no margin.

- [ ] **Step 4: Run to verify they pass**

Run both specs from Step 2 → PASS. Then `npm --prefix frontend test -- --include src/app/ui/spacing.spec.ts` → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/calendar
git commit -m "fix(v89): calendar leaves future days blank, marks today, aligns the weekday table, stacks by the section gap"
```

---

### Task UA12: Watchlist, Ticker detail, System and Versions — spacing

**Files:**
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts:434`
- Modify: `frontend/src/app/workspaces/watchlist/ticker-detail.ts:136`
- Modify: `frontend/src/app/workspaces/system/system.ts:87`
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts:399` (and its sb-async content, ~51–309)
- Modify: `frontend/src/app/workspaces/system/scan-tab.ts:156`
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts:528` (off-scale padding)
- Modify: `frontend/src/app/workspaces/versions/versions.ts:221`
- Create: `frontend/src/app/workspaces/workspace-gaps.spec.ts`

**Interfaces:**
- Consumes: UA1 `--section-gap`, `.sb-stack`.
- Produces: `workspace-gaps.spec.ts`, which asserts every workspace host grid uses `--section-gap`. UA13 must keep it green.

- [ ] **Step 1: Write the failing guard**

Create `frontend/src/app/workspaces/workspace-gaps.spec.ts`:

```ts
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

/** v89: every workspace (and tab) host that lays its children out as a grid
 *  spaces them by --section-gap -- not --register-pad, whose 10px instrument
 *  rung made Risk measure half of Dashboard, and not a literal --space-20. */
const ROOT = join(process.cwd(), 'src/app/workspaces');
const EXEMPT = new Set(['gallery/gallery.ts']); // the component gallery is a demo page, not a workspace

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : n.endsWith('.ts') && !n.endsWith('.spec.ts') ? [p] : [];
  });
}

describe('workspace host grids', () => {
  it('use --section-gap', () => {
    const offenders: string[] = [];
    for (const path of walk(ROOT)) {
      const rel = relative(ROOT, path).replace(/\\/g, '/');
      if (EXEMPT.has(rel)) continue;
      for (const m of readFileSync(path, 'utf8').matchAll(/:host\s*\{([^}]*display:\s*grid[^}]*)\}/g)) {
        const gap = /(?:^|;|\s)gap:\s*([^;]+)/.exec(m[1]);
        if (gap && gap[1].trim() !== 'var(--section-gap)') offenders.push(`${rel}: gap ${gap[1].trim()}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm --prefix frontend test -- --include src/app/workspaces/workspace-gaps.spec.ts`
Expected: FAIL, listing `watchlist/watchlist.ts`, `watchlist/ticker-detail.ts`, `system/system.ts`, `system/settings-tab.ts`, `system/scan-tab.ts` and `versions/versions.ts`. Calendar, Dashboard and Risk are also listed if UA8, UA9 or UA11 have not merged into this branch yet. Those are theirs to fix.

- [ ] **Step 3: Convert**

- In each of the six files listed for this task, change the `:host { display: grid; … gap: … }` gap to `var(--section-gap)`. Replace any v54 `--register-pad` comment directly above it with `v89: --section-gap between panels (spec §4.2).`
- `settings-tab.ts`: inside the `<sb-async>` at ~line 51, wrap its content in `<div class="sb-stack">` … `</div>` (open right after the opening tag's `>`, close right before `</sb-async>` at ~309). Delete `margin-bottom: var(--space-10);` from `.find`.
- `settings-tab.ts:528`: `padding: 2px var(--space-8);` → `padding: var(--space-4) var(--space-8);`.

- [ ] **Step 4: Run to verify it passes**

Run: `npm --prefix frontend test -- --include src/app/workspaces/workspace-gaps.spec.ts` → PASS for this task's six files. (Any remaining offender must belong to UA8, UA9, UA11 or UA13 and disappears when that task lands.)
Also run:
- `npm --prefix frontend test -- --include src/app/workspaces/system/settings-tab.spec.ts`
- `npm --prefix frontend test -- --include src/app/workspaces/watchlist/watchlist.spec.ts`
- `npm --prefix frontend test -- --include src/app/workspaces/versions/versions.spec.ts`

Expected: PASS (skip any that does not exist).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/workspace-gaps.spec.ts frontend/src/app/workspaces/watchlist frontend/src/app/workspaces/system frontend/src/app/workspaces/versions
git commit -m "fix(v89): watchlist, system and versions space panels by the section gap, with a guard for every host grid"
```
