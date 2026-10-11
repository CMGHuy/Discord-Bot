import ast
import pathlib


def test_slash_has_no_direct_colour():
    tree = ast.parse(pathlib.Path("swingbot/commands/slash.py").read_text(encoding="utf-8"))
    assert not [node.lineno for node in ast.walk(tree)
                if isinstance(node, ast.Attribute) and node.attr in ("Color", "Colour")]
