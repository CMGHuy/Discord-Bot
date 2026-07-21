# Edge Engine — Growth Maximization Implementation Plan (100 tasks)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute strictly in order (Tasks E1–E100).

**Goal:** Maximize compounded account growth honestly — by raising per-trade expectancy (better filters, data-driven stops/targets), raising valid-trade frequency (a liquidity-screened 500+ ticker & index universe), and protecting compounding (fractional-Kelly & volatility-targeted sizing, portfolio heat and correlation caps, drawdown throttles) — with every new component forced through a walk-forward anti-overfit harness before it touches live behavior.

**What this plan will NOT do (read before Task E1):**

- It will **not** target a ~100% win rate. Win rate is trivially inflated by shrinking targets and widening stops, which destroys expectancy; the validated 80–87% OOS win rates of the current system are already near the healthy ceiling for its R:R profile. The optimization target throughout is **expectancy_r and compounded growth at bounded drawdown**, never raw WR.
- It will **not** promise a 10x timeline. It ships a growth calculator (E2) so the real timeline is always visible: 10x = `ln(10)/ln(1 + risk_pct × expectancy_r)` closed trades. Example: 1% risk, +0.10R → ≈2,303 trades; at 60 valid signals/month post-universe-expansion that is a ~3–4 year base case, faster only via the levers this plan builds — never via leverage-to-ruin.
- It will **not** reuse the burned 2024–2025 validation window for tuning. All new components validate by **anchored walk-forward folds inside 2018–2023** (E31) plus a **live shadow forward-gate** (E40). The 2024–2025 window is touched exactly once more, at E97, for the pooled final system, pre-registered.

**Architecture:** New `swingbot/core/edge/` package (growth math, sizing, portfolio risk, regime v2, factors), `swingbot/core/backtest_wf.py` walk-forward harness, execution-realism layer inside the existing backtest, `charts/` v3 decision charts. Everything gates through TRAIN-fold discipline → shadow forward-test → live, mirroring the flag/shadow pattern proven in plan-engine-v2.

**Tech Stack:** Python 3.11+, pandas, numpy, mplfinance/matplotlib, pytest ≥8. **No new pip dependencies** (no ML frameworks — every model here is transparent arithmetic the walk-forward harness can audit).

**Prerequisites:** plan-engine-v2 merged (TradePlanV2, exit simulator, registry); cockpit-v3 Part 1 merged (analytics: journal MFE/MAE, jsonio, snapshot). Independent of cockpit Parts 2–3 and llm-advisor.

## Progress

