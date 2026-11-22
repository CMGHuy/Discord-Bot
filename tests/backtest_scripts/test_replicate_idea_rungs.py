"""v238 replicate_idea (V238-15): rungs 2-4 race the rung above's events, per ticker, resumably."""
import json

import pytest

import replicate_idea as ri  # on sys.path via conftest.py
import screen_idea

from swingbot.core.backtesting.screen import ladder, ladder_race
from swingbot.core.backtesting.screen.ideas import IDEAS
from swingbot.core.backtesting.screen.ladder import LadderEvent
from tests.backtest_scripts.test_replicate_idea import PASS_ROW, _args, _argv, _ladder_row, _ledger, _store

IDEA = IDEAS["turn_of_month"]            # fixed race, next-open entry, cap 4, long
POSITIONS = range(300, 1000, 35)         # 20 signal bars per ticker, all inside READ_END


def _upper(tmp_path, rung_above, tickers=("AAA", "BBB"), positions=POSITIONS):
    """A hand-made events file for the rung above (keys only matter to rungs 2-4)."""
    events = []
    for ticker in tickers:
        index = ri._frame(tmp_path / "store", ticker).index
        day = lambda p: index[p].strftime("%Y-%m-%d")  # noqa: E731
        events += [LadderEvent(ticker, day(p), day(p + 1), day(p + 4), 0.1, 0.1, "timeout",
                               r_null=0.0) for p in positions]
    ri.write_events(ri._events_path(tmp_path / "work", rung_above), events)
    return ri._sorted(events)


def _run(tmp_path, rung, *extra):
    return ri.run_rung(IDEA, rung, _args(tmp_path, *extra, rung=rung),
                       out=lambda *_a, **_k: None)


def test_rung_two_races_every_rung_one_event_from_the_signal_close(tmp_path):
    _store(tmp_path)
    upper = _upper(tmp_path, 1)
    run = _run(tmp_path, 2)
    assert [e.key for e in run.events] == [e.key for e in upper]
    assert run.counters["events_in"] == run.counters["raced"] == len(upper)
    gaps = [e for e in run.events if e.outcome in ladder_race.GAP_OUTCOMES]
    assert (run.gap_count, run.gap_r) == (len(gaps), pytest.approx(sum(e.r for e in gaps)))
    assert all(e.r_stress is not None and e.r_stress <= e.r + 1e-12 for e in run.events)
    assert run.survival is None and run.clamp_share is None and run.attrition is None
    assert run.risk_cap is None


def test_rung_two_checkpoints_each_ticker_and_resumes(tmp_path, monkeypatch):
    _store(tmp_path)
    _upper(tmp_path, 1)
    first = _run(tmp_path, 2)
    blob = json.loads(ri._ticker_checkpoint(tmp_path / "work", 2, "AAA").read_text(encoding="utf-8"))
    assert len(blob["signals"]) == len(POSITIONS) and blob["reasons"] == {}
    monkeypatch.setattr(ri, "_race_ticker", lambda *a, **k: pytest.fail("a finished ticker re-raced"))
    assert _run(tmp_path, 2).events == first.events


def test_a_tickers_smoke_run_keeps_its_checkpoints_apart_from_the_real_run(tmp_path, monkeypatch):
    _store(tmp_path)
    _upper(tmp_path, 1)
    smoke = _run(tmp_path, 2, "--tickers", "AAA")
    assert {e.ticker for e in smoke.events} == {"AAA"}
    assert ri._ticker_checkpoint(tmp_path / "work", 2, "AAA", smoke=True).is_file()
    assert not ri._ticker_checkpoint(tmp_path / "work", 2, "AAA").exists()
    raced, real = [], ri._race_ticker
    monkeypatch.setattr(ri, "_race_ticker",
                        lambda idea, rung, ticker, *a: raced.append(ticker) or real(idea, rung, ticker, *a))
    _run(tmp_path, 2)
    assert raced == ["AAA", "BBB"]                     # the smoke blob is never picked up
    assert ri._ticker_checkpoint(tmp_path / "work", 2, "AAA").is_file()


