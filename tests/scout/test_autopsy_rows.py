"""autopsy.rows: the VM export CSV as typed BookRows, with modelled net R."""
import csv
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))

from autopsy import rows  # noqa: E402
from autopsy.rows import BookRow, RejectionCount  # noqa: E402
from swingbot import config  # noqa: E402
from tests.scout.test_export_script import EXPECTED_COLUMNS, SCRIPT, select_aliases  # noqa: E402


@pytest.fixture(autouse=True)
def _frictions(monkeypatch):
    """Pin the friction model so the arithmetic below is exact."""
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)


def _write_csv(tmp_path: Path, records: list[dict], columns=EXPECTED_COLUMNS) -> Path:
    path = tmp_path / "rows.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns))
        writer.writeheader()
        for record in records:
            writer.writerow({c: record.get(c, "") for c in columns})
    return path


TRADE = {
    "row_kind": "trade", "trade_id": "T1", "plan_id": "P1", "ticker": "AAA",
    "strategy": "RSI", "horizon": "2w", "direction": "bullish",
    "plan_created_at": "2026-03-02 00:00:00+00",
    "plan_first_status_at": "2026-03-02T14:35:10.123456+00:00",
    "plan_status": "CLOSED", "plan_status_reason": "tp1_runner_tp2",
    "entry_type": "stop_entry", "expiry_bars": "3", "valid_session": "2026-03-03",
    "planned_entry": "99.5", "opened_at": "2026-03-03 15:00:00+00", "entry": "100",
    "stop_loss": "95", "take_profit": "110", "target2": "115",
    "closed_at": "2026-03-10 01:30:00+00", "exit_price": "110",
    "close_reason": "auto (price monitor)", "last_leg_reason": "", "outcome": "win",
    "r_realized": "2.0", "mfe_r": "2.5", "mae_r": "-0.4", "exit_efficiency": "0.8",
    "holding_days": "6", "stop_width_atr": "1.5", "atr_pct": "2.4",
    "regime2_state": "bull_quiet", "session_bucket": "open",
    "days_to_earnings": "12", "rs_percentile": "81",
}

PLAN = {
    "row_kind": "plan", "plan_id": "P2", "ticker": "BBB", "strategy": "RSI",
    "horizon": "1m", "direction": "bullish",
    "plan_created_at": "2026-03-04 00:00:00+00", "plan_status": "CANCELLED",
    "plan_status_reason": "expired", "entry_type": "stop_entry", "expiry_bars": "2",
    "planned_entry": "50.25",
}


def test_export_columns_match_the_script():
    source = SCRIPT.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert rows.EXPORT_COLUMNS == EXPECTED_COLUMNS
    assert tuple(select_aliases(source)[0]) == rows.EXPORT_COLUMNS


def test_every_book_row_field_has_a_default():
    a, b = BookRow(), BookRow()
    assert a.ticker is None and a.gross_r is None and a.close_reason == ""
    assert a.bars == {} and a.bars is not b.bars


def test_a_closed_trade_row_parses_into_eastern_dates(tmp_path):
    [row] = rows.load_rows(_write_csv(tmp_path, [TRADE]))
    assert (row.row_kind, row.trade_id, row.plan_id, row.ticker) == ("trade", "T1", "P1", "AAA")
    assert (row.strategy, row.horizon, row.direction) == ("RSI", "2w", "bullish")
    assert row.plan_date == "2026-03-02"
    assert row.plan_hour == 9                    # 14:35 UTC = 09:35 EST
    assert row.entry_date == "2026-03-03"
    assert row.exit_date == "2026-03-09"         # 01:30 UTC on the 10th = 21:30 EDT on the 9th


def test_a_closed_trade_row_parses_prices_and_journal_metrics(tmp_path):
    [row] = rows.load_rows(_write_csv(tmp_path, [TRADE]))
    assert row.expiry_bars == 3 and row.planned_entry == 99.5
    assert (row.entry, row.stop, row.take_profit, row.target2) == (100.0, 95.0, 110.0, 115.0)
    assert row.exit_price == 110.0 and row.gross_r == 2.0
    assert (row.mfe_r, row.mae_r, row.exit_efficiency) == (2.5, -0.4, 0.8)
    assert (row.holding_days, row.stop_width_atr, row.atr_pct) == (6.0, 1.5, 2.4)
    assert (row.days_to_earnings, row.rs_percentile) == (12.0, 81.0)
    assert (row.regime2_state, row.session_bucket) == ("bull_quiet", "open")
    assert row.close_reason == "auto (price monitor)" and row.outcome == "win"
    assert row.bars == {}


def test_the_last_leg_reason_wins_and_is_lower_cased(tmp_path):
    record = dict(TRADE, close_reason="closed", last_leg_reason="TP1_runner_TP2")
    [row] = rows.load_rows(_write_csv(tmp_path, [record]))
    assert row.close_reason == "tp1_runner_tp2"


def test_a_missing_close_reason_is_an_empty_string(tmp_path):
    record = dict(TRADE, close_reason="", last_leg_reason="")
    [row] = rows.load_rows(_write_csv(tmp_path, [record]))
    assert row.close_reason == ""


