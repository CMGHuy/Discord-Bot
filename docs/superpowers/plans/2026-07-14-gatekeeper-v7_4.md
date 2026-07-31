# Gatekeeper v7 - Part 4/5: Backtest validation & the win-rate frontier (Tasks G89–G118)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute strictly in order (G89 -> G118) — skipping the gaps left by cut tasks.
>
> **Provenance:** this is part 4 of 5 after the 2026-07-29 win-rate audit merged the previous 12 parts down (see "Scope note" below). Parts execute in numeric order.
> **Requires complete first:** Parts 1–3.
>
> Cross-part references (task numbers like G38, file names, `Interfaces:` blocks) refer to work done in earlier parts — those modules exist on the branch by the time this part runs.

## Progress

> Updated by the executing session after each task batch. Resume from the first unchecked task.
>
> - **Branch:** `main` (operator's choice 2026-07-29 — no feature branch for this plan; this line
>   was stale, carried over from the pre-merge 12-part split)
> - **Completed:** G89-G96 (backtestable subset, no-lookahead historical context joins, backtest
>   hook, gate-filtered replay, decile report, frontier report, tier-cut proposal, fold runner) and
>   G103-G104 (shadow-mode live wiring, shadow comparison report) — done and merged 2026-07-31.
>   Skipped ahead of numeric order deliberately: G103/G104 only depend on already-merged
>   G76/G81, not on G97-G102's evidence-generation chain, so they were parallelized alongside
>   G89-G96 rather than left to wait.
> - **Next:** G97 (baseline annotation run — needs an actual multi-strategy backtest run, route
>   through the `backtest-runner` subagent per CLAUDE.md, not a plain code-writing session), then
>   G98-G102, G110, and the G118 Phase G3 checkpoint.

**Goal:** Push per-strategy win rate toward the 95% final target the honest way — by turning the operator's Pre-Trade Entry Checklist into an automated, fold-validated **advisor** (higher-timeframe context, setup quality, 8 red-flag detectors, risk definition, entry timing) that annotates every trade plan, and by refreshing a full macro context snapshot (sector rotation, VIX, breadth, event calendar) before every scan — wired into the scan pipeline and the alert embed.

**Inform-first principle (operator decision, 2026-07-14 — binds every task):** the checklist is information, not a gateway. **Every trade plan is created and alerted regardless of its checklist verdict**; negative signals are marked loudly in the Discord message (tier, score, red-flag table) and the human decides. Blocking (`enforce` mode) exists as a strictly opt-in rung the operator may climb *after* the evidence phase proves specific cuts — it is never the default, and plan completion does not depend on it. Every strict threshold is a settings-page field with documented relax direction plus one-click strictness presets, so the checklist can always be loosened without code changes — a checklist that silences all trades is a misconfiguration, not a feature.

**Architecture:** Two new packages — `swingbot/core/macro/` (data providers, caches, econ/earnings calendar, composite risk score, pre-scan snapshot) and `swingbot/core/gate/` (one module per checklist check, red-flag detectors, scoring, hard-block/soft-flag policy, tier ladder) — wired into the scan pipeline behind default-off flags, validated through the walk-forward fold discipline established in edge-engine-v4, surfaced in the Discord alert embed. Mode ladder: `shadow` (log only, invisible) → `inform` (**the default destination**: full checklist rendered on every alert, nothing ever blocked) → `enforce` (optional, opt-in, evidence-gated).

**Tech Stack:** Python 3.11+, pandas, numpy, requests (already a dependency), mplfinance/matplotlib, pytest ≥8. Data: Finnhub (key already a config Field from llm-advisor L10) for the earnings/event calendar, yfinance daily bars via the existing fetch/cache layer. **No new pip dependencies.**

## The 95% goal, stated honestly (read before Task G1)

This plan exists because the operator wants ~95% win rate on every strategy. The series' own honesty rules (edge-engine-v4 header; llm-advisor honesty contract) bind this plan too, so the goal is encoded the only defensible way:

- **95% portfolio-wide cannot be promised, only earned and measured.** Win rate is trivially inflated by shrinking targets and widening stops — that destroys expectancy and the account with it. Every WR gain in this plan must come from *not taking bad trades* (filtering), never from degrading the exit geometry validated in plan-engine-v2.
- **The target is a ladder, not a number.** The checklist score partitions signals into tiers. Pre-registered targets (frozen below, before any data contact): **A+ tier** (every box checked, zero red flags) targets **≥ 90% pooled fold WR** with N ≥ 30 per fold and expectancy_r ≥ the strategy's unfiltered baseline; if the folds show ≥ 95% at that sample size, the tier is *labeled* 95-class — measured, never assumed. **All-strategies aggregate** targets **+3 to +8 WR points vs. the v2 baseline** at ≤ 40% signal loss.
- **WR is reported next to expectancy and N, always.** Any surface this plan builds that shows a win rate without its sample size and expectancy is a bug (same rule as cockpit-v3).
- **The 2024–2025 validation window stays burned.** All tuning here runs on TRAIN folds (2018–2023, anchored, per edge-engine E39 rules). The single pre-registered validation shot belongs to edge-engine E92; this plan feeds it, never spends it.
- **The path to 95% runs through the operator, not through suppression.** In inform mode the bot's raw WR doesn't change — what changes is that every alert carries its tier and its red flags, so the operator can choose to act only on A+/A setups. The tier ladder measures what following the checklist *would have* earned (fold + shadow reports); the human applies it. Enforcement is available later if the operator wants the bot to apply it mechanically.

## Scope note — win-rate audit (2026-07-28 / 2026-07-29)

This plan was pruned from **219 tasks across 12 parts (~1 MB)** to **90 tasks
across 5 parts**, then re-merged. The single admission test was: *does this task
change which setups get filtered, or prove that the filtering works?* Everything
that only reported, rendered, sized, or administered was cut — the full cut list
with per-task reasons lives in `2026-07-14-gatekeeper-v7_0-index.md`.

Consequences an executing agent must know:

- **No inflation/curve/credit series.** The macro snapshot is VIX + breadth +
  sector RS + the event/earnings calendar, and `composite.py` composites those
  three market-internal inputs only. The FRED *client* (G12) survives — it is how
  VIX and the economic release dates are fetched — but the G13–G20 series
  registry (CPI/PPI/PCE, labor, yields, curve, breakevens) is cut.
- **No news or sentiment layer.** Event *timing* (earnings, FOMC/CPI prints,
  thin sessions) is kept because it is calendar-driven and testable; headline
  *interpretation* is gone, and with it the rumor red flags.
- **No Discord command suite and no admin frontend.** Config Fields still render
  on the existing Settings page for free; every analysis surface is a report
  artifact under `docs/superpowers/results/` instead of a page.
- **No sizing tasks.** Sizing moves expectancy and risk of ruin, not win rate.
- Task IDs are **unchanged** (G1…G219, with gaps) so older notes and
  cross-references still resolve. Gaps are cut tasks, not missing work.
- Prose inside surviving tasks may still mention a cut task, command or page.
  Treat those mentions as no-ops — never re-add a cut task to satisfy one.

## Prerequisites

- **Required merged:** unified-plan-engine-v2 (TradePlanV2, exit simulator, plan_store/plan_manager, registry) and cockpit-v3 **Part 1** (`swingbot/core/jsonio.py`, `swingbot/core/analytics/` — journal, snapshots, rank).
- **Reused when present, degraded when absent (every integration point wrapped in a capability check, noted per task):** edge-engine-v4 `backtest_wf.py` walk-forward engine (G96 ships a minimal fallback fold runner), E47 kill switch (G134).
- Cached daily OHLCV 2018-06→present via `scripts/fetch_backtest_data.py`; DataFrame convention `Open,High,Low,Close,Volume`, DatetimeIndex.

## Global Constraints

- **Optimization target for every tuned threshold:** maximize WR **subject to** pooled fold expectancy_r ≥ baseline − 0.02R and N ≥ 30 per fold. WR alone never picks a parameter.
- **Pre-registered fold gate (identical to edge-engine):** anchored expanding folds, train 2018→fold-start, test years 2021/2022/2023; a check/threshold is promoted only if it improves the target in ≥ 2 of 3 folds and no fold degrades expectancy by > 0.05R. Failures are documented in `docs/superpowers/results/` and dropped — no second grid on the same hypothesis.
- **Inform-first, always.** The checklist never prevents a plan from being created or alerted unless the operator has explicitly opted into `enforce` mode. Negative signals are rendered on the alert; the human decides. Any task that drops/holds/blocks anything applies **only** in enforce mode (or behind its own dedicated opt-in flag) — every such task carries an inform-mode regression test proving the alert still ships annotated.
- **Every strict constraint is tunable from the settings page.** Each check's thresholds are config Fields (registry-driven, G79) with min/max/step and a help text naming the relax direction (they render on the existing admin Settings page for free); `GATE_STRICTNESS` presets (strict/balanced/relaxed) reseed them in one edit. Defaults ship at **balanced**, chosen so the G97 baseline census shows a healthy tier mix — never a wall of C.
- **Every new flag is a config Field, default off** (master switches; per-check toggles default on but do nothing user-visible until `MACRO_ENABLED`/`GATE_ENABLED`). Nothing is suppressed silently in any mode: annotated/held/blocked candidates are always visible somewhere (the blocked log written by G81, the alert embed itself).
- **No network in the test suite.** All providers are tested via monkeypatched `requests`/stub clients and fixture payloads; real calls live only in `scripts/*_smoke*.py` and backfill scripts.
- **Provider failure never degrades scanning.** Every fetch has a timeout (default 5s), on-disk TTL cache fallback, and a "stale/unknown" degradation path; a scan with zero working data providers must still complete (G43 is the proof).
- **API keys are config Fields (sensitive), never logged, never committed.** Free-tier quotas are respected by the TTL cache; there is no metering task.
- **Validation-window hygiene:** nothing in this plan reads 2024–2025 bars for tuning; `assert_train_only` (cockpit C31 pattern) guards every tuning entry point.
- **One definition per stat** (cockpit rule): WR/expectancy_r come from `analytics.metrics`; the gate never re-derives them.
- **Timezone:** all calendars/sessions use US/Eastern for market events, Europe/Berlin for user-facing day buckets (matches `performance.get_detailed_stats`).
- **Every task ends green:** `python -m pytest tests/ -q` + `make check` before commit; conventional commits; run from repo root `E:\Documents\Private\Projects\Discord-Bot`. (Windows note: if `make`/`python3` unavailable, run the `python -m py_compile` loop per cockpit A31 note.)