def test_a_checkpoint_from_other_events_is_refused(tmp_path):
    _store(tmp_path)
    _upper(tmp_path, 1)
    _run(tmp_path, 2)
    _upper(tmp_path, 1, positions=range(300, 1000, 70))
    with pytest.raises(RuntimeError, match="other rung 1 events"):
        _run(tmp_path, 2)


def test_a_signal_bar_missing_from_the_store_stops_the_run(tmp_path):
    _store(tmp_path, tickers=("AAA",))
    ri.write_events(ri._events_path(tmp_path / "work", 1), [LadderEvent(
        "AAA", "2017-03-04", "2017-03-06", "2017-03-09", 0.1, 0.1, "timeout")])   # a Saturday
    with pytest.raises(RuntimeError, match="not in the store frame"):
        _run(tmp_path, 2)


def test_rung_three_counts_no_stop_and_the_clamp_share(tmp_path, monkeypatch):
    _store(tmp_path, tickers=("AAA",))
    upper = _upper(tmp_path, 2, tickers=("AAA",))
    first = ri._frame(tmp_path / "store", "AAA").index.get_loc(upper[0].signal_date)

    def wide(df, pos, *, direction):            # 5% stops: sized down, never dropped
        close = float(df["Close"].iloc[pos])
        return (None, None) if pos == first else (close * 0.95, close * 1.10)

    monkeypatch.setattr(ri.ladder_bot, "rung3_levels", wide)
    run = _run(tmp_path, 3)
    assert run.counters["no_stop"] == 1 and run.counters["raced"] == len(upper) - 1
    assert run.clamp_share == pytest.approx(1.0)


def test_rung_three_live_adapter_keeps_every_event(tmp_path):
    _store(tmp_path, tickers=("AAA",))
    upper = _upper(tmp_path, 2, tickers=("AAA",))
    run = _run(tmp_path, 3)
    assert [e.key for e in run.events] == [e.key for e in upper]
    assert 0.0 <= run.clamp_share <= 1.0


def test_rung_four_reports_attrition_risk_cap_and_book_survival(tmp_path, monkeypatch):
    _store(tmp_path, tickers=("AAA",))
    upper = _upper(tmp_path, 3, tickers=("AAA",))
    index = ri._frame(tmp_path / "store", "AAA").index
    no_level = index.get_loc(upper[0].signal_date)
    wide = index.get_loc(upper[1].signal_date)

    def band(df, pos, *, direction):
        close = float(df["Close"].iloc[pos])
        if pos == no_level:
            return close * 0.99, None, "no_level_in_band"
        if pos == wide:                         # 5% stop: past the cap, still raced
            return close * 0.95, close * 1.10, None
        return close * 0.99, close * 1.02, None

    monkeypatch.setattr(ri.ladder_bot, "rung4_levels", band)
    run = _run(tmp_path, 4)
    assert run.attrition == {"no_level_in_band": 1, "no_stop": 0}
    assert run.counters["raced"] == len(upper) - 1 == len(run.events)
    assert upper[1].key in {e.key for e in run.events}
    assert run.risk_cap == {"count": 1, "share": pytest.approx(1 / (len(upper) - 1))}
    assert set(run.survival) == {"one_per_ticker_share", "concurrent_share",
                                 "signals_per_day_p95", "signals_per_day_max"}


def test_rung_four_races_every_wide_stop_and_counts_it_in_the_risk_cap_readout(tmp_path, monkeypatch):
    _store(tmp_path, tickers=("AAA",))
    upper = _upper(tmp_path, 3, tickers=("AAA",))

    def wide(df, pos, *, direction):            # every stop 5% away: sized down, never dropped
        close = float(df["Close"].iloc[pos])
        return close * 0.95, close * 1.10, None

    monkeypatch.setattr(ri.ladder_bot, "rung4_levels", wide)
    run = _run(tmp_path, 4)
    assert [e.key for e in run.events] == [e.key for e in upper]
    assert run.risk_cap == {"count": len(upper), "share": pytest.approx(1.0)}
    assert run.attrition == {"no_level_in_band": 0, "no_stop": 0}


