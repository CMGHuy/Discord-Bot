# Gatekeeper v7 - Part 3/5: Checklist engine — HTF context, setup quality, red flags, risk & timing (Tasks G45–G88)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute strictly in order (G45 -> G88) — skipping the gaps left by cut tasks.
>
> **Provenance:** this is part 3 of 5 after the 2026-07-29 win-rate audit merged the previous 12 parts down (see "Scope note" below). Parts execute in numeric order.
> **Requires complete first:** Parts 1–2.
>
> Cross-part references (task numbers like G38, file names, `Interfaces:` blocks) refer to work done in earlier parts — those modules exist on the branch by the time this part runs.

## Progress

> Updated by the executing session after each task batch. Resume from the first unchecked task.
>
> - **Branch:** `main` (operator's choice 2026-07-29 — no feature branch for this plan)
> - **Completed:** —
> - **Next:** Task G45

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
# Phase G2 — The checklist engine: every box becomes a check (G45–G88)

One module per checklist section; one task per check. Every check task follows the same contract: pure function `(df_daily, plan, macro_snap, **ctx) -> CheckResult`, registered in `registry.CHECKS` with its weight/policy row, tested against the G7 golden scenarios, and given a config Field `GATE_CHECK_<ID>` (checkbox, default on — the master `GATE_ENABLED`/`GATE_MODE` still governs visibility, and nothing blocks outside opt-in enforce). **Every numeric cutoff named in these tasks (volume multiples, ATR bands, percentiles, wick ratios, RSI/ADX bounds, distances, day counts) is a `ThresholdSpec`** (G5) with strict/balanced/relaxed preset values — the numbers written below are the *balanced* defaults, tunable from the settings page (G79/G180), never hardcoded. Weights in parentheses are initial values; G78 calibrates, G96+ validates. Statuses are information: `fail` renders as ⛔ on the alert; it stops nothing by itself.

## Section 1 — Higher-timeframe context

### Task G45: HTF trend detector

**Files:**
- Create: `swingbot/core/gate/context_htf.py`
- Test: `tests/test_gate_context_htf.py`

**Interfaces:**
- Produces: `htf_trend(df_daily) -> dict` — weekly resample; trend from 10w vs 40w SMA + last-pivot structure: `"up"` (10w > 40w and higher highs/lows over last 8 pivots), `"down"` (mirror), `"range"` otherwise; returns `{weekly, daily, detail}` (daily uses 20/50 SMA same logic). If edge-engine E27 (MTF alignment) is merged, consume its primitives instead of duplicating resample logic.

**Shared test factory (created here, reused by every check task):**

```python
# tests/fixtures/gate/plans.py
"""Minimal TradePlanV2 factory for gate tests. Verify the horizon_key
values against HORIZONS at execution."""
from swingbot.core.plan_engine import TradePlanV2


def make_plan(**overrides) -> TradePlanV2:
    base = dict(
        plan_id="p_test_0001", ticker="TEST", created_at="2026-07-14",
        source="strategy", strategy="Break & Retest", horizon_key="swing",
        direction="bullish", entry_type="stop_entry", trigger_price=101.0,
        entry_price=None, expiry_bars=5, stop_loss=97.0, tp1=107.0,
        tp1_fraction=0.5, tp2=112.0, breakeven_trigger_fraction=0.5,
        trail_atr_mult=1.5, quality_score=70, quality_breakdown=[],
        tier="B", badge="VALIDATED", badge_stats={}, status="pending",
    )
    base.update(overrides)
    return TradePlanV2(**base)
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_context_htf.py
from swingbot.core.gate.context_htf import htf_trend
from tests.fixtures.gate import downtrend_daily, range_daily, uptrend_daily


def test_htf_trend_three_states():
    assert htf_trend(uptrend_daily())["weekly"] == "up"
    assert htf_trend(downtrend_daily())["weekly"] == "down"
    assert htf_trend(range_daily(90, 110, n=300))["weekly"] == "range"


def test_short_history_is_range_with_detail():
    result = htf_trend(uptrend_daily(n=100))     # ~20 weekly bars
    assert result["weekly"] == "range"
    assert "insufficient" in result["detail"]


def test_daily_state_present():
    assert htf_trend(uptrend_daily())["daily"] == "up"
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_gate_context_htf.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/gate/context_htf.py
"""HTF trend detection. If edge-engine E27 MTF primitives are merged,
consume them instead of this resample logic (capability-check at
execution: `from swingbot.core.edge import mtf`)."""
from __future__ import annotations

import pandas as pd


def _resample_weekly(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Open": df["Open"].resample("W-FRI").first(),
        "High": df["High"].resample("W-FRI").max(),
        "Low": df["Low"].resample("W-FRI").min(),
        "Close": df["Close"].resample("W-FRI").last(),
    }).dropna()


def _pivots(closes: pd.Series, span: int = 2) -> tuple[list, list]:
    highs, lows = [], []
    vals = closes.values
    for i in range(span, len(vals) - span):
        window = vals[i - span:i + span + 1]
        if vals[i] == window.max():
            highs.append(float(vals[i]))
        elif vals[i] == window.min():
            lows.append(float(vals[i]))
    return highs, lows


def _trend(closes: pd.Series, fast: int, slow: int) -> str:
    """SMA cross + pivot structure; SMAs within 0.5% of each other are
    treated as flat (keeps oscillating ranges deterministic)."""
    if len(closes) < slow + 5:
        return "range"
    sma_fast = float(closes.rolling(fast).mean().iloc[-1])
    sma_slow = float(closes.rolling(slow).mean().iloc[-1])
    if abs(sma_fast / sma_slow - 1.0) < 0.005:
        return "range"
    highs, lows = _pivots(closes.iloc[-min(len(closes), 8 * fast):])
    up_structure = ((len(highs) >= 2 and highs[-1] > highs[0])
                    or (len(lows) >= 2 and lows[-1] > lows[0]))
    down_structure = ((len(highs) >= 2 and highs[-1] < highs[0])
                      or (len(lows) >= 2 and lows[-1] < lows[0]))
    if sma_fast > sma_slow and up_structure:
        return "up"
    if sma_fast < sma_slow and down_structure:
        return "down"
    return "range"


def htf_trend(df_daily: pd.DataFrame) -> dict:
    weekly_df = _resample_weekly(df_daily)
    daily = _trend(df_daily["Close"], 20, 50)
    if len(weekly_df) < 45:                      # 40w SMA + margin
        return {"weekly": "range", "daily": daily,
                "detail": "insufficient weekly history"}
    weekly = _trend(weekly_df["Close"], 10, 40)
    return {"weekly": weekly, "daily": daily,
            "detail": f"weekly {weekly} (10/40w SMA + pivots), daily {daily}"}
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_context_htf.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/context_htf.py tests/fixtures/gate/plans.py tests/test_gate_context_htf.py
git commit -m "feat: HTF trend detector"
```

### Task G46: Check `htf_alignment` (weight 12, checklist §1 "I know the HTF trend and I'm not against it")

**Files:** Modify `context_htf.py`, `registry.py`; test `tests/test_gate_context_htf.py`

**Interfaces:** `check_htf_alignment(df_daily, plan, macro_snap) -> CheckResult` — bullish plan + weekly "up" → pass; weekly "range" → warn; bullish into weekly "down" (or mirror) → **fail**; evidence carries both timeframe states.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_context_htf.py`)

```python
from swingbot.core.gate.context_htf import check_htf_alignment
from swingbot.core.gate.registry import CHECKS
from tests.fixtures.gate.plans import make_plan


def test_htf_alignment_four_outcomes():
    up, down = uptrend_daily(), downtrend_daily()
    bull, bear = make_plan(direction="bullish"), make_plan(direction="bearish")
    assert check_htf_alignment(up, bull, None).status == "pass"
    assert check_htf_alignment(down, bear, None).status == "pass"     # mirror
    assert check_htf_alignment(down, bull, None).status == "fail"     # against trend
    assert check_htf_alignment(uptrend_daily(n=100), bull, None).status == "warn"  # range
    result = check_htf_alignment(down, bull, None)
    assert result.evidence["weekly"] == "down" and "daily" in result.evidence


def test_htf_alignment_registered():
    spec = CHECKS["htf_alignment"]
    assert spec.section == "context" and spec.weight == 12.0
    assert spec.hard_block is False and spec.applies_to is None
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'check_htf_alignment'`)
- [ ] **Step 3: Write the implementation** (append to `context_htf.py`)

```python
from swingbot.core.gate.registry import register
from swingbot.core.gate.types import CheckResult


def check_htf_alignment(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    trend = htf_trend(df_daily)
    weekly = trend["weekly"]
    with_trend = "up" if plan.direction == "bullish" else "down"
    if weekly == with_trend:
        status, detail = "pass", f"{plan.direction} plan with the weekly {weekly}trend"
    elif weekly == "range":
        status, detail = "warn", "weekly trend is range-bound"
    else:
        status, detail = "fail", f"{plan.direction} plan AGAINST the weekly {weekly}trend"
    return CheckResult("htf_alignment", "context", status, 12.0, detail,
                       {"weekly": weekly, "daily": trend["daily"]})


register(check_id="htf_alignment", section="context", weight=12.0,
         func=check_htf_alignment)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_context_htf.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/context_htf.py tests/test_gate_context_htf.py
git commit -m "feat: htf_alignment check"
```

### Task G47: Swing S/R level extraction

**Files:**
- Create: `swingbot/core/gate/levels.py`
- Test: `tests/test_gate_levels.py`

**Interfaces:**
- Produces: `swing_levels(df_daily, lookback=250, pivot_span=5) -> list[Level]` — `Level(price, kind: "support"|"resistance", touches, last_touch)`; pivots = local extrema over ±`pivot_span` bars, clustered within 0.5×ATR, touch-counted; sorted by touches desc. Reuse the existing scanning support/resistance helpers if `swingbot/core/scanning/` already exposes them (verify at execution; wrap, don't fork).

**Reuse decision (verified):** `swingbot/core/levels.py` exists but its `collect_candidate_levels`/`build_level_map` are horizon-config-coupled (`h` dict) and vote 10+ indicator sources for scenario building; its `Level` is `(price, sources)`. The gate needs plain touch-counted price structure, so `swingbot/core/gate/levels.py` keeps its own lean extractor with a distinct `SwingLevel` dataclass — a documented decision, not a fork of the same concern.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_levels.py
import numpy as np

from swingbot.core.gate.levels import SwingLevel, swing_levels
from tests.conftest import make_ohlcv


def _three_touch_resistance(level=110.0, base=100.0, n=120):
    closes = []
    for _ in range(3):
        # [1:] drops the duplicated peak/valley joints so every extremum
        # is unique (the pivot rule rejects ties)
        closes += list(np.linspace(base, level, 15)) + list(np.linspace(level, base, 15))[1:]
    closes += list(np.linspace(base, base * 1.01, n - len(closes)))
    return make_ohlcv(np.asarray(closes), spread_pct=0.5)


def test_three_touch_level_clustered_and_counted():
    levels = swing_levels(_three_touch_resistance(), pivot_span=5)
    res = [l for l in levels if l.kind == "resistance"]
    assert res, "no resistance found"
    assert res[0].touches == 3                       # strongest first
    assert abs(res[0].price - 110.0) / 110.0 < 0.01
    assert res[0].last_touch >= "2019-01-01"


def test_flat_series_has_no_levels():
    assert swing_levels(make_ohlcv(np.full(120, 100.0))) == []
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_gate_levels.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/gate/levels.py
"""Swing S/R extraction + round numbers (G48) + level_map check (G49)."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from swingbot.core.indicators import atr


@dataclass(frozen=True)
class SwingLevel:
    price: float
    kind: str          # "support" | "resistance"
    touches: int
    last_touch: str    # ISO date


def _safe_atr(df: pd.DataFrame, fallback_price: float) -> float:
    val = float(atr(df).iloc[-1])
    return val if val == val and val > 0 else fallback_price * 0.02


def swing_levels(df_daily: pd.DataFrame, lookback: int = 250,
                 pivot_span: int = 5) -> list[SwingLevel]:
    """Pivots = UNIQUE local extrema over +/-pivot_span bars (ties are not
    pivots — a flat series yields nothing), clustered within 0.5*ATR,
    touch-counted, sorted by touches desc."""
    df = df_daily.iloc[-lookback:]
    if len(df) < 2 * pivot_span + 1:
        return []
    highs, lows, idx = df["High"].values, df["Low"].values, df.index
    atr_val = _safe_atr(df, float(df["Close"].iloc[-1]))
    raw = []   # (price, kind, date)
    for i in range(pivot_span, len(df) - pivot_span):
        hi_win = highs[i - pivot_span:i + pivot_span + 1]
        lo_win = lows[i - pivot_span:i + pivot_span + 1]
        if highs[i] == hi_win.max() and (hi_win == highs[i]).sum() == 1:
            raw.append((float(highs[i]), "resistance", str(idx[i].date())))
        if lows[i] == lo_win.min() and (lo_win == lows[i]).sum() == 1:
            raw.append((float(lows[i]), "support", str(idx[i].date())))
    levels: list[SwingLevel] = []
    for kind in ("support", "resistance"):
        bucket: list[tuple[float, str]] = []
        for price, _, date in sorted((r for r in raw if r[1] == kind),
                                     key=lambda r: r[0]):
            if bucket and price - sum(p for p, _ in bucket) / len(bucket) > 0.5 * atr_val:
                levels.append(_close_bucket(bucket, kind))
                bucket = []
            bucket.append((price, date))
        if bucket:
            levels.append(_close_bucket(bucket, kind))
    return sorted(levels, key=lambda l: l.touches, reverse=True)


def _close_bucket(bucket: list[tuple[float, str]], kind: str) -> SwingLevel:
    prices = [p for p, _ in bucket]
    return SwingLevel(round(sum(prices) / len(prices), 4), kind,
                      len(bucket), max(d for _, d in bucket))
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_levels.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/levels.py tests/test_gate_levels.py
git commit -m "feat: swing S/R extraction"
```

### Task G48: Round-number levels

**Files:** Modify `levels.py`; test `tests/test_gate_levels.py`

**Interfaces:** `round_levels(price) -> list[float]` — the psychological grid near price: multiples of 1/5/10/50/100 chosen by price magnitude (e.g. price 187 → 180, 185, 190, 195, 200 and the majors 150/200); `nearest_round(price) -> tuple[float, float]` (level, distance in ATRs given atr kwarg).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_levels.py`)

```python
from swingbot.core.gate.levels import major_levels, nearest_round, round_levels


def test_round_grid_goldens():
    assert 8.0 in round_levels(8.0)                  # step 0.25 at single digits
    assert 87.5 in round_levels(87.0)                # step 2.5 in the tens
    assert 430.0 in round_levels(432.0)              # step 10 in the hundreds
    assert 4300.0 in round_levels(4300.0)            # step 100 in the thousands
    assert all(p > 0 for p in round_levels(0.8))


def test_majors():
    assert 200.0 in major_levels(187.0) and 150.0 in major_levels(187.0)
    assert 4000.0 in major_levels(4300.0)


def test_nearest_round_with_atr_distance():
    level, dist = nearest_round(187.0, atr=2.0)
    assert level == 185.0 and dist == 1.0            # |185-187| / 2 (grid steps by 5)
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'round_levels'`)
- [ ] **Step 3: Write the implementation** (append to `levels.py`)

```python
_STEPS = (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0)


def _step_for(price: float) -> float:
    target = price / 50.0
    for step in _STEPS:
        if step >= target:
            return step
    return _STEPS[-1]


def round_levels(price: float) -> list[float]:
    """The minor psychological grid near price (5 multiples of the
    magnitude-appropriate step) plus the majors around it."""
    step = _step_for(price)
    center = round(price / step) * step
    grid = {round(center + k * step, 2) for k in range(-2, 3)}
    grid |= set(major_levels(price))
    return sorted(p for p in grid if p > 0)


def major_levels(price: float) -> list[float]:
    """Only these count as 'walls' — a 10x-step grid (e.g. 150/200 for a
    $187 stock). The minor grid is context, not obstruction."""
    major = _step_for(price) * 10
    center = round(price / major) * major
    return sorted({round(center + k * major, 2) for k in (-1, 0, 1)} - {0.0})


def nearest_round(price: float, *, atr: float) -> tuple[float, float]:
    level = min(round_levels(price), key=lambda l: abs(l - price))
    dist = abs(level - price) / atr if atr > 0 else float("inf")
    return level, round(dist, 3)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_levels.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/levels.py tests/test_gate_levels.py
git commit -m "feat: round-number levels"
```

### Task G49: Check `level_map` (weight 8, §1 "nearest major S/R, prior swings, round numbers marked")

**Files:** Modify `levels.py`, `registry.py`; test `tests/test_gate_levels.py`

**Interfaces:** `check_level_map(df_daily, plan, macro_snap) -> CheckResult` — computes the three nearest levels above/below entry (swing + round merged); **fail** when a resistance (for longs; support for shorts) sits closer than 1×ATR to entry *before* TP1 (the trade runs straight into a wall); warn when between 1–2×ATR; pass otherwise. Evidence lists the levels — this is also what the embed renders (G123).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_levels.py`)

```python
from swingbot.core.gate.levels import check_level_map
from swingbot.core.gate.registry import CHECKS
from tests.fixtures.gate.plans import make_plan


def test_wall_before_tp1_fails():
    df = _three_touch_resistance(level=110.0)        # resistance wall ~110
    plan = make_plan(direction="bullish", trigger_price=110.0, entry_price=110.0,
                     stop_loss=106.0, tp1=118.0)
    result = check_level_map(df, plan, None)
    assert result.status == "fail"
    assert result.evidence["nearest_wall"] is not None
    assert result.evidence["below"] and result.evidence["above"]


def test_clear_path_passes():
    df = _three_touch_resistance(level=110.0)
    plan = make_plan(direction="bullish", trigger_price=111.5, entry_price=111.5,
                     stop_loss=107.0, tp1=118.0)     # above the wall, majors clear
    assert check_level_map(df, plan, None).status == "pass"


def test_level_map_registered_with_thresholds():
    spec = CHECKS["level_map"]
    assert spec.weight == 8.0 and spec.section == "context"
    assert spec.threshold("wall_atr_fail") == 1.0    # balanced default
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'check_level_map'`)
- [ ] **Step 3: Write the implementation** (append to `levels.py`)

