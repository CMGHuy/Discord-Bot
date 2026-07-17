# Gatekeeper v6 - Part 9/11: Discord command suite (Tasks G147-G166)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute strictly in order (G147 -> G166).
>
> **Split note:** this is part 9 of 11, extracted verbatim from the master plan `2026-07-14-gatekeeper-v6.md` (which stays as the reference copy; the checklist-to-task traceability appendix is in Part 11). Parts execute in numeric order.
> **Requires complete first:** Parts 1-8 complete (all their tasks checked off).
>
> Cross-part references (task numbers like G38, file names, `Interfaces:` blocks) refer to work done in earlier parts - those modules exist on the branch by the time this part runs.

## Progress

> Updated by the executing session after each task batch. Resume from the first unchecked task.
>
> - **Branch:** `feature/gatekeeper-v6`
> - **Completed:** —
> - **Next:** Task G147

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

# Phase G5 — Discord command suite (G147–G166)

All commands render from the saved snapshot / stored artifacts — a command never triggers a provider fetch (except `!macro refresh`, explicitly). Renderers are pure string/embed builders in `swingbot/commands/macro.py` and `gatecheck.py`, tested without a live bot. Every command: help-catalog + `COMMAND_USAGE` entries, empty-state message, slash bridge via the existing `Context.from_interaction` pattern.

### Task G147: `!macro` — the market context dashboard

**Files:** Create `swingbot/commands/macro.py` (registered in `bot_core.py` like other command modules); test `tests/test_commands_macro.py`

**Interfaces:** `!macro` — one embed from `load_snapshot()`: Inflation field (CPI/Core/PPI/PCE yoy + vs-target), Rates field (FF, 2y/10y, curve state), Risk field (VIX regime, credit, dollar, fear/greed), Rotation field (top-3/bottom-3 sectors), Events field (next high-impact + within-24h), News field (sentiment label + top-3 headlines), footer `built_at` + stale marker. `!macro refresh` → `ensure_fresh_snapshot(ttl_min=0)` in a thread, then renders (admin-style confirm). Empty state: "Macro layer off or no snapshot yet — set MACRO_ENABLED and FRED_API_KEY." The pure builder is `build_macro_embed(snap) -> discord.Embed | None` (None on empty state); the command is a thin async shell. **This task also sets the phase's test conventions:** a shared `FakeCtx` (captures `.send(...)` kwargs) and a full fixture snapshot in `tests/fixtures/gate/snapshots.py` (`full_snapshot()` — reused by every G5 command test).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_commands_macro.py
"""Phase-G5 command tests: pure embed/table builders + thin command shells
driven through FakeCtx. No live bot, no network — commands render from the
saved snapshot ONLY (the phase's contract)."""
import asyncio

import swingbot.commands.macro as macro
import swingbot.config as config
from tests.fixtures.gate.snapshots import full_snapshot


class FakeCtx:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kw):
        self.sent.append((content, kw))


def test_macro_embed_golden():
    embed = macro.build_macro_embed(full_snapshot())
    names = [f.name for f in embed.fields]
    assert names == ["📈 Inflation", "🏦 Rates", "⚖️ Risk",
                     "🔄 Rotation", "📅 Events", "📰 News"]
    inflation = embed.fields[0].value
    assert "CPI 3.1%" in inflation and "Core PCE 2.6%" in inflation
    assert "vs 2% target" in inflation
    rates = embed.fields[1].value
    assert "FF 4.25" in rates and "10y" in rates and "normal" in rates
    assert "VIX 14.2 (calm)" in embed.fields[2].value
    assert embed.fields[3].value.startswith("Leaders: ")
    assert "CPI" in embed.fields[4].value
    assert embed.footer.text.startswith("Snapshot 2026-07-14")


def test_macro_embed_stale_marker():
    snap = full_snapshot()
    snap["stale"] = True
    embed = macro.build_macro_embed(snap)
    assert "STALE" in embed.footer.text


def test_macro_embed_none_snapshot_is_none():
    assert macro.build_macro_embed(None) is None


def test_macro_command_empty_state(monkeypatch):
    monkeypatch.setattr(macro, "_load_snapshot", lambda: None)
    ctx = FakeCtx()
    asyncio.run(macro.macro_cmd.callback(ctx))
    content, _ = ctx.sent[0]
    assert "MACRO_ENABLED" in content and "FRED_API_KEY" in content


def test_macro_refresh_rebuilds_once(monkeypatch):
    calls = {"n": 0}

    def fake_refresh(ttl_min=None):
        calls["n"] += 1
        return full_snapshot()

    monkeypatch.setattr(macro, "_ensure_fresh", fake_refresh)
    ctx = FakeCtx()
    asyncio.run(macro.macro_cmd.callback(ctx, "refresh"))
    assert calls["n"] == 1
    assert ctx.sent[-1][1].get("embed") is not None
```

And the shared fixture (create `tests/fixtures/gate/snapshots.py`):

```python
# tests/fixtures/gate/snapshots.py
"""One fully-populated G38-shaped snapshot for every command/page test.
Keys mirror snapshot.build_snapshot — when G38's shape changes, change it
HERE and every renderer test follows."""


def full_snapshot():
    return {
        "built_at": "2026-07-14T12:00:00", "stale": False,
        "inflation": {"cpi_yoy": 3.1, "core_cpi_yoy": 3.4, "ppi_yoy": 2.2,
                      "pce_yoy": 2.8, "core_pce_yoy": 2.6, "vs_target": 0.6},
        "labor": {"unemployment": 4.1, "payrolls_k": 180},
        "rates": {"fed_funds": 4.25, "y3m": 4.30, "y2": 3.9, "y10": 4.2,
                  "y30": 4.5, "curve_state": "normal"},
        "expectations": {"breakeven_5y": 2.3, "breakeven_10y": 2.4},
        "risk": {"vix": 14.2, "credit": "risk_on", "dollar": 104.2, "wti": 78.0},
        "vix": {"level": 14.2, "regime": "calm"},
        "curve": {"state": "normal", "spread_10y2y": 0.3, "spread_10y3m": -0.1},
        "composite": {"score": 67, "label": "risk_on", "inputs_used": 6, "detail": []},
        "fear_greed": {"score": 66, "label": "greed"},
        "sectors": {"leader": "Tech", "rotation": "risk_on", "rs_rows": [
            {"sector": "Technology", "etf": "XLK", "rank": 1,
             "rs_1m": 2.1, "rs_3m": 4.0, "rs_6m": 7.5},
            {"sector": "Utilities", "etf": "XLU", "rank": 11,
             "rs_1m": -1.8, "rs_3m": -3.2, "rs_6m": -5.0},
        ]},
        "breadth": {"pct_above_50dma": 62.0, "pct_above_200dma": 71.0, "n": 480},
        "events": {"refreshed_at": "2026-07-14T06:00:00",
                   "next_high_impact": {"name": "CPI", "importance": 3,
                                        "at": "2026-07-17T08:30:00"},
                   "within_24h": [], "today": [],
                   "upcoming": [{"name": "CPI", "importance": 3,
                                 "at": "2026-07-17T08:30:00"},
                                {"name": "OPEX", "importance": 2,
                                 "at": "2026-07-18T16:00:00"}]},
        "news": {"headlines_top5": [
                     {"title": "Chipmaker beats and raises guidance",
                      "score": 0.6, "kind": "confirmed"},
                     {"title": "Retailer said to weigh merger",
                      "score": 0.2, "kind": "rumor"}],
                 "sentiment": {"score": 0.22, "n": 25, "label": "positive"},
                 "rumor_ratio": 0.2},
        "quality_warnings": [],
    }
```

(Field values here must satisfy the goldens above; adjust the assertions and this fixture TOGETHER, never one side alone. Verify key names against the real `snapshot.py` before writing.)

- [ ] **Step 2: Run — FAIL**, then **implement**

```python
# swingbot/commands/macro.py
"""Market-context commands (G147-G152). Contract: a command NEVER triggers
a provider fetch — everything renders from the saved snapshot. The one
exception is `!macro refresh` (explicit, runs in a thread)."""
import asyncio
import logging

import discord
from discord.ext import commands

from swingbot import config

log = logging.getLogger(__name__)

EMPTY_STATE = ("Macro layer off or no snapshot yet — set MACRO_ENABLED "
               "and FRED_API_KEY, then `!macro refresh`.")


def _load_snapshot():
    from swingbot.core.macro.snapshot import load_snapshot
    return load_snapshot()


def _ensure_fresh(ttl_min=None):
    from swingbot.core.macro.snapshot import ensure_fresh_snapshot
    return ensure_fresh_snapshot(ttl_min=ttl_min)


def _fmt(v, suffix="", dash="—"):
    return dash if v is None else f"{v}{suffix}"


