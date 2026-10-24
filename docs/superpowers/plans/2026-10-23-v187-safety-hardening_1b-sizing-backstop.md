# v187 — Safety hardening, part 1 (continued): the sizing backstop (V187-6..V187-7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read this file whole**: `grep -n "^### Task V187-7:" -A 260 docs/superpowers/plans/2026-10-23-v187-safety-hardening_1b-sizing-backstop.md`.

**Bump:** bot patch
**Edge:** none (integrity)
**Spec:** [2026-10-23-v187-safety-hardening-design.md](../specs/2026-10-23-v187-safety-hardening-design.md) — § D2 "Backstop", "Numerics", "The 2% cap also binds in account_pct mode", § Testing (D2, Numerics, D2 additions)
**Index:** [2026-10-23-v187-safety-hardening_0-index.md](2026-10-23-v187-safety-hardening_0-index.md) — Goal, Global Constraints, Spec clarifications 1–7, Contracts and the task ledger. This file continues part 1 ([`_1-admin-gate-and-account-limits.md`](2026-10-23-v187-safety-hardening_1-admin-gate-and-account-limits.md), V187-1..V187-5), split off only for the 1500-line cap.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot`, `$WT` = `$R/.claude/worktrees/2026-10-23-v187-safety-hardening` (created in V187-1). Paths below are relative to `$WT`; git via `git -C "$WT"`; tests via `(cd "$WT" && python scripts/dev/testrun.py file <test>)`. Run `/replicate-prod-db` before the first run if part 1 has not already (the sizing callers' tests touch the store).

## Parallelisation

V187-6 runs after V187-4 (same file `swingbot/core/planning/account.py`); V187-7 runs after V187-6 (same function `compute_position_size`). Either may run beside V187-2 or any part-2 task except V187-13 (index § Parallelisation), at most two implementers at once.

**Existing sizing tests (must pass unchanged in both tasks).** `tests/edge/test_edge_sizing.py`, `tests/planning/test_opex_stop_size.py`, `tests/planning/test_stop_scope.py`, `tests/scanning/test_embeds_badges.py`, `tests/scanning/test_outlook_run.py`, `tests/scanning/test_transition_embeds.py`, `tests/scanning/test_feed_close_routes.py`, `tests/commands/test_plans_board.py`, `tests/admin/test_admin_freshness.py`, `tests/admin/test_dashboard_builders.py` (every test file that calls `compute_position_size` or asserts a sized `shares`, `git grep` 2026-10-23). A red one means behaviour changed: fix the code, never the test.

### Task V187-6: Sizing backstop: finite guards, risk clamp, helpers out of compute_position_size

**Model:** opus — money-path refactor of a complexity-18 function that must stay bit-identical for every in-range config while adding refusals and a clamp; numerics and logging rules from three panel findings.

**Files:**
- Modify: `swingbot/core/planning/account.py` (`compute_position_size` l.405-~545 after V187-3/4 shifts; new helpers directly above it)
- Modify: `swingbot/core/scanning/analyze.py` (the `compute_position_size(...)` call, l.254-255)
- Create: `tests/planning/test_sizing_backstop.py`

**Interfaces:**
- Consumes: `math`, `RISK_CEILING_PCT` (imported in V187-3) and `log` (created in V187-4) in `swingbot/core/planning/account.py`.
- Produces: `compute_position_size(entry, stop_loss, account_cfg=None, *, strategy_stats=None, ticker_atr_pct=None, open_positions=0, ticker: str | None = None) -> dict | None` (result shape unchanged); `_edge_risk_pct(mode: str, risk_pct: float, strategy_stats, ticker_atr_pct, open_positions) -> tuple[float, str]`; `_sizing_inputs_finite(balance: float, entry: float, stop_loss: float, ticker: str | None) -> bool`; `_usable_risk_pct(stored: float, effective: float, ticker: str | None) -> float | None`; `_apply_size_caps(raw_shares: float, position_value: float, entry: float, stop_distance: float, balance: float, max_position_pct: float, max_value_abs: float, max_risk_abs: float) -> tuple[float, bool]`. V187-7 inserts its ceiling and settle steps between `_apply_size_caps` and the result.

**Ledger deviation (flagged to the controller).** `_apply_size_caps` takes `position_value` as its second argument, which the ledger signature omits. In `account_pct` mode today's first cap compares `position_value = balance × position_pct / 100` with the cap, not `raw_shares × entry`; the two can differ by one ulp, and when `position_pct == max_position_pct` that would flip `capped` to `True`. Passing the value keeps every output bit-identical. Only `compute_position_size` calls the helper, so no other task is affected.

**Why (spec D2 "Backstop", "Numerics"; index clarifications 2, 3).** The validator (V187-3) never saw a hand-edited or legacy row. The backstop, in order:
1. `balance <= 0 or entry <= 0` → `None` (today's guard, kept first so a `None` stop on a zero balance still returns `None` as today).
2. `balance`, `entry`, `stop_loss` or the stop distance not finite → `None` + warning (`nan <= 0` is false, so NaN passed every guard before).
3. Only in `risk_pct` mode (after the edge chain has normalised kelly / vol_target / min_of_all to it): the **stored** `risk_pct` non-finite or `<= 0` → `None` + warning; the **effective** value (after edge chain and OPEX) non-finite → `None` + warning, `<= 0` → `None` silently (a deliberate throttle), `> RISK_CEILING_PCT` → clamped to the ceiling + warning. The returned `risk_pct` is the clamped value, which `analyze.py` already shows in the alert. `account_pct` never reads `risk_pct`, so a bad stored value there changes nothing.
4. A non-finite final share count → `None` + warning.
Every warning goes to `log` with the prefix `sizing:` and names `ticker=` (or `ticker=?`) and the offending value, every time (no rate limit: a stream of unsized alerts must not read as a quiet day). `analyze.py` passes `ticker=ticker`, the local the decision context already resolved from the item (`plan.ticker` on a v2 plan; the local also covers a legacy plan without the attribute, so the sizing block cannot die on an `AttributeError`); every other caller is unchanged. The complexity of `compute_position_size` drops from 18 to about 10.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/planning/test_sizing_backstop.py`:

