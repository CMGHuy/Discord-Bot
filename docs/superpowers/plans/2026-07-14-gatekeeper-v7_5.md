# Gatekeeper v7 - Part 5/5: Scan & alert integration, forward gate & wrap-up (Tasks G119–G216 + appendix)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute strictly in order (G119 -> G216) — skipping the gaps left by cut tasks.
>
> **Provenance:** this is part 5 of 5 after the 2026-07-29 win-rate audit merged the previous 12 parts down (see "Scope note" below). Parts execute in numeric order.
> **Requires complete first:** Parts 1–4.
>
> Cross-part references (task numbers like G38, file names, `Interfaces:` blocks) refer to work done in earlier parts — those modules exist on the branch by the time this part runs.

## Progress

> Updated by the executing session after each task batch. Resume from the first unchecked task.
>
> - **Branch:** `main`
> - **Completed:** G119-G146 (all of Phase G4). Scan-path gate context (G119),
>   event blackout annotate-first/hold-opt-in (G120), per-candidate gate
>   evaluation with the inform-never-drops + unknowns-never-block invariants
>   (G121), kill-switch/throttle interop (G134), checklist embed field
>   (G123), trigger-time re-check (G128), telemetry counters (G135), and all
>   four e2e paths (clean-pass / flagged-ships-inform / blocked-enforce from
>   G140-G141, plus total-darkness reused from G43) are green. G122,
>   G124-G133 (except G134/G135), G136-G139 and G142-G145 are cut per the
>   index appendix — verified 2026-07-31 that none were skipped by mistake.
>   Full suite 2026-07-31: 1245 passed, 136 skipped, 1 failed (0 errors) —
>   the one failure is the documented pre-existing
>   `test_trade_monitor_wiring.py::test_flag_on_polls_open_plans`. Skip count
>   is above the CLAUDE.md-documented 54 baseline because this worktree has
>   no OHLCV CSV cache populated (`scripts/fetch_backtest_data.py` not run
>   here) — all extra skips are "no OHLCV cache present" in
>   `test_exit_parity.py`/`test_backtest_engine.py`, not gate-related.
> - **Next:** Task G206 (4-week paper forward-gate — blocked until the live
>   window elapses; not started by this checkpoint) — see the Phase G7
>   header note on prerequisites before picking it up.

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
# Phase G4 — Scan pipeline & alert integration (G119–G146)

The gate meets the live bot. Every task here is flag-gated and ships with a "flags off → byte-identical behavior" regression test.

### Task G119: Scan entry — snapshot + gate context assembly

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_scan_gate_wiring.py`

**Interfaces:** one `GateContext` assembled per scan run (not per ticker): `{macro_snap (G39), open_plans, spy_df, now}`; per-candidate additions (company headlines) fetched lazily inside `run_checklist` callers with the quota meter respected. `GateContext` built even when only `MACRO_ENABLED` (for embeds) — gate checks additionally need `GATE_ENABLED`.
- [x] **Step 1: Write the failing tests**

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

- [x] **Step 2: Run — FAIL**, then **implement** (add to `swingbot/commands/scanning.py`, near the scan-tick helpers):

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

- [x] **Step 3: Run — PASS**: `python -m pytest tests/test_scan_gate_wiring.py -v`
- [x] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py swingbot/core/scan_engine.py tests/test_scan_gate_wiring.py
git commit -m "feat: per-scan gate context"
```

### Task G120: Event blackout scan gate

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_scan_gate_wiring.py`

**Interfaces:** when `GATE_BLACKOUT_ENABLED` and an importance-3 event falls within the blackout window at scan time: **default behavior is annotation** — the plan is created and alerted normally with a prominent warning line ("⚠️ CPI 08:30 ET tomorrow — historically whipsaw-prone; consider waiting for the print"). Only when `GATE_BLACKOUT_ENFORCE` (new checkbox Field, default false) is *also* on are new entries marked `held_for_event` (plan created, alert says "⏸ held — releases after the print") and auto-released by the monitor loop once `hours_until(event) < -GATE_BLACKOUT_HOURS_AFTER`. Stale event calendar (> 7 days unrefreshed) auto-disables holding with a WARN — annotation continues. One pure decision function owns the whole rule: `blackout_decision(macro_snap, now) -> dict | None`.
- [x] **Step 1: Write the failing tests** (append to `tests/test_scan_gate_wiring.py`)

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

- [x] **Step 2: Run — FAIL**, then **implement** (append to `scanning.py`):

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

- [x] **Step 3: Run — PASS**: `python -m pytest tests/test_scan_gate_wiring.py -v`
- [x] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py swingbot/config.py tests/test_scan_gate_wiring.py
git commit -m "feat: event blackout annotate-first, hold opt-in"
```

