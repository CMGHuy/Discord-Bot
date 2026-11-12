#!/usr/bin/env python3
"""v220 safety check 2: is every Alembic revision the target lacks additive?

Reads revision files from any commit's tree (`git ls-tree` + `git show`) and
classifies each `upgrade()` by AST. Never imports a revision file and never uses
Alembic's ScriptDirectory (it reads the working tree, not the target commit).
Standard library only: the VM host's python3 runs this from a copy.

    python3 rollback_migrations.py <target_sha> [--head HEAD] [--repo DIR]
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

MIGRATIONS_DIR = "swingbot/core/db/migrations/versions"
SAFE_SQL_HEADS = ("CREATE TABLE ", "CREATE INDEX ", "CREATE UNIQUE INDEX ", "INSERT ", "COMMENT ")
TEXT_FUNCS = {"text", "sa.text", "sqlalchemy.text"}
DB_ATTRS = {"get_bind", "execute", "exec_driver_sql", "connection"}
_MISSING = object()


@dataclass
class Verdict:
    revision: str
    path: str
    safe: bool
    reasons: list[str] = field(default_factory=list)
    override: str | None = None


@dataclass(frozen=True)
class Rev:
    revision: str
    down: tuple[str, ...]
    path: str
    source: str


def split_sql(sql: str) -> list[str]:
    """Statements of a literal SQL string: `--` comments dropped, whitespace collapsed."""
    lines = [line.split("--", 1)[0] for line in sql.splitlines()]
    return [" ".join(part.split()) for part in "\n".join(lines).split(";") if part.strip()]


def _op_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "op":
        return func.attr
    return None


def _literal_sql(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Call) and ast.unparse(node.func) in TEXT_FUNCS and node.args:
        first = node.args[0]
        return first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
    return None


def _touches_db(fn: ast.AST) -> bool:
    return any(isinstance(node, ast.Attribute) and (node.attr in DB_ATTRS or _op_name(node))
               for node in ast.walk(fn))


def _nested_reasons(call: ast.Call, helpers: dict) -> list[str]:
    reasons = []
    for node in ast.walk(call):
        if node is call or not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else None
        if _op_name(node.func):
            reasons.append(f"line {node.lineno}: nested op.{_op_name(node.func)}()")
        elif name in helpers and _touches_db(helpers[name]):
            reasons.append(f"line {node.lineno}: helper {name}() touches op or a connection")
    return reasons


def _column_of(call: ast.Call) -> ast.Call | None:
    nodes = list(call.args[1:]) + [kw.value for kw in call.keywords if kw.arg == "column"]
    for node in nodes:
        if isinstance(node, ast.Call) and ast.unparse(node.func).split(".")[-1] == "Column":
            return node
    return None


def _is_none(node: ast.AST | None) -> bool:
    return node is None or (isinstance(node, ast.Constant) and node.value is None)


def _add_column_reasons(call: ast.Call, helpers: dict) -> list[str]:
    column = _column_of(call)
    if column is None:
        return [f"line {call.lineno}: op.add_column() without a literal Column(...)"]
    kw = {k.arg: k.value for k in column.keywords}
    nullable = isinstance(kw.get("nullable"), ast.Constant) and kw["nullable"].value is True
    reasons = _nested_reasons(call, helpers)
    if not nullable and _is_none(kw.get("server_default")):
        name = ast.unparse(column.args[0]) if column.args else "?"
        reasons.append(f"line {call.lineno}: op.add_column({name}) is neither "
                       "nullable=True nor given a server_default")
    return reasons


def _execute_reasons(call: ast.Call, helpers: dict) -> list[str]:
    sql = _literal_sql(call.args[0]) if call.args else None
    if sql is None:
        return [f"line {call.lineno}: op.execute() with non-literal SQL"]
    return [f"line {call.lineno}: SQL is not additive: {stmt[:60]}"
            for stmt in split_sql(sql) if not (stmt.upper() + " ").startswith(SAFE_SQL_HEADS)]


_OP_CHECKS = {"create_table": _nested_reasons, "create_index": _nested_reasons,
              "add_column": _add_column_reasons, "execute": _execute_reasons}


def _call_reasons(call: ast.Call, helpers: dict) -> list[str]:
    name = _op_name(call.func)
    if name is None:
        return [f"line {call.lineno}: call to helper {ast.unparse(call.func)}()"]
    check = _OP_CHECKS.get(name)
    return check(call, helpers) if check else [f"line {call.lineno}: op.{name}()"]


def _statement_reasons(stmt: ast.stmt, helpers: dict) -> list[str]:
    value = stmt.value if isinstance(stmt, ast.Expr) else None
    if isinstance(stmt, ast.Pass) or (isinstance(value, ast.Constant) and isinstance(value.value, str)):
        return []
    if isinstance(value, ast.Call):
        return _call_reasons(value, helpers)
    return [f"line {stmt.lineno}: {type(stmt).__name__} statement in upgrade()"]


def _connection_reasons(fn: ast.AST) -> list[str]:
    reasons = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Attribute) and node.attr == "get_bind":
            reasons.append(f"line {node.lineno}: {ast.unparse(node)}()")
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr in ("execute", "exec_driver_sql") and not _op_name(node.func)):
            reasons.append(f"line {node.lineno}: {ast.unparse(node.func)}()")
    return reasons


def _assigned(stmt: ast.stmt) -> list[tuple[str, ast.AST]]:
    """(name, value node) pairs of a module-level assignment, tuple unpacking included."""
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value:
        return [(stmt.target.id, stmt.value)]
    if not isinstance(stmt, ast.Assign):
        return []
    pairs: list[tuple[str, ast.AST]] = []
    for target in stmt.targets:
        if isinstance(target, ast.Name):
            pairs.append((target.id, stmt.value))
        elif (isinstance(target, ast.Tuple) and isinstance(stmt.value, ast.Tuple)
              and len(target.elts) == len(stmt.value.elts)):
            pairs.extend((t.id, v) for t, v in zip(target.elts, stmt.value.elts) if isinstance(t, ast.Name))
    return pairs


def _module_value(tree: ast.Module, name: str):
    """Literal value of the first top-level assignment to `name`; _MISSING when absent."""
    for stmt in tree.body:
        for target, node in _assigned(stmt):
            if target == name:
                return ast.literal_eval(node)
    return _MISSING


def _rollback_safe(tree: ast.Module) -> str | None:
    try:
        value = _module_value(tree, "ROLLBACK_SAFE")
    except ValueError:
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def scan_upgrade(source: str, *, revision: str = "?", path: str = "?") -> Verdict:
    """Classify one revision file's upgrade(); ROLLBACK_SAFE overrides an unsafe verdict."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return Verdict(revision, path, False, [f"unparsable: {exc.msg} (line {exc.lineno})"])
    helpers = {s.name: s for s in tree.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))}
    upgrade = helpers.get("upgrade")
    if upgrade is None:
        reasons = ["no upgrade() function"]
    else:
        reasons = [r for stmt in upgrade.body for r in _statement_reasons(stmt, helpers)]
        reasons = list(dict.fromkeys(reasons + _connection_reasons(upgrade)))
    override = _rollback_safe(tree)
    return Verdict(revision, path, not reasons or override is not None, reasons, override)


