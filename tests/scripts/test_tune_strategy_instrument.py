"""v158 WC9: tune_strategy.py --instrument v1|v2 (v136 rule 1: v1 byte-identical;
section 1: research span, PIT universe gated on the signal day, per-fold
selection on train data only, pooled out-of-fold ExpR, watchlist slice)."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
for _sub in ("scripts/backtest", "scripts/data"):
    if str(ROOT / _sub) not in sys.path:
        sys.path.insert(0, str(ROOT / _sub))

import tune_strategy as ts  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting import backtest  # noqa: E402
from swingbot.core.backtesting.backtest import BacktestTrade  # noqa: E402
from swingbot.core.backtesting.instrument.contract import resolve  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402

V1, V2 = resolve("v1"), resolve("v2")
ALWAYS = [("2009-01-01", "9999-12-31")]


def _trade(entry, r=1.0, outcome=None, exit_=None):
    return BacktestTrade(entry_date=entry, exit_date=exit_ or entry, direction="bullish",
                         entry=50.0, stop_loss=48.0, take_profit=54.0,
                         outcome=outcome or ("win" if r > 0 else "loss"), exit_price=54.0,
                         return_pct=8.0, r_multiple=r, holding_days=3)


def _frame(volume=1_000_000, start="2009-06-01", end="2025-12-31"):
    index = pd.bdate_range(start, end)
    return pd.DataFrame({"Open": 50.0, "High": 50.0, "Low": 50.0, "Close": 50.0,
                         "Volume": volume}, index=index)


def _rows(r_by_year, tickers=("AAA",)):
    return [(tk, _trade(f"{y}-03-02", r_by_year(y), exit_=f"{y}-03-10"))
            for tk in tickers for y in range(2010, 2026)]


def STEADY(year):
    return 0.5


def FADES(year):
    return 3.0 if year <= 2013 else -1.0


def LOSES(year):
    return -1.0


@pytest.fixture(autouse=True)
def _pin_yfinance(monkeypatch):
    """v162: pin the training source so main() never needs the Alpaca store."""
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")
    training_data.reset()
    yield
    training_data.reset()


@pytest.fixture
def live_flags_off(monkeypatch):
    for name in backtest._LIVE_STATE_FLAGS:
        monkeypatch.setattr(config, name, False, raising=False)


# --- the v1 rule, moved into helpers unchanged -------------------------------------

def test_run_config_statistics_are_unchanged(monkeypatch):
    trades = [_trade("2019-12-31", 5.0), _trade("2020-01-02", 2.0), _trade("2021-06-01", -1.0),
              _trade("2023-12-31", 0.0, outcome="scratch"), _trade("2024-01-02", 9.0)]
    monkeypatch.setattr(ts.bt, "run_backtest", lambda *a, **k: SimpleNamespace(trades=trades))
    monkeypatch.setattr(ts, "LEGACY_HORIZONS", ("3m",))
    assert ts.run_config("RSI", {"AAA": None}) == {
        "n_eval": 2, "win_rate": 50.0, "expectancy_r": pytest.approx(1 / 3),
        "excluded_share": pytest.approx(1 / 3)}


def test_rank_prefers_qualifying_rows_then_falls_back_to_the_argmax():
    good = {"n_eval": 30, "win_rate": 80.0, "expectancy_r": 0.1, "excluded_share": 0.5}
    loud = {"n_eval": 29, "win_rate": 99.0, "expectancy_r": 9.0, "excluded_share": 0.0}
    assert ts._qualifies(good) and not ts._qualifies(loud)
    assert [k for k, _ in ts._rank([("loud", loud), ("good", good)])] == ["good"]
    unscored = dict(loud, expectancy_r=None)
    assert [k for k, _ in ts._rank([("b", unscored), ("a", loud)])] == ["a", "b"]


def test_rank_keeps_grid_order_on_ties():
    s = {"n_eval": 1, "win_rate": 100.0, "expectancy_r": 0.5, "excluded_share": 0.0}
    assert [k for k, _ in ts._rank([(0, s), (1, dict(s)), (2, dict(s))])] == [0, 1, 2]


# --- guards ---------------------------------------------------------------------------

def _ns(exit_model):
    return SimpleNamespace(exit_model=exit_model, scale_out=False)


def test_v1_guards_are_a_no_op():
    ts._instrument_guards(_ns("v1"), V1)


def test_v2_refuses_the_v1_exit_model(live_flags_off):
    with pytest.raises(SystemExit, match="needs exit_model='v2'"):
        ts._instrument_guards(_ns("v1"), V2)


def test_v2_refuses_a_live_state_flag(monkeypatch, live_flags_off):
    monkeypatch.setattr(config, backtest._LIVE_STATE_FLAGS[0], True, raising=False)
    with pytest.raises(SystemExit, match="refuses lookahead"):
        ts._instrument_guards(_ns("v2"), V2)


def test_v2_accepts_exit_model_v2(live_flags_off):
    ts._instrument_guards(_ns("v2"), V2)


# --- universe ---------------------------------------------------------------------------

def test_v1_loads_the_watchlist_exactly_as_today(monkeypatch):
    monkeypatch.setattr(ts, "load_watchlist", lambda: ["BBB", "AAA", "CCC"])
    monkeypatch.setattr(ts, "load_cached", lambda t: None if t == "CCC" else t.lower())
    assert ts._load_universe(V1) == ({"AAA": "aaa", "BBB": "bbb"}, {})


def test_v2_loads_the_contract_pit_universe_with_spans(monkeypatch):
    seen, pits = {}, []

    def tickers(universe):
        seen["tickers"] = universe
        return ["AAA", "BBB", "CCC", "DDD"]

    def membership(universe, symbols):
        seen["membership"] = (universe, list(symbols))
        return {"AAA": ALWAYS, "CCC": ALWAYS}

    def exclusion(df, ticker, pit):
        pits.append(pit)
        return ("data_quality", "bad bars") if ticker == "CCC" else None

    monkeypatch.setattr(ts.rbr, "_tickers_for_run", tickers)
    monkeypatch.setattr(ts.rbr, "_membership_for_run", membership)
    monkeypatch.setattr(ts.rbr, "_exclusion_reason", exclusion)
    monkeypatch.setattr(ts, "load_cached", lambda t: None if t == "DDD" else t)
    frames, spans = ts._load_universe(V2)
    assert seen == {"tickers": "sp500_pit",
                    "membership": ("sp500_pit", ["AAA", "BBB", "CCC", "DDD"])}
    assert pits == [True, True, True]          # the PIT branch: no non-causal floor
    assert frames == {"AAA": "AAA", "BBB": "BBB"}
    assert spans == {"AAA": ALWAYS, "BBB": []}  # no membership row = never a member


# --- _v2_trades -----------------------------------------------------------------------------

def test_v2_trades_run_the_v2_instrument_over_the_research_span(monkeypatch):
    calls = []

    def fake(ticker, df, strategy, hk, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(trades=[_trade("2009-12-31"), _trade("2010-01-04"),
                                       _trade("2025-12-31"), _trade("2026-01-02")])

    monkeypatch.setattr(ts.bt, "run_backtest", fake)
    monkeypatch.setattr(ts, "LEGACY_HORIZONS", ("3m",))
    rows = ts._v2_trades("RSI", {"AAA": _frame()}, {"AAA": ALWAYS}, V2, True)
    assert [(tk, t.entry_date) for tk, t in rows] == [("AAA", "2010-01-04"), ("AAA", "2025-12-31")]
    assert calls == [{"one_at_a_time": True, "exit_model": "v2", "scale_out": True,
                      "tp2_mode": "none", "instrument": V2}]


def test_v2_trades_never_read_a_bar_past_the_research_end(monkeypatch):
    """WC4 caller rule: price data is truncated at research_end, so even a
    trade whose exit walk runs past it never reads a sealed-holdout bar."""
    last_bars = []

    def fake(ticker, df, strategy, hk, **kwargs):
        last_bars.append(df.index.max())
        return SimpleNamespace(trades=[])

    monkeypatch.setattr(ts.bt, "run_backtest", fake)
    monkeypatch.setattr(ts, "LEGACY_HORIZONS", ("3m",))
    ts._v2_trades("RSI", {"AAA": _frame(end="2026-09-30")}, {"AAA": ALWAYS}, V2, False)
    assert last_bars == [pd.Timestamp("2025-12-31")]


def test_v2_trades_gate_membership_and_the_floor_on_the_signal_day(monkeypatch):
    signal_inside = SimpleNamespace(entry_date="2021-03-01", signal_date="2021-02-26",
                                    exit_date="2021-03-05", outcome="win", r_multiple=1.0)
    entry_inside = SimpleNamespace(entry_date="2021-02-01", signal_date="2021-01-29",
                                   exit_date="2021-02-05", outcome="win", r_multiple=1.0)
    monkeypatch.setattr(ts.bt, "run_backtest",
                        lambda *a, **k: SimpleNamespace(trades=[signal_inside, entry_inside]))
    monkeypatch.setattr(ts, "LEGACY_HORIZONS", ("3m",))
    spans = {"AAA": [("2021-02-01", "2021-03-01")]}        # [start, end)
    rows = ts._v2_trades("RSI", {"AAA": _frame()}, spans, V2, False)
    assert [t for _, t in rows] == [signal_inside]
    assert ts._v2_trades("RSI", {"AAA": _frame(volume=1_000)}, {"AAA": ALWAYS}, V2, False) == []


# --- out of fold ------------------------------------------------------------------------------

def test_out_of_fold_selects_per_fold_on_train_trades_only():
    """FADES leads STEADY in train while (12 - m) / (4 + m) > 0.5, i.e. for the
    folds 2014..2020 (m = 0..6 earlier test years in train); STEADY after."""
    oof = ts._out_of_fold({0: _rows(STEADY), 1: _rows(FADES)}, V2)
    assert oof.choices == tuple((y, 1 if y <= 2020 else 0) for y in range(2014, 2026))
    assert [t.r_multiple for t in oof.trades] == [-1.0] * 7 + [0.5] * 5


def test_nothing_tuned_skips_the_folds():
    rows = _rows(FADES)
    oof = ts._out_of_fold({0: rows}, V2)
    assert oof.choices == ()
    assert oof.trades == [t for _, t in rows]


def test_fold_report_is_empty_and_silent_under_v1(capsys):
    assert ts._fold_report([], {}, V1) == {}
    assert capsys.readouterr().out == ""


# --- main, end to end on a stubbed engine ------------------------------------------------------

GRID = {0.75: STEADY, 1.0: FADES, 1.5: LOSES}     # MACD's built-in ext_atr grid


@pytest.fixture
def harness(monkeypatch, tmp_path, live_flags_off):
    calls, frame = [], _frame()

    def fake_run_backtest(ticker, df, strategy, hk, **kwargs):
        calls.append(dict(kwargs, ticker=ticker))
        r_by_year = GRID[ts.ef.DEFAULT_PARAMS[strategy]["ext_atr"]]
        return SimpleNamespace(trades=[_trade(f"{y}-03-02", r_by_year(y), exit_=f"{y}-03-10")
                                       for y in range(2010, 2026)])

    monkeypatch.setitem(ts.PARAM_GRID, "MACD", ts.PARAM_GRID["MACD"])   # --grid rewrites it
    monkeypatch.setattr(ts.bt, "run_backtest", fake_run_backtest)
    monkeypatch.setattr(ts, "LEGACY_HORIZONS", ("3m",))
    monkeypatch.setattr(ts, "load_watchlist", lambda: ["AAA"])
    monkeypatch.setattr(ts, "load_cached", lambda ticker: frame)
    monkeypatch.setattr(ts.rbr, "_tickers_for_run", lambda universe: ["AAA", "BBB"])
    monkeypatch.setattr(ts.rbr, "_membership_for_run",
                        lambda universe, tickers: {t: ALWAYS for t in tickers})
    monkeypatch.setattr(ts.rbr, "_exclusion_reason", lambda df, ticker, pit: None)

    def run(*argv):
        out = tmp_path / "out.json"
        monkeypatch.setattr(sys, "argv", ["tune_strategy.py", "--strategy", "MACD",
                                          "--json", str(out), *argv])
        ts.main()
        return json.loads(out.read_text(encoding="utf-8"))

    return SimpleNamespace(run=run, calls=calls)


V2_FLAGS = ("--instrument", "v2", "--exit-model", "v2")


def test_v1_payload_and_output_are_todays(harness, capsys):
    payload = harness.run()
    assert list(payload) == ["strategy", "gate", "grid", "best", "data_source", "provenance"]
    assert len(harness.calls) == 3                    # 3 configs x 1 watchlist ticker x 1 horizon
    assert all("instrument" not in call and call["tp2_mode"] == "none"
               for call in harness.calls)
    assert payload["grid"][0]["n_eval"] == 4          # TRAIN 2020..2023 only
    out = capsys.readouterr().out
    assert "1 tickers loaded from yfinance training data" in out
    assert "instrument" not in out and "out-of-fold" not in out


def test_explicit_v1_is_identical_to_the_default(harness, capsys):
    default = harness.run()
    default_out = capsys.readouterr().out
    assert harness.run("--instrument", "v1") == default
    assert capsys.readouterr().out == default_out


def test_v2_selects_per_fold_and_reports_pooled_out_of_fold_expectancy(harness, capsys):
    payload = harness.run(*V2_FLAGS)
    assert len(harness.calls) == 6                    # 3 configs x 2 PIT tickers x 1 horizon
    assert all(call["instrument"] is V2 and call["tp2_mode"] == "none"
               for call in harness.calls)
    assert payload["instrument"] == "v2"
    assert payload["research_span"] == ["2010-01-01", "2025-12-31"]
    assert payload["grid"][0]["n_eval"] == 32         # research span: 16 years x 2 tickers
    assert payload["best"]["params"] == {"ext_atr": 0.75}
    oof = payload["out_of_fold"]
    assert [f["test_year"] for f in oof["folds"]] == list(range(2014, 2026))
    assert [f["params"]["ext_atr"] for f in oof["folds"]] == [1.0] * 7 + [0.75] * 5
    assert oof["n_eval"] == 24
    assert oof["expectancy_r"] == -0.375
    assert payload["watchlist_slice"] == {"status": "thin", "n": 12, "expectancy_r": -0.375}
    out = capsys.readouterr().out
    assert "Pooled out-of-fold: N=24" in out
    assert "-> THIN" in out


def test_v2_with_nothing_tuned_reports_the_research_span_as_out_of_fold(harness):
    payload = harness.run(*V2_FLAGS, "--grid", "ext_atr=1.0")
    assert payload["out_of_fold"]["folds"] == []
    assert payload["out_of_fold"]["n_eval"] == 32
    assert payload["out_of_fold"]["expectancy_r"] == 0.0


def test_v2_with_the_default_exit_model_exits_before_any_ticker(harness):
    with pytest.raises(SystemExit, match="needs exit_model='v2'"):
        harness.run("--instrument", "v2")
    assert harness.calls == []