def build_macro_embed(snap: dict | None) -> discord.Embed | None:
    """The whole !macro dashboard as one pure builder. None-tolerant per
    section (a dead section renders as em-dashes, never a KeyError)."""
    if not snap:
        return None
    inf = snap.get("inflation") or {}
    rates = snap.get("rates") or {}
    risk = snap.get("risk") or {}
    vix = snap.get("vix") or {}
    fg = snap.get("fear_greed") or {}
    comp = snap.get("composite") or {}
    embed = discord.Embed(
        title="🌍 Market Context",
        description=f"Composite: **{comp.get('label', 'unknown')}** "
                    f"({comp.get('score', '—')})")
    embed.add_field(name="📈 Inflation", inline=False, value=(
        f"CPI {_fmt(inf.get('cpi_yoy'), '%')} · Core {_fmt(inf.get('core_cpi_yoy'), '%')} · "
        f"PPI {_fmt(inf.get('ppi_yoy'), '%')} · PCE {_fmt(inf.get('pce_yoy'), '%')} · "
        f"Core PCE {_fmt(inf.get('core_pce_yoy'), '%')} "
        f"({_fmt(inf.get('vs_target'), ' pts')} vs 2% target)"))
    embed.add_field(name="🏦 Rates", inline=False, value=(
        f"FF {_fmt(rates.get('fed_funds'))} · 2y {_fmt(rates.get('y2'))} · "
        f"10y {_fmt(rates.get('y10'))} · curve {rates.get('curve_state', '—')}"))
    embed.add_field(name="⚖️ Risk", inline=False, value=(
        f"VIX {_fmt(vix.get('level'))} ({vix.get('regime', '—')}) · "
        f"credit {risk.get('credit', '—')} · DXY {_fmt(risk.get('dollar'))} · "
        f"fear/greed {fg.get('label', '—')} ({_fmt(fg.get('score'))})"))
    rows = (snap.get("sectors") or {}).get("rs_rows") or []
    by_rank = sorted(rows, key=lambda r: r.get("rank", 99))
    leaders = ", ".join(r["sector"] for r in by_rank[:3])
    laggards = ", ".join(r["sector"] for r in by_rank[-3:]) if len(by_rank) > 3 else ""
    embed.add_field(name="🔄 Rotation", inline=False,
                    value=f"Leaders: {leaders or '—'}"
                          + (f" · Laggards: {laggards}" if laggards else ""))
    events = snap.get("events") or {}
    nxt = events.get("next_high_impact")
    ev_bits = [f"Next: {nxt['name']} {nxt['at'][:16]}" if nxt else "Next: —"]
    if events.get("within_24h"):
        ev_bits.append("⚠️ within 24h: "
                       + ", ".join(e["name"] for e in events["within_24h"]))
    embed.add_field(name="📅 Events", inline=False, value=" · ".join(ev_bits))
    news = snap.get("news") or {}
    sent = news.get("sentiment") or {}
    heads = "\n".join(f"• {h['title']}" for h in (news.get("headlines_top5") or [])[:3])
    embed.add_field(name="📰 News", inline=False,
                    value=f"Sentiment: {sent.get('label', '—')} "
                          f"({_fmt(sent.get('score'))})"
                          + (f"\n{heads}" if heads else ""))
    footer = f"Snapshot {str(snap.get('built_at', ''))[:16].replace('T', ' ')}"
    if snap.get("stale"):
        footer += " · STALE"
    embed.set_footer(text=footer)
    return embed


@commands.command(name="macro")
async def macro_cmd(ctx, arg: str = None):
    """!macro — market context dashboard · !macro refresh — force rebuild"""
    if arg == "refresh":
        snap = await asyncio.to_thread(_ensure_fresh, 0)
    else:
        snap = _load_snapshot()
    embed = build_macro_embed(snap)
    if embed is None:
        await ctx.send(EMPTY_STATE)
        return
    await ctx.send(embed=embed)


def setup_commands(bot):
    """Registered from bot_core like the other command modules — match the
    exact registration pattern (add_command vs cog) at execution."""
    bot.add_command(macro_cmd)
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_commands_macro.py -v`
- [ ] **Step 4: Full suite + commit** (register the module in `bot_core.py` alongside the existing command modules)

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/macro.py swingbot/bot_core.py tests/test_commands_macro.py tests/fixtures/gate/snapshots.py
git commit -m "feat: !macro dashboard"
```

### Task G148: `!calendar [days]`

**Files:** Modify `macro.py`; test `tests/test_commands_macro.py`

**Interfaces:** `!calendar [days=7]` — upcoming events table (date ET, kind emoji 🏛️ FOMC / 📈 CPI / 👷 NFP / 🏭 PPI / 💰 PCE / 🎯 OPEX / 🏖️ holiday, importance stars), blackout-window rows bolded with "entries held" note when `GATE_BLACKOUT_ENABLED` **and** `GATE_BLACKOUT_ENFORCE` (annotate-only mode says "annotated" instead — never claim a hold that won't happen); cap 20 rows. Pure builder `calendar_table(events, days, now, *, blackout_enforce) -> str`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_commands_macro.py`)

```python
import datetime as dt

NOW = dt.datetime(2026, 7, 14, 12, 0)


def test_calendar_table_golden():
    events = full_snapshot()["events"]["upcoming"]
    table = macro.calendar_table(events, days=7, now=NOW, blackout_enforce=False)
    lines = table.splitlines()
    assert lines[0] == "📈 Fri 07-17 08:30 ET · CPI ★★★"   # 2026-07-17 is a Friday
    assert lines[1] == "🎯 Sat 07-18 16:00 ET · OPEX ★★"


def test_calendar_blackout_row_marks_hold_only_when_enforcing():
    events = [{"name": "CPI", "importance": 3,
               "at": (NOW + dt.timedelta(hours=20)).isoformat()}]
    enforced = macro.calendar_table(events, 7, NOW, blackout_enforce=True)
    assert enforced.startswith("**") and "entries held" in enforced
    informed = macro.calendar_table(events, 7, NOW, blackout_enforce=False)
    assert "annotated" in informed and "held" not in informed


def test_calendar_caps_rows_and_respects_horizon():
    events = [{"name": f"E{i}", "importance": 1,
               "at": (NOW + dt.timedelta(days=1, minutes=i)).isoformat()}
              for i in range(30)]
    table = macro.calendar_table(events, days=7, now=NOW, blackout_enforce=False)
    assert len(table.splitlines()) == 20                    # cap
    far = [{"name": "FAR", "importance": 3,
            "at": (NOW + dt.timedelta(days=30)).isoformat()}]
    assert macro.calendar_table(far, days=7, now=NOW,
                                blackout_enforce=False) == ""
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `macro.py`)

```python
KIND_EMOJI = {"FOMC": "🏛️", "CPI": "📈", "NFP": "👷", "PPI": "🏭",
              "PCE": "💰", "OPEX": "🎯", "HOLIDAY": "🏖️"}


def _in_blackout(ev_at, now):
    before = float(getattr(config, "GATE_BLACKOUT_HOURS_BEFORE", 24.0))
    after = float(getattr(config, "GATE_BLACKOUT_HOURS_AFTER", 2.0))
    hours = (ev_at - now).total_seconds() / 3600.0
    return -after <= hours <= before


def calendar_table(events, days, now, *, blackout_enforce) -> str:
    """≤20 rows of upcoming events inside the horizon. Blackout-window
    high-impact rows are bolded — saying 'entries held' only when holding
    is actually enforced, 'annotated' otherwise (never promise a hold that
    inform mode won't perform)."""
    import datetime as dt
    rows = []
    horizon = now + dt.timedelta(days=days)
    for ev in sorted(events or [], key=lambda e: e.get("at", "")):
        try:
            at = dt.datetime.fromisoformat(ev["at"])
        except (KeyError, ValueError):
            continue
        if not (now <= at <= horizon):
            continue
        emoji = KIND_EMOJI.get(ev.get("name", "").upper(), "📌")
        stars = "★" * int(ev.get("importance", 1))
        line = f"{emoji} {at.strftime('%a %m-%d %H:%M')} ET · {ev['name']} {stars}"
        if int(ev.get("importance", 0)) >= 3 and \
                getattr(config, "GATE_BLACKOUT_ENABLED", False) and \
                _in_blackout(at, now):
            note = "entries held" if blackout_enforce else "annotated"
            line = f"**{line} — {note}**"
        rows.append(line)
        if len(rows) == 20:
            break
    return "\n".join(rows)


@commands.command(name="calendar")
async def calendar_cmd(ctx, days: int = 7):
    """!calendar [days] — upcoming economic events"""
    import datetime as dt
    snap = _load_snapshot()
    if not snap:
        await ctx.send(EMPTY_STATE)
        return
    table = calendar_table((snap.get("events") or {}).get("upcoming", []),
                           days, dt.datetime.now(),
                           blackout_enforce=getattr(
                               config, "GATE_BLACKOUT_ENFORCE", False))
    await ctx.send(embed=discord.Embed(
        title=f"📅 Next {days} days",
        description=table or "No events inside the horizon."))
```

(Test goldens assume `GATE_BLACKOUT_ENABLED=True` where bolding is asserted — set it via monkeypatch in that test, matching the `_flags` helper pattern.)

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_commands_macro.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/macro.py tests/test_commands_macro.py
git commit -m "feat: !calendar"
```

### Task G149: `!sectors`

**Files:** Modify `macro.py`; test `tests/test_commands_macro.py`

**Interfaces:** `!sectors` — rotation posture line + 11-row table (rank, sector, 1m/3m/6m RS vs SPY with ▲/▼), leaders/laggards summary; data from the snapshot's `sectors` section. Pure builder `sectors_table(sectors: dict) -> str`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_commands_macro.py`)

```python
def test_sectors_table_golden():
    table = macro.sectors_table(full_snapshot()["sectors"])
    lines = table.splitlines()
    assert lines[0] == "Rotation: risk_on"
    assert lines[1] == " 1. Technology    ▲+2.1  ▲+4.0  ▲+7.5"
    assert lines[2] == "11. Utilities     ▼-1.8  ▼-3.2  ▼-5.0"
    assert lines[-1].startswith("Leaders: Technology")


def test_sectors_table_empty_section():
    assert macro.sectors_table({}) == "No sector data in the snapshot yet."
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `macro.py`)

```python
def _rs(v):
    if v is None:
        return "   —  "
    return f"{'▲' if v >= 0 else '▼'}{v:+.1f}"


def sectors_table(sectors: dict) -> str:
    """Rotation posture + one row per sector ranked by composite RS.
    Monospace-ish alignment (sector padded to 14) — rendered inside a
    code block by the command."""
    rows = (sectors or {}).get("rs_rows") or []
    if not rows:
        return "No sector data in the snapshot yet."
    out = [f"Rotation: {sectors.get('rotation', 'unknown')}"]
    ranked = sorted(rows, key=lambda r: r.get("rank", 99))
    for r in ranked:
        out.append(f"{r.get('rank', '?'):>2}. {r.get('sector', '?'):<14}"
                   f"{_rs(r.get('rs_1m'))}  {_rs(r.get('rs_3m'))}  {_rs(r.get('rs_6m'))}")
    leaders = ", ".join(r["sector"] for r in ranked[:3])
    laggards = ", ".join(r["sector"] for r in ranked[-3:]) if len(ranked) > 3 else "—"
    out.append(f"Leaders: {leaders} · Laggards: {laggards}")
    return "\n".join(out)


@commands.command(name="sectors")
async def sectors_cmd(ctx):
    """!sectors — sector rotation vs SPY (1m/3m/6m)"""
    snap = _load_snapshot()
    if not snap:
        await ctx.send(EMPTY_STATE)
        return
    await ctx.send(embed=discord.Embed(
        title="🔄 Sector rotation",
        description=f"```\n{sectors_table(snap.get('sectors'))}\n```"))
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_commands_macro.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/macro.py tests/test_commands_macro.py
git commit -m "feat: !sectors rotation table"
```

### Task G150: `!sentiment`

**Files:** Modify `macro.py`; test `tests/test_commands_macro.py`

**Interfaces:** `!sentiment [ticker]` — market-wide: news sentiment score/label, rumor ratio, fear/greed gauge with the 5-band label; with ticker: company headlines (top 5, each with G36 score emoji and G37 rumor/confirmed tag). Ticker path reads the cached company-news (no fetch); cache miss → "no cached headlines — appears on the next scan". Pure builders `sentiment_overview(snap) -> str`, `ticker_headlines(headlines) -> str`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_commands_macro.py`)

