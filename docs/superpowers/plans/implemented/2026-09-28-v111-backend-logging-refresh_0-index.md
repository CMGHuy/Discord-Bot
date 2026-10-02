# v111 — Backend logging: one setup, named loggers, scan ids, lifecycle coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/superpowers/specs/2026-09-28-v111-backend-logging-refresh-design.md`](../specs/2026-09-28-v111-backend-logging-refresh-design.md)
**Bump:** bot patch
**Edge:** none (integrity)

**Goal:** Make production diagnosable from the log files alone. Both processes log through one root setup. Every line names its module logger and the scan it belongs to. A paper trade's life reads from `bot.log` at INFO. No caught exception is logged without its traceback.

**Architecture:** A new module `swingbot/core/infra/logsetup.py` owns the root logger: `configure_logging()` installs a console and a rotating-file handler (idempotent), and `apply_log_level()` is the only level setter. A `ContextVar` holds the scan id. `scan_context()` sets it around `run_scan`, and a `ScanIdFilter` on both handlers stamps it onto every record. `asyncio.to_thread` copies the context already. The two thread pools reached from a scan (`fetch.map_tickers`, the Alpaca router's `_pool`) submit through `with_current_context()`. Every module switches to `logging.getLogger(__name__)`. New INFO/DEBUG/WARNING lines are added at the decision and lifecycle sites the spec names. Existing lines gain `exc_info` where they log a caught exception, and a few change level or wording.

**Tech Stack:** Python 3.11 (`logging.getLevelNamesMapping`, `Formatter(defaults=)`), stdlib `logging`/`contextvars`, discord.py 2.x, pytest (`caplog`, `asyncio.run`, no pytest-asyncio), radon.

## Global Constraints

Copied from the spec. Every task's requirements include this section.

- Log format, both processes: `%(asctime)s [%(levelname)s] [%(scan_id)s] %(name)s: %(message)s`.
- `configure_logging(log_file, level, *, max_bytes, backups)` configures the **root** logger with a console `StreamHandler` and a `RotatingFileHandler`, and is idempotent (a second call never duplicates handlers).
- Bot: `config.LOG_FILE`, 5MB x3. Admin: `config.ADMIN_LOG_FILE`, 5MB x2. The ad-hoc handler wiring in `admin/app.py` is removed. Werkzeug and `app.logger` propagate to root.
- `apply_log_level(level)` is the only way to change the level. It is called at startup, on SIGHUP, by the config watcher, and by the scan-time auto-reload.
- `scan_id_var: ContextVar[str]`, default `"-"`. `scan_context(scan_id)` sets and resets it, wrapped around each scan run in `scan_run.py` (manual `!check`, the scheduled scan, the admin trigger and the weekend deep scan all enter through `run_scan`).
- Scan id: `s-` + HHMM + a two-character suffix (see resolved ambiguity 1).
- `ScanIdFilter` is attached to both handlers.
- Every module uses `log = logging.getLogger(__name__)`. No hard-coded `"swing-bot…"`/`"swingbot…"` names. Command modules stop importing the shared logger from `bot_core`.
- New INFO lines: plan transitions (armed, filled, break-even moved, TP1 hit, stopped, expired, invalidated) with ticker, plan id (8 chars), direction and the relevant price. Trade closed with outcome, realised R, hold days. Alert posted as `kind=<v110 Kind name> ticker=<T> channel=<name>`. Kill switch flipped. A risk limit hit.
- New DEBUG lines: dedup merges and gating rejects with the reason, and fetch misses and fallbacks (`yf_safe.py`, `alpaca_provider.py`, the router).
- New WARNING with `exc_info=True`: command errors (the user-facing `ctx.send("⚠️ …")` stays), and healthcheck cleanup failures in `presence.py` (bare `except: pass` becomes `except discord.HTTPException`, DEBUG for 404, WARNING otherwise).
- Every `log.warning/error` that logs a caught exception gains `exc_info=True`. `log.exception(..., exc)` drops the redundant `exc` argument.
- Level changes: "Alpaca miss" INFO → DEBUG. Batch price failures (`data.py`, `loops.py`) DEBUG → WARNING. Earnings inside the holding window WARNING → INFO.
- `retry.py` logs the full exception and gives up at WARNING with `exc_info`.
- "CHANNEL_ID not set" → "DISCORD_CHANNEL_TRADES_ID not set". "Config auto-reloaded" and "Scan interval hot-reloaded" are each logged once, at the site that performs the reload.
- Every function written or changed ends at cyclomatic complexity **< 15** (`python -m radon cc -s -n C <files>`). A legacy function already at 15 or more never gets worse. Baselines measured 2026-09-28: `_sync_run_scan` 108, `_session_scan_tick` 30, `config_watcher` 27, `_send_alerts` 26, `on_ready` 17, `trade_monitor` 16, `PlanManager.poll` 21, `PlanManager._on_event` 15, `_scan_one` 39, `TradeLog.check_near_tp_timeout` 42, `TradeLog.update_open_trades` 31, `TradeLog.close_if_live_price_hit` 20, `info.ticker_cmd` 15, `history.plans_cmd` 24, `data.scrapeall_cmd` 18.
- A refactor never changes behaviour. Every helper extracted here (`_run_scan_in_context`, `_reload_config_before_scan`, `_earnings_in_window`, `_live_price_batch`, `_reject_plan`, `_delete_healthcheck`) is a verbatim move plus the log change its task names.
- Nothing here changes which plans are produced, how they are sized, or how they exit.
- Never `cd` in Bash. Stage only the task's own files and commit with an explicit pathspec.

## Spec ambiguities resolved here (not design changes)

1. **Scan id suffix.** The spec says "a two-character suffix … (for example `s-1405a`)". The example has one character. The plan follows the rule, not the example: two characters from `[a-z0-9]`, for example `s-1405k3`. HHMM is local time from `time.localtime()`, the same clock `%(asctime)s` prints, so the id matches the timestamp beside it.
2. **Module path.** The spec names `swingbot/infra/logsetup.py`. The repo has no `swingbot/infra/`; the infra package is `swingbot/core/infra/` (with tests in `tests/infra/`). The module is `swingbot/core/infra/logsetup.py`.
3. **`run_in_executor` audit (spec §2).** No `run_in_executor` call exists in `swingbot/`. The context-losing equivalents are `ThreadPoolExecutor.submit/map`. The audit (V111-4) finds four pools. Two are reached from a scan and are converted: `fetch.map_tickers` and `providers/router._pool`. `market/events.warm_earnings_cache_background` is admin-only and `earnings_history.refresh_watchlist_earnings` is the weekly loop, so both are left alone. The spawned `ProcessPoolExecutor` children (`fetch._run_bounded`, the cold fetch) cannot inherit a ContextVar and have no log handlers. The parent logs their outcome inside the scan context.
4. **"Risk limit hit" (`risk_limits.py`).** `risk_limits.py` holds only pure predicates, called per candidate thousands of times per scan. A log there would be neither "a few per day" nor a decision. A risk limit is actually *hit* at two sites. The INFO line is PlanManager's `cancelled_risk_cap` transition (V111-8, "Plan risk cap hit"). The per-candidate scan rejection is `attach_plan_v2`'s `plan_v2_rejected = "risk_cap"`, logged at DEBUG with the other gate rejects (V111-11). `risk_limits.py` itself is unchanged.
5. **"Gating rejects" (`gating.py`).** `gating.passes_confluence` is called only by the backtest replays (`armed_replay.py`, `backtest_scenarios.py`), never by a live scan. The live gate decisions are `analyze.paper_trade_decision` and `attach_plan_v2`'s rejections, and those carry the DEBUG line (V111-11). `gating.py` is unchanged, which also keeps a per-bar log call out of the backtest hot loop.
6. **"Armed" transition.** `PlanManager` never creates plans. A plan is armed when the scan persists it (`scan_run.py`, `PlanStore().add(plan_v2)`). The formatting lives in `plan_manager.py` (`log_plan_armed`), as the spec places it, and the scan calls it after a successful add.
7. **`print()` sites.** `fmp_client.py:20` is inside the module docstring's usage example, not a call. There is nothing to convert. `backtest_wf.py:491,493` stay `print(..., flush=True)`. They are the per-symbol progress of `collect_portfolio_signals`, whose only callers are the CLI scripts `scripts/backtest/wf_run.py` and `reversal_ab.py`, and the `backtest-runner` agent reads that stdout. CLAUDE.md's long-run rule requires flushed progress there, and a log call would vanish in a script that never configures logging.
8. **Command errors.** "Command errors" means caught *exceptions* shown to the user. User-input errors (a bad date, wrong usage) are not logged: `bot_core.py:367`, `history.py:260`, `commands.py:34`, and the `ValueError` handlers in `account.py`/`stats.py`. `views.py`'s two button handlers reply through `interaction.followup.send`, and they count.
9. **"Config auto-reloaded" once.** The site that performs the reload is `config.reload()`. It already logs every changed value, **masked** for sensitive fields. The two caller lines (`scan_run.py`, `loops.config_watcher`) repeat it **unmasked**, so they are removed. "Scan interval hot-reloaded" lives only in `_apply_scan_interval_change`, and the config watcher calls that function instead of its inline copy.
10. **"Alert posted" scope.** The line fires for ticker-bearing pushed notifications: `_send_alerts` (full alert + simple mirror), `_post_daily_digest`, `notify_closed_trades`, `notify_near_close` and `notify_plan_events`. SYSTEM messages carry no ticker and are not "alerts". The `Kind` is read from the sent embed (v110's `PushEmbed`). V111-18 stops if the landed `PushEmbed` carries no kind (see OPEN in the hand-off).
11. **Werkzeug level.** Before v111, `admin/app.py` pinned `werkzeug` to INFO. Admin setup keeps that pin, so the Logs page still shows request lines when `LOG_LEVEL=WARNING`. This is behaviour preservation, not a new rule.

## Parts

| File | Phases | Tasks |
|---|---|---|
| `_1-setup.md` | Phase 1 — One setup and the scan id | V111-1 .. V111-5 |
| `_2-names.md` | Phase 2 — Logger names; Phase 3 — Lifecycle INFO (first half) | V111-6 .. V111-9 |
| `_3-coverage.md` | Phase 3 — Coverage (second half) | V111-10 .. V111-14 |
| `_4-fixes-release.md` | Phase 4 — Fixes to existing logs; Phase 5 — v110-gated; Phase 6 — Verification, release, close-out | V111-15 .. V111-21 |

Pull one task: `grep -n "^### Task V111-8" -A 160 docs/superpowers/plans/2026-09-28-v111-backend-logging-refresh_*.md`.

## Parallelisation

- **V111-1 first.** It creates `logsetup.py` and the `restore_root_logging` fixture in `tests/conftest.py`. V111-2, -3, -4 and -5 consume both.
- **Group A (parallel, after V111-1):** V111-2, V111-3, V111-4, V111-10, V111-13, V111-16.
  - V111-2: `swingbot/bot_core.py`, `tests/test_bot_core_logging.py`.
  - V111-3: `admin_ui.py`, `swingbot/admin/app.py`, `tests/admin/test_admin_logging.py`.
  - V111-4: `swingbot/core/scanning/scan_run.py` (`run_scan` only), `swingbot/core/scanning/fetch.py`, `swingbot/core/marketdata/providers/router.py`, and three new test files.
  - V111-10: `swingbot/core/edge/throttle.py`, `tests/edge/test_killswitch_log.py`.
  - V111-13: `swingbot/commands/{backtest,data,info,views,watchlist,history}.py`, `tests/commands/test_command_error_logging.py`.
  - V111-16: `swingbot/core/infra/retry.py`, `tests/infra/test_retry.py`.
  - The files are disjoint. V111-10, -13 and -16 consume nothing from V111-1 and may even start before it.
- **Group B (parallel, after V111-4):** V111-5 and V111-12.
  - V111-5 (`scan_run.py`, `loops.py`) edits `scan_run.py` after V111-4 did, which is its sequential edge.
  - V111-12 (`yf_safe.py`, `router.py`, `alpaca_provider.py`) edits `router.py` after V111-4 did.
  - The files are disjoint.
- **Sequential: V111-6 after V111-2, V111-4 and V111-5.** The rename sweep rewrites the logger line in `bot_core.py`, `scan_run.py` and `fetch.py`, which those tasks also edit. It creates `tests/infra/test_logger_names.py`.
- **Group C (parallel, after V111-6):** V111-7, V111-8, V111-9, V111-11.
  - V111-7: `swingbot/commands/scanning/{alerts,commands,loops,presence,recap}.py`, and it appends to `tests/infra/test_logger_names.py` (created by V111-6).
  - V111-8: `plan_manager.py`, `scan_run.py`, `tests/planning/test_plan_manager_logging.py`.
  - V111-9: `performance.py`, `tests/tracking/test_trade_closed_log.py`.
  - V111-11: `dedup.py`, `analyze.py`, `tests/scanning/test_decision_debug_logs.py`.
  - The files are disjoint. Each edits a module V111-6 renamed, which is the edge to V111-6.
- **Sequential: V111-14 after V111-7.** Both edit `presence.py`.
- **Sequential: V111-15 after every task above.** The `exc_info` sweep touches about 20 files across all of them. Its guard test must see their final call sites.
- **Sequential: V111-17 after V111-15.** Both edit `loops.py`, `scan_run.py` and `core/marketdata/data.py`.
- **Sequential: V111-18 after V111-17 and after v110 is merged to `main`.** It consumes v110's `Kind` enum (`swingbot/core/presentation/kinds.py`) and the `PushEmbed`/`push_kwargs` send path. It is the only task that depends on v110.
- **Sequential from here on:** V111-19 (the one full-suite run), then V111-20 (merge and release), then V111-21 (production verification and close-out).

**Cross-plan file overlap: merge carefully.** v110 (Discord notification identity) rewrites the send paths in `commands/scanning/alerts.py`, `loops.py`, `recap.py`, `presence.py` and `core/scanning/lifecycle_embeds.py` (and likely `alert_embeds.py` for its titles). These v111 tasks touch the same files:

| v111 task | Files shared with v110 | What v111 changes there |
|---|---|---|
| V111-5 | `loops.py` | `config_watcher` reload block |
| V111-6 | `alert_embeds.py`, `lifecycle_embeds.py` | the one `log = …` line |
| V111-7 | `alerts.py`, `loops.py`, `presence.py`, `recap.py` | the `bot_core` import line and a new `log = …` line |
| V111-14 | `presence.py` | the healthcheck delete loop |
| V111-15 | `alerts.py`, `loops.py`, `presence.py`, `recap.py`, `lifecycle_embeds.py` | `exc_info=True` on existing warning calls |
| V111-17 | `loops.py`, `alert_embeds.py` | trigger message, batch-price helper, docstring |
| V111-18 | `alerts.py`, `lifecycle_embeds.py` | a `log_posted(...)` call after each send |

Whichever plan merges second resolves these conflicts. The v111 edits are line-local, so on a conflict keep v110's send code and re-apply the v111 line.

Two more live plans share files:
- **v106 T13a** (Alpaca page-sized parallel batches) edits `providers/router.py` and `providers/alpaca_provider.py`, the same files as V111-4 and V111-12.
- **v109** edits `providers/router.py` (V109-4), `scanning/fetch.py` (V109-7) and `core/marketdata/data.py` (V109-5), the same files as V111-4, V111-15 and V111-17.

All parallel tasks share one worktree. Each stages only its own files and commits with an explicit pathspec. If a commit fails on `index.lock`, wait and retry. Never `git add -A`.

## Conventions for every task

- V111-1..V111-19 run in the worktree `.claude/worktrees/2026-09-28-v111-backend-logging-refresh` on branch `2026-09-28-v111-backend-logging-refresh`, created from `main` before V111-1 (`worktree-lifecycle` skill). V111-20 merges it. Run every command from the worktree root.
- Before V111-18, merge `main` into the branch once v110 has landed (`worktree-lifecycle` skill; a merge that resolved conflicts gets one `python scripts/dev/testrun.py fast` before V111-18 continues).
- Per-task check: `python scripts/dev/testrun.py file <the task's test file(s)>`, never `full`. V111-19 is the one full run.
- Complexity check per task: `python -m radon cc -s -n C <the task's modified .py files>`. Every function the task wrote or changed must be absent from the output (below C means < 11), or sit at C with a value < 15, or be a listed legacy function at or below its baseline.
- Load the `alert-surface` skill before V111-4, V111-5, V111-8, V111-11 and V111-17, which touch the scan pipeline (`scan_run.py`, `analyze.py`). No task changes a computed value, so `no-lookahead` is not required. The reviewer still checks that no expression feeding a plan changed.
- New tests pin logger names through the module object (`caplog.at_level(logging.INFO, logger=pm.log.name)`), never a string literal. That keeps them correct on either side of V111-6's rename.
- Root-logger tests use the `restore_root_logging` fixture (V111-1). Any test that calls `configure_logging` without it leaks a tmp-file handler into every later test in the worker.
