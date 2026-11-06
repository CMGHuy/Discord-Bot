# v217 — Admin Part 3: fewer heavy requests per page — Part 1: evidence and the two server fields

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v206 — Admin under load](../specs/2026-11-05-v206-admin-under-load-design.md) § Plan 2; P3 authority [v205 — Admin read performance](../specs/2026-11-04-v205-admin-read-performance-design.md) § Part 3.
**Index:** [`2026-11-06-v217-admin-part3-heavy-requests_0-index.md`](2026-11-06-v217-admin-part3-heavy-requests_0-index.md). Goal, architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there; every task below implicitly includes the Global Constraints.

All paths are relative to the worktree `.claude/worktrees/2026-11-06-v217-admin-part3-heavy-requests` (branch of the same name). Never edit the main tree from a task. Commit inside the worktree only.

# Phase A — Boot merge evidence

### Task V217-1: Boot `/trades` merge: evidence specs, record the verdict

**Model:** sonnet — two component specs plus a spec-section write-up; reasoning over existing behaviour, no production code.

**Premise correction (found while writing this task, checked with `git grep`).** The brief and the index count **three** boot `/trades` calls, the third from `sb-exposure-by-horizon`. That panel is **not mounted anywhere**: no template outside its own file names `sb-exposure-by-horizon`, `dashboard.spec.ts` already asserts `el.querySelector('sb-exposure-by-horizon')` is `null` ("keeps the dashboard focused…"), and `git log -S "sb-exposure-by-horizon" -- frontend/src/app/workspaces/dashboard/dashboard.ts` shows it left the Dashboard template in `d9fef9eb` (2026-09-12, "fix(dashboard): streamline workspace controls and help"). So the boot sends **two** `/trades` calls, exactly as v206 § Plan 2 says. The verdict the index expects ("no merge, keep the calls") still holds. Only the count changes. This task pins the two-call fact and records it. It does not delete the dead panel: that is outside this plan's scope and is named in the Results text as a follow-up.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (append one `describe` at the end of the file)
- Modify: `frontend/src/app/workspaces/dashboard/panels/exposure-by-horizon.spec.ts` (append one `describe` at the end of the file)
- Modify: `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (`## Results`: new `### Plan 2 boot merge (V217-1)` after the `### Plan 1 baseline (committed probe)` block, at the end of the file)

**Interfaces:**
- Consumes: nothing from other tasks. Uses the existing spec helpers in `dashboard.spec.ts`: `seed()`, `tradeRow()`, `payload()`, and the `readFileSync`/`join` imports at its top; in `exposure-by-horizon.spec.ts`: `seed()`, `row()`, `slicesOf()`.
- Produces: spec heading `### Plan 2 boot merge (V217-1)` in the v206 spec. V217-6 writes `### Plan 2 after (committed probe)` below it.

No production code changes in this task. If any spec below fails against unchanged production code, the evidence contradicts the verdict: stop and report `BLOCKED` with the failing assertion. Do not adjust the assertion to pass, and do not write merge code.

- [ ] **Step 1: Append the boot-calls evidence spec to `dashboard.spec.ts`**

Append at the end of `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (every name used is already imported or defined at the top of that file):

```ts
/* v217 V217-1 (v206 § Plan 2 boot merge): the Dashboard boot sends two
 * /api/v1/trades requests, the activity feed's (newest 20 of every status)
 * and the positions table's Open tab (status=ACTIVE, its own page size).
 * The merge would need the feed to hold every row the Open tab shows, in the
 * same order. It does not: a position opened before the 20 newest rows is in
 * the table and missing from the feed. These specs are the recorded reason
 * the two calls stay separate. */