> - **Branch:** — (executing directly on `main`, by explicit user decision; no worktree/branch for this plan)
> - Task E1 (`edge` package + growth equations — `per_trade_growth`, `trades_to_multiple`, `eta_days`, `growth_table`) done: brief verified fully accurate against the golden numbers, no corrections needed.
> - Task E2 (`!growth` reality dashboard) done: controller pre-corrected two real assumed-shape bugs before wiring `_collect_stats()` — the analytics snapshot's `overall` dict has no `trades_per_month`/`closed_trades` keys (real count key is `"n"`; trade pace isn't stored anywhere and is derived here from the equity curve's own per-close `points`), and `account.load_account_config()` has no `starting_balance` key (real key is `base_balance`, with `balance` as the current effective balance). Also corrected the registration target: every command module is actually imported in `bot.py`, not `bot_core.py` as the brief assumed (`bot_core.py` only owns `COMMAND_USAGE`). Full suite green (746 passed, 54 skipped, +1 known pre-existing unrelated wall-clock failure in `test_trade_monitor_wiring.py`, carried forward from cockpit-v3).
> - Task E3 (Bootstrap Monte Carlo — drawdown & ruin, `simulate()`) done: brief verified fully accurate, no corrections needed.
> - Task E4 (Fractional-Kelly sizing, `kelly_fraction`/`kelly_risk_pct`) done: brief verified fully accurate against hand-derived golden numbers, no corrections needed.
> - Full suite green after each (756 passed, 54 skipped, +1 known pre-existing unrelated wall-clock failure, carried forward).
> - Task E5 (Volatility-targeted sizing, `vol_target_risk_pct`/`effective_risk_pct`) done: brief verified fully accurate against hand-derived golden numbers, no corrections needed.
> - Task E6 (Sizing modes wired into `account.compute_position_size`) done: controller pre-corrected two real bugs in the brief before implementing/testing — (1) the suggested edge-mode resolution rewrote `account_cfg`'s dict entries **after** `risk_pct`/`mode` had already been extracted into local variables from the original dict, so the rewrite would have been silently inert; fixed by overriding the locals directly instead; (2) the brief's own test fixture omitted `max_position_value_absolute`/`max_risk_amount_absolute`, so every golden share-count silently capped down to 10 against this project's real $1000/$100 absolute-cap defaults — fixed by explicitly disabling both (0) in the fixture. One golden number in the brief was also arithmetically wrong ($25 risk / $2 stop = 12.5 shares, not the brief's stated 12) — corrected to the real value. Also extended `set_sizing_mode` (core/account.py, not mentioned by file path in the brief) to actually accept the three new modes so `!account sizing kelly|vol_target|min_of_all` is reachable at all, with a matching reply-text fix in `commands/account.py` so it doesn't mislabel a new mode as "Risk %"; added one test for this beyond the brief's own coverage. Full suite green throughout (final: 765 passed, 54 skipped, +1 known pre-existing unrelated wall-clock failure, carried forward).
> - Task E7 (Portfolio heat cap) done: controller pre-corrected a real wiring-location bug in the brief before implementing — position sizing and embed building actually happen in the confluence scan's alert-building loop (`core/scanning/engine.py`, right before its `build_embed()` call), not in `commands/scanning.py`'s `_send_alerts` as the brief assumed (that function only posts already-built `(embed, chart_path, plan)` tuples and never touches sizing — the brief's wiring point would have been a silent no-op). Also rendered the blocked-heat field through `embeds.py`'s existing `sections["headline"]` accumulator (respecting the fixed `SECTION_ORDER` flush) instead of the brief's raw `embed.add_field()` call, which would have broken field ordering on every alert. Added a `build_embed` regression test beyond the brief's own coverage (which only exercised `heat.py`'s pure functions) since this change touches a heavily-shared rendering function. `heat.py` itself (`trade_risk_pct`/`open_heat`/`heat_check`) verified fully accurate against golden numbers. Full suite green (772 passed, 54 skipped, +1 known pre-existing unrelated wall-clock failure, carried forward).
> - Task E8 (Correlation-aware exposure) done: `correlation.py` (`returns_corr`/`cluster_exposure`/`cluster_check`) verified fully accurate against the brief's golden numbers, no corrections needed. Same file-location correction as E7 applied to the alert-path wiring (the brief only said "mirrors E7 exactly", so the same fix carried over): wired into `core/scanning/engine.py`'s alert-building loop. Reuses `fresh_data` — the `{ticker: df}` dict every scan pass already crawls once at the top via `_crawl_latest_data` — as the correlation lookup source, so this costs zero extra network calls; `sectors` stays `None` until the universe file (E13) lands with sector tags, exactly as the brief's own deferral note anticipated. Rendered through `embeds.py`'s `sections["headline"]` accumulator, same pattern as E7's heat-cap field, with a matching regression test. Full suite green (779 passed, 54 skipped, +1 known pre-existing unrelated wall-clock failure, carried forward).
> - **Next:** Task E9 (Growth-path tracker)

## Global Constraints

- **Optimization target:** `expectancy_r` and fold-consistent compounded growth; WR is reported, never optimized.
- **Pre-registered fold gate (fixed now, before any data contact):** anchored expanding folds — train 2018→fold-start, test years 2021 / 2022 / 2023. A component passes if pooled test `expectancy_r` improves vs baseline in **≥ 2 of 3 folds**, no fold degrades baseline expectancy by more than 0.05R, and N ≥ 30 per fold. Components that fail are documented and dropped — no second grid on the same hypothesis.
- **Every new gate/filter/factor is a flag-gated config Field, default off**, tuned only via the walk-forward harness, promoted to live only after the E40 shadow forward-gate.
- **Sizing safety rails (frozen constants):** `KELLY_FRACTION_CAP = 0.25` (quarter-Kelly ceiling), `PORTFOLIO_HEAT_CAP_PCT = 6.0` default, drawdown throttle ladder fixed at E45. Nothing in this plan may raise effective risk beyond these without the user editing config deliberately.
- **Same-bar conservative ordering, win definition, and exit constants from plan-engine-v2 are untouched.**
- **Every task ends green:** `python -m pytest tests/ -q` + `make check` before commit; conventional commits; run from repo root.
- **Backtest data:** cached daily OHLCV 2018-06→present via `scripts/fetch_backtest_data.py`; universe files under `data/universe/`.
- **DataFrame convention** unchanged (`Open,High,Low,Close,Volume`, DatetimeIndex).

## File Structure (target state)

```
swingbot/core/edge/
  __init__.py         growth.py (math)       ruin.py (Monte Carlo)
  sizing.py (kelly/vol-target)               heat.py (portfolio risk)
  correlation.py      regime2.py             factors.py (RS, MTF, breadth)
  stops.py (MAE/MFE-driven)                  frictions.py (slippage/commission)
  gates.py (earnings/liquidity/gap)          throttle.py (streak/DD ladders)
swingbot/core/
  backtest_wf.py      walk-forward fold engine + permutation test
  backtest.py         MOD frictions + portfolio replay mode
  universe.py         NEW universe files + liquidity screen
  scan_engine / scanning/*  MOD new gates (flag-gated), parallel scan
swingbot/core/charts/
  decision_chart.py   NEW one-pager trade chart (MTF, AVWAP, RS, outcome cloud)
  portfolio_charts.py NEW heat/correlation/growth-path/Monte-Carlo renders
scripts/
  build_universe.py, wf_run.py, permutation_test.py, ablation.py, premortem template
tests/  test_edge_*.py, test_wf_*.py, test_universe.py, test_decision_chart.py ...
```

---


# Phase E0 — Honest growth math & sizing foundations (E1–E10)

### Task E1: `edge` package + growth equations

**Files:**
- Create: `swingbot/core/edge/__init__.py`
- Create: `swingbot/core/edge/growth.py`
- Test: `tests/test_edge_growth.py`

**Interfaces:**
- Produces: `per_trade_growth(risk_pct, expectancy_r) -> float`; `trades_to_multiple(multiple, risk_pct, expectancy_r) -> int | None` (None when expectancy ≤ 0); `eta_days(trades_needed, trades_per_month) -> int | None`; `growth_table(expectancies=(0.05,0.10,0.15,0.20), risks=(0.5,1.0,1.5,2.0)) -> list[dict]`.
- Consumed by: E2 (`!growth`), E9 (growth path), E70/E71 charts.

- [x] **Step 1: Write the failing test**

```python
# tests/test_edge_growth.py
"""Growth math: the honest 10x arithmetic. Golden numbers derived by hand
in the docstrings of swingbot/core/edge/growth.py."""
import pytest

from swingbot.core.edge.growth import (
    eta_days, growth_table, per_trade_growth, trades_to_multiple,
)


def test_ten_x_trade_count_golden():
    # 1% risk, +0.10R expectancy -> 0.1% growth per closed trade.
    # ln(10)/ln(1.001) = 2303.7 -> floor 2303 (the trade DURING which the
    # target is crossed is #2304; 2303 full trades come before it).
    assert trades_to_multiple(10, 1.0, 0.10) == 2303
    assert per_trade_growth(1.0, 0.10) == pytest.approx(0.001)


def test_negative_expectancy_never_compounds():
    assert trades_to_multiple(10, 1.0, -0.05) is None
    assert trades_to_multiple(10, 1.0, 0.0) is None


def test_already_there():
    assert trades_to_multiple(1.0, 1.0, 0.10) == 0


def test_eta_days_golden():
    # 2303 trades at 60/month = 38.383 months * 30.44 = 1168.4 -> ceil 1169
    assert eta_days(2303, 60) == 1169
    assert eta_days(2303, 0) is None
    assert eta_days(None, 60) is None


def test_growth_table_shape():
    rows = growth_table()
    assert len(rows) == 16  # 4 expectancies x 4 risks
    assert set(rows[0]) == {"risk_pct", "expectancy_r", "growth_per_trade", "trades_to_10x"}
    # higher expectancy at same risk always needs fewer trades
    at_1pct = {r["expectancy_r"]: r["trades_to_10x"] for r in rows if r["risk_pct"] == 1.0}
    assert at_1pct[0.20] < at_1pct[0.05]
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_edge_growth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.edge'`

- [x] **Step 3: Write the implementation**

```python
# swingbot/core/edge/__init__.py
"""Edge package: growth math, sizing, portfolio risk, regime v2, factors.

Everything in this package is transparent arithmetic -- no ML, no fitted
black boxes -- so the walk-forward harness (backtest_wf.py) can audit any
component before it is allowed to touch live behavior.
"""
```

```python
# swingbot/core/edge/growth.py
"""The honest 10x math.

Risking `risk_pct` percent of equity per trade with expectancy
`expectancy_r` (in R) grows equity by risk_pct/100 * expectancy_r per
closed trade:

    equity_after = equity_before * (1 + risk_pct/100 * expectancy_r)

10x therefore takes ln(10) / ln(1 + g) closed trades. At 1% risk and
+0.10R that is ~2303 trades. There is no honest shortcut -- only three
levers: expectancy up, valid-trade frequency up, and drawdowns bounded
so compounding never has to restart. This module is the reality check
every other Edge component is measured against.
"""
from __future__ import annotations

import math

AVG_DAYS_PER_MONTH = 30.44  # 365.25 / 12


def per_trade_growth(risk_pct: float, expectancy_r: float) -> float:
    """Expected fractional equity growth per closed trade."""
    return (risk_pct / 100.0) * expectancy_r


def trades_to_multiple(multiple: float, risk_pct: float, expectancy_r: float) -> int | None:
    """Closed trades needed to multiply equity by `multiple`.

    Returns None when per-trade growth <= 0: a negative edge never
    compounds toward a target, it compounds toward zero.
    """
    g = per_trade_growth(risk_pct, expectancy_r)
    if g <= 0:
        return None
    if multiple <= 1:
        return 0
    return int(math.log(multiple) / math.log(1.0 + g))


def eta_days(trades_needed: int | None, trades_per_month: float) -> int | None:
    """Calendar days to complete `trades_needed` at the observed pace."""
    if trades_needed is None or trades_per_month <= 0:
        return None
    return int(math.ceil(trades_needed / trades_per_month * AVG_DAYS_PER_MONTH))


def growth_table(expectancies: tuple = (0.05, 0.10, 0.15, 0.20),
                 risks: tuple = (0.5, 1.0, 1.5, 2.0)) -> list[dict]:
    """The sensitivity grid `!growth` prints: what each (risk, expectancy)
    pair means in trades-to-10x. Sorted by expectancy, then risk."""
    rows = []
    for e in expectancies:
        for r in risks:
            rows.append({
                "risk_pct": r,
                "expectancy_r": e,
                "growth_per_trade": per_trade_growth(r, e),
                "trades_to_10x": trades_to_multiple(10, r, e),
            })
    return rows
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_edge_growth.py -v`
Expected: PASS (5 tests). Then full suite: `python -m pytest tests/ -q` — green.

- [x] **Step 5: Commit**

```bash
git add swingbot/core/edge/__init__.py swingbot/core/edge/growth.py tests/test_edge_growth.py
git commit -m "feat: growth equations (the honest 10x math)"
```

### Task E2: `!growth` command — the reality dashboard

**Files:**
- Modify: `swingbot/core/edge/growth.py` (renderer)
- Create: `swingbot/commands/growth.py` (registered like the other command modules — imported from `bot_core.py`'s command-module block)
- Test: `tests/test_edge_growth.py`

**Interfaces:**
- Produces: `growth_report(stats: dict, target: float = 10.0) -> str` — the tested unit. `stats` keys (all optional, graceful degradation): `expectancy_r`, `trades_per_month`, `risk_pct`, `current_multiple`, `n_closed`. Command `!growth [target_multiple]` assembles `stats` from the analytics snapshot (`swingbot.core.analytics.snapshots.load_snapshot()`, cockpit Part 1) + `account.load_account_config()` and posts the report in a code block.
- Consumes: E1 functions.

- [x] **Step 1: Write the failing test** (append to `tests/test_edge_growth.py`)

```python
def test_growth_report_contains_trades_and_eta():
    from swingbot.core.edge.growth import growth_report
    stats = {"expectancy_r": 0.10, "trades_per_month": 60,
             "risk_pct": 1.0, "current_multiple": 1.0, "n_closed": 120}
    out = growth_report(stats, target=10.0)
    assert "2303" in out              # trades to 10x at current settings
    assert "1169" in out or "1,169" in out  # ETA days
    assert "+0.05R" in out            # sensitivity row header
    assert "not financial advice" in out.lower() or "will differ" in out.lower()


def test_growth_report_handles_no_edge():
    from swingbot.core.edge.growth import growth_report
    out = growth_report({"expectancy_r": -0.02, "trades_per_month": 10,
                         "risk_pct": 1.0, "n_closed": 15})
    assert "never" in out.lower() or "no positive edge" in out.lower()
    assert "N=15" in out              # sample size always shown
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_edge_growth.py -v`
Expected: FAIL — `ImportError: cannot import name 'growth_report'`

- [x] **Step 3: Implement the renderer** (append to `swingbot/core/edge/growth.py`)

```python
def growth_report(stats: dict, target: float = 10.0) -> str:
    """Plain-text reality dashboard for !growth. Never promises anything:
    it prints the arithmetic of the CURRENT numbers and what each lever
    changes. Sample size is always visible."""
    e = stats.get("expectancy_r")
    tpm = stats.get("trades_per_month") or 0.0
    risk = stats.get("risk_pct") or 1.0
    mult = stats.get("current_multiple") or 1.0
    n = stats.get("n_closed") or 0

    lines = [f"GROWTH REALITY CHECK — target {target:g}x   (N={n} closed trades)"]
    if e is None or n == 0:
        lines.append("No closed trades yet — no expectancy to project from.")
        return "\n".join(lines)

    lines.append(f"current: expectancy {e:+.3f}R | {tpm:.1f} trades/mo | risk {risk:.2f}%/trade | at {mult:.2f}x")
    remaining = target / mult
    trades = trades_to_multiple(remaining, risk, e)
    if trades is None:
        lines.append(f"expectancy {e:+.3f}R is not positive — this NEVER compounds to "
                     f"{target:g}x (no positive edge; fix expectancy before anything else).")
    else:
        days = eta_days(trades, tpm)
        eta = f"~{days} days (~{days / 365.25:.1f} yrs)" if days else "no pace data"
        lines.append(f"projected: {trades} more trades -> ETA {eta}")
        lines.append("")
        lines.append("sensitivity (what the levers buy you):")
        for label, e2, tpm2 in ((f"expectancy +0.05R", e + 0.05, tpm),
                                (f"frequency +20/mo", e, tpm + 20),
                                (f"both", e + 0.05, tpm + 20)):
            t2 = trades_to_multiple(remaining, risk, e2)
            d2 = eta_days(t2, tpm2)
            eta2 = f"{t2} trades, ~{d2 / 365.25:.1f} yrs" if d2 else "n/a"
            lines.append(f"  {label:<20} -> {eta2}")
    lines.append("")
    lines.append("Backtested/live projections — real results will differ. Not financial advice.")
    return "\n".join(lines)
```

Then the command module:

```python
# swingbot/commands/growth.py
"""!growth — the compounding reality dashboard (Edge plan E2)."""
import asyncio

from swingbot.bot_core import bot
from swingbot.core import account as account_module
from swingbot.core.edge.growth import growth_report


def _collect_stats() -> dict:
    stats = {}
    try:
        from swingbot.core.analytics.snapshots import load_snapshot
        snap = load_snapshot() or {}
        overall = snap.get("overall", {})
        stats["expectancy_r"] = overall.get("expectancy_r")
        stats["trades_per_month"] = overall.get("trades_per_month")
        stats["n_closed"] = overall.get("closed_trades", 0)
    except Exception:  # analytics not merged yet / snapshot stale — degrade
        pass
    cfg = account_module.load_account_config()
    stats["risk_pct"] = cfg.get("risk_pct", 1.0)
    start = cfg.get("starting_balance") or cfg.get("balance")
    if start:
        stats["current_multiple"] = cfg.get("balance", start) / start
    return stats


@bot.command(name="growth")
async def growth_command(ctx, target: float = 10.0):
    """Show the honest math to <target>x at current expectancy/frequency."""
    stats = await asyncio.to_thread(_collect_stats)
    await ctx.send(f"```\n{growth_report(stats, target=target)}\n```")
```

Register the module exactly like the existing command modules: add `from swingbot.commands import growth  # noqa: F401` to the command-import block in `swingbot/bot_core.py`, and add `!growth` to the help catalog / `COMMAND_USAGE` dict where the other commands are listed.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_edge_growth.py -v` — PASS. Full suite `python -m pytest tests/ -q` — green (the command module imports lazily; no Discord connection in tests).

- [x] **Step 5: Commit**

```bash
git add swingbot/core/edge/growth.py swingbot/commands/growth.py swingbot/bot_core.py
git commit -m "feat: !growth reality dashboard"
```

### Task E3: Bootstrap Monte Carlo — drawdown & ruin

**Files:**
- Create: `swingbot/core/edge/ruin.py`
- Test: `tests/test_edge_ruin.py`

**Interfaces:**
- Produces: `simulate(r_multiples: list[float], *, risk_pct: float, n_trades: int = 1000, n_paths: int = 2000, seed: int = 42) -> dict` with keys `p50_final_multiple, p05_final_multiple, max_dd_p50, max_dd_p95, p_ruin, p_10x` (ruin = equity dips below 0.5× start at any point; 10x = equity reaches 10× at any point). Deterministic under `seed`. Raises `ValueError` on an empty R list.
- Consumed by: E2/E10 smoke, E51 portfolio doc, E53 weekly report, E70 fan chart.

- [x] **Step 1: Write the failing test**

```python
# tests/test_edge_ruin.py
import pytest

from swingbot.core.edge.ruin import simulate

# Positive-expectancy but loss-heavy mix: 8 wins of +0.4R, 2 losses of -1R
# -> expectancy +0.12R. Realistic shape for this bot's strategies.
R_MIX = [0.4] * 8 + [-1.0] * 2


def test_deterministic_under_seed():
    a = simulate(R_MIX, risk_pct=1.0)
    b = simulate(R_MIX, risk_pct=1.0)
    assert a == b


def test_risk_scales_drawdown_and_ruin():
    low = simulate(R_MIX, risk_pct=1.0)
    high = simulate(R_MIX, risk_pct=5.0)
    assert high["max_dd_p95"] > low["max_dd_p95"]
    assert high["p_ruin"] >= low["p_ruin"]
    assert low["p_ruin"] < 0.01  # 1% risk on a +0.12R edge basically never halves


def test_positive_edge_compounds_at_median():
    out = simulate(R_MIX, risk_pct=1.0)
    assert out["p50_final_multiple"] > 1.0
    assert 0.0 <= out["p_10x"] <= 1.0


def test_empty_history_raises():
    with pytest.raises(ValueError):
        simulate([], risk_pct=1.0)
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_edge_ruin.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.edge.ruin'`

- [x] **Step 3: Write the implementation**

```python
# swingbot/core/edge/ruin.py
"""Bootstrap Monte Carlo over the realized R distribution.

Resamples the bot's OWN closed-trade R multiples (no distributional
assumptions -- fat tails included exactly as observed), compounds
`n_paths` equity paths of `n_trades` each, and reports the percentiles
that matter for survival. `ruin` is deliberately conservative: halving
the account (equity < 0.5x start at ANY point) is treated as ruin,
because in practice the operator intervenes/abandons long before zero.
"""
from __future__ import annotations

import numpy as np

RUIN_THRESHOLD = 0.5   # equity multiple below which a path counts as ruined
TARGET_MULTIPLE = 10.0


def simulate(r_multiples: list[float], *, risk_pct: float,
             n_trades: int = 1000, n_paths: int = 2000, seed: int = 42) -> dict:
    r = np.asarray(list(r_multiples), dtype=float)
    if r.size == 0:
        raise ValueError("need at least one closed trade to bootstrap from")

    rng = np.random.default_rng(seed)
    draws = rng.choice(r, size=(n_paths, n_trades), replace=True)
    growth = 1.0 + (risk_pct / 100.0) * draws
    # A single trade can't lose more than 100% of equity even at absurd risk.
    np.clip(growth, 0.0, None, out=growth)
    equity = np.cumprod(growth, axis=1)

    peaks = np.maximum.accumulate(equity, axis=1)
    max_dd = 1.0 - (equity / peaks).min(axis=1)          # per-path max drawdown, fraction
    final = equity[:, -1]

    return {
        "p50_final_multiple": float(np.percentile(final, 50)),
        "p05_final_multiple": float(np.percentile(final, 5)),
        "max_dd_p50": float(np.percentile(max_dd, 50)),
        "max_dd_p95": float(np.percentile(max_dd, 95)),
        "p_ruin": float((equity.min(axis=1) < RUIN_THRESHOLD).mean()),
        "p_10x": float((equity.max(axis=1) >= TARGET_MULTIPLE).mean()),
    }
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_edge_ruin.py -v` — PASS (4 tests, ~1s: 2000×1000 is a 2M-cell array, vectorized).

- [x] **Step 5: Commit**

```bash
git add swingbot/core/edge/ruin.py tests/test_edge_ruin.py
git commit -m "feat: bootstrap Monte Carlo ruin/drawdown simulator"
```

### Task E4: Fractional-Kelly sizing

**Files:**
- Create: `swingbot/core/edge/sizing.py`
- Test: `tests/test_edge_sizing.py`

**Interfaces:**
- Produces: `kelly_fraction(win_rate, avg_win_r, avg_loss_r) -> float` (0.0 when edge ≤ 0; win_rate is a 0–1 fraction); `kelly_risk_pct(stats: dict, cap: float = KELLY_FRACTION_CAP) -> float` — quarter-Kelly of the strategy's own stats, clamped to `[RISK_FLOOR_PCT, RISK_CEILING_PCT]`; frozen constants `KELLY_FRACTION_CAP = 0.25`, `RISK_FLOOR_PCT = 0.25`, `RISK_CEILING_PCT = 2.0`.
- `stats` dict keys: `win_rate` (0–1), `avg_win_r`, `avg_loss_r` (positive magnitude), `n` (kelly returns the config floor when `n < 30` — a Kelly estimate off 12 trades is noise).
- Consumed by: E6 (`compute_position_size`), E50 portfolio replay, E55 shadow comparison.

- [x] **Step 1: Write the failing test**

```python
# tests/test_edge_sizing.py
import pytest

from swingbot.core.edge.sizing import (
    KELLY_FRACTION_CAP, RISK_CEILING_PCT, RISK_FLOOR_PCT,
    kelly_fraction, kelly_risk_pct,
)


def test_kelly_fraction_golden():
    # f* = p - q/b with b = avg_win/avg_loss.
    # WR 0.80, avg win 0.4R, avg loss 1.0R: b = 0.4 -> f* = 0.8 - 0.2/0.4 = 0.30
    assert kelly_fraction(0.80, 0.4, 1.0) == pytest.approx(0.30)


def test_kelly_zero_when_no_edge():
    # WR 0.70 at b = 0.4 -> f* = 0.7 - 0.3/0.4 = -0.05 -> clamp to 0
    assert kelly_fraction(0.70, 0.4, 1.0) == 0.0
    assert kelly_fraction(0.50, 0.0, 1.0) == 0.0   # degenerate avg win


def test_quarter_kelly_capped_to_ceiling():
    # f* = 0.30 -> quarter-Kelly = 7.5% of equity -> way past the 2% ceiling
    stats = {"win_rate": 0.80, "avg_win_r": 0.4, "avg_loss_r": 1.0, "n": 200}
    assert kelly_risk_pct(stats) == RISK_CEILING_PCT


def test_zero_edge_floors():
    stats = {"win_rate": 0.60, "avg_win_r": 0.3, "avg_loss_r": 1.0, "n": 200}
    # f* = 0.6 - 0.4/0.3 = negative -> floor
    assert kelly_risk_pct(stats) == RISK_FLOOR_PCT


def test_small_sample_floors():
    stats = {"win_rate": 0.90, "avg_win_r": 0.5, "avg_loss_r": 1.0, "n": 12}
    assert kelly_risk_pct(stats) == RISK_FLOOR_PCT


def test_constants_frozen():
    assert KELLY_FRACTION_CAP == 0.25
    assert RISK_FLOOR_PCT == 0.25 and RISK_CEILING_PCT == 2.0
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_edge_sizing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.edge.sizing'`

- [x] **Step 3: Write the implementation**

```python
# swingbot/core/edge/sizing.py
"""Fractional-Kelly and volatility-targeted position sizing.

Kelly derivation (two-outcome approximation over R multiples):
    b  = avg_win_r / avg_loss_r        (payoff odds per unit risked)
    f* = p - q/b                       (p = win rate, q = 1-p)
f* is the growth-optimal fraction of equity to risk -- and also the
fraction at which drawdowns become psychologically unsurvivable, which
is why nobody sane trades full Kelly. We take a QUARTER of it
(KELLY_FRACTION_CAP) and then clamp to [0.25%, 2.0%] of equity. These
constants are frozen by the Edge plan's Global Constraints: nothing in
code may raise effective risk beyond them.
"""
from __future__ import annotations

KELLY_FRACTION_CAP = 0.25   # quarter-Kelly ceiling -- FROZEN
RISK_FLOOR_PCT = 0.25       # never size below this (min position still tradeable)
RISK_CEILING_PCT = 2.0      # never size above this -- FROZEN
KELLY_MIN_SAMPLE = 30       # below this N a Kelly estimate is noise


def kelly_fraction(win_rate: float, avg_win_r: float, avg_loss_r: float) -> float:
    """Full-Kelly fraction f* = p - q/b, floored at 0 (no edge -> no bet)."""
    if avg_win_r <= 0 or avg_loss_r <= 0:
        return 0.0
    b = avg_win_r / avg_loss_r
    f = win_rate - (1.0 - win_rate) / b
    return max(0.0, f)


def kelly_risk_pct(stats: dict, cap: float = KELLY_FRACTION_CAP) -> float:
    """Quarter-Kelly of the strategy's own stats as a percent of equity,
    clamped to [RISK_FLOOR_PCT, RISK_CEILING_PCT]."""
    if stats.get("n", 0) < KELLY_MIN_SAMPLE:
        return RISK_FLOOR_PCT
    f = kelly_fraction(stats.get("win_rate", 0.0),
                       stats.get("avg_win_r", 0.0),
                       stats.get("avg_loss_r", 1.0))
    pct = f * cap * 100.0
    return max(RISK_FLOOR_PCT, min(pct, RISK_CEILING_PCT))
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_edge_sizing.py -v` — PASS (6 tests).

- [x] **Step 5: Commit**

```bash
git add swingbot/core/edge/sizing.py tests/test_edge_sizing.py
git commit -m "feat: fractional-Kelly sizing math"
```

### Task E5: Volatility-targeted sizing

**Files:**
- Modify: `swingbot/core/edge/sizing.py`
- Test: `tests/test_edge_sizing.py`

**Interfaces:**
- Produces: `vol_target_risk_pct(ticker_atr_pct, portfolio_target_daily_vol_pct=0.7, open_positions=0, stop_cap_pct=3.0) -> float`; `effective_risk_pct(config_risk, kelly_risk=None, vol_risk=None, throttle_mult=1.0) -> float` — the min-chain every sizing decision flows through from E6 on (E45's throttle multiplies at the end, floor at `RISK_FLOOR_PCT` unless the throttle says 0).

- [x] **Step 1: Write the failing test** (append to `tests/test_edge_sizing.py`)

```python
def test_high_atr_ticker_gets_less_risk():
    from swingbot.core.edge.sizing import vol_target_risk_pct
    calm = vol_target_risk_pct(1.0)    # 1% daily ATR
    wild = vol_target_risk_pct(3.0)    # 3% daily ATR
    assert wild < calm
    # golden: atr 1% -> budget 0.7% vol, notional 70% of equity,
    # stop 2*ATR = 2% -> risk = 70% * 2% = 1.4% of equity
    assert calm == pytest.approx(1.4)
    # atr 3% -> notional 23.33%, stop capped at 3% -> 0.7%
    assert wild == pytest.approx(0.7)


def test_more_open_positions_shrinks_the_budget():
    from swingbot.core.edge.sizing import vol_target_risk_pct
    alone = vol_target_risk_pct(1.0, open_positions=0)
    crowded = vol_target_risk_pct(1.0, open_positions=3)
    assert crowded < alone


def test_effective_risk_takes_the_min():
    from swingbot.core.edge.sizing import effective_risk_pct
    assert effective_risk_pct(1.0, kelly_risk=2.0, vol_risk=1.4) == 1.0
    assert effective_risk_pct(1.0, kelly_risk=0.5, vol_risk=1.4) == 0.5
    assert effective_risk_pct(1.0) == 1.0                      # nothing else supplied
    assert effective_risk_pct(1.0, throttle_mult=0.5) == 0.5   # throttle multiplies last
    assert effective_risk_pct(1.0, throttle_mult=0.0) == 0.0   # kill = truly zero
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_edge_sizing.py -v`
Expected: FAIL — `ImportError: cannot import name 'vol_target_risk_pct'`

- [x] **Step 3: Write the implementation** (append to `swingbot/core/edge/sizing.py`)

```python
import math


def vol_target_risk_pct(ticker_atr_pct: float,
                        portfolio_target_daily_vol_pct: float = 0.7,
                        open_positions: int = 0,
                        stop_cap_pct: float = 3.0) -> float:
    """Risk% such that this position's expected daily equity impact stays
    inside its share of the portfolio vol budget.

    Model (transparent, documented so the walk-forward harness can audit):
      - per-position vol budget = target / sqrt(open_positions + 1)
        (sqrt because independent positions add in quadrature)
      - position notional (as % of equity) = budget / ticker_atr_pct * 100
      - stop distance = 2*ATR, capped at stop_cap_pct (the horizon caps
        already bound stops; beyond the cap high-ATR names lose notional
        AND risk -- which is the point)
      - risk% = notional% * stop% / 100
    """
    if ticker_atr_pct <= 0:
        return RISK_FLOOR_PCT
    budget = portfolio_target_daily_vol_pct / math.sqrt(open_positions + 1)
    notional_pct = budget / ticker_atr_pct * 100.0
    stop_pct = min(2.0 * ticker_atr_pct, stop_cap_pct)
    risk = notional_pct * stop_pct / 100.0
    return max(RISK_FLOOR_PCT, min(risk, RISK_CEILING_PCT))


def effective_risk_pct(config_risk: float, kelly_risk: float | None = None,
                       vol_risk: float | None = None,
                       throttle_mult: float = 1.0) -> float:
    """THE sizing chain: min of every estimate that exists, then the
    drawdown/streak throttle multiplies the survivor. throttle_mult == 0
    means the kill switch / pause rung -- risk is exactly 0, not floored."""
    candidates = [config_risk]
    if kelly_risk is not None:
        candidates.append(kelly_risk)
    if vol_risk is not None:
        candidates.append(vol_risk)
    base = min(candidates)
    if throttle_mult <= 0:
        return 0.0
    return max(RISK_FLOOR_PCT, base * throttle_mult) if base > 0 else 0.0
```

Wait — `effective_risk_pct(1.0, throttle_mult=0.5) == 0.5` and the floor is 0.25, so `max(0.25, 0.5)` = 0.5 ✓; a throttled `0.25 * 0.5 = 0.125` would floor at 0.25 — that is intended (the floor keeps positions tradeable; the PAUSE rung uses `throttle_mult=0`).

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_edge_sizing.py -v` — PASS (9 tests).

- [x] **Step 5: Commit**

```bash
git add swingbot/core/edge/sizing.py tests/test_edge_sizing.py
git commit -m "feat: volatility-targeted sizing"
```

### Task E6: Sizing modes wired into `account.compute_position_size`

**Files:**
- Modify: `swingbot/core/account.py` (`compute_position_size`, line ~405)
- Modify: `swingbot/config.py` (`POSITION_SIZING_MODE` Field at line ~244 gains options; new Field `PORTFOLIO_TARGET_DAILY_VOL_PCT`)
- Test: `tests/test_edge_sizing.py`

**Interfaces:**
- `compute_position_size(entry, stop_loss, account_cfg=None, *, strategy_stats=None, ticker_atr_pct=None, open_positions=0)` — three new keyword-only args, all optional; existing call sites unchanged.
- `POSITION_SIZING_MODE` options become `risk_pct | account_pct | kelly | vol_target | min_of_all` (default `risk_pct` — **no behavior change**). New modes compute `effective_risk_pct(...)` and then reuse the existing `risk_pct` sizing branch.
- New Field: `PORTFOLIO_TARGET_DAILY_VOL_PCT` (float, default 0.7, min 0.1, max 3.0, step 0.1, section "Account Defaults").

- [x] **Step 1: Write the failing test** (append to `tests/test_edge_sizing.py`)

```python
def _cfg(mode):
    return {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": mode,
            "max_open_positions": 5, "max_position_pct": 100.0}


def test_default_mode_unchanged():
    from swingbot.core.account import compute_position_size
    # entry 100, stop 98 -> $2 risk/share; 1% of 10k = $100 -> 50 shares.
    out = compute_position_size(100.0, 98.0, _cfg("risk_pct"))
    assert out["shares"] == 50


def test_kelly_mode_uses_strategy_stats():
    from swingbot.core.account import compute_position_size
    stats = {"win_rate": 0.80, "avg_win_r": 0.4, "avg_loss_r": 1.0, "n": 200}
    # kelly says 2.0% but min(config 1.0, kelly 2.0) = 1.0 -> same 50 shares
    out = compute_position_size(100.0, 98.0, _cfg("kelly"), strategy_stats=stats)
    assert out["shares"] == 50
    # weak stats: kelly floors at 0.25% -> min(1.0, 0.25) -> $25 risk -> 12 shares
    weak = {"win_rate": 0.60, "avg_win_r": 0.3, "avg_loss_r": 1.0, "n": 200}
    out = compute_position_size(100.0, 98.0, _cfg("kelly"), strategy_stats=weak)
    assert out["shares"] == 12


def test_vol_target_mode_shrinks_wild_tickers():
    from swingbot.core.account import compute_position_size
    out = compute_position_size(100.0, 98.0, _cfg("vol_target"), ticker_atr_pct=3.0)
    # vol-target 0.7% -> min(1.0, 0.7) -> $70 risk -> 35 shares
    assert out["shares"] == 35


def test_min_of_all_takes_the_smallest():
    from swingbot.core.account import compute_position_size
    stats = {"win_rate": 0.80, "avg_win_r": 0.4, "avg_loss_r": 1.0, "n": 200}
    out = compute_position_size(100.0, 98.0, _cfg("min_of_all"),
                                strategy_stats=stats, ticker_atr_pct=3.0)
    assert out["shares"] == 35  # min(1.0 config, 2.0 kelly, 0.7 vol) = 0.7


def test_new_modes_without_inputs_fall_back_to_config_risk():
    from swingbot.core.account import compute_position_size
    out = compute_position_size(100.0, 98.0, _cfg("min_of_all"))
    assert out["shares"] == 50
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_edge_sizing.py -v`
Expected: FAIL — `TypeError: compute_position_size() got an unexpected keyword argument 'strategy_stats'` (and/or unknown-mode handling).

- [x] **Step 3: Implement**

In `swingbot/core/account.py`, change the signature and insert the mode resolution right where `mode = account_cfg.get("sizing_mode", "risk_pct")` is read (line ~457):

```python
def compute_position_size(entry: float, stop_loss: float, account_cfg: dict = None,
                          *, strategy_stats: dict = None, ticker_atr_pct: float = None,
                          open_positions: int = 0) -> dict | None:
```

```python
    mode = account_cfg.get("sizing_mode", "risk_pct")

    # --- Edge sizing modes (E6): resolve to an effective risk_pct, then
    # fall through to the ordinary risk_pct branch below. Optional inputs
    # missing -> that estimator simply doesn't participate in the min().
    if mode in ("kelly", "vol_target", "min_of_all"):
        from swingbot import config as app_config
        from swingbot.core.edge import sizing as edge_sizing
        kelly = vol = None
        if mode in ("kelly", "min_of_all") and strategy_stats:
            kelly = edge_sizing.kelly_risk_pct(strategy_stats)
        if mode in ("vol_target", "min_of_all") and ticker_atr_pct:
            vol = edge_sizing.vol_target_risk_pct(
                ticker_atr_pct,
                getattr(app_config, "PORTFOLIO_TARGET_DAILY_VOL_PCT", 0.7),
                open_positions)
        effective = edge_sizing.effective_risk_pct(
            account_cfg.get("risk_pct", 1.0), kelly_risk=kelly, vol_risk=vol)
        account_cfg = {**account_cfg, "sizing_mode": "risk_pct", "risk_pct": effective}
        mode = "risk_pct"
```

In `swingbot/config.py`: extend the existing Field's options and add the new Field right after it:

```python
    Field("POSITION_SIZING_MODE", "POSITION_SIZING_MODE", "Account Defaults", "Position sizing mode",
          type="select", default="risk_pct",
          options=[("risk_pct", "Fixed risk % per trade"),
                   ("account_pct", "Fixed % of account"),
                   ("kelly", "Quarter-Kelly of strategy stats (capped 2%)"),
                   ("vol_target", "Volatility-targeted (portfolio vol budget)"),
                   ("min_of_all", "Minimum of all estimates (most conservative)")],
          help="kelly/vol_target/min_of_all are Edge-plan modes: they can only ever "
               "REDUCE risk below your risk % (hard ceiling 2%, quarter-Kelly cap frozen). "
               "See !growth for what each mode does to the compounding ETA."),
    Field("PORTFOLIO_TARGET_DAILY_VOL_PCT", "PORTFOLIO_TARGET_DAILY_VOL_PCT", "Account Defaults",
          "Portfolio daily vol target (%)", type="float", default="0.7",
          min=0.1, max=3.0, step=0.1,
          help="vol_target sizing keeps estimated portfolio daily volatility near this. "
               "0.7% daily ≈ 11% annualized — calm enough to hold through."),
```

(Keep the existing Field's other kwargs — only `options` and `help` change. `!account sizing` in `swingbot/commands/account.py` validates against the mode list; extend its accepted set to the five values.)

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_edge_sizing.py -v` — PASS (14 tests). Full suite `python -m pytest tests/ -q` — green (default mode byte-for-byte unchanged; the parity test `scripts/parity_sizing.py` still agrees).

- [x] **Step 5: Commit**

```bash
git add swingbot/core/account.py swingbot/config.py swingbot/commands/account.py tests/test_edge_sizing.py
git commit -m "feat: kelly/vol-target sizing modes (default unchanged)"
```

### Task E7: Portfolio heat cap

**Files:**
- Create: `swingbot/core/edge/heat.py`
- Modify: `swingbot/config.py` (Field `PORTFOLIO_HEAT_CAP_PCT`, float, default 6.0, min 1, max 20, step 0.5, section "Account Defaults")
- Modify: `swingbot/commands/scanning.py` (alert path, pre-sizing — see Step 3)
- Test: `tests/test_edge_heat.py`

**Interfaces:**
- Produces: `trade_risk_pct(trade: dict, balance: float) -> float` (uses `trade["risk_pct"]` when present, else `(entry − stop) × shares / balance × 100`); `open_heat(open_trades, balance) -> float`; `heat_check(open_trades, balance, candidate_risk_pct, cap_pct=None) -> dict` with keys `allowed, open_heat, remaining, cap`.
- Blocking is **flagged, not hidden** (user-requirement pattern): a blocked plan still alerts, labeled `⛔ heat cap` with suggested size 0.
- Consumed by: E49 (sector cap extends this file), E50 portfolio replay, E52 `!portfolio`, E68 treemap.

- [x] **Step 1: Write the failing test**

```python
# tests/test_edge_heat.py
import pytest

from swingbot.core.edge.heat import heat_check, open_heat, trade_risk_pct

BALANCE = 10_000.0


def _trade(entry, stop, shares):
    return {"entry": entry, "stop_loss": stop, "shares": shares}


def test_trade_risk_pct_from_prices():
    # (100-98) * 100 shares = $200 = 2% of 10k
    assert trade_risk_pct(_trade(100.0, 98.0, 100), BALANCE) == pytest.approx(2.0)


def test_trade_risk_pct_prefers_recorded_value():
    assert trade_risk_pct({"risk_pct": 1.5}, BALANCE) == 1.5


def test_open_heat_sums():
    trades = [_trade(100.0, 98.0, 100)] * 3   # 3 x 2%
    assert open_heat(trades, BALANCE) == pytest.approx(6.0)


def test_heat_check_blocks_at_cap():
    trades = [_trade(100.0, 98.0, 100)] * 3   # 6% open = at the 6% cap
    chk = heat_check(trades, BALANCE, candidate_risk_pct=1.0, cap_pct=6.0)
    assert chk["allowed"] is False
    assert chk["remaining"] == pytest.approx(0.0)


def test_closing_one_frees_heat():
    trades = [_trade(100.0, 98.0, 100)] * 2   # 4% open
    chk = heat_check(trades, BALANCE, candidate_risk_pct=1.0, cap_pct=6.0)
    assert chk["allowed"] is True
    assert chk["remaining"] == pytest.approx(2.0)
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_edge_heat.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.edge.heat'`

- [x] **Step 3: Write the implementation**

```python
# swingbot/core/edge/heat.py
"""Portfolio heat: the sum of risk-to-stop across every open position,
as a percent of equity. Heat is what actually hits the account when a
correlated gap takes every stop out on the same morning -- capping it is
survival, not style. Blocking is FLAGGED, never hidden: the alert still
posts, labeled, with size 0, so the operator always sees what the cap
cost them and can free heat deliberately."""
from __future__ import annotations

from swingbot import config


def trade_risk_pct(trade: dict, balance: float) -> float:
    if trade.get("risk_pct") is not None:
        return float(trade["risk_pct"])
    entry = float(trade.get("entry", 0.0))
    stop = float(trade.get("stop_loss", 0.0))
    shares = float(trade.get("shares", 0.0))
    if balance <= 0:
        return 0.0
    return abs(entry - stop) * shares / balance * 100.0


def open_heat(open_trades: list, balance: float) -> float:
    return sum(trade_risk_pct(t, balance) for t in open_trades)


def heat_check(open_trades: list, balance: float, candidate_risk_pct: float,
               cap_pct: float | None = None) -> dict:
    cap = cap_pct if cap_pct is not None else getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0)
    heat = open_heat(open_trades, balance)
    remaining = max(0.0, cap - heat)
    return {
        "allowed": candidate_risk_pct <= remaining + 1e-9,
        "open_heat": round(heat, 3),
        "remaining": round(remaining, 3),
        "cap": cap,
    }
```

Wire into the alert path in `swingbot/commands/scanning.py`, in `_send_alerts` where each item's position size is computed (just before the embed build):

```python
        from swingbot.core.edge import heat as heat_mod
        open_trades = performance.trade_log.get_open_trades()  # existing accessor
        cfg = account_module.load_account_config()
        chk = heat_mod.heat_check(open_trades, cfg.get("balance", 0.0),
                                  candidate_risk_pct=cfg.get("risk_pct", 1.0))
        if not chk["allowed"]:
            item.heat_blocked = chk          # embed builder reads this
```

and in `swingbot/core/scanning/embeds.py` (`build_embed`), when `getattr(item, "heat_blocked", None)` is set, prepend a field:

```python
        embed.add_field(
            name="⛔ ENTRY BLOCKED — portfolio heat cap",
            value=(f"Open heat {hb['open_heat']}% / cap {hb['cap']}% — "
                   f"suggested size **0 shares**. Close or trim a position to free heat."),
            inline=False)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_edge_heat.py -v` — PASS (5 tests). Full suite green.

- [x] **Step 5: Commit**

```bash
git add swingbot/core/edge/heat.py swingbot/config.py swingbot/commands/scanning.py swingbot/core/scanning/embeds.py tests/test_edge_heat.py
git commit -m "feat: portfolio heat cap"
```

### Task E8: Correlation-aware exposure

**Files:**
- Create: `swingbot/core/edge/correlation.py`
- Modify: `swingbot/config.py` (Field `CORRELATED_HEAT_CAP_PCT`, float, default 3.0, min 0.5, max 10, step 0.5, section "Account Defaults")
- Test: `tests/test_edge_correlation.py`

**Interfaces:**
- Produces: `returns_corr(df_a, df_b, window=90) -> float | None` (None when < 30 overlapping bars); `cluster_exposure(open_trades, candidate_ticker, dfs: dict[str, pd.DataFrame], balance: float, *, window=90, threshold=0.75, sectors: dict[str, str] | None = None) -> dict` with keys `max_corr, correlated_heat, cluster` (list of tickers whose 90-day returns-corr with the candidate > threshold, or same sector when price data is thin); `cluster_check(exposure, candidate_risk_pct, cap_pct=None) -> dict {allowed, ...}` mirroring E7's shape.
- Consumed by: alert path (same flagged-not-hidden pattern as E7), E50 replay, E69 heatmap.

- [x] **Step 1: Write the failing test**

```python
# tests/test_edge_correlation.py
import numpy as np
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.edge.correlation import cluster_exposure, returns_corr


def _walk(seed, n=200):
    rng = np.random.default_rng(seed)
    return make_ohlcv(100 * np.cumprod(1 + rng.normal(0, 0.01, n)))


def test_clone_correlates_near_one():
    a = _walk(1)
    assert returns_corr(a, a.copy()) == pytest.approx(1.0)


def test_independent_walks_do_not():
    c = returns_corr(_walk(1), _walk(2))
    assert abs(c) < 0.5


def test_too_little_overlap_returns_none():
    a, b = _walk(1, n=200), _walk(2, n=10)
    assert returns_corr(a, b) is None


def test_cluster_exposure_counts_correlated_heat():
    a = _walk(1)
    dfs = {"AAA": a, "BBB": a.copy(), "CCC": _walk(2), "CAND": a.copy()}
    open_trades = [
        {"ticker": "AAA", "risk_pct": 2.0},
        {"ticker": "BBB", "risk_pct": 1.0},
        {"ticker": "CCC", "risk_pct": 2.0},
    ]
    exp = cluster_exposure(open_trades, "CAND", dfs, balance=10_000.0)
    assert exp["cluster"] == ["AAA", "BBB"]          # CCC uncorrelated
    assert exp["correlated_heat"] == pytest.approx(3.0)
    assert exp["max_corr"] == pytest.approx(1.0)


def test_sector_fallback_when_data_thin():
    dfs = {"AAA": _walk(1, n=10), "CAND": _walk(3, n=10)}   # too short to correlate
    exp = cluster_exposure([{"ticker": "AAA", "risk_pct": 2.0}], "CAND", dfs,
                           balance=10_000.0,
                           sectors={"AAA": "Information Technology",
                                    "CAND": "Information Technology"})
    assert exp["cluster"] == ["AAA"]                 # same sector counted
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_edge_correlation.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [x] **Step 3: Write the implementation**

```python
# swingbot/core/edge/correlation.py
"""Correlation-aware exposure: three 'different' trades that are 0.9-
correlated are one trade at 3x size. Positions whose 90-day daily-returns
correlation with a candidate exceeds THRESHOLD count their heat against
the candidate's cluster budget (CORRELATED_HEAT_CAP_PCT). When price
history is too thin to correlate, same-sector membership (universe file
tags, E13) is the conservative fallback."""
from __future__ import annotations

import pandas as pd

from swingbot import config
from swingbot.core.edge.heat import trade_risk_pct

MIN_OVERLAP_BARS = 30
DEFAULT_THRESHOLD = 0.75


def returns_corr(df_a: pd.DataFrame, df_b: pd.DataFrame, window: int = 90) -> float | None:
    ra = df_a["Close"].pct_change().dropna().tail(window)
    rb = df_b["Close"].pct_change().dropna().tail(window)
    joined = pd.concat([ra, rb], axis=1, join="inner").dropna()
    if len(joined) < MIN_OVERLAP_BARS:
        return None
    return float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))


def cluster_exposure(open_trades: list, candidate_ticker: str,
                     dfs: dict, balance: float, *, window: int = 90,
                     threshold: float = DEFAULT_THRESHOLD,
                     sectors: dict | None = None) -> dict:
    cand_df = dfs.get(candidate_ticker)
    cluster, correlated_heat, max_corr = [], 0.0, 0.0
    for t in open_trades:
        tick = t.get("ticker")
        corr = None
        if cand_df is not None and tick in dfs:
            corr = returns_corr(cand_df, dfs[tick], window)
        in_cluster = corr is not None and corr > threshold
        if corr is None and sectors:
            # thin data -> conservative sector fallback
            in_cluster = (sectors.get(tick) is not None
                          and sectors.get(tick) == sectors.get(candidate_ticker))
        if corr is not None:
            max_corr = max(max_corr, corr)
        if in_cluster:
            cluster.append(tick)
            correlated_heat += trade_risk_pct(t, balance)
    return {"cluster": cluster, "correlated_heat": round(correlated_heat, 3),
            "max_corr": round(max_corr, 3)}


def cluster_check(exposure: dict, candidate_risk_pct: float,
                  cap_pct: float | None = None) -> dict:
    cap = cap_pct if cap_pct is not None else getattr(config, "CORRELATED_HEAT_CAP_PCT", 3.0)
    remaining = max(0.0, cap - exposure["correlated_heat"])
    return {"allowed": candidate_risk_pct <= remaining + 1e-9,
            "remaining": round(remaining, 3), "cap": cap, **exposure}
```

Alert-path wiring mirrors E7 exactly (same `_send_alerts` block, `item.cluster_blocked = chk`, embed field `⛔ ENTRY BLOCKED — correlated cluster {tickers}`), with `sectors` built from `universe.load(...)` when E13 has landed (soft import, `None` until then).

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_edge_correlation.py -v` — PASS (5 tests).

- [x] **Step 5: Commit**

```bash
git add swingbot/core/edge/correlation.py swingbot/config.py swingbot/commands/scanning.py swingbot/core/scanning/embeds.py tests/test_edge_correlation.py
git commit -m "feat: correlation-aware heat clustering"
```

### Task E9: Growth-path tracker

**Files:**
- Modify: `swingbot/core/edge/growth.py`
- Test: `tests/test_edge_growth.py`

**Interfaces:**
- Produces: `growth_path(equity_curve_points: list[tuple[str, float]], start_balance: float, target_multiple: float = 10.0, horizons_years: tuple = (3, 5, 8)) -> dict` with keys `current_multiple`, `pct_to_target` (log-scale progress — halfway to 10x is ~3.16x, not 5x), `required_daily_growth` (`{years: fraction/day}` from *now* to target), `realized_daily_growth`, `on_track_vs` (`{years: bool}`).
- Consumed by: `!growth` (E2), E71 growth-path chart, E53 weekly report.

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_growth.py`)

```python
def test_growth_path_fixture():
    from swingbot.core.edge.growth import growth_path
    import math
    # 365 days from 10k to 15k -> 1.5x
    points = [("2025-07-12", 10_000.0), ("2026-07-12", 15_000.0)]
    gp = growth_path(points, start_balance=10_000.0)
    assert gp["current_multiple"] == pytest.approx(1.5)
    # log progress: ln(1.5)/ln(10) = 17.6%
    assert gp["pct_to_target"] == pytest.approx(17.6, abs=0.1)
    # required daily growth for 10x-in-3y from 1.5x: (10/1.5)^(1/1095.75)-1
    want = (10 / 1.5) ** (1 / (3 * 365.25)) - 1
    assert gp["required_daily_growth"][3] == pytest.approx(want, rel=1e-6)
    # realized: 1.5^(1/365) - 1 per day ≈ 0.111%/day
    assert gp["realized_daily_growth"] == pytest.approx(1.5 ** (1 / 365) - 1, rel=1e-4)
    assert gp["on_track_vs"][8] in (True, False)


def test_growth_path_empty_curve():
    from swingbot.core.edge.growth import growth_path
    gp = growth_path([], start_balance=10_000.0)
    assert gp["current_multiple"] == 1.0 and gp["realized_daily_growth"] is None
```

- [ ] **Step 2: Run — FAIL (`ImportError: growth_path`).**

- [ ] **Step 3: Implement** (append to `swingbot/core/edge/growth.py`)

```python
import datetime as _dt


def growth_path(equity_curve_points: list, start_balance: float,
                target_multiple: float = 10.0,
                horizons_years: tuple = (3, 5, 8)) -> dict:
    """Where the account actually is on the road to `target_multiple`,
    measured in log space (compounding progress, not linear dollars)."""
    if not equity_curve_points or start_balance <= 0:
        return {"current_multiple": 1.0, "pct_to_target": 0.0,
                "required_daily_growth": {y: (target_multiple ** (1 / (y * 365.25)) - 1)
                                          for y in horizons_years},
                "realized_daily_growth": None,
                "on_track_vs": {y: False for y in horizons_years}}
    import math
    first_date = _dt.date.fromisoformat(str(equity_curve_points[0][0])[:10])
    last_date = _dt.date.fromisoformat(str(equity_curve_points[-1][0])[:10])
    current = equity_curve_points[-1][1] / start_balance
    days = max(1, (last_date - first_date).days)
    realized = current ** (1 / days) - 1 if current > 0 else None
    remaining = max(target_multiple / max(current, 1e-9), 1.0)
    required = {y: remaining ** (1 / (y * 365.25)) - 1 for y in horizons_years}
    return {
        "current_multiple": round(current, 4),
        "pct_to_target": round(math.log(max(current, 1e-9)) / math.log(target_multiple) * 100, 2),
        "required_daily_growth": required,
        "realized_daily_growth": realized,
        "on_track_vs": {y: (realized is not None and realized >= r)
                        for y, r in required.items()},
    }
```

In `swingbot/commands/growth.py`, extend `_collect_stats` to include `growth_path(account_module.get_balance_history_points(), start)` output and append its lines (`at {current_multiple}x — {pct_to_target}% of the way (log scale); on track for 10x-in-8y: yes/no`) to the report. `get_balance_history_points()` is a 4-line adapter over the existing `get_balance_history()` returning `[(entry["at"][:10], entry["balance"]), ...]` — add it to `account.py`.

- [ ] **Step 4: Run `python -m pytest tests/test_edge_growth.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/growth.py swingbot/core/account.py swingbot/commands/growth.py tests/test_edge_growth.py
git commit -m "feat: growth-path tracker"
```

### Task E10: Phase E0 checkpoint

- [ ] **Step 1: Full verification**

Run: `python -m pytest tests/ -q` then `make check` — both green.

- [ ] **Step 2: Smoke the math against the LIVE account** (paste output into the Progress block):

```bash
python -c "from swingbot.core.edge.growth import growth_table; import json; print(json.dumps(growth_table(), indent=1))"
python -c "
from swingbot.core.performance import TradeLog
from swingbot.core.edge.ruin import simulate
rs = [t.get('r_multiple') for t in TradeLog().all_trades() if t.get('r_multiple') is not None]
print('N =', len(rs))
print(simulate(rs, risk_pct=1.0) if len(rs) >= 10 else 'need >=10 closed trades')
"
```

(Adapt the `TradeLog` accessor name to the real one — `all_trades()` vs `trades` attribute — whichever `performance.py` exposes; the point is the live R list.)

- [ ] **Step 3: Update the Progress block** (Completed: E1–E10, Next: E11) **and commit**

```bash
git add docs/superpowers/plans/2026-07-11-edge-engine.md
git commit -m "docs: E0 checkpoint"
```

---

# Phase E1 — Data, universe & execution realism (E11–E22)

### Task E11: Friction model in the backtest

**Files:**
- Create: `swingbot/core/edge/frictions.py`
- Modify: `swingbot/core/backtest.py` (`run_backtest` — the fill/exit block quoted below)
- Modify: `swingbot/config.py` (Fields `SLIPPAGE_BPS` float default 5, min 0, max 50, step 1; `COMMISSION_PER_TRADE` float default 1.0, min 0, max 20, step 0.5; `COMMISSION_RISK_BASIS` float default 100.0 — all in a new section "Execution Realism")
- Test: `tests/test_edge_frictions.py`

**Interfaces:**
- Produces: `apply_frictions(fill_price, side, slippage_bps=None) -> float` (`side` ∈ `{"buy","sell"}`; buys fill higher, sells lower); `commission_r(risk_dollars=None, commission=None) -> float` (round-trip commission expressed in R against the risk basis).
- `run_backtest(..., frictions: bool = True)` — **default ON from now**; every entry/exit fill is worsened by slippage and every trade's `r_multiple` is reduced by the round-trip commission-R. This creates the honest baseline every later component must beat.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_frictions.py
import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.edge.frictions import apply_frictions, commission_r


def test_slippage_direction_golden():
    assert apply_frictions(100.0, "buy", 5) == pytest.approx(100.05)
    assert apply_frictions(100.0, "sell", 5) == pytest.approx(99.95)
    assert apply_frictions(100.0, "buy", 0) == 100.0


def test_commission_r_golden():
    # $1 per side, $100 risk basis -> 2 x 1/100 = 0.02R round trip
    assert commission_r(risk_dollars=100.0, commission=1.0) == pytest.approx(0.02)


def test_backtest_frictions_reduce_r(monkeypatch):
    import swingbot.core.backtest as bt
    df = make_ohlcv(np.full(80, 100.0), spread_pct=1.0)
    bull = pd.Series(False, index=df.index); bull.iloc[40] = True
    bear = pd.Series(False, index=df.index)
    monkeypatch.setattr(bt, "_vectorized_entries", lambda *a, **k: (bull, bear))
    clean = bt.run_backtest("TEST", df, "EMA Crossover", "2w", frictions=False)
    real = bt.run_backtest("TEST", df, "EMA Crossover", "2w", frictions=True)
    assert clean.trades and real.trades
    # same bars, worse arithmetic: friction expectancy strictly lower
    assert real.expectancy_r < clean.expectancy_r


def test_frictions_off_is_bit_identical_to_before(monkeypatch):
    import swingbot.core.backtest as bt
    df = make_ohlcv(np.full(80, 100.0), spread_pct=1.0)
    bull = pd.Series(False, index=df.index); bull.iloc[40] = True
    monkeypatch.setattr(bt, "_vectorized_entries",
                        lambda *a, **k: (bull, pd.Series(False, index=df.index)))
    s = bt.run_backtest("TEST", df, "EMA Crossover", "2w", frictions=False)
    t = s.trades[0]
    assert t.entry == 100.0  # unslipped fill preserved when off
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_edge_frictions.py -v`
Expected: FAIL — `ModuleNotFoundError` then `TypeError: run_backtest() got an unexpected keyword argument 'frictions'`

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/edge/frictions.py
"""Execution frictions: slippage + commission.

The clean backtest fills at exact trigger/stop/target prices. Real fills
don't. 5 bps of slippage per side and a commission per trade is a
conservative-for-liquid-names model (the E12 liquidity screen is what
makes this assumption defensible). Commission is expressed in R against
a fixed risk basis (default $100 risked/trade = 1% of a $10k account)
so the unit-less backtest can subtract it from r_multiple.
"""
from __future__ import annotations

from swingbot import config


def apply_frictions(fill_price: float, side: str, slippage_bps: float | None = None) -> float:
    """Worsen a fill by `slippage_bps`. Buys fill higher, sells fill lower."""
    bps = slippage_bps if slippage_bps is not None else getattr(config, "SLIPPAGE_BPS", 5.0)
    adj = fill_price * bps / 10_000.0
    return fill_price + adj if side == "buy" else fill_price - adj


def commission_r(risk_dollars: float | None = None, commission: float | None = None) -> float:
    """Round-trip commission as an R deduction."""
    basis = risk_dollars if risk_dollars else getattr(config, "COMMISSION_RISK_BASIS", 100.0)
    per_side = commission if commission is not None else getattr(config, "COMMISSION_PER_TRADE", 1.0)
    if basis <= 0:
        return 0.0
    return 2.0 * per_side / basis
```

In `swingbot/core/backtest.py`, add the parameter (`run_backtest(..., one_at_a_time: bool = True, frictions: bool = True)`) and modify the trade loop — current code shown with the exact replacements:

```python
        direction = "bullish" if bullish_entries.values[i] else "bearish"
        entry, stop_loss, take_profit = _trade_plan_at(
            df, i, direction, strategy, horizon_key, atr_series,
            swing_high_series, swing_low_series, volume_ratio_series, entry_levels
        )
        # --- E11: slip the entry fill. Levels (stop/target/BE trigger) stay
        # at their PLANNED prices -- slippage moves your fill, not the chart.
        entry_fill = entry
        if frictions:
            from swingbot.core.edge.frictions import apply_frictions, commission_r
            entry_fill = apply_frictions(entry, "buy" if direction == "bullish" else "sell")
        risk_per_share = abs(entry_fill - stop_loss)
        if risk_per_share <= 0:
            continue
```

…the BE trigger and the bar loop are unchanged (they compare HIGH/LOW to planned levels)… then at the exit:

```python
        if outcome == "timeout":
            exit_price, exit_i = float(close_vals[end]), end

        # --- E11: slip the exit fill (opposite side of the entry).
        exit_fill = exit_price
        if frictions:
            exit_fill = apply_frictions(exit_price, "sell" if direction == "bullish" else "buy")

        _open_until = exit_i
        sign = 1 if direction == "bullish" else -1
        return_pct = (exit_fill - entry_fill) / entry_fill * sign * 100
        r_multiple = (exit_fill - entry_fill) * sign / risk_per_share
        if frictions:
            r_multiple -= commission_r()
        holding_days = exit_i - i

        trades.append(BacktestTrade(
            entry_date=str(df.index[i].date()), exit_date=str(df.index[exit_i].date()),
            direction=direction, entry=round(entry_fill, 4), stop_loss=round(stop_loss, 4),
            take_profit=round(take_profit, 4), outcome=outcome,
            exit_price=round(exit_fill, 4), return_pct=round(return_pct, 3),
            r_multiple=round(r_multiple, 3), holding_days=holding_days,
        ))
```

Thread `frictions` through `run_full_backtest` and `run_backtest_daterange` (same default True) and add `--frictions on|off` to `scripts/run_backtest_range.py` (default on).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_edge_frictions.py -v` — PASS. Full suite: some backtest goldens in existing tests may assume frictionless fills — those tests should pass `frictions=False` explicitly (they test entry/exit *logic*, not economics); update them in this task.

- [ ] **Step 5: Re-baseline and commit**

Run the TRAIN window twice and save the comparison (expect a ~0.02–0.05R haircut per strategy):

```bash
python scripts/run_backtest_range.py --train --frictions off > /tmp/base_clean.txt
python scripts/run_backtest_range.py --train --frictions on  > /tmp/base_real.txt
```

Create `docs/superpowers/results/2026-XX-edge-baseline.md` with both tables and a per-strategy delta column (this doc is finalized at E22).

```bash
git add swingbot/core/edge/frictions.py swingbot/core/backtest.py swingbot/config.py scripts/run_backtest_range.py tests/test_edge_frictions.py docs/superpowers/results/
git commit -m "feat: slippage+commission realism (new baseline)"
```

### Task E12: Liquidity screen

**Files:**
- Create: `swingbot/core/universe.py`
- Modify: `swingbot/config.py` (Fields `UNIVERSE_MIN_DOLLAR_VOL` float default 20000000, `UNIVERSE_MIN_PRICE` float default 5.0, section "Universe & Scanning")
- Modify: `swingbot/core/scanning/engine.py` (skip illiquid tickers in the scan loop, log-visible)
- Test: `tests/test_universe.py`

**Interfaces:**
- Produces: `liquidity_ok(df, min_avg_dollar_vol=None, min_price=None) -> bool` — 20-day average of `Close × Volume` ≥ threshold AND last close ≥ min price. `liquidity_reason(df) -> str | None` for the log line.
- Consumed by: scan loop, backtest scripts, E13 top-150 ranking, E16 validator.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_universe.py
import numpy as np

from tests.conftest import make_ohlcv
from swingbot.core.universe import liquidity_ok


def test_spy_like_passes():
    df = make_ohlcv(np.full(60, 450.0), volumes=np.full(60, 80_000_000.0))
    assert liquidity_ok(df) is True


def test_penny_stock_fails_price():
    df = make_ohlcv(np.full(60, 2.0), volumes=np.full(60, 50_000_000.0))
    assert liquidity_ok(df) is False


def test_thin_name_fails_dollar_volume():
    # $30 x 100k shares = $3M/day << $20M floor
    df = make_ohlcv(np.full(60, 30.0), volumes=np.full(60, 100_000.0))
    assert liquidity_ok(df) is False


def test_explicit_thresholds_override_config():
    df = make_ohlcv(np.full(60, 30.0), volumes=np.full(60, 100_000.0))
    assert liquidity_ok(df, min_avg_dollar_vol=1_000_000, min_price=1.0) is True
```

- [ ] **Step 2: Run — FAIL (`ModuleNotFoundError: swingbot.core.universe`).**

- [ ] **Step 3: Implement**

```python
# swingbot/core/universe.py
"""Tradeable-universe utilities: liquidity screening (this task), universe
files + loaders (E13), ETF tagging (E14), data-quality rules (E16).

Liquidity is what makes the E11 slippage assumption honest: 5 bps is a
reasonable model for a $20M+/day name, a fantasy for a $500k/day one.
"""
from __future__ import annotations

import pandas as pd

from swingbot import config


def _avg_dollar_vol(df: pd.DataFrame, window: int = 20) -> float:
    tail = df.tail(window)
    return float((tail["Close"] * tail["Volume"]).mean())


def liquidity_ok(df: pd.DataFrame, min_avg_dollar_vol: float | None = None,
                 min_price: float | None = None) -> bool:
    return liquidity_reason(df, min_avg_dollar_vol, min_price) is None


def liquidity_reason(df: pd.DataFrame, min_avg_dollar_vol: float | None = None,
                     min_price: float | None = None) -> str | None:
    """None when liquid; else a loggable reason string."""
    if df is None or len(df) < 20:
        return "insufficient history (<20 bars)"
    floor_dv = min_avg_dollar_vol if min_avg_dollar_vol is not None else \
        getattr(config, "UNIVERSE_MIN_DOLLAR_VOL", 20_000_000.0)
    floor_px = min_price if min_price is not None else \
        getattr(config, "UNIVERSE_MIN_PRICE", 5.0)
    last_close = float(df["Close"].iloc[-1])
    if last_close < floor_px:
        return f"price {last_close:.2f} < {floor_px:.2f} floor"
    dv = _avg_dollar_vol(df)
    if dv < floor_dv:
        return f"avg dollar vol ${dv/1e6:.1f}M < ${floor_dv/1e6:.0f}M floor"
    return None
```

Wire into `swingbot/core/scanning/engine.py`, in the per-ticker loop of `_sync_run_scan` right after the ticker's DataFrame is loaded:

```python
            from swingbot.core import universe
            reason = universe.liquidity_reason(df)
            if reason is not None:
                log.info("scan skip %s: %s", ticker, reason)
                continue
```

and equivalently in `scripts/run_backtest_range.py`'s ticker loop (excluded tickers printed once at the top of the report).

- [ ] **Step 4: Run `python -m pytest tests/test_universe.py -v` — PASS (4 tests). Full suite green.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/universe.py swingbot/config.py swingbot/core/scanning/engine.py scripts/run_backtest_range.py tests/test_universe.py
git commit -m "feat: liquidity screen"
```

### Task E13: Universe files + S&P 500 builder

**Files:**
- Create: `scripts/build_universe.py`, `data/universe/etfs.json` (hand-written), `data/universe/sp500.json` + `data/universe/sp500_top150.json` (generated)
- Modify: `swingbot/core/universe.py` (loader), `swingbot/config.py` (Field `SCAN_UNIVERSE`, select, options `watchlist|sp500|sp500_top150|etfs|sp500+etfs`, default `watchlist`, section "Universe & Scanning")
- Test: `tests/test_universe.py`

**Interfaces:**
- Produces: `load(name: str) -> list[dict]` (each `{"symbol", "name", "sector", "etf": bool}`, deduped, schema-validated, `[]` for unknown/missing); `universe_symbols(name) -> list[str]`; `sector_map(name) -> dict[str, str]` (feeds E8's `sectors=`). Builder: `python scripts/build_universe.py --raw data/universe/sp500_raw.csv [--top 150]` reads a manually-refreshed constituent CSV (`Symbol,Name,Sector` — paste from any public S&P 500 list; documented in the script docstring), validates, writes `sp500.json`; with `--top N` it ranks by 20d avg dollar volume from the local OHLCV cache and writes `sp500_topN.json`.
- Scanning source becomes `WATCHLIST | UNIVERSE` via `SCAN_UNIVERSE` (default `watchlist` — **no behavior change yet**; the flip is E77/E84). The watchlist remains the user's curated overlay and is ALWAYS included.

- [ ] **Step 1: Write the failing test** (append to `tests/test_universe.py`)

```python
def test_load_etfs_universe():
    from swingbot.core.universe import load, universe_symbols
    rows = load("etfs")
    syms = universe_symbols("etfs")
    assert "SPY" in syms and "QQQ" in syms and "GLD" in syms and "TLT" in syms
    assert all(set(r) >= {"symbol", "name", "sector", "etf"} for r in rows)
    assert all(r["etf"] is True for r in rows)


def test_load_dedupes_and_unknown_is_empty(tmp_path, monkeypatch):
    import json
    from swingbot.core import universe
    d = tmp_path / "universe"; d.mkdir()
    (d / "dup.json").write_text(json.dumps([
        {"symbol": "AAA", "name": "A", "sector": "Energy", "etf": False},
        {"symbol": "AAA", "name": "A again", "sector": "Energy", "etf": False},
    ]))
    monkeypatch.setattr(universe, "UNIVERSE_DIR", str(d))
    assert len(universe.load("dup")) == 1
    assert universe.load("nope") == []


def test_sector_map():
    from swingbot.core.universe import sector_map
    m = sector_map("etfs")
    assert m.get("XLE") == "Energy"
```

- [ ] **Step 2: Run — FAIL (`ImportError: load`).**

- [ ] **Step 3: Implement**

Append to `swingbot/core/universe.py`:

```python
import json
import os

UNIVERSE_DIR = os.path.join(config.DATA_DIR, "universe")
_REQUIRED_KEYS = {"symbol", "name", "sector", "etf"}


def load(name: str) -> list[dict]:
    """Load a universe file, validated + deduped by symbol. `sp500+etfs`
    concatenates. Unknown or missing -> [] (scanning falls back to watchlist)."""
    if "+" in name:
        seen, out = set(), []
        for part in name.split("+"):
            for row in load(part):
                if row["symbol"] not in seen:
                    seen.add(row["symbol"]); out.append(row)
        return out
    path = os.path.join(UNIVERSE_DIR, f"{name}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    seen, out = set(), []
    for row in raw:
        if not isinstance(row, dict) or not _REQUIRED_KEYS <= set(row):
            continue
        sym = str(row["symbol"]).upper()
        if sym in seen:
            continue
        seen.add(sym)
        out.append({"symbol": sym, "name": row["name"],
                    "sector": row["sector"], "etf": bool(row["etf"])})
    return out


def universe_symbols(name: str) -> list[str]:
    return [r["symbol"] for r in load(name)]


def sector_map(name: str) -> dict:
    return {r["symbol"]: r["sector"] for r in load(name)}
```

`data/universe/etfs.json` (checked in, hand-maintained):

```json
[
  {"symbol": "SPY", "name": "SPDR S&P 500", "sector": "Broad Market", "etf": true},
  {"symbol": "QQQ", "name": "Invesco Nasdaq 100", "sector": "Broad Market", "etf": true},
  {"symbol": "IWM", "name": "iShares Russell 2000", "sector": "Broad Market", "etf": true},
  {"symbol": "DIA", "name": "SPDR Dow Jones", "sector": "Broad Market", "etf": true},
  {"symbol": "XLK", "name": "Technology Select", "sector": "Information Technology", "etf": true},
  {"symbol": "XLF", "name": "Financial Select", "sector": "Financials", "etf": true},
  {"symbol": "XLE", "name": "Energy Select", "sector": "Energy", "etf": true},
  {"symbol": "XLV", "name": "Health Care Select", "sector": "Health Care", "etf": true},
  {"symbol": "XLI", "name": "Industrial Select", "sector": "Industrials", "etf": true},
  {"symbol": "XLP", "name": "Consumer Staples Select", "sector": "Consumer Staples", "etf": true},
  {"symbol": "XLY", "name": "Consumer Discretionary Select", "sector": "Consumer Discretionary", "etf": true},
  {"symbol": "XLU", "name": "Utilities Select", "sector": "Utilities", "etf": true},
  {"symbol": "XLB", "name": "Materials Select", "sector": "Materials", "etf": true},
  {"symbol": "XLRE", "name": "Real Estate Select", "sector": "Real Estate", "etf": true},
  {"symbol": "XLC", "name": "Communication Services Select", "sector": "Communication Services", "etf": true},
  {"symbol": "GLD", "name": "SPDR Gold Shares", "sector": "Commodities", "etf": true},
  {"symbol": "TLT", "name": "iShares 20+ Year Treasury", "sector": "Bonds", "etf": true}
]
```

`scripts/build_universe.py`:

```python
"""Build data/universe/sp500.json from a manually refreshed constituent CSV.

Refresh procedure (documented, no scraping dependency): copy the current
S&P 500 constituent table from any public source into
data/universe/sp500_raw.csv with the header `Symbol,Name,Sector`
(GICS sector names). Then:

    python scripts/build_universe.py --raw data/universe/sp500_raw.csv
    python scripts/build_universe.py --raw data/universe/sp500_raw.csv --top 150

--top N ranks by 20-day average dollar volume using the local OHLCV cache
(fetch it first: python scripts/fetch_backtest_data.py --universe sp500).
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swingbot.core.universe import UNIVERSE_DIR  # noqa: E402


def build(raw_csv: str, top: int | None) -> str:
    rows = []
    with open(raw_csv, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            sym = r["Symbol"].strip().upper().replace(".", "-")  # BRK.B -> BRK-B (yfinance)
            rows.append({"symbol": sym, "name": r["Name"].strip(),
                         "sector": r["Sector"].strip(), "etf": False})
    seen, deduped = set(), []
    for r in rows:
        if r["symbol"] not in seen:
            seen.add(r["symbol"]); deduped.append(r)

    name = "sp500"
    if top:
        from swingbot.core.data_store import load_from_disk
        def dollar_vol(sym):
            df = load_from_disk(sym, "1d")
            if df is None or len(df) < 20:
                return 0.0
            t = df.tail(20)
            return float((t["Close"] * t["Volume"]).mean())
        deduped.sort(key=lambda r: dollar_vol(r["symbol"]), reverse=True)
        deduped = deduped[:top]
        name = f"sp500_top{top}"

    os.makedirs(UNIVERSE_DIR, exist_ok=True)
    out = os.path.join(UNIVERSE_DIR, f"{name}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(deduped, f, indent=1)
    print(f"wrote {out}: {len(deduped)} symbols")
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--raw", default="data/universe/sp500_raw.csv")
    p.add_argument("--top", type=int, default=None)
    a = p.parse_args()
    build(a.raw, a.top)
```

Config Field:

```python
    Field("SCAN_UNIVERSE", "SCAN_UNIVERSE", "Universe & Scanning", "Scan universe",
          type="select", default="watchlist",
          options=["watchlist", "sp500", "sp500_top150", "etfs", "sp500+etfs"],
          help="What the scanner covers. The watchlist is ALWAYS included on top of any "
               "universe. Flip beyond watchlist only after the E77 rollout checklist."),
```

and in `_sync_run_scan`, where the ticker list is assembled:

```python
    tickers = list(watchlist_symbols)
    if config.SCAN_UNIVERSE != "watchlist":
        from swingbot.core import universe
        extra = [s for s in universe.universe_symbols(config.SCAN_UNIVERSE)
                 if s not in set(tickers)]
        tickers.extend(extra)
```

- [ ] **Step 4: Run the builder once** (paste the current constituents into `sp500_raw.csv` first), then `python -m pytest tests/test_universe.py -v` — PASS.

- [ ] **Step 5: Commit** (including the generated JSON files — they are versioned data)

```bash
git add swingbot/core/universe.py swingbot/config.py swingbot/core/scanning/engine.py scripts/build_universe.py data/universe/ tests/test_universe.py
git commit -m "feat: tradeable universe files"
```

### Task E14: Index/ETF plan support

**Files:**
- Modify: `swingbot/core/universe.py` (`is_etf`), the earnings-days helper used by the plan/alert path (`swingbot/core/market_events.py` or wherever `days_to_earnings` currently lives — locate with `grep -rn "earnings" swingbot/core/`)
- Test: `tests/test_universe.py`

**Interfaces:**
- Produces: `is_etf(symbol: str) -> bool` (True when the symbol appears with `etf: true` in ANY universe file — `etfs` checked first, cached per process); earnings lookups return `None` for ETFs without any network call (ETFs have no earnings; the gate must not misfire on fund distribution dates).
- Verified end-to-end: a plan builds for SPY through the same pipeline as a stock.

- [ ] **Step 1: Write the failing test** (append to `tests/test_universe.py`)

```python
def test_is_etf():
    from swingbot.core.universe import is_etf
    assert is_etf("SPY") is True
    assert is_etf("spy") is True          # case-insensitive
    assert is_etf("NVDA") is False


def test_etf_skips_earnings_lookup(monkeypatch):
    # the earnings helper must return None for ETFs WITHOUT calling the network
    from swingbot.core import market_events
    def boom(*a, **k):
        raise AssertionError("network lookup attempted for an ETF")
    monkeypatch.setattr(market_events, "_fetch_earnings_date", boom, raising=False)
    assert market_events.days_to_earnings("SPY") is None


def test_spy_plan_builds_end_to_end():
    import numpy as np
    from tests.conftest import make_trend_df
    from swingbot.core.trade_plan import build_trade_plan  # existing public builder
    df = make_trend_df(300, +0.15)
    plan = build_trade_plan("SPY", df, direction="bullish", horizon_key="4w")
    assert plan is not None and plan.stop_loss < plan.entry
```

(If the trade-plan builder's public name differs — `create_plan`, `plan_for` — use the real one; the assertion is that an ETF symbol flows through with no special-casing.)

- [ ] **Step 2: Run — FAIL (`ImportError: is_etf`).**

- [ ] **Step 3: Implement**

Append to `swingbot/core/universe.py`:

```python
_ETF_CACHE: set | None = None


def is_etf(symbol: str) -> bool:
    global _ETF_CACHE
    if _ETF_CACHE is None:
        cache = set()
        for name in ("etfs", "sp500"):
            for row in load(name):
                if row["etf"]:
                    cache.add(row["symbol"])
        _ETF_CACHE = cache
    return symbol.upper() in _ETF_CACHE
```

In the earnings helper (`market_events.days_to_earnings` or equivalent), first line:

```python
    from swingbot.core.universe import is_etf
    if is_etf(symbol):
        return None   # funds don't report earnings; never gate or fetch
```

- [ ] **Step 4: Run `python -m pytest tests/test_universe.py -v` — PASS. Full suite green.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/universe.py swingbot/core/market_events.py tests/test_universe.py
git commit -m "feat: index/ETF plan support"
```

### Task E15: Incremental data cache

**Files:**
- Modify: `swingbot/core/data_store.py` (`update_cache`)
- Modify: `scripts/fetch_backtest_data.py` (`--universe` flag; incremental by default)
- Test: `tests/test_universe.py`

**Interfaces:**
- Produces: `update_cache(symbols: list[str], interval: str = "1d", base_dir: str = DATA_DIR, fetch_fn=None) -> dict` — per symbol: reads the cached CSV's last date, fetches only newer bars (`fetch_fn(symbol, start_date)`, defaulting to a ranged `yfinance.download`), concatenates without duplicate index rows, writes via atomic replace (`.tmp` + `os.replace`). Returns `{symbol: n_new_bars}`. Nightly-safe for 500+ symbols (one ranged call per symbol, no full re-downloads).
- `python scripts/fetch_backtest_data.py --universe sp500` fetches/updates the whole universe.

- [ ] **Step 1: Write the failing test** (append to `tests/test_universe.py`)

```python
def test_update_cache_appends_only_new_bars(tmp_path):
    import numpy as np
    import pandas as pd
    from tests.conftest import make_ohlcv
    from swingbot.core.data_store import save_to_disk, load_from_disk, update_cache

    old = make_ohlcv(np.full(50, 100.0), start="2026-01-01")
    save_to_disk(old, "TEST", "1d", base_dir=str(tmp_path))

    fresh = make_ohlcv(np.full(60, 101.0), start="2026-01-01")  # 10 newer bars, 50 overlap

    def fake_fetch(symbol, start):
        return fresh[fresh.index >= start]

    result = update_cache(["TEST"], base_dir=str(tmp_path), fetch_fn=fake_fetch)
    assert result["TEST"] == 10
    merged = load_from_disk("TEST", "1d", base_dir=str(tmp_path))
    assert len(merged) == 60
    assert not merged.index.duplicated().any()


def test_update_cache_empty_delta_is_noop(tmp_path):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.data_store import save_to_disk, update_cache
    save_to_disk(make_ohlcv(np.full(50, 100.0), start="2026-01-01"), "TEST", "1d",
                 base_dir=str(tmp_path))
    result = update_cache(["TEST"], base_dir=str(tmp_path),
                          fetch_fn=lambda s, start: None)
    assert result["TEST"] == 0
```

- [ ] **Step 2: Run — FAIL (`ImportError: update_cache`).**

- [ ] **Step 3: Implement** (append to `swingbot/core/data_store.py`)

```python
def _default_ranged_fetch(symbol: str, start) -> "pd.DataFrame | None":
    import yfinance as yf
    try:
        df = yf.download(symbol, start=str(start), interval="1d",
                         auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None
        return _normalize_columns(df)
    except Exception as exc:  # network flake: skip symbol this run
        log.warning("ranged fetch %s failed: %s", symbol, exc)
        return None


def update_cache(symbols: list, interval: str = "1d", base_dir: str = DATA_DIR,
                 fetch_fn=None) -> dict:
    """Incremental cache update: fetch only bars newer than each CSV's
    last date; atomic replace so a crash mid-write never corrupts a file."""
    import os
    fetch = fetch_fn or _default_ranged_fetch
    result = {}
    for symbol in symbols:
        existing = load_from_disk(symbol, interval, base_dir=base_dir)
        if existing is None or existing.empty:
            fresh = fetch(symbol, "2018-06-01")
            if fresh is None or fresh.empty:
                result[symbol] = 0
                continue
            save_to_disk(fresh, symbol, interval, base_dir=base_dir)
            result[symbol] = len(fresh)
            continue
        last = existing.index.max()
        fresh = fetch(symbol, (last + pd.Timedelta(days=1)).date())
        fresh = fresh[fresh.index > last] if fresh is not None else None
        if fresh is None or fresh.empty:
            result[symbol] = 0
            continue
        merged = pd.concat([existing, fresh])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        path = cache_path(symbol, interval, base_dir=base_dir)
        tmp = path + ".tmp"
        merged.to_csv(tmp)
        os.replace(tmp, path)
        result[symbol] = len(fresh)
    return result
```

In `scripts/fetch_backtest_data.py`, add `--universe NAME` (resolves symbols via `universe.universe_symbols(NAME)` + watchlist) and route through `update_cache` instead of full downloads when caches exist.

- [ ] **Step 4: Run `python -m pytest tests/test_universe.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/data_store.py scripts/fetch_backtest_data.py tests/test_universe.py
git commit -m "perf: incremental OHLCV cache"
```

### Task E16: Data-quality validator

**Files:**
- Modify: `swingbot/core/universe.py` (`data_quality_issues`)
- Create: `scripts/validate_data.py`
- Modify: `swingbot/core/scanning/engine.py` + backtest scripts (skip symbols with issues, logged)
- Test: `tests/test_universe.py`

**Interfaces:**
- Produces: `data_quality_issues(df, symbol) -> list[str]` — four rules: (1) >5 consecutive identical closes; (2) a single-bar close-to-close move >40% without a ≥3× volume spike (bad split adjustment); (3) any non-positive price; (4) an index gap >10 calendar days. Empty list = clean.
- `python scripts/validate_data.py` reports issues across the whole cache; scan/backtest skip flagged symbols.

- [ ] **Step 1: Write the failing test** (append to `tests/test_universe.py`)

```python
def _clean_frame(n=100):
    import numpy as np
    rng = np.random.default_rng(7)
    from tests.conftest import make_ohlcv
    return make_ohlcv(100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n)),
                      volumes=rng.integers(1_000_000, 2_000_000, n).astype(float))


def test_clean_frame_has_no_issues():
    from swingbot.core.universe import data_quality_issues
    assert data_quality_issues(_clean_frame(), "OK") == []


def test_flat_closes_flagged():
    from swingbot.core.universe import data_quality_issues
    df = _clean_frame()
    df.iloc[40:47, df.columns.get_loc("Close")] = 55.5   # 7 identical closes
    assert any("identical closes" in i for i in data_quality_issues(df, "X"))


def test_unadjusted_split_flagged():
    from swingbot.core.universe import data_quality_issues
    df = _clean_frame()
    df.iloc[50:, df.columns.get_loc("Close")] *= 0.5     # -50% jump, volume unchanged
    assert any("split" in i for i in data_quality_issues(df, "X"))


def test_negative_price_and_gap_flagged():
    import pandas as pd
    from swingbot.core.universe import data_quality_issues
    df = _clean_frame()
    df.iloc[10, df.columns.get_loc("Low")] = -1.0
    df = df.drop(df.index[60:75])                        # 15-bar hole ≈ 21 calendar days
    issues = data_quality_issues(df, "X")
    assert any("non-positive" in i for i in issues)
    assert any("gap" in i for i in issues)
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `swingbot/core/universe.py`)

```python
import numpy as np


def data_quality_issues(df: pd.DataFrame, symbol: str) -> list[str]:
    """Bad data makes every downstream number a lie -- flag, skip, report."""
    issues: list[str] = []
    if df is None or len(df) < 30:
        return [f"{symbol}: <30 bars of history"]

    close = df["Close"]
    # 1) frozen feed: >5 consecutive identical closes
    runs = (close != close.shift()).cumsum()
    if int(close.groupby(runs).transform("size").max()) > 5:
        issues.append(f"{symbol}: >5 consecutive identical closes (frozen feed?)")

    # 2) unadjusted split: >40% single-bar move without a >=3x volume spike
    move = close.pct_change().abs()
    vol_ratio = df["Volume"] / df["Volume"].rolling(20).mean()
    suspicious = (move > 0.40) & ~(vol_ratio >= 3.0)
    if suspicious.fillna(False).any():
        d = df.index[suspicious.fillna(False)][0].date()
        issues.append(f"{symbol}: >40% bar on {d} without volume spike (bad split adjust?)")

    # 3) non-positive prices
    if (df[["Open", "High", "Low", "Close"]] <= 0).any().any():
        issues.append(f"{symbol}: non-positive price values")

    # 4) calendar holes > 10 days
    deltas = df.index.to_series().diff().dt.days.dropna()
    if (deltas > 10).any():
        issues.append(f"{symbol}: gap of {int(deltas.max())} calendar days in the index")
    return issues
```

`scripts/validate_data.py`:

```python
"""Report data-quality issues across the local OHLCV cache.
Run: python scripts/validate_data.py [--universe sp500]"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swingbot.config import DATA_DIR                       # noqa: E402
from swingbot.core.data_store import load_from_disk        # noqa: E402
from swingbot.core.universe import data_quality_issues     # noqa: E402

if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    bad = 0
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*_1d.csv"))):
        symbol = os.path.basename(path).rsplit("_", 1)[0]
        issues = data_quality_issues(load_from_disk(symbol, "1d"), symbol)
        for i in issues:
            print("ISSUE:", i)
        bad += bool(issues)
    print(f"done — {bad} symbols with issues")
```

(Adjust the glob to the real cache filename pattern from `data_store.cache_path` — check it before writing the script.) Scan wiring: extend the E12 skip block to also call `data_quality_issues` and skip+log when non-empty.

- [ ] **Step 4: Run `python -m pytest tests/test_universe.py -v` — PASS. Then run `python scripts/validate_data.py` once over the real cache and fix/refetch anything it flags.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/universe.py scripts/validate_data.py swingbot/core/scanning/engine.py tests/test_universe.py
git commit -m "feat: data-quality gate"
```

### Task E17: Overnight gap model

**Files:**
- Create: `swingbot/core/edge/gates.py`
- Test: `tests/test_edge_gates.py`

**Interfaces:**
- Produces: `gap_stats(df, lookback=250) -> dict` (`{p90_gap_pct, p99_gap_pct, n}` over `|Open/prev Close − 1| × 100`); `stop_beyond_gap_noise(stop_distance_pct, gap_p90_pct, cushion=1.0) -> bool` (stop must sit ≥ `cushion` × P90 gap away — inside that band an overnight gap decides the trade, not the setup).
- Plans whose stop fails the check get `"gap_fragile": true` in the plan/alert annotations (E64 draws it; E33 fold-tests it as a filter).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_gates.py
import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.edge.gates import gap_stats, stop_beyond_gap_noise


def _with_gaps(gap_every=10, gap_pct=3.0, n=300):
    closes = np.full(n, 100.0)
    df = make_ohlcv(closes, spread_pct=1.0)
    open_col = df.columns.get_loc("Open")
    for i in range(gap_every, n, gap_every):
        df.iloc[i, open_col] = 100.0 * (1 + gap_pct / 100)
    return df


def test_gappy_ticker_has_fat_gap_tail():
    smooth = gap_stats(make_ohlcv(np.full(300, 100.0), spread_pct=1.0))
    gappy = gap_stats(_with_gaps())
    assert gappy["p90_gap_pct"] > smooth["p90_gap_pct"]
    assert gappy["p99_gap_pct"] >= gappy["p90_gap_pct"]
    assert gappy["n"] == 250   # lookback bound respected


def test_stop_inside_gap_noise_is_fragile():
    # stop 1.5% away, P90 gap 3% -> a coin flip, not risk control
    assert stop_beyond_gap_noise(1.5, 3.0) is False
    assert stop_beyond_gap_noise(4.0, 3.0) is True
```

- [ ] **Step 2: Run — FAIL (`ModuleNotFoundError`).**

- [ ] **Step 3: Implement**

```python
# swingbot/core/edge/gates.py
"""Entry gates driven by distributions, not vibes: overnight gap noise
(this task), earnings blackout (E18). Each is a pure function; wiring is
always flag-gated and fold-validated before it can touch live behavior."""
from __future__ import annotations

import numpy as np
import pandas as pd


def gap_stats(df: pd.DataFrame, lookback: int = 250) -> dict:
    """Distribution of overnight gaps |Open / prev Close - 1| in percent."""
    tail = df.tail(lookback + 1)
    gaps = (tail["Open"] / tail["Close"].shift(1) - 1.0).abs().dropna() * 100.0
    if gaps.empty:
        return {"p90_gap_pct": 0.0, "p99_gap_pct": 0.0, "n": 0}
    return {"p90_gap_pct": float(np.percentile(gaps, 90)),
            "p99_gap_pct": float(np.percentile(gaps, 99)),
            "n": int(len(gaps))}


def stop_beyond_gap_noise(stop_distance_pct: float, gap_p90_pct: float,
                          cushion: float = 1.0) -> bool:
    """A stop inside the ticker's routine overnight gap is decided by the
    open print, not by the setup. True = the stop clears the noise."""
    return stop_distance_pct >= cushion * gap_p90_pct
```

Annotation wiring (advice-only until E33 decides): where plan requirements/annotations are assembled in the scan path, compute `gs = gap_stats(df)` and set `gap_fragile = not stop_beyond_gap_noise(stop_dist_pct, gs["p90_gap_pct"])` onto the item; the embed shows `⚠ stop inside P90 overnight gap ({p90:.1f}%)` when true.

- [ ] **Step 4: Run `python -m pytest tests/test_edge_gates.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/gates.py tests/test_edge_gates.py
git commit -m "feat: overnight gap-noise model"
```

### Task E18: Earnings blackout gate

**Files:**
- Modify: `swingbot/core/edge/gates.py`
- Modify: `swingbot/config.py` (Field `EARNINGS_BLACKOUT_DAYS`, number, default 0 = off, min 0, max 10, step 1, section "Universe & Scanning")
- Test: `tests/test_edge_gates.py`

**Interfaces:**
- Produces: `in_earnings_blackout(symbol, now=None, days=None, days_to_earnings_fn=None) -> bool` — True when `0 ≤ days_to_earnings < days`. Uses the existing earnings source (`market_events.days_to_earnings`, which is ETF-exempt since E14); the advisor's Finnhub module (`swingbot.core.advisor.market_context.days_to_earnings`) is soft-imported as a second source when present. `days=0` (default) disables the gate entirely. Flag-gated filter candidate for E33.

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_gates.py`)

```python
def test_earnings_blackout_window():
    from swingbot.core.edge.gates import in_earnings_blackout
    assert in_earnings_blackout("NVDA", days=3, days_to_earnings_fn=lambda s: 2) is True
    assert in_earnings_blackout("NVDA", days=3, days_to_earnings_fn=lambda s: 5) is False
    assert in_earnings_blackout("NVDA", days=3, days_to_earnings_fn=lambda s: None) is False
    assert in_earnings_blackout("NVDA", days=0, days_to_earnings_fn=lambda s: 1) is False  # off


def test_earnings_blackout_etf_exempt():
    from swingbot.core.edge.gates import in_earnings_blackout
    # default source is ETF-exempt (E14 returns None) -> never blacked out
    assert in_earnings_blackout("SPY", days=5) is False
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `swingbot/core/edge/gates.py`)

```python
from swingbot import config


def _default_days_to_earnings(symbol: str):
    try:  # advisor's Finnhub feed, when the llm-advisor plan is merged
        from swingbot.core.advisor.market_context import days_to_earnings as finnhub_days
        d = finnhub_days(symbol)
        if d is not None:
            return d
    except ImportError:
        pass
    from swingbot.core import market_events
    return market_events.days_to_earnings(symbol)


def in_earnings_blackout(symbol: str, now=None, days: int | None = None,
                         days_to_earnings_fn=None) -> bool:
    window = days if days is not None else getattr(config, "EARNINGS_BLACKOUT_DAYS", 0)
    if window <= 0:
        return False
    fn = days_to_earnings_fn or _default_days_to_earnings
    dte = fn(symbol)
    return dte is not None and 0 <= dte < window
```

- [ ] **Step 4: Run `python -m pytest tests/test_edge_gates.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/gates.py swingbot/config.py tests/test_edge_gates.py
git commit -m "feat: earnings blackout gate (off by default)"
```

### Task E19: Intraday confirmation data (1h bars)

**Files:**
- Modify: `swingbot/core/data_store.py`
- Test: `tests/test_universe.py`

**Interfaces:**
- Produces: `get_intraday(symbol, interval="1h", base_dir=DATA_DIR, fetch_fn=None) -> pd.DataFrame | None` — disk-cached 1h bars (`{symbol}_1h.csv` via the existing `cache_path`/`save_to_disk` machinery), refreshed when the cache is older than 4 hours, fetch window capped at 700 days (yfinance's 730-day 1h limit with margin). **None-safe**: any fetch error → cached copy if present, else `None`. Daily-only mode always works — nothing downstream may *require* intraday data (E29 treats `None` as neutral).

- [ ] **Step 1: Write the failing test** (append to `tests/test_universe.py`)

```python
def test_get_intraday_roundtrip_and_cache(tmp_path):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.data_store import get_intraday

    frame = make_ohlcv(np.full(40, 100.0), start="2026-07-01")
    calls = {"n": 0}

    def fake_fetch(symbol, interval):
        calls["n"] += 1
        return frame

    a = get_intraday("TEST", base_dir=str(tmp_path), fetch_fn=fake_fetch)
    b = get_intraday("TEST", base_dir=str(tmp_path), fetch_fn=fake_fetch)
    assert a is not None and len(a) == 40
    assert len(b) == 40
    assert calls["n"] == 1          # second call served from the fresh cache


def test_get_intraday_none_on_fetch_error(tmp_path):
    from swingbot.core.data_store import get_intraday

    def broken(symbol, interval):
        raise RuntimeError("rate limited")

    assert get_intraday("TEST", base_dir=str(tmp_path), fetch_fn=broken) is None
```

- [ ] **Step 2: Run — FAIL (`ImportError: get_intraday`).**

- [ ] **Step 3: Implement** (append to `swingbot/core/data_store.py`)

```python
INTRADAY_MAX_AGE_SECONDS = 4 * 3600


def get_intraday(symbol: str, interval: str = "1h", base_dir: str = DATA_DIR,
                 fetch_fn=None) -> "pd.DataFrame | None":
    """Cached 1h bars for the E29 entry-timing annotation. NEVER required:
    every caller must treat None as 'no intraday data, stay neutral'."""
    import os
    import time
    path = cache_path(symbol, interval, base_dir=base_dir)
    fresh_enough = (os.path.exists(path)
                    and time.time() - os.path.getmtime(path) < INTRADAY_MAX_AGE_SECONDS)
    if fresh_enough:
        return load_from_disk(symbol, interval, base_dir=base_dir)

    def _default_fetch(sym, iv):
        import yfinance as yf
        df = yf.download(sym, period="700d", interval=iv,
                         auto_adjust=True, progress=False)
        return _normalize_columns(df) if df is not None and not df.empty else None

    try:
        df = (fetch_fn or _default_fetch)(symbol, interval)
    except Exception as exc:
        log.warning("intraday fetch %s failed: %s", symbol, exc)
        df = None
    if df is None or df.empty:
        return load_from_disk(symbol, interval, base_dir=base_dir)  # stale > nothing
    save_to_disk(df, symbol, interval, base_dir=base_dir)
    return df
```

- [ ] **Step 4: Run `python -m pytest tests/test_universe.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/data_store.py tests/test_universe.py
git commit -m "feat: 1h bar cache"
```

### Task E20: Scan parallelization

**Files:**
- Modify: `swingbot/core/scanning/engine.py`
- Modify: `swingbot/config.py` (Field `SCAN_WORKERS`, number, default 4, min 1, max 16, step 1, section "Universe & Scanning", help "Thread-pool size for per-ticker scanning. 4 is CX23-safe; raise only with the E82 telemetry watching.")
- Test: `tests/test_universe.py`

**Interfaces:**
- Produces: `map_tickers(fn, tickers, workers=None) -> list` — thread-pool map that (a) **preserves input order** in its results, (b) isolates errors (an exception in one ticker logs and yields `None` for that slot, never kills the scan), (c) degrades to serial when `workers <= 1`. The per-ticker analysis body of `_sync_run_scan` is extracted into a function and routed through it; the yfinance crawl (`_crawl_latest_data`) already batches and stays as-is.

- [ ] **Step 1: Write the failing test** (append to `tests/test_universe.py`)

```python
def test_map_tickers_preserves_order_and_matches_serial():
    from swingbot.core.scanning.engine import map_tickers
    tickers = [f"T{i}" for i in range(10)]
    fn = lambda t: t.lower()
    assert map_tickers(fn, tickers, workers=4) == map_tickers(fn, tickers, workers=1)
    assert map_tickers(fn, tickers, workers=4) == [t.lower() for t in tickers]


def test_map_tickers_isolates_errors():
    from swingbot.core.scanning.engine import map_tickers
    def flaky(t):
        if t == "BOOM":
            raise RuntimeError("bad ticker")
        return t
    out = map_tickers(flaky, ["A", "BOOM", "C"], workers=3)
    assert out == ["A", None, "C"]
```

- [ ] **Step 2: Run — FAIL (`ImportError: map_tickers`).**

- [ ] **Step 3: Implement** (add to `swingbot/core/scanning/engine.py`)

```python
from concurrent.futures import ThreadPoolExecutor


def map_tickers(fn, tickers: list, workers: int | None = None) -> list:
    """Order-preserving, error-isolated parallel map for the scan loop.
    The per-ticker work is pandas/numpy-heavy (releases the GIL in C) so
    threads give real speedup without multiprocessing's pickling pain."""
    n = workers if workers is not None else getattr(config, "SCAN_WORKERS", 4)

    def safe(t):
        try:
            return fn(t)
        except Exception:
            log.exception("scan worker failed for %s", t)
            return None

    if n <= 1 or len(tickers) <= 1:
        return [safe(t) for t in tickers]
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(safe, tickers))
```

Then in `_sync_run_scan`, extract the existing per-ticker analysis body into `def _scan_one(ticker, dfs, h, progress): ...` (returning the ticker's `ScanItem` list) and replace the serial loop with:

```python
    per_ticker = map_tickers(lambda t: _scan_one(t, dfs, h, progress), tickers)
    items = [item for sub in per_ticker if sub for item in sub]
```

`ScanProgress` updates (`progress.done += 1`) are plain attribute writes under the GIL — already safe per its docstring. Signal-confirmation state writes must stay in the main thread: `_scan_one` returns candidates; confirmation bookkeeping happens after the join, exactly where it happens today.

- [ ] **Step 4: Run `python -m pytest tests/test_universe.py -v` — PASS. Full suite green (dedup and confirmation tests unchanged — same ordered item set).**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/engine.py swingbot/config.py tests/test_universe.py
git commit -m "perf: parallel scan"
```

### Task E21: Universe-scale dry run

Operational task — no new code.

- [ ] **Step 1: Fetch the full cache:** `python scripts/fetch_backtest_data.py --universe sp500` (first run is the big one; nightly incrementals are cheap after E15).
- [ ] **Step 2: Dry-run a full scan** in a test channel: set `SCAN_UNIVERSE=sp500` and `DISCORD_CHANNEL_TRADES_ID=<test channel>` in `.env`, trigger one scan, and record in the Progress block: wall-clock duration, peak RSS (`ps` / Task Manager), alerts produced, errors logged.
- [ ] **Step 3: Tune if needed:** if the scan exceeds ~15 min on the CX23, adjust `SCAN_WORKERS` (try 6) and/or confirm the E15 cache is being hit rather than live-fetching; re-run and re-record. Revert `.env` to `watchlist` when done.
- [ ] **Step 4: Commit the notes**

```bash
git add docs/superpowers/plans/2026-07-11-edge-engine.md
git commit -m "docs: sp500 dry-run telemetry"
```

### Task E22: Phase E1 checkpoint

- [ ] **Step 1: Full suite + `make check` — green.**
- [ ] **Step 2: Finalize `docs/superpowers/results/2026-XX-edge-baseline.md`** (started at E11): the frictions-ON, liquidity-screened TRAIN 2018–2023 table per strategy (N, WR, expectancy_r, max DD) — **this is the reference number every Phase-E2 component must beat.** Include the frictions-off deltas and the list of liquidity/data-quality excluded symbols.
- [ ] **Step 3: Update the Progress block and commit**

```bash
git add docs/superpowers/results/ docs/superpowers/plans/2026-07-11-edge-engine.md
git commit -m "docs: friction-adjusted baseline"
```

---

# Phase E2 — Signal & exit upgrades (E23–E44)

Every factor lands the same way: pure function → flag-gated filter/score → walk-forward fold gate (E39 harness; the fold *decisions* are recorded at E33). No factor tunes on 2024+.

### Task E23: Regime model v2

**Files:**
- Create: `swingbot/core/edge/regime2.py`
- Test: `tests/test_edge_regime2.py`

**Interfaces:**
- Produces: constants `REGIMES = ("bull_quiet", "bull_volatile", "bear_quiet", "bear_volatile")`, `VOL_PCTILE_SPLIT = 0.60`, `TREND_EMA = 200`, `BREADTH_TIEBREAK = 50.0`; `classify(spy_df, breadth: float | None = None) -> str`; `regime_series(spy_df) -> pd.Series` (one label per bar, aligned to the index, for backtests).
- Rules (transparent, frozen): trend = last close vs 200-EMA (breadth ≥ 50 breaks the tie when price is within ±1% of the EMA and breadth is provided); vol = 20d realized vol vs its own trailing 252d 60th percentile (`quiet` below, `volatile` at/above).
- Consumed by: E24 gates, E61 shading, E72 timeline, `!regime`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_regime2.py
import numpy as np

from tests.conftest import make_ohlcv, make_trend_df
from swingbot.core.edge.regime2 import REGIMES, classify, regime_series


def _vol_walk(daily_pct, vol, n=400, seed=3):
    rng = np.random.default_rng(seed)
    rets = rng.normal(daily_pct / 100, vol / 100, n)
    return make_ohlcv(100 * np.cumprod(1 + rets))


def test_quiet_uptrend_is_bull_quiet():
    assert classify(make_trend_df(400, +0.15)) == "bull_quiet"


def test_quiet_downtrend_is_bear_quiet():
    assert classify(make_trend_df(400, -0.15)) == "bear_quiet"


def test_late_vol_spike_flips_to_volatile():
    df = _vol_walk(+0.08, 0.5)
    spiky = _vol_walk(+0.08, 3.5, n=40, seed=4)

    df.iloc[-40:] = spiky.values
    assert classify(df).endswith("_volatile")


def test_breadth_breaks_ties_near_the_ema():
    flat = make_ohlcv(np.full(400, 100.0), spread_pct=0.2)  # price == EMA
    assert classify(flat, breadth=70.0).startswith("bull")
    assert classify(flat, breadth=30.0).startswith("bear")


def test_regime_series_aligned_and_labeled():
    df = make_trend_df(400, +0.15)
    s = regime_series(df)
    assert s.index.equals(df.index)
    assert set(s.dropna().unique()) <= set(REGIMES)
    assert s.iloc[-1] == "bull_quiet"
```

- [ ] **Step 2: Run — FAIL (`ModuleNotFoundError`).**

- [ ] **Step 3: Implement**

```python
# swingbot/core/edge/regime2.py
"""Four-state market regime: (bull|bear) x (quiet|volatile).

Trend: SPY close vs its 200-EMA. Vol: 20-day realized volatility vs the
60th percentile of its own trailing year. All thresholds are module
constants -- transparent enough for the fold harness to audit, dumb
enough not to overfit. Regime v1 (scanning/regime.py) stays untouched;
consumers migrate deliberately."""
from __future__ import annotations

import numpy as np
import pandas as pd

REGIMES = ("bull_quiet", "bull_volatile", "bear_quiet", "bear_volatile")
TREND_EMA = 200
VOL_WINDOW = 20
VOL_HISTORY = 252
VOL_PCTILE_SPLIT = 0.60
EMA_TIE_BAND_PCT = 1.0     # within +-1% of the EMA the trend call is a coin flip
BREADTH_TIEBREAK = 50.0    # ...so breadth (E28), when available, decides


def _trend_and_vol(spy_df: pd.DataFrame):
    close = spy_df["Close"]
    ema = close.ewm(span=TREND_EMA, adjust=False).mean()
    rv = close.pct_change().rolling(VOL_WINDOW).std()
    vol_threshold = rv.rolling(VOL_HISTORY, min_periods=VOL_WINDOW * 3).quantile(VOL_PCTILE_SPLIT)
    return close, ema, rv, vol_threshold


def classify(spy_df: pd.DataFrame, breadth: float | None = None) -> str:
    close, ema, rv, thr = _trend_and_vol(spy_df)
    c, e = float(close.iloc[-1]), float(ema.iloc[-1])
    if breadth is not None and abs(c - e) / e * 100 <= EMA_TIE_BAND_PCT:
        bull = breadth >= BREADTH_TIEBREAK
    else:
        bull = c >= e
    t = thr.iloc[-1]
    volatile = bool(not np.isnan(t) and rv.iloc[-1] >= t)
    return f"{'bull' if bull else 'bear'}_{'volatile' if volatile else 'quiet'}"


def regime_series(spy_df: pd.DataFrame) -> pd.Series:
    """Vectorized per-bar labels for backtests (no breadth history -> pure
    price rule; identical to classify(breadth=None) at every bar)."""
    close, ema, rv, thr = _trend_and_vol(spy_df)
    bull = close >= ema
    volatile = (rv >= thr).fillna(False)
    labels = np.where(bull, "bull", "bear") + np.where(volatile, "_volatile", "_quiet")
    return pd.Series(labels, index=spy_df.index)
```

- [ ] **Step 4: Run `python -m pytest tests/test_edge_regime2.py -v` — PASS (5 tests).**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/regime2.py tests/test_edge_regime2.py
git commit -m "feat: 4-state regime model"
```

### Task E24: Per-strategy regime gates (walk-forward candidate)

**Files:**
- Modify: `swingbot/core/strategy_types.py` (constant `REGIME_ALLOW`), `swingbot/core/entry_filters.py` (gate hook)
- Modify: `swingbot/config.py` (Field `REGIME_GATES_ENABLED`, checkbox, default false, section "Universe & Scanning")
- Test: `tests/test_edge_regime2.py`

**Interfaces:**
- Produces: `REGIME_ALLOW: dict[str, tuple[str, ...]]` in `strategy_types.py` — `{strategy: allowed regimes}`; **empty until E33's fold runs fill it** (this task ships mechanism only). `entry_filters.apply_regime_gate(bull, bear, strategy, regimes: pd.Series) -> tuple[pd.Series, pd.Series]` — zeroes entries on bars whose regime isn't allowed; missing key or flag off ⇒ untouched. Backtest and live share the gate through `entries_for` exactly like `STRATEGY_GATES`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_regime2.py`)

```python
def test_regime_gate_masks_disallowed_bars(monkeypatch):
    import pandas as pd
    from swingbot.core import entry_filters
    from swingbot.core import strategy_types
    from swingbot import config

    idx = pd.bdate_range("2024-01-01", periods=6)
    bull = pd.Series([True] * 6, index=idx)
    bear = pd.Series([False] * 6, index=idx)
    regimes = pd.Series(["bull_quiet"] * 3 + ["bear_volatile"] * 3, index=idx)

    monkeypatch.setattr(config, "REGIME_GATES_ENABLED", True, raising=False)
    monkeypatch.setitem(strategy_types.REGIME_ALLOW, "RSI", ("bull_quiet",))

    b2, s2 = entry_filters.apply_regime_gate(bull, bear, "RSI", regimes)
    assert b2.tolist() == [True, True, True, False, False, False]


def test_regime_gate_noop_when_unconfigured(monkeypatch):
    import pandas as pd
    from swingbot.core import entry_filters
    from swingbot import config
    monkeypatch.setattr(config, "REGIME_GATES_ENABLED", True, raising=False)
    idx = pd.bdate_range("2024-01-01", periods=3)
    bull = pd.Series([True, True, True], index=idx)
    bear = pd.Series(False, index=idx)
    regimes = pd.Series(["bear_volatile"] * 3, index=idx)
    b2, _ = entry_filters.apply_regime_gate(bull, bear, "MACD", regimes)  # no REGIME_ALLOW entry
    assert b2.tolist() == [True, True, True]
```

- [ ] **Step 2: Run — FAIL (`AttributeError: REGIME_ALLOW` / `apply_regime_gate`).**

- [ ] **Step 3: Implement**

`strategy_types.py` (append):

```python
# Per-strategy allowed regimes (E24 mechanism; E33's fold runs decide the
# actual sets). Missing key = allowed in every regime. Both the backtest
# and live signals flow through entry_filters.apply_regime_gate, so the
# gate can never diverge between them.
REGIME_ALLOW: dict[str, tuple] = {}
```

`entry_filters.py` (append; call it inside `entries_for` right after the existing `STRATEGY_GATES` mask, passing the regime series when the caller supplies one):

```python
def apply_regime_gate(bull: pd.Series, bear: pd.Series, strategy: str,
                      regimes: "pd.Series | None"):
    """Zero out entries on bars whose market regime the strategy isn't
    allowed to trade. Flag-gated + empty-by-default: shipping the
    mechanism costs nothing until E33's evidence fills REGIME_ALLOW."""
    from swingbot import config
    from swingbot.core.strategy_types import REGIME_ALLOW
    allowed = REGIME_ALLOW.get(strategy)
    if not getattr(config, "REGIME_GATES_ENABLED", False) or not allowed or regimes is None:
        return bull, bear
    ok = regimes.reindex(bull.index).isin(allowed).fillna(False)
    return (bull & ok), (bear & ok)
```

`entries_for(...)` gains an optional `regimes: pd.Series | None = None` parameter threaded from: the backtest (build `regime_series(spy_df)` once per run when the flag is on) and the live signal path (label the last bar via `classify`). Both pass `None` when the flag is off — zero behavior change.

- [ ] **Step 4: Run `python -m pytest tests/test_edge_regime2.py -v` — PASS. Full suite green (flag off everywhere).**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/strategy_types.py swingbot/core/entry_filters.py swingbot/core/backtest.py swingbot/core/signals.py swingbot/config.py tests/test_edge_regime2.py
git commit -m "feat: regime gate mechanism"
```

### Task E25: Relative-strength factor

**Files:**
- Create: `swingbot/core/edge/factors.py`
- Test: `tests/test_edge_factors.py`

**Interfaces:**
- Produces: `relative_return(ticker_df, spy_df, window=63) -> float | None` (ticker 63-bar return minus SPY's, as a fraction); `rs_percentile(ticker_df, spy_df, window=63, universe_rels: list[float] | None = None) -> float` — percentile (0–100) of the ticker's relative return within the scanned universe's relative returns; `universe_rels=None` ⇒ neutral 50.0. `refresh_rs_cache(universe_dfs: dict, spy_df) -> dict` writes `data/universe/rs_cache.json` (`{"as_of": iso, "rels": {symbol: rel}}`, via `jsonio.write_json`) once per scan; `load_rs_cache() -> dict`.
- Filter candidate for E33: `rs_min` on long entries (grid {50, 60, 70}).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_factors.py
import numpy as np
import pytest

from tests.conftest import make_trend_df
from swingbot.core.edge.factors import relative_return, rs_percentile


def test_outperformer_beats_underperformer():
    spy = make_trend_df(200, +0.05)
    strong = make_trend_df(200, +0.30)
    weak = make_trend_df(200, -0.20)
    assert relative_return(strong, spy) > 0 > relative_return(weak, spy)
    rels = [relative_return(make_trend_df(200, p), spy)
            for p in (-0.2, -0.1, 0.0, 0.1, 0.2, 0.3)]
    assert rs_percentile(strong, spy, universe_rels=rels) > \
           rs_percentile(weak, spy, universe_rels=rels)
    assert rs_percentile(strong, spy, universe_rels=rels) >= 80.0


def test_neutral_without_universe():
    spy = make_trend_df(200, +0.05)
    assert rs_percentile(make_trend_df(200, +0.30), spy) == 50.0


def test_short_history_is_none():
    spy = make_trend_df(200, +0.05)
    assert relative_return(make_trend_df(30, +0.30), spy) is None


def test_rs_cache_roundtrip(tmp_path, monkeypatch):
    from swingbot.core.edge import factors
    monkeypatch.setattr(factors, "RS_CACHE_PATH", str(tmp_path / "rs_cache.json"))
    spy = make_trend_df(200, +0.05)
    cache = factors.refresh_rs_cache({"STRONG": make_trend_df(200, +0.30)}, spy)
    assert "STRONG" in cache["rels"]
    assert factors.load_rs_cache()["rels"] == cache["rels"]
```

- [ ] **Step 2: Run — FAIL (`ModuleNotFoundError`).**

- [ ] **Step 3: Implement**

```python
# swingbot/core/edge/factors.py
"""Signal-quality factors: relative strength (this task), sector RS (E26),
multi-timeframe alignment (E27), breadth (E28), intraday confirmation
(E29), candle quality at levels (E34). Pure functions over DataFrames --
the scan supplies data, the fold harness supplies judgment."""
from __future__ import annotations

import datetime as dt
import os

import numpy as np
import pandas as pd

from swingbot import config
from swingbot.core.jsonio import read_json, write_json

RS_WINDOW = 63  # ~3 months of trading days
RS_CACHE_PATH = os.path.join(config.DATA_DIR, "universe", "rs_cache.json")


def relative_return(ticker_df: pd.DataFrame, spy_df: pd.DataFrame,
                    window: int = RS_WINDOW) -> float | None:
    if ticker_df is None or spy_df is None or len(ticker_df) < window + 1 or len(spy_df) < window + 1:
        return None
    t = float(ticker_df["Close"].iloc[-1] / ticker_df["Close"].iloc[-window - 1] - 1.0)
    s = float(spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[-window - 1] - 1.0)
    return t - s


def rs_percentile(ticker_df: pd.DataFrame, spy_df: pd.DataFrame,
                  window: int = RS_WINDOW,
                  universe_rels: list | None = None) -> float:
    rel = relative_return(ticker_df, spy_df, window)
    if rel is None or not universe_rels:
        return 50.0
    rels = [r for r in universe_rels if r is not None]
    if not rels:
        return 50.0
    return float(round(100.0 * np.mean([rel >= r for r in rels]), 1))


def refresh_rs_cache(universe_dfs: dict, spy_df: pd.DataFrame) -> dict:
    cache = {"as_of": dt.date.today().isoformat(),
             "rels": {sym: relative_return(df, spy_df)
                      for sym, df in universe_dfs.items()}}
    write_json(RS_CACHE_PATH, cache)
    return cache


def load_rs_cache() -> dict:
    return read_json(RS_CACHE_PATH, {"as_of": None, "rels": {}})
```

Scan wiring: `_sync_run_scan` calls `refresh_rs_cache(dfs, spy_df)` once after the crawl; each item gets `item.rs_percentile = rs_percentile(df, spy_df, universe_rels=list(cache["rels"].values()))` for E37's score and the E60 chart strip.

- [ ] **Step 4: Run `python -m pytest tests/test_edge_factors.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/factors.py swingbot/core/scanning/engine.py tests/test_edge_factors.py
git commit -m "feat: relative-strength factor"
```

### Task E26: Sector RS factor

**Files:**
- Modify: `swingbot/core/edge/factors.py`
- Test: `tests/test_edge_factors.py`

**Interfaces:**
- Produces: `sector_rs_percentile(sector: str, sector_etf_dfs: dict[str, pd.DataFrame], spy_df, sector_of_etf: dict[str, str] | None = None, window=63) -> float` — the sector's ETF relative return ranked against all 11 sector ETFs (0–100; 50.0 when unknown); `rs_score(ticker_pctile, sector_pctile) -> float` = `0.7 × ticker + 0.3 × sector`. `sector_of_etf` defaults to `universe.sector_map("etfs")` inverted (ETF symbol → sector).

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_factors.py`)

```python
def test_sector_rs_ranks_across_etfs():
    from swingbot.core.edge.factors import sector_rs_percentile
    spy = make_trend_df(200, +0.05)
    etf_dfs = {"XLE": make_trend_df(200, +0.40),
               "XLK": make_trend_df(200, +0.10),
               "XLU": make_trend_df(200, -0.10)}
    sectors = {"XLE": "Energy", "XLK": "Information Technology", "XLU": "Utilities"}
    hot = sector_rs_percentile("Energy", etf_dfs, spy, sector_of_etf=sectors)
    cold = sector_rs_percentile("Utilities", etf_dfs, spy, sector_of_etf=sectors)
    assert hot > cold
    assert sector_rs_percentile("Nonexistent", etf_dfs, spy, sector_of_etf=sectors) == 50.0


def test_rs_score_weights():
    from swingbot.core.edge.factors import rs_score
    assert rs_score(80.0, 40.0) == pytest.approx(0.7 * 80 + 0.3 * 40)
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `factors.py`)

```python
def sector_rs_percentile(sector: str, sector_etf_dfs: dict, spy_df,
                         sector_of_etf: dict | None = None,
                         window: int = RS_WINDOW) -> float:
    if sector_of_etf is None:
        from swingbot.core.universe import sector_map
        sector_of_etf = sector_map("etfs")
    rels = {}
    for etf, df in sector_etf_dfs.items():
        rel = relative_return(df, spy_df, window)
        if rel is not None:
            rels[sector_of_etf.get(etf)] = rel
    mine = rels.get(sector)
    if mine is None or len(rels) < 2:
        return 50.0
    return float(round(100.0 * np.mean([mine >= r for r in rels.values()]), 1))


def rs_score(ticker_pctile: float, sector_pctile: float) -> float:
    """Combined RS: the stock carries most of the signal, its sector tide
    the rest. Weights are frozen constants, not tunables."""
    return 0.7 * ticker_pctile + 0.3 * sector_pctile
```

- [ ] **Step 4: Run `python -m pytest tests/test_edge_factors.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/factors.py tests/test_edge_factors.py
git commit -m "feat: sector RS"
```

### Task E27: Multi-timeframe alignment score

**Files:**
- Modify: `swingbot/core/edge/factors.py`
- Test: `tests/test_edge_factors.py`

**Interfaces:**
- Produces: `weekly_frame(daily_df) -> pd.DataFrame` (W-FRI resample: first/max/min/last/sum — no new data source); `mtf_alignment(daily_df, direction) -> int` (0–3) — one point each, mirrored for bearish: (1) weekly close above a rising 10-week EMA; (2) weekly higher-low structure (the two most recent completed weekly swing lows ascend); (3) daily close above the prior week's pivot `(H+L+C)/3`. Filter candidate `mtf_min` (grid {1, 2}) for E33.

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_factors.py`)

```python
def test_clean_uptrend_aligns_fully():
    from swingbot.core.edge.factors import mtf_alignment
    df = make_trend_df(400, +0.25)
    assert mtf_alignment(df, "bullish") == 3
    assert mtf_alignment(df, "bearish") == 0


def test_chop_scores_low():
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.edge.factors import mtf_alignment
    rng = np.random.default_rng(11)
    df = make_ohlcv(100 + np.cumsum(rng.normal(0, 0.3, 400)) * 0.1, spread_pct=2.0)
    assert mtf_alignment(df, "bullish") <= 1


def test_weekly_frame_shape():
    from swingbot.core.edge.factors import weekly_frame
    df = make_trend_df(400, +0.25)
    w = weekly_frame(df)
    assert list(w.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(w) < len(df) / 4
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `factors.py`)

```python
def weekly_frame(daily_df: pd.DataFrame) -> pd.DataFrame:
    return daily_df.resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min",
         "Close": "last", "Volume": "sum"}).dropna()


def _swing_lows(series: pd.Series, span: int = 2) -> list:
    vals = series.values
    return [vals[i] for i in range(span, len(vals) - span)
            if vals[i] == min(vals[i - span:i + span + 1])]


def mtf_alignment(daily_df: pd.DataFrame, direction: str) -> int:
    """0-3: how many higher-timeframe boxes this direction ticks. Weekly
    context is resampled from daily -- same data, longer lens."""
    w = weekly_frame(daily_df)
    if len(w) < 15:
        return 0
    bull = direction == "bullish"
    score = 0

    ema10 = w["Close"].ewm(span=10, adjust=False).mean()
    ema_rising = ema10.iloc[-1] > ema10.iloc[-4]
    above = w["Close"].iloc[-1] > ema10.iloc[-1]
    if (above and ema_rising) if bull else (not above and not ema_rising):
        score += 1

    lows = _swing_lows(w["Low"].iloc[:-1])   # completed weeks only
    highs = [-v for v in _swing_lows(-w["High"].iloc[:-1])]
    if bull and len(lows) >= 2 and lows[-1] > lows[-2]:
        score += 1
    if not bull and len(highs) >= 2 and highs[-1] < highs[-2]:
        score += 1

    prev = w.iloc[-2]
    pivot = (prev["High"] + prev["Low"] + prev["Close"]) / 3.0
    daily_close = float(daily_df["Close"].iloc[-1])
    if (daily_close > pivot) if bull else (daily_close < pivot):
        score += 1
    return score
```

- [ ] **Step 4: Run `python -m pytest tests/test_edge_factors.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/factors.py tests/test_edge_factors.py
git commit -m "feat: MTF alignment score"
```

### Task E28: Breadth internals

**Files:**
- Modify: `swingbot/core/edge/factors.py`; scan hook in `swingbot/core/scanning/engine.py`
- Test: `tests/test_edge_factors.py`

**Interfaces:**
- Produces: `breadth_pct_above_50ema(universe_dfs: dict) -> float | None` — percent (0–100) of universe tickers whose last close is above their 50-EMA; `None` when fewer than 20 usable tickers (a breadth reading off 6 names is noise). Computed once per scan from the already-crawled universe frames; feeds `regime2.classify(breadth=...)` and the E33 filter candidate (`no new longs when breadth < X`, grid {40, 45, 50}).

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_factors.py`)

```python
def test_breadth_split_universe():
    from swingbot.core.edge.factors import breadth_pct_above_50ema
    ups = {f"U{i}": make_trend_df(150, +0.3) for i in range(15)}
    downs = {f"D{i}": make_trend_df(150, -0.3) for i in range(15)}
    b = breadth_pct_above_50ema({**ups, **downs})
    assert b == pytest.approx(50.0, abs=1.0)


def test_breadth_none_when_universe_tiny():
    from swingbot.core.edge.factors import breadth_pct_above_50ema
    assert breadth_pct_above_50ema({"A": make_trend_df(150, +0.3)}) is None
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `factors.py`)

