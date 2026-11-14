"""v220 V220-5: open-trade vocabulary check (safety check 4)."""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_checks as rc  # noqa: E402
from tests.scripts.rollback_repo import make_repo, sha_of  # noqa: E402

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

VOCAB_PY = (
    'STATUSES = ("PENDING", "ACTIVE")\n'
    "STRATEGIES = ('RSI', \"Break & Retest\")\n"
    'KINDS = ("plan_transition",)\n'
)


class FakeRun:
    """Stands in for subprocess.run; records every call."""

    def __init__(self, stdout: str = "", code: int = 0):
        self.stdout, self.code, self.calls = stdout, code, []

    def __call__(self, cmd, **kw):
        self.calls.append((list(cmd), kw))
        if self.code and kw.get("check"):
            raise subprocess.CalledProcessError(self.code, cmd, output="", stderr="psql: boom")
        return subprocess.CompletedProcess(args=cmd, returncode=self.code, stdout=self.stdout, stderr="")


def test_vocab_sql_names_every_field():
    assert rc.VOCAB_FIELDS == ("status", "strategy", "source", "entry_type", "ledger", "lifecycle_kind")
    for field in rc.VOCAB_FIELDS:
        assert f"'{field}'" in rc.VOCAB_SQL


def test_vocab_sql_reads_only_open_rows_and_never_writes():
    sql = " ".join(rc.VOCAB_SQL.split())
    assert "status IN ('PENDING', 'ACTIVE', 'PARTIAL')" in sql
    assert "FROM journal_entries WHERE closed_at IS NULL" in sql
    assert "FROM manual_close_notify WHERE delivered_at IS NULL" in sql
    for verb in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"):
        assert verb not in sql.upper()


def test_vocab_sql_columns_exist_in_the_schema():
    schema = pytest.importorskip("swingbot.core.db.schema")
    wanted = {"plans": ("status", "strategy", "doc"),
              "journal_entries": ("strategy", "closed_at"),
              "manual_close_notify": ("delivered_at", "doc")}
    for table, columns in wanted.items():
        for column in columns:
            assert column in schema.METADATA.tables[table].c, f"{table}.{column}"


def test_psql_lines_runs_read_only_psql_in_the_app_dir(tmp_path):
    run = FakeRun("status\tACTIVE\n\nstrategy\tRSI\n")
    assert rc.psql_lines("SELECT 1", app_dir=tmp_path, run=run) == ["status\tACTIVE", "strategy\tRSI"]
    cmd, kw = run.calls[0]
    assert cmd[:4] == ["docker", "compose", "exec", "-T"]
    assert "PGOPTIONS=-c default_transaction_read_only=on" in cmd
    assert cmd[cmd.index("-F") + 1] == "\t" and cmd[-1] == "SELECT 1"
    assert {"-A", "-t", "-X"} <= set(cmd) and "ON_ERROR_STOP=1" in cmd
    assert kw["cwd"] == str(tmp_path) and kw["check"] is True


def test_psql_failure_raises(tmp_path):
    with pytest.raises(subprocess.CalledProcessError):
        rc.psql_lines("SELECT 1", app_dir=tmp_path, run=FakeRun(code=1))


def test_vocab_from_db_groups_values_by_field(tmp_path):
    run = FakeRun("status\tACTIVE\nstrategy\tRSI\nstrategy\tBreak & Retest\n"
                  "ledger\t\nlifecycle_kind\tplan_transition\nbogus\tx\n")
    values = rc.vocab_from_db(app_dir=tmp_path, run=run)
    assert set(values) == set(rc.VOCAB_FIELDS)
    assert values["strategy"] == {"RSI", "Break & Retest"}
    assert values["ledger"] == set() and values["source"] == set()
    assert values["lifecycle_kind"] == {"plan_transition"}
    assert run.calls[0][0][-1] == rc.VOCAB_SQL


@pytest.fixture
def tree(tmp_path):
    repo = make_repo(tmp_path, [{"subject": "chore: base",
                                 "files": {"swingbot/vocab.py": VOCAB_PY, "docs/x.md": '"Turtle Soup"\n'}}])
    return repo, sha_of(repo)


@needs_git
def test_every_value_present_passes(tree):
    repo, sha = tree
    values = {"status": {"PENDING", "ACTIVE"}, "strategy": {"RSI", "Break & Retest"},
              "lifecycle_kind": {"plan_transition"}, "ledger": set()}
    assert rc.missing_vocabulary(repo, sha, values) == []


@needs_git
def test_absent_value_is_named_and_docs_do_not_count(tree):
    repo, sha = tree
    values = {"strategy": {"RSI", "Turtle Soup"}, "status": {"PARTIAL"}}
    assert rc.missing_vocabulary(repo, sha, values) == ["status=PARTIAL", "strategy=Turtle Soup"]


@needs_git
def test_a_bare_word_is_not_a_quoted_literal(tmp_path):
    repo = make_repo(tmp_path, [{"subject": "c",
                                 "files": {"swingbot/a.py": "# RSI without quotes\nx = 'RSIX'\n"}}])
    assert rc.missing_vocabulary(repo, sha_of(repo), {"strategy": {"RSI"}}) == ["strategy=RSI"]


@needs_git
def test_the_target_tree_is_read_not_the_head_tree(tmp_path):
    repo = make_repo(tmp_path, [
        {"subject": "old", "files": {"swingbot/vocab.py": 'S = ("RSI",)\n'}},
        {"subject": "new", "files": {"swingbot/vocab.py": 'S = ("RSI", "Gap Reclaim")\n'}},
    ])
    wanted = {"strategy": {"Gap Reclaim"}}
    assert rc.missing_vocabulary(repo, sha_of(repo, "HEAD~1"), wanted) == ["strategy=Gap Reclaim"]
    assert rc.missing_vocabulary(repo, sha_of(repo), wanted) == []


@needs_git
def test_bad_sha_raises(tree):
    repo, _ = tree
    with pytest.raises(subprocess.CalledProcessError):
        rc.missing_vocabulary(repo, "f" * 40, {"status": {"ACTIVE"}})
