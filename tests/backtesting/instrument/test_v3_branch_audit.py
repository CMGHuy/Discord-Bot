"""v190 V190-8: the instrument branch audit (spec §4).

Every instrument comparison in swingbot/ and scripts/ is `== "v1"` or
`!= "v1"`, so v3 takes v2's path at each. The scan pins the 14 literal sites;
three more branch on a field v3 shares with v2 (`live_constructor`,
`train_window`, `universe`). One behaviour test per site runs v3 beside v2
(and v1 where the contrast matters). A new literal site fails the scan until
it is added here with its v3 test."""
import ast
import inspect
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
for _sub in ("scripts/backtest", "scripts/data"):
    if str(ROOT / _sub) not in sys.path:
        sys.path.insert(0, str(ROOT / _sub))

import run_backtest_range as rbr  # noqa: E402
import tune_strategy as tune  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.analytics import override_fidelity, override_verdict  # noqa: E402
from swingbot.core.backtesting import backtest, backtest_wf  # noqa: E402
from swingbot.core.backtesting.backtest import BacktestTrade  # noqa: E402
from swingbot.core.backtesting.instrument import cli, coverage  # noqa: E402
from swingbot.core.backtesting.instrument.contract import resolve  # noqa: E402
from swingbot.core.planning import exit_sim, exit_sim_v2  # noqa: E402

V1, V2, V3 = resolve("v1"), resolve("v2"), resolve("v3")
ALWAYS = [("2010-01-01", "9999-12-31")]
RESEARCH_END = pd.Timestamp("2025-12-31")
VERSION = re.compile(r"^v\d+$")
RBR, TUNE = "scripts/backtest/run_backtest_range.py", "scripts/backtest/tune_strategy.py"

#: (file, enclosing function) -> the literal it compares `.version` against.
LITERAL_SITES = {
    (RBR, "_instrument_frame"): "v1",
    (RBR, "_windowed_trades"): "v1",
    (RBR, "_instrument_guards"): "v1",
    (RBR, "_missing_frames"): "v1",
    (RBR, "_instrument_report"): "v1",
    (TUNE, "_instrument_guards"): "v1",
    (TUNE, "_load_universe"): "v1",
    (TUNE, "_evaluate"): "v1",
    (TUNE, "_fold_report"): "v1",
    ("swingbot/core/backtesting/backtest_wf.py", "_exit_kwargs"): "v1",
    ("swingbot/core/backtesting/instrument/cli.py", "run_instrument"): "v1",
    ("swingbot/core/backtesting/instrument/cli.py", "require_v1"): "v1",
    ("swingbot/core/planning/exit_sim.py", "simulate_exit"): "v1",
    ("swingbot/core/backtesting/instrument/contract.py", "live_constructor"): "v1",
}
#: (function, the field it branches on) -- the three sites with no literal.
INDIRECT_SITES = ((backtest._uses_live_constructor, "live_constructor"),
                  (cli._has_v1_split, "train_window"),
                  (coverage._intervals, "universe"))
REQUIRE_V1_SCRIPTS = (
    "ablation", "emit_cohort_registry", "measure_arms", "measure_giveback_levels",
    "measure_runner_giveback", "measure_strategy_arm", "permutation_test",
    "quarterly_revalidation", "tune_confluence_gates", "tune_exit_v2", "wf_components",
    "wf_run", "run_backtest_range")


def _version_literals(nodes):
    for node in nodes:
        elements = node.elts if isinstance(node, (ast.Tuple, ast.List, ast.Set)) else [node]
        for element in elements:
            if (isinstance(element, ast.Constant) and isinstance(element.value, str)
                    and VERSION.match(element.value)):
                yield element.value


class _Comparisons(ast.NodeVisitor):
    """(enclosing function, literal) of every `<x>.version <op> "vN"` compare."""

    def __init__(self):
        self.stack, self.found = [], []

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Compare(self, node):
        operands = [node.left, *node.comparators]
        if any(isinstance(o, ast.Attribute) and o.attr == "version" for o in operands):
            others = [o for o in operands if not (isinstance(o, ast.Attribute) and o.attr == "version")]
            function = self.stack[-1] if self.stack else "<module>"
            self.found.extend((function, value) for value in _version_literals(others))
        self.generic_visit(node)


def instrument_comparisons() -> dict:
    found = {}
    for base in ("swingbot", "scripts"):
        for path in sorted((ROOT / base).rglob("*.py")):
            visitor = _Comparisons()
            visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
            rel = path.relative_to(ROOT).as_posix()
            found.update({(rel, function): value for function, value in visitor.found})
    return found


def _frame(periods=2600, start="2016-01-04"):
    index = pd.bdate_range(start, periods=periods)
    return pd.DataFrame({"Open": 50.0, "High": 50.0, "Low": 50.0, "Close": 50.0,
                         "Volume": 1_000_000}, index=index)


