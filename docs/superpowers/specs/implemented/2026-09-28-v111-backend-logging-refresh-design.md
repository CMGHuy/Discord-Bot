# v111 — Backend logging: one setup, named loggers, scan ids, lifecycle coverage

**Version:** ui 1.21.0 · bot 1.10.4
**Bump:** bot patch
**Edge:** none (integrity)
**Plan:** not yet written

This spec is the companion to v110 (Discord notification identity). The
"alert posted" log in §3 names notification kinds by v110's `Kind` enum, so
that task runs after v110 lands. Every other task is independent of v110.
`Edge: none (integrity)`: nothing here changes which plans are produced or
how they trade. It makes production diagnosable.

## Why

A survey of logging (2026-09-28) found:

- **The admin process never configures the root logger.** `admin_ui.py`
  does not import `bot_core`, and `admin/app.py` attaches `admin.log` only to
  `app.logger` and `werkzeug`. Module loggers in the admin process drop INFO
  (for example `events/stream.py`, `spa.py`). WARNING and above go to stderr
  via `lastResort`, never to `admin.log`.
- **`bot.log` lines carry no logger name** (`"%(asctime)s [%(levelname)s]
  %(message)s"`), so a line cannot be traced to its module.
- **Logger names are stale or mixed:**
  - `"swing-bot.scan_engine"` in six modules; that shim was removed in v27.
  - `"swing-bot.plan_engine"` in `planning/lifecycle.py` and `params.py`.
  - `"swing-bot.data_refresh"` in `adjustments.py`.
  - `swing-bot.config` beside `swingbot.config` in `config.py`.
  - A shared `"swing-bot"` logger imported by every command module.
  - Inline `getLogger` calls in `performance.py`.
  - `getLogger(__name__)` in only 9 files.
- **Silent paths:**
  - Paper-trade lifecycle transitions (`plan_manager.py`, `performance.py`,
    `ledger.py`).
  - Dedup and gating decisions.
  - `yf_safe.py` and the Alpaca provider.
  - All of `core/edge`, `throttle.py`, `risk_limits.py`.
  - Command errors, which are shown to the user in chat and never logged.
  - Healthcheck cleanup (a bare `except: pass` in `presence.py`).
  - Successful alert posts.
- **Misleading or low-value logs:**
  - About 53 warning/error calls log `%s` of the exception without a traceback.
  - `log.exception(..., exc)` repeats the exception text.
  - "CHANNEL_ID not set" names a setting that is really
    `DISCORD_CHANNEL_TRADES_ID`.
  - "Config auto-reloaded" and "Scan interval hot-reloaded" are each logged
    twice.
  - "Alpaca miss" is logged at INFO.
  - Batch price failures are logged at DEBUG.
  - Earnings inside the holding window is a WARNING on routine alerts.
  - `retry.py` truncates the exception to 120 characters.
  - Two `print()` calls (`fmp_client.py`, `backtest_wf.py`).
- **`LOG_LEVEL` is not reapplied** by the scan-time config auto-reload
  (`scan_run.py`), only by SIGHUP and the config watcher.

## 1. One logging setup — `swingbot/infra/logsetup.py`

- `configure_logging(log_file, level, *, max_bytes, backups)` configures the
  **root** logger with a console `StreamHandler` and a `RotatingFileHandler`.
  It is idempotent: calling it twice does not duplicate handlers.
- Format: `%(asctime)s [%(levelname)s] [%(scan_id)s] %(name)s: %(message)s`.
- `bot_core` calls it with `config.LOG_FILE` (5MB x3, as today).
  `admin_ui.py` calls it with `config.ADMIN_LOG_FILE` (5MB x2, as today). The
  ad-hoc handler wiring in `admin/app.py` is removed. Werkzeug and `app.logger`
  propagate to root.
- `apply_log_level(level)` is the only way to change the level. It is called
  at startup, on SIGHUP, by the config watcher, and by the scan-time
  auto-reload, which currently misses it.

## 2. Scan id

- `scan_id_var: ContextVar[str]`, default `"-"`.
- `scan_context(scan_id)`: a context manager that sets and resets the var.
  It is wrapped around each scan run in `scan_run.py`, including manual
  `!check` scans and the weekend deep scan.
- The id is a short, human-greppable string: `s-` plus the HHMM, plus a
  two-character suffix to disambiguate scans in the same minute (for example
  `s-1405a`).
