# v111 — Backend logging refresh, Part 2: logger names and lifecycle INFO

**Index, global constraints, resolved ambiguities and parallelisation:** [`2026-09-28-v111-backend-logging-refresh_0-index.md`](2026-09-28-v111-backend-logging-refresh_0-index.md). Every task below includes that file's Global Constraints.

# Phase 2 — Logger names

### Task V111-6: Every module logger is `getLogger(__name__)`

**Files:**
- Modify (the logger line only), as listed by `git grep -n 'getLogger("swing' -- swingbot` at plan time:
  - `swingbot/bot_core.py`, `swingbot/config.py` (line 55 and the two inline `logging.getLogger("swingbot.config")` calls in `_cast`)
  - `swingbot/admin/api_v1/trade_commands.py`, `swingbot/admin/events/broker.py`, `swingbot/admin/events/stream.py`, `swingbot/admin/events/watcher.py`, `swingbot/admin/spa.py`
  - `swingbot/core/analytics/journal.py`, `swingbot/core/analytics/snapshots.py`
  - `swingbot/core/backtesting/backtest_wf.py`
  - `swingbot/core/charts/trade_chart.py`
  - `swingbot/core/infra/deploy_marker.py`, `swingbot/core/infra/jsonio.py`, `swingbot/core/infra/notifier.py`
  - `swingbot/core/market/candlestick_patterns.py`, `swingbot/core/market/events.py`, `swingbot/core/market/trendlines.py`
  - `swingbot/core/marketdata/adjustments.py`, `backtest_cache.py`, `data_refresh.py`, `data_store.py`, `fmp_client.py`
  - `swingbot/core/planning/lifecycle.py`, `params.py`, `plan_manager.py`, `plan_store.py`
  - `swingbot/core/scanning/alert_embeds.py`, `analyze.py`, `confidence.py`, `fetch.py`, `lifecycle_embeds.py`, `progress_store.py`, `scan_run.py`
  - `swingbot/core/tracking/performance.py` (four inline calls become one module logger), `retrospective.py`, `risk_metrics.py`
- Modify (tests that named the old loggers): `tests/marketdata/test_data_refresh.py` (lines 53, 66), `tests/scanning/test_engine_v2_plans.py` (lines 893, 903), `tests/test_market_data_refresh_task.py` (line 73)
- Create: `tests/infra/test_logger_names.py`

**v110 overlap:** `alert_embeds.py` and `lifecycle_embeds.py` get a one-line change here. On a merge conflict, keep v110's side and re-apply `log = logging.getLogger(__name__)`.

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - Logger names equal module paths (`swingbot.core.scanning.scan_run`, `swingbot.core.planning.plan_manager`, `swingbot.bot_core`, …).
  - `performance.log` exists as a module attribute.
  - `tests/infra/test_logger_names.py`, with the helper `_python_files()` and the constant `ROOT`. V111-7 appends a second test to this file.
- Out of scope: `scripts/**` (CLI scripts are not under `swingbot/`), and `bot.py`, which keeps importing `log` from `bot_core` (it is an entry point, not a command module, and `__name__` there is `"__main__"`).

- [ ] **Step 1: Write the failing guard test**

Create `tests/infra/test_logger_names.py`:

```python
"""v111 §3: every module under swingbot/ names its logger with __name__.

Hard-coded names went stale (e.g. "swing-bot.scan_engine" in six modules,
a shim removed in v27) and made a bot.log line untraceable to its module."""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2] / "swingbot"


def _python_files():
    return sorted(ROOT.rglob("*.py"))


def _literal_logger_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "getLogger" and node.args):
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            yield node.lineno, first.value


def test_no_module_names_its_logger_with_a_swing_bot_literal():
    offenders = [f"{path.relative_to(ROOT.parent).as_posix()}:{line} {name!r}"
                 for path in _python_files()
                 for line, name in _literal_logger_names(path)
                 if name.startswith(("swing-bot", "swingbot"))]
    assert offenders == [], "use logging.getLogger(__name__):\n" + "\n".join(offenders)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/infra/test_logger_names.py`
Expected: FAIL, listing 41 offenders (every file above; `performance.py` counts four and `config.py` three).

- [ ] **Step 3: Rewrite the assignment lines**

