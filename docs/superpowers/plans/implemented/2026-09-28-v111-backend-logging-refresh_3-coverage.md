# v111 — Backend logging refresh, Part 3: coverage (kill switch, decisions, fetch, command errors, healthcheck)

**Index, global constraints, resolved ambiguities and parallelisation:** [`2026-09-28-v111-backend-logging-refresh_0-index.md`](2026-09-28-v111-backend-logging-refresh_0-index.md). Every task below includes that file's Global Constraints.

# Phase 3 — Lifecycle and decision coverage (continued)

### Task V111-10: INFO line when the kill switch actually flips

**Files:**
- Modify: `swingbot/core/edge/throttle.py` (`set_kill`, plus a new `_log_kill_flip` and a module logger)
- Create: `tests/edge/test_killswitch_log.py`

**Interfaces:**
- Consumes: `throttle.kill_state() -> dict` (`on`, `reason`, `at`, `manual_release`), `throttle.KILLSWITCH_PATH`.
- Produces: `throttle.log`, and the lines `Kill switch ON: <reason>` and `Kill switch OFF (released, was: <prior reason>)`, logged only when `on` actually changes. `set_kill`'s return value is unchanged (the post-write `kill_state()`).

`scan_run.py`'s existing `log.warning("Kill switch engaged: …")` stays as it is. It reports the trigger check on every scan that trips it, while this line reports the state change once.

- [ ] **Step 1: Write the failing test**

Create `tests/edge/test_killswitch_log.py`:

```python
"""v111 §3: the kill switch logs each real flip, once, at INFO."""
import logging

from swingbot.core.edge import throttle


def _kill_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == throttle.log.name]


def test_each_real_flip_logs_once(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(throttle, "KILLSWITCH_PATH", str(tmp_path / "killswitch.json"))
    monkeypatch.setattr(throttle.config, "KILLSWITCH_DEFAULT_ON", False)

    with caplog.at_level(logging.INFO, logger=throttle.log.name):
        throttle.set_kill(True, reason="drawdown >20%")
        throttle.set_kill(True, reason="drawdown >20%")   # already on: early return, no line
        throttle.set_kill(False)

    assert _kill_lines(caplog) == [
        "Kill switch ON: drawdown >20%",
        "Kill switch OFF (released, was: drawdown >20%)",
    ]
    assert all(r.levelno == logging.INFO for r in caplog.records if r.name == throttle.log.name)


def test_releasing_an_already_released_switch_is_silent(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(throttle, "KILLSWITCH_PATH", str(tmp_path / "killswitch.json"))
    monkeypatch.setattr(throttle.config, "KILLSWITCH_DEFAULT_ON", False)

    with caplog.at_level(logging.INFO, logger=throttle.log.name):
        throttle.set_kill(False)

    assert _kill_lines(caplog) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/edge/test_killswitch_log.py`
Expected: FAIL with `AttributeError: module … has no attribute 'log'`.

- [ ] **Step 3: Implement**

In `swingbot/core/edge/throttle.py`, add `import logging` to the imports and `log = logging.getLogger(__name__)` below them. Add above `set_kill`:

```python
def _log_kill_flip(prior: dict, after: dict, reason: str) -> None:
    """INFO line only when the switch actually changed state."""
    if bool(prior.get("on")) == bool(after.get("on")):
        return
    if after.get("on"):
        log.info("Kill switch ON: %s", after.get("reason") or reason)
    else:
        log.info("Kill switch OFF (released, was: %s)", prior.get("reason"))
```

In `set_kill`, replace the final `return kill_state()` with:

```python
    after = kill_state()
    _log_kill_flip(prior, after, reason)
    return after
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/edge/test_killswitch_log.py`
Expected: PASS (2 tests).
Run: `python scripts/dev/testrun.py file tests/edge/test_edge_throttle.py`
Run: `python scripts/dev/testrun.py file tests/edge/test_killswitch_db.py`
Expected: PASS (unchanged).

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/edge/throttle.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/edge/throttle.py tests/edge/test_killswitch_log.py
git commit -m "feat(v111): INFO line when the kill switch flips

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/edge/throttle.py tests/edge/test_killswitch_log.py
```

---

### Task V111-11: DEBUG lines for dedup merges and gate rejects

Load the `alert-surface` skill first (this edits `analyze.py`). No computed value may change. The reviewer checks that every `return` value and every attribute assignment is identical before and after.

**Files:**
- Modify: `swingbot/core/scanning/dedup.py` (a module logger, plus one DEBUG line in each dedup function)
- Modify: `swingbot/core/scanning/analyze.py` (`paper_trade_decision` and `attach_plan_v2`'s two rejections, through a new `_reject_plan`)
- Create: `tests/scanning/test_decision_debug_logs.py`

**Interfaces:**
- Consumes: `ScanItem(result, plan, conf, requirements)`, `RequirementCheck(key, label, passed, detail)` (from `swingbot.core.scanning.embeds`), and the test helpers `_item`, `_scenario` from `tests/scanning/test_engine_v2_plans.py`.
- Produces:
  - `dedup.log`
  - `analyze._decision_for(item, already_open) -> tuple[bool, str | None]` (the old body)
  - `analyze._reject_plan(item, reason: str, ticker: str, horizon_key: str) -> None`
  - DEBUG lines starting `dedup:` and `gate:`

`gating.py` is deliberately unchanged (index, resolved ambiguity 5).

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_decision_debug_logs.py`:

```python
"""v111 §3: per-symbol, per-scan DEBUG lines for dedup merges and gate rejects."""
import logging
from types import SimpleNamespace

from swingbot import config
from swingbot.core.scanning import analyze, dedup, engine
from swingbot.core.scanning.analyze import ScanItem, paper_trade_decision
from swingbot.core.scanning.embeds import RequirementCheck
from tests.helpers import make_ohlcv
from tests.scanning.test_engine_v2_plans import _item, _scenario


def _messages(caplog, logger):
    return [r.getMessage() for r in caplog.records if r.name == logger.name]


def _dedup_item(strategy, score):
    return SimpleNamespace(
        result=SimpleNamespace(ticker="AAPL", trend="bullish", strategy=strategy, horizon_key="4w"),
        plan=SimpleNamespace(entry=100.0, take_profit=110.0, stop_loss=95.0),
        conf=SimpleNamespace(score=score, level=3))


def test_dedup_merge_is_logged_at_debug(caplog):
    with caplog.at_level(logging.DEBUG, logger=dedup.log.name):
        out = dedup.dedup_scan_items([_dedup_item("EMA", 60), _dedup_item("Fibonacci", 70)])
    assert len(out) == 1
    assert _messages(caplog, dedup.log) == [
        "dedup: AAPL bullish merged 2 scenario(s) into Fibonacci/4w"]
    assert all(r.levelno == logging.DEBUG for r in caplog.records if r.name == dedup.log.name)


def test_a_lone_scenario_logs_nothing(caplog):
    with caplog.at_level(logging.DEBUG, logger=dedup.log.name):
        dedup.dedup_scan_items([_dedup_item("EMA", 60)])
    assert _messages(caplog, dedup.log) == []


def test_sector_collapse_is_logged_at_debug(caplog):
    items = [SimpleNamespace(sector="XLK", follow_score=80, ticker="AAPL"),
             SimpleNamespace(sector="XLK", follow_score=60, ticker="MSFT")]
    with caplog.at_level(logging.DEBUG, logger=dedup.log.name):
        dedup.dedup_sector_items(items)
    assert _messages(caplog, dedup.log) == ["dedup: sector XLK kept AAPL over MSFT"]


def test_an_unmet_gate_is_logged_with_its_reason(caplog):
    item = ScanItem(result=SimpleNamespace(ticker="AAPL", horizon_key="4w"), plan=None, conf=None,
                    requirements=[RequirementCheck(key="k0", label="Gate 0", passed=False, detail="too far")])
    with caplog.at_level(logging.DEBUG, logger=analyze.log.name):
        assert paper_trade_decision(item, False) == (False, "unmet: Gate 0: too far")
    assert "gate: AAPL (4w) not logged -- unmet: Gate 0: too far" in _messages(caplog, analyze.log)


def test_an_allowed_item_logs_nothing(caplog):
    item = ScanItem(result=None, plan=None, conf=None, requirements=[])
    with caplog.at_level(logging.DEBUG, logger=analyze.log.name):
        assert paper_trade_decision(item, False) == (True, None)
    assert not any(m.startswith("gate:") for m in _messages(caplog, analyze.log))


def test_a_plan_rejection_is_logged_with_its_reason(monkeypatch, caplog):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: None)
    item = _item()
    with caplog.at_level(logging.DEBUG, logger=analyze.log.name):
        engine.attach_plan_v2(item, _scenario(), make_ohlcv([100.0] * 60), "AAPL", "4w", level_map=None)
    assert item.plan_v2_rejected == "no_qualifying_target"
    assert "gate: AAPL (4w) plan rejected -- no_qualifying_target" in _messages(caplog, analyze.log)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_decision_debug_logs.py`
