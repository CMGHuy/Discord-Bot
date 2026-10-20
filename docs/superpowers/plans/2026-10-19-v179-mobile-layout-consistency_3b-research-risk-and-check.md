# v179 — Mobile layout consistency, Part 3b: Research, Risk, the no-hand-rolled-cards guard and the Part 3 browser check

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-19-v179-mobile-layout-consistency-design.md](../specs/2026-10-19-v179-mobile-layout-consistency-design.md) — §3.1 (badge floor, money floor), §4 anti-goals, §6a.4, §6b.2 and §7.5.
**Index:** [2026-10-19-v179-mobile-layout-consistency_0-index.md](2026-10-19-v179-mobile-layout-consistency_0-index.md) — Global Constraints, Contracts, Parallelisation and the ledger bind this task.

The tail of Part 3 ([`_3-tables.md`](2026-10-19-v179-mobile-layout-consistency_3-tables.md)): Part 3 holds V179-9..V179-12 and would pass 1500 lines with this task too. Same worktree, same conventions — read that file's preamble ("Three things every task here relies on") before starting. V179-9..V179-12 are done before this task starts.

---

### Task V179-13: Research registry (badge floor), ledger `emit`, Risk exposure (money floor); no-hand-rolled-cards guard; Part 3 browser check

**Model:** sonnet — three more declarations in the established pattern, one regex guard, then a measured three-width check of everything Part 3 changed.

**Files:**
- Modify: `frontend/src/app/workspaces/research/research.ts`
- Modify: `frontend/src/app/workspaces/research/research.spec.ts`
- Modify: `frontend/src/app/workspaces/risk/risk.ts`
- Modify: `frontend/src/app/workspaces/risk/risk.spec.ts`
- Modify: `frontend/src/app/workspaces/workspace-consistency.spec.ts`

**Interfaces:**
- Consumes: `ColumnDef.compact`, `DetailLink` (V179-9); `phoneTap`, `detailLink`, `compactKeys`, `drawerKeys`, `openRowDrawer`, `phoneViewport` (V179-10); the declarations of V179-11 and V179-12 (the guard checks them).
- Produces: nothing later tasks import.

**Field choice.**
- **Research registry** (generic drawer, spec §6b.2) — line 1: strategy and the badge tier (its cell already carries the run date and window); line 2: OOS ExpR, OOS N and **evidence freshness**. That is the §3.1 badge floor: a WEAK strategy never reads like a validated one, and stale evidence shows on the row. Live N goes to the drawer. No detail page, so no link.
- **Pre-registration ledger** — `phoneTap="emit"`: its rows already open Research's own store drawer (`store.select`, research.ts ~125, ~136-166), so the table must not open a second one (§6a.4). Line 1: id and verdict; line 2: date, N, ExpR. Hypothesis, instrument, p and q are in the store drawer, which lists every ledger field (the id is its heading).
- **Risk "Exposure by position"** — line 1: ticker and Risk %; line 2: stop and entry. That is the money floor for a table that carries risk, not P&L: the risk amount and the stop never sit behind a tap. Strategy and shares go to the drawer; the shares and Risk % footers become the compact totals line. **One deviation from the index's consumer list, on purpose:** Risk gets `detailLink` → `/trades/:trade_id` ("Open full trade →"). The ticker cell is an `sb-row-link` to that page today; on a phone the cell sits inside the row button with pointer events off, so without the link a phone user would lose a destination they have today (§4 anti-goal).

- [ ] **Step 1: Write the failing tests**

(a) `frontend/src/app/workspaces/research/research.spec.ts` — add `Provider` to the `@angular/core` import (`import { Provider, provideZonelessChangeDetection } from '@angular/core';`) and add `import { compactKeys, drawerKeys, openRowDrawer, phoneViewport } from '../../ui/data-table/testing/reachability';`. Give `create()` a third parameter that is spread into its providers:

```ts
function create(
  ledger: ResearchLedger = LEDGER,
  registry: StrategyRow[] = REGISTRY,
  extra: Provider[] = [],
): { fixture: ComponentFixture<Research>; store: InstanceType<typeof ResearchStore>; router: Router } {
```

with `ResearchStore,` in its providers list becoming `ResearchStore, ...extra,`. Then append:

```ts
describe('Research on a phone (v179 §3.1, §6b.2)', () => {
  it('keeps the badge tier on line 1 and evidence freshness on the registry row (badge floor)', () => {
    const { fixture } = create(LEDGER, REGISTRY, [phoneViewport()]);
    const rows = tables(fixture)[0].querySelectorAll('li.compact-row');
    const weakTier = rows[1].querySelector('.line1 > [data-col="status"]')!.textContent!;
    expect(weakTier).toContain('WEAK');
    expect(weakTier).toContain('2026-07-15');
    expect(rows[0].querySelector('.line2 > [data-col="evidence_decay"]')!.textContent).toContain('fresh');
  });

  it('reaches every registry column through its own row drawer, with no detail link', () => {
    const { fixture } = create(LEDGER, REGISTRY, [phoneViewport()]);
    const registry = tables(fixture)[0];
    openRowDrawer(registry);
    fixture.detectChanges();
    expect([...compactKeys(registry), ...drawerKeys(registry)].sort())
      .toEqual(['evidence_decay', 'expectancy_r', 'live_n', 'n', 'status', 'strategy']);
    expect(registry.querySelector('a.drawer-detail-link')).toBeNull();
  });

  it('sends a ledger tap to its own store drawer only -- one tap, one drawer (§6a.4)', () => {
    const { fixture, store } = create(LEDGER, REGISTRY, [phoneViewport()]);
    const ledger = tables(fixture)[1];
    openRowDrawer(ledger);
    fixture.detectChanges();
    const selected = store.selected()!;
    expect(selected).not.toBeNull();
    expect(ledger.querySelector('sb-drawer.row-drawer')).toBeNull();

    // Reachability (§7.5): the compact row, plus the store drawer's labels,
    // plus its heading (the id).
    const page = fixture.nativeElement as HTMLElement;
    expect(page.querySelector('sb-drawer:not(.row-drawer) h2')!.textContent!.trim()).toBe(selected.id);
    const labels = [...page.querySelectorAll('dl.detail dt')].map((dt) => dt.textContent!.trim());
    const HEADERS: Record<string, string> = {
      date: 'Date', hypothesis: 'Hypothesis', instrument: 'Instrument', n: 'N', exp_r: 'ExpR', p: 'p', q: 'q', verdict: 'Verdict',
    };
    const reached = new Set([...compactKeys(ledger), 'id']);
    for (const [key, label] of Object.entries(HEADERS)) if (labels.includes(label)) reached.add(key);
    expect([...reached].sort()).toEqual(['date', 'exp_r', 'hypothesis', 'id', 'instrument', 'n', 'p', 'q', 'verdict']);
  });
});
```

(b) `frontend/src/app/workspaces/risk/risk.spec.ts` — add `Provider` to the `@angular/core` import and add `import { installDialogPolyfill } from '../../testing/dialog-polyfill';` and `import { compactKeys, drawerKeys, openRowDrawer, phoneViewport } from '../../ui/data-table/testing/reachability';`. Thread an `extra` list through the two helpers: `function seed(extra: Provider[] = [])` with `RiskStore,` becoming `RiskStore, ...extra,` in its providers, and `async function render(overrides: Partial<RiskData> = {}, extra: Provider[] = [])` calling `seed(extra)`. Then append:

```ts
describe('Risk exposure on a phone (v179 §3.1)', () => {
  async function phoneTable(): Promise<{ fixture: ComponentFixture<Risk>; table: HTMLElement }> {
    installDialogPolyfill();
    const fixture = await render({}, [phoneViewport()]);
    return { fixture, table: (fixture.nativeElement as HTMLElement).querySelector('sb-data-table') as HTMLElement };
  }

  it('keeps the risk and the stop on the compact row (money floor)', async () => {
    const { table } = await phoneTable();
    expect(compactKeys(table)).toEqual(['ticker', 'risk_pct', 'stop_loss', 'entry']);
  });

  it('keeps the shares and Risk % totals as a compact totals line', async () => {
    const { table } = await phoneTable();
    expect(table.querySelector('.compact-footer [data-col="shares"]')!.textContent).toContain('10');
    expect(table.querySelector('.compact-footer [data-col="risk_pct"]')!.textContent).toContain('3.00');
  });

  it('reaches every column and keeps the link to the trade the ticker cell had', async () => {
    const { fixture, table } = await phoneTable();
    openRowDrawer(table);
    fixture.detectChanges();
    expect([...compactKeys(table), ...drawerKeys(table)].sort())
      .toEqual(['entry', 'risk_pct', 'shares', 'stop_loss', 'strategy', 'ticker']);
    expect(table.querySelector('a.drawer-detail-link')!.getAttribute('href')).toBe('/trades/t1');
  });
});
```

(c) Append to `frontend/src/app/workspaces/workspace-consistency.spec.ts`:

```ts
describe('compact rows are declared, never hand-built (v179 §3.1, §4)', () => {
  it('no workspace builds or restyles the compact row or row drawer itself', () => {
    // sb-data-table owns this DOM. A workspace that writes it (or reaches
    // into it with ::ng-deep) is hand-rolling cards -- the §4 anti-goal.
    const offenders = SOURCES
      .filter((s) => /compact-(?:list|row|hit|footer)|drawer-fields|\.line[12]\b/.test(s.source))
      .map((s) => s.name);
    expect(offenders).toEqual([]);
  });

  it.each([
    'trades/trades.columns.ts',
    'watchlist/watchlist.ts',
    'watchlist/ticker-detail.ts',
    'research/research.ts',
    'risk/risk.ts',
  ])('%s declares its compact row', (name) => {
    expect(SOURCES.find((s) => s.name === name)?.source ?? '').toContain('compact: { line: 1, order: 1 }');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/research/research.spec.ts --include src/app/workspaces/risk/risk.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts`
Expected: FAIL — Research and Risk still render `<table>` on the phone stub (`li.compact-row` absent, `compactKeys` `[]`); the guard fails only on `research/research.ts` and `risk/risk.ts` (V179-11 and V179-12 already declared theirs).

- [ ] **Step 3: Declare the Research rows**

In `frontend/src/app/workspaces/research/research.ts`:

- registry `<sb-data-table …>` (the one with `clientPaging="research-registry"`): add `phoneTap="drawer"` after `[fillPage]="false"`;
- ledger `<sb-data-table …>`: add `phoneTap="emit"` before `(rowActivate)="store.select($event.id)"`;
- replace `registryColumns` and `ledgerColumns` with:

