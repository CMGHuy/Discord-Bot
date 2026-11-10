"""v211 --count-only for level-context ideas (spec § Track 2, Outcome-blind
preflight): context loads and is checked like the real run, the count ends
with shock days, ISO weeks and events per year, nothing is raced, nothing is
written, and every existing idea's count is byte-identical (golden from the
base commit)."""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402

from swingbot.core.backtesting.screen import null, race, shock_readouts, trail, verdict  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS  # noqa: E402
from swingbot.core.backtesting.screen.ideas import _shock_breakdown as sb  # noqa: E402
from tests.backtest_scripts.test_screen_level_context import (  # noqa: E402,F401
    _fake_level_idea, _level_argv, _level_cache, level_registered)

GOLDEN = Path(__file__).with_name("golden") / "count_only_range_breakdown_close.md"
ALWAYS = [("2000-01-01", "9999-12-31")]
HEADER = "| year | shock days | shock weeks | events |"


def _count_out(tmp_path, cache, idea):
    """(exit code, stdout, stderr) of `--count-only` on the level fixture."""
    argv = _level_argv(tmp_path, cache, "--count-only")
    argv[1] = idea
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = screen_idea.main(argv)
    return code, out.getvalue(), err.getvalue()


def capture_golden() -> None:
    """V211-12 Step 2 only: run once on the base commit, before
    screen_idea.py is edited. Never re-run to make a test pass."""
    with tempfile.TemporaryDirectory() as tmp:
        code, out, err = _count_out(Path(tmp), _level_cache(Path(tmp)),
                                    "range_breakdown_close")
    assert code == 0, err
    GOLDEN.write_text(out, encoding="utf-8", newline="\n")


def _count_n(lines) -> int:
    return int(next(x for x in lines if x.startswith("| **count N** |")).split("**")[3])


def _cells(line) -> list[str]:
    return [cell.strip(" *") for cell in line.strip("|").split("|")]


def _boom(*args, **kwargs):
    raise AssertionError("--count-only must never race")


# --- byte-identical for every existing idea ------------------------------------

def test_a_context_free_idea_counts_byte_identical_to_the_base_golden(tmp_path):
    code, out, err = _count_out(tmp_path, _level_cache(tmp_path), "range_breakdown_close")
    assert code == 0, err
    assert out == GOLDEN.read_text(encoding="utf-8")
    assert HEADER not in out and "**count N**" in out        # non-vacuous golden


def test_a_z_context_idea_is_still_refused_before_any_data_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(screen_idea, "_context_step", _boom)
    code, out, err = _count_out(tmp_path, _level_cache(tmp_path), "dollar_drop")
    assert code == 2 and HEADER not in out
    assert "--count-only counts ideas without context series; dollar_drop reads UUP" in err


def test_count_ticker_lists_one_date_per_counted_event(tmp_path):
    cache = _level_cache(tmp_path)
    df = screen_idea.load_frame(cache / "AAA.csv", screen_idea.WINDOW_START,
                                screen_idea.WINDOW_END)
    context = screen_idea.load_context(cache, sb.CONTEXT, kind="level").frames
    for idea, ctx in ((_fake_level_idea(), context), (IDEAS["range_breakdown_close"], None)):
        out = screen_idea.count_ticker(idea, "AAA", df, ALWAYS, context=ctx)
        assert out["events"] > 0, idea.name                      # non-vacuous
        assert len(out["event_dates"]) == out["events"]
        assert out["event_dates"] == sorted(out["event_dates"])
        assert out["event_dates"][0] >= screen_idea.EVENT_START


# --- a level idea counts with its context ----------------------------------------

