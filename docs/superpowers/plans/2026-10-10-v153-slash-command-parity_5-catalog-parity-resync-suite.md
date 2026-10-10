# v153 Slash command parity. Part 5: help catalog, parity test, superseded tests, resync script, tip date, full suite

**Spec:** `docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md`
**Bump:** bot minor
**Edge:** none (integrity)
**Index:** `docs/superpowers/plans/2026-10-10-v153-slash-command-parity_0-index.md`. Global Constraints, Parallelisation and the task ledger live there and are binding here. Read `## Global Constraints` before any task.

These six tasks run **after every module task (SP5–SP16) has landed**. Order: SP17, SP18, then SP19 and SP20 in parallel (disjoint files), then SP21, then SP22.

**Shared conventions for this part** (they restate the index; the index wins on any conflict):

- `$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v153-slash-command-parity`. Never `cd`; use `git -C $WT` and absolute paths. Python commands that import the package run with `PYTHONPATH=$WT`.
- Consumed from SP1 (`swingbot/commands/reply.py`): `SLASH_TWIN`, `PREFIX_TIP_UNTIL`, `prefix_tip`, `send_prefix_tip`, `_today`, `CtxReply`, `InteractionReply`. From SP1's harness: `ParityCase`, `run_both`, `comparable`.
- Consumed from SP4: `SLASH_ONLY` in `swingbot/commands/notify.py`, **only if v152 landed** (then `bot.py` imports `notify`). SP18 reads `SLASH_ONLY` off whatever module defines it, so it needs no branch of its own.
- Consumed from SP7: `growth.slash_killswitch`. From SP9: `info.HELP_DESCRIPTION`, `info.handle_help`, and the `info_help` parity case with its `_freeze_clock` stub.
- `send_error` answers carry no tip. `ui.apply_chrome` stamps `discord.utils.utcnow()` on an embed; a test that builds a chromed embed twice and compares them freezes that clock.
- Narrow test runs only: `python $WT/scripts/dev/testrun.py file <test>`. The full suite runs once, in SP22.
- **discord.py must be installed** where the tests run (index, "Where to work").

# Phase 5: Catalog, parity, rollback remedy, close

### Task SP17: Help catalog lists slash forms within Discord embed limits

**Model:** sonnet — one renderer inside `info.py` plus a comment in `bot_core.py`; the behaviour (row format, split rule, limits) is fixed by the ledger and Controller decision 4.

**Files:**
- Modify: `swingbot/bot_core.py` (comment above `COMMANDS_BY_CATEGORY`, line 79 today; no row changes)
- Modify: `swingbot/commands/info.py` (SP9's `_help_embed` and `handle_help`; one import line)
- Create: `tests/commands/test_help_catalog.py`
- Modify: `tests/commands/test_stats_commands.py` (`test_help_catalog_covers_analytics_and_plans` gains the `!`-first assertion)

**Interfaces:**
- Consumes (SP1): `SLASH_TWIN`; harness `run_both`, `comparable`. Consumes (SP9): `info.HELP_DESCRIPTION`, `info.handle_help`, the `info_help` parity case.
- Produces (ledger): `info.help_line(usage: str, desc: str) -> str` and `info.help_embeds() -> list[discord.Embed]`. Also, used only inside `info.py` and its test: `info.help_fields() -> list[tuple[str, str]]`, `info._field_chunks(lines, limit=FIELD_VALUE_LIMIT) -> list[str]`, and the constants `FIELD_VALUE_LIMIT = 1024`, `EMBED_FIELD_LIMIT = 25`, `EMBED_TOTAL_LIMIT = 6000`, `HELP_TITLE`.
- Row format: `` `!usage` · `/twin` — desc``. `twin` is `SLASH_TWIN[key]` for the **longest** key that equals the usage's leading words (`!trades clear` → `trades clear` → `/trades-clear`; `!trade ID` → `trade` → `/trade show`). A row with no matching key renders as `` `!usage` — desc`` (none exists today; a test pins that).
- Split rule: a category whose rows exceed 1024 chars continues in a field named `"<category> (cont.)"`, breaking only between rows. Fields are packed into embeds of at most 25 fields and 6000 chars (`len(embed)`, which counts title, description, field names and values, and the footer). The first embed carries `HELP_TITLE` and `HELP_DESCRIPTION`; any further embed is titled `HELP_TITLE + " (cont.)"`. Every embed gets `ui.apply_chrome`.
- Output change (index, Global Constraints item 3): `!help`/`!commands` and `/help` show each row's slash form. "📊 Trades & performance" is 1262 chars with slash forms (1116 today, already over the cap), so it becomes two fields. All 9 categories fit one embed today (about 5,400 chars); the multi-embed path is still built and tested.
- Not in scope: `COMMANDS_BY_CATEGORY` still omits `!recap`, `!soak`, `!growth`, `!killswitch`, `!portfolio`, `!account maxpositionpct|maxposition|maxrisk` and `!trades clear history`, as it does today. The spec only asks for the slash form per row. Adding rows is a separate decision for the partner.

- [ ] **Step 0: Confirm every module task landed**

```bash
git -C $WT grep -c "@bot.tree.command" -- swingbot/commands/slash.py
git -C $WT grep -n "def handle_help\|^HELP_DESCRIPTION\|def _help_embed" -- swingbot/commands/info.py
git -C $WT grep -n "def handle_check\|def handle_stop" -- swingbot/commands/scanning/commands.py
```

Expected: the first command prints `0` (or exits 1 with no output). The second shows `handle_help`, `HELP_DESCRIPTION` and `_help_embed`. The third shows both handlers. If not, stop and report `BLOCKED: SP9..SP16 not all landed`.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/commands/test_help_catalog.py`:

```python
"""v153 SP17: the help catalog shows each row's slash twin and fits
Discord's embed limits (field value <= 1024, <= 25 fields, <= 6000 chars)."""
import datetime as dt

import discord
import pytest

from swingbot.bot_core import COMMANDS_BY_CATEGORY
from swingbot.commands import info
from tests.commands.reply_harness import comparable, run_both

_NOW = dt.datetime(2026, 10, 9, 14, 30, tzinfo=dt.timezone.utc)
ROWS = [(usage, desc) for rows in COMMANDS_BY_CATEGORY.values() for usage, desc in rows]


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch):
    # ui.apply_chrome stamps utcnow(); two builds must compare equal.
    monkeypatch.setattr(discord.utils, "utcnow", lambda: _NOW)


@pytest.mark.parametrize("usage, desc, expected", [
    ("!ping", "Check bot latency", "`!ping` · `/ping` — Check bot latency"),
    ("!commands", "Show this list", "`!commands` · `/help` — Show this list"),
    ("!trades clear", "Delete ALL trade records",
     "`!trades clear` · `/trades-clear` — Delete ALL trade records"),
    ("!trades [open|win|loss|all] [per_page]", "x",
     "`!trades [open|win|loss|all] [per_page]` · `/trades` — x"),
    ("!trade delete ID", "x", "`!trade delete ID` · `/trade delete` — x"),
    ("!trade ID", "x", "`!trade ID` · `/trade show` — x"),
    ("!account", "x", "`!account` · `/account show` — x"),
    ("!account sizing risk|account", "x", "`!account sizing risk|account` · `/account sizing` — x"),
    ("!watchlist add TICKER", "x", "`!watchlist add TICKER` · `/watchlist add` — x"),
    ("!nosuchcommand ARG", "x", "`!nosuchcommand ARG` — x"),
])
def test_help_line(usage, desc, expected):
    assert info.help_line(usage, desc) == expected