def test_rung_four_live_adapter_accounts_for_every_event(tmp_path):
    _store(tmp_path, tickers=("AAA",))
    upper = _upper(tmp_path, 3, tickers=("AAA",), positions=range(300, 1000, 70))
    run = _run(tmp_path, 4)
    assert run.counters["raced"] + sum(run.attrition.values()) == len(upper)


def test_later_rungs_never_read_past_read_end(tmp_path, monkeypatch):
    _store(tmp_path)
    _upper(tmp_path, 1)
    ends, real = [], screen_idea.load_frame
    monkeypatch.setattr(screen_idea, "load_frame",
                        lambda path, start, end: ends.append(end) or real(path, start, end))
    _run(tmp_path, 2)
    assert ends and set(ends) == {ladder.READ_END}


def test_run_marker_allows_one_rerun_after_a_crash(tmp_path):
    directory = tmp_path / "rung1"
    first = ri.RunMarker(directory)
    assert first.start() is None and first.crash_note() is None
    again = ri.RunMarker(directory)                 # the first process died: running.json stays
    assert again.start() is None and "re-run once after a crash" in again.crash_note()
    crash = json.loads((directory / ri.CRASH_FILE).read_text(encoding="utf-8"))
    assert crash["crashed_run"]["started"]
    assert ri.RunMarker(directory).start().startswith("refused:")
    again.finish()
    assert not (directory / ri.RUNNING_FILE).exists()


def test_main_full_dry_run_rung_two_counts_and_writes_nothing(tmp_path, monkeypatch, capsys):
    _store(tmp_path)
    upper = _upper(tmp_path, 1)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW, _ladder_row(1, ladder.HOLD))
    monkeypatch.setattr(ri.ladder, "hold", lambda *a, **k: pytest.fail("a dry run read the outcome"))
    before = sorted(p.name for p in (tmp_path / "work").iterdir())
    assert ri.main(_argv(tmp_path, "--dry-run", rung=2)) == 0
    out = capsys.readouterr().out
    assert f"ladder-turn_of_month-r2 (dry run, no outcome read): {len(upper)} events" in out
    for text in ("mean", "lower", "gap-through", "# ladder-", "Next step", "minus rung"):
        assert text not in out, text
    assert sorted(p.name for p in (tmp_path / "work").iterdir()) == before
    assert not (tmp_path / "results").exists()


def test_main_smoke_rung_two_writes_events_and_checkpoints_under_smoke(tmp_path, capsys):
    _store(tmp_path)
    _upper(tmp_path, 1)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW, _ladder_row(1, ladder.HOLD))
    assert ri.main(_argv(tmp_path, "--dry-run", "--tickers", "AAA", rung=2)) == 0
    assert "# ladder-turn_of_month-r2" in capsys.readouterr().out
    assert {e.ticker for e in ri.read_events(ri._smoke_events_path(tmp_path / "work", 2))} == {"AAA"}
    assert not ri._events_path(tmp_path / "work", 2).exists()
    assert not (tmp_path / "work" / "rung2").exists() and not (tmp_path / "results").exists()


def test_rung_four_attriting_a_whole_ticker_races_nothing(tmp_path, monkeypatch):
    _store(tmp_path, tickers=("AAA",))
    upper = _upper(tmp_path, 3, tickers=("AAA",))
    monkeypatch.setattr(ri.ladder_bot, "rung4_levels",
                        lambda df, pos, *, direction: (None, None, "no_level_in_band"))
    run = _run(tmp_path, 4)
    assert run.events == [] and run.counters["raced"] == 0
    assert run.attrition == {"no_level_in_band": len(upper), "no_stop": 0}
    assert run.risk_cap == {"count": 0, "share": None}
