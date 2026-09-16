# v89 Admin UI Integrity and Spacing — Part 2: admin API

> Header, global constraints, parallelisation and the task index live in `2026-09-16-v89-ui-integrity-and-spacing_0-index.md`. Every task here implicitly includes that file's Global Constraints.

# Phase 2 — Backend (worktree)

### Task UA4: One expectancy and win-rate definition on admin surfaces, with N

**Files:**
- Modify: `swingbot/admin/api_v1/dashboard.py` (the `dashboard()` route, ~lines 176–225)
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_performance()`, top-level `win_rate`/`expectancy_r`, ~line 134)
- Test: `tests/admin/test_api_v1_dashboard.py`
- Test: `tests/admin/test_api_v1_analytics.py`

**Interfaces:**
- Consumes: `swingbot.core.analytics.metrics` — `win_rate(closed) -> float | None`, `expectancy_r(closed) -> float | None`, `r_multiples(closed) -> list[float]`, `payoff_ratio_from_rs(rs) -> float | None`.
- Produces (JSON):
  - `GET /api/v1/dashboard` adds `win_rate_n: int` and `expectancy_n: int`. `win_rate`, `expectancy_r` and `payoff_ratio` are now per trade over the `mode`-scoped closed trades.
  - `GET /api/v1/analytics/performance` adds top-level `win_rate_n: int` and `expectancy_n: int`. Top-level `win_rate`/`expectancy_r` are per trade, all-time.
  - `win_rate_n` = the number of `win` + `loss` status trades. `expectancy_n` = `len(r_multiples(closed))`.

- [ ] **Step 1: Write the failing dashboard test**

In `tests/admin/test_api_v1_dashboard.py`, add `"win_rate_n": int,` and `"expectancy_n": int,` to the `DASHBOARD` dict, directly after `"payoff_ratio": NULLABLE_NUMBER,`. Then append:

```python
def test_expectancy_is_per_trade_and_counts_the_scratch(seed, logged_in):
    """v89 spec §3.3. A win (+7/6 R: entry 101, stop 95, exit 108) and a
    scratch closed at entry (0R). The old `stats` figure dropped the scratch
    and read +1.17R; per trade it is +0.58R. On production that difference was
    -0.030R shown against a real -0.142R."""
    from tests.admin.test_api_v1_trades import _trade

    win = _trade("w" * 16, status="win")
    scratch = {**_trade("s" * 16, status="closed"), "exit_price": 101.0, "realized_pnl_amount": 0.0}
    seed(trades=[win, scratch])

    body = logged_in.get("/api/v1/dashboard?mode=all").get_json()

    assert body["expectancy_r"] == pytest.approx((7 / 6 + 0.0) / 2)
    assert body["expectancy_n"] == 2
    # Win rate stays status-based: the scratch is neither a win nor a loss.
    assert body["win_rate"] == 100.0
    assert body["win_rate_n"] == 1
```

- [ ] **Step 2: Write the failing analytics test**

In `tests/admin/test_api_v1_analytics.py`, extend the `assert_shape` dict in `test_performance_top_level_shape` with `"win_rate_n": int, "expectancy_n": int,`. Then append:

```python
def test_overall_and_derived_expectancy_are_the_same_number(seed, logged_in):
    """v89 spec §3.3: same label, same population, same figure. They differed
    on production (-0.030R vs -0.142R) because the top level read the
    leg-expanded, scratch-free `stats` definition."""
    win = _trade("w" * 16, status="win")
    scratch = {**_trade("s" * 16, status="closed"), "exit_price": 101.0, "realized_pnl_amount": 0.0}
    seed(trades=[win, scratch])

    body = logged_in.get("/api/v1/analytics/performance").get_json()

    assert body["expectancy_r"] == pytest.approx(body["derived"]["expectancy_r"])
    assert body["win_rate"] == pytest.approx(body["derived"]["win_rate"])
    assert body["expectancy_n"] == 2
    assert body["win_rate_n"] == 1
```

- [ ] **Step 3: Run both to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py`
Expected: FAIL. There is a `KeyError`/shape failure on `win_rate_n`, and `expectancy_r` reads ≈1.1667.
Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: FAIL, same reasons.

- [ ] **Step 4: Implement in the dashboard route**

In `swingbot/admin/api_v1/dashboard.py`, inside `dashboard()`, directly after `stats.update(tl.get_extended_stats(trades=scoped_raw))` add:

