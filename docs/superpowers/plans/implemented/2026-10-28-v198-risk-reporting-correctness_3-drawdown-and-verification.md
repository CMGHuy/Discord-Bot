# Risk reporting correctness — drawdown and final verification

**Spec:** [Approved risk spec](../../specs/implemented/2026-10-28-v198-risk-reporting-correctness.md)
**Index:** [Contracts, constraints and task ledger](2026-10-28-v198-risk-reporting-correctness_0-index.md)

This part follows V198-4b's three-result metric contract and preserves its independent market block. Commands are implementation instructions only. No source change, test, database operation or production work was performed while authoring. The partner approved the written design for planning on 2026-10-28; implementation remains unstarted.

# Phase 3 — chronological drawdown and release verification

### Task V198-5: Count initial losses and select closed records chronologically
**Model:** sonnet — corrects a pure drawdown definition and adds bounded Risk-only record selection.

**Files:** Modify `swingbot/core/analytics/risk_metrics.py`, `tests/analytics/test_risk_metrics.py`, `swingbot/admin/api_v1/risk_read_model.py`, `tests/admin/test_risk_read_model.py`.

**Interfaces:** Preserve `max_drawdown_r(r_multiples: list[float]) -> float|None`. Add `chronological_records(closed: list[dict], *, outcome: Callable[[dict], float|None]|None=None) -> tuple[list[dict], dict[str,int]]` in the Risk read-model. It returns original records in parsed UTC close order with string trade-ID tie-breaks and mutually exclusive date-then-outcome counts. No shared r_multiples reordering, stored record mutation or trading-policy change.

**Shared-caller preflight:** The verified brief identifies Risk R/money metrics, `swingbot/admin/api_v1/analytics.py` breakdown calls and `scripts/reports/short_gap_sizing_impact.py:_side_drawdown`. The breakdown retains its separate population/order contract; only its initial-loss baseline changes. The report consumes money outcomes and also runs research simulation. Do not execute it or any backtest/validation measurement under this plan. If a newly discovered caller would change a backtest consumer's behavior, apply backtest-gate before proceeding with that consumer. The text field in `scripts/backtest/measure_runner_giveback.py` is not a helper call. Recheck the tracked symbol references at implementation time with `git grep -n max_drawdown_r -- swingbot scripts`; do not broaden the change beyond the approved pure baseline.

- [ ] Add these cases to the existing TestMaxDrawdownR class in `tests/analytics/test_risk_metrics.py`. Existing winners/empty/recovery tests remain; use parametrization rather than repeating the implementation.

```python
    @pytest.mark.parametrize("outcomes,expected", [
        ([-100.0], 100.0), ([-100.0, -50.0], 150.0),
        ([1.0, 2.0], 0.0), ([-2.0, 3.0, -1.0], 2.0),
        ([0.0], 0.0), ([], None),
        ([1.0, float("nan")], None), ([float("inf")], None),
        ([float("-inf")], None), ([1e308, 1e308], None),
    ])
    def test_zero_baseline_and_finite_domain(self, outcomes, expected):
        from swingbot.core.analytics.risk_metrics import max_drawdown_r
        assert max_drawdown_r(outcomes) == expected
```

- [ ] Add chronological cases to `tests/admin/test_risk_read_model.py`, reusing its `model` import. The synthetic rows deliberately disagree with opening order and include offset-aware, naive-UTC and tied timestamps. The callback-count assertion proves a date-invalid row never also becomes an invalid outcome.

