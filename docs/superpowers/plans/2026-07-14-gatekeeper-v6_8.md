# Gatekeeper v6 - Part 8/11: Scan pipeline & alert integration (Tasks G119-G146)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute strictly in order (G119 -> G146).
>
> **Split note:** this is part 8 of 11, extracted verbatim from the master plan `2026-07-14-gatekeeper-v6.md` (which stays as the reference copy; the checklist-to-task traceability appendix is in Part 11). Parts execute in numeric order.
> **Requires complete first:** Parts 1-7 complete (all their tasks checked off).
>
> Cross-part references (task numbers like G38, file names, `Interfaces:` blocks) refer to work done in earlier parts - those modules exist on the branch by the time this part runs.

## Progress

> Updated by the executing session after each task batch. Resume from the first unchecked task.
>
> - **Branch:** `feature/gatekeeper-v6`
> - **Completed:** —
> - **Next:** Task G119

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

# Phase G4 — Scan pipeline & alert integration (G119–G146)

The gate meets the live bot. Every task here is flag-gated and ships with a "flags off → byte-identical behavior" regression test.

### Task G119: Scan entry — snapshot + gate context assembly

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_scan_gate_wiring.py`

**Interfaces:** one `GateContext` assembled per scan run (not per ticker): `{macro_snap (G39), open_plans, spy_df, now}`; per-candidate additions (company headlines) fetched lazily inside `run_checklist` callers with the quota meter respected. `GateContext` built even when only `MACRO_ENABLED` (for embeds) — gate checks additionally need `GATE_ENABLED`.
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scan_gate_wiring.py
"""Scan-path gate wiring — no live bot, no network. scan_engine, providers
and the plan store are stubbed; these tests pin the wiring invariants."""
import datetime as dt

import swingbot.commands.scanning as scanning
import swingbot.config as config


def _flags(monkeypatch, *, macro, gate):
    monkeypatch.setattr(config, "MACRO_ENABLED", macro, raising=False)
    monkeypatch.setattr(config, "GATE_ENABLED", gate, raising=False)


def test_context_none_when_everything_off(monkeypatch):
    _flags(monkeypatch, macro=False, gate=False)
    assert scanning.build_gate_context() is None


def test_context_built_once_per_scan(monkeypatch):
    calls = {"snap": 0}

    def fake_load():
        calls["snap"] += 1
        return {"built_at": "2026-07-14T12:00:00", "stale": False}

    _flags(monkeypatch, macro=True, gate=False)
    monkeypatch.setattr(scanning, "_load_macro_snapshot", fake_load)
    ctx = scanning.build_gate_context(now=dt.datetime(2026, 7, 14, 12, 0))
    # per-candidate work only READS the assembled context — a 60-candidate
    # scan performs exactly one snapshot load, regardless of ticker count
    for _ in range(60):
        assert ctx.macro_snap["stale"] is False
    assert calls["snap"] == 1


def test_context_macro_only_skips_gate_inputs(monkeypatch):
    _flags(monkeypatch, macro=True, gate=False)
    monkeypatch.setattr(scanning, "_load_macro_snapshot",
                        lambda: {"built_at": "t", "stale": False})
    ctx = scanning.build_gate_context()
    assert ctx.macro_snap is not None                  # embeds get their line
    assert ctx.open_plans == [] and ctx.spy_df is None # gate inputs not fetched


def test_context_degrades_when_snapshot_unreadable(monkeypatch):
    def boom():
        raise OSError("disk")

    _flags(monkeypatch, macro=True, gate=True)
    monkeypatch.setattr(scanning, "_load_macro_snapshot", boom)
    ctx = scanning.build_gate_context()
    assert ctx is not None and ctx.macro_snap is None  # degrade, never crash
```

- [ ] **Step 2: Run — FAIL**, then **implement** (add to `swingbot/commands/scanning.py`, near the scan-tick helpers):

```python
@dataclasses.dataclass
class GateContext:
    macro_snap: dict | None
    open_plans: list
    spy_df: object | None          # cached SPY daily bars (rf_beta_move)
    now: dt.datetime


def _load_macro_snapshot():
    """Seam for tests — reads the saved snapshot only; G39's
    ensure_fresh_snapshot already refreshed it at scan entry."""
    from swingbot.core.macro.snapshot import load_snapshot
    return load_snapshot()


def build_gate_context(now=None) -> GateContext | None:
    """One per scan RUN, never per ticker (G119). Cheap by construction:
    saved snapshot + open plans + cached SPY bars. Built when MACRO_ENABLED
    alone (the embed macro line needs it); gate inputs are fetched only
    when GATE_ENABLED. Company headlines are NOT here — they are fetched
    lazily per candidate inside the run_checklist caller (quota-metered).
    Every input degrades to None/[] — assembly never raises."""
    if not (getattr(config, "MACRO_ENABLED", False)
            or getattr(config, "GATE_ENABLED", False)):
        return None
    now = now or dt.datetime.now()
    macro_snap = None
    if getattr(config, "MACRO_ENABLED", False):
        try:
            macro_snap = _load_macro_snapshot()
        except Exception:  # noqa: BLE001
            log.warning("macro snapshot unreadable — context degrades", exc_info=True)
    open_plans, spy_df = [], None
    if getattr(config, "GATE_ENABLED", False):
        try:
            from swingbot.core.plan_store import load_open_plans  # verify accessor name at execution
            open_plans = load_open_plans()
        except Exception:  # noqa: BLE001
            open_plans = []
        try:
            from swingbot.core.data import load_cached_daily      # verify name at execution
            spy_df = load_cached_daily("SPY")
        except Exception:  # noqa: BLE001
            spy_df = None
    return GateContext(macro_snap=macro_snap, open_plans=open_plans,
                       spy_df=spy_df, now=now)
```

**Wiring** (`_session_scan_tick`, directly after the G39 `ensure_fresh_snapshot` call, before `run_scan`): `gate_ctx = build_gate_context()`, passed through to the alert path (`run_scan(..., gate_ctx=gate_ctx)` — add the pass-through kwarg to `scan_engine.run_scan`, default `None`, unused until G121/G122 consume it; `!check` builds its own context the same way).

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_scan_gate_wiring.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py swingbot/core/scan_engine.py tests/test_scan_gate_wiring.py
git commit -m "feat: per-scan gate context"
```

### Task G120: Event blackout scan gate

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_scan_gate_wiring.py`

**Interfaces:** when `GATE_BLACKOUT_ENABLED` and an importance-3 event falls within the blackout window at scan time: **default behavior is annotation** — the plan is created and alerted normally with a prominent warning line ("⚠️ CPI 08:30 ET tomorrow — historically whipsaw-prone; consider waiting for the print"). Only when `GATE_BLACKOUT_ENFORCE` (new checkbox Field, default false) is *also* on are new entries marked `held_for_event` (plan created, alert says "⏸ held — releases after the print") and auto-released by the monitor loop once `hours_until(event) < -GATE_BLACKOUT_HOURS_AFTER`. Stale event calendar (> 7 days unrefreshed) auto-disables holding with a WARN — annotation continues. One pure decision function owns the whole rule: `blackout_decision(macro_snap, now) -> dict | None`.
- [ ] **Step 1: Write the failing tests** (append to `tests/test_scan_gate_wiring.py`)

```python
NOW = dt.datetime(2026, 7, 14, 18, 0)


def _snap(hours_until_event=14.0, importance=3, refreshed_days_ago=0):
    refreshed = (NOW - dt.timedelta(days=refreshed_days_ago)).isoformat()
    return {"built_at": NOW.isoformat(), "stale": False,
            "events": {"refreshed_at": refreshed, "upcoming": [
                {"name": "CPI", "importance": importance,
                 "at": (NOW + dt.timedelta(hours=hours_until_event)).isoformat()}]}}


def _blackout_flags(monkeypatch, *, enabled, enforce, before=24.0, after=2.0):
    monkeypatch.setattr(config, "GATE_BLACKOUT_ENABLED", enabled, raising=False)
    monkeypatch.setattr(config, "GATE_BLACKOUT_ENFORCE", enforce, raising=False)
    monkeypatch.setattr(config, "GATE_BLACKOUT_HOURS_BEFORE", before, raising=False)
    monkeypatch.setattr(config, "GATE_BLACKOUT_HOURS_AFTER", after, raising=False)


def test_blackout_default_is_annotate(monkeypatch):
    _blackout_flags(monkeypatch, enabled=True, enforce=False)
    verdict = scanning.blackout_decision(_snap(), NOW)
    assert verdict["action"] == "annotate"             # plan ships, loudly
    assert "CPI" in verdict["line"] and "⚠️" in verdict["line"]


def test_blackout_hold_requires_both_flags(monkeypatch):
    _blackout_flags(monkeypatch, enabled=True, enforce=True)
    verdict = scanning.blackout_decision(_snap(), NOW)
    assert verdict["action"] == "hold"
    assert verdict["release_at"] > NOW.isoformat()     # after + GATE_BLACKOUT_HOURS_AFTER


def test_blackout_ignores_low_importance_and_far_events(monkeypatch):
    _blackout_flags(monkeypatch, enabled=True, enforce=True)
    assert scanning.blackout_decision(_snap(importance=2), NOW) is None
    assert scanning.blackout_decision(_snap(hours_until_event=72.0), NOW) is None


def test_blackout_stale_calendar_never_holds(monkeypatch, caplog):
    _blackout_flags(monkeypatch, enabled=True, enforce=True)
    verdict = scanning.blackout_decision(_snap(refreshed_days_ago=8), NOW)
    assert verdict["action"] == "annotate"             # holding auto-disabled
    assert any("stale" in r.message.lower() for r in caplog.records)


def test_blackout_flag_off_is_none(monkeypatch):
    _blackout_flags(monkeypatch, enabled=False, enforce=True)
    assert scanning.blackout_decision(_snap(), NOW) is None
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `scanning.py`):

```python
def blackout_decision(macro_snap: dict | None, now: dt.datetime) -> dict | None:
    """The G120 rule in one pure function. None → no blackout applies.
    {"action": "annotate", "line": ...} → alert ships with the warning line
    (the DEFAULT — inform-first). {"action": "hold", "line", "release_at"}
    only when GATE_BLACKOUT_ENFORCE is also on and the event calendar is
    fresh (≤ 7 days). Event shape comes from the snapshot's events section
    (G38) — verify key names against snapshot.py at execution."""
    if not getattr(config, "GATE_BLACKOUT_ENABLED", False) or not macro_snap:
        return None
    events = (macro_snap.get("events") or {})
    before = float(getattr(config, "GATE_BLACKOUT_HOURS_BEFORE", 24.0))
    after = float(getattr(config, "GATE_BLACKOUT_HOURS_AFTER", 2.0))
    hit = None
    for ev in events.get("upcoming", []):
        if int(ev.get("importance", 0)) < 3:
            continue
        try:
            at = dt.datetime.fromisoformat(ev["at"])
        except (KeyError, ValueError):
            continue
        hours_until = (at - now).total_seconds() / 3600.0
        if -after <= hours_until <= before:
            hit = (ev, at)
            break
    if hit is None:
        return None
    ev, at = hit
    line = (f"⚠️ {ev['name']} {at.strftime('%H:%M')} ET "
            f"{'today' if at.date() == now.date() else 'tomorrow'} — "
            f"historically whipsaw-prone; consider waiting for the print")
    if getattr(config, "GATE_BLACKOUT_ENFORCE", False):
        refreshed = events.get("refreshed_at")
        fresh = False
        try:
            fresh = (now - dt.datetime.fromisoformat(refreshed)).days <= 7
        except (TypeError, ValueError):
            pass
        if fresh:
            release_at = at + dt.timedelta(hours=after)
            return {"action": "hold", "line": line,
                    "event": ev["name"], "release_at": release_at.isoformat()}
        log.warning("event calendar stale (> 7 days) — blackout holding "
                    "auto-disabled, annotating instead")
    return {"action": "annotate", "line": line, "event": ev["name"]}
```

**Wiring** (alert path, once per scan run using `gate_ctx.macro_snap`): `annotate` → the line is prepended to each alert embed's description (or a dedicated `⚠️ Event` field — match the embed style at execution) and the plan is created normally; `hold` → plan stored with `status="held_for_event"` + `release_at`, alert ships saying `"⏸ held — releases after the print"`, and `trade_monitor` releases it (normal pending flow + a release note on the alert) once `now >= release_at`. The monitor-release path is exercised in the G143 e2e.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_scan_gate_wiring.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py swingbot/config.py tests/test_scan_gate_wiring.py
git commit -m "feat: event blackout annotate-first, hold opt-in"
```

### Task G121: Per-candidate gate evaluation in the scan path

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_scan_gate_wiring.py`

**Interfaces:** the alert path calls `run_checklist` per surviving candidate (background thread, same place llm-advisor L14 hooks), applies `with_advisory()` per mode (G76/G103/G106 semantics unified here — shadow/inform always pass), attaches results (G81). Two hard invariants tested here: (1) **inform mode never drops an alert** — property test over arbitrary GateResults including all-fail/hard-block ones; (2) extends the G43 proof through the gate: all providers down → all candidates evaluate with unknowns → **no block ever fires on unknowns** even in enforce mode. The unifying function is pure and owns every invariant: `gate_candidate(result, mode, min_tier) -> (decision, result)`.
- [ ] **Step 1: Write the failing tests** (append to `tests/test_scan_gate_wiring.py`)

```python
from swingbot.core.gate.types import CheckResult, GateResult