```python
    # v89 spec §3.3: the admin figures are per trade (legs blended) over every
    # closed trade with a computable R, scratches included -- the definition
    # Analytics' Derived block already used. `stats` stays for the keys below
    # that still read it; its leg-expanded, scratch-free expectancy also feeds
    # plan confidence, which is bot behaviour and not changed here.
    from swingbot.core.analytics import metrics as m

    closed_scoped = [t for t in scoped_raw if t.get("status") in ("win", "loss", "closed")]
    scoped_rs = m.r_multiples(closed_scoped)
```

Replace the three lines

```python
        "win_rate": stats.get("win_rate"),
        "expectancy_r": stats.get("expectancy_r"),
        # v85 D9. Beside expectancy deliberately: win rate and payoff ratio
        # decompose it, so the three travel together.
        "payoff_ratio": stats.get("payoff_ratio"),
```

with

```python
        "win_rate": m.win_rate(closed_scoped),
        "win_rate_n": sum(1 for t in closed_scoped if t.get("status") in ("win", "loss")),
        "expectancy_r": m.expectancy_r(closed_scoped),
        "expectancy_n": len(scoped_rs),
        # v85 D9 kept beside expectancy; v89 computes it from the SAME per-trade
        # R list expectancy averages, so the pair still describes one population.
        "payoff_ratio": m.payoff_ratio_from_rs(scoped_rs),
```

- [ ] **Step 5: Implement in the analytics route**

In `swingbot/admin/api_v1/analytics.py`, `analytics_performance()`, replace

```python
        "win_rate": stats.get("win_rate"),
        "expectancy_r": stats.get("expectancy_r"),
```

with

```python
        # v89 spec §3.3: the same per-trade definitions `derived` uses, over
        # all-time closed trades, so Overall and Derived cannot disagree again.
        "win_rate": m.win_rate(closed),
        "win_rate_n": sum(1 for t in closed if t.get("status") in ("win", "loss")),
        "expectancy_r": m.expectancy_r(closed),
        "expectancy_n": len(m.r_multiples(closed)),
```

Also update the route docstring paragraph that begins `**What \`?from=\`/\`?to=\` scopes`: replace "stay all-time, unchanged from before SR54" with "stay all-time (and, since v89, use the same per-trade definitions as `derived`)".

- [ ] **Step 6: Run both to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: PASS.

If `test_win_rate_expectancy_and_payoff_scope_with_mode` or a payoff test now fails, it is asserting the old leg-expanded figure. Recompute the expected value by hand under the per-trade definition, update the assertion, and state the change in the commit body.

- [ ] **Step 7: Commit**

```bash
git add swingbot/admin/api_v1/dashboard.py swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_dashboard.py tests/admin/test_api_v1_analytics.py
git commit -m "fix(v89): admin expectancy and win rate are per trade with scratches, and ship their N"
```

---

### Task UA5: Account-based total, annualised and monthly returns, and Calmar

**Files:**
- Modify: `swingbot/core/analytics/metrics.py` — `total_return_pct`, `annualised_return_pct`, `calmar`, `calendar_returns`; add `balance_at`, `_account_points`; delete `_equity_points`
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_performance()`)
- Test: `tests/analytics/test_metrics_derived.py`
- Test: `tests/admin/test_api_analytics.py`

**Interfaces:**
- Consumes: `metrics.equity_curve(closed, starting_balance) -> {"points": [{date, balance, pnl}], "skipped_n"}`, `metrics.max_drawdown_pct(points)`, `metrics.span_years(closed)`, `swingbot.core.planning.account.load_account_config()["base_balance"]`.
- Produces:
  - `balance_at(closed: list[dict], before: str | None, base_balance: float) -> float`
  - `total_return_pct(closed: list[dict], starting_balance: float) -> float | None`
  - `annualised_return_pct(closed: list[dict], starting_balance: float) -> float | None`
  - `calmar(closed: list[dict], starting_balance: float) -> float | None`
  - `calendar_returns(closed: list[dict], starting_balance: float) -> list[{"month": str, "return_pct": float | None, "pnl": float, "n": int}]`
  - `/analytics/performance` → `calendar[]` rows gain `pnl`.

- [ ] **Step 1: Rewrite the metric tests to the account definition (failing)**

In `tests/analytics/test_metrics_derived.py`:
- Add `balance_at,` to the import list (alphabetical, after `avg_win_pct,`).
- Replace `_year_of_trades` with a version that carries amounts:

```python
BASE = 1000.0


