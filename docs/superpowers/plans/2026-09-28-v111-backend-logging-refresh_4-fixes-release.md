# v111 — Backend logging refresh, Part 4: fixes to existing logs, the v110-gated line, verification and release

**Index, global constraints, resolved ambiguities and parallelisation:** [`2026-09-28-v111-backend-logging-refresh_0-index.md`](2026-09-28-v111-backend-logging-refresh_0-index.md). Every task below includes that file's Global Constraints.

# Phase 4 — Fixes to existing logs

### Task V111-15: Every warning/error about a caught exception carries its traceback

Run this after every task in Phases 1-3 has been committed. It sweeps files those tasks edited.

**Files:**
- Create: `tests/infra/test_log_tracebacks.py`
- Modify: every file the guard lists. At plan time (AST scan, 58 missing `exc_info` + 3 redundant `log.exception` arguments):

| File | Missing `exc_info` | Redundant `log.exception` arg |
|---|---|---|
| `swingbot/admin/api_v1/trade_commands.py` | 1 | |
| `swingbot/commands/scanning/alerts.py` | 1 | |
| `swingbot/commands/scanning/commands.py` | | 1 (`!recap failed: %s`) |
| `swingbot/commands/scanning/loops.py` | 12 | 2 (`daily_recap: failed to post retrospective: %s`, `market_data_refresh: refresh failed: %s`) |
| `swingbot/commands/scanning/presence.py` | 3 | |
| `swingbot/commands/scanning/recap.py` | 1 | |
| `swingbot/core/backtesting/backtest_wf.py` | 1 | |
| `swingbot/core/charts/trade_chart.py` | 1 | |
| `swingbot/core/infra/jsonio.py` | 1 | |
| `swingbot/core/infra/notifier.py` | 3 | |
| `swingbot/core/marketdata/backtest_cache.py` | 2 | |
| `swingbot/core/marketdata/data.py` | 2 | |
| `swingbot/core/marketdata/data_refresh.py` | 4 | |
| `swingbot/core/marketdata/data_store.py` | 4 | |
| `swingbot/core/marketdata/ticker_directory.py` | 2 | |
| `swingbot/core/planning/params.py` | 4 | |
| `swingbot/core/planning/plan_store.py` | 1 | |
| `swingbot/core/scanning/fetch.py` | 3 | |
| `swingbot/core/scanning/lifecycle_embeds.py` | 5 | |
| `swingbot/core/scanning/scan_run.py` | 6 | |
| `swingbot/core/tracking/risk_metrics.py` | 1 | |

The guard's own output is authoritative. Counts shift slightly with Phases 1-3 and with v110 if it merged first.

**v110 overlap:** `alerts.py`, `loops.py`, `presence.py`, `recap.py` and `lifecycle_embeds.py`. Each edit here is a keyword argument appended to an existing call. On a conflict, keep v110's call and re-append `exc_info=True`.

**Interfaces:**
- Consumes: V111-6 and V111-7 (every module logs through a `log`/`logger` name, so the guard can recognise the calls).
- Produces: `tests/infra/test_log_tracebacks.py`, which V111-17 and V111-18 must keep green.

- [ ] **Step 1: Write the failing guard test**

Create `tests/infra/test_log_tracebacks.py`:

```python
"""v111 §4: no warning or error about a caught exception is missing its
traceback, and log.exception() never repeats the exception text itself.

"Logs a caught exception" = a log.warning/log.error call inside an
`except ... as <name>:` block whose arguments mention <name>."""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2] / "swingbot"
_LOGGERS = {"log", "logger"}


def _is_log_call(node, methods):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in methods and isinstance(node.func.value, ast.Name)
            and node.func.value.id in _LOGGERS)


def _mentions(call, name):
    return any(isinstance(n, ast.Name) and n.id == name for arg in call.args for n in ast.walk(arg))


def _handler_calls(tree):
    for handler in ast.walk(tree):
        if isinstance(handler, ast.ExceptHandler) and handler.name:
            for stmt in handler.body:
                for node in ast.walk(stmt):
                    yield handler.name, node


def _findings(path):
    where = path.relative_to(ROOT.parent).as_posix()
    for name, node in _handler_calls(ast.parse(path.read_text(encoding="utf-8"))):
        if (_is_log_call(node, {"warning", "error"}) and _mentions(node, name)
                and not any(k.arg == "exc_info" for k in node.keywords)):
            yield f"{where}:{node.lineno} missing exc_info=True"
        if _is_log_call(node, {"exception"}) and _mentions(node, name):
            yield f"{where}:{node.lineno} log.exception repeats the exception argument"


def test_caught_exceptions_are_logged_with_their_traceback():
    offenders = [finding for path in sorted(ROOT.rglob("*.py")) for finding in _findings(path)]
    assert offenders == [], "\n".join(offenders)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/infra/test_log_tracebacks.py`