```python
from swingbot.core.gate.registry import CHECKS, ThresholdSpec, register
from swingbot.core.gate.types import CheckResult


def check_level_map(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    spec = CHECKS["level_map"]
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    atr_val = _safe_atr(df_daily, entry)
    swings = swing_levels(df_daily)
    all_prices = sorted({l.price for l in swings} | set(round_levels(entry)))
    below = [p for p in all_prices if p < entry][-3:]
    above = [p for p in all_prices if p > entry][:3]
    bullish = plan.direction == "bullish"
    lo, hi = (entry, plan.tp1) if bullish else (plan.tp1, entry)
    opposing = "resistance" if bullish else "support"
    walls = [l.price for l in swings if l.kind == opposing and lo < l.price < hi]
    walls += [m for m in major_levels(entry) if lo < m < hi]
    nearest = min(walls, key=lambda w: abs(w - entry)) if walls else None
    dist_atr = round(abs(nearest - entry) / atr_val, 2) if nearest is not None else None
    if dist_atr is not None and dist_atr < spec.threshold("wall_atr_fail"):
        status = "fail"
        detail = f"{opposing} wall {nearest:.2f} only {dist_atr} ATR into the path to TP1"
    elif dist_atr is not None and dist_atr < spec.threshold("wall_atr_warn"):
        status = "warn"
        detail = f"{opposing} {nearest:.2f} sits {dist_atr} ATR into the path to TP1"
    else:
        status, detail = "pass", "no significant wall before TP1"
    return CheckResult("level_map", "context", status, 8.0, detail,
                       {"below": below, "above": above, "walls": sorted(walls)[:5],
                        "nearest_wall": nearest, "dist_atr": dist_atr,
                        "atr": round(atr_val, 4)})


register(check_id="level_map", section="context", weight=8.0, func=check_level_map,
         thresholds={
             "wall_atr_fail": ThresholdSpec(
                 "wall_atr_fail", 1.0, 0.25, 3.0, 0.25,
                 "lower to tolerate closer walls before TP1",
                 presets={"strict": 1.5, "balanced": 1.0, "relaxed": 0.5}),
             "wall_atr_warn": ThresholdSpec(
                 "wall_atr_warn", 2.0, 0.5, 4.0, 0.25,
                 "lower to warn about fewer walls",
                 presets={"strict": 2.5, "balanced": 2.0, "relaxed": 1.0}),
         })
```

(This evidence block — `below`/`above`/`walls` — is exactly what the embed renders in G123.)

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_levels.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/levels.py tests/test_gate_levels.py
git commit -m "feat: level_map check"
```

### Task G50: Check `atr_normal` (weight 6, §1 "volatility normal — not compressed or spiked")

**Files:**
- Create: `swingbot/core/gate/atr_regime.py`; modify `registry.py`
- Test: `tests/test_gate_atr.py`

**Interfaces:** `check_atr_normal(df_daily, plan, macro_snap) -> CheckResult` — ATR(14)/close percentile over trailing 252 bars; pass in [20th, 80th]; warn <20th (compression — breakout fuel but whipsaw risk) or 80–95th; **fail** >95th (spiked — stop math unreliable). Evidence: percentile + raw ATR%.
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_atr.py
import numpy as np

from swingbot.core.gate.atr_regime import check_atr_normal
from swingbot.core.gate.registry import CHECKS
from tests.conftest import make_ohlcv
from tests.fixtures.gate.plans import make_plan


def _vol_path(early_move, late_move, n=300, late=25):
    """Alternating +/- daily moves: early_move for n-late bars, late_move after."""
    closes = [100.0]
    for i in range(n):
        m = early_move if i < n - late else late_move
        closes.append(closes[-1] * (1 + (m if i % 2 == 0 else -m)))
    return make_ohlcv(np.asarray(closes[1:]), spread_pct=0.2)


PLAN = make_plan()


def test_normal_band_passes():
    result = check_atr_normal(_vol_path(0.01, 0.01), PLAN, None)
    assert result.status == "pass"
    assert 20 <= result.evidence["percentile"] <= 80


def test_compression_warns():
    assert check_atr_normal(_vol_path(0.02, 0.002), PLAN, None).status == "warn"


def test_spike_fails():
    result = check_atr_normal(_vol_path(0.004, 0.05), PLAN, None)
    assert result.status == "fail"
    assert result.evidence["percentile"] > 95


def test_short_history_unknown():
    df = _vol_path(0.01, 0.01, n=40, late=5)
    assert check_atr_normal(df, PLAN, None).status == "unknown"


def test_registered():
    assert CHECKS["atr_normal"].threshold("pct_spike") == 95.0
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_gate_atr.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/gate/atr_regime.py
"""ATR-percentile regime checks. Percentile uses MIDRANK so a
constant-volatility series sits at ~50, not 100."""
from __future__ import annotations

import pandas as pd

from swingbot.core.gate.registry import CHECKS, ThresholdSpec, register
from swingbot.core.gate.types import CheckResult
from swingbot.core.indicators import atr


def _atr_percentile(df_daily) -> tuple[float | None, float | None]:
    atr_pct = (atr(df_daily) / df_daily["Close"]).dropna()
    if len(atr_pct) < 60:
        return None, None
    window = atr_pct.iloc[-252:]
    last = float(atr_pct.iloc[-1])
    midrank = 100.0 * (float((window < last).mean())
                       + float((window <= last).mean())) / 2.0
    return midrank, last * 100.0


def check_atr_normal(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    spec = CHECKS["atr_normal"]
    pctile, atr_pct = _atr_percentile(df_daily)
    if pctile is None:
        return CheckResult("atr_normal", "context", "unknown", 6.0,
                           "insufficient history for ATR percentile", {})
    evidence = {"percentile": round(pctile, 1), "atr_pct": round(atr_pct, 2)}
    if pctile > spec.threshold("pct_spike"):
        return CheckResult("atr_normal", "context", "fail", 6.0,
                           f"ATR spiked ({pctile:.0f}th pct) — stop math unreliable",
                           evidence)
    if pctile < spec.threshold("pct_low"):
        return CheckResult("atr_normal", "context", "warn", 6.0,
                           f"volatility compressed ({pctile:.0f}th pct) — "
                           f"breakout fuel but whipsaw risk", evidence)
    if pctile > spec.threshold("pct_high"):
        return CheckResult("atr_normal", "context", "warn", 6.0,
                           f"volatility elevated ({pctile:.0f}th pct)", evidence)
    return CheckResult("atr_normal", "context", "pass", 6.0,
                       f"volatility normal ({pctile:.0f}th pct)", evidence)


register(check_id="atr_normal", section="context", weight=6.0, func=check_atr_normal,
         thresholds={
             "pct_low": ThresholdSpec("pct_low", 20.0, 0.0, 40.0, 5.0,
                 "lower to accept more compression without a warn",
                 presets={"strict": 25.0, "balanced": 20.0, "relaxed": 10.0}),
             "pct_high": ThresholdSpec("pct_high", 80.0, 60.0, 100.0, 5.0,
                 "raise to accept more elevated volatility",
                 presets={"strict": 75.0, "balanced": 80.0, "relaxed": 90.0}),
             "pct_spike": ThresholdSpec("pct_spike", 95.0, 80.0, 100.0, 1.0,
                 "raise to fail only on the most extreme spikes",
                 presets={"strict": 90.0, "balanced": 95.0, "relaxed": 99.0}),
         })
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_atr.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/atr_regime.py tests/test_gate_atr.py
git commit -m "feat: atr_normal check"
```

## Section 2 — Setup quality

### Task G52: Check `signal_confirmed` (weight 10, **hard block**, §2 "pattern fully closed/confirmed")

**Files:**
- Create: `swingbot/core/gate/setup_quality.py`; modify `registry.py`
- Test: `tests/test_gate_setup.py`