describe('Dashboard boot /trades calls (v217 V217-1)', () => {
  /** The feed's answer: the 20 newest rows of every status, none of them the
   *  long-held position below. */
  const FEED: TradeRow[] = Array.from({ length: 20 }, (_, i) => tradeRow({
    id: `feed-${i}`, ticker: `FEED${i}`, status: 'CLOSED', status_label: 'CLOSED',
    opened_at: '2026-10-20T10:00:00Z', closed_at: '2026-10-21T10:00:00Z',
  }));
  /** Opened in August, still ACTIVE: older than every feed row. */
  const OLD_ACTIVE = tradeRow({
    id: 'old-active', ticker: 'OLDPOS', status: 'ACTIVE', status_label: 'Open',
    opened_at: '2026-08-01T10:00:00Z', closed_at: null, exit_price: null,
    realized_pnl_amount: null, pnl_pct: 0.4, open_shares: 5,
  });

  async function boot() {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    const trades = backend.match((r) => r.url === '/api/v1/trades');
    for (const req of trades) {
      const open = req.request.params.get('status') === 'ACTIVE';
      req.flush({
        items: open ? [OLD_ACTIVE] : FEED,
        total: open ? 1 : 21,
        page: 1,
        per_page: Number(req.request.params.get('per_page')),
      });
    }
    backend.expectOne('/api/v1/dashboard?mode=today')
      .flush(payload({ lifecycle: { ACTIVE: 1 } as never }));
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, trades };
  }

  it('sends exactly two /trades requests: the activity feed and the Open tab', async () => {
    const { trades } = await boot();
    const params = trades.map((req) => req.request.params);
    expect(params).toHaveLength(2);

    const feed = params.find((p) => !p.has('status'));
    const open = params.find((p) => p.get('status') === 'ACTIVE');
    expect(feed).toBeDefined();
    expect(open).toBeDefined();
    expect(feed!.get('sort')).toBe('-opened_at');
    expect(feed!.get('page')).toBe('1');
    expect(feed!.get('per_page')).toBe('20');
    expect(open!.get('sort')).toBe('-opened_at');
    expect(open!.get('page')).toBe('1');
    // The table's own page size (10 desktop, 5 tablet/phone, or a saved
    // choice): never the feed's 20, so one response cannot serve both.
    expect(open!.get('per_page')).not.toBe('20');
  });

  it('mounts no exposure-by-horizon panel, so there is no third boot call', async () => {
    const { fixture } = await boot();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-exposure-by-horizon')).toBeNull();
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/dashboard.ts'), 'utf8');
    expect(src).not.toContain('sb-exposure-by-horizon');
  });

  it('shows an ACTIVE position older than the feed window in the table, not in the feed', async () => {
    const { fixture } = await boot();
    const el = fixture.nativeElement as HTMLElement;

    // The positions table renders the position from its own request ...
    expect(el.querySelector('sb-positions-table tbody')?.textContent).toContain('OLDPOS');
    // ... while the feed's population (all 20 rows it fetched) does not hold
    // it, so the table cannot take its rows from the feed's call.
    const recent = (fixture.componentInstance as unknown as {
      recent: { rows: () => TradeRow[] };
    }).recent.rows();
    expect(recent).toHaveLength(20);
    expect(recent.some((r) => r.id === 'old-active')).toBe(false);
    expect(el.querySelector('sb-recent-activity')?.textContent ?? '').not.toContain('OLDPOS');
  });
});
```

- [ ] **Step 2: Append the population comparison spec to `exposure-by-horizon.spec.ts`**

Append at the end of `frontend/src/app/workspaces/dashboard/panels/exposure-by-horizon.spec.ts` (uses that file's own `seed`, `row`, `slicesOf`):

```ts
/* v217 V217-1: if this unmounted panel ever came back, could it share the
 * positions table's Open-tab call? No: it asks `status=open` (ACTIVE plus
 * PARTIAL) at the server cap of 200, unpaged, while the Open tab asks
 * `status=ACTIVE` one page at a time. A PARTIAL runner counts here and is
 * absent from the Open tab, so identical rows cannot be asserted. */
describe('exposure by horizon vs the Open tab (v217 V217-1)', () => {
  it('asks a different query from the Open tab: status=open at 200 rows', () => {
    const { backend } = seed();
    const req = backend.expectOne((r) => r.url === '/api/v1/trades');
    expect(req.request.params.get('status')).toBe('open');
    expect(req.request.params.get('status')).not.toBe('ACTIVE');
    expect(req.request.params.get('per_page')).toBe('200');
    req.flush({ items: [], total: 0, page: 1, per_page: 200 });
  });

  it('counts a PARTIAL runner the Open tab never lists', () => {
    const { fixture, backend } = seed();
    backend.expectOne((r) => r.url === '/api/v1/trades').flush({
      items: [
        row({ id: 'a', status: 'ACTIVE', horizon: '2w', entry: 100, stop_loss: 95, open_shares: 10 }),
        row({ id: 'p', status: 'PARTIAL', status_label: 'PARTIAL', horizon: '1m',
              entry: 200, stop_loss: 190, open_shares: 2 }),
      ],
      total: 2, page: 1, per_page: 200,
    });
    fixture.detectChanges();
    // 2w: (100-95)*10 = 50 from the ACTIVE row; 1m: (200-190)*2 = 20 from the
    // PARTIAL row, which an ACTIVE-only response would have dropped.
    expect(slicesOf(fixture)).toEqual([
      { label: '2w', count: 50 },
      { label: '1m', count: 20 },
    ]);
  });
});
```

- [ ] **Step 3: Run both specs**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/dashboard/panels/exposure-by-horizon.spec.ts`
Expected: PASS, every case. These specs pin existing behaviour, so there is no red step. A failure here is evidence against the verdict: report `BLOCKED` with the assertion (see the rule above the steps).

- [ ] **Step 4: Record the verdict in the v206 spec**

Append at the end of `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (after the `### Plan 1 baseline (committed probe)` block, the last section of `## Results`), leaving one blank line before the heading:

