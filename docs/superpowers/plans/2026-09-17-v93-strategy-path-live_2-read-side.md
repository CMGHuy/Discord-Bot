# Strategy path goes live — Part 2: Phase 1b (read side: analytics, dashboard, Discord, admin API, frontend, docs)

Index, header block, global constraints and the parallelisation map: `2026-09-17-v93-strategy-path-live_0-index.md`. Spec: `docs/superpowers/specs/2026-09-17-v93-strategy-path-live-design.md` (§1 trust rule surface, §2 reporting).

# Phase 1b — Read side

### Task 10: `ledger` analytics dimension and the snapshot's `weak` block

**Files:**
- Modify: `swingbot/core/analytics/aggregate.py` (`DIMENSIONS`, `_EXTRACTORS`, ~L96–110)
- Modify: `swingbot/core/analytics/snapshots.py` (`build_snapshot` ~L25–66, `refresh_snapshot` ~L94–115)
- Test: `tests/analytics/test_aggregate.py`, `tests/analytics/test_snapshots_ledger.py`

**Interfaces:**
- Consumes: `tracking.ledger.split_by_ledger`, `is_main` (Task 2).
- Produces: `DIMENSIONS` includes `"ledger"`; `build_snapshot(closed, starting_balance, registry_entries, *, weak_closed=())` adds `snap["weak"] = {n, wins, losses, win_rate, expectancy_r, total_pnl}` and computes `by["ledger"]` over main+weak while every other figure stays main-only.

- [ ] **Step 1: Write the failing tests**

Append to `tests/analytics/test_aggregate.py`:

```python
def test_ledger_dimension_defaults_missing_to_main():
    closed = [
        _t(["EMA20"], "win", 80.0),
        {**_t(["EMA20"], "loss", -40.0), "ledger": "weak"},
        {**_t(["EMA20"], "win", 10.0), "ledger": "main"},
    ]
    assert "ledger" in DIMENSIONS
    rows = {r.key: r for r in stats_by(closed, "ledger")}
    assert rows["main"].n == 2 and rows["weak"].n == 1
    assert rows["weak"].total_pnl == -40.0
```

`tests/analytics/test_snapshots_ledger.py`:

```python
from swingbot.core.analytics.snapshots import build_snapshot


def _t(status, pnl, ledger=None, day="2026-09-10"):
    t = {"target_sources": ["EMA20"], "status": status, "direction": "bullish",
         "entry": 100.0, "stop_loss": 95.0,
         "exit_price": 104.0 if status == "win" else 96.0,
         "realized_pnl_amount": pnl,
         "opened_at": f"{day}T10:00:00+00:00", "closed_at": f"{day}T15:00:00+00:00"}
    if ledger:
        t["ledger"] = ledger
    return t


def test_weak_block_is_separate_and_never_summed_into_overall():
    main = [_t("win", 100.0), _t("loss", -40.0)]
    weak = [_t("loss", -50.0, "weak"), _t("win", 80.0, "weak")]
    snap = build_snapshot(main, 10_000.0, [], weak_closed=weak)
    assert snap["overall"]["n"] == 2
    assert snap["overall"]["total_pnl"] == 60.0            # main only
    assert snap["weak"] == {"n": 2, "wins": 1, "losses": 1, "win_rate": 50.0,
                            "expectancy_r": snap["weak"]["expectancy_r"], "total_pnl": 30.0}
    assert snap["weak"]["expectancy_r"] is not None
    by_ledger = {r["key"]: r for r in snap["by"]["ledger"]}
    assert by_ledger["main"]["n"] == 2 and by_ledger["weak"]["n"] == 2


def test_weak_block_empty_is_a_measured_zero():
    snap = build_snapshot([_t("win", 10.0)], 10_000.0, [])
    assert snap["weak"] == {"n": 0, "wins": 0, "losses": 0, "win_rate": None,
                            "expectancy_r": None, "total_pnl": 0.0}
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/analytics/test_aggregate.py::test_ledger_dimension_defaults_missing_to_main tests/analytics/test_snapshots_ledger.py -v`
Expected: FAIL (`"ledger" in DIMENSIONS` false; `TypeError: unexpected keyword 'weak_closed'`)

