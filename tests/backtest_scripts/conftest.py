"""Shared fixtures for tests/backtest_scripts/."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))


@pytest.fixture
def screen_null_v1(monkeypatch):
    """v230: screen_idea on the frozen v1 null -- the pre-v230 tests pin v1 output."""
    import screen_idea
    monkeypatch.setattr(screen_idea, "NULL_VERSION", "v1")
