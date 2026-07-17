# Gatekeeper v6 - Part 4/11: Checklist engine I: HTF context & setup quality (sections 1-2) (Tasks G45-G56)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute strictly in order (G45 -> G56).
>
> **Split note:** this is part 4 of 11, extracted verbatim from the master plan `2026-07-14-gatekeeper-v6.md` (which stays as the reference copy; the checklist-to-task traceability appendix is in Part 11). Parts execute in numeric order.
> **Requires complete first:** Parts 1-3 complete (all their tasks checked off).
>
> Cross-part references (task numbers like G38, file names, `Interfaces:` blocks) refer to work done in earlier parts - those modules exist on the branch by the time this part runs.

## Progress

> Updated by the executing session after each task batch. Resume from the first unchecked task.
>
> - **Branch:** `feature/gatekeeper-v6`
> - **Completed:** —
> - **Next:** Task G45

**Goal:** Push per-strategy win rate toward the 95% final target the honest way — by turning the operator's Pre-Trade Entry Checklist into an automated, fold-validated **advisor** (higher-timeframe context, setup quality, 11 red-flag detectors, risk definition, timing, gut-check ritual) that annotates every trade plan, and by refreshing a full macro context snapshot (news, sentiment, sector rotation, CPI, PPI, PCE, treasury curve, inflation expectations, VIX, breadth, credit) before every scan — with new Discord surfaces and admin pages to drive it.

**Inform-first principle (operator decision, 2026-07-14 — binds every task):** the checklist is information, not a gateway. **Every trade plan is created and alerted regardless of its checklist verdict**; negative signals are marked loudly in the Discord message (tier, score, red-flag table) and the human decides. Blocking (`enforce` mode) exists as a strictly opt-in rung the operator may climb *after* the evidence phase proves specific cuts — it is never the default, and plan completion does not depend on it. Every strict threshold is a settings-page field with documented relax direction plus one-click strictness presets, so the checklist can always be loosened without code changes — a checklist that silences all trades is a misconfiguration, not a feature.

**Architecture:** Two new packages — `swingbot/core/macro/` (data providers, caches, econ calendar, sentiment, composite risk score, pre-scan snapshot) and `swingbot/core/gate/` (one module per checklist check, red-flag detectors, scoring, hard-block/soft-flag policy, tier ladder) — wired into the scan pipeline behind default-off flags, validated through the walk-forward fold discipline established in edge-engine-v4, surfaced in Discord embeds/commands and new admin pages. Mode ladder: `shadow` (log only, invisible) → `inform` (**the default destination**: full checklist rendered on every alert, nothing ever blocked) → `enforce` (optional, opt-in, evidence-gated).

**Tech Stack:** Python 3.11+, pandas, numpy, requests (already a dependency), mplfinance/matplotlib, Flask + Jinja2 + Chart.js (vendored, per cockpit-v3), pytest ≥8. Data: FRED REST API (free key), U.S. Treasury FiscalData, Finnhub (key already a config Field from llm-advisor L10), yfinance daily bars via the existing fetch/cache layer. **No new pip dependencies.**

## The 95% goal, stated honestly (read before Task G1)

This plan exists because the operator wants ~95% win rate on every strategy. The series' own honesty rules (edge-engine-v4 header; llm-advisor honesty contract) bind this plan too, so the goal is encoded the only defensible way:

- **95% portfolio-wide cannot be promised, only earned and measured.** Win rate is trivially inflated by shrinking targets and widening stops — that destroys expectancy and the account with it. Every WR gain in this plan must come from *not taking bad trades* (filtering), never from degrading the exit geometry validated in plan-engine-v2.
- **The target is a ladder, not a number.** The checklist score partitions signals into tiers. Pre-registered targets (Task G2, frozen before any data contact): **A+ tier** (every box checked, zero red flags) targets **≥ 90% pooled fold WR** with N ≥ 30 per fold and expectancy_r ≥ the strategy's unfiltered baseline; if the folds show ≥ 95% at that sample size, the tier is *labeled* 95-class — measured, never assumed. **All-strategies aggregate** targets **+3 to +8 WR points vs. the v2 baseline** at ≤ 40% signal loss.
- **WR is reported next to expectancy and N, always.** Any surface this plan builds that shows a win rate without its sample size and expectancy is a bug (same rule as cockpit-v3).
- **The 2024–2025 validation window stays burned.** All tuning here runs on TRAIN folds (2018–2023, anchored, per edge-engine E39 rules). The single pre-registered validation shot belongs to edge-engine E92; this plan feeds it, never spends it.
- **The path to 95% runs through the operator, not through suppression.** In inform mode the bot's raw WR doesn't change — what changes is that every alert carries its tier and its red flags, so the operator can choose to act only on A+/A setups. The tier ladder measures what following the checklist *would have* earned (`!tierwr`, shadow reports); the human applies it. Enforcement is available later if the operator wants the bot to apply it mechanically.

## Prerequisites