### Task G121: Per-candidate gate evaluation in the scan path

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_scan_gate_wiring.py`

**Interfaces:** the alert path calls `run_checklist` per surviving candidate (background thread, same place llm-advisor L14 hooks), applies `with_advisory()` per mode (G76/G103/G106 semantics unified here — shadow/inform always pass), attaches results (G81). Two hard invariants tested here: (1) **inform mode never drops an alert** — property test over arbitrary GateResults including all-fail/hard-block ones; (2) extends the G43 proof through the gate: all providers down → all candidates evaluate with unknowns → **no block ever fires on unknowns** even in enforce mode. The unifying function is pure and owns every invariant: `gate_candidate(result, mode, min_tier) -> (decision, result)`.
- [x] **Step 1: Write the failing tests** (append to `tests/test_scan_gate_wiring.py`)

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

- [x] **Step 2: Run — FAIL**, then **implement** (append to `scanning.py`):

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

- [x] **Step 3: Run — PASS**: `python -m pytest tests/test_scan_gate_wiring.py -v`
- [x] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py tests/test_scan_gate_wiring.py
git commit -m "feat: gate evaluation in scan path (inform never drops, unknown never blocks)"
```

### Task G123: Alert embed — checklist field

**Files:** Modify `embeds.py`; test `tests/test_embeds_gate.py`

**Interfaces:** `build_embed(..., gate: dict | None = None)` — renders G82's `checklist_field` + (when any flag fired) `redflag_table` as a second field, plus the `advisory_decision` line when enforce-would-have-blocked ("⛔ 2 red flags — plan ships anyway; your call"). Render matrix: `inform` and `enforce` modes render always (**inform is the default — this field is the product**); `shadow` renders only with `GATE_SHOW_IN_SHADOW` (new checkbox field, default false). None → byte-identical. One pure function owns the matrix: `gate_embed_fields(result, mode, show_in_shadow) -> list[tuple[str, str]]` in `gate/render.py`.
- [x] **Step 1: Write the failing tests** (append to `tests/test_embeds_gate.py`; reuse the `_result()` fixture shape from `tests/test_gate_render.py` — import it or lift it into `tests/fixtures/gate/`)

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

- [x] **Step 2: Run — FAIL**, then **implement** (append to `gate/render.py`):

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

- [x] **Step 3: Run — PASS**: `python -m pytest tests/test_embeds_gate.py -v`
- [x] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/render.py swingbot/core/scanning/embeds.py swingbot/commands/scanning.py swingbot/config.py tests/test_embeds_gate.py
git commit -m "feat: checklist field on alerts (inform-first)"
```

### Task G128: Re-check at entry trigger

**Files:** Modify the plan-trigger path in the monitor loop; test `tests/test_scan_gate_wiring.py`

**Interfaces:** a pending plan about to trigger re-runs the **cheap** subset (rf_news_whipsaw, rf_thin_session, not_chasing, calendar events — no network beyond the snapshot) via `run_checklist(subset="trigger")` (registry gains a `trigger_recheck: bool` column — default `False`, set `True` on exactly those checks; `run_checklist` already honors it since G75). A newly-fired flag at trigger time → **the alert message is updated with the new warning and a ping** ("⚠️ since this alert: CPI now within 18h") — the entry still fires normally; it is held per G120 semantics only when `GATE_BLACKOUT_ENFORCE`/enforce mode says so. Pure core: `recheck_delta(stored_gate: dict | None, new_result) -> list[str]`.
- [x] **Step 1: Write the failing tests** (append to `tests/test_scan_gate_wiring.py`)

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

- [x] **Step 2: Run — FAIL**, then **implement**. Registry: add `trigger_recheck: bool = False` to the check spec dataclass and set it on the four checks above. Then in `scanning.py`:

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

- [x] **Step 3: Run — PASS**: `python -m pytest tests/test_scan_gate_wiring.py -v`
- [x] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py swingbot/core/gate/registry.py tests/test_scan_gate_wiring.py
git commit -m "feat: trigger-time re-check (inform-first)"
```

