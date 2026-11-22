"""v238 replicate_idea (V238-16): results docs, ledger rows, the run marker and the next step."""
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

import replicate_idea as ri  # on sys.path via conftest.py

from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import ladder
from swingbot.core.backtesting.screen.ideas import IDEAS
from swingbot.core.backtesting.screen.ladder import LadderEvent
from tests.backtest_scripts.test_replicate_idea import PASS_ROW, _args, _argv, _ladder_row, _ledger, _store

IDEA = IDEAS["turn_of_month"]
DAY = pd.Timedelta(days=1)


def _events(r=0.5):
    """320 events: eight tickers on 40 Mondays, 2019-09 into 2020."""
    mondays = pd.date_range("2019-09-02", periods=40, freq="W-MON")
    return [LadderEvent(f"T{i}", d.strftime("%Y-%m-%d"), (d + DAY).strftime("%Y-%m-%d"),
                        (d + 3 * DAY).strftime("%Y-%m-%d"), r, r, "timeout", r_null=0.0,
                        r_stress=r - 0.01) for i in range(8) for d in mondays]


def _run(r=0.5, **readouts):
    return ri.RungRun(_events(r), Counter(raced=320), **readouts)


def test_results_path_names_the_rung():
    assert ri.results_path(Path("r"), "turn_of_month", 3, "2026-11-20").name == \
        "2026-11-20-ladder-turn_of_month-r3.md"


def test_ledger_row_is_valid_and_flags_the_v1_null():
    hold = ladder.hold(_events(), rung=1, n_resamples=500)
    row = ri.ledger_row(IDEA, 1, hold, Path("x.md"), "2026-11-20", input_instrument="screen-v1")
    stats.validate_ledger_row(row)
    assert (row["instrument"], row["data_source"], row["verdict"]) == ("ladder-v1", "alpaca", ladder.HOLD)
    assert (row["n"], row["exp_r"], row["p"]) == (320, 0.5, 0.0)
    assert ladder.BIASED_NULL_NOTE in row["hypothesis"] and "screen-v1 SCREEN-PASS" in row["hypothesis"]
    later = ri.ledger_row(IDEA, 2, ladder.hold(_events(), rung=2, n_resamples=500), Path("x.md"),
                          "2026-11-20", input_instrument="screen-v2")
    assert "biased" not in later["hypothesis"]


def test_rung_one_doc_prints_the_year_alone_the_null_and_the_disclaimers():
    hold = ladder.hold(_events(), rung=1, n_resamples=500)
    text = ri.render_rung(IDEA, 1, _run(), hold, watchlist={"n": 40, "mean": 0.5},
                          date="2026-11-20", input_instrument="screen-v1")
    for needle in (f"{ri.FINAL_YEAR} alone: N = ", ladder.BIASED_NULL_NOTE, "Input flag",
                   "Watchlist subset", "Not an independent replication", "Gap-through fills",
                   "2 x slippage", "LADDER-HOLD"):
        assert needle in text
    soup = ri.render_rung(IDEAS["turtle_soup"], 1, _run(), hold, date="2026-11-20")
    assert "-0.046R" in soup


def test_rung_three_and_four_docs_print_the_bot_shape_and_readouts():
    events = _events()
    hold = ladder.hold(events, rung=3, n_resamples=500)
    diff = ladder.paired_difference(events, events, n_resamples=200)
    three = ri.render_rung(IDEA, 3, _run(clamp_share=0.25), hold, diff=diff, date="2026-11-20")
    assert ri.ladder_bot.BOT_SHAPE["stop_entry_point"] in three and "25.0%" in three
    assert "Paired difference to the rung above" in three
    survival = {"one_per_ticker_share": 0.5, "concurrent_share": 0.4,
                "signals_per_day_p95": 8.0, "signals_per_day_max": 8}
    four = ri.render_rung(IDEA, 4, _run(attrition={"no_level_in_band": 3, "no_stop": 0},
                                        risk_cap={"count": 8, "share": 0.025},
                                        survival=survival), hold, diff=diff, date="2026-11-20")
    assert "no_level_in_band 3, no_stop 0" in four and "Book survival" in four
    assert "risk_cap (never gating): 8 raced events (2.5%)" in four
    assert "never dropped" in four