def _year_of_trades():
    """Four trades spanning one calendar year: +10%, -5%, +20%, -10% on price,
    and +100, -50, +200, -100 in realised money on a 1,000 account.

    Account walk: 1000 -> 1100 -> 1050 -> 1250 -> 1150 (+15.0%).
    Compounding the PRICE returns instead would give +12.86% -- the v89 bug,
    which on production read -94.72% for a 0.26% account loss.
    """
    return [
        _t("2024-01-01", "2024-01-11", 100.0, 110.0, strategy="RSI", pnl_amount=100.0),
        _t("2024-04-01", "2024-04-11", 100.0, 95.0, status="loss", strategy="RSI", pnl_amount=-50.0),
        _t("2024-07-01", "2024-07-21", 100.0, 120.0, strategy="MACD", pnl_amount=200.0),
        _t("2024-12-22", "2025-01-01", 100.0, 90.0, status="loss", strategy="MACD", pnl_amount=-100.0),
    ]
```

- Replace the whole `# --- returns / calmar` section (from `def test_total_return_pct_compounds_rather_than_summing` through `def test_calmar_none_when_the_curve_never_drew_down` inclusive) with:

```python
# ------------------------------------------------------- returns / calmar

def test_balance_at_adds_realised_pnl_closed_strictly_before_the_date():
    trades = _year_of_trades()
    assert balance_at(trades, None, BASE) == 1000.0
    assert balance_at(trades, "2024-01-11", BASE) == 1000.0   # closes that day are not before it
    assert balance_at(trades, "2024-07-01", BASE) == 1050.0


def test_total_return_pct_is_account_growth_not_compounded_trade_returns():
    assert total_return_pct(_year_of_trades(), BASE) == pytest.approx(15.0)


def test_annualised_return_is_close_to_total_return_over_about_one_year():
    ann = annualised_return_pct(_year_of_trades(), BASE)
    assert 14.0 < ann < 15.0     # ~366 days, so barely below the raw total


def test_annualised_return_scales_a_short_window_up():
    quick = [_t("2024-01-01", "2024-01-11", 100.0, 110.0, pnl_amount=100.0)]
    assert annualised_return_pct(quick, BASE) > 1000.0


def test_returns_none_on_empty_window():
    assert total_return_pct([], BASE) is None
    assert annualised_return_pct([], BASE) is None
    assert calmar([], BASE) is None


def test_returns_none_when_no_trade_carries_a_realised_amount():
    # An unsized trade has no money to walk; 0.0% would claim a flat account.
    assert total_return_pct([_t("2024-01-01", "2024-01-11", 100.0, 110.0)], BASE) is None


def test_returns_none_without_a_positive_starting_balance():
    assert total_return_pct(_year_of_trades(), 0.0) is None


def test_calmar_is_annualised_return_over_account_max_drawdown():
    trades = _year_of_trades()
    # Peak 1250, then 1150 -> max drawdown 8.0%.
    assert calmar(trades, BASE) == pytest.approx(annualised_return_pct(trades, BASE) / 8.0, rel=1e-3)


def test_calmar_none_when_the_curve_never_drew_down():
    winners = [
        _t("2024-01-01", "2024-01-11", 100.0, 110.0, pnl_amount=100.0),
        _t("2024-02-01", "2024-02-11", 100.0, 110.0, pnl_amount=100.0),
    ]
    assert calmar(winners, BASE) is None
```

- Replace the two calendar tests with:

```python
def test_calendar_returns_are_monthly_pnl_over_the_balance_the_month_opened_with():
    cal = {c["month"]: c for c in calendar_returns(_year_of_trades(), BASE)}
    assert cal["2024-01"]["return_pct"] == pytest.approx(10.0)    # +100 on 1,000
    assert cal["2024-01"]["pnl"] == 100.0
    assert cal["2024-01"]["n"] == 1
    assert cal["2025-01"]["return_pct"] == pytest.approx(-8.0)    # -100 on 1,250
    assert "2024-02" not in cal   # months with no closes are omitted, not zeroed


def test_calendar_returns_empty_on_no_trades():
    assert calendar_returns([], BASE) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_metrics_derived.py`
Expected: FAIL — `ImportError: cannot import name 'balance_at'`.

- [ ] **Step 3: Implement in `metrics.py`**

Add directly above `def total_return_pct`:

```python
def balance_at(closed: list[dict], before: str | None, base_balance: float) -> float:
    """The account balance at the start of day `before` (YYYY-MM-DD): the base
    plus the realised P&L of every trade that closed strictly earlier.

    `before=None` is the base itself. Trades without `realized_pnl_amount`
    contribute nothing, the same rule `equity_curve` walks by.
    """
    base = float(base_balance or 0.0)
    if before is None:
        return base
    return base + sum(
        float(t["realized_pnl_amount"]) for t in closed
        if t.get("realized_pnl_amount") is not None
        and t.get("closed_at") and str(t["closed_at"])[:10] < before
    )


def _account_points(closed: list[dict], starting_balance: float) -> list[dict]:
    """`equity_curve`'s points, or [] when there is nothing honest to walk: no
    trades, no positive starting balance, or no trade with a realised amount
    (a lone baseline point is not a curve)."""
    if not closed or not starting_balance or starting_balance <= 0:
        return []
    points = equity_curve(closed, starting_balance)["points"]
    return points if len(points) >= 2 else []
```

Replace `total_return_pct` with:

```python
def total_return_pct(closed: list[dict], starting_balance: float) -> float | None:
    """Account growth across the window, in %: final balance over the balance
    the window opened with. None on an empty or unsized window.

    v89: this used to compound each trade's PRICE return as if every trade
    were the whole account, which read -94.72% on a book that had lost 0.26%.
    """
    points = _account_points(closed, starting_balance)
    if not points:
        return None
    return round((points[-1]["balance"] / float(starting_balance) - 1.0) * 100.0, 4)
```

Change `annualised_return_pct`'s signature to `(closed: list[dict], starting_balance: float)` and its first line to `total = total_return_pct(closed, starting_balance)`. The rest of the body is unchanged.

Replace `calmar`'s signature and body (keeping its docstring) with:

```python
def calmar(closed: list[dict], starting_balance: float) -> float | None:
    """Annualised return / maximum drawdown, both on the account equity walk.

    None when the curve never drew down: dividing by a zero drawdown is
    undefined, and reporting a huge number for "never lost" would rank a
    two-trade sample above a real track record.
    """
    ann = annualised_return_pct(closed, starting_balance)
    if ann is None:
        return None
    max_dd = max_drawdown_pct(_account_points(closed, starting_balance))
    if not max_dd:          # None (too few points) or 0.0 (no drawdown at all)
        return None
    return round(ann / abs(max_dd), 4)
```

Delete `_equity_points` (its only caller was `calmar`). Confirm first with `git grep -n "_equity_points" -- swingbot tests scripts`, which must show only its definition.

Replace `calendar_returns` with:

```python
def calendar_returns(closed: list[dict], starting_balance: float) -> list[dict]:
    """Account return per calendar month of close, oldest first: that month's
    realised P&L over the balance the month opened with.

    Months with no closes are OMITTED rather than emitted as 0.0 -- a flat
    month and a month you did not trade are different facts. `pnl` ships with
    it so a chart can say what the percentage is a percentage of.

    v89: previously compounded per-trade price returns (the same defect as
    `total_return_pct`), which drew -82% months on a near-flat account.
    """
    by_month: dict[str, list[dict]] = {}
    for t in _closed_in_order(closed):
        if t.get("realized_pnl_amount") is None:
            continue
        by_month.setdefault(t["closed_at"][:7], []).append(t)
    out = []
    for month, ts in sorted(by_month.items()):
        opening = balance_at(closed, f"{month}-01", starting_balance)
        pnl = sum(float(t["realized_pnl_amount"]) for t in ts)
        out.append({
            "month": month,
            "return_pct": round(pnl / opening * 100.0, 4) if opening > 0 else None,
            "pnl": round(pnl, 2),
            "n": len(ts),
        })
    return out
```

- [ ] **Step 4: Run to verify the metric tests pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_metrics_derived.py`
Expected: PASS.

- [ ] **Step 5: Update the admin test fixture and expectations (failing)**

In `tests/admin/test_api_analytics.py`, replace the `seed` fixture with:

```python
@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(trades=()):
        (tmp_path / "plans.json").write_text("[]", encoding="utf-8")
        (tmp_path / "trades.json").write_text(json.dumps(list(trades)), encoding="utf-8")
        # v89: account returns are measured against base_balance. Pinned here
        # so the expectations below do not depend on config.ACCOUNT_BALANCE.
        (tmp_path / "account.json").write_text(json.dumps({
            "base_balance": 1000.0, "balance": 1150.0, "risk_pct": 1.0,
            "max_position_pct": 20.0, "sizing_mode": "risk_pct", "balance_history": [],
        }), encoding="utf-8")
    return _seed
