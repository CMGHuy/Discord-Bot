"""pitr_resolve: what rollback_to.sh restores for a target second (v116)."""
import ast
import datetime as dt
import json
import pathlib
import shlex
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import pitr_resolve as pr  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
FIRST_BACKUP_STOP = dt.datetime(2026, 9, 1, 1, 0, tzinfo=UTC)


@pytest.fixture
def inputs(tmp_path):
    deploys = tmp_path / "deploys.jsonl"
    deploys.write_text(
        json.dumps({"ts": "2026-09-01T00:00:00Z", "git_sha": "a" * 40,
                    "bot_image": "ghcr.io/o/r:sha-aaa", "db_image": "ghcr.io/o/r-db:pgcfg-111"}) + "\n"
        + "not json\n"
        + json.dumps({"ts": "2026-09-20T12:00:00Z", "git_sha": "b" * 40,
                      "bot_image": "ghcr.io/o/r:sha-bbb", "db_image": "ghcr.io/o/r-db:pgcfg-111"}) + "\n",
        encoding="utf-8")
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    for name in ("2026-09-01T00-00-00-000000Z.env", "2026-09-25T08-00-00-000000Z.env"):
        (env_dir / name).write_text(name, encoding="utf-8")
    restic = json.dumps([
        {"time": "2026-09-25T07:07:01.123456789Z", "short_id": "aaaa1111", "id": "aaaa1111ff"},
        {"time": "2026-09-25T08:07:02.5Z", "short_id": "bbbb2222", "id": "bbbb2222ff"},
    ])
    pgbackrest = json.dumps([{"name": "swingbot", "backup": [
        {"type": "full", "timestamp": {"start": int(FIRST_BACKUP_STOP.timestamp()) - 600,
                                       "stop": int(FIRST_BACKUP_STOP.timestamp())}}]}])
    return {"deploys": pr.load_deploys(str(deploys)), "envs": pr.env_versions(str(env_dir)),
            "snapshots": pr.restic_snapshots(restic), "pg_oldest": pr.pgbackrest_oldest(pgbackrest),
            "paths": (deploys, env_dir, restic, pgbackrest)}


def _resolve(inputs, target):
    return pr.resolve(target, NOW, inputs["deploys"], inputs["envs"], inputs["snapshots"],
                      inputs["pg_oldest"])


def test_parse_ts_accepts_every_form_the_inputs_use():
    expected = dt.datetime(2026, 9, 25, 8, 0, 30, tzinfo=UTC)
    for text in ("2026-09-25T08:00:30Z", "2026-09-25 08:00:30", "2026-09-25T08:00:30+00:00"):
        assert pr.parse_ts(text) == expected
    assert pr.parse_ts("2026-09-25T08:00:30.123456789Z") == expected.replace(microsecond=123456)


def test_a_malformed_deploy_line_is_skipped(inputs):
    assert [row["git_sha"][0] for row in inputs["deploys"]] == ["a", "b"]


def test_resolves_the_artifacts_current_at_the_target(inputs):
    res = _resolve(inputs, dt.datetime(2026, 9, 25, 8, 0, 30, tzinfo=UTC))
    assert res.refusals == []
    assert res.deploy["git_sha"] == "b" * 40
    assert res.env_file.endswith("2026-09-25T08-00-00-000000Z.env")
    assert res.restic[1] == "aaaa1111"          # 08:07 is after the target


def test_refuses_a_future_target(inputs):
    res = _resolve(inputs, NOW + dt.timedelta(seconds=1))
    assert any("future" in line for line in res.refusals)


def test_refuses_a_target_before_the_oldest_restorable_point(inputs):
    res = _resolve(inputs, FIRST_BACKUP_STOP - dt.timedelta(seconds=1))
    assert any("oldest restorable point" in line for line in res.refusals)


def test_refuses_when_no_market_data_snapshot_predates_the_target(inputs):
    res = _resolve(inputs, dt.datetime(2026, 9, 10, tzinfo=UTC))
    assert "no market_data snapshot at or before the target" in res.refusals


def test_main_prints_assignments_a_shell_can_eval(inputs, tmp_path, capsys):
    deploys, env_dir, restic, pgbackrest = inputs["paths"]
    (tmp_path / "r.json").write_text(restic, encoding="utf-8")
    (tmp_path / "p.json").write_text(pgbackrest, encoding="utf-8")
    code = pr.main(["--target", "2026-09-25T08:00:30Z", "--now", "2026-10-01T12:00:00Z",
                    "--deploys", str(deploys), "--env-dir", str(env_dir),
                    "--restic-json", str(tmp_path / "r.json"),
                    "--pgbackrest-json", str(tmp_path / "p.json")])
    assert code == 0
    pairs = dict(shlex.split(line)[0].split("=", 1) for line in capsys.readouterr().out.splitlines())
    assert pairs["target_pg"] == "2026-09-25 08:00:30+00"
    assert pairs["bot_image"] == "ghcr.io/o/r:sha-bbb"
    assert pairs["restic_id"] == "aaaa1111"


def test_main_exits_2_with_refusals(inputs, tmp_path, capsys):
    deploys, env_dir, restic, pgbackrest = inputs["paths"]
    (tmp_path / "r.json").write_text(restic, encoding="utf-8")
    (tmp_path / "p.json").write_text(pgbackrest, encoding="utf-8")
    code = pr.main(["--target", "2027-01-01T00:00:00Z", "--now", "2026-10-01T12:00:00Z",
                    "--deploys", str(deploys), "--env-dir", str(env_dir),
                    "--restic-json", str(tmp_path / "r.json"),
                    "--pgbackrest-json", str(tmp_path / "p.json")])
    assert code == 2
    assert capsys.readouterr().out.startswith("REFUSE: ")


def test_it_is_stdlib_only_apart_from_env_snapshot():
    tree = ast.parse((ROOT / "scripts" / "ops" / "pitr_resolve.py").read_text(encoding="utf-8"))
    roots = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    froms = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert roots <= set(sys.stdlib_module_names)
    assert {m for m in froms if m.split(".")[0] not in sys.stdlib_module_names} \
        <= {"__future__", "swingbot.core.infra"}
