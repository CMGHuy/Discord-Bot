"""v187 D2: the alert's suggested size and the engine's trade size are the
same compute_position_size call -- equal, and at the 2% cap, for a legacy
risk_pct=10 account row."""
from types import SimpleNamespace

from swingbot.core.edge.sizing import RISK_CEILING_PCT
from swingbot.core.planning import account as acct
from swingbot.core.scanning import analyze

LEGACY = {"balance": 10_000.0, "risk_pct": 10.0, "position_pct": 20.0, "max_position_pct": 100.0,
          "max_position_value_absolute": 0.0, "max_risk_amount_absolute": 0.0, "sizing_mode": "risk_pct"}


def test_alert_size_equals_engine_size_for_a_legacy_ten_percent_row(monkeypatch):
    monkeypatch.setattr(acct.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(acct, "load_account_config", lambda: dict(LEGACY))
    monkeypatch.setattr(analyze, "load_account_config", lambda: dict(LEGACY))
    monkeypatch.setattr(analyze.trade_log, "get_trades", lambda **k: [])
    monkeypatch.setattr(analyze.corr_mod, "cluster_exposure", lambda *a, **k: {"cluster": []})
    plan = SimpleNamespace(ticker="AAPL", trigger_price=100.0, entry_price=100.0, stop_loss=98.0,
                           tp1=104.0, strategy="X", quality_breakdown=[], quality_score=0,
                           badge=None, badge_stats=None)
    item = SimpleNamespace(plan_v2=plan, result=SimpleNamespace(ticker="AAPL"))

    alert = analyze.build_decision_context(item, {}, None)["sizing"]
    engine = acct.compute_position_size(100.0, 98.0)   # shared function reached by performance.log_trade sizing

    assert alert["shares"] == engine["shares"] == 100.0
    assert alert["risk_pct"] == engine["risk_pct"] == RISK_CEILING_PCT
    assert engine["risk_amount"] == 200.0