Expected: FAIL, listing about 61 findings.

- [ ] **Step 3: Fix every finding**

For each `missing exc_info=True` finding, append `exc_info=True` as the last keyword argument of that call. Change nothing else. The `%s` of the exception stays in the message, because it keeps the one-line summary greppable. For example, in `loops.py`:

```python
        except Exception as exc:
            log.warning("trade_monitor: failed to post plan events: %s", exc, exc_info=True)
```

For each `log.exception repeats the exception argument` finding, drop the exception argument and its `%s` placeholder. `log.exception` already prints the exception and the traceback. At plan time:

```python
log.exception("!recap failed")                                   # commands.py, was ("!recap failed: %s", exc)
log.exception("daily_recap: failed to post retrospective")       # loops.py, was (...: %s", exc)
log.exception("market_data_refresh: refresh failed")             # loops.py, was (...: %s", exc)
```

If the exception variable is now unused in a handler (only possible for the three `log.exception` sites), keep `as exc` only if the handler still uses it: `commands.py`'s `!recap` handler still sends `{exc}` to the user. Otherwise write `except Exception:`.

- [ ] **Step 4: Run the guard and the tests of every touched file**

Run: `python scripts/dev/testrun.py file tests/infra/test_log_tracebacks.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py fast`, because the blast radius is about 20 modules.
Expected: `0 failed`. Existing tests that patch a logger (`tests/scanning/test_cold_fetch_pool.py`, `tests/marketdata/test_data_refresh.py`, `tests/tracking/test_retrospective_v2.py`, `tests/test_market_data_refresh_task.py`) assert substrings of `call_args` and are unaffected by an extra keyword.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C $(git diff --name-only HEAD -- 'swingbot/*.py' 'swingbot/**/*.py')`
Expected: values identical to before the task. A keyword argument adds no branch.

- [ ] **Step 6: Commit**

```bash
git add tests/infra/test_log_tracebacks.py $(git diff --name-only -- swingbot)
git commit -m "fix(v111): warnings/errors about caught exceptions carry exc_info; log.exception stops repeating the exception

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- tests/infra/test_log_tracebacks.py $(git diff --cached --name-only -- swingbot)
```

Before committing, confirm `git diff --cached --stat` lists only this task's files.

---

### Task V111-16: `retry.py` logs the full exception and gives up at WARNING with the traceback

**Files:**
- Modify: `swingbot/core/infra/retry.py`
- Modify: `tests/infra/test_retry.py` (append tests)

**Interfaces:**
- Consumes: nothing from other tasks (Group A; may run any time).
- Produces: unchanged `with_retry` signature and return/raise behaviour, plus one WARNING line on give-up.

- [ ] **Step 1: Write the failing tests**

Append to `tests/infra/test_retry.py`:

```python
import logging

from swingbot.core.infra import retry as retry_mod


def test_retry_line_carries_the_full_exception(monkeypatch, caplog):
    monkeypatch.setattr("swingbot.core.infra.retry.time.sleep", lambda s: None)
    long_message = "x" * 300
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise ValueError(long_message)
        return "ok"

    with caplog.at_level(logging.INFO, logger=retry_mod.log.name):
        assert with_retry(flaky, attempts=3, base_delay=0.0, label="fetch AAPL") == "ok"
    [line] = [r.getMessage() for r in caplog.records if r.name == retry_mod.log.name]
    assert line.endswith(long_message)          # no 120-character truncation


def test_giving_up_is_a_warning_with_the_traceback(monkeypatch, caplog):
    monkeypatch.setattr("swingbot.core.infra.retry.time.sleep", lambda s: None)

    def always_fails():
        raise ConnectionError("curl 28 timeout")

    with caplog.at_level(logging.INFO, logger=retry_mod.log.name):
        with pytest.raises(ConnectionError):
            with_retry(always_fails, attempts=2, base_delay=0.0, label="fetch MSFT")
    [give_up] = [r for r in caplog.records
                 if r.name == retry_mod.log.name and r.levelno == logging.WARNING]
    assert "fetch MSFT" in give_up.getMessage() and "2 attempt" in give_up.getMessage()
    assert give_up.exc_info is not None and give_up.exc_info[0] is ConnectionError
