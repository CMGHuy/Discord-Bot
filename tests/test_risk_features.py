import datetime as dt

import pytest

from swingbot.core.scanning.risk_features import build


def _kwargs(**over):
    base = dict(
        regime2_state="bear_volatile", confidence_level=2, htf_bias="bullish",
        direction="bullish", confluence_count=3, entry=100.0, level_price=98.0,
        stop_loss=96.0, atr_val=2.0, close=100.0, rs_percentile=45.0,
        now=dt.datetime(2026, 9, 14, 15, 45),
    )
    base.update(over)
    return base


def test_builds_every_documented_feature():
    f = build(**_kwargs())
    assert set(f) == {
        "regime2_state", "confidence_level", "htf_agree", "confluence_count",
        "dist_to_level_atr", "stop_width_atr", "atr_pct", "rs_percentile",
        "session_bucket", "days_to_earnings",
    }


def test_htf_agree_is_true_only_when_bias_matches_direction():
    assert build(**_kwargs(htf_bias="bullish", direction="bullish"))["htf_agree"] is True
    assert build(**_kwargs(htf_bias="bearish", direction="bullish"))["htf_agree"] is False
    assert build(**_kwargs(htf_bias=None))["htf_agree"] is None


def test_distances_are_expressed_in_atr():
    f = build(**_kwargs(entry=100.0, level_price=98.0, stop_loss=96.0, atr_val=2.0))
    assert f["dist_to_level_atr"] == pytest.approx(1.0)
    assert f["stop_width_atr"] == pytest.approx(2.0)


def test_atr_pct_is_atr_over_close():
    assert build(**_kwargs(atr_val=2.0, close=100.0))["atr_pct"] == pytest.approx(2.0)


def test_zero_atr_yields_none_rather_than_a_divide_by_zero():
    f = build(**_kwargs(atr_val=0.0))
    assert f["dist_to_level_atr"] is None
    assert f["stop_width_atr"] is None
    assert f["atr_pct"] is None


def test_session_buckets_split_open_midday_close():
    assert build(**_kwargs(now=dt.datetime(2026, 9, 14, 9, 45)))["session_bucket"] == "open"
    assert build(**_kwargs(now=dt.datetime(2026, 9, 14, 12, 30)))["session_bucket"] == "midday"
    assert build(**_kwargs(now=dt.datetime(2026, 9, 14, 15, 50)))["session_bucket"] == "close"


def test_days_to_earnings_is_null_when_no_calendar_is_available():
    assert build(**_kwargs())["days_to_earnings"] is None
    assert build(**_kwargs(days_to_earnings=3))["days_to_earnings"] == 3


def test_every_feature_is_json_serialisable():
    import json
    json.dumps(build(**_kwargs()))   # must not raise
