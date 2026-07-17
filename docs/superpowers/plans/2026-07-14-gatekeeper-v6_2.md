# Gatekeeper v6 - Part 2/11: Macro data layer I: plumbing, FRED series, market internals (Tasks G9-G28)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute strictly in order (G9 -> G28).
>
> **Split note:** this is part 2 of 11, extracted verbatim from the master plan `2026-07-14-gatekeeper-v6.md` (which stays as the reference copy; the checklist-to-task traceability appendix is in Part 11). Parts execute in numeric order.
> **Requires complete first:** Parts 1-1 complete (all their tasks checked off).
>
> Cross-part references (task numbers like G38, file names, `Interfaces:` blocks) refer to work done in earlier parts - those modules exist on the branch by the time this part runs.

## Progress

> Updated by the executing session after each task batch. Resume from the first unchecked task.
>
> - **Branch:** `feature/gatekeeper-v6`
> - **Completed:** —
> - **Next:** Task G9

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