```

(`pytest` and `with_retry` are already imported at the top of the file.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/infra/test_retry.py`
Expected: FAIL. The retry line is truncated, and there is no WARNING record.

- [ ] **Step 3: Implement**

In `swingbot/core/infra/retry.py`, replace the loop tail with:

```python
    for i in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last = exc
            if i < attempts - 1:
                delay = base_delay * (2 ** i)
                log.info("retry %s in %.1fs (attempt %d/%d): %s",
                         label, delay, i + 1, attempts, exc)
                time.sleep(delay)
    log.warning("giving up on %s after %d attempt(s): %s", label, attempts, last,
                exc_info=last)
    raise last
```

`exc_info=last` (an exception instance) is accepted by `logging` and carries `last`'s own traceback. The call sits outside the `except` block, where `sys.exc_info()` is already cleared.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/infra/test_retry.py`
Expected: PASS (all, old and new).

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/infra/retry.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/infra/retry.py tests/infra/test_retry.py
git commit -m "fix(v111): retry logs the full exception; giving up is a WARNING with the traceback

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/infra/retry.py tests/infra/test_retry.py
```

---

### Task V111-17: Level and wording fixes (trigger message, batch prices, earnings, stale docstring)

Load the `alert-surface` skill first (this edits `scan_run.py` and `alert_embeds.py`).

**Files:**
- Modify: `swingbot/commands/scanning/loops.py` (trigger-path message; the trade monitor's batch fetch moves into a new `_live_price_batch`)
- Modify: `swingbot/core/marketdata/data.py` (`prefetch_prices`'s batch failure)
- Modify: `swingbot/core/scanning/scan_run.py` (the earnings check moves into a new `_earnings_in_window`)
- Modify: `swingbot/core/scanning/alert_embeds.py` (`build_embed` docstring)
- Create: `tests/scanning/test_log_levels_v111.py`

**Not changed, with the reason (spec §4 asks the plan to decide):** `backtest_wf.py:491,493` stay `print(..., flush=True)`, per index resolved ambiguity 7. `fmp_client.py:20` is docstring text, not a call.

**v110 overlap:** `loops.py` and `alert_embeds.py`.

**Interfaces:**
- Consumes: V111-7's `loops.log`, and V111-15's guard (which must stay green).
- Produces:
  - `loops._live_price_batch(tickers: list) -> dict` (async)
  - `scan_run._earnings_in_window(ticker: str, max_holding_days: int)`, which returns what `earnings_within_window` returned, or `None` on error

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_log_levels_v111.py`:

```python
"""v111 §4: level and wording fixes to existing log lines."""
import asyncio
import logging

from swingbot import config
from swingbot.commands.scanning import loops
from swingbot.core.marketdata import data as data_mod
from swingbot.core.scanning import scan_run


def _records(caplog, logger):
    return [r for r in caplog.records if r.name == logger.name]


def test_earnings_inside_the_window_is_info_not_warning(monkeypatch, caplog):
    monkeypatch.setattr(scan_run, "earnings_within_window", lambda ticker, days: ("2026-10-01", 3))
    with caplog.at_level(logging.DEBUG, logger=scan_run.log.name):
        assert scan_run._earnings_in_window("AAPL", 20) == ("2026-10-01", 3)
    [record] = _records(caplog, scan_run.log)
    assert record.levelno == logging.INFO and "AAPL has earnings 2026-10-01 (3d away)" in record.getMessage()


def test_an_earnings_lookup_error_is_none_at_debug(monkeypatch, caplog):
    def boom(ticker, days):
        raise RuntimeError("yahoo")

    monkeypatch.setattr(scan_run, "earnings_within_window", boom)
    with caplog.at_level(logging.DEBUG, logger=scan_run.log.name):
        assert scan_run._earnings_in_window("AAPL", 20) is None
    assert [r.levelno for r in _records(caplog, scan_run.log)] == [logging.DEBUG]


def test_trade_monitor_batch_price_failure_is_a_warning(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise TimeoutError("hung")

    monkeypatch.setattr(loops, "_run_bounded", boom)
    with caplog.at_level(logging.DEBUG, logger=loops.log.name):
        assert asyncio.run(loops._live_price_batch(["AAPL"])) == {}
    [record] = _records(caplog, loops.log)
    assert record.levelno == logging.WARNING and record.exc_info is not None


def test_trade_monitor_with_no_open_tickers_fetches_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(loops, "_run_bounded", lambda *args, **kwargs: calls.append(args))
    assert asyncio.run(loops._live_price_batch([])) == {}
    assert calls == []


def test_prefetch_batch_failure_is_a_warning(monkeypatch, caplog):
    def boom(tickers):
        raise ConnectionError("down")

    monkeypatch.setattr(data_mod, "get_current_price_batch", boom)
    with caplog.at_level(logging.DEBUG, logger=data_mod.log.name):
        data_mod.prefetch_prices(["AAPL"])
    [record] = [r for r in _records(caplog, data_mod.log) if "prefetch_prices" in r.getMessage()]
    assert record.levelno == logging.WARNING and record.exc_info is not None


def test_admin_trigger_names_the_real_setting(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(loops, "auto_reload_if_changed", lambda: {}, raising=False)
    monkeypatch.setattr(loops.runstate, "_MANUAL_CLOSE_QUEUE", str(tmp_path / "manual_close_notify.json"))
    monkeypatch.setattr(loops.runstate, "is_trigger_requested", lambda: True)
    monkeypatch.setattr(loops.runstate, "clear_trigger", lambda: None)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "")
    with caplog.at_level(logging.WARNING, logger=loops.log.name):
        asyncio.run(loops.config_watcher.coro())
    assert "DISCORD_CHANNEL_TRADES_ID not set; cannot post scan results." in [
        r.getMessage() for r in _records(caplog, loops.log)]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_log_levels_v111.py`
