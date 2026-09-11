# v85 Part 2 — Backend

Header block, global constraints, parallelisation and exit criteria live in
`2026-09-11-v85-dashboard-shell-redesign_0-index.md`.

Two independent strands — run them in parallel only as whole strands, never
task-interleaved:

- **Payoff ratio:** R2-01 → R2-02 → R2-03 (`core/analytics/metrics.py`,
  `core/tracking/performance.py`, `admin/api_v1/dashboard.py`)
- **Bulk close:** R2-04 → R2-05 → R2-06 (`admin/api_v1/trade_commands.py`,
  `frontend/src/app/api/`)

They share no file and no symbol.

---

# Phase 1 — Payoff ratio

### Task R2-01: The payoff-ratio computation

**Files:**
- Modify: `swingbot/core/analytics/metrics.py` (beside `profit_factor`, line ~234)
- Test: `tests/analytics/test_metrics_ratios.py`

**Interfaces:**
- Consumes: `r_multiples(closed)`, already in `metrics.py:289`.
- Produces:
  - `payoff_ratio_from_rs(rs: list[float]) -> float | None`
  - `payoff_ratio(closed: list[dict]) -> float | None`

  R2-02 calls the first with its own leg-expanded list.

**Why two entry points.** `performance.get_extended_stats` already has the
leg-expanded R list in hand, and recomputing it from dicts there would risk the
payoff ratio and `expectancy_r` disagreeing about which legs count — the exact
drift `metrics.py`'s "one definition per stat" rule exists to stop. The
arithmetic lives in `payoff_ratio_from_rs`; `payoff_ratio` is the convenience
wrapper for callers holding trade dicts.

- [ ] **Step 1: Write the failing tests**

Add to `tests/analytics/test_metrics_ratios.py`:

```python
from swingbot.core.analytics.metrics import payoff_ratio_from_rs


def test_payoff_ratio_is_mean_win_over_mean_loss():
    # wins mean 2.0, losses mean -1.0 -> 2.0
    assert payoff_ratio_from_rs([3.0, 1.0, -1.0, -1.0]) == 2.0


def test_payoff_ratio_uses_means_not_sums():
    # One big winner and two small losers: mean win 4.0, mean loss -1.0.
    # A sum-based ratio would give 4.0/2.0 = 2.0; the mean-based answer is 4.0.
    assert payoff_ratio_from_rs([4.0, -1.0, -1.0]) == 4.0


def test_payoff_ratio_is_none_without_losers():
    # Mathematically infinite, reported as None -- same choice profit_factor
    # already makes, and for the same reason: "no losses yet" is a different
    # message from a huge finite number.
    assert payoff_ratio_from_rs([1.0, 2.0]) is None


def test_payoff_ratio_is_none_without_winners():
    assert payoff_ratio_from_rs([-1.0, -2.0]) is None


def test_payoff_ratio_is_none_when_empty():
    assert payoff_ratio_from_rs([]) is None


def test_payoff_ratio_ignores_breakeven_legs():
    # A scratch is neither a win nor a loss and must not drag either mean.
    assert payoff_ratio_from_rs([2.0, 0.0, -1.0]) == 2.0
```

- [ ] **Step 2: Run them and watch them fail**

```bash
python scripts/dev/testrun.py file tests/analytics/test_metrics_ratios.py
```

Expected: FAIL — `ImportError: cannot import name 'payoff_ratio_from_rs'`.

- [ ] **Step 3: Implement it**

In `swingbot/core/analytics/metrics.py`, directly after `profit_factor`:

```python
def payoff_ratio_from_rs(rs: list[float]) -> float | None:
    """Mean winning R divided by the magnitude of mean losing R -- "when this
    wins, how much bigger is the win than a typical loss".

    Takes R-multiples rather than trades so a caller that already expanded
    legs (performance.get_extended_stats) passes the SAME list it computed
    expectancy_r from. That matters: win rate and payoff ratio together
    decompose expectancy, and a decomposition whose parts were measured over
    different populations is not one.

    Breakeven legs (r == 0) are neither win nor loss and are excluded from
    both means -- counted as wins they would deflate the numerator, counted
    as losses they would deflate the denominator, and they are honestly
    neither.

    None when either side is empty: with no losers the ratio is infinite, and
    reporting None instead keeps every consumer's formatting simple and says
    "not enough outcomes yet" rather than a misleadingly large number. Same
    choice profit_factor makes above.
    """
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    if not wins or not losses:
        return None
    mean_win = sum(wins) / len(wins)
    mean_loss = abs(sum(losses) / len(losses))
    if mean_loss == 0:
        return None
    return mean_win / mean_loss


def payoff_ratio(closed: list[dict]) -> float | None:
    """payoff_ratio_from_rs over every computable R in `closed`. The entry
    point for callers holding trade dicts rather than a prepared R list."""
    return payoff_ratio_from_rs(r_multiples(closed))
```