- [ ] **Step 3: Implement**

`aggregate.py`: add `"ledger"` to the end of `DIMENSIONS` and `"ledger": lambda t: t.get("ledger") or "main",` to `_EXTRACTORS`.

`snapshots.py`, `build_snapshot`:
- signature → `def build_snapshot(closed, starting_balance, registry_entries, *, weak_closed=()) -> dict:`
- after the `by = {...}` line add:
```python
    # v93: every figure above is the MAIN ledger. The ledger breakdown is the
    # one row set computed over both, so the table shows them side by side;
    # the weak block is its own object and is never folded into `overall`.
    weak_closed = list(weak_closed)
    by["ledger"] = [dataclasses.asdict(row) for row in stats_by(closed + weak_closed, "ledger")]
    w_wins = sum(1 for t in weak_closed if t.get("status") == "win")
    w_losses = sum(1 for t in weak_closed if t.get("status") == "loss")
    weak = {
        "n": len(weak_closed), "wins": w_wins, "losses": w_losses,
        "win_rate": metrics.win_rate(weak_closed) if weak_closed else None,
        "expectancy_r": metrics.expectancy_r(weak_closed) if weak_closed else None,
        "total_pnl": round(sum(float(t.get("realized_pnl_amount") or 0.0) for t in weak_closed), 2),
    }
```
  and include `"weak": weak,` in the returned dict next to `"by": by,`.
- `refresh_snapshot`: replace the `closed = [...]` line with
```python
        from swingbot.core.tracking.ledger import split_by_ledger
        closed_all = [t for t in all_trades if t.get("status") in ("win", "loss", "closed")]
        closed, weak_closed = split_by_ledger(closed_all)
```
  and call `build_snapshot(closed, starting_balance, registry_entries, weak_closed=weak_closed)`.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/analytics/test_aggregate.py`, `... tests/analytics/test_snapshots_ledger.py`, `... tests/analytics/test_snapshots.py`
Expected: green. If `metrics.win_rate` on the weak list returns a float the fixture's `50.0` comparison holds; if `equity_curve` demands more fields, add them to `_t` rather than weakening assertions.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/aggregate.py swingbot/core/analytics/snapshots.py tests/analytics/test_aggregate.py tests/analytics/test_snapshots_ledger.py
git commit -m "feat(v93): ledger analytics dimension; snapshot main-only figures + separate weak block"
```

---

### Task 11: Dashboard and performance APIs report `main`; add `realized_weak` / `weak`

**Files:**
- Modify: `swingbot/admin/api_v1/dashboard.py` (`dashboard()` ~L178–215)
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_performance()` ~L72–150)
- Test: `tests/admin/test_api_v1_dashboard.py`, `tests/admin/test_api_v1_analytics.py`

**Interfaces:**
- Consumes: `ledger.split_by_ledger`, `is_main`; `TradeLog.weak_summary()` (Task 3).
- Produces: `GET /api/v1/dashboard` → `realized` (main) unchanged in meaning + new `realized_weak` (same shape); `win_rate`/`expectancy_r` chips computed over main. `GET /api/v1/analytics/performance` → totals/win_rate/expectancy over main + new top-level `weak` block (`weak_summary()` shape).

- [ ] **Step 1: Write the failing tests**

In `tests/admin/test_api_v1_dashboard.py` add `"realized_weak": dict,` to the `DASHBOARD` shape dict and append:

```python
def test_realized_weak_is_separate(client, auth, tmp_path):
    from swingbot import config
    from swingbot.core.tracking.performance import TradeLog
    log = TradeLog()   # admin_app fixture already points config.DATA_DIR at tmp_path
    a = log.log_trade(ticker="AAPL", strategy="MACD", horizon_key="3m", direction="bullish",
                      confidence_level=None, confidence_label="strategy signal",
                      entry=100.0, stop_loss=95.0, take_profit=110.0, source="strategy", badge="VALIDATED", ledger="main")
    b = log.log_trade(ticker="MSFT", strategy="RSI", horizon_key="3m", direction="bullish",
                      confidence_level=None, confidence_label="strategy signal",
                      entry=100.0, stop_loss=95.0, take_profit=110.0, source="strategy", badge="WEAK", ledger="weak")
    for tid, status, px, pnl in ((a, "win", 110.0, 100.0), (b, "loss", 95.0, -50.0)):
        t = log.get_trade(tid)
        t.update(status=status, exit_price=px, realized_pnl_amount=pnl, closed_at="2026-09-17T20:00:00+00:00")
    log._save()
    body = client.get("/api/v1/dashboard?mode=all", headers=auth).get_json()
    assert body["realized"]["n"] == 1 and body["realized"]["amount"] == 100.0
    assert body["realized_weak"]["n"] == 1 and body["realized_weak"]["amount"] == -50.0
    assert body["win_rate_n"] == 1            # chips are main-only