```bash
git grep -l -E 'getLogger\("swing-bot' -- swingbot | xargs sed -i -E 's/logging\.getLogger\("swing-bot[^"]*"\)/logging.getLogger(__name__)/g'
```

Then check the result: `git grep -n 'getLogger("swing' -- swingbot` must print nothing, and `git diff --stat` must list only the files above.

- [ ] **Step 4: Hand-fix the inline calls**

`swingbot/config.py`: in `_cast`, the two `logging.getLogger("swingbot.config").warning(` calls become `log.warning(`. The module-level `log` at line 55 is now `logging.getLogger(__name__)`, which is `"swingbot.config"`.

`swingbot/core/tracking/performance.py`:
1. Add `import logging` to the top-level imports (beside `import os`). Below the imports, next to the other module constants, add `log = logging.getLogger(__name__)`.
2. The sed turned the four inline calls into `logging.getLogger(__name__).warning(`, in `_journal_close_safely`, `_close_linked_plan_safely`, `_refresh_snapshot_safely` and `TradeLog._settle_account_balance`. Change each to `log.warning(`.
3. Delete the four function-local `import logging` lines above them.
Then check: `git grep -n "getLogger" -- swingbot/core/tracking/performance.py` prints exactly one line.

- [ ] **Step 5: Update the tests that named the old loggers**

- `tests/marketdata/test_data_refresh.py` lines 53 and 66: `logger="swing-bot.data_refresh"` → `logger=refresh_mod.log.name` (`refresh_mod` is already imported at the top of that file).
- `tests/scanning/test_engine_v2_plans.py` lines 893 and 903: `logger="swing-bot.scan_engine"` → `logger="swingbot.core.scanning.analyze"` (these tests exercise `analyze._regime_at`).
- `tests/test_market_data_refresh_task.py` line 73: `caplog.at_level("WARNING", logger="swing-bot")` → `caplog.at_level("WARNING")`. The test asserts an *absence*, and a root-level capture is the stricter check on both sides of V111-7.

Check that nothing else pins an old name: `git grep -n '"swing-bot\.' -- tests` must print nothing. (`tests/admin/test_event_watcher.py` uses `w.log.name` and follows automatically.)

- [ ] **Step 6: Run the tests**

Run: `python scripts/dev/testrun.py file tests/infra/test_logger_names.py`
Expected: PASS.
Run each changed test file:
`python scripts/dev/testrun.py file tests/marketdata/test_data_refresh.py`
`python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`
`python scripts/dev/testrun.py file tests/test_market_data_refresh_task.py`
`python scripts/dev/testrun.py file tests/admin/test_event_watcher.py`
`python scripts/dev/testrun.py file tests/tracking/test_tradelog_v2.py`
Expected: all PASS.
Then `python scripts/dev/testrun.py fast`, because the blast radius crosses about 40 modules. Expected: `0 failed`.

- [ ] **Step 7: Syntax and complexity**

Run: `python -m py_compile bot.py swingbot/config.py swingbot/core/tracking/performance.py`
Expected: no output.
Run: `python -m radon cc -s -n C swingbot/core/tracking/performance.py swingbot/config.py`
Expected: the legacy values listed in the index are unchanged. No new entries.

- [ ] **Step 8: Commit**

```bash
git add -u swingbot tests/marketdata/test_data_refresh.py tests/scanning/test_engine_v2_plans.py tests/test_market_data_refresh_task.py
git add tests/infra/test_logger_names.py
git commit -m "refactor(v111): every module logger is getLogger(__name__); guard against hard-coded names

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot tests/marketdata/test_data_refresh.py tests/scanning/test_engine_v2_plans.py tests/test_market_data_refresh_task.py tests/infra/test_logger_names.py
```

Before committing, confirm `git diff --cached --stat` lists only this task's files. `git add -u swingbot` must not sweep in another parallel task's edits. If another task has uncommitted changes under `swingbot/`, stage this task's files by name instead.

---

### Task V111-7: Command modules stop borrowing `bot_core`'s logger

**Files:**
- Modify: `swingbot/commands/scanning/alerts.py`, `commands.py`, `loops.py`, `presence.py`, `recap.py` (the `from swingbot.bot_core import …` line, plus a new `log = …` line)
- Modify: `tests/infra/test_logger_names.py` (append one test)

