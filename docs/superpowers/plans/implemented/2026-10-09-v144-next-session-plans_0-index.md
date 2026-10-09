# v144 Next-session plans: Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part whole**: pull one task with `/task-brief V144-4` or `grep -n "^### Task V144-4:" -A 400 docs/superpowers/plans/implemented/2026-10-09-v144-next-session-plans_*.md`.

**Bump:** bot minor
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/implemented/2026-10-09-v144-next-session-plans-design.md`](../../specs/implemented/2026-10-09-v144-next-session-plans-design.md) (as amended in `a52cc4bd`: stop-entry candidates only, market candidates as watch names, `origin` on the trade record too, invalidated/risk_cap decided in session, wrap-up time from the NYSE close, only `valid_session` promoted)

**Goal:** At 23:30 Berlin, Sunday to Thursday, scan the watchlist on today's closed daily bar and issue tomorrow's stop-entry plans as a segregated `origin="next_session"` cohort. Each plan is valid for one NYSE session and is cancelled with a stated reason if not filled by that session's close. A wrap-up posts after the close. The regular lane is unchanged.

**Architecture:** One new field triple on `TradePlanV2` (`origin`, `valid_session`, `cancel_reason_message`) and `origin` on the trade record. `valid_session` is promoted to an indexed column (`v144_001`) for the per-session query. The one-session window is the v119 compression mechanism generalised: `PlanManager._session_window` runs for any plan with an eligible session, and `_eligible_session` returns `valid_session` when it is set. A pure classifier (`planning/session_expiry.py`) names the cancellation reason from D's bars. The pooled figures stay byte-identical because `ledger.is_main`/`is_weak` and the readers the ledger rule misses all require `origin is None`. The 23:30 run (`scanning/outlook_run.py`) reuses the live pieces: `analyze._scan_one` with a no-monitoring `ScanIO`, `qualify.qualify_short_item` with no debounce, `dedup` and the live sort. Each accepted item then goes one of three ways: a `stop_entry` plan is issued, a market plan is listed as a watch name, a plan-stage rejection is listed as a near-miss. Two minute loops in `commands/scanning/loops.py` (`next_session_scan`, `next_session_wrapup`) drive it and post through `commands/scanning/outlook.py`.

**Tech Stack:** Python 3.11, discord.py, pandas, SQLAlchemy Core + Alembic (Postgres), Flask, pytest.

## Where to work

- **Branch and worktree:** `2026-10-09-v144-next-session-plans` at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v144-next-session-plans`. V144-1 Step 0 creates it with the `worktree-lifecycle` skill. Every task runs there. Name the worktree in every subagent dispatch, and after each task run `git -C E:/Documents/Private/Projects/Discord-Bot status --short` to confirm the main tree is unchanged.
- **Skills:** `schema-change` before V144-1 and V144-2. `no-lookahead` before V144-3, V144-4 and V144-11 (they decide what a bar knew). `alert-surface` before V144-5, V144-9, V144-10 and V144-11. `worktree-lifecycle` before creating, merging and removing the worktree.
- **Production:** nothing in this plan touches the Hetzner VM. The feature ships inert (`NEXT_SESSION_SCAN_ENABLED=false`). Turning it on is the partner's call after merge, through `mirror-prod`. The Alembic revision runs at the next deploy like every other revision.

## Parts

| Part | File | Tasks | Content |
|---|---|---|---|
| 0 | `_0-index` (this file) | none | Header, constraints, the open point's answer, parallelisation, file map |
| 1 | [`_1-model-lifecycle`](2026-10-09-v144-next-session-plans_1-model-lifecycle.md) | V144-1 .. V144-5 | Fields, the `valid_session` column, the expiry classifier, the generalised window, cancel notices |
| 2 | [`_2-isolation-overlap`](2026-10-09-v144-next-session-plans_2-isolation-overlap.md) | V144-6 .. V144-9 | Pooled isolation, the admin cohort filter, config and session arithmetic, the overlap line |
| 3 | [`_3-outlook-close-out`](2026-10-09-v144-next-session-plans_3-outlook-close-out.md) | V144-10 .. V144-13 | Digest/card/wrap-up rendering, the outlook run, the loops, the full suite |

## The spec's open point, resolved