**Interfaces:** `check_signal_confirmed(df_daily, plan, macro_snap) -> CheckResult` — asserts the signal bar the plan was built from is a **closed** bar (plan.as_of < today's session date, or session closed) and, for breakout-family strategies, that the trigger candle closed beyond the level (not intrabar poke). Evaluating mid-session on the forming bar → **fail** (hard block: never alert on an unclosed pattern). Uses plan metadata (`entry_type`, signal date) from TradePlanV2.
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_setup.py
import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np

from swingbot.core.gate.registry import CHECKS
from swingbot.core.gate.setup_quality import check_signal_confirmed
from tests.conftest import make_ohlcv
from tests.fixtures.gate import uptrend_daily
from tests.fixtures.gate.plans import make_plan

ET = ZoneInfo("America/New_York")


def test_closed_bar_passes():
    plan = make_plan(created_at="2026-07-13")            # yesterday's bar
    now = dt.datetime(2026, 7, 14, 15, 0, tzinfo=ET)     # mid-session today
    assert check_signal_confirmed(uptrend_daily(), plan, None, now=now).status == "pass"


def test_same_day_forming_bar_fails_hard():
    plan = make_plan(created_at="2026-07-14")
    now = dt.datetime(2026, 7, 14, 15, 0, tzinfo=ET)     # Tuesday, session open
    assert check_signal_confirmed(uptrend_daily(), plan, None, now=now).status == "fail"
    # after the close the same plan is fine
    evening = dt.datetime(2026, 7, 14, 17, 30, tzinfo=ET)
    assert check_signal_confirmed(uptrend_daily(), plan, None, now=evening).status == "pass"


def test_breakout_close_back_inside_fails():
    # market-entry breakout plan whose signal bar poked above the level
    # intrabar (high 100.5) but closed back inside (99.5)
    df = make_ohlcv(np.concatenate([np.full(59, 97.0), [99.5]]), spread_pct=2.0)
    plan = make_plan(strategy="Break & Retest", entry_type="market",
                     trigger_price=100.0, created_at="2026-07-13")
    now = dt.datetime(2026, 7, 14, 17, 30, tzinfo=ET)
    result = check_signal_confirmed(df, plan, None, now=now)
    assert result.status == "fail" and "inside" in result.detail


def test_registered_as_hard_block():
    assert CHECKS["signal_confirmed"].hard_block is True
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_gate_setup.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/gate/setup_quality.py
"""Section-2 setup-quality checks. Raw helpers (volume_ratio,
momentum_with_plan) are shared by the confluence counter (G53)."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd

from swingbot.core.gate.registry import CHECKS, ThresholdSpec, register
from swingbot.core.gate.types import CheckResult
from swingbot.core.indicators import macd, rsi

ET = ZoneInfo("America/New_York")

# Strategies whose entry IS a level break — cross-checked against the real
# ALL_STRATEGIES names (backtest.py:392); revisited deliberately in G80.
BREAKOUT_FAMILY = ("Break & Retest", "Support/Resistance", "Volume Profile")
MEANREV_FAMILY = ("RSI", "RSI Divergence")


def check_signal_confirmed(df_daily, plan, macro_snap, *, now=None, **ctx) -> CheckResult:
    """HARD BLOCK: never alert on an unclosed pattern."""
    now_et = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ET)
    session_open = (now_et.weekday() < 5
                    and dt.time(9, 30) <= now_et.time() < dt.time(16, 0))
    if plan.created_at == now_et.date().isoformat() and session_open:
        return CheckResult("signal_confirmed", "setup", "fail", 10.0,
                           "signal bar is still forming — pattern not closed",
                           {"created_at": plan.created_at,
                            "now_et": now_et.isoformat()})
    if plan.strategy in BREAKOUT_FAMILY and plan.entry_type == "market":
        level = plan.trigger_price
        bullish = plan.direction == "bullish"
        close = float(df_daily["Close"].iloc[-1])
        hi, lo = float(df_daily["High"].iloc[-1]), float(df_daily["Low"].iloc[-1])
        beyond = close > level if bullish else close < level
        poked = hi >= level if bullish else lo <= level
        if poked and not beyond:
            return CheckResult("signal_confirmed", "setup", "fail", 10.0,
                               "breakout bar closed back inside the level — "
                               "intrabar poke, not a confirmed close",
                               {"level": level, "close": close})
    return CheckResult("signal_confirmed", "setup", "pass", 10.0,
                       "signal bar closed / pattern confirmed",
                       {"created_at": plan.created_at})


register(check_id="signal_confirmed", section="setup", weight=10.0,
         func=check_signal_confirmed, hard_block=True)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_setup.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/setup_quality.py tests/test_gate_setup.py
git commit -m "feat: signal_confirmed hard-block check"
```

### Task G53: Confluence counter (weight 10, §2 "≥ 2 independent signals agree")

> **Audit note (2026-07-28):** 4 of this check's 6 confluence factors (volume, momentum, HTF alignment, swing-level proximity) re-derive booleans already scored independently by G46/G49/G54/G55 — the same evidence gets counted once as an individual check and again in this aggregate, double-weighting it in the final score. Resolve this (e.g. drop the overlapping factors from the confluence count, or reduce weight) before G78 calibration locks in weights.

**Files:** Modify `setup_quality.py`, `registry.py`; test `tests/test_gate_setup.py`

**Interfaces:** `check_confluence(df_daily, plan, macro_snap) -> CheckResult` — counts independent agreeing factors at the entry zone: (a) at a G47 swing level, (b) at/near a round number, (c) 20/50/200 SMA within 0.5 ATR and pointing with-plan, (d) volume confirmation (G54's raw bool), (e) momentum agreement (G55's raw bool), (f) with-trend HTF (G46). Pass ≥ 3, warn = 2, fail < 2. Evidence lists which factors fired — reused verbatim by the embed and by `!whycheck`.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_setup.py`)

```python
from swingbot.core.gate.setup_quality import check_confluence


def test_confluence_bands(monkeypatch):
    import swingbot.core.gate.setup_quality as sq
    df, plan = uptrend_daily(), make_plan()
    # deterministic factor control: patch the factor probes directly
    def factors(n):
        return {"at_swing_level": n >= 1, "near_round": n >= 2,
                "sma_support": n >= 3, "volume": n >= 4,
                "momentum": n >= 5, "with_htf": n >= 6}
    monkeypatch.setattr(sq, "_confluence_factors", lambda d, p, m, **c: factors(4))
    assert check_confluence(df, plan, None).status == "pass"      # >= 3
    monkeypatch.setattr(sq, "_confluence_factors", lambda d, p, m, **c: factors(2))
    assert check_confluence(df, plan, None).status == "warn"      # exactly 2
    monkeypatch.setattr(sq, "_confluence_factors", lambda d, p, m, **c: factors(0))
    assert check_confluence(df, plan, None).status == "fail"      # < 2
    monkeypatch.setattr(sq, "_confluence_factors", lambda d, p, m, **c: factors(4))
    fired = check_confluence(df, plan, None).evidence["factors"]
    assert fired == ["at_swing_level", "near_round", "sma_support", "volume"]


def test_confluence_factors_run_on_real_frame():
    # smoke: the real factor probe runs end-to-end without raising
    result = check_confluence(uptrend_daily(), make_plan(), None)
    assert result.status in ("pass", "warn", "fail")
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'check_confluence'`)
- [ ] **Step 3: Write the implementation** (append to `setup_quality.py`)

```python
def volume_ratio(df_daily) -> float | None:
    """Signal-bar volume vs 20d average — shared with G54."""
    vol = df_daily["Volume"]
    if len(vol) < 21:
        return None
    avg20 = float(vol.iloc[-21:-1].mean())
    return float(vol.iloc[-1]) / avg20 if avg20 > 0 else None


def momentum_with_plan(df_daily, plan) -> bool | None:
    """True unless RSI slope AND MACD histogram both point against the
    plan — shared with G55."""
    closes = df_daily["Close"]
    if len(closes) < 40:
        return None
    rsi_slope = float(rsi(closes).iloc[-1] - rsi(closes).iloc[-6])
    hist = float(macd(closes)["histogram"].iloc[-1])
    bullish = plan.direction == "bullish"
    rsi_against = rsi_slope < 0 if bullish else rsi_slope > 0
    macd_against = hist < 0 if bullish else hist > 0
    return not (rsi_against and macd_against)


def _confluence_factors(df_daily, plan, macro_snap, **ctx) -> dict[str, bool]:
    from swingbot.core.gate.context_htf import htf_trend
    from swingbot.core.gate.levels import (_safe_atr, nearest_round,
                                           swing_levels)
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    atr_val = _safe_atr(df_daily, entry)
    bullish = plan.direction == "bullish"
    swings = swing_levels(df_daily)
    at_level = any(abs(l.price - entry) <= 0.5 * atr_val for l in swings)
    _, round_dist = nearest_round(entry, atr=atr_val)
    closes = df_daily["Close"]
    sma_support = False
    if len(closes) >= 200:
        for period in (20, 50, 200):
            sma = closes.rolling(period).mean()
            near = abs(float(sma.iloc[-1]) - entry) <= 0.5 * atr_val
            pointing = (float(sma.iloc[-1] - sma.iloc[-6]) > 0) == bullish
            if near and pointing:
                sma_support = True
                break
    ratio = volume_ratio(df_daily)
    trend = htf_trend(df_daily)
    with_htf = trend["weekly"] == ("up" if bullish else "down")
    return {
        "at_swing_level": at_level,
        "near_round": round_dist <= 0.5,
        "sma_support": sma_support,
        "volume": bool(ratio and ratio >= 1.3),
        "momentum": bool(momentum_with_plan(df_daily, plan)),
        "with_htf": with_htf,
    }


def check_confluence(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    factors = _confluence_factors(df_daily, plan, macro_snap, **ctx)
    fired = [name for name, on in factors.items() if on]
    n = len(fired)
    status = "pass" if n >= 3 else "warn" if n == 2 else "fail"
    return CheckResult("confluence", "setup", status, 10.0,
                       f"{n} independent factors agree: {', '.join(fired) or 'none'}",
                       {"factors": fired, "count": n})


register(check_id="confluence", section="setup", weight=10.0, func=check_confluence)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_setup.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/setup_quality.py tests/test_gate_setup.py
git commit -m "feat: confluence counter"
```

### Task G54: Check `volume_confirms` (weight 8, §2 + golden rule)

**Files:** Modify `setup_quality.py`, `registry.py`; test `tests/test_gate_setup.py`

**Interfaces:** `check_volume(df_daily, plan, macro_snap) -> CheckResult` — signal-bar volume vs 20d average: pass ≥ 1.3×; warn 0.8–1.3×; **fail** < 0.8× for breakout-family entries (a breakout on dead volume is the #1 trap per the golden rule), warn-only for mean-reversion strategies (registry `applies_to` handles the split).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_setup.py`)

```python
from swingbot.core.gate.setup_quality import check_volume


def _vol_df(last_ratio):
    vols = np.full(60, 1_000_000.0)
    vols[-1] = 1_000_000.0 * last_ratio
    return make_ohlcv(np.linspace(95, 100, 60), volumes=vols)


def test_volume_bands_for_breakout_family():
    breakout = make_plan(strategy="Break & Retest")
    assert check_volume(_vol_df(1.5), breakout, None).status == "pass"   # >= 1.3x
    assert check_volume(_vol_df(1.0), breakout, None).status == "warn"   # 0.8-1.3x
    assert check_volume(_vol_df(0.5), breakout, None).status == "fail"   # < 0.8x: the #1 trap


def test_dead_volume_is_warn_only_for_meanrev():
    meanrev = make_plan(strategy="RSI Divergence")
    assert check_volume(_vol_df(0.5), meanrev, None).status == "warn"


def test_no_volume_history_unknown():
    df = make_ohlcv(np.linspace(95, 100, 10))
    assert check_volume(df, make_plan(), None).status == "unknown"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'check_volume'`)
- [ ] **Step 3: Write the implementation** (append to `setup_quality.py`)

```python
def check_volume(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    spec = CHECKS["volume_confirms"]
    ratio = volume_ratio(df_daily)
    if ratio is None:
        return CheckResult("volume_confirms", "setup", "unknown", 8.0,
                           "insufficient volume history", {})
    evidence = {"ratio": round(ratio, 2)}
    if ratio >= spec.threshold("pass_mult"):
        return CheckResult("volume_confirms", "setup", "pass", 8.0,
                           f"signal volume {ratio:.1f}x the 20d average", evidence)
    if ratio >= spec.threshold("warn_mult"):
        return CheckResult("volume_confirms", "setup", "warn", 8.0,
                           f"signal volume only {ratio:.1f}x average", evidence)
    # dead volume: fail-grade for breakout entries, warn-only for mean reversion
    if plan.strategy in BREAKOUT_FAMILY:
        return CheckResult("volume_confirms", "setup", "fail", 8.0,
                           f"breakout on dead volume ({ratio:.1f}x) — the #1 trap",
                           evidence)
    return CheckResult("volume_confirms", "setup", "warn", 8.0,
                       f"dead volume ({ratio:.1f}x)", evidence)


register(check_id="volume_confirms", section="setup", weight=8.0, func=check_volume,
         thresholds={
             "pass_mult": ThresholdSpec("pass_mult", 1.3, 1.0, 3.0, 0.1,
                 "lower to accept quieter signal bars",
                 presets={"strict": 1.5, "balanced": 1.3, "relaxed": 1.1}),
             "warn_mult": ThresholdSpec("warn_mult", 0.8, 0.3, 1.2, 0.1,
                 "lower to fail only on truly dead volume",
                 presets={"strict": 0.9, "balanced": 0.8, "relaxed": 0.6}),
         })
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_setup.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/setup_quality.py tests/test_gate_setup.py
git commit -m "feat: volume confirmation check"
```

### Task G55: Check `momentum_agrees` (weight 6)

**Files:** Modify `setup_quality.py`, `registry.py`; test `tests/test_gate_setup.py`

**Interfaces:** `check_momentum(df_daily, plan, macro_snap) -> CheckResult` — RSI(14) slope over 5 bars and MACD histogram sign must not *both* point against the plan; both against → fail; one against → warn; else pass.

- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_setup.py`)

```python
from swingbot.core.gate.setup_quality import check_momentum
from tests.fixtures.gate import downtrend_daily


def test_momentum_three_outcomes():
    import pandas as pd
    bull = make_plan(direction="bullish")
    # steady uptrend: RSI slope up, MACD hist > 0 -> pass
    assert check_momentum(uptrend_daily(), bull, None).status == "pass"
    # steady downtrend against a bullish plan: both against -> fail
    assert check_momentum(downtrend_daily(), bull, None).status == "fail"
    # downtrend with a fresh 3-bar pop: RSI slope turns up while the MACD
    # histogram is still negative -> exactly one against -> warn
    df = downtrend_daily()
    pop = df["Close"].iloc[-1] * np.array([1.02, 1.04, 1.06])
    extra = make_ohlcv(pop, start=str((df.index[-1]
                                       + pd.tseries.offsets.BDay(1)).date()))
    mixed = pd.concat([df, extra])
    assert check_momentum(mixed, bull, None).status == "warn"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'check_momentum'`)
- [ ] **Step 3: Write the implementation** (append to `setup_quality.py`)

```python
def check_momentum(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    closes = df_daily["Close"]
    if len(closes) < 40:
        return CheckResult("momentum_agrees", "setup", "unknown", 6.0,
                           "insufficient history", {})
    rsi_series = rsi(closes)
    rsi_slope = float(rsi_series.iloc[-1] - rsi_series.iloc[-6])
    hist = float(macd(closes)["histogram"].iloc[-1])
    bullish = plan.direction == "bullish"
    rsi_against = rsi_slope < 0 if bullish else rsi_slope > 0
    macd_against = hist < 0 if bullish else hist > 0
    evidence = {"rsi_slope5": round(rsi_slope, 2), "macd_hist": round(hist, 4)}
    if rsi_against and macd_against:
        return CheckResult("momentum_agrees", "setup", "fail", 6.0,
                           "RSI slope AND MACD histogram both point against the plan",
                           evidence)
    if rsi_against or macd_against:
        which = "RSI slope" if rsi_against else "MACD histogram"
        return CheckResult("momentum_agrees", "setup", "warn", 6.0,
                           f"{which} points against the plan", evidence)
    return CheckResult("momentum_agrees", "setup", "pass", 6.0,
                       "momentum agrees with the plan", evidence)


register(check_id="momentum_agrees", section="setup", weight=6.0, func=check_momentum)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_setup.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/setup_quality.py tests/test_gate_setup.py
git commit -m "feat: momentum agreement check"
```

### Task G56: Check `no_bearish_divergence_at_entry` (weight 6, §2 "not diverging against the move")

**Files:** Modify `setup_quality.py`, `registry.py`; test `tests/test_gate_setup.py`

**Interfaces:** `check_divergence_against(df_daily, plan, macro_snap) -> CheckResult` — for longs: price higher high in last 20 bars while RSI lower high → warn (fail if the plan's own strategy is *not* divergence-based and the divergence is 2-swing confirmed). Mirror for shorts. Distinct from G60 (which polices divergence-*entry* strategies).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_setup.py`)

```python
from swingbot.core.gate.setup_quality import check_divergence_against


def _hh_price_lh_rsi():
    """Three higher price highs on successively weaker legs -> RSI lower
    highs. Trailing pullback makes the last peak a detectable pivot."""
    closes = list(np.linspace(95, 100, 60))
    closes += list(np.linspace(100, 110, 5))          # sharp leg, RSI hot
    closes += list(np.linspace(110, 104, 4))[1:]
    closes += list(np.linspace(104, 112, 12))         # slower leg, RSI cooler
    closes += list(np.linspace(112, 106, 4))[1:]
    closes += list(np.linspace(106, 113, 18))         # crawl, RSI cooler still
    closes += list(np.linspace(113, 109, 4))[1:]
    return make_ohlcv(np.asarray(closes), spread_pct=0.5)


def test_divergence_against_move():
    df = _hh_price_lh_rsi()
    momentum_plan = make_plan(strategy="MACD", direction="bullish")
    result = check_divergence_against(df, momentum_plan, None)
    assert result.status == "fail"        # 2-swing confirmed + non-divergence strategy
    assert result.evidence["divergent_pairs"] >= 2
    div_plan = make_plan(strategy="RSI Divergence", direction="bullish")
    assert check_divergence_against(df, div_plan, None).status == "warn"
    assert check_divergence_against(uptrend_daily(), momentum_plan, None).status == "pass"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'check_divergence_against'`)
- [ ] **Step 3: Write the implementation** (append to `setup_quality.py`; registry id `divergence_against`)

```python
def _pivot_high_positions(series, span=3) -> list[int]:
    vals = series.values
    out = []
    for i in range(span, len(vals) - span):
        win = vals[i - span:i + span + 1]
        if vals[i] == win.max() and (win == vals[i]).sum() == 1:
            out.append(i)
    return out


def check_divergence_against(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """Momentum diverging AGAINST the move at entry. Distinct from G60,
    which polices divergence-ENTRY strategies for missing confirmation."""
    closes_full = df_daily["Close"]
    if len(closes_full) < 60:
        return CheckResult("divergence_against", "setup", "unknown", 6.0,
                           "insufficient history", {})
    window = closes_full.iloc[-60:]
    rsi_window = rsi(closes_full).iloc[-60:]
    bullish = plan.direction == "bullish"
    price_probe = window if bullish else -window       # shorts: mirror via negation
    rsi_probe = rsi_window if bullish else -rsi_window
    pivots = _pivot_high_positions(price_probe, span=3)[-3:]
    divergent_pairs = 0
    for a, b in zip(pivots, pivots[1:]):
        if price_probe.iloc[b] > price_probe.iloc[a] \
                and rsi_probe.iloc[b] < rsi_probe.iloc[a]:
            divergent_pairs += 1
    evidence = {"divergent_pairs": divergent_pairs, "pivots_found": len(pivots)}
    if divergent_pairs == 0:
        return CheckResult("divergence_against", "setup", "pass", 6.0,
                           "no momentum divergence against the move", evidence)
    if divergent_pairs >= 2 and plan.strategy != "RSI Divergence":
        return CheckResult("divergence_against", "setup", "fail", 6.0,
                           "2-swing momentum divergence against the move", evidence)
    return CheckResult("divergence_against", "setup", "warn", 6.0,
                       "momentum divergence forming against the move", evidence)


register(check_id="divergence_against", section="setup", weight=6.0,
         func=check_divergence_against)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_setup.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/setup_quality.py tests/test_gate_setup.py
git commit -m "feat: divergence-against-move check"
```

## Section 3 — The 8 surviving red flags (checklist §3, one task each)

Red-flag checks live in `swingbot/core/gate/redflags.py`, ids prefixed `rf_`, section `"redflag"`. Policy: a red flag that fires = `fail`; flags marked **HB** are hard blocks. Each returns evidence sufficient for the embed's red-flag table row.

### Task G57: `rf_fake_breakout` (weight 10)

> **Audit note (2026-07-28):** Overlaps significantly with G58 (`rf_stop_sweep`) — both detect "price pierced/crossed a level and got rejected" via wick/close-position + volume/follow-through evidence, sharing most of the underlying math (levels, ATR, volume ratio). Kept distinct by `applies_to` scoping, but there's real risk of double-counting the same false-break event on a signal bar that qualifies for both. Revisit whether these should collapse into one detector with two sub-conditions before finalizing weights.

**Files:** Create `swingbot/core/gate/redflags.py`; modify `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_fake_breakout(df_daily, plan, macro_snap) -> CheckResult` — for breakout-family plans: fires when the breakout bar closed back inside the range (close < level for longs) OR broke out on < 0.8× avg volume; also fires when the *prior* 10 bars contain ≥ 2 failed pokes through the same level (serial-liar level). Non-breakout strategies → pass with detail "n/a" (registry `applies_to` limits it, but the function stays total).
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_redflags.py
import datetime as dt

import numpy as np

from swingbot.core.gate.redflags import rf_fake_breakout
from tests.conftest import make_ohlcv
from tests.fixtures.gate import breakout_and_fail, uptrend_daily
from tests.fixtures.gate.plans import make_plan

BREAKOUT_PLAN = make_plan(strategy="Break & Retest", direction="bullish",
                          trigger_price=100.0)


def test_breakout_and_fail_fires():
    result = rf_fake_breakout(breakout_and_fail(level=100.0), BREAKOUT_PLAN, None)
    assert result.status == "fail"


def test_clean_high_volume_breakout_passes():
    vols = np.full(60, 1_000_000.0)
    vols[-1] = 2_500_000.0
    closes = np.concatenate([np.linspace(92, 99, 59), [102.0]])
    df = make_ohlcv(closes, volumes=vols)
    assert rf_fake_breakout(df, BREAKOUT_PLAN, None).status == "pass"


def test_serial_poker_fires():
    df = make_ohlcv(np.full(60, 97.0), spread_pct=1.0)
    for pos in (-5, -3):                       # two failed pokes through 100
        df.loc[df.index[pos], "High"] = 101.0
    df.loc[df.index[-1], "Close"] = 99.0
    assert rf_fake_breakout(df, BREAKOUT_PLAN, None).status == "fail"


def test_non_breakout_strategy_na_pass():
    result = rf_fake_breakout(breakout_and_fail(), make_plan(strategy="RSI"), None)
    assert result.status == "pass" and "n/a" in result.detail
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_gate_redflags.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/gate/redflags.py
"""The 11 red-flag detectors, ids rf_*. A fired flag = status "fail"
(warn-grade flags are noted per check); functions stay total — a
strategy the flag doesn't police returns pass with detail "n/a"."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from swingbot.core.gate.registry import CHECKS, ThresholdSpec, register
from swingbot.core.gate.setup_quality import BREAKOUT_FAMILY, volume_ratio
from swingbot.core.gate.types import CheckResult
from swingbot.core.indicators import adx, rsi

ET = ZoneInfo("America/New_York")


def _rf(check_id, status, detail, evidence, weight) -> CheckResult:
    return CheckResult(check_id, "redflag", status, weight, detail, evidence)


def rf_fake_breakout(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    spec = CHECKS["rf_fake_breakout"]
    if plan.strategy not in BREAKOUT_FAMILY:
        return _rf("rf_fake_breakout", "pass", "n/a (not a breakout strategy)", {}, 10.0)
    level = plan.trigger_price
    bullish = plan.direction == "bullish"
    last_close = float(df_daily["Close"].iloc[-1])
    ratio = volume_ratio(df_daily)
    recent = df_daily.iloc[-3:]
    if bullish:
        broke_out = bool((recent["Close"] > level).any() or (recent["High"] > level).any())
        back_inside = last_close < level
        beyond_now = last_close > level
    else:
        broke_out = bool((recent["Close"] < level).any() or (recent["Low"] < level).any())
        back_inside = last_close > level
        beyond_now = last_close < level
    evidence = {"level": level, "close": last_close, "vol_ratio": ratio}
    if broke_out and back_inside:
        return _rf("rf_fake_breakout", "fail",
                   f"breakout closed back inside on {ratio or 0:.1f}x volume",
                   evidence, 10.0)
    if beyond_now and ratio is not None and ratio < spec.threshold("vol_mult"):
        return _rf("rf_fake_breakout", "fail",
                   f"breakout on dead volume ({ratio:.1f}x)", evidence, 10.0)
    prior = df_daily.iloc[-11:-1]
    if bullish:
        pokes = int(((prior["High"] >= level) & (prior["Close"] < level)).sum())
    else:
        pokes = int(((prior["Low"] <= level) & (prior["Close"] > level)).sum())
    if pokes >= int(spec.threshold("serial_pokes")):
        evidence["failed_pokes"] = pokes
        return _rf("rf_fake_breakout", "fail",
                   f"{pokes} failed pokes through {level:.2f} in the prior 10 bars "
                   f"— serial-liar level", evidence, 10.0)
    return _rf("rf_fake_breakout", "pass", "no fake-breakout signature", evidence, 10.0)


register(check_id="rf_fake_breakout", section="redflag", weight=10.0,
         func=rf_fake_breakout, applies_to=BREAKOUT_FAMILY,
         thresholds={
             "vol_mult": ThresholdSpec("vol_mult", 0.8, 0.3, 1.5, 0.1,
                 "lower to tolerate quieter breakouts",
                 presets={"strict": 1.0, "balanced": 0.8, "relaxed": 0.5}),
             "serial_pokes": ThresholdSpec("serial_pokes", 2, 1, 5, 1,
                 "raise to tolerate more failed pokes",
                 presets={"strict": 1, "balanced": 2, "relaxed": 3}),
         })
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_redflags.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/redflags.py tests/test_gate_redflags.py
git commit -m "feat: rf_fake_breakout"
```

### Task G58: `rf_stop_sweep` (weight 8)

> **Audit note (2026-07-28):** See the note on G57 (`rf_fake_breakout`) — same overlap concern, not a full duplicate but a double-counting risk worth resolving before weight calibration.

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_stop_sweep(df_daily, plan, macro_snap) -> CheckResult` — fires when the signal bar (or prior bar) printed a wick through an obvious level (G47 level or round number) of ≥ 1.5× body length with close back on the far side, **and** the next bar shows no follow-through (for continuation plans this is the trap; for sweep-reclaim strategies the registry marks it n/a). Evidence: wick/body ratio, level touched.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_redflags.py`)

```python
from swingbot.core.gate.redflags import rf_stop_sweep
from tests.fixtures.gate import sweep_wick


def test_sweep_wick_fires():
    plan = make_plan(trigger_price=101.0)
    result = rf_stop_sweep(sweep_wick(level=100.0), plan, None)
    assert result.status == "fail"
    assert result.evidence["wick_body"] >= 1.5


def test_normal_trend_passes():
    assert rf_stop_sweep(uptrend_daily(), make_plan(), None).status == "pass"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'rf_stop_sweep'`)
- [ ] **Step 3: Write the implementation** (append to `redflags.py`)

```python
def rf_stop_sweep(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """Wick >= wick_body_mult x body through an obvious level with a close
    back on the far side, and no follow-through on the next bar. For
    sweep-reclaim strategies the registry applies_to marks this n/a."""
    spec = CHECKS["rf_stop_sweep"]
    from swingbot.core.gate.levels import _safe_atr, round_levels, swing_levels
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    atr_val = _safe_atr(df_daily, entry)
    levels = [l.price for l in swing_levels(df_daily)] + round_levels(entry)
    wick_mult = spec.threshold("wick_body_mult")
    for pos in (-2, -3):                        # signal bar or the bar before
        if len(df_daily) + pos < 0:
            continue
        bar, nxt = df_daily.iloc[pos], df_daily.iloc[pos + 1]
        body = abs(float(bar["Close"]) - float(bar["Open"])) or 1e-9
        lower_wick = min(float(bar["Close"]), float(bar["Open"])) - float(bar["Low"])
        upper_wick = float(bar["High"]) - max(float(bar["Close"]), float(bar["Open"]))
        for level in levels:
            swept_down = (float(bar["Low"]) < level < min(float(bar["Close"]), float(bar["Open"]))
                          and lower_wick >= wick_mult * body)
            swept_up = (float(bar["High"]) > level > max(float(bar["Close"]), float(bar["Open"]))
                        and upper_wick >= wick_mult * body)
            if not (swept_down or swept_up):
                continue
            follow_atr = abs(float(nxt["Close"]) - float(bar["Close"])) / atr_val
            if follow_atr < spec.threshold("follow_atr"):
                wick_body = round(max(lower_wick, upper_wick) / body, 2)
                return _rf("rf_stop_sweep", "fail",
                           f"stop-sweep wick through {level:.2f} "
                           f"({wick_body}x body), no follow-through",
                           {"level": level, "wick_body": wick_body,
                            "follow_atr": round(follow_atr, 2)}, 8.0)
    return _rf("rf_stop_sweep", "pass", "no sweep signature", {}, 8.0)


register(check_id="rf_stop_sweep", section="redflag", weight=8.0,
         func=rf_stop_sweep,
         thresholds={
             "wick_body_mult": ThresholdSpec("wick_body_mult", 1.5, 1.0, 4.0, 0.25,
                 "raise to ignore smaller wicks",
                 presets={"strict": 1.25, "balanced": 1.5, "relaxed": 2.5}),
             "follow_atr": ThresholdSpec("follow_atr", 0.5, 0.1, 1.5, 0.1,
                 "lower to require less follow-through before clearing",
                 presets={"strict": 0.8, "balanced": 0.5, "relaxed": 0.25}),
         })
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_redflags.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/redflags.py tests/test_gate_redflags.py
git commit -m "feat: rf_stop_sweep"
```

### Task G59: `rf_dead_cat` (weight 10)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_dead_cat(df_daily, plan, macro_snap) -> CheckResult` — for bullish plans only: fires when price is in a G45 daily downtrend, has bounced ≥ 5% off a ≤ 20-day low, **and** structure shows no confirmed higher low + higher high pair since that low ("no structure shift yet"). Evidence: days since low, bounce %, structure verdict.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_redflags.py`)

```python
from swingbot.core.gate.redflags import rf_dead_cat
from tests.fixtures.gate import dead_cat


def _reversal_with_structure():
    """Downtrend, then bounce -> higher low -> higher high: a real shift."""
    lead = np.full(200, 150.0)
    down = 150.0 * (1 - 0.01) ** np.arange(40)
    low = down[-1]
    leg1 = np.linspace(low, low * 1.06, 5)[1:]
    dip = np.linspace(low * 1.06, low * 1.03, 4)[1:]      # higher low
    leg2 = np.linspace(low * 1.03, low * 1.09, 6)[1:]     # higher high
    return make_ohlcv(np.concatenate([lead, down, leg1, dip, leg2]), spread_pct=2.0)


def test_dead_cat_fires_on_v_bounce():
    result = rf_dead_cat(dead_cat(bounce_pct=8.0), make_plan(direction="bullish"), None)
    assert result.status == "fail"
    assert result.evidence["bounce_pct"] >= 5


def test_structure_shift_passes():
    assert rf_dead_cat(_reversal_with_structure(),
                       make_plan(direction="bullish"), None).status == "pass"


def test_bearish_plan_na():
    result = rf_dead_cat(dead_cat(), make_plan(direction="bearish"), None)
    assert result.status == "pass" and "n/a" in result.detail
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'rf_dead_cat'`)
- [ ] **Step 3: Write the implementation** (append to `redflags.py`)

```python
def rf_dead_cat(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    spec = CHECKS["rf_dead_cat"]
    if plan.direction != "bullish":
        return _rf("rf_dead_cat", "pass", "n/a (bearish plan)", {}, 10.0)
    from swingbot.core.gate.context_htf import htf_trend
    closes = df_daily["Close"]
    if len(closes) < 60:
        return _rf("rf_dead_cat", "unknown", "insufficient history", {}, 10.0)
    if htf_trend(df_daily)["daily"] != "down":
        return _rf("rf_dead_cat", "pass", "not in a daily downtrend", {}, 10.0)
    tail = closes.iloc[-20:]
    low_pos = int(np.argmin(tail.values))
    low_val = float(tail.iloc[low_pos])
    bounce_pct = (float(tail.iloc[-1]) / low_val - 1.0) * 100.0
    evidence = {"bounce_pct": round(bounce_pct, 1),
                "days_since_low": len(tail) - 1 - low_pos}
    if bounce_pct < spec.threshold("bounce_pct"):
        return _rf("rf_dead_cat", "pass", "no meaningful bounce yet", evidence, 10.0)
    # structure shift = a pullback low ABOVE the low, then a new bounce high
    vals = tail.values[low_pos:]
    structure = False
    for i in range(1, len(vals) - 1):
        is_local_low = vals[i] < vals[i - 1] and vals[i] < vals[i + 1]
        if is_local_low and vals[i] > low_val and float(max(vals[i + 1:])) > float(max(vals[:i])):
            structure = True
            break
    evidence["structure_shift"] = structure
    if structure:
        return _rf("rf_dead_cat", "pass",
                   "higher-low + higher-high printed since the low", evidence, 10.0)
    return _rf("rf_dead_cat", "fail",
               f"dead-cat risk: +{bounce_pct:.1f}% V-bounce in a downtrend, "
               f"no structure shift yet", evidence, 10.0)


register(check_id="rf_dead_cat", section="redflag", weight=10.0, func=rf_dead_cat,
         thresholds={
             "bounce_pct": ThresholdSpec("bounce_pct", 5.0, 2.0, 15.0, 0.5,
                 "raise to flag only larger bounces",
                 presets={"strict": 4.0, "balanced": 5.0, "relaxed": 8.0}),
         })
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_redflags.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/redflags.py tests/test_gate_redflags.py
git commit -m "feat: rf_dead_cat"
```

### Task G60: `rf_divergence_trap` (weight 8)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_divergence_trap(df_daily, plan, macro_snap) -> CheckResult` — for divergence-entry strategies: fires when the divergence exists but price has NOT yet confirmed (no close above the divergence swing's high for longs / below the low for shorts) — "divergence alone, without price confirmation". Pass once the confirmation close printed.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_redflags.py`)

```python
from swingbot.core.gate.redflags import rf_divergence_trap


def _bullish_divergence(confirmed: bool):
    """Steep decline (RSI cold) -> bounce to 108 -> gentle grind to a LOWER
    low (RSI warmer = bullish divergence). Confirmation = close above 108."""
    closes = list(np.full(40, 130.0))
    closes += list(np.linspace(130, 100, 20))[1:]
    closes += list(np.linspace(100, 108, 6))[1:]
    closes += list(np.linspace(108, 98, 16))[1:]
    if confirmed:
        closes += list(np.linspace(98, 110, 8))[1:]     # closes above 108
    else:
        closes += list(np.linspace(98, 103, 5))[1:]     # bounce, still below 108
    return make_ohlcv(np.asarray(closes), spread_pct=0.5)


DIV_PLAN = make_plan(strategy="RSI Divergence", direction="bullish")


def test_unconfirmed_divergence_fires():
    result = rf_divergence_trap(_bullish_divergence(confirmed=False), DIV_PLAN, None)
    assert result.status == "fail" and "confirmation" in result.detail


def test_confirmed_divergence_passes():
    assert rf_divergence_trap(_bullish_divergence(confirmed=True),
                              DIV_PLAN, None).status == "pass"


def test_non_divergence_strategy_na():
    result = rf_divergence_trap(_bullish_divergence(False),
                                make_plan(strategy="VWAP"), None)
    assert result.status == "pass" and "n/a" in result.detail
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'rf_divergence_trap'`)
- [ ] **Step 3: Write the implementation** (append to `redflags.py`)

```python
def rf_divergence_trap(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """For divergence-ENTRY strategies: divergence exists but price has
    not confirmed it (no close beyond the intervening swing)."""
    if plan.strategy != "RSI Divergence":
        return _rf("rf_divergence_trap", "pass", "n/a (not a divergence entry)", {}, 8.0)
    from swingbot.core.gate.setup_quality import _pivot_high_positions
    closes_full = df_daily["Close"]
    if len(closes_full) < 60:
        return _rf("rf_divergence_trap", "unknown", "insufficient history", {}, 8.0)
    window = closes_full.iloc[-60:]
    rsi_window = rsi(closes_full).iloc[-60:]
    bullish = plan.direction == "bullish"
    price_probe = -window if bullish else window       # pivot LOWS via negation
    rsi_probe = -rsi_window if bullish else rsi_window
    pivots = _pivot_high_positions(price_probe, span=3)[-2:]
    if len(pivots) < 2:
        return _rf("rf_divergence_trap", "pass", "no divergence structure found", {}, 8.0)
    a, b = pivots
    # bullish: price lower low (probe higher) with RSI higher low (probe lower)
    divergent = (price_probe.iloc[b] > price_probe.iloc[a]
                 and rsi_probe.iloc[b] < rsi_probe.iloc[a])
    if not divergent:
        return _rf("rf_divergence_trap", "pass", "no active divergence", {}, 8.0)
    swing = float(window.iloc[a:b + 1].max()) if bullish else float(window.iloc[a:b + 1].min())
    last = float(window.iloc[-1])
    confirmed = last > swing if bullish else last < swing
    evidence = {"swing_level": round(swing, 2), "last_close": round(last, 2)}
    if confirmed:
        return _rf("rf_divergence_trap", "pass",
                   f"divergence confirmed by close beyond {swing:.2f}", evidence, 8.0)
    return _rf("rf_divergence_trap", "fail",
               "divergence without price confirmation — wait for the "
               "confirmation close", evidence, 8.0)


register(check_id="rf_divergence_trap", section="redflag", weight=8.0,
         func=rf_divergence_trap, applies_to=("RSI Divergence",))
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_redflags.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/redflags.py tests/test_gate_redflags.py
git commit -m "feat: rf_divergence_trap"
```

### Task G61: `rf_extreme_fade` (weight 8)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_extreme_fade(df_daily, plan, macro_snap) -> CheckResult` — fires when the plan fades a strong trend on overbought/oversold alone: counter-trend plan (vs G45 daily trend) + RSI beyond 75/25 + ADX(14) > 30 (strong trend — "overbought can stay overbought"). Counter-trend with ADX < 20 → warn only.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_redflags.py`)

```python
from swingbot.core.gate.redflags import rf_extreme_fade
from tests.fixtures.gate import climax_overbought, range_daily


def test_fading_strong_trend_fires():
    short_fade = make_plan(direction="bearish", strategy="RSI")
    result = rf_extreme_fade(climax_overbought(), short_fade, None)
    assert result.status == "fail"
    assert result.evidence["rsi"] > 75 and result.evidence["adx"] > 30


def test_range_fade_passes():
    short_fade = make_plan(direction="bearish", strategy="RSI")
    assert rf_extreme_fade(range_daily(90, 110, n=300), short_fade, None).status == "pass"


def test_with_trend_plan_passes():
    long_with = make_plan(direction="bullish")
    assert rf_extreme_fade(climax_overbought(), long_with, None).status == "pass"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'rf_extreme_fade'`)
- [ ] **Step 3: Write the implementation** (append to `redflags.py`)

```python
def rf_extreme_fade(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """Fading a STRONG trend on overbought/oversold alone — "overbought
    can stay overbought". Weak-trend counter plays warn only (mean
    reversion's own edge IS fading; G80 relaxes applies_to accordingly)."""
    spec = CHECKS["rf_extreme_fade"]
    from swingbot.core.gate.context_htf import htf_trend
    trend = htf_trend(df_daily)["daily"]
    bullish = plan.direction == "bullish"
    counter = (trend == "down" and bullish) or (trend == "up" and not bullish)
    if not counter:
        return _rf("rf_extreme_fade", "pass", "not a counter-trend plan",
                   {"trend": trend}, 8.0)
    rsi_val = float(rsi(df_daily["Close"]).iloc[-1])
    adx_val = float(adx(df_daily).iloc[-1])
    extreme = (rsi_val <= spec.threshold("rsi_lo") if bullish
               else rsi_val >= spec.threshold("rsi_hi"))
    evidence = {"rsi": round(rsi_val, 1), "adx": round(adx_val, 1), "trend": trend}
    if not extreme:
        return _rf("rf_extreme_fade", "pass",
                   "counter-trend but not at an RSI extreme", evidence, 8.0)
    if adx_val > spec.threshold("adx_strong"):
        return _rf("rf_extreme_fade", "fail",
                   f"fading a strong trend (ADX {adx_val:.0f}) on RSI "
                   f"{rsi_val:.0f} alone", evidence, 8.0)
    return _rf("rf_extreme_fade", "warn",
               f"counter-trend fade (ADX {adx_val:.0f} — trend not strong)",
               evidence, 8.0)


register(check_id="rf_extreme_fade", section="redflag", weight=8.0,
         func=rf_extreme_fade,
         thresholds={
             "rsi_hi": ThresholdSpec("rsi_hi", 75.0, 60.0, 90.0, 1.0,
                 "raise to flag only more extreme overbought fades",
                 presets={"strict": 70.0, "balanced": 75.0, "relaxed": 85.0}),
             "rsi_lo": ThresholdSpec("rsi_lo", 25.0, 10.0, 40.0, 1.0,
                 "lower to flag only more extreme oversold fades",
                 presets={"strict": 30.0, "balanced": 25.0, "relaxed": 15.0}),
             "adx_strong": ThresholdSpec("adx_strong", 30.0, 20.0, 50.0, 1.0,
                 "raise to fail only against the very strongest trends",
                 presets={"strict": 25.0, "balanced": 30.0, "relaxed": 40.0}),
         })
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_redflags.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/redflags.py tests/test_gate_redflags.py
git commit -m "feat: rf_extreme_fade"
```

### Task G62: `rf_news_whipsaw` (weight 10, **HB** inside the blackout window)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_news_whipsaw(df_daily, plan, macro_snap) -> CheckResult` — from `macro_snap["events"]`: importance-3 event (CPI/NFP/FOMC) within the blackout window (config `GATE_BLACKOUT_HOURS_BEFORE` default 18, `_AFTER` default 2, added to config here) → **fail/HB**; importance-2 within window → warn; earnings within `GATE_EARNINGS_BLACKOUT_DAYS` (default 3, reuses G33; defers to edge-engine E18 gate if merged) → fail. Snapshot missing → `unknown`.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_redflags.py`)

```python
import swingbot.config as config
import swingbot.core.gate.redflags as redflags
from swingbot.core.gate.redflags import rf_news_whipsaw

NOW = dt.datetime(2026, 7, 14, 16, 0, tzinfo=dt.timezone.utc)


def _snap_with(events_24h):
    return {"events": {"next_high_impact": events_24h[0] if events_24h else None,
                       "within_24h": events_24h, "today": []}}


def test_cpi_tomorrow_fires_hard(monkeypatch):
    monkeypatch.setattr(redflags.earnings, "earnings_within",
                        lambda *a, **k: None)
    cpi = {"date": "2026-07-15", "time_et": "08:30", "kind": "cpi",
           "label": "CPI release", "importance": 3}
    result = rf_news_whipsaw(uptrend_daily(), make_plan(), _snap_with([cpi]), now=NOW)
    assert result.status == "fail"                    # ~16.5h ahead, inside 18h window
    from swingbot.core.gate.registry import CHECKS
    assert CHECKS["rf_news_whipsaw"].hard_block is True


def test_importance_2_warns(monkeypatch):
    monkeypatch.setattr(redflags.earnings, "earnings_within", lambda *a, **k: None)
    ppi = {"date": "2026-07-15", "time_et": "08:30", "kind": "ppi",
           "label": "PPI release", "importance": 2}
    assert rf_news_whipsaw(uptrend_daily(), make_plan(),
                           _snap_with([ppi]), now=NOW).status == "warn"


def test_quiet_week_passes(monkeypatch):
    monkeypatch.setattr(redflags.earnings, "earnings_within", lambda *a, **k: False)
    assert rf_news_whipsaw(uptrend_daily(), make_plan(),
                           _snap_with([]), now=NOW).status == "pass"


def test_earnings_inside_blackout_fires(monkeypatch):
    monkeypatch.setattr(redflags.earnings, "earnings_within", lambda *a, **k: True)
    result = rf_news_whipsaw(uptrend_daily(), make_plan(), _snap_with([]), now=NOW)
    assert result.status == "fail" and "earnings" in result.detail


def test_no_snapshot_unknown():
    assert rf_news_whipsaw(uptrend_daily(), make_plan(), None, now=NOW).status == "unknown"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'rf_news_whipsaw'`)
- [ ] **Step 3: Write the implementation** (append to `redflags.py`; plus config Fields)

```python
import swingbot.config as config
from swingbot.core.macro import calendar_events, earnings


def rf_news_whipsaw(df_daily, plan, macro_snap, *, now=None, **ctx) -> CheckResult:
    """HB inside the blackout window. Statuses are information — actually
    holding an entry additionally requires GATE_BLACKOUT_ENFORCE (G120)."""
    if not macro_snap or not macro_snap.get("events"):
        return _rf("rf_news_whipsaw", "unknown", "no event calendar available", {}, 10.0)
    now = now or dt.datetime.now(dt.timezone.utc)
    before = float(getattr(config, "GATE_BLACKOUT_HOURS_BEFORE", 18))
    after = float(getattr(config, "GATE_BLACKOUT_HOURS_AFTER", 2))
    seen = {}
    ev_section = macro_snap["events"]
    for e in (ev_section.get("within_24h") or []) + \
             ([ev_section["next_high_impact"]] if ev_section.get("next_high_impact") else []):
        seen[(e["date"], e["kind"])] = e
    for event in seen.values():
        hours = calendar_events.hours_until(event, now)
        if -after <= hours <= before:
            detail = f"{event['label']} in {hours:.0f}h — inside the blackout window"
            if event["importance"] >= 3:
                return _rf("rf_news_whipsaw", "fail", detail,
                           {"event": event, "hours": round(hours, 1)}, 10.0)
            return _rf("rf_news_whipsaw", "warn", detail,
                       {"event": event, "hours": round(hours, 1)}, 10.0)
    # Earnings blackout (reuses G33; defers to edge E18's gate if merged)
    days = int(getattr(config, "GATE_EARNINGS_BLACKOUT_DAYS", 3))
    within = earnings.earnings_within(plan.ticker, days, now=now.date())
    if within:
        return _rf("rf_news_whipsaw", "fail",
                   f"earnings within {days} days", {"earnings_within_days": days}, 10.0)
    return _rf("rf_news_whipsaw", "pass", "no high-impact event in the window", {}, 10.0)


register(check_id="rf_news_whipsaw", section="redflag", weight=10.0,
         func=rf_news_whipsaw, hard_block=True)
```

```python
# swingbot/config.py — append to the Gatekeeper section:
    Field("GATE_BLACKOUT_HOURS_BEFORE", "GATE_BLACKOUT_HOURS_BEFORE", "Gatekeeper",
          "Blackout hours before event", type="float", default="18", min=0, max=72, step=1,
          help="High-impact events (CPI/NFP/FOMC) within this many hours ahead flag the "
               "checklist. Lower to shrink the annotation window."),
    Field("GATE_BLACKOUT_HOURS_AFTER", "GATE_BLACKOUT_HOURS_AFTER", "Gatekeeper",
          "Blackout hours after event", type="float", default="2", min=0, max=24, step=0.5,
          help="The window stays flagged this long after the print."),
    Field("GATE_EARNINGS_BLACKOUT_DAYS", "GATE_EARNINGS_BLACKOUT_DAYS", "Gatekeeper",
          "Earnings blackout days", type="number", default="3", min=0, max=15, step=1,
          help="Flag plans whose ticker reports earnings within this many days. "
               "Lower to allow entries closer to earnings."),
```

(Extend `tests/test_gate_config.py`'s expected-keys map with these three.)

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_redflags.py tests/test_gate_config.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/redflags.py swingbot/config.py tests/test_gate_redflags.py tests/test_gate_config.py
git commit -m "feat: rf_news_whipsaw + blackout config"
```

### Task G65: `rf_thin_session` (weight 6)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_thin_session(df_daily, plan, macro_snap, now=None) -> CheckResult` — from G32: fires (warn-grade fail→warn mapping: this one is `warn`, never `fail` — EOD swing entries mostly dodge it) when *now* is a half-day, holiday-adjacent thin week, or intraday thin window and the plan's entry could trigger in it; plus fires when the ticker's own 20d median dollar-volume < config floor `GATE_MIN_DOLLAR_VOL` (float field, default 2_000_000).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_redflags.py`)

```python
from swingbot.core.gate.redflags import rf_thin_session


def _liquid_df():
    return make_ohlcv(np.full(60, 50.0), volumes=np.full(60, 1_000_000.0))


def test_holiday_week_warns():
    holiday_week = dt.datetime(2026, 12, 29, 16, 0, tzinfo=dt.timezone.utc)  # 11:00 ET
    result = rf_thin_session(_liquid_df(), make_plan(), None, now=holiday_week)
    assert result.status == "warn" and "holiday week" in result.detail


def test_liquid_normal_day_passes():
    normal = dt.datetime(2026, 7, 14, 16, 0, tzinfo=dt.timezone.utc)         # 12:00 ET Tue
    assert rf_thin_session(_liquid_df(), make_plan(), None, now=normal).status == "pass"


def test_illiquid_ticker_warns():
    normal = dt.datetime(2026, 7, 14, 16, 0, tzinfo=dt.timezone.utc)
    thin = make_ohlcv(np.full(60, 2.0), volumes=np.full(60, 100_000.0))      # $200k/day
    result = rf_thin_session(thin, make_plan(), None, now=normal)
    assert result.status == "warn" and "dollar volume" in result.detail
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'rf_thin_session'`)
- [ ] **Step 3: Write the implementation** (append to `redflags.py`; plus one config Field)

```python
def rf_thin_session(df_daily, plan, macro_snap, *, now=None, **ctx) -> CheckResult:
    """warn-grade only — EOD swing entries mostly dodge intraday windows,
    but illiquid tickers and dead weeks still deserve the label."""
    from swingbot.core.macro.sessions import is_thin_window
    dollar_vol = float((df_daily["Close"] * df_daily["Volume"]).iloc[-20:].median())
    floor = float(getattr(config, "GATE_MIN_DOLLAR_VOL", 2_000_000))
    if dollar_vol < floor:
        return _rf("rf_thin_session", "warn",
                   f"median dollar volume ${dollar_vol:,.0f} below the "
                   f"${floor:,.0f} floor",
                   {"dollar_vol": round(dollar_vol)}, 6.0)
    now_et = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ET)
    thin, reason = is_thin_window(now_et)
    if thin:
        return _rf("rf_thin_session", "warn", f"thin session: {reason}",
                   {"reason": reason}, 6.0)
    return _rf("rf_thin_session", "pass", "normal liquidity conditions",
               {"dollar_vol": round(dollar_vol)}, 6.0)


register(check_id="rf_thin_session", section="redflag", weight=6.0,
         func=rf_thin_session, trigger_recheck=True)
```

```python
# swingbot/config.py — append to the Gatekeeper section:
    Field("GATE_MIN_DOLLAR_VOL", "GATE_MIN_DOLLAR_VOL", "Gatekeeper",
          "Min median dollar volume", type="float", default="2000000", min=0, step=100000,
          help="Tickers whose 20d median dollar volume sits below this get a "
               "thin-liquidity warning on the checklist. Lower to silence it "
               "for small caps."),
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_redflags.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/redflags.py swingbot/config.py tests/test_gate_redflags.py
git commit -m "feat: rf_thin_session"
```

### Task G67: `rf_beta_move` (weight 6, "is this really my instrument's move?")

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_beta_move(df_daily, plan, macro_snap, spy_df=None) -> CheckResult` — regress ticker daily returns on SPY (60d) → beta + residual; fires when the signal move's residual (move minus beta×SPY move over the signal window) is < 35% of the raw move — the "signal" is just index beta, and it evaporates when the index mean-reverts. Evidence: beta, raw vs idiosyncratic move %. SPY bars missing → unknown.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_redflags.py`)

```python
from swingbot.core.gate.redflags import rf_beta_move


def _spy_and_clone(pure_beta: bool):
    """SPY with alternating returns; ticker either 1.2x SPY exactly
    (pure beta) or flat-then-idiosyncratic-gap."""
    spy_closes, tick_closes = [100.0], [50.0]
    for i in range(120):
        r = 0.01 if i % 2 == 0 else -0.008
        spy_closes.append(spy_closes[-1] * (1 + r))
        tick_closes.append(tick_closes[-1] * (1 + (1.2 * r if pure_beta else 0.0)))
    if not pure_beta:
        tick_closes[-1] = tick_closes[-2] * 1.10        # +10% on flat SPY
    return (make_ohlcv(np.asarray(spy_closes)),
            make_ohlcv(np.asarray(tick_closes)))


def test_pure_beta_move_fires():
    spy, tick = _spy_and_clone(pure_beta=True)
    result = rf_beta_move(tick, make_plan(), None, spy_df=spy)
    assert result.status == "fail"
    assert result.evidence["idio_frac"] < 0.35


def test_idiosyncratic_gap_passes():
    spy, tick = _spy_and_clone(pure_beta=False)
    assert rf_beta_move(tick, make_plan(), None, spy_df=spy).status == "pass"


def test_missing_spy_unknown():
    _, tick = _spy_and_clone(True)
    assert rf_beta_move(tick, make_plan(), None, spy_df=None).status == "unknown"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'rf_beta_move'`)
- [ ] **Step 3: Write the implementation** (append to `redflags.py`)

```python
def rf_beta_move(df_daily, plan, macro_snap, *, spy_df=None, **ctx) -> CheckResult:
    """Is this really MY instrument's move? Regress 60d daily returns on
    SPY; if the signal-window move is mostly beta x index, it evaporates
    when the index mean-reverts."""
    spec = CHECKS["rf_beta_move"]
    if spy_df is None or len(spy_df) < 70 or len(df_daily) < 70:
        return _rf("rf_beta_move", "unknown", "SPY bars unavailable", {}, 6.0)
    t_ret = df_daily["Close"].pct_change().dropna().iloc[-60:]
    s_ret = spy_df["Close"].pct_change().dropna().iloc[-60:]
    joined = pd.concat([t_ret.rename("t"), s_ret.rename("s")], axis=1).dropna()
    if len(joined) < 40:
        return _rf("rf_beta_move", "unknown", "insufficient overlapping bars", {}, 6.0)
    var_s = float(np.var(joined["s"]))
    beta = float(np.cov(joined["t"], joined["s"])[0, 1] / (var_s or 1e-12))
    window = int(spec.threshold("signal_window"))
    t_move = float(df_daily["Close"].iloc[-1] / df_daily["Close"].iloc[-1 - window] - 1)
    s_move = float(spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[-1 - window] - 1)
    if abs(t_move) < 1e-6:
        return _rf("rf_beta_move", "pass", "no signal move to attribute",
                   {"beta": round(beta, 2)}, 6.0)
    residual = t_move - beta * s_move
    idio_frac = abs(residual) / abs(t_move)
    evidence = {"beta": round(beta, 2), "move_pct": round(t_move * 100, 1),
                "idio_frac": round(idio_frac, 2)}
    if idio_frac < spec.threshold("idio_frac"):
        return _rf("rf_beta_move", "fail",
                   f"move is ~{(1 - idio_frac) * 100:.0f}% index beta "
                   f"(beta {beta:.1f}) — not this instrument's own move",
                   evidence, 6.0)
    return _rf("rf_beta_move", "pass",
               f"{idio_frac * 100:.0f}% of the move is idiosyncratic", evidence, 6.0)


register(check_id="rf_beta_move", section="redflag", weight=6.0, func=rf_beta_move,
         thresholds={
             "idio_frac": ThresholdSpec("idio_frac", 0.35, 0.1, 0.8, 0.05,
                 "lower to tolerate more index-driven moves",
                 presets={"strict": 0.5, "balanced": 0.35, "relaxed": 0.2}),
             "signal_window": ThresholdSpec("signal_window", 5, 2, 15, 1,
                 "bars defining 'the signal move'",
                 presets={"strict": 5, "balanced": 5, "relaxed": 5}),
         })
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_redflags.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/redflags.py tests/test_gate_redflags.py
git commit -m "feat: rf_beta_move idiosyncrasy check"
```

## Section 4 — Risk definition

Stop placement and target realism only. The sizing checks that used to live here
(`size_formula` G69, `portfolio_room` G71) were cut in the win-rate audit: position
size moves expectancy and risk of ruin, never win rate.

### Task G68: Check `stop_structural` (weight 10, §4 "stop beyond structure, widened ~1 ATR")

**Files:**
- Create: `swingbot/core/gate/risk_def.py`; modify `registry.py`
- Test: `tests/test_gate_risk.py`

**Interfaces:** `check_stop_structural(df_daily, plan, macro_snap) -> CheckResult` — the plan's stop must sit beyond the nearest protective structure level (G47 support for longs) by ≥ 0.5 ATR and not *exactly at* an obvious level/round number (within 0.15 ATR of one → warn "sweep bait"). Stop inside the structure → **fail**. Advisory-only against the v2 exit model: this check flags, it never mutates the plan's stop (Global Constraints — exit geometry is v2-validated).
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_risk.py
import numpy as np

from swingbot.core.gate.risk_def import check_stop_structural
from tests.conftest import make_ohlcv
from tests.fixtures.gate.plans import make_plan


def _support_touches(support=100.0, top=110.0, n=120):
    """Three clean touches of a support at ~100 (valleys unique)."""
    closes = []
    for _ in range(3):
        closes += list(np.linspace(top, support, 15)) + list(np.linspace(support, top, 15))[1:]
    closes += list(np.linspace(top, top * 1.01, n - len(closes)))
    return make_ohlcv(np.asarray(closes), spread_pct=0.5)


def test_beyond_and_wide_passes():
    # support (with spread) ~99.75; stop 98.4 is >0.5 ATR beyond, off-level
    plan = make_plan(direction="bullish", trigger_price=104.0, entry_price=104.0,
                     stop_loss=98.4, tp1=112.0)
    result = check_stop_structural(_support_touches(), plan, None)
    assert result.status == "pass"
    assert result.evidence["margin_atr"] >= 0.5


def test_at_level_or_too_tight_warns():
    plan = make_plan(direction="bullish", trigger_price=104.0, entry_price=104.0,
                     stop_loss=99.7, tp1=112.0)      # a hair beyond the structure
    assert check_stop_structural(_support_touches(), plan, None).status == "warn"


def test_inside_structure_fails():
    plan = make_plan(direction="bullish", trigger_price=104.0, entry_price=104.0,
                     stop_loss=101.0, tp1=112.0)     # above the support = inside
    assert check_stop_structural(_support_touches(), plan, None).status == "fail"
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_gate_risk.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/gate/risk_def.py
"""Section-4 risk-definition checks. Advisory-only: these flag, they
never mutate the plan's v2-validated exit geometry."""
from __future__ import annotations

from swingbot.core.gate.levels import (_safe_atr, round_levels, swing_levels)
from swingbot.core.gate.registry import CHECKS, ThresholdSpec, register
from swingbot.core.gate.types import CheckResult


def check_stop_structural(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    spec = CHECKS["stop_structural"]
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    atr_val = _safe_atr(df_daily, entry)
    bullish = plan.direction == "bullish"
    swings = swing_levels(df_daily)
    if bullish:
        protective = [l.price for l in swings if l.kind == "support" and l.price < entry]
        nearest = max(protective) if protective else None
        margin = (nearest - plan.stop_loss) / atr_val if nearest is not None else None
        inside = nearest is not None and plan.stop_loss > nearest
    else:
        protective = [l.price for l in swings if l.kind == "resistance" and l.price > entry]
        nearest = min(protective) if protective else None
        margin = (plan.stop_loss - nearest) / atr_val if nearest is not None else None
        inside = nearest is not None and plan.stop_loss < nearest
    if nearest is None:
        return CheckResult("stop_structural", "risk", "warn", 10.0,
                           "no structure found to anchor the stop", {"atr": round(atr_val, 4)})
    on_level = next((lvl for lvl in [l.price for l in swings] + round_levels(entry)
                     if abs(plan.stop_loss - lvl) <= spec.threshold("at_level_atr") * atr_val),
                    None)
    evidence = {"nearest_structure": round(nearest, 4), "stop": plan.stop_loss,
                "margin_atr": round(margin, 2), "on_level": on_level}
    if inside:
        return CheckResult("stop_structural", "risk", "fail", 10.0,
                           f"stop {plan.stop_loss:.2f} sits INSIDE the protective "
                           f"structure ({nearest:.2f})", evidence)
    if margin < spec.threshold("beyond_atr"):
        return CheckResult("stop_structural", "risk", "warn", 10.0,
                           f"stop only {margin:.1f} ATR beyond structure — "
                           f"checklist wants ~1 ATR of air", evidence)
    if on_level is not None:
        return CheckResult("stop_structural", "risk", "warn", 10.0,
                           f"stop parked exactly at {on_level:.2f} — sweep bait",
                           evidence)
    return CheckResult("stop_structural", "risk", "pass", 10.0,
                       f"stop {margin:.1f} ATR beyond structure", evidence)


register(check_id="stop_structural", section="risk", weight=10.0,
         func=check_stop_structural,
         thresholds={
             "beyond_atr": ThresholdSpec("beyond_atr", 0.5, 0.1, 2.0, 0.1,
                 "lower to accept tighter stops behind structure",
                 presets={"strict": 0.8, "balanced": 0.5, "relaxed": 0.25}),
             "at_level_atr": ThresholdSpec("at_level_atr", 0.15, 0.05, 0.5, 0.05,
                 "lower to only flag stops sitting dead on a level",
                 presets={"strict": 0.25, "balanced": 0.15, "relaxed": 0.05}),
         })
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_risk.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/risk_def.py tests/test_gate_risk.py
git commit -m "feat: stop_structural check"
```

### Task G70: Check `rr_realistic` (weight 10, §4 "R:R ≥ 1.5–2 to a realistic target")

**Files:** Modify `risk_def.py`, `registry.py`; test `tests/test_gate_risk.py`

**Interfaces:** `check_rr_realistic(df_daily, plan, macro_snap) -> CheckResult` — R:R computed to the *structure-capped* target: min(plan TP1, nearest opposing G47/G48 level). Capped R:R ≥ `GATE_MIN_RR` (float field, default 1.5) → pass; 1.2–1.5 → warn; < 1.2 → **fail**. Evidence shows both the plan's nominal R:R and the structure-capped one (the honest number).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_risk.py`)

```python
from swingbot.core.gate.risk_def import check_rr_realistic


def _resistance_touches(level=110.0, base=100.0, n=120):
    closes = []
    for _ in range(3):
        closes += list(np.linspace(base, level, 15)) + list(np.linspace(level, base, 15))[1:]
    closes += list(np.linspace(base, base * 1.04, n - len(closes)))
    return make_ohlcv(np.asarray(closes), spread_pct=0.5)


def test_wall_capped_rr_fails_despite_nominal_2to1():
    # nominal RR = (115-104)/5.5 = 2.0, but the ~110 wall caps it at ~1.15
    plan = make_plan(direction="bullish", trigger_price=104.0, entry_price=104.0,
                     stop_loss=98.5, tp1=115.0)
    result = check_rr_realistic(_resistance_touches(), plan, None)
    assert result.status == "fail"
    assert result.evidence["nominal_rr"] >= 1.9
    assert result.evidence["capped_rr"] < 1.2


def test_clear_sky_passes():
    # entry above the wall: nothing caps TP1
    plan = make_plan(direction="bullish", trigger_price=111.0, entry_price=111.0,
                     stop_loss=107.0, tp1=119.0)
    result = check_rr_realistic(_resistance_touches(), plan, None)
    assert result.status == "pass" and result.evidence["capped_rr"] >= 1.5
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'check_rr_realistic'`)
- [ ] **Step 3: Write the implementation** (append to `risk_def.py`)

