# v152 part 2b: SPA `Followed vs paper` option

**Spec:** [`docs/superpowers/specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md`](../specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md) § D2
**Index:** [`2026-10-10-v152-discord-notify-taken-cooldown_0-index.md`](2026-10-10-v152-discord-notify-taken-cooldown_0-index.md): Global Constraints, Decisions fixed by this index, the task ledger and `## Parallelisation` live there and bind every task below.

Part 2 is split in two files only to stay under 1500 lines: [`_2-panel-following-taken`](2026-10-10-v152-discord-notify-taken-cooldown_2-panel-following-taken.md) holds V152-6 .. V152-9, this file V152-10. Same part, same ledger rows, same contracts. None is v151-gated.

# Phase 3 (continued): The `taken` dimension

### Task V152-10: SPA `Followed vs paper` option, caption, `exp_r`-first order

**Model:** sonnet — Angular template and computed-signal edits with Vitest specs; verbatim copy from the financial-advisor panel.

**Files:**
- Modify: `frontend/src/app/stores/analytics.store.ts` (`BREAKDOWN_DIMENSIONS` `:275-286`)
- Modify: `frontend/src/app/stores/analytics.store.spec.ts` (exact list `:739-743`)
- Modify: `frontend/src/app/workspaces/analytics/tabs/attribution.ts` (template under `.breakdown-controls`; styles; `dimensionVisible`)
- Modify: `frontend/src/app/workspaces/analytics/tabs/attribution.spec.ts`

**Produces (ledger):** `{ value: 'taken', label: 'Followed vs paper' }` in `BREAKDOWN_DIMENSIONS` (after `ledger`); `export const TAKEN_CAPTION` in `attribution.ts`. Verbatim copy (Global Constraints): label `Followed vs paper`; caption `Paper results, R units, pre-tax. Followed records the plan as followed, not your fill.` Shown only while the `taken` breakdown is selected. For that breakdown `dimensionVisible` puts `exp_r` before `win_rate` (expectancy leads, win rate secondary) and keeps `n`. The data table renders in `visible` order (`ui/data-table/data-table.ts` `renderedColumns`, which maps `visible()` keys; the class comment above it calling the order "ignored" predates SR14), so reordering the list reorders the columns. Every other breakdown keeps today's order.

- [ ] **Step 1: Write the failing specs**

In `analytics.store.spec.ts`, inside `it('carries the unit and offers every server-supported scoped breakdown', ...)`, add `'taken'` after `'ledger'` in the CURRENT `toEqual([...])` list, keeping every entry already there (v146 adds `'confluence'`, `'rs_quintile'` if merged) — do not replace the list from this text — and add the label expectation. The no-v146 result:

```ts
      expect(BREAKDOWN_DIMENSIONS.map((dimension) => dimension.value)).toEqual([
        'strategy', 'horizon', 'direction', 'dow', 'month', 'badge',
        'confidence', 'source', 'ledger', 'taken', 'ticker',
      ]);
      expect(BREAKDOWN_DIMENSIONS.find((d) => d.value === 'taken')?.label).toBe('Followed vs paper');
```

In `attribution.spec.ts`, change the import to `import { AttributionTab, TAKEN_CAPTION } from './attribution';` and add inside `describe('AttributionTab', ...)`, after the badge-column tests:

```ts
  /* -- v152 D2: the followed-vs-paper breakdown ------------------------- */

  it('captions the followed-vs-paper breakdown as paper results, not fills', () => {
    const { el } = render({ breakdown: signal('taken'), breakdownLabel: signal('Followed vs paper') });
    expect(TAKEN_CAPTION).toBe(
      'Paper results, R units, pre-tax. Followed records the plan as followed, not your fill.');
    expect(el.textContent).toContain(TAKEN_CAPTION);
  });

  it('shows no caption for any other breakdown', () => {
    const { el } = render();
    expect(el.textContent).not.toContain(TAKEN_CAPTION);
  });

  it('leads with expectancy for the followed-vs-paper breakdown and keeps N', () => {
    const { fixture } = render({ breakdown: signal('taken') });
    const visible: string[] = fixture.componentInstance['dimensionVisible']();
    expect(visible.slice(0, 4)).toEqual(['key', 'n', 'exp_r', 'win_rate']);
  });

  it('keeps the default column order for every other breakdown', () => {
    const { fixture } = render();
    const visible: string[] = fixture.componentInstance['dimensionVisible']();
    expect(visible.slice(0, 4)).toEqual(['key', 'n', 'win_rate', 'exp_r']);
  });
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `npm --prefix frontend test -- --include src/app/stores/analytics.store.spec.ts --watch=false`
Expected: FAIL (list lacks `taken`).
Run: `npm --prefix frontend test -- --include src/app/workspaces/analytics/tabs/attribution.spec.ts --watch=false`
Expected: FAIL (`TAKEN_CAPTION` is not exported).

- [ ] **Step 3: Add the option**

In `analytics.store.ts`, insert into the CURRENT `BREAKDOWN_DIMENSIONS` block directly after `{ value: 'ledger', label: 'Ledger' },`, keeping every entry other plans added (v146's `confluence`, `rs_quintile` if present):

```ts
  // v152 D2: trades whose plan had a Following follower vs the rest. Intent,
  // never a fill -- the attribution tab captions it.
  { value: 'taken', label: 'Followed vs paper' },
```

- [ ] **Step 4: Caption and column order in `attribution.ts`**

Above `@Component(`, add:

```ts
/** v152 D2 (financial-advisor panel, verbatim): the followed/paper split is
 *  the paper book, in R, before tax; "followed" is what a user said, never
 *  a fill. */
export const TAKEN_CAPTION =
  'Paper results, R units, pre-tax. Followed records the plan as followed, not your fill.';
```

In the template, directly after the closing `</div>` of `.breakdown-controls`, add:

```html
      @if (store.breakdown() === 'taken') {
        <p class="caption">{{ takenCaption }}</p>
      }
```

Append to `styles` (both tokens exist: `styles/tokens.css:86`, and `--text-micro` is used across `ui/`): `.caption { margin: 0 0 var(--space-10); color: var(--text-muted); font-size: var(--text-micro); }`

In the class, after `breakdownOptions`, add `protected readonly takenCaption = TAKEN_CAPTION;` and replace `dimensionVisible` with:

```ts
  /** `badge`/`soak` are present only for some dimensions (`dim=strategy` in
   *  particular) -- shown only when a row on screen actually carries one.
   *  v152: the followed-vs-paper split leads with expectancy, win rate
   *  second; N stays shown per cell. */
  protected readonly dimensionVisible = computed<string[]>(() => {
    const rows = this.dimensionRows();
    const rates = this.store.breakdown() === 'taken' ? ['exp_r', 'win_rate'] : ['win_rate', 'exp_r'];
    const visible = ['key', 'n', ...rates, 'total_r', 'total_pnl', 'avg_win_r', 'avg_loss_r'];
    if (rows.some((r) => r.badge !== undefined)) visible.push('badge');
    if (rows.some((r) => r.soak !== undefined)) visible.push('soak');
    return visible;
  });
```

- [ ] **Step 5: Run the specs**

Run: `npm --prefix frontend test -- --include src/app/stores/analytics.store.spec.ts --watch=false`
Expected: PASS.
Run: `npm --prefix frontend test -- --include src/app/workspaces/analytics/tabs/attribution.spec.ts --watch=false`
Expected: PASS (the breakpoint test still finds only `639`).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts frontend/src/app/workspaces/analytics/tabs/attribution.ts frontend/src/app/workspaces/analytics/tabs/attribution.spec.ts
git commit -m "feat(v152): Followed vs paper breakdown with its caption, expectancy first (V152-10)"
```