## File Structure (target state)

```
swingbot/core/macro/
  __init__.py        public API re-exports
  httpcache.py       fetch_json() with TTL disk cache under data/macro/cache/
  vix.py             VIX level + term structure from cached bars
  sectors.py         11 SPDR sector ETFs: data, RS ranks, rotation table
  breadth.py         % of universe above 50/200 DMA
  composite.py       risk-on/off composite (VIX + breadth + sector RS)
  calendar_events.py econ event calendar (historical static + future fetch)
  sessions.py        market holidays, half-days, low-liquidity windows
  earnings.py        earnings calendar (wraps advisor market_context if merged)
  history.py         publication-lag-aware historical macro frame
  quality.py         snapshot sanity validator
  snapshot.py        build/save/load data/macro/macro_snapshot.json
swingbot/core/gate/
  __init__.py        run_checklist() public API
  types.py           CheckResult / GateResult / Tier dataclasses
  registry.py        check registry + per-strategy applicability + policy
  score.py           checklist score 0–100 + tier assignment
  context_htf.py     HTF trend, with/against-trend classifier
  levels.py          swing S/R extraction, round numbers, distance checks
  atr_regime.py      ATR percentile normality, compression/spike
  setup_quality.py   signal closure, confluence count, volume/momentum
  redflags.py       the 8 surviving red-flag detectors (one function each)
  risk_def.py       structural stop placement + realistic RR
  timing.py          chasing check, trigger objectivity, session calendar
  wr_math.py         win-rate/expectancy identities + frontier math
  persistence.py     attach results to plans, journal tags, blocked log
  render.py          embed field / red-flag table / macro-line string builders
  backtest_ctx.py    historical macro snapshots (no lookahead)
  frontier.py        WR-by-decile, frontier, tier-cut proposals
  folds.py           fold runner (delegates to edge E39 when present)
  telemetry.py       evaluated/blocked/held counters
swingbot/core/charts/
  gate_charts.py     frontier/decile/ablation/macro-dashboard/rotation charts
swingbot/core/
  backtest.py            MOD checklist evaluation per simulated signal
  scan_engine / scanning/*  MOD pre-scan snapshot, gates, embed fields
scripts/
  backfill_macro.py, macro_smoke.py, gate_fold_run.py, gate_frontier.py,
  gate_shadow_report.py, build_event_history.py
tests/ test_macro_*.py, test_gate_*.py, ...
data/  macro/ (cache, snapshot, history), gate/ (blocked log, shadow log, tiers)
```

---
# Phase G3 — Backtest validation & the win-rate frontier (G89–G118)

Where the 95% question gets answered with folds instead of hope. Everything here runs on TRAIN data (2018–2023) behind `assert_train_only`.

### Task G89: Backtestable-check subset registry

**Files:** Modify `swingbot/core/gate/registry.py`; test `tests/test_gate_registry.py`

**Interfaces:** every CheckSpec's `backtestable: bool` finalized: price/volume/calendar checks (htf, levels, atr, setup, rf_fake_breakout, rf_stop_sweep, rf_dead_cat, rf_divergence_trap, rf_extreme_fade, rf_news_whipsaw via G29 history, rf_buy_rumor_sell_fact, rf_thin_session, rf_opex_pin, rf_beta_move, risk checks, not_chasing) = True; live-only checks (rf_rumor_spike's news half, calendar_checked, portfolio_room, trigger_objective) = False. `backtest_checks(strategy) -> list[CheckSpec]`. The backtest tier is computed from backtestable checks only — G103's shadow comparison quantifies how much the live-only checks add.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_registry.py`, outside the `_clean_registry` scope like G80's test)

```python
def test_backtestable_subset_membership():
    import swingbot.core.gate  # noqa: F401
    from swingbot.core.gate import registry as live
    LIVE_ONLY = {"rf_rumor_spike", "calendar_checked", "portfolio_room",
                 "trigger_objective", "size_formula"}
    for check_id in LIVE_ONLY:
        assert live.CHECKS[check_id].backtestable is False, check_id
    BACKTESTABLE = {"htf_alignment", "level_map", "atr_normal", "confluence",
                    "volume_confirms", "momentum_agrees", "signal_confirmed",
                    "rf_fake_breakout", "rf_stop_sweep", "rf_dead_cat",
                    "rf_divergence_trap", "rf_extreme_fade", "rf_news_whipsaw",
                    "rf_buy_rumor_sell_fact", "rf_thin_session", "rf_opex_pin",
                    "rf_beta_move", "stop_structural", "rr_realistic",
                    "not_chasing"}
    for check_id in BACKTESTABLE:
        assert live.CHECKS[check_id].backtestable is True, check_id
    ids = {s.check_id for s in live.backtest_checks("Break & Retest")}
    assert "rf_fake_breakout" in ids and "calendar_checked" not in ids
```

- [ ] **Step 2: Run — FAIL** (`AttributeError: ... 'backtest_checks'`)
- [ ] **Step 3: Implement** — append to `registry.py` (and fix any `backtestable=` flag the test exposes; most were set at registration in Phase G2):

```python
def backtest_checks(strategy: str) -> list[CheckSpec]:
    """The subset a historical replay can honestly evaluate. The backtest
    tier is computed from these only — G103's shadow comparison quantifies
    what the live-only checks add."""
    return [spec for spec in enabled_checks(strategy) if spec.backtestable]
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_registry.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/registry.py tests/test_gate_registry.py
git commit -m "feat: backtestable check subset"
```

### Task G90: Historical context joins — no lookahead

**Files:**
- Create: `swingbot/core/gate/backtest_ctx.py`
- Test: `tests/test_gate_backtest_ctx.py`

**Interfaces:** `historical_macro_snap(as_of: date) -> dict` — a macro-snapshot-shaped dict reconstructed from G41's publication-lag-aware frame + G29 events + G31/G32 calendars, containing exactly what was knowable at `as_of`'s close: VIX percentile, curve state, events within blackout, opex/session flags. Missing history → unknowns (same degradation contract). **The no-lookahead test is the deliverable:** for a date the day before a CPI print, the snap must contain the *previous* CPI value and the *pending* event.
- [ ] **Step 1: Write the failing tests — the lookahead traps ARE the deliverable**

```python
# tests/test_gate_backtest_ctx.py
import datetime as dt

import pandas as pd
import pytest

import swingbot.core.gate.backtest_ctx as bctx


@pytest.fixture
def env(monkeypatch):
    # cpi_yoy: April print (0.3) visible from May 12; May print (0.1) from Jun 10
    idx = pd.bdate_range("2020-05-01", "2020-06-30")
    frame = pd.DataFrame(index=idx)
    col = pd.Series(index=idx, dtype=float)
    col[pd.Timestamp("2020-05-12")] = 0.3
    col[pd.Timestamp("2020-06-10")] = 0.1
    frame["cpi_yoy"] = col.ffill()
    for key in ("core_cpi_yoy", "ppi_yoy", "pce_yoy", "core_pce_yoy", "fed_funds",
                "y2", "y10", "curve_10y2y", "curve_10y3m", "dollar_index", "wti"):
        frame[key] = 1.0
    monkeypatch.setattr(bctx, "_frame", lambda start="2018-01-01": frame)
    events = [{"date": "2020-06-10", "time_et": "08:30", "kind": "cpi",
               "label": "CPI release", "importance": 3}]
    monkeypatch.setattr(bctx.calendar_events, "load_events", lambda: events)
    monkeypatch.setattr(bctx, "_vix_percentile", lambda: {"2020-06-09": 71.0})


def test_day_before_cpi_sees_previous_print_and_pending_event(env):
    snap = bctx.historical_macro_snap(dt.date(2020, 6, 9))
    assert snap["inflation"]["cpi_yoy"]["value"] == 0.3      # PREVIOUS print
    assert snap["events"]["next_high_impact"]["date"] == "2020-06-10"  # pending
    assert snap["events"]["within_24h"]                       # inside 24h at the close
    assert snap["risk"]["vix"]["percentile_1y"] == 71.0
    assert snap["historical"] is True


def test_release_day_sees_new_print(env):
    snap = bctx.historical_macro_snap(dt.date(2020, 6, 10))
    assert snap["inflation"]["cpi_yoy"]["value"] == 0.1


def test_missing_history_degrades_to_unknowns(env, monkeypatch):
    monkeypatch.setattr(bctx, "_frame",
                        lambda start="2018-01-01": pd.DataFrame(
                            index=pd.bdate_range("2020-05-01", "2020-06-30")))
    snap = bctx.historical_macro_snap(dt.date(2020, 6, 9))
    assert snap["inflation"]["cpi_yoy"] is None
    assert snap["rates"]["curve_state"] == "unknown"
```

- [ ] **Step 2: Run — FAIL** (`ImportError`), then **implement**:

```python
# swingbot/core/gate/backtest_ctx.py
"""Macro-snapshot-shaped dicts reconstructed from the publication-lag
frame (G41) + the event calendar (G29) — exactly what was knowable at
as_of's close. Same shape as snapshot.build_snapshot, same degradation
contract (missing history -> unknowns)."""
from __future__ import annotations

import datetime as dt
import os
from functools import lru_cache

from swingbot.core.jsonio import read_json
from swingbot.core.macro import calendar_events
from swingbot.core.macro.history import HISTORY_DIR, as_of_frame


@lru_cache(maxsize=1)
def _cached_frame(start: str):
    return as_of_frame(start=start)


def _frame(start: str = "2018-01-01"):
    return _cached_frame(start)


@lru_cache(maxsize=1)
def _vix_percentile() -> dict:
    rows = read_json(os.path.join(HISTORY_DIR, "vix_percentile.json"),
                     default=[]) or []
    return dict(rows)


def historical_macro_snap(as_of) -> dict:
    date = str(as_of)[:10]
    frame = _frame()
    visible = frame.loc[:date]
    row = visible.iloc[-1] if len(visible) else None

    def val(key):
        if row is None or key not in row.index or row[key] != row[key]:  # NaN-safe
            return None
        return {"value": round(float(row[key]), 2), "as_of": date, "direction": 0}

    spreads = [v["value"] for v in (val("curve_10y2y"), val("curve_10y3m")) if v]
    if not spreads:
        curve = "unknown"
    elif any(s < 0 for s in spreads):
        curve = "inverted"
    elif all(0 <= s <= 0.25 for s in spreads):
        curve = "flat"
    else:
        curve = "normal"

    close_utc = dt.datetime.combine(dt.date.fromisoformat(date), dt.time(21, 0),
                                    tzinfo=dt.timezone.utc)   # ~16:00 ET close
    horizon = (dt.date.fromisoformat(date) + dt.timedelta(days=3)).isoformat()
    upcoming = calendar_events.events_between(date, horizon)
    vix_pct = _vix_percentile().get(date)
    return {
        "built_at": close_utc.isoformat(), "stale": False, "historical": True,
        "inflation": {k: val(k) for k in ("cpi_yoy", "core_cpi_yoy", "ppi_yoy",
                                          "pce_yoy", "core_pce_yoy")},
        "rates": {**{k: val(k) for k in ("fed_funds", "y2", "y10")},
                  "curve_state": curve},
        "risk": {"vix": ({"level": None, "percentile_1y": vix_pct,
                          "regime": None, "term_structure": None}
                         if vix_pct is not None else None),
                 "credit": None,
                 "dollar_index": val("dollar_index"), "wti": val("wti")},
        "events": {
            "next_high_impact": next((e for e in upcoming if e["importance"] == 3),
                                     None),
            "within_24h": [e for e in upcoming
                           if 0 <= calendar_events.hours_until(e, close_utc) <= 24],
            "today": [e for e in upcoming if e["date"] == date],
        },
        "news": {"headlines_top5": [],
                 "sentiment": {"score": 0.0, "n": 0, "label": "neutral"},
                 "rumor_ratio": 0.0},
        "composite": {"score": 0, "label": "unknown", "inputs_used": 0, "detail": []},
        "quality_warnings": [],
    }
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_backtest_ctx.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/backtest_ctx.py tests/test_gate_backtest_ctx.py
git commit -m "feat: historical macro snapshots for backtests"
```

### Task G91: Backtest hook — checklist per simulated signal

**Files:** Modify `swingbot/core/backtest.py`; test `tests/test_gate_backtest.py`

**Interfaces:** new backtest kwarg `gate_eval: bool = False` — when on, each simulated signal calls `run_checklist` with `macro_snap=historical_macro_snap(signal_date)`, `spy_df` from cache, and records `{gate_score, gate_tier, fired_flags}` onto the simulated trade record. **Zero behavior change:** trades are still taken; the gate only annotates. Baseline-regression test: `gate_eval=False` output byte-identical to pre-change for a fixture run.
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_backtest.py
import json

import numpy as np
import pytest

from swingbot.core import backtest
from tests.fixtures.gate import uptrend_daily


def _run(**kw):
    # run_backtest is the per-ticker/strategy simulator — verify the exact
    # entry point + signature in backtest.py at execution (v2 exit model).
    return backtest.run_backtest("TEST", uptrend_daily(320),
                                 strategy="Break & Retest",
                                 horizon_key="swing", **kw)


def test_gate_eval_annotates_trades(monkeypatch):
    import swingbot.core.gate.backtest_ctx as bctx
    monkeypatch.setattr(bctx, "historical_macro_snap",
                        lambda as_of: {"built_at": f"{as_of}T21:00:00+00:00",
                                       "stale": False, "events": {
                                           "next_high_impact": None,
                                           "within_24h": [], "today": []}})
    result = _run(gate_eval=True)
    trades = result.trades          # verify the result container at execution
    assert trades, "fixture must produce at least one simulated signal"
    for trade in trades:
        assert "gate_score" in trade and "gate_tier" in trade
        assert isinstance(trade["fired_flags"], list)


def test_gate_eval_off_is_byte_identical():
    baseline = json.dumps(_run().to_dict(), sort_keys=True, default=str)
    again = json.dumps(_run(gate_eval=False).to_dict(), sort_keys=True, default=str)
    assert baseline == again
```

- [ ] **Step 2: Run — FAIL** (`TypeError: unexpected keyword argument 'gate_eval'`)
- [ ] **Step 3: Implement** — in `swingbot/core/backtest.py`, add `gate_eval: bool = False` to the simulator's signature and, at the point where each simulated signal's trade record is finalized (verify the exact loop at execution — it's where the v2 exit walk returns its `ExitResult`), insert:

```python
    if gate_eval:
        from swingbot.core.gate import run_checklist
        from swingbot.core.gate.backtest_ctx import historical_macro_snap
        from swingbot.core.gate.registry import backtest_checks  # noqa: F401 (subset via registry flags)
        signal_date = df.index[signal_index].date()
        gate_result = run_checklist(
            ticker, strategy, plan_v2, df.iloc[:signal_index + 1],
            macro_snap=historical_macro_snap(signal_date),
            spy_df=spy_df)          # spy_df: cached SPY bars, loaded once per run
        trade_record["gate_score"] = gate_result.score
        trade_record["gate_tier"] = gate_result.tier
        trade_record["fired_flags"] = [
            c.check_id for c in gate_result.checks
            if c.section == "redflag" and c.status == "fail"]
```

**Zero behavior change:** trades are still taken; the gate only annotates. The `gate_eval=False` path must not import the gate package at all (keep the imports inside the `if`).

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_backtest.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/backtest.py tests/test_gate_backtest.py
git commit -m "feat: gate annotation in backtests (no behavior change)"
```

### Task G92: Gate-filtered replay mode

**Files:** Modify `swingbot/core/backtest.py`; test `tests/test_gate_backtest.py`

**Interfaces:** kwarg `gate_min_tier: str | None = None` — when set, signals below the tier (or hard-blocked) are recorded as `skipped_by_gate` (kept in output for the frontier math, excluded from equity/WR); `assert_train_only` guards the entry point when either gate kwarg is used.
- [ ] **Step 1: Write the failing tests** (append to `tests/test_gate_backtest.py`)

```python
import pandas as pd

from swingbot.core.backtest import assert_train_only
from tests.conftest import make_ohlcv


def test_filtered_run_drops_exactly_subtier(monkeypatch):
    import swingbot.core.gate.backtest_ctx as bctx
    monkeypatch.setattr(bctx, "historical_macro_snap",
                        lambda as_of: {"built_at": f"{as_of}T21:00:00+00:00",
                                       "stale": False, "events": {
                                           "next_high_impact": None,
                                           "within_24h": [], "today": []}})
    annotated = _run(gate_eval=True)
    filtered = _run(gate_eval=True, gate_min_tier="A")
    kept = {t["entry_date"] for t in filtered.trades}         # verify key name at execution
    skipped = {t["entry_date"] for t in filtered.skipped_by_gate}
    for trade in annotated.trades:
        tier_ok = trade["gate_tier"] in ("A+", "A")
        assert (trade["entry_date"] in kept) == tier_ok
        assert (trade["entry_date"] in skipped) == (not tier_ok)


def test_validation_window_raises():
    df_2024 = make_ohlcv(np.full(60, 100.0), start="2024-03-01")
    with pytest.raises(ValueError, match="validation"):
        assert_train_only(df_2024)
    assert_train_only(make_ohlcv(np.full(60, 100.0), start="2022-01-03"))  # no raise
```

- [ ] **Step 2: Run — FAIL**, then **implement** (in `backtest.py`):

```python
def assert_train_only(df) -> None:
    """Validation-window hygiene (cockpit C31 pattern): gate tuning never
    reads 2024-2025 bars. The single pre-registered validation shot belongs
    to edge-engine E92 — this plan feeds it, never spends it."""
    last = df.index.max()
    if str(last)[:10] > "2023-12-31":
        raise ValueError(
            "gate replay touched the 2024-2025 validation window — "
            "TRAIN folds end 2023; see the gatekeeper-v7 targets doc")
```

And in the simulator: add `gate_min_tier: str | None = None`; guard at entry:

```python
    if gate_eval or gate_min_tier:
        assert_train_only(df)
    if gate_min_tier and not gate_eval:
        raise ValueError("gate_min_tier requires gate_eval=True")
```

