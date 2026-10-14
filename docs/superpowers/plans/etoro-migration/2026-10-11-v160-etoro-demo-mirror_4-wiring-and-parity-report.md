# v160 eToro demo mirror: plan events become demo-account trades. Part 4: wiring and the parity report (EM10–EM12)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task EM10" -A 500 <this file>`.

**Spec:** `docs/superpowers/specs/etoro-migration/2026-10-11-v160-etoro-demo-mirror-design.md` (§ Components, § Hook, § Disable, drain and rollback, § Comparison report, § Testing)
**Index:** `docs/superpowers/plans/etoro-migration/2026-10-11-v160-etoro-demo-mirror_0-index.md`. Its `## Global Constraints`, `## Parallelisation` and `## Task ledger` apply to every task below and win over anything here.

**Conventions for every task in this part**

- `WT` is the worktree root: `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v160-etoro-demo-mirror` (created in EM1). Every path below is relative to `WT`. Never `cd`: use `git -C "$WT" ...`, and run tests as `python "$WT/scripts/dev/testrun.py" file <test path relative to WT>`.
- `swingbot/core/broker/__init__.py`, `guard.py` and `tests/broker/__init__.py` exist already (v159 ER7). EM10 replaces the body of `__init__.py`; no task creates it.
- v159's AST scan (`tests/broker/test_guard.py::unguarded_etoro_modules`) flags any module under `swingbot/`, `scripts/`, `bot.py`, `admin_ui.py` that imports a module whose dotted name contains `etoro`, holds a string containing `etoro.com`, or names `ETORO_USER_KEY`/`ETORO_API_KEY`, without calling `assert_demo`. Nothing in this part does any of those: `broker/__init__.py` imports `executor` (not `etoro_client`), `loops.py` imports `swingbot.core.broker`, and the parity report imports only the repository and the plan store. A file name containing `etoro` is not an import. Keep it that way.
- Every new or changed function stays below cyclomatic complexity 15: `python -m radon cc -s -n C <files>` prints nothing new.

## Part-local constraints

- **The report reads only persisted fields** (spec § Comparison report, "never re-reads mutable live routes"). Its row contract, from the index ledger (EM2, EM8, EM9): open row `units_filled`, `avg_price`, `stop_sent`, `quote_at_send`, `filled_at`, `direction`, `ticker`, `settlement_type`; close row `action`, `status`, `seq`, `units_requested`, `fraction_closed`, and the close economics EM9 persists (`close_rate`, `closed_at`, `net_profit`, `fees`, `overnight_fees`); skipped row `skip_reason`.
- **A close leg's exit price is `close_rate` only.** A close row's `avg_price` is never used as an exit price: EM8 fills it from the lookup's `openingData`, which describes the position's opening, not the close. A leg without `close_rate` makes that trade's gross R `None` (counted in `n_gross`, never guessed). Net R needs only the rows that carry `net_profit`. Likewise a partial close's units are `units_requested` (what EM8 asked eToro to close), never the lookup's `units_filled`, for the same `openingData` reason.
- **A trade enters the report only when its eToro position is closed**: the plan has an `open` row `filled`, and either a `close_all` row `filled` or any row `closed_by_broker`. Plans still open at eToro, and plans missing from the store, are left out of the per-trade table; their skipped rows still count in the skip totals.
- **Every mean ignores `None`** and the pooled block prints how many values each mean used (`n_paper`, `n_gross`, `n_net`), so a thin column is visible rather than hidden.
- **The parity report never calls eToro** and needs no keys; it runs on production with `docker compose exec -T bot python scripts/reports/etoro_parity_report.py`.

# Phase 5 — wiring and docs (EM10)

### Task EM10: Wiring: `mirror_events`, the `trade_monitor` hook, import direction, docs

**Model:** opus — it puts an external order path on the live trade-monitor loop; a misplaced await (inside `if plan_events:`) silently stops lookups and reconciliation on quiet ticks, and a swallowed `CancelledError` or a blocking call would stall the paper side.

Spec § Components (`__init__.py`: `mirror_events`, `MIRROR_TICK_BUDGET_S = 25`), § Hook (after `_post_plan_events`, every tick including empty ones, one WARNING on failure), § Disable, drain and rollback (the flag makes `mirror_events` a no-op), § Testing (`test_import_direction.py`, scoped to `swingbot/`). Index § Global Constraints (import direction; `trade_monitor` gains one plain line; settings read at call time).

The hook goes into a helper, `_mirror_plan_events`, so `trade_monitor` (radon C 13 today) gains one `await` statement and no branch. It sits **after** the `if plan_events:` block, not inside it: `poll()` returns `[]` in quiet hours, and those ticks must still advance in-flight lookups and the daily reconciliation. The helper checks the flag itself, so a disabled mirror costs no thread hop; `mirror_events` checks it again, because the drain and any future caller go through it.

`asyncio.wait_for(asyncio.to_thread(...))` bounds how long the loop waits, not how long the thread runs: a thread that outlives its 25 s keeps going, and the executor's non-blocking tick lock (EM8) makes the next tick return at once until it finishes. `asyncio.TimeoutError` is an `Exception` on 3.11, so a blown budget lands in the one WARNING; `CancelledError` is not, so loop shutdown still cancels cleanly.

**Files:**
- Modify (v159 ER7): `swingbot/core/broker/__init__.py`
- Modify: `swingbot/commands/scanning/loops.py` (new helper next to `_retry_notifications`, ~:543; one line in `trade_monitor` after the `if plan_events:` block, ~:668-669)
- Create: `tests/broker/test_mirror_events.py`
- Create: `tests/broker/test_import_direction.py`
- Create: `tests/commands/test_loops_etoro_mirror.py`
- Modify: `docs/claude/architecture.md` (the `core/broker/` paragraph v159 ER7 added to § Module map)
- Modify: `docs/claude/etoro-roadmap.md`

**Interfaces:**
- Consumes:
  - `swingbot.core.broker.executor` (EM8, EM9): `get_executor() -> Executor`; `Executor.run_tick(events: list) -> None` (takes the tick lock, enqueues, advances under `SEND_BUDGET_S = 20.0`, runs `maybe_reconcile`); `SEND_BUDGET_S`.
  - `config.ETORO_MIRROR_ENABLED: bool` (EM1), read at call time.
  - `loops.py` names that exist today: `asyncio`, `config`, `log`, `_post_plan_events` (`loops.py:528`), `_retry_notifications` (`loops.py:543`), `trade_monitor` (`@tasks.loop(seconds=60)`, `loops.py:590-591`; the raw coroutine is `trade_monitor.coro`).
- Produces:
  - `swingbot.core.broker.MIRROR_TICK_BUDGET_S = 25`
  - `swingbot.core.broker.mirror_events(events) -> None`: no-op unless `config.ETORO_MIRROR_ENABLED`; else `executor.get_executor().run_tick(list(events or []))`. The executor is imported inside the function.
  - `swingbot.commands.scanning.loops._mirror_plan_events(plan_events) -> None` (async): returns at once when the flag is off; else `await asyncio.wait_for(asyncio.to_thread(broker.mirror_events, plan_events), timeout=broker.MIRROR_TICK_BUDGET_S)`; any `Exception` → one WARNING starting `trade_monitor: eToro mirror failed`.
  - `trade_monitor` awaits `_mirror_plan_events(plan_events)` as the statement right after the `if plan_events:` block, on every tick.

- [ ] **Step 1: Confirm the consumed contracts are on the branch**

```bash
git -C "$WT" grep -n "def get_executor\|def run_tick\|def maybe_reconcile\|^SEND_BUDGET_S" -- swingbot/core/broker/executor.py
git -C "$WT" grep -n "ETORO_MIRROR_ENABLED" -- swingbot/config.py
git -C "$WT" grep -n "async def _post_plan_events\|async def _retry_notifications\|async def trade_monitor\|await _post_plan_events(plan_events)" -- swingbot/commands/scanning/loops.py
git -C "$WT" grep -n "v160 adds\|core/broker/" -- docs/claude/architecture.md
python -m radon cc -s "$WT/swingbot/commands/scanning/loops.py" | grep "trade_monitor"
```

