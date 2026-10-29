# Risk reporting correctness — collector and API

**Spec:** [Approved risk spec](../specs/2026-10-28-v198-risk-reporting-correctness.md)
**Index:** [Contracts, constraints and task ledger](2026-10-28-v198-risk-reporting-correctness_0-index.md)

Follow the index contracts, sequencing, scope and verification cadence. This part is authored only; the commands below run during separately requested implementation. Preserve current-main v194/v197 fields. No database test precedes `replicate-prod-db`; isolated monkeypatch tests below do not need database access. Read `code-complexity.md`, `architecture.md`, and applicable `no-lookahead`/`edge-module` guidance before changing the collector. These are reporting changes, never execution-policy changes.

# Phase 1 — establish the collector seam

### Task V198-1: Decompose portfolio collection without changing behavior
**Model:** opus — splits a legacy collector currently at complexity 20.

**Files:** Modify `swingbot/core/edge/portfolio_state.py`; create `tests/edge/test_portfolio_state_collection.py`; update `scripts/dev/complexity_baseline.json` only through the shrinking gate. Existing `tests/edge/test_portfolio_state_sectors.py` and `tests/edge/test_edge_heat.py` remain behaviorally unchanged in this task.

**Interfaces:** Preserve `collect_portfolio_state() -> dict`, `_load_sector_map() -> dict` and `_unmapped_count(open_trades, sectors) -> int`. Create private `_cluster_groups(open_trades: list, balance, sectors: dict, dfs: dict) -> list` and `_cluster_state(open_trades: list, balance, sectors: dict) -> list`. V198-2 retains `_cluster_groups` while replacing the failure-default collection wrapper. No availability metadata or nullable values yet.

- [ ] Add these isolated characterization tests before extraction. They pin current behavior, including the incorrect safe defaults that the next task deliberately changes. Add them to the new test file; its existing `tests/edge` directory already belongs to its feature suite.

```python
import pytest

from swingbot.core.edge import portfolio_state as ps


@pytest.fixture
def collected(monkeypatch):
    from swingbot.core.edge import correlation, throttle
    from swingbot.core.marketdata import data, universe
    from swingbot.core.planning import account
    from swingbot.core.tracking.performance import TradeLog

    trades = [{"id": "a", "ticker": "AAA", "risk_pct": 0.4},
              {"id": "b", "ticker": "BBB", "risk_pct": 0.2}]
    monkeypatch.setattr(account, "load_account_config", lambda: {"balance": 1000})
    monkeypatch.setattr(account, "get_balance_history_points", lambda: [])
    monkeypatch.setattr(TradeLog, "get_trades", lambda self, **kw: list(trades))
    monkeypatch.setattr(universe, "sector_map", lambda name: {"AAA": "Tech", "BBB": "Tech"})
    monkeypatch.setattr(data, "get_daily_data", lambda ticker: object())
    monkeypatch.setattr(correlation, "cluster_exposure", lambda *a, **kw: {"cluster": ["AAA", "BBB"]})
    monkeypatch.setattr(throttle, "current_throttle", lambda *a, **kw: (0.75, False))
    monkeypatch.setattr(throttle, "kill_state", lambda: {"on": False, "reason": None})
    return trades


def boom(*args, **kwargs):
    raise OSError("synthetic collection failure")


def test_characterized_success_has_original_fields(collected):
    state = ps.collect_portfolio_state()
    assert set(state) == {"open_heat", "heat_cap", "sector_heat", "unmapped_count",
                          "throttle_mult", "paused", "kill", "growth", "clusters"}
    assert state["open_heat"] == pytest.approx(0.6)
    assert state["sector_heat"] == {"Tech": pytest.approx(0.6)}
    assert state["unmapped_count"] == 0
    assert state["clusters"] == [["AAA", "BBB"]]
    assert state["throttle_mult"] == 0.75
    assert state["paused"] is False
    assert state["growth"] == {}


def test_characterized_failed_trade_read_is_empty(monkeypatch, collected):
    from swingbot.core.tracking.performance import TradeLog
    monkeypatch.setattr(TradeLog, "get_trades", boom)
    state = ps.collect_portfolio_state()
    assert state["open_heat"] == 0.0
    assert state["sector_heat"] == {}
    assert state["clusters"] == []


def test_characterized_failed_controls_use_legacy_defaults(monkeypatch, collected):
    from swingbot.core.edge import throttle
    monkeypatch.setattr(throttle, "current_throttle", boom)
    monkeypatch.setattr(throttle, "kill_state", boom)
    state = ps.collect_portfolio_state()
    assert state["throttle_mult"] == 1.0
    assert state["paused"] is False
    assert state["kill"] == {"on": False, "reason": None}


def test_characterized_cluster_failure_does_not_blank_heat(monkeypatch, collected):
    from swingbot.core.edge import correlation
    monkeypatch.setattr(correlation, "cluster_exposure", boom)
    state = ps.collect_portfolio_state()
    assert state["clusters"] == []
    assert state["open_heat"] == pytest.approx(0.6)
```