```

Change `assert derived["total_return_pct"] == pytest.approx(12.86, abs=0.01)` to:

```python
    # +100 -50 +200 -100 on base 1,000 (realised = (exit - entry) * 10 shares).
    assert derived["total_return_pct"] == pytest.approx(15.0)
```

In `test_range_actually_narrows_the_figures`, keep `winners_only["total_return_pct"] == pytest.approx(10.0)`. It is still +100 on the 1,000 balance the January window opens with.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_analytics.py`
Expected: FAIL — `TypeError: total_return_pct() missing 1 required positional argument`.

- [ ] **Step 6: Pass the starting balance from the route**

In `swingbot/admin/api_v1/analytics.py`, `analytics_performance()`, directly after `scoped = m.in_date_range(closed, start=start, end=end)` add:

```python
    # v89 spec §3.4: returns are account growth, measured from the balance the
    # selected window opened with -- not per-trade price returns compounded.
    from swingbot.core.planning import account as account_module

    base_balance = float(account_module.load_account_config().get("base_balance") or 0.0)
    window_balance = m.balance_at(closed, start, base_balance)
```

Then change the four call sites:

```python
            "total_return_pct": m.total_return_pct(scoped, window_balance),
            "annualised_return_pct": m.annualised_return_pct(scoped, window_balance),
            "calmar": m.calmar(scoped, window_balance),
```
```python
        "calendar": m.calendar_returns(scoped, window_balance),
```

- [ ] **Step 7: Run to verify both files pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_analytics.py` → PASS.
Run: `python scripts/dev/testrun.py file tests/analytics/test_metrics_derived.py` → PASS.
Run: `git grep -n -e "total_return_pct(" -e "annualised_return_pct(" -e "calmar(" -e "calendar_returns(" -- swingbot scripts tests`. Every non-definition call must pass a starting balance. `swingbot/core/tracking/risk_metrics.py` has its own local `total_return_pct` variable, which is not a call; leave it.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/analytics/metrics.py swingbot/admin/api_v1/analytics.py tests/analytics/test_metrics_derived.py tests/admin/test_api_analytics.py
git commit -m "fix(v89): total, annualised and monthly returns and Calmar measure the account, not compounded trade returns"
```

---

### Task UA6: Report the close-reason strings the exit buckets cannot map

**Files:**
- Modify: `swingbot/core/analytics/metrics.py` (add `unmapped_exit_reasons` after `exit_reason_split`)
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_exit_quality()`)
- Test: `tests/analytics/test_metrics_exit_reasons.py`
- Test: `tests/admin/test_api_v1_analytics.py`

**Interfaces:**
- Consumes: `metrics._exit_reason_bucket(trade) -> str`, `metrics.close_reason_text(trade) -> str`.
- Produces:
  - `unmapped_exit_reasons(closed: list[dict], limit: int = 10) -> list[{"status": str, "text": str, "n": int}]`, sorted by `n` desc, then status, then text.
  - `GET /api/v1/analytics/exit-quality` adds `unmapped_reasons` (that list).

- [ ] **Step 1: Write the failing metric test**

Append to `tests/analytics/test_metrics_exit_reasons.py`:

```python
def test_unmapped_reasons_lists_the_raw_strings_the_buckets_do_not_know():
    """v89 spec §3.5. Production's Exit reason mix was 91% "other"; this is
    what tells us which strings to map, without guessing."""
    trades = [
        _t("tp hit", 1.0, status="win"),
        _t("tp hit", 1.0, status="win"),
        _t("stop", -1.0),                 # exact bucket -> not unmapped
        _t("sl hit", -1.0, status="loss"),
    ]
    assert metrics.unmapped_exit_reasons(trades) == [
        {"status": "win", "text": "tp hit", "n": 2},
        {"status": "loss", "text": "sl hit", "n": 1},
    ]


def test_unmapped_reasons_reports_a_missing_reason_as_an_empty_string():
    assert metrics.unmapped_exit_reasons([_t(None, 1.0, status="win")]) == [
        {"status": "win", "text": "", "n": 1},
    ]


