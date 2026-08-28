# v61 part 1 — `commands/scanning.py` → `commands/scanning/`

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 1824-line `swingbot/commands/scanning.py` into a package of
six focused modules plus a facade, moving whole functions without editing any
body.

**Architecture:** `scanning.py` becomes `scanning/__init__.py` — the facade
that re-exports the verified external surface **and** imports every submodule
so decorator registration still fires on `from swingbot.commands import
scanning`. Moves go leaf-first so the package imports cleanly after every task.

**Tech Stack:** Python 3.11+, discord.py (`@tasks.loop`, `@bot.command`,
`@bot.event`), pytest.

**Read first:** `_0-index.md` in this directory — its Global Constraints C1–C7
apply to every task here and are not repeated below.

**Worktree:** `2026-08-25-v61-large-file-decomposition_1-commands-scanning`

---

## Global Constraints

All of `_0-index.md` §Global Constraints, plus one specific to this part:

**C8 — Registration must survive.** `bot.py:39` does
`from swingbot.commands import scanning   # noqa: F401` purely for side
effects. Seven `@bot.command`s, six `@tasks.loop`s, one `@bot.event` and one
`@on_config_reload` register at import time. If `__init__.py` fails to import
a submodule, those handlers silently vanish — the bot starts fine and simply
stops responding. Task 2 builds the test that makes this loud.

**Confirmed patch targets** (verified 2026-08-25; re-verify in Task 2). Every
one is reached as `scanning_mod.<name>` from tests, so under C2 its callers
must call through the module:

`_check_session_transition` · `_refresh_presence` · `_write_heartbeat` ·
`is_scan_paused` · `get_current_price` · `load_watchlist` · `bot`

**Hard couplings** — these pairs cannot be separated, because the decorator
references the other object by name at import time:

| Decorator | at line | Must live with |
|---|---|---|
| `@session_scan.error` on `_session_scan_error` | 800 | `session_scan` (610) |
| `@market_data_refresh.before_loop` on `_before_market_data_refresh` | 1413 | `market_data_refresh` (1338) |

---

## Target structure

| Module | Holds (current line) | ~lines |
|---|---|---|
| `runstate.py` | `_PAUSE_FILE`, `_HEARTBEAT_FILE`, `_TRIGGER_FILE`, `_MANUAL_CLOSE_QUEUE`, `_write_heartbeat` (161), `is_scan_paused` (181), `set_scan_paused` (190) | ~90 |
| `alerts.py` | `_ordered_alerts` (204), `digest_payload` (225), `_post_daily_digest` (238), `cap_alerts` (266), `route_channel_id` (277), `_simple_alert_channel` (297), `deep_scan_report` (323), `_send_alerts` (336) | ~250 |
| `presence.py` | `_WELCOME_MESSAGES` (57), `_GOODBYE_MESSAGES` (113), `_presence_text` (453), `_refresh_presence` (478), `_check_session_transition` (514), `_post_healthcheck` (568) | ~230 |
| `recap.py` | `_resolve_retrospective_channel` (1127), `_post_retrospective` (1160), `weekend_deep_scan` (1186) | ~130 |
| `commands.py` | `recap_cmd` (1488), `check_cmd` (1514), `_check_historical` (1685), `session_cmd` (1743), `status_cmd` (1758), `pause_cmd` (1780), `resume_cmd` (1795), `stop_cmd` (1807) | ~340 |
| `loops.py` | `session_scan` (610), `_refresh_snapshot_safely` (630), `_session_scan_tick` (638), `_session_scan_error` (800), `heartbeat` (815), `config_watcher` (839), `trade_monitor` (1031), `daily_recap` (1257), `weekend_deep_scan_task` (1305), `market_data_refresh` (1338), `_before_market_data_refresh` (1413), `_apply_scan_interval_change` (1421), `on_ready` (1436) | ~800 |
| `__init__.py` | facade: `__all__`, submodule imports, shared singletons | ~80 |

`loops.py` staying ~800 lines is expected and acceptable — it is a dense
scheduler layer of many medium functions, not one mega-function. Shrinking it
is Phase B work and explicitly not attempted here.

---

### Task 1: The move-purity checker

Tooling every later task depends on. Built first so no move is ever committed
unverified.

**Files:**
- Create: `scripts/dev/check_move_purity.py`
- Test: `tests/dev/test_check_move_purity.py`