def test_a_date_only_created_at_gives_no_alert_hour(tmp_path):
    record = dict(TRADE, plan_first_status_at="")
    [row] = rows.load_rows(_write_csv(tmp_path, [record]))
    assert row.plan_hour is None


def test_postgres_and_date_only_timestamps_parse():
    assert rows._eastern_date("2026-03-10 01:30:00+00") == "2026-03-09"
    assert rows._eastern_date("2026-03-02") == "2026-03-01"   # naive = UTC midnight
    assert rows._eastern_date("") is None


def test_a_timed_created_at_is_the_alert_hour_fallback(tmp_path):
    record = dict(TRADE, plan_first_status_at="", plan_created_at="2026-03-02 15:10:00+00")
    [row] = rows.load_rows(_write_csv(tmp_path, [record]))
    assert row.plan_hour == 10


def test_modelled_net_r_subtracts_slippage_and_commission():
    row = BookRow(direction="bullish", entry=100.0, stop=95.0, exit_price=110.0, gross_r=2.0)
    # slippage 0.05 + 0.055 = 0.105 over risk 5 = 0.021 R; commission 2 x 1 / 100 = 0.02 R
    assert rows.modelled_net_r(row) == pytest.approx(2.0 - 0.021 - 0.02)


def test_modelled_net_r_of_a_short():
    row = BookRow(direction="bearish", entry=50.0, stop=52.0, exit_price=46.0, gross_r=2.0)
    # slippage 0.025 + 0.023 = 0.048 over risk 2 = 0.024 R
    assert rows.modelled_net_r(row) == pytest.approx(2.0 - 0.024 - 0.02)


def test_modelled_net_r_without_an_exit_price_charges_the_entry_twice():
    row = BookRow(direction="bullish", entry=100.0, stop=95.0, gross_r=-1.0)
    assert rows.modelled_net_r(row) == pytest.approx(-1.0 - 0.1 / 5.0 - 0.02)


@pytest.mark.parametrize("kwargs", [
    {"entry": 100.0, "stop": None, "gross_r": 1.0},
    {"entry": None, "stop": 95.0, "gross_r": 1.0},
    {"entry": 100.0, "stop": 95.0, "gross_r": None},
    {"entry": 100.0, "stop": 100.0, "gross_r": 1.0},
    {"entry": 100.0, "stop": 99.95, "gross_r": 1.0},   # risk below 0.1% of entry
])
def test_modelled_net_r_is_none_without_a_usable_risk(kwargs):
    assert rows.modelled_net_r(BookRow(direction="bullish", **kwargs)) is None


def test_load_rows_fills_net_r_and_splits_the_kinds(tmp_path):
    loaded = rows.load_rows(_write_csv(tmp_path, [TRADE, PLAN]))
    [trade] = rows.closed_trades(loaded)
    [plan] = rows.plan_rows(loaded)
    assert trade.net_r == pytest.approx(2.0 - 0.021 - 0.02)
    assert plan.plan_id == "P2" and plan.plan_status_reason == "expired"
    assert plan.gross_r is None and plan.net_r is None and plan.entry_date is None
    assert plan.plan_date == "2026-03-04" and plan.expiry_bars == 2


def test_a_trade_without_realised_r_is_not_a_closed_trade(tmp_path):
    loaded = rows.load_rows(_write_csv(tmp_path, [dict(TRADE, r_realized="")]))
    assert rows.closed_trades(loaded) == []


def test_a_wrong_header_is_refused_naming_the_gap(tmp_path):
    path = _write_csv(tmp_path, [TRADE], columns=EXPECTED_COLUMNS[:-1])
    with pytest.raises(ValueError, match="rs_percentile"):
        rows.load_rows(path)


def test_rejections_load_as_counts(tmp_path):
    path = tmp_path / "rejections.csv"
    path.write_bytes(b"date,reason,count\n2026-03-04,risk_cap,2\n2026-03-05,no_qualifying_target,1\n")
    assert rows.load_rejections(path) == [
        RejectionCount("2026-03-04", "risk_cap", 2),
        RejectionCount("2026-03-05", "no_qualifying_target", 1),
    ]


def test_a_wrong_rejections_header_is_refused(tmp_path):
    path = tmp_path / "rejections.csv"
    path.write_bytes(b"day,reason,n\n2026-03-04,risk_cap,2\n")
    with pytest.raises(ValueError, match="date,reason,count"):
        rows.load_rejections(path)


def test_explicit_friction_snapshot_controls_model_after_config_changes(monkeypatch, tmp_path):
    settings = rows.friction_settings()
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 100.0)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 50.0)
    loaded = rows.load_rows(_write_csv(tmp_path, [TRADE]), frictions=settings)
    assert loaded[0].net_r == pytest.approx(2.0 - 0.021 - 0.02)


@pytest.mark.parametrize("value", ["inf", "-inf", "Infinity", "-Infinity", "1e999", "nan"])
def test_nonfinite_csv_numbers_are_missing_not_trade_or_bucket_inputs(tmp_path, value):
    record = dict(TRADE, r_realized=value, planned_entry=value, atr_pct=value, expiry_bars=value)
    [row] = rows.load_rows(_write_csv(tmp_path, [record]))
    assert row.gross_r is None
    assert row.planned_entry is None
    assert row.atr_pct is None
    assert row.expiry_bars is None
    assert rows.closed_trades([row]) == []
