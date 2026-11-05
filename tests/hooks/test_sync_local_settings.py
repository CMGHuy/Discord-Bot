import importlib.util
import json
import pathlib

_P = pathlib.Path(__file__).parent.parent.parent / ".claude" / "hooks" / "sync-local-settings.py"
_S = importlib.util.spec_from_file_location("sync_local_settings", _P)
m = importlib.util.module_from_spec(_S)
_S.loader.exec_module(m)


def _write(root, allow):
    f = root / ".claude" / "settings.local.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"permissions": {"allow": allow}}))
    return f


def test_copies_when_missing(tmp_path):
    main, wt = tmp_path / "main", tmp_path / "wt"
    wt.mkdir()
    _write(main, ["Bash(ls:*)"])
    assert "copied" in m.sync(wt, main)
    assert json.loads((wt / m.REL).read_text())["permissions"]["allow"] == ["Bash(ls:*)"]


def test_merges_missing_rules_and_keeps_local_only(tmp_path):
    main, wt = tmp_path / "main", tmp_path / "wt"
    _write(main, ["A", "B"])
    _write(wt, ["B", "C"])
    assert "added" in m.sync(wt, main)
    assert json.loads((wt / m.REL).read_text())["permissions"]["allow"] == ["B", "C", "A"]
    assert m.sync(wt, main) == "already in step"


def test_main_checkout_and_absent_source_are_noops(tmp_path):
    _write(tmp_path / "main", ["A"])
    assert m.sync(tmp_path / "main", tmp_path / "main") == "nothing to do"
    (tmp_path / "wt").mkdir()
    assert m.sync(tmp_path / "wt", tmp_path / "empty") == "nothing to do"


def test_deny_mirrors_main_so_a_lifted_restriction_lifts_everywhere(tmp_path):
    main, wt = tmp_path / "main", tmp_path / "wt"
    for root, deny in ((main, ["Read(./.env.bak)"]), (wt, ["Read(./.env)", "Read(./.env.bak)"])):
        f = _write(root, ["A"])
        f.write_text(json.dumps({"permissions": {"allow": ["A"], "deny": deny}}))
    assert "added" in m.sync(wt, main)
    assert json.loads((wt / m.REL).read_text())["permissions"]["deny"] == ["Read(./.env.bak)"]
    assert m.sync(wt, main) == "already in step"