**Interfaces:**
- Produces: `check_move_purity(old_source: str, new_source: str, symbols: list[str]) -> list[str]` — returns the names whose bodies differ. CLI: `python scripts/dev/check_move_purity.py <git-ref>:<old-path> <new-path> <symbol>...`, exit 1 and a report if any differ.

- [ ] **Step 1: Write the failing test**

```python
# tests/dev/test_check_move_purity.py
from scripts.dev.check_move_purity import check_move_purity

OLD = '''
import os

def alpha(a, b):
    """Docstring."""
    x = a + b
    return x

def beta():
    return 1
'''

NEW_CLEAN = '''
from .other import helper

def alpha(a, b):
    """Docstring."""
    x = a + b
    return x
'''

NEW_EDITED = '''
def alpha(a, b):
    """Docstring."""
    x = a - b          # body changed
    return x
'''


def test_pure_move_reports_nothing():
    assert check_move_purity(OLD, NEW_CLEAN, ["alpha"]) == []


def test_edited_body_is_reported():
    assert check_move_purity(OLD, NEW_EDITED, ["alpha"]) == ["alpha"]


def test_missing_symbol_is_reported():
    assert check_move_purity(OLD, NEW_CLEAN, ["beta"]) == ["beta"]
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python -m pytest tests/dev/test_check_move_purity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.dev.check_move_purity'`

- [ ] **Step 3: Implement**

Uses `ast` so formatting and import changes are invisible and only real body
edits register. Comments are absent from the AST, so a comment-only change
passes — acceptable, since C1's concern is behaviour.

```python
# scripts/dev/check_move_purity.py
"""Verify that a refactor moved functions without editing their bodies.

Used by the v61 decomposition plans (docs/superpowers/plans/). The move
invariant is that a relocated function's body is byte-identical; this
compares ASTs so that import-block and formatting differences around the
move are ignored while any change inside a body is reported.
"""
import argparse
import ast
import subprocess
import sys


def _bodies(source: str) -> dict:
    tree = ast.parse(source)
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = ast.dump(ast.Module(body=node.body, type_ignores=[]))
    return out


def check_move_purity(old_source: str, new_source: str, symbols: list) -> list:
    """Return the names in `symbols` whose body differs between the two sources."""
    old, new = _bodies(old_source), _bodies(new_source)
    differing = []
    for name in symbols:
        if name not in old or name not in new or old[name] != new[name]:
            differing.append(name)
    return differing


def _read_ref(spec: str) -> str:
    if ":" in spec:
        return subprocess.run(["git", "show", spec], capture_output=True,
                              text=True, check=True).stdout
    with open(spec, encoding="utf-8") as fh:
        return fh.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("old", help="git ref:path, e.g. HEAD:swingbot/commands/scanning.py")
    ap.add_argument("new", help="path to the new file on disk")
    ap.add_argument("symbols", nargs="+")
    args = ap.parse_args()

    bad = check_move_purity(_read_ref(args.old), _read_ref(args.new), args.symbols)
    if bad:
        print("MOVE NOT PURE -- these bodies differ or are missing:")
        for name in bad:
            print(f"  - {name}")
        return 1
    print(f"OK -- {len(args.symbols)} symbol(s) moved unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/dev/test_check_move_purity.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/dev/check_move_purity.py tests/dev/test_check_move_purity.py
git commit -m "tools(v61): AST-based move-purity checker for the decomposition plans"
```

---

### Task 2: Package skeleton, facade, and the registration guard

Converts the module to a package with everything still in one place, so this
task changes structure without moving a single function. Every later task is
then a pure move.

**Files:**
- Create: `swingbot/commands/scanning/__init__.py` (from the old file, unchanged content)
- Delete: `swingbot/commands/scanning.py`
- Create: `tests/commands/test_scanning_package.py`

**Interfaces:**
- Produces: the package `swingbot.commands.scanning`, importable exactly as before. No symbol moves yet.

- [ ] **Step 1: Re-verify the external surface**

Do not trust the spec's list. Run:

```bash
git grep -ohE "from swingbot\.commands\.scanning import [a-zA-Z_, ]+" -- '*.py' | sort -u
git grep -ohE "scanning_mod\.[a-zA-Z_]+|bot_module\.[a-zA-Z_]+" -- 'tests/' | sort -u
```

Record the union in the task's commit message. If it differs from the header's
list above, the header is stale — the grep wins.

- [ ] **Step 2: Write the registration guard test**

This is the test that makes C8 loud. It must fail if any submodule stops being
imported.

