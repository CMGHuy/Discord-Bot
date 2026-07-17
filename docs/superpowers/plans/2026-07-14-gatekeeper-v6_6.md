# Gatekeeper v6 - Part 6/11: Checklist engine III: risk, timing & assembly (sections 4-5) (Tasks G68-G88)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute strictly in order (G68 -> G88).
>
> **Split note:** this is part 6 of 11, extracted verbatim from the master plan `2026-07-14-gatekeeper-v6.md` (which stays as the reference copy; the checklist-to-task traceability appendix is in Part 11). Parts execute in numeric order.
> **Requires complete first:** Parts 1-5 complete (all their tasks checked off).
>
> Cross-part references (task numbers like G38, file names, `Interfaces:` blocks) refer to work done in earlier parts - those modules exist on the branch by the time this part runs.

## Progress

> Updated by the executing session after each task batch. Resume from the first unchecked task.
>
> - **Branch:** `feature/gatekeeper-v6`
> - **Completed:** —
> - **Next:** Task G68

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


> *(Phase intro above repeated from the part where this phase begins - this part continues it with tasks G68-G88.)*

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

### Task G69: Check `size_formula` (weight 8, §4 "size from account risk ÷ stop distance")

**Files:** Modify `risk_def.py`, `registry.py`; test `tests/test_gate_risk.py`

**Interfaces:** `check_size_formula(df_daily, plan, macro_snap, account=None) -> CheckResult` — recomputes size from `account.compute_position_size` semantics (risk % ÷ stop distance) and compares to the plan's stated size: pass within 5%, warn within 20%, fail beyond (conviction-sized). When edge-engine sizing modes (E4–E6) are live, pass-through their output as the reference. Evidence: expected vs actual shares.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_risk.py`)

```python
from swingbot.core.gate.risk_def import check_size_formula
from tests.fixtures.gate import uptrend_daily


class _StubAccount:
    def compute_position_size(self, entry, stop):   # verify real signature at execution
        return 100.0


def test_exact_size_passes():
    plan = make_plan()
    result = check_size_formula(uptrend_daily(), plan, None,
                                account=_StubAccount(), stated_size=101.0)
    assert result.status == "pass"


def test_conviction_double_size_fails():
    result = check_size_formula(uptrend_daily(), make_plan(), None,
                                account=_StubAccount(), stated_size=210.0)
    assert result.status == "fail" and "conviction" in result.detail


def test_no_account_is_unknown():
    assert check_size_formula(uptrend_daily(), make_plan(), None).status == "unknown"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'check_size_formula'`)
- [ ] **Step 3: Write the implementation** (append to `risk_def.py`)

```python
def check_size_formula(df_daily, plan, macro_snap, *, account=None,
                       stated_size=None, **ctx) -> CheckResult:
    """Recompute size from risk%/stop-distance semantics and compare to the
    stated size. When edge-engine sizing modes (E4-E6) are live, their
    output becomes the reference (pass-through, verify at execution)."""
    spec = CHECKS["size_formula"]
    if account is None or stated_size is None:
        return CheckResult("size_formula", "risk", "unknown", 8.0,
                           "no account / stated size to verify", {})
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    if abs(entry - plan.stop_loss) <= 0:
        return CheckResult("size_formula", "risk", "fail", 8.0,
                           "zero stop distance — size formula undefined", {})
    expected = account.compute_position_size(entry, plan.stop_loss)
    if not expected:
        return CheckResult("size_formula", "risk", "unknown", 8.0,
                           "sizing reference unavailable", {})
    deviation = abs(stated_size - expected) / expected
    evidence = {"expected": round(expected, 1), "stated": stated_size,
                "deviation": round(deviation, 3)}
    if deviation <= spec.threshold("pass_dev"):
        return CheckResult("size_formula", "risk", "pass", 8.0,
                           "size matches the risk formula", evidence)
    if deviation <= spec.threshold("warn_dev"):
        return CheckResult("size_formula", "risk", "warn", 8.0,
                           f"size off formula by {deviation * 100:.0f}%", evidence)
    return CheckResult("size_formula", "risk", "fail", 8.0,
                       f"conviction-sized: {deviation * 100:.0f}% off the formula",
                       evidence)


register(check_id="size_formula", section="risk", weight=8.0,
         func=check_size_formula, backtestable=False,
         thresholds={
             "pass_dev": ThresholdSpec("pass_dev", 0.05, 0.01, 0.25, 0.01,
                 "raise to tolerate rougher rounding",
                 presets={"strict": 0.03, "balanced": 0.05, "relaxed": 0.10}),
             "warn_dev": ThresholdSpec("warn_dev", 0.20, 0.05, 0.60, 0.05,
                 "raise to fail only on egregious oversizing",
                 presets={"strict": 0.15, "balanced": 0.20, "relaxed": 0.35}),
         })
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_risk.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/risk_def.py tests/test_gate_risk.py
git commit -m "feat: size_formula check"
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

### Task G71: Check `portfolio_room` (weight 6)

**Files:** Modify `risk_def.py`, `registry.py`; test `tests/test_gate_risk.py`

**Interfaces:** `check_portfolio_room(df_daily, plan, macro_snap, open_plans=None) -> CheckResult` — warn when ≥ `GATE_MAX_CORR_POSITIONS` (int field, default 2) open plans share the ticker's sector (G25 `sector_of`); fail when the same ticker already has an open plan. Delegates to edge-engine heat/correlation caps (E7/E8) when merged — then this check only *reports* their verdict.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_risk.py`)

