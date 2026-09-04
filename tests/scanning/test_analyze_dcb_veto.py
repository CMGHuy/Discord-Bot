"""The live scan honours the veto -- and only when the flag is on."""
import pytest

from swingbot import config
from swingbot.core.scanning import analyze


@pytest.fixture
def veto_on(monkeypatch):
    monkeypatch.setattr(config, "DEAD_CAT_BOUNCE_VETO", True)


@pytest.fixture
def veto_off(monkeypatch):
    monkeypatch.setattr(config, "DEAD_CAT_BOUNCE_VETO", False)


def test_the_flag_off_never_computes_the_verdict(veto_off, monkeypatch):
    """Not just 'does not block' -- does not even run. The detector walks a
    20-bar window per horizon per ticker, and paying for it while the feature
    is off is a scan-budget regression for a disabled flag."""
    called = []
    monkeypatch.setattr(analyze, "dead_cat_bounce",
                        lambda *a, **k: called.append(1) or {"detected": False})
    analyze.veto_bullish_for(None)      # the seam D5 introduces
    assert called == []


def test_the_flag_on_computes_the_verdict(veto_on, monkeypatch):
    monkeypatch.setattr(analyze, "dead_cat_bounce",
                        lambda *a, **k: {"detected": True})
    assert analyze.veto_bullish_for(object()) is True


def test_a_detector_failure_never_blocks_the_scan(veto_on, monkeypatch):
    """A pattern detector is an accelerator, not trading state. If it raises,
    the scan proceeds unvetoed rather than losing the ticker entirely."""
    def boom(*a, **k):
        raise ValueError("bad frame")
    monkeypatch.setattr(analyze, "dead_cat_bounce", boom)
    assert analyze.veto_bullish_for(object()) is False