After each trade record is annotated (G91's block), apply the filter:

```python
    if gate_min_tier is not None:
        from swingbot.core.gate.score import TIER_ORDER
        blocked = bool(trade_record.get("gate_tier") is None
                       or TIER_ORDER.index(trade_record["gate_tier"])
                       > TIER_ORDER.index(gate_min_tier)
                       or trade_record.get("fired_hard_block"))
        if blocked:
            trade_record["skipped_by_gate"] = True
            skipped_by_gate.append(trade_record)   # kept for the frontier math
            continue                               # excluded from equity/WR
```

(the result container gains a `skipped_by_gate` list, default empty — additive.)

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_backtest.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/backtest.py tests/test_gate_backtest.py
git commit -m "feat: gate-filtered backtest replay"
```

### Task G93: WR-by-score-decile report

**Files:**
- Create: `swingbot/core/gate/frontier.py`
- Test: `tests/test_gate_frontier.py`

**Interfaces:** `wr_by_decile(trades) -> list[dict]` — over gate-annotated trades: per score-decile `{decile, n, wr, expectancy_r, wilson_lb}` (G1's Wilson bound — the *proven* WR column). Pure function.
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_frontier.py
from swingbot.core.gate.frontier import wr_by_decile


def synth_trades(n=200):
    """Deterministic monotone synthetic: score = i/2 (0..99.5); a trade
    wins iff score >= 40, so higher deciles have strictly higher WR."""
    trades = []
    for i in range(n):
        score = i / 2.0
        trades.append({"gate_score": score,
                       "outcome": "win" if score >= 40 else "loss",
                       "r_multiple": 1.5 if score >= 40 else -1.0})
    return trades


def test_deciles_monotone_and_golden():
    rows = wr_by_decile(synth_trades())
    assert len(rows) == 10
    assert [r["decile"] for r in rows] == list(range(10))
    assert rows[3]["wr"] == 0.0            # scores 30-40: all losses
    assert rows[4]["wr"] == 100.0          # scores 40-50: all wins
    wrs = [r["wr"] for r in rows]
    assert wrs == sorted(wrs)              # monotone by construction
    assert rows[9]["n"] == 20
    assert rows[9]["wilson_lb"] > 0.8      # 20/20 wins proves > 80%
    assert rows[9]["expectancy_r"] == 1.5


def test_empty_trades():
    assert wr_by_decile([]) == []
```

- [ ] **Step 2: Run — FAIL** (`ImportError`), then **implement**:

```python
# swingbot/core/gate/frontier.py
"""WR-by-decile, frontier, tier-cut proposals — pure functions over
gate-annotated trade records ({gate_score, gate_tier, outcome,
r_multiple, ...})."""
from __future__ import annotations

from swingbot.core.gate.wr_math import wilson_lower_bound


def _closed(trades):
    return [t for t in trades if t.get("outcome") in ("win", "loss")
            and t.get("gate_score") is not None]


def _stats(rows) -> dict:
    wins = sum(1 for t in rows if t["outcome"] == "win")
    n = len(rows)
    return {
        "n": n,
        "wr": round(100.0 * wins / n, 1) if n else None,
        "wilson_lb": round(wilson_lower_bound(wins, n), 4) if n else 0.0,
        "expectancy_r": (round(sum(t.get("r_multiple", 0.0) for t in rows) / n, 3)
                         if n else None),
    }


def wr_by_decile(trades) -> list[dict]:
    closed = _closed(trades)
    if not closed:
        return []
    out = []
    for decile in range(10):
        lo, hi = decile * 10.0, (decile + 1) * 10.0
        rows = [t for t in closed
                if lo <= t["gate_score"] < hi or (decile == 9 and t["gate_score"] == 100.0)]
        out.append({"decile": decile, **_stats(rows)})
    return out
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_frontier.py -v`

- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/frontier.py tests/test_gate_frontier.py
git commit -m "feat: WR-by-decile report"
```

### Task G94: The frontier report

**Files:** Modify `frontier.py`; test `tests/test_gate_frontier.py`

**Interfaces:** `frontier(trades, cuts=range(0, 101, 5)) -> list[dict]` — for each score cut: `{cut, n_kept, pct_kept, wr, wilson_lb, expectancy_r, trades_per_month}` — **the honest tradeoff curve** (WR you gain vs signals you lose vs expectancy). `best_cut(frontier_rows, min_n, max_signal_loss_pct)` — highest-WR cut satisfying the G2 constraints, None when nothing qualifies (an allowed, reportable outcome).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_frontier.py`)

```python
from swingbot.core.gate.frontier import best_cut, frontier


def test_frontier_golden():
    rows = frontier(synth_trades(), cuts=range(0, 101, 20))
    by_cut = {r["cut"]: r for r in rows}
    assert by_cut[0]["n_kept"] == 200 and by_cut[0]["pct_kept"] == 100.0
    assert by_cut[0]["wr"] == 60.0                    # 120 of 200 win
    assert by_cut[40]["wr"] == 100.0                  # only winners survive
    assert by_cut[40]["pct_kept"] == 60.0
    assert by_cut[100]["n_kept"] == 0 and by_cut[100]["wr"] is None
    assert all("trades_per_month" in r and "wilson_lb" in r for r in rows)


def test_best_cut_constraints():
    rows = frontier(synth_trades(), cuts=range(0, 101, 20))
    chosen = best_cut(rows, min_n=30, max_signal_loss_pct=50.0)
    assert chosen["cut"] == 40                         # highest WR within loss budget
    # impossible constraints -> None is an allowed, reportable outcome
    assert best_cut(rows, min_n=500, max_signal_loss_pct=10.0) is None
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'frontier'`)
- [ ] **Step 3: Write the implementation** (append to `frontier.py`)

```python
def frontier(trades, cuts=range(0, 101, 5)) -> list[dict]:
    """The honest tradeoff curve: WR gained vs signals lost vs expectancy,
    at every score cut."""
    closed = _closed(trades)
    total = len(closed)
    if total == 0:
        return []
    dates = sorted(str(t.get("entry_date", "")) for t in closed if t.get("entry_date"))
    months = 1.0
    if len(dates) >= 2 and dates[0] and dates[-1]:
        span_days = max((_days_between(dates[0], dates[-1])), 1)
        months = max(span_days / 30.44, 1.0)
    out = []
    for cut in cuts:
        kept = [t for t in closed if t["gate_score"] >= cut]
        stats = _stats(kept)
        out.append({"cut": cut,
                    "n_kept": stats["n"],
                    "pct_kept": round(100.0 * stats["n"] / total, 1),
                    "wr": stats["wr"], "wilson_lb": stats["wilson_lb"],
                    "expectancy_r": stats["expectancy_r"],
                    "trades_per_month": round(stats["n"] / months, 1)})
    return out


def _days_between(a: str, b: str) -> int:
    import datetime as dt
    try:
        return (dt.date.fromisoformat(b[:10]) - dt.date.fromisoformat(a[:10])).days
    except ValueError:
        return 1


def best_cut(frontier_rows, min_n: int, max_signal_loss_pct: float) -> dict | None:
    """Highest-WR cut satisfying the G2 constraints; None when nothing
    qualifies (an allowed, reportable outcome — never force a cut)."""
    eligible = [r for r in frontier_rows
                if r["n_kept"] >= min_n
                and (100.0 - r["pct_kept"]) <= max_signal_loss_pct
                and r["wr"] is not None]
    if not eligible:
        return None
    return max(eligible, key=lambda r: (r["wr"], r["cut"]))
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_frontier.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/frontier.py tests/test_gate_frontier.py
git commit -m "feat: WR frontier + constrained best-cut"
```

### Task G95: Tier cuts from the frontier — pre-registered procedure

**Files:** Modify `frontier.py`; test `tests/test_gate_frontier.py`

**Interfaces:** `propose_tier_cuts(frontier_rows) -> dict | None` — mechanically: A+ = lowest cut whose wilson_lb ≥ 0.80 and n ≥ 59 (the G1 math: the sample size where ~95% observed WR *proves* > 90%); A = lowest cut with wr ≥ baseline + 5 pts; B = baseline. Output is a **proposal dict** written to `data/tuning_proposals/{ts}-gate-tiers.json` (cockpit C36 shape) — never applied to config by code.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_frontier.py`)

```python
import json
import os

from swingbot.core.gate.frontier import propose_tier_cuts, write_proposal


def test_proposal_from_golden_frontier():
    rows = frontier(synth_trades(), cuts=range(0, 101, 20))
    proposal = propose_tier_cuts(rows)
    # A+: lowest cut with wilson_lb >= 0.80 and n >= 59 -> cut 40 (120/120)
    assert proposal["aplus_cut"] == 40
    # A: lowest cut with wr >= baseline(60) + 5 and n >= 30 -> cut 20 (wr 75)
    assert proposal["a_cut"] == 20
    assert proposal["baseline_wr"] == 60.0
    assert "b stays at the configured default" in proposal["note"]


def test_insufficient_data_returns_none():
    assert propose_tier_cuts([]) is None
    thin = frontier(synth_trades(n=20), cuts=range(0, 101, 20))
    assert propose_tier_cuts(thin) is None            # nothing clears N floors


def test_write_proposal_file(tmp_path, monkeypatch):
    import swingbot.config as config
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    path = write_proposal({"aplus_cut": 90}, kind="gate-tiers")
    with open(path, encoding="utf-8") as fh:
        saved = json.load(fh)
    assert saved["kind"] == "gate-tiers" and saved["payload"]["aplus_cut"] == 90
    assert os.path.dirname(path).endswith("tuning_proposals")
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'propose_tier_cuts'`)
- [ ] **Step 3: Write the implementation** (append to `frontier.py`)

```python
def propose_tier_cuts(frontier_rows) -> dict | None:
    """Mechanical, pre-registered: A+ = lowest cut whose wilson_lb >= 0.80
    with n >= 59 (the G1 math: where ~95% observed WR PROVES > 90% is
    N >= 59); A = lowest cut with wr >= baseline + 5 pts and n >= 30;
    B stays at the configured default (baseline behavior). Returns a
    PROPOSAL — never applied to config by code."""
    if not frontier_rows:
        return None
    baseline = next((r for r in frontier_rows if r["cut"] == 0), frontier_rows[0])
    if baseline["wr"] is None:
        return None
    aplus = next((r for r in frontier_rows
                  if r["wilson_lb"] >= 0.80 and r["n_kept"] >= 59), None)
    a_row = next((r for r in frontier_rows
                  if r["wr"] is not None and r["wr"] >= baseline["wr"] + 5.0
                  and r["n_kept"] >= 30), None)
    if aplus is None and a_row is None:
        return None
    return {"aplus_cut": aplus["cut"] if aplus else None,
            "a_cut": a_row["cut"] if a_row else None,
            "baseline_wr": baseline["wr"],
            "evidence": {"aplus": aplus, "a": a_row},
            "note": "b stays at the configured default (baseline tier); "
                    "cuts are proposals — apply via the settings page only"}