```python
def test_sentiment_overview_golden():
    text = macro.sentiment_overview(full_snapshot())
    assert "News: positive (+0.22, N=25)" in text
    assert "Rumor ratio: 20%" in text
    assert "Fear/greed: greed (66)" in text


def test_ticker_headlines_golden():
    heads = [{"title": "Beats and raises", "score": 0.6, "kind": "confirmed"},
             {"title": "Said to weigh merger", "score": 0.2, "kind": "rumor"}]
    text = macro.ticker_headlines(heads)
    assert text.splitlines()[0] == "🟢 [confirmed] Beats and raises"
    assert text.splitlines()[1] == "⚪ [rumor] Said to weigh merger"


def test_sentiment_ticker_cache_miss(monkeypatch):
    monkeypatch.setattr(macro, "_cached_company_news", lambda t: None)
    monkeypatch.setattr(macro, "_load_snapshot", lambda: full_snapshot())
    ctx = FakeCtx()
    asyncio.run(macro.sentiment_cmd.callback(ctx, "NVDA"))
    content, _ = ctx.sent[0]
    assert "no cached headlines" in content
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `macro.py`)

```python
def _score_emoji(score):
    if score is None:
        return "⚪"
    return "🟢" if score > 0.15 else "🔴" if score < -0.15 else "⚪"


def sentiment_overview(snap: dict) -> str:
    news = (snap or {}).get("news") or {}
    sent = news.get("sentiment") or {}
    fg = (snap or {}).get("fear_greed") or {}
    parts = []
    if sent.get("label"):
        parts.append(f"News: {sent['label']} ({sent.get('score', 0):+.2f}, "
                     f"N={sent.get('n', 0)})")
    if news.get("rumor_ratio") is not None:
        parts.append(f"Rumor ratio: {news['rumor_ratio']:.0%}")
    if fg.get("label"):
        parts.append(f"Fear/greed: {fg['label']} ({fg.get('score', '—')})")
    return "\n".join(parts) or "No sentiment data in the snapshot yet."


def ticker_headlines(headlines: list) -> str:
    return "\n".join(
        f"{_score_emoji(h.get('score'))} [{h.get('kind', '?')}] {h.get('title', '')}"
        for h in (headlines or [])[:5])


def _cached_company_news(ticker: str) -> list | None:
    """Cache-only read of G35's company headlines — NEVER fetches.
    Verify the exact cache accessor in core/macro/company_news.py (G35)."""
    from swingbot.core.macro.company_news import cached_headlines
    return cached_headlines(ticker)


@commands.command(name="sentiment")
async def sentiment_cmd(ctx, ticker: str = None):
    """!sentiment [ticker] — market or company news sentiment"""
    snap = _load_snapshot()
    if not snap:
        await ctx.send(EMPTY_STATE)
        return
    if ticker:
        heads = _cached_company_news(ticker.upper())
        if not heads:
            await ctx.send(f"{ticker.upper()}: no cached headlines — "
                           f"appears on the next scan.")
            return
        await ctx.send(embed=discord.Embed(
            title=f"📰 {ticker.upper()} headlines",
            description=ticker_headlines(heads)))
        return
    await ctx.send(embed=discord.Embed(
        title="📰 Sentiment", description=sentiment_overview(snap)))
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_commands_macro.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/macro.py tests/test_commands_macro.py
git commit -m "feat: !sentiment"
```

### Task G151: `!yields`

**Files:** Modify `macro.py`; test `tests/test_commands_macro.py`

**Interfaces:** `!yields` — 3m/2y/10y/30y rows with daily change arrows, both curve spreads, curve state with the plain-English line ("10y−2y negative: historically a caution flag, not a timing signal"), breakevens. Pure builder `yields_text(snap) -> str`. Daily changes come from the previous `snapshot_history.jsonl` row when available (injected as `prev`), else no arrows.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_commands_macro.py`)

```python
def test_yields_text_golden():
    snap = full_snapshot()
    prev = {"rates": {"y3m": 4.32, "y2": 3.85, "y10": 4.25, "y30": 4.5}}
    text = macro.yields_text(snap, prev=prev)
    lines = text.splitlines()
    assert lines[0] == "3m  4.30 ▼"
    assert lines[1] == "2y  3.90 ▲"
    assert lines[2] == "10y 4.20 ▼"
    assert lines[3] == "30y 4.50 ·"
    assert "10y−2y +0.30 · 10y−3m -0.10" in text
    assert "Curve: normal" in text
    assert "Breakevens: 5y 2.3 · 10y 2.4" in text


def test_yields_text_inverted_gets_the_honest_line():
    snap = full_snapshot()
    snap["curve"] = {"state": "inverted", "spread_10y2y": -0.4,
                     "spread_10y3m": -0.8}
    text = macro.yields_text(snap, prev=None)
    assert "caution flag, not a timing signal" in text


def test_yields_text_missing_rates_section():
    assert "No rates data" in macro.yields_text({}, prev=None)
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `macro.py`)

```python
def _arrow(cur, prev_v):
    if cur is None or prev_v is None:
        return "·"
    return "▲" if cur > prev_v else "▼" if cur < prev_v else "·"


def yields_text(snap: dict, prev: dict | None = None) -> str:
    rates = (snap or {}).get("rates") or {}
    if not rates:
        return "No rates data in the snapshot yet."
    prev_rates = (prev or {}).get("rates") or {}
    out = []
    for label, key in (("3m", "y3m"), ("2y", "y2"), ("10y", "y10"), ("30y", "y30")):
        v = rates.get(key)
        out.append(f"{label:<3} {v:.2f} {_arrow(v, prev_rates.get(key))}"
                   if v is not None else f"{label:<3} —")
    curve = (snap or {}).get("curve") or {}
    s2, s3 = curve.get("spread_10y2y"), curve.get("spread_10y3m")
    if s2 is not None or s3 is not None:
        out.append(f"10y−2y {s2:+.2f} · 10y−3m {s3:+.2f}")
    state = curve.get("state") or rates.get("curve_state")
    if state:
        line = f"Curve: {state}"
        if state == "inverted":
            line += (" — 10y−2y negative: historically a caution flag, "
                     "not a timing signal")
        out.append(line)
    exp = (snap or {}).get("expectations") or {}
    if exp.get("breakeven_5y") is not None:
        out.append(f"Breakevens: 5y {exp['breakeven_5y']} · "
                   f"10y {exp.get('breakeven_10y', '—')}")
    return "\n".join(out)