```python
def closed_row(trade_id, closed_at, value, opened_at="2026-01-01"):
    return {"id": trade_id, "closed_at": closed_at, "value": value,
            "opened_at": opened_at}


def test_close_order_ignores_input_and_opening_order():
    rows = [closed_row("late", "2026-03-03T10:00:00Z", 1, "2026-01-01"),
            closed_row("first", "2026-03-01T11:00:00+01:00", -1, "2026-02-20"),
            closed_row("middle", "2026-03-02T10:00:00", -1, "2026-02-10")]
    ordered, counts = model.chronological_records(rows, outcome=lambda row: row["value"])
    reversed_order, _ = model.chronological_records(list(reversed(rows)), outcome=lambda row: row["value"])
    assert [row["id"] for row in ordered] == ["first", "middle", "late"]
    assert ordered == reversed_order
    assert counts == {"excluded_count": 0, "invalid_date_count": 0, "invalid_outcome_count": 0}
    from swingbot.core.analytics.risk_metrics import max_drawdown_r
    assert max_drawdown_r([row["value"] for row in ordered]) == 2


def test_equal_instants_use_stable_trade_id():
    rows = [closed_row("b", "2026-03-01T11:00:00+01:00", -1),
            closed_row("a", "2026-03-01T10:00:00Z", 1)]
    ordered, _ = model.chronological_records(rows, outcome=lambda row: row["value"])
    assert [row["id"] for row in ordered] == ["a", "b"]


def test_exclusion_reasons_are_nonoverlapping_and_date_first():
    seen = []
    rows = [closed_row("both_bad", "not-a-date", float("nan")),
            closed_row("missing_date", None, 1),
            closed_row("bad_value", "2026-03-01", float("inf")),
            closed_row("missing_value", "2026-03-02", None),
            closed_row("good", "2026-03-03", -1)]
    def outcome(row):
        seen.append(row["id"])
        return row["value"]
    ordered, counts = model.chronological_records(rows, outcome=outcome)
    assert [row["id"] for row in ordered] == ["good"]
    assert counts == {"excluded_count": 4, "invalid_date_count": 2, "invalid_outcome_count": 2}
    assert seen == ["bad_value", "missing_value", "good"]


def test_outcome_exception_is_counted_without_blanking_other_records():
    rows = [closed_row("bad", "2026-03-01", None), closed_row("good", "2026-03-02", 1)]
    ordered, counts = model.chronological_records(rows, outcome=lambda row: 1 / row["value"])
    assert [row["id"] for row in ordered] == ["good"]
    assert counts["invalid_outcome_count"] == 1


def test_money_selection_filters_dates_before_outcome_or_fx_work():
    rows = [closed_row("unknown_amount", "2026-03-01", None), closed_row("bad_date", None, 1)]
    ordered, counts = model.chronological_records(rows)
    assert [row["id"] for row in ordered] == ["unknown_amount"]
    assert counts == {"excluded_count": 1, "invalid_date_count": 1, "invalid_outcome_count": 0}
    assert model.chronological_records([]) == ([], {"excluded_count": 0, "invalid_date_count": 0, "invalid_outcome_count": 0})
```

- [ ] Run `python scripts/dev/testrun.py file tests/analytics/test_risk_metrics.py` and `python scripts/dev/testrun.py file tests/admin/test_risk_read_model.py`; expect the baseline regressions and missing chronological helper to fail before implementation. The latter follows the replica prerequisite if its conftest accesses the database.

- [ ] Replace only max_drawdown_r's body/docstring with the pure finite zero-baseline walk. Existing math import is available. This is unit-agnostic; no account conversion or record selection enters the pure metrics module.

```python
def max_drawdown_r(r_multiples: list[float]) -> float | None:
    """Largest cumulative peak-to-trough loss, including the initial zero."""
    if not r_multiples:
        return None
    cumulative = peak = largest = 0.0
    for raw in r_multiples:
        try:
            value = float(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(value):
            return None
        cumulative += value
        if not math.isfinite(cumulative):
            return None
        peak = max(peak, cumulative)
        largest = max(largest, peak - cumulative)
        if not math.isfinite(largest):
            return None
    return largest
```

- [ ] In risk_read_model.py extend imports to `from datetime import date, datetime, timezone` and `from typing import Callable`. Add these helpers beneath the signed weights/bar-coverage code. The original rows are not mutated; default-UTC parsing is confined to the Risk projection.

```python
def _close_stamp(row) -> datetime | None:
    if not isinstance(row, dict):
        return None
    value = row.get("closed_at")
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def _finite_outcome(outcome: Callable, row: dict) -> float | None:
    try:
        raw = outcome(row)
        if raw is None or isinstance(raw, bool):
            return None
        value = float(raw)
        return value if math.isfinite(value) else None
    except Exception:
        return None


def chronological_records(closed: list[dict], *,
                          outcome: Callable[[dict], float | None] | None = None
                          ) -> tuple[list[dict], dict[str, int]]:
    selected = []
    invalid_date = invalid_outcome = 0
    for row in closed:
        stamp = _close_stamp(row)
        if stamp is None:
            invalid_date += 1
            continue
        if outcome is not None and _finite_outcome(outcome, row) is None:
            invalid_outcome += 1
            continue
        selected.append((stamp, str(row.get("id", "")), row))
    selected.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in selected], {
        "excluded_count": invalid_date + invalid_outcome,
        "invalid_date_count": invalid_date,
        "invalid_outcome_count": invalid_outcome,
    }
```

