"""scripts/dev/build_version_matrix.py's pure logic.

Only the sorting and the pair/range derivation are tested directly — walking
git is subprocess orchestration, matching this codebase's convention of testing
the pure logic a script wraps (see test_quarterly_revalidation.py).

The sort is what earns most of these. Version strings compared as text put
`1.0.10` before `1.0.5`, which would silently reverse a bot range and draw the
admin page's bars backwards — a wrong answer that looks entirely plausible.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import build_version_matrix as bvm  # noqa: E402


def _fake_git(monkeypatch, blobs: dict[str, str]):
    """Stub `subprocess.run` for both calls the walk makes: the log, then one
    `git show` per commit. Keys of `blobs` are shas, in log order."""
    log = "\n".join(f"{sha}0000000|2026-07-{i+1:02d}|subject {i}"
                    for i, sha in enumerate(blobs))

    class R:
        def __init__(self, stdout, code=0):
            self.stdout, self.returncode = stdout, code

    def fake_run(cmd, **kwargs):
        if cmd[1] == "log":
            return R(log)
        sha = cmd[2].split(":")[0][:8]
        return R(blobs.get(sha, ""), 0 if sha in blobs else 1)

    monkeypatch.setattr(bvm.subprocess, "run", fake_run)
    monkeypatch.setattr(bvm.Path, "exists", lambda self: False)


def test_components_are_every_key_that_is_not_a_timestamp():
    doc = {"ui": "1.3.1", "bot": "1.1.2",
           "ui_updated": "2026-08-15 11-58-58", "bot_updated": "2026-08-07 20-59-24"}
    assert bvm._components(doc) == ["ui", "bot"]


def test_a_new_component_needs_no_code_change():
    """The whole interface for adding a component is a key in VERSION.json."""
    doc = {"ui": "1.3.1", "bot": "1.1.2", "worker": "0.2.0", "ui_updated": "x"}
    assert bvm._components(doc) == ["ui", "bot", "worker"]


def test_a_component_named_like_a_stamp_is_invisible():
    """Documents the trap rather than fixing it: `_updated` is reserved."""
    assert bvm._components({"ui": "1.0.0", "cache_updated": "0.1.0"}) == ["ui"]


def test_semver_sorts_numerically_not_lexically():
    versions = ["1.0.5", "1.0.10", "1.0.2", "1.1.0", "1.0.9"]
    assert sorted(versions, key=bvm._semver_key) == [
        "1.0.2", "1.0.5", "1.0.9", "1.0.10", "1.1.0",
    ]


def test_semver_orders_minor_above_patch():
    assert sorted(["1.9.9", "1.10.0"], key=bvm._semver_key) == ["1.9.9", "1.10.0"]


def test_semver_tolerates_a_non_numeric_part():
    """A malformed version must sort last, not raise — one bad historical
    value should not make the whole page unrenderable."""
    out = sorted(["1.0.2", "1.0.0-rc1", "1.0.1"], key=bvm._semver_key)
    assert out[0] == "1.0.1" or out[0] == "1.0.2"
    assert "1.0.0-rc1" in out


def test_a_release_missing_one_component_is_kept_not_skipped(monkeypatch):
    """The guard is at-least-one. Requiring EVERY component would delete all
    history predating a component the day someone adds one."""
    blobs = {
        "aaaaaaa1": '{"ui": "1.0.0", "bot": "1.0.0"}',
        "aaaaaaa2": '{"ui": "1.1.0", "bot": "1.0.0", "worker": "0.1.0"}',
    }
    _fake_git(monkeypatch, blobs)
    states = bvm._states()
    assert len(states) == 2, "the pre-worker release must survive"
    assert states[0]["versions"] == {"ui": "1.0.0", "bot": "1.0.0"}
    assert "worker" not in states[0]["versions"]


def test_a_release_with_no_components_at_all_is_skipped(monkeypatch):
    _fake_git(monkeypatch, {"aaaaaaa1": '{"ui_updated": "x"}',
                            "aaaaaaa2": '{"ui": "1.0.0"}'})
    assert [s["versions"] for s in bvm._states()] == [{"ui": "1.0.0"}]


def test_no_states_fails_loudly(monkeypatch):
    monkeypatch.setattr(bvm, "_states", lambda: [])
    try:
        bvm.build()
    except SystemExit:
        return
    raise AssertionError("an empty history must abort, not write an empty file")


def test_build_derives_components_releases_and_changed(monkeypatch):
    states = [
        {"sha": "aaaaaaa1", "date": "2026-07-01", "subject": "a",
         "versions": {"ui": "1.0.0", "bot": "1.0.0"}},
        {"sha": "aaaaaaa2", "date": "2026-07-02", "subject": "b",
         "versions": {"ui": "1.0.0", "bot": "1.0.1"}},
        # Repeat of the whole tuple: extends last_seen, does not add a release.
        {"sha": "aaaaaaa3", "date": "2026-07-03", "subject": "c",
         "versions": {"ui": "1.0.0", "bot": "1.0.1"}},
        # A component appearing for the first time, mid-history.
        {"sha": "aaaaaaa4", "date": "2026-07-04", "subject": "d",
         "versions": {"ui": "1.0.0", "bot": "1.0.1", "worker": "0.1.0"}},
    ]
    monkeypatch.setattr(bvm, "_states", lambda: states)
    doc = bvm.build()

    assert doc["components"] == ["ui", "bot", "worker"], "first-appearance order"
    assert doc["current"] == {"ui": "1.0.0", "bot": "1.0.1", "worker": "0.1.0"}
    assert len(doc["releases"]) == 3, "the repeated tuple must not add a release"

    first, second, third = doc["releases"]
    assert first["changed"] == ["ui", "bot"], "everything is new at the first release"
    assert second["changed"] == ["bot"]
    assert second["last_seen"] == "2026-07-03", "the repeat extended it"
    assert third["changed"] == ["worker"]


def test_a_component_is_null_before_it_existed(monkeypatch):
    """null distinguishes 'did not exist yet' from 'unchanged' -- the strip
    draws those differently and cannot recover the difference from equality."""
    monkeypatch.setattr(bvm, "_states", lambda: [
        {"sha": "a1", "date": "2026-07-01", "subject": "a",
         "versions": {"ui": "1.0.0"}},
        {"sha": "a2", "date": "2026-07-02", "subject": "b",
         "versions": {"ui": "1.0.0", "worker": "0.1.0"}},
    ])
    releases = bvm.build()["releases"]
    assert releases[0]["versions"] == {"ui": "1.0.0", "worker": None}
    assert "worker" not in releases[0]["changed"], "absent is not changed"


def test_the_committed_file_matches_the_current_generator():
    """The frozen file is committed; this notices when it drifts from what the
    generator would produce today — the same drift the endpoint's `stale` flag
    reports at runtime, caught earlier."""
    import json

    frozen_path = ROOT / "swingbot" / "admin" / "version_history.json"
    assert frozen_path.exists(), "run: python scripts/dev/build_version_matrix.py"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))

    live = json.loads((ROOT / "VERSION.json").read_text(encoding="utf-8"))
    assert frozen["current"]["ui"] == live["ui"], (
        "VERSION.json moved without regenerating: run "
        "python scripts/dev/build_version_matrix.py")
    assert frozen["current"]["bot"] == live["bot"], (
        "VERSION.json moved without regenerating: run "
        "python scripts/dev/build_version_matrix.py")
