import pytest

from swingbot.core.analytics.aggregate import DIMENSIONS, StatRow, rs_quintile_label, stats_by


def _t(strategy_sources, status, pnl, direction="bullish", entry=100.0, stop_loss=95.0, exit_price=None):
    return {"target_sources": strategy_sources, "status": status, "direction": direction,
            "entry": entry, "stop_loss": stop_loss,
            "exit_price": exit_price if exit_price is not None else (104.0 if status == "win" else 96.0),
            "realized_pnl_amount": pnl, "closed_at": "2026-03-10T10:00:00+00:00"}


def test_stats_by_strategy_groups_and_sums():
    closed = [
        _t(["EMA20"], "win", 80.0),
        _t(["EMA20"], "loss", -40.0),
        _t(["Fib 61.8%"], "win", 60.0),
    ]
    rows = stats_by(closed, "strategy")
    assert isinstance(rows[0], StatRow)
    by_key = {r.key: r for r in rows}
    assert by_key["EMA20"].n == 2 and by_key["EMA20"].wins == 1 and by_key["EMA20"].losses == 1
    assert by_key["EMA20"].total_pnl == 40.0
    assert by_key["Fib 61.8%"].n == 1 and by_key["Fib 61.8%"].total_pnl == 60.0


def test_stats_by_missing_pnl_counts_as_zero():
    closed = [_t(["EMA20"], "win", None)]
    rows = stats_by(closed, "strategy")
    assert rows[0].total_pnl == 0.0


def test_stats_by_sorted_by_n_desc():
    closed = [_t(["EMA20"], "win", 10.0), _t(["EMA20"], "loss", -5.0), _t(["Fib 61.8%"], "win", 5.0)]
    rows = stats_by(closed, "strategy")
    assert [r.key for r in rows] == ["EMA20", "Fib 61.8%"]


def _full_trade():
    return {
        "target_sources": ["EMA20"], "status": "win", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0, "realized_pnl_amount": 80.0,
        "horizon_key": "4w", "badge": "VALIDATED", "source": "confluence",
        "confidence_level": 4, "ticker": "AAPL",
        # 2026-03-09 is a Monday in both UTC and Europe/Berlin.
        "opened_at": "2026-03-06T10:00:00+00:00", "closed_at": "2026-03-09T10:00:00+00:00",
    }


def test_all_dimensions_present():
    """v32 Task 11: "tier" (A/B/C) retired -- "confidence" already covered
    the same role, so DIMENSIONS dropped from 10 to 9. v93 then added
    "ledger" (main/weak) as its own grouping dimension, back to 10; v152
    adds "taken" (followed/paper): 11. v146 I4 adds "confluence"
    (target-source count) and "rs_quintile" (entry RS percentile in
    20-point bands): 13."""
    assert set(DIMENSIONS) == {"strategy", "horizon", "badge", "confidence",
                               "direction", "dow", "month", "ticker", "source", "ledger",
                               "taken", "confluence", "rs_quintile"}


def test_dimension_extractors():
    closed = [_full_trade()]
    assert stats_by(closed, "badge")[0].key == "VALIDATED"
    assert stats_by(closed, "source")[0].key == "confluence"
    assert stats_by(closed, "horizon")[0].key == "4w"
    assert stats_by(closed, "confidence")[0].key == "4"
    assert stats_by(closed, "direction")[0].key == "bullish"
    assert stats_by(closed, "ticker")[0].key == "AAPL"
    assert stats_by(closed, "dow")[0].key == "Monday"
    assert stats_by(closed, "month")[0].key == "2026-03"


def test_taken_splits_followed_from_paper():
    followed = {**_full_trade(), "taken_by": [123456789012345678]}
    paper = _full_trade()
    emptied = {**_full_trade(), "taken_by": []}
    rows = {r.key: r for r in stats_by([followed, paper, emptied], "taken")}
    assert set(rows) == {"followed", "paper"}
    assert rows["followed"].n == 1
    assert rows["paper"].n == 2


def test_taken_never_buckets_as_unknown():
    assert [r.key for r in stats_by([_full_trade()], "taken")] == ["paper"]


def test_unknown_fields_bucket_as_unknown():
    closed = [{"target_sources": [], "status": "win", "direction": "bullish",
              "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0}]
    assert stats_by(closed, "badge")[0].key == "unknown"
    assert stats_by(closed, "source")[0].key == "unknown"
    assert stats_by(closed, "confidence")[0].key == "unknown"


def test_stats_by_raises_on_unknown_dimension():
    with pytest.raises(ValueError):
        stats_by([], "nope")


def test_group_by_is_public_and_row_for_matches_stats_by():
    from swingbot.core.analytics.aggregate import group_by, row_for
    closed = [_t(["EMA20"], "win", 80.0), _t(["EMA20"], "loss", -40.0)]
    groups = group_by(closed, "strategy")
    assert set(groups) == {"EMA20"} and len(groups["EMA20"]) == 2
    assert row_for("EMA20", groups["EMA20"]) == stats_by(closed, "strategy")[0]


# --- v146 I4: confluence and rs_quintile ---------------------------------

def test_confluence_counts_target_sources():
    two = dict(_full_trade(), target_sources=["EMA20", "Fib 61.8%"])
    assert stats_by([two], "confluence")[0].key == "2"
    assert stats_by([_full_trade()], "confluence")[0].key == "1"


def test_confluence_empty_list_reads_zero_and_missing_reads_unknown():
    empty = dict(_full_trade(), target_sources=[])
    assert stats_by([empty], "confluence")[0].key == "0"
    missing = {k: v for k, v in _full_trade().items() if k != "target_sources"}
    assert stats_by([missing], "confluence")[0].key == "unknown"


def test_rs_quintile_reads_entry_context():
    trade = dict(_full_trade(), entry_context={"rs_pctile": 64.0})
    assert stats_by([trade], "rs_quintile")[0].key == "Q4"


def test_rs_quintile_unknown_without_entry_context():
    assert stats_by([_full_trade()], "rs_quintile")[0].key == "unknown"
    assert stats_by([dict(_full_trade(), entry_context=None)], "rs_quintile")[0].key == "unknown"
    assert stats_by([dict(_full_trade(), entry_context={})], "rs_quintile")[0].key == "unknown"
    assert stats_by([dict(_full_trade(), entry_context="garbage")], "rs_quintile")[0].key == "unknown"


@pytest.mark.parametrize("value, label", [
    (0.0, "Q1"), (19.999, "Q1"), (20.0, "Q2"), (39.9, "Q2"), (40.0, "Q3"),
    (59.9, "Q3"), (60.0, "Q4"), (79.9, "Q4"), (80.0, "Q5"), (100.0, "Q5"),
    (-3.0, "Q1"), (104.0, "Q5"),
    (None, "unknown"), (float("nan"), "unknown"), ("n/a", "unknown"),
])
def test_rs_quintile_label_edges(value, label):
    assert rs_quintile_label(value) == label