def _gate_result(statuses, tier="C", hard_blocks=()):
    checks = tuple(CheckResult(f"c{i}", "setup", s, 10.0, s, {})
                   for i, s in enumerate(statuses))
    return GateResult(ticker="T", strategy="S", as_of="2026-07-14",
                      checks=checks, score=10.0, tier=tier,
                      hard_blocks=tuple(hard_blocks))


def test_inform_never_drops_property():
    """Invariant 1: inform mode passes EVERY result — including all-fail
    and hard-blocked ones. The checklist is information, not a gateway."""
    worst_cases = [
        _gate_result(["fail"] * 7, tier="C", hard_blocks=("signal_confirmed",)),
        _gate_result(["fail", "unknown", "fail"], tier="C"),
        _gate_result(["pass"] * 7, tier="A+"),
    ]
    for result in worst_cases:
        decision, out = scanning.gate_candidate(result, "inform", "A")
        assert decision == "pass"                      # alert always ships
        assert out.advisory_decision in ("pass", "downgrade", "block")


def test_unknown_never_blocks_even_in_enforce():
    """Invariant 2 (the G43 proof through the gate): a result whose low
    tier comes from unknowns — not observed failures — never blocks."""
    dark = _gate_result(["unknown"] * 7, tier="C")
    decision, out = scanning.gate_candidate(dark, "enforce", "A")
    assert decision == "pass"
    assert out.advisory_decision == "block"            # the would-be verdict stays honest


def test_enforce_blocks_only_on_observed_evidence():
    flagged = _gate_result(["fail"] * 5 + ["pass"] * 2, tier="C")
    decision, _ = scanning.gate_candidate(flagged, "enforce", "A")
    assert decision == "block"                         # real fails may block
    mixed = _gate_result(["unknown"] * 6 + ["fail"], tier="C")
    decision, _ = scanning.gate_candidate(mixed, "enforce", "A")
    assert decision == "pass"                          # unknown-dominated → pass


def test_shadow_passes_and_records_would_block():
    result = _gate_result(["fail"] * 7, tier="C")
    decision, out = scanning.gate_candidate(result, "shadow", "A")
    assert decision == "pass" and out.advisory_decision == "block"
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `scanning.py`):

```python
def _unknown_dominated(result, max_unknown_weight_pct: float = 50.0) -> bool:
    """True when more than half the checklist's weight answered "unknown"
    — a tier earned by missing data, not observed failures. Such a result
    NEVER blocks (extends the G43 darkness proof through the gate)."""
    total = sum(c.weight for c in result.checks) or 1.0
    unknown = sum(c.weight for c in result.checks if c.status == "unknown")
    return 100.0 * unknown / total > max_unknown_weight_pct


def gate_candidate(result, mode: str, min_tier: str):
    """The single scan-path decision point, G76/G103/G106 unified:
    shadow/inform ALWAYS pass (invariant 1); enforce may block, but never
    on an unknown-dominated result (invariant 2). Returns
    (decision, result-with-advisory)."""
    from swingbot.core.gate.score import with_advisory
    decision, out = with_advisory(result, mode, min_tier)
    if decision == "block" and _unknown_dominated(out):
        log.warning("gate: %s %s would block on unknown-dominated evidence "
                    "— passing instead (unknown never blocks)",
                    out.ticker, out.strategy)
        decision = "pass"
    return decision, out
```

**Wiring** (alert path in `scanning.py`, per surviving candidate, same seam llm-advisor L14 hooks — all inside `asyncio.to_thread` alongside the existing per-alert work):

```python
    # per candidate: gate_ctx from G119; headlines fetched lazily + quota-metered
    if gate_ctx is not None and getattr(config, "GATE_ENABLED", False):
        try:
            result = run_checklist(item.result.ticker, item.result.strategy,
                                   item.plan_v2, item_df,
                                   macro_snap=gate_ctx.macro_snap,
                                   open_plans=gate_ctx.open_plans,
                                   spy_df=gate_ctx.spy_df, now=gate_ctx.now)
            decision, result = gate_candidate(
                result, config.GATE_MODE, config.GATE_MIN_TIER)
            attach_to_plan(plan_store, item.plan_v2.plan_id, result)   # G81
            if config.GATE_MODE == "shadow":
                shadow_log(result)                                     # G81/G103
            if decision == "block":
                blocked_log(result, decision, ", ".join(result.hard_blocks) or
                            f"tier {result.tier} < {config.GATE_MIN_TIER}")
                continue        # enforce mode only — reachable ONLY after G105/G106 opt-in
            item.gate_result = result                                  # G123 renders it
        except Exception:  # noqa: BLE001 — a gate bug must never cost an alert
            log.warning("gate evaluation failed — alert ships ungated", exc_info=True)
```

Add a test for that last guarantee: monkeypatch `run_checklist` to raise → the candidate still reaches the send path with no `gate_result` (exception in gate → alert ships ungated + one log line).

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_scan_gate_wiring.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py tests/test_scan_gate_wiring.py
git commit -m "feat: gate evaluation in scan path (inform never drops, unknown never blocks)"
```

### Task G122: Alert embed — macro context field

**Files:** Modify `swingbot/core/scanning/embeds.py` (`build_embed`); test `tests/test_embeds_gate.py`

**Interfaces:** `build_embed(..., macro: dict | None = None)` — one field `🌍 Market` valued e.g. `"Risk-ON (+67) · VIX 14.2 calm · Curve normal · Tech leads · CPI in 3d"` built by `render.macro_line(snap)` (added to `gate/render.py`, ≤ 120 chars, unknown-tolerant). `macro=None` → byte-identical embed (regression). Follow the repo's embed-test convention (test_embeds_badges.py): the pure builder carries the logic, the `build_embed` wiring is a guarded two-liner.
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_embeds_gate.py
from swingbot.core.gate.render import macro_line

SNAP = {
    "built_at": "2026-07-14T12:00:00", "stale": False,
    "composite": {"score": 67, "label": "risk_on", "inputs_used": 6, "detail": []},
    "vix": {"level": 14.2, "regime": "calm"},
    "curve": {"state": "normal"},
    "sectors": {"leader": "Tech"},
    "events": {"upcoming": [{"name": "CPI", "importance": 3,
                             "at": "2026-07-17T08:30:00"}]},
}


def test_macro_line_golden():
    line = macro_line(SNAP)
    assert line == "Risk-ON (+67) · VIX 14.2 calm · Curve normal · Tech leads · CPI in 3d"
    assert len(line) <= 120


def test_macro_line_stale_marker():
    assert macro_line(dict(SNAP, stale=True)).endswith("(stale)")


def test_macro_line_unknown_tolerant():
    # darkness: every section missing → still a line, never a KeyError
    line = macro_line({"built_at": "t", "stale": False})
    assert "unknown" in line.lower() and len(line) <= 120


def test_macro_line_none_snapshot():
    assert macro_line(None) is None                    # → no field added
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `swingbot/core/gate/render.py`; keys mirror the G38 snapshot — verify against `snapshot.py` at execution):

```python
def macro_line(snap: dict | None) -> str | None:
    """One ≤120-char market-context line for the alert embed. Every part
    is optional — a missing/unknown section renders as its unknown form,
    an absent snapshot renders as None (no field). Never raises."""
    if not snap:
        return None
    parts = []
    comp = snap.get("composite") or {}
    if comp.get("label") and comp["label"] != "unknown":
        arrow = {"risk_on": "Risk-ON", "risk_off": "Risk-OFF",
                 "neutral": "Risk-neutral"}.get(comp["label"], comp["label"])
        parts.append(f"{arrow} ({comp['score']:+d})")
    else:
        parts.append("Risk unknown")
    vix = snap.get("vix") or {}
    if vix.get("level") is not None:
        parts.append(f"VIX {vix['level']:.1f} {vix.get('regime', '')}".strip())
    curve = snap.get("curve") or {}
    if curve.get("state"):
        parts.append(f"Curve {curve['state']}")
    leader = (snap.get("sectors") or {}).get("leader")
    if leader:
        parts.append(f"{leader} leads")
    nxt = next((e for e in (snap.get("events") or {}).get("upcoming", [])
                if int(e.get("importance", 0)) >= 3), None)
    if nxt:
        try:
            import datetime as dt
            days = (dt.datetime.fromisoformat(nxt["at"]).date()
                    - dt.datetime.fromisoformat(snap["built_at"]).date()).days
            parts.append(f"{nxt['name']} today" if days <= 0
                         else f"{nxt['name']} in {days}d")
        except (KeyError, ValueError):
            pass
    line = " · ".join(parts)
    if snap.get("stale"):
        line += " (stale)"
    return line[:120]
```

**Wiring** (`swingbot/core/scanning/embeds.py` — `build_embed` gains the kwarg, appended after the existing fields so every prior field keeps its position):

```python
def build_embed(item, explanation, perf_stats, open_positions_warning,
                chart_filename, htf_info: dict = None,
                macro: dict | None = None) -> discord.Embed:
    ...
    # at the end, before returning:
    if macro is not None:
        from swingbot.core.gate.render import macro_line
        line = macro_line(macro)
        if line:
            embed.add_field(name="🌍 Market", value=line, inline=False)
```

The `macro=None` byte-identity is structural (the block is skipped entirely) — pin it with one regression test that calls `macro_line(None)` (above) plus, in the caller, pass `macro=gate_ctx.macro_snap if gate_ctx else None` so `MACRO_ENABLED=false` flows through as None end-to-end (asserted again in the G140 e2e).

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_embeds_gate.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/render.py swingbot/core/scanning/embeds.py swingbot/commands/scanning.py tests/test_embeds_gate.py
git commit -m "feat: market context line on alerts"
```

### Task G123: Alert embed — checklist field

**Files:** Modify `embeds.py`; test `tests/test_embeds_gate.py`

**Interfaces:** `build_embed(..., gate: dict | None = None)` — renders G82's `checklist_field` + (when any flag fired) `redflag_table` as a second field, plus the `advisory_decision` line when enforce-would-have-blocked ("⛔ 2 red flags — plan ships anyway; your call"). Render matrix: `inform` and `enforce` modes render always (**inform is the default — this field is the product**); `shadow` renders only with `GATE_SHOW_IN_SHADOW` (new checkbox field, default false). None → byte-identical. One pure function owns the matrix: `gate_embed_fields(result, mode, show_in_shadow) -> list[tuple[str, str]]` in `gate/render.py`.
- [ ] **Step 1: Write the failing tests** (append to `tests/test_embeds_gate.py`; reuse the `_result()` fixture shape from `tests/test_gate_render.py` — import it or lift it into `tests/fixtures/gate/`)

```python
from swingbot.core.gate.render import gate_embed_fields
from tests.test_gate_render import _result                # the B-tier, 2-flag fixture


def test_inform_renders_checklist_and_flags():
    fields = gate_embed_fields(_result(), "inform", show_in_shadow=False)
    names = [n for n, _ in fields]
    assert names[0] == "📋 Checklist — B (61)"
    assert any(n.startswith("🚩") for n in names)      # flags fired → table field
    # the fixture's advisory_decision is "downgrade", not "block" → no ⛔ line
    assert not any("ships anyway" in v for _, v in fields)


def test_advisory_block_line_golden():
    import dataclasses
    result = dataclasses.replace(_result(), advisory_decision="block")
    fields = gate_embed_fields(result, "inform", show_in_shadow=False)
    flat = "\n".join(v for _, v in fields)
    assert "⛔ 2 red flags — plan ships anyway; your call" in flat


def test_shadow_render_matrix():
    assert gate_embed_fields(_result(), "shadow", show_in_shadow=False) == []
    assert gate_embed_fields(_result(), "shadow", show_in_shadow=True) != []
    assert gate_embed_fields(_result(), "enforce", show_in_shadow=False) != []


def test_none_result_renders_nothing():
    assert gate_embed_fields(None, "inform", show_in_shadow=False) == []
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `gate/render.py`):

```python
def gate_embed_fields(result, mode: str,
                      show_in_shadow: bool = False) -> list[tuple[str, str]]:
    """The G123 render matrix in one place: inform/enforce always render
    (inform is the default — this field IS the product); shadow renders
    only when the operator opted in; no result → no fields (byte-identical
    embed). Returns (name, value) pairs ready for embed.add_field."""
    if result is None:
        return []
    if mode == "shadow" and not show_in_shadow:
        return []
    fields = [checklist_field(result)]
    fired = [c for c in result.checks
             if c.check_id.startswith("rf_") and c.status in ("fail", "warn")]
    if fired:
        value = redflag_table(result)
        if result.advisory_decision == "block":
            n = len(fired)
            value += (f"\n⛔ {n} red flag{'s' if n != 1 else ''} — "
                      f"plan ships anyway; your call")
        fields.append(("🚩 Red flags", value))
    return fields
```

**Wiring** — `build_embed` gains `gate=None` alongside G122's `macro`, appended after the 🌍 field:

```python
    if gate is not None:
        from swingbot.core.gate.render import gate_embed_fields
        for name, value in gate_embed_fields(
                gate, getattr(config, "GATE_MODE", "inform"),
                getattr(config, "GATE_SHOW_IN_SHADOW", False)):
            embed.add_field(name=name, value=value, inline=False)
```

Caller passes `gate=getattr(item, "gate_result", None)` (set by G121). Config field `GATE_SHOW_IN_SHADOW` (checkbox, default false, help: "Render the checklist on alerts while still in shadow mode — for previewing the field before promoting to inform.") added to the Gatekeeper section.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_embeds_gate.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/render.py swingbot/core/scanning/embeds.py swingbot/commands/scanning.py swingbot/config.py tests/test_embeds_gate.py
git commit -m "feat: checklist field on alerts (inform-first)"
```

