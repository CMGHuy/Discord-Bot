"""v232: per-trade rows carry strategy, horizon and ticker -- they never reach git."""
import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


def _ignored(path: str) -> bool:
    done = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=REPO)
    assert done.returncode in (0, 1), done
    return done.returncode == 0


@pytest.mark.parametrize("path", [
    "data/v232/trade-rows.jsonl",
    "data/v232/layer2/lane-base.jsonl",
    "data/v232/bars/raw/daily/AAPL.csv",
    "data/v232/bars/split/daily/_manifest.json",
])
def test_git_ignores_the_work_dir(path):
    assert _ignored(path), f"{path} is not git-ignored"


@pytest.mark.parametrize("path", [
    "docs/superpowers/results/2026-11-20-v232-live-replay-reconciliation.md",
    "docs/superpowers/results/2026-11-20-v232-live-replay-reconciliation.json",
    "scripts/reports/reconcile/sessions.py",
])
def test_the_committed_outputs_are_not_ignored(path):
    assert not _ignored(path), f"{path} must stay committable"