```

In `tests/admin/test_api_v1_analytics.py` append:

```python
def test_performance_has_weak_block_and_main_totals(client, auth):
    body = client.get("/api/v1/analytics/performance", headers=auth).get_json()
    assert set(body["weak"]) == {"n", "wins", "losses", "win_rate", "expectancy_r", "total_pnl"}
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/admin/test_api_v1_dashboard.py::test_realized_weak_is_separate tests/admin/test_api_v1_analytics.py::test_performance_has_weak_block_and_main_totals -v`
Expected: FAIL with `KeyError: 'realized_weak'` / `KeyError: 'weak'`

- [ ] **Step 3: Implement**

`dashboard.py`, inside `dashboard()` after `scoped_raw = ...`:
```python
    from swingbot.core.tracking.ledger import is_main, split_by_ledger
    scoped_main = [t for t in scoped_raw if is_main(t)]
    stats = tl.get_stats(trades=scoped_main)
    stats.update(tl.get_extended_stats(trades=scoped_main))
    from swingbot.core.analytics import metrics as m
    closed_scoped_all = [t for t in scoped_raw if t.get("status") in ("win", "loss", "closed")]
    closed_scoped, closed_weak = split_by_ledger(closed_scoped_all)
    scoped_rs = m.r_multiples(closed_scoped)