Expected: FAIL. `_earnings_in_window` and `_live_price_batch` do not exist, the prefetch line is DEBUG, and the message says `CHANNEL_ID not set`.

- [ ] **Step 3: Earnings helper in `scan_run.py`**

Add above `_sync_run_scan`:

```python
def _earnings_in_window(ticker: str, max_holding_days: int):
    """Earnings inside the holding window. INFO, not WARNING: it is routine on
    alerts and the explanation already flags it (v111 §4)."""
    try:
        earnings_info = earnings_within_window(ticker, max_holding_days)
    except Exception as e:
        log.debug("Earnings check failed for %s: %s", ticker, e)
        return None
    if earnings_info:
        log.info("%s has earnings %s (%dd away) inside this trade's holding window -- "
                 "volatility spike risk, will flag in explanation", ticker, *earnings_info)
    else:
        log.debug("%s: no earnings inside the %dd holding window", ticker, max_holding_days)
    return earnings_info
```

In `_sync_run_scan`, replace:

```python
        earnings_info = None
        try:
            earnings_info = earnings_within_window(result.ticker, h["max_holding_days"])
            if earnings_info:
                log.warning("%s has earnings %s (%dd away) inside this trade's holding window -- "
                             "volatility spike risk, will flag in explanation", result.ticker, *earnings_info)
            else:
                log.debug("%s: no earnings inside the %dd holding window", result.ticker, h["max_holding_days"])
        except Exception as e:
            log.debug("Earnings check failed for %s: %s", result.ticker, e)
```

with:

```python
        earnings_info = _earnings_in_window(result.ticker, h["max_holding_days"])
```

The behaviour is the same (an error leaves `earnings_info` as `None`), apart from the level.

- [ ] **Step 4: Batch-price helper and trigger message in `loops.py`**

Add above `trade_monitor`:

```python
async def _live_price_batch(tickers: list) -> dict:
    """Fresh-only live prices for the trade monitor, or {} on failure.

    One Yahoo request for the whole open book avoids a serial minute-history
    request per ticker. Fresh-only (allow_stale=False): acting on an old
    print could falsely close a trade or satisfy an exit transition.
    Routed through scanning.fetch._run_bounded, not a bare asyncio.to_thread
    (2026-09-17 incident): a hung yfinance call would otherwise wedge this
    @tasks.loop forever. A PROCESS, deliberately -- see _run_bounded.

    A failure is a WARNING (was DEBUG until v111): while it lasts, no open
    trade is checked against its stop or target."""
    if not tickers:
        return {}
    try:
        return await asyncio.to_thread(
            _run_bounded, functools.partial(get_current_price_batch, allow_stale=False),
            (tickers,), float(getattr(config, "LIVE_PRICE_TIMEOUT_SECONDS", 60)),
            f"trade_monitor: live-price batch of {len(tickers)} ticker(s)") or {}
    except Exception as exc:
        log.warning("trade_monitor: batch price fetch failed: %s", exc, exc_info=True)
        return {}
```

In `trade_monitor`, replace the block from the comment `# One Yahoo request for the whole open book avoids a serial minute-history` through the closing `else:` / `live_prices = {}` (the whole `if tickers: try: … except … else: …`) with:

```python
    live_prices = await _live_price_batch(tickers)
```

