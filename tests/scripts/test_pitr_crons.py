"""The v116 PITR cron scripts' shape. They run only on the VM; what is
pinned is what an edit would silently break."""
import pathlib

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
    assert "--keep-within 30d --prune" in text
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