- [ ] **Step 4: Run them and watch them pass**

```bash
python scripts/dev/testrun.py file tests/analytics/test_metrics_ratios.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/metrics.py tests/analytics/test_metrics_ratios.py
git commit -m "feat(analytics): add payoff ratio beside profit factor"
```

---

### Task R2-02: Expose payoff ratio from get_extended_stats

**Files:**
- Modify: `swingbot/core/tracking/performance.py:921-988` (`get_extended_stats`)
- Test: `tests/analytics/test_metrics_legged_trades.py`

**Interfaces:**
- Consumes: `payoff_ratio_from_rs` from R2-01.
- Produces: a `"payoff_ratio"` key in `get_extended_stats`'s returned dict,
  consumed by R2-03.

- [ ] **Step 1: Write the failing test**

Add to `tests/analytics/test_metrics_legged_trades.py` (it already builds
`TradeLog` fixtures with win/loss legs — reuse that file's existing helper for
constructing trades rather than inventing a second fixture shape):

```python
def test_extended_stats_reports_payoff_ratio_over_the_same_legs_as_expectancy(tmp_path, monkeypatch):
    log = _trade_log(tmp_path, monkeypatch)  # the helper this module already uses
    # Two wins at +2R and +4R, two losses at -1R and -1R.
    # expectancy_r = (2 + 4 - 1 - 1) / 4 = 1.0
    # payoff_ratio = mean(2, 4) / |mean(-1, -1)| = 3.0
    _add_closed(log, r=2.0, status="win")
    _add_closed(log, r=4.0, status="win")
    _add_closed(log, r=-1.0, status="loss")
    _add_closed(log, r=-1.0, status="loss")

    stats = log.get_extended_stats()
    assert stats["expectancy_r"] == pytest.approx(1.0)
    assert stats["payoff_ratio"] == pytest.approx(3.0)


def test_extended_stats_payoff_ratio_is_none_with_no_losses(tmp_path, monkeypatch):
    log = _trade_log(tmp_path, monkeypatch)
    _add_closed(log, r=2.0, status="win")
    assert log.get_extended_stats()["payoff_ratio"] is None
```

Read the top of that test module first and use its real fixture/helper names
in place of `_trade_log` / `_add_closed`.

- [ ] **Step 2: Run it and watch it fail**

```bash
python scripts/dev/testrun.py file tests/analytics/test_metrics_legged_trades.py
```

Expected: FAIL — `KeyError: 'payoff_ratio'`.

- [ ] **Step 3: Add the key**

In `performance.py`, add the import at the top beside the other metrics
imports, then extend the return dict of `get_extended_stats`:

```python
        return {
            "expectancy_r": (sum(r_multiples) / len(r_multiples)) if r_multiples else None,
            "r_multiples_count": len(r_multiples),
            # The SAME r_multiples list expectancy_r is averaged from, so win
            # rate and payoff ratio genuinely decompose expectancy rather than
            # describing two different populations -- v85 D9.
            "payoff_ratio": payoff_ratio_from_rs(r_multiples),
            "avg_holding_days": (sum(holding_days) / len(holding_days)) if holding_days else None,
            "avg_open_confidence": (sum(open_confidences) / len(open_confidences)) if open_confidences else None,
        }
```

Also extend this method's docstring with a `payoff_ratio` bullet, matching the
style of the three already documented there.

- [ ] **Step 4: Run it and watch it pass**

```bash
python scripts/dev/testrun.py file tests/analytics/test_metrics_legged_trades.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/tracking/performance.py tests/analytics/test_metrics_legged_trades.py
git commit -m "feat(tracking): report payoff ratio from get_extended_stats"
```

---

### Task R2-03: Payoff ratio on the dashboard payload and in the client

