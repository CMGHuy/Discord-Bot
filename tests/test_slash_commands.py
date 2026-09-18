import ast
import pathlib


def test_slash_has_no_direct_colour():
    tree = ast.parse(pathlib.Path("swingbot/commands/slash.py").read_text(encoding="utf-8"))
    assert not [node.lineno for node in ast.walk(tree)
                if isinstance(node, ast.Attribute) and node.attr in ("Color", "Colour")]


def test_soak_slash_registered():
    # Import as an explicit side effect (registers @bot.tree.command
    # decorators) rather than relying on another test module having
    # already imported it -- see test_stats_commands.py's
    # test_six_bridge_commands_still_registered for why that matters
    # under `-n 4` (import order across workers is not deterministic).
    import swingbot.commands.slash  # noqa: F401
    from swingbot.bot_core import bot

    names = {cmd.name for cmd in bot.tree.get_commands()}
    assert "soak" in names, "/soak not registered on bot.tree"