```python
"""v187 D2: compute_position_size refuses non-finite inputs and invalid stored
risk, clamps risk above the hard cap, and says so in the log."""
import logging
from types import SimpleNamespace

import pytest

from swingbot.core.edge.sizing import RISK_CEILING_PCT
from swingbot.core.planning import account as acct

NAN, INF = float("nan"), float("inf")
CFG = {"balance": 10_000.0, "risk_pct": 1.0, "position_pct": 20.0, "max_position_pct": 100.0,
       "max_position_value_absolute": 0.0, "max_risk_amount_absolute": 0.0, "sizing_mode": "risk_pct"}


@pytest.fixture(autouse=True)
def no_opex(monkeypatch):
    monkeypatch.setattr(acct.opex, "size_mult", lambda *a, **k: 1.0)


def _warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.name == acct.log.name and r.levelno == logging.WARNING]


def _size(caplog, entry=100.0, stop=98.0, ticker="AAPL", **cfg):
    with caplog.at_level(logging.WARNING, logger=acct.log.name):
        return acct.compute_position_size(entry, stop, {**CFG, **cfg}, ticker=ticker)


def test_legacy_ten_percent_is_sized_at_the_hard_cap_and_warns(caplog):
    out = _size(caplog, risk_pct=10.0)
    assert (out["shares"], out["risk_amount"], out["risk_pct"]) == (100.0, 200.0, RISK_CEILING_PCT)
    [msg] = _warnings(caplog)
    assert msg.startswith("sizing:") and "ticker=AAPL" in msg and "10.0" in msg


@pytest.mark.parametrize("stored", [-1.0, 0.0, NAN, INF, -INF])
def test_invalid_stored_risk_refuses_sizing_and_warns(caplog, stored):
    assert _size(caplog, risk_pct=stored) is None
    [msg] = _warnings(caplog)
    assert "ticker=AAPL" in msg and repr(stored) in msg


@pytest.mark.parametrize("field,value", [("balance", NAN), ("balance", INF), ("entry", NAN),
                                         ("entry", INF), ("stop", NAN), ("stop", -INF)])
def test_non_finite_inputs_refuse_sizing_and_warn(caplog, field, value):
    kwargs = {"entry": 100.0, "stop": 98.0}
    cfg = {}
    if field == "balance":
        cfg["balance"] = value
    else:
        kwargs[field] = value
    assert _size(caplog, **kwargs, **cfg) is None
    [msg] = _warnings(caplog)
    assert msg.startswith("sizing:") and "ticker=AAPL" in msg


def test_exactly_at_the_cap_is_unchanged_and_silent(caplog):
    out = _size(caplog, risk_pct=RISK_CEILING_PCT)
    assert (out["shares"], out["capped"], out["risk_pct"]) == (100.0, False, RISK_CEILING_PCT)
    assert _warnings(caplog) == []


def test_in_range_risk_is_unchanged_and_silent(caplog):
    out = _size(caplog)
    assert (out["shares"], out["risk_amount"], out["position_value"], out["capped"]) == (50.0, 100.0, 5000.0, False)
    assert _warnings(caplog) == []


def test_account_pct_ignores_a_bad_stored_risk(caplog):
    out = _size(caplog, sizing_mode="account_pct", risk_pct=NAN, stop=95.0)
    assert out["mode"] == "account_pct" and out["shares"] == 20.0
    assert _warnings(caplog) == []


def test_edge_mode_without_estimates_is_clamped_too(caplog):
    out = _size(caplog, sizing_mode="kelly", risk_pct=10.0)
    assert out["risk_pct"] == RISK_CEILING_PCT and out["shares"] == 100.0
    assert len(_warnings(caplog)) == 1


def test_a_deliberate_zero_after_the_multiplier_refuses_silently(caplog, monkeypatch):
    monkeypatch.setattr(acct.opex, "size_mult", lambda *a, **k: 0.0)
    assert _size(caplog) is None
    assert _warnings(caplog) == []


def test_missing_ticker_is_named_as_a_question_mark(caplog):
    _size(caplog, ticker=None, risk_pct=10.0)
    assert "ticker=?" in _warnings(caplog)[0]


def test_ticker_is_optional_for_every_existing_caller():
    assert acct.compute_position_size(100.0, 98.0, dict(CFG))["shares"] == 50.0


# ── helpers ─────────────────────────────────────────────────────────────

def test_edge_risk_pct_passes_plain_modes_through():
    assert acct._edge_risk_pct("risk_pct", 1.0, None, None, 0) == (1.0, "risk_pct")
    assert acct._edge_risk_pct("account_pct", 1.0, None, None, 0) == (1.0, "account_pct")
    assert acct._edge_risk_pct("min_of_all", 1.0, None, None, 0) == (1.0, "risk_pct")


@pytest.mark.parametrize("stored,effective,expected", [
    (1.0, 1.0, 1.0), (1.0, 0.75, 0.75), (10.0, 10.0, RISK_CEILING_PCT), (1.0, 0.0, None),
    (-1.0, -1.0, None), (NAN, NAN, None), (1.0, NAN, None),
])
def test_usable_risk_pct(stored, effective, expected):
    assert acct._usable_risk_pct(stored, effective, "T") == expected


def test_apply_size_caps_matches_the_three_existing_caps():
    # 50 shares x 100 = 5000; 10% cap = 1000 -> 10 shares; abs 800 -> 8; abs risk 10 / 2 -> 5
    assert acct._apply_size_caps(50.0, 5000.0, 100.0, 2.0, 10_000.0, 100.0, 0.0, 0.0) == (50.0, False)
    assert acct._apply_size_caps(50.0, 5000.0, 100.0, 2.0, 10_000.0, 10.0, 0.0, 0.0) == (10.0, True)
    assert acct._apply_size_caps(50.0, 5000.0, 100.0, 2.0, 10_000.0, 100.0, 800.0, 0.0) == (8.0, True)
    assert acct._apply_size_caps(50.0, 5000.0, 100.0, 2.0, 10_000.0, 100.0, 0.0, 10.0) == (5.0, True)


def test_analyze_passes_the_ticker(monkeypatch):
    from swingbot.core.scanning import analyze

    seen = {}

    def spy(entry, stop_loss, account_cfg=None, **kw):
        seen.update(kw)
        return None

    monkeypatch.setattr(analyze, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(analyze.account_module, "compute_position_size", spy)
    monkeypatch.setattr(analyze.trade_log, "get_trades", lambda **k: [])
    monkeypatch.setattr(analyze.corr_mod, "cluster_exposure", lambda *a, **k: {"cluster": []})
    plan = SimpleNamespace(ticker="AAPL", trigger_price=100.0, entry_price=100.0, stop_loss=98.0,
                           tp1=104.0, strategy="X", quality_breakdown=[], quality_score=0,
                           badge=None, badge_stats=None)
    item = SimpleNamespace(plan_v2=plan, result=SimpleNamespace(ticker="AAPL"))
    analyze.build_decision_context(item, {}, None)
    assert seen.get("ticker") == "AAPL"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/planning/test_sizing_backstop.py)`