def test_every_row_keeps_the_bang_form_first_and_has_a_slash_twin():
    for usage, desc in ROWS:
        assert usage.startswith("!"), usage
        assert info.help_line(usage, desc).startswith(f"`{usage}` · `/"), f"no slash twin for {usage!r}"


def test_every_embed_and_field_fits_discord_limits():
    for embed in info.help_embeds():
        assert len(embed.fields) <= info.EMBED_FIELD_LIMIT == 25
        assert len(embed) <= info.EMBED_TOTAL_LIMIT == 6000
        for field in embed.fields:
            assert 0 < len(field.value) <= info.FIELD_VALUE_LIMIT == 1024, field.name
            assert len(field.name) <= 256


def test_every_row_appears_once_and_in_order():
    rendered = "\n".join(field.value for embed in info.help_embeds() for field in embed.fields)
    assert rendered.split("\n") == [info.help_line(usage, desc) for usage, desc in ROWS]


def test_an_oversized_category_continues_in_a_cont_field():
    names = [field.name for embed in info.help_embeds() for field in embed.fields]
    # 1262 chars with slash forms (1116 before v153, already over 1024).
    assert "📊 Trades & performance (cont.)" in names
    for category in COMMANDS_BY_CATEGORY:
        assert names.count(category) == 1
    assert names[0] == next(iter(COMMANDS_BY_CATEGORY))


def test_first_embed_carries_the_title_and_both_prefixes():
    first = info.help_embeds()[0]
    assert first.title == info.HELP_TITLE == "📖 Swing Trade Bot — Commands"
    assert first.description == info.HELP_DESCRIPTION
    assert "Prefix: `!`" in first.description and "Slash: `/`" in first.description
    assert first.footer.text  # apply_chrome ran


def test_field_chunks_break_between_lines_only():
    assert info._field_chunks(["a" * 600, "b" * 400, "c" * 10], 1024) == [
        "a" * 600 + "\n" + "b" * 400, "c" * 10]
    assert info._field_chunks(["a" * 600, "b" * 600], 1024) == ["a" * 600, "b" * 600]
    assert info._field_chunks(["x" * 2000], 1024) == ["x" * 1023 + "…"]
    assert info._field_chunks([], 1024) == []


def test_help_spills_into_further_embeds_within_limits(monkeypatch):
    big = {f"Category {i:02d}": [("!ping", "d" * 900)] for i in range(30)}
    monkeypatch.setattr(info, "COMMANDS_BY_CATEGORY", big)
    embeds = info.help_embeds()
    assert len(embeds) >= 2
    assert all(embed.title == info.HELP_TITLE + " (cont.)" for embed in embeds[1:])
    assert all(embed.description is None for embed in embeds[1:])
    for embed in embeds:
        assert len(embed) <= 6000 and len(embed.fields) <= 25
    assert [field.name for embed in embeds for field in embed.fields] == list(big)


def test_handle_help_sends_every_embed_on_both_surfaces(monkeypatch):
    run = run_both(info.handle_help, monkeypatch)
    count = len(info.help_embeds())
    assert comparable(run.ctx_events) == comparable(run.inter_events)
    assert [event[0] for event in run.ctx_events] == ["send"] * count
    assert all(event[5] for event in run.inter_events)  # ephemeral on /help
    assert not run.ctx_reply.failed and not run.inter_reply.failed
```

- [ ] **Step 2: Run them to see them fail**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_help_catalog.py
```

Expected: failures with `AttributeError: module 'swingbot.commands.info' has no attribute 'help_line'` (and `help_embeds`, `HELP_TITLE`, `_field_chunks`).

- [ ] **Step 3: Replace `_help_embed` and `handle_help` in `info.py`**

In `$WT/swingbot/commands/info.py`, change the reply import line from

```python
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
```

to

```python
from swingbot.commands.reply import SLASH_TWIN, CtxReply, InteractionReply, send_prefix_tip
```

Directly under the `HELP_DESCRIPTION = ...` line, add:

```python
HELP_TITLE = "📖 Swing Trade Bot — Commands"
CONT = " (cont.)"

# Discord embed limits: a field value, the fields per embed, and the
# characters per embed (title + description + field names/values + footer).
FIELD_VALUE_LIMIT = 1024
EMBED_FIELD_LIMIT = 25
EMBED_TOTAL_LIMIT = 6000
```

Replace the whole `_help_embed` function with:

```python
def help_line(usage: str, desc: str) -> str:
    """One help row: the `!` form first, then its slash twin (v153).

    The twin comes only from SLASH_TWIN, for the longest key equal to the
    usage's leading words: `!trades clear` -> `trades clear` -> `/trades-clear`,
    `!trade ID` -> `trade` -> `/trade show`."""
    words = usage.lstrip("!").split()
    for n in range(len(words), 0, -1):
        twin = SLASH_TWIN.get(" ".join(words[:n]))
        if twin is not None:
            return f"`{usage}` · `/{twin}` — {desc}"
    return f"`{usage}` — {desc}"


def _clip(line: str, limit: int) -> str:
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _field_chunks(lines: list[str], limit: int = FIELD_VALUE_LIMIT) -> list[str]:
    """Join rows into field values of at most `limit` chars, breaking only between rows."""
    chunks: list[str] = []
    current = ""
    for line in (_clip(raw, limit) for raw in lines):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            candidate = line
        current = candidate
    if current:
        chunks.append(current)
    return chunks


def help_fields() -> list[tuple[str, str]]:
    """(name, value) per field; an oversized category continues as '<category> (cont.)'."""
    fields: list[tuple[str, str]] = []
    for category, rows in COMMANDS_BY_CATEGORY.items():
        chunks = _field_chunks([help_line(usage, desc) for usage, desc in rows])
        fields.extend((category if i == 0 else category + CONT, value) for i, value in enumerate(chunks))
    return fields


def _new_help_embed(first: bool) -> discord.Embed:
    if first:
        embed = discord.Embed(title=HELP_TITLE, description=HELP_DESCRIPTION)
    else:
        embed = discord.Embed(title=HELP_TITLE + CONT)
    ui.apply_chrome(embed, accent=ui.accent_for_outcome("scratch"))
    return embed


def _fits(embed: discord.Embed, name: str, value: str) -> bool:
    return (len(embed.fields) < EMBED_FIELD_LIMIT
            and len(embed) + len(name) + len(value) <= EMBED_TOTAL_LIMIT)


def help_embeds() -> list[discord.Embed]:
    """The help catalog as embeds within Discord's limits (chrome applied first,
    so len(embed) already counts the footer)."""
    embeds = [_new_help_embed(first=True)]
    for name, value in help_fields():
        if not _fits(embeds[-1], name, value):
            embeds.append(_new_help_embed(first=False))
        embeds[-1].add_field(name=name, value=value, inline=False)
    return embeds
```

Replace `handle_help` with:

```python
async def handle_help(reply) -> None:
    for embed in help_embeds():
        await reply.send(embed=embed, ephemeral=True)
```

Confirm nothing still calls the old builder:

```bash
grep -n "_help_embed\b" $WT/swingbot/commands/info.py
```

Expected: no output.

- [ ] **Step 4: Document the rule at `COMMANDS_BY_CATEGORY`**

In `$WT/swingbot/bot_core.py`, directly above `COMMANDS_BY_CATEGORY = {`, add:

```python
# Help catalog, rendered by swingbot/commands/info.py:help_embeds() for !help
# and /help. Each row is (usage, description) with the `!` form FIRST (v153):
# info.help_line() appends the slash twin from reply.SLASH_TWIN, so a row
# never spells out a `/` form itself. Rows are split into "(cont.)" fields to
# stay within Discord's 1024-char field limit.
```

