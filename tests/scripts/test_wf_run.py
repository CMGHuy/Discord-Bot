"""wf_run.py's --window shorthand and --once-guard (Task E92)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import wf_run  # noqa: E402


def test_once_guard_refuses_when_result_section_already_present(tmp_path, monkeypatch, capsys):
    doc = tmp_path / "shot.md"
    doc.write_text("# Pre-registration\n\n## Result\n\nalready ran once\n", encoding="utf-8")

    def _boom(*a, **k):
        raise AssertionError("collect_portfolio_signals must not run once the guard refuses")

    monkeypatch.setattr(wf_run, "collect_portfolio_signals", _boom)
    monkeypatch.setattr(sys, "argv", ["wf_run.py", "--portfolio", "--once-guard", str(doc)])

    rc = wf_run.main()

    assert rc == 1
    assert "REFUSING" in capsys.readouterr().err


def test_once_guard_allows_run_when_no_result_section_yet(tmp_path, monkeypatch):
    doc = tmp_path / "shot.md"
    doc.write_text("# Pre-registration\n\n(no result yet)\n", encoding="utf-8")

    calls = []

    def _fake_collect(start, end, strategies=None, horizons=None):
        calls.append((start, end))
        return []

    monkeypatch.setattr(wf_run, "collect_portfolio_signals", _fake_collect)
    monkeypatch.setattr(sys, "argv", ["wf_run.py", "--portfolio", "--once-guard", str(doc)])

    rc = wf_run.main()

    assert rc == 0
    assert len(calls) == 1


def test_once_guard_ignores_prose_that_merely_mentions_the_marker(tmp_path, monkeypatch):
    # A pre-registration doc describing its own one-shot mechanism will
    # legitimately contain the phrase "## Result" in prose (e.g. explaining
    # what the guard checks for) without an actual '## Result' heading ever
    # having been appended -- that must NOT be mistaken for a completed run.
    doc = tmp_path / "shot.md"
    doc.write_text(
        "# Pre-registration\n\n"
        "This guard refuses to run if this file already has a `## Result` "
        "section appended.\n",
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(wf_run, "collect_portfolio_signals",
                        lambda start, end, strategies=None, horizons=None: calls.append(1) or [])
    monkeypatch.setattr(sys, "argv", ["wf_run.py", "--portfolio", "--once-guard", str(doc)])

    assert wf_run.main() == 0
    assert calls == [1]


def test_once_guard_allows_run_when_file_does_not_exist_yet(tmp_path, monkeypatch):
    doc = tmp_path / "does-not-exist-yet.md"

    monkeypatch.setattr(wf_run, "collect_portfolio_signals", lambda *a, **k: [])
    monkeypatch.setattr(sys, "argv", ["wf_run.py", "--portfolio", "--once-guard", str(doc)])

    assert wf_run.main() == 0


def test_window_overrides_start_end_in_portfolio_mode(monkeypatch):
    calls = []

    def _fake_collect(start, end, strategies=None, horizons=None):
        calls.append((start, end))
        return []

    monkeypatch.setattr(wf_run, "collect_portfolio_signals", _fake_collect)
    monkeypatch.setattr(sys, "argv",
                        ["wf_run.py", "--portfolio", "--window", "2024-01-01:2025-12-31"])

    assert wf_run.main() == 0
    assert calls == [("2024-01-01", "2025-12-31")]


def test_window_replaces_anchored_folds_in_fold_mode(monkeypatch):
    captured = {}

    def _fake_run_folds(overrides, folds=None, run_fn=None):
        captured["folds"] = folds
        return {"folds": [], "pooled_delta_expectancy_r": None}

    monkeypatch.setattr(wf_run, "run_folds", _fake_run_folds)
    monkeypatch.setattr(sys, "argv",
                        ["wf_run.py", "--full", "--window", "2024-01-01:2025-12-31"])

    assert wf_run.main() == 0
    assert captured["folds"] == (("2024-01-01", "2024-01-01", "2024-01-01", "2025-12-31"),)


def test_no_window_keeps_anchored_folds(monkeypatch):
    from swingbot.core.backtest_wf import ANCHORED_FOLDS

    captured = {}

    def _fake_run_folds(overrides, folds=None, run_fn=None):
        captured["folds"] = folds
        return {"folds": [], "pooled_delta_expectancy_r": None}

    monkeypatch.setattr(wf_run, "run_folds", _fake_run_folds)
    monkeypatch.setattr(sys, "argv", ["wf_run.py", "--full"])

    assert wf_run.main() == 0
    assert captured["folds"] == ANCHORED_FOLDS
