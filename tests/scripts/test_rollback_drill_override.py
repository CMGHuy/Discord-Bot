"""The v220 rollback drill's compose override (deploy/drill/rollback-drill.override.yml):
it may only rename containers, drop host ports and point the admin's container
controls at a bot that does not exist, so a scratch project can run next to
the live stack on the VM."""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")

ROOT = pathlib.Path(__file__).resolve().parents[2]
OVERRIDE = ROOT / "deploy" / "drill" / "rollback-drill.override.yml"


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!reset", lambda loader, node: ("!reset", loader.construct_sequence(node)))


@pytest.fixture(scope="module")
def base():
    return yaml.load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"), Loader=_Loader)["services"]


@pytest.fixture(scope="module")
def over():
    return yaml.load(OVERRIDE.read_text(encoding="utf-8"), Loader=_Loader)["services"]


def test_every_fixed_container_name_is_renamed(base, over):
    named = {svc for svc, spec in base.items() if "container_name" in spec}
    assert named == {svc for svc, spec in over.items() if "container_name" in spec}
    for svc in named:
        assert over[svc]["container_name"].startswith("rbdrill-"), svc
        assert over[svc]["container_name"] != base[svc]["container_name"]


def test_no_host_port_is_published(base, over):
    for svc, spec in base.items():
        if "ports" in spec:
            assert over[svc]["ports"] == ("!reset", []), svc


def test_admin_controls_point_at_a_bot_that_does_not_exist(over):
    assert over["admin"]["environment"]["BOT_CONTAINER_NAME"] == over["bot"]["container_name"]


def test_it_changes_nothing_but_names_ports_and_the_bot_pointer(over):
    allowed = {"container_name", "ports", "environment"}
    for svc, spec in over.items():
        assert set(spec) <= allowed, (svc, set(spec) - allowed)


def test_the_header_says_the_bot_never_starts():
    assert "never started" in OVERRIDE.read_text(encoding="utf-8")