def _prev_history_row():
    """Second-newest line of snapshot_history.jsonl, for daily-change
    arrows. Any problem → None (arrows degrade to '·')."""
    import json
    import os
    from swingbot.core.macro import snapshot as snap_mod
    try:
        with open(snap_mod.HISTORY_PATH, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        return json.loads(lines[-2]) if len(lines) >= 2 else None
    except (OSError, ValueError, IndexError):
        return None


@commands.command(name="yields")
async def yields_cmd(ctx):
    """!yields — treasury yields, curve spreads, breakevens"""
    snap = _load_snapshot()
    if not snap:
        await ctx.send(EMPTY_STATE)
        return
    await ctx.send(embed=discord.Embed(
        title="🏦 Yields & curve",
        description=f"```\n{yields_text(snap, prev=_prev_history_row())}\n```"))
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_commands_macro.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/macro.py tests/test_commands_macro.py
git commit -m "feat: !yields"
```

### Task G152: `!inflation`

**Files:** Modify `macro.py`; test `tests/test_commands_macro.py`

**Interfaces:** `!inflation` — CPI/Core CPI/PPI/PCE/Core PCE yoy + m/m, direction arrows vs prior print, core-PCE-vs-2%-target gap line, next CPI/PPI/PCE print dates from the calendar. Pure builder `inflation_text(snap, prev=None) -> str` (m/m + prior-print arrows render only when the snapshot carries them — G13/G15 store `*_mom` and `*_prev` keys; verify against `snapshot.py`).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_commands_macro.py`)

```python
def test_inflation_text_golden():
    text = macro.inflation_text(full_snapshot())
    lines = text.splitlines()
    assert lines[0] == "CPI       3.1% yoy"
    assert "Core PCE  2.6% yoy" in text
    assert "Core PCE vs 2% target: +0.6 pts" in text
    assert "Next prints: CPI 07-17" in text


def test_inflation_text_no_inflation_section():
    assert "No inflation data" in macro.inflation_text({})
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `macro.py`)

```python
def inflation_text(snap: dict, prev: dict | None = None) -> str:
    inf = (snap or {}).get("inflation") or {}
    if not inf:
        return "No inflation data in the snapshot yet."
    prev_inf = (prev or {}).get("inflation") or {}
    out = []
    for label, key in (("CPI", "cpi_yoy"), ("Core CPI", "core_cpi_yoy"),
                       ("PPI", "ppi_yoy"), ("PCE", "pce_yoy"),
                       ("Core PCE", "core_pce_yoy")):
        v = inf.get(key)
        if v is None:
            continue
        line = f"{label:<9} {v}% yoy"
        mom = inf.get(key.replace("_yoy", "_mom"))
        if mom is not None:
            line += f" · {mom:+.1f}% m/m"
        arrow = _arrow(v, prev_inf.get(key))
        if arrow != "·":
            line += f" {arrow}"
        out.append(line)
    if inf.get("vs_target") is not None:
        out.append(f"Core PCE vs 2% target: {inf['vs_target']:+.1f} pts")
    nxt = [f"{e['name']} {e['at'][5:10]}"
           for e in ((snap or {}).get("events") or {}).get("upcoming", [])
           if e.get("name") in ("CPI", "PPI", "PCE")]
    if nxt:
        out.append("Next prints: " + " · ".join(nxt))
    return "\n".join(out)


@commands.command(name="inflation")
async def inflation_cmd(ctx):
    """!inflation — inflation dashboard"""
    snap = _load_snapshot()
    if not snap:
        await ctx.send(EMPTY_STATE)
        return
    await ctx.send(embed=discord.Embed(
        title="📈 Inflation",
        description=f"```\n{inflation_text(snap, prev=_prev_history_row())}\n```"))
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_commands_macro.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/macro.py tests/test_commands_macro.py
git commit -m "feat: !inflation"
```

### Task G153: `!checklist <TICKER>` — on-demand full run

**Files:** Modify `swingbot/commands/gatecheck.py`; test `tests/test_commands_gatecheck.py`

**Interfaces:** `!checklist NVDA [strategy]` — runs `run_checklist` on demand against cached bars + current snapshot (in a thread; strategy defaults to the best-scoring applicable one, stated in the output); renders the G82 field + `full_breakdown` chunks. No plan required — this is the manual pre-trade ritual for trades the operator is eyeing personally. Unknown ticker / no cached bars → helpful error. Pure core: `checklist_on_demand(ticker, strategy, df, snap, now) -> tuple[GateResult, str]` (result, "strategy line"); the command shell threads + renders.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_commands_gatecheck.py additions (module exists since G113)
import asyncio
import datetime as dt

import swingbot.commands.gatecheck as gatecheck
from tests.fixtures.gate import uptrend_daily
from tests.fixtures.gate.snapshots import full_snapshot


class FakeCtx:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kw):
        self.sent.append((content, kw))


def test_checklist_on_demand_picks_best_strategy(monkeypatch):
    df = uptrend_daily(n=300)
    result, line = gatecheck.checklist_on_demand(
        "NVDA", None, df, full_snapshot(), now=dt.datetime(2026, 7, 14, 18, 0))
    assert result.ticker == "NVDA"
    assert line.startswith("Strategy: ") and "(best-scoring applicable)" in line


def test_checklist_on_demand_explicit_strategy(monkeypatch):
    df = uptrend_daily(n=300)
    result, line = gatecheck.checklist_on_demand(
        "NVDA", "RSI-Div", df, full_snapshot(), now=dt.datetime(2026, 7, 14, 18, 0))
    assert result.strategy == "RSI-Div" and "(requested)" in line


def test_checklist_command_no_bars(monkeypatch):
    monkeypatch.setattr(gatecheck, "_cached_daily", lambda t: None)
    ctx = FakeCtx()
    asyncio.run(gatecheck.checklist_cmd.callback(ctx, "ZZZZ"))
    content, _ = ctx.sent[0]
    assert "no cached bars" in content.lower()
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `gatecheck.py`)

```python
def _cached_daily(ticker: str):
    """Cache-only daily bars — the same loader the scan uses; never a
    network fetch. Verify the accessor name (G119 used load_cached_daily)."""
    from swingbot.core.data import load_cached_daily
    return load_cached_daily(ticker)


def _synthetic_plan(ticker, strategy, df):
    """A minimal plan at the current price so risk/timing checks have
    something to evaluate — the embed states this is a dry run. Mirrors
    the plan attrs run_checklist reads; deliberately NOT imported from
    tests/fixtures (production code never imports tests/)."""
    import types
    price = float(df["Close"].iloc[-1])
    atr = float((df["High"] - df["Low"]).tail(14).mean())
    return types.SimpleNamespace(
        ticker=ticker, strategy=strategy, direction="long",
        plan_id=f"dryrun_{ticker}", created_at=str(df.index[-1].date()),
        entry=price, trigger_price=price, stop_loss=price - 1.5 * atr,
        take_profit=price + 3.0 * atr)   # match TradePlanV2 attr names at execution


def checklist_on_demand(ticker, strategy, df, snap, now):
    """G153 core: run the full checklist against cached bars. strategy
    None → evaluate every applicable strategy and keep the best-scoring
    result (stated in the returned line — never silently chosen)."""
    from swingbot.core.gate import run_checklist
    from swingbot.core.gate.registry import applicable_strategies
    if strategy:
        result = run_checklist(ticker, strategy, _synthetic_plan(ticker, strategy, df),
                               df, macro_snap=snap, now=now)
        return result, f"Strategy: {strategy} (requested)"
    best = None
    for strat in applicable_strategies():
        r = run_checklist(ticker, strat, _synthetic_plan(ticker, strat, df),
                          df, macro_snap=snap, now=now)
        if best is None or r.score > best.score:
            best = r
    return best, f"Strategy: {best.strategy} (best-scoring applicable)"


@commands.command(name="checklist")
async def checklist_cmd(ctx, ticker: str, strategy: str = None):
    """!checklist <TICKER> [strategy] — the manual pre-trade ritual"""
    import asyncio as _asyncio
    import datetime as dt
    from swingbot.core.gate.render import checklist_field, full_breakdown
    ticker = ticker.upper()
    df = _cached_daily(ticker)
    if df is None or len(df) < 60:
        await ctx.send(f"{ticker}: no cached bars — run a scan first or "
                       f"check the ticker spelling.")
        return
    snap = _load_snapshot()
    result, strat_line = await _asyncio.to_thread(
        checklist_on_demand, ticker, strategy, df, snap, dt.datetime.now())
    name, value = checklist_field(result)
    embed = discord.Embed(title=f"📋 {ticker} — dry run", description=strat_line)
    embed.add_field(name=name, value=value, inline=False)
    await ctx.send(embed=embed)
    for chunk in full_breakdown(result):
        await ctx.send(f"```\n{chunk}\n```")
