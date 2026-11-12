# v220 — Code-only rollback, Part 1b: migration scanner and host checks (V220-3, V220-3b, V220-4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v220 — Code-only rollback](../specs/2026-11-08-v220-code-only-rollback-design.md)
**Index:** [`2026-11-08-v220-code-only-rollback_0-index.md`](2026-11-08-v220-code-only-rollback_0-index.md) — Goal, Architecture, **Global Constraints**, CLI contract, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.

Scope of this part: safety check 2 (the AST migration scanner, the Alembic revision graph read from any commit's tree, and the one-time `ROLLBACK_SAFE` audit) in `scripts/ops/rollback_migrations.py`, and safety checks 3, 5 and 6 (config keys, compose `db` block, market-data writer paths) in `scripts/ops/rollback_checks.py`. V220-6 (Part 2) assembles them into the `check` report; nothing here has a CLI the VM script calls except the debug CLI of `rollback_migrations.py`.

Shared rules for these three tasks:

- Both modules are **standard library only** and import nothing from `swingbot`; tests import them with `sys.path.insert(0, str(REPO / "scripts" / "ops"))`, the `tests/scripts/test_backup_manifest.py` pattern.
- Target files are read with `git show <sha>:<path>` and parsed with `ast`; never imported or executed.
- Tests that build temp git repositories skip when `git` is not on `PATH`. Files are written with `write_bytes(text.encode("utf-8"))` so Windows never turns `\n` into `\r\n`.
- All new tests live in `tests/scripts/` (suite `tooling`); no `tests/suites.toml` change.
- Per-task verification is the narrow run only: `python scripts/dev/testrun.py file <test>`. Complexity: `python scripts/dev/complexity_gate.py` must stay green (every new function < 15).


# Phase 1b — Migration scanner and host checks

### Task V220-3: AST migration scanner and its rules

**Model:** opus — classifies Alembic revisions statement by statement

This task builds the per-revision classifier (`scan_upgrade`, `Verdict`, `split_sql`) and its rule tests on synthetic sources. **V220-3b** (split for size) adds the revision graph read from a git tree, `check_migrations`, the debug CLI, the real-repo tests and the one-time `ROLLBACK_SAFE` audit to the same two files.

**Files:**
- Create: `scripts/ops/rollback_migrations.py`
- Create: `tests/scripts/test_rollback_migrations.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (final, per the ledger; consumed by V220-3b and V220-6): `MIGRATIONS_DIR = "swingbot/core/db/migrations/versions"`; `@dataclass Verdict(revision: str, path: str, safe: bool, reasons: list[str], override: str | None)`; `scan_upgrade(source: str, *, revision: str = "?", path: str = "?") -> Verdict` (a non-blank module-level `ROLLBACK_SAFE` overrides an unsafe verdict, the reasons are kept); `split_sql(sql: str) -> list[str]`. Private helpers V220-3b reuses: `_MISSING` (sentinel), `_module_value(tree: ast.Module, name: str)` (literal value of the first top-level assignment to `name`, tuple unpacking included; `_MISSING` when absent; `ValueError` from `ast.literal_eval` on a non-literal).

Decisions (spec § Safety check 2, index notes):
- **Classification is per statement of `upgrade()`**: each statement must be a bare `op.<name>(...)` call (or a docstring / `pass`). Safe calls: `create_table`, `create_index`, `add_column` (its `Column` has `nullable=True` or a non-`None` `server_default`; the spec's wording, so a Column with no `nullable=` is unsafe), `execute` of a literal string or `sa.text("<literal>")` whose every `;`-separated statement (after stripping `--` comments) starts with `CREATE TABLE`, `CREATE INDEX`, `CREATE UNIQUE INDEX`, `INSERT` or `COMMENT`.
- Unsafe: every other `op.*` call (`drop_*`, `alter_column`, `rename_*`, `create_foreign_key`, …), any other statement type (assignment, `for`, `with`, `if`), a statement-level call to any non-`op` function (helpers such as `rename_doc_field`, `drop_doc_field`, `_complete`), anywhere in `upgrade()` an `op.get_bind()` or a non-`op` `.execute(...)`/`.exec_driver_sql(...)`, and inside `create_table`/`create_index`/`add_column` arguments a nested `op.*` call or a module helper whose body touches `op` or a connection. A helper that only builds columns (`v207_001`'s `_standard()`) is safe.
- **`ROLLBACK_SAFE = "<non-blank reason>"`** at module level makes the verdict safe and is reported in `override`; a blank or non-literal value is no override.
- **Module-level assignments are read with tuple unpacking**: `p2_001`..`p2_005` declare `revision, down_revision, branch_labels, depends_on = "p2_001", "p1_003", None, None` on one line; `_module_value` handles that form, `ast.AnnAssign` and plain `Assign` (V220-3b relies on it for the graph; without it the graph loses five revisions and finds two heads).

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_rollback_migrations.py`:

```python
"""v220 V220-3/3b: AST migration scanner and the revision graph built from a git tree."""
from __future__ import annotations

import ast
import pathlib
import sys
import textwrap

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_migrations as rm  # noqa: E402


def _mig(body: str, *, head: str = "", revision: str = "r1", down=("r0")) -> str:
    code = textwrap.indent(textwrap.dedent(body).strip("\n"), "    ")
    return (f'"""doc"""\nimport sqlalchemy as sa\nfrom alembic import op\n{head}\n'
            f"revision = {revision!r}\ndown_revision = {down!r}\n\n\n"
            f"def upgrade() -> None:\n{code}\n")


SAFE = {
    "create_table": 'op.create_table("t", sa.Column("id", sa.Integer, primary_key=True))',
    "create_index": 'op.create_index("t_i", "t", ["id"], unique=True)',
    "add_nullable": 'op.add_column("t", sa.Column("x", sa.Text, nullable=True))',
    "add_default": 'op.add_column("t", sa.Column("x", sa.Text, nullable=False, server_default="a"))',
    "sql_create": 'op.execute("CREATE TABLE IF NOT EXISTS t (id int)")',
    "sql_multi": ('op.execute("CREATE TABLE t (id int); -- note\\nCREATE UNIQUE INDEX t_i ON t (id);'
                  "\\nINSERT INTO t VALUES (1);\\nCOMMENT ON TABLE t IS 'x'\")"),
    "sa_text": 'op.execute(sa.text("CREATE INDEX t_i ON t (id)"))',
    "docstring_pass": '"""Only a docstring."""\npass',
}


@pytest.mark.parametrize("name", sorted(SAFE))
def test_safe_rules(name):
    verdict = rm.scan_upgrade(_mig(SAFE[name]), revision="r1", path="p.py")
    assert (verdict.safe, verdict.reasons, verdict.revision, verdict.path) == (True, [], "r1", "p.py")


def test_a_column_building_helper_is_safe():
    head = 'def _cols():\n    return [sa.Column("doc", sa.Text, nullable=True)]\n'
    assert rm.scan_upgrade(_mig('op.create_table("t", sa.Column("id", sa.Integer), *_cols())',
                                head=head)).safe


UNSAFE = [
    ('op.drop_column("t", "x")', "op.drop_column()"),
    ('op.alter_column("t", "x", nullable=True)', "op.alter_column()"),
    ('op.rename_table("a", "b")', "op.rename_table()"),
    ('op.drop_index("i")', "op.drop_index()"),
    ('op.create_foreign_key("fk", "a", "b", ["x"], ["id"])', "op.create_foreign_key()"),
    ('op.add_column("t", sa.Column("x", sa.Text, nullable=False))', "neither nullable=True"),
    ('op.add_column("t", sa.Column("x", sa.Text))', "neither nullable=True"),
    ('op.add_column("t", sa.Column("x", sa.Text, server_default=None))', "neither nullable=True"),
    ('op.add_column("t", COLUMN)', "without a literal Column"),
    ('op.execute("UPDATE plans SET doc = doc")', "not additive: UPDATE plans"),
    ('op.execute("CREATE TABLE a (id int); DELETE FROM b")', "not additive: DELETE FROM b"),
    ('op.execute("CREATE OR REPLACE FUNCTION f() RETURNS int AS $$ SELECT 1 $$ LANGUAGE sql")',
     "not additive: CREATE OR REPLACE FUNCTION"),
    ('op.execute(f"CREATE TABLE {name} (id int)")', "non-literal SQL"),
    ("op.execute(SQL)", "non-literal SQL"),
    ('conn = op.get_bind()\nconn.execute(sa.text("SELECT 1"))', "op.get_bind()"),
    ('conn = op.get_bind()\nconn.execute(sa.text("SELECT 1"))', "conn.execute()"),
    ('rename_doc_field("plans", "a", "b")', "call to helper rename_doc_field()"),
    ('drop_doc_field("plans", "a")', "call to helper drop_doc_field()"),
    ("_complete()", "call to helper _complete()"),
    ('for t in ("a", "b"):\n    op.create_index(t + "_i", t, ["id"])', "For statement"),
    ('op.create_table("t", op.f("x"))', "nested op.f()"),
]


@pytest.mark.parametrize("body,reason", UNSAFE)
def test_unsafe_rules(body, reason):
    verdict = rm.scan_upgrade(_mig(body))
    assert verdict.safe is False and verdict.override is None
    assert any(reason in r for r in verdict.reasons), verdict.reasons


def test_reasons_carry_the_line_and_are_not_repeated():
    verdict = rm.scan_upgrade(_mig('op.drop_column("t", "x")\nop.drop_column("t", "y")'))
    assert len(verdict.reasons) == 2 and all(r.startswith("line ") for r in verdict.reasons)


def test_a_helper_in_arguments_that_touches_op_is_unsafe():
    head = 'def _rows():\n    op.execute("DELETE FROM t")\n    return []\n'
    verdict = rm.scan_upgrade(_mig('op.create_table("t", *_rows())', head=head))
    assert not verdict.safe and any("helper _rows() touches op" in r for r in verdict.reasons)


def test_rollback_safe_overrides_and_keeps_the_reasons():
    verdict = rm.scan_upgrade(_mig('op.drop_column("t", "x")',
                                   head='ROLLBACK_SAFE = "old code never reads t.x"\n'))
    assert verdict.safe and verdict.override == "old code never reads t.x"
    assert len(verdict.reasons) == 1 and verdict.reasons[0].endswith("op.drop_column()")


@pytest.mark.parametrize("value", ['"  "', "REASON", "None"])
def test_a_blank_or_non_literal_rollback_safe_is_no_override(value):
    verdict = rm.scan_upgrade(_mig('op.drop_column("t", "x")', head=f"ROLLBACK_SAFE = {value}\n"))
    assert not verdict.safe and verdict.override is None


def test_rollback_safe_on_a_safe_revision_is_still_reported():
    verdict = rm.scan_upgrade(_mig('op.create_index("i", "t", ["id"])', head='ROLLBACK_SAFE = "r"\n'))
    assert (verdict.safe, verdict.reasons, verdict.override) == (True, [], "r")


def test_unparsable_and_missing_upgrade_are_unsafe():
    assert rm.scan_upgrade("def upgrade(:\n").reasons[0].startswith("unparsable")
    assert rm.scan_upgrade('revision = "r"\n').reasons == ["no upgrade() function"]


def test_split_sql_strips_comments_and_whitespace():
    assert rm.split_sql("CREATE TABLE t (id int); -- c;\n\n  INSERT  INTO t\nVALUES (1);  ") == [
        "CREATE TABLE t (id int)", "INSERT INTO t VALUES (1)"]
    assert rm.split_sql("-- only a comment\n") == []


def test_module_value_reads_plain_annotated_and_unpacked_assignments():
    tree = ast.parse('a = "x"\nb: str = "y"\nc, d = "z", ("p", "q")\ne = f()\n')
    assert [rm._module_value(tree, n) for n in "abcd"] == ["x", "y", "z", ("p", "q")]
    assert rm._module_value(tree, "missing") is rm._MISSING
    with pytest.raises(ValueError):
        rm._module_value(tree, "e")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_migrations.py`
Expected: collection error, `ModuleNotFoundError: No module named 'rollback_migrations'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/ops/rollback_migrations.py`:

```python
#!/usr/bin/env python3
"""v220 safety check 2: is every Alembic revision the target lacks additive?

Reads revision files from any commit's tree (`git ls-tree` + `git show`) and
classifies each `upgrade()` by AST. Never imports a revision file and never uses
Alembic's ScriptDirectory (it reads the working tree, not the target commit).
Standard library only: the VM host's python3 runs this from a copy.

    python3 rollback_migrations.py <target_sha> [--head HEAD] [--repo DIR]
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field

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
```

Notes for the implementer:
- `ROLLBACK_SAFE = None` and `ROLLBACK_SAFE = REASON` (a name, not a literal) are both "no override": `literal_eval` returns `None` for the first and raises `ValueError` for the second.
- `dict.fromkeys` drops exact duplicate reasons only; two different calls on two lines stay two reasons.
- The module docstring already names the debug CLI; V220-3b adds it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_migrations.py`
Expected: `0 failed`.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (the largest new function, `_assigned`, rates 12).

- [ ] **Step 6: Commit**

```bash
git add scripts/ops/rollback_migrations.py tests/scripts/test_rollback_migrations.py
git commit -m "feat(v220): rollback_migrations -- AST classifier for one revision's upgrade()"
```

### Task V220-3b: Revision graph from a tree, `check_migrations`, `ROLLBACK_SAFE` audit

**Model:** opus — reads Alembic graphs from git trees and may mark migration files

**Files:**
- Modify: `scripts/ops/rollback_migrations.py` (import block; append below `scan_upgrade`)
- Modify: `tests/scripts/test_rollback_migrations.py` (import block; append)
- Audit target (edited only if the Step 6 audit finds an unsafe revision above the floor with a real reason; none expected today): one revision file in the `swingbot/core/db/migrations/versions/` directory

**Interfaces:**
- Consumes (V220-3): `MIGRATIONS_DIR`, `Verdict`, `scan_upgrade`, `_module_value`, `_MISSING`.
- Produces (final, per the ledger; consumed by V220-6): `@dataclass(frozen=True) Rev(revision: str, down: tuple[str, ...], path: str, source: str)`; `revision_graph(files: dict[str, str]) -> dict[str, Rev]` (files without a string `revision` are skipped; `ValueError` on an unparsable file or a duplicate revision); `tree_migrations(repo: Path, sha: str) -> dict[str, str]` (path → source of every `*.py` under `MIGRATIONS_DIR` at `sha`, `__init__.py` excluded); `head_of(graph) -> str` (`ValueError` unless exactly one head); `between(graph, target_head: str, *, known: set[str] | None = None) -> list[Rev]` (oldest first; `LookupError` when `target_head` is absent); `check_migrations(repo: Path, target_sha: str, head_sha: str) -> list[Verdict]` (raises `LookupError` / `ValueError` / `subprocess.CalledProcessError`, which V220-6 turns into a refusal). Debug CLI: `python3 rollback_migrations.py <target_sha> [--head HEAD] [--repo DIR]` (JSON list of verdicts on stdout; exit 0 all safe, 2 otherwise or `REFUSE: <why>` on stderr).

Decisions (spec § Safety check 2, index "Findings from Part 1"):
- **Which revisions are checked: the ones the target's tree does not have** (`set(head graph) - set(target graph)`), passed to `between` as `known`. Pure ancestry from the target's head is wrong here: the v197 branch tip `8562c35a` carries `v197_001` with `down_revision = "v173_002"`, while on `main` `v197_001` sits after `v201_001 → v200_001 → v205_001`; ancestry would skip those three although the target's code never saw them. `between` keeps the ancestry mode when `known` is `None` (the ledger signature) and `known` is an additive keyword.
- A target revision missing from the current graph is a `LookupError` (refuse: the current history rewrote or dropped it). A target tree with no revisions at all is a `LookupError` too.
- "Oldest first" is a topological order over the revisions returned: a revision comes after every one of its `down` revisions that is also returned; ties sort by id.
- The graph is built only from `git ls-tree` + `git show <sha>:<path>`; Alembic's `ScriptDirectory` is used only in one real-repo cross-check test (skipped when `alembic` is not importable).
- `FLOOR_TREE = "10c75111"` (release commit `release(bot,ui): bot 2.16.5 / ui 1.39.1 -- durable lifecycle notifications (v197)`) is the first `main` commit at the v197 floor whose tree carries every revision older than `v207_001`. Checked at plan time: `check_migrations(REPO, "10c75111", "HEAD")` returns `v207_001`, `v204_001`, both safe; `check_migrations(REPO, "8562c35a", "HEAD")` returns `v201_001`, `v207_001`, `v200_001` (unsafe), `v204_001`, `v205_001`.

- [ ] **Step 1: Write the failing tests**

In `tests/scripts/test_rollback_migrations.py`, replace the import block (from `import ast` to `import pytest`) with:

```python
import ast
import json
import os
import pathlib
import shutil
import subprocess
import sys
import textwrap

import pytest
```

Then append:

```python
VERSIONS = REPO / "swingbot" / "core" / "db" / "migrations" / "versions"
FLOOR_TREE = "10c75111"   # first main commit at the v197 floor (release bot 2.16.5)
V197_BRANCH_TIP = "8562c35a"
has_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

GRAPH = {  # deliberately non-numeric, with a merge revision
    "v/a.py": _mig("pass", revision="a", down=None),
    "v/b.py": _mig("pass", revision="b", down="a"),
    "v/c.py": _mig("pass", revision="c", down="a"),
    "v/m.py": _mig("pass", revision="m", down=("b", "c")),
    "v/z.py": _mig("pass", revision="z", down="m"),
    "v/y.py": _mig("pass", revision="y", down="z"),
    "v/util.py": "X = 1\n",
}


def _ids(revs):
    return [rev.revision for rev in revs]


def test_revision_graph_reads_tuples_and_skips_non_revisions():
    graph = rm.revision_graph(GRAPH)
    assert sorted(graph) == ["a", "b", "c", "m", "y", "z"]
    assert graph["m"].down == ("b", "c") and graph["a"].down == () and graph["b"].path == "v/b.py"
    assert graph["b"].source == GRAPH["v/b.py"]
    assert rm.head_of(graph) == "y"


def test_revision_graph_reads_the_one_line_unpacked_declaration():
    src = ('revision, down_revision, branch_labels, depends_on = "b", "a", None, None\n'
           "def upgrade():\n    pass\n")
    graph = rm.revision_graph({"v/a.py": GRAPH["v/a.py"], "v/b.py": src})
    assert graph["b"].down == ("a",) and rm.head_of(graph) == "b"


def test_between_walks_newer_revisions_oldest_first():
    graph = rm.revision_graph(GRAPH)
    assert _ids(rm.between(graph, "m")) == ["z", "y"]
    assert _ids(rm.between(graph, "b")) == ["c", "m", "z", "y"]
    assert _ids(rm.between(graph, "y")) == []


def test_known_catches_revisions_rebased_underneath_the_target():
    linear = rm.revision_graph({f"v/{r}.py": _mig("pass", revision=r, down=d)
                                for r, d in (("a", None), ("b", "a"), ("c", "b"), ("d", "c"))})
    assert _ids(rm.between(linear, "d")) == []
    assert _ids(rm.between(linear, "d", known={"a", "d"})) == ["b", "c"]


def test_graph_errors():
    with pytest.raises(LookupError):
        rm.between(rm.revision_graph(GRAPH), "nope")
    with pytest.raises(ValueError, match="one head"):
        rm.head_of(rm.revision_graph({k: GRAPH[k] for k in ("v/a.py", "v/b.py", "v/c.py")}))
    with pytest.raises(ValueError, match="duplicate"):
        rm.revision_graph({"v/a.py": GRAPH["v/a.py"], "v/a2.py": GRAPH["v/a.py"]})
    with pytest.raises(ValueError, match="cannot read"):
        rm.revision_graph({"v/bad.py": "revision = (\n"})


def _repo_with(tmp_path, trees):
    repo = tmp_path / "r"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@e"}

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                              env=env, check=True).stdout.strip()

    git("init", "-q")
    git("config", "commit.gpgsign", "false")
    shas = []
    for files in trees:
        for rel, text in files.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_bytes(text.encode("utf-8"))
        git("add", "-A")
        git("commit", "-q", "-m", "c")
        shas.append(git("rev-parse", "HEAD"))
    return repo, shas