```python
def check_rr_realistic(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """R:R to the STRUCTURE-CAPPED target — min(TP1, nearest opposing
    wall) — the honest number, shown next to the nominal one."""
    spec = CHECKS["rr_realistic"]
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    risk = abs(entry - plan.stop_loss)
    if risk <= 0:
        return CheckResult("rr_realistic", "risk", "fail", 10.0,
                           "zero stop distance", {})
    bullish = plan.direction == "bullish"
    swings = swing_levels(df_daily)
    if bullish:
        opposing = [l.price for l in swings if l.kind == "resistance" and l.price > entry]
        capped_target = min([plan.tp1] + opposing)
        capped_rr = (capped_target - entry) / risk
    else:
        opposing = [l.price for l in swings if l.kind == "support" and l.price < entry]
        capped_target = max([plan.tp1] + opposing)
        capped_rr = (entry - capped_target) / risk
    nominal_rr = abs(plan.tp1 - entry) / risk
    evidence = {"nominal_rr": round(nominal_rr, 2), "capped_rr": round(capped_rr, 2),
                "capped_target": round(capped_target, 2)}
    if capped_rr >= spec.threshold("min_rr"):
        return CheckResult("rr_realistic", "risk", "pass", 10.0,
                           f"structure-capped R:R {capped_rr:.1f}", evidence)
    if capped_rr >= spec.threshold("warn_rr"):
        return CheckResult("rr_realistic", "risk", "warn", 10.0,
                           f"capped R:R only {capped_rr:.1f} "
                           f"(nominal {nominal_rr:.1f})", evidence)
    return CheckResult("rr_realistic", "risk", "fail", 10.0,
                       f"capped R:R {capped_rr:.1f} — the wall eats the trade "
                       f"(nominal {nominal_rr:.1f} is not the honest number)",
                       evidence)


register(check_id="rr_realistic", section="risk", weight=10.0,
         func=check_rr_realistic,
         thresholds={
             "min_rr": ThresholdSpec("min_rr", 1.5, 1.0, 3.0, 0.1,
                 "lower to accept slimmer capped targets (this is GATE_MIN_RR)",
                 presets={"strict": 2.0, "balanced": 1.5, "relaxed": 1.2}),
             "warn_rr": ThresholdSpec("warn_rr", 1.2, 0.8, 2.0, 0.1,
                 "lower to fail less often",
                 presets={"strict": 1.4, "balanced": 1.2, "relaxed": 1.0}),
         })
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_risk.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/risk_def.py tests/test_gate_risk.py
git commit -m "feat: rr_realistic (structure-capped) check"
```

