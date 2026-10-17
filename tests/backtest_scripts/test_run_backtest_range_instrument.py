"""v158 WC8: run_backtest_range.py --instrument v1|v2 (v136 rule 1: v1
byte-identical; rule 2: windows from the contract; section 1: PIT universe on
the signal date and the watchlist slice)."""
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

import run_backtest_range as rbr  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting import backtest  # noqa: E402
from swingbot.core.backtesting.backtest import BacktestTrade  # noqa: E402
from swingbot.core.backtesting.instrument.cli import HOLDOUT_SEALED  # noqa: E402
from swingbot.core.backtesting.instrument.contract import resolve  # noqa: E402

V1, V2 = resolve("v1"), resolve("v2")
ALWAYS = [("2010-01-01", "9999-12-31")]


def _args(**over):
    base = dict(train=False, validation=False, date_from=None, date_to=None, universe=None,
                scenarios=False, emit_registry=None, from_json=None,
                exit_model="v2", tp2="none")
    base.update(over)
    return SimpleNamespace(**base)


def _trade(entry, r=1.0, outcome="win"):
    return BacktestTrade(entry_date=entry, exit_date=entry, direction="bullish", entry=50.0,
                         stop_loss=48.0, take_profit=54.0, outcome=outcome, exit_price=54.0,
                         return_pct=8.0, r_multiple=r, holding_days=3)


def _frame(volume=1_000_000, periods=400, start="2020-06-01"):
    index = pd.bdate_range(start, periods=periods)
    return pd.DataFrame({"Open": 50.0, "High": 50.0, "Low": 50.0, "Close": 50.0,
                         "Volume": volume}, index=index)


@pytest.fixture
def live_flags_off(monkeypatch):
    for name in backtest._LIVE_STATE_FLAGS:
        monkeypatch.setattr(config, name, False, raising=False)


# --- _resolve_window ------------------------------------------------------------

def test_v1_windows_are_todays():
    assert rbr._resolve_window(_args(train=True), V1) == (*rbr.TRAIN, 30, "TRAIN")
    assert rbr._resolve_window(_args(validation=True), V1) == (*rbr.VALIDATION, 15, "VALIDATION")
    assert rbr._resolve_window(_args(train=True), V1)[:2] == ("2020-01-01", "2023-12-31")


def test_v1_custom_window_is_unchecked_as_today():
    args = _args(date_from="2018-06-01", date_to="2019-01-01")
    assert rbr._resolve_window(args, V1) == ("2018-06-01", "2019-01-01", 15, "CUSTOM")


@pytest.mark.parametrize("over", [{}, {"date_from": "2021-01-01"}, {"date_to": "2021-12-31"}])
def test_a_missing_window_is_a_value_error_main_turns_into_ap_error(over):
    with pytest.raises(ValueError, match="need --train, --validation, or --from/--to"):
        rbr._resolve_window(_args(**over), V1)


def test_v2_train_is_the_research_span():
    assert rbr._resolve_window(_args(train=True), V2) == ("2010-01-01", "2025-12-31", 30, "TRAIN")


def test_v2_validation_is_sealed():
    with pytest.raises(SystemExit) as exc:
        rbr._resolve_window(_args(validation=True), V2)
    assert HOLDOUT_SEALED in str(exc.value)


def test_v2_custom_window_must_lie_inside_the_research_span():
    inside = _args(date_from="2014-01-01", date_to="2014-12-31")
    assert rbr._resolve_window(inside, V2) == ("2014-01-01", "2014-12-31", 15, "CUSTOM")
    with pytest.raises(SystemExit, match="research span"):
        rbr._resolve_window(_args(date_from="2025-01-01", date_to="2026-03-31"), V2)


# --- _instrument_guards ---------------------------------------------------------

def test_v1_guards_are_a_no_op():
    args = _args(scenarios=True, emit_registry="reg.json", from_json="x.json",
                 exit_model="v1", tp2="levels", universe="etfs")
    before = dict(vars(args))
    rbr._instrument_guards(args, V1)
    assert vars(args) == before


def test_v2_pins_the_contract_universe(live_flags_off):
    args = _args()
    rbr._instrument_guards(args, V2)
    assert args.universe == "sp500_pit"
    explicit = _args(universe="sp500_pit")
    rbr._instrument_guards(explicit, V2)
    assert explicit.universe == "sp500_pit"


def test_v2_refuses_a_different_universe(live_flags_off):
    with pytest.raises(SystemExit, match="sp500_pit"):
        rbr._instrument_guards(_args(universe="etfs"), V2)


@pytest.mark.parametrize("over, owner", [
    ({"scenarios": True}, "phase 5"),
    ({"emit_registry": "reg.json"}, "phase 6"),
    ({"from_json": "x.json"}, "phase 6"),
])
def test_v2_refuses_paths_a_later_phase_owns(live_flags_off, over, owner):
    with pytest.raises(SystemExit) as exc:
        rbr._instrument_guards(_args(**over), V2)
    assert owner in str(exc.value)
    assert "--instrument v2" in str(exc.value)


