"""v62 C5: colour is defined in core.presentation and nowhere else."""

import ast
import pathlib

import pytest


REPO = pathlib.Path(__file__).resolve().parents[2]
GUARDED_PACKAGES: tuple[str, ...] = ("swingbot/core/presentation",)
ALLOWED = "swingbot/core/presentation"


def _guarded_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for package in GUARDED_PACKAGES:
        files.extend(sorted((REPO / package).rglob("*.py")))
    return files


def _colour_offences(tree: ast.AST) -> list[tuple[int, str]]:
    """Find actual colour syntax, never words in comments or strings."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("Color", "Colour"):
            if isinstance(node.value, ast.Name) and node.value.id == "discord":
                hits.append((node.lineno, f"discord.{node.attr}"))
        if isinstance(node, ast.Call):
            func = node.func
            is_embed = ((isinstance(func, ast.Attribute) and func.attr == "Embed")
                        or (isinstance(func, ast.Name) and func.id == "Embed"))
            if is_embed:
                for keyword in node.keywords:
                    if keyword.arg in ("color", "colour"):
                        hits.append((node.lineno, f"Embed({keyword.arg}=...)"))
    return hits


@pytest.mark.parametrize("path", _guarded_files(), ids=lambda path: path.name)
def test_no_adhoc_colour_outside_the_presentation_package(path):
    rel = path.relative_to(REPO).as_posix()
    if rel.startswith(ALLOWED):
        pytest.skip("the presentation package owns colour")
    offences = _colour_offences(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    assert not offences, f"{rel} sets colour directly: {offences}"


def test_the_guard_actually_catches_an_offence():
    tree = ast.parse("import discord\ne = discord.Embed(color=discord.Color.red())")
    assert _colour_offences(tree)


def test_the_guard_ignores_colour_named_in_a_docstring_or_comment():
    tree = ast.parse('"""Embed titles cannot carry color."""\n# discord.Color.red()\n')
    assert not _colour_offences(tree)