```markdown
### Plan 2 boot merge (V217-1)

**Verdict: no merge. Both boot `/trades` calls stay.** Pinned by
`frontend/src/app/workspaces/dashboard/dashboard.spec.ts` ("Dashboard boot
/trades calls (v217 V217-1)") and
`frontend/src/app/workspaces/dashboard/panels/exposure-by-horizon.spec.ts`
("exposure by horizon vs the Open tab (v217 V217-1)").

The Dashboard boot sends two `/trades` requests, as § Plan 2 says:

| Caller | Query | Feeds |
|---|---|---|
| `dashboard.ts` `recent` (activity feed) | `sort=-opened_at&page=1&per_page=20`, no status | `deriveActivity` (at most 6 events), `liveSymbols` for Refresh, the trade drawer's lookups, the `recentSettled` redirect rule |
| `positions-table.ts` own `TradesStore` | `status=ACTIVE&sort=-opened_at&page=1&per_page=<10 desktop, 5 tablet/phone, or saved>` | the Open tab, its server pager, its own `trades`-event refetch |

Why they cannot merge under this section's rule ("the same rows in the same
order, asserted by a spec"):

1. The feed is not a superset of the Open tab. It holds the 20 newest rows of
   every status, so an ACTIVE position opened before those 20 is rendered by
   the table and missing from the feed (the spec seeds exactly that case).
2. The page sizes differ (20 vs 10/5/saved), and the table pages on the
   server and refetches on its own events. A shared response would have to
   carry both windows.

The brief behind plan v217 counted a third call, `sb-exposure-by-horizon`
(`status=open&per_page=200`). That panel is not mounted. It left the
Dashboard template in `d9fef9eb` (2026-09-12), and the boot spec asserts no
such element and no such tag in `dashboard.ts`. Had it been mounted, it still
could not share the Open tab's call: `status=open` is ACTIVE plus PARTIAL at
200 rows unpaged, `status=ACTIVE` is ACTIVE only and paged, so a PARTIAL
runner lands in one and not the other. Deleting the unmounted panel
(`panels/exposure-by-horizon.ts`, its spec and its `PANEL_HELP` entry) is a
follow-up outside plan v217.
```

- [ ] **Step 5: Commit (two scoped commits)**

```bash
git add frontend/src/app/workspaces/dashboard/dashboard.spec.ts frontend/src/app/workspaces/dashboard/panels/exposure-by-horizon.spec.ts
git commit -m "test(dashboard): pin the two boot /trades calls and why they cannot merge (v217 V217-1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git add docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md
git commit -m "docs(v206): Plan 2 boot merge verdict -- keep both /trades calls (v217 V217-1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase B — The two server fields

### Task V217-2: `/calendar/pnl/day` carries `prev_day` / `next_day`

**Model:** sonnet — one pure helper and one route line, with a hand-edited frozen golden and a strict contract test to keep in step.

**Files:**
- Modify: `swingbot/core/analytics/pnl_calendar.py` (new `adjacent_trading_days` directly after `day_context`)
- Modify: `swingbot/admin/api_v1/calendar.py` (`calendar_pnl_day`: one spread into the response, docstring line)
- Modify: `tests/analytics/test_pnl_calendar.py` (append unit tests)
- Modify: `tests/admin/test_api_v1_calendar.py` (contract shape in `test_day_trade_shape_carries_the_journal_join`; append endpoint tests)
- Modify: `tests/admin_perf/golden/calendar_day.json` (hand edit: two keys, nothing else)

**Interfaces:**
- Consumes: nothing from other tasks. Existing: `pnl_calendar.filter_rows`, `pnl_calendar.load_rows`, `pnl_calendar.day_context` (all in `swingbot/core/analytics/pnl_calendar.py`); test helpers `_trade`, `_context_book`, `seed`, `logged_in`, `assert_shape`, `assert_error`, `NULLABLE_STR` (in `tests/admin/test_api_v1_calendar.py` and `tests/admin/api_v1_contract.py`).
- Produces: `pnl_calendar.adjacent_trading_days(rows: list[dict], date: str) -> dict[str, str | None]` returning exactly `{"prev_day": <YYYY-MM-DD or None>, "next_day": <YYYY-MM-DD or None>}`. Response keys `prev_day` and `next_day` on every 200 `GET /api/v1/calendar/pnl/day` (JSON `null` at either end, never missing). V217-4 reads them as `CalendarDayTrades.prev_day?: string | null` / `next_day?: string | null`. 404 bodies do not change.

**Rules this task must hold (index § Global Constraints):** the neighbours are computed from the `rows` the route already loaded and filtered (same `strategy`/`horizon`, all history). No second `load_rows`, so the `calendar_day` SQL budget in `tests/admin_perf/test_budgets.py` (2 statements, 2 `list_all`) holds unchanged. `calendar_pnl_day` stays at complexity A (one added call, no branch). `record_golden` never overwrites a golden, so the golden edit is by hand, in the same commit as the code.

**Before the first test run:** run `/replicate-prod-db` once for this session (shared `swing-db` container, port 56789). The `admin` and `admin-perf` suites reach Postgres.

- [ ] **Step 1: Write the failing unit tests**

Append to the end of `tests/analytics/test_pnl_calendar.py`:

```python
# ---- v217 V217-2: the nearest trading days around a date -------------------

from swingbot.core.analytics.pnl_calendar import adjacent_trading_days


def _on(*days):
    """Rows reduced to the one key the helper reads."""
    return [{"day": day} for day in days]


