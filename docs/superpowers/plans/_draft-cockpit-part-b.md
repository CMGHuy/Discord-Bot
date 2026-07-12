# PART 2 (Plan B) — Discord Experience v3 (Tasks B1–B38)

**Goal:** Make the Discord surface answer one question at a glance — *which plan should I follow right now?* — via a unified embed design language keyed to tier/badge, `follow_score`-ranked alerts and boards, interactive buttons (chart / breakdown / watch / dismiss), new `!top` / `!stats` / `!lessons` / `!calibration` commands, richer plan charts (risk/reward bands, trigger arrows, trail paths, MFE/MAE markers), a daily Top-Plans digest, and chart-render caching so none of it slows the scan loop.

**Architecture:** A tiny theme module (`embed_theme.py`) centralizes colors/chips/ordering so every embed builder stops inventing its own; `analytics.rank.follow_score` (Plan A) is the only ranking authority; all interactivity uses discord.py `View`s following the existing `TradesPaginator` conventions (author-lock, timeout, disable-on-timeout); chart upgrades extend `generate_trade_chart` behind an optional `plan=` kwarg so legacy callers are untouched; a PNG cache keyed by content hash sits under `exports/chart_cache/`.

**Tech Stack:** discord.py 2.7.1 (`discord.ui.View/Button/Select`), matplotlib/mplfinance with the existing `chart_style.py` palette, pytest ≥8. **No new dependencies.**

**Prerequisites:** Plan-engine-v2 complete (badged embeds, `commands/plans.py` board, `PlanStore`/`PlanManager`); **Plan A merged** (`swingbot/core/analytics/*` — rank, metrics, snapshots, journal, insights).

## Notes on assumptions vs. the real codebase (read this before Task B1)

Verified directly against the repo on branch `feature/plan-engine-v2` (commits through "feat: shared trigger/fill/expiry/invalidation semantics"):

- `swingbot/core/plan_engine.py` **already exists** with exactly the field names this plan assumes: `TradePlanV2(plan_id, ticker, created_at, source, strategy, horizon_key, direction, entry_type, trigger_price, entry_price, expiry_bars, stop_loss, tp1, tp1_fraction, tp2, breakeven_trigger_fraction, trail_atr_mult, quality_score, quality_breakdown, tier, badge, badge_stats, status, status_history)`, `PlanStatus.{PENDING,ACTIVE,PARTIAL,CLOSED,CANCELLED}`, `record_transition(plan, new_status, reason, at)`, `stamp_badge(plan)`, `badge_stats_line(badge)`, `WEAK_CAUTION_TEXT`. Every task below that touches a `TradePlanV2` uses these exact names — no deviation needed.
- `swingbot/core/plan_store.py`, `swingbot/core/plan_manager.py`, `swingbot/core/quality.py`, and `swingbot/commands/plans.py` **do not exist yet** on this branch — they are later tasks in the still-in-progress plan-engine-v2 track (only ~15 of 110 tasks landed as of this writing). Per this Part's own stated Prerequisite, they are assumed complete by the time Part B executes. This document writes against the documented interface from plan-engine-v2 Task references: `PlanStore.all(status: str | None = None) -> list[TradePlanV2]`, `PlanStore.get(plan_id: str) -> TradePlanV2 | None`, `PlanStore.update(plan: TradePlanV2) -> None`.
- `swingbot/core/analytics/` **does not exist yet** either (Plan A, Part 1 of this same combined document, not yet started). Every `analytics.*` import below uses the exact names Part A's own task list commits to: `analytics.rank.follow_score`, `analytics.rank.rank_plans`, `analytics.rank.follow_breakdown`, `analytics.snapshots.load_snapshot`/`refresh_snapshot`, `analytics.journal.JournalStore`, `analytics.aggregate.stats_by`, `analytics.calibration.tier_calibration`/`score_deciles`/`badge_drift`, `analytics.insights.weekly_digest`/`edge_decay_report`/`top_lessons`, `analytics.metrics.*`.
- **Important real-codebase gap:** today, `swingbot/core/scanning/engine.py`'s `ScanItem.plan` (the object `build_embed`/`_build_trade_plan_table` in `embeds.py` currently render) is still the *old* pre-v2 plan object (`entry`, `stop_loss`, `take_profit`, `target2_price`, `risk_reward_ratio`, `target_sources`, `stop_sources` — see `embeds.py:227-307`), **not** a `TradePlanV2`. Wiring `ScanItem.plan` to a real `TradePlanV2` (and updating `_build_trade_plan_table`'s field reads to `trigger_price`/`stop_loss`/`tp1`/`tp2`) is plan-engine-v2's own remaining work, covered by this Part's Prerequisite line ("badged embeds"). Every task below that reads plan fields (`badge`, `tier`, `quality_score`, `quality_breakdown`, `badge_stats`, `status`, `status_history`, `plan_id`, `entry_type`, `trigger_price`, `stop_loss`, `tp1`, `tp2`) therefore builds test fixtures using a small stand-in object exposing exactly those `TradePlanV2` field names (either a real `TradePlanV2(...)` instance or, where only a handful of fields matter, `types.SimpleNamespace(...)`) rather than assuming today's old plan object — this plan does **not** touch `_build_trade_plan_table`'s existing body (B3 explicitly keeps it "unchanged"), only the wrapper logic around it (color, title chips, field ordering, new fields).
- Confirmed exact line numbers used throughout this document (re-verified by reading the files, not trusted from the abbreviated draft): `embeds.py` — `CONFIDENCE_COLORS`/`confidence_color` at :143-162, `_build_trade_plan_table` at :227, `build_embed` at :310, `regenerate_chart_for_trade` at :404, `build_closed_trade_embed` at :430, `build_near_close_embed` at :586. `trades.py` — `format_trades_table` at :56, `TradesPaginator` at :83, `_build_trade_detail_embed` at :180, `tradecharts_cmd` at :288. `scanning.py` — `_send_alerts` at :204, `@tasks.loop` `session_scan` at :362. `explain.py` — `build_explanation` at :38. `trade_chart.py` — `generate_trade_chart` at :147, `generate_all_strategy_charts` at :867. `bot_core.py` — `bot = commands.Bot(...)` at :46, `COMMANDS_BY_CATEGORY` at :90, `COMMAND_USAGE` at :152. `slash.py` — `/check` (the `Context.from_interaction` bridge pattern) at :164-212, `/ticker` at :234, `/backtest` at :246, `/backtestwatchlist` at :284, `/trades` at :315, `/performance` at :335, `/watchlist` at :349 — all six of these post a literal `!command` string into the channel via `interaction.channel.send(f"!...")` today, confirming Task B25's premise exactly. `config.py` — the `Field` dataclass at :73-93, `FIELDS` list closes at :357 (new entries in this plan are inserted immediately before that `]`); no `"Discord Alerts"` Field section exists yet — this plan introduces it fresh, following the same style as the existing `"Plan Engine v2"` section (config.py:324-337).

## Global Constraints

- **Never suppress WEAK plans** (standing user requirement) — visual de-emphasis only.
- **Ranking = `analytics.rank.follow_score` everywhere.** No embed, board, or digest sorts plans any other way.
- **Stat displays read Plan A functions/snapshot** — no formulas in command modules.
- **Embed limits enforced in code:** description ≤ 4096, field value ≤ 1024, total ≤ 6000; builders truncate with `…` rather than raise (existing 4000-char description truncation stays).
- **Views:** author-locked, `timeout=180`, `on_timeout` disables components — copy the `TradesPaginator` pattern (`swingbot/commands/trades.py:83`).
- **Blocking work off the event loop:** every chart render or backtest triggered from a command runs via `asyncio.to_thread` (or the existing background-thread pattern in `scanning.py`).
- **New behavior that changes channel output ships behind a config Field, default preserving today's output:** `ALERT_EMBED_LAYOUT` (detailed), `DAILY_DIGEST_ENABLED` (false), `DIGEST_MAX_PLANS` (3).
- **Charts:** all new renders use `chart_style.py` constants (`CHART_BG`, `UP_COLOR`, …) — one visual system.
- **Every task ends green:** `python -m pytest tests/ -q` + `make check` before commit; conventional commits.

## File Structure (target state)

```
swingbot/core/scanning/
  embed_theme.py         NEW  tier/badge colors, chips, section order, price fmt
  embeds.py              MOD  themed build_embed, layouts, follow-score line, WEAK compact block
swingbot/core/charts/
  analytics_charts.py    NEW  equity, R-histogram, calibration, strategy-heatmap renders
  cache.py               NEW  content-hash PNG cache + purge
  trade_chart.py         MOD  plan= kwarg: R bands, trigger arrow, watermark, trail, MFE/MAE
swingbot/core/
  explain.py             MOD  v2 trigger wording
swingbot/commands/
  scanning.py            MOD  _send_alerts ranked order + views, digest hook
  views.py               NEW  PlanActionView, PlanBoardView
  plans.py               MOD  live ranked board, filters
  stats.py               NEW  !top, !stats, !lessons, !calibration, !journal
  slash.py               MOD  real callback bridges + new slash commands
swingbot/
  bot_core.py            MOD  help catalog additions
  config.py              MOD  3 new Fields
tests/
  test_embed_theme.py, test_embeds_v3.py, test_views.py, test_plans_board.py,
  test_stats_commands.py, test_analytics_charts.py, test_plan_chart_overlays.py,
  test_chart_cache.py, test_digest.py
```

---

# Phase B0 — Embed design system (Tasks B1–B4)

### Task B1: `embed_theme.py`

**Files:**
- Create: `swingbot/core/scanning/embed_theme.py`
- Test: `tests/test_embed_theme.py`

**Interfaces:**
- Produces (consumed by every later embed task):
  - `TIER_COLORS = {"A": 0x2ecc71, "B": 0xf1c40f, "C": 0x95a5a6}`
  - `plan_color(badge: str, tier: str) -> discord.Color` — VALIDATED → `TIER_COLORS[tier]`; WEAK → fixed `0xe67e22` amber regardless of tier
  - `tier_chip(tier) -> str` → `"🅰"`/`"🅱"`/`"🅲"`; `badge_chip(badge) -> str` → `"✅ VALIDATED"` / `"⚠️ WEAK"`
  - `follow_chip(score: float) -> str` → `"▰▰▰▰▱ 82"` (5 blocks, filled = round(score/20))
  - `fmt_price(x: float, sym: str) -> str` — 2dp ≥ 1.0, 4dp below
  - `SECTION_ORDER = ("headline", "plan", "quality", "confluence", "changes", "branches", "track_record", "warnings")`
  - `apply_footer(embed, *, plan_id=None)` — added here as a stub raising `NotImplementedError` is wrong; it is fully implemented in Task B8 (kept in this same module, added there) — this task only defines the five items above.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_embed_theme.py
import discord
from swingbot.core.scanning import embed_theme as th


def test_plan_color_weak_is_amber_regardless_of_tier():
    assert th.plan_color("WEAK", "A").value == 0xE67E22
    assert th.plan_color("WEAK", "C").value == 0xE67E22
    assert th.plan_color("VALIDATED", "A").value == 0x2ECC71
    assert th.plan_color("VALIDATED", "B").value == 0xF1C40F
    assert th.plan_color("VALIDATED", "C").value == 0x95A5A6


def test_tier_and_badge_chips():
    assert th.tier_chip("A") == "🅰"
    assert th.tier_chip("B") == "🅱"
    assert th.tier_chip("C") == "🅲"
    assert th.badge_chip("VALIDATED") == "✅ VALIDATED"
    assert th.badge_chip("WEAK") == "⚠️ WEAK"


def test_follow_chip():
    assert th.follow_chip(82.0) == "▰▰▰▰▱ 82"
    assert th.follow_chip(0.0) == "▱▱▱▱▱ 0"
    assert th.follow_chip(100.0) == "▰▰▰▰▰ 100"
    assert th.follow_chip(49.9) == "▰▰▱▱▱ 50"   # round(49.9/20)=round(2.495)=2... see impl note


def test_fmt_price():
    assert th.fmt_price(1234.5, "€") == "€1234.50"
    assert th.fmt_price(0.4321, "$") == "$0.4321"
    assert th.fmt_price(1.0, "€") == "€1.00"
    assert th.fmt_price(0.9999, "€") == "€0.9999"


def test_section_order_is_the_documented_tuple():
    assert th.SECTION_ORDER == (
        "headline", "plan", "quality", "confluence",
        "changes", "branches", "track_record", "warnings",
    )
```

Note on `test_follow_chip`'s last assertion: `round(49.9 / 20) = round(2.495)`. Python's banker's rounding on a float that is not exactly representable evaluates `round(2.495)` to `2` in practice (2.495 is stored as slightly below 2.495), so the expected filled-block count is 2, matching `"▰▰▱▱▱ 50"` — the display number itself is `round(score)`, i.e. `50`, independent of the block count. This is spelled out here because it is exactly the kind of off-by-one a reviewer would otherwise flag as a bug; the implementation below computes blocks and the printed number from two separate `round()` calls on purpose.

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_embed_theme.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.scanning.embed_theme'`.

- [ ] **Step 3: Implement**

```python
# swingbot/core/scanning/embed_theme.py
"""
Single source of truth for the tier/badge-driven visual language every
embed builder in swingbot/core/scanning/embeds.py uses from here on --
colors, chip glyphs, the follow-score progress bar, price formatting,
and the fixed section order fields are grouped into. Centralizing this
here means "what does a WEAK plan look like" or "what order do fields
render in" is answered by reading ONE small module instead of grepping
every embed builder for its own ad-hoc color/order logic.
"""
import discord

# Tier accent colors -- used only for a VALIDATED plan. A WEAK plan is
# always amber (see plan_color) regardless of which tier it landed in,
# since "did this pass the 80% OOS bar at all" dominates "which tier
# within the passing set" for visual triage.
TIER_COLORS = {
    "A": 0x2ECC71,  # green
    "B": 0xF1C40F,  # yellow
    "C": 0x95A5A6,  # grey
}
WEAK_COLOR = 0xE67E22  # amber

_TIER_CHIPS = {"A": "🅰", "B": "🅱", "C": "🅲"}
_BADGE_CHIPS = {"VALIDATED": "✅ VALIDATED", "WEAK": "⚠️ WEAK"}

# Fixed rendering order for build_embed's fields -- every field the
# builder wants to show is bucketed into one of these named sections
# (see embeds.py's `sections: dict[str, list]` accumulator added in
# Task B2) and flushed in this exact order regardless of the order the
# code below happened to compute them in.
SECTION_ORDER = (
    "headline", "plan", "quality", "confluence",
    "changes", "branches", "track_record", "warnings",
)


def plan_color(badge: str, tier: str) -> discord.Color:
    """VALIDATED plans get their tier's accent color; WEAK plans are
    always amber, independent of tier -- badge (did it clear the bar)
    matters more for at-a-glance triage than tier (how good is it,
    conditional on having cleared the bar)."""
    if badge == "WEAK":
        return discord.Color(WEAK_COLOR)
    return discord.Color(TIER_COLORS.get(tier, TIER_COLORS["C"]))


def tier_chip(tier: str) -> str:
    return _TIER_CHIPS.get(tier, "🅲")


def badge_chip(badge: str) -> str:
    return _BADGE_CHIPS.get(badge, badge)


def follow_chip(score: float) -> str:
    """5-block progress bar plus the rounded integer score, e.g.
    '▰▰▰▰▱ 82'. Blocks filled and the printed number are each their own
    independent round() -- the bar is a coarse 0-5 visual, the number
    next to it is the precise one, and they're allowed to disagree at
    a rounding boundary (see test_follow_chip's docstring note)."""
    score = max(0.0, min(100.0, score))
    filled = round(score / 20)
    filled = max(0, min(5, filled))
    bar = "▰" * filled + "▱" * (5 - filled)
    return f"{bar} {round(score)}"


def fmt_price(x: float, sym: str) -> str:
    """2 decimal places for anything at or above 1.0 (typical equity
    price granularity); 4 decimal places below 1.0 (penny stocks/FX-like
    tickers where 2dp would lose all precision)."""
    if abs(x) >= 1.0:
        return f"{sym}{x:.2f}"
    return f"{sym}{x:.4f}"
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_embed_theme.py -v`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/embed_theme.py tests/test_embed_theme.py
git commit -m "feat: embed theme module (tier/badge colors, chips, follow chip, section order)"
```

### Task B2: Theme applied to `build_embed`

**Files:**
- Modify: `swingbot/core/scanning/embeds.py` (`build_embed` :310, `confidence_color` usage :330)
- Test: `tests/test_embeds_v3.py`

**Interfaces:**
- Produces: embed color comes from `plan_color(badge, tier)` when the item carries a v2 plan (falls back to existing `confidence_color`/gray otherwise); title gains `tier_chip` + `badge_chip` prefix: `"🅰 ✅ VALIDATED · 📈 LONG NVDA"`; fields are accumulated into a `sections: dict[str, list[tuple]]` keyed by `embed_theme.SECTION_ORDER` and flushed in that fixed order instead of `embed.add_field` being called inline as each field is computed. `_build_trade_plan_table` itself is untouched (still reads whatever field names `item.plan` exposes today — this task only changes the wrapper around it).

- [ ] **Step 1: Failing test**

```python
# tests/test_embeds_v3.py
"""v3 embed behavior: theming, layouts, follow-score line, WEAK compact
block, unified footer. Uses lightweight stand-in objects for
ScanItem/TradePlanV2 rather than running a real scan, since build_embed
is pure (object in, discord.Embed out)."""
import types

import discord
import pytest

from swingbot.core.scanning import embeds


def _fake_v2_plan(badge="VALIDATED", tier="A", quality_score=82, plan_id="p-abc123",
                   status="PENDING", entry_type="market", trigger_price=100.0,
                   stop_loss=95.0, tp1=110.0, tp2=None, quality_breakdown=None,
                   badge_stats=None, status_history=None, created_at="2026-07-11",
                   direction="bullish", strategy="EMA Crossover", horizon_key="4w",
                   source="strategy"):
    """A TradePlanV2-shaped stand-in exposing exactly the field names
    plan_engine.TradePlanV2 defines -- real embed code never reads
    fields outside this set, so this fixture doubles as a spec check:
    if a future refactor renames a TradePlanV2 field, tests using this
    helper start failing the moment code tries to read the old name."""
    return types.SimpleNamespace(
        plan_id=plan_id, ticker="NVDA", created_at=created_at, source=source,
        strategy=strategy, horizon_key=horizon_key, direction=direction,
        entry_type=entry_type, trigger_price=trigger_price, entry_price=None,
        expiry_bars=5, stop_loss=stop_loss, tp1=tp1, tp1_fraction=0.5, tp2=tp2,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
        quality_score=quality_score, quality_breakdown=quality_breakdown or [],
        tier=tier, badge=badge, badge_stats=badge_stats or {},
        status=status, status_history=status_history or [],
        # legacy fields _build_trade_plan_table still reads today (see
        # this Part's "Notes on assumptions" -- kept here so the fixture
        # also works as `item.plan` for the untouched table renderer).
        entry=trigger_price, take_profit=tp1, target2_price=tp2,
        risk_reward_ratio=round(abs(tp1 - trigger_price) / abs(trigger_price - stop_loss), 2),
        target_sources=["EMA"], stop_sources=["EMA"],
        stop_distance_pct=abs(trigger_price - stop_loss) / trigger_price * 100,
        target_distance_pct=abs(tp1 - trigger_price) / trigger_price * 100,
        target2_distance_pct=(abs(tp2 - trigger_price) / trigger_price * 100) if tp2 else None,
    )


def _fake_result(ticker="NVDA", trend="bullish", strategy="EMA Crossover", horizon_label="4 Weeks"):
    return types.SimpleNamespace(ticker=ticker, trend=trend, strategy=strategy, horizon_label=horizon_label)


def _fake_conf(level=4, label="High", score=78):
    return types.SimpleNamespace(level=level, label=label, score=score)


def _fake_item(plan=None, requirements=None, combined_from=None, htf_info=None):
    return types.SimpleNamespace(
        result=_fake_result(), plan=plan or _fake_v2_plan(), conf=_fake_conf(),
        requirements=requirements or [], combined_from=combined_from or [{"strategy": "EMA Crossover", "horizon_key": "4w"}],
        all_requirements_met=True, htf_info=htf_info,
    )


def test_weak_plan_is_amber_and_legacy_gray_path_still_works():
    weak_item = _fake_item(plan=_fake_v2_plan(badge="WEAK", tier="A"))
    embed = embeds.build_embed(weak_item, "explanation text", {"closed": 0}, None, None)
    assert embed.colour.value == 0xE67E22
    assert embed.title.startswith("🅰 ⚠️ WEAK")

    # A legacy item whose plan carries no `badge` attribute at all keeps
    # today's confidence-color path untouched.
    legacy_plan = types.SimpleNamespace(
        entry=100.0, stop_loss=95.0, take_profit=110.0, target2_price=None,
        risk_reward_ratio=2.0, target_sources=["EMA"], stop_sources=["EMA"],
        stop_distance_pct=5.0, target_distance_pct=10.0, target2_distance_pct=None,
    )
    legacy_item = _fake_item(plan=legacy_plan)
    legacy_embed = embeds.build_embed(legacy_item, "explanation text", {"closed": 0}, None, None)
    assert legacy_embed.colour == embeds.confidence_color(legacy_item.conf.level)
    assert not legacy_embed.title.startswith("🅰")


def test_validated_title_has_both_chips():
    item = _fake_item(plan=_fake_v2_plan(badge="VALIDATED", tier="B"))
    embed = embeds.build_embed(item, "explanation text", {"closed": 0}, None, None)
    assert embed.title.startswith("🅱 ✅ VALIDATED")
    assert "NVDA" in embed.title
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_embeds_v3.py -v`
Expected: FAIL — `AttributeError: 'SimpleNamespace' object has no attribute 'badge'` is swallowed by no such check existing yet; actual failure is an `AssertionError` on `embed.colour.value == 0xE67E22` (today it's the confidence color, not amber).

- [ ] **Step 3: Implement**

Add the import and a small helper near the top of `embeds.py` (after the existing imports, before `CONFIDENCE_COLORS`):

```python
from swingbot.core.scanning import embed_theme as theme


def _v2_plan(item):
    """Returns item.plan if it looks like a TradePlanV2 (has a `badge`
    attribute -- the old pre-v2 plan object never does), else None. A
    plain attribute probe rather than isinstance(...) so this keeps
    working for both a real TradePlanV2 and the lightweight test
    stand-ins used throughout tests/test_embeds_v3.py."""
    return item.plan if getattr(item.plan, "badge", None) is not None else None
