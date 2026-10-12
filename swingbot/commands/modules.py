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