## Section 5 — Timing & trigger

### Task G72: Check `trigger_objective` (weight 6, **HB**, §5 "entry trigger is objective, not a feel")

**Files:**
- Create: `swingbot/core/gate/timing.py`; modify `registry.py`
- Test: `tests/test_gate_timing.py`

**Interfaces:** `check_trigger_objective(df_daily, plan, macro_snap) -> CheckResult` — asserts the plan carries a machine-readable trigger: `entry_type` in the TradePlanV2 vocabulary (limit/stop/close-confirm...) with a concrete price. Missing/None entry price or unknown entry_type → **fail/HB** (a plan the bot can't state objectively is a feel). This is a plan-integrity invariant — it should never fire in production, and firing = engine bug surfaced loudly.
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_timing.py
from swingbot.core.gate.registry import CHECKS
from swingbot.core.gate.timing import check_trigger_objective
from tests.fixtures.gate import uptrend_daily
from tests.fixtures.gate.plans import make_plan


def test_well_formed_plan_passes():
    assert check_trigger_objective(uptrend_daily(), make_plan(), None).status == "pass"


def test_priceless_plan_fails_hard():
    broken = make_plan(trigger_price=None)
    result = check_trigger_objective(uptrend_daily(), broken, None)
    assert result.status == "fail"
    assert CHECKS["trigger_objective"].hard_block is True


def test_unknown_entry_type_fails():
    weird = make_plan(entry_type="vibes")
    assert check_trigger_objective(uptrend_daily(), weird, None).status == "fail"
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_gate_timing.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/gate/timing.py
"""Section-5 timing & trigger checks."""
from __future__ import annotations

from swingbot.core.gate.levels import _safe_atr
from swingbot.core.gate.registry import CHECKS, ThresholdSpec, register
from swingbot.core.gate.types import CheckResult

# TradePlanV2's machine-readable entry vocabulary (plan_engine.py) —
# extend here if the engine grows new entry types.
ENTRY_TYPES = ("stop_entry", "market")


def check_trigger_objective(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """Plan-integrity invariant (HB). Firing in production = engine bug
    surfaced loudly, not a market condition."""
    problems = []
    if plan.entry_type not in ENTRY_TYPES:
        problems.append(f"unknown entry_type {plan.entry_type!r}")
    if plan.trigger_price is None or not isinstance(plan.trigger_price, (int, float)) \
            or plan.trigger_price <= 0:
        problems.append("no concrete trigger price")
    if problems:
        return CheckResult("trigger_objective", "timing", "fail", 6.0,
                           "plan has no objective trigger: " + "; ".join(problems),
                           {"entry_type": str(plan.entry_type),
                            "trigger_price": plan.trigger_price})
    return CheckResult("trigger_objective", "timing", "pass", 6.0,
                       f"objective trigger: {plan.entry_type} @ {plan.trigger_price:.2f}",
                       {"entry_type": plan.entry_type})


register(check_id="trigger_objective", section="timing", weight=6.0,
         func=check_trigger_objective, hard_block=True, backtestable=False)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_timing.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/timing.py tests/test_gate_timing.py
git commit -m "feat: trigger_objective invariant check"
```

### Task G73: Check `not_chasing` (weight 8, §5 "price hasn't already run far past")

**Files:** Modify `timing.py`, `registry.py`; test `tests/test_gate_timing.py`

**Interfaces:** `check_not_chasing(df_daily, plan, macro_snap) -> CheckResult` — distance from signal level to current price: pass ≤ 0.5 ATR, warn 0.5–1.0, **fail** > `GATE_CHASE_ATR_MAX` (float field, default 1.0) ATR past the trigger (late entry wrecks the R:R that was validated).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_timing.py`)

```python
import numpy as np

from swingbot.core.gate.timing import check_not_chasing
from tests.conftest import make_ohlcv


def _df_at(price):
    return make_ohlcv(np.concatenate([np.full(59, price * 0.97), [price]]),
                      spread_pct=2.0)


def test_fresh_entry_passes():
    # price at 100.2, trigger 100, ATR ~2 -> 0.1 ATR past: fresh
    plan = make_plan(direction="bullish", trigger_price=100.0)
    assert check_not_chasing(_df_at(100.2), plan, None).status == "pass"


def test_late_entry_fails():
    # price at 103.5 with ATR ~2 -> ~1.75 ATR past the trigger
    plan = make_plan(direction="bullish", trigger_price=100.0)
    result = check_not_chasing(_df_at(103.5), plan, None)
    assert result.status == "fail"
    assert result.evidence["dist_atr"] > 1.0


def test_not_yet_triggered_passes():
    plan = make_plan(direction="bullish", trigger_price=100.0)
    assert check_not_chasing(_df_at(99.0), plan, None).status == "pass"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'check_not_chasing'`)