**Files:**
- Modify: `swingbot/admin/api_v1/dashboard.py:197-230`
- Modify: `frontend/src/app/api/models.ts` (the `Dashboard` interface)
- Modify: `frontend/src/app/stores/dashboard.store.ts:110-113`
- Test: `tests/admin/test_api_v1_dashboard.py`
- Test: `frontend/src/app/stores/dashboard.store.spec.ts`

**Interfaces:**
- Consumes: `get_extended_stats()["payoff_ratio"]` from R2-02.
- Produces:
  - payload key `payoff_ratio: number | null`
  - `DashboardStore.payoffRatio: Signal<number | null>`, consumed by R3-02.

- [ ] **Step 1: Write the failing tests**

Backend, in `tests/admin/test_api_v1_dashboard.py` (follow the module's
existing client fixture):

```python
def test_dashboard_reports_payoff_ratio(client):
    body = client.get("/api/v1/dashboard").get_json()
    assert "payoff_ratio" in body


def test_dashboard_payoff_ratio_is_null_not_zero_without_outcomes(client):
    # An empty book has no winners and no losers. null means "not enough
    # outcomes"; 0.0 would claim wins are worth nothing against losses.
    body = client.get("/api/v1/dashboard").get_json()
    assert body["payoff_ratio"] is None
```

Frontend, in `frontend/src/app/stores/dashboard.store.spec.ts`, following the
store spec's existing pattern for asserting a computed over a stubbed payload:

```ts
it('exposes payoff ratio, and keeps null distinct from zero', () => {
  // …arrange the store with a payload whose payoff_ratio is 2.5
  expect(store.payoffRatio()).toBe(2.5);
  // …and again with null
  expect(store.payoffRatio()).toBeNull();
});
```

- [ ] **Step 2: Run them and watch them fail**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py
cd frontend && npx ng test --include src/app/stores/dashboard.store.spec.ts
```

Expected: FAIL on both — the key is absent, `payoffRatio` is not a function.

- [ ] **Step 3: Add it on both sides**

In `swingbot/admin/api_v1/dashboard.py`, in the `jsonify({...})` block beside
`expectancy_r`:

```python
        "expectancy_r": stats.get("expectancy_r"),
        # v85 D9. Beside expectancy deliberately: win rate and payoff ratio
        # decompose it, so the three travel together.
        "payoff_ratio": stats.get("payoff_ratio"),
```

Update the module docstring's chip list at line ~14 to name it too.

In `frontend/src/app/api/models.ts`, add to the `Dashboard` interface:

```ts
  payoff_ratio: number | null;
```

In `frontend/src/app/stores/dashboard.store.ts`, beside `expectancyR`:

```ts
    payoffRatio: computed(() => data()?.payoff_ratio ?? null),
```

- [ ] **Step 4: Run them and watch them pass**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py
cd frontend && npx ng test --include src/app/stores/dashboard.store.spec.ts
```

Expected: PASS on both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/dashboard.py tests/admin/test_api_v1_dashboard.py \
        frontend/src/app/api/models.ts frontend/src/app/stores/dashboard.store.ts \
        frontend/src/app/stores/dashboard.store.spec.ts
git commit -m "feat(dashboard): serve payoff ratio and bind it in the client"
```

---

# Phase 2 — Bulk close

### Task R2-04: Extract the single-position close

**Files:**
- Modify: `swingbot/admin/api_v1/trade_commands.py:103-142` (`close_trade`)
- Test: `tests/admin/test_api_v1_trade_commands.py`

**Interfaces:**
- Consumes: `_CLOSEABLE_PLAN`, `_OPEN_LEGACY`, `_linked_trade`,
  `_queue_notify`, `record_transition`, `PlanStatus`, `PlanStore`, `TradeLog` —
  all already in this module.
- Produces: `_close_plan(store: PlanStore, plan) -> None`, called by both
  `close_trade` (R2-04) and `close_open` (R2-05).

**This task must not change any behaviour.** It is a pure extraction so the
bulk endpoint cannot drift from the single one. The existing trade-command
tests are the proof: they must pass untouched.

- [ ] **Step 1: Write the failing test**

Add to `tests/admin/test_api_v1_trade_commands.py`:

```python
def test_closing_a_plan_queues_a_notify_record(client, tmp_data_dir):
    """The bot is a separate process; this file is how it learns. A close that
    skips it silently stops the Discord trade-history channel."""
    plan_id = _seed_active_plan(client)          # module's existing helper
    client.post(f"/api/v1/trades/{plan_id}/close")

    queued = json.loads((tmp_data_dir / "manual_close_notify.json").read_text())
    assert any(r.get("plan_id") == plan_id for r in queued)