```python
import swingbot.core.gate.risk_def as risk_def
from swingbot.core.gate.risk_def import check_portfolio_room


def test_duplicate_ticker_fails():
    open_plans = [{"ticker": "TEST", "status": "open"}]
    result = check_portfolio_room(uptrend_daily(), make_plan(ticker="TEST"), None,
                                  open_plans=open_plans)
    assert result.status == "fail"


def test_correlated_sector_warns(monkeypatch):
    monkeypatch.setattr(risk_def, "sector_of", lambda t: "Technology")
    open_plans = [{"ticker": "AAPL"}, {"ticker": "MSFT"}]
    result = check_portfolio_room(uptrend_daily(), make_plan(ticker="NVDA"), None,
                                  open_plans=open_plans)
    assert result.status == "warn" and "Technology" in result.detail


def test_empty_book_passes():
    assert check_portfolio_room(uptrend_daily(), make_plan(), None,
                                open_plans=[]).status == "pass"
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'check_portfolio_room'`)
- [ ] **Step 3: Write the implementation** (append to `risk_def.py`)

```python
from swingbot.core.macro.sectors import sector_of


def check_portfolio_room(df_daily, plan, macro_snap, *, open_plans=None,
                         **ctx) -> CheckResult:
    """Capability note: when edge-engine heat/correlation caps (E7/E8) are
    merged, this check only REPORTS their verdict (verify at execution)."""
    spec = CHECKS["portfolio_room"]
    open_plans = open_plans or []
    tickers = [p.get("ticker") for p in open_plans if p.get("ticker")]
    if plan.ticker in tickers:
        return CheckResult("portfolio_room", "risk", "fail", 6.0,
                           f"{plan.ticker} already has an open plan",
                           {"open_tickers": tickers})
    sector = sector_of(plan.ticker)
    if sector:
        same = sum(1 for t in tickers if sector_of(t) == sector)
        if same >= int(spec.threshold("max_corr")):
            return CheckResult("portfolio_room", "risk", "warn", 6.0,
                               f"{same} open plans already in {sector}",
                               {"sector": sector, "same_sector": same})
    return CheckResult("portfolio_room", "risk", "pass", 6.0,
                       "room in the book", {"open_count": len(tickers)})


register(check_id="portfolio_room", section="risk", weight=6.0,
         func=check_portfolio_room, backtestable=False,
         thresholds={
             "max_corr": ThresholdSpec("max_corr", 2, 1, 6, 1,
                 "raise to allow more same-sector positions (GATE_MAX_CORR_POSITIONS)",
                 presets={"strict": 1, "balanced": 2, "relaxed": 4}),
         })
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_risk.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/risk_def.py tests/test_gate_risk.py
git commit -m "feat: portfolio_room check"
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

### Task G77: Soft-flag sizing suggestion

**Files:** Modify `score.py`; test `tests/test_gate_score.py`

**Interfaces:** `suggested_size_mult(tier: str) -> float` — the checklist's own "size down significantly" rule as a *suggestion carried on the result*, never auto-applied in this phase: `{"A+": 1.0, "A": 1.0, "B": 0.5, "C": 0.0}` from config fields `GATE_SIZE_MULT_B` (default 0.5) etc. G116 fold-tests making it real.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_score.py`)