```

(`applicable_strategies()` = the registry-side list of strategies with at least one applicable check — if G80 named it differently, use that name; `_load_snapshot` imported from `swingbot.commands.macro`.)

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_commands_gatecheck.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/gatecheck.py tests/test_commands_gatecheck.py
git commit -m "feat: !checklist on-demand"
```

### Task G154: `!whycheck <plan_id>`

**Files:** Modify `gatecheck.py`; test `tests/test_commands_gatecheck.py`

**Interfaces:** `!whycheck p_20260714_ab12` — replays the **stored** GateResult from the plan record (never re-evaluates): every check, status, evidence line, plus the macro-at-entry stamp and (if closed) the outcome next to it — the post-mortem view. Missing gate data → "plan pre-dates the gate". Pure builder `whycheck_text(plan_record) -> str`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_commands_gatecheck.py`)

```python
STORED_PLAN = {
    "plan_id": "p_20260714_ab12", "ticker": "NVDA", "strategy": "RSI-Div",
    "status": "closed", "outcome": {"result": "win", "r_multiple": 2.1},
    "gate": {"tier": "B", "score": 61.0, "as_of": "2026-07-14",
             "hard_blocks": [], "advisory_decision": "downgrade",
             "checks": [
                 {"check_id": "htf_alignment", "section": "context",
                  "status": "pass", "weight": 12.0,
                  "evidence": "weekly uptrend, daily agrees"},
                 {"check_id": "rf_fake_breakout", "section": "redflags",
                  "status": "warn", "weight": 10.0,
                  "evidence": "closed back inside on 0.6x volume"}]},
    "macro_at_entry": {"composite": {"label": "risk_on", "score": 67}},
}


def test_whycheck_text_golden():
    text = gatecheck.whycheck_text(STORED_PLAN)
    assert "NVDA · RSI-Div · tier B (61) · 2026-07-14" in text
    assert "✅ htf_alignment — weekly uptrend, daily agrees" in text
    assert "⚠️ rf_fake_breakout — closed back inside on 0.6x volume" in text
    assert "Macro at entry: risk_on (67)" in text
    assert "Outcome: win (+2.1R)" in text          # the post-mortem line


def test_whycheck_text_pre_gate_plan():
    assert "pre-dates the gate" in gatecheck.whycheck_text(
        {"plan_id": "p_old", "ticker": "AAPL"})


def test_whycheck_command_unknown_plan(monkeypatch):
    monkeypatch.setattr(gatecheck, "_load_plan_record", lambda pid: None)
    ctx = FakeCtx()
    asyncio.run(gatecheck.whycheck_cmd.callback(ctx, "p_nope"))
    assert "not found" in ctx.sent[0][0].lower()
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `gatecheck.py`)

```python
_STATUS_EMOJI = {"pass": "✅", "warn": "⚠️", "fail": "⛔", "unknown": "◻️"}


def _load_plan_record(plan_id: str) -> dict | None:
    from swingbot.core.plan_store import PlanStore
    return PlanStore().get(plan_id)     # match the store's accessor at execution


def whycheck_text(plan_record: dict | None) -> str:
    """G154: the stored verdict, replayed verbatim — this function NEVER
    calls run_checklist (the whole point is what the gate said THEN)."""
    if not plan_record:
        return "Plan not found."
    gate = plan_record.get("gate")
    if not gate:
        return (f"{plan_record.get('ticker', '?')}: plan pre-dates the gate — "
                f"no stored verdict.")
    out = [f"{plan_record.get('ticker')} · {plan_record.get('strategy')} · "
           f"tier {gate['tier']} ({gate['score']:.0f}) · {gate.get('as_of', '')}"]
    for c in gate.get("checks", []):
        emoji = _STATUS_EMOJI.get(c.get("status"), "◻️")
        out.append(f"{emoji} {c['check_id']} — {c.get('evidence', '')}")
    macro = plan_record.get("macro_at_entry") or {}
    comp = macro.get("composite") or {}
    if comp:
        out.append(f"Macro at entry: {comp.get('label')} ({comp.get('score')})")
    outcome = plan_record.get("outcome") or {}
    if outcome:
        r = outcome.get("r_multiple")
        out.append(f"Outcome: {outcome.get('result')}"
                   + (f" ({r:+.1f}R)" if r is not None else ""))
    return "\n".join(out)


@commands.command(name="whycheck")
async def whycheck_cmd(ctx, plan_id: str):
    """!whycheck <plan_id> — the stored checklist verdict, post-mortem view"""
    record = _load_plan_record(plan_id)
    if record is None:
        await ctx.send(f"Plan `{plan_id}` not found.")
        return
    text = whycheck_text(record)
    for i in range(0, len(text), 1900):                # Discord 2000-char guard
        await ctx.send(f"```\n{text[i:i + 1900]}\n```")
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_commands_gatecheck.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/gatecheck.py tests/test_commands_gatecheck.py
git commit -m "feat: !whycheck stored-verdict replay"
```

### Task G155: `!blocked [date]`

**Files:** Modify `gatecheck.py`; test `tests/test_commands_gatecheck.py`

**Interfaces:** `!blocked [YYYY-MM-DD|today]` — reads `blocked.jsonl`: table of blocked/downgraded/held candidates (ticker, strategy, tier, reason chain), so nothing is ever silently suppressed (Global Constraint made visible). Footer: count + "blocked ≠ deleted; see !whycheck". Pure builder `blocked_table(rows, date) -> str`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_commands_gatecheck.py`)

```python
BLOCKED_ROWS = [
    {"at": "2026-07-14T15:00:00", "ticker": "XYZ", "strategy": "Breakout",
     "tier": "C", "decision": "block", "reason": "rf_fake_breakout"},
    {"at": "2026-07-14T15:05:00", "ticker": "ABC", "strategy": "RSI-Div",
     "tier": "B", "decision": "downgrade", "reason": "tier B < A"},
    {"at": "2026-07-13T15:00:00", "ticker": "OLD", "strategy": "Breakout",
     "tier": "C", "decision": "block", "reason": "rf_stop_sweep"},
]


def test_blocked_table_filters_by_date():
    import datetime as dt
    table = gatecheck.blocked_table(BLOCKED_ROWS, dt.date(2026, 7, 14))
    lines = table.splitlines()
    assert len(lines) == 3                          # 2 rows + footer
    assert "XYZ  Breakout  C  block      rf_fake_breakout" in lines[0]
    assert "ABC  RSI-Div   B  downgrade  tier B < A" in lines[1]
    assert lines[-1] == "2 entries · blocked ≠ deleted; see !whycheck"


def test_blocked_table_empty_day():
    import datetime as dt
    assert "Nothing blocked" in gatecheck.blocked_table(
        BLOCKED_ROWS, dt.date(2026, 7, 12))
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `gatecheck.py`)

```python
def _read_blocked_rows() -> list[dict]:
    import json
    from swingbot.core.gate import persistence
    try:
        with open(persistence.BLOCKED_PATH, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except (OSError, ValueError):
        return []


def blocked_table(rows: list[dict], date) -> str:
    """G155: every held-back candidate for the day, visible. Column
    widths fixed so the code-block renders as a table."""
    day = [r for r in rows if r.get("at", "").startswith(date.isoformat())]
    if not day:
        return (f"Nothing blocked, downgraded or held on {date.isoformat()} "
                f"— in inform mode that is every day.")
    out = [f"{r.get('ticker', '?'):<4} {r.get('strategy', '?'):<9} "
           f"{r.get('tier', '?'):<2} {r.get('decision', '?'):<10} {r.get('reason', '')}"
           for r in day]
    out.append(f"{len(day)} entries · blocked ≠ deleted; see !whycheck")
    return "\n".join(out)


@commands.command(name="blocked")
async def blocked_cmd(ctx, date_arg: str = "today"):
    """!blocked [YYYY-MM-DD|today] — everything the gate held back"""
    import datetime as dt
    date = dt.date.today() if date_arg == "today" \
        else dt.date.fromisoformat(date_arg)
    await ctx.send(f"```\n{blocked_table(_read_blocked_rows(), date)}\n```")
```

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_commands_gatecheck.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/gatecheck.py tests/test_commands_gatecheck.py
git commit -m "feat: !blocked transparency command"
```

### Task G156: `!gutcheck`

**Files:** Modify `gatecheck.py`; test `tests/test_commands_gatecheck.py`

**Interfaces:** `!gutcheck` — pending gut-checks (alerts awaiting the ritual, with age), plus G126's stats (WR with vs without ritual, the "took it anyway" cohort). The self-accountability mirror. Pure builder `gutcheck_text(pending, stats) -> str` (`pending` = open plans lacking a `gutcheck` key; `stats` = G126's `gutcheck_stats` output).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_commands_gatecheck.py`)