- [ ] Run `python scripts/dev/testrun.py file tests/edge/test_portfolio_state_collection.py` before editing production code. Expected: all four characterization tests pass. This is a behavior-preserving refactor, so a deliberately failing behavior assertion would be wrong here.

- [ ] Extract only the existing cluster block into these two helpers, preserving duplicate suppression, sorting, per-ticker failed-fetch skipping and outer exception fallback exactly. Move the correlation and get_daily_data imports into their owning helpers. Replace the collector's final cluster try/except block with the one assignment shown below; retain every preceding statement, including sector warning logs, unchanged.

```python
def _cluster_groups(open_trades: list, balance, sectors: dict, dfs: dict) -> list:
    from swingbot.core.edge import correlation

    clusters = []
    seen = set()
    tickers = sorted({t.get("ticker") for t in open_trades if t.get("ticker")})
    for ticker in tickers:
        result = correlation.cluster_exposure(
            open_trades, ticker, dfs, balance, sectors=sectors)
        cluster = result.get("cluster") or []
        if not cluster:
            continue
        group = frozenset({ticker}) | frozenset(cluster)
        if len(group) < 2 or group in seen:
            continue
        seen.add(group)
        clusters.append(sorted(group))
    return clusters


def _cluster_state(open_trades: list, balance, sectors: dict) -> list:
    from swingbot.core.marketdata.data import get_daily_data

    try:
        tickers = sorted({t.get("ticker") for t in open_trades if t.get("ticker")})
        dfs = {}
        for ticker in tickers:
            try:
                dfs[ticker] = get_daily_data(ticker)
            except Exception:
                continue
        return _cluster_groups(open_trades, balance, sectors, dfs)
    except Exception:
        return []
```

Inside `collect_portfolio_state`, replace the entire last try/except from `clusters: list = []` through its `state["clusters"] = []` fallback, including the surrounding try, with:

```python
    state["clusters"] = _cluster_state(open_trades, balance, sectors)
```

- [ ] Run `python scripts/dev/testrun.py file tests/edge/test_portfolio_state_collection.py` and `python scripts/dev/testrun.py file tests/edge/test_portfolio_state_sectors.py`. Run the account failure characterization alone with `python -m pytest tests/edge/test_edge_heat.py::test_collect_portfolio_state_degrades_on_account_config_failure -v` only after its database prerequisites if applicable. Expected: unchanged assertions pass, including old zero fallback. Run `python scripts/dev/complexity_gate.py --update`, then `python scripts/dev/complexity_gate.py`; confirm collector and each new helper are below 15 and the baseline only shrinks. Do not combine the next task's behavior change into this commit.

- [ ] Fetch/status and inspect recent commits through the controller's repository-safe workflow. Stage only the three owned paths (baseline only if changed), and commit `refactor(risk): isolate portfolio cluster collection`. Record the narrow verification results before continuing.

### Task V198-2: Project collector availability and render it in Discord
**Model:** opus — changes the cross-package portfolio reporting collector after its isolated refactor.

**Files:** Modify `swingbot/core/edge/portfolio_state.py`, `swingbot/commands/growth.py`, `tests/edge/test_portfolio_state_collection.py`, `tests/edge/test_edge_heat.py`, `tests/edge/test_portfolio_state_sectors.py`, `tests/commands/parity_cases/growth.py`; create `tests/commands/test_portfolio_availability.py`.

**Interfaces:** Preserve `collect_portfolio_state() -> dict` and the V198-1 `_cluster_groups` helper. Add `open_trades`, `balance`, six-domain `availability`, and nullable reporting fields exactly as indexed. `portfolio_report(state: dict) -> str` accepts new metadata and legacy known-value fixtures. No execution caller or `heat.open_heat` semantics change. V198-2b consumes the shared snapshot and statuses; this task does not change Flask routes.

- [ ] Revise V198-1 characterizations to assert the approved failure behavior and add these edge cases. Keep the success test's old field assertions, changing only its exact-key assertion to the old keys plus `open_trades`, `balance`, `availability`. Change the fixture's daily-data value from `object()` to a nonempty pandas DataFrame, so cluster coverage can be validated. Replace the failed-trade assertions with unknown heat/sectors/clusters and unavailable positions. Replace failed-control expectations with `throttle_mult is None`, `paused is None`, and `kill["on"] is None`. Cluster calculation failure now expects clusters None and unchanged known heat.