@pytest.fixture
def three_commits(tmp_path):
    d = rm.MIGRATIONS_DIR
    return _repo_with(tmp_path, [
        {"README": "x\n"},
        {f"{d}/__init__.py": "", f"{d}/a.py": _mig("pass", revision="a", down=None),
         f"{d}/b.py": _mig("pass", revision="b", down="a")},
        {f"{d}/c.py": _mig('op.create_table("t")', revision="c", down="b"),
         f"{d}/d.py": _mig('op.drop_column("t", "x")', revision="d", down="c")},
    ])


@has_git
def test_check_migrations_reads_both_trees_from_git(three_commits):
    repo, shas = three_commits
    d = rm.MIGRATIONS_DIR
    assert sorted(rm.tree_migrations(repo, shas[1])) == [f"{d}/a.py", f"{d}/b.py"]
    verdicts = rm.check_migrations(repo, shas[1], shas[2])
    assert [(v.revision, v.safe, v.path) for v in verdicts] == [("c", True, f"{d}/c.py"),
                                                               ("d", False, f"{d}/d.py")]
    assert rm.check_migrations(repo, shas[2], shas[2]) == []
    with pytest.raises(LookupError, match="no Alembic revisions"):
        rm.check_migrations(repo, shas[0], shas[2])
    with pytest.raises(LookupError, match="missing from"):
        rm.check_migrations(repo, shas[2], shas[1])