@pytest.mark.parametrize("over, message", [
    ({"exit_model": "v1"}, "needs exit_model='v2'"),
    ({"tp2": "levels"}, "tp2_mode='levels'"),
])
def test_v2_refuses_v1_exit_knobs_before_any_backtest(live_flags_off, over, message):
    with pytest.raises(SystemExit, match=message):
        rbr._instrument_guards(_args(**over), V2)


def test_v2_refuses_a_live_state_flag(monkeypatch, live_flags_off):
    monkeypatch.setattr(config, backtest._LIVE_STATE_FLAGS[0], True, raising=False)
    with pytest.raises(SystemExit, match="refuses lookahead"):
        rbr._instrument_guards(_args(), V2)


# --- _windowed_trades / _v2_window_trades ------------------------------------------

def _signal_trade(signal, entry):
    return SimpleNamespace(entry_date=entry, signal_date=signal, exit_date=entry,
                           outcome="win", r_multiple=1.0)


def test_v1_windowing_is_exactly_todays_expression():
    trades = [_trade("2019-12-31"), _trade("2020-01-02"), _trade("2022-06-01"),
              _trade("2024-01-02")]
    summary = SimpleNamespace(trades=trades)
    spans = [("2020-01-01", "2022-01-01")]
    for s in (None, spans, []):
        assert rbr._windowed_trades(summary, *rbr.TRAIN, s, _frame(), V1) == \
            rbr.member_trades(rbr.window_trades(summary, *rbr.TRAIN), s)


def test_v2_checks_membership_on_the_signal_day_v1_on_the_entry_day():
    spans = [("2021-01-01", "2021-03-01")]
    crosses_out = _signal_trade(signal="2021-02-26", entry="2021-03-01")
    summary = SimpleNamespace(trades=[crosses_out])
    df = _frame()
    assert rbr._v2_window_trades(summary, "2010-01-01", "2025-12-31", spans, df, V2) == [crosses_out]
    assert rbr._windowed_trades(summary, "2010-01-01", "2025-12-31", spans, df, V2) == [crosses_out]
    assert rbr._windowed_trades(summary, "2010-01-01", "2025-12-31", spans, df, V1) == []


def test_v2_applies_the_causal_floor_v1_does_not():
    summary = SimpleNamespace(trades=[_trade("2021-02-01")])
    thin = _frame(volume=1_000)                      # $50k a day
    assert rbr._windowed_trades(summary, *rbr.TRAIN, None, thin, V1) == summary.trades
    assert rbr._v2_window_trades(summary, "2010-01-01", "2025-12-31", ALWAYS, thin, V2) == []


def test_v2_windows_by_entry_date():
    summary = SimpleNamespace(trades=[_signal_trade(signal="2025-12-31", entry="2026-01-02")])
    df = _frame(periods=1600, start="2020-01-01")
    assert rbr._v2_window_trades(summary, "2010-01-01", "2025-12-31", ALWAYS, df, V2) == []


# --- _watchlist_slice ---------------------------------------------------------------

def _rows(ticker, n, r, outcome):
    return [(ticker, "RSI", "3m", _trade("2021-02-01", r=r, outcome=outcome)) for _ in range(n)]


def test_slice_scores_only_watchlist_rows_and_fails_on_negative_expectancy():
    rows = _rows("AAA", 30, -1.0, "loss") + _rows("BBB", 50, 2.0, "win")
    line, verdict = rbr._watchlist_slice(rows, ["AAA"])
    assert verdict == {"status": "fail", "n": 30, "expectancy_r": -1.0}
    assert "N=30" in line and "FAIL" in line


def test_slice_passes_at_or_above_zero():
    line, verdict = rbr._watchlist_slice(_rows("AAA", 30, 1.0, "win"), {"AAA"})
    assert verdict == {"status": "pass", "n": 30, "expectancy_r": 1.0}
    assert "PASS" in line


def test_slice_below_thirty_is_thin_and_an_empty_slice_too():
    _, few = rbr._watchlist_slice(_rows("AAA", 29, -1.0, "loss"), ["AAA"])
    assert few == {"status": "thin", "n": 29, "expectancy_r": -1.0}
    line, none = rbr._watchlist_slice(_rows("BBB", 40, -1.0, "loss"), ["AAA"])
    assert none == {"status": "thin", "n": 0, "expectancy_r": None}
    assert "ExpR=n/a" in line


# --- main, end to end on a stubbed engine -----------------------------------------------