- [ ] Run those two narrow files again, then `python scripts/dev/complexity_gate.py`. Audit all changed functions and closures below 15. Inspect the shared caller list against the brief; do not alter analytics breakdown population ordering or execute the research report. Stage the four named files and commit `fix(risk): anchor drawdown at zero and select close chronology`. The following task wires coverage into Risk; final verification remains V198-6.

### Task V198-5b: Project reconciled R and money coverage without cross-domain failures
**Model:** sonnet — connects chronological selection to independent Risk read projections.

**Files:** Modify `swingbot/admin/api_v1/risk.py`, `tests/admin/test_api_v1_risk.py`; update `scripts/dev/complexity_baseline.json` only through its shrinking tool when required.

**Interfaces:** Create `_closed_metrics(closed: list|None, checked: str) -> tuple[dict, dict]`, producing trade metric fields and drawdown availability. Preserve `_risk_metrics_and_correlation`'s V198-4b three-result return and `_distribution_metrics` unchanged. Keep `_max_drawdown_amount(closed) -> dict` as a narrow wrapper for direct callers; introduce `_money_metric(closed) -> tuple[dict, str|None]` for API failure status. R Sharpe/drawdown share selected records and all three exclusion counts; money retains its exit-date FX behavior and fx_missing_count, adds invalid_date_count, and never treats missing amount as missing FX.

- [ ] Add these cases to the existing API test file. Tests directly exercise the read projection with deterministic records; API fixtures and older database tests still require replica setup before running the file.