def test_adjacent_trading_days_finds_both_neighbours():
    rows = _on("2026-08-05", "2026-08-03", "2026-08-04", "2026-08-03")
    assert adjacent_trading_days(rows, "2026-08-04") == {
        "prev_day": "2026-08-03", "next_day": "2026-08-05"}


def test_the_first_and_last_trading_day_have_a_null_neighbour():
    rows = _on("2026-08-03", "2026-08-04", "2026-08-05")
    assert adjacent_trading_days(rows, "2026-08-03") == {
        "prev_day": None, "next_day": "2026-08-04"}
    assert adjacent_trading_days(rows, "2026-08-05") == {
        "prev_day": "2026-08-04", "next_day": None}


def test_an_empty_book_has_no_neighbours_rather_than_an_error():
    assert adjacent_trading_days([], "2026-08-03") == {"prev_day": None, "next_day": None}


def test_a_gap_longer_than_a_month_still_resolves():
    """The SPA's month-grid fallback looks one month either way; this helper
    looks across all history, so a two-month quiet spell still has a neighbour."""
    rows = _on("2026-05-04", "2026-08-03", "2026-11-02")
    assert adjacent_trading_days(rows, "2026-08-03") == {
        "prev_day": "2026-05-04", "next_day": "2026-11-02"}


def test_a_date_with_no_rows_of_its_own_still_finds_its_neighbours():
    rows = _on("2026-08-03", "2026-08-05")
    assert adjacent_trading_days(rows, "2026-08-04") == {
        "prev_day": "2026-08-03", "next_day": "2026-08-05"}


def test_a_row_without_a_day_is_ignored():
    rows = [{"day": None}, {"day": "2026-08-03"}, {}]
    assert adjacent_trading_days(rows, "2026-08-04") == {
        "prev_day": "2026-08-03", "next_day": None}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: FAIL at collection with `ImportError: cannot import name 'adjacent_trading_days'`.

- [ ] **Step 3: Implement the helper**

In `swingbot/core/analytics/pnl_calendar.py`, insert directly after the end of `day_context` (before the `# --- v165 D3: what drove one day ---` comment):

```python
def adjacent_trading_days(rows: list[dict], date: str) -> dict[str, str | None]:
    """v217 P3-b -- the nearest trading days before and after `date`.

    `rows` is the filtered ALL-HISTORY row set the day route already holds
    (the same scope `day_context` reads), so the neighbours honour the
    strategy/horizon filter and cost no second read. A trading day is any day
    with at least one row, the grid's own rule (days with no close are
    omitted). Days are `YYYY-MM-DD` strings, so string order is date order.

    `None` at either end of the book: "no earlier day" is a measured answer,
    and the key is always present so a client can tell it from an older
    server that sends neither key.
    """
    days = {row.get("day") for row in rows} - {None}
    earlier = [day for day in days if day < date]
    later = [day for day in days if day > date]
    return {
        "prev_day": max(earlier) if earlier else None,
        "next_day": min(later) if later else None,
    }
```

- [ ] **Step 4: Run the unit tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: PASS (all, including the six new tests).

- [ ] **Step 5: Write the failing endpoint tests**

In `tests/admin/test_api_v1_calendar.py`, `test_day_trade_shape_carries_the_journal_join`: extend the first `assert_shape(body, {...})` spec with the two keys, after `"context": dict, "breakdown": dict,`:

```python
        # v165 D2 / D3.
        "context": dict, "breakdown": dict,
        # v217 P3-b -- nearest trading days under the same filter, null at the ends.
        "prev_day": NULLABLE_STR, "next_day": NULLABLE_STR,
    })
```

(`NULLABLE_STR` is already imported at the top of the file.) Then append to the end of the file:

```python
# ---- v217 V217-2: prev_day / next_day on the day route ----------------------


def test_day_carries_its_neighbouring_trading_days(seed, logged_in):
    seed(trades=_context_book())
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-04").get_json()
    assert body["prev_day"] == "2026-08-03"
    assert body["next_day"] == "2026-08-05"


def test_the_first_and_last_day_neighbours_are_null_not_missing(seed, logged_in):
    seed(trades=_context_book())
    first = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    last = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-05").get_json()
    assert "prev_day" in first and first["prev_day"] is None
    assert first["next_day"] == "2026-08-04"
    assert last["prev_day"] == "2026-08-04"
    assert "next_day" in last and last["next_day"] is None


def test_neighbours_respect_the_strategy_filter(seed, logged_in):
    """VWAP closed on 08-03 and 08-05 only, so under strategy=VWAP the
    EMA20-only 08-04 is not a trading day."""
    seed(trades=_context_book())
    body = logged_in.get(
        "/api/v1/calendar/pnl/day?date=2026-08-05&strategy=VWAP").get_json()
    assert body["prev_day"] == "2026-08-03"
    assert body["next_day"] is None


def test_neighbours_respect_the_horizon_filter(seed, logged_in):
    seed(trades=[
        _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", horizon="4w"),
        _trade("b" * 16, closed_at="2026-08-04T20:00:00+00:00", horizon="1m"),
        _trade("c" * 16, closed_at="2026-08-05T20:00:00+00:00", horizon="4w"),
    ])
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03&horizon=4w").get_json()
    assert body["prev_day"] is None
    assert body["next_day"] == "2026-08-05"


def test_neighbours_span_a_gap_longer_than_a_month(seed, logged_in):
    """Behaviour change v217 makes on purpose: the SPA used to look only one
    month either way, so this day showed no previous day at all."""
    seed(trades=[
        _trade("a" * 16, closed_at="2026-05-04T20:00:00+00:00"),
        _trade("b" * 16, closed_at="2026-08-03T20:00:00+00:00"),
    ])
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    assert body["prev_day"] == "2026-05-04"
    assert body["next_day"] is None


def test_a_404_day_body_is_unchanged_and_carries_no_neighbours(seed, logged_in):
    seed(trades=[_trade("a" * 16)])
    response = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-09")
    assert_error(response, "not_found", 404)
    assert set(response.get_json()) == {"error"}
```

