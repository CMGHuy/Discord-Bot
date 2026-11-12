"""v220: rollback_plan.resolve -- every target form (V220-1, V220-1b, V220-2)."""
from __future__ import annotations

import json
import pathlib
import shutil
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_plan as rp  # noqa: E402
from tests.scripts.rollback_repo import commit_off_main, make_repo, sha_of  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

IMAGE = "ghcr.io/owner/swing-bot:sha-aaaaaaaaaaaa"


def _version(bot: str) -> dict:
    return {"VERSION.json": json.dumps({"ui": "1.0.0", "bot": bot}, indent=2) + "\n"}


def _line(ts: str, sha: str, **extra) -> str:
    return json.dumps({"ts": ts, "git_sha": sha, "bot_image": "b", "db_image": "d", **extra}) + "\n"


@pytest.fixture
def world(tmp_path):
    repo = make_repo(tmp_path, [
        {"subject": "chore: init", "files": _version("2.0.0")},
        {"subject": "feat(v200): add thing", "files": {"a.txt": "a\n"}},
        {"subject": "release(bot): 2.0.1", "files": _version("2.0.1"), "tag": "stable-2026-01-01"},
        {"subject": "docs(v210): spec", "files": {"spec.md": "s\n"}},
        {"subject": "feat(v210): build", "files": {"b.txt": "b\n"}},
        {"subject": "release(bot): 2.0.2", "files": _version("2.0.2")},
    ])
    shas = [sha_of(repo, f"HEAD~{n}") for n in range(5, -1, -1)]
    deploys = tmp_path / "deploys.jsonl"
    deploys.write_bytes((_line("2026-02-01T10:00:00Z", shas[2]) + "not json\n"
                         + _line("2026-02-03T10:00:00Z", shas[5])).encode("utf-8"))
    return {"repo": repo, "shas": shas, "deploys": deploys}


def _resolve(world, text, **kw):
    kw.setdefault("deploys_path", world["deploys"])
    kw.setdefault("current_image", IMAGE)
    return rp.resolve(text, world["repo"], **kw)


def test_full_sha_resolves_with_its_sha_image(world):
    sha = world["shas"][1]
    target = _resolve(world, sha)
    assert (target.sha, target.form) == (sha, "sha")
    assert target.image == f"ghcr.io/owner/swing-bot:sha-{sha[:12]}"


def test_seven_char_and_uppercase_prefixes_resolve(world):
    sha = world["shas"][3]
    assert _resolve(world, sha[:7]).sha == sha
    assert _resolve(world, sha[:10].upper()).sha == sha


def test_commit_off_main_is_refused(world):
    side = commit_off_main(world["repo"], "side work")
    with pytest.raises(rp.Refused, match="not an ancestor of origin/main"):
        _resolve(world, side)


def test_unknown_commit_lists_stable_candidates(world):
    with pytest.raises(rp.Refused, match="unknown commit") as exc:
        _resolve(world, "deadbeefdeadbeef")
    assert exc.value.candidates == [f"stable-2026-01-01 {world['shas'][2][:12]}"]


def test_ambiguous_prefix_is_refused_with_every_match(world, monkeypatch):
    real = rp.git_out
    first, second = "abcdef1" + "0" * 33, "abcdef1" + "1" * 33

    def fake(repo, *args):
        if args[:1] == ("rev-list",):
            return f"{first}\n{second}"
        if args[:2] == ("log", "-1"):
            return "a subject"
        return real(repo, *args)

    monkeypatch.setattr(rp, "git_out", fake)
    with pytest.raises(rp.Refused, match="ambiguous") as exc:
        _resolve(world, "abcdef1")
    assert exc.value.candidates == [f"a subject {first[:12]}", f"a subject {second[:12]}"]


def test_stable_tag_resolves_to_the_tagged_commit(world):
    target = _resolve(world, "stable-2026-01-01")
    assert (target.sha, target.form, target.label) == (world["shas"][2], "stable", "stable-2026-01-01")


def test_stable_manifest_git_sha_wins_over_the_tag(world):
    folder = world["repo"] / "backups" / "stable" / "stable-2026-01-01"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_bytes(json.dumps({"git_sha": world["shas"][1]}).encode())
    assert _resolve(world, "stable-2026-01-01").sha == world["shas"][1]


def test_stable_point_known_only_by_its_manifest_resolves(world):
    folder = world["repo"] / "backups" / "stable" / "stable-2026-01-05-2"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_bytes(json.dumps({"git_sha": world["shas"][4]}).encode())
    assert _resolve(world, "stable-2026-01-05-2").sha == world["shas"][4]


def test_unknown_stable_point_is_refused_with_candidates(world):
    with pytest.raises(rp.Refused, match="unknown stable point") as exc:
        _resolve(world, "stable-2030-01-01")
    assert exc.value.candidates[0].startswith("stable-2026-01-01 ")


def test_unknown_form_and_empty_image_are_refused(world):
    with pytest.raises(rp.Refused, match="unknown target form"):
        _resolve(world, "hello")
    with pytest.raises(rp.Refused, match="SWING_BOT_IMAGE"):
        _resolve(world, world["shas"][1], current_image="")