### Task G134: Kill-switch + throttle interop (v4 present)

**Files:** Modify `swingbot/commands/scanning.py`; test `tests/test_scan_gate_wiring.py`

**Interfaces:** when edge-engine E45–E47 exist: kill-switch active → gate evaluation still runs (annotation continues, evidence keeps accruing) but enforce decisions defer to the kill switch (its "no new entries" outranks any A+ tier); drawdown throttle's size multiplier composes multiplicatively with G117's tier multiplier, floored at 0. Absent edge → no-op. The composition/precedence math is pure and lands NOW (tested unconditionally); only the two-line wiring is capability-checked.

> **Execution note:** as of 2026-07-17 no kill-switch or throttle code exists in the repo (edge-engine v4 is a separate round). The pure functions below carry the whole contract; the wiring block activates by itself when `swingbot.core.edge.killswitch` appears (verify the module/attr names against the merged edge-engine code — E45–E47).

- [x] **Step 1: Write the failing tests** (append to `tests/test_scan_gate_wiring.py`)

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

- [x] **Step 2: Run — FAIL**, then **implement** (append to `swingbot/commands/scanning.py`):

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

- [x] **Step 3: Run — PASS**: `python -m pytest tests/test_scan_gate_wiring.py -v`
- [x] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/scanning.py tests/test_scan_gate_wiring.py
git commit -m "feat: gate interop with kill switch + throttle"
```

### Task G135: Gate telemetry counters

**Files:** Create `swingbot/core/gate/telemetry.py`; test `tests/test_gate_telemetry.py`

**Interfaces:** `count(event: str, at=None, **labels)` → appends `data/gate/telemetry.jsonl` (events: `evaluated`, `blocked` with `reason=`, `downgraded`, `held_for_event`, `recheck_held`, `provider_answer` with `provider=`/`unknown=`); `summary(since: str | None) -> dict` with keys **matching G130's retrospective counts by design** (`evaluated, blocked, blocked_reasons, downgraded, held_for_event, recheck_held, unknown_rate`) — consumed by the retrospective line (G130), admin (G185), and the health page.

- [x] **Step 1: Write the failing tests**

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

- [x] **Step 2: Run — FAIL**, then **implement**

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

- [x] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_telemetry.py -v`
- [x] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/telemetry.py swingbot/commands/scanning.py swingbot/core/retrospective.py tests/test_gate_telemetry.py
git commit -m "feat: gate telemetry"
```

### Task G140: E2E offline — clean pass path

**Files:** Test `tests/test_gate_e2e.py`

- [x] **Step 1: Write the harness + the test** — tmp data dir, stubbed providers: a G7 clean-uptrend candidate in **inform mode (the default)** + fresh fake snapshot → embed carries 🌍 and 📋 fields (A-tier, no flags), plan stored with gate+macro stamps, telemetry `evaluated=1 blocked=0`. The harness drives the REAL pipeline pieces in the exact order the scan wires them (G119→G121→G81→G122/G123) — only data dirs and the snapshot are faked; if the wiring order in `scanning.py` changes, this file is the canary.

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

- [x] **Step 2: Run — PASS**: `python -m pytest tests/test_gate_e2e.py -v` (fix any drift between the harness and the actual wiring — the harness must keep mirroring `scanning.py`, never diverge to make the test pass).
- [x] **Step 3: Commit**

```bash
python -m pytest tests/ -q && make check
git add tests/test_gate_e2e.py
git commit -m "test: gate e2e clean-pass path (inform)"
```

### Task G141: E2E offline — flagged-but-ships path (inform) + blocked path (opt-in enforce)

**Files:** Test `tests/test_gate_e2e.py`

- [x] **Step 1: Write the inform test (the product's main path)** — a `breakout_and_fail` candidate in **inform mode** → alert SHIPS with a low tier, the ⛔ rf_fake_breakout row in the red-flag table, and the advisory line ("plan ships anyway; your call") when the would-be verdict is block; plan stored normally (not blocked); telemetry counts `evaluated=1 blocked=0`. (Append to `tests/test_gate_e2e.py`, reusing the G140 harness.)

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

- [x] **Step 2: Write the enforce test** — the same candidate after opting into enforce + min-tier A → no embed fields (alert suppressed), blocked_log line with the reason, plan marked blocked, telemetry counts the block.

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

- [x] **Step 3: Run — PASS both**: `python -m pytest tests/test_gate_e2e.py -v`
- [x] **Step 4: Commit**

```bash
python -m pytest tests/ -q && make check
git add tests/test_gate_e2e.py
git commit -m "test: gate e2e flagged-ships (inform) + blocked (enforce)"
```

### Task G146: Phase G4 checkpoint

- [x] **Step 1:** Full suite green (2026-07-31): 1245 passed, 136 skipped, 1
  failed (0 errors) — the one failure is the documented pre-existing
  `test_trade_monitor_wiring.py::test_flag_on_polls_open_plans`; extra skips
  vs. the CLAUDE.md 54-baseline are all "no OHLCV cache present" in this
  worktree, unrelated to the gate. `py_compile` sweep over
  `bot.py admin_ui.py swingbot/**/*.py` (136 files) clean. All four e2e paths
  green: `test_gate_e2e.py::test_clean_pass_inform`,
  `test_flagged_candidate_still_ships_in_inform`,
  `test_same_candidate_blocks_only_after_enforce_opt_in` (G140/G141), plus
  the total-darkness proof reused from G43 (`test_macro_degradation.py`).
  Flags-off byte-identity regressions green:
  `test_context_none_when_everything_off` (`test_scan_gate_wiring.py`),
  `test_none_result_renders_nothing` +
  `test_build_embed_no_gate_fields_when_result_is_none`
  (`test_embeds_gate.py`).
- [x] **Step 2:** Progress block updated above. Commit — `chore(G146): phase G4 checkpoint`

---

# Phase G7 — Forward gate & wrap-up (G206–G216)

The governance/ops ceremony that filled this phase was cut; what remains is the
live-forward proof (G206) and the two closing checkpoints.

### Task G206: 4-week paper forward-gate for the A+ channel

> **Audit note (2026-07-29):** this is the plan's live-forward proof and the last gate before the
> A+ channel is trusted. It replaces the cut shadow-sign-off ceremony (G105) — do not skip it.

**Files:** Create `docs/superpowers/results/2026-08-gate-forward-test.md` (template now, filled during the gate)

- [ ] **Step 1: Write the template + procedure** — this exact content (filled-in cells stay blank until the gate actually runs):

```markdown
# A+ Forward Gate — 4-week paper test (pre-registered)

