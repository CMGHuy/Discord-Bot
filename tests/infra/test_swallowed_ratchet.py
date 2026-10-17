"""v148 O5: the swallowed-error ratchet.

An ``except`` handler is *untagged* when it catches ``Exception`` (alone or in
a tuple), its body calls no ``swallowed()``, and it contains no ``raise``.
Three rules, all AST-based so comments and strings never count:

1. No untagged handler in the converted scopes (``SCOPES``), except a file
   named in ``EXCLUDED`` with its reason.
2. Repo-wide (``swingbot/**/*.py`` plus the root entry points) the untagged
   count equals ``BASELINE``. It can only fall: a lower count fails with
   "lower BASELINE to N", so the next person cannot quietly spend the slack.
3. Every ``swallowed()`` tag is a string literal ``<area>.<function>`` and no
   two ``except`` handlers share one. A tag may appear again outside any
   handler: ``fetch._run_bounded`` counts its timeout path, which is not a
   handler, under the same ``scan.run_bounded`` as its child-raised handler.
"""
from __future__ import annotations

import ast
import re
import textwrap
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: The scopes v148 converted; every handler in them is tagged.
SCOPES: tuple[str, ...] = (
    "swingbot/core/scanning/*.py",
    "swingbot/core/marketdata/**/*.py",
    "swingbot/core/market/events.py",
    "swingbot/core/market/earnings_history.py",
    "swingbot/commands/scanning/runstate.py",
)

#: Scope files deliberately left unconverted, path -> reason. Their untagged
#: handlers are counted in BASELINE, never silently exempted.
EXCLUDED: dict[str, str] = {}

ROOT_FILES: tuple[str, ...] = ("bot.py", "admin_ui.py", "admin_wsgi.py")

#: Repo-wide untagged handlers, measured after the v148 conversion (OH15).
BASELINE: int = 243

TAG_RE = re.compile(r"^(scan|marketdata|earnings|runstate|ops)\.[a-z0-9_]+(\.[a-z0-9_]+)*$")


def _catches_exception(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return False
    names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(n, ast.Name) and n.id == "Exception" for n in names)


def _is_swallowed_call(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "swallowed")


def _is_untagged(handler: ast.ExceptHandler) -> bool:
    if not _catches_exception(handler):
        return False
    nodes = list(ast.walk(handler))
    return not any(_is_swallowed_call(n) for n in nodes) and not any(
        isinstance(n, ast.Raise) for n in nodes)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def untagged_handlers(path: Path) -> list[int]:
    """Line numbers of the untagged handlers in one file."""
    return sorted(h.lineno for h in ast.walk(_tree(path))
                  if isinstance(h, ast.ExceptHandler) and _is_untagged(h))


def _own_calls(handler: ast.ExceptHandler) -> list[ast.Call]:
    """The swallowed() calls of this handler, not of a handler nested in it."""
    calls, stack = [], list(ast.iter_child_nodes(handler))
    while stack:
        node = stack.pop()
        if isinstance(node, ast.ExceptHandler):
            continue
        if _is_swallowed_call(node):
            calls.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return calls


def _tag(call: ast.Call) -> str | None:
    if len(call.args) < 2:
        return None
    arg = call.args[1]
    return arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None


def handler_tags(path: Path) -> list[tuple[int, str]]:
    """(handler line, tag) once per distinct tag per handler."""
    pairs = []
    for handler in ast.walk(_tree(path)):
        if isinstance(handler, ast.ExceptHandler):
            tags = {_tag(call) for call in _own_calls(handler)}
            pairs += [(handler.lineno, tag) for tag in sorted(tags, key=str)]
    return pairs


def bad_tags(path: Path) -> list[tuple[int, object]]:
    """Every swallowed() call in the file whose tag is not a valid literal."""
    found = []
    for node in ast.walk(_tree(path)):
        if _is_swallowed_call(node):
            tag = _tag(node)
            if tag is None or not TAG_RE.match(tag):
                found.append((node.lineno, tag))
    return found


def duplicate_tags(paths: list[Path]) -> dict[str, list[str]]:
    sites = defaultdict(list)
    for path in paths:
        for line, tag in handler_tags(path):
            sites[tag].append(f"{path.relative_to(REPO).as_posix()}:{line}")
    return {tag: where for tag, where in sites.items() if len(where) > 1}


def _repo_files() -> list[Path]:
    """``test_every_scope_and_root_file_exists`` asserts the root files exist;
    skipping a missing one here keeps that the single, readable failure."""
    roots = [REPO / name for name in ROOT_FILES if (REPO / name).is_file()]
    return sorted(REPO.glob("swingbot/**/*.py")) + roots