Expected: FAIL — `TypeError: compute_position_size() got an unexpected keyword argument 'ticker'`; helper tests `AttributeError`.

- [ ] **Step 3: Implement the helpers**

In `$WT/swingbot/core/planning/account.py`, add directly above `compute_position_size`:

```python
_EDGE_SIZING_MODES = ("kelly", "vol_target", "min_of_all")


def _edge_risk_pct(mode: str, risk_pct: float, strategy_stats, ticker_atr_pct,
                   open_positions) -> tuple[float, str]:
    """Edge sizing modes (E6) resolve to an effective risk_pct and then size
    as the ordinary risk_pct mode; a missing optional input simply doesn't
    take part in the min(). Any other mode passes through untouched."""
    if mode not in _EDGE_SIZING_MODES:
        return risk_pct, mode
    from swingbot.core.edge import sizing as edge_sizing
    kelly = vol = None
    if mode in ("kelly", "min_of_all") and strategy_stats:
        kelly = edge_sizing.kelly_risk_pct(strategy_stats)
    if mode in ("vol_target", "min_of_all") and ticker_atr_pct:
        vol = edge_sizing.vol_target_risk_pct(
            ticker_atr_pct, app_config.PORTFOLIO_TARGET_DAILY_VOL_PCT, open_positions)
    return edge_sizing.effective_risk_pct(risk_pct, kelly_risk=kelly, vol_risk=vol), "risk_pct"


def _sizing_inputs_finite(balance: float, entry: float, stop_loss: float, ticker: str | None) -> bool:
    """False (with a warning) when NaN/inf would slip past every <= guard."""
    if all(math.isfinite(x) for x in (balance, entry, stop_loss, entry - stop_loss)):
        return True
    log.warning("sizing: ticker=%s non-finite input (balance=%r entry=%r stop_loss=%r); alert left unsized",
                ticker or "?", balance, entry, stop_loss)
    return False


def _usable_risk_pct(stored: float, effective: float, ticker: str | None) -> float | None:
    """The risk % to size from in risk_pct mode: None for an invalid stored or
    effective value (warned) or a deliberate 0 (silent); clamped to the hard
    cap (warned) above it -- v187 D2 backstop for rows the validator never saw."""
    name = ticker or "?"
    if not math.isfinite(stored) or stored <= 0:
        log.warning("sizing: ticker=%s stored risk_pct=%r is not a positive finite number; alert left unsized",
                    name, stored)
        return None
    if not math.isfinite(effective):
        log.warning("sizing: ticker=%s effective risk_pct=%r (stored %r) is not finite; alert left unsized",
                    name, effective, stored)
        return None
    if effective <= 0:
        return None
    if effective > RISK_CEILING_PCT:
        log.warning("sizing: ticker=%s risk_pct=%r (stored %r) is above the %s%% hard cap; sized at %s%%",
                    name, effective, stored, RISK_CEILING_PCT, RISK_CEILING_PCT)
        return RISK_CEILING_PCT
    return effective


def _apply_size_caps(raw_shares: float, position_value: float, entry: float, stop_distance: float,
                     balance: float, max_position_pct: float, max_value_abs: float,
                     max_risk_abs: float) -> tuple[float, bool]:
    """The three existing caps, in order (see compute_position_size's docstring);
    returns (shares, capped). position_value is the pre-cap value the mode
    computed, compared exactly as before."""
    capped = False
    max_position_value = balance * max_position_pct / 100.0
    if position_value > max_position_value:
        raw_shares = max_position_value / entry
        capped = True
    # Absolute currency caps -- always enforced last, on top of whatever the
    # %-based sizing/cap above produced, so they hold no matter what balance
    # or % settings are in play.
    if max_value_abs > 0 and raw_shares > max_value_abs / entry:
        raw_shares = max_value_abs / entry
        capped = True
    if max_risk_abs > 0 and stop_distance > 0 and raw_shares > max_risk_abs / stop_distance:
        raw_shares = max_risk_abs / stop_distance
        capped = True
    return raw_shares, capped
```

