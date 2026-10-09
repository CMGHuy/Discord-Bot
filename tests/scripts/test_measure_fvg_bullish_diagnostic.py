"""v143 driver: refusals, the per-ticker collector, the population gate and
the render-from-rows path. No real replay runs here."""
import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_fvg_bullish_diagnostic as mf  # noqa: E402
from swingbot.core.backtesting import backtest_scenarios as bs  # noqa: E402
from swingbot.core.backtesting import fvg_diagnostic as fd  # noqa: E402
from swingbot.core.market.session import SessionCalendar  # noqa: E402
from swingbot.core.market.strategy_types import MIN_BARS  # noqa: E402
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df  # noqa: E402
from tests.backtesting.fvg_diagnostic_rows import row  # noqa: E402
from tests.helpers import make_ohlcv  # noqa: E402
from tests.planning.test_exit_sim_single import _plan  # noqa: E402

SCRIPT = ROOT / "scripts" / "backtest" / "measure_fvg_bullish_diagnostic.py"


class Scenario:
    """The four levels.Scenario attributes the driver reads."""
    take_profit = 123.0
    target_sources = ["FVG (bullish)", "EMA 50"]
    stop_loss = 95.0
    stop_sources = ["Swing Low"]


SCENARIO = Scenario()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Scratch out-dir, an earnings dir with one CSV, logs under tmp."""
    earnings = tmp_path / "earnings"
    earnings.mkdir()
    (earnings / "AAA.csv").write_text("report_date,timing,report_ts_et\n", encoding="utf-8")
    monkeypatch.setattr(mf, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(mf, "PROGRESS", tmp_path / "logs" / "p.progress")
    monkeypatch.setattr(mf, "enabled_arms", lambda: ())
    out = tmp_path / "out"
    return {"out": out, "earnings": earnings,
            "argv": ["--date", "2026-10-10", "--out-dir", str(out),
                     "--earnings-dir", str(earnings)]}


def test_the_script_has_a_main_guard():
    """Windows spawns pool workers by re-importing the script; without the
    guard every worker would start its own replay."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    guards = [node for node in tree.body if isinstance(node, ast.If)
              and "__main__" in ast.unparse(node.test)]
    assert len(guards) == 1


def test_ticker_rows_keeps_fvg_bullish_plans_inside_train(monkeypatch):
    bars = [100.0, 100.0, (100.0, 111.0, 99.5, 110.5), 110.0]
    frame = make_ohlcv(bars, start="2021-03-01")           # signal bar 1 = 2021-03-02
    fvg_plan = _plan(strategy=fd.STRATEGY, source="confluence")
    other = _plan(strategy="Fib 38.2%", source="confluence")
    unfilled = _plan(strategy=fd.STRATEGY, source="confluence", entry_type="stop_entry",
                     trigger_price=500.0)
    monkeypatch.setattr(mf, "replay_with_scenarios", lambda ticker, f, hk: [
        (1, fvg_plan, SCENARIO, 0), (1, other, SCENARIO, 0), (1, unfilled, SCENARIO, 0)])
    seen = []
    monkeypatch.setattr(fd, "target_confluence_count",
                        lambda df, i, hk, target, tol: seen.append((i, hk, target, tol)) or 3)
    calendar = SessionCalendar.from_bar_index(frame.index)
    rows, others = mf.ticker_rows("AAA", frame, [0, 3], calendar, 2.0, horizons=("2w",))
    assert seen[0] == (1, "2w", 123.0, 2.0)                 # the SCENARIO target, live tolerance
    assert isinstance(rows[0]["features"]["quality"], int)  # scored, not the replay's 0
    assert len(rows) == 1 and others == 1                   # the unfilled plan is no trade
    assert rows[0]["signal_date"] == "2021-03-02"
    assert rows[0]["features"]["earnings_distance"] == 2    # reaction at session 3
    assert rows[0]["outcomes"]["live"]["outcome"] == "win"
    late = make_ohlcv(bars, start="2024-01-02")             # VALIDATION dates: never kept
    assert mf.ticker_rows("AAA", late, [], SessionCalendar.from_bar_index(late.index), 2.0,
                          horizons=("2w",)) == ([], 0)