No row changes.

- [ ] **Step 5: Pin the `!`-first rule in the existing catalog test**

In `$WT/tests/commands/test_stats_commands.py`, at the end of `test_help_catalog_covers_analytics_and_plans` (after its `for` loop), add:

```python
    # v153 (Controller decision 4): the `!` form stays first in every row, so
    # the first-word lookup above keeps working; info.help_line adds the `/` form.
    assert all(cmd.startswith("!") for cmds in COMMANDS_BY_CATEGORY.values() for cmd, _ in cmds)
```

- [ ] **Step 6: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_help_catalog.py
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_stats_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_views.py
```

Expected: every run `0 failed`, `0 xfailed`. In `test_reply_parity.py`, the `info_help` case still passes. Its `expect="send"` means at least one send and no edit, and one embed today is one send.

- [ ] **Step 7: Check the real sizes**

```bash
PYTHONPATH=$WT python -c "from swingbot.commands import info; es = info.help_embeds(); print(len(es), [len(e) for e in es], max(len(f.value) for e in es for f in e.fields))"
```

Expected: `1 [~5400] <=1024`. Paste the line into the task report.

- [ ] **Step 8: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/commands/info.py $WT/swingbot/bot_core.py
```

Expected: no line for `info.py`. This task adds only a comment to `bot_core.py`, so any line it prints was there before (`on_command_error` and friends are unchanged). Paste the output into the report.

- [ ] **Step 9: Commit**

```bash
git -C $WT add swingbot/bot_core.py swingbot/commands/info.py tests/commands/test_help_catalog.py tests/commands/test_stats_commands.py
git -C $WT commit -m "feat(v153): SP17 help catalog shows each row's slash twin, split within Discord embed limits"
```

### Task SP18: Slash parity test and shared module list

**Model:** sonnet — one small parser module and one offline test file over the registered command objects; every rule is spelled out by the spec's "Parity test" section and the ledger.

**Files:**
- Create: `swingbot/commands/modules.py`
- Create: `tests/commands/test_slash_parity.py`