- [ ] **Step 3: Write the implementation** (append to `timing.py`)

```python
def check_not_chasing(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """Distance current price has already run PAST the trigger, in ATRs.
    Late entry wrecks the R:R the plan was validated with."""
    spec = CHECKS["not_chasing"]
    price = float(df_daily["Close"].iloc[-1])
    atr_val = _safe_atr(df_daily, price)
    bullish = plan.direction == "bullish"
    past = (price - plan.trigger_price) if bullish else (plan.trigger_price - price)
    dist_atr = round(past / atr_val, 2)
    evidence = {"dist_atr": dist_atr, "price": price, "trigger": plan.trigger_price}
    if dist_atr <= spec.threshold("pass_atr"):
        return CheckResult("not_chasing", "timing", "pass", 8.0,
                           "entry is fresh", evidence)
    if dist_atr <= spec.threshold("chase_atr_max"):
        return CheckResult("not_chasing", "timing", "warn", 8.0,
                           f"price already {dist_atr} ATR past the trigger", evidence)
    return CheckResult("not_chasing", "timing", "fail", 8.0,
                       f"chasing: {dist_atr} ATR past the trigger", evidence)


register(check_id="not_chasing", section="timing", weight=8.0,
         func=check_not_chasing, trigger_recheck=True,
         thresholds={
             "pass_atr": ThresholdSpec("pass_atr", 0.5, 0.1, 1.5, 0.1,
                 "raise to call later entries still fresh",
                 presets={"strict": 0.3, "balanced": 0.5, "relaxed": 0.8}),
             "chase_atr_max": ThresholdSpec("chase_atr_max", 1.0, 0.5, 3.0, 0.1,
                 "raise to allow later entries (this is GATE_CHASE_ATR_MAX)",
                 presets={"strict": 0.8, "balanced": 1.0, "relaxed": 1.5}),
         })
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_timing.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/timing.py tests/test_gate_timing.py
git commit -m "feat: not_chasing check"
```

### Task G74: Check `calendar_checked` (weight 4, §5 "I've checked the economic calendar")

**Files:** Modify `timing.py`, `registry.py`; test `tests/test_gate_timing.py`

**Interfaces:** `check_calendar(df_daily, plan, macro_snap) -> CheckResult` — pass when the macro snapshot is fresh (< TTL) and its events section is populated (the bot literally checked the calendar this session); warn when stale; unknown when `MACRO_ENABLED` off. Complements rf_news_whipsaw: this checks that we *looked*; G62 checks what we *saw*.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_timing.py`)

```python
import datetime as dt

import swingbot.config as config
from swingbot.core.gate.timing import check_calendar


