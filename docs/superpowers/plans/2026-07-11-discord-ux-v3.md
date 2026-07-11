# Plan B — Discord Experience v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Discord surface answer one question at a glance — *which plan should I follow right now?* — via a unified embed design language keyed to tier/badge, `follow_score`-ranked alerts and boards, interactive buttons (chart / breakdown / watch / dismiss), new `!top` / `!stats` / `!lessons` / `!calibration` commands, richer plan charts (risk/reward bands, trigger arrows, trail paths, MFE/MAE markers), a daily Top-Plans digest, and chart-render caching so none of it slows the scan loop.

**Architecture:** A tiny theme module (`embed_theme.py`) centralizes colors/chips/ordering so every embed builder stops inventing its own; `analytics.rank.follow_score` (Plan A) is the only ranking authority; all interactivity uses discord.py `View`s following the existing `TradesPaginator` conventions (author-lock, timeout, disable-on-timeout); chart upgrades extend `generate_trade_chart` behind an optional `plan=` kwarg so legacy callers are untouched; a PNG cache keyed by content hash sits under `exports/chart_cache/`.

**Tech Stack:** discord.py 2.7.1 (`discord.ui.View/Button/Select`), matplotlib/mplfinance with the existing `chart_style.py` palette, pytest ≥8. **No new dependencies.**

**Prerequisites:** Plan-engine-v2 complete (badged embeds, `commands/plans.py` board, PlanStore/PlanManager); **Plan A merged** (`swingbot/core/analytics/*` — rank, metrics, snapshots, journal, insights).

## Progress

> - **Branch:** `feature/discord-ux-v3` (from `main` after Plan A merge)
> - **Completed:** —
> - **Next:** Task B1

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

- [ ] **Step 1: Failing test**

```python
# tests/test_embed_theme.py
from swingbot.core.scanning import embed_theme as th

def test_plan_color_weak_is_amber_regardless_of_tier():
    assert th.plan_color("WEAK", "A").value == 0xE67E22
    assert th.plan_color("VALIDATED", "A").value == 0x2ECC71

def test_follow_chip():
    assert th.follow_chip(82.0) == "▰▰▰▰▱ 82"
    assert th.follow_chip(0.0) == "▱▱▱▱▱ 0"

def test_fmt_price():
    assert th.fmt_price(1234.5, "€") == "€1234.50"
    assert th.fmt_price(0.4321, "$") == "$0.4321"
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement. Step 4: PASS. Step 5: Commit** — `feat: embed theme module`

### Task B2: Theme applied to `build_embed`

**Files:**
- Modify: `swingbot/core/scanning/embeds.py` (`build_embed` ~:310, `confidence_color` usage ~:160)
- Test: `tests/test_embeds_v3.py`

**Interfaces:**
- Produces: embed color comes from `plan_color(badge, tier)` when the item carries a v2 plan (falls back to existing `confidence_color` otherwise); title gains `tier_chip` + `badge_chip` prefix: `"🅰 ✅ VALIDATED · 📈 LONG NVDA"`; fields reordered to `SECTION_ORDER`.

- [ ] **Step 1: Failing test** — build an item fixture with `plan.badge="WEAK"`, assert `embed.colour.value == 0xE67E22` and title starts with the chips; legacy item without plan → old color path still used.
- [ ] **Step 2–4: Implement, run full suite (existing embed tests from v2 Phase 6 must stay green), commit** — `feat: tier/badge-themed scan embeds`

### Task B3: Compact / detailed layouts

**Files:**
- Modify: `swingbot/core/scanning/embeds.py`, `swingbot/config.py` (new Field), callers passing layout (`scan_engine` alert path)
- Test: `tests/test_embeds_v3.py`

**Interfaces:**
- Produces: `build_embed(..., layout: str = "detailed")`. `"compact"` renders: headline, the ANSI plan table (`_build_trade_plan_table` unchanged), one-line quality (`Tier A · 82/100 · ✅ VALIDATED (OOS N=206 WR 81.6%)`), follow chip — and drops confluence/changes/branches sections. Config Field `ALERT_EMBED_LAYOUT` (select `detailed|compact`, section "Discord Alerts", default `detailed`, hot-reloadable) feeds the scan alert path.

- [ ] **Step 1: Failing test** — compact embed has ≤ 5 fields and no `"What changed"` field; detailed keeps current field set.
- [ ] **Step 2–4: Implement + Field entry, PASS, commit** — `feat: compact alert layout behind ALERT_EMBED_LAYOUT`

### Task B4: Trigger-aware explanation wording

**Files:**
- Modify: `swingbot/core/explain.py` (`build_explanation` :38)
- Test: `tests/test_embeds_v3.py`

**Interfaces:**
- Produces: `build_explanation(..., plan=None)` — when a v2 plan with `entry_type="stop_entry"` is passed, line 1 reads `"Waits for a BUY STOP above {trigger}"` (SELL STOP below for bearish) instead of implying immediate entry; market-entry plans read `"Enters at market"`. No plan → wording unchanged.

- [ ] **Step 1: Failing test** — stop-entry bullish plan → explanation contains `"BUY STOP above"`; no plan → unchanged first line.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: trigger-aware explanations`

