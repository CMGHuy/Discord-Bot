# Gatekeeper v6 - Part 5/11: Checklist engine II: the 11 red flags (section 3) (Tasks G57-G67)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute strictly in order (G57 -> G67).
>
> **Split note:** this is part 5 of 11, extracted verbatim from the master plan `2026-07-14-gatekeeper-v6.md` (which stays as the reference copy; the checklist-to-task traceability appendix is in Part 11). Parts execute in numeric order.
> **Requires complete first:** Parts 1-4 complete (all their tasks checked off).
>
> Cross-part references (task numbers like G38, file names, `Interfaces:` blocks) refer to work done in earlier parts - those modules exist on the branch by the time this part runs.

## Progress

> Updated by the executing session after each task batch. Resume from the first unchecked task.
>
> - **Branch:** `feature/gatekeeper-v6`
> - **Completed:** —
> - **Next:** Task G57

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


> *(Phase intro above repeated from the part where this phase begins - this part continues it with tasks G57-G67.)*

## Section 3 — The 11 red flags (checklist §3, one task each)

Red-flag checks live in `swingbot/core/gate/redflags.py`, ids prefixed `rf_`, section `"redflag"`. Policy: a red flag that fires = `fail`; flags marked **HB** are hard blocks. Each returns evidence sufficient for the embed's red-flag table row.

### Task G57: `rf_fake_breakout` (weight 10)

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

### Task G63: `rf_rumor_spike` (weight 6)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_rumor_spike(df_daily, plan, macro_snap, headlines=None) -> CheckResult` — fires when the signal bar gapped ≥ 5% or ranged ≥ 2.5× ATR on ≥ 3× volume **and** the ticker's recent headlines (G35, injected by the orchestrator) are majority `"rumor"`-classified (G37) or absent entirely (unexplained spike). Confirmed-news spike → warn (still event-driven). No headlines provider → `unknown` on the news half, decided by geometry half alone (warn max).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_redflags.py`)

```python
from swingbot.core.gate.redflags import rf_rumor_spike
from tests.fixtures.gate import gap_spike

RUMOR_HEADS = [{"title": "TEST reportedly in talks over mega-merger"},
               {"title": "Sources say TEST weighing acquisition"}]
CONFIRMED_HEADS = [{"title": "TEST announces record Q2 earnings"},
                   {"title": "TEST files 8-K on new contract"}]


def test_rumor_spike_fires():
    result = rf_rumor_spike(gap_spike(pct=12.0), make_plan(), None,
                            headlines=RUMOR_HEADS)
    assert result.status == "fail"


def test_no_headlines_at_all_is_unexplained_fail():
    assert rf_rumor_spike(gap_spike(12.0), make_plan(), None,
                          headlines=[]).status == "fail"


def test_confirmed_news_spike_warns():
    assert rf_rumor_spike(gap_spike(12.0), make_plan(), None,
                          headlines=CONFIRMED_HEADS).status == "warn"


def test_no_provider_geometry_only_warn():
    assert rf_rumor_spike(gap_spike(12.0), make_plan(), None,
                          headlines=None).status == "warn"


def test_quiet_tape_passes():
    assert rf_rumor_spike(uptrend_daily(), make_plan(), None,
                          headlines=RUMOR_HEADS).status == "pass"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'rf_rumor_spike'`)
- [ ] **Step 3: Write the implementation** (append to `redflags.py`)

