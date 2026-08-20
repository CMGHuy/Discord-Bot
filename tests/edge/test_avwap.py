import pandas as pd
import pytest

from swingbot.core.edge.factors import anchored_vwap, avwap_anchors


def _frame(n=200):
    closes = [100 + (i % 20) - 10 for i in range(n)]
    return pd.DataFrame({
        "Open": closes,
        "High": [c + 2 for c in closes],
        "Low": [c - 2 for c in closes],
        "Close": closes,
        "Volume": [1_000_000 + (i % 7) * 100_000 for i in range(n)],
    })


def test_anchors_are_all_within_the_frame():
    df = _frame()
    for a in avwap_anchors(df):
        assert 0 <= a < len(df)


def test_no_anchor_within_span_of_the_last_bar():
    """NO-LOOKAHEAD: a pivot needs span=5 bars of confirmation on both sides,
    so an anchor closer than that to the end would be a pivot only because
    the data ran out. factors.py:136-141 documents this; this test enforces it
    against future edits."""
    df = _frame()
    # Volume anchor computed same way as production: start + argmax over the lookback window
    lookback = 120
    start = max(0, len(df) - lookback)
    vol_anchor = start + int(df["Volume"].values[start:].argmax())
    anchors = avwap_anchors(df)
    # Verify the volume anchor is actually among the returned anchors
    assert vol_anchor in anchors, f"volume anchor {vol_anchor} should be in returned anchors {anchors}"
    # All pivots (non-volume anchors) must be at least 6 bars from the end
    pivots = [a for a in anchors if a != vol_anchor]
    assert all(a <= len(df) - 6 for a in pivots)


def test_anchored_vwap_starts_at_the_anchor_bar_price():
    df = _frame()
    series = anchored_vwap(df, 100)
    assert len(series) == len(df) - 100
    bar = df.iloc[100]
    expected = (bar["High"] + bar["Low"] + bar["Close"]) / 3.0
    assert series.iloc[0] == pytest.approx(expected)


def test_multiple_avwap_anchors_count_as_one_confirming_method():
    """The inflation guard, verified not assumed: several anchors landing in
    one cluster must not let a single method reach Lv5 wearing three hats."""
    from swingbot.core.scanning.confidence import _resolve_confluence
    count, families = _resolve_confluence(None, ["AVWAP", "AVWAP", "EMA"])
    assert count == 2
    assert families == ["AVWAP", "EMA"]