- [ ] **Step 6: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py`
Expected: FAIL. `test_day_trade_shape_carries_the_journal_join` fails with `body: missing key(s) ['next_day', 'prev_day']`, and the five new 200-path tests fail with `KeyError: 'prev_day'` or a failed `in` assertion. `test_a_404_day_body_is_unchanged_and_carries_no_neighbours` already passes (it pins what must not change).

- [ ] **Step 7: Wire the helper into the route**

In `swingbot/admin/api_v1/calendar.py`, `calendar_pnl_day()`: add the spread directly after the `"context"` entry of the `jsonify({...})` call, so the return reads:

```python
    return jsonify({
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "date": date,
        "trades": day_rows,
        "fx_missing_count": missing_count(day_rows),
        **pc.day_totals(day_rows),
        "context": pc.day_context(rows, date),
        # v217 P3-b: the nearest trading days under the same filter, from the
        # rows already loaded, so the day page needs no neighbouring month grid.
        **pc.adjacent_trading_days(rows, date),
        "breakdown": pc.day_breakdown(day_rows),
    })
```

And append one sentence to the end of the view's docstring (after "... all history, like the grid's weekday table)."):

```python
    `prev_day` / `next_day` (v217) are the nearest trading days before and
    after `date` under the same filter, across all history; null at either
    end. The 404 above carries neither: an empty day has no body.
    """
```

- [ ] **Step 8: Hand-edit the frozen golden**

The golden book's trading days are 2026-10-29, 2026-11-02 and 2026-11-03 (`tests/admin_perf/golden_book.py`; the golden date is `DAY = "2026-11-03"`), so the golden day's neighbours are `prev_day = "2026-11-02"` and `next_day = null`. The golden is written with `sort_keys=True, indent=1`, so the two keys go between `"losers"` and `"total_ccy"`. In `tests/admin_perf/golden/calendar_day.json` replace exactly these two lines:

```json
 "losers": 0,
 "total_ccy": 163.5,
```

with these four:

```json
 "losers": 0,
 "next_day": null,
 "prev_day": "2026-11-02",
 "total_ccy": 163.5,
```

No other byte of the file changes (check with `git diff --stat tests/admin_perf/golden/calendar_day.json`: 2 insertions, 0 deletions). Never run the golden test with `ADMIN_PERF_RECORD=1` to produce this: `record_golden.write_golden` refuses to overwrite, and a re-record would hide any other drift.

- [ ] **Step 9: Run every touched test file and the two admin-perf files**

Run, one at a time:
- `python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
- `python scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py`
- `python scripts/dev/testrun.py file tests/admin_perf/test_golden_endpoints.py`
- `python scripts/dev/testrun.py file tests/admin_perf/test_budgets.py`

Expected: all PASS, `0 failed`, `0 xfailed`. In `test_golden_endpoints.py` the `calendar_day` cases of `test_endpoint_matches_its_frozen_golden` and `test_money_pointers_are_exactly_the_fx_sensitive_fields` pass (the new fields carry no money, so `money_reference.EXPECTED_MONEY` is untouched). `test_endpoint_stays_within_its_budget[calendar_day]` stays at or under (2, 2).

- [ ] **Step 10: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: passes. `adjacent_trading_days` is A, and `calendar_pnl_day` gains no branch.

- [ ] **Step 11: Commit**

```bash
git add swingbot/core/analytics/pnl_calendar.py tests/analytics/test_pnl_calendar.py
git commit -m "feat(analytics): adjacent_trading_days -- nearest trading days over filtered rows (v217 V217-2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git add swingbot/admin/api_v1/calendar.py tests/admin/test_api_v1_calendar.py tests/admin_perf/golden/calendar_day.json
git commit -m "feat(admin): /calendar/pnl/day carries prev_day/next_day; calendar_day golden gains the two keys by hand (v217 V217-2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V217-3: `/dashboard` carries `today` for modes `all`/`range`

**Model:** sonnet — two small helpers in one route module. The care is in the scope rule (goldens stay byte-identical), in reusing the loaded trades, and in the SQL budget proof.

**Files:**
- Modify: `swingbot/admin/api_v1/dashboard.py` (new `_TODAY_BLOCK_MODES`, `_today_block`, `_today_field` above the `dashboard()` view; one spread in `dashboard()`)
- Modify: `tests/admin/test_api_v1_dashboard.py` (append tests)
- Create: `tests/admin_perf/test_today_block.py`

**Interfaces:**
- Consumes: nothing from other tasks. Existing in `swingbot/admin/api_v1/dashboard.py`: `_realized_parts(trades, mode, window=None)`, `_realized(closed) -> dict`, `_lifecycle_counts(mode, all_trades, window=None) -> dict`; `swingbot.core.tracking.ledger.is_main`. Test helpers in `tests/admin/test_api_v1_dashboard.py`: `seed`, `logged_in`, `_closed`, `_today_iso`, `_range`, `_parity_book`, `RANGE_FROM`, `RANGE_TO`, `assert_shape`, `NULLABLE_NUMBER`. Fixtures in `tests/admin_perf/conftest.py`: `golden_seed`, `frozen_clock`, `sql_counted`, `logged_in`; `tests/admin_perf/test_budgets.py` `BUDGETS`; `tests/admin_perf/golden_book.py` `golden_path`, `admin_endpoint_timing`.
- Produces: `dashboard._TODAY_BLOCK_MODES = ("all", "range")`; `dashboard._today_block(all_raw: list[dict]) -> dict` returning exactly `{"realized": dict, "lifecycle": dict}` (the same shapes as the top-level `realized` and `lifecycle`); response key `today` on `GET /api/v1/dashboard?mode=all` and `?mode=range&from=&to=` only. V217-5 reads it as `Dashboard.today?: DashboardToday`. Private helper `_today_field(mode: str, all_raw: list[dict]) -> dict` (`{"today": ...}` or `{}`) keeps `dashboard()` at one added call and no added branch. No other task uses it.

**Rules this task must hold (index § Global Constraints):**
- `today` appears only for `all` and `range`. Never for `active` (the default, frozen in `tests/admin_perf/golden/dashboard.json`) or `today` (frozen in `dashboard_today.json`). Both goldens stay byte-identical. The SPA sends only `today`/`all`/`range` (`scopeToRequest`), so `active` needs no block. v205 says "wider than 1D" and is silent on `active`; the index fixes this choice.
- The block equals `GET /api/v1/dashboard?mode=today`'s `realized` and `lifecycle` on the same book. A day with no closes is a measured zero (`n: 0`, amounts `null`), and the block is still present.
- It reuses the request's `all_raw`: no second `TradeLog().get_trades`. `_lifecycle_counts("today", ...)` re-reads plans and journal through `_plan_rows()`/`build_rows()`, but `@read_scope` memoises each store once per request (`swingbot/core/infra/read_memo.py`), so the `dashboard` budget (12 statements, 4 `list_all`) holds for mode `all` too. The new admin-perf test proves it. The extra cost is CPU only (one more `build_rows` pass over the loaded trades).
- `dashboard()` is B(10) and gains exactly one call and no branch. `_realized` (C13) is not touched.

**Before the first test run:** run `/replicate-prod-db` once for this session, unless V217-2 already did in this session (shared `swing-db` container, port 56789).

- [ ] **Step 1: Write the failing endpoint tests**

Append to the end of `tests/admin/test_api_v1_dashboard.py`:

```python
# --------------------------------------------------------- v217 the today block
#
# A wider-scope Dashboard used to send /dashboard twice: once for its scope and
# once with mode=today for the "today" card. Modes all and range now carry the
# today figures themselves, computed from the same loaded trades. active and
# today never carry them: their own figures are today's, and their frozen
# goldens (tests/admin_perf/golden/dashboard*.json) must stay byte-identical.

_REALIZED_SHAPE = {
    "amount": NULLABLE_NUMBER, "pct": NULLABLE_NUMBER,
    "n": int, "wins": int, "losses": int, "fx_missing_count": int,
}


def test_today_block_modes_are_exactly_all_and_range(admin_app):
    from swingbot.admin.api_v1.dashboard import _TODAY_BLOCK_MODES
    assert _TODAY_BLOCK_MODES == ("all", "range")


@pytest.mark.parametrize("query", ["", "?mode=active", "?mode=today"])
def test_today_block_is_absent_for_active_and_today(seed, logged_in, query):
    seed(**_parity_book())
    body = logged_in.get(f"/api/v1/dashboard{query}").get_json()
    assert "today" not in body


def test_today_block_is_present_and_shaped_for_all_and_range(seed, logged_in):
    seed(**_parity_book())
    for body in (logged_in.get("/api/v1/dashboard?mode=all").get_json(),
                 _range(logged_in).get_json()):
        assert_shape(body["today"], {"realized": dict, "lifecycle": dict}, where="today")
        assert_shape(body["today"]["realized"], _REALIZED_SHAPE, where="today.realized")
        assert set(body["today"]["lifecycle"]) == set(body["lifecycle"])


def test_today_block_equals_mode_today_for_all(seed, logged_in):
    seed(**_parity_book())
    all_days = logged_in.get("/api/v1/dashboard?mode=all").get_json()
    today = logged_in.get("/api/v1/dashboard?mode=today").get_json()
    assert all_days["today"] == {"realized": today["realized"], "lifecycle": today["lifecycle"]}
    # The parity book closes a win and a loss today on the main ledger.
    assert all_days["today"]["realized"]["n"] == 2
    # ... and the scoped figures beside it are still all-time.
    assert all_days["realized"]["n"] == 3


def test_today_block_equals_mode_today_for_a_range_that_excludes_today(seed, logged_in):
    """The range (5 Jan 2026) holds only the old loss; the block is still today's."""
    seed(**_parity_book())
    ranged = _range(logged_in, RANGE_FROM, RANGE_TO).get_json()
    today = logged_in.get("/api/v1/dashboard?mode=today").get_json()
    assert ranged["today"] == {"realized": today["realized"], "lifecycle": today["lifecycle"]}
    assert ranged["realized"]["n"] == 1
    assert ranged["today"]["realized"]["n"] == 2