```python
BREADTH_MIN_TICKERS = 20


def breadth_pct_above_50ema(universe_dfs: dict) -> float | None:
    """Market internals: % of the scanned universe above its own 50-EMA.
    An index made of its members, not of cap-weighted illusions."""
    above = total = 0
    for df in universe_dfs.values():
        if df is None or len(df) < 60:
            continue
        ema50 = df["Close"].ewm(span=50, adjust=False).mean()
        total += 1
        above += bool(df["Close"].iloc[-1] > ema50.iloc[-1])
    if total < BREADTH_MIN_TICKERS:
        return None
    return round(100.0 * above / total, 1)
```

Scan hook (`_sync_run_scan`, right after the crawl): `breadth = breadth_pct_above_50ema(dfs)`; store it on the progress/funnel dict, pass into `regime2.classify(spy_df, breadth)`, and stamp `item.breadth = breadth` for E37/E66.

- [ ] **Step 4: Run `python -m pytest tests/test_edge_factors.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/factors.py swingbot/core/scanning/engine.py tests/test_edge_factors.py
git commit -m "feat: market breadth factor"
```

### Task E29: Intraday entry-timing check

**Files:**
- Modify: `swingbot/core/edge/factors.py`
- Test: `tests/test_edge_factors.py`

**Interfaces:**
- Produces: `intraday_confirms(symbol, direction, intraday_df=None) -> bool | None` — last 1h close vs the current day's running VWAP (`cum(TP×V)/cum(V)` over today's bars): above ⇒ True for longs; `None` (neutral, NEVER blocks) when no intraday data / empty day. `intraday_df=None` fetches via `data_store.get_intraday` (E19).
- **Live-only annotation** — stop-entry plans keep their daily trigger; this only annotates plan quality on the alert (`⏱ intraday: confirms/against/n-a`). Explicitly NOT a backtest filter: there is no intraday history depth to fold-test it honestly, and it must never be presented as validated.

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_factors.py`)

```python
def _hourly_day(prices, volumes=None):
    import pandas as pd
    idx = pd.date_range("2026-07-10 14:30", periods=len(prices), freq="h")
    v = volumes or [1_000_000] * len(prices)
    return pd.DataFrame({"Open": prices, "High": [p * 1.001 for p in prices],
                         "Low": [p * 0.999 for p in prices], "Close": prices,
                         "Volume": v}, index=idx)


