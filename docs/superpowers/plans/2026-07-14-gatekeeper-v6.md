# Gatekeeper v6 — Pre-Trade Checklist Gate & Macro Context Engine Implementation Plan (216 tasks)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute strictly in order (Tasks G1–G216).

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

## Progress

> Updated by the executing session after each task batch. Resume from the first unchecked task.
>
> - **Branch:** `feature/gatekeeper-v6`
> - **Completed:** —
> - **Next:** Task G1

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

# Phase G0 — Honest math, contracts & scaffolding (G1–G8)

### Task G1: `wr_math.py` — the win-rate arithmetic everyone must share

**Files:**
- Create: `swingbot/core/gate/__init__.py`, `swingbot/core/gate/wr_math.py`
- Test: `tests/test_gate_wr_math.py`

**Interfaces:**
- Produces: `breakeven_wr(rr: float) -> float` (WR where expectancy = 0 for a fixed R:R); `implied_expectancy(wr_pct: float, avg_win_r: float, avg_loss_r: float = 1.0) -> float`; `required_filter_precision(base_wr: float, target_wr: float) -> float` (fraction of losers a filter must remove, keeping winners, to lift base to target: `1 - (base*(100-target))/(target*(100-base))` on decimal odds); `wilson_lower_bound(wins: int, n: int, z: float = 1.96) -> float` (the WR a sample actually *proves*).
- Consumed by: G2 (targets doc), G93–G95 (frontier/tiers), G114, G204.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gate_wr_math.py
import pytest
from swingbot.core.gate.wr_math import (
    breakeven_wr, implied_expectancy, required_filter_precision, wilson_lower_bound,
)

def test_breakeven_wr_golden():
    assert breakeven_wr(1.5) == pytest.approx(40.0)   # 1/(1+1.5)
    assert breakeven_wr(1.0) == pytest.approx(50.0)

def test_implied_expectancy_95_at_1_5r():
    # 95% WR, +1.5R wins, -1R losses -> 0.95*1.5 - 0.05*1 = +1.375R.
    # No swing system sustains that; the number itself is the honesty check.
    assert implied_expectancy(95.0, 1.5) == pytest.approx(1.375)

def test_filter_precision_needed_for_85_to_95():
    # Lifting 85% -> 95% means removing ~70.2% of losers without touching winners.
    assert required_filter_precision(85.0, 95.0) == pytest.approx(0.7018, abs=1e-3)

def test_wilson_needs_n_59_for_proven_90():
    # 59/59 wins is the smallest all-win sample whose 95% lower bound clears 90%.
    assert wilson_lower_bound(59, 59) > 0.90
    assert wilson_lower_bound(35, 35) < 0.90
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gate_wr_math.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.core.gate'`

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/gate/__init__.py
"""Gatekeeper — pre-trade checklist engine. Public API grows in G75."""
```

```python
# swingbot/core/gate/wr_math.py
"""Win-rate arithmetic every gate surface must share.

Golden numbers (hand-derived, mirrored in tests):
- breakeven_wr(1.5) = 100/(1+1.5) = 40.0
- implied_expectancy(95, 1.5) = 0.95*1.5 - 0.05*1.0 = +1.375R
- required_filter_precision(85, 95) = 1 - (85*5)/(95*15) = 0.7018
- wilson_lower_bound uses the CONTINUITY-CORRECTED Wilson interval
  (Newcombe 1998). The plain Wilson bound gives 35/35 -> 0.901 which
  would falsely "prove" 90% from 35 trades; the corrected bound gives
  35/35 -> 0.877 and 59/59 -> 0.924, which is the conservatism the
  95%-label rule (G2, G204) is built on.
"""
import math


def breakeven_wr(rr: float) -> float:
    """WR (percent) where expectancy = 0 for a fixed reward:risk ratio."""
    return 100.0 / (1.0 + rr)


def implied_expectancy(wr_pct: float, avg_win_r: float, avg_loss_r: float = 1.0) -> float:
    """Expectancy in R implied by a WR and average win/loss sizes."""
    p = wr_pct / 100.0
    return p * avg_win_r - (1.0 - p) * avg_loss_r


def required_filter_precision(base_wr: float, target_wr: float) -> float:
    """Fraction of losers a filter must remove (keeping every winner)
    to lift base_wr to target_wr. Derivation: keep W winners, remove
    fraction f of L losers; W/(W+L(1-f)) = t  =>  f = 1 - (b(100-t))/(t(100-b))
    with b, t as percentages."""
    b, t = base_wr, target_wr
    return 1.0 - (b * (100.0 - t)) / (t * (100.0 - b))


