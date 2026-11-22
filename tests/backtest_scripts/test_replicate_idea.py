"""v238 replicate_idea (V238-14): refusals, the events file and rung 1."""
import json
import math
from types import SimpleNamespace

import pytest

import replicate_idea as ri  # on sys.path via conftest.py
import screen_idea

from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import ladder
from swingbot.core.backtesting.screen.ideas import IDEAS
from swingbot.core.backtesting.screen.ladder import LadderEvent
from tests.backtesting.screen.helpers import random_walk

IDEA = SimpleNamespace(name="turn_of_month", race_shape="fixed", entry="next_open", context=())
PASS_ROW = {"id": "screen-turn_of_month", "date": "2026-11-01", "hypothesis": "fixture pass",
            "instrument": "screen-v1", "n": 400, "exp_r": 0.2, "p": 0.01,
            "verdict": "SCREEN-PASS", "record": "docs/superpowers/results/fixture.md"}


def _ladder_row(rung, verdict):
    return {**PASS_ROW, "id": ladder.ladder_id("turn_of_month", rung),
            "instrument": "ladder-v1", "verdict": verdict, "data_source": "alpaca"}


def _ledger(path, *rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _store(tmp_path, tickers=("AAA", "BBB", "DDD"), extra_members=()):
    store = tmp_path / "store"
    store.mkdir()
    for seed, ticker in enumerate(tickers, start=1):
        random_walk(1300, seed=seed, start=ladder.STORE_START).rename_axis("Date").to_csv(
            store / f"{ticker}.csv")
    (tmp_path / "membership.csv").write_text("ticker,start_date,end_date\n" + "".join(
        f"{t},2000-01-01,\n" for t in (*tickers, *extra_members)), encoding="utf-8")
    return store


def _argv(tmp_path, *extra, rung=1):
    return ["--idea", "turn_of_month", "--rung", str(rung), "--work-dir", str(tmp_path / "work"),
            "--store", str(tmp_path / "store"), "--membership", str(tmp_path / "membership.csv"),
            "--ledger", str(tmp_path / "ledger.jsonl"), "--results-dir", str(tmp_path / "results"),
            "--date", "2026-11-20", *extra]


def _args(tmp_path, *extra, rung=1):
    return ri.build_parser().parse_args(_argv(tmp_path, *extra, rung=rung))


def _quiet(lines):
    return lambda message, **_kw: lines.append(message)


def test_parser_defaults():
    args = ri.build_parser().parse_args(["--idea", "turn_of_month", "--rung", "1"])
    assert args.store == ri.DEFAULT_STORE and args.store.parts[-2:] == ("market_data_pit", "daily")
    assert ri._work(args).parts[-2:] == ("ladder", "turn_of_month")


def test_input_rung_order_and_one_shot_refusals(tmp_path):
    _store(tmp_path)
    assert "SCREEN-PASS" in ri.refusals(_args(tmp_path, "--dry-run"), IDEA, [])
    assert ri.refusals(_args(tmp_path, "--dry-run"), IDEA, [PASS_ROW]) is None
    spent = [PASS_ROW, _ladder_row(1, ladder.FAIL)]
    assert "one shot per id" in ri.refusals(_args(tmp_path), IDEA, spent)
    above = ri.refusals(_args(tmp_path, "--dry-run", rung=2), IDEA, [PASS_ROW])
    assert "needs LADDER-HOLD on ladder-turn_of_month-r1" in above


def test_shape_store_and_context_refusals(tmp_path):
    assert "does not exist" in ri.refusals(_args(tmp_path, "--dry-run"), IDEA, [PASS_ROW])
    _store(tmp_path)
    trail = SimpleNamespace(**{**vars(IDEA), "race_shape": "trail"})
    rows = [PASS_ROW, _ladder_row(1, ladder.HOLD)]
    assert ri.refusals(_args(tmp_path, "--dry-run", rung=2), trail, rows).startswith(ladder.UNAVAILABLE)
    dollar = SimpleNamespace(**{**vars(IDEA), "context": ("UUP",)})
    reason = ri.refusals(_args(tmp_path, "--dry-run"), dollar, [PASS_ROW])
    assert reason.startswith(ladder.UNAVAILABLE) and "UUP" in reason


def test_smoke_written_result_and_events_refusals(tmp_path):
    _store(tmp_path)
    assert "--dry-run" in ri.refusals(_args(tmp_path, "--tickers", "AAA"), IDEA, [PASS_ROW])
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "2026-11-19-ladder-turn_of_month-r1.md").write_text("x", encoding="utf-8")
    assert "exists without a ledger row" in ri.refusals(_args(tmp_path), IDEA, [PASS_ROW])
    rows, args = [PASS_ROW, _ladder_row(1, ladder.HOLD)], _args(tmp_path, "--dry-run", rung=2)
    assert "rung1-events.json" in ri.refusals(args, IDEA, rows)
    ri.write_events(ri._events_path(tmp_path / "work", 1), [])
    assert ri.refusals(args, IDEA, rows) is None


def test_main_refuses_on_stderr_and_writes_nothing(tmp_path, capsys):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl")
    assert ri.main(_argv(tmp_path, "--dry-run")) == 2
    assert "SCREEN-PASS" in capsys.readouterr().err
    assert not (tmp_path / "work").exists() and not (tmp_path / "results").exists()