```python
def test_gutcheck_text_golden():
    pending = [{"plan_id": "p_1", "ticker": "NVDA", "age_hours": 3.5}]
    stats = {"with_gutcheck": {"n": 24, "wr": 71.0},
             "without_gutcheck": {"n": 18, "wr": 55.0},
             "took_anyway": {"n": 5, "wr": 40.0}}
    text = gatecheck.gutcheck_text(pending, stats)
    assert "Pending (1):" in text and "NVDA (3.5h)" in text
    assert "With ritual: 71% (N=24)" in text
    # the G109 low-N guard applies here too — small cohorts never print a %
    assert "Without: — (N=18 < 20)" in text
    assert '"Would not take after a loss, took anyway": — (N=5 < 20)' in text


def test_gutcheck_text_low_n_guarded():
    stats = {"with_gutcheck": {"n": 3, "wr": 100.0},
             "without_gutcheck": {"n": 0, "wr": None},
             "took_anyway": {"n": 0, "wr": None}}
    text = gatecheck.gutcheck_text([], stats)
    assert "— (N=3 < 20)" in text                   # fmt_wr guard applies here too
    assert "Nothing pending" in text
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `gatecheck.py`)

```python
def gutcheck_text(pending: list[dict], stats: dict) -> str:
    """G156: the self-accountability mirror. Every WR through fmt_wr —
    a 3-trade '100%' must render as the small sample it is (G109)."""
    from swingbot.core.gate.render import fmt_wr
    out = []
    if pending:
        names = ", ".join(f"{p['ticker']} ({p['age_hours']:.1f}h)"
                          for p in pending)
        out.append(f"Pending ({len(pending)}): {names}")
    else:
        out.append("Nothing pending — every live alert has had its ritual.")
    w, wo = stats.get("with_gutcheck", {}), stats.get("without_gutcheck", {})
    ta = stats.get("took_anyway", {})
    out.append(f"With ritual: {fmt_wr(w.get('wr'), w.get('n', 0))}")
    out.append(f"Without: {fmt_wr(wo.get('wr'), wo.get('n', 0))}")
    out.append(f'"Would not take after a loss, took anyway": '
               f"{fmt_wr(ta.get('wr'), ta.get('n', 0))}")
    return "\n".join(out)


@commands.command(name="gutcheck")
async def gutcheck_cmd(ctx):
    """!gutcheck — pending rituals + does the ritual pay?"""
    from swingbot.core.gate.persistence import gutcheck_stats
    pending = _pending_gutchecks()      # open plans lacking a gutcheck key,
                                        # age from created_at — reuse the
                                        # plan-store accessor G125 used
    stats = gutcheck_stats(_load_journal_entries())
    await ctx.send(embed=discord.Embed(title="🪞 Gut check",
                                       description=gutcheck_text(pending, stats)))
```

(`_pending_gutchecks()` and `_load_journal_entries()` are four-line helpers over `PlanStore.open_plans()` and the journal source G84 used — match those exact accessors at execution.)

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_commands_gatecheck.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/gatecheck.py tests/test_commands_gatecheck.py
git commit -m "feat: !gutcheck"
```

### Task G157: Slash-command bridges

**Files:** Modify `macro.py`, `gatecheck.py`; test `tests/test_commands_macro.py`

**Interfaces:** `/macro /calendar /sectors /sentiment /yields /inflation /checklist /whycheck /blocked /gutcheck /frontier /tierwr /redflags` via the repo's existing bridge pattern in `swingbot/commands/slash.py`: `ctx = await commands.Context.from_interaction(interaction)` then `await <prefix_cmd>.callback(ctx, *args)` (this is exactly how `slash_check` bridges today — copy that shape).

- [ ] **Step 1: Write the failing test** (append to `tests/test_commands_macro.py`)

```python
def test_every_new_command_has_a_slash_bridge():
    """Structural: slash.py defines a bridge for each new command. The
    bridge bodies are three-liners over Context.from_interaction — the
    smoke here is existence + naming, the behavior is the prefix
    command's own tests."""
    import inspect
    import swingbot.commands.slash as slash
    for name in ("macro", "calendar", "sectors", "sentiment", "yields",
                 "inflation", "checklist", "whycheck", "blocked",
                 "gutcheck", "frontier", "tierwr", "redflags"):
        fn = getattr(slash, f"slash_{name}", None)
        assert fn is not None, f"slash_{name} missing"
        assert "from_interaction" in inspect.getsource(fn)
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `swingbot/commands/slash.py`, one per command — the `!macro` example verbatim, the rest identical in shape):

```python
@bot.tree.command(name="macro", description="Market context dashboard")
async def slash_macro(interaction: discord.Interaction):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.macro import macro_cmd
    await macro_cmd.callback(ctx)


@bot.tree.command(name="checklist", description="Run the pre-trade checklist")
@app_commands.describe(ticker="Ticker symbol", strategy="Optional strategy name")
async def slash_checklist(interaction: discord.Interaction,
                          ticker: str, strategy: str = None):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.gatecheck import checklist_cmd
    await checklist_cmd.callback(ctx, ticker, strategy)
```

(Commands with arguments — `/calendar days`, `/sentiment ticker`, `/whycheck plan_id`, `/blocked date` — declare them via `app_commands.describe` exactly like `slash_checklist` above. Match the registration style of the existing `slash.py` functions, including where `bot` comes from.)

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_commands_macro.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/slash.py tests/test_commands_macro.py
git commit -m "feat: slash bridges for macro+gate commands"
```

### Task G158: Help catalog + usage sweep

**Files:** Modify `swingbot/commands/info.py` (`commands_cmd`) + `swingbot/commands/slash.py` (`slash_help`); test `tests/test_commands_macro.py`

> **Execution note:** the repo has no `COMMAND_USAGE` catalog structure — `!help` text is inline in `info.py:commands_cmd` and `slash.py:slash_help`. If a catalog structure has appeared by execution time (cockpit), register entries there instead; otherwise extend the inline help as below.

- [ ] **Step 1: Write the failing test** (append to `tests/test_commands_macro.py`)

```python
def _flatten_sent(ctx):
    """Everything the command sent — content strings + embed dicts —
    as one searchable string."""
    parts = []
    for content, kw in ctx.sent:
        if content:
            parts.append(content)
        if kw.get("embed") is not None:
            parts.append(str(kw["embed"].to_dict()))
    return " ".join(parts)


def test_help_lists_every_new_command():
    import swingbot.commands.info as info
    ctx = FakeCtx()
    asyncio.run(info.commands_cmd.callback(ctx))
    rendered = _flatten_sent(ctx)
    for cmd in ("!macro", "!calendar", "!sectors", "!sentiment", "!yields",
                "!inflation", "!checklist", "!whycheck", "!blocked",
                "!gutcheck", "!frontier", "!tierwr", "!redflags"):
        assert cmd in rendered, f"{cmd} missing from !help"
    assert "Market Context" in rendered and "Gatekeeper" in rendered
```

- [ ] **Step 2: Run — FAIL**, then **implement**: add two sections to the help output in `info.py` —

```text
**Market Context**
!macro [refresh] · !calendar [days] · !sectors · !sentiment [ticker] · !yields · !inflation

**Gatekeeper**
!checklist <TICKER> [strategy] · !whycheck <plan_id> · !blocked [date] · !gutcheck · !frontier [strategy] · !tierwr · !redflags
```

— and mirror the same two sections in `slash_help`.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_commands_macro.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/info.py swingbot/commands/slash.py tests/test_commands_macro.py
git commit -m "feat: help catalog for macro+gate commands"
```

### Task G159: Macro dashboard chart

**Files:** Modify `swingbot/core/charts/gate_charts.py`; test `tests/test_gate_charts.py`

**Interfaces:** `macro_dashboard_chart(history_rows, path) -> str | None` — 4-panel PNG from `snapshot_history.jsonl`: composite risk score (30d line), VIX + regime bands, 10y−2y spread, fear/greed gauge history; attached by `!macro` when ≥ 7 history rows exist (None when fewer — no half-empty chart).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_gate_charts.py`)