**Interfaces:**
- Consumes (SP1): `SLASH_TWIN`, `PREFIX_TIP_UNTIL`, `prefix_tip`. Consumes (SP7): `growth.slash_killswitch`. Consumes (SP4, if v152 landed): `SLASH_ONLY` on `swingbot.commands.notify`. Consumes every module task's prefix commands and twins as registered on `bot` / `bot.tree`.
- Produces (ledger): `modules.BOT_PY: Path`, `modules.bot_command_modules(bot_py: Path = BOT_PY) -> list[str]` (dotted names parsed from `^from swingbot\.commands import (\w+)` lines of `bot.py`), `modules.import_bot_command_modules(bot_py: Path = BOT_PY) -> list[ModuleType]`. SP20 imports the last one.
- Not duplicated here (SP16 owns them, controller note): "no `@bot.tree.command` left in `slash.py`" and "no `from_interaction` anywhere under `swingbot/commands/`" (SP16's v153 block in `tests/commands/test_commands_check.py`: `test_scanning_twins_live_in_commands_py_and_slash_py_holds_none`, `test_no_context_bridge_is_left_in_the_commands_package`). This file covers the spec's parity points 1–5.
- One-body rule, as tested. The spec's "called by exactly one prefix and one slash command" has one built-in exception, `handle_watchlist`: four prefix commands (`watchlist`, `add`, `remove`, `clear`) call it, and so does the one choice-dispatched `/watchlist`. So the test asserts the rule in a form that holds for every command:
  - (a) every prefix callback calls exactly one `handle_*`, and so does every slash callback;
  - (b) for every prefix command, the slash command that its `SLASH_TWIN` row resolves to calls **the same** handler;
  - (c) every `handle_*` defined under `swingbot.commands` has exactly one slash caller, and at least one prefix caller unless its slash command is in `SLASH_ONLY`.

  Together these give no duplicated body on either surface, and every pair shares one body.

- [ ] **Step 0: Confirm SP17 landed**

```bash
git -C $WT grep -n "def help_embeds\|def help_line" -- swingbot/commands/info.py
git -C $WT grep -n "def slash_killswitch" -- swingbot/commands/growth.py
git -C $WT grep -n "SLASH_ONLY" -- swingbot/commands/
```

Expected: two hits and one hit. The `SLASH_ONLY` grep is empty unless v152 landed (then one hit in `notify.py`). Otherwise `BLOCKED: SP7/SP17 missing`.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/commands/test_slash_parity.py`:

```python
"""v153 SP18: prefix <-> slash parity over exactly what bot.py registers.

1. Mapping: every qualified prefix name is a SLASH_TWIN key (and back), and
   every SLASH_TWIN value resolves to a command path in bot.tree.
2. One body: each prefix command and its twin call the same handle_*.
3. Sync payload: cmd.to_dict(bot.tree) -- the JSON tree.sync() sends --
   within Discord's limits, so a rejected sync fails here, not as a WARNING
   in on_ready (loops.py:1048-1049) that is never retried.
4. Tip helper over every prefix name.
5. /killswitch is the only admin-gated command, guild-only, with a runtime check.
Offline: no gateway, no HTTP.
"""
import ast
import collections
import datetime as dt
import inspect
import json
import re
import sys
import textwrap
from unittest.mock import MagicMock

import discord
import pytest
from discord import app_commands

from swingbot.bot_core import bot
from swingbot.commands import modules
from swingbot.commands.reply import PREFIX_TIP_UNTIL, SLASH_TWIN, prefix_tip

MODULES = modules.import_bot_command_modules()
MODULE_NAMES = [module.__name__ for module in MODULES]
SLASH_ONLY: set[str] = set().union(*(getattr(module, "SLASH_ONLY", set()) for module in MODULES))
EXPECTED_TOP_LEVEL = 41 + len(SLASH_ONLY)   # 19 existing + 22 new (+ /notify if v152 landed)
NAME_RE = re.compile(r"^[-_a-z0-9]{1,32}$")
SUBCOMMAND_TYPES = (1, 2)   # SUB_COMMAND, SUB_COMMAND_GROUP


# ── helpers ─────────────────────────────────────────────────────────────

def _prefix_commands() -> dict:
    return {command.qualified_name: command for command in bot.walk_commands()}


def _slash_commands() -> list:
    return [command for command in bot.tree.walk_commands() if isinstance(command, app_commands.Command)]


def _action_values(command) -> set:
    param = next((p for p in command.parameters if p.name == "action"), None)
    return {choice.value for choice in (param.choices if param else [])}


def _resolve(path: str):
    """A SLASH_TWIN value -> the app command that answers it, or None."""
    head, _, rest = path.partition(" ")
    command = bot.tree.get_command(head)
    if isinstance(command, app_commands.Group):
        return command.get_command(rest) if rest else None
    if command is None or not rest:
        return command
    return command if rest in _action_values(command) else None


def _called_names(func, prefix: str) -> list[str]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
            if name.startswith(prefix):
                names.append(name)
    return names


def _handler_of(func) -> tuple[str, str]:
    found = set(_called_names(func, "handle_"))
    assert len(found) == 1, (
        f"{func.__module__}.{func.__qualname__} calls {sorted(found) or 'no handler'}; expected exactly one")
    return func.__module__, found.pop()


def _defined_handlers() -> set[tuple[str, str]]:
    found = set()
    for name, module in list(sys.modules.items()):
        if module is None or not name.startswith("swingbot.commands"):
            continue
        for attr, obj in vars(module).items():
            if attr.startswith("handle_") and inspect.iscoroutinefunction(obj) and obj.__module__ == name:
                found.add((name, attr))
    return found


def _root_name(command) -> str:
    return command.qualified_name.split()[0]


# ── 0. the module list comes from bot.py ────────────────────────────────

def test_bot_command_modules_reads_bot_py():
    names = modules.bot_command_modules()
    assert "swingbot.commands.slash" in names
    assert "swingbot.commands.scanning" in names
    assert len(names) == len(set(names)) >= 12


def test_bot_command_modules_parses_only_command_imports(tmp_path):
    fake = tmp_path / "bot.py"
    fake.write_text(
        "from swingbot.commands import scanning   # noqa: F401\n"
        "from swingbot.commands import watchlist  # noqa: F401\n"
        "    from swingbot.commands import indented\n"
        "from swingbot.core import other\n",
        encoding="utf-8",
    )
    assert modules.bot_command_modules(fake) == ["swingbot.commands.scanning", "swingbot.commands.watchlist"]


def test_every_registered_command_comes_from_a_bot_py_module():
    def from_listed(func) -> bool:
        return any(func.__module__ == m or func.__module__.startswith(m + ".") for m in MODULE_NAMES)

    strays = [c.qualified_name for c in bot.walk_commands() if not from_listed(c.callback)]
    strays += ["/" + c.qualified_name for c in _slash_commands() if not from_listed(c.callback)]
    assert not strays, f"registered outside bot.py's command modules: {strays}"


# ── 1. mapping ──────────────────────────────────────────────────────────

def test_slash_twin_keys_are_exactly_the_prefix_commands():
    walked = set(_prefix_commands())
    assert walked - set(SLASH_TWIN) == set(), "prefix commands with no SLASH_TWIN row"
    assert set(SLASH_TWIN) - walked == set(), "SLASH_TWIN rows with no prefix command"


@pytest.mark.parametrize("name, path", sorted(SLASH_TWIN.items()))
def test_every_twin_path_resolves_in_the_tree(name, path):
    assert _resolve(path) is not None, f"!{name} -> /{path} is not a command path in bot.tree"


def test_top_level_set_is_the_twins_plus_slash_only():
    top = {command.name for command in bot.tree.get_commands()}
    assert top == {path.split()[0] for path in SLASH_TWIN.values()} | SLASH_ONLY
    assert len(bot.tree.get_commands()) == EXPECTED_TOP_LEVEL <= 100


# ── 2. one body ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(SLASH_TWIN))
def test_prefix_command_and_its_twin_call_the_same_handler(name):
    prefix = _prefix_commands()[name]
    twin = _resolve(SLASH_TWIN[name])
    assert _handler_of(prefix.callback) == _handler_of(twin.callback)


@pytest.mark.parametrize("name", sorted(SLASH_TWIN))
def test_every_prefix_command_sends_the_tip(name):
    callback = _prefix_commands()[name].callback
    assert _called_names(callback, "send_prefix_tip") == ["send_prefix_tip"], name


def test_every_handler_has_one_slash_caller_and_a_prefix_caller():
    slash_callers = collections.Counter(_handler_of(c.callback) for c in _slash_commands())
    prefix_callers = collections.Counter(_handler_of(c.callback) for c in bot.walk_commands())
    slash_only = {_handler_of(c.callback) for c in _slash_commands() if _root_name(c) in SLASH_ONLY}
    handlers = _defined_handlers()
    assert handlers, "no handle_* found under swingbot.commands"
    assert set(slash_callers) <= handlers and set(prefix_callers) <= handlers
    for handler in sorted(handlers):
        assert slash_callers[handler] == 1, f"{handler}: {slash_callers[handler]} slash callers"
        if handler not in slash_only:
            assert prefix_callers[handler] >= 1, f"{handler}: no prefix caller"


# ── 3. sync payload ─────────────────────────────────────────────────────

def _payloads() -> list[dict]:
    return [command.to_dict(bot.tree) for command in bot.tree.get_commands()]


def _name_and_description_problems(node: dict, where: str) -> list[str]:
    problems = []
    if not NAME_RE.match(node["name"]):
        problems.append(f"{where}: name {node['name']!r} breaks ^[-_a-z0-9]{{1,32}}$")
    if not 1 <= len(node.get("description") or "") <= 100:
        problems.append(f"{where}: description must be 1-100 chars")
    return problems


def _parameter_problems(params: list[dict], where: str) -> list[str]:
    problems = []
    for param in params:
        problems += _name_and_description_problems(param, f"{where} {param['name']}")
        choices = param.get("choices") or []
        if len(choices) > 25:
            problems.append(f"{where} {param['name']}: {len(choices)} choices > 25")
        problems += [f"{where} {param['name']}: choice name {c['name']!r} not 1-100 chars"
                     for c in choices if not 1 <= len(c["name"]) <= 100]
    required = [bool(param.get("required")) for param in params]
    if required != sorted(required, reverse=True):
        problems.append(f"{where}: a required option follows an optional one")
    return problems


def _payload_problems(node: dict, where: str) -> list[str]:
    problems = _name_and_description_problems(node, where)
    options = node.get("options") or []
    if len(options) > 25:
        problems.append(f"{where}: {len(options)} options/subcommands > 25")
    subs = [option for option in options if option["type"] in SUBCOMMAND_TYPES]
    params = [option for option in options if option["type"] not in SUBCOMMAND_TYPES]
    if subs and params:
        problems.append(f"{where}: mixes subcommands and options")
    problems += _parameter_problems(params, where)
    for sub in subs:
        problems += _payload_problems(sub, f"{where} {sub['name']}")
    return problems


def test_sync_payload_is_within_discord_limits():
    payloads = _payloads()
    problems = [p for payload in payloads for p in _payload_problems(payload, "/" + payload["name"])]
    assert not problems, "\n".join(problems)
    assert len(payloads) <= 100
    json.dumps(payloads)  # what tree.sync() posts must serialise


def test_payload_checker_catches_bad_shapes():
    bad = {"name": "Bad Name", "description": "", "type": 1, "options": [
        {"name": "opt", "description": "x", "type": 3, "required": False},
        {"name": "req", "description": "x", "type": 3, "required": True,
         "choices": [{"name": str(i), "value": str(i)} for i in range(26)]},
    ]}
    problems = "\n".join(_payload_problems(bad, "/bad"))
    for fragment in ("name 'Bad Name'", "description must be", "26 choices", "required option follows"):
        assert fragment in problems


# ── 4. tip helper over every prefix name ────────────────────────────────

@pytest.mark.parametrize("name", sorted(SLASH_TWIN))
def test_prefix_tip_names_the_twin_until_the_cutoff(name):
    day_before = PREFIX_TIP_UNTIL - dt.timedelta(days=1)
    assert prefix_tip(name, day_before) == f"Tip: this is now /{SLASH_TWIN[name]}"
    assert prefix_tip(name, PREFIX_TIP_UNTIL) is None
    # "no tip after a handler error" is pinned in tests/commands/test_reply_parity.py (SP1).


# ── 5. /killswitch ──────────────────────────────────────────────────────

def test_killswitch_is_the_only_admin_gated_command_and_is_guild_only():
    from swingbot.commands.growth import slash_killswitch

    gated = {p["name"]: p["default_member_permissions"] for p in _payloads()
             if p.get("default_member_permissions") is not None}
    assert gated == {"killswitch": discord.Permissions(administrator=True).value}
    payload = slash_killswitch.to_dict(bot.tree)
    assert payload["dm_permission"] is False
    assert slash_killswitch.guild_only is True


def test_killswitch_check_rejects_a_non_admin_interaction():
    from swingbot.commands.growth import slash_killswitch

    interaction = MagicMock()
    interaction.permissions = discord.Permissions.none()
    with pytest.raises(app_commands.MissingPermissions):
        for check in slash_killswitch.checks:
            check(interaction)
```

- [ ] **Step 2: Run them to see them fail**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_parity.py
```

Expected: a collection error, `ImportError: cannot import name 'modules' from 'swingbot.commands'`.

- [ ] **Step 3: Write `modules.py`**

Create `$WT/swingbot/commands/modules.py`:

```python
"""The command modules the live bot registers, read from bot.py itself (v153).

Command modules register on the shared `bot` / `bot.tree` as an import side
effect, so "what the live bot serves" is exactly the set of modules bot.py
imports. The parity test (tests/commands/test_slash_parity.py) and the
rollback resync script (scripts/ops/resync_slash_commands.py) both read the
list from here, so neither can drift from bot.py.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path
from types import ModuleType

BOT_PY = Path(__file__).resolve().parents[2] / "bot.py"
_COMMAND_IMPORT = re.compile(r"^from swingbot\.commands import (\w+)", re.MULTILINE)


def bot_command_modules(bot_py: Path = BOT_PY) -> list[str]:
    """Dotted names of the command modules bot.py imports at top level, in file order."""
    text = Path(bot_py).read_text(encoding="utf-8")
    return [f"swingbot.commands.{name}" for name in _COMMAND_IMPORT.findall(text)]


def import_bot_command_modules(bot_py: Path = BOT_PY) -> list[ModuleType]:
    """Import every command module bot.py imports, registering its commands."""
    return [importlib.import_module(name) for name in bot_command_modules(bot_py)]
```

- [ ] **Step 4: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_parity.py
```

Expected: `0 failed`, `0 xfailed`. If a test fails, it has found a real gap in an earlier module task:
- a SLASH_TWIN row that does not resolve;
- a twin calling a different handler from its prefix command;
- a payload over a limit;
- a handler with two slash callers.

Report the failing id and the module it names. Do not loosen the test, and do not edit another task's module without the controller's go-ahead.

- [ ] **Step 5: Print the counts for the report**

```bash
PYTHONPATH=$WT python -c "from swingbot.commands import modules; modules.import_bot_command_modules(); from swingbot.bot_core import bot; print(len(bot.tree.get_commands()), sum(1 for _ in bot.walk_commands()))"
```

Expected: `41 53` (`42 53` if v152 landed). The second number counts every prefix command once; the `help` alias is not a separate command.

- [ ] **Step 6: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/commands/modules.py $WT/tests/commands/test_slash_parity.py
```

Expected: nothing printed. Paste `(none)` into the report.

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/commands/modules.py tests/commands/test_slash_parity.py
git -C $WT commit -m "test(v153): SP18 slash parity test (mapping, one body, sync payload limits, tip, /killswitch) and modules.py"
```

### Task SP19: Delete superseded registration tests

**Model:** haiku — deletions of named test functions fixed by the spec and Controller decision 3; no new code.

**Files:**
- Modify: `tests/commands/test_slash_commands.py` (delete `test_soak_slash_registered`)
- Modify: `tests/commands/test_stats_commands.py` (delete `test_new_slash_commands_registered_on_tree`, `test_slash_py_has_no_bang_command_channel_send_calls`, `BRIDGE_COMMANDS`, `test_six_bridge_commands_still_registered`, `test_bot_entrypoint_still_imports_the_slash_module`)

**Why each goes** (spec "Existing tests this supersedes"; brief §6; Controller decision 3):

| Test | Superseded by (SP18, `tests/commands/test_slash_parity.py`) |
|---|---|
| `test_soak_slash_registered` | `test_every_twin_path_resolves_in_the_tree` covers `/soak` and every other command |
| `test_new_slash_commands_registered_on_tree` | the same, for `/liveplans` `/top` `/stats` `/lessons` |
| `test_slash_py_has_no_bang_command_channel_send_calls` | stale: `slash.py` holds only choices and the error handler now. SP16 asserts that it holds no `@bot.tree.command` |
| `BRIDGE_COMMANDS` + `test_six_bridge_commands_still_registered` | the bridges are gone; registration is covered by the mapping tests |
| `test_bot_entrypoint_still_imports_the_slash_module` | `test_bot_command_modules_reads_bot_py` and `test_every_registered_command_comes_from_a_bot_py_module`: the parity test's import list is read from `bot.py` itself |

**Stays:** `test_slash_has_no_direct_colour` (`slash.py` still exists and must stay colour-free), `test_help_catalog_covers_analytics_and_plans` (SP17 extended it), `test_no_direct_chart_render_calls_outside_to_thread` with the module-level `import re` above it, and SP15's v153 block at the end of `test_stats_commands.py`.

Delete by **name**, not by line number: SP9–SP15 each added an `import swingbot.commands.<module>` line inside these functions, so today's line numbers (`:330-391`) have drifted.

- [ ] **Step 0: Confirm SP18 landed and is green**

```bash
git -C $WT grep -n "def test_every_twin_path_resolves_in_the_tree\|def test_bot_command_modules_reads_bot_py" -- tests/commands/test_slash_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_parity.py
```

Expected: two hits; `0 failed`. Otherwise `BLOCKED: SP18 missing or red` (never delete coverage before its replacement is green).

- [ ] **Step 1: Delete the functions with an AST-located script**

```bash
PYTHONPATH=$WT python - <<'PY'
import ast
from pathlib import Path

WT = Path("/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v153-slash-command-parity")
TARGETS = {
    "tests/commands/test_slash_commands.py": {"test_soak_slash_registered"},
    "tests/commands/test_stats_commands.py": {
        "test_new_slash_commands_registered_on_tree",
        "test_slash_py_has_no_bang_command_channel_send_calls",
        "BRIDGE_COMMANDS",
        "test_six_bridge_commands_still_registered",
        "test_bot_entrypoint_still_imports_the_slash_module",
    },
}


def node_name(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    return None


for rel, names in TARGETS.items():
    path = WT / rel
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    tree = ast.parse("".join(lines))
    spans = []
    for node in tree.body:
        if node_name(node) in names:
            start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
            spans.append((start, node.end_lineno, node_name(node)))
    found = {name for _, _, name in spans}
    assert found == names, f"{rel}: missing {sorted(names - found)}"
    for start, end, _ in sorted(spans, reverse=True):
        del lines[start - 1:end]
    text = "".join(lines)
    while "\n\n\n\n" in text:
        text = text.replace("\n\n\n\n", "\n\n\n")
    path.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
    print(rel, "deleted", sorted(found))
PY
```

Expected: two lines, `tests/commands/test_slash_commands.py deleted ['test_soak_slash_registered']` and the stats line listing all five names.

- [ ] **Step 2: Check what is left**

```bash
grep -n "^def test_\|^BRIDGE_COMMANDS\|^import re" $WT/tests/commands/test_slash_commands.py $WT/tests/commands/test_stats_commands.py | grep -n "slash_registered\|registered_on_tree\|bang_command\|BRIDGE\|bridge\|entrypoint\|no_direct_colour\|help_catalog\|chart_render\|import re"
python -m pyflakes $WT/tests/commands/test_slash_commands.py $WT/tests/commands/test_stats_commands.py 2>/dev/null || python -m py_compile $WT/tests/commands/test_slash_commands.py $WT/tests/commands/test_stats_commands.py
```

Expected: only `test_slash_has_no_direct_colour`, `test_help_catalog_covers_analytics_and_plans`, `import re` and `test_no_direct_chart_render_calls_outside_to_thread` remain among those names. pyflakes (or py_compile, if pyflakes is absent) reports nothing about the two files. If pyflakes flags an import that only the deleted tests used, remove that import too.

- [ ] **Step 3: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_stats_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_parity.py
```

Expected: every run `0 failed`, `0 xfailed`. The pass count drops by the five deleted tests; that is expected.

- [ ] **Step 4: Commit**

```bash
git -C $WT add tests/commands/test_slash_commands.py tests/commands/test_stats_commands.py
git -C $WT commit -m "test(v153): SP19 delete registration tests superseded by the slash parity test"
```

### Task SP20: `scripts/ops/resync_slash_commands.py` rollback remedy

**Model:** sonnet — one small ops script with offline tests; the discord.py behaviour it rests on is verified below and pinned by a test.

**Files:**
- Create: `scripts/ops/resync_slash_commands.py`
- Create: `tests/scripts/test_resync_slash_commands.py`

**Interfaces:**
- Consumes (SP18): `swingbot.commands.modules.import_bot_command_modules()`. Consumes `swingbot.bot_core.bot` and `swingbot.config.TOKEN`.
- Produces (ledger): `resync(bot, token: str) -> int` (async; the synced count) and `main() -> int` (exit code: `0` synced, `1` login or sync rejected, `2` no token).

**discord.py 2.7.1 facts this rests on** (read from the 2.7.1 wheel's source while writing this plan; Step 1's last test pins the first one against the installed version):
- `Client.login(token)` sets the application id that `tree.sync()` needs. It runs `data = await self.http.static_login(token)`, then `self._application = await self.application_info()`, then `if self._connection.application_id is None: self._connection.application_id = self._application.id` (`discord/client.py:679-683`). After that it calls `setup_hook()`; this repo defines none (`git grep -n setup_hook -- swingbot` is empty).
- `CommandTree.sync()` raises `MissingApplicationID` when the id is unset (`discord/app_commands/tree.py:1103-1104`). It then posts `[command.to_dict(tree) for command in commands]` through `bulk_upsert_global_commands` (`:1112-1116`). That is a bulk **overwrite**: the global set becomes exactly this image's commands.
- `login()` opens no gateway, so the script never fires `on_ready`, never answers a command, and does not disturb the running bot's gateway session. `async with bot:` runs `_async_setup_hook()` on entry and `close()` on exit.

- [ ] **Step 0: Confirm SP18 landed**

```bash
git -C $WT grep -n "def import_bot_command_modules" -- swingbot/commands/modules.py
PYTHONPATH=$WT python -c "import inspect, discord; print(discord.__version__); print('self._connection.application_id = self._application.id' in inspect.getsource(discord.Client.login))"
```

Expected: one hit; then `2.7.1` and `True`. If `False`, stop and report `BLOCKED: installed discord.py's login() no longer sets application_id`.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/scripts/test_resync_slash_commands.py`:

```python
"""scripts/ops/resync_slash_commands.py (v153 rollback remedy): offline.

A fake bot stands in for discord's Client: no login, no HTTP."""
import asyncio
import inspect
import sys
from pathlib import Path

import discord
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import resync_slash_commands as rs  # noqa: E402


class _FakeTree:
    def __init__(self, calls: list, count: int):
        self._calls = calls
        self._count = count

    async def sync(self):
        self._calls.append("sync")
        return [object()] * self._count


class _FakeBot:
    def __init__(self, count: int = 41, login_error: Exception | None = None):
        self.calls: list[str] = []
        self.tree = _FakeTree(self.calls, count)
        self._login_error = login_error

    async def __aenter__(self):
        self.calls.append("enter")
        return self

    async def __aexit__(self, *exc):
        self.calls.append("close")

    async def login(self, token: str):
        self.calls.append(f"login:{token}")
        if self._login_error is not None:
            raise self._login_error


def test_resync_logs_in_then_syncs_then_closes():
    bot = _FakeBot(41)
    assert asyncio.run(rs.resync(bot, "tok")) == 41
    assert bot.calls == ["enter", "login:tok", "sync", "close"]


def test_resync_closes_the_client_when_login_fails():
    bot = _FakeBot(login_error=discord.LoginFailure("Improper token has been passed."))
    with pytest.raises(discord.LoginFailure):
        asyncio.run(rs.resync(bot, "tok"))
    assert bot.calls == ["enter", "login:tok", "close"]


def test_main_without_a_token_syncs_nothing(monkeypatch, capsys):
    from swingbot import config

    monkeypatch.setattr(config, "TOKEN", "")
    called = []
    monkeypatch.setattr(rs, "resync", lambda *args: called.append(args))
    assert rs.main() == 2
    assert called == []
    assert "DISCORD_TOKEN" in capsys.readouterr().err


def test_main_imports_bot_py_modules_and_prints_the_count(monkeypatch, capsys):
    from swingbot import config
    from swingbot.bot_core import bot
    import swingbot.commands.modules as modules

    imported = []
    monkeypatch.setattr(config, "TOKEN", "tok")
    monkeypatch.setattr(modules, "import_bot_command_modules", lambda: imported.append(1) or ["m"] * 12)
    seen = {}

    async def fake_resync(the_bot, token):
        seen.update(bot=the_bot, token=token)
        return 41

    monkeypatch.setattr(rs, "resync", fake_resync)
    assert rs.main() == 0
    assert imported == [1]
    assert seen == {"bot": bot, "token": "tok"}
    assert "Synced 41 slash command(s) to Discord from 12 command modules." in capsys.readouterr().out


def test_main_reports_a_rejected_login(monkeypatch, capsys):
    from swingbot import config
    import swingbot.commands.modules as modules

    monkeypatch.setattr(config, "TOKEN", "bad")
    monkeypatch.setattr(modules, "import_bot_command_modules", lambda: [])

    async def failing_resync(the_bot, token):
        raise discord.LoginFailure("Improper token has been passed.")

    monkeypatch.setattr(rs, "resync", failing_resync)
    assert rs.main() == 1
    assert "Sync failed: Improper token has been passed." in capsys.readouterr().err


def test_installed_discord_login_sets_the_application_id_sync_needs():
    """tree.sync() raises MissingApplicationID unless login() set it. Pinned
    against the installed discord.py so an upgrade cannot silently break the
    rollback remedy."""
    source = inspect.getsource(discord.Client.login)
    assert "self._connection.application_id = self._application.id" in source
```

- [ ] **Step 2: Run them to see them fail**

```bash
python $WT/scripts/dev/testrun.py file tests/scripts/test_resync_slash_commands.py
```

Expected: a collection error, `ModuleNotFoundError: No module named 'resync_slash_commands'`.

- [ ] **Step 3: Write the script**

Create `$WT/scripts/ops/resync_slash_commands.py`:

```python
#!/usr/bin/env python3
"""Re-sync Discord's global slash-command set to THIS image's commands.

v153 rollback remedy. on_ready syncs once per process start
(swingbot/commands/scanning/loops.py:1047). A failed sync is only a WARNING
(:1048-1049) and is never retried in-process, so a rollback whose sync
failed leaves the newer image's commands registered against an image that
no longer handles them.

This script imports the command modules bot.py imports
(swingbot.commands.modules), logs in with the bot token over HTTP only (no
gateway: it never fires on_ready, never answers a command, and leaves the
running bot's session alone) and calls bot.tree.sync(), which bulk-overwrites
the global set with the running image's commands. Idempotent.

Run on production:
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/ops/resync_slash_commands.py"
Fallback: docker compose restart bot (on_ready re-syncs on every start).

discord.py 2.7.1: Client.login() sets the application id tree.sync() needs;
tests/scripts/test_resync_slash_commands.py pins that.

Exit codes: 0 synced, 1 login or sync rejected, 2 DISCORD_TOKEN not set.
"""
from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


async def resync(bot, token: str) -> int:
    """Log in without the gateway, bulk-overwrite the global set, close. Returns the synced count."""
    async with bot:
        await bot.login(token)
        synced = await bot.tree.sync()
    return len(synced)


def main() -> int:
    import discord

    from swingbot import config
    from swingbot.bot_core import bot
    from swingbot.commands.modules import import_bot_command_modules

    if not config.TOKEN:
        print("DISCORD_TOKEN is not set; nothing synced.", file=sys.stderr)
        return 2
    loaded = import_bot_command_modules()
    try:
        count = asyncio.run(resync(bot, config.TOKEN))
    except (discord.LoginFailure, discord.HTTPException) as exc:
        print(f"Sync failed: {exc}", file=sys.stderr)
        return 1
    print(f"Synced {count} slash command(s) to Discord from {len(loaded)} command modules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/scripts/test_resync_slash_commands.py
```

Expected: `0 failed`, `0 xfailed`, 6 passed.

- [ ] **Step 5: Smoke the no-token path locally (never against production here)**

```bash
DISCORD_TOKEN= python $WT/scripts/ops/resync_slash_commands.py; echo "exit=$?"
```

Expected: `DISCORD_TOKEN is not set; nothing synced.` and `exit=2`. If the worktree's `.env` supplies a token anyway, skip this step and say so in the report. **Do not run the script with a real token in this task.** A real run re-syncs the live bot's global command set. It belongs to the controller's rollback procedure (index, "Production and rollback").

- [ ] **Step 6: Complexity**

```bash
python -m radon cc -s -n C $WT/scripts/ops/resync_slash_commands.py
```

Expected: nothing printed. Paste `(none)` into the report.

- [ ] **Step 7: Commit**

```bash
git -C $WT add scripts/ops/resync_slash_commands.py tests/scripts/test_resync_slash_commands.py
git -C $WT commit -m "feat(v153): SP20 scripts/ops/resync_slash_commands.py rollback remedy (HTTP-only login + tree.sync)"
```

### Task SP21: Pin `PREFIX_TIP_UNTIL` to deploy day + 90; amend the spec's output line

**Model:** haiku — one constant and fixed text replacements, all given verbatim below; the only input is the deploy day the controller supplies.

**Files:**
- Modify: `swingbot/commands/reply.py` (the `PREFIX_TIP_UNTIL` line and its comment, from SP1)
- Modify: `docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md` (`**Bump:**` paragraph, `**Status:**` line, a new `## Output changes` section, the "What this does not do" sentence)

**Interfaces:**
- Consumes (SP1): `reply.PREFIX_TIP_UNTIL` (provisional `dt.date(2027, 1, 8)`). The SP1, SP7 and SP18 tests compute their dates relative to the constant, so none of them changes.
- Input: **`DEPLOY_DAY`** (`YYYY-MM-DD`), the planned production deploy day. The controller asks the partner and passes it in the dispatch. If the dispatch has none, use the next weekday after today, say so in the report, and the controller re-pins before deploying (index, "Production and rollback": re-pin if the deploy slips by more than a week).
- Spec amendment (Controller decision 1): the spec says "no command's result changes", but the union rule changes a few `!` answers and three slash answers. This task lists every one of them in the spec. Sources: index Global Constraints "Every resulting `!` output change", SP9 (`send_error` answers), SP13 (the `/backtest` horizon fix, controller note), SP11 (`/pnl`), SP16 (`/stop` log line).

- [ ] **Step 0: Confirm SP20 landed and compute the date**

```bash
git -C $WT grep -n "^PREFIX_TIP_UNTIL" -- swingbot/commands/reply.py
git -C $WT grep -n "def resync" -- scripts/ops/resync_slash_commands.py
DEPLOY_DAY=YYYY-MM-DD   # from the dispatch
python -c "import datetime as d, sys; day = d.date.fromisoformat(sys.argv[1]); until = day + d.timedelta(days=90); print(until, until.year, until.month, until.day)" "$DEPLOY_DAY"
```

Expected: `PREFIX_TIP_UNTIL = dt.date(2027, 1, 8)`; one hit; then the cutoff date and its three parts. Below, `<UNTIL_Y>`, `<UNTIL_M>` and `<UNTIL_D>` are those parts, written without leading zeros.

- [ ] **Step 1: Pin the constant**

In `$WT/swingbot/commands/reply.py`, replace these three lines

```python
# Deploy day + 90 days; after it `prefix_tip` returns None. Provisional value,
# pinned to the real deploy day by plan v153 SP21.
PREFIX_TIP_UNTIL = dt.date(2027, 1, 8)
```

with (filling in `DEPLOY_DAY` and the parts):

```python
# Deploy day (<DEPLOY_DAY>) + 90 days; on and after it `prefix_tip` returns
# None and the tip line retires itself (pinned by plan v153 SP21). A date
# check, not a config key. Owner: the partner. Deleting this constant and the
# tip helpers is folded into the next plan that touches this file.
PREFIX_TIP_UNTIL = dt.date(<UNTIL_Y>, <UNTIL_M>, <UNTIL_D>)
```

Check:

```bash
PYTHONPATH=$WT python -c "import datetime as d; from swingbot.commands.reply import PREFIX_TIP_UNTIL as u; print(u, (u - d.date.fromisoformat('$DEPLOY_DAY')).days)"
```

Expected: the cutoff and `90`.

- [ ] **Step 2: Amend the spec**

```bash
python - <<'PY'
from pathlib import Path

spec = Path("/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v153-slash-command-parity/docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md")
text = spec.read_text(encoding="utf-8")

EDITS = [
    (
        "which is the shape of a minor (`working-conventions.md` § The three levels),\n"
        "even though no command's result changes. No admin UI change.",
        "which is the shape of a minor (`working-conventions.md` § The three levels).\n"
        "A few answers change too, each listed under \"Output changes\" (amended by\n"
        "plan v153 SP21; the first draft said no command's result changes). No admin UI change.",
    ),
    (
        "panel review applied 2026-10-09; no plan yet.",
        "panel review applied 2026-10-09; plan `docs/superpowers/plans/2026-10-10-v153-slash-command-parity_0-index.md`; "
        "\"Output changes\" added by its SP21.",
    ),
    (
        "change any command's output beyond the tip line and the `/watchlist`\n"
        "missing-ticker text on the prefix surface; guild-scoped sync.",
        "change any command's output beyond the list under \"Output changes\";\n"
        "guild-scoped sync.",
    ),
    (
        "## What this does not do\n",
        "## Output changes (amended by plan v153 SP21)\n"
        "\n"
        "One handler per command means one answer per command. Where the two\n"
        "surfaces disagreed, the partner chose \"union, `!` body as base\": the\n"
        "handler keeps the `!` answer and takes in the slash side's fixes.\n"
        "Every resulting change:\n"
        "\n"
        "On `!`:\n"
        "\n"
        "1. `Tip: this is now /<twin>` follows every successful answer until\n"
        "   `PREFIX_TIP_UNTIL`. It is never sent after an error answer.\n"
        "2. `!strategies` lists the 11 strategies (was 6) and keeps the\n"
        "   `(needs N+ trading days of history)` note.\n"
        "3. `!help` / `!commands`: the header reads ``Prefix: `!`  •  Slash: `/` ``.\n"
        "   Each row shows its slash twin after the `!` form. Fields split into\n"
        "   `\"<category> (cont.)\"` fields so that each stays within Discord's\n"
        "   1024-char limit (\"📊 Trades & performance\" was already 1116 chars).\n"
        "4. A bare `!watchlist add|remove` answers `Please provide a ticker for\n"
        "   add/remove actions.` instead of the `COMMAND_USAGE` hint.\n"
        "5. `!watchlist add aapl` stores `AAPL`; `add_ticker` used to receive the raw text.\n"
        "6. Validation, \"not found\" and fetch-failure answers go through\n"
        "   `send_error`. The text is the same, and no tip follows.\n"
        "\n"
        "`!scrapeall` and `!check` deliver unchanged: a prefix reply never goes stale.\n"
        "\n"
        "On `/`:\n"
        "\n"
        "7. `/strategies` gains the history note (item 2).\n"
        "8. `/pnl` answers with the `!pnl` table. Its old raw-row body is dropped.\n"
        "9. `/backtest` and `/backtestwatchlist` keep a chosen horizon. The old\n"
        "   bridge re-joined the options into prefix tokens, and the default\n"
        "   strategy `all` then overrode the horizon.\n"
        "10. `/stop` logs `(by <user>)`, as `!stop` does.\n"
        "11. A `/scrapeall` or `/check` that outlives the 15-minute interaction\n"
        "    token posts its later answers as fresh channel messages instead of\n"
        "    losing them.\n"
        "\n"
        "## What this does not do\n",
    ),
]

for old, new in EDITS:
    assert text.count(old) == 1, f"expected exactly one match for: {old[:60]!r}"
    text = text.replace(old, new)
spec.write_text(text, encoding="utf-8")
print("spec amended:", len(EDITS), "edits")
PY
```

Expected: `spec amended: 4 edits`. An assertion error means the spec text drifted; report the quoted fragment, do not guess.

The spec lives on `main` too. This edit travels with the branch and lands on `main` at merge. If the controller has already amended `main`'s copy, keep `main`'s version at merge.

- [ ] **Step 3: Check the amendment matches the code**

```bash
grep -n "^## Output changes\|^1\. \`Tip\|^11\. \|no command's result changes\|no plan yet" $WT/docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md
git -C $WT grep -n "MISSING_TICKER = \|^HELP_DESCRIPTION = \|STRATEGY_NAMES = (" -- swingbot/commands/
```

Expected: the first grep shows `## Output changes`, item 1, item 11, and the Bump line now quoting "no command's result changes" as the superseded first draft; no `no plan yet`. The second grep shows the three constants items 2–4 rest on.

- [ ] **Step 4: Run the tests that read the constant**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_growth_command.py
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_parity.py
```

Expected: every run `0 failed`, `0 xfailed`.

- [ ] **Step 5: Commit**

```bash
git -C $WT add swingbot/commands/reply.py docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md
git -C $WT commit -m "chore(v153): SP21 pin PREFIX_TIP_UNTIL to deploy day + 90; spec lists every output change"
```

### Task SP22: Full suite

**Model:** haiku — runs the fixed gate commands and reports; any failure goes back to the task that owns the file.

**Files:** none (a fix, if one is needed, belongs to the owning task's files and goes through review again).

- [ ] **Step 0: Confirm every task landed**

```bash
git -C $WT log --oneline main..HEAD | grep -c "v153"
git -C $WT grep -n "^PREFIX_TIP_UNTIL" -- swingbot/commands/reply.py
git -C $WT grep -c "@bot.tree.command\|from_interaction" -- swingbot/commands/slash.py
git -C /home/user/Discord-Bot status --short
```

Expected:
- at least 21 commits (SP4 may have committed nothing);
- the pinned SP21 date, not `2027, 1, 8` unless the deploy day really makes it that;
- `0`, or no output;
- the main tree is clean, or shows only the controller's own files.

- [ ] **Step 1: Syntax pass**

```bash
python -m py_compile $WT/bot.py $WT/admin_ui.py $(git -C $WT ls-files 'swingbot/**/*.py' 'swingbot/*.py' | sed "s|^|$WT/|") $WT/scripts/ops/resync_slash_commands.py
```

Expected: silent.

- [ ] **Step 2: The full suite, once**

Dispatch the `test-runner` subagent on `$WT` (keeps the progress lines out of the controller's context), or run directly:

```bash
python $WT/scripts/dev/testrun.py full
```

Expected: one-line verdict with `0 failed` and `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`). The suite gains the parity cases, `test_help_catalog.py`, `test_slash_parity.py` and `test_resync_slash_commands.py`, and loses SP19's five tests.

On a failure:
- name the test and the task whose files it touches (the index ledger maps files to tasks);
- re-dispatch that task's implementer with the failure (escalation ladder in `docs/claude/model-routing.md`);
- re-run only that test file with `testrun.py file`, then run this step once more.

Never edit a test to make it pass without the owning task's review.

If `tests/infra/test_swallowed_ratchet.py` exists (v148 merged), it passes: `python $WT/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py` (no `BASELINE` raise). If `scripts/dev/complexity_gate.py` exists (v149 merged), `python $WT/scripts/dev/complexity_gate.py` prints no `new`/`risen` verdict.

- [ ] **Step 3: Complexity over every touched module**

```bash
python -m radon cc -s -n C \
  $WT/swingbot/commands/reply.py $WT/swingbot/commands/modules.py $WT/swingbot/commands/slash.py \
  $WT/swingbot/commands/account.py $WT/swingbot/commands/data.py $WT/swingbot/commands/growth.py \
  $WT/swingbot/commands/history.py $WT/swingbot/commands/info.py $WT/swingbot/commands/trades.py \
  $WT/swingbot/commands/plans.py $WT/swingbot/commands/backtest.py $WT/swingbot/commands/watchlist.py \
  $WT/swingbot/commands/stats.py $WT/swingbot/commands/scanning/commands.py \
  $WT/swingbot/core/edge/portfolio_state.py $WT/scripts/ops/resync_slash_commands.py
```

Expected: every function or method this plan wrote or changed is below 15. The lines still allowed are legacy functions this plan did not touch, at no higher score than in the brief's §4: `_run_backtest_combo` C15, `render_board` D22, `format_trade_row` C16, and `collect_portfolio_state` D22 (moved unchanged by SP2). Nothing new appears, and none of `scrapeall_cmd`, `plans_cmd`, `ticker_cmd`, `summary_cmd`, `check_cmd` or `_check_historical` scores 15 or above. Paste the output into the report.

- [ ] **Step 4: Live-shape check (offline)**

```bash
PYTHONPATH=$WT python -c "from swingbot.commands import modules; modules.import_bot_command_modules(); from swingbot.bot_core import bot; from swingbot.commands.reply import SLASH_TWIN; print(len(bot.tree.get_commands()), sum(1 for _ in bot.walk_commands()), len(SLASH_TWIN))"
```

Expected: `41 53 53` (`42 53 53` if v152 landed). This is the number the post-deploy log check expects in `Synced N slash command(s)` (index, "Production and rollback").

- [ ] **Step 5: Record and hand back**

Append to `/home/user/Discord-Bot/.superpowers/sdd/progress.md`:

```bash
echo "$(date -I) v153 SP22: full suite green (<verdict line>); radon clean; tree 41/53/53. Ready for /close-out (bot minor) and deploy; post-deploy: grep 'Synced 41 slash' and the PREFIX_TIP_UNTIL date." >> /home/user/Discord-Bot/.superpowers/sdd/progress.md
```

Paste the real verdict line in place of `<verdict line>`. No commit in this task, unless Step 2 needed a fix, which the owning task commits. The controller then runs `/panel staff-engineer,senior-engineer` over the diff (spec `Panel:` line), then `/close-out`. Close-out applies the bot minor bump, merges, and removes the worktree. After the deploy, the controller follows the index's "Production and rollback" section.
