"""rollback_to.sh's step order (spec section rollback_to.sh). The real restore is
proven by the V116-10 drill; this pins the order an edit could break."""
import pathlib

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ops" / "rollback_to.sh"


@pytest.fixture(scope="module")
def src():
    return SCRIPT.read_text(encoding="utf-8")


def test_the_steps_run_in_the_spec_order(src):
    markers = [
        "pitr_resolve.py",                                 # 1 + 3 refuse / resolve
        'if [ "$DRY_RUN" = 1 ]',                           # --dry-run stops here
        "--type=diff backup",                              # 2 checkpoint of now
        "scripts/ops/restic_hourly.sh",
        "docker compose stop bot admin",                   # 4
        "restic restore",                                  # 5
        'cat "$env_file" > .env',                          # 6 (in place)
        "env_set.py SWING_BOT_IMAGE",
        "--type=time",                                     # 7
        "scan_paused",                                     # 8 pause before start
        "docker compose up -d --no-build --wait bot admin",  # 9
    ]
    positions = [src.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_the_restore_promotes_and_uses_delta(src):
    assert "--delta" in src and "--target-action=promote" in src


def test_images_must_still_be_on_ghcr_before_anything_stops(src):
    assert src.index("docker manifest inspect") < src.index("docker compose stop bot admin")


def test_it_logs_every_rollback_and_never_sed(src):
    assert "logs/rollback.log" in src
    assert "sed -i" not in src
    assert "set -euo pipefail" in src
    assert b"\r" not in SCRIPT.read_bytes()


MONITOR_KEY_SQL = "UPDATE bot_heartbeat SET doc = doc - 'monitor' WHERE key = 'bot'"
DEPLOY_DOC = SCRIPT.parents[2] / "docs" / "deploy" / "DEPLOY_HETZNER.md"


def test_it_reminds_to_clear_the_v184_monitor_key_after_the_restart(src):
    """v184 spec section 3: a stale `monitor` key reads monitor_stale for good."""
    assert "REMINDER (v184)" in src and MONITOR_KEY_SQL in src
    start = src.index("docker compose up -d --no-build --wait bot admin")
    paused = src.index("Scanning is PAUSED")
    reminder = src.index("REMINDER (v184)")
    finished = src.index('rollback to $TARGET finished')
    assert start < paused < reminder < finished


def test_the_deploy_doc_names_the_key_removal_in_both_rollback_sections():
    doc = DEPLOY_DOC.read_text(encoding="utf-8")
    image = doc.split("\n## Rolling back\n", 1)[1].split("\n### After every deploy or rollback", 1)[0]
    pitr = doc.split("\n### Point-in-time rollback\n", 1)[1].split("\n**Backups.**", 1)[0]
    assert MONITOR_KEY_SQL in image
    assert "not_deployed" in image and "monitor_stale" in image
    assert "REMINDER (v184)" in pitr and "Rolling back" in pitr
