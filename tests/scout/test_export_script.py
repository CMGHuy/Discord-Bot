"""scripts/ops/export_book_rows.sh runs only on the VM, piped through
ssh-hetzner.sh, so CI cannot run its psql half. What is pinned is what a broken
edit would remove: the READ ONLY session, the absence of every write keyword,
the fixed column list, the host log path, and the rejections reducer (run
locally against fake logs through the SWING_BOT_DIR / BOOK_LOGS_DIR seams)."""
import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "export_book_rows.sh"

EXPECTED_COLUMNS = (
    "row_kind", "trade_id", "plan_id", "ticker", "strategy", "horizon", "direction",
    "plan_created_at", "plan_first_status_at", "plan_status", "plan_status_reason",
    "entry_type", "expiry_bars", "valid_session", "planned_entry", "opened_at", "entry",
    "stop_loss", "take_profit", "target2", "closed_at", "exit_price", "close_reason",
    "last_leg_reason", "outcome", "r_realized", "mfe_r", "mae_r", "exit_efficiency",
    "holding_days", "stop_width_atr", "atr_pct", "regime2_state", "session_bucket",
    "days_to_earnings", "rs_percentile", "plan_issued_at", "plan_issued_at_source",
    "excursion_source",
)

# Word-bounded and case-sensitive: `updated_at` / `created_at` must not trip it,
# a real SQL write keyword (even in a comment) must.
WRITE_KEYWORDS = re.compile(r"\b(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP|CREATE)\b")
ALIAS = re.compile(r"\bAS ([a-z][a-z0-9_]*)\b")


@pytest.fixture(scope="module")
def source() -> str:
    assert SCRIPT.exists(), "scripts/ops/export_book_rows.sh is missing"
    return SCRIPT.read_text(encoding="utf-8").replace("\r\n", "\n")


def select_aliases(source: str) -> tuple[list[str], list[str]]:
    """The output aliases of the trade SELECT and of the plan SELECT, in order."""
    body = source[source.index("COPY ("):source.index(") TO STDOUT")]
    trade_part, plan_part = body.split("UNION ALL")
    return ALIAS.findall(trade_part), ALIAS.findall(plan_part)


def test_it_fails_fast(source):
    assert re.search(r"^set -euo pipefail$", source, re.M)


def test_the_session_is_read_only_before_the_query(source):
    guard = "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;"
    assert guard in source
    assert source.index(guard) < source.index("COPY (")


def test_no_write_keyword_appears_anywhere(source):
    assert WRITE_KEYWORDS.findall(source) == []


def test_the_keyword_guard_itself_catches_a_write():
    assert WRITE_KEYWORDS.findall("x; DELETE FROM plans; updated_at created_at") == ["DELETE"]


def test_the_export_is_one_copy_to_stdout_with_a_header(source):
    assert source.count("COPY (") == 1
    assert ") TO STDOUT WITH (FORMAT csv, HEADER true);" in source
    assert source.count("UNION ALL") == 1


def test_both_selects_list_the_export_columns_in_order(source):
    trade_aliases, plan_aliases = select_aliases(source)
    assert trade_aliases == list(EXPECTED_COLUMNS)
    assert plan_aliases == list(EXPECTED_COLUMNS)


def test_psql_runs_in_the_db_container_quietly(source):
    assert "docker compose exec -T db psql -U swingbot -d swingbot" in source
    assert " -q " in source          # no "SET" / "COPY n" tags in the CSV
    assert "ON_ERROR_STOP=1" in source


def test_logs_are_read_on_the_host_not_the_container_path(source):
    assert "/opt/swing-bot/logs" in source
    assert "/app/logs" not in source
    assert 'grep -h "plan rejected ("' in source
    assert 'echo "date,reason,count"' in source


def test_no_python_runs_on_the_vm(source):
    assert "python" not in source.lower()


def test_the_body_is_parsed_before_it_runs(source):
    """The script arrives on stdin: everything sits in functions, run by the last line."""
    lines = [ln for ln in source.splitlines() if ln.strip()]
    assert lines[-1] == 'main "$@"'


def _bash() -> str:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on PATH")
    return bash


def test_bash_parses_the_script(source):
    done = subprocess.run([_bash(), "-n"], input=source.encode("utf-8"),
                          capture_output=True, timeout=30)
    assert done.returncode == 0, done.stderr


def _write_log(path: Path, lines: list[str]) -> None:
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _seen_by_bash(env: dict, var: str) -> bool:
    probe = subprocess.run([_bash(), "-c", f'test -d "${var}"'], env=env, timeout=30)
    return probe.returncode == 0