@has_git
def test_cli_prints_verdicts_and_exits_by_safety(three_commits, capsys):
    repo, shas = three_commits
    assert rm.main([shas[1], "--head", shas[2], "--repo", str(repo)]) == 2
    out = json.loads(capsys.readouterr().out)
    assert [(v["revision"], v["safe"]) for v in out] == [("c", True), ("d", False)]
    assert rm.main([shas[2], "--head", shas[2], "--repo", str(repo)]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert rm.main([shas[0], "--head", shas[2], "--repo", str(repo)]) == 2
    assert capsys.readouterr().err.startswith("REFUSE: ")


def _real_files():
    return {p.relative_to(REPO).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(VERSIONS.glob("*.py")) if p.name != "__init__.py"}


def test_every_real_revision_classifies_without_error():
    graph = rm.revision_graph(_real_files())
    assert len(graph) == len(_real_files())
    for rev in graph.values():
        verdict = rm.scan_upgrade(rev.source, revision=rev.revision, path=rev.path)
        assert verdict.revision == rev.revision and isinstance(verdict.safe, bool)


def test_head_matches_alembic():
    script = pytest.importorskip("alembic.script")
    config = pytest.importorskip("alembic.config")
    cfg = config.Config(str(REPO / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO / "swingbot" / "core" / "db" / "migrations"))
    directory = script.ScriptDirectory.from_config(cfg)
    assert [rm.head_of(rm.revision_graph(_real_files()))] == list(directory.get_heads())


def test_known_data_rewrites_classify_unsafe():
    for name in ("v197_001_lifecycle_notifications.py", "v200_001_discord_issued_at.py"):
        assert not rm.scan_upgrade((VERSIONS / name).read_text(encoding="utf-8")).safe


def _has_commit(sha: str) -> bool:
    return shutil.which("git") is not None and subprocess.run(
        ["git", "-C", str(REPO), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _has_commit(FLOOR_TREE), reason="shallow checkout")
def test_every_revision_newer_than_the_floor_is_rollback_safe():
    verdicts = rm.check_migrations(REPO, FLOOR_TREE, "HEAD")
    assert [(v.revision, v.reasons) for v in verdicts if not v.safe] == []
    assert {"v207_001", "v204_001"} <= {v.revision for v in verdicts}


@pytest.mark.skipif(not _has_commit(V197_BRANCH_TIP), reason="shallow checkout")
def test_the_v197_branch_tip_sees_the_revisions_rebased_underneath_it():
    verdicts = {v.revision: v.safe for v in rm.check_migrations(REPO, V197_BRANCH_TIP, "HEAD")}
    assert {"v201_001", "v200_001", "v205_001"} <= set(verdicts)
    assert verdicts["v200_001"] is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_migrations.py`
Expected: the V220-3 tests pass; the new ones fail with `AttributeError: module 'rollback_migrations' has no attribute 'revision_graph'` (and `'MIGRATIONS_DIR'`-based fixtures with `no attribute 'check_migrations'` / `'main'`).

- [ ] **Step 3: Write the implementation**

In `scripts/ops/rollback_migrations.py`, replace the import block (from `import ast` to `from dataclasses import dataclass, field`) with:

```python
import argparse
import ast
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
```

Insert directly below the `Verdict` dataclass:

```python
@dataclass(frozen=True)
class Rev:
    revision: str
    down: tuple[str, ...]
    path: str
    source: str
```

Append below `scan_upgrade`:

```python
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
```

Notes for the implementer:
- `_git` passes `encoding="utf-8"`: revision docstrings carry non-ASCII (em dashes), and the VM's and Windows' default encodings differ.
- `tree_migrations` lists `MIGRATIONS_DIR/` non-recursively (no `-r`): revision files sit flat in that directory, and `__pycache__` is never committed.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_migrations.py`
Expected: `0 failed` (the two real-history tests skip only on a shallow checkout).

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: One-time `ROLLBACK_SAFE` audit**

Run: `python scripts/ops/rollback_migrations.py 10c75111 --head HEAD`
Expected today: exit 0, verdicts for `v207_001` and `v204_001` (plus any revision merged since), all `"safe": true` with `"override": null`.

For each revision reported unsafe: read its `upgrade()`. Add `ROLLBACK_SAFE = "<reason>"` directly below `depends_on = None` **only** when the reason is real and checkable (for example "creates the X table and back-fills it; code older than this revision never reads or writes X"). If old code would mis-handle the data the revision changed, do not mark it: stop and report to the controller that the revision needs an `INCOMPATIBLE_BOUNDARIES` entry (a ledger change, never decided inside this task). Revisions at or below the floor (`v197_001`, `v200_001` and older) are never marked: no target above the floor on `main` lacks them, and the v197 branch tip correctly refuses. Re-run Step 4 after any edit.

- [ ] **Step 7: Commit**

```bash
git add scripts/ops/rollback_migrations.py tests/scripts/test_rollback_migrations.py
git commit -m "feat(v220): rollback_migrations -- revision graph from any commit's tree, check_migrations, debug CLI"
```

(If the audit marked a migration file, commit it separately: `git add swingbot/core/db/migrations/versions/<file>.py && git commit -m "chore(v220): ROLLBACK_SAFE on <revision> -- <reason>"`.)

### Task V220-4: Config-key, compose `db` block and market-data writer checks

**Model:** sonnet — pure stdlib checks in one new module

**Files:**
- Create: `scripts/ops/rollback_checks.py`
- Create: `tests/scripts/test_rollback_checks.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (final, per the ledger; consumed by V220-5, V220-6 and v221): `CRITICAL_KEYS = ("DISCORD_TOKEN", "POSTGRES_PASSWORD", "DATABASE_URL")`; `CONFIG_PATH = "swingbot/config.py"`; `COMPOSE_PATH = "docker-compose.yml"`; `declared_config_keys(source: str) -> list[str]` (sorted, unique; raises `ValueError` when unparsable or when no `Field("<KEY>", …)` call is found; v221 `config_keys_sha256` hashes this list); `env_key_names(env_text: str) -> set[str]`; `check_config(target_config: str | None, head_config: str, env_names: set[str]) -> tuple[list[str], list[str]]` (refusals, warnings; a `None`/empty target is a refusal); `compose_db_block(compose_text: str) -> str` (raises `ValueError` when there is no `db` service); `check_compose(target_text: str | None, head_text: str) -> list[str]` (refusals); `MARKET_DATA_WRITER_PATHS: tuple[str, ...]`; `changed_writer_paths(repo: Path, target_sha: str, head_sha: str, paths=MARKET_DATA_WRITER_PATHS) -> list[str]` (sorted changed file paths; `subprocess.CalledProcessError` on a bad sha); `show(repo: Path, sha: str, path: str) -> str | None` (`None` when the path is absent at `sha`). V220-5 appends its vocabulary check and the `psql` runner to this module.

Decisions (spec § Safety checks 3, 5, 6; index notes):
- **Check 3 (config).** `swingbot/config.py` declares every key as the first positional string of a `Field(...)` call inside `FIELDS` (`Field("DISCORD_TOKEN", "TOKEN", …)`: the first argument is the `.env` name, the second the module attribute). The target's file is read with `git show` and `ast`, never imported. Refuse when any `CRITICAL_KEYS` name is missing from the current `.env` (key names only, values never read into output), or when the target's or HEAD's `config.py` cannot be read. Warn for every other key the target declares that `.env` lacks and HEAD no longer declares (a key the old code used that was since removed: the old code runs on its default). An `.env` key the target does not declare ("extra key") is neither: old code ignores it.
- **Check 5 (compose `db`).** The `db` service block is the `db:` line directly under top-level `services:` plus every following line indented deeper, up to the next sibling (`db-test` today). Comment-only and blank lines are dropped and trailing whitespace stripped before comparing (they never change what Compose runs); everything else must be byte-equal, else refuse, quoting up to four differing lines.
- **Check 6 (writer).** `MARKET_DATA_WRITER_PATHS = ("swingbot/refresher/", "swingbot/core/marketdata/data_store.py", "swingbot/core/marketdata/data_refresh.py")`: the refresher package, `save_to_disk` (the only writer of `market_data/<interval>/<TICKER>.csv`) and `refresh_symbol`. Confirmed at plan time with `git grep -n "save_to_disk(\|refresh_symbol(" -- swingbot scripts`: the other hits are callers (`swingbot/admin/freshness.py`, `swingbot/core/marketdata/fx.py`, `scripts/ops/market_cache_repair.py`, `scripts/data/fetch_intraday_cache.py`) that go through those two functions, so the on-disk format is decided by the listed paths; `backtest_cache.py` and `export_data.py` write other directories. Step 5 re-runs the grep; a new *definition* of a cache writer elsewhere is added to the tuple. `changed_writer_paths` only reports; V220-6 turns a non-empty list into the warning and `refresher: "keep-stopped"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_rollback_checks.py`:

```python
"""v220 V220-4: config-key, compose db block and market-data writer checks."""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_checks as rc  # noqa: E402

has_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _config(*keys: str) -> str:
    rows = "\n".join(f'    Field("{k}", "{k.lower()}", "S", "label", default=""),' for k in keys)
    return f"from dataclasses import dataclass\n\nFIELDS = [\n{rows}\n]\n"


ALL = ("DISCORD_TOKEN", "POSTGRES_PASSWORD", "DATABASE_URL")


def test_declared_config_keys_reads_the_first_positional_string():
    src = _config("B_KEY", "A_KEY", "B_KEY") + 'X = Field(name="NOT_POSITIONAL")\nY = Other("NOPE")\n'
    assert rc.declared_config_keys(src) == ["A_KEY", "B_KEY"]


@pytest.mark.parametrize("src,match", [("FIELDS = [\n", "unparsable"), ("X = 1\n", "no Field")])
def test_declared_config_keys_refuses_what_it_cannot_read(src, match):
    with pytest.raises(ValueError, match=match):
        rc.declared_config_keys(src)


def test_env_key_names_returns_names_only():
    env = ("# comment\n\nDISCORD_TOKEN=abc=def\nexport POSTGRES_PASSWORD = s3cret\n"
           "  DATABASE_URL=postgresql://u:p@db/x\nnot a key line\n1BAD=x\nlower_ok=1\n")
    names = rc.env_key_names(env)
    assert names == {"DISCORD_TOKEN", "POSTGRES_PASSWORD", "DATABASE_URL", "lower_ok"}
    assert not any(secret in repr(names) for secret in ("abc", "s3cret", "postgresql"))


def test_check_config_passes_when_everything_is_present():
    target = head = _config(*ALL, "OLD_OK")
    assert rc.check_config(target, head, {*ALL, "OLD_OK"}) == ([], [])


def test_a_missing_critical_key_refuses():
    refusals, warnings = rc.check_config(_config(*ALL), _config(*ALL), {"DISCORD_TOKEN", "DATABASE_URL"})
    assert refusals == ["critical key POSTGRES_PASSWORD is missing from .env"] and warnings == []


def test_a_key_removed_since_the_target_warns():
    refusals, warnings = rc.check_config(_config(*ALL, "GONE_KEY", "STILL_HERE"),
                                         _config(*ALL, "STILL_HERE"), set(ALL))
    assert refusals == []
    assert len(warnings) == 1 and warnings[0].startswith("GONE_KEY: ")


def test_an_extra_env_key_is_neither_refused_nor_warned():
    assert rc.check_config(_config(*ALL), _config(*ALL, "NEW_KEY"), {*ALL, "NEW_KEY", "STRAY"}) == ([], [])


@pytest.mark.parametrize("target,head,who", [
    ("FIELDS = [\n", _config(*ALL), "target"),
    (None, _config(*ALL), "target"),
    ("", _config(*ALL), "target"),
    (_config(*ALL), "X = 1\n", "HEAD"),
])
def test_an_unreadable_config_refuses(target, head, who):
    refusals, warnings = rc.check_config(target, head, set(ALL))
    assert len(refusals) == 1 and refusals[0].startswith(f"{who} swingbot/config.py") and warnings == []


COMPOSE = """\
# header comment
name: x
services:
  db:
    # pinned major
    image: ${SWING_BOT_DB_IMAGE:-swing-bot-db:local}
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?}

    volumes:
      - pgdata:/var/lib/postgresql

  db-test:
    image: postgres:18
  bot:
    image: ${SWING_BOT_IMAGE:-swing-bot:latest}
volumes:
  pgdata:
"""


def test_compose_db_block_stops_at_the_next_sibling_and_drops_comments():
    block = rc.compose_db_block(COMPOSE)
    assert block.splitlines() == [
        "  db:", "    image: ${SWING_BOT_DB_IMAGE:-swing-bot-db:local}", "    environment:",
        "      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?}", "    volumes:", "      - pgdata:/var/lib/postgresql"]


def test_compose_db_block_without_a_db_service_raises():
    with pytest.raises(ValueError, match="no db service"):
        rc.compose_db_block("services:\n  bot:\n    image: x\n  db-test:\n    image: y\n")


def test_check_compose_ignores_comments_and_other_services():
    other = COMPOSE.replace("# pinned major", "# reworded").replace("postgres:18", "postgres:17") \
                   .replace("swing-bot:latest", "swing-bot:old")
    assert rc.check_compose(other, COMPOSE) == []


def test_check_compose_refuses_a_changed_db_block():
    old = COMPOSE.replace("pgdata:/var/lib/postgresql", "pgdata:/var/lib/postgresql/data")
    refusals = rc.check_compose(old, COMPOSE)
    assert len(refusals) == 1 and "db service differs" in refusals[0]
    assert "/var/lib/postgresql/data" in refusals[0]


@pytest.mark.parametrize("target,head,who", [(None, COMPOSE, "target"), ("services:\n", COMPOSE, "target"),
                                             (COMPOSE, "services:\n", "HEAD")])
def test_check_compose_refuses_an_unreadable_file(target, head, who):
    refusals = rc.check_compose(target, head)
    assert len(refusals) == 1 and refusals[0].startswith(f"{who} docker-compose.yml")


def _git_repo(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@e"}

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                              env=env, check=True).stdout.strip()

    def commit(files):
        for rel, text in files.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_bytes(text.encode("utf-8"))
        git("add", "-A")
        git("commit", "-q", "-m", "c")
        return git("rev-parse", "HEAD")

    git("init", "-q")
    git("config", "commit.gpgsign", "false")
    return repo, commit


@has_git
def test_changed_writer_paths_and_show(tmp_path):
    repo, commit = _git_repo(tmp_path)
    a = commit({"swingbot/refresher/loop.py": "x = 1\n", "swingbot/core/marketdata/data_store.py": "s\n",
                "swingbot/other.py": "o\n"})
    b = commit({"swingbot/other.py": "changed\n"})
    c = commit({"swingbot/refresher/loop.py": "x = 2\n", "swingbot/refresher/new.py": "n\n"})
    assert rc.changed_writer_paths(repo, a, b) == []
    assert rc.changed_writer_paths(repo, a, c) == ["swingbot/refresher/loop.py", "swingbot/refresher/new.py"]
    assert rc.changed_writer_paths(repo, a, c, paths=("swingbot/core/marketdata/data_store.py",)) == []
    assert rc.show(repo, a, "swingbot/refresher/loop.py") == "x = 1\n"
    assert rc.show(repo, a, "swingbot/refresher/new.py") is None
    with pytest.raises(subprocess.CalledProcessError):
        rc.changed_writer_paths(repo, "0" * 40, c)


def test_the_real_config_declares_every_critical_key():
    keys = rc.declared_config_keys((REPO / rc.CONFIG_PATH).read_text(encoding="utf-8"))
    assert set(rc.CRITICAL_KEYS) <= set(keys) and len(keys) >= 200


def test_the_real_compose_db_block():
    block = rc.compose_db_block((REPO / rc.COMPOSE_PATH).read_text(encoding="utf-8"))
    assert block.startswith("  db:\n") and "${SWING_BOT_DB_IMAGE" in block
    assert "db-test" not in block and "swing-bot:latest" not in block


def test_every_writer_path_exists():
    assert all((REPO / p).exists() for p in rc.MARKET_DATA_WRITER_PATHS)


@has_git
def test_the_cache_writers_are_defined_only_inside_the_writer_paths():
    out = subprocess.run(["git", "-C", str(REPO), "grep", "-l", "-e", "def save_to_disk(",
                          "-e", "def refresh_symbol(", "--", "swingbot"],
                         capture_output=True, text=True, check=True).stdout.split()
    assert out and all(any(f.startswith(p) for p in rc.MARKET_DATA_WRITER_PATHS) for f in out), out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_checks.py`
Expected: collection error, `ModuleNotFoundError: No module named 'rollback_checks'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/ops/rollback_checks.py`:

```python
#!/usr/bin/env python3
"""v220 safety checks 3, 5 and 6 (config keys, compose db block, market-data writer).

Reads the target tree with `git show <sha>:<path>` and `ast`; never imports or runs
a target file. `.env` is read for key NAMES only -- no value ever reaches output.
Standard library only: the VM host's python3 runs this from a copy.
"""
from __future__ import annotations

import ast
import difflib
import re
import subprocess
from pathlib import Path

CRITICAL_KEYS = ("DISCORD_TOKEN", "POSTGRES_PASSWORD", "DATABASE_URL")
CONFIG_PATH = "swingbot/config.py"
COMPOSE_PATH = "docker-compose.yml"
MARKET_DATA_WRITER_PATHS: tuple[str, ...] = (
    "swingbot/refresher/",
    "swingbot/core/marketdata/data_store.py",   # save_to_disk: market_data/<interval>/<TICKER>.csv
    "swingbot/core/marketdata/data_refresh.py",  # refresh_symbol
)
_ENV_KEY = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
_DB_LINE = re.compile(r"^(\s+)db:\s*(#.*)?$")


def show(repo: Path, sha: str, path: str) -> str | None:
    """`git show <sha>:<path>` as text; None when the path is absent at that commit."""
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{sha}:{path}"], capture_output=True,
                          text=True, encoding="utf-8")
    return proc.stdout if proc.returncode == 0 else None


def _is_field_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not node.args:
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    first = node.args[0]
    return name == "Field" and isinstance(first, ast.Constant) and isinstance(first.value, str)


def declared_config_keys(source: str) -> list[str]:
    """Every `.env` key a config.py declares: the first positional string of each Field(...)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"unparsable: {exc.msg} (line {exc.lineno})") from None
    keys = {node.args[0].value for node in ast.walk(tree) if _is_field_call(node)}
    if not keys:
        raise ValueError("no Field(...) declarations found")
    return sorted(keys)


def env_key_names(env_text: str) -> set[str]:
    """Key names of a .env file; values are matched over and never kept."""
    names = set()
    for line in env_text.splitlines():
        match = _ENV_KEY.match(line)
        if match:
            names.add(match.group(1))
    return names


def _keys_or_refusal(source: str | None, who: str) -> tuple[list[str] | None, str | None]:
    if not source:
        return None, f"{who} {CONFIG_PATH} is missing or empty"
    try:
        return declared_config_keys(source), None
    except ValueError as exc:
        return None, f"{who} {CONFIG_PATH} cannot be read: {exc}"


def check_config(target_config: str | None, head_config: str,
                 env_names: set[str]) -> tuple[list[str], list[str]]:
    """Check 3: (refusals, warnings). Names only; .env values never enter the result."""
    target, refusal = _keys_or_refusal(target_config, "target")
    if refusal:
        return [refusal], []
    head, refusal = _keys_or_refusal(head_config, "HEAD")
    if refusal:
        return [refusal], []
    refusals = [f"critical key {key} is missing from .env" for key in CRITICAL_KEYS if key not in env_names]
    warnings = [f"{key}: declared by the target, no longer declared at HEAD and absent from .env "
                "(the old code runs on its default)"
                for key in target if key not in head and key not in env_names and key not in CRITICAL_KEYS]
    return refusals, warnings


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_content(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _services_children(lines: list[str]) -> list[int]:
    """Indexes of the content lines inside the top-level `services:` mapping."""
    inside, found = False, []
    for i, line in enumerate(lines):
        if _is_content(line) and _indent(line) == 0:
            inside = line.rstrip() == "services:"
            continue
        if inside and _is_content(line):
            found.append(i)
    return found


def compose_db_block(compose_text: str) -> str:
    """The `db` service block, comment-only and blank lines dropped, trailing space stripped."""
    lines = compose_text.splitlines()
    children = _services_children(lines)
    child_indent = _indent(lines[children[0]]) if children else 0
    start = next((i for i in children if _DB_LINE.match(lines[i]) and _indent(lines[i]) == child_indent), None)
    if start is None:
        raise ValueError("no db service under services:")
    block = [lines[start].rstrip()]
    for line in lines[start + 1:]:
        if _is_content(line) and _indent(line) <= child_indent:
            break
        if _is_content(line):
            block.append(line.rstrip())
    return "\n".join(block)


def _block_or_refusal(text: str | None, who: str) -> tuple[str | None, str | None]:
    if not text:
        return None, f"{who} {COMPOSE_PATH} is missing or empty"
    try:
        return compose_db_block(text), None
    except ValueError as exc:
        return None, f"{who} {COMPOSE_PATH} cannot be read: {exc}"


def check_compose(target_text: str | None, head_text: str) -> list[str]:
    """Check 5: refuse unless the target's db service block equals HEAD's."""
    target, refusal = _block_or_refusal(target_text, "target")
    if refusal:
        return [refusal]
    head, refusal = _block_or_refusal(head_text, "HEAD")
    if refusal:
        return [refusal]
    if target == head:
        return []
    diff = [d for d in difflib.unified_diff(head.splitlines(), target.splitlines(), lineterm="", n=0)
            if d[:1] in "+-" and not d.startswith(("+++", "---"))]
    return ["compose db service differs between target and HEAD (Compose would recreate Postgres): "
            + "; ".join(d.strip() for d in diff[:4])]


def changed_writer_paths(repo: Path, target_sha: str, head_sha: str,
                         paths: tuple[str, ...] = MARKET_DATA_WRITER_PATHS) -> list[str]:
    """Check 6: files under the market-data writer paths that differ between target and HEAD."""
    out = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", target_sha, head_sha, "--", *paths],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return sorted(line for line in out.splitlines() if line)
```

Notes for the implementer:
- The diff in `check_compose` lists HEAD lines as `-` and target lines as `+`, so the refusal reads "what HEAD has / what the target would bring back".
- `check_config` and `check_compose` accept `None` for the target text so V220-6 can pass `show(...)` straight through (a path absent at the target is a refusal, not a crash). The `str | None` widening is compatible with the ledger's `str`.
- Never add a `.env` value to any message: the tests assert that secret-looking values stay out of `env_key_names`' result.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_checks.py`
Expected: `0 failed`.

- [ ] **Step 5: Re-confirm the writer list and the complexity gate**

Run: `git grep -n "def save_to_disk(\|def refresh_symbol(\|market_data" -- swingbot | grep -v "^swingbot/core/marketdata/data_store.py\|^swingbot/core/marketdata/data_refresh.py\|^swingbot/refresher/"`
Expected: only readers, callers and comments (no other function that writes `market_data/<interval>/<TICKER>.csv`). If a new writer *definition* shows up, add its path to `MARKET_DATA_WRITER_PATHS` and re-run Step 4.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/ops/rollback_checks.py tests/scripts/test_rollback_checks.py
git commit -m "feat(v220): rollback_checks -- config keys, compose db block and market-data writer checks"
```