```ts
  /** v179 §3.1 badge floor: on a phone the tier (with its run date and
   *  window) stays on line 1 and evidence freshness on line 2, so a WEAK or
   *  decayed strategy never reads like a validated one. */
  protected readonly registryColumns = computed<ColumnDef<StrategyRow>[]>(() => [
    { key: 'strategy', header: 'Strategy', value: (row) => row.strategy, compact: { line: 1, order: 1 } },
    { key: 'status', header: 'Badge tier', cell: this.tierCell(), compact: { line: 1, order: 2 } },
    { key: 'n', header: 'OOS N', numeric: true, value: (row) => row.n, compact: { line: 2, order: 2 } },
    { key: 'expectancy_r', header: 'OOS ExpR', numeric: true, value: (row) => fixed(row.expectancy_r, 2), compact: { line: 2, order: 1 } },
    { key: 'live_n', header: 'Live N', numeric: true, value: (row) => row.live_n },
    { key: 'evidence_decay', header: 'Evidence', value: (row) => row.evidence_decay, compact: { line: 2, order: 3 } },
  ]);

  protected readonly ledgerVisible = ['date', 'id', 'hypothesis', 'instrument', 'n', 'exp_r', 'p', 'q', 'verdict'];
  /** v179 §6a.4: on a phone a ledger row emits only (`phoneTap="emit"`) and
   *  opens the store drawer below, which lists every field. */
  protected readonly ledgerColumns = computed<ColumnDef<LedgerRow>[]>(() => [
    { key: 'date', header: 'Date', sortable: true, value: (row) => row.date, compact: { line: 2, order: 1 } },
    { key: 'id', header: 'Id', sortable: true, value: (row) => row.id, compact: { line: 1, order: 1 } },
    { key: 'hypothesis', header: 'Hypothesis', cell: this.hypothesisCell(), inlineFrom: 'md' },
    { key: 'instrument', header: 'Instrument', sortable: true, value: (row) => row.instrument, inlineFrom: 'md' },
    { key: 'n', header: 'N', numeric: true, sortable: true, value: (row) => row.n, compact: { line: 2, order: 2 } },
    { key: 'exp_r', header: 'ExpR', numeric: true, sortable: true, value: (row) => fixed(row.exp_r, 3), compact: { line: 2, order: 3 } },
    { key: 'p', header: 'p', numeric: true, sortable: true, value: (row) => fixed(row.p, 4), inlineFrom: 'md' },
    { key: 'q', header: 'q', numeric: true, sortable: true, value: (row) => fixed(row.q, 4), inlineFrom: 'md' },
    { key: 'verdict', header: 'Verdict', sortable: true, cell: this.verdictCell(), compact: { line: 1, order: 2 } },
  ]);
```

(the `ledgerVisible` line is unchanged; it is shown for position).

- [ ] **Step 4: Declare the Risk row**

In `frontend/src/app/workspaces/risk/risk.ts`:

- change line 19 to `import { ColumnDef, DetailLink, RowContext, SortSpec } from '../../ui/data-table/data-table.types';`;
- in the "Exposure by position" `<sb-data-table …>`, add after `[emptyState]="emptyState"`:

```html
        phoneTap="drawer"
        [detailLink]="tradeLink"
```

- replace the `columns` computed (keep its doc comment) with:

```ts
  protected readonly columns = computed<ColumnDef<RiskPosition>[]>(() => [
    { key: 'ticker', header: 'Ticker', value: (row) => row.ticker, cell: this.tickerCell(), sortable: true, compact: { line: 1, order: 1 } },
    { key: 'strategy', header: 'Strategy', value: (row) => text(row.strategy), sortable: true },
    { key: 'shares', header: 'Shares', value: (row) => num(row.shares, 0), numeric: true, sortable: true, footer: (rows) => num(rows.reduce((sum, row) => sum + (row.shares ?? 0), 0), 0) },
    { key: 'entry', header: 'Entry', value: (row) => num(row.entry), numeric: true, sortable: true, compact: { line: 2, order: 2 } },
    { key: 'stop_loss', header: 'Stop', value: (row) => num(row.stop_loss), numeric: true, sortable: true, compact: { line: 2, order: 1 } },
    { key: 'risk_pct', header: 'Risk %', numeric: true, cell: this.riskCell(), sortable: true, footer: (rows) => num(rows.reduce((sum, row) => sum + (row.risk_pct ?? 0), 0)), compact: { line: 1, order: 2 } },
  ]);

  /** v179: the money floor keeps Risk % and the stop on the phone row. The
   *  ticker cell links to the trade; inside the row button it cannot be
   *  tapped, so the drawer carries the same destination. `ticker`'s `value`
   *  is the drawer heading only -- its cell renders. */
  protected readonly tradeLink = (row: RiskPosition): DetailLink => ({
    commands: ['/trades', row.trade_id],
    label: 'Open full trade →',
  });
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/research/research.spec.ts --include src/app/workspaces/risk/risk.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts`
Expected: PASS, `0 failed`.