### Task G124: Full breakdown surface

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_embeds_gate.py`

**Interfaces:** the existing breakdown surface (cockpit B10 when present, else follow-up message — mirror llm-advisor L15's degradation pattern) gains the `full_breakdown(result)` chunks: every check, its status emoji, its one-line evidence. This is the checklist *as a readable document* per trade. `full_breakdown` itself exists since G82 — this task is the send path plus the chunk-budget proof over a realistic (25-check) result.
- [ ] **Step 1: Write the failing test** (append to `tests/test_embeds_gate.py`)

```python
from swingbot.core.gate.render import full_breakdown
from swingbot.core.gate.types import CheckResult, GateResult


def test_full_breakdown_chunks_fit_discord_limit():
    # realistic worst case: every registered check present with a long
    # evidence line — chunks must each stay under the 2000-char message
    # cap and preserve every check id across the chunk boundary
    checks = tuple(
        CheckResult(f"check_{i:02d}", "setup", "warn", 5.0,
                    "evidence " + "x" * 140, {})
        for i in range(25))
    result = GateResult(ticker="NVDA", strategy="Break & Retest",
                        as_of="2026-07-14", checks=checks, score=50.0,
                        tier="B", hard_blocks=())
    chunks = full_breakdown(result)
    assert len(chunks) >= 2                            # forced to split
    assert all(len(c) < 2000 for c in chunks)
    joined = "\n".join(chunks)
    assert all(f"check_{i:02d}" in joined for i in range(25))
```

- [ ] **Step 2: Run — PASS or FAIL** — if G82's implementation already chunks correctly this passes immediately (fine: the test still pins the budget); otherwise fix the chunker in `render.py` (split on line boundaries, never mid-line, `limit=1900` for headroom).
- [ ] **Step 3: Wire the send path** (`scanning.py`, right after the alert message is sent, only for candidates that carry a `gate_result`):

```python
    # mirror llm-advisor L15's degradation: cockpit B10 breakdown surface
    # when present, else plain follow-up messages under the alert
    if getattr(item, "gate_result", None) is not None \
            and getattr(config, "GATE_FULL_BREAKDOWN", False):
        for chunk in full_breakdown(item.gate_result):
            await channel.send(chunk)
```

`GATE_FULL_BREAKDOWN` (checkbox, default false — the compact 📋 field is the default surface; the full document is opt-in channel volume) added to the Gatekeeper config section. `!whycheck <plan_id>` (G154) is the on-demand route to the same chunks, so nothing is lost with the flag off.

- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/render.py swingbot/commands/scanning.py swingbot/config.py tests/test_embeds_gate.py
git commit -m "feat: full checklist breakdown per alert"
```

### Task G125: Gut-check view on alerts

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_gate_gutcheck.py`

**Interfaces:** alerts for tier ≥ A attach `GutCheckView` (G83); `GATE_GUTCHECK_REQUIRED` mode: the Follow button defers plan-follow until the modal lands (§6 ritual enforced — the ordering logic already lives in G83's Follow button). View timeout 24h; expiry treated as "not answered" (never blocks the plan lifecycle). New pure helper: `wants_gutcheck(result) -> bool`.
- [ ] **Step 1: Write the failing tests** (append to `tests/test_gate_gutcheck.py`; fake-interaction pattern from G83's tests)

```python
from swingbot.commands.scanning import wants_gutcheck


class _R:
    def __init__(self, tier):
        self.tier = tier


def test_wants_gutcheck_tier_gate(monkeypatch):
    monkeypatch.setattr(config, "GATE_ENABLED", True, raising=False)
    assert wants_gutcheck(_R("A+")) is True
    assert wants_gutcheck(_R("A")) is True
    assert wants_gutcheck(_R("B")) is False            # ritual is for the good ones
    assert wants_gutcheck(None) is False


def test_wants_gutcheck_off_when_gate_off(monkeypatch):
    monkeypatch.setattr(config, "GATE_ENABLED", False, raising=False)
    assert wants_gutcheck(_R("A+")) is False


async def test_required_mode_follow_opens_modal_first(monkeypatch, store_with_plan):
    """G83's Follow button already defers to the modal when required —
    re-asserted here at the alert level: no gutcheck recorded until the
    modal submits."""
    monkeypatch.setattr(config, "GATE_GUTCHECK_REQUIRED", True, raising=False)
    view = GutCheckView("p_test_0001", store_with_plan)
    interaction = FakeInteraction()                    # G83 test helper
    await view.follow.callback(view, interaction)
    assert interaction.modal_sent is not None          # modal first...
    assert get_gutcheck(store_with_plan, "p_test_0001") is None   # ...nothing recorded yet


async def test_timeout_records_nothing(store_with_plan):
    view = GutCheckView("p_test_0001", store_with_plan)
    await view.on_timeout()
    assert get_gutcheck(store_with_plan, "p_test_0001") is None   # expiry = unanswered
```

- [ ] **Step 2: Run — FAIL**, then **implement** — `wants_gutcheck` in `scanning.py`:

```python
def wants_gutcheck(result) -> bool:
    """Gut-check buttons ride only tier ≥ A alerts — the §6 ritual is for
    setups you might actually take; expiry/timeout is 'not answered' and
    never touches the plan lifecycle."""
    return (getattr(config, "GATE_ENABLED", False)
            and result is not None
            and getattr(result, "tier", None) in ("A+", "A"))
```

**Wiring** (`_send_alerts` / the alert-send call): when `wants_gutcheck(item.gate_result)`, send with `view=GutCheckView(item.plan_v2.plan_id, plan_store)`; otherwise the exact previous call (no `view=` kwarg — byte-path regression rides the flags-off e2e). `GutCheckView.on_timeout` needs no body beyond the default (buttons disable; nothing recorded) — the test pins that it stays that way.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_gutcheck.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py tests/test_gate_gutcheck.py
git commit -m "feat: gut-check ritual on alerts"
```

### Task G126: Gut-check journaling analytics

**Files:** Modify `persistence.py`; test `tests/test_gate_persistence.py`

**Interfaces:** `gutcheck_stats(journal_entries) -> dict` — WR of trades with vs without a completed gut-check, and the "would I take it after a loss = no, taken anyway" cohort. Surfaces in `!gutcheck` (G156) and the journal browser (G186). Journal entries carry `gutcheck_present` since G84; this task additionally reads the stored answers dict (`gutcheck: {choice, why_wrong, after_loss}`) when G84's close hook copies it onto the entry (one-line additive change there).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_persistence.py`)

```python
from swingbot.core.gate.persistence import gutcheck_stats


def test_gutcheck_stats_golden():
    entries = (
        [{"outcome": "win", "gutcheck": {"choice": "follow", "after_loss": "yes"}}] * 6
        + [{"outcome": "loss", "gutcheck": {"choice": "follow", "after_loss": "yes"}}] * 2
        + [{"outcome": "win"}] * 3
        + [{"outcome": "loss"}] * 3
        # the cohort that matters: said "no" to after-loss, took it anyway
        + [{"outcome": "loss", "gutcheck": {"choice": "follow", "after_loss": "no"}}] * 3
        + [{"outcome": "win", "gutcheck": {"choice": "follow", "after_loss": "no"}}]
    )
    stats = gutcheck_stats(entries)
    assert stats["with_gutcheck"] == {"n": 12, "wr": 58.3}
    assert stats["without_gutcheck"] == {"n": 6, "wr": 50.0}
    assert stats["no_but_taken"] == {"n": 4, "wr": 25.0}     # the honest mirror


def test_gutcheck_stats_empty():
    assert gutcheck_stats([]) == {"with_gutcheck": {"n": 0, "wr": None},
                                  "without_gutcheck": {"n": 0, "wr": None},
                                  "no_but_taken": {"n": 0, "wr": None}}
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `persistence.py`):

```python
def gutcheck_stats(journal_entries: list[dict]) -> dict:
    """Did the §6 ritual earn its keep? WR with vs without a completed
    gut-check, plus the cohort that answered "would I take this after a
    loss?" with NO and took the trade anyway — the number the journal
    browser (G186) and !gutcheck (G156) lead with."""
    closed = [e for e in journal_entries if e.get("outcome") in ("win", "loss")]

    def _cohort(rows):
        n = len(rows)
        wr = (round(100.0 * sum(r["outcome"] == "win" for r in rows) / n, 1)
              if n else None)
        return {"n": n, "wr": wr}

    with_gc = [e for e in closed if e.get("gutcheck")]
    return {"with_gutcheck": _cohort(with_gc),
            "without_gutcheck": _cohort([e for e in closed if not e.get("gutcheck")]),
            "no_but_taken": _cohort([e for e in with_gc
                                     if (e["gutcheck"] or {}).get("after_loss") == "no"])}
```

Plus the additive G84 hook change: `on_trade_close` also copies the plan's stored gutcheck payload onto the journal entry (`journal_entry["gutcheck"] = get_gutcheck(store, plan_id)` when present — verify the hook's store access at execution).

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_persistence.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/persistence.py tests/test_gate_persistence.py
git commit -m "feat: gut-check outcome stats"
```

### Task G127: Plan store carries gate + macro at creation

**Files:** Modify the plan-creation path (plan_manager integration point); test `tests/test_gate_persistence.py`

**Interfaces:** every stored plan gains optional keys `gate` (GateResult dict), `macro_at_entry` (the G122 one-liner + composite score + VIX + next event — a compact dict, NOT the full snapshot). Old plans without keys load fine (additive-schema test). New pure builder: `macro_at_entry(snap) -> dict | None` in `gate/persistence.py`; the `gate` key is already written by G81's `attach_to_plan` — this task adds the macro stamp beside it at plan creation.
- [ ] **Step 1: Write the failing tests** (append to `tests/test_gate_persistence.py`)

```python
from swingbot.core.gate.persistence import macro_at_entry


def test_macro_at_entry_compact():
    snap = {"built_at": "2026-07-14T12:00:00", "stale": False,
            "composite": {"score": 67, "label": "risk_on"},
            "vix": {"level": 14.2, "regime": "calm"},
            "events": {"upcoming": [{"name": "CPI", "importance": 3,
                                     "at": "2026-07-17T08:30:00"}]}}
    stamp = macro_at_entry(snap)
    assert stamp["composite"] == 67 and stamp["vix"] == 14.2
    assert stamp["next_event"] == "CPI 2026-07-17"
    assert "line" in stamp and len(stamp["line"]) <= 120
    assert "sectors" not in stamp                      # compact, NOT the snapshot
    assert macro_at_entry(None) is None


def test_plan_stamps_round_trip_and_legacy_load(env):
    # env: the G81 fixture (tmp store with one plan)
    stamp = macro_at_entry({"built_at": "t", "stale": False})
    assert env.set_extra("p_test_0001", "macro_at_entry", stamp) is True
    loaded = env.get_extra("p_test_0001", "macro_at_entry")
    assert loaded == stamp
    # legacy: a plan that pre-dates the gate has neither key and loads fine
    assert env.get_extra("p_test_0001", "gate") is None or True   # no KeyError path
    assert env.get("p_test_0001") is not None
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `persistence.py`):

```python
def macro_at_entry(snap: dict | None) -> dict | None:
    """The compact market stamp stored on a plan at creation — what the
    world looked like when the trade was planned, small enough to keep
    forever: the G122 line, composite score, VIX, next high-impact event.
    NEVER the full snapshot (plans are long-lived; snapshots are big)."""
    if not snap:
        return None
    from swingbot.core.gate.render import macro_line
    nxt = next((e for e in (snap.get("events") or {}).get("upcoming", [])
                if int(e.get("importance", 0)) >= 3), None)
    return {"line": macro_line(snap),
            "composite": (snap.get("composite") or {}).get("score"),
            "vix": (snap.get("vix") or {}).get("level"),
            "next_event": (f"{nxt['name']} {str(nxt.get('at', ''))[:10]}"
                           if nxt else None),
            "stale": bool(snap.get("stale"))}
```

**Wiring** (the plan-creation path — where G121's `attach_to_plan` call landed): immediately after attaching the gate result, `store.set_extra(plan_id, "macro_at_entry", macro_at_entry(gate_ctx.macro_snap))` when a context exists. Nothing else changes — both keys ride the store's existing extra mechanism, so old plans are untouched by construction (the legacy-load test pins it anyway).

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_persistence.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/persistence.py swingbot/commands/scanning.py tests/test_gate_persistence.py
git commit -m "feat: gate+macro stamped on plans"
```

### Task G128: Re-check at entry trigger

**Files:** Modify the plan-trigger path in the monitor loop; test `tests/test_scan_gate_wiring.py`

**Interfaces:** a pending plan about to trigger re-runs the **cheap** subset (rf_news_whipsaw, rf_thin_session, not_chasing, calendar events — no network beyond the snapshot) via `run_checklist(subset="trigger")` (registry gains a `trigger_recheck: bool` column — default `False`, set `True` on exactly those checks; `run_checklist` already honors it since G75). A newly-fired flag at trigger time → **the alert message is updated with the new warning and a ping** ("⚠️ since this alert: CPI now within 18h") — the entry still fires normally; it is held per G120 semantics only when `GATE_BLACKOUT_ENFORCE`/enforce mode says so. Pure core: `recheck_delta(stored_gate: dict | None, new_result) -> list[str]`.
- [ ] **Step 1: Write the failing tests** (append to `tests/test_scan_gate_wiring.py`)

