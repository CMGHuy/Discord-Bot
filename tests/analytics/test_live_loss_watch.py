"""v164 live loss watch: the D1 matcher (LW1) and the D2 loss rule (LW2).

Pure functions, plain dict fixtures, no DB. Trade timestamps are UTC ISO like
`performance.log_trade` writes them; every day boundary is a Berlin date."""
import datetime as dt

import pytest

from swingbot.core.analytics import calibration
from swingbot.core.analytics.calibration import (
    EXPR_WATCH_START,
    WATCH_COUNT_KEYS,
    LiveTrade,
    MatchResult,
    berlin_entry_date,
    match_live_rows,
    row_key,
)

CONF_HORIZONS = ("2w", "4w", "2m")


def _reg(source, strategy, horizon, status="WEAK", expr=-0.2,
         window="2024-01-01..2025-12-31", run_date="2026-07-17"):
    return {"source": source, "strategy": strategy, "horizon": horizon, "status": status,
            "n": 400, "win_rate": 48.8, "expectancy_r": expr, "window": window,
            "run_date": run_date}


def _registry():
    rows = [_reg("confluence", "ALL", h) for h in CONF_HORIZONS]
    rows.append(_reg("confluence", "ALL", None))
    rows.append(_reg("strategy", "Fibonacci", None, status="VALIDATED", expr=0.105))
    return rows


def _trade(**over):
    """A closed, regular-lane, post-start confluence 4w win of +2R."""
    base = {"status": "win", "source": "confluence", "strategy": "S/R Confluence",
            "horizon_key": "4w", "opened_at": "2026-10-19T14:00:00+00:00",
            "closed_at": "2026-10-23T14:00:00+00:00", "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 110.0, "legs": [],
            "ledger": "main"}
    base.update(over)
    return base


CONF_4W = ("confluence", "ALL", "4w")
CONF_POOLED = ("confluence", "ALL", None)
FIB_POOLED = ("strategy", "Fibonacci", None)


def _sizes(result: MatchResult) -> dict:
    return {key: len(bucket) for key, bucket in result.buckets.items()}


def _zero_counts() -> dict:
    return dict.fromkeys(WATCH_COUNT_KEYS, 0)


def test_start_date_is_the_pre_registered_constant():
    assert EXPR_WATCH_START == dt.date(2026, 10, 16)
    assert WATCH_COUNT_KEYS == ("no_source", "unknown_strategy", "no_r",
                                "manual_close", "no_entry_date")


def test_every_registry_row_gets_a_bucket_even_when_empty():
    result = match_live_rows([], _registry())
    assert set(result.buckets) == {row_key(e) for e in _registry()}
    assert all(bucket == [] for bucket in result.buckets.values())
    assert result.counts == _zero_counts()


def test_row_key_reads_source_strategy_horizon():
    assert row_key(_reg("confluence", "ALL", "4w")) == CONF_4W
    assert row_key(_reg("strategy", "Fibonacci", None)) == FIB_POOLED


def test_confluence_trade_feeds_its_horizon_row_and_the_pooled_row():
    result = match_live_rows([_trade()], _registry())
    sizes = _sizes(result)
    assert sizes[CONF_4W] == 1
    assert sizes[CONF_POOLED] == 1
    assert sizes[("confluence", "ALL", "2w")] == 0
    assert result.counts == _zero_counts()


def test_confluence_is_matched_on_source_not_on_strategy_name():
    # builders.py:687 path: a confluence plan carries its primary strategy.
    result = match_live_rows([_trade(strategy="Fibonacci")], _registry())
    sizes = _sizes(result)
    assert sizes[CONF_4W] == 1 and sizes[CONF_POOLED] == 1
    assert sizes[FIB_POOLED] == 0


def test_strategy_trade_feeds_the_pooled_row_only():
    result = match_live_rows([_trade(source="strategy", strategy="Fibonacci")], _registry())
    sizes = _sizes(result)
    assert sizes[FIB_POOLED] == 1
    assert sizes[CONF_4W] == 0 and sizes[CONF_POOLED] == 0