**v110 overlap:** all five modules are rewritten by v110. The change here is two lines at each file's top. On a conflict, keep v110's imports and re-apply: drop `log` from the `bot_core` import, and add `import logging` and `log = logging.getLogger(__name__)`.

**Interfaces:**
- Consumes: V111-6's `tests/infra/test_logger_names.py` (`ROOT`, `_python_files`).
- Produces: `alerts.log`, `commands.log`, `loops.log`, `presence.log`, `recap.log`, each named `swingbot.commands.scanning.<module>`. Tests that patch `loops.log` (`tests/test_market_data_refresh_task.py:57`) keep working, because they patch the module attribute.

- [ ] **Step 1: Write the failing guard test**

Append to `tests/infra/test_logger_names.py`:

```python
def _borrows_bot_core_log(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "swingbot.bot_core"
            and any(alias.name == "log" for alias in node.names)]


def test_no_module_borrows_the_bot_core_logger():
    offenders = [f"{path.relative_to(ROOT.parent).as_posix()}:{line}"
                 for path in _python_files() for line in _borrows_bot_core_log(path)]
    assert offenders == [], "give the module its own logging.getLogger(__name__):\n" + "\n".join(offenders)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/infra/test_logger_names.py`
Expected: FAIL, listing `alerts.py:6`, `commands.py:8`, `loops.py:13`, `presence.py:7`, `recap.py:2` (line numbers may have moved).

- [ ] **Step 3: Give each module its own logger**

In each of the five files, remove `log` from the `from swingbot.bot_core import …` line, and add `import logging` to the stdlib imports. After the imports, add:

```python
log = logging.getLogger(__name__)
```

The import lines at plan time become:
- `alerts.py`: `from swingbot.bot_core import bot`
- `commands.py`: `from swingbot.bot_core import SESSION_TZ, bot, in_session`
- `loops.py`: `from swingbot.bot_core import bot, in_session, SESSION_TZ, install_reload_signal_handler, on_config_reload`
- `presence.py`: `from swingbot.bot_core import SESSION_TZ, bot, in_session`
- `recap.py`: `from swingbot.bot_core import bot`

Then check that no module still uses a `log` it no longer defines: run `python -m py_compile` on the five files, then `python -c "import swingbot.commands.scanning as s; print([m.log.name for m in (s.alerts, s.commands, s.loops, s.presence, s.recap)])"`. It must print the five `swingbot.commands.scanning.*` names.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/infra/test_logger_names.py`
Expected: PASS (2 tests).
Run: `python scripts/dev/testrun.py file tests/commands/test_scanning_package.py`
Run: `python scripts/dev/testrun.py file tests/test_market_data_refresh_task.py`
Run: `python scripts/dev/testrun.py file tests/infra/test_silent_alerts_channel.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/scanning/alerts.py swingbot/commands/scanning/commands.py swingbot/commands/scanning/loops.py swingbot/commands/scanning/presence.py swingbot/commands/scanning/recap.py tests/infra/test_logger_names.py
git commit -m "refactor(v111): scanning command modules get their own __name__ loggers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/commands/scanning/alerts.py swingbot/commands/scanning/commands.py swingbot/commands/scanning/loops.py swingbot/commands/scanning/presence.py swingbot/commands/scanning/recap.py tests/infra/test_logger_names.py
```

---

# Phase 3 — Lifecycle and decision coverage

### Task V111-8: One INFO line per plan transition (armed, filled, BE, TP1, stopped, expired, invalidated, risk cap)

Load the `alert-surface` skill first (this edits `scan_run.py`).

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (new module-level helpers; one call in `PlanManager.poll`'s event loop and one in `PlanManager.check_bar`)
- Modify: `swingbot/core/scanning/scan_run.py` (one call after `PlanStore().add(plan_v2)`)
- Create: `tests/planning/test_plan_manager_logging.py`

**Interfaces:**
- Consumes: `PlanEvent` (`plan_id`, `transition`, `detail`), `TradePlanV2` (`plan_id`, `ticker`, `direction`, `status`, `entry_price`, `trigger_price`).
- Produces:
  - `plan_manager.log_plan_event(plan, event: PlanEvent) -> None`
  - `plan_manager.log_plan_armed(plan) -> None`
  - Line shape: `Plan <label>: <TICKER> id=<plan_id[:8]> <direction> price=<x.xx|n/a>[ reason=<reason>][ status=<STATUS>]`
  - Labels: `armed`, `filled`, `break-even moved`, `TP1 hit`, `stopped`, `closed`, `expired`, `invalidated`, `risk cap hit`. The feed-only events `stop_moved` and `pyramid_add` log nothing.

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_plan_manager_logging.py`:

```python
"""v111 §3: a paper trade's life reads from bot.log at INFO alone.
One line per lifecycle transition, with ticker, 8-char plan id, direction
and the relevant price."""
import logging

import pytest

from swingbot import config
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_manager import PlanEvent, PlanManager, log_plan_armed, log_plan_event
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_pending import _pending

CASES = [
    ("filled", {"entry_price": 106.0, "live_price": 106.0},
     "Plan filled: AAPL id=p1 bullish price=106.00"),
    ("be_moved", {"working_stop": 106.0, "live_price": 108.1},
     "Plan break-even moved: AAPL id=p1 bullish price=106.00"),
    ("tp1_partial", {"exit_price": 110.5, "reason": "tp1", "fraction": 0.5, "r": 2.0},
     "Plan TP1 hit: AAPL id=p1 bullish price=110.50 reason=tp1"),
    ("closed", {"exit_price": 104.0, "reason": "loss"},
     "Plan stopped: AAPL id=p1 bullish price=104.00 reason=loss"),
    ("closed", {"exit_price": 106.0, "reason": "scratch"},
     "Plan stopped: AAPL id=p1 bullish price=106.00 reason=scratch"),
    ("closed", {"exit_price": 118.0, "reason": "tp1_runner_trail"},
     "Plan stopped: AAPL id=p1 bullish price=118.00 reason=tp1_runner_trail"),
    ("closed", {"exit_price": 120.0, "reason": "tp1_runner_tp2"},
     "Plan closed: AAPL id=p1 bullish price=120.00 reason=tp1_runner_tp2"),
    ("closed", {"exit_price": 101.0, "reason": "stall_exit"},
     "Plan closed: AAPL id=p1 bullish price=101.00 reason=stall_exit"),
    ("cancelled_expired", {"bars_waited": 5},
     "Plan expired: AAPL id=p1 bullish price=n/a"),
    ("cancelled_invalidated", {"live_price": 99.0},
     "Plan invalidated: AAPL id=p1 bullish price=99.00"),
    ("cancelled_risk_cap", {"entry_price": 106.0, "stop_loss": 95.0,
                            "planned_loss_pct": 10.38, "max_planned_loss_pct": 2.0},
     "Plan risk cap hit: AAPL id=p1 bullish price=106.00"),
]


def _plan_lines(caplog):
    return [r for r in caplog.records if r.name == pm.log.name]


@pytest.mark.parametrize("transition,detail,expected", CASES)
def test_each_transition_logs_one_info_line(transition, detail, expected, caplog):
    with caplog.at_level(logging.INFO, logger=pm.log.name):
        log_plan_event(_plan(), PlanEvent("p1", transition, dict(detail)))
    [record] = _plan_lines(caplog)
    assert record.levelno == logging.INFO
    assert record.getMessage() == expected


def test_plan_id_is_cut_to_eight_characters(caplog):
    with caplog.at_level(logging.INFO, logger=pm.log.name):
        log_plan_event(_plan(plan_id="abcdef1234567890"),
                       PlanEvent("abcdef1234567890", "filled", {"entry_price": 1.0}))
    assert "id=abcdef12 " in _plan_lines(caplog)[0].getMessage()


@pytest.mark.parametrize("transition", ["stop_moved", "pyramid_add"])
def test_feed_only_events_are_not_transition_lines(transition, caplog):
    with caplog.at_level(logging.INFO, logger=pm.log.name):
        log_plan_event(_plan(), PlanEvent("p1", transition, {"new": 1.0}))
    assert _plan_lines(caplog) == []


def test_armed_line_uses_the_trigger_for_a_pending_plan(caplog):
    with caplog.at_level(logging.INFO, logger=pm.log.name):
        log_plan_armed(_pending())
    assert [r.getMessage() for r in _plan_lines(caplog)] == [
        "Plan armed: AAPL id=p1 bullish price=105.00 status=PENDING"]


def test_armed_line_uses_the_entry_once_there_is_one(caplog):
    with caplog.at_level(logging.INFO, logger=pm.log.name):
        log_plan_armed(_plan(entry_price=100.5, status="ACTIVE"))
    assert [r.getMessage() for r in _plan_lines(caplog)] == [
        "Plan armed: AAPL id=p1 bullish price=100.50 status=ACTIVE"]


def test_poll_logs_the_fill_it_performs(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    feed = FakePriceFeed([("AAPL", 106.0)])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_pending(stop_loss=104.0))
    mgr = PlanManager(store, feed.get_price)
    with caplog.at_level(logging.INFO, logger=pm.log.name):
        mgr.poll()
    assert "Plan filled: AAPL id=p1 bullish price=106.00" in [r.getMessage() for r in _plan_lines(caplog)]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_logging.py`
