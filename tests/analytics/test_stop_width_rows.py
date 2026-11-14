"""v226: stop-width rows wrap the v146 attribution rows without widening them,
and the two loaders reuse the v146 row builders."""
from __future__ import annotations

import math

import pytest

from swingbot.core.analytics import expectancy_attribution as ea
from tests.analytics.test_expectancy_attribution_report import (
    StubSource, _replay_row, _trade, _write_jsonl)

CONTEXT = {"regime2_state": "bull_quiet", "rs_pctile": 55.0,
           "stop_atr": 0.4, "stop_pct": 2.0, "stop_clamped": True}


@pytest.mark.parametrize("value, expected", [
    (0.42, 0.42), (3, 3.0), (True, None), (False, None), ("1.2", None), (None, None),
    (0, None), (0.0, None), (-0.5, None), (math.nan, None), (math.inf, None),
    (-math.inf, None), ([1.0], None)])
def test_positive_number_accepts_only_finite_positive_numbers(value, expected):
    assert ea._positive_number(value) == expected


def test_a_train_stop_width_row_extends_the_attribution_row(tmp_path):
    path = _write_jsonl(tmp_path / "train.jsonl", [_replay_row(entry_context=dict(CONTEXT))])
    source = StubSource(["2024-02-01", "2024-05-02"])
    [row] = ea.load_stop_width_train_rows(path, source=source)
    [base] = ea.load_train_rows(path, source=source)
    assert tuple(row) == ea.ROW_KEYS + ea.STOP_WIDTH_KEYS
    assert {key: row[key] for key in ea.ROW_KEYS} == base
    assert row["stop_atr"] == 0.4 and row["stop_clamped"] is True
    assert row["atr_pct"] == pytest.approx(5.0)              # stop_pct / stop_atr


def test_the_train_loader_skips_untriggered_rows_like_the_v146_loader(tmp_path):
    path = _write_jsonl(tmp_path / "train.jsonl", [
        _replay_row(entry_context=dict(CONTEXT)),
        _replay_row(outcome="not_triggered", legs=[], r_total=0.0, entry_price=None)])
    assert len(ea.load_stop_width_train_rows(path, source=StubSource([]))) == 1


def test_the_train_loader_defaults_to_the_csv_source(tmp_path, monkeypatch):
    made = []

    class FakeCsv(StubSource):
        def __init__(self):
            super().__init__([])
            made.append(self)

    monkeypatch.setattr(ea.earnings_calendar, "CsvSource", FakeCsv)
    rows = ea.load_stop_width_train_rows(_write_jsonl(tmp_path / "t.jsonl", [_replay_row()]))
    assert len(made) == 1 and len(rows) == 1


@pytest.mark.parametrize("context", [
    None, "not a dict", {}, {"stop_atr": None}, {"stop_atr": "0.4"}, {"stop_atr": 0},
    {"stop_atr": -0.3}, {"stop_atr": True}, {"stop_atr": math.nan}],
    ids=["absent", "non-dict", "empty", "none", "string", "zero", "negative", "bool", "nan"])
def test_an_unusable_stop_atr_is_none_and_so_is_atr_pct(context):
    row = ea.stop_width_row({"r": 1.0}, {"entry_context": context})
    assert row["stop_atr"] is None and row["atr_pct"] is None


def test_atr_pct_needs_a_positive_stop_pct():
    assert ea.stop_width_row({}, {"entry_context": {"stop_atr": 0.5}})["atr_pct"] is None
    assert ea.stop_width_row({}, {"entry_context": {"stop_atr": 0.5, "stop_pct": 0}})["atr_pct"] is None


@pytest.mark.parametrize("flag, expected", [(True, True), (False, False), (None, None),
                                            ("yes", None), (1, None)])
def test_stop_clamped_keeps_only_a_real_bool(flag, expected):
    row = ea.stop_width_row({}, {"entry_context": {"stop_clamped": flag}})
    assert row["stop_clamped"] is expected


def test_stop_width_row_never_mutates_the_base_row():
    base = {"r": 1.0, "week": "2021-03-01"}
    row = ea.stop_width_row(base, {"entry_context": dict(CONTEXT)}, live=True)
    assert base == {"r": 1.0, "week": "2021-03-01"} and row is not base


def test_a_live_stop_width_row_adds_timestamps_and_the_family(monkeypatch):
    from swingbot.core.tracking.performance import primary_strategy_label
    trade = _trade(entry_context=dict(CONTEXT), closed_at="2026-03-11T19:00:00+00:00")
    seen = {}

    class FakeLog:
        def get_trades(self, **kwargs):
            seen.update(kwargs)
            return [trade, _trade(status="open", exit_price=None)]

    monkeypatch.setattr("swingbot.core.tracking.performance.TradeLog", FakeLog)
    [row] = ea.load_stop_width_live_rows()
    assert seen == {"status": None, "limit": None, "ledger": None}
    assert tuple(row) == ea.ROW_KEYS + ea.STOP_WIDTH_KEYS + ea.STOP_WIDTH_LIVE_KEYS
    assert {key: row[key] for key in ea.ROW_KEYS} == ea.live_row(trade)
    assert row["opened_at"] == "2026-03-11T14:30:00+00:00"
    assert row["closed_at"] == "2026-03-11T19:00:00+00:00"
    label = primary_strategy_label(trade)
    assert row["strategy"] == (None if label == "--" else label)
    assert row["stop_atr"] == 0.4


def test_live_keys_are_none_when_the_trade_lacks_them():
    row = ea.stop_width_row({}, {"entry_context": {}}, live=True)
    assert (row["opened_at"], row["closed_at"], row["strategy"]) == (None, None, None)


def test_the_v146_row_contracts_are_unchanged():
    assert tuple(ea.live_row(_trade())) == ea.ROW_KEYS
    assert "stop_atr" not in ea.ROW_KEYS and "strategy" not in ea.ROW_KEYS
    assert ea.STOP_WIDTH_KEYS == ("stop_atr", "atr_pct", "stop_clamped")
    assert ea.STOP_WIDTH_LIVE_KEYS == ("opened_at", "closed_at", "strategy")