def test_a_day_with_no_closes_is_a_measured_zero_block_not_an_absent_one(seed, logged_in):
    seed(trades=[_closed("a" * 16, closed_at="2026-01-05T15:00:00+00:00", amount=40.0)])
    body = logged_in.get("/api/v1/dashboard?mode=all").get_json()
    assert body["today"]["realized"] == {
        "amount": None, "pct": None, "n": 0, "wins": 0, "losses": 0, "fx_missing_count": 0}
    assert body["today"]["lifecycle"]["CLOSED"] == 0
    assert body["realized"]["n"] == 1


def test_today_block_on_an_empty_book(seed, logged_in):
    seed()
    body = logged_in.get("/api/v1/dashboard?mode=all").get_json()
    assert body["today"]["realized"]["n"] == 0
    assert body["today"]["realized"]["amount"] is None
    assert isinstance(body["today"]["lifecycle"], dict)


def test_all_mode_with_the_today_block_reads_the_trade_log_once(seed, logged_in, monkeypatch):
    from swingbot.core.tracking.performance import TradeLog

    seed(**_parity_book())
    calls = []
    original = TradeLog.get_trades

    def counting(self, *args, **kwargs):
        calls.append(kwargs.get("status"))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TradeLog, "get_trades", counting)
    body = logged_in.get("/api/v1/dashboard?mode=all").get_json()
    assert "today" in body
    assert len(calls) == 1, f"get_trades called {len(calls)} times: {calls}"