def _trade(entry, signal=None):
    trade = BacktestTrade(entry_date=entry, exit_date=entry, direction="bullish", entry=50.0,
                          stop_loss=48.0, take_profit=54.0, outcome="win", exit_price=54.0,
                          return_pct=8.0, r_multiple=1.0, holding_days=3)
    if signal is not None:
        trade.signal_date = signal
    return trade


def _args(**over):
    base = dict(train=False, validation=False, date_from=None, date_to=None, universe=None,
                scenarios=False, emit_registry=None, from_json=None, tickers_file=None,
                exit_model="v2", tp2="none")
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture
def live_flags_off(monkeypatch):
    for name in backtest._LIVE_STATE_FLAGS:
        monkeypatch.setattr(config, name, False, raising=False)


# --- the scan -------------------------------------------------------------------------

def test_every_instrument_comparison_is_against_v1_and_is_audited():
    assert instrument_comparisons() == LITERAL_SITES
    assert set(LITERAL_SITES.values()) == {"v1"}
    assert len(LITERAL_SITES) + len(INDIRECT_SITES) == 17


@pytest.mark.parametrize("function, field", INDIRECT_SITES)
def test_each_indirect_site_still_branches_on_its_field(function, field):
    assert field in inspect.getsource(function)


def test_v3_shares_every_field_the_indirect_sites_read_with_v2():
    assert V3.live_constructor is V2.live_constructor is True
    assert V3.train_window is V2.train_window is None
    assert V3.universe == V2.universe == "sp500_pit"


# --- run_backtest_range ---------------------------------------------------------------

def test_rbr_instrument_frame_cuts_v3_at_research_end_like_v2():
    df = _frame()
    assert rbr._instrument_frame(df, V3).equals(rbr._instrument_frame(df, V2))
    assert rbr._instrument_frame(df, V3).index.max() <= RESEARCH_END
    assert rbr._instrument_frame(df, V1) is df


def test_rbr_windowed_trades_take_the_signal_day_gate_under_v3():
    crosses_out = _trade("2021-03-01", signal="2021-02-26")
    summary = SimpleNamespace(trades=[crosses_out])
    spans = [("2021-01-01", "2021-03-01")]
    for spec in (V2, V3):
        assert rbr._windowed_trades(summary, "2017-01-01", "2025-12-31", spans, _frame(), spec) \
            == [crosses_out]
    assert rbr._windowed_trades(summary, "2017-01-01", "2025-12-31", spans, _frame(), V1) == []


def test_rbr_guards_pin_the_universe_and_name_v3(live_flags_off):
    args = _args()
    rbr._instrument_guards(args, V3)
    assert args.universe == "sp500_pit"
    with pytest.raises(SystemExit) as exc:
        rbr._instrument_guards(_args(scenarios=True), V3)
    assert "--instrument v3" in str(exc.value)


def test_rbr_lists_a_missing_frame_under_v3_and_not_under_v1(capsys):
    assert rbr._missing_frames(["AAA", "BBB"], {"AAA": _frame()}, V3) == ["BBB"]
    assert rbr._missing_frames(["AAA", "BBB"], {"AAA": _frame()}, V1) == []


def test_rbr_instrument_report_names_v3(monkeypatch):
    monkeypatch.setattr(rbr, "load_watchlist", lambda: ["AAA"])
    lines, extra = rbr._instrument_report(V3, [], ["RSI"], ["AAA"])
    assert any("instrument v3: universe sp500_pit" in line for line in lines)
    assert set(extra) == {"_watchlist_slice"}
    assert rbr._instrument_report(V1, [], ["RSI"], ["AAA"]) == ([], {})


# --- tune_strategy --------------------------------------------------------------------

def test_tune_guards_refuse_the_v1_exit_loop_under_v3(live_flags_off):
    with pytest.raises(SystemExit, match="--instrument v3"):
        tune._instrument_guards(SimpleNamespace(exit_model="v1"), V3)
    assert tune._instrument_guards(SimpleNamespace(exit_model="v2"), V3) is None
    assert tune._instrument_guards(SimpleNamespace(exit_model="v1"), V1) is None


def test_tune_load_universe_takes_the_pit_path_under_v3(monkeypatch):
    seen = {}

    def tickers(universe, tickers_file=None):
        seen["universe"] = universe
        return ["AAA"]

    monkeypatch.setattr(rbr, "_tickers_for_run", tickers)
    monkeypatch.setattr(rbr, "_membership_for_run", lambda universe, symbols: {s: ALWAYS for s in symbols})
    monkeypatch.setattr(rbr, "_exclusion_reason", lambda df, ticker, pit: None)
    monkeypatch.setattr(tune, "load_cached", lambda ticker: _frame())
    frames, spans = tune._load_universe(V3)
    assert seen["universe"] == "sp500_pit"
    assert list(frames) == ["AAA"] and spans == {"AAA": ALWAYS}
    assert frames["AAA"].index.max() <= RESEARCH_END