def test_a_level_idea_counts_and_ends_with_the_preflight_table(tmp_path, level_registered):
    code, out, err = _count_out(tmp_path, _level_cache(tmp_path), "fake_level")
    assert code == 0, err
    lines = out.rstrip("\n").splitlines()
    assert "# v182 count: `fake_level` (outcome-blind: no race, no R)" in lines
    start = lines.index(HEADER)
    rows = [[int(c) for c in _cells(x)] for x in lines[start + 2:-1]]
    assert [r[0] for r in rows] == list(verdict.YEARS)
    total = _cells(lines[-1])
    assert total[0] == "total"
    assert [int(c) for c in total[1:]] == [sum(col) for col in zip(*rows)][1:]
    assert int(total[3]) == _count_n(lines) > 0
    assert int(total[1]) > 0                                     # shock days exist
    for written in ("hashes.json", "ledger.jsonl", "results"):
        assert not (tmp_path / written).exists(), written        # writes nothing


def test_the_preflight_reads_the_market_state_and_the_counted_dates(tmp_path, monkeypatch,
                                                                     level_registered):
    seen, real = {}, shock_readouts.preflight_years

    def spy(state, event_dates, *args, **kwargs):
        seen["state"], seen["dates"] = state, list(event_dates)
        return real(state, event_dates, *args, **kwargs)

    monkeypatch.setattr(shock_readouts, "preflight_years", spy)
    cache = _level_cache(tmp_path)
    code, out, err = _count_out(tmp_path, cache, "fake_level")
    assert code == 0, err
    context = screen_idea.load_context(cache, sb.CONTEXT, kind="level").frames
    pd.testing.assert_frame_equal(
        seen["state"], sb.shock_state(context[sb.BREADTH]["Close"], context[sb.VIX]["Close"]))
    assert len(seen["dates"]) == _count_n(out.splitlines())
    years = pd.to_datetime(seen["dates"]).year
    assert years.min() >= 2011 and years.max() <= 2019


def test_a_level_count_races_nothing(tmp_path, monkeypatch, level_registered):
    for owner, name in ((race, "race"), (race, "run_book"), (trail, "race_trail"),
                        (null, "matched_null"), (screen_idea, "_books"),
                        (shock_readouts, "shock_null")):
        monkeypatch.setattr(owner, name, _boom)
    code, out, err = _count_out(tmp_path, _level_cache(tmp_path), "fake_level")
    assert code == 0, err
    assert HEADER in out


def test_a_level_count_refuses_a_missing_context_file(tmp_path, level_registered):
    cache = _level_cache(tmp_path)
    (cache / "^VIX.csv").unlink()
    code, out, err = _count_out(tmp_path, cache, "fake_level")
    assert code == 2 and "refused:" in err and "^VIX" in err and "is missing" in err
    assert HEADER not in out


def test_a_level_count_refuses_a_differing_pin_and_never_rewrites_it(tmp_path,
                                                                     level_registered):
    cache = _level_cache(tmp_path)
    pins = {t: r["sha256"] for t, r in screen_idea._hash_records(cache).items()}
    pins["^VIX"] = "0" * 64
    path = tmp_path / "hashes.json"
    path.write_text(json.dumps(pins), encoding="utf-8")
    code, out, err = _count_out(tmp_path, cache, "fake_level")
    assert code == 2 and "differs" in err and HEADER not in out
    assert json.loads(path.read_text(encoding="utf-8")) == pins


# --- the printed block ----------------------------------------------------------

def test_preflight_block_prints_every_year_and_the_totals_last():
    table = {y: {"shock_days": 0, "shock_weeks": 0, "events": 0} for y in verdict.YEARS}
    table[2011] = {"shock_days": 3, "shock_weeks": 2, "events": 5}
    table[2015] = {"shock_days": 1, "shock_weeks": 1, "events": 0}
    lines = screen_idea._preflight_block(table)
    assert lines[-1] == "| **total** | **4** | **3** | **5** |"
    assert "| 2011 | 3 | 2 | 5 |" in lines and "| 2019 | 0 | 0 | 0 |" in lines
    assert lines.index(screen_idea.PREFLIGHT_HEADER) == len(lines) - len(table) - 3
    assert "Years without a shock day: 7 of 9." in lines
    assert any("never decides whether the shot runs" in x for x in lines)


def test_count_preflight_is_none_for_every_non_level_idea():
    for name in ("range_breakdown_close", "turn_of_month", "dollar_drop"):
        assert screen_idea._count_preflight(IDEAS[name], None, {"event_dates": []}) is None
