# v209 — Market-shock detector, part 3: scan wiring and the plan stamp

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v209 — Market-shock detector](../specs/2026-11-05-v209-market-shock-detector-design.md)
**Index:** [`2026-11-05-v209-market-shock-detector_0-index.md`](2026-11-05-v209-market-shock-detector_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there; every task below implicitly carries the index's Global Constraints.

This part builds **V209-6b, V209-6c, V209-7 and V209-8** (V209-8b moved to part 3b at the 1500-line cap): the scheduled scan steps the
detector through a guarded call in `_sync_run_scan` and a keyword-only
`run_scan(step_shock=)` that only `_session_scan_tick` sets (V209-6b); the
label returned by that line travels as an argument into every confluence,
requote and strategy plan, and `params.stamp_entry_context` merges it into
`entry_context` after the feature dict (V209-7); the SHORT lane reads the
stored label once per run through its lane dict, and a byte-identical test
pins every lane under `off` and `shadow` (V209-8b).

Decided choices restated so a task read alone is complete:

- Parts 1, 1b and 2 are merged on the worktree branch first.
  `swingbot/core/scanning/shock_scan.py` (V209-6, V209-6a) exports
  `run_shock_pass(*, step_shock, frames, live_prices, sector_of, quotes_at, spy_df=None, now=None, repo=None) -> str | None`
  (the label to stamp this pass; `None` under `off`; it never fetches a
  quote and never raises: a failure is swallowed and the stored label
  returned; V209-6b still wraps the call site, belt and braces) and
  `current_label(*, repo=None) -> str | None` (`"NORMAL"` before the first
  reading, `None` under `off` or when the store is unreadable).
- `_sync_run_scan` is CC 94 and `_session_scan_tick` CC 15: neither gains a
  branch. `attach_plan_v2` (12) and `_maybe_run_strategy_pass` gain none
  either; the one conditional ("add the key only when not `None`") lives in
  the new helper `params.shock_asof` and in `params._merge_shock_state`.
- `shock_state` is never added to `edge/context.py:FEATURE_KEYS`; `None`
  means **absent**, never a `None` value, so `MARKET_SHOCK_MODE=off` is a
  byte-identical kill switch.
- Every task's tests reach no network. The end-to-end `_sync_run_scan`
  drivers that already exist now also read the stored label through
  `current_label()`, which opens the test database: run `/replicate-prod-db`
  first so the shared `swing-db` is up (a skip means it is unreachable —
  fix that, never accept it).

# Phase 5 — scan wiring and the plan stamp

### Task V209-6b: Scan wiring: `run_scan(step_shock=)`, `quotes_at`, the guarded shock call, the scheduled call

**Model:** opus — wiring into a CC-94 legacy function and the scan's async/thread boundary, where a positional slip or a second stepping caller silently corrupts the state machine.

**Files:**
- Modify: `swingbot/core/scanning/scan_run.py` (`from . import (...)` gains `shock_scan`; new module helper `_shock_state_for_pass`; `run_scan`, `_run_scan_in_context`, `_sync_run_scan`: one `quotes_at` line and one `shock_state = _shock_state_for_pass(...)` statement; V209-6c then changes the live-price line)
- Modify: `swingbot/commands/scanning/loops.py` (the scheduled `_run_scan_posting_partial(...)` call inside `_session_scan_tick` adds `step_shock=True`)
- Modify: `tests/scanning/test_run_scan_scan_id.py` (fakes accept `step_shock`)
- Modify: `tests/scanning/test_run_scan_publishes_progress.py` (its fixed-arity fake accepts `step_shock` too — the same positional-fake trap, T6)
- Create: `tests/commands/test_shock_step_gate.py`

**Interfaces:**
- Consumes: `shock_scan.run_shock_pass(*, step_shock, frames, live_prices, sector_of, quotes_at, spy_df=None, now=None, repo=None) -> str | None` (V209-6a; never fetches, never raises).
- Produces:
  - `scan_run._shock_state_for_pass(**kwargs) -> str | None` — `shock_scan.run_shock_pass(**kwargs)`, or `None` (swallow tag `scan.shock.call`) when it raises, so the scan always proceeds and that pass's plans carry no `shock_state` key. V209-8b pins it.
  - `run_scan(horizon_filter="all", require_confirmation=True, bot=None, progress=None, min_confluence=None, *, step_shock: bool = False) -> list`
  - `_run_scan_in_context(horizon_filter, require_confirmation, bot, progress, min_confluence, step_shock=False)`
  - `_sync_run_scan(horizon_filter, require_confirmation, progress=None, min_confluence=None, params=None, step_shock: bool = False) -> tuple`, which binds the local `shock_state: str | None` right after the sector-map block, before the market-context stamp and before any plan builder runs. V209-7 threads this local into the plan builders. Until V209-6c it hands the pass the scan's `live_prices` as they are.
  - Only `_session_scan_tick` passes `step_shock=True`; `!check` (`commands.py:_check_live`), the recap (`recap.py`) and the admin-UI scan (`loops.py`, `require_confirmation=False`) pass nothing and therefore only read the stored label.

- [ ] **Step 1: Run `/replicate-prod-db`** (skip if a sibling task in this session already synced the replica). The existing end-to-end `_sync_run_scan` drivers run in Step 7 now read the stored label through `current_label()`, which opens the test database.

- [ ] **Step 2: Write the failing gate test**

Create `tests/commands/test_shock_step_gate.py`:

```python
"""v209: only the scheduled session scan steps the market-shock state.

!check, the recap and the admin-UI scan go through run_scan without the flag
and only read the stored label (spec § The reading, Gating)."""
import ast
import asyncio
import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

from swingbot import config
from swingbot.commands.scanning import loops
from swingbot.core.scanning import fetch, runstate, scan_run, shock_scan
from tests.helpers import make_ohlcv

REPO = Path(__file__).resolve().parents[2]
SCAN_CALLS = {"run_scan", "_run_scan_posting_partial"}


class _Calls(ast.NodeVisitor):
    """Every run_scan-family call with its innermost enclosing function."""

    def __init__(self, filename):
        self.filename, self.stack, self.found = filename, [], []

    def _function(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _function

    def visit_Call(self, node):
        func = node.func
        called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if called in SCAN_CALLS:
            flag = next((k.value for k in node.keywords if k.arg == "step_shock"), None)
            self.found.append((self.filename, self.stack[-1] if self.stack else None,
                               None if flag is None else ast.unparse(flag)))
        self.generic_visit(node)


def _scan_calls():
    found = []
    for path in sorted((REPO / "swingbot" / "commands").rglob("*.py")):
        visitor = _Calls(path.name)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        found.extend(visitor.found)
    return found


def test_only_the_scheduled_session_scan_passes_step_shock():
    stepping = [call for call in _scan_calls() if call[2] is not None]
    assert stepping == [("loops.py", "_session_scan_tick", "True")]


def test_check_recap_and_the_admin_scan_still_call_run_scan_without_the_flag():
    calls = _scan_calls()
    readers = {(name, fn) for name, fn, flag in calls if flag is None}
    assert ("commands.py", "_check_live") in readers
    assert any(name == "recap.py" for name, _fn, _flag in calls)
    assert all(flag is None for name, _fn, flag in calls if name in ("commands.py", "recap.py"))
    loops_readers = [fn for name, fn, flag in calls
                     if name == "loops.py" and flag is None and fn != "_run_scan_posting_partial"]
    assert loops_readers, "the admin-UI scan call in loops.py must exist and carry no step_shock"


def test_posting_partial_forwards_the_flag_to_run_scan(monkeypatch):
    seen = {}

    async def fake_run_scan(**kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(loops.scan_engine, "run_scan", fake_run_scan)
    asyncio.run(loops._run_scan_posting_partial("chan", require_confirmation=True, step_shock=True))
    assert seen == {"require_confirmation": True, "step_shock": True}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    # Same isolation as tests/scanning/test_run_scan_scan_id.py.
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runstate, "_mark_running", lambda running: None)
    monkeypatch.setattr(runstate, "_clear_stop", lambda: None)


def test_run_scan_takes_step_shock_by_keyword_only_and_defaults_off():
    param = inspect.signature(scan_run.run_scan).parameters["step_shock"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY and param.default is False
    assert inspect.signature(scan_run._sync_run_scan).parameters["step_shock"].default is False


@pytest.mark.parametrize("kwargs,expected", [({}, False), ({"step_shock": True}, True)])
def test_run_scan_hands_the_flag_to_the_worker_thread(isolated, monkeypatch, kwargs, expected):
    seen = []

    def fake_sync_run(horizon_filter, require_confirmation, progress, min_confluence,
                      step_shock=False):
        seen.append(step_shock)
        return [], [], []

    monkeypatch.setattr(scan_run, "_sync_run_scan", fake_sync_run)
    asyncio.run(scan_run.run_scan(**kwargs))
    assert seen == [expected]


class _Halt(BaseException):
    """Raised by the fake shock pass so the worker stops right after it. A
    BaseException, so _shock_state_for_pass's `except Exception` lets it through."""


@pytest.fixture
def worker(monkeypatch):
    frames = {"AAA": make_ohlcv([100.0] * 60), "SPY": make_ohlcv([400.0] * 60)}
    order, asked = [], []
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")
    monkeypatch.setattr(scan_run, "_reload_config_before_scan", lambda: {})
    monkeypatch.setattr(scan_run, "_scan_tickers", lambda: ["AAA"])
    monkeypatch.setattr(scan_run.opex, "current_tier", lambda: None)
    monkeypatch.setattr(fetch, "_crawl_latest_data", lambda tickers, progress=None: dict(frames))

    def live(tickers, progress=None):
        order.append(("live", datetime.now(timezone.utc)))
        asked.append(list(tickers))
        return {t: QUOTES[t] for t in tickers}

    monkeypatch.setattr(fetch, "_fetch_live_prices", live)
    monkeypatch.setattr(scan_run.rs_factors, "refresh_rs_cache", lambda data, spy: None)
    monkeypatch.setattr(scan_run, "get_regime", lambda df: None)
    monkeypatch.setattr(fetch, "_etf_symbol_of_sector", lambda: {"Information Technology": "XLK"})
    monkeypatch.setattr(fetch, "_sector_etfs_for_tickers",
                        lambda tickers: ({"AAA": "Information Technology"}, []))

    def shock_pass(**kwargs):
        order.append(("shock", kwargs))
        raise _Halt

    monkeypatch.setattr(shock_scan, "run_shock_pass", shock_pass)
    return frames, order, asked


QUOTES = {"AAA": 97.0, "SPY": 400.0, "QQQ": 300.0}


@pytest.mark.parametrize("flag", [False, True])
def test_the_worker_hands_the_pass_its_own_frames_quotes_sectors_and_clock(worker, flag):
    frames, order, _asked = worker
    with pytest.raises(_Halt):
        scan_run._sync_run_scan("all", True, None, None, step_shock=flag)
    (first, live_at), (second, kwargs) = order
    assert (first, second) == ("live", "shock")
    assert kwargs["step_shock"] is flag
    assert set(kwargs["frames"]) == {"AAA", "SPY"}
    assert kwargs["live_prices"] == {"AAA": 97.0}
    assert kwargs["sector_of"] == {"AAA": "Information Technology"}
    assert kwargs["spy_df"] is frames["SPY"]
    quotes_at = kwargs["quotes_at"]
    assert quotes_at.tzinfo is not None and quotes_at >= live_at


def test_a_raising_shock_pass_yields_no_label_and_the_scan_goes_on(monkeypatch, caplog):
    def boom(**kwargs):
        raise RuntimeError("shock pass blew up")

    monkeypatch.setattr(shock_scan, "run_shock_pass", boom)
    assert scan_run._shock_state_for_pass(step_shock=True) is None
    assert any(getattr(r, "swallowed_tag", "") == "scan.shock.call" for r in caplog.records)


def test_the_label_is_bound_once_before_any_plan_is_built():
    src = inspect.getsource(scan_run._sync_run_scan)
    assert src.count("_shock_state_for_pass(") == 1 and "run_shock_pass(" not in src
    assert src.index("shock_state = _shock_state_for_pass(") < src.index("_attach_item_plan(")
    assert src.index("quotes_at = datetime.now(timezone.utc)") < src.index("_shock_state_for_pass(")
```

If a stub in the `worker` fixture misses a call the worker makes before the
shock pass (the test then fails with a network or database error rather than
`_Halt`), stub that call too; never move the shock pass earlier to dodge it.

- [ ] **Step 3: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/commands/test_shock_step_gate.py`
Expected: FAIL — `test_only_the_scheduled_session_scan_passes_step_shock` (no caller passes the flag), `KeyError: 'step_shock'` from the signature test, `TypeError: _sync_run_scan() got an unexpected keyword argument 'step_shock'`, `AttributeError` for `_shock_state_for_pass`.

- [ ] **Step 4: Wire `swingbot/core/scanning/scan_run.py`**

4a. The package import (keep it alphabetical; `shock_scan` sorts before `short_funnel`):

```python
from . import (analyze, dedup, fetch, lane_overlap, progress_store, rejection_recorder, runstate,
               shock_scan, short_funnel, strategy_pass, telemetry)
```

4b. `run_scan` — add the keyword-only flag, one docstring paragraph, and forward it:

```python
async def run_scan(horizon_filter: str = "all", require_confirmation: bool = True, bot=None, progress: "ScanProgress" = None,
                    min_confluence: int = None, *, step_shock: bool = False) -> list:
```

Append to its docstring, before the closing `"""`:

```text
    v209: `step_shock` (keyword only) lets this pass take a market-shock
    reading and step the state. Only the scheduled session scan sets it;
    `!check`, the recap and the admin-UI scan leave it False and only read
    the stored label for their plans.
```

and change its body's call to:

```python
    with scan_context(new_scan_id()):
        return await _run_scan_in_context(horizon_filter, require_confirmation, bot,
                                          progress, min_confluence, step_shock=step_shock)
```

4c. `_run_scan_in_context` — signature and the thread call:

```python
async def _run_scan_in_context(horizon_filter, require_confirmation, bot, progress,
                               min_confluence, step_shock=False) -> list:
```

```python
                alerts, newly_closed, near_close_warnings = await asyncio.to_thread(
                    _sync_run_scan, horizon_filter, require_confirmation, progress, min_confluence,
                    step_shock=step_shock
                )
```

4d. `_sync_run_scan` — signature and one docstring paragraph:

```python
def _sync_run_scan(horizon_filter: str, require_confirmation: bool, progress: "ScanProgress" = None,
                    min_confluence: int = None, params: ScanParams | None = None,
                    step_shock: bool = False) -> tuple:
```

Append to the docstring, before the closing `"""`:

```text
    `step_shock` (v209) is run_scan's flag: True only for the scheduled
    session scan, which may then write a market-shock reading.
```

4e. Directly below `live_prices = fetch._fetch_live_prices(tickers, progress)` (above `_finish_phase("live_prices")`):

```python
    quotes_at = datetime.now(timezone.utc)   # v209: live_prices carry no per-quote time
```

(`datetime` and `timezone` are already imported at the top of `scan_run.py`.)

4f. Directly below the sector-ETF `try/except` block (the one whose `except`
ends `sector_etf_frames = {}`), above the `# Market context (P0):` comment:

```python
    # v209: one market-shock reading per scheduled pass (shock_scan owns the
    # NYSE-regular-hours gate and swallows its own failures); the returned
    # label is stamped on this pass's plans. None under MARKET_SHOCK_MODE=off.
    shock_state = _shock_state_for_pass(
        step_shock=step_shock, frames=fresh_data, live_prices=live_prices,
        sector_of=sector_of_ticker, quotes_at=quotes_at, spy_df=spy_df)
```

`spy_df` here is the frame the RS block already resolved (`None` when SPY
could not be fetched, which `run_shock_pass` handles). No `if`, no `try` in
`_sync_run_scan`: its CC stays 94. `shock_state` is unused until V209-7.

4g. Add the wrapper as a module-level function directly above `_sync_run_scan`:

```python
def _shock_state_for_pass(**kwargs) -> str | None:
    """v209: the shock pass's label for this scan. run_shock_pass swallows its own
    failures; this wrapper is belt and braces so a raise can never stop the scan
    (LONG issuing unchanged): the pass then stamps no shock_state key."""
    try:
        return shock_scan.run_shock_pass(**kwargs)
    except Exception as exc:
        swallowed(log, "scan.shock.call", exc,
                  "shock pass raised; scanning without a label: %s", exc, exc_info=True)
        return None
```

- [ ] **Step 5: Set the flag on the scheduled call in `swingbot/commands/scanning/loops.py`**

V209-5b inserted `_prune_shock_readings` above this call, so find it by
text, not by line number:

Run: `git grep -n "require_confirmation=True, bot=bot, progress=progress)" -- swingbot/commands/scanning/loops.py`
Expected: one hit, inside `_session_scan_tick`.

Replace that call with:

```python
    # v209: the only caller that steps the market-shock state (spec § Gating).
    alerts = await _run_scan_posting_partial(
        channel, require_confirmation=True, bot=bot, progress=progress, step_shock=True)
```

Leave the admin-UI call (`require_confirmation=False`) untouched.
`_session_scan_tick` stays CC 15 (a keyword argument is not a branch).

- [ ] **Step 6: Update the two fixed-arity fakes of `_sync_run_scan`**

In `tests/scanning/test_run_scan_scan_id.py`:

```python
    def fake_sync_run(horizon_filter, require_confirmation, progress, min_confluence,
                      step_shock=False):
        seen.append(scan_id_var.get())
        return [], [], []
```

and

```python
def test_a_scan_that_raises_still_resets_the_id(data_dir, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("fetch died")
```

In `tests/scanning/test_run_scan_publishes_progress.py`:

```python
    def fake_sync_run(horizon_filter, require_confirmation, progress, min_confluence,
                      step_shock=False):
        seen["during"] = progress_store.read()
        if raises:
            raise RuntimeError("fetch died")
        return [], [], []
```

(Its other fake, `lambda *a, **k: ([], [], [])`, already accepts the keyword.)

- [ ] **Step 7: Run the tests to verify they pass**

Run each:
`python scripts/dev/testrun.py file tests/commands/test_shock_step_gate.py`
`python scripts/dev/testrun.py file tests/scanning/test_run_scan_scan_id.py`
`python scripts/dev/testrun.py file tests/scanning/test_run_scan_publishes_progress.py`
`python scripts/dev/testrun.py file tests/commands/test_store_write_halt.py` (its `_run_scan(**kw)` fake)
`python scripts/dev/testrun.py file tests/commands/test_loops_cooldown.py`
`python scripts/dev/testrun.py file tests/scanning/test_short_lane_split.py` (drives `_sync_run_scan` end to end)
`python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`
Expected: PASS, and 0 skipped in the last two (a skip means the shared `swing-db` is unreachable; the drivers now read the stored label).

Run: `python scripts/dev/complexity_gate.py`
Expected: no violation; `_sync_run_scan` still 94, `_session_scan_tick` still 15, `_shock_state_for_pass` CC 2.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/scanning/scan_run.py swingbot/commands/scanning/loops.py \
        tests/commands/test_shock_step_gate.py tests/scanning/test_run_scan_scan_id.py \
        tests/scanning/test_run_scan_publishes_progress.py
git commit -m "feat(v209): run_scan(step_shock=) -- guarded shock call; only the session scan steps"
```

### Task V209-6c: SPY and QQQ ride the scan's one live-price fetch

**Model:** opus — it edits the one batched quote call every long plan prices from, inside a CC-94 function; an order change or a leaked key moves live long plans.

Split from V209-6b at the 20 KB task cap. Runs straight after V209-6b on the
same branch and before V209-7.

**Files:**
- Modify: `swingbot/core/scanning/shock_scan.py` (append `QQQ_TICKER`, `_benchmarks`, `quote_tickers`, `scan_quotes`)
- Modify: `swingbot/core/scanning/scan_run.py` (`_sync_run_scan`: the live-price line at `scan_run.py:548` becomes two lines; the `_shock_state_for_pass(...)` call passes `live_prices=shock_prices`)
- Modify: `tests/commands/test_shock_step_gate.py` (one assertion changed, four tests appended)

**Interfaces:**
- Consumes: `shock_scan.shock_mode()` (V209-6); `scan_run._shock_state_for_pass(**kwargs)`, the `worker` fixture, `QUOTES` and `_Halt` in `tests/commands/test_shock_step_gate.py` (V209-6b); existing `fetch._fetch_live_prices(tickers, progress)` (the scan's one batched call), `config.MARKET_REGIME_TICKER`.
- Produces:
  - `shock_scan.QQQ_TICKER = "QQQ"` (the default `build_snapshot` already uses for `qqq_ticker`).
  - `shock_scan.quote_tickers(tickers: list, step_shock: bool) -> list` — `tickers` itself (same object, untouched) unless `step_shock` is true and `shock_mode() != "off"`; then a new list: `tickers` in its own order, followed by `config.MARKET_REGIME_TICKER` and `QQQ_TICKER`, each only when not already in `tickers` (deduped, SPY before QQQ), **and only as many as fit in the free room of the last `BATCH_FETCH_CHUNK_SIZE` chunk** (`(-len(tickers)) % chunk`), so the fetch never gains a chunk; an empty watchlist or a full last chunk gets no extras, and the pass records the reading without SPY/QQQ (V209-6a's None path).
  - `shock_scan.scan_quotes(prices: dict, tickers: list) -> dict` — `prices` with the benchmark keys that are **not** in `tickers` removed; the same `prices` object when there is nothing to remove. The long scan, the strategy pass and the SHORT lane see exactly the quote dict they saw before v209.
  - `_sync_run_scan` keeps exactly one `_fetch_live_prices` call; the shock pass gets its full result (`shock_prices`), everything else the `scan_quotes` view (`live_prices`).

**Why the extra quotes ride the existing fetch (index Global Constraints,
"LONG issuing is unchanged", (b)).** The shock pass must add no network call
of its own before the plan builders. Every consumer of `live_prices`
downstream (`analyze.py:1045` `_scan_one`, `analyze.py:1361` the strategy
context, the SHORT lane) looks quotes up with `.get(ticker)` for its own
ticker, so extra keys would be inert today; `scan_quotes` still strips them
so a future `items()` loop cannot pick up a non-watchlist SPY or QQQ.
Appending at the end keeps every existing ticker in the same chunk
position; only the last chunk grows, by at most its free room, and only on
stepped passes. The chunk count — and so the number of network round-trips
before the plan builders — never changes (partner, 2026-11-06: no added
call on the long path, not even a bounded one).

- [ ] **Step 1: Write the failing tests**

In `tests/commands/test_shock_step_gate.py`, change the last assertion of
`test_the_worker_hands_the_pass_its_own_frames_quotes_sectors_and_clock` to:

```python
    assert kwargs["live_prices"] == (QUOTES if flag else {"AAA": 97.0})
```

and append:

```python
@pytest.mark.parametrize("mode,flag,extra", [
    ("off", True, []), ("shadow", False, []), ("live", False, []),
    ("shadow", True, ["SPY", "QQQ"]), ("live", True, ["SPY", "QQQ"])])
def test_the_one_live_price_fetch_carries_spy_and_qqq_only_when_stepping(
        worker, monkeypatch, mode, flag, extra):
    _frames, _order, asked = worker
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", mode)
    with pytest.raises(_Halt):
        scan_run._sync_run_scan("all", True, None, None, step_shock=flag)
    assert asked == [["AAA", *extra]]       # one fetch, watchlist order first, extras appended


def test_quote_tickers_appends_missing_benchmarks_without_reordering(monkeypatch):
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")
    watchlist = ["QQQ", "MSFT", "AAPL"]
    assert shock_scan.quote_tickers(watchlist, True) == ["QQQ", "MSFT", "AAPL", "SPY"]
    assert shock_scan.quote_tickers(["SPY", "QQQ"], True) == ["SPY", "QQQ"]
    assert shock_scan.quote_tickers([], True) == []                  # no chunk to ride
    assert watchlist == ["QQQ", "MSFT", "AAPL"]                     # never mutated
    assert shock_scan.quote_tickers(watchlist, False) is watchlist
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "off")
    assert shock_scan.quote_tickers(watchlist, True) is watchlist


