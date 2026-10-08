"""v130: major-tier snapshot keys ride in trades.doc JSONB -- add, no revision."""
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.db.schema import trades
from swingbot.core.tracking.performance import _db_record, _json_record

MAJOR = {"structure_state_major": "down", "structure_aligned_major": False, "major_sh_atr": -2.294486,
         "major_sl_atr": 9.001443, "struct_event_last": "choch_against", "struct_event_bars_ago": 2,
         "last_sl_reaction_atr": 11.861716, "last_sh_reaction_atr": None}


def _trade(trade_id, context):
    return {"id": trade_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
            "direction": "bullish", "status": "open", "opened_at": "2026-10-03T15:00:00+00:00",
            "entry_context": context}


def test_entry_context_is_still_a_doc_payload_not_a_column():
    assert "entry_context" not in trades.c


def test_major_keys_round_trip_with_their_types(db_conn):
    context = {"vol_ratio_20": 1.2, "structure_state": "up"} | MAJOR
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V130-T1", context)), conn=db_conn)
    back = _json_record(repository.get("V130-T1", conn=db_conn))["entry_context"]
    assert back == context
    assert type(back["struct_event_bars_ago"]) is int
    assert back["structure_aligned_major"] is False and back["last_sh_reaction_atr"] is None
    assert back["struct_event_last"] == "choch_against"


def test_a_pre_v130_record_reads_every_major_key_as_none(db_conn):
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V130-T0", {"structure_state": "up"})), conn=db_conn)
    back = _json_record(repository.get("V130-T0", conn=db_conn))["entry_context"]
    assert all(back.get(key) is None for key in MAJOR)
    assert back == {"structure_state": "up"}