```
(replacing the existing `stats = ...`, `stats.update(...)`, `closed_scoped = ...`, `scoped_rs = ...` lines). Where the payload builds `"realized": _realized(closed_scoped, mode)`, add `"realized_weak": _realized(closed_weak, mode),`.

`analytics.py`, `analytics_performance()`: change `all_raw = tl.get_trades(status=None, limit=None) or []` to `all_raw = tl.get_trades(status=None, limit=None, ledger="main") or []` and add `"weak": tl.weak_summary(),` to the returned payload (top level, next to `"by_confidence"`).

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py` and `... tests/admin/test_api_v1_analytics.py` and `... tests/admin/test_api_v1_contract.py`
Expected: green (if the contract test pins the performance payload's key set, add `weak`).

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/dashboard.py swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_dashboard.py tests/admin/test_api_v1_analytics.py tests/admin/test_api_v1_contract.py
git commit -m "feat(v93): dashboard/performance APIs report the main ledger + separate weak blocks"
```

---

### Task 12: Discord — WEAK block in `!stats`/`!performance`, new `!soak <strategy>`

**Files:**
- Modify: `swingbot/commands/stats.py` (`stats_embed` ~L120; new `soak_lines`, `soak_cmd`)
- Modify: `swingbot/commands/trades.py` (`performance_cmd` ~L376–410)
- Modify: `swingbot/commands/slash.py` (add `/soak` bridge next to `/stats`)
- Test: `tests/test_stats_commands.py`, `tests/test_slash_commands.py`

**Interfaces:**
- Consumes: `snap["weak"]` (Task 10); `TradeLog.weak_summary()` (Task 3); `strategy_soak.soak_verdict` (Task 9); `registry.get_badge("strategy", name)`; `PlanStore().all()`.
- Produces: `stats.soak_lines(strategy: str, verdict: dict, badge) -> list[str]`; `!soak <strategy>` and `/soak`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_stats_commands.py`:

```python
def test_stats_embed_renders_weak_block_separately():
    snap = {
        "built_at": "2026-09-17T00:00:00", "overall": {
            "n": 3, "wins": 2, "losses": 1, "win_rate": 66.7, "expectancy_r": 0.2, "profit_factor": 1.5,
            "sharpe": None, "sortino": None, "max_drawdown_pct": 3.0, "total_pnl": 120.0,
            "streaks": {"current": 1, "current_kind": "win", "best_win_streak": 2, "worst_loss_streak": 1}},
        "by": {}, "weak": {"n": 2, "wins": 1, "losses": 1, "win_rate": 50.0, "expectancy_r": -0.1, "total_pnl": -30.0},
    }
    embed = stats_embed(snap)
    weak = next(f for f in embed.fields if f.name.startswith("WEAK ledger"))
    assert "N 2" in weak.value and "-30.00" in weak.value
    assert "120.00" in embed.description          # main total untouched


def test_stats_embed_without_weak_key_is_unchanged():
    snap = {"built_at": None, "overall": {"n": 0, "wins": 0, "losses": 0, "win_rate": None, "expectancy_r": None,
            "profit_factor": None, "sharpe": None, "sortino": None, "max_drawdown_pct": None, "total_pnl": 0.0,
            "streaks": {"current": 0, "current_kind": None, "best_win_streak": 0, "worst_loss_streak": 0}}, "by": {}}
    assert not any(f.name.startswith("WEAK ledger") for f in stats_embed(snap).fields)


def test_soak_lines_reports_each_clause():
    from swingbot.commands.stats import soak_lines
    from swingbot.core.backtesting.registry import Badge
    verdict = {"n_closed": 12, "exp_r": 0.15, "badge_exp_r": 0.219, "median_entry_dev": 0.04,
               "clauses": {"n": False, "non_inferior": False, "entry_parity": True}, "pass": False}
    lines = soak_lines("MACD", verdict, Badge(status="VALIDATED", n=112, win_rate=50.0, expectancy_r=0.219))
    text = "\n".join(lines)
    assert "MACD" in text and "12/30" in text and "FAIL" in text and "PASS" in text
    assert "not ready" in text.lower()
```

Append to `tests/test_slash_commands.py` (it enumerates registered slash commands — follow its existing assertion style):

```python
def test_soak_slash_registered():
    from swingbot.bot_core import bot
    assert any(c.name == "soak" for c in bot.tree.get_commands())
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_stats_commands.py -k "weak or soak" tests/test_slash_commands.py::test_soak_slash_registered -v`
Expected: FAIL (`StopIteration` on the WEAK field; `ImportError: soak_lines`; no `soak` command)

- [ ] **Step 3: Implement**

`stats.py`, in `stats_embed` before `ui.apply_chrome(...)`:
```python
    weak = snap.get("weak")
    if weak:
        embed.add_field(
            name="WEAK ledger (separate — never summed into the figures above)",
            value=(f"**N** {weak['n']} ({weak['wins']}W/{weak['losses']}L)  ·  "
                   f"**Win rate** {ui.fmt_pct(weak['win_rate'])}  ·  "
                   f"**Expectancy** {ui.fmt_r(weak['expectancy_r'])}  ·  "
                   f"**P&L** {_dash(weak['total_pnl'], '{:+.2f}')}"),
            inline=False)
```

Add to `stats.py`:
```python
def soak_lines(strategy: str, verdict: dict, badge) -> list[str]:
    """v93 trust rule readout. One line per clause, each PASS/FAIL, and a
    verdict line -- the flip itself is a config edit (STRATEGY_ALERTS_LIVE_STRATEGIES)."""
    from swingbot.core.edge.strategy_soak import MAX_ENTRY_DEV, MIN_CLOSED
    c = verdict["clauses"]
    def pf(ok): return "PASS" if ok else "FAIL"
    exp = f"{verdict['exp_r']:+.3f}R" if verdict["exp_r"] is not None else "n/a"
    bexp = f"{verdict['badge_exp_r']:+.3f}R" if verdict["badge_exp_r"] is not None else "n/a (no badge sample)"
    dev = f"{verdict['median_entry_dev']:.3f}" if verdict["median_entry_dev"] is not None else "n/a"
    lines = [f"**Soak — {strategy}** ({badge.status}, badge OOS N={badge.n})",
             f"1. Closed shadow plans {verdict['n_closed']}/{MIN_CLOSED}: {pf(c['n'])}",
             f"2. Shadow ExpR {exp} vs badge {bexp} (margin −0.01R): {pf(c['non_inferior'])}",
             f"3. Median entry deviation {dev} of stop distance (≤ {MAX_ENTRY_DEV:.2f}): {pf(c['entry_parity'])}"]
    lines.append("**Verdict:** ready to flip to live — add it to STRATEGY_ALERTS_LIVE_STRATEGIES."
                 if verdict["pass"] else "**Verdict:** not ready — keep in shadow.")
    return lines


@bot.command(name="soak")
async def soak_cmd(ctx, *, strategy: str):
    from swingbot.core.backtesting.registry import get_badge
    from swingbot.core.edge.strategy_soak import soak_verdict
    plans = [p for p in PlanStore().all() if p.source == "strategy" and p.strategy == strategy]
    if not plans:
        await ctx.send(f"No strategy-sourced plans for `{strategy}` yet (is STRATEGY_ALERTS_MODE off?).")
        return
    badge = get_badge("strategy", strategy)
    await ctx.send("\n".join(soak_lines(strategy, soak_verdict(plans, badge), badge)))
```

`trades.py`, `performance_cmd`, after the `**Overall:**` line is appended:
```python
    weak = trade_log.weak_summary()
    wr_weak = f"{weak['win_rate']:.0f}%" if weak["win_rate"] is not None else "n/a"
    lines.append(f"**WEAK ledger (separate):** {wr_weak} win rate — {weak['wins']}W/{weak['losses']}L closed, "
                 f"P&L {weak['total_pnl']:+.2f}")
```
and make `overall = trade_log.get_stats()` explicit as `trade_log.get_stats(ledger="main")`.

`slash.py`, next to `/stats`:
```python
@bot.tree.command(name="soak", description="v93 trust-rule readout for a strategy's shadow plans")
@app_commands.describe(strategy="Exact strategy name, e.g. MACD")
async def slash_soak(interaction: discord.Interaction, strategy: str):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.stats import soak_cmd
    await soak_cmd.callback(ctx, strategy=strategy)
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/test_stats_commands.py` and `... tests/test_slash_commands.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/stats.py swingbot/commands/trades.py swingbot/commands/slash.py tests/test_stats_commands.py tests/test_slash_commands.py
git commit -m "feat(v93): WEAK ledger block in !stats/!performance; !soak and /soak trust-rule readout"
```

---

### Task 13: Admin API — `GET /analytics/soak?strategy=` and `soak` on `dim=strategy` rows

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py`
- Test: `tests/admin/test_api_v1_analytics.py`

**Interfaces:**
- Consumes: `strategy_soak.soak_verdict`, `PlanStore().all()`, `get_badge`.
- Produces: `GET /api/v1/analytics/soak?strategy=<name>` → `{strategy, badge: {status, n, expectancy_r}, verdict: <soak_verdict dict>}`; each `dim=strategy` row from `/analytics/by-dimension` gains `soak: {pass, n_closed, clauses} | null` (null when no shadow plans exist for it).

- [ ] **Step 1: Write the failing tests**

Append to `tests/admin/test_api_v1_analytics.py`:

```python
def test_soak_requires_strategy_param(client, auth):
    assert_error(client.get("/api/v1/analytics/soak", headers=auth), "invalid", 400)


def test_soak_endpoint_shape_with_no_plans(client, auth):
    body = client.get("/api/v1/analytics/soak?strategy=MACD", headers=auth).get_json()
    assert body["strategy"] == "MACD"
    assert set(body["badge"]) == {"status", "n", "expectancy_r"}
    assert body["verdict"]["n_closed"] == 0 and body["verdict"]["pass"] is False
    assert set(body["verdict"]["clauses"]) == {"n", "non_inferior", "entry_parity"}


def test_by_dimension_strategy_rows_carry_soak_key(client, auth):
    body = client.get("/api/v1/analytics/by-dimension?dim=strategy", headers=auth).get_json()
    for row in body["rows"]:
        assert "soak" in row
```
(If the by-dimension envelope key is not `rows`, use the name the existing tests in this file already read.)

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/admin/test_api_v1_analytics.py -k soak -v`
Expected: FAIL (404 on `/analytics/soak`; `KeyError: 'soak'`)

- [ ] **Step 3: Implement**

In `analytics.py` add:

```python
def _soak_for(strategy: str) -> tuple[dict, object]:
    from swingbot.core.backtesting.registry import get_badge
    from swingbot.core.edge.strategy_soak import soak_verdict
    from swingbot.core.planning.plan_store import PlanStore
    plans = [p for p in PlanStore().all() if p.source == "strategy" and p.strategy == strategy]
    badge = get_badge("strategy", strategy)
    return soak_verdict(plans, badge), badge


@api_v1.route("/analytics/soak", methods=["GET"])
@require_auth
def analytics_soak():
    """v93 trust rule (spec §1) for one strategy's shadow plans. Read-only:
    the flip to live is a config edit, never an API side effect."""
    unknown = set(request.args) - {"strategy"}
    if unknown:
        raise ApiError("invalid", f"unknown parameter {sorted(unknown)[0]!r}; allowed: ['strategy']", 400)
    strategy = (request.args.get("strategy") or "").strip()
    if not strategy:
        raise ApiError("invalid", "strategy is required", 400)
    verdict, badge = _soak_for(strategy)
    return jsonify({"strategy": strategy,
                    "badge": {"status": badge.status, "n": badge.n, "expectancy_r": badge.expectancy_r},
                    "verdict": verdict})
```

In `analytics_by_dimension()`, where each `dim == "strategy"` row dict is assembled (the place that attaches `badge`), add:
```python
            verdict, _ = _soak_for(row_strategy_name)
            row["soak"] = ({"pass": verdict["pass"], "n_closed": verdict["n_closed"], "clauses": verdict["clauses"]}
                           if verdict["n_closed"] or any(True for p in PlanStore().all() if p.source == "strategy" and p.strategy == row_strategy_name)
                           else None)
```
Use the row's existing strategy-name variable in place of `row_strategy_name`, and import `PlanStore` once at the top of the function rather than inside the loop.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics.py
git commit -m "feat(v93): /analytics/soak endpoint; soak verdict on strategy rows"
```

---

### Task 14: Frontend — ledger dimension, WEAK tile, WEAK realised card, soak column

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`Dashboard`, `AnalyticsSnapshot`, `AnalyticsPerformance`, `AnalyticsByDimensionRow`)
- Modify: `frontend/src/app/stores/analytics.store.ts` (`BREAKDOWN_DIMENSIONS`, new `weak*` computeds)
- Modify: `frontend/src/app/stores/dashboard.store.ts` (new `realizedWeak*` computeds)
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts` (two inputs + one card)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (pass the inputs)
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` (`kpiTiles` + soak column cell)
- Modify: `frontend/src/app/workspaces/analytics/analytics.columns.ts` (soak column def)
- Test: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, `frontend/src/app/workspaces/analytics/analytics.spec.ts`, `frontend/src/app/stores/analytics.store.spec.ts`

**Interfaces:**
- Consumes: Task 11's `realized_weak`, Task 10's `snapshot.weak`, Task 13's `row.soak`.
- Produces: `Dashboard.realized_weak`, `AnalyticsSnapshot.weak`, `AnalyticsByDimensionRow.soak`; store signals `realizedWeakAmount()`, `realizedWeakCount()`, `weakN()`, `weakPnl()`, `weakWinRate()`; a `ledger` option in the Breakdowns picker.

- [ ] **Step 1: Write the failing specs**

`dashboard.spec.ts` — in `payload()` add `realized: { amount: 100, pct: 1, n: 1, wins: 1, losses: 0 }, realized_weak: { amount: -50, pct: -0.5, n: 1, wins: 0, losses: 1 },` then a new test in the same `describe` (use the file's existing fixture-creation helper that flushes the `/api/v1/dashboard` request):

```ts
  it('renders the WEAK ledger card separately from realised', async () => {
    const { fixture, http } = create();                  // this file's existing helper name
    flushDashboard(http, payload());                     // and its existing flush helper
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('WEAK ledger');
    expect(text).toContain('-50');
    expect(text).toContain('100');
  });
```

`analytics.store.spec.ts`:

```ts
  it('exposes the weak block and offers ledger as a breakdown dimension', () => {
    const { store, http } = create();                    // this file's existing helper
    store.load();
    http.expectOne((r) => r.url.endsWith('/analytics/snapshot')).flush({
      built_at: null, overall: {}, equity_curve: null, drawdown: [], rolling_wr: [], by: {},
      calibration: {}, r_multiples: [],
      weak: { n: 2, wins: 1, losses: 1, win_rate: 50, expectancy_r: -0.1, total_pnl: -30 },
    });
    // other requests this store issues on load: flush them with empty payloads as the file already does
    expect(store.weakN()).toBe(2);
    expect(store.weakPnl()).toBe(-30);
    expect(BREAKDOWN_DIMENSIONS.some((d) => d.value === 'ledger')).toBe(true);
  });
```

`analytics.spec.ts`: extend the snapshot payload helper with the same `weak` block and assert the KPI row contains a tile labelled `WEAK ledger P&L`.

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npm test -- --include src/app/stores/analytics.store.spec.ts`
Expected: FAIL (`weakN is not a function`)

- [ ] **Step 3: Implement**

`models.ts`:
- `Dashboard`: add `realized_weak: Dashboard['realized'];` after `realized`.
- `AnalyticsSnapshot`: add `weak?: { n: number; wins: number; losses: number; win_rate: number | null; expectancy_r: number | null; total_pnl: number };`
- `AnalyticsPerformance`: add `weak?: AnalyticsSnapshot['weak'];`
- `AnalyticsByDimensionRow`: add `soak?: { pass: boolean; n_closed: number; clauses: Record<string, boolean> } | null;`

`analytics.store.ts`:
- `BREAKDOWN_DIMENSIONS`: append `{ value: 'ledger', label: 'Ledger' },`.
- next to `totalPnl`: 
```ts
    weakN: computed(() => snapshot()?.weak?.n ?? null),
    weakPnl: computed(() => snapshot()?.weak?.total_pnl ?? null),
    weakWinRate: computed(() => snapshot()?.weak?.win_rate ?? null),
```

`dashboard.store.ts`, next to `realizedAmount`:
```ts
    realizedWeakAmount: computed(() => data()?.realized_weak?.amount ?? null),
    realizedWeakCount: computed(() => data()?.realized_weak?.n ?? 0),
```

`trading-performance.ts`: add inputs
```ts
  readonly realizedWeakAmount = input<number | null>(null);
  readonly realizedWeakCount = input(0);
```
and, directly after the existing realised `<sb-metric-card ...>`, 
```html
          <sb-metric-card label="WEAK ledger (separate)" [value]="realizedWeakAmount()"
                          [hint]="realizedWeakCount() + ' closed — never summed into realised'" />
```
(if `sb-metric-card` has no `hint` input, render the count in the label string instead: `[label]="'WEAK ledger (' + realizedWeakCount() + ' closed, separate)'"`).

`dashboard.ts`: pass `[realizedWeakAmount]="store.realizedWeakAmount()" [realizedWeakCount]="store.realizedWeakCount()"` on `<sb-trading-performance>`.

`analytics.ts`, `kpiTiles`: append
```ts
    { label: 'WEAK ledger P&L', value: this.fmtMoney(this.store.weakPnl()), sample: this.store.weakN() },
```
(use whatever money formatter the component already exposes for `totalPnl`; if none, `this.store.weakPnl() === null ? null : this.store.weakPnl()!.toFixed(2)`).

Soak column: in `analytics.columns.ts` add a column definition with `key: 'soak'` and label `Soak` to the strategies table's column list, and in `analytics.ts`'s strategies table template render the cell as:
```html
      @if (row.soak) {
        <span [class.ok]="row.soak.pass">{{ row.soak.pass ? 'PASS' : 'FAIL' }} · {{ row.soak.n_closed }}/30</span>
      } @else { <span class="muted">—</span> }
```

- [ ] **Step 4: Run the specs**

Run: `cd frontend && npm test -- --include src/app/stores/analytics.store.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/analytics/analytics.spec.ts`
Expected: green. Also `npm test -- --include src/app/workspaces/workspace-consistency.spec.ts`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/dashboard.store.ts frontend/src/app/workspaces/dashboard/panels/trading-performance.ts frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/analytics/analytics.ts frontend/src/app/workspaces/analytics/analytics.columns.ts frontend/src/app/**/*.spec.ts
git commit -m "feat(v93): WEAK ledger card + tile, ledger breakdown dimension, soak column"
```

---

### Task 15: Docs for Phase 1

**Files:**
- Modify: `docs/commands.md` (table row after `!performance`)
- Modify: `docs/strategy/strategy-plans.md` (new section before "## Logging")
- Modify: `docs/strategy/strategy-gates.md` (new section after the RS gate section)
- Modify: `docs/claude/architecture.md` (the sentence describing the two pipelines)
- Modify: `docs/setup.md` (config table, if it lists scan flags)

- [ ] **Step 1: `docs/commands.md`** — add after the `!performance` row:

```
| `!soak STRATEGY` | v93 trust-rule readout for a strategy's shadow plans: 3 clauses PASS/FAIL, flip advice |
```

- [ ] **Step 2: `docs/strategy/strategy-plans.md`** — insert before `## Logging`:

```markdown
## Strategy-sourced plans (v93)

Until v93 every live plan came from the confluence scan; the eleven per-strategy
entry rules (`entry_filters.entries_for`) were only ever run by the backtest, the
registry badges and `!ticker`. `STRATEGY_ALERTS_MODE` adds a second scan pass that
runs those same functions on the last **completed** daily bar and builds a plan
with the same constructor the backtest's v2 branch uses -- so a live strategy
signal is, by construction, the signal its badge was measured on.

- `off` (default): nothing changes.
- `shadow`: plans are built, badge- and ledger-stamped, stored and walked through
  the lifecycle, but post nothing and open no paper trade. `!soak STRATEGY` reads
  the pre-registered trust rule off them.
- `live`: alerts post and paper trades open. `STRATEGY_ALERTS_LIVE_STRATEGIES`
  names which strategies go live; the rest stay in shadow.

**Ledger.** Each trade is stamped `main` or `weak` at creation and never
re-stamped. Strategy plans carrying a WEAK badge book to `weak`; every other trade,
including confluence plans that borrow a WEAK badge from their primary method,
books to `main`. Every figure the bot showed before v93 is the `main` figure; the
`weak` block is its own line in `!stats`, `!performance`, the dashboard and the
analytics Breakdowns table. The two are never summed.

**Collisions.** One trade per ticker still holds. A strategy plan on a ticker with
an open trade is stored, not opened. Same ticker and direction in one pass: the
strategy plan opens, the confluence plan is stored (higher measured expectancy).
```

- [ ] **Step 3: `docs/strategy/strategy-gates.md`** — after the RS gate section:

```markdown
## Strategy alert soak rule (v93, pre-registered)

A strategy flips from `shadow` to `live` only when all three hold on its shadow
plans (`swingbot/core/edge/strategy_soak.py`):

1. at least 30 closed shadow plans;
2. shadow expectancy at least the badge expectancy minus 0.01R
   (`acceptance.NON_INFERIORITY_R`);
3. median |first live print − recorded close| ≤ 10 % of stop distance.

The flip itself is a config edit to `STRATEGY_ALERTS_LIVE_STRATEGIES`. Written
before any shadow data existed; not to be loosened after looking.
```

- [ ] **Step 4: `docs/claude/architecture.md`** — find the sentence stating the live scan never calls the strategy path (`grep -n -i "never" docs/claude/architecture.md | grep -i strat`) and amend it to: "…the live scan loop calls the strategy path only through the v93 strategy pass (`scanning/strategy_pass.py`), off by default (`STRATEGY_ALERTS_MODE`)."

- [ ] **Step 5: Verify and commit**

Run: `python scripts/dev/testrun.py file tests/test_env_example_sync.py` (docs-only change; guards nothing regressed in config) — green.

```bash
git add docs/commands.md docs/strategy/strategy-plans.md docs/strategy/strategy-gates.md docs/claude/architecture.md docs/setup.md
git commit -m "docs(v93): strategy-sourced plans, ledger split, soak rule, !soak"
```