```python
from swingbot.commands.scanning import recheck_delta


def _recheck_result(fired):
    checks = tuple(CheckResult(f, "redflag", "fail", 6.0, f, {}) for f in fired)
    return GateResult(ticker="T", strategy="S", as_of="2026-07-15",
                      checks=checks, score=50.0, tier="B", hard_blocks=())


def test_recheck_delta_only_new_flags():
    stored = {"checks": [{"check_id": "rf_thin_session", "status": "fail"}]}
    new = _recheck_result(["rf_thin_session", "rf_news_whipsaw"])
    assert recheck_delta(stored, new) == ["rf_news_whipsaw"]   # already-known flag not re-warned


def test_recheck_delta_clean_is_empty():
    assert recheck_delta({"checks": []}, _recheck_result([])) == []


def test_recheck_delta_no_stored_gate_treats_all_as_new():
    assert recheck_delta(None, _recheck_result(["rf_news_whipsaw"])) == ["rf_news_whipsaw"]


def test_registry_trigger_subset_is_cheap():
    from swingbot.core.gate.registry import CHECKS
    subset = {cid for cid, spec in CHECKS.items() if spec.trigger_recheck}
    assert subset == {"rf_news_whipsaw", "rf_thin_session",
                      "not_chasing", "calendar_checked"}
```

- [ ] **Step 2: Run — FAIL**, then **implement**. Registry: add `trigger_recheck: bool = False` to the check spec dataclass and set it on the four checks above. Then in `scanning.py`:

```python
def recheck_delta(stored_gate: dict | None, new_result) -> list[str]:
    """Flags that fired at trigger time but NOT at alert time — the only
    thing worth interrupting the operator for. The signal was checked when
    it alerted; the world may have changed since."""
    known = {c["check_id"] for c in (stored_gate or {}).get("checks", [])
             if c.get("status") in ("fail", "warn")}
    return [c.check_id for c in new_result.checks
            if c.status in ("fail", "warn") and c.check_id not in known]
```

**Wiring** (`trade_monitor`, at the pending-plan trigger point, only when `GATE_ENABLED`): build the cheap context (saved snapshot only — never a fetch inside the monitor loop), `new = run_checklist(..., subset="trigger")`, `delta = recheck_delta(store.get_extra(plan_id, "gate"), new)`. Non-empty delta → edit the original alert message appending `"⚠️ since this alert: " + render.redflag_table(new)`-style lines + one ping message referencing the plan; **the entry still fires** (inform-first) unless `blackout_decision(...)` says `hold` under its own enforce flag (G120 path reused verbatim). Exception anywhere → entry fires as before + one log line (same never-costs-a-trade guard as G121). Monitor tests use a fake channel/message capture; the three paths (updated+fires / held / clean+silent) are asserted there and re-proven end-to-end in G143.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_scan_gate_wiring.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py swingbot/core/gate/registry.py tests/test_scan_gate_wiring.py
git commit -m "feat: trigger-time re-check (inform-first)"
```

### Task G129: Curated digest respects tiers

**Files:** Modify the digest builder (cockpit insights path); test `tests/test_gate_digest.py`

**Interfaces:** in inform mode the digest lists everything with its tier label leading each row (A+ first); only when enforce mode is on does the curated section restrict to tier ≥ A (WEAK-rule parity: B/C listed in a compact "watch, don't chase" line, never hidden). Pure core: `digest_sections(rows, mode) -> {"main": [...], "watch": [...]}` where each row is `{ticker, tier, line}`.
- [ ] **Step 1: Write the failing test**

```python
# tests/test_gate_digest.py
from swingbot.commands.scanning import digest_sections

ROWS = [{"ticker": "AAPL", "tier": "B", "line": "AAPL — pullback"},
        {"ticker": "NVDA", "tier": "A+", "line": "NVDA — breakout"},
        {"ticker": "MSFT", "tier": "C", "line": "MSFT — late chase"},
        {"ticker": "AMD", "tier": "A", "line": "AMD — retest"}]


def test_inform_lists_everything_tier_sorted():
    out = digest_sections(ROWS, "inform")
    assert [r["ticker"] for r in out["main"]] == ["NVDA", "AMD", "AAPL", "MSFT"]
    assert out["main"][0]["line"].startswith("[A+] ")  # tier label leads each row
    assert out["watch"] == []                          # nothing demoted in inform


def test_enforce_curates_but_never_hides():
    out = digest_sections(ROWS, "enforce")
    assert [r["ticker"] for r in out["main"]] == ["NVDA", "AMD"]
    # WEAK-rule parity: B/C still visible in the compact watch line
    assert [r["ticker"] for r in out["watch"]] == ["AAPL", "MSFT"]


def test_untierd_rows_sort_last_and_survive():
    rows = ROWS + [{"ticker": "TSLA", "tier": None, "line": "TSLA — no gate"}]
    out = digest_sections(rows, "inform")
    assert out["main"][-1]["ticker"] == "TSLA"         # no tier ≠ dropped
```

- [ ] **Step 2: Run — FAIL**, then **implement** (in `scanning.py`, next to the digest builder it feeds):

```python
_TIER_SORT = {"A+": 0, "A": 1, "B": 2, "C": 3}


def digest_sections(rows: list[dict], mode: str) -> dict:
    """Tier-aware digest split. Inform (the default): every row, best
    first, tier label leading. Enforce: curated main section ≥ A, with
    B/C in a compact watch-don't-chase list — demoted, never hidden."""
    ordered = sorted(rows, key=lambda r: _TIER_SORT.get(r.get("tier"), 9))
    labeled = [dict(r, line=(f"[{r['tier']}] {r['line']}" if r.get("tier")
                             else r["line"])) for r in ordered]
    if mode != "enforce":
        return {"main": labeled, "watch": []}
    return {"main": [r for r in labeled if r.get("tier") in ("A+", "A")],
            "watch": [r for r in labeled
                      if r.get("tier") not in ("A+", "A")]}
```

**Wiring** (the curated digest builder — cockpit insights path, capability-checked): rows gain their `tier` from each plan's stored gate stamp (`get_extra(plan_id, "gate")`); the watch section renders as one line — `"👀 Watch, don't chase: AAPL (B), MSFT (C)"`.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_digest.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py tests/test_gate_digest.py
git commit -m "feat: tier-aware digest"
```

### Task G130: Retrospective gains gate lines

**Files:** Modify `swingbot/core/retrospective.py`; test `tests/test_gate_digest.py`

**Interfaces:** daily retrospective appends (when gate active): `"Gate: N evaluated · X blocked (reasons…) · Y downgraded · shadow divergence Z"` + any G108 audit line due. One line, data from the day's logs; absent data → no line. Pure core: `gate_retro_line(counts: dict | None) -> str | None` — counts assembled from the day's blocked/shadow logs now, and from `telemetry.summary` once G135 lands (same keys by design).
- [ ] **Step 1: Write the failing test** (append to `tests/test_gate_digest.py`)

```python
from swingbot.core.retrospective import gate_retro_line


def test_gate_retro_line_golden():
    counts = {"evaluated": 14, "blocked": 2,
              "blocked_reasons": ["rf_fake_breakout", "tier C < A"],
              "downgraded": 1, "shadow_divergence": 3}
    line = gate_retro_line(counts)
    assert line == ("Gate: 14 evaluated · 2 blocked (rf_fake_breakout, "
                    "tier C < A) · 1 downgraded · shadow divergence 3")


def test_gate_retro_line_inform_day_has_no_block_noise():
    line = gate_retro_line({"evaluated": 9, "blocked": 0, "blocked_reasons": [],
                            "downgraded": 0, "shadow_divergence": 0})
    assert line == "Gate: 9 evaluated"                 # quiet day reads quiet


def test_gate_retro_line_absent_data_is_none():
    assert gate_retro_line(None) is None
    assert gate_retro_line({}) is None
    assert gate_retro_line({"evaluated": 0}) is None   # gate idle → no line
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `swingbot/core/retrospective.py`):

```python
def gate_retro_line(counts: dict | None) -> str | None:
    """One line in the daily retrospective when the gate did anything
    today; None otherwise (no line — never an empty stub). Zero-count
    parts are omitted so an inform-mode day reads as the quiet day it was."""
    if not counts or not counts.get("evaluated"):
        return None
    parts = [f"Gate: {counts['evaluated']} evaluated"]
    if counts.get("blocked"):
        reasons = ", ".join(counts.get("blocked_reasons", [])[:4])
        parts.append(f"{counts['blocked']} blocked" + (f" ({reasons})" if reasons else ""))
    if counts.get("downgraded"):
        parts.append(f"{counts['downgraded']} downgraded")
    if counts.get("shadow_divergence"):
        parts.append(f"shadow divergence {counts['shadow_divergence']}")
    return " · ".join(parts)
```

**Wiring** (`_post_retrospective` in `scanning.py` / the retrospective builder): assemble `counts` for the day — evaluated/downgraded from the day's attached gate results, blocked from `data/gate/blocked.jsonl`, divergence from `data/gate/shadow.jsonl` (line-count of would-blocks) — append the line when non-None, plus any G108 audit line due. Reading a missing/empty log file yields zero counts → no line (test the file-absent path in the builder's own test).

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_digest.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/retrospective.py swingbot/commands/scanning.py tests/test_gate_digest.py
git commit -m "feat: gate lines in retrospective"
```

### Task G131: Advisor payload integration (v5 present)

**Files:** Modify `swingbot/core/advisor/context.py` **if merged** (capability-checked import); test `tests/test_gate_advisor.py` (skipped when advisor absent)

**Interfaces:** `plan_review_payload` gains `gate: result.to_dict()` and `macro: macro_at_entry`; the advisor's prompt template sentence added: "The checklist verdict is data — critique it, don't parrot it." Advisor absent → no-op module guard, tests skip cleanly.

> **Execution note (G131–G133):** as of 2026-07-17 `swingbot/core/advisor/` does **not** exist in the repo — llm-advisor v5 is a separate planned round. If it is still unmerged when you reach this task: write the test file anyway (it documents the contract and passes-by-skipping via `importorskip`), commit, move on. The gate side needs **zero** changes — G131/G133 modify only advisor files. Exact builder names (`plan_review_payload`, `prompts.PLAN_REVIEW_TEMPLATE`) come from llm-advisor L11/L12 — verify against the merged code before editing.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gate_advisor.py
"""Advisor (llm-advisor v5) integration — every test in this module skips
cleanly when the advisor is not merged. The gate never depends on the
advisor; G131-G133 only enrich advisor payloads when both features exist."""
import pytest

pytest.importorskip("swingbot.core.advisor",
                    reason="llm-advisor v5 not merged — G131-G133 dormant")

from swingbot.core.advisor import context as adv_context   # noqa: E402

PLAN_RECORD = {
    "plan_id": "p_20260714_ab12", "ticker": "NVDA", "strategy": "RSI-Div",
    "gate": {"tier": "B", "score": 61.0, "hard_blocks": [],
             "checks": [{"check_id": "rf_fake_breakout", "status": "warn"}]},
    "macro_at_entry": {"composite": {"label": "risk_on", "score": 67}},
}


def test_plan_review_payload_carries_gate_and_macro():
    payload = adv_context.plan_review_payload(PLAN_RECORD)   # L11 signature — verify
    assert payload["gate"]["tier"] == "B"
    assert payload["gate"]["checks"][0]["check_id"] == "rf_fake_breakout"
    assert payload["macro"]["composite"]["label"] == "risk_on"


def test_plan_review_payload_without_gate_is_unchanged():
    record = {k: v for k, v in PLAN_RECORD.items()
              if k not in ("gate", "macro_at_entry")}
    payload = adv_context.plan_review_payload(record)
    assert "gate" not in payload and "macro" not in payload  # pre-gate plans unaffected


def test_prompt_template_tells_the_model_to_critique():
    from swingbot.core.advisor import prompts                # L12's template module
    assert "critique it, don't parrot it" in prompts.PLAN_REVIEW_TEMPLATE
```

- [ ] **Step 2: Run — FAIL (or SKIP if advisor absent → commit and stop here)**, then **implement** (inside the advisor's payload builder in `swingbot/core/advisor/context.py`, right after the existing plan fields are assembled):

```python
    # G131: the checklist verdict rides along as data for the reviewer —
    # the prompt tells the model to critique it, never to parrot it.
    gate = (plan_record or {}).get("gate")
    if gate:
        payload["gate"] = gate
        macro = plan_record.get("macro_at_entry")
        if macro:
            payload["macro"] = macro
```

And append this sentence to `prompts.PLAN_REVIEW_TEMPLATE` (same paragraph that describes the plan data): `"The checklist verdict is data — critique it, don't parrot it."`

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_advisor.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/advisor/context.py swingbot/core/advisor/prompts.py tests/test_gate_advisor.py
git commit -m "feat: gate context in advisor plan reviews"
```

### Task G132: Advisor headline nuance job (v5 present)

**Files:** Modify `swingbot/commands/scanning.py` (the gate-side hook — capability-checked, works today); advisor producers **if merged**; test `tests/test_gate_advisor.py`

