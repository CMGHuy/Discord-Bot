"""v146: the two population loaders, the report shape, the run and the thin
script. No database and no TRAIN replay: live trades, replay rows and the
earnings calendar are all hand-built."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.analytics import expectancy_attribution as ea
from swingbot.core.infra import expectancy_attribution_store as store
from swingbot.core.market.earnings_calendar import AFTER_CLOSE, Report
from swingbot.core.market.strategy_types import HORIZONS
from tests.analytics.test_expectancy_attribution_stats import population

HK = next(iter(HORIZONS))
REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "reports" / "expectancy_attribution.py"


@pytest.fixture(autouse=True)
def cheap_and_costed(monkeypatch):
    monkeypatch.setattr(ea, "N_RESAMPLES", 200)
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 10.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)


class StubSource:
    def __init__(self, dates):
        self._reports = [Report(dt.date.fromisoformat(day), AFTER_CLOSE) for day in dates]

    def reports(self, ticker):
        return list(self._reports)


def _trade(**over):
    trade = {
        "status": "win", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
        "exit_price": 110.0, "legs": [], "opened_at": "2026-03-11T14:30:00+00:00",
        "horizon_key": HK, "confidence_score": 71, "confidence_level": 4,
        "confidence_points": {"MACD momentum": 10},
        "confidence_unevaluated": ["ADX trend strength"],
        "target_sources": ["ema", "vwap", "fib", "pivot", "sma"],
        "risk_features": {"confluence_count": 3, "days_to_earnings": 7,
                          "regime2_state": "bull_quiet"},
        "entry_context": {"regime2_state": "bull_quiet", "rs_pctile": 81.0},
        "risk_reward_ratio": 2.0,
    }
    trade.update(over)
    return trade


def test_live_row_maps_a_closed_trade_onto_the_row_keys():
    row = ea.live_row(_trade())
    assert tuple(row) == ea.ROW_KEYS
    assert row["week"] == "2026-03-09"                      # the Monday of the entry week
    assert row["r_gross"] == pytest.approx(2.0)
    assert row["r"] == pytest.approx((109.89 - 100.1) / (100.1 - 95.0) - 0.02)
    assert row["confluence_count"] == 3                     # not len(target_sources)
    assert (row["earnings_sessions"], row["earnings_status"]) == (7, "known")
    assert (row["rs_pctile"], row["horizon"]) == (81.0, HK)


def test_live_row_before_the_earnings_stamp_reads_unknown():
    row = ea.live_row(_trade(risk_features={}, entry_context={}))
    assert (row["earnings_sessions"], row["earnings_status"]) == (None, "unknown")
    assert row["confluence_count"] is None and row["regime2_state"] is None


def test_live_row_nets_a_scaled_out_trade_leg_by_leg():
    legs = [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0},
            {"fraction": 0.5, "exit_price": 100.0, "r": 0.0}]
    row = ea.live_row(_trade(legs=legs, exit_price=100.0))
    assert row["r_gross"] == pytest.approx(1.0)
    assert row["r"] < row["r_gross"]


def test_live_row_refuses_a_trade_without_r_or_an_entry_week():
    assert ea.live_row(_trade(exit_price=None)) is None
    assert ea.live_row(_trade(opened_at=None)) is None
    assert ea.live_row(_trade(legs=[{"fraction": 1.0, "r": 1.0}])) is None   # no fill to net


def test_live_row_uses_r_multiple_as_is_when_fills_already_carry_frictions(monkeypatch):
    monkeypatch.setattr(ea, "LIVE_FILLS_INCLUDE_FRICTIONS", True)
    row = ea.live_row(_trade())
    assert row["r"] == row["r_gross"] == pytest.approx(2.0)


def test_the_frictions_branch_of_record_is_a_bool():
    assert isinstance(ea.LIVE_FILLS_INCLUDE_FRICTIONS, bool)


def test_load_live_rows_reads_closed_trades_of_every_ledger(monkeypatch):
    seen = {}

    class FakeLog:
        def get_trades(self, **kwargs):
            seen.update(kwargs)
            return [_trade(), _trade(status="open", exit_price=None),
                    _trade(status="loss", exit_price=95.0), _trade(status="closed", exit_price=None)]

    monkeypatch.setattr("swingbot.core.tracking.performance.TradeLog", FakeLog)
    rows = ea.load_live_rows()
    assert seen == {"status": None, "limit": None, "ledger": None}
    assert len(rows) == 2 and rows[1]["r"] < -1.0


def test_train_earnings_statuses():
    source = StubSource(["2024-02-01", "2024-05-02"])
    sessions, status = ea.train_earnings("AAA", dt.date(2024, 4, 25), source)
    assert status == "known" and 0 < sessions <= 10
    assert ea.train_earnings("AAA", dt.date(2024, 6, 3), source) == (None, "none")
    assert ea.train_earnings("AAA", dt.date(2024, 8, 11), source) == (None, "unknown")
    assert ea.train_earnings("AAA", dt.date(2024, 6, 3), source, margin_days=10) == (None, "unknown")
    assert ea.train_earnings("AAA", dt.date(2024, 4, 25), StubSource([])) == (None, "unknown")


def _replay_row(**over):
    row = {
        "ticker": "AAA", "horizon_key": HK, "signal_date": "2024-04-25",
        "direction": "bullish", "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "risk_reward_ratio": 2.0, "outcome": "win", "runner_outcome": None,
        "r_total": 2.0, "entry_price": 100.0,
        "legs": [{"fraction": 1.0, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}],
        "entry_context": {"regime2_state": "bull_quiet", "rs_pctile": 55.0},
        "confluence_count": 4, "confidence_score": 66, "confidence_level": 3,
        "confidence_points": {"MACD momentum": 15}, "confidence_unevaluated": [],
    }
    row.update(over)
    return row


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows) + "\n", encoding="utf-8")
    return path


def test_load_train_rows_nets_the_replay_rows_and_stamps_earnings(tmp_path):
    path = _write_jsonl(tmp_path / "train.jsonl", [
        _replay_row(),
        _replay_row(outcome="not_triggered", legs=[], r_total=0.0, entry_price=None),
        _replay_row(ticker="BBB", signal_date="2024-06-03", entry_price=None)])
    rows = ea.load_train_rows(path, source=StubSource(["2024-02-01", "2024-05-02"]))
    assert len(rows) == 2                                   # the untriggered row is not a trade
    first, second = rows
    assert tuple(first) == ea.ROW_KEYS
    assert first["week"] == "2024-04-22" and first["r_gross"] == 2.0
    assert first["r"] == pytest.approx((109.89 - 100.1) / (100.1 - 95.0) - 0.02)
    assert (first["confluence_count"], first["horizon"], first["rs_pctile"]) == (4, HK, 55.0)
    assert first["earnings_status"] == "known"
    assert second["earnings_status"] == "none"              # falls back to the planned entry


def test_load_train_rows_defaults_to_the_csv_source(tmp_path, monkeypatch):
    made = []

    class FakeCsv(StubSource):
        def __init__(self):
            super().__init__([])
            made.append(self)

    monkeypatch.setattr(ea.earnings_calendar, "CsvSource", FakeCsv)
    rows = ea.load_train_rows(_write_jsonl(tmp_path / "train.jsonl", [_replay_row()]))
    assert len(made) == 1 and rows[0]["earnings_status"] == "unknown"


def test_earnings_provenance_names_the_file_set(tmp_path):
    header = "report_date,timing,report_ts_et\n"
    (tmp_path / "AAA.csv").write_text(header + "2024-02-01,after_close,\n", encoding="utf-8")
    (tmp_path / "BBB.csv").write_text(header + "2025-07-30,before_open,\n", encoding="utf-8")
    first = ea.earnings_provenance(tmp_path)
    assert first["files"] == 2 and first["newest_report_date"] == "2025-07-30"
    assert len(first["sha256"]) == 64 and "sessions_to_reaction" in first["calendar"]
    (tmp_path / "BBB.csv").write_text(header + "2025-10-29,before_open,\n", encoding="utf-8")
    assert ea.earnings_provenance(tmp_path)["sha256"] != first["sha256"]
    missing = ea.earnings_provenance(tmp_path / "absent")
    assert (missing["files"], missing["sha256"], missing["newest_report_date"]) == (0, None, None)


def test_build_report_has_the_contract_shape_and_a_predictive_verdict():
    live, train = population("predictive"), population("predictive", n=240)
    report = ea.build_report(live, train, seed=42, generated_at="2026-10-12T08:00:00+00:00")
    assert list(report) == ["generated_at", "verdict", "verdict_of_record", "looks",
                            "seed", "provenance", "populations"]
    assert report["verdict"] == "PREDICTIVE" and report["seed"] == 42
    assert report["verdict_of_record"] == {"verdict": "PREDICTIVE", "date": "2026-10-12",
                                           "n": 180 + 240}
    assert report["looks"] > 10
    for name in ("live", "train"):
        pop = report["populations"][name]
        assert list(pop) == ["window", "n", "monotonicity", "factors", "buckets",
                             "splits", "notes"]
        assert set(pop["splits"]) == {"direction", "horizon"}
        assert set(pop["splits"]["direction"]) == {"bullish", "bearish"}
        assert pop["window"]["first_week"] == "2024-01-01" and pop["notes"]
        assert all(bucket["thin"] is (bucket["n"] < 30)
                   for grouping in pop["buckets"].values() for bucket in grouping)
        assert any(bucket["q"] is not None for bucket in pop["buckets"]["direction"])
    assert report["populations"]["live"]["n"] == 180       # never pooled with TRAIN's 240
    json.dumps(report)                                      # JSON-serialisable as is


def test_build_report_verdicts_follow_the_populations():
    good, flat = population("predictive"), population("flat")
    assert ea.build_report(flat, good, seed=42)["verdict"] == "WEAK"
    assert ea.build_report(flat, population("inverted"), seed=42)["verdict"] == "NOT PREDICTIVE"
    empty_live = ea.build_report([], good, seed=42)
    assert empty_live["populations"]["live"] is None and empty_live["verdict"] == "WEAK"
    assert empty_live["verdict_of_record"]["n"] == 180


def test_run_writes_the_latest_report_and_load_latest_round_trips(tmp_path, monkeypatch):
    train = _write_jsonl(tmp_path / "train.jsonl", [_replay_row()])
    monkeypatch.setattr(store, "REPORT_PATH", tmp_path / "reports" / "expectancy-attribution.json")
    monkeypatch.setattr(ea, "load_live_rows", lambda: population("flat"))
    monkeypatch.setattr(ea, "load_train_rows", lambda path: population("predictive"))
    monkeypatch.setattr(ea, "earnings_provenance", lambda: {"files": 0})
    written = ea.run(train, seed=7)
    assert written["verdict"] == "WEAK" and written["seed"] == 7
    assert written["provenance"]["train_rows"]["rows"] == 180
    assert len(written["provenance"]["train_rows"]["sha256"]) == 64
    assert written["provenance"]["live_fills_include_frictions"] is ea.LIVE_FILLS_INCLUDE_FRICTIONS
    assert ea.load_latest is store.load_latest
    assert ea.load_latest() == written

    monkeypatch.setattr(ea, "load_live_rows", lambda: population("predictive"))
    dry = ea.run(train, write=False)
    assert dry["verdict"] == "PREDICTIVE" and dry["seed"] == ea.WEEK_BOOTSTRAP_SEED
    assert ea.load_latest()["verdict"] == "WEAK"            # --no-write left the file alone
    later = ea.run(train)
    assert later["verdict"] == "PREDICTIVE"
    assert later["verdict_of_record"]["verdict"] == "WEAK"  # the verdict of record never moves


def _script():
    spec = importlib.util.spec_from_file_location("v146_expectancy_attribution_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_parses_calls_and_prints(monkeypatch, capsys):
    calls = []
    report = ea.build_report([], population("predictive"), seed=42,
                             generated_at="2026-10-12T08:00:00+00:00")

    def fake_run(train_jsonl, *, seed, write):
        calls.append((train_jsonl, seed, write))
        return report

    monkeypatch.setattr(ea, "run", fake_run)
    script = _script()
    assert script.main(["--train-jsonl", "rows.jsonl", "--no-write"]) == 0
    assert script.main(["--train-jsonl", "rows.jsonl", "--seed", "9"]) == 0
    assert calls == [("rows.jsonl", ea.WEEK_BOOTSTRAP_SEED, False), ("rows.jsonl", 9, True)]
    out = capsys.readouterr().out
    assert "Expectancy attribution" in out and "verdict of record: WEAK" in out
    assert "live  no rows" in out and "train n=180" in out