```python
@pytest.mark.parametrize("balance", [0, -1, float("nan"), float("inf"), "bad", None])
def test_invalid_balance_retains_identities_without_heat(monkeypatch, collected, balance):
    from swingbot.core.planning import account
    monkeypatch.setattr(account, "load_account_config", lambda: {"balance": balance})
    state = ps.collect_portfolio_state()
    assert state["open_trades"] == collected
    assert state["availability"]["positions"]["state"] == "ok"
    assert state["open_heat"] is None
    assert state["sector_heat"] is None
    assert state["availability"]["heat"]["reason"] == "invalid_balance"


def test_account_failure_is_not_measured_zero(monkeypatch, collected):
    from swingbot.core.planning import account
    monkeypatch.setattr(account, "load_account_config", boom)
    state = ps.collect_portfolio_state()
    assert state["open_trades"] == collected
    assert state["balance"] is None
    assert state["open_heat"] is None
    assert state["availability"]["heat"]["reason"] == "account_unavailable"


def test_known_empty_is_ok(monkeypatch, collected):
    from swingbot.core.tracking.performance import TradeLog
    monkeypatch.setattr(TradeLog, "get_trades", lambda self, **kw: [])
    state = ps.collect_portfolio_state()
    assert state["open_trades"] == []
    assert state["open_heat"] == 0
    assert state["clusters"] == []
    assert state["availability"]["positions"]["state"] == "ok"
    assert state["availability"]["heat"]["state"] == "ok"


def test_heat_failure_preserves_positions_and_controls(monkeypatch, collected):
    from swingbot.core.edge import heat
    monkeypatch.setattr(heat, "open_heat", boom)
    state = ps.collect_portfolio_state()
    assert state["open_trades"] == collected
    assert state["open_heat"] is None
    assert state["availability"]["heat"]["reason"] == "heat_unavailable"
    assert state["kill"]["on"] is False


def test_partial_sector_map_is_distinct_from_failed_map(monkeypatch, collected):
    from swingbot.core.marketdata import universe
    monkeypatch.setattr(universe, "sector_map", lambda name: {"AAA": "Tech"})
    partial = ps.collect_portfolio_state()
    assert partial["unmapped_count"] == 1
    assert partial["availability"]["sector_heat"]["state"] == "partial"
    monkeypatch.setattr(universe, "sector_map", boom)
    failed = ps.collect_portfolio_state()
    assert failed["sector_heat"] is None
    assert failed["availability"]["sector_heat"]["reason"] == "sector_map_unavailable"


def test_missing_cluster_bars_cannot_claim_no_clusters(monkeypatch, collected):
    from swingbot.core.marketdata import data
    monkeypatch.setattr(data, "get_daily_data", boom)
    state = ps.collect_portfolio_state()
    assert state["clusters"] is None
    assert state["availability"]["clusters"]["state"] == "unavailable"


def test_statuses_have_utc_checks_and_sanitized_reasons(monkeypatch, collected):
    from datetime import datetime
    from swingbot.core.edge import throttle
    monkeypatch.setattr(throttle, "kill_state", boom)
    state = ps.collect_portfolio_state()
    for status in state["availability"].values():
        assert datetime.fromisoformat(status["checked_at"]).utcoffset().total_seconds() == 0
    assert "synthetic collection failure" not in str(state)
```

In the fixture, add `import pandas as pd` and use `lambda ticker: pd.DataFrame({"Close": [1.0, 1.1]})` for daily data. Add this missing-one-ticker coverage test:

```python
def test_partial_cluster_bars_preserve_coverage_warning(monkeypatch, collected):
    import pandas as pd
    from swingbot.core.marketdata import data

    def read(ticker):
        if ticker == "BBB":
            return boom()
        return pd.DataFrame({"Close": [1.0, 1.1]})

    monkeypatch.setattr(data, "get_daily_data", read)
    state = ps.collect_portfolio_state()
    assert state["availability"]["clusters"]["state"] == "partial"
    assert state["availability"]["clusters"]["reason"] == "clusters_incomplete"
    assert state["open_heat"] == pytest.approx(0.6)
```

 In the existing `test_collect_portfolio_state_degrades_on_account_config_failure`, retain dict/growth assertions but replace the old zero/empty assertions with `open_heat is None`, `sector_heat is None`, and heat reason `account_unavailable`; rewrite its obsolete docstring accordingly. In sector tests keep successful and partial-map expectations, but map-read and sector-calculation failure assertions now inspect explicit unavailable state. Preserve the existing warning-log assertion and its logger code.

- [ ] Run `python scripts/dev/testrun.py file tests/edge/test_portfolio_state_collection.py` to observe the new failure assertions failing before implementation.

- [ ] Replace the collector and remove only the obsolete `_cluster_state` wrapper. Keep `_cluster_groups` and `_unmapped_count`. Add imports `math` and `datetime, timezone`. Change `_load_sector_map`'s successful return to `result = universe.sector_map(name)`, validate `isinstance(result, dict)` (raise `ValueError("invalid sector map")` if false), then return result. Change its exception tail from `return {}` to `raise`, retaining its existing warning before raising; this makes the exception observable without changing the universe provider. Add the following helpers and collector. They keep observation, dependencies and calculation separated; each must remain below complexity 15.

