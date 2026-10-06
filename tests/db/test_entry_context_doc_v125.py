"""v125: the nine new snapshot keys ride in trades.doc JSONB -- add, no revision."""
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.db.schema import trades
from swingbot.core.edge.context import FEATURE_KEYS
from swingbot.core.tracking.performance import _db_record, _json_record

V125 = {"target_capped": True, "stop_clamped": False, "zone_dist_atr": 0.473761, "room_atr": 1.257851,
        "range_pos": -1.787727, "leg_phase": "broken", "zone_state": "tested", "zone_touches": 5,
        "zone_departure_atr": 0.473761}


def _trade(trade_id, context):
    return {"id": trade_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
            "direction": "bullish", "status": "open", "opened_at": "2026-10-02T15:00:00+00:00",
            "entry_context": context}


def test_no_v125_key_is_a_promoted_column():
    assert not set(V125) & set(trades.c.keys())
    assert "entry_context" not in trades.c


def test_v125_keys_round_trip_with_their_types(db_conn):
    context = {key: None for key in FEATURE_KEYS} | V125
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V125-T1", context)), conn=db_conn)
    back = _json_record(repository.get("V125-T1", conn=db_conn))["entry_context"]
    assert back == context
    assert type(back["zone_touches"]) is int and back["leg_phase"] == "broken"
    assert back["target_capped"] is True and back["stop_clamped"] is False


def test_unknown_provenance_round_trips_as_none(db_conn):
    context = {key: None for key in FEATURE_KEYS} | V125 | {"target_capped": None, "stop_clamped": None}
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V125-T2", context)), conn=db_conn)
    back = _json_record(repository.get("V125-T2", conn=db_conn))["entry_context"]
    assert back["target_capped"] is None and back["stop_clamped"] is None


def test_a_pre_v125_record_reads_every_new_key_as_none(db_conn):
    old = {"vol_ratio_20": 1.2, "structure_state": "up"}
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V125-T0", old)), conn=db_conn)
    back = _json_record(repository.get("V125-T0", conn=db_conn))["entry_context"]
    assert all(back.get(key) is None for key in V125)
    assert back == old                              # nothing upcast on read