```python
def rf_rumor_spike(df_daily, plan, macro_snap, *, headlines=None, **ctx) -> CheckResult:
    """Spike geometry + rumor-classified (or absent) headlines.
    headlines is injected by the orchestrator (G75) from company news
    (G35); None = provider unavailable -> geometry half only, warn max."""
    spec = CHECKS["rf_rumor_spike"]
    from swingbot.core.gate.levels import _safe_atr
    from swingbot.core.macro.sentiment import classify_confirmation
    closes = df_daily["Close"]
    if len(closes) < 30:
        return _rf("rf_rumor_spike", "unknown", "insufficient history", {}, 6.0)
    prev = float(closes.iloc[-2])
    bar = df_daily.iloc[-1]
    move_pct = abs(float(bar["Close"]) / prev - 1.0) * 100.0
    atr_val = _safe_atr(df_daily.iloc[:-1], prev)
    range_atr = (float(bar["High"]) - float(bar["Low"])) / atr_val
    vol = volume_ratio(df_daily) or 0.0
    spiky = ((move_pct >= spec.threshold("gap_pct")
              or range_atr >= spec.threshold("range_atr"))
             and vol >= spec.threshold("vol_mult"))
    evidence = {"move_pct": round(move_pct, 1), "range_atr": round(range_atr, 1),
                "vol_ratio": round(vol, 1)}
    if not spiky:
        return _rf("rf_rumor_spike", "pass", "no spike geometry", evidence, 6.0)
    if headlines is None:
        return _rf("rf_rumor_spike", "warn",
                   f"spike ({move_pct:.0f}%, {vol:.0f}x vol) — headlines "
                   f"provider unavailable", evidence, 6.0)
    labels = [classify_confirmation(h.get("title", "")) for h in headlines]
    evidence["headline_labels"] = labels
    if not labels or labels.count("rumor") > len(labels) / 2:
        why = "majority rumor-classified headlines" if labels else "no headlines at all"
        return _rf("rf_rumor_spike", "fail",
                   f"spike on {why} — unexplained/rumor-driven", evidence, 6.0)
    return _rf("rf_rumor_spike", "warn",
               "event-driven spike (confirmed news) — still volatile tape",
               evidence, 6.0)


register(check_id="rf_rumor_spike", section="redflag", weight=6.0,
         func=rf_rumor_spike, backtestable=False,   # news half is live-only (G89)
         thresholds={
             "gap_pct": ThresholdSpec("gap_pct", 5.0, 2.0, 15.0, 0.5,
                 "raise to flag only bigger one-day moves",
                 presets={"strict": 4.0, "balanced": 5.0, "relaxed": 8.0}),
             "range_atr": ThresholdSpec("range_atr", 2.5, 1.5, 5.0, 0.25,
                 "raise to flag only wider ranges",
                 presets={"strict": 2.0, "balanced": 2.5, "relaxed": 3.5}),
             "vol_mult": ThresholdSpec("vol_mult", 3.0, 1.5, 6.0, 0.25,
                 "raise to require heavier volume before flagging",
                 presets={"strict": 2.5, "balanced": 3.0, "relaxed": 4.0}),
         })
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_redflags.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/redflags.py tests/test_gate_redflags.py
git commit -m "feat: rf_rumor_spike"
```

### Task G64: `rf_buy_rumor_sell_fact` (weight 6)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_buy_rumor_sell_fact(df_daily, plan, macro_snap) -> CheckResult` — fires for with-move entries within 2 sessions **after** a scheduled importance-3 event or the ticker's earnings date when the pre-event 5-day run-up exceeded 1.5× ATR-normalized average (the move was priced in; entering now buys the fact). Evidence: event, run-up multiple.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_redflags.py`)

```python
from swingbot.core.gate.redflags import rf_buy_rumor_sell_fact


def _runup_df():
    closes = np.concatenate([np.full(100, 100.0),
                             np.linspace(100, 112, 6)[1:]])   # hard 5-day run-up
    return make_ohlcv(closes, spread_pct=1.0)


FOMC_YESTERDAY = [{"date": "2026-07-13", "time_et": "14:00", "kind": "fomc",
                   "label": "FOMC decision", "importance": 3}]
NOW = dt.datetime(2026, 7, 14, 16, 0, tzinfo=dt.timezone.utc)


def test_post_fomc_chase_fires():
    result = rf_buy_rumor_sell_fact(_runup_df(), make_plan(direction="bullish"),
                                    None, now=NOW, recent_events=FOMC_YESTERDAY)
    assert result.status == "fail"
    assert result.evidence["runup_atr"] > 0


def test_no_event_passes():
    assert rf_buy_rumor_sell_fact(_runup_df(), make_plan(), None,
                                  now=NOW, recent_events=[]).status == "pass"


def test_event_without_runup_passes():
    flat = make_ohlcv(np.full(105, 100.0), spread_pct=1.0)
    assert rf_buy_rumor_sell_fact(flat, make_plan(), None,
                                  now=NOW, recent_events=FOMC_YESTERDAY).status == "pass"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'rf_buy_rumor_sell_fact'`)
- [ ] **Step 3: Write the implementation** (append to `redflags.py`)

