# Gatekeeper v6 - Part 3/11: Macro data layer II: events, news, snapshot & degradation (Tasks G29-G44)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute strictly in order (G29 -> G44).
>
> **Split note:** this is part 3 of 11, extracted verbatim from the master plan `2026-07-14-gatekeeper-v6.md` (which stays as the reference copy; the checklist-to-task traceability appendix is in Part 11). Parts execute in numeric order.
> **Requires complete first:** Parts 1-2 complete (all their tasks checked off).
>
> Cross-part references (task numbers like G38, file names, `Interfaces:` blocks) refer to work done in earlier parts - those modules exist on the branch by the time this part runs.

## Progress

> Updated by the executing session after each task batch. Resume from the first unchecked task.
>
> - **Branch:** `feature/gatekeeper-v6`
> - **Completed:** —
> - **Next:** Task G29

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

# Phase G1 — Macro data layer: news, sentiment, rotation, CPI/PPI, treasury (G9–G44)

Everything here is read-only market context. Each provider: 5s timeout, TTL disk cache, `None`-on-failure, no network in tests.


> *(Phase intro above repeated from the part where this phase begins - this part continues it with tasks G29-G44.)*

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