**Are `market_data/1h` (hourly) bars fresh at D's close + 15 min? No.**
- `market_data_refresh` (`swingbot/commands/scanning/loops.py:750`) wakes every `MARKET_DATA_REFRESH_MINUTES` (default 60).
- `data_refresh.is_stale` decides from the CSV's mtime against `REFRESH_HOURS["hourly"] = 4.0`, so at D's close the hourly file can miss D's last 4–5 RTH bars.

The decision, as amended into the spec: neither the classifier nor the wrap-up fetches hourly bars.
- `session_expiry.hourly_session_bar` uses the hourly cache only when its last RTH bar on D starts within an hour of D's close.
- Otherwise `session_expiry.daily_session_bar` uses D's daily bar from `PlanManager.daily_frame_fn`. Daily bars are RTH-only, so their high/low is exactly what `never_triggered` needs.
- With neither bar, the code is `no_session_data`.

**One correction to the amended spec, found while writing this plan.** The spec says the classifier "never fetches", but `PlanManager.daily_frame_fn` is `plan_manager._daily_frame` → `marketdata.data.get_daily_data`, which is a network fetch (Alpaca, then yfinance). So the classifier makes at most one daily fetch per outlook plan, once, at expiry. It runs inside the trade-monitor tick, off the event loop (`asyncio.to_thread`). A failed fetch reads as "no daily bar".

## Frozen readings (how the spec's wording maps to code)

| Spec wording | Code reading |
|---|---|
| "the closed daily bar of the run date" | the bar of `outlook_session.signal_session(run_date)`, the last NYSE session on or before the run date. Read literally, the spec fails on Sunday, which is a run day with no bar: Sunday reads Friday's bar, and Thanksgiving Thursday reads Wednesday's. "The daily bar for the run date is missing" means that session's bar is missing for the regime ticker. |
| "today's closed daily bar" | `outlook_run.closed_frames`: a cached daily CSV is used only if written **after** the run date's close (`data_refresh.is_stale(..., max_age_hours=<hours since close>)`); otherwise the symbol is fetched (`fetch._fetch_cold_frames`). A frame whose last bar is not the run date is dropped. The live scan's cache-first crawl (`fetch._load_cached_daily`, 6h freshness) is **not** used: a CSV written mid-session holds a partial bar, which breaks the spec's NO-LOOKAHEAD claim. |
| "same gates apply unchanged" | `analyze._scan_one` (requirements, hard filters, opex) and `qualify.qualify_short_item` (sector RS, RS gate, plan build incl. the 2% hard cap). **No earnings blackout runs.** The live scan has none wired: `edge.gates.in_earnings_blackout` has no caller (`analyze.py:278` says so). Adding one would be a new filter. |
| near-miss | a fully-qualifying item whose `qualify` verdict is `Rejected(stage="plan")`. Reason text: `<plan_v2_rejected> (stop <x>% from entry)`, the same words `scan_run._skip_rejected_plan` logs. |
| watch name | an accepted item whose `plan_v2.entry_type != "stop_entry"` |
| "already exists" | `outlook_run.outlook_open_tickers()`: open plans and open trades with `origin == "next_session"` |
| dollar risk | `account.compute_position_size(trigger, stop)["shares"] × |trigger − stop|` |
| regime line | `scanning.regime.get_market_regime(frame, symbol).label` for SPY and QQQ, plus the weekly phrase |
| context line | `outlook_context.context_line`: weekly from the daily frame resampled `W-FRI` (close vs 20-week SMA, last two weekly lows); hourly from the hourly cache's last 7 bars. Display only. |
| `never_triggered` when D's bars show the trigger was reached but no poll filled it | code stays `never_triggered`; message: `High 102.05 reached the 102.00 trigger between polls; no live print filled it` |
| `risk_cap` message | `Gapped to 104.10 past the 102.00 trigger; ...` when the fill differs from the trigger, else `Triggered at ...`. The spec's "at the open" is not knowable from the event detail. |
| wrap-up "posts once all of D's evening plans are terminal" | terminal = no plan for D still `PENDING`. A D with zero outlook plans posts nothing (the digest already said so) and is marked done. |
| cohort filter in the admin | API only: `?origin=next_session` on every scoped `/analytics/*` route, plus `GET /api/v1/analytics/cohort`. **No frontend task**: the spec's `Bump:` is `bot minor` only. A UI panel would be a `ui` bump and a separate plan. |

## Global Constraints