**Interfaces:** when a candidate fires `rf_rumor_spike` with `unclear` classification and the advisor is enabled+budgeted: a `plan_review` job is enqueued with the headlines attached so Haiku adjudicates rumor-vs-confirmed *advisorily* (result lands via the normal L15 advisor field; the gate's own verdict is never overwritten). Absent advisor → nothing. The gate-side hook `_maybe_enqueue_rumor_review(result, plan_id, headlines) -> bool` is written NOW with a capability-checked import — it tests today via a stub advisor module and starts firing the day v5 merges.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_gate_advisor.py` — these do NOT skip; they inject a stub advisor module, so the hook is tested even before v5 merges. Put them ABOVE the module-level `importorskip` by moving that guard into the G131 tests' class/section, or simpler: put G131's skipping tests in their own module section and these first — `importorskip` must not kill these)

```python
# tests/test_gate_advisor.py (top of file, BEFORE the importorskip section)
"""G132 hook tests — run always: the advisor is stubbed into sys.modules."""
import sys
import types

from swingbot.core.gate.types import CheckResult, GateResult


def _result_with_rumor(classification):
    checks = (CheckResult("rf_rumor_spike", "redflags", "warn", 6.0,
                          "spike on unconfirmed headline",
                          {"classification": classification}),)
    return GateResult(ticker="NVDA", strategy="RSI-Div", as_of="2026-07-14",
                      checks=checks, score=55.0, tier="B", hard_blocks=())


def _stub_advisor(monkeypatch, *, budgeted=True):
    jobs = types.ModuleType("swingbot.core.advisor.jobs")
    jobs.calls = []
    jobs.enabled_and_budgeted = lambda: budgeted
    jobs.enqueue = lambda kind, **kw: jobs.calls.append((kind, kw))
    pkg = types.ModuleType("swingbot.core.advisor")
    monkeypatch.setitem(sys.modules, "swingbot.core.advisor", pkg)
    monkeypatch.setitem(sys.modules, "swingbot.core.advisor.jobs", jobs)
    return jobs


def test_unclear_rumor_enqueues_review_with_headlines(monkeypatch):
    import swingbot.commands.scanning as scanning
    jobs = _stub_advisor(monkeypatch)
    result = _result_with_rumor("unclear")
    fired = scanning._maybe_enqueue_rumor_review(
        result, "p_1", headlines=["NVDA said to weigh acquisition"])
    assert fired is True
    kind, kw = jobs.calls[0]
    assert kind == "plan_review" and kw["plan_id"] == "p_1"
    assert kw["extra"]["headlines"] == ["NVDA said to weigh acquisition"]
    assert result.checks[0].detail["classification"] == "unclear"  # verdict untouched


def test_confirmed_classification_enqueues_nothing(monkeypatch):
    import swingbot.commands.scanning as scanning
    jobs = _stub_advisor(monkeypatch)
    assert scanning._maybe_enqueue_rumor_review(
        _result_with_rumor("confirmed"), "p_1", headlines=[]) is False
    assert jobs.calls == []


def test_absent_advisor_is_a_quiet_noop(monkeypatch):
    import swingbot.commands.scanning as scanning
    for mod in ("swingbot.core.advisor", "swingbot.core.advisor.jobs"):
        monkeypatch.delitem(sys.modules, mod, raising=False)
    assert scanning._maybe_enqueue_rumor_review(
        _result_with_rumor("unclear"), "p_1", headlines=["x"]) is False


def test_unbudgeted_advisor_enqueues_nothing(monkeypatch):
    import swingbot.commands.scanning as scanning
    jobs = _stub_advisor(monkeypatch, budgeted=False)
    assert scanning._maybe_enqueue_rumor_review(
        _result_with_rumor("unclear"), "p_1", headlines=["x"]) is False
    assert jobs.calls == []
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `swingbot/commands/scanning.py`):

```python
def _maybe_enqueue_rumor_review(result, plan_id: str, headlines: list) -> bool:
    """G132: when the lexicon classifier answered 'unclear' (G37) and the
    llm-advisor (v5) is merged+enabled+budgeted, enqueue a plan_review job
    carrying the headlines so Haiku adjudicates rumor-vs-confirmed
    ADVISORILY. The gate's own verdict is never overwritten — the answer
    lands via the normal advisor field (L15). Returns True iff enqueued."""
    fired = next((c for c in result.checks
                  if c.check_id == "rf_rumor_spike"
                  and (c.detail or {}).get("classification") == "unclear"), None)
    if fired is None:
        return False
    try:
        from swingbot.core.advisor import jobs as advisor_jobs  # v5 — verify names (L14)
    except ImportError:
        return False
    if not advisor_jobs.enabled_and_budgeted():
        return False
    advisor_jobs.enqueue("plan_review", plan_id=plan_id,
                         extra={"headlines": headlines or [],
                                "question": "rumor or confirmed?"})
    return True
```

**Wiring** (G121's per-candidate block, one line after `attach_to_plan`): `_maybe_enqueue_rumor_review(result, item.plan_v2.plan_id, headlines)` — `headlines` is the same lazily-fetched list the checks consumed.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_advisor.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py tests/test_gate_advisor.py
git commit -m "feat: advisor adjudication of unclear news spikes"
```

### Task G133: Nightly analysis gains gate stats (v5 present)

**Files:** Modify advisor nightly payload **if merged**; test `tests/test_gate_advisor.py`

**Interfaces:** `nightly_payload` gains the day's gate telemetry + flag-outcome deltas so the local analyst reasons over them (schema untouched — data rides in the existing snapshot section). Advisor absent → skip (same `importorskip` section as G131).

- [ ] **Step 1: Write the failing test** (append to the **skipping** section of `tests/test_gate_advisor.py`, below the G131 `importorskip`)

```python
def test_nightly_payload_carries_gate_day_stats(monkeypatch, tmp_path):
    from swingbot.core.advisor import nightly              # L13's module — verify name
    import swingbot.core.gate.telemetry as telemetry
    monkeypatch.setattr(telemetry, "TELEMETRY_PATH",
                        str(tmp_path / "telemetry.jsonl"))
    telemetry.count("evaluated")
    telemetry.count("blocked", reason="rf_fake_breakout")
    payload = nightly.nightly_payload()                    # L13 signature — verify
    gate = payload["snapshot"]["gate"]
    assert gate["today"]["evaluated"] == 1
    assert gate["today"]["blocked"] == 1
    assert "flag_outcomes" in gate                         # G85 stats ride along


def test_nightly_payload_survives_gate_absence(monkeypatch):
    """A broken/empty gate layer must never break the nightly job."""
    from swingbot.core.advisor import nightly
    import swingbot.core.gate.telemetry as telemetry
    monkeypatch.setattr(telemetry, "summary",
                        lambda since=None: (_ for _ in ()).throw(OSError("disk")))
    payload = nightly.nightly_payload()
    assert "gate" not in payload["snapshot"]               # section omitted, no crash
```

- [ ] **Step 2: Run — FAIL (or SKIP if advisor absent → commit the test file and stop)**, then **implement** (inside the advisor's nightly payload builder, after the existing snapshot section is assembled):

```python
    # G133: the day's gate stats ride in the existing snapshot section —
    # schema untouched, section simply absent when the gate layer is off/broken.
    try:
        from swingbot.core.gate import telemetry
        from swingbot.core.gate.persistence import flag_outcome_stats
        payload["snapshot"]["gate"] = {
            "today": telemetry.summary(since=now.date().isoformat()),
            "flag_outcomes": flag_outcome_stats(journal_entries),
        }
    except Exception:  # noqa: BLE001 — gate absent/broken → payload unchanged
        payload["snapshot"].pop("gate", None)
```

(`journal_entries` = whatever the nightly builder already loads for its trade section; if it doesn't load them, pass `[]` — the flag stats are then empty, not wrong.)

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_advisor.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/advisor/nightly.py tests/test_gate_advisor.py
git commit -m "feat: gate stats in nightly advisor payload"
```

### Task G134: Kill-switch + throttle interop (v4 present)

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_scan_gate_wiring.py`

**Interfaces:** when edge-engine E45–E47 exist: kill-switch active → gate evaluation still runs (annotation continues, evidence keeps accruing) but enforce decisions defer to the kill switch (its "no new entries" outranks any A+ tier); drawdown throttle's size multiplier composes multiplicatively with G117's tier multiplier, floored at 0. Absent edge → no-op. The composition/precedence math is pure and lands NOW (tested unconditionally); only the two-line wiring is capability-checked.

> **Execution note:** as of 2026-07-17 no kill-switch or throttle code exists in the repo (edge-engine v4 is a separate round). The pure functions below carry the whole contract; the wiring block activates by itself when `swingbot.core.edge.killswitch` appears (verify the module/attr names against the merged edge-engine code — E45–E47).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_scan_gate_wiring.py`)

```python
def test_size_multipliers_compose_multiplicatively():
    # throttle 0.5 × tier 0.75 → 0.375; None means "no opinion" (×1)
    assert scanning.compose_size_multipliers(0.5, 0.75) == 0.375
    assert scanning.compose_size_multipliers(None, 0.75) == 0.75
    assert scanning.compose_size_multipliers(None, None) == 1.0
    assert scanning.compose_size_multipliers(0.0, 2.0) == 0.0     # floored at 0
    assert scanning.compose_size_multipliers(-0.5, 1.0) == 0.0    # negative → 0


def test_killswitch_outranks_any_tier():
    """'No new entries' beats an A+ pass — and a gate block stays a block."""
    assert scanning.entry_allowed_with_killswitch(True, "pass") is False
    assert scanning.entry_allowed_with_killswitch(True, "block") is False
    assert scanning.entry_allowed_with_killswitch(False, "pass") is True
    assert scanning.entry_allowed_with_killswitch(False, "block") is False
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `swingbot/commands/scanning.py`):

```python
def compose_size_multipliers(*mults) -> float:
    """G134: the drawdown throttle's multiplier (edge E46) and the tier
    sizing multiplier (G117) compose MULTIPLICATIVELY, floored at 0.
    None entries mean 'no opinion' (x1) — so either feature works alone."""
    out = 1.0
    for m in mults:
        if m is not None:
            out *= max(0.0, float(m))
    return max(0.0, out)


def entry_allowed_with_killswitch(kill_active: bool, gate_decision: str) -> bool:
    """G134 precedence: the kill switch (edge E45) outranks ANY gate
    verdict — an A+ tier never overrides 'no new entries'. Gate evaluation
    still runs upstream (annotation + evidence continue); only the entry
    decision defers. A gate block stays a block either way."""
    if kill_active:
        return False
    return gate_decision != "block"
```

**Wiring** (capability-checked, two places): (1) where G117 applies the tier multiplier, replace the bare multiplier with `compose_size_multipliers(_throttle_multiplier(), tier_mult)` where `_throttle_multiplier()` is `try: from swingbot.core.edge import throttle; return throttle.size_multiplier() / except ImportError: return None`; (2) at the entry-decision point in the enforce path, route through `entry_allowed_with_killswitch(_killswitch_active(), decision)` with the same try/except import pattern (`_killswitch_active()` returns False when edge is absent). Both helper names verified against edge E45–E47 at execution.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_scan_gate_wiring.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py tests/test_scan_gate_wiring.py
git commit -m "feat: gate interop with kill switch + throttle"
```

### Task G135: Gate telemetry counters

**Files:** Create `swingbot/core/gate/telemetry.py`; test `tests/test_gate_telemetry.py`

**Interfaces:** `count(event: str, at=None, **labels)` → appends `data/gate/telemetry.jsonl` (events: `evaluated`, `blocked` with `reason=`, `downgraded`, `held_for_event`, `recheck_held`, `provider_answer` with `provider=`/`unknown=`); `summary(since: str | None) -> dict` with keys **matching G130's retrospective counts by design** (`evaluated, blocked, blocked_reasons, downgraded, held_for_event, recheck_held, unknown_rate`) — consumed by the retrospective line (G130), admin (G185), and the health page.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gate_telemetry.py
import datetime as dt

import swingbot.core.gate.telemetry as telemetry


def _tmp_telemetry(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "TELEMETRY_PATH",
                        str(tmp_path / "telemetry.jsonl"))


def test_count_then_summary_roundtrip(tmp_path, monkeypatch):
    _tmp_telemetry(tmp_path, monkeypatch)
    at = dt.datetime(2026, 7, 14, 15, 0)
    for _ in range(3):
        telemetry.count("evaluated", at=at)
    telemetry.count("blocked", at=at, reason="rf_fake_breakout")
    telemetry.count("blocked", at=at, reason="tier C < A")
    telemetry.count("downgraded", at=at)
    telemetry.count("held_for_event", at=at)
    s = telemetry.summary()
    assert s["evaluated"] == 3 and s["blocked"] == 2
    assert s["blocked_reasons"] == ["rf_fake_breakout", "tier C < A"]
    assert s["downgraded"] == 1 and s["held_for_event"] == 1


def test_summary_since_filters_by_date(tmp_path, monkeypatch):
    _tmp_telemetry(tmp_path, monkeypatch)
    telemetry.count("evaluated", at=dt.datetime(2026, 7, 13, 10, 0))
    telemetry.count("evaluated", at=dt.datetime(2026, 7, 14, 10, 0))
    assert telemetry.summary(since="2026-07-14")["evaluated"] == 1
    assert telemetry.summary()["evaluated"] == 2


def test_unknown_rate_per_provider(tmp_path, monkeypatch):
    _tmp_telemetry(tmp_path, monkeypatch)
    at = dt.datetime(2026, 7, 14, 10, 0)
    telemetry.count("provider_answer", at=at, provider="fred", unknown=False)
    telemetry.count("provider_answer", at=at, provider="fred", unknown=True)
    telemetry.count("provider_answer", at=at, provider="finnhub", unknown=False)
    rates = telemetry.summary()["unknown_rate"]
    assert rates == {"fred": 0.5, "finnhub": 0.0}


def test_count_never_raises(tmp_path, monkeypatch):
    # unwritable path → count swallows; telemetry must never cost an alert
    monkeypatch.setattr(telemetry, "TELEMETRY_PATH",
                        str(tmp_path / "no_such_dir" / "x" / "t.jsonl"))
    monkeypatch.setattr(telemetry.os, "makedirs",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("ro")))
    telemetry.count("evaluated")                           # no exception
    assert telemetry.summary(since=None)["evaluated"] == 0


def test_summary_skips_corrupt_lines(tmp_path, monkeypatch):
    _tmp_telemetry(tmp_path, monkeypatch)
    telemetry.count("evaluated", at=dt.datetime(2026, 7, 14, 10, 0))
    with open(telemetry.TELEMETRY_PATH, "a", encoding="utf-8") as fh:
        fh.write("{corrupt\n")
    assert telemetry.summary()["evaluated"] == 1
```

- [ ] **Step 2: Run — FAIL**, then **implement**

```python
# swingbot/core/gate/telemetry.py
"""Gate telemetry — append-only JSONL counters. count() is fire-and-forget
(NEVER raises: telemetry must never cost an alert, same rule as the gate);
summary() aggregates for the retrospective (G130 — same keys by design),
the admin dashboard card (G185) and the health page."""
import datetime as dt
import json
import os

from swingbot import config

TELEMETRY_PATH = os.path.join(config.DATA_DIR, "gate", "telemetry.jsonl")


def count(event: str, at: dt.datetime | None = None, **labels) -> None:
    try:
        row = {"at": (at or dt.datetime.now()).isoformat(timespec="seconds"),
               "event": event, **labels}
        os.makedirs(os.path.dirname(TELEMETRY_PATH), exist_ok=True)
        with open(TELEMETRY_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception:  # noqa: BLE001
        pass


def summary(since: str | None = None) -> dict:
    """Aggregate counters at/after `since` (ISO date string; None = all).
    ISO timestamps compare lexicographically, so "2026-07-14T…" >= "2026-07-14"
    does the date filtering without parsing."""
    out = {"evaluated": 0, "blocked": 0, "blocked_reasons": [],
           "downgraded": 0, "held_for_event": 0, "recheck_held": 0,
           "unknown_rate": {}}
    if not os.path.exists(TELEMETRY_PATH):
        return out
    unknown_hits: dict[str, int] = {}
    unknown_totals: dict[str, int] = {}
    with open(TELEMETRY_PATH, encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if since and row.get("at", "") < since:
                continue
            ev = row.get("event")
            if ev in ("evaluated", "blocked", "downgraded",
                      "held_for_event", "recheck_held"):
                out[ev] += 1
                if ev == "blocked" and row.get("reason"):
                    out["blocked_reasons"].append(row["reason"])
            elif ev == "provider_answer":
                p = row.get("provider", "?")
                unknown_totals[p] = unknown_totals.get(p, 0) + 1
                if row.get("unknown"):
                    unknown_hits[p] = unknown_hits.get(p, 0) + 1
    out["unknown_rate"] = {p: round(unknown_hits.get(p, 0) / n, 3)
                          for p, n in unknown_totals.items()}
    return out
```

**Wiring** (three one-liners, all inside existing try/except so telemetry can never break the caller): G121's per-candidate block gains `telemetry.count("evaluated")` after `run_checklist`, `telemetry.count("blocked", reason=...)` next to `blocked_log`, `telemetry.count("downgraded")` on the downgrade branch; G120's hold path gains `telemetry.count("held_for_event")`; G128's re-check hold gains `telemetry.count("recheck_held")`. **G130's counts builder switches to `telemetry.summary(since=today.isoformat())`** for evaluated/blocked/downgraded (shadow divergence stays a `shadow.jsonl` line count) — its own test keeps passing because the keys match.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_telemetry.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/telemetry.py swingbot/commands/scanning.py swingbot/core/retrospective.py tests/test_gate_telemetry.py
git commit -m "feat: gate telemetry"
```

### Task G136: Scan latency budget with gate on

**Files:** Test `tests/test_scan_gate_perf.py`

- [ ] **Step 1: Write the test** — a stubbed 60-candidate scan with gate on (warm snapshot, no network) adds < 5 s total vs gate off (marker per G87); plus a unit budget: `GateContext` assembly < 500 ms with warm caches.

```python
# tests/test_scan_gate_perf.py
"""G136: the gate's whole-scan latency budget. No network, warm snapshot —
this is pure-compute cost, the only kind the gate is allowed to add."""
import datetime as dt
import time

import pytest

import swingbot.commands.scanning as scanning
import swingbot.config as config
from swingbot.core.gate import run_checklist
from tests.fixtures.gate import uptrend_daily
from tests.fixtures.gate.plans import make_plan

NOW = dt.datetime(2026, 7, 14, 23, 0, tzinfo=dt.timezone.utc)
WARM_SNAP = {"built_at": "2026-07-14T22:00:00+00:00", "stale": False,
             "composite": {"score": 50, "label": "risk_on",
                           "inputs_used": 5, "detail": []},
             "events": {"next_high_impact": None, "within_24h": [],
                        "today": [], "upcoming": [], "refreshed_at": "2026-07-14"}}


@pytest.mark.perf   # same marker G87 introduced — verify at execution
def test_sixty_candidate_gate_pass_under_five_seconds():
    df = uptrend_daily(n=500)
    plan = make_plan(created_at="2026-07-13",
                     trigger_price=float(df["Close"].iloc[-1]))
    run_checklist("WARM", plan.strategy, plan, df,
                  macro_snap=WARM_SNAP, now=NOW)               # warm-up / caches
    t0 = time.perf_counter()
    for i in range(60):
        result = run_checklist(f"T{i:02d}", plan.strategy, plan, df,
                               macro_snap=WARM_SNAP, now=NOW)
        scanning.gate_candidate(result, "inform", "A")
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, (
        f"gate added {elapsed:.1f}s for 60 candidates — batch the level "
        f"extraction / memoize per-ticker frames (G87's lru fix) before shipping")


@pytest.mark.perf
def test_gate_context_assembly_under_500ms(monkeypatch):
    monkeypatch.setattr(config, "MACRO_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "GATE_ENABLED", True, raising=False)
    monkeypatch.setattr(scanning, "_load_macro_snapshot", lambda: WARM_SNAP)
    scanning.build_gate_context(now=NOW)                       # warm-up
    t0 = time.perf_counter()
    scanning.build_gate_context(now=NOW)
    assert time.perf_counter() - t0 < 0.5
```

- [ ] **Step 2: Run — PASS** (`python -m pytest tests/test_scan_gate_perf.py -v`; if over budget, batch level extraction / memoize per-ticker frames — the G87 `lru_cache` seam is the expected fix, never a looser budget).
- [ ] **Step 3: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add tests/test_scan_gate_perf.py
git commit -m "test: scan latency budget with gate"
```

### Task G137: Alert routing by tier (channel option)

**Files:** Modify `swingbot/commands/scanning.py` + config; test `tests/test_scan_gate_wiring.py`

**Interfaces:** optional `GATE_APLUS_CHANNEL_ID` (int field, 0 = off): A+ alerts additionally mirrored to a dedicated channel (the "only the best" feed the 95% goal actually wants day-to-day). Mirror failure → log, never blocks the main alert. One async helper owns it: `_mirror_aplus(bot, embed, tier) -> bool` — called from `_send_alerts` per alert with the gate tier that G121 attached (extend the alert tuple `(embed, chart_path)` to carry `gate_tier` — match `_send_alerts`'s actual tuple shape at execution and default the new element to `None` so pre-gate callers are untouched).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_scan_gate_wiring.py`)

```python
import asyncio


class _FakeChannel:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, **kw):
        if self.fail:
            raise RuntimeError("discord hiccup")
        self.sent.append(kw)


class _FakeBot:
    def __init__(self, channel):
        self._channel = channel

    def get_channel(self, cid):
        return self._channel


def test_aplus_mirror_sends_only_aplus(monkeypatch):
    monkeypatch.setattr(config, "GATE_APLUS_CHANNEL_ID", 1234, raising=False)
    chan = _FakeChannel()
    bot = _FakeBot(chan)
    assert asyncio.run(scanning._mirror_aplus(bot, "EMBED", "A+")) is True
    assert asyncio.run(scanning._mirror_aplus(bot, "EMBED", "B")) is False
    assert len(chan.sent) == 1 and chan.sent[0]["embed"] == "EMBED"


def test_aplus_mirror_off_when_unconfigured(monkeypatch):
    monkeypatch.setattr(config, "GATE_APLUS_CHANNEL_ID", 0, raising=False)
    assert asyncio.run(scanning._mirror_aplus(
        _FakeBot(_FakeChannel()), "EMBED", "A+")) is False


def test_aplus_mirror_failure_never_raises(monkeypatch, caplog):
    monkeypatch.setattr(config, "GATE_APLUS_CHANNEL_ID", 1234, raising=False)
    bot = _FakeBot(_FakeChannel(fail=True))
    assert asyncio.run(scanning._mirror_aplus(bot, "EMBED", "A+")) is False
    assert any("mirror" in r.message.lower() for r in caplog.records)


def test_aplus_mirror_missing_channel_logs(monkeypatch, caplog):
    monkeypatch.setattr(config, "GATE_APLUS_CHANNEL_ID", 1234, raising=False)
    assert asyncio.run(scanning._mirror_aplus(
        _FakeBot(None), "EMBED", "A+")) is False
    assert any("not found" in r.message.lower() for r in caplog.records)
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `scanning.py`)

```python
async def _mirror_aplus(bot, embed, tier: str | None) -> bool:
    """G137: A+ alerts additionally mirror to a dedicated channel — the
    'only the best' feed. Best-effort: any failure logs and returns False;
    the main alert has already shipped and is never affected."""
    chan_id = int(getattr(config, "GATE_APLUS_CHANNEL_ID", 0) or 0)
    if not chan_id or tier != "A+":
        return False
    channel = bot.get_channel(chan_id)
    if channel is None:
        log.warning("GATE_APLUS_CHANNEL_ID=%s set but channel not found", chan_id)
        return False
    try:
        await channel.send(embed=embed)
        return True
    except Exception:  # noqa: BLE001
        log.warning("A+ mirror send failed — main alert unaffected", exc_info=True)
        return False
```

**Wiring** (`_send_alerts`, after the existing `destination.send(...)` per alert): `await _mirror_aplus(bot, embed, gate_tier)` — the chart file is deliberately NOT re-attached (a `discord.File` can't be sent twice; the mirror is a headline feed). Config Field: `Field("GATE_APLUS_CHANNEL_ID", "0", "Gatekeeper", "A+ mirror channel", type="int", help="Channel ID that additionally receives A+-tier alerts. 0 = off. Mirror failures never affect the main alert.")` — match the exact `Field` signature in `config.py`.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_scan_gate_wiring.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py swingbot/config.py tests/test_scan_gate_wiring.py
git commit -m "feat: A+ tier channel mirror"
```

### Task G138: Config completeness sweep for Phase G4

**Files:** Modify `swingbot/config.py`; test `tests/test_gate_config.py`

**Interfaces:** all Phase-G4 fields present + help texts: `GATE_SHOW_IN_SHADOW`, `GATE_BLACKOUT_ENFORCE`, `GATE_BLACKOUT_HOURS_BEFORE/AFTER`, `GATE_EARNINGS_BLACKOUT_DAYS`, `GATE_GUTCHECK_REQUIRED`, `GATE_TIER_SIZING_ENABLED`, `GATE_APLUS_CHANNEL_ID`, `GATE_MIN_DOLLAR_VOL`, `GATE_CHASE_ATR_MAX`, `GATE_MIN_RR`, `GATE_MAX_CORR_POSITIONS` (the last four are ThresholdSpec-backed per G79 — asserted to resolve through `spec.threshold`). Test asserts every config key referenced by any gate/macro module exists in FIELDS (import-and-introspect sweep).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_gate_config.py`)

```python
import pathlib
import re

import swingbot.config as config

PHASE_G4_FIELDS = [
    "GATE_SHOW_IN_SHADOW", "GATE_BLACKOUT_ENFORCE",
    "GATE_BLACKOUT_HOURS_BEFORE", "GATE_BLACKOUT_HOURS_AFTER",
    "GATE_EARNINGS_BLACKOUT_DAYS", "GATE_GUTCHECK_REQUIRED",
    "GATE_TIER_SIZING_ENABLED", "GATE_APLUS_CHANNEL_ID",
]


def _field_names():
    # Field's first positional attr is the env key — verify attr name
    # (.name vs .key) against the Field dataclass in config.py
    return {f.name for f in config.FIELDS}


def test_phase_g4_fields_present_with_help():
    names = _field_names()
    missing = [k for k in PHASE_G4_FIELDS if k not in names]
    assert not missing, f"config.FIELDS missing: {missing}"
    for f in config.FIELDS:
        if f.name in PHASE_G4_FIELDS:
            assert f.help, f"{f.name} has no help text"


def test_every_referenced_gate_key_has_a_field():
    """Import-and-introspect sweep: any config.GATE_*/MACRO_* attribute
    referenced anywhere in swingbot/ must be a declared Field — a key that
    exists only as getattr() default is a silent misconfiguration trap."""
    pattern = re.compile(
        r"(?:config\.((?:GATE|MACRO|FRED|FINNHUB)_[A-Z0-9_]+))"
        r"|(?:getattr\(config,\s*[\"']((?:GATE|MACRO|FRED|FINNHUB)_[A-Z0-9_]+)[\"'])")
    names = _field_names()
    offenders = []
    for path in pathlib.Path("swingbot").rglob("*.py"):
        for m in pattern.finditer(path.read_text(encoding="utf-8")):
            key = m.group(1) or m.group(2)
            if key not in names:
                offenders.append(f"{path.as_posix()}: {key}")
    assert not offenders, "referenced but undeclared:\n" + "\n".join(sorted(set(offenders)))


def test_threshold_backed_fields_resolve_through_spec():
    """GATE_MIN_DOLLAR_VOL / GATE_CHASE_ATR_MAX / GATE_MIN_RR /
    GATE_MAX_CORR_POSITIONS are ThresholdSpec-backed (G79): the registry
    spec resolves them, so a settings-page edit reaches the check."""
    from swingbot.core.gate.registry import CHECKS
    spec_of = {"rf_thin_session": "min_dollar_vol",
               "not_chasing": "chase_atr_max",
               "rr_realistic": "min_rr",
               "portfolio_room": "max_corr"}
    for check_id, th_name in spec_of.items():
        spec = CHECKS[check_id]
        assert th_name in spec.thresholds, f"{check_id} lost its {th_name} spec"
        assert spec.threshold(th_name) is not None
```

- [ ] **Step 2: Run — FAIL**, then **implement**: add every missing Field to the "Gatekeeper" section of `config.py` (checkbox/int/float types per the list above, each with a help sentence that states its default and its relax direction, e.g. `GATE_BLACKOUT_HOURS_BEFORE`: "Hours before a high-impact print during which new entries are annotated (or held, if blackout-enforce is on). Default 24. Lower = fewer annotations."). Fix any sweep offenders by declaring the missing Field, never by deleting the reference.
- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_config.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/config.py tests/test_gate_config.py
git commit -m "feat: gate config completeness"
```

### Task G139: Startup diagnostics

**Files:** Modify `swingbot/bot_core.py` startup; test `tests/test_gate_telemetry.py`

**Interfaces:** one log block when `GATE_ENABLED` or `MACRO_ENABLED`: mode, min tier, cuts, checks on/off count, FRED/Finnhub key presence, snapshot age, event calendar horizon, quota state — one WARNING per misconfiguration (enforce mode without the G105 sign-off file → auto-fallback to **inform** + loud warning; blackout-enforce on without event data → falls back to annotate-only + warning). Pure builder `gate_startup_diagnostics() -> tuple[list[str], list[str]]` (info lines, warning lines) in `scanning.py`; `bot_core.py` startup logs them.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_gate_telemetry.py`)

```python
import os

import swingbot.commands.scanning as scanning
import swingbot.config as config


def _diag_flags(monkeypatch, tmp_path, *, gate=True, macro=True,
                mode="inform", blackout_enforce=False, signoff=False):
    monkeypatch.setattr(config, "GATE_ENABLED", gate, raising=False)
    monkeypatch.setattr(config, "MACRO_ENABLED", macro, raising=False)
    monkeypatch.setattr(config, "GATE_MODE", mode, raising=False)
    monkeypatch.setattr(config, "GATE_BLACKOUT_ENFORCE", blackout_enforce,
                        raising=False)
    monkeypatch.setattr(scanning, "SIGNOFF_PATH",
                        str(tmp_path / "enforce_signoff.json"))
    if signoff:
        with open(scanning.SIGNOFF_PATH, "w", encoding="utf-8") as fh:
            fh.write('{"signed_at": "2026-07-01", "min_tier": "B"}')


def test_diagnostics_silent_when_everything_off(monkeypatch, tmp_path):
    _diag_flags(monkeypatch, tmp_path, gate=False, macro=False)
    info, warns = scanning.gate_startup_diagnostics()
    assert info == [] and warns == []


def test_diagnostics_info_block_lists_mode_and_keys(monkeypatch, tmp_path):
    _diag_flags(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "FRED_API_KEY", "k", raising=False)
    monkeypatch.setattr(config, "FINNHUB_API_KEY", "", raising=False)
    info, _ = scanning.gate_startup_diagnostics()
    joined = "\n".join(info)
    assert "mode=inform" in joined
    assert "FRED key: present" in joined and "Finnhub key: MISSING" in joined


def test_enforce_without_signoff_falls_back_to_inform(monkeypatch, tmp_path):
    _diag_flags(monkeypatch, tmp_path, mode="enforce", signoff=False)
    _, warns = scanning.gate_startup_diagnostics()
    assert any("falling back to inform" in w for w in warns)
    assert config.GATE_MODE == "inform"          # in-process only, .env untouched


def test_enforce_with_signoff_is_respected(monkeypatch, tmp_path):
    _diag_flags(monkeypatch, tmp_path, mode="enforce", signoff=True)
    _, warns = scanning.gate_startup_diagnostics()
    assert config.GATE_MODE == "enforce"
    assert not any("falling back" in w for w in warns)


def test_blackout_enforce_without_events_warns(monkeypatch, tmp_path):
    _diag_flags(monkeypatch, tmp_path, blackout_enforce=True)
    monkeypatch.setattr(scanning, "_load_macro_snapshot",
                        lambda: {"built_at": "t", "events": {"upcoming": []}})
    _, warns = scanning.gate_startup_diagnostics()
    assert any("annotate-only" in w for w in warns)
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `scanning.py`)

```python
SIGNOFF_PATH = os.path.join(config.DATA_DIR, "gate", "enforce_signoff.json")


def gate_startup_diagnostics() -> tuple[list[str], list[str]]:
    """G139: one startup block saying exactly what the gate/macro layer
    will do — and one WARNING per misconfiguration, each of which
    DOWNGRADES the behavior rather than crashing. The GATE_MODE fallback
    mutates the config module in-process only (the .env keeps the
    operator's value; the warning tells them why it isn't in effect)."""
    gate_on = getattr(config, "GATE_ENABLED", False)
    macro_on = getattr(config, "MACRO_ENABLED", False)
    if not (gate_on or macro_on):
        return [], []
    info, warns = [], []
    mode = getattr(config, "GATE_MODE", "inform")
    if mode == "enforce" and not os.path.exists(SIGNOFF_PATH):
        warns.append("GATE_MODE=enforce but data/gate/enforce_signoff.json "
                     "is absent (G105 evidence gate) — falling back to inform")
        config.GATE_MODE = mode = "inform"
    snap = None
    try:
        snap = _load_macro_snapshot()
    except Exception:  # noqa: BLE001
        pass
    if getattr(config, "GATE_BLACKOUT_ENFORCE", False):
        upcoming = ((snap or {}).get("events") or {}).get("upcoming", [])
        if not upcoming:
            warns.append("GATE_BLACKOUT_ENFORCE on but no event data — "
                         "annotate-only until the calendar refreshes")
    try:
        from swingbot.core.gate.registry import CHECKS
        enabled = sum(1 for s in CHECKS.values()
                      if getattr(config, s.config_flag, True))
        checks_line = f"checks: {enabled}/{len(CHECKS)} enabled"
    except Exception:  # noqa: BLE001
        checks_line = "checks: registry unavailable"
    age = "no snapshot yet"
    if snap and snap.get("built_at"):
        age = f"snapshot built {snap['built_at']}" + (" (stale)" if snap.get("stale") else "")
    info.extend([
        f"gate: enabled={gate_on} mode={mode} "
        f"min_tier={getattr(config, 'GATE_MIN_TIER', 'B')} "
        f"cuts A+/{getattr(config, 'GATE_TIER_APLUS_CUT', 90)} "
        f"A/{getattr(config, 'GATE_TIER_A_CUT', 75)} "
        f"B/{getattr(config, 'GATE_TIER_B_CUT', 55)}",
        checks_line,
        f"macro: enabled={macro_on} · {age}",
        f"FRED key: {'present' if getattr(config, 'FRED_API_KEY', '') else 'MISSING'} · "
        f"Finnhub key: {'present' if getattr(config, 'FINNHUB_API_KEY', '') else 'MISSING'}",
    ])
    return info, warns
```

**Wiring** (`bot_core.py` startup, same place other startup logging happens): `info, warns = gate_startup_diagnostics()`, log each info line at INFO and each warning at WARNING (one log call per line — the block must be greppable). Mirrors llm-advisor L30's pattern if merged.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_telemetry.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py swingbot/bot_core.py tests/test_gate_telemetry.py
git commit -m "feat: gate startup diagnostics"
```

### Task G140: E2E offline — clean pass path

**Files:** Test `tests/test_gate_e2e.py`

- [ ] **Step 1: Write the harness + the test** — tmp data dir, stubbed providers: a G7 clean-uptrend candidate in **inform mode (the default)** + fresh fake snapshot → embed carries 🌍 and 📋 fields (A-tier, no flags), plan stored with gate+macro stamps, telemetry `evaluated=1 blocked=0`. The harness drives the REAL pipeline pieces in the exact order the scan wires them (G119→G121→G81→G122/G123) — only data dirs and the snapshot are faked; if the wiring order in `scanning.py` changes, this file is the canary.

```python
# tests/test_gate_e2e.py
"""Offline end-to-end paths (G140-G144): fixture candidate -> gate ->
embed -> plan store -> logs. No network, no live bot. The pipeline
helper below mirrors the scan path's wiring ORDER exactly — G119's
context, G121's evaluation, G81's persistence, G122/G123's rendering."""
import datetime as dt

import pytest

import swingbot.commands.scanning as scanning
import swingbot.config as config
import swingbot.core.gate.persistence as persistence
import swingbot.core.gate.telemetry as telemetry
from swingbot.core.gate import run_checklist
from swingbot.core.gate.render import gate_embed_fields, macro_line
from swingbot.core.plan_store import PlanStore
from tests.fixtures.gate import breakout_and_fail, uptrend_daily
from tests.fixtures.gate.plans import make_plan

NOW = dt.datetime(2026, 7, 14, 18, 0)


def fresh_snapshot(now=NOW, **overrides):
    snap = {"built_at": now.isoformat(), "stale": False,
            "composite": {"score": 67, "label": "risk_on",
                          "inputs_used": 6, "detail": []},
            "vix": {"level": 14.2, "regime": "calm"},
            "curve": {"state": "normal"},
            "sectors": {"leader": "Tech", "rs_rows": [], "rotation": "risk_on"},
            "events": {"refreshed_at": now.isoformat(), "upcoming": [],
                       "next_high_impact": None, "within_24h": [], "today": []},
            "news": {"headlines_top5": [],
                     "sentiment": {"score": 0.1, "n": 4, "label": "neutral"},
                     "rumor_ratio": 0.0},
            "quality_warnings": []}
    snap.update(overrides)
    return snap


@pytest.fixture
def city(tmp_path, monkeypatch):
    """Isolated data city: every gate/macro path constant points at tmp."""
    monkeypatch.setattr(persistence, "BLOCKED_PATH",
                        str(tmp_path / "blocked.jsonl"))
    monkeypatch.setattr(persistence, "SHADOW_PATH",
                        str(tmp_path / "shadow.jsonl"))
    monkeypatch.setattr(telemetry, "TELEMETRY_PATH",
                        str(tmp_path / "telemetry.jsonl"))
    monkeypatch.setattr(config, "MACRO_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "GATE_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "GATE_MODE", "inform", raising=False)
    monkeypatch.setattr(config, "GATE_MIN_TIER", "A", raising=False)
    return PlanStore(path=str(tmp_path / "plans.json"))


def pipeline(df, plan, plan_store, snap, *, mode=None, now=NOW):
    """The scan path's gate block, in wiring order. Returns
    (decision, result, embed_fields) — embed_fields is what G122/G123
    would add to the alert embed (None entries filtered)."""
    mode = mode or config.GATE_MODE
    result = run_checklist(plan.ticker, plan.strategy, plan, df,
                           macro_snap=snap, open_plans=[], spy_df=None, now=now)
    decision, result = scanning.gate_candidate(result, mode, config.GATE_MIN_TIER)
    telemetry.count("evaluated", at=now)
    persistence.attach_to_plan(plan_store, plan.plan_id, result)
    if mode == "shadow":
        persistence.shadow_log(result)
    if decision == "block":
        reason = ", ".join(result.hard_blocks) or \
            f"tier {result.tier} < {config.GATE_MIN_TIER}"
        persistence.blocked_log(result, decision, reason)
        telemetry.count("blocked", at=now, reason=reason)
        return decision, result, []
    fields = []
    line = macro_line(snap)
    if line:
        fields.append(("🌍 Market", line))
    fields.extend(gate_embed_fields(
        result, mode, getattr(config, "GATE_SHOW_IN_SHADOW", False)))
    return decision, result, fields


def _stored_plan(df, plan_store):
    plan = make_plan(created_at="2026-07-13",
                     trigger_price=float(df["Close"].iloc[-1]))
    plan_store.add(plan)          # match PlanStore.add's exact shape at execution
    return plan


def test_clean_pass_inform(city):
    df = uptrend_daily(n=300)
    plan = _stored_plan(df, city)
    decision, result, fields = pipeline(df, plan, city, fresh_snapshot())
    assert decision == "pass"
    assert result.tier in ("A", "A+") and result.hard_blocks == ()
    names = [n for n, _ in fields]
    assert names[0] == "🌍 Market"                       # G122
    assert any(n.startswith("📋") for n in names)        # G123
    assert not any(n.startswith("🚩") for n in names)    # no flags fired
    stored = city.get(plan.plan_id)
    assert stored["gate"]["tier"] == result.tier         # G81 stamp
    s = telemetry.summary()
    assert s["evaluated"] == 1 and s["blocked"] == 0
```

- [ ] **Step 2: Run — PASS**: `python -m pytest tests/test_gate_e2e.py -v` (fix any drift between the harness and the actual wiring — the harness must keep mirroring `scanning.py`, never diverge to make the test pass).
- [ ] **Step 3: Commit**

```bash
python -m pytest tests/ -q && make check
git add tests/test_gate_e2e.py
git commit -m "test: gate e2e clean-pass path (inform)"
```

### Task G141: E2E offline — flagged-but-ships path (inform) + blocked path (opt-in enforce)

**Files:** Test `tests/test_gate_e2e.py`

- [ ] **Step 1: Write the inform test (the product's main path)** — a `breakout_and_fail` candidate in **inform mode** → alert SHIPS with a low tier, the ⛔ rf_fake_breakout row in the red-flag table, and the advisory line ("plan ships anyway; your call") when the would-be verdict is block; plan stored normally (not blocked); telemetry counts `evaluated=1 blocked=0`. (Append to `tests/test_gate_e2e.py`, reusing the G140 harness.)

```python
def _failing_candidate(city):
    df = breakout_and_fail(level=100.0)
    plan = _stored_plan(df, city)
    return df, plan


def test_flagged_candidate_still_ships_in_inform(city):
    df, plan = _failing_candidate(city)
    decision, result, fields = pipeline(df, plan, city, fresh_snapshot())
    assert decision == "pass"                            # inform NEVER drops
    fired = [c.check_id for c in result.checks
             if c.check_id == "rf_fake_breakout" and c.status in ("fail", "warn")]
    assert fired == ["rf_fake_breakout"]
    flat = "\n".join(v for _, v in fields)
    assert "Fake breakout" in flat                       # the ⛔ row renders
    if result.advisory_decision == "block":
        assert "plan ships anyway; your call" in flat
    stored = city.get(plan.plan_id)
    assert stored.get("status") != "blocked"             # stored NORMALLY
    s = telemetry.summary()
    assert s["evaluated"] == 1 and s["blocked"] == 0     # the inform invariant
```

- [ ] **Step 2: Write the enforce test** — the same candidate after opting into enforce + min-tier A → no embed fields (alert suppressed), blocked_log line with the reason, plan marked blocked, telemetry counts the block.

```python
def test_same_candidate_blocks_only_after_enforce_opt_in(city, monkeypatch):
    import json
    monkeypatch.setattr(config, "GATE_MODE", "enforce", raising=False)
    df, plan = _failing_candidate(city)
    decision, result, fields = pipeline(df, plan, city, fresh_snapshot())
    if result.advisory_decision != "block":              # guard: fixture must be bad enough
        pytest.skip("fixture no longer tiers below A — regenerate breakout_and_fail")
    assert decision == "block" and fields == []          # no alert
    with open(persistence.BLOCKED_PATH, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    assert len(rows) == 1 and rows[0]["ticker"] == plan.ticker
    assert "rf_fake_breakout" in rows[0]["reason"] or "tier" in rows[0]["reason"]
    s = telemetry.summary()
    assert s["evaluated"] == 1 and s["blocked"] == 1
    # blocked ≠ deleted: the plan record and its gate result survive
    assert city.get(plan.plan_id)["gate"]["tier"] == result.tier
```

The "plan stored status `blocked`" assertion belongs to G106's own tests (the enforce path sets it there); here the e2e pins the *observable* contract: no alert, a blocked_log receipt, the record preserved. `!blocked` listing it is asserted in G155's tests over the same `blocked.jsonl` shape.

- [ ] **Step 3: Run — PASS both**: `python -m pytest tests/test_gate_e2e.py -v`
- [ ] **Step 4: Commit**

```bash
python -m pytest tests/ -q && make check
git add tests/test_gate_e2e.py
git commit -m "test: gate e2e flagged-ships (inform) + blocked (enforce)"
```

### Task G142: E2E offline — shadow path

**Files:** Test `tests/test_gate_e2e.py`

- [ ] **Step 1: Write the test** — same failing candidate in shadow mode → zero embed fields added (user-visible output unchanged — this IS the byte-identity, since G122/G123 only ever *add* fields), shadow_log records the would-block, plan stored normally. (Append to `tests/test_gate_e2e.py`.)

```python
def test_shadow_mode_is_invisible_but_records(city, monkeypatch):
    import json
    monkeypatch.setattr(config, "GATE_MODE", "shadow", raising=False)
    monkeypatch.setattr(config, "GATE_SHOW_IN_SHADOW", False, raising=False)
    monkeypatch.setattr(config, "MACRO_ENABLED", False, raising=False)  # minimal mode
    df, plan = _failing_candidate(city)
    decision, result, fields = pipeline(df, plan, city, None)
    assert decision == "pass"
    assert fields == []                        # nothing user-visible differs
    with open(persistence.SHADOW_PATH, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    assert len(rows) == 1
    assert rows[0]["plan_id"] == plan.plan_id  # joined to outcomes later (G104)
    assert rows[0]["would_decision"] == result.advisory_decision
    assert city.get(plan.plan_id).get("status") != "blocked"
```

(Shadow-log row keys per G81/G103 — verify the exact names against `persistence.shadow_log` when writing.)

- [ ] **Step 2: Run — PASS**: `python -m pytest tests/test_gate_e2e.py -v`
- [ ] **Step 3: Commit**

```bash
python -m pytest tests/ -q && make check
git add tests/test_gate_e2e.py
git commit -m "test: gate e2e shadow path"
```

### Task G143: E2E offline — trigger re-check hold

**Files:** Test `tests/test_gate_e2e.py`

- [ ] **Step 1: Write the test** — plan passes at alert time; clock advances into a CPI blackout before trigger → G128's re-check holds the entry; after the window it releases. (Append to `tests/test_gate_e2e.py`; drives G120's `blackout_decision` + G128's re-check exactly as `trade_monitor` wires them.)

```python
def test_trigger_recheck_holds_through_blackout_then_releases(city, monkeypatch):
    monkeypatch.setattr(config, "GATE_BLACKOUT_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "GATE_BLACKOUT_ENFORCE", True, raising=False)
    monkeypatch.setattr(config, "GATE_BLACKOUT_HOURS_BEFORE", 24.0, raising=False)
    monkeypatch.setattr(config, "GATE_BLACKOUT_HOURS_AFTER", 2.0, raising=False)

    alert_time = NOW                                       # Tue 18:00, CPI Thu 08:30
    cpi_at = dt.datetime(2026, 7, 16, 8, 30)
    snap = fresh_snapshot(events={
        "refreshed_at": alert_time.isoformat(), "next_high_impact": None,
        "within_24h": [], "today": [],
        "upcoming": [{"name": "CPI", "importance": 3, "at": cpi_at.isoformat()}]})

    df = uptrend_daily(n=300)
    plan = _stored_plan(df, city)
    # 1) alert time: CPI is ~38h away — outside the window, plan passes clean
    assert scanning.blackout_decision(snap, alert_time) is None
    decision, _, _ = pipeline(df, plan, city, snap, now=alert_time)
    assert decision == "pass"

    # 2) trigger fires Wed 19:00 — inside the 24h window → hold
    trigger_time = dt.datetime(2026, 7, 15, 19, 0)
    verdict = scanning.blackout_decision(snap, trigger_time)
    assert verdict["action"] == "hold"
    release_at = dt.datetime.fromisoformat(verdict["release_at"])
    assert release_at == cpi_at + dt.timedelta(hours=2)
    telemetry.count("recheck_held", at=trigger_time)

    # 3) after the print + buffer → no blackout, entry releases
    after = release_at + dt.timedelta(minutes=1)
    assert scanning.blackout_decision(snap, after) is None
    assert telemetry.summary()["recheck_held"] == 1
```

The monitor-loop side (plan status flip to `held_for_event` and the release note on the alert) is pinned by G128's own wiring tests; this e2e pins the decision sequence across the clock.

- [ ] **Step 2: Run — PASS**: `python -m pytest tests/test_gate_e2e.py -v`
- [ ] **Step 3: Commit**

```bash
python -m pytest tests/ -q && make check
git add tests/test_gate_e2e.py
git commit -m "test: gate e2e trigger-hold path"
```

### Task G144: E2E offline — total darkness

**Files:** Test `tests/test_gate_e2e.py`

- [ ] **Step 1: Write the test** — the G43/G121 invariant end-to-end: no snapshot at all (all providers dead, caches empty), **enforce** mode → evaluation completes, macro-dependent checks answer `unknown`, zero blocks, alert ships. (Append to `tests/test_gate_e2e.py`.)

```python
def test_total_darkness_never_blocks_even_in_enforce(city, monkeypatch):
    monkeypatch.setattr(config, "GATE_MODE", "enforce", raising=False)
    df = uptrend_daily(n=300)
    plan = _stored_plan(df, city)
    # macro_snap=None IS total darkness: providers raising + empty caches
    # make load_snapshot return None (G38) — the pipeline sees exactly this.
    decision, result, fields = pipeline(df, plan, city, None)
    assert decision == "pass"                              # unknown never blocks
    macro_checks = [c for c in result.checks
                    if c.check_id in ("rf_news_whipsaw", "rf_rumor_spike",
                                      "rf_buy_rumor_sell_fact", "calendar_checked")]
    assert macro_checks and all(c.status == "unknown" for c in macro_checks)
    assert result.macro_stale is True
    assert telemetry.summary()["blocked"] == 0
    with pytest.raises(FileNotFoundError):
        open(persistence.BLOCKED_PATH, encoding="utf-8")   # nothing was ever blocked
```

(The "one health WARNING" half of the invariant lives at the provider layer and is already pinned by G43's tests — a snapshot rebuild in darkness logs it. This e2e pins the gate half: darkness in, alerts out, zero blocks.)

- [ ] **Step 2: Run — PASS**: `python -m pytest tests/test_gate_e2e.py -v`
- [ ] **Step 3: Commit**

```bash
python -m pytest tests/ -q && make check
git add tests/test_gate_e2e.py
git commit -m "test: gate e2e darkness (unknown never blocks)"
```

### Task G145: Operator runbook — scan integration

**Files:** Create `docs/gatekeeper-runbook.md`

- [ ] **Step 1: Write it** — this exact structure, every section filled from the shipped behavior (not from this plan — read the code/tests when unsure):

```markdown
# Gatekeeper — Operator Runbook

## Philosophy: inform first, always

The checklist is INFORMATION. In the default mode (`GATE_MODE=inform`)
every plan alerts, every alert is annotated, and NOTHING is ever
blocked. You decide; the gate shows its work. Enforce mode exists, is
optional, and is guarded by evidence (see "The mode ladder").

## The one-switch off

`GATE_ENABLED=false` — checklist gone, alerts byte-identical to
pre-gate. `MACRO_ENABLED=false` — market-context layer gone too.
Both are hot-reloadable from the settings page.

## What each embed field means

| Field | Source | Reading it |
|---|---|---|
| 🌍 Market | macro snapshot | risk composite, VIX regime, curve, leading sector, next event |
| 📋 Checklist — {tier} ({score}) | run_checklist | section pass/warn/fail counts |
| 🚩 Red flags | fired rf_* checks | one line per flag with its evidence |
| ⚠️ Event | blackout_decision | high-impact print inside the window |
| ⏸ held | blackout enforce (opt-in) | releases automatically after the print |

## The red flags (what fires them, what to do)

<one row per rf_* check: id, plain-English trigger, the evidence line
format, whether it can hard-block in enforce — copy the registry
docstrings, do not paraphrase from memory>

## The mode ladder

off -> shadow (logs only) -> INFORM (default, the product) ->
enforce-minB -> enforce-chosen-tiers (each enforce rung requires the
G105 sign-off file; loosening never requires sign-off)

## Too strict? Relax it from /gate

`GATE_STRICTNESS` preset (strict/balanced/relaxed) or per-check
threshold sliders. Loosening changes LABELS, not the underlying stats.
No A-tier plans in a week -> apply the relaxed preset and watch the
next scan's tiers.

## Reading the receipts

- `!blocked [date]` — everything held back or downgraded, with reasons
- `!tierwr` — live WR per tier vs the TRAIN fold numbers
- `!redflags` — per-flag live outcomes vs backtest ablation
- `!whycheck <plan_id>` — the stored verdict for any plan, post-mortem view

## Darkness behavior

All providers down -> every macro check answers "unknown", nothing
blocks (unknown NEVER blocks — tested end-to-end), one health WARNING,
alerts keep shipping. No action needed; the snapshot self-heals.

## Incident: enforce blocked something it shouldn't

1. Flip GATE_MODE to inform (no sign-off needed to loosen).
2. `!whycheck <plan_id>` — read the stored verdict.
3. File the check bug. NEVER hand-edit a stored result.
```

- [ ] **Step 2: Commit**

```bash
git add docs/gatekeeper-runbook.md
git commit -m "docs: gatekeeper operator runbook"
```

### Task G146: Phase G4 checkpoint

- [ ] **Step 1:** Full suite + `make check` green; all four e2e paths green; flags-off byte-identity regressions green.
- [ ] **Step 2:** Update Progress block. Commit — `chore: phase G4 checkpoint`

---
