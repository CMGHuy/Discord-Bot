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


def test_dry_run_with_widened_selection_exits_without_running(testrun, monkeypatch, capsys):
    monkeypatch.setattr(testrun, "select", lambda *_a, **_k: FakeSelection())
    monkeypatch.setattr(testrun, "changed_paths", lambda: ["swingbot/core/edge/rsi.py"])
    calls = []
    monkeypatch.setattr(testrun, "run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(testrun, "undefined_names", lambda *a, **k: calls.append(a) or [])
    monkeypatch.setattr(sys, "argv", ["testrun.py", "changed", "--dry-run"])
    with pytest.raises(SystemExit) as exc:
        testrun.main()
    assert exc.value.code == 0
    assert calls == [], "dry-run must not run the lint gate or pytest"
    assert "registry dispatch" in capsys.readouterr().out


def test_audit_misses_finds_the_uncovered_failure(testrun):
    misses = testrun.audit_misses(
        ["tests/planning/test_plan_engine.py", "tests/scanning/"],
        [
            "tests/planning/test_plan_engine.py::test_a",
            "tests/scanning/test_engine.py::test_b",
            "tests/market/test_session.py::test_c",
        ],
    )
    assert misses == ["tests/market/test_session.py::test_c"]


def test_audit_misses_is_empty_when_everything_was_selected(testrun):
    assert testrun.audit_misses(
        ["tests/planning/"], ["tests/planning/test_plan_engine.py::test_a"]
    ) == []


def test_audit_is_an_accepted_flag(testrun):
    assert testrun.build_parser().parse_args(["changed", "--audit"]).audit is True


def _fake_full_run(monkeypatch, testrun, failed):
    monkeypatch.setattr(testrun, "run", lambda args: ({"passed": 1}, failed, 1.0, 0))


def test_run_audit_reports_a_miss_and_fails(testrun, monkeypatch, capsys):
    _fake_full_run(monkeypatch, testrun, ["tests/market/test_session.py::test_c"])
    assert testrun.run_audit(["tests/planning/"]) == 1
    out = capsys.readouterr().out
    assert "AUDIT: MISS" in out and "tests/market/test_session.py::test_c" in out


def test_run_audit_ok_says_covered_never_safe(testrun, monkeypatch, capsys):
    _fake_full_run(monkeypatch, testrun, [])
    assert testrun.run_audit(["tests/planning/"]) == 0
    out = capsys.readouterr().out
    assert "covered every failure" in out and "safe" not in out


def test_run_audit_with_empty_selection_counts_every_failure_as_a_miss(testrun, monkeypatch, capsys):
    _fake_full_run(monkeypatch, testrun, ["tests/a/test_x.py::test_1"])
    assert testrun.run_audit([]) == 1


def test_audit_on_widened_selection_skips_and_does_not_claim_ok(testrun, monkeypatch, capsys):
    """Widened means the run already WAS the full suite: nothing to compare."""
    monkeypatch.setattr(testrun, "select", lambda paths, repo: FakeSelection(full=True))
    monkeypatch.setattr(sys, "argv", ["testrun.py", "changed", "--audit", "--skip-lint-gate"])
    monkeypatch.setattr(testrun, "db_preflight", lambda: None)
    calls = []
    monkeypatch.setattr(testrun, "run", lambda a: calls.append(a) or ({"passed": 1}, [], 1.0, 0))
    assert testrun.main() == 0
    out = capsys.readouterr().out
    assert len(calls) == 1
    assert "AUDIT: SKIPPED" in out and "AUDIT: OK" not in out


def test_audit_with_dry_run_runs_nothing(testrun, monkeypatch):
    monkeypatch.setattr(testrun, "select", lambda paths, repo: FakeSelection(targets=["tests/x/"], full=False))
    monkeypatch.setattr(sys, "argv", ["testrun.py", "changed", "--audit", "--dry-run"])
    monkeypatch.setattr(testrun, "run", lambda a: pytest.fail("must not run"))
    with pytest.raises(SystemExit) as exc:
        testrun.main()
    assert exc.value.code == 0
