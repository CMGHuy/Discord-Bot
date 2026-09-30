"""v113: find code that ITERATES strategy_types.HORIZONS.

Since v113, HORIZONS holds a masked-by-default horizon ("1w"). A loop over it
silently scans or measures 1w. Iterate LEGACY_HORIZONS (confluence scans,
replays, measurement scripts) or live_horizons() (strategy vocabulary) instead.
Lookups (HORIZONS[k], HORIZONS.get(k)) and membership (k in HORIZONS) are fine.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPERS = frozenset({"list", "tuple", "set", "frozenset", "len", "enumerate", "sorted", "iter"})
VIEWS = frozenset({"keys", "items", "values"})


def _is_horizons(node) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "HORIZONS"
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in VIEWS and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "HORIZONS")


def _hit(node) -> bool:
    if isinstance(node, (ast.For, ast.comprehension)):
        return _is_horizons(node.iter)
    if isinstance(node, ast.Starred):
        return _is_horizons(node.value)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in WRAPPERS:
        return bool(node.args) and _is_horizons(node.args[0])
    return False


def _line(node) -> int:
    return node.iter.lineno if isinstance(node, (ast.For, ast.comprehension)) else node.lineno


def iterations(path: Path) -> list[tuple[int, str]]:
    """(line number, stripped source line) of every HORIZONS iteration in `path`."""
    source = Path(path).read_text(encoding="utf-8")
    lines = source.splitlines()
    hits = sorted({_line(node) for node in ast.walk(ast.parse(source)) if _hit(node)})
    return [(number, lines[number - 1].strip()) for number in hits]


def offenders(paths, allowed: set[tuple[str, str]]) -> list[str]:
    """`path:line: text` for every iteration not in `allowed` ((posix relpath, stripped line))."""
    found = []
    for path in paths:
        rel = Path(path).resolve().relative_to(ROOT).as_posix()
        found.extend(f"{rel}:{number}: {text}" for number, text in iterations(path)
                     if (rel, text) not in allowed)
    return found