**Status:** template — runs only after enforce-mode promotion (G105/G106).
**Window:** 4 calendar weeks from the first A+ alert after promotion.
Start date: ____  End date: ____

## Pre-registered pass criteria (ALL must hold — written before the data)

- [ ] >= 10 A+ signals occurred in the window (else: extend 2 weeks, once)
- [ ] A+ cohort live WR Wilson LB >= B-tier cohort live WR (point estimate)
- [ ] A+ cohort expectancy (R) >= B-tier cohort expectancy
- [ ] zero gate-attributable incidents (crashes, wrong holds)

## Data (filled during the window — source: shadow/journal joins, !tierwr)

| week | A+ signals | A+ W-L | A+ WR (LB) | B WR | notes |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |

## On pass
Enforce may move from min-tier B to the chosen-tier ladder (G207).

## On fail (pre-registered — no renegotiation after seeing data)
Tier cuts revert to proposal state; gate stays enforce at min-tier B;
next attempt requires a fresh G98 frontier run and a new 4-week window.
```

- [ ] **Step 2: Commit** — `git add docs/superpowers/results/2026-08-gate-forward-test.md && git commit -m "docs: A+ forward-gate template (pre-registered)"`

### Task G215: Live smoke — the full ritual, end to end

**Files:** Update the Progress block with evidence notes

- [ ] **Step 1: In order, on the real bot with real keys:** (a) `scripts/macro_smoke.py` green; (b) `!macro`, `!calendar`, `!sectors`, `!sentiment`, `!yields`, `!inflation` in a test channel; (c) enable `MACRO_ENABLED` + `GATE_ENABLED` (**inform mode, the default**) → trigger a scan → alert with 🌍 + 📋 fields, red flags rendered when fired, plan created regardless of tier; (d) `!checklist NVDA` full run; (e) `/macro`, `/gate` (drag a threshold slider, apply the relaxed preset, watch the next scan's tiers shift), `/events`, `/macro/health` admin pages with live data; (f) blackout dry-run: set a fake imminent event in a test copy of the calendar, verify the annotation appears while the plan still ships (and hold/release only with `GATE_BLACKOUT_ENFORCE`); (g) confirm zero blocks occurred in inform mode (telemetry `blocked=0` — the invariant, live) and the darkness test still passes offline.
- [ ] **Step 2: Note evidence in the Progress block. Commit** — `chore: live smoke evidence`

### Task G216: Final checkpoint — plan complete

- [ ] **Step 1:** Full suite + `make check` green. All evidence docs committed (baseline, frontier, ablation, decision memo, QA, pre-mortem).
- [ ] **Step 2:** Enforce mode is **deliberately not** part of this plan's completion — it is an optional rung the operator may never climb. The plan is complete when **inform mode runs live**: every alert annotated, nothing blocked, thresholds tunable from `/gate`, and the evidence pipeline (`!tierwr`, shadow reports, receipts) full.
- [ ] **Step 3:** Update Progress block (Completed: G1–G216). Commit — `chore: gatekeeper v7 complete (inform mode live, enforce stays optional)`

---

---

# Appendix — carried-over verification debt (G217–G219)

> Not part of the win-rate path. These three tasks audit *other* plans (`unified-plan-engine-v2`, `cockpit-v3`, `llm-advisor-v5`) and were kept only so the debt they track is not lost with the old Part 12. They may run in any order, or be dropped, without affecting anything above.

**Goal:** Close out verification debt that a 2026-07-27 plan audit surfaced in plans OTHER than gatekeeper: two cases where a plan reached "Completed" status with pre-registered live-verification steps explicitly skipped by user decision rather than passed, and one case (`llm-advisor-v5`) where implementation status was never independently confirmed and might have the same problem gatekeeper-v7 itself turned out to have (fully planned, zero code, zero branch, zero commits).

### Task G217: Reconcile unified-plan-engine-v2's skipped staged-rollout gates

**Context:** Tasks 85, 88, 89 §3-4, 90, 91, and 94 of `unified-plan-engine-v2` were a staged rollout (shadow mode ≥5 sessions → enable → watch a week → enable scale-out → watch another week → phase checkpoint) with live-verification gates at each step. Per `docs/superpowers/results/2026-07-v2-final-report.md:88-119`, the user explicitly chose to skip the entire staged rollout and deploy straight to production (commit `8aef8e5`, 2026-07-18). Those checkpoints were never actually passed — but the system has since run in production for weeks with real telemetry accumulating that the original tasks didn't have when written.

**Files:** Read-only against `unified-plan-engine-v2.md` Tasks 85/88/89/90/91/94, `data/scan_telemetry.jsonl`, `data/trades.json`, `data/journal.json`. Write: `docs/superpowers/results/2026-07-gate-carryover-e2v2.md`.

- [ ] **Step 1:** For each of the six skipped checkpoints, restate in one sentence what it was meant to verify (e.g. Task 88: "shadow-mode v2 plans match legacy scenario numbers, 0 invariant violations, ≥80% coverage over ≥5 sessions").
- [ ] **Step 2:** For each, check whether real production data since 2026-07-18 can answer the same question retroactively (e.g. `shadow_parity_report.py` needs actual shadow-mode logs — if the system went straight to `PLAN_ENGINE_V2=on` with no shadow period, this data was never generated and the checkpoint literally cannot be answered from history; say so plainly rather than approximating).
- [ ] **Step 3:** For every checkpoint you *can* answer retroactively, do so and record the number/verdict. For every one you cannot, write an explicit waiver: what it was, why it can't be verified after the fact, and what weaker evidence (if any) substitutes for it (e.g. "system has run N weeks in production with zero related incidents" is weaker than the original gate but is honest about being weaker).
- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/2026-07-gate-carryover-e2v2.md
git commit -m "docs: reconcile unified-plan-engine-v2's skipped staged-rollout gates"
```

