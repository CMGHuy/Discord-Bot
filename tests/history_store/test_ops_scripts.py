"""v162 AH20: the weekly update cron installer and the store pull. Both reach
the VM, so what is pinned is what an edit could silently break."""
import os
import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
OPS = REPO / "scripts" / "ops"
INSTALL = OPS / "install_v162_history_cron.sh"
PULL = OPS / "pull_history_store.sh"
MARKER = "# v162 alpaca history store weekly update (installed by install_v162_history_cron.sh)"


def _text(path):
    return path.read_text(encoding="utf-8")


def _remote_block(src):
    return src[src.index("<<'REMOTE_EOF'"):src.index("\nREMOTE_EOF")]


@pytest.mark.parametrize("path", [INSTALL, PULL])
def test_house_rules(path):
    src = _text(path)
    assert src.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in src
    assert "sed -i" not in src
    assert b"\r" not in path.read_bytes()


# --- installer ---------------------------------------------------------------

def test_cron_runs_the_update_then_the_check_in_their_own_containers():
    src = _text(INSTALL)
    assert MARKER in src
    line = next(l for l in src.splitlines() if l.startswith("CRON_LINE="))
    assert "'30 6 * * 0 cd /opt/swing-bot && " in line
    update = "/usr/bin/docker compose run --rm -T bot python scripts/data/fetch_alpaca_history.py --mode update"
    check = "/usr/bin/docker compose run --rm -T bot python scripts/data/check_history_store.py --verify-hashes"
    assert line.index(update) < line.index(check)
    assert 'echo "update exit $?"' in line and 'echo "check exit $?"' in line
    assert ">> /opt/swing-bot/logs/history_store_cron.log 2>&1" in line
    assert "compose exec" not in src


def test_cron_percent_signs_are_escaped():
    """cron turns a bare % into a newline."""
    line = next(l for l in _text(INSTALL).splitlines() if l.startswith("CRON_LINE="))
    assert re.search(r"(?<!\\)%", line) is None


def _working_bash(*paths):
    """A bash that resolves these host paths, or None (on Windows `bash` can be
    WSL's, which cannot see C:/...; Git for Windows' bash is tried next)."""
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


def test_installer_is_idempotent_and_replaces_an_older_line(tmp_path):
    bash = _working_bash(INSTALL, tmp_path)
    if bash is None:
        pytest.skip("no bash that can see host paths")
    store = tmp_path / "cron.txt"
    store.write_text("0 3 * * * /x/backup_db.sh\n"
                     "0 5 * * 0 cd /old && docker compose run bot python scripts/data/fetch_alpaca_history.py --mode update\n")
    # crontab is an exported bash function: a stub file is not executable on Windows.
    fn = (f'crontab() {{ if [ "$1" = "-l" ]; then cat "{store.as_posix()}"; '
          f'else d=$(cat); printf "%s\\n" "$d" > "{store.as_posix()}"; fi; }}; export -f crontab; '
          f'bash "{INSTALL.as_posix()}"')
    env = {**os.environ, "BASE": tmp_path.as_posix()}
    for _ in range(2):
        subprocess.run([bash, "-c", fn], env=env, check=True, capture_output=True)
    lines = store.read_text().splitlines()
    assert sum(l == MARKER for l in lines) == 1
    assert sum("fetch_alpaca_history.py --mode update" in l for l in lines) == 1
    assert not any("/old" in l for l in lines)
    assert sum("backup_db.sh" in l for l in lines) == 1
    assert (tmp_path / "logs").is_dir()


@pytest.mark.parametrize("path", [INSTALL, PULL])
def test_scripts_parse(path):
    bash = _working_bash(path)
    if bash is None:
        pytest.skip("no bash that can see host paths")
    assert subprocess.run([bash, "-n", path.as_posix()], capture_output=True).returncode == 0


# --- pull --------------------------------------------------------------------

def test_pull_reaches_the_vm_only_through_the_wrapper():
    src = _text(PULL)
    assert 'SSH_HETZNER="${SSH_HETZNER:-' in src
    assert 'bash "$SSH_HETZNER" "bash -s -- $*"' in src
    assert not re.search(r"(^|[\s;|&(])(ssh|scp)\s", src, re.M)
    for line in src.splitlines():
        if "SSH_HETZNER" in line and "bash -s" in line:
            assert "$(" not in line, line


def test_pull_streams_each_timeframe_as_base64_tar():
    src = _text(PULL)
    remote = _remote_block(src)
    assert "cd /opt/swing-bot/data/market_data" in remote
    assert 'tar czf - "$ARG" | base64 -w0' in remote
    assert "15min|hourly|daily)" in remote
    assert 'TIMEFRAMES="15min hourly daily"' in src
    assert 'base64 -d | tar xzf - -C "$PARTIAL"' in src


def test_the_remote_side_only_reads():
    remote = _remote_block(_text(PULL))
    assert "rm " not in remote
    assert "docker" not in remote
    assert not re.search(r"[^2&]>\s*[\"'$/a-zA-Z]", remote)


def test_pull_targets_the_main_trees_history_store_not_the_live_cache():
    src = _text(PULL)
    assert 'DEST="${HISTORY_PULL_DEST:-$MAIN_ROOT/data/market_data}"' in src
    assert "git rev-parse --path-format=absolute --git-common-dir" in src
    assert 'PARTIAL="$DEST.partial"' in src


def test_hashes_are_verified_before_the_swap():
    src = _text(PULL)
    body = src[src.index("pull() {"):]
    body = body[:body.index("\n}")]
    verify = body.index('verify "$PARTIAL"')
    assert verify < body.index('mv "$DEST" "$DEST.prev"')
    assert verify < body.index('mv "$PARTIAL" "$DEST"')
    assert "check_history_store.py --root" in src and "--verify-hashes" in src


def test_an_existing_partial_is_never_overwritten():
    body = _text(PULL)
    body = body[body.index("pull() {"):]
    assert body.index('if [ -e "$PARTIAL" ]') < body.index('mkdir -p "$PARTIAL"')


def test_probe_compares_one_small_file_by_sha256():
    src = _text(PULL)
    remote = _remote_block(src)
    assert "probe-hash)" in remote and "probe-stream)" in remote
    assert "daily/_manifest.json" in remote
    assert '"${1:-}" = "--probe"' in src
