# tests/scripts/test_volume_context_report.py
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import volume_context_report as vcr  # noqa: E402

from tests.conftest import make_ohlcv  # noqa: E402


@pytest.mark.parametrize("start,end", [("2020-01-01", "2024-01-01"), ("2020-01-01", "2025-06-30"),
                                       ("2019-06-01", "2023-12-31"), ("2023-06-01", "2023-01-01")])
def test_replay_refuses_any_window_outside_train(start, end, monkeypatch, capsys):
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: pytest.fail("computed"))
    assert vcr.main(["--source", "replay", "--start", start, "--end", end]) == 1
    assert "refused" in capsys.readouterr().out


def test_train_window_is_accepted():
    assert vcr.window_refusal("2020-01-01", "2023-12-31") is None


def _row(source, direction, outcome, r, **context):
    return vcr.ReportRow(source=source, direction=direction, outcome=outcome, r_multiple=r, context=context)


def test_categorical_buckets_split_by_source_and_direction():
    rows = [_row("confluence", "bullish", "win", 2.0, structure_state="up"),
            _row("confluence", "bullish", "loss", -1.0, structure_state="up"),
            _row("strategy", "bearish", "loss", -1.0, structure_state="down"),
            _row("confluence", "bullish", "timeout", 0.0)]
    table = {(line["source"], line["direction"], line["bucket"]): line
             for line in vcr.bucket_table(rows, "structure_state", None)}
    up = table[("confluence", "bullish", "up")]
    assert (up["n"], up["win_rate"], up["expectancy_r"]) == (2, 50.0, 0.5)
    assert table[("confluence", "bullish", "None")]["n"] == 1
    assert table[("strategy", "bearish", "down")]["win_rate"] == 0.0


def test_continuous_buckets_use_fixed_edges():
    rows = [_row("confluence", "bullish", "win", 1.0, vol_trend_10_50=v) for v in (0.1, 0.3, 0.5, 0.7, 0.9)]
    edges = vcr.quintile_edges(rows, "vol_trend_10_50")
    assert edges == [0.26, 0.42, 0.58, 0.74]
    assert [vcr.bucket_of(v, edges) for v in (0.1, 0.3, 0.5, 0.7, 0.9, None)] == \
        ["Q1", "Q2", "Q3", "Q4", "Q5", "None"]
    assert vcr.quintile_edges(rows[:4], "vol_trend_10_50") is None


def test_live_rows_read_old_records_without_new_keys():
    trades = [{"status": "win", "source": "strategy", "direction": "bullish", "entry": 100.0,
               "stop_loss": 95.0, "exit_price": 110.0, "entry_context": {"vol_ratio_20": 1.2}},
              {"status": "open", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0},
              {"status": "closed", "direction": "bearish", "entry": 100.0, "stop_loss": 105.0,
               "exit_price": 100.0}]
    rows = vcr.live_rows(trades)
    assert [(r.source, r.outcome) for r in rows] == [("strategy", "win"), ("unknown", "scratch")]
    assert rows[0].r_multiple == pytest.approx(2.0)
    assert vcr.bucket_of(rows[1].context.get("structure_state"), None) == "None"


def test_live_refuses_without_train_edges(tmp_path, capsys):
    assert vcr.main(["--source", "live", "--edges", str(tmp_path / "missing.json")]) == 1
    assert "refused" in capsys.readouterr().out


def test_live_render_carries_the_holdout_warning(tmp_path, monkeypatch, capsys):
    edges = tmp_path / "edges.json"
    edges.write_text('{"window": ["2020-01-01", "2023-12-31"], "edges": {}}', encoding="utf-8")
    monkeypatch.setattr(vcr, "load_live_trades", lambda: [])
    assert vcr.main(["--source", "live", "--edges", str(edges)]) == 0
    out = capsys.readouterr().out
    assert "DESCRIPTIVE ONLY" in out and "holdout" in out and "p=" not in out