```python
import swingbot.config as config
from swingbot.core.gate.score import suggested_size_mult


def test_default_multipliers():
    assert suggested_size_mult("A+") == 1.0
    assert suggested_size_mult("A") == 1.0
    assert suggested_size_mult("B") == 0.5
    assert suggested_size_mult("C") == 0.0


def test_config_overrides(monkeypatch):
    monkeypatch.setattr(config, "GATE_SIZE_MULT_B", 0.75, raising=False)
    assert suggested_size_mult("B") == 0.75
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'suggested_size_mult'`)
- [ ] **Step 3: Write the implementation** (append to `score.py`; plus config Fields)

```python
_SIZE_MULT_DEFAULTS = {"A+": 1.0, "A": 1.0, "B": 0.5, "C": 0.0}
_SIZE_MULT_KEYS = {"A+": "GATE_SIZE_MULT_APLUS", "A": "GATE_SIZE_MULT_A",
                   "B": "GATE_SIZE_MULT_B", "C": "GATE_SIZE_MULT_C"}


def suggested_size_mult(tier: str) -> float:
    """The checklist's own "size down significantly" rule as a SUGGESTION
    carried on the result — never auto-applied in this phase (G116
    fold-tests making it real; G117 wires it behind its own flag)."""
    import swingbot.config as config
    return float(getattr(config, _SIZE_MULT_KEYS[tier], _SIZE_MULT_DEFAULTS[tier]))
```

```python
# swingbot/config.py — append to the Gatekeeper section:
    Field("GATE_SIZE_MULT_APLUS", "GATE_SIZE_MULT_APLUS", "Gatekeeper",
          "Size multiplier: A+ tier", type="float", default="1.0", min=0, max=2, step=0.05,
          help="Suggested position-size multiplier for A+ checklists (applied only "
               "with tier sizing enabled, G117)."),
    Field("GATE_SIZE_MULT_A", "GATE_SIZE_MULT_A", "Gatekeeper",
          "Size multiplier: A tier", type="float", default="1.0", min=0, max=2, step=0.05),
    Field("GATE_SIZE_MULT_B", "GATE_SIZE_MULT_B", "Gatekeeper",
          "Size multiplier: B tier", type="float", default="0.5", min=0, max=2, step=0.05),
    Field("GATE_SIZE_MULT_C", "GATE_SIZE_MULT_C", "Gatekeeper",
          "Size multiplier: C tier", type="float", default="0.0", min=0, max=2, step=0.05),
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_score.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/score.py swingbot/config.py tests/test_gate_score.py
git commit -m "feat: tier size-multiplier suggestion"
```

### Task G78: Weight & neutrality calibration over fixtures

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

### Task G82: Checklist embed renderer

**Files:**
- Create: `swingbot/core/gate/render.py`
- Test: `tests/test_gate_render.py`

**Interfaces:** `checklist_field(result) -> tuple[str, str]` — (name `"📋 Checklist — {tier} ({score:.0f})"`, value: five section lines `✅/⚠️/⛔/◻️` counts e.g. `"Context ✅3 · Setup ✅2 ⚠️1 · Red flags ⛔1 · Risk ✅3 · Timing ✅2"`); `redflag_table(result) -> str` — only fired/warned flags, one line each `"⛔ Fake breakout — closed back inside on 0.6× volume"` (≤ 1024 chars, truncation-safe); `full_breakdown(result) -> list[str]` — every check with its detail, chunked for Discord message limits. Pure string builders, no discord.py imports (testable).
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_render.py
from swingbot.core.gate.render import checklist_field, full_breakdown, redflag_table
from swingbot.core.gate.types import CheckResult, GateResult


