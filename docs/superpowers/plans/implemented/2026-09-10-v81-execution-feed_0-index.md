# v81 — Execution Feed Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-10-v81-execution-feed-design.md`
**Bump:** bot minor, ui patch
**Edge:** harvest

**Goal:** Turn the simple-alerts channel into an execution feed — an order
ticket per alert and a broker instruction per plan change, delivered at least
once — without changing any exit, fill, gate or sizing rule.

**Architecture:** A pure projection (`core/presentation/instructions.py`) turns
a plan plus an event into an `Instruction`; one renderer
(`core/scanning/execution_embeds.py`) turns that into an embed. `plan_manager`
stays the only writer of plans: it stamps events, emits `stop_moved`, queues
undelivered notices on the plan, and records deliveries through
`ack_notified`, which `trade_monitor` calls after each send.

**Tech Stack:** Python 3.11, discord.py 2.7.1, pytest (no pytest-asyncio —
coroutines run under `asyncio.run`), JSON persistence through `PlanStore`.

## Global Constraints

- No change to what the bot trades or how it exits. `swingbot/core/planning/lifecycle.py`
  and `swingbot/core/planning/exit_sim.py` end the plan with no diff; F3's
  parity test pins the manager.
- `plan_manager` is the only writer of `TradePlanV2` rows. The notifier never
  calls `PlanStore.update`.
- Delivery is at-least-once: a duplicate ping is acceptable, a lost one is not.
- `TRAIL_NOTIFY_MIN_R` defaults to `0.25`; the value used is clamped to `[0.01, 1.0]`.
- A notice older than 5 calendar days is dropped with one warning, never resent.
- Ticket share counts are whole shares, rounded down, from `account.compute_position_size`.
- The expiry date is always prefixed `≈` and counts weekdays only.
- No `discord.Color`/`discord.Colour` syntax outside `swingbot/core/presentation/`
  — type annotations included; `tests/presentation/test_no_adhoc_color.py` walks the AST.
- Per-task checks: `python scripts/dev/testrun.py file <one test file>`. The
  full suite runs once, in F8.
- Never hard-code a version number. F8 resolves both from `VERSION.json`.

## Before starting

- **v79's code must be on `main`** — v79 and this plan both edit
  `plan_manager.py`. Check: `git log --oneline main --grep="feat(v79)"` prints
  at least one line. If it prints nothing, F1 and F2 may proceed; stop before
  F3 and tell the human partner.
- Work in a worktree named after the plan stem:
  `.claude/worktrees/2026-09-10-v81-execution-feed/`, branch
  `2026-09-10-v81-execution-feed` (`docs/claude/document-lifecycle.md`). Run
  `git worktree list` first; never dispatch with `isolation: "worktree"` onto
  an existing worktree.

## Parts

| File | Tasks |
|---|---|
| `2026-09-10-v81-execution-feed_1-foundation.md` | F1 ledger fields, `breakeven_trigger`, config · F2 `instructions.py` |
| `2026-09-10-v81-execution-feed_2-manager.md` | F3 manager feed bookkeeping · F4 `ack_notified`, `run_notice_sweep` |
| `2026-09-10-v81-execution-feed_3-feed.md` | F5 ticket renderer and scan wiring · F6 routing and `trade_monitor` · F7 surface agreement, v67 note, preview · F8 verification, release, close-out |

## File map

| File | Change | Task |
|---|---|---|
| `swingbot/core/planning/plan_types.py` | `notified_stop`, `pending_notice`, `breakeven_trigger()` | F1 |
| `swingbot/config.py` | `TRAIL_NOTIFY_MIN_R` Field | F1 |
| `swingbot/core/presentation/instructions.py` | new — `Instruction`, `ticket_for`, `instruction_for`, helpers | F2 |
| `swingbot/core/planning/plan_manager.py` | feed bookkeeping, `resting_stop`, `stop_move_event`, notice re-send (F3); `Delivery`, `ack_notified`, `run_notice_sweep` (F4) | F3, F4 |
| `swingbot/core/scanning/execution_embeds.py` | new — `render`, `build_ticket_embed`, `build_instruction_embed` | F5 |
| `swingbot/core/scanning/alert_embeds.py` | `build_simple_alert` sends v2 items to the ticket | F5 |
| `swingbot/core/scanning/analyze.py` | `ScanItem.paper_logged`, `ScanItem.not_logged_reason` | F5 |
| `swingbot/core/scanning/scan_run.py` | sets both at the paper-trade decision | F5 |
| `swingbot/core/scanning/lifecycle_embeds.py` | `notify_plan_events` routes to the feed, returns deliveries | F6 |
| `swingbot/commands/scanning/loops.py` | `trade_monitor` acknowledges deliveries; sweeps with no open trade | F6 |
| `tests/presentation/test_surface_agreement.py` | the feed's stop agrees with `plan_view` | F7 |
| `docs/superpowers/plans/2026-08-29-v67-json-to-postgres_2b-trading-state-plans.md` | P2-07 note and round-trip fields | F7 |
| `scripts/dev/preview_execution_feed.py` | new — prints every instruction | F7 |