```

Replace the body of `build_embed` (currently `embeds.py:310-401`) with a version that buckets every field into `sections` and flushes them in `theme.SECTION_ORDER`:

```python
def build_embed(item, explanation, perf_stats, open_positions_warning, chart_filename,
                htf_info: dict = None) -> discord.Embed:
    """
    htf_info, when provided, is a dict from scan_engine.py's HTF check:
        {"htf_bias": "bullish"|"bearish", "counter_trend": bool, "ema_period": int, "horizon_key": str}
    Counter-trend setups get a ⚠️ warning field added to the embed.
    """
    result, plan, conf = item.result, item.plan, item.conf
    is_bull = result.trend == "bullish"
    direction = "LONG (buy)" if is_bull else "SHORT (sell)"
    all_ok = item.all_requirements_met
    v2 = _v2_plan(item)

    priority_marker = "⭐ " if (conf.level >= 4 and all_ok) else ""
    needs_review_marker = "⚠️ " if not all_ok else ""
    chip_prefix = f"{theme.tier_chip(v2.tier)} {theme.badge_chip(v2.badge)} · " if v2 else ""
    title = f"{chip_prefix}{needs_review_marker}{priority_marker}{'🟢' if is_bull else '🔴'} {direction} — {result.ticker}"

    # Embed color: a v2 plan's badge/tier wins outright (theme.plan_color);
    # otherwise fall back to the pre-v2 confidence-color-when-all-ok,
    # neutral-gray-otherwise behavior exactly as before.
    if v2:
        embed_color = theme.plan_color(v2.badge, v2.tier)
    else:
        embed_color = confidence_color(conf.level) if all_ok else discord.Color.from_rgb(149, 165, 166)
    embed = discord.Embed(title=title, color=embed_color)

    # Every field is appended to its named bucket instead of the embed
    # directly -- theme.SECTION_ORDER below decides final render order,
    # not the order this function happens to compute things in.
    sections: dict[str, list[tuple]] = {k: [] for k in theme.SECTION_ORDER}

    confirmations = ", ".join(f"{c['strategy']} ({c['horizon_key']})" for c in item.combined_from)
    extra = f"  +{len(item.combined_from)-1} more horizon(s)" if len(item.combined_from) > 1 else ""
    sections["headline"].append(("Setup", f"{result.strategy}{extra}", True))
    sections["headline"].append(("Confirmed by", confirmations, False))
    sections["headline"].append(("Swing type", result.horizon_label, True))
    sections["headline"].append(("Confidence", _confidence_block(conf), True))

    if not all_ok:
        unmet = ", ".join(r.label for r in item.requirements if not r.passed)
        sections["warnings"].append((
            "⚠️ Not yet a clean setup",
            f"Doesn't meet: {unmet}. Shown for visibility -- see the trade plan below for exactly why "
            "(marked in bold red); not logged as a paper trade and won't auto-alert until it clears these.",
            False,
        ))

    if htf_info and htf_info.get("counter_trend"):
        ema_p = htf_info["ema_period"]
        htf_bias_word = htf_info["htf_bias"].capitalize()
        signal_word = "Bullish" if is_bull else "Bearish"
        sections["warnings"].append((
            "📉 Counter-trend signal",
            f"{signal_word} setup, but this ticker's own {ema_p}-day EMA trend is **{htf_bias_word}** "
            f"(higher-timeframe bias for {htf_info['horizon_key']} horizon). "
            f"Counter-trend setups have a lower base probability of following through -- "
            f"confidence was reduced by {config.HTF_COUNTER_TREND_PENALTY} points to reflect this.",
            False,
        ))

    sections["plan"].append(("🎯 Trade plan", _build_trade_plan_table(item), False))

    what_changed = _snapshot_and_diff(item)
    if what_changed:
        sections["changes"].append(("🔄 What changed since last scan", what_changed, False))

    level_word = "Resistance" if is_bull else "Support"
    opposite_word = "Support" if is_bull else "Resistance"
    branch_lines = []
    if plan.target2_price is not None:
        branch_lines.append(f"Continues past {level_word.lower()} 1 → next stop {plan.target2_price:.2f} (+{plan.target2_distance_pct:.1f}%)")
    else:
        branch_lines.append(f"Continues past {level_word.lower()} 1 → no further level found for a stretch target")
    branch_lines.append(f"Reverses at {level_word.lower()} 1 → pulls back toward {opposite_word.lower()} at {plan.stop_loss:.2f} ({plan.stop_distance_pct:.1f}%)")
    sections["branches"].append(("🔀 If it gets there", "\n".join(branch_lines), False))

    if perf_stats["closed"] > 0:
        wr = perf_stats["win_rate"]
        sections["track_record"].append((
            f"Track record @ Lv{conf.level}",
            f"{wr:.0f}% win rate ({perf_stats['wins']}W/{perf_stats['losses']}L, {perf_stats['closed']} closed)",
            True,
        ))
    else:
        sections["track_record"].append((f"Track record @ Lv{conf.level}", "No closed trades yet at this level", True))

    if open_positions_warning:
        sections["warnings"].append(("⚠️ Position limit", open_positions_warning, False))

    for section_key in theme.SECTION_ORDER:
        for name, value, inline in sections[section_key]:
            embed.add_field(name=name, value=value, inline=inline)

    embed.description = explanation[:4000]
    if chart_filename:
        embed.set_image(url=f"attachment://{chart_filename}")
    embed.set_footer(text="Technical signal only, based on today's still-developing daily candle -- not financial advice.")
    return embed
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_embeds_v3.py tests/test_embed_theme.py -q`
Expected: all pass. Then run the full suite to confirm no regression in v2 Phase 6's own embed tests: `python -m pytest tests/ -q` — green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/embeds.py tests/test_embeds_v3.py
git commit -m "feat: tier/badge-themed scan embeds"
```

### Task B3: Compact / detailed layouts

**Files:**
- Modify: `swingbot/core/scanning/embeds.py`, `swingbot/config.py` (new Field)
- Test: `tests/test_embeds_v3.py`

**Interfaces:**
- Produces: `build_embed(..., layout: str = "detailed")`. `"compact"` renders: headline, the ANSI plan table (`_build_trade_plan_table` unchanged), one-line quality (`Tier A · 82/100 · ✅ VALIDATED (OOS N=206 WR 81.6%)`), follow chip — and drops confluence/changes/branches sections. Config Field `ALERT_EMBED_LAYOUT` (select `detailed|compact`, section "Discord Alerts", default `detailed`, hot-reloadable) feeds the scan alert path.

- [ ] **Step 1: Failing test**

```python
# tests/test_embeds_v3.py (append)
def test_compact_layout_drops_confluence_and_has_at_most_5_fields():
    item = _fake_item(plan=_fake_v2_plan(
        badge="VALIDATED", tier="A", quality_score=82,
        badge_stats={"status": "VALIDATED", "n": 206, "win_rate": 81.6, "expectancy_r": 0.42, "window": "2024-2025"},
    ))
    embed = embeds.build_embed(item, "explanation text", {"closed": 0}, None, None, layout="compact")
    assert len(embed.fields) <= 5
    assert not any("What changed" in f.name for f in embed.fields)
    assert not any(f.name == "Confirmed by" for f in embed.fields)
    assert any("Tier A" in f.value and "82/100" in f.value and "VALIDATED" in f.value for f in embed.fields)


def test_detailed_layout_keeps_current_field_set():
    item = _fake_item(plan=_fake_v2_plan())
    embed = embeds.build_embed(item, "explanation text", {"closed": 0}, None, None, layout="detailed")
    assert any(f.name == "Confirmed by" for f in embed.fields)
    assert any(f.name == "🔀 If it gets there" for f in embed.fields)
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_embeds_v3.py -v -k layout`
Expected: FAIL — `build_embed() got an unexpected keyword argument 'layout'`.

- [ ] **Step 3: Implement**

In `config.py`, insert before the closing `]` of `FIELDS` (currently `config.py:357`), a new section:

```python
    # --- Discord Alerts (Cockpit v3 / Plan B) ---
    Field("ALERT_EMBED_LAYOUT", "ALERT_EMBED_LAYOUT", "Discord Alerts", "Alert embed layout",
          type="select", default="detailed", options=["detailed", "compact"],
          help="'detailed' (default) shows every section this bot has always shown. 'compact' shows "
               "just the headline, trade plan table, a one-line quality summary, and the follow-score "
               "chip -- confluence/what-changed/branch sections are dropped to fit more alerts on screen "
               "at once. Purely a rendering choice; no scoring or filtering changes."),
```

In `embeds.py`, change the `build_embed` signature and gate the optional sections:

```python
def build_embed(item, explanation, perf_stats, open_positions_warning, chart_filename,
                htf_info: dict = None, layout: str = "detailed") -> discord.Embed:
    ...
    v2 = _v2_plan(item)
    compact = layout == "compact"
    ...
    if not compact:
        confirmations = ", ".join(f"{c['strategy']} ({c['horizon_key']})" for c in item.combined_from)
        extra = f"  +{len(item.combined_from)-1} more horizon(s)" if len(item.combined_from) > 1 else ""
        sections["headline"].append(("Setup", f"{result.strategy}{extra}", True))
        sections["headline"].append(("Confirmed by", confirmations, False))
    else:
        sections["headline"].append(("Setup", result.strategy, True))
    sections["headline"].append(("Swing type", result.horizon_label, True))
    sections["headline"].append(("Confidence", _confidence_block(conf), True))

    if v2:
        stats = v2.badge_stats or {}
        oos_bit = f" (OOS N={stats.get('n', 0)} WR {stats.get('win_rate', 0):.1f}%)" if stats else ""
        quality_line = f"Tier {v2.tier} · {v2.quality_score}/100 · {theme.badge_chip(v2.badge)}{oos_bit}"
        sections["quality"].append(("📐 Quality", quality_line, False))

    if not all_ok:
        ...  # unchanged, still appended to sections["warnings"]
    if htf_info and htf_info.get("counter_trend") and not compact:
        ...  # unchanged, gated out of compact same as "Confirmed by"

    sections["plan"].append(("🎯 Trade plan", _build_trade_plan_table(item), False))

    if not compact:
        what_changed = _snapshot_and_diff(item)
        if what_changed:
            sections["changes"].append(("🔄 What changed since last scan", what_changed, False))

        level_word = "Resistance" if is_bull else "Support"
        opposite_word = "Support" if is_bull else "Resistance"
        branch_lines = [...]  # unchanged
        sections["branches"].append(("🔀 If it gets there", "\n".join(branch_lines), False))

        if perf_stats["closed"] > 0:
            ...  # unchanged track_record field
        else:
            ...
        if open_positions_warning:
            sections["warnings"].append(("⚠️ Position limit", open_positions_warning, False))
    ...
```