- **Phase 1 only.** No new signal, filter or threshold. Only `stop_entry` candidates are issued. Market candidates are watch names and never plans or trades. Phase 2's `next_session_stop` screen is not in this plan.
- **The regular lane is unchanged.** Its expiry, dedup, `already_open`, reversal path and alerts stay as they are, except for the display-only `⚠ Overlap` field. A regular plan's `_step_pending` output is pinned identical with and without an outlook plan on the same ticker. The compression short's tests stay green untouched.
- **Pooled figures filter `origin is None`.** That means ExpR, win rate, the snapshot, the dashboard, the journal-driven E31/E32 overrides, the soak verdict and the plan funnel. They are byte-identical with and without an outlook trade (V144-6 pins it). Badges come from the backtest registry (`registry.get_badge`) and cannot move.
- **Schema.** `origin` and `cancel_reason_message` live in `doc` (no migration, `schema-evolution.md` § add). `valid_session` is promoted with revision `v144_001`, `down_revision = "v116_002"`, the `plans_valid_session_idx` index and one `PROMOTION_REASONS` line. No read-time upcasting.
- **Complexity.** Every new or changed function stays below 15 (`python -m radon cc -s -n C <files>`). Several legacy functions are already at or over 15 and must not gain a branch: `scan_run._sync_run_scan` F(100), `alert_embeds.build_embed` E(33), `TradeLog.log_trade` C(15), `PlanManager._on_event` C(15), `queries._plan_lifecycle` C(20), `dashboard.dashboard` D(25). Edits there are a keyword pass-through or one unconditional call, nothing more.
- **Ships inert.** `NEXT_SESSION_SCAN_ENABLED` defaults to `false`. `NEXT_SESSION_SCAN_TIME` defaults to `23:30` Berlin.
- **Session arithmetic in ET.** RTH open and close come from `market.session` (`RTH_OPEN`, `session_close`, `nyse_calendar`). Never hard-code a Berlin hour.
- **Tests.** Per task: `python scripts/dev/testrun.py file <the task's test file>`, or `... changed` when a task edits a shared module. The full suite runs once, in V144-13.
- **Commits.** One commit per task on the worktree branch, message ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never commit on `main` from a task.

## Parallelisation

Every edge below states its reason. "Disjoint" means no shared file *and* no symbol one task introduces that the other consumes.