```python
def r_trade(trade_id, stamp, outcome):
    return {"id": trade_id, "ticker": "AAA", "status": "closed", "direction": "bullish",
            "entry": 100.0, "stop_loss": 90.0, "exit_price": 100.0 + outcome * 10,
            "shares": 10, "opened_at": "2026-01-01T00:00:00Z", "closed_at": stamp}


def test_r_walk_uses_close_order_and_reconciled_exclusions(monkeypatch):
    from swingbot.admin.api_v1 import risk
    rows = [r_trade("late", "2026-03-03T10:00:00Z", 1),
            r_trade("first", "2026-03-01T10:00:00Z", -1),
            r_trade("middle", "2026-03-02T10:00:00Z", -1),
            r_trade("both_bad", None, float("nan")),
            r_trade("bad_outcome", "2026-03-04", float("nan")),
            {**r_trade("zero_risk", "2026-03-05", 1), "stop_loss": 100.0}]
    metrics, availability = risk._closed_metrics(rows, "2026-10-28T00:00:00+00:00")
    drawdown = metrics["max_drawdown_r"]
    assert drawdown == {"value": 2.0, "n": 3, "excluded_count": 3,
                        "invalid_date_count": 1, "invalid_outcome_count": 2}
    assert metrics["sharpe_r"]["n"] == 3
    assert metrics["sharpe_r"]["excluded_count"] == 3
    assert availability["drawdown_r"]["state"] == "partial"
    assert json.dumps(metrics, allow_nan=False)


def test_missing_r_fields_are_excluded_not_zero_filled():
    from swingbot.admin.api_v1 import risk
    rows = [{**r_trade("bad", "2026-03-01", 1), "exit_price": None}]
    metrics, availability = risk._closed_metrics(rows, "2026-10-28T00:00:00+00:00")
    assert metrics["max_drawdown_r"]["n"] == 0
    assert metrics["max_drawdown_r"]["invalid_outcome_count"] == 1
    assert metrics["max_drawdown_r"]["value"] is None
    assert availability["drawdown_r"]["state"] == "unavailable"


def test_money_date_exclusions_precede_fx_lookup(eur_account):
    from datetime import date
    from swingbot.admin.api_v1 import risk
    rows = [_settled("bad_date", ticker="NOFX", pnl=-900, closed_at=None),
            _settled("loss", pnl=-100, closed_at="2026-08-04T20:00:00Z")]
    metrics, availability = risk._closed_metrics(rows, "2026-10-28T00:00:00+00:00")
    assert metrics["max_drawdown_amount"] == {
        "value": 50.0, "n": 1, "fx_missing_count": 0, "invalid_date_count": 1}
    assert availability["drawdown_amount"]["state"] == "partial"
    assert eur_account == [("USD", "EUR", date(2026, 8, 4))]


def test_nonfinite_money_blanks_only_money(eur_account):
    from swingbot.admin.api_v1 import risk
    rows = [_settled("nan", pnl=float("nan"), closed_at="2026-08-04T20:00:00Z")]
    metrics, availability = risk._closed_metrics(rows, "2026-10-28T00:00:00+00:00")
    assert metrics["max_drawdown_amount"]["value"] is None
    assert availability["drawdown_amount"]["state"] == "unavailable"
    assert metrics["max_drawdown_r"]["n"] == 1
    assert availability["drawdown_r"]["state"] == "ok"
    assert json.dumps(metrics, allow_nan=False)


def test_empty_closed_book_and_failed_read_are_distinct():
    from swingbot.admin.api_v1 import risk
    empty, empty_status = risk._closed_metrics([], "2026-10-28T00:00:00+00:00")
    failed, failed_status = risk._closed_metrics(None, "2026-10-28T00:00:00+00:00")
    assert empty["max_drawdown_r"]["value"] is None
    assert failed["max_drawdown_r"]["value"] is None
    assert empty_status["drawdown_r"]["state"] == "ok"
    assert failed_status["drawdown_r"]["reason"] == "closed_trades_unavailable"
    assert failed_status["drawdown_amount"]["state"] == "unavailable"


def test_closed_read_failure_does_not_blank_market_metrics(distribution_inputs, monkeypatch):
    from swingbot.core.tracking.performance import TradeLog
    risk, _ = distribution_inputs
    def trades(self, status=None, **kwargs):
        if status == "open":
            return [_open_trade("open")]
        raise OSError("closed ledger unavailable")
    monkeypatch.setattr(TradeLog, "get_trades", trades)
    metrics, _, availability = risk._risk_metrics_and_correlation()
    assert metrics["beta_spy"]["value"] == pytest.approx(1.0)
    assert availability["distribution_metrics"]["state"] == "ok"
    assert availability["drawdown_r"]["state"] == "unavailable"
```

Update existing exact R metric shape expectations to include excluded_count/invalid_date_count/invalid_outcome_count; keep distribution shapes unchanged. Add `invalid_date_count: 0` to existing successful/failing money dictionary assertions. Update `test_pnl_amounts_sorts_by_close_and_skips_unpriced_rows` to expect `[1.0, 3.0]`, excluding its undated 9.0 row; rename its comment to explain date exclusion rather than “sorts last”. Existing FX missing, unsettled close, same-currency and conversion-failure cases retain their monetary values and fx_missing_count assertions.

- [ ] Run `python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py`; expect the new helper/coverage assertions to fail before implementation.

- [ ] Replace `_pnl_amounts` and add `_money_metric` below it. Date selection happens before conversion, so money._day cannot silently assign today to an invalid parent close. The existing money converter continues to handle each exit-date/realized-leg rate; do not change money.py, fx.py or stored amounts. Read-model math uses only converted finite values.

```python
def _pnl_amounts(closed: list) -> list[float]:
    from .risk_read_model import chronological_records
    ordered, _ = chronological_records(closed)
    amounts = []
    for row in ordered:
        raw = row.get("realized_pnl_amount")
        if raw is None:
            continue
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("nonfinite realized amount")
        amounts.append(value)
    return amounts


def _money_metric(closed: list) -> tuple[dict, str | None]:
    from swingbot.core.analytics import risk_metrics as rm
    from . import money
    from .risk_read_model import chronological_records
    ordered, counts = chronological_records(closed)
    metric = {"value": None, "n": 0, "fx_missing_count": 0,
              "invalid_date_count": counts["invalid_date_count"]}
    try:
        converted = money.to_account_currency(ordered)
        metric["fx_missing_count"] = money.missing_count(converted)
        amounts = _pnl_amounts(converted)
        value = rm.max_drawdown_r(amounts)
        if amounts and value is None:
            raise ValueError("nonfinite cumulative amount")
        metric.update(value=None if value is None else round(value, 2), n=len(amounts))
    except Exception as exc:
        swallowed(log, "ops.risk.max_drawdown_amount", exc, level=logging.DEBUG)
        return metric, "money_conversion_unavailable"
    return metric, None


def _max_drawdown_amount(closed: list) -> dict:
    return _money_metric(closed)[0]
```

