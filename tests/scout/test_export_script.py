"""scripts/ops/export_book_rows.sh runs only on the VM, piped through
ssh-hetzner.sh, so CI cannot run its psql half. What is pinned is what a broken
edit would remove: the READ ONLY session, the absence of every write keyword,
the fixed column list, the host log path, and the rejections reducer (run
locally against fake logs through the SWING_BOT_DIR / BOOK_LOGS_DIR seams)."""
import os
import re
import shutil
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
    "days_to_earnings", "rs_percentile",
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
    done = subprocess.run([_bash(), "-n"], input=source, text=True,
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