def test_signal_context_carries_the_scenario_levels_and_sources(monkeypatch):
    frame = make_ohlcv([100.0, 100.0, 100.0, 100.0], start="2021-03-01")
    monkeypatch.setattr(fd, "target_confluence_count", lambda *a: 4)
    calendar = SessionCalendar.from_bar_index(frame.index)
    context = mf.signal_context(frame, 1, _plan(), (SCENARIO, 0), ([0, 3], calendar, 5.0))
    assert context == fd.SignalContext(
        target=123.0, target_sources=("FVG (bullish)", "EMA 50"), stop=95.0,
        stop_sources=("Swing Low",), tolerance_pct=5.0, map_bar=0, earnings_distance=2,
        confluence_count=4)


def test_replay_with_scenarios_restores_both_wrapped_functions(monkeypatch):
    built = _plan(strategy=fd.STRATEGY, source="confluence")

    def builder(scenario, window, **kwargs):
        return built

    def fake_asof(ticker, df, bar_index, horizon_key, cache):
        cache.setdefault(bar_index // 5, bar_index)
        return [], []

    def fake_replay(ticker, frame, hk):
        cache: dict = {}
        for bar in (12, 13, 14, 15, 16):             # maps are built at 12 and at 15
            bs.levels_asof(ticker, frame, bar, hk, cache)
        return [(16, bs.build_confluence_plan(SCENARIO, frame, ticker=ticker))]

    monkeypatch.setattr(bs, "build_confluence_plan", builder)
    monkeypatch.setattr(bs, "levels_asof", fake_asof)
    monkeypatch.setattr(bs, "replay_scenarios", fake_replay)
    assert mf.replay_with_scenarios("AAA", None, "2w") == [(16, built, SCENARIO, 15)]
    assert bs.build_confluence_plan is builder and bs.levels_asof is fake_asof

    def boom(ticker, frame, hk):
        raise RuntimeError("replay died")

    monkeypatch.setattr(bs, "replay_scenarios", boom)
    with pytest.raises(RuntimeError):
        mf.replay_with_scenarios("AAA", None, "2w")
    assert bs.build_confluence_plan is builder and bs.levels_asof is fake_asof


def test_the_map_bar_is_the_bar_the_real_replay_built_its_level_map_on(monkeypatch):
    """Pinned against replay_scenarios itself. Its loop asks levels_asof for
    every bar from MIN_BARS on, and the cache is keyed by bar // 5, so a map
    is built on the warm-up bar and then on every multiple of 5. A spy on
    levels.build_level_map confirms a map really was built on each map_bar."""
    built_on = set()
    real = bs.levels.build_level_map

    def spying(window, h, price, *args, **kwargs):
        built_on.add(len(window) - 1)
        return real(window, h, price, *args, **kwargs)

    monkeypatch.setattr(bs.levels, "build_level_map", spying)
    out = mf.replay_with_scenarios("AAPL", _structured_df(), "4w", gates=GATES)
    assert out, "fixture must produce at least one plan"
    refresh = bs.LEVEL_REFRESH_BARS
    for i, plan, scenario, map_bar in out:
        assert map_bar == max(MIN_BARS["4w"], refresh * (i // refresh))
        assert map_bar <= i and map_bar in built_on
        assert scenario.direction == plan.direction
    assert {i - map_bar for i, _plan_, _scenario, map_bar in out} - {0}, "no stale map exercised"


def test_smoke_run_refuses_the_results_directory(env, capsys):
    assert mf.main(["--tickers", "2", "--earnings-dir", str(env["earnings"])]) == 2
    assert "refused:smoke-run" in capsys.readouterr().err


def test_refuses_without_earnings_csvs(env, tmp_path, capsys):
    empty = tmp_path / "none"
    empty.mkdir()
    assert mf.main(["--date", "2026-10-10", "--out-dir", str(env["out"]),
                    "--earnings-dir", str(empty)]) == 2
    assert "refused:no-earnings" in capsys.readouterr().err


def test_refuses_when_an_acceptance_arm_is_enabled(env, monkeypatch, capsys):
    monkeypatch.setattr(mf, "enabled_arms", lambda: ("Z",))
    assert mf.main(env["argv"]) == 2
    assert "refused:acceptance-exit-enabled" in capsys.readouterr().err


def test_a_population_off_by_more_than_two_percent_writes_no_document(env, monkeypatch, capsys):
    monkeypatch.setattr(mf, "run_replay", lambda universe, earnings_dir, workers=None: {
        "rows": [row()] * 3, "other_triggered": 5, "tickers": 1,
        "confluence_tolerance_pct": 2.0})
    monkeypatch.setattr("measure_acceptance_exits.cache_universe", lambda: ["AAA"])
    assert mf.main(env["argv"]) == 2
    captured = capsys.readouterr()
    assert "population: N=3 FVG (bullish) of 8 triggered confluence plans" in captured.out
    assert "refused:population" in captured.err
    assert not mf.doc_path(env["out"], "2026-10-10").exists()
    assert json.loads(mf.rows_path(env["out"]).read_text(encoding="utf-8"))["tickers"] == 1


def test_the_replay_never_runs_twice(env, monkeypatch, capsys):
    env["out"].mkdir()
    mf.rows_path(env["out"]).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(mf, "run_replay", lambda *a, **k: pytest.fail("replayed twice"))
    assert mf.main(env["argv"]) == 2
    assert "refused:already-run" in capsys.readouterr().err


def test_from_rows_renders_without_replaying(env, monkeypatch, tmp_path, capsys):
    saved = tmp_path / "rows.json"
    rows = [row(year) for year in fd.YEARS for _ in range(320)]       # 1280: inside 2%
    saved.write_text(json.dumps({"rows": rows, "other_triggered": 6800, "tickers": 75,
                                 "confluence_tolerance_pct": 2.0}), encoding="utf-8")
    monkeypatch.setattr(mf, "run_replay", lambda *a, **k: pytest.fail("replayed"))
    assert mf.main(env["argv"] + ["--from-rows", str(saved)]) == 0
    doc = mf.doc_path(env["out"], "2026-10-10")
    text = doc.read_text(encoding="utf-8")
    assert "**Population N = 1280** (expected 1278)" in text
    assert "within 2% of the scenario target" in text
    out = capsys.readouterr().out
    assert f"-> {doc}" in out and "27 looks" in out
    assert ("coverage: unidentified=0 of 1280; role target=1280 stop=0; "
            "gap open=1280 filled=0; computable: gap_age 100.0%") in out
    assert mf.main(env["argv"] + ["--from-rows", str(saved)]) == 2     # the doc now exists
    assert "refused:already-written" in capsys.readouterr().err


def test_run_replay_is_ticker_ordered_and_clears_its_progress_file(env, monkeypatch, capsys):
    monkeypatch.setattr(mf, "_worker", lambda task: (task[0], [{"t": task[0]}], 2))
    blob = mf.run_replay(["BBB", "AAA"], env["earnings"], workers=1)
    tolerance = blob.pop("confluence_tolerance_pct")
    assert tolerance == float(mf.ScanParams.from_config().confluence_deviation_pct)
    assert blob == {"rows": [{"t": "AAA"}, {"t": "BBB"}], "other_triggered": 4, "tickers": 2}
    assert not mf.PROGRESS.exists()
    assert "1/2 BBB: 1 FVG (bullish) trades, 2 other" in capsys.readouterr().out


def test_rows_file_never_lands_in_the_results_directory(tmp_path):
    assert mf.rows_path(mf.RESULTS) == mf.LOG_DIR / mf.ROWS_NAME
    assert mf.rows_path(tmp_path) == tmp_path / mf.ROWS_NAME