def _result():
    checks = (
        CheckResult("htf_alignment", "context", "pass", 12.0, "with trend", {}),
        CheckResult("level_map", "context", "warn", 8.0, "wall 1.5 ATR out", {}),
        CheckResult("confluence", "setup", "pass", 10.0, "3 factors", {}),
        CheckResult("rf_fake_breakout", "redflag", "fail", 10.0,
                    "closed back inside on 0.6x volume", {}),
        CheckResult("rf_opex_pin", "redflag", "warn", 4.0, "opex tomorrow", {}),
        CheckResult("stop_structural", "risk", "pass", 10.0, "1.2 ATR beyond", {}),
        CheckResult("not_chasing", "timing", "unknown", 8.0, "no price", {}),
    )
    return GateResult(ticker="NVDA", strategy="Break & Retest", as_of="2026-07-14",
                      checks=checks, score=61.0, tier="B",
                      hard_blocks=(), macro_stale=False, advisory_decision="downgrade")


def test_checklist_field_golden():
    name, value = checklist_field(_result())
    assert name == "📋 Checklist — B (61)"
    assert "Context ✅1 ⚠️1" in value
    assert "Red flags ⛔1 ⚠️1" in value
    assert "Timing ◻️1" in value


def test_redflag_table_only_fired_rows():
    table = redflag_table(_result())
    assert "⛔ Fake Breakout — closed back inside on 0.6x volume" in table
    assert "⚠️ Opex Pin — opex tomorrow" in table
    assert "stop_structural" not in table
    assert len(table) <= 1024


def test_redflag_table_truncation_safe():
    many = tuple(CheckResult(f"rf_flag_{i}", "redflag", "fail", 5.0, "x" * 90, {})
                 for i in range(30))
    result = GateResult("T", "VWAP", "2026-07-14", many, 0.0, "C", (), False)
    assert len(redflag_table(result)) <= 1024


def test_full_breakdown_chunks_under_2000():
    chunks = full_breakdown(_result())
    assert chunks and all(len(c) <= 2000 for c in chunks)
    assert any("`rf_fake_breakout`" in c for c in chunks)
```

- [ ] **Step 2: Run — FAIL** (`ImportError`), then **implement**:

```python
# swingbot/core/gate/render.py
"""Pure string builders for Discord surfaces — no discord.py imports."""
from __future__ import annotations

from swingbot.core.gate.types import GateResult

STATUS_EMOJI = {"pass": "✅", "warn": "⚠️", "fail": "⛔", "unknown": "◻️"}
SECTION_LABEL = {"context": "Context", "setup": "Setup", "redflag": "Red flags",
                 "risk": "Risk", "timing": "Timing"}
SECTION_ORDER = ("context", "setup", "redflag", "risk", "timing")


def _flag_title(check_id: str) -> str:
    return check_id.removeprefix("rf_").replace("_", " ").title()


def checklist_field(result: GateResult) -> tuple[str, str]:
    name = f"📋 Checklist — {result.tier} ({result.score:.0f})"
    parts = []
    for section in SECTION_ORDER:
        checks = [c for c in result.checks if c.section == section]
        if not checks:
            continue
        counts = [f"{STATUS_EMOJI[s]}{n}"
                  for s in ("pass", "warn", "fail", "unknown")
                  if (n := sum(1 for c in checks if c.status == s))]
        parts.append(f"{SECTION_LABEL[section]} {' '.join(counts)}")
    return name, " · ".join(parts)


def redflag_table(result: GateResult) -> str:
    rows = [f"{STATUS_EMOJI[c.status]} {_flag_title(c.check_id)} — {c.detail}"
            for c in result.checks
            if c.section == "redflag" and c.status in ("fail", "warn")]
    text = "\n".join(rows)
    if len(text) > 1024:
        text = text[:990].rsplit("\n", 1)[0] + "\n… (truncated)"
    return text