Expected: FAIL. `dedup` has no attribute `log`, and the `gate:` lines are missing.

- [ ] **Step 3: Dedup lines**

In `swingbot/core/scanning/dedup.py`, add `import logging` and `log = logging.getLogger(__name__)`. In `dedup_scan_items`, after `rep.combined_from = [...]` and before `deduped.append(rep)`, add:

```python
            if len(cluster) > 1:
                log.debug("dedup: %s %s merged %d scenario(s) into %s/%s",
                          rep.result.ticker, rep.result.trend, len(cluster),
                          rep.result.strategy, rep.result.horizon_key)
```

In `dedup_sector_items`, change `for group in by_sector.values():` to `for sector, group in by_sector.items():`. After `best.also_qualifying = [...]`, add:

```python
        if best.also_qualifying:
            log.debug("dedup: sector %s kept %s over %s", sector, _item_ticker(best),
                      ", ".join(best.also_qualifying))
```

- [ ] **Step 4: Gate lines**

In `swingbot/core/scanning/analyze.py`, rename the body of `paper_trade_decision` to a private helper and wrap it:

```python
def _decision_for(item: ScanItem, already_open: bool) -> tuple[bool, str | None]:
    if already_open:
        return False, "already open"
    unmet = [f"{requirement.label}: {requirement.detail}"
             for requirement in item.requirements if not requirement.passed]
    if unmet:
        return False, "unmet: " + "; ".join(unmet)
    return True, None


def paper_trade_decision(item: ScanItem, already_open: bool) -> tuple[bool, str | None]:
    """Whether this item is logged, and the ticket's explanation when not."""
    allowed, reason = _decision_for(item, already_open)
    if not allowed:
        log.debug("gate: %s (%s) not logged -- %s", getattr(item.result, "ticker", "?"),
                  getattr(item.result, "horizon_key", "?"), reason)
    return allowed, reason
```

Add below it:

```python
def _reject_plan(item, reason: str, ticker: str, horizon_key: str) -> None:
    """Record why no v2 plan was attached; say so at DEBUG (per symbol, per scan)."""
    item.plan_v2_rejected = reason
    log.debug("gate: %s (%s) plan rejected -- %s", ticker, horizon_key, reason)
```

In `attach_plan_v2`, replace `item.plan_v2_rejected = "no_qualifying_target"` with `_reject_plan(item, "no_qualifying_target", ticker, horizon_key)`, and `item.plan_v2_rejected = "risk_cap"` with `_reject_plan(item, "risk_cap", ticker, horizon_key)`. Keep the `return` after each and every comment above them.