```python
# tests/commands/test_scanning_package.py
"""The scanning package registers its handlers purely as an import side
effect (bot.py:39). If __init__.py stops importing a submodule the bot still
starts and simply stops responding -- these tests make that loud."""
import importlib


EXPECTED_COMMANDS = {"recap", "check", "session", "status", "pause", "resume", "stop"}
EXPECTED_LOOPS = {
    "session_scan", "heartbeat", "config_watcher", "trade_monitor",
    "daily_recap", "weekend_deep_scan_task", "market_data_refresh",
}


def test_every_command_is_registered():
    from swingbot.bot_core import bot
    importlib.import_module("swingbot.commands.scanning")
    registered = {c.name for c in bot.commands}
    assert EXPECTED_COMMANDS <= registered, f"missing: {EXPECTED_COMMANDS - registered}"


def test_every_task_loop_is_reachable_on_the_facade():
    scanning = importlib.import_module("swingbot.commands.scanning")
    for name in EXPECTED_LOOPS:
        loop = getattr(scanning, name, None)
        assert loop is not None, f"{name} not exposed on the scanning facade"
        assert hasattr(loop, "start"), f"{name} is not a discord.py task loop"


def test_error_and_before_loop_handlers_are_attached():
    scanning = importlib.import_module("swingbot.commands.scanning")
    # @session_scan.error and @market_data_refresh.before_loop bind by name at
    # import time -- if their targets were split from their loops, these are None.
    assert scanning.session_scan._error is not None
    assert scanning.market_data_refresh._before_loop is not None
```

- [ ] **Step 3: Convert the module to a package**

Content is unchanged — this is a rename only.

```bash
mkdir swingbot/commands/scanning
git mv swingbot/commands/scanning.py swingbot/commands/scanning/__init__.py
```

- [ ] **Step 4: Run the guard test and the affected suites**

```bash
python scripts/dev/testrun.py file tests/commands/test_scanning_package.py
python scripts/dev/testrun.py file tests/test_trade_monitor_task.py
python scripts/dev/testrun.py file tests/test_market_data_refresh_task.py
```
Expected: all pass. They must pass **now**, before any move — that is what
makes them a regression net for Tasks 3–8.

- [ ] **Step 5: Commit**

```bash
git add -A swingbot/commands/scanning tests/commands/test_scanning_package.py
git commit -m "refactor(v61): make commands/scanning a package; add registration guard"
```

---

### Tasks 3–8: the moves

**These six tasks share one procedure.** It is written out once here and each
task below states only what differs. Read this block before starting any of
them.

For a task moving symbol set `S` into new module `M`:

1. **Create `swingbot/commands/scanning/<M>.py`.** Header docstring naming
   what the module owns and that it was split from `scanning.py` on
   2026-08-25. Then the import block it needs, then the moved symbols **in
   their original relative order**, bodies untouched.
2. **Delete those symbols from `__init__.py`.**
3. **Add `from . import <M>` to `__init__.py`**, and re-export any of `S` that
   is in the verified external surface: `from .<M> import name1, name2  # noqa: F401`.
4. **Fix callers.** Any remaining reference to a moved symbol resolves via
   `from . import <M>` then `<M>.name(...)` — per C2, **module-qualified, not
   bare-name**, for every symbol in this part's patch-target list. Bare
   `from .<M> import name` is permitted only for symbols never patched.
5. **Purity check:**
   ```bash
   python scripts/dev/check_move_purity.py \
     HEAD:swingbot/commands/scanning/__init__.py \
     swingbot/commands/scanning/<M>.py \
     <every symbol in S>
   ```
   Expected: `OK -- N symbol(s) moved unchanged`. Non-empty report ⇒ stop, the
   move was not pure.
6. **Run the task's narrow tests** (named per task below), plus
   `tests/commands/test_scanning_package.py` every time.
7. **Commit**, one commit for the task:
   `refactor(v61): move <concern> out of commands/scanning into <M>.py`

---

### Task 3: `runstate.py`

**Files:**
- Create: `swingbot/commands/scanning/runstate.py`
- Modify: `swingbot/commands/scanning/__init__.py`

**Interfaces:**
- Produces: `runstate.is_scan_paused() -> bool`, `runstate.set_scan_paused(paused: bool) -> None`, `runstate._write_heartbeat() -> None`, and the constants `_PAUSE_FILE`, `_HEARTBEAT_FILE`, `_TRIGGER_FILE`, `_MANUAL_CLOSE_QUEUE`.
- Consumes: nothing from earlier move tasks. Leaf module — do this one first.