Expected: four hits in `executor.py` (EM8 `get_executor`, `run_tick`, `SEND_BUDGET_S`; EM9 `maybe_reconcile`), one in `config.py`, four in `loops.py`, at least one in `architecture.md` (v159 ER7's paragraph), and `F ...:0 trade_monitor - C (13)`. A missing executor hit: `BLOCKED: EM10 needs EM8/EM9`. No `core/broker/` paragraph in `architecture.md`: `BLOCKED: v159 ER7 docs not on the branch`. A `trade_monitor` grade other than C (13): write down the number you see and use it in Step 7's expectation instead.

- [ ] **Step 2: Write the failing tests**

Create `tests/broker/test_mirror_events.py`:

```python
"""v160: broker.mirror_events is the trade monitor's single entry point.

It is a no-op while ETORO_MIRROR_ENABLED is off (read per call, so a SIGHUP
reload takes effect on the next tick) and otherwise runs exactly one executor
tick with a list -- also an empty one, so lookups and reconciliation advance.
"""
from swingbot import config
from swingbot.core import broker
from swingbot.core.broker import executor


class _Executor:
    def __init__(self):
        self.ticks = []

    def run_tick(self, events):
        self.ticks.append(events)


def _wire(monkeypatch, enabled):
    monkeypatch.setattr(config, "ETORO_MIRROR_ENABLED", enabled, raising=False)
    fake, built = _Executor(), []

    def get_executor():
        built.append(True)
        return fake

    monkeypatch.setattr(executor, "get_executor", get_executor)
    return fake, built


def test_disabled_is_a_no_op_that_never_builds_the_executor(monkeypatch):
    fake, built = _wire(monkeypatch, False)
    broker.mirror_events(["event"])
    assert fake.ticks == [] and built == []


def test_enabled_runs_one_tick_with_a_list(monkeypatch):
    fake, _ = _wire(monkeypatch, True)
    broker.mirror_events(("e1", "e2"))
    assert fake.ticks == [["e1", "e2"]]


def test_an_empty_tick_still_runs(monkeypatch):
    fake, _ = _wire(monkeypatch, True)
    broker.mirror_events([])
    broker.mirror_events(None)
    assert fake.ticks == [[], []]


def test_the_flag_is_read_on_every_call(monkeypatch):
    fake, _ = _wire(monkeypatch, True)
    broker.mirror_events(["e1"])
    monkeypatch.setattr(config, "ETORO_MIRROR_ENABLED", False)
    broker.mirror_events(["e2"])
    assert fake.ticks == [["e1"]]


def test_the_send_budget_fits_inside_the_tick_budget():
    assert broker.MIRROR_TICK_BUDGET_S == 25
    assert executor.SEND_BUDGET_S < broker.MIRROR_TICK_BUDGET_S
```

Create `tests/broker/test_import_direction.py`:

```python
"""v160: who may import swingbot.core.broker, and what broker/ may import.

Inside swingbot/, only swingbot/core/broker/** and
swingbot/commands/scanning/loops.py import the broker package, and loops.py
does it lazily, inside a function. broker/ itself reaches only planning/,
edge/, db/, market/, marketdata/, core.risk_limits and config. Scripts are
out of scope on purpose: the drain, smoke and parity scripts import it.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SWINGBOT = ROOT / "swingbot"
BROKER_DIR = SWINGBOT / "core" / "broker"
LOOPS = SWINGBOT / "commands" / "scanning" / "loops.py"
BROKER = "swingbot.core.broker"
ALLOWED_IMPORTERS = {"swingbot/commands/scanning/loops.py"}
BROKER_MAY_REACH = (
    BROKER,
    "swingbot.core.planning",
    "swingbot.core.edge",
    "swingbot.core.db",
    "swingbot.core.market",
    "swingbot.core.marketdata",
    "swingbot.core.risk_limits",
    "swingbot.config",
)
# Package names a `from swingbot[.core] import x` statement binds on the way.
_PARENTS = {"swingbot", "swingbot.core"}


def imported_names(text: str) -> set:
    """Every dotted module name an import statement can bind, including
    ``from pkg import mod`` as ``pkg.mod``."""
    names = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _under(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def _reaches_broker(names) -> bool:
    return any(_under(name, BROKER) for name in names)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_the_guard_sees_both_import_forms():
    assert _reaches_broker(imported_names("from swingbot.core import broker"))
    assert _reaches_broker(imported_names("import swingbot.core.broker.executor"))
    assert not _reaches_broker(imported_names("from swingbot.core import planning"))


def test_only_loops_imports_the_broker_from_inside_swingbot():
    offenders = [
        _rel(path) for path in sorted(SWINGBOT.rglob("*.py"))
        if BROKER_DIR not in path.parents
        and _rel(path) not in ALLOWED_IMPORTERS
        and _reaches_broker(imported_names(path.read_text(encoding="utf-8")))
    ]
    assert offenders == []


def test_loops_imports_the_broker_lazily():
    tree = ast.parse(LOOPS.read_text(encoding="utf-8"))
    top_level = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            top_level |= imported_names(ast.unparse(node))
    assert not _reaches_broker(top_level)
    assert _reaches_broker(imported_names(LOOPS.read_text(encoding="utf-8")))


def _outside_allowed(names) -> list:
    return sorted(
        name for name in names
        if _under(name, "swingbot") and name not in _PARENTS
        and not any(_under(name, prefix) for prefix in BROKER_MAY_REACH)
    )


def test_the_outbound_check_flags_a_forbidden_package():
    assert _outside_allowed(imported_names("from swingbot.core import scanning")) == [
        "swingbot.core.scanning"]
    assert _outside_allowed(imported_names("from swingbot import config")) == []


def test_broker_reaches_only_its_allowed_packages():
    offenders = {
        _rel(path): _outside_allowed(imported_names(path.read_text(encoding="utf-8")))
        for path in sorted(BROKER_DIR.glob("*.py"))
    }
    assert {path: names for path, names in offenders.items() if names} == {}
```

Create `tests/commands/test_loops_etoro_mirror.py`:

```python
"""v160: the trade monitor mirrors plan events to the eToro demo account.

The hook runs after the Discord feed, on every tick (also when the plan
manager returned nothing), never waits longer than MIRROR_TICK_BUDGET_S, and
turns any failure into one WARNING. With the flag off it never calls the
broker package.
"""
import ast
import asyncio
import inspect
import logging
import textwrap
import time

from swingbot import config
from swingbot.commands.scanning import loops
from swingbot.core import broker


def _spy(monkeypatch, enabled=True):
    monkeypatch.setattr(config, "ETORO_MIRROR_ENABLED", enabled, raising=False)
    calls = []
    monkeypatch.setattr(broker, "mirror_events", lambda events: calls.append(events))
    return calls


def _warnings(caplog) -> list:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


def test_flag_off_never_reaches_the_broker(monkeypatch):
    calls = _spy(monkeypatch, enabled=False)
    asyncio.run(loops._mirror_plan_events(["event"]))
    assert calls == []


def test_flag_on_hands_the_events_to_the_broker(monkeypatch):
    calls = _spy(monkeypatch)
    asyncio.run(loops._mirror_plan_events(["e1", "e2"]))
    assert calls == [["e1", "e2"]]


def test_an_empty_tick_still_reaches_the_broker(monkeypatch):
    calls = _spy(monkeypatch)
    asyncio.run(loops._mirror_plan_events([]))
    assert calls == [[]]


def test_a_broker_failure_is_one_warning(monkeypatch, caplog):
    monkeypatch.setattr(config, "ETORO_MIRROR_ENABLED", True, raising=False)

    def boom(events):
        raise RuntimeError("eToro down")

    monkeypatch.setattr(broker, "mirror_events", boom)
    with caplog.at_level(logging.WARNING):
        asyncio.run(loops._mirror_plan_events(["event"]))
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert warnings[0].startswith("trade_monitor: eToro mirror failed")


def test_a_blown_budget_is_a_warning_not_a_stall(monkeypatch, caplog):
    monkeypatch.setattr(config, "ETORO_MIRROR_ENABLED", True, raising=False)
    monkeypatch.setattr(broker, "MIRROR_TICK_BUDGET_S", 0.05)
    monkeypatch.setattr(broker, "mirror_events", lambda events: time.sleep(0.5))

    async def timed() -> float:
        started = time.monotonic()
        await loops._mirror_plan_events([])
        return time.monotonic() - started

    # asyncio.run joins the worker thread on exit; only the awaited time matters.
    with caplog.at_level(logging.WARNING):
        elapsed = asyncio.run(timed())
    assert elapsed < 0.4
    assert len(_warnings(caplog)) == 1


def _awaited_call(stmt):
    """(name, [args]) of a bare `await name(...)` statement, else None."""
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Await):
        call = stmt.value.value
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
            return call.func.id, [ast.unparse(arg) for arg in call.args]
    return None


def test_trade_monitor_mirrors_every_tick_right_after_posting():
    source = textwrap.dedent(inspect.getsource(loops.trade_monitor.coro))
    body = ast.parse(source).body[0].body
    post_block = next(
        index for index, stmt in enumerate(body)
        if isinstance(stmt, ast.If) and "_post_plan_events" in ast.unparse(stmt))
    # Top level of the function, not inside `if plan_events:`.
    assert _awaited_call(body[post_block + 1]) == ("_mirror_plan_events", ["plan_events"])
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_mirror_events.py`
Expected: FAIL, `AttributeError: module 'swingbot.core.broker' has no attribute 'mirror_events'` (or `MIRROR_TICK_BUDGET_S`).

Run: `python "$WT/scripts/dev/testrun.py" file tests/commands/test_loops_etoro_mirror.py`
Expected: FAIL with `AttributeError`: `monkeypatch.setattr(broker, "mirror_events", ...)` finds no such attribute, and `loops` has no `_mirror_plan_events`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_import_direction.py`
Expected: FAIL in `test_loops_imports_the_broker_lazily` only (`loops.py` does not import the broker yet, so its second assert fails); the other four pass. If `test_broker_reaches_only_its_allowed_packages` fails, an earlier task imported a package outside the index's import-direction list: stop with `BLOCKED: EM10 -- <module> imports <name>`, never widen `BROKER_MAY_REACH`.

- [ ] **Step 4: Implement `mirror_events`**

Replace the whole of `swingbot/core/broker/__init__.py` (v159 ER7 left a docstring only) with:

```python
"""Broker integration: the account guard (v159) and the eToro demo mirror (v160).

`guard.assert_demo` keeps every eToro call on the demo account. The mirror's
single entry point is `mirror_events`: `commands/scanning/loops.py` calls it
from the trade monitor, after the Discord feed has been posted, inside
``asyncio.wait_for(..., MIRROR_TICK_BUDGET_S)``. It is a no-op while
ETORO_MIRROR_ENABLED is off (read per call, hot-reloaded). The executor is
imported inside the function, so importing this package builds no client.
"""
from __future__ import annotations

from swingbot import config

MIRROR_TICK_BUDGET_S = 25


def mirror_events(events) -> None:
    """Mirror one trade-monitor tick's plan events onto the eToro demo account.

    Runs on every tick, also with no events, so in-flight lookups and the
    daily reconciliation advance. The executor stops starting requests once
    its own 20 s send budget is spent; whatever is left stays queued."""
    if not config.ETORO_MIRROR_ENABLED:
        return
    from swingbot.core.broker import executor
    executor.get_executor().run_tick(list(events or []))
```

- [ ] **Step 5: Implement the hook**

In `swingbot/commands/scanning/loops.py`, insert directly after `_retry_notifications` (before `async def _resend_plan_notices`):

```python
async def _mirror_plan_events(plan_events) -> None:
    """v160: mirror this tick's plan events onto the eToro demo account.

    Awaited after _post_plan_events, so Discord delivery never waits on
    eToro, and on every tick (also with no events), so in-flight lookups and
    the daily reconciliation advance. A no-op while ETORO_MIRROR_ENABLED is
    off. A failure or a blown MIRROR_TICK_BUDGET_S is one WARNING: the paper
    ledger never depends on eToro."""
    if not config.ETORO_MIRROR_ENABLED:
        return
    from swingbot.core import broker
    try:
        await asyncio.wait_for(asyncio.to_thread(broker.mirror_events, plan_events),
                               timeout=broker.MIRROR_TICK_BUDGET_S)
    except Exception as exc:
        log.warning("trade_monitor: eToro mirror failed: %s", exc, exc_info=True)
```

In `trade_monitor`, change

```python
    if plan_events:
        await _post_plan_events(plan_events)
    await _retry_notifications()
```

to

```python
    if plan_events:
        await _post_plan_events(plan_events)
    await _mirror_plan_events(plan_events)
    await _retry_notifications()
```

`plan_events` is always bound at that point (`[]` when the manager tick raised). Nothing else in `trade_monitor` changes.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_mirror_events.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_import_direction.py`
Expected: PASS.

Run: `python "$WT/scripts/dev/testrun.py" file tests/commands/test_loops_etoro_mirror.py`
Expected: PASS.

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py`
Expected: PASS (`unguarded_etoro_modules(ROOT) == []`: neither `__init__.py` nor `loops.py` touches eToro in the scan's sense; the broker-package allow-list test still passes, no module added).

Run: `python "$WT/scripts/dev/testrun.py" file tests/commands/test_loops_notices.py`
Expected: PASS (the neighbouring loop tests are unaffected).

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s "$WT/swingbot/commands/scanning/loops.py" | grep -E "trade_monitor|_mirror_plan_events"`
Expected: `trade_monitor - C (13)` (unchanged: one statement, no branch) and `_mirror_plan_events - A (3)`.

Run: `python -m radon cc -s -n C "$WT/swingbot/core/broker/__init__.py"`
Expected: no output.

- [ ] **Step 8: Update the docs**

`docs/claude/architecture.md`: in the `core/broker/` paragraph v159 ER7 added to § Module map, replace

```
  the hot-reloaded config). v160 adds the eToro client, `sizing.py` and
  `pre_open.py` beside it; `tests/broker/test_guard.py` scans for eToro code
  that skips the guard.
```

with

```
  the hot-reloaded config). v160 adds the eToro **demo mirror** beside it:
  `sizing.py` (the plan's own size scaled down to `ETORO_MAX_TRADE_USD`),
  `checks.py` (every order-risk check; the first failure is the skip reason),
  `mirror.py` (pure `PlanEvent` -> `BrokerAction` translator, event-key
  dedupe), `etoro_client.py` (demo routes only, 10 s timeout, non-sleeping
  15-per-60 s order bucket) and `executor.py` (no row, no send; per-plan `seq`
  order; 20 s send budget; close-time P&L; reconciliation after 16:15 ET).
  `broker.mirror_events` is the one entry point: `trade_monitor` in
  `commands/scanning/loops.py` awaits it after the Discord feed, on every
  tick, inside `MIRROR_TICK_BUDGET_S = 25`. Rows live in `broker_orders`
  (`core/db/repositories/broker_orders.py`). Inside `swingbot/`, only
  `loops.py` imports `broker/`, lazily (`tests/broker/test_import_direction.py`);
  `tests/broker/test_guard.py` scans for eToro code that skips the guard.
```

If v159 landed different wording, replace whichever sentence of that paragraph names v160's modules (`pre_open.py`, "v160 adds") with the replacement text from `v160 adds the eToro **demo mirror**` onwards; keep v159's sentences about `assert_demo` intact.

`docs/claude/etoro-roadmap.md`: if stage 1 still says `Nothing reads them yet.` (it wraps after `Nothing` today), replace that sentence with `The v160 demo mirror reads them (§ Demo mirror below).` Then append at the end of the file:

```markdown

## Demo mirror (v160)

Built by v160 (`swingbot/core/broker/`, spec
`docs/superpowers/specs/etoro-migration/2026-10-11-v160-etoro-demo-mirror-design.md`).
That spec is the durable authorisation for **demo** automation; it grants
nothing for real money.

- **What:** every main-ledger plan the bot fills on paper is opened on the
  eToro demo account with a market order at the paper fill event (stop
  attached; long `buy`, short `sellShort` CFD), then follows the plan's
  partial close, stop moves and close. Off by default:
  `ETORO_MIRROR_ENABLED=false`.
- **Size:** the plan's own 2%-risk size, scaled down so `units x entry` stays
  within `ETORO_MAX_TRADE_USD` (default 100). Entry, stop and target are the
  plan's, so R is comparable to paper. Every order-risk check is
  `broker/checks.py`; a skip logs `etoro mirror skipped (<reason>): ...`.
- **Keys:** `ETORO_USER_KEY`/`ETORO_API_KEY` need the scopes `demo:write`,
  `demo:read` and `market-data:read`.
- **Disable:** flag off. Open demo positions keep their eToro-side stop and
  target but stop following the bot; missed events are never replayed, and the
  next reconciliation (first tick after 16:15 ET) logs the drift at WARNING.
- **Drain:** `scripts/ops/etoro_mirror_drain.py` (dry run by default,
  `--execute` closes every mirrored position). Run it before any rollback that
  removes `broker/`; the `broker_orders` table is additive and needs no
  downgrade.
- **Smoke:** `scripts/ops/etoro_demo_smoke.py`, once by hand after a deploy.
- **Report:** `scripts/reports/etoro_parity_report.py`: paper R against eToro
  R gross and net, entry drift (latency and execution), skip counts, split by
  direction, settlement type and sector. Read-only; no eToro call.
- **Lifetime:** `ETORO_MIRROR_ENABLED` is retired when the real-money spec
  brings its own switch; the table and the client are reused by it.
```

Run: `git -C "$WT" grep -n "mirror_events\|Demo mirror (v160)" -- docs/claude/architecture.md docs/claude/etoro-roadmap.md`
Expected: at least one hit in each file.

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py`
Expected: PASS. `AGENTS.md` mirrors neither paragraph verbatim. `CLAUDE.md` and `AGENTS.md` still call the eToro keys "unused so far": that line is EM15's to weigh (it needs both files in one commit), not this task's.

- [ ] **Step 9: Commit**

```bash
git -C "$WT" add swingbot/core/broker/__init__.py swingbot/commands/scanning/loops.py tests/broker/test_mirror_events.py tests/broker/test_import_direction.py tests/commands/test_loops_etoro_mirror.py docs/claude/architecture.md docs/claude/etoro-roadmap.md
git -C "$WT" commit -m "feat(v160): EM10 -- wire the eToro demo mirror into trade_monitor

broker.mirror_events is the single entry point (no-op while
ETORO_MIRROR_ENABLED is off); trade_monitor awaits _mirror_plan_events after
the Discord feed on every tick, inside MIRROR_TICK_BUDGET_S = 25, and any
failure is one WARNING. Import direction pinned for swingbot/; architecture
and roadmap docs describe the mirror.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 6 — the parity report (EM11–EM12)

### Task EM11: Parity report I: per-trade definitions

**Model:** opus — this fixes the numbers Stage 2 is decided on: sign conventions for shorts, which stop defines 1R, gross against net, and leg pairing; a wrong sign or a guessed exit price turns a friction measurement into a fiction, silently.

Spec § Comparison report (1R in price and dollars, paper R, eToro R gross and net, entry drift split into latency and execution, leg matching, the three flags), § Risks (gap-through-stop on CFD shorts). Part-local constraints above (persisted fields only, `close_rate` as the only exit price, `units_requested` for a partial, closed positions only).

This task creates the module with every per-trade function and no CLI; EM12 adds the pooled totals, the snapshot header, the caveat and `main`. All functions are pure over plain dicts and a `TradePlanV2`, so the tests need no database.

Definitions, fixed here so a re-run reproduces:

- **1R (price)** = `|plan.entry_price − plan.stop_loss|`. `stop_loss` is the plan's original stop; `working_stop` is never read. Zero, missing or non-finite → `None`.
- **1R (dollars)** = `units_filled × |avg_price − stop_sent|` from the open row.
- **Paper R** = `Σ leg["fraction"] × leg["r"]` over `plan.legs_realized`; no legs, or a leg with a missing number → `None`.
- **eToro P&L gross (USD)** = `Σ sign × (close_rate − avg_price) × leg_units` over the closing rows in `seq` order, `sign = +1` bullish, `−1` bearish. `leg_units` is `units_requested` for a filled `close_units` row (capped at what is left) and everything left for a `close_all` or `closed_by_broker` row. **eToro R gross** = that ÷ 1R dollars.
- **eToro P&L net (USD)** = `Σ (net_profit − fees − overnight_fees)` over the closing rows that carry `net_profit` (a missing `fees`/`overnight_fees` counts 0). **eToro R net** = that ÷ 1R dollars.
- **Latency R** = `sign × (quote_at_send − entry_price) ÷ 1R price`; **execution R** = `sign × (avg_price − quote_at_send) ÷ 1R price`. Positive always hurts: a long that pays more, a short that sells lower.
- **Closing rows** = rows whose action is `close_units`/`close_all` with status `filled`, plus every row with status `closed_by_broker` (a `move_stop` or close that found the position already gone), sorted by `seq`.
- **Leg pairs** = paper fractions in `legs_realized` order zipped (longest, `None`-padded) with the broker fractions: `fraction_closed` for a partial, `1 − Σ earlier` for a closing-all row.

**Files:**
- Create: `scripts/reports/etoro_parity_report.py`
- Create: `tests/scripts/test_etoro_parity_report.py`

**Interfaces:**
- Consumes:
  - The `broker_orders` row contract (index ledger, EM2/EM8/EM9; flat record dicts): `plan_id`, `action` (`open`/`close_units`/`close_all`/`move_stop`), `status`, `seq`, and the doc fields listed in this part's constraints.
  - `TradePlanV2` fields `plan_id`, `ticker`, `direction` (`bullish`/`bearish`), `entry_price`, `stop_loss`, `legs_realized` (`swingbot/core/planning/plan_types.py:21`).
  - Test helper `tests.planning.test_plan_engine_model._plan(**kw) -> TradePlanV2` (`tests/planning/test_plan_engine_model.py:6`); `PlanStatus` (`swingbot/core/planning/plan_types.py`).
- Produces (EM12 relies on these exact names):
  - Constants `OPEN = "open"`, `CLOSE_UNITS = "close_units"`, `CLOSE_ALL = "close_all"`, `CLOSED_BY_BROKER = "closed_by_broker"`.
  - `one_r_price(plan) -> float | None`; `one_r_dollars(open_row: dict) -> float | None`; `paper_r(plan) -> float | None`; `closing_rows(rows: list[dict]) -> list[dict]`; `etoro_r_gross(open_row: dict, close_rows: list[dict]) -> float | None`; `etoro_r_net(open_row: dict, close_rows: list[dict]) -> float | None`; `entry_drift(plan, open_row: dict) -> tuple[float | None, float | None]` (latency, execution); `leg_pairs(plan, close_rows: list[dict]) -> list[tuple[float | None, float | None]]`; `holding_days(open_row: dict, close_rows: list[dict]) -> float | None`.
  - `trade_row(plan, rows: list[dict]) -> dict | None` with keys `plan_id, ticker, direction, settlement_type, paper_r, etoro_r_gross, etoro_r_net, latency_r, execution_r, legs, divergent, below_minus_one, holding_days` (the ledger's keys) plus `gross_usd, net_usd` (the spec's separately reported dollar totals; only EM12 reads them). `None` when the plan is missing, there is no `filled` open row, or the eToro position is not closed yet.

- [ ] **Step 1: Confirm the helpers the tests lean on**

```bash
git -C "$WT" grep -n "^def _plan" -- tests/planning/test_plan_engine_model.py
git -C "$WT" grep -n "legs_realized\|class PlanStatus" -- swingbot/core/planning/plan_types.py
test -e "$WT/scripts/reports/etoro_parity_report.py" && echo EXISTS || echo absent
```

Expected: one `_plan` hit, a `legs_realized` field and `class PlanStatus`, and `absent`. `EXISTS` means a previous run got here: read it and resume at the first step whose test fails.

- [ ] **Step 2: Write the failing tests**

Create `tests/scripts/test_etoro_parity_report.py`:

```python
"""v160 eToro parity report: per-trade definitions (spec § Comparison report).

Worked examples, by hand:
- long p1: entry 100, stop 95 (1R price 5); eToro 2 units at 100.5, stop 95
  (1R dollars 11); TP1 closes 1 unit at 103, the rest closes at 106 ->
  gross 8.0 USD = 0.7273 R; net (9.0 - 0.5 - 0.2) / 11 = 0.7545 R;
  latency (100.2 - 100) / 5 = 0.04; execution (100.5 - 100.2) / 5 = 0.06.
- short p2: entry 50, stop 52 (1R price 2); eToro 4 units sold at 49.8, stop 52
  (1R dollars 8.8); gap close at 53 -> gross -12.8 USD = -1.4545 R (below -1);
  latency -(49.9 - 50) / 2 = 0.05; execution -(49.8 - 49.9) / 2 = 0.05.
"""
import math

import pytest

from scripts.reports import etoro_parity_report as report
from swingbot.core.planning.plan_types import PlanStatus
from tests.planning.test_plan_engine_model import _plan

LONG_LEGS = [{"fraction": 0.5, "r": 0.4, "exit_price": 102.0, "reason": "tp1"},
             {"fraction": 0.5, "r": 1.2, "exit_price": 106.0, "reason": "tp1_runner_trail"}]


def _long_plan(**kw):
    base = dict(plan_id="p1", ticker="AAPL", direction="bullish", entry_price=100.0,
                stop_loss=95.0, tp1=103.0, tp2=106.0, status=PlanStatus.CLOSED,
                legs_realized=list(LONG_LEGS))
    base.update(kw)
    return _plan(**base)


def _short_plan(**kw):
    base = dict(plan_id="p2", ticker="TSLA", direction="bearish", entry_price=50.0,
                stop_loss=52.0, tp1=46.0, tp2=None, status=PlanStatus.CLOSED,
                legs_realized=[{"fraction": 1.0, "r": -1.0, "exit_price": 52.0,
                                "reason": "loss"}])
    base.update(kw)
    return _plan(**base)


def _row(plan_id, action, seq, status="filled", **doc):
    return {"plan_id": plan_id, "action": action, "event_key": f"k{seq}", "seq": seq,
            "status": status, **doc}


def _long_open(**doc):
    base = dict(ticker="AAPL", direction="bullish", settlement_type="real",
                units_filled=2.0, avg_price=100.5, stop_sent=95.0, quote_at_send=100.2,
                filled_at="2026-10-12T14:00:00+00:00")
    base.update(doc)
    return _row("p1", "open", 1, **base)


def _long_rows(partial=None, final=None):
    partial_doc = dict(units_requested=1.0, fraction_closed=0.5, close_rate=103.0)
    partial_doc.update(partial or {})
    final_doc = dict(close_rate=106.0, net_profit=9.0, fees=0.5, overnight_fees=0.2,
                     closed_at="2026-10-15T14:00:00+00:00")
    final_doc.update(final or {})
    return [_long_open(),
            _row("p1", "close_units", 2, **partial_doc),
            _row("p1", "move_stop", 3, stop_sent=100.0),
            _row("p1", "close_all", 4, **final_doc)]


def _short_rows():
    return [_row("p2", "open", 1, ticker="TSLA", direction="bearish", settlement_type="cfd",
                 units_filled=4.0, avg_price=49.8, stop_sent=52.0, quote_at_send=49.9,
                 filled_at="2026-10-12T15:00:00+00:00"),
            _row("p2", "close_all", 2, close_rate=53.0, net_profit=-13.0, fees=0.0,
                 overnight_fees=0.3, closed_at="2026-10-13T15:00:00+00:00")]


def _closes(rows):
    return report.closing_rows(rows)


# --- 1R ----------------------------------------------------------------------

def test_one_r_price_uses_the_original_stop_never_working_stop():
    assert report.one_r_price(_long_plan(working_stop=101.0)) == 5.0
    assert report.one_r_price(_short_plan()) == 2.0


@pytest.mark.parametrize("entry, stop", [(None, 95.0), (100.0, 100.0), (math.nan, 95.0)])
def test_one_r_price_is_none_when_undefined(entry, stop):
    assert report.one_r_price(_long_plan(entry_price=entry, stop_loss=stop)) is None


def test_one_r_dollars_comes_from_the_open_row():
    assert report.one_r_dollars(_long_open()) == pytest.approx(11.0)


@pytest.mark.parametrize("field, value", [("units_filled", None), ("avg_price", math.inf),
                                          ("stop_sent", "x"), ("avg_price", 95.0)])
def test_one_r_dollars_is_none_when_undefined(field, value):
    assert report.one_r_dollars(_long_open(**{field: value})) is None


# --- paper R -------------------------------------------------------------------

def test_paper_r_weights_each_leg_by_its_fraction():
    assert report.paper_r(_long_plan()) == pytest.approx(0.8)


def test_paper_r_is_none_without_legs_or_with_a_broken_leg():
    assert report.paper_r(_long_plan(legs_realized=[])) is None
    assert report.paper_r(_long_plan(legs_realized=[{"fraction": 0.5, "r": None}])) is None


# --- closing rows and eToro R --------------------------------------------------------

def test_closing_rows_are_filled_closes_and_broker_closes_in_seq_order():
    rows = list(reversed(_long_rows())) + [
        _row("p1", "close_units", 5, status="rejected"),
        _row("p1", "move_stop", 6, status="closed_by_broker")]
    assert [(r["action"], r["seq"]) for r in report.closing_rows(rows)] == [
        ("close_units", 2), ("close_all", 4), ("move_stop", 6)]


def test_long_gross_and_net_r():
    rows = _long_rows()
    assert report.etoro_r_gross(rows[0], _closes(rows)) == pytest.approx(8.0 / 11.0)
    assert report.etoro_r_net(rows[0], _closes(rows)) == pytest.approx(8.3 / 11.0)


def test_short_gross_r_is_sign_adjusted_and_can_fall_below_minus_one():
    rows = _short_rows()
    assert report.etoro_r_gross(rows[0], _closes(rows)) == pytest.approx(-12.8 / 8.8)
    assert report.etoro_r_net(rows[0], _closes(rows)) == pytest.approx(-13.3 / 8.8)


def test_a_leg_without_close_rate_makes_gross_unknown_never_guessed():
    rows = _long_rows(partial={"close_rate": None, "avg_price": 100.5})
    assert report.etoro_r_gross(rows[0], _closes(rows)) is None
    assert report.etoro_r_net(rows[0], _closes(rows)) == pytest.approx(8.3 / 11.0)


def test_a_partial_uses_units_requested_not_the_lookup_units():
    rows = _long_rows(partial={"units_filled": 2.0})
    assert report.etoro_r_gross(rows[0], _closes(rows)) == pytest.approx(8.0 / 11.0)


def test_net_is_none_without_persisted_economics_and_missing_fees_count_zero():
    rows = _long_rows(final={"net_profit": None})
    assert report.etoro_r_net(rows[0], _closes(rows)) is None
    rows = _long_rows(final={"fees": None, "overnight_fees": None})
    assert report.etoro_r_net(rows[0], _closes(rows)) == pytest.approx(9.0 / 11.0)


def test_closed_by_broker_closes_whatever_is_left():
    open_row = _row("p3", "open", 1, direction="bullish", units_filled=3.0, avg_price=20.0,
                    stop_sent=19.0)
    gone = _row("p3", "move_stop", 2, status="closed_by_broker", close_rate=19.5)
    assert report.etoro_r_gross(open_row, [gone]) == pytest.approx(-0.5)


def test_no_close_rows_means_no_etoro_r():
    assert report.etoro_r_gross(_long_open(), []) is None
    assert report.etoro_r_net(_long_open(), []) is None


# --- entry drift -------------------------------------------------------------------

def test_long_entry_drift_splits_latency_and_execution():
    assert report.entry_drift(_long_plan(), _long_open()) == (
        pytest.approx(0.04), pytest.approx(0.06))


def test_short_entry_drift_is_positive_when_it_hurts():
    latency, execution = report.entry_drift(_short_plan(), _short_rows()[0])
    assert (latency, execution) == (pytest.approx(0.05), pytest.approx(0.05))


def test_entry_drift_without_a_quote_keeps_what_it_can():
    assert report.entry_drift(_long_plan(), _long_open(quote_at_send=None)) == (None, None)
    assert report.entry_drift(_long_plan(stop_loss=100.0), _long_open()) == (None, None)


# --- legs and holding ------------------------------------------------------------------

def test_leg_pairs_match_paper_legs_to_broker_closes_in_order():
    rows = _long_rows()
    assert report.leg_pairs(_long_plan(), _closes(rows)) == [(0.5, 0.5), (0.5, 0.5)]


def test_leg_pairs_pad_the_shorter_side_with_none():
    rows = _short_rows()
    plan = _short_plan(legs_realized=LONG_LEGS)
    assert report.leg_pairs(plan, _closes(rows)) == [(0.5, 1.0), (0.5, None)]


def test_holding_days_run_from_the_open_fill_to_the_last_close():
    rows = _long_rows()
    assert report.holding_days(rows[0], _closes(rows)) == pytest.approx(3.0)
    assert report.holding_days(_long_open(filled_at="bad"), _closes(rows)) is None


# --- trade_row ------------------------------------------------------------------------

TRADE_KEYS = {"plan_id", "ticker", "direction", "settlement_type", "paper_r", "etoro_r_gross",
              "etoro_r_net", "latency_r", "execution_r", "legs", "divergent",
              "below_minus_one", "holding_days", "gross_usd", "net_usd"}


def test_trade_row_for_a_closed_long():
    trade = report.trade_row(_long_plan(), _long_rows())
    assert set(trade) == TRADE_KEYS
    assert (trade["plan_id"], trade["ticker"], trade["direction"], trade["settlement_type"]) == (
        "p1", "AAPL", "bullish", "real")
    assert trade["paper_r"] == pytest.approx(0.8)
    assert trade["etoro_r_gross"] == pytest.approx(8.0 / 11.0)
    assert (trade["gross_usd"], trade["net_usd"]) == (pytest.approx(8.0), pytest.approx(8.3))
    assert (trade["divergent"], trade["below_minus_one"]) == (False, False)


def test_trade_row_flags_a_gap_through_stop_short():
    trade = report.trade_row(_short_plan(), _short_rows())
    assert trade["below_minus_one"] is True and trade["settlement_type"] == "cfd"


def test_trade_row_flags_a_broker_side_exit_as_divergent():
    plan = _long_plan(plan_id="p3", entry_price=20.0, stop_loss=19.0, legs_realized=[])
    rows = [_row("p3", "open", 1, direction="bullish", units_filled=3.0, avg_price=20.0,
                 stop_sent=19.0),
            _row("p3", "move_stop", 2, status="closed_by_broker", close_rate=19.5)]
    trade = report.trade_row(plan, rows)
    assert trade["divergent"] is True and trade["paper_r"] is None
    assert trade["settlement_type"] == "unknown"


def test_trade_row_skips_missing_plans_unfilled_opens_and_open_positions():
    rows = _long_rows()
    assert report.trade_row(None, rows) is None
    assert report.trade_row(_long_plan(), [_long_open(status="skipped")] + rows[1:]) is None
    assert report.trade_row(_long_plan(), rows[:3]) is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/scripts/test_etoro_parity_report.py`
Expected: FAIL, collection error `ImportError: cannot import name 'etoro_parity_report' from 'scripts.reports'` (or `ModuleNotFoundError`).

- [ ] **Step 4: Write the per-trade functions**

Create `scripts/reports/etoro_parity_report.py`:

```python
"""v160 eToro parity report: paper R against eToro demo R, per trade and pooled.

Read-only over the `broker_orders` table and the plan store; it never calls
eToro and needs no keys. Definitions are fixed by the v160 spec (section
"Comparison report") so a re-run reproduces:

- 1R price   = |plan.entry_price - plan.stop_loss| (the original stop).
- 1R dollars = units_filled x |avg_price - stop_sent| from the open row.
- Paper R    = sum(fraction x r) over plan.legs_realized (model fills, gross).
- eToro R gross = sum(sign x (close_rate - avg_price) x leg units) / 1R dollars.
- eToro R net   = sum(net_profit - fees - overnight_fees) / 1R dollars.
- Latency R = sign x (quote_at_send - entry_price) / 1R price; execution R =
  sign x (avg_price - quote_at_send) / 1R price. Positive always hurts.

A close leg's exit price is its persisted close_rate only: a close row's
avg_price comes from the lookup's openingData and is not a close price.

    python scripts/reports/etoro_parity_report.py [--json out.json]
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OPEN = "open"
CLOSE_UNITS = "close_units"
CLOSE_ALL = "close_all"
CLOSED_BY_BROKER = "closed_by_broker"
_CLOSE_ACTIONS = frozenset({CLOSE_UNITS, CLOSE_ALL})


def _num(value) -> float | None:
    """A finite float, else None (missing, text, NaN, inf)."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _sign(direction) -> float:
    return -1.0 if direction == "bearish" else 1.0


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def one_r_price(plan) -> float | None:
    """The paper plan's original risk per unit; working_stop is never used."""
    entry, stop = _num(plan.entry_price), _num(plan.stop_loss)
    if entry is None or stop is None:
        return None
    risk = abs(entry - stop)
    return risk if risk > 0 else None


def one_r_dollars(open_row: dict) -> float | None:
    """The eToro position's own risk in USD, as recorded at the open."""
    units = _num(open_row.get("units_filled"))
    avg, stop = _num(open_row.get("avg_price")), _num(open_row.get("stop_sent"))
    if units is None or avg is None or stop is None:
        return None
    risk = units * abs(avg - stop)
    return risk if risk > 0 else None


def paper_r(plan) -> float | None:
    """Sum of fraction x r over the paper legs; None without complete legs."""
    legs = plan.legs_realized or []
    if not legs:
        return None
    total = 0.0
    for leg in legs:
        fraction, r = _num(leg.get("fraction")), _num(leg.get("r"))
        if fraction is None or r is None:
            return None
        total += fraction * r
    return total


def _is_partial(row: dict) -> bool:
    return row.get("action") == CLOSE_UNITS and row.get("status") == "filled"


def _is_closing(row: dict) -> bool:
    if row.get("status") == CLOSED_BY_BROKER:
        return True
    return row.get("action") in _CLOSE_ACTIONS and row.get("status") == "filled"


def closing_rows(rows: list[dict]) -> list[dict]:
    """Filled closes plus every closed_by_broker row, in seq order."""
    return sorted((row for row in rows if _is_closing(row)), key=lambda row: row.get("seq", 0))


def _leg_units(open_units: float, close_rows: list[dict]) -> list[float] | None:
    """Units each closing row took off: units_requested for a partial (capped
    at what is left), everything left for a closing-all row."""
    legs, left = [], open_units
    for row in close_rows:
        units = _num(row.get("units_requested")) if _is_partial(row) else left
        if units is None:
            return None
        units = min(units, left)
        legs.append(units)
        left -= units
    return legs


def _gross_usd(open_row: dict, close_rows: list[dict]) -> float | None:
    avg, units = _num(open_row.get("avg_price")), _num(open_row.get("units_filled"))
    if avg is None or units is None or not close_rows:
        return None
    legs = _leg_units(units, close_rows)
    if legs is None:
        return None
    sign = _sign(open_row.get("direction"))
    total = 0.0
    for row, leg_units in zip(close_rows, legs):
        exit_price = _num(row.get("close_rate"))
        if exit_price is None:
            return None
        total += sign * (exit_price - avg) * leg_units
    return total


def _net_usd(close_rows: list[dict]) -> float | None:
    economics = [row for row in close_rows if _num(row.get("net_profit")) is not None]
    if not economics:
        return None
    return sum(_num(row["net_profit"]) - (_num(row.get("fees")) or 0.0)
               - (_num(row.get("overnight_fees")) or 0.0) for row in economics)


def etoro_r_gross(open_row: dict, close_rows: list[dict]) -> float | None:
    return _ratio(_gross_usd(open_row, close_rows), one_r_dollars(open_row))


def etoro_r_net(open_row: dict, close_rows: list[dict]) -> float | None:
    return _ratio(_net_usd(close_rows), one_r_dollars(open_row))


def entry_drift(plan, open_row: dict) -> tuple[float | None, float | None]:
    """(latency, execution) in R; positive always hurts."""
    risk, sign = one_r_price(plan), _sign(plan.direction)
    entry, quote = _num(plan.entry_price), _num(open_row.get("quote_at_send"))
    avg = _num(open_row.get("avg_price"))
    if risk is None or quote is None:
        return None, None
    latency = sign * (quote - entry) / risk
    execution = None if avg is None else sign * (avg - quote) / risk
    return latency, execution


def _broker_fractions(close_rows: list[dict]) -> list[float | None]:
    out, used = [], 0.0
    for row in close_rows:
        if used is None:
            out.append(None)
            continue
        fraction = (_num(row.get("fraction_closed")) if _is_partial(row)
                    else max(0.0, 1.0 - used))
        out.append(fraction)
        used = None if fraction is None else used + fraction
    return out


def leg_pairs(plan, close_rows: list[dict]) -> list[tuple[float | None, float | None]]:
    """(paper fraction, broker fraction) per leg, paper order against seq order."""
    paper = [_num(leg.get("fraction")) for leg in (plan.legs_realized or [])]
    return list(zip_longest(paper, _broker_fractions(close_rows)))


def holding_days(open_row: dict, close_rows: list[dict]) -> float | None:
    start = _parse_ts(open_row.get("filled_at"))
    ends = [_parse_ts(row.get("closed_at") or row.get("filled_at")) for row in close_rows]
    ends = [end for end in ends if end is not None]
    if start is None or not ends:
        return None
    return max(0.0, (max(ends) - start).total_seconds() / 86400.0)


def _filled_open(rows: list[dict]) -> dict | None:
    return next((row for row in rows
                 if row.get("action") == OPEN and row.get("status") == "filled"), None)


def _position_closed(rows: list[dict]) -> bool:
    return any(row.get("status") == CLOSED_BY_BROKER
               or (row.get("action") == CLOSE_ALL and row.get("status") == "filled")
               for row in rows)


def trade_row(plan, rows: list[dict]) -> dict | None:
    """One closed eToro trade against its paper plan, else None."""
    open_row = _filled_open(rows)
    if plan is None or open_row is None or not _position_closed(rows):
        return None
    closes = closing_rows(rows)
    gross = etoro_r_gross(open_row, closes)
    latency, execution = entry_drift(plan, open_row)
    return {
        "plan_id": plan.plan_id,
        "ticker": open_row.get("ticker") or plan.ticker,
        "direction": plan.direction,
        "settlement_type": open_row.get("settlement_type") or "unknown",
        "paper_r": paper_r(plan),
        "etoro_r_gross": gross,
        "etoro_r_net": etoro_r_net(open_row, closes),
        "latency_r": latency,
        "execution_r": execution,
        "legs": leg_pairs(plan, closes),
        "divergent": any(row.get("status") == CLOSED_BY_BROKER for row in rows),
        "below_minus_one": gross is not None and gross < -1.0,
        "holding_days": holding_days(open_row, closes),
        "gross_usd": _gross_usd(open_row, closes),
        "net_usd": _net_usd(closes),
    }
```

`entry_drift` returns `(None, None)` when `entry` is `None` because `one_r_price` is then `None` too.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/scripts/test_etoro_parity_report.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python -m radon cc -s -n C "$WT/scripts/reports/etoro_parity_report.py"`
Expected: no output (the largest, `trade_row`, grades B).

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py`
Expected: PASS (the report holds no `etoro.com` string, no eToro import and no key name, so the AST scan does not list it).

- [ ] **Step 6: Commit**

```bash
git -C "$WT" add scripts/reports/etoro_parity_report.py tests/scripts/test_etoro_parity_report.py
git -C "$WT" commit -m "feat(v160): EM11 -- parity report per-trade definitions

1R from the original stop, eToro R gross (close_rate legs, sign-adjusted for
shorts) and net (persisted net_profit less fees and overnight), latency and
execution drift signed so positive hurts, leg pairing by seq, divergent and
below -1 flags. Pure functions over persisted rows; no CLI yet.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task EM12: Parity report II: pooled totals, flags, snapshot, caveat, CLI

**Model:** sonnet — aggregation, formatting and a thin CLI over EM11's fixed definitions; the one decision (means ignore `None` and print their own `n`) is pinned below.

Spec § Comparison report (pooled totals: N, mean paper R, mean eToro R gross and net, mean latency and execution drift; split by direction, `settlement_type` and correlated cluster; skip counts by reason; snapshot header; the caveat on every run; dollar totals reported separately). Index ledger EM12 (`cluster_of`: the ticker's sector, else `"unknown"`). Part-local constraints above.

`updated_at` is a reserved column the repository drops from every record (`swingbot/core/db/codec.py:12`, `RESERVED_KEYS`), so `_load_rows` reads it with one extra `SELECT request_id, updated_at` and attaches it as an ISO string; `snapshot_header` takes the maximum. The plan-store cut-off is the UTC time stamped right after the plans were read.

**Files:**
- Modify: `scripts/reports/etoro_parity_report.py`
- Modify: `tests/scripts/test_etoro_parity_report.py`

**Interfaces:**
- Consumes:
  - EM11: `trade_row(plan, rows) -> dict | None` (keys incl. `gross_usd`, `net_usd`), `CLOSED_BY_BROKER`.
  - EM2: `swingbot.core.db.repositories.broker_orders.broker_orders_repo().all_rows() -> list[dict]` (ordered `plan_id, seq`), `insert_new(record) -> dict | None`; table `swingbot.core.db.schema.broker_orders` (columns `request_id`, `updated_at`).
  - `swingbot.core.db.engine.get_engine()` (`engine.py:23`; the autouse `_store_database` fixture patches it, `tests/conftest.py:173`); `swingbot.core.planning.plan_store.PlanStore().get(plan_id)`; `swingbot.core.marketdata.universe.sector_map(name) -> dict` (`universe.py:219`); `config.SCAN_UNIVERSE`.
- Produces:
  - `CAVEAT: str`; `pooled(trades: list[dict]) -> dict` (keys `n, n_paper, n_gross, n_net, mean_paper_r, mean_etoro_r_gross, mean_etoro_r_net, mean_latency_r, mean_execution_r, mean_holding_days, gross_usd, net_usd, divergent, below_minus_one`); `split_by(trades: list[dict], key: str) -> dict[str, dict]`; `skip_counts(rows: list[dict]) -> dict[str, int]`; `snapshot_header(rows: list[dict], plan_cutoff: str) -> str`; `cluster_of(ticker: str, sectors: dict | None) -> str`; `build_report(rows: list[dict], plans: dict, sectors: dict | None, plan_cutoff: str) -> dict` (keys `snapshot, caveat, pooled, by_direction, by_settlement, by_cluster, skips, trades`; each trade gains `cluster`); `render(report: dict) -> str`; `main(argv: list[str] | None = None) -> int` (`--json PATH`).

- [ ] **Step 1: Confirm EM11 is in place**

```bash
git -C "$WT" grep -n "^def trade_row\|^def closing_rows\|^CLOSED_BY_BROKER" -- scripts/reports/etoro_parity_report.py
git -C "$WT" grep -n "def all_rows\|def insert_new" -- swingbot/core/db/repositories/broker_orders.py
```

Expected: three hits, then two. Otherwise `BLOCKED: EM12 needs EM11` (or `EM2`).

- [ ] **Step 2: Write the failing tests**

Append to `tests/scripts/test_etoro_parity_report.py`:

```python
# --- pooled totals, splits, skips, snapshot (EM12) ------------------------------

def _trade(**kw):
    base = dict(plan_id="p", ticker="AAPL", direction="bullish", settlement_type="real",
                paper_r=1.0, etoro_r_gross=0.8, etoro_r_net=0.7, latency_r=0.1,
                execution_r=0.05, legs=[], divergent=False, below_minus_one=False,
                holding_days=2.0, gross_usd=8.0, net_usd=7.0, cluster="Technology")
    base.update(kw)
    return base


def test_pooled_means_ignore_none_and_report_their_own_n():
    trades = [_trade(), _trade(etoro_r_gross=None, gross_usd=None, paper_r=-1.0),
              _trade(divergent=True, below_minus_one=True, etoro_r_net=None, net_usd=None)]
    block = report.pooled(trades)
    assert (block["n"], block["n_paper"], block["n_gross"], block["n_net"]) == (3, 3, 2, 2)
    assert block["mean_paper_r"] == pytest.approx(1.0 / 3.0)
    assert block["mean_etoro_r_gross"] == pytest.approx(0.8)
    assert block["mean_etoro_r_net"] == pytest.approx(0.7)
    assert (block["gross_usd"], block["net_usd"]) == (pytest.approx(16.0), pytest.approx(14.0))
    assert (block["divergent"], block["below_minus_one"]) == (1, 1)


def test_pooled_over_nothing_is_empty_not_an_error():
    block = report.pooled([])
    assert block["n"] == 0 and block["mean_paper_r"] is None and block["gross_usd"] == 0


def test_split_by_groups_and_names_missing_values_unknown():
    trades = [_trade(direction="bullish"), _trade(direction="bearish"),
              _trade(direction="bearish", settlement_type=None)]
    assert {k: v["n"] for k, v in report.split_by(trades, "direction").items()} == {
        "bearish": 2, "bullish": 1}
    assert list(report.split_by(trades, "settlement_type")) == ["real", "unknown"]


def test_skip_counts_count_only_skipped_rows_by_reason():
    rows = [_row("a", "open", 1, status="skipped", skip_reason="ineligible"),
            _row("b", "open", 1, status="skipped", skip_reason="ineligible"),
            _row("c", "open", 1, status="skipped", skip_reason="stale_fill"),
            _row("d", "open", 1, status="rejected", skip_reason="ignored")]
    assert report.skip_counts(rows) == {"ineligible": 2, "stale_fill": 1}


def test_snapshot_header_names_rows_latest_update_and_cutoff():
    rows = [{"updated_at": "2026-10-12T14:00:00+00:00"}, {"updated_at": "2026-10-13T09:00:00+00:00"},
            {}]
    header = report.snapshot_header(rows, "2026-10-14T08:00:00+00:00")
    assert "rows=3" in header
    assert "2026-10-13T09:00:00+00:00" in header and "2026-10-14T08:00:00+00:00" in header
    assert "max updated_at=none" in report.snapshot_header([], "c")


def test_cluster_of_falls_back_to_unknown():
    assert report.cluster_of("AAPL", {"AAPL": "Technology"}) == "Technology"
    assert report.cluster_of("XYZ", {"AAPL": "Technology"}) == "unknown"
    assert report.cluster_of("AAPL", None) == "unknown"


def test_build_report_joins_rows_to_plans_and_splits_by_cluster():
    rows = _long_rows() + _short_rows() + [
        _row("p9", "open", 1, status="skipped", skip_reason="ineligible")]
    plans = {"p1": _long_plan(), "p2": _short_plan()}
    out = report.build_report(rows, plans, {"AAPL": "Technology"}, "2026-10-14T08:00:00+00:00")
    assert set(out) == {"snapshot", "caveat", "pooled", "by_direction", "by_settlement",
                        "by_cluster", "skips", "trades"}
    assert [t["plan_id"] for t in out["trades"]] == ["p1", "p2"]
    assert out["pooled"]["n"] == 2 and out["pooled"]["below_minus_one"] == 1
    assert set(out["by_cluster"]) == {"Technology", "unknown"}
    assert set(out["by_settlement"]) == {"real", "cfd"}
    assert out["skips"] == {"ineligible": 1}
    assert out["caveat"] == report.CAVEAT


def test_the_caveat_names_the_execution_style_gap():
    assert "market order at the paper fill event" in report.CAVEAT
    assert "resting orders placed at alert time" in report.CAVEAT


def test_main_prints_snapshot_and_caveat_and_writes_json(monkeypatch, capsys, tmp_path):
    import json

    monkeypatch.setattr(report, "_load_rows", lambda: _long_rows())
    monkeypatch.setattr(report, "_load_plans", lambda ids: {"p1": _long_plan()})
    monkeypatch.setattr(report, "_load_sectors", lambda: {"AAPL": "Technology"})
    out_path = tmp_path / "parity.json"
    assert report.main(["--json", str(out_path)]) == 0
    printed = capsys.readouterr().out
    assert printed.splitlines()[0].startswith("Snapshot: broker_orders rows=4")
    assert report.CAVEAT in printed and "p1 AAPL" in printed
    saved = json.loads(out_path.read_text(encoding="utf-8"))
    assert saved["pooled"]["n"] == 1 and saved["trades"][0]["cluster"] == "Technology"


def test_load_rows_attaches_updated_at_from_the_table():
    from swingbot.core.db.repositories.broker_orders import broker_orders_repo
    broker_orders_repo().insert_new({"plan_id": "p1", "action": "open", "event_key": "filled",
                                     "request_id": "rid-1", "ticker": "AAPL"})
    rows = report._load_rows()
    assert [(row["request_id"], row["ticker"]) for row in rows] == [("rid-1", "AAPL")]
    assert rows[0]["updated_at"][:2] == "20"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/scripts/test_etoro_parity_report.py`
Expected: FAIL, the EM12 tests with `AttributeError: module 'scripts.reports.etoro_parity_report' has no attribute 'pooled'` (and `CAVEAT`, `split_by`, `main`, `_load_rows`, ...); every EM11 test still passes. `test_load_rows_attaches_updated_at_from_the_table` needs the db-test Postgres: if it shows as skipped, start it before Step 5 (a skipped DB test does not count as run).

- [ ] **Step 4: Add the pooled totals, the report and the CLI**

In `scripts/reports/etoro_parity_report.py`, extend the import block to:

```python
import argparse
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path
```

Then append to the end of the file:

```python
# --- pooled totals, report and CLI (EM12) -----------------------------------

CAVEAT = ("Caveat: the mirror enters with a market order at the paper fill event, while "
          "the partner's real-money practice is resting orders placed at alert time. This "
          "report measures broker frictions on the bot's plans; it does not validate that "
          "execution style.")

_MEANS = (("mean_paper_r", "paper_r"), ("mean_etoro_r_gross", "etoro_r_gross"),
          ("mean_etoro_r_net", "etoro_r_net"), ("mean_latency_r", "latency_r"),
          ("mean_execution_r", "execution_r"), ("mean_holding_days", "holding_days"))
_COUNTS = (("n_paper", "paper_r"), ("n_gross", "etoro_r_gross"), ("n_net", "etoro_r_net"))
_SPLITS = (("By direction", "by_direction"), ("By settlement type", "by_settlement"),
           ("By cluster (sector)", "by_cluster"))


def _present(trades: list[dict], key: str) -> list[float]:
    return [trade[key] for trade in trades if trade.get(key) is not None]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def pooled(trades: list[dict]) -> dict:
    """N, the means (each over its non-None values, with its own n), the
    dollar totals and the two flag counts."""
    block = {"n": len(trades)}
    block.update({name: len(_present(trades, key)) for name, key in _COUNTS})
    block.update({name: _mean(_present(trades, key)) for name, key in _MEANS})
    block["gross_usd"] = sum(_present(trades, "gross_usd"))
    block["net_usd"] = sum(_present(trades, "net_usd"))
    block["divergent"] = sum(1 for trade in trades if trade.get("divergent"))
    block["below_minus_one"] = sum(1 for trade in trades if trade.get("below_minus_one"))
    return block


def split_by(trades: list[dict], key: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for trade in trades:
        groups.setdefault(str(trade.get(key) or "unknown"), []).append(trade)
    return {name: pooled(groups[name]) for name in sorted(groups)}


def skip_counts(rows: list[dict]) -> dict[str, int]:
    counts = Counter(str(row.get("skip_reason") or "unknown")
                     for row in rows if row.get("status") == "skipped")
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def snapshot_header(rows: list[dict], plan_cutoff: str) -> str:
    stamps = [str(row["updated_at"]) for row in rows if row.get("updated_at")]
    latest = max(stamps) if stamps else "none"
    return (f"Snapshot: broker_orders rows={len(rows)}, max updated_at={latest}, "
            f"plan store read at {plan_cutoff}")


def cluster_of(ticker: str, sectors: dict | None) -> str:
    return (sectors or {}).get(ticker) or "unknown"


def _rows_by_plan(rows: list[dict]) -> dict:
    by_plan: dict = {}
    for row in rows:
        by_plan.setdefault(row.get("plan_id"), []).append(row)
    return by_plan


def build_report(rows: list[dict], plans: dict, sectors: dict | None, plan_cutoff: str) -> dict:
    trades = []
    for plan_id, plan_rows in sorted(_rows_by_plan(rows).items(), key=lambda item: str(item[0])):
        ordered = sorted(plan_rows, key=lambda row: row.get("seq", 0))
        trade = trade_row(plans.get(plan_id), ordered)
        if trade is not None:
            trade["cluster"] = cluster_of(trade["ticker"], sectors)
            trades.append(trade)
    return {
        "snapshot": snapshot_header(rows, plan_cutoff),
        "caveat": CAVEAT,
        "pooled": pooled(trades),
        "by_direction": split_by(trades, "direction"),
        "by_settlement": split_by(trades, "settlement_type"),
        "by_cluster": split_by(trades, "cluster"),
        "skips": skip_counts(rows),
        "trades": trades,
    }


def _fmt(value, spec: str = "+.3f") -> str:
    return "-" if value is None else format(value, spec)


def _pooled_line(label: str, block: dict) -> str:
    return (f"  {label:<16} N={block['n']:<4} paper {_fmt(block['mean_paper_r'])} "
            f"(n={block['n_paper']})  eToro gross {_fmt(block['mean_etoro_r_gross'])} "
            f"(n={block['n_gross']})  net {_fmt(block['mean_etoro_r_net'])} "
            f"(n={block['n_net']})  latency {_fmt(block['mean_latency_r'])}  "
            f"execution {_fmt(block['mean_execution_r'])}  divergent {block['divergent']}  "
            f"below -1R {block['below_minus_one']}")


def _trade_line(trade: dict) -> str:
    flag = "  DIVERGENT" if trade["divergent"] else ""
    return (f"  {trade['plan_id']} {trade['ticker']} {trade['direction']} "
            f"{trade['settlement_type']}  paper {_fmt(trade['paper_r'])}  "
            f"gross {_fmt(trade['etoro_r_gross'])}  net {_fmt(trade['etoro_r_net'])}  "
            f"latency {_fmt(trade['latency_r'])}  execution {_fmt(trade['execution_r'])}  "
            f"held {_fmt(trade['holding_days'], '.1f')} d  legs {trade['legs']}{flag}")


def render(report: dict) -> str:
    total = report["pooled"]
    lines = [report["snapshot"], report["caveat"], "", "Pooled", _pooled_line("all", total),
             f"  dollars: gross {total['gross_usd']:+.2f} USD, net {total['net_usd']:+.2f} USD; "
             f"mean holding {_fmt(total['mean_holding_days'], '.1f')} d"]
    for title, key in _SPLITS:
        lines += ["", title] + [_pooled_line(name, block) for name, block in report[key].items()]
    skips = [f"  {reason}: {count}" for reason, count in report["skips"].items()]
    lines += ["", "Skips by reason"] + (skips or ["  none"])
    lines += ["", "Trades"] + ([_trade_line(t) for t in report["trades"]] or ["  none"])
    return "\n".join(lines)


def _load_rows() -> list[dict]:
    """Every broker_orders row, with updated_at attached (a reserved column
    the repository drops from its records) for the snapshot header."""
    import sqlalchemy as sa

    from swingbot.core.db.engine import get_engine
    from swingbot.core.db.repositories.broker_orders import broker_orders_repo
    from swingbot.core.db.schema import broker_orders
    rows = broker_orders_repo().all_rows()
    query = sa.select(broker_orders.c.request_id, broker_orders.c.updated_at)
    with get_engine().connect() as conn:
        stamps = {request_id: stamp for request_id, stamp in conn.execute(query)}
    for row in rows:
        stamp = stamps.get(row.get("request_id"))
        if stamp is not None:
            row["updated_at"] = stamp.isoformat()
    return rows


def _load_plans(plan_ids) -> dict:
    from swingbot.core.planning.plan_store import PlanStore
    store = PlanStore()
    plans = {plan_id: store.get(plan_id) for plan_id in plan_ids if plan_id}
    return {plan_id: plan for plan_id, plan in plans.items() if plan is not None}


def _load_sectors() -> dict | None:
    from swingbot import config
    from swingbot.core.marketdata import universe
    try:
        return universe.sector_map(getattr(config, "SCAN_UNIVERSE", "watchlist") or "watchlist")
    except Exception as exc:  # the report still prints; clusters read "unknown"
        print(f"sector map unavailable ({exc}); clusters read 'unknown'", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="eToro demo mirror parity report (v160)")
    parser.add_argument("--json", metavar="PATH", help="also write the report as JSON")
    args = parser.parse_args(argv)
    rows = _load_rows()
    plans = _load_plans({row.get("plan_id") for row in rows})
    plan_cutoff = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report = build_report(rows, plans, _load_sectors(), plan_cutoff)
    print(render(report))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/scripts/test_etoro_parity_report.py`
Expected: PASS, `0 failed`, `0 xfailed`, and `test_load_rows_attaches_updated_at_from_the_table` passed, not skipped.

Run: `python -m radon cc -s -n C "$WT/scripts/reports/etoro_parity_report.py"`
Expected: no output.

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py`
Expected: PASS (still no eToro import, host string or key name in the report).

Run (manual smoke against the worktree's db-test, optional): `python "$WT/scripts/reports/etoro_parity_report.py"`
Expected: a `Snapshot: broker_orders rows=0, max updated_at=none, ...` line, the caveat, `N=0` everywhere, `Skips by reason` / `Trades` both `none`, exit 0. A connection error here only means no local database; the DB test above is the gate.

- [ ] **Step 6: Commit**

```bash
git -C "$WT" add scripts/reports/etoro_parity_report.py tests/scripts/test_etoro_parity_report.py
git -C "$WT" commit -m "feat(v160): EM12 -- parity report pooled totals, snapshot, caveat and CLI

Pooled N and means (each over its non-None values, with its own n), dollar
totals, divergent and below -1R counts, split by direction, settlement type
and sector cluster; skip counts by reason; a snapshot header with the row
count, max updated_at and the plan-store cut-off; the execution-style caveat
on every run; --json.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