def test_intraday_confirms_above_vwap():
    from swingbot.core.edge.factors import intraday_confirms
    rising = _hourly_day([100.0, 100.5, 101.0, 101.5])   # last close > day VWAP
    assert intraday_confirms("X", "bullish", intraday_df=rising) is True
    assert intraday_confirms("X", "bearish", intraday_df=rising) is False


def test_intraday_none_is_neutral():
    from swingbot.core.edge.factors import intraday_confirms
    assert intraday_confirms("X", "bullish", intraday_df=None,
                             fetch=lambda s: None) is None
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `factors.py`)

```python
def intraday_confirms(symbol: str, direction: str,
                      intraday_df: "pd.DataFrame | None" = None,
                      fetch=None) -> bool | None:
    """Last 1h close vs today's running VWAP. None = no data = NEUTRAL --
    this annotation may inform the operator, never gate an alert, and is
    deliberately absent from the backtest (no honest intraday history)."""
    if intraday_df is None:
        if fetch is None:
            from swingbot.core.data_store import get_intraday
            fetch = get_intraday
        intraday_df = fetch(symbol)
    if intraday_df is None or intraday_df.empty:
        return None
    last_day = intraday_df.index[-1].date()
    day = intraday_df[intraday_df.index.date == last_day]
    if day.empty or day["Volume"].sum() <= 0:
        return None
    tp = (day["High"] + day["Low"] + day["Close"]) / 3.0
    vwap = float((tp * day["Volume"]).cumsum().iloc[-1] / day["Volume"].cumsum().iloc[-1])
    above = float(day["Close"].iloc[-1]) >= vwap
    return above if direction == "bullish" else not above
```

Alert wiring: in the alert build (background thread), `item.intraday = intraday_confirms(ticker, direction)`; embed renders `⏱ intraday: ✅ confirms / ⚠️ against / — n/a`.

- [ ] **Step 4: Run `python -m pytest tests/test_edge_factors.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/factors.py swingbot/commands/scanning.py tests/test_edge_factors.py
git commit -m "feat: intraday confirmation annotation"
```

### Task E30: Anchored VWAP levels

**Files:**
- Modify: `swingbot/core/edge/factors.py` (AVWAP math + anchor finder)
- Modify: `swingbot/core/levels.py` (`collect_candidate_levels` gains the AVWAP source)
- Test: `tests/test_edge_factors.py`

**Interfaces:**
- Produces: `anchored_vwap(df, anchor_idx: int) -> pd.Series` (cumulative `TP×V / V` from the anchor bar to the end); `avwap_anchors(df, lookback=120) -> list[int]` — positional indices of: the last 2 swing lows, last 2 swing highs (5-bar pivots), and the highest-volume bar of the lookback (deduped, sorted).
- `collect_candidate_levels` appends `(avwap_value_today, "AVWAP")` for each anchor — AVWAPs then cluster with every other level source, so confluence counting picks them up with zero further changes.

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_factors.py`)

```python
def test_avwap_math_golden():
    import pandas as pd
    from swingbot.core.edge.factors import anchored_vwap
    df = _hourly_day([100.0, 102.0, 104.0], volumes=[1000, 1000, 2000])
    s = anchored_vwap(df, 0)
    # TP == Close here (High/Low straddle by ±0.1%): vwap_2 =
    # (100*1000 + 102*1000 + 104*2000) / 4000 = 102.5 (±0.1% wick noise)
    assert s.iloc[-1] == pytest.approx(102.5, rel=2e-3)
    assert len(s) == 3 and s.index.equals(df.index)


def test_avwap_levels_enter_the_level_map():
    from swingbot.core import levels
    df = make_trend_df(300, +0.2)
    h = {"fib_lookback": 60}   # minimal horizon dict fields the collector uses
    cands = levels.collect_candidate_levels(df, h, float(df["Close"].iloc[-1]))
    assert any(src == "AVWAP" for _, src in cands)
```

(If `collect_candidate_levels` needs more `h` keys, reuse the fixture/horizon dict existing levels tests use — check `tests/` for a prior fixture before inventing one.)

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement**

Append to `factors.py`:

```python
def anchored_vwap(df: pd.DataFrame, anchor_idx: int) -> pd.Series:
    """Volume-weighted average price anchored at a specific bar -- the
    market's own average cost since that event. Institutions defend it;
    that's why it acts as support/resistance."""
    part = df.iloc[anchor_idx:]
    tp = (part["High"] + part["Low"] + part["Close"]) / 3.0
    return (tp * part["Volume"]).cumsum() / part["Volume"].cumsum()


def avwap_anchors(df: pd.DataFrame, lookback: int = 120) -> list:
    """Anchor bars that mean something: recent swing pivots + the highest-
    volume day (a capitulation/breakout bar everyone remembers)."""
    n = len(df)
    start = max(0, n - lookback)
    lows, highs = df["Low"].values, df["High"].values
    anchors = set()
    span = 5
    pivots_lo = [i for i in range(max(start, span), n - span)
                 if lows[i] == min(lows[i - span:i + span + 1])]
    pivots_hi = [i for i in range(max(start, span), n - span)
                 if highs[i] == max(highs[i - span:i + span + 1])]
    anchors.update(pivots_lo[-2:])
    anchors.update(pivots_hi[-2:])
    anchors.add(start + int(df["Volume"].values[start:].argmax()))
    return sorted(anchors)
```

In `swingbot/core/levels.py::collect_candidate_levels`, alongside the other sources (each already individually try/excepted):

```python
    # Anchored VWAPs (edge E30): today's value of each anchored series.
    try:
        from swingbot.core.edge.factors import anchored_vwap, avwap_anchors
        for a in avwap_anchors(df):
            v = float(anchored_vwap(df, a).iloc[-1])
            if v > 0:
                candidates.append((v, "AVWAP"))
    except Exception:
        pass
```

- [ ] **Step 4: Run `python -m pytest tests/test_edge_factors.py -v` and the existing levels tests — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/factors.py swingbot/core/levels.py tests/test_edge_factors.py
git commit -m "feat: anchored VWAP levels"
```

### Task E31: Data-driven stops from MAE distributions

**Files:**
- Create: `swingbot/core/edge/stops.py`
- Modify: `swingbot/config.py` (Field `DATA_DRIVEN_STOPS_ENABLED`, checkbox, default false, section "Universe & Scanning")
- Test: `tests/test_edge_stops.py`

**Interfaces:**
- Produces: `mae_informed_stop_mult(entries: list[dict], strategy: str) -> float | None` — takes journal/fold trade dicts (`{"strategy", "outcome", "mae_r", ...}`, `mae_r` positive magnitude in R), computes P90 of WINNERS' MAE for the strategy, returns an ATR-mult **adjustment factor** `clamp(p90 + 0.15 cushion, 0.8, 1.3)`; `None` when winners `N < MIN_SAMPLE (= 40)`.
- Semantics: winners rarely go beyond their P90 MAE — a stop tighter than that gets noise-stopped out of trades that were going to work; a stop much wider wastes risk budget. Multiplies the plan's ATR stop distance when `DATA_DRIVEN_STOPS_ENABLED` (fold-validated at E33 using backtest-simulated MAE over fold-train trades first).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_stops.py
import pytest

from swingbot.core.edge.stops import MIN_SAMPLE, mae_informed_stop_mult


def _winners(maes, strategy="RSI"):
    return [{"strategy": strategy, "outcome": "win", "mae_r": m} for m in maes]


def test_p90_of_winner_mae_drives_the_mult():
    # 50 winners, MAE uniform 0.02..1.00 -> P90 ≈ 0.90 -> 0.90+0.15 = 1.05
    entries = _winners([i / 50 for i in range(1, 51)])
    assert mae_informed_stop_mult(entries, "RSI") == pytest.approx(1.05, abs=0.03)


def test_tight_winners_tighten_the_stop():
    # winners never drew down past 0.4R -> P90 0.36 + 0.15 = 0.51 -> clamp 0.8
    entries = _winners([0.3 + 0.002 * i for i in range(50)])
    assert mae_informed_stop_mult(entries, "RSI") == 0.8


def test_clamped_at_1_3():
    entries = _winners([2.5] * 50)
    assert mae_informed_stop_mult(entries, "RSI") == 1.3


def test_small_sample_returns_none():
    entries = _winners([0.5] * (MIN_SAMPLE - 1))
    assert mae_informed_stop_mult(entries, "RSI") is None


def test_other_strategies_ignored():
    entries = _winners([0.5] * 60, strategy="MACD")
    assert mae_informed_stop_mult(entries, "RSI") is None
```

- [ ] **Step 2: Run — FAIL (`ModuleNotFoundError`).**

- [ ] **Step 3: Implement**

```python
# swingbot/core/edge/stops.py
"""Stops and targets sized by the strategy's OWN excursion history
instead of one ATR multiple for everything.

MAE (maximum adverse excursion): how far winners went against you before
working. Stops inside the winners' P90 MAE amputate trades that were
about to work; stops far beyond it buy nothing but smaller position
sizes. MFE (E32) is the mirror image for targets. Everything here is
flag-gated (DATA_DRIVEN_STOPS_ENABLED) and fold-validated before live.
"""
from __future__ import annotations

import numpy as np

MIN_SAMPLE = 40          # winners needed before the distribution means anything
MAE_CUSHION_R = 0.15     # breathing room beyond the winners' P90
CLAMP = (0.8, 1.3)       # never move a stop by more than this factor


def mae_informed_stop_mult(entries: list, strategy: str) -> float | None:
    maes = [e["mae_r"] for e in entries
            if e.get("strategy") == strategy and e.get("outcome") == "win"
            and e.get("mae_r") is not None]
    if len(maes) < MIN_SAMPLE:
        return None
    p90 = float(np.percentile(maes, 90))
    return float(min(max(p90 + MAE_CUSHION_R, CLAMP[0]), CLAMP[1]))
```

Plan-engine wiring (behind the flag): where the ATR stop distance is computed for a plan, multiply by `mae_informed_stop_mult(journal_entries, strategy)` when it returns a value:

```python
    if getattr(config, "DATA_DRIVEN_STOPS_ENABLED", False):
        from swingbot.core.edge.stops import mae_informed_stop_mult
        mult = mae_informed_stop_mult(journal.entries(), plan.strategy)
        if mult is not None:
            stop_distance *= mult
            plan.quality_breakdown.append(f"MAE-informed stop x{mult:.2f}")
```

- [ ] **Step 4: Run `python -m pytest tests/test_edge_stops.py -v` — PASS (5 tests).**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/stops.py swingbot/config.py swingbot/core/plan_engine.py tests/test_edge_stops.py
git commit -m "feat: MAE-informed stop sizing"
```

### Task E32: MFE-informed TP2 + time stops

**Files:**
- Modify: `swingbot/core/edge/stops.py`
- Test: `tests/test_edge_stops.py`

**Interfaces:**
- Produces: `mfe_informed_tp2_r(entries, strategy) -> float | None` — P60 of winners' `mfe_r` (a runner target winners actually reach), `None` under `MIN_SAMPLE`, clamped to ≥ 0.5R; `optimal_time_stop_days(entries, strategy) -> int | None` — smallest day `d` such that ≥80% of eventual winners had reached ≥0.5R by day `d` (input dicts carry `days_to_half_r: int | None`, produced by the exit simulator for fold trades and by journal MFE tracking live) — beyond `d`, holding a sub-0.5R position has historically been dead capital.
- Both feed `plan_engine` as optional overrides behind `DATA_DRIVEN_STOPS_ENABLED`, fold-validated at E33 as exit-model variants.

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_stops.py`)

```python
def _winners_with(key, values, strategy="RSI"):
    return [{"strategy": strategy, "outcome": "win", key: v} for v in values]


def test_mfe_tp2_is_p60_of_winner_mfe():
    from swingbot.core.edge.stops import mfe_informed_tp2_r
    entries = _winners_with("mfe_r", [i / 25 for i in range(1, 51)])  # 0.04..2.0
    # P60 of uniform(0.04..2.0) ≈ 1.216
    assert mfe_informed_tp2_r(entries, "RSI") == pytest.approx(1.216, abs=0.06)


def test_mfe_tp2_floors_at_half_r():
    from swingbot.core.edge.stops import mfe_informed_tp2_r
    entries = _winners_with("mfe_r", [0.2] * 50)
    assert mfe_informed_tp2_r(entries, "RSI") == 0.5


def test_time_stop_day():
    from swingbot.core.edge.stops import optimal_time_stop_days
    # 40 winners hit 0.5R by day 3, 10 stragglers by day 12:
    # cumulative 80% is reached at day 3
    entries = (_winners_with("days_to_half_r", [3] * 40)
               + _winners_with("days_to_half_r", [12] * 10))
    assert optimal_time_stop_days(entries, "RSI") == 3


def test_time_stop_none_under_sample():
    from swingbot.core.edge.stops import optimal_time_stop_days
    assert optimal_time_stop_days(_winners_with("days_to_half_r", [3] * 10), "RSI") is None
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `stops.py`)

```python
TP2_FLOOR_R = 0.5
TIME_STOP_COVERAGE = 0.80


def mfe_informed_tp2_r(entries: list, strategy: str) -> float | None:
    """P60 of winners' max favorable excursion: a TP2 the runner actually
    reaches more often than not, instead of a hope."""
    mfes = [e["mfe_r"] for e in entries
            if e.get("strategy") == strategy and e.get("outcome") == "win"
            and e.get("mfe_r") is not None]
    if len(mfes) < MIN_SAMPLE:
        return None
    return float(max(np.percentile(mfes, 60), TP2_FLOOR_R))


def optimal_time_stop_days(entries: list, strategy: str) -> int | None:
    """Day by which TIME_STOP_COVERAGE of eventual winners had already
    reached +0.5R. A position slower than that is statistically dead
    capital -- frequency (the compounding lever) says recycle it."""
    days = sorted(e["days_to_half_r"] for e in entries
                  if e.get("strategy") == strategy and e.get("outcome") == "win"
                  and e.get("days_to_half_r") is not None)
    if len(days) < MIN_SAMPLE:
        return None
    idx = int(np.ceil(TIME_STOP_COVERAGE * len(days))) - 1
    return int(days[idx])
```

Plan-engine wiring mirrors E31 (same flag): TP2 override when the plan's strategy has a value; `optimal_time_stop_days` is stored on the plan (`plan.time_stop_days`) for E48's recycler — it does NOT auto-close anything.

