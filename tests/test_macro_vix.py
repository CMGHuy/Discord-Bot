import pytest

import swingbot.core.macro.vix as vix_mod


def _stub(monkeypatch, vix_series, vix3m_series=None):
    def fake(fred_id, **kw):
        if fred_id == "VIXCLS":
            return vix_series
        if fred_id == "VXVCLS":
            return vix3m_series
        return None
    monkeypatch.setattr(vix_mod.fred, "fred_series", fake)


def _series(levels):
    return [(f"d{i}", float(v)) for i, v in enumerate(levels)]


@pytest.mark.parametrize("level,regime", [
    (12.0, "calm"), (15.99, "calm"), (16.0, "normal"), (23.99, "normal"),
    (24.0, "elevated"), (31.99, "elevated"), (32.0, "stress"), (80.0, "stress"),
])
def test_regime_boundaries(monkeypatch, level, regime):
    _stub(monkeypatch, _series([20.0] * 300 + [level]))
    assert vix_mod.vix_state()["regime"] == regime


def test_percentile_golden(monkeypatch):
    # 251 obs at 1..251, then a final 226: it is >= 227 of the 252 values.
    window = list(range(1, 252))          # 1..251
    window.append(226)
    _stub(monkeypatch, _series(window))
    state = vix_mod.vix_state()
    assert state["percentile_1y"] == pytest.approx(100.0 * 227 / 252, abs=0.1)


def test_term_structure(monkeypatch):
    _stub(monkeypatch, _series([20.0] * 260), _series([25.0] * 260))
    assert vix_mod.vix_state()["term_structure"] == "contango"       # VIX < VIX3M
    _stub(monkeypatch, _series([30.0] * 260), _series([25.0] * 260))
    assert vix_mod.vix_state()["term_structure"] == "backwardation"  # VIX > VIX3M
    _stub(monkeypatch, _series([20.0] * 260), None)
    assert vix_mod.vix_state()["term_structure"] is None             # degrades, no error


def test_no_data_returns_none(monkeypatch):
    _stub(monkeypatch, None, None)
    assert vix_mod.vix_state() is None