```python
def _availability(state: str, checked_at: str, reason=None) -> dict:
    return {"state": state, "checked_at": checked_at, "reason": reason}


def _observed(read, checked_at: str, reason: str) -> tuple:
    try:
        return read(), _availability("ok", checked_at)
    except Exception as exc:
        code = "sector_heat" if reason == "sector_heat_unavailable" else reason
        swallowed(log, "ops.portfolio_state." + code, exc, level=logging.WARNING)
        return None, _availability("unavailable", checked_at, reason)


def _dependent(read, checked_at: str, reason: str, dependencies: list) -> tuple:
    failed = next((s for s in dependencies if s["state"] == "unavailable"), None)
    if failed is not None:
        return None, _availability("unavailable", checked_at, failed["reason"])
    return _observed(read, checked_at, reason)


def _balance(cfg: dict) -> float:
    value = float(cfg.get("balance", cfg.get("base_balance", 0)))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("invalid balance")
    return value


def _valid_trade(row) -> bool:
    return isinstance(row, dict) and isinstance(row.get("ticker"), str) and bool(row["ticker"].strip())


def _trades() -> list:
    rows = TradeLog().get_trades(status="open", limit=None)
    if not isinstance(rows, list) or any(not _valid_trade(t) for t in rows):
        raise ValueError("invalid open-trade response")
    return rows


def _finite_heat(read):
    value = float(read())
    if not math.isfinite(value):
        raise ValueError("nonfinite heat")
    return value


def _sector_values(trades: list, balance: float, sectors: dict) -> dict:
    from swingbot.core.edge import heat
    result = heat.sector_heat(trades, balance, sectors)
    if any(not math.isfinite(float(value)) for value in result.values()):
        raise ValueError("nonfinite sector heat")
    return result


def _sector_state(trades, balance, sectors, checked_at, dependencies) -> tuple:
    values, status = _dependent(
        lambda: _sector_values(trades, balance, sectors),
        checked_at, "sector_heat_unavailable", dependencies)
    if status["state"] == "ok" and _unmapped_count(trades, sectors):
        status = _availability("partial", checked_at, "sector_mapping_incomplete")
    return values, status


def _daily_frames(trades: list) -> tuple[dict, int]:
    from swingbot.core.marketdata.data import get_daily_data
    tickers = sorted({t.get("ticker") for t in trades if t.get("ticker")})
    frames = {}
    for ticker in tickers:
        try:
            frame = get_daily_data(ticker)
            if frame is not None and not frame.empty:
                frames[ticker] = frame
        except Exception as exc:
            swallowed(log, "ops.portfolio_state.cluster_bars", exc, level=logging.DEBUG)
    return frames, len(tickers) - len(frames)


def _clusters_state(trades, balance, sectors, checked_at, dependencies) -> tuple:
    failed = next((s for s in dependencies if s["state"] == "unavailable"), None)
    if failed is not None:
        return None, _availability("unavailable", checked_at, failed["reason"])
    if not trades:
        return [], _availability("ok", checked_at)
    collected, status = _observed(lambda: _daily_frames(trades), checked_at, "clusters_unavailable")
    if collected is None:
        return None, status
    frames, missing = collected
    if not frames:
        return None, _availability("unavailable", checked_at, "clusters_unavailable")
    groups, status = _observed(
        lambda: _cluster_groups(trades, balance, sectors, frames),
        checked_at, "clusters_unavailable")
    if status["state"] == "ok" and missing:
        status = _availability("partial", checked_at, "clusters_incomplete")
    return groups, status


def _throttle_state() -> tuple:
    from swingbot.core.edge import throttle
    points = [bal for _, bal in account_module.get_balance_history_points()]
    mult, paused = throttle.current_throttle(points, was_paused=False)
    if not math.isfinite(float(mult)) or not isinstance(paused, bool):
        raise ValueError("invalid throttle")
    return mult, paused


def _kill_state() -> dict:
    from swingbot.core.edge import throttle
    result = throttle.kill_state()
    if not isinstance(result, dict) or not isinstance(result.get("on"), bool):
        raise ValueError("invalid killswitch")
    return result


def _growth_state(cfg: dict) -> dict:
    try:
        base = cfg.get("base_balance")
        if base:
            return growth_path(account_module.get_balance_history_points(), base,
                               target_multiple=10.0)
    except Exception:
        pass
    return {}


def collect_portfolio_state() -> dict:
    from swingbot.core.edge import heat
    checked = datetime.now(timezone.utc).isoformat()
    cfg, cfg_status = _observed(account_module.load_account_config, checked, "account_unavailable")
    balance, balance_status = _dependent(
        lambda: _balance(cfg), checked, "invalid_balance", [cfg_status])
    trades, positions_status = _observed(_trades, checked, "positions_unavailable")
    dependencies = [positions_status, balance_status]
    open_heat, heat_status = _dependent(
        lambda: _finite_heat(lambda: heat.open_heat(trades, balance)),
        checked, "heat_unavailable", dependencies)
    sectors, map_status = _observed(_load_sector_map, checked, "sector_map_unavailable")
    sector_heat, sector_status = _sector_state(
        trades, balance, sectors, checked, dependencies + [map_status])
    clusters, cluster_status = _clusters_state(
        trades, balance, sectors, checked, dependencies + [map_status])
    control, throttle_status = _observed(_throttle_state, checked, "throttle_unavailable")
    mult, paused = control if control is not None else (None, None)
    kill, kill_status = _observed(_kill_state, checked, "killswitch_unavailable")
    return {
        "open_trades": trades, "balance": balance,
        "open_heat": open_heat, "heat_cap": getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0),
        "sector_heat": sector_heat,
        "unmapped_count": _unmapped_count(trades or [], sectors or {}),
        "clusters": clusters, "throttle_mult": mult, "paused": paused,
        "kill": kill if kill is not None else {"on": None, "reason": None, "at": None},
        "growth": _growth_state(cfg or {}),
        "availability": {"positions": positions_status, "heat": heat_status,
                         "sector_heat": sector_status, "clusters": cluster_status,
                         "throttle": throttle_status, "killswitch": kill_status},
    }
```

