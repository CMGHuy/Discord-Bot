"""Pin the Dashboard equity candle and snapshot contracts for v208."""
from dataclasses import fields
from datetime import datetime, timezone
from decimal import Decimal

from swingbot.commands.scanning import equity_recorder
from swingbot.core.tracking import equity
from swingbot.core.tracking.equity_candles import mtm_candles

UTC = timezone.utc


def _sample(i, at, value, *, source="live"):
    return {"id": i, "at": at, "equity": value, "kind": "point", "source": source,
            "skipped_n": 0, "realized_balance": 10000.0, "unrealized_pnl": value - 10000.0,
            "open_n": 1}


ROWS = [_sample(1, datetime(2026, 10, 14, 13, 35, tzinfo=UTC), 10000.0),
        _sample(2, datetime(2026, 10, 14, 15, 0, tzinfo=UTC), 10050.0),
        _sample(3, datetime(2026, 10, 14, 19, 55, tzinfo=UTC), 10020.0),
        _sample(4, datetime(2026, 10, 15, 13, 35, tzinfo=UTC), 10020.0),
        _sample(5, datetime(2026, 10, 15, 19, 55, tzinfo=UTC), 9990.0)]


def test_existing_snapshot_fields_are_unchanged_and_open_notional_is_appended():
    assert [f.name for f in fields(equity.EquitySnapshot)] == [
        "realized_balance", "unrealized_pnl", "equity", "open_n", "skipped_n", "open_notional"]


def test_daily_candles_ignore_the_new_columns():
    plain = mtm_candles([dict(r) for r in ROWS], "1D")
    tagged = mtm_candles([{**r, "open_notional": 2040.0, "open_notional_approx": True}
                          for r in ROWS], "1D")
    assert tagged == plain
    assert [(c["t"], float(c["c"])) for c in plain] == [("2026-10-14", 10020.0),
                                                        ("2026-10-15", 9990.0)]


def test_the_recorder_row_keeps_every_v172_key():
    snap = equity.EquitySnapshot(realized_balance=Decimal("1"), unrealized_pnl=Decimal("0"),
                                 equity=Decimal("1"), open_n=0, skipped_n=0)
    row = equity_recorder._row(snap, datetime(2026, 10, 14, 15, 0, tzinfo=UTC))
    assert set(row) == {"at", "realized_balance", "unrealized_pnl", "equity", "open_n",
                        "skipped_n", "source", "kind", "backfill_run",
                        "open_notional", "open_notional_approx"}