- [ ] **Step 5: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_decision_debug_logs.py`
Expected: PASS (6 tests).
Run: `python scripts/dev/testrun.py file tests/scanning/test_paper_trade_decision.py`
Run: `python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`
Run: `python scripts/dev/testrun.py file tests/marketdata/test_universe.py`
Expected: PASS (unchanged).

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/scanning/dedup.py swingbot/core/scanning/analyze.py`
Expected: `_scan_one` still 39 and `build_decision_context` still 24. `dedup_scan_items`, `dedup_sector_items`, `paper_trade_decision`, `_decision_for`, `_reject_plan` and `attach_plan_v2` are below 15.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/scanning/dedup.py swingbot/core/scanning/analyze.py tests/scanning/test_decision_debug_logs.py
git commit -m "feat(v111): DEBUG lines for dedup merges and gate rejects, with the reason

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/scanning/dedup.py swingbot/core/scanning/analyze.py tests/scanning/test_decision_debug_logs.py
```

---

### Task V111-12: DEBUG lines for fetch misses and fallbacks; "Alpaca miss" drops to DEBUG

**Files:**
- Modify: `swingbot/core/marketdata/yf_safe.py`
- Modify: `swingbot/core/marketdata/providers/router.py` (`_attempt`'s miss line, and a new `_log_fallback` called from `daily_bars`, `latest_prices` and `intraday_bars`)
- Modify: `swingbot/core/marketdata/providers/alpaca_provider.py` (`latest_prices`)
- Create: `tests/marketdata/test_fetch_debug_logs.py`

**Cross-plan overlap:** v106 T13a and v109 V109-4 also edit `router.py`, and v106 T13a edits `alpaca_provider.py`. On a conflict, keep their logic and re-apply these line-local additions.

**Interfaces:**
- Consumes: V111-4's `with_current_context` wrap in `_attempt` (same function; keep it). Test fakes from `tests/marketdata/test_provider_router.py` (`FakeProvider`, `_use`, `enabled`) and `tests/marketdata/test_alpaca_provider.py` (`FakeClient`, `_prov`, `_snap`, `NOW`).
- Produces: `yf_safe.log`, `alpaca_provider.log`, `router._log_fallback(kind: str, symbols: list) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_fetch_debug_logs.py`:

```python
"""v111 §3/§4: fetch misses and fallbacks are DEBUG, per symbol, never INFO."""
import logging

import pandas as pd

from swingbot.core.marketdata import yf_safe
from swingbot.core.marketdata.providers import alpaca_provider, router
from swingbot.core.marketdata.providers.alpaca_provider import AlpacaMiss
from tests.marketdata.test_alpaca_provider import NOW, FakeClient, _prov, _snap
from tests.marketdata.test_provider_router import FakeProvider, _use, enabled  # noqa: F401


def _records(caplog, logger):
    return [r for r in caplog.records if r.name == logger.name]


def test_empty_yfinance_download_is_a_debug_line(monkeypatch, caplog):
    monkeypatch.setattr("yfinance.download", lambda *a, **k: pd.DataFrame())
    with caplog.at_level(logging.DEBUG, logger=yf_safe.log.name):
        yf_safe.download(tickers="ZZZZ", period="5d")
    [record] = _records(caplog, yf_safe.log)
    assert record.levelno == logging.DEBUG and "ZZZZ" in record.getMessage()


def test_alpaca_miss_is_debug_not_info(enabled, monkeypatch, caplog):
    _use(monkeypatch, FakeProvider(exc=AlpacaMiss("boom")))
    with caplog.at_level(logging.DEBUG, logger=router.log.name):
        router.daily_bars(["AAPL"], "2y", lambda tickers, period: {})
    misses = [r for r in _records(caplog, router.log) if "miss" in r.getMessage()]
    assert misses and all(r.levelno == logging.DEBUG for r in misses)