- [ ] Add Discord regression tests in `tests/commands/test_portfolio_availability.py`. Reuse existing `portfolio_report` import conventions; the simple dicts never read a store.

```python
from swingbot.commands.growth import portfolio_report


def test_unavailable_controls_do_not_claim_safe_defaults():
    unavailable = {"state": "unavailable", "reason": "source_unavailable", "checked_at": "2026-10-28T00:00:00+00:00"}
    state = {"open_heat": None, "heat_cap": 6.0, "sector_heat": None,
             "clusters": None, "throttle_mult": None, "paused": None,
             "kill": {"on": None}, "growth": {},
             "availability": {key: unavailable for key in
                              ("heat", "sector_heat", "clusters", "throttle", "killswitch")}}
    text = portfolio_report(state)
    assert "heat: unavailable" in text
    assert "killswitch: unavailable" in text
    assert "throttle: unavailable" in text
    assert "sector heat: unavailable" in text
    assert "clusters: unavailable" in text
    assert "x1.00" not in text


def test_partial_sector_coverage_preserves_known_rows():
    state = {"open_heat": 0.6, "heat_cap": 6, "sector_heat": {"Tech": 0.4},
             "clusters": [], "throttle_mult": 0.75, "paused": False,
             "kill": {"on": False}, "unmapped_count": 1,
             "availability": {"sector_heat": {"state": "partial"}}}
    text = portfolio_report(state)
    assert "Tech" in text
    assert "sector heat: partial" in text
    assert "1 unmapped" in text
    assert "x0.75" in text
```

- [ ] Run `python scripts/dev/testrun.py file tests/commands/test_portfolio_availability.py`, observe failure, then replace `portfolio_report` with the following three small render helpers and orchestrator. Successful legacy fixtures remain accepted, but null values never use their old safe defaults.

```python
def _portfolio_controls(state: dict) -> list[str]:
    kill = state.get("kill") or {}
    lines = []
    if kill.get("on") is None:
        lines.append("killswitch: unavailable")
    elif kill["on"]:
        lines.append(f"🔴 KILL SWITCH ON — {kill.get('reason')} — no new entries")
    mult = state.get("throttle_mult")
    if mult is None or state.get("paused") is None:
        lines.append("throttle: unavailable")
    else:
        lines.append(f"throttle: x{mult:.2f}" + (" (PAUSED)" if state["paused"] else ""))
    return lines


def _portfolio_exposure(state: dict) -> list[str]:
    value = state.get("open_heat")
    amount = ui.fmt_pct(value) if value is not None else "unavailable"
    lines = [f"heat: {amount} / {ui.fmt_pct(state.get('heat_cap', 6.0))} cap"]
    for key, label in (("sector_heat", "sector heat"), ("clusters", "clusters")):
        status = state.get("availability", {}).get(key, {}).get("state", "ok")
        if status != "ok":
            lines.append(f"{label}: {status}")
    if state.get("unmapped_count"):
        lines.append(f"sector coverage: {state['unmapped_count']} unmapped")
    for sec, value in sorted((state.get("sector_heat") or {}).items(), key=lambda kv: -kv[1]):
        bar = "█" * int(round(value * 4))
        lines.append(f"  {sec:<24} {ui.fmt_pct(value)} {bar}")
    for cluster in state.get("clusters") or []:
        lines.append(f"  ⚠ correlated cluster: {', '.join(cluster)}")
    return lines


def portfolio_report(state: dict) -> str:
    lines = ["PORTFOLIO SURVIVAL DASHBOARD"]
    controls = _portfolio_controls(state)
    # Keep an engaged/unknown kill observation prominent, ahead of exposure.
    lines.extend(controls[:-1])
    lines.extend(_portfolio_exposure(state))
    lines.extend(controls[-1:])
    growth = state.get("growth") or {}
    if growth:
        lines.append(f"growth path: {growth.get('current_multiple', 1.0):.2f}x — "
                     f"{ui.fmt_pct(growth.get('pct_to_target', 0.0))} of the way to 10x (log scale)")
    lines.append("Projections from backtests/paper — real results will differ.")
    return "\n".join(lines)
```