- [ ] **Step 4: Rewrite `compute_position_size` around them**

Signature and body (the docstring keeps its text; its "Returns None when ..." paragraph is replaced by the one shown):

```python
def compute_position_size(entry: float, stop_loss: float, account_cfg: dict = None,
                          *, strategy_stats: dict = None, ticker_atr_pct: float = None,
                          open_positions: int = 0, ticker: str | None = None) -> dict | None:
    """
    ...existing docstring text down to the "Returns None" paragraph...

    Returns None when balance <= 0, entry <= 0, balance/entry/stop is not
    finite, or (risk_pct mode only) stop distance is zero or the risk % is
    unusable: a stored risk_pct that is not a positive finite number, or an
    effective one that is not finite or is <= 0. A risk % above
    RISK_CEILING_PCT is clamped to it (v187 D2 backstop for rows the
    validator never saw). Every refusal for an invalid value, and every clamp,
    logs a `sizing:` warning naming `ticker` (keyword-only, for that text only).

    ...existing "Return dict keys" block unchanged...
    """
    if account_cfg is None:
        account_cfg = load_account_config()

    balance = float(account_cfg.get("balance", 0))
    stored_risk_pct = float(account_cfg.get("risk_pct", 1.0))
    position_pct = float(account_cfg.get("position_pct", app_config.POSITION_SIZE_PCT_OF_ACCOUNT))
    max_position_pct = float(account_cfg.get("max_position_pct", app_config.MAX_POSITION_SIZE_PCT))
    max_position_value_absolute = float(account_cfg.get(
        "max_position_value_absolute", app_config.MAX_POSITION_VALUE_ABSOLUTE))
    max_risk_amount_absolute = float(account_cfg.get(
        "max_risk_amount_absolute", app_config.MAX_RISK_AMOUNT_ABSOLUTE))
    risk_pct, mode = _edge_risk_pct(account_cfg.get("sizing_mode", "risk_pct"), stored_risk_pct,
                                    strategy_stats, ticker_atr_pct, open_positions)

    # Opex size reduction, applied after the edge estimators so it composes
    # with kelly/vol_target rather than being overwritten by them. BOTH modes
    # are scaled: account_pct never reads risk_pct, so scaling only that one
    # would silently exempt every account_pct user.
    _opex_size_mult = opex.size_mult()
    if _opex_size_mult != 1.0:
        risk_pct *= _opex_size_mult
        position_pct *= _opex_size_mult

    if balance <= 0 or entry <= 0:
        return None
    if not _sizing_inputs_finite(balance, entry, stop_loss, ticker):
        return None

    stop_distance = abs(entry - stop_loss)

    if mode == "account_pct":
        # Fixed allocation: the position is always exactly position_pct% of
        # the account, independent of how far away the stop sits.
        position_value = balance * position_pct / 100.0
        raw_shares = position_value / entry
    else:
        mode = "risk_pct"   # normalize anything unrecognized to the documented default
        if stop_distance <= 0:
            return None
        risk_pct = _usable_risk_pct(stored_risk_pct, risk_pct, ticker)
        if risk_pct is None:
            return None
        risk_amount = balance * risk_pct / 100.0
        raw_shares = risk_amount / stop_distance
        position_value = raw_shares * entry

    raw_shares, capped = _apply_size_caps(
        raw_shares, position_value, entry, stop_distance, balance,
        max_position_pct, max_position_value_absolute, max_risk_amount_absolute)

    # Always the REAL figures for the final (possibly capped) share count --
    # never a pre-cap "intended" number -- so what's shown is always what
    # this trade would actually do to the account.
    position_value = raw_shares * entry
    risk_amount = raw_shares * stop_distance
    shares = round(raw_shares, 2)
    if not math.isfinite(shares):
        log.warning("sizing: ticker=%s share count %r is not finite; alert left unsized", ticker or "?", shares)
        return None

    return {
        "shares":           shares,
        "risk_amount":      round(risk_amount, 2),
        "position_value":   round(position_value, 2),
        "capped":           capped,
        "balance":          balance,
        "risk_pct":         risk_pct,
        "position_pct":     position_pct,
        "max_position_pct": max_position_pct,
        "max_position_value_absolute": max_position_value_absolute,
        "max_risk_amount_absolute":    max_risk_amount_absolute,
        "mode":             mode,
    }
```