def test_per_symbol_fallback_names_the_symbols(enabled, monkeypatch, caplog):
    _use(monkeypatch, FakeProvider(daily={"AAPL"}))
    with caplog.at_level(logging.DEBUG, logger=router.log.name):
        router.daily_bars(["AAPL", "MSFT"], "2y", lambda tickers, period: {})
    assert "Alpaca daily_bars fallback to yfinance for 1 symbol(s): MSFT" in [
        r.getMessage() for r in _records(caplog, router.log)]


def test_no_fallback_no_line(enabled, monkeypatch, caplog):
    _use(monkeypatch, FakeProvider(daily={"AAPL"}))
    with caplog.at_level(logging.DEBUG, logger=router.log.name):
        router.daily_bars(["AAPL"], "2y", lambda tickers, period: {})
    assert not any("fallback" in r.getMessage() for r in _records(caplog, router.log))


def test_stale_snapshot_names_the_symbol(caplog):
    client = FakeClient(snaps={"AAPL": _snap(190.0, NOW - pd.Timedelta(minutes=20))})
    with caplog.at_level(logging.DEBUG, logger=alpaca_provider.log.name):
        assert _prov(client).latest_prices(["AAPL"], 300) == {}
    assert ["Alpaca snapshot: no fresh price for AAPL"] == [
        r.getMessage() for r in _records(caplog, alpaca_provider.log)]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_fetch_debug_logs.py`
Expected: FAIL. `yf_safe` has no attribute `log`, and the miss line is INFO.

- [ ] **Step 3: `yf_safe.py`**

Add `import logging` and `log = logging.getLogger(__name__)`. Replace `download` with:

```python
def download(*args, **kwargs):
    with _DOWNLOAD_LOCK:
        frame = yf.download(*args, **kwargs)
    if frame is None or getattr(frame, "empty", False):
        log.debug("yfinance download returned no rows: tickers=%r",
                  kwargs.get("tickers", args[0] if args else None))
    return frame
```

(The lock still covers only the `yf.download` call. The empty check reads the returned frame, so it needs no lock.)

- [ ] **Step 4: `router.py`**

In `_attempt`, change `log.info("Alpaca %s miss: %s", method, exc)` to `log.debug("Alpaca %s miss: %s", method, exc)`. Add below `_tag`:

```python
def _log_fallback(kind: str, symbols) -> None:
    """DEBUG line for Alpaca-eligible symbols served by yfinance instead."""
    if symbols:
        log.debug("Alpaca %s fallback to yfinance for %d symbol(s): %s",
                  kind, len(symbols), ", ".join(list(symbols)[:10]))
```

Call it:
- in `daily_bars`, after `misses = [...]`: `_log_fallback("daily_bars", misses)`
- in `latest_prices`, after `misses = [...]`: `_log_fallback("latest_prices", misses)`
- in `intraday_bars`, inside the existing `if df is None or df.empty:` block, before the `yf_fetch` line: `_log_fallback("intraday_bars", [ticker])`

- [ ] **Step 5: `alpaca_provider.py`**

Add `import logging` and `log = logging.getLogger(__name__)`. In `latest_prices`, before `return out`, add:

```python
        missing = [t for t in tickers if t not in out]
        if missing:
            log.debug("Alpaca snapshot: no fresh price for %s", ", ".join(missing[:10]))
```

- [ ] **Step 6: Run the tests**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_fetch_debug_logs.py`
Expected: PASS (5 tests).
Run: `python scripts/dev/testrun.py file tests/marketdata/test_provider_router.py`
Run: `python scripts/dev/testrun.py file tests/marketdata/test_alpaca_provider.py`
Run: `python scripts/dev/testrun.py file tests/marketdata/test_router_scan_context.py`
Expected: PASS (unchanged).

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/marketdata/yf_safe.py swingbot/core/marketdata/providers/router.py swingbot/core/marketdata/providers/alpaca_provider.py`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/marketdata/yf_safe.py swingbot/core/marketdata/providers/router.py swingbot/core/marketdata/providers/alpaca_provider.py tests/marketdata/test_fetch_debug_logs.py
git commit -m "feat(v111): DEBUG lines for fetch misses and Alpaca fallbacks; Alpaca miss INFO -> DEBUG

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/marketdata/yf_safe.py swingbot/core/marketdata/providers/router.py swingbot/core/marketdata/providers/alpaca_provider.py tests/marketdata/test_fetch_debug_logs.py
```

