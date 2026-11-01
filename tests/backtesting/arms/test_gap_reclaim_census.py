"""V192-15: the gap-reclaim census -- every next-open market decision the component replay makes,
keyed as ArmTrade.key -- and the measure_arms sidecar <out stem>.gap_reclaim.json."""
import dataclasses
import json
import sys
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms import gap_reclaim_census as grc
from swingbot.core.backtesting.arms.engine import run_arm
from swingbot.core.planning import gap_reclaim as gr
from swingbot.core.planning import market_next_open as mno
from tests.backtesting.test_v74_fixture import load_v74_fixture

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_arms as ma  # noqa: E402

FIXTURE = load_v74_fixture()
WINDOW = ("1900-01-01", "2100-12-31")
VETO = {"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": 0.10}
DECISIONS = {gr.FILL_OPEN, gr.RECLAIM_WAIT, gr.OPEN_THROUGH_STOP, gr.RISK_CAP, mno.NO_BAR}


@pytest.fixture(autouse=True)
def _legacy_source(monkeypatch):
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    yield
    training_data.reset()


def decision(**over):
    base = dict(ticker="AAA", strategy="RSI", horizon_key="4w", source="strategy", direction="bullish",
                signal_date="2021-03-01", entry=100.0, stop=95.0, open_price=99.0, atr=2.0,
                reclaim_level=99.8, gap_atr=0.5, decision=gr.RECLAIM_WAIT, reclaimed=False,
                ambiguous=False, fill_price=None)
    base.update(over)
    return mno.NextOpenDecision(**base)


def row(**over):
    return dataclasses.asdict(decision(**over))


def test_row_key_is_the_arm_trade_key():
    trade = ArmTrade("AAA", "RSI", "4w", "2021-03-01", "win", 1.0, 2.0, "strategy", "bullish")
    assert grc.row_key(row()) == trade.key


def _emitting_run_arm(monkeypatch, decisions_for, seen_deltas=None):
    def fake_run_arm(ticker, df, engine_ids, horizons, signal_window, delta):
        if seen_deltas is not None:
            seen_deltas.append(dict(delta))
        for item in decisions_for(ticker):
            mno._emit(item)
        return []
    monkeypatch.setattr(grc, "run_arm", fake_run_arm)


def test_census_ticker_keeps_only_decisions_inside_the_window(monkeypatch):
    deltas = []
    _emitting_run_arm(monkeypatch, lambda t: [decision(signal_date="2020-12-31"),
                                              decision(signal_date="2021-03-01"),
                                              decision(signal_date="2023-01-02")], deltas)
    rows = grc.census_ticker("AAA", object(), ("strategy",), ("4w",), ("2021-01-01", "2022-12-31"), VETO)
    assert [r["signal_date"] for r in rows] == ["2021-03-01"]
    assert rows[0] == row()
    assert deltas == [VETO]


def test_the_observer_is_released_after_the_census(monkeypatch):
    before = list(mno._OBSERVERS)
    _emitting_run_arm(monkeypatch, lambda t: [decision()])
    grc.census_ticker("AAA", object(), ("strategy",), ("4w",), WINDOW, VETO)
    assert mno._OBSERVERS == before


def test_census_skips_a_ticker_without_a_frame_and_sorts_by_ticker(monkeypatch, capsys):
    monkeypatch.setattr(grc, "load_frame", {"AAA": object(), "BBB": object()}.get)
    _emitting_run_arm(monkeypatch, lambda t: [decision(ticker=t)])
    rows = grc.census(["BBB", "ZZZ", "AAA"], ("strategy",), ("4w",), WINDOW, VETO, workers=1)
    assert [r["ticker"] for r in rows] == ["AAA", "BBB"]
    assert "[census] 3/3 (100%)" in capsys.readouterr().out


def _mixed_rows():
    return [
        row(decision=gr.FILL_OPEN, gap_atr=0.05, fill_price=99.0),
        row(signal_date="2021-03-02", reclaimed=True, ambiguous=True, fill_price=100.01, gap_atr=0.30),
        row(signal_date="2021-03-03", gap_atr=0.60),
        row(signal_date="2021-03-04", decision=gr.OPEN_THROUGH_STOP, gap_atr=2.6),
        row(signal_date="2021-03-05", decision=gr.RISK_CAP, gap_atr=0.12),
        row(signal_date="2021-03-08", direction="bearish", decision=gr.FILL_OPEN, gap_atr=-0.2),
        row(signal_date="2021-03-09", horizon_key="2w", decision=mno.NO_BAR, open_price=None, gap_atr=None),
    ]