The two absolute caps compare `raw_shares > max / entry` (and `/ stop_distance`) exactly as the old code's `max_shares_for_position` / `max_shares_for_risk` did, so they are bit-identical. In `$WT/swingbot/core/scanning/analyze.py` (l.254-255) the call becomes:

```python
        sizing = account_module.compute_position_size(
            plan.trigger_price or plan.entry_price, plan.stop_loss, account_cfg, ticker=ticker)
```

- [ ] **Step 5: Run the tests and the complexity gate**

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/planning/test_sizing_backstop.py)` → PASS.
Run each file in this document's "Existing sizing tests" list with `(cd "$WT" && python scripts/dev/testrun.py file <file>)` → PASS, unchanged.
Run: `(cd "$WT" && python scripts/dev/complexity_gate.py)` → no offender; `compute_position_size` is below its baseline 18 (shrink the baseline with `python scripts/dev/complexity_gate.py --update` only if the gate reports it can shrink, and commit that file too).

- [ ] **Step 6: Commit**

```bash
git -C "$WT" add swingbot/core/planning/account.py swingbot/core/scanning/analyze.py tests/planning/test_sizing_backstop.py
git -C "$WT" commit -m "fix(sizing): refuse non-finite inputs and invalid stored risk, clamp risk to the 2% cap (v187 D2)"
```

(Add `scripts/dev/complexity_baseline.json` to that `git add` if `--update` changed it.)

### Task V187-7: 2% ceiling in both modes and floor-on-breach rounding

**Model:** opus — the final money-path invariant (`shares × stop ≤ 2%` on the returned figure) with a float tolerance and a rounding rule that must leave every in-ceiling output bit-identical.

**Files:**
- Modify: `swingbot/core/planning/account.py` (`compute_position_size`'s tail after V187-6; two helpers and `_RISK_TOLERANCE` above it)
- Create: `tests/planning/test_sizing_risk_ceiling.py`
- Create: `tests/scanning/test_alert_size_matches_engine.py`

**Interfaces:**
- Consumes: V187-6's `compute_position_size` body and `_apply_size_caps`; `RISK_CEILING_PCT`, `math`.
- Produces: `_RISK_TOLERANCE = 1e-9`; `_cap_to_risk_ceiling(raw_shares: float, stop_distance: float, balance: float) -> tuple[float, bool]`; `_settle_shares(raw_shares: float, stop_distance: float, balance: float) -> tuple[float, float]` returning `(basis_for_figures, reported_shares)`.

**Why (spec D2 "Numerics", "The 2% cap also binds in account_pct mode"; index clarification 4).** In `account_pct` mode size comes from `position_pct` alone, so a wide stop can risk more than 2%. After every existing cap, shares are cut, in both modes, so `shares × stop_distance ≤ balance × RISK_CEILING_PCT / 100`, setting `capped = True` when the cut fires. The cut fires only above `limit × (1 + 1e-9)`, so a config sitting exactly at `risk_pct = 2.0` is not reported as capped because of float noise. Then rounding: `round(raw_shares, 2)` stays, unless the rounded figure would breach the same toleranced limit, in which case shares are floored to 2 decimals and `position_value` / `risk_amount` are computed from the floored shares (otherwise from the unrounded shares, exactly as today). Both steps are skipped when `stop_distance <= 0` (`account_pct` with entry == stop has no stop risk). Every output that already respects the ceiling is bit-identical. The alert's suggested size (`analyze.build_decision_context` → `ctx["sizing"]["shares"]`) and the engine's size (`performance.log_trade` → `compute_position_size(entry, stop_loss)`) come from the same function and config; the scanning test pins them equal for a legacy `risk_pct=10`.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/planning/test_sizing_risk_ceiling.py`:

```python
"""v187 D2: the 2% risk ceiling binds in both sizing modes, on the RETURNED
(rounded) share count; rounding floors only when it would breach."""
import itertools

import pytest

from swingbot.core.edge.sizing import RISK_CEILING_PCT
from swingbot.core.planning import account as acct

CFG = {"balance": 10_000.0, "risk_pct": 1.0, "position_pct": 20.0, "max_position_pct": 100.0,
       "max_position_value_absolute": 0.0, "max_risk_amount_absolute": 0.0, "sizing_mode": "risk_pct"}
LIMIT = CFG["balance"] * RISK_CEILING_PCT / 100      # 200.0


@pytest.fixture(autouse=True)
def no_opex(monkeypatch):
    monkeypatch.setattr(acct.opex, "size_mult", lambda *a, **k: 1.0)


def _size(entry=100.0, stop=98.0, **cfg):
    return acct.compute_position_size(entry, stop, {**CFG, **cfg})


def test_account_pct_wide_stop_is_cut_to_two_percent_risk():
    out = _size(stop=80.0, sizing_mode="account_pct")      # 20 shares x $20 = $400 = 4%
    assert (out["shares"], out["risk_amount"], out["position_value"], out["capped"]) == (10.0, 200.0, 1000.0, True)


def test_account_pct_inside_the_ceiling_is_unchanged():
    out = _size(stop=95.0, sizing_mode="account_pct")      # 20 x $5 = $100 = 1%
    assert (out["shares"], out["risk_amount"], out["capped"]) == (20.0, 100.0, False)


def test_account_pct_with_no_stop_distance_is_sized_as_today():
    out = _size(stop=100.0, sizing_mode="account_pct")
    assert (out["shares"], out["risk_amount"], out["capped"]) == (20.0, 0.0, False)


def test_exactly_two_percent_is_not_reported_as_capped():
    out = _size(risk_pct=RISK_CEILING_PCT)
    assert (out["shares"], out["risk_amount"], out["capped"]) == (100.0, 200.0, False)


def test_a_round_up_that_would_breach_is_floored():
    out = _size(stop=97.0, risk_pct=RISK_CEILING_PCT)      # raw 66.666..., round -> 66.67 x 3 = 200.01
    assert out["shares"] == 66.66
    assert (out["risk_amount"], out["position_value"]) == (round(66.66 * 3, 2), round(66.66 * 100, 2))
    assert out["shares"] * 3.0 <= LIMIT * (1 + 1e-9)


def test_a_round_up_inside_the_ceiling_is_kept():
    out = _size(stop=94.0)                                  # raw 16.666..., 16.67 x 6 = 100.02 <= 200
    assert (out["shares"], out["risk_amount"], out["position_value"]) == (16.67, 100.0, 1666.67)


def test_absolute_caps_still_bind_first():
    out = _size(stop=80.0, sizing_mode="account_pct", max_risk_amount_absolute=100.0)
    assert (out["shares"], out["risk_amount"], out["capped"]) == (5.0, 100.0, True)


@pytest.mark.parametrize("mode,entry,distance,risk,position", list(itertools.product(
    ("risk_pct", "account_pct"), (7.31, 100.0, 312.17), (0.013, 0.37, 3.0, 41.9), (0.5, 2.0, 10.0), (5.0, 60.0),
)))
def test_returned_shares_never_risk_more_than_the_ceiling(mode, entry, distance, risk, position):
    out = _size(entry=entry, stop=entry - distance, sizing_mode=mode, risk_pct=risk, position_pct=position)
    assert out["shares"] * distance <= LIMIT * (1 + 1e-9)


def test_helpers():
    assert acct._RISK_TOLERANCE == 1e-9
    assert acct._cap_to_risk_ceiling(20.0, 20.0, 10_000.0) == (10.0, True)
    assert acct._cap_to_risk_ceiling(20.0, 5.0, 10_000.0) == (20.0, False)
    assert acct._cap_to_risk_ceiling(20.0, 0.0, 10_000.0) == (20.0, False)
    assert acct._settle_shares(200.0 / 3.0, 3.0, 10_000.0) == (66.66, 66.66)
    assert acct._settle_shares(100.0 / 6.0, 6.0, 10_000.0) == (100.0 / 6.0, 16.67)
    assert acct._settle_shares(20.0, 0.0, 10_000.0) == (20.0, 20.0)
```

