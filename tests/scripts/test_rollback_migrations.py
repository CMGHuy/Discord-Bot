"""v220 V220-3/3b: AST migration scanner and the revision graph built from a git tree."""
from __future__ import annotations

import ast
import json
import os
import pathlib
import shutil
import subprocess
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