---

### Task V111-13: Command errors shown to the user are also logged, with the traceback

**Files:**
- Modify: `swingbot/commands/backtest.py`, `data.py`, `info.py`, `views.py`, `watchlist.py`, `history.py` (a module logger, plus one `log.warning(..., exc_info=True)` per failing handler)
- Create: `tests/commands/test_command_error_logging.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: a module `log` in each of the six files, and the guard test `test_every_user_facing_exception_is_logged_with_its_traceback`.

The sites at plan time, found by an AST scan for `except Exception` handlers that reply to the user without logging:

| File | Handler | Line to add before the reply |
|---|---|---|
| `backtest.py` | `backtest_cmd`'s `except Exception as e:` (reply `⚠️ Could not fetch data for {ticker}`) | `log.warning("!backtest %s: could not fetch data", ticker, exc_info=True)` |
| `backtest.py` | `_sync_backtest_watchlist`'s `except Exception as e:` (runs in the worker thread; the reply happens later from the `errors` list) | `log.warning("!backtestwatchlist: could not fetch %s", t, exc_info=True)` |
| `data.py` | `charts_cmd`'s `except Exception as e:` (reply `⚠️ Could not export {ticker}`) | `log.warning("!charts: could not export %s", ticker, exc_info=True)` |
| `data.py` | `download_cmd`'s `except Exception as e:` (reply `⚠️ {t}: {e}`) | `log.warning("!download: %s failed", t, exc_info=True)` |
| `info.py` | `ticker_cmd`'s `except Exception as e:` | `log.warning("!ticker %s: could not fetch data", ticker, exc_info=True)` |
| `info.py` | `strategycharts_cmd`'s `except Exception as e:` | `log.warning("!strategycharts %s: could not fetch data", ticker, exc_info=True)` |
| `views.py` | `chart_button`'s first `except Exception as exc:` (price data) | `log.warning("plan panel %s: could not fetch price data for %s", self.plan_id, plan.ticker, exc_info=True)` |
| `views.py` | `chart_button`'s second `except Exception as exc:` (chart render) | `log.warning("plan panel %s: chart render failed", self.plan_id, exc_info=True)` |
| `watchlist.py` | the add command's `except Exception as e:` (reply `⚠️ Heads up: couldn't fetch data`) | `log.warning("!watchlist add %s: could not fetch data", ticker.upper(), exc_info=True)` |
| `history.py` | `plans_cmd`'s `except Exception as e:` (reply by `status_msg.edit`) | `log.warning("!plans %s: could not generate plans", ticker, exc_info=True)` |

Input-validation replies are not logged (index, resolved ambiguity 8).

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_command_error_logging.py`:

```python
"""v111 §3: an exception a command shows the user is also logged with its traceback."""
import ast
import asyncio
import logging
import pathlib

COMMANDS = pathlib.Path(__file__).resolve().parents[2] / "swingbot" / "commands"
_REPLIES = {"send", "send_message", "edit"}


def _calls(handler):
    return [node for stmt in handler.body for node in ast.walk(stmt)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]


def _logs_traceback(handler):
    for call in _calls(handler):
        if call.func.attr == "exception":
            return True
        if call.func.attr in {"warning", "error"} and any(k.arg == "exc_info" for k in call.keywords):
            return True
    return False


def _silent_user_facing_handlers(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for handler in (n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)):
        catches_exception = isinstance(handler.type, ast.Name) and handler.type.id == "Exception"
        replies = any(call.func.attr in _REPLIES for call in _calls(handler))
        if catches_exception and replies and not _logs_traceback(handler):
            yield handler.lineno


