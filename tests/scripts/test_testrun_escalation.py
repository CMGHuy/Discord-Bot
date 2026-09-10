import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "dev"))


def test_a_token_edit_escalates_fast_to_full(monkeypatch):
    """tests/charts/test_chart_theme.py reads frontend/src/styles/tokens.css
    and runs only in the slow tier, so a token edit must not let `fast` skip it."""
    import testrun

    monkeypatch.setattr(testrun, "changed_paths", lambda: ["frontend/src/styles/tokens.css"])
    escalate, reason = testrun.should_escalate()
    assert escalate
    assert "frontend/src/styles/tokens.css" in reason


def test_the_deleted_admin_palette_is_no_longer_a_trigger():
    import testrun

    assert not any(prefix.startswith("swingbot/admin/static") for prefix in testrun.ESCALATE_PREFIXES)


def test_an_unrelated_frontend_edit_does_not_escalate(monkeypatch):
    import testrun

    monkeypatch.setattr(testrun, "changed_paths", lambda: ["frontend/src/app/ui/chip.ts"])
    assert testrun.should_escalate() == (False, "")