**Symbols:** `_TRIGGER_FILE`, `_MANUAL_CLOSE_QUEUE`, `_PAUSE_FILE`,
`_HEARTBEAT_FILE`, `_write_heartbeat`, `is_scan_paused`, `set_scan_paused`

**Patch-target note:** `is_scan_paused` and `_write_heartbeat` are both
patched by tests. Every caller must use `runstate.is_scan_paused()`, never a
bare imported name.

**Narrow tests:**
```bash
python scripts/dev/testrun.py file tests/admin/test_api_v1_system_scan.py
python scripts/dev/testrun.py file tests/commands/test_scanning_package.py
```

`tests/admin/test_api_v1_system_scan.py` matters here specifically: its
docstring says it guards `app.py`'s `TRIGGER_FILE`/`PAUSE_FILE` against
`commands/scanning.py`'s. Those constants are moving, so this is the test that
catches a divergence.

---

### Task 4: `alerts.py`

**Files:**
- Create: `swingbot/commands/scanning/alerts.py`
- Modify: `swingbot/commands/scanning/__init__.py`

**Interfaces:**
- Produces: `alerts._ordered_alerts(alerts, today=None) -> list`, `alerts.digest_payload(plans, today, max_n) -> list`, `alerts.cap_alerts(items, max_alerts=None) -> tuple`, `alerts.route_channel_id(item) -> str`, `alerts.deep_scan_report(items) -> str`, `alerts._send_alerts(destination, alerts, route_by_confidence=False)`, `alerts._post_daily_digest(channel)`, `alerts._simple_alert_channel()`.
- Consumes: `runstate` (Task 3) if any alert path checks the pause flag.

**Symbols:** `_ordered_alerts`, `digest_payload`, `_post_daily_digest`,
`cap_alerts`, `route_channel_id`, `_simple_alert_channel`, `deep_scan_report`,
`_send_alerts`

**External surface — all six of these are imported by name from tests and
must be re-exported on the facade:** `_ordered_alerts`, `digest_payload`,
`cap_alerts`, `route_channel_id`, `deep_scan_report`, `_send_alerts`.

**Known trap:** `_send_alerts` returns a **4-tuple**. Commit `452864e` fixed
call sites that unpacked it into 3 names, which silently dropped every alert
on any scan over `MAX_ALERTS_PER_SCAN`. Do not "tidy" the unpacking at any
call site while moving.

**Narrow tests:**
```bash
python scripts/dev/testrun.py file tests/scanning/test_simple_alerts.py
python scripts/dev/testrun.py file tests/infra/test_silent_alerts_channel.py
python scripts/dev/testrun.py file tests/test_digest.py
python scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py
python scripts/dev/testrun.py file tests/marketdata/test_universe.py
python scripts/dev/testrun.py file tests/commands/test_scanning_package.py
```

---

### Task 5: `presence.py`

**Files:**
- Create: `swingbot/commands/scanning/presence.py`
- Modify: `swingbot/commands/scanning/__init__.py`

**Interfaces:**
- Produces: `presence._presence_text() -> str`, `presence._refresh_presence()`, `presence._check_session_transition(channel)`, `presence._post_healthcheck(channel, text)`, and the `_WELCOME_MESSAGES` / `_GOODBYE_MESSAGES` tuples.
- Consumes: `runstate.is_scan_paused` (Task 3) — `_presence_text` reports paused state.

**Symbols:** `_WELCOME_MESSAGES`, `_GOODBYE_MESSAGES`, `_presence_text`,
`_refresh_presence`, `_check_session_transition`, `_post_healthcheck`

**Patch-target note — the one most likely to break this part.** Both
`_refresh_presence` and `_check_session_transition` are monkeypatched by
tests, and both are **called from `_session_scan_tick`**, which moves to
`loops.py` in Task 8. Under C2, `loops.py` must call
`presence._refresh_presence()` through the module. If Task 8 instead writes
`from .presence import _refresh_presence`, the existing tests will pass while
patching nothing and the real Discord presence call will run. Re-read C2
before Task 8.

**Narrow tests:**
```bash
python scripts/dev/testrun.py file tests/commands/test_scanning_package.py
```
Plus any file the Task 2 grep showed patching `_refresh_presence` or
`_check_session_transition`.

---

### Task 6: `recap.py`

**Files:**
- Create: `swingbot/commands/scanning/recap.py`
- Modify: `swingbot/commands/scanning/__init__.py`