`_snapshot_and_diff` is still called and still updates the on-disk snapshot even when `compact` (it must run every time regardless of display, since it's also the *write*, not just the read) — so in compact mode call it for its side effect but discard the result: `_snapshot_and_diff(item)` unconditionally, then only append the field `if not compact and what_changed`. Adjust the diff above so the call always happens ahead of the `if not compact:` branch:

```python
    what_changed = _snapshot_and_diff(item)   # always runs -- it's the snapshot WRITE, not just a read
    if not compact and what_changed:
        sections["changes"].append(("🔄 What changed since last scan", what_changed, False))
```

Finally, thread `layout` from the scan alert path (`scan_engine`'s call into `build_embed` — find the call site with `Grep "build_embed(" swingbot/core/scan_engine.py`) by passing `layout=config.ALERT_EMBED_LAYOUT`.

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_embeds_v3.py -q`
Expected: `6 passed`. Full suite: `python -m pytest tests/ -q` — green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/embeds.py swingbot/config.py tests/test_embeds_v3.py
git commit -m "feat: compact alert layout behind ALERT_EMBED_LAYOUT"
```

### Task B4: Trigger-aware explanation wording

**Files:**
- Modify: `swingbot/core/explain.py` (`build_explanation` :38)
- Test: `tests/test_embeds_v3.py`

**Interfaces:**
- Produces: `build_explanation(..., plan=None)` — when a v2 plan with `entry_type="stop_entry"` is passed, line 1 reads `"Waits for a BUY STOP above {trigger}"` (SELL STOP below for bearish) instead of implying immediate entry; market-entry plans read `"Enters at market"`. No plan → wording unchanged.

- [ ] **Step 1: Failing test**

```python
# tests/test_embeds_v3.py (append)
import types as _types


def _fake_scenario_result(direction="bullish"):
    scenario = _types.SimpleNamespace(
        direction=direction, target_sources=["EMA"], stop_sources=["EMA"],
        take_profit=110.0, target_distance_pct=10.0, stop_loss=95.0,
        stop_distance_pct=5.0, target2_price=None, target2_distance_pct=None,
    )
    return _types.SimpleNamespace(ticker="NVDA", horizon_label="4 Weeks", strategy="EMA Crossover", scenario=scenario)


def test_stop_entry_plan_gets_buy_stop_wording():
    from swingbot.core.explain import build_explanation
    plan = _fake_v2_plan(entry_type="stop_entry", trigger_price=112.5, direction="bullish")
    text = build_explanation(_fake_scenario_result(), plan=plan)
    assert "BUY STOP above" in text
    assert "112.5" in text or "112.50" in text


def test_bearish_stop_entry_plan_gets_sell_stop_wording():
    from swingbot.core.explain import build_explanation
    plan = _fake_v2_plan(entry_type="stop_entry", trigger_price=88.0, direction="bearish")
    text = build_explanation(_fake_scenario_result(direction="bearish"), plan=plan)
    assert "SELL STOP below" in text


def test_market_entry_plan_reads_enters_at_market():
    from swingbot.core.explain import build_explanation
    plan = _fake_v2_plan(entry_type="market")
    text = build_explanation(_fake_scenario_result(), plan=plan)
    assert "Enters at market" in text


def test_no_plan_keeps_wording_unchanged():
    from swingbot.core.explain import build_explanation
    text = build_explanation(_fake_scenario_result())
    assert "BUY STOP" not in text
    assert "Enters at market" not in text
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_embeds_v3.py -v -k explanation`
Expected: FAIL — `TypeError: build_explanation() got an unexpected keyword argument 'plan'`.

- [ ] **Step 3: Implement**

In `explain.py`, change the signature and insert the new first line only when `plan` is given:

```python
def build_explanation(result, earnings_info=None,
                      target_confluence: tuple = None,
                      stop_confluence: tuple = None,
                      confirmed_by: list = None,
                      plan=None) -> str:
    scenario = result.scenario
    is_bull = scenario.direction == "bullish"
    level_word = "resistance" if is_bull else "support"
    opp_word = "support" if is_bull else "resistance"
    arrow = "↑" if is_bull else "↓"

    if target_confluence:
        t_count, t_families = target_confluence
    else:
        t_families = list(dict.fromkeys(scenario.target_sources))
        t_count = len(t_families)

    if stop_confluence:
        s_count, s_families = stop_confluence
    else:
        s_families = list(dict.fromkeys(scenario.stop_sources))
        s_count = len(s_families)

    t_str = _family_list(t_families)
    s_str = _family_list(s_families)
    plural = "" if t_count == 1 else "s"

    lines = []

    # Entry-mechanics line -- only present when a v2 plan is passed, and
    # placed FIRST so the reader knows how this actually gets triggered
    # before reading what confirmed the level. entry_type="market" plans
    # (and legacy no-plan callers) fall through unchanged.
    if plan is not None and getattr(plan, "entry_type", None) == "stop_entry":
        trigger_word = "BUY STOP above" if is_bull else "SELL STOP below"
        lines.append(f"⏱️ Waits for a **{trigger_word} {plan.trigger_price:.2f}** before this trade is live.")
    elif plan is not None and getattr(plan, "entry_type", None) == "market":
        lines.append("▶️ Enters at market -- no trigger to wait for.")

    lines.append(
        f"{arrow} **{result.ticker}** — {t_count} method{plural} ({t_str}) "
        f"converge on {level_word} **{scenario.take_profit:.2f}** "
        f"(+{scenario.target_distance_pct:.1f}%, {result.horizon_label.lower()})."
    )
    lines.append(
        f"🛑 Stop at **{scenario.stop_loss:.2f}** "
        f"({'-' if is_bull else '+'}{scenario.stop_distance_pct:.1f}%) "
        f"— {s_str}."
    )

    strategy_names = []
    if hasattr(result, "strategy"):
        strategy_names.append(result.strategy)
    if confirmed_by:
        for cb in confirmed_by:
            if isinstance(cb, dict):
                strategy_names.append(cb.get("strategy", ""))
            elif hasattr(cb, "strategy"):
                strategy_names.append(cb.strategy)
    is_bnr = any("break" in s.lower() and "retest" in s.lower() for s in strategy_names)
    if is_bnr:
        level_label = "resistance" if is_bull else "support"
        entry_bar = "green candle close" if is_bull else "red candle close"
        lines.append(
            f"⏳ **Wait for the retest**: after the breakout, let price pull back to "
            f"the broken {level_label} (~{scenario.stop_loss:.2f} area) and wait for a "
            f"confirming {entry_bar} — entering on the breakout bar itself carries "
            f"significantly higher false-breakout risk."
        )

    if scenario.target2_price is not None:
        t2_str = (
            f"continues → **{scenario.target2_price:.2f}** "
            f"(+{scenario.target2_distance_pct:.1f}%)"
        )
    else:
        t2_str = "continues → no further level"
    lines.append(
        f"🔀 At {scenario.take_profit:.2f}: {t2_str} "
        f"| reverses → stop {scenario.stop_loss:.2f}."
    )

    if earnings_info is not None:
        edate, days = earnings_info
        lines.append(
            f"⚠️ Earnings **{edate}** ({days}d) — inside hold window, "
            f"volatility spike can gap through stop and target."
        )

    return "\n".join(lines)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_embeds_v3.py -q`
Expected: all pass. `python -m pytest tests/ -q` — green (existing `explain.py` callers pass no `plan` kwarg, default `None`, wording unchanged for them).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/explain.py tests/test_embeds_v3.py
git commit -m "feat: trigger-aware explanations"
```

---

# Phase B1 — Alert stream (Tasks B5–B8)

### Task B5: Alerts post in follow-score order

**Files:**
- Modify: `swingbot/commands/scanning.py` (`_send_alerts` :204 — alert dispatch loop, currently scan order)
- Test: `tests/test_embeds_v3.py`

**Interfaces:**
- Consumes: `analytics.rank.rank_plans`.
- Produces: within one scan cycle, alert items carrying plans are stamped `regime_aligned` (from the scan's regime check vs plan direction) and dispatched in `rank_plans` order, highest first; non-plan legacy alerts keep original order after them. Extracted testable helper `_ordered_alerts(alerts: list[tuple], today=None) -> list[tuple]` where each tuple is `(embed, chart_path, plan_or_none)` — note this is a **3-tuple**, one element more than today's `(embed, chart_path)` pairs; `_send_alerts` and every caller that builds the `alerts` list must be updated to the 3-tuple shape in this same task (see Step 3).

- [ ] **Step 1: Failing test**

```python
# tests/test_embeds_v3.py (append)
def test_ordered_alerts_sorts_by_follow_score_plans_first():
    from swingbot.commands.scanning import _ordered_alerts
    import datetime as dt

    def _plan(score_inputs):
        badge, quality, regime = score_inputs
        return _fake_v2_plan(badge=badge, quality_score=quality)

    # Fixture follow_scores: 30 (WEAK, low quality), 90 (VALIDATED, high
    # quality, regime aligned, fresh), 60 (VALIDATED, mid quality, no regime).
    low = ("dummy_embed_low", "chart_low.png", _plan(("WEAK", 20, False)))
    high = ("dummy_embed_high", "chart_high.png", _plan(("VALIDATED", 80, True)))
    mid = ("dummy_embed_mid", "chart_mid.png", _plan(("VALIDATED", 50, False)))
    for _, _, plan in (low, high, mid):
        plan.regime_aligned = plan.badge == "VALIDATED" and plan.quality_score == 80
        plan.created_at = "2026-07-11"

    ordered = _ordered_alerts([low, mid, high], today=dt.date(2026, 7, 11))
    assert [a[0] for a in ordered] == ["dummy_embed_high", "dummy_embed_mid", "dummy_embed_low"]


def test_ordered_alerts_keeps_legacy_alerts_after_plan_alerts_in_original_order():
    from swingbot.commands.scanning import _ordered_alerts
    legacy1 = ("legacy1", "c1.png", None)
    legacy2 = ("legacy2", "c2.png", None)
    plan_item = ("planned", "c3.png", _fake_v2_plan(badge="VALIDATED", quality_score=90))
    plan_item[2].regime_aligned = True
    plan_item[2].created_at = "2026-07-11"

    import datetime as dt
    ordered = _ordered_alerts([legacy1, plan_item, legacy2], today=dt.date(2026, 7, 11))
    assert [a[0] for a in ordered] == ["planned", "legacy1", "legacy2"]
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_embeds_v3.py -v -k ordered_alerts`
Expected: FAIL — `ImportError: cannot import name '_ordered_alerts' from 'swingbot.commands.scanning'`.

- [ ] **Step 3: Implement**

In `swingbot/commands/scanning.py`, add the import and helper near the top (after existing imports), and change `_send_alerts` to accept and dispatch the 3-tuple shape:

```python
from swingbot.core.analytics.rank import rank_plans


def _ordered_alerts(alerts: list, today=None) -> list:
    """Splits `alerts` (each a (embed, chart_path, plan_or_none) tuple)
    into plan-carrying and legacy groups, ranks the plan-carrying group
    by analytics.rank.rank_plans (THE shared ordering -- see Plan A
    Task A18), and returns plan-carrying alerts first (highest
    follow_score first), then every legacy (no-plan) alert in its
    original scan order, unchanged. rank_plans is given the plan
    objects directly and returns them in ranked order; this function
    re-derives the alert tuple order from that ranked plan-object list
    rather than re-scoring anything itself, so there is exactly one
    place (analytics.rank) that ever computes follow_score."""
    plan_alerts = [a for a in alerts if a[2] is not None]
    legacy_alerts = [a for a in alerts if a[2] is None]

    ranked_plans = rank_plans([a[2] for a in plan_alerts], today=today)
    by_plan_id = {id(a[2]): a for a in plan_alerts}
    ranked_alert_tuples = [by_plan_id[id(p)] for p in ranked_plans]

    return ranked_alert_tuples + legacy_alerts


async def _send_alerts(destination, alerts):
    """alerts: list of (embed, chart_path, plan_or_none) 3-tuples. Every
    call site that builds this list (scan_engine.run_scan's return
    value) must be updated to append the plan (or None for a legacy,
    non-v2 alert) as the third element -- see scan_engine.py's own
    alert-building loop."""
    for embed, chart_path, _plan in _ordered_alerts(alerts):
        if chart_path:
            await destination.send(embed=embed, file=discord.File(chart_path, filename=os.path.basename(chart_path)))
        else:
            await destination.send(embed=embed)
```

Update `scan_engine.run_scan`'s alert-building loop (`Grep "alerts.append" swingbot/core/scan_engine.py`) to append the plan as a third tuple element: `alerts.append((embed, chart_path, item.plan if _v2_plan_marker(item) else None))` — reuse the same `getattr(item.plan, "badge", None) is not None` probe used in `embeds._v2_plan` (import it, or duplicate the one-liner locally to avoid a scan_engine → scanning-command-module import cycle; duplicating the one-liner is preferred here since `scan_engine.py` must not import from `swingbot/commands/`).

Regime stamping: inside the same alert-building loop, immediately after resolving `htf_info`, stamp `item.plan.regime_aligned = (htf_info is None) or not htf_info.get("counter_trend", False)` when `item.plan` carries a `badge` attribute — `regime_aligned` is exactly "the scan's regime check agreed with the plan's own direction", i.e. NOT flagged counter-trend.

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_embeds_v3.py -q` then the full suite `python -m pytest tests/ -q` (this task changes the `alerts` tuple shape consumed by `!check`'s and the automatic scan's own send paths — confirm both still work by grep-checking every unpacking site: `Grep "for embed, chart_path in" swingbot/` must return zero results afterward).

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/scanning.py swingbot/core/scan_engine.py tests/test_embeds_v3.py
git commit -m "feat: alerts ranked by follow_score"
```

### Task B6: "Why follow this" line

**Files:**
- Modify: `swingbot/core/scanning/embeds.py`, `swingbot/core/analytics/rank.py` (adds `follow_breakdown`)
- Test: `tests/test_embeds_v3.py`, `tests/test_rank.py`

**Interfaces:**
- Produces: field `🧭 Follow score` on plan-carrying embeds: `follow_chip(score)` + one line per non-zero component, e.g. `"✅ validated source +40 · quality 82 → +33 · regime aligned +10 · fresh +10"`. Component values come from `rank.follow_breakdown(plan, today) -> list[tuple[str, float]]` (same weights as `follow_score`).

- [ ] **Step 1: Failing tests**

```python
# tests/test_rank.py (append -- this function lives in Plan A's module,
# tested here alongside follow_score/rank_plans since B6 is what actually
# consumes it; Plan A's own Task A18 test file already covers follow_score
# itself, so this only adds follow_breakdown's contract)
import datetime as dt
from swingbot.core.analytics.rank import follow_score, follow_breakdown

TODAY = dt.date(2026, 7, 11)


def test_follow_breakdown_sums_to_follow_score():
    fixtures = [
        {"badge": "VALIDATED", "quality_score": 80, "regime_aligned": True, "created_at": "2026-07-11"},
        {"badge": "WEAK", "quality_score": 30, "regime_aligned": False, "created_at": "2026-07-05"},
        {"badge": "VALIDATED", "quality_score": 0, "regime_aligned": False, "created_at": "2026-06-01"},
        {"badge": "VALIDATED", "quality_score": 100, "regime_aligned": True, "created_at": "2026-07-11"},
        {"badge": "WEAK", "quality_score": 50, "regime_aligned": True, "created_at": "2026-07-10"},
    ]
    for p in fixtures:
        breakdown = follow_breakdown(p, TODAY)
        assert abs(sum(v for _, v in breakdown) - follow_score(p, today=TODAY)) < 1e-9


def test_follow_breakdown_labels_and_zero_components_omitted():
    p = {"badge": "WEAK", "quality_score": 0, "regime_aligned": False, "created_at": "2026-06-01"}
    breakdown = follow_breakdown(p, TODAY)
    labels = [label for label, _ in breakdown]
    assert not any("validated" in l.lower() for l in labels)  # badge component is 0, omitted
```

```python
# tests/test_embeds_v3.py (append)
def test_follow_score_field_present_with_chip_and_components():
    plan = _fake_v2_plan(badge="VALIDATED", tier="A", quality_score=82)
    plan.regime_aligned = True
    plan.created_at = "2026-07-11"
    item = _fake_item(plan=plan)
    embed = embeds.build_embed(item, "explanation text", {"closed": 0}, None, None)
    field = next((f for f in embed.fields if f.name == "🧭 Follow score"), None)
    assert field is not None
    assert "▰" in field.value
    assert "validated" in field.value.lower()
    assert "quality" in field.value.lower()
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_rank.py tests/test_embeds_v3.py -v -k "breakdown or follow_score_field"`
Expected: FAIL — `ImportError: cannot import name 'follow_breakdown'`.

- [ ] **Step 3: Implement**

In `swingbot/core/analytics/rank.py` (Plan A's module — this task adds one function to it, per this Part's own file-ownership note that Plan B may add to `rank.py` when the addition is itself part of the shared ranking contract):

```python
def follow_breakdown(plan, today: "dt.date | None" = None) -> list:
    """Same four weighted components follow_score sums, itemized as
    (label, points) pairs -- used to render the '🧭 Follow score' embed
    field (Plan B Task B6) so every number on screen traces back to
    exactly the formula follow_score itself computes. Zero-value
    components are OMITTED (a WEAK plan doesn't get a '0' line cluttering
    the field), matching follow_chip's "only show what actually
    contributed" spirit."""
    import datetime as _dt

    today = today or _dt.date.today()
    badge = _get(plan, "badge", None)
    quality_score = _get(plan, "quality_score", 0) or 0
    regime_aligned = bool(_get(plan, "regime_aligned", False))
    created_at = _get(plan, "created_at", None)

    parts = []
    if badge == "VALIDATED":
        parts.append(("✅ validated source", 40.0))
    quality_pts = 0.4 * quality_score
    if quality_pts:
        parts.append((f"quality {quality_score} → +{quality_pts:.0f}", quality_pts))
    if regime_aligned:
        parts.append(("regime aligned", 10.0))
    if created_at:
        try:
            age_days = (today - _dt.date.fromisoformat(created_at)).days
        except ValueError:
            age_days = 0
        freshness = max(0.0, 10.0 - 2.0 * age_days)
        if freshness:
            parts.append(("fresh", freshness))
    return parts
```

(`_get` is `rank.py`'s existing internal `getattr`-or-`.get` helper from Task A18 — reuse it, do not redefine.)

In `embeds.py`, add the field inside `build_embed`, right after the quality-line insertion point (works for both compact and detailed layouts — insert unconditionally when `v2` is truthy, into `sections["quality"]`):

```python
    if v2:
        from swingbot.core.analytics.rank import follow_score, follow_breakdown
        import datetime as _dt
        today = _dt.date.today()
        score = follow_score(v2, today=today)
        breakdown = follow_breakdown(v2, today)
        breakdown_line = " · ".join(f"{label} +{pts:.0f}" if "quality" not in label else label for label, pts in breakdown)
        sections["quality"].append(("🧭 Follow score", f"{theme.follow_chip(score)}\n{breakdown_line}", False))
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_rank.py tests/test_embeds_v3.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/rank.py swingbot/core/scanning/embeds.py tests/test_rank.py tests/test_embeds_v3.py
git commit -m "feat: follow-score breakdown on alerts"
```

### Task B7: WEAK block goes compact

**Files:**
- Modify: `swingbot/core/scanning/embeds.py`
- Test: `tests/test_embeds_v3.py`

**Interfaces:**
- Produces: WEAK plans render a single-line caution `⚠️ WEAK — OOS WR {wr}% (N={n}), below the 80% bar. Extra care.` as the FIRST field (was a multi-line block), plus the amber color from B2. Exact stats still verbatim from `badge_stats`. VALIDATED plans unaffected.

- [ ] **Step 1: Failing test**

```python
# tests/test_embeds_v3.py (append)
def test_weak_caution_is_first_field_and_one_line():
    plan = _fake_v2_plan(badge="WEAK", tier="B",
                          badge_stats={"status": "WEAK", "n": 42, "win_rate": 63.4, "expectancy_r": -0.05, "window": "2024-2025"})
    item = _fake_item(plan=plan)
    embed = embeds.build_embed(item, "explanation text", {"closed": 0}, None, None)
    first = embed.fields[0]
    assert first.name.startswith("⚠️ WEAK")
    assert "N=42" in first.value
    assert "63.4%" in first.value
    assert "\n" not in first.value.strip()


def test_validated_plan_has_no_weak_caution_field():
    item = _fake_item(plan=_fake_v2_plan(badge="VALIDATED"))
    embed = embeds.build_embed(item, "explanation text", {"closed": 0}, None, None)
    assert not any(f.name.startswith("⚠️ WEAK") for f in embed.fields)
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_embeds_v3.py -v -k weak_caution`
Expected: FAIL — no such field exists yet.

- [ ] **Step 3: Implement**

In `build_embed`, right after `sections: dict[str, list[tuple]] = {k: [] for k in theme.SECTION_ORDER}` is declared, insert the WEAK caution as the very first thing appended to `sections["headline"]` (so it stays first after the flush loop, since dict insertion order is preserved within a bucket):

```python
    if v2 and v2.badge == "WEAK":
        stats = v2.badge_stats or {}
        wr = stats.get("win_rate", 0.0)
        n = stats.get("n", 0)
        sections["headline"].append((
            "⚠️ WEAK", f"OOS WR {wr:.1f}% (N={n}), below the 80% bar. Extra care.", False,
        ))
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_embeds_v3.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/embeds.py tests/test_embeds_v3.py
git commit -m "feat: compact WEAK caution line"
```

### Task B8: Consistent footer + timestamps

**Files:**
- Modify: `swingbot/core/scanning/embed_theme.py` (adds `apply_footer`), `swingbot/core/scanning/embeds.py` (`build_embed`, `build_closed_trade_embed` :430, `build_near_close_embed` :586)
- Test: `tests/test_embeds_v3.py`

**Interfaces:**
- Produces: shared `apply_footer(embed, *, plan_id=None)` in `embed_theme.py` — sets `embed.timestamp = discord.utils.utcnow()` and footer `"{disclaimer} · plan {short_id}"` (8-char id when given). All three builders call it; disclaimer text unchanged.

- [ ] **Step 1: Failing test**

```python
# tests/test_embeds_v3.py (append)
def test_all_three_embeds_have_timestamp_and_identical_disclaimer_prefix():
    scan_item = _fake_item(plan=_fake_v2_plan(plan_id="12345678-abcd-efgh"))
    scan_embed = embeds.build_embed(scan_item, "x", {"closed": 0}, None, None)

    closed_trade = {
        "status": "win", "ticker": "NVDA", "entry": 100.0, "stop_loss": 95.0,
        "take_profit": 110.0, "exit_price": 108.0, "strategy": "EMA Crossover",
        "horizon_key": "4w", "direction": "bullish", "confidence_label": "High",
        "confidence_level": 4, "risk_reward_ratio": 2.0, "id": "T1",
        "opened_at": "2026-07-01T10:00:00+00:00", "closed_at": "2026-07-05T10:00:00+00:00",
        "explanation": "why", "close_reason": "auto (price monitor)",
    }
    closed_embed = embeds.build_closed_trade_embed(closed_trade)

    warning = {
        "trade": {"ticker": "NVDA", "strategy": "EMA Crossover", "horizon_key": "4w",
                  "direction": "bullish", "confidence_label": "High", "confidence_level": 4,
                  "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "id": "T1"},
        "near_which": "take-profit", "sl_dist_pct": 8.0, "tp_dist_pct": 1.2, "current_price": 108.7,
    }
    near_embed = embeds.build_near_close_embed(warning)

    for e in (scan_embed, closed_embed, near_embed):
        assert e.timestamp is not None
    disclaimers = {e.footer.text.split(" · plan ")[0] for e in (scan_embed, closed_embed, near_embed)}
    assert len(disclaimers) == 1
    assert "plan 12345678" in scan_embed.footer.text
    assert " · plan " not in closed_embed.footer.text  # no plan_id passed for a legacy trade dict
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_embeds_v3.py -v -k footer`
Expected: FAIL — `AttributeError` / footer text mismatch (each builder currently sets its own distinct footer, no `.timestamp`).

- [ ] **Step 3: Implement**

Add to `embed_theme.py` (this is the item deferred from Task B1's Interfaces list):

```python
import discord as _discord  # already imported as `discord` at module top in embeds.py callers; local alias avoids
                             # shadowing if this module is ever imported star-style -- kept explicit here.

DISCLAIMER = "Technical signal only, based on today's still-developing daily candle -- not financial advice."


def apply_footer(embed, *, plan_id: str | None = None) -> None:
    """Stamps embed.timestamp = now (UTC) and a single shared footer
    format across every embed builder in embeds.py: the disclaimer,
    plus ' · plan {first 8 chars of plan_id}' when a plan_id is given.
    Mutates embed in place; returns None so call sites read as a plain
    statement (`apply_footer(embed, plan_id=...)`) rather than needing
    to reassign anything."""
    import discord
    embed.timestamp = discord.utils.utcnow()
    text = DISCLAIMER
    if plan_id:
        text = f"{DISCLAIMER} · plan {plan_id[:8]}"
    embed.set_footer(text=text)
```

Remove the real top-level `import discord as _discord` line above (it was written only to flag the shadowing consideration for the reviewer; the actual file uses the plain `import discord` inside the function body as shown, matching every other module's lazy-import style is unnecessary here — `embed_theme.py` should just `import discord` once at the top like `embeds.py` does). Corrected final module-level state: `embed_theme.py` gains `import discord` at the top (it already has it from Task B1) and `apply_footer`/`DISCLAIMER` as shown, without the stray alias line.

In `embeds.py`:
- `build_embed`: replace the final `embed.set_footer(text="Technical signal only...")` line with:
  ```python
  theme.apply_footer(embed, plan_id=v2.plan_id if v2 else None)
  ```
- `build_closed_trade_embed`: replace `embed.set_footer(text=f"Trade ID: {trade['id']}")` with:
  ```python
  theme.apply_footer(embed, plan_id=trade.get("plan_id"))
  ```
  (legacy trade dicts have no `plan_id` key → `.get` returns `None` → no `· plan` suffix, matching the test above.)
- `build_near_close_embed`: replace `embed.set_footer(text=f"Trade ID: {t['id']} -- use !trade {t['id']} for full detail")` with:
  ```python
  theme.apply_footer(embed, plan_id=t.get("plan_id"))
  embed.add_field(name="Trade ID", value=f"`{t['id']}` — use `!trade {t['id']}` for full detail", inline=False)
  ```
  (the trade-ID-and-usage-hint text moves into a field since the footer format is now fixed/shared — this preserves the information, just relocated.)

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_embeds_v3.py -q`
Expected: all pass. Full suite: `python -m pytest tests/ -q` — green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/embed_theme.py swingbot/core/scanning/embeds.py tests/test_embeds_v3.py
git commit -m "feat: unified embed footer/timestamp"
```

---

# Phase B2 — Interactive views (Tasks B9–B14)

### Task B9: `PlanActionView` skeleton + Chart button

**Files:**
- Create: `swingbot/commands/views.py`
- Test: `tests/test_views.py`

**Interfaces:**
- Produces: `class PlanActionView(discord.ui.View)` — `__init__(self, plan_id: str, author_id: int | None, *, timeout=180)`; author-lock via `interaction_check` (non-author → ephemeral `"Not your panel."`; `author_id=None` means any user passes — used by scan alerts in Task B12); `on_timeout` disables all children. Button `📊 Chart` (`custom_id="plan:chart"`): loads plan from `PlanStore`, renders its chart via `asyncio.to_thread(generate_trade_chart, ...)`, replies with the file ephemeral. Buttons added in B10/B11 follow this shape.

- [ ] **Step 1: Failing test**

```python
# tests/test_views.py
"""Unit tests for the interactive Views (PlanActionView, PlanBoardView).
No live gateway connection is used or needed -- discord.ui.View/Button
instances and their callbacks are plain Python objects once constructed;
interaction_check and button callbacks are called directly with small
stand-in Interaction objects (types.SimpleNamespace/AsyncMock), matching
discord.py's own test conventions for View unit tests."""
import types
from unittest.mock import AsyncMock

import pytest

from swingbot.commands.views import PlanActionView


def _fake_interaction(user_id: int):
    interaction = types.SimpleNamespace()
    interaction.user = types.SimpleNamespace(id=user_id)
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


@pytest.mark.asyncio
async def test_view_has_one_child_and_180s_timeout():
    view = PlanActionView("plan-123", author_id=42)
    assert view.timeout == 180
    assert len(view.children) == 1  # chart button only, until B10/B11 add more


@pytest.mark.asyncio
async def test_interaction_check_rejects_wrong_user():
    view = PlanActionView("plan-123", author_id=42)
    interaction = _fake_interaction(user_id=999)
    allowed = await view.interaction_check(interaction)
    assert allowed is False
    interaction.response.send_message.assert_awaited_once()
    _, kwargs = interaction.response.send_message.call_args
    assert kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_interaction_check_accepts_matching_user():
    view = PlanActionView("plan-123", author_id=42)
    interaction = _fake_interaction(user_id=42)
    allowed = await view.interaction_check(interaction)
    assert allowed is True
```

Add `pytest-asyncio` awareness: this repo's `pytest.ini`/`pyproject.toml` may not yet have `asyncio_mode` configured for bare `@pytest.mark.asyncio` tests. Check first:

Run: `python -c "import pytest_asyncio" `
Expected: no `ModuleNotFoundError` (pytest-asyncio is already a transitive dependency of discord.py's own test tooling in this repo's `requirements.txt`; if it prints an error, add `pytest-asyncio>=0.24` to `requirements.txt` and `pip install pytest-asyncio` before continuing — Views are the first async-callback code under test in this codebase, so this is a real first-time setup step, not boilerplate).

If `pytest.ini` does not already set `asyncio_mode`, add:

```ini
# pytest.ini (create if it doesn't exist, or append the [pytest] section)
[pytest]
asyncio_mode = auto
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_views.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.commands.views'`.

- [ ] **Step 3: Implement**

```python
# swingbot/commands/views.py
"""
Interactive discord.ui.View subclasses for the plan-centric UX: a
per-alert action panel (chart / breakdown / watch / dismiss buttons --
PlanActionView, Tasks B9-B11) and the filterable/paginated !plans board
(PlanBoardView, Tasks B13-B14). Both follow the exact author-lock/
timeout/on_timeout-disables-children pattern TradesPaginator already
established (swingbot/commands/trades.py:83) -- the ONLY other View in
this codebase before this file existed -- so a user who has learned
"only the person who ran the command can page through it" from !trades
gets the identical mental model here.
"""
import asyncio
import os

import discord

from swingbot import config
from swingbot.core.data import get_currency_symbol, get_daily_data
from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS, generate_trade_chart
from swingbot.core.plan_store import PlanStore
from swingbot.core.strategy import HORIZONS

_plan_store = PlanStore()


class PlanActionView(discord.ui.View):
    """
    One action panel per posted plan: Chart (this task), Breakdown
    (Task B10), Watch/Dismiss (Task B11). `author_id=None` relaxes the
    lock to "any user may click" -- used when this view is attached to
    a scan alert (Task B12), where there is no single "author" (nobody
    ran a command; the bot posted it on its own schedule) and locking
    it to one person would make the buttons useless to everyone else
    watching the channel.
    """

    def __init__(self, plan_id: str, author_id: int | None, *, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.plan_id = plan_id
        self.author_id = author_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id is None or interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("Not your panel.", ephemeral=True)
        return False

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="📊 Chart", style=discord.ButtonStyle.primary, custom_id="plan:chart")
    async def chart_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        plan = _plan_store.get(self.plan_id)
        if plan is None:
            await interaction.followup.send("This plan no longer exists (closed/cancelled and pruned).", ephemeral=True)
            return
        try:
            df = await asyncio.to_thread(get_daily_data, plan.ticker)
        except Exception as exc:
            await interaction.followup.send(f"Could not fetch price data for {plan.ticker}: {exc}", ephemeral=True)
            return
        h = HORIZONS.get(plan.horizon_key, {})
        filename = f"{plan.ticker}_{plan.plan_id}_panel.png"
        try:
            chart_path = await asyncio.to_thread(
                generate_trade_chart,
                plan.ticker, df, plan.trigger_price, plan.stop_loss, plan.tp1,
                plan.direction, plan.strategy, h.get("label", plan.horizon_key), config.TRADE_CHART_DIR,
                filename=filename, currency_symbol=get_currency_symbol(plan.ticker, config.CURRENCY_SYMBOL),
                target2=plan.tp2, trendline_lookback=h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS),
                horizon=h, plan=plan,
            )
        except Exception as exc:
            await interaction.followup.send(f"Chart render failed: {exc}", ephemeral=True)
            return
        await interaction.followup.send(
            file=discord.File(chart_path, filename=os.path.basename(chart_path)), ephemeral=True,
        )
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_views.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/views.py tests/test_views.py pytest.ini
git commit -m "feat: PlanActionView with chart button"
```

### Task B10: Breakdown button

**Files:** Modify `swingbot/commands/views.py`; test `tests/test_views.py`

**Interfaces:**
- Produces: button `🔍 Breakdown` (`custom_id="plan:breakdown"`) — ephemeral embed showing `quality_breakdown` (one line per `(component, points)`), `badge_stats` verbatim, follow-score breakdown (B6), and `status_history` timeline (last 5 transitions, `"{ts} {from}→{to} ({reason})"`). Pure helper `breakdown_embed(plan) -> discord.Embed` is the testable unit.

- [ ] **Step 1: Failing test**

```python
# tests/test_views.py (append)
import datetime as dt

from swingbot.commands.views import breakdown_embed


def _fixture_plan():
    return types.SimpleNamespace(
        plan_id="abcd1234-plan", ticker="NVDA", tier="A", badge="VALIDATED", quality_score=82,
        quality_breakdown=[("Trend alignment", 20), ("Volume confirmation", 15), ("Multi-strategy confluence", 47)],
        badge_stats={"status": "VALIDATED", "n": 206, "win_rate": 81.6, "expectancy_r": 0.42, "window": "2024-2025"},
        regime_aligned=True, created_at="2026-07-11",
        status="ACTIVE",
        status_history=[
            {"status": "PENDING", "reason": None, "at": "2026-07-10T09:00:00+00:00"},
            {"status": "ACTIVE", "reason": "trigger_hit", "at": "2026-07-11T10:15:00+00:00"},
        ],
    )


def test_breakdown_embed_has_one_field_per_section_and_every_quality_line():
    embed = breakdown_embed(_fixture_plan())
    names = [f.name for f in embed.fields]
    assert any("quality" in n.lower() for n in names)
    assert any("track record" in n.lower() or "badge" in n.lower() for n in names)
    assert any("follow" in n.lower() for n in names)
    assert any("timeline" in n.lower() or "status" in n.lower() for n in names)
    quality_field = next(f for f in embed.fields if "quality" in f.name.lower())
    for label, pts in _fixture_plan().quality_breakdown:
        assert label in quality_field.value and str(pts) in quality_field.value


@pytest.mark.asyncio
async def test_breakdown_button_sends_ephemeral():
    view = PlanActionView("abcd1234-plan", author_id=1)
    interaction = _fake_interaction(user_id=1)
    import swingbot.commands.views as views_mod
    views_mod._plan_store.get = lambda pid: _fixture_plan()
    await view.breakdown_button.callback(interaction)
    interaction.response.send_message.assert_awaited_once()
    _, kwargs = interaction.response.send_message.call_args
    assert kwargs.get("ephemeral") is True
    assert "embed" in kwargs
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_views.py -v -k breakdown`
Expected: FAIL — `ImportError: cannot import name 'breakdown_embed'`.

- [ ] **Step 3: Implement**

Append to `views.py`:

```python
def breakdown_embed(plan) -> discord.Embed:
    """Pure renderer (plan in, Embed out) so this is unit-testable
    without any Interaction plumbing -- the button callback below is a
    thin wrapper that just calls this and sends it ephemeral."""
    from swingbot.core.analytics.rank import follow_score, follow_breakdown
    import datetime as dt

    embed = discord.Embed(title=f"🔍 Breakdown — {plan.ticker} ({plan.tier}/{plan.badge})",
                          color=discord.Color.blurple())

    quality_lines = "\n".join(f"{label}: {pts:+d}" for label, pts in (plan.quality_breakdown or [])) or "no components recorded"
    embed.add_field(name=f"📐 Quality score ({plan.quality_score}/100)", value=quality_lines, inline=False)

    stats = plan.badge_stats or {}
    badge_lines = (
        f"Status: {stats.get('status', plan.badge)}\n"
        f"OOS N={stats.get('n', 0)}, WR {stats.get('win_rate', 0):.1f}%, "
        f"ExpR {stats.get('expectancy_r', 0):+.3f}\nWindow: {stats.get('window', 'n/a')}"
    )
    embed.add_field(name="🏷️ Badge / track record", value=badge_lines, inline=False)

    today = dt.date.today()
    score = follow_score(plan, today=today)
    breakdown = follow_breakdown(plan, today)
    breakdown_lines = "\n".join(f"{label}: +{pts:.0f}" for label, pts in breakdown) or "no components"
    embed.add_field(name=f"🧭 Follow score ({score:.0f})", value=breakdown_lines, inline=False)

    history = (plan.status_history or [])[-5:]
    if history:
        timeline_lines = []
        for i, entry in enumerate(history):
            frm = history[i - 1]["status"] if i > 0 else "—"
            timeline_lines.append(f"{entry.get('at', '?')} {frm}→{entry['status']} ({entry.get('reason') or 'n/a'})")
        timeline = "\n".join(timeline_lines)
    else:
        timeline = "No transitions recorded yet."
    embed.add_field(name="🕒 Status timeline", value=timeline[:1024], inline=False)

    return embed
```

Add the button to `PlanActionView`:

```python
    @discord.ui.button(label="🔍 Breakdown", style=discord.ButtonStyle.secondary, custom_id="plan:breakdown")
    async def breakdown_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        plan = _plan_store.get(self.plan_id)
        if plan is None:
            await interaction.response.send_message("This plan no longer exists.", ephemeral=True)
            return
        await interaction.response.send_message(embed=breakdown_embed(plan), ephemeral=True)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_views.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/views.py tests/test_views.py
git commit -m "feat: quality/lifecycle breakdown button"
```

### Task B11: Watch / Dismiss buttons

**Files:** Modify `swingbot/commands/views.py`; test `tests/test_views.py`

**Interfaces:**
- Produces: `⭐ Watch` toggles the plan id in `data/starred_plans.json` (list of ids, `jsonio`-persisted; module fns `star_plan(plan_id)`, `unstar_plan(plan_id)`, `starred_ids() -> set`); `🔕 Dismiss` removes the view from the message (`edit(view=None)`) — the embed stays. Starred plans get a `⭐` prefix and sort-first within equal follow scores on the board (B15).

- [ ] **Step 1: Failing test**

```python
# tests/test_views.py (append)
from swingbot.commands.views import star_plan, unstar_plan, starred_ids


def test_star_unstar_roundtrip(tmp_path, monkeypatch):
    star_path = str(tmp_path / "starred_plans.json")
    monkeypatch.setattr("swingbot.commands.views._STARRED_PATH", star_path)
    assert starred_ids() == set()
    star_plan("p1")
    star_plan("p2")
    assert starred_ids() == {"p1", "p2"}
    unstar_plan("p1")
    assert starred_ids() == {"p2"}
    # A fresh read (new call, not a cached object) still reflects disk state.
    assert starred_ids() == {"p2"}


@pytest.mark.asyncio
async def test_watch_button_toggles_star(tmp_path, monkeypatch):
    star_path = str(tmp_path / "starred_plans.json")
    monkeypatch.setattr("swingbot.commands.views._STARRED_PATH", star_path)
    view = PlanActionView("plan-x", author_id=1)
    interaction = _fake_interaction(user_id=1)
    await view.watch_button.callback(interaction)
    assert "plan-x" in starred_ids()
    await view.watch_button.callback(interaction)
    assert "plan-x" not in starred_ids()


@pytest.mark.asyncio
async def test_dismiss_button_removes_view_keeps_embed():
    view = PlanActionView("plan-x", author_id=1)
    interaction = _fake_interaction(user_id=1)
    await view.dismiss_button.callback(interaction)
    interaction.response.edit_message.assert_awaited_once_with(view=None)
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_views.py -v -k "star or dismiss or watch"`
Expected: FAIL — `ImportError: cannot import name 'star_plan'`.

- [ ] **Step 3: Implement**

Append to `views.py` (imports `jsonio` at the top: `from swingbot.core.jsonio import atomic_write_json, read_json`):

```python
_STARRED_PATH = os.path.join(config.DATA_DIR, "starred_plans.json")


def starred_ids() -> set:
    return set(read_json(_STARRED_PATH, []))


def star_plan(plan_id: str) -> None:
    ids = starred_ids()
    ids.add(plan_id)
    atomic_write_json(_STARRED_PATH, sorted(ids))


def unstar_plan(plan_id: str) -> None:
    ids = starred_ids()
    ids.discard(plan_id)
    atomic_write_json(_STARRED_PATH, sorted(ids))
```

Add the two buttons to `PlanActionView`:

```python
    @discord.ui.button(label="⭐ Watch", style=discord.ButtonStyle.secondary, custom_id="plan:watch")
    async def watch_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.plan_id in starred_ids():
            unstar_plan(self.plan_id)
            await interaction.response.send_message("Unstarred.", ephemeral=True)
        else:
            star_plan(self.plan_id)
            await interaction.response.send_message("⭐ Starred — it'll sort first on `!plans` at equal follow score.", ephemeral=True)

    @discord.ui.button(label="🔕 Dismiss", style=discord.ButtonStyle.secondary, custom_id="plan:dismiss")
    async def dismiss_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=None)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_views.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/views.py tests/test_views.py
git commit -m "feat: watch/dismiss plan buttons"
```

### Task B12: Views attached to scan alerts

**Files:**
- Modify: `swingbot/commands/scanning.py` (`_send_alerts` :204 message send)
- Test: `tests/test_views.py`

**Interfaces:**
- Produces: every alert message for a plan-carrying item is sent with `view=PlanActionView(plan.plan_id, author_id=None)` (any user may click). Legacy alerts get no view.

- [ ] **Step 1: Failing test**

```python
# tests/test_views.py (append)
@pytest.mark.asyncio
async def test_any_author_id_none_interaction_check_true_for_any_user():
    view = PlanActionView("plan-x", author_id=None)
    for uid in (1, 2, 999999):
        assert await view.interaction_check(_fake_interaction(user_id=uid)) is True
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_views.py -v -k author_id_none`
Expected: PASS already (this is the same code path Task B9 wrote — `author_id is None` was handled from the start). This step exists to *document and lock in* the contract Task B12 depends on before wiring it into `scanning.py`; nothing to fix here.

- [ ] **Step 3: Implement**

In `swingbot/commands/scanning.py`, update `_send_alerts` (already changed in Task B5 to unpack 3-tuples) to attach a view when a plan is present:

```python
async def _send_alerts(destination, alerts):
    from swingbot.commands.views import PlanActionView

    for embed, chart_path, plan in _ordered_alerts(alerts):
        view = PlanActionView(plan.plan_id, author_id=None) if plan is not None else None
        kwargs = {"embed": embed}
        if chart_path:
            kwargs["file"] = discord.File(chart_path, filename=os.path.basename(chart_path))
        if view is not None:
            kwargs["view"] = view
        msg = await destination.send(**kwargs)
        if view is not None:
            view.message = msg
```

Import `PlanActionView` lazily inside the function (as shown) rather than at module top, to avoid a circular import: `views.py` imports from `swingbot.core.plan_store`, and `scanning.py` is imported very early during bot startup (`bot_core.py` registers commands from every `swingbot/commands/*` module) — a top-level `from swingbot.commands.views import PlanActionView` in `scanning.py` is safe today (no cycle exists), but the lazy import documents the intent and costs nothing at this call frequency (once per alert message, not per scan tick).

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_views.py tests/test_embeds_v3.py -q`
Expected: all pass. Full suite: `python -m pytest tests/ -q` — green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/scanning.py tests/test_views.py
git commit -m "feat: interactive scan alerts"
```

### Task B13: `PlanBoardView` filters

**Files:** Modify `swingbot/commands/views.py`; test `tests/test_views.py`

**Interfaces:**
- Produces: `class PlanBoardView(discord.ui.View)` — `discord.ui.Select` "Status" (options All/PENDING/ACTIVE/PARTIAL), Select "Tier" (All/A/B/C), Select "Badge" (All/VALIDATED/WEAK), `🔄 Refresh` button. Holds a `render_fn(status, tier, badge) -> tuple[str, discord.Embed]` callback supplied by `plans.py`; selection re-renders via `interaction.response.edit_message`.

- [ ] **Step 1: Failing test**

```python
# tests/test_views.py (append)
from swingbot.commands.views import PlanBoardView


def _stub_render_fn(calls):
    def render(status, tier, badge):
        calls.append((status, tier, badge))
        return "content", discord.Embed(title="board")
    return render


@pytest.mark.asyncio
async def test_plan_board_view_has_4_children_and_apply_calls_render_fn():
    calls = []
    view = PlanBoardView(_stub_render_fn(calls), author_id=1)
    assert len(view.children) == 4  # 3 selects + 1 refresh button
    await view._apply(status="ACTIVE", tier="A", badge="All")
    assert calls == [("ACTIVE", "A", "All")]
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_views.py -v -k plan_board`
Expected: FAIL — `ImportError: cannot import name 'PlanBoardView'`.

- [ ] **Step 3: Implement**

Append to `views.py`:

```python
class PlanBoardView(discord.ui.View):
    """
    Filterable !plans board (Task B15 supplies render_fn). Three
    dropdowns hold the current status/tier/badge filter state; every
    selection change and the Refresh button all funnel through the
    same `_apply` method, which calls `render_fn` and edits the
    message in place -- one render path regardless of which control
    triggered it, so there's no risk of the three selects drifting out
    of sync with each other.
    """

    def __init__(self, render_fn, author_id: int, *, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.render_fn = render_fn
        self.author_id = author_id
        self.status = "All"
        self.tier = "All"
        self.badge = "All"
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("Not your panel.", ephemeral=True)
        return False

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def _apply(self, *, status=None, tier=None, badge=None, interaction: discord.Interaction = None):
        if status is not None:
            self.status = status
        if tier is not None:
            self.tier = tier
        if badge is not None:
            self.badge = badge
        content, embed = self.render_fn(self.status, self.tier, self.badge)
        if interaction is not None:
            await interaction.response.edit_message(content=content, embed=embed, view=self)
        return content, embed

    @discord.ui.select(
        placeholder="Status: All", custom_id="board:status",
        options=[discord.SelectOption(label=v, value=v) for v in ("All", "PENDING", "ACTIVE", "PARTIAL")],
    )
    async def status_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self._apply(status=select.values[0], interaction=interaction)

    @discord.ui.select(
        placeholder="Tier: All", custom_id="board:tier",
        options=[discord.SelectOption(label=v, value=v) for v in ("All", "A", "B", "C")],
    )
    async def tier_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self._apply(tier=select.values[0], interaction=interaction)

    @discord.ui.select(
        placeholder="Badge: All", custom_id="board:badge",
        options=[discord.SelectOption(label=v, value=v) for v in ("All", "VALIDATED", "WEAK")],
    )
    async def badge_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self._apply(badge=select.values[0], interaction=interaction)

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary, custom_id="board:refresh")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply(interaction=interaction)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_views.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/views.py tests/test_views.py
git commit -m "feat: plan board filter view"
```

### Task B14: Board pagination

**Files:** Modify `swingbot/commands/views.py`; test `tests/test_views.py`

**Interfaces:**
- Produces: `PlanBoardView` gains Prev/Next buttons reusing the `TradesPaginator` page logic (extract shared `paginate(items, page, per_page) -> tuple[list, int, int]` into `views.py`; `TradesPaginator` may adopt it later — do not modify `trades.py` here). Page size 8 plans.

- [ ] **Step 1: Failing test**

```python
# tests/test_views.py (append)
from swingbot.commands.views import paginate


def test_paginate_middle_page():
    items, page_num, max_page = paginate(list(range(20)), page=2, per_page=8)
    assert items == [16, 17, 18, 19]
    assert page_num == 2
    assert max_page == 2  # 0-indexed: pages 0,1,2 for 20 items at 8/page


def test_paginate_clamps_out_of_range_page():
    items, page_num, max_page = paginate(list(range(5)), page=99, per_page=8)
    assert items == [0, 1, 2, 3, 4]
    assert page_num == 0
    assert max_page == 0


@pytest.mark.asyncio
async def test_plan_board_view_has_6_children_after_pagination():
    calls = []
    view = PlanBoardView(_stub_render_fn(calls), author_id=1, items=list(range(20)))
    assert len(view.children) == 6  # 3 selects + refresh + prev + next
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_views.py -v -k paginate`
Expected: FAIL — `ImportError: cannot import name 'paginate'`.

- [ ] **Step 3: Implement**

Append near the top of `views.py` (above `PlanBoardView`, used by it):

```python
PLAN_BOARD_PAGE_SIZE = 8


def paginate(items: list, page: int, per_page: int) -> tuple:
    """Same slicing/clamping semantics as TradesPaginator's inline page
    logic (trades.py:83-113), extracted here so PlanBoardView can reuse
    it without duplicating the arithmetic. TradesPaginator itself is
    intentionally left untouched by this task -- a follow-up could have
    it import this helper too, but that's out of scope here."""
    max_page = max(0, (len(items) - 1) // per_page) if items else 0
    page = max(0, min(page, max_page))
    start = page * per_page
    return items[start:start + per_page], page, max_page
```

Update `PlanBoardView.__init__` to accept `items` and add Prev/Next:

```python
    def __init__(self, render_fn, author_id: int, *, items: list = None, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.render_fn = render_fn
        self.author_id = author_id
        self.status = "All"
        self.tier = "All"
        self.badge = "All"
        self.items = items or []
        self.page = 0
        self.message: discord.Message | None = None
```

```python
    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, custom_id="board:prev", row=1)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        await self._apply(interaction=interaction)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="board:next", row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        _, _, max_page = paginate(self.items, self.page, PLAN_BOARD_PAGE_SIZE)
        self.page = min(max_page, self.page + 1)
        await self._apply(interaction=interaction)
```

`row=1` places Prev/Next on a second action row, below the three selects + Refresh (each select consumes its own row automatically; `refresh_button` shares row 0 with them by default unless it also collides — discord.py auto-assigns rows for components without an explicit `row`, but since the three `discord.ui.select` decorators already claim rows 0-2, `refresh_button` lands on row 3 automatically; explicitly setting `row=1` on Prev/Next only matters relative to Refresh, so also set `row=3` on `refresh_button` here for a clean two-row layout: selects on rows 0-2, Refresh+Prev+Next together on row 3). Add `row=3` to the existing `refresh_button` decorator from Task B13 and use `row=3` (not `row=1`) on both Prev/Next above.

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_views.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/views.py tests/test_views.py
git commit -m "feat: plan board pagination"
```

---

# Phase B3 — Commands (Tasks B15–B25)

### Task B15: `!plans` live ranked board

**Files:**
- Modify: `swingbot/commands/plans.py` (the v2 lifecycle board, assumed to exist from plan-engine-v2's own track — see this Part's "Notes on assumptions")
- Test: `tests/test_plans_board.py`

**Interfaces:**
- Produces: `!plans` with no args renders the live board: plans from `PlanStore.all()` with status in `{PENDING, ACTIVE, PARTIAL}`, ordered by `rank_plans` (starred plans sort first within an equal integer-rounded follow score), one line each: `"{⭐?}{tier_chip}{badge_chip} {ticker} {direction} · {status} · follow {score} · entry {trigger} SL {sl} TP1 {tp1}"`, grouped under status headings, wrapped in `PlanBoardView`. Pure renderer `render_board(plans, *, status, tier, badge, page, today) -> tuple[str, discord.Embed]` is the testable unit and the `render_fn` for B13.

- [ ] **Step 1: Failing test**

```python
# tests/test_plans_board.py
import datetime as dt
import types

from swingbot.commands.plans import render_board

TODAY = dt.date(2026, 7, 11)


def _plan(ticker, status, badge="VALIDATED", tier="A", quality_score=80, plan_id=None, direction="bullish"):
    return types.SimpleNamespace(
        plan_id=plan_id or f"{ticker}-{status}", ticker=ticker, status=status, badge=badge, tier=tier,
        quality_score=quality_score, direction=direction, entry_type="market",
        trigger_price=100.0, stop_loss=95.0, tp1=110.0, tp2=None,
        regime_aligned=True, created_at="2026-07-11",
    )


def test_render_board_groups_by_status_and_ranks_within_group():
    plans = [
        _plan("AAA", "PENDING", quality_score=20),
        _plan("BBB", "ACTIVE", quality_score=90),
        _plan("CCC", "PARTIAL", quality_score=50),
        _plan("DDD", "CLOSED"),   # excluded -- not in {PENDING, ACTIVE, PARTIAL}
    ]
    content, embed = render_board(plans, status="All", tier="All", badge="All", page=0, today=TODAY)
    assert "DDD" not in content
    assert "PENDING" in content and "ACTIVE" in content and "PARTIAL" in content
    # Within-group order isn't cross-group -- each status heading has exactly
    # its own plan(s); this fixture has one plan per status so ordering
    # inside a group can't be asserted here beyond "each ticker appears
    # under its own status heading", verified by substring position checks.
    pending_pos = content.index("PENDING")
    active_pos = content.index("ACTIVE")
    assert content.index("AAA", pending_pos) > pending_pos
    assert content.index("BBB", active_pos) > active_pos


def test_render_board_filters_by_tier():
    plans = [_plan("AAA", "ACTIVE", tier="A"), _plan("BBB", "ACTIVE", tier="B")]
    content, _ = render_board(plans, status="All", tier="A", badge="All", page=0, today=TODAY)
    assert "AAA" in content and "BBB" not in content
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_plans_board.py -v`
Expected: FAIL — `ModuleNotFoundError` (if `plans.py` doesn't exist yet on the branch this executes against) or `ImportError: cannot import name 'render_board'` (if the v2 lifecycle board already landed without this function). Either way, nothing to render yet.

- [ ] **Step 3: Implement**

Add to `swingbot/commands/plans.py` (alongside whatever the v2 lifecycle board already put there — this task does not remove the historical from:/to: query mode, see Task B16):

```python
import discord

from swingbot.core.analytics.rank import rank_plans
from swingbot.core.scanning import embed_theme as theme
from swingbot.commands.views import starred_ids, paginate, PLAN_BOARD_PAGE_SIZE

LIVE_STATUSES = ("PENDING", "ACTIVE", "PARTIAL")


def _plan_line(plan) -> str:
    from swingbot.core.analytics.rank import follow_score
    import datetime as dt

    star = "⭐" if plan.plan_id in starred_ids() else ""
    score = follow_score(plan, today=dt.date.today())
    direction_word = "LONG" if plan.direction == "bullish" else "SHORT"
    tp2_bit = f" TP2 {plan.tp2:.2f}" if plan.tp2 is not None else ""
    return (
        f"{star}{theme.tier_chip(plan.tier)}{theme.badge_chip(plan.badge)} {plan.ticker} {direction_word} · "
        f"{plan.status} · follow {score:.0f} · entry {plan.trigger_price:.2f} SL {plan.stop_loss:.2f} "
        f"TP1 {plan.tp1:.2f}{tp2_bit}"
    )


def render_board(plans: list, *, status: str, tier: str, badge: str, page: int, today=None) -> tuple:
    """Pure renderer: a fixed list of TradePlanV2s (or v2-shaped stand-
    ins) in, (content_str, discord.Embed) out. Called directly by
    !plans (Task B15/B16) and as PlanBoardView's render_fn (Task B13).
    Filtering happens here, BEFORE ranking and BEFORE pagination, so
    the page count in the footer always reflects the filtered set, not
    the whole store."""
    live = [p for p in plans if p.status in LIVE_STATUSES]
    if status != "All":
        live = [p for p in live if p.status == status]
    if tier != "All":
        live = [p for p in live if p.tier == tier]
    if badge != "All":
        live = [p for p in live if p.badge == badge]

    ranked = rank_plans(live, today=today)
    starred = starred_ids()
    # Starred-first tiebreak within an equal ROUNDED follow score -- exact
    # float ties are rare, so comparing round(score) (not the raw float)
    # is what actually makes "starred sorts first at equal follow score"
    # observable rather than a purely theoretical rule that never fires.
    from swingbot.core.analytics.rank import follow_score
    import datetime as _dt
    _today = today or _dt.date.today()
    ranked.sort(key=lambda p: (-round(follow_score(p, today=_today)), p.plan_id not in starred))

    page_items, page_num, max_page = paginate(ranked, page, PLAN_BOARD_PAGE_SIZE)

    lines_by_status: dict = {s: [] for s in LIVE_STATUSES}
    for p in page_items:
        lines_by_status[p.status].append(_plan_line(p))

    body_parts = []
    for s in LIVE_STATUSES:
        if lines_by_status[s]:
            body_parts.append(f"**{s}**\n" + "\n".join(lines_by_status[s]))
    body = "\n\n".join(body_parts) if body_parts else "No live plans match this filter."

    content = (
        f"📋 **Live plans** — {len(ranked)} match (status={status}, tier={tier}, badge={badge}), "
        f"page {page_num + 1}/{max_page + 1}\n\n{body}"
    )
    embed = discord.Embed(
        title="📋 Live Plans Board", description=content[:4000],
        color=discord.Color.blurple(),
    )
    return content, embed


@bot.group(name="plans", invoke_without_command=True)
async def plans_cmd(ctx, *args: str):
    parsed = _parse_board_args(args)   # Task B16
    if parsed.get("legacy"):
        await _plans_historical(ctx, parsed)
        return

    plans = _plan_store.all()
    content, embed = render_board(
        plans, status=parsed.get("status", "All"), tier=parsed.get("tier", "All"),
        badge=parsed.get("badge", "All"), page=0,
    )
    view = views_mod.PlanBoardView(
        lambda status, tier, badge: render_board(plans, status=status, tier=tier, badge=badge, page=0),
        author_id=ctx.author.id, items=plans,
    )
    view.status, view.tier, view.badge = parsed.get("status", "All"), parsed.get("tier", "All"), parsed.get("badge", "All")
    view.message = await ctx.send(content, embed=embed, view=view)
```

`bot`, `_plan_store` (a module-level `PlanStore()`), and `views_mod` (`import swingbot.commands.views as views_mod`) are assumed already present in `plans.py` from plan-engine-v2's own board task — add the missing imports at the top of the file if they are not already there.

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_plans_board.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/plans.py tests/test_plans_board.py
git commit -m "feat: live ranked !plans board"
```

### Task B16: `!plans` arguments

**Files:** Modify `swingbot/commands/plans.py`; test `tests/test_plans_board.py`

**Interfaces:**
- Produces: `!plans [status] [tier:A|B|C] [badge:validated|weak] [TICKER]` argument parsing (`_parse_board_args(args) -> dict`, case-insensitive); the historical query mode (existing behavior with dates/ticker per the current `plans_cmd`) still triggers whenever `from:`/`to:` args are present — zero regression.

- [ ] **Step 1: Failing test**

```python
# tests/test_plans_board.py (append)
from swingbot.commands.plans import _parse_board_args


def test_parse_board_args_status_tier_ticker():
    parsed = _parse_board_args(("active", "tier:a", "NVDA"))
    assert parsed == {"status": "ACTIVE", "tier": "A", "ticker": "NVDA"}


def test_parse_board_args_badge():
    parsed = _parse_board_args(("badge:validated",))
    assert parsed["badge"] == "VALIDATED"


def test_parse_board_args_legacy_date_mode():
    parsed = _parse_board_args(("from:2026-01-01",))
    assert parsed == {"legacy": True}
    parsed2 = _parse_board_args(("to:2026-06-30", "NVDA"))
    assert parsed2.get("legacy") is True


def test_parse_board_args_empty():
    assert _parse_board_args(()) == {}
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_plans_board.py -v -k parse_board_args`
Expected: FAIL — `ImportError: cannot import name '_parse_board_args'`.

- [ ] **Step 3: Implement**

Add to `plans.py`:

```python
_VALID_STATUSES = {"PENDING", "ACTIVE", "PARTIAL", "CLOSED", "CANCELLED", "ALL"}
_VALID_TIERS = {"A", "B", "C"}
_VALID_BADGES = {"VALIDATED", "WEAK"}


def _parse_board_args(args: tuple) -> dict:
    """Case-insensitive board-mode arg parser for !plans. Returns
    {"legacy": True} the instant a from:/to: token is seen -- the
    historical query mode takes over entirely in that case (dates and
    board filters were never meant to compose; the old !plans dates
    syntax predates this board and must keep working unmodified for
    every existing user habit)."""
    parsed: dict = {}
    for token in args:
        tl = token.lower()
        if tl.startswith("from:") or tl.startswith("to:"):
            return {"legacy": True}
        if tl.startswith("tier:"):
            val = tl[5:].upper()
            if val in _VALID_TIERS:
                parsed["tier"] = val
            continue
        if tl.startswith("badge:"):
            val = tl[6:].upper()
            if val in _VALID_BADGES:
                parsed["badge"] = val
            continue
        if tl.upper() in _VALID_STATUSES and tl.upper() != "ALL":
            parsed["status"] = tl.upper()
            continue
        # Anything else is treated as a ticker (legacy positional arg) --
        # both the board mode (Task B15, filtered by ticker=... below in
        # a follow-up refinement if needed) and the legacy historical
        # mode already accept a bare ticker token.
        parsed["ticker"] = token.upper()
    return parsed
```

Update `plans_cmd`'s call to `render_board` to also filter by `parsed.get("ticker")` (add a ticker filter identical in shape to the tier/badge filters already in `render_board`, applied in the same place — `if ticker: live = [p for p in live if p.ticker == ticker]`).

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_plans_board.py -q`
Expected: all pass. Confirm zero regression on the historical mode: `python -m pytest tests/ -q -k plans` — green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/plans.py tests/test_plans_board.py
git commit -m "feat: !plans filters"
```

### Task B17: `!top`

**Files:**
- Create: `swingbot/commands/stats.py` (new cog-style module, registered in `bot_core.py` like existing command modules — see `bot.py`'s or `bot_core.py`'s `import swingbot.commands.X` list)
- Test: `tests/test_stats_commands.py`

**Interfaces:**
- Produces: `!top [n]` (default `config.DIGEST_MAX_PLANS`) — the n highest-`follow_score` PENDING/ACTIVE plans as compact embeds (B3 layout) each with its follow-breakdown line and `PlanActionView`. Pure helper `top_plans(plans, n, today) -> list` reused by the digest (B37).

- [ ] **Step 1: Failing test**

```python
# tests/test_stats_commands.py
"""Unit tests for the new !top/!stats/!lessons/!calibration/!journal
commands. Pure-renderer functions are tested directly; command
callbacks are exercised only where they hold real branching logic
(argument parsing) -- Discord I/O itself is not re-tested here (that's
what tests/test_views.py's Interaction stand-ins cover for buttons)."""
import datetime as dt
import types

from swingbot.commands.stats import top_plans

TODAY = dt.date(2026, 7, 11)


def _plan(ticker, status="PENDING", badge="VALIDATED", quality_score=50):
    return types.SimpleNamespace(
        plan_id=f"id-{ticker}", ticker=ticker, status=status, badge=badge, tier="A",
        quality_score=quality_score, direction="bullish", entry_type="market",
        trigger_price=100.0, stop_loss=95.0, tp1=110.0, tp2=None,
        regime_aligned=True, created_at="2026-07-11",
    )


def test_top_plans_returns_n_ranked_excludes_closed():
    plans = [
        _plan("AAA", quality_score=10),
        _plan("BBB", quality_score=90),
        _plan("CCC", status="CLOSED", quality_score=100),
        _plan("DDD", status="CANCELLED", quality_score=100),
        _plan("EEE", status="ACTIVE", quality_score=60),
    ]
    top = top_plans(plans, n=2, today=TODAY)
    assert [p.ticker for p in top] == ["BBB", "EEE"]


def test_top_plans_n_larger_than_available_returns_all_eligible():
    plans = [_plan("AAA"), _plan("BBB", status="CLOSED")]
    top = top_plans(plans, n=5, today=TODAY)
    assert [p.ticker for p in top] == ["AAA"]
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_stats_commands.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.commands.stats'`.

- [ ] **Step 3: Implement**

```python
# swingbot/commands/stats.py
"""!top, !stats, !lessons, !calibration, !journal -- the analytics-facing
command surface. Every number here is read from a Plan A function or
the analytics snapshot; nothing in this module computes a stat from
raw trades itself (see this Part's Global Constraints)."""
import datetime as dt

import discord

from swingbot import config
from swingbot.bot_core import bot
from swingbot.core.analytics.rank import rank_plans
from swingbot.core.plan_store import PlanStore
from swingbot.commands.views import PlanActionView
from swingbot.core.scanning.embeds import build_embed

_plan_store = PlanStore()

LIVE_STATUSES = ("PENDING", "ACTIVE")


def top_plans(plans: list, n: int, today=None) -> list:
    """The n highest-follow_score PENDING/ACTIVE plans, ranked by
    analytics.rank.rank_plans (the one shared ordering -- see this
    Part's Global Constraints). Shared between !top (this task) and
    the daily digest (Task B37) so both ever answer "what's worth
    following right now" identically."""
    eligible = [p for p in plans if p.status in LIVE_STATUSES]
    ranked = rank_plans(eligible, today=today)
    return ranked[:max(0, n)]


@bot.command(name="top")
async def top_cmd(ctx, n: int = None):
    n = n or config.DIGEST_MAX_PLANS
    plans = _plan_store.all()
    top = top_plans(plans, n, today=dt.date.today())
    if not top:
        await ctx.send("No PENDING/ACTIVE plans right now.")
        return

    await ctx.send(f"📌 **Top {len(top)} plan(s) by follow score:**")
    for plan in top:
        # top_plans/render use TradePlanV2 objects directly, but build_embed
        # expects a ScanItem-shaped object -- construct a minimal one whose
        # .plan is this TradePlanV2 and whose other fields degrade gracefully
        # (no confluence/HTF context available outside a live scan; the
        # compact layout (Task B3) drops every field that would need it).
        item = _fake_item_from_plan(plan)
        embed = build_embed(item, "", {"closed": 0}, None, None, layout="compact")
        view = PlanActionView(plan.plan_id, author_id=ctx.author.id)
        view.message = await ctx.send(embed=embed, view=view)


def _fake_item_from_plan(plan):
    """Bridges a bare TradePlanV2 (as returned by PlanStore, with no
    ScanItem context -- there was no live scan producing this !top
    listing) into the shape build_embed expects. Only compact layout
    (Task B3) is ever used with this bridge, since it's the only layout
    that never reads item.combined_from/item.requirements/htf_info."""
    import types

    return types.SimpleNamespace(
        result=types.SimpleNamespace(ticker=plan.ticker, trend=plan.direction,
                                     strategy=plan.strategy, horizon_label=plan.horizon_key),
        plan=plan,
        conf=types.SimpleNamespace(level=3, label="n/a", score=0),
        requirements=[], combined_from=[{"strategy": plan.strategy, "horizon_key": plan.horizon_key}],
        all_requirements_met=True, htf_info=None,
    )
```

Register the module in `bot_core.py`'s (or `bot.py`'s) command-module import list — `Grep "from swingbot.commands import" swingbot/bot.py` to find the exact line and add `stats` to it, matching the existing style for `trades`, `scanning`, etc.

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_stats_commands.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/stats.py tests/test_stats_commands.py
git commit -m "feat: !top ranked plans command"
```

### Task B18: `!stats` embed

**Files:** Modify `swingbot/commands/stats.py`; test `tests/test_stats_commands.py`

**Interfaces:**
- Consumes: `snapshots.load_snapshot()` (fallback: `refresh_snapshot()` then load).
- Produces: `!stats` — embed with overall block (N, WR, expectancy R, profit factor, Sharpe, max DD, current streak), a `by tier` mini-table (ANSI block), a `by strategy` top-5 table, and the equity-curve chart image (Task B26) attached. Renderer `stats_embed(snap) -> discord.Embed` is the unit under test.

- [ ] **Step 1: Failing test**

```python
# tests/test_stats_commands.py (append)
from swingbot.commands.stats import stats_embed


def _fixture_snapshot():
    return {
        "built_at": "2026-07-11T20:00:00+00:00",
        "overall": {
            "n": 40, "wins": 28, "losses": 12, "win_rate": 70.0, "expectancy_r": 0.35,
            "profit_factor": 1.8, "sharpe": 0.6, "sortino": 0.9, "max_drawdown_pct": 12.5,
            "total_pnl": 3210.5, "streaks": {"current": 3, "current_kind": "win", "best_win_streak": 5, "worst_loss_streak": 3},
        },
        "by": {
            "tier": [
                {"key": "A", "n": 20, "wins": 16, "losses": 4, "win_rate": 80.0, "expectancy_r": 0.5, "avg_r": 0.5, "profit_factor": 2.2, "total_pnl": 2000.0},
                {"key": "B", "n": 20, "wins": 12, "losses": 8, "win_rate": 60.0, "expectancy_r": 0.2, "avg_r": 0.2, "profit_factor": 1.3, "total_pnl": 1210.5},
            ],
            "strategy": [
                {"key": "EMA Crossover", "n": 15, "wins": 11, "losses": 4, "win_rate": 73.3, "expectancy_r": 0.4, "avg_r": 0.4, "profit_factor": 2.0, "total_pnl": 1500.0},
            ],
        },
    }


def test_stats_embed_has_key_numbers():
    embed = stats_embed(_fixture_snapshot())
    joined = "\n".join(f.value for f in embed.fields) + embed.description
    assert "Win rate" in joined
    assert "70.0%" in joined
    assert "Expectancy" in joined
    assert "0.35" in joined


def test_stats_embed_none_heavy_snapshot_shows_dashes_not_none():
    empty = {
        "built_at": "2026-07-11T20:00:00+00:00",
        "overall": {"n": 0, "wins": 0, "losses": 0, "win_rate": None, "expectancy_r": None,
                    "profit_factor": None, "sharpe": None, "sortino": None, "max_drawdown_pct": None,
                    "total_pnl": 0.0, "streaks": {"current": 0, "current_kind": None, "best_win_streak": 0, "worst_loss_streak": 0}},
        "by": {"tier": [], "strategy": []},
    }
    embed = stats_embed(empty)
    joined = "\n".join(f.value for f in embed.fields) + embed.description
    assert "None" not in joined
    assert "—" in joined
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_stats_commands.py -v -k stats_embed`
Expected: FAIL — `ImportError: cannot import name 'stats_embed'`.

- [ ] **Step 3: Implement**

Append to `stats.py`:

```python
def _dash(x, fmt="{:.1f}"):
    return fmt.format(x) if x is not None else "—"


def _mini_table(rows: list, cols=("key", "n", "win_rate", "expectancy_r")) -> str:
    headers = {"key": "Group", "n": "N", "win_rate": "WR%", "expectancy_r": "ExpR"}
    header_line = " ".join(f"{headers[c]:>8s}" for c in cols)
    lines = [header_line]
    for row in rows:
        cells = []
        for c in cols:
            v = row.get(c)
            if c == "key":
                cells.append(f"{str(v):>8s}")
            elif c == "win_rate":
                cells.append(f"{_dash(v, '{:.1f}%'):>8s}")
            elif c == "expectancy_r":
                cells.append(f"{_dash(v, '{:+.2f}'):>8s}")
            else:
                cells.append(f"{v:>8}")
        lines.append(" ".join(cells))
    return "```\n" + "\n".join(lines) + "\n```"


def stats_embed(snap: dict) -> discord.Embed:
    o = snap["overall"]
    embed = discord.Embed(
        title="📐 Analytics — overall performance",
        description=(
            f"**N** {o['n']} ({o['wins']}W/{o['losses']}L)  ·  **Win rate** {_dash(o['win_rate'], '{:.1f}%')}  ·  "
            f"**Expectancy** {_dash(o['expectancy_r'], '{:+.3f}')}R  ·  **Profit factor** {_dash(o['profit_factor'], '{:.2f}')}\n"
            f"**Sharpe** {_dash(o['sharpe'], '{:.2f}')}  ·  **Sortino** {_dash(o['sortino'], '{:.2f}')}  ·  "
            f"**Max DD** {_dash(o['max_drawdown_pct'], '{:.1f}%')}  ·  **Total P&L** {o['total_pnl']:+.2f}"
        ),
        color=discord.Color.blurple(),
    )
    streak = o["streaks"]
    streak_word = streak["current_kind"] or "none"
    embed.add_field(name="🔥 Current streak", value=f"{streak['current']} {streak_word} "
                     f"(best win streak {streak['best_win_streak']}, worst loss streak {streak['worst_loss_streak']})",
                     inline=False)

    tier_rows = snap["by"].get("tier", [])
    if tier_rows:
        embed.add_field(name="By tier", value=_mini_table(tier_rows), inline=False)

    strat_rows = sorted(snap["by"].get("strategy", []), key=lambda r: r["n"], reverse=True)[:5]
    if strat_rows:
        embed.add_field(name="By strategy (top 5 by N)", value=_mini_table(strat_rows), inline=False)

    embed.set_footer(text=f"Snapshot built {snap['built_at']}")
    return embed


@bot.command(name="stats")
async def stats_cmd(ctx, period: str = "all"):
    from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot
    import asyncio

    snap = load_snapshot()
    if snap is None:
        await asyncio.to_thread(refresh_snapshot)
        snap = load_snapshot()
    if snap is None:
        await ctx.send("No analytics snapshot available yet — not enough closed trades, or the snapshot build failed. Check logs.")
        return
    embed = stats_embed(snap)
    await ctx.send(embed=embed)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_stats_commands.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/stats.py tests/test_stats_commands.py
git commit -m "feat: !stats analytics embed"
```

### Task B19: `!stats` period filters

**Files:** Modify `swingbot/commands/stats.py`; test `tests/test_stats_commands.py`

**Interfaces:**
- Produces: `!stats [7d|30d|90d|ytd|all]` — period filters closed trades by `closed_at` then computes via Plan A metrics directly (snapshot only serves `all`). `_since(period, today) -> date | None` helper.

- [ ] **Step 1: Failing test**

```python
# tests/test_stats_commands.py (append)
import datetime as dt

from swingbot.commands.stats import _since

TODAY = dt.date(2026, 7, 11)


def test_since_7d_30d_90d():
    assert _since("7d", TODAY) == TODAY - dt.timedelta(days=7)
    assert _since("30d", TODAY) == TODAY - dt.timedelta(days=30)
    assert _since("90d", TODAY) == TODAY - dt.timedelta(days=90)


def test_since_ytd_is_jan_1():
    assert _since("ytd", TODAY) == dt.date(2026, 1, 1)


def test_since_all_is_none():
    assert _since("all", TODAY) is None


def test_since_unknown_period_defaults_to_none():
    assert _since("bogus", TODAY) is None
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_stats_commands.py -v -k since`
Expected: FAIL — `ImportError: cannot import name '_since'`.

- [ ] **Step 3: Implement**

Add to `stats.py`:

```python
def _since(period: str, today: dt.date) -> "dt.date | None":
    """Start date for a !stats period filter. 'all' (and anything
    unrecognized -- degrade gracefully, never raise on a typo'd
    argument) means no filter at all: None."""
    if period == "7d":
        return today - dt.timedelta(days=7)
    if period == "30d":
        return today - dt.timedelta(days=30)
    if period == "90d":
        return today - dt.timedelta(days=90)
    if period == "ytd":
        return dt.date(today.year, 1, 1)
    return None
```

Update `stats_cmd` to branch on `period`:

```python
@bot.command(name="stats")
async def stats_cmd(ctx, period: str = "all"):
    period = period.lower()
    if period == "all":
        from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot
        import asyncio

        snap = load_snapshot()
        if snap is None:
            await asyncio.to_thread(refresh_snapshot)
            snap = load_snapshot()
        if snap is None:
            await ctx.send("No analytics snapshot available yet — not enough closed trades, or the snapshot build failed. Check logs.")
            return
        await ctx.send(embed=stats_embed(snap))
        return

    since = _since(period, dt.date.today())
    if since is None:
        await ctx.send(f"Unrecognized period `{period}`. Use one of: 7d, 30d, 90d, ytd, all.")
        return

    from swingbot.core import scan_engine
    from swingbot.core.analytics import metrics as m

    all_trades = scan_engine.trade_log.get_trades(status="all", limit=None)
    closed = [t for t in all_trades if t.get("status") in ("win", "loss")
             and t.get("closed_at", "")[:10] >= since.isoformat()]
    if not closed:
        await ctx.send(f"No closed trades in the last `{period}` window.")
        return

    embed = discord.Embed(
        title=f"📐 Analytics — last {period}",
        description=(
            f"**N** {len(closed)}  ·  **Win rate** {_dash(m.win_rate(closed), '{:.1f}%')}  ·  "
            f"**Expectancy** {_dash(m.expectancy_r(closed), '{:+.3f}')}R  ·  "
            f"**Profit factor** {_dash(m.profit_factor(closed), '{:.2f}')}"
        ),
        color=discord.Color.blurple(),
    )
    await ctx.send(embed=embed)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_stats_commands.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/stats.py tests/test_stats_commands.py
git commit -m "feat: !stats period filters"
```

### Task B20: `!lessons`

**Files:** Modify `swingbot/commands/stats.py`; test `tests/test_stats_commands.py`

**Interfaces:**
- Produces: `!lessons [n|week]` — default: last 5 journal entries as `"{outcome emoji} {ticker} {r_realized:+.2f}R — {auto_lesson}"` lines + tag cloud; `week` posts `insights.weekly_digest` messages.

- [ ] **Step 1: Failing test**

```python
# tests/test_stats_commands.py (append)
from swingbot.commands.stats import lessons_lines


def _entry(ticker, outcome, r, lesson, tags=None):
    return {"ticker": ticker, "outcome": outcome, "r_realized": r, "auto_lesson": lesson, "tags": tags or []}


def test_lessons_lines_renders_each_entry():
    entries = [
        _entry("AAA", "win", 1.5, "Clean capture: banked 90% of the available move."),
        _entry("BBB", "loss", -1.0, "Entry was wrong from the first bar — review the trigger, not the exit."),
        _entry("CCC", "scratch", 0.0, "No follow-through within the horizon — count it as rent, not error."),
    ]
    lines = lessons_lines(entries)
    assert len(lines) == 3
    assert "AAA" in lines[0] and "+1.50R" in lines[0] and "Clean capture" in lines[0]
    assert "✅" in lines[0]
    assert "❌" in lines[1]
    assert "⬜" in lines[2] or "➖" in lines[2]
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_stats_commands.py -v -k lessons_lines`
Expected: FAIL — `ImportError: cannot import name 'lessons_lines'`.

- [ ] **Step 3: Implement**

Append to `stats.py`:

```python
_OUTCOME_EMOJI = {"win": "✅", "loss": "❌", "scratch": "⬜", "timeout": "⬜"}


def lessons_lines(entries: list) -> list:
    lines = []
    for e in entries:
        emoji = _OUTCOME_EMOJI.get(e["outcome"], "➖")
        r = e.get("r_realized")
        r_str = f"{r:+.2f}R" if r is not None else "n/aR"
        lines.append(f"{emoji} {e['ticker']} {r_str} — {e['auto_lesson']}")
    return lines


def _tag_cloud(entries: list) -> str:
    from collections import Counter
    counts = Counter(tag for e in entries for tag in e.get("tags", []))
    if not counts:
        return "no tags yet"
    return " · ".join(f"`{tag}` x{n}" for tag, n in counts.most_common(10))


@bot.command(name="lessons")
async def lessons_cmd(ctx, arg: str = "5"):
    from swingbot.core.analytics.journal import JournalStore
    store = JournalStore()

    if arg.lower() == "week":
        from swingbot.core import scan_engine
        from swingbot.core.analytics.insights import weekly_digest
        import datetime as _dt

        all_trades = scan_engine.trade_log.get_trades(status="all", limit=None)
        closed = [t for t in all_trades if t.get("status") in ("win", "loss", "closed")]
        messages = weekly_digest(store.entries(), closed, today=_dt.date.today())
        for msg in messages:
            await ctx.send(msg)
        return

    try:
        n = max(1, min(25, int(arg)))
    except ValueError:
        await ctx.send(f"`{arg}` isn't a number or `week`. Usage: `!lessons [n|week]`.")
        return

    entries = store.entries()[:n]
    if not entries:
        await ctx.send("No journal entries yet.")
        return

    lines = lessons_lines(entries)
    text = "\n".join(lines) + f"\n\n**Tags:** {_tag_cloud(entries)}"
    await ctx.send(f"📖 **Last {len(entries)} journal entr{'y' if len(entries)==1 else 'ies'}:**\n{text[:1900]}")
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_stats_commands.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/stats.py tests/test_stats_commands.py
git commit -m "feat: !lessons journal command"
```

### Task B21: `!calibration`

**Files:** Modify `swingbot/commands/stats.py`; test `tests/test_stats_commands.py`

**Interfaces:**
- Produces: `!calibration` — tier-calibration table (tier / n / live WR / expected band / ✅|❌|—), decile summary line, edge-decay alert lines from `insights.edge_decay_report`, plus the calibration chart (Task B28) attached.

- [ ] **Step 1: Failing test**

```python
# tests/test_stats_commands.py (append)
from swingbot.commands.stats import calibration_lines


def test_calibration_lines_marks_failing_tier_and_drift_alert():
    tiers = [
        {"tier": "A", "n": 40, "win_rate": 60.0, "expectancy_r": 0.1, "expected_band": ">=80", "ok": False},
        {"tier": "B", "n": 5, "win_rate": None, "expectancy_r": None, "expected_band": "70-80", "ok": None},
    ]
    decay_lines = ["📉 Fibonacci: OOS WR 81.6% -> live WR 64.0% (N=25) — drift alert"]
    lines = calibration_lines(tiers, decay_lines)
    assert any("❌" in l and "A" in l for l in lines)
    assert any("—" in l and "B" in l for l in lines)
    assert any("Fibonacci" in l for l in lines)
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_stats_commands.py -v -k calibration_lines`
Expected: FAIL — `ImportError: cannot import name 'calibration_lines'`.

- [ ] **Step 3: Implement**

Append to `stats.py`:

```python
def calibration_lines(tier_rows: list, decay_lines: list) -> list:
    lines = []
    for row in tier_rows:
        mark = "—" if row["ok"] is None else ("✅" if row["ok"] else "❌")
        wr_str = _dash(row["win_rate"], "{:.1f}%")
        lines.append(f"{mark} Tier {row['tier']}: N={row['n']}, WR {wr_str} (expected {row['expected_band']})")
    lines.extend(decay_lines)
    return lines


@bot.command(name="calibration")
async def calibration_cmd(ctx):
    from swingbot.core import scan_engine
    from swingbot.core.analytics.calibration import tier_calibration, score_deciles
    from swingbot.core.analytics.insights import edge_decay_report

    all_trades = scan_engine.trade_log.get_trades(status="all", limit=None)
    closed = [t for t in all_trades if t.get("status") in ("win", "loss")]
    if not closed:
        await ctx.send("No closed trades yet — nothing to calibrate against.")
        return

    tiers = tier_calibration(closed)
    decay = edge_decay_report(closed)
    lines = calibration_lines(tiers, decay)

    deciles = score_deciles(closed)
    decile_summary = (
        f"Score deciles: {len(deciles)} populated bucket(s), "
        f"best {max(deciles, key=lambda d: d['win_rate'])['decile']} @ "
        f"{max(d['win_rate'] for d in deciles):.1f}% WR" if deciles else "No quality-scored trades yet."
    )

    embed = discord.Embed(title="📐 Calibration", description="\n".join(lines)[:4000], color=discord.Color.blurple())
    embed.add_field(name="Score deciles", value=decile_summary, inline=False)
    await ctx.send(embed=embed)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_stats_commands.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/stats.py tests/test_stats_commands.py
git commit -m "feat: !calibration command"
```

### Task B22: `!journal` notes

**Files:** Modify `swingbot/commands/stats.py`; test `tests/test_stats_commands.py`

**Interfaces:**
- Produces: `!journal TRADE_ID your note text…` → `JournalStore.set_note`; confirmation or `"No journal entry for that id"`; `!journal TICKER` lists that ticker's entries (reuses B20's `lessons_lines` renderer with a filter).

- [ ] **Step 1: Failing test**

```python
# tests/test_stats_commands.py (append)
from swingbot.commands.stats import _journal_note_result


def test_journal_note_result_success(tmp_path, monkeypatch):
    from swingbot.core.analytics.journal import JournalStore
    store = JournalStore(path=str(tmp_path / "journal.json"))
    store.add({"trade_id": "T1", "ticker": "NVDA", "outcome": "win", "r_realized": 1.0,
              "auto_lesson": "lesson", "tags": []})
    msg = _journal_note_result(store, "T1", "watch the gap next time")
    assert "saved" in msg.lower() or "note" in msg.lower()
    assert store.get("T1")["note"] == "watch the gap next time"


def test_journal_note_result_missing_id(tmp_path):
    from swingbot.core.analytics.journal import JournalStore
    store = JournalStore(path=str(tmp_path / "journal.json"))
    msg = _journal_note_result(store, "missing", "x")
    assert "no journal entry" in msg.lower()
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_stats_commands.py -v -k journal_note`
Expected: FAIL — `ImportError: cannot import name '_journal_note_result'`.

- [ ] **Step 3: Implement**

Append to `stats.py`:

```python
def _journal_note_result(store, trade_id: str, note: str) -> str:
    ok = store.set_note(trade_id, note)
    if not ok:
        return f"No journal entry for that id (`{trade_id}`)."
    return f"📝 Note saved for trade `{trade_id}`."


@bot.command(name="journal")
async def journal_cmd(ctx, target: str, *, note: str = None):
    from swingbot.core.analytics.journal import JournalStore
    store = JournalStore()

    if note:
        # target is a trade_id in this form.
        await ctx.send(_journal_note_result(store, target, note))
        return

    # No note text -> target is a ticker to list, reusing lessons_lines.
    entries = store.entries()
    matching = [e for e in entries if e.get("ticker", "").upper() == target.upper()]
    if not matching:
        await ctx.send(f"No journal entries for `{target.upper()}`.")
        return
    lines = lessons_lines(matching)
    await ctx.send(f"📖 **{len(matching)} journal entr{'y' if len(matching)==1 else 'ies'} for {target.upper()}:**\n" + "\n".join(lines)[:1900])
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_stats_commands.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/stats.py tests/test_stats_commands.py
git commit -m "feat: !journal notes"
```

### Task B23: Help catalog overhaul

**Files:**
- Modify: `swingbot/bot_core.py` (`COMMANDS_BY_CATEGORY` :90, `COMMAND_USAGE` :152)
- Test: `tests/test_stats_commands.py`

**Interfaces:**
- Produces: new category `📐 Analytics` (top, stats, lessons, calibration, journal); `!plans` finally listed (explorer finding: registered in `COMMAND_USAGE` — already present at `bot_core.py:201` — but missing from `COMMANDS_BY_CATEGORY`); every new command has a usage string.

- [ ] **Step 1: Failing test**

```python
# tests/test_stats_commands.py (append)
def test_help_catalog_covers_analytics_and_plans():
    from swingbot.bot_core import COMMANDS_BY_CATEGORY, COMMAND_USAGE

    all_listed = {cmd.split()[0].lstrip("!") for cmds in COMMANDS_BY_CATEGORY.values() for cmd, _ in cmds}
    for name in ("top", "stats", "lessons", "calibration", "journal", "plans"):
        assert name in all_listed, f"{name} missing from COMMANDS_BY_CATEGORY"
        assert name in COMMAND_USAGE, f"{name} missing from COMMAND_USAGE"
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_stats_commands.py -v -k help_catalog`
Expected: FAIL — `AssertionError: top missing from COMMANDS_BY_CATEGORY`.

- [ ] **Step 3: Implement**

In `bot_core.py`, add a new category to `COMMANDS_BY_CATEGORY` (insert after `"📊 Trades & performance"`, before `"🧪 Backtesting"`):

```python
    "📐 Analytics": [
        ("!top [n]", "The n highest follow-score PENDING/ACTIVE plans right now (default: DIGEST_MAX_PLANS)"),
        ("!stats [7d|30d|90d|ytd|all]", "Win rate, expectancy, profit factor, Sharpe/Sortino, max drawdown, by-tier and by-strategy breakdowns"),
        ("!lessons [n|week]", "Last n journal entries with their auto-generated lesson, or `week` for the weekly digest"),
        ("!calibration", "Tier calibration vs. design bands, quality-score deciles, and edge-decay alerts"),
        ("!journal TRADE_ID your note", "Attach a manual note to a trade's journal entry; `!journal TICKER` lists that ticker's entries"),
    ],
```

Add `"plans"` to `"📊 Trades & performance"` (it already has a `COMMAND_USAGE` entry at `bot_core.py:201`, only the category listing was missing):

```python
        ("!plans [status] [tier:A|B|C] [badge:validated|weak] [TICKER] [from:YYYY-MM-DD] [to:YYYY-MM-DD]",
         "Live ranked plan board (no dates) or historical query (with from:/to:). Filters compose: status/tier/badge/ticker."),
```

Add the four new `COMMAND_USAGE` entries (insert after the existing `"plans"` entry at `bot_core.py:201-202`):

```python
    "top":                 ("!top [n]", "!top  or  !top 5"),
    "stats":               ("!stats [7d|30d|90d|ytd|all]", "!stats  or  !stats 30d"),
    "lessons":             ("!lessons [n|week]", "!lessons 10  or  !lessons week"),
    "calibration":         ("!calibration", "!calibration"),
    "journal":             ("!journal TRADE_ID your note here", "!journal T-42 watch the gap next time  or  !journal NVDA"),
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_stats_commands.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/bot_core.py tests/test_stats_commands.py
git commit -m "feat: help catalog covers analytics + plans"
```

### Task B24: New slash commands

**Files:**
- Modify: `swingbot/commands/slash.py`
- Test: `tests/test_stats_commands.py`

**Interfaces:**
- Produces: `/plans` (status/tier choices), `/top` (n int), `/stats` (period choices), `/lessons` — all invoking the prefix callbacks via the `Context.from_interaction` pattern `/check` already uses (`slash.py:164-212`), NOT the `interaction.channel.send("!...")` hack the six broken bridges use (fixed separately in Task B25).

- [ ] **Step 1: Failing test**

```python
# tests/test_stats_commands.py (append)
def test_new_slash_commands_registered_on_tree():
    import swingbot.commands.slash  # noqa: F401 -- import side effect registers the commands
    from swingbot.bot_core import bot

    names = {cmd.name for cmd in bot.tree.get_commands()}
    for expected in ("plans", "top", "stats", "lessons"):
        assert expected in names, f"/{expected} not registered on bot.tree"
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_stats_commands.py -v -k new_slash`
Expected: FAIL — `AssertionError: plans not registered on bot.tree`.

- [ ] **Step 3: Implement**

Append to `slash.py`:

```python
STATUS_CHOICES = [app_commands.Choice(name=v, value=v) for v in ("All", "PENDING", "ACTIVE", "PARTIAL")]
TIER_CHOICES = [app_commands.Choice(name=v, value=v) for v in ("All", "A", "B", "C")]
PERIOD_CHOICES = [app_commands.Choice(name=v, value=v) for v in ("7d", "30d", "90d", "ytd", "all")]


@bot.tree.command(name="plans", description="Live ranked plan board")
@app_commands.describe(status="Filter by lifecycle status", tier="Filter by quality tier")
@app_commands.choices(status=STATUS_CHOICES, tier=TIER_CHOICES)
async def slash_plans(interaction: discord.Interaction, status: app_commands.Choice[str] = None,
                      tier: app_commands.Choice[str] = None):
    args = []
    if status and status.value != "All":
        args.append(status.value.lower())
    if tier and tier.value != "All":
        args.append(f"tier:{tier.value.lower()}")

    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.plans import plans_cmd
    await plans_cmd.callback(ctx, *args)


@bot.tree.command(name="top", description="Highest follow-score PENDING/ACTIVE plans")
@app_commands.describe(n="How many plans to show (default: config.DIGEST_MAX_PLANS)")
async def slash_top(interaction: discord.Interaction, n: int = None):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.stats import top_cmd
    if n is not None:
        await top_cmd.callback(ctx, n)
    else:
        await top_cmd.callback(ctx)


@bot.tree.command(name="stats", description="Win rate, expectancy, and risk-adjusted stats")
@app_commands.describe(period="Time window")
@app_commands.choices(period=PERIOD_CHOICES)
async def slash_stats(interaction: discord.Interaction, period: app_commands.Choice[str] = None):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.stats import stats_cmd
    await stats_cmd.callback(ctx, period.value if period else "all")


@bot.tree.command(name="lessons", description="Recent journal entries and their auto-generated lessons")
@app_commands.describe(arg="A number of entries, or 'week' for the weekly digest")
async def slash_lessons(interaction: discord.Interaction, arg: str = "5"):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.stats import lessons_cmd
    await lessons_cmd.callback(ctx, arg)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_stats_commands.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/slash.py tests/test_stats_commands.py
git commit -m "feat: slash parity for analytics commands"
```

### Task B25: Fix legacy slash bridges

**Files:** Modify `slash.py` (`/ticker` :234, `/backtest` :246, `/backtestwatchlist` :284, `/trades` :315, `/performance` :335, `/watchlist` :349)
- Test: `tests/test_stats_commands.py`

**Interfaces:**
- Produces: the six bridge commands that today post a literal `!command` string into the channel (`interaction.channel.send(f"!...")`) instead call their prefix callbacks via `Context.from_interaction` (same as `/check`, `slash.py:164-212`). User-visible behavior otherwise identical.

- [ ] **Step 1: Failing test**

```python
# tests/test_stats_commands.py (append)
def test_slash_py_has_no_bang_command_channel_send_calls():
    import inspect
    from swingbot.commands import slash as slash_mod

    source = inspect.getsource(slash_mod)
    # Regression tripwire: this exact pattern is the broken bridge -- a
    # bot-authored message that process_commands() silently ignores
    # (discord.py never re-parses a message from a bot as a command).
    assert 'channel.send(f"!' not in source
    assert 'channel.send("!' not in source


def test_six_bridge_commands_still_registered():
    from swingbot.bot_core import bot
    names = {cmd.name for cmd in bot.tree.get_commands()}
    for expected in ("ticker", "backtest", "backtestwatchlist", "trades", "performance", "watchlist"):
        assert expected in names
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_stats_commands.py -v -k bridge`
Expected: FAIL — `AssertionError` on the tripwire (both patterns are present today, six times total).

- [ ] **Step 3: Implement**

Replace each of the six commands in `slash.py`:

```python
@bot.tree.command(name="ticker", description="Full bias snapshot for a single stock across all strategies")
@app_commands.describe(ticker="Stock ticker symbol, e.g. AAPL")
async def slash_ticker(interaction: discord.Interaction, ticker: str):
    ticker = ticker.upper()
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.data import ticker_cmd
    await ticker_cmd.callback(ctx, ticker)


@bot.tree.command(name="backtest", description="Backtest a ticker against historical data")
@app_commands.describe(
    ticker="Stock ticker symbol, e.g. AAPL", horizon="Swing horizon (default: all)",
    strategy="Strategy to test (default: all)", from_date="Start date YYYY-MM-DD (optional)",
    to_date="End date YYYY-MM-DD (optional)", setups="List every individual trade setup instead of the summary table",
)
@app_commands.choices(horizon=HORIZON_CHOICES, strategy=STRATEGY_CHOICES)
async def slash_backtest(interaction: discord.Interaction, ticker: str,
                         horizon: app_commands.Choice[str] = None, strategy: app_commands.Choice[str] = None,
                         from_date: str = None, to_date: str = None, setups: bool = False):
    ticker = ticker.upper()
    args = [ticker, horizon.value if horizon else "all", strategy.value if strategy else "all"]
    if from_date:
        args.append(f"from:{from_date}")
    if to_date:
        args.append(f"to:{to_date}")
    if setups:
        args.append("setups")
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.backtest import backtest_cmd
    await backtest_cmd.callback(ctx, *args)


@bot.tree.command(name="backtestwatchlist", description="Backtest every watchlist ticker, ranked by expectancy")
@app_commands.describe(
    horizon="Swing horizon (default: all)", strategy="Strategy to test (default: all)",
    from_date="Start date YYYY-MM-DD (optional)", to_date="End date YYYY-MM-DD (optional)",
)
@app_commands.choices(horizon=HORIZON_CHOICES, strategy=STRATEGY_CHOICES)
async def slash_backtestwatchlist(interaction: discord.Interaction, horizon: app_commands.Choice[str] = None,
                                  strategy: app_commands.Choice[str] = None, from_date: str = None, to_date: str = None):
    args = [horizon.value if horizon else "all", strategy.value if strategy else "all"]
    if from_date:
        args.append(f"from:{from_date}")
    if to_date:
        args.append(f"to:{to_date}")
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.backtest import backtestwatchlist_cmd
    await backtestwatchlist_cmd.callback(ctx, *args)


@bot.tree.command(name="trades", description="List logged trades with pagination")
@app_commands.describe(filter="Filter by trade status (default: all)", per_page="Trades per page (default: 10)")
@app_commands.choices(filter=TRADE_FILTER_CHOICES)
async def slash_trades(interaction: discord.Interaction, filter: app_commands.Choice[str] = None, per_page: int = 10):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.trades import trades_cmd
    await trades_cmd.callback(ctx, filter.value if filter else "all", per_page)


@bot.tree.command(name="performance", description="Win rate + risk-adjusted stats for closed trades")
@app_commands.describe(level="Filter to a specific confidence level (1-5), or omit for overall")
async def slash_performance(interaction: discord.Interaction, level: int = None):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.trades import performance_cmd
    if level is not None:
        await performance_cmd.callback(ctx, level)
    else:
        await performance_cmd.callback(ctx)


@bot.tree.command(name="watchlist", description="Show, add, or remove tickers from the watchlist")
@app_commands.describe(action="Action to perform (leave blank to just show the list)", ticker="Ticker to add or remove")
@app_commands.choices(action=[
    app_commands.Choice(name="Show", value="show"), app_commands.Choice(name="Add", value="add"),
    app_commands.Choice(name="Remove", value="remove"), app_commands.Choice(name="Clear", value="clear"),
])
async def slash_watchlist(interaction: discord.Interaction, action: app_commands.Choice[str] = None, ticker: str = None):
    act = action.value if action else "show"
    if act in ("add", "remove") and not ticker:
        await interaction.response.send_message("Please provide a ticker for add/remove actions.", ephemeral=True)
        return

    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.watchlist import watchlist_cmd, watchlist_add, watchlist_remove, watchlist_clear
    if act == "show":
        await watchlist_cmd.callback(ctx)
    elif act == "add":
        await watchlist_add.callback(ctx, ticker.upper())
    elif act == "remove":
        await watchlist_remove.callback(ctx, ticker.upper())
    elif act == "clear":
        await watchlist_clear.callback(ctx)
```

Every prefix-callback import name above (`ticker_cmd`, `backtest_cmd`, `backtestwatchlist_cmd`, `trades_cmd`, `performance_cmd`, `watchlist_cmd`/`watchlist_add`/`watchlist_remove`/`watchlist_clear`) must be verified against the real function names in `swingbot/commands/data.py`, `swingbot/commands/backtest.py`, `swingbot/commands/trades.py`, and `swingbot/commands/watchlist.py` before landing this — `trades_cmd` and `performance_cmd` are confirmed exact matches (`trades.py:145` and `trades.py:335`); `Grep "@bot.command\|@bot.group" swingbot/commands/data.py swingbot/commands/backtest.py swingbot/commands/watchlist.py` to confirm the other five before wiring the imports, and correct any name mismatch found (do not rename the underlying prefix command — only correct the import alias here).

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_stats_commands.py -q`
Expected: all pass. Full suite: `python -m pytest tests/ -q` — green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/slash.py tests/test_stats_commands.py
git commit -m "fix: slash bridges invoke callbacks directly"
```

---

# Phase B4 — Charts v2 (Tasks B26–B36)

### Task B26: Equity-curve render

**Files:**
- Create: `swingbot/core/charts/analytics_charts.py`
- Test: `tests/test_analytics_charts.py`

**Interfaces:**
- Produces: `render_equity_curve(curve: dict, out_dir: str, *, spy_overlay: list | None = None) -> str` — dark-theme (chart_style constants) line chart of Plan A's `equity_curve` points, drawdown shaded beneath in `DOWN_COLOR` alpha 0.15, optional SPY overlay dashed `MUTED_TEXT_COLOR`; saves PNG dpi 150 and returns path. All renderers in this module follow this signature shape: `(data, out_dir, **style) -> str`.

- [ ] **Step 1: Failing test**

```python
# tests/test_analytics_charts.py
"""Chart-render smoke tests -- every renderer in analytics_charts.py is
(data, out_dir, ...) -> path_to_png. No display backend is needed
(chart_style.py already forces matplotlib's Agg backend); assertions
just confirm a real, non-trivial PNG landed on disk -- pixel-level
content isn't asserted (that's what a human "!stats"/"!calibration"
smoke-check in Task B38 is for)."""
import os

from swingbot.core.charts.analytics_charts import render_equity_curve


def _fixture_curve():
    return {
        "points": [
            {"date": "2026-01-02", "balance": 1000.0, "pnl": 0.0},
            {"date": "2026-01-05", "balance": 1050.0, "pnl": 50.0},
            {"date": "2026-01-06", "balance": 980.0, "pnl": -70.0},
            {"date": "2026-01-08", "balance": 1120.0, "pnl": 140.0},
        ],
        "skipped_n": 0,
    }


def test_render_equity_curve_writes_a_real_png(tmp_path):
    path = render_equity_curve(_fixture_curve(), str(tmp_path))
    assert os.path.exists(path)
    assert os.path.getsize(path) > 10_000


def test_render_equity_curve_with_spy_overlay(tmp_path):
    spy = [
        {"date": "2026-01-02", "balance": 1000.0},
        {"date": "2026-01-08", "balance": 1030.0},
    ]
    path = render_equity_curve(_fixture_curve(), str(tmp_path), spy_overlay=spy)
    assert os.path.exists(path)
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_analytics_charts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.charts.analytics_charts'`.

- [ ] **Step 3: Implement**

```python
# swingbot/core/charts/analytics_charts.py
"""
Stat/analytics charts (equity curve, R-multiple histogram, calibration
decile bars, strategy heatmap) -- distinct from trade_chart.py's
per-trade candlestick charts, but sharing the exact same dark visual
system (chart_style.py's constants) so a !stats screenshot and a scan
alert's chart never look like they came from two different tools.
Every function here follows the same (data, out_dir, **style) -> path
shape and is designed to run inside asyncio.to_thread from command
handlers (see Task B36's async-render audit).
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from .chart_style import (
    CHART_BG, CHIP_BG, DOWN_COLOR, GRID_COLOR, MUTED_TEXT_COLOR,
    SPINE_COLOR, TARGET_COLOR, TEXT_COLOR, UP_COLOR,
)

_FIGSIZE = (10, 5)
_DPI = 150


def _new_dark_axes(figsize=_FIGSIZE):
    fig, ax = plt.subplots(figsize=figsize, facecolor=CHART_BG)
    ax.set_facecolor(CHART_BG)
    ax.grid(True, color=GRID_COLOR, linestyle="--", linewidth=0.6, alpha=0.7)
    for spine in ax.spines.values():
        spine.set_color(SPINE_COLOR)
    ax.tick_params(colors=MUTED_TEXT_COLOR, labelsize=8)
    ax.xaxis.label.set_color(TEXT_COLOR)
    ax.yaxis.label.set_color(TEXT_COLOR)
    return fig, ax


def _save(fig, out_dir: str, filename: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    try:
        fig.savefig(path, dpi=_DPI, bbox_inches="tight", facecolor=CHART_BG)
    finally:
        plt.close(fig)
    return path


def render_equity_curve(curve: dict, out_dir: str, *, spy_overlay: list = None,
                        filename: str = "equity_curve.png") -> str:
    """curve is Plan A's equity_curve() return shape:
    {"points": [{"date","balance","pnl"}, ...], "skipped_n": int}.
    Drawdown is shaded beneath the equity line itself (peak-to-current
    gap, filled in DOWN_COLOR at low alpha) rather than drawn on a
    separate panel -- for a single balance series, overlaying it directly
    is more legible than a second synced axis."""
    points = curve["points"]
    dates = [np.datetime64(p["date"]) for p in points]
    balances = [p["balance"] for p in points]

    fig, ax = _new_dark_axes()
    ax.plot(dates, balances, color=TARGET_COLOR, linewidth=1.8, marker="o", markersize=3, label="Equity")

    peak = balances[0]
    peaks = []
    for b in balances:
        peak = max(peak, b)
        peaks.append(peak)
    ax.fill_between(dates, balances, peaks, color=DOWN_COLOR, alpha=0.15, step=None, label="Drawdown")

    if spy_overlay:
        spy_dates = [np.datetime64(p["date"]) for p in spy_overlay]
        spy_bal = [p["balance"] for p in spy_overlay]
        # Normalized to the same starting balance as the equity curve so
        # the two lines are visually comparable regardless of SPY's own
        # price scale.
        scale = balances[0] / spy_bal[0] if spy_bal[0] else 1.0
        ax.plot(spy_dates, [b * scale for b in spy_bal], color=MUTED_TEXT_COLOR,
                linestyle="--", linewidth=1.2, alpha=0.8, label="SPY (normalized)")

    ax.set_title("Equity Curve", color=TEXT_COLOR, fontsize=12, fontweight="bold")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()
    legend = ax.legend(loc="upper left", fontsize=8, framealpha=0.9, facecolor=CHIP_BG, edgecolor=SPINE_COLOR, labelcolor=TEXT_COLOR)
    return _save(fig, out_dir, filename)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_analytics_charts.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/analytics_charts.py tests/test_analytics_charts.py
git commit -m "feat: equity curve chart"
```

### Task B27: R-multiple histogram render

**Files:** Modify `swingbot/core/charts/analytics_charts.py`; test `tests/test_analytics_charts.py`

**Interfaces:**
- Produces: `render_r_histogram(r_list: list[float], out_dir) -> str` — bins width 0.25R from −3R to +5R, losses `DOWN_COLOR` / wins `UP_COLOR`, vertical line at mean (expectancy) with label.

- [ ] **Step 1: Failing test**

```python
# tests/test_analytics_charts.py (append)
from swingbot.core.charts.analytics_charts import render_r_histogram


def test_render_r_histogram_writes_a_real_png(tmp_path):
    r_list = [-1.0, -0.5, 0.3, 0.8, 1.2, 1.5, -1.0, 2.0, 0.5, -0.8]
    path = render_r_histogram(r_list, str(tmp_path))
    assert os.path.exists(path)
    assert os.path.getsize(path) > 10_000


def test_render_r_histogram_empty_list_still_renders(tmp_path):
    path = render_r_histogram([], str(tmp_path), filename="empty.png")
    assert os.path.exists(path)
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_analytics_charts.py -v -k r_histogram`
Expected: FAIL — `ImportError: cannot import name 'render_r_histogram'`.

- [ ] **Step 3: Implement**

Append to `analytics_charts.py`:

```python
def render_r_histogram(r_list: list, out_dir: str, filename: str = "r_histogram.png") -> str:
    """Fixed bin edges -3R..+5R at 0.25R width regardless of the actual
    data range -- a stable x-axis across every render means two !stats
    screenshots taken weeks apart are visually comparable, rather than
    each auto-scaling to whatever that particular sample happened to
    span."""
    bins = np.arange(-3.0, 5.0 + 0.25, 0.25)
    fig, ax = _new_dark_axes()

    if r_list:
        wins = [r for r in r_list if r >= 0]
        losses = [r for r in r_list if r < 0]
        ax.hist(losses, bins=bins, color=DOWN_COLOR, alpha=0.85, label=f"Losses (n={len(losses)})")
        ax.hist(wins, bins=bins, color=UP_COLOR, alpha=0.85, label=f"Wins/scratch (n={len(wins)})")
        mean_r = float(np.mean(r_list))
        ax.axvline(mean_r, color=TARGET_COLOR, linewidth=1.8, linestyle="--")
        ax.text(mean_r, ax.get_ylim()[1] * 0.95, f" Expectancy {mean_r:+.2f}R",
               color=TARGET_COLOR, fontsize=9, fontweight="bold", va="top")
    else:
        ax.text(0.5, 0.5, "No R-multiples yet", transform=ax.transAxes, ha="center", va="center",
               color=MUTED_TEXT_COLOR, fontsize=11)

    ax.set_xlabel("R multiple")
    ax.set_ylabel("Trade count")
    ax.set_title("R-Multiple Distribution", color=TEXT_COLOR, fontsize=12, fontweight="bold")
    if r_list:
        ax.legend(loc="upper right", fontsize=8, framealpha=0.9, facecolor=CHIP_BG, edgecolor=SPINE_COLOR, labelcolor=TEXT_COLOR)
    return _save(fig, out_dir, filename)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_analytics_charts.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/analytics_charts.py tests/test_analytics_charts.py
git commit -m "feat: R-multiple histogram chart"
```

### Task B28: Calibration chart render

**Files:** Modify `swingbot/core/charts/analytics_charts.py`; test `tests/test_analytics_charts.py`

**Interfaces:**
- Produces: `render_calibration(deciles: list[dict], out_dir) -> str` — bar chart of realized WR per score decile with an 80% target line; bars below target `DOWN_COLOR`, above `UP_COLOR`.

- [ ] **Step 1: Failing test**

```python
# tests/test_analytics_charts.py (append)
from swingbot.core.charts.analytics_charts import render_calibration


def test_render_calibration_writes_a_real_png(tmp_path):
    deciles = [
        {"decile": "0-9", "n": 4, "win_rate": 25.0, "expectancy_r": -0.4},
        {"decile": "50-59", "n": 12, "win_rate": 66.7, "expectancy_r": 0.1},
        {"decile": "90-100", "n": 20, "win_rate": 90.0, "expectancy_r": 0.7},
    ]
    path = render_calibration(deciles, str(tmp_path))
    assert os.path.exists(path)
    assert os.path.getsize(path) > 10_000
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_analytics_charts.py -v -k calibration`
Expected: FAIL — `ImportError: cannot import name 'render_calibration'`.

- [ ] **Step 3: Implement**

Append to `analytics_charts.py`:

```python
CALIBRATION_TARGET_WR = 80.0


def render_calibration(deciles: list, out_dir: str, filename: str = "calibration.png") -> str:
    fig, ax = _new_dark_axes()
    if deciles:
        labels = [d["decile"] for d in deciles]
        wrs = [d["win_rate"] for d in deciles]
        colors = [UP_COLOR if wr >= CALIBRATION_TARGET_WR else DOWN_COLOR for wr in wrs]
        bars = ax.bar(labels, wrs, color=colors, alpha=0.9)
        for bar, d in zip(bars, deciles):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5, f"n={d['n']}",
                   ha="center", fontsize=7, color=MUTED_TEXT_COLOR)
        ax.axhline(CALIBRATION_TARGET_WR, color=TEXT_COLOR, linewidth=1.2, linestyle="--")
        ax.text(len(labels) - 0.5, CALIBRATION_TARGET_WR + 1.5, f"{CALIBRATION_TARGET_WR:.0f}% target",
               color=TEXT_COLOR, fontsize=8, ha="right")
        ax.set_ylim(0, 105)
    else:
        ax.text(0.5, 0.5, "No quality-scored closed trades yet", transform=ax.transAxes,
               ha="center", va="center", color=MUTED_TEXT_COLOR, fontsize=11)

    ax.set_xlabel("Quality score decile")
    ax.set_ylabel("Realized win rate %")
    ax.set_title("Quality-Score Calibration", color=TEXT_COLOR, fontsize=12, fontweight="bold")
    return _save(fig, out_dir, filename)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_analytics_charts.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/analytics_charts.py tests/test_analytics_charts.py
git commit -m "feat: calibration decile chart"
```

### Task B29: Strategy heatmap render

**Files:** Modify `swingbot/core/charts/analytics_charts.py`; test `tests/test_analytics_charts.py`

**Interfaces:**
- Produces: `render_strategy_heatmap(rows: list[dict], out_dir, *, value="win_rate") -> str` — strategy × (win_rate, expectancy_r, n) table as an imshow heatmap, red→green centered at 80 for WR and 0 for ExpR, cell annotations.

- [ ] **Step 1: Failing test**

```python
# tests/test_analytics_charts.py (append)
from swingbot.core.charts.analytics_charts import render_strategy_heatmap


def _fixture_rows():
    return [
        {"key": "EMA Crossover", "n": 15, "win_rate": 73.3, "expectancy_r": 0.4, "wins": 11, "losses": 4, "avg_r": 0.4, "profit_factor": 2.0, "total_pnl": 1500.0},
        {"key": "Fibonacci", "n": 20, "win_rate": 85.0, "expectancy_r": 0.6, "wins": 17, "losses": 3, "avg_r": 0.6, "profit_factor": 3.0, "total_pnl": 2400.0},
    ]


def test_render_strategy_heatmap_win_rate(tmp_path):
    path = render_strategy_heatmap(_fixture_rows(), str(tmp_path))
    assert os.path.exists(path)
    assert os.path.getsize(path) > 8_000


def test_render_strategy_heatmap_expectancy(tmp_path):
    path = render_strategy_heatmap(_fixture_rows(), str(tmp_path), value="expectancy_r", filename="heatmap_exp.png")
    assert os.path.exists(path)
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_analytics_charts.py -v -k heatmap`
Expected: FAIL — `ImportError: cannot import name 'render_strategy_heatmap'`.

- [ ] **Step 3: Implement**

Append to `analytics_charts.py`:

```python
def render_strategy_heatmap(rows: list, out_dir: str, *, value: str = "win_rate",
                            filename: str = "strategy_heatmap.png") -> str:
    """Single-column heatmap (one row per strategy, one color-mapped
    column for whichever `value` was asked for) -- diverging red->green,
    centered at 80 for win_rate (the OOS validation bar) or 0 for
    expectancy_r (breakeven)."""
    fig, ax = _new_dark_axes(figsize=(6, max(2.5, 0.5 * len(rows) + 1)))
    if not rows:
        ax.text(0.5, 0.5, "No strategy stats yet", transform=ax.transAxes, ha="center", va="center",
               color=MUTED_TEXT_COLOR, fontsize=11)
        ax.set_title("Strategy Heatmap", color=TEXT_COLOR)
        return _save(fig, out_dir, filename)

    center = 80.0 if value == "win_rate" else 0.0
    values = np.array([[r[value]] for r in rows], dtype=float)
    span = max(abs(values.max() - center), abs(values.min() - center), 1e-6)
    norm = (values - center) / span  # -1..+1, 0 at center

    cmap = plt.get_cmap("RdYlGn")
    ax.imshow(norm, cmap=cmap, vmin=-1, vmax=1, aspect="auto")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r["key"] for r in rows], color=TEXT_COLOR, fontsize=9)
    ax.set_xticks([0])
    ax.set_xticklabels([value.replace("_", " ")], color=TEXT_COLOR, fontsize=9)

    for i, r in enumerate(rows):
        val = r[value]
        label = f"{val:.1f}%" if value == "win_rate" else f"{val:+.2f}"
        ax.text(0, i, f"{label}\n(n={r['n']})", ha="center", va="center", fontsize=8,
               color="black" if abs(norm[i, 0]) < 0.6 else "white", fontweight="bold")

    ax.set_title(f"Strategy Heatmap — {value.replace('_', ' ')}", color=TEXT_COLOR, fontsize=12, fontweight="bold")
    return _save(fig, out_dir, filename)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_analytics_charts.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/analytics_charts.py tests/test_analytics_charts.py
git commit -m "feat: strategy heatmap chart"
```

### Task B30: Plan overlays — risk/reward bands

**Files:**
- Modify: `swingbot/core/charts/trade_chart.py` (`generate_trade_chart` :147 — add `plan=None` kwarg), `swingbot/core/charts/chart_style.py` (band alphas)
- Test: `tests/test_plan_chart_overlays.py`

**Interfaces:**
- Produces: `generate_trade_chart(..., plan: "TradePlanV2 | dict | None" = None)` — when given: horizontal shaded band entry↔stop in `STOP_COLOR` alpha 0.08 (risk), entry↔TP1 in `TARGET_COLOR` alpha 0.08 (reward), TP1↔TP2 in `TARGET2_COLOR` alpha 0.06 (runner, when tp2). Constants `RISK_BAND_ALPHA=0.08`, `REWARD_BAND_ALPHA=0.08`, `RUNNER_BAND_ALPHA=0.06` in `chart_style.py`. Legacy calls (`plan=None`) render pixel-identically to today — the existing target2 band alpha stays hardcoded at its current `0.05` for the no-plan path; only a plan-driven runner band uses the new `0.06` constant.

- [ ] **Step 1: Failing test**

```python
# tests/test_plan_chart_overlays.py
"""Chart-render tests for trade_chart.py's plan= kwarg (risk/reward
bands, trigger arrow, status watermark, chandelier trail) and for
embeds.py's MFE/MAE markers on closed-trade charts. These are smoke
tests (file exists, non-trivial size, no exception) -- pixel content is
not asserted; Task B38's manual smoke pass is where a human actually
looks at one."""
import os
import types

from tests.conftest import make_ohlcv
from swingbot.core.charts.trade_chart import generate_trade_chart


def _fixture_plan(entry_type="market", status="ACTIVE", direction="bullish", tp2=118.0):
    return types.SimpleNamespace(
        plan_id="p1", ticker="NVDA", direction=direction, entry_type=entry_type,
        trigger_price=100.0, stop_loss=95.0, tp1=110.0, tp2=tp2,
        trail_atr_mult=2.5, status=status, strategy="EMA Crossover", horizon_key="4w",
    )


def _fixture_df():
    closes = [100 + i * 0.3 for i in range(60)]
    return make_ohlcv(closes, spread_pct=1.5)


def test_generate_trade_chart_with_plan_renders(tmp_path):
    df = _fixture_df()
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="with_plan.png", target2=118.0, plan=_fixture_plan(),
    )
    assert os.path.exists(path)
    assert os.path.getsize(path) > 10_000


def test_generate_trade_chart_without_plan_is_unaffected(tmp_path):
    df = _fixture_df()
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="no_plan.png", target2=118.0,
    )
    assert os.path.exists(path)
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_plan_chart_overlays.py -v`
Expected: FAIL — `TypeError: generate_trade_chart() got an unexpected keyword argument 'plan'`.

- [ ] **Step 3: Implement**

In `chart_style.py`, add near `FVG_ZONE_ALPHA`:

```python
# Plan-driven R:R band alphas (trade_chart.py's plan= kwarg, Task B30).
# RISK_BAND_ALPHA/REWARD_BAND_ALPHA match the long-standing hardcoded
# 0.08 used for the entry<->stop and entry<->target1 bands regardless
# of whether a plan= kwarg is present -- unifying the literal into a
# named constant, not changing its value. RUNNER_BAND_ALPHA (0.06) is
# NEW and used ONLY when a plan is actually passed; the legacy no-plan
# path keeps its original 0.05 literal untouched so old callers render
# pixel-identically to before this task.
RISK_BAND_ALPHA = 0.08
REWARD_BAND_ALPHA = 0.08
RUNNER_BAND_ALPHA = 0.06
```

In `trade_chart.py`:
- Add the import: `from .chart_style import (..., RISK_BAND_ALPHA, REWARD_BAND_ALPHA, RUNNER_BAND_ALPHA)` (append to the existing multi-line import block from `.chart_style`).
- Add `plan=None` to `generate_trade_chart`'s signature (after `market_price: float = None,`).
- Replace the three existing `ax.axhspan(...)` lines (`trade_chart.py:779-782`) with:

```python
        reward_alpha = REWARD_BAND_ALPHA
        risk_alpha = RISK_BAND_ALPHA
        runner_alpha = RUNNER_BAND_ALPHA if plan is not None else 0.05
        ax.axhspan(min(entry, take_profit), max(entry, take_profit), color=TARGET_COLOR, alpha=reward_alpha, zorder=0)
        ax.axhspan(min(entry, stop_loss), max(entry, stop_loss), color=STOP_COLOR, alpha=risk_alpha, zorder=0)
        if target2 is not None:
            ax.axhspan(min(take_profit, target2), max(take_profit, target2), color=TARGET2_COLOR, alpha=runner_alpha, zorder=0)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_plan_chart_overlays.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/trade_chart.py swingbot/core/charts/chart_style.py tests/test_plan_chart_overlays.py
git commit -m "feat: R:R shaded bands on plan charts"
```

### Task B31: Plan overlays — trigger arrow + status watermark

**Files:** Modify `swingbot/core/charts/trade_chart.py`; test `tests/test_plan_chart_overlays.py`

**Interfaces:**
- Produces: stop-entry plans draw an annotate-arrow at `trigger_price` on the last bar (`"BUY STOP"` / `"SELL STOP"` in `ENTRY_COLOR`); a status watermark (`plan.status`) bottom-right in `MUTED_TEXT_COLOR` alpha 0.5, 20 pt.

- [ ] **Step 1: Failing test**

```python
# tests/test_plan_chart_overlays.py (append)
def test_pending_stop_entry_plan_renders_with_arrow(tmp_path):
    df = _fixture_df()
    plan = _fixture_plan(entry_type="stop_entry", status="PENDING")
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="pending_stop_entry.png", target2=118.0, plan=plan,
    )
    assert os.path.exists(path)


def test_market_entry_plan_renders_without_error(tmp_path):
    df = _fixture_df()
    plan = _fixture_plan(entry_type="market", status="ACTIVE")
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="market_active.png", target2=118.0, plan=plan,
    )
    assert os.path.exists(path)
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_plan_chart_overlays.py -v -k "pending_stop_entry or market_entry_plan"`
Expected: PASS already for the "renders without error" shape (nothing raises without the new code), but the intent (an arrow/watermark actually drawn) has no assertion yet to fail against -- this task's real verification is Step 4's full-suite run plus the Task B38 manual smoke pass, since matplotlib draw calls aren't easily assertable from a smoke test without inspecting the rendered pixels. Proceed straight to Step 3.

- [ ] **Step 3: Implement**

In `trade_chart.py`, immediately before the existing "Legal/liability fine print" block (`trade_chart.py:845-855`), insert:

```python
        # Trigger arrow + status watermark (Task B31) -- only when a plan
        # was passed; drawn late (after every axis limit/label placement
        # above has settled) so the arrow anchors to the FINAL x_right/
        # ylim, not a pre-adjustment one.
        if plan is not None:
            if getattr(plan, "entry_type", None) == "stop_entry" and getattr(plan, "status", None) == "PENDING":
                trigger_word = "BUY STOP" if plan.direction == "bullish" else "SELL STOP"
                ax.annotate(
                    trigger_word, xy=(x_right, plan.trigger_price), xytext=(x_right - 4, plan.trigger_price),
                    color=ENTRY_COLOR, fontsize=8, fontweight="bold", ha="right", va="center", zorder=9,
                    arrowprops=dict(arrowstyle="->", color=ENTRY_COLOR, lw=1.3),
                    bbox=dict(boxstyle="round,pad=0.2", facecolor=CHIP_BG, edgecolor=ENTRY_COLOR, alpha=0.85),
                )
            status_text = getattr(plan, "status", None)
            if status_text:
                ax.text(
                    0.98, 0.04, status_text, transform=ax.transAxes, fontsize=20, fontweight="bold",
                    color=MUTED_TEXT_COLOR, alpha=0.5, ha="right", va="bottom", zorder=1,
                )
```

`CHIP_BG` must already be imported in `trade_chart.py` (it is, from the existing `.chart_style` import block).

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_plan_chart_overlays.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/trade_chart.py tests/test_plan_chart_overlays.py
git commit -m "feat: trigger arrow + status watermark"
```

### Task B32: Plan overlays — runner trail path

**Files:** Modify `swingbot/core/charts/trade_chart.py`; test `tests/test_plan_chart_overlays.py`

**Interfaces:**
- Produces: for PARTIAL plans, a dotted chandelier-trail line: `highest close since TP1 bar − trail_atr_mult × ATR(14)` per bar (reuse `swingbot.core.indicators.atr` — the same ATR helper `plan_engine.build_strategy_plan` imports as `atr_indicator`), drawn in `CURRENT_PRICE_COLOR`; needs `plan` + the df already passed. Non-PARTIAL → nothing.

- [ ] **Step 1: Failing test**

```python
# tests/test_plan_chart_overlays.py (append)
def test_partial_plan_renders_trail(tmp_path):
    df = _fixture_df()
    plan = _fixture_plan(entry_type="market", status="PARTIAL")
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="partial_trail.png", target2=118.0, plan=plan,
    )
    assert os.path.exists(path)
    assert os.path.getsize(path) > 10_000


def test_active_plan_has_no_trail_and_still_renders(tmp_path):
    df = _fixture_df()
    plan = _fixture_plan(entry_type="market", status="ACTIVE")
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="active_no_trail.png", target2=118.0, plan=plan,
    )
    assert os.path.exists(path)
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_plan_chart_overlays.py -v -k trail`
Expected: PASS already for existence (the fixture's synthetic uptrend crosses `tp1=110` well within 60 bars, so the trail-drawing code path this step adds will actually execute once implemented — nothing to newly fail against without pixel inspection, same caveat as B31). Proceed to Step 3; verify by temporarily adding `print`/`assert False` inside the new block during local development if you want to confirm it executes, then remove the debug assertion before committing.

- [ ] **Step 3: Implement**

In `trade_chart.py`, insert the chandelier trail block right before the B31 trigger-arrow/watermark block added above (so it draws under the arrow/watermark, which are meant to be the topmost overlays):

```python
        # Chandelier runner trail (Task B32) -- PARTIAL plans only. Finds
        # the first bar in the VISIBLE window where price actually
        # touched tp1 (the runner's own starting point), then walks
        # forward tracking the highest close since (lowest, for a
        # bearish plan) minus trail_atr_mult * ATR(14) per bar -- the
        # same chandelier formula plan_engine.py's TRAIL_ATR_MULT
        # constant is designed for, just visualized here rather than
        # applied to a live exit decision.
        if plan is not None and getattr(plan, "status", None) == "PARTIAL":
            try:
                from ..indicators import atr as atr_indicator
                atr_full = atr_indicator(df, 14)
                atr_recent = atr_full.reindex(recent.index).bfill()
                is_bull_trail = plan.direction == "bullish"
                if is_bull_trail:
                    tp1_hit = recent.index[recent["High"] >= plan.tp1]
                else:
                    tp1_hit = recent.index[recent["Low"] <= plan.tp1]
                if len(tp1_hit):
                    start_pos = recent.index.get_loc(tp1_hit[0])
                    trail_xs, trail_ys = [], []
                    running_extreme = None
                    for i in range(start_pos, len(recent)):
                        close_i = float(recent["Close"].iloc[i])
                        if running_extreme is None:
                            running_extreme = close_i
                        else:
                            running_extreme = max(running_extreme, close_i) if is_bull_trail else min(running_extreme, close_i)
                        atr_i = float(atr_recent.iloc[i])
                        trail_val = (running_extreme - plan.trail_atr_mult * atr_i if is_bull_trail
                                    else running_extreme + plan.trail_atr_mult * atr_i)
                        trail_xs.append(i)
                        trail_ys.append(trail_val)
                    ax.plot(trail_xs, trail_ys, color=CURRENT_PRICE_COLOR, linestyle=":", linewidth=1.6,
                           alpha=0.85, zorder=6)
                    ax.text(trail_xs[-1], trail_ys[-1], " trail", color=CURRENT_PRICE_COLOR, fontsize=7,
                           va="center", ha="left", zorder=6)
            except Exception as _te:
                log.debug("Chandelier trail overlay skipped: %s", _te)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_plan_chart_overlays.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/trade_chart.py tests/test_plan_chart_overlays.py