- **Required merged:** unified-plan-engine-v2 (TradePlanV2, exit simulator, plan_store/plan_manager, registry) and cockpit-v3 **Part 1** (`swingbot/core/jsonio.py`, `swingbot/core/analytics/` — journal, snapshots, rank).
- **Reused when present, degraded when absent (every integration point wrapped in a capability check, noted per task):** edge-engine-v4 `backtest_wf.py` walk-forward engine (G96 ships a minimal fallback fold runner), E47 kill switch, E7 portfolio heat; llm-advisor v5 (`swingbot/core/advisor/`) for G132–G133.
- Cached daily OHLCV 2018-06→present via `scripts/fetch_backtest_data.py`; DataFrame convention `Open,High,Low,Close,Volume`, DatetimeIndex.

## Global Constraints

- **Optimization target for every tuned threshold:** maximize WR **subject to** pooled fold expectancy_r ≥ baseline − 0.02R and N ≥ 30 per fold. WR alone never picks a parameter.
- **Pre-registered fold gate (identical to edge-engine):** anchored expanding folds, train 2018→fold-start, test years 2021/2022/2023; a check/threshold is promoted only if it improves the target in ≥ 2 of 3 folds and no fold degrades expectancy by > 0.05R. Failures are documented in `docs/superpowers/results/` and dropped — no second grid on the same hypothesis.
- **Inform-first, always.** The checklist never prevents a plan from being created or alerted unless the operator has explicitly opted into `enforce` mode. Negative signals are rendered on the alert; the human decides. Any task that drops/holds/blocks anything applies **only** in enforce mode (or behind its own dedicated opt-in flag) — every such task carries an inform-mode regression test proving the alert still ships annotated.
- **Every strict constraint is tunable from the settings page.** Each check's thresholds are config Fields (registry-driven, G79) with min/max/step and a help text naming the relax direction; `GATE_STRICTNESS` presets (strict/balanced/relaxed) reseed them in one click. Defaults ship at **balanced**, chosen so the G97 baseline census shows a healthy tier mix — never a wall of C.
- **Every new flag is a config Field, default off** (master switches; per-check toggles default on but do nothing user-visible until `MACRO_ENABLED`/`GATE_ENABLED`). Nothing is suppressed silently in any mode: annotated/held/blocked candidates are always visible somewhere (`!blocked`, admin log, retrospective line).
- **No network in the test suite.** All providers are tested via monkeypatched `requests`/stub clients and fixture payloads; real calls live only in `scripts/*_smoke*.py` and backfill scripts.
- **Provider failure never degrades scanning.** Every fetch has a timeout (default 5s), on-disk TTL cache fallback, and a "stale/unknown" degradation path; a scan with zero working data providers must still complete (G43 is the proof).
- **API keys are config Fields (sensitive), never logged, never committed.** Free-tier quotas are budgeted and metered (G200).
- **Validation-window hygiene:** nothing in this plan reads 2024–2025 bars for tuning; `assert_train_only` (cockpit C31 pattern) guards every tuning entry point.
- **One definition per stat** (cockpit rule): WR/expectancy_r come from `analytics.metrics`; the gate never re-derives them.
- **Timezone:** all calendars/sessions use US/Eastern for market events, Europe/Berlin for user-facing day buckets (matches `performance.get_detailed_stats`).
- **Every task ends green:** `python -m pytest tests/ -q` + `make check` before commit; conventional commits; run from repo root `E:\Documents\Private\Projects\Discord-Bot`. (Windows note: if `make`/`python3` unavailable, run the `python -m py_compile` loop per cockpit A31 note.)

## File Structure (target state)