```

- [ ] **Step 2: Write the failing admin-perf test**

Create `tests/admin_perf/test_today_block.py` (suite `admin-perf` already covers `tests/admin_perf/`, so `tests/suites.toml` needs no edit):

```python
"""v217 V217-3: the wider-scope /dashboard `today` block on the golden book.

A `mode=all` request now also computes today's realised figures and lifecycle
counts, from the same loaded trades. These tests prove it costs no more SQL
than the frozen `dashboard` budget, reads the trade log once, equals what
`mode=today` answers, and never appears on the two frozen dashboard goldens."""
import json

from swingbot.core.db.repositories.base import Repository
from tests.admin_perf import golden_book as gb
from tests.admin_perf.test_budgets import BUDGETS

ALL = "/api/v1/dashboard?mode=all"
TODAY = "/api/v1/dashboard?mode=today"


def _cost(client, path, monkeypatch) -> tuple[int, list[str]]:
    """(SQL statements, list_all caller classes) of one GET of ``path``,
    the way test_budgets._cost measures a named endpoint."""
    calls: list[str] = []
    real = Repository.list_all

    def counting(self, *args, **kwargs):
        calls.append(type(self).__name__)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Repository, "list_all", counting)
    try:
        response = client.get(path)
    finally:
        monkeypatch.setattr(Repository, "list_all", real)
    assert response.status_code == 200, (path, response.status_code, response.get_data()[:300])
    assert "today" in response.get_json()
    timing = gb.admin_endpoint_timing.parse_server_timing(response.headers.get("Server-Timing"))
    assert "db" in timing, f"{path}: no Server-Timing db entry"
    return int(timing["db"]["statements"]), calls


def test_mode_all_with_the_block_stays_within_the_dashboard_budget(
        golden_seed, frozen_clock, sql_counted, logged_in, monkeypatch):
    statements, calls = _cost(logged_in, ALL, monkeypatch)
    max_statements, max_list_all = BUDGETS["dashboard"]
    assert statements <= max_statements, f"{statements} SQL statements > budget {max_statements}"
    assert len(calls) <= max_list_all, f"list_all x{len(calls)} > budget {max_list_all}: {calls}"


def test_mode_all_reads_the_trade_log_once(golden_seed, frozen_clock, logged_in, monkeypatch):
    from swingbot.core.tracking.performance import TradeLog

    calls = []
    original = TradeLog.get_trades

    def counting(self, *args, **kwargs):
        calls.append(kwargs.get("status"))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TradeLog, "get_trades", counting)
    assert logged_in.get(ALL).status_code == 200
    assert len(calls) == 1, f"get_trades called {len(calls)} times: {calls}"