Create `$WT/tests/scanning/test_alert_size_matches_engine.py`:

```python
"""v187 D2: the alert's suggested size and the engine's trade size are the
same compute_position_size call -- equal, and at the 2% cap, for a legacy
risk_pct=10 account row."""
from types import SimpleNamespace

from swingbot.core.edge.sizing import RISK_CEILING_PCT
from swingbot.core.planning import account as acct
from swingbot.core.scanning import analyze

LEGACY = {"balance": 10_000.0, "risk_pct": 10.0, "position_pct": 20.0, "max_position_pct": 100.0,
          "max_position_value_absolute": 0.0, "max_risk_amount_absolute": 0.0, "sizing_mode": "risk_pct"}


def test_alert_size_equals_engine_size_for_a_legacy_ten_percent_row(monkeypatch):
    monkeypatch.setattr(acct.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(acct, "load_account_config", lambda: dict(LEGACY))
    monkeypatch.setattr(analyze, "load_account_config", lambda: dict(LEGACY))
    monkeypatch.setattr(analyze.trade_log, "get_trades", lambda **k: [])
    monkeypatch.setattr(analyze.corr_mod, "cluster_exposure", lambda *a, **k: {"cluster": []})
    plan = SimpleNamespace(ticker="AAPL", trigger_price=100.0, entry_price=100.0, stop_loss=98.0,
                           tp1=104.0, strategy="X", quality_breakdown=[], quality_score=0,
                           badge=None, badge_stats=None)
    item = SimpleNamespace(plan_v2=plan, result=SimpleNamespace(ticker="AAPL"))

    alert = analyze.build_decision_context(item, {}, None)["sizing"]
    engine = acct.compute_position_size(100.0, 98.0)   # what performance.log_trade calls

    assert alert["shares"] == engine["shares"] == 100.0
    assert alert["risk_pct"] == engine["risk_pct"] == RISK_CEILING_PCT
    assert engine["risk_amount"] == 200.0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/planning/test_sizing_risk_ceiling.py)`
