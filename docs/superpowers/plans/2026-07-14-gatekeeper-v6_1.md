# Gatekeeper v6 - Part 1/11: Honest math, contracts & scaffolding (Tasks G1-G8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute strictly in order (G1 -> G8).
>
> **Split note:** this is part 1 of 11, extracted verbatim from the master plan `2026-07-14-gatekeeper-v6.md` (which stays as the reference copy; the checklist-to-task traceability appendix is in Part 11). Parts execute in numeric order.
> **Requires complete first:** none within this plan - only the master Prerequisites below.
>
> Cross-part references (task numbers like G38, file names, `Interfaces:` blocks) refer to work done in earlier parts - those modules exist on the branch by the time this part runs.

## Progress

> Updated by the executing session after each task batch. Resume from the first unchecked task.
>
> - **Branch:** `feature/gatekeeper-v6`
> - **Completed:** —
> - **Next:** Task G1

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