def _scope_files() -> list[Path]:
    return sorted({path for pattern in SCOPES for path in REPO.glob(pattern)})


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


# --- the rule itself, on a sample -------------------------------------------

_SAMPLE = textwrap.dedent('''\
    def f(log):
        try:
            pass
        except Exception:
            pass
        try:
            pass
        except (ValueError, Exception) as exc:
            log.warning("x")
        try:
            pass
        except Exception as exc:
            swallowed(log, "scan.f", exc)
        try:
            pass
        except Exception:
            raise
        try:
            pass
        except ValueError:
            pass
        try:
            pass
        except:
            pass
        try:
            pass
        except BaseException:
            pass
    ''')


def test_the_untagged_rule_on_a_sample(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(_SAMPLE, encoding="utf-8")
    assert untagged_handlers(sample) == [4, 8]


def test_a_nested_handler_tag_belongs_to_the_inner_handler_only(tmp_path):
    sample = tmp_path / "nested.py"
    sample.write_text(textwrap.dedent('''\
        def g(log):
            try:
                pass
            except Exception as exc:
                swallowed(log, "scan.outer", exc)
                try:
                    pass
                except Exception as inner:
                    swallowed(log, "scan.inner", inner)
        '''), encoding="utf-8")
    assert handler_tags(sample) == [(4, "scan.outer"), (8, "scan.inner")]


def test_a_tag_reused_outside_any_handler_is_not_a_duplicate(tmp_path):
    """fetch._run_bounded's shape: one handler, one timeout path, one tag."""
    sample = tmp_path / "bounded.py"
    sample.write_text(textwrap.dedent('''\
        def run(log):
            try:
                pass
            except Exception as exc:
                swallowed(log, "scan.run_bounded", exc)
            swallowed(log, "scan.run_bounded", TimeoutError("x"))
        '''), encoding="utf-8")
    assert handler_tags(sample) == [(4, "scan.run_bounded")]


def test_bad_tags_are_found(tmp_path):
    sample = tmp_path / "bad.py"
    sample.write_text(textwrap.dedent('''\
        def h(log, name):
            swallowed(log, name, ValueError())
            swallowed(log, "Scan.Bad", ValueError())
            swallowed(log, "nope.area", ValueError())
            swallowed(log, "scan.ok", ValueError())
        '''), encoding="utf-8")
    assert bad_tags(sample) == [(2, None), (3, "Scan.Bad"), (4, "nope.area")]


# --- the ratchet on the repo --------------------------------------------------

def test_every_scope_and_root_file_exists():
    assert all(list(REPO.glob(pattern)) for pattern in SCOPES), SCOPES
    assert all((REPO / name).is_file() for name in ROOT_FILES), ROOT_FILES


def test_excluded_paths_are_in_scope_and_carry_a_reason():
    in_scope = {_rel(path) for path in _scope_files()}
    for path, reason in EXCLUDED.items():
        assert path in in_scope, f"EXCLUDED names {path}, which is not in SCOPES"
        assert reason.strip(), f"EXCLUDED[{path!r}] needs its reason"


def test_no_untagged_handler_in_the_converted_scopes():
    found = {_rel(path): untagged_handlers(path) for path in _scope_files()
             if _rel(path) not in EXCLUDED}
    found = {path: lines for path, lines in found.items() if lines}
    assert found == {}, (
        "untagged `except Exception` in a v148 scope -- call swallowed(log, '<area>.<function>', "
        f"exc, <same message>, level=<same level>) instead (spec O5): {found}")


def test_the_repo_wide_untagged_count_only_falls():
    count = sum(len(untagged_handlers(path)) for path in _repo_files())
    assert count <= BASELINE, (
        f"{count} untagged `except Exception` handlers, BASELINE is {BASELINE}: a new swallow "
        "must call swallowed(log, '<area>.<function>', exc, ...) -- never raise BASELINE")
    assert count == BASELINE, f"the untagged count fell to {count}: lower BASELINE to {count}"


def test_every_tag_is_a_valid_literal():
    found = {_rel(path): bad for path in _repo_files() if (bad := bad_tags(path))}
    assert found == {}, (
        "swallowed() tags are string literals '<area>.<function>' with area one of "
        f"scan, marketdata, earnings, runstate, ops: {found}")


def test_no_two_handlers_share_a_tag():
    assert duplicate_tags(_repo_files()) == {}, (
        "each except handler needs its own tag -- add a suffix naming what failed "
        "(scan.run_scan.telemetry)")