def test_every_user_facing_exception_is_logged_with_its_traceback():
    offenders = [f"{path.relative_to(COMMANDS.parent.parent).as_posix()}:{line}"
                 for path in sorted(COMMANDS.rglob("*.py"))
                 for line in _silent_user_facing_handlers(path)]
    assert offenders == [], "add log.warning(..., exc_info=True) beside the reply:\n" + "\n".join(offenders)


class _Ctx:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append(args[0] if args else kwargs)


def test_ticker_command_failure_is_logged_and_still_shown(monkeypatch, caplog):
    from swingbot.commands import info

    def boom(ticker):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(info, "_sync_ticker_snapshot", boom)
    ctx = _Ctx()
    with caplog.at_level(logging.WARNING, logger=info.log.name):
        asyncio.run(info.ticker_cmd.callback(ctx, "aapl"))

    [record] = [r for r in caplog.records if r.name == info.log.name]
    assert record.levelno == logging.WARNING and record.exc_info is not None
    assert "AAPL" in record.getMessage()
    assert ctx.sent[-1] == "⚠️ Could not fetch data for AAPL: yahoo down"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_command_error_logging.py`
Expected: FAIL. The guard lists nine handlers, and `info` has no attribute `log`. The table's tenth row, `_sync_backtest_watchlist`, replies later through its `errors` list, so the guard cannot see it; fix it anyway.

- [ ] **Step 3: Add the loggers and the lines**

In each of the six files, add `import logging` to the stdlib imports and `log = logging.getLogger(__name__)` after the imports. Then add each line from the table as the **first statement** of its handler, before the existing reply. For example, `info.ticker_cmd`:

```python
    try:
        df, results, regime = await asyncio.to_thread(_sync_ticker_snapshot, ticker)
    except Exception as e:
        log.warning("!ticker %s: could not fetch data", ticker, exc_info=True)
        await ctx.send(f"⚠️ Could not fetch data for {ticker}: {e}")
        return
```

and `backtest._sync_backtest_watchlist`:

```python
        try:
            df = get_daily_data(t, period="max")
        except Exception as e:
            log.warning("!backtestwatchlist: could not fetch %s", t, exc_info=True)
            errors.append((t, str(e)))
            continue
```

Leave every user-facing message unchanged.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/commands/test_command_error_logging.py`
Expected: PASS (2 tests).
Run: `python scripts/dev/testrun.py file tests/commands/test_backtest_format.py`
Run: `python scripts/dev/testrun.py file tests/commands/test_history_format.py`
Run: `python scripts/dev/testrun.py file tests/test_views.py`
Expected: PASS (unchanged).

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/commands/backtest.py swingbot/commands/data.py swingbot/commands/info.py swingbot/commands/views.py swingbot/commands/watchlist.py swingbot/commands/history.py`
Expected: values unchanged from the index baselines (`ticker_cmd` 15, `plans_cmd` 24, `scrapeall_cmd` 18, `backtestwatchlist_cmd` 14, `_run_backtest_combo` 15). A log line adds no branch.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/backtest.py swingbot/commands/data.py swingbot/commands/info.py swingbot/commands/views.py swingbot/commands/watchlist.py swingbot/commands/history.py tests/commands/test_command_error_logging.py
git commit -m "fix(v111): command errors shown to the user are logged with their traceback

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/commands/backtest.py swingbot/commands/data.py swingbot/commands/info.py swingbot/commands/views.py swingbot/commands/watchlist.py swingbot/commands/history.py tests/commands/test_command_error_logging.py
```

---

### Task V111-14: Healthcheck cleanup failures are logged, not swallowed

