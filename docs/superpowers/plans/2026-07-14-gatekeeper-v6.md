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

- [ ] **Step 2: Run — FAIL (module missing). Step 3: Implement the four pure functions (docstrings show the hand-derived golden numbers). Step 4: PASS. Step 5: Commit** — `feat: gate win-rate arithmetic (breakeven, implied E, filter precision, Wilson)`

### Task G2: Pre-registered targets & promotion gates document

**Files:**
- Create: `docs/superpowers/specs/2026-07-14-gatekeeper-v6-targets.md`

- [ ] **Step 1: Write the frozen targets doc** — verbatim content: the tier ladder (A+ ≥ 90% pooled fold WR aspiration with 95-class labeling rule, A ≥ target band, B = baseline, C = skip-in-live), the fold gate (≥2/3 folds, ≤0.05R degradation, N≥30), the shadow gate (2 calendar weeks live shadow, ≥ 15 shadow decisions, blocked cohort's realized WR must be *lower* than the passed cohort's), the all-strategies aggregate target (+3–8 WR pts at ≤40% signal loss), and the explicit non-promise sentence: *"95% is a label a tier can earn from N≥59 proven samples (Wilson LB > 90%) — never a setting."* Include the checklist→task traceability appendix pointer (end of this plan).
- [ ] **Step 2: Commit** — `docs: gatekeeper v6 pre-registered targets (frozen before data contact)`

### Task G3: Config section "Gatekeeper" — base flags

**Files:**
- Modify: `swingbot/config.py`
- Test: `tests/test_gate_config.py`

**Interfaces:**
- Produces Fields (section `"Gatekeeper"`, all default off/neutral): `GATE_ENABLED` (checkbox, false — master switch), `GATE_MODE` (select `shadow`|`inform`|`enforce`, default `inform` — inform renders the checklist on every alert and never blocks; enforce is opt-in and guarded by G170), `GATE_MIN_TIER` (select `A+`|`A`|`B`|`C`, default `C`; **consulted only in enforce mode**), `GATE_STRICTNESS` (select `strict`|`balanced`|`relaxed`, default `balanced` — preset seeding for the G79 threshold fields), `MACRO_ENABLED` (checkbox, false), `FRED_API_KEY` (password, sensitive), `MACRO_SNAPSHOT_TTL_MIN` (int, 30, min 5), `GATE_BLACKOUT_ENABLED` (checkbox, false — annotate-only; holding entries additionally requires `GATE_BLACKOUT_ENFORCE`, G120). (`FINNHUB_API_KEY` already exists from llm-advisor L10; if that plan is unmerged, add it here with the same shape.)

- [ ] **Step 1: Failing test** — each key present in `{f.key for f in config.FIELDS}`, section label correct, defaults as specified, key fields marked sensitive.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: Gatekeeper config section (default off)`

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

- [ ] **Step 1: Failing tests** — round-trip `to_dict`/`from_dict`; frozen; unknown-weight exclusion helper `scoreable(checks)` returns only pass/warn/fail.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: gate result types`

### Task G5: Check registry + policy table

**Files:**
- Create: `swingbot/core/gate/registry.py`
- Test: `tests/test_gate_registry.py`