```python
import os


def _history_rows(n=30):
    return [{"built_at": f"2026-06-{d:02d}T22:00:00",
             "composite_score": 40 + d, "vix": 13.0 + d / 10,
             "spread_10y2y": 0.1 + d / 100, "fear_greed": 50 + d}
            for d in range(1, n + 1)]   # keys per G38's history summary line — verify


def test_macro_dashboard_chart_renders(tmp_path):
    path = str(tmp_path / "macro.png")
    out = macro_dashboard_chart(_history_rows(30), path)
    assert out == path and os.path.getsize(path) > 0


def test_macro_dashboard_chart_needs_seven_rows(tmp_path):
    assert macro_dashboard_chart(_history_rows(5),
                                 str(tmp_path / "x.png")) is None


def test_macro_dashboard_chart_tolerates_gaps(tmp_path):
    rows = _history_rows(10)
    for r in rows[3:6]:
        r["vix"] = None                                 # provider gap days
    assert macro_dashboard_chart(rows, str(tmp_path / "g.png")) is not None
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `swingbot/core/charts/gate_charts.py`, following the module's existing style constants from G111)

```python
def macro_dashboard_chart(history_rows: list[dict], path: str) -> str | None:
    """G159: 4-panel macro trend PNG. < 7 rows → None (no chart beats a
    misleading two-point line). None values are masked, not interpolated."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not history_rows or len(history_rows) < 7:
        return None
    rows = history_rows[-30:]
    x = list(range(len(rows)))
    labels = [r.get("built_at", "")[5:10] for r in rows]

    def series(key):
        return [r.get(key) if r.get(key) is not None else float("nan")
                for r in rows]

    fig, axes = plt.subplots(4, 1, figsize=(8, 9), sharex=True)
    panels = [("Composite risk", "composite_score"),
              ("VIX", "vix"), ("10y−2y spread", "spread_10y2y"),
              ("Fear/greed", "fear_greed")]
    for ax, (title, key) in zip(axes, panels):
        ax.plot(x, series(key))
        ax.set_title(title, fontsize=9, loc="left")
        if key == "spread_10y2y":
            ax.axhline(0, linewidth=0.8, linestyle="--")
    axes[-1].set_xticks(x[::5])
    axes[-1].set_xticklabels(labels[::5], fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
```

**Wiring** (`!macro` in `macro.py`): after the embed builds, read the history rows (same loader `_prev_history_row` uses, full list), call the chart into a tempfile, attach via `discord.File` when non-None, delete after send — one added test in `test_commands_macro.py` monkeypatching the chart fn to a sentinel path and asserting `file=` was passed.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_charts.py tests/test_commands_macro.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/charts/gate_charts.py swingbot/commands/macro.py tests/test_gate_charts.py tests/test_commands_macro.py
git commit -m "feat: macro dashboard chart"
```

### Task G160: Sector rotation chart

**Files:** Modify `gate_charts.py`; test `tests/test_gate_charts.py`

**Interfaces:** `sector_rotation_chart(rs_rows, path) -> str | None` — horizontal bar chart, 1m RS bars with 3m markers overlaid, SPY zero-line, sector labels; attached by `!sectors`. Empty rows → None.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_gate_charts.py`)

```python
def test_sector_rotation_chart_renders(tmp_path):
    from tests.fixtures.gate.snapshots import full_snapshot
    path = str(tmp_path / "sectors.png")
    rows = full_snapshot()["sectors"]["rs_rows"]
    assert sector_rotation_chart(rows, path) == path
    assert os.path.getsize(path) > 0


def test_sector_rotation_chart_empty_rows(tmp_path):
    assert sector_rotation_chart([], str(tmp_path / "e.png")) is None
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `gate_charts.py`)

```python
def sector_rotation_chart(rs_rows: list[dict], path: str) -> str | None:
    """G160: horizontal 1m-RS bars (3m as diamond markers), zero line =
    SPY. Rows sorted by rank so the leader is on top."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not rs_rows:
        return None
    rows = sorted(rs_rows, key=lambda r: r.get("rank", 99), reverse=True)
    names = [r.get("sector", "?") for r in rows]
    rs1 = [r.get("rs_1m") or 0.0 for r in rows]
    rs3 = [r.get("rs_3m") or 0.0 for r in rows]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(names, rs1, label="1m RS")
    ax.plot(rs3, names, "D", markersize=5, linestyle="none", label="3m RS")
    ax.axvline(0, linewidth=0.8)
    ax.set_xlabel("RS vs SPY (%)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
```

**Wiring:** `!sectors` attaches it exactly as G159 wired `!macro` (tempfile + `discord.File` + cleanup).

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_charts.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/charts/gate_charts.py swingbot/commands/macro.py tests/test_gate_charts.py
git commit -m "feat: sector rotation chart"
```

### Task G161: Sentiment/news trend chart

**Files:** Modify `gate_charts.py`; test `tests/test_gate_charts.py`

**Interfaces:** `sentiment_trend_chart(history_rows, path) -> str | None` — daily aggregate news-sentiment line + fear/greed overlay (30d, twin y-axes); attached by `!sentiment` when ≥ 7 history rows carry sentiment.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_gate_charts.py`)

```python
def test_sentiment_trend_chart_renders(tmp_path):
    rows = [{"built_at": f"2026-06-{d:02d}T22:00:00",
             "news_sentiment": (d % 7 - 3) / 10, "fear_greed": 45 + d}
            for d in range(1, 31)]
    path = str(tmp_path / "sent.png")
    assert sentiment_trend_chart(rows, path) == path


def test_sentiment_trend_chart_insufficient(tmp_path):
    rows = [{"built_at": "2026-06-01", "news_sentiment": 0.1, "fear_greed": 50}]
    assert sentiment_trend_chart(rows, str(tmp_path / "n.png")) is None
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `gate_charts.py`)

```python
def sentiment_trend_chart(history_rows: list[dict], path: str) -> str | None:
    """G161: news sentiment (left axis, ±1) + fear/greed (right, 0-100)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [r for r in (history_rows or [])
            if r.get("news_sentiment") is not None][-30:]
    if len(rows) < 7:
        return None
    x = list(range(len(rows)))
    fig, ax1 = plt.subplots(figsize=(8, 4))
    ax1.plot(x, [r["news_sentiment"] for r in rows], label="news sentiment")
    ax1.set_ylim(-1, 1)
    ax1.axhline(0, linewidth=0.8, linestyle="--")
    ax2 = ax1.twinx()
    ax2.plot(x, [r.get("fear_greed") for r in rows], alpha=0.6,
             label="fear/greed")
    ax2.set_ylim(0, 100)
    fig.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
```

**Wiring:** `!sentiment` (market-wide path only) attaches it per the G159 pattern.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_charts.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/charts/gate_charts.py swingbot/commands/macro.py tests/test_gate_charts.py
git commit -m "feat: sentiment trend chart"
```

### Task G162: `!frontier`/`!tierwr` chart wiring

**Files:** Modify `gatecheck.py`; test `tests/test_commands_gatecheck.py`

**Interfaces:** `!frontier` attaches G111's chart (rendered on demand from the stored artifact to tmp, cleaned after send); `!tierwr` attaches the decile chart (G112). Chart render failure → embed still ships, log only. One shared helper owns the pattern: `_send_with_chart(ctx, embed, render_fn, *args)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_commands_gatecheck.py`)

```python
def test_send_with_chart_attaches_and_cleans(tmp_path, monkeypatch):
    made = {}

    def fake_render(rows, path):
        made["path"] = path
        with open(path, "wb") as fh:
            fh.write(b"png")
        return path

    ctx = FakeCtx()
    asyncio.run(gatecheck._send_with_chart(ctx, "EMBED", fake_render, [1, 2]))
    _, kw = ctx.sent[0]
    assert kw.get("embed") == "EMBED" and kw.get("file") is not None
    import os
    assert not os.path.exists(made["path"])            # tmp cleaned after send


def test_send_with_chart_survives_render_failure(caplog):
    def boom(rows, path):
        raise RuntimeError("matplotlib exploded")

    ctx = FakeCtx()
    asyncio.run(gatecheck._send_with_chart(ctx, "EMBED", boom, []))
    _, kw = ctx.sent[0]
    assert kw.get("embed") == "EMBED" and "file" not in kw   # embed still ships
    assert any("chart" in r.message.lower() for r in caplog.records)
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `gatecheck.py`)

```python
async def _send_with_chart(ctx, embed, render_fn, *args):
    """G162: best-effort chart attachment. Render to a tempfile, attach,
    always delete; ANY render failure → embed ships chartless + one log."""
    import os
    import tempfile
    path = os.path.join(tempfile.gettempdir(),
                        f"gate_chart_{os.getpid()}_{id(embed)}.png")
    chart = None
    try:
        chart = render_fn(*args, path)
    except Exception:  # noqa: BLE001
        log.warning("chart render failed — embed ships without it", exc_info=True)
    try:
        if chart:
            await ctx.send(embed=embed,
                           file=discord.File(chart, filename="chart.png"))
        else:
            await ctx.send(embed=embed)
    finally:
        if chart and os.path.exists(chart):
            os.remove(chart)
```

**Wiring:** `!frontier` calls `_send_with_chart(ctx, embed, frontier_chart, artifact["frontier"])` (chosen cut passed through); `!tierwr` calls it with `decile_chart` and the artifact's decile rows.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_commands_gatecheck.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/gatecheck.py tests/test_commands_gatecheck.py
git commit -m "feat: charts on frontier/tierwr"
```

### Task G163: Alert footer context one-liner

**Files:** Modify `embeds.py`; test `tests/test_embeds_gate.py`

**Interfaces:** when macro data exists but the full 🌍 field is off (`MACRO_ENABLED` on, `GATE_ENABLED` off), the alert footer gains the compact suffix `" · Risk-ON · CPI 3d"` (≤ 40 chars) — context even in minimal mode. Both off → byte-identical footer. Pure builder `footer_suffix(snap) -> str` in `gate/render.py`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_embeds_gate.py`)