git commit -m "feat: chandelier trail on PARTIAL charts"
```

### Task B33: Closed-trade MFE/MAE markers

**Files:** Modify `swingbot/core/scanning/embeds.py` (`regenerate_chart_for_trade` :404 → pass markers), `swingbot/core/charts/trade_chart.py`
- Test: `tests/test_plan_chart_overlays.py`

**Interfaces:**
- Produces: `generate_trade_chart(..., markers: dict | None = None)` where `markers={"mfe": (date, price), "mae": (date, price)}` draws ▲ `UP_COLOR` at MFE and ▼ `DOWN_COLOR` at MAE with `"+2.0R"`-style labels; `regenerate_chart_for_trade` computes them from the journal entry when present.

- [ ] **Step 1: Failing test**

```python
# tests/test_plan_chart_overlays.py (append)
import pandas as pd


def test_markers_render_without_error(tmp_path):
    df = _fixture_df()
    mfe_date = df.index[30]
    mae_date = df.index[10]
    markers = {
        "mfe": (mfe_date, float(df["High"].iloc[30])), "mfe_r": 2.0,
        "mae": (mae_date, float(df["Low"].iloc[10])), "mae_r": -0.5,
    }
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="with_markers.png", target2=118.0, markers=markers,
    )
    assert os.path.exists(path)