- [ ] Extend `_stub_portfolio` in `tests/commands/parity_cases/growth.py` immediately after its existing state literal with `state["availability"] = {key: {"state": "ok", "checked_at": "2026-10-28T00:00:00+00:00", "reason": None} for key in ("positions", "heat", "sector_heat", "clusters", "throttle", "killswitch")}`. Preserve its handler and monkeypatch alias. Existing known-state parity output stays the same. Keep existing sector/Discord assertions for populated maps; update only failure semantics and explicitly expected coverage text.

- [ ] Run each affected edge/command test file narrowly with `testrun.py file`, including `tests/edge/test_portfolio_state_sectors.py` and `tests/edge/test_edge_heat.py` (replica prerequisite before any DB-using fixture). Run the existing parity test harness selected for portfolio via `python -m pytest tests/commands -k portfolio -q`; do not run a full suite here. Run `python scripts/dev/complexity_gate.py`; every changed function stays below 15. If its baseline reports an improved/gone entry from replacing a renderer, run the shrinking `--update` and include that baseline change in this commit.

- [ ] Stage the named collector/Discord/test files only and commit `fix(risk): distinguish unavailable portfolio domains`. No API/UI implementation belongs in this commit. Record narrow results; continue to V198-2b.

### Task V198-2b: Expose shared Risk snapshots and fresh killswitch observations
**Model:** sonnet — projects the finalized collector contract through existing Flask endpoints.

**Files:** Modify `swingbot/admin/api_v1/risk.py` and `tests/admin/test_api_v1_risk.py`.

**Interfaces:** Consume V198-2 `collect_portfolio_state` snapshots. Change `_positions(open_trades: list[dict]|None, balance: float|None) -> list[dict]|None` and `_heat_gap_block(open_trades: list[dict]|None) -> dict` to consume that snapshot. Preserve `_risk_metrics_and_correlation`'s current two-result contract here; V198-4 owns its later third availability result. Both killswitch routes return `{killswitch: Killswitch}` with nullable current `on`, nested availability and optional timestamped `last_known`; POST input remains a strict explicit boolean.

- [ ] Add the following API regressions using existing `logged_in` and cache-reset fixtures. Before running this file, complete `replicate-prod-db` and point DATABASE_URL at the shared replica; its existing app fixtures and older tests access Postgres. The synthetic fixture below prevents additional live market/store reads in these regressions.

