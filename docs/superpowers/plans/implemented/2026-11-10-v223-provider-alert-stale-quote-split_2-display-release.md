# v223 Provider alert counts only real Alpaca failures — Part 2: display and release

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [2026-11-10-v223-provider-alert-stale-quote-split-design.md](../specs/2026-11-10-v223-provider-alert-stale-quote-split-design.md)
**Index:** [2026-11-10-v223-provider-alert-stale-quote-split_0-index.md](2026-11-10-v223-provider-alert-stale-quote-split_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there.

# Phase 2 — Telemetry and display (continued)

### Task V223-5: System-health key and Risk pooled-rate docstring

**Model:** sonnet — an admin endpoint key and a pinned pooled-rate test, inside one package

**Files:**
- Modify: `swingbot/admin/api_v1/ops_health.py:42-43` (`_PROVIDER_KEYS`)
- Modify: `swingbot/admin/api_v1/risk.py:51-57` (`_data_sources_summary` docstring)
- Test: `tests/admin/test_api_v1_ops_health.py`, `tests/admin/test_api_v1_risk.py` (suite `admin`)

**Interfaces:**
- Consumes: the telemetry row field name `old_print_rate` (V223-4's contract;
  these tests write raw rows, so V223-4 need not be merged first).
- Produces: every provider row of `GET /api/v1/system/health` carries
  `old_print_rate` (number or null), consumed by V223-6's
  `ProviderHealthRow.old_print_rate`.

Spec items 8 and 9 (first bullet). `_provider_rows` already reads
`row.get(key)`, so a pre-v223 row reads `None` with no upcasting. `risk.py`
pools `price_sources` through `telemetry.fallback_rate`, whose formula never
counted `yfinance-old-print`, so its code does not change. Only its stated
meaning does. For one window after deploy the pooled rate mixes pre-v223 rows
(old prints counted as fallback) with post-v223 rows, and reads as a falling
rate. That is expected.

These tests log in through the admin app. If the `admin` suite reaches the
local Postgres on this machine, run `/replicate-prod-db` first (shared
`swing-db` container, port 56789, `.env` credentials never printed).

- [ ] **Step 1: Update the key-set tests and write the failing tests**

In `tests/admin/test_api_v1_ops_health.py`, add the field to the contract
shape `_PROVIDER_ROW` (around L19):

```python
_PROVIDER_ROW = {
    "at": str,
    "tickers": NUMBER,
    "provider_fallback_rate": NULLABLE_NUMBER,
    "old_print_rate": NULLABLE_NUMBER,
    "stale_symbols": NULLABLE_NUMBER,
    "empty_symbols": NULLABLE_NUMBER,
    "empty_rate": NULLABLE_NUMBER,
}
```

In `test_a_pre_v148_row_reads_as_null_and_deploy_markers_are_skipped`
(around L163), replace the exact-dict assertion with:

```python
    assert rows[1] == {"at": "2026-10-09T14:01:00+00:00", "tickers": 150,
                       "provider_fallback_rate": None, "old_print_rate": None,
                       "stale_symbols": None, "empty_symbols": None, "empty_rate": None}
```

Append to the same file:

```python
def test_the_old_print_rate_is_carried_and_a_pre_v223_row_reads_null(logged_in, telemetry_rows):
    telemetry_rows(
        _scan_row(1, provider_fallback_rate=0.02, stale_symbols=0,
                  empty_symbols=0, empty_rate=0.0),                       # pre-v223
        _scan_row(2, provider_fallback_rate=0.0, old_print_rate=0.9195, stale_symbols=0,
                  empty_symbols=1, empty_rate=0.0067),
    )

    rows = _health(logged_in)["providers"]

    assert [r["old_print_rate"] for r in rows] == [0.9195, None]
    for row in rows:
        assert_shape(row, _PROVIDER_ROW, where="provider row")
```

In `tests/admin/test_api_v1_risk.py`, append after
`test_fallback_rate_pools_daily_frames_and_live_prices`:

```python
def test_the_pooled_fallback_rate_excludes_old_prints(logged_in, tmp_path, monkeypatch):
    """v223: an old IEX print outside regular hours is neither an Alpaca hit
    nor a failure, so 80 old prints leave the pooled rate at 1 / 10."""
    from swingbot.core.scanning import engine
    from swingbot.core.scanning import telemetry

    monkeypatch.setattr(telemetry, "TELEMETRY_PATH", str(tmp_path / "scan_telemetry.jsonl"))
    engine.log_scan_telemetry({"duration_s": 60, "tickers": 150,
        "data_sources": {"alpaca": 2, "yfinance": 0, "yfinance-fallback": 0, "cache": 70},
        "price_sources": {"alpaca": 7, "yfinance": 2, "yfinance-fallback": 1,
                          "yfinance-old-print": 80, "none": 0}})
    ds = logged_in.get("/api/v1/risk").get_json()["scan_health"]["data_sources"]
    assert ds["fallback_rate"] == pytest.approx(1 / 10)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_ops_health.py`
Expected: FAIL — `old_print_rate` missing from every provider row.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py`
Expected: PASS already for the new risk test (the formula never counted the
new key). It is the regression pin for spec item 8, so keep it.

- [ ] **Step 3: Add the key**

In `swingbot/admin/api_v1/ops_health.py`, replace L42-43:

```python
_PROVIDER_KEYS = ("at", "tickers", "provider_fallback_rate", "old_print_rate",
                  "stale_symbols", "empty_symbols", "empty_rate")
```

- [ ] **Step 4: State the v223 meaning in the Risk docstring**

In `swingbot/admin/api_v1/risk.py`, replace the first paragraph of the
`_data_sources_summary` docstring (L51-57) with:

```python
    """v106: which provider is live and how often Alpaca misses. The rate is
    yfinance-fallback over everything Alpaca was asked for (hits + misses),
    daily frames and live-price answers pooled, across the last
    `_DATA_SOURCE_WINDOW` scans that logged `data_sources`;
    None when none of them asked Alpaca for anything. The formula is
    telemetry.fallback_rate, shared with each scan's provider_fallback_rate
    (v148 O4). From v223 on, old IEX prints outside regular hours
    (yfinance-old-print) are excluded -- for one window after that deploy the
    pool mixes rows that still counted them as fallback, so the rate falls.
```

(Keep the `breaker_open` paragraph and the closing `"""` that follow.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_ops_health.py`
Expected: PASS, 0 failed.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py`
Expected: PASS, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add swingbot/admin/api_v1/ops_health.py tests/admin/test_api_v1_ops_health.py
git commit -m "feat(v223): system health provider rows carry old_print_rate (null before v223)"
git add swingbot/admin/api_v1/risk.py tests/admin/test_api_v1_risk.py
git commit -m "docs(v223): Risk pooled fallback rate excludes old prints from v223 on; pinned by a test"
```

# Phase 3 — Admin SPA

### Task V223-6: Provider health panel "Old prints" column

**Model:** sonnet — one Angular panel plus its model, the three-width UI check included

**Files:**
- Modify: `frontend/src/app/api/models.ts:1436-1440` (`Ticker.price_source` union + comment), `:1568-1570` (`DataSourcesHealth` docstring), `:1828-1845` (`ProviderHealthRow`)
- Modify: `frontend/src/app/workspaces/system/provider-health-panel.ts`
- Test: `frontend/src/app/workspaces/system/provider-health-panel.spec.ts`, `frontend/src/app/stores/system.store.spec.ts`

**Interfaces:**
- Consumes: `GET /api/v1/system/health` provider rows carrying
  `old_print_rate` (V223-5's contract; the panel treats it as optional, so
  it does not wait for V223-5).
- Produces: `ProviderHealthRow.old_print_rate?: number | null`;
  `ProviderHealthLine.oldPrint: string`; the `Ticker.price_source` union
  `'alpaca' | 'yfinance' | 'yfinance-fallback' | 'yfinance-old-print' | null`
  (consumed by V223-7).

Spec item 9, second bullet, and item 10's TS union. The panel is a table with
one row per scan; it gains one **column**, "Old prints", with a header hint
"Old IEX prints re-asked from yfinance, share of live-price asks" and "—" for
None or a missing field. The field is **optional** on `ProviderHealthRow`,
so the typed fixtures in `providers-tab.spec.ts` and other specs still
compile unchanged. `models.ts:1006` (`price_source: string` on an
override-fidelity row) is unrelated and must not be touched.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/workspaces/system/provider-health-panel.spec.ts`, give the
first `HEALTH` row a value and leave the other two without one (the third
stays a pre-v148 row with no field at all):

```ts
const HEALTH: SystemHealth = {
  providers: [
    { ...ROW, at: '2026-10-09T14:10:00+00:00', provider_fallback_rate: 0.25,
      empty_symbols: 12, empty_rate: 0.08, old_print_rate: 0.42 },
    { ...ROW, old_print_rate: null },
    { at: '2026-10-09T14:00:00+00:00', tickers: 150, provider_fallback_rate: null,
      stale_symbols: null, empty_symbols: null, empty_rate: null },
  ],
  thresholds: { fallback_pct: 20, empty_pct: 5 },
  notifications: null,
  swallowed: [],
  bot_counts_since: null,
};
```

Add to the `provider health formatting` describe block:

```ts
  it('renders the old-print rate, and a dash when it is null or missing (v223)', () => {
    const lines = providerLines(HEALTH);

    expect(lines[0].oldPrint).toBe('42.0%');
    expect(lines[1].oldPrint).toBe('—');
    expect(lines[2].oldPrint).toBe('—');
  });
```

Add to the `ProviderHealthPanel` describe block:

```ts
  it('shows an Old prints column with its own hint and no breach mark (v223)', () => {
    const el = render(HEALTH);
    const headers = [...el.querySelectorAll('thead th')].map((th) => th.textContent ?? '');
    const oldHeader = el.querySelectorAll('thead th')[3];

    expect(headers).toHaveLength(6);
    expect(headers[3]).toContain('Old prints');
    expect(oldHeader.querySelector('[role="tooltip"]')!.textContent!.trim())
      .toBe('Old IEX prints re-asked from yfinance, share of live-price asks');
    const firstRow = el.querySelectorAll('tbody tr')[0].querySelectorAll('td');
    expect(firstRow).toHaveLength(6);
    expect(firstRow[3].textContent!.trim()).toBe('42.0%');
    expect(firstRow[3].classList.contains('breach')).toBe(false);
    expect(el.querySelectorAll('tbody tr')[2].querySelectorAll('td')[3].textContent!.trim()).toBe('—');
  });

  it('says the old-print rate is shown, not alerted on', () => {
    expect(render(HEALTH).querySelector('.explain')!.textContent)
      .toContain('share of live-price asks; it is shown here, not alerted on');
  });
```

The existing `renders one row per scan` (3 rows) and `marks a breach with
text as well as colour` (2 breach cells) tests must keep passing as they are.

In `frontend/src/app/stores/system.store.spec.ts`, add the field to the
`HEALTH` literal's provider row (around L120-130):

```ts
    {
      at: '2026-10-09T14:05:00+00:00',
      tickers: 150,
      provider_fallback_rate: 0.04,
      old_print_rate: 0.92,
      stale_symbols: 0,
      empty_symbols: 2,
      empty_rate: 0.0133,
    },
```

and add, directly after the `resolves health with the Providers tab ...` test:

```ts
  it('carries the old-print rate through from the health answer (v223)', () => {
    store.resolveProviders().subscribe();
    backend.expectOne('/api/v1/system/health').flush(HEALTH);
    backend.expectOne('/api/v1/risk').flush({});

    expect(store.health()!.providers[0].old_print_rate).toBe(0.92);
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend test -- --include src/app/workspaces/system/provider-health-panel.spec.ts`
Expected: FAIL — TS error `old_print_rate` does not exist on `ProviderHealthRow`
(or `oldPrint` undefined, 5 headers instead of 6).

- [ ] **Step 3: Update `models.ts`**

Replace the `price_source` member and its comment (L1436-1440):

```ts
  /** v106 -- which provider served `price` when it is the live overlay;
   *  null when `price` is the cached close. Only the yfinance answers for an
   *  Alpaca-eligible symbol are flagged in the table: `yfinance-fallback`
   *  (Alpaca missed) and, from v223, `yfinance-old-print` (Alpaca's last IEX
   *  trade was too old outside regular hours). */
  price_source?: 'alpaca' | 'yfinance' | 'yfinance-fallback' | 'yfinance-old-print' | null;
```

Replace the `DataSourcesHealth` docstring (L1568-1570):

```ts
/** v106 -- the live data provider and how often Alpaca misses.
 *  `fallback_rate` is yfinance-fallback over everything Alpaca was asked for
 *  across the last `scans` scans that logged it; null when none did. From
 *  v223 on, old IEX prints outside regular hours are excluded. */
```

Replace `ProviderHealthRow` (L1828-1845):

```ts
/** One scheduled scan's provider figures, from `GET /system/health`.
 *  Rates are fractions (0.05 = 5%). The figures are null on a row written
 *  before v148 (`old_print_rate`: before v223) -- render "—", never 0. */
export interface ProviderHealthRow {
  at: string;
  tickers: number;
  /** yfinance-fallback / (alpaca + yfinance-fallback), daily frames and live
   *  prices pooled; null when Alpaca was asked for nothing. From v223 on,
   *  old IEX prints outside regular hours are excluded. */
  provider_fallback_rate: number | null;
  /** v223: old IEX prints re-asked from yfinance, as a share of live-price
   *  asks only (not the fallback rate's wider pool). Display only: no alert
   *  reads it. Optional: older rows and fixtures do not carry it. */
  old_print_rate?: number | null;
  /** Frames whose last bar is before the previous NYSE session. Display
   *  only: no alert reads it. */
  stale_symbols: number | null;
  empty_symbols: number | null;
  empty_rate: number | null;
}
```

- [ ] **Step 4: Add the column to the panel**

In `provider-health-panel.ts`:

Import the hint next to `Panel`:

```ts
import { Hint } from '../../ui/hint';
import { Panel } from '../../ui/layout';
```

Add the header text as an exported constant below `isKnown`:

```ts
/** v223: the "Old prints" column's header hint. */
export const OLD_PRINT_HINT = 'Old IEX prints re-asked from yfinance, share of live-price asks';
```

Add `oldPrint: string;` to `ProviderHealthLine` after `emptyBreach`, and in
`providerLines` add after `emptyBreach: ...`:

```ts
    oldPrint: rateText(row.old_print_rate),
```

Set `imports: [Panel, Hint],`. In the template, replace the explain paragraph's
second sentence line with these two lines:

```html
        Stale counts frames whose last bar is older than the previous NYSE session; it is shown here, not alerted on.
        Old prints are old IEX prints outside regular hours re-asked from yfinance, as a share of live-price asks; it is shown here, not alerted on.
```

Insert the header cell between `Empty` and `Stale`:

```html
                <th scope="col" class="right">Old prints<sb-hint [text]="oldPrintHint" label="About old prints" align="left" /></th>
```

and the body cell between the `empty` and `stale` cells:

```html
                  <td class="num right">{{ line.oldPrint }}</td>
```

Add to the class:

```ts
  protected readonly oldPrintHint = OLD_PRINT_HINT;
```

The existing `.scroll { overflow-x: auto; }` wrapper and `white-space: nowrap`
cells are the table's responsive rule: at phone width the six columns scroll
horizontally inside the panel, as the five did. No new breakpoint.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npm --prefix frontend test -- --include src/app/workspaces/system/provider-health-panel.spec.ts`
Expected: PASS.

Run: `npm --prefix frontend test -- --include src/app/stores/system.store.spec.ts`
Expected: PASS.

Run: `npm --prefix frontend test -- --include src/app/workspaces/system/providers-tab.spec.ts`
Expected: PASS (its fixture has no `old_print_rate`; the field is optional).

- [ ] **Step 6: Check the panel at three widths**

Build the SPA and drive it with Playwright (never claude-in-chrome), logging
in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and
never printed. Use the stale-bundle workaround from memory "Layout audit stale
bundle": copy `frontend/dist` into `static/app` and block the service worker.
Open System → Providers at 390, 768 and 1280 px wide. Check that:
- the "Old prints" header and its hint trigger sit on one line;
- the hint opens inside the viewport when tapped at 390 px;
- at 390 px the table scrolls sideways inside the panel and the page itself
  does not scroll sideways;
- pre-v223 rows read "—".

Save the screenshots to the scratchpad and report their paths. Do not commit them.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/api/models.ts
git commit -m "feat(ui/v223): ProviderHealthRow.old_print_rate (optional), price_source union adds yfinance-old-print"
git add frontend/src/app/workspaces/system/provider-health-panel.ts frontend/src/app/workspaces/system/provider-health-panel.spec.ts frontend/src/app/stores/system.store.spec.ts
git commit -m "feat(ui/v223): Provider health panel Old prints column, share of live-price asks"
```

### Task V223-7: Watchlist badge tooltip for old prints

**Model:** sonnet — a copied template pattern, but it closes with a Playwright check at three widths

**Files:**
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts:178-179` (hint constants), `:467-471` (price cell), `:596` (class fields)
- Test: `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`

**Interfaces:**
- Consumes: the `Ticker.price_source` union containing `'yfinance-old-print'`
  (V223-6, `models.ts`). `swingbot/admin/watchlist_rows.py:306` already passes
  `router.last_source(symbol)` through as `price_source`, so there is no
  Python change.
- Produces: `export const WATCHLIST_OLD_PRINT_HINT` in `watchlist.ts`.

Spec item 10. Both tags show the same "fallback" badge, so pre-market and
after-hours rows keep the badge they show today. `yfinance-fallback` keeps
`WATCHLIST_FALLBACK_HINT` verbatim (pinned by the existing v194 A3 test).
`yfinance-old-print` gets its own hint text:
"Alpaca's last IEX trade is older than 5 minutes outside regular hours, so this price comes from yfinance's extended-hours data."

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`, extend the
import at L24:

```ts
import { compareTickers, isWithinCurrentWeek, Watchlist, WATCHLIST_COLUMNS, WATCHLIST_FALLBACK_HINT, WATCHLIST_OLD_PRINT_HINT } from './watchlist';
```

Add inside `describe('fallback price badge (v194 A3)', ...)`, after the first test:

```ts
  it('shows the same badge for an old IEX print, with its own hint (v223)', () => {
    const r = firstRow({ price_source: 'yfinance-old-print' });
    const badge = r.querySelector('.source-badge')!;
    expect(badge.textContent!.trim()).toBe('fallback');
    expect(badge.nextElementSibling!.querySelector('[role="tooltip"]')!.textContent!.trim())
      .toBe(WATCHLIST_OLD_PRINT_HINT);
  });

  it('keeps the two hints apart (v223)', () => {
    expect(WATCHLIST_OLD_PRINT_HINT).toBe(
      "Alpaca's last IEX trade is older than 5 minutes outside regular hours, so this price comes from yfinance's extended-hours data.");
    expect(WATCHLIST_FALLBACK_HINT).toBe('Alpaca missed this quote; yfinance answered instead.');
  });

  it('shows neither badge nor hint for a plain yfinance price', () => {
    expect(firstRow({ price_source: 'yfinance' }).querySelector('.source-badge')).toBeNull();
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend test -- --include src/app/workspaces/watchlist/watchlist.spec.ts`
Expected: FAIL — `WATCHLIST_OLD_PRINT_HINT` is not exported.

- [ ] **Step 3: Implement**

In `watchlist.ts`, below `WATCHLIST_FALLBACK_HINT` (L179) add:

```ts
/** v223: the same badge when Alpaca's last IEX trade was too old outside
 *  regular hours and yfinance's extended-hours price was used on purpose. */
export const WATCHLIST_OLD_PRINT_HINT =
  "Alpaca's last IEX trade is older than 5 minutes outside regular hours, so this price comes from yfinance's extended-hours data.";
```

Replace the comment and `@if` block in the price cell (L467-471):

```html
        <!-- v106: only the exception is flagged -- Alpaca missed and yfinance
             answered. v223: an old IEX print outside regular hours shows the
             same badge with its own hint. An Alpaca or plain-yfinance price
             stays quiet. -->
        @if (row.price_source === 'yfinance-fallback') {
          <span class="source-badge">fallback</span><sb-hint [text]="fallbackHint" label="About fallback prices" align="left" />
        } @else if (row.price_source === 'yfinance-old-print') {
          <span class="source-badge">fallback</span><sb-hint [text]="oldPrintHint" label="About old-print prices" align="left" />
        }
```

Below `protected readonly fallbackHint = WATCHLIST_FALLBACK_HINT;` (L596) add:

```ts
  protected readonly oldPrintHint = WATCHLIST_OLD_PRINT_HINT;
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix frontend test -- --include src/app/workspaces/watchlist/watchlist.spec.ts`
Expected: PASS, including the unchanged v194 A3 tests.

- [ ] **Step 5: Check the hint at three widths**

Drive the built SPA with Playwright (setup as in V223-6 Step 6: `.env` login
loaded in the script and never printed; dist copied to `static/app`; service
worker blocked). Open the Watchlist at 390, 768 and 1280 px. A row with
`price_source: 'yfinance-old-print'` will not exist locally, so stub the
watchlist API response with Playwright's `page.route` and set one row's
`price_source` to `'yfinance-old-print'`. Open its hint by tap or click at
each width and check that:
- the longer text wraps inside the popover;
- the popover stays inside the viewport;
- the badge stays on the price line.

Save the screenshots to the scratchpad and report their paths. Do not commit them.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/watchlist/watchlist.ts frontend/src/app/workspaces/watchlist/watchlist.spec.ts
git commit -m "feat(ui/v223): watchlist fallback badge on old IEX prints, with its own hint"
```

# Phase 4 — Release

### Task V223-8: Release, pipeline watch, production acceptance

**Model:** sonnet — mechanical release steps, then reading CI failures and production telemetry

**Files:**
- Modify: `VERSION.json` (bot patch, ui patch, both `*_updated` stamps)
- Modify: `swingbot/admin/version_history.json` (regenerated, never hand-edited)
- Scratchpad only: `<scratchpad>/v223-telemetry.jsonl`, `<scratchpad>/v223_acceptance.py`

**Interfaces:**
- Consumes: every earlier task merged into the worktree branch, each green on
  its narrow run.
- Produces: nothing for later tasks.

No task in this plan runs the full suite. CI runs it after the push
(`working-conventions.md` § Pipeline watch).

- [ ] **Step 1: Bump the versions (resolved now, not before)**

Read `VERSION.json` at this moment; do not assume the 2026-11-06 values,
because another plan may have released since. Increment the **bot** patch
(e.g. `2.17.3` -> `2.17.4`), set `bot_updated` to the current UTC time as
`YYYY-MM-DD HH-MM-SS` (Git Bash: `date -u +"%Y-%m-%d %H-%M-%S"`), and commit:

```bash
git add VERSION.json
git commit -m "release(bot): <new bot version> -- provider alert counts only real Alpaca failures; old IEX prints tagged apart (v223)"
```

Then increment the **ui** patch, set `ui_updated` the same way, and commit:

```bash
git add VERSION.json
git commit -m "release(ui): <new ui version> -- Provider health Old prints column, watchlist old-print hint (v223)"
```

- [ ] **Step 2: Regenerate the version history (after the bump commits)**

Run: `python scripts/dev/build_version_matrix.py`

Run: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
Expected: PASS (the committed file's `current` pair equals `VERSION.json`).

```bash
git add swingbot/admin/version_history.json
git commit -m "chore(bot,ui): <bot version> / <ui version> -- provider alert counts only real Alpaca failures, old-print display (v223)"
```

- [ ] **Step 3: Narrow pre-push check of what the branch touched**

Run: `python scripts/dev/testrun.py changed --dry-run`, then
`python scripts/dev/testrun.py changed`.
Expected: 0 failed, 0 xfailed. If it widens to the full suite, stop it and run
only the files this plan named (V223-1..V223-7 test files, one
`testrun.py file` each). The full run belongs to CI.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 4: Merge and push, then watch the pipeline**

The controller merges the worktree branch into `main` following
`worktree-lifecycle` (check for concurrent sessions first) and pushes. Then:

```bash
gh run list --branch main --limit 1 --json databaseId,status,conclusion
gh run watch <id> --exit-status
```

Run `gh run watch` in the background (`run_in_background`).
- Green: continue to Step 5. The deploy follows by itself.
- Red: `gh run view <id> --log-failed > <scratchpad>/v223-ci.log`. Read only
  the failing test names and their assertion lines. Fix each failure, re-run
  it alone with `testrun.py file ...`, commit the fix scoped, push, and watch
  the new run.
- A deploy-job failure touches production: stop and tell the partner. Do not retry.

- [ ] **Step 5: Production acceptance (read-only, first weekday after deploy)**

Standing permission covers read-only production access through
`scripts/ops/ssh-hetzner.sh`. Nothing on the VM is changed. If the deploy
landed after 22:00 UTC on a Friday or at the weekend, schedule this step for
the next weekday and record that in the index's `## Handoff`.

Fetch the day's telemetry rows:

```bash
bash scripts/ops/ssh-hetzner.sh "tail -n 600 /opt/swing-bot/data/scan_telemetry.jsonl" > "<scratchpad>/v223-telemetry.jsonl"
```

Write `<scratchpad>/v223_acceptance.py`:

```python
"""v223 acceptance: per window, the provider fields of each scan row."""
import json
import sys
from datetime import datetime

day = sys.argv[2]                          # YYYY-MM-DD, the weekday checked (UTC)
WINDOWS = {"pre-market": ("09:00", "14:30"), "regular": ("14:30", "21:00"),
           "after-hours": ("21:00", "22:00")}


def window(at: str):
    t = at[11:16]
    return next((name for name, (lo, hi) in WINDOWS.items() if lo <= t < hi), None)


rows = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
for row in rows:
    at = str(row.get("at", ""))
    if row.get("type") == "deploy" or not at.startswith(day) or window(at) is None:
        continue
    fb, op, er = row.get("provider_fallback_rate"), row.get("old_print_rate"), row.get("empty_rate")
    alerts = (fb is not None and fb > 0.20) or (er is not None and er > 0.05)
    print(f"{at[11:19]} {window(at):<11} fallback={fb} old_print={op} empty={er}"
          f"{'  ALERT' if alerts else ''}")
```

Run: `python "<scratchpad>/v223_acceptance.py" "<scratchpad>/v223-telemetry.jsonl" <YYYY-MM-DD>`

Then check that no alert went out in the windows:

```bash
bash scripts/ops/ssh-hetzner.sh "grep -h 'provider degraded\|provider_health' /opt/swing-bot/logs/*.log | grep '<YYYY-MM-DD>' | tail -n 20"
```

Pass when all of these hold (spec § Acceptance):
- no `ALERT` row and no "market-data provider degraded" post between 09:00
  and 14:30 UTC or between 21:00 and 22:00 UTC;
- those rows show `provider_fallback_rate` near 0 and `old_print_rate` high;
- `regular` rows show `old_print_rate` 0 (or None when Alpaca was asked
  nothing).

Ask the partner (`AskUserQuestion`) to confirm the ops channel stayed quiet
in those windows. The Discord channel is the final word; the log grep only
supports it.

Record the verdict in the hand-off to the controller: the per-window row
counts, the maximum `provider_fallback_rate`, the median `old_print_rate`, and
pass or fail. A fail is a finding for the partner. It never triggers a
production change from this task; any change goes through `mirror-prod`.

- [ ] **Step 6: Close-out**

Once every task is merged and the pipeline is green, the controller runs
`/close-out` (standing permission). Close-out moves these plan files to
`implemented/` and removes the worktree. It also checks whether a skill or
agent cites what changed. `alert-surface` and `docs/claude/known-traps.md`
mention the provider alert and `yfinance-fallback`; align them in the same
close-out (Step 5b) if they state that every miss is a failure.

