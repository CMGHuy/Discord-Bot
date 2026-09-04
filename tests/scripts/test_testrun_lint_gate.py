import sys
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "dev"))


def test_undefined_names_flags_a_broken_module(tmp_path):
    import testrun

    bad = tmp_path / "bad_module.py"
    bad.write_text("def go():\n    return not_a_real_name\n")

    found = testrun.undefined_names([str(bad)])

    assert len(found) == 1
    assert "not_a_real_name" in found[0]


def test_undefined_names_is_clean_on_a_good_module(tmp_path):
    import testrun

    good = tmp_path / "good_module.py"
    good.write_text("import os\n\n\ndef go():\n    return os.getcwd()\n")

    assert testrun.undefined_names([str(good)]) == []


def test_the_repo_itself_has_no_undefined_names():
    """The gate must be green on the tree it is about to police."""
    import testrun

    assert testrun.undefined_names() == []


def run_main(monkeypatch, profile, target=None):
    import testrun

    monkeypatch.setattr(sys, "argv", ["testrun.py", profile] + ([target] if target else []))
    return testrun.main()


@pytest.mark.parametrize("profile", ["file", "lf", "fast"])
def test_narrow_profiles_skip_undefined_name_gate(monkeypatch, profile):
    import testrun

    called = []
    monkeypatch.setattr(testrun, "should_escalate", lambda: (False, ""))
    monkeypatch.setattr(testrun, "undefined_names", lambda: called.append(True) or [])
    monkeypatch.setattr(testrun, "run", lambda args: ({"passed": 1}, [], 0.1, 0))

    assert run_main(monkeypatch, profile, "tests/scripts/test_testrun_lint_gate.py" if profile == "file" else None) == 0
    assert called == []


def test_full_gate_runs_before_pytest(monkeypatch, capsys):
    import testrun

    monkeypatch.setattr(sys, "argv", ["testrun.py", "full"])
    monkeypatch.setattr(testrun, "undefined_names", lambda: ["swingbot/x.py:2: undefined name 'x'"])
    monkeypatch.setattr(testrun, "run", lambda args: pytest.fail("pytest must not run"))

    assert testrun.main() == 1
    assert "undefined name(s)" in capsys.readouterr().out


def test_escalated_fast_runs_full_gate(monkeypatch):
    import testrun

    monkeypatch.setattr(sys, "argv", ["testrun.py", "fast"])
    monkeypatch.setattr(testrun, "should_escalate", lambda: (True, "probe touched"))
    calls = []
    monkeypatch.setattr(testrun, "undefined_names", lambda: calls.append(True) or [])
    monkeypatch.setattr(testrun, "run", lambda args: ({"passed": 1}, [], 0.1, 0))

    assert testrun.main() == 0
    assert calls == [True]


def test_git_listing_failure_fails_closed(monkeypatch, capsys):
    import testrun

    monkeypatch.setattr(sys, "argv", ["testrun.py", "full"])
    monkeypatch.setattr(testrun, "undefined_names", lambda: (_ for _ in ()).throw(RuntimeError("git ls-files failed; undefined-name gate unavailable")))
    monkeypatch.setattr(testrun, "run", lambda args: pytest.fail("pytest must not run"))

    assert testrun.main() == 1
    assert "gate unavailable" in capsys.readouterr().out


def test_git_listing_exception_fails_closed(monkeypatch, capsys):
    import testrun

    monkeypatch.setattr(sys, "argv", ["testrun.py", "full"])
    monkeypatch.setattr(testrun.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("git unavailable")))
    monkeypatch.setattr(testrun, "run", lambda args: pytest.fail("pytest must not run"))

    assert testrun.main() == 1
    assert "gate unavailable" in capsys.readouterr().out


def test_pyflakes_process_failure_fails_closed_before_pytest(monkeypatch, capsys):
    import testrun

    def _run(cmd, **kwargs):
        if cmd[:2] == ["git", "ls-files"]:
            return testrun.subprocess.CompletedProcess(
                cmd, 0, stdout="swingbot/example.py\n", stderr=""
            )
        return testrun.subprocess.CompletedProcess(
            cmd, 1, stdout="", stderr="pyflakes could not start"
        )

    monkeypatch.setattr(sys, "argv", ["testrun.py", "full"])
    monkeypatch.setattr(testrun.subprocess, "run", _run)
    monkeypatch.setattr(testrun, "run", lambda args: pytest.fail("pytest must not run"))

    assert testrun.main() == 1
    output = capsys.readouterr().out
    assert "gate unavailable" in output
    assert "pyflakes could not start" in output