- [ ] **Step 6: Commit the code**

```bash
git add frontend/src/app/workspaces/research/research.ts frontend/src/app/workspaces/research/research.spec.ts
git commit -m "feat(research): registry compact rows keep tier and freshness; ledger taps open only its own drawer (v179 §3.1, §6a.4)"
git add frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/risk/risk.spec.ts frontend/src/app/workspaces/workspace-consistency.spec.ts
git commit -m "feat(risk): exposure compact rows keep risk and stop on the row; guard against hand-rolled compact rows (v179 §3.1, §4)"
```

- [ ] **Step 7: Part 3 browser check at 1440, 768 and 390**

Run `/replicate-prod-db` if the local replica is older than this session, then from the worktree root:

```bash
cd frontend && npm run build && cd ..
python admin_ui.py            # http://localhost:1234 -- leave running (run_in_background)
node frontend/scripts/browse.mjs login --base http://localhost:1234
OUT="$(mktemp -d)"
SYMBOL=AAPL                   # a symbol on the local watchlist that has trades -- see below
node frontend/scripts/browse.mjs shots --base http://localhost:1234 --widths 1440,768,390 --out "$OUT" \
  --path /trades --path /dashboard --path /watchlist --path "/watchlist/$SYMBOL" --path /research --path /risk
node frontend/scripts/browse.mjs shots --base http://localhost:1234 --widths 390 --out "$OUT/drawer" \
  --click "li.compact-row > button.compact-hit" \
  --path /trades --path /dashboard --path /watchlist --path "/watchlist/$SYMBOL" --path /research --path /risk
grep -H "page-scroll-x" "$OUT"/*.txt "$OUT"/drawer/*.txt | grep -v "page-scroll-x: 0"
```

`browse.mjs` signs in with `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded from `.env` inside the script, never printed. Pick `$SYMBOL` from the Watchlist screenshot's first row (a symbol that has trades, so the ticker page's trade list is not empty). Expected: the `grep` prints nothing — no page overflow at any width, drawer open or not. Then check the PNGs:

| What | Where | Pass when |
|---|---|---|
| Compact rows (V179-9) | all six paths @390 | two lines per row, no table header, no ▸, nothing past the right edge; Sort select above, pager below; Risk shows its totals line |
| Floors (V179-11, V179-13) | Trades, Dashboard positions, Risk, Research registry @390 | P&L % **with its amount** and the plan (with the stop in red) on Trades/Dashboard rows; Risk % and Stop on Risk rows; badge chip with its run date/window on line 1 and Evidence on line 2 in the registry |
| Row drawer (V179-10) | `drawer/*@390.png` | a bottom sheet titled with the row's ticker/symbol/strategy; every other column as label/value pairs on one baseline per pair; row actions present on Trades/Dashboard; "Open full trade →" (Trades, ticker page, Risk) or "Open ticker →" (Watchlist); none in the registry |
| One drawer per tap (V179-13) | `/research` drawer shot | the first compact list on the page is the registry, so the shot shows the generic drawer; tap a ledger row by hand (`browse.mjs` `--click` takes the first match only) and confirm only the ledger's own drawer opens |
| Desktop and tablet unchanged | all six paths @1440 and @768 | the same tables as before Part 3; header sort buttons unchanged in look; clicking a Trades or Watchlist row still opens the full page |

Each failure is fixed in the file it traces to (the Part 3 task that owns it), with a test in that file's spec in the style of the owning task, run with that spec's narrow `ng test --include`, and committed as `fix(ui): <what> -- v179 Part 3 browser check`. Re-shoot the affected paths until the table passes. Stop `admin_ui.py` when done.

---