@pytest.fixture
def harness(monkeypatch, tmp_path, live_flags_off):
    calls, seen, frame = [], {}, _frame()

    def fake_run_backtest(ticker, df, strat, hk, **kwargs):
        calls.append(dict(kwargs, ticker=ticker))
        return SimpleNamespace(trades=[_trade("2021-02-01"),
                                       _trade("2021-03-01", r=-1.0, outcome="loss")])

    def tickers(universe, tickers_file=None):
        seen["universe"] = universe
        return ["AAA", "BBB"]

    def membership(universe, symbols):
        return None if universe is None else {sym: ALWAYS for sym in symbols}

    monkeypatch.chdir(tmp_path)          # main writes backtest_range_summary.txt to cwd
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    monkeypatch.setattr(rbr, "run_backtest", fake_run_backtest)
    monkeypatch.setattr(rbr, "_tickers_for_run", tickers)
    monkeypatch.setattr(rbr, "_membership_for_run", membership)
    monkeypatch.setattr(rbr, "load_cached", lambda ticker: frame)
    monkeypatch.setattr(rbr, "_with_context", lambda df, **kwargs: df)
    monkeypatch.setattr(rbr, "_exclusion_reason", lambda df, ticker, pit: None)
    monkeypatch.setattr(rbr, "load_watchlist", lambda: ["AAA"])
    monkeypatch.setattr(rbr, "LEGACY_HORIZONS", ("3m",))

    def run(*argv):
        out = tmp_path / "out.json"
        monkeypatch.setattr(sys, "argv", ["run_backtest_range.py", "--strategy", "RSI",
                                          "--context", "off", "--json", str(out), *argv])
        rbr.main()
        report = (tmp_path / "backtest_range_summary.txt").read_text(encoding="utf-8")
        return json.loads(out.read_text(encoding="utf-8")), report

    return SimpleNamespace(run=run, calls=calls, seen=seen)


V2_FLAGS = ("--instrument", "v2", "--exit-model", "v2", "--tp2", "none")


def test_v1_main_passes_instrument_none_and_adds_nothing(harness):
    payload, report = harness.run("--train")
    assert harness.seen["universe"] is None
    assert len(harness.calls) == 2
    assert all(call["instrument"] is None for call in harness.calls)
    assert list(payload) == ["RSI"]
    assert payload["RSI"]["n_eval"] == 4
    assert "== TRAIN 2020-01-01 .. 2023-12-31" in report
    assert "watchlist slice" not in report and "instrument" not in report


def test_explicit_v1_is_identical_to_the_default(harness):
    default = harness.run("--train")
    default_calls = list(harness.calls)
    harness.calls.clear()
    assert harness.run("--train", "--instrument", "v1") == default
    assert harness.calls == default_calls


def test_v2_main_runs_the_research_span_on_the_pit_universe_with_a_slice(harness):
    payload, report = harness.run("--train", *V2_FLAGS)
    assert harness.seen["universe"] == "sp500_pit"
    assert len(harness.calls) == 2
    assert all(call["instrument"] is resolve("v2") for call in harness.calls)
    assert all(call["exit_model"] == "v2" and call["tp2_mode"] == "none"
               for call in harness.calls)
    assert payload["RSI"]["n_eval"] == 4
    assert payload["_watchlist_slice"] == {"RSI": {"status": "thin", "n": 2, "expectancy_r": 0.0}}
    assert "== TRAIN 2010-01-01 .. 2025-12-31" in report
    assert "instrument v2: universe sp500_pit" in report
    assert "THIN" in report


def test_v2_validation_exits_before_any_backtest(harness):
    with pytest.raises(SystemExit) as exc:
        harness.run("--validation", *V2_FLAGS)
    assert HOLDOUT_SEALED in str(exc.value)
    assert harness.calls == []


def test_v2_with_the_default_tp2_exits_before_any_backtest(harness):
    with pytest.raises(SystemExit, match="tp2_mode='levels'"):
        harness.run("--train", "--instrument", "v2", "--exit-model", "v2")
    assert harness.calls == []


# --- holdout truncation (carry-over from the WC4 fold review) ---------------------

def test_v1_frame_is_untouched():
    df = _frame(periods=1600, start="2020-01-01")
    assert rbr._instrument_frame(df, V1) is df
    assert rbr._instrument_frame(None, V1) is None


def test_v2_frame_stops_at_research_end_so_no_trade_reads_holdout_prices():
    df = _frame(periods=1600, start="2020-01-01")
    assert df.index.max() > pd.Timestamp("2025-12-31")
    cut = rbr._instrument_frame(df, V2)
    assert cut.index.max() <= pd.Timestamp("2025-12-31")
    assert cut.index.max() >= pd.Timestamp("2025-12-30")
    assert rbr._instrument_frame(None, V2) is None


def test_v2_main_hands_run_backtest_no_bar_after_research_end(harness, monkeypatch):
    long_frame = _frame(periods=1600, start="2020-01-01")
    monkeypatch.setattr(rbr, "load_cached", lambda ticker: long_frame)
    seen_ends = []
    original = rbr.run_backtest

    def spy(ticker, df, strat, hk, **kwargs):
        seen_ends.append(df.index.max())
        return original(ticker, df, strat, hk, **kwargs)

    monkeypatch.setattr(rbr, "run_backtest", spy)
    harness.run("--train", *V2_FLAGS)
    assert seen_ends and all(end <= pd.Timestamp("2025-12-31") for end in seen_ends)