```python
def rf_buy_rumor_sell_fact(df_daily, plan, macro_snap, *, now=None,
                           recent_events=None, **ctx) -> CheckResult:
    """With-move entry within 2 sessions AFTER a high-impact event when the
    pre-event run-up was already outsized — the move is priced in."""
    spec = CHECKS["rf_buy_rumor_sell_fact"]
    from swingbot.core.gate.levels import _safe_atr
    now_date = (now or dt.datetime.now(dt.timezone.utc)).date()
    if recent_events is None:
        start = (now_date - dt.timedelta(days=4)).isoformat()
        recent_events = calendar_events.events_between(start, now_date.isoformat())
    high_impact = [e for e in recent_events if e.get("importance", 0) >= 3]
    if not high_impact:
        return _rf("rf_buy_rumor_sell_fact", "pass",
                   "no recent high-impact event", {}, 6.0)
    closes = df_daily["Close"]
    if len(closes) < 30:
        return _rf("rf_buy_rumor_sell_fact", "unknown", "insufficient history", {}, 6.0)
    atr_val = _safe_atr(df_daily, float(closes.iloc[-1]))
    runup_atr = (float(closes.iloc[-1]) - float(closes.iloc[-6])) / atr_val
    with_move = runup_atr > 0 if plan.direction == "bullish" else runup_atr < 0
    evidence = {"event": high_impact[-1]["label"],
                "runup_atr": round(runup_atr, 2)}
    if with_move and abs(runup_atr) >= spec.threshold("runup_atr"):
        return _rf("rf_buy_rumor_sell_fact", "fail",
                   f"entering WITH a {abs(runup_atr):.1f}-ATR run-up right after "
                   f"{high_impact[-1]['label']} — buying the fact", evidence, 6.0)
    return _rf("rf_buy_rumor_sell_fact", "pass",
               "no priced-in run-up signature", evidence, 6.0)


register(check_id="rf_buy_rumor_sell_fact", section="redflag", weight=6.0,
         func=rf_buy_rumor_sell_fact,
         thresholds={
             "runup_atr": ThresholdSpec("runup_atr", 3.0, 1.0, 6.0, 0.25,
                 "raise to flag only more extreme pre-event run-ups",
                 presets={"strict": 2.5, "balanced": 3.0, "relaxed": 4.0}),
         })
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_redflags.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/redflags.py tests/test_gate_redflags.py
git commit -m "feat: rf_buy_rumor_sell_fact"
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

### Task G66: `rf_opex_pin` (weight 4)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_opex_pin(df_daily, plan, macro_snap, now=None) -> CheckResult` — warn when today or tomorrow `is_opex` (G31), escalating detail on quad-witching; pass otherwise. Warn-grade only.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_redflags.py`)

```python
from swingbot.core.gate.redflags import rf_opex_pin


def test_quad_witching_warns():
    qw_friday = dt.datetime(2026, 3, 20, 15, 0, tzinfo=dt.timezone.utc)
    result = rf_opex_pin(_liquid_df(), make_plan(), None, now=qw_friday)
    assert result.status == "warn" and "quad-witching" in result.detail
    day_before = dt.datetime(2026, 3, 19, 15, 0, tzinfo=dt.timezone.utc)
    assert rf_opex_pin(_liquid_df(), make_plan(), None, now=day_before).status == "warn"


def test_normal_day_passes():
    normal = dt.datetime(2026, 7, 14, 15, 0, tzinfo=dt.timezone.utc)
    assert rf_opex_pin(_liquid_df(), make_plan(), None, now=normal).status == "pass"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'rf_opex_pin'`)
- [ ] **Step 3: Write the implementation** (append to `redflags.py`)

```python
def rf_opex_pin(df_daily, plan, macro_snap, *, now=None, **ctx) -> CheckResult:
    """warn-grade only: opex/quad-witching pin risk today or tomorrow."""
    from swingbot.core.macro.opex import is_opex, is_quad_witching
    today = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ET).date()
    for offset, when in ((0, "today"), (1, "tomorrow")):
        date = (today + dt.timedelta(days=offset)).isoformat()
        if is_opex(date):
            label = "quad-witching" if is_quad_witching(date) else "monthly opex"
            return _rf("rf_opex_pin", "warn",
                       f"{label} {when} — pin/unwind risk around strikes",
                       {"date": date, "quad": is_quad_witching(date)}, 4.0)
    return _rf("rf_opex_pin", "pass", "no expiry nearby", {}, 4.0)


register(check_id="rf_opex_pin", section="redflag", weight=4.0, func=rf_opex_pin,
         trigger_recheck=True)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_redflags.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/redflags.py tests/test_gate_redflags.py
git commit -m "feat: rf_opex_pin"
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

## Section 4 — Risk definition (decided BEFORE entry)