```python
@pytest.fixture
def projection_state(monkeypatch):
    from swingbot.admin.api_v1 import risk
    from swingbot.core.edge import portfolio_state, throttle
    stamp = "2026-10-28T00:00:00+00:00"
    ok = {"state": "ok", "checked_at": stamp, "reason": None}
    state = {"open_trades": [], "balance": 1000.0, "open_heat": 0.0,
             "heat_cap": 6.0, "sector_heat": {}, "unmapped_count": 0,
             "clusters": [], "throttle_mult": 1.0, "paused": False,
             "kill": {"on": False}, "growth": {},
             "availability": {key: dict(ok) for key in
                              ("positions", "heat", "sector_heat", "clusters", "throttle", "killswitch")}}
    monkeypatch.setattr(portfolio_state, "collect_portfolio_state", lambda: state)
    monkeypatch.setattr(risk, "_risk_metrics_and_correlation", lambda: ({}, {"labels": [], "values": []}))
    monkeypatch.setattr(risk, "_scan_health", lambda: {})
    monkeypatch.setattr(throttle, "kill_state", lambda: {"on": False, "reason": None, "at": None})
    return state


def unavailable_read(*args, **kwargs):
    raise OSError("private diagnostic must not reach JSON")


def test_unknown_book_remains_null_in_api(logged_in, projection_state):
    state = projection_state
    state.update(open_trades=None, open_heat=None, sector_heat=None, clusters=None)
    for key in ("positions", "heat", "sector_heat", "clusters"):
        state["availability"][key].update(state="unavailable", reason="positions_unavailable")
    body = logged_in.get("/api/v1/risk").get_json()
    assert body["positions"] is None
    assert body["heat"]["open_pct"] is None
    assert body["sector_heat"] is None
    assert body["clusters"] is None
    assert body["availability"]["positions"]["state"] == "unavailable"
    assert body["killswitch"]["on"] is False


def test_invalid_balance_keeps_positions_without_percentage(logged_in, projection_state):
    projection_state.update(balance=None, open_heat=None,
                            open_trades=[_open_trade("visible")])
    projection_state["availability"]["heat"].update(state="unavailable", reason="invalid_balance")
    body = logged_in.get("/api/v1/risk").get_json()
    assert body["positions"][0]["trade_id"] == "visible"
    assert body["positions"][0]["risk_pct"] is None
    assert body["heat"]["utilisation_pct"] is None


def test_positions_do_not_read_trade_log_again(logged_in, projection_state, monkeypatch):
    from swingbot.core.tracking.performance import TradeLog
    projection_state["open_trades"] = [_open_trade("snapshot")]
    monkeypatch.setattr(TradeLog, "get_trades", unavailable_read)
    body = logged_in.get("/api/v1/risk").get_json()
    assert body["positions"][0]["trade_id"] == "snapshot"


@pytest.mark.parametrize("path", ["/api/v1/risk", "/api/v1/risk/killswitch"])
def test_fresh_kill_failure_never_reuses_current_state(logged_in, projection_state, monkeypatch, path):
    from swingbot.core.edge import throttle
    first = logged_in.get(path).get_json()["killswitch"]
    monkeypatch.setattr(throttle, "kill_state", unavailable_read)
    body = logged_in.get(path).get_json()
    current = body["killswitch"]
    assert current["on"] is None
    assert current["availability"]["state"] == "unavailable"
    assert current["last_known"]["on"] is False
    assert current["last_known"]["checked_at"] == first["availability"]["checked_at"]
    assert "private diagnostic" not in str(body)
    if path == "/api/v1/risk":
        assert body["availability"]["killswitch"] == current["availability"]
        assert body["availability"]["positions"]["checked_at"] == projection_state["availability"]["positions"]["checked_at"]


def test_unknown_read_allows_explicit_engage_without_implicit_release(logged_in, projection_state, monkeypatch):
    from swingbot.core.edge import throttle
    calls = []
    monkeypatch.setattr(throttle, "kill_state", unavailable_read)
    monkeypatch.setattr(throttle, "set_kill", lambda on, **kw: calls.append(on))
    assert logged_in.get("/api/v1/risk/killswitch").get_json()["killswitch"]["on"] is None
    assert calls == []
    response = logged_in.post("/api/v1/risk/killswitch", json={"on": True})
    assert response.status_code == 200
    assert calls == [True]
    assert response.get_json()["killswitch"]["on"] is None
    assert response.get_json()["killswitch"]["availability"]["state"] == "unavailable"
    assert logged_in.post("/api/v1/risk/killswitch", json={"on": None}).status_code == 400
    assert calls == [True]
```

Add `[]`, `[True]` and `"off"` to the existing rejected-mutation payload parameterization. Keep auth, cache coalescing, unclamped utilization, known-empty and existing explicit on/off roundtrip cases. Update `test_risk_shape` with top-level `availability: dict`, nullable lists `(list, type(None))`, nullable boolean `(bool, type(None))` for paused/on and nested killswitch `availability: dict`. Optional `last_known` is asserted in the explicit stale-state tests, not required in a successful observation. Retain v194 money/gap/sector fields.

- [ ] Run `python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py`; observe contract failures before editing the API.

- [ ] Add `import math` and `from datetime import datetime, timezone`. Replace `_positions` with these helpers. A failed per-row risk calculation preserves identity with null risk; valid null-denominator cases never call the zero-returning heat helper.

```python
def _position_risk(trade: dict, balance: float | None) -> float | None:
    from swingbot.core.edge.heat import trade_risk_pct
    if balance is None:
        return None
    try:
        value = float(trade_risk_pct(trade, balance))
        return round(value, 3) if math.isfinite(value) else None
    except Exception:
        return None


def _positions(open_trades: list[dict] | None, balance: float | None) -> list[dict] | None:
    if open_trades is None:
        return None
    rows = [{"trade_id": t.get("id"), "ticker": t.get("ticker"),
             "strategy": t.get("strategy"), "shares": t.get("shares"),
             "entry": t.get("entry"), "stop_loss": t.get("stop_loss"),
             "risk_pct": _position_risk(t, balance)} for t in open_trades]
    rows.sort(key=lambda row: row["risk_pct"] if row["risk_pct"] is not None else -math.inf,
              reverse=True)
    return rows


def _heat_gap_block(open_trades: list[dict] | None) -> dict:
    if open_trades is None:
        return {"gap_risk_amount": None, "gap_risk_unknown": 0}
    try:
        return _open_short_gap_risk(open_trades)
    except Exception as exc:
        swallowed(log, "ops.risk.heat_gap_block", exc, level=logging.DEBUG)
        return {"gap_risk_amount": None, "gap_risk_unknown": 0}


def _sector_rows(values: dict | None) -> list[dict] | None:
    if values is None:
        return None
    return [{"sector": sector, "heat_pct": pct} for sector, pct in
            sorted(values.items(), key=lambda item: item[1] or 0.0, reverse=True)]
```