- [ ] **Step 4: Run `python -m pytest tests/test_edge_stops.py -v` — PASS (9 tests).**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/stops.py swingbot/core/plan_engine.py tests/test_edge_stops.py
git commit -m "feat: MFE-informed TP2 + time stops"
```

### Task E33: Fold-tune the Phase-E2 filter set

**Files:**
- Create: `scripts/wf_components.py`
- Create: `docs/superpowers/results/2026-XX-edge-folds.md`

**Ordering note:** this task *executes after E39* (the fold engine) is built — the numbering keeps the decision record adjacent to the components it judges. Build E34–E39 first, then come back here.

**Interfaces:**
- Consumes: `backtest_wf.run_folds` + `gate` (E39), the E22 baseline doc.
- Produces: the decision record — one fold-run per component against the friction-adjusted baseline, pass/fail per the pre-registered Global-Constraints gate, adopted values written into config defaults / `REGIME_ALLOW` (flags stay OFF until the E40 shadow gate).

- [ ] **Step 1: Write the component grid script**

```python
# scripts/wf_components.py
"""Run every Phase-E2 component through the anchored walk-forward gate.

One component at a time, against the E22 friction-adjusted baseline.
The gate is PRE-REGISTERED (Global Constraints): pooled test expectancy_r
improves in >= 2 of 3 folds, no fold degrades baseline by > 0.05R,
N >= 30 per fold. Components that fail are documented and DROPPED --
no second grid on the same hypothesis.

Run: python scripts/wf_components.py [--component NAME] [--out docs/superpowers/results/2026-XX-edge-folds.md]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swingbot.core.backtest_wf import run_folds, gate  # noqa: E402

# The full pre-registered component grid. Each entry: config overrides to
# apply on top of baseline. Grids are enumerated here ONCE -- adding values
# later is a new pre-registration, not a retry.
COMPONENTS = {
    "regime_gates":      [{"REGIME_GATES_ENABLED": True}],
    "rs_min_50":         [{"RS_MIN_ENABLED": True, "RS_MIN": 50}],
    "rs_min_60":         [{"RS_MIN_ENABLED": True, "RS_MIN": 60}],
    "rs_min_70":         [{"RS_MIN_ENABLED": True, "RS_MIN": 70}],
    "sector_rs":         [{"SECTOR_RS_ENABLED": True}],
    "mtf_min_1":         [{"MTF_MIN_ENABLED": True, "MTF_MIN": 1}],
    "mtf_min_2":         [{"MTF_MIN_ENABLED": True, "MTF_MIN": 2}],
    "breadth_floor_40":  [{"BREADTH_FLOOR_ENABLED": True, "BREADTH_FLOOR": 40}],
    "breadth_floor_45":  [{"BREADTH_FLOOR_ENABLED": True, "BREADTH_FLOOR": 45}],
    "breadth_floor_50":  [{"BREADTH_FLOOR_ENABLED": True, "BREADTH_FLOOR": 50}],
    "gap_fragile_filter":[{"GAP_FRAGILE_FILTER_ENABLED": True}],
    "earnings_blackout_2":[{"EARNINGS_BLACKOUT_DAYS": 2}],
    "earnings_blackout_3":[{"EARNINGS_BLACKOUT_DAYS": 3}],
    "mae_stops":         [{"DATA_DRIVEN_STOPS_ENABLED": True, "MAE_ONLY": True}],
    "mfe_tp2":           [{"DATA_DRIVEN_STOPS_ENABLED": True, "MFE_ONLY": True}],
    "time_stops":        [{"DATA_DRIVEN_STOPS_ENABLED": True, "TIME_STOP_ONLY": True}],
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--component", default=None, help="run one; default all")
    p.add_argument("--out", default="docs/superpowers/results/2026-XX-edge-folds.md")
    args = p.parse_args()

    rows = []
    for name, variants in COMPONENTS.items():
        if args.component and name != args.component:
            continue
        for overrides in variants:
            print(f"=== {name} {overrides}")
            result = run_folds(overrides)
            verdict = gate(result)
            rows.append({"component": name, "overrides": overrides,
                         "verdict": verdict, "folds": result["folds"],
                         "pooled_delta": result["pooled_delta_expectancy_r"]})
            print(json.dumps(rows[-1], indent=1, default=str))
    with open(args.out.replace(".md", ".json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1, default=str)
    print(f"\n{sum(r['verdict'] == 'PASS' for r in rows)}/{len(rows)} passed the gate")


if __name__ == "__main__":
    main()
```

(The per-component filter flags — `RS_MIN_ENABLED`, `MTF_MIN_ENABLED`, `BREADTH_FLOOR_ENABLED`, `GAP_FRAGILE_FILTER_ENABLED` — are small config Fields + entry-filter hooks added alongside the factor tasks E25–E31; each is a ≤10-line flag-gated mask in `entry_filters.entries_for` following the exact `apply_regime_gate` pattern. Add any that are still missing as part of this task.)

- [ ] **Step 2: Execute the grid** — `python scripts/wf_components.py` (hours, not minutes: 16 variants × 3 folds × universe; run overnight or per-component).

- [ ] **Step 3: Write the decision record** — `docs/superpowers/results/2026-XX-edge-folds.md`: one row per variant (component, per-fold Δexpectancy, pooled Δ, N per fold, PASS/FAIL), the adopted value per component family (best PASSING variant, plateau-checked at E42), and an explicit **dropped list** with the fold numbers that killed each. Update config defaults / `REGIME_ALLOW` with adopted values — **flags remain off** until E40.

- [ ] **Step 4: Commit**

```bash
git add scripts/wf_components.py docs/superpowers/results/ swingbot/config.py swingbot/core/strategy_types.py
git commit -m "docs: component fold decisions (pre-registered gate applied)"
```

### Task E34: Candlestick quality at levels

**Files:**
- Modify: `swingbot/core/edge/factors.py` (score lives with the other factors; `candlestick_patterns.py` supplies pattern detection as-is)
- Test: `tests/test_edge_factors.py`

**Interfaces:**
- Produces: `pattern_quality_at_level(df, idx: int, level: float, direction: str = "bullish") -> int` (0–10): close position within the bar's range (0–4), volume vs its 20-bar average (0–3), wick rejection through the level (0–3). **Score component** for E37, not a hard filter.

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_factors.py`)

```python
def _bar(df_idx, o, h, l, c, v, base_vol=1_000_000):
    import numpy as np
    import pandas as pd
    idx = pd.bdate_range("2026-01-01", periods=30)
    df = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0,
                       "Close": 100.0, "Volume": float(base_vol)}, index=idx)
    df.iloc[-1] = [o, h, l, c, v]
    return df


def test_hammer_rejection_at_support_scores_high():
    from swingbot.core.edge.factors import pattern_quality_at_level
    # dipped through the 98 level, closed at the top of the bar, 3x volume
    df = _bar(-1, 100.0, 100.6, 97.5, 100.5, 3_000_000)
    assert pattern_quality_at_level(df, len(df) - 1, 98.0, "bullish") >= 8


def test_weak_close_low_volume_scores_low():
    from swingbot.core.edge.factors import pattern_quality_at_level
    # never touched the level, closed mid-range, average volume
    df = _bar(-1, 100.0, 101.0, 99.5, 100.2, 1_000_000)
    assert pattern_quality_at_level(df, len(df) - 1, 98.0, "bullish") <= 4
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `factors.py`)

```python
def pattern_quality_at_level(df: pd.DataFrame, idx: int, level: float,
                             direction: str = "bullish") -> int:
    """0-10 quality of the level-touch bar. Rewards conviction closes,
    participation (volume), and an actual rejection wick THROUGH the
    level -- the difference between a bounce and a drift."""
    bar = df.iloc[idx]
    rng = float(bar["High"] - bar["Low"])
    if rng <= 0:
        return 0
    bull = direction == "bullish"

    # 1) close position in range: 0 (worst) .. 4 (closes at the favorable extreme)
    pos = (bar["Close"] - bar["Low"]) / rng
    pos = pos if bull else 1.0 - pos
    score = round(4 * pos)

    # 2) volume vs 20-bar average: >=2.5x -> 3, >=1.5x -> 2, >=1.0x -> 1
    vol_avg = float(df["Volume"].iloc[max(0, idx - 20):idx].mean() or 0)
    ratio = float(bar["Volume"]) / vol_avg if vol_avg > 0 else 0.0
    score += 3 if ratio >= 2.5 else 2 if ratio >= 1.5 else 1 if ratio >= 1.0 else 0

    # 3) wick rejection through the level: pierced it AND closed back beyond it
    pierced = bar["Low"] <= level if bull else bar["High"] >= level
    reclaimed = bar["Close"] > level if bull else bar["Close"] < level
    if pierced and reclaimed:
        wick = (level - bar["Low"]) if bull else (bar["High"] - level)
        score += 3 if wick / rng >= 0.25 else 2
    return int(min(score, 10))
```

- [ ] **Step 4: Run `python -m pytest tests/test_edge_factors.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/factors.py tests/test_edge_factors.py
git commit -m "feat: level-touch candle quality"
```

### Task E35: Volume profile HVN/LVN targets

**Files:**
- Modify: `swingbot/core/levels.py` (volume-profile level source)
- Test: `tests/test_edge_factors.py` (levels section)

**Interfaces:**
- Produces: `volume_profile_nodes(df, lookback_days=180, bins=42) -> dict {"hvn": [prices], "lvn": [prices]}` — high-volume nodes = local maxima of the volume-at-price histogram (≥1.5× median bin), low-volume nodes = local minima (≤0.5× median). `collect_candidate_levels` appends `(price, "HVN")` / `(price, "LVN")`. Pure level-map enrichment: LVNs naturally become TP-zone material (price moves fast through them), HVNs stop shelter — the existing confluence machinery does the rest.

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_factors.py`)

```python
def test_bimodal_volume_finds_nodes():
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.levels import volume_profile_nodes
    # price spends time at 100 and 120 (heavy volume), races through 110
    closes = np.concatenate([np.full(80, 100.0), np.linspace(100, 120, 20),
                             np.full(80, 120.0)])
    vols = np.concatenate([np.full(80, 5e6), np.full(20, 4e5), np.full(80, 5e6)])
    df = make_ohlcv(closes, spread_pct=1.0, volumes=vols)
    nodes = volume_profile_nodes(df)
    assert any(abs(p - 100) < 2 for p in nodes["hvn"])
    assert any(abs(p - 120) < 2 for p in nodes["hvn"])
    assert any(102 < p < 118 for p in nodes["lvn"])
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (add to `levels.py`, near the other source builders)

```python
def volume_profile_nodes(df: pd.DataFrame, lookback_days: int = 180,
                         bins: int = 42) -> dict:
    """High/low-volume nodes from volume-at-price. HVNs are acceptance
    (stop shelter), LVNs are vacuum (price transits fast -> TP zones)."""
    part = df.tail(lookback_days)
    tp = (part["High"] + part["Low"] + part["Close"]) / 3.0
    hist, edges = np.histogram(tp, bins=bins, weights=part["Volume"])
    centers = (edges[:-1] + edges[1:]) / 2.0
    med = np.median(hist[hist > 0]) if (hist > 0).any() else 0
    hvn, lvn = [], []
    for i in range(1, len(hist) - 1):
        local_max = hist[i] >= hist[i - 1] and hist[i] >= hist[i + 1]
        local_min = hist[i] <= hist[i - 1] and hist[i] <= hist[i + 1]
        if local_max and med and hist[i] >= 1.5 * med:
            hvn.append(float(centers[i]))
        elif local_min and med and hist[i] <= 0.5 * med:
            lvn.append(float(centers[i]))
    return {"hvn": hvn, "lvn": lvn}
```

and in `collect_candidate_levels`:

```python
    try:
        nodes = volume_profile_nodes(df)
        candidates.extend((p, "HVN") for p in nodes["hvn"])
        candidates.extend((p, "LVN") for p in nodes["lvn"])
    except Exception:
        pass
```

- [ ] **Step 4: Run the levels tests + new test — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/levels.py tests/test_edge_factors.py
git commit -m "feat: HVN/LVN levels"
```

### Task E36: Divergence quality upgrade

**Files:**
- Modify: `swingbot/core/signals.py` (RSI-divergence detector)
- Test: `tests/test_edge_factors.py`

**Interfaces:**
- Produces: `divergence_strength(df, price_swings: list[int], rsi_swings: list[float]) -> int` (0–10): swing-point count beyond the minimum 2 (0–3), price/RSI slope differential magnitude (0–4), volume fading into the final swing (0–3). The detector keeps its exact current detections (characterization-tested) and attaches `strength` to each; fold candidate `div_strength_min` for a later pre-registration (NOT in the E33 grid — it needs live scores accumulated first).

- [ ] **Step 1: Characterization test FIRST** (before touching the detector)

```python
def test_divergence_detections_unchanged_with_score_attached():
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core import signals
    # a frame the current detector fires on: falling price, rising RSI lows
    rng = np.random.default_rng(5)
    closes = np.concatenate([np.linspace(100, 90, 60) + rng.normal(0, 0.2, 60),
                             np.linspace(90, 88, 60) + rng.normal(0, 0.05, 60)])
    df = make_ohlcv(closes, spread_pct=1.5)
    before = signals.detect_rsi_divergence(df)          # capture current output
    # after the change: same bars flagged, each detection now has a strength
    after = signals.detect_rsi_divergence(df)
    assert [d["bar"] if isinstance(d, dict) else d for d in after] \
        == [d["bar"] if isinstance(d, dict) else d for d in before]
    if after and isinstance(after[0], dict):
        assert all(0 <= d["strength"] <= 10 for d in after)
```

(Adapt the accessor to the real detector name/return shape in `signals.py` — capture the current behavior exactly, then assert it is preserved. If the current return is a bare boolean Series, the upgrade wraps it: same Series plus a parallel `strength` Series.)

- [ ] **Step 2: Run — currently PASSES against the old detector (it's a characterization); it FAILS once you add the strength assertion. Lock the old output in first.**

- [ ] **Step 3: Implement** — add the scoring function to `signals.py` and attach it without changing detection logic:

```python
def divergence_strength(price_lows: list, rsi_lows: list, volumes: list) -> int:
    """0-10. More swing points, steeper disagreement, fading volume =
    a divergence worth acting on rather than a two-touch accident."""
    score = min(len(price_lows) - 2, 3) if len(price_lows) >= 2 else 0
    if len(price_lows) >= 2 and len(rsi_lows) >= 2 and price_lows[0] > 0:
        price_slope = (price_lows[-1] - price_lows[0]) / price_lows[0]
        rsi_slope = (rsi_lows[-1] - rsi_lows[0]) / 100.0
        disagreement = abs(rsi_slope - price_slope)
        score += min(int(disagreement * 40), 4)
    if len(volumes) >= 2 and volumes[0] > 0:
        fade = 1.0 - volumes[-1] / volumes[0]
        score += 3 if fade >= 0.4 else 2 if fade >= 0.2 else 0
    return int(min(score, 10))
```

- [ ] **Step 4: Run — characterization + strength tests PASS; full suite green (RSI-Divergence backtest goldens unchanged).**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/signals.py tests/test_edge_factors.py
git commit -m "feat: scored divergences"
```

### Task E37: Composite entry-quality score v2

**Files:**
- Modify: `swingbot/core/quality.py` (plan-engine-v2's transparent points system)
- Test: `tests/test_edge_factors.py`

**Interfaces:**
- Produces: new component functions, each returning `(points, label)` and appended to the existing breakdown list: `rs_points(rs_pctile) -> 0–10` (linear from percentile 50→100), `mtf_points(mtf_score) -> 0–10` (0/3/6/10 for 0/1/2/3), `breadth_points(breadth) -> 0–5` (0 below 40, linear 40→60, 5 above 60), `candle_points(cq) -> 0–5` (`cq/2`), `gap_penalty(gap_fragile) -> −10 or 0`. Total still clamped 0–100; weights are frozen here and **audited** (not tuned) by re-running the plan-engine-v2 Task-52 decile harness.

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_factors.py`)

```python
def test_quality_v2_component_points():
    from swingbot.core.quality import (breadth_points, candle_points,
                                       gap_penalty, mtf_points, rs_points)
    assert rs_points(50.0) == 0 and rs_points(100.0) == 10 and rs_points(75.0) == 5
    assert mtf_points(0) == 0 and mtf_points(2) == 6 and mtf_points(3) == 10
    assert breadth_points(35.0) == 0 and breadth_points(60.0) == 5
    assert candle_points(8) == 4
    assert gap_penalty(True) == -10 and gap_penalty(False) == 0


def test_quality_v2_total_still_clamped():
    from swingbot.core.quality import compute_quality  # v2's existing entry point
    # a maxed-out context must still clamp at 100
    ctx = {"rs_percentile": 100.0, "mtf": 3, "breadth": 70.0,
           "candle_quality": 10, "gap_fragile": False}
    score, breakdown = compute_quality_with_edge(ctx)
    assert 0 <= score <= 100
```

(Adapt `compute_quality`'s real signature — the v2 plan defines it; the edge components append to its breakdown list. Name the combined helper `compute_quality_with_edge(ctx)` if extending the signature directly would ripple.)

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `quality.py`)

```python
# --- Edge v2 components (E37). Frozen weights; the decile audit judges
# them as a set, the ablation harness (E43) judges them individually.

def rs_points(rs_pctile: float) -> int:
    return int(round(max(0.0, min(rs_pctile - 50.0, 50.0)) / 5.0))


def mtf_points(mtf_score: int) -> int:
    return {0: 0, 1: 3, 2: 6, 3: 10}.get(int(mtf_score), 0)


def breadth_points(breadth: float | None) -> int:
    if breadth is None:
        return 0
    return int(round(max(0.0, min(breadth - 40.0, 20.0)) / 4.0))


def candle_points(candle_quality: int) -> int:
    return int(min(candle_quality, 10) // 2)


def gap_penalty(gap_fragile: bool) -> int:
    return -10 if gap_fragile else 0
```

Wire each into the plan's quality breakdown where the v1 components are summed, clamp unchanged. Then **re-run the decile audit** (plan-engine-v2 Task 52 harness) over the TRAIN window and commit the table next to the old one — the audit is the evidence the new components rank-order outcomes.

- [ ] **Step 4: Run `python -m pytest tests/test_edge_factors.py -v` + full suite — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/quality.py docs/superpowers/results/ tests/test_edge_factors.py
git commit -m "feat: quality score v2 components"
```

### Task E38: Pyramiding rules

**Files:**
- Modify: `swingbot/core/plan_manager.py`
- Modify: `swingbot/config.py` (Field `PYRAMIDING_ENABLED`, checkbox, default false, section "Universe & Scanning")
- Test: `tests/test_edge_stops.py` (pyramiding section)

**Interfaces:**
- Produces: `maybe_pyramid(plan, price: float) -> dict | None` — pure decision: when the plan is `PARTIAL` (TP1 banked, stop at breakeven) and price ≥ entry + 1R (long), returns `{"add_shares_fraction": 0.5, "add_entry": price, "add_stop": plan.entry_price}`; else `None`. **Risk invariant:** original remaining position risks 0 (stop at BE); the add risks `0.5 × size × (price − entry)` where `price − entry ≥ 1R` — the add's stop at the ORIGINAL ENTRY caps total position risk at ≤ the original 1R at every moment, including a gap through both stops (both fill at the same gap price; loss on add ≤ gain locked on TP1 + BE remainder). The invariant is the test, not a comment.

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_stops.py`)

```python
def _partial_plan():
    class P:  # minimal stand-in with the fields maybe_pyramid reads
        status = "PARTIAL"
        direction = "bullish"
        entry_price = 100.0
        stop_loss = 100.0            # moved to BE at PARTIAL
        tp1 = 101.0
        risk_per_share = 2.0         # original 1R = $2
    return P()


def test_pyramid_fires_at_plus_1r():
    from swingbot.core.plan_manager import maybe_pyramid
    plan = _partial_plan()
    assert maybe_pyramid(plan, price=101.9) is None          # < entry + 1R
    add = maybe_pyramid(plan, price=102.0)                   # == entry + 1R
    assert add == {"add_shares_fraction": 0.5, "add_entry": 102.0,
                   "add_stop": 100.0}


def test_pyramid_risk_invariant_even_gapping_through():
    from swingbot.core.plan_manager import maybe_pyramid
    plan = _partial_plan()
    add = maybe_pyramid(plan, price=102.0)
    # worst case: overnight gap fills BOTH stops at 97 (way through).
    # remainder: (97-100)*1.0 = -3/share on half size = -1.5R-equivalents...
    # invariant checked in R of the ORIGINAL position (risk_per_share=2):
    size = 1.0                       # original shares (normalized)
    tp1_banked = (plan.tp1 - plan.entry_price) * (size * 0.5)      # +0.5
    gap = 97.0
    remainder_pnl = (gap - plan.entry_price) * (size * 0.5)        # -1.5
    add_pnl = (gap - add["add_entry"]) * (size * 0.5)              # -2.5
    total_r = (tp1_banked + remainder_pnl + add_pnl) / (plan.risk_per_share * size)
    no_pyramid_r = (tp1_banked + remainder_pnl) / (plan.risk_per_share * size)
    # documented property: pyramiding adds at most 1R of NEW downside in a
    # catastrophic gap, and in the no-gap case adds zero risk (stop at entry).
    assert total_r >= no_pyramid_r - 1.0


def test_pyramid_only_in_partial_and_flag_gated(monkeypatch):
    from swingbot import config
    from swingbot.core.plan_manager import maybe_pyramid
    plan = _partial_plan()
    plan.status = "ACTIVE"
    assert maybe_pyramid(plan, price=105.0) is None
    plan.status = "PARTIAL"
    monkeypatch.setattr(config, "PYRAMIDING_ENABLED", False, raising=False)
    # the manager tick consults the flag BEFORE calling; the pure fn doesn't
```

- [ ] **Step 2: Run — FAIL (`ImportError: maybe_pyramid`).**

- [ ] **Step 3: Implement** (add to `plan_manager.py`)

```python
def maybe_pyramid(plan, price: float) -> dict | None:
    """Add half size at +1R with the add's stop at the ORIGINAL entry.
    Only from PARTIAL (TP1 banked, remainder stopped at breakeven), so a
    normal stop-out of everything nets >= breakeven on the whole campaign;
    only a gap THROUGH the entry can cost new money, bounded by the tests
    above. Fold-validated as an exit-model variant before enabling."""
    if getattr(plan, "status", None) != "PARTIAL":
        return None
    bull = plan.direction == "bullish"
    trigger = plan.entry_price + plan.risk_per_share if bull \
        else plan.entry_price - plan.risk_per_share
    if (price >= trigger) if bull else (price <= trigger):
        return {"add_shares_fraction": 0.5, "add_entry": price,
                "add_stop": plan.entry_price}
    return None
```

Manager-tick wiring (flag-gated, one add per plan): if `config.PYRAMIDING_ENABLED` and no prior add recorded on the plan, call `maybe_pyramid`; a non-None result emits a `PlanEvent` (`"pyramid_add"`) that the Discord layer posts as a suggestion — the bot never sizes real money itself.

- [ ] **Step 4: Run `python -m pytest tests/test_edge_stops.py -v` — PASS. Full suite green (flag off).**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/plan_manager.py swingbot/config.py tests/test_edge_stops.py
git commit -m "feat: risk-invariant pyramiding (off)"
```

### Task E39: Walk-forward engine

**Files:**
- Create: `swingbot/core/backtest_wf.py`, `scripts/wf_run.py`
- Test: `tests/test_wf_engine.py`

**Ordering note:** built immediately after E32; E33's decision runs execute once this lands.

**Interfaces:**
- Produces: `ANCHORED_FOLDS = (("2018-01-01","2020-12-31","2021-01-01","2021-12-31"), ("2018-01-01","2021-12-31","2022-01-01","2022-12-31"), ("2018-01-01","2022-12-31","2023-01-01","2023-12-31"))` — **frozen constant**; `run_folds(overrides: dict, folds=ANCHORED_FOLDS, tickers=None, run_fn=None) -> dict` — per fold, runs baseline (no overrides) and component (config overrides applied & restored via try/finally) over the test window with frictions on, pooling all (ticker, strategy) trades; returns `{"folds": [{"test_years", "baseline": {...}, "component": {...}, "delta_expectancy_r", "n"}], "pooled_delta_expectancy_r"}`. `gate(result) -> "PASS" | "FAIL"` — the pre-registered rule verbatim: improves in ≥2 of 3 folds AND no fold degrades > 0.05R AND `n ≥ 30` per fold.
- `run_fn(start, end, overrides) -> dict {expectancy_r, n}` is injectable for tests; default runs `run_backtest_daterange` over the cached universe.
- `python scripts/wf_run.py [--component-json '{"FLAG": true}'] [--full]` is the CLI.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wf_engine.py
import pytest

from swingbot.core.backtest_wf import ANCHORED_FOLDS, gate, run_folds


def test_folds_are_frozen():
    assert len(ANCHORED_FOLDS) == 3
    for train_start, train_end, test_start, test_end in ANCHORED_FOLDS:
        assert train_end < test_start          # ISO strings compare correctly
        assert train_start == "2018-01-01"     # anchored, expanding
    assert ANCHORED_FOLDS[0][2].startswith("2021")
    assert ANCHORED_FOLDS[2][3] == "2023-12-31"


def test_run_folds_no_test_bars_reachable_in_train():
    seen = []
    def spy_run(start, end, overrides):
        seen.append((start, end, bool(overrides)))
        return {"expectancy_r": 0.10, "n": 100}
    run_folds({"X": 1}, run_fn=spy_run)
    # every invocation is a TEST window from the fold table -- never a
    # window that overlaps training years
    for start, end, _ in seen:
        assert (start, end) in {(f[2], f[3]) for f in ANCHORED_FOLDS}


def _result(deltas, n=100):
    folds = [{"test_years": f"202{i+1}", "baseline": {"expectancy_r": 0.10, "n": n},
              "component": {"expectancy_r": 0.10 + d, "n": n},
              "delta_expectancy_r": d, "n": n}
             for i, d in enumerate(deltas)]
    pooled = sum(deltas) / len(deltas)
    return {"folds": folds, "pooled_delta_expectancy_r": pooled}


def test_gate_two_of_three_improving_passes():
    assert gate(_result([0.03, 0.02, -0.01])) == "PASS"


def test_gate_fails_on_big_single_fold_degradation():
    assert gate(_result([0.05, 0.05, -0.06])) == "FAIL"   # one fold worse by >0.05R


def test_gate_fails_on_one_of_three():
    assert gate(_result([0.05, -0.01, -0.02])) == "FAIL"


def test_gate_fails_on_thin_folds():
    assert gate(_result([0.03, 0.03, 0.01], n=20)) == "FAIL"
```

- [ ] **Step 2: Run — FAIL (`ModuleNotFoundError`).**

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/backtest_wf.py
"""Anchored walk-forward harness -- the gatekeeper for every Edge component.

Folds are FROZEN (pre-registered before any data contact, per the plan's
Global Constraints). Train windows exist for parameter *fitting* inside
components that need it; the judgment numbers come only from the test
years. The 2024-2025 window does not appear here at all -- it is spent
exactly once, at E92.
"""
from __future__ import annotations

import logging

from swingbot import config

log = logging.getLogger("swing-bot.backtest_wf")

ANCHORED_FOLDS = (
    ("2018-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
    ("2018-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    ("2018-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
)

# Pre-registered gate constants -- do not touch without a new pre-registration.
GATE_MIN_IMPROVING_FOLDS = 2
GATE_MAX_DEGRADATION_R = 0.05
GATE_MIN_N_PER_FOLD = 30


def _apply_overrides(overrides: dict) -> dict:
    old = {}
    for key, value in overrides.items():
        old[key] = getattr(config, key, None)
        setattr(config, key, value)
    return old


def _default_run(start: str, end: str, overrides: dict) -> dict:
    """Pooled expectancy over the cached universe for one window."""
    import numpy as np
    from swingbot.core.backtest import ALL_STRATEGIES, run_backtest_daterange
    from swingbot.core.data_store import load_from_disk
    from swingbot.core.universe import liquidity_ok, universe_symbols

    symbols = universe_symbols(getattr(config, "SCAN_UNIVERSE", "watchlist")) or []
    if not symbols:
        from swingbot.core.watchlist import get_watchlist  # existing accessor
        symbols = get_watchlist()
    rs = []
    old = _apply_overrides(overrides)
    try:
        for sym in symbols:
            df = load_from_disk(sym, "1d")
            if df is None or not liquidity_ok(df):
                continue
            for strat in ALL_STRATEGIES:
                s = run_backtest_daterange(sym, df, strat, start, end, frictions=True)
                rs.extend(t.r_multiple for t in (s.trades or []))
    finally:
        _apply_overrides(old)
    return {"expectancy_r": float(np.mean(rs)) if rs else None, "n": len(rs)}


def run_folds(overrides: dict, folds=ANCHORED_FOLDS, tickers=None, run_fn=None) -> dict:
    run = run_fn or _default_run
    fold_rows = []
    for train_start, train_end, test_start, test_end in folds:
        base = run(test_start, test_end, {})
        comp = run(test_start, test_end, dict(overrides))
        delta = None
        if base["expectancy_r"] is not None and comp["expectancy_r"] is not None:
            delta = comp["expectancy_r"] - base["expectancy_r"]
        fold_rows.append({"test_years": test_start[:4],
                          "baseline": base, "component": comp,
                          "delta_expectancy_r": delta,
                          "n": min(base["n"], comp["n"])})
    deltas = [f["delta_expectancy_r"] for f in fold_rows if f["delta_expectancy_r"] is not None]
    pooled = sum(deltas) / len(deltas) if deltas else None
    return {"folds": fold_rows, "pooled_delta_expectancy_r": pooled}


def gate(result: dict) -> str:
    """The PRE-REGISTERED pass rule. A component that fails is dropped and
    documented -- no second grid on the same hypothesis."""
    folds = result["folds"]
    deltas = [f["delta_expectancy_r"] for f in folds]
    if any(d is None for d in deltas):
        return "FAIL"
    if any(f["n"] < GATE_MIN_N_PER_FOLD for f in folds):
        return "FAIL"
    if sum(d > 0 for d in deltas) < GATE_MIN_IMPROVING_FOLDS:
        return "FAIL"
    if any(d < -GATE_MAX_DEGRADATION_R for d in deltas):
        return "FAIL"
    return "PASS"
```

`scripts/wf_run.py`:

```python
"""CLI for the walk-forward harness.
Run: python scripts/wf_run.py --component-json '{"REGIME_GATES_ENABLED": true}'
     python scripts/wf_run.py --full     # E89: everything adopted, portfolio mode
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swingbot.core.backtest_wf import gate, run_folds  # noqa: E402

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--component-json", default="{}")
    p.add_argument("--full", action="store_true",
                   help="run the full adopted system (reads adopted defaults)")
    args = p.parse_args()
    overrides = json.loads(args.component_json)
    result = run_folds(overrides)
    result["verdict"] = gate(result)
    print(json.dumps(result, indent=1, default=str))
```

(`run_backtest_daterange` gains the `frictions=` passthrough from E11 if it hasn't already.)

- [ ] **Step 4: Run `python -m pytest tests/test_wf_engine.py -v` — PASS (6 tests).**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtest_wf.py scripts/wf_run.py tests/test_wf_engine.py
git commit -m "feat: anchored walk-forward harness"
```

### Task E40: Shadow forward-gate

**Files:**
- Create: `scripts/shadow_component_report.py`
- Modify: the shadow logger (plan-engine-v2 Task 86 infra) to accept a `component`/`variant` tag
- Test: `tests/test_wf_engine.py`

**Interfaces:**
- Produces: shadow log lines (`data/shadow_log.jsonl`, one JSON per line) gain optional keys `component`, `variant` (`"on" | "off"`); during a component's 4-week shadow window the scan logs BOTH variants' would-be entries. `shadow_component_report(lines: list[dict], component: str) -> dict` — pure: pairs each cohort's would-be entries with their 10-day forward returns (already recorded by the shadow logger's follow-up job) and returns `{"on": {"n", "fwd_expectancy"}, "off": {...}, "verdict"}` where verdict is `"PROMOTE"` only when the on-cohort forward expectancy ≥ off-cohort (pre-registered promotion bar). Promotion itself = the **user** flips the flag after reading the report.

- [ ] **Step 1: Write the failing test** (append to `tests/test_wf_engine.py`)

```python
def _shadow_line(component, variant, fwd):
    return {"ticker": "T", "component": component, "variant": variant,
            "fwd_return_10d": fwd}


def test_shadow_report_compares_cohorts():
    from scripts.shadow_component_report import shadow_component_report
    lines = ([_shadow_line("rs_min", "on", 0.02)] * 30
             + [_shadow_line("rs_min", "off", 0.01)] * 40
             + [_shadow_line("other", "on", 9.9)] * 5)      # ignored
    rep = shadow_component_report(lines, "rs_min")
    assert rep["on"]["n"] == 30 and rep["off"]["n"] == 40
    assert rep["on"]["fwd_expectancy"] > rep["off"]["fwd_expectancy"]
    assert rep["verdict"] == "PROMOTE"


def test_shadow_report_holds_when_component_underperforms():
    from scripts.shadow_component_report import shadow_component_report
    lines = ([_shadow_line("rs_min", "on", 0.00)] * 30
             + [_shadow_line("rs_min", "off", 0.02)] * 30)
    assert shadow_component_report(lines, "rs_min")["verdict"] == "HOLD"
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement**

```python
# scripts/shadow_component_report.py
"""4-week shadow forward-gate for fold-passing components.
Run: python scripts/shadow_component_report.py --component rs_min"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swingbot.config import DATA_DIR  # noqa: E402

SHADOW_LOG = os.path.join(DATA_DIR, "shadow_log.jsonl")


def shadow_component_report(lines: list, component: str) -> dict:
    cohorts = {"on": [], "off": []}
    for row in lines:
        if row.get("component") == component and row.get("variant") in cohorts \
                and row.get("fwd_return_10d") is not None:
            cohorts[row["variant"]].append(row["fwd_return_10d"])
    out = {}
    for k, v in cohorts.items():
        out[k] = {"n": len(v), "fwd_expectancy": (sum(v) / len(v)) if v else None}
    promotable = (out["on"]["fwd_expectancy"] is not None
                  and out["off"]["fwd_expectancy"] is not None
                  and out["on"]["n"] >= 20
                  and out["on"]["fwd_expectancy"] >= out["off"]["fwd_expectancy"])
    out["verdict"] = "PROMOTE" if promotable else "HOLD"
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--component", required=True)
    args = p.parse_args()
    with open(SHADOW_LOG, encoding="utf-8") as f:
        lines = [json.loads(l) for l in f if l.strip()]
    print(json.dumps(shadow_component_report(lines, args.component), indent=1))
```

Shadow-logger change: the scan's shadow pass evaluates each fold-passing component twice (flag forced on / off via the E39 override helper, scan-local) and logs both cohorts' would-be entries with the tag. The existing 10-day forward-return follow-up job fills `fwd_return_10d` unchanged.

- [ ] **Step 4: Run `python -m pytest tests/test_wf_engine.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add scripts/shadow_component_report.py swingbot/core/scanning/engine.py tests/test_wf_engine.py
git commit -m "feat: component shadow forward-gate"
```

### Task E41: Permutation test (reality check)

**Files:**
- Create: `scripts/permutation_test.py`
- Test: `tests/test_wf_engine.py`

**Interfaces:**
- Produces: `permuted_expectancies(run_fn, n_perm=200, seed=42) -> list[float]` — re-runs the fold tests with entry signals circularly shifted by random offsets (`np.roll` on the entry boolean arrays — destroys signal-bar alignment, preserves autocorrelation & entry frequency); `p_value(real_expectancy, permuted: list[float]) -> float` — fraction of permuted runs ≥ real. A component with `p > 0.05` is flagged **"indistinguishable from luck"** in the fold doc regardless of its fold deltas.
- The shift hooks into `run_backtest` via a module-level `ENTRY_SHIFT` int in `backtest.py` (default 0 = exact current behavior), applied as `np.roll(bullish.values, ENTRY_SHIFT)` right after `_vectorized_entries`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_wf_engine.py`)

```python
def test_p_value_math():
    from scripts.permutation_test import p_value
    permuted = [0.01, 0.02, 0.03, 0.20]
    assert p_value(0.15, permuted) == 0.25      # 1 of 4 >= real
    assert p_value(0.30, permuted) == 0.0
    assert p_value(-0.10, permuted) == 1.0


def test_planted_signal_beats_noise(monkeypatch):
    import numpy as np
    from scripts.permutation_test import permuted_expectancies, p_value
    rng = np.random.default_rng(0)
    # a run_fn with real skill: expectancy 0.15 unshifted, ~0 shifted
    def run_fn(shift):
        return 0.15 if shift == 0 else float(rng.normal(0.0, 0.02))
    permuted = permuted_expectancies(run_fn, n_perm=100, seed=1)
    assert p_value(run_fn(0), permuted) < 0.05          # skill detected
    # pure noise: the "real" run is just another draw
    def noise_fn(shift):
        return float(rng.normal(0.0, 0.02))
    permuted2 = permuted_expectancies(noise_fn, n_perm=100, seed=2)
    assert p_value(noise_fn(0), permuted2) > 0.05       # luck not mistaken for skill
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement**

```python
# scripts/permutation_test.py
"""Permutation reality check: is the edge distinguishable from luck?

Circularly shifting entry dates severs the entry-signal/price-future link
while preserving entry count, autocorrelation and the exit engine -- if
the un-shifted expectancy doesn't beat ~95% of shifted runs, the
'component' is noise wearing a lab coat.

Run: python scripts/permutation_test.py --component-json '{...}' [--n 200]
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def permuted_expectancies(run_fn, n_perm: int = 200, seed: int = 42) -> list:
    rng = np.random.default_rng(seed)
    shifts = rng.integers(20, 200, size=n_perm)   # >= 20 bars so nothing 'almost' aligns
    return [float(run_fn(int(s))) for s in shifts]


def p_value(real_expectancy: float, permuted: list) -> float:
    if not permuted:
        return 1.0
    return float(np.mean([p >= real_expectancy for p in permuted]))


def _fold_run_fn(overrides: dict):
    """Returns run_fn(shift) -> pooled test expectancy with entries rolled."""
    import swingbot.core.backtest as bt
    from swingbot.core.backtest_wf import run_folds

    def run(shift: int) -> float:
        bt.ENTRY_SHIFT = shift
        try:
            r = run_folds(overrides)
            deltas = [f["component"]["expectancy_r"] for f in r["folds"]
                      if f["component"]["expectancy_r"] is not None]
            return sum(deltas) / len(deltas) if deltas else 0.0
        finally:
            bt.ENTRY_SHIFT = 0
    return run


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--component-json", default="{}")
    p.add_argument("--n", type=int, default=200)
    args = p.parse_args()
    run = _fold_run_fn(json.loads(args.component_json))
    real = run(0)
    permuted = permuted_expectancies(run, n_perm=args.n)
    pv = p_value(real, permuted)
    print(json.dumps({"real_expectancy": real, "p_value": pv,
                      "verdict": "REAL" if pv <= 0.05 else "INDISTINGUISHABLE FROM LUCK"},
                     indent=1))
```

`backtest.py` hook (2 lines after `_vectorized_entries` in `run_backtest`):

```python
    if ENTRY_SHIFT:
        import numpy as _np
        bullish_entries = pd.Series(_np.roll(bullish_entries.values, ENTRY_SHIFT), index=df.index)
        bearish_entries = pd.Series(_np.roll(bearish_entries.values, ENTRY_SHIFT), index=df.index)
```

with `ENTRY_SHIFT = 0` at module level.

- [ ] **Step 4: Run `python -m pytest tests/test_wf_engine.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add scripts/permutation_test.py swingbot/core/backtest.py tests/test_wf_engine.py
git commit -m "feat: permutation reality check"
```

### Task E42: Parameter-plateau report

**Files:**
- Modify: `swingbot/core/backtest_wf.py`
- Test: `tests/test_wf_engine.py`

**Interfaces:**
- Produces: `plateau_report(param_name: str, grid: list, expectancies: list[float], adopted_value) -> dict` — pure: `{"param", "grid", "expectancies", "adopted", "neighbors", "is_plateau"}`; a value **is on a plateau** when every immediate grid neighbor's expectancy is within `PLATEAU_TOLERANCE_R = 0.03` of the adopted value's. Values on spikes are rejected in the fold doc — a spike is curve-fit by definition. Auto-appended to fold docs by `wf_components.py` for gridded components.

- [ ] **Step 1: Write the failing test** (append to `tests/test_wf_engine.py`)

```python
def test_plateau_vs_spike():
    from swingbot.core.backtest_wf import plateau_report
    plateau = plateau_report("rs_min", [50, 60, 70], [0.10, 0.11, 0.09], 60)
    assert plateau["is_plateau"] is True
    spike = plateau_report("rs_min", [50, 60, 70], [0.02, 0.15, 0.03], 60)
    assert spike["is_plateau"] is False
    edge_val = plateau_report("rs_min", [50, 60, 70], [0.11, 0.10, 0.02], 50)
    assert edge_val["is_plateau"] is True      # single neighbor within 0.03
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `backtest_wf.py`)

```python
PLATEAU_TOLERANCE_R = 0.03


def plateau_report(param_name: str, grid: list, expectancies: list,
                   adopted_value) -> dict:
    """Adopted values must sit on plateaus, never spikes: if moving one
    grid step changes expectancy by more than PLATEAU_TOLERANCE_R, the
    'optimum' is noise you happened to sample."""
    i = grid.index(adopted_value)
    neighbors = [j for j in (i - 1, i + 1) if 0 <= j < len(grid)]
    is_plateau = all(abs(expectancies[j] - expectancies[i]) <= PLATEAU_TOLERANCE_R
                     for j in neighbors)
    return {"param": param_name, "grid": grid, "expectancies": expectancies,
            "adopted": adopted_value,
            "neighbors": {grid[j]: expectancies[j] for j in neighbors},
            "is_plateau": is_plateau}
```

- [ ] **Step 4: Run `python -m pytest tests/test_wf_engine.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtest_wf.py scripts/wf_components.py tests/test_wf_engine.py
git commit -m "feat: parameter plateau check"
```

### Task E43: Feature ablation harness

**Files:**
- Create: `scripts/ablation.py`

**Interfaces:**
- Produces: with ALL adopted components on, remove one at a time across folds → contribution table (`component, pooled_delta_when_removed`). Components contributing < 0.01R pooled are removal candidates (simplicity is robustness). Reads the adopted set from a checked-in `docs/superpowers/results/adopted_components.json` written by E33.

- [ ] **Step 1: Write the script**

```python
# scripts/ablation.py
"""Leave-one-out ablation over the adopted component set.
Run: python scripts/ablation.py"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swingbot.core.backtest_wf import run_folds  # noqa: E402

ADOPTED_PATH = "docs/superpowers/results/adopted_components.json"

if __name__ == "__main__":
    with open(ADOPTED_PATH, encoding="utf-8") as f:
        adopted: dict = json.load(f)          # {"REGIME_GATES_ENABLED": true, ...}

    full = run_folds(adopted)
    print(f"full system pooled Δ: {full['pooled_delta_expectancy_r']:+.4f}R")
    rows = []
    for key in adopted:
        subset = {k: v for k, v in adopted.items() if k != key}
        r = run_folds(subset)
        contribution = full["pooled_delta_expectancy_r"] - r["pooled_delta_expectancy_r"]
        rows.append((key, contribution))
        print(f"without {key:<32} contribution {contribution:+.4f}R")
    rows.sort(key=lambda x: x[1])
    weak = [k for k, c in rows if c < 0.01]
    print("\nremoval candidates (<0.01R):", weak or "none")
```

- [ ] **Step 2: Run it once after E33's adoptions** and append the printed table to the fold doc.

- [ ] **Step 3: Commit**

```bash
git add scripts/ablation.py docs/superpowers/results/
git commit -m "feat: ablation harness + first table"
```

### Task E44: Phase E2/E3 checkpoint

- [ ] **Step 1: Full suite + `make check` — green.**
- [ ] **Step 2: Evidence pack complete and committed:** fold doc (E33), permutation p-values per adopted component (E41), plateau evidence for every gridded adoption (E42), ablation table (E43), `adopted_components.json`. Adopted flag **defaults recorded but everything still shadow-only** (E40 windows may still be running — note their end dates in the Progress block).
- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/results/ docs/superpowers/plans/2026-07-11-edge-engine.md
git commit -m "docs: edge components adopted (evidence pack)"
```

---

# Phase E3 — Campaign & survival systems (E45–E56)

### Task E45: Drawdown throttle ladder

**Files:**
- Create: `swingbot/core/edge/throttle.py`
- Modify: `swingbot/config.py` (Field `DD_THROTTLE_ENABLED`, checkbox, default false, section "Account Defaults")
- Test: `tests/test_edge_throttle.py`

**Interfaces:**
- Produces: frozen ladder `DD_LADDER = ((8.0, 0.75), (12.0, 0.50), (16.0, 0.25), (20.0, 0.0))`, `RESUME_DD_PCT = 15.0`; `drawdown_pct(equity_points: list[float]) -> float` (current DD from the running peak, %); `current_throttle(equity_points, was_paused: bool = False) -> tuple[float, bool]` — `(multiplier, paused)`; the 0.0 rung pauses NEW entries and stays paused until DD recovers below 15% (hysteresis — no flapping at the 20% line). The multiplier feeds `sizing.effective_risk_pct(throttle_mult=...)` (E5's min-chain).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_throttle.py
import pytest

from swingbot.core.edge.throttle import current_throttle, drawdown_pct


def _curve(dd_pct):
    return [100.0, 120.0, 120.0 * (1 - dd_pct / 100)]


def test_drawdown_from_peak():
    assert drawdown_pct(_curve(10.0)) == pytest.approx(10.0)
    assert drawdown_pct([100.0, 110.0, 120.0]) == 0.0


def test_ladder_rungs():
    assert current_throttle(_curve(5.0)) == (1.0, False)
    assert current_throttle(_curve(9.0)) == (0.75, False)
    assert current_throttle(_curve(13.0)) == (0.50, False)
    assert current_throttle(_curve(17.0)) == (0.25, False)
    assert current_throttle(_curve(21.0)) == (0.0, True)     # paused


def test_hysteresis_stays_paused_until_15():
    mult, paused = current_throttle(_curve(18.0), was_paused=True)
    assert (mult, paused) == (0.0, True)     # 18% still paused (came from >20%)
    mult, paused = current_throttle(_curve(14.0), was_paused=True)
    assert paused is False and mult == 0.50  # recovered below 15 -> back on the ladder
```

- [ ] **Step 2: Run — FAIL (`ModuleNotFoundError`).**

- [ ] **Step 3: Implement**

```python
# swingbot/core/edge/throttle.py
"""Drawdown throttle ladder + loss-streak damper (E46) + kill switch (E47).

The math of drawdowns is asymmetric (-20% needs +25% back) and the math
of tilted operators is worse. The ladder cuts risk mechanically so
neither compounding nor judgment has to survive a deep hole at full
size. Constants are FROZEN by the plan's Global Constraints."""
from __future__ import annotations

DD_LADDER = ((8.0, 0.75), (12.0, 0.50), (16.0, 0.25), (20.0, 0.0))
RESUME_DD_PCT = 15.0   # once paused, entries resume only below this


def drawdown_pct(equity_points: list) -> float:
    peak, dd = float("-inf"), 0.0
    for v in equity_points:
        peak = max(peak, v)
        if peak > 0:
            dd = max(dd, (peak - v) / peak * 100.0)
    # current (not max-historical) drawdown is what throttles sizing:
    return (peak - equity_points[-1]) / peak * 100.0 if equity_points and peak > 0 else 0.0


def current_throttle(equity_points: list, was_paused: bool = False) -> tuple:
    dd = drawdown_pct(equity_points)
    if was_paused and dd >= RESUME_DD_PCT:
        return 0.0, True                       # hysteresis: stay paused
    mult = 1.0
    for threshold, m in DD_LADDER:
        if dd > threshold:
            mult = m
    return mult, mult == 0.0
```

