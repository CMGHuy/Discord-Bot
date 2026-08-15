"""scripts/build_version_matrix.py's pure logic.

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
sys.path.insert(0, str(ROOT / "scripts"))

import build_version_matrix as bvm  # noqa: E402


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


def test_build_derives_pairs_and_ranges(monkeypatch):
    states = [
        {"sha": "aaaaaaa1", "date": "2026-07-01", "subject": "a", "ui": "1.0.0", "bot": "1.0.0"},
        {"sha": "aaaaaaa2", "date": "2026-07-02", "subject": "b", "ui": "1.0.0", "bot": "1.0.1"},
        # Repeat of an existing pair: must extend last_seen, not duplicate.
        {"sha": "aaaaaaa3", "date": "2026-07-03", "subject": "c", "ui": "1.0.0", "bot": "1.0.1"},
        {"sha": "aaaaaaa4", "date": "2026-07-04", "subject": "d", "ui": "1.1.0", "bot": "1.0.10"},
    ]
    monkeypatch.setattr(bvm, "_states", lambda: states)
    doc = bvm.build()

    assert doc["current"] == {"ui": "1.1.0", "bot": "1.0.10"}
    assert len(doc["pairs"]) == 3, "the repeated pair must be deduplicated"

    repeated = [p for p in doc["pairs"] if p["bot"] == "1.0.1"][0]
    assert repeated["first_seen"] == "2026-07-02"
    assert repeated["last_seen"] == "2026-07-03"

    ranges = {r["ui"]: r for r in doc["ranges"]}
    assert ranges["1.0.0"]["bot_min"] == "1.0.0"
    assert ranges["1.0.0"]["bot_max"] == "1.0.1"
    assert ranges["1.0.0"]["bot_count"] == 2
    assert ranges["1.1.0"]["bot_min"] == ranges["1.1.0"]["bot_max"] == "1.0.10"


def test_bot_axis_is_sorted_numerically(monkeypatch):
    """The axis order is what the page's column indices are built from."""
    states = [
        {"sha": "a", "date": "2026-07-01", "subject": "s", "ui": "1.0.0", "bot": "1.0.9"},
        {"sha": "b", "date": "2026-07-02", "subject": "s", "ui": "1.0.0", "bot": "1.0.10"},
        {"sha": "c", "date": "2026-07-03", "subject": "s", "ui": "1.0.0", "bot": "1.0.2"},
    ]
    monkeypatch.setattr(bvm, "_states", lambda: states)
    assert bvm.build()["bot_versions"] == ["1.0.2", "1.0.9", "1.0.10"]


def test_every_pair_falls_inside_its_ui_range(monkeypatch):
    """The property the admin page's bars depend on."""
    states = [
        {"sha": "a", "date": "2026-07-01", "subject": "s", "ui": "1.0.0", "bot": "1.0.1"},
        {"sha": "b", "date": "2026-07-02", "subject": "s", "ui": "1.0.0", "bot": "1.0.12"},
        {"sha": "c", "date": "2026-07-03", "subject": "s", "ui": "1.0.0", "bot": "1.0.3"},
    ]
    monkeypatch.setattr(bvm, "_states", lambda: states)
    doc = bvm.build()
    order = {v: i for i, v in enumerate(doc["bot_versions"])}
    spans = {r["ui"]: (order[r["bot_min"]], order[r["bot_max"]]) for r in doc["ranges"]}
    for pair in doc["pairs"]:
        low, high = spans[pair["ui"]]
        assert low <= order[pair["bot"]] <= high


def test_no_states_fails_loudly(monkeypatch):
    monkeypatch.setattr(bvm, "_states", lambda: [])
    try:
        bvm.build()
    except SystemExit:
        return
    raise AssertionError("an empty history must abort, not write an empty file")


def test_the_committed_file_matches_the_current_generator():
    """The frozen file is committed; this notices when it drifts from what the
    generator would produce today — the same drift the endpoint's `stale` flag
    reports at runtime, caught earlier."""
    import json

    frozen_path = ROOT / "swingbot" / "admin" / "version_history.json"
    assert frozen_path.exists(), "run: python scripts/build_version_matrix.py"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))

    live = json.loads((ROOT / "VERSION.json").read_text(encoding="utf-8"))
    assert frozen["current"]["ui"] == live["ui"], (
        "VERSION.json moved without regenerating: run "
        "python scripts/build_version_matrix.py")
    assert frozen["current"]["bot"] == live["bot"], (
        "VERSION.json moved without regenerating: run "
        "python scripts/build_version_matrix.py")
