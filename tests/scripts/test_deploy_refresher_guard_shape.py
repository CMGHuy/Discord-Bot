"""v201: deploy.sh must not start or verify the refresher on an image without it."""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def src():
    return (ROOT / "deploy" / "deploy.sh").read_text(encoding="utf-8")


def test_the_image_is_probed_for_the_refresher_module(src):
    assert 'import swingbot.refresher' in src and '"$IMAGE"' in src.split("import swingbot.refresher")[0][-200:]


def test_up_starts_only_the_probed_services(src):
    assert "docker compose up -d --no-build --wait $SERVICES" in src
    assert "docker compose up -d --no-build --wait\n" not in src


def test_the_probe_runs_before_the_services_start(src):
    assert src.index("import swingbot.refresher") < src.index("up -d --no-build --wait $SERVICES")


def test_verification_iterates_the_probed_services(src):
    assert "for svc in $SERVICES; do" in src
    assert "for svc in bot admin refresher" not in src


def test_a_notice_is_printed_when_the_refresher_is_skipped(src):
    assert "rolling back past v201" in src.lower()