**Interfaces:**
- Produces: `CHECKS: dict[str, CheckSpec]` — `CheckSpec(check_id, section, weight, hard_block: bool, applies_to: tuple[str,...] | None, backtestable: bool, config_flag: str, thresholds: dict[str, ThresholdSpec])` where `ThresholdSpec(name, default, min, max, step, relax_direction: str, presets: dict[str, float])` (`presets` carries the strict/balanced/relaxed values; `relax_direction` is the help-text sentence, e.g. "raise to allow later entries"). Check functions read thresholds via `spec.threshold(name)` (config-Field-backed, G79) — never module constants; one entry per check built in Phases G1–G2 (registered incrementally — each later task adds its row and this module's test asserts registry consistency: unique ids, sections valid, weights ≥ 0, every `config_flag` exists in `config.FIELDS`). `applies_to=None` = all strategies. `enabled_checks(strategy) -> list[CheckSpec]`.
- Hard-block policy: `hard_block=True` checks (news whipsaw inside blackout, kill-switch conflict, unconfirmed signal bar) force tier C on `fail` even at score 100.

- [ ] **Step 1: Failing tests** — registry invariants; `enabled_checks` filters by strategy + config flag off.
- [ ] **Step 2–4: Implement with the initial empty-but-typed registry + invariant machinery, PASS, commit** — `feat: gate check registry + policy`

### Task G6: Checklist score + tier assignment

**Files:**
- Create: `swingbot/core/gate/score.py`
- Test: `tests/test_gate_score.py`

**Interfaces:**
- Produces: `score(checks: Sequence[CheckResult]) -> float` — weighted: pass=1.0, warn=0.5, fail=0.0, unknown excluded from denominator; empty/all-unknown → 50.0 (neutral) with `macro_stale` responsibility on the caller. `assign_tier(score: float, hard_blocks: Sequence[str], *, aplus_cut: float, a_cut: float, b_cut: float) -> str` — cuts come from config (G79); any hard block → "C". `TIER_ORDER = ("A+", "A", "B", "C")`.

- [ ] **Step 1: Failing tests** — golden score for a mixed fixture (2 pass w=10, 1 warn w=10, 1 fail w=20, 1 unknown w=50 → (10+10+5+0)/40*100 = 62.5); hard block forces C at score 100; all-unknown neutral 50.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: checklist scoring + tier ladder`

### Task G7: Golden OHLCV scenario fixture library

**Files:**
- Create: `tests/fixtures/gate/__init__.py` (builders), `tests/fixtures/gate/scenarios.py`
- Test: `tests/test_gate_fixtures.py`

**Interfaces:**
- Produces deterministic bar-series builders reused by every detector test (extends `tests/conftest.py`'s real `make_ohlcv(closes, spread_pct, ...)` — verify its actual signature before writing): `uptrend_daily(n=260)`, `downtrend_daily(n=260)`, `range_daily(lo, hi, n=120)`, `breakout_and_fail(level)` (closes back inside next bar, low volume), `sweep_wick(level)` (long lower wick through level, close back above), `dead_cat(n_down=40, bounce_pct=8)` (no higher-low structure), `climax_overbought()` (RSI>75 into resistance), `gap_spike(pct=12)` (news-gap bar, volume 5×), plus weekly resamples `to_weekly(df)`.

- [ ] **Step 1: Failing tests** — each builder's shape assertions (monotone trend slope sign, wick geometry, volume ratios) so detectors built later have trustworthy inputs.
- [ ] **Step 2–4: Implement, PASS, commit** — `test: golden gate scenario fixtures`

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

- [ ] **Step 1: Failing tests** — monkeypatched `requests.get`: fresh-hit skips network (counting stub); expiry refetches; failure serves stale; failure without cache → None; purge removes only old files.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: macro http fetch with TTL disk cache + stale fallback`

### Task G10: Provider health ledger

**Files:**
- Create: `swingbot/core/macro/health.py`
- Test: `tests/test_macro_health.py`

**Interfaces:**
- Produces: `record_call(provider: str, ok: bool, latency_ms: float, from_cache: bool)` → appends `data/macro/health.jsonl`; `provider_status() -> dict[str, dict]` (`{ok_rate_24h, last_ok, last_error, calls_today, cache_hit_rate}`); `is_degraded(provider) -> bool` (ok_rate_24h < 0.5). Wired into `fetch_json` via a `provider=` kwarg (modify G9's signature now, one place).

- [ ] **Step 1: Failing tests** — ledger math over synthetic lines; degraded flip; `fetch_json(provider=...)` records.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: provider health ledger`

### Task G11: Quota meter (free-tier budgets)

**Files:**
- Modify: `swingbot/core/macro/health.py`
- Test: `tests/test_macro_health.py`

**Interfaces:**
- Produces: `QUOTAS: dict[str, dict] = {"fred": {"per_minute": 60, "per_day": 5000}, "finnhub": {"per_minute": 50, "per_day": 3000}}` (soft caps under the published free-tier limits); `allow_call(provider, now=None) -> bool` from the ledger; `fetch_json` returns cached/stale/None without network when disallowed. Quota exhaustion is a WARN in health, never an exception.

- [ ] **Step 1: Failing tests** — 51st finnhub call in a minute denied; day rollover resets; denied call still serves cache.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: provider quota meter`

### Task G12: FRED client

**Files:**
- Create: `swingbot/core/macro/fred.py`
- Test: `tests/test_macro_fred.py`

**Interfaces:**
- Produces: `fred_series(series_id: str, *, start: str | None = None, ttl_s=6*3600) -> list[tuple[str, float]] | None` — GET `https://api.stlouisfed.org/fred/series/observations` with `api_key=config.FRED_API_KEY`, `file_type=json`, sorted ascending, `"."` observations skipped; empty key → None without network. `fred_release_dates(release_id: int, *, include_future=True) -> list[str]` (GET `/fred/releases/dates`). `latest(series_id) -> tuple[str, float] | None`; `yoy(series_id) -> float | None` (last vs value 12 monthly observations earlier).
- Consumed by: G13–G20, G30.

- [ ] **Step 1: Failing tests** — fixture JSON payload parses to sorted pairs; `"."` skipped; yoy golden ((last/year_ago − 1)×100); no key → None, zero network calls.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: FRED client (series, release dates, yoy)`

### Task G13: Inflation series — CPI + Core CPI

**Files:**
- Create: `swingbot/core/macro/series.py`
- Test: `tests/test_macro_series.py`

**Interfaces:**
- Produces: `SERIES: dict[str, SeriesSpec]` registry — `SeriesSpec(key, fred_id, kind, label, transform)`; first entries `cpi_yoy` (`CPIAUCSL`, transform yoy), `core_cpi_yoy` (`CPILFESL`, yoy), `cpi_mom` (m/m % of last two obs). `get_value(key) -> MacroValue | None` where `MacroValue(key, value, as_of, label, direction)` (`direction` = sign of change vs prior obs). All later series tasks only add registry rows; `get_value` never changes.

- [ ] **Step 1: Failing tests** — registry row shapes; `get_value("cpi_yoy")` over a fixture series → golden value/as_of/direction; missing data → None.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: macro series registry + CPI`

### Task G14: PPI series

**Files:** Modify `series.py`; test `tests/test_macro_series.py`

- Adds `ppi_yoy` (`PPIFIS` — Final Demand, the headline print), `ppi_mom`, `core_ppi_yoy` (`PPIFES` less foods/energy/trade). Verify both ids resolve in the G40 live smoke; the smoke script prints a loud warning if either 404s.
- [ ] **Step 1–4: Failing tests (golden yoy/mom over fixtures), implement rows, PASS, commit** — `feat: PPI series`

### Task G15: PCE series (the Fed's target measure)

**Files:** Modify `series.py`; test `tests/test_macro_series.py`

- Adds `pce_yoy` (`PCEPI`), `core_pce_yoy` (`PCEPILFE`) + a derived `inflation_vs_target` = core_pce_yoy − 2.0.
- [ ] **Step 1–4: TDD as above, commit** — `feat: PCE series + target gap`

### Task G16: Labor series

**Files:** Modify `series.py`; test `tests/test_macro_series.py`

- Adds `unemployment` (`UNRATE`), `payrolls_change_k` (`PAYEMS` m/m diff, thousands), `jobless_claims` (`ICSA`, weekly latest).
- [ ] **Step 1–4: TDD, commit** — `feat: labor market series`

### Task G17: Policy rate series

**Files:** Modify `series.py`; test `tests/test_macro_series.py`

- Adds `fed_funds` (`FEDFUNDS`), `fed_funds_target_upper` (`DFEDTARU`, daily).
- [ ] **Step 1–4: TDD, commit** — `feat: policy rate series`

### Task G18: Treasury yields

**Files:** Modify `series.py`; test `tests/test_macro_series.py`

- Adds `y3m` (`DGS3MO`), `y2` (`DGS2`), `y10` (`DGS10`), `y30` (`DGS30`) — daily, last non-null.
- [ ] **Step 1–4: TDD, commit** — `feat: treasury yield series`

### Task G19: Curve spreads + inversion flags

**Files:** Modify `series.py`; test `tests/test_macro_series.py`

**Interfaces:** derived registry rows `curve_10y2y` (`T10Y2Y` direct), `curve_10y3m` (`T10Y3M`), plus `curve_state() -> str` (`"inverted"` if either spread < 0, `"flat"` if both in [0, 0.25], else `"normal"`).
- [ ] **Step 1–4: TDD (three-state golden fixtures), commit** — `feat: curve spreads + inversion state`

### Task G20: Inflation expectations & risk-context series

**Files:** Modify `series.py`; test `tests/test_macro_series.py`

- Adds `breakeven_5y` (`T5YIE`), `breakeven_10y` (`T10YIE`), `dollar_index` (`DTWEXBGS`), `wti` (`DCOILWTICO`).
- [ ] **Step 1–4: TDD, commit** — `feat: breakevens, dollar, oil series`

### Task G21: VIX level + term structure

**Files:**
- Create: `swingbot/core/macro/vix.py`
- Test: `tests/test_macro_vix.py`

**Interfaces:**
- Produces: `vix_state() -> dict | None` — `{level, percentile_1y, regime, term_structure}`; level from FRED `VIXCLS` (fallback: cached `^VIX` bars via the existing fetch layer); `regime`: `<16 "calm"`, `16–24 "normal"`, `24–32 "elevated"`, `>32 "stress"`; `term_structure`: `"backwardation"` when VIX > VIX3M (`VXVCLS`) else `"contango"` (None if 3M unavailable). Percentile over trailing 252 obs.

- [ ] **Step 1: Failing tests** — regime boundaries; percentile golden; missing 3M degrades to `term_structure=None` not error.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: VIX regime + term structure`

### Task G22: Credit stress (HYG/LQD)

**Files:**
- Create: `swingbot/core/macro/credit.py`
- Test: `tests/test_macro_credit.py`

**Interfaces:**
- Produces: `credit_state(bars: dict[str, pd.DataFrame] | None = None) -> dict | None` — ratio HYG/LQD closes (from the existing daily-bar cache; injectable for tests), `{ratio, sma20_slope, state}`; `state = "risk_off"` when ratio < its 20DMA and slope < 0, `"risk_on"` when above and rising, else `"neutral"`.

- [ ] **Step 1: Failing tests** — three-state goldens from synthetic ratio paths; missing either ETF → None.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: credit stress gauge`

### Task G23: Sector ETF data plumbing

**Files:**
- Create: `swingbot/core/macro/sectors.py`
- Modify: `scripts/fetch_backtest_data.py` (add sector ETFs + SPY + HYG/LQD + ^VIX to the ticker set)
- Test: `tests/test_macro_sectors.py`

**Interfaces:**
- Produces: `SECTOR_ETFS = {"XLK": "Technology", "XLF": "Financials", "XLV": "Health Care", "XLY": "Cons. Discretionary", "XLP": "Cons. Staples", "XLE": "Energy", "XLI": "Industrials", "XLB": "Materials", "XLU": "Utilities", "XLRE": "Real Estate", "XLC": "Comm. Services"}`, benchmark `SPY`; `sector_bars(loader=None) -> dict[str, pd.DataFrame]` using the existing daily cache loader (injectable).

- [ ] **Step 1: Failing tests** — injectable loader; missing sector skipped with health WARN, not raise.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: sector ETF data plumbing`

### Task G24: Sector relative-strength ranks

**Files:** Modify `sectors.py`; test `tests/test_macro_sectors.py`

**Interfaces:** `sector_rs(bars, windows=(21, 63, 126)) -> list[dict]` — per sector: return over each window minus SPY's, composite = mean of window z-scores, rank 1–11; `leaders(rs_rows, n=3)` / `laggards(rs_rows, n=3)`.
- [ ] **Step 1–4: TDD (synthetic bars where XLE strictly outperforms → rank 1), commit** — `feat: sector RS ranks`

### Task G25: Rotation classification + ticker→sector map

**Files:** Modify `sectors.py`; create seed `data/macro/ticker_sectors.json`; test `tests/test_macro_sectors.py`

**Interfaces:** `rotation_state(rs_rows) -> dict` — `{posture, note}`; `posture = "risk_on"` when ≥2 of {XLK, XLY, XLC} in top 4 composite ranks, `"risk_off"` when ≥2 of {XLP, XLU, XLV} in top 4, else `"mixed"`; note names the leaders. `sector_of(ticker) -> str | None` via the static map (seeded for the current scan universe; unknown → None).
- [ ] **Step 1–4: TDD (three postures from crafted ranks; unknown ticker), commit** — `feat: sector rotation posture`

### Task G26: Breadth internals

**Files:**
- Create: `swingbot/core/macro/breadth.py`
- Test: `tests/test_macro_breadth.py`

**Interfaces:**
- Produces: `breadth(bars: dict[str, pd.DataFrame]) -> dict` — `{pct_above_50dma, pct_above_200dma, n}` over the scan universe's cached bars; `breadth_state(b) -> str` (`"healthy"` ≥60% above 50DMA, `"weak"` ≤40%, else `"mixed"`). (If edge-engine E28 landed, wrap it instead of recomputing — capability check `try: from swingbot.core.edge import factors`.)

- [ ] **Step 1–4: TDD (synthetic universe of 10 tickers, golden pcts), commit** — `feat: breadth internals`

### Task G27: Risk-on/off composite

**Files:**
- Create: `swingbot/core/macro/composite.py`
- Test: `tests/test_macro_composite.py`

**Interfaces:**
- Produces: `risk_composite(vix, credit, rotation, breadth, curve) -> dict` — pure function over the five upstream dicts (any may be None): each contributes −1/0/+1 (vix calm=+1 stress=−1; credit risk_on=+1; rotation risk_on=+1; breadth healthy=+1; curve normal=+1 inverted=−1), score = mean of available × 100 → `{score: -100..100, label: "risk_on"|"neutral"|"risk_off"|"unknown", inputs_used: int, detail: [...]}` (label cuts at ±33; fewer than 2 inputs → `"unknown"`).

- [ ] **Step 1: Failing tests** — all-bull → +100 risk_on; mixed → neutral; one input → unknown; None-tolerance.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: risk-on/off composite`

### Task G28: Fear/greed-style gauge

**Files:** Modify `composite.py`; test `tests/test_macro_composite.py`

**Interfaces:** `fear_greed(vix, breadth, credit, spy_momentum) -> dict | None` — 0–100 gauge from four 0–100 subcomponents (VIX percentile inverted; breadth pct_above_50; credit ratio percentile; SPY 125d momentum percentile), equal-weight mean of available (≥3 required); labels `<25 extreme fear, <45 fear, ≤55 neutral, ≤75 greed, >75 extreme greed`. Own gauge — no scraping of CNN's.
- [ ] **Step 1–4: TDD (label boundaries, <3 inputs → None), commit** — `feat: fear/greed gauge`

### Task G29: Historical econ event dataset (2018→present)

**Files:**
- Create: `scripts/build_event_history.py`, `data/macro/event_history.json` (generated, committed), `swingbot/core/macro/calendar_events.py`
- Test: `tests/test_macro_calendar.py`

**Interfaces:**
- Produces: `Event = {date, time_et, kind, label, importance}` with `kind` in `{"fomc", "cpi", "ppi", "nfp", "pce", "opex", "holiday"}`, importance 1–3 (fomc/cpi/nfp = 3). The script builds history from: FOMC — the Fed's published meeting dates hardcoded 2018–2026 (public, finite, stable — a literal list in the script with a source-URL comment; decision days 14:00 ET); CPI/PPI/PCE/NFP — `fred_release_dates()` (release ids: CPI 10, PPI 46, Employment Situation 50, Personal Income & Outlays 54), 08:30 ET. `calendar_events.load_events() -> list[Event]`; `events_between(start, end)`; `events_on(date)`.
- **This file is what makes the news-whipsaw red flag backtestable** — G90 joins it into the backtest frame.

- [ ] **Step 1: Failing tests** — loader over a fixture file; `events_between` inclusive bounds; kinds/importance validated.
- [ ] **Step 2: Implement loader + script (script hits network — excluded from the test suite; usage documented in its header).**
- [ ] **Step 3: Run the script once for real; spot-check (CPI monthly ~mid-month 08:30 ET; 8 FOMC/year). Commit the generated JSON.**
- [ ] **Step 4: Commit** — `feat: historical econ event calendar 2018→present`

### Task G30: Forward event schedule refresh

**Files:** Modify `calendar_events.py`; test `tests/test_macro_calendar.py`

**Interfaces:** `refresh_future_events(days_ahead=45) -> int` — re-pulls `fred_release_dates(include_future=True)` + the static future FOMC list, merges into `event_history.json` (idempotent by (date, kind)), returns rows added; called by the snapshot scheduler (G39) at most daily. `next_event(kinds=None, now=None) -> Event | None`; `hours_until(event, now) -> float` (ET-aware).
- [ ] **Step 1–4: TDD (merge idempotency, next_event ordering, tz math ET→UTC), commit** — `feat: forward event schedule`

### Task G31: Options-expiry calendar

**Files:**
- Create: `swingbot/core/macro/opex.py`
- Test: `tests/test_macro_opex.py`

**Interfaces:**
- Produces: `opex_dates(year) -> list[str]` (3rd Fridays, shifted to Thursday when Friday is a market holiday); `is_opex(date) -> bool`; `is_quad_witching(date) -> bool` (3rd Friday of Mar/Jun/Sep/Dec); pure calendar math, no network.

- [ ] **Step 1: Failing tests** — golden: 2026 quad-witching = Mar 20, Jun 18 (Jun 19 Juneteenth → Thursday), Sep 18, Dec 18; `is_opex` true/false pairs.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: opex + quad-witching calendar`

### Task G32: Market sessions — holidays, half-days, thin windows

**Files:**
- Create: `swingbot/core/macro/sessions.py`
- Test: `tests/test_macro_sessions.py`

**Interfaces:**
- Produces: NYSE holiday/half-day table 2018–2027 (static literal, source comment); `is_holiday(date)`, `is_half_day(date)`, `is_thin_window(dt_et) -> tuple[bool, str]` — true for first 30 min after open, last 10 min before close, half-day afternoons, and the week between Christmas and New Year (reason string for the embed); `session_flag(date, time_et=None) -> dict` (CheckResult-ready).

- [ ] **Step 1–4: TDD (Jul 3 half-day; 09:45 ET thin; 11:00 not), commit** — `feat: session liquidity calendar`

### Task G33: Earnings calendar provider

**Files:**
- Create: `swingbot/core/macro/earnings.py`
- Test: `tests/test_macro_earnings.py`

**Interfaces:**
- Produces: `days_to_earnings(ticker, now=None) -> int | None` — if llm-advisor's `market_context.py` exists, wrap it (one-implementation rule); else implement here: Finnhub `/calendar/earnings` window ±30d, 6h TTL via `fetch_json(provider="finnhub")`, empty key → None. `earnings_within(ticker, days) -> bool | None` (None when unknown — never a silent False).

- [ ] **Step 1–4: TDD (fixture payload → day math; no key → None, no network), commit** — `feat: earnings calendar provider`

### Task G34: Market news headlines

**Files:**
- Create: `swingbot/core/macro/news.py`
- Test: `tests/test_macro_news.py`

**Interfaces:**
- Produces: `market_headlines(n=15) -> list[dict]` — Finnhub `/news?category=general`, headline dict `{ts, source, title, url, related}`; 30-min TTL; de-dup by lowercase title prefix (first 60 chars); empty key → `[]`.

- [ ] **Step 1–4: TDD (fixture parse, dedup, cap), commit** — `feat: market news provider`

### Task G35: Company news

**Files:** Modify `news.py`; test `tests/test_macro_news.py`

**Interfaces:** `company_headlines(ticker, days=5, n=10) -> list[dict]` — Finnhub `/company-news`, 2h TTL, same dict shape.
- [ ] **Step 1–4: TDD, commit** — `feat: company news provider`

### Task G36: Headline sentiment scorer (lexicon)

**Files:**
- Create: `swingbot/core/macro/sentiment.py`
- Test: `tests/test_macro_sentiment.py`

**Interfaces:**
- Produces: `score_headline(title) -> float` in [-1, 1] — transparent finance lexicon (two literal frozensets, ~60 words each: POSITIVE beats/raises/surges/upgrade/record/approval/…, NEGATIVE misses/cuts/plunges/downgrade/probe/recall/bankruptcy/…), hit-count normalized, negation flip for not/no/fails-to within 3 tokens; `aggregate_sentiment(headlines) -> dict` `{score, n, label}` (label cuts ±0.15). Deliberately simple and auditable; the LLM advisor (G132) adds nuance separately and advisorily.

- [ ] **Step 1: Failing tests** — golden titles each direction; negation flip ("fails to beat" → negative); empty → n=0 label neutral.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: lexicon headline sentiment`

### Task G37: Rumor vs. confirmed classifier

**Files:** Modify `sentiment.py`; test `tests/test_macro_sentiment.py`

**Interfaces:** `classify_confirmation(headline_title) -> str` — `"rumor"` (matches report(edly)|sources say|rumor|in talks|considering|mulls|according to people familiar), `"confirmed"` (announces|files|reports Q|8-K|SEC filing|earnings|guidance|completes), else `"unclear"`; `rumor_ratio(headlines) -> float`. Feeds rf_rumor_spike (G63) and rf_buy_rumor (G64).
- [ ] **Step 1–4: TDD (three-way goldens), commit** — `feat: rumor/confirmed headline classifier`

### Task G38: Macro snapshot builder

**Files:**
- Create: `swingbot/core/macro/snapshot.py`
- Test: `tests/test_macro_snapshot.py`

**Interfaces:**
- Produces: `build_snapshot(*, loaders=None, now=None) -> dict` — assembles every upstream module into ONE dict (each section None-tolerant): `{built_at, stale: bool, inflation: {cpi_yoy, core_cpi_yoy, ppi_yoy, pce_yoy, core_pce_yoy, vs_target}, labor: {...}, rates: {fed_funds, y3m, y2, y10, y30, curve_state}, expectations: {breakeven_5y, breakeven_10y}, risk: {vix, credit, dollar, wti}, composite: {...G27}, fear_greed: {...G28}, sectors: {rs_rows, rotation}, breadth: {...}, events: {next_high_impact, within_24h: [...], today: [...]}, news: {headlines_top5, sentiment, rumor_ratio}, quality_warnings: [...]}`. `save_snapshot(snap)` → `data/macro/macro_snapshot.json` (jsonio) + one summary line appended to `data/macro/snapshot_history.jsonl` (admin trend charts); `load_snapshot(max_age_min=None) -> dict | None`.
- **The single source every consumer reads** — scan gate, embeds, `!macro`, admin pages, advisor payloads. Nobody re-fetches providers at render time.

- [ ] **Step 1: Failing tests** — all-providers-stubbed build → full shape; all-providers-None build → skeleton with unknowns + `stale=True` (the G43 contract starts here); save/load round-trip; max_age gate.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: macro snapshot (single source of context)`

### Task G39: Snapshot scheduler — refresh before every scan

**Files:**
- Modify: `swingbot/core/macro/snapshot.py`, `swingbot/commands/scanning.py` (scan entry point)
- Test: `tests/test_macro_snapshot.py`

**Interfaces:**
- Produces: `ensure_fresh_snapshot(ttl_min=None) -> dict | None` — returns the saved snapshot when younger than TTL (default `config.MACRO_SNAPSHOT_TTL_MIN`), else rebuilds (called via `asyncio.to_thread` from the scan path); **wired at the top of every scan run** when `MACRO_ENABLED`; once per day also calls `refresh_future_events()`. Rebuild failure → previous snapshot with `stale=True` (never blocks the scan). Flag off → None and zero provider calls.

- [ ] **Step 1: Failing tests** — TTL respected (no rebuild when fresh, counting stub); rebuild failure serves stale; disabled → None + zero calls.
- [ ] **Step 2–4: Implement + wire (try/except-log), PASS, commit** — `feat: pre-scan macro snapshot refresh`

### Task G40: Live smoke script

**Files:**
- Create: `scripts/macro_smoke.py`

- [ ] **Step 1: Write it** — with real keys in env: builds a snapshot, prints each section, provider latencies, and which sections came back None; exits non-zero if > 3 sections missing; loudly warns if either PPI id (G14) 404s.
- [ ] **Step 2: Run once for real; save the output summary to `docs/superpowers/results/2026-07-macro-smoke.md`. Commit both** — `feat: macro live smoke script + first snapshot evidence`

### Task G41: Historical macro backfill (publication-lag aware)

**Files:**
- Create: `scripts/backfill_macro.py`, `swingbot/core/macro/history.py`
- Test: `tests/test_macro_history.py`

**Interfaces:**
- Produces: script writes `data/macro/history/{series_key}.json` full FRED history 2017-01→present for every registry series (2017 start gives yoy room for 2018 backtests) plus derived daily VIX-percentile and credit-state series from cached bars. `history.as_of_frame() -> pd.DataFrame` — date-indexed, one column per key, forward-filled **with publication lag**: monthly prints become visible on their release date (from G29's calendar), not their reference month — the no-lookahead rule G90 depends on.

- [ ] **Step 1: Failing tests** — publication-lag golden (May CPI, released Jun 10, appears in the frame from Jun 10, not May 31); ffill correctness; missing series → column of NaN, not error.
- [ ] **Step 2: Implement; run the script once for real; commit generated history files** — `feat: macro history backfill (publication-lag aware)`

### Task G42: Macro data-quality validator

**Files:**
- Create: `swingbot/core/macro/quality.py` (wired into `build_snapshot`)
- Test: `tests/test_macro_quality.py`

**Interfaces:**
- Produces: `validate_snapshot(snap) -> list[str]` — WARN strings for: yields outside [0, 20], VIX outside [5, 100], CPI yoy outside [-5, 25], sector count < 8, missing sections, empty event calendar within 30d ahead. Warnings land in `snap["quality_warnings"]` and surface in admin (G187); never raise.

- [ ] **Step 1–4: TDD (each rule trips on a crafted snapshot), commit** — `feat: macro snapshot sanity validator`

### Task G43: Total-degradation proof

**Files:**
- Test: `tests/test_macro_degradation.py`

- [ ] **Step 1: The test** — monkeypatch `requests` to always raise + empty cache dir: `build_snapshot()` still returns the skeleton (every section None/unknown, `stale=True`), `ensure_fresh_snapshot` returns it, `risk_composite` label `"unknown"` — proving the bot scans normally with the entire internet down. (G121 extends this proof through the gate.)
- [ ] **Step 2: PASS. Step 3: Commit** — `test: macro layer total-degradation proof`

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

- [ ] **Step 1: Failing tests** — G7 `uptrend_daily` → weekly "up"; `downtrend_daily` → "down"; `range_daily` → "range"; short history (< 60 weekly bars) → "range" with detail "insufficient history".
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: HTF trend detector`

### Task G46: Check `htf_alignment` (weight 12, checklist §1 "I know the HTF trend and I'm not against it")

**Files:** Modify `context_htf.py`, `registry.py`; test `tests/test_gate_context_htf.py`

**Interfaces:** `check_htf_alignment(df_daily, plan, macro_snap) -> CheckResult` — bullish plan + weekly "up" → pass; weekly "range" → warn; bullish into weekly "down" (or mirror) → **fail**; evidence carries both timeframe states.
- [ ] **Step 1–4: TDD (all four outcomes + registry row asserted), commit** — `feat: htf_alignment check`

### Task G47: Swing S/R level extraction

**Files:**
- Create: `swingbot/core/gate/levels.py`
- Test: `tests/test_gate_levels.py`

**Interfaces:**
- Produces: `swing_levels(df_daily, lookback=250, pivot_span=5) -> list[Level]` — `Level(price, kind: "support"|"resistance", touches, last_touch)`; pivots = local extrema over ±`pivot_span` bars, clustered within 0.5×ATR, touch-counted; sorted by touches desc. Reuse the existing scanning support/resistance helpers if `swingbot/core/scanning/` already exposes them (verify at execution; wrap, don't fork).

- [ ] **Step 1–4: TDD (crafted series with an obvious 3-touch level → clustered, counted; empty for flat synthetic), commit** — `feat: swing S/R extraction`

### Task G48: Round-number levels

**Files:** Modify `levels.py`; test `tests/test_gate_levels.py`

**Interfaces:** `round_levels(price) -> list[float]` — the psychological grid near price: multiples of 1/5/10/50/100 chosen by price magnitude (e.g. price 187 → 180, 185, 190, 195, 200 and the majors 150/200); `nearest_round(price) -> tuple[float, float]` (level, distance in ATRs given atr kwarg).
- [ ] **Step 1–4: TDD (goldens at $8, $87, $432, $4300), commit** — `feat: round-number levels`

### Task G49: Check `level_map` (weight 8, §1 "nearest major S/R, prior swings, round numbers marked")

**Files:** Modify `levels.py`, `registry.py`; test `tests/test_gate_levels.py`

**Interfaces:** `check_level_map(df_daily, plan, macro_snap) -> CheckResult` — computes the three nearest levels above/below entry (swing + round merged); **fail** when a resistance (for longs; support for shorts) sits closer than 1×ATR to entry *before* TP1 (the trade runs straight into a wall); warn when between 1–2×ATR; pass otherwise. Evidence lists the levels — this is also what the embed renders (G123).
- [ ] **Step 1–4: TDD (wall-before-TP1 fail; clear-path pass), commit** — `feat: level_map check`

### Task G50: Check `atr_normal` (weight 6, §1 "volatility normal — not compressed or spiked")

**Files:**
- Create: `swingbot/core/gate/atr_regime.py`; modify `registry.py`
- Test: `tests/test_gate_atr.py`

**Interfaces:** `check_atr_normal(df_daily, plan, macro_snap) -> CheckResult` — ATR(14)/close percentile over trailing 252 bars; pass in [20th, 80th]; warn <20th (compression — breakout fuel but whipsaw risk) or 80–95th; **fail** >95th (spiked — stop math unreliable). Evidence: percentile + raw ATR%.
- [ ] **Step 1–4: TDD (three bands via crafted vol paths), commit** — `feat: atr_normal check`

### Task G51: Check `vol_expansion_direction` (weight 4, info-grade)

**Files:** Modify `atr_regime.py`, `registry.py`; test `tests/test_gate_atr.py`

**Interfaces:** `check_vol_expansion(df_daily, plan, macro_snap) -> CheckResult` — when ATR is rising (5d slope > 0), is expansion happening on with-plan bars or against-plan bars (sum of true range on up-close vs down-close days, last 10)? Against-plan expansion → warn. Never fails — weight-4 nuance.
- [ ] **Step 1–4: TDD, commit** — `feat: vol expansion direction check`

## Section 2 — Setup quality

### Task G52: Check `signal_confirmed` (weight 10, **hard block**, §2 "pattern fully closed/confirmed")

**Files:**
- Create: `swingbot/core/gate/setup_quality.py`; modify `registry.py`
- Test: `tests/test_gate_setup.py`

**Interfaces:** `check_signal_confirmed(df_daily, plan, macro_snap) -> CheckResult` — asserts the signal bar the plan was built from is a **closed** bar (plan.as_of < today's session date, or session closed) and, for breakout-family strategies, that the trigger candle closed beyond the level (not intrabar poke). Evaluating mid-session on the forming bar → **fail** (hard block: never alert on an unclosed pattern). Uses plan metadata (`entry_type`, signal date) from TradePlanV2.
- [ ] **Step 1–4: TDD (closed pass; same-day-forming fail; close-back-inside fail), commit** — `feat: signal_confirmed hard-block check`

### Task G53: Confluence counter (weight 10, §2 "≥ 2 independent signals agree")

**Files:** Modify `setup_quality.py`, `registry.py`; test `tests/test_gate_setup.py`

**Interfaces:** `check_confluence(df_daily, plan, macro_snap) -> CheckResult` — counts independent agreeing factors at the entry zone: (a) at a G47 swing level, (b) at/near a round number, (c) 20/50/200 SMA within 0.5 ATR and pointing with-plan, (d) volume confirmation (G54's raw bool), (e) momentum agreement (G55's raw bool), (f) with-trend HTF (G46). Pass ≥ 3, warn = 2, fail < 2. Evidence lists which factors fired — reused verbatim by the embed and by `!whycheck`.
- [ ] **Step 1–4: TDD (0/2/4-factor fixtures), commit** — `feat: confluence counter`

### Task G54: Check `volume_confirms` (weight 8, §2 + golden rule)

**Files:** Modify `setup_quality.py`, `registry.py`; test `tests/test_gate_setup.py`

**Interfaces:** `check_volume(df_daily, plan, macro_snap) -> CheckResult` — signal-bar volume vs 20d average: pass ≥ 1.3×; warn 0.8–1.3×; **fail** < 0.8× for breakout-family entries (a breakout on dead volume is the #1 trap per the golden rule), warn-only for mean-reversion strategies (registry `applies_to` handles the split).
- [ ] **Step 1–4: TDD (both strategy families), commit** — `feat: volume confirmation check`

### Task G55: Check `momentum_agrees` (weight 6)

**Files:** Modify `setup_quality.py`, `registry.py`; test `tests/test_gate_setup.py`

**Interfaces:** `check_momentum(df_daily, plan, macro_snap) -> CheckResult` — RSI(14) slope over 5 bars and MACD histogram sign must not *both* point against the plan; both against → fail; one against → warn; else pass.
- [ ] **Step 1–4: TDD, commit** — `feat: momentum agreement check`

### Task G56: Check `no_bearish_divergence_at_entry` (weight 6, §2 "not diverging against the move")

**Files:** Modify `setup_quality.py`, `registry.py`; test `tests/test_gate_setup.py`

**Interfaces:** `check_divergence_against(df_daily, plan, macro_snap) -> CheckResult` — for longs: price higher high in last 20 bars while RSI lower high → warn (fail if the plan's own strategy is *not* divergence-based and the divergence is 2-swing confirmed). Mirror for shorts. Distinct from G60 (which polices divergence-*entry* strategies).
- [ ] **Step 1–4: TDD (crafted HH-price/LH-RSI series), commit** — `feat: divergence-against-move check`

## Section 3 — The 11 red flags (checklist §3, one task each)

Red-flag checks live in `swingbot/core/gate/redflags.py`, ids prefixed `rf_`, section `"redflag"`. Policy: a red flag that fires = `fail`; flags marked **HB** are hard blocks. Each returns evidence sufficient for the embed's red-flag table row.

### Task G57: `rf_fake_breakout` (weight 10)

**Files:** Create `swingbot/core/gate/redflags.py`; modify `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_fake_breakout(df_daily, plan, macro_snap) -> CheckResult` — for breakout-family plans: fires when the breakout bar closed back inside the range (close < level for longs) OR broke out on < 0.8× avg volume; also fires when the *prior* 10 bars contain ≥ 2 failed pokes through the same level (serial-liar level). Non-breakout strategies → pass with detail "n/a" (registry `applies_to` limits it, but the function stays total).
- [ ] **Step 1: Failing tests** — G7 `breakout_and_fail` fixture fires; clean high-volume breakout passes; serial-poke fixture fires.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: rf_fake_breakout`

### Task G58: `rf_stop_sweep` (weight 8)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_stop_sweep(df_daily, plan, macro_snap) -> CheckResult` — fires when the signal bar (or prior bar) printed a wick through an obvious level (G47 level or round number) of ≥ 1.5× body length with close back on the far side, **and** the next bar shows no follow-through (for continuation plans this is the trap; for sweep-reclaim strategies the registry marks it n/a). Evidence: wick/body ratio, level touched.
- [ ] **Step 1–4: TDD (`sweep_wick` fixture fires; normal test-and-hold passes), commit** — `feat: rf_stop_sweep`

### Task G59: `rf_dead_cat` (weight 10)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_dead_cat(df_daily, plan, macro_snap) -> CheckResult` — for bullish plans only: fires when price is in a G45 daily downtrend, has bounced ≥ 5% off a ≤ 20-day low, **and** structure shows no confirmed higher low + higher high pair since that low ("no structure shift yet"). Evidence: days since low, bounce %, structure verdict.
- [ ] **Step 1–4: TDD (`dead_cat` fixture fires; genuine reversal with HL+HH passes), commit** — `feat: rf_dead_cat`

### Task G60: `rf_divergence_trap` (weight 8)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_divergence_trap(df_daily, plan, macro_snap) -> CheckResult` — for divergence-entry strategies: fires when the divergence exists but price has NOT yet confirmed (no close above the divergence swing's high for longs / below the low for shorts) — "divergence alone, without price confirmation". Pass once the confirmation close printed.
- [ ] **Step 1–4: TDD (unconfirmed fires; confirmed passes), commit** — `feat: rf_divergence_trap`

### Task G61: `rf_extreme_fade` (weight 8)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_extreme_fade(df_daily, plan, macro_snap) -> CheckResult` — fires when the plan fades a strong trend on overbought/oversold alone: counter-trend plan (vs G45 daily trend) + RSI beyond 75/25 + ADX(14) > 30 (strong trend — "overbought can stay overbought"). Counter-trend with ADX < 20 → warn only.
- [ ] **Step 1–4: TDD (`climax_overbought` short-fade fires when ADX high; range fade passes), commit** — `feat: rf_extreme_fade`

### Task G62: `rf_news_whipsaw` (weight 10, **HB** inside the blackout window)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_news_whipsaw(df_daily, plan, macro_snap) -> CheckResult` — from `macro_snap["events"]`: importance-3 event (CPI/NFP/FOMC) within the blackout window (config `GATE_BLACKOUT_HOURS_BEFORE` default 18, `_AFTER` default 2, added to config here) → **fail/HB**; importance-2 within window → warn; earnings within `GATE_EARNINGS_BLACKOUT_DAYS` (default 3, reuses G33; defers to edge-engine E18 gate if merged) → fail. Snapshot missing → `unknown`.
- [ ] **Step 1–4: TDD (CPI tomorrow fires; quiet week passes; None snapshot → unknown), commit** — `feat: rf_news_whipsaw + blackout config`

### Task G63: `rf_rumor_spike` (weight 6)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_rumor_spike(df_daily, plan, macro_snap, headlines=None) -> CheckResult` — fires when the signal bar gapped ≥ 5% or ranged ≥ 2.5× ATR on ≥ 3× volume **and** the ticker's recent headlines (G35, injected by the orchestrator) are majority `"rumor"`-classified (G37) or absent entirely (unexplained spike). Confirmed-news spike → warn (still event-driven). No headlines provider → `unknown` on the news half, decided by geometry half alone (warn max).
- [ ] **Step 1–4: TDD (`gap_spike` + rumor headlines fires; confirmed earnings headline → warn; no provider → geometry-only warn), commit** — `feat: rf_rumor_spike`

### Task G64: `rf_buy_rumor_sell_fact` (weight 6)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_buy_rumor_sell_fact(df_daily, plan, macro_snap) -> CheckResult` — fires for with-move entries within 2 sessions **after** a scheduled importance-3 event or the ticker's earnings date when the pre-event 5-day run-up exceeded 1.5× ATR-normalized average (the move was priced in; entering now buys the fact). Evidence: event, run-up multiple.
- [ ] **Step 1–4: TDD (post-FOMC chase fires; no-event passes), commit** — `feat: rf_buy_rumor_sell_fact`

### Task G65: `rf_thin_session` (weight 6)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_thin_session(df_daily, plan, macro_snap, now=None) -> CheckResult` — from G32: fires (warn-grade fail→warn mapping: this one is `warn`, never `fail` — EOD swing entries mostly dodge it) when *now* is a half-day, holiday-adjacent thin week, or intraday thin window and the plan's entry could trigger in it; plus fires when the ticker's own 20d median dollar-volume < config floor `GATE_MIN_DOLLAR_VOL` (float field, default 2_000_000).
- [ ] **Step 1–4: TDD (holiday week warn; liquid normal day pass; illiquid ticker warn), commit** — `feat: rf_thin_session`

### Task G66: `rf_opex_pin` (weight 4)

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_opex_pin(df_daily, plan, macro_snap, now=None) -> CheckResult` — warn when today or tomorrow `is_opex` (G31), escalating detail on quad-witching; pass otherwise. Warn-grade only.
- [ ] **Step 1–4: TDD (quad-witching Friday warns), commit** — `feat: rf_opex_pin`

### Task G67: `rf_beta_move` (weight 6, "is this really my instrument's move?")

**Files:** Modify `redflags.py`, `registry.py`; test `tests/test_gate_redflags.py`

**Interfaces:** `rf_beta_move(df_daily, plan, macro_snap, spy_df=None) -> CheckResult` — regress ticker daily returns on SPY (60d) → beta + residual; fires when the signal move's residual (move minus beta×SPY move over the signal window) is < 35% of the raw move — the "signal" is just index beta, and it evaporates when the index mean-reverts. Evidence: beta, raw vs idiosyncratic move %. SPY bars missing → unknown.
- [ ] **Step 1–4: TDD (pure-beta synthetic fires; idiosyncratic gap passes), commit** — `feat: rf_beta_move idiosyncrasy check`

## Section 4 — Risk definition (decided BEFORE entry)

### Task G68: Check `stop_structural` (weight 10, §4 "stop beyond structure, widened ~1 ATR")

**Files:**
- Create: `swingbot/core/gate/risk_def.py`; modify `registry.py`
- Test: `tests/test_gate_risk.py`

**Interfaces:** `check_stop_structural(df_daily, plan, macro_snap) -> CheckResult` — the plan's stop must sit beyond the nearest protective structure level (G47 support for longs) by ≥ 0.5 ATR and not *exactly at* an obvious level/round number (within 0.15 ATR of one → warn "sweep bait"). Stop inside the structure → **fail**. Advisory-only against the v2 exit model: this check flags, it never mutates the plan's stop (Global Constraints — exit geometry is v2-validated).
- [ ] **Step 1–4: TDD (beyond+wide pass; at-level warn; inside fail), commit** — `feat: stop_structural check`

### Task G69: Check `size_formula` (weight 8, §4 "size from account risk ÷ stop distance")

**Files:** Modify `risk_def.py`, `registry.py`; test `tests/test_gate_risk.py`

**Interfaces:** `check_size_formula(df_daily, plan, macro_snap, account=None) -> CheckResult` — recomputes size from `account.compute_position_size` semantics (risk % ÷ stop distance) and compares to the plan's stated size: pass within 5%, warn within 20%, fail beyond (conviction-sized). When edge-engine sizing modes (E4–E6) are live, pass-through their output as the reference. Evidence: expected vs actual shares.
- [ ] **Step 1–4: TDD (exact pass; 2× conviction fail), commit** — `feat: size_formula check`

### Task G70: Check `rr_realistic` (weight 10, §4 "R:R ≥ 1.5–2 to a realistic target")

**Files:** Modify `risk_def.py`, `registry.py`; test `tests/test_gate_risk.py`

**Interfaces:** `check_rr_realistic(df_daily, plan, macro_snap) -> CheckResult` — R:R computed to the *structure-capped* target: min(plan TP1, nearest opposing G47/G48 level). Capped R:R ≥ `GATE_MIN_RR` (float field, default 1.5) → pass; 1.2–1.5 → warn; < 1.2 → **fail**. Evidence shows both the plan's nominal R:R and the structure-capped one (the honest number).
- [ ] **Step 1–4: TDD (wall-capped fail even when nominal 2:1; clear-sky pass), commit** — `feat: rr_realistic (structure-capped) check`

### Task G71: Check `portfolio_room` (weight 6)

**Files:** Modify `risk_def.py`, `registry.py`; test `tests/test_gate_risk.py`

**Interfaces:** `check_portfolio_room(df_daily, plan, macro_snap, open_plans=None) -> CheckResult` — warn when ≥ `GATE_MAX_CORR_POSITIONS` (int field, default 2) open plans share the ticker's sector (G25 `sector_of`); fail when the same ticker already has an open plan. Delegates to edge-engine heat/correlation caps (E7/E8) when merged — then this check only *reports* their verdict.
- [ ] **Step 1–4: TDD (dup-ticker fail; 3-same-sector warn; empty book pass), commit** — `feat: portfolio_room check`

## Section 5 — Timing & trigger

### Task G72: Check `trigger_objective` (weight 6, **HB**, §5 "entry trigger is objective, not a feel")

**Files:**
- Create: `swingbot/core/gate/timing.py`; modify `registry.py`
- Test: `tests/test_gate_timing.py`

**Interfaces:** `check_trigger_objective(df_daily, plan, macro_snap) -> CheckResult` — asserts the plan carries a machine-readable trigger: `entry_type` in the TradePlanV2 vocabulary (limit/stop/close-confirm...) with a concrete price. Missing/None entry price or unknown entry_type → **fail/HB** (a plan the bot can't state objectively is a feel). This is a plan-integrity invariant — it should never fire in production, and firing = engine bug surfaced loudly.
- [ ] **Step 1–4: TDD (well-formed pass; priceless plan fail), commit** — `feat: trigger_objective invariant check`

### Task G73: Check `not_chasing` (weight 8, §5 "price hasn't already run far past")

**Files:** Modify `timing.py`, `registry.py`; test `tests/test_gate_timing.py`

**Interfaces:** `check_not_chasing(df_daily, plan, macro_snap) -> CheckResult` — distance from signal level to current price: pass ≤ 0.5 ATR, warn 0.5–1.0, **fail** > `GATE_CHASE_ATR_MAX` (float field, default 1.0) ATR past the trigger (late entry wrecks the R:R that was validated).
- [ ] **Step 1–4: TDD (fresh pass; 1.5-ATR-late fail), commit** — `feat: not_chasing check`

### Task G74: Check `calendar_checked` (weight 4, §5 "I've checked the economic calendar")

**Files:** Modify `timing.py`, `registry.py`; test `tests/test_gate_timing.py`

**Interfaces:** `check_calendar(df_daily, plan, macro_snap) -> CheckResult` — pass when the macro snapshot is fresh (< TTL) and its events section is populated (the bot literally checked the calendar this session); warn when stale; unknown when `MACRO_ENABLED` off. Complements rf_news_whipsaw: this checks that we *looked*; G62 checks what we *saw*.
- [ ] **Step 1–4: TDD, commit** — `feat: calendar_checked freshness check`

## Assembly

### Task G75: `run_checklist()` orchestrator

**Files:**
- Modify: `swingbot/core/gate/__init__.py`
- Test: `tests/test_gate_run.py`

**Interfaces:**
- Produces: `run_checklist(ticker, strategy, plan, df_daily, *, macro_snap=None, open_plans=None, account=None, headlines=None, spy_df=None, now=None) -> GateResult` — resolves `enabled_checks(strategy)`, calls each check inside try/except (an exception in any check → that check `unknown` + log, **never** a scan crash), assembles score (G6), tier (cuts from config, G79), hard_blocks, `macro_stale`. Deterministic given inputs. `__init__.py` re-exports `run_checklist`, `GateResult`, `CheckResult`.

- [ ] **Step 1: Failing tests** — full run over a G7 clean-uptrend fixture + stubbed macro snap → all sections present in result, score in range, no hard blocks; a check monkeypatched to raise → its id `unknown`, others unaffected; strategy filtering respected.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: run_checklist orchestrator`

### Task G76: Hard-block policy wiring + `GATE_MODE` semantics

**Files:** Modify `swingbot/core/gate/registry.py`, `score.py`; test `tests/test_gate_run.py`

**Interfaces:** `decide(result: GateResult, mode: str, min_tier: str) -> str` — returns `"pass"` | `"downgrade"` | `"block"`: **shadow and inform modes always return `"pass"`** (the would-be enforce decision is recorded on the result as `advisory_decision` — inform mode renders it as information, e.g. "⛔ enforce would block this: 2 red flags"); only enforce mode may return `"downgrade"`/`"block"` (below `GATE_MIN_TIER` or on a hard block; downgrade = WEAK-style de-emphasis, cockpit rule 6, one tier above the block line).
- [ ] **Step 1–4: TDD (shadow AND inform never block — property test over random results; enforce matrix over tiers × hard blocks; advisory_decision always populated), commit** — `feat: gate decision policy (shadow/inform/enforce)`

### Task G77: Soft-flag sizing suggestion

**Files:** Modify `score.py`; test `tests/test_gate_score.py`

**Interfaces:** `suggested_size_mult(tier: str) -> float` — the checklist's own "size down significantly" rule as a *suggestion carried on the result*, never auto-applied in this phase: `{"A+": 1.0, "A": 1.0, "B": 0.5, "C": 0.0}` from config fields `GATE_SIZE_MULT_B` (default 0.5) etc. G116 fold-tests making it real.
- [ ] **Step 1–4: TDD, commit** — `feat: tier size-multiplier suggestion`

### Task G78: Weight & neutrality calibration over fixtures

**Files:**
- Test: `tests/test_gate_calibration_fixtures.py`

- [ ] **Step 1: The test battery** — run `run_checklist` across all G7 scenarios × both directions with a neutral macro snap and assert the *ordering* invariants (not absolute scores): clean with-trend confluence setup > range-bounce setup > counter-trend setup > `breakout_and_fail`/`dead_cat`; every red-flag scenario lands tier ≤ B; the clean setup lands ≥ A. If orderings fail, adjust registry weights (weights are the free variable; detectors are not) and record final weights in a table comment.
- [ ] **Step 2: PASS. Step 3: Commit** — `test: checklist ordering calibration over golden scenarios`

### Task G79: Tier-cut, threshold & strictness-preset config fields

**Files:** Modify `swingbot/config.py`, `swingbot/core/gate/registry.py`; test `tests/test_gate_config.py`

**Interfaces:**
- Fields `GATE_TIER_APLUS_CUT` (float, 90.0), `GATE_TIER_A_CUT` (75.0), `GATE_TIER_B_CUT` (55.0) + per-check `GATE_CHECK_*` checkboxes for every registered check id (generated from the registry — one loop, asserted complete by test), all in the Gatekeeper section.
- **Per-check threshold Fields**, generated from every `ThresholdSpec` in the registry (G5): key pattern `GATE_TH_{CHECK_ID}_{NAME}` (float/int, with the spec's min/max/step and the relax-direction sentence as help text). This is the "loosen it from the settings page" surface: every strict number in Phase G2 — volume multiples, ATR bands and percentile cuts, confluence minimum, chase distance, RR floor, wick ratios, bounce/gap percentages, blackout hours, RSI/ADX bounds — lives here, none are hardcoded. `spec.threshold(name)` resolves Field value → preset default.
- `apply_strictness_preset(level: str) -> dict[str, float]` — returns (and `config` setter applies) every threshold's `presets[level]` value; **relaxed** is deliberately generous (roughly: warn where balanced fails, pass where balanced warns) so a relaxed profile always lets plans through; **strict** is the A+-hunting profile. Changing `GATE_STRICTNESS` reseeds only thresholds the operator hasn't individually overridden (override tracking = value ≠ any preset value, noted in help text).
- [ ] **Step 1: Failing tests** — every registry check id has its enable Field; every ThresholdSpec has its Field with correct bounds; cuts ordered; preset application golden (relaxed ≥ balanced ≥ strict in the relax direction for every threshold — property test over the registry); individually-overridden threshold survives a preset switch.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: tier cuts + registry-driven thresholds + strictness presets`

### Task G80: Per-strategy applicability matrix finalized

**Files:** Modify `registry.py`; test `tests/test_gate_registry.py`

- [ ] **Step 1: Enumerate the actual strategy names** from the codebase's strategy registry (read the real list at execution time — do not trust this plan) and fill every CheckSpec's `applies_to` deliberately: breakout family gets rf_fake_breakout as fail-grade; mean-reversion gets rf_extreme_fade relaxed (its own edge *is* fading — the flag polices only strong-ADX fades); divergence strategies get rf_divergence_trap. Table documented in a module docstring.
- [ ] **Step 2: Failing test asserting the matrix rows for each real strategy name; implement; PASS. Step 3: Commit** — `feat: per-strategy check applicability`

### Task G81: Gate result persistence on plans

**Files:**
- Create: `swingbot/core/gate/persistence.py`
- Test: `tests/test_gate_persistence.py`

**Interfaces:** `attach_to_plan(plan_id, result: GateResult)` — stores `result.to_dict()` on the plan record via `plan_store` (new optional `gate` key — additive, old plans unaffected); `blocked_log(result, decision, reason)` → append `data/gate/blocked.jsonl`; `shadow_log(result)` → `data/gate/shadow.jsonl` (one line per evaluated candidate in shadow mode: score, tier, would-be decision, plan outcome joined later by G104).
- [ ] **Step 1–4: TDD (attach round-trip; logs append JSONL-valid lines), commit** — `feat: gate persistence (plan attach + blocked/shadow logs)`

### Task G82: Checklist embed renderer

**Files:**
- Create: `swingbot/core/gate/render.py`
- Test: `tests/test_gate_render.py`

**Interfaces:** `checklist_field(result) -> tuple[str, str]` — (name `"📋 Checklist — {tier} ({score:.0f})"`, value: five section lines `✅/⚠️/⛔/◻️` counts e.g. `"Context ✅3 · Setup ✅2 ⚠️1 · Red flags ⛔1 · Risk ✅3 · Timing ✅2"`); `redflag_table(result) -> str` — only fired/warned flags, one line each `"⛔ Fake breakout — closed back inside on 0.6× volume"` (≤ 1024 chars, truncation-safe); `full_breakdown(result) -> list[str]` — every check with its detail, chunked for Discord message limits. Pure string builders, no discord.py imports (testable).
- [ ] **Step 1–4: TDD (goldens over a fixture result; length caps), commit** — `feat: checklist render strings`

### Task G83: Gut-check ritual — Discord buttons + modal

**Files:**
- Create: `swingbot/core/gate/gutcheck.py` (state), modify `swingbot/commands/scanning.py` (view wiring)
- Test: `tests/test_gate_gutcheck.py`

**Interfaces:** `GutCheckView(plan_id)` — buttons `✅ Follow` / `⛔ Skip` / `📝 Why I'd be wrong`; the third opens a modal with two inputs: "One sentence: why I'd be wrong if the stop is hit" (required, checklist §6) and "Would I take this if my last trade was a loss?" (yes/no). `record_gutcheck(plan_id, answers) -> None` persists to the plan record + journal (`gutcheck` key). Buttons are optional ritual — a plan follows normally without them; config `GATE_GUTCHECK_REQUIRED` (checkbox, default false) makes Follow require the modal first. State machinery pure-python; the discord View is a thin shell (interaction handlers tested via the fake-interaction pattern already used by the command tests — verify the existing pattern at execution).
- [ ] **Step 1–4: TDD (record round-trip; required-mode ordering), commit** — `feat: gut-check ritual (buttons + why-wrong journal)`

### Task G84: Journal integration on close — was the checklist right?

**Files:** Modify `swingbot/core/gate/persistence.py` (+ the analytics journal close-hook)
- Test: `tests/test_gate_persistence.py`

**Interfaces:** `on_trade_close(trade, journal_entry) -> dict` — pulls the plan's stored GateResult; appends to the journal entry: `{gate_tier, gate_score, fired_flags: [...], gutcheck_present: bool}` tags (e.g. `tier-a-plus`, `rf-fake-breakout-ignored` when a flagged trade was taken anyway). Wired into the existing JournalStore close hook (cockpit A-phase) behind a capability check.
- [ ] **Step 1–4: TDD (tags land on a fixture close), commit** — `feat: gate outcome tags in the journal`

### Task G85: Red-flag outcome tagger — the receipts

**Files:** Modify `persistence.py`; test `tests/test_gate_persistence.py`

**Interfaces:** `flag_outcome_stats(journal_entries) -> list[dict]` — per red-flag id: `{flag, n_fired_and_taken, wr_when_ignored, wr_when_clean, delta_wr, avg_r_when_ignored}` — the live evidence for "this flag earns its keep" consumed by `!redflags` (G115) and the admin analytics page (G183). Pure over journal entries.
- [ ] **Step 1–4: TDD (golden stats over synthetic entries), commit** — `feat: red-flag outcome stats`

### Task G86: Analytics snapshot integration

**Files:** Modify `swingbot/core/analytics/snapshots.py` (additive section)
- Test: `tests/test_gate_persistence.py`

**Interfaces:** snapshot gains a `"gate"` section: tier distribution of open+recent plans, WR by tier (via `analytics.metrics`, one-definition rule), flag outcome stats (G85), shadow-mode divergence summary (G104's numbers once live). Absent gate data → section `{}`, snapshot otherwise unchanged (byte-compare test for the no-gate case).
- [ ] **Step 1–4: TDD, commit** — `feat: gate section in analytics snapshot`

### Task G87: Performance guard

**Files:**
- Test: `tests/test_gate_perf.py`

- [ ] **Step 1: The test** — `run_checklist` over a 500-bar frame with warm inputs completes < 50 ms median of 20 runs (pure-compute budget; macro I/O is excluded by design since the snapshot is prebuilt); a full 60-ticker scan's gate overhead projected < 3 s. Mark `@pytest.mark.perf` consistent with existing perf tests (cockpit A-phase precedent — verify marker name at execution).
- [ ] **Step 2: PASS (optimize level extraction caching if not). Step 3: Commit** — `test: gate evaluation perf budget`

### Task G88: Phase G2 checkpoint

- [ ] **Step 1:** Full suite + `make check` green. Registry invariant test passes with **all** checks registered (context 4, setup 5, red flags 11, risk 4, timing 3 = 27 checks).
- [ ] **Step 2:** Update Progress block. Commit — `chore: phase G2 checkpoint (27 checks live)`

---

# Phase G3 — Backtest validation & the win-rate frontier (G89–G118)

Where the 95% question gets answered with folds instead of hope. Everything here runs on TRAIN data (2018–2023) behind `assert_train_only`.

### Task G89: Backtestable-check subset registry

**Files:** Modify `swingbot/core/gate/registry.py`; test `tests/test_gate_registry.py`

**Interfaces:** every CheckSpec's `backtestable: bool` finalized: price/volume/calendar checks (htf, levels, atr, setup, rf_fake_breakout, rf_stop_sweep, rf_dead_cat, rf_divergence_trap, rf_extreme_fade, rf_news_whipsaw via G29 history, rf_buy_rumor_sell_fact, rf_thin_session, rf_opex_pin, rf_beta_move, risk checks, not_chasing) = True; live-only checks (rf_rumor_spike's news half, calendar_checked, portfolio_room, trigger_objective) = False. `backtest_checks(strategy) -> list[CheckSpec]`. The backtest tier is computed from backtestable checks only — G103's shadow comparison quantifies how much the live-only checks add.
- [ ] **Step 1–4: TDD (subset membership assertions), commit** — `feat: backtestable check subset`

### Task G90: Historical context joins — no lookahead

**Files:**
- Create: `swingbot/core/gate/backtest_ctx.py`
- Test: `tests/test_gate_backtest_ctx.py`

**Interfaces:** `historical_macro_snap(as_of: date) -> dict` — a macro-snapshot-shaped dict reconstructed from G41's publication-lag-aware frame + G29 events + G31/G32 calendars, containing exactly what was knowable at `as_of`'s close: VIX percentile, curve state, events within blackout, opex/session flags. Missing history → unknowns (same degradation contract). **The no-lookahead test is the deliverable:** for a date the day before a CPI print, the snap must contain the *previous* CPI value and the *pending* event.
- [ ] **Step 1–4: TDD (lookahead trap fixtures), commit** — `feat: historical macro snapshots for backtests`

### Task G91: Backtest hook — checklist per simulated signal

**Files:** Modify `swingbot/core/backtest.py`; test `tests/test_gate_backtest.py`

**Interfaces:** new backtest kwarg `gate_eval: bool = False` — when on, each simulated signal calls `run_checklist` with `macro_snap=historical_macro_snap(signal_date)`, `spy_df` from cache, and records `{gate_score, gate_tier, fired_flags}` onto the simulated trade record. **Zero behavior change:** trades are still taken; the gate only annotates. Baseline-regression test: `gate_eval=False` output byte-identical to pre-change for a fixture run.
- [ ] **Step 1–4: TDD (annotations present when on; byte-identity when off), commit** — `feat: gate annotation in backtests (no behavior change)`

### Task G92: Gate-filtered replay mode

**Files:** Modify `swingbot/core/backtest.py`; test `tests/test_gate_backtest.py`

**Interfaces:** kwarg `gate_min_tier: str | None = None` — when set, signals below the tier (or hard-blocked) are recorded as `skipped_by_gate` (kept in output for the frontier math, excluded from equity/WR); `assert_train_only` guards the entry point when either gate kwarg is used.
- [ ] **Step 1–4: TDD (filtered run drops exactly the sub-tier trades; skipped list preserved; validation-window call raises), commit** — `feat: gate-filtered backtest replay`

### Task G93: WR-by-score-decile report

**Files:**
- Create: `swingbot/core/gate/frontier.py`
- Test: `tests/test_gate_frontier.py`

**Interfaces:** `wr_by_decile(trades) -> list[dict]` — over gate-annotated trades: per score-decile `{decile, n, wr, expectancy_r, wilson_lb}` (G1's Wilson bound — the *proven* WR column). Pure function.
- [ ] **Step 1–4: TDD (monotone synthetic: higher deciles → higher WR; golden numbers), commit** — `feat: WR-by-decile report`

### Task G94: The frontier report

**Files:** Modify `frontier.py`; test `tests/test_gate_frontier.py`

**Interfaces:** `frontier(trades, cuts=range(0, 101, 5)) -> list[dict]` — for each score cut: `{cut, n_kept, pct_kept, wr, wilson_lb, expectancy_r, trades_per_month}` — **the honest tradeoff curve** (WR you gain vs signals you lose vs expectancy). `best_cut(frontier_rows, min_n, max_signal_loss_pct)` — highest-WR cut satisfying the G2 constraints, None when nothing qualifies (an allowed, reportable outcome).
- [ ] **Step 1–4: TDD (golden frontier over synthetic; best_cut constraint behavior incl. None), commit** — `feat: WR frontier + constrained best-cut`

### Task G95: Tier cuts from the frontier — pre-registered procedure

**Files:** Modify `frontier.py`; test `tests/test_gate_frontier.py`

**Interfaces:** `propose_tier_cuts(frontier_rows) -> dict | None` — mechanically: A+ = lowest cut whose wilson_lb ≥ 0.80 and n ≥ 59 (the G1 math: the sample size where ~95% observed WR *proves* > 90%); A = lowest cut with wr ≥ baseline + 5 pts; B = baseline. Output is a **proposal dict** written to `data/tuning_proposals/{ts}-gate-tiers.json` (cockpit C36 shape) — never applied to config by code.
- [ ] **Step 1–4: TDD (proposal from goldens; insufficient data → None), commit** — `feat: mechanical tier-cut proposal`

### Task G96: Fold runner (reuse E39 or minimal fallback)

**Files:**
- Create: `scripts/gate_fold_run.py`, `swingbot/core/gate/folds.py`
- Test: `tests/test_gate_folds.py`

**Interfaces:** `run_folds(strategy, *, gate_min_tier=None) -> dict` — if `swingbot/core/backtest_wf.py` (edge E39) exists, delegate; else the minimal fallback implemented here: anchored folds (train 2018→fold-start, test 2021/2022/2023), runs G92 replay per fold, returns `{folds: [{year, n, wr, expectancy_r}], pooled: {...}, passes_gate: bool}` applying the Global-Constraints fold gate verbatim. CLI: `python scripts/gate_fold_run.py --strategy X --min-tier A [--all]` printing a table + writing `docs/superpowers/results/2026-07-gate-folds-{strategy}.json`.
- [ ] **Step 1–4: TDD (fold windows correct; gate math on synthetic fold results; delegation branch mocked), commit** — `feat: gate fold runner`

### Task G97: Baseline annotation run — all strategies

**Files:** Create `docs/superpowers/results/2026-07-gate-baseline.md` (generated evidence)

- [ ] **Step 1:** Run `scripts/gate_fold_run.py --all` with `gate_min_tier=None` (annotate-only) on TRAIN. This is the census: per strategy, the score distribution, WR by decile, flag fire-rates.
- [ ] **Step 2:** Write the results doc: the decile tables + three sentences per strategy on where its losers cluster. **No tuning decisions in this task** — census only. Commit — `docs: gate baseline census on TRAIN folds`

### Task G98: Frontier run — all strategies

**Files:** Create `scripts/gate_frontier.py`; evidence `docs/superpowers/results/2026-07-gate-frontier.md`

- [ ] **Step 1:** CLI wrapping G94 over the G97 annotated trades: per strategy the frontier table + the constrained best cut + the tier-cut proposal (G95) when supported.
- [ ] **Step 2:** Run for real on TRAIN; commit the evidence doc with the honest headline numbers per strategy (`WR @ cut`, `wilson_lb`, `% signals kept`, `expectancy`). Commit — `feat: frontier CLI + TRAIN evidence`

### Task G99: Red-flag ablation — each flag earns its keep

**Files:** Modify `scripts/gate_fold_run.py` (`--ablate` mode); evidence doc `docs/superpowers/results/2026-07-gate-ablation.md`
- Test: `tests/test_gate_folds.py`

**Interfaces:** `--ablate` runs folds once per red flag with only that flag active as a filter: reports each flag's standalone `{signals_removed_pct, wr_delta, expectancy_delta}` pooled + per fold. Flags that *hurt* expectancy in ≥ 2 folds get their registry weight set to 0 (info-only) in a follow-up commit, documented.
- [ ] **Step 1–4: TDD (ablation loop mechanics on stub folds); run for real; commit evidence + any demotions** — `feat: per-flag ablation + evidence`

### Task G100: Permutation reality check on the score

**Files:** Modify `folds.py` (`permutation_test(trades, n=1000)`); test `tests/test_gate_folds.py`; evidence in the G98 doc

**Interfaces:** shuffles gate scores across the annotated trades 1000× → p-value that the observed WR-by-decile monotonicity is luck (reuses edge E41 machinery when present). p ≥ 0.05 → the score is noise → **stop the phase and say so** in the results doc (pre-registered stopping rule).
- [ ] **Step 1–4: TDD (rigged monotone → tiny p; shuffled → large p); run for real; append evidence; commit** — `feat: gate score permutation test`

### Task G101: Threshold plateau check

**Files:** Modify `frontier.py` (`plateau_report(frontier_rows, chosen_cut)`); test `tests/test_gate_frontier.py`

**Interfaces:** asserts the chosen cut sits on a plateau (WR within 2 pts and expectancy within 0.03R for cut ± 10) not a spike; spiky choice → report recommends the plateau center instead (edge E42 pattern).
- [ ] **Step 1–4: TDD (plateau vs spike fixtures); commit** — `feat: plateau check for tier cuts`

### Task G102: TRAIN decision memo — the honest 95% answer

**Files:** Create `docs/superpowers/results/2026-07-gate-decision.md`

- [ ] **Step 1: Write the memo from G97–G101 evidence, per strategy:** chosen min-tier + cuts (or "no cut qualifies"), fold table, the explicit sentence per strategy: *"A+ tier fold WR = X% (Wilson LB Y%, N=Z) — this {does/does not} support a 95-class label"*, aggregate WR before/after at the chosen cuts, signals kept. Where the ladder tops out below target, the memo says exactly that and what evidence would change it (more N, new checks — not looser math).
- [ ] **Step 2: Apply the surviving cuts to config Field *defaults* (`GATE_MODE` stays `inform` — cuts only label tiers on alerts; nothing starts blocking). Also sanity-check the balanced preset against the census: if balanced thresholds put < 30% of TRAIN signals at tier ≥ B, loosen the balanced presets (G79) and note it in the memo — defaults must never starve the alert flow. Commit** — `docs: gate TRAIN decision memo + inform-mode defaults`

### Task G103: Shadow mode live wiring

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_gate_shadow.py`

**Interfaces:** with `GATE_ENABLED=true`: every scan candidate gets `run_checklist` (full live inputs — news, portfolio, macro snap), result attached to the plan + `shadow_log` line (G81) in **all modes** (the shadow log is the evidence stream regardless of mode). In `shadow` mode alerts are completely unchanged (byte-compare test on the embed); in `inform`/`enforce` the rendering tasks (G122–G124) take over. The checklist field does NOT render in shadow (G123 defines the render matrix).
- [ ] **Step 1–4: TDD (shadow logs written; embeds byte-identical), commit** — `feat: live shadow-mode gate`

### Task G104: Shadow comparison report

**Files:** Create `scripts/gate_shadow_report.py`; modify `persistence.py` (`join_shadow_outcomes()`)
- Test: `tests/test_gate_shadow.py`

**Interfaces:** `join_shadow_outcomes() -> list[dict]` — joins `shadow.jsonl` rows to closed-trade outcomes by plan_id; report prints: would-have-blocked cohort vs passed cohort `{n, wr, expectancy}`, per-flag live fire→outcome table, live-vs-backtest score-distribution drift. CLI `--since YYYY-MM-DD`.
- [ ] **Step 1–4: TDD (join over synthetic logs+trades; cohort math goldens), commit** — `feat: shadow comparison report`

### Task G105: Shadow promotion gate — pre-registered

**Files:** Modify `docs/superpowers/specs/2026-07-14-gatekeeper-v6-targets.md` (checkboxes section)

- [ ] **Step 1: Append the operational checklist to the targets doc** (relevant **only if** the operator ever chooses to leave inform mode — enforce is optional forever): enforce may be enabled only when: ≥ 14 calendar days in inform/shadow with logging, ≥ 15 would-have-blocked decisions, blocked-cohort WR < passed-cohort WR (directionally right), no live crash/timeout attributable to the gate, G104 report attached. Sign-off = a dated line in the doc.
- [ ] **Step 2: Commit** — `docs: shadow→enforce promotion gate (pre-registered)`

### Task G106: Enforce-mode switch (OPTIONAL — opt-in, never the default)

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_gate_enforce.py`

**Interfaces:** `GATE_MODE=enforce` (operator-chosen, guarded by the G105 evidence gate via G170): `decide()` (G76) verdicts apply — `block` → candidate dropped from alerts, `blocked_log` line + counted in telemetry (G135); `downgrade` → alert ships WEAK-style de-emphasized (amber, caution line — reuse the cockpit WEAK rendering path) with the checklist field showing why. Blocking **never** deletes the plan record — blocked plans are stored with status `blocked` for the audit trail. **Inform-mode regression test in this task:** the same failing candidate under `inform` still alerts, annotated, unblocked.
- [ ] **Step 1–4: TDD (block drops alert but stores plan; downgrade renders de-emphasized; inform + shadow regressions untouched), commit** — `feat: optional enforce mode`

### Task G107: Validation-shot interface (deferred to edge E92)

**Files:** Modify `docs/superpowers/results/2026-07-gate-decision.md`

- [ ] **Step 1: Document the handshake:** the gate's chosen cuts become part of the pooled final system that edge-engine E92 fires at 2024–2025 exactly once. This plan performs **no** validation-window run of its own; if edge-engine is unmerged when v6 finishes, the single shot waits. One paragraph, committed — the point is that it's written down before anyone is tempted.
- [ ] **Step 2: Commit** — `docs: validation-shot ownership note`

### Task G108: Monthly gate re-audit cron

**Files:** Modify `swingbot/commands/scanning.py` (monitor loop, month boundary); test `tests/test_gate_audit.py`

**Interfaces:** `monthly_gate_audit(journal_entries, now) -> str | None` — first scan of each month: live WR by tier vs the TRAIN fold WR (drift alert when live tier-WR < fold WR − 10 pts with N ≥ 20, mirroring cockpit's pre-registered edge-decay rule), flag outcome stats, posted to the retrospective channel + saved `data/gate/audits/{YYYY-MM}.json`.
- [ ] **Step 1–4: TDD (drift trips; small-N stays silent; idempotent per month), commit** — `feat: monthly gate audit`

### Task G109: Low-N cell guard

**Files:** Modify `frontier.py`, `render.py`; test `tests/test_gate_frontier.py`

**Interfaces:** every WR the gate surfaces anywhere routes through `fmt_wr(wr, n) -> str` — renders `"—"` with `"N<20"` note below the threshold, appends `"(N=…)"` always. Grep-level test asserts `render.py`/report builders use it (no raw `f"{wr:.0f}%"` slips through).
- [ ] **Step 1–4: TDD, commit** — `feat: low-N guard on every displayed WR`

### Task G110: Overfit sentinel

**Files:** Modify `folds.py`; test `tests/test_gate_folds.py`

**Interfaces:** `overfit_sentinel(fold_result) -> list[str]` — WARNs when train-fold WR exceeds test-fold WR by > 12 pts, when a strategy's chosen cut keeps < 15% of signals (over-filtered to anecdotes), or when pooled N < 90. Warnings print in fold CLI output and land in the results docs automatically.
- [ ] **Step 1–4: TDD, commit** — `feat: overfit sentinel`

### Task G111: Frontier chart (matplotlib)

**Files:** Create `swingbot/core/charts/gate_charts.py`; test `tests/test_gate_charts.py`

**Interfaces:** `frontier_chart(frontier_rows, path) -> str` — dual-axis: WR + Wilson LB curves vs cut (left), % signals kept (right), chosen cut vline, N annotated per point; follows the existing charts' style constants. Smoke-test renders to tmp and asserts file non-empty + no exception (visual QA in G195).
- [ ] **Step 1–4: TDD (render smoke), commit** — `feat: frontier chart`

### Task G112: Decile + flag-ablation charts

**Files:** Modify `gate_charts.py`; test `tests/test_gate_charts.py`

**Interfaces:** `decile_chart(decile_rows, path)` (WR bars + N labels + expectancy line), `ablation_chart(ablation_rows, path)` (per-flag ΔWR vs Δsignals scatter, quadrant lines).
- [ ] **Step 1–4: TDD (render smokes), commit** — `feat: decile + ablation charts`

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
