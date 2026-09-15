from swingbot.core.analytics.journal import build_entry


def _trade(**over):
    t = {
        "trade_id": "t1", "ticker": "AAPL", "direction": "bullish",
        "outcome": "loss", "r_realized": -1.0, "strategy": "RSI",
        "source": "confluence", "horizon_key": "2w",
        "risk_features": {"regime2_state": "bear_volatile", "session_bucket": "close"},
        "cohort_label": "COHORT_POOR",
        "cohort_stats": {"run_date": "2026-09-14", "expectancy_r": -0.38},
    }
    t.update(over)
    return t


def test_entry_carries_the_risk_features_verbatim():
    e = build_entry(_trade(), None)
    assert e["risk_features"]["regime2_state"] == "bear_volatile"
    assert e["risk_features"]["session_bucket"] == "close"


def test_entry_carries_the_cohort_label_and_its_freeze_date():
    e = build_entry(_trade(), None)
    assert e["cohort_label"] == "COHORT_POOR"
    assert e["cohort_run_date"] == "2026-09-14"


def test_a_trade_predating_v86_journals_without_raising():
    t = _trade()
    del t["risk_features"], t["cohort_label"], t["cohort_stats"]
    e = build_entry(t, None)
    assert e["risk_features"] == {}
    assert e["cohort_label"] is None
    assert e["cohort_run_date"] is None