Expected: FAIL with `ImportError: cannot import name 'log_plan_armed'`.

- [ ] **Step 3: Add the helpers to `plan_manager.py`**

Add below the `NOTICE_RESEND_DAYS` constant:

```python
# v111: one INFO line per lifecycle transition, so a paper trade's life reads
# from bot.log at INFO alone. transition -> (label, detail key of the price).
# Feed-only events (stop_moved, pyramid_add) are absent on purpose.
_TRANSITION_LOG = {
    "filled": ("filled", "entry_price"),
    "be_moved": ("break-even moved", "working_stop"),
    "tp1_partial": ("TP1 hit", "exit_price"),
    "closed": ("closed", "exit_price"),
    "cancelled_expired": ("expired", None),
    "cancelled_invalidated": ("invalidated", "live_price"),
    "cancelled_risk_cap": ("risk cap hit", "entry_price"),
}
# Closes where a stop took the position out (initial, break-even, the
# post-TP1 runner floor, or the chandelier trail), not a target or a time rule.
_STOPPED_REASONS = frozenset({"loss", "scratch", "tp1_runner_be", "tp1_runner_trail"})


def _fmt_price(value) -> str:
    return "n/a" if value is None else f"{float(value):.2f}"


def _plan_line(label: str, plan, price, suffix: str = "") -> None:
    log.info("Plan %s: %s id=%s %s price=%s%s", label, plan.ticker,
             str(plan.plan_id)[:8], plan.direction, _fmt_price(price), suffix)


def log_plan_event(plan, event: PlanEvent) -> None:
    """INFO line for one lifecycle transition; silent for feed-only events."""
    entry = _TRANSITION_LOG.get(event.transition)
    if entry is None:
        return
    label, price_key = entry
    reason = event.detail.get("reason")
    if event.transition == "closed" and reason in _STOPPED_REASONS:
        label = "stopped"
    price = event.detail.get(price_key) if price_key else None
    _plan_line(label, plan, price, f" reason={reason}" if reason else "")


def log_plan_armed(plan) -> None:
    """INFO line when the scan persists a new plan (the plan is armed)."""
    price = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    _plan_line("armed", plan, price, f" status={plan.status}")
```

- [ ] **Step 4: Call it where transitions are applied**

In `PlanManager.poll`, change:

```python
            for event in new_events:
                self._on_event(plan, event)
```

to:

```python
            for event in new_events:
                log_plan_event(plan, event)
                self._on_event(plan, event)
```

In `PlanManager.check_bar` (unwired today, kept consistent), change:

```python
        for event in events:
            self._on_event(plan, event)
```

to:

```python
        for event in events:
            log_plan_event(plan, event)
            self._on_event(plan, event)
```

`_on_event` is not touched, so its complexity stays at 15. It returns early when `trade_log is None`, which is why the log call sits beside it rather than inside it.

- [ ] **Step 5: Log the armed plan in `scan_run.py`**

Add `from swingbot.core.planning.plan_manager import log_plan_armed` to the imports. Change:

```python
                try:
                    PlanStore().add(plan_v2)
                except Exception:
```

to:

```python
                try:
                    PlanStore().add(plan_v2)
                    log_plan_armed(plan_v2)
                except Exception:
```

Inside the `try` rather than a `try/else`: an `else` would add a branch to `_sync_run_scan` (legacy 108, must not get worse). `log_plan_armed` only formats and logs. Check the import does not create a cycle: `python -c "import swingbot.core.scanning.scan_run"` must succeed. (`plan_manager` imports only `config`, `market.session`, `risk_limits` and `planning.*`.)