```
swingbot/core/macro/
  __init__.py        public API re-exports
  httpcache.py       fetch_json() with TTL disk cache under data/macro/cache/
  health.py          provider health ledger + quota meter
  fred.py            FRED series client + release-dates client
  series.py          named macro series registry (CPI, PPI, PCE, yields, ...)
  vix.py             VIX level + term structure from cached bars
  credit.py          HYG/LQD credit-stress ratio
  sectors.py         11 SPDR sector ETFs: data, RS ranks, rotation table
  breadth.py         % of universe above 50/200 DMA
  composite.py       risk-on/off composite + fear-greed-style gauge
  calendar_events.py econ event calendar (historical static + future fetch)
  opex.py            options-expiry / quad-witching calendar
  sessions.py        market holidays, half-days, low-liquidity windows
  earnings.py        earnings calendar (wraps advisor market_context if merged)
  history.py         publication-lag-aware historical macro frame
  quality.py         snapshot sanity validator
  news.py            Finnhub market/company headlines
  sentiment.py       lexicon headline scorer + rumor/confirmed classifier
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
  redflags.py        the 11 red-flag detectors (one function each)
  risk_def.py        structural stop, size-formula check, realistic RR
  timing.py          chasing check, trigger objectivity, session calendar
  wr_math.py         win-rate/expectancy identities + frontier math
  persistence.py     attach results to plans, journal tags, blocked log
  render.py          embed field / red-flag table / macro-line string builders
  gutcheck.py        gut-check ritual state (buttons + why-wrong journal)
  backtest_ctx.py    historical macro snapshots (no lookahead)
  frontier.py        WR-by-decile, frontier, tier-cut proposals
  folds.py           fold runner (delegates to edge E39 when present)
  telemetry.py       evaluated/blocked/held counters
swingbot/core/charts/
  gate_charts.py     frontier/decile/ablation/macro-dashboard/rotation charts
swingbot/core/
  backtest.py            MOD checklist evaluation per simulated signal
  scan_engine / scanning/*  MOD pre-scan snapshot, gates, embed fields
swingbot/commands/
  macro.py           NEW !macro !calendar !sectors !sentiment !yields !inflation
  gatecheck.py       NEW !checklist !whycheck !blocked !gutcheck !frontier !tierwr !redflags
swingbot/admin/      MOD /api/macro/*, /api/gate/*, macro dashboard, calendar,
                     checklist config, red-flag analytics, frontier pages
scripts/
  backfill_macro.py, macro_smoke.py, gate_fold_run.py, gate_frontier.py,
  gate_shadow_report.py, build_event_history.py
tests/ test_macro_*.py, test_gate_*.py, tests/admin/test_macro_api.py, ...
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

### Task G51: Check `vol_expansion_direction` (weight 4, info-grade)

**Files:** Modify `atr_regime.py`, `registry.py`; test `tests/test_gate_atr.py`

**Interfaces:** `check_vol_expansion(df_daily, plan, macro_snap) -> CheckResult` — when ATR is rising (5d slope > 0), is expansion happening on with-plan bars or against-plan bars (sum of true range on up-close vs down-close days, last 10)? Against-plan expansion → warn. Never fails — weight-4 nuance.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_atr.py`)

```python
from swingbot.core.gate.atr_regime import check_vol_expansion


def _expansion_path(down_big: bool, n=200):
    """Flat lead-in, then 12 alternating bars where either the down or the
    up bars carry the big true ranges (growing, so ATR slope > 0)."""
    closes = [100.0] * n
    mag = 0.02
    for i in range(12):
        mag *= 1.12
        if down_big:
            move = -mag if i % 2 == 0 else 0.004
        else:
            move = mag if i % 2 == 0 else -0.004
        closes.append(closes[-1] * (1 + move))
    return make_ohlcv(np.asarray(closes), spread_pct=0.2)


def test_against_plan_expansion_warns():
    result = check_vol_expansion(_expansion_path(down_big=True),
                                 make_plan(direction="bullish"), None)
    assert result.status == "warn"
    assert result.evidence["tr_against"] > result.evidence["tr_with"]


def test_with_plan_expansion_passes():
    assert check_vol_expansion(_expansion_path(down_big=False),
                               make_plan(direction="bullish"), None).status == "pass"


def test_no_expansion_passes():
    flat = make_ohlcv(np.full(200, 100.0), spread_pct=1.0)
    assert check_vol_expansion(flat, make_plan(), None).status == "pass"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'check_vol_expansion'`)
- [ ] **Step 3: Write the implementation** (append to `atr_regime.py`)

```python
def check_vol_expansion(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """Info-grade: when ATR is rising, is the expansion on with-plan or
    against-plan bars (true-range sums, last 10)? Never fails."""
    series = atr(df_daily).dropna()
    if len(series) < 20:
        return CheckResult("vol_expansion_direction", "context", "unknown", 4.0,
                           "insufficient history", {})
    slope5 = float(series.iloc[-1] - series.iloc[-6])
    if slope5 <= 0:
        return CheckResult("vol_expansion_direction", "context", "pass", 4.0,
                           "ATR not expanding", {"atr_slope5": round(slope5, 4)})
    tail = df_daily.iloc[-10:]
    prev_close = tail["Close"].shift(1)
    true_range = pd.concat([tail["High"] - tail["Low"],
                            (tail["High"] - prev_close).abs(),
                            (prev_close - tail["Low"]).abs()], axis=1).max(axis=1)
    up_bars = tail["Close"] >= tail["Open"]
    with_plan = up_bars if plan.direction == "bullish" else ~up_bars
    tr_with = round(float(true_range[with_plan].sum()), 2)
    tr_against = round(float(true_range[~with_plan].sum()), 2)
    evidence = {"atr_slope5": round(slope5, 4),
                "tr_with": tr_with, "tr_against": tr_against}
    if tr_against > tr_with:
        return CheckResult("vol_expansion_direction", "context", "warn", 4.0,
                           "ATR expanding on against-plan bars", evidence)
    return CheckResult("vol_expansion_direction", "context", "pass", 4.0,
                       "expansion happening with-plan", evidence)


register(check_id="vol_expansion_direction", section="context", weight=4.0,
         func=check_vol_expansion)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_atr.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/atr_regime.py tests/test_gate_atr.py
git commit -m "feat: vol expansion direction check"
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