@pytest.mark.parametrize("current,expected", [
    ("ghcr.io/o/swing-bot:sha-111111111111", "ghcr.io/o/swing-bot:sha-0123456789ab"),
    ("ghcr.io/o/swing-bot@sha256:" + "f" * 64, "ghcr.io/o/swing-bot:sha-0123456789ab"),
    ("localhost:5000/swing-bot:latest", "localhost:5000/swing-bot:sha-0123456789ab"),
    ("swing-bot", "swing-bot:sha-0123456789ab"),
])
def test_image_for_keeps_the_repository_and_swaps_the_tag(current, expected):
    assert rp.image_for("0123456789abcdef" + "0" * 24, current) == expected


def _cli(world, *args):
    return rp.main(["resolve", *args, "--repo", str(world["repo"]), "--current-image", IMAGE])


def test_cli_resolve_prints_the_target_json(world, capsys):
    rc = _cli(world, world["shas"][5][:9], "--deploys", str(world["deploys"]))
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["sha"] == world["shas"][5]
    assert set(out) == {"sha", "image", "form", "label"}


def test_cli_refusal_exits_2_with_candidates(world, capsys):
    rc = _cli(world, "stable-2030-01-01", "--deploys", str(world["deploys"]))
    err = capsys.readouterr().err
    assert rc == 2 and err.startswith("REFUSE: unknown stable point")
    assert "  candidate: stable-2026-01-01 " in err


def test_cli_bad_ref_is_a_refusal_not_a_crash(world, capsys):
    rc = rp.main(["resolve", world["shas"][1], "--repo", str(world["repo"]),
                  "--ref", "no/such", "--current-image", IMAGE])
    assert rc == 2 and capsys.readouterr().err.startswith("REFUSE: git failed")


# --- V220-1b: bot version and date forms -------------------------------------


def test_bot_version_resolves_to_the_commit_that_set_it(world):
    target = _resolve(world, "bot-2.0.1")
    assert (target.sha, target.form, target.label) == (world["shas"][2], "bot", "bot-2.0.1")
    assert _resolve(world, "bot-2.0.0").sha == world["shas"][0]


def test_unknown_bot_version_is_refused_with_candidates(world):
    with pytest.raises(rp.Refused, match="sets bot 9.9.9") as exc:
        _resolve(world, "bot-9.9.9")
    assert exc.value.candidates[0].startswith("stable-2026-01-01 ")


@pytest.mark.parametrize("text,index", [
    ("2026-02-01", 2), ("2026-02-02", 2), ("2026-02-03T09:59", 2), ("2026-02-03T10:00", 5),
])
def test_date_resolves_to_the_deploy_live_then(world, text, index):
    target = _resolve(world, text)
    assert (target.sha, target.form) == (world["shas"][index], "date")
    assert target.label.startswith("deploy 2026-02-0")


def test_date_before_any_deploy_is_refused_with_the_deploys(world):
    with pytest.raises(rp.Refused, match="no deploy recorded") as exc:
        _resolve(world, "2026-01-15")
    assert exc.value.candidates == [f"deploy 2026-02-01T10:00:00Z {world['shas'][2][:12]}",
                                    f"deploy 2026-02-03T10:00:00Z {world['shas'][5][:12]}"]


def test_rollback_lines_count_as_deploys(world):
    with world["deploys"].open("ab") as fh:
        fh.write(_line("2026-02-04T00:00:00Z", world["shas"][1], kind="rollback",
                       from_sha=world["shas"][5]).encode("utf-8"))
    assert _resolve(world, "2026-02-04").sha == world["shas"][1]


def test_bad_date_is_refused(world):
    with pytest.raises(rp.Refused, match="bad date"):
        _resolve(world, "2026-13-01")


def test_missing_deploys_file_refuses_a_date(world, tmp_path):
    with pytest.raises(rp.Refused, match="no deploy recorded"):
        _resolve(world, "2026-02-02", deploys_path=tmp_path / "absent.jsonl")


def test_load_deploys_skips_junk_and_sorts(tmp_path):
    path = tmp_path / "d.jsonl"
    path.write_bytes(("not json\n" + '{"ts": "", "git_sha": "x"}\n' + '{"ts": "bad", "git_sha": "x"}\n'
                      + _line("2026-02-03T10:00:00Z", "b") + _line("2026-02-01 10:00:00", "a")
                      + '["list"]\n').encode("utf-8"))
    rows = rp.load_deploys(path)
    assert [row["git_sha"] for row in rows] == ["a", "b"]
    assert rows[0]["_at"].tzinfo is not None


def test_cli_reads_deploys_under_the_repo_by_default(world, capsys):
    (world["repo"] / "backups").mkdir()
    shutil.copy(world["deploys"], world["repo"] / "backups" / "deploys.jsonl")
    assert _cli(world, "2026-02-02") == 0
    assert json.loads(capsys.readouterr().out)["sha"] == world["shas"][2]