```

Use the module's real fixtures in place of `_seed_active_plan` /
`tmp_data_dir`; read its top before writing this.

- [ ] **Step 2: Run it and watch it pass or fail**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_commands.py
```

This one may already PASS — the behaviour exists. That is fine and expected:
it is a **characterisation test**, pinning the notify obligation before the
refactor moves the code that satisfies it. If it fails, the fixture names are
wrong, not the behaviour.

- [ ] **Step 3: Extract the helper**

In `trade_commands.py`, above `close_trade`:

```python
def _close_plan(store: PlanStore, plan) -> None:
    """Close one ACTIVE/PARTIAL plan: settle its linked legacy trade, record
    the transition, and queue the bot's notification.

    Extracted from close_trade so the bulk endpoint runs exactly this and
    cannot drift from the single-position path. The caller checks status.
    """
    tl = TradeLog()
    linked = _linked_trade(tl, plan.plan_id)
    if linked and linked.get("status") == _OPEN_LEGACY:
        # Through TradeLog's own locked mutator: the admin and the bot are
        # separate processes over one trades.json, so an unlocked
        # read-modify-write here could race the scan loop.
        tl.close_trade_manual(linked["id"], reason="manual (plan close, admin UI)")
    # `at` is passed explicitly -- record_transition defaults it to None, and
    # the lifecycle strip's "today" counts read status_history[-1]["at"].
    record_transition(plan, PlanStatus.CLOSED, reason="manual",
                      at=datetime.now(timezone.utc).isoformat())
    store.update(plan)
    _queue_notify({"kind": "plan_transition", "plan_id": plan.plan_id,
                   "ticker": plan.ticker, "status": plan.status})
```

Then replace that same block inside `close_trade`'s plan branch with:

```python
        _close_plan(store, plan)
        return _plan_row(trade_id)
```

- [ ] **Step 4: Run the whole trade-command file and watch it pass**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_commands.py
```

Expected: PASS, including every pre-existing test. A refactor that changed
behaviour shows up here.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/trade_commands.py tests/admin/test_api_v1_trade_commands.py
git commit -m "refactor(api): extract _close_plan so bulk and single close share one path"
```

---

### Task R2-05: The bulk-close endpoint

**Files:**
- Modify: `swingbot/admin/api_v1/trade_commands.py` (new route beside the bulk clears, line ~205)
- Test: `tests/admin/test_api_v1_trade_commands.py`

**Interfaces:**
- Consumes: `_close_plan` from R2-04.
- Produces: `POST /api/v1/trades/close-open` returning
  `{"closed": int, "failed": int, "tickers": list[str]}`.

**This is not `clear-open`.** That route deletes records
(`performance.py:1267`) and realises nothing. This one closes positions. They
sit next to each other in the same file and mean opposite things — the
docstring below is load-bearing.

- [ ] **Step 1: Write the failing tests**

```python
def test_close_open_closes_active_and_partial(client):
    active = _seed_active_plan(client)
    partial = _seed_partial_plan(client)

    body = client.post("/api/v1/trades/close-open").get_json()

    assert body["closed"] == 2
    assert body["failed"] == 0
    assert sorted(body["tickers"]) == sorted([_ticker(active), _ticker(partial)])


def test_close_open_leaves_pending_plans_alone(client):
    """A plan that never filled cannot be closed -- cancelling is the act that
    means something for one, and it is a different act."""
    pending = _seed_pending_plan(client)

    body = client.post("/api/v1/trades/close-open").get_json()

    assert body["closed"] == 0
    assert _plan_status(client, pending) == "PENDING"


def test_close_open_on_an_empty_book_is_a_no_op(client):
    body = client.post("/api/v1/trades/close-open").get_json()
    assert body == {"closed": 0, "failed": 0, "tickers": []}


def test_close_open_queues_one_notify_record_per_position(client, tmp_data_dir):
    _seed_active_plan(client)
    _seed_active_plan(client)

    client.post("/api/v1/trades/close-open")

    queued = json.loads((tmp_data_dir / "manual_close_notify.json").read_text())
    assert len([r for r in queued if r.get("kind") == "plan_transition"]) == 2


def test_close_open_reports_failures_without_aborting_the_rest(client, monkeypatch):
    """One bad position must not strand the others half-closed."""
    _seed_active_plan(client)
    good = _seed_active_plan(client)

    calls = {"n": 0}
    real = trade_commands._close_plan

    def flaky(store, plan):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(store, plan)

    monkeypatch.setattr(trade_commands, "_close_plan", flaky)

    body = client.post("/api/v1/trades/close-open").get_json()
    assert body["closed"] == 1
    assert body["failed"] == 1
```

