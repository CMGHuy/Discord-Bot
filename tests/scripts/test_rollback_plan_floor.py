"""v220: INCOMPATIBLE_BOUNDARIES, floor_violations (V220-2) and candidates (V220-2b)."""
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
from tests.scripts.rollback_repo import make_repo, sha_of  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _full_history() -> bool:
    try:
        out = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--is-shallow-repository"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return False
    return out == "false"


needs_history = pytest.mark.skipif(not _full_history(), reason="shallow or no git checkout")


def test_boundaries_are_the_spec_entries_verbatim():
    assert rp.INCOMPATIBLE_BOUNDARIES == (
        ("66e67c00", "v116", "unknown-field round-trip; older code can strip JSONB fields on re-save (merged in 14551c3c)"),
        ("2d672bab", "v184", "monitor heartbeat key (merged in b37c6e44)"),
        ("8562c35a", "v197", "durable lifecycle queue replaces the DELETE-drain consumer (migration a47f9ebc)"),
    )
    assert all(isinstance(b, rp.Boundary) for b in rp.INCOMPATIBLE_BOUNDARIES)


@needs_history
def test_every_boundary_is_an_ancestor_of_head_in_this_repo():
    assert rp.floor_violations("HEAD", REPO) == []


@pytest.fixture
def chain(tmp_path):
    repo = make_repo(tmp_path, [
        {"subject": "chore: init", "files": {"VERSION.json": '{"bot": "1.0.0"}\n'}},
        {"subject": "feat(v300): one"},
        {"subject": "release(bot): 1.0.1", "files": {"VERSION.json": '{"bot": "1.0.1"}\n'},
         "tag": "stable-2026-01-01"},
        {"subject": "feat(v301): two"},
        {"subject": "feat(v302): three", "files": {"VERSION.json": '{"bot": "1.0.2"}\n'}},
    ])
    return repo, [sha_of(repo, f"HEAD~{n}") for n in range(4, -1, -1)]


def test_floor_violations_names_each_boundary_not_yet_reached(chain):
    repo, shas = chain
    one, three = rp.Boundary(shas[1], "v300", "a"), rp.Boundary(shas[3], "v301", "b")
    assert rp.floor_violations(shas[2], repo, (one, three)) == [three]
    assert rp.floor_violations(shas[4], repo, (one, three)) == []
    assert rp.floor_violations(shas[0], repo, (one, three)) == [one, three]


def test_a_boundary_missing_from_the_repo_fails_closed(chain):
    repo, shas = chain
    ghost = rp.Boundary("0123456789ab", "v999", "absent")
    assert rp.floor_violations(shas[4], repo, (ghost,)) == [ghost]


def test_cli_floor_in_a_foreign_repo_names_all_three_boundaries(chain, capsys):
    repo, shas = chain
    assert rp.main(["floor", shas[4], "--repo", str(repo)]) == 2
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[2] for line in lines] == ["66e67c00", "2d672bab", "8562c35a"]
    assert all(line.startswith("below floor: ") for line in lines)


@needs_history
def test_cli_floor_on_head_is_above_floor(capsys):
    assert rp.main(["floor", "HEAD", "--repo", str(REPO)]) == 0
    assert capsys.readouterr().out.strip() == "above floor"


# --- V220-2b: picker candidates ----------------------------------------------


def _deploys(tmp_path, shas):
    path = tmp_path / "deploys.jsonl"
    lines = [{"ts": "2026-02-01T00:00:00Z", "git_sha": shas[2]},
             {"ts": "2026-02-02T00:00:00Z", "git_sha": shas[4]},
             {"ts": "2026-02-03T00:00:00Z", "git_sha": shas[4], "kind": "release"}]
    path.write_bytes("".join(json.dumps(line) + "\n" for line in lines).encode("utf-8"))
    return path


def test_candidates_list_deploys_then_stable_points(chain, tmp_path):
    repo, shas = chain
    stable_dir = tmp_path / "stable"
    (stable_dir / "stable-2026-01-05").mkdir(parents=True)
    (stable_dir / "stable-2026-01-05" / "manifest.json").write_bytes(
        json.dumps({"git_sha": shas[3]}).encode())
    (stable_dir / "not-a-point").mkdir()
    rows = rp.candidates(repo, deploys_path=_deploys(tmp_path, shas), stable_dir=stable_dir,
                         boundaries=(rp.Boundary(shas[3], "v301", "b"),))
    assert [(r["kind"], r["label"], r["sha"]) for r in rows] == [
        ("deploy", "deploy 2026-02-03T00:00:00Z", shas[4]),
        ("deploy", "deploy 2026-02-01T00:00:00Z", shas[2]),
        ("stable", "stable-2026-01-05", shas[3]),
        ("stable", "stable-2026-01-01", shas[2]),
    ]
    assert [r["above_floor"] for r in rows] == [True, False, True, False]
    assert [r["bot_version"] for r in rows] == ["1.0.2", "1.0.1", "1.0.1", "1.0.1"]
    assert rows[0]["plans"] == ["v302", "v301", "v300"]


def test_candidates_limit_and_missing_stable_dir(chain, tmp_path):
    repo, shas = chain
    rows = rp.candidates(repo, deploys_path=_deploys(tmp_path, shas), stable_dir=None,
                         limit=1, boundaries=())
    assert [(r["kind"], r["sha"]) for r in rows] == [("deploy", shas[4]), ("stable", shas[2])]


def test_candidates_skip_deploys_off_main(chain, tmp_path):
    repo, shas = chain
    path = tmp_path / "d.jsonl"
    path.write_bytes((json.dumps({"ts": "2026-02-01T00:00:00Z", "git_sha": "f" * 40}) + "\n").encode())
    assert rp.candidates(repo, deploys_path=path, stable_dir=None, boundaries=())[0]["kind"] == "stable"


def test_cli_candidates_prints_json_rows(chain, tmp_path, capsys):
    repo, shas = chain
    rc = rp.main(["candidates", "--repo", str(repo), "--deploys", str(_deploys(tmp_path, shas)),
                  "--limit", "5"])
    rows = json.loads(capsys.readouterr().out)
    assert rc == 0 and len(rows) == 3
    assert set(rows[0]) == {"label", "sha", "kind", "bot_version", "plans", "above_floor"}