- [ ] Replace `_kill_block` and `_fresh_kill` with the following. Add the dedicated observation lock and last-known dictionary near existing cache globals. A lock serializes reads and timestamps; a cached portfolio or a prior success never substitutes for a fresh failed observation. Sanitized JSON reasons are separate from log diagnostics.

```python
_kill_observation_lock = threading.Lock()
_last_known_kill: dict = {}


def _kill_block(state: dict) -> dict:
    on = state.get("on")
    return {"on": on if isinstance(on, bool) else None,
            "reason": state.get("reason"), "at": state.get("at")}


def _kill_status(state: str, checked: str) -> dict:
    return {"state": state, "checked_at": checked,
            "reason": None if state == "ok" else "killswitch_unavailable"}


def _fresh_kill(throttle, state: dict) -> dict:
    # Retain the call signature while deliberately ignoring cached state.
    with _kill_observation_lock:
        checked = datetime.now(timezone.utc).isoformat()
        try:
            observed = _kill_block(throttle.kill_state())
            if observed["on"] is None:
                raise ValueError("invalid killswitch response")
        except Exception as exc:
            swallowed(log, "ops.risk.killswitch_unavailable", exc, level=logging.WARNING)
            block = {"on": None, "reason": None, "at": None,
                     "availability": _kill_status("unavailable", checked)}
            if _last_known_kill:
                block["last_known"] = dict(_last_known_kill)
            return block
        _last_known_kill.clear()
        _last_known_kill.update(observed, checked_at=checked)
        return {**observed, "availability": _kill_status("ok", checked)}


def _invalidate_cache() -> None:
    with _cache_lock:
        _cache.clear()
    with _kill_observation_lock:
        _last_known_kill.clear()
```

- [ ] Update `get_risk` precisely at these seams: remove the dashboard import and its independent account-config try/except; use `balance = state.get("balance")`. Leave cap/utilization calculation and v194 fields otherwise intact. After fetching the two existing metric results, obtain `kill = _fresh_kill(throttle, state)`. Use the following entries in the response mapping, replacing their corresponding existing entries. Do not mutate the cached state/availability dictionaries.

```python
        "availability": {**state.get("availability", {}), "killswitch": kill["availability"]},
        "positions": _positions(state.get("open_trades"), balance),
        "sector_heat": _sector_rows(state.get("sector_heat")),
        "clusters": state.get("clusters"),
        "throttle": {"multiplier": state.get("throttle_mult"), "paused": state.get("paused")},
        "killswitch": kill,
```

In its existing heat mapping, replace only `**_heat_gap_block()` with `**_heat_gap_block(state.get("open_trades"))`. Keep `unmapped_count`, scan health, metrics, correlation, and uncapped utilization intact. Remove the unused `throttle_mult` local.

- [ ] Keep both route decorators and authentication. Replace the GET killswitch return with `return jsonify({"killswitch": _fresh_kill(throttle, {})})`. Replace the POST body after its existing throttle import with this complete validation/action/readback block. The command is explicit even if reading before or after it is unavailable; successful issuance plus failed observation is current unknown, never a claimed release.

```python
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("on"), bool):
        return error("invalid", "Body must contain 'on' as a boolean.", 400)
    reason = str(payload.get("reason") or "admin panel")
    try:
        throttle.set_kill(payload["on"], reason=reason)
    except Exception as exc:
        swallowed(log, "ops.risk.killswitch_write", exc, level=logging.WARNING)
        return error("unavailable", "Could not update the killswitch.", 503)
    # Clear portfolio data without discarding the last confirmed observation.
    with _cache_lock:
        _cache.clear()
    return jsonify({"killswitch": _fresh_kill(throttle, {})})
```

- [ ] Update existing tests that intentionally stub only `{}` or `{"sector_heat": {}, "unmapped_count": 8}`: missing data remains unknown, but `_sector_rows({})` still gives [] and the unmapped count remains unchanged. No backend fallback to invented availability is needed for incomplete test-only snapshots. Existing position tests now receive their account denominator from `account_module.load_account_config` through the collector, so replace any dashboard-only balance monkeypatch with that actual seam. Keep `fresh_risk_cache` calling `_invalidate_cache()` before/after tests so last-known observations cannot leak between them.

- [ ] Run `python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py` after the replica prerequisite, then `python scripts/dev/complexity_gate.py`. Fix a failure narrowly. New/changed functions must remain below 15; if any baseline entry is improved/gone, shrink it with `--update` and stage the resulting baseline update. No full suite, backtest, production change or UI work in this task.

- [ ] Stage only `swingbot/admin/api_v1/risk.py`, `tests/admin/test_api_v1_risk.py` and a genuinely shrinking baseline if produced, inspect status/recent commits through the controller, and commit `fix(risk): expose unknown observations without stale control defaults`. Hand the now-stable API contract to V198-3; final suite/layout/release checks remain V198-6.