def test_strategy_rows_stamp_context_at_the_signal_bar(monkeypatch):
    df = make_ohlcv(np.linspace(100, 130, 120), spread_pct=1.0)
    signal_date = str(df.index[90].date())
    plan = SimpleNamespace(source="strategy", direction="bullish", horizon_key="2w",
                           stop_loss=110.0, tp1=140.0, entry_context={})
    result = SimpleNamespace(outcome="win", r_total=1.5)
    seen = {}

    class FakeEngine:
        strategies = ("RSI",)

        def iter_trades(self, *args):
            yield signal_date, plan, result

    import swingbot.core.backtesting.arms.strategy_engine as strategy_engine
    import swingbot.core.planning.params as params
    monkeypatch.setattr(strategy_engine, "StrategyEngine", FakeEngine)
    monkeypatch.setattr(params, "stamp_entry_context",
                        lambda p, window, asof: (seen.update(last=window.index[-1]),
                                                 setattr(p, "entry_context", {"ok": 1})))
    rows = vcr.strategy_rows("TEST", df, ("2w",), ("2020-01-01", "2023-12-31"), None)
    assert seen["last"] == df.index[90]
    assert rows == [vcr.ReportRow("strategy", "bullish", "win", 1.5, {"ok": 1})]


def test_replay_writes_train_edges(tmp_path, monkeypatch, capsys):
    rows = [_row("confluence", "bullish", "win", 1.0, pullback_vol_ratio=v) for v in (0.2, 0.4, 0.6, 0.8, 1.0)]
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: rows)
    out_path = tmp_path / "edges.json"
    assert vcr.main(["--source", "replay", "--tickers", "AAA", "--edges", str(out_path)]) == 0
    import json
    blob = json.loads(out_path.read_text(encoding="utf-8"))
    assert blob["window"] == ["2020-01-01", "2023-12-31"]
    assert blob["edges"]["pullback_vol_ratio"] == [0.36, 0.52, 0.68, 0.84]


def test_replay_subset_refuses_the_default_edges_path(monkeypatch, capsys):
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: pytest.fail("computed"))
    assert vcr.main(["--source", "replay", "--tickers", "AAA"]) == 1
    assert "refused" in capsys.readouterr().out


def test_live_header_names_the_local_book(tmp_path, monkeypatch, capsys):
    edges = tmp_path / "edges.json"
    edges.write_text('{"window": ["2020-01-01", "2023-12-31"], "edges": {}}', encoding="utf-8")
    monkeypatch.setattr(vcr, "load_live_trades", lambda: [])
    vcr.main(["--source", "live", "--edges", str(edges)])
    assert "local TradeLog book" in capsys.readouterr().out


def test_replay_train_subwindow_refuses_the_default_edges_path(monkeypatch, capsys):
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: pytest.fail("computed"))
    assert vcr.main(["--source", "replay", "--start", "2022-01-01"]) == 1
    assert "refused" in capsys.readouterr().out


def test_live_refuses_edges_not_built_from_the_full_train_window(tmp_path, monkeypatch, capsys):
    edges = tmp_path / "edges.json"
    edges.write_text('{"window": ["2022-01-01", "2023-12-31"], "edges": {}}', encoding="utf-8")
    monkeypatch.setattr(vcr, "load_live_trades", lambda: pytest.fail("read the book"))
    assert vcr.main(["--source", "live", "--edges", str(edges)]) == 1
    assert "refused" in capsys.readouterr().out


def test_continuous_key_without_edges_is_one_no_edges_bucket():
    assert vcr.bucket_of(0.37, None, continuous=True) == "no-edges"
    assert vcr.bucket_of(0.91, None, continuous=True) == "no-edges"
    assert vcr.bucket_of(None, None, continuous=True) == "None"
    rows = [_row("confluence", "bullish", "win", 1.0, vol_trend_10_50=v) for v in (0.1, 0.2)]
    assert [line["bucket"] for line in vcr.bucket_table(rows, "vol_trend_10_50", None)] == ["no-edges"]


@pytest.mark.parametrize("start,end", [("garbage", "2023-12-31"), ("2020-01-01", "2023-13-45"), ("2020", "2023-12-31"),
                                       ("2021-1-5", "2023-12-31")])
def test_window_refusal_rejects_unparseable_dates(start, end):
    assert "refused" in vcr.window_refusal(start, end)