def test_no_markers_still_renders(tmp_path):
    df = _fixture_df()
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="no_markers.png", target2=118.0,
    )
    assert os.path.exists(path)
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_plan_chart_overlays.py -v -k markers`
Expected: FAIL — `TypeError: generate_trade_chart() got an unexpected keyword argument 'markers'`.

- [ ] **Step 3: Implement**

In `trade_chart.py`, add `markers: dict = None` to the signature (after `plan=None,`), and insert the drawing block right after the B32 trail block:

```python
        # MFE/MAE markers (Task B33) -- closed-trade charts only. `markers`
        # keys "mfe"/"mae" are (date, price) tuples; optional "mfe_r"/
        # "mae_r" floats add the R-multiple label. A marker whose date
        # falls outside the currently-visible `recent` window is skipped
        # silently rather than raising -- an old trade re-viewed with a
        # short lookback_days can easily have its MFE/MAE bar scrolled
        # out of frame.
        if markers:
            for key, arrow, color in (("mfe", "▲", UP_COLOR), ("mae", "▼", DOWN_COLOR)):
                point = markers.get(key)
                if point is None:
                    continue
                m_date, m_price = point
                try:
                    x_pos = recent.index.get_loc(m_date)
                except KeyError:
                    continue
                r_val = markers.get(f"{key}_r")
                label = f"{arrow} {key.upper()}" + (f" {r_val:+.1f}R" if r_val is not None else "")
                va = "bottom" if key == "mfe" else "top"
                offset = 1 if key == "mfe" else -1
                ax.annotate(
                    label, xy=(x_pos, m_price), xytext=(x_pos, m_price + offset * (ylim[1] - ylim[0]) * 0.03),
                    color=color, fontsize=8, fontweight="bold", ha="center", va=va, zorder=9,
                    arrowprops=dict(arrowstyle="-", color=color, lw=1.0, alpha=0.7),
                )
