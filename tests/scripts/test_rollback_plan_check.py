"""v220 V220-6/6b: rollback_plan check report and deploy-line."""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_plan as rp  # noqa: E402
from tests.scripts.rollback_repo import commit_off_main, make_repo, sha_of  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

MIG = "swingbot/core/db/migrations/versions"
CONFIG = ('FIELDS = [\n    Field("DISCORD_TOKEN", "TOKEN"),\n    Field("POSTGRES_PASSWORD", "PGPW"),\n'
          '    Field("DATABASE_URL", "DB_URL"),\n{extra}]\n')
COMPOSE = "services:\n  db:\n    image: {db}\n  bot:\n    image: bot\n"
ENV = ("DISCORD_TOKEN=tok-SECRET-1\nPOSTGRES_PASSWORD=pw-SECRET-2\n"
       "DATABASE_URL=postgresql+psycopg://u:SECRET-3@h/d\n")
SAFE = '    op.create_table("t2", sa.Column("k", sa.Text))'
UNSAFE = '    op.drop_column("t1", "k")'
IMAGE = "ghcr.io/o/swing-bot:sha-"


def _migration(rev: str, down: str | None, body: str, extra: str = "") -> dict:
    text = f'revision = "{rev}"\ndown_revision = {down!r}\n{extra}\n\ndef upgrade():\n{body}\n'
    return {f"{MIG}/{rev}_x.py": text}


def _base_files() -> dict:
    return {"swingbot/config.py": CONFIG.format(extra='    Field("OLD_KEY", "OLD"),\n'),
            "docker-compose.yml": COMPOSE.format(db="pg:16"),
            "swingbot/refresher/main.py": "x = 1\n",
            "swingbot/vocab.py": 'V = ("ACTIVE", "RSI", "plan_transition")\n',
            **_migration("v1_001", None, '    op.create_table("t1", sa.Column("k", sa.Text))')}


@pytest.fixture
def stack(tmp_path, monkeypatch):
    """build(*later_commits): base (the target) -> v300 (safe table, OLD_KEY removed) -> later."""
    monkeypatch.setattr(rp, "INCOMPATIBLE_BOUNDARIES", ())
    env = tmp_path / "env"
    env.write_bytes(ENV.encode("utf-8"))

    def build(*later: dict, env_text: str | None = None) -> dict:
        if env_text is not None:
            env.write_bytes(env_text.encode("utf-8"))
        repo = make_repo(tmp_path, [
            {"subject": "chore: base", "files": _base_files()},
            {"subject": "feat(v300): new table",
             "files": {"swingbot/config.py": CONFIG.format(extra=""), **_migration("v2_001", "v1_001", SAFE)}},
            *later])
        return {"repo": repo, "target": sha_of(repo, f"HEAD~{len(later) + 1}"), "head": sha_of(repo), "env": env}
    return build


def _check(w, **kw):
    kw.setdefault("ref", "origin/main")
    kw.setdefault("env_path", w["env"])
    kw.setdefault("running_sha", w["head"])
    kw.setdefault("hold_path", w["repo"] / "backups" / "deploy_hold.json")
    kw.setdefault("host", False)
    image = kw.pop("image", IMAGE + w["target"][:12])
    return rp.run_checks(kw.pop("sha", w["target"]), image, repo=w["repo"], **kw)


def test_clean_target_passes_and_warns_about_a_removed_key(stack):
    r = _check(stack())
    assert r["ok"] is True and r["noop"] is False and r["refusals"] == []
    assert r["refresher"] == "start" and r["hold"] is None
    assert [m["revision"] for m in r["migrations"]] == ["v2_001"] and r["migrations"][0]["safe"]
    assert any("OLD_KEY" in w for w in r["warnings"])
    assert set(r) == {"ok", "noop", "refusals", "warnings", "notes", "refresher", "migrations", "hold"}


def test_target_already_running_is_a_noop(stack):
    w = stack()
    r = _check(w, running_sha=w["target"])
    assert r["noop"] is True and r["ok"] is False and r["refusals"] == [] and r["migrations"] == []


def test_unsafe_migration_refuses_naming_the_revision(stack):
    r = _check(stack({"subject": "feat(v301): drop", "files": _migration("v3_001", "v2_001", UNSAFE)}))
    assert r["ok"] is False and any("v3_001" in x for x in r["refusals"])
    assert [m["safe"] for m in r["migrations"]] == [True, False]


def test_rollback_safe_override_is_a_note(stack):
    files = _migration("v3_001", "v2_001", UNSAFE, extra='ROLLBACK_SAFE = "column was never read"')
    r = _check(stack({"subject": "feat(v301): drop", "files": files}))
    assert r["ok"] is True and any("column was never read" in n for n in r["notes"])


def test_missing_critical_key_refuses_and_no_value_leaks(stack):
    r = _check(stack(env_text="DISCORD_TOKEN=tok-SECRET-1\nPOSTGRES_PASSWORD=pw-SECRET-2\n"))
    assert any("DATABASE_URL" in x for x in r["refusals"])
    dumped = json.dumps(r)
    assert all(secret not in dumped for secret in ("tok-SECRET-1", "pw-SECRET-2", "SECRET-3"))


def test_missing_env_file_is_a_refusal_not_a_crash(stack, tmp_path):
    r = _check(stack(), env_path=tmp_path / "nope.env")
    assert any(x.startswith("config keys: cannot run") for x in r["refusals"])


def test_compose_db_change_refuses(stack):
    r = _check(stack({"subject": "chore: pg 17", "files": {"docker-compose.yml": COMPOSE.format(db="pg:17")}}))
    assert any("compose db service differs" in x for x in r["refusals"])


def test_target_below_the_floor_refuses(stack, monkeypatch):
    w = stack()
    monkeypatch.setattr(rp, "INCOMPATIBLE_BOUNDARIES", (rp.Boundary(w["head"], "v399", "reason"),))
    assert any("v399" in x for x in _check(w)["refusals"])


def test_target_off_main_refuses_and_stops(stack):
    w = stack()
    off = commit_off_main(w["repo"], "hotfix")
    r = _check(w, sha=off, image=IMAGE + off[:12])
    assert r["ok"] is False and any("not an ancestor" in x for x in r["refusals"]) and r["migrations"] == []


def test_existing_hold_is_shown_and_will_be_replaced(stack):
    w = stack()
    hold = w["repo"] / "backups" / "deploy_hold.json"
    hold.parent.mkdir(parents=True, exist_ok=True)
    hold.write_text(json.dumps({"sha": "abc123", "at": "2026-11-08T10:00:00Z"}), encoding="utf-8")
    r = _check(w)
    assert r["hold"]["sha"] == "abc123" and any("replaces it" in n for n in r["notes"])
    hold.write_text("{broken", encoding="utf-8")
    r = _check(w)
    assert r["hold"] is None and any("unreadable" in x for x in r["warnings"]) and r["ok"] is True