def test_unmapped_reasons_is_capped():
    trades = [_t(f"reason {i}", 0.5, status="win") for i in range(12)]
    assert len(metrics.unmapped_exit_reasons(trades)) == 10
    assert len(metrics.unmapped_exit_reasons(trades, limit=3)) == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/dev/testrun.py file tests/analytics/test_metrics_exit_reasons.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'unmapped_exit_reasons'`.

- [ ] **Step 3: Implement**

Add after `exit_reason_split` in `swingbot/core/analytics/metrics.py`:

```python
def unmapped_exit_reasons(closed: list[dict], limit: int = 10) -> list[dict]:
    """The raw close-reason texts that `_exit_reason_bucket` files under
    "other", with how often each occurs -- most frequent first.

    `exit_reason_split` is right to keep an "other" bucket rather than guess;
    this is the other half of that contract: the strings themselves, so the
    mapping can be extended by exact match from real data (v89 spec §3.5).
    Keyed by status as well, since the same text under "win" and "loss" may
    mean different exits.
    """
    counts: dict[tuple[str, str], int] = {}
    for trade in closed:
        if _exit_reason_bucket(trade) != "other":
            continue
        key = (str(trade.get("status") or ""), close_reason_text(trade))
        counts[key] = counts.get(key, 0) + 1
    rows = [{"status": status, "text": text, "n": n} for (status, text), n in counts.items()]
    rows.sort(key=lambda row: (-row["n"], row["status"], row["text"]))
    return rows[:limit]
```

In `swingbot/admin/api_v1/analytics.py`, `analytics_exit_quality()`, add to the returned dict directly after `"exit_reasons": m.exit_reason_split(closed),`:

```python
                    "unmapped_reasons": m.unmapped_exit_reasons(closed),
```

- [ ] **Step 4: Write the failing API test**

Append to `tests/admin/test_api_v1_analytics.py`:

```python
def test_exit_quality_reports_the_reasons_it_could_not_map(seed, logged_in):
    trade = {**_trade("a" * 16, status="win"), "close_reason": "take profit reached"}
    seed(trades=[trade])
    body = logged_in.get("/api/v1/analytics/exit-quality").get_json()
    assert body["unmapped_reasons"] == [{"status": "win", "text": "take profit reached", "n": 1}]
```

- [ ] **Step 5: Run both files to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_metrics_exit_reasons.py` → PASS.
Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py` → PASS.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/metrics.py swingbot/admin/api_v1/analytics.py tests/analytics/test_metrics_exit_reasons.py tests/admin/test_api_v1_analytics.py
git commit -m "feat(v89): exit-quality reports the close-reason strings its buckets cannot map"
```

---

### Task UA7: `prices_as_of` on the trades list

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py` (`list_trades()`, the final `return`, ~line 878)
- Test: `tests/admin/test_api_v1_trades.py`

**Interfaces:**
- Consumes: `collection(items, total, page, per_page) -> dict`.
- Produces: `GET /api/v1/trades` body gains `prices_as_of: str | None`. It is an ISO-8601 UTC instant (seconds precision) when at least one row on the page carries a `current_price`, else `null`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/admin/test_api_v1_trades.py`:

```python
def test_list_says_when_its_live_prices_were_fetched(seed, logged_in, priced):
    """v89 spec §3.10: Open Positions printed "age unknown" permanently. The
    prices are fetched during this request, so the request time IS their age."""
    from datetime import datetime

    plan, trade = _open_pair()
    seed(plans=[plan], trades=[trade])
    priced(110.0)

    body = logged_in.get("/api/v1/trades?status=open").get_json()

    assert body["prices_as_of"] is not None
    assert datetime.fromisoformat(body["prices_as_of"]).tzinfo is not None


def test_list_has_no_prices_as_of_when_nothing_on_the_page_was_priced(seed, logged_in):
    seed(trades=[_trade("c" * 16, status="win")])
    assert logged_in.get("/api/v1/trades").get_json()["prices_as_of"] is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py`
Expected: FAIL — `KeyError: 'prices_as_of'`.

- [ ] **Step 3: Implement**

In `list_trades()`, replace

```python
    return jsonify(collection(page_rows, total, params.page, params.per_page))
```

with

```python
    body = collection(page_rows, total, params.page, params.per_page)
    # v89: the live prices on this page were fetched during this request, so
    # its time is their age. Null when nothing was priced (closed rows only,
    # or the price fetch failed) -- never a timestamp for prices that are not
    # there.
    body["prices_as_of"] = (
        datetime.now(timezone.utc).isoformat(timespec="seconds")
        if any(row.get("current_price") is not None for row in page_rows)
        else None
    )
    return jsonify(body)
```

(`datetime` and `timezone` are already imported at the top of the module.)

- [ ] **Step 4: Run to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py`
Expected: PASS. If an existing test asserts the exact key set of the list body, add `prices_as_of` to it.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/trades.py tests/admin/test_api_v1_trades.py
git commit -m "feat(v89): trades list reports when its live prices were fetched"
```