## Parallelisation

- **Sequential:** F1 → F2 — F2 imports `breakeven_trigger`, which F1 adds.
- **Group A (parallel, after F2):** F3, F5 — disjoint files (`plan_manager.py`
  and `tests/planning/test_plan_manager_feed.py`, against `execution_embeds.py`,
  `alert_embeds.py`, `analyze.py`, `scan_run.py` and their tests). F3 consumes
  F1 only; F5 consumes F2 only. F3 also waits on v79.
- **Sequential:** F4 after F3 (same file). F6 after F4 and F5 — it imports
  `Delivery`, `STOP_EVENTS`, `NOTICE_EVENTS` and `build_instruction_embed`. F7
  after F4 and F5 — the surface test imports `resting_stop`, `stop_move_event`
  and `instruction_for`. F8 last.

## Planning findings, recorded in the spec in this plan's commit

1. `notified_status="UNSENT"` became `pending_notice`, the whole undelivered
   event. A pre-TP1 close appends no leg to `legs_realized`, so its exit price
   exists only in the event; FILLED also had no re-send path.
2. `effective_stop` became a new `resting_stop` for the stop rule. A PARTIAL
   row persisted before v39 has no `working_stop`, and `effective_stop` returns
   the original risk stop there — the display bug v73 removed.
3. Field `min`/`max` bind only the admin API (`admin/api_v1/system.py:154`),
   not `.env` loading, so the clamp lives in `plan_manager.trail_notify_min_r()`.
4. `trade_monitor` returns before the manager tick when no trade is open
   (`loops.py:531-533`) — the state right after the last position closes — so
   it runs `run_notice_sweep` alone there.
5. The break-even formula was inline in `_step_active`. It moves to
   `plan_types.breakeven_trigger`, so the manager and the ticket read one copy;
   that makes F1 → F2 sequential where the spec had them parallel.
6. The spec's example date was wrong: 17 Sep 2026 is a Thursday.

## Progress

- [x] F1 — ledger fields, `breakeven_trigger`, `TRAIL_NOTIFY_MIN_R`
- [x] F2 — `instructions.py`
- [x] F3 — manager feed bookkeeping
- [x] F4 — `ack_notified`, `run_notice_sweep`
- [x] F5 — ticket renderer and scan wiring
- [x] F6 — routing and `trade_monitor`
- [x] F7 — surface agreement, v67 note, preview (the human partner reads the preview)
- [x] F8 — full suite, release, close-out

**F8 findings, recorded 2026-09-15:**

1. The merge into `main` (`f8fa6e19`) landed clean (no `CONFLICT` markers) but
   silently combined this branch's `_feed_bookkeeping(plan, new_events,
   regular, now)` call with a same-day, unrelated main refactor
   (`40f74c08`, "simplify poll-window coverage") that deleted the local
   `regular` variable `poll()` computed it from — an undefined-name bug
   pyflakes caught in CI, not locally (the pre-merge full run was green
   because it ran before the merge existed). Fixed in `8c0aeec9`: `regular`
   is reintroduced as `is_regular_session(now) if config.INTRADAY_RTH_ONLY
   else True`, matching this branch's original three-way gate — decoupled
   from `_step()`'s gating, which main's refactor deliberately made
   RTH-independent. A first attempt (`50e02d8c`'s sibling, since reworked)
   dropped the `INTRADAY_RTH_ONLY` escape hatch and broke every test that
   runs with it `False`; both are in `8c0aeec9`'s message.
2. `alert_embeds.py`'s `build_simple_alert` referenced `config.PLAN_ENGINE_V2`
   with no `config` import in scope — another merge-time gap, fixed in
   `50e02d8c`.
3. `notify_plan_events` only ever logged delivery *failures*; a successful
   post was silent, so this task's own Step 5 verification (grep prod logs
   for a `delivered stop_moved` line) had nothing to match. Added the
   missing success-path log line in `6a87aa9e`.
4. **Deferred, not cut:** Step 5's post-deploy log check. Deploy (image
   `sha-6a87aa9e48ec`) landed 2026-09-15 09:09 UTC — pre-market (05:09 ET),
   well before the 09:30 ET regular-session open `is_regular_session` gates
   stop-move detection on — so no `stop_moved` catch-up had a chance to
   fire yet. Both containers came up healthy on the right image; the human
   partner should re-run the Step 5 grep after 09:30 ET today and compare
   against the admin Plans page as described there.