In `config_watcher`'s admin-trigger branch, change `log.warning("CHANNEL_ID not set; cannot post scan results.")` to `log.warning("DISCORD_CHANNEL_TRADES_ID not set; cannot post scan results.")`.

- [ ] **Step 5: `data.py` prefetch**

In `swingbot/core/marketdata/data.py` `prefetch_prices`, change:

```python
    except Exception as exc:
        log.debug("prefetch_prices batch failed: %s", exc)
        return
```

to:

```python
    except Exception as exc:
        log.warning("prefetch_prices batch failed: %s", exc, exc_info=True)
        return
```

- [ ] **Step 6: Stale docstring in `alert_embeds.py`**

In `build_embed`'s docstring, change `htf_info, when provided, is a dict from scan_engine.py's HTF check:` to `htf_info, when provided, is the dict analyze._scan_one builds from regime.get_htf_bias():`. Confirm with `git grep -n "scan_engine.py's HTF" -- swingbot`, which should print nothing.

- [ ] **Step 7: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_log_levels_v111.py`
Expected: PASS (6 tests).
Run: `python scripts/dev/testrun.py file tests/test_trade_monitor_task.py`
Run: `python scripts/dev/testrun.py file tests/infra/test_log_tracebacks.py`
Run: `python scripts/dev/testrun.py file tests/commands/test_config_watcher_task.py`
Expected: PASS.

- [ ] **Step 8: Complexity**

Run: `python -m radon cc -s -n C swingbot/commands/scanning/loops.py swingbot/core/scanning/scan_run.py swingbot/core/marketdata/data.py`
Expected: `trade_monitor` < 16 (it loses a branch), and `_sync_run_scan` below its value after V111-8 (it loses the `try` and the `if`). `_live_price_batch` and `_earnings_in_window` are below C.

- [ ] **Step 9: Commit**

```bash
git add swingbot/commands/scanning/loops.py swingbot/core/marketdata/data.py swingbot/core/scanning/scan_run.py swingbot/core/scanning/alert_embeds.py tests/scanning/test_log_levels_v111.py
git commit -m "fix(v111): batch price failures WARNING, earnings-in-window INFO, DISCORD_CHANNEL_TRADES_ID wording, stale HTF docstring

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/commands/scanning/loops.py swingbot/core/marketdata/data.py swingbot/core/scanning/scan_run.py swingbot/core/scanning/alert_embeds.py tests/scanning/test_log_levels_v111.py
```

---

# Phase 5 — v110-gated

### Task V111-18: One INFO line per successfully posted alert, named by v110's `Kind`

**GATE: do not start until v110 (Discord notification identity) is merged to `main`, and `main` is merged into this branch.** This is the only v111 task that depends on v110.

**Files:**
- Create: `swingbot/core/infra/posted_log.py`
- Create: `tests/infra/test_posted_log.py`
- Modify: `swingbot/commands/scanning/alerts.py` (`_send_alerts`, `_post_daily_digest`)
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` (`notify_closed_trades`, `notify_near_close`, `notify_plan_events`)

**Interfaces:**
- Consumes (from v110, verified in Step 1):
  - `swingbot.core.presentation.kinds.Kind`, an enum whose members have `.name`
  - `PushEmbed` (in `swingbot/core/presentation/components.py`), carrying the `Kind` it was built for as `.kind`
  - `ui.push_kwargs(embed) -> dict`, which every pushed send spreads into `.send(...)`
- Produces:
  - `posted_log.log_posted(embed, ticker, destination) -> None`
  - Line: `alert posted kind=<Kind.name> ticker=<T or -> channel=<name>`, at INFO, logger `swingbot.core.infra.posted_log`

- [ ] **Step 1: Verify the gate**

```bash
git log --oneline main | grep -m1 "v110"
git grep -n "^class Kind" -- swingbot/core/presentation/kinds.py
git grep -n "class PushEmbed" -- swingbot/core/presentation/components.py
git grep -n "def push_kwargs" -- swingbot/core/presentation
python -c "from swingbot.core.presentation.components import PushEmbed; print(getattr(PushEmbed, '__slots__', None))"
```

All four greps must print a line, and the last command must show a `kind` slot (or `PushEmbed` must otherwise expose `.kind`). **If `PushEmbed` carries no `kind`, stop here and report `BLOCKED: v110's PushEmbed does not record its Kind` to the controller.** Deciding where the kind lives is v110's design, not this task's.

- [ ] **Step 2: Write the failing tests**

Create `tests/infra/test_posted_log.py`:

```python
"""v111 §3: one INFO line per successful ticker-bearing push, named by v110's Kind."""
import asyncio
import logging
from types import SimpleNamespace

from swingbot import config
from swingbot.commands.scanning import alerts
from swingbot.core import presentation as ui
from swingbot.core.infra import posted_log
from swingbot.core.infra.posted_log import log_posted
from swingbot.core.presentation.kinds import Kind


def _lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == posted_log.log.name]


def test_line_names_kind_ticker_and_channel(caplog):
    member = next(iter(Kind))
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        log_posted(SimpleNamespace(kind=member), "AAPL", SimpleNamespace(name="trades"))
    assert _lines(caplog) == [f"alert posted kind={member.name} ticker=AAPL channel=trades"]


def test_a_command_context_is_named_by_its_channel(caplog):
    member = next(iter(Kind))
    ctx = SimpleNamespace(channel=SimpleNamespace(name="bot-commands"))
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        log_posted(SimpleNamespace(kind=member), None, ctx)
    assert _lines(caplog) == [f"alert posted kind={member.name} ticker=- channel=bot-commands"]


class _Chan:
    def __init__(self, name, fail=False):
        self.name, self.fail, self.sent = name, fail, []

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord 500")
        self.sent.append(kwargs)
        return SimpleNamespace(id=len(self.sent))


def _send(monkeypatch, chan, member):
    monkeypatch.setattr(ui, "push_kwargs", lambda embed: {"embed": embed})
    monkeypatch.setattr(alerts, "_simple_alert_channel", lambda: None)
    monkeypatch.setattr(config, "MAX_ALERTS_PER_SCAN", 10)
    embed = SimpleNamespace(kind=member, footer=None)
    asyncio.run(alerts._send_alerts(chan, [(embed, None, None, None)]))


def test_send_alerts_logs_each_successful_send_once(monkeypatch, caplog):
    member = next(iter(Kind))
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        _send(monkeypatch, _Chan("trades"), member)
    assert _lines(caplog) == [f"alert posted kind={member.name} ticker=- channel=trades"]


def test_a_failed_send_logs_no_posted_line(monkeypatch, caplog):
    member = next(iter(Kind))
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        _send(monkeypatch, _Chan("trades", fail=True), member)
    assert _lines(caplog) == []
```

The two `_send_alerts` tests rely on v110's per-message send isolation (v110 spec §6.2). A raising send is logged by v110's guard and the batch continues. If the landed `_send_alerts` reads more embed attributes than `kind`/`footer`, add them to the `SimpleNamespace` in `_send`. Do not change `_send_alerts` to suit the test.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/infra/test_posted_log.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.core.infra.posted_log'`.

- [ ] **Step 4: Write the helper**

Create `swingbot/core/infra/posted_log.py`:

```python
"""One INFO line per successfully pushed, ticker-bearing notification (v111 §3).

Called right after the awaited send returns, so a line exists only for a
message Discord accepted. The kind is v110's registry member, read off the
sent PushEmbed. This module never imports the registry; it only prints
the member's .name, so it cannot create an import cycle with presentation.
"""
import logging

log = logging.getLogger(__name__)


def _channel_name(destination) -> str:
    """A channel's name; a command Context's channel name; else its id."""
    name = getattr(destination, "name", None)
    if not name:
        name = getattr(getattr(destination, "channel", None), "name", None)
    return str(name) if name else str(getattr(destination, "id", "?"))


def log_posted(embed, ticker, destination) -> None:
    kind = getattr(embed, "kind", None)
    log.info("alert posted kind=%s ticker=%s channel=%s",
             getattr(kind, "name", "UNKNOWN"), ticker or "-", _channel_name(destination))
```

- [ ] **Step 5: Call it after every successful ticker-bearing send**

Add `from swingbot.core.infra.posted_log import log_posted` to `alerts.py` and `lifecycle_embeds.py`. Then, in each function below, add one `log_posted(...)` call **immediately after** each awaited `.send(...)` that posts a pushed embed, inside the same guard v110 put around that send. The call must never run when the send raised.

