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
        "parity_report.py --dual",
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
