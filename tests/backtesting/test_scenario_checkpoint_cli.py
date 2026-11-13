"""v226 V226-4/4b: --trades-jsonl checkpointing. Each finished ticker's rows
and a done-list line reach disk as it completes; a restart with the same
arguments replays only the rest, and the rows and the rebuilt table equal an
uninterrupted run."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.market.strategy_types import LEGACY_HORIZONS
from swingbot.core.marketdata import training_data
from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import run_backtest_range as rr  # noqa: E402

HK1, HK2 = LEGACY_HORIZONS[0], LEGACY_HORIZONS[1]
TICKERS = ["AAA", "BBB", "CCC"]


def _exit(outcome, r_total=0.0, runner=None):
    return SimpleNamespace(outcome=outcome, runner_outcome=runner, r_total=r_total)


FAKE_EXITS = {
    "AAA": {HK1: [_exit("win", 2.5, "tp2"), _exit("not_triggered")], HK2: [_exit("loss", -1.0)]},
    "BBB": {HK1: [_exit("not_triggered"), _exit("not_triggered")], HK2: []},   # no rows, still done
    "CCC": {HK1: [_exit("scratch", 0.1)],
            HK2: [_exit("timeout", -0.3), _exit("win", 1.75, "runner_stop")]},
}


def _rows(ticker):
    return [{"ticker": ticker, "horizon_key": hk, "outcome": e.outcome,
             "runner_outcome": e.runner_outcome, "r_total": e.r_total}
            for hk, exits in FAKE_EXITS[ticker].items() for e in exits
            if e.outcome != "not_triggered"]


def _lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


@pytest.fixture(autouse=True)
def _legacy_source(monkeypatch):
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    yield
    training_data.reset()


@pytest.fixture(autouse=True)
def _fixed_run(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_backtest_range.py", "--scenarios", "--train",
                                      "--trades-jsonl", "out/rows.jsonl"])
    monkeypatch.setattr(rr, "_git_head", lambda: "c" * 40)
    monkeypatch.setattr(rr, "_utc_today", lambda: "2026-11-12")


def _sidecar(**over):
    kwargs = dict(date_from="2020-01-06", date_to="2023-12-29", tickers=list(TICKERS),
                  universe=None, membership=None, argv=sys.argv[1:], today=rr._utc_today())
    kwargs.update(over)
    return rr.run_sidecar(**kwargs)


def _write(target, tickers=TICKERS):
    writer = rr._checkpoint_writer(target)
    for ticker in tickers:
        writer(ticker, FAKE_EXITS[ticker], _rows(ticker))


# --- helpers (V226-4) -----------------------------------------------------------

def test_the_writer_appends_rows_then_a_done_line_per_ticker(tmp_path):
    target = tmp_path / "rows.jsonl"

    _write(target)

    assert _lines(target) == [row for ticker in TICKERS for row in _rows(ticker)]
    assert _lines(rr._done_path(target)) == [
        {"ticker": "AAA", "rows": 2, "not_triggered": {HK1: 1, HK2: 0}},
        {"ticker": "BBB", "rows": 0, "not_triggered": {HK1: 2, HK2: 0}},
        {"ticker": "CCC", "rows": 3, "not_triggered": {HK1: 0, HK2: 0}}]


def test_the_rebuilt_table_equals_the_aggregate_of_every_exit(tmp_path):
    target = tmp_path / "rows.jsonl"
    _write(target)
    by_hz = {hk: [] for hk in LEGACY_HORIZONS}
    for ticker in TICKERS:
        for hk, exits in FAKE_EXITS[ticker].items():
            by_hz[hk].extend(exits)
    every = [result for results in by_hz.values() for result in results]

    stats = rr._stats_from_checkpoint(target, list(LEGACY_HORIZONS))

    assert stats == {"pooled": bs._aggregate(every),
                     "by_horizon": {hk: bs._aggregate(rs) for hk, rs in by_hz.items()}}


def test_a_fresh_start_empties_stale_rows_and_writes_the_sidecar(tmp_path):
    target = tmp_path / "out" / "rows.jsonl"
    target.parent.mkdir()
    target.write_text('{"ticker": "OLD"}\n', encoding="utf-8")
    sidecar = _sidecar()

    assert rr._resume_checkpoint(target, sidecar) == {}
    assert target.read_text(encoding="utf-8") == ""
    assert json.loads(rr._run_sidecar_path(target).read_text(encoding="utf-8")) == sidecar


def test_a_resume_keeps_only_done_tickers_and_cuts_half_written_tails(tmp_path):
    target, full = tmp_path / "rows.jsonl", tmp_path / "full.jsonl"
    rr._resume_checkpoint(target, _sidecar())                 # fresh start writes the sidecar
    _write(target, ["AAA"])
    with target.open("a", encoding="utf-8") as handle:        # BBB's rows flushed, done line not
        handle.write(json.dumps({"ticker": "BBB", "horizon_key": HK1}) + "\n" + '{"ticker": "BB')
    with rr._done_path(target).open("a", encoding="utf-8") as handle:
        handle.write('{"ticker": "BB')

    done = rr._resume_checkpoint(target, _sidecar())

    assert list(done) == ["AAA"] and done["AAA"]["rows"] == 2
    assert _lines(target) == _rows("AAA")
    assert _lines(rr._done_path(target)) == [done["AAA"]]
    _write(target, ["BBB", "CCC"])                             # appends cleanly after the cut
    _write(full)
    assert target.read_bytes() == full.read_bytes()
    assert rr._done_path(target).read_bytes() == rr._done_path(full).read_bytes()


@pytest.mark.parametrize("change", ["window", "command", "stop_setting", "no_sidecar"])
def test_a_done_list_from_another_run_is_refused(tmp_path, monkeypatch, change):
    target = tmp_path / "rows.jsonl"
    rr._resume_checkpoint(target, _sidecar())
    _write(target, ["AAA"])
    before = (target.read_bytes(), rr._done_path(target).read_bytes())
    over = {"window": {"date_to": "2022-12-30"},
            "command": {"argv": ["--scenarios", "--validation"]}}.get(change, {})
    if change == "stop_setting":
        monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 9.9)
    if change == "no_sidecar":
        rr._run_sidecar_path(target).unlink()

    with pytest.raises(SystemExit) as exc:
        rr._resume_checkpoint(target, _sidecar(**over))

    assert exc.value.code == 2
    assert (target.read_bytes(), rr._done_path(target).read_bytes()) == before


def test_a_resume_on_another_day_ignores_membership_asof(tmp_path):
    target = tmp_path / "rows.jsonl"
    first = _sidecar()
    rr._resume_checkpoint(target, first)
    _write(target, ["AAA"])

    assert list(rr._resume_checkpoint(target, _sidecar(today="2026-11-13"))) == ["AAA"]
    assert json.loads(rr._run_sidecar_path(target).read_text(encoding="utf-8")) == first
    assert "membership_asof" not in rr.RESUME_KEYS


GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def _structured_df():
    """Trend up, then a 60-bar box (test_scenario_trade_rows_cli.py's fixture)."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


@pytest.mark.slow
def test_the_rebuilt_table_equals_the_real_replays_own_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", False)
    spy = make_ohlcv([300.0 + 0.1 * k for k in range(500)], start="2023-01-02")
    target = tmp_path / "rows.jsonl"

    stats = bs.run_scenario_backtest({"AAPL": _structured_df()}, None, None, gates=GATES,
                                     horizons=["4w"], workers=1, spy_df=spy, collect_rows=True,
                                     on_ticker_result=rr._checkpoint_writer(target))

    assert stats["rows"], "fixture must close at least one trade"
    assert rr._stats_from_checkpoint(target, ["4w"]) == {"pooled": stats["pooled"],
                                                          "by_horizon": stats["by_horizon"]}
    assert _lines(target) == json.loads(json.dumps(stats["rows"], default=rr._jsonable))