- [ ] **Step 2: Run them and watch them fail**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_commands.py
```

Expected: FAIL — 404, the route does not exist.

- [ ] **Step 3: Add the route**

In `trade_commands.py`, in the bulk-clears section:

```python
@api_v1.route("/trades/close-open", methods=["POST"])
@require_auth
def close_open():
    """Close every ACTIVE/PARTIAL position at its current price.

    **This is not `/trades/clear-open`.** That one DELETES open trade records
    and realises nothing; this one banks them. The two live in the same file
    and read one word apart, so check which you are calling.

    PENDING plans are untouched: one that never filled has nothing to close,
    and cancelling it is a different act with a different meaning.

    Per position it runs `_close_plan` -- the same path the single-position
    close uses, including the manual-close notify record the bot reads.

    One failure does not abort the rest: a half-closed book with no report of
    which half is worse than a partial success that says so.
    """
    store = PlanStore()
    closed, failed, tickers = 0, 0, []
    for plan in list(store._plans.values()):
        if plan.status not in _CLOSEABLE_PLAN:
            continue
        try:
            _close_plan(store, plan)
            closed += 1
            tickers.append(plan.ticker)
        except Exception:
            log.exception("bulk close failed for plan %s", plan.plan_id)
            failed += 1
    return jsonify({"closed": closed, "failed": failed, "tickers": tickers})
```

`list(...)` around the values: `_close_plan` writes through `store.update`, and
iterating a mapping being mutated is how this becomes an intermittent
`RuntimeError` in production rather than in the test.

- [ ] **Step 4: Run them and watch them pass**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_commands.py
```

Expected: PASS, all five plus the pre-existing tests.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/trade_commands.py tests/admin/test_api_v1_trade_commands.py
git commit -m "feat(api): add POST /trades/close-open to bank every open position"
```

---

### Task R2-06: Client binding for bulk close

**Files:**
- Modify: `frontend/src/app/api/api-client.ts:137-143`
- Modify: `frontend/src/app/api/models.ts`
- Test: `frontend/src/app/api/api-client.spec.ts`

**Interfaces:**
- Consumes: the endpoint from R2-05.
- Produces: `ApiClient.closeOpenTrades(): Observable<CloseOpenResult>` and
  `interface CloseOpenResult { closed: number; failed: number; tickers: string[] }`,
  consumed by R4-06.

- [ ] **Step 1: Write the failing test**

In `frontend/src/app/api/api-client.spec.ts`, following the file's existing
`HttpTestingController` pattern:

```ts
it('posts to close-open and returns the summary', () => {
  let result: CloseOpenResult | undefined;
  api.closeOpenTrades().subscribe((r) => (result = r));

  const req = httpMock.expectOne('/api/v1/trades/close-open');
  expect(req.request.method).toBe('POST');
  req.flush({ closed: 2, failed: 0, tickers: ['ASTS', 'HOOD'] });

  expect(result).toEqual({ closed: 2, failed: 0, tickers: ['ASTS', 'HOOD'] });
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/api/api-client.spec.ts
```

Expected: FAIL — `api.closeOpenTrades is not a function`.

- [ ] **Step 3: Add the method and the type**

In `models.ts`, beside `ClearResult`:

```ts
/** What POST /trades/close-open reports. `failed` is separate from `closed`
 *  on purpose: a partial success has to be able to say so. */
export interface CloseOpenResult {
  closed: number;
  failed: number;
  tickers: string[];
}
```

In `api-client.ts`, beside `clearOpenTrades` — and directly above it, so the
next reader meets both at once:

```ts
  /** Banks every ACTIVE/PARTIAL position. NOT clearOpenTrades below, which
   *  deletes the records instead. */
  closeOpenTrades(): Observable<CloseOpenResult> {
    return this.http.post<CloseOpenResult>(`${this.base}/trades/close-open`, {});
  }
```

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/api/api-client.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/api/api-client.ts frontend/src/app/api/models.ts \
        frontend/src/app/api/api-client.spec.ts
git commit -m "feat(api-client): bind the bulk close endpoint"
```
