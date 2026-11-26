# v249 — Admin client data layer, part 1b: Risk balance (V249-4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull the task with `grep -n "^### Task V249-4" -A 400 <this file>`.

**Spec:** [2026-11-25-v249-admin-client-data-layer-design.md](../specs/2026-11-25-v249-admin-client-data-layer-design.md)
**Index:** [2026-11-25-v249-admin-client-data-layer_0-index.md](2026-11-25-v249-admin-client-data-layer_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there and bind this task.

Part 1 overflowed the 1500-line cap once V249-1 was split into V249-1/V249-1b, so its last task moved here whole. Scope: the Risk page takes its balance from the `/risk` body it already reads (spec § 3).

# Phase 1 (continued) — Risk balance

### Task V249-4: Risk balance from the `/risk` body: delete `readBalance`, the `balance` slice and the `/dashboard` call

**Model:** sonnet — a contained store deletion with spec rewrites in two files and one small server pin.

**Files:**
- Modify: `frontend/src/app/stores/risk.store.ts:14` (rxjs import), `:45-50` (`balance` slice doc and field), `:96-104` (class doc), `:113` (initial `balance`), `:223-225` (`accountBalance`), `:235-262` (`readBalance`, `resolve`)
- Modify: `frontend/src/app/stores/risk.store.spec.ts` (describe `'RiskStore balance and cap headroom (v195 §5.2)'` `:436-495`; snapshot describe helper `risk()` `:536-539`; test `"accountBalance prefers the risk body's account balance"` `:584-592`)
- Modify: `frontend/src/app/workspaces/risk/risk.spec.ts:962-980` (`renderPage`), `:1101-1105`
- Modify: `tests/admin/test_api_v1_risk.py` (one parametrized test appended; spec § 7 "zero/negative never reach it (`/risk` drops them). Both cases tested." No other task touches this file.)

**Interfaces:**
- Consumes: nothing from earlier tasks. Existing: `RiskAccount { balance: number | null; currency: string }` (`frontend/src/app/api/models.ts:1776`), `Risk.account?: RiskAccount` (`:1787`), server `_account_balance()` (`swingbot/admin/api_v1/risk.py:218`: `balance`, else `base_balance`, finite and > 0, else `None`), body key `account.balance` (`risk.py:302`).
- Produces (index ledger): `RiskStore.accountBalance: Signal<number | null>` = `finiteOrNull(data()?.account?.balance)`, no fallback. `RiskStore` no longer has a `balance` slice and the Risk page makes no `/dashboard` request.

Why: spec § 3. `/risk` already returns `account.balance`, and the Risk page already fetches `/risk`. Taking every Risk-page figure from one body is the consistent choice, even though `/risk` falls back to `base_balance` and drops a non-positive balance where `/dashboard` passes the raw value. A null balance renders the existing `"— · 3.00%"` through `riskUnits(pct, balance, currency)` (`frontend/src/app/workspaces/risk/risk.ts:921`, `:1032`); no template changes. `store.balance()` has no reader outside `risk.store.ts` (the Dashboard's `balance` is `DashboardStore`'s own).

- [ ] **Step 1: Pin the server's balance rule (passes already; the client now relies on it)**

Append to `tests/admin/test_api_v1_risk.py`:

```python
@pytest.mark.parametrize("balance, base, expected", [
    (12_500.0, 10_000.0, 12_500.0),   # the live balance wins
    (0.0, 10_000.0, 10_000.0),        # zero never reaches the page: base_balance instead
    (-50.0, 10_000.0, 10_000.0),      # nor does a negative balance
    (0.0, 0.0, None),                 # nothing positive: null, the page shows "—"
    (-50.0, -1.0, None),
])
def test_account_balance_is_positive_or_null(logged_in, balance, base, expected):
    """v249 V249-4: the Risk page's money figures read only this field."""
    seed_store("trades", [])
    seed_store("account", {"base_balance": base, "balance": balance, "risk_pct": 1.0})
    assert logged_in.get("/api/v1/risk").get_json()["account"]["balance"] == expected
```

Run `/replicate-prod-db` once this session if no sibling task did, then:

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py`
Expected: PASS.

- [ ] **Step 2: Rewrite the store tests (failing first)**

In `frontend/src/app/stores/risk.store.spec.ts`, replace the whole describe `'RiskStore balance and cap headroom (v195 §5.2)'` (`:436-495`, with the `/* -- v195 §5.2 … */` banner above it kept) with:

```ts
describe('RiskStore balance and cap headroom (v195 §5.2, v249: from the /risk body)', () => {
  let store: InstanceType<typeof RiskStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    configure([fakeLive().provider]);
    store = TestBed.inject(RiskStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const respond = (body: Partial<Risk> = {}) =>
    backend.expectOne('/api/v1/risk').flush({ ...RESPONSE, ...body });
  const unavailable = { status: 503, statusText: 'Service Unavailable' };
  const DOWN = { error: { code: 'unavailable', message: 'down' } };
  const ACCOUNT = { balance: 10_000, currency: 'USD' };

  it('takes the balance from the /risk body and makes no /dashboard request', () => {
    store.load();
    respond({ account: ACCOUNT });
    backend.expectNone('/api/v1/dashboard');

    expect(store.accountBalance()).toBe(10_000);
    expect(store.openHeatPct()).toBe(3);
  });

  it('has no balance slice of its own any more', () => {
    expect('balance' in store).toBe(false);
  });

  it('leaves the balance null, and the risk loaded, when the body has none', () => {
    store.load();
    respond({ account: { balance: null, currency: 'USD' } });

    expect(store.accountBalance()).toBeNull();
    expect(store.error()).toBeNull();
    expect(store.positions()).toHaveLength(2);
  });

  it("keeps the last body's balance when a later /risk read fails", () => {
    store.load();
    respond({ account: ACCOUNT });

    store.load();
    backend.expectOne('/api/v1/risk').flush(DOWN, unavailable);
    expect(store.accountBalance()).toBe(10_000);
    expect(store.error()).not.toBeNull();
  });

  it('never takes a balance that is not a finite number', () => {
    store.load();
    respond({ account: { balance: '10000' as never, currency: 'USD' } });
    expect(store.accountBalance()).toBeNull();
  });

  it('finishes the route on the /risk read, with nothing else in flight', () => {
    let finished = 0;
    store.resolve().subscribe({ complete: () => { finished += 1; } });
    respond({ account: ACCOUNT });

    expect(finished).toBe(1);
    backend.verify();
  });

  it('reads nothing until the resolver is subscribed', () => {
    store.resolve();
    backend.expectNone('/api/v1/risk');
    backend.expectNone('/api/v1/dashboard');
  });

  it('measures cap headroom as the cap less the open heat, unclamped', () => {
    store.load();
    respond({ heat: { open_pct: 3, cap_pct: 6, utilisation_pct: 50 } });
    expect(store.headroomPct()).toBe(3);

    store.load();
    respond({ heat: { open_pct: 7.5, cap_pct: 6, utilisation_pct: 125 } });
    expect(store.headroomPct()).toBe(-1.5);
  });

  it('has no headroom when either side is unknown, and before the first answer', () => {
    expect(store.headroomPct()).toBeNull();
    store.load();
    respond({ heat: { open_pct: null, cap_pct: 6, utilisation_pct: null } });
    expect(store.headroomPct()).toBeNull();
    store.load();
    respond({ heat: { open_pct: 3, cap_pct: null, utilisation_pct: null } });
    expect(store.headroomPct()).toBeNull();
  });
});
```

In the snapshot describe (`'RiskStore snapshot (v204)'`), change the `risk` helper (`:536-539`) to flush `/risk` only:

```ts
  const risk = (body: Partial<Risk> = {}) => {
    backend.expectOne('/api/v1/risk').flush({ ...RESPONSE, ...body });
  };
```

Replace `"accountBalance prefers the risk body's account balance"` (`:584-592`) with:

```ts
  it("accountBalance is the risk body's account balance, with no fallback", () => {
    const store = setup([fakeLive().provider]);
    store.load(); tick();
    risk({ account: { balance: 12_500, currency: 'USD' } });
    expect(store.accountBalance()).toBe(12_500);
    store.load(); tick();
    risk({ account: undefined });
    expect(store.accountBalance()).toBeNull();
    backend.expectNone('/api/v1/dashboard');
  });
```

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/risk.store.spec.ts`
Expected: FAIL. `'takes the balance … makes no /dashboard request'` and `'… with nothing else in flight'` fail on the store's own `/dashboard` read, `'has no balance slice'` fails, and `'accountBalance is … with no fallback'` fails (it still sees no `/dashboard` flush, so the old fallback is `null` here too; the `expectNone` fails on the pending read).

- [ ] **Step 3: Delete the read in the store**

In `frontend/src/app/stores/risk.store.ts`:

Delete the `balance` field and its doc comment from `RiskSlice` (`:45-50`), and `balance: null,` from `withState` (`:113`).

Replace the class-doc paragraph that begins `**One read beside it (v195 §5.2).**` (`:99-103`) with:

```ts
 * **Money beside %.** `GET /risk` carries risk as % of account and, since
 * v249, the store also takes the account balance from that same body
 * (`account.balance`: the live balance, else `base_balance`, finite and
 * positive or null; `risk.py` `_account_balance`). Every Risk figure comes
 * from one read; a null balance leaves the money half of each KPI blank
 * ("— · 3.00%"), it never fails the route.
```

Replace `accountBalance` and its doc comment (`:223-225`) with:

```ts
    /** The `/risk` body's own balance (v249: the only source; no `/dashboard` read). */
    accountBalance: computed(() => finiteOrNull(store.data()?.account?.balance)),
```

Replace `readBalance` and `resolve` with their doc comments (`:235-262`) with:

```ts
    /** The one read; `routeRequest` starts it when the resolver subscribes. */
    const resolve = (): Observable<void> => routeRequest(api.risk(), {
      start: () => patchState(store, { loading: true }),
      next: (data) => patchState(store, { data, control: data.killswitch, loading: false, error: null }),
      error: (error) => patchState(store, {
        control: unavailableKillswitch(store.control()),
        loading: false,
        error: error.code === 'unavailable' ? 'The admin is not responding — these figures may be stale.' : error.message,
      }),
    });
```

Change the rxjs import (`:14`) from `import { Observable, defer } from 'rxjs';` to `import { Observable } from 'rxjs';`.

Run: `git grep -n "readBalance\|store.balance()" -- frontend/src/app/stores/risk.store.ts frontend/src/app/workspaces/risk`
Expected: no output.

- [ ] **Step 4: Rewrite the Risk page helper and the no-balance test**

In `frontend/src/app/workspaces/risk/risk.spec.ts`, replace `renderPage` with its doc comment (`:962-980`) with:

```ts
/** Flushes /risk, whose `account.balance` is the page's only balance (v249).
 *  `balance: null` is a body with no usable balance. */
async function renderPage(
  overrides: Partial<RiskData> = {},
  balance: number | null = 10000,
): Promise<ComponentFixture<Risk>> {
  const { fixture, backend } = seed();
  TestBed.inject(RouteTitleService).set('Risk', 'Exposure, heat and the killswitch');
  fixture.detectChanges();
  backend.expectOne('/api/v1/risk').flush(payload({
    heat: { open_pct: 3, cap_pct: 20, utilisation_pct: 15 },
    positions: [OPEN_POSITION],
    account: { balance, currency: 'USD' },
    ...overrides,
  }));
  backend.expectNone('/api/v1/dashboard');
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture;
}
```

If `DOWN` and `UNAVAILABLE` (`:958-959`) have no other user after this (`git grep -n "UNAVAILABLE\|DOWN" -- frontend/src/app/workspaces/risk/risk.spec.ts`), delete them so lint stays clean.

Replace `'never invents money when the balance read fails'` (`:1101-1105`) with:

```ts
  it('never invents money when the /risk body has no balance', async () => {
    const tiles = kpis(await renderPage({}, null));
    expect(tiles.get('Open risk')!.value()).toBe('— · 3.00%');
    expect(tiles.get('Cap headroom')!.value()).toBe('— · 17.00%');
  });

  it("shows the /risk body's balance in the money half, not any other read", async () => {
    const tiles = kpis(await renderPage({}, 12_500));
    expect(tiles.get('Open risk')!.value()).toBe('375 € · 3.00%');
  });
```

- [ ] **Step 5: Run the frontend tests and lint**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/risk.store.spec.ts`
Expected: PASS.

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/risk/risk.spec.ts`
Expected: PASS (the existing `'300 € · 3.00%'` tests still read 10 000 from the body).

Run: `git grep -n "api/v1/dashboard" -- frontend/src/app/workspaces/risk frontend/src/app/stores/risk.store.spec.ts`
Expected: only the `expectNone('/api/v1/dashboard')` lines added above.

Run: `npm --prefix frontend run lint`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/stores/risk.store.ts frontend/src/app/stores/risk.store.spec.ts frontend/src/app/workspaces/risk/risk.spec.ts
git commit -m "refactor(ui): v249 risk balance from the /risk body -- no /dashboard read on the Risk page"
git add tests/admin/test_api_v1_risk.py
git commit -m "test(api): v249 pin /risk account.balance positive-or-null (zero and negative dropped)"
```