def test_reachability_summary_counts_every_decision_kind():
    summary = grc.reachability_summary(_mixed_rows())
    total = summary["total"]
    assert (total["market_plans"], total["filled_at_open"], total["armed"], total["reclaimed"]) == (7, 2, 2, 1)
    assert (total["ambiguous"], total["gap_no_reclaim"], total["open_through_stop"]) == (1, 1, 1)
    assert (total["risk_cap"], total["no_bar"]) == (1, 1)
    assert total["reclaim_rate"] == 0.5 and total["ambiguous_share"] == 1.0
    assert [(c["horizon_key"], c["direction"], c["market_plans"]) for c in summary["cells"]] == [
        ("2w", "bullish", 1), ("4w", "bearish", 1), ("4w", "bullish", 5)]
    assert summary["verdict"] == grc.REACHABLE == "REACHABLE"


def test_reachability_summary_reports_the_gap_over_atr_distribution():
    gap = grc.reachability_summary(_mixed_rows())["gap_atr"]
    assert gap["n"] == 6
    assert gap["q50"] == pytest.approx(0.21)
    assert gap["share_at_or_above"] == {"0.1": pytest.approx(4 / 6), "0.25": pytest.approx(3 / 6),
                                        "0.5": pytest.approx(2 / 6)}


def test_no_armed_plan_is_zero_diff():
    summary = grc.reachability_summary([row(decision=gr.FILL_OPEN, gap_atr=0.01)])
    assert summary["verdict"] == grc.ZERO_DIFF == "refused:zero-diff"
    assert summary["total"]["reclaim_rate"] is None and summary["total"]["ambiguous_share"] is None


def test_an_empty_census_is_zero_diff_with_no_distribution():
    summary = grc.reachability_summary([])
    assert summary["verdict"] == grc.ZERO_DIFF and summary["cells"] == []
    assert summary["gap_atr"] == {"n": 0, "share_at_or_above": {}}


def test_repriced_and_ambiguous_keys():
    rows = _mixed_rows()
    assert grc.repriced_keys(rows) == {grc.row_key(rows[1])}
    assert grc.ambiguous_keys(rows) == {grc.row_key(rows[1])}
    assert grc.repriced_keys([]) == set() == grc.ambiguous_keys([])


def test_sidecar_path_and_loader(tmp_path):
    arms = tmp_path / "v192-g025-selection.json"
    assert grc.sidecar_path(arms) == tmp_path / "v192-g025-selection.gap_reclaim.json"
    assert grc.load_sidecar(arms) is None
    grc.sidecar_path(arms).write_text(json.dumps({"rows": []}), encoding="utf-8")
    assert grc.load_sidecar(arms) == {"rows": []}


# --- integration on the v74 AAPL fixture (V192-5..V192-7 behaviour) ---------------------------

def test_with_both_knobs_off_the_census_sees_nothing():
    assert grc.census_ticker("AAPL", FIXTURE["AAPL"], ("confluence", "strategy"), ("4w",), WINDOW, {}) == []


def test_the_veto_census_pairs_with_the_component_rows():
    rows = grc.census_ticker("AAPL", FIXTURE["AAPL"], ("confluence", "strategy"), ("4w",), WINDOW, VETO)
    component = run_arm("AAPL", FIXTURE["AAPL"], ("confluence", "strategy"), ("4w",), WINDOW, VETO)
    assert rows and {r["decision"] for r in rows} <= DECISIONS
    assert grc.repriced_keys(rows) <= {t.key for t in component}
    assert all(r["fill_price"] == r["open_price"] for r in rows if r["decision"] == gr.FILL_OPEN)
    assert all(r["reclaim_level"] is not None for r in rows if r["decision"] == gr.RECLAIM_WAIT)
    assert grc.reachability_summary(rows)["total"]["market_plans"] == len(rows)


# --- the measure_arms sidecar ------------------------------------------------------------------

def test_the_sidecar_row_is_registered_under_the_census_suffix():
    assert ("gap_reclaim", "gap_reclaim_sidecar") in ma._SIDECARS
    assert grc.SIDECAR_SUFFIX == "gap_reclaim" and ma.GAP_RECLAIM_KNOB == "GAP_RECLAIM_ATR"


@pytest.mark.parametrize("delta", [{"MARKET_ENTRY_NEXT_OPEN": True}, {"MIN_REWARD_PCT": 4.0},
                                   {"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": 0.0}])
