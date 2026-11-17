"""The v229 weekly cron scripts (plan v229 V229-11). They run only on the VM;
these tests pin their shape and run both under a stubbed crontab and docker.
crontab and docker are exported bash functions: a stub file is not
executable on Windows (the precedent is tests/scripts/test_pitr_crons.py)."""
import os
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
OPS = REPO / "scripts" / "ops"
RUNNER, INSTALLER = "v229_pairs_cron.sh", "install_v229_cron.sh"
T0 = "2026-11-16T09:00:00+00:00"
MARKER = "# v229 deferred-entry pairs"
EXPORT_OK = 'echo "row_kind,trade_id"\necho "trade,t-1"\n'
EXPORT_FAIL = 'echo "partial"\nexit 3\n'


def _text(name):
    return (OPS / name).read_text(encoding="utf-8")


def _working_bash(*paths):
    """A bash that resolves these host paths, or None. On Windows `bash` can be
    WSL's, which cannot see `C:/...`; Git for Windows' bash is tried next."""
    git = shutil.which("git")
    candidates = [shutil.which("bash")]
    if git:
        candidates.append(str(pathlib.Path(git).resolve().parents[1] / "usr" / "bin" / "bash.exe"))
    test = " && ".join(f'test -e "{p.as_posix()}"' for p in paths)
    for bash in filter(None, candidates):
        try:
            if subprocess.run([bash, "-c", test], capture_output=True, timeout=20).returncode == 0:
                return bash
        except OSError:
            continue
    return None


@pytest.fixture
def bash(tmp_path):
    found = _working_bash(OPS / RUNNER, tmp_path)
    if found is None:
        pytest.skip("no bash that can see host paths")
    return found


def _crontab_fn(store):
    return (f'crontab() {{ if [ "$1" = "-l" ]; then cat "{store.as_posix()}" 2>/dev/null; '
            f'else d=$(cat); printf "%s\n" "$d" > "{store.as_posix()}"; fi; }}; export -f crontab; ')


def _install(bash, tmp_path, store, t0=T0):
    env = {**os.environ, "SWING_BOT_DIR": tmp_path.as_posix()}
    cmd = _crontab_fn(store) + f'bash "{(OPS / INSTALLER).as_posix()}" "{t0}"'
    return subprocess.run([bash, "-c", cmd], env=env, capture_output=True, text=True)


def _run_runner(bash, tmp_path, *, export_body, docker_rc=0, args=(T0,)):
    ops = tmp_path / "scripts" / "ops"
    ops.mkdir(parents=True, exist_ok=True)
    (ops / "export_book_rows.sh").write_text(export_body, encoding="utf-8", newline="\n")
    fn = f'docker_stub() {{ echo "DOCKER $*"; return {docker_rc}; }}; export -f docker_stub; '
    env = {**os.environ, "SWING_BOT_DIR": tmp_path.as_posix(), "DOCKER": "docker_stub"}
    quoted = " ".join(f'"{a}"' for a in args)
    cmd = fn + f'bash "{(OPS / RUNNER).as_posix()}" {quoted}'
    return subprocess.run([bash, "-c", cmd], env=env, capture_output=True, text=True)


def _log(tmp_path):
    return (tmp_path / "logs" / "v229-pairs.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", [RUNNER, INSTALLER])
def test_strict_mode_lf_and_no_in_place_sed(name):
    assert "set -" in _text(name)
    assert b"\r" not in (OPS / name).read_bytes()
    assert "sed -i" not in _text(name)


def test_installer_is_weekly_marked_and_rewrites_its_own_line():
    text = _text(INSTALLER)
    assert f"MARKER='{MARKER}'" in text
    assert "15 8 * * 6 /bin/bash" in text
    assert "grep -vF" in text


def test_runner_calls_the_cli_in_append_mode_only():
    text = _text(RUNNER)
    assert "scripts/reports/deferred_entry_counterfactual.py" in text
    assert "--mode append" in text
    assert "--mode verdict" not in text and "--mode exploratory" not in text