```

In `embeds.py`, update `regenerate_chart_for_trade` (`:404-427`) to compute markers from the journal entry when one exists:

```python
def regenerate_chart_for_trade(trade: dict) -> str | None:
    try:
        df = get_daily_data(trade["ticker"])
        h = HORIZONS.get(trade["horizon_key"], {})
        horizon_label = h.get("label", trade["horizon_key"])
        filename = f"{trade['ticker']}_{trade['id']}_view.png"
        current_price = float(df["Close"].iloc[-1])

        markers = None
        try:
            from swingbot.core.analytics.journal import JournalStore
            entry = JournalStore().get(trade["id"])
            if entry and entry.get("mfe_r") is not None:
                opened = df.index[df.index.searchsorted(trade["opened_at"][:10])]
                closed_key = trade.get("closed_at", trade["opened_at"])[:10]
                window = df.loc[trade["opened_at"][:10]:closed_key]
                if not window.empty:
                    is_bull = trade["direction"] == "bullish"
                    mfe_date = window["High"].idxmax() if is_bull else window["Low"].idxmin()
                    mae_date = window["Low"].idxmin() if is_bull else window["High"].idxmax()
                    mfe_price = float(window.loc[mfe_date, "High" if is_bull else "Low"])
                    mae_price = float(window.loc[mae_date, "Low" if is_bull else "High"])
                    markers = {
                        "mfe": (mfe_date, mfe_price), "mfe_r": entry.get("mfe_r"),
                        "mae": (mae_date, mae_price), "mae_r": entry.get("mae_r"),
                    }
        except Exception as _je:
            log.debug("Could not compute MFE/MAE markers for trade %s: %s", trade.get("id"), _je)

        return generate_trade_chart(
            trade["ticker"], df, trade["entry"], trade["stop_loss"], trade["take_profit"],
            trade["direction"], trade["strategy"], horizon_label, config.TRADE_CHART_DIR, filename=filename,
            currency_symbol=get_currency_symbol(trade["ticker"], config.CURRENCY_SYMBOL),
            target2=trade.get("target2"),
            trendline_lookback=h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS),
            target_sources=trade.get("target_sources"),
            stop_sources=trade.get("stop_sources"),
            horizon=h,
            market_price=current_price,
            markers=markers,
        )
    except Exception as e:
        log.warning("Could not regenerate chart for trade %s: %s", trade.get("id"), e)
        return None
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_plan_chart_overlays.py -q`
Expected: all pass. Full suite: `python -m pytest tests/ -q` — green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/trade_chart.py swingbot/core/scanning/embeds.py tests/test_plan_chart_overlays.py
git commit -m "feat: MFE/MAE markers on closed-trade charts"
```