def test_tune_evaluate_keeps_rows_under_v3(monkeypatch):
    rows = [("AAA", _trade("2021-02-02"))]
    monkeypatch.setattr(tune, "_v2_trades", lambda strategy, frames, spans, spec, scale_out: rows)
    stats, kept = tune._evaluate("RSI", ({}, {}), SimpleNamespace(exit_model="v2", scale_out=True), V3)
    assert kept == rows
    assert stats["n_eval"] == 1


def test_tune_fold_report_reports_v3(monkeypatch, capsys):
    monkeypatch.setattr(tune, "_out_of_fold",
                        lambda rows_by_config, spec: SimpleNamespace(trades=[], choices=[]))
    monkeypatch.setattr(tune, "_watchlist_slice", lambda trades, rows_by_config:
                        {"status": "thin", "n": 0, "expectancy_r": None})
    report = tune._fold_report([], {}, V3)
    assert report["instrument"] == "v3"
    assert report["research_span"] == ["2017-01-01", "2025-12-31"]
    assert tune._fold_report([], {}, V1) == {}


# --- engine, cli, contract, coverage --------------------------------------------------

def test_wf_exit_kwargs_give_v3_its_own_fills_and_costs():
    assert backtest_wf._exit_kwargs(V3) == {"exit_model": "v2", "scale_out": True,
                                            "tp2_mode": "none", "instrument": V3}
    assert backtest_wf._exit_kwargs(V1) == backtest_wf._exit_kwargs(None)


def test_cli_run_instrument_passes_v3_through():
    assert cli.run_instrument(V3) is V3
    assert cli.run_instrument(V1) is None


def test_cli_require_v1_refuses_v3():
    with pytest.raises(SystemExit, match="--instrument v3 is not wired yet"):
        cli.require_v1(V3, "x.py", "a later phase")


def test_exit_sim_routes_v3_to_the_v2_walk(monkeypatch):
    monkeypatch.setattr(exit_sim_v2, "simulate_exit_v2",
                        lambda df, signal_index, plan, instrument, **kwargs: ("v2-walk", instrument))
    assert exit_sim.simulate_exit(None, 0, SimpleNamespace(), instrument=V3) == ("v2-walk", V3)


def test_contract_builds_v3_through_the_live_constructor():
    assert V3.live_constructor is True
    assert V1.live_constructor is False


def test_uses_live_constructor_under_v3(live_flags_off):
    assert backtest._uses_live_constructor(V3, "v2", "none") is True
    with pytest.raises(ValueError, match="instrument v3 needs exit_model='v2'"):
        backtest._uses_live_constructor(V3, "v1", "none")
    with pytest.raises(ValueError, match="tp2_mode='levels'"):
        backtest._uses_live_constructor(V3, "v2", "levels")


def test_cli_windows_seal_the_v3_holdout():
    assert cli.window_for(V3, "train") == ("2017-01-01", "2025-12-31")
    with pytest.raises(SystemExit, match="holdout starts 2026-01-01"):
        cli.window_for(V3, "validation")
    with pytest.raises(SystemExit, match="research span"):
        cli.check_inside_research(V3, "2025-06-01", "2026-02-27")
    cli.check_inside_research(V3, "2021-01-04", "2021-12-31")


def test_coverage_members_follow_the_v3_research_span(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "universe").mkdir(parents=True)
    (data / "universe" / "sp500_membership.csv").write_text(
        "ticker,start_date,end_date\nAAA,2005-01-03,\nCCC,2012-03-01,2015-01-02\n"
        "DDD,2026-02-02,\n", encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    assert coverage.research_members(V3) == ["AAA"]
    assert coverage.research_members(V2) == ["AAA", "CCC"]
    with pytest.raises(ValueError, match="no point-in-time universe"):
        coverage.research_members(V1)


# --- what stays v2 alone, and the scripts that refuse v3 --------------------------------

def test_the_two_analytics_hard_codes_stay_v2_alone():
    assert override_fidelity.INSTRUMENT == V2
    assert '"instrument": "v2"' in inspect.getsource(override_verdict.mirror_ledger_row)
    for module in (override_fidelity, override_verdict):
        assert "v2 alone" in Path(module.__file__).read_text(encoding="utf-8")


@pytest.mark.parametrize("script", REQUIRE_V1_SCRIPTS)
def test_require_v1_scripts_keep_refusing_every_instrument_but_v1(script):
    tree = ast.parse((ROOT / "scripts" / "backtest" / f"{script}.py").read_text(encoding="utf-8"))
    called = {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
              for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert "require_v1" in called