def test_runner_exports_then_appends(bash, tmp_path):
    out = _run_runner(bash, tmp_path, export_body=EXPORT_OK)
    assert out.returncode == 0, out.stderr
    v229 = tmp_path / "data" / "v229"
    assert (v229 / "rows.csv").read_text(encoding="utf-8").splitlines() == [
        "row_kind,trade_id", "trade,t-1"]
    assert not (v229 / "rows.csv.tmp").exists()
    log = _log(tmp_path)
    assert log.startswith("=== ")
    docker = [line for line in log.splitlines() if line.startswith("DOCKER ")]
    assert docker == ["DOCKER compose exec -T bot python "
                      "scripts/reports/deferred_entry_counterfactual.py "
                      f"--mode append --rows data/v229/rows.csv --t0 {T0}"]


def test_a_failed_export_keeps_the_last_rows_and_appends_nothing(bash, tmp_path):
    v229 = tmp_path / "data" / "v229"
    v229.mkdir(parents=True)
    (v229 / "rows.csv").write_text("old\n", encoding="utf-8")
    out = _run_runner(bash, tmp_path, export_body=EXPORT_FAIL)
    assert out.returncode == 1
    assert (v229 / "rows.csv").read_text(encoding="utf-8") == "old\n"
    assert not (v229 / "rows.csv.tmp").exists()
    log = _log(tmp_path)
    assert "export failed" in log
    assert "DOCKER" not in log


def test_a_failed_append_is_the_runner_exit_status(bash, tmp_path):
    out = _run_runner(bash, tmp_path, export_body=EXPORT_OK, docker_rc=5)
    assert out.returncode == 5
    assert "DOCKER compose exec" in _log(tmp_path)


def test_runner_without_t0_does_nothing(bash, tmp_path):
    out = _run_runner(bash, tmp_path, export_body=EXPORT_OK, args=())
    assert out.returncode != 0
    assert not (tmp_path / "logs" / "v229-pairs.log").exists()
    assert not (tmp_path / "data" / "v229" / "rows.csv").exists()


def test_installer_is_idempotent_and_replaces_an_old_v229_line(bash, tmp_path):
    store = tmp_path / "cron.txt"
    store.write_text("0 3 * * * /x/backup_db.sh\n" + MARKER + "\n"
                     "15 8 * * 6 /bin/bash /old/scripts/ops/v229_pairs_cron.sh "
                     "2026-01-01T00:00:00+00:00\n", encoding="utf-8")
    for _ in range(2):
        out = _install(bash, tmp_path, store)
        assert out.returncode == 0, out.stderr
    lines = store.read_text(encoding="utf-8").splitlines()
    assert sum("backup_db.sh" in line for line in lines) == 1
    assert lines.count(MARKER) == 1
    v229 = [line for line in lines if "v229_pairs_cron.sh" in line]
    assert v229 == [f"15 8 * * 6 /bin/bash {tmp_path.as_posix()}/scripts/ops/v229_pairs_cron.sh {T0}"]
    assert (tmp_path / "logs").is_dir() and (tmp_path / "data" / "v229").is_dir()


@pytest.mark.parametrize("bad", ["2026-11-16", "2026-11-16T09:00:00",
                                 "2026-11-16 09:00:00+00:00", "2026-11-16T09:00:00+00:00 x"])
def test_installer_refuses_a_malformed_t0(bash, tmp_path, bad):
    store = tmp_path / "cron.txt"
    store.write_text("0 3 * * * /x/backup_db.sh\n", encoding="utf-8")
    out = _install(bash, tmp_path, store, t0=bad)
    assert out.returncode == 2
    assert "T0" in out.stderr
    assert store.read_text(encoding="utf-8") == "0 3 * * * /x/backup_db.sh\n"