| Function | Send | Call to add after it |
|---|---|---|
| `alerts._send_alerts` | the simple-channel mirror send | `log_posted(<the mirror embed>, getattr(plan, "ticker", None), simple_channel)` |
| `alerts._send_alerts` | the full-alert send (`msg = await send_to.send(...)`) | `log_posted(embed, getattr(plan, "ticker", None), send_to)` |
| `alerts._post_daily_digest` | each per-plan entry send | `log_posted(embed, plan.ticker, channel)` (use the loop's plan variable) |
| `lifecycle_embeds.notify_closed_trades` | the per-trade send | `log_posted(embed, <that trade's ticker>, channel)` |
| `lifecycle_embeds.notify_near_close` | the per-warning send | `log_posted(embed, <that warning's ticker>, channel)` |
| `lifecycle_embeds.notify_plan_events` | each of the history / feed sends | `log_posted(embed, plan.ticker, <that send's channel>)` |

Where a send builds its embed inline (for example `send(**ui.push_kwargs(build_near_close_embed(warning)))`), bind the embed to a local variable first, so the same object is sent and logged. SYSTEM notices (scan summary, health, config, bot online, retrospective, the deep-scan report) are not ticker-bearing and get no line (index, resolved ambiguity 10).

Then check coverage: `git grep -n "push_kwargs(" -- swingbot/commands/scanning/alerts.py swingbot/core/scanning/lifecycle_embeds.py` and `git grep -n "log_posted(" -- swingbot`. Every push send in those two files must have a `log_posted` directly after it.

- [ ] **Step 6: Run the tests**

Run: `python scripts/dev/testrun.py file tests/infra/test_posted_log.py`
Expected: PASS (4 tests).
Run the v110 send tests that cover these functions: `python scripts/dev/testrun.py file tests/commands/test_send_alerts_v110.py`, `python scripts/dev/testrun.py file tests/scanning/test_execution_feed_routing.py`, `python scripts/dev/testrun.py file tests/infra/test_silent_alerts_channel.py`, and `python scripts/dev/testrun.py file tests/infra/test_log_tracebacks.py`.
Expected: PASS.

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/infra/posted_log.py swingbot/commands/scanning/alerts.py swingbot/core/scanning/lifecycle_embeds.py`
Expected: `posted_log` functions absent. `_send_alerts` and the three `notify_*` functions at or below their values as v110 left them (a call adds no branch).

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/infra/posted_log.py tests/infra/test_posted_log.py swingbot/commands/scanning/alerts.py swingbot/core/scanning/lifecycle_embeds.py
git commit -m "feat(v111): INFO line per posted alert -- kind (v110 Kind), ticker, channel

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/infra/posted_log.py tests/infra/test_posted_log.py swingbot/commands/scanning/alerts.py swingbot/core/scanning/lifecycle_embeds.py
```

---

# Phase 6 — Verification, release, close-out

### Task V111-19: Full-suite verification

**Files:** none (a fix-forward touches whatever the failures name).

**Interfaces:**
- Consumes: V111-1..V111-18 committed on the worktree branch.
- Produces: a green branch, ready to merge.

- [ ] **Step 1: The one full-suite run**

Dispatch the `test-runner` subagent for `python scripts/dev/testrun.py full` in the worktree. Require `0 failed` and `0 xfailed`. A changed pass count is not a failure. A red result is this plan's regressions, so fix forward from the failures it names. If a failure passes in isolation and sits in code this plan never touched, report it with both outputs and do not call the suite green.

The likeliest cross-test failure is a root-logger leak: a test that calls `configure_logging`/`setup_logging`/`configure_bot_logging` without `restore_root_logging`. It shows up as later `caplog` tests seeing unexpected levels. `git grep -n "configure_logging\|setup_logging()\|configure_bot_logging()" -- tests` finds them.

- [ ] **Step 2: Complexity sweep over everything the plan touched**

Run: `python -m radon cc -s -n C $(git diff --name-only main... -- '*.py' | grep -v '^tests/')`
Expected: only functions this plan did not change, plus the legacy values from the index, each at or below its baseline. `_sync_run_scan` < 108, `config_watcher` < 27, `trade_monitor` < 16, `PlanManager.poll` 21, `PlanManager._on_event` 15. Any other function at 15 or more is a regression to split before V111-20.

- [ ] **Step 3: Syntax pass**

Run: `python -m py_compile bot.py admin_ui.py swingbot/core/infra/logsetup.py swingbot/core/infra/posted_log.py swingbot/bot_core.py swingbot/core/scanning/scan_run.py swingbot/commands/scanning/loops.py`
Expected: no output.

- [ ] **Step 4: The two guards and the acceptance smoke**

Run: `python scripts/dev/testrun.py file tests/infra/test_logger_names.py` and `python scripts/dev/testrun.py file tests/infra/test_log_tracebacks.py`. Expected: PASS. (They already ran in the full suite. This step records the two spec acceptance guards by name in the task log.)

---

### Task V111-20: Merge and release `bot patch`

**Files:**
- Modify: `VERSION.json`, `swingbot/admin/version_history.json`

**Interfaces:**
- Consumes: V111-19's green branch.
- Produces: the branch merged on `main`, the release commit and the regenerated history, pushed to `origin/main` (which triggers the image build and deploy).

- [ ] **Step 1: Merge**

Follow the `worktree-lifecycle` skill. Run `git fetch` and compare with `origin/main`, because another session may have committed (v106 and v109 share files; see the index). Then merge branch `2026-09-28-v111-backend-logging-refresh` into `main`. If the merge resolved conflicts, run `python scripts/dev/testrun.py full` once on the result (the one exception in `document-conventions.md`). Otherwise do not re-run anything.

- [ ] **Step 2: Bump — read `VERSION.json` from disk**

Read `VERSION.json` now: never this plan, the spec's `Version:` line, or memory. Increment `bot` at the **patch** level, leave `ui` and `ui_updated` untouched, and set `bot_updated` to the current UTC time in `YYYY-MM-DD HH-MM-SS` format.

```bash
git add VERSION.json
git commit -m "release(bot): <new bot version> -- one logging setup, __name__ loggers, scan ids, lifecycle log lines

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- VERSION.json
```

- [ ] **Step 3: Regenerate the version history (after the bump commit)**

Run: `python scripts/dev/build_version_matrix.py`
Check: `git diff swingbot/admin/version_history.json` shows the new bot pair as `current`, with a real commit (not `"uncommitted"`).
Run: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
Expected: PASS.

```bash
git add swingbot/admin/version_history.json
git commit -m "chore(bot): <new bot version> -- one logging setup, __name__ loggers, scan ids, lifecycle log lines

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/admin/version_history.json
```

- [ ] **Step 4: Push**

`git fetch`, confirm `main` is ahead of `origin/main` only by this plan's commits, then `git push origin main`. The GitHub Actions deploy runs on the push.

---

### Task V111-21: Production verification and close-out

Operator task, run by the controller. Production reads go through the `prod-inspector` agent (read-only). Nothing on the VM should need to change. If something does, follow `mirror-prod`: mirror it into the repo and commit it.

**Files:**
- Move: `docs/superpowers/specs/2026-09-28-v111-backend-logging-refresh-design.md` → `docs/superpowers/specs/implemented/`
- Move: the five plan files `docs/superpowers/plans/2026-09-28-v111-backend-logging-refresh_0-index.md`, `_1-setup.md`, `_2-names.md`, `_3-coverage.md`, `_4-fixes-release.md` → `docs/superpowers/plans/implemented/`

**Interfaces:**
- Consumes: V111-20's deployed image.
- Produces: the spec's Acceptance section checked on production, and the documents closed.

- [ ] **Step 1: Confirm the deploy (prod-inspector, read-only)**

The bot and admin containers run the image built from V111-20's push, and the bot logs the new version at start.

- [ ] **Step 2: Check the acceptance criteria on the live files (prod-inspector, read-only)**

After at least one scheduled scan:
1. `tail -n 50 logs/bot.log`: every line has the shape `<asctime> [LEVEL] [<scan id or ->] swingbot.<module>: <message>`.
2. Pick one `s-XXXXxx` id from a "Scan starting" line. `grep -c "s-XXXXxx" logs/bot.log` is well above 2, and `grep "s-XXXXxx" logs/bot.log` runs from "Scan starting" to "Scan finished", with lines from `swingbot.core.scanning.analyze`/`fetch` among them (the pool workers carry the id).
3. `tail -n 50 logs/admin.log` shows `[INFO]` lines from `swingbot.admin.*` modules (for example the events stream on a page load), not only werkzeug.
4. `grep -E "Plan (armed|filled|break-even moved|TP1 hit|stopped|closed|expired|invalidated|risk cap hit):|Trade closed:" logs/bot.log` returns the transitions since the deploy. If a plan transitioned since the deploy, its life reads in order from those lines.
5. `grep "alert posted kind=" logs/bot.log` shows one line per alert posted since the deploy.
6. The admin Logs page still filters by level (the level stays the first bracketed word).

Report any criterion that cannot be checked yet (for example, no transition happened) as pending. Do not report it as passed.

- [ ] **Step 3: Close out**

Follow `document-lifecycle.md`. Move the spec and the five plan files to their `implemented/` folders with `git mv`, remove the worktree and branch per the `worktree-lifecycle` skill (the branch name contains no `backup` and no `stable-`; still run `git rev-list --count main..2026-09-28-v111-backend-logging-refresh` first and stop if it is non-zero), and commit:

```bash
git commit -m "docs(v111): close out -- backend logging refresh implemented

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/superpowers/specs docs/superpowers/plans
```
