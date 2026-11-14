# v220 — Code-only rollback, Part 2: vocabulary check, `check` report, window report (V220-5..V220-7, V220-6b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v220 — Code-only rollback](../specs/2026-11-08-v220-code-only-rollback-design.md)
**Index:** [`2026-11-08-v220-code-only-rollback_0-index.md`](2026-11-08-v220-code-only-rollback_0-index.md) — Goal, Architecture, **Global Constraints**, CLI contract, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.

Scope of this part: safety check 4 (open-trade vocabulary, with the one read-only `psql` runner) in `scripts/ops/rollback_checks.py`; the assembled `check` report (all eight checks, including the **check 6 refusal** with its `--allow-writer-drift` override from the index's "Check 6 is a refusal" note) and the `deploy-line` writer in `scripts/ops/rollback_plan.py` (V220-6 builds the report framework and checks 1, 2, 3 and 5; V220-6b adds checks 4, 6 and 7, `deploy-line` and both CLIs, split at the 20 KB task cap); and the rollback-window key snapshot and release report in `scripts/ops/rollback_window.py`. The write-free lifecycle evaluation `swingbot.core.infra.rollback_smoke` (V220-8) sits in [Part 2b](2026-11-08-v220-code-only-rollback_2b-smoke.md), moved out to keep this file under 1500 lines.

Shared rules for these four tasks:

- `scripts/ops/rollback_*.py` stay **standard library only** and never import `swingbot`. Tests import them with `sys.path.insert(0, str(REPO / "scripts" / "ops"))`, the `tests/scripts/test_backup_manifest.py` pattern; temp repositories come from `tests/scripts/rollback_repo.py` (V220-1: `make_repo`, `sha_of`, `commit_off_main`, `git`).
- **Every database read from the VM host is read-only:** the `psql` runners pass `-e PGOPTIONS=-c default_transaction_read_only=on` to `docker compose exec`, so a typo in a query can never write. `rollback_smoke` (Part 2b) forces the same on its engine's connections.
- `.env` is read for key **names** only; no value ever reaches a report, a log line or stdout.
- **The planner runs as the `deploy` user on the VM** (V220-9 calls it as `runuser -u deploy -- python3 "$WORK/rollback_plan.py" …`): every `git` call inside it is then `deploy`'s (Global Constraints), and `deploy` already runs `docker` for CI's `deploy.sh`, so the host checks (`docker manifest inspect`, `docker compose exec db psql`) work from the same process.
- New tests in `tests/scripts/` (suite `tooling`); no `tests/suites.toml` change. Narrow runs only: `python scripts/dev/testrun.py file <test>`. `python scripts/dev/complexity_gate.py` stays green (every new function < 15).


# Phase 2 — Checks, report and smoke

### Task V220-5: Open-trade vocabulary check

**Model:** sonnet — one SQL constant and a git-grep check in one module

**Files:**
- Modify: `scripts/ops/rollback_checks.py` (append below `changed_writer_paths`)
- Create: `tests/scripts/test_rollback_vocabulary.py`

**Interfaces:**
- Consumes (V220-4): the module `scripts/ops/rollback_checks.py` and its imports (`subprocess`, `Path`); test helpers `make_repo`, `sha_of` from `tests/scripts/rollback_repo.py` (V220-1).
- Produces (final, per the ledger; consumed by V220-6): `VOCAB_FIELDS = ("status", "strategy", "source", "entry_type", "ledger", "lifecycle_kind")`; `VOCAB_SQL: str`; `PSQL: tuple[str, ...]` (the read-only `docker compose exec … psql` prefix); `psql_lines(sql: str, *, app_dir: Path, run=subprocess.run) -> list[str]` (non-blank stdout lines; `subprocess.CalledProcessError` on a failed query); `vocab_from_db(*, app_dir: Path, run=subprocess.run) -> dict[str, set[str]]` (every `VOCAB_FIELDS` key present, blank values dropped, unknown field names ignored); `missing_vocabulary(repo: Path, sha: str, values: dict[str, set[str]]) -> list[str]` (`"<field>=<value>"`, sorted by field then value; `subprocess.CalledProcessError` on a bad sha).

Decisions (spec § Safety check 4; index note "Vocabulary sources"):
- **Where the values live.** `plans` promotes `status` and `strategy` to columns; `source`, `entry_type` and `ledger` sit in its `doc` JSONB (`swingbot/core/db/schema.py:94`, promoted list). Open plans are `status IN ('PENDING', 'ACTIVE', 'PARTIAL')` (`plan_store._OPEN_STATUSES`). Open journal rows are `journal_entries` with `closed_at IS NULL` (column `strategy`). The v197 lifecycle queue is the `manual_close_notify` table; its event `kind` (`"trade_closed"`/`"plan_transition"`, `lifecycle_events.validate_event`) is a `doc` key, and an event still owed is `delivered_at IS NULL` (`notify_queue.py` reads it that way). One `UNION` query returns `field<TAB>value` rows; `UNION` already removes duplicates, and a JSON `null` or absent key prints as an empty value, which `vocab_from_db` drops.
- **Read-only by construction.** `PSQL` runs `psql` inside the `db` container with `PGOPTIONS=-c default_transaction_read_only=on`, `-X` (no `.psqlrc`), `-A -t -F <TAB>` (bare rows) and `ON_ERROR_STOP=1`, as `-U swingbot -d swingbot` (the `rollback_to.sh` precedent). The test pins that the SQL contains no write verb.
- **"Occurs in the target tree"** means a quoted literal, `"x"` or `'x'`, in any file under `swingbot/` at the target sha: `git grep -q -F -e '"x"' -e "'x'" <sha> -- swingbot`. Exit 0 = found, 1 = absent, anything else (an unknown sha) raises. A bare word in a comment does not count; a literal under `docs/` does not count.
- `exit_model` is not stored and is not checked (spec, code-brief corrections).

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_rollback_vocabulary.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_vocabulary.py`
Expected: FAIL with `AttributeError: module 'rollback_checks' has no attribute 'VOCAB_FIELDS'` (and `psql_lines`, `vocab_from_db`, `missing_vocabulary`).

- [ ] **Step 3: Write the implementation**

Append to `scripts/ops/rollback_checks.py` (below `changed_writer_paths`), and change the module docstring's first line to `v220 safety checks 3, 4, 5 and 6 (config keys, open-trade vocabulary, compose db block, market-data writer).`:

```python
# --- Check 4: open-trade vocabulary (V220-5) ---------------------------------

VOCAB_FIELDS = ("status", "strategy", "source", "entry_type", "ledger", "lifecycle_kind")
_OPEN_PLANS = "status IN ('PENDING', 'ACTIVE', 'PARTIAL')"
# One row per (field, value) stored on an open trade. `plans` promotes status and
# strategy to columns; source, entry_type and ledger live in its doc. The v197
# lifecycle queue is manual_close_notify; an undelivered event's kind is doc->>'kind'.
# UNION removes duplicates; NULLs print as empty values and are dropped by the reader.
VOCAB_SQL = f"""
SELECT 'status', status FROM plans WHERE {_OPEN_PLANS}
UNION SELECT 'strategy', strategy FROM plans WHERE {_OPEN_PLANS}
UNION SELECT 'source', doc->>'source' FROM plans WHERE {_OPEN_PLANS}
UNION SELECT 'entry_type', doc->>'entry_type' FROM plans WHERE {_OPEN_PLANS}
UNION SELECT 'ledger', doc->>'ledger' FROM plans WHERE {_OPEN_PLANS}
UNION SELECT 'strategy', strategy FROM journal_entries WHERE closed_at IS NULL
UNION SELECT 'lifecycle_kind', doc->>'kind' FROM manual_close_notify WHERE delivered_at IS NULL
ORDER BY 1, 2
"""
# psql inside the db container, every transaction read-only, bare tab-separated rows.
PSQL: tuple[str, ...] = (
    "docker", "compose", "exec", "-T", "-e", "PGOPTIONS=-c default_transaction_read_only=on", "db",
    "psql", "-X", "-U", "swingbot", "-d", "swingbot", "-v", "ON_ERROR_STOP=1", "-A", "-t", "-F", "\t", "-c",
)


def psql_lines(sql: str, *, app_dir: Path, run=subprocess.run) -> list[str]:
    """Non-blank output rows of one read-only query; CalledProcessError when it fails."""
    done = run([*PSQL, sql], cwd=str(app_dir), capture_output=True, text=True,
               encoding="utf-8", check=True)
    return [line for line in done.stdout.splitlines() if line.strip()]


def vocab_from_db(*, app_dir: Path, run=subprocess.run) -> dict[str, set[str]]:
    """field -> distinct stored values of the open trades (every VOCAB_FIELDS key present)."""
    values: dict[str, set[str]] = {field: set() for field in VOCAB_FIELDS}
    for line in psql_lines(VOCAB_SQL, app_dir=app_dir, run=run):
        field, _, value = line.partition("\t")
        if field in values and value.strip():
            values[field].add(value)
    return values


def _literal_in_tree(repo: Path, sha: str, value: str) -> bool:
    """True when "value" or 'value' occurs in a file under swingbot/ at `sha`."""
    proc = subprocess.run(["git", "-C", str(repo), "grep", "-q", "-F", "-e", f'"{value}"',
                           "-e", f"'{value}'", sha, "--", "swingbot"],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode in (0, 1):
        return proc.returncode == 0
    raise subprocess.CalledProcessError(proc.returncode, proc.args, proc.stdout, proc.stderr)


def missing_vocabulary(repo: Path, sha: str, values: dict[str, set[str]]) -> list[str]:
    """Check 4: every stored value the target tree does not know, as "<field>=<value>"."""
    return [f"{field}={value}"
            for field in sorted(values) for value in sorted(values[field])
            if not _literal_in_tree(Path(repo), sha, value)]
```

Notes for the implementer:
- `PSQL` ends with `-c`, so the SQL is the last argument; `subprocess.run` with a list never goes through a shell, so the quotes and `>` in the SQL need no escaping.
- One `git grep` per value is fine: open trades carry a few dozen distinct values at most.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_vocabulary.py`
Then: `python scripts/dev/testrun.py file tests/scripts/test_rollback_checks.py`
Expected: both `0 failed`.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/ops/rollback_checks.py tests/scripts/test_rollback_vocabulary.py
git commit -m "feat(v220): rollback_checks -- open-trade vocabulary check over a read-only psql"
```

### Task V220-6: `check` report: framework, floor, migrations, config keys, compose

**Model:** sonnet — assembles earlier checks behind one function

**Files:**
- Modify: `scripts/ops/rollback_plan.py`
- Create: `tests/scripts/test_rollback_plan_check.py`

**Interfaces:**
- Consumes: `git_out`, `_full`, `_on_main`, `_Ctx`, `Refused` (V220-1); `Boundary`, `INCOMPATIBLE_BOUNDARIES`, `floor_violations` (V220-2); `rollback_migrations.check_migrations` and the `Verdict` fields `revision`, `path`, `safe`, `reasons`, `override` (V220-3/3b); `rollback_checks.CONFIG_PATH`, `COMPOSE_PATH`, `show`, `env_key_names`, `check_config`, `check_compose` (V220-4); test helpers `make_repo`, `sha_of`, `commit_off_main` (V220-1).
- Produces (final; consumed by V220-6b, V220-9, V220-10, V220-15): `run_checks(sha: str, image: str, *, repo: Path, ref: str, env_path: Path, running_sha: str, hold_path: Path, host: bool = True, allow_writer_drift: bool = False, run=subprocess.run) -> dict` with the index CLI contract's report shape `{"ok", "noop", "refusals", "warnings", "notes", "refresher", "migrations", "hold"}` (`allow_writer_drift` and `run` are additive keywords: the first comes from the index's "Check 6 is a refusal" note, the second lets tests fake `docker`/`psql`). Private, extended by V220-6b: `@dataclass _Run(sha, image, repo, head, env_path, allow_writer_drift, run, report)`; `_CHECK_ERRORS`; `_CHECKS` (tuple of `(label, check(_Run) -> None, needs_host: bool)`); `_run_all(ctx, host)`. Test file helpers V220-6b reuses: `stack` fixture, `_check`, `_migration`, `CONFIG`, `COMPOSE`, `IMAGE`, `SAFE`, `UNSAFE`.

Decisions (spec § Safety checks 1, 2, 3, 5, 8; index notes):
- **One report, every check run.** `run_checks` runs all checks and collects every refusal instead of stopping at the first, so one dry run shows the whole picture. A check that cannot run (a git error, a missing `.env`, an unreachable `db`) is a refusal `"<check>: cannot run: <error>"`: never a crash, never a pass.
- **Order:** target on `ref` (else refuse and stop), no-op (target equals the running sha: `noop: true`, no check runs; the CLI in V220-6b exits 3), then the `_CHECKS` table. This task's table: 1 floor, 2 migrations, 3 config keys, 5 compose `db`. V220-6b inserts check 4 (vocabulary), check 6 (writer) and check 7 (image tag, registry, clean tree) at their spec positions.
- **Check 2:** every verdict lands in `migrations`; an unsafe one is a refusal naming revision, path and reasons; a `ROLLBACK_SAFE` override is a note with its reason.
- **Check 8, the hold:** an existing `deploy_hold.json` comes back in `hold` with a note that a new rollback replaces it; an unreadable one is a warning (the rollback rewrites it).
- **Floor:** `run_checks` reads `INCOMPATIBLE_BOUNDARIES` at call time (not through `floor_violations`' default, which is bound when the function is defined), so the tests' `monkeypatch.setattr(rp, "INCOMPATIBLE_BOUNDARIES", ())` reaches it.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_rollback_plan_check.py` (V220-6b appends to it; keep the fixture and helpers as written):

```python
"""v220 V220-6/6b: rollback_plan check report and deploy-line."""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_plan as rp  # noqa: E402
from tests.scripts.rollback_repo import commit_off_main, make_repo, sha_of  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

MIG = "swingbot/core/db/migrations/versions"
CONFIG = ('FIELDS = [\n    Field("DISCORD_TOKEN", "TOKEN"),\n    Field("POSTGRES_PASSWORD", "PGPW"),\n'
          '    Field("DATABASE_URL", "DB_URL"),\n{extra}]\n')
COMPOSE = "services:\n  db:\n    image: {db}\n  bot:\n    image: bot\n"
ENV = ("DISCORD_TOKEN=tok-SECRET-1\nPOSTGRES_PASSWORD=pw-SECRET-2\n"
       "DATABASE_URL=postgresql+psycopg://u:SECRET-3@h/d\n")
SAFE = '    op.create_table("t2", sa.Column("k", sa.Text))'
UNSAFE = '    op.drop_column("t1", "k")'
IMAGE = "ghcr.io/o/swing-bot:sha-"


def _migration(rev: str, down: str | None, body: str, extra: str = "") -> dict:
    text = f'revision = "{rev}"\ndown_revision = {down!r}\n{extra}\n\ndef upgrade():\n{body}\n'
    return {f"{MIG}/{rev}_x.py": text}


def _base_files() -> dict:
    return {"swingbot/config.py": CONFIG.format(extra='    Field("OLD_KEY", "OLD"),\n'),
            "docker-compose.yml": COMPOSE.format(db="pg:16"),
            "swingbot/refresher/main.py": "x = 1\n",
            "swingbot/vocab.py": 'V = ("ACTIVE", "RSI", "plan_transition")\n',
            **_migration("v1_001", None, '    op.create_table("t1", sa.Column("k", sa.Text))')}


@pytest.fixture
def stack(tmp_path, monkeypatch):
    """build(*later_commits): base (the target) -> v300 (safe table, OLD_KEY removed) -> later."""
    monkeypatch.setattr(rp, "INCOMPATIBLE_BOUNDARIES", ())
    env = tmp_path / "env"
    env.write_bytes(ENV.encode("utf-8"))

    def build(*later: dict, env_text: str | None = None) -> dict:
        if env_text is not None:
            env.write_bytes(env_text.encode("utf-8"))
        repo = make_repo(tmp_path, [
            {"subject": "chore: base", "files": _base_files()},
            {"subject": "feat(v300): new table",
             "files": {"swingbot/config.py": CONFIG.format(extra=""), **_migration("v2_001", "v1_001", SAFE)}},
            *later])
        return {"repo": repo, "target": sha_of(repo, f"HEAD~{len(later) + 1}"), "head": sha_of(repo), "env": env}
    return build


def _check(w, **kw):
    kw.setdefault("ref", "origin/main")
    kw.setdefault("env_path", w["env"])
    kw.setdefault("running_sha", w["head"])
    kw.setdefault("hold_path", w["repo"] / "backups" / "deploy_hold.json")
    kw.setdefault("host", False)
    image = kw.pop("image", IMAGE + w["target"][:12])
    return rp.run_checks(kw.pop("sha", w["target"]), image, repo=w["repo"], **kw)


def test_clean_target_passes_and_warns_about_a_removed_key(stack):
    r = _check(stack())
    assert r["ok"] is True and r["noop"] is False and r["refusals"] == []
    assert r["refresher"] == "start" and r["hold"] is None
    assert [m["revision"] for m in r["migrations"]] == ["v2_001"] and r["migrations"][0]["safe"]
    assert any("OLD_KEY" in w for w in r["warnings"])
    assert set(r) == {"ok", "noop", "refusals", "warnings", "notes", "refresher", "migrations", "hold"}


def test_target_already_running_is_a_noop(stack):
    w = stack()
    r = _check(w, running_sha=w["target"])
    assert r["noop"] is True and r["ok"] is False and r["refusals"] == [] and r["migrations"] == []


def test_unsafe_migration_refuses_naming_the_revision(stack):
    r = _check(stack({"subject": "feat(v301): drop", "files": _migration("v3_001", "v2_001", UNSAFE)}))
    assert r["ok"] is False and any("v3_001" in x for x in r["refusals"])
    assert [m["safe"] for m in r["migrations"]] == [True, False]


def test_rollback_safe_override_is_a_note(stack):
    files = _migration("v3_001", "v2_001", UNSAFE, extra='ROLLBACK_SAFE = "column was never read"')
    r = _check(stack({"subject": "feat(v301): drop", "files": files}))
    assert r["ok"] is True and any("column was never read" in n for n in r["notes"])


def test_missing_critical_key_refuses_and_no_value_leaks(stack):
    r = _check(stack(env_text="DISCORD_TOKEN=tok-SECRET-1\nPOSTGRES_PASSWORD=pw-SECRET-2\n"))
    assert any("DATABASE_URL" in x for x in r["refusals"])
    dumped = json.dumps(r)
    assert all(secret not in dumped for secret in ("tok-SECRET-1", "pw-SECRET-2", "SECRET-3"))


def test_missing_env_file_is_a_refusal_not_a_crash(stack, tmp_path):
    r = _check(stack(), env_path=tmp_path / "nope.env")
    assert any(x.startswith("config keys: cannot run") for x in r["refusals"])


def test_compose_db_change_refuses(stack):
    r = _check(stack({"subject": "chore: pg 17", "files": {"docker-compose.yml": COMPOSE.format(db="pg:17")}}))
    assert any("compose db service differs" in x for x in r["refusals"])


def test_target_below_the_floor_refuses(stack, monkeypatch):
    w = stack()
    monkeypatch.setattr(rp, "INCOMPATIBLE_BOUNDARIES", (rp.Boundary(w["head"], "v399", "reason"),))
    assert any("v399" in x for x in _check(w)["refusals"])


def test_target_off_main_refuses_and_stops(stack):
    w = stack()
    off = commit_off_main(w["repo"], "hotfix")
    r = _check(w, sha=off, image=IMAGE + off[:12])
    assert r["ok"] is False and any("not an ancestor" in x for x in r["refusals"]) and r["migrations"] == []


def test_existing_hold_is_shown_and_will_be_replaced(stack):
    w = stack()
    hold = w["repo"] / "backups" / "deploy_hold.json"
    hold.parent.mkdir(parents=True, exist_ok=True)
    hold.write_text(json.dumps({"sha": "abc123", "at": "2026-11-08T10:00:00Z"}), encoding="utf-8")
    r = _check(w)
    assert r["hold"]["sha"] == "abc123" and any("replaces it" in n for n in r["notes"])
    hold.write_text("{broken", encoding="utf-8")
    r = _check(w)
    assert r["hold"] is None and any("unreadable" in x for x in r["warnings"]) and r["ok"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_check.py`
Expected: FAIL with `AttributeError: module 'rollback_plan' has no attribute 'run_checks'`.

- [ ] **Step 3: Write the implementation**

(a) In `scripts/ops/rollback_plan.py`, directly below the standard-library imports, add the two sibling modules (V220-9 copies them next to this file into `$WORK` on the VM, so a plain import finds them there as well as in the tests' `sys.path`):

```python
import rollback_checks as rc  # sibling module (scripts/ops/, or $WORK on the VM)
import rollback_migrations as rm  # sibling module
```

(b) Insert this section directly above `def _print_refusal`:

```python
# --- V220-6: the check report ------------------------------------------------

_CHECK_ERRORS = (subprocess.CalledProcessError, LookupError, ValueError, OSError, Refused)


@dataclass
class _Run:
    sha: str
    image: str
    repo: Path
    head: str
    env_path: Path
    allow_writer_drift: bool
    run: object
    report: dict


def _new_report() -> dict:
    return {"ok": False, "noop": False, "refusals": [], "warnings": [], "notes": [],
            "refresher": "start", "migrations": [], "hold": None}


def _check_floor(c: _Run) -> None:
    for b in floor_violations(c.sha, c.repo, INCOMPATIBLE_BOUNDARIES):
        c.report["refusals"].append(f"below the compatibility floor: {b.sha} {b.plan} {b.reason}")


def _check_migrations(c: _Run) -> None:
    for v in rm.check_migrations(c.repo, c.sha, c.head):
        c.report["migrations"].append({"revision": v.revision, "safe": v.safe,
                                       "reasons": list(v.reasons), "override": v.override})
        if not v.safe:
            c.report["refusals"].append(f"migration {v.revision} ({v.path}) is not provably additive: "
                                        + "; ".join(v.reasons))
        if v.override:
            c.report["notes"].append(f"migration {v.revision} is marked ROLLBACK_SAFE: {v.override}")


def _check_config(c: _Run) -> None:
    names = rc.env_key_names(c.env_path.read_text(encoding="utf-8"))
    refusals, warnings = rc.check_config(rc.show(c.repo, c.sha, rc.CONFIG_PATH),
                                         rc.show(c.repo, c.head, rc.CONFIG_PATH) or "", names)
    c.report["refusals"].extend(refusals)
    c.report["warnings"].extend(warnings)


def _check_compose(c: _Run) -> None:
    c.report["refusals"].extend(rc.check_compose(rc.show(c.repo, c.sha, rc.COMPOSE_PATH),
                                                 rc.show(c.repo, c.head, rc.COMPOSE_PATH) or ""))


# (label, check, needs the VM host), in spec order. V220-6b inserts vocabulary (4),
# market-data writer (6) and image tag / image / clean tree (7).
_CHECKS = (
    ("floor", _check_floor, False),
    ("migrations", _check_migrations, False),
    ("config keys", _check_config, False),
    ("compose db", _check_compose, False),
)


def _read_hold(path: Path, report: dict) -> None:
    if not path.exists():
        return
    try:
        hold = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(hold, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as exc:
        report["warnings"].append(f"hold file {path} is unreadable ({exc}); a new rollback rewrites it")
        return
    report["hold"] = hold
    report["notes"].append(f"existing hold: rollback to {str(hold.get('sha', ''))[:12]} since "
                           f"{hold.get('at')}; a new rollback replaces it")


def _run_all(ctx: _Run, host: bool) -> None:
    for label, check, needs_host in _CHECKS:
        if needs_host and not host:
            ctx.report["notes"].append(f"{label}: skipped (--skip-host)")
            continue
        try:
            check(ctx)
        except _CHECK_ERRORS as exc:
            ctx.report["refusals"].append(f"{label}: cannot run: {exc}")


def run_checks(sha: str, image: str, *, repo: Path, ref: str, env_path: Path, running_sha: str,
               hold_path: Path, host: bool = True, allow_writer_drift: bool = False,
               run=subprocess.run) -> dict:
    """Every safety check for rolling back to `sha`; nothing is changed. See the CLI contract."""
    repo, report = Path(repo), _new_report()
    _read_hold(Path(hold_path), report)
    try:
        full = _on_main(_Ctx(repo, ref, Path()), sha, "target")
        head = git_out(repo, "rev-parse", f"{ref}^{{commit}}")
    except _CHECK_ERRORS as exc:
        report["refusals"].append(str(exc))
        return report
    if running_sha and _full(repo, running_sha) == full:
        report["noop"] = True
        report["notes"].append(f"target {full[:12]} is already running")
        return report
    _run_all(_Run(full, image, repo, head, Path(env_path), allow_writer_drift, run, report), host)
    report["ok"] = not report["refusals"]
    return report
```

Notes for the implementer:
- `run` and `allow_writer_drift` are carried on `_Run` but used only by the V220-6b checks; keep them in the signature now so V220-6b changes no call site.
- The report never carries a `.env` value: `_check_config` passes key names only, and an `OSError` message names the path, not the content.
- `_on_main` raises `Refused` with the "is not an ancestor of" wording for a commit off `ref`; it is in `_CHECK_ERRORS`, so that is a refusal.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_check.py`
Then: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_resolve.py` and `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_floor.py`
Expected: all three `0 failed`.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/ops/rollback_plan.py tests/scripts/test_rollback_plan_check.py
git commit -m "feat(v220): rollback_plan run_checks -- report framework, floor, migrations, config, compose"
```

### Task V220-6b: `check` host checks, writer refusal, `deploy-line`, both CLIs

**Model:** sonnet — finishes the check table and adds two thin CLI commands

**Files:**
- Modify: `scripts/ops/rollback_plan.py`
- Modify: `tests/scripts/test_rollback_plan_check.py`

**Interfaces:**
- Consumes: `run_checks`, `_Run`, `_CHECK_ERRORS`, `_CHECKS`, `_run_all`, `_check_floor`, `_check_migrations`, `_check_config`, `_check_compose` and the test helpers `stack`, `_check`, `COMPOSE`, `IMAGE` (V220-6); `git_out`, `UTC`, `dt`, `load_deploys`, `HANDLERS`, `_parser`, `_add_repo_args`, `main` (V220-1/1b/2/2b); `rollback_checks.vocab_from_db`, `missing_vocabulary` (V220-5); `rollback_checks.changed_writer_paths` (V220-4); `scripts/ops/pitr_resolve.py` `load_deploys(path: str)` (existing, untouched).
- Produces (final; consumed by V220-9, V220-10, V220-15): the full `_CHECKS` table (spec checks 1–7 in order); `DEPLOY_KINDS = ("rollback", "release")`; `deploy_line(kind: str, *, ts: str, git_sha: str, bot_image: str, db_image: str, from_sha: str) -> str` (one `sort_keys` JSON object, no newline; `ValueError` on an unknown kind or an empty field); CLI `check <sha> --image IMG [--repo] [--ref] [--env FILE] [--running-sha SHA] [--hold FILE] [--skip-host] [--allow-writer-drift]` printing the report (exit 0 ok, 2 refused, 3 no-op) and `deploy-line --kind K --sha S --image I --db-image D --from-sha F [--ts TS]` (`--ts` defaults to now, `%Y-%m-%dT%H:%M:%SZ`; `--ts` is additive to the index contract).

Decisions (spec § Safety checks 4, 6, 7, Execution step 7; index notes):
- **Check 4 (host):** `vocab_from_db(app_dir=<repo>)` then `missing_vocabulary`; each missing value is a refusal `open-trade value unknown to the target: <field>=<value>`.
- **Check 6 is a refusal** (spec amended 2026-11-08): any changed writer path sets `refresher: "keep-stopped"` and refuses unless `allow_writer_drift`, because `swingbot/admin/freshness.py` calls the same writers from the admin container. With the override it is a warning that the admin may still write `market_data/`.
- **Check 7:** the image must end in `:sha-<first 12 of the target>` (always checked, it is pure text); the registry probe is `docker manifest inspect <image>` (host); the clean tree is `git status --porcelain --untracked-files=no` (host; as `deploy`, see this part's shared rules). `--skip-host` skips the three host checks with a note each.
- **`deploy-line`** carries every field `pitr_resolve.py` reads (`ts`, `git_sha`, `bot_image`, `db_image`) plus `kind` and `from_sha`; the test parses it through `pitr_resolve.load_deploys` and this module's `load_deploys`. `--kind` is a free string so an unknown kind is a `REFUSE:` line with exit 2 like every other refusal here, not an argparse usage dump.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_rollback_plan_check.py`. Add `import pitr_resolve as pr  # noqa: E402` next to the `import rollback_plan as rp` line, then append:

```python
# --- V220-6b: host checks, writer refusal, deploy-line, CLIs -----------------


class HostRun:
    """subprocess.run stand-in for the host checks: docker manifest inspect and psql."""

    def __init__(self, vocab: str | None = "status\tACTIVE\nstrategy\tRSI\n", manifest: int = 0):
        self.vocab, self.manifest = vocab, manifest

    def __call__(self, cmd, **kw):
        if list(cmd[:3]) == ["docker", "manifest", "inspect"]:
            return subprocess.CompletedProcess(cmd, self.manifest, "", "")
        if self.vocab is None:
            raise subprocess.CalledProcessError(2, cmd, "", "db is down")
        return subprocess.CompletedProcess(cmd, 0, self.vocab, "")


def test_skip_host_skips_exactly_the_three_host_checks(stack):
    notes = _check(stack())["notes"]
    assert sorted(n for n in notes if "skipped (--skip-host)" in n) == [
        "clean tree: skipped (--skip-host)", "image: skipped (--skip-host)",
        "vocabulary: skipped (--skip-host)"]


def test_writer_drift_refuses_unless_allowed(stack):
    w = stack({"subject": "feat(v302): refresher", "files": {"swingbot/refresher/main.py": "x = 2\n"}})
    refused = _check(w)
    assert refused["ok"] is False and refused["refresher"] == "keep-stopped"
    assert any("--allow-writer-drift" in x and "freshness.py" in x for x in refused["refusals"])
    allowed = _check(w, allow_writer_drift=True)
    assert allowed["ok"] is True and allowed["refresher"] == "keep-stopped"
    assert any("admin may still write" in x for x in allowed["warnings"])


def test_image_tag_must_match_the_target(stack):
    r = _check(stack(), image=IMAGE + "0" * 12)
    assert any(x.startswith("image ") and "sha-" in x for x in r["refusals"])


def test_host_checks_pass_with_known_vocabulary_and_a_present_image(stack):
    r = _check(stack(), host=True, run=HostRun())
    assert r["ok"] is True, r["refusals"]
    assert not any("skipped" in n for n in r["notes"])


@pytest.mark.parametrize("run,expected", [
    (HostRun(vocab="strategy\tGap Reclaim\n"), "open-trade value unknown to the target: strategy=Gap Reclaim"),
    (HostRun(manifest=1), "is not on the registry"),
    (HostRun(vocab=None), "vocabulary: cannot run"),
])
def test_host_check_refusals(stack, run, expected):
    r = _check(stack(), host=True, run=run)
    assert any(expected in x for x in r["refusals"]), r["refusals"]


def test_dirty_tracked_file_refuses(stack):
    w = stack()
    (w["repo"] / "swingbot" / "vocab.py").write_bytes(b"V = ('edited live',)\n")
    r = _check(w, host=True, run=HostRun())
    assert any("local changes" in x for x in r["refusals"])


def _cli_check(w, running: str, *extra: str) -> int:
    return rp.main(["check", w["target"], "--image", IMAGE + w["target"][:12], "--repo", str(w["repo"]),
                    "--env", str(w["env"]), "--running-sha", running, "--skip-host", *extra])


def test_cli_check_exit_codes(stack, capsys):
    w = stack({"subject": "feat(v302): refresher", "files": {"swingbot/refresher/main.py": "x = 2\n"}})
    assert _cli_check(w, w["head"]) == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert _cli_check(w, w["head"], "--allow-writer-drift") == 0
    assert json.loads(capsys.readouterr().out)["refresher"] == "keep-stopped"
    assert _cli_check(w, w["target"]) == 3
    assert json.loads(capsys.readouterr().out)["noop"] is True


def test_deploy_line_parses_through_both_readers(tmp_path):
    line = rp.deploy_line("rollback", ts="2026-11-08T10:00:00Z", git_sha="a" * 40,
                          bot_image="ghcr.io/o/swing-bot:sha-aaaaaaaaaaaa", db_image="ghcr.io/o/swing-bot-db:x",
                          from_sha="b" * 40)
    row = json.loads(line)
    assert "\n" not in line and list(row) == sorted(row)
    path = tmp_path / "deploys.jsonl"
    path.write_bytes(('{"ts": "2026-11-01T10:00:00Z", "git_sha": "c", "bot_image": "b", "db_image": "d"}\n'
                      + line + "\n").encode("utf-8"))
    last = pr.load_deploys(str(path))[-1]
    assert (last["git_sha"], last["kind"], last["from_sha"]) == ("a" * 40, "rollback", "b" * 40)
    assert rp.load_deploys(path)[-1]["db_image"] == "ghcr.io/o/swing-bot-db:x"


@pytest.mark.parametrize("kind,sha", [("deploy", "a"), ("release", "")])
def test_deploy_line_refuses_unknown_kind_and_empty_fields(kind, sha):
    with pytest.raises(ValueError):
        rp.deploy_line(kind, ts="t", git_sha=sha, bot_image="b", db_image="d", from_sha="f")


def test_cli_deploy_line_defaults_ts_to_now(capsys):
    assert rp.main(["deploy-line", "--kind", "release", "--sha", "a" * 40, "--image", "b",
                    "--db-image", "d", "--from-sha", "f" * 40]) == 0
    row = json.loads(capsys.readouterr().out)
    assert row["kind"] == "release" and row["ts"].endswith("Z") and len(row["ts"]) == 20
    assert rp.main(["deploy-line", "--kind", "oops", "--sha", "a", "--image", "b",
                    "--db-image", "d", "--from-sha", "f"]) == 2
    assert "REFUSE:" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_check.py`
Expected: the V220-6 tests pass; the new ones FAIL (no skip notes, writer drift passes, `AttributeError: ... 'deploy_line'`, argparse exit 2 on `check`/`deploy-line`).

- [ ] **Step 3: Write the implementation**

(a) In `scripts/ops/rollback_plan.py`, insert directly above the `# (label, check, needs the VM host)` comment:

```python
_DRIFT = "the admin's freshness refresh (swingbot/admin/freshness.py) calls the same writers"


def _check_vocabulary(c: _Run) -> None:
    values = rc.vocab_from_db(app_dir=c.repo, run=c.run)
    for item in rc.missing_vocabulary(c.repo, c.sha, values):
        c.report["refusals"].append(f"open-trade value unknown to the target: {item}")


def _check_writer(c: _Run) -> None:
    changed = rc.changed_writer_paths(c.repo, c.sha, c.head)
    if not changed:
        return
    c.report["refresher"] = "keep-stopped"
    listed = ", ".join(changed[:5]) + (" ..." if len(changed) > 5 else "")
    if c.allow_writer_drift:
        c.report["warnings"].append(f"market-data writer differs ({listed}); the refresher stays stopped, "
                                    f"but {_DRIFT}, so the admin may still write market_data/ "
                                    "in the target's format")
    else:
        c.report["refusals"].append(f"market-data writer differs ({listed}) and {_DRIFT}; "
                                    "pass --allow-writer-drift to roll back anyway")


def _check_image_tag(c: _Run) -> None:
    if not c.image.endswith(f":sha-{c.sha[:12]}"):
        c.report["refusals"].append(f"image {c.image} is not the target's sha-{c.sha[:12]} tag")


def _check_image_exists(c: _Run) -> None:
    done = c.run(["docker", "manifest", "inspect", c.image], capture_output=True, text=True)
    if done.returncode != 0:
        c.report["refusals"].append(f"image {c.image} is not on the registry (pruned?)")


def _check_clean_tree(c: _Run) -> None:
    dirty = git_out(c.repo, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        c.report["refusals"].append("tracked files have local changes (an unmirrored live edit?): "
                                    + "; ".join(dirty.splitlines()[:3]))
```

(b) Replace the `_CHECKS` comment and table with the full one:

```python
# (label, check, needs the VM host) -- spec checks 1-7 in order; 8 is the no-op/hold.
_CHECKS = (
    ("floor", _check_floor, False),
    ("migrations", _check_migrations, False),
    ("config keys", _check_config, False),
    ("vocabulary", _check_vocabulary, True),
    ("compose db", _check_compose, False),
    ("market-data writer", _check_writer, False),
    ("image tag", _check_image_tag, False),
    ("image", _check_image_exists, True),
    ("clean tree", _check_clean_tree, True),
)
```

(c) Directly below `run_checks`, add:

```python
DEPLOY_KINDS = ("rollback", "release")


def deploy_line(kind: str, *, ts: str, git_sha: str, bot_image: str, db_image: str,
                from_sha: str) -> str:
    """One deploys.jsonl line for a rollback or release: pitr_resolve's fields plus kind/from_sha."""
    if kind not in DEPLOY_KINDS:
        raise ValueError(f"kind must be one of {', '.join(DEPLOY_KINDS)}, got {kind!r}")
    row = {"ts": ts, "git_sha": git_sha, "bot_image": bot_image, "db_image": db_image,
           "kind": kind, "from_sha": from_sha}
    empty = [key for key, value in row.items() if not value]
    if empty:
        raise ValueError(f"empty field(s): {', '.join(empty)}")
    return json.dumps(row, sort_keys=True)
```

(d) Add the two command handlers above `HANDLERS`, and replace `HANDLERS` with the line below:

```python
def _cmd_check(args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    report = run_checks(
        args.sha, args.image, repo=repo, ref=args.ref,
        env_path=Path(args.env) if args.env else repo / ".env",
        running_sha=args.running_sha or git_out(repo, "rev-parse", "HEAD"),
        hold_path=Path(args.hold) if args.hold else repo / "backups" / "deploy_hold.json",
        host=not args.skip_host, allow_writer_drift=args.allow_writer_drift)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["noop"]:
        return 3
    return 0 if report["ok"] else 2


def _cmd_deploy_line(args: argparse.Namespace) -> int:
    ts = args.ts or dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        line = deploy_line(args.kind, ts=ts, git_sha=args.sha, bot_image=args.image,
                           db_image=args.db_image, from_sha=args.from_sha)
    except ValueError as exc:
        print(f"REFUSE: {exc}", file=sys.stderr)
        return 2
    print(line)
    return 0


HANDLERS = {"resolve": _cmd_resolve, "candidates": _cmd_candidates, "floor": _cmd_floor,
            "check": _cmd_check, "deploy-line": _cmd_deploy_line}
```

(e) In `_parser`, directly before `return parser`, add:

```python
    chk = sub.add_parser("check", help="every safety check for a rollback target; changes nothing")
    chk.add_argument("sha")
    chk.add_argument("--image", required=True)
    _add_repo_args(chk)
    chk.add_argument("--env", default=None, help="default: <repo>/.env (key names only)")
    chk.add_argument("--running-sha", default=None, help="default: <repo> HEAD")
    chk.add_argument("--hold", default=None, help="default: <repo>/backups/deploy_hold.json")
    chk.add_argument("--skip-host", action="store_true",
                     help="skip the vocabulary, registry and clean-tree checks")
    chk.add_argument("--allow-writer-drift", action="store_true",
                     help="roll back although the market-data writer differs (refresher stays stopped)")
    dline = sub.add_parser("deploy-line", help="one deploys.jsonl line for a rollback or release")
    for flag in ("--kind", "--sha", "--image", "--db-image", "--from-sha"):
        dline.add_argument(flag, required=True)
    dline.add_argument("--ts", default=None, help="default: now, UTC, %%Y-%%m-%%dT%%H:%%M:%%SZ")
```

(f) Extend the module docstring's usage block with the `check …` and `deploy-line …` lines from the index CLI contract, and its exit-code line to `0 pass, 2 refused (nothing changed), 3 no-op (target already running).`

Notes for the implementer:
- The `main()` wrapper from V220-1 already turns an unexpected `CalledProcessError` (e.g. `git rev-parse HEAD` in `_cmd_check`) into `REFUSE: git failed …` with exit 2.
- `HostRun` dispatches on the command, so the test does not depend on the order the host checks call `run`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_check.py`
Then: `python scripts/dev/testrun.py file tests/scripts/test_pitr_resolve.py`
Expected: both `0 failed` (`pitr_resolve.py` itself is untouched).

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/ops/rollback_plan.py tests/scripts/test_rollback_plan_check.py
git commit -m "feat(v220): rollback_plan check/deploy-line CLIs -- vocabulary, writer refusal, image and tree checks"
```

### Task V220-7: Rollback-window key snapshot and release report

**Model:** sonnet — one new stdlib module with its own CLI

**Files:**
- Create: `scripts/ops/rollback_window.py`
- Create: `tests/scripts/test_rollback_window.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (index Parallelisation: V220-7 shares no file or contract with Lane P, so it carries its own small `psql` runner instead of importing V220-5's).
- Produces (final, per the ledger; consumed by V220-9 and V220-10): `TABLES = ("plans", "journal_entries")`; `KEYS_SQL: str`; `UPDATED_SQL: str` (a template with `{since}` and `{until}`); `updated_sql(since: str, until: str) -> str` (`ValueError` unless both are `YYYY-MM-DDTHH:MM:SSZ`); `keys_snapshot(*, app_dir: Path, run=subprocess.run) -> dict` (`{"at": <UTC Z>, "plans": {id: [keys]}, "journal_entries": {id: [keys]}}`); `window_report(snapshot: dict, current: dict, updated: dict[str, list[str]]) -> dict` (`{"tables": {<table>: {"updated": n, "new": n, "fewer_keys": [{"id", "before", "after", "dropped": [...]}]}}}`); CLI `python3 rollback_window.py snapshot --out FILE [--app-dir DIR]` and `report --snapshot FILE --since TS --until TS [--app-dir DIR]` (JSON on stdout; exit 0, or 1 with `window report failed: <why>` on stderr).

Decisions (spec § Release step 5; index CLI contract):
- **What is compared.** Rows an old writer re-saves during the hold can lose `doc` fields the newer code wrote (the reason for the v116 floor entry). At rollback time V220-9 stores the sorted top-level `doc` key names of every `plans` row (by `plan_id`) and every `journal_entries` row (by `trade_id`) in `backups/rollback_keys_<at>.json`. At release V220-10 asks for the rows whose `updated_at` falls in the window and compares their current key set with the snapshot: `updated` counts them, `new` counts those absent from the snapshot (created during the window), `fewer_keys` lists every pre-window row that lost keys, with both counts and the dropped names. Promoted columns are columns and cannot be dropped by a re-save, so only `doc` keys matter. Key **names** only, never values.
- **Read-only.** Same `docker compose exec -T -e PGOPTIONS=-c default_transaction_read_only=on db psql … -A -t -F <TAB> -c` runner as V220-5.
- **Timestamps go into SQL as text**, so `updated_sql` accepts only the exact `date -u +%Y-%m-%dT%H:%M:%SZ` shape the `deploys.jsonl` lines carry (no injection surface); anything else is a `ValueError`.
- **Snapshot file** is written to `<out>.tmp` and renamed, so a cut-off run never leaves half a JSON file for the release to read.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_rollback_window.py`:

```python
"""v220 V220-7: rollback-window doc-key snapshot and release report."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_window as rw  # noqa: E402


class FakeRun:
    def __init__(self, stdout: str = "", code: int = 0):
        self.stdout, self.code, self.calls = stdout, code, []

    def __call__(self, cmd, **kw):
        self.calls.append((list(cmd), kw))
        if self.code:
            raise subprocess.CalledProcessError(self.code, cmd, "", "psql: down")
        return subprocess.CompletedProcess(cmd, 0, self.stdout, "")


ROWS = ("plans\tP1\tentry_context,legs_realized,status_history\n"
        "plans\tP2\t\n"
        "journal_entries\tT1\tlesson,note,tags\n"
        "bogus\tX\ta\n")


def test_keys_sql_reads_both_tables_and_never_writes():
    sql = " ".join(rw.KEYS_SQL.split())
    assert "FROM plans" in sql and "FROM journal_entries" in sql and "jsonb_object_keys(doc)" in sql
    for verb in ("INSERT", "UPDATE ", "DELETE", "DROP", "ALTER", "TRUNCATE"):
        assert verb not in sql.upper()


def test_keys_snapshot_parses_rows_read_only(tmp_path):
    run = FakeRun(ROWS)
    snap = rw.keys_snapshot(app_dir=tmp_path, run=run)
    assert snap["plans"] == {"P1": ["entry_context", "legs_realized", "status_history"], "P2": []}
    assert snap["journal_entries"] == {"T1": ["lesson", "note", "tags"]}
    assert snap["at"].endswith("Z") and len(snap["at"]) == 20
    cmd, kw = run.calls[0]
    assert "PGOPTIONS=-c default_transaction_read_only=on" in cmd and cmd[-1] == rw.KEYS_SQL
    assert kw["cwd"] == str(tmp_path)


def test_updated_sql_embeds_only_well_formed_timestamps():
    sql = rw.updated_sql("2026-11-08T10:00:00Z", "2026-11-09T12:30:00Z")
    assert "updated_at >= '2026-11-08T10:00:00Z'" in sql and "updated_at <= '2026-11-09T12:30:00Z'" in sql
    for bad in ("2026-11-08", "2026-11-08T10:00:00Z'; DROP TABLE plans; --", ""):
        with pytest.raises(ValueError):
            rw.updated_sql(bad, "2026-11-09T12:30:00Z")


def test_window_report_counts_updated_new_and_dropped_keys():
    snapshot = {"at": "x", "plans": {"P1": ["a", "b", "c"], "P2": ["a"]}, "journal_entries": {"T1": ["n"]}}
    current = {"plans": {"P1": ["a"], "P2": ["a", "z"], "P9": ["a"]}, "journal_entries": {}}
    updated = {"plans": ["P2", "P1", "P9"]}
    report = rw.window_report(snapshot, current, updated)
    assert report["tables"]["plans"] == {
        "updated": 3, "new": 1,
        "fewer_keys": [{"id": "P1", "before": 3, "after": 1, "dropped": ["b", "c"]}]}
    assert report["tables"]["journal_entries"] == {"updated": 0, "new": 0, "fewer_keys": []}


def test_cli_snapshot_writes_the_file_atomically(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rw, "_RUN", FakeRun(ROWS))
    out = tmp_path / "keys.json"
    assert rw.main(["snapshot", "--out", str(out), "--app-dir", str(tmp_path)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["plans"]["P2"] == []
    assert not (tmp_path / "keys.json.tmp").exists()
    assert str(out) in capsys.readouterr().out


def test_cli_report_prints_the_window_report(tmp_path, monkeypatch, capsys):
    snap = tmp_path / "keys.json"
    snap.write_text(json.dumps({"at": "x", "plans": {"P1": ["a", "b"]}, "journal_entries": {}}), encoding="utf-8")
    run = FakeRun("plans\tP1\ta\n")
    monkeypatch.setattr(rw, "_RUN", run)
    assert rw.main(["report", "--snapshot", str(snap), "--since", "2026-11-08T10:00:00Z",
                    "--until", "2026-11-09T10:00:00Z", "--app-dir", str(tmp_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["tables"]["plans"]["fewer_keys"][0]["dropped"] == ["b"]
    assert "2026-11-08T10:00:00Z" in run.calls[0][0][-1]


@pytest.mark.parametrize("args", [
    ["report", "--snapshot", "MISSING", "--since", "2026-11-08T10:00:00Z", "--until", "2026-11-09T10:00:00Z"],
    ["report", "--snapshot", "SNAP", "--since", "yesterday", "--until", "2026-11-09T10:00:00Z"],
])
def test_cli_report_failures_exit_1(tmp_path, monkeypatch, capsys, args):
    snap = tmp_path / "keys.json"
    snap.write_text('{"plans": {}, "journal_entries": {}}', encoding="utf-8")
    monkeypatch.setattr(rw, "_RUN", FakeRun())
    args = [str(tmp_path / "nope.json") if a == "MISSING" else str(snap) if a == "SNAP" else a for a in args]
    assert rw.main([*args, "--app-dir", str(tmp_path)]) == 1
    assert "window report failed" in capsys.readouterr().err


def test_cli_snapshot_psql_failure_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rw, "_RUN", FakeRun(code=2))
    assert rw.main(["snapshot", "--out", str(tmp_path / "k.json"), "--app-dir", str(tmp_path)]) == 1
    assert not (tmp_path / "k.json").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_window.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'rollback_window'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/ops/rollback_window.py`:

```python
#!/usr/bin/env python3
"""v220 rollback window: doc-key snapshot at rollback, rows changed during it at release.

    python3 rollback_window.py snapshot --out FILE [--app-dir DIR]
    python3 rollback_window.py report --snapshot FILE --since TS --until TS [--app-dir DIR]

Reads Postgres through `docker compose exec db psql` with every transaction read-only.
Key NAMES only, never values. Standard library only: the VM host's python3 runs it
from a copy outside the checkout.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

TABLES = ("plans", "journal_entries")
_ID = {"plans": "plan_id", "journal_entries": "trade_id"}
_KEYS = "COALESCE((SELECT string_agg(k, ',' ORDER BY k) FROM jsonb_object_keys(doc) AS k), '')"
KEYS_SQL = (f"SELECT 'plans', plan_id, {_KEYS} FROM plans\n"
            f"UNION ALL SELECT 'journal_entries', trade_id, {_KEYS} FROM journal_entries\n")
UPDATED_SQL = (f"SELECT 'plans', plan_id, {_KEYS} FROM plans\n"
               "  WHERE updated_at >= '{since}' AND updated_at <= '{until}'\n"
               f"UNION ALL SELECT 'journal_entries', trade_id, {_KEYS} FROM journal_entries\n"
               "  WHERE updated_at >= '{since}' AND updated_at <= '{until}'\n")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_PSQL = ("docker", "compose", "exec", "-T", "-e", "PGOPTIONS=-c default_transaction_read_only=on", "db",
         "psql", "-X", "-U", "swingbot", "-d", "swingbot", "-v", "ON_ERROR_STOP=1", "-A", "-t", "-F", "\t", "-c")
_RUN = subprocess.run  # test seam for the CLI


def _psql(sql: str, app_dir: Path, run) -> list[str]:
    done = run([*_PSQL, sql], cwd=str(app_dir), capture_output=True, text=True,
               encoding="utf-8", check=True)
    return [line for line in done.stdout.splitlines() if line.strip()]


def _key_map(lines: list[str]) -> dict[str, dict[str, list[str]]]:
    """table -> {row id -> sorted doc key names}; rows of other tables are ignored."""
    found: dict[str, dict[str, list[str]]] = {table: {} for table in TABLES}
    for line in lines:
        table, _, rest = line.partition("\t")
        row_id, _, keys = rest.partition("\t")
        if table in found and row_id:
            found[table][row_id] = sorted(k for k in keys.split(",") if k)
    return found


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def keys_snapshot(*, app_dir: Path, run=subprocess.run) -> dict:
    """{"at", "plans": {id: [keys]}, "journal_entries": {id: [keys]}} for every row."""
    return {"at": _now(), **_key_map(_psql(KEYS_SQL, Path(app_dir), run))}


def updated_sql(since: str, until: str) -> str:
    for value in (since, until):
        if not _TS.match(value or ""):
            raise ValueError(f"timestamp must be YYYY-MM-DDTHH:MM:SSZ, got {value!r}")
    return UPDATED_SQL.format(since=since, until=until)


def _table_report(before: dict, now: dict, ids: list[str]) -> dict:
    fewer = []
    for row_id in sorted(set(ids) & set(before)):
        after = now.get(row_id, [])
        dropped = sorted(set(before[row_id]) - set(after))
        if dropped:
            fewer.append({"id": row_id, "before": len(before[row_id]), "after": len(after), "dropped": dropped})
    return {"updated": len(ids), "new": len(set(ids) - set(before)), "fewer_keys": fewer}


def window_report(snapshot: dict, current: dict, updated: dict[str, list[str]]) -> dict:
    """Rows updated in the window, new rows, and pre-window rows that lost doc keys."""
    return {"tables": {table: _table_report(snapshot.get(table, {}), current.get(table, {}),
                                            list(updated.get(table, [])))
                       for table in TABLES}}


def _cmd_snapshot(args: argparse.Namespace) -> int:
    snap = keys_snapshot(app_dir=Path(args.app_dir), run=_RUN)
    out = Path(args.out)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(snap, sort_keys=True), encoding="utf-8")
    tmp.replace(out)
    counts = ", ".join(f"{table} {len(snap[table])}" for table in TABLES)
    print(f"snapshot {out}: {counts}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    sql = updated_sql(args.since, args.until)
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    current = _key_map(_psql(sql, Path(args.app_dir), _RUN))
    updated = {table: sorted(rows) for table, rows in current.items()}
    print(json.dumps(window_report(snapshot, current, updated), indent=2, sort_keys=True))
    return 0


HANDLERS = {"snapshot": _cmd_snapshot, "report": _cmd_report}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="v220 rollback-window snapshot and report")
    sub = parser.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot", help="doc key names of every plans/journal_entries row")
    snap.add_argument("--out", required=True)
    rep = sub.add_parser("report", help="rows updated during the window vs the snapshot")
    rep.add_argument("--snapshot", required=True)
    rep.add_argument("--since", required=True)
    rep.add_argument("--until", required=True)
    for cmd in (snap, rep):
        cmd.add_argument("--app-dir", default=".")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return HANDLERS[args.cmd](args)
    except (subprocess.CalledProcessError, OSError, ValueError) as exc:
        detail = getattr(exc, "stderr", None) or exc
        print(f"window report failed: {str(detail).strip()}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

Notes for the implementer:
- `UPDATED_SQL` mixes f-string parts (the `_KEYS` expression, filled at import) with plain parts keeping literal `{since}`/`{until}` for `str.format`; `_KEYS` itself contains no braces, so `.format` touches only the two placeholders. Keep that split as written.
- The "updated" set is exactly the rows the window query returns, so `current` and `updated` come from the same query; `window_report` keeps them separate so V220-10 or a test can pass any combination.
- `json.loads` of a broken snapshot raises `json.JSONDecodeError`, a `ValueError`, so it exits 1 like a missing file.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_window.py`
Expected: `0 failed`.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/ops/rollback_window.py tests/scripts/test_rollback_window.py
git commit -m "feat(v220): rollback_window -- doc-key snapshot at rollback and the release-time window report"
```