### Task B34: Chart cache module

**Files:**
- Create: `swingbot/core/charts/cache.py`
- Test: `tests/test_chart_cache.py`

**Interfaces:**
- Produces: `cached_chart(key_parts: dict, render_fn: Callable[[str], str], cache_dir=None) -> str` — key = sha256 of sorted `key_parts` JSON; if `exports/chart_cache/{key}.png` exists, return it; else call `render_fn(target_path)` and return. `purge(max_age_days=7, cache_dir=None) -> int` deletes stale files, returns count.

- [ ] **Step 1: Failing test**

```python
# tests/test_chart_cache.py
import os
import time

from swingbot.core.charts.cache import cached_chart, purge


def _counting_render(calls):
    def render(target_path):
        calls.append(target_path)
        with open(target_path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"0" * 100)  # minimal PNG-ish blob, enough to test file existence/size
        return target_path
    return render


def test_cached_chart_renders_once_for_same_key(tmp_path):
    calls = []
    key = {"trade_id": "T1", "closed_at": "2026-07-05", "v": 3}
    p1 = cached_chart(key, _counting_render(calls), cache_dir=str(tmp_path))
    p2 = cached_chart(key, _counting_render(calls), cache_dir=str(tmp_path))
    assert p1 == p2
    assert len(calls) == 1
    assert os.path.exists(p1)


def test_cached_chart_rerenders_on_changed_key(tmp_path):
    calls = []
    p1 = cached_chart({"trade_id": "T1", "v": 3}, _counting_render(calls), cache_dir=str(tmp_path))
    p2 = cached_chart({"trade_id": "T1", "v": 4}, _counting_render(calls), cache_dir=str(tmp_path))
    assert p1 != p2
    assert len(calls) == 2


def test_purge_removes_stale_files(tmp_path):
    calls = []
    p1 = cached_chart({"k": "a"}, _counting_render(calls), cache_dir=str(tmp_path))
    old_time = time.time() - 8 * 86400
    os.utime(p1, (old_time, old_time))
    removed = purge(max_age_days=7, cache_dir=str(tmp_path))
    assert removed == 1
    assert not os.path.exists(p1)
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_chart_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.charts.cache'`.

