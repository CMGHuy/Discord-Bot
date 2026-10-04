"""v121: entry_context is a doc JSONB payload, so new snapshot keys need no revision."""
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.db.schema import trades
from swingbot.core.edge.context import FEATURE_KEYS
from swingbot.core.tracking.performance import _db_record, _json_record

NEW = {"structure_state": "up", "structure_aligned": True, "last_pivot_held": True, "hh_failed": False,
       "swing_high_atr": 1.25, "swing_low_atr": 0.75, "vol_trend_10_50": 0.8, "range_trend_10_50": 0.9,
       "progress_atr_10": -0.5, "absorption_bar": False, "absorption_count_10": 2, "pullback_vol_ratio": 0.5,
       "pullback_depth_frac": 0.4, "pullback_bars_ratio": 0.3, "impulse_atr_per_bar": 1.1, "impulse_range_decay": 0.8}


def _trade(trade_id, context):
    return {"id": trade_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
            "direction": "bullish", "status": "open", "opened_at": "2026-10-02T15:00:00+00:00",
            "entry_context": context}


def test_entry_context_is_a_doc_payload_not_a_column():
    assert "entry_context" not in trades.c


def test_new_keys_round_trip_with_their_types(db_conn):
    context = {key: None for key in FEATURE_KEYS} | NEW
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V121-T1", context)), conn=db_conn)
    back = _json_record(repository.get("V121-T1", conn=db_conn))["entry_context"]
    assert back == context
    assert type(back["absorption_count_10"]) is int
    assert back["structure_aligned"] is True and back["pullback_vol_ratio"] == 0.5


def test_an_old_record_reads_every_new_key_as_none(db_conn):
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V121-T0", {"vol_ratio_20": 1.2})), conn=db_conn)
    back = _json_record(repository.get("V121-T0", conn=db_conn))["entry_context"]
    assert all(back.get(key) is None for key in NEW)
    assert back == {"vol_ratio_20": 1.2}       # nothing upcast on read