Expected: FAIL — the wide-stop case returns `(20.0, 400.0, 2000.0, False)`, the breach case returns `66.67`, the property grid fails on `account_pct` rows with wide stops, `test_helpers` hits `AttributeError`.

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/scanning/test_alert_size_matches_engine.py)`
Expected: PASS already (V187-6's clamp makes both sides 100 shares at 2%). It is kept as the spec's pinned guard; confirm it is green before and after Step 3.

- [ ] **Step 3: Implement**

In `$WT/swingbot/core/planning/account.py`, add above `compute_position_size` (below `_apply_size_caps`):

```python
# Relative slack on the 2% ceiling, so a config sitting exactly at
# RISK_CEILING_PCT is not reported as capped because of float noise.
_RISK_TOLERANCE = 1e-9


def _risk_limit(balance: float) -> float:
    return balance * RISK_CEILING_PCT / 100.0


def _cap_to_risk_ceiling(raw_shares: float, stop_distance: float, balance: float) -> tuple[float, bool]:
    """Shares cut so shares x stop_distance <= RISK_CEILING_PCT of balance, in
    both sizing modes (v187 D2); (shares, capped). No stop risk, no cut."""
    if stop_distance <= 0:
        return raw_shares, False
    limit = _risk_limit(balance)
    if raw_shares * stop_distance > limit * (1 + _RISK_TOLERANCE):
        return limit / stop_distance, True
    return raw_shares, False


def _settle_shares(raw_shares: float, stop_distance: float, balance: float) -> tuple[float, float]:
    """(basis_for_figures, reported_shares). Today's round(raw, 2), unless the
    rounded figure would breach the ceiling: then floored to 2 decimals and the
    floored count is also the basis for risk_amount / position_value."""
    rounded = round(raw_shares, 2)
    if stop_distance > 0 and rounded * stop_distance > _risk_limit(balance) * (1 + _RISK_TOLERANCE):
        floored = math.floor(raw_shares * 100) / 100
        return floored, floored
    return raw_shares, rounded
```

In `compute_position_size`, replace V187-6's tail (from `raw_shares, capped = _apply_size_caps(` to the `return {`) with:

```python
    raw_shares, capped = _apply_size_caps(
        raw_shares, position_value, entry, stop_distance, balance,
        max_position_pct, max_position_value_absolute, max_risk_amount_absolute)
    # The 2% ceiling binds last, in both modes, and on the RETURNED figure.
    raw_shares, ceiling_capped = _cap_to_risk_ceiling(raw_shares, stop_distance, balance)
    capped |= ceiling_capped
    basis, shares = _settle_shares(raw_shares, stop_distance, balance)

    # Always the REAL figures for the final (possibly capped) share count --
    # never a pre-cap "intended" number -- so what's shown is always what
    # this trade would actually do to the account.
    position_value = basis * entry
    risk_amount = basis * stop_distance
    if not math.isfinite(shares):
        log.warning("sizing: ticker=%s share count %r is not finite; alert left unsized", ticker or "?", shares)
        return None
```

The `return {...}` dict is unchanged (it already reads `shares`, `risk_amount`, `position_value`, `capped`). Also add to the docstring's cap list, after item 3:

```
      4. RISK_CEILING_PCT (v187) -- in BOTH modes, the real risk (final
         shares x stop distance) never exceeds this % of balance; shares
         are floored instead of rounded when rounding would breach it.
```

`capped |= ceiling_capped` adds no boolean operator, so the complexity stays where V187-6 left it.

- [ ] **Step 4: Run the tests and the complexity gate**

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/planning/test_sizing_risk_ceiling.py)` → PASS.
Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/scanning/test_alert_size_matches_engine.py)` → PASS.
Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/planning/test_sizing_backstop.py)` → PASS.
Run each file in this document's "Existing sizing tests" list → PASS, unchanged (none of their fixtures exceeds 2% risk; `test_opex_stop_size.py`'s `account_pct` case risks 1%).
Run: `(cd "$WT" && python scripts/dev/complexity_gate.py)` → no offender; `compute_position_size` at or below V187-6's figure.

- [ ] **Step 5: Commit**

```bash
git -C "$WT" add swingbot/core/planning/account.py tests/planning/test_sizing_risk_ceiling.py tests/scanning/test_alert_size_matches_engine.py
git -C "$WT" commit -m "fix(sizing): 2% risk ceiling in both modes on the returned shares; floor only on a breach (v187 D2)"
```