- [ ] Add the independent closed-history and population helpers. Missing fields, zero initial risk, malformed legs and nonfinite R values are counted by chronological_records' per-row outcome guard, not globally dropped. The pure R computation remains the existing trade_metrics.r_multiple. Outcome callbacks are deterministic; the second pass over selected records obtains the values in close order without changing the general r_multiples helper.

```python
def _closed_history() -> list | None:
    from swingbot.core.tracking.performance import TradeLog
    try:
        rows = TradeLog().get_trades(status=None, limit=None, ledger="main")
        if not isinstance(rows, list):
            raise ValueError("invalid closed-history response")
        return [row for row in rows if not isinstance(row, dict)
                or row.get("status") in ("win", "loss", "closed")]
    except Exception as exc:
        swallowed(log, "ops.risk.closed_trades_unavailable", exc, level=logging.WARNING)
        return None


def _population_status(checked: str, count: int, total: int, excluded: int, reason: str) -> dict:
    state = "ok"
    if total and count == 0:
        state = "unavailable"
    elif excluded:
        state = "partial"
    return {"state": state, "checked_at": checked, "reason": None if state == "ok" else reason}


def _finite_metric(value) -> float | None:
    return float(value) if value is not None and math.isfinite(value) else None


def _r_metrics(closed: list, checked: str) -> tuple[dict, dict]:
    from swingbot.core.analytics import metrics as trade_metrics
    from swingbot.core.analytics import risk_metrics as rm
    from .risk_read_model import chronological_records
    ordered, counts = chronological_records(closed, outcome=trade_metrics.r_multiple)
    values = [float(trade_metrics.r_multiple(row)) for row in ordered]
    drawdown = rm.max_drawdown_r(values)
    status = _population_status(checked, len(values), len(closed), counts["excluded_count"],
                                "invalid_closed_records")
    if values and drawdown is None:
        status = {"state": "unavailable", "checked_at": checked, "reason": "invalid_closed_records"}
    return {
        "sharpe_r": {**_metric(_finite_metric(rm.sharpe_of(values)), len(values)), **counts},
        "max_drawdown_r": {**_metric(drawdown, len(values)), **counts},
    }, {"drawdown_r": status}


def _closed_metrics(closed: list | None, checked: str) -> tuple[dict, dict]:
    if closed is None:
        counts = {"excluded_count": 0, "invalid_date_count": 0, "invalid_outcome_count": 0}
        unavailable = {"state": "unavailable", "checked_at": checked, "reason": "closed_trades_unavailable"}
        return {
            "sharpe_r": {**_metric(None, 0), **counts},
            "max_drawdown_r": {**_metric(None, 0), **counts},
            "max_drawdown_amount": {"value": None, "n": 0, "fx_missing_count": 0, "invalid_date_count": 0},
        }, {"drawdown_r": dict(unavailable), "drawdown_amount": dict(unavailable)}
    metrics, availability = _r_metrics(closed, checked)
    money, failure = _money_metric(closed)
    reason = "missing_fx" if money["fx_missing_count"] else "incomplete_money_outcomes"
    if money["invalid_date_count"]:
        reason = "invalid_closed_records"
    money_status = _population_status(checked, money["n"], len(closed), len(closed) - money["n"], reason)
    if failure:
        money_status = {"state": "unavailable", "checked_at": checked, "reason": failure}
    return {**metrics, "max_drawdown_amount": money}, {**availability, "drawdown_amount": money_status}
```

- [ ] Replace `_risk_metrics_and_correlation` with this short orchestration over independently guarded sources. This removes its earlier broad malformed-R exception fallback and duplicates of the result dictionary; it preserves V198-4b's tested market helper verbatim. The API's three-result cache unpack and metadata merge remain unchanged.