def full_breakdown(result: GateResult, chunk_size: int = 1900) -> list[str]:
    lines = [f"**Checklist {result.ticker} [{result.strategy}] — "
             f"{result.tier} ({result.score:.0f})**"]
    for section in SECTION_ORDER:
        checks = [c for c in result.checks if c.section == section]
        if not checks:
            continue
        lines.append(f"__{SECTION_LABEL[section]}__")
        lines += [f"{STATUS_EMOJI[c.status]} `{c.check_id}` {c.detail}"
                  for c in checks]
    chunks, current = [], ""
    for line in lines:
        if len(current) + len(line) + 1 > chunk_size:
            chunks.append(current.rstrip())
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current.rstrip())
    return chunks
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_render.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/render.py tests/test_gate_render.py
git commit -m "feat: checklist render strings"
```

### Task G83: Gut-check ritual — Discord buttons + modal

**Files:**
- Create: `swingbot/core/gate/gutcheck.py` (state), modify `swingbot/commands/scanning.py` (view wiring)
- Test: `tests/test_gate_gutcheck.py`

**Interfaces:** `GutCheckView(plan_id)` — buttons `✅ Follow` / `⛔ Skip` / `📝 Why I'd be wrong`; the third opens a modal with two inputs: "One sentence: why I'd be wrong if the stop is hit" (required, checklist §6) and "Would I take this if my last trade was a loss?" (yes/no). `record_gutcheck(plan_id, answers) -> None` persists to the plan record + journal (`gutcheck` key). Buttons are optional ritual — a plan follows normally without them; config `GATE_GUTCHECK_REQUIRED` (checkbox, default false) makes Follow require the modal first. State machinery pure-python; the discord View is a thin shell (interaction handlers tested via the fake-interaction pattern already used by the command tests — verify the existing pattern at execution).
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_gutcheck.py
import pytest

import swingbot.config as config
from swingbot.core.gate.gutcheck import (get_gutcheck, record_gutcheck,
                                         required_before_follow)
from swingbot.core.plan_store import PlanStore
from tests.fixtures.gate.plans import make_plan


@pytest.fixture
def store(tmp_path):
    s = PlanStore(path=str(tmp_path / "plans.json"))
    s.add(make_plan())
    return s


def test_record_round_trip(store):
    ok = record_gutcheck(store, "p_test_0001",
                         {"choice": "follow",
                          "why_wrong": "  Breakout fails if SPY rejects 5600  ",
                          "after_loss": "yes"})
    assert ok is True
    saved = get_gutcheck(store, "p_test_0001")
    assert saved["choice"] == "follow"
    assert saved["why_wrong"] == "Breakout fails if SPY rejects 5600"
    assert saved["after_loss"] == "yes" and saved["ts"] > 0
    assert record_gutcheck(store, "p_missing", {"choice": "skip"}) is False


def test_required_mode_flag(monkeypatch):
    monkeypatch.setattr(config, "GATE_GUTCHECK_REQUIRED", False, raising=False)
    assert required_before_follow() is False
    monkeypatch.setattr(config, "GATE_GUTCHECK_REQUIRED", True, raising=False)
    assert required_before_follow() is True
```

- [ ] **Step 2: Run — FAIL** (`ImportError`), then **implement**:

```python
# swingbot/core/gate/gutcheck.py
"""Gut-check ritual state — pure python + PlanStore persistence. The
discord View/Modal shells live in swingbot/commands/scanning.py."""
from __future__ import annotations

import time

import swingbot.config as config

GUTCHECK_KEY = "gutcheck"


def record_gutcheck(store, plan_id: str, answers: dict) -> bool:
    """answers: {"choice": "follow"|"skip", "why_wrong": str|None,
    "after_loss": "yes"|"no"|None}. Persists on the plan record."""
    payload = {"ts": time.time(),
               "choice": answers.get("choice"),
               "why_wrong": (answers.get("why_wrong") or "").strip() or None,
               "after_loss": answers.get("after_loss")}
    return store.set_extra(plan_id, GUTCHECK_KEY, payload)


def get_gutcheck(store, plan_id: str) -> dict | None:
    return store.get_extra(plan_id, GUTCHECK_KEY)


def required_before_follow() -> bool:
    return bool(getattr(config, "GATE_GUTCHECK_REQUIRED", False))
```

**The Discord shell** (`swingbot/commands/scanning.py` — thin; interaction
handlers follow the fake-interaction test pattern the command tests already
use, verify at execution):

```python
import discord

from swingbot.core.gate import gutcheck


