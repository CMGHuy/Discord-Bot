# v194 part 4 — metric basis (B8) and leg rows (B3 data and helper)

**Spec:** [2026-10-25-v194-ui-tooltips-and-data-truth.md](../specs/2026-10-25-v194-ui-tooltips-and-data-truth.md) — sections B8 and B3.
**Index:** [2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md](2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md) — Global Constraints, `### Standard task close`, Parallelisation and the ledger live there. Tasks V194-10, V194-11 and V194-12: V194-11 consumes V194-10's `max_drawdown_amount`; V194-12 is independent of both (it shares only `api/models.ts` with V194-11, so run them in order).

# Phase 4 — Risk and Analytics name their basis; leg rows say which part they are

### Task V194-10: B8 backend — `metrics.max_drawdown_amount` on `/risk`

**Model:** sonnet — one helper and one response key over an existing seam, tests spelled out.

**Files:**
- Modify: `swingbot/admin/api_v1/risk.py` (imports at `:34-38`; `_metric` `:217`; `_risk_metrics_and_correlation` `:230-359`, the `max_drawdown_r` line `:281`, `null_metrics` `:285`, the `metrics` dict `:344`)
- Test: `tests/admin/test_api_v1_risk.py` (`test_risk_shape` metrics block `:146-165`; new tests appended at the end of the metrics tests)

**Interfaces:**
- Consumes: `to_account_currency(rows: list[dict], *, account: str | None = None) -> list[dict]` and `missing_count(rows) -> int` from `swingbot/admin/api_v1/money.py` (V194-6b; a row comes back with `realized_pnl_amount` in the account currency, or `None` plus `fx_missing: True`); `rm.max_drawdown_r(values: list[float]) -> float | None` (`swingbot/core/analytics/risk_metrics.py:174`, the peak-to-trough fall of a cumulative curve as a positive number — unit-free, so it serves money as well); the `closed` list already built in `_risk_metrics_and_correlation` (`status in win/loss/closed`, `ledger="main"`).
- Produces: `/api/v1/risk` `metrics.max_drawdown_amount: {value: float | None, n: int, fx_missing_count: int}` (positive magnitude, account currency; `n` = trades counted, i.e. closed trades that have a rate); `_pnl_amounts(converted: list[dict]) -> list[float]` and `_money_drawdown(closed: list) -> dict` (both in `risk.py`). V194-11 reads the key.

