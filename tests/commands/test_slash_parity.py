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