- [ ] **Step 3: Implement**

```python
# swingbot/core/charts/cache.py
"""
Content-hash PNG cache for expensive chart renders. A closed trade's
chart never changes once the trade is closed (same OHLCV window, same
levels), so re-rendering it every time !trade/tradecharts/a Discord
button asks for it is pure waste -- this caches by a hash of whatever
"identity" fields the caller considers immutable (trade_id + closed_at
+ a schema version number, so a future chart-format change still
busts every old cache entry automatically), not by a TTL.
"""
import hashlib
import json
import os
import time
from typing import Callable

from swingbot import config

DEFAULT_CACHE_DIR = os.path.join(config.EXPORT_DIR, "chart_cache")


def _key_hash(key_parts: dict) -> str:
    canonical = json.dumps(key_parts, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def cached_chart(key_parts: dict, render_fn: Callable[[str], str], cache_dir: str = None) -> str:
    """Returns the cached PNG path for `key_parts` if it already exists;
    otherwise calls `render_fn(target_path)` (which must write to
    `target_path` and return it, matching every existing chart-render
    function's own `(..., out_dir, filename) -> path` shape when given
    that this function IS effectively picking out_dir/filename for it)
    and returns the freshly rendered path."""
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)
    key = _key_hash(key_parts)
    target_path = os.path.join(cache_dir, f"{key}.png")
    if os.path.exists(target_path):
        return target_path
    return render_fn(target_path)


def purge(max_age_days: int = 7, cache_dir: str = None) -> int:
    """Deletes every cached PNG whose mtime is older than max_age_days.
    Returns the count removed. Safe to call every scan cycle -- a
    directory listing + stat per file is negligible next to a single
    chart render."""
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    if not os.path.isdir(cache_dir):
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for name in os.listdir(cache_dir):
        path = os.path.join(cache_dir, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError:
            continue
    return removed
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_chart_cache.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/cache.py tests/test_chart_cache.py
git commit -m "feat: content-hash chart cache"
```

### Task B35: Cache wired into hot paths

**Files:**
- Modify: `swingbot/core/scanning/embeds.py` (`regenerate_chart_for_trade`), `swingbot/commands/trades.py` (`tradecharts_cmd` :288), `swingbot/commands/stats.py` (B18/B21 chart attachments), scan-loop purge call
- Test: `tests/test_chart_cache.py`

**Interfaces:**
- Produces: closed-trade chart keys `{trade_id, closed_at, "v": 3}` (immutable → cache forever until purge); analytics chart keys `{kind, snapshot_built_at}`; `purge()` runs once per scan cycle. Live open-trade charts stay uncached (price moves).

- [ ] **Step 1: Failing test**

```python
# tests/test_chart_cache.py (append)
def test_regenerate_chart_for_trade_only_renders_closed_trade_once(tmp_path, monkeypatch):
    """Not a full integration test of regenerate_chart_for_trade (that
    needs real price data) -- verifies the caching CONTRACT: calling
    cached_chart twice with the same closed-trade key and a counting
    render function only renders once, exactly the pattern
    regenerate_chart_for_trade must follow for a closed trade."""
    calls = []
    key = {"trade_id": "T99", "closed_at": "2026-07-05T00:00:00+00:00", "v": 3}
    p1 = cached_chart(key, _counting_render(calls), cache_dir=str(tmp_path))
    p2 = cached_chart(key, _counting_render(calls), cache_dir=str(tmp_path))
    assert p1 == p2
    assert len(calls) == 1
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_chart_cache.py -v -k only_renders_closed_trade_once`
Expected: PASS (this locks in the contract Step 3 below wires real call sites to follow — Task B34 already implements `cached_chart` correctly; this task's own work is entirely in the wiring, not `cache.py` itself).

- [ ] **Step 3: Implement**

In `embeds.py`'s `regenerate_chart_for_trade`, wrap the render in `cached_chart` **only when the trade is closed** (an `"open"` trade's chart must never be cached — price and the "current price" marker move every tick):

```python
def regenerate_chart_for_trade(trade: dict) -> str | None:
    from swingbot.core.charts.cache import cached_chart

    def _render(_target_path_unused=None):
        # (existing body of this function, unchanged -- computes df,
        # markers, and calls generate_trade_chart exactly as before,
        # returning the path generate_trade_chart itself decided on via
        # its own out_dir/filename args, NOT _target_path_unused --
        # generate_trade_chart's filename is already deterministic
        # (f"{ticker}_{id}_view.png"), so cached_chart's own target_path
        # is only used for the cache LOOKUP, not as the render
        # destination.)
        ...  # body from Task B33, unchanged

    if trade.get("status") in ("win", "loss", "closed"):
        cache_key = {"trade_id": trade["id"], "closed_at": trade.get("closed_at"), "v": 3}
        # cached_chart's own file check is keyed on ITS OWN target_path,
        # not generate_trade_chart's filename -- so this wraps the whole
        # regenerate call and, on a cache hit, returns generate_trade_chart's
        # already-known deterministic path directly rather than invoking
        # cached_chart's render_fn/target_path machinery at all: simpler
        # and avoids a redundant file copy between two paths.
        import os
        from swingbot.core.charts.cache import _key_hash, DEFAULT_CACHE_DIR
        deterministic_path = os.path.join(config.TRADE_CHART_DIR, f"{trade['ticker']}_{trade['id']}_view.png")
        if os.path.exists(deterministic_path):
            return deterministic_path
    return _render()
```

This reads more naturally as: check for the deterministic filename's existence directly (since `generate_trade_chart` already writes to a stable, trade-id-keyed filename — there is no separate cache-directory copy needed for this particular hot path). Simplify the implementation to exactly that — no `cached_chart`/`_key_hash` import needed here at all:

```python
def regenerate_chart_for_trade(trade: dict) -> str | None:
    deterministic_path = os.path.join(config.TRADE_CHART_DIR, f"{trade['ticker']}_{trade['id']}_view.png")
    if trade.get("status") in ("win", "loss", "closed") and os.path.exists(deterministic_path):
        return deterministic_path
    try:
        df = get_daily_data(trade["ticker"])
        ...  # unchanged body from Task B33, still writing to `filename = f"{trade['ticker']}_{trade['id']}_view.png"`
    except Exception as e:
        log.warning("Could not regenerate chart for trade %s: %s", trade.get("id"), e)
        return None
```

`swingbot/core/charts/cache.py`'s `cached_chart`/`purge` remain the right tool for the **analytics** charts (Task B18/B21), which have no natural stable filename to check for existence the way a trade-id-keyed chart does — those genuinely need the content-hash approach since their "identity" is a snapshot timestamp, not a fixed id. Wire `stats.py`'s chart attachments through it:

```python
# in stats.py, stats_cmd (Task B18/B19) -- attach the equity curve, cached by snapshot build time
from swingbot.core.charts.cache import cached_chart
from swingbot.core.charts.analytics_charts import render_equity_curve

chart_path = cached_chart(
    {"kind": "equity_curve", "snapshot_built_at": snap["built_at"]},
    lambda target: render_equity_curve(snap["equity_curve"], os.path.dirname(target), filename=os.path.basename(target)),
)
await ctx.send(embed=embed, file=discord.File(chart_path, filename=os.path.basename(chart_path)))
```

(same pattern for `calibration_cmd`'s `render_calibration` attachment, keyed `{"kind": "calibration", "snapshot_built_at": ...}` — or, since `!calibration` recomputes from live trades rather than the snapshot, key it off the count and latest `closed_at` of the trades it computed from instead: `{"kind": "calibration", "n": len(closed), "latest": closed[-1].get("closed_at")}`.)

Wire `purge()` into the scan loop: in `swingbot/commands/scanning.py`'s `_session_scan_tick` (`:382`), after `await _send_alerts(channel, alerts)`, add:

```python
    from swingbot.core.charts.cache import purge
    await asyncio.to_thread(purge)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_chart_cache.py -q`
Expected: all pass. Full suite: `python -m pytest tests/ -q` — green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/embeds.py swingbot/commands/stats.py swingbot/commands/scanning.py tests/test_chart_cache.py
git commit -m "perf: chart caching on closed-trade + analytics charts"
```

### Task B36: Async render audit

**Files:**
- Modify: `swingbot/commands/stats.py`, `swingbot/commands/plans.py`, `swingbot/commands/views.py` — every render call
- Test: `tests/test_stats_commands.py`

**Interfaces:**
- Produces: all chart renders inside command handlers/views run via `await asyncio.to_thread(...)`; a source-level tripwire test asserts no direct `generate_trade_chart(`/`render_` call in async defs of these modules (regex over the files, excluding `to_thread` lines).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stats_commands.py (append)
import re


def test_no_direct_chart_render_calls_outside_to_thread():
    """Regression tripwire: every call to generate_trade_chart(/render_*(
    inside stats.py, plans.py, or views.py must be preceded on the SAME
    physical line by 'to_thread' (i.e. wrapped in asyncio.to_thread(...)
    or awaited via a lambda/thread pool) -- a bare synchronous call
    inside an async def blocks the whole bot's event loop for the
    duration of a matplotlib render (measured 200-800ms per chart),
    stalling every other command and the scan loop's own message
    sends for that whole window."""
    import swingbot.commands.stats as stats_mod
    import swingbot.commands.plans as plans_mod
    import swingbot.commands.views as views_mod

    pattern = re.compile(r"(generate_trade_chart\(|render_\w+\()")
    for mod in (stats_mod, plans_mod, views_mod):
        import inspect
        for lineno, line in enumerate(inspect.getsource(mod).splitlines(), start=1):
            if pattern.search(line) and "def " not in line and "to_thread" not in line and "lambda" not in line:
                raise AssertionError(f"{mod.__name__}:{lineno}: direct chart render call not wrapped in to_thread: {line.strip()}")
```

Note the `"lambda" not in line` exemption: Task B35's `cached_chart(key, lambda target: render_equity_curve(...))` call passes a *lambda* as `render_fn` to `cached_chart` — the lambda body is only ever invoked from inside `cached_chart`, which this task's Step 3 wraps in `asyncio.to_thread` at the *call site* (`await asyncio.to_thread(cached_chart, key, render_fn)`), not by wrapping the lambda's own definition line. The regex is line-based and can't see that the enclosing `cached_chart(...)` call is itself inside a `to_thread` a few lines up, so the lambda line is explicitly exempted here rather than producing a false positive.

- [ ] **Step 2: Fix stragglers**

Run: `python -m pytest tests/test_stats_commands.py -v -k no_direct_chart_render`
Expected: FAIL initially — Task B35's `stats_cmd`/`calibration_cmd` call `cached_chart(...)` directly (not wrapped), and `views.py`'s `chart_button` (Task B9) already calls `generate_trade_chart` via `asyncio.to_thread` (written correctly from the start) so that one line passes already.

Fix `stats.py`'s `stats_cmd` and `calibration_cmd` (from Tasks B18/B21/B35) by wrapping the `cached_chart(...)` call itself in `asyncio.to_thread`:

```python
    import asyncio
    chart_path = await asyncio.to_thread(
        cached_chart,
        {"kind": "equity_curve", "snapshot_built_at": snap["built_at"]},
        lambda target: render_equity_curve(snap["equity_curve"], os.path.dirname(target), filename=os.path.basename(target)),
    )
```

Grep for any other straggler across all three files: `Grep "generate_trade_chart\(|render_\w+\(|cached_chart\(" swingbot/commands/stats.py swingbot/commands/plans.py swingbot/commands/views.py` and wrap each result found outside an already-`to_thread`-wrapped line the same way.

- [ ] **Step 3: Run**

Run: `python -m pytest tests/test_stats_commands.py -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add swingbot/commands/stats.py swingbot/commands/plans.py swingbot/commands/views.py tests/test_stats_commands.py
git commit -m "perf: chart renders off the event loop"
```

---

# Phase B5 — Digest + wrap-up (Tasks B37–B38)

### Task B37: Daily Top-Plans digest

**Files:**
- Modify: `swingbot/commands/scanning.py` (the scan `@tasks.loop` `session_scan`/`_session_scan_tick` :362-382 — post-scan hook, next to the retrospective trigger), `swingbot/config.py` (2 Fields)
- Test: `tests/test_digest.py`

**Interfaces:**
- Produces: after the LAST scan cycle of a session (reuse the session-window check that triggers the retrospective — `_check_session_transition`'s `active == False` edge, the same "session just closed" moment `daily_recap` fires 15 minutes after), post to `DISCORD_CHANNEL_TRADES_ID`: `"📌 Top plans today"` + up to `DIGEST_MAX_PLANS` compact embeds from `top_plans` (Task B17) — VALIDATED plans only in the digest (WEAK still visible in `!plans`/alerts; digest is the curated shortlist). Fields: `DAILY_DIGEST_ENABLED` (checkbox, default false), `DIGEST_MAX_PLANS` (number 1–10, default 3), section "Discord Alerts". Pure helper `digest_payload(plans, today, max_n) -> list` under test.

- [ ] **Step 1: Failing test**

```python
# tests/test_digest.py
import datetime as dt
import types

from swingbot.commands.scanning import digest_payload

TODAY = dt.date(2026, 7, 11)


def _plan(ticker, badge="VALIDATED", status="PENDING", quality_score=50):
    return types.SimpleNamespace(
        plan_id=f"id-{ticker}", ticker=ticker, status=status, badge=badge, tier="A",
        quality_score=quality_score, direction="bullish", entry_type="market",
        trigger_price=100.0, stop_loss=95.0, tp1=110.0, tp2=None,
        regime_aligned=True, created_at="2026-07-11",
    )


def test_digest_payload_excludes_weak_caps_and_ranks():
    plans = [
        _plan("AAA", badge="WEAK", quality_score=95),   # excluded despite high quality -- WEAK
        _plan("BBB", badge="VALIDATED", quality_score=90),
        _plan("CCC", badge="VALIDATED", quality_score=70),
        _plan("DDD", badge="VALIDATED", quality_score=50),
        _plan("EEE", badge="VALIDATED", quality_score=30),
    ]
    payload = digest_payload(plans, TODAY, max_n=3)
    assert [p.ticker for p in payload] == ["BBB", "CCC", "DDD"]


def test_digest_payload_empty_when_no_validated_plans():
    plans = [_plan("AAA", badge="WEAK")]
    assert digest_payload(plans, TODAY, max_n=3) == []
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/test_digest.py -v`
Expected: FAIL — `ImportError: cannot import name 'digest_payload'`.

- [ ] **Step 3: Implement**

In `config.py`, add two Fields to the `"Discord Alerts"` section created in Task B3 (insert immediately after the `ALERT_EMBED_LAYOUT` Field):

```python
    Field("DAILY_DIGEST_ENABLED", "DAILY_DIGEST_ENABLED", "Discord Alerts", "Daily top-plans digest enabled",
          type="checkbox", default="false",
          help="Post a curated 'Top plans today' digest (VALIDATED plans only, ranked by follow score) "
               "to the alerts channel right after the trading session closes for the day. WEAK plans stay "
               "visible everywhere else (!plans, live alerts) -- the digest is deliberately the curated "
               "shortlist, not the full picture."),
    Field("DIGEST_MAX_PLANS", "DIGEST_MAX_PLANS", "Discord Alerts", "Digest max plans",
          type="number", default="3", min=1, max=10, step=1,
          help="How many plans the daily digest (and !top's own default, when no n is given) shows."),
```

In `swingbot/commands/scanning.py`, add the pure helper (near `_ordered_alerts`, added in Task B5):

```python
def digest_payload(plans: list, today, max_n: int) -> list:
    """VALIDATED-only, follow_score-ranked, capped at max_n -- the exact
    same top_plans() ranking (Task B17) with one extra filter: WEAK
    plans never appear in the curated digest even though they stay
    fully visible in !plans and in live alerts (this Part's Global
    Constraint: 'never suppress WEAK plans' applies to the FULL
    surface, not to this one deliberately-curated shortlist)."""
    from swingbot.commands.stats import top_plans

    validated_only = [p for p in plans if p.badge == "VALIDATED"]
    return top_plans(validated_only, max_n, today=today)
```

Wire the post-session hook. In `_check_session_transition` (`scanning.py`, currently fires the welcome/goodbye message on a session state flip), add the digest send right after the existing goodbye-message send, gated on `config.DAILY_DIGEST_ENABLED` and only on the "session just closed" edge (`active is False`):

```python
    try:
        await channel.send(message)
    except Exception as e:
        log.warning("Could not post session welcome/goodbye message: %s", e)

    if not active and config.DAILY_DIGEST_ENABLED:
        try:
            await _post_daily_digest(channel)
        except Exception as e:
            log.warning("Could not post daily top-plans digest: %s", e)

    _session_was_active = active
```

Add `_post_daily_digest`:

```python
async def _post_daily_digest(channel):
    import datetime as _dt

    from swingbot.core.plan_store import PlanStore
    from swingbot.commands.stats import _fake_item_from_plan
    from swingbot.core.scanning.embeds import build_embed
    from swingbot.commands.views import PlanActionView

    plans = PlanStore().all()
    top = digest_payload(plans, _dt.date.today(), config.DIGEST_MAX_PLANS)
    if not top:
        await channel.send("📌 **Top plans today** — no VALIDATED plans qualified today.")
        return

    await channel.send(f"📌 **Top plans today** — {len(top)} VALIDATED plan(s), ranked by follow score:")
    for plan in top:
        item = _fake_item_from_plan(plan)
        embed = build_embed(item, "", {"closed": 0}, None, None, layout="compact")
        view = PlanActionView(plan.plan_id, author_id=None)
        view.message = await channel.send(embed=embed, view=view)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_digest.py -q`
Expected: `2 passed`. Full suite: `python -m pytest tests/ -q` — green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/scanning.py swingbot/config.py tests/test_digest.py
git commit -m "feat: daily top-plans digest (flag-gated)"
```

### Task B38: Phase checkpoint — manual smoke

**Files:** Modify plan Progress block.

- [ ] **Step 1: Full suite**

Run:
```bash
python -m pytest tests/ -q
make check
```
Expected: both green — zero failures, zero new warnings introduced by this Part's 38 tasks.

- [ ] **Step 2: Live smoke in a test guild/channel**

Run the bot against a scratch Discord server (or the existing dev guild, off-hours) with `PLAN_ENGINE_V2=on` and a small watchlist, and walk through, in order:

1. `!plans` — confirm the live board renders, grouped by status heading, ranked highest-follow-score-first within each group; click each of the three filter dropdowns and the Refresh button; confirm the message edits in place each time and the filter persists across an unrelated click (e.g. picking Tier=A then clicking Refresh keeps Tier=A).
2. `!top 3` — confirm three compact embeds post, each with a `📊 Chart`/`🔍 Breakdown`/`⭐ Watch`/`🔕 Dismiss` panel; click Chart on one (expect an ephemeral chart image within a few seconds); click Breakdown (expect an ephemeral embed with quality/badge/follow-score/timeline sections); click Watch then run `!plans` again and confirm that plan now shows the `⭐` prefix; click Dismiss and confirm the buttons disappear but the embed text stays.
3. `!stats 30d` — confirm real numbers (not `None`) render even with a small trade sample; confirm the equity-curve image attaches.
4. `!lessons` — confirm at least one entry (from any already-closed trade in the test environment) renders with its `auto_lesson` text; `!lessons week` posts the weekly digest messages.
5. `!calibration` — confirm the tier table, decile summary, and (if any registry strategy has ≥20 live trades in this test environment) an edge-decay alert line all render.
6. Trigger one scan cycle (`!check` or wait for the scheduled tick) with the watchlist containing at least one ticker expected to produce a WEAK setup and one expected to produce a VALIDATED setup (cross-check against `data/validation_registry.json`): confirm the WEAK alert renders amber with the single-line caution field first, the VALIDATED alert renders in its tier color, both carry the `🧭 Follow score` field and a working `PlanActionView`, and — critically — the VALIDATED alert posts **before** the WEAK one regardless of scan discovery order (follow-score ordering, Task B5).
7. Check the bot process logs for `cache hit`/render-skip evidence: re-run `!trade ID` twice on the same already-closed trade and confirm the second call is visibly faster and the log shows the deterministic-filename short-circuit from Task B35 (add a temporary `log.debug("chart cache hit for %s", trade["id"])` at that branch if it isn't already logged, for this smoke check only — remove before commit if added purely for this verification).

- [ ] **Step 3: Update Progress block; commit**

Update the plan document's Progress block (top of the combined `2026-07-11-cockpit-v3.md` document, not this draft) to read:

```
- **Completed:** Plan A (A1-A31), Plan B (B1-B38)
- **Next:** Task C1
```

```bash
git add docs/superpowers/plans/2026-07-11-cockpit-v3.md
git commit -m "docs: discord ux v3 checkpoint"
```