```python
def _risk_metrics_and_correlation() -> tuple[dict, dict, dict]:
    from swingbot.core.tracking.performance import TradeLog
    try:
        open_trades = TradeLog().get_trades(status="open", limit=None)
    except Exception:
        open_trades = None
    checked = datetime.now(timezone.utc).isoformat()
    benchmark = getattr(config, "MARKET_REGIME_TICKER", "SPY") or "SPY"
    closed_metrics, closed_availability = _closed_metrics(_closed_history(), checked)
    market_metrics, correlation, market_availability = _distribution_metrics(open_trades, benchmark, checked)
    return {**market_metrics, **closed_metrics, "benchmark_symbol": benchmark}, correlation, {
        **market_availability, **closed_availability,
    }
```

Update V198-4b's `test_failed_market_data_preserves_trade_derived_metrics` monkeypatch from `_max_drawdown_amount` to `_money_metric`, returning `({"value": 0, "n": 1, "fx_missing_count": 0, "invalid_date_count": 0}, None)`. Keep the earlier fixture's three-result metrics stub. Update the old malformed-closed-record test to expect valid records retained plus exclusions, instead of blanking both R metrics because one record is malformed. A record with an invalid date is date-excluded before its malformed outcome is inspected.

- [ ] Run the affected API test file narrowly, then `python scripts/dev/complexity_gate.py`. Apply a shrinking baseline update only when the gate requests it. Verify money conversion failure preserves valid R and market metrics; failed closed reads preserve market metrics; no NaN JSON, no invalid-row zero fills, and each exclusion total reconciles. Stage named files plus a required shrinking baseline and commit `fix(risk): expose chronological drawdown coverage`. No full suite in this task; proceed to the one final verification task.

### Task V198-6: Verify complete reporting behavior and close out once
**Model:** sonnet — coordinates the sole final full verification and established release ritual.

**Files:** Record actual verification evidence in `docs/superpowers/plans/2026-10-28-v198-risk-reporting-correctness_0-index.md`. Fix observed defects only in the owning task's listed source/test files. At close-out update `VERSION.json` and then `swingbot/admin/version_history.json` in separate release/history commits; move this plan's index, three parts and approved spec to their corresponding `implemented/` directories. No new runtime interface or redundant test harness is introduced by this verification task.

**Interfaces:** All prior tasks are committed and tested narrowly. The final API preserves independent collector, market, R, money and fresh-killswitch domains. The following matrix identifies the concrete existing assertions to inspect before the final run; test fixtures are synthetic, never reported as live-book performance.

| Requirement | Existing/new regression evidence |
|---|---|
| Legacy refactor unchanged before behavior work | V198-1 characterization and separate commit |
| Failed reads versus successful empty book | test_portfolio_state_collection, API unknown-book/known-empty cases |
| Invalid balance and heat failure preserve identities | Collector invalid-balance parameterization and API position projection tests |
| Mapping/cluster partial coverage | Sector-map failure/partial cases and partial-cluster-frame case |
| Fresh killswitch unknown after cached success | Both parameterized API GET paths, shell HTTP failure test, store stale observation test |
| No implicit release; explicit unknown actions remain usable | Boolean POST rejection cases, unknown-read command case, both workspace action-target tests |
| Signed common-currency gross exposure | Read-model direction/hedge/FX cases, API beta/offset/correlation cases |
| Complete coverage and independent market failure | Missing-bar/FX cases and valid closed metrics surviving market failure |
| Initial loss and finite domain | Pure zero-baseline/overflow/nonfinite cases |
| Close chronology and exclusion reconciliation | UTC ties, shuffled opening/closing order, date-first callback count, R zero-risk/missing-outcome cases |
| Money FX and invalid-date integrity | Existing v194 per-exit conversion, missing-FX, unsettled/same-currency tests plus date-before-FX and nonfinite-money cases |
| Responsive/accessibility/empty-state truth | Risk component lg/sm/xs cases, existing exact hints/drawers, explicit status text and final layout audit |

- [ ] Reconcile completed deliverables and commit history with the active ledger; do not treat checked boxes or stale handoff text as implementation evidence. Fetch/status through the controller, inspect `git log --oneline -5`, and preserve other sessions' changes. Check that v194 is merged, that v197's fields remain intact, and that any subsequently merged v195 layout was adapted rather than duplicated. Inspect the final branch diff for changes outside approved reporting scope; no scan gates, sizing, stops, fills, account ledger writes, registry or validation budget changes are permitted.