### Task G218: Run or waive cockpit-v3's skipped live-mutation smoke

**Context:** `cockpit-v3` Task B38 §2 (live smoke: `!plans`, `!top 3` buttons, `!stats`, `!lessons`, `!calibration`, scan-cycle alert ordering) and Task C46 §2 (admin UI live-mutation pass: launch a real TRAIN tuning grid, edit/export/import settings, cancel/close a real plan) were both **deliberately skipped** per their own Progress blocks (`cockpit-v3.md:17` and `:25` — C46's read-only portion done, live-mutation portion explicitly not performed).

**Files:** Write: `docs/superpowers/results/2026-07-gate-carryover-cockpit.md`.

- [ ] **Step 1:** Stand up a dev bot + dev admin UI against a *copy* of production data — never against the real prod DB for the mutation steps, since cancelling/closing a plan and editing settings must not touch live state.
- [ ] **Step 2:** Run B38 §2's live smoke exactly as originally specified; note pass/fail per bullet.
- [ ] **Step 3:** Run C46 §2's live-mutation pass exactly as originally specified (grid launch, settings edit/export/import, plan cancel/close) against the dev copy; note pass/fail per bullet.
- [ ] **Step 4:** If cockpit-v3's admin UI has since been substantially replaced by `admin-ui-tradingview-redesign-v8` by the time this task runs, note that explicitly and redirect this verification to the newer UI's equivalent smoke (Task U36) instead of testing dead pages — don't fabricate a pass against code that no longer exists.
- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/2026-07-gate-carryover-cockpit.md
git commit -m "docs: run cockpit-v3's previously-skipped live-mutation smoke"
```

### Task G219: Audit llm-advisor-v5's implementation status (Phase G8 checkpoint — Part 12 complete)

**Context:** The 2026-07-27 plan audit found gatekeeper-v6/v7 fully planned (219 tasks, ~950 KB of task detail) but with **zero** implementing code, no feature branch, and no implementation commits — 0%, not "mostly done," contradicting a stale memory note. `llm-advisor-v5` showed the same red flags in a quick check during that audit (no code found for it) but was **not verified as thoroughly** as gatekeeper was. This task closes that gap using the identical method, and serves as this part's phase checkpoint.

**Files:** Read-only. Write: a status note at the top of `llm-advisor-v5.md`'s Progress block, and (if warranted) an update to CLAUDE.md's "on disk but not current focus" line.

- [ ] **Step 1:** `grep -c "- \[x\]"` across `llm-advisor-v5.md` — if 0, the plan's own tracking says nothing is done.
- [ ] **Step 2:** Check whether the code the plan describes exists: an Ollama integration module, an Anthropic-provider module, `scripts/eval_advisor.py`, `run_worker.ps1`, an `/advisor` admin page. Absence of all of them corroborates "not started."
- [ ] **Step 3:** `git log --all --grep "advisor"` and check for a `feature/llm-advisor` branch — planning-only commits (write/split/edit the plan doc) don't count as implementation.
- [ ] **Step 4:** Write the honest verdict into `llm-advisor-v5.md`'s Progress block. If it's 0% like gatekeeper was, say so in the same direct terms — don't soften it. Update CLAUDE.md only if its current wording is actually misleading (it currently just lists the plan as "on disk but not current focus," which is compatible with either partial or zero progress — no change needed unless this step finds something that contradicts even that).
- [ ] **Step 5: Commit** (docs-only; no code changes expected from this task)

```bash
git add docs/superpowers/plans/2026-07-11-llm-advisor-v5.md
git commit -m "docs: verify llm-advisor-v5 implementation status"
```

- [ ] **Step 6: Part 12 checkpoint.** All three carry-over docs committed (`2026-07-gate-carryover-e2v2.md`, `2026-07-gate-carryover-cockpit.md`, G219's status verdict). Update this part's Progress block (Completed: G217-G219) and mirror into `2026-07-14-gatekeeper-v7_0-index.md`'s status table (Part 12 row: not started → done).