- `ScanIdFilter`, attached to both handlers, sets `record.scan_id` from the
  var, so every module's lines inside a scan carry the id without knowing
  about it.
- asyncio tasks inherit the context. Threaded work inside a scan must use
  `asyncio.to_thread`, which copies the context. The plan audits the
  `run_in_executor` call sites reached from a scan, and either converts them or
  wraps them with `contextvars.copy_context().run`.

## 3. Logger names and new coverage

**Names.** Every module uses `log = logging.getLogger(__name__)`.
- Hard-coded `"swing-bot…"`/`"swingbot…"` names are removed.
- Command modules stop importing the shared `"swing-bot"` logger.
- Before renaming, the plan greps the tests for `caplog`, `getLogger("swing-bot`
  and `logger=` assertions and updates them in the same task.

**New INFO** (a few per day, and they matter):
- Plan transitions: armed, filled, break-even moved, TP1 hit, stopped,
  expired, invalidated (`plan_manager.py`). One line each, with ticker,
  plan id (8 chars), direction and the relevant price.
- Trade closed: outcome, realised R, hold days (`performance.py`).
- Alert posted: `kind=<v110 Kind name> ticker=<T> channel=<name>`, one line per
  successful send. **This task depends on v110.**
- Kill switch flipped (`throttle.py`) and a risk limit hit (`risk_limits.py`).

**New DEBUG** (per symbol, per scan):
- Dedup merges and gating rejects, with the reason (`dedup.py`, `gating.py`).
- Fetch misses and fallbacks (`yf_safe.py`, `alpaca_provider.py`).

**New WARNING with `exc_info=True`:**
- Command errors. The existing user-facing `ctx.send("⚠️ …")` stays; a log
  line is added beside it (`backtest.py`, `data.py`, `info.py`, `views.py`
  and the rest found by grepping `ctx.send(f"⚠️`).
- Healthcheck cleanup failures in `presence.py`. The bare `except: pass`
  becomes `except discord.HTTPException` plus a DEBUG log for 404 (message
  already gone) and a WARNING for anything else.

## 4. Fixes to existing logs

- Add `exc_info=True` to every `log.warning/error` that logs a caught exception
  (about 53). Drop the redundant `exc` argument from `log.exception(...)`
  calls.
- `loops.py` "CHANNEL_ID not set" → "DISCORD_CHANNEL_TRADES_ID not set".
- Log "Config auto-reloaded" and "Scan interval hot-reloaded" once each, at the
  site that performs the reload.
- Levels:
  - "Alpaca miss" INFO → DEBUG.
  - Batch price failures (`data.py`, `loops.py`) DEBUG → WARNING.
  - Earnings inside the holding window WARNING → INFO.
- `retry.py`: log the full exception (no 120-character truncation), and the
  final give-up at WARNING with `exc_info`.
- `print()` in `fmp_client.py` → a log call. `backtest_wf.py` progress stays a
  `print()` if it is CLI script output (it is read by `backtest-runner`);
  the plan decides after reading the call site and records why.
- The docstring in `alert_embeds.py` naming "scan_engine.py's HTF check" is
  updated.

## Testing

- `tests/infra/test_logsetup.py`:
  - the format contains the level, scan id and logger name
  - `configure_logging` is idempotent
  - the scan id reads `-` outside `scan_context` and the set id inside it
  - `asyncio.to_thread` work inside a scan carries the id
  - `apply_log_level` changes the effective level
- An admin-process test: after the admin setup, an INFO record from a
  `swingbot.admin.*` logger reaches the admin file handler.
- A `caplog` test per new INFO transition (armed, filled, BE, TP1, stopped,
  expired, invalidated, closed, alert posted, kill switch).
- A guard test: no module under `swingbot/` calls `getLogger` with a
  string literal that starts with `"swing-bot"` or `"swingbot"`.
- A regression test: the scan-time auto-reload reapplies `LOG_LEVEL`.
- Complexity: `radon cc -s -n C` over every touched file shows no new or
  worsened function ≥ 15.
- One full suite run, as the plan's final task.

## Acceptance

- `bot.log` and `admin.log` lines both show the logger name and scan id.
  `grep s-XXXX bot.log` shows one scan end to end.
- `admin.log` receives INFO from admin modules.
- A paper trade's life (armed → filled → … → closed) can be read from
  `bot.log` at INFO alone.
- No warning or error about a caught exception is missing its traceback.
- Full suite green: `0 failed`, `0 xfailed`.