def wilson_lower_bound(wins: int, n: int, z: float = 1.96) -> float:
    """Continuity-corrected Wilson score lower bound — the WR (as a
    fraction) a sample actually *proves* at ~95% confidence. Returns 0.0
    for n == 0 or wins == 0."""
    if n == 0 or wins == 0:
        return 0.0
    p = wins / n
    num = (
        2 * n * p + z * z - 1
        - z * math.sqrt(z * z - 2 - 1 / n + 4 * p * (n * (1 - p) + 1))
    )
    return max(0.0, num / (2 * (n + z * z)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gate_wr_math.py -v`
Expected: 4 passed

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/ tests/test_gate_wr_math.py
git commit -m "feat: gate win-rate arithmetic (breakeven, implied E, filter precision, Wilson)"
```

### Task G2: Pre-registered targets & promotion gates document

**Files:**
- Create: `docs/superpowers/specs/2026-07-14-gatekeeper-v6-targets.md`

- [ ] **Step 1: Write the frozen targets doc** — this exact content:

```markdown
# Gatekeeper v6 — Pre-registered targets & promotion gates

**Frozen 2026-07-14, before any data contact.** After the first baseline
census (Task G97) runs, evidence may be appended (dated) but targets may
never be moved.

## The non-promise

> **"95% is a label a tier can earn from N ≥ 59 proven samples
> (Wilson LB > 90%) — never a setting."**

Win rate is trivially inflated by shrinking targets and widening stops;
that destroys expectancy and the account with it. Every WR gain must come
from *not taking bad trades*. The exit geometry validated in
plan-engine-v2 is untouchable.

## Tier ladder

| Tier | Meaning | Pre-registered target (pooled TRAIN folds) |
|---|---|---|
| A+ | Every box checked, zero red flags | WR ≥ 90% with N ≥ 30 per fold and expectancy_r ≥ the strategy's unfiltered baseline. **"95-class" label** may be applied only when the continuity-corrected Wilson lower bound (z=1.96) exceeds 0.90 — at ~95% observed WR that takes N ≥ 59. |
| A | Score ≥ A-cut, no hard blocks | WR ≥ baseline + 5 pts, expectancy_r ≥ baseline − 0.02R |
| B | Score ≥ B-cut | ≈ baseline (the unfiltered strategy) |
| C | Below B-cut, or any hard block | Skip-in-live candidate. Measured and always visible — never silently hidden. |

## Fold gate (identical to edge-engine-v4)

Anchored expanding folds — train 2018→fold-start, test years 2021 / 2022 / 2023.
A check or threshold is promoted only if:

- it improves the optimization target in ≥ 2 of 3 folds, and
- no fold degrades expectancy_r by > 0.05R, and
- N ≥ 30 per fold behind every quoted WR.

Optimization target: maximize WR **subject to** pooled fold expectancy_r
≥ baseline − 0.02R. WR alone never picks a parameter. Failures are
documented in `docs/superpowers/results/` and dropped — no second grid on
the same hypothesis.

## All-strategies aggregate target

**+3 to +8 WR points vs. the v2 baseline at ≤ 40% signal loss**, pooled
TRAIN folds, all strategies together.

## Shadow gate (prerequisite for ever leaving inform mode)

Enforce mode may be considered only after all of:

- ≥ 14 calendar days of live shadow/inform logging,
- ≥ 15 would-have-blocked decisions on record,
- the would-have-blocked cohort's realized WR is *lower* than the passed
  cohort's (the gate is directionally right live),
- zero live crashes or scan timeouts attributable to the gate.

Operationalized as a dated sign-off checklist in Task G105. Enforce is
optional forever; plan completion does not depend on it.

## Traceability

Every checklist line maps to its implementing task in
"Appendix — Checklist-to-task traceability" at the end of
`docs/superpowers/plans/2026-07-14-gatekeeper-v6.md`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-07-14-gatekeeper-v6-targets.md
git commit -m "docs: gatekeeper v6 pre-registered targets (frozen before data contact)"
```

### Task G3: Config section "Gatekeeper" — base flags

**Files:**
- Modify: `swingbot/config.py`
- Test: `tests/test_gate_config.py`

**Interfaces:**
- Produces Fields (section `"Gatekeeper"`, all default off/neutral): `GATE_ENABLED` (checkbox, false — master switch), `GATE_MODE` (select `shadow`|`inform`|`enforce`, default `inform` — inform renders the checklist on every alert and never blocks; enforce is opt-in and guarded by G170), `GATE_MIN_TIER` (select `A+`|`A`|`B`|`C`, default `C`; **consulted only in enforce mode**), `GATE_STRICTNESS` (select `strict`|`balanced`|`relaxed`, default `balanced` — preset seeding for the G79 threshold fields), `MACRO_ENABLED` (checkbox, false), `FRED_API_KEY` (password, sensitive), `MACRO_SNAPSHOT_TTL_MIN` (int, 30, min 5), `GATE_BLACKOUT_ENABLED` (checkbox, false — annotate-only; holding entries additionally requires `GATE_BLACKOUT_ENFORCE`, G120). (`FINNHUB_API_KEY` already exists from llm-advisor L10; if that plan is unmerged, add it here with the same shape.)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gate_config.py
from swingbot import config


def field(key):
    return next((f for f in config.FIELDS if f.key == key), None)


def test_gatekeeper_fields_present_with_defaults():
    expected = {  # key: (type, default)
        "GATE_ENABLED": ("checkbox", "false"),
        "GATE_MODE": ("select", "inform"),
        "GATE_MIN_TIER": ("select", "C"),
        "GATE_STRICTNESS": ("select", "balanced"),
        "MACRO_ENABLED": ("checkbox", "false"),
        "FRED_API_KEY": ("password", ""),
        "MACRO_SNAPSHOT_TTL_MIN": ("number", "30"),
        "GATE_BLACKOUT_ENABLED": ("checkbox", "false"),
    }
    for key, (ftype, default) in expected.items():
        f = field(key)
        assert f is not None, f"{key} missing from config.FIELDS"
        assert f.section == "Gatekeeper", key
        assert f.type == ftype, key
        assert f.default == default, key


def test_select_options_exact():
    assert [v for v, _ in field("GATE_MODE").options] == ["shadow", "inform", "enforce"]
    assert [v for v, _ in field("GATE_MIN_TIER").options] == ["A+", "A", "B", "C"]
    assert [v for v, _ in field("GATE_STRICTNESS").options] == ["strict", "balanced", "relaxed"]


def test_api_key_sensitive_and_ttl_floor():
    assert field("FRED_API_KEY").sensitive is True
    assert field("MACRO_SNAPSHOT_TTL_MIN").min == 5


def test_finnhub_key_exists_somewhere():
    # From llm-advisor L10 when merged; added here otherwise — either way it must exist.
    f = field("FINNHUB_API_KEY")
    assert f is not None and f.sensitive is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gate_config.py -v`
Expected: FAIL — `assert f is not None` for `GATE_ENABLED`

- [ ] **Step 3: Write the implementation** — append to `FIELDS` in `swingbot/config.py` (new section, after the last existing section):

```python
    # --- Gatekeeper ---
    Field("GATE_ENABLED", "GATE_ENABLED", "Gatekeeper", "Gate enabled (master switch)",
          type="checkbox", default="false",
          help="Master switch for the pre-trade checklist engine. Off = no gate code runs anywhere."),
    Field("GATE_MODE", "GATE_MODE", "Gatekeeper", "Gate mode",
          type="select", default="inform", options=["shadow", "inform", "enforce"],
          help="shadow: evaluate + log only, alerts unchanged. inform (default): the full checklist is "
               "rendered on every alert and nothing is ever blocked. enforce: opt-in blocking below "
               "'Min tier' — guarded by fold + shadow evidence (see the targets doc); never the default."),
    Field("GATE_MIN_TIER", "GATE_MIN_TIER", "Gatekeeper", "Min tier (enforce mode only)",
          type="select", default="C", options=["A+", "A", "B", "C"],
          help="Consulted ONLY in enforce mode: candidates below this tier are held back. "
               "At the default C nothing is ever blocked by tier."),
    Field("GATE_STRICTNESS", "GATE_STRICTNESS", "Gatekeeper", "Strictness preset",
          type="select", default="balanced", options=["strict", "balanced", "relaxed"],
          help="One-click reseed of every checklist threshold (see /gate). relaxed is deliberately "
               "generous so plans always flow; strict is the A+-hunting profile. Thresholds you have "
               "individually overridden survive a preset switch."),
    Field("MACRO_ENABLED", "MACRO_ENABLED", "Gatekeeper", "Macro context enabled",
          type="checkbox", default="false",
          help="Refresh the macro snapshot (news, sentiment, CPI/PPI/PCE, yields, VIX, sectors, "
               "breadth) before every scan and render the market-context field on alerts."),
    Field("FRED_API_KEY", "FRED_API_KEY", "Gatekeeper", "FRED API key",
          type="password", sensitive=True,
          help="Free key: https://fred.stlouisfed.org/docs/api/api_key.html. Empty = FRED-backed "
               "series degrade to 'unknown'; scanning is never affected."),
    Field("MACRO_SNAPSHOT_TTL_MIN", "MACRO_SNAPSHOT_TTL_MIN", "Gatekeeper", "Snapshot TTL (minutes)",
          type="number", default="30", min=5, step=5,
          help="A macro snapshot younger than this is reused; older triggers a rebuild before the scan."),
    Field("GATE_BLACKOUT_ENABLED", "GATE_BLACKOUT_ENABLED", "Gatekeeper", "Event blackout annotations",
          type="checkbox", default="false",
          help="Annotate alerts that fall inside a high-impact event window (CPI/NFP/FOMC). "
               "Annotate-only: actually holding entries additionally requires GATE_BLACKOUT_ENFORCE."),
```

**Conditional:** if llm-advisor L10 is unmerged at execution time (check: `grep FINNHUB_API_KEY swingbot/config.py`), also add with the same shape:

```python
    Field("FINNHUB_API_KEY", "FINNHUB_API_KEY", "Gatekeeper", "Finnhub API key",
          type="password", sensitive=True,
          help="Free key: https://finnhub.io/register. Powers news, sentiment, and the earnings "
               "calendar. Empty = those sections degrade to 'unknown'."),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gate_config.py -v`
Expected: 4 passed

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/config.py tests/test_gate_config.py
git commit -m "feat: Gatekeeper config section (default off)"
```

### Task G4: Gate result types

**Files:**
- Create: `swingbot/core/gate/types.py`
- Test: `tests/test_gate_types.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class CheckResult:
    check_id: str          # e.g. "htf_trend", "rf_fake_breakout"
    section: str           # "context" | "setup" | "redflag" | "risk" | "timing"
    status: str            # "pass" | "warn" | "fail" | "unknown"
    weight: float          # scoring weight, 0 for pure-info checks
    detail: str            # one human sentence, embed-ready
    evidence: dict         # raw numbers the detail cites

@dataclass(frozen=True)
class GateResult:
    ticker: str
    strategy: str
    as_of: str                     # ISO date of the signal bar
    checks: tuple[CheckResult, ...]
    score: float                   # 0-100 (G6)
    tier: str                      # "A+" | "A" | "B" | "C"
    hard_blocks: tuple[str, ...]   # check_ids that force C regardless of score
    macro_stale: bool              # snapshot older than TTL at eval time
    def to_dict(self) -> dict: ...           # JSON-safe, round-trips
    @classmethod
    def from_dict(cls, d: dict) -> "GateResult": ...
```

- `status="unknown"` (provider down / not computable) never counts against the score — it excludes the check's weight from the denominator. This rule is THE degradation contract; test it here.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_types.py
import dataclasses
import json

import pytest

from swingbot.core.gate.types import CheckResult, GateResult, scoreable


def _check(status="pass", check_id="htf_alignment", weight=10.0):
    return CheckResult(check_id=check_id, section="context", status=status,
                       weight=weight, detail="ok", evidence={"x": 1})


def _result():
    return GateResult(
        ticker="NVDA", strategy="Break & Retest", as_of="2026-07-14",
        checks=(_check(), _check(status="unknown", check_id="rf_rumor_spike")),
        score=87.5, tier="A", hard_blocks=(), macro_stale=False,
    )


def test_round_trip_through_json():
    r = _result()
    restored = GateResult.from_dict(json.loads(json.dumps(r.to_dict())))
    assert restored == r


def test_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _result().tier = "C"
    with pytest.raises(dataclasses.FrozenInstanceError):
        _check().status = "fail"


def test_scoreable_excludes_unknown():
    checks = [_check("pass"), _check("warn"), _check("fail"), _check("unknown")]
    assert [c.status for c in scoreable(checks)] == ["pass", "warn", "fail"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gate_types.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError` (types module missing)

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/gate/types.py
"""Result dataclasses shared by every gate module. Pure — no I/O, no config."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class CheckResult:
    check_id: str          # e.g. "htf_trend", "rf_fake_breakout"
    section: str           # "context" | "setup" | "redflag" | "risk" | "timing"
    status: str            # "pass" | "warn" | "fail" | "unknown"
    weight: float          # scoring weight, 0 for pure-info checks
    detail: str            # one human sentence, embed-ready
    evidence: dict = field(default_factory=dict)   # raw numbers the detail cites


def scoreable(checks: Sequence[CheckResult]) -> list[CheckResult]:
    """THE degradation contract: status='unknown' (provider down / not
    computable) is excluded entirely — its weight never enters the
    denominator, so missing data can only widen uncertainty, never
    penalize a candidate."""
    return [c for c in checks if c.status in ("pass", "warn", "fail")]


@dataclass(frozen=True)
class GateResult:
    ticker: str
    strategy: str
    as_of: str                     # ISO date of the signal bar
    checks: tuple[CheckResult, ...]
    score: float                   # 0-100 (G6)
    tier: str                      # "A+" | "A" | "B" | "C"
    hard_blocks: tuple[str, ...]   # check_ids that force C regardless of score
    macro_stale: bool              # snapshot older than TTL at eval time
    advisory_decision: str = "pass"  # what enforce WOULD do — set by decide() (G76)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["checks"] = [asdict(c) for c in self.checks]
        d["hard_blocks"] = list(self.hard_blocks)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GateResult":
        return cls(
            ticker=d["ticker"], strategy=d["strategy"], as_of=d["as_of"],
            checks=tuple(CheckResult(**c) for c in d.get("checks", [])),
            score=float(d["score"]), tier=d["tier"],
            hard_blocks=tuple(d.get("hard_blocks", ())),
            macro_stale=bool(d.get("macro_stale", False)),
            advisory_decision=d.get("advisory_decision", "pass"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gate_types.py -v`
Expected: 3 passed

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/types.py tests/test_gate_types.py
git commit -m "feat: gate result types"
```

### Task G5: Check registry + policy table

**Files:**
- Create: `swingbot/core/gate/registry.py`
- Test: `tests/test_gate_registry.py`

**Interfaces:**
- Produces: `CHECKS: dict[str, CheckSpec]` — `CheckSpec(check_id, section, weight, hard_block: bool, applies_to: tuple[str,...] | None, backtestable: bool, config_flag: str, thresholds: dict[str, ThresholdSpec])` where `ThresholdSpec(name, default, min, max, step, relax_direction: str, presets: dict[str, float])` (`presets` carries the strict/balanced/relaxed values; `relax_direction` is the help-text sentence, e.g. "raise to allow later entries"). Check functions read thresholds via `spec.threshold(name)` (config-Field-backed, G79) — never module constants; one entry per check built in Phases G1–G2 (registered incrementally — each later task adds its row and this module's test asserts registry consistency: unique ids, sections valid, weights ≥ 0, every `config_flag` exists in `config.FIELDS`). `applies_to=None` = all strategies. `enabled_checks(strategy) -> list[CheckSpec]`.
- Hard-block policy: `hard_block=True` checks (news whipsaw inside blackout, kill-switch conflict, unconfirmed signal bar) force tier C on `fail` even at score 100.

**Registration convention used by every Phase-G2 check task:** checks call `register(check_id=..., section=..., weight=..., func=..., thresholds={...})` at module import time; `config_flag` is derived automatically as `GATE_CHECK_<ID>`. The per-check enable Fields and per-threshold Fields are *generated* in G79 — until then `enabled_checks` treats a missing flag attr as True, and the "every config_flag exists in config.FIELDS" invariant is asserted from G79's test onward (not here — the fields don't exist yet).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_registry.py
import pytest

import swingbot.config as config
from swingbot.core.gate import registry
from swingbot.core.gate.registry import ThresholdSpec
from swingbot.core.gate.types import CheckResult


def _dummy_check(df_daily, plan, macro_snap, **ctx):
    return CheckResult("dummy", "context", "pass", 1.0, "ok", {})


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    monkeypatch.setattr(registry, "CHECKS", {})
    yield


def _th(name="rr_min", default=1.5):
    return ThresholdSpec(name, default, 1.0, 3.0, 0.1,
                         "lower to accept slimmer targets",
                         presets={"strict": 2.0, "balanced": default, "relaxed": 1.2})


def test_register_derives_flag_and_rejects_duplicates():
    spec = registry.register(check_id="dummy", section="context", weight=5.0, func=_dummy_check)
    assert registry.CHECKS["dummy"] is spec
    assert spec.config_flag == "GATE_CHECK_DUMMY"
    with pytest.raises(ValueError):
        registry.register(check_id="dummy", section="context", weight=5.0, func=_dummy_check)


def test_validate_registry_invariants():
    registry.register(check_id="ok", section="setup", weight=1.0, func=_dummy_check,
                      thresholds={"rr_min": _th()})
    registry.validate_registry()  # no raise
    bad = registry.CHECKS["ok"].__class__(
        check_id="bad", section="not_a_section", weight=1.0,
        func=_dummy_check, config_flag="GATE_CHECK_BAD")
    registry.CHECKS["bad"] = bad
    with pytest.raises(AssertionError):
        registry.validate_registry()


def test_enabled_checks_filters_strategy_and_flag(monkeypatch):
    registry.register(check_id="allstrats", section="context", weight=1.0, func=_dummy_check)
    registry.register(check_id="breakout_only", section="redflag", weight=1.0,
                      func=_dummy_check, applies_to=("Break & Retest",))
    assert [s.check_id for s in registry.enabled_checks("RSI Divergence")] == ["allstrats"]
    assert [s.check_id for s in registry.enabled_checks("Break & Retest")] == [
        "allstrats", "breakout_only"]
    monkeypatch.setattr(config, "GATE_CHECK_ALLSTRATS", False, raising=False)
    assert [s.check_id for s in registry.enabled_checks("RSI Divergence")] == []


def test_threshold_resolves_config_field_then_spec_default(monkeypatch):
    spec = registry.register(check_id="th", section="setup", weight=1.0,
                             func=_dummy_check, thresholds={"rr_min": _th()})
    assert spec.threshold("rr_min") == 1.5           # no Field yet -> spec default
    monkeypatch.setattr(config, "GATE_TH_TH_RR_MIN", 1.8, raising=False)
    assert spec.threshold("rr_min") == 1.8           # Field wins
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gate_registry.py -v`
Expected: FAIL with `ImportError` (registry module missing)

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/gate/registry.py
"""Check registry + policy table.

Check modules (Phase G2) register themselves at import time via
register(); this module owns the invariants. Hard-block policy:
hard_block=True checks force tier C on `fail` even at score 100
(enforced by score.assign_tier via the hard_blocks list the
orchestrator assembles in G75).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import swingbot.config as config

SECTIONS = ("context", "setup", "redflag", "risk", "timing")
PRESET_LEVELS = ("strict", "balanced", "relaxed")


@dataclass(frozen=True)
class ThresholdSpec:
    name: str
    default: float          # the *balanced* value
    min: float
    max: float
    step: float
    relax_direction: str    # help-text sentence, e.g. "raise to allow later entries"
    presets: dict           # {"strict": x, "balanced": y, "relaxed": z}


@dataclass(frozen=True)
class CheckSpec:
    check_id: str
    section: str
    weight: float
    func: Callable          # (df_daily, plan, macro_snap, **ctx) -> CheckResult
    hard_block: bool = False
    applies_to: tuple | None = None   # exact ALL_STRATEGIES names; None = all
    backtestable: bool = True         # finalized in G89
    trigger_recheck: bool = False     # cheap re-check subset (G128)
    config_flag: str = ""             # GATE_CHECK_<ID>, derived by register()
    thresholds: dict = field(default_factory=dict)   # name -> ThresholdSpec

    def threshold(self, name: str) -> float:
        """Config-Field-backed threshold lookup. The Field
        GATE_TH_{CHECK_ID}_{NAME} is generated in G79; until it exists
        the spec's balanced default applies. Check functions must use
        this — never module constants."""
        spec = self.thresholds[name]
        attr = f"GATE_TH_{self.check_id.upper()}_{name.upper()}"
        return float(getattr(config, attr, spec.default))


CHECKS: dict[str, CheckSpec] = {}


def register(**kw) -> CheckSpec:
    kw.setdefault("config_flag", f"GATE_CHECK_{kw['check_id'].upper()}")
    spec = CheckSpec(**kw)
    if spec.check_id in CHECKS:
        raise ValueError(f"duplicate check id {spec.check_id!r}")
    CHECKS[spec.check_id] = spec
    return spec


def validate_registry() -> None:
    """Invariants asserted by tests after every registration task."""
    for spec in CHECKS.values():
        assert spec.section in SECTIONS, f"{spec.check_id}: bad section {spec.section}"
        assert spec.weight >= 0, f"{spec.check_id}: negative weight"
        assert spec.config_flag == f"GATE_CHECK_{spec.check_id.upper()}", spec.check_id
        for th in spec.thresholds.values():
            assert th.min <= th.default <= th.max, f"{spec.check_id}.{th.name}"
            assert set(th.presets) == set(PRESET_LEVELS), f"{spec.check_id}.{th.name}"


def enabled_checks(strategy: str) -> list[CheckSpec]:
    out = []
    for spec in CHECKS.values():
        if spec.applies_to is not None and strategy not in spec.applies_to:
            continue
        if not getattr(config, spec.config_flag, True):   # Field generated in G79
            continue
        out.append(spec)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gate_registry.py -v`
Expected: 4 passed

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/registry.py tests/test_gate_registry.py
git commit -m "feat: gate check registry + policy"
```

### Task G6: Checklist score + tier assignment

**Files:**
- Create: `swingbot/core/gate/score.py`
- Test: `tests/test_gate_score.py`

**Interfaces:**
- Produces: `score(checks: Sequence[CheckResult]) -> float` — weighted: pass=1.0, warn=0.5, fail=0.0, unknown excluded from denominator; empty/all-unknown → 50.0 (neutral) with `macro_stale` responsibility on the caller. `assign_tier(score: float, hard_blocks: Sequence[str], *, aplus_cut: float, a_cut: float, b_cut: float) -> str` — cuts come from config (G79); any hard block → "C". `TIER_ORDER = ("A+", "A", "B", "C")`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_score.py
from swingbot.core.gate.score import assign_tier, score
from swingbot.core.gate.types import CheckResult


def _c(status, weight, cid="c"):
    return CheckResult(cid, "setup", status, weight, "", {})


def test_golden_mixed_score():
    # (10*1 + 10*1 + 10*0.5 + 20*0 = 25) / 40 * 100 = 62.5 — unknown w=50 excluded
    checks = [_c("pass", 10, "a"), _c("pass", 10, "b"), _c("warn", 10, "w"),
              _c("fail", 20, "f"), _c("unknown", 50, "u")]
    assert score(checks) == 62.5


def test_all_unknown_or_empty_is_neutral_50():
    assert score([_c("unknown", 10), _c("unknown", 20)]) == 50.0
    assert score([]) == 50.0


def test_zero_weight_checks_are_info_only():
    assert score([_c("fail", 0, "info"), _c("pass", 10, "real")]) == 100.0


def test_hard_block_forces_c_even_at_100():
    assert assign_tier(100.0, ["signal_confirmed"],
                       aplus_cut=90.0, a_cut=75.0, b_cut=55.0) == "C"


def test_tier_cut_boundaries():
    kw = dict(aplus_cut=90.0, a_cut=75.0, b_cut=55.0)
    assert assign_tier(95.0, [], **kw) == "A+"
    assert assign_tier(90.0, [], **kw) == "A+"   # cuts are inclusive
    assert assign_tier(80.0, [], **kw) == "A"
    assert assign_tier(60.0, [], **kw) == "B"
    assert assign_tier(54.9, [], **kw) == "C"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gate_score.py -v`
Expected: FAIL with `ImportError` (score module missing)

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/gate/score.py
"""Checklist score 0-100 + tier ladder. Pure functions — cuts arrive as
arguments (resolved from config Fields by the G75 orchestrator)."""
from __future__ import annotations

from typing import Sequence

from swingbot.core.gate.types import CheckResult, scoreable

TIER_ORDER = ("A+", "A", "B", "C")
_STATUS_CREDIT = {"pass": 1.0, "warn": 0.5, "fail": 0.0}


def score(checks: Sequence[CheckResult]) -> float:
    """Weighted score: pass=1.0, warn=0.5, fail=0.0; unknown excluded from
    the denominator (types.scoreable). Nothing scoreable -> neutral 50.0;
    the caller carries macro_stale responsibility."""
    scored = [c for c in scoreable(checks) if c.weight > 0]
    denom = sum(c.weight for c in scored)
    if denom == 0:
        return 50.0
    got = sum(c.weight * _STATUS_CREDIT[c.status] for c in scored)
    return round(got / denom * 100.0, 2)


def assign_tier(score: float, hard_blocks: Sequence[str], *,
                aplus_cut: float, a_cut: float, b_cut: float) -> str:
    """Any hard block -> C regardless of score; otherwise inclusive cuts."""
    if hard_blocks:
        return "C"
    if score >= aplus_cut:
        return "A+"
    if score >= a_cut:
        return "A"
    if score >= b_cut:
        return "B"
    return "C"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gate_score.py -v`
Expected: 5 passed

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/score.py tests/test_gate_score.py
git commit -m "feat: checklist scoring + tier ladder"
```

### Task G7: Golden OHLCV scenario fixture library

**Files:**
- Create: `tests/fixtures/gate/__init__.py` (builders), `tests/fixtures/gate/scenarios.py`
- Test: `tests/test_gate_fixtures.py`

**Interfaces:**
- Produces deterministic bar-series builders reused by every detector test (extends `tests/conftest.py`'s real `make_ohlcv(closes, spread_pct, ...)` — verify its actual signature before writing): `uptrend_daily(n=260)`, `downtrend_daily(n=260)`, `range_daily(lo, hi, n=120)`, `breakout_and_fail(level)` (closes back inside next bar, low volume), `sweep_wick(level)` (long lower wick through level, close back above), `dead_cat(n_down=40, bounce_pct=8)` (no higher-low structure), `climax_overbought()` (RSI>75 into resistance), `gap_spike(pct=12)` (news-gap bar, volume 5×), plus weekly resamples `to_weekly(df)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_fixtures.py
from swingbot.core.indicators import rsi
from tests.fixtures.gate import (
    breakout_and_fail, climax_overbought, dead_cat, downtrend_daily,
    gap_spike, range_daily, sweep_wick, to_weekly, uptrend_daily,
)


def test_trend_slopes():
    up, down = uptrend_daily(), downtrend_daily()
    assert up["Close"].iloc[-1] > up["Close"].iloc[0] * 1.5
    assert down["Close"].iloc[-1] < down["Close"].iloc[0] * 0.6
    rng = range_daily(90, 110)
    assert rng["Close"].min() > 85 and rng["Close"].max() < 115


def test_breakout_and_fail_geometry():
    df = breakout_and_fail(level=100.0)
    assert df["Close"].iloc[-2] > 100.0                 # broke out...
    assert df["Close"].iloc[-1] < 100.0                 # ...failed back inside next bar
    assert df["Volume"].iloc[-2] < df["Volume"].iloc[:-2].mean()   # on dead volume


def test_sweep_wick_geometry():
    df = sweep_wick(level=100.0)
    bar = df.iloc[-2]
    body = abs(bar["Close"] - bar["Open"])
    lower_wick = min(bar["Close"], bar["Open"]) - bar["Low"]
    assert bar["Low"] < 100.0 < bar["Close"]            # swept through, closed back above
    assert lower_wick >= 1.5 * body


def test_dead_cat_geometry():
    df = dead_cat(bounce_pct=8.0)
    recent_low = df["Close"].iloc[-25:].min()
    assert df["Close"].iloc[-1] >= recent_low * 1.05    # >=5% bounce off a recent low
    assert df["Close"].iloc[-1] < df["Close"].iloc[0]   # still deep below the old range


def test_climax_overbought_rsi():
    assert rsi(climax_overbought()["Close"]).iloc[-1] > 75


def test_gap_spike_geometry():
    df = gap_spike(pct=12.0)
    assert df["Close"].iloc[-1] / df["Close"].iloc[-2] >= 1.10
    assert df["Volume"].iloc[-1] >= 4 * df["Volume"].iloc[:-1].mean()


def test_to_weekly_shape():
    wk = to_weekly(uptrend_daily(260))
    assert 45 <= len(wk) <= 60
    assert (wk["High"] >= wk["Low"]).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gate_fixtures.py -v`
Expected: FAIL with `ImportError` (fixtures package missing)

- [ ] **Step 3: Write the implementation** (if `tests/fixtures/__init__.py` doesn't exist yet, create it empty)

```python
# tests/fixtures/gate/scenarios.py
"""Deterministic OHLCV scenario builders for gate detector tests.

All return daily frames in the repo convention (Open,High,Low,Close,Volume,
DatetimeIndex) built on tests.conftest.make_ohlcv — verify its signature is
still make_ohlcv(closes, spread_pct=1.0, volumes=None, start="2019-01-01")
before extending. make_ohlcv sets Open = prior close and symmetric H/L
around the close; builders that need asymmetric bars (wicks, gaps) patch
individual cells afterwards.
"""
import numpy as np
import pandas as pd

from tests.conftest import make_ohlcv

BASE_VOL = 1_000_000.0


def uptrend_daily(n=260, start_price=100.0, daily_pct=0.4):
    closes = start_price * (1 + daily_pct / 100) ** np.arange(n)
    return make_ohlcv(closes, spread_pct=2.0)


def downtrend_daily(n=260, start_price=100.0, daily_pct=0.4):
    closes = start_price * (1 - daily_pct / 100) ** np.arange(n)
    return make_ohlcv(closes, spread_pct=2.0)


def range_daily(lo=90.0, hi=110.0, n=120):
    mid, amp = (lo + hi) / 2.0, (hi - lo) / 2.0
    closes = mid + amp * np.sin(np.arange(n) * 2 * np.pi / 20)
    return make_ohlcv(closes, spread_pct=1.5)


def breakout_and_fail(level=100.0, n=80):
    """Grind up to the level, close above it on DEAD volume, close back
    inside the next bar — the rf_fake_breakout golden scenario."""
    closes = np.concatenate([
        np.linspace(level * 0.90, level * 0.99, n - 2),
        [level * 1.02],      # breakout close above the level...
        [level * 0.985],     # ...next bar closes back inside
    ])
    volumes = np.full(n, BASE_VOL)
    volumes[-2] = BASE_VOL * 0.6
    return make_ohlcv(closes, spread_pct=1.5, volumes=volumes)


def sweep_wick(level=100.0, n=60):
    """Long lower wick through the level with a close back above, then a
    no-follow-through bar — the rf_stop_sweep golden scenario."""
    closes = np.linspace(level * 1.08, level * 1.01, n)
    df = make_ohlcv(closes, spread_pct=1.0)
    sweep = df.index[-2]
    df.loc[sweep, "Open"] = level * 1.010
    df.loc[sweep, "Close"] = level * 1.005          # body 0.5
    df.loc[sweep, "Low"] = level * 0.970            # wick 3.5 -> ratio 7x
    last = df.index[-1]
    df.loc[last, "Close"] = level * 1.004           # no follow-through
    df.loc[last, "High"] = level * 1.012
    return df


def dead_cat(n_down=40, bounce_pct=8.0, start_price=150.0):
    """Flat lead-in (history for 250-bar lookbacks), -1%/day grind, then a
    V-bounce with no higher-low structure — the rf_dead_cat golden scenario."""
    lead_in = np.full(220, start_price)
    down = start_price * (1 - 0.01) ** np.arange(n_down)
    low = down[-1]
    bounce = np.linspace(low, low * (1 + bounce_pct / 100), 6)
    closes = np.concatenate([lead_in, down, bounce[1:]])
    return make_ohlcv(closes, spread_pct=2.0)


def climax_overbought(n=120, level=120.0):
    """30-bar blow-off into resistance; RSI(14) finishes > 75."""
    closes = np.concatenate([np.linspace(90, 100, n - 30),
                             np.linspace(100, level, 30)])
    return make_ohlcv(closes, spread_pct=1.5)


def gap_spike(pct=12.0, n=80):
    """Flat series, last bar +pct% close-to-close on 5x volume — the
    rf_rumor_spike geometry scenario."""
    closes = np.full(n, 100.0)
    closes[-1] = 100.0 * (1 + pct / 100)
    volumes = np.full(n, BASE_VOL)
    volumes[-1] = BASE_VOL * 5
    return make_ohlcv(closes, spread_pct=1.0, volumes=volumes)


def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Open": df["Open"].resample("W-FRI").first(),
        "High": df["High"].resample("W-FRI").max(),
        "Low": df["Low"].resample("W-FRI").min(),
        "Close": df["Close"].resample("W-FRI").last(),
        "Volume": df["Volume"].resample("W-FRI").sum(),
    }).dropna()
```

```python
# tests/fixtures/gate/__init__.py
from tests.fixtures.gate.scenarios import (   # noqa: F401
    BASE_VOL, breakout_and_fail, climax_overbought, dead_cat,
    downtrend_daily, gap_spike, range_daily, sweep_wick, to_weekly,
    uptrend_daily,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gate_fixtures.py -v`
Expected: 7 passed

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add tests/fixtures/gate/ tests/test_gate_fixtures.py
git commit -m "test: golden gate scenario fixtures"
```

### Task G8: Phase G0 checkpoint

- [ ] **Step 1:** Full suite green: `python -m pytest tests/ -q` + `make check`.
- [ ] **Step 2:** Update the Progress block (Completed: G1–G8, Next: G9). Commit — `chore: phase G0 checkpoint`

---

# Phase G1 — Macro data layer: news, sentiment, rotation, CPI/PPI, treasury (G9–G44)

Everything here is read-only market context. Each provider: 5s timeout, TTL disk cache, `None`-on-failure, no network in tests.

### Task G9: HTTP fetch + TTL disk cache

**Files:**
- Create: `swingbot/core/macro/__init__.py`, `swingbot/core/macro/httpcache.py`
- Test: `tests/test_macro_httpcache.py`

**Interfaces:**
- Produces: `fetch_json(url, *, params=None, ttl_s=3600, timeout_s=5.0, cache_key=None) -> dict | list | None` — key = sha1 of url+sorted params unless given; cache files `data/macro/cache/{key}.json` via `jsonio` storing `{fetched_at, payload}`; fresh cache → no network; expired cache + fetch failure → **stale payload returned** with module-level `LAST_SERVED_STALE` flag set (snapshot marks `macro_stale`); no cache + failure → None. `purge_cache(max_age_days=30) -> int`.
- Consumed by: every provider below.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_httpcache.py
import os
import time

import pytest

import swingbot.core.macro.httpcache as httpcache


class _Resp:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(httpcache, "CACHE_DIR", str(tmp_path))
    httpcache.LAST_SERVED_STALE = False
    return tmp_path


def _counting_get(payload):
    calls = {"n": 0}
    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        return _Resp(payload)
    return fake_get, calls


def test_fresh_cache_skips_network(cache_dir, monkeypatch):
    fake_get, calls = _counting_get({"v": 1})
    monkeypatch.setattr(httpcache.requests, "get", fake_get)
    assert httpcache.fetch_json("https://x.test/a", ttl_s=3600) == {"v": 1}
    assert httpcache.fetch_json("https://x.test/a", ttl_s=3600) == {"v": 1}
    assert calls["n"] == 1


def test_expired_cache_refetches(cache_dir, monkeypatch):
    fake_get, calls = _counting_get({"v": 1})
    monkeypatch.setattr(httpcache.requests, "get", fake_get)
    httpcache.fetch_json("https://x.test/a", ttl_s=0)
    httpcache.fetch_json("https://x.test/a", ttl_s=0)
    assert calls["n"] == 2


def test_failure_serves_stale_and_flags(cache_dir, monkeypatch):
    fake_get, _ = _counting_get({"v": 1})
    monkeypatch.setattr(httpcache.requests, "get", fake_get)
    httpcache.fetch_json("https://x.test/a", ttl_s=0)
    def boom(url, params=None, timeout=None):
        raise OSError("network down")
    monkeypatch.setattr(httpcache.requests, "get", boom)
    assert httpcache.fetch_json("https://x.test/a", ttl_s=0) == {"v": 1}
    assert httpcache.LAST_SERVED_STALE is True


def test_failure_without_cache_returns_none(cache_dir, monkeypatch):
    def boom(url, params=None, timeout=None):
        raise OSError("network down")
    monkeypatch.setattr(httpcache.requests, "get", boom)
    assert httpcache.fetch_json("https://x.test/never") is None


def test_secret_params_never_reach_filenames(cache_dir, monkeypatch):
    fake_get, _ = _counting_get({"v": 1})
    monkeypatch.setattr(httpcache.requests, "get", fake_get)
    httpcache.fetch_json("https://x.test/a", params={"api_key": "SECRET123"})
    names = "".join(os.listdir(cache_dir))
    assert "SECRET123" not in names            # keys are sha1-hashed (G201 contract)


def test_purge_removes_only_old(cache_dir, monkeypatch):
    fake_get, _ = _counting_get({"v": 1})
    monkeypatch.setattr(httpcache.requests, "get", fake_get)
    httpcache.fetch_json("https://x.test/old")
    httpcache.fetch_json("https://x.test/new")
    old_file = sorted(cache_dir.iterdir())[0]
    past = time.time() - 40 * 86400
    os.utime(old_file, (past, past))
    assert httpcache.purge_cache(max_age_days=30) == 1
    assert len(list(cache_dir.iterdir())) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_macro_httpcache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.core.macro'`

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/__init__.py
"""Macro context layer — read-only market data. Public API re-exports
grow as modules land; snapshot.build_snapshot (G38) is the main entry."""
```

```python
# swingbot/core/macro/httpcache.py
"""fetch_json(): HTTP GET with a TTL disk cache under data/macro/cache/.

Degradation ladder (the contract every provider inherits):
  fresh cache            -> served, no network
  expired + fetch ok     -> refreshed
  expired + fetch FAIL   -> stale payload served, LAST_SERVED_STALE set
  no cache + fetch FAIL  -> None
Never raises toward a caller.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time

import requests

from swingbot import config
from swingbot.core.jsonio import atomic_write_json, read_json  # cockpit-v3 A1 — verify signature at execution

log = logging.getLogger("swing-bot.macro.httpcache")

CACHE_DIR = os.path.join(config.DATA_DIR, "macro", "cache")

# Set whenever an expired-but-cached payload was served because the
# network failed; the snapshot builder (G38) reads and resets it.
LAST_SERVED_STALE = False


def _cache_key(url: str, params: dict | None) -> str:
    # sha1 of url+sorted params: api_key/token values never appear in
    # filenames in readable form (G201 secrets contract).
    blob = url + "|" + json.dumps(sorted((params or {}).items()))
    return hashlib.sha1(blob.encode()).hexdigest()


def fetch_json(url, *, params=None, ttl_s=3600, timeout_s=5.0, cache_key=None):
    global LAST_SERVED_STALE
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = cache_key or _cache_key(url, params)
    path = os.path.join(CACHE_DIR, f"{key}.json")
    cached = read_json(path, default=None)
    now = time.time()
    if cached is not None and now - cached.get("fetched_at", 0) < ttl_s:
        return cached["payload"]
    try:
        resp = requests.get(url, params=params, timeout=timeout_s)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001 — every failure degrades, never raises
        # Log the exception TYPE and the bare path only — params (which
        # carry api keys) and query strings are never logged (G201).
        log.warning("macro fetch failed (%s): %s", type(exc).__name__, url.split("?")[0])
        if cached is not None:
            LAST_SERVED_STALE = True
            return cached["payload"]
        return None
    atomic_write_json(path, {"fetched_at": now, "payload": payload})
    return payload


def purge_cache(max_age_days: int = 30) -> int:
    """Remove cache files older than max_age_days; returns count removed."""
    if not os.path.isdir(CACHE_DIR):
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for name in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, name)
        if os.path.getmtime(path) < cutoff:
            os.remove(path)
            removed += 1
    return removed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_macro_httpcache.py -v`
Expected: 6 passed

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/ tests/test_macro_httpcache.py
git commit -m "feat: macro http fetch with TTL disk cache + stale fallback"
```

### Task G10: Provider health ledger

**Files:**
- Create: `swingbot/core/macro/health.py`
- Test: `tests/test_macro_health.py`

**Interfaces:**
- Produces: `record_call(provider: str, ok: bool, latency_ms: float, from_cache: bool)` → appends `data/macro/health.jsonl`; `provider_status() -> dict[str, dict]` (`{ok_rate_24h, last_ok, last_error, calls_today, cache_hit_rate}`); `is_degraded(provider) -> bool` (ok_rate_24h < 0.5). Wired into `fetch_json` via a `provider=` kwarg (modify G9's signature now, one place).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_health.py
import time

import pytest

import swingbot.core.macro.health as health
import swingbot.core.macro.httpcache as httpcache


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(health, "LEDGER_PATH", str(tmp_path / "health.jsonl"))
    return tmp_path


def test_status_math(ledger):
    for ok in (True, True, False):
        health.record_call("fred", ok=ok, latency_ms=42.0, from_cache=False)
    health.record_call("fred", ok=True, latency_ms=0.0, from_cache=True)
    s = health.provider_status()["fred"]
    assert s["ok_rate_24h"] == pytest.approx(2 / 3)
    assert s["calls_today"] == 3                       # cache hits aren't calls
    assert s["cache_hit_rate"] == pytest.approx(1 / 4)
    assert s["last_ok"] is not None and s["last_error"] is not None
    assert not health.is_degraded("fred")


def test_degraded_flip(ledger):
    for _ in range(3):
        health.record_call("finnhub", ok=False, latency_ms=10.0, from_cache=False)
    health.record_call("finnhub", ok=True, latency_ms=10.0, from_cache=False)
    assert health.is_degraded("finnhub")               # ok_rate 0.25 < 0.5


def test_fetch_json_records(tmp_path, ledger, monkeypatch):
    monkeypatch.setattr(httpcache, "CACHE_DIR", str(tmp_path / "cache"))

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"v": 1}

    monkeypatch.setattr(httpcache.requests, "get", lambda *a, **k: _Resp())
    httpcache.fetch_json("https://x.test/a", provider="fred")
    assert health.provider_status()["fred"]["calls_today"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_macro_health.py -v`
Expected: FAIL with `ImportError` (health module missing)

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/health.py
"""Provider health ledger — one JSONL line per call attempt (incl. cache hits)."""
from __future__ import annotations

import json
import os
import time

from swingbot import config

LEDGER_PATH = os.path.join(config.DATA_DIR, "macro", "health.jsonl")


def record_call(provider: str, ok: bool, latency_ms: float, from_cache: bool) -> None:
    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    line = {"ts": time.time(), "provider": provider, "ok": ok,
            "latency_ms": round(latency_ms, 1), "from_cache": from_cache}
    with open(LEDGER_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")


def _lines(since_s: float | None = None) -> list[dict]:
    if not os.path.exists(LEDGER_PATH):
        return []
    cutoff = (time.time() - since_s) if since_s else 0.0
    out = []
    with open(LEDGER_PATH, encoding="utf-8") as fh:
        for raw in fh:
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if row.get("ts", 0) >= cutoff:
                out.append(row)
    return out


def provider_status() -> dict[str, dict]:
    day = _lines(24 * 3600)
    out: dict[str, dict] = {}
    for provider in {r["provider"] for r in day if r.get("provider")}:
        rows = [r for r in day if r["provider"] == provider]
        network = [r for r in rows if not r["from_cache"]]
        oks = [r for r in network if r["ok"]]
        fails = [r for r in network if not r["ok"]]
        out[provider] = {
            "ok_rate_24h": (len(oks) / len(network)) if network else 1.0,
            "last_ok": max((r["ts"] for r in oks), default=None),
            "last_error": max((r["ts"] for r in fails), default=None),
            "calls_today": len(network),
            "cache_hit_rate": sum(r["from_cache"] for r in rows) / len(rows),
        }
    return out


def is_degraded(provider: str) -> bool:
    status = provider_status().get(provider)
    return bool(status and status["ok_rate_24h"] < 0.5)
```

**And modify `fetch_json` (G9) — the one place every provider goes through** — add the `provider` kwarg + timing:

```python
# swingbot/core/macro/httpcache.py — fetch_json becomes:
def fetch_json(url, *, params=None, ttl_s=3600, timeout_s=5.0,
               cache_key=None, provider=None):
    global LAST_SERVED_STALE
    from swingbot.core.macro import health   # local import: no cycle at module load
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = cache_key or _cache_key(url, params)
    path = os.path.join(CACHE_DIR, f"{key}.json")
    cached = read_json(path, default=None)
    now = time.time()
    if cached is not None and now - cached.get("fetched_at", 0) < ttl_s:
        if provider:
            health.record_call(provider, ok=True, latency_ms=0.0, from_cache=True)
        return cached["payload"]
    t0 = time.time()
    try:
        resp = requests.get(url, params=params, timeout=timeout_s)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        if provider:
            health.record_call(provider, ok=False,
                               latency_ms=(time.time() - t0) * 1000, from_cache=False)
        log.warning("macro fetch failed (%s): %s", type(exc).__name__, url.split("?")[0])
        if cached is not None:
            LAST_SERVED_STALE = True
            return cached["payload"]
        return None
    if provider:
        health.record_call(provider, ok=True,
                           latency_ms=(time.time() - t0) * 1000, from_cache=False)
    atomic_write_json(path, {"fetched_at": now, "payload": payload})
    return payload
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_macro_health.py tests/test_macro_httpcache.py -v`
Expected: all passed (G9's tests must stay green — `provider` defaults to None)

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/health.py swingbot/core/macro/httpcache.py tests/test_macro_health.py
git commit -m "feat: provider health ledger"
```

### Task G11: Quota meter (free-tier budgets)

**Files:**
- Modify: `swingbot/core/macro/health.py`
- Test: `tests/test_macro_health.py`

**Interfaces:**
- Produces: `QUOTAS: dict[str, dict] = {"fred": {"per_minute": 60, "per_day": 5000}, "finnhub": {"per_minute": 50, "per_day": 3000}}` (soft caps under the published free-tier limits); `allow_call(provider, now=None) -> bool` from the ledger; `fetch_json` returns cached/stale/None without network when disallowed. Quota exhaustion is a WARN in health, never an exception.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_macro_health.py`)

```python
def test_quota_denies_next_finnhub_call_after_50_in_a_minute(ledger):
    for _ in range(50):
        health.record_call("finnhub", ok=True, latency_ms=5.0, from_cache=False)
    assert health.allow_call("finnhub") is False
    assert health.allow_call("fred") is True            # independent budgets


def test_day_rollover_resets(ledger):
    import json
    old = time.time() - 2 * 86400
    line = {"ts": old, "provider": "finnhub", "ok": True,
            "latency_ms": 5.0, "from_cache": False}
    with open(health.LEDGER_PATH, "a", encoding="utf-8") as fh:
        for _ in range(3000):
            fh.write(json.dumps(line) + "\n")
    assert health.allow_call("finnhub") is True         # yesterday doesn't count


def test_denied_call_serves_cache_not_network(tmp_path, ledger, monkeypatch):
    monkeypatch.setattr(httpcache, "CACHE_DIR", str(tmp_path / "cache"))

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"v": 1}

    calls = {"n": 0}
    def fake_get(*a, **k):
        calls["n"] += 1
        return _Resp()
    monkeypatch.setattr(httpcache.requests, "get", fake_get)
    httpcache.fetch_json("https://x.test/q", provider="finnhub")     # seeds cache
    monkeypatch.setattr(health, "allow_call", lambda p, now=None: False)
    assert httpcache.fetch_json("https://x.test/q", ttl_s=0, provider="finnhub") == {"v": 1}
    assert calls["n"] == 1                              # denied call never hit network
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_macro_health.py -v`
Expected: FAIL with `AttributeError: ... 'allow_call'`

- [ ] **Step 3: Write the implementation** (append to `swingbot/core/macro/health.py`)

```python
# Soft caps deliberately under the published free-tier limits.
QUOTAS: dict[str, dict] = {
    "fred": {"per_minute": 60, "per_day": 5000},
    "finnhub": {"per_minute": 50, "per_day": 3000},
}


def allow_call(provider: str, now: float | None = None) -> bool:
    """False when the next network call would breach a budget. Quota
    exhaustion is a WARN in health, never an exception."""
    quota = QUOTAS.get(provider)
    if quota is None:
        return True
    now = now if now is not None else time.time()
    day_key = time.strftime("%Y-%m-%d", time.gmtime(now))
    minute = day_count = 0
    for row in _lines():
        if row.get("provider") != provider or row.get("from_cache"):
            continue
        if row["ts"] > now - 60:
            minute += 1
        if time.strftime("%Y-%m-%d", time.gmtime(row["ts"])) == day_key:
            day_count += 1
    return minute < quota["per_minute"] and day_count < quota["per_day"]
```

**And in `fetch_json` (httpcache.py)**, insert the quota gate directly after the fresh-cache return, before any network:

```python
    if provider is not None and not health.allow_call(provider):
        log.warning("quota: %s call denied — serving cache/None, no network", provider)
        if cached is not None:
            LAST_SERVED_STALE = True
            return cached["payload"]
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_macro_health.py tests/test_macro_httpcache.py -v`
Expected: all passed

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/health.py swingbot/core/macro/httpcache.py tests/test_macro_health.py
git commit -m "feat: provider quota meter"
```

### Task G12: FRED client

**Files:**
- Create: `swingbot/core/macro/fred.py`
- Test: `tests/test_macro_fred.py`

**Interfaces:**
- Produces: `fred_series(series_id: str, *, start: str | None = None, ttl_s=6*3600) -> list[tuple[str, float]] | None` — GET `https://api.stlouisfed.org/fred/series/observations` with `api_key=config.FRED_API_KEY`, `file_type=json`, sorted ascending, `"."` observations skipped; empty key → None without network. `fred_release_dates(release_id: int, *, include_future=True) -> list[str]` (GET `/fred/releases/dates`). `latest(series_id) -> tuple[str, float] | None`; `yoy(series_id) -> float | None` (last vs value 12 monthly observations earlier).
- Consumed by: G13–G20, G30.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_fred.py
import pytest

import swingbot.config as config
import swingbot.core.macro.fred as fred

FIXTURE = {"observations": [
    {"date": "2025-05-01", "value": "310.5"},
    {"date": "2025-06-01", "value": "."},          # FRED's "no data" marker
    {"date": "2025-07-01", "value": "312.0"},
    {"date": "2024-07-01", "value": "300.0"},      # out of order on purpose
]}


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(config, "FRED_API_KEY", "test-key", raising=False)


def test_series_parses_sorted_and_skips_dots(with_key, monkeypatch):
    monkeypatch.setattr(fred, "fetch_json", lambda *a, **k: FIXTURE)
    assert fred.fred_series("CPIAUCSL") == [
        ("2024-07-01", 300.0), ("2025-05-01", 310.5), ("2025-07-01", 312.0)]


def test_latest(with_key, monkeypatch):
    monkeypatch.setattr(fred, "fetch_json", lambda *a, **k: FIXTURE)
    assert fred.latest("CPIAUCSL") == ("2025-07-01", 312.0)


def test_yoy_golden(with_key, monkeypatch):
    # 13 monthly observations: yoy = (last / value-12-obs-earlier - 1) * 100
    obs = [{"date": f"2025-{m:02d}-01", "value": str(100 + m)} for m in range(1, 13)]
    obs.append({"date": "2026-01-01", "value": "113.0"})
    monkeypatch.setattr(fred, "fetch_json", lambda *a, **k: {"observations": obs})
    assert fred.yoy("X") == pytest.approx((113.0 / 101.0 - 1) * 100)


def test_release_dates(with_key, monkeypatch):
    payload = {"release_dates": [{"release_id": 10, "date": "2026-07-15"},
                                 {"release_id": 10, "date": "2026-08-12"}]}
    monkeypatch.setattr(fred, "fetch_json", lambda *a, **k: payload)
    assert fred.fred_release_dates(10) == ["2026-07-15", "2026-08-12"]


def test_no_key_means_none_and_zero_network(monkeypatch):
    monkeypatch.setattr(config, "FRED_API_KEY", "", raising=False)
    def boom(*a, **k):
        raise AssertionError("network path must not be reached without a key")
    monkeypatch.setattr(fred, "fetch_json", boom)
    assert fred.fred_series("CPIAUCSL") is None
    assert fred.fred_release_dates(10) == []
    assert fred.yoy("CPIAUCSL") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_macro_fred.py -v`
Expected: FAIL with `ImportError` (fred module missing)

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/fred.py
"""FRED REST client. Empty API key -> None/[] without touching the network."""
from __future__ import annotations

from swingbot import config
from swingbot.core.macro.httpcache import fetch_json

BASE = "https://api.stlouisfed.org/fred"


def _key() -> str:
    return (getattr(config, "FRED_API_KEY", "") or "").strip()


def fred_series(series_id: str, *, start: str | None = None,
                ttl_s: int = 6 * 3600) -> list[tuple[str, float]] | None:
    if not _key():
        return None
    params = {"series_id": series_id, "api_key": _key(),
              "file_type": "json", "sort_order": "asc"}
    if start:
        params["observation_start"] = start
    data = fetch_json(f"{BASE}/series/observations", params=params,
                      ttl_s=ttl_s, provider="fred")
    if not data or "observations" not in data:
        return None
    out = []
    for obs in data["observations"]:
        if obs.get("value") in (".", "", None):
            continue
        try:
            out.append((obs["date"], float(obs["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out) or None


def fred_release_dates(release_id: int, *, include_future: bool = True) -> list[str]:
    if not _key():
        return []
    params = {"release_id": release_id, "api_key": _key(), "file_type": "json",
              "sort_order": "asc",
              "include_release_dates_with_no_data": "true" if include_future else "false"}
    data = fetch_json(f"{BASE}/releases/dates", params=params,
                      ttl_s=24 * 3600, provider="fred")
    if not data:
        return []
    return [d["date"] for d in data.get("release_dates", []) if d.get("date")]


def latest(series_id: str) -> tuple[str, float] | None:
    series = fred_series(series_id)
    return series[-1] if series else None


def yoy(series_id: str) -> float | None:
    """Last observation vs the one 12 monthly observations earlier."""
    series = fred_series(series_id)
    if not series or len(series) < 13:
        return None
    last, year_ago = series[-1][1], series[-13][1]
    if year_ago == 0:
        return None
    return (last / year_ago - 1.0) * 100.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_macro_fred.py -v`
Expected: 5 passed

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/fred.py tests/test_macro_fred.py
git commit -m "feat: FRED client (series, release dates, yoy)"
```

### Task G13: Inflation series — CPI + Core CPI

**Files:**
- Create: `swingbot/core/macro/series.py`
- Test: `tests/test_macro_series.py`

**Interfaces:**
- Produces: `SERIES: dict[str, SeriesSpec]` registry — `SeriesSpec(key, fred_id, kind, label, transform)`; first entries `cpi_yoy` (`CPIAUCSL`, transform yoy), `core_cpi_yoy` (`CPILFESL`, yoy), `cpi_mom` (m/m % of last two obs). `get_value(key) -> MacroValue | None` where `MacroValue(key, value, as_of, label, direction)` (`direction` = sign of change vs prior obs). All later series tasks only add registry rows; `get_value` never changes.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_series.py
import pytest

import swingbot.core.macro.series as series_mod
from swingbot.core.macro.series import SERIES, get_value

# 26 monthly CPI observations, accelerating at the end so direction = +1.
CPI_FIX = ([(f"2024-{m:02d}-01", 300.0 + m) for m in range(1, 13)]
           + [(f"2025-{m:02d}-01", 315.0 + 2 * m) for m in range(1, 13)]
           + [("2026-01-01", 345.0), ("2026-02-01", 351.0)])


@pytest.fixture
def fred_stub(monkeypatch):
    def fake_series(fred_id, **kw):
        return list(CPI_FIX)
    monkeypatch.setattr(series_mod.fred, "fred_series", fake_series)


def test_registry_rows_shape():
    for key in ("cpi_yoy", "core_cpi_yoy", "cpi_mom"):
        spec = SERIES[key]
        assert spec.key == key and spec.fred_id and spec.label
        assert spec.kind in series_mod.KINDS or spec.kind == "derived"


def test_cpi_yoy_golden(fred_stub):
    mv = get_value("cpi_yoy")
    # last=351.0 (2026-02), 12 obs earlier=319.0 (2025-02) -> +10.03%
    assert mv.value == pytest.approx((351.0 / 319.0 - 1) * 100, abs=0.01)
    assert mv.as_of == "2026-02-01"
    assert mv.direction == 1
    assert mv.label == "CPI YoY %"


def test_cpi_mom_golden(fred_stub):
    mv = get_value("cpi_mom")
    assert mv.value == pytest.approx((351.0 / 345.0 - 1) * 100, abs=0.01)


def test_missing_data_returns_none(monkeypatch):
    monkeypatch.setattr(series_mod.fred, "fred_series", lambda *a, **k: None)
    assert get_value("cpi_yoy") is None
    assert get_value("no_such_key") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_macro_series.py -v`
Expected: FAIL with `ImportError` (series module missing)

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/series.py
"""Named macro series registry.

Later tasks (G14-G20) ONLY add SERIES rows (and, rarely, a KINDS
transform); get_value never changes. kind="derived" rows compute from
other rows via spec.derive() -> MacroValue | None.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from swingbot.core.macro import fred


@dataclass(frozen=True)
class SeriesSpec:
    key: str
    fred_id: str
    kind: str                       # a KINDS name, or "derived"
    label: str
    derive: Callable | None = None  # only for kind="derived"


@dataclass(frozen=True)
class MacroValue:
    key: str
    value: float
    as_of: str
    label: str
    direction: int                  # sign of change vs prior computable obs


def _yoy_at(series, i):
    if i < 12 or series[i - 12][1] == 0:
        return None
    return (series[i][1] / series[i - 12][1] - 1.0) * 100.0


def _mom_at(series, i):
    if i < 1 or series[i - 1][1] == 0:
        return None
    return (series[i][1] / series[i - 1][1] - 1.0) * 100.0


def _level_at(series, i):
    return series[i][1]


# Transform registry — additive, like SERIES itself (G16 adds "diff").
KINDS: dict[str, Callable] = {"yoy": _yoy_at, "mom": _mom_at, "level": _level_at}


SERIES: dict[str, SeriesSpec] = {
    "cpi_yoy": SeriesSpec("cpi_yoy", "CPIAUCSL", "yoy", "CPI YoY %"),
    "core_cpi_yoy": SeriesSpec("core_cpi_yoy", "CPILFESL", "yoy", "Core CPI YoY %"),
    "cpi_mom": SeriesSpec("cpi_mom", "CPIAUCSL", "mom", "CPI MoM %"),
}


def get_value(key: str) -> MacroValue | None:
    spec = SERIES.get(key)
    if spec is None:
        return None
    if spec.kind == "derived":
        return spec.derive()
    series = fred.fred_series(spec.fred_id)
    if not series:
        return None
    calc = KINDS[spec.kind]
    i = len(series) - 1
    value = calc(series, i)
    if value is None:
        return None
    prior = calc(series, i - 1) if i >= 1 else None
    direction = 0 if prior is None else (value > prior) - (value < prior)
    return MacroValue(key, round(value, 2), series[i][0], spec.label, direction)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_macro_series.py -v`
Expected: 4 passed

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/series.py tests/test_macro_series.py
git commit -m "feat: macro series registry + CPI"
```

### Task G14: PPI series

**Files:** Modify `series.py`; test `tests/test_macro_series.py`

- Adds `ppi_yoy` (`PPIFIS` — Final Demand, the headline print), `ppi_mom`, `core_ppi_yoy` (`PPIFES` less foods/energy/trade). Verify both ids resolve in the G40 live smoke; the smoke script prints a loud warning if either 404s.
- [ ] **Step 1: Write the failing test** (append to `tests/test_macro_series.py`)

```python
def test_ppi_rows(fred_stub):
    assert SERIES["ppi_yoy"].fred_id == "PPIFIS"
    assert SERIES["core_ppi_yoy"].fred_id == "PPIFES"
    assert get_value("ppi_yoy").value == pytest.approx((351.0 / 319.0 - 1) * 100, abs=0.01)
    assert get_value("ppi_mom").value == pytest.approx((351.0 / 345.0 - 1) * 100, abs=0.01)
```

- [ ] **Step 2: Run — FAIL** (`KeyError: 'ppi_yoy'`): `python -m pytest tests/test_macro_series.py -v`
- [ ] **Step 3: Implement** — add to the `SERIES` literal:

```python
    "ppi_yoy": SeriesSpec("ppi_yoy", "PPIFIS", "yoy", "PPI YoY %"),
    "ppi_mom": SeriesSpec("ppi_mom", "PPIFIS", "mom", "PPI MoM %"),
    "core_ppi_yoy": SeriesSpec("core_ppi_yoy", "PPIFES", "yoy", "Core PPI YoY %"),
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_series.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/series.py tests/test_macro_series.py
git commit -m "feat: PPI series"
```

### Task G15: PCE series (the Fed's target measure)

**Files:** Modify `series.py`; test `tests/test_macro_series.py`

- Adds `pce_yoy` (`PCEPI`), `core_pce_yoy` (`PCEPILFE`) + a derived `inflation_vs_target` = core_pce_yoy − 2.0.
- [ ] **Step 1: Write the failing test** (append to `tests/test_macro_series.py`)

```python
def test_pce_rows_and_target_gap(fred_stub):
    core = get_value("core_pce_yoy")
    gap = get_value("inflation_vs_target")
    assert SERIES["pce_yoy"].fred_id == "PCEPI"
    assert gap.value == pytest.approx(core.value - 2.0, abs=0.01)
    assert gap.as_of == core.as_of


def test_target_gap_none_when_core_missing(monkeypatch):
    monkeypatch.setattr(series_mod.fred, "fred_series", lambda *a, **k: None)
    assert get_value("inflation_vs_target") is None
```

- [ ] **Step 2: Run — FAIL** (`KeyError: 'core_pce_yoy'`): `python -m pytest tests/test_macro_series.py -v`
- [ ] **Step 3: Implement** — rows in the `SERIES` literal plus a derive helper placed **after** `get_value`:

```python
    "pce_yoy": SeriesSpec("pce_yoy", "PCEPI", "yoy", "PCE YoY %"),
    "core_pce_yoy": SeriesSpec("core_pce_yoy", "PCEPILFE", "yoy", "Core PCE YoY %"),
```

```python
def _pce_vs_target() -> MacroValue | None:
    core = get_value("core_pce_yoy")
    if core is None:
        return None
    return MacroValue("inflation_vs_target", round(core.value - 2.0, 2),
                      core.as_of, "Core PCE vs 2% target", core.direction)


SERIES["inflation_vs_target"] = SeriesSpec(
    "inflation_vs_target", "", "derived", "Core PCE vs 2% target",
    derive=_pce_vs_target)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_series.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/series.py tests/test_macro_series.py
git commit -m "feat: PCE series + target gap"
```

### Task G16: Labor series

**Files:** Modify `series.py`; test `tests/test_macro_series.py`

- Adds `unemployment` (`UNRATE`), `payrolls_change_k` (`PAYEMS` m/m diff, thousands), `jobless_claims` (`ICSA`, weekly latest).
- [ ] **Step 1: Write the failing test** (append to `tests/test_macro_series.py`)

```python
def test_labor_rows(fred_stub):
    assert SERIES["unemployment"].fred_id == "UNRATE"
    assert SERIES["jobless_claims"].fred_id == "ICSA"
    assert get_value("unemployment").value == 351.0            # level kind
    assert get_value("payrolls_change_k").value == pytest.approx(351.0 - 345.0)  # diff kind
```

- [ ] **Step 2: Run — FAIL** (`KeyError: 'unemployment'`): `python -m pytest tests/test_macro_series.py -v`
- [ ] **Step 3: Implement** — new `KINDS` transform + rows:

```python
def _diff_at(series, i):
    if i < 1:
        return None
    return series[i][1] - series[i - 1][1]


KINDS["diff"] = _diff_at
```

```python
    "unemployment": SeriesSpec("unemployment", "UNRATE", "level", "Unemployment %"),
    "payrolls_change_k": SeriesSpec("payrolls_change_k", "PAYEMS", "diff",
                                    "Payrolls MoM change (k)"),   # PAYEMS is in thousands
    "jobless_claims": SeriesSpec("jobless_claims", "ICSA", "level", "Initial claims"),
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_series.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/series.py tests/test_macro_series.py
git commit -m "feat: labor market series"
```

### Task G17: Policy rate series

**Files:** Modify `series.py`; test `tests/test_macro_series.py`

- Adds `fed_funds` (`FEDFUNDS`), `fed_funds_target_upper` (`DFEDTARU`, daily).
- [ ] **Step 1: Write the failing test** (append to `tests/test_macro_series.py`)

```python
def test_policy_rate_rows(fred_stub):
    assert SERIES["fed_funds"].fred_id == "FEDFUNDS"
    assert SERIES["fed_funds_target_upper"].fred_id == "DFEDTARU"
    assert get_value("fed_funds").value == 351.0               # level kind
```

- [ ] **Step 2: Run — FAIL** (`KeyError: 'fed_funds'`): `python -m pytest tests/test_macro_series.py -v`
- [ ] **Step 3: Implement** — rows:

```python
    "fed_funds": SeriesSpec("fed_funds", "FEDFUNDS", "level", "Fed funds %"),
    "fed_funds_target_upper": SeriesSpec("fed_funds_target_upper", "DFEDTARU",
                                         "level", "Fed target upper %"),
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_series.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/series.py tests/test_macro_series.py
git commit -m "feat: policy rate series"
```

### Task G18: Treasury yields

**Files:** Modify `series.py`; test `tests/test_macro_series.py`

- Adds `y3m` (`DGS3MO`), `y2` (`DGS2`), `y10` (`DGS10`), `y30` (`DGS30`) — daily, last non-null.
- [ ] **Step 1: Write the failing test** (append to `tests/test_macro_series.py`)

```python
def test_treasury_yield_rows(fred_stub):
    for key, fred_id in (("y3m", "DGS3MO"), ("y2", "DGS2"),
                         ("y10", "DGS10"), ("y30", "DGS30")):
        assert SERIES[key].fred_id == fred_id
        assert SERIES[key].kind == "level"
    assert get_value("y10").value == 351.0
```

- [ ] **Step 2: Run — FAIL** (`KeyError: 'y3m'`): `python -m pytest tests/test_macro_series.py -v`
- [ ] **Step 3: Implement** — rows (daily series; `"."` days are already skipped by `fred_series`, so "level" is the last non-null print):

```python
    "y3m": SeriesSpec("y3m", "DGS3MO", "level", "3m yield %"),
    "y2": SeriesSpec("y2", "DGS2", "level", "2y yield %"),
    "y10": SeriesSpec("y10", "DGS10", "level", "10y yield %"),
    "y30": SeriesSpec("y30", "DGS30", "level", "30y yield %"),
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_series.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/series.py tests/test_macro_series.py
git commit -m "feat: treasury yield series"
```

### Task G19: Curve spreads + inversion flags

**Files:** Modify `series.py`; test `tests/test_macro_series.py`

**Interfaces:** derived registry rows `curve_10y2y` (`T10Y2Y` direct), `curve_10y3m` (`T10Y3M`), plus `curve_state() -> str` (`"inverted"` if either spread < 0, `"flat"` if both in [0, 0.25], else `"normal"`).
- [ ] **Step 1: Write the failing test** (append to `tests/test_macro_series.py`)

```python
def _stub_spreads(monkeypatch, values):
    """values: fred_id -> spread value (None = series unavailable)."""
    def fake(fred_id, **kw):
        v = values.get(fred_id)
        return None if v is None else [("2026-07-13", v), ("2026-07-14", v)]
    monkeypatch.setattr(series_mod.fred, "fred_series", fake)


def test_curve_state_three_states_plus_unknown(monkeypatch):
    _stub_spreads(monkeypatch, {"T10Y2Y": -0.30, "T10Y3M": 0.50})
    assert series_mod.curve_state() == "inverted"      # either spread < 0
    _stub_spreads(monkeypatch, {"T10Y2Y": 0.10, "T10Y3M": 0.20})
    assert series_mod.curve_state() == "flat"          # both in [0, 0.25]
    _stub_spreads(monkeypatch, {"T10Y2Y": 0.60, "T10Y3M": 1.10})
    assert series_mod.curve_state() == "normal"
    _stub_spreads(monkeypatch, {})
    assert series_mod.curve_state() == "unknown"       # degradation contract
```

- [ ] **Step 2: Run — FAIL** (`AttributeError: ... 'curve_state'`): `python -m pytest tests/test_macro_series.py -v`
- [ ] **Step 3: Implement** — rows + state function:

```python
    "curve_10y2y": SeriesSpec("curve_10y2y", "T10Y2Y", "level", "10y-2y spread"),
    "curve_10y3m": SeriesSpec("curve_10y3m", "T10Y3M", "level", "10y-3m spread"),
```

```python
def curve_state() -> str:
    """"inverted" if either spread < 0; "flat" if all available in
    [0, 0.25]; "normal" otherwise; "unknown" when nothing is available."""
    vals = [mv.value for mv in (get_value("curve_10y2y"), get_value("curve_10y3m")) if mv]
    if not vals:
        return "unknown"
    if any(v < 0 for v in vals):
        return "inverted"
    if all(0 <= v <= 0.25 for v in vals):
        return "flat"
    return "normal"
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_series.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/series.py tests/test_macro_series.py
git commit -m "feat: curve spreads + inversion state"
```

### Task G20: Inflation expectations & risk-context series

**Files:** Modify `series.py`; test `tests/test_macro_series.py`

- Adds `breakeven_5y` (`T5YIE`), `breakeven_10y` (`T10YIE`), `dollar_index` (`DTWEXBGS`), `wti` (`DCOILWTICO`).
- [ ] **Step 1: Write the failing test** (append to `tests/test_macro_series.py`)

```python
def test_expectations_and_risk_context_rows(fred_stub):
    for key, fred_id in (("breakeven_5y", "T5YIE"), ("breakeven_10y", "T10YIE"),
                         ("dollar_index", "DTWEXBGS"), ("wti", "DCOILWTICO")):
        assert SERIES[key].fred_id == fred_id
        assert SERIES[key].kind == "level"
```

- [ ] **Step 2: Run — FAIL** (`KeyError: 'breakeven_5y'`): `python -m pytest tests/test_macro_series.py -v`
- [ ] **Step 3: Implement** — rows:

```python
    "breakeven_5y": SeriesSpec("breakeven_5y", "T5YIE", "level", "5y breakeven %"),
    "breakeven_10y": SeriesSpec("breakeven_10y", "T10YIE", "level", "10y breakeven %"),
    "dollar_index": SeriesSpec("dollar_index", "DTWEXBGS", "level", "Dollar index"),
    "wti": SeriesSpec("wti", "DCOILWTICO", "level", "WTI crude $"),
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_series.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/series.py tests/test_macro_series.py
git commit -m "feat: breakevens, dollar, oil series"
```

### Task G21: VIX level + term structure

**Files:**
- Create: `swingbot/core/macro/vix.py`
- Test: `tests/test_macro_vix.py`

**Interfaces:**
- Produces: `vix_state() -> dict | None` — `{level, percentile_1y, regime, term_structure}`; level from FRED `VIXCLS` (fallback: cached `^VIX` bars via the existing fetch layer); `regime`: `<16 "calm"`, `16–24 "normal"`, `24–32 "elevated"`, `>32 "stress"`; `term_structure`: `"backwardation"` when VIX > VIX3M (`VXVCLS`) else `"contango"` (None if 3M unavailable). Percentile over trailing 252 obs.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_vix.py
import pytest

import swingbot.core.macro.vix as vix_mod


def _stub(monkeypatch, vix_series, vix3m_series=None):
    def fake(fred_id, **kw):
        if fred_id == "VIXCLS":
            return vix_series
        if fred_id == "VXVCLS":
            return vix3m_series
        return None
    monkeypatch.setattr(vix_mod.fred, "fred_series", fake)


def _series(levels):
    return [(f"d{i}", float(v)) for i, v in enumerate(levels)]


@pytest.mark.parametrize("level,regime", [
    (12.0, "calm"), (15.99, "calm"), (16.0, "normal"), (23.99, "normal"),
    (24.0, "elevated"), (31.99, "elevated"), (32.0, "stress"), (80.0, "stress"),
])
def test_regime_boundaries(monkeypatch, level, regime):
    _stub(monkeypatch, _series([20.0] * 300 + [level]))
    assert vix_mod.vix_state()["regime"] == regime


def test_percentile_golden(monkeypatch):
    # 251 obs at 10..? Make last obs higher than exactly 90% of the window.
    window = list(range(1, 252))          # 1..251
    window.append(226)                    # 226 is > 225 of 252 values -> ~89.7
    _stub(monkeypatch, _series(window))
    state = vix_mod.vix_state()
    assert state["percentile_1y"] == pytest.approx(100.0 * 227 / 252, abs=0.1)


def test_term_structure(monkeypatch):
    _stub(monkeypatch, _series([20.0] * 260), _series([25.0] * 260))
    assert vix_mod.vix_state()["term_structure"] == "contango"       # VIX < VIX3M
    _stub(monkeypatch, _series([30.0] * 260), _series([25.0] * 260))
    assert vix_mod.vix_state()["term_structure"] == "backwardation"  # VIX > VIX3M
    _stub(monkeypatch, _series([20.0] * 260), None)
    assert vix_mod.vix_state()["term_structure"] is None             # degrades, no error


def test_no_data_returns_none(monkeypatch):
    _stub(monkeypatch, None, None)
    assert vix_mod.vix_state() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_macro_vix.py -v`
Expected: FAIL with `ImportError` (vix module missing)

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/vix.py
"""VIX level, trailing-1y percentile, regime bands, term structure."""
from __future__ import annotations

from swingbot.core.macro import fred

_REGIME_BANDS = ((16.0, "calm"), (24.0, "normal"), (32.0, "elevated"))


def _regime(level: float) -> str:
    for cut, name in _REGIME_BANDS:
        if level < cut:
            return name
    return "stress"


def vix_state(loader=None) -> dict | None:
    """loader (optional): ticker -> daily OHLCV frame; used as a ^VIX
    cached-bars fallback when FRED's VIXCLS is unavailable."""
    series = fred.fred_series("VIXCLS")
    if not series and loader is not None:
        bars = loader("^VIX")
        if bars is not None and len(bars):
            series = [(str(idx.date()), float(v))
                      for idx, v in bars["Close"].items()]
    if not series:
        return None
    closes = [v for _, v in series]
    level = closes[-1]
    window = closes[-252:]
    percentile = 100.0 * sum(v <= level for v in window) / len(window)
    vix3m = fred.fred_series("VXVCLS")
    term = None
    if vix3m:
        term = "backwardation" if level > vix3m[-1][1] else "contango"
    return {"level": round(level, 2), "percentile_1y": round(percentile, 1),
            "regime": _regime(level), "term_structure": term}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_macro_vix.py -v`
Expected: 11 passed (8 regime params + 3)

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/vix.py tests/test_macro_vix.py
git commit -m "feat: VIX regime + term structure"
```

### Task G22: Credit stress (HYG/LQD)

**Files:**
- Create: `swingbot/core/macro/credit.py`
- Test: `tests/test_macro_credit.py`

**Interfaces:**
- Produces: `credit_state(bars: dict[str, pd.DataFrame] | None = None) -> dict | None` — ratio HYG/LQD closes (from the existing daily-bar cache; injectable for tests), `{ratio, sma20_slope, state}`; `state = "risk_off"` when ratio < its 20DMA and slope < 0, `"risk_on"` when above and rising, else `"neutral"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_credit.py
import numpy as np

from swingbot.core.macro.credit import credit_state
from tests.conftest import make_ohlcv


def _bars(hyg_closes, lqd_level=100.0):
    n = len(hyg_closes)
    return {"HYG": make_ohlcv(np.asarray(hyg_closes)),
            "LQD": make_ohlcv(np.full(n, lqd_level))}


def test_risk_on_rising_ratio():
    hyg = 80.0 * (1 + 0.002) ** np.arange(60)      # steadily rising vs flat LQD
    state = credit_state(_bars(hyg))
    assert state["state"] == "risk_on"
    assert state["sma20_slope"] > 0


def test_risk_off_falling_ratio():
    hyg = 80.0 * (1 - 0.002) ** np.arange(60)
    assert credit_state(_bars(hyg))["state"] == "risk_off"


def test_neutral_pop_above_falling_sma():
    hyg = list(100.0 * (1 - 0.005) ** np.arange(59))
    hyg.append(hyg[-1] * 1.05)   # one-bar pop above a still-falling 20DMA
    assert credit_state(_bars(np.asarray(hyg)))["state"] == "neutral"


def test_missing_etf_returns_none():
    assert credit_state({"HYG": make_ohlcv(np.full(60, 80.0))}) is None
    assert credit_state({}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_macro_credit.py -v`
Expected: FAIL with `ImportError` (credit module missing)

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/credit.py
"""HYG/LQD credit-stress ratio. Risk appetite proxy: high-yield
outperforming investment-grade = risk_on."""
from __future__ import annotations

import logging

log = logging.getLogger("swing-bot.macro.credit")


def _load_default_bars() -> dict | None:
    try:
        # Existing daily-bar cache loader — verify the exact function name
        # in swingbot/core/data.py at execution time (G23 wires the same one).
        from swingbot.core.data import load_cached_daily
        return {t: load_cached_daily(t) for t in ("HYG", "LQD")}
    except Exception:  # noqa: BLE001 — provider failure never degrades scanning
        log.warning("credit: cached HYG/LQD bars unavailable")
        return None


def credit_state(bars: dict | None = None) -> dict | None:
    bars = bars if bars is not None else _load_default_bars()
    if not bars or bars.get("HYG") is None or bars.get("LQD") is None:
        return None
    ratio = (bars["HYG"]["Close"] / bars["LQD"]["Close"]).dropna()
    if len(ratio) < 26:
        return None
    sma20 = ratio.rolling(20).mean()
    slope = float(sma20.iloc[-1] - sma20.iloc[-6])
    above = bool(ratio.iloc[-1] > sma20.iloc[-1])
    if above and slope > 0:
        state = "risk_on"
    elif not above and slope < 0:
        state = "risk_off"
    else:
        state = "neutral"
    return {"ratio": round(float(ratio.iloc[-1]), 4),
            "sma20_slope": round(slope, 5), "state": state}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_macro_credit.py -v`
Expected: 4 passed

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/credit.py tests/test_macro_credit.py
git commit -m "feat: credit stress gauge"
```

### Task G23: Sector ETF data plumbing

**Files:**
- Create: `swingbot/core/macro/sectors.py`
- Modify: `scripts/fetch_backtest_data.py` (add sector ETFs + SPY + HYG/LQD + ^VIX to the ticker set)
- Test: `tests/test_macro_sectors.py`

**Interfaces:**
- Produces: `SECTOR_ETFS = {"XLK": "Technology", "XLF": "Financials", "XLV": "Health Care", "XLY": "Cons. Discretionary", "XLP": "Cons. Staples", "XLE": "Energy", "XLI": "Industrials", "XLB": "Materials", "XLU": "Utilities", "XLRE": "Real Estate", "XLC": "Comm. Services"}`, benchmark `SPY`; `sector_bars(loader=None) -> dict[str, pd.DataFrame]` using the existing daily cache loader (injectable).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_sectors.py
import numpy as np

from swingbot.core.macro.sectors import SECTOR_ETFS, sector_bars
from tests.conftest import make_ohlcv


def test_sector_universe_complete():
    assert len(SECTOR_ETFS) == 11
    assert SECTOR_ETFS["XLK"] == "Technology"
    assert "XLRE" in SECTOR_ETFS and "XLC" in SECTOR_ETFS


def test_injectable_loader_and_missing_sector_skipped(caplog):
    frames = {t: make_ohlcv(np.full(150, 50.0)) for t in list(SECTOR_ETFS) + ["SPY"]}
    frames.pop("XLU")                       # simulate a missing cache file

    def loader(ticker):
        return frames.get(ticker)           # None for XLU

    bars = sector_bars(loader=loader)
    assert "XLU" not in bars                # skipped, not raised
    assert "SPY" in bars and "XLK" in bars
    assert len(bars) == 11                  # 10 sectors + SPY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_macro_sectors.py -v`
Expected: FAIL with `ImportError` (sectors module missing)

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/sectors.py
"""11 SPDR sector ETFs: data plumbing, RS ranks (G24), rotation (G25)."""
from __future__ import annotations

import logging

log = logging.getLogger("swing-bot.macro.sectors")

SECTOR_ETFS = {
    "XLK": "Technology", "XLF": "Financials", "XLV": "Health Care",
    "XLY": "Cons. Discretionary", "XLP": "Cons. Staples", "XLE": "Energy",
    "XLI": "Industrials", "XLB": "Materials", "XLU": "Utilities",
    "XLRE": "Real Estate", "XLC": "Comm. Services",
}
BENCHMARK = "SPY"


def _default_loader(ticker):
    try:
        # Existing daily-bar cache loader — verify the exact function name
        # in swingbot/core/data.py at execution time.
        from swingbot.core.data import load_cached_daily
        return load_cached_daily(ticker)
    except Exception:  # noqa: BLE001
        return None


def sector_bars(loader=None) -> dict:
    """{ticker: df} for the 11 sectors + SPY; missing tickers are skipped
    with a WARN — never a raise (a scan must survive a cold cache)."""
    loader = loader or _default_loader
    bars = {}
    for ticker in list(SECTOR_ETFS) + [BENCHMARK]:
        df = loader(ticker)
        if df is None or not len(df):
            log.warning("sectors: no cached bars for %s — skipped", ticker)
            continue
        bars[ticker] = df
    return bars
```

**And modify `scripts/fetch_backtest_data.py`:** add the context tickers to its universe so the daily cache covers them:

```python
# scripts/fetch_backtest_data.py — extend the ticker set:
CONTEXT_TICKERS = [
    "SPY", "HYG", "LQD", "^VIX",
    "XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLU", "XLRE", "XLC",
]
# wherever the script assembles its ticker list (verify variable name at
# execution), append: tickers = sorted(set(tickers) | set(CONTEXT_TICKERS))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_macro_sectors.py -v`
Expected: 2 passed

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/sectors.py scripts/fetch_backtest_data.py tests/test_macro_sectors.py
git commit -m "feat: sector ETF data plumbing"
```

### Task G24: Sector relative-strength ranks

**Files:** Modify `sectors.py`; test `tests/test_macro_sectors.py`

**Interfaces:** `sector_rs(bars, windows=(21, 63, 126)) -> list[dict]` — per sector: return over each window minus SPY's, composite = mean of window z-scores, rank 1–11; `leaders(rs_rows, n=3)` / `laggards(rs_rows, n=3)`.
- [ ] **Step 1: Write the failing test** (append to `tests/test_macro_sectors.py`)

```python
def _rs_universe():
    """XLE strictly outperforms (+0.3%/day), SPY flat, everyone else -0.1%/day."""
    n = 150
    bars = {"SPY": make_ohlcv(np.full(n, 100.0))}
    for t in SECTOR_ETFS:
        pct = 0.003 if t == "XLE" else -0.001
        bars[t] = make_ohlcv(100.0 * (1 + pct) ** np.arange(n))
    return bars


def test_xle_ranks_first():
    from swingbot.core.macro.sectors import laggards, leaders, sector_rs
    rows = sector_rs(_rs_universe())
    assert len(rows) == 11
    assert rows[0]["etf"] == "XLE" and rows[0]["rank"] == 1
    assert all(rows[i]["composite"] >= rows[i + 1]["composite"] for i in range(10))
    assert leaders(rows)[0]["etf"] == "XLE"
    assert "XLE" not in [r["etf"] for r in laggards(rows)]
    for w in (21, 63, 126):
        assert rows[0][f"rs_{w}"] > 0          # beat SPY on every window


def test_rs_short_history_skipped():
    from swingbot.core.macro.sectors import sector_rs
    bars = _rs_universe()
    bars["XLU"] = bars["XLU"].iloc[-50:]       # < max window + 1
    rows = sector_rs(bars)
    assert "XLU" not in [r["etf"] for r in rows]
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'sector_rs'`): `python -m pytest tests/test_macro_sectors.py -v`
- [ ] **Step 3: Write the implementation** (append to `sectors.py`)

```python
def _window_return_pct(df, w) -> float:
    c = df["Close"]
    return float(c.iloc[-1] / c.iloc[-1 - w] - 1.0) * 100.0


def sector_rs(bars: dict, windows=(21, 63, 126)) -> list[dict]:
    """Per sector: return-over-window minus SPY's, composite = mean of
    per-window z-scores, rank 1..11 (1 = strongest)."""
    spy = bars.get(BENCHMARK)
    need = max(windows) + 1
    if spy is None or len(spy) < need:
        return []
    rows = []
    for etf, name in SECTOR_ETFS.items():
        df = bars.get(etf)
        if df is None or len(df) < need:
            continue
        rows.append({"etf": etf, "sector": name,
                     **{f"rs_{w}": round(_window_return_pct(df, w)
                                         - _window_return_pct(spy, w), 2)
                        for w in windows}})
    if not rows:
        return []
    for w in windows:
        vals = [r[f"rs_{w}"] for r in rows]
        mu = sum(vals) / len(vals)
        sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
        for r in rows:
            r[f"z_{w}"] = (r[f"rs_{w}"] - mu) / sd
    for r in rows:
        r["composite"] = sum(r[f"z_{w}"] for w in windows) / len(windows)
    rows.sort(key=lambda r: r["composite"], reverse=True)
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows


def leaders(rs_rows: list[dict], n=3) -> list[dict]:
    return rs_rows[:n]


def laggards(rs_rows: list[dict], n=3) -> list[dict]:
    return rs_rows[-n:]
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_sectors.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/sectors.py tests/test_macro_sectors.py
git commit -m "feat: sector RS ranks"
```

### Task G25: Rotation classification + ticker→sector map

**Files:** Modify `sectors.py`; create seed `data/macro/ticker_sectors.json`; test `tests/test_macro_sectors.py`

**Interfaces:** `rotation_state(rs_rows) -> dict` — `{posture, note}`; `posture = "risk_on"` when ≥2 of {XLK, XLY, XLC} in top 4 composite ranks, `"risk_off"` when ≥2 of {XLP, XLU, XLV} in top 4, else `"mixed"`; note names the leaders. `sector_of(ticker) -> str | None` via the static map (seeded for the current scan universe; unknown → None).
- [ ] **Step 1: Write the failing test** (append to `tests/test_macro_sectors.py`)

```python
def _ranked(order):
    """Build minimal rs_rows in the given etf order (rank 1 first)."""
    return [{"etf": t, "sector": SECTOR_ETFS[t], "rank": i + 1,
             "composite": float(len(order) - i)} for i, t in enumerate(order)]


def test_rotation_postures():
    from swingbot.core.macro.sectors import rotation_state
    risk_on = _ranked(["XLK", "XLY", "XLE", "XLC", "XLF", "XLV", "XLI",
                       "XLB", "XLP", "XLU", "XLRE"])
    assert rotation_state(risk_on)["posture"] == "risk_on"     # XLK+XLY+XLC in top 4
    risk_off = _ranked(["XLP", "XLU", "XLE", "XLV", "XLK", "XLY", "XLC",
                        "XLF", "XLI", "XLB", "XLRE"])
    assert rotation_state(risk_off)["posture"] == "risk_off"   # XLP+XLU+XLV in top 4
    mixed = _ranked(["XLK", "XLP", "XLE", "XLF", "XLY", "XLU", "XLV",
                     "XLC", "XLI", "XLB", "XLRE"])
    assert rotation_state(mixed)["posture"] == "mixed"         # 1 of each camp
    assert "XLK" in rotation_state(risk_on)["note"]            # note names leaders


def test_sector_of_static_map(tmp_path, monkeypatch):
    import swingbot.core.macro.sectors as sectors_mod
    from swingbot.core.jsonio import atomic_write_json
    path = tmp_path / "ticker_sectors.json"
    atomic_write_json(str(path), {"NVDA": "Technology", "XOM": "Energy"})
    monkeypatch.setattr(sectors_mod, "TICKER_SECTORS_PATH", str(path))
    sectors_mod._ticker_map_cache = None
    assert sectors_mod.sector_of("NVDA") == "Technology"
    assert sectors_mod.sector_of("nvda") == "Technology"       # case-insensitive
    assert sectors_mod.sector_of("ZZZZ") is None
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'rotation_state'`): `python -m pytest tests/test_macro_sectors.py -v`
- [ ] **Step 3: Write the implementation** (append to `sectors.py`)

```python
import os

from swingbot import config
from swingbot.core.jsonio import read_json

_GROWTH = ("XLK", "XLY", "XLC")
_DEFENSIVE = ("XLP", "XLU", "XLV")

TICKER_SECTORS_PATH = os.path.join(config.DATA_DIR, "macro", "ticker_sectors.json")
_ticker_map_cache: dict | None = None


def rotation_state(rs_rows: list[dict]) -> dict:
    if not rs_rows:
        return {"posture": "unknown", "note": "no sector data"}
    top4 = [r["etf"] for r in rs_rows[:4]]
    growth = sum(t in top4 for t in _GROWTH)
    defensive = sum(t in top4 for t in _DEFENSIVE)
    if growth >= 2:
        posture = "risk_on"
    elif defensive >= 2:
        posture = "risk_off"
    else:
        posture = "mixed"
    names = ", ".join(f"{r['etf']} ({r['sector']})" for r in rs_rows[:3])
    return {"posture": posture, "note": f"leaders: {names}"}


def sector_of(ticker: str) -> str | None:
    global _ticker_map_cache
    if _ticker_map_cache is None:
        raw = read_json(TICKER_SECTORS_PATH, default={}) or {}
        _ticker_map_cache = {k.upper(): v for k, v in raw.items()}
    return _ticker_map_cache.get(ticker.upper())
```

**And create the seed map** `data/macro/ticker_sectors.json` for the current scan universe (read the live watchlist at execution time — `data/watchlist.json` — and map each ticker to its GICS sector name from `SECTOR_ETFS` values; unknown/ETF tickers may be omitted). Example shape:

```json
{"AAPL": "Technology", "NVDA": "Technology", "JPM": "Financials",
 "XOM": "Energy", "UNH": "Health Care", "AMZN": "Cons. Discretionary"}
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_sectors.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/sectors.py data/macro/ticker_sectors.json tests/test_macro_sectors.py
git commit -m "feat: sector rotation posture"
```

### Task G26: Breadth internals

**Files:**
- Create: `swingbot/core/macro/breadth.py`
- Test: `tests/test_macro_breadth.py`

**Interfaces:**
- Produces: `breadth(bars: dict[str, pd.DataFrame]) -> dict` — `{pct_above_50dma, pct_above_200dma, n}` over the scan universe's cached bars; `breadth_state(b) -> str` (`"healthy"` ≥60% above 50DMA, `"weak"` ≤40%, else `"mixed"`). (If edge-engine E28 landed, wrap it instead of recomputing — capability check `try: from swingbot.core.edge import factors`.)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_macro_breadth.py
import numpy as np

from swingbot.core.macro.breadth import breadth, breadth_state
from tests.conftest import make_ohlcv


def _universe():
    """10 tickers with 220 bars: 7 in uptrends (above both DMAs),
    3 in downtrends (below both)."""
    bars = {}
    for i in range(7):
        bars[f"UP{i}"] = make_ohlcv(100.0 * (1 + 0.002) ** np.arange(220))
    for i in range(3):
        bars[f"DN{i}"] = make_ohlcv(100.0 * (1 - 0.002) ** np.arange(220))
    return bars


def test_golden_percentages():
    b = breadth(_universe())
    assert b == {"pct_above_50dma": 70.0, "pct_above_200dma": 70.0, "n": 10}
    assert breadth_state(b) == "healthy"          # >= 60%


def test_state_bands():
    assert breadth_state({"pct_above_50dma": 40.0}) == "weak"
    assert breadth_state({"pct_above_50dma": 50.0}) == "mixed"
    assert breadth_state({"pct_above_50dma": None}) == "unknown"


def test_short_history_excluded():
    bars = _universe()
    bars["NEW"] = make_ohlcv(np.full(100, 50.0))   # < 200 bars: not countable
    assert breadth(bars)["n"] == 10


def test_empty_universe():
    b = breadth({})
    assert b["n"] == 0 and b["pct_above_50dma"] is None
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_macro_breadth.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/breadth.py
"""% of the scan universe above its 50/200 DMA.

Capability check: if edge-engine E28 breadth factors are merged
(`swingbot.core.edge.factors`), wrap them instead of recomputing —
verify at execution; the interface below stays either way.
"""
from __future__ import annotations


def breadth(bars: dict) -> dict:
    above50 = above200 = n = 0
    for df in bars.values():
        closes = df["Close"]
        if len(closes) < 200:
            continue
        n += 1
        above50 += bool(closes.iloc[-1] > closes.rolling(50).mean().iloc[-1])
        above200 += bool(closes.iloc[-1] > closes.rolling(200).mean().iloc[-1])
    if n == 0:
        return {"pct_above_50dma": None, "pct_above_200dma": None, "n": 0}
    return {"pct_above_50dma": round(100.0 * above50 / n, 1),
            "pct_above_200dma": round(100.0 * above200 / n, 1), "n": n}


def breadth_state(b: dict) -> str:
    pct = b.get("pct_above_50dma")
    if pct is None:
        return "unknown"
    if pct >= 60:
        return "healthy"
    if pct <= 40:
        return "weak"
    return "mixed"
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_breadth.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/breadth.py tests/test_macro_breadth.py
git commit -m "feat: breadth internals"
```

### Task G27: Risk-on/off composite

**Files:**
- Create: `swingbot/core/macro/composite.py`
- Test: `tests/test_macro_composite.py`

**Interfaces:**
- Produces: `risk_composite(vix, credit, rotation, breadth, curve) -> dict` — pure function over the five upstream dicts (any may be None): each contributes −1/0/+1 (vix calm=+1 stress=−1; credit risk_on=+1; rotation risk_on=+1; breadth healthy=+1; curve normal=+1 inverted=−1), score = mean of available × 100 → `{score: -100..100, label: "risk_on"|"neutral"|"risk_off"|"unknown", inputs_used: int, detail: [...]}` (label cuts at ±33; fewer than 2 inputs → `"unknown"`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_composite.py
from swingbot.core.macro.composite import risk_composite

VIX_CALM = {"level": 13.0, "percentile_1y": 20.0, "regime": "calm", "term_structure": "contango"}
VIX_STRESS = {"level": 38.0, "percentile_1y": 99.0, "regime": "stress", "term_structure": "backwardation"}
CREDIT_ON = {"ratio": 0.82, "sma20_slope": 0.001, "state": "risk_on"}
ROT_ON = {"posture": "risk_on", "note": "leaders: XLK"}
BREADTH_OK = {"pct_above_50dma": 72.0, "pct_above_200dma": 65.0, "n": 60}


def test_all_bull_is_plus_100_risk_on():
    out = risk_composite(VIX_CALM, CREDIT_ON, ROT_ON, BREADTH_OK, "normal")
    assert out["score"] == 100 and out["label"] == "risk_on"
    assert out["inputs_used"] == 5 and len(out["detail"]) == 5


def test_mixed_is_neutral():
    out = risk_composite(VIX_STRESS, CREDIT_ON, {"posture": "mixed", "note": ""},
                         BREADTH_OK, "inverted")
    # votes: -1, +1, 0, +1, -1 -> score 0
    assert out["score"] == 0 and out["label"] == "neutral"


def test_single_input_is_unknown():
    out = risk_composite(VIX_CALM, None, None, None, None)
    assert out["label"] == "unknown" and out["inputs_used"] == 1


def test_none_tolerance_everywhere():
    out = risk_composite(None, None, None, None, None)
    assert out == {"score": 0, "label": "unknown", "inputs_used": 0, "detail": []}
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_macro_composite.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/composite.py
"""Risk-on/off composite — a pure function over the five upstream dicts."""
from __future__ import annotations

from swingbot.core.macro.breadth import breadth_state

_VIX_VOTE = {"calm": 1, "normal": 0, "elevated": 0, "stress": -1}
_TRI_VOTE = {"risk_on": 1, "neutral": 0, "mixed": 0, "risk_off": -1,
             "healthy": 1, "weak": -1,
             "normal": 1, "flat": 0, "inverted": -1}


def risk_composite(vix, credit, rotation, breadth, curve) -> dict:
    """Each available input votes -1/0/+1; score = mean * 100.
    Fewer than 2 usable inputs -> label "unknown" (never a guess)."""
    votes, detail = [], []

    def _vote(value: int, text: str):
        votes.append(value)
        detail.append(f"{text} ({value:+d})")

    if vix and vix.get("regime"):
        _vote(_VIX_VOTE.get(vix["regime"], 0), f"VIX {vix['regime']}")
    if credit and credit.get("state"):
        _vote(_TRI_VOTE[credit["state"]], f"credit {credit['state']}")
    if rotation and rotation.get("posture") in ("risk_on", "mixed", "risk_off"):
        _vote(_TRI_VOTE[rotation["posture"]], f"rotation {rotation['posture']}")
    if breadth and breadth.get("pct_above_50dma") is not None:
        state = breadth_state(breadth)
        _vote(_TRI_VOTE[state], f"breadth {state}")
    if curve in ("normal", "flat", "inverted"):
        _vote(_TRI_VOTE[curve], f"curve {curve}")

    if len(votes) < 2:
        return {"score": 0, "label": "unknown",
                "inputs_used": len(votes), "detail": detail}
    score = round(100.0 * sum(votes) / len(votes))
    label = "risk_on" if score > 33 else "risk_off" if score < -33 else "neutral"
    return {"score": score, "label": label,
            "inputs_used": len(votes), "detail": detail}
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_composite.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/composite.py tests/test_macro_composite.py
git commit -m "feat: risk-on/off composite"
```

### Task G28: Fear/greed-style gauge

**Files:** Modify `composite.py`; test `tests/test_macro_composite.py`

**Interfaces:** `fear_greed(vix, breadth, credit, spy_momentum) -> dict | None` — 0–100 gauge from four 0–100 subcomponents (VIX percentile inverted; breadth pct_above_50; credit ratio percentile; SPY 125d momentum percentile), equal-weight mean of available (≥3 required); labels `<25 extreme fear, <45 fear, ≤55 neutral, ≤75 greed, >75 extreme greed`. Own gauge — no scraping of CNN's.
- [ ] **Step 1: Write the failing test** (append to `tests/test_macro_composite.py`)

```python
from swingbot.core.macro.composite import fear_greed


def _fg(vix_pct, breadth_pct, credit_pctile, mom_pctile):
    vix = None if vix_pct is None else {"percentile_1y": vix_pct, "regime": "normal"}
    b = None if breadth_pct is None else {"pct_above_50dma": breadth_pct}
    return fear_greed(vix, b, credit_pctile, mom_pctile)


def test_label_boundaries():
    # all four components equal -> value == that number
    assert _fg(100 - 10, 10, 10, 10)["label"] == "extreme fear"    # 10 < 25
    assert _fg(100 - 30, 30, 30, 30)["label"] == "fear"            # 30 < 45
    assert _fg(100 - 50, 50, 50, 50)["label"] == "neutral"         # 45..55
    assert _fg(100 - 70, 70, 70, 70)["label"] == "greed"           # 56..75
    assert _fg(100 - 90, 90, 90, 90)["label"] == "extreme greed"   # > 75


def test_vix_component_is_inverted():
    out = _fg(80.0, None, 50.0, 50.0)          # high VIX percentile = fear
    assert out["components"]["vix"] == 20.0


def test_fewer_than_three_inputs_returns_none():
    assert _fg(50.0, None, None, 50.0) is None
    assert _fg(None, None, None, None) is None
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'fear_greed'`): `python -m pytest tests/test_macro_composite.py -v`
- [ ] **Step 3: Write the implementation** (append to `composite.py`)

```python
def fear_greed(vix, breadth, credit_pctile, spy_momentum_pctile) -> dict | None:
    """0-100 gauge from up to four 0-100 subcomponents (equal-weight mean;
    >= 3 required): inverted VIX 1y percentile, breadth %>50DMA, HYG/LQD
    ratio percentile, SPY 125d momentum percentile. Our own gauge — no
    scraping of CNN's."""
    comps = {}
    if vix and vix.get("percentile_1y") is not None:
        comps["vix"] = round(100.0 - vix["percentile_1y"], 1)
    if breadth and breadth.get("pct_above_50dma") is not None:
        comps["breadth"] = breadth["pct_above_50dma"]
    if credit_pctile is not None:
        comps["credit"] = credit_pctile
    if spy_momentum_pctile is not None:
        comps["momentum"] = spy_momentum_pctile
    if len(comps) < 3:
        return None
    value = round(sum(comps.values()) / len(comps), 1)
    label = ("extreme fear" if value < 25 else "fear" if value < 45 else
             "neutral" if value <= 55 else "greed" if value <= 75 else
             "extreme greed")
    return {"value": value, "label": label, "components": comps}
```

(The two percentile inputs are computed by the snapshot builder (G38) from
cached bars: `credit_pctile` = today's HYG/LQD ratio vs its trailing 252
values; `spy_momentum_pctile` = today's SPY 125-day return vs its own
trailing 252 values — both via the same `sum(v <= last)/len` percentile
used in `vix.py`.)

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_composite.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/composite.py tests/test_macro_composite.py
git commit -m "feat: fear/greed gauge"
```

### Task G29: Historical econ event dataset (2018→present)

**Files:**
- Create: `scripts/build_event_history.py`, `data/macro/event_history.json` (generated, committed), `swingbot/core/macro/calendar_events.py`
- Test: `tests/test_macro_calendar.py`

**Interfaces:**
- Produces: `Event = {date, time_et, kind, label, importance}` with `kind` in `{"fomc", "cpi", "ppi", "nfp", "pce", "opex", "holiday"}`, importance 1–3 (fomc/cpi/nfp = 3). The script builds history from: FOMC — the Fed's published meeting dates hardcoded 2018–2026 (public, finite, stable — a literal list in the script with a source-URL comment; decision days 14:00 ET); CPI/PPI/PCE/NFP — `fred_release_dates()` (release ids: CPI 10, PPI 46, Employment Situation 50, Personal Income & Outlays 54), 08:30 ET. `calendar_events.load_events() -> list[Event]`; `events_between(start, end)`; `events_on(date)`.
- **This file is what makes the news-whipsaw red flag backtestable** — G90 joins it into the backtest frame.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_calendar.py
import json

import pytest

from swingbot.core.macro.calendar_events import events_between, events_on, load_events

FIXTURE = [
    {"date": "2026-07-14", "time_et": "08:30", "kind": "cpi", "label": "CPI release", "importance": 3},
    {"date": "2026-07-29", "time_et": "14:00", "kind": "fomc", "label": "FOMC decision", "importance": 3},
    {"date": "2026-07-02", "time_et": "08:30", "kind": "nfp", "label": "NFP release", "importance": 3},
    {"date": "2026-07-17", "time_et": "", "kind": "opex", "label": "OPEX", "importance": 1},
    {"date": "2026-07-20", "time_et": "08:30", "kind": "bogus", "label": "bad kind", "importance": 3},
    {"date": "2026-07-21", "time_et": "08:30", "kind": "cpi", "label": "bad importance", "importance": 9},
]


@pytest.fixture
def events_file(tmp_path):
    path = tmp_path / "event_history.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    return str(path)


def test_loader_validates_and_sorts(events_file):
    events = load_events(events_file)
    # invalid kind + invalid importance dropped; remainder date-sorted
    assert [e["kind"] for e in events] == ["nfp", "cpi", "opex", "fomc"]


def test_events_between_inclusive_bounds(events_file):
    events = load_events(events_file)
    window = events_between("2026-07-14", "2026-07-17", events)
    assert [e["kind"] for e in window] == ["cpi", "opex"]


def test_events_on(events_file):
    events = load_events(events_file)
    assert events_on("2026-07-29", events)[0]["kind"] == "fomc"
    assert events_on("2026-07-30", events) == []
```

- [ ] **Step 2: Run — FAIL** (`ImportError`), then **implement the loader**:

```python
# swingbot/core/macro/calendar_events.py
"""Econ event calendar. Event = {date, time_et, kind, label, importance}.
History is generated by scripts/build_event_history.py; the future edge
is kept fresh by refresh_future_events (G30)."""
from __future__ import annotations

import os

from swingbot import config
from swingbot.core.jsonio import read_json

KINDS = ("fomc", "cpi", "ppi", "nfp", "pce", "opex", "holiday")
IMPORTANCE = {"fomc": 3, "cpi": 3, "nfp": 3, "ppi": 2, "pce": 2, "opex": 1, "holiday": 1}
EVENTS_PATH = os.path.join(config.DATA_DIR, "macro", "event_history.json")


def load_events(path: str | None = None) -> list[dict]:
    rows = read_json(path or EVENTS_PATH, default=[]) or []
    out = []
    for e in rows:
        if (e.get("kind") in KINDS and e.get("date")
                and 1 <= int(e.get("importance", 0)) <= 3):
            out.append(e)
    return sorted(out, key=lambda e: (e["date"], e["kind"]))


def events_between(start: str, end: str, events: list[dict] | None = None) -> list[dict]:
    events = load_events() if events is None else events
    return [e for e in events if start <= e["date"] <= end]   # both bounds inclusive


def events_on(date: str, events: list[dict] | None = None) -> list[dict]:
    return events_between(date, date, events)
```

**And the generator script** (hits the network — excluded from the test suite; usage in header):

```python
# scripts/build_event_history.py
"""Build data/macro/event_history.json (2018 -> currently published future).

USAGE (network; NEVER imported by tests):
    FRED_API_KEY=... python scripts/build_event_history.py

Sources:
- FOMC decision days: the Fed's published calendars —
  https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
  (+ the "historical materials" pages for 2018-2020). Paste the SECOND
  day of each two-day meeting into FOMC_DECISION_DAYS below (decision at
  14:00 ET); the validation block rejects a bad paste (the Fed holds 8
  scheduled meetings/year — 7-9 allowed for unscheduled cuts/additions).
- CPI/PPI/NFP/PCE: fred_release_dates() — release ids CPI=10, PPI=46,
  Employment Situation=50, Personal Income & Outlays=54; prints 08:30 ET.
"""
import datetime as dt
import sys

sys.path.insert(0, ".")

from swingbot.core.jsonio import atomic_write_json
from swingbot.core.macro.calendar_events import EVENTS_PATH, IMPORTANCE
from swingbot.core.macro.fred import fred_release_dates

# Paste from the Fed's calendar pages (source URLs in the header) —
# every scheduled decision day 2018-01-31 through the last published
# future meeting, one ISO date per entry:
FOMC_DECISION_DAYS: list[str] = [
    # "2018-01-31", "2018-03-21", "2018-05-02", "2018-06-13", ...
]

RELEASES = {"cpi": 10, "ppi": 46, "nfp": 50, "pce": 54}


def _validate_fomc(days: list[str]) -> None:
    per_year: dict[str, int] = {}
    for d in days:
        dt.date.fromisoformat(d)                      # raises on a bad paste
        per_year[d[:4]] = per_year.get(d[:4], 0) + 1
    for year, n in sorted(per_year.items()):
        current = dt.date.today().year
        if int(year) < current:                        # future years may be partial
            assert 7 <= n <= 9, f"{year}: {n} FOMC days — check the paste"


def main() -> int:
    assert FOMC_DECISION_DAYS, "paste the FOMC decision days first (see header)"
    _validate_fomc(FOMC_DECISION_DAYS)
    events = [{"date": d, "time_et": "14:00", "kind": "fomc",
               "label": "FOMC decision", "importance": 3}
              for d in FOMC_DECISION_DAYS]
    for kind, release_id in RELEASES.items():
        dates = fred_release_dates(release_id, include_future=True)
        assert dates, f"no release dates for {kind} — check FRED_API_KEY"
        events += [{"date": d, "time_et": "08:30", "kind": kind,
                    "label": f"{kind.upper()} release",
                    "importance": IMPORTANCE[kind]}
                   for d in dates if d >= "2018-01-01"]
    events.sort(key=lambda e: (e["date"], e["kind"]))
    atomic_write_json(EVENTS_PATH, events)
    print(f"wrote {len(events)} events -> {EVENTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run tests — PASS** (`python -m pytest tests/test_macro_calendar.py -v`). **Then run the script once for real**; spot-check the JSON (CPI monthly ~mid-month 08:30 ET; 8 FOMC decision days/year; NFP first-Friday-ish). Commit the generated `data/macro/event_history.json`.
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/calendar_events.py scripts/build_event_history.py data/macro/event_history.json tests/test_macro_calendar.py
git commit -m "feat: historical econ event calendar 2018->present"
```

### Task G30: Forward event schedule refresh

**Files:** Modify `calendar_events.py`; test `tests/test_macro_calendar.py`

**Interfaces:** `refresh_future_events(days_ahead=45) -> int` — re-pulls `fred_release_dates(include_future=True)` + the static future FOMC list, merges into `event_history.json` (idempotent by (date, kind)), returns rows added; called by the snapshot scheduler (G39) at most daily. `next_event(kinds=None, now=None) -> Event | None`; `hours_until(event, now) -> float` (ET-aware).
- [ ] **Step 1: Write the failing tests** (append to `tests/test_macro_calendar.py`)

```python
import datetime as dt

import swingbot.core.macro.calendar_events as cal
import swingbot.core.macro.fred as fred


def test_refresh_merge_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "event_history.json"
    path.write_text(json.dumps([FIXTURE[0]]), encoding="utf-8")   # cpi 2026-07-14 known
    monkeypatch.setattr(cal, "EVENTS_PATH", str(path))
    monkeypatch.setattr(cal, "FUTURE_FOMC", ["2026-07-29"])
    monkeypatch.setattr(fred, "fred_release_dates",
                        lambda rid, include_future=True: ["2026-07-14", "2026-08-12"])
    today = dt.date(2026, 7, 10)
    # 4 kinds x 2 dates = 8 pairs, minus (cpi, 07-14) already present,
    # plus the future FOMC = 8 rows added.
    assert cal.refresh_future_events(days_ahead=45, today=today) == 8
    assert cal.refresh_future_events(days_ahead=45, today=today) == 0   # idempotent
    assert len(cal.load_events()) == 9


def test_next_event_ordering_and_tz_math():
    events = sorted(FIXTURE[:3], key=lambda e: (e["date"], e["kind"]))
    now = dt.datetime(2026, 7, 14, 11, 0, tzinfo=dt.timezone.utc)   # 07:00 ET (EDT)
    nxt = cal.next_event(now=now, events=events)
    assert nxt["kind"] == "cpi"                       # today's 08:30 ET still ahead
    # 08:30 ET on 2026-07-14 = 12:30 UTC -> 1.5 h away
    assert cal.hours_until(nxt, now=now) == pytest.approx(1.5)
    later = dt.datetime(2026, 7, 14, 13, 0, tzinfo=dt.timezone.utc)
    assert cal.next_event(now=later, events=events)["kind"] == "fomc"
    assert cal.next_event(kinds=("nfp",), now=later, events=events) is None
```

- [ ] **Step 2: Run — FAIL** (`AttributeError: ... 'refresh_future_events'`)
- [ ] **Step 3: Write the implementation** (append to `calendar_events.py`)

```python
import datetime as dt
from zoneinfo import ZoneInfo

from swingbot.core.jsonio import atomic_write_json

ET = ZoneInfo("America/New_York")

# Future FOMC decision days beyond what's in event_history.json — update
# when the Fed publishes next year's calendar (same source URL as
# scripts/build_event_history.py).
FUTURE_FOMC: list[str] = []

_RELEASES = {"cpi": 10, "ppi": 46, "nfp": 50, "pce": 54}


def refresh_future_events(days_ahead: int = 45, today: dt.date | None = None) -> int:
    """Merge newly published release dates + FUTURE_FOMC into the events
    file. Idempotent by (date, kind). Returns rows added. Called by the
    snapshot scheduler (G39) at most daily."""
    from swingbot.core.macro import fred as fred_mod

    today = today or dt.date.today()
    horizon = (today + dt.timedelta(days=days_ahead)).isoformat()
    start = today.isoformat()
    existing = load_events()
    seen = {(e["date"], e["kind"]) for e in existing}
    added = []

    def _add(date, kind, time_et, label):
        if start <= date <= horizon and (date, kind) not in seen:
            added.append({"date": date, "time_et": time_et, "kind": kind,
                          "label": label, "importance": IMPORTANCE[kind]})
            seen.add((date, kind))

    for kind, release_id in _RELEASES.items():
        for date in fred_mod.fred_release_dates(release_id, include_future=True):
            _add(date, kind, "08:30", f"{kind.upper()} release")
    for date in FUTURE_FOMC:
        _add(date, "fomc", "14:00", "FOMC decision")
    if added:
        merged = sorted(existing + added, key=lambda e: (e["date"], e["kind"]))
        atomic_write_json(EVENTS_PATH, merged)
    return len(added)


def _event_dt_utc(event: dict) -> dt.datetime:
    hh, mm = (int(x) for x in (event.get("time_et") or "09:30").split(":"))
    d = dt.date.fromisoformat(event["date"])
    return dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET) \
             .astimezone(dt.timezone.utc)


def next_event(kinds=None, now: dt.datetime | None = None,
               events: list[dict] | None = None) -> dict | None:
    now = now or dt.datetime.now(dt.timezone.utc)
    for e in (load_events() if events is None else events):
        if kinds and e["kind"] not in kinds:
            continue
        if _event_dt_utc(e) >= now:
            return e
    return None


def hours_until(event: dict, now: dt.datetime | None = None) -> float:
    now = now or dt.datetime.now(dt.timezone.utc)
    return (_event_dt_utc(event) - now).total_seconds() / 3600.0
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_calendar.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/calendar_events.py tests/test_macro_calendar.py
git commit -m "feat: forward event schedule"
```

### Task G31: Options-expiry calendar

**Files:**
- Create: `swingbot/core/macro/opex.py`
- Test: `tests/test_macro_opex.py`

**Interfaces:**
- Produces: `opex_dates(year) -> list[str]` (3rd Fridays, shifted to Thursday when Friday is a market holiday); `is_opex(date) -> bool`; `is_quad_witching(date) -> bool` (3rd Friday of Mar/Jun/Sep/Dec); pure calendar math, no network.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_opex.py
from swingbot.core.macro.opex import is_opex, is_quad_witching, opex_dates


def test_2026_quad_witching_golden():
    dates = opex_dates(2026)
    assert dates[2] == "2026-03-20"
    assert dates[5] == "2026-06-18"     # Jun 19 is Juneteenth -> Thursday
    assert dates[8] == "2026-09-18"
    assert dates[11] == "2026-12-18"


def test_is_opex_pairs():
    assert is_opex("2026-06-18") is True
    assert is_opex("2026-06-19") is False
    assert is_opex("2026-01-16") is True
    assert is_opex("2026-01-15") is False


def test_quad_witching_only_mar_jun_sep_dec():
    assert is_quad_witching("2026-03-20") and is_quad_witching("2026-12-18")
    assert not is_quad_witching("2026-01-16")
    assert not is_quad_witching("2026-06-19")
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_macro_opex.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/opex.py
"""Options-expiry / quad-witching calendar. Pure date math, no network.

Expiry = 3rd Friday, shifted to Thursday when that Friday is a market
holiday. Until G32 lands, _is_holiday covers the fixed-date holidays
that can land on a Friday; G32 swaps it to sessions.is_holiday (one
calendar authority)."""
import datetime as dt

# (month, day) fixed-date market holidays that can fall on a 3rd Friday.
_FRIDAY_HOLIDAYS = {(1, 1), (6, 19), (7, 4), (12, 25)}


def _is_holiday(date: dt.date) -> bool:
    return (date.month, date.day) in _FRIDAY_HOLIDAYS


def _third_friday(year: int, month: int) -> dt.date:
    first = dt.date(year, month, 1)
    offset = (4 - first.weekday()) % 7          # days to the first Friday
    return first + dt.timedelta(days=offset + 14)


def opex_dates(year: int) -> list[str]:
    out = []
    for month in range(1, 13):
        day = _third_friday(year, month)
        if _is_holiday(day):
            day -= dt.timedelta(days=1)
        out.append(day.isoformat())
    return out


def is_opex(date: str) -> bool:
    return date in opex_dates(int(date[:4]))


def is_quad_witching(date: str) -> bool:
    return is_opex(date) and int(date[5:7]) in (3, 6, 9, 12)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_opex.py -v` (3 passed)
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/opex.py tests/test_macro_opex.py
git commit -m "feat: opex + quad-witching calendar"
```

### Task G32: Market sessions — holidays, half-days, thin windows

**Files:**
- Create: `swingbot/core/macro/sessions.py`
- Test: `tests/test_macro_sessions.py`

**Interfaces:**
- Produces: NYSE holiday/half-day table 2018–2027 (static literal, source comment); `is_holiday(date)`, `is_half_day(date)`, `is_thin_window(dt_et) -> tuple[bool, str]` — true for first 30 min after open, last 10 min before close, half-day afternoons, and the week between Christmas and New Year (reason string for the embed); `session_flag(date, time_et=None) -> dict` (CheckResult-ready).

**Design note:** instead of a hand-typed 10-year table (typo-prone, unverifiable), the calendar is *rule-generated*: nth-weekday math for the floating holidays, the anonymous-Gregorian computus for Good Friday, NYSE observance shifts (Sun→Mon; Sat→Fri except New Year's, which is simply not observed), Juneteenth from 2022, plus a literal `EXTRA_CLOSURES` set for the two mourning closures. Source: https://www.nyse.com/markets/hours-calendars. The interface is exactly as specified.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_sessions.py
import datetime as dt

from swingbot.core.macro.sessions import (
    holidays, is_half_day, is_holiday, is_thin_window, session_flag,
)


def test_holiday_rules_2026():
    h = holidays(2026)
    assert "2026-01-01" in h                       # New Year's (Thursday)
    assert "2026-01-19" in h                       # MLK: 3rd Monday
    assert h["2026-04-03"] == "Good Friday"        # Easter 2026 = Apr 5
    assert "2026-06-19" in h                       # Juneteenth (Friday)
    assert "2026-07-03" in h                       # Jul 4 = Saturday -> observed Fri
    assert "2026-11-26" in h                       # Thanksgiving: 4th Thursday
    assert "2026-12-25" in h


def test_mourning_closures():
    assert is_holiday("2018-12-05")                # G.H.W. Bush
    assert is_holiday("2025-01-09")                # J. Carter


def test_half_days_2025():
    assert is_half_day("2025-07-03")               # Jul 4 2025 is a Friday
    assert is_half_day("2025-11-28")               # day after Thanksgiving
    assert is_half_day("2025-12-24")               # Christmas Eve (Wednesday)
    assert not is_half_day("2025-07-04")


def test_thin_windows():
    assert is_thin_window(dt.datetime(2026, 7, 14, 9, 45))[0]      # first 30 min
    assert not is_thin_window(dt.datetime(2026, 7, 14, 11, 0))[0]  # mid-session
    assert is_thin_window(dt.datetime(2026, 7, 14, 15, 55))[0]     # last 10 min
    thin, reason = is_thin_window(dt.datetime(2026, 12, 29, 11, 0))
    assert thin and "holiday week" in reason


def test_session_flag_shapes():
    assert session_flag("2026-06-19")["flag"] == "holiday"
    assert session_flag("2025-11-28")["flag"] == "half_day"
    assert session_flag("2026-07-14", dt.time(9, 45))["flag"] == "thin"
    assert session_flag("2026-07-14")["flag"] == "normal"
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_macro_sessions.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/sessions.py
"""NYSE session calendar: holidays, half-days (13:00 close), thin windows.
Rule-generated per https://www.nyse.com/markets/hours-calendars ."""
from __future__ import annotations

import datetime as dt

EXTRA_CLOSURES = {
    "2018-12-05": "National day of mourning (G.H.W. Bush)",
    "2025-01-09": "National day of mourning (J. Carter)",
}


def _easter(year: int) -> dt.date:
    """Anonymous Gregorian computus."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    last = (dt.date(year, month + 1, 1) if month < 12
            else dt.date(year + 1, 1, 1)) - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _observed(d: dt.date) -> dt.date:
    if d.weekday() == 6:                # Sunday -> Monday
        return d + dt.timedelta(days=1)
    if d.weekday() == 5:                # Saturday -> Friday
        return d - dt.timedelta(days=1)
    return d


def holidays(year: int) -> dict[str, str]:
    out: dict[str, str] = {}
    ny = dt.date(year, 1, 1)
    if ny.weekday() == 6:
        out[(ny + dt.timedelta(days=1)).isoformat()] = "New Year's Day (observed)"
    elif ny.weekday() != 5:             # on a Saturday it is NOT observed
        out[ny.isoformat()] = "New Year's Day"
    out[_nth_weekday(year, 1, 0, 3).isoformat()] = "MLK Day"
    out[_nth_weekday(year, 2, 0, 3).isoformat()] = "Washington's Birthday"
    out[(_easter(year) - dt.timedelta(days=2)).isoformat()] = "Good Friday"
    out[_last_weekday(year, 5, 0).isoformat()] = "Memorial Day"
    if year >= 2022:
        out[_observed(dt.date(year, 6, 19)).isoformat()] = "Juneteenth"
    out[_observed(dt.date(year, 7, 4)).isoformat()] = "Independence Day"
    out[_nth_weekday(year, 9, 0, 1).isoformat()] = "Labor Day"
    out[_nth_weekday(year, 11, 3, 4).isoformat()] = "Thanksgiving"
    out[_observed(dt.date(year, 12, 25)).isoformat()] = "Christmas"
    for date, label in EXTRA_CLOSURES.items():
        if date.startswith(str(year)):
            out[date] = label
    return out


def half_days(year: int) -> dict[str, str]:
    out: dict[str, str] = {}
    if dt.date(year, 7, 4).weekday() in (1, 2, 3, 4):   # Jul 4 Tue-Fri -> Jul 3 Mon-Thu
        out[dt.date(year, 7, 3).isoformat()] = "July 3rd early close"
    after_tg = _nth_weekday(year, 11, 3, 4) + dt.timedelta(days=1)
    out[after_tg.isoformat()] = "Day after Thanksgiving"
    dec24 = dt.date(year, 12, 24)
    if dec24.weekday() < 5 and dt.date(year, 12, 25).weekday() != 5:
        out[dec24.isoformat()] = "Christmas Eve early close"
    return out


def is_holiday(date: str) -> bool:
    return date in holidays(int(date[:4])) 


def is_half_day(date: str) -> bool:
    return date in half_days(int(date[:4]))


def is_thin_window(dt_et: dt.datetime) -> tuple[bool, str]:
    date = dt_et.date().isoformat()
    if is_holiday(date):
        return True, "market holiday"
    t = dt_et.time()
    if dt.time(9, 30) <= t < dt.time(10, 0):
        return True, "first 30 min after open"
    close = dt.time(13, 0) if is_half_day(date) else dt.time(16, 0)
    last10 = (dt.datetime.combine(dt_et.date(), close)
              - dt.timedelta(minutes=10)).time()
    if last10 <= t < close:
        return True, "last 10 min before close"
    if is_half_day(date) and t >= dt.time(12, 0):
        return True, "half-day session"
    if date[5:7] == "12" and "26" <= date[8:10] <= "31":
        return True, "holiday week (Christmas -> New Year)"
    return False, ""


def session_flag(date: str, time_et: dt.time | None = None) -> dict:
    """CheckResult-ready summary used by rf_thin_session (G65)."""
    year = int(date[:4])
    if is_holiday(date):
        return {"flag": "holiday", "detail": holidays(year)[date]}
    if is_half_day(date):
        return {"flag": "half_day", "detail": half_days(year)[date]}
    if time_et is not None:
        thin, reason = is_thin_window(
            dt.datetime.combine(dt.date.fromisoformat(date), time_et))
        if thin:
            return {"flag": "thin", "detail": reason}
    return {"flag": "normal", "detail": ""}
```

**And make sessions the one calendar authority** — replace the interim shim in `opex.py`:

```python
# swingbot/core/macro/opex.py — _is_holiday becomes:
def _is_holiday(date: dt.date) -> bool:
    from swingbot.core.macro.sessions import is_holiday
    return is_holiday(date.isoformat())
```

(delete `_FRIDAY_HOLIDAYS`; the G31 goldens must stay green.)

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_sessions.py tests/test_macro_opex.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/sessions.py swingbot/core/macro/opex.py tests/test_macro_sessions.py
git commit -m "feat: session liquidity calendar"
```

### Task G33: Earnings calendar provider

**Files:**
- Create: `swingbot/core/macro/earnings.py`
- Test: `tests/test_macro_earnings.py`

**Interfaces:**
- Produces: `days_to_earnings(ticker, now=None) -> int | None` — if llm-advisor's `market_context.py` exists, wrap it (one-implementation rule); else implement here: Finnhub `/calendar/earnings` window ±30d, 6h TTL via `fetch_json(provider="finnhub")`, empty key → None. `earnings_within(ticker, days) -> bool | None` (None when unknown — never a silent False).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_earnings.py
import datetime as dt

import swingbot.config as config
import swingbot.core.macro.earnings as earnings

PAYLOAD = {"earningsCalendar": [
    {"date": "2026-07-01", "symbol": "NVDA"},      # past
    {"date": "2026-07-22", "symbol": "NVDA"},      # next
    {"date": "2026-10-21", "symbol": "NVDA"},
]}

NOW = dt.date(2026, 7, 14)


def _with_key(monkeypatch, payload=PAYLOAD):
    monkeypatch.setattr(config, "FINNHUB_API_KEY", "k", raising=False)
    monkeypatch.setattr(earnings, "fetch_json", lambda *a, **k: payload)


def test_day_math(monkeypatch):
    _with_key(monkeypatch)
    assert earnings.days_to_earnings("NVDA", now=NOW) == 8
    assert earnings.earnings_within("NVDA", 10, now=NOW) is True
    assert earnings.earnings_within("NVDA", 3, now=NOW) is False


def test_no_future_earnings_is_none(monkeypatch):
    _with_key(monkeypatch, {"earningsCalendar": [{"date": "2026-07-01"}]})
    assert earnings.days_to_earnings("NVDA", now=NOW) is None


def test_no_key_none_and_no_network(monkeypatch):
    monkeypatch.setattr(config, "FINNHUB_API_KEY", "", raising=False)
    def boom(*a, **k):
        raise AssertionError("no network without a key")
    monkeypatch.setattr(earnings, "fetch_json", boom)
    assert earnings.days_to_earnings("NVDA", now=NOW) is None
    assert earnings.earnings_within("NVDA", 3, now=NOW) is None   # unknown, never False
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_macro_earnings.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/earnings.py
"""Earnings calendar provider. One-implementation rule: when llm-advisor's
market_context (v5 L-phase) is merged, wrap it; else Finnhub directly."""
from __future__ import annotations

import datetime as dt

from swingbot import config
from swingbot.core.macro.httpcache import fetch_json

_UNAVAILABLE = object()


def _via_advisor(ticker: str, now: dt.date):
    try:
        from swingbot.core.advisor import market_context   # capability check
    except ImportError:
        return _UNAVAILABLE
    fn = getattr(market_context, "days_to_earnings", None)
    return fn(ticker, now=now) if fn else _UNAVAILABLE


def days_to_earnings(ticker: str, now: dt.date | None = None) -> int | None:
    now = now or dt.date.today()
    advisor = _via_advisor(ticker, now)
    if advisor is not _UNAVAILABLE:
        return advisor
    key = (getattr(config, "FINNHUB_API_KEY", "") or "").strip()
    if not key:
        return None
    params = {"symbol": ticker, "token": key,
              "from": (now - dt.timedelta(days=30)).isoformat(),
              "to": (now + dt.timedelta(days=30)).isoformat()}
    data = fetch_json("https://finnhub.io/api/v1/calendar/earnings",
                      params=params, ttl_s=6 * 3600, provider="finnhub")
    if not data:
        return None
    dates = sorted(e["date"] for e in data.get("earningsCalendar", [])
                   if e.get("date"))
    future = [d for d in dates if d >= now.isoformat()]
    if not future:
        return None
    return (dt.date.fromisoformat(future[0]) - now).days


def earnings_within(ticker: str, days: int, now: dt.date | None = None) -> bool | None:
    d = days_to_earnings(ticker, now=now)
    return None if d is None else d <= days    # None = unknown, never a silent False
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_earnings.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/earnings.py tests/test_macro_earnings.py
git commit -m "feat: earnings calendar provider"
```

### Task G34: Market news headlines

**Files:**
- Create: `swingbot/core/macro/news.py`
- Test: `tests/test_macro_news.py`

**Interfaces:**
- Produces: `market_headlines(n=15) -> list[dict]` — Finnhub `/news?category=general`, headline dict `{ts, source, title, url, related}`; 30-min TTL; de-dup by lowercase title prefix (first 60 chars); empty key → `[]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_news.py
import swingbot.config as config
import swingbot.core.macro.news as news

RAW = [
    {"datetime": 300, "source": "A", "headline": "Fed holds rates steady", "url": "u1", "related": ""},
    {"datetime": 200, "source": "B", "headline": "FED HOLDS RATES STEADY", "url": "u2", "related": ""},  # dup by prefix
    {"datetime": 100, "source": "C", "headline": "Oil surges on supply fears", "url": "u3", "related": ""},
    {"datetime": 50, "source": "D", "headline": "", "url": "u4", "related": ""},                          # empty dropped
]


def test_parse_dedup_cap(monkeypatch):
    monkeypatch.setattr(config, "FINNHUB_API_KEY", "k", raising=False)
    monkeypatch.setattr(news, "fetch_json", lambda *a, **k: RAW)
    rows = news.market_headlines(n=15)
    assert [r["title"] for r in rows] == ["Fed holds rates steady",
                                          "Oil surges on supply fears"]
    assert rows[0] == {"ts": 300, "source": "A", "title": "Fed holds rates steady",
                       "url": "u1", "related": ""}
    assert news.market_headlines(n=1) == rows[:1]           # cap respected


def test_no_key_returns_empty(monkeypatch):
    monkeypatch.setattr(config, "FINNHUB_API_KEY", "", raising=False)
    def boom(*a, **k):
        raise AssertionError("no network without a key")
    monkeypatch.setattr(news, "fetch_json", boom)
    assert news.market_headlines() == []
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_macro_news.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/news.py
"""Finnhub market headlines (company headlines arrive in G35)."""
from __future__ import annotations

import datetime as dt

from swingbot import config
from swingbot.core.macro.httpcache import fetch_json

BASE = "https://finnhub.io/api/v1"


def _key() -> str:
    return (getattr(config, "FINNHUB_API_KEY", "") or "").strip()


def _norm(item: dict) -> dict:
    return {"ts": item.get("datetime", 0), "source": item.get("source", ""),
            "title": (item.get("headline") or "").strip(),
            "url": item.get("url", ""), "related": item.get("related", "")}


def _dedup(rows: list[dict], n: int) -> list[dict]:
    """Newest first, de-duplicated by lowercase 60-char title prefix."""
    seen, out = set(), []
    for row in sorted(rows, key=lambda r: r["ts"], reverse=True):
        prefix = row["title"].lower()[:60]
        if not row["title"] or prefix in seen:
            continue
        seen.add(prefix)
        out.append(row)
        if len(out) == n:
            break
    return out


def market_headlines(n: int = 15) -> list[dict]:
    if not _key():
        return []
    data = fetch_json(f"{BASE}/news", params={"category": "general", "token": _key()},
                      ttl_s=30 * 60, provider="finnhub")
    return _dedup([_norm(i) for i in data], n) if isinstance(data, list) else []
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_news.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/news.py tests/test_macro_news.py
git commit -m "feat: market news provider"
```

### Task G35: Company news

**Files:** Modify `news.py`; test `tests/test_macro_news.py`

**Interfaces:** `company_headlines(ticker, days=5, n=10) -> list[dict]` — Finnhub `/company-news`, 2h TTL, same dict shape.

- [ ] **Step 1: Write the failing test** (append to `tests/test_macro_news.py`)

```python
def test_company_headlines(monkeypatch):
    monkeypatch.setattr(config, "FINNHUB_API_KEY", "k", raising=False)
    captured = {}
    def fake_fetch(url, *, params=None, **kw):
        captured["url"], captured["params"] = url, params
        return RAW
    monkeypatch.setattr(news, "fetch_json", fake_fetch)
    rows = news.company_headlines("NVDA", days=5, n=10)
    assert captured["url"].endswith("/company-news")
    assert captured["params"]["symbol"] == "NVDA"
    assert len(rows) == 2                                   # dedup applies here too


def test_company_headlines_no_key(monkeypatch):
    monkeypatch.setattr(config, "FINNHUB_API_KEY", "", raising=False)
    assert news.company_headlines("NVDA") == []
```

- [ ] **Step 2: Run — FAIL** (`AttributeError: ... 'company_headlines'`)
- [ ] **Step 3: Write the implementation** (append to `news.py`)

```python
def company_headlines(ticker: str, days: int = 5, n: int = 10) -> list[dict]:
    if not _key():
        return []
    today = dt.date.today()
    params = {"symbol": ticker, "token": _key(),
              "from": (today - dt.timedelta(days=days)).isoformat(),
              "to": today.isoformat()}
    data = fetch_json(f"{BASE}/company-news", params=params,
                      ttl_s=2 * 3600, provider="finnhub")
    return _dedup([_norm(i) for i in data], n) if isinstance(data, list) else []
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_news.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/news.py tests/test_macro_news.py
git commit -m "feat: company news provider"
```

### Task G36: Headline sentiment scorer (lexicon)

**Files:**
- Create: `swingbot/core/macro/sentiment.py`
- Test: `tests/test_macro_sentiment.py`

**Interfaces:**
- Produces: `score_headline(title) -> float` in [-1, 1] — transparent finance lexicon (two literal frozensets, ~60 words each: POSITIVE beats/raises/surges/upgrade/record/approval/…, NEGATIVE misses/cuts/plunges/downgrade/probe/recall/bankruptcy/…), hit-count normalized, negation flip for not/no/fails-to within 3 tokens; `aggregate_sentiment(headlines) -> dict` `{score, n, label}` (label cuts ±0.15). Deliberately simple and auditable; the LLM advisor (G132) adds nuance separately and advisorily.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_sentiment.py
from swingbot.core.macro.sentiment import aggregate_sentiment, score_headline


def test_golden_directions():
    assert score_headline("NVDA beats estimates, raises guidance") > 0
    assert score_headline("Regulator opens probe; shares plunge on recall") < 0
    assert score_headline("Company holds annual meeting") == 0.0


def test_negation_flip():
    assert score_headline("Company fails to beat estimates") < 0
    assert score_headline("No probe after review") > 0


def test_score_bounds():
    assert -1.0 <= score_headline("plunges plunges plunges") <= 1.0


def test_aggregate():
    heads = [{"title": "NVDA beats estimates"}, {"title": "Sector rally continues"},
             {"title": "Weather is mild"}]
    agg = aggregate_sentiment(heads)
    assert agg["n"] == 3 and agg["score"] > 0.15 and agg["label"] == "positive"
    empty = aggregate_sentiment([])
    assert empty == {"score": 0.0, "n": 0, "label": "neutral"}
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_macro_sentiment.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/sentiment.py
"""Transparent finance-lexicon headline scorer. Deliberately simple and
auditable; the LLM advisor (G132) adds nuance separately, advisorily."""
from __future__ import annotations

POSITIVE = frozenset("""
beats beat raises raised surges surged soars soared upgrade upgraded upgrades
record rally rallies jumps jumped gains gained wins won win approval approved
strong tops topped exceeds exceeded outperform outperforms outperformed
bullish accelerates expands expansion growth profitable breakthrough buyback
dividend hike hikes partnership secures secured awarded milestone robust
momentum upbeat optimistic rebound rebounds recovers recovery booming
""".split())

NEGATIVE = frozenset("""
misses missed cuts plunges plunged sinks sank tumbles tumbled downgrade
downgraded downgrades probe probes investigation lawsuit sues sued recall
recalls bankruptcy default warns warning weak slump slumps layoffs fraud
halted halt delays delayed loss losses declines declined bearish shortfall
crash crashes selloff scandal fine fined penalty breach outage disappointing
downbeat pessimistic slowdown plunge tumble miss falls fell
""".split())

NEGATIONS = frozenset(("not", "no", "never", "fails", "failed", "without"))


def _tokens(title: str) -> list[str]:
    return [t.strip(".,!?:;()'\"").lower() for t in title.split()]


def score_headline(title: str) -> float:
    """[-1, 1]; hit-count normalized; negation within 3 tokens flips."""
    tokens = _tokens(title)
    total = hits = 0
    for i, tok in enumerate(tokens):
        val = 1 if tok in POSITIVE else -1 if tok in NEGATIVE else 0
        if val == 0:
            continue
        if any(w in NEGATIONS for w in tokens[max(0, i - 3):i]):
            val = -val
        total += val
        hits += 1
    if hits == 0:
        return 0.0
    return max(-1.0, min(1.0, total / hits))


def aggregate_sentiment(headlines: list[dict]) -> dict:
    """label cuts at +/-0.15."""
    scores = [score_headline(h.get("title", "")) for h in headlines]
    if not scores:
        return {"score": 0.0, "n": 0, "label": "neutral"}
    score = round(sum(scores) / len(scores), 3)
    label = "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"
    return {"score": score, "n": len(scores), "label": label}
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_sentiment.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/sentiment.py tests/test_macro_sentiment.py
git commit -m "feat: lexicon headline sentiment"
```

### Task G37: Rumor vs. confirmed classifier

**Files:** Modify `sentiment.py`; test `tests/test_macro_sentiment.py`

**Interfaces:** `classify_confirmation(headline_title) -> str` — `"rumor"` (matches report(edly)|sources say|rumor|in talks|considering|mulls|according to people familiar), `"confirmed"` (announces|files|reports Q|8-K|SEC filing|earnings|guidance|completes), else `"unclear"`; `rumor_ratio(headlines) -> float`. Feeds rf_rumor_spike (G63) and rf_buy_rumor (G64).
- [ ] **Step 1: Write the failing test** (append to `tests/test_macro_sentiment.py`)

```python
from swingbot.core.macro.sentiment import classify_confirmation, rumor_ratio


def test_three_way_classification():
    assert classify_confirmation("Apple reportedly in talks to acquire startup") == "rumor"
    assert classify_confirmation("Sources say merger being considered") == "rumor"
    assert classify_confirmation("NVDA announces record Q2 earnings") == "confirmed"
    assert classify_confirmation("Company files 8-K with SEC") == "confirmed"
    assert classify_confirmation("Shares move higher in afternoon trade") == "unclear"
    # rumor phrasing wins even when confirmation words also appear
    assert classify_confirmation("Reportedly set to announce acquisition") == "rumor"


def test_rumor_ratio():
    heads = [{"title": "reportedly in talks"}, {"title": "announces earnings"},
             {"title": "sources say deal near"}, {"title": "plain headline"}]
    assert rumor_ratio(heads) == 0.5
    assert rumor_ratio([]) == 0.0
```

- [ ] **Step 2: Run — FAIL** (`ImportError: ... 'classify_confirmation'`)
- [ ] **Step 3: Write the implementation** (append to `sentiment.py`)

```python
import re

_RUMOR = re.compile(
    r"reportedly|report(s|ed)? that|sources? say|rumou?r|in talks|considering|"
    r"mulls?|mulling|according to people familiar|weighs?|weighing|exploring|"
    r"could be|said to be|poised to|set to announce", re.I)
_CONFIRMED = re.compile(
    r"announce[sd]?|files?|filed|reports? q[1-4]|8-k|10-[kq]|sec filing|"
    r"earnings|guidance|completes?|completed|acquires?|acquired|confirms?|"
    r"confirmed|declares?|launches?|launched|signs?|signed", re.I)


def classify_confirmation(headline_title: str) -> str:
    if _RUMOR.search(headline_title):
        return "rumor"                 # rumor phrasing outranks confirmation verbs
    if _CONFIRMED.search(headline_title):
        return "confirmed"
    return "unclear"


def rumor_ratio(headlines: list[dict]) -> float:
    if not headlines:
        return 0.0
    rumors = sum(classify_confirmation(h.get("title", "")) == "rumor"
                 for h in headlines)
    return rumors / len(headlines)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_sentiment.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/sentiment.py tests/test_macro_sentiment.py
git commit -m "feat: rumor/confirmed headline classifier"
```

### Task G38: Macro snapshot builder

**Files:**
- Create: `swingbot/core/macro/snapshot.py`
- Test: `tests/test_macro_snapshot.py`

**Interfaces:**
- Produces: `build_snapshot(*, loaders=None, now=None) -> dict` — assembles every upstream module into ONE dict (each section None-tolerant): `{built_at, stale: bool, inflation: {cpi_yoy, core_cpi_yoy, ppi_yoy, pce_yoy, core_pce_yoy, vs_target}, labor: {...}, rates: {fed_funds, y3m, y2, y10, y30, curve_state}, expectations: {breakeven_5y, breakeven_10y}, risk: {vix, credit, dollar, wti}, composite: {...G27}, fear_greed: {...G28}, sectors: {rs_rows, rotation}, breadth: {...}, events: {next_high_impact, within_24h: [...], today: [...]}, news: {headlines_top5, sentiment, rumor_ratio}, quality_warnings: [...]}`. `save_snapshot(snap)` → `data/macro/macro_snapshot.json` (jsonio) + one summary line appended to `data/macro/snapshot_history.jsonl` (admin trend charts); `load_snapshot(max_age_min=None) -> dict | None`.
- **The single source every consumer reads** — scan gate, embeds, `!macro`, admin pages, advisor payloads. Nobody re-fetches providers at render time.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_snapshot.py
import datetime as dt

import numpy as np
import pytest

import swingbot.core.macro.snapshot as snap_mod
from tests.conftest import make_ohlcv


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(snap_mod, "SNAPSHOT_PATH", str(tmp_path / "macro_snapshot.json"))
    monkeypatch.setattr(snap_mod, "HISTORY_PATH", str(tmp_path / "snapshot_history.jsonl"))
    return tmp_path


@pytest.fixture
def all_stubbed(monkeypatch):
    """Every provider returns healthy fixture data — no network anywhere."""
    monkeypatch.setattr(snap_mod.httpcache, "LAST_SERVED_STALE", False)
    monkeypatch.setattr(snap_mod.series, "get_value",
                        lambda key: snap_mod.series.MacroValue(key, 2.5, "2026-07-01", key, 1))
    monkeypatch.setattr(snap_mod.series, "curve_state", lambda: "normal")
    monkeypatch.setattr(snap_mod.vix, "vix_state",
                        lambda loader=None: {"level": 14.0, "percentile_1y": 30.0,
                                             "regime": "calm", "term_structure": "contango"})
    monkeypatch.setattr(snap_mod.credit, "credit_state",
                        lambda bars=None: {"ratio": 0.8, "sma20_slope": 0.001,
                                           "state": "risk_on"})
    bars = {t: make_ohlcv(100.0 * (1 + 0.002) ** np.arange(220))
            for t in list(snap_mod.sectors.SECTOR_ETFS) + ["SPY"]}
    monkeypatch.setattr(snap_mod.sectors, "sector_bars", lambda loader=None: bars)
    monkeypatch.setattr(snap_mod.calendar_events, "load_events", lambda: [
        {"date": "2026-07-15", "time_et": "08:30", "kind": "cpi",
         "label": "CPI release", "importance": 3}])
    monkeypatch.setattr(snap_mod.news, "market_headlines",
                        lambda n=15: [{"ts": 1, "source": "A",
                                       "title": "Stocks rally on strong earnings",
                                       "url": "", "related": ""}])


def test_full_shape(paths, all_stubbed):
    now = dt.datetime(2026, 7, 14, 12, 0, tzinfo=dt.timezone.utc)
    snap = snap_mod.build_snapshot(now=now)
    for section in ("inflation", "labor", "rates", "expectations", "risk",
                    "composite", "fear_greed", "sectors", "breadth", "events",
                    "news", "quality_warnings"):
        assert section in snap, section
    assert snap["stale"] is False
    assert snap["rates"]["curve_state"] == "normal"
    assert snap["inflation"]["cpi_yoy"]["value"] == 2.5
    assert snap["events"]["next_high_impact"]["kind"] == "cpi"
    assert snap["news"]["sentiment"]["label"] == "positive"
    assert snap["composite"]["label"] == "risk_on"     # calm+credit+rotation+curve


def test_total_darkness_skeleton(paths, monkeypatch):
    monkeypatch.setattr(snap_mod.httpcache, "LAST_SERVED_STALE", False)
    monkeypatch.setattr(snap_mod.series, "get_value", lambda key: None)
    monkeypatch.setattr(snap_mod.series, "curve_state", lambda: "unknown")
    monkeypatch.setattr(snap_mod.vix, "vix_state", lambda loader=None: None)
    monkeypatch.setattr(snap_mod.credit, "credit_state", lambda bars=None: None)
    monkeypatch.setattr(snap_mod.sectors, "sector_bars", lambda loader=None: {})
    monkeypatch.setattr(snap_mod.calendar_events, "load_events", lambda: [])
    monkeypatch.setattr(snap_mod.news, "market_headlines", lambda n=15: [])
    snap = snap_mod.build_snapshot()
    assert snap["stale"] is True                       # the G43 contract starts here
    assert snap["composite"]["label"] == "unknown"
    assert snap["inflation"]["cpi_yoy"] is None
    assert snap["fear_greed"] is None
    assert snap["events"]["next_high_impact"] is None
    assert snap["news"]["sentiment"] == {"score": 0.0, "n": 0, "label": "neutral"}


def test_save_load_round_trip_and_history_line(paths, all_stubbed):
    snap = snap_mod.build_snapshot()
    snap_mod.save_snapshot(snap)
    assert snap_mod.load_snapshot() == snap
    with open(snap_mod.HISTORY_PATH, encoding="utf-8") as fh:
        lines = fh.readlines()
    assert len(lines) == 1 and '"composite"' in lines[0]


def test_max_age_gate(paths, all_stubbed):
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=90)
    snap_mod.save_snapshot(snap_mod.build_snapshot(now=old))
    assert snap_mod.load_snapshot(max_age_min=30) is None
    assert snap_mod.load_snapshot(max_age_min=240) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_macro_snapshot.py -v`
Expected: FAIL with `ImportError` (snapshot module missing)

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/snapshot.py
"""Build/save/load the ONE macro snapshot every consumer reads (scan gate,
embeds, !macro, admin pages, advisor payloads). Nobody re-fetches
providers at render time."""
from __future__ import annotations

import datetime as dt
import json
import logging
import os

from swingbot import config
from swingbot.core.jsonio import atomic_write_json, read_json
from swingbot.core.macro import (breadth as breadth_mod, calendar_events,
                                 composite, credit, httpcache, news,
                                 sectors, sentiment, series, vix)

log = logging.getLogger("swing-bot.macro.snapshot")

SNAPSHOT_PATH = os.path.join(config.DATA_DIR, "macro", "macro_snapshot.json")
HISTORY_PATH = os.path.join(config.DATA_DIR, "macro", "snapshot_history.jsonl")

_SERIES_KEYS = {
    "inflation": ("cpi_yoy", "core_cpi_yoy", "ppi_yoy", "pce_yoy",
                  "core_pce_yoy", "inflation_vs_target"),
    "labor": ("unemployment", "payrolls_change_k", "jobless_claims"),
    "rates": ("fed_funds", "y3m", "y2", "y10", "y30",
              "curve_10y2y", "curve_10y3m"),
    "expectations": ("breakeven_5y", "breakeven_10y"),
}


def _safe(fn, *args, **kw):
    """A broken provider never breaks the build — None + one log line."""
    try:
        return fn(*args, **kw)
    except Exception:  # noqa: BLE001
        log.warning("snapshot: %s failed", getattr(fn, "__name__", fn), exc_info=True)
        return None


def _mv_dict(keys) -> dict:
    out = {}
    for key in keys:
        mv = _safe(series.get_value, key)
        out[key] = None if mv is None else {"value": mv.value, "as_of": mv.as_of,
                                            "direction": mv.direction}
    return out


def _percentile(values, last) -> float | None:
    if not len(values):
        return None
    return round(100.0 * sum(v <= last for v in values) / len(values), 1)


def build_snapshot(*, loaders: dict | None = None, now=None) -> dict:
    """loaders (optional, injectable for tests / decoupling):
      "bars": ticker -> daily OHLCV frame (cache loader)
      "universe": () -> {ticker: df} for breadth over the scan universe
    Every section is None-tolerant; total provider failure still returns
    the full skeleton with unknowns and stale=True (proven in G43)."""
    loaders = loaders or {}
    bars_loader = loaders.get("bars")
    universe = loaders.get("universe")
    httpcache.LAST_SERVED_STALE = False
    now = now or dt.datetime.now(dt.timezone.utc)
    today = now.date().isoformat()

    snap: dict = {"built_at": now.isoformat(), "stale": False}
    for section, keys in _SERIES_KEYS.items():
        snap[section] = _mv_dict(keys)
    snap["rates"]["curve_state"] = _safe(series.curve_state) or "unknown"

    vix_state = _safe(vix.vix_state, bars_loader)
    credit_bars = None
    if bars_loader is not None:
        credit_bars = {t: _safe(bars_loader, t) for t in ("HYG", "LQD")}
    credit_state = _safe(credit.credit_state, credit_bars)

    sector_bars = _safe(sectors.sector_bars, bars_loader) or {}
    rs_rows = _safe(sectors.sector_rs, sector_bars) or []
    rotation = (_safe(sectors.rotation_state, rs_rows)
                or {"posture": "unknown", "note": ""})

    breadth_dict = (_safe(breadth_mod.breadth, universe() if universe else {})
                    or {"pct_above_50dma": None, "pct_above_200dma": None, "n": 0})

    comp = composite.risk_composite(vix_state, credit_state, rotation,
                                    breadth_dict, snap["rates"]["curve_state"])

    # fear/greed percentile inputs — only computable with cached bars
    credit_pctile = spy_mom_pctile = None
    if credit_bars and credit_bars.get("HYG") is not None \
            and credit_bars.get("LQD") is not None:
        ratio = (credit_bars["HYG"]["Close"] / credit_bars["LQD"]["Close"]).dropna()
        if len(ratio) >= 60:
            credit_pctile = _percentile(list(ratio.iloc[-252:]), float(ratio.iloc[-1]))
    if bars_loader is not None:
        spy = _safe(bars_loader, "SPY")
        if spy is not None and len(spy) > 380:
            mom = spy["Close"].pct_change(125).dropna()
            spy_mom_pctile = _percentile(list(mom.iloc[-252:]), float(mom.iloc[-1]))
    fg = _safe(composite.fear_greed, vix_state, breadth_dict,
               credit_pctile, spy_mom_pctile)

    events = _safe(calendar_events.load_events) or []
    horizon = (now + dt.timedelta(days=30)).date().isoformat()
    upcoming = [e for e in events if today <= e["date"] <= horizon]
    heads = _safe(news.market_headlines) or []

    snap["risk"] = {"vix": vix_state, "credit": credit_state,
                    **_mv_dict(("dollar_index", "wti"))}
    snap["composite"] = comp
    snap["fear_greed"] = fg
    snap["sectors"] = {"rs_rows": rs_rows, "rotation": rotation}
    snap["breadth"] = breadth_dict
    snap["events"] = {
        "next_high_impact": next((e for e in upcoming if e["importance"] == 3), None),
        "within_24h": [e for e in upcoming
                       if 0 <= calendar_events.hours_until(e, now) <= 24],
        "today": [e for e in upcoming if e["date"] == today],
    }
    snap["news"] = {"headlines_top5": heads[:5],
                    "sentiment": sentiment.aggregate_sentiment(heads),
                    "rumor_ratio": sentiment.rumor_ratio(heads)}
    # Stale when a stale cache was served OR too little arrived to say
    # anything (composite needs >= 2 inputs).
    snap["stale"] = bool(httpcache.LAST_SERVED_STALE or comp["inputs_used"] < 2)
    snap["quality_warnings"] = []          # G42's validator fills this in
    return snap


def save_snapshot(snap: dict) -> None:
    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    atomic_write_json(SNAPSHOT_PATH, snap)
    line = {
        "ts": snap["built_at"],
        "composite": snap["composite"]["score"],
        "label": snap["composite"]["label"],
        "vix": (snap["risk"]["vix"] or {}).get("level"),
        "curve_10y2y": (snap["rates"].get("curve_10y2y") or {}).get("value"),
        "curve_10y3m": (snap["rates"].get("curve_10y3m") or {}).get("value"),
        "fear_greed": (snap["fear_greed"] or {}).get("value"),
        "sentiment": snap["news"]["sentiment"]["score"],
    }
    with open(HISTORY_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")


def load_snapshot(max_age_min: float | None = None) -> dict | None:
    snap = read_json(SNAPSHOT_PATH, default=None)
    if snap is None:
        return None
    if max_age_min is not None:
        try:
            built = dt.datetime.fromisoformat(snap["built_at"])
        except (KeyError, TypeError, ValueError):
            return None
        age_min = (dt.datetime.now(dt.timezone.utc) - built).total_seconds() / 60.0
        if age_min > max_age_min:
            return None
    return snap
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_macro_snapshot.py -v`
Expected: 4 passed

- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/snapshot.py tests/test_macro_snapshot.py
git commit -m "feat: macro snapshot (single source of context)"
```

### Task G39: Snapshot scheduler — refresh before every scan

**Files:**
- Modify: `swingbot/core/macro/snapshot.py`, `swingbot/commands/scanning.py` (scan entry point)
- Test: `tests/test_macro_snapshot.py`

**Interfaces:**
- Produces: `ensure_fresh_snapshot(ttl_min=None) -> dict | None` — returns the saved snapshot when younger than TTL (default `config.MACRO_SNAPSHOT_TTL_MIN`), else rebuilds (called via `asyncio.to_thread` from the scan path); **wired at the top of every scan run** when `MACRO_ENABLED`; once per day also calls `refresh_future_events()`. Rebuild failure → previous snapshot with `stale=True` (never blocks the scan). Flag off → None and zero provider calls.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_macro_snapshot.py`)

```python
def test_ttl_respected_no_rebuild(paths, all_stubbed, monkeypatch):
    monkeypatch.setattr(snap_mod.config, "MACRO_ENABLED", True, raising=False)
    monkeypatch.setattr(snap_mod.config, "MACRO_SNAPSHOT_TTL_MIN", 30, raising=False)
    snap_mod.save_snapshot(snap_mod.build_snapshot())
    calls = {"n": 0}
    real_build = snap_mod.build_snapshot
    def counting_build(**kw):
        calls["n"] += 1
        return real_build(**kw)
    monkeypatch.setattr(snap_mod, "build_snapshot", counting_build)
    assert snap_mod.ensure_fresh_snapshot() is not None
    assert calls["n"] == 0                              # fresh -> no rebuild


def test_rebuild_failure_serves_previous_as_stale(paths, all_stubbed, monkeypatch):
    monkeypatch.setattr(snap_mod.config, "MACRO_ENABLED", True, raising=False)
    monkeypatch.setattr(snap_mod, "_last_future_refresh_day", None)
    monkeypatch.setattr(snap_mod.calendar_events, "refresh_future_events",
                        lambda **k: 0)
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=120)
    snap_mod.save_snapshot(snap_mod.build_snapshot(now=old))
    def boom(**kw):
        raise RuntimeError("providers down")
    monkeypatch.setattr(snap_mod, "build_snapshot", boom)
    served = snap_mod.ensure_fresh_snapshot(ttl_min=30)
    assert served is not None and served["stale"] is True


def test_disabled_returns_none_and_zero_calls(paths, monkeypatch):
    monkeypatch.setattr(snap_mod.config, "MACRO_ENABLED", False, raising=False)
    def boom(**kw):
        raise AssertionError("no provider calls when MACRO_ENABLED is off")
    monkeypatch.setattr(snap_mod, "build_snapshot", boom)
    assert snap_mod.ensure_fresh_snapshot() is None
```

- [ ] **Step 2: Run — FAIL** (`AttributeError: ... 'ensure_fresh_snapshot'`)
- [ ] **Step 3: Write the implementation** (append to `snapshot.py`)

```python
_last_future_refresh_day: str | None = None


def ensure_fresh_snapshot(ttl_min: float | None = None, *,
                          loaders: dict | None = None, now=None) -> dict | None:
    """Return a snapshot no older than ttl_min (default:
    config.MACRO_SNAPSHOT_TTL_MIN), rebuilding + saving when expired.
    Never raises; a failed rebuild serves the previous snapshot marked
    stale (never blocks the scan). MACRO_ENABLED off -> None and zero
    provider calls. Once per day also refreshes the forward event
    schedule (G30)."""
    global _last_future_refresh_day
    if not getattr(config, "MACRO_ENABLED", False):
        return None
    ttl = ttl_min if ttl_min is not None else float(
        getattr(config, "MACRO_SNAPSHOT_TTL_MIN", 30))
    fresh = load_snapshot(max_age_min=ttl)
    if fresh is not None:
        return fresh
    today = dt.date.today().isoformat()
    if _last_future_refresh_day != today:
        _last_future_refresh_day = today
        try:
            calendar_events.refresh_future_events()
        except Exception:  # noqa: BLE001
            log.warning("forward event refresh failed", exc_info=True)
    try:
        snap = build_snapshot(loaders=loaders, now=now)
        save_snapshot(snap)
        return snap
    except Exception:  # noqa: BLE001
        log.error("snapshot rebuild failed — serving previous as stale",
                  exc_info=True)
        prev = load_snapshot()
        if prev is not None:
            prev["stale"] = True
        return prev
```

**And wire it into the scan path** — `swingbot/commands/scanning.py` has three `scan_engine.run_scan(...)` call sites (`_session_scan_tick` ~line 416, the UI-poll path ~line 723, `check_cmd` ~line 1103 — verify at execution). Add one helper and await it immediately before each:

```python
# swingbot/commands/scanning.py
from swingbot.core.macro import snapshot as macro_snapshot


async def _refresh_macro_snapshot() -> None:
    """Pre-scan macro refresh (G39). Failure is logged, never blocks a scan."""
    if not config.MACRO_ENABLED:
        return
    try:
        await asyncio.to_thread(macro_snapshot.ensure_fresh_snapshot)
    except Exception:
        log.warning("macro snapshot refresh failed", exc_info=True)
```

```python
    # at each run_scan call site:
    await _refresh_macro_snapshot()
    alerts = await scan_engine.run_scan(...)
```

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_snapshot.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/snapshot.py swingbot/commands/scanning.py tests/test_macro_snapshot.py
git commit -m "feat: pre-scan macro snapshot refresh"
```

### Task G40: Live smoke script

**Files:**
- Create: `scripts/macro_smoke.py`

- [ ] **Step 1: Write it**

```python
# scripts/macro_smoke.py
"""Live macro smoke test (NETWORK — never imported by the test suite).

Usage:
    FRED_API_KEY=... FINNHUB_API_KEY=... python scripts/macro_smoke.py

Exit codes: 0 healthy, 1 degraded (> 3 sections missing), 2 config error.
"""
import json
import sys
import time

sys.path.insert(0, ".")

from swingbot import config
from swingbot.core.macro import fred, health
from swingbot.core.macro.snapshot import build_snapshot

SECTIONS = ("inflation", "labor", "rates", "expectations", "risk",
            "composite", "fear_greed", "sectors", "breadth", "events", "news")


def _section_missing(snap, name) -> bool:
    val = snap.get(name)
    if val in (None, {}, []):
        return True
    if isinstance(val, dict):
        return all(v in (None, [], {}) for v in val.values())
    return False


def main() -> int:
    if not (getattr(config, "FRED_API_KEY", "") or "").strip():
        print("FRED_API_KEY not set — nothing to smoke-test")
        return 2
    for series_id in ("PPIFIS", "PPIFES"):        # G14's ids must resolve live
        if fred.fred_series(series_id) is None:
            print(f"!!! WARNING: PPI series {series_id} returned nothing — "
                  f"re-check the FRED id chosen in G14 !!!")
    t0 = time.time()
    snap = build_snapshot()
    missing = [s for s in SECTIONS if _section_missing(snap, s)]
    for name in SECTIONS:
        status = "MISSING" if name in missing else "ok"
        print(f"{name:14s} {status:8s} "
              f"{json.dumps(snap.get(name), default=str)[:110]}")
    print(f"\nbuild took {time.time() - t0:.1f}s   stale={snap['stale']}")
    print("provider health:")
    for provider, s in health.provider_status().items():
        print(f"  {provider}: ok_rate={s['ok_rate_24h']:.2f} "
              f"calls_today={s['calls_today']} cache_hit={s['cache_hit_rate']:.2f}")
    print(f"missing sections: {missing or 'none'}")
    return 1 if len(missing) > 3 else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run once for real** (`FRED_API_KEY=... FINNHUB_API_KEY=... python scripts/macro_smoke.py`); paste the printed summary into `docs/superpowers/results/2026-07-macro-smoke.md` with a one-paragraph verdict (which sections are live, which providers degraded, build time). Commit both:

```bash
git add scripts/macro_smoke.py docs/superpowers/results/2026-07-macro-smoke.md
git commit -m "feat: macro live smoke script + first snapshot evidence"
```

### Task G41: Historical macro backfill (publication-lag aware)

**Files:**
- Create: `scripts/backfill_macro.py`, `swingbot/core/macro/history.py`
- Test: `tests/test_macro_history.py`

**Interfaces:**
- Produces: script writes `data/macro/history/{series_key}.json` full FRED history 2017-01→present for every registry series (2017 start gives yoy room for 2018 backtests) plus derived daily VIX-percentile and credit-state series from cached bars. `history.as_of_frame() -> pd.DataFrame` — date-indexed, one column per key, forward-filled **with publication lag**: monthly prints become visible on their release date (from G29's calendar), not their reference month — the no-lookahead rule G90 depends on.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_history.py
import os

import pandas as pd
import pytest

import swingbot.core.macro.history as hist
from swingbot.core.jsonio import atomic_write_json


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(hist, "HISTORY_DIR", str(tmp_path))
    events = [
        {"date": "2020-05-12", "time_et": "08:30", "kind": "cpi", "label": "CPI", "importance": 3},
        {"date": "2020-06-10", "time_et": "08:30", "kind": "cpi", "label": "CPI", "importance": 3},
    ]
    monkeypatch.setattr(hist.calendar_events, "load_events", lambda: events)
    return tmp_path


def test_publication_lag_golden(env):
    # April CPI (ref 2020-04-01) released May 12; May CPI released Jun 10.
    atomic_write_json(os.path.join(str(env), "cpi_yoy.json"),
                      [["2020-04-01", 0.3], ["2020-05-01", 0.1]])
    frame = hist.as_of_frame(start="2020-05-01", end="2020-06-30")
    assert frame.loc["2020-05-29", "cpi_yoy"] == 0.3   # May 29: only April's print is out
    assert frame.loc["2020-06-09", "cpi_yoy"] == 0.3   # still April's the day before release
    assert frame.loc["2020-06-10", "cpi_yoy"] == 0.1   # May's print appears ON release day
    assert pd.isna(frame.loc["2020-05-01", "cpi_yoy"]) # nothing published yet in-window


def test_ffill_and_missing_series(env):
    atomic_write_json(os.path.join(str(env), "cpi_yoy.json"), [["2020-04-01", 0.3]])
    frame = hist.as_of_frame(start="2020-05-01", end="2020-06-30")
    assert (frame.loc["2020-05-12":, "cpi_yoy"] == 0.3).all()   # forward-filled
    assert frame["y10"].isna().all()                # missing file -> NaN column, no error
```

- [ ] **Step 2: Run — FAIL** (`ImportError`), then **write the frame implementation**:

```python
# swingbot/core/macro/history.py
"""Publication-lag-aware historical macro frame — the no-lookahead
foundation G90's backtest snapshots stand on. Monthly prints become
visible on their RELEASE date (from the G29 calendar), not their
reference month."""
from __future__ import annotations

import os

import pandas as pd

from swingbot import config
from swingbot.core.jsonio import read_json
from swingbot.core.macro import calendar_events
from swingbot.core.macro.series import SERIES

HISTORY_DIR = os.path.join(config.DATA_DIR, "macro", "history")

# series key -> release kind gating its visibility. Unlisted keys are
# daily prints (yields, VIX, dollar, oil, weekly claims ~5d lag treated
# as same-day — a conservative simplification noted here deliberately).
_RELEASE_KIND = {
    "cpi_yoy": "cpi", "core_cpi_yoy": "cpi", "cpi_mom": "cpi",
    "ppi_yoy": "ppi", "ppi_mom": "ppi", "core_ppi_yoy": "ppi",
    "pce_yoy": "pce", "core_pce_yoy": "pce",
    "unemployment": "nfp", "payrolls_change_k": "nfp",
}


def _visible_from(obs_date: str, key: str, release_dates: dict) -> str:
    """A monthly print for reference month M becomes visible on the first
    release date AFTER M's month-end; daily series are same-day."""
    kind = _RELEASE_KIND.get(key)
    if kind is None:
        return obs_date
    month_end = (pd.Timestamp(obs_date) + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
    for release in release_dates.get(kind, ()):
        if release > month_end:
            return release
    return month_end        # no known release: month-end (still conservative)


def as_of_frame(start: str = "2018-01-01", end: str | None = None) -> pd.DataFrame:
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    idx = pd.bdate_range(start, end)
    release_dates: dict[str, list[str]] = {}
    for e in calendar_events.load_events():
        release_dates.setdefault(e["kind"], []).append(e["date"])
    for dates in release_dates.values():
        dates.sort()
    frame = pd.DataFrame(index=idx)
    for key, spec in SERIES.items():
        if spec.kind == "derived":
            continue
        col = pd.Series(index=idx, dtype=float)
        raw = read_json(os.path.join(HISTORY_DIR, f"{key}.json"), default=None)
        for obs_date, value in raw or []:
            ts = pd.Timestamp(_visible_from(obs_date, key, release_dates))
            pos = idx.searchsorted(ts)
            if pos < len(idx):
                col.iloc[pos] = value          # later prints overwrite on same day
        frame[key] = col.ffill()
    return frame
```

**And the backfill script:**

```python
# scripts/backfill_macro.py
"""Backfill data/macro/history/{key}.json for every registry series
(2017-01 -> present — 2017 gives yoy headroom for 2018 backtests), plus
derived daily vix_percentile.json and credit_state.json from cached bars.

Usage (NETWORK): FRED_API_KEY=... python scripts/backfill_macro.py
(--dry-run / --only / resume discipline are hardened in G202.)
"""
import os
import sys

sys.path.insert(0, ".")

from swingbot.core.jsonio import atomic_write_json
from swingbot.core.macro import fred
from swingbot.core.macro.history import HISTORY_DIR
from swingbot.core.macro.series import KINDS, SERIES


def build_transformed(key: str) -> list[list]:
    spec = SERIES[key]
    raw = fred.fred_series(spec.fred_id, start="2016-01-01", ttl_s=0)
    if not raw:
        return []
    calc = KINDS[spec.kind]
    out = []
    for i, (date, _) in enumerate(raw):
        value = calc(raw, i)
        if value is not None and date >= "2017-01-01":
            out.append([date, round(value, 4)])
    return out


def main() -> int:
    os.makedirs(HISTORY_DIR, exist_ok=True)
    written = 0
    for key, spec in SERIES.items():
        if spec.kind == "derived":
            continue
        rows = build_transformed(key)
        if not rows:
            print(f"  {key}: NO DATA (check FRED id {spec.fred_id})")
            continue
        atomic_write_json(os.path.join(HISTORY_DIR, f"{key}.json"), rows)
        print(f"  {key}: {len(rows)} rows ({rows[0][0]} .. {rows[-1][0]})")
        written += 1
    # Derived daily series from cached bars (verify loader name at execution):
    try:
        from swingbot.core.data import load_cached_daily
        vix_bars = load_cached_daily("^VIX")
        if vix_bars is not None and len(vix_bars) > 260:
            closes = vix_bars["Close"]
            pct = closes.rolling(252).apply(
                lambda w: 100.0 * (w <= w.iloc[-1]).mean()).dropna()
            atomic_write_json(os.path.join(HISTORY_DIR, "vix_percentile.json"),
                              [[str(d.date()), round(float(v), 1)]
                               for d, v in pct.items()])
            written += 1
    except Exception as exc:  # noqa: BLE001
        print(f"  vix_percentile: skipped ({exc})")
    print(f"wrote {written} history files -> {HISTORY_DIR}")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run tests — PASS**: `python -m pytest tests/test_macro_history.py -v`
- [ ] **Step 4: Run the backfill once for real; spot-check row counts; commit generated history files.**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/history.py scripts/backfill_macro.py data/macro/history/
git commit -m "feat: macro history backfill (publication-lag aware)"
```

### Task G42: Macro data-quality validator

**Files:**
- Create: `swingbot/core/macro/quality.py` (wired into `build_snapshot`)
- Test: `tests/test_macro_quality.py`

**Interfaces:**
- Produces: `validate_snapshot(snap) -> list[str]` — WARN strings for: yields outside [0, 20], VIX outside [5, 100], CPI yoy outside [-5, 25], sector count < 8, missing sections, empty event calendar within 30d ahead. Warnings land in `snap["quality_warnings"]` and surface in admin (G187); never raise.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_macro_quality.py
from swingbot.core.macro.quality import validate_snapshot


def _healthy():
    return {
        "inflation": {"cpi_yoy": {"value": 3.1, "as_of": "2026-06-01", "direction": 1}},
        "rates": {"y10": {"value": 4.2, "as_of": "2026-07-13", "direction": 0}},
        "risk": {"vix": {"level": 15.0}},
        "sectors": {"rs_rows": [{"etf": f"X{i}"} for i in range(11)]},
        "events": {"next_high_impact": {"kind": "cpi", "date": "2026-07-15"}},
        "news": {"headlines_top5": []},
    }


def test_healthy_snapshot_no_warnings():
    assert validate_snapshot(_healthy()) == []


def test_each_rule_trips():
    snap = _healthy()
    snap["rates"]["y10"]["value"] = 35.0
    assert any("yield" in w for w in validate_snapshot(snap))
    snap = _healthy()
    snap["risk"]["vix"]["level"] = 2.0
    assert any("VIX" in w for w in validate_snapshot(snap))
    snap = _healthy()
    snap["inflation"]["cpi_yoy"]["value"] = 40.0
    assert any("CPI" in w for w in validate_snapshot(snap))
    snap = _healthy()
    snap["sectors"]["rs_rows"] = snap["sectors"]["rs_rows"][:5]
    assert any("sectors" in w for w in validate_snapshot(snap))
    snap = _healthy()
    snap["events"]["next_high_impact"] = None
    assert any("calendar" in w for w in validate_snapshot(snap))
    snap = _healthy()
    del snap["rates"]
    assert any("section rates missing" in w for w in validate_snapshot(snap))


def test_never_raises_on_garbage():
    assert isinstance(validate_snapshot({}), list)
    assert isinstance(validate_snapshot({"rates": None, "risk": {"vix": None}}), list)
```

- [ ] **Step 2: Run — FAIL** (`ImportError`): `python -m pytest tests/test_macro_quality.py -v`
- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/macro/quality.py
"""Snapshot sanity validator — WARN strings, never raises, never blocks."""
from __future__ import annotations


def _val(section, key):
    entry = (section or {}).get(key)
    return None if not isinstance(entry, dict) else entry.get("value")


def validate_snapshot(snap: dict) -> list[str]:
    warnings: list[str] = []
    rates = snap.get("rates") or {}
    for key in ("y3m", "y2", "y10", "y30"):
        v = _val(rates, key)
        if v is not None and not (0 <= v <= 20):
            warnings.append(f"yield {key}={v} outside [0, 20]")
    vix_level = ((snap.get("risk") or {}).get("vix") or {}).get("level")
    if vix_level is not None and not (5 <= vix_level <= 100):
        warnings.append(f"VIX {vix_level} outside [5, 100]")
    cpi = _val(snap.get("inflation") or {}, "cpi_yoy")
    if cpi is not None and not (-5 <= cpi <= 25):
        warnings.append(f"CPI yoy {cpi} outside [-5, 25]")
    rs_rows = ((snap.get("sectors") or {}).get("rs_rows")) or []
    if len(rs_rows) < 8:
        warnings.append(f"only {len(rs_rows)} sectors with data (< 8)")
    for section in ("inflation", "rates", "risk", "events", "news"):
        if not snap.get(section):
            warnings.append(f"section {section} missing")
    events = snap.get("events") or {}
    if snap.get("events") is not None and events.get("next_high_impact") is None:
        warnings.append("no high-impact event within 30d — calendar may be stale")
    return warnings
```

**And wire it into the builder** — in `snapshot.build_snapshot`, replace the final `snap["quality_warnings"] = []` with:

```python
    from swingbot.core.macro.quality import validate_snapshot
    snap["quality_warnings"] = validate_snapshot(snap)
```

(The G38 tests keep passing: the healthy stubbed build produces zero warnings; the darkness build now carries warnings, which its assertions don't forbid.)

- [ ] **Step 4: Run — PASS**: `python -m pytest tests/test_macro_quality.py tests/test_macro_snapshot.py -v`
- [ ] **Step 5: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/macro/quality.py swingbot/core/macro/snapshot.py tests/test_macro_quality.py
git commit -m "feat: macro snapshot sanity validator"
```

### Task G43: Total-degradation proof

**Files:**
- Test: `tests/test_macro_degradation.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_macro_degradation.py
"""THE proof: entire internet down + cold caches -> the bot still gets a
full snapshot skeleton (every section None/unknown, stale=True) and
scanning proceeds. G121 extends this proof through the gate."""
import pytest

import swingbot.config as config_mod
import swingbot.core.macro.health as health
import swingbot.core.macro.httpcache as httpcache
import swingbot.core.macro.snapshot as snap_mod


@pytest.fixture
def darkness(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError("internet down")
    monkeypatch.setattr(httpcache.requests, "get", boom)
    monkeypatch.setattr(httpcache, "CACHE_DIR", str(tmp_path / "cache"))   # cold
    monkeypatch.setattr(httpcache, "LAST_SERVED_STALE", False)
    monkeypatch.setattr(health, "LEDGER_PATH", str(tmp_path / "health.jsonl"))
    monkeypatch.setattr(snap_mod, "SNAPSHOT_PATH", str(tmp_path / "snap.json"))
    monkeypatch.setattr(snap_mod, "HISTORY_PATH", str(tmp_path / "hist.jsonl"))
    monkeypatch.setattr(snap_mod, "_last_future_refresh_day", None)
    monkeypatch.setattr(snap_mod.calendar_events, "load_events", lambda: [])
    monkeypatch.setattr(config_mod, "MACRO_ENABLED", True, raising=False)
    monkeypatch.setattr(config_mod, "FRED_API_KEY", "key-set-net-down", raising=False)
    monkeypatch.setattr(config_mod, "FINNHUB_API_KEY", "key-set-net-down", raising=False)


def test_total_darkness(darkness):
    snap = snap_mod.build_snapshot()
    assert snap["stale"] is True
    assert snap["composite"]["label"] == "unknown"
    assert snap["inflation"]["cpi_yoy"] is None
    assert snap["rates"]["curve_state"] == "unknown"
    assert snap["risk"]["vix"] is None
    assert snap["news"]["headlines_top5"] == []
    # the scheduler still serves it — a scan would proceed normally
    served = snap_mod.ensure_fresh_snapshot()
    assert served is not None and served["composite"]["label"] == "unknown"
```

- [ ] **Step 2: Run — PASS**: `python -m pytest tests/test_macro_degradation.py -v`
- [ ] **Step 3: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add tests/test_macro_degradation.py
git commit -m "test: macro layer total-degradation proof"
```

### Task G44: Phase G1 checkpoint

- [ ] **Step 1:** Full suite + `make check` green; `scripts/macro_smoke.py` evidence committed (G40).
- [ ] **Step 2:** Update Progress block. Commit — `chore: phase G1 checkpoint`

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
            "TRAIN folds end 2023; see the gatekeeper-v6 targets doc")
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
# Gatekeeper v6 — baseline census (TRAIN folds, annotate-only)

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

### Task G98: Frontier run — all strategies

**Files:** Create `scripts/gate_frontier.py`; evidence `docs/superpowers/results/2026-07-gate-frontier.md`

- [ ] **Step 1: Write the CLI**

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

- [ ] **Step 2: Run for real on TRAIN**; write `docs/superpowers/results/2026-07-gate-frontier.md` with the honest headline numbers per strategy — one table row each: `WR @ chosen cut`, `wilson_lb`, `% signals kept`, `expectancy_r`, plus "no cut qualifies" rows stated plainly. Commit:

```bash
git add scripts/gate_frontier.py docs/superpowers/results/2026-07-gate-frontier*.json docs/superpowers/results/2026-07-gate-frontier.md
git commit -m "feat: frontier CLI + TRAIN evidence"
```

### Task G99: Red-flag ablation — each flag earns its keep

**Files:** Modify `scripts/gate_fold_run.py` (`--ablate` mode); evidence doc `docs/superpowers/results/2026-07-gate-ablation.md`
- Test: `tests/test_gate_folds.py`

**Interfaces:** `--ablate` runs folds once per red flag with only that flag active as a filter: reports each flag's standalone `{signals_removed_pct, wr_delta, expectancy_delta}` pooled + per fold. Flags that *hurt* expectancy in ≥ 2 folds get their registry weight set to 0 (info-only) in a follow-up commit, documented.
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_folds.py`)

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

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `folds.py`):

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

- [ ] **Step 3: Run tests — PASS.** Then **run for real** on TRAIN; write `docs/superpowers/results/2026-07-gate-ablation.md` (per flag: pooled + per-fold `{signals_removed_pct, wr_delta, expectancy_delta}` table). **Demotions:** any flag whose `expectancy_delta` is negative in ≥ 2 folds gets its registry weight set to 0 (info-only) in a follow-up commit, named in the doc.
- [ ] **Step 4: Commit**

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
# Gatekeeper v6 — TRAIN decision memo

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

### Task G105: Shadow promotion gate — pre-registered

**Files:** Modify `docs/superpowers/specs/2026-07-14-gatekeeper-v6-targets.md` (checkboxes section)

- [ ] **Step 1: Append this exact section to `docs/superpowers/specs/2026-07-14-gatekeeper-v6-targets.md`** (relevant **only if** the operator ever chooses to leave inform mode — enforce is optional forever):

```markdown
## Operational promotion checklist: inform -> enforce

Enforce mode may be enabled only when EVERY box below is checked. The
G170 config API refuses `GATE_MODE=enforce` while the sign-off file
`data/gate/enforce_signoff.json` is absent.

- [ ] >= 14 calendar days in inform/shadow with the shadow log writing
- [ ] >= 15 would-have-blocked decisions on record
- [ ] blocked-cohort realized WR < passed-cohort realized WR
      (gate_shadow_report output pasted below)
- [ ] zero live crashes / scan timeouts attributable to the gate
- [ ] the G104 report is attached below this checklist

Sign-off: add a dated line here (`YYYY-MM-DD — enabled enforce at
min-tier <X> — <initials>`) AND write data/gate/enforce_signoff.json:
`{"signed_at": "<ISO date>", "min_tier": "<X>", "report": "<path>"}`.

Leaving enforce (any reason, any time): flip GATE_MODE back to inform —
no sign-off needed to loosen, ever.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-07-14-gatekeeper-v6-targets.md
git commit -m "docs: shadow->enforce promotion gate (pre-registered)"
```

### Task G106: Enforce-mode switch (OPTIONAL — opt-in, never the default)

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_gate_enforce.py`

**Interfaces:** `GATE_MODE=enforce` (operator-chosen, guarded by the G105 evidence gate via G170): `decide()` (G76) verdicts apply — `block` → candidate dropped from alerts, `blocked_log` line + counted in telemetry (G135); `downgrade` → alert ships WEAK-style de-emphasized (amber, caution line — reuse the cockpit WEAK rendering path) with the checklist field showing why. Blocking **never** deletes the plan record — blocked plans are stored with status `blocked` for the audit trail. **Inform-mode regression test in this task:** the same failing candidate under `inform` still alerts, annotated, unblocked.
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_enforce.py
import json
import types

import pytest

import swingbot.commands.scanning as scanning
import swingbot.config as config
import swingbot.core.gate.persistence as persistence
from swingbot.core.plan_store import PlanStore
from tests.fixtures.gate import breakout_and_fail, uptrend_daily
from tests.fixtures.gate.plans import make_plan


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "SHADOW_PATH", str(tmp_path / "shadow.jsonl"))
    monkeypatch.setattr(persistence, "BLOCKED_PATH", str(tmp_path / "blocked.jsonl"))
    monkeypatch.setattr(config, "GATE_ENABLED", True, raising=False)
    store = PlanStore(path=str(tmp_path / "plans.json"))
    return store


def _candidate(store, df, **plan_kw):
    plan = make_plan(created_at="2026-07-13", **plan_kw)
    store.add(plan)
    return types.SimpleNamespace(ticker=plan.ticker, strategy=plan.strategy,
                                 plan=plan, df_daily=df)


def test_enforce_block_drops_alert_but_stores_plan(env, monkeypatch):
    monkeypatch.setattr(config, "GATE_MODE", "enforce", raising=False)
    monkeypatch.setattr(config, "GATE_MIN_TIER", "A", raising=False)
    candidate = _candidate(env, breakout_and_fail(100.0),
                           strategy="Break & Retest", trigger_price=100.0)
    decision, result = scanning._gate_evaluate(candidate, env, macro_snap=None)
    verdict = scanning._apply_gate_decision(candidate, decision, result, env)
    assert verdict == "drop"
    record = env.get_extra(candidate.plan.plan_id, "gate")
    assert record is not None                              # blocked != deleted
    assert env._plans[candidate.plan.plan_id]["status"] == "blocked"
    with open(persistence.BLOCKED_PATH, encoding="utf-8") as fh:
        assert json.loads(fh.readline())["decision"] == "block"


def test_enforce_downgrade_ships_deemphasized(env, monkeypatch):
    monkeypatch.setattr(config, "GATE_MODE", "enforce", raising=False)
    monkeypatch.setattr(config, "GATE_MIN_TIER", "C", raising=False)
    candidate = _candidate(env, breakout_and_fail(100.0),
                           strategy="Break & Retest", trigger_price=100.0)
    decision, result = scanning._gate_evaluate(candidate, env, macro_snap=None)
    # rf_fake_breakout fires -> tier C -> at min-tier C: downgrade, still ships
    if decision == "downgrade":
        assert scanning._apply_gate_decision(candidate, decision, result, env) == "send_weak"


@pytest.mark.parametrize("mode", ["shadow", "inform"])
def test_inform_and_shadow_regression_never_drop(env, monkeypatch, mode):
    monkeypatch.setattr(config, "GATE_MODE", mode, raising=False)
    monkeypatch.setattr(config, "GATE_MIN_TIER", "A+", raising=False)
    candidate = _candidate(env, breakout_and_fail(100.0),
                           strategy="Break & Retest", trigger_price=100.0)
    decision, result = scanning._gate_evaluate(candidate, env, macro_snap=None)
    assert decision == "pass"
    assert scanning._apply_gate_decision(candidate, decision, result, env) == "send"
```

- [ ] **Step 2: Run — FAIL**, then **implement** in `swingbot/commands/scanning.py`:

```python
from swingbot.core.gate.persistence import blocked_log


def _apply_gate_decision(candidate, decision: str, result, plan_store) -> str:
    """"send" | "send_weak" | "drop". Blocking NEVER deletes the plan —
    it is stored with status "blocked" for the audit trail. Only enforce
    mode can return anything but "send" (decide() guarantees it)."""
    if decision == "pass" or result is None:
        return "send"
    if decision == "downgrade":
        # WEAK-style de-emphasis: amber + caution line, reuse the cockpit
        # WEAK rendering path (G123 renders the why).
        return "send_weak"
    # decision == "block"
    reason = ", ".join(result.hard_blocks) or f"tier {result.tier} below GATE_MIN_TIER"
    blocked_log(result, "block", reason)
    record = plan_store._plans.get(candidate.plan.plan_id)
    if record is not None:
        record["status"] = "blocked"
        plan_store._save()
    return "drop"
```

At the alert-send site: `"drop"` skips the Discord send (telemetry counts it, G135); `"send_weak"` routes through the existing WEAK/de-emphasized embed styling (verify the cockpit WEAK path name at execution); `"send"` is unchanged.

(If touching `plan_store._plans` directly offends — add a `set_status(plan_id, status)` public method to PlanStore in this task instead; either way the record survives.)

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_enforce.py tests/test_gate_shadow.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py swingbot/core/plan_store.py tests/test_gate_enforce.py
git commit -m "feat: optional enforce mode"
```

### Task G107: Validation-shot interface (deferred to edge E92)

**Files:** Modify `docs/superpowers/results/2026-07-gate-decision.md`

- [ ] **Step 1: Append this exact paragraph to `docs/superpowers/results/2026-07-gate-decision.md`:**

```markdown
## Validation-shot ownership

The tier cuts chosen in this memo are part of the pooled final system
that edge-engine Task E92 fires at the 2024-2025 window EXACTLY ONCE.
Gatekeeper v6 performs no validation-window run of its own — every
number above is TRAIN (2018-2023). If edge-engine is unmerged when v6
finishes, the single shot waits; it is never spent early, split, or
retried. Anyone proposing "just a quick look at 2024" is proposing to
burn the only unbiased estimate this system will ever have.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/results/2026-07-gate-decision.md
git commit -m "docs: validation-shot ownership note"
```

### Task G108: Monthly gate re-audit cron

**Files:** Modify `swingbot/commands/scanning.py` (monitor loop, month boundary); test `tests/test_gate_audit.py`

**Interfaces:** `monthly_gate_audit(journal_entries, now) -> str | None` — first scan of each month: live WR by tier vs the TRAIN fold WR (drift alert when live tier-WR < fold WR − 10 pts with N ≥ 20, mirroring cockpit's pre-registered edge-decay rule), flag outcome stats, posted to the retrospective channel + saved `data/gate/audits/{YYYY-MM}.json`.
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_audit.py
import datetime as dt

import pytest

import swingbot.core.gate.audit as audit

NOW = dt.datetime(2026, 8, 3, 9, 0, tzinfo=dt.timezone.utc)   # first scan of August
FOLD_REF = {"A+": 90.0, "A": 78.0, "B": 62.0, "C": 45.0}


def _entries(tier, outcome, n):
    return [{"outcome": outcome, "r_multiple": 1.5 if outcome == "win" else -1.0,
             "gate_tier": tier, "fired_flags": []}] * n


@pytest.fixture
def audits_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "AUDITS_DIR", str(tmp_path))
    return tmp_path


def test_drift_trips(audits_dir):
    entries = _entries("A", "win", 12) + _entries("A", "loss", 12)   # live A WR 50 vs fold 78
    text = audit.monthly_gate_audit(entries, NOW, fold_reference=FOLD_REF)
    assert text is not None and "drift" in text and "A" in text


def test_small_n_stays_silent_on_drift(audits_dir):
    entries = _entries("A", "loss", 10)          # N=10 < 20: no drift alarm
    text = audit.monthly_gate_audit(entries, NOW, fold_reference=FOLD_REF)
    assert text is None or "drift" not in text


def test_idempotent_per_month(audits_dir):
    entries = _entries("A", "win", 25)
    assert audit.monthly_gate_audit(entries, NOW, fold_reference=FOLD_REF) is not None
    assert audit.monthly_gate_audit(entries, NOW, fold_reference=FOLD_REF) is None
```

- [ ] **Step 2: Run — FAIL**, then **implement**:

```python
# swingbot/core/gate/audit.py
"""Monthly gate re-audit: live WR by tier vs TRAIN fold WR. Drift rule
(pre-registered, mirrors cockpit's edge-decay rule): live tier WR
< fold WR - 10 pts with N >= 20."""
from __future__ import annotations

import os

import swingbot.config as config
from swingbot.core.gate.persistence import flag_outcome_stats, gate_analytics_section
from swingbot.core.jsonio import atomic_write_json, read_json

AUDITS_DIR = os.path.join(config.DATA_DIR, "gate", "audits")


def _fold_reference() -> dict | None:
    """Chosen-cut fold WRs per tier, read from the G98 frontier artifacts
    (verify the artifact path once G98 has run)."""
    ref = read_json(os.path.join(config.DATA_DIR, "gate", "fold_reference.json"),
                    default=None)
    return ref


def monthly_gate_audit(journal_entries, now, fold_reference=None) -> str | None:
    """First scan of each month (caller checks the boundary); idempotent
    via data/gate/audits/{YYYY-MM}.json. Returns the retrospective text or
    None when already run / nothing to say."""
    month = now.strftime("%Y-%m")
    os.makedirs(AUDITS_DIR, exist_ok=True)
    path = os.path.join(AUDITS_DIR, f"{month}.json")
    if os.path.exists(path):
        return None
    section = gate_analytics_section(journal_entries)
    if not section:
        return None
    fold_reference = fold_reference or _fold_reference() or {}
    lines = [f"📊 Gate audit {month} — live tier WR vs TRAIN folds"]
    drift = []
    for tier, stats in section["tier_wr"].items():
        if not stats["n"]:
            continue
        ref = fold_reference.get(tier)
        line = f"{tier}: {stats['wr']}% (N={stats['n']}, exp {stats['expectancy_r']}R)"
        if ref is not None:
            line += f" vs fold {ref}%"
            if stats["n"] >= 20 and stats["wr"] is not None and stats["wr"] < ref - 10:
                line = "⚠️ " + line + " — drift"
                drift.append(tier)
        lines.append(line)
    worst = (section["flags"] or [{}])[0]
    if worst.get("flag"):
        lines.append(f"worst flag by outcome: {worst['flag']} "
                     f"(ΔWR {worst['delta_wr']}, N={worst['n_fired_and_taken']})")
    atomic_write_json(path, {"month": month, "tiers": section["tier_wr"],
                             "flags": section["flags"], "drift": drift})
    return "\n".join(lines)
```

**Wiring:** in the monitor loop (`swingbot/commands/scanning.py`), on the first scan after a month boundary, post `monthly_gate_audit(...)`'s text to the retrospective channel (same posting helper `_post_retrospective` uses — verify at execution).

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_audit.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/audit.py swingbot/commands/scanning.py tests/test_gate_audit.py
git commit -m "feat: monthly gate audit"
```

### Task G109: Low-N cell guard

**Files:** Modify `frontier.py`, `render.py`; test `tests/test_gate_frontier.py`

**Interfaces:** every WR the gate surfaces anywhere routes through `fmt_wr(wr, n) -> str` — renders `"—"` with `"N<20"` note below the threshold, appends `"(N=…)"` always. Grep-level test asserts `render.py`/report builders use it (no raw `f"{wr:.0f}%"` slips through).
- [ ] **Step 1: Write the failing tests** (append to `tests/test_gate_frontier.py`)

```python
from swingbot.core.gate.render import fmt_wr


def test_fmt_wr_guard():
    assert fmt_wr(87.5, 41) == "88% (N=41)"
    assert fmt_wr(100.0, 7) == "— (N=7 < 20)"
    assert fmt_wr(None, 50) == "— (N=50)"


def test_no_raw_wr_format_slips_through():
    """Grep-level: render.py and the report builders must route every
    displayed WR through fmt_wr — no raw '{...:.0f}%' on wr variables."""
    import pathlib
    for path in ("swingbot/core/gate/render.py",
                 "swingbot/core/gate/audit.py"):
        src = pathlib.Path(path).read_text(encoding="utf-8")
        offenders = [line for line in src.splitlines()
                     if "wr" in line.lower() and ":.0f}%" in line
                     and "fmt_wr" not in line]
        assert not offenders, f"{path}: {offenders}"
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `render.py`; refactor `audit.py`'s tier lines to use it):

```python
def fmt_wr(wr: float | None, n: int, min_n: int = 20) -> str:
    """EVERY win rate the gate displays anywhere goes through here:
    below min_n renders as an em-dash with the reason; N is appended
    always. A WR without its sample size is a bug (cockpit rule)."""
    if wr is None:
        return f"— (N={n})"
    if n < min_n:
        return f"— (N={n} < {min_n})"
    return f"{wr:.0f}% (N={n})"
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_frontier.py tests/test_gate_audit.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/render.py swingbot/core/gate/audit.py tests/test_gate_frontier.py
git commit -m "feat: low-N guard on every displayed WR"
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

### Task G111: Frontier chart (matplotlib)

**Files:** Create `swingbot/core/charts/gate_charts.py`; test `tests/test_gate_charts.py`

**Interfaces:** `frontier_chart(frontier_rows, path) -> str` — dual-axis: WR + Wilson LB curves vs cut (left), % signals kept (right), chosen cut vline, N annotated per point; follows the existing charts' style constants. Smoke-test renders to tmp and asserts file non-empty + no exception (visual QA in G195).
- [ ] **Step 1: Write the failing test**

```python
# tests/test_gate_charts.py
import os

from swingbot.core.charts.gate_charts import frontier_chart

FRONTIER_ROWS = [
    {"cut": c, "n_kept": 200 - c, "pct_kept": 100.0 - c / 2, "wr": 55.0 + c / 4,
     "wilson_lb": (55.0 + c / 4) / 100 - 0.05, "expectancy_r": 0.3,
     "trades_per_month": 8.0}
    for c in range(0, 101, 10)
]


def test_frontier_chart_renders(tmp_path):
    path = str(tmp_path / "frontier.png")
    out = frontier_chart(FRONTIER_ROWS, path, chosen_cut=60)
    assert out == path and os.path.getsize(path) > 1000
```

- [ ] **Step 2: Run — FAIL**, then **implement**:

```python
# swingbot/core/charts/gate_charts.py
"""Gate/macro matplotlib charts. Reuse the existing style constants from
swingbot/core/charts/chart_style.py where they fit (verify names at
execution); every function renders to `path` and returns it. Visual QA
happens in G195 — tests only smoke-render."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def frontier_chart(frontier_rows, path: str, chosen_cut: int | None = None) -> str:
    rows = [r for r in frontier_rows if r["wr"] is not None]
    cuts = [r["cut"] for r in rows]
    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax1.plot(cuts, [r["wr"] for r in rows], marker="o", color="tab:blue",
             label="WR %")
    ax1.plot(cuts, [r["wilson_lb"] * 100 for r in rows], linestyle="--",
             color="tab:cyan", label="Wilson LB %")
    for r in rows:
        ax1.annotate(f"N={r['n_kept']}", (r["cut"], r["wr"]), fontsize=7,
                     textcoords="offset points", xytext=(0, 6))
    ax1.set_xlabel("checklist score cut")
    ax1.set_ylabel("win rate %")
    ax2 = ax1.twinx()
    ax2.plot(cuts, [r["pct_kept"] for r in rows], color="tab:gray", alpha=0.6,
             label="% signals kept")
    ax2.set_ylabel("% signals kept")
    if chosen_cut is not None:
        ax1.axvline(chosen_cut, color="tab:red", linestyle=":", label="chosen cut")
    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(handles1 + handles2, labels1 + labels2, loc="lower left", fontsize=8)
    ax1.set_title("WR frontier — the honest tradeoff curve")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_charts.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/charts/gate_charts.py tests/test_gate_charts.py
git commit -m "feat: frontier chart"
```

### Task G112: Decile + flag-ablation charts

**Files:** Modify `gate_charts.py`; test `tests/test_gate_charts.py`

**Interfaces:** `decile_chart(decile_rows, path)` (WR bars + N labels + expectancy line), `ablation_chart(ablation_rows, path)` (per-flag ΔWR vs Δsignals scatter, quadrant lines).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_charts.py`)

```python
from swingbot.core.charts.gate_charts import ablation_chart, decile_chart

DECILE_ROWS = [{"decile": d, "n": 20, "wr": 30.0 + d * 7,
                "wilson_lb": 0.2 + d * 0.06, "expectancy_r": -0.5 + d * 0.15}
               for d in range(10)]
ABLATION_ROWS = [
    {"flag": "rf_dead_cat", "signals_removed_pct": 12.0, "wr_delta": 6.0,
     "expectancy_delta": 0.08, "n_kept": 150},
    {"flag": "rf_opex_pin", "signals_removed_pct": 4.0, "wr_delta": -0.5,
     "expectancy_delta": -0.01, "n_kept": 180},
]


def test_decile_chart_renders(tmp_path):
    path = str(tmp_path / "deciles.png")
    assert decile_chart(DECILE_ROWS, path) == path
    assert os.path.getsize(path) > 1000


def test_ablation_chart_renders(tmp_path):
    path = str(tmp_path / "ablation.png")
    assert ablation_chart(ABLATION_ROWS, path) == path
    assert os.path.getsize(path) > 1000
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `gate_charts.py`):

```python
def decile_chart(decile_rows, path: str) -> str:
    rows = [r for r in decile_rows if r["wr"] is not None]
    fig, ax1 = plt.subplots(figsize=(9, 5))
    xs = [r["decile"] for r in rows]
    ax1.bar(xs, [r["wr"] for r in rows], color="tab:blue", alpha=0.8, label="WR %")
    for r in rows:
        ax1.annotate(f"N={r['n']}", (r["decile"], r["wr"]), ha="center",
                     fontsize=7, textcoords="offset points", xytext=(0, 4))
    ax1.set_xlabel("score decile")
    ax1.set_ylabel("win rate %")
    ax2 = ax1.twinx()
    ax2.plot(xs, [r["expectancy_r"] for r in rows], color="tab:orange",
             marker="o", label="expectancy R")
    ax2.set_ylabel("expectancy (R)")
    ax2.axhline(0, color="tab:gray", linewidth=0.8)
    ax1.set_title("WR by checklist-score decile")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def ablation_chart(ablation_rows, path: str) -> str:
    fig, ax = plt.subplots(figsize=(8, 6))
    for r in ablation_rows:
        ax.scatter(r["signals_removed_pct"], r["wr_delta"], s=60)
        ax.annotate(r["flag"].removeprefix("rf_"),
                    (r["signals_removed_pct"], r["wr_delta"]),
                    fontsize=8, textcoords="offset points", xytext=(6, 4))
    ax.axhline(0, color="tab:gray", linewidth=0.8)
    ax.axvline(0, color="tab:gray", linewidth=0.8)
    ax.set_xlabel("% signals removed by the flag alone")
    ax.set_ylabel("ΔWR (pts) when removed")
    ax.set_title("Per-flag ablation — does each flag earn its keep?")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_charts.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/charts/gate_charts.py tests/test_gate_charts.py
git commit -m "feat: decile + ablation charts"
```

### Task G113: `!frontier` command

**Files:** Create `swingbot/commands/gatecheck.py` (module registered like other command modules; help catalog + `COMMAND_USAGE` entries); test `tests/test_commands_gatecheck.py`

**Interfaces:** `!frontier [strategy]` — renders the latest saved frontier evidence (from the G98 JSON artifacts): table embed (cut/WR/LB/N/kept%) + attached G111 chart; strategy omitted → aggregate. Empty state: "No frontier evidence yet — run scripts/gate_frontier.py".
- [ ] **Step 1–4: TDD (embed golden over fixture artifact; empty state), commit** — `feat: !frontier command`

### Task G114: `!tierwr` command — live tier scoreboard

**Files:** Modify `gatecheck.py`; test `tests/test_commands_gatecheck.py`

**Interfaces:** `!tierwr` — live WR/expectancy/N by tier from the analytics snapshot's gate section (G86), side-by-side with the TRAIN fold numbers, every WR through `fmt_wr` (G109), footer states the honesty line: "Tiers are earned labels — see gate-decision memo".
- [ ] **Step 1–4: TDD, commit** — `feat: !tierwr live scoreboard`

### Task G115: `!redflags` command

**Files:** Modify `gatecheck.py`; test `tests/test_commands_gatecheck.py`

**Interfaces:** `!redflags` — G85's live flag-outcome table as an embed (flag, times fired & taken anyway, WR ignored vs clean, ΔR), sorted by damage; the receipts that make the checklist self-enforcing.
- [ ] **Step 1–4: TDD, commit** — `feat: !redflags receipts command`

### Task G116: Tier-sized positions — fold test

**Files:** Modify `scripts/gate_fold_run.py` (`--tier-sizing` mode); evidence appended to the G102 memo
- Test: `tests/test_gate_folds.py`

**Interfaces:** replays folds with G77's size multipliers applied (A+/A full, B half, C zero) vs flat sizing: compares compounded growth + max drawdown per fold (uses edge growth math when merged, else plain compounding). Promotion decision recorded in the memo; config `GATE_TIER_SIZING_ENABLED` (checkbox, default false) added.
- [ ] **Step 1–4: TDD (replay math on stub folds); run for real; append evidence; commit** — `feat: tier-sizing fold evidence + flag`

### Task G117: Tier sizing live wiring (flag-gated)

**Files:** Modify the position-size call path in `swingbot/commands/scanning.py` / `account.py` integration point; test `tests/test_gate_enforce.py`

**Interfaces:** when `GATE_TIER_SIZING_ENABLED` and enforce mode: computed size × `suggested_size_mult(tier)`; embed sizing line shows the multiplier explicitly (`"½ size — B-tier checklist"`). Off → byte-identical sizing (regression test).
- [ ] **Step 1–4: TDD, commit** — `feat: tier-scaled sizing (flag-gated)`

### Task G118: Phase G3 checkpoint

- [ ] **Step 1:** Full suite + `make check` green; evidence docs (baseline, frontier, ablation, decision memo) committed; permutation p < 0.05 on record — or the documented stop.
- [ ] **Step 2:** Update Progress block. Commit — `chore: phase G3 checkpoint (fold evidence on record)`

---

# Phase G4 — Scan pipeline & alert integration (G119–G146)

The gate meets the live bot. Every task here is flag-gated and ships with a "flags off → byte-identical behavior" regression test.

### Task G119: Scan entry — snapshot + gate context assembly

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_scan_gate_wiring.py`

**Interfaces:** one `GateContext` assembled per scan run (not per ticker): `{macro_snap (G39), open_plans, spy_df, now}`; per-candidate additions (company headlines) fetched lazily inside `run_checklist` callers with the quota meter respected. `GateContext` built even when only `MACRO_ENABLED` (for embeds) — gate checks additionally need `GATE_ENABLED`.
- [ ] **Step 1–4: TDD (one snapshot call per scan regardless of ticker count — counting stub), commit** — `feat: per-scan gate context`

### Task G120: Event blackout scan gate

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_scan_gate_wiring.py`

**Interfaces:** when `GATE_BLACKOUT_ENABLED` and an importance-3 event falls within the blackout window at scan time: **default behavior is annotation** — the plan is created and alerted normally with a prominent warning line ("⚠️ CPI 08:30 ET tomorrow — historically whipsaw-prone; consider waiting for the print"). Only when `GATE_BLACKOUT_ENFORCE` (new checkbox Field, default false) is *also* on are new entries marked `held_for_event` (plan created, alert says "⏸ held — releases after the print") and auto-released by the monitor loop once `hours_until(event) < -GATE_BLACKOUT_HOURS_AFTER`. Stale event calendar (> 7 days unrefreshed) auto-disables holding with a WARN — annotation continues.
- [ ] **Step 1–4: TDD (annotate-only default; hold + release only with enforce flag, on a clock stub; stale-calendar fallback; flags off unchanged), commit** — `feat: event blackout annotate-first, hold opt-in`

### Task G121: Per-candidate gate evaluation in the scan path

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_scan_gate_wiring.py`

**Interfaces:** the alert path calls `run_checklist` per surviving candidate (background thread, same place llm-advisor L14 hooks), applies `decide()` per mode (G76/G103/G106 semantics unified here — shadow/inform always pass), attaches results (G81). Two hard invariants tested here: (1) **inform mode never drops an alert** — property test over arbitrary GateResults including all-fail/hard-block ones; (2) extends the G43 proof through the gate: all providers down → all candidates evaluate with unknowns → **no block ever fires on unknowns** even in enforce mode.
- [ ] **Step 1–4: TDD (both invariants; mode matrix; exception in gate → alert ships ungated + log), commit** — `feat: gate evaluation in scan path (inform never drops, unknown never blocks)`

### Task G122: Alert embed — macro context field

**Files:** Modify `swingbot/core/scanning/embeds.py` (`build_embed`); test `tests/test_embeds_gate.py`

**Interfaces:** `build_embed(..., macro: dict | None = None)` — one field `🌍 Market` valued e.g. `"Risk-ON (+67) · VIX 14.2 calm · Curve normal · Tech leads · CPI in 3d"` built by `render.macro_line(snap)` (added to `gate/render.py`, ≤ 120 chars, unknown-tolerant). `macro=None` → byte-identical embed (regression).
- [ ] **Step 1–4: TDD (golden line; stale marker `"(stale)"`; None regression), commit** — `feat: market context line on alerts`

### Task G123: Alert embed — checklist field

**Files:** Modify `embeds.py`; test `tests/test_embeds_gate.py`

**Interfaces:** `build_embed(..., gate: dict | None = None)` — renders G82's `checklist_field` + (when any flag fired) `redflag_table` as a second field, plus the `advisory_decision` line when enforce-would-have-blocked ("⛔ 2 red flags — plan ships anyway; your call"). Render matrix: `inform` and `enforce` modes render always (**inform is the default — this field is the product**); `shadow` renders only with `GATE_SHOW_IN_SHADOW` (new checkbox field, default false). None → byte-identical.
- [ ] **Step 1–4: TDD (render matrix incl. inform default; advisory line golden; regression), commit** — `feat: checklist field on alerts (inform-first)`

### Task G124: Full breakdown surface

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_embeds_gate.py`

**Interfaces:** the existing breakdown surface (cockpit B10 when present, else follow-up message — mirror llm-advisor L15's degradation pattern) gains the `full_breakdown(result)` chunks: every check, its status emoji, its one-line evidence. This is the checklist *as a readable document* per trade.
- [ ] **Step 1–4: TDD (chunking under 2000-char message limit), commit** — `feat: full checklist breakdown per alert`

### Task G125: Gut-check view on alerts

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_gate_gutcheck.py`

**Interfaces:** alerts for tier ≥ A attach `GutCheckView` (G83); `GATE_GUTCHECK_REQUIRED` mode: the Follow button defers plan-follow until the modal lands (§6 ritual enforced). View timeout 24h; expiry treated as "not answered" (never blocks the plan lifecycle).
- [ ] **Step 1–4: TDD (required-mode ordering; timeout path), commit** — `feat: gut-check ritual on alerts`

### Task G126: Gut-check journaling analytics

**Files:** Modify `persistence.py`; test `tests/test_gate_persistence.py`

**Interfaces:** `gutcheck_stats(journal_entries) -> dict` — WR of trades with vs without a completed gut-check, and the "would I take it after a loss = no, taken anyway" cohort. Surfaces in `!gutcheck` (G156) and the journal browser (G186).
- [ ] **Step 1–4: TDD, commit** — `feat: gut-check outcome stats`

### Task G127: Plan store carries gate + macro at creation

**Files:** Modify the plan-creation path (plan_manager integration point); test `tests/test_gate_persistence.py`

**Interfaces:** every stored plan gains optional keys `gate` (GateResult dict), `macro_at_entry` (the G122 one-liner + composite score + VIX + next event — a compact dict, NOT the full snapshot). Old plans without keys load fine (additive-schema test).
- [ ] **Step 1–4: TDD (round-trip; legacy-load), commit** — `feat: gate+macro stamped on plans`

### Task G128: Re-check at entry trigger

**Files:** Modify the plan-trigger path in the monitor loop; test `tests/test_scan_gate_wiring.py`

**Interfaces:** a pending plan about to trigger re-runs the **cheap** subset (rf_news_whipsaw, rf_thin_session, not_chasing, calendar events — no network beyond the snapshot) via `run_checklist(subset="trigger")` (registry gains a `trigger_recheck: bool` column). A newly-fired flag at trigger time → **the alert message is updated with the new warning and a ping** ("⚠️ since this alert: CPI now within 18h") — the entry still fires normally; it is held per G120 semantics only when `GATE_BLACKOUT_ENFORCE`/enforce mode says so. The signal was checked at alert time; the world may have changed by trigger time — the operator hears about it either way.
- [ ] **Step 1–4: TDD (inform: alert updated + entry fires; enforce+blackout-enforce: held; clean → fires silently), commit** — `feat: trigger-time re-check (inform-first)`

### Task G129: Curated digest respects tiers

**Files:** Modify the digest builder (cockpit insights path); test `tests/test_gate_digest.py`

**Interfaces:** in inform mode the digest lists everything with its tier label leading each row (A+ first); only when enforce mode is on does the curated section restrict to tier ≥ A (WEAK-rule parity: B/C listed in a compact "watch, don't chase" line, never hidden).
- [ ] **Step 1–4: TDD, commit** — `feat: tier-aware digest`

### Task G130: Retrospective gains gate lines

**Files:** Modify `swingbot/core/retrospective.py`; test `tests/test_gate_digest.py`

**Interfaces:** daily retrospective appends (when gate active): `"Gate: N evaluated · X blocked (reasons…) · Y downgraded · shadow divergence Z"` + any G108 audit line due. One line, data from the day's logs; absent data → no line.
- [ ] **Step 1–4: TDD, commit** — `feat: gate lines in retrospective`

### Task G131: Advisor payload integration (v5 present)

**Files:** Modify `swingbot/core/advisor/context.py` **if merged** (capability-checked import); test `tests/test_gate_advisor.py` (skipped when advisor absent)

**Interfaces:** `plan_review_payload` gains `gate: result.to_dict()` and `macro: macro_at_entry`; the advisor's prompt template sentence added: "The checklist verdict is data — critique it, don't parrot it." Advisor absent → no-op module guard, tests skip cleanly.
- [ ] **Step 1–4: TDD (payload contains gate; skip-guard), commit** — `feat: gate context in advisor plan reviews`

### Task G132: Advisor headline nuance job (v5 present)

**Files:** Modify advisor producers **if merged**; test `tests/test_gate_advisor.py`

**Interfaces:** when a candidate fires `rf_rumor_spike` with `unclear` classification and the advisor is enabled+budgeted: a `plan_review` job is enqueued with the headlines attached so Haiku adjudicates rumor-vs-confirmed *advisorily* (result lands via the normal L15 advisor field; the gate's own verdict is never overwritten). Absent advisor → nothing.
- [ ] **Step 1–4: TDD (job enqueued with headlines on the unclear path; gate verdict untouched), commit** — `feat: advisor adjudication of unclear news spikes`

### Task G133: Nightly analysis gains gate stats (v5 present)

**Files:** Modify advisor nightly payload **if merged**; test `tests/test_gate_advisor.py`

**Interfaces:** `nightly_payload` gains the day's gate telemetry + flag-outcome deltas so the local analyst reasons over them (schema untouched — data rides in the existing snapshot section).
- [ ] **Step 1–4: TDD, commit** — `feat: gate stats in nightly advisor payload`

### Task G134: Kill-switch + throttle interop (v4 present)

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_scan_gate_wiring.py`

**Interfaces:** when edge-engine E45–E47 exist: kill-switch active → gate evaluation still runs (annotation continues, evidence keeps accruing) but enforce decisions defer to the kill switch (its "no new entries" outranks any A+ tier); drawdown throttle's size multiplier composes multiplicatively with G117's tier multiplier, floored at 0. Absent edge → no-op.
- [ ] **Step 1–4: TDD (composition math; precedence), commit** — `feat: gate interop with kill switch + throttle`

### Task G135: Gate telemetry counters

**Files:** Create `swingbot/core/gate/telemetry.py`; test `tests/test_gate_telemetry.py`

**Interfaces:** `count(event: str, **labels)` → `data/gate/telemetry.jsonl` (evaluated, blocked{reason}, downgraded, held_for_event, recheck_held, unknown_rate per provider); `summary(since) -> dict` consumed by the retrospective line (G130), admin (G185), and the health page.
- [ ] **Step 1–4: TDD (counter math over synthetic lines), commit** — `feat: gate telemetry`

### Task G136: Scan latency budget with gate on

**Files:** Test `tests/test_scan_gate_perf.py`

- [ ] **Step 1: The test** — a stubbed 60-candidate scan with gate on (warm snapshot, no network) adds < 5 s total vs gate off (marker per G87); plus a unit budget: `GateContext` assembly < 500 ms with warm caches.
- [ ] **Step 2: PASS (batch level extraction / memoize per-ticker frames if not). Step 3: Commit** — `test: scan latency budget with gate`

### Task G137: Alert routing by tier (channel option)

**Files:** Modify `swingbot/commands/scanning.py` + config; test `tests/test_scan_gate_wiring.py`

**Interfaces:** optional `GATE_APLUS_CHANNEL_ID` (int field, 0 = off): A+ alerts additionally mirrored to a dedicated channel (the "only the best" feed the 95% goal actually wants day-to-day). Mirror failure → log, never blocks the main alert.
- [ ] **Step 1–4: TDD (mirror on/off; failure path), commit** — `feat: A+ tier channel mirror`

### Task G138: Config completeness sweep for Phase G4

**Files:** Modify `swingbot/config.py`; test `tests/test_gate_config.py`

**Interfaces:** all Phase-G4 fields present + help texts: `GATE_SHOW_IN_SHADOW`, `GATE_BLACKOUT_ENFORCE`, `GATE_BLACKOUT_HOURS_BEFORE/AFTER`, `GATE_EARNINGS_BLACKOUT_DAYS`, `GATE_GUTCHECK_REQUIRED`, `GATE_TIER_SIZING_ENABLED`, `GATE_APLUS_CHANNEL_ID`, `GATE_MIN_DOLLAR_VOL`, `GATE_CHASE_ATR_MAX`, `GATE_MIN_RR`, `GATE_MAX_CORR_POSITIONS` (the last four are ThresholdSpec-backed per G79 — asserted to resolve through `spec.threshold`). Test asserts every config key referenced by any gate/macro module exists in FIELDS (import-and-introspect sweep).
- [ ] **Step 1–4: TDD, commit** — `feat: gate config completeness`

### Task G139: Startup diagnostics

**Files:** Modify `swingbot/bot_core.py` startup; test `tests/test_gate_telemetry.py`

**Interfaces:** one log block when `GATE_ENABLED` or `MACRO_ENABLED`: mode, min tier, cuts, checks on/off count, FRED/Finnhub key presence, snapshot age, event calendar horizon, quota state — one WARNING per misconfiguration (enforce mode without fold evidence file → auto-fallback to **inform** + loud warning; blackout-enforce on without event data → falls back to annotate-only + warning). Mirrors llm-advisor L30's pattern.
- [ ] **Step 1–4: TDD (on/off/misconfigured matrix via caplog), commit** — `feat: gate startup diagnostics`

### Task G140: E2E offline — clean pass path

**Files:** Test `tests/test_gate_e2e.py`

- [ ] **Step 1: The test** — tmp data dir, fake bot, stubbed providers: scan a G7 clean-uptrend candidate in **inform mode (the default)** + fresh fake snapshot → alert captured with 🌍 and 📋 fields (A-tier, no flags), plan stored with gate+macro stamps, telemetry `evaluated=1 blocked=0`.
- [ ] **Step 2: PASS. Step 3: Commit** — `test: gate e2e clean-pass path (inform)`

### Task G141: E2E offline — flagged-but-ships path (inform) + blocked path (opt-in enforce)

**Files:** Test `tests/test_gate_e2e.py`

- [ ] **Step 1: The inform test (the product's main path)** — a `breakout_and_fail` candidate in **inform mode** → alert SHIPS with tier C, the ⛔ rf_fake_breakout row in the red-flag table, and the advisory line ("plan ships anyway; your call"); plan stored normally (not blocked); telemetry counts `evaluated=1 flagged=1 blocked=0`.
- [ ] **Step 2: The enforce test** — the same candidate after opting into enforce + min-tier A → no alert, plan stored status `blocked`, blocked_log line with rf_fake_breakout reason, retrospective line counts it, `!blocked` (stub) lists it.
- [ ] **Step 3: PASS both. Step 4: Commit** — `test: gate e2e flagged-ships (inform) + blocked (enforce)`

### Task G142: E2E offline — shadow path

**Files:** Test `tests/test_gate_e2e.py`

- [ ] **Step 1: The test** — same failing candidate in shadow mode → alert ships unchanged (byte-compare), shadow_log records the would-block, nothing user-visible differs.
- [ ] **Step 2: PASS. Step 3: Commit** — `test: gate e2e shadow path`

### Task G143: E2E offline — trigger re-check hold

**Files:** Test `tests/test_gate_e2e.py`

- [ ] **Step 1: The test** — plan passes at alert time; clock advances into a CPI blackout before trigger → entry held, alert updated, release after the window fires the entry.
- [ ] **Step 2: PASS. Step 3: Commit** — `test: gate e2e trigger-hold path`

### Task G144: E2E offline — total darkness

**Files:** Test `tests/test_gate_e2e.py`

- [ ] **Step 1: The test** — the G43/G121 invariant end-to-end: all providers raising, empty caches, enforce mode → scan completes, alerts ship, all macro checks `unknown`, zero blocks, one health WARNING.
- [ ] **Step 2: PASS. Step 3: Commit** — `test: gate e2e darkness (unknown never blocks)`

### Task G145: Operator runbook — scan integration

**Files:** Create `docs/gatekeeper-runbook.md`

- [ ] **Step 1: Write it:** the inform-first philosophy up top (checklist = information, plans always ship by default), flag reference table, mode ladder + the optional enforce procedure (G105 gate), what each embed field means, how to relax strictness from the settings page, how to read `!blocked`/`!tierwr`, the darkness behavior, how to hard-off everything fast (`GATE_ENABLED=false` — one switch).
- [ ] **Step 2: Commit** — `docs: gatekeeper operator runbook`

### Task G146: Phase G4 checkpoint

- [ ] **Step 1:** Full suite + `make check` green; all four e2e paths green; flags-off byte-identity regressions green.
- [ ] **Step 2:** Update Progress block. Commit — `chore: phase G4 checkpoint`

---

# Phase G5 — Discord command suite (G147–G166)

All commands render from the saved snapshot / stored artifacts — a command never triggers a provider fetch (except `!macro refresh`, explicitly). Renderers are pure string/embed builders in `swingbot/commands/macro.py` and `gatecheck.py`, tested without a live bot. Every command: help-catalog + `COMMAND_USAGE` entries, empty-state message, slash bridge via the existing `Context.from_interaction` pattern.

### Task G147: `!macro` — the market context dashboard

**Files:** Create `swingbot/commands/macro.py` (registered in `bot_core.py` like other command modules); test `tests/test_commands_macro.py`

**Interfaces:** `!macro` — one embed from `load_snapshot()`: Inflation field (CPI/Core/PPI/PCE yoy + vs-target), Rates field (FF, 2y/10y, curve state), Risk field (VIX regime, credit, dollar, fear/greed), Rotation field (top-3/bottom-3 sectors), Events field (next high-impact + within-24h), News field (sentiment label + top-3 headlines), footer `built_at` + stale marker. `!macro refresh` → `ensure_fresh_snapshot(ttl_min=0)` in a thread, then renders (admin-style confirm). Empty state: "Macro layer off or no snapshot yet — set MACRO_ENABLED and FRED_API_KEY."
- [ ] **Step 1–4: TDD (embed golden over a fixture snapshot; stale marker; empty state; refresh calls rebuild once), commit** — `feat: !macro dashboard`

### Task G148: `!calendar [days]`

**Files:** Modify `macro.py`; test `tests/test_commands_macro.py`

**Interfaces:** `!calendar [days=7]` — upcoming events table (date ET, kind emoji 🏛️ FOMC / 📈 CPI / 👷 NFP / 🏭 PPI / 💰 PCE / 🎯 OPEX / 🏖️ holiday, importance stars), blackout-window rows bolded with "entries held" note when `GATE_BLACKOUT_ENABLED`; cap 20 rows.
- [ ] **Step 1–4: TDD (fixture events → golden table; blackout bolding), commit** — `feat: !calendar`

### Task G149: `!sectors`

**Files:** Modify `macro.py`; test `tests/test_commands_macro.py`

**Interfaces:** `!sectors` — rotation posture line + 11-row table (rank, sector, 1m/3m/6m RS vs SPY with ▲/▼), leaders/laggards summary; data from the snapshot's `sectors` section.
- [ ] **Step 1–4: TDD, commit** — `feat: !sectors rotation table`

### Task G150: `!sentiment`

**Files:** Modify `macro.py`; test `tests/test_commands_macro.py`

**Interfaces:** `!sentiment [ticker]` — market-wide: news sentiment score/label, rumor ratio, fear/greed gauge with the 5-band label; with ticker: company headlines (top 5, each with G36 score emoji and G37 rumor/confirmed tag). Ticker path reads the cached company-news (no fetch); cache miss → "no cached headlines — appears on the next scan".
- [ ] **Step 1–4: TDD (both paths; cache-miss message), commit** — `feat: !sentiment`

### Task G151: `!yields`

**Files:** Modify `macro.py`; test `tests/test_commands_macro.py`

**Interfaces:** `!yields` — 3m/2y/10y/30y rows with daily change arrows, both curve spreads, curve state with the plain-English line ("10y−2y negative: historically a caution flag, not a timing signal"), breakevens.
- [ ] **Step 1–4: TDD, commit** — `feat: !yields`

### Task G152: `!inflation`

**Files:** Modify `macro.py`; test `tests/test_commands_macro.py`

**Interfaces:** `!inflation` — CPI/Core CPI/PPI/PCE/Core PCE yoy + m/m, direction arrows vs prior print, core-PCE-vs-2%-target gap line, next CPI/PPI/PCE print dates from the calendar.
- [ ] **Step 1–4: TDD, commit** — `feat: !inflation`

### Task G153: `!checklist <TICKER>` — on-demand full run

**Files:** Modify `swingbot/commands/gatecheck.py`; test `tests/test_commands_gatecheck.py`

**Interfaces:** `!checklist NVDA [strategy]` — runs `run_checklist` on demand against cached bars + current snapshot (in a thread; strategy defaults to the best-scoring applicable one, stated in the output); renders the G82 field + `full_breakdown` chunks. No plan required — this is the manual pre-trade ritual for trades the operator is eyeing personally. Unknown ticker / no cached bars → helpful error.
- [ ] **Step 1–4: TDD (fixture run golden; no-bars error), commit** — `feat: !checklist on-demand`

### Task G154: `!whycheck <plan_id>`

**Files:** Modify `gatecheck.py`; test `tests/test_commands_gatecheck.py`

**Interfaces:** `!whycheck p_20260714_ab12` — replays the **stored** GateResult from the plan record (never re-evaluates): every check, status, evidence line, plus the macro-at-entry stamp and (if closed) the outcome next to it — the post-mortem view. Missing gate data → "plan pre-dates the gate".
- [ ] **Step 1–4: TDD, commit** — `feat: !whycheck stored-verdict replay`

### Task G155: `!blocked [date]`

**Files:** Modify `gatecheck.py`; test `tests/test_commands_gatecheck.py`

**Interfaces:** `!blocked [YYYY-MM-DD|today]` — reads `blocked.jsonl`: table of blocked/downgraded/held candidates (ticker, strategy, tier, reason chain), so nothing is ever silently suppressed (Global Constraint made visible). Footer: count + "blocked ≠ deleted; see !whycheck".
- [ ] **Step 1–4: TDD, commit** — `feat: !blocked transparency command`

### Task G156: `!gutcheck`

**Files:** Modify `gatecheck.py`; test `tests/test_commands_gatecheck.py`

**Interfaces:** `!gutcheck` — pending gut-checks (alerts awaiting the ritual, with age), plus G126's stats (WR with vs without ritual, the "took it anyway" cohort). The self-accountability mirror.
- [ ] **Step 1–4: TDD, commit** — `feat: !gutcheck`

### Task G157: Slash-command bridges

**Files:** Modify `macro.py`, `gatecheck.py`; test `tests/test_commands_macro.py`

**Interfaces:** `/macro /calendar /sectors /sentiment /yields /inflation /checklist /whycheck /blocked /gutcheck /frontier /tierwr /redflags` via the existing `Context.from_interaction` bridge pattern (verify the exact helper at execution — same one llm-advisor L16 uses).
- [ ] **Step 1–4: TDD (bridge smoke per command), commit** — `feat: slash bridges for macro+gate commands`

### Task G158: Help catalog + usage sweep

**Files:** Modify the help catalog + `COMMAND_USAGE`; test `tests/test_commands_macro.py`

- [ ] **Step 1: Failing test** — every new command has a catalog entry + usage string; help renders them under new sections "Market Context" and "Gatekeeper".
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: help catalog for macro+gate commands`

### Task G159: Macro dashboard chart

**Files:** Modify `swingbot/core/charts/gate_charts.py`; test `tests/test_gate_charts.py`

**Interfaces:** `macro_dashboard_chart(history_rows, path)` — 4-panel PNG from `snapshot_history.jsonl`: composite risk score (30d line), VIX + regime bands, 10y−2y spread, fear/greed gauge history; attached by `!macro` when ≥ 7 history rows exist.
- [ ] **Step 1–4: TDD (render smoke; !macro attaches when eligible), commit** — `feat: macro dashboard chart`

### Task G160: Sector rotation chart

**Files:** Modify `gate_charts.py`; test `tests/test_gate_charts.py`

**Interfaces:** `sector_rotation_chart(rs_rows, path)` — horizontal bar chart, 1m RS bars with 3m markers overlaid, SPY zero-line, sector labels; attached by `!sectors`.
- [ ] **Step 1–4: TDD (render smoke), commit** — `feat: sector rotation chart`

### Task G161: Sentiment/news trend chart

**Files:** Modify `gate_charts.py`; test `tests/test_gate_charts.py`

**Interfaces:** `sentiment_trend_chart(history_rows, path)` — daily aggregate news-sentiment line + fear/greed overlay (30d); attached by `!sentiment` when history suffices.
- [ ] **Step 1–4: TDD (render smoke), commit** — `feat: sentiment trend chart`

### Task G162: `!frontier`/`!tierwr` chart wiring

**Files:** Modify `gatecheck.py`; test `tests/test_commands_gatecheck.py`

**Interfaces:** `!frontier` attaches G111's chart (rendered on demand from the stored artifact to tmp, cleaned after send); `!tierwr` attaches the decile chart (G112). Chart render failure → embed still ships, log only.
- [ ] **Step 1–4: TDD (attachment path; failure tolerance), commit** — `feat: charts on frontier/tierwr`

### Task G163: Alert footer context one-liner

**Files:** Modify `embeds.py`; test `tests/test_embeds_gate.py`

**Interfaces:** when macro data exists but the full 🌍 field is off (`MACRO_ENABLED` on, `GATE_ENABLED` off), the alert footer gains the compact suffix `" · Risk-ON · CPI 3d"` (≤ 40 chars) — context even in minimal mode. Both off → byte-identical footer.
- [ ] **Step 1–4: TDD (matrix), commit** — `feat: footer context one-liner`

### Task G164: Weekly digest macro section

**Files:** Modify the weekly digest builder; test `tests/test_gate_digest.py`

**Interfaces:** weekly digest gains "Market Week" (composite trend, biggest sector rotation move, events next week) + "Gate Week" (evaluated/blocked/tier mix, best/worst flag by outcome) sections, built from history + telemetry; absent data → sections omitted.
- [ ] **Step 1–4: TDD, commit** — `feat: digest macro + gate sections`

### Task G165: Command cooldowns + long-output guards

**Files:** Modify `macro.py`, `gatecheck.py`; test `tests/test_commands_macro.py`

**Interfaces:** per-user 10s cooldown on the render-heavy commands (`!macro`, `!sectors`, `!frontier` — reuse the existing cooldown decorator if the codebase has one, else a small shared one here); every table builder enforces Discord's 1024/2000/6000 limits with explicit truncation markers (tested at the builder level with oversized fixtures).
- [ ] **Step 1–4: TDD (cooldown; truncation goldens), commit** — `feat: cooldowns + output guards`

### Task G166: Phase G5 checkpoint

- [ ] **Step 1:** Full suite + `make check` green; manual smoke in a test channel: `!macro`, `!calendar`, `!sectors`, `!sentiment`, `!yields`, `!inflation`, `!checklist NVDA`, `!frontier` all render with real data (evidence screenshot/paste noted in the Progress block).
- [ ] **Step 2:** Update Progress block. Commit — `chore: phase G5 checkpoint`

---

# Phase G6 — Admin frontend (G167–G196)

Follows every cockpit-v3 Part-3 convention: Flask + Jinja2, vendored Chart.js + morphdom (no CDN), existing auth/CSRF machinery, `/api/*` JSON endpoints backing pages, Flask-test-client tests under `tests/admin/`, empty states everywhere. Pages read the snapshot/artifacts — an admin request never triggers a provider fetch (the one exception: the explicit refresh button, G174).

### Task G167: `GET /api/macro/snapshot`

**Files:** Modify `swingbot/admin/app.py` (or the `api.py` blueprint if cockpit C4 landed); test `tests/admin/test_macro_api.py`

**Interfaces:** returns `load_snapshot() | {}` + `{age_min, stale}` envelope; 200 always (empty snapshot is `{}`, not 404). Existing admin auth applies (session-gated like every other `/api/*` route — verify the exact decorator at execution).
- [ ] **Step 1–4: TDD (authed 200 + shape; unauthed 401/redirect parity with existing routes), commit** — `feat: /api/macro/snapshot`

### Task G168: `GET /api/macro/history?days=30&keys=composite,vix`

**Files:** Modify admin app; test `tests/admin/test_macro_api.py`

**Interfaces:** rows from `snapshot_history.jsonl` filtered/downsampled server-side (≤ 500 points), key allow-list validated (400 on unknown key).
- [ ] **Step 1–4: TDD, commit** — `feat: /api/macro/history`

### Task G169: `GET /api/macro/events?days=30`

**Files:** Modify admin app; test `tests/admin/test_macro_api.py`

**Interfaces:** upcoming + past-7d events with blackout-window annotations; powers the calendar page.
- [ ] **Step 1–4: TDD, commit** — `feat: /api/macro/events`

### Task G170: `GET/POST /api/gate/config`

**Files:** Modify admin app; test `tests/admin/test_gate_api.py`

**Interfaces:** GET → all Gatekeeper fields with current values + per-check registry rows (id, section, weight, enabled, hard_block, backtestable); POST → validated field updates through the **existing settings machinery** (same path the settings page uses — no second config-write implementation), with two guards: switching `GATE_MODE` to enforce requires the G105 evidence file to exist (else 409 + message), and tier-cut edits append an audit line to `data/gate/config_audit.jsonl` (who/when/old/new).
- [ ] **Step 1–4: TDD (GET shape; enforce-guard 409; audit line on cut change), commit** — `feat: gate config API with enforce guard`

### Task G171: `GET /api/gate/results?since=&tier=&flag=`

**Files:** Modify admin app; test `tests/admin/test_gate_api.py`

**Interfaces:** paginated stored GateResults joined to plan status/outcome (from plan store + journal), filterable by tier/flag/strategy; ≤ 100 rows/page.
- [ ] **Step 1–4: TDD (filters; pagination), commit** — `feat: /api/gate/results`

### Task G172: `GET /api/gate/frontier` + `/api/gate/flags`

**Files:** Modify admin app; test `tests/admin/test_gate_api.py`

**Interfaces:** frontier → latest G98 artifact per strategy (404 with hint when never run); flags → G85 live outcome stats + G99 ablation artifact side by side (the backtest-vs-live receipts in one payload).
- [ ] **Step 1–4: TDD, commit** — `feat: frontier + flags APIs`

### Task G173: `GET /api/gate/blocked?date=` + `GET /api/gate/telemetry?days=`

**Files:** Modify admin app; test `tests/admin/test_gate_api.py`

**Interfaces:** blocked/held/downgraded rows; telemetry summary (G135) bucketed daily.
- [ ] **Step 1–4: TDD, commit** — `feat: blocked + telemetry APIs`

### Task G174: Macro dashboard page `/macro`

**Files:** Modify admin app + nav; create `templates/macro.html`; test `tests/admin/test_macro_pages.py`

**Interfaces:** tile grid (CPI, Core PCE vs target, PPI, unemployment, Fed funds, 2y/10y + curve badge, VIX + regime badge, credit, dollar, fear/greed gauge, composite risk banner colored by label), each tile: value, as-of date, direction arrow; stale banner when snapshot old; **Refresh button** POSTs `/api/macro/refresh` (added here: triggers `ensure_fresh_snapshot(ttl_min=0)` in a background thread, 202 + poll). Empty state when `MACRO_ENABLED` off explains setup.
- [ ] **Step 1–4: TDD (200 authed, tiles render from fixture snapshot, refresh 202, empty state), commit** — `feat: /macro dashboard page`

### Task G175: Yields & curve chart panel

**Files:** Modify `templates/macro.html` + static JS; test `tests/admin/test_macro_pages.py`

**Interfaces:** Chart.js line panel on `/macro`: 10y−2y and 10y−3m spreads (30/90/365d toggles) from `/api/macro/history`, zero-line annotated "inversion"; renders nothing gracefully with < 2 points.
- [ ] **Step 1–4: TDD (page includes the canvas + data endpoint wiring; JS logic kept declarative-minimal per cockpit convention), commit** — `feat: curve chart panel`

### Task G176: Inflation trend panel

**Files:** Modify `templates/macro.html`; test `tests/admin/test_macro_pages.py`

**Interfaces:** CPI/Core CPI/Core PCE yoy lines (2y window from `data/macro/history/`, served by a small `/api/macro/series?key=` addition, allow-listed), 2% target hline.
- [ ] **Step 1–4: TDD, commit** — `feat: inflation trend panel`

### Task G177: Sector rotation heatmap page `/sectors`

**Files:** Modify admin app + nav; create `templates/sectors.html`; test `tests/admin/test_macro_pages.py`

**Interfaces:** 11×3 grid (sector × window) colored by RS sign/magnitude (CSS classes, no chart lib needed), posture banner, leaders/laggards lists, per-sector sparkline (Chart.js) of composite rank history.
- [ ] **Step 1–4: TDD, commit** — `feat: /sectors rotation page`

### Task G178: Breadth + sentiment panels on `/macro`

**Files:** Modify `templates/macro.html`; test `tests/admin/test_macro_pages.py`

**Interfaces:** breadth tile pair (%>50DMA, %>200DMA with health badge) + news panel (top-10 headlines with sentiment emoji + rumor/confirmed tag, aggregate score, rumor ratio).
- [ ] **Step 1–4: TDD, commit** — `feat: breadth + news panels`

### Task G179: Event calendar page `/events`

**Files:** Modify admin app + nav; create `templates/events.html`; test `tests/admin/test_macro_pages.py`

**Interfaces:** month grid (pure Jinja, no JS calendar lib): event chips by kind, blackout windows shaded, opex/holidays marked; list view fallback below (accessible + mobile); prev/next month URLs.
- [ ] **Step 1–4: TDD (grid renders fixture month; blackout shading class present), commit** — `feat: /events calendar page`

### Task G180: Checklist config page `/gate`

**Files:** Modify admin app + nav; create `templates/gate.html`; test `tests/admin/test_gate_pages.py`

**Interfaces:** sections: mode/master switches (mode selector with plain-language descriptions — "Inform (default): every plan alerts, checklist annotates" / "Enforce: below-tier plans are held back" — enforce-guard message surfaced from G170's 409), **strictness panel** (the `GATE_STRICTNESS` preset selector with a one-click "Relax all" affordance + per-check threshold sliders generated from the G79 ThresholdSpec fields, each labeled with its relax direction and preset markers on the slider track, overridden thresholds visually badged), tier cuts (sliders + current fold-evidence values shown beside for comparison), per-check table (enable toggle, weight read-only + "weights change via evidence, not sliders" note, hard-block badge, applies-to list), blackout window settings (with the annotate-vs-hold distinction spelled out). All writes through `/api/gate/config`.
- [ ] **Step 1–4: TDD (200; toggles POST; preset apply POST reseeds thresholds; enforce guard surfaced; slider fields present for every ThresholdSpec), commit** — `feat: /gate config page with strictness presets + threshold sliders`

### Task G181: Red-flag analytics page `/gate/flags`

**Files:** Modify admin app + nav; create `templates/gate_flags.html`; test `tests/admin/test_gate_pages.py`

**Interfaces:** per-flag row: backtest ablation numbers (G99) vs live outcome numbers (G85) side by side, fire-rate trend sparkline, "earning its keep?" verdict cell (green when live delta agrees with folds, amber when N < 20, red when contradicting); links each flag to its registry docstring rendered as help text.
- [ ] **Step 1–4: TDD, commit** — `feat: /gate/flags analytics page`

### Task G182: Frontier page `/gate/frontier`

**Files:** Modify admin app + nav; create `templates/gate_frontier.html`; test `tests/admin/test_gate_pages.py`

**Interfaces:** per-strategy frontier table + Chart.js dual-axis chart (mirror of G111), a **client-side threshold slider** that highlights the corresponding row and shows `{WR, Wilson LB, kept%, expectancy, trades/mo}` live (pure JS over the already-served rows — no server round-trip), current configured cut marked; "propose as tier cut" button writes a proposal file via `POST /api/gate/propose` (C36 shape — proposals, never direct config writes from this page).
- [ ] **Step 1–4: TDD (rows served; propose endpoint writes proposal file), commit** — `feat: /gate/frontier interactive page`

### Task G183: Blocked-log viewer `/gate/blocked`

**Files:** Modify admin app + nav; create `templates/gate_blocked.html`; test `tests/admin/test_gate_pages.py`

**Interfaces:** filterable table (date, ticker, strategy, tier, decision, reason chain, link to plan detail if cockpit's plan pages exist), daily counts chart, CSV export link (`?format=csv`).
- [ ] **Step 1–4: TDD (filters; CSV content-type), commit** — `feat: /gate/blocked viewer`

### Task G184: Gut-check journal browser section

**Files:** Modify the journal browser template (cockpit C-phase) if present, else a section on `/gate`; test `tests/admin/test_gate_pages.py`

**Interfaces:** gut-check entries (plan, the "why I'd be wrong" sentence, the after-a-loss answer, outcome), plus G126 stats header. Capability-checked against the journal browser's existence.
- [ ] **Step 1–4: TDD, commit** — `feat: gut-check browser`

### Task G185: Live gate status fragment on the dashboard

**Files:** Modify the admin dashboard template + its morphdom fragment endpoint; test `tests/admin/test_gate_pages.py`

**Interfaces:** dashboard card: gate mode badge, today's evaluated/blocked/held counts, snapshot age, provider health dots (green/amber/red from G10), next high-impact event countdown. Auto-refreshes with the existing fragment cadence.
- [ ] **Step 1–4: TDD (fragment renders counts from fixture telemetry), commit** — `feat: gate status dashboard card`

### Task G186: Provider health page `/macro/health`

**Files:** Modify admin app + nav; create `templates/macro_health.html`; test `tests/admin/test_macro_pages.py`

**Interfaces:** per-provider: status dot, ok-rate 24h, last success/error, calls today vs quota bar, cache hit rate, last-served-stale flag; snapshot quality warnings (G42) listed; a "test fetch" button per provider (POST, runs one live probe in a thread, 202 + result poll — the only other admin-triggered network path, admin-auth + rate-limited 1/min).
- [ ] **Step 1–4: TDD (page + quota bars from fixture ledger; probe rate-limit 429), commit** — `feat: /macro/health page`

### Task G187: Quality warnings surfacing

**Files:** Modify `templates/macro.html`, dashboard card; test `tests/admin/test_macro_pages.py`

**Interfaces:** `quality_warnings` from the snapshot render as a dismissible amber banner on `/macro` + a warning count on the dashboard card; empty → nothing.
- [ ] **Step 1–4: TDD, commit** — `feat: macro quality warnings banner`

### Task G188: Config audit trail viewer

**Files:** Modify `templates/gate.html`; test `tests/admin/test_gate_pages.py`

**Interfaces:** collapsible "change history" section reading `config_audit.jsonl` (G170): when, what, old→new — tier cuts and mode flips are risk decisions and deserve receipts.
- [ ] **Step 1–4: TDD, commit** — `feat: gate config audit viewer`

### Task G189: Navigation + empty states sweep

**Files:** Modify the admin nav template + all new templates; test `tests/admin/test_gate_pages.py`

- [ ] **Step 1: Failing test** — nav contains Macro, Sectors, Events, Gate (with sub-links), Health; every new page returns 200 with **zero** data files present and shows its empty-state copy (parametrized test over all new routes with a bare tmp data dir).
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: nav + empty states for all gate/macro pages`

### Task G190: Auth/CSRF parity test

**Files:** Test `tests/admin/test_gate_pages.py`

- [ ] **Step 1: The test** — parametrized over every new GET route: unauthenticated → same redirect/401 behavior as existing pages; every new POST route: missing CSRF token → rejected (matching the existing settings-POST behavior exactly — read that test first).
- [ ] **Step 2: PASS (fix any route that slipped). Step 3: Commit** — `test: auth/CSRF parity for new admin surface`

### Task G191: Fragment live-refresh wiring

**Files:** Modify the morphdom refresh registry (cockpit pattern); test `tests/admin/test_gate_pages.py`

**Interfaces:** `/macro` tiles and the dashboard gate card join the existing periodic fragment refresh (same interval constants); charts re-render only on data change (hash guard) to avoid flicker.
- [ ] **Step 1–4: TDD (fragment endpoints registered; hash guard skips unchanged), commit** — `feat: live refresh for macro fragments`

### Task G192: Mobile pass

**Files:** Modify new templates/CSS; test `tests/admin/test_gate_pages.py` (structural assertions only)

- [ ] **Step 1:** Tile grids collapse to 2-col/1-col via the existing responsive CSS conventions; tables gain horizontal-scroll wrappers; the events month grid falls back to the list view below 640px (CSS, not JS). Structural test: wrapper classes present.
- [ ] **Step 2–4: Implement, PASS, commit** — `style: mobile pass for macro/gate pages`

### Task G193: Admin e2e — fixture-city walkthrough

**Files:** Test `tests/admin/test_gate_e2e.py`

- [ ] **Step 1: The test** — seed a full fixture city (snapshot, history, events, gate results, blocked log, frontier artifact, telemetry) in tmp data dir → walk every new page + API with the test client, assert key numbers thread through consistently (the composite score shown on `/macro` equals the API's, the frontier cut on `/gate/frontier` equals the artifact's).
- [ ] **Step 2: PASS. Step 3: Commit** — `test: admin gate/macro e2e walkthrough`

### Task G194: Accessibility pass

**Files:** Modify new templates; test structural assertions

- [ ] **Step 1:** Color-coded cells (heatmap, health dots, tier badges) all carry text/aria equivalents (rank numbers, status words); charts get `aria-label` summaries; contrast per the existing admin palette. Structural test: no color-only cell (grep-level assertion on templates for the badge classes requiring text content).
- [ ] **Step 2–4: Implement, PASS, commit** — `style: a11y pass (no color-only information)`

### Task G195: Visual QA checklist

**Files:** Create `docs/superpowers/results/2026-07-gate-admin-qa.md`

- [ ] **Step 1:** Manual pass with real data: each page screenshotted at desktop + mobile width, charts sane, dark-mode parity if the admin has it (match existing behavior), notes filed as issues-to-fix inline. Fix what's broken before checking the box.
- [ ] **Step 2: Commit** — `docs: gate/macro admin visual QA`

### Task G196: Phase G6 checkpoint

- [ ] **Step 1:** Full suite + `make check` green; e2e walkthrough green; QA doc committed.
- [ ] **Step 2:** Update Progress block. Commit — `chore: phase G6 checkpoint`

---

# Phase G7 — Ops, governance & wrap-up (G197–G216)

### Task G197: Cache janitor

**Files:** Modify `swingbot/core/macro/httpcache.py` + the monitor loop; test `tests/test_macro_httpcache.py`

**Interfaces:** nightly `purge_cache(30)` + `data/macro/history/` size check wired into the existing maintenance cadence (wherever the session-end hooks run — same spot the retrospective posts); one log line with bytes freed.
- [ ] **Step 1–4: TDD (purge wired via clock stub), commit** — `feat: macro cache janitor`

### Task G198: Disk-usage cap

**Files:** Modify `httpcache.py`, `telemetry.py`; test `tests/test_macro_httpcache.py`

**Interfaces:** `data/macro/` + `data/gate/` combined soft cap 200 MB: over the cap → oldest cache/telemetry files pruned first (never `event_history.json`, `history/` series, or `blocked.jsonl` — the audit trail is sacred), WARN logged.
- [ ] **Step 1–4: TDD (prune order; protected files survive), commit** — `feat: disk-usage cap with protected audit files`

### Task G199: Provider outage alerting

**Files:** Modify the monitor loop; test `tests/test_gate_telemetry.py`

**Interfaces:** a provider degraded (G10) for > 12h → one Discord warning per provider per day to the retrospective channel ("FRED degraded since …, macro checks running as unknown — nothing is blocking on missing data"); recovery posts an all-clear once.
- [ ] **Step 1–4: TDD (once-per-day dedup; recovery line), commit** — `feat: provider outage alerts`

### Task G200: Quota budget report

**Files:** Modify `health.py`; test `tests/test_macro_health.py`

**Interfaces:** `quota_report() -> dict` — per provider: calls today, projected daily total at current cadence, headroom %; WARN into snapshot quality when projection > 80% of quota; shown on `/macro/health` (G186 wires the field) and in startup diagnostics.
- [ ] **Step 1–4: TDD (projection math), commit** — `feat: quota budget projection`

### Task G201: Secrets hygiene audit

**Files:** Test `tests/test_gate_secrets.py`

- [ ] **Step 1: The test** — grep-level assertions over `swingbot/core/macro/` + `swingbot/core/gate/`: no module logs a variable named `*_API_KEY`; `fetch_json` redacts `api_key`/`token` params from every log/exception message and from cache keys' readable form (keys hashed — assert a crafted URL's key doesn't contain the secret); config Fields for keys are `sensitive=True`.
- [ ] **Step 2: PASS (fix any leak found). Step 3: Commit** — `test: secrets never logged or cached in the clear`

### Task G202: Backfill + rebuild runbook hardening

**Files:** Modify `scripts/backfill_macro.py`, `scripts/build_event_history.py`; docs section in `docs/gatekeeper-runbook.md`

**Interfaces:** both scripts gain `--dry-run`, `--only <key>`, resume-on-partial (skip existing unless `--force`), and exit-code discipline; runbook gains the "rebuild from nothing" procedure (fresh clone → keys → backfill → event history → smoke → first snapshot) with expected durations.
- [ ] **Step 1–4: TDD (arg handling, resume logic — network stubbed); update runbook; commit** — `feat: hardened backfill scripts + rebuild runbook`

### Task G203: Weekly gate-effectiveness report

**Files:** Modify `swingbot/commands/scanning.py` (Sunday hook, llm-advisor L13 cadence pattern); test `tests/test_gate_audit.py`

**Interfaces:** `weekly_gate_report(now) -> str | None` — Sundays: the week's shadow/enforce divergence, flag receipts delta, tier WR movement (all `fmt_wr`-guarded), quota + health summary, posted to the retrospective channel + saved `data/gate/weekly/{ISO-week}.json`. Idempotent per week.
- [ ] **Step 1–4: TDD (Sunday-only; idempotent; golden text over fixtures), commit** — `feat: weekly gate-effectiveness report`

### Task G204: Monthly WR honesty audit

**Files:** Modify the G108 audit; test `tests/test_gate_audit.py`

**Interfaces:** the monthly audit gains the honesty banner logic: per strategy, live WR (Wilson LB) vs the G2 target band → status line `"RSI-Div: 87% observed (LB 81%, N=41) — target band met / not yet provable / drifting"`; **never** renders an unproven "95%" — the exact string `95` may appear only when `wilson_lower_bound > 0.90` (unit-tested string guard, the plan's promise made executable).
- [ ] **Step 1–4: TDD (the 95-string guard; band statuses), commit** — `feat: monthly WR honesty audit`

### Task G205: Quarterly re-validation hook

**Files:** Modify the audit module; docs note; test `tests/test_gate_audit.py`

**Interfaces:** first audit of each quarter additionally: re-runs the fold suite via `scripts/gate_fold_run.py --all` **on TRAIN only** (subprocess, background), diffs chosen cuts vs current config defaults, posts "re-validation drift" summary + writes a proposal file when drift exceeds the plateau tolerance (G101). Extends edge E96's cron if merged (one quarterly job, two payloads) — capability-checked.
- [ ] **Step 1–4: TDD (quarter boundary; proposal-on-drift; subprocess mocked), commit** — `feat: quarterly re-validation`

### Task G206: 4-week paper forward-gate for the A+ channel

**Files:** Create `docs/superpowers/results/2026-08-gate-forward-test.md` (template now, filled during the gate)

- [ ] **Step 1: Write the template + procedure:** after enforce-mode promotion (G105/G106), run 4 calendar weeks where A+ alerts are paper-tracked as their own cohort; the doc pre-registers what "pass" means (A+ live WR Wilson LB ≥ B-tier live WR; no expectancy degradation; ≥ 10 A+ signals) and what happens on fail (tier cuts revert to proposal state, gate stays enforce at min-tier B).
- [ ] **Step 2: Commit** — `docs: A+ forward-gate template (pre-registered)`

### Task G207: Promotion + rollback runbook

**Files:** Modify `docs/gatekeeper-runbook.md`

- [ ] **Step 1: Write the full ladder as an operator checklist:** **inform (default, most operators stop here — the checklist annotates, you decide)** → optionally: (G105 evidence) → enforce min-tier B → (G206 forward gate) → enforce chosen tiers → tier sizing (G116 evidence) — and the rollback for every rung (single flag each, data preserved, what to watch after; every rollback lands back on inform, never on off). Include: the "too strict / no A-tier plans in a week" procedure (switch `GATE_STRICTNESS` to relaxed or drag individual sliders on `/gate` — with the reminder that loosening changes labels, not the underlying stats), and the "incident: enforce blocked something it shouldn't" procedure (flip to inform, `!whycheck`, file the check bug, never hand-edit a stored result).
- [ ] **Step 2: Commit** — `docs: promotion + rollback ladder`

### Task G208: Pre-mortem

**Files:** Create `docs/superpowers/results/2026-07-gate-premortem.md`

- [ ] **Step 1: Write it (edge E95 pattern), covering at minimum:** overfit-to-folds (mitigation: permutation + plateau + sentinel), macro provider drift/silent schema change (quality validator + smoke), the gate blocking the exact trades that made the system work (shadow comparison + `!blocked` visibility), operator abandons the checklist when it disagrees with gut (receipts commands + monthly audit), free-tier quota death (meter + degradation), event-calendar staleness blocking entries wrongly (staleness auto-disables blackout with warning — verify G120 implements this; if not, fix in this task), and lookahead bugs in backtest context (G90's trap tests as the canary).
- [ ] **Step 2: Commit** — `docs: gatekeeper pre-mortem`

### Task G209: README section

**Files:** Modify `README.md`

- [ ] **Step 1:** "Gatekeeper & Market Context" section: what it does, what it will never do (the honesty ladder, verbatim from the header), the two API keys and their free tiers, command list, the shadow-first philosophy, pointer to the runbook.
- [ ] **Step 2: Commit** — `docs: README gatekeeper section`

### Task G210: Deploy notes

**Files:** Modify `DEPLOY_HETZNER.md`

- [ ] **Step 1:** New env/config keys, `data/macro` + `data/gate` dirs in backup scope (audit files!), backfill as a deploy step, quota notes for the server's timezone/cadence, memory footprint note (history frames lazy-loaded).
- [ ] **Step 2: Commit** — `docs: deploy notes for gatekeeper`

### Task G211: `.env.example` + settings surface sweep

**Files:** Modify `.env.example` (if present) + verify the admin settings page renders the Gatekeeper section

- [ ] **Step 1:** `FRED_API_KEY=`, `FINNHUB_API_KEY=` documented with sign-up URLs; settings page shows all Gatekeeper fields grouped (FIELDS-driven — should be automatic; test asserts the section renders).
- [ ] **Step 2–4: TDD (settings page section present), commit** — `chore: env example + settings surface`

### Task G212: Dependency + import hygiene audit

**Files:** Test `tests/test_gate_imports.py`

- [ ] **Step 1: The test** — `swingbot/core/gate/` pure modules (types, score, wr_math, frontier, all check modules) import neither `requests` nor `config`-path I/O (AST-level check, cockpit A-phase precedent); `swingbot/core/macro/` imports no discord; `requirements.txt` unchanged by this whole plan (git-diff assertion documented as a manual step, import assertion automated).
- [ ] **Step 2: PASS (refactor violations). Step 3: Commit** — `test: gate/macro import hygiene`

### Task G213: Full-suite performance budget

**Files:** Test `tests/test_gate_suite_perf.py` + measurement note

- [ ] **Step 1:** The new test modules collectively add < 60 s to the suite on the dev machine (measure, record in the test's docstring); mark the worst offenders `@pytest.mark.slow` consistent with existing markers if over.
- [ ] **Step 2: PASS. Step 3: Commit** — `test: suite time budget for gate/macro`

### Task G214: Lint/type sweep

- [ ] **Step 1:** `make check` + the repo's lint config over every new file; fix all findings (no suppressions without an inline reason).
- [ ] **Step 2: Commit** — `chore: lint sweep for gatekeeper`

### Task G215: Live smoke — the full ritual, end to end

**Files:** Update the Progress block with evidence notes

- [ ] **Step 1: In order, on the real bot with real keys:** (a) `scripts/macro_smoke.py` green; (b) `!macro`, `!calendar`, `!sectors`, `!sentiment`, `!yields`, `!inflation` in a test channel; (c) enable `MACRO_ENABLED` + `GATE_ENABLED` (**inform mode, the default**) → trigger a scan → alert with 🌍 + 📋 fields, red flags rendered when fired, plan created regardless of tier; (d) `!checklist NVDA` full run; (e) `/macro`, `/gate` (drag a threshold slider, apply the relaxed preset, watch the next scan's tiers shift), `/events`, `/macro/health` admin pages with live data; (f) blackout dry-run: set a fake imminent event in a test copy of the calendar, verify the annotation appears while the plan still ships (and hold/release only with `GATE_BLACKOUT_ENFORCE`); (g) confirm zero blocks occurred in inform mode (telemetry `blocked=0` — the invariant, live) and the darkness test still passes offline.
- [ ] **Step 2: Note evidence in the Progress block. Commit** — `chore: live smoke evidence`

### Task G216: Final checkpoint — plan complete

- [ ] **Step 1:** Full suite + `make check` green. All evidence docs committed (baseline, frontier, ablation, decision memo, QA, pre-mortem).
- [ ] **Step 2:** Enforce mode is **deliberately not** part of this plan's completion — it is an optional rung the operator may never climb. The plan is complete when **inform mode runs live**: every alert annotated, nothing blocked, thresholds tunable from `/gate`, and the evidence pipeline (`!tierwr`, shadow reports, receipts) full.
- [ ] **Step 3:** Update Progress block (Completed: G1–G216). Commit — `chore: gatekeeper v6 complete (inform mode live, enforce stays optional)`

---

# Appendix — Checklist-to-task traceability

Every line of the operator's Pre-Trade Entry Checklist, and where it became code:

| Checklist item | Tasks |
|---|---|
| §1 HTF trend known, not against it | G45, G46 |
| §1 Major S/R, prior swings, round numbers marked | G47, G48, G49 |
| §1 Volatility normal (not compressed/spiked) | G50, G51 |
| §2 Pattern fully closed/confirmed | G52 (hard block) |
| §2 ≥ 2 independent signals agree | G53 |
| §2 Volume/momentum supports the move | G54, G55, G56 |
| §3 Fake breakout | G57 |
| §3 Stop-loss sweep | G58 |
| §3 Dead cat bounce | G59 |
| §3 Divergence trap | G60 |
| §3 Overbought/oversold fade | G61 |
| §3 News whipsaw (CPI/NFP/rate/earnings due) | G29, G30, G62, G120, G128 |
| §3 Rumor-driven spike | G34–G37, G63, G132 |
| §3 Buy-rumor-sell-fact | G64 |
| §3 Low-liquidity session | G32, G65 |
| §3 Options expiry pin | G31, G66 |
| §3 Correlated-asset move | G67 |
| §4 Stop beyond structure, widened ~1 ATR | G68 |
| §4 Size from risk % ÷ stop distance | G69 |
| §4 R:R ≥ 1.5–2 to a realistic target | G70 |
| §5 Objective entry trigger | G72 (hard block) |
| §5 Not chasing | G73 |
| §5 Economic calendar checked | G74 (+ G39: checked before *every* scan) |
| §6 Matches a strategy in the plan | inherent (bot only trades registered strategies) + G80 |
| §6 Would take it after a loss | G83, G126 |
| §6 One sentence why I'd be wrong | G83, G125, G184 |
| Golden rule: volume + follow-through | G54 (volume), G57/G58 (follow-through traps) |
| "Grab news/sentiment/rotation/CPI/PPI/treasury before every trade" | G9–G44, G39 (pre-scan), G119, G122, G147–G152 |
| "Size down significantly if boxes unchecked" | G77, G116, G117 |
| "Checklist informs, never gates — plan always ships, user decides" | G76, G106, G120, G121, G123, G128, G141 |
| "Settings fields to relax the strict constraints" | G5 (ThresholdSpec), G79 (fields + presets), G180 (sliders + one-click relax) |
| "Improve winrate toward 95%" (final target) | G1, G2, G93–G102, G114, G204 — the ladder, measured |
