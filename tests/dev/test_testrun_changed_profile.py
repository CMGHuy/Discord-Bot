"""The `changed` profile wires selection into the runner (v99, Task V99-3)."""
import importlib.util
import pathlib
import sys
from dataclasses import dataclass, field

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def testrun():
    spec = importlib.util.spec_from_file_location("testrun_mod", REPO / "scripts/dev/testrun.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@dataclass
class FakeSelection:
    targets: list = field(default_factory=list)
    full: bool = True
    reason: str = "registry dispatch"
    changed: list = field(default_factory=list)


def test_escalate_prefixes_come_from_select_tests(testrun):
    """One list, not two copies that can drift apart."""
    sys.path.insert(0, str(REPO / "scripts/dev"))
    import select_tests
    assert testrun.ESCALATE_PREFIXES is select_tests.ESCALATE_PREFIXES


def test_changed_is_an_accepted_profile(testrun):
    args = testrun.build_parser().parse_args(["changed"])
    assert args.profile == "changed"
    assert args.dry_run is False


def test_build_args_for_changed_takes_explicit_targets(testrun):
    args = testrun.build_args("changed", [], targets=["tests/planning/", "tests/test_x.py"])
    assert args[-2:] == ["tests/planning/", "tests/test_x.py"]
    assert "-n" not in args, "selected sets are small; xdist startup dominates"


def test_full_selection_falls_through_to_the_full_profile(testrun, monkeypatch, capsys):
    monkeypatch.setattr(testrun, "select", lambda *_a, **_k: FakeSelection())
    monkeypatch.setattr(testrun, "changed_paths", lambda: ["swingbot/core/edge/rsi.py"])
    resolved = testrun.resolve_changed(testrun.build_parser().parse_args(["changed"]))
    assert resolved is None, "None means: run the full profile"
    assert "registry dispatch" in capsys.readouterr().out


def test_dry_run_prints_targets_and_exits_zero(testrun, monkeypatch, capsys):
    sel = FakeSelection(targets=["tests/scanning/"], full=False, reason="1 file")
    monkeypatch.setattr(testrun, "select", lambda *_a, **_k: sel)
    monkeypatch.setattr(testrun, "changed_paths", lambda: ["tests/scanning/conftest.py"])
    args = testrun.build_parser().parse_args(["changed", "--dry-run"])
    with pytest.raises(SystemExit) as exc:
        testrun.resolve_changed(args)
    assert exc.value.code == 0
    assert "tests/scanning/" in capsys.readouterr().out