**Interfaces:**
- Produces: `recap._resolve_retrospective_channel(channel_id_override=None, *, caller="daily_recap")`, `recap._post_retrospective(channel_id_override=None, today=None)`, `recap.weekend_deep_scan() -> str`.
- Consumes: `alerts.deep_scan_report` (Task 4) — `weekend_deep_scan` formats through it.

**Symbols:** `_resolve_retrospective_channel`, `_post_retrospective`,
`weekend_deep_scan`

**Do not move** `daily_recap` (1257) or `weekend_deep_scan_task` (1305) — both
carry `@tasks.loop` and belong to `loops.py` in Task 8. This task moves the
*work* functions; the loops that call them move later. That split is
deliberate: it keeps every `@tasks.loop` in exactly one module.

**Narrow tests:**
```bash
python scripts/dev/testrun.py file tests/commands/test_scanning_package.py
```
Plus any retrospective test the Task 2 grep surfaced.

---

### Task 7: `commands.py`

**Files:**
- Create: `swingbot/commands/scanning/commands.py`
- Modify: `swingbot/commands/scanning/__init__.py`

**Interfaces:**
- Produces: the seven `@bot.command` coroutines `recap_cmd`, `check_cmd`, `session_cmd`, `status_cmd`, `pause_cmd`, `resume_cmd`, `stop_cmd`, plus helper `_check_historical(ctx, horizon, date_from, date_to)`.
- Consumes: `runstate.set_scan_paused` (Task 3), `alerts._send_alerts` (Task 4), `recap._post_retrospective` (Task 6).

**Symbols:** `recap_cmd`, `check_cmd`, `_check_historical`, `session_cmd`,
`status_cmd`, `pause_cmd`, `resume_cmd`, `stop_cmd`

**External surface:** `check_cmd` is imported directly by
`swingbot/commands/slash.py:238` (`from swingbot.commands.scanning import
check_cmd`). It must be re-exported on the facade or the slash-command layer
breaks.

**Narrow tests:**
```bash
python scripts/dev/testrun.py file tests/commands/test_scanning_package.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_system_scan.py
```

The registration guard from Task 2 is the real test here: it asserts all seven
command names are on the bot.

---

### Task 8: `loops.py`

The big one, and last, because everything else must already be in place.

**Files:**
- Create: `swingbot/commands/scanning/loops.py`
- Modify: `swingbot/commands/scanning/__init__.py`

**Interfaces:**
- Produces: `loops.session_scan`, `loops.heartbeat`, `loops.config_watcher`, `loops.trade_monitor`, `loops.daily_recap`, `loops.weekend_deep_scan_task`, `loops.market_data_refresh` (all `discord.ext.tasks.Loop` objects), plus `loops.on_ready`, `loops._session_scan_tick`, `loops._refresh_snapshot_safely`, `loops._apply_scan_interval_change`.
- Consumes: every module from Tasks 3–7.

**Symbols, in original order:** `session_scan`, `_refresh_snapshot_safely`,
`_session_scan_tick`, `_session_scan_error`, `heartbeat`, `config_watcher`,
`trade_monitor`, `daily_recap`, `weekend_deep_scan_task`,
`market_data_refresh`, `_before_market_data_refresh`,
`_apply_scan_interval_change`, `on_ready`

- [ ] **Step 1: Move the pairs together**

`_session_scan_error` carries `@session_scan.error` and
`_before_market_data_refresh` carries `@market_data_refresh.before_loop`.
Both resolve their target **by name at import time**, so each must appear in
`loops.py` *after* its loop, in the original order. Keeping the original
relative order of all thirteen symbols satisfies this automatically — which is
why the procedure requires it.

- [ ] **Step 2: Apply C2 to every patched symbol**

`loops.py` is the biggest consumer of this part's patch targets. Every one of
these must be module-qualified:

```python
from . import alerts, presence, runstate

# in _session_scan_tick and friends:
await presence._check_session_transition(channel)
await presence._refresh_presence()
runstate._write_heartbeat()
if runstate.is_scan_paused():
    ...
```

Bare `from .presence import _refresh_presence` here is the single most likely
way to break this part silently. It will not fail a test — it will make tests
that think they are patching pass while the real function runs.

- [ ] **Step 3: Preserve the decoration-time interval read**

