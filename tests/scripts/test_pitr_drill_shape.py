"""The PITR drill (spec § Proof). It runs only on the VM; this pins what
keeps it from harming production and what makes it a real proof."""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")
REPO = pathlib.Path(__file__).resolve().parents[2]
COMPOSE = REPO / "deploy" / "db" / "docker-compose.drill.yml"
SCRIPT = REPO / "scripts" / "ops" / "pitr_drill.sh"


@pytest.fixture(scope="module")
def drill():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_scratch_project_never_archives_into_production(drill):
    db = drill["services"]["db"]
    assert "archive_mode=off" in db["command"]
    for service in drill["services"].values():
        assert "/opt/swing-bot/backups/pitr:/var/lib/pgbackrest:ro" in service["volumes"]
        assert not any(v.startswith("pgdata:") for v in service["volumes"])


def test_scratch_project_has_its_own_name_port_and_volume(drill):
    assert drill["name"] == "swingbot-drill"
    assert drill["services"]["db"]["ports"] == ["127.0.0.1:55433:5432"]
    assert "drill_pgdata" in drill["volumes"]


def test_the_restore_targets_a_time_and_promotes(drill):
    command = " ".join(drill["services"]["restore"]["command"])
    assert "--type=time" in command and "--target-action=promote" in command


def test_the_drill_brackets_the_target_with_two_marks_and_checks_both():
    src = SCRIPT.read_text(encoding="utf-8")
    before, target, after = (src.index("-before')"), src.index("TARGET=\"$(psql_prod"),
                             src.index("-after')"))
    assert before < target < after
    assert "pg_switch_wal()" in src
    assert 'AFTER" = "0"' in src and 'BEFORE" = "1"' in src
    assert "VERDICT" in src and "logs/pitr_drill.log" in src
    assert "down -v" in src
    assert b"\r" not in SCRIPT.read_bytes()


def test_drill_target_is_exported_before_any_compose_call_on_the_scratch_project():
    # The compose file requires DRILL_TARGET at parse time, so every `$DRILL ...`
    # call (down, run, up, exec) needs it in the environment, not only `run restore`.
    src = SCRIPT.read_text(encoding="utf-8")
    export = src.index('export DRILL_TARGET="$TARGET"')
    first_use = src.index("$DRILL --profile restore down")
    assert src.index('TARGET="$(psql_prod') < export < first_use
