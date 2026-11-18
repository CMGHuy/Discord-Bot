"""V229-5: reading the export by column name, the population funnel, and one
assembled pair in the shared PAIR shape."""
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from deferred_entry import arms, pairs  # noqa: E402
from swingbot import config  # noqa: E402
from tests.scripts.v229_fixtures import et, five_min  # noqa: E402

DAYS = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"]
ARCHIVE_END = et("2026-11-10 15:55").isoformat()
NO_EARNINGS = lambda ticker: []  # noqa: E731 -- never touch the network in tests
PAIR_KEYS = {"trade_id", "ticker", "direction", "opened_at", "entry_date", "iso_week", "bucket",
             "trade", "arms", "live", "tradeability", "coverage", "rule_hash", "frictions"}


@pytest.fixture(autouse=True)
def _frictions(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)


def _row(**over):
    row = {"row_kind": "trade", "trade_id": "t-1", "plan_id": "p-1", "ticker": "AAPL",
           "strategy": "S/R Confluence", "horizon": "4w", "direction": "bullish",
           "plan_created_at": "2026-11-02 14:00:00+00", "entry_type": "market",
           "expiry_bars": "5", "opened_at": "2026-11-03 15:02:00+00",   # 10:02 ET
           "entry": "100.0", "stop_loss": "98.0", "take_profit": "104.0",
           "closed_at": "2026-11-03 16:30:00+00", "close_reason": "stop",
           "last_leg_reason": "loss", "outcome": "loss", "r_realized": "-1.02",
           "session_bucket": "open"}
    row.update(over)
    return row


def _classify(row, frame=None, archive_end=ARCHIVE_END):
    return pairs.classify(row, five_min(DAYS) if frame is None else frame, archive_end=archive_end)


