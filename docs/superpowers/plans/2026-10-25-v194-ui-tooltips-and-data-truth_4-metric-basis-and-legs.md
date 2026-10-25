# v194 — UI integrity: tooltips that open, figures that are true: Implementation Plan (part 4 — metric basis and legs)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [2026-10-25-v194-ui-tooltips-and-data-truth.md](../specs/2026-10-25-v194-ui-tooltips-and-data-truth.md)
**Index:** [2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md](2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md) — Global Constraints, `### Standard task close`, `## Parallelisation`, `## Handoff` and the task ledger live there; every task below inherits them.

Tasks: V194-10 (B8 backend), V194-11 (B8 frontend), V194-12 (B3 data and helper).

Line numbers are those of `main` at 2026-10-25. Earlier parts edit some of the same files (`risk.ts`, `risk.spec.ts` in V194-7/V194-9, `models.ts` in V194-6c/V194-9, `trades.py` in V194-6b), so a cited range can drift by a few lines: locate the edit by the quoted old text, which is exact.

# Phase B8 — one name per quantity, money beside R

### Task V194-10: B8 backend — `metrics.max_drawdown_amount` on `/risk`, all closed trades, in the account currency

**Model:** sonnet — one helper pair inside an existing guarded block, test patterns already in the file.

**Files:**
- Modify: `swingbot/admin/api_v1/risk.py:217-218` (after `_metric`, two new helpers), `:276-286` and `:343-344` (`_risk_metrics_and_correlation`)
- Test: `tests/admin/test_api_v1_risk.py:151-162` (`test_risk_shape`), new tests appended after `test_an_empty_book_returns_metrics_of_nulls_rather_than_omitting_them` (`:307-311`)