```python
from swingbot.core.gate.render import footer_suffix


def test_footer_suffix_golden():
    assert footer_suffix(SNAP) == " · Risk-ON · CPI 3d"   # SNAP from G122's tests
    assert len(footer_suffix(SNAP)) <= 40


def test_footer_suffix_unknown_and_none():
    assert footer_suffix(None) == ""                       # both-off byte identity
    assert footer_suffix({"built_at": "t"}) == ""          # nothing to say → nothing
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `gate/render.py`)

```python
def footer_suffix(snap: dict | None) -> str:
    """G163: the 40-char minimal-mode context tail. Empty string whenever
    there is nothing meaningful to say — an empty suffix keeps the footer
    byte-identical, which IS the flags-off contract."""
    if not snap:
        return ""
    parts = []
    comp = snap.get("composite") or {}
    label = {"risk_on": "Risk-ON", "risk_off": "Risk-OFF",
             "neutral": "Risk-neutral"}.get(comp.get("label"))
    if label:
        parts.append(label)
    nxt = next((e for e in (snap.get("events") or {}).get("upcoming", [])
                if int(e.get("importance", 0)) >= 3), None)
    if nxt:
        try:
            import datetime as dt
            days = (dt.datetime.fromisoformat(nxt["at"]).date()
                    - dt.datetime.fromisoformat(snap["built_at"]).date()).days
            parts.append(f"{nxt['name']} {'today' if days <= 0 else f'{days}d'}")
        except (KeyError, ValueError):
            pass
    return (" · " + " · ".join(parts))[:40] if parts else ""
```

**Wiring** (`build_embed`, at the footer line): when `macro is not None and gate is None` (the minimal-mode combination — caller passes `gate=None` when `GATE_ENABLED` off), append `footer_suffix(macro)` to the existing footer text. Matrix test: (macro on, gate off) → suffix present; (both on) → NO suffix (the 🌍 field already carries it); (both off) → footer byte-identical.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_embeds_gate.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/gate/render.py swingbot/core/scanning/embeds.py tests/test_embeds_gate.py
git commit -m "feat: footer context one-liner"
```

### Task G164: Weekly digest macro section

**Files:** Modify the weekly digest builder; test `tests/test_gate_digest.py`

**Interfaces:** weekly digest gains "Market Week" (composite trend, biggest sector rotation move, events next week) + "Gate Week" (evaluated/blocked/tier mix, best/worst flag by outcome) sections, built from history + telemetry; absent data → sections omitted. Pure builders in `retrospective.py`: `market_week_section(history_rows, events) -> str | None`, `gate_week_section(telemetry_summary, flag_stats) -> str | None`.

> **Execution note:** the repo has no weekly digest builder today. If one has appeared by execution (cockpit), wire these sections into it; otherwise wire them into the **Friday** retrospective post (the week's last daily post — `daily_recap` already knows the weekday) with a `── Week in review ──` divider. Either way the builders below are the deliverable.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_gate_digest.py`)

```python
from swingbot.core.retrospective import gate_week_section, market_week_section


def test_market_week_section_golden():
    rows = [{"built_at": f"2026-07-{d:02d}", "composite_score": s}
            for d, s in ((7, 20), (8, 30), (9, 45), (10, 55), (11, 60))]
    events = [{"name": "FOMC", "importance": 3, "at": "2026-07-15T14:00:00"}]
    text = market_week_section(rows, events)
    assert "Composite 20 → 60 (improving)" in text
    assert "Next week: FOMC" in text


def test_market_week_section_absent_data():
    assert market_week_section([], []) is None


def test_gate_week_section_golden():
    summary = {"evaluated": 41, "blocked": 0, "downgraded": 3,
               "blocked_reasons": [], "held_for_event": 1, "recheck_held": 0}
    flags = [{"flag": "rf_fake_breakout", "delta_wr": 12.0, "n_fired_and_taken": 8},
             {"flag": "rf_opex_pin", "delta_wr": -2.0, "n_fired_and_taken": 5}]
    text = gate_week_section(summary, flags)
    assert "41 evaluated · 0 blocked · 3 downgraded · 1 held" in text
    assert "Best flag: rf_fake_breakout" in text
    assert "Worst: rf_opex_pin" in text


def test_gate_week_section_idle_week():
    assert gate_week_section({"evaluated": 0}, []) is None
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `retrospective.py`)

```python
def market_week_section(history_rows: list[dict], events: list[dict]) -> str | None:
    """G164 'Market Week': composite start→end + next week's headliners.
    None when there's no history — a digest never renders empty sections."""
    rows = [r for r in (history_rows or []) if r.get("composite_score") is not None]
    if len(rows) < 2:
        return None
    first, last = rows[0]["composite_score"], rows[-1]["composite_score"]
    trend = ("improving" if last > first + 5 else
             "deteriorating" if last < first - 5 else "flat")
    parts = [f"Composite {first:.0f} → {last:.0f} ({trend})"]
    nxt = [e["name"] for e in (events or []) if int(e.get("importance", 0)) >= 3]
    if nxt:
        parts.append("Next week: " + ", ".join(nxt[:3]))
    return " · ".join(parts)


def gate_week_section(telemetry_summary: dict, flag_stats: list[dict]) -> str | None:
    """G164 'Gate Week': the week's counts + the flag receipts extremes."""
    s = telemetry_summary or {}
    if not s.get("evaluated"):
        return None
    parts = [f"{s['evaluated']} evaluated · {s.get('blocked', 0)} blocked · "
             f"{s.get('downgraded', 0)} downgraded · "
             f"{s.get('held_for_event', 0)} held"]
    rated = [f for f in (flag_stats or []) if f.get("delta_wr") is not None]
    if rated:
        best = max(rated, key=lambda f: f["delta_wr"])
        worst = min(rated, key=lambda f: f["delta_wr"])
        parts.append(f"Best flag: {best['flag']} ({best['delta_wr']:+.0f} pts) · "
                     f"Worst: {worst['flag']} ({worst['delta_wr']:+.0f} pts)")
    return "\n".join(parts)
```

**Wiring:** in the Friday branch of the retrospective builder (or the digest builder if present): `market_week_section(history_rows_7d, upcoming_events)` + `gate_week_section(telemetry.summary(since=monday_iso), flag_outcome_stats(journal_entries))` — append each non-None with its header line.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_gate_digest.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/core/retrospective.py swingbot/commands/scanning.py tests/test_gate_digest.py
git commit -m "feat: digest macro + gate sections"
```

### Task G165: Command cooldowns + long-output guards

**Files:** Modify `macro.py`, `gatecheck.py`; test `tests/test_commands_macro.py`

**Interfaces:** per-user 10s cooldown on the render-heavy commands (`!macro`, `!sectors`, `!frontier`) via discord.py's own `@commands.cooldown(1, 10, commands.BucketType.user)` (the repo has no custom decorator — the library one is the standard tool); every table builder routes through `clamp(text, limit)` with an explicit truncation marker.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_commands_macro.py`)

```python
def test_render_heavy_commands_have_user_cooldowns():
    import swingbot.commands.gatecheck as gatecheck
    for cmd in (macro.macro_cmd, macro.sectors_cmd, gatecheck.frontier_cmd):
        buckets = cmd._buckets                     # discord.py CooldownMapping
        cd = buckets._cooldown
        assert cd is not None and cd.rate == 1 and cd.per == 10.0


def test_clamp_truncates_with_marker():
    text = "x" * 3000
    out = macro.clamp(text, 1024)
    assert len(out) <= 1024
    assert out.endswith("… [truncated]")
    assert macro.clamp("short", 1024) == "short"


def test_oversized_builders_stay_inside_discord_limits():
    """Field values ≤1024, descriptions ≤2000 (guarded at the builder)."""
    rows = [{"sector": f"Sector{i}", "etf": "XXX", "rank": i,
             "rs_1m": 1.0, "rs_3m": 1.0, "rs_6m": 1.0} for i in range(200)]
    out = macro.sectors_table({"rotation": "risk_on", "rs_rows": rows})
    assert len(macro.clamp(out, 1900)) <= 1900
```

- [ ] **Step 2: Run — FAIL**, then **implement** (append to `macro.py`; import into `gatecheck.py`)

```python
def clamp(text: str, limit: int) -> str:
    """G165: Discord-limit guard. Truncation is EXPLICIT — a cut table
    says so instead of silently eating rows."""
    marker = "… [truncated]"
    if len(text) <= limit:
        return text
    return text[:limit - len(marker)] + marker
```

And decorate the three commands (order matters — cooldown above the command decorator per discord.py convention):

```python
@commands.cooldown(1, 10, commands.BucketType.user)
@commands.command(name="macro")
async def macro_cmd(ctx, arg: str = None):
    ...
```

(Verify decorator stacking against a working discord.py example in the repo; if `@commands.command` must come first in this codebase's discord.py version, swap them — the test pins the effect, not the order.) Route every code-block send in `macro.py`/`gatecheck.py` through `clamp(..., 1900)` and every `add_field` value through `clamp(..., 1024)`.

- [ ] **Step 3: Run — PASS**: `python -m pytest tests/test_commands_macro.py tests/test_commands_gatecheck.py -v`
- [ ] **Step 4: Full suite + commit**

```bash
python -m pytest tests/ -q && make check
git add swingbot/commands/macro.py swingbot/commands/gatecheck.py tests/test_commands_macro.py
git commit -m "feat: cooldowns + output guards"
```

### Task G166: Phase G5 checkpoint

- [ ] **Step 1:** Full suite + `make check` green; manual smoke in a test channel: `!macro`, `!calendar`, `!sectors`, `!sentiment`, `!yields`, `!inflation`, `!checklist NVDA`, `!frontier` all render with real data (evidence screenshot/paste noted in the Progress block).
- [ ] **Step 2:** Update Progress block. Commit — `chore: phase G5 checkpoint`

---