def test_publish_dry_run_prints_and_writes_nothing(tmp_path, capsys):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    (tmp_path / "watch.txt").write_text("T0\n", encoding="utf-8")
    assert ri.publish(_args(tmp_path, "--dry-run", "--tickers", "T0",
                            "--watchlist", str(tmp_path / "watch.txt")),
                      IDEA, 1, _run()) == 0
    out = capsys.readouterr().out
    assert "# ladder-turn_of_month-r1" in out and ladder.NEXT_STEPS["pending"] in out
    assert "Watchlist subset (never gating): N = 40" in out and "3/3 members in the store" in out
    assert not (tmp_path / "results").exists()
    assert len(stats.load_ledger(tmp_path / "ledger.jsonl")) == 1


def test_publish_writes_the_doc_before_the_row(tmp_path, monkeypatch):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    doc = ri.results_path(tmp_path / "results", "turn_of_month", 1, "2026-11-20")
    seen, real = [], stats.append_ledger_row
    monkeypatch.setattr(ri.stats, "append_ledger_row",
                        lambda row, path: seen.append(doc.is_file()) or real(row, path=path))
    assert ri.publish(_args(tmp_path), IDEA, 1, _run()) == 0
    assert seen == [True]
    assert stats.load_ledger(tmp_path / "ledger.jsonl")[-1]["id"] == "ladder-turn_of_month-r1"


def test_a_failed_rung_one_closes_the_idea(tmp_path, capsys):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    ri.publish(_args(tmp_path, "--dry-run", "--tickers", "T0"), IDEA, 1, _run(r=-0.1))
    assert ladder.NEXT_STEPS["non_replication"] in capsys.readouterr().out


def test_rung_four_names_the_shape_from_its_difference_to_rung_two(tmp_path, capsys):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW, *(_ladder_row(r, ladder.HOLD) for r in (1, 2, 3)))
    for rung in (2, 3):
        ri.write_events(ri._events_path(tmp_path / "work", rung), _events(0.6))
    args = _args(tmp_path, "--dry-run", "--tickers", "T0", rung=4)
    assert ri.publish(args, IDEA, 4, _run(0.6)) == 0
    out = capsys.readouterr().out
    assert ladder.NEXT_STEPS["bot_shape"] in out and "Rung 4 minus rung 2 on 320 shared events" in out
    assert ri.publish(args, IDEA, 4, _run(0.4)) == 0           # holds, but wholly below rung 2
    assert ladder.NEXT_STEPS["orderable_shape"] in capsys.readouterr().out


def test_main_publishes_records_the_crash_and_spends_the_shot(tmp_path, monkeypatch, capsys):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    monkeypatch.setattr(ri, "run_rung", lambda idea, rung, args: _run())
    ri._write_json(tmp_path / "work" / "rung1" / ri.RUNNING_FILE, {"started": "earlier"})
    assert ri.main(_argv(tmp_path)) == 0
    doc = ri.results_path(tmp_path / "results", "turn_of_month", 1, "2026-11-20")
    assert "re-run once after a crash" in doc.read_text(encoding="utf-8")
    assert not (tmp_path / "work" / "rung1" / ri.RUNNING_FILE).exists()
    assert (tmp_path / "work" / "rung1-events.json").is_file()
    assert ri.main(_argv(tmp_path)) == 2
    assert "one shot per id" in capsys.readouterr().err


def test_publish_refuses_a_full_universe_dry_run(tmp_path, monkeypatch):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    monkeypatch.setattr(ri.ladder, "hold", lambda *a, **k: pytest.fail("a dry run read the outcome"))
    with pytest.raises(RuntimeError, match="no outcome"):
        ri.publish(_args(tmp_path, "--dry-run"), IDEA, 1, _run())


def test_a_crashed_smoke_run_never_reaches_the_real_runs_doc(tmp_path, monkeypatch):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    smoke = ri._run_dir(tmp_path / "work", 1, smoke=True)
    ri._write_json(smoke / ri.RUNNING_FILE, {"started": "earlier"})
    ri._write_json(smoke / ri.CRASH_FILE, {"crashed_run": {"started": "earlier"}})
    monkeypatch.setattr(ri, "run_rung", lambda idea, rung, args: _run())
    assert ri.main(_argv(tmp_path)) == 0
    doc = ri.results_path(tmp_path / "results", "turn_of_month", 1, "2026-11-20")
    assert "crash" not in doc.read_text(encoding="utf-8").lower()