def _write(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_read_export_reads_by_name_and_ignores_extra_columns(tmp_path):
    row = _row(excursion_source="archive")
    fields = list(reversed(list(row)))           # any order, 39th column present
    _write(tmp_path / "rows.csv", [row], fields)
    out = pairs.read_export(tmp_path / "rows.csv")
    assert out[0]["trade_id"] == "t-1" and out[0]["take_profit"] == "104.0"


def test_read_export_names_missing_columns(tmp_path):
    row = _row()
    fields = [f for f in row if f not in ("entry_type", "take_profit")]
    _write(tmp_path / "rows.csv", [{f: row[f] for f in fields}], fields)
    with pytest.raises(ValueError, match="entry_type.*take_profit"):
        pairs.read_export(tmp_path / "rows.csv")


@pytest.mark.parametrize("over, reason", [
    ({"row_kind": "plan"}, "not_trade"),
    ({"entry_type": ""}, "entry_type_unknown"),
    ({"entry_type": "stop_entry"}, "not_market"),
    ({"stop_loss": "101.0"}, "bad_levels"),
    ({"take_profit": "99.0"}, "bad_levels"),
    ({"direction": "sideways"}, "bad_levels"),
    ({"entry": ""}, "bad_levels"),
    ({"opened_at": "2026-11-03 13:00:00+00"}, "outside_session"),   # 08:00 ET
    ({"opened_at": "2026-11-07 15:00:00+00"}, "outside_session"),   # Saturday
    ({"opened_at": ""}, "outside_session"),
    ({"opened_at": "2026-11-03 20:31:00+00"}, "close_bucket"),      # 15:31 ET
    ({}, "eligible"),
    ({"direction": "long"}, "eligible"),
    ({"direction": "bearish", "stop_loss": "102.0", "take_profit": "96.0"}, "eligible"),
])
def test_static_funnel(over, reason):
    assert _classify(_row(**over)) == reason


def test_pending_until_the_archive_reaches_the_fifth_session():
    assert _classify(_row(), archive_end=et("2026-11-10 12:00").isoformat()) == "pending"
    assert _classify(_row(), archive_end=None) == "pending"
    assert _classify(_row(), archive_end=et("2026-11-10 15:45")) == "eligible"


def test_no_coverage_without_a_file_or_with_a_missing_session():
    assert pairs.classify(_row(), None, archive_end=ARCHIVE_END) == "no_coverage"
    frame = five_min([d for d in DAYS if d != "2026-11-05"])
    assert _classify(_row(), frame) == "no_coverage"
    short = five_min(DAYS)
    assert _classify(_row(), short[short.index < et("2026-11-10 14:00")]) == "no_coverage"


def test_no_deferral_bar_on_a_half_day_or_without_a_1530_bar():
    half = ["2026-11-27", "2026-11-30", "2026-12-01", "2026-12-02", "2026-12-03", "2026-12-04"]
    row = _row(opened_at="2026-11-27 15:02:00+00")                   # 10:02 ET, 13:00 close
    assert pairs.classify(row, five_min(half), archive_end=et("2026-12-04 15:55")) == "no_deferral_bar"
    frame = five_min(DAYS)
    gap = (frame.index >= et("2026-11-03 15:30")) & (frame.index < et("2026-11-03 16:00"))
    assert _classify(_row(), frame[~gap]) == "no_deferral_bar"


def test_every_reason_is_declared():
    assert set(pairs.REASONS) >= {"not_trade", "eligible", "pending", "no_coverage"}
    assert len(set(pairs.REASONS)) == len(pairs.REASONS) == 10


def _pair(row=None, frame=None):
    return pairs.build_pair(row or _row(), frame if frame is not None else five_min(DAYS),
                            rule_hash="0123abcd4567ef89", earnings_lookup=NO_EARNINGS)


def test_build_pair_has_the_pair_shape_and_serialises():
    out = _pair()
    assert set(out) == PAIR_KEYS
    assert json.loads(json.dumps(out)) == out
    assert (out["trade_id"], out["ticker"], out["direction"]) == ("t-1", "AAPL", "bullish")
    assert out["entry_date"] == "2026-11-03" and out["iso_week"] == "2026-W45"
    assert out["opened_at"] == et("2026-11-03 10:02").isoformat()
    assert out["trade"] == {"entry": 100.0, "stop_loss": 98.0, "take_profit": 104.0}
    assert set(out["arms"]) == {"C", "A", "B"} and out["arms"]["A"]["arm"] == "A"
    assert out["live"] == {"reason": "loss", "outcome": "loss", "r_realized": -1.02}
    assert out["rule_hash"] == "0123abcd4567ef89"
    assert out["frictions"] == arms.frictions_stamp()
    assert out["coverage"] == {"bars_from": et("2026-11-03 10:05").isoformat(),
                               "bars_to": et("2026-11-10 15:55").isoformat(),
                               "deferral_bar": et("2026-11-03 15:30").isoformat()}
    assert out["tradeability"]["earnings_after_close"] is False


@pytest.mark.parametrize("opened, bucket", [("2026-11-03 15:02:00+00", "open"),
                                            ("2026-11-03 17:00:00+00", "midday")])
def test_bucket_is_recomputed_from_opened_at(opened, bucket):
    assert _pair(_row(opened_at=opened, session_bucket="close"))["bucket"] == bucket


def test_live_reason_falls_back_to_close_reason_and_blank_r_is_none():
    out = _pair(_row(last_leg_reason="", close_reason="manual", r_realized=""))
    assert out["live"]["reason"] == "manual" and out["live"]["r_realized"] is None


def test_bearish_pair_is_built_for_the_disclosure():
    out = _pair(_row(direction="short", stop_loss="102.0", take_profit="96.0"))
    assert out["direction"] == "bearish"
    assert out["arms"]["A"]["stop"] == pytest.approx(102.0)


def test_build_pair_refuses_a_row_with_bad_levels():
    with pytest.raises(ValueError, match="levels"):
        _pair(_row(stop_loss="101.0"))