- [ ] **Step 6: Run the tests**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_logging.py`
Expected: PASS (17 tests).
Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_pending.py`
Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_feed.py`
Run: `python scripts/dev/testrun.py file tests/tracking/test_tradelog_v2.py`
Expected: PASS (unchanged).

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/planning/plan_manager.py swingbot/core/scanning/scan_run.py`
Expected: `PlanManager.poll` still 21, `_on_event` still 15, `_sync_run_scan` ≤ its value after V111-5. `log_plan_event`, `log_plan_armed` and `_plan_line` are below C.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/planning/plan_manager.py swingbot/core/scanning/scan_run.py tests/planning/test_plan_manager_logging.py
git commit -m "feat(v111): INFO line per plan transition -- armed, filled, BE, TP1, stopped, expired, invalidated, risk cap

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/planning/plan_manager.py swingbot/core/scanning/scan_run.py tests/planning/test_plan_manager_logging.py
```

---

### Task V111-9: One INFO line per closed trade (outcome, realised R, hold days)

**Files:**
- Modify: `swingbot/core/tracking/performance.py` (new `_hold_days`, `_log_trade_closed` and `_after_close`; the six `_journal_close_safely(...)` call sites become `_after_close(...)`)
- Create: `tests/tracking/test_trade_closed_log.py`

**Interfaces:**
- Consumes: V111-6's module-level `performance.log`. `closed_r_multiple(t) -> float | None` already exists in the same module.
- Produces:
  - `performance._after_close(trade: dict) -> None`. It logs the line, then calls `_journal_close_safely(trade)`, looked up at call time, so `tests/tracking/test_tradelog_v2.py`'s monkeypatch of `_journal_close_safely` still intercepts.
  - Line shape: `Trade closed: <TICKER> <direction> id=<id[:8]> outcome=<status> R=<+x.xx|n/a> hold=<d.d>d|n/a`

The six close paths at plan time all call `_journal_close_safely` exactly once after their lock releases: `close_plan_trade`, `update_open_trades`, `close_trade_reversed`, `close_trade_manual`, `close_if_live_price_hit` and `check_near_tp_timeout`. `backfill_exit_price` settles the balance but is not a close and never journals, so it gets no line.

- [ ] **Step 1: Write the failing tests**

Create `tests/tracking/test_trade_closed_log.py`:

```python
"""v111 §3: every trade close logs outcome, realised R and hold days at INFO."""
import logging
import re

from swingbot.core.tracking import performance as perf
from swingbot.core.tracking.performance import TradeLog


def _closed_lines(caplog):
    return [r.getMessage() for r in caplog.records
            if r.name == perf.log.name and r.getMessage().startswith("Trade closed:")]


def test_close_plan_trade_logs_outcome_r_and_hold(tmp_path, monkeypatch, caplog):
    trades = TradeLog(path=str(tmp_path / "trades.json"))
    trades._trades = [{
        "id": "t-close-123456789", "plan_id": "p-close", "ticker": "AAPL",
        "status": "open", "direction": "bullish", "entry": 100.0,
        "stop_loss": 95.0, "shares": None, "legs": [],
        "opened_at": "2026-09-20T14:00:00+00:00",
    }]
    monkeypatch.setattr(perf, "_journal_close_safely", lambda trade: None)
    monkeypatch.setattr(perf, "_refresh_snapshot_safely", lambda: None)

    with caplog.at_level(logging.INFO, logger=perf.log.name):
        trades.close_plan_trade("p-close", {"fraction": 1.0, "exit_price": 105.0, "r": 1.0}, "win")

    [line] = _closed_lines(caplog)
    assert re.fullmatch(r"Trade closed: AAPL bullish id=t-close- outcome=win R=\+1\.00 hold=\d+\.\dd", line)


def test_the_journal_hook_still_runs_after_the_line(tmp_path, monkeypatch):
    journaled = []
    trades = TradeLog(path=str(tmp_path / "trades.json"))
    trades._trades = [{"id": "t1", "plan_id": "p1", "ticker": "MSFT", "status": "open",
                       "direction": "bearish", "entry": 100.0, "stop_loss": 105.0,
                       "shares": None, "legs": []}]
    monkeypatch.setattr(perf, "_journal_close_safely", journaled.append)
    monkeypatch.setattr(perf, "_refresh_snapshot_safely", lambda: None)

    trades.close_plan_trade("p1", {"fraction": 1.0, "exit_price": 105.0, "r": -1.0}, "loss")

    assert [t["id"] for t in journaled] == ["t1"]