def test_the_block_equals_mode_today_on_the_golden_book(golden_seed, frozen_clock, logged_in):
    """FROZEN_NOW is 2026-11-04 12:00 UTC and the book's last close is
    2026-11-03 20:30 UTC (21:30 Berlin), so today is a measured zero."""
    block = logged_in.get(ALL).get_json()["today"]
    today = logged_in.get(TODAY).get_json()
    assert block == {"realized": today["realized"], "lifecycle": today["lifecycle"]}
    assert block["realized"]["n"] == 0
    assert block["realized"]["amount"] is None


def test_the_frozen_dashboard_goldens_carry_no_block(golden_seed, frozen_clock, logged_in):
    for name in ("dashboard", "dashboard_today"):
        assert "today" not in logged_in.get(gb.ENDPOINTS[name]).get_json(), name
        assert "today" not in json.loads(gb.golden_path(name).read_text(encoding="utf-8")), name
```

- [ ] **Step 3: Run both files to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py`
Expected: FAIL. `test_today_block_modes_are_exactly_all_and_range` fails with `ImportError: cannot import name '_TODAY_BLOCK_MODES'`. The present/equals/zero/empty/reads-once tests fail with `KeyError: 'today'` or `assert 'today' in body`. The three `test_today_block_is_absent_for_active_and_today` cases already pass (they pin what must not change).

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_today_block.py`
Expected: FAIL in the first three tests (`assert "today" in ...` / `KeyError: 'today'`). `test_the_frozen_dashboard_goldens_carry_no_block` passes.

- [ ] **Step 4: Implement the helpers and the one call**

In `swingbot/admin/api_v1/dashboard.py`, insert directly above the `@api_v1.route("/dashboard", methods=["GET"])` decorator (after `_open_figures`):

```python
#: v217 P3-a: the scopes whose response also carries today's figures. Not
#: `active` or `today`: their own `realized`/`lifecycle` already are today's,
#: and their frozen goldens (tests/admin_perf/golden/dashboard*.json) must stay
#: byte-identical. The SPA sends only today/all/range (`scopeToRequest`).
_TODAY_BLOCK_MODES = ("all", "range")


def _today_block(all_raw: list[dict]) -> dict:
    """Today's `realized` and `lifecycle`, from the trades the request loaded.

    Exactly what `?mode=today` answers for those two keys (same helpers, mode
    `"today"`, no window), so a wider-scope Dashboard needs no second request
    for its "today" card. `all_raw` is reused: never a second `get_trades`.
    `_lifecycle_counts` re-reads plans and the journal, which `@read_scope`
    serves from the request's memo.

    A day with no closes is a measured zero (`n: 0`, amounts `None`), never a
    missing block: the SPA reads absence as "older backend, fetch it".
    """
    from swingbot.core.tracking.ledger import is_main
    return {
        "realized": _realized(_realized_parts([t for t in all_raw if is_main(t)], "today")),
        "lifecycle": _lifecycle_counts("today", all_raw),
    }


def _today_field(mode: str, all_raw: list[dict]) -> dict:
    """`{"today": ...}` for the wider scopes, `{}` otherwise; spread into the
    response so `dashboard()` gains one call and no branch."""
    if mode not in _TODAY_BLOCK_MODES:
        return {}
    return {"today": _today_block(all_raw)}
```

Then in `dashboard()`, add one line at the end of the `jsonify({...})` dict, after the `"realized_weak"` entry:

```python
        "realized_weak": _realized(
            _realized_parts([t for t in all_raw if is_weak(t)], mode, window)),
        # v217 P3-a: today's figures ride a wider-scope response (all/range).
        **_today_field(mode, all_raw),
    })
```

- [ ] **Step 5: Run the narrow tests to verify they pass**

Run, one at a time:
- `python scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py`
- `python scripts/dev/testrun.py file tests/admin_perf/test_today_block.py`
- `python scripts/dev/testrun.py file tests/admin_perf/test_golden_endpoints.py`
- `python scripts/dev/testrun.py file tests/admin_perf/test_budgets.py`

Expected: all PASS, `0 failed`, `0 xfailed`. `test_endpoint_matches_its_frozen_golden[dashboard]` and `[dashboard_today]` pass with no golden edit (`git diff --stat tests/admin_perf/golden/` shows nothing from this task). `test_returns_exactly_the_nine_metrics` passes unchanged, because the default mode is `active`, which carries no block.

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: passes. `dashboard()` stays B(10), since a spread of a call adds no branch. `_today_field` is A(2) and `_today_block` A(2) (the comprehension's `if`).

- [ ] **Step 7: Commit**

```bash
git add swingbot/admin/api_v1/dashboard.py tests/admin/test_api_v1_dashboard.py tests/admin_perf/test_today_block.py
git commit -m "feat(admin): /dashboard modes all and range carry today's realized and lifecycle (v217 V217-3)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

