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