def test_rejections_reduce_to_date_reason_count(source, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_log(logs / "bot.log", [
        "2026-03-05 10:00:00,000 INFO swingbot.scan: NVDA (2w, up): plan rejected "
        "(no_qualifying_target, stop 1.00% from entry) -- not posted",
        "2026-03-05 10:00:01,000 INFO swingbot.scan: scan finished",
    ])
    _write_log(logs / "bot.log.1", [
        "2026-03-04 15:01:02,123 INFO swingbot.scan: AAPL (2w, up): plan rejected "
        "(risk_cap, stop 3.10% from entry) -- not posted",
        "2026-03-04 15:02:02,123 INFO swingbot.scan: MSFT (1m, up): plan rejected "
        "(risk_cap, stop 2.00% from entry) -- not posted",
    ])
    env = dict(os.environ, SWING_BOT_DIR=tmp_path.as_posix(), BOOK_LOGS_DIR=logs.as_posix())
    if not _seen_by_bash(env, "BOOK_LOGS_DIR"):
        pytest.skip("this bash cannot see the Windows temp dir (WSL bash)")
    done = subprocess.run([_bash(), "-s", "--", "rejections"], input=source, env=env,
                          text=True, capture_output=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [
        "date,reason,count",
        "2026-03-04,risk_cap,2",
        "2026-03-05,no_qualifying_target,1",
    ]
    assert "bot.log.1 starts 2026-03-04 15:01:02" in done.stderr


def test_an_unknown_mode_exits_two(source, tmp_path):
    env = dict(os.environ, SWING_BOT_DIR=tmp_path.as_posix())
    if not _seen_by_bash(env, "SWING_BOT_DIR"):
        pytest.skip("this bash cannot see the Windows temp dir (WSL bash)")
    done = subprocess.run([_bash(), "-s", "--", "nope"], input=source, env=env,
                          text=True, capture_output=True, timeout=30)
    assert done.returncode == 2
    assert "rows|rejections" in done.stderr


def test_rejections_fail_when_no_log_files_exist(source, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    env = dict(os.environ, SWING_BOT_DIR=tmp_path.as_posix(), BOOK_LOGS_DIR=logs.as_posix())
    if not _seen_by_bash(env, "BOOK_LOGS_DIR"):
        pytest.skip("this bash cannot see the Windows temp dir (WSL bash)")
    done = subprocess.run([_bash(), "-s", "--", "rejections"], input=source.encode("utf-8"),
                          env=env, capture_output=True, timeout=30)
    assert done.returncode != 0
    assert b"no readable log files" in done.stderr
    assert done.stdout == b""


def test_rejections_propagate_grep_read_failure(source, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_log(logs / "bot.log", ["2026-03-05 INFO scan finished"])
    env = dict(os.environ, SWING_BOT_DIR=tmp_path.as_posix(), BOOK_LOGS_DIR=logs.as_posix())
    if not _seen_by_bash(env, "BOOK_LOGS_DIR"):
        pytest.skip("this bash cannot see the Windows temp dir (WSL bash)")
    command = 'grep() { return 2; }; export -f grep; bash -s -- rejections'
    done = subprocess.run([_bash(), "-c", command], input=source.encode("utf-8"),
                          env=env, capture_output=True, timeout=30)
    assert done.returncode != 0


@pytest.fixture
def book_rows_db():
    """Only synthetic rows; the real export SELECT runs without a VM/database service."""
    with sqlite3.connect(":memory:") as conn:
        conn.executescript("""
            CREATE TABLE journal_entries (
                trade_id TEXT, closed_at TEXT, outcome TEXT, doc TEXT
            );
            CREATE TABLE trades (
                trade_id TEXT, ticker TEXT, strategy TEXT, horizon TEXT, direction TEXT,
                opened_at TEXT, entry REAL, stop_loss REAL, doc TEXT
            );
            CREATE TABLE plans (
                plan_id TEXT, ticker TEXT, strategy TEXT, horizon_key TEXT,
                created_at TEXT, status TEXT, valid_session TEXT, doc TEXT
            );
            INSERT INTO plans (plan_id, doc) VALUES
                ('closed-plan', '{}'), ('open-plan', '{}'), ('unfilled-plan', '{}'),
                ('missing-journal-plan', '{}'), ('unclosed-journal-plan', '{}');
            INSERT INTO trades (trade_id, doc) VALUES
                ('closed-trade', '{"plan_id":"closed-plan"}'),
                ('open-trade', '{"plan_id":"open-plan"}'),
                ('another-open-trade', '{"plan_id":"closed-plan"}'),
                ('missing-journal-trade', '{"plan_id":"missing-journal-plan"}'),
                ('unclosed-journal-trade', '{"plan_id":"unclosed-journal-plan"}'),
                ('orphan-closed-trade', '{}');
            INSERT INTO journal_entries (trade_id, closed_at, doc) VALUES
                ('closed-trade', '2026-10-15', '{}'),
                ('unclosed-journal-trade', NULL, '{}'),
                ('orphan-closed-trade', '2026-10-15', '{}');
        """)
        yield conn


def _sqlite_query(source: str) -> str:
    """The rows COPY body, with projection-only PostgreSQL syntax adapted for sqlite."""
    query = source.split("COPY (", 1)[1].split(") TO STDOUT", 1)[0]
    return query.replace("::text", "").replace("->(-1)", "->'$[#-1]'")


def test_rows_include_each_plan_and_preserve_closed_trades(source, book_rows_db):
    """An open trade must not hide its plan from the issued-plan denominator."""
    cursor = book_rows_db.execute(_sqlite_query(source))
    assert tuple(column[0] for column in cursor.description) == EXPECTED_COLUMNS
    rows = [(row[0], row[1], row[2]) for row in cursor.fetchall()]
    assert sorted(rows) == [
        ("plan", None, "missing-journal-plan"),
        ("plan", None, "open-plan"),
        ("plan", None, "unclosed-journal-plan"),
        ("plan", None, "unfilled-plan"),
        ("trade", "closed-trade", "closed-plan"),
        ("trade", "orphan-closed-trade", None),
    ]


def test_the_issued_columns_read_the_plan_doc(source, book_rows_db):
    book_rows_db.execute(
        "UPDATE plans SET doc = ? WHERE plan_id = 'unfilled-plan'",
        ('{"issued_at": "2026-08-04T13:02:11+00:00", "issued_at_source": "discord"}',))
    book_rows_db.execute(
        "UPDATE plans SET doc = ? WHERE plan_id = 'closed-plan'",
        ('{"issued_at": "2026-10-15T14:31:07+00:00"}',))
    cursor = book_rows_db.execute(_sqlite_query(source))
    names = [column[0] for column in cursor.description]
    pid, at, src = (names.index(n) for n in ("plan_id", "plan_issued_at", "plan_issued_at_source"))
    got = {row[pid]: (row[at], row[src]) for row in cursor.fetchall()}
    assert got["unfilled-plan"] == ("2026-08-04T13:02:11+00:00", "discord")
    assert got["closed-plan"] == ("2026-10-15T14:31:07+00:00", None)
    assert got["open-plan"] == (None, None)


def test_excursion_source_is_column_39_in_both_branches(source):
    trade_aliases, plan_aliases = select_aliases(source)
    assert len(trade_aliases) == len(plan_aliases) == 39
    assert trade_aliases[38] == plan_aliases[38] == "excursion_source"
    assert "j.doc->>'excursion_source' AS excursion_source" in source
    assert "NULL::text AS excursion_source" in source


def test_the_positional_order_by_is_unchanged(source):
    assert "ORDER BY 1 DESC, 21, 8, 2, 3" in source
    trade_aliases, _ = select_aliases(source)
    assert [trade_aliases[i - 1] for i in (1, 21, 8, 2, 3)] == [
        "row_kind", "closed_at", "plan_created_at", "trade_id", "plan_id"]


def test_the_header_comment_counts_39_columns(source):
    assert "rows: 39" in source
    assert "rows: 38" not in source


def test_the_excursion_column_reads_the_journal_doc(source, book_rows_db):
    book_rows_db.execute(
        "UPDATE journal_entries SET doc = ? WHERE trade_id = 'closed-trade'",
        ('{"excursion_source": "5min", "mfe_r": 0.31}',))
    cursor = book_rows_db.execute(_sqlite_query(source))
    names = [column[0] for column in cursor.description]
    kind, tid, pid, src = (names.index(n) for n in ("row_kind", "trade_id", "plan_id",
                                                     "excursion_source"))
    got = {(row[kind], row[tid] or row[pid]): row[src] for row in cursor.fetchall()}
    assert got[("trade", "closed-trade")] == "5min"
    assert got[("trade", "orphan-closed-trade")] is None          # doc '{}': no source yet
    assert got[("plan", "unfilled-plan")] is None                 # plan rows are NULL
    assert got[("plan", "open-plan")] is None


# --- v232: the reconcile mode (JSON lines for live_replay_reconcile.py) -----------

READ_ONLY = "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;"


def reconcile_body(source: str) -> str:
    """export_reconcile and export_deploys: from the reconcile function to main."""
    return source[source.index("export_reconcile() {"):source.index("\nmain() {")]


def test_reconcile_has_its_own_read_only_guard_before_its_first_select(source):
    body = reconcile_body(source)
    assert READ_ONLY in body
    assert body.index(READ_ONLY) < body.index("SELECT")
    assert "SET TIME ZONE 'UTC';" in body


def test_reconcile_is_json_lines_not_a_second_copy(source):
    body = reconcile_body(source)
    assert "COPY (" not in body and "UNION ALL" not in body
    assert " -A -t " in body and " -X -q " in body and "ON_ERROR_STOP=1" in body
    assert body.count("SELECT row_to_json(x) FROM (") == 3
    assert "<<'SQL'" in body                # quoted: bash expands nothing in the SQL


def test_reconcile_plan_lines_join_trade_and_journal_docs(source):
    body = reconcile_body(source)
    assert "'plan'::text AS kind," in body
    assert all(f" AS {alias}" in body for alias in ("plan", "trade", "journal"))
    assert "LEFT JOIN trades t ON t.doc->>'plan_id' = p.plan_id" in body
    assert "LEFT JOIN journal_entries j ON j.trade_id = t.trade_id" in body
    assert "WHERE p.created_at >= (:'since')::timestamptz" in body


def _merge_of(body: str, alias: str) -> str:
    """The SQL expression emitted AS <alias> in the reconcile plan select: the
    select lists one aliased expression per line, from `AS kind` to FROM plans."""
    select = body[body.index("'plan'::text AS kind"):body.index("FROM plans p")]
    lines = [line.strip() for line in select.splitlines()]
    out = []
    for line in lines[lines.index(f"-- {alias}") + 1:]:
        if line.startswith("--"):
            break
        out.append(line)
    return " ".join(out)


PLAN_COLUMNS = ("plan_id", "ticker", "strategy", "horizon_key", "status", "created_at",
                "valid_session")
TRADE_COLUMNS = ("trade_id", "ticker", "strategy", "horizon", "direction", "status",
                 "opened_at", "closed_at", "entry", "stop_loss")
JOURNAL_COLUMNS = ("trade_id", "strategy", "outcome", "closed_at", "created_at")


@pytest.mark.parametrize("alias, alias_of, columns", [
    ("plan", "p", PLAN_COLUMNS), ("trade", "t", TRADE_COLUMNS),
    ("journal", "j", JOURNAL_COLUMNS)])
def test_reconcile_merges_the_identity_columns_into_each_doc(source, alias, alias_of, columns):
    # The docs do not hold the columns promoted out of them (schema.py), so the
    # export puts them back like codec.merge_doc: the columns are the right operand, so a
    # non-null column overrides a stale doc copy, and null columns are stripped (omitted).
    expr = _merge_of(reconcile_body(source), alias)
    for column in columns:
        assert f"'{column}', {alias_of}.{column}" in expr
    assert f"{alias_of}.doc || jsonb_strip_nulls(jsonb_build_object(" in expr
    assert f"|| {alias_of}.doc" not in expr
    assert expr.count("jsonb_build_object(") == 1 and expr.rstrip(" ,").endswith(f"AS {alias}")


@pytest.mark.parametrize("alias, alias_of, key", [("trade", "t", "trade_id"),
                                                  ("journal", "j", "trade_id")])
def test_reconcile_keeps_a_missing_left_join_row_null(source, alias, alias_of, key):
    expr = _merge_of(reconcile_body(source), alias)
    assert f"CASE WHEN {alias_of}.{key} IS NULL THEN NULL ELSE" in expr


def test_reconcile_rejection_and_watchlist_lines(source):
    body = reconcile_body(source)
    assert ("'rejection'::text AS kind, r.ticker AS ticker, r.gate AS gate, "
            "r.strategy AS strategy, r.horizon AS horizon, r.signal_date AS signal_date") in body
    assert "FROM gate_rejections r" in body and "WHERE r.signal_date >= :'since'" in body
    assert "'watchlist'::text AS kind, w.ticker AS ticker, w.added_at AS added_at" in body
    watch = body[body.index("FROM watchlist w"):]
    assert "WHERE" not in watch.split(") x;")[0]          # the whole table


def test_reconcile_date_reaches_sql_only_as_a_psql_variable(source):
    body = reconcile_body(source)
    assert '-v since="$since"' in body
    sql = body[body.index("<<'SQL'"):body.rindex("\nSQL\n")]
    assert "$since" not in sql and "${" not in sql


def test_the_rows_copy_is_still_the_first_and_only_copy(source):
    assert source.index("COPY (") < source.index("export_reconcile() {")


PLAN_LINE = '{"kind":"plan","plan":{"plan_id":"P1"},"trade":null,"journal":null}'
WATCH_LINE = '{"kind":"watchlist","ticker":"AAA","added_at":"2026-09-01T00:00:00+00:00"}'
DOCKER_STUB = (
    'docker() { echo "ARGS $*" >&2; cat >/dev/null; '
    f"printf '%s\n' '{PLAN_LINE}' '{WATCH_LINE}'; }}; export -f docker; "
)


def _run_reconcile(source, tmp_path, *args, stub=DOCKER_STUB):
    env = dict(os.environ, SWING_BOT_DIR=tmp_path.as_posix())
    if not _seen_by_bash(env, "SWING_BOT_DIR"):
        pytest.skip("this bash cannot see the Windows temp dir (WSL bash)")
    command = stub + "bash -s -- reconcile " + " ".join(args)
    return subprocess.run([_bash(), "-c", command], input=source.encode("utf-8"),
                          env=env, capture_output=True, timeout=60)


@pytest.mark.parametrize("since", ["", "2026-9-15", "yesterday", "'2026-09-15;'"])
def test_reconcile_refuses_a_missing_or_malformed_date_before_any_query(source, tmp_path, since):
    stub = 'docker() { echo CALLED >&2; return 9; }; export -f docker; '
    done = _run_reconcile(source, tmp_path, since, stub=stub)
    assert done.returncode == 2
    assert b"YYYY-MM-DD" in done.stderr
    assert b"CALLED" not in done.stderr and done.stdout == b""


def test_reconcile_streams_psql_then_wraps_each_deploy_line(source, tmp_path):
    (tmp_path / "backups").mkdir()
    (tmp_path / "backups" / "deploys.jsonl").write_bytes(
        b'{"at":"2026-09-15T08:54:50Z","commit":"abc1234"}\n'
        b"\n"
        b'{"at":"2026-10-02T10:00:00Z","commit":"def5678"}\r\n')
    done = _run_reconcile(source, tmp_path, "2026-09-15")
    assert done.returncode == 0, done.stderr
    assert done.stdout.decode("utf-8").splitlines() == [
        PLAN_LINE,
        WATCH_LINE,
        '{"kind":"deploy","entry":{"at":"2026-09-15T08:54:50Z","commit":"abc1234"}}',
        '{"kind":"deploy","entry":{"at":"2026-10-02T10:00:00Z","commit":"def5678"}}',
    ]
    args = done.stderr.decode("utf-8")
    assert "-A -t" in args and "since=2026-09-15" in args
    assert "compose exec -T db psql -U swingbot -d swingbot" in args


def test_reconcile_without_a_deploy_file_prints_no_deploy_line(source, tmp_path):
    done = _run_reconcile(source, tmp_path, "2026-09-15")
    assert done.returncode == 0, done.stderr
    assert b'"kind":"deploy"' not in done.stdout
    assert done.stdout.decode("utf-8").splitlines() == [PLAN_LINE, WATCH_LINE]


def test_reconcile_fails_when_psql_fails_and_prints_no_deploys(source, tmp_path):
    (tmp_path / "backups").mkdir()
    (tmp_path / "backups" / "deploys.jsonl").write_bytes(b'{"at":"x","commit":"y"}\n')
    stub = 'docker() { cat >/dev/null; return 3; }; export -f docker; '
    done = _run_reconcile(source, tmp_path, "2026-09-15", stub=stub)
    assert done.returncode != 0
    assert b'"kind":"deploy"' not in done.stdout


def test_the_usage_line_names_the_reconcile_mode(source, tmp_path):
    env = dict(os.environ, SWING_BOT_DIR=tmp_path.as_posix())
    if not _seen_by_bash(env, "SWING_BOT_DIR"):
        pytest.skip("this bash cannot see the Windows temp dir (WSL bash)")
    done = subprocess.run([_bash(), "-s", "--", "nope"], input=source, env=env,
                          text=True, capture_output=True, timeout=30)
    assert done.returncode == 2
    assert "rows|rejections|reconcile <since YYYY-MM-DD>" in done.stderr