def _snap(age_min, with_events=True):
    built = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=age_min)
    events = {"next_high_impact": {"kind": "cpi"}, "within_24h": [], "today": []}
    return {"built_at": built.isoformat(), "stale": False,
            "events": events if with_events else {}}


def test_fresh_snapshot_with_events_passes(monkeypatch):
    monkeypatch.setattr(config, "MACRO_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "MACRO_SNAPSHOT_TTL_MIN", 30, raising=False)
    assert check_calendar(None, make_plan(), _snap(5)).status == "pass"


def test_stale_snapshot_warns(monkeypatch):
    monkeypatch.setattr(config, "MACRO_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "MACRO_SNAPSHOT_TTL_MIN", 30, raising=False)
    assert check_calendar(None, make_plan(), _snap(90)).status == "warn"


def test_macro_disabled_unknown(monkeypatch):
    monkeypatch.setattr(config, "MACRO_ENABLED", False, raising=False)
    assert check_calendar(None, make_plan(), None).status == "unknown"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'check_calendar'`)
- [ ] **Step 3: Write the implementation** (append to `timing.py`)

```python
import datetime as dt

import swingbot.config as config


def check_calendar(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """Did the bot literally check the calendar this session? Complements
    rf_news_whipsaw: this checks that we LOOKED; G62 checks what we SAW."""
    if not getattr(config, "MACRO_ENABLED", False) or macro_snap is None:
        return CheckResult("calendar_checked", "timing", "unknown", 4.0,
                           "macro layer off — calendar not machine-checked", {})
    try:
        built = dt.datetime.fromisoformat(macro_snap["built_at"])
        age_min = (dt.datetime.now(dt.timezone.utc) - built).total_seconds() / 60.0
    except (KeyError, TypeError, ValueError):
        return CheckResult("calendar_checked", "timing", "unknown", 4.0,
                           "snapshot has no readable timestamp", {})
    ttl = float(getattr(config, "MACRO_SNAPSHOT_TTL_MIN", 30))
    populated = bool(macro_snap.get("events"))
    evidence = {"age_min": round(age_min, 1), "events_populated": populated}
    if age_min <= ttl and populated:
        return CheckResult("calendar_checked", "timing", "pass", 4.0,
                           "calendar checked this session", evidence)
    return CheckResult("calendar_checked", "timing", "warn", 4.0,
                       "macro snapshot stale or event section empty", evidence)


register(check_id="calendar_checked", section="timing", weight=4.0,
         func=check_calendar, backtestable=False)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_timing.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/timing.py tests/test_gate_timing.py
git commit -m "feat: calendar_checked freshness check"
```

## Assembly

### Task G75: `run_checklist()` orchestrator

> **Audit note (2026-07-29):** the registry holds **21** checks — 13 checklist checks
> (G46, G49, G50, G52, G53, G54, G55, G56, G68, G70, G72, G73, G74) plus 8 red flags
> (G57–G62, G65, G67). G51, G63, G64, G66, G69, G71 were cut. The orchestrator must derive its
> check list from `registry.CHECKS` rather than any hardcoded count, and the score denominator is
> the sum of *registered* weights — never a constant copied from an older draft of this plan.

**Files:**
- Modify: `swingbot/core/gate/__init__.py`
- Test: `tests/test_gate_run.py`

**Interfaces:**
- Produces: `run_checklist(ticker, strategy, plan, df_daily, *, macro_snap=None, open_plans=None, account=None, headlines=None, spy_df=None, now=None) -> GateResult` — resolves `enabled_checks(strategy)`, calls each check inside try/except (an exception in any check → that check `unknown` + log, **never** a scan crash), assembles score (G6), tier (cuts from config, G79), hard_blocks, `macro_stale`. Deterministic given inputs. `__init__.py` re-exports `run_checklist`, `GateResult`, `CheckResult`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_run.py
import dataclasses
import datetime as dt

import pytest

from swingbot.core.gate import run_checklist
from swingbot.core.gate import registry
from tests.fixtures.gate import uptrend_daily
from tests.fixtures.gate.plans import make_plan

EVENING = dt.datetime(2026, 7, 14, 23, 0, tzinfo=dt.timezone.utc)
QUIET_SNAP = {"built_at": "2026-07-14T22:00:00+00:00", "stale": False,
              "events": {"next_high_impact": None, "within_24h": [], "today": []}}


def _clean_run(strategy="Break & Retest"):
    df = uptrend_daily()
    plan = make_plan(strategy=strategy, created_at="2026-07-13",
                     trigger_price=float(df["Close"].iloc[-1]),
                     entry_price=None,
                     stop_loss=float(df["Close"].iloc[-1]) * 0.95,
                     tp1=float(df["Close"].iloc[-1]) * 1.10)
    return run_checklist(plan.ticker, strategy, plan, df,
                         macro_snap=QUIET_SNAP, now=EVENING)


def test_full_run_shape():
    result = _clean_run()
    assert {c.section for c in result.checks} == {"context", "setup", "redflag",
                                                  "risk", "timing"}
    assert 0 <= result.score <= 100
    assert result.hard_blocks == ()
    assert result.tier in ("A+", "A", "B", "C")
    assert result.as_of == str(uptrend_daily().index[-1].date())
    assert result.macro_stale is False


def test_raising_check_becomes_unknown(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("detector bug")
    spec = registry.CHECKS["atr_normal"]
    monkeypatch.setitem(registry.CHECKS, "atr_normal",
                        dataclasses.replace(spec, func=boom))
    result = _clean_run()
    by_id = {c.check_id: c for c in result.checks}
    assert by_id["atr_normal"].status == "unknown"        # never a scan crash
    assert by_id["htf_alignment"].status != "unknown"     # others unaffected


def test_strategy_filtering():
    breakout_ids = {c.check_id for c in _clean_run("Break & Retest").checks}
    vwap_ids = {c.check_id for c in _clean_run("VWAP").checks}
    assert "rf_fake_breakout" in breakout_ids
    assert "rf_fake_breakout" not in vwap_ids


def test_deterministic():
    a, b = _clean_run(), _clean_run()
    assert a.score == b.score and a.tier == b.tier
```

- [ ] **Step 2: Run — FAIL** (`ImportError: cannot import name 'run_checklist'`)
- [ ] **Step 3: Write the implementation** (replaces `swingbot/core/gate/__init__.py`)

```python
# swingbot/core/gate/__init__.py
"""Gatekeeper public API: run_checklist(), GateResult, CheckResult."""
from __future__ import annotations

import logging

import swingbot.config as config

log = logging.getLogger("swing-bot.gate")

# Importing the check modules runs their register() side effects.
from swingbot.core.gate import (atr_regime, context_htf, levels,      # noqa: F401,E402
                                redflags, risk_def, setup_quality, timing)
from swingbot.core.gate.registry import CHECKS, enabled_checks        # noqa: E402
from swingbot.core.gate.score import assign_tier, score               # noqa: E402
from swingbot.core.gate.types import CheckResult, GateResult          # noqa: E402


def run_checklist(ticker, strategy, plan, df_daily, *, macro_snap=None,
                  open_plans=None, account=None, headlines=None,
                  spy_df=None, now=None, subset: str | None = None) -> GateResult:
    """Deterministic given inputs. An exception inside any check makes THAT
    check unknown (+log) — never a scan crash. subset="trigger" runs only
    the cheap trigger_recheck checks (G128)."""
    ctx = {"open_plans": open_plans, "account": account,
           "headlines": headlines, "spy_df": spy_df, "now": now}
    checks: list[CheckResult] = []
    for spec in enabled_checks(strategy):
        if subset == "trigger" and not spec.trigger_recheck:
            continue
        try:
            result = spec.func(df_daily, plan, macro_snap, **ctx)
        except Exception:  # noqa: BLE001
            log.warning("check %s raised — recorded as unknown",
                        spec.check_id, exc_info=True)
            result = CheckResult(spec.check_id, spec.section, "unknown",
                                 spec.weight, "check errored — treated as unknown", {})
        checks.append(result)
    hard_blocks = tuple(c.check_id for c in checks
                        if c.status == "fail" and CHECKS[c.check_id].hard_block)
    total = score(checks)
    tier = assign_tier(
        total, hard_blocks,
        aplus_cut=float(getattr(config, "GATE_TIER_APLUS_CUT", 90.0)),
        a_cut=float(getattr(config, "GATE_TIER_A_CUT", 75.0)),
        b_cut=float(getattr(config, "GATE_TIER_B_CUT", 55.0)))
    return GateResult(
        ticker=ticker, strategy=strategy,
        as_of=str(df_daily.index[-1].date()),
        checks=tuple(checks), score=total, tier=tier,
        hard_blocks=hard_blocks,
        macro_stale=bool(macro_snap.get("stale")) if macro_snap else True)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_run.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/__init__.py tests/test_gate_run.py
git commit -m "feat: run_checklist orchestrator"
```

### Task G76: Hard-block policy wiring + `GATE_MODE` semantics

**Files:** Modify `swingbot/core/gate/registry.py`, `score.py`; test `tests/test_gate_run.py`

**Interfaces:** `decide(result: GateResult, mode: str, min_tier: str) -> str` — returns `"pass"` | `"downgrade"` | `"block"`: **shadow and inform modes always return `"pass"`** (the would-be enforce decision is recorded on the result as `advisory_decision` — inform mode renders it as information, e.g. "⛔ enforce would block this: 2 red flags"); only enforce mode may return `"downgrade"`/`"block"` (below `GATE_MIN_TIER` or on a hard block; downgrade = WEAK-style de-emphasis, cockpit rule 6, one tier above the block line).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_run.py`)

```python
import itertools
import random

from swingbot.core.gate.score import TIER_ORDER, decide, with_advisory
from swingbot.core.gate.types import GateResult


def _result(tier, hard_blocks=()):
    return GateResult(ticker="T", strategy="VWAP", as_of="2026-07-14",
                      checks=(), score=70.0, tier=tier,
                      hard_blocks=tuple(hard_blocks), macro_stale=False)


def test_shadow_and_inform_NEVER_block_property():
    rng = random.Random(42)
    for _ in range(200):
        tier = rng.choice(TIER_ORDER)
        hbs = ("signal_confirmed",) if rng.random() < 0.5 else ()
        for mode in ("shadow", "inform"):
            assert decide(_result(tier, hbs), mode, "A+") == "pass"


def test_enforce_matrix():
    for tier, min_tier in itertools.product(TIER_ORDER, TIER_ORDER):
        decision = decide(_result(tier), "enforce", min_tier)
        t, m = TIER_ORDER.index(tier), TIER_ORDER.index(min_tier)
        if t > m:
            assert decision == "block", (tier, min_tier)
        elif t == m and min_tier != "A+":
            assert decision == "downgrade", (tier, min_tier)
        else:
            assert decision == "pass", (tier, min_tier)
    # a hard block outranks any tier
    assert decide(_result("A+", ("signal_confirmed",)), "enforce", "C") == "block"


def test_advisory_always_populated():
    decision, result = with_advisory(_result("C"), "inform", "A")
    assert decision == "pass"                       # inform ships everything
    assert result.advisory_decision == "block"      # ...but says what enforce would do
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'decide'`)
- [ ] **Step 3: Write the implementation** (append to `swingbot/core/gate/score.py`)

```python
import dataclasses


def _enforce_verdict(result, min_tier: str) -> str:
    """What enforce WOULD do: hard block or below-min-tier -> block; the
    min tier itself -> WEAK-style downgrade (cockpit rule 6) unless the
    bar is already A+."""
    if result.hard_blocks:
        return "block"
    tier_rank = TIER_ORDER.index(result.tier)
    min_rank = TIER_ORDER.index(min_tier)
    if tier_rank > min_rank:
        return "block"
    if tier_rank == min_rank and min_tier != "A+":
        return "downgrade"
    return "pass"


def decide(result, mode: str, min_tier: str) -> str:
    """Shadow and inform ALWAYS return "pass" — only opt-in enforce may
    block or downgrade. The would-be verdict is exposed via with_advisory."""
    return _enforce_verdict(result, min_tier) if mode == "enforce" else "pass"


def with_advisory(result, mode: str, min_tier: str):
    """(decision, result) where result.advisory_decision carries the
    enforce verdict regardless of mode — inform renders it as information
    ("enforce would block this"), G123."""
    advisory = _enforce_verdict(result, min_tier)
    decision = advisory if mode == "enforce" else "pass"
    return decision, dataclasses.replace(result, advisory_decision=advisory)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_run.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/score.py tests/test_gate_run.py
git commit -m "feat: gate decision policy (shadow/inform/enforce)"
```

### Task G78: Weight & neutrality calibration over fixtures

> **Audit note (2026-07-29):** calibrate over the surviving checks only (see the G75 note). If a
> weight table in the body below lists a cut check, drop that row rather than reinstating the check.

> **Audit note (2026-07-28):** Before locking in weights here, resolve the G53 confluence-counter double-counting issue flagged in part 4 (`2026-07-14-gatekeeper-v7_4.md`) — 4 of its 6 factors re-score evidence already counted by G46/G49/G54/G55.

**Files:**
- Test: `tests/test_gate_calibration_fixtures.py`

- [ ] **Step 1: Write the test battery**

```python
# tests/test_gate_calibration_fixtures.py
"""ORDERING invariants over the golden scenarios — not absolute scores.
If these fail, adjust registry WEIGHTS (the free variable; detectors are
not) and record the final weights in the table comment below.

Weight table (initial):
  context: htf_alignment 12, level_map 8, atr_normal 6, vol_expansion 4
  setup:   signal_confirmed 10(HB), confluence 10, volume 8, momentum 6,
           divergence_against 6
  redflag: fake_breakout 10, dead_cat 10, news_whipsaw 10(HB), stop_sweep 8,
           divergence_trap 8, extreme_fade 8, rumor_spike 6, buy_rumor 6,
           beta_move 6, thin_session 6, opex_pin 4
  risk:    stop_structural 10, rr_realistic 10, size_formula 8, portfolio_room 6
  timing:  not_chasing 8, trigger_objective 6(HB), calendar_checked 4
"""
import datetime as dt

from swingbot.core.gate import run_checklist
from swingbot.core.gate.score import TIER_ORDER
from tests.fixtures.gate import (breakout_and_fail, dead_cat, downtrend_daily,
                                 range_daily, uptrend_daily)
from tests.fixtures.gate.plans import make_plan

EVENING = dt.datetime(2026, 7, 14, 23, 0, tzinfo=dt.timezone.utc)
QUIET_SNAP = {"built_at": "2026-07-14T22:00:00+00:00", "stale": False,
              "events": {"next_high_impact": None, "within_24h": [], "today": []}}


def _run(df, direction="bullish", strategy="Break & Retest", trigger=None):
    last = float(df["Close"].iloc[-1])
    trigger = trigger if trigger is not None else last
    stop = trigger * (0.95 if direction == "bullish" else 1.05)
    tp1 = trigger * (1.10 if direction == "bullish" else 0.90)
    plan = make_plan(strategy=strategy, direction=direction, created_at="2026-07-13",
                     trigger_price=trigger, entry_price=None,
                     stop_loss=stop, tp1=tp1, tp2=None)
    return run_checklist("TEST", strategy, plan, df,
                         macro_snap=QUIET_SNAP, now=EVENING)


def test_ordering_invariants():
    clean = _run(uptrend_daily())                                  # with-trend
    range_bounce = _run(range_daily(90, 110, n=300), trigger=110.0)
    counter = _run(downtrend_daily())                              # long into downtrend
    trap = _run(breakout_and_fail(level=100.0), trigger=100.0)
    dead = _run(dead_cat())
    assert clean.score > range_bounce.score > counter.score
    assert counter.score > min(trap.score, dead.score) or \
        counter.score >= max(trap.score, dead.score) - 5           # traps land at the bottom
    assert clean.score > trap.score and clean.score > dead.score


def test_red_flag_scenarios_capped_at_B():
    for result in (_run(breakout_and_fail(100.0), trigger=100.0), _run(dead_cat())):
        assert TIER_ORDER.index(result.tier) >= TIER_ORDER.index("B"), result.tier


def test_clean_setup_reaches_A():
    clean = _run(uptrend_daily())
    assert TIER_ORDER.index(clean.tier) <= TIER_ORDER.index("A"), \
        f"clean uptrend landed {clean.tier} ({clean.score}) — rebalance weights"
```

- [ ] **Step 2: Run — if orderings fail, adjust registry weights only, rerun until green**: `python -m pytest tests/test_gate_calibration_fixtures.py -v`
- [ ] **Step 3: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add tests/test_gate_calibration_fixtures.py swingbot/core/gate/
git commit -m "test: checklist ordering calibration over golden scenarios"
```

### Task G79: Tier-cut, threshold & strictness-preset config fields

**Files:** Modify `swingbot/config.py`, `swingbot/core/gate/registry.py`; test `tests/test_gate_config.py`

**Interfaces:**
- Fields `GATE_TIER_APLUS_CUT` (float, 90.0), `GATE_TIER_A_CUT` (75.0), `GATE_TIER_B_CUT` (55.0) + per-check `GATE_CHECK_*` checkboxes for every registered check id (generated from the registry — one loop, asserted complete by test), all in the Gatekeeper section.
- **Per-check threshold Fields**, generated from every `ThresholdSpec` in the registry (G5): key pattern `GATE_TH_{CHECK_ID}_{NAME}` (float/int, with the spec's min/max/step and the relax-direction sentence as help text). This is the "loosen it from the settings page" surface: every strict number in Phase G2 — volume multiples, ATR bands and percentile cuts, confluence minimum, chase distance, RR floor, wick ratios, bounce/gap percentages, blackout hours, RSI/ADX bounds — lives here, none are hardcoded. `spec.threshold(name)` resolves Field value → preset default.
- `apply_strictness_preset(level: str) -> dict[str, float]` — returns (and `config` setter applies) every threshold's `presets[level]` value; **relaxed** is deliberately generous (roughly: warn where balanced fails, pass where balanced warns) so a relaxed profile always lets plans through; **strict** is the A+-hunting profile. Changing `GATE_STRICTNESS` reseeds only thresholds the operator hasn't individually overridden (override tracking = value ≠ any preset value, noted in help text).
- [ ] **Step 1: Write the failing tests** (append to `tests/test_gate_config.py`)

```python
def test_tier_cut_fields_ordered():
    aplus, a, b = (field(k) for k in
                   ("GATE_TIER_APLUS_CUT", "GATE_TIER_A_CUT", "GATE_TIER_B_CUT"))
    assert aplus and a and b
    assert float(aplus.default) > float(a.default) > float(b.default)


def test_every_check_has_enable_field():
    import swingbot.core.gate  # noqa: F401 — triggers registration + field injection
    from swingbot.core.gate.registry import CHECKS
    keys = {f.key for f in config.FIELDS}
    for spec in CHECKS.values():
        assert spec.config_flag in keys, spec.check_id


def test_every_threshold_has_field_with_bounds():
    import swingbot.core.gate  # noqa: F401
    from swingbot.core.gate.registry import CHECKS
    by_key = {f.key: f for f in config.FIELDS}
    for spec in CHECKS.values():
        for th in spec.thresholds.values():
            key = f"GATE_TH_{spec.check_id.upper()}_{th.name.upper()}"
            f = by_key.get(key)
            assert f is not None, key
            assert f.min == th.min and f.max == th.max and f.step == th.step
            assert float(f.default) == th.presets["balanced"]


def test_preset_application_and_override_survival(monkeypatch):
    import swingbot.core.gate  # noqa: F401
    from swingbot.core.gate.registry import CHECKS, apply_strictness_preset
    seed = apply_strictness_preset("relaxed")
    assert seed, "no thresholds found"
    spec = CHECKS["rr_realistic"]
    key = "GATE_TH_RR_REALISTIC_MIN_RR"
    assert seed[key] == spec.thresholds["min_rr"].presets["relaxed"]
    # an individually-overridden threshold (value matching NO preset)
    # survives a preset switch
    monkeypatch.setattr(config, key, 1.37, raising=False)
    assert key not in apply_strictness_preset("strict")
```

- [ ] **Step 2: Run — FAIL**, then **implement**:

**(a) Tier-cut Fields** in `swingbot/config.py` (Gatekeeper section):

```python
    Field("GATE_TIER_APLUS_CUT", "GATE_TIER_APLUS_CUT", "Gatekeeper",
          "A+ tier score cut", type="float", default="90.0", min=50, max=100, step=1,
          help="Checklist score at or above this = tier A+. Fold evidence (G95/G102) "
               "proposes changes; edits are audited (G170)."),
    Field("GATE_TIER_A_CUT", "GATE_TIER_A_CUT", "Gatekeeper",
          "A tier score cut", type="float", default="75.0", min=40, max=100, step=1),
    Field("GATE_TIER_B_CUT", "GATE_TIER_B_CUT", "Gatekeeper",
          "B tier score cut", type="float", default="55.0", min=20, max=100, step=1),
```

**(b) Late-registration hook** in `swingbot/config.py` (after `_apply_env()` is defined):

```python
def register_fields(new_fields: list["Field"]) -> None:
    """Late registration for package-generated Fields (per-check enables,
    per-threshold values). Called by swingbot.core.gate at import time —
    config can't import the gate package itself (it's the other way
    around), so the gate pushes its Fields here. Idempotent by key."""
    known = {f.key for f in FIELDS}
    added = [f for f in new_fields if f.key not in known]
    if added:
        FIELDS.extend(added)
        _apply_env()
```

**(c) Field generation + presets** in `swingbot/core/gate/registry.py`:

```python
def config_fields() -> list:
    from swingbot.config import Field
    fields = []
    for spec in CHECKS.values():
        fields.append(Field(
            spec.config_flag, spec.config_flag, "Gatekeeper",
            f"Check: {spec.check_id}", type="checkbox", default="true",
            help=f"Disable to remove {spec.check_id} from the checklist "
                 f"(visible only with GATE_ENABLED)."))
        for th in spec.thresholds.values():
            key = f"GATE_TH_{spec.check_id.upper()}_{th.name.upper()}"
            fields.append(Field(
                key, key, "Gatekeeper", f"{spec.check_id}: {th.name}",
                type="float", default=str(th.presets["balanced"]),
                min=th.min, max=th.max, step=th.step,
                help=f"{th.relax_direction}. Presets — strict "
                     f"{th.presets['strict']}, balanced {th.presets['balanced']}, "
                     f"relaxed {th.presets['relaxed']}."))
    return fields


def apply_strictness_preset(level: str) -> dict[str, float]:
    """{field_key: preset value} for every threshold the operator has NOT
    individually overridden (override = current value matches no preset).
    The caller (settings machinery / G180) writes the returned values."""
    import swingbot.config as config
    out = {}
    for spec in CHECKS.values():
        for th in spec.thresholds.values():
            key = f"GATE_TH_{spec.check_id.upper()}_{th.name.upper()}"
            current = float(getattr(config, key, th.presets["balanced"]))
            if any(abs(current - v) < 1e-9 for v in th.presets.values()):
                out[key] = th.presets[level]
    return out
```

**(d) Push registration** at the bottom of `swingbot/core/gate/__init__.py` (after the check-module imports):

```python
from swingbot.core.gate.registry import config_fields  # noqa: E402

config.register_fields(config_fields())
```

**(e)** `GATE_STRICTNESS` changes are applied by the settings machinery calling `apply_strictness_preset` and persisting the returned values through the same path the settings page uses (wired on `/gate`, G180).

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_config.py tests/test_gate_registry.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/config.py swingbot/core/gate/registry.py swingbot/core/gate/__init__.py tests/test_gate_config.py
git commit -m "feat: tier cuts + registry-driven thresholds + strictness presets"
```

### Task G80: Per-strategy applicability matrix finalized

**Files:** Modify `registry.py`; test `tests/test_gate_registry.py`

- [ ] **Step 1: Enumerate the actual strategy names** — the live list is `swingbot/core/backtest.py:392` `ALL_STRATEGIES = ("EMA Crossover", "VWAP", "Fibonacci", "Support/Resistance", "RSI", "MACD", "Elliott Wave", "MA Ribbon", "Break & Retest", "RSI Divergence", "Volume Profile")` (re-read it at execution — do not trust this plan). Fill every CheckSpec's `applies_to` deliberately and document the matrix in the `registry.py` module docstring:

```python
# swingbot/core/gate/registry.py — extend the module docstring:
"""...
Applicability matrix (strategies from backtest.ALL_STRATEGIES):
  rf_fake_breakout    -> Break & Retest, Support/Resistance, Volume Profile
  rf_divergence_trap  -> RSI Divergence
  rf_extreme_fade     -> all (its own logic already relaxes weak-ADX fades,
                          which is what mean-reversion entries are)
  everything else     -> all strategies (applies_to=None)
"""
```

- [ ] **Step 2: Write the failing test** (append to `tests/test_gate_registry.py` — note: this test must NOT use the `_clean_registry` fixture; put it in a separate class or module scope without autouse, e.g. guard with `registry_module = importlib.import_module("swingbot.core.gate")` first):

```python
def test_applicability_matrix_uses_real_strategy_names():
    import swingbot.core.gate  # noqa: F401 — ensure all checks registered
    from swingbot.core.backtest import ALL_STRATEGIES
    from swingbot.core.gate import registry as live_registry
    for spec in live_registry.CHECKS.values():
        if spec.applies_to is not None:
            unknown = set(spec.applies_to) - set(ALL_STRATEGIES)
            assert not unknown, f"{spec.check_id}: unknown strategies {unknown}"
    assert set(live_registry.CHECKS["rf_fake_breakout"].applies_to) == {
        "Break & Retest", "Support/Resistance", "Volume Profile"}
    assert live_registry.CHECKS["rf_divergence_trap"].applies_to == ("RSI Divergence",)
    assert live_registry.CHECKS["rf_extreme_fade"].applies_to is None
    # every strategy gets a non-empty checklist
    for strategy in ALL_STRATEGIES:
        assert len(live_registry.enabled_checks(strategy)) >= 20, strategy
```

- [ ] **Step 3: Implement** — adjust any `applies_to` that the test exposes as stale (the values were set in G57/G60; this task is the deliberate sign-off), add the docstring table, PASS, then commit:

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/registry.py tests/test_gate_registry.py
git commit -m "feat: per-strategy check applicability"
```

### Task G81: Gate result persistence on plans

**Files:**
- Create: `swingbot/core/gate/persistence.py`
- Test: `tests/test_gate_persistence.py`

**Interfaces:** `attach_to_plan(plan_id, result: GateResult)` — stores `result.to_dict()` on the plan record via `plan_store` (new optional `gate` key — additive, old plans unaffected); `blocked_log(result, decision, reason)` → append `data/gate/blocked.jsonl`; `shadow_log(result)` → `data/gate/shadow.jsonl` (one line per evaluated candidate in shadow mode: score, tier, would-be decision, plan outcome joined later by G104).
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_persistence.py
import json

import pytest

import swingbot.core.gate.persistence as persistence
from swingbot.core.gate.persistence import attach_to_plan, blocked_log, shadow_log
from swingbot.core.gate.types import CheckResult, GateResult
from swingbot.core.plan_store import PlanStore
from tests.fixtures.gate.plans import make_plan


def _result(tier="B"):
    checks = (CheckResult("rf_fake_breakout", "redflag", "fail", 10.0, "trap", {}),)
    return GateResult(ticker="TEST", strategy="Break & Retest", as_of="2026-07-14",
                      checks=checks, score=48.0, tier=tier,
                      hard_blocks=(), macro_stale=False, advisory_decision="block")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "BLOCKED_PATH", str(tmp_path / "blocked.jsonl"))
    monkeypatch.setattr(persistence, "SHADOW_PATH", str(tmp_path / "shadow.jsonl"))
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(make_plan())
    return store


def test_attach_round_trip(env):
    assert attach_to_plan(env, "p_test_0001", _result()) is True
    stored = env.get_extra("p_test_0001", "gate")
    assert stored["tier"] == "B" and stored["checks"][0]["check_id"] == "rf_fake_breakout"
    assert env.get("p_test_0001") is not None          # legacy load path unbroken
    assert attach_to_plan(env, "p_missing", _result()) is False


def test_logs_append_valid_jsonl(env):
    blocked_log(_result("C"), "block", "rf_fake_breakout")
    shadow_log(_result(), plan_id="p_test_0001")
    for path in (persistence.BLOCKED_PATH, persistence.SHADOW_PATH):
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh]
        assert len(rows) == 1 and rows[0]["ticker"] == "TEST"
    with open(persistence.SHADOW_PATH, encoding="utf-8") as fh:
        row = json.loads(fh.readline())
    assert row["advisory_decision"] == "block"
    assert row["fired_flags"] == ["rf_fake_breakout"]
```

- [ ] **Step 2: Run — FAIL** (`ImportError`), then **implement**:

```python
# swingbot/core/gate/persistence.py
"""Attach gate results to plan records + blocked/shadow JSONL logs.
The shadow log is the evidence stream regardless of mode (G103)."""
from __future__ import annotations

import json
import os
import time

import swingbot.config as config
from swingbot.core.gate.types import GateResult

BLOCKED_PATH = os.path.join(config.DATA_DIR, "gate", "blocked.jsonl")
SHADOW_PATH = os.path.join(config.DATA_DIR, "gate", "shadow.jsonl")


def _append_jsonl(path: str, row: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def attach_to_plan(store, plan_id: str, result: GateResult) -> bool:
    """store = PlanStore (plan-engine-v2). Uses the additive set_extra hook
    added below — plan_from_dict must ignore unknown record keys (verify;
    if it doesn't, filter to dataclass fields there — one-line fix)."""
    return store.set_extra(plan_id, "gate", result.to_dict())


def blocked_log(result: GateResult, decision: str, reason: str) -> None:
    _append_jsonl(BLOCKED_PATH, {
        "ts": time.time(), "ticker": result.ticker, "strategy": result.strategy,
        "as_of": result.as_of, "tier": result.tier, "score": result.score,
        "decision": decision, "reason": reason,
        "hard_blocks": list(result.hard_blocks)})


def shadow_log(result: GateResult, plan_id: str | None = None) -> None:
    _append_jsonl(SHADOW_PATH, {
        "ts": time.time(), "plan_id": plan_id, "ticker": result.ticker,
        "strategy": result.strategy, "tier": result.tier, "score": result.score,
        "advisory_decision": result.advisory_decision,
        "fired_flags": [c.check_id for c in result.checks
                        if c.section == "redflag" and c.status == "fail"]})
```

**And the additive PlanStore hook** (`swingbot/core/plan_store.py`):

```python
    # PlanStore gains two methods — additive; old plans are unaffected:
    def set_extra(self, plan_id: str, key: str, value) -> bool:
        """Store an auxiliary key (e.g. 'gate', 'macro_at_entry',
        'gutcheck') on the raw record dict."""
        with _LOCK:
            record = self._plans.get(plan_id)
            if record is None:
                return False
            record[key] = value
            self._save()
            return True

    def get_extra(self, plan_id: str, key: str, default=None):
        record = self._plans.get(plan_id)
        return default if record is None else record.get(key, default)
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_persistence.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/persistence.py swingbot/core/plan_store.py tests/test_gate_persistence.py
git commit -m "feat: gate persistence (plan attach + blocked/shadow logs)"
```

### Task G87: Performance guard

**Files:**
- Test: `tests/test_gate_perf.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_gate_perf.py
import datetime as dt
import statistics
import time

import pytest

from swingbot.core.gate import run_checklist
from tests.fixtures.gate import uptrend_daily
from tests.fixtures.gate.plans import make_plan

EVENING = dt.datetime(2026, 7, 14, 23, 0, tzinfo=dt.timezone.utc)
QUIET_SNAP = {"built_at": "2026-07-14T22:00:00+00:00", "stale": False,
              "events": {"next_high_impact": None, "within_24h": [], "today": []}}


@pytest.mark.perf   # match the repo's existing perf marker name — verify at execution
def test_run_checklist_median_under_50ms():
    df = uptrend_daily(n=500)
    plan = make_plan(created_at="2026-07-13",
                     trigger_price=float(df["Close"].iloc[-1]))
    run_checklist("TEST", plan.strategy, plan, df,
                  macro_snap=QUIET_SNAP, now=EVENING)          # warm-up
    times = []
    for _ in range(20):
        t0 = time.perf_counter()
        run_checklist("TEST", plan.strategy, plan, df,
                      macro_snap=QUIET_SNAP, now=EVENING)
        times.append(time.perf_counter() - t0)
    median = statistics.median(times)
    # 50 ms pure-compute budget/ticker -> a 60-ticker scan adds < 3 s.
    assert median < 0.050, f"median {median * 1000:.1f} ms — cache the swing_levels/" \
                           f"htf_trend calls per frame (they run in 4+ checks)"
```

- [ ] **Step 2: Run — if over budget, memoize per-frame** (the expected fix: several checks recompute `swing_levels`/`htf_trend`/`atr` on the same frame — add a tiny `functools.lru_cache` keyed on `id(df)`-safe wrapper or compute-once context passed via `ctx` from `run_checklist`), then PASS.
- [ ] **Step 3: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add tests/test_gate_perf.py swingbot/core/gate/
git commit -m "test: gate evaluation perf budget"
```

### Task G88: Phase G2 checkpoint

- [ ] **Step 1:** Full suite + `make check` green. Registry invariant test passes with **all** checks registered (context 3, setup 5, red flags 11, risk 4, timing 3 = 26 checks). (count reduced from 27 to 26: G51 `check_vol_expansion_direction` was cut in the 2026-07-28 win-rate audit)
- [ ] **Step 2:** Update Progress block. Commit — `chore: phase G2 checkpoint (26 checks live)`

---