def test_one_week_confluence_trade_feeds_pooled_only_and_is_not_unmatched():
    result = match_live_rows([_trade(horizon_key="1w")], _registry())
    sizes = _sizes(result)
    assert sizes[CONF_POOLED] == 1
    assert sum(sizes.values()) == 1
    assert result.counts == _zero_counts()


def test_trade_without_horizon_key_is_appended_once():
    result = match_live_rows([_trade(horizon_key=None)], _registry())
    assert _sizes(result)[CONF_POOLED] == 1
    assert sum(_sizes(result).values()) == 1


def test_trade_entered_before_start_is_excluded_and_not_counted():
    # 21:00 UTC on 15 Oct is 23:00 Berlin on 15 Oct: before the start.
    result = match_live_rows([_trade(opened_at="2026-10-15T21:00:00+00:00")], _registry())
    assert sum(_sizes(result).values()) == 0
    assert result.counts == _zero_counts()


def test_start_boundary_is_the_berlin_date_not_the_utc_date():
    # 22:30 UTC on 15 Oct is 00:30 Berlin on 16 Oct: on the start date.
    result = match_live_rows([_trade(opened_at="2026-10-15T22:30:00+00:00")], _registry())
    assert _sizes(result)[CONF_POOLED] == 1
    assert result.buckets[CONF_POOLED][0].entry_date == "2026-10-16"


def test_cohort_trade_is_excluded():
    result = match_live_rows([_trade(origin="next_session")], _registry())
    assert sum(_sizes(result).values()) == 0
    assert result.counts == _zero_counts()


def test_weak_ledger_trade_is_included():
    result = match_live_rows([_trade(ledger="weak")], _registry())
    assert _sizes(result)[CONF_4W] == 1


def test_open_trade_is_not_in_the_population():
    result = match_live_rows([_trade(status="open", exit_price=None)], _registry())
    assert sum(_sizes(result).values()) == 0
    assert result.counts == _zero_counts()


@pytest.mark.parametrize("over, reason", [
    ({"source": None}, "no_source"),
    ({"source": ""}, "no_source"),
    ({"source": "strategy", "strategy": "Not In Registry"}, "unknown_strategy"),
    ({"source": "mystery"}, "unknown_strategy"),
    ({"exit_price": None}, "no_r"),
    ({"opened_at": None}, "no_entry_date"),
    ({"opened_at": "not a timestamp"}, "no_entry_date"),
])
def test_each_exclusion_is_counted_and_never_bucketed(over, reason):
    result = match_live_rows([_trade(**over)], _registry())
    assert sum(_sizes(result).values()) == 0
    expected = _zero_counts()
    expected[reason] = 1
    assert result.counts == expected


def test_missing_source_key_counts_as_no_source():
    trade = _trade()
    del trade["source"]
    result = match_live_rows([trade], _registry())
    assert result.counts["no_source"] == 1


def test_manual_close_is_included_and_counted():
    result = match_live_rows([_trade(status="closed", exit_price=101.0)], _registry())
    assert _sizes(result)[CONF_4W] == 1
    assert result.counts["manual_close"] == 1


def test_live_trade_carries_berlin_date_r_and_status():
    result = match_live_rows([_trade(status="loss", exit_price=96.0)], _registry())
    live = result.buckets[CONF_4W][0]
    assert isinstance(live, LiveTrade)
    assert live == LiveTrade("2026-10-19", -0.8, "loss")


def test_berlin_entry_date_handles_naive_z_and_garbage():
    assert berlin_entry_date({"opened_at": "2026-10-15T23:30:00"}) == "2026-10-16"  # naive = UTC
    assert berlin_entry_date({"opened_at": "2026-10-19T10:00:00Z"}) == "2026-10-19"
    assert berlin_entry_date({"opened_at": ""}) is None
    assert berlin_entry_date({}) is None
    assert berlin_entry_date({"opened_at": "garbage"}) is None


def test_calibration_does_not_import_the_retrospective():
    # retrospective.py:29 imports calibration; the reverse would be a cycle.
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(calibration))
    imported = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imported += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                 for alias in node.names]
    assert not any("retrospective" in name for name in imported)