- **Sequential start:** V144-1 runs first and alone. It introduces `tracking/origin.py` (`NEXT_SESSION`, `is_regular`, `in_cohort`, `ALL`) and the `TradePlanV2` fields that every other task consumes.
- **Group 1 (parallel, after V144-1):** V144-2, V144-3, V144-6 and V144-8. Their files are disjoint:
  - V144-2: `db/schema.py`, the migration, `db/repositories/plans.py`, `planning/plan_store.py`
  - V144-3: new `planning/session_expiry.py`
  - V144-6: `tracking/ledger.py`, `admin/api_v1/dashboard.py`, `analytics/journal.py` (`entries` only, after V144-1's `build_entry` edit), `admin/api_v1/trades.py`, `analytics/pnl_calendar.py`, `commands/stats.py`, `admin/api_v1/analytics.py`
  - V144-8: `config.py`, `.env.example`, new `scanning/outlook_session.py`
- **Group 2 (parallel, after Group 1):** V144-4, V144-5, V144-7, V144-9 and V144-10. Their files are disjoint (`plan_manager.py`; `lifecycle_embeds.py` + `instructions.py`; `analytics/scope.py` + `partials.py` + new `analytics/cohort.py` + `admin/api_v1/analytics.py`; new `scanning/lane_overlap.py` + `scan_run.py` + `short_run.py`; `presentation/kinds.py` + new `scanning/outlook_types.py`, `outlook_context.py`, `outlook_embeds.py`). Sequential edges into the group:
  - V144-4 after V144-3: it calls `session_expiry.classify_expiry`, `in_session_message` and `code_for`.
  - V144-5 after V144-3: it reads the `REASON_MESSAGE`/`REASON_CODE` detail keys defined there.
  - V144-7 after V144-6, because both edit `admin/api_v1/analytics.py`; and after V144-3, because `cohort.py` imports `session_expiry.cancel_reason`.
  - V144-9 after V144-1: it reads trade `origin`.
  - V144-10 after V144-3: the wrap-up text reads `session_expiry.cancel_reason`.
- **Sequential tail:**
  - V144-11 after V144-8, V144-9 and V144-10. It consumes `outlook_session.target_session`, `lane_overlap.overlap_line`, `outlook_types`, `outlook_context` and `outlook_embeds.decorate_card`, and it edits `short_run.py` after V144-9 did.
  - V144-12 after V144-2 (`PlanStore.for_session`), V144-8 (the config fields and `outlook_session`), V144-10 (`digest_text`, `wrapup_text`, `Kind.OUTLOOK*`) and V144-11 (`run_outlook`).
  - V144-13 last: the full suite runs over everything.

## File map

| File | Task | Change |
|---|---|---|
| `swingbot/core/tracking/origin.py` | V144-1 | **new** — `NEXT_SESSION`, `ORIGINS`, `ALL`, `origin_of`, `is_regular`, `in_cohort` |
| `swingbot/core/planning/plan_types.py` | V144-1 | `TradePlanV2.origin`, `.valid_session`, `.cancel_reason_message` |
| `swingbot/core/tracking/performance.py` | V144-1 | `log_trade(origin=)`, `open_trade_for_ticker(ticker, origin=None)` |
| `swingbot/core/analytics/journal.py` | V144-1, V144-6 | `build_entry` copies `origin`; `JournalStore.entries(cohort=)` |
| `swingbot/core/db/schema.py`, `migrations/versions/v144_001_plans_valid_session.py`, `db/repositories/plans.py`, `planning/plan_store.py` | V144-2 | promote `valid_session`; `for_session` |
| `swingbot/core/planning/session_expiry.py` | V144-3 | **new** — the reason catalogue, the classifier, `cancel_reason` |
| `swingbot/core/planning/plan_manager.py` | V144-4 | `_eligible_session`, `_has_session_window`, `_session_window` (renamed from `_compression_window`), `_expire_window`, `_window_reason`, `_annotate_outlook`, `hourly_frame_fn`, `_cached_hourly`, `_on_event` origin pass-through |
| `swingbot/core/scanning/lifecycle_embeds.py`, `presentation/instructions.py` | V144-5 | the cancel notice states the catalogue reason |
| `swingbot/core/tracking/ledger.py`, `admin/api_v1/dashboard.py`, `admin/api_v1/trades.py`, `analytics/pnl_calendar.py`, `commands/stats.py`, `admin/api_v1/analytics.py` | V144-6 | pooled isolation |
| `swingbot/core/analytics/scope.py`, `analytics/partials.py`, `analytics/cohort.py` (**new**), `admin/api_v1/analytics.py` | V144-7 | `origin` scope param, cohort endpoint |
| `swingbot/config.py`, `.env.example`, `swingbot/core/scanning/outlook_session.py` (**new**) | V144-8 | two fields; session arithmetic |
| `swingbot/core/scanning/lane_overlap.py` (**new**), `scan_run.py`, `short_run.py` | V144-9 | the ⚠ overlap field on regular alerts |
| `swingbot/core/presentation/kinds.py`, `scanning/outlook_types.py`, `outlook_context.py`, `outlook_embeds.py` (**new**) | V144-10 | digest, card, wrap-up text |
| `swingbot/core/scanning/outlook_run.py` (**new**), `short_run.py` | V144-11 | the 23:30 run; `_log_trade(origin=)` |
| `swingbot/commands/scanning/outlook.py` (**new**), `loops.py` | V144-12 | the two loops and their posting |

## Task list

- V144-1: Origin vocabulary, plan fields and trade `origin`
- V144-2: Promote `plans.valid_session` (`v144_001`) and `PlanStore.for_session`
- V144-3: The cancellation-reason classifier (`session_expiry`)
- V144-4: Generalise the one-session window to outlook plans
- V144-5: Cancel notices state the catalogue reason
- V144-6: Keep every pooled figure on `origin is None`
- V144-7: The admin cohort filter and `/analytics/cohort`
- V144-8: Config fields and session arithmetic (`outlook_session`)
- V144-9: The ⚠ overlap line on regular alerts (`lane_overlap`)
- V144-10: Digest, card and wrap-up rendering
- V144-11: The outlook run (`outlook_run`)
- V144-12: The `next_session_scan` and `next_session_wrapup` loops
- V144-13: Full-suite verification