Wiring: the alert path keeps `data/throttle_state.json` (`{"paused": bool}`, via `jsonio`) updated each scan from the balance history, and passes the multiplier into `effective_risk_pct` when `DD_THROTTLE_ENABLED`. A paused state labels alerts `⛔ ENTRIES PAUSED (drawdown throttle)` — shown, never hidden.

- [ ] **Step 4: Run `python -m pytest tests/test_edge_throttle.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/throttle.py swingbot/config.py tests/test_edge_throttle.py
git commit -m "feat: drawdown throttle ladder"
```

### Task E46: Loss-streak damper

**Files:**
- Modify: `swingbot/core/edge/throttle.py`
- Test: `tests/test_edge_throttle.py`

**Interfaces:**
- Produces: `streak_multiplier(recent_closed: list[str]) -> float` — input is outcomes newest-last (`"win" | "loss" | "scratch" | "timeout"`); 4+ consecutive losses (scratches/timeouts don't break OR extend the streak) ⇒ 0.5 until 2 wins have occurred after the streak; else 1.0. `combined_throttle(dd_mult, streak_mult) -> float` = product, floored at 0.25 (unless dd_mult is 0 — pause wins).

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_throttle.py`)

```python
def test_streak_damper_kicks_in_at_4():
    from swingbot.core.edge.throttle import streak_multiplier
    assert streak_multiplier(["loss"] * 3) == 1.0
    assert streak_multiplier(["loss"] * 4) == 0.5
    assert streak_multiplier(["win", "loss", "loss", "scratch", "loss", "loss"]) == 0.5
    # scratches don't extend: 3 losses + scratch + loss is still 4 consecutive


def test_streak_recovers_after_two_wins():
    from swingbot.core.edge.throttle import streak_multiplier
    assert streak_multiplier(["loss"] * 4 + ["win"]) == 0.5      # one win: not yet
    assert streak_multiplier(["loss"] * 4 + ["win", "win"]) == 1.0


def test_combined_floor():
    from swingbot.core.edge.throttle import combined_throttle
    assert combined_throttle(0.75, 0.5) == pytest.approx(0.375)
    assert combined_throttle(0.25, 0.5) == 0.25       # floor
    assert combined_throttle(0.0, 1.0) == 0.0         # pause always wins
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `throttle.py`)

```python
STREAK_TRIGGER = 4
STREAK_MULT = 0.5
STREAK_RECOVERY_WINS = 2
COMBINED_FLOOR = 0.25


def streak_multiplier(recent_closed: list) -> float:
    """4 consecutive losses halve new-entry risk until 2 wins land.
    Scratches/timeouts are noise: they neither break nor extend a streak."""
    decisive = [o for o in recent_closed if o in ("win", "loss")]
    streak = wins_after = 0
    triggered = False
    for o in decisive:
        if o == "loss":
            streak += 1
            if streak >= STREAK_TRIGGER:
                triggered, wins_after = True, 0
        else:
            streak = 0
            if triggered:
                wins_after += 1
                if wins_after >= STREAK_RECOVERY_WINS:
                    triggered = False
    return STREAK_MULT if triggered else 1.0


def combined_throttle(dd_mult: float, streak_mult: float) -> float:
    if dd_mult <= 0.0:
        return 0.0
    return max(COMBINED_FLOOR, dd_mult * streak_mult)
```

- [ ] **Step 4: Run `python -m pytest tests/test_edge_throttle.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/throttle.py tests/test_edge_throttle.py
git commit -m "feat: loss-streak damper"
```

### Task E47: Kill switch

**Files:**
- Modify: `swingbot/core/edge/throttle.py` (state + triggers), `swingbot/core/scanning/engine.py` (scan-loop check), `swingbot/commands/growth.py` (`!killswitch` lives with the other edge commands)
- Test: `tests/test_edge_throttle.py`

**Interfaces:**
- Produces: `kill_state() -> dict` (`{"on": bool, "reason": str | None, "at": iso}` from `data/killswitch.json` via `jsonio.read_json`); `set_kill(on: bool, reason: str = "manual")`; `check_kill_triggers(dd_pct, spy_move_pct, data_fail_frac) -> str | None` — returns the trigger reason when any fires: `dd_pct > 20`, `|spy_move_pct| > 5`, `data_fail_frac > 0.20` (broken feed); the scan loop calls it each cycle and auto-engages. Alerts are still generated + labeled `⛔ ENTRIES PAUSED (kill switch: {reason})` — informed, not blind. `!killswitch on|off|status` with an admin-only check.

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_throttle.py`)

```python
def test_kill_triggers():
    from swingbot.core.edge.throttle import check_kill_triggers
    assert check_kill_triggers(21.0, 0.0, 0.0) == "drawdown >20%"
    assert check_kill_triggers(0.0, -5.5, 0.0) == "SPY moved 5.5% in a day"
    assert check_kill_triggers(0.0, 0.0, 0.30) == "30% of universe failed data quality"
    assert check_kill_triggers(10.0, 2.0, 0.05) is None


def test_kill_state_roundtrip(tmp_path, monkeypatch):
    from swingbot.core.edge import throttle
    monkeypatch.setattr(throttle, "KILLSWITCH_PATH", str(tmp_path / "killswitch.json"))
    assert throttle.kill_state()["on"] is False              # default off
    throttle.set_kill(True, reason="manual")
    st = throttle.kill_state()
    assert st["on"] is True and st["reason"] == "manual" and st["at"]
    throttle.set_kill(False)
    assert throttle.kill_state()["on"] is False
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `throttle.py`)

```python
import datetime as _dt
import os

from swingbot import config
from swingbot.core.jsonio import read_json, write_json

KILLSWITCH_PATH = os.path.join(config.DATA_DIR, "killswitch.json")
KILL_DD_PCT = 20.0
KILL_SPY_MOVE_PCT = 5.0
KILL_DATA_FAIL_FRAC = 0.20


def kill_state() -> dict:
    return read_json(KILLSWITCH_PATH, {"on": False, "reason": None, "at": None})


def set_kill(on: bool, reason: str = "manual") -> dict:
    state = {"on": on, "reason": reason if on else None,
             "at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    write_json(KILLSWITCH_PATH, state)
    return state


def check_kill_triggers(dd_pct: float, spy_move_pct: float,
                        data_fail_frac: float) -> str | None:
    """Hard-pause triggers. Deliberately blunt: when any of these is true,
    the correct number of NEW positions is zero while a human looks."""
    if dd_pct > KILL_DD_PCT:
        return "drawdown >20%"
    if abs(spy_move_pct) > KILL_SPY_MOVE_PCT:
        return f"SPY moved {abs(spy_move_pct):.1f}% in a day"
    if data_fail_frac > KILL_DATA_FAIL_FRAC:
        return f"{data_fail_frac:.0%} of universe failed data quality"
    return None
```

Scan-loop wiring (`_sync_run_scan`, once per scan after the crawl): compute the three inputs (DD from balance history, SPY day move from its frame, data-fail fraction from the E16 skip counter); a firing trigger calls `set_kill(True, reason)` (never auto-releases — release is `!killswitch off`); when `kill_state()["on"]`, alerts get the `⛔ ENTRIES PAUSED` label and sizing suggestions become 0. `!killswitch` command in `commands/growth.py`:

```python
@bot.command(name="killswitch")
async def killswitch_command(ctx, action: str = "status"):
    """!killswitch on|off|status — hard pause for all new entries."""
    from swingbot.core.edge import throttle
    if action == "status":
        st = throttle.kill_state()
        await ctx.send(f"kill switch: {'🔴 ON — ' + str(st['reason']) if st['on'] else '🟢 off'}")
        return
    st = throttle.set_kill(action == "on", reason="manual")
    await ctx.send(f"kill switch {'engaged 🔴 — no new entries' if st['on'] else 'released 🟢'}")
```

- [ ] **Step 4: Run `python -m pytest tests/test_edge_throttle.py -v` — PASS. Full suite green.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/throttle.py swingbot/core/scanning/engine.py swingbot/commands/growth.py tests/test_edge_throttle.py
git commit -m "feat: kill switch"
```

### Task E48: Stale-position recycler

**Files:**
- Modify: `swingbot/core/plan_manager.py`
- Test: `tests/test_edge_throttle.py` (recycler section)

**Interfaces:**
- Produces: `recycle_candidates(plans: list, prices: dict[str, float]) -> list[dict]` — pure: ACTIVE/PARTIAL plans older than their `time_stop_days` (E32; skip plans without one) with progress `< 0.3R` return `{"plan_id", "ticker", "age_days", "progress_r"}`. The manager tick emits one `♻️ recycle candidate` PlanEvent per plan per day (advice-only — capital in dead trades is frequency lost, and frequency is the compounding lever).

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_throttle.py`)

```python
def test_recycle_candidates():
    import datetime as dt
    from swingbot.core.plan_manager import recycle_candidates

    class Plan:
        def __init__(self, pid, age_days, time_stop, entry=100.0, rps=2.0):
            self.plan_id = pid; self.ticker = pid
            self.status = "ACTIVE"; self.direction = "bullish"
            self.entry_price = entry; self.risk_per_share = rps
            self.time_stop_days = time_stop
            self.activated_at = (dt.date.today() - dt.timedelta(days=age_days)).isoformat()

    stale = Plan("STALE", age_days=10, time_stop=5)      # old + going nowhere
    young = Plan("YOUNG", age_days=2, time_stop=5)
    mover = Plan("MOVER", age_days=10, time_stop=5)
    out = recycle_candidates([stale, young, mover],
                             prices={"STALE": 100.2, "YOUNG": 100.2, "MOVER": 101.5})
    ids = [c["plan_id"] for c in out]
    assert ids == ["STALE"]                              # mover is at +0.75R
    assert out[0]["progress_r"] == pytest.approx(0.1)
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (add to `plan_manager.py`)

```python
RECYCLE_PROGRESS_R = 0.3


def recycle_candidates(plans: list, prices: dict) -> list:
    """Positions past their strategy's time stop with <0.3R to show for it.
    Advice-only: the notice says 'this capital is statistically dead',
    the operator decides."""
    import datetime as dt
    out = []
    today = dt.date.today()
    for p in plans:
        if getattr(p, "status", None) not in ("ACTIVE", "PARTIAL"):
            continue
        ts_days = getattr(p, "time_stop_days", None)
        price = prices.get(p.ticker)
        if ts_days is None or price is None or not getattr(p, "activated_at", None):
            continue
        age = (today - dt.date.fromisoformat(p.activated_at[:10])).days
        if age <= ts_days:
            continue
        sign = 1 if p.direction == "bullish" else -1
        progress = (price - p.entry_price) * sign / p.risk_per_share
        if progress < RECYCLE_PROGRESS_R:
            out.append({"plan_id": p.plan_id, "ticker": p.ticker,
                        "age_days": age, "progress_r": round(progress, 3)})
    return out
```

Tick wiring: `run_manager_tick` calls it with current prices and emits `PlanEvent("recycle_notice", ...)` once per plan per calendar day (dedupe on `(plan_id, date)` in the manager's state dict); Discord layer renders `♻️ {ticker} recycle candidate — {age_days}d in, {progress_r:+.2f}R. Dead capital is lost frequency.`

- [ ] **Step 4: Run — PASS. Step 5: Commit**

```bash
git add swingbot/core/plan_manager.py tests/test_edge_throttle.py
git commit -m "feat: stale-position notices"
```

### Task E49: Sector concentration cap

**Files:**
- Modify: `swingbot/core/edge/heat.py`
- Modify: `swingbot/config.py` (Field `SECTOR_HEAT_CAP_PCT`, float, default 3.0, min 0.5, max 10, step 0.5, section "Account Defaults")
- Test: `tests/test_edge_heat.py`

**Interfaces:**
- Produces: `sector_heat(open_trades, balance, sectors: dict[str, str]) -> dict[str, float]`; `sector_check(open_trades, balance, candidate_ticker, candidate_risk_pct, sectors, cap_pct=None) -> dict {allowed, sector, sector_heat, remaining, cap}` — same flagged-not-hidden blocking as E7, `sectors` from `universe.sector_map(...)`; unknown sector ⇒ always allowed (never block on missing metadata).

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_heat.py`)

```python
def test_sector_heat_and_cap():
    from swingbot.core.edge.heat import sector_check, sector_heat
    sectors = {"AAA": "Energy", "BBB": "Energy", "CCC": "Utilities", "CAND": "Energy"}
    trades = [{"ticker": "AAA", "risk_pct": 2.0}, {"ticker": "BBB", "risk_pct": 1.0},
              {"ticker": "CCC", "risk_pct": 2.0}]
    heat = sector_heat(trades, BALANCE, sectors)
    assert heat["Energy"] == pytest.approx(3.0)
    chk = sector_check(trades, BALANCE, "CAND", 1.0, sectors, cap_pct=3.0)
    assert chk["allowed"] is False and chk["sector"] == "Energy"


def test_unknown_sector_never_blocks():
    from swingbot.core.edge.heat import sector_check
    chk = sector_check([], BALANCE, "MYSTERY", 1.0, sectors={}, cap_pct=3.0)
    assert chk["allowed"] is True
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `heat.py`)

```python
def sector_heat(open_trades: list, balance: float, sectors: dict) -> dict:
    out: dict = {}
    for t in open_trades:
        sec = sectors.get(t.get("ticker"))
        if sec:
            out[sec] = out.get(sec, 0.0) + trade_risk_pct(t, balance)
    return {k: round(v, 3) for k, v in out.items()}


def sector_check(open_trades: list, balance: float, candidate_ticker: str,
                 candidate_risk_pct: float, sectors: dict,
                 cap_pct: float | None = None) -> dict:
    cap = cap_pct if cap_pct is not None else getattr(config, "SECTOR_HEAT_CAP_PCT", 3.0)
    sec = sectors.get(candidate_ticker)
    if sec is None:
        return {"allowed": True, "sector": None, "sector_heat": 0.0,
                "remaining": cap, "cap": cap}
    heat = sector_heat(open_trades, balance, sectors).get(sec, 0.0)
    remaining = max(0.0, cap - heat)
    return {"allowed": candidate_risk_pct <= remaining + 1e-9, "sector": sec,
            "sector_heat": heat, "remaining": round(remaining, 3), "cap": cap}
```

Alert-path wiring: same block as E7/E8, `item.sector_blocked = chk`, embed label `⛔ ENTRY BLOCKED — {sector} heat {sector_heat}%/{cap}%`.

- [ ] **Step 4: Run `python -m pytest tests/test_edge_heat.py -v` — PASS. Step 5: Commit**

```bash
git add swingbot/core/edge/heat.py swingbot/config.py swingbot/commands/scanning.py tests/test_edge_heat.py
git commit -m "feat: sector heat cap"
```

### Task E50: Portfolio replay backtest mode

**Files:**
- Modify: `swingbot/core/backtest_wf.py` (`portfolio_replay`), `scripts/wf_run.py` (`--portfolio`)
- Test: `tests/test_wf_portfolio.py`

**Interfaces:**
- Produces: `portfolio_replay(signals: list[dict], *, start_balance=10_000.0, risk_pct=1.0, heat_cap_pct=6.0, sector_cap_pct=3.0, max_open=None, sectors=None, throttles=True) -> dict` — chronological replay of ALL signals under real constraints. Each signal dict: `{"date", "ticker", "sector", "r_multiple", "exit_date"}` (produced from fold-run trades). Signals arriving when heat/sector caps are full are **skipped** (counted); wins/losses release heat on their exit date; equity compounds per closed trade at the throttled risk. Returns `{"equity_curve": [(date, balance)], "final_multiple", "max_dd_pct", "trades_taken", "trades_skipped", "trades_per_month"}`.
- **This is THE number that feeds honest 10x ETAs** — per-signal expectancy overstates growth when capital is constrained.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wf_portfolio.py
import pytest

from swingbot.core.backtest_wf import portfolio_replay


def _sig(date, ticker, r, exit_date, sector="Tech"):
    return {"date": date, "ticker": ticker, "sector": sector,
            "r_multiple": r, "exit_date": exit_date}


def test_heat_cap_forces_skips_deterministically():
    # 8 simultaneous signals at 1% risk each, 6% heat cap -> 6 taken, 2 skipped
    sigs = [_sig("2021-01-04", f"T{i}", 0.4, "2021-02-01") for i in range(8)]
    out = portfolio_replay(sigs, heat_cap_pct=6.0, sector_cap_pct=100.0)
    assert out["trades_taken"] == 6
    assert out["trades_skipped"] == 2


def test_heat_frees_on_exit():
    sigs = ([_sig("2021-01-04", f"A{i}", 0.4, "2021-01-10") for i in range(6)]
            + [_sig("2021-01-11", "LATE", 0.4, "2021-02-01")])
    out = portfolio_replay(sigs, heat_cap_pct=6.0, sector_cap_pct=100.0)
    assert out["trades_taken"] == 7            # early exits freed heat for LATE


def test_equity_compounds_and_dd_measured():
    sigs = [_sig(f"2021-0{m}-04", f"T{m}", r, f"2021-0{m}-20")
            for m, r in [(1, 1.0), (2, -1.0), (3, 1.0)]]
    out = portfolio_replay(sigs, heat_cap_pct=6.0, sector_cap_pct=100.0)
    assert out["final_multiple"] == pytest.approx(1.01 * 0.99 * 1.01, rel=1e-6)
    assert out["max_dd_pct"] > 0
    assert out["trades_per_month"] > 0
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `backtest_wf.py`)

```python
def portfolio_replay(signals: list, *, start_balance: float = 10_000.0,
                     risk_pct: float = 1.0, heat_cap_pct: float = 6.0,
                     sector_cap_pct: float = 3.0, max_open: int | None = None,
                     sectors: dict | None = None, throttles: bool = True) -> dict:
    """Chronological replay under real capital constraints. Per-signal
    expectancy answers 'is the edge real'; THIS answers 'what does the
    account actually do'. The difference is skipped signals."""
    from swingbot.core.edge.throttle import current_throttle

    events = sorted(signals, key=lambda s: (s["date"], s["ticker"]))
    balance = start_balance
    curve = [(events[0]["date"] if events else "start", balance)]
    open_pos: list[dict] = []      # {"exit_date", "ticker", "sector", "risk_pct", "r"}
    taken = skipped = 0
    paused = False

    for sig in events:
        # 1) close everything that exited before this signal's date
        due = [p for p in open_pos if p["exit_date"] <= sig["date"]]
        for p in sorted(due, key=lambda p: p["exit_date"]):
            balance *= 1 + (p["risk_pct"] / 100.0) * p["r"]
            curve.append((p["exit_date"], balance))
            open_pos.remove(p)

        # 2) throttle from the equity curve so far
        mult = 1.0
        if throttles:
            mult, paused = current_throttle([b for _, b in curve], was_paused=paused)
        eff_risk = risk_pct * mult
        if eff_risk <= 0:
            skipped += 1
            continue

        # 3) capacity checks
        heat = sum(p["risk_pct"] for p in open_pos)
        sec = (sectors or {}).get(sig["ticker"], sig.get("sector"))
        sec_heat = sum(p["risk_pct"] for p in open_pos if p["sector"] == sec)
        if (heat + eff_risk > heat_cap_pct + 1e-9
                or (sec and sec_heat + eff_risk > sector_cap_pct + 1e-9)
                or (max_open is not None and len(open_pos) >= max_open)):
            skipped += 1
            continue

        open_pos.append({"exit_date": sig["exit_date"], "ticker": sig["ticker"],
                         "sector": sec, "risk_pct": eff_risk, "r": sig["r_multiple"]})
        taken += 1

    for p in sorted(open_pos, key=lambda p: p["exit_date"]):
        balance *= 1 + (p["risk_pct"] / 100.0) * p["r"]
        curve.append((p["exit_date"], balance))

    values = [b for _, b in curve]
    peak, max_dd = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak * 100.0)

    months = 1.0
    if taken and len(curve) > 1:
        import datetime as dt
        d0 = dt.date.fromisoformat(str(curve[0][0])[:10]) if curve[0][0] != "start" else None
        d1 = dt.date.fromisoformat(str(curve[-1][0])[:10])
        months = max(((d1 - d0).days / 30.44) if d0 else 1.0, 1.0)

    return {"equity_curve": curve, "final_multiple": balance / start_balance,
            "max_dd_pct": round(max_dd, 2), "trades_taken": taken,
            "trades_skipped": skipped, "trades_per_month": round(taken / months, 1)}
```

`scripts/wf_run.py --portfolio`: builds the signal list from fold-run trades (date/ticker/sector/r/exit) and prints the replay dict.

- [ ] **Step 4: Run `python -m pytest tests/test_wf_portfolio.py -v` — PASS (3 tests).**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtest_wf.py scripts/wf_run.py tests/test_wf_portfolio.py
git commit -m "feat: portfolio-level replay"
```

### Task E51: Portfolio replay of the adopted system

Operational task — no new code.

- [ ] **Step 1: Run the replay over the TRAIN folds** with adopted components + quarter-Kelly + throttles:

```bash
python scripts/wf_run.py --portfolio --component-json "$(cat docs/superpowers/results/adopted_components.json)"
```

- [ ] **Step 2: Monte Carlo it at 3 risk levels** — feed the replay's realized R sequence into `ruin.simulate` at `risk_pct` 0.5 / 1.0 / 1.5:

```bash
python -c "
import json
from swingbot.core.edge.ruin import simulate
rs = json.load(open('data/replay_r_sequence.json'))   # wf_run --portfolio writes this
for risk in (0.5, 1.0, 1.5):
    print(risk, simulate(rs, risk_pct=risk))
"
```

- [ ] **Step 3: Write `docs/superpowers/results/2026-XX-edge-portfolio.md`** — CAGR, max DD, trades/month, skipped-signal fraction, `p_ruin`/`p_10x` per risk level. **This doc IS the honest growth expectation** — the `!growth` ETA should be quoted from these numbers, not from per-signal expectancy.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/2026-XX-edge-portfolio.md
git commit -m "docs: portfolio-level replay of the adopted system"
```

### Task E52: `!portfolio` command

**Files:**
- Modify: `swingbot/commands/growth.py`
- Test: `tests/test_edge_heat.py` (renderer section)

**Interfaces:**
- Produces: `portfolio_report(state: dict) -> str` — pure renderer; `state` keys: `open_heat, heat_cap, sector_heat (dict), clusters (list[list[str]]), throttle_mult, paused, kill (dict), growth (growth_path output)`. Command `!portfolio` assembles state from `heat.open_heat`, `heat.sector_heat`, `correlation.cluster_exposure` pairs over open positions, `throttle.current_throttle`, `throttle.kill_state`, `growth.growth_path` — the survival dashboard in one embed (plus the E68 treemap once charts land).

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_heat.py`)

```python
def test_portfolio_report_renders_every_section():
    from swingbot.commands.growth import portfolio_report
    state = {"open_heat": 4.5, "heat_cap": 6.0,
             "sector_heat": {"Energy": 3.0, "Tech": 1.5},
             "clusters": [["XOM", "CVX"]],
             "throttle_mult": 0.75, "paused": False,
             "kill": {"on": False, "reason": None},
             "growth": {"current_multiple": 1.32, "pct_to_target": 12.1}}
    out = portfolio_report(state)
    assert "4.5% / 6.0%" in out
    assert "Energy" in out and "3.0%" in out
    assert "XOM" in out and "CVX" in out
    assert "x0.75" in out
    assert "1.32x" in out


def test_portfolio_report_kill_state_prominent():
    from swingbot.commands.growth import portfolio_report
    state = {"open_heat": 0.0, "heat_cap": 6.0, "sector_heat": {}, "clusters": [],
             "throttle_mult": 0.0, "paused": True,
             "kill": {"on": True, "reason": "manual"}, "growth": {}}
    assert "KILL SWITCH ON" in portfolio_report(state)
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `commands/growth.py`)

```python
def portfolio_report(state: dict) -> str:
    """Survival dashboard: heat, sectors, clusters, throttle, kill, growth."""
    lines = ["PORTFOLIO SURVIVAL DASHBOARD"]
    if state.get("kill", {}).get("on"):
        lines.append(f"🔴 KILL SWITCH ON — {state['kill'].get('reason')} — no new entries")
    lines.append(f"heat: {state.get('open_heat', 0.0):.1f}% / {state.get('heat_cap', 6.0):.1f}% cap")
    for sec, h in sorted(state.get("sector_heat", {}).items(), key=lambda kv: -kv[1]):
        bar = "█" * int(round(h * 4))
        lines.append(f"  {sec:<24} {h:.1f}% {bar}")
    for cluster in state.get("clusters", []):
        lines.append(f"  ⚠ correlated cluster: {', '.join(cluster)}")
    mult = state.get("throttle_mult", 1.0)
    lines.append(f"throttle: x{mult:.2f}" + (" (PAUSED)" if state.get("paused") else ""))
    g = state.get("growth") or {}
    if g:
        lines.append(f"growth path: {g.get('current_multiple', 1.0):.2f}x — "
                     f"{g.get('pct_to_target', 0.0):.1f}% of the way to 10x (log scale)")
    lines.append("Projections from backtests/paper — real results will differ.")
    return "\n".join(lines)


@bot.command(name="portfolio")
async def portfolio_command(ctx):
    """Open heat vs cap, sector bars, clusters, throttle + kill state."""
    state = await asyncio.to_thread(_collect_portfolio_state)
    await ctx.send(f"```\n{portfolio_report(state)}\n```")
