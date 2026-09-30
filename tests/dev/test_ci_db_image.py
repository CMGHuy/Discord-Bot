"""CI builds the PITR db image, the deploy receives it, and GHCR keeps
every tag long enough for a 30-day rollback (v116 Phase 0)."""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")
WORKFLOWS = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def test_a_job_builds_the_db_image_from_its_own_inputs():
    job = _load("deploy.yml")["jobs"]["db-image"]
    text = yaml.safe_dump(job)
    assert "Dockerfile.db" in text
    assert "deploy/db/pgbackrest.conf" in text
    assert "pgcfg-" in text
    # Immutable once pushed: an existing tag is never rebuilt over.
    assert "docker manifest inspect" in text


def test_the_deploy_waits_for_and_passes_the_db_image():
    deploy = _load("deploy.yml")["jobs"]["deploy"]
    assert "db-image" in deploy["needs"]
    step = deploy["steps"][0]
    assert "SWING_BOT_DB_IMAGE" in step["with"]["envs"]
    assert step["env"]["SWING_BOT_DB_IMAGE"] == "${{ needs.db-image.outputs.image }}"


def test_ghcr_retention_covers_the_rollback_window_for_both_images():
    step = _load("registry-retention.yml")["jobs"]["prune"]["steps"][0]
    cut = step["with"]["cut-off"]
    assert cut.endswith("d") and int(cut[:-1]) >= 30
    assert "-db" in step["with"]["image-names"]
