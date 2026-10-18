import pandas as pd

from scripts.backtest.emit_cohort_registry import aggregate_cells, _normalize_live_trades


def _regimes():
    index = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
    return pd.Series(["bull_quiet", "bear_volatile", "bear_volatile"], index=index)


def test_aggregate_buckets_by_direction_and_regime():
    trades = [
        {"created_at": "2026-01-02", "direction": "bullish", "r_realized": 1.0},
        {"created_at": "2026-01-05", "direction": "bearish", "r_realized": -1.0},
        {"created_at": "2026-01-06", "direction": "bearish", "r_realized": -1.0},
    ]

    cells = aggregate_cells(trades, _regimes())

    assert cells["bullish|bull_quiet"]["n"] == 1
    assert cells["bearish|bear_volatile"]["n"] == 2
    assert cells["bearish|bear_volatile"]["win_rate"] == 0.0
    assert cells["bearish|bear_volatile"]["expectancy_r"] == -1.0


def test_trade_with_no_regime_for_its_date_is_dropped_not_guessed():
    trades = [{"created_at": "2019-01-01", "direction": "bullish", "r_realized": 1.0}]
    assert aggregate_cells(trades, _regimes()) == {}


def test_trade_missing_r_realized_is_dropped():
    trades = [{"created_at": "2026-01-02", "direction": "bullish", "r_realized": None}]
    assert aggregate_cells(trades, _regimes()) == {}


# ── Final-review Fix 2: _normalize_live_trades adapts real trades.json
# records (performance.py's log_trade shape) into the {created_at,
# direction, r_realized} shape aggregate_cells() expects. Earlier code
# guessed at "CLOSED" status / "created_at" / a top-level "r_realized" field
# -- none of which real trade records carry -- so the live side could never
# count anything.

def _raw_win_trade(**overrides):
    trade = {
        "id": "trade-1", "source": "confluence", "status": "win",
        "opened_at": "2026-01-02T14:30:00+00:00", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "exit_price": 110.0,
        "legs": [],
    }
    trade.update(overrides)
    return trade


def test_normalize_live_trades_uses_opened_at_not_created_at():
    trade = _raw_win_trade(opened_at="2026-01-02T14:30:00+00:00")  # 09:30 ET, same calendar day
    assert "created_at" not in trade  # sanity: real records don't have this key
    [normalized] = _normalize_live_trades([trade])
    assert normalized["created_at"] == "2026-01-02"


def test_normalize_live_trades_converts_opened_at_to_the_et_calendar_day():
    # 2026-01-06 03:00 UTC is still 2026-01-05 22:00 ET -- opened_at's UTC
    # calendar date and its ET trading date disagree across this boundary.
    # A naive string slice would silently mis-bucket the trade one day late.
    trade = _raw_win_trade(opened_at="2026-01-06T03:00:00+00:00")
    [normalized] = _normalize_live_trades([trade])
    assert normalized["created_at"] == "2026-01-05"


def test_normalize_live_trades_computes_r_realized_via_shared_r_multiple():
    trade = _raw_win_trade(entry=100.0, stop_loss=95.0, exit_price=110.0, direction="bullish")
    [normalized] = _normalize_live_trades([trade])
    # (110 - 100) / (100 - 95) == 2.0R -- same shared metrics.r_multiple()
    # performance.py/journal.py use, not a nonexistent top-level field.
    assert normalized["r_realized"] == 2.0


def test_normalize_live_trades_accepts_win_loss_and_manual_closed_statuses():
    trades = [
        _raw_win_trade(status="win"),
        _raw_win_trade(status="loss", exit_price=90.0),
        _raw_win_trade(status="closed", exit_price=102.0),
    ]
    normalized = _normalize_live_trades(trades)
    assert len(normalized) == 3


def test_normalize_live_trades_drops_open_trades():
    trades = [_raw_win_trade(status="open", exit_price=None)]
    assert _normalize_live_trades(trades) == []


def test_normalize_live_trades_rejects_the_old_uppercase_closed_guess():
    # There is no "CLOSED" status in real trade records -- confirms the
    # generator no longer relies on a value this codebase never writes.
    trades = [_raw_win_trade(status="CLOSED")]
    assert _normalize_live_trades(trades) == []


def test_normalize_live_trades_end_to_end_through_aggregate_cells():
    trades = [
        _raw_win_trade(status="win", opened_at="2026-01-02T14:30:00+00:00",
                        direction="bullish", entry=100.0, stop_loss=95.0, exit_price=110.0),
        _raw_win_trade(status="open", opened_at="2026-01-05T14:30:00+00:00",
                        direction="bearish", exit_price=None),  # excluded: not closed
    ]
    normalized = _normalize_live_trades(trades)
    cells = aggregate_cells(normalized, _regimes())
    assert cells["bullish|bull_quiet"]["n"] == 1
    assert cells["bullish|bull_quiet"]["expectancy_r"] == 2.0
    assert "bearish|bear_volatile" not in cells