- [ ] Before any database-backed verification, apply `replicate-prod-db` exactly as required by repository policy: use the shared swing-db replica and its DATABASE_URL, never a per-task container. Use the configured `test-runner` agent for the one full backend run: `python scripts/dev/testrun.py full`. Require the actual final exit status and verdict, with 0 failed and 0 xfailed; a truncated log or changed test count is not a passing result. Do not launch a second full suite after a local fix or clean merge. A failure is repaired and rerun narrowly with its file or single-test command; use `testrun.py changed` only when the fix touches other areas. Record what failed, what changed and the narrow confirmation.

- [ ] Run the one full frontend suite from frontend: `npm test`. Require the actual successful exit status and zero failing tests. If a failure occurs, fix the owning task and rerun only its affected spec with the affected spec command, for example `npm test -- --include src/app/workspaces/risk/risk.spec.ts` for Risk workspace failures. This is the final full frontend verification, not permission to repeat full suites during cleanup.

- [ ] Bring up the existing local application using the repository's supported local startup workflow at `http://localhost:1234`, with the authorized local ADMIN_USERNAME/ADMIN_PASSWORD loaded only inside the browser/local-app script. Never print credentials, use admin/admin as local login defaults, or make a production change. Run the mandatory command from the repository root: `node frontend/scripts/layout-audit.mjs --base http://localhost:1234`. It must exit 0 before merge. Inspect phone, tablet and desktop layouts for known-empty, unavailable, partial and stale Risk states, explicit action controls, status announcements, 44px touch controls and v194 exact-value hints. A covered/off-screen hint is fixed, never allow-listed. Do not fabricate audit coverage for an unavailable fixture scenario; add the scenario to the existing relevant component test and check its rendered layout through the established local browser workflow.

- [ ] Apply `panel` for the approved spec's quant-engineer seat against the completed v198 branch diff, one reviewer at a time. Scope the review to the preserved execution boundary, missing/partial data, shared-cache status timestamps, FX valuation date and gross denominator, direction, drawdown chronology, exclusion reconciliation, and market/trade failure isolation. Resolve every BLOCKING finding with the owning narrow tests before close-out; ADVISORY findings remain recorded with their disposition. Do not run a backtest or a research report to validate a reporting correction.

- [ ] Record real commands, exit statuses, full-suite verdicts, layout audit outcome and panel disposition in the index Handoff. Identify synthetic fixture provenance. Until those runs actually happen, keep the authoring-only evidence and “implementation unstarted” text; never replace it with a predicted PASS. The verification task owns no source behavior beyond fixing an observed defect, so it requires no new illustrative implementation code or duplicated unit tests.

- [ ] Once every required check is green, apply `close-out` and the applicable `worktree-lifecycle` instructions. Resolve both patch bumps from the then-current VERSION.json: UI patch covers API/read-model/page behavior; bot patch covers Discord reporting. Update the corresponding ui_updated/bot_updated UTC timestamps using `YYYY-MM-DD HH-MM-SS`. Commit the release changes with their actual resolved version numbers and concrete summary; never use a predicted number from an old document.

- [ ] Only after release commits exist, run `python scripts/dev/build_version_matrix.py` and commit the generated `swingbot/admin/version_history.json` separately with the same resolved release summaries. Run the required narrow post-bump regression: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`. This is a specific release-history check, not a second full verification. Fix a missing history entry or working-tree placeholder before continuing.

- [ ] Move the approved v198 spec and all four v198 plan files into their respective implemented/ folders in the closing commit, preserving relative links as necessary. Merge using the repository's worktree/concurrency rules only after inspecting current worktrees and recent commits. No full suite follows a clean merge; conflicts require the appropriate focused verification of resolved files. Clean up only the implementation worktree created for this plan, using its supported lifecycle tool. Never delete another session's worktree, a backup branch or stable rollback reference. No production deployment is part of this plan.

- [ ] Finish with the required numbered file summary and actual verification evidence, distinguish source changes from authoring-only work, and report any unresolved limitation explicitly. The plan is complete only after the delivered implementation, required checks, review, releases, history and document lifecycle are all satisfied.