class WhyWrongModal(discord.ui.Modal, title="Gut check"):
    why_wrong = discord.ui.TextInput(
        label="One sentence: why I'd be wrong if the stop is hit",
        style=discord.TextStyle.short, required=True, max_length=200)
    after_loss = discord.ui.TextInput(
        label="Would I take this if my last trade was a loss? (yes/no)",
        style=discord.TextStyle.short, required=True, max_length=3)

    def __init__(self, plan_id: str, store, follow_after: bool = False):
        super().__init__()
        self.plan_id, self.store, self.follow_after = plan_id, store, follow_after

    async def on_submit(self, interaction: discord.Interaction):
        gutcheck.record_gutcheck(self.store, self.plan_id, {
            "choice": "follow" if self.follow_after else "noted",
            "why_wrong": str(self.why_wrong.value),
            "after_loss": str(self.after_loss.value).lower()})
        await interaction.response.send_message("Gut check recorded. 📝", ephemeral=True)


class GutCheckView(discord.ui.View):
    def __init__(self, plan_id: str, store):
        super().__init__(timeout=86400)          # 24h; expiry = "not answered"
        self.plan_id, self.store = plan_id, store

    @discord.ui.button(label="✅ Follow", style=discord.ButtonStyle.success)
    async def follow(self, interaction, button):
        if gutcheck.required_before_follow() and \
                not gutcheck.get_gutcheck(self.store, self.plan_id):
            await interaction.response.send_modal(
                WhyWrongModal(self.plan_id, self.store, follow_after=True))
            return
        gutcheck.record_gutcheck(self.store, self.plan_id, {"choice": "follow"})
        await interaction.response.send_message("Following. ✅", ephemeral=True)

    @discord.ui.button(label="⛔ Skip", style=discord.ButtonStyle.danger)
    async def skip(self, interaction, button):
        gutcheck.record_gutcheck(self.store, self.plan_id, {"choice": "skip"})
        await interaction.response.send_message("Skipped. ⛔", ephemeral=True)

    @discord.ui.button(label="📝 Why I'd be wrong", style=discord.ButtonStyle.secondary)
    async def why(self, interaction, button):
        await interaction.response.send_modal(WhyWrongModal(self.plan_id, self.store))
```

**Plus one config Field:**

```python
    Field("GATE_GUTCHECK_REQUIRED", "GATE_GUTCHECK_REQUIRED", "Gatekeeper",
          "Require gut check before Follow", type="checkbox", default="false",
          help="When on, the ✅ Follow button opens the why-I'd-be-wrong modal "
               "first (checklist §6 ritual). A plan still follows its lifecycle "
               "normally without the buttons."),
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_gutcheck.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/gutcheck.py swingbot/commands/scanning.py swingbot/config.py tests/test_gate_gutcheck.py
git commit -m "feat: gut-check ritual (buttons + why-wrong journal)"
```

### Task G84: Journal integration on close — was the checklist right?

**Files:** Modify `swingbot/core/gate/persistence.py` (+ the analytics journal close-hook)
- Test: `tests/test_gate_persistence.py`

**Interfaces:** `on_trade_close(trade, journal_entry) -> dict` — pulls the plan's stored GateResult; appends to the journal entry: `{gate_tier, gate_score, fired_flags: [...], gutcheck_present: bool}` tags (e.g. `tier-a-plus`, `rf-fake-breakout-ignored` when a flagged trade was taken anyway). Wired into the existing JournalStore close hook (cockpit A-phase) behind a capability check.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_persistence.py`)

```python
from swingbot.core.gate.persistence import on_trade_close


def test_close_hook_tags_journal_entry(env):
    attach_to_plan(env, "p_test_0001", _result())          # tier B, rf fired
    trade = {"plan_id": "p_test_0001", "ticker": "TEST", "outcome": "loss"}
    entry = on_trade_close(trade, {"outcome": "loss"}, store=env)
    assert entry["gate_tier"] == "B" and entry["gate_score"] == 48.0
    assert entry["fired_flags"] == ["rf_fake_breakout"]
    assert entry["gutcheck_present"] is False
    assert "tier-b" in entry["tags"]
    assert "rf-fake-breakout-ignored" in entry["tags"]


def test_close_hook_noop_without_gate_data(env):
    entry = on_trade_close({"plan_id": "p_test_0001"}, {"outcome": "win"}, store=env)
    assert "gate_tier" not in entry                        # plan pre-dates the gate
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'on_trade_close'`)
- [ ] **Step 3: Write the implementation** (append to `persistence.py`)