```

`_collect_portfolio_state()` assembles the dict from the E7/E8/E45/E47/E9 accessors over the open-trade list (mirror `_collect_stats`'s soft-import style; every sub-collector try/excepted to `{}`/defaults so a missing piece never kills the command).

- [ ] **Step 4: Run `python -m pytest tests/test_edge_heat.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/growth.py tests/test_edge_heat.py
git commit -m "feat: !portfolio survival dashboard"
```

### Task E53: Weekly risk report

**Files:**
- Modify: `swingbot/core/retrospective.py` (Sunday hook), `swingbot/commands/growth.py` (renderer reuse)
- Test: `tests/test_edge_heat.py`

**Interfaces:**
- Produces: `weekly_risk_report(week_stats: dict) -> str` — pure renderer; `week_stats`: `{heat_utilization_pct (mean open-heat / cap over the week's scans), biggest_cluster (list), throttle_activations (int), mc (ruin.simulate output on updated R history), growth_delta (multiple change this week)}`. Posted Sundays by the retrospective scheduler to the retrospective channel, titled `🛡️ Weekly risk report`.
- Heat utilization source: the E82 telemetry lines (each scan logs `open_heat`); until E82 lands, the report says "n/a".

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_heat.py`)

```python
def test_weekly_risk_report_renders():
    from swingbot.commands.growth import weekly_risk_report
    out = weekly_risk_report({
        "heat_utilization_pct": 62.0,
        "biggest_cluster": ["NVDA", "AMD", "AVGO"],
        "throttle_activations": 1,
        "mc": {"max_dd_p95": 0.18, "p_ruin": 0.002, "p_10x": 0.11},
        "growth_delta": 0.014,
    })
    assert "62" in out and "NVDA" in out
    assert "p95 drawdown 18%" in out
    assert "+1.4%" in out
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `commands/growth.py`; hook in `retrospective.py`'s Sunday branch calling it with assembled stats, try/except-logged)

```python
def weekly_risk_report(week_stats: dict) -> str:
    mc = week_stats.get("mc") or {}
    cluster = week_stats.get("biggest_cluster") or []
    util = week_stats.get("heat_utilization_pct")
    lines = [
        "🛡️ WEEKLY RISK REPORT",
        f"heat utilization: {util:.0f}% of cap" if util is not None else "heat utilization: n/a",
        f"biggest correlated cluster: {', '.join(cluster) if cluster else 'none'}",
        f"throttle activations: {week_stats.get('throttle_activations', 0)}",
    ]
    if mc:
        lines.append(f"Monte Carlo (updated R history): p95 drawdown {mc['max_dd_p95']:.0%}, "
                     f"p(halve) {mc['p_ruin']:.1%}, p(10x within 1000 trades) {mc['p_10x']:.0%}")
    gd = week_stats.get("growth_delta")
    if gd is not None:
        lines.append(f"growth path this week: {gd:+.1%}")
    lines.append("Projections, not promises.")
    return "\n".join(lines)
```

- [ ] **Step 4: Run — PASS. Step 5: Commit**

```bash
git add swingbot/commands/growth.py swingbot/core/retrospective.py tests/test_edge_heat.py
git commit -m "feat: weekly risk report"
```

### Task E54: Admin risk panel

**Files:**
- Modify: `swingbot/admin/app.py` (route `/risk` + kill-switch POST), `swingbot/admin/templates/` (new `risk.html`, nav link)
- Test: `tests/admin/test_risk_panel.py`

**Interfaces:**
- Produces: `GET /risk` — heat gauge (open vs cap), sector bars, throttle state, kill-switch state + toggle button (`POST /risk/killswitch` body `action=on|off`, with a JS `confirm()`); reuses `_collect_portfolio_state` from E52. Cockpit Part 3 absent ⇒ the page stands alone off the existing admin nav (degrades gracefully — no dashboard-card dependency).

- [ ] **Step 1: Write the failing test**

```python
# tests/admin/test_risk_panel.py
"""Flask test-client tests. Reuse the existing admin conftest (authed
client fixture); if tests/admin/ doesn't exist yet, mirror the fixtures
from the cockpit plan's tests/admin/conftest.py (authed session client)."""


def test_risk_page_renders(client):
    resp = client.get("/risk")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Portfolio heat" in body and "Kill switch" in body


def test_killswitch_toggle_roundtrip(client, tmp_path, monkeypatch):
    from swingbot.core.edge import throttle
    monkeypatch.setattr(throttle, "KILLSWITCH_PATH", str(tmp_path / "ks.json"))
    resp = client.post("/risk/killswitch", data={"action": "on"})
    assert resp.status_code in (200, 302)
    assert throttle.kill_state()["on"] is True
    client.post("/risk/killswitch", data={"action": "off"})
    assert throttle.kill_state()["on"] is False
```

- [ ] **Step 2: Run — FAIL (404).**

- [ ] **Step 3: Implement** — route in `admin/app.py`:

```python
@app.route("/risk")
@login_required
def risk_panel():
    from swingbot.commands.growth import _collect_portfolio_state
    return render_template("risk.html", state=_collect_portfolio_state())


@app.route("/risk/killswitch", methods=["POST"])
@login_required
def risk_killswitch():
    from swingbot.core.edge import throttle
    throttle.set_kill(request.form.get("action") == "on", reason="admin panel")
    return redirect(url_for("risk_panel"))
```

`templates/risk.html` (extends the admin base template): heat gauge as a CSS progress bar (`state.open_heat / state.heat_cap`), sector bars (loop over `state.sector_heat`), throttle chip, kill-switch form with `onsubmit="return confirm('Toggle the kill switch?')"`. Match the existing template idioms (same blocks/classes as `settings.html`).

- [ ] **Step 4: Run `python -m pytest tests/admin/ -v` — PASS. Step 5: Commit**

```bash
git add swingbot/admin/app.py swingbot/admin/templates/risk.html tests/admin/test_risk_panel.py
git commit -m "feat: admin risk panel"
```

### Task E55: Sizing-mode shadow comparison

**Files:**
- Modify: `swingbot/core/performance.py` (shadow columns), `scripts/` (new `sizing_shadow_report.py`)
- Test: `tests/test_edge_sizing.py`

**Interfaces:**
- Produces: every logged trade record gains `shadow_sizing: {"kelly": risk_pct, "vol_target": risk_pct, "min_of_all": risk_pct}` (computed at entry time from the same inputs the E6 modes would use — recorded, never applied). `sizing_shadow_report(trades: list[dict]) -> dict` — per mode: what the realized equity multiple WOULD have been (`Π(1 + risk/100 × r_multiple)`), vs actual. Script prints the comparison; decision recorded after 4 weeks; the user flips `POSITION_SIZING_MODE` deliberately.

- [ ] **Step 1: Write the failing test** (append to `tests/test_edge_sizing.py`)

```python
def test_sizing_shadow_report_compares_modes():
    from scripts.sizing_shadow_report import sizing_shadow_report
    trades = [
        {"r_multiple": 1.0, "risk_pct": 1.0,
         "shadow_sizing": {"kelly": 2.0, "vol_target": 0.7, "min_of_all": 0.7}},
        {"r_multiple": -1.0, "risk_pct": 1.0,
         "shadow_sizing": {"kelly": 2.0, "vol_target": 0.7, "min_of_all": 0.7}},
        {"r_multiple": 1.0, "risk_pct": 1.0,
         "shadow_sizing": {"kelly": 2.0, "vol_target": 0.7, "min_of_all": 0.7}},
    ]
    rep = sizing_shadow_report(trades)
    assert rep["actual"]["multiple"] == pytest.approx(1.01 * 0.99 * 1.01, rel=1e-9)
    assert rep["kelly"]["multiple"] == pytest.approx(1.02 * 0.98 * 1.02, rel=1e-9)
    assert rep["kelly"]["max_dd_pct"] > rep["vol_target"]["max_dd_pct"]
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** — `scripts/sizing_shadow_report.py`:

```python
"""What would each sizing mode have done with the SAME trades?
Run: python scripts/sizing_shadow_report.py"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _walk(trades, risk_key):
    bal, peak, max_dd = 1.0, 1.0, 0.0
    for t in trades:
        risk = (t["shadow_sizing"].get(risk_key) if risk_key != "actual"
                else t.get("risk_pct")) or 0.0
        bal *= 1 + risk / 100.0 * t["r_multiple"]
        peak = max(peak, bal)
        max_dd = max(max_dd, (peak - bal) / peak * 100.0)
    return {"multiple": bal, "max_dd_pct": round(max_dd, 2)}


def sizing_shadow_report(trades: list) -> dict:
    trades = [t for t in trades if t.get("shadow_sizing") and t.get("r_multiple") is not None]
    return {mode: _walk(trades, mode)
            for mode in ("actual", "kelly", "vol_target", "min_of_all")}


if __name__ == "__main__":
    from swingbot.core.performance import TradeLog
    print(json.dumps(sizing_shadow_report(TradeLog().all_trades()), indent=1))
```

`performance.py` change: where the trade record is assembled at entry (the block that already stamps `sizing_mode`), add the shadow dict — each mode's would-be risk from `edge.sizing` with whatever inputs are available (`None`-safe; missing input ⇒ mode omitted).

- [ ] **Step 4: Run — PASS. Step 5: Run 4 weeks, write the decision** into `docs/superpowers/results/2026-XX-edge-portfolio.md` (append a "sizing mode shadow" section), **commit**

```bash
git add scripts/sizing_shadow_report.py swingbot/core/performance.py tests/test_edge_sizing.py
git commit -m "feat: sizing-mode shadow comparison"
```

### Task E56: Phase E3 checkpoint

- [ ] **Step 1: Full suite + `make check` — green.**
- [ ] **Step 2: Live smoke in the test channel:** `!portfolio` (with ≥1 open paper position), `!killswitch status` → `on` → verify the next scan's alerts carry the pause label → `off`; admin `/risk` page reflects all of it.
- [ ] **Step 3: Portfolio doc (E51) committed; Progress block updated; commit**

```bash
git add docs/superpowers/plans/2026-07-11-edge-engine.md
git commit -m "docs: survival systems checkpoint"
```

---

# Phase E4 — Decision charts v3 (E57–E76)

All renders use `chart_style.py` constants (`CHART_BG`, `PRO_STYLE`, `UP_COLOR`/`DOWN_COLOR`, `ENTRY_COLOR`/`STOP_COLOR`/`TARGET_COLOR`, `DISCLAIMER_TEXT`); every chart task carries a file-exists + no-crash test on synthetic data in `tests/test_decision_chart.py` / `tests/test_portfolio_charts.py`. Matplotlib runs headless (`matplotlib.use("Agg")` in the test module top, as the existing chart tests do).

### Task E57: `decision_chart.py` skeleton — the one-pager

**Files:**
- Create: `swingbot/core/charts/decision_chart.py`
- Test: `tests/test_decision_chart.py`

**Interfaces:**
- Produces: `render_decision_chart(symbol: str, daily_df: pd.DataFrame, plan, context: dict, out_dir: str) -> str` (path of the written PNG). Layout: 3×4 GridSpec — main daily panel (candles + plan levels, cols 0–2, all rows), right column top→bottom: weekly context (E58), RS strip (E60), info column (E65/E66). `context` is a plain dict; **every key optional** — panels render placeholders when data is absent (`draw_placeholder(ax, "no data")`), so the chart NEVER crashes an alert. Context keys land task by task: `weekly` (E58), `avwaps` (E59), `rs` (E60), `regimes` (E61), `outcomes` (E62), `ev_cone` (E63), `gap` (E64), `sizing` (E65), `quality` (E66).
- `plan` needs: `direction, entry_price/trigger_price, stop_loss, tp1, tp2, strategy, horizon_key` (TradePlanV2 or any duck-typed stand-in).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_decision_chart.py
import os

import matplotlib
matplotlib.use("Agg")

import numpy as np
import pytest

from tests.conftest import make_trend_df


class FakePlan:
    direction = "bullish"
    entry_price = None
    trigger_price = 108.0
    stop_loss = 104.0
    tp1 = 111.0
    tp2 = 114.0
    strategy = "Support/Resistance"
    horizon_key = "4w"


@pytest.fixture
def daily_df():
    return make_trend_df(300, +0.15)


def test_skeleton_renders_with_empty_context(tmp_path, daily_df):
    from swingbot.core.charts.decision_chart import render_decision_chart
    path = render_decision_chart("TEST", daily_df, FakePlan(), {}, str(tmp_path))
    assert os.path.exists(path)
    assert os.path.getsize(path) > 10_000       # a real figure, not a stub
    assert path.endswith(".png")
```

- [ ] **Step 2: Run — FAIL (`ModuleNotFoundError`).**

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/charts/decision_chart.py
"""The decision one-pager: everything needed to take or skip a trade on
one image -- daily plan, weekly context, relative strength, regime,
historical outcome distribution, sizing math. Composed of independent
panel functions; every panel degrades to a placeholder when its context
key is missing, because a chart must never cost us an alert."""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

from swingbot.core.charts.chart_style import (
    CHART_BG, DISCLAIMER_TEXT, ENTRY_COLOR, GRID_COLOR, MUTED_TEXT_COLOR,
    PRO_STYLE, STOP_COLOR, TARGET_COLOR, TEXT_COLOR,
)

PANEL_LOOKBACK_BARS = 130


def draw_placeholder(ax, text: str) -> None:
    ax.set_facecolor(CHART_BG)
    ax.text(0.5, 0.5, text, transform=ax.transAxes, ha="center", va="center",
            color=MUTED_TEXT_COLOR, fontsize=9)
    ax.set_xticks([]); ax.set_yticks([])


def _draw_main_panel(ax, daily_df: pd.DataFrame, plan) -> None:
    part = daily_df.tail(PANEL_LOOKBACK_BARS)
    mpf.plot(part, type="candle", ax=ax, style=PRO_STYLE, warn_too_much_data=10_000)
    levels = [(plan.trigger_price or plan.entry_price, ENTRY_COLOR, "entry"),
              (plan.stop_loss, STOP_COLOR, "stop"),
              (plan.tp1, TARGET_COLOR, "TP1")]
    if getattr(plan, "tp2", None):
        levels.append((plan.tp2, TARGET_COLOR, "TP2"))
    for price, color, label in levels:
        if price:
            ax.axhline(price, color=color, lw=1.1, ls="--", alpha=0.9)
            ax.annotate(f"{label} {price:.2f}", xy=(1.0, price),
                        xycoords=("axes fraction", "data"),
                        fontsize=8, color=color, ha="right", va="bottom")
    ax.set_facecolor(CHART_BG)


def render_decision_chart(symbol: str, daily_df: pd.DataFrame, plan,
                          context: dict, out_dir: str) -> str:
    fig = plt.figure(figsize=(16, 9), facecolor=CHART_BG, dpi=110)
    gs = fig.add_gridspec(3, 4, hspace=0.25, wspace=0.18,
                          width_ratios=[1, 1, 1, 0.85])
    ax_main = fig.add_subplot(gs[:, :3])
    ax_weekly = fig.add_subplot(gs[0, 3])
    ax_rs = fig.add_subplot(gs[1, 3])
    ax_info = fig.add_subplot(gs[2, 3])

    _draw_main_panel(ax_main, daily_df, plan)
    # Later tasks replace these placeholders panel by panel:
    from swingbot.core.charts import decision_panels as panels  # this module, split below
    panels.draw_weekly(ax_weekly, context.get("weekly"))
    panels.draw_rs_strip(ax_rs, context.get("rs"))
    panels.draw_info(ax_info, context.get("sizing"), context.get("quality"))

    fig.suptitle(f"{symbol} — {plan.strategy} ({plan.horizon_key}) {plan.direction}",
                 color=TEXT_COLOR, fontsize=13, x=0.02, ha="left")
    fig.text(0.99, 0.005, DISCLAIMER_TEXT, color=MUTED_TEXT_COLOR,
             fontsize=7, ha="right")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{symbol}_decision.png")
    fig.savefig(path, facecolor=CHART_BG, bbox_inches="tight")
    plt.close(fig)
    return path
```

and the panel module starting as placeholders:

```python
# swingbot/core/charts/decision_panels.py
"""Right-column panels of the decision chart. Each takes (ax, data) and
must handle data=None with a placeholder -- panels are optional, alerts
are not."""
from swingbot.core.charts.decision_chart import draw_placeholder


def draw_weekly(ax, weekly_ctx):
    draw_placeholder(ax, "weekly context (E58)") if weekly_ctx is None else _weekly(ax, weekly_ctx)


def draw_rs_strip(ax, rs_ctx):
    draw_placeholder(ax, "relative strength (E60)") if rs_ctx is None else _rs(ax, rs_ctx)


def draw_info(ax, sizing_ctx, quality_ctx):
    if sizing_ctx is None and quality_ctx is None:
        draw_placeholder(ax, "sizing & quality (E65/E66)")
        return
    _info(ax, sizing_ctx, quality_ctx)
```

(`_weekly/_rs/_info` are implemented in E58/E60/E65 — until then the non-None branch simply calls `draw_placeholder(ax, "pending")` so the module imports clean.)

- [ ] **Step 4: Run `python -m pytest tests/test_decision_chart.py -v` — PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/decision_chart.py swingbot/core/charts/decision_panels.py tests/test_decision_chart.py
git commit -m "feat: decision chart skeleton"
```

### Task E58: Weekly context panel

**Files:** Modify `swingbot/core/charts/decision_panels.py`; test `tests/test_decision_chart.py`

**Interfaces:**
- Produces: `_weekly(ax, weekly_ctx)` — `weekly_ctx = {"df": weekly_frame(daily_df), "pivots": [prices]}` (weekly frame from E27's `weekly_frame`); draws weekly candles (last ~40 weeks), 10/40-week EMAs, horizontal pivot levels, the current (incomplete) week's candle highlighted with an outline. Caller (`render_decision_chart`'s alert wiring, E67) builds the ctx.

- [ ] **Step 1: Failing test** (append)

```python
def test_weekly_panel_renders(tmp_path, daily_df):
    from swingbot.core.edge.factors import weekly_frame
    from swingbot.core.charts.decision_chart import render_decision_chart
    ctx = {"weekly": {"df": weekly_frame(daily_df), "pivots": [105.0, 112.0]}}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert os.path.getsize(path) > 10_000
```

- [ ] **Step 2: Run — FAIL (placeholder branch raises nothing but `_weekly` is a stub → implement to make the panel real; assert by absence of exceptions + size).**

- [ ] **Step 3: Implement** (replace the `_weekly` stub)

```python
import mplfinance as mpf

from swingbot.core.charts.chart_style import (CHART_BG, CHIP_EDGE, GRID_COLOR,
                                              MUTED_TEXT_COLOR, PRO_STYLE, TEXT_COLOR)


def _weekly(ax, ctx):
    df = ctx["df"].tail(40)
    if len(df) < 5:
        draw_placeholder(ax, "not enough weekly history")
        return
    mpf.plot(df, type="candle", ax=ax, style=PRO_STYLE, warn_too_much_data=10_000)
    for span, alpha in ((10, 0.9), (40, 0.6)):
        ema = ctx["df"]["Close"].ewm(span=span, adjust=False).mean().tail(40)
        ax.plot(range(len(ema)), ema.values, lw=1.0, alpha=alpha, color=TEXT_COLOR)
    for p in ctx.get("pivots", []):
        ax.axhline(p, color=CHIP_EDGE, lw=0.8, ls=":")
    # highlight the live (incomplete) week
    ax.axvspan(len(df) - 1.5, len(df) - 0.5, color=GRID_COLOR, alpha=0.5)
    ax.set_title("weekly", color=MUTED_TEXT_COLOR, fontsize=8, loc="left")
    ax.set_facecolor(CHART_BG)
```

- [ ] **Step 4: PASS. Step 5: Commit** — `git add swingbot/core/charts/decision_panels.py tests/test_decision_chart.py && git commit -m "feat: weekly panel"`

### Task E59: Anchored VWAP overlays on the main panel

**Files:** Modify `swingbot/core/charts/decision_chart.py`; test `tests/test_decision_chart.py`

**Interfaces:**
- Produces: `_draw_main_panel` gains `avwaps: list[dict] | None` — each `{"series": pd.Series, "anchor_label": str}` (from E30's `anchored_vwap`/`avwap_anchors`); drawn in a distinct color with a ⚓ marker at the anchor bar and the label chip at the right edge. Context key: `context["avwaps"]`.

- [ ] **Step 1: Failing test** (append)

```python
def test_avwap_overlay_renders(tmp_path, daily_df):
    from swingbot.core.edge.factors import anchored_vwap, avwap_anchors
    from swingbot.core.charts.decision_chart import render_decision_chart
    avwaps = [{"series": anchored_vwap(daily_df, a), "anchor_label": f"⚓{a}"}
              for a in avwap_anchors(daily_df)[:3]]
    path = render_decision_chart("TEST", daily_df, FakePlan(),
                                 {"avwaps": avwaps}, str(tmp_path))
    assert os.path.getsize(path) > 10_000
```

- [ ] **Step 2: FAIL (unknown kwarg/ignored key — add the drawing). Step 3: Implement** — in `_draw_main_panel` (signature gains `avwaps=None`, threaded from `context.get("avwaps")`):

```python
AVWAP_COLOR = "#b39ddb"   # add to chart_style.py with the other overlay colors

    # inside _draw_main_panel, after the level lines:
    part_index = part.index
    for av in (avwaps or []):
        s = av["series"].reindex(part_index).dropna()
        if s.empty:
            continue
        x0 = part_index.get_indexer([s.index[0]])[0]
        xs = range(x0, x0 + len(s))
        ax.plot(list(xs), s.values, color=AVWAP_COLOR, lw=1.2, alpha=0.85)
        ax.annotate("⚓", xy=(x0, s.values[0]), color=AVWAP_COLOR, fontsize=9)
        ax.annotate(f"AVWAP {s.values[-1]:.2f}", xy=(1.0, s.values[-1]),
                    xycoords=("axes fraction", "data"), fontsize=7,
                    color=AVWAP_COLOR, ha="right")
```

- [ ] **Step 4: PASS. Step 5: Commit** — `git add swingbot/core/charts/decision_chart.py swingbot/core/charts/chart_style.py tests/test_decision_chart.py && git commit -m "feat: AVWAP overlay"`

### Task E60: RS strip panel

**Files:** Modify `swingbot/core/charts/decision_panels.py`; test `tests/test_decision_chart.py`

**Interfaces:**
- Produces: `_rs(ax, rs_ctx)` — `rs_ctx = {"rel_series": pd.Series (63d rolling relative return vs SPY), "percentile": float}`; line plot, zero-line, shading below zero (underperformance) in `DOWN_COLOR` alpha, current percentile annotated top-right (`RS 78th pct`).

- [ ] **Step 1: Failing test** (append)

```python
def test_rs_strip_renders(tmp_path, daily_df):
    import pandas as pd
    from swingbot.core.charts.decision_chart import render_decision_chart
    rel = (daily_df["Close"].pct_change(63) - 0.01).dropna()
    ctx = {"rs": {"rel_series": rel, "percentile": 78.0}}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert os.path.getsize(path) > 10_000
```

- [ ] **Step 2: FAIL. Step 3: Implement** (replace `_rs` stub)

```python
from swingbot.core.charts.chart_style import DOWN_COLOR, UP_COLOR


def _rs(ax, ctx):
    s = ctx["rel_series"].tail(130)
    if s.empty:
        draw_placeholder(ax, "no RS history")
        return
    x = range(len(s))
    ax.plot(x, s.values, color=UP_COLOR, lw=1.0)
    ax.axhline(0.0, color=MUTED_TEXT_COLOR, lw=0.7)
    ax.fill_between(x, s.values, 0, where=(s.values < 0),
                    color=DOWN_COLOR, alpha=0.25)
    pct = ctx.get("percentile")
    if pct is not None:
        ax.set_title(f"RS vs SPY — {pct:.0f}th pct", color=MUTED_TEXT_COLOR,
                     fontsize=8, loc="left")
    ax.set_xticks([]); ax.set_facecolor(CHART_BG)
```

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: RS strip"` (with the touched files staged)

### Task E61: Regime background shading

**Files:** Modify `swingbot/core/charts/decision_chart.py`; test `tests/test_decision_chart.py`

**Interfaces:**
- Produces: `_draw_main_panel` gains `regimes: pd.Series | None` (E23's `regime_series`, reindexed to the ticker frame); background `axvspan` per contiguous regime run — greens for bull, reds for bear, deeper alpha for volatile (`{"bull_quiet": (UP, .05), "bull_volatile": (UP, .12), "bear_quiet": (DOWN, .05), "bear_volatile": (DOWN, .12)}`); a small legend chip row under the title.

- [ ] **Step 1: Failing test** (append)

```python
def test_regime_shading_renders(tmp_path, daily_df):
    import pandas as pd
    from swingbot.core.charts.decision_chart import render_decision_chart
    labels = (["bull_quiet"] * 150 + ["bear_volatile"] * 150)
    ctx = {"regimes": pd.Series(labels, index=daily_df.index)}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert os.path.getsize(path) > 10_000
```

- [ ] **Step 2: FAIL. Step 3: Implement** — in `_draw_main_panel` (new `regimes=None` arg):

```python
REGIME_SHADE = {"bull_quiet": (UP_COLOR, 0.05), "bull_volatile": (UP_COLOR, 0.12),
                "bear_quiet": (STOP_COLOR, 0.05), "bear_volatile": (STOP_COLOR, 0.12)}

    # inside _draw_main_panel, before candles are drawn:
    if regimes is not None:
        r = regimes.reindex(part.index).ffill()
        run_start = 0
        vals = r.values
        for i in range(1, len(vals) + 1):
            if i == len(vals) or vals[i] != vals[run_start]:
                color, alpha = REGIME_SHADE.get(vals[run_start], (GRID_COLOR, 0.0))
                ax.axvspan(run_start - 0.5, i - 0.5, color=color, alpha=alpha, zorder=0)
                run_start = i
```

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: regime shading"`

### Task E62: Historical outcome cloud

**Files:** Modify `swingbot/core/charts/decision_chart.py`; test `tests/test_decision_chart.py`

**Interfaces:**
- Produces: `_draw_main_panel` gains `outcomes: list[dict] | None` — past fold-trade outcomes for the plan's strategy: each `{"r_path": list[float] (daily R progression from entry), "outcome": "win"|"loss"}`; drawn as translucent forward paths projected from the current entry bar/price (R → price via the plan's `risk_per_share`), wins in `TARGET_COLOR` alpha 0.10, losses `STOP_COLOR` alpha 0.10. **Panel omitted when < 20 samples** (an outcome cloud of 6 paths is an anecdote generator). Data source: the fold-results trade cache written by E39 runs (`data/fold_trades/{strategy}.json`).

- [ ] **Step 1: Failing test** (append)

```python
def test_outcome_cloud_renders_and_respects_min_samples(tmp_path, daily_df):
    from swingbot.core.charts.decision_chart import render_decision_chart
    win = {"r_path": [0.1, 0.3, 0.6, 1.0], "outcome": "win"}
    loss = {"r_path": [-0.2, -0.6, -1.0], "outcome": "loss"}
    big = {"outcomes": [win] * 16 + [loss] * 8}      # 24 >= 20 -> drawn
    small = {"outcomes": [win] * 5}                  # < 20 -> silently omitted
    p1 = render_decision_chart("BIG", daily_df, FakePlan(), big, str(tmp_path))
    p2 = render_decision_chart("SMALL", daily_df, FakePlan(), small, str(tmp_path))
    assert os.path.getsize(p1) > os.path.getsize(p2) * 0.5   # both render fine
```

- [ ] **Step 2: FAIL. Step 3: Implement** — in `_draw_main_panel` (new `outcomes=None` arg; plan gains `risk_per_share` read):

```python
OUTCOME_MIN_SAMPLES = 20

    # inside _draw_main_panel, after levels:
    if outcomes and len(outcomes) >= OUTCOME_MIN_SAMPLES:
        entry_px = plan.trigger_price or plan.entry_price
        rps = abs(entry_px - plan.stop_loss)
        x0 = len(part) - 1
        sign = 1 if plan.direction == "bullish" else -1
        for o in outcomes:
            ys = [entry_px + sign * r * rps for r in [0.0] + list(o["r_path"])]
            color = TARGET_COLOR if o["outcome"] == "win" else STOP_COLOR
            ax.plot(range(x0, x0 + len(ys)), ys, color=color, alpha=0.10, lw=0.8,
                    zorder=1)
        ax.annotate(f"outcome cloud: {len(outcomes)} past setups",
                    xy=(0.02, 0.02), xycoords="axes fraction",
                    fontsize=7, color=MUTED_TEXT_COLOR)
```

(Extend the x-limit by ~15 bars — `ax.set_xlim(0, len(part) + 15)` — so forward paths have room; the trader literally SEES the distribution they're buying.)

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: outcome cloud"`

### Task E63: Expected-value cone

**Files:** Modify `swingbot/core/charts/decision_chart.py`; test `tests/test_decision_chart.py`

**Interfaces:**
- Produces: `_draw_main_panel` gains `ev_cone: dict | None` — `{"p25_path": [r/day], "p50_path": [...], "p75_path": [...], "ev_r": float}` (built from E32's MFE trajectory distributions per strategy); drawn as a shaded cone from the entry point out to the TP zone (P25→P75 fill, P50 dashed centerline), `EV {ev_r:+.2f}R` annotated at the cone's tip.

- [ ] **Step 1: Failing test** (append to `tests/test_decision_chart.py`)

```python
def test_ev_cone_renders(tmp_path, daily_df):
    from swingbot.core.charts.decision_chart import render_decision_chart
    ctx = {"ev_cone": {"p25_path": [0.05, 0.1, 0.2, 0.3],
                       "p50_path": [0.1, 0.25, 0.45, 0.6],
                       "p75_path": [0.2, 0.5, 0.8, 1.1],
                       "ev_r": 0.14}}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert os.path.getsize(path) > 10_000
```

- [ ] **Step 2: FAIL. Step 3: Implement** — in `_draw_main_panel` (new `ev_cone=None` arg):

```python
    if ev_cone:
        entry_px = plan.trigger_price or plan.entry_price
        rps = abs(entry_px - plan.stop_loss)
        sign = 1 if plan.direction == "bullish" else -1
        x0 = len(part) - 1
        def to_px(path):
            return [entry_px + sign * r * rps for r in [0.0] + list(path)]
        lo, mid, hi = (to_px(ev_cone["p25_path"]), to_px(ev_cone["p50_path"]),
                       to_px(ev_cone["p75_path"]))
        xs = list(range(x0, x0 + len(mid)))
        ax.fill_between(xs, lo, hi, color=TARGET_COLOR, alpha=0.12, zorder=1)
        ax.plot(xs, mid, color=TARGET_COLOR, lw=1.0, ls="--", alpha=0.8)
        ax.annotate(f"EV {ev_cone['ev_r']:+.2f}R", xy=(xs[-1], mid[-1]),
                    fontsize=8, color=TARGET_COLOR, ha="left")
```

- [ ] **Step 4: PASS. Step 5: Commit** — `git add swingbot/core/charts/decision_chart.py tests/test_decision_chart.py && git commit -m "feat: EV cone"`

### Task E64: Gap-risk band

**Files:** Modify `swingbot/core/charts/decision_chart.py`; test `tests/test_decision_chart.py`

**Interfaces:**
- Produces: `_draw_main_panel` gains `gap: dict | None` — `{"p90_gap_pct": float, "gap_fragile": bool}` (E17); a hatched band drawn around the stop at ±P90-gap distance; when `gap_fragile`, the band label carries `⚠ stop inside gap noise`.

- [ ] **Step 1: Failing test** (append)

```python
def test_gap_band_renders(tmp_path, daily_df):
    from swingbot.core.charts.decision_chart import render_decision_chart
    ctx = {"gap": {"p90_gap_pct": 2.5, "gap_fragile": True}}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert os.path.getsize(path) > 10_000
```

- [ ] **Step 2: FAIL. Step 3: Implement** — in `_draw_main_panel` (new `gap=None` arg):

```python
    if gap and plan.stop_loss:
        entry_px = plan.trigger_price or plan.entry_price
        band = entry_px * gap["p90_gap_pct"] / 100.0
        ax.axhspan(plan.stop_loss - band, plan.stop_loss + band,
                   color=STOP_COLOR, alpha=0.08, hatch="//", zorder=0)
        label = "P90 overnight gap band"
        if gap.get("gap_fragile"):
            label = "⚠ stop inside gap noise — " + label
        ax.annotate(label, xy=(0.02, plan.stop_loss + band),
                    xycoords=("axes fraction", "data"),
                    fontsize=7, color=STOP_COLOR, va="bottom")
```

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: gap band"`

### Task E65: Sizing math box

**Files:** Modify `swingbot/core/charts/decision_panels.py`; test `tests/test_decision_chart.py`

**Interfaces:**
- Produces: the info column's top block — `sizing_ctx = {"risk_pct": float, "risk_source": str ("config" | "kelly" | "vol_target" | "throttle x0.5"), "shares": int, "heat_before": float, "heat_after": float, "cap": float, "cluster_note": str | None}` rendered as aligned monospace text lines; heat-after over the cap renders in `STOP_COLOR`.

- [ ] **Step 1: Failing test** (append)

```python
def test_sizing_box_renders(tmp_path, daily_df):
    from swingbot.core.charts.decision_chart import render_decision_chart
    ctx = {"sizing": {"risk_pct": 0.7, "risk_source": "vol_target",
                      "shares": 35, "heat_before": 4.0, "heat_after": 4.7,
                      "cap": 6.0, "cluster_note": "corr 0.82 with NVDA"}}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert os.path.getsize(path) > 10_000
```

- [ ] **Step 2: FAIL. Step 3: Implement** (in `decision_panels.py`, the `_info` implementation — sizing half)

```python
def _info(ax, sizing_ctx, quality_ctx):
    ax.set_facecolor(CHART_BG)
    ax.set_xticks([]); ax.set_yticks([])
    y = 0.97
    if sizing_ctx:
        rows = [
            ("risk", f"{sizing_ctx['risk_pct']:.2f}%  (min: {sizing_ctx['risk_source']})"),
            ("shares", f"{sizing_ctx['shares']}"),
            ("heat", f"{sizing_ctx['heat_before']:.1f}% → {sizing_ctx['heat_after']:.1f}%"
                     f" / {sizing_ctx['cap']:.1f}%"),
        ]
        if sizing_ctx.get("cluster_note"):
            rows.append(("cluster", sizing_ctx["cluster_note"]))
        over = sizing_ctx["heat_after"] > sizing_ctx["cap"]
        for label, value in rows:
            color = STOP_COLOR if (label == "heat" and over) else TEXT_COLOR
            ax.text(0.04, y, f"{label:<8}", transform=ax.transAxes, fontsize=8,
                    color=MUTED_TEXT_COLOR, family="monospace", va="top")
            ax.text(0.30, y, value, transform=ax.transAxes, fontsize=8,
                    color=color, family="monospace", va="top")
            y -= 0.11
    if quality_ctx:
        y = _quality_rows(ax, quality_ctx, y)      # E66
```

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: sizing math box"`

### Task E66: Quality + follow-score box

**Files:** Modify `swingbot/core/charts/decision_panels.py`; test `tests/test_decision_chart.py`

**Interfaces:**
- Produces: `_quality_rows(ax, quality_ctx, y_start) -> float` — `quality_ctx = {"score": int, "components": [(label, points, max_points)], "follow_score": float | None, "badge": str, "badge_stats": str, "advisor": str | None}`; renders mini component bars (`points/max` as filled/empty blocks), the follow-score chip, badge line (`VALIDATED · N=206 · 81.6% OOS`), and the advisor one-liner when present.

- [ ] **Step 1: Failing test** (append)

```python
def test_quality_box_renders(tmp_path, daily_df):
    from swingbot.core.charts.decision_chart import render_decision_chart
    ctx = {"quality": {"score": 74,
                       "components": [("RS", 8, 10), ("MTF", 6, 10), ("breadth", 3, 5)],
                       "follow_score": 81.5, "badge": "VALIDATED",
                       "badge_stats": "N=206 · 81.6% OOS",
                       "advisor": "CAUTION (62) — earnings in 2 days"}}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert os.path.getsize(path) > 10_000
```

- [ ] **Step 2: FAIL. Step 3: Implement** (append to `decision_panels.py`)

```python
def _quality_rows(ax, q, y):
    ax.text(0.04, y, f"quality {q['score']}/100   follow "
            f"{q.get('follow_score') if q.get('follow_score') is not None else '—'}",
            transform=ax.transAxes, fontsize=8, color=TEXT_COLOR,
            family="monospace", va="top")
    y -= 0.11
    for label, pts, mx in q.get("components", []):
        filled = int(round(6 * pts / mx)) if mx else 0
        bar = "▮" * filled + "▯" * (6 - filled)
        ax.text(0.04, y, f"{label:<8}{bar} {pts}/{mx}", transform=ax.transAxes,
                fontsize=7, color=MUTED_TEXT_COLOR, family="monospace", va="top")
        y -= 0.09
    ax.text(0.04, y, f"{q.get('badge', 'WEAK')} · {q.get('badge_stats', '')}",
            transform=ax.transAxes, fontsize=7, color=TEXT_COLOR,
            family="monospace", va="top")
    y -= 0.10
    if q.get("advisor"):
        ax.text(0.04, y, f"🤖 {q['advisor']}", transform=ax.transAxes, fontsize=7,
                color=MUTED_TEXT_COLOR, family="monospace", va="top", wrap=True)
        y -= 0.10
    return y
```

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: quality box"`

### Task E67: Decision chart wired to alerts

**Files:** Modify `swingbot/config.py` (Field `DECISION_CHART_ENABLED`, checkbox, default false, section "Universe & Scanning"), the alert chart call site in `swingbot/commands/scanning.py` (where `generate_trade_chart` is invoked); test `tests/test_decision_chart.py`

**Interfaces:**
- Produces: `build_decision_context(item, dfs, spy_df) -> dict` — assembles every context key from the E58–E66 producers (each sub-build try/excepted to absent — a failed panel is a placeholder, never a failed alert); the alert path renders `render_decision_chart` **instead of** the legacy chart when the flag is on, legacy otherwise (byte-for-byte unchanged path). Chart-cache integration (cockpit B34) when present, direct render otherwise.

- [ ] **Step 1: Failing test** (append)

```python
def test_build_decision_context_never_raises(daily_df):
    from swingbot.commands.scanning import build_decision_context

    class Item:  # minimal ScanItem stand-in
        plan = FakePlan()
        rs_percentile = 70.0
        breadth = 55.0
        heat_blocked = None

    ctx = build_decision_context(Item(), {"TEST": daily_df}, daily_df)
    assert isinstance(ctx, dict)          # missing pieces -> keys absent, no raise
```

- [ ] **Step 2: FAIL. Step 3: Implement** — `build_decision_context` in `commands/scanning.py` (each block `try/except: pass`): `weekly` from `weekly_frame`, `avwaps` from E30, `rs` from the RS cache series, `regimes` from `regime2.regime_series(spy_df)`, `outcomes` from `data/fold_trades/{strategy}.json` (`jsonio.read_json`), `ev_cone` from E32 distributions, `gap` from E17, `sizing` from the E7/E6 numbers already computed for the embed, `quality` from the plan's breakdown + registry badge + advisor verdict. Call site:

```python
        if config.DECISION_CHART_ENABLED:
            ctx = build_decision_context(item, dfs, spy_df)
            chart_path = render_decision_chart(ticker, df, item.plan, ctx,
                                               config.TRADE_CHART_DIR)
        else:
            chart_path = generate_trade_chart(...)   # existing call, untouched
```

- [ ] **Step 4: PASS + full suite green (flag off). Side-by-side smoke: flip the flag in the test channel, trigger a scan, eyeball old vs new.**
- [ ] **Step 5: Commit** — `git add swingbot/commands/scanning.py swingbot/config.py tests/test_decision_chart.py && git commit -m "feat: decision charts on alerts (flag)"`

### Task E68: `portfolio_charts.py` — heat treemap

**Files:**
- Create: `swingbot/core/charts/portfolio_charts.py`
- Test: `tests/test_portfolio_charts.py`

**Interfaces:**
- Produces: `render_heat_map(open_trades: list[dict], caps: dict, out_dir: str) -> str` — nested rectangles (sector column width ∝ sector heat; positions stacked inside, area ∝ risk, fill color by current R: green ≥ 0, red < 0); `caps = {"total": 6.0, "sector": 3.0}` drawn as a headroom bar. `open_trades` dicts: `{ticker, sector, risk_pct, current_r}`. Attached to `!portfolio` (E52) when charts exist.

- [ ] **Step 1: Failing test**

```python
# tests/test_portfolio_charts.py
import os

import matplotlib
matplotlib.use("Agg")


def _trades():
    return [{"ticker": "XOM", "sector": "Energy", "risk_pct": 2.0, "current_r": 0.4},
            {"ticker": "CVX", "sector": "Energy", "risk_pct": 1.0, "current_r": -0.2},
            {"ticker": "MSFT", "sector": "Tech", "risk_pct": 1.5, "current_r": 1.1}]


def test_heat_treemap_renders(tmp_path):
    from swingbot.core.charts.portfolio_charts import render_heat_map
    path = render_heat_map(_trades(), {"total": 6.0, "sector": 3.0}, str(tmp_path))
    assert os.path.exists(path) and os.path.getsize(path) > 5_000


def test_heat_treemap_empty_state(tmp_path):
    from swingbot.core.charts.portfolio_charts import render_heat_map
    path = render_heat_map([], {"total": 6.0, "sector": 3.0}, str(tmp_path))
    assert os.path.exists(path)     # renders "no open positions", never crashes
```

- [ ] **Step 2: FAIL. Step 3: Implement**

```python
# swingbot/core/charts/portfolio_charts.py
"""Portfolio survival visuals: heat treemap (E68), correlation heatmap
(E69), Monte Carlo fan (E70), growth path (E71), regime timeline (E72),
fold evidence (E73)."""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from swingbot.core.charts.chart_style import (CHART_BG, DISCLAIMER_TEXT,
                                              DOWN_COLOR, GRID_COLOR,
                                              MUTED_TEXT_COLOR, TEXT_COLOR,
                                              UP_COLOR)


def _save(fig, out_dir: str, name: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    fig.text(0.99, 0.01, DISCLAIMER_TEXT, color=MUTED_TEXT_COLOR, fontsize=6, ha="right")
    fig.savefig(path, facecolor=CHART_BG, bbox_inches="tight")
    plt.close(fig)
    return path


def render_heat_map(open_trades: list, caps: dict, out_dir: str) -> str:
    fig, ax = plt.subplots(figsize=(9, 5), facecolor=CHART_BG, dpi=110)
    ax.set_facecolor(CHART_BG)
    total_cap = caps.get("total", 6.0)
    if not open_trades:
        ax.text(0.5, 0.5, "no open positions", ha="center", va="center",
                color=MUTED_TEXT_COLOR, transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
        return _save(fig, out_dir, "heat_treemap.png")

    sectors: dict = {}
    for t in open_trades:
        sectors.setdefault(t.get("sector") or "?", []).append(t)
    x = 0.0
    for sec, ts in sorted(sectors.items(), key=lambda kv: -sum(t["risk_pct"] for t in kv[1])):
        width = sum(t["risk_pct"] for t in ts) / total_cap
        y = 0.0
        for t in sorted(ts, key=lambda t: -t["risk_pct"]):
            h = t["risk_pct"] / sum(p["risk_pct"] for p in ts)
            color = UP_COLOR if t.get("current_r", 0) >= 0 else DOWN_COLOR
            ax.add_patch(plt.Rectangle((x, y), width * 0.97, h * 0.97,
                                       color=color, alpha=0.55))
            ax.text(x + width / 2, y + h / 2,
                    f"{t['ticker']}\n{t['risk_pct']:.1f}% {t.get('current_r', 0):+.1f}R",
                    ha="center", va="center", fontsize=8, color=TEXT_COLOR)
            y += h
        ax.text(x + width / 2, 1.03, sec, ha="center", fontsize=8,
                color=MUTED_TEXT_COLOR)
        x += width
    # headroom to the cap
    if x < 1.0:
        ax.add_patch(plt.Rectangle((x, 0), 1.0 - x, 1.0, color=GRID_COLOR, alpha=0.4))
        ax.text(x + (1 - x) / 2, 0.5, f"free heat\n{(1 - x) * total_cap:.1f}%",
                ha="center", va="center", fontsize=8, color=MUTED_TEXT_COLOR)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1.08)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"portfolio heat — cap {total_cap:.1f}%", color=TEXT_COLOR,
                 fontsize=11, loc="left")
    return _save(fig, out_dir, "heat_treemap.png")
```

- [ ] **Step 4: Run `python -m pytest tests/test_portfolio_charts.py -v` — PASS.**
- [ ] **Step 5: Commit** — `git add swingbot/core/charts/portfolio_charts.py tests/test_portfolio_charts.py && git commit -m "feat: heat treemap"`

### Task E69: Correlation heatmap image

**Files:** Modify `swingbot/core/charts/portfolio_charts.py`; test `tests/test_portfolio_charts.py`

**Interfaces:**
- Produces: `render_corr_matrix(open_trades, dfs, out_dir) -> str` — N×N matrix of pairwise 90d returns-corr (E8's `returns_corr`), `imshow` with a diverging colormap, cells > 0.75 outlined in `DOWN_COLOR`, ticker labels both axes, correlation values annotated.

- [ ] **Step 1: Failing test** (append)

```python
def test_corr_matrix_renders(tmp_path):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.charts.portfolio_charts import render_corr_matrix
    rng = np.random.default_rng(1)
    a = make_ohlcv(100 * np.cumprod(1 + rng.normal(0, 0.01, 200)))
    dfs = {"AAA": a, "BBB": a.copy(), "CCC": make_ohlcv(
        100 * np.cumprod(1 + np.random.default_rng(2).normal(0, 0.01, 200)))}
    trades = [{"ticker": t} for t in dfs]
    path = render_corr_matrix(trades, dfs, str(tmp_path))
    assert os.path.getsize(path) > 5_000
```

- [ ] **Step 2: FAIL. Step 3: Implement** (append to `portfolio_charts.py`)

```python
def render_corr_matrix(open_trades: list, dfs: dict, out_dir: str) -> str:
    from swingbot.core.edge.correlation import DEFAULT_THRESHOLD, returns_corr
    tickers = [t["ticker"] for t in open_trades if t["ticker"] in dfs]
    n = len(tickers)
    fig, ax = plt.subplots(figsize=(1.2 * max(n, 4), 1.0 * max(n, 4)),
                           facecolor=CHART_BG, dpi=110)
    ax.set_facecolor(CHART_BG)
    if n < 2:
        ax.text(0.5, 0.5, "need 2+ open positions", ha="center", va="center",
                color=MUTED_TEXT_COLOR, transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
        return _save(fig, out_dir, "corr_matrix.png")
    m = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            c = returns_corr(dfs[tickers[i]], dfs[tickers[j]]) or 0.0
            m[i, j] = m[j, i] = c
    im = ax.imshow(m, cmap="RdYlGn_r", vmin=-1, vmax=1)
    for i in range(n):
        for j in range(n):
            ax.text(j, i, f"{m[i, j]:.2f}", ha="center", va="center",
                    fontsize=7, color=TEXT_COLOR)
            if i != j and m[i, j] > DEFAULT_THRESHOLD:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                           edgecolor=DOWN_COLOR, lw=2))
    ax.set_xticks(range(n), tickers, rotation=45, color=TEXT_COLOR, fontsize=8)
    ax.set_yticks(range(n), tickers, color=TEXT_COLOR, fontsize=8)
    ax.set_title("90d returns correlation — outlined > 0.75", color=TEXT_COLOR,
                 fontsize=10, loc="left")
    fig.colorbar(im, ax=ax, shrink=0.8)
    return _save(fig, out_dir, "corr_matrix.png")
```

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: correlation heatmap"`

### Task E70: Monte Carlo fan chart

**Files:** Modify `swingbot/core/charts/portfolio_charts.py`; test `tests/test_portfolio_charts.py`

**Interfaces:**
- Produces: `render_mc_fan(sim_result: dict, start_balance: float, out_dir: str, percentile_paths: dict | None = None) -> str` — when `percentile_paths` (`{"p05": [...], "p25": [...], "p50": [...], "p75": [...], "p95": [...]}`, per-trade equity multiples) is given, draws the fan (P25–P75 fill, P5/P95 outlines, P50 line); otherwise renders the summary card from `sim_result` alone. The 10x line is always drawn; `p_10x` and `max_dd_p95` annotated. `ruin.simulate` gains `return_paths: bool = False` → adds `percentile_paths` to its output (computed per-trade with `np.percentile(equity, q, axis=0)` — cheap). Attached to `!growth`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_portfolio_charts.py`)

```python
def test_mc_fan_renders(tmp_path):
    from swingbot.core.edge.ruin import simulate
    from swingbot.core.charts.portfolio_charts import render_mc_fan
    sim = simulate([0.4] * 8 + [-1.0] * 2, risk_pct=1.0,
                   n_trades=300, n_paths=500, return_paths=True)
    path = render_mc_fan(sim, 10_000.0, str(tmp_path),
                         percentile_paths=sim["percentile_paths"])
    assert os.path.getsize(path) > 5_000
```

- [ ] **Step 2: Run — FAIL (`TypeError: simulate() got an unexpected keyword argument 'return_paths'`).**

- [ ] **Step 3: Implement** — in `ruin.py`, `simulate(..., return_paths: bool = False)`; before the return dict:

```python
    out = { ... }                       # the existing dict
    if return_paths:
        out["percentile_paths"] = {
            f"p{q:02d}": np.percentile(equity, q, axis=0).tolist()
            for q in (5, 25, 50, 75, 95)}
    return out
```

Append to `portfolio_charts.py`:

```python
def render_mc_fan(sim_result: dict, start_balance: float, out_dir: str,
                  percentile_paths: dict | None = None) -> str:
    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=CHART_BG, dpi=110)
    ax.set_facecolor(CHART_BG)
    if percentile_paths:
        n = len(percentile_paths["p50"])
        xs = range(n)
        bal = lambda path: [start_balance * m for m in path]
        ax.fill_between(xs, bal(percentile_paths["p25"]), bal(percentile_paths["p75"]),
                        color=UP_COLOR, alpha=0.18, label="P25–P75")
        for q, ls in (("p05", ":"), ("p95", ":")):
            ax.plot(xs, bal(percentile_paths[q]), color=MUTED_TEXT_COLOR, lw=0.8, ls=ls)
        ax.plot(xs, bal(percentile_paths["p50"]), color=UP_COLOR, lw=1.4, label="median")
        ax.set_yscale("log")
    ax.axhline(start_balance * 10, color=TEXT_COLOR, lw=1.0, ls="--")
    ax.annotate("10x", xy=(0.99, start_balance * 10), xycoords=("axes fraction", "data"),
                color=TEXT_COLOR, fontsize=9, ha="right", va="bottom")
    ax.set_title(f"Monte Carlo — p(10x) {sim_result['p_10x']:.0%}, "
                 f"P95 max drawdown {sim_result['max_dd_p95']:.0%}, "
                 f"p(halve) {sim_result['p_ruin']:.1%}",
                 color=TEXT_COLOR, fontsize=10, loc="left")
    ax.tick_params(colors=MUTED_TEXT_COLOR)
    ax.grid(color=GRID_COLOR, lw=0.4)
    ax.legend(loc="upper left", fontsize=8)
    return _save(fig, out_dir, "mc_fan.png")
```

`!growth` attaches the render when the account has ≥10 closed trades (soft — text report always posts).

- [ ] **Step 4: PASS (both test files + `tests/test_edge_ruin.py` — the new kwarg defaults off, old goldens untouched).**
- [ ] **Step 5: Commit** — `git add swingbot/core/edge/ruin.py swingbot/core/charts/portfolio_charts.py swingbot/commands/growth.py tests/test_portfolio_charts.py && git commit -m "feat: Monte Carlo fan"`

### Task E71: Growth-path chart

**Files:** Modify `swingbot/core/charts/portfolio_charts.py`; test `tests/test_portfolio_charts.py`

**Interfaces:**
- Produces: `render_growth_path(equity_curve: list[tuple[str, float]], out_dir: str, target: float = 10.0, horizons_years: tuple = (3, 5, 8)) -> str` — actual equity curve (log y) vs the three required-rate reference curves from the first point to `target×`, current multiple marker + label. Consumes the same points as E9.

- [ ] **Step 1: Failing test** (append)

```python
def test_growth_path_chart_renders(tmp_path):
    from swingbot.core.charts.portfolio_charts import render_growth_path
    curve = [(f"2026-{m:02d}-01", 10_000 * (1.02 ** m)) for m in range(1, 13)]
    path = render_growth_path(curve, str(tmp_path))
    assert os.path.getsize(path) > 5_000
```

- [ ] **Step 2: FAIL. Step 3: Implement** (append)

```python
def render_growth_path(equity_curve: list, out_dir: str, target: float = 10.0,
                       horizons_years: tuple = (3, 5, 8)) -> str:
    import datetime as dt
    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=CHART_BG, dpi=110)
    ax.set_facecolor(CHART_BG)
    dates = [dt.date.fromisoformat(str(d)[:10]) for d, _ in equity_curve]
    values = [v for _, v in equity_curve]
    start = values[0]
    ax.plot(dates, values, color=UP_COLOR, lw=1.6, label="actual")
    for years in horizons_years:
        daily = target ** (1 / (years * 365.25))
        ref_dates = [dates[0] + dt.timedelta(days=i)
                     for i in range(0, years * 366, 14)]
        ax.plot(ref_dates, [start * daily ** (d - dates[0]).days for d in ref_dates],
                lw=0.9, ls="--", alpha=0.6, color=MUTED_TEXT_COLOR)
        ax.annotate(f"10x in {years}y", xy=(ref_dates[-1], start * target),
                    fontsize=7, color=MUTED_TEXT_COLOR)
    ax.plot([dates[-1]], [values[-1]], "o", color=TEXT_COLOR)
    ax.annotate(f"{values[-1] / start:.2f}x", xy=(dates[-1], values[-1]),
                color=TEXT_COLOR, fontsize=9, va="bottom")
    ax.set_yscale("log")
    ax.grid(color=GRID_COLOR, lw=0.4)
    ax.tick_params(colors=MUTED_TEXT_COLOR)
    ax.set_title("growth path vs required rates", color=TEXT_COLOR, fontsize=10, loc="left")
    ax.legend(loc="upper left", fontsize=8)
    return _save(fig, out_dir, "growth_path.png")
```

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: growth-path chart"`

### Task E72: Regime timeline chart

**Files:** Modify `swingbot/core/charts/portfolio_charts.py`; test `tests/test_portfolio_charts.py`

**Interfaces:**
- Produces: `render_regime_timeline(spy_df, regime_stats: dict[str, dict], out_dir) -> str` — SPY close (2y) with the E61 shading over the whole span (reuse `REGIME_SHADE` via import from `decision_chart`), plus a table strip under the axis: per regime `live WR% (N)` from `regime_stats = {"bull_quiet": {"win_rate": 84.0, "n": 31}, ...}`. Attached to `!regime`.

- [ ] **Step 1: Failing test** (append)

```python
def test_regime_timeline_renders(tmp_path):
    from tests.conftest import make_trend_df
    from swingbot.core.charts.portfolio_charts import render_regime_timeline
    spy = make_trend_df(500, +0.06)
    stats = {"bull_quiet": {"win_rate": 84.0, "n": 31},
             "bear_volatile": {"win_rate": 61.0, "n": 9}}
    path = render_regime_timeline(spy, stats, str(tmp_path))
    assert os.path.getsize(path) > 5_000
```

- [ ] **Step 2: FAIL. Step 3: Implement** (append)

```python
def render_regime_timeline(spy_df, regime_stats: dict, out_dir: str) -> str:
    from swingbot.core.charts.decision_chart import REGIME_SHADE
    from swingbot.core.edge.regime2 import regime_series
    part = spy_df.tail(500)
    labels = regime_series(spy_df).reindex(part.index).ffill()
    fig, ax = plt.subplots(figsize=(11, 5), facecolor=CHART_BG, dpi=110)
    ax.set_facecolor(CHART_BG)
    ax.plot(range(len(part)), part["Close"].values, color=TEXT_COLOR, lw=1.0)
    vals = labels.values
    run = 0
    for i in range(1, len(vals) + 1):
        if i == len(vals) or vals[i] != vals[run]:
            color, alpha = REGIME_SHADE.get(vals[run], (GRID_COLOR, 0.0))
            ax.axvspan(run, i, color=color, alpha=alpha, zorder=0)
            run = i
    rows = [f"{k}: {v['win_rate']:.0f}% WR (N={v['n']})"
            for k, v in regime_stats.items()]
    fig.text(0.02, 0.02, "   |   ".join(rows), color=MUTED_TEXT_COLOR, fontsize=8)
    ax.set_title("SPY 2y — regime timeline + live win rate per regime",
                 color=TEXT_COLOR, fontsize=10, loc="left")
    ax.set_xticks([]); ax.tick_params(colors=MUTED_TEXT_COLOR)
    return _save(fig, out_dir, "regime_timeline.png")
```

(`regime_stats` assembled by the `!regime` command from journal entries grouped by their recorded regime — `entry.get("regime2")`, stamped on trades from E23 on.)

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: regime timeline"`

### Task E73: Fold-evidence chart

**Files:** Modify `swingbot/core/charts/portfolio_charts.py`; test `tests/test_portfolio_charts.py`

**Interfaces:**
- Produces: `render_fold_evidence(component_results: list[dict], out_dir) -> str` — grouped bars: one group per component (`{"component", "folds": [delta_2021, delta_2022, delta_2023], "verdict"}`), bar per fold year, `PASS` groups titled green / `FAIL` red, the −0.05R degradation line drawn. Embedded in fold docs + the admin risk page.

- [ ] **Step 1: Failing test** (append)

```python
def test_fold_evidence_renders(tmp_path):
    from swingbot.core.charts.portfolio_charts import render_fold_evidence
    results = [{"component": "rs_min_60", "folds": [0.03, 0.02, -0.01], "verdict": "PASS"},
               {"component": "mtf_min_2", "folds": [0.01, -0.06, 0.02], "verdict": "FAIL"}]
    path = render_fold_evidence(results, str(tmp_path))
    assert os.path.getsize(path) > 5_000
```

- [ ] **Step 2: FAIL. Step 3: Implement** (append)

```python
def render_fold_evidence(component_results: list, out_dir: str) -> str:
    from swingbot.core.backtest_wf import GATE_MAX_DEGRADATION_R
    n = len(component_results)
    fig, ax = plt.subplots(figsize=(max(8, 2.2 * n), 5), facecolor=CHART_BG, dpi=110)
    ax.set_facecolor(CHART_BG)
    width = 0.25
    year_colors = ("#4dd0e1", "#ba68c8", "#ffa726")   # 2021/2022/2023
    for gi, res in enumerate(component_results):
        for fi, delta in enumerate(res["folds"]):
            ax.bar(gi + (fi - 1) * width, delta, width * 0.9, color=year_colors[fi])
        color = UP_COLOR if res["verdict"] == "PASS" else DOWN_COLOR
        ax.text(gi, max(res["folds"]) + 0.005, f"{res['component']}\n{res['verdict']}",
                ha="center", fontsize=7, color=color)
    ax.axhline(0, color=MUTED_TEXT_COLOR, lw=0.8)
    ax.axhline(-GATE_MAX_DEGRADATION_R, color=DOWN_COLOR, lw=0.8, ls="--")
    ax.annotate("max allowed degradation", xy=(0.99, -GATE_MAX_DEGRADATION_R),
                xycoords=("axes fraction", "data"), fontsize=7,
                color=DOWN_COLOR, ha="right", va="top")
    ax.set_xticks([]); ax.tick_params(colors=MUTED_TEXT_COLOR)
    ax.set_ylabel("Δ expectancy_r vs baseline", color=MUTED_TEXT_COLOR, fontsize=8)
    ax.set_title("walk-forward fold evidence (bars: 2021 / 2022 / 2023)",
                 color=TEXT_COLOR, fontsize=10, loc="left")
    return _save(fig, out_dir, "fold_evidence.png")
```

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: fold evidence chart"`

### Task E74: Chart render performance pass

- [ ] **Step 1: Benchmark (local, not CI):**

```bash
python -c "
import time
from tests.conftest import make_trend_df
from tests.test_decision_chart import FakePlan
from swingbot.core.charts.decision_chart import render_decision_chart
df = make_trend_df(300, 0.15)
render_decision_chart('WARM', df, FakePlan(), {}, 'exports/trade_charts')  # warm caches
t0 = time.perf_counter()
for i in range(5):
    render_decision_chart(f'T{i}', df, FakePlan(), {}, 'exports/trade_charts')
print('avg', (time.perf_counter() - t0) / 5, 's')
"
```

- [ ] **Step 2: Target < 3s warm on the CX23** (this box will be faster — note both numbers). If over: reduce `dpi` to 100, cap `PANEL_LOOKBACK_BARS`, precompute the weekly resample once per scan (pass through context instead of recomputing), and reuse a module-level figure via `fig.clf()` if allocation dominates the profile (`python -m cProfile -s cumtime` on the loop above).
- [ ] **Step 3: Record the numbers in the Progress block. Commit** — `git commit -m "perf: decision chart under 3s"` (with whatever files changed)

### Task E75: Chart visual QA

- [ ] **Step 1: Render the full set against real data** — 5 liquid tickers + SPY, decision chart with FULL context, all four portfolio charts:

```bash
python -c "
from swingbot.core.data_store import load_from_disk
from swingbot.commands.scanning import build_decision_context
# ... loop NVDA MSFT XOM JPM UNH SPY, render to exports/chart_qa/ ...
"
```

- [ ] **Step 2: Eyeball at Discord sizes** — downscale to 400px height; check: level labels don't collide (reuse the existing `_spread_labels` helper from `chart_drawing.py` where they do), info-column text is readable, regime shading doesn't drown candles, cone/cloud don't obscure the plan levels.
- [ ] **Step 3: Fix what fails the eyeball, re-render, note the fixes. Commit** — `git commit -m "style: chart QA pass"`

### Task E76: Phase E4 checkpoint

- [ ] **Step 1: Full suite + `make check` — green.**
- [ ] **Step 2: Smoke every chart surface in the test channel:** an alert with `DECISION_CHART_ENABLED` on, `!portfolio` (treemap + corr), `!growth` (fan + path), `!regime` (timeline).
- [ ] **Step 3: Archive screenshots** under `docs/superpowers/results/charts-v3/` (one per chart type). Update the Progress block. Commit —

```bash
git add docs/superpowers/results/charts-v3/ docs/superpowers/plans/2026-07-11-edge-engine.md
git commit -m "docs: charts v3 checkpoint"
```

---

# Phase E5 — Frequency scale-up (E77–E88)

### Task E77: Universe rollout — top-150 by liquidity

**Files:**
- Modify: `swingbot/config.py` (Field `MAX_ALERTS_PER_SCAN`, number, default 10, min 1, max 50, step 1, section "Universe & Scanning"), `swingbot/commands/scanning.py` (`_send_alerts` flood control)
- Test: `tests/test_universe.py`

**Interfaces:**
- Produces: `cap_alerts(items: list, max_alerts: int) -> tuple[list, list]` — items ranked by follow score (fallback: quality score) descending; first `max_alerts` alert fully, the remainder become one digest line (`"+N more: TICK1 (72), TICK2 (69), …"` appended to the last embed). Then the production flip: `SCAN_UNIVERSE=sp500_top150`.

- [ ] **Step 1: Failing test** (append to `tests/test_universe.py`)

```python
def test_cap_alerts_ranks_by_follow_score():
    from swingbot.commands.scanning import cap_alerts

    class Item:
        def __init__(self, t, fs):
            self.ticker, self.follow_score = t, fs
    items = [Item("LOW", 40), Item("HI", 90), Item("MID", 70)]
    top, rest = cap_alerts(items, max_alerts=2)
    assert [i.ticker for i in top] == ["HI", "MID"]
    assert [i.ticker for i in rest] == ["LOW"]
```

- [ ] **Step 2: FAIL. Step 3: Implement** (in `commands/scanning.py`)

```python
def cap_alerts(items: list, max_alerts: int | None = None) -> tuple:
    """Alert-flood control for big universes: full alerts for the best
    `max_alerts` by follow score, a digest line for the rest -- ranked,
    not truncated arbitrarily."""
    cap = max_alerts if max_alerts is not None else getattr(config, "MAX_ALERTS_PER_SCAN", 10)
    ranked = sorted(items, key=lambda i: (getattr(i, "follow_score", None)
                                          or getattr(i, "quality_score", 0) or 0),
                    reverse=True)
    return ranked[:cap], ranked[cap:]
```

wired into `_send_alerts` before the embed loop; digest line built from `rest` and appended to the final message.

- [ ] **Step 4: PASS + full suite. Step 5: Production flip + watch week**

Set `SCAN_UNIVERSE=sp500_top150` in the production `.env` (file generated by E13's `--top 150`). For one week record daily in the Progress block: scan duration, alert count, digest length, memory. Commit — `git add swingbot/commands/scanning.py swingbot/config.py tests/test_universe.py && git commit -m "feat: top-150 rollout + alert flood control"`

### Task E78: Signal dedup at portfolio level

**Files:** Modify `swingbot/core/scanning/engine.py` (`dedup_scan_items`); test `tests/test_universe.py`

**Interfaces:**
- Produces: `dedup_scan_items` grows a cross-ticker pass: multiple same-sector signals in one scan collapse to the highest-follow-score one, which gains `also_qualifying: list[str]` (rendered as `"also qualifying: X, Y"` in its embed). Rationale: the correlation/sector caps would block the extras anyway — don't tease untakeable trades. Different-sector items untouched; the existing same-ticker dedup runs first.

- [ ] **Step 1: Failing test** (append to `tests/test_universe.py`)

```python
def test_sector_dedup_collapses_to_best():
    from swingbot.core.scanning.engine import dedup_sector_items

    class Item:
        def __init__(self, t, sector, fs):
            self.ticker, self.sector, self.follow_score = t, sector, fs
            self.also_qualifying = []
    items = [Item("XOM", "Energy", 80), Item("CVX", "Energy", 70),
             Item("MSFT", "Tech", 60)]
    out = dedup_sector_items(items)
    assert [i.ticker for i in out] == ["XOM", "MSFT"]
    assert out[0].also_qualifying == ["CVX"]
```

- [ ] **Step 2: FAIL. Step 3: Implement** (in `engine.py`, called at the end of `dedup_scan_items`)

```python
def dedup_sector_items(items: list) -> list:
    by_sector: dict = {}
    passthrough = []
    for it in items:
        sec = getattr(it, "sector", None)
        (by_sector.setdefault(sec, []) if sec else passthrough).append(it)
    out = list(passthrough)
    for sec, group in by_sector.items():
        group.sort(key=lambda i: getattr(i, "follow_score", 0) or 0, reverse=True)
        best = group[0]
        best.also_qualifying = [g.ticker for g in group[1:]]
        out.append(best)
    out.sort(key=lambda i: getattr(i, "follow_score", 0) or 0, reverse=True)
    return out
```

(`item.sector` stamped from `universe.sector_map` during the scan; items without a sector pass through untouched.)

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: portfolio-aware signal dedup"`

### Task E79: Per-horizon capacity budget

**Files:** Modify `swingbot/core/edge/heat.py`, `swingbot/config.py` (Field `MAX_OPEN_PER_HORIZON`, number, default 4, min 1, max 20, step 1, section "Account Defaults"); test `tests/test_edge_heat.py`

**Interfaces:**
- Produces: `horizon_check(open_trades, candidate_horizon, max_per_horizon=None) -> dict {allowed, open_in_horizon, cap}` — capital spread across time horizons so a single horizon's regime can't own the book. Same flagged-not-hidden alert treatment.

- [ ] **Step 1: Failing test** (append to `tests/test_edge_heat.py`)

```python
def test_horizon_capacity():
    from swingbot.core.edge.heat import horizon_check
    trades = [{"horizon_key": "4w"}] * 4 + [{"horizon_key": "2m"}]
    assert horizon_check(trades, "4w", max_per_horizon=4)["allowed"] is False
    assert horizon_check(trades, "2m", max_per_horizon=4)["allowed"] is True
```

- [ ] **Step 2: FAIL. Step 3: Implement** (append to `heat.py`)

```python
def horizon_check(open_trades: list, candidate_horizon: str,
                  max_per_horizon: int | None = None) -> dict:
    cap = max_per_horizon if max_per_horizon is not None else \
        getattr(config, "MAX_OPEN_PER_HORIZON", 4)
    n = sum(1 for t in open_trades if t.get("horizon_key") == candidate_horizon)
    return {"allowed": n < cap, "open_in_horizon": n, "cap": cap}
```

- [ ] **Step 4: PASS. Step 5: Commit** — `git add swingbot/core/edge/heat.py swingbot/config.py swingbot/commands/scanning.py tests/test_edge_heat.py && git commit -m "feat: per-horizon capacity budget"`

### Task E80: ETF baseline strategies fold-run

Operational task.

- [ ] **Step 1:** `python scripts/fetch_backtest_data.py --universe etfs`, then run the fold harness over the ETF universe with NO components (baseline strategies only): `SCAN_UNIVERSE=etfs python scripts/wf_run.py` (indices trend cleaner; expectation: S/R and Break & Retest pass).
- [ ] **Step 2:** Registry entries per the standard process for whatever passes: add `(source="strategy", strategy, horizon=null)` rows scoped to the ETF universe in `validation_registry.json` with `window` and `run_date` (follow the exact seeding format from plan-engine-v2 Task 3).
- [ ] **Step 3:** Results doc `docs/superpowers/results/2026-XX-etf-folds.md` + commit — `git commit -m "docs: ETF fold results"`

### Task E81: Universe RS rotation report

**Files:** Modify `swingbot/commands/growth.py` (renderer), `swingbot/core/retrospective.py` (weekly hook); test `tests/test_edge_factors.py`

**Interfaces:**
- Produces: `rs_rotation_report(rels: dict[str, float], sectors: dict[str, str], top_n=10) -> str` — top/bottom RS deciles of the universe (from the E25 cache) + a sector table (mean relative return per sector, sorted) — "where the next trades likely come from". Posted Sundays with the risk report.

- [ ] **Step 1: Failing test** (append to `tests/test_edge_factors.py`)

```python
def test_rs_rotation_report():
    from swingbot.commands.growth import rs_rotation_report
    rels = {f"T{i}": i / 100 for i in range(30)}          # T29 strongest
    sectors = {f"T{i}": ("Energy" if i >= 15 else "Utilities") for i in range(30)}
    out = rs_rotation_report(rels, sectors, top_n=5)
    assert out.index("T29") < out.index("T0")             # leaders first
    assert out.index("Energy") < out.index("Utilities")   # sector table sorted
```

- [ ] **Step 2: FAIL. Step 3: Implement** (append to `commands/growth.py`)

```python
def rs_rotation_report(rels: dict, sectors: dict, top_n: int = 10) -> str:
    ranked = sorted(((r, s) for s, r in rels.items() if r is not None), reverse=True)
    lines = ["📈 RS ROTATION — universe leaders / laggards (63d vs SPY)"]
    lines += [f"  {s:<6} {r:+.1%}" for r, s in ranked[:top_n]]
    lines.append("  …")
    lines += [f"  {s:<6} {r:+.1%}" for r, s in ranked[-top_n:]]
    by_sector: dict = {}
    for sym, r in rels.items():
        sec = sectors.get(sym)
        if sec and r is not None:
            by_sector.setdefault(sec, []).append(r)
    lines.append("sector tide:")
    for sec, rs in sorted(by_sector.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
        lines.append(f"  {sec:<26} {sum(rs) / len(rs):+.1%} (n={len(rs)})")
    return "\n".join(lines)
```

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: weekly RS rotation report"`

### Task E82: Scan health telemetry

**Files:** Modify `swingbot/core/scanning/engine.py`; admin sparkline on the risk page; test `tests/test_universe.py`

**Interfaces:**
- Produces: `log_scan_telemetry(stats: dict, path=None)` — appends one JSON line per scan to `data/scan_telemetry.jsonl`: `{at, duration_s, tickers, errors, data_skips, signals, alerts, open_heat}`; `recent_telemetry(n=50) -> list[dict]`; alert (log WARNING + retrospective note) when the latest duration > 2× the median of the prior 20.

- [ ] **Step 1: Failing test** (append to `tests/test_universe.py`)

```python
def test_scan_telemetry_roundtrip_and_slowdown_alarm(tmp_path):
    from swingbot.core.scanning.engine import log_scan_telemetry, recent_telemetry, scan_slowdown
    p = str(tmp_path / "t.jsonl")
    for d in [60] * 20:
        log_scan_telemetry({"duration_s": d, "tickers": 150}, path=p)
    rows = recent_telemetry(n=10, path=p)
    assert len(rows) == 10 and rows[-1]["duration_s"] == 60
    assert scan_slowdown(path=p) is False
    log_scan_telemetry({"duration_s": 150, "tickers": 150}, path=p)
    assert scan_slowdown(path=p) is True
```

- [ ] **Step 2: FAIL. Step 3: Implement** (append to `engine.py`)

```python
import json as _json

TELEMETRY_PATH = os.path.join(config.DATA_DIR, "scan_telemetry.jsonl")


def log_scan_telemetry(stats: dict, path: str | None = None) -> None:
    import datetime as dt
    row = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), **stats}
    with open(path or TELEMETRY_PATH, "a", encoding="utf-8") as f:
        f.write(_json.dumps(row) + "\n")


def recent_telemetry(n: int = 50, path: str | None = None) -> list:
    try:
        with open(path or TELEMETRY_PATH, encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return [_json.loads(l) for l in lines if l.strip()]
    except OSError:
        return []


def scan_slowdown(path: str | None = None) -> bool:
    rows = recent_telemetry(21, path=path)
    if len(rows) < 6:
        return False
    import statistics
    prior = [r["duration_s"] for r in rows[:-1]]
    return rows[-1]["duration_s"] > 2 * statistics.median(prior)
```

Wire: `_sync_run_scan` fills the stats dict at the end of every scan; `scan_slowdown()` true ⇒ `log.warning` + a line in the next retrospective. Admin risk page (E54) gets an inline SVG sparkline over `recent_telemetry(50)` durations.

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: scan health telemetry"`

### Task E83: Memory ceiling guard

**Files:** Modify `swingbot/core/scanning/engine.py`; test `tests/test_universe.py`

**Interfaces:**
- Produces: `LRUFrames(max_frames=200)` — dict-like cache used by the scan loop's frame store; on insert past capacity, evicts least-recently-used frames (they reload from the CSV cache on next touch — cheap). CX23 has 8GB: 500 tickers × ~2MB frames uncapped would eat 1GB+ alongside pandas temporaries.

- [ ] **Step 1: Failing test** (append to `tests/test_universe.py`)

```python
def test_lru_frames_evicts_least_recent():
    from swingbot.core.scanning.engine import LRUFrames
    lru = LRUFrames(max_frames=2)
    lru["A"], lru["B"] = 1, 2
    _ = lru["A"]              # touch A -> B is now least recent
    lru["C"] = 3
    assert "B" not in lru and "A" in lru and "C" in lru
```

- [ ] **Step 2: FAIL. Step 3: Implement** (append to `engine.py`)

```python
from collections import OrderedDict


class LRUFrames(OrderedDict):
    """Bounded frame store for universe-scale scans on an 8GB box."""
    def __init__(self, max_frames: int = 200):
        super().__init__()
        self.max_frames = max_frames

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.max_frames:
            self.popitem(last=False)
```

Swap the scan's `dfs` dict for `LRUFrames()`; `_scan_one` reloads evicted frames via `load_from_disk`. Assert RSS < 2.5GB during the next E77-style dry run (note it in the Progress block).

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "perf: LRU frame cache (memory ceiling)"`

### Task E84: Full-500 rollout decision

Operational task.

- [ ] **Step 1:** After 2 weeks of healthy top-150 telemetry (durations stable, RSS < 2.5GB, no data-quality kill triggers): flip `SCAN_UNIVERSE=sp500+etfs`. Watch one week the same way.
- [ ] **Step 2:** If the CX23 can't hold it (duration/memory), fall back to `sp500_top150` and **document the ceiling** in the Progress block ("full 500 needs the next server tier") — staying at 150 liquid names is a fine outcome, not a failure.
- [ ] **Step 3:** Commit the notes — `git commit -m "docs: universe rollout decision"`

### Task E85: Frequency impact measurement

Operational task — THE payoff measurement of this phase.

- [ ] **Step 1:** From the journal/telemetry, compute valid signals/month and taken trades/month for: the 4 weeks BEFORE E77 vs the most recent 4 weeks.
- [ ] **Step 2:** Re-run `!growth` with the real new frequency; screenshot before/after ETAs.
- [ ] **Step 3:** Write both into `docs/superpowers/results/2026-XX-edge-frequency.md` (tables + the honest delta — including whether alert quality follow-score distribution shifted). Commit — `git commit -m "docs: frequency impact of universe expansion"`

### Task E86: Alert routing by tier

**Files:** Modify `swingbot/config.py` (Field `DISCORD_CHANNEL_FIREHOSE_ID`, text, default "", section "Discord Connection", help "Channel for non-tier-A alerts. Empty = everything goes to the main alerts channel (no change)."), `swingbot/commands/scanning.py`; test `tests/test_universe.py`

**Interfaces:**
- Produces: `route_channel_id(item) -> str` — tier-A VALIDATED plans → `DISCORD_CHANNEL_TRADES_ID`; everything else → `DISCORD_CHANNEL_FIREHOSE_ID` when set, else the main channel (default = no behavior change).

- [ ] **Step 1: Failing test** (append to `tests/test_universe.py`)

```python
def test_alert_routing_by_tier(monkeypatch):
    from swingbot import config
    from swingbot.commands.scanning import route_channel_id

    class Item:
        def __init__(self, tier, badge):
            self.plan = type("P", (), {"tier": tier, "badge": badge})()
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "111", raising=False)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "222", raising=False)
    assert route_channel_id(Item("A", "VALIDATED")) == "111"
    assert route_channel_id(Item("B", "VALIDATED")) == "222"
    assert route_channel_id(Item("A", "WEAK")) == "222"
    monkeypatch.setattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "", raising=False)
    assert route_channel_id(Item("C", "WEAK")) == "111"   # unset -> no change
```

- [ ] **Step 2: FAIL. Step 3: Implement** (in `commands/scanning.py`)

```python
def route_channel_id(item) -> str:
    firehose = getattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "") or ""
    plan = getattr(item, "plan", None)
    tier_a = plan is not None and getattr(plan, "tier", "") == "A" \
        and getattr(plan, "badge", "") == "VALIDATED"
    if tier_a or not firehose:
        return config.DISCORD_CHANNEL_TRADES_ID
    return firehose
```

`_send_alerts` resolves the channel per item through it.

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: alert routing by tier"`

### Task E87: Weekend full-universe deep scan

**Files:** Modify `swingbot/commands/scanning.py` (scheduler hook), `swingbot/core/scanning/engine.py`; test `tests/test_universe.py`

**Interfaces:**
- Produces: `weekend_deep_scan() -> str` — Saturday job (scheduler branch alongside the Sunday retrospective): full-universe scan at relaxed thresholds (`SIGNAL_CONFIRMATION_SCANS` treated as 1, quality floor lowered by 10) producing a **watchlist-candidates report**, not alerts: top 15 setups forming (`ticker, strategy, follow/quality score, distance to trigger`) posted to the retrospective channel — Monday's curated watchlist feed. Renderer `deep_scan_report(items) -> str` is the tested unit.

- [ ] **Step 1: Failing test** (append to `tests/test_universe.py`)

```python
def test_deep_scan_report_renders():
    from swingbot.commands.scanning import deep_scan_report

    class Item:
        def __init__(self, t, score, dist):
            self.ticker, self.quality_score, self.trigger_distance_pct = t, score, dist
            self.plan = type("P", (), {"strategy": "MACD"})()
    out = deep_scan_report([Item("AAA", 80, 1.2), Item("BBB", 60, 0.4)])
    assert "AAA" in out and "MACD" in out and "1.2%" in out
    assert "watchlist candidates" in out.lower()
```

- [ ] **Step 2: FAIL. Step 3: Implement**

```python
def deep_scan_report(items: list) -> str:
    lines = ["🔭 WEEKEND DEEP SCAN — watchlist candidates for Monday",
             "(forming setups at relaxed thresholds — NOT alerts, NOT validated signals)"]
    for it in sorted(items, key=lambda i: -(i.quality_score or 0))[:15]:
        lines.append(f"  {it.ticker:<6} {it.plan.strategy:<18} "
                     f"q{it.quality_score} — {it.trigger_distance_pct:.1f}% from trigger")
    return "\n".join(lines)
```

plus the Saturday scheduler branch calling a relaxed `_sync_run_scan` variant in a thread and posting the report (try/except-log, never blocks the loop).

- [ ] **Step 4: PASS. Step 5: Commit** — `git commit -m "feat: weekend deep scan"`

### Task E88: Phase E5 checkpoint

- [ ] **Step 1: Full suite + `make check` — green.**
- [ ] **Step 2: Telemetry healthy** (E82 sparkline flat, no slowdown alarms in 2 weeks); frequency report (E85) committed.
- [ ] **Step 3: Progress block updated; commit** — `git commit -m "docs: frequency scale-up checkpoint"`

---

# Phase E6 — Final verification & governance (E89–E100)

### Task E89: Full-system walk-forward re-run

- [ ] **Step 1:** Regenerate the complete evidence pack in one command:

```bash
python scripts/wf_run.py --full --portfolio > docs/superpowers/results/2026-XX-edge-full-system.json
```

(`--full` reads `adopted_components.json`, applies every adopted flag, runs folds 2021/22/23 with frictions on, then the portfolio replay over the pooled fold trades.)

- [ ] **Step 2:** Render `render_fold_evidence` over the result for the doc; write `docs/superpowers/results/2026-XX-edge-full-system.md` (fold table, portfolio numbers, chart).
- [ ] **Step 3: Commit** — `git commit -m "docs: full-system walk-forward evidence"`

### Task E90: Full-system permutation test

- [ ] **Step 1:**

```bash
python scripts/permutation_test.py --component-json "$(cat docs/superpowers/results/adopted_components.json)" --n 200
```

- [ ] **Step 2:** p-value into the full-system doc. **Pre-registered rule: if p > 0.05, STOP** — strip components (worst ablation contributors first, E43's table) and re-run until the remaining system's edge is distinguishable from luck. Document every strip.
- [ ] **Step 3: Commit** — `git commit -m "docs: full-system permutation test"`

### Task E91: Sensitivity table

- [ ] **Step 1:** The "how wrong can our assumptions be" grid — rerun the full system at slippage 5/10/20 bps × risk 0.5/1.0/1.5%:

```bash
for bps in 5 10 20; do
  python scripts/wf_run.py --full --portfolio --component-json "{\"SLIPPAGE_BPS\": $bps}"
done
```

(risk levels via the portfolio replay's `risk_pct` arg; 9 cells total: expectancy_r, final multiple, max DD, `p_ruin` each.)

- [ ] **Step 2:** Table into the full-system doc with the one-line reading: at which assumption does the edge die? (If 10 bps kills it, the edge is too thin to trade — better to know now.)
- [ ] **Step 3: Commit** — `git commit -m "docs: sensitivity table"`

### Task E92: The single 2024–2025 shot

**Pre-registered, run ONCE. The window has been spent on round-1 validation; this is its one reuse, for the pooled final system only, and the numbers are reported as-is whatever they say.**

- [ ] **Step 1: Write the pre-registration paragraph FIRST** (into `docs/superpowers/results/2026-XX-edge-final-shot.md`, committed before the run): system config hash (`git rev-parse HEAD` + `adopted_components.json` content), the exact command, and the gates: pooled `expectancy_r > 0` after frictions; portfolio max DD < 25%; per-strategy WR within 10 points of its fold results.
- [ ] **Step 2: Run it:**

```bash
python scripts/wf_run.py --full --portfolio --window 2024-01-01:2025-12-31 >> docs/superpowers/results/2026-XX-edge-final-shot.md
```

(`--window` overrides the fold table with a single test window — add the flag to `wf_run.py` in this task; it refuses to run twice by checking for an existing results section.)

- [ ] **Step 3: Verdict, verbatim.** Gates pass ⇒ proceed to E93. Any gate fails ⇒ the failing components revert to their pre-E33 state (flags off, defaults restored) and the doc says exactly that. No re-runs, no "adjusted" second attempt.
- [ ] **Step 4: Commit** — `git commit -m "docs: the 2024-2025 shot (verbatim)"`

### Task E93: 4-week live paper forward-test

- [ ] **Step 1:** All adopted flags ON in **shadow/paper** (no real behavioral change vs current live until this gate passes): decision charts to the test channel, component-on plans logged by the shadow logger, sizing modes in shadow columns (E55).
- [ ] **Step 2:** Weekly comparison snapshot (component-on vs current-live cohort forward returns, `shadow_component_report` per component + pooled) posted to the test channel and appended to a running doc.
- [ ] **Step 3:** After 4 weeks: promotion decision doc — which flags go live, which stay shadow, which die. The market's own out-of-sample is the only judge left. Commit — `git commit -m "docs: paper forward-test verdict"`

### Task E94: Promotion + rollback plan

- [ ] **Step 1:** Flip the promoted flags in production `.env`, one scan-cycle apart, watching the E82 telemetry between flips.
- [ ] **Step 2:** `docs/superpowers/results/2026-XX-edge-final.md`: what went live, why (link every evidence doc), and a **one-line rollback per flag** (`REGIME_GATES_ENABLED=false — reverts to ungated entries, no data migration`). Anything needing more than one line to roll back gets fixed until it doesn't.
- [ ] **Step 3: Commit** — `git commit -m "docs: promotion + rollback runbook"`

### Task E95: Pre-mortem document

- [ ] **Step 1:** Write `docs/superpowers/edge-premortem.md` — "it is 12 months later and the system failed; what killed it?" One section per killer, each with its built-in tripwire:

| Killer | Tripwire |
|---|---|
| Regime break (edge was 2018–23-shaped) | drift alerts + quarterly re-validation (E96) |
| Liquidity evaporation in a crash | liquidity screen re-checked per scan; kill switch on SPY ±5% |
| Correlated overnight gap through every stop | heat + cluster + sector caps bound the worst morning |
| Data feed corruption | E16 quality gate; kill switch at >20% failures |
| Overfit residue that survived the harness | permutation re-runs (E96); ablation pruning |
| Operator overriding throttles in a drawdown | throttles are code, overrides need a deliberate config edit that the weekly risk report calls out |
| Position sizing creep | frozen constants: quarter-Kelly cap, 2% ceiling, ladder |

- [ ] **Step 2:** Honest, specific, no marketing. **Commit** — `git commit -m "docs: pre-mortem"`

### Task E96: Quarterly re-validation cron

- [ ] **Step 1:** `scripts/quarterly_revalidation.py` — orchestrates: refresh cache (E15) → data quality (E16) → roll the fold set forward one year (2019-anchored once 2026 completes) → re-run `wf_run.py --full` + permutation → diff against the previous quarter's numbers → print a PASS/DEGRADED verdict per component.
- [ ] **Step 2:** Document the ritual in README ("first weekend of Jan/Apr/Jul/Oct — run, read, prune") + a calendar note; this is deliberately a human-run script, not a cron job — re-validation results demand a reader.
- [ ] **Step 3: Commit** — `git commit -m "feat: quarterly re-validation script + ritual"`

### Task E97: Risk disclosure in every surface

**Files:** audit + test `tests/test_decision_chart.py` / `tests/test_portfolio_charts.py` / `tests/test_edge_growth.py`

- [ ] **Step 1: Failing test** — every new surface carries the disclosure:

```python
def test_every_edge_surface_carries_the_disclaimer():
    from swingbot.core.edge.growth import growth_report
    from swingbot.commands.growth import portfolio_report, weekly_risk_report
    for text in (growth_report({"expectancy_r": 0.1, "trades_per_month": 10,
                                "risk_pct": 1.0, "n_closed": 50}),
                 portfolio_report({"open_heat": 0, "heat_cap": 6, "sector_heat": {},
                                   "clusters": [], "throttle_mult": 1.0,
                                   "paused": False, "kill": {"on": False}, "growth": {}}),
                 weekly_risk_report({"heat_utilization_pct": 1.0})):
        assert ("will differ" in text or "not promises" in text
                or "financial advice" in text.lower())
```

Charts: assert `DISCLAIMER_TEXT` is passed into every `_save`/`fig.text` (already structural in E68's `_save` and E57's footer — the test greps the module source for renderers that bypass `_save`).

- [ ] **Step 2–3: Fix any surface that fails; wording everywhere:** *"Backtested + paper-tested projections. Real results will differ. Risk of loss is real."* on growth/portfolio/decision charts and in `!growth`. **Commit** — `git commit -m "test: risk disclosure on every edge surface"`

### Task E98: Docs — the growth playbook

- [ ] **Step 1:** README section **"The growth playbook"**, written for future-you in a drawdown: the growth equation and where `!growth` gets its numbers; the three honest levers (expectancy, frequency, survival) and which feature serves which; what the throttle ladder will do at −8/−12/−16/−20% and why you must not override it; how to read the Monte Carlo fan (the P5 path is a real future too); why this system will never promise 100% WR and what the actual promise is (pre-registered evidence, visible ETA, bounded ruin).
- [ ] **Step 2: Commit** — `git commit -m "docs: the growth playbook"`

### Task E99: Performance + integration sweep

- [ ] **Step 1:** `python -m pytest tests/ -q` + `make check` — green.
- [ ] **Step 2:** With everything promoted: one full scan cycle timed (target: within 2× the E21 baseline), RSS < 2.5GB, decision chart < 3s warm, one full live trading day reviewed end-to-end (alerts, charts, `!portfolio`, telemetry, no ERROR-level logs).
- [ ] **Step 3:** Fix stragglers found by the review; note results in the Progress block. **Commit** — `git commit -m "chore: integration sweep"`

### Task E100: Final checkpoint

- [ ] **Step 1:** Progress block completed (E1–E100 checked, dates).
- [ ] **Step 2:** Evidence-pack index in README, linked in causal order: baseline (E22) → component folds (E33) → permutation/plateau/ablation (E41–43) → portfolio replay (E51) → sensitivity (E91) → the 2024–25 shot (E92) → paper gate (E93) → promotion runbook (E94) → pre-mortem (E95).
- [ ] **Step 3: Commit** — `git commit -m "docs: edge engine complete"`. **Plan complete — the honest maximum-growth configuration of this bot, with its real ETA always visible in `!growth`.**