**Why this is well defined for all closed trades (spec B8's "record why and show percent of account" escape is not needed):** the money curve is the cumulative realised P&L in the account currency over the same all-closed population `max_drawdown_r` uses; each trade is converted at its own exit-date rate by V194-6b, so no single R-to-currency factor is involved. Trades with a missing rate are excluded from the curve and counted in `fx_missing_count`, never valued at 1.0.

- [ ] **Step 1: Write the failing tests.** In `tests/admin/test_api_v1_risk.py`, first extend `test_risk_shape`'s metrics block: in the `assert_shape(body["metrics"], {...})` dict add `"max_drawdown_amount": dict,` after `**{key: dict for key in metric_keys},` and, after the existing `for key in metric_keys:` loop, add

```python
    assert_shape(body["metrics"]["max_drawdown_amount"], {
        "value": NULLABLE_NUMBER, "n": int, "fx_missing_count": int,
    }, where="metrics.max_drawdown_amount")
```

Then append a helper and tests after the existing metric tests:

```python
def _paid_trade(trade_id, amount, closed_at, ticker="AAPL"):
    """A closed trade carrying the stored money figure the drawdown reads."""
    return {**_closed_trade(trade_id, ticker), "realized_pnl_amount": amount,
            "closed_at": closed_at}


def _seed_paid(amounts, tickers=None):
    trades = [
        _paid_trade(f"p{i:015d}", amount, f"2026-02-{i + 1:02d}T15:00:00+00:00",
                    (tickers or {}).get(i, "AAPL"))
        for i, amount in enumerate(amounts)
    ]
    seed_store("trades", trades)


def test_money_drawdown_is_the_peak_to_trough_fall_of_cumulative_pnl(logged_in):
    # cumulative: 100, 50, -30, 0 -> peak 100, trough -30 -> 130
    _seed_paid([100.0, -50.0, -80.0, 30.0])
    dd = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    assert dd == {"value": 130.0, "n": 4, "fx_missing_count": 0}


def test_money_drawdown_orders_by_close_date_not_storage_order(logged_in):
    # The same four trades stored newest first: the curve still runs oldest first.
    trades = [
        _paid_trade(f"p{i:015d}", amount, f"2026-02-{day:02d}T15:00:00+00:00")
        for i, (amount, day) in enumerate([(30.0, 4), (-80.0, 3), (-50.0, 2), (100.0, 1)])
    ]
    seed_store("trades", trades)
    dd = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    assert dd["value"] == 130.0


def test_money_drawdown_is_zero_for_a_book_that_only_wins(logged_in):
    _seed_paid([10.0, 20.0])
    dd = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    assert dd == {"value": 0.0, "n": 2, "fx_missing_count": 0}


def test_money_drawdown_is_null_with_no_closed_trades(logged_in):
    dd = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    assert dd == {"value": None, "n": 0, "fx_missing_count": 0}


def test_money_drawdown_reads_the_account_currency_seam(logged_in, monkeypatch):
    """Amounts go through `to_account_currency`: a doubling fake proves the
    curve is built from converted rows, and a ticker without a rate is left
    out and counted -- never valued at 1.0."""
    def fake(rows, **_kw):
        return [
            {**row, "realized_pnl_amount": None, "fx_missing": True}
            if row["ticker"] == "NOFX"
            else {**row, "realized_pnl_amount": row["realized_pnl_amount"] * 2, "fx_missing": False}
            for row in rows
        ]

    monkeypatch.setattr("swingbot.admin.api_v1.risk.to_account_currency", fake)
    _seed_paid([100.0, -50.0, -80.0, 500.0], tickers={3: "NOFX"})
    dd = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    # kept: 200, -100, -160 -> cumulative 200, 100, -60 -> fall 260; NOFX left out
    assert dd == {"value": 260.0, "n": 3, "fx_missing_count": 1}


def test_money_drawdown_degrades_to_null_when_conversion_raises(logged_in, monkeypatch):
    def boom(rows, **_kw):
        raise RuntimeError("rate store down")

    monkeypatch.setattr("swingbot.admin.api_v1.risk.to_account_currency", boom)
    _seed_paid([100.0, -50.0])
    response = logged_in.get("/api/v1/risk")
    assert response.status_code == 200
    body = response.get_json()["metrics"]
    assert body["max_drawdown_amount"] == {"value": None, "n": 0, "fx_missing_count": 0}
    assert body["max_drawdown_r"]["n"] == 2          # the R metric is unaffected
```

`seed_store` is used by the `open_book` fixture already: run `git grep -n "seed_store" tests/admin/test_api_v1_risk.py`; if its import is local to the fixture, add `from tests.store_seed import seed_store` at module level.

- [ ] **Step 2: Run to verify failure.** `python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py` → the six new tests and `test_risk_shape` FAIL (`KeyError: 'max_drawdown_amount'`).

- [ ] **Step 3: Implement.** In `swingbot/admin/api_v1/risk.py`:
  - imports: after `from .auth import require_auth` add `from .money import missing_count, to_account_currency`.
  - Below `_metric` (`:217-218`) add the two helpers:

```python
def _pnl_amounts(converted: list[dict]) -> list[float]:
    """Account-currency P&L per closed trade, oldest close first. A trade
    with no amount (no FX rate) is left out, not counted as zero."""
    ordered = sorted(converted, key=lambda t: str(t.get("closed_at") or ""))
    return [float(t["realized_pnl_amount"]) for t in ordered
            if t.get("realized_pnl_amount") is not None]


def _money_drawdown(closed: list) -> dict:
    """`max_drawdown_amount`: the all-closed cumulative realised P&L's
    peak-to-trough fall in the account currency (v194 B8). Its own guard, like
    the R series beside it: a failed conversion nulls this one metric."""
    from swingbot.core.analytics import risk_metrics as rm
    try:
        converted = to_account_currency(closed)
        amounts = _pnl_amounts(converted)
        return {"value": rm.max_drawdown_r(amounts), "n": len(amounts),
                "fx_missing_count": missing_count(converted)}
    except Exception:
        return {"value": None, "n": 0, "fx_missing_count": 0}
```

  - In `_risk_metrics_and_correlation`: after `max_drawdown_r = _metric(rm.max_drawdown_r(r_series), len(r_series))` (`:281`) add `max_drawdown_amount = _money_drawdown(closed)`; after `null_metrics["max_drawdown_r"] = max_drawdown_r` (`:285`) add `null_metrics["max_drawdown_amount"] = max_drawdown_amount`; in the `metrics = {...}` dict after `"max_drawdown_r": max_drawdown_r,` (`:344`) add `"max_drawdown_amount": max_drawdown_amount,`. No new branches in that function.
  - `get_risk`'s docstring (`:362`): add one line under the metrics description: "`metrics.max_drawdown_amount` is `{value, n, fx_missing_count}`: the all-closed cumulative-P&L drawdown in the account currency (v194 B8)."

- [ ] **Step 4: Run to verify pass.** `python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py` → all green (`0 failed`).

Close: standard (test: tests/admin/test_api_v1_risk.py). Backend only: one `feat(v194)` commit, no frontend files.

### Task V194-11: B8 frontend — `sb-stat-tile` `about` hint; basis-named Sharpe / Max drawdown tiles on Risk and Analytics; money drawdown on Risk

**Model:** sonnet — one new tile input, label and hint copy fixed by the spec, tests spelled out.

**Files:**
- Modify: `frontend/src/app/ui/stat-tile.ts` (template `:35-55`, inputs `:125-131`; add `Hint` to `imports` and the import line)
- Modify: `frontend/src/app/ui/stat-tile.spec.ts` (new tests; `render(inputs)` helper at `:9-16`)
- Modify: `frontend/src/app/api/models.ts:1416-1430` (`RiskMetrics`)
- Modify: `frontend/src/app/workspaces/risk/risk.ts` (`metricTiles` `:745-757`, the tile loop `:171`, the footnote `:177-186` and its CSS rule `:571`, `fmtDrawdownR` `:736`)
- Modify: `frontend/src/app/workspaces/risk/risk.spec.ts` (every `'Sharpe (R)'` / `'Max drawdown (R)'` occurrence: `git grep -n "Sharpe (R)\|Max drawdown (R)" frontend/src`; tests at `:157-200`)
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.ts` (`kpiTiles` `:215-282`, `KpiTile` `:23-30`, the tile binding `:80`)
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts` (`describe('OverviewTab')` `:56`)

**Interfaces:**
- Consumes: `/api/v1/risk` `metrics.max_drawdown_amount` (V194-10); `Hint` (`frontend/src/app/ui/hint.ts`, selector `sb-hint`, inputs `text`, `label`); `money(value, unit, decimals)` (`ui/format.ts:60`, prints a leading `+` for a positive value); `this.connection.currency()` (already injected in `risk.ts`); `this.store.scopeN()` (overview).
- Produces: `StatTile.about = input<string | undefined>(undefined)`, rendered as `<sb-hint [text]="about()" [label]="'About ' + label()">` inside the `.label` element, only when set (`hint` stays the plain line under the value); `RiskMetrics.max_drawdown_amount?: RiskMetric & { fx_missing_count: number }` (optional, per the index's Global Constraints).

**Label and copy (spec B8).** Risk: `'Sharpe · per-trade R, all closed'`, `'Max drawdown · per-trade R, all closed'`. Analytics: `'Sharpe · annualised, selected range'`, `'Max drawdown · selected range'`. All four hints end in `PAPER_CAVEAT = 'Paper trades: simulated fills, gross of commissions and slippage, before tax.'` (a `const` at the top of `risk.ts` and another in `overview.ts`: the two files share no module and a third file for one sentence is not worth it). The old plain `hint` strings on the two Analytics tiles (`overview.ts:279`, `:281`) are replaced by `about`; Analytics' `Profit factor` keeps its `hint`. The hint texts are written in Steps 4 and 5.

- [ ] **Step 1: Write the failing tests.**
  - `stat-tile.spec.ts`, inside the existing `describe`:

```ts
  it('renders an sb-hint inside the label when about is set', () => {
    const el = render({ about: 'Definition, population and N.' });
    const hint = el.querySelector('.label sb-hint');
    expect(hint).not.toBeNull();
    expect(hint!.querySelector('button')!.getAttribute('aria-label')).toBe('About Win rate');
    expect(hint!.textContent).toContain('Definition, population and N.');
  });

  it('renders no hint when about is unset, and keeps the plain hint line', () => {
    const el = render({ hint: 'A plain line.' });
    expect(el.querySelector('sb-hint')).toBeNull();
    expect(el.querySelector('.hint')!.textContent).toContain('A plain line.');
  });
```
  (If `hint.ts`'s trigger is not a `<button>`, read how `hint.spec.ts` finds it and use that selector; the assertion is the trigger's accessible name `About Win rate`.)
  - `risk.spec.ts`: replace the two old labels in the six-tiles test with `['VaR 95%', 'Expected shortfall', 'Annualised vol', 'Beta vs SPY', 'Sharpe · per-trade R, all closed', 'Max drawdown · per-trade R, all closed']`, update every `tileHost(fixture, 'Sharpe (R)')` to the new label, replace the test `'labels Sharpe as an R measure so it is not read as annualised'` with the tests below. `renderWithMetrics(overrides)` merges into `metrics`; `max_drawdown_amount` is optional on the interface, so the default payload omits it.

```ts
  it('names its basis in the Sharpe and drawdown labels', async () => {
    const fixture = await renderWithMetrics();
    expect(tileLabels(fixture)).toContain('Sharpe · per-trade R, all closed');
    expect(tileLabels(fixture)).toContain('Max drawdown · per-trade R, all closed');
    expect(tileLabels(fixture)).not.toContain('Sharpe (R)');
  });

  it('carries the paper, gross and pre-tax caveat and the sample N in each basis tile hint', async () => {
    const fixture = await renderWithMetrics({ sharpe_r: { value: 0.9, n: 782 }, max_drawdown_r: { value: 12.5, n: 782 } });
    for (const label of ['Sharpe · per-trade R, all closed', 'Max drawdown · per-trade R, all closed']) {
      const text = tileHost(fixture, label).querySelector('sb-hint')!.textContent!;
      expect(text).toContain('N=782');
      expect(text).toContain('Paper trades');
      expect(text).toContain('gross of commissions and slippage');
      expect(text).toContain('before tax');
    }
  });

  it('shows the drawdown in the account currency under the R figure', async () => {
    const fixture = await renderWithMetrics({
      max_drawdown_amount: { value: 1234.5, n: 780, fx_missing_count: 0 },
    });
    const secondary = tileHost(fixture, 'Max drawdown · per-trade R, all closed').querySelector('.secondary')!.textContent!;
    expect(secondary).toContain('1,234.5');
    expect(secondary).toContain('−');
    expect(secondary).not.toContain('+');
  });

  it('says how many trades the money drawdown left out for want of an FX rate', async () => {
    const fixture = await renderWithMetrics({
      max_drawdown_amount: { value: 100, n: 780, fx_missing_count: 3 },
    });
    expect(tileHost(fixture, 'Max drawdown · per-trade R, all closed')
      .querySelector('.secondary')!.textContent).toContain('3 without an FX rate');
  });

  it('shows no money line when the backend sent none, and the old footnote is gone', async () => {
    const fixture = await renderWithMetrics();
    expect(tileHost(fixture, 'Max drawdown · per-trade R, all closed').querySelector('.secondary')).toBeNull();
    expect((fixture.nativeElement as HTMLElement).querySelector('.metrics-scope')).toBeNull();
  });
```
  - `overview.spec.ts`, inside `describe('OverviewTab')`. The existing `'shows six KPI tiles, all six labelled'` and the `tileFor(...)` substring lookups in `'gives the R-multiple tiles a money line...'` still match the longer labels, so they stand.

```ts
  const tileByLabel = (el: HTMLElement, label: string) =>
    Array.from(el.querySelectorAll('sb-stat-tile'))
      .find((t) => t.querySelector('.label')?.textContent?.trim() === label);

  it('names the basis of its Sharpe and Max drawdown tiles', () => {
    const { el } = render();
    expect(tileByLabel(el, 'Sharpe · annualised, selected range')).toBeDefined();
    expect(tileByLabel(el, 'Max drawdown · selected range')).toBeDefined();
    expect(el.textContent).not.toContain('Risk shows per-trade R, all-time');
  });

  it('gives both a hint with the paper, gross and pre-tax caveat', () => {
    const { el } = render();
    for (const label of ['Sharpe · annualised, selected range', 'Max drawdown · selected range']) {
      const text = tileByLabel(el, label)!.querySelector('sb-hint')!.textContent!;
      expect(text).toContain('Paper trades');
      expect(text).toContain('gross of commissions and slippage');
      expect(text).toContain('before tax');
    }
  });
```

- [ ] **Step 2: Run to verify failure.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/stat-tile.spec.ts --include src/app/workspaces/risk/risk.spec.ts --include src/app/workspaces/analytics/tabs/overview.spec.ts` → the new tests FAIL (no `about` input, old labels).

- [ ] **Step 3: Implement `about` on the tile.** `stat-tile.ts`: `import { Hint } from './hint';`, `imports: [Sparkline, CountUp, Hint]`, add `readonly about = input<string | undefined>(undefined);` after `hint`, and change the label line to

```html
      <div class="label sb-label">{{ label() }}@if (about(); as text) { <sb-hint [text]="text" [label]="'About ' + label()" /> }</div>
```

  Add one sentence to the class doc comment: "`about` is the definition behind the figure, an `sb-hint` beside the label; `hint` is a plain line under the value."

- [ ] **Step 4: Implement Risk.** `models.ts` `RiskMetrics`: after `max_drawdown_r: RiskMetric;` add `max_drawdown_amount?: RiskMetric & { fx_missing_count: number };` with a doc comment: v194 B8, the same fall in the account currency (positive magnitude), converted per trade at its exit date; `fx_missing_count` trades had no rate and are left out; absent on an older backend. In `risk.ts` add `const PAPER_CAVEAT = 'Paper trades: simulated fills, gross of commissions and slippage, before tax.';` above the component, and change the last two `metricTiles` rows (`:755-756`) to:

```ts
      { label: 'Sharpe · per-trade R, all closed', value: this.fmtRatio(m.sharpe_r.value), sample: m.sharpe_r.n,
        about: `Mean ÷ standard deviation of each closed trade's R multiple, not annualised. Population: every closed trade (N=${m.sharpe_r.n}). ${PAPER_CAVEAT} Analytics shows an annualised Sharpe over its selected date range.` },
      { label: 'Max drawdown · per-trade R, all closed', value: this.fmtDrawdownR(m.max_drawdown_r.value), sample: m.max_drawdown_r.n,
        secondary: this.fmtDrawdownAmount(m.max_drawdown_amount),
        about: `Largest peak-to-trough fall of cumulative R over every closed trade (N=${m.max_drawdown_r.n}); the line below is the same fall in ${this.connection.currency()}, each trade converted at its exit date. ${PAPER_CAVEAT}` },
```

  New helper beside `fmtDrawdownR` (`:736`); import `RiskMetrics` from `../../api/models` and `money` from `../../ui/format` if absent:

```ts
  /** The money line under the drawdown tile: negative like the R figure; null
   *  when the backend sent none. Trades without an FX rate are named, not hidden. */
  private fmtDrawdownAmount(metric: RiskMetrics['max_drawdown_amount']): string | null {
    if (!metric || metric.value === null) return null;
    const amount = money(Math.abs(metric.value), this.connection.currency(), 2).replace(/^\+/, '');
    const text = `${metric.value === 0 ? '' : '−'}${amount}`;
    return metric.fx_missing_count > 0 ? `${text} · ${metric.fx_missing_count} without an FX rate` : text;
  }
```

  The tile loop (`:171`) becomes `<sb-stat-tile [label]="tile.label" [value]="tile.value" [sample]="tile.sample" [secondary]="tile.secondary ?? null" [about]="tile.about" />`. Delete the `<p class="metrics-scope">` block with its comment (`:177-186`) and the `.metrics-scope` CSS rule (`:571`). The four distributional tiles get no `about` (the A4 audit, V194-16, owns their copy).

- [ ] **Step 5: Implement Analytics.** `overview.ts`: add `const PAPER_CAVEAT = ...` (same sentence); `KpiTile` gains `about?: string;`; the two tiles at `:276-281` become (keep the "Negated: a drawdown is a loss…" comment above the first):

```ts
      { ...tile('Max drawdown · selected range', drawdownR === null ? null : -drawdownR, null,
          drawdownMoney === null ? null : -drawdownMoney, equityCurve?.points_n ?? null),
        about: `Largest peak-to-trough fall inside the selected range, from the equity curve. Risk shows the all-closed-trades figure. ${PAPER_CAVEAT}` },
      { ...fixedTile('Sharpe · annualised, selected range', signed(sharpe, 2), this.store.scopeN()),
        about: `Annualised, from realised returns inside the selected range (N=${this.store.scopeN() ?? 0}). Risk shows the per-trade R Sharpe over every closed trade. ${PAPER_CAVEAT}` },
```

  and the tile binding (`:80`) gains `[about]="tile.about"`.

- [ ] **Step 6: Run to verify pass.** The Step 2 command → green; then the whole-frontend run and lint from the standard close.

Close: standard (test: frontend/src/app/workspaces/risk/risk.spec.ts). Deviation: the narrow run is the three specs named in Step 2; before committing, a Playwright screenshot of Risk's metrics strip and Analytics' Overview KPI row at 390 and 1440 against the local replica (the longer labels must wrap inside their tiles, not widen the strip).

### Task V194-12: B3 data and helper — `leg_exit_reason` on leg rows; shared `legLabel` and `LEG_HINT_TEXT`; Calendar uses them

**Model:** sonnet — one backend key beside `leg_index`, one small pure helper, and a rename-with-reuse in Calendar.

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py:362` (`_row_from_plan` defaults), `:551` (`_row_from_leg`, beside `"leg_index": leg_index`), `:665` (`_row_from_trade` defaults)
- Modify: `tests/admin/test_api_v1_trades.py` (`TRADE_ROW` `:35`, new tests after `test_open_shares_is_reduced_by_a_realized_tp1_leg` `:400`)
- Modify: `frontend/src/app/api/models.ts:190-198` (`TradeRow`)
- Create: `frontend/src/app/workspaces/trades/leg-label.ts`, `frontend/src/app/workspaces/trades/leg-label.spec.ts`
- Modify: `frontend/src/app/workspaces/calendar/day/day-trade-card.ts` (the local `legLabel` `:14-17` deleted; `imports` `:40`; template `:48-50`; class `:132`)
- Modify: `frontend/src/app/workspaces/calendar/day/day-trade-card.spec.ts:9,50-51` (not in the ledger: the old helper's import and its two assertions move with the helper)
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts` (imports `:4-12` and `imports:` `:29`, template `:291`, class)

**Interfaces:**
- Consumes: `_row_from_leg(plan, trade, leg, leg_index, noted) -> dict` and `_runner_exit_reason(leg: dict) -> str | None` (`trades.py:408`; returns `"giveback"` when `stop_source == "giveback"`, else the leg's `reason`); `reasonLabel(reason: string | null | undefined): string | null` (`workspaces/trades/exit-reasons.ts`, maps `tp1` → `TP1`, `stop` → `Stop`, `runner_trail` → `Runner trailed`, an unknown code → itself); `Hint` (`ui/hint.ts`, `sb-hint`, inputs `text`, `label`); `CalendarTrade` (`leg_index`, `leg_total`, `exit_reason: string`, one of the metrics `EXIT_REASONS` incl. `other`).
- Produces: leg-row field `leg_exit_reason: str | None` on **every** `/trades` row (`None` on a non-leg row, the key is always present so `TRADE_ROW` can declare it); `TradeRow.leg_exit_reason?: string | null`; in `leg-label.ts`: `interface LegLike { leg_index: number; leg_total: number; leg_exit_reason?: string | null; exit_reason?: string | null }`, `legLabel(row: LegLike): string | null`, `LEG_HINT_TEXT: string`. V194-13 and V194-16 consume them.

**`legLabel` rules (spec B3).** `null` unless `leg_total > 1`. Otherwise `Leg ${leg_index + 1} of ${leg_total}`. A reason follows as `' · ' + reasonLabel(reason)` where `reason = row.leg_exit_reason ?? row.exit_reason`; no suffix when the reason is empty, unknown to `reasonLabel` (null), or the Calendar's catch-all `'other'`. Never "TP1"/"Runner" as the label itself: `leg_index` follows realisation order, so leg 1 may be a stop-out.

**`LEG_HINT_TEXT`** is exactly: `These rows are the parts of one plan. Each row's P&L is that part's share of the plan. Win rate and N count plans, not legs.`

**The name clash (index Handoff, B3).** `legLabel(trade: CalendarTrade)` already exists at `day-trade-card.ts:14-17` and is imported by `day-trade-card.spec.ts`. The shared helper **replaces** it: `CalendarTrade` satisfies `LegLike` structurally (`exit_reason: string` fits `exit_reason?: string | null`), so there is one function, not two. `day-trade-card.ts` deletes its own and imports the shared one; it does not re-export it, and its spec imports from the shared file.

- [ ] **Step 1: Write the failing backend tests.** In `tests/admin/test_api_v1_trades.py`: add `"leg_exit_reason": NULLABLE_STR,` to `TRADE_ROW` right after the `leg_index`/`leg_total` entries (find them with `grep -n "leg_index" tests/admin/test_api_v1_trades.py`), then add:

```python
def test_a_realized_leg_row_carries_its_own_exit_reason(seed, logged_in, monkeypatch):
    plan = _plan("11111111-1111-4111-8111-111111111111", status="PARTIAL")
    plan["legs_realized"] = [
        {"fraction": 0.5, "exit_price": 110.0, "r": 1.8, "reason": "tp1"},
    ]
    trade = _trade("aaaaaaaaaaaaaaaa", plan_id=plan["plan_id"], status="open")
    trade["shares"] = 10
    seed(plans=[plan], trades=[trade])
    monkeypatch.setattr("swingbot.admin.api_v1.trades._attach_current_prices", lambda rows: None)

    items = logged_in.get("/api/v1/trades").get_json()["items"]
    banked = next(r for r in items if r["leg_index"] == 0 and r["leg_total"] > 1)
    runner = next(r for r in items if r["status"] == "PARTIAL")
    assert banked["leg_exit_reason"] == "tp1"
    assert runner["leg_exit_reason"] is None        # the still-open runner has not exited


def test_a_row_that_is_not_a_leg_has_no_leg_exit_reason(seed, logged_in):
    seed(trades=[_trade("aaaaaaaaaaaaaaaa", status="closed")])
    row = logged_in.get("/api/v1/trades").get_json()["items"][0]
    assert row["leg_total"] == 1
    assert row["leg_exit_reason"] is None


def test_a_giveback_runner_leg_reports_giveback_not_the_trail_reason():
    from swingbot.admin.api_v1 import trades as trades_api
    plan = _plan("11111111-1111-4111-8111-111111111111", status="CLOSED")
    trade = _trade("aaaaaaaaaaaaaaaa", plan_id=plan["plan_id"], status="closed")
    leg = {"fraction": 0.5, "exit_price": 104.0, "r": 0.4,
           "reason": "runner_trail", "stop_source": "giveback"}
    row = trades_api._row_from_leg(plan, trade, leg, 1, set())
    assert row["leg_exit_reason"] == "giveback"
```

  If `_row_from_leg` needs plan/trade keys the helpers do not set, give the three-line fixture those keys (read the raised `KeyError`); the assertion is the contract.

- [ ] **Step 2: Run to verify failure.** `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py` → the three new tests and every `TRADE_ROW`-checked test FAIL (`leg_exit_reason` missing from the response).

- [ ] **Step 3: Implement the backend.** In `trades.py`: add `"leg_exit_reason": None,` next to `"leg_index": 0,` / `"leg_total": 1,` in `_row_from_plan` (`:362-363`) and `_row_from_trade` (`:665-666`) — dict entries only, no new branch (`_row_from_plan` is already CC 15 and must not grow); add `"leg_exit_reason": _runner_exit_reason(leg),` after `"leg_index": leg_index,` in `_row_from_leg` (`:551`). The still-open runner remainder row (`_expand_plan_row`, `:576`) is built from `_row_from_plan`, so it inherits `None`.

- [ ] **Step 4: Run to verify pass.** `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py` → green. Run `python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_detail.py` too: it imports `TRADE_ROW`.

- [ ] **Step 5: Commit the backend** (`feat(v194): leg_exit_reason on leg rows (V194-12)`, with the trailer) before touching `frontend/`.

- [ ] **Step 6: Write the failing frontend tests.** Create `frontend/src/app/workspaces/trades/leg-label.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { LEG_HINT_TEXT, legLabel } from './leg-label';

const leg = (index: number, total: number, reason?: string | null) =>
  ({ leg_index: index, leg_total: total, leg_exit_reason: reason });

describe('legLabel', () => {
  it('is null for a single-leg trade, with or without a reason', () => {
    expect(legLabel(leg(0, 1))).toBeNull();
    expect(legLabel(leg(0, 1, 'tp1'))).toBeNull();
    expect(legLabel(leg(0, 0))).toBeNull();
  });

  it('numbers legs 1-based out of the total, for two and three legs', () => {
    expect(legLabel(leg(0, 2))).toBe('Leg 1 of 2');
    expect(legLabel(leg(1, 2))).toBe('Leg 2 of 2');
    expect(legLabel(leg(2, 3))).toBe('Leg 3 of 3');
  });

  it('appends the leg exit reason in the Trades wording', () => {
    expect(legLabel(leg(0, 2, 'tp1'))).toBe('Leg 1 of 2 · TP1');
    expect(legLabel(leg(1, 2, 'stop'))).toBe('Leg 2 of 2 · Stop');
    expect(legLabel(leg(1, 2, 'timeout'))).toBe('Leg 2 of 2 · Time exit');
  });

  it('does not assume leg 1 is the target or the last leg a runner', () => {
    expect(legLabel(leg(0, 2, 'stop'))).toBe('Leg 1 of 2 · Stop');
    expect(legLabel(leg(1, 2, 'tp1'))).toBe('Leg 2 of 2 · TP1');
  });

  it('stands alone when the reason is missing, blank or the Calendar catch-all', () => {
    expect(legLabel(leg(0, 2, null))).toBe('Leg 1 of 2');
    expect(legLabel(leg(0, 2, '   '))).toBe('Leg 1 of 2');
    expect(legLabel({ leg_index: 0, leg_total: 2, exit_reason: 'other' })).toBe('Leg 1 of 2');
  });

  it('falls back to exit_reason (Calendar rows) when there is no leg_exit_reason', () => {
    expect(legLabel({ leg_index: 1, leg_total: 3, exit_reason: 'runner_trail' })).toBe('Leg 2 of 3 · Runner trailed');
    expect(legLabel({ leg_index: 1, leg_total: 3, leg_exit_reason: 'stop', exit_reason: 'tp1' })).toBe('Leg 2 of 3 · Stop');
  });
});

describe('LEG_HINT_TEXT', () => {
  it('says the rows are one plan and that win rate and N count plans, not legs', () => {
    expect(LEG_HINT_TEXT).toContain('parts of one plan');
    expect(LEG_HINT_TEXT).toContain("that part's share");
    expect(LEG_HINT_TEXT).toContain('plans, not legs');
  });
});
```

  `day-trade-card.spec.ts`: change the import at `:9` to `import { DayTradeCard, heldLabel, tradeLinkId } from './day-trade-card';` plus `import { legLabel } from '../../trades/leg-label';`; the assertion `expect(legLabel({ ...TRADE, leg_index: 1, leg_total: 3 })).toBe('Leg 2 of 3');` becomes `.toBe('Leg 2 of 3 · TP1')` (the fixture's `exit_reason` is `'tp1'`), and add to the card tests (find the existing test that renders a multi-leg trade, or add one rendering `{ ...TRADE, leg_index: 1, leg_total: 3 }`):

```ts
  it('shows the leg label with the plans-not-legs hint on a scale-out leg, and neither on a whole trade', () => {
    const leg = render({ ...TRADE, leg_index: 1, leg_total: 3 });
    expect(leg.querySelector('.leg')!.textContent).toContain('Leg 2 of 3 · TP1');
    expect(leg.querySelector('.leg sb-hint, sb-hint')!.textContent).toContain('plans, not legs');
    const whole = render(TRADE);
    expect(whole.querySelector('.leg')).toBeNull();
    expect(whole.querySelector('sb-hint')).toBeNull();
  });
```

  (`render` here is the spec's existing helper for `DayTradeCard`; use its real name and `setInput('trade', …)` shape from the file.) `calendar.spec.ts` is not touched: Calendar's day drawer shares the label through `legLabel`, covered above, and the drawer line is checked by the Step 9 screenshot.

- [ ] **Step 7: Run to verify failure.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/trades/leg-label.spec.ts --include src/app/workspaces/calendar/day/day-trade-card.spec.ts` → FAIL (`leg-label` does not exist).

- [ ] **Step 8: Implement the frontend.**
  - `models.ts` `TradeRow` (after `leg_total: number;` `:197`): `/** v194 B3 -- why this leg exited (a leg row only; null on a whole trade or an open runner). */ leg_exit_reason?: string | null;`.
  - Create `leg-label.ts` exporting `LegLike`, `LEG_HINT_TEXT` (the exact sentence above) and `legLabel(row: LegLike): string | null` per the rules above; it imports `reasonLabel` from `./exit-reasons`. Drop `'other'` before calling `reasonLabel`.
  - `day-trade-card.ts`: delete `:14-17` (and its doc comment); `import { LEG_HINT_TEXT, legLabel } from '../../trades/leg-label';` and `import { Hint } from '../../../ui/hint';`; `imports: [Chip, Hint, RouterLink, TradeSparkline]`; add `protected readonly legHint = LEG_HINT_TEXT;`; the template (`:48-50`) becomes `@if (leg(); as label) { <span class="leg">{{ label }}</span><sb-hint [text]="legHint" label="About leg rows" /> }`. `protected readonly leg = computed(() => legLabel(this.trade()))` stays.
  - `calendar.ts`: `import { LEG_HINT_TEXT, legLabel } from '../trades/leg-label';`, `import { Hint } from '../../ui/hint';`, `Hint` added to `imports:` (`:29`), class members `protected readonly legLabel = legLabel; protected readonly legHint = LEG_HINT_TEXT;`, and the template line `:291` becomes
    `@if (legLabel(trade); as leg) { <span class="leg">{{ leg }}</span><sb-hint [text]="legHint" label="About leg rows" /> · }`.
  - Verify nothing else imported the old helper: `git grep -n "legLabel" frontend/src` lists only `leg-label.ts`, its spec, `day-trade-card.*` and `calendar.ts`.

- [ ] **Step 9: Run to verify pass.** The Step 7 command → green. Then a Playwright screenshot of the Calendar day drawer for a scale-out day at 390 and 1440 on the local replica: the label, the hint trigger and the dot separator share a line or wrap, with no overflow; the hint's popover stays inside the viewport.

Close: standard (test: frontend/src/app/workspaces/trades/leg-label.spec.ts). Deviation: two commits (backend at Step 5, frontend here); the backend's narrow run is `tests/admin/test_api_v1_trades.py`.