def test_no_sidecar_without_a_positive_gap_knob(monkeypatch, delta):
    monkeypatch.setattr(grc, "census", lambda *a, **k: pytest.fail("census ran"))
    assert ma.gap_reclaim_sidecar({}, delta, ["AAA"], ma.windows.resolve("pilot")) is None


def test_the_sidecar_carries_the_census_and_counts_repriced_component_rows(monkeypatch):
    calls = []
    census_rows = [row(reclaimed=True, fill_price=100.01), row(ticker="BBB", reclaimed=True, fill_price=100.01)]
    monkeypatch.setattr(grc, "census", lambda *a, **k: calls.append((a, k)) or census_rows)
    monkeypatch.setattr(ma, "_resolve_replay_workers", lambda workers: 1)
    trade = ArmTrade("AAA", "RSI", "4w", "2021-03-01", "win", 1.0, 2.0, "strategy", "bullish")
    blob = {"provenance": {"engines": ["strategy"], "horizons": ["4w"],
                           "baseline_knob_delta": {"MARKET_ENTRY_NEXT_OPEN": True}},
            "component": [dataclasses.asdict(trade)]}
    spec = ma.windows.resolve("pilot")
    side = ma.gap_reclaim_sidecar(blob, VETO, ["AAA", "BBB"], spec)
    assert calls == [((["AAA", "BBB"], ["strategy"], ["4w"], tuple(spec.signal_window), VETO), {"workers": 1})]
    assert side["repriced_in_component"] == 1 and side["repriced_absent_from_component"] == 1
    assert side["knob_delta"] == VETO and side["baseline_knob_delta"] == {"MARKET_ENTRY_NEXT_OPEN": True}
    assert side["universe_count"] == 2 and side["signal_window"] == list(spec.signal_window)
    assert side["summary"]["verdict"] == grc.REACHABLE and side["rows"] == census_rows


def _main(tmp_path, *knobs):
    return ma.main([*knobs, "--stage", "pilot", "--out", str(tmp_path / "arms.json"), "--workers", "1"])


@pytest.fixture
def fake_producer(monkeypatch):
    monkeypatch.setattr(ma, "cached_universe", lambda: ["AAA"])
    monkeypatch.setattr(ma, "produce", lambda stage, delta, **kw: {
        "provenance": {"changed_outcomes": 2, "engines": ["strategy"], "horizons": ["4w"]},
        "baseline": [], "component": []})
    monkeypatch.setattr(ma.training_data, "write_provenance", lambda out: None)
    monkeypatch.setattr(ma, "_resolve_replay_workers", lambda workers: 1)


def test_main_writes_the_gap_reclaim_sidecar_beside_the_arms(monkeypatch, tmp_path, fake_producer):
    monkeypatch.setattr(grc, "census", lambda *a, **k: [row(reclaimed=True, fill_price=100.01)])
    assert _main(tmp_path, "--knob", "MARKET_ENTRY_NEXT_OPEN=true", "--knob", "GAP_RECLAIM_ATR=0.25",
                 "--baseline-knob", "MARKET_ENTRY_NEXT_OPEN=true") == 0
    side = json.loads((tmp_path / "arms.gap_reclaim.json").read_text(encoding="utf-8"))
    assert side["summary"]["total"]["reclaimed"] == 1 and len(side["rows"]) == 1
    assert grc.load_sidecar(tmp_path / "arms.json") == side


def test_main_writes_no_gap_sidecar_for_the_next_open_basis_run(monkeypatch, tmp_path, fake_producer):
    monkeypatch.setattr(grc, "census", lambda *a, **k: pytest.fail("census ran"))
    assert _main(tmp_path, "--knob", "MARKET_ENTRY_NEXT_OPEN=true") == 0
    assert not (tmp_path / "arms.gap_reclaim.json").exists()


def test_a_census_failure_only_warns(monkeypatch, tmp_path, capsys, fake_producer):
    def boom(*a, **k):
        raise RuntimeError("frame store down")
    monkeypatch.setattr(grc, "census", boom)
    assert _main(tmp_path, "--knob", "MARKET_ENTRY_NEXT_OPEN=true", "--knob", "GAP_RECLAIM_ATR=0.25") == 0
    assert "gap_reclaim sidecar not written" in capsys.readouterr().err
    assert (tmp_path / "arms.json").exists() and not (tmp_path / "arms.gap_reclaim.json").exists()