def test_missing_fields_log_n_a_rather_than_raise(caplog):
    with caplog.at_level(logging.INFO, logger=perf.log.name):
        perf._log_trade_closed({"status": "closed", "ticker": "X"})
    assert _closed_lines(caplog) == ["Trade closed: X - id=- outcome=closed R=n/a hold=n/a"]


def test_hold_days_is_none_for_bad_timestamps():
    assert perf._hold_days({"opened_at": "2026-09-20T14:00:00+00:00", "closed_at": "garbage"}) is None
    assert perf._hold_days({"opened_at": "2026-09-20T14:00:00", "closed_at": "2026-09-21T14:00:00+00:00"}) is None
    assert perf._hold_days({"opened_at": "2026-09-20T00:00:00+00:00",
                            "closed_at": "2026-09-22T12:00:00+00:00"}) == 2.5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/tracking/test_trade_closed_log.py`
Expected: FAIL. No "Trade closed" line, and `AttributeError: … '_log_trade_closed'`.

- [ ] **Step 3: Add the helpers**

In `swingbot/core/tracking/performance.py`, add directly below `_journal_close_safely`:

```python
def _hold_days(trade: dict) -> float | None:
    """Calendar days from opened_at to closed_at, or None when either is
    missing, unparseable, or the two cannot be subtracted (naive vs aware)."""
    try:
        opened = datetime.fromisoformat(trade["opened_at"])
        closed = datetime.fromisoformat(trade["closed_at"])
        return (closed - opened).total_seconds() / 86400
    except (KeyError, TypeError, ValueError):
        return None


def _log_trade_closed(trade: dict) -> None:
    r = closed_r_multiple(trade)
    days = _hold_days(trade)
    log.info("Trade closed: %s %s id=%s outcome=%s R=%s hold=%s",
             trade.get("ticker") or "-", trade.get("direction") or "-",
             str(trade.get("id") or "-")[:8], trade.get("status") or "-",
             "n/a" if r is None else f"{r:+.2f}",
             "n/a" if days is None else f"{days:.1f}d")


def _after_close(trade: dict) -> None:
    """Everything that follows a trade close once TradeLog's lock is released:
    the v111 INFO line, then the journal hook. The line must never break a
    close, so a formatting failure is logged at DEBUG and swallowed."""
    try:
        _log_trade_closed(trade)
    except Exception:
        log.debug("trade-closed log line failed for %s", trade.get("id"), exc_info=True)
    _journal_close_safely(trade)
```

`closed_r_multiple` is defined further down the module. That is fine, because it is looked up at call time.

- [ ] **Step 4: Route the six closes through `_after_close`**

Run: `git grep -n "_journal_close_safely(" -- swingbot/core/tracking/performance.py`
Every call site (not the `def` line, and not the call inside `_after_close`) changes from `_journal_close_safely(<x>)` to `_after_close(<x>)`, keeping the same argument. At plan time these were the calls after `close_plan_trade`, `update_open_trades`, `close_trade_reversed`, `close_trade_manual`, `close_if_live_price_hit` and `check_near_tp_timeout`. Afterwards, the same grep shows exactly two lines: the `def` and the call inside `_after_close`.

- [ ] **Step 5: Run the tests**

Run: `python scripts/dev/testrun.py file tests/tracking/test_trade_closed_log.py`
Expected: PASS (4 tests).
Run: `python scripts/dev/testrun.py file tests/tracking/test_tradelog_v2.py`
Expected: PASS (unchanged; its `_journal_close_safely` monkeypatch still intercepts).

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/tracking/performance.py`
Expected: every legacy value in the index unchanged. `_hold_days`, `_log_trade_closed` and `_after_close` are below C.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/tracking/performance.py tests/tracking/test_trade_closed_log.py
git commit -m "feat(v111): INFO line per closed trade -- outcome, realised R, hold days

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/tracking/performance.py tests/tracking/test_trade_closed_log.py
```