---

# Phase B1 — Alert stream (Tasks B5–B8)

### Task B5: Alerts post in follow-score order

**Files:**
- Modify: `swingbot/commands/scanning.py` (`_send_alerts` :204 — alert dispatch loop, currently scan order)
- Test: `tests/test_embeds_v3.py`

**Interfaces:**
- Consumes: `analytics.rank.rank_plans`.
- Produces: within one scan cycle, alert items carrying plans are stamped `regime_aligned` (from the scan's regime check vs plan direction) and dispatched in `rank_plans` order, highest first; non-plan legacy alerts keep original order after them.

- [ ] **Step 1: Failing test** — feed a fake dispatch list of 3 items (scores 30/90/60 via badge/quality fixtures) into the ordering helper (extract `_ordered_alerts(items, today) -> list` for testability), assert 90-60-30 order.
- [ ] **Step 2–4: Implement `_ordered_alerts` + call it in `_send_alerts`, PASS, commit** — `feat: alerts ranked by follow_score`

### Task B6: "Why follow this" line

**Files:**
- Modify: `swingbot/core/scanning/embeds.py`
- Test: `tests/test_embeds_v3.py`

**Interfaces:**
- Produces: field `🧭 Follow score` on plan-carrying embeds: `follow_chip(score)` + one line per non-zero component, e.g. `"✅ validated source +40 · quality 82 → +33 · regime aligned +10 · fresh +10"`. Component values come from a new `rank.follow_breakdown(plan, today) -> list[tuple[str, float]]` added here (same weights as `follow_score`; add to `swingbot/core/analytics/rank.py` with its own test in `tests/test_rank.py`).

- [ ] **Step 1: Failing tests** — `follow_breakdown` sums to `follow_score` (property test over 5 fixtures); embed contains the field with the chip.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: follow-score breakdown on alerts`

### Task B7: WEAK block goes compact

**Files:**
- Modify: `swingbot/core/scanning/embeds.py` (WEAK caution block from v2 Task 74)
- Test: `tests/test_embeds_v3.py`

**Interfaces:**
- Produces: WEAK plans render a single-line caution `⚠️ WEAK — OOS WR {wr}% (N={n}), below the 80% bar. Extra care.` as the FIRST field (was a multi-line block), plus the amber color from B2. Exact stats still verbatim from `badge_stats`. VALIDATED plans unaffected.

- [ ] **Step 1: Failing test** — WEAK embed's first field name starts `⚠️ WEAK`, value is one line containing `N=` and `%`.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: compact WEAK caution line`

### Task B8: Consistent footer + timestamps

**Files:**
- Modify: `swingbot/core/scanning/embeds.py` (`build_embed`, `build_closed_trade_embed` :430, `build_near_close_embed` :586)
- Test: `tests/test_embeds_v3.py`

**Interfaces:**
- Produces: shared `apply_footer(embed, *, plan_id=None)` in `embed_theme.py` — sets `embed.timestamp = discord.utils.utcnow()` and footer `"{disclaimer} · plan {short_id}"` (8-char id when given). All three builders call it; disclaimer text unchanged.

- [ ] **Step 1: Failing test** — all three embeds have `.timestamp` set and identical disclaimer prefix in footer.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: unified embed footer/timestamp`

---

# Phase B2 — Interactive views (Tasks B9–B14)

### Task B9: `PlanActionView` skeleton + Chart button

**Files:**
- Create: `swingbot/commands/views.py`
- Test: `tests/test_views.py`

**Interfaces:**
- Produces: `class PlanActionView(discord.ui.View)` — `__init__(self, plan_id: str, author_id: int, *, timeout=180)`; author-lock via `interaction_check` (non-author → ephemeral `"Not your panel."`); `on_timeout` disables all children. Button `📊 Chart` (`custom_id="plan:chart"`): loads plan from PlanStore, renders its chart via `asyncio.to_thread(generate_trade_chart, ...)`, replies with the file ephemeral. Buttons added in B10/B11 follow this shape.

- [ ] **Step 1: Failing test** — instantiate view; assert 1 child, `timeout == 180`; simulate `interaction_check` with wrong user id → False. (Interaction plumbing is tested at this unit level throughout — no live gateway in tests.)
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: PlanActionView with chart button`

### Task B10: Breakdown button

**Files:** Modify `views.py`; test `tests/test_views.py`

**Interfaces:**
- Produces: button `🔍 Breakdown` (`custom_id="plan:breakdown"`) — ephemeral embed showing `quality_breakdown` (one line per `(component, points)`), `badge_stats` verbatim, follow-score breakdown (B6), and `status_history` timeline (last 5 transitions, `"{ts} {from}→{to} ({reason})"`).

- [ ] **Step 1: Failing test** — extract pure helper `breakdown_embed(plan) -> discord.Embed`; assert one field per section and every quality component line present.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: quality/lifecycle breakdown button`

### Task B11: Watch / Dismiss buttons

**Files:** Modify `views.py`; create starred store inside `views.py`; test `tests/test_views.py`

**Interfaces:**
- Produces: `⭐ Watch` toggles the plan id in `data/starred_plans.json` (list of ids, `jsonio`-persisted; module fns `star_plan(plan_id)`, `unstar_plan(plan_id)`, `starred_ids() -> set`); `🔕 Dismiss` removes the view from the message (`edit(view=None)`) — the embed stays. Starred plans get a `⭐` prefix and sort-first within equal follow scores on the board (B15).

- [ ] **Step 1: Failing test** — star/unstar roundtrip through fresh reads; `starred_ids()` is a set.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: watch/dismiss plan buttons`

### Task B12: Views attached to scan alerts

**Files:**
- Modify: `swingbot/commands/scanning.py` (`_send_alerts` :204 message send)
- Test: `tests/test_views.py`

**Interfaces:**
- Produces: every alert message for a plan-carrying item is sent with `view=PlanActionView(plan.plan_id, author_id=0)` where author-lock is relaxed to *any* user for scan alerts (`author_id=None` → `interaction_check` returns True). Legacy alerts get no view.

- [ ] **Step 1: Failing test** — `PlanActionView(pid, author_id=None)`: `interaction_check` True for any user.
- [ ] **Step 2–4: Implement + wire, PASS, commit** — `feat: interactive scan alerts`

### Task B13: `PlanBoardView` filters

**Files:** Modify `views.py`; test `tests/test_views.py`

**Interfaces:**
- Produces: `class PlanBoardView(discord.ui.View)` — `discord.ui.Select` "Status" (options All/PENDING/ACTIVE/PARTIAL), Select "Tier" (All/A/B/C), Select "Badge" (All/VALIDATED/WEAK), `🔄 Refresh` button. Holds a `render_fn(status, tier, badge) -> tuple[str, discord.Embed]` callback supplied by `plans.py`; selection re-renders via `interaction.response.edit_message`.

- [ ] **Step 1: Failing test** — instantiate with stub render_fn; assert 4 children; call the internal `_apply(status="ACTIVE", ...)` → stub received filters.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: plan board filter view`

### Task B14: Board pagination

**Files:** Modify `views.py`; test `tests/test_views.py`

**Interfaces:**
- Produces: `PlanBoardView` gains Prev/Next buttons reusing the `TradesPaginator` page logic (extract shared `paginate(items, page, per_page) -> tuple[list, int, int]` into `views.py`; `TradesPaginator` may adopt it later — do not modify trades.py here). Page size 8 plans.

- [ ] **Step 1: Failing test** — `paginate(list(range(20)), page=2, per_page=8)` → items 16–19, `(page 2 of 3)`.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: plan board pagination`

---

# Phase B3 — Commands (Tasks B15–B25)

### Task B15: `!plans` live ranked board

**Files:**
- Modify: `swingbot/commands/plans.py` (the v2 lifecycle board)
- Test: `tests/test_plans_board.py`

**Interfaces:**
- Produces: `!plans` with no args renders the live board: plans from `PlanStore.all()` with status in {PENDING, ACTIVE, PARTIAL}, ordered by `rank_plans` (starred-first tiebreak from B11), one line each: `"{⭐?}{tier_chip}{badge_chip} {ticker} {direction} · {status} · follow {score} · entry {trigger} SL {sl} TP1 {tp1}"`, grouped under status headings, wrapped in `PlanBoardView`. Pure renderer `render_board(plans, *, status, tier, badge, page, today) -> tuple[str, discord.Embed]` is the testable unit and the `render_fn` for B13.

- [ ] **Step 1: Failing test** — 3 fixture plans (one per status), assert grouping headers, rank order inside groups, filter `tier="A"` drops others.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: live ranked !plans board`

### Task B16: `!plans` arguments

**Files:** Modify `plans.py`; test `tests/test_plans_board.py`

**Interfaces:**
- Produces: `!plans [status] [tier:A|B|C] [badge:validated|weak] [TICKER]` argument parsing (`_parse_board_args(args) -> dict`, case-insensitive); the historical query mode (existing behavior with dates/ticker per current `plans_cmd`) still triggers whenever `from:`/`to:` args are present — zero regression.

- [ ] **Step 1: Failing test** — `_parse_board_args(("active","tier:a","NVDA"))` → `{"status":"ACTIVE","tier":"A","ticker":"NVDA"}`; `("from:2026-01-01",)` → `{"legacy": True}`.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: !plans filters`

### Task B17: `!top`

**Files:**
- Create: `swingbot/commands/stats.py` (new cog-style module, registered in `bot_core.py` like existing command modules)
- Test: `tests/test_stats_commands.py`

**Interfaces:**
- Produces: `!top [n]` (default `config.DIGEST_MAX_PLANS`) — the n highest-`follow_score` PENDING/ACTIVE plans as compact embeds (B3 layout) each with its follow-breakdown line and `PlanActionView`. Pure helper `top_plans(plans, n, today) -> list` reused by the digest (B37).

- [ ] **Step 1: Failing test** — `top_plans` returns n items, ranked, excludes CLOSED/CANCELLED.
- [ ] **Step 2–4: Implement command + registration, PASS, commit** — `feat: !top ranked plans command`

### Task B18: `!stats` embed

**Files:** Modify `stats.py`; test `tests/test_stats_commands.py`

**Interfaces:**
- Consumes: `snapshots.load_snapshot()` (fallback: `refresh_snapshot()` then load).
- Produces: `!stats` — embed with overall block (N, WR, expectancy R, profit factor, Sharpe, max DD, current streak), a `by tier` mini-table (ANSI block), a `by strategy` top-5 table, and the equity-curve chart image (B26) attached. Renderer `stats_embed(snap) -> discord.Embed` is the unit under test.

- [ ] **Step 1: Failing test** — fixture snapshot → embed contains `"Win rate"`, `"Expectancy"`, tier table lines; None-heavy snapshot (no trades) renders `"—"` not `"None"`.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: !stats analytics embed`

### Task B19: `!stats` period filters

**Files:** Modify `stats.py`; test `tests/test_stats_commands.py`

**Interfaces:**
- Produces: `!stats [7d|30d|90d|ytd|all]` — period filters closed trades by `closed_at` then computes via Plan A metrics directly (snapshot only serves `all`). `_since(period, today) -> date | None` helper.

- [ ] **Step 1: Failing test** — `_since("30d", date(2026,7,11)) == date(2026,6,11)`; `"ytd"` → Jan 1; `"all"` → None.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: !stats period filters`

### Task B20: `!lessons`

**Files:** Modify `stats.py`; test `tests/test_stats_commands.py`

**Interfaces:**
- Produces: `!lessons [n|week]` — default: last 5 journal entries as `"{outcome emoji} {ticker} {r_realized:+.2f}R — {auto_lesson}"` lines + tag cloud; `week` posts `insights.weekly_digest` messages.

- [ ] **Step 1: Failing test** — renderer over 3 fixture entries → 3 lines each containing the lesson text.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: !lessons journal command`

### Task B21: `!calibration`

**Files:** Modify `stats.py`; test `tests/test_stats_commands.py`

**Interfaces:**
- Produces: `!calibration` — tier-calibration table (tier / n / live WR / expected band / ✅|❌|—), decile summary line, edge-decay alert lines from `insights.edge_decay_report`, plus the calibration chart (B28) attached.

- [ ] **Step 1: Failing test** — renderer with one failing tier and one drift alert → contains `❌` and the strategy name.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: !calibration command`

### Task B22: `!journal` notes

**Files:** Modify `stats.py`; test `tests/test_stats_commands.py`

**Interfaces:**
- Produces: `!journal TRADE_ID your note text…` → `JournalStore.set_note`; confirmation or `"No journal entry for that id"`; `!journal TICKER` lists that ticker's entries (reuses B20 renderer with a filter).

- [ ] **Step 1: Failing test** — note set path returns confirmation string; unknown id path returns the error string.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: !journal notes`

### Task B23: Help catalog overhaul

**Files:**
- Modify: `swingbot/bot_core.py` (`COMMANDS_BY_CATEGORY`, `COMMAND_USAGE` ~:201)
- Test: `tests/test_stats_commands.py`

**Interfaces:**
- Produces: new category `📐 Analytics` (top, stats, lessons, calibration, journal); `!plans` finally listed (explorer finding: registered in `COMMAND_USAGE` but missing from `COMMANDS_BY_CATEGORY`); every new command has a usage string.

- [ ] **Step 1: Failing test** — assert each new command name appears in `COMMANDS_BY_CATEGORY` values and `COMMAND_USAGE` keys.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: help catalog covers analytics + plans`

### Task B24: New slash commands

**Files:**
- Modify: `swingbot/commands/slash.py`
- Test: `tests/test_stats_commands.py`

**Interfaces:**
- Produces: `/plans` (status/tier choices), `/top` (n int), `/stats` (period choices), `/lessons` — all invoking the prefix callbacks via the `Context.from_interaction` pattern `/check` already uses (slash.py:164), NOT the channel-message hack.

- [ ] **Step 1: Failing test** — assert the four app commands exist on `bot.tree` after setup (instantiate bot_core test bot fixture).
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: slash parity for analytics commands`

### Task B25: Fix legacy slash bridges

**Files:** Modify `slash.py` (`/ticker` :234, `/backtest` :246, `/backtestwatchlist` :284, `/trades` :315, `/performance` :335, `/watchlist` :349)
- Test: `tests/test_stats_commands.py`

**Interfaces:**
- Produces: the six bridge commands that today post a literal `!command` string into the channel instead call their prefix callbacks via `Context.from_interaction` (same as `/check`). User-visible behavior otherwise identical.

- [ ] **Step 1: Failing test** — source-level assertion: `slash.py` contains no `interaction.channel.send("!` occurrences (regression tripwire), and the six commands still exist on the tree.
- [ ] **Step 2–4: Implement, PASS, commit** — `fix: slash bridges invoke callbacks directly`

---

# Phase B4 — Charts v2 (Tasks B26–B36)

### Task B26: Equity-curve render

**Files:**
- Create: `swingbot/core/charts/analytics_charts.py`
- Test: `tests/test_analytics_charts.py`

**Interfaces:**
- Produces: `render_equity_curve(curve: dict, out_dir: str, *, spy_overlay: list | None = None) -> str` — dark-theme (chart_style constants) line chart of Plan A's `equity_curve` points, drawdown shaded beneath in `DOWN_COLOR` alpha 0.15, optional SPY overlay dashed `MUTED_TEXT_COLOR`; saves PNG dpi 150 and returns path. All renderers in this module follow this signature shape: `(data, out_dir, **style) -> str`.

- [ ] **Step 1: Failing test** — render fixture curve into `tmp_path`, assert file exists and non-trivial size (>10 KB); no display backend needed (Agg).
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: equity curve chart`

### Task B27: R-multiple histogram render

**Files:** Modify `analytics_charts.py`; test `tests/test_analytics_charts.py`

**Interfaces:**
- Produces: `render_r_histogram(r_list: list[float], out_dir) -> str` — bins width 0.25R from −3R to +5R, losses `DOWN_COLOR` / wins `UP_COLOR`, vertical line at mean (expectancy) with label.

- [ ] **Step 1–4: Same test pattern (file exists), implement, PASS, commit** — `feat: R-multiple histogram chart`

### Task B28: Calibration chart render

**Files:** Modify `analytics_charts.py`; test `tests/test_analytics_charts.py`

**Interfaces:**
- Produces: `render_calibration(deciles: list[dict], out_dir) -> str` — bar chart of realized WR per score decile with an 80% target line; bars below target `DOWN_COLOR`, above `UP_COLOR`.

- [ ] **Step 1–4: Test, implement, PASS, commit** — `feat: calibration decile chart`

### Task B29: Strategy heatmap render

**Files:** Modify `analytics_charts.py`; test `tests/test_analytics_charts.py`

**Interfaces:**
- Produces: `render_strategy_heatmap(rows: list[StatRow-like dicts], out_dir, *, value="win_rate") -> str` — strategy × (win_rate, expectancy_r, n) table as an imshow heatmap, red→green centered at 80 for WR and 0 for ExpR, cell annotations.

- [ ] **Step 1–4: Test, implement, PASS, commit** — `feat: strategy heatmap chart`

### Task B30: Plan overlays — risk/reward bands

**Files:**
- Modify: `swingbot/core/charts/trade_chart.py` (`generate_trade_chart` :147 — add `plan=None` kwarg), `swingbot/core/charts/chart_style.py` (band alphas)
- Test: `tests/test_plan_chart_overlays.py`

**Interfaces:**
- Produces: `generate_trade_chart(..., plan: TradePlanV2 | dict | None = None)` — when given: horizontal shaded band entry↔stop in `STOP_COLOR` alpha 0.08 (risk), entry↔TP1 in `TARGET_COLOR` alpha 0.08, TP1↔TP2 in `TARGET2_COLOR` alpha 0.06 (when tp2). Constants `RISK_BAND_ALPHA=0.08`, `REWARD_BAND_ALPHA=0.08`, `RUNNER_BAND_ALPHA=0.06` in chart_style. Legacy calls (`plan=None`) render pixel-identically to today.

- [ ] **Step 1: Failing test** — render with a fixture plan on `make_ohlcv` data into tmp dir; assert file exists; render without plan also succeeds (regression).
- [ ] **Step 2–4: Implement (axhspan between levels), PASS, commit** — `feat: R:R shaded bands on plan charts`

### Task B31: Plan overlays — trigger arrow + status watermark

**Files:** Modify `trade_chart.py`; test `tests/test_plan_chart_overlays.py`

**Interfaces:**
- Produces: stop-entry plans draw an annotate-arrow at `trigger_price` on the last bar (`"BUY STOP"` / `"SELL STOP"` in `ENTRY_COLOR`); a status watermark (`plan.status`) bottom-right in `MUTED_TEXT_COLOR` alpha 0.5, 20 pt.

- [ ] **Step 1–4: Test (renders for PENDING stop-entry and market plans), implement, PASS, commit** — `feat: trigger arrow + status watermark`

### Task B32: Plan overlays — runner trail path

**Files:** Modify `trade_chart.py`; test `tests/test_plan_chart_overlays.py`

**Interfaces:**
- Produces: for PARTIAL plans, a dotted chandelier-trail line: `highest close since TP1 bar − trail_atr_mult × ATR(14)` per bar (reuse `plan_engine`'s ATR helper), drawn in `CURRENT_PRICE_COLOR`; needs `plan` + the df already passed. Non-PARTIAL → nothing.

- [ ] **Step 1–4: Test, implement, PASS, commit** — `feat: chandelier trail on PARTIAL charts`

### Task B33: Closed-trade MFE/MAE markers

**Files:** Modify `swingbot/core/scanning/embeds.py` (`regenerate_chart_for_trade` :404 → pass markers), `trade_chart.py`
- Test: `tests/test_plan_chart_overlays.py`

**Interfaces:**
- Produces: `generate_trade_chart(..., markers: dict | None = None)` where `markers={"mfe": (date, price), "mae": (date, price)}` draws ▲ `UP_COLOR` at MFE and ▼ `DOWN_COLOR` at MAE with `"+2.0R"`-style labels; `regenerate_chart_for_trade` computes them from the journal entry when present.

- [ ] **Step 1–4: Test, implement, PASS, commit** — `feat: MFE/MAE markers on closed-trade charts`

### Task B34: Chart cache module

**Files:**
- Create: `swingbot/core/charts/cache.py`
- Test: `tests/test_chart_cache.py`

**Interfaces:**
- Produces: `cached_chart(key_parts: dict, render_fn: Callable[[str], str], cache_dir=None) -> str` — key = sha256 of sorted `key_parts` JSON; if `exports/chart_cache/{key}.png` exists, return it; else call `render_fn(target_path)` and return. `purge(max_age_days=7, cache_dir=None) -> int` deletes stale files, returns count.

- [ ] **Step 1: Failing test** — counting render_fn: first call renders, second identical key doesn't; changed key re-renders; purge removes an artificially-old file.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: content-hash chart cache`

### Task B35: Cache wired into hot paths

**Files:**
- Modify: `swingbot/core/scanning/embeds.py` (`regenerate_chart_for_trade`), `swingbot/commands/trades.py` (`tradecharts_cmd` :288), `stats.py` (B18/B21 chart attachments), scan-loop purge call
- Test: `tests/test_chart_cache.py`

**Interfaces:**
- Produces: closed-trade chart keys `{trade_id, closed_at, "v": 3}` (immutable → cache forever until purge); analytics chart keys `{kind, snapshot_built_at}`; `purge()` runs once per scan cycle. Live open-trade charts stay uncached (price moves).

- [ ] **Step 1: Failing test** — regenerate same closed trade twice with a counting monkeypatched renderer → one render.
- [ ] **Step 2–4: Wire, PASS, commit** — `perf: chart caching on closed-trade + analytics charts`

### Task B36: Async render audit

**Files:**
- Modify: `swingbot/commands/stats.py`, `plans.py`, `views.py` — every render call
- Test: `tests/test_stats_commands.py`

**Interfaces:**
- Produces: all chart renders inside command handlers/views run via `await asyncio.to_thread(...)`; a source-level tripwire test asserts no direct `generate_trade_chart(`/`render_` call in async defs of these modules (regex over the files, excluding `to_thread` lines).

- [ ] **Step 1: Write the tripwire test — expect FAIL if any sync call slipped in. Step 2: Fix stragglers. Step 3: PASS. Step 4: Commit** — `perf: chart renders off the event loop`

---

# Phase B5 — Digest + wrap-up (Tasks B37–B38)

### Task B37: Daily Top-Plans digest

**Files:**
- Modify: `swingbot/commands/scanning.py` (the scan `@tasks.loop` :362 — post-scan hook, next to the retrospective trigger), `swingbot/config.py` (2 Fields)
- Test: `tests/test_digest.py`

**Interfaces:**
- Produces: after the LAST scan cycle of a session (reuse the session-window check that triggers the retrospective), post to `DISCORD_CHANNEL_TRADES_ID`: `"📌 Top plans today"` + up to `DIGEST_MAX_PLANS` compact embeds from `top_plans` (B17) — VALIDATED plans only in the digest (WEAK still visible in `!plans`/alerts; digest is the curated shortlist). Fields: `DAILY_DIGEST_ENABLED` (checkbox, default false), `DIGEST_MAX_PLANS` (number 1–10, default 3), section "Discord Alerts". Pure helper `digest_payload(plans, today, max_n) -> list` under test.

- [ ] **Step 1: Failing test** — mixed VALIDATED/WEAK plans → payload only VALIDATED, capped, ranked; empty when none.
- [ ] **Step 2–4: Implement + Fields + hook, PASS, commit** — `feat: daily top-plans digest (flag-gated)`

### Task B38: Phase checkpoint — manual smoke

**Files:** Modify plan Progress block.

- [ ] **Step 1: Full suite:** `python -m pytest tests/ -q` + `make check` green.
- [ ] **Step 2: Live smoke in a test guild/channel:** `!plans`, filter selects, `!top`, `!stats 30d`, `!lessons`, `!calibration`, chart buttons, a WEAK and a VALIDATED alert render (trigger a scan or post fixtures via a scratch script). Verify colors, chips, ordering, ephemeral responses, cache hits in logs.
- [ ] **Step 3: Update Progress block; commit** — `docs: discord ux v3 checkpoint`