`@tasks.loop(minutes=config.SCAN_INTERVAL_MINUTES)` (line 610) and
`@tasks.loop(minutes=config.MARKET_DATA_REFRESH_MINUTES)` (1338) read config
**at decoration time**. `swingbot/bot_core.py:244` documents this. The
`from swingbot import config` in `loops.py` must therefore be a module import,
never `from swingbot.config import SCAN_INTERVAL_MINUTES`, or the value freezes
differently than before and `_apply_scan_interval_change` stops working.

- [ ] **Step 4: Purity check**

```bash
python scripts/dev/check_move_purity.py \
  HEAD:swingbot/commands/scanning/__init__.py \
  swingbot/commands/scanning/loops.py \
  session_scan _refresh_snapshot_safely _session_scan_tick _session_scan_error \
  heartbeat config_watcher trade_monitor daily_recap weekend_deep_scan_task \
  market_data_refresh _before_market_data_refresh _apply_scan_interval_change on_ready
```
Expected: `OK -- 13 symbol(s) moved unchanged`

- [ ] **Step 5: Narrow tests**

```bash
python scripts/dev/testrun.py file tests/test_trade_monitor_task.py
python scripts/dev/testrun.py file tests/test_market_data_refresh_task.py
python scripts/dev/testrun.py file tests/commands/test_scanning_package.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_system_scan.py
```

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/loops.py swingbot/commands/scanning/__init__.py
git commit -m "refactor(v61): move the task-loop scheduler layer into loops.py"
```

---

### Task 9: Facade cleanup and full verification

**Files:**
- Modify: `swingbot/commands/scanning/__init__.py`

- [ ] **Step 1: Reduce `__init__.py` to a facade**

What remains should be only: the module docstring, the submodule imports, the
shared singletons (C4), `__all__`, and the re-exports. If any function body is
still here, it was missed — move it.

```python
"""Discord command layer for scanning.

Split from the 1824-line commands/scanning.py on 2026-08-25 (v61). This module
is the facade: it re-exports the external surface and, critically, imports
every submodule so that decorator registration still fires on
`from swingbot.commands import scanning` (bot.py:39).
"""
from . import runstate, alerts, presence, recap, commands, loops  # noqa: F401

from .runstate import is_scan_paused, set_scan_paused  # noqa: F401
from .alerts import (  # noqa: F401
    _ordered_alerts, digest_payload, cap_alerts, route_channel_id,
    deep_scan_report, _send_alerts,
)
from .commands import check_cmd  # noqa: F401
from .loops import (  # noqa: F401
    session_scan, heartbeat, config_watcher, trade_monitor, daily_recap,
    weekend_deep_scan_task, market_data_refresh, on_ready,
)

__all__ = [
    "is_scan_paused", "set_scan_paused",
    "_ordered_alerts", "digest_payload", "cap_alerts", "route_channel_id",
    "deep_scan_report", "_send_alerts", "check_cmd",
    "session_scan", "heartbeat", "config_watcher", "trade_monitor",
    "daily_recap", "weekend_deep_scan_task", "market_data_refresh", "on_ready",
]
```

Reconcile this list against the Task 2 grep. If Task 2 found a symbol not
listed here, add it — the grep is authoritative, this block is a starting
point.

- [ ] **Step 2: Verify no submodule imports the facade (C3)**

```bash
git grep -n "from swingbot.commands.scanning import\|from . import scanning" -- swingbot/commands/scanning/
```
Expected: no matches. Any hit is an import cycle waiting to happen.

- [ ] **Step 3: Confirm the line-count goal was met**

```bash
wc -l swingbot/commands/scanning/*.py
```
Expected: `__init__.py` under ~80 lines; no module over ~850; total within
~50 lines of the original 1824 (moves neither add nor remove code).

- [ ] **Step 4: Full suite — dispatch, do not run inline**

Dispatch the `test-runner` subagent with:
`python scripts/dev/testrun.py full`

Expected: `0 failed, 0 xfailed`, pass count within a handful of the baseline
recorded in Task 2. **A new `xfailed` is a failure.** If anything is red, that
is where the fixing starts — do not proceed to merge.

- [ ] **Step 5: Commit and finish the branch**

```bash
git add swingbot/commands/scanning/__init__.py
git commit -m "refactor(v61): reduce commands/scanning to a facade; part 1 complete"
```

Then merge to `main` and remove the worktree and its branch per
`docs/claude/document-lifecycle.md`. Per `CLAUDE.md`, **do not re-run the
suite after merging** — the branch was already green; only a merge that
resolved conflicts earns another run.