```python
def on_trade_close(trade: dict, journal_entry: dict, *, store=None) -> dict:
    """Journal close-hook: was the checklist right? Wire into the existing
    JournalStore close hook (cockpit A-phase) behind a capability check —
    absent journal, this function is simply never called."""
    plan_id = trade.get("plan_id")
    gate = store.get_extra(plan_id, "gate") if (store and plan_id) else None
    if not gate:
        return journal_entry
    fired = [c["check_id"] for c in gate.get("checks", [])
             if c.get("section") == "redflag" and c.get("status") == "fail"]
    journal_entry["gate_tier"] = gate.get("tier")
    journal_entry["gate_score"] = gate.get("score")
    journal_entry["fired_flags"] = fired
    journal_entry["gutcheck_present"] = bool(store.get_extra(plan_id, "gutcheck"))
    tags = journal_entry.setdefault("tags", [])
    tags.append(f"tier-{gate.get('tier', '?').lower().replace('+', '-plus')}")
    tags += [f"{flag.replace('_', '-')}-ignored" for flag in fired]
    return journal_entry
```

**Wiring** (the JournalStore close hook, cockpit A-phase — capability-checked):

```python
# at the journal close site (verify exact hook name at execution):
try:
    from swingbot.core.gate.persistence import on_trade_close as _gate_close
    entry = _gate_close(trade, entry, store=plan_store_instance)
except ImportError:
    pass
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_persistence.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/persistence.py tests/test_gate_persistence.py
git commit -m "feat: gate outcome tags in the journal"
```

### Task G85: Red-flag outcome tagger — the receipts

**Files:** Modify `persistence.py`; test `tests/test_gate_persistence.py`

**Interfaces:** `flag_outcome_stats(journal_entries) -> list[dict]` — per red-flag id: `{flag, n_fired_and_taken, wr_when_ignored, wr_when_clean, delta_wr, avg_r_when_ignored}` — the live evidence for "this flag earns its keep" consumed by `!redflags` (G115) and the admin analytics page (G183). Pure over journal entries.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_persistence.py`)

```python
from swingbot.core.gate.persistence import flag_outcome_stats


def test_flag_outcome_stats_golden():
    entries = (
        [{"outcome": "loss", "r_multiple": -1.0, "fired_flags": ["rf_fake_breakout"]}] * 3
        + [{"outcome": "win", "r_multiple": 1.5, "fired_flags": ["rf_fake_breakout"]}]
        + [{"outcome": "win", "r_multiple": 1.5, "fired_flags": []}] * 6
        + [{"outcome": "loss", "r_multiple": -1.0, "fired_flags": []}] * 2
        + [{"outcome": "open", "fired_flags": ["rf_fake_breakout"]}]   # ignored
    )
    rows = flag_outcome_stats(entries)
    assert len(rows) == 1
    row = rows[0]
    assert row["flag"] == "rf_fake_breakout"
    assert row["n_fired_and_taken"] == 4
    assert row["wr_when_ignored"] == 25.0          # 1/4
    assert row["wr_when_clean"] == 75.0            # 6/8
    assert row["delta_wr"] == -50.0                # the receipt
    assert row["avg_r_when_ignored"] == -0.38


def test_empty_entries():
    assert flag_outcome_stats([]) == []
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'flag_outcome_stats'`)
- [ ] **Step 3: Write the implementation** (append to `persistence.py`)

```python
def flag_outcome_stats(journal_entries: list[dict]) -> list[dict]:
    """Per red flag: what happened when a flagged trade was taken anyway
    vs when the flag was clean — the live receipts for !redflags (G115)
    and the flags analytics page (G181). Pure over journal entries."""
    closed = [e for e in journal_entries if e.get("outcome") in ("win", "loss")]

    def _wr(rows):
        return round(100.0 * sum(r["outcome"] == "win" for r in rows) / len(rows), 1) \
            if rows else None

    flags = sorted({f for e in closed for f in e.get("fired_flags", [])})
    out = []
    for flag in flags:
        fired = [e for e in closed if flag in e.get("fired_flags", [])]
        clean = [e for e in closed if flag not in e.get("fired_flags", [])]
        wr_fired, wr_clean = _wr(fired), _wr(clean)
        out.append({
            "flag": flag,
            "n_fired_and_taken": len(fired),
            "wr_when_ignored": wr_fired,
            "wr_when_clean": wr_clean,
            "delta_wr": (round(wr_fired - wr_clean, 1)
                         if None not in (wr_fired, wr_clean) else None),
            "avg_r_when_ignored": (round(sum(e.get("r_multiple", 0.0) for e in fired)
                                         / len(fired), 2) if fired else None),
        })
    out.sort(key=lambda r: r["delta_wr"] if r["delta_wr"] is not None else 0.0)
    return out
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_gate_persistence.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/persistence.py tests/test_gate_persistence.py
git commit -m "feat: red-flag outcome stats"
```

### Task G86: Analytics snapshot integration

**Files:** Modify `swingbot/core/analytics/snapshots.py` (additive section)
- Test: `tests/test_gate_persistence.py`

**Interfaces:** snapshot gains a `"gate"` section: tier distribution of open+recent plans, WR by tier (via `analytics.metrics`, one-definition rule), flag outcome stats (G85), shadow-mode divergence summary (G104's numbers once live). Absent gate data → section `{}`, snapshot otherwise unchanged (byte-compare test for the no-gate case).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_persistence.py`)