def _downs(value) -> tuple[str, ...]:
    if value is None or value is _MISSING:
        return ()
    return (value,) if isinstance(value, str) else tuple(value)


def revision_graph(files: dict[str, str]) -> dict[str, Rev]:
    """revision id -> Rev for every file declaring a string `revision`."""
    graph: dict[str, Rev] = {}
    for path, source in sorted(files.items()):
        try:
            tree = ast.parse(source)
            revision, down = _module_value(tree, "revision"), _module_value(tree, "down_revision")
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"{path}: cannot read revision ids ({exc})") from None
        if not isinstance(revision, str):
            continue
        if revision in graph:
            raise ValueError(f"duplicate revision {revision} in {graph[revision].path} and {path}")
        graph[revision] = Rev(revision, _downs(down), path, source)
    return graph


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def tree_migrations(repo: Path, sha: str) -> dict[str, str]:
    """path -> source of every revision file in `sha`'s tree (never the working tree)."""
    names = _git(repo, "ls-tree", "--name-only", sha, f"{MIGRATIONS_DIR}/").splitlines()
    wanted = [n for n in names if n.endswith(".py") and not n.endswith("__init__.py")]
    return {name: _git(repo, "show", f"{sha}:{name}") for name in wanted}


def head_of(graph: dict[str, Rev]) -> str:
    referenced = {down for rev in graph.values() for down in rev.down}
    heads = sorted(set(graph) - referenced)
    if len(heads) != 1:
        raise ValueError(f"expected exactly one head, found {heads or 'none'}")
    return heads[0]


def _ancestors(graph: dict[str, Rev], start: str) -> set[str]:
    seen: set[str] = set()
    stack = [start]
    while stack:
        rev = stack.pop()
        if rev in seen:
            continue
        if rev not in graph:
            raise LookupError(f"revision {rev} is not in the graph")
        seen.add(rev)
        stack.extend(graph[rev].down)
    return seen


def _topological(graph: dict[str, Rev], revs: set[str]) -> list[Rev]:
    order: list[Rev] = []
    done: set[str] = set()
    pending = sorted(revs)
    while pending:
        ready = [r for r in pending if all(d in done or d not in revs for d in graph[r].down)]
        if not ready:
            raise ValueError(f"cycle among revisions {pending}")
        order.extend(graph[r] for r in ready)
        done.update(ready)
        pending = [r for r in pending if r not in done]
    return order


def between(graph: dict[str, Rev], target_head: str, *, known: set[str] | None = None) -> list[Rev]:
    """Revisions newer than the target, oldest first.

    With `known` (the target tree's revision ids) the answer is every revision the
    target lacks; without it, ancestry from the target head to the current head."""
    if target_head not in graph:
        raise LookupError(f"revision {target_head} is not in the current history")
    if known is not None:
        newer = set(graph) - set(known)
    else:
        newer = _ancestors(graph, head_of(graph)) - _ancestors(graph, target_head)
    return _topological(graph, newer)


def check_migrations(repo: Path, target_sha: str, head_sha: str) -> list[Verdict]:
    """Safety check 2: a verdict for every revision `head_sha` has and `target_sha` lacks."""
    target = revision_graph(tree_migrations(repo, target_sha))
    if not target:
        raise LookupError(f"{target_sha[:12]} has no Alembic revisions")
    current = revision_graph(tree_migrations(repo, head_sha))
    unknown = sorted(set(target) - set(current))
    if unknown:
        raise LookupError(f"target revisions missing from {head_sha[:12]}: {', '.join(unknown)}")
    return [scan_upgrade(rev.source, revision=rev.revision, path=rev.path)
            for rev in between(current, head_of(target), known=set(target))]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v220 migration rollback-safety scan")
    parser.add_argument("target_sha")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args(argv)
    try:
        verdicts = check_migrations(Path(args.repo), args.target_sha, args.head)
    except (LookupError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"REFUSE: {exc}", file=sys.stderr)
        return 2
    print(json.dumps([asdict(v) for v in verdicts], indent=2))
    return 0 if all(v.safe for v in verdicts) else 2


if __name__ == "__main__":
    sys.exit(main())