**Interfaces:**
- Consumes: `to_account_currency(rows, *, account=None) -> list[dict]` and `missing_count(rows) -> int` from `swingbot/admin/api_v1/money.py` (V194-6b; copies, `realized_pnl_amount` converted or `None`, `fx_missing: bool` on each); `fx.account_currency_code`, `fx.quote_currency_code`, `fx.fx_rate` in `swingbot/core/marketdata/fx.py` (V194-6/6a; `money.py` reads them at call time, so tests monkeypatch the `fx` module); `rm.max_drawdown_r(series) -> float | None` (`swingbot/core/analytics/risk_metrics.py:174`, a positive magnitude of the cumulative series' largest peak-to-trough fall — unit-agnostic, reused for money); `_metric` (`risk.py:217`).
- Produces: `GET /api/v1/risk` → `metrics.max_drawdown_amount: {"value": float | None, "n": int, "fx_missing_count": int}` (value positive, rounded to 2, account currency; present in both the computed and the null-metrics branch); `_pnl_amounts(closed: list) -> list[float]` in `risk.py`. V194-11 reads the field.

**Definition (decided here).** The money walk is the realised P&L of every closed main-ledger trade (the same `closed` list the R figures use), converted per trade at its exit date's rate, **ordered by `closed_at`, oldest first** (a peak-to-trough decline of cumulative P&L is a time walk). A trade with no rate (`fx_missing`) is left out and counted in `fx_missing_count`; a trade with no settled amount (`realized_pnl_amount` null, `fx_missing` false) is left out and not counted. `n` is the number of amounts walked. A conversion failure degrades only this metric to `{"value": None, "n": 0, "fx_missing_count": 0}`.

- [ ] **Step 1: Write the failing tests**

In `tests/admin/test_api_v1_risk.py`, `test_risk_shape` (`:151-162`), old:

```python
    assert_shape(body["metrics"], {
        **{key: dict for key in metric_keys},
        "as_of": NULLABLE_STR,
```

new:

```python
    assert_shape(body["metrics"], {
        **{key: dict for key in metric_keys},
        # v194 B8 -- the money twin of max_drawdown_r; carries its FX gap count.
        "max_drawdown_amount": dict,
        "as_of": NULLABLE_STR,
```

and after the `for key in metric_keys:` loop that ends at `:162` (`}, where=f"metrics.{key}")`), add:

```python
    assert_shape(body["metrics"]["max_drawdown_amount"], {
        "value": NULLABLE_NUMBER, "n": int, "fx_missing_count": int,
    }, where="metrics.max_drawdown_amount")
```

Append after `test_an_empty_book_returns_metrics_of_nulls_rather_than_omitting_them` (`:307-311`):

```python
# -- v194 B8 -- max drawdown in money, beside the R figure. --

def _settled(trade_id, *, ticker="AAPL", pnl, closed_at, status="closed"):
    """A closed main-ledger trade with a settled amount in its quote currency."""
    return {
        "id": trade_id, "ticker": ticker, "status": status,
        "strategy": "VWAP", "horizon_key": "1m", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "exit_price": 105.0, "shares": 10,
        "opened_at": "2026-07-01T00:00:00+00:00", "closed_at": closed_at,
        "realized_pnl_amount": pnl,
    }


@pytest.fixture
def eur_account(logged_in, monkeypatch):
    """A EUR account: USD quotes convert at 0.5 on every day; `NOFX` has no
    quote currency, so its rate is missing. Depends on `logged_in` so it is
    applied after the admin app's own FX pin. Returns the lookups made."""
    from swingbot.core.marketdata import fx
    asked = []

    def fake_rate(from_code, to_code, on):
        asked.append((from_code, to_code, on))
        return 0.5 if from_code == "USD" else None

    quotes = {"AAPL": "USD", "MSFT": "USD", "ASML.AS": "EUR"}
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: quotes.get(ticker))
    monkeypatch.setattr(fx, "fx_rate", fake_rate)
    return asked


def test_money_drawdown_walks_converted_pnl_in_close_order(logged_in, eur_account):
    # Seeded out of order on purpose: the walk sorts by closed_at.
    # In close order: +100, -300, +50, -200 USD -> x0.5 -> +50, -150, +25, -100 EUR.
    # Cumulative 50, -100, -75, -175; peak 50 -> largest fall 225.
    seed_store("trades", [
        _settled("c3", pnl=50.0, closed_at="2026-08-05T20:00:00+00:00"),
        _settled("c1", pnl=100.0, closed_at="2026-08-03T20:00:00+00:00"),
        _settled("c4", pnl=-200.0, closed_at="2026-08-06T20:00:00+00:00", status="loss"),
        _settled("c2", pnl=-300.0, closed_at="2026-08-04T20:00:00+00:00", status="loss"),
    ])
    metric = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    assert metric == {"value": 225.0, "n": 4, "fx_missing_count": 0}


def test_a_trade_without_a_rate_is_left_out_and_counted(logged_in, eur_account):
    seed_store("trades", [
        _settled("c1", pnl=100.0, closed_at="2026-08-03T20:00:00+00:00"),
        _settled("c2", ticker="NOFX", pnl=-900.0, closed_at="2026-08-04T20:00:00+00:00"),
        _settled("c3", pnl=-300.0, closed_at="2026-08-05T20:00:00+00:00"),
    ])
    metric = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    # +50, -150 in EUR (cumulative 50, -100): the -900 with no rate is never read as 1.0.
    assert metric == {"value": 150.0, "n": 2, "fx_missing_count": 1}


def test_an_unsettled_close_is_left_out_but_not_counted_as_missing(logged_in, eur_account):
    seed_store("trades", [
        _settled("c1", pnl=100.0, closed_at="2026-08-03T20:00:00+00:00"),
        _settled("c2", pnl=None, closed_at="2026-08-04T20:00:00+00:00"),
        _settled("c3", pnl=-100.0, closed_at="2026-08-05T20:00:00+00:00"),
    ])
    metric = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    assert metric == {"value": 50.0, "n": 2, "fx_missing_count": 0}   # +50, -50 EUR


def test_an_account_in_the_quote_currency_converts_nothing(logged_in, eur_account, monkeypatch):
    from swingbot.core.marketdata import fx
    monkeypatch.setattr(fx, "account_currency_code", lambda: "USD")
    seed_store("trades", [
        _settled("c1", pnl=100.0, closed_at="2026-08-03T20:00:00+00:00"),
        _settled("c2", pnl=-300.0, closed_at="2026-08-04T20:00:00+00:00"),
    ])
    metric = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    assert metric == {"value": 300.0, "n": 2, "fx_missing_count": 0}
    assert eur_account == []          # identity: no rate was asked for


def test_no_closed_trade_gives_a_null_money_drawdown_not_zero(logged_in, eur_account):
    seed_store("trades", [_open_trade("o1")])
    metric = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    assert metric == {"value": None, "n": 0, "fx_missing_count": 0}


def test_a_conversion_failure_degrades_only_the_money_drawdown(logged_in, eur_account, monkeypatch):
    def boom(rows, **kwargs):
        raise RuntimeError("rate store down")

    monkeypatch.setattr("swingbot.admin.api_v1.money.to_account_currency", boom)
    seed_store("trades", [
        _closed_trade("c1", win=True), _closed_trade("c2", win=False),
        _settled("c3", pnl=-100.0, closed_at="2026-08-05T20:00:00+00:00"),
    ])
    response = logged_in.get("/api/v1/risk")
    assert response.status_code == 200
    metrics = response.get_json()["metrics"]
    assert metrics["max_drawdown_amount"] == {"value": None, "n": 0, "fx_missing_count": 0}
    assert metrics["max_drawdown_r"]["value"] is not None


def test_pnl_amounts_sorts_by_close_and_skips_unpriced_rows():
    import swingbot.admin.app  # noqa: F401 -- api_v1 imports resolve through the app
    from swingbot.admin.api_v1.risk import _pnl_amounts
    rows = [
        {"closed_at": "2026-08-05T00:00:00+00:00", "realized_pnl_amount": 3.0},
        {"closed_at": "2026-08-03T00:00:00+00:00", "realized_pnl_amount": 1.0},
        {"closed_at": "2026-08-04T00:00:00+00:00", "realized_pnl_amount": None},
        {"closed_at": None, "realized_pnl_amount": 9.0},
    ]
    assert _pnl_amounts(rows) == [1.0, 3.0, 9.0]   # no close stamp sorts last
    assert _pnl_amounts([]) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py`
Expected: FAIL — `test_risk_shape` with `metrics: missing key(s) ['max_drawdown_amount']`, the six money tests with `KeyError: 'max_drawdown_amount'`, `test_pnl_amounts_sorts_by_close_and_skips_unpriced_rows` with `ImportError: cannot import name '_pnl_amounts'`.

- [ ] **Step 3: Implement the helpers in `swingbot/admin/api_v1/risk.py`**

After `_metric` (`:217-218`), insert:

```python
def _pnl_amounts(closed: list) -> list[float]:
    """Realised amounts of `closed`, oldest close first (no stamp sorts last),
    rows without an amount skipped -- the money walk behind
    `max_drawdown_amount`. `closed` is already in the account currency
    (`to_account_currency`), so a skipped row is either unsettled or had no
    FX rate; the caller counts the second kind."""
    ordered = sorted(closed, key=lambda trade: str(trade.get("closed_at") or "￿"))
    return [
        float(trade["realized_pnl_amount"])
        for trade in ordered
        if trade.get("realized_pnl_amount") is not None
    ]


def _max_drawdown_amount(closed: list) -> dict:
    """v194 B8: the money twin of `max_drawdown_r` -- the largest
    peak-to-trough fall of cumulative realised P&L over every closed trade,
    in the account currency, a positive magnitude. Converted read-side per
    trade at its exit date's rate (`money.to_account_currency`); a trade
    with no rate is left out and counted, never read at 1.0. Its own guard:
    a conversion failure blanks this figure, not the R metrics beside it."""
    from swingbot.core.analytics import risk_metrics as rm

    from . import money
    try:
        converted = money.to_account_currency(closed)
        amounts = _pnl_amounts(converted)
        value = rm.max_drawdown_r(amounts)   # unit-agnostic: a cumulative walk
    except Exception:
        return {"value": None, "n": 0, "fx_missing_count": 0}
    return {
        "value": None if value is None else round(value, 2),
        "n": len(amounts),
        "fx_missing_count": money.missing_count(converted),
    }
```

(`money.to_account_currency` is read through the module at call time, so the failure test's monkeypatch on `swingbot.admin.api_v1.money.to_account_currency` reaches it.)

In `_risk_metrics_and_correlation`, `:280-286`, old:

```python
    sharpe_r = _metric(rm.sharpe_of(r_series), len(r_series))
    max_drawdown_r = _metric(rm.max_drawdown_r(r_series), len(r_series))

    null_metrics = {key: _metric(None, 0) for key in metric_keys}
    null_metrics["sharpe_r"] = sharpe_r
    null_metrics["max_drawdown_r"] = max_drawdown_r
```

new:

```python
    sharpe_r = _metric(rm.sharpe_of(r_series), len(r_series))
    max_drawdown_r = _metric(rm.max_drawdown_r(r_series), len(r_series))
    max_drawdown_amount = _max_drawdown_amount(closed)

    null_metrics = {key: _metric(None, 0) for key in metric_keys}
    null_metrics["sharpe_r"] = sharpe_r
    null_metrics["max_drawdown_r"] = max_drawdown_r
    null_metrics["max_drawdown_amount"] = max_drawdown_amount
```

and in the computed `metrics` dict, `:343-344`, old:

```python
            "sharpe_r": sharpe_r,
            "max_drawdown_r": max_drawdown_r,
```

new:

```python
            "sharpe_r": sharpe_r,
            "max_drawdown_r": max_drawdown_r,
            # v194 B8: {value, n, fx_missing_count} -- money, account currency.
            "max_drawdown_amount": max_drawdown_amount,
```

No new branch lands in `_risk_metrics_and_correlation` (one call, two assignments), so its complexity is unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py`
Expected: PASS, `0 failed`, `0 xfailed` (the existing metric tests keep passing: `test_every_metric_carries_its_own_sample_size` lists its six keys explicitly and does not include the new one).

- [ ] **Step 5: Close**

Close: standard (test: tests/admin/test_api_v1_risk.py). Commit `feat(v194): money max drawdown on /risk in the account currency (V194-10)`. Backend only — one commit.

### Task V194-11: B8 frontend — `sb-stat-tile` `about` hint; basis-named Sharpe / Max drawdown on Risk; money drawdown on Risk; footnote removed

**Model:** sonnet — one new input plus label and copy changes on two pages, all covered by existing spec helpers.

**Files:**
- Modify: `frontend/src/app/ui/stat-tile.ts:1-6` (imports), `:34-41` (`imports`, label line), `:94-97` (`.label` style), `:124-131` (inputs)
- Modify: `frontend/src/app/api/models.ts:1416-1430` (`RiskMetrics`)
- Modify: `frontend/src/app/workspaces/risk/risk.ts:22` and `:29` (imports), `:171` (tile binding), `:173-186` (footnote), `:571` (`.metrics-scope` style), `:735-757` (`fmtDrawdownR`, `metricTiles`)
- Test: `frontend/src/app/ui/stat-tile.spec.ts`, `frontend/src/app/workspaces/risk/risk.spec.ts`
- Split: the Analytics half (`overview.ts`) is V194-11b, so each task stays under the 400-line ceiling.

**Interfaces:**
- Consumes: `metrics.max_drawdown_amount: {value, n, fx_missing_count}` from V194-10 (`value` a positive magnitude in the account currency); `Hint` (`frontend/src/app/ui/hint.ts`, inputs `text`, `label`; its popover is `[role="tooltip"]` and its trigger carries `aria-label`); the global popover polyfill from V194-1; `money(value, unit, decimals)` (`ui/format.ts:60`).
- Produces: `StatTile.about = input<string | undefined>(undefined)` (renders `<sb-hint>` beside the label, trigger `aria-label` `"About <label>"`); `PERFORMANCE_CAVEAT` (exported from `ui/stat-tile.ts`); `RiskMetrics.max_drawdown_amount?: RiskMetric & { fx_missing_count: number }`; exported label/hint constants `RISK_SHARPE_LABEL`, `RISK_DRAWDOWN_LABEL`, `RISK_SHARPE_ABOUT`, `RISK_DRAWDOWN_ABOUT`, `drawdownFxNote(missing: number): string | undefined` (in `risk.ts`). V194-11b consumes `about` and `PERFORMANCE_CAVEAT`. V194-14 converts `stat-tile.ts`'s `[title]="sampleTitle()"` and may reuse `about`; V194-16 audits the hint texts written here.

**Decisions.** Labels: Risk "Sharpe · per-trade R, all closed" / "Max drawdown · cumulative R, all closed"; Analytics "Sharpe · annualised, selected range" / "Max drawdown · cumulative R, selected range". The definition moves from the plain `hint` line into the `about` popover, so the old Analytics hint lines on these two tiles go. The caveat is gross (the tracker models no fees or slippage: `swingbot/core/tracking/performance.py:15`); V194-16 re-checks it. Risk's money line uses the tile's existing `secondary` slot, negative like the R figure; a missing-FX count shows in the tile's plain `hint` line.

- [ ] **Step 1: Write the failing `stat-tile` tests**

Append inside `describe('StatTile (v85 D23)', ...)` in `frontend/src/app/ui/stat-tile.spec.ts`, and add `PERFORMANCE_CAVEAT` to its import (`import { MIN_SAMPLE_N, PERFORMANCE_CAVEAT, StatTile } from './stat-tile';`):

```ts
  it('renders an about hint beside the label, named for the tile (v194 B8)', () => {
    const el = render({ about: 'Mean R over every closed trade.' });
    const hint = el.querySelector('.label-row sb-hint');
    expect(hint).not.toBeNull();
    expect(hint!.querySelector('button')!.getAttribute('aria-label')).toBe('About Win rate');
    expect(hint!.querySelector('[role="tooltip"]')!.textContent).toContain('Mean R over every closed trade.');
  });

  it('keeps the label text to the label alone when an about hint is present', () => {
    const el = render({ about: 'Definition.' });
    expect(el.querySelector('.label')!.textContent!.trim()).toBe('Win rate');
  });

  it('renders no hint trigger without an about text', () => {
    expect(render({}).querySelector('sb-hint')).toBeNull();
    expect(render({ about: '' }).querySelector('sb-hint')).toBeNull();
  });

  it('keeps the plain hint line as plain text, separate from the about hint', () => {
    const el = render({ hint: '3 trades left out.', about: 'Definition.' });
    expect(el.querySelector('div.hint')!.textContent).toContain('3 trades left out.');
    expect(el.querySelector('div.hint sb-hint')).toBeNull();
  });

  it('states the performance caveat as paper, gross and pre-tax', () => {
    expect(PERFORMANCE_CAVEAT).toBe(
      'Paper trades (simulated fills), gross of commissions and slippage, pre-tax.');
  });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/stat-tile.spec.ts`
Expected: FAIL — the `PERFORMANCE_CAVEAT` import is undefined and `setInput('about', ...)` throws `NG0303`-style "Can't set value of the 'about' input".

- [ ] **Step 3: Implement `about` in `frontend/src/app/ui/stat-tile.ts`**

Imports (`:4`), old `import { Sparkline } from './sparkline';` → new:

```ts
import { Hint } from './hint';
import { Sparkline } from './sparkline';
```

After `export type StatTone = 'neutral' | 'pos' | 'neg';` (`:18`), add:

```ts
/**
 * v194 B8 -- how every performance figure states its basis (spec hint copy
 * rule): paper fills, no costs modelled, before tax. One string, so the Risk
 * and Analytics tiles cannot drift apart.
 */
export const PERFORMANCE_CAVEAT =
  'Paper trades (simulated fills), gross of commissions and slippage, pre-tax.';
```

`:36`, old `  imports: [Sparkline, CountUp],` → new `  imports: [Hint, Sparkline, CountUp],`.

`:40`, old:

```html
      <div class="label sb-label">{{ label() }}</div>
```

new:

```html
      <div class="label-row">
        <div class="label sb-label">{{ label() }}</div>
        @if (about(); as text) { <sb-hint [text]="text" [label]="'About ' + label()" /> }
      </div>
```

Styles, `:94-97`, old `    .label { overflow-wrap: anywhere; }` → new:

```css
    .label { overflow-wrap: anywhere; min-width: 0; }
    /* v194 B8 -- the definition hint sits on the label's line, never under
       the value: the label wraps first, the trigger keeps its size. */
    .label-row { display: flex; align-items: center; gap: var(--space-6, 6px); min-width: 0; }
    .label-row sb-hint { flex: none; }
```

Inputs, `:128`, after `  readonly hint = input<string | undefined>(undefined);` add:

```ts
  /** v194 B8 -- the tile's definition, population and caveat, behind an
   *  `sb-hint` beside the label. `hint` stays the always-visible line. */
  readonly about = input<string | undefined>(undefined);
```

Run the Step 2 command. Expected: PASS.

- [ ] **Step 4: Add the payload field in `frontend/src/app/api/models.ts`**

In `RiskMetrics` (`:1416-1430`), after `  max_drawdown_r: RiskMetric;` add:

```ts
  /** v194 B8: the largest peak-to-trough fall of cumulative realised P&L
   *  over every closed main-ledger trade, oldest close first, in the account
   *  currency (a positive magnitude). `fx_missing_count` trades had no FX
   *  rate for their exit day and are left out of it. Optional: older
   *  payloads and spec fixtures omit it. */
  max_drawdown_amount?: RiskMetric & { fx_missing_count: number };
```

- [ ] **Step 5: Write the failing Risk tests**

In `frontend/src/app/workspaces/risk/risk.spec.ts`: add `import { ConnectionStore } from '../../stores/connection.store';` and change `import { Risk } from './risk';` to:

```ts
import {
  drawdownFxNote, Risk, RISK_DRAWDOWN_LABEL, RISK_SHARPE_LABEL,
} from './risk';
```

Replace the old labels everywhere they occur — `'Sharpe (R)'` → `RISK_SHARPE_LABEL` and `'Max drawdown (R)'` → `RISK_DRAWDOWN_LABEL` — at `:162`, `:173`, `:183`, `:197`, `:216`, `:238`. The test at `:181-184` is renamed and tightened, old:

```ts
  it('labels Sharpe as an R measure so it is not read as annualised', async () => {
    const fixture = await renderWithMetrics();
    expect(tileLabels(fixture)).toContain('Sharpe (R)');
  });
```

new:

```ts
  it('names the basis of Sharpe and max drawdown so neither reads as the Analytics figure', async () => {
    const fixture = await renderWithMetrics();
    const labels = tileLabels(fixture);
    expect(labels).toContain('Sharpe · per-trade R, all closed');
    expect(labels).toContain('Max drawdown · cumulative R, all closed');
    expect(labels).not.toContain('Sharpe (R)');
    expect(labels).not.toContain('Max drawdown (R)');
  });
```

Append a new describe at the end of the file:

```ts
describe('Risk metric basis and money drawdown (v194 B8)', () => {
  it('gives the Sharpe and drawdown tiles a hint with definition, population, N and caveat', async () => {
    const fixture = await renderWithMetrics();
    for (const label of [RISK_SHARPE_LABEL, RISK_DRAWDOWN_LABEL]) {
      const hint = tileHost(fixture, label).querySelector('sb-hint')!;
      expect(hint.querySelector('button')!.getAttribute('aria-label')).toBe(`About ${label}`);
      const text = hint.querySelector('[role="tooltip"]')!.textContent!;
      expect(text).toContain('every closed main-ledger trade, all time');
      expect(text).toContain('N is the closed-trade count');
      expect(text).toContain('Paper trades (simulated fills)');
      expect(text).toContain('gross of commissions and slippage');
      expect(text).toContain('pre-tax');
    }
  });

  it('says the Risk Sharpe is not annualised', async () => {
    const fixture = await renderWithMetrics();
    const text = tileHost(fixture, RISK_SHARPE_LABEL).querySelector('[role="tooltip"]')!.textContent!;
    expect(text).toContain('Not annualised');
  });

  it('shows the money drawdown under the R figure, negative, in the account currency', async () => {
    const fixture = await renderWithMetrics({
      max_drawdown_amount: { value: 412.5, n: 782, fx_missing_count: 0 },
    });
    const tile = tileHost(fixture, RISK_DRAWDOWN_LABEL);
    const secondary = tile.querySelector('.secondary')!.textContent!.trim();
    expect(secondary).toContain('412.50');
    expect(secondary).toMatch(/^[-−]/);
    expect(secondary).toContain(TestBed.inject(ConnectionStore).currency());
    expect(tile.querySelector('div.hint')).toBeNull();
  });

  it('shows no money line when the payload carries none', async () => {
    const fixture = await renderWithMetrics();
    expect(tileHost(fixture, RISK_DRAWDOWN_LABEL).querySelector('.secondary')).toBeNull();
  });

  it('shows no money line for an uncomputable money drawdown', async () => {
    const fixture = await renderWithMetrics({
      max_drawdown_amount: { value: null, n: 0, fx_missing_count: 0 },
    });
    expect(tileHost(fixture, RISK_DRAWDOWN_LABEL).querySelector('.secondary')).toBeNull();
  });

  it('says how many trades the money figure left out for want of an FX rate', async () => {
    const fixture = await renderWithMetrics({
      max_drawdown_amount: { value: 100, n: 779, fx_missing_count: 3 },
    });
    expect(tileHost(fixture, RISK_DRAWDOWN_LABEL).querySelector('div.hint')!.textContent)
      .toContain('3 closed trades without an FX rate for the exit day left out of the amount.');
  });

  it('drops the scope footnote now the labels carry the basis', async () => {
    const fixture = await renderWithMetrics();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.metrics-scope')).toBeNull();
    expect(el.textContent).not.toContain('Sharpe and max drawdown are per-trade R over all closed trades');
  });

  it('words the FX gap note in the singular and is silent at zero', () => {
    expect(drawdownFxNote(0)).toBeUndefined();
    expect(drawdownFxNote(1)).toBe('1 closed trade without an FX rate for the exit day left out of the amount.');
  });
});
```

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/risk/risk.spec.ts`
Expected: FAIL — `drawdownFxNote`, `RISK_SHARPE_LABEL`, `RISK_DRAWDOWN_LABEL` are not exported, so the label lookups throw `no tile labelled "undefined"`.

- [ ] **Step 6: Implement the Risk changes in `frontend/src/app/workspaces/risk/risk.ts`**

Imports: add `money` to the `'../../ui/format'` import (`:22`; V194-7 may already have added `riskPct`/`shareCount` there — keep them, alphabetical order), and `:29` `import { StatTile } from '../../ui/stat-tile';` → `import { PERFORMANCE_CAVEAT, StatTile } from '../../ui/stat-tile';`.

After the last import and before `@Component`, add:

```ts
/* v194 B8 -- Risk and Analytics both show a Sharpe and a max drawdown over
 * different populations. Each label names its basis, so the two never read
 * as one quantity, and the definition sits in the tile's hint. */
export const RISK_SHARPE_LABEL = 'Sharpe · per-trade R, all closed';
export const RISK_DRAWDOWN_LABEL = 'Max drawdown · cumulative R, all closed';
export const RISK_SHARPE_ABOUT =
  'Mean R ÷ standard deviation of R over every closed main-ledger trade, all time. '
  + 'Not annualised: trades have no fixed cadence. Analytics shows an annualised Sharpe '
  + 'for its selected range instead. N is the closed-trade count. ' + PERFORMANCE_CAVEAT;
export const RISK_DRAWDOWN_ABOUT =
  'Largest peak-to-trough fall of cumulative R over every closed main-ledger trade, all time. '
  + 'The amount under it is the largest fall of cumulative realised P&L, oldest close first, '
  + "converted to the account currency at each exit day's FX rate. Analytics shows the fall "
  + 'within its selected range instead. N is the closed-trade count. ' + PERFORMANCE_CAVEAT;

/** The tile's visible note when the money drawdown left trades out for want
 *  of an FX rate; nothing when none were (a missing rate is never read as 1). */
export function drawdownFxNote(missing: number): string | undefined {
  if (!(missing > 0)) return undefined;
  return `${missing} closed trade${missing === 1 ? '' : 's'} without an FX rate for the exit day left out of the amount.`;
}

/** One Risk metric tile, pre-formatted -- `StatTile` never formats. */
interface MetricTile {
  label: string;
  value: string;
  sample: number;
  about?: string;
  secondary?: string | null;
  hint?: string;
}
```

Template, `:171`, old:

```html
            <sb-stat-tile [label]="tile.label" [value]="tile.value" [sample]="tile.sample" />
```

new:

```html
            <sb-stat-tile [label]="tile.label" [value]="tile.value" [sample]="tile.sample"
              [about]="tile.about" [secondary]="tile.secondary ?? null" [hint]="tile.hint" />
```

Delete the footnote, `:173-186` — the comment `<!-- Sharpe and drawdown here are over every closed trade, in R; ... -->` and the whole `<p class="metrics-scope"> ... </p>` — leaving `</sb-stat-strip>` followed directly by `</div>`. Delete the style rule `:571`:

```css
    .metrics-scope { margin: var(--space-10) 0 0; font-size: var(--text-micro); color: var(--text-faint); }
```

After `fmtDrawdownR` (`:735-739`), add:

```ts
  /** The money drawdown under the R figure, negative like it; null (no
   *  line) when the payload has no money figure. */
  private fmtDrawdownMoney(value: number | null): string | null {
    return value === null ? null : money(value === 0 ? 0 : -value, this.connection.currency(), 2);
  }
```

`metricTiles` (`:745-757`), old:

```ts
  protected readonly metricTiles = computed(() => {
    const m = this.store.metrics();
    if (!m) return [];
```

new:

```ts
  protected readonly metricTiles = computed<MetricTile[]>(() => {
    const m = this.store.metrics();
    if (!m) return [];
    const ddAmount = m.max_drawdown_amount;
```

and its last two entries, old:

```ts
      { label: 'Sharpe (R)', value: this.fmtRatio(m.sharpe_r.value), sample: m.sharpe_r.n },
      { label: 'Max drawdown (R)', value: this.fmtDrawdownR(m.max_drawdown_r.value), sample: m.max_drawdown_r.n },
```

new:

```ts
      {
        label: RISK_SHARPE_LABEL, value: this.fmtRatio(m.sharpe_r.value), sample: m.sharpe_r.n,
        about: RISK_SHARPE_ABOUT,
      },
      {
        label: RISK_DRAWDOWN_LABEL, value: this.fmtDrawdownR(m.max_drawdown_r.value),
        sample: m.max_drawdown_r.n, about: RISK_DRAWDOWN_ABOUT,
        secondary: this.fmtDrawdownMoney(ddAmount?.value ?? null),
        hint: drawdownFxNote(ddAmount?.fx_missing_count ?? 0),
      },
```

Run the Step 5 command. Expected: PASS.

- [ ] **Step 7: Close**

Close: standard (test: frontend/src/app/workspaces/risk/risk.spec.ts). Deviation: the narrow run covers both specs — `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/stat-tile.spec.ts --include src/app/workspaces/risk/risk.spec.ts` — then the whole frontend run and lint. Commit `feat(v194): stat-tile about hint; basis-named Sharpe and drawdown, money drawdown on Risk (V194-11)`. Frontend only — one commit.

### Task V194-11b: B8 frontend — basis-named Sharpe / Max drawdown tiles on Analytics, definitions in `about` hints

**Model:** sonnet — label and copy change on one tab, through the `about` input V194-11 added.

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.ts:18` (import), `:23-30` (`KpiTile`), `:79-80` (tile binding), `:276-281` (`kpiTiles`)
- Test: `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts`

**Interfaces:**
- Consumes: `StatTile.about`, `PERFORMANCE_CAVEAT` (V194-11, `frontend/src/app/ui/stat-tile.ts`).
- Produces: `ANALYTICS_SHARPE_LABEL`, `ANALYTICS_DRAWDOWN_LABEL`, `ANALYTICS_SHARPE_ABOUT`, `ANALYTICS_DRAWDOWN_ABOUT` (exported from `overview.ts`); `KpiTile.about?: string`. V194-15 and V194-16 work on this file after it.

The Analytics money drawdown already exists (`drawdownMoney` feeds the tile's `secondary` line); this task keeps it and only renames and explains.

- [ ] **Step 1: Write the failing Analytics tests**

In `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts`, change `import { OverviewTab } from './overview';` to:

```ts
import { ANALYTICS_DRAWDOWN_LABEL, ANALYTICS_SHARPE_LABEL, OverviewTab } from './overview';
```

and append inside `describe('OverviewTab', ...)`:

```ts
  it('names the basis of Sharpe and max drawdown in their labels (v194 B8)', () => {
    const { el } = render();
    const labels = [...el.querySelectorAll('sb-stat-tile .label')].map((n) => n.textContent!.trim());
    expect(labels).toContain('Sharpe · annualised, selected range');
    expect(labels).toContain('Max drawdown · cumulative R, selected range');
    expect(labels).not.toContain('Sharpe');
    expect(labels).not.toContain('Max drawdown');
  });

  it('gives both tiles a hint with definition, population, N and the paper caveat', () => {
    const { el } = render();
    for (const label of [ANALYTICS_SHARPE_LABEL, ANALYTICS_DRAWDOWN_LABEL]) {
      const tile = [...el.querySelectorAll('sb-stat-tile')]
        .find((t) => t.querySelector('.label')?.textContent?.trim() === label)!;
      const hint = tile.querySelector('sb-hint')!;
      expect(hint.querySelector('button')!.getAttribute('aria-label')).toBe(`About ${label}`);
      const text = hint.querySelector('[role="tooltip"]')!.textContent!;
      expect(text).toContain('selected range and filters');
      expect(text).toContain('N is the');
      expect(text).toContain('Paper trades (simulated fills)');
      expect(text).toContain('gross of commissions and slippage');
      expect(text).toContain('pre-tax');
      // The definition moved into the hint: no plain hint line repeats it.
      expect(tile.querySelector('div.hint')).toBeNull();
    }
  });

  it('keeps the money equivalent under the max drawdown tile', () => {
    const { el } = render();
    const tile = [...el.querySelectorAll('sb-stat-tile')]
      .find((t) => t.querySelector('.label')?.textContent?.trim() === ANALYTICS_DRAWDOWN_LABEL)!;
    // cum_pnl 70 -> 40: a 30 fall, in the stubbed '$'.
    const secondary = tile.querySelector('.secondary')!.textContent!;
    expect(secondary).toContain('30');
    expect(secondary).toContain('$');
  });
```

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/analytics/tabs/overview.spec.ts`
Expected: FAIL — `ANALYTICS_SHARPE_LABEL`/`ANALYTICS_DRAWDOWN_LABEL` undefined, labels still "Sharpe" / "Max drawdown".

- [ ] **Step 2: Implement the Analytics changes in `frontend/src/app/workspaces/analytics/tabs/overview.ts`**

`:18`, old `import { StatTile } from '../../../ui/stat-tile';` → new `import { PERFORMANCE_CAVEAT, StatTile } from '../../../ui/stat-tile';`.

After the imports, before `/** One KPI tile's resolved, ...` (`:22`), add:

```ts
/* v194 B8 -- the Risk page shows a Sharpe and a max drawdown over every
 * closed trade; these follow the selected range. The label names the basis,
 * the hint the definition. */
export const ANALYTICS_SHARPE_LABEL = 'Sharpe · annualised, selected range';
export const ANALYTICS_DRAWDOWN_LABEL = 'Max drawdown · cumulative R, selected range';
export const ANALYTICS_SHARPE_ABOUT =
  'Annualised, from the realised returns of closed trades in the selected range and filters. '
  + "Not the Risk page's Sharpe, which is per-trade R over every closed trade and not annualised. "
  + 'N is the sample it was computed from. ' + PERFORMANCE_CAVEAT;
export const ANALYTICS_DRAWDOWN_ABOUT =
  'Largest peak-to-trough fall of the cumulative R curve in the selected range and filters; '
  + 'the amount under it is the largest fall of cumulative realised P&L in the account currency. '
  + 'Risk shows the same measure over every closed trade. N is the number of equity-curve points '
  + 'it was computed from. ' + PERFORMANCE_CAVEAT;
```

`KpiTile` (`:23-30`): after `  hint?: string;` add `  about?: string;`.

Template `:79-80`, old:

```html
      <sb-stat-tile [label]="tile.label" [value]="tile.value" [secondary]="tile.money"
        [sample]="tile.sample" [trend]="tile.trend" [hint]="tile.hint" />
```

new:

```html
      <sb-stat-tile [label]="tile.label" [value]="tile.value" [secondary]="tile.money"
        [sample]="tile.sample" [trend]="tile.trend" [hint]="tile.hint" [about]="tile.about" />
```

`kpiTiles`, `:276-281`, old:

```ts
      tile('Max drawdown', drawdownR === null ? null : -drawdownR, null,
        drawdownMoney === null ? null : -drawdownMoney, equityCurve?.points_n ?? null, null,
        'Largest peak-to-trough decline in the selected range (Risk shows all closed trades).'),
      fixedTile('Sharpe', signed(sharpe, 2), this.store.scopeN(), null,
        'Annualised, from realised returns in the selected range (Risk shows per-trade R, all-time).'),
```

new:

```ts
      {
        ...tile(ANALYTICS_DRAWDOWN_LABEL, drawdownR === null ? null : -drawdownR, null,
          drawdownMoney === null ? null : -drawdownMoney, equityCurve?.points_n ?? null),
        about: ANALYTICS_DRAWDOWN_ABOUT,
      },
      { ...fixedTile(ANALYTICS_SHARPE_LABEL, signed(sharpe, 2), this.store.scopeN()), about: ANALYTICS_SHARPE_ABOUT },
```

Run the Step 1 command. Expected: PASS, including the existing `'shows six KPI tiles, all six labelled'` and `'gives the R-multiple tiles a money line, ...'` (both match by substring, and neither hint text carries `$` or `€`).

- [ ] **Step 3: Close**

Close: standard (test: frontend/src/app/workspaces/analytics/tabs/overview.spec.ts). Commit `feat(v194): basis-named Sharpe and drawdown tiles on Analytics (V194-11b)`.

# Phase B3 — one name for a leg

### Task V194-12: B3 data — `leg_exit_reason` on every `/trades` row

**Model:** sonnet — one row field in three builders, test patterns already in the file.

**Split:** the frontend half (the `TradeRow` field, the shared `legLabel`/`LEG_HINT_TEXT`, Calendar) is V194-12b, so each task stays under the 400-line ceiling. The Interfaces and Decisions below cover both.

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py:362-363` (`_row_from_plan`), `:551` (`_row_from_leg`), `:665-666` (`_row_from_trade`)
- Modify: `tests/admin/test_api_v1_trades.py:94-95` (`TRADE_ROW`), new tests after `test_status_filter_returns_the_closed_leg_and_the_open_remainder_separately` (`:246-261`)

**Interfaces:**
- Consumes: `_runner_exit_reason(leg) -> str | None` (`trades.py:408`: the leg's `reason`, or `"giveback"` when `stop_source == "giveback"`); `reasonLabel(reason) -> string | null` (`frontend/src/app/workspaces/trades/exit-reasons.ts:25`; known codes map through `EXIT_REASON_LABELS`, e.g. `tp1` → `TP1`, `stop` → `Stop`, `runner_trail` → `Runner trailed`; unknown codes come back trimmed; blank → null); `CalendarTrade` (`models.ts`, `leg_index`, `leg_total`, `exit_reason: string`); `Hint` (`frontend/src/app/ui/hint.ts`).
- Produces: leg-row field `leg_exit_reason: str | None` on every `/trades` row (`None` on rows that are not legs, and on a leg with no recorded reason); `TradeRow.leg_exit_reason?: string | null`; `interface LegLike`, `legLabel(row: LegLike): string | null`, `LEG_HINT_TEXT` (all in `frontend/src/app/workspaces/trades/leg-label.ts`). V194-13 renders them on Trades and the Dashboard.

**Decisions.** The reason uses the existing exit-reason vocabulary (`reasonLabel`), so a leg reads "Leg 1 of 2 · TP1", "Leg 2 of 2 · Stop" — the words the trade page already uses. `legLabel` reads `leg_exit_reason` first (a `TradeRow`), then `exit_reason` (a `CalendarTrade`); `TradeRow` has no `exit_reason`, so a Trades leg never borrows the plan's. The reason `other` (Calendar's catch-all) counts as unrecorded: the label stands alone. Calendar's day card keeps the bare "Leg N of M": the exit-reason chip beside it already says the reason, and saying it twice is noise. The drawer line in `calendar.ts` has no chip, so it shows the reason.

- [ ] **Step 1: Write the failing backend tests**

In `tests/admin/test_api_v1_trades.py`, `TRADE_ROW` (`:94-95`), old:

```python
    "leg_index": int,
    "leg_total": int,
```

new:

```python
    "leg_index": int,
    "leg_total": int,
    # v194 B3 -- what closed this leg; None on a row that is not a leg.
    "leg_exit_reason": NULLABLE_STR,
```

Append after `test_status_filter_returns_the_closed_leg_and_the_open_remainder_separately` (`:246-261`):

```python
def _two_leg_plan(pid, *, second_leg):
    plan = _plan(pid, status="CLOSED")
    plan["legs_realized"] = [
        {"fraction": 0.5, "exit_price": 110.0, "r": 1.0, "reason": "tp1",
         "closed_at": "2026-08-02T10:00:00+00:00"},
        {"fraction": 0.5, "exit_price": 101.0, "r": 0.0,
         "closed_at": "2026-08-04T15:00:00+00:00", **second_leg},
    ]
    return plan


def _leg_rows(client, pid):
    items = client.get("/api/v1/trades").get_json()["items"]
    return sorted((r for r in items if r["id"] == pid), key=lambda r: r["leg_index"])


def test_each_leg_row_carries_its_own_recorded_exit_reason(seed, logged_in, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api_v1.trades._attach_current_prices", lambda rows: None)
    pid = "66666666-6666-4666-8666-666666666666"
    seed(plans=[_two_leg_plan(pid, second_leg={"reason": "runner_be"})],
         trades=[_trade("hhhhhhhhhhhhhhhh", plan_id=pid, status="win")])

    legs = _leg_rows(logged_in, pid)
    assert [(r["leg_index"], r["leg_total"]) for r in legs] == [(0, 2), (1, 2)]
    assert [r["leg_exit_reason"] for r in legs] == ["tp1", "runner_be"]


def test_a_give_back_stop_leg_reads_giveback(seed, logged_in, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api_v1.trades._attach_current_prices", lambda rows: None)
    pid = "77777777-7777-4777-8777-777777777777"
    seed(plans=[_two_leg_plan(pid, second_leg={"reason": "runner_trail", "stop_source": "giveback"})],
         trades=[_trade("iiiiiiiiiiiiiiii", plan_id=pid, status="win")])

    assert [r["leg_exit_reason"] for r in _leg_rows(logged_in, pid)] == ["tp1", "giveback"]


def test_a_leg_with_no_recorded_reason_reads_none(seed, logged_in, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api_v1.trades._attach_current_prices", lambda rows: None)
    pid = "88888888-8888-4888-8888-888888888888"
    seed(plans=[_two_leg_plan(pid, second_leg={})],
         trades=[_trade("jjjjjjjjjjjjjjjj", plan_id=pid, status="win")])

    assert [r["leg_exit_reason"] for r in _leg_rows(logged_in, pid)] == ["tp1", None]


def test_rows_that_are_not_legs_carry_no_leg_exit_reason(seed, logged_in, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api_v1.trades._attach_current_prices", lambda rows: None)
    partial = "99999999-9999-4999-8999-999999999999"
    plan = _plan(partial, status="PARTIAL")
    plan["legs_realized"] = [{"fraction": 0.5, "exit_price": 110.0, "r": 1.0,
                              "reason": "tp1", "closed_at": "2026-08-02T10:00:00+00:00"}]
    seed(plans=[plan, _plan("12121212-1212-4121-8121-121212121212", status="PENDING")],
         trades=[_trade("kkkkkkkkkkkkkkkk", plan_id=partial),
                 _trade("llllllllllllllll", status="win")])

    rows = logged_in.get("/api/v1/trades").get_json()["items"]
    remainder = next(r for r in rows if r["id"] == partial and r["status"] == "PARTIAL")
    assert remainder["leg_exit_reason"] is None          # the still-open runner
    pending = next(r for r in rows if r["status"] == "PENDING")
    assert pending["leg_exit_reason"] is None            # a plan that never scaled out
    legacy = next(r for r in rows if r["id"] == "llllllllllllllll")
    assert legacy["leg_exit_reason"] is None             # a legacy trade
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py`
Expected: FAIL — every row-contract check reports `missing key(s) ['leg_exit_reason']`, and the four new tests fail with `KeyError: 'leg_exit_reason'`.

- [ ] **Step 3: Implement the field in `swingbot/admin/api_v1/trades.py`**

`_row_from_plan`, `:362-363`, old:

```python
        "leg_index": 0,
        "leg_total": 1,
```

new (the same edit, once in `_row_from_plan` at `:362-363` and once in `_row_from_trade` at `:665-666`; both blocks read exactly as quoted):

```python
        "leg_index": 0,
        "leg_total": 1,
        # v194 B3 -- set only on a realised leg row (`_row_from_leg`).
        "leg_exit_reason": None,
```

`_row_from_leg`, `:551`, old:

```python
        "leg_index": leg_index,
```

new:

```python
        "leg_index": leg_index,
        # v194 B3 -- what closed THIS leg (legs realise in close order, so
        # leg 1 may be a stop); `giveback` for a v176 give-back stop.
        "leg_exit_reason": _runner_exit_reason(leg),
```

The still-open remainder row is built by `_row_from_plan`, so it keeps `None`. A dict entry adds no branch: `_row_from_plan` (CC 15) and `list_trades` stay as they are.

Run the Step 2 command. Expected: PASS, `0 failed`, `0 xfailed`. Also run the two files that import `TRADE_ROW`: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_detail.py` and `python scripts/dev/testrun.py file tests/admin/test_cohort_api.py` — both green.

- [ ] **Step 4: Close**

Close: standard (test: tests/admin/test_api_v1_trades.py). Commit `feat(v194): leg_exit_reason on leg rows of /trades (V194-12)`. Backend only — one commit.

### Task V194-12b: B3 helper — `TradeRow.leg_exit_reason`; shared `legLabel` and `LEG_HINT_TEXT`; Calendar uses them

**Model:** sonnet — one pure helper and two template swaps, the Interfaces and Decisions of V194-12 apply.

**Files:**
- Modify: `frontend/src/app/api/models.ts:193-197` (`TradeRow`)
- Create: `frontend/src/app/workspaces/trades/leg-label.ts`, `frontend/src/app/workspaces/trades/leg-label.spec.ts`
- Modify: `frontend/src/app/workspaces/calendar/day/day-trade-card.ts:1-18` (imports, local `legLabel` removed), `:40-49` (template), `:132` (`leg`)
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts:1-29` (imports), `:291` (detail drawer leg text)
- Modify (deviation from the ledger, no other task touches it): `frontend/src/app/workspaces/calendar/day/day-trade-card.spec.ts:9`, `:49-52` — it imports the local `legLabel` this task removes.

**Interfaces:** as V194-12's — consumes `leg_exit_reason` (V194-12), `reasonLabel`, `CalendarTrade`, `Hint`; produces `TradeRow.leg_exit_reason?`, `LegLike`, `legLabel`, `LEG_HINT_TEXT` for V194-13.

- [ ] **Step 1: Add the field to `TradeRow` in `frontend/src/app/api/models.ts`**

After `  leg_total: number;` (`:197`, the end of `TradeRow`), add:

```ts
  /** v194 B3: what closed this leg (the stored leg's `reason`, `giveback`
   *  for a v176 give-back stop); null on a row that is not a leg, or a leg
   *  with no recorded reason. Optional: older payloads omit it. */
  leg_exit_reason?: string | null;
```

- [ ] **Step 2: Write the failing helper tests**

Create `frontend/src/app/workspaces/trades/leg-label.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { LEG_HINT_TEXT, legLabel } from './leg-label';

describe('legLabel (v194 B3)', () => {
  it('labels nothing for a trade that never scaled out', () => {
    expect(legLabel({ leg_index: 0, leg_total: 1 })).toBeNull();
    expect(legLabel({ leg_index: 0, leg_total: 1, leg_exit_reason: 'stop' })).toBeNull();
  });

  it('labels each of two legs 1-based, with and without a reason', () => {
    expect(legLabel({ leg_index: 0, leg_total: 2 })).toBe('Leg 1 of 2');
    expect(legLabel({ leg_index: 0, leg_total: 2, leg_exit_reason: 'tp1' })).toBe('Leg 1 of 2 · TP1');
    expect(legLabel({ leg_index: 1, leg_total: 2, leg_exit_reason: 'stop' })).toBe('Leg 2 of 2 · Stop');
  });

  it('labels three legs, the reason in the trade page vocabulary', () => {
    expect(legLabel({ leg_index: 2, leg_total: 3 })).toBe('Leg 3 of 3');
    expect(legLabel({ leg_index: 2, leg_total: 3, leg_exit_reason: 'runner_trail' }))
      .toBe('Leg 3 of 3 · Runner trailed');
  });

  it('keeps an unmapped reason as recorded', () => {
    expect(legLabel({ leg_index: 1, leg_total: 2, leg_exit_reason: 'giveback' })).toBe('Leg 2 of 2 · giveback');
  });

  it('lets the label stand alone when no reason was recorded', () => {
    for (const reason of [null, undefined, '', '  ', 'other']) {
      expect(legLabel({ leg_index: 1, leg_total: 2, leg_exit_reason: reason })).toBe('Leg 2 of 2');
    }
  });

  it("reads a calendar row's exit_reason when there is no leg_exit_reason", () => {
    expect(legLabel({ leg_index: 0, leg_total: 2, exit_reason: 'tp1' })).toBe('Leg 1 of 2 · TP1');
    expect(legLabel({ leg_index: 0, leg_total: 2, exit_reason: 'other' })).toBe('Leg 1 of 2');
  });

  it("prefers the leg's own reason over a row-level one", () => {
    expect(legLabel({ leg_index: 0, leg_total: 2, leg_exit_reason: 'stop', exit_reason: 'tp1' }))
      .toBe('Leg 1 of 2 · Stop');
  });
});

describe('LEG_HINT_TEXT (v194 B3)', () => {
  it('says the rows are one plan, each its share, and that win rate and N count plans', () => {
    expect(LEG_HINT_TEXT).toContain('one plan');
    expect(LEG_HINT_TEXT).toContain("that part's share");
    expect(LEG_HINT_TEXT).toContain('Win rate and N count plans, not legs.');
  });

  it('does not name legs TP1 or Runner, since legs are numbered in close order', () => {
    expect(LEG_HINT_TEXT).not.toMatch(/TP1|Runner/);
    expect(LEG_HINT_TEXT).toContain('in the order they closed');
  });
});
```

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/trades/leg-label.spec.ts`
Expected: FAIL — `Failed to resolve import "./leg-label"`.

- [ ] **Step 3: Create `frontend/src/app/workspaces/trades/leg-label.ts`**

```ts
import { reasonLabel } from './exit-reasons';

/**
 * v194 B3 -- the one name for a scale-out leg, everywhere a leg row renders
 * (Trades table, compact rows and drawer, Dashboard positions, Calendar).
 *
 * "Leg N of M", never "TP1"/"Runner": legs are numbered in the order they
 * realised, so leg 1 may be a stop-out and the last leg may exit at the stop
 * or by timeout. When the leg's own exit reason was recorded it follows the
 * label in the trade page's vocabulary (`reasonLabel`).
 */
export interface LegLike {
  leg_index: number;
  leg_total: number;
  /** A `/trades` leg row's own reason (`TradeRow`). */
  leg_exit_reason?: string | null;
  /** A calendar row's reason (`CalendarTrade`), read when the above is absent. */
  exit_reason?: string | null;
}

/** Calendar's catch-all: not a recorded reason, so the label stands alone. */
const UNRECORDED_REASONS: ReadonlySet<string> = new Set(['other']);

export const LEG_HINT_TEXT =
  'These rows are parts of one plan that scaled out, numbered in the order they closed. '
  + "Each row's P&L is that part's share of the plan's result. "
  + 'Win rate and N count plans, not legs.';

function recordedReason(row: LegLike): string | null {
  const raw = (row.leg_exit_reason ?? row.exit_reason ?? '').trim();
  if (!raw || UNRECORDED_REASONS.has(raw.toLowerCase())) return null;
  return reasonLabel(raw);
}

/** "Leg 2 of 3 · Stop" for a scale-out leg, "Leg 2 of 3" when no reason was
 *  recorded, null for a trade that never scaled out. 1-based. */
export function legLabel(row: LegLike): string | null {
  if (!(row.leg_total > 1)) return null;
  const base = `Leg ${row.leg_index + 1} of ${row.leg_total}`;
  const reason = recordedReason(row);
  return reason ? `${base} · ${reason}` : base;
}
```

Run the Step 2 command. Expected: PASS.

- [ ] **Step 4: Calendar day card — shared label and hint (failing test first)**

In `frontend/src/app/workspaces/calendar/day/day-trade-card.spec.ts`, `:9`, old:

```ts
import { DayTradeCard, heldLabel, legLabel, tradeLinkId } from './day-trade-card';
```

new:

```ts
import { DayTradeCard, heldLabel, tradeLinkId } from './day-trade-card';
import { LEG_HINT_TEXT, legLabel } from '../../trades/leg-label';
```

`:49-52`, old:

```ts
  it('labels a leg 1-based and a whole trade not at all', () => {
    expect(legLabel(TRADE)).toBeNull();
    expect(legLabel({ ...TRADE, leg_index: 1, leg_total: 3 })).toBe('Leg 2 of 3');
  });
```

new:

```ts
  it('labels a leg 1-based and a whole trade not at all', () => {
    expect(legLabel(TRADE)).toBeNull();
    // The shared helper appends a calendar row's exit reason (v194 B3).
    expect(legLabel({ ...TRADE, leg_index: 1, leg_total: 3 })).toBe('Leg 2 of 3 · TP1');
  });
```

Append at the end of the file:

```ts
describe('DayTradeCard leg label (v194 B3)', () => {
  function card(trade: CalendarTrade): HTMLElement {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        { provide: ConnectionStore, useValue: { currency: () => '€' } },
      ],
    });
    const fixture = TestBed.createComponent(DayTradeCard);
    fixture.componentRef.setInput('trade', trade);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('names the leg once, leaving the reason to the chip beside it', () => {
    const el = card({ ...TRADE, leg_index: 1, leg_total: 2 });
    expect(el.querySelector('.leg')!.textContent!.trim()).toBe('Leg 2 of 2');
  });

  it('explains leg rows with a hint that says win rate and N count plans', () => {
    const el = card({ ...TRADE, leg_index: 0, leg_total: 2 });
    const hint = el.querySelector('.leg + sb-hint')!;
    expect(hint.querySelector('button')!.getAttribute('aria-label')).toBe('About leg rows');
    expect(hint.querySelector('[role="tooltip"]')!.textContent).toContain(LEG_HINT_TEXT);
  });

  it('shows neither label nor leg hint for a trade that never scaled out', () => {
    const el = card(TRADE);
    expect(el.querySelector('.leg')).toBeNull();
    expect(el.querySelector('.leg + sb-hint')).toBeNull();
  });
});
```

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/calendar/day/day-trade-card.spec.ts`
Expected: FAIL — the leg-hint test finds no `.leg + sb-hint`.

- [ ] **Step 5: Implement the day card in `frontend/src/app/workspaces/calendar/day/day-trade-card.ts`**

Imports: add

```ts
import { Hint } from '../../../ui/hint';
import { LEG_HINT_TEXT, legLabel } from '../../trades/leg-label';
```

Delete the local helper, `:14-18`:

```ts
/** "Leg 2 of 3" for a scale-out leg, null for a whole trade. 1-based, like
 *  the drawer. */
export function legLabel(trade: CalendarTrade): string | null {
  return trade.leg_total > 1 ? `Leg ${trade.leg_index + 1} of ${trade.leg_total}` : null;
}
```

(`git grep -n "legLabel" frontend/src` lists only this file and its spec, so nothing else imports it.)

Component `imports` (`:40`), old `  imports: [Chip, RouterLink, TradeSparkline],` → new `  imports: [Chip, Hint, RouterLink, TradeSparkline],`.

Template `:48-50`, old:

```html
        @if (leg(); as label) {
          <span class="leg">{{ label }}</span>
        }
```

new:

```html
        @if (leg(); as label) {
          <span class="leg">{{ label }}</span>
          <sb-hint [text]="legHint" label="About leg rows" />
        }
```

Class, `:132`, old:

```ts
  protected readonly leg = computed(() => legLabel(this.trade()));
```

new:

```ts
  /** Bare "Leg N of M": the exit-reason chip beside it already names the
   *  reason, so the shared label is built without one. */
  protected readonly leg = computed(() =>
    legLabel({ leg_index: this.trade().leg_index, leg_total: this.trade().leg_total }));
  protected readonly legHint = LEG_HINT_TEXT;
```

Run the Step 4 command. Expected: PASS.

- [ ] **Step 6: Calendar drawer line in `frontend/src/app/workspaces/calendar/calendar.ts`**

Imports: add

```ts
import { Hint } from '../../ui/hint';
import { LEG_HINT_TEXT, legLabel } from '../trades/leg-label';
```

Component `imports` (`:29`), old:

```ts
  imports: [Button, ControlRow, Drawer, Panel, RouterLink, SectionHead, Select, StatStrip, StatTile, Async],
```

new:

```ts
  imports: [Button, ControlRow, Drawer, Hint, Panel, RouterLink, SectionHead, Select, StatStrip, StatTile, Async],
```

Template `:291`, old:

```html
              @if (trade.leg_total > 1) { <span class="leg">Leg {{ trade.leg_index + 1 }} of {{ trade.leg_total }}</span> · }
```

new:

```html
              @if (legLabel(trade); as leg) {
                <span class="leg">{{ leg }}</span> <sb-hint [text]="legHint" label="About leg rows" /> ·
              }
```

In the class, beside `protected readonly currency = computed(...)` (`:489`), add:

```ts
  /** v194 B3 -- the one leg name (shared with Trades and the Dashboard). */
  protected readonly legLabel = legLabel;
  protected readonly legHint = LEG_HINT_TEXT;
```

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/calendar/calendar.spec.ts`
Expected: PASS — `'lists both legs of a scaled-out trade closed that day, each labelled'` (`calendar.spec.ts:383-394`) checks `.leg` with `toContain('Leg 1 of 2')` / `toContain('Leg 2 of 2')`, which the reason suffix keeps true, and `'does not label an unsplit trade as a leg'` still finds no `.leg`.

- [ ] **Step 7: Close**

Close: standard (test: frontend/src/app/workspaces/trades/leg-label.spec.ts). Deviation: the narrow run covers `--include src/app/workspaces/trades/leg-label.spec.ts --include src/app/workspaces/calendar/day/day-trade-card.spec.ts --include src/app/workspaces/calendar/calendar.spec.ts`, then the whole frontend run and lint. Commit `feat(v194): shared leg label and leg hint, Calendar uses them (V194-12b)`, adding `day-trade-card.spec.ts` by name with the ledger's files.

