"""The v116 PITR cron scripts' shape. They run only on the VM; what is
pinned is what an edit would silently break."""
import os
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
OPS = REPO / "scripts" / "ops"
NAMES = ["pitr_backup.sh", "restic_hourly.sh", "pitr_verify.sh", "install_pitr_crons.sh"]


def _text(name):
    return (OPS / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", NAMES)
def test_strict_mode_and_lf(name):
    assert "set -" in _text(name)
    assert b"\r" not in (OPS / name).read_bytes()
    assert "sed -i" not in _text(name)


def test_backup_is_full_on_sunday_and_differential_otherwise():
    text = _text("pitr_backup.sh")
    assert "TYPE=diff" in text and "TYPE=full" in text and "%u" in text
    assert 'pgbackrest --stanza=swingbot --type="$TYPE" backup' in text


def test_env_versions_are_pruned_after_the_backup():
    text = _text("pitr_backup.sh")
    assert text.index("backup </dev/null") < text.index("env_snapshot prune backups/env 30")


def test_restic_snapshots_market_data_and_keeps_thirty_days():
    text = _text("restic_hourly.sh")
    assert "restic backup" in text and "market_data" in text
    assert "--keep-within 30d --keep-tag stable --prune" in text
    assert "env_set.py --get RESTIC_PASSWORD" in text


def test_verify_checks_both_repos_and_prints_a_verdict():
    text = _text("pitr_verify.sh")
    assert "pgbackrest --stanza=swingbot verify" in text
    assert "restic check" in text
    assert "VERDICT" in text


def test_installer_is_idempotent_and_schedules_all_three():
    text = _text("install_pitr_crons.sh")
    assert "grep -vF" in text
    for name in ("pitr_backup.sh", "restic_hourly.sh", "pitr_verify.sh"):
        assert name in text


def test_the_vm_setup_installs_restic_and_python3():
    text = (REPO / "deploy" / "hetzner-setup.sh").read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith("apt-get install -y ca-certificates"))
    assert "restic" in line and "python3" in line


def test_installer_wraps_each_cron_in_flock_with_shared_restic_lock():
    text = _text("install_pitr_crons.sh")
    assert "flock -n -E 199" in text and "mkdir -p" in text
    assert 'cronline "7 * * * *" restic_hourly.sh restic ' in text
    assert 'cronline "0 4 1 * *" pitr_verify.sh restic ' in text
    assert "cronline \"30 2 * * *\" pitr_backup.sh pitr_backup " in text


def _run_installer_twice(bash, tmp_path, store):
    (tmp_path / "scripts" / "ops").mkdir(parents=True)
    for n in ("pitr_backup.sh", "restic_hourly.sh", "pitr_verify.sh"):
        (tmp_path / "scripts" / "ops" / n).write_text("")
    env = {**os.environ, "BASE": tmp_path.as_posix()}
    # crontab buffers stdin first, like the real one (the reader runs concurrently).
    # crontab is an exported bash function: a stub file is not executable on Windows.
    fn = (f'crontab() {{ if [ "$1" = "-l" ]; then cat "{store.as_posix()}"; '
          f'else d=$(cat); printf "%s\n" "$d" > "{store.as_posix()}"; fi; }}; export -f crontab; '
          f'bash "{(OPS / "install_pitr_crons.sh").as_posix()}"')
    for _ in range(2):
        subprocess.run([bash, "-c", fn], env=env, check=True, capture_output=True)


def _lock_of(line):
    return next(t for t in line.split() if t.endswith(".lock"))


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


def test_wrapped_scripts_never_exit_with_the_flock_skip_code():
    """The cron wrapper treats exit 199 as 'lock held, skipped'; a script that
    could exit 199 would have a real failure logged as a skip."""
    import re
    for name in ("pitr_backup.sh", "restic_hourly.sh", "pitr_verify.sh"):
        codes = re.findall(r"exit\s+(\S+)", _text(name))
        assert all(c in ("0", "1", '"$rc"') for c in codes), (name, codes)


def _assert_flock_lines(cron):
    assert len(cron) == 3 and all("skipped: previous run" in l for l in cron)
    restic = [l for l in cron if "restic_hourly" in l or "pitr_verify" in l]
    assert _lock_of(restic[0]) == _lock_of(restic[1])
    assert _lock_of(next(l for l in cron if "pitr_backup" in l)) != _lock_of(restic[0])


def test_installer_really_is_idempotent_and_replaces_old_lines(tmp_path):
    bash = _working_bash(OPS / "install_pitr_crons.sh", tmp_path)
    if bash is None:
        pytest.skip("no bash that can see host paths")
    store = tmp_path / "cron.txt"
    store.write_text("0 3 * * * /x/backup_db.sh\n7 * * * * /old/restic_hourly.sh >> l 2>&1\n")
    _run_installer_twice(bash, tmp_path, store)
    lines = store.read_text().splitlines()
    assert sum("backup_db.sh" in l for l in lines) == 1
    assert sum("restic_hourly.sh" in l for l in lines) == 1
    assert not any("/old/" in l for l in lines)
    _assert_flock_lines([l for l in lines if "flock" in l])
    assert (tmp_path / "logs").is_dir()


def test_restic_forget_keeps_stable_snapshots_forever():
    """v120: a stable point's market_data must outlive the 30-day window.
    restic keeps a snapshot when ANY keep policy matches."""
    text = _text("restic_hourly.sh")
    forget = next(l for l in text.splitlines() if "restic forget" in l)
    assert "--keep-within 30d" in forget and "--keep-tag stable" in forget