def test_events_round_trip_with_nan_gross_and_no_stress(tmp_path):
    events = [LadderEvent("AAA", "2017-03-01", "2017-03-02", "2017-03-08", -0.5, math.nan,
                          "timeout", r_null=0.1),
              LadderEvent("BBB", "2017-03-01", "2017-03-02", "2017-03-03", 2.0, 2.01,
                          "target", r_stress=1.98)]
    path = tmp_path / "w" / "rung1-events.json"
    ri.write_events(path, events)
    back = ri.read_events(path)
    assert [e.key for e in back] == [e.key for e in events]
    assert math.isnan(back[0].gross_r) and back[1] == events[1]
    assert b"\r" not in path.read_bytes()


def test_rung_one_races_the_screen_and_checkpoints_it(tmp_path, monkeypatch):
    _store(tmp_path)
    ends, real = [], screen_idea.load_frame
    monkeypatch.setattr(screen_idea, "load_frame",
                        lambda path, start, end: ends.append(end) or real(path, start, end))
    lines = []
    events = ri.run_rung(IDEAS["turn_of_month"], 1, _args(tmp_path), out=_quiet(lines)).events
    assert len(events) > 50 and events == ri._sorted(events)
    assert all(ladder.EVENT_START <= e.signal_date < e.entry_date <= e.exit_date <= ladder.READ_END
               for e in events)
    assert all(e.r_null is not None and math.isfinite(e.gross_r) for e in events)
    assert all(e.r_stress is not None and e.r_stress <= e.r + 1e-12 for e in events)
    assert set(ends) == {ladder.READ_END}
    assert any((tmp_path / "work" / "rung1" / "screen").glob("*.pkl"))
    assert any("3/3 members in the store" in line for line in lines)


def _no_outcome(out):
    """A full-universe dry run prints counts only: no doc, no R figure, no verdict."""
    low = out.lower()
    for text in ("# ladder-", "## next step", "mean", "lower", "gap-through", "verdict",
                 ladder.HOLD.lower(), "paired", "minus rung"):
        assert text not in low, text


def test_a_full_universe_dry_run_reads_no_outcome_and_writes_nothing(tmp_path, monkeypatch, capsys):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    monkeypatch.setattr(ri.ladder, "hold", lambda *a, **k: pytest.fail("a dry run read the outcome"))
    assert ri.main(_argv(tmp_path, "--dry-run")) == 0
    out = capsys.readouterr().out
    _no_outcome(out)
    assert "3/3 members in the store" in out and "ladder-turn_of_month-r1 (dry run" in out
    assert "events" in out
    assert not (tmp_path / "work").exists() and not (tmp_path / "results").exists()
    assert len(stats.load_ledger(tmp_path / "ledger.jsonl")) == 1


def test_a_full_dry_run_leaves_no_events_for_rung_two(tmp_path):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    assert ri.main(_argv(tmp_path, "--dry-run")) == 0
    rows = [PASS_ROW, _ladder_row(1, ladder.HOLD)]
    assert "rung1-events.json" in ri.refusals(_args(tmp_path, "--dry-run", rung=2), IDEA, rows)


def test_a_smoke_run_writes_its_events_apart_and_rung_two_refuses_them(tmp_path, capsys):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    assert ri.main(_argv(tmp_path, "--dry-run", "--tickers", "AAA")) == 0
    out = capsys.readouterr().out
    assert "# ladder-turn_of_month-r1" in out                  # the smoke doc still prints
    smoke = ri.read_events(ri._smoke_events_path(tmp_path / "work", 1))
    assert smoke and {e.ticker for e in smoke} == {"AAA"}
    assert not ri._events_path(tmp_path / "work", 1).exists()
    assert not (tmp_path / "work" / "rung1").exists() and not (tmp_path / "results").exists()
    assert len(stats.load_ledger(tmp_path / "ledger.jsonl")) == 1
    rows = [PASS_ROW, _ladder_row(1, ladder.HOLD)]
    assert "rung1-events.json" in ri.refusals(_args(tmp_path, "--dry-run", rung=2), IDEA, rows)


def test_a_smoke_run_reads_its_own_crash_record_not_the_real_runs(tmp_path, capsys):
    _store(tmp_path)
    _ledger(tmp_path / "ledger.jsonl", PASS_ROW)
    real = tmp_path / "work" / "rung1"
    ri._write_json(real / ri.RUNNING_FILE, {"started": "earlier"})
    ri._write_json(real / ri.CRASH_FILE, {"crashed_run": {"started": "earlier"}})
    assert ri.main(_argv(tmp_path, "--dry-run", "--tickers", "AAA")) == 0
    assert "Crash record" not in capsys.readouterr().out
    assert ri._run_dir(tmp_path / "work", 1, smoke=True).name == "rung1-smoke"


def test_a_smoke_run_prints_missing_members_and_keeps_apart(tmp_path):
    _store(tmp_path, extra_members=("ZZZ",))
    lines = []
    run = ri.run_rung(IDEAS["turn_of_month"], 1, _args(tmp_path, "--dry-run", "--tickers", "AAA"),
                      out=_quiet(lines))
    assert {e.ticker for e in run.events} == {"AAA"}
    assert any("missing 1: ZZZ" in line for line in lines)
    assert not (tmp_path / "work" / "rung1").exists()
    assert [p.name for p in (tmp_path / "work" / "rung1-smoke").iterdir()] == ["screen"]


def test_a_re_race_that_disagrees_with_the_screen_stops_the_run():
    ri._check_rerace("AAA", SimpleNamespace(r=[0.25]), [{"r_event": 0.25}])
    with pytest.raises(RuntimeError, match="disagrees"):
        ri._check_rerace("AAA", SimpleNamespace(r=[0.25]), [{"r_event": 0.75}])