@pytest.mark.parametrize("watchlist,expected", [
    (["A", "B", "C"], ["A", "B", "C"]),                 # last chunk full: no extras, no new chunk
    (["A", "B"], ["A", "B", "SPY"]),                    # room for one
    (["A"], ["A", "SPY", "QQQ"]),                       # room for both
    (["A", "B", "C", "D"], ["A", "B", "C", "D", "SPY", "QQQ"])])
def test_quote_tickers_never_adds_a_fetch_chunk(monkeypatch, watchlist, expected):
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")
    monkeypatch.setattr(config, "BATCH_FETCH_CHUNK_SIZE", 3)
    got = shock_scan.quote_tickers(watchlist, True)
    assert got == expected
    assert -(-len(got) // 3) == -(-len(watchlist) // 3)   # same chunk count


def test_scan_quotes_hides_only_the_benchmarks_the_watchlist_lacks(monkeypatch):
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    prices = {"MSFT": 1.0, "SPY": 2.0, "QQQ": 3.0}
    assert shock_scan.scan_quotes(prices, ["MSFT"]) == {"MSFT": 1.0}
    assert shock_scan.scan_quotes(prices, ["MSFT", "SPY"]) == {"MSFT": 1.0, "SPY": 2.0}
    plain = {"MSFT": 1.0}
    assert shock_scan.scan_quotes(plain, ["MSFT"]) is plain          # nothing to strip: same dict
    assert shock_scan.scan_quotes({}, []) == {}
    assert prices == {"MSFT": 1.0, "SPY": 2.0, "QQQ": 3.0}          # never mutated


def test_the_scan_keeps_one_live_price_fetch_and_hands_the_pass_the_full_result():
    src = inspect.getsource(scan_run._sync_run_scan)
    assert src.count("_fetch_live_prices(") == 1
    assert "fetch._fetch_live_prices(shock_scan.quote_tickers(tickers, step_shock), progress)" in src
    assert "live_prices = shock_scan.scan_quotes(shock_prices, tickers)" in src
    assert "live_prices=shock_prices" in src
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_shock_step_gate.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.scanning.shock_scan' has no attribute 'quote_tickers'` (and `scan_quotes`), the stepped `worker` cases (`asked == [["AAA"]]`, `live_prices` lacks SPY/QQQ) and the source test.

- [ ] **Step 3: Append the helpers to `swingbot/core/scanning/shock_scan.py`**

```python
QQQ_TICKER = "QQQ"


def _benchmarks() -> tuple[str, str]:
    return str(config.MARKET_REGIME_TICKER), QQQ_TICKER


def quote_tickers(tickers: list, step_shock: bool) -> list:
    """The scan's one live-price list: the watchlist untouched, plus SPY and QQQ
    appended (deduped) on a stepped pass, so the shock pass never fetches --
    only into the last chunk's free room, so the fetch never gains a chunk."""
    if not step_shock or shock_mode() == "off":
        return tickers
    have = set(tickers)
    room = (-len(tickers)) % max(1, int(getattr(config, "BATCH_FETCH_CHUNK_SIZE", 100)))
    extra = [t for t in dict.fromkeys(_benchmarks()) if t not in have][:room]
    return [*tickers, *extra] if extra else tickers


def scan_quotes(prices: dict, tickers: list) -> dict:
    """The quote dict the rest of the scan sees: benchmark extras the watchlist
    does not hold are removed, so the long and SHORT lanes see what they saw before."""
    have = set(tickers)
    drop = [t for t in _benchmarks() if t not in have and t in prices]
    if not drop:
        return prices
    return {t: p for t, p in prices.items() if t not in drop}
```

- [ ] **Step 4: Route the extra quotes in `swingbot/core/scanning/scan_run.py`**

Replace the scan's one live-price line,
`live_prices = fetch._fetch_live_prices(tickers, progress)` (above
`_finish_phase("live_prices")`), with these two lines; the v55 Phase 1b
comment above it and V209-6b's `quotes_at` line below it stay:

```python
    shock_prices = fetch._fetch_live_prices(shock_scan.quote_tickers(tickers, step_shock), progress)
    live_prices = shock_scan.scan_quotes(shock_prices, tickers)   # v209: SPY/QQQ extras feed the shock pass only
```

In V209-6b's `shock_state = _shock_state_for_pass(...)` call change
`live_prices=live_prices` to `live_prices=shock_prices`.

`tickers` itself is never modified; under `off` or an unstepped pass both
helpers hand back the very objects they were given, so the call and the dict
are what they were before v209.

- [ ] **Step 5: Run the tests to verify they pass**

Run each:
`python scripts/dev/testrun.py file tests/commands/test_shock_step_gate.py`
`python scripts/dev/testrun.py file tests/scanning/test_short_lane_split.py` (drives `_sync_run_scan` end to end)
`python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`
Expected: PASS, and 0 skipped in the last two.

Run: `python scripts/dev/complexity_gate.py`
Expected: no violation; `_sync_run_scan` still 94 (two assignments, no branch), `quote_tickers` and `scan_quotes` below 5.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/shock_scan.py swingbot/core/scanning/scan_run.py \
        tests/commands/test_shock_step_gate.py
git commit -m "feat(v209): SPY/QQQ ride the scan's one live-price fetch; the long lanes never see them"
```

### Task V209-7: Stamp `shock_state` on confluence, requote and strategy plans

**Model:** opus — threads one value through three plan-builder lanes and a requote rebuild where a single missed hop silently loses the label, under a byte-identical `off` contract.

**Files:**
- Modify: `swingbot/core/planning/params.py` (new `shock_asof`; `stamp_entry_context` calls new `_merge_shock_state` after the feature dict and after the failure fallback)
- Modify: `swingbot/core/scanning/analyze.py` (import `shock_asof`; `attach_plan_v2(..., shock_state=None)` adds `**shock_asof(shock_state)` to the asof dict)
- Modify: `swingbot/core/scanning/scan_run.py` (import `shock_asof`; `_attach_item_plan`, `_rebuild_item`, `_maybe_run_strategy_pass` + its `asof_of`; in `_sync_run_scan` the `_attach_item_plan(...)` call, the `functools.partial(_rebuild_item, ...)` and the `_maybe_run_strategy_pass(...)` call each gain `shock_state=shock_state`)
- Create: `tests/planning/test_stamp_entry_context_shock.py`
- Create: `tests/scanning/test_shock_state_stamp.py`

**Interfaces:**
- Consumes: the `_sync_run_scan` local `shock_state: str | None` (V209-6b), bound before the plan builders run.
- Produces:
  - `params.shock_asof(shock_state: str | None) -> dict` — `{}` for `None`, else `{"shock_state": shock_state}`.
  - `params.stamp_entry_context(plan, df, asof)` (signature unchanged) writes `plan.entry_context["shock_state"]` when `asof.get("shock_state") is not None`, after the feature dict and after the `entry_context = {}` fallback; never otherwise.
  - `analyze.attach_plan_v2(item, scenario, df, ticker, horizon_key, level_map=None, regime=None, rs_percentile=None, breadth=None, regime2_state=None, issued_at=None, now=None, shock_state: str | None = None)` — V209-8's SHORT lane passes `shock_state=context.shock_state`.
  - `scan_run._attach_item_plan(item, scenario, df, regimes, regime, shock_state=None)`; `scan_run._rebuild_item(item, price, *, fresh_data, regimes, regime, require_confirmation, shock_state=None)`; `scan_run._maybe_run_strategy_pass(*, ..., require_confirmation, shock_state: str | None = None)`, whose `asof_of(ticker)` returns the RS readings plus `shock_asof(shock_state)`.
- The strategy lane needs no `strategy_pass.py` edit: `build_strategy_plan_at` already merges `{**(asof or {}), "regime2_state": ...}` and hands it to `stamp_entry_context`.

- [ ] **Step 1: Write the failing stamp test**

Create `tests/planning/test_stamp_entry_context_shock.py`:

```python
"""v209: stamp_entry_context merges shock_state beside the feature dict.

Never a FEATURE_KEYS member; absent (not None) without a label, so
MARKET_SHOCK_MODE=off stays byte-identical; survives a feature-build failure."""
import pytest

from swingbot.core.edge import context as edge_context
from swingbot.core.edge.context import FEATURE_KEYS
from swingbot.core.planning import params
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from tests.helpers import make_ohlcv

ASOF = {"regime2_state": "bear_volatile", "rs_pctile": 40.0, "sector_pctile": None,
        "rs_combined": 40.0}


def _plan():
    return TradePlanV2(plan_id="p", ticker="AAPL", created_at="2026-11-05", source="confluence",
                       strategy="MACD", horizon_key="3m", direction="bullish", entry_type="market",
                       trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=98.5,
                       tp1=110.0, tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5,
                       trail_atr_mult=2.0, quality_score=0, quality_breakdown=[], badge="WEAK",
                       badge_stats={}, status=PlanStatus.PENDING)


def _stamped(asof):
    plan = _plan()
    frame = make_ohlcv([100.0 + i * 0.1 for i in range(300)], start="2025-06-02")
    params.stamp_entry_context(plan, frame, asof)
    return plan.entry_context


def test_shock_state_is_never_a_feature_key():
    assert "shock_state" not in FEATURE_KEYS


def test_the_asof_fragment_is_empty_without_a_label():
    assert params.shock_asof(None) == {}
    assert params.shock_asof("SHOCK") == {"shock_state": "SHOCK"}


@pytest.mark.parametrize("label", ["NORMAL", "SHOCK", "RECOVERY"])
def test_the_label_is_merged_after_the_feature_dict(label):
    base = _stamped(ASOF)
    shocked = _stamped({**ASOF, "shock_state": label})
    assert shocked.pop("shock_state") == label
    assert shocked == base
    assert set(base) == set(FEATURE_KEYS)


@pytest.mark.parametrize("asof", [ASOF, {**ASOF, "shock_state": None}, None, {}])
def test_no_label_leaves_the_key_absent(asof):
    assert "shock_state" not in _stamped(asof)


def test_the_label_survives_a_feature_build_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("bad frame")

    monkeypatch.setattr(edge_context, "entry_context", boom)
    assert _stamped({**ASOF, "shock_state": "SHOCK"}) == {"shock_state": "SHOCK"}
    assert _stamped(ASOF) == {}
```

(`stamp_entry_context` imports `entry_context` inside the function, so the
module-attribute patch reaches it.)

- [ ] **Step 2: Write the failing wiring test**

Create `tests/scanning/test_shock_state_stamp.py`:

```python
"""v209: the scan's shock label reaches every confluence, requote and strategy plan."""
import ast
import inspect
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning.rebuild import RebuildOutcome, RebuildPrice
from swingbot.core.scanning import analyze, scan_run, strategy_pass
from tests.helpers import make_ohlcv
from tests.scanning.test_live_context_stamp import _plan

PRICE = RebuildPrice(101.0, "trade", 1.0, "2026-11-05T15:00:00+00:00", 1000.0, True, "regular")
FRAME = make_ohlcv([100.0] * 300, start="2025-06-02")


def _attach_env(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *a, **k: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: _plan())
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")
    seen = []
    monkeypatch.setattr(analyze, "stamp_entry_context", lambda plan, df, asof: seen.append(asof))
    return seen


def _readings_item():
    return SimpleNamespace(rs_combined=61.0, sector_rs_percentile=55.0, conf=None, htf_bias=None,
                           target_confluence=None)


PRE_V209 = {"regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": 55.0,
            "rs_combined": 61.0}


def test_attach_plan_v2_adds_the_label_to_the_asof(monkeypatch):
    seen = _attach_env(monkeypatch)
    analyze.attach_plan_v2(_readings_item(), SimpleNamespace(direction="bullish", entry=100.0),
                           FRAME, "AAPL", "3m", rs_percentile=64.0, regime2_state="bull_quiet",
                           shock_state="SHOCK")
    assert seen == [{**PRE_V209, "shock_state": "SHOCK"}]


@pytest.mark.parametrize("kwargs", [{}, {"shock_state": None}])
def test_attach_plan_v2_without_a_label_hands_over_the_pre_v209_asof(monkeypatch, kwargs):
    seen = _attach_env(monkeypatch)
    analyze.attach_plan_v2(_readings_item(), SimpleNamespace(direction="bullish", entry=100.0),
                           FRAME, "AAPL", "3m", rs_percentile=64.0, regime2_state="bull_quiet",
                           **kwargs)
    assert seen == [PRE_V209]


def _capture_attach(monkeypatch):
    calls = []
    monkeypatch.setattr(analyze, "attach_plan_v2",
                        lambda *a, **k: calls.append(k.get("shock_state", "MISSING")))
    return calls


def _scan_item():
    return SimpleNamespace(
        result=SimpleNamespace(ticker="AAA", horizon_key="4w", trend="bullish",
                               state_key="k", state_value="v"),
        level_map=None, rs_percentile=None, breadth=None, htf_info=None,
        plan_v2=None, plan_v2_rejected=None, plan="scenario")


@pytest.mark.parametrize("label", [None, "SHOCK"])
def test_attach_item_plan_forwards_the_label(monkeypatch, label):
    calls = _capture_attach(monkeypatch)
    scan_run._attach_item_plan(_scan_item(), "scenario", None, None, None, shock_state=label)
    assert calls == [label]


def test_attach_item_plan_defaults_to_no_label(monkeypatch):
    calls = _capture_attach(monkeypatch)
    scan_run._attach_item_plan(_scan_item(), "scenario", None, None, None)
    assert calls == [None]


def test_the_requote_rebuild_attaches_with_the_label(monkeypatch):
    calls = _capture_attach(monkeypatch)

    def rebuild(item, price, *, rescenario, attach):
        attach("rebuilt")
        return RebuildOutcome(True, None, price)

    monkeypatch.setattr(scan_run.rebuild, "rebuild_before_post", rebuild)
    out = scan_run._rebuild_item(_scan_item(), PRICE, fresh_data={}, regimes=None, regime=None,
                                 require_confirmation=True, shock_state="RECOVERY")
    assert out.kept and calls == ["RECOVERY"]


@pytest.fixture
def strategy_env(monkeypatch):
    monkeypatch.setattr(config, "STRATEGY_ALERTS_MODE", "shadow")
    monkeypatch.setattr(scan_run, "PlanStore", lambda: None)
    monkeypatch.setattr(scan_run, "_compression_hooks", lambda *a: (None, None))
    monkeypatch.setattr(scan_run, "_compression_seen", lambda: set())
    monkeypatch.setattr(scan_run, "_record_compression_shadow", lambda result: None)
    seen = {}

    def fake_pass(tickers, fresh_data, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(alerts=[], plans=[], opened=0, compression_shadow=[],
                               compression_rejected=0, pullback_volume=0, headroom=0)

    monkeypatch.setattr(strategy_pass, "run_strategy_pass", fake_pass)
    return seen


def _strategy(**extra):
    return scan_run._maybe_run_strategy_pass(
        tickers=["AAA"], fresh_data={"AAA": None}, spy_df=None, regimes=None, rs_cache=None,
        sector_of_ticker={}, etf_symbol_of_sector={}, sector_etf_frames={}, trade_log=None,
        alerts=[], require_confirmation=True, **extra)


@pytest.mark.parametrize("label,expected", [(None, {}), ("SHOCK", {"shock_state": "SHOCK"})])
def test_the_strategy_asof_carries_the_label(strategy_env, label, expected):
    _strategy(shock_state=label)
    assert strategy_env["asof_of"]("AAA") == expected
    assert strategy_env["rs_combined_of"]("AAA") is None


def test_the_strategy_pass_defaults_to_no_label(strategy_env):
    _strategy()
    assert strategy_env["asof_of"]("AAA") == {}


def test_the_strategy_plan_stamp_receives_the_label(monkeypatch):
    calls = []
    monkeypatch.setattr(strategy_pass, "build_strategy_plan", lambda *a, **k: _plan())
    monkeypatch.setattr(strategy_pass, "stamp_badge", lambda plan: None)
    monkeypatch.setattr(strategy_pass, "stamp_cohort", lambda plan, state: None)
    monkeypatch.setattr(strategy_pass, "stamp_entry_context",
                        lambda plan, df, asof: calls.append(asof))
    strategy_pass.build_strategy_plan_at(FRAME, ticker="AAPL", strategy="MACD", horizon_key="3m",
                                         direction="bullish", regime2_state="bear_volatile",
                                         asof={"shock_state": "SHOCK"})
    assert calls == [{"shock_state": "SHOCK", "regime2_state": "bear_volatile"}]


def test_the_scan_threads_its_label_into_every_builder():
    tree = ast.parse(inspect.getsource(scan_run))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_sync_run_scan")
    wanted = {"_attach_item_plan", "_maybe_run_strategy_pass", "partial"}
    seen = []
    for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
        func = call.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in wanted:
            keywords = {k.arg: ast.unparse(k.value) for k in call.keywords}
            seen.append((name, keywords.get("shock_state")))
    assert {name for name, _ in seen} == wanted
    assert all(value == "shock_state" for _, value in seen), seen
```

- [ ] **Step 3: Run the tests to verify they fail**

Run each:
`python scripts/dev/testrun.py file tests/planning/test_stamp_entry_context_shock.py`
`python scripts/dev/testrun.py file tests/scanning/test_shock_state_stamp.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.planning.params' has no attribute 'shock_asof'`, `TypeError: attach_plan_v2() got an unexpected keyword argument 'shock_state'`, the AST test's missing keywords.

- [ ] **Step 4: Merge the label in `swingbot/core/planning/params.py`**

Replace `stamp_entry_context` with:

```python
def shock_asof(shock_state: str | None) -> dict:
    """v209: the asof fragment carrying the market-shock label. Empty for None,
    so an `off` pass hands stamp_entry_context exactly the pre-v209 dict."""
    return {} if shock_state is None else {"shock_state": shock_state}


def stamp_entry_context(plan: TradePlanV2, df, asof: dict | None) -> None:
    from swingbot.core.edge.context import entry_context
    try:
        plan.entry_context = entry_context(df, direction=plan.direction, horizon_key=plan.horizon_key,
                                            stop=plan.stop_loss, target=plan.tp1, asof=asof,
                                            entry=getattr(plan, "trigger_price", None))
    except Exception:
        plan.entry_context = {}
    _merge_shock_state(plan, asof)


def _merge_shock_state(plan: TradePlanV2, asof: dict | None) -> None:
    """v209: shock_state rides beside the feature dict (never in FEATURE_KEYS) and
    survives a feature-build failure; absent, not None, when the pass stamped none."""
    label = (asof or {}).get("shock_state")
    if label is not None:
        plan.entry_context = {**(plan.entry_context or {}), "shock_state": label}
```

Replay (`backtest_scenarios.asof_row`) never carries `shock_state`, so
replayed plans keep exactly `FEATURE_KEYS`.

- [ ] **Step 5: Pass the label through `swingbot/core/scanning/analyze.py`**

Change the import:

```python
from swingbot.core.planning.params import shock_asof, stamp_entry_context
```

Change the signature and add one docstring line:

```python
def attach_plan_v2(item, scenario, df, ticker, horizon_key, level_map=None,
                    regime=None, rs_percentile=None, breadth=None, regime2_state=None,
                    issued_at=None, now=None, shock_state=None):
```

```text
    `shock_state` (v209) is the scan's market-shock label; None (MARKET_SHOCK_MODE
    off) leaves entry_context without the key.
```

Change the stamp call:

```python
        stamp_entry_context(plan, df, {
            "regime2_state": regime2_state,
            "rs_pctile": rs_percentile,
            "sector_pctile": getattr(item, "sector_rs_percentile", None),
            "rs_combined": getattr(item, "rs_combined", None),
            **shock_asof(shock_state),
        })
```

No new branch: `attach_plan_v2` stays CC 12.

- [ ] **Step 6: Thread it through `swingbot/core/scanning/scan_run.py`**

6a. Import, below `from swingbot.core.planning.account import ...`:

```python
from swingbot.core.planning.params import shock_asof
```

6b. `_attach_item_plan` and `_rebuild_item`:

```python
def _attach_item_plan(item, scenario, df, regimes, regime, shock_state=None) -> None:
    """Attach the v2 plan for `scenario` at the frame's last bar's regime;
    shared by the merge loop and the v171 pre-post rebuild. `shock_state` is
    the scan's market-shock label (v209), None under MARKET_SHOCK_MODE=off."""
    regime2_state = analyze._regime_at(regimes, df.index[-1] if df is not None and len(df) > 0 else None)
    analyze.attach_plan_v2(item, scenario, df,
                           item.result.ticker, item.result.horizon_key,
                           level_map=item.level_map, regime=regime,
                           rs_percentile=item.rs_percentile, breadth=item.breadth,
                           regime2_state=regime2_state, shock_state=shock_state)
    if item.plan_v2 is not None:
        item.plan_v2.regime_aligned = not (
            item.htf_info and item.htf_info.get("counter_trend", False)
        )


def _rebuild_item(item, price, *, fresh_data, regimes, regime, require_confirmation,
                  shock_state=None):
    """v171 D5: rebuild `item` at `price` from the scan's own frame. A drop
    revokes the confirmation, so it consumes no cooldown and no dedup."""
    df = fresh_data.get(item.result.ticker)
    outcome = rebuild.rebuild_before_post(
        item, price,
        rescenario=lambda p: analyze.rescenario(item, df, p),
        attach=lambda s: _attach_item_plan(item, s, df, regimes, regime, shock_state))
```

(the rest of `_rebuild_item` is unchanged).

6c. `_maybe_run_strategy_pass` — add the keyword, split the RS closure from
the label so neither gains a branch:

```python
def _maybe_run_strategy_pass(*,tickers, fresh_data, spy_df, regimes, rs_cache, sector_of_ticker,
                             etf_symbol_of_sector, sector_etf_frames, trade_log, alerts,
                             require_confirmation, shock_state: str | None = None) -> dict:
```

Rename the existing inner `def asof_of(ticker):` to `def rs_asof(ticker):`
(body unchanged), then replace the old `rs_combined_of` with:

```python
    def asof_of(ticker):
        # v209: the scan's shock label rides on every strategy plan's asof.
        return {**rs_asof(ticker), **shock_asof(shock_state)}

    def rs_combined_of(ticker):
        return rs_asof(ticker).get("rs_combined")
```

`run_strategy_pass(..., asof_of=asof_of, ...)` stays as it is.

6d. In `_sync_run_scan`, add `shock_state=shock_state` to three calls:

```python
                _attach_item_plan(item, item.plan, fresh_data.get(item.result.ticker),
                                  regimes, regime, shock_state=shock_state)
```

```python
    for item in requote.iter_fresh(deduped, rebuild=functools.partial(
            _rebuild_item, fresh_data=fresh_data, regimes=regimes, regime=regime,
            require_confirmation=require_confirmation, shock_state=shock_state)):
```

```python
    strategy_counts = _maybe_run_strategy_pass(
        tickers=tickers, fresh_data=fresh_data, spy_df=spy_df, regimes=regimes,
        rs_cache=rs_cache, sector_of_ticker=sector_of_ticker,
        etf_symbol_of_sector=etf_symbol_of_sector, sector_etf_frames=sector_etf_frames,
        trade_log=trade_log, alerts=alerts, require_confirmation=require_confirmation,
        shock_state=shock_state)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run each:
`python scripts/dev/testrun.py file tests/planning/test_stamp_entry_context_shock.py`
`python scripts/dev/testrun.py file tests/scanning/test_shock_state_stamp.py`
`python scripts/dev/testrun.py file tests/scanning/test_live_context_stamp.py` (the pre-v209 four-key asof)
`python scripts/dev/testrun.py file tests/scanning/test_scan_rebuild_wiring.py`
`python scripts/dev/testrun.py file tests/scanning/test_headroom_live.py` (`_maybe_run_strategy_pass` by keyword)
`python scripts/dev/testrun.py file tests/scanning/test_pullback_dryup_live.py`
`python scripts/dev/testrun.py file tests/backtesting/test_backtest_context.py` (`set(context) == set(FEATURE_KEYS)` for replay)
`python scripts/dev/testrun.py file tests/backtesting/test_replay_context.py`
`python scripts/dev/testrun.py file tests/edge/test_edge_context_location.py`
Expected: PASS.

Run: `python scripts/dev/complexity_gate.py`
Expected: no violation; `_sync_run_scan` 94, `attach_plan_v2` 12, `_maybe_run_strategy_pass` unchanged.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/planning/params.py swingbot/core/scanning/analyze.py \
        swingbot/core/scanning/scan_run.py tests/planning/test_stamp_entry_context_shock.py \
        tests/scanning/test_shock_state_stamp.py
git commit -m "feat(v209): stamp entry_context.shock_state on confluence, requote and strategy plans"
```


### Task V209-8: SHORT lane reads the label via the lane dict

**Model:** opus — a short-side change under the byte-identical rule: the label must reach the SHORT build and its requote rebuild through exactly one store read per run.

**Files:**
- Modify: `swingbot/core/scanning/qualify.py` (`QualifyContext.shock_state` as the last field; `_attach_plan` forwards it)
- Modify: `swingbot/core/scanning/short_run.py` (import `shock_scan`; `_lane_state`, `_qualify_context`, `_bare_context`)
- Create: `tests/scanning/test_shock_short_lane.py`

**Interfaces:**
- Consumes: `shock_scan.current_label(*, repo=None) -> str | None` (V209-6a; never raises, `None` under `off` or when the store is unreadable, `"NORMAL"` before the first reading); `analyze.attach_plan_v2(..., shock_state: str | None = None)`, `scan_run._attach_item_plan(..., shock_state=None)`, `scan_run._rebuild_item(..., shock_state=None)`, `params.shock_asof(shock_state) -> dict` and the `stamp_entry_context` merge (V209-7).
- Produces:
  - `qualify.QualifyContext.shock_state: str | None = None` — the **last** field, so every construction in `scan_replay.py:207`, `outlook_run.py:146` and the existing tests is unchanged and carries `None` (replayed plans keep exactly `FEATURE_KEYS`).
  - `qualify._attach_plan(item, context)` passes `shock_state=context.shock_state` to `analyze.attach_plan_v2`; no new branch.
  - `short_run._lane_state(reference, snapshot, regime) -> dict` gains `"shock_state": shock_scan.current_label()` — the only `current_label()` call in `short_run.py`, so one store read per SHORT run (the `reference is None` early return reads nothing).
  - `short_run._qualify_context(require_confirmation, frames, lane)` passes `shock_state=lane.get("shock_state")` (a lane dict without the key, as in older tests, gives `None`).
  - `short_run._bare_context(frames, shock_state=None) -> qualify.QualifyContext`.
- The SHORT requote rebuild needs no edit: `_build_alerts(..., qualify_context=_qualify_context(...))` hands the same context to `_rebuild_fn`, whose `_attach_for` calls `qualify._attach_plan(item, context)`.
- `qualify.py` imports nothing new: planning never reads the shock repository.
- The byte-identical long/short pins are V209-8b (split at the 20 KB cap); they consume this task's `_context(shock_state=...)` field and lane-dict key.

- [ ] **Step 1: Write the failing SHORT-lane wiring test**

Create `tests/scanning/test_shock_short_lane.py`:

```python
"""v209: the SHORT lane reads the stored shock label once per run, at its own
entry point (`_lane_state`), and hands it to every SHORT build and rebuild
through QualifyContext. Planning (qualify.py) never reads the repository."""
import ast
import dataclasses
import inspect
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning.rebuild import RebuildOutcome, RebuildPrice
from swingbot.core.scanning import analyze, qualify, scan_replay, shock_scan, short_run

PRICE = RebuildPrice(101.0, "trade", 1.0, "2026-11-05T15:00:00+00:00", 1000.0, True, "regular")
LANE = {"sector_of": {}, "etf_symbol_of": {}, "sector_frames": {}, "spy": None,
        "regime": None, "regimes": None}


def _item():
    return SimpleNamespace(result=SimpleNamespace(ticker="AAA", horizon_key="4w", trend="bearish",
                                                  state_key="k", state_value="v"),
                           plan="scenario", level_map=None, rs_percentile=None, htf_info=None,
                           plan_v2=None, plan_v2_rejected=None)


def _capture_attach(monkeypatch):
    calls = []
    monkeypatch.setattr(analyze, "attach_plan_v2",
                        lambda *a, **k: calls.append(k.get("shock_state", "MISSING")))
    return calls


def _lane_inputs(monkeypatch):
    monkeypatch.setattr(short_run.regime2, "regime_series", lambda spy: "series")
    monkeypatch.setattr(short_run.fetch, "_etf_symbol_of_sector", lambda: {"Tech": "XLK"})
    reference = SimpleNamespace(spy="spy", sector_frames={"XLK": "frame"})
    snapshot = SimpleNamespace(sector_of={"AAA": "Tech"})
    return reference, snapshot


def test_the_label_is_the_last_context_field_and_defaults_to_none():
    fields = dataclasses.fields(qualify.QualifyContext)
    assert fields[-1].name == "shock_state" and fields[-1].default is None
    ctx = qualify.QualifyContext(frames={}, spy=None, sector_of={}, etf_symbol_of={},
                                 sector_frames={}, regime=None, regimes=None)
    assert ctx.shock_state is None


@pytest.mark.parametrize("label", [None, "SHOCK", "RECOVERY"])
def test_the_short_attach_forwards_the_context_label(monkeypatch, label):
    calls = _capture_attach(monkeypatch)
    qualify._attach_plan(_item(), short_run._bare_context({}, shock_state=label))
    assert calls == [label]


def test_the_bare_context_defaults_to_no_label():
    assert short_run._bare_context({}).shock_state is None


def test_the_lane_state_reads_the_stored_label_once(monkeypatch):
    reads = []
    monkeypatch.setattr(shock_scan, "current_label", lambda **k: reads.append(k) or "SHOCK")
    lane = short_run._lane_state(*_lane_inputs(monkeypatch), "regime")
    assert reads == [{}]
    assert lane == {"sector_of": {"AAA": "Tech"}, "etf_symbol_of": {"Tech": "XLK"},
                    "sector_frames": {"XLK": "frame"}, "spy": "spy", "regime": "regime",
                    "regimes": "series", "shock_state": "SHOCK"}


def test_under_off_the_lane_carries_no_label(monkeypatch):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "off")
    lane = short_run._lane_state(*_lane_inputs(monkeypatch), None)
    assert lane["shock_state"] is None
    assert short_run._qualify_context(False, {}, lane).shock_state is None


@pytest.mark.parametrize("lane,expected", [({**LANE, "shock_state": "RECOVERY"}, "RECOVERY"),
                                           ({**LANE, "shock_state": None}, None),
                                           (LANE, None)])
def test_the_qualify_context_takes_the_label_from_the_lane(lane, expected):
    assert short_run._qualify_context(False, {}, lane).shock_state == expected


def test_the_short_requote_rebuild_keeps_the_label(monkeypatch):
    calls = _capture_attach(monkeypatch)

    def rebuild(item, price, *, rescenario, attach):
        attach("rebuilt")
        return RebuildOutcome(True, None, price)

    monkeypatch.setattr(short_run.rebuild, "rebuild_before_post", rebuild)
    item = _item()
    out = short_run._rebuild_fn({}, short_run._bare_context({}, shock_state="SHOCK"))(item, PRICE)
    assert out.kept and item.plan == "rebuilt" and calls == ["SHOCK"]


def _functions(module):
    tree = ast.parse(inspect.getsource(module))
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _calls(node, name):
    return [c for c in ast.walk(node) if isinstance(c, ast.Call)
            and name in (getattr(c.func, "attr", None), getattr(c.func, "id", None))]


def test_the_label_is_read_once_per_short_run_and_only_at_the_lane_entry():
    fns = _functions(short_run)
    readers = [name for name, fn in fns.items() if _calls(fn, "current_label")]
    assert readers == ["_lane_state"]
    assert len(_calls(fns["_lane_state"], "current_label")) == 1
    assert len(_calls(fns["_sync_run_short_scan"], "_lane_state")) == 1


def test_planning_never_reads_the_shock_store():
    source = inspect.getsource(qualify)
    assert "shock_scan" not in source and "market_shock" not in source


def test_replay_contexts_never_carry_a_label():
    for call in _calls(ast.parse(inspect.getsource(scan_replay)), "QualifyContext"):
        assert "shock_state" not in {k.arg for k in call.keywords}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_shock_short_lane.py`
Expected: FAIL — `TypeError: _bare_context() got an unexpected keyword argument 'shock_state'`, `TypeError: QualifyContext.__init__() got an unexpected keyword argument 'shock_state'`, the field-order and AST tests.

- [ ] **Step 3: Add the field and forward it in `swingbot/core/scanning/qualify.py`**

Append the field after `now: object = None` (it must stay last):

```python
    now: object = None
    shock_state: str | None = None         # v209: the run's stored shock label; None = no key
```

In `_attach_plan`, add one keyword to the existing call:

```python
    analyze.attach_plan_v2(
        item, item.plan, frame, item.result.ticker, item.result.horizon_key,
        level_map=item.level_map, regime=context.regime, rs_percentile=item.rs_percentile,
        breadth=context.breadth, regime2_state=analyze._regime_at(context.regimes, when),
        issued_at=context.issued_at, now=context.now, shock_state=context.shock_state)
```

Add one sentence to the module docstring's purity paragraph: `The v209
shock label arrives in the context too; this module never reads the shock
store.` (no `shock_scan` or `market_shock` anywhere in `qualify.py`: Step 1
pins that).

- [ ] **Step 4: Read the label once in `swingbot/core/scanning/short_run.py`**

5a. Add `shock_scan` to the existing relative import, keeping it sorted:

```python
from . import (analyze, dedup, fetch, lane_overlap, qualify, rejection_recorder, runstate, scan_run,
               shock_scan, short_funnel, telemetry)
```

5b. `_lane_state` — one new dict entry, plus a docstring:

```python
def _lane_state(reference, snapshot, regime) -> dict:
    """The lane's run-wide inputs. v209: the stored market-shock label is read
    here, once per SHORT run, never inside planning (None under off or when the
    store is unreadable: those plans carry no shock_state key)."""
    regimes = None
    try:
        regimes = regime2.regime_series(reference.spy)
    except Exception as exc:
        swallowed(log, "scan.short_run.lane_state", exc, "regime_series computation failed",
                  level=logging.DEBUG, exc_info=True)
    return {"sector_of": snapshot.sector_of, "etf_symbol_of": fetch._etf_symbol_of_sector(),
            "sector_frames": dict(reference.sector_frames), "spy": reference.spy,
            "regime": regime, "regimes": regimes, "shock_state": shock_scan.current_label()}
```

5c. `_qualify_context` — one keyword:

```python
    return qualify.QualifyContext(
        frames=frames, spy=lane["spy"], sector_of=lane["sector_of"],
        etf_symbol_of=lane["etf_symbol_of"], sector_frames=lane["sector_frames"],
        regime=lane["regime"], regimes=lane["regimes"],
        confirmations=state if require_confirmation else None,
        required_confirmations=config.SIGNAL_CONFIRMATION_SCANS,
        shock_state=lane.get("shock_state"))
```

5d. `_bare_context`:

```python
def _bare_context(frames, shock_state=None) -> qualify.QualifyContext:
    """A context with no lane state, for callers that pass none (tests)."""
    return qualify.QualifyContext(frames=frames, spy=None, sector_of={}, etf_symbol_of={},
                                  sector_frames={}, regime=None, regimes=None,
                                  shock_state=shock_state)
```

`_sync_run_short_scan` is not edited: its `lane = {**_lane_state(...), "funnel": funnel}`
already carries the key into both `_qualify_context` calls, and the second
one feeds `_build_alerts`' rebuild.

- [ ] **Step 5: Run the tests to verify they pass**

The end-to-end SHORT drivers below now reach `current_label()`; under the
default `shadow` mode it reads the test database (it never raises, but a
dead store silently gives `None`), so run `/replicate-prod-db` first unless
a sibling task already did this session.

Run each:
`python scripts/dev/testrun.py file tests/scanning/test_shock_short_lane.py`
`python scripts/dev/testrun.py file tests/scanning/test_short_qualify.py` (golden SHORT prices)
`python scripts/dev/testrun.py file tests/scanning/test_short_lane_rebuild.py`
`python scripts/dev/testrun.py file tests/scanning/test_short_lane_scan.py` (its stubbed `_lane_state` has no `shock_state` key: `lane.get` gives `None`)
`python scripts/dev/testrun.py file tests/scanning/test_short_alert_parity.py`
`python scripts/dev/testrun.py file tests/scanning/test_short_funnel.py`
`python scripts/dev/testrun.py file tests/scanning/test_short_lane_admission.py`
`python scripts/dev/testrun.py file tests/commands/test_send_alerts_cooldown.py`
Expected: PASS, `0 failed`, `0 xfailed`. A pre-existing SHORT test that
fails here means a plan changed: stop and report, never update a golden.

Run: `python scripts/dev/complexity_gate.py`
Expected: no violation; `_attach_plan`, `_lane_state`, `_qualify_context` and `_bare_context` gain no branch.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/qualify.py swingbot/core/scanning/short_run.py \
        tests/scanning/test_shock_short_lane.py
git commit -m "feat(v209): SHORT lane stamps the stored shock label read once per run"
```