**Files:**
- Modify: `swingbot/commands/scanning/presence.py` (`_post_healthcheck`'s delete loop, through a new `_delete_healthcheck`)
- Create: `tests/commands/test_healthcheck_cleanup.py`

**v110 overlap:** v110 prefixes the healthcheck text with 🩺 in this area. The change here replaces only the `for old_msg in _healthcheck_msgs:` loop body.

**Interfaces:**
- Consumes: V111-7's `presence.log`.
- Produces: `presence._delete_healthcheck(msg) -> None` (async).

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_healthcheck_cleanup.py`:

```python
"""v111 §3: the hourly healthcheck cleanup no longer swallows every error.
404 (already gone) is DEBUG, any other Discord HTTP error is WARNING with the
traceback, and a non-HTTP error is a bug that propagates."""
import asyncio
import logging
from types import SimpleNamespace

import discord
import pytest

from swingbot.commands.scanning import presence


def _http_error(cls, status):
    return cls(SimpleNamespace(status=status, reason="x"), "boom")


class _Msg:
    id = 42

    def __init__(self, exc=None):
        self.exc = exc

    async def delete(self):
        if self.exc is not None:
            raise self.exc


def _records(caplog):
    return [r for r in caplog.records if r.name == presence.log.name]


def test_a_message_already_gone_is_debug(caplog):
    with caplog.at_level(logging.DEBUG, logger=presence.log.name):
        asyncio.run(presence._delete_healthcheck(_Msg(_http_error(discord.NotFound, 404))))
    [record] = _records(caplog)
    assert record.levelno == logging.DEBUG


def test_any_other_http_failure_is_a_warning_with_traceback(caplog):
    with caplog.at_level(logging.DEBUG, logger=presence.log.name):
        asyncio.run(presence._delete_healthcheck(_Msg(_http_error(discord.Forbidden, 403))))
    [record] = _records(caplog)
    assert record.levelno == logging.WARNING and record.exc_info is not None


def test_a_successful_delete_logs_nothing(caplog):
    with caplog.at_level(logging.DEBUG, logger=presence.log.name):
        asyncio.run(presence._delete_healthcheck(_Msg()))
    assert _records(caplog) == []


def test_a_non_http_error_is_not_swallowed():
    with pytest.raises(RuntimeError):
        asyncio.run(presence._delete_healthcheck(_Msg(RuntimeError("bug"))))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_healthcheck_cleanup.py`
Expected: FAIL with `AttributeError: … has no attribute '_delete_healthcheck'`.

- [ ] **Step 3: Implement**

In `swingbot/commands/scanning/presence.py`, add above `_post_healthcheck`:

```python
async def _delete_healthcheck(msg) -> None:
    """Delete one of last hour's healthcheck lines. Already gone (404) is
    routine; any other Discord refusal is worth a warning. A non-HTTP error
    is a bug and propagates to the tick's own error handling."""
    try:
        await msg.delete()
    except discord.NotFound:
        log.debug("Healthcheck message %s already gone", getattr(msg, "id", "?"))
    except discord.HTTPException:
        log.warning("Could not delete healthcheck message %s", getattr(msg, "id", "?"),
                    exc_info=True)
```

In `_post_healthcheck`, replace:

```python
        for old_msg in _healthcheck_msgs:
            try:
                await old_msg.delete()
            except Exception:
                pass  # already gone, or too old/no permission -- not worth failing the tick over
```

with:

```python
        for old_msg in _healthcheck_msgs:
            await _delete_healthcheck(old_msg)
```

(`discord.NotFound` subclasses `discord.HTTPException`, so the order of the two `except` clauses matters and must stay as written.)

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/commands/test_healthcheck_cleanup.py`
Expected: PASS (4 tests).
Run: `python scripts/dev/testrun.py file tests/infra/test_silent_alerts_channel.py`
Expected: PASS (unchanged).

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/commands/scanning/presence.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/presence.py tests/commands/test_healthcheck_cleanup.py
git commit -m "fix(v111): healthcheck cleanup logs 404 at DEBUG and other HTTP failures at WARNING

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/commands/scanning/presence.py tests/commands/test_healthcheck_cleanup.py
```