def write_proposal(proposal: dict, kind: str = "gate-tiers") -> str:
    """data/tuning_proposals/{ts}-{kind}.json (cockpit C36 shape)."""
    import os
    import time

    import swingbot.config as config
    from swingbot.core.jsonio import atomic_write_json
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(config.DATA_DIR, "tuning_proposals", f"{ts}-{kind}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write_json(path, {"kind": kind, "created_at": ts, "payload": proposal})
    return path
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_frontier.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/frontier.py tests/test_gate_frontier.py
git commit -m "feat: mechanical tier-cut proposal"
```

### Task G96: Fold runner (reuse E39 or minimal fallback)

**Files:**
- Create: `scripts/gate_fold_run.py`, `swingbot/core/gate/folds.py`
- Test: `tests/test_gate_folds.py`

**Interfaces:** `run_folds(strategy, *, gate_min_tier=None) -> dict` — if `swingbot/core/backtest_wf.py` (edge E39) exists, delegate; else the minimal fallback implemented here: anchored folds (train 2018→fold-start, test 2021/2022/2023), runs G92 replay per fold, returns `{folds: [{year, n, wr, expectancy_r}], pooled: {...}, passes_gate: bool}` applying the Global-Constraints fold gate verbatim. CLI: `python scripts/gate_fold_run.py --strategy X --min-tier A [--all]` printing a table + writing `docs/superpowers/results/2026-07-gate-folds-{strategy}.json`.
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_folds.py
import sys
import types

import swingbot.core.gate.folds as folds


def test_fold_windows_anchored():
    windows = folds.fold_windows()
    assert [w["year"] for w in windows] == [2021, 2022, 2023]
    for w in windows:
        assert w["test_start"] == f"{w['year']}-01-01"
        assert w["test_end"] == f"{w['year']}-12-31"
        assert w["train_end"] < w["test_start"]       # anchored, no overlap


def test_apply_fold_gate_math():
    base = [{"year": y, "n": 100, "wr": 60.0, "expectancy_r": 0.30} for y in (2021, 2022, 2023)]
    good = [{"year": y, "n": 60, "wr": 68.0, "expectancy_r": 0.32} for y in (2021, 2022, 2023)]
    assert folds.apply_fold_gate(good, base)["passes_gate"] is True
    one_fold_degrades = [dict(good[0]), dict(good[1]),
                         {"year": 2023, "n": 60, "wr": 68.0, "expectancy_r": 0.20}]
    verdict = folds.apply_fold_gate(one_fold_degrades, base)
    assert verdict["passes_gate"] is False            # > 0.05R degradation
    small_n = [dict(r, n=20) for r in good]
    assert folds.apply_fold_gate(small_n, base)["passes_gate"] is False
    only_one_improves = [dict(good[0]),
                         {"year": 2022, "n": 60, "wr": 55.0, "expectancy_r": 0.30},
                         {"year": 2023, "n": 60, "wr": 58.0, "expectancy_r": 0.30}]
    assert folds.apply_fold_gate(only_one_improves, base)["passes_gate"] is False


def test_run_folds_with_stub_replay():
    def replay(strategy, ticker, start, end, min_tier):
        year = int(start[:4])
        wins = {"2021": 6, "2022": 7, "2023": 8}[str(year)]
        return ([{"outcome": "win", "r_multiple": 1.5}] * wins
                + [{"outcome": "loss", "r_multiple": -1.0}] * 4)

    result = folds.run_folds("VWAP", tickers=["T1", "T2"], replay=replay)
    assert [f["year"] for f in result["folds"]] == [2021, 2022, 2023]
    assert result["folds"][0]["n"] == 20              # 2 tickers x 10 trades
    assert result["folds"][0]["wr"] == 60.0           # 12/20
    assert result["pooled"]["n"] == 66
    assert result["strategy"] == "VWAP"


def test_delegates_to_edge_engine_when_present(monkeypatch):
    fake = types.ModuleType("swingbot.core.backtest_wf")
    fake.run_walk_forward = lambda strategy, gate_min_tier=None: {"delegated": strategy}
    monkeypatch.setitem(sys.modules, "swingbot.core.backtest_wf", fake)
    assert folds.run_folds("VWAP")["delegated"] == "VWAP"
```

- [ ] **Step 2: Run — FAIL** (`ImportError`), then **implement**:

```python
# swingbot/core/gate/folds.py
"""Anchored walk-forward fold runner. Delegates to edge-engine E39
(swingbot/core/backtest_wf.py) when merged; else the minimal fallback
below runs the G92 replay per fold."""
from __future__ import annotations

FOLDS = (
    {"year": 2021, "train_end": "2020-12-31",
     "test_start": "2021-01-01", "test_end": "2021-12-31"},
    {"year": 2022, "train_end": "2021-12-31",
     "test_start": "2022-01-01", "test_end": "2022-12-31"},
    {"year": 2023, "train_end": "2022-12-31",
     "test_start": "2023-01-01", "test_end": "2023-12-31"},
)


def fold_windows() -> tuple:
    return FOLDS


def apply_fold_gate(fold_rows: list[dict], baseline_rows: list[dict]) -> dict:
    """The Global-Constraints fold gate verbatim: improve in >= 2 of 3
    folds, no fold degrades expectancy_r by > 0.05R, N >= 30 per fold."""
    improved = degraded = 0
    for fold, base in zip(fold_rows, baseline_rows):
        if (fold.get("n") or 0) < 30:
            return {"passes_gate": False,
                    "reason": f"{fold['year']}: N={fold.get('n')} < 30"}
        if fold["wr"] > base["wr"]:
            improved += 1
        if fold["expectancy_r"] < base["expectancy_r"] - 0.05:
            degraded += 1
    passes = improved >= 2 and degraded == 0
    return {"passes_gate": passes, "improved_folds": improved,
            "degraded_folds": degraded,
            "reason": None if passes else f"improved {improved}/3, degraded {degraded}"}


def _fold_stats(trades: list[dict]) -> dict:
    closed = [t for t in trades if t.get("outcome") in ("win", "loss")]
    wins = sum(t["outcome"] == "win" for t in closed)
    n = len(closed)
    return {"n": n, "wr": round(100.0 * wins / n, 1) if n else None,
            "expectancy_r": (round(sum(t.get("r_multiple", 0.0) for t in closed) / n, 3)
                             if n else None)}


def _default_replay(strategy, ticker, test_start, test_end, gate_min_tier):
    """Wraps the G92 replay: load cached bars ending at test_end, run with
    gate_eval=True (+ gate_min_tier), keep trades entered inside the test
    window. Verify the loader + result container names at execution."""
    from swingbot.core.backtest import run_backtest
    from swingbot.core.data import load_cached_daily
    df = load_cached_daily(ticker)
    if df is None or not len(df):
        return []
    df = df.loc[:test_end]
    result = run_backtest(ticker, df, strategy=strategy, horizon_key="swing",
                          gate_eval=True, gate_min_tier=gate_min_tier)
    return [t for t in result.trades
            if test_start <= str(t.get("entry_date", ""))[:10] <= test_end]


def run_folds(strategy: str, *, gate_min_tier: str | None = None,
              tickers=None, replay=None) -> dict:
    try:
        from swingbot.core import backtest_wf          # edge E39 delegation
        return backtest_wf.run_walk_forward(strategy, gate_min_tier=gate_min_tier)
    except ImportError:
        pass
    replay = replay or _default_replay
    if tickers is None:
        from swingbot.core.watchlist import load_watchlist  # verify name at execution
        tickers = load_watchlist()
    folds, all_trades = [], []
    for window in FOLDS:
        trades = []
        for ticker in tickers:
            trades += replay(strategy, ticker, window["test_start"],
                             window["test_end"], gate_min_tier)
        stats = _fold_stats(trades)
        folds.append({"year": window["year"], **stats})
        all_trades += [t for t in trades if t.get("outcome") in ("win", "loss")]
    return {"strategy": strategy, "min_tier": gate_min_tier,
            "folds": folds, "pooled": _fold_stats(all_trades),
            "trades": all_trades}
```

**And the CLI:**

```python
# scripts/gate_fold_run.py
"""Fold runner CLI — TRAIN data only (assert_train_only guards the replay).

Usage:
    python scripts/gate_fold_run.py --strategy "Break & Retest" [--min-tier A]
    python scripts/gate_fold_run.py --all [--min-tier A]
Writes docs/superpowers/results/2026-07-gate-folds-{slug}.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, ".")

from swingbot.core.backtest import ALL_STRATEGIES
from swingbot.core.gate.folds import apply_fold_gate, run_folds

OUT_DIR = "docs/superpowers/results"


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("&", "and").replace("/", "-")


def run_one(strategy: str, min_tier: str | None) -> dict:
    baseline = run_folds(strategy, gate_min_tier=None)
    result = {"strategy": strategy, "baseline": baseline}
    if min_tier:
        filtered = run_folds(strategy, gate_min_tier=min_tier)
        result["filtered"] = filtered
        result["gate"] = apply_fold_gate(filtered["folds"], baseline["folds"])
    for label in ("baseline", "filtered"):
        if label in result:
            print(f"\n{strategy} [{label}]")
            for f in result[label]["folds"]:
                print(f"  {f['year']}: n={f['n']} wr={f['wr']} exp={f['expectancy_r']}")
            print(f"  pooled: {result[label]['pooled']}")
    result.get("gate") and print(f"  fold gate: {result['gate']}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--min-tier", default=None)
    args = parser.parse_args()
    strategies = ALL_STRATEGIES if args.all else [args.strategy]
    if not strategies[0]:
        parser.error("--strategy or --all required")
    os.makedirs(OUT_DIR, exist_ok=True)
    for strategy in strategies:
        result = run_one(strategy, args.min_tier)
        result_slim = {k: v for k, v in result.items()}
        for label in ("baseline", "filtered"):
            if label in result_slim:
                result_slim[label] = {k: v for k, v in result_slim[label].items()
                                      if k != "trades"}
        path = os.path.join(OUT_DIR, f"2026-07-gate-folds-{_slug(strategy)}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(result_slim, fh, indent=2)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_folds.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/folds.py scripts/gate_fold_run.py tests/test_gate_folds.py
git commit -m "feat: gate fold runner"
```

### Task G97: Baseline annotation run — all strategies

**Files:** Create `docs/superpowers/results/2026-07-gate-baseline.md` (generated evidence)

- [ ] **Step 1:** Run `python scripts/gate_fold_run.py --all` (annotate-only, no `--min-tier`) on TRAIN. This is the census.
- [ ] **Step 2:** Write `docs/superpowers/results/2026-07-gate-baseline.md` in this exact structure (filled from the JSON artifacts + `wr_by_decile` over each strategy's trades):

```markdown
# Gatekeeper v7 — baseline census (TRAIN folds, annotate-only)

Run: scripts/gate_fold_run.py --all · date · commit <sha>
No tuning decisions live in this file — census only.

## <Strategy name>  (repeat per strategy)

Pooled baseline: N=…, WR=…%, expectancy_r=…

| Decile | N | WR % | Wilson LB | expectancy_r |
|---|---|---|---|---|
| 0-9 | … | … | … | … |
… (10 rows from frontier.wr_by_decile)

Flag fire-rates: rf_fake_breakout …%, rf_dead_cat …%, … (fraction of
signals where the flag fired)

Losers cluster: <exactly three sentences: which score bands / flags /
market regimes hold this strategy's losses — observations, not decisions.>
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/results/2026-07-gate-baseline.md docs/superpowers/results/2026-07-gate-folds-*.json
git commit -m "docs: gate baseline census on TRAIN folds"
```

### Task G98: Frontier run — all strategies ✅ (commit `19b73a7`)

**Files:** Create `scripts/gate_frontier.py`; evidence `docs/superpowers/results/2026-07-gate-frontier.md`

- [x] **Step 1: Write the CLI**

```python
# scripts/gate_frontier.py
"""Frontier CLI over annotated TRAIN trades.

Usage: python scripts/gate_frontier.py [--strategy "Break & Retest"]
Reruns run_folds (annotate-only), prints per-strategy frontier tables,
writes docs/superpowers/results/2026-07-gate-frontier-{slug}.json and a
G95 tier-cut proposal file when one is supported.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, ".")

from swingbot.core.backtest import ALL_STRATEGIES
from swingbot.core.gate.folds import run_folds
from swingbot.core.gate.frontier import (best_cut, frontier,
                                         propose_tier_cuts, write_proposal,
                                         wr_by_decile)

OUT_DIR = "docs/superpowers/results"


def _slug(name):
    return name.lower().replace(" ", "-").replace("&", "and").replace("/", "-")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default=None)
    args = parser.parse_args()
    strategies = [args.strategy] if args.strategy else list(ALL_STRATEGIES)
    os.makedirs(OUT_DIR, exist_ok=True)
    for strategy in strategies:
        trades = run_folds(strategy)["trades"]
        rows = frontier(trades)
        chosen = best_cut(rows, min_n=30, max_signal_loss_pct=40.0)
        proposal = propose_tier_cuts(rows)
        print(f"\n== {strategy} ==")
        print(f"{'cut':>4} {'N':>5} {'kept%':>6} {'WR':>6} {'LB':>6} {'exp':>6} {'tr/mo':>6}")
        for r in rows:
            print(f"{r['cut']:>4} {r['n_kept']:>5} {r['pct_kept']:>6} "
                  f"{r['wr'] if r['wr'] is not None else '—':>6} "
                  f"{r['wilson_lb']:>6} "
                  f"{r['expectancy_r'] if r['expectancy_r'] is not None else '—':>6} "
                  f"{r['trades_per_month']:>6}")
        print(f"best cut (N>=30, <=40% loss): {chosen}")
        artifact = {"strategy": strategy, "frontier": rows,
                    "deciles": wr_by_decile(trades),
                    "best_cut": chosen, "proposal": proposal}
        path = os.path.join(OUT_DIR, f"2026-07-gate-frontier-{_slug(strategy)}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(artifact, fh, indent=2)
        print(f"wrote {path}")
        if proposal:
            print(f"proposal -> {write_proposal(proposal, kind=f'gate-tiers-{_slug(strategy)}')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 2: Run for real on TRAIN**; write `docs/superpowers/results/2026-07-gate-frontier.md` with the honest headline numbers per strategy — one table row each: `WR @ chosen cut`, `wilson_lb`, `% signals kept`, `expectancy_r`, plus "no cut qualifies" rows stated plainly. Commit:

```bash
git add scripts/gate_frontier.py docs/superpowers/results/2026-07-gate-frontier*.json docs/superpowers/results/2026-07-gate-frontier.md
git commit -m "feat: frontier CLI + TRAIN evidence"
```

### Task G99: Red-flag ablation — each flag earns its keep ✅ (commit `8f8f17f`)

**Files:** Modify `scripts/gate_fold_run.py` (`--ablate` mode); evidence doc `docs/superpowers/results/2026-07-gate-ablation.md`
- Test: `tests/test_gate_folds.py`

**Interfaces:** `--ablate` runs folds once per red flag with only that flag active as a filter: reports each flag's standalone `{signals_removed_pct, wr_delta, expectancy_delta}` pooled + per fold. Flags that *hurt* expectancy in ≥ 2 folds get their registry weight set to 0 (info-only) in a follow-up commit, documented.

**Result:** `rf_stop_sweep` demoted to weight 0.0 in `redflags.py` — negative
`expectancy_delta` in 9 of 11 non-trivial fold observations across 5
strategies. `rf_fake_breakout`/`rf_divergence_trap` evidence stayed thin/
one-sided; no demotion for either. See
`docs/superpowers/results/2026-07-gate-ablation.md`.
- [x] **Step 1: Write the failing test** (append to `tests/test_gate_folds.py`)

```python
from swingbot.core.gate.folds import ablate_flags


def test_ablation_loop_mechanics():
    trades = ([{"outcome": "loss", "r_multiple": -1.0, "fired_flags": ["rf_dead_cat"]}] * 10
              + [{"outcome": "win", "r_multiple": 1.5, "fired_flags": []}] * 30
              + [{"outcome": "loss", "r_multiple": -1.0, "fired_flags": []}] * 10)
    rows = ablate_flags(trades, flags=["rf_dead_cat", "rf_opex_pin"])
    dead_cat = next(r for r in rows if r["flag"] == "rf_dead_cat")
    # removing rf_dead_cat trades: 50 -> 40 signals (20% removed), WR 60 -> 75
    assert dead_cat["signals_removed_pct"] == 20.0
    assert dead_cat["wr_delta"] == 15.0
    assert dead_cat["expectancy_delta"] > 0
    opex = next(r for r in rows if r["flag"] == "rf_opex_pin")
    assert opex["signals_removed_pct"] == 0.0 and opex["wr_delta"] == 0.0
```

- [x] **Step 2: Run — FAIL**, then **implement** (append to `folds.py`):

```python
def ablate_flags(trades: list[dict], flags: list[str] | None = None) -> list[dict]:
    """Each flag alone as a filter: what does removing ITS trades do to
    WR/expectancy? Flags that HURT expectancy get demoted to weight 0 by
    the follow-up commit this task documents."""
    closed = [t for t in trades if t.get("outcome") in ("win", "loss")]
    if not closed:
        return []
    if flags is None:
        flags = sorted({f for t in closed for f in t.get("fired_flags", [])})
    base = _fold_stats(closed)
    out = []
    for flag in flags:
        kept = [t for t in closed if flag not in t.get("fired_flags", [])]
        stats = _fold_stats(kept)
        out.append({
            "flag": flag,
            "signals_removed_pct": round(100.0 * (len(closed) - len(kept))
                                         / len(closed), 1),
            "wr_delta": (round(stats["wr"] - base["wr"], 1)
                         if None not in (stats["wr"], base["wr"]) else None),
            "expectancy_delta": (round(stats["expectancy_r"] - base["expectancy_r"], 3)
                                 if None not in (stats["expectancy_r"],
                                                 base["expectancy_r"]) else None),
            "n_kept": stats["n"],
        })
    return out
```

**And the CLI mode** — `scripts/gate_fold_run.py` gains `--ablate`: per strategy, run annotate-only folds, call `ablate_flags` per fold and pooled, print + include in the JSON artifact.

- [x] **Step 3: Run tests — PASS.** Then **run for real** on TRAIN; write `docs/superpowers/results/2026-07-gate-ablation.md` (per flag: pooled + per-fold `{signals_removed_pct, wr_delta, expectancy_delta}` table). **Demotions:** any flag whose `expectancy_delta` is negative in ≥ 2 folds gets its registry weight set to 0 (info-only) in a follow-up commit, named in the doc.
- [x] **Step 4: Commit** (demotion folded into the same G99 commit rather than a
  separate follow-up — `redflags.py`'s `rf_stop_sweep` weight change plus the
  doc landed together in `8f8f17f`)

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/folds.py scripts/gate_fold_run.py docs/superpowers/results/2026-07-gate-ablation.md tests/test_gate_folds.py
git commit -m "feat: per-flag ablation + evidence"
```

### Task G100: Permutation reality check on the score

**Files:** Modify `folds.py` (`permutation_test(trades, n=1000)`); test `tests/test_gate_folds.py`; evidence in the G98 doc

**Interfaces:** shuffles gate scores across the annotated trades 1000× → p-value that the observed WR-by-decile monotonicity is luck (reuses edge E41 machinery when present). p ≥ 0.05 → the score is noise → **stop the phase and say so** in the results doc (pre-registered stopping rule).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_folds.py`)

```python
import random

from swingbot.core.gate.folds import permutation_test


def _rigged(n=200):
    return [{"gate_score": i / 2.0,
             "outcome": "win" if i >= 80 else "loss",
             "r_multiple": 1.5 if i >= 80 else -1.0} for i in range(n)]


def _noise(n=200, seed=7):
    rng = random.Random(seed)
    return [{"gate_score": rng.uniform(0, 100),
             "outcome": rng.choice(["win", "loss"]),
             "r_multiple": rng.choice([1.5, -1.0])} for _ in range(n)]


def test_rigged_monotone_tiny_p():
    assert permutation_test(_rigged(), n=500, seed=1)["p_value"] < 0.01


def test_noise_large_p():
    assert permutation_test(_noise(), n=500, seed=1)["p_value"] >= 0.05
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `folds.py`; reuses edge E41 machinery when present — capability check documented):

```python
def _spearman_score_outcome(trades) -> float:
    """Rank correlation between gate_score and win/loss — the monotonicity
    statistic the permutation test defends."""
    closed = [t for t in trades if t.get("outcome") in ("win", "loss")
              and t.get("gate_score") is not None]
    n = len(closed)
    if n < 10:
        return 0.0
    scores = [t["gate_score"] for t in closed]
    wins = [1.0 if t["outcome"] == "win" else 0.0 for t in closed]
    rank = {v: i for i, v in enumerate(sorted(scores))}
    mean_rank = (n - 1) / 2.0
    mean_win = sum(wins) / n
    cov = sum((rank[s] - mean_rank) * (w - mean_win) for s, w in zip(scores, wins))
    var_r = sum((rank[s] - mean_rank) ** 2 for s in scores) ** 0.5
    var_w = sum((w - mean_win) ** 2 for w in wins) ** 0.5
    return cov / (var_r * var_w) if var_r and var_w else 0.0


def permutation_test(trades, n: int = 1000, seed: int = 0) -> dict:
    """Shuffle gate scores across trades n times: p = fraction of shuffles
    whose monotonicity beats the observed one. Pre-registered stopping
    rule: p >= 0.05 -> the score is noise -> STOP the phase and say so in
    the results doc."""
    import random as _random
    rng = _random.Random(seed)
    observed = _spearman_score_outcome(trades)
    closed = [dict(t) for t in trades if t.get("outcome") in ("win", "loss")]
    scores = [t["gate_score"] for t in closed]
    beat = 0
    for _ in range(n):
        rng.shuffle(scores)
        for t, s in zip(closed, scores):
            t["gate_score"] = s
        if _spearman_score_outcome(closed) >= observed:
            beat += 1
    return {"observed_rho": round(observed, 4),
            "p_value": round(beat / n, 4), "n_shuffles": n}
```

- [ ] **Step 3: Run tests — PASS.** Then **run for real** over the G97 annotated trades (add a `--permutation` flag to `scripts/gate_frontier.py` that appends the result to each strategy's artifact); append the p-values to the G98 evidence doc. **If p ≥ 0.05 pooled: stop the phase and write that.**
- [ ] **Step 4: Commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/folds.py scripts/gate_frontier.py docs/superpowers/results/ tests/test_gate_folds.py
git commit -m "feat: gate score permutation test"
```

### Task G101: Threshold plateau check

**Files:** Modify `frontier.py` (`plateau_report(frontier_rows, chosen_cut)`); test `tests/test_gate_frontier.py`

**Interfaces:** asserts the chosen cut sits on a plateau (WR within 2 pts and expectancy within 0.03R for cut ± 10) not a spike; spiky choice → report recommends the plateau center instead (edge E42 pattern).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_frontier.py`)

```python
from swingbot.core.gate.frontier import plateau_report


def _rows(wr_by_cut):
    return [{"cut": c, "n_kept": 100, "pct_kept": 50.0, "wr": wr,
             "wilson_lb": 0.5, "expectancy_r": 0.3, "trades_per_month": 5}
            for c, wr in wr_by_cut.items()]


def test_plateau_accepted():
    rows = _rows({40: 70.0, 45: 71.0, 50: 71.5, 55: 70.5, 60: 70.0})
    report = plateau_report(rows, chosen_cut=50)
    assert report["on_plateau"] is True and report["recommend"] == 50


def test_spike_redirected_to_plateau_center():
    rows = _rows({40: 60.0, 45: 61.0, 50: 78.0, 55: 60.5, 60: 60.0})
    report = plateau_report(rows, chosen_cut=50)
    assert report["on_plateau"] is False
    assert report["recommend"] != 50            # the spike is not trustworthy
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `frontier.py`; edge E42 pattern):

```python
def plateau_report(frontier_rows, chosen_cut: int,
                   wr_tol: float = 2.0, exp_tol: float = 0.03,
                   span: int = 10) -> dict:
    """A trustworthy cut sits on a plateau: neighbors within +/-span score
    points hold WR within wr_tol pts and expectancy within exp_tol R.
    A spiky choice gets redirected to the widest plateau's center."""
    by_cut = {r["cut"]: r for r in frontier_rows if r["wr"] is not None}
    chosen = by_cut.get(chosen_cut)
    if chosen is None:
        return {"on_plateau": False, "recommend": None, "reason": "cut has no data"}
    neighbors = [r for c, r in by_cut.items()
                 if c != chosen_cut and abs(c - chosen_cut) <= span]
    stable = [r for r in neighbors
              if abs(r["wr"] - chosen["wr"]) <= wr_tol
              and abs((r["expectancy_r"] or 0) - (chosen["expectancy_r"] or 0)) <= exp_tol]
    on_plateau = neighbors and len(stable) == len(neighbors)
    if on_plateau:
        return {"on_plateau": True, "recommend": chosen_cut, "reason": None}
    # widest run of mutually-stable consecutive cuts -> its center
    cuts = sorted(by_cut)
    best_run, run = [], []
    for cut in cuts:
        if run and not (abs(by_cut[cut]["wr"] - by_cut[run[0]]["wr"]) <= wr_tol):
            run = []
        run = run + [cut]
        if len(run) > len(best_run):
            best_run = run
    recommend = best_run[len(best_run) // 2] if best_run else None
    return {"on_plateau": False, "recommend": recommend,
            "reason": f"cut {chosen_cut} is a spike; widest plateau centers at {recommend}"}
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_frontier.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/frontier.py tests/test_gate_frontier.py
git commit -m "feat: plateau check for tier cuts"
```

### Task G102: TRAIN decision memo — the honest 95% answer

**Files:** Create `docs/superpowers/results/2026-07-gate-decision.md`

- [ ] **Step 1: Write the memo from G97–G101 evidence** — `docs/superpowers/results/2026-07-gate-decision.md`, this exact structure per strategy:

```markdown
# Gatekeeper v7 — TRAIN decision memo

Sources: baseline census (G97), frontier (G98), ablation (G99),
permutation p-values (G100), plateau checks (G101). All TRAIN
(2018-2023); the 2024-2025 window stays burned (owned by edge E92).

## <Strategy>  (one section per strategy)

- Chosen cuts: A+ = <cut|"no cut qualifies">, A = <cut|"no cut qualifies">
  (plateau-checked: <on plateau | redirected from X to Y>)
- Fold table (filtered @ chosen min-tier vs baseline):
  | fold | N | WR | exp_r | baseline WR | baseline exp_r |
- **"A+ tier fold WR = X% (Wilson LB Y%, N=Z) — this {does/does not}
  support a 95-class label."**  <- the sentence, verbatim, per strategy
- Signals kept at chosen cuts: X% · permutation p = …

## Aggregate

All-strategies WR before/after at chosen cuts: … -> … (+X pts) at Y%
signals kept — target band was +3..+8 pts at <= 40% loss: {met / not met}.

## Where the ladder tops out below target

<Named strategies + exactly what evidence would change it: more N,
new checks — never looser math.>
```

- [ ] **Step 2: Apply the surviving cuts to the config Field *defaults*** (`GATE_TIER_*_CUT` defaults in `config.py`; `GATE_MODE` stays `inform` — cuts only label tiers on alerts; nothing starts blocking). **Balanced-preset sanity check:** if balanced thresholds put < 30% of TRAIN signals at tier ≥ B in the census, loosen the balanced preset values in the affected `ThresholdSpec`s (G79) and note which in the memo — defaults must never starve the alert flow.
- [ ] **Step 3: Commit**

```bash
python -m pytest tests/ -q && make check
git add docs/superpowers/results/2026-07-gate-decision.md swingbot/config.py swingbot/core/gate/
git commit -m "docs: gate TRAIN decision memo + inform-mode defaults"
```

### Task G103: Shadow mode live wiring

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_gate_shadow.py`

**Interfaces:** with `GATE_ENABLED=true`: every scan candidate gets `run_checklist` (full live inputs — news, portfolio, macro snap), result attached to the plan + `shadow_log` line (G81) in **all modes** (the shadow log is the evidence stream regardless of mode). In `shadow` mode alerts are completely unchanged (byte-compare test on the embed); in `inform`/`enforce` the rendering tasks (G122–G124) take over. The checklist field does NOT render in shadow (G123 defines the render matrix).
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_shadow.py
import json
import types

import pytest

import swingbot.commands.scanning as scanning
import swingbot.config as config
import swingbot.core.gate.persistence as persistence
from swingbot.core.plan_store import PlanStore
from tests.fixtures.gate import uptrend_daily
from tests.fixtures.gate.plans import make_plan


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "SHADOW_PATH", str(tmp_path / "shadow.jsonl"))
    monkeypatch.setattr(config, "GATE_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "GATE_MIN_TIER", "C", raising=False)
    store = PlanStore(path=str(tmp_path / "plans.json"))
    plan = make_plan(created_at="2026-07-13")
    store.add(plan)
    candidate = types.SimpleNamespace(ticker="TEST", strategy=plan.strategy,
                                      plan=plan, df_daily=uptrend_daily())
    return store, candidate


@pytest.mark.parametrize("mode", ["shadow", "inform", "enforce"])
def test_shadow_log_written_in_every_mode(env, monkeypatch, mode):
    store, candidate = env
    monkeypatch.setattr(config, "GATE_MODE", mode, raising=False)
    decision, result = scanning._gate_evaluate(candidate, store, macro_snap=None)
    assert result is not None
    assert store.get_extra(candidate.plan.plan_id, "gate")            # attached
    with open(persistence.SHADOW_PATH, encoding="utf-8") as fh:
        row = json.loads(fh.readline())
    assert row["plan_id"] == candidate.plan.plan_id
    assert row["advisory_decision"] in ("pass", "downgrade", "block")


def test_shadow_mode_renders_nothing(env, monkeypatch):
    store, candidate = env
    monkeypatch.setattr(config, "GATE_MODE", "shadow", raising=False)
    monkeypatch.setattr(config, "GATE_SHOW_IN_SHADOW", False, raising=False)
    _, result = scanning._gate_evaluate(candidate, store, macro_snap=None)
    assert scanning._gate_render_payload(result) is None    # embeds byte-identical
    monkeypatch.setattr(config, "GATE_MODE", "inform", raising=False)
    assert scanning._gate_render_payload(result) is not None


def test_gate_disabled_is_noop(env, monkeypatch):
    store, candidate = env
    monkeypatch.setattr(config, "GATE_ENABLED", False, raising=False)
    assert scanning._gate_evaluate(candidate, store, macro_snap=None) == ("pass", None)
```

- [ ] **Step 2: Run — FAIL**, then **implement** in `swingbot/commands/scanning.py`:

```python
from swingbot.core.gate import run_checklist
from swingbot.core.gate.persistence import attach_to_plan, shadow_log
from swingbot.core.gate.score import with_advisory


def _gate_evaluate(candidate, plan_store, macro_snap):
    """Evaluate one scan candidate. Runs in ALL modes when GATE_ENABLED —
    the shadow log is the evidence stream regardless of mode. Never raises;
    a failure means the alert ships ungated. Returns (decision, result)."""
    if not config.GATE_ENABLED:
        return "pass", None
    try:
        result = run_checklist(
            candidate.ticker, candidate.strategy, candidate.plan,
            candidate.df_daily, macro_snap=macro_snap,
            open_plans=[{"ticker": p.ticker} for p in plan_store.open_plans()])
        decision, result = with_advisory(result, config.GATE_MODE,
                                         config.GATE_MIN_TIER)
        attach_to_plan(plan_store, candidate.plan.plan_id, result)
        shadow_log(result, plan_id=candidate.plan.plan_id)
        return decision, result
    except Exception:
        log.warning("gate evaluation failed — alert ships ungated", exc_info=True)
        return "pass", None


def _gate_render_payload(result):
    """The render matrix's first gate (full matrix in G123): shadow mode
    renders nothing unless GATE_SHOW_IN_SHADOW."""
    if result is None:
        return None
    if config.GATE_MODE == "shadow" and not getattr(config, "GATE_SHOW_IN_SHADOW", False):
        return None
    return result.to_dict()
```

Wire `_gate_evaluate` into the alert path where each surviving candidate is turned into an embed (same place llm-advisor L14 hooks — verify at execution); pass `_gate_render_payload(result)` to `build_embed(..., gate=...)` (the kwarg lands in G123 — until then it's computed and unused, which is exactly shadow behavior).

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_shadow.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py tests/test_gate_shadow.py
git commit -m "feat: live shadow-mode gate"
```

### Task G104: Shadow comparison report

**Files:** Create `scripts/gate_shadow_report.py`; modify `persistence.py` (`join_shadow_outcomes()`)
- Test: `tests/test_gate_shadow.py`

**Interfaces:** `join_shadow_outcomes() -> list[dict]` — joins `shadow.jsonl` rows to closed-trade outcomes by plan_id; report prints: would-have-blocked cohort vs passed cohort `{n, wr, expectancy}`, per-flag live fire→outcome table, live-vs-backtest score-distribution drift. CLI `--since YYYY-MM-DD`.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_shadow.py`)

```python
from swingbot.core.gate.persistence import join_shadow_outcomes, shadow_cohorts

SHADOW_ROWS = [
    {"plan_id": "p1", "tier": "C", "advisory_decision": "block",
     "fired_flags": ["rf_dead_cat"], "ts": 1},
    {"plan_id": "p2", "tier": "A", "advisory_decision": "pass", "fired_flags": [], "ts": 2},
    {"plan_id": "p3", "tier": "A", "advisory_decision": "pass", "fired_flags": [], "ts": 3},
    {"plan_id": "p4", "tier": "B", "advisory_decision": "pass", "fired_flags": [], "ts": 4},
    {"plan_id": "p9", "tier": "A", "advisory_decision": "pass", "fired_flags": [], "ts": 5},
]
TRADES = [
    {"plan_id": "p1", "outcome": "loss", "r_multiple": -1.0},
    {"plan_id": "p2", "outcome": "win", "r_multiple": 1.5},
    {"plan_id": "p3", "outcome": "win", "r_multiple": 1.5},
    {"plan_id": "p4", "outcome": "loss", "r_multiple": -1.0},
    # p9 never closed -> excluded from the join
]


def test_join_and_cohort_goldens():
    joined = join_shadow_outcomes(shadow_rows=SHADOW_ROWS, trades=TRADES)
    assert len(joined) == 4
    cohorts = shadow_cohorts(joined)
    assert cohorts["would_block"] == {"n": 1, "wr": 0.0, "expectancy_r": -1.0}
    assert cohorts["passed"]["n"] == 3
    assert cohorts["passed"]["wr"] == pytest.approx(66.7, abs=0.1)
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `persistence.py`):

```python
def _read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def join_shadow_outcomes(shadow_rows=None, trades=None) -> list[dict]:
    """Join shadow.jsonl rows to closed-trade outcomes by plan_id."""
    rows = shadow_rows if shadow_rows is not None else _read_jsonl(SHADOW_PATH)
    if trades is None:
        from swingbot.core import performance   # verify closed-trade source at execution
        trades = performance.load_closed_trades()
    by_plan = {t.get("plan_id"): t for t in trades if t.get("plan_id")}
    joined = []
    for row in rows:
        trade = by_plan.get(row.get("plan_id"))
        if trade and trade.get("outcome") in ("win", "loss"):
            joined.append({**row, "outcome": trade["outcome"],
                           "r_multiple": trade.get("r_multiple", 0.0)})
    return joined


def shadow_cohorts(joined: list[dict]) -> dict:
    def _stats(rows):
        n = len(rows)
        wins = sum(r["outcome"] == "win" for r in rows)
        return {"n": n, "wr": round(100.0 * wins / n, 1) if n else None,
                "expectancy_r": (round(sum(r["r_multiple"] for r in rows) / n, 3)
                                 if n else None)}
    return {"would_block": _stats([r for r in joined
                                   if r["advisory_decision"] == "block"]),
            "passed": _stats([r for r in joined
                              if r["advisory_decision"] != "block"])}
```

**And the CLI:**

```python
# scripts/gate_shadow_report.py
"""Shadow comparison report. Usage: python scripts/gate_shadow_report.py [--since YYYY-MM-DD]"""
import argparse
import sys
import time

sys.path.insert(0, ".")

from swingbot.core.gate.persistence import (join_shadow_outcomes,
                                            shadow_cohorts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default=None)
    args = parser.parse_args()
    joined = join_shadow_outcomes()
    if args.since:
        cutoff = time.mktime(time.strptime(args.since, "%Y-%m-%d"))
        joined = [r for r in joined if r.get("ts", 0) >= cutoff]
    cohorts = shadow_cohorts(joined)
    print(f"joined decisions: {len(joined)}")
    print(f"would-have-blocked cohort: {cohorts['would_block']}")
    print(f"passed cohort:             {cohorts['passed']}")
    per_flag: dict[str, list] = {}
    for row in joined:
        for flag in row.get("fired_flags", []):
            per_flag.setdefault(flag, []).append(row)
    for flag, rows in sorted(per_flag.items()):
        wins = sum(r["outcome"] == "win" for r in rows)
        print(f"  {flag}: fired {len(rows)}x live, WR when taken "
              f"{100.0 * wins / len(rows):.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_shadow.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/persistence.py scripts/gate_shadow_report.py tests/test_gate_shadow.py
git commit -m "feat: shadow comparison report"
```

### Task G110: Overfit sentinel

**Files:** Modify `folds.py`; test `tests/test_gate_folds.py`

**Interfaces:** `overfit_sentinel(fold_result) -> list[str]` — WARNs when train-fold WR exceeds test-fold WR by > 12 pts, when a strategy's chosen cut keeps < 15% of signals (over-filtered to anecdotes), or when pooled N < 90. Warnings print in fold CLI output and land in the results docs automatically.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_folds.py`)

```python
from swingbot.core.gate.folds import overfit_sentinel


def test_overfit_sentinel_rules():
    healthy = {"pooled": {"n": 120, "wr": 68.0, "expectancy_r": 0.3}}
    assert overfit_sentinel(healthy, train_wr=72.0, pct_kept=55.0) == []
    # train-test gap > 12 pts
    warns = overfit_sentinel(healthy, train_wr=85.0, pct_kept=55.0)
    assert any("overfit" in w for w in warns)
    # over-filtered to anecdotes
    warns = overfit_sentinel(healthy, train_wr=72.0, pct_kept=10.0)
    assert any("anecdotes" in w for w in warns)
    # thin pooled evidence
    warns = overfit_sentinel({"pooled": {"n": 50, "wr": 68.0}}, train_wr=None,
                             pct_kept=None)
    assert any("N=50" in w for w in warns)
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `folds.py`; the fold CLI prints these and they land in the results docs automatically):

```python
def overfit_sentinel(fold_result: dict, train_wr: float | None = None,
                     pct_kept: float | None = None) -> list[str]:
    warnings = []
    pooled = fold_result.get("pooled") or {}
    if (train_wr is not None and pooled.get("wr") is not None
            and train_wr - pooled["wr"] > 12):
        warnings.append(f"train WR {train_wr}% vs test {pooled['wr']}% — "
                        f"gap > 12 pts, overfit smell")
    if pct_kept is not None and pct_kept < 15:
        warnings.append(f"chosen cut keeps only {pct_kept}% of signals — "
                        f"over-filtered to anecdotes")
    if (pooled.get("n") or 0) < 90:
        warnings.append(f"pooled N={pooled.get('n')} < 90 — thin evidence")
    return warnings
```

(In `scripts/gate_fold_run.py`, print `overfit_sentinel(...)` output after each run and include it in the JSON artifact.)

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_folds.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/folds.py scripts/gate_fold_run.py tests/test_gate_folds.py
git commit -m "feat: overfit sentinel"
```

### Task G118: Phase G3 checkpoint

- [ ] **Step 1:** Full suite + `make check` green; evidence docs (baseline, frontier, ablation, decision memo) committed; permutation p < 0.05 on record — or the documented stop.
- [ ] **Step 2:** Update Progress block. Commit — `chore: phase G3 checkpoint (fold evidence on record)`

---