```python
from swingbot.core.gate.persistence import gate_analytics_section


def test_gate_section_shape():
    entries = [
        {"outcome": "win", "r_multiple": 1.5, "gate_tier": "A", "fired_flags": []},
        {"outcome": "loss", "r_multiple": -1.0, "gate_tier": "C",
         "fired_flags": ["rf_dead_cat"]},
    ]
    section = gate_analytics_section(entries)
    assert section["tier_wr"]["A"]["n"] == 1
    assert section["tier_wr"]["C"]["wr"] == 0.0
    assert section["flags"][0]["flag"] == "rf_dead_cat"


def test_no_gate_data_is_empty_dict():
    assert gate_analytics_section([{"outcome": "win"}]) == {}
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `persistence.py`):

```python
def gate_analytics_section(journal_entries: list[dict]) -> dict:
    """The "gate" section for the analytics snapshot. One-definition rule:
    when swingbot.core.analytics.metrics is available (cockpit Part 1),
    WR/expectancy_r route through it; the local fallback below keeps the
    same arithmetic for a pre-merge tree. Absent gate data -> {} and the
    snapshot is byte-identical to before."""
    tagged = [e for e in journal_entries if e.get("gate_tier")]
    if not tagged:
        return {}
    try:
        from swingbot.core.analytics import metrics  # verify names at execution
        wr_fn = metrics.win_rate
        exp_fn = metrics.expectancy_r
    except ImportError:
        def wr_fn(rows):
            closed = [r for r in rows if r.get("outcome") in ("win", "loss")]
            return (round(100.0 * sum(r["outcome"] == "win" for r in closed)
                          / len(closed), 1) if closed else None)

        def exp_fn(rows):
            closed = [r for r in rows if r.get("outcome") in ("win", "loss")]
            return (round(sum(r.get("r_multiple", 0.0) for r in closed)
                          / len(closed), 3) if closed else None)
    tiers = {}
    for tier in ("A+", "A", "B", "C"):
        rows = [e for e in tagged if e["gate_tier"] == tier]
        tiers[tier] = {"n": len(rows), "wr": wr_fn(rows) if rows else None,
                       "expectancy_r": exp_fn(rows) if rows else None}
    return {"tier_wr": tiers, "flags": flag_outcome_stats(tagged)}
```

**Wiring into `swingbot/core/analytics/snapshots.py`** (cockpit Part 1 — additive):

```python
    # inside the snapshot builder, after the existing sections:
    try:
        from swingbot.core.gate.persistence import gate_analytics_section
        gate_section = gate_analytics_section(journal_entries)
        if gate_section:
            snapshot["gate"] = gate_section
    except ImportError:
        pass
```

Add a byte-compare test in `tests/` (or extend the existing snapshot test): building the snapshot with zero gate-tagged entries produces output identical to before this change.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_persistence.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/persistence.py swingbot/core/analytics/snapshots.py tests/test_gate_persistence.py
git commit -m "feat: gate section in analytics snapshot"
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

- [ ] **Step 1:** Full suite + `make check` green. Registry invariant test passes with **all** checks registered (context 4, setup 5, red flags 11, risk 4, timing 3 = 27 checks).
- [ ] **Step 2:** Update Progress block. Commit — `chore: phase G2 checkpoint (27 checks live)`

---
