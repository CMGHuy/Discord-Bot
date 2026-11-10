"""v211: screen_universe's opt-in per-ticker checkpoint -- a resumed run
equals an uninterrupted one, another run's checkpoint refuses, nothing is
written without --checkpoint-dir."""
import functools
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402

from swingbot.core.backtesting.screen import verdict  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS  # noqa: E402
from tests.backtesting.screen.helpers import random_walk  # noqa: E402

IDEA = IDEAS["turn_of_month"]


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    monkeypatch.setattr(screen_idea.verdict, "decide",
                        functools.partial(verdict.decide, n_resamples=500))


def _write_csv(path, df):
    df.rename_axis("Date").to_csv(path)


def _universe(tmp_path):
    """AAA, BBB, DDD with 2010-2019 bars; CCC only after 2019 (an empty frame)."""
    cache = tmp_path / "cache"
    cache.mkdir()
    for seed, ticker in enumerate(("AAA", "BBB", "DDD"), start=1):
        _write_csv(cache / f"{ticker}.csv", random_walk(2700, seed=seed))
    _write_csv(cache / "CCC.csv", random_walk(60, seed=9, start="2020-06-01"))
    membership = tmp_path / "membership.csv"
    membership.write_text("ticker,start_date,end_date\n" + "".join(
        f"{t},2000-01-01,\n" for t in ("AAA", "BBB", "CCC", "DDD")), encoding="utf-8")
    return cache, screen_idea.load_universe(cache, membership)


def _quiet(*_args, **_kwargs):
    return None


def _same(a, b):
    assert [s.ticker for s in a] == [s.ticker for s in b]
    for x, y in zip(a, b):
        assert x.events == y.events and x.counters == y.counters
        assert x.null_outcomes == y.null_outcomes and repr(x.excess) == repr(y.excess)
        assert x.rank.equals(y.rank) and x.null_slots == y.null_slots


def test_without_a_directory_nothing_is_written(tmp_path):
    cache, universe = _universe(tmp_path)
    before = sorted(p.name for p in tmp_path.rglob("*"))
    screens, skipped = screen_idea.screen_universe(IDEA, universe, cache, out=_quiet)
    assert [s.ticker for s in screens] == ["AAA", "BBB", "DDD"]
    assert skipped == Counter({"empty_frame": 1})
    assert sorted(p.name for p in tmp_path.rglob("*")) == before


def test_a_resumed_run_equals_an_uninterrupted_run(tmp_path, monkeypatch):
    cache, universe = _universe(tmp_path)
    assert universe.cached == ["AAA", "BBB", "CCC", "DDD"]     # members_between sorts
    full, full_skipped = screen_idea.screen_universe(IDEA, universe, cache, out=_quiet)
    directory = tmp_path / "ckpt"
    real, calls = screen_idea.screen_ticker, []

    def dies_on_bbb(idea, ticker, *args, **kwargs):
        if ticker == "BBB":
            raise RuntimeError("killed")
        return real(idea, ticker, *args, **kwargs)

    monkeypatch.setattr(screen_idea, "screen_ticker", dies_on_bbb)
    with pytest.raises(RuntimeError, match="killed"):
        screen_idea.screen_universe(IDEA, universe, cache, out=_quiet, checkpoint_dir=directory)
    assert sorted(p.name for p in directory.iterdir()) == ["AAA.pkl", "manifest.json"]

    def counting(idea, ticker, *args, **kwargs):
        calls.append(ticker)
        return real(idea, ticker, *args, **kwargs)

    monkeypatch.setattr(screen_idea, "screen_ticker", counting)
    resumed, skipped = screen_idea.screen_universe(IDEA, universe, cache, out=_quiet,
                                                   checkpoint_dir=directory)
    assert calls == ["BBB", "DDD"]
    assert skipped == full_skipped
    _same(resumed, full)


def test_the_layout_and_the_manifest(tmp_path, monkeypatch):
    cache, universe = _universe(tmp_path)
    directory = tmp_path / "ckpt"
    moves, real_replace = [], screen_idea.os.replace

    def spy(src, dst):
        moves.append((Path(src).name, Path(dst).name))
        return real_replace(src, dst)

    monkeypatch.setattr(screen_idea.os, "replace", spy)
    screen_idea.screen_universe(IDEA, universe, cache, out=_quiet, checkpoint_dir=directory)
    assert sorted(p.name for p in directory.iterdir()) == [
        "AAA.pkl", "BBB.pkl", "DDD.pkl", "manifest.json"]       # CCC (empty frame) never pickled
    assert ("AAA.pkl.tmp", "AAA.pkl") in moves
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == screen_idea._checkpoint_manifest(
        IDEA, "2010-01-01", "2019-12-31", ["AAA", "BBB", "CCC", "DDD"],
        None, universe.intervals)
    assert set(manifest) == {"idea", "start", "end", "tickers_sha256", "context_sha256",
                             "intervals_sha256", "params_sha256"}
    assert manifest["context_sha256"] is None
    assert manifest["idea"] == "turn_of_month" and len(manifest["tickers_sha256"]) == 64


@pytest.mark.parametrize("change", ["idea", "tickers", "end"])
def test_another_runs_checkpoint_refuses_before_screening(tmp_path, monkeypatch, change):
    cache, universe = _universe(tmp_path)
    directory = tmp_path / "ckpt"
    screen_idea.screen_universe(IDEA, universe, cache, out=_quiet, checkpoint_dir=directory)
    monkeypatch.setattr(screen_idea, "screen_ticker",
                        lambda *a, **k: pytest.fail("screened after a manifest mismatch"))
    idea = IDEAS["high52w"] if change == "idea" else IDEA
    kwargs = {"tickers": {"tickers": ["AAA"]}, "end": {"end": "2018-12-31"}}.get(change, {})
    with pytest.raises(ValueError, match="belongs to another run"):
        screen_idea.screen_universe(idea, universe, cache, out=_quiet,
                                    checkpoint_dir=directory, **kwargs)


def _changed_run(change, universe):
    """The idea, the context frames and the universe a run resumes with."""
    idea, context = IDEA, {"X": random_walk(300, seed=5)}
    if change == "param":
        idea = replace(IDEA, params={**IDEA.params, "edited": 1})
    elif change == "context":
        context = {"X": random_walk(300, seed=6)}
    elif change == "intervals":
        universe = replace(universe, intervals={**universe.intervals, "AAA": [("2011-01-01", None)]})
    return idea, context, universe


@pytest.mark.parametrize("change", ["param", "context", "intervals"])
def test_a_changed_context_parameter_or_membership_refuses(tmp_path, monkeypatch, change):
    cache, universe = _universe(tmp_path)
    directory = tmp_path / "ckpt"
    first_context = {"X": random_walk(300, seed=5)}
    screen_idea.screen_universe(IDEA, universe, cache, out=_quiet, checkpoint_dir=directory,
                                context=first_context)
    monkeypatch.setattr(screen_idea, "screen_ticker",
                        lambda *a, **k: pytest.fail("screened after a manifest mismatch"))
    idea, context, universe = _changed_run(change, universe)
    with pytest.raises(ValueError, match="belongs to another run"):
        screen_idea.screen_universe(idea, universe, cache, out=_quiet,
                                    checkpoint_dir=directory, context=context)


def test_main_threads_the_checkpoint_dir(tmp_path):
    cache, _universe_ = _universe(tmp_path)
    directory = tmp_path / "ckpt"
    argv = ["--idea", "turn_of_month", "--cache-dir", str(cache),
            "--membership", str(tmp_path / "membership.csv"),
            "--ledger", str(tmp_path / "ledger.jsonl"),
            "--results-dir", str(tmp_path / "results"), "--date", "2026-11-06",
            "--dry-run", "--tickers", "AAA,BBB", "--checkpoint-dir", str(directory)]
    assert screen_idea.main(argv) == 0
    assert sorted(p.name for p in directory.iterdir()) == ["AAA.pkl", "BBB.pkl", "manifest.json"]
    assert screen_idea.build_parser().parse_args(["--idea", "high52w"]).checkpoint_dir is None


def test_a_checkpointed_dry_run_prints_the_same_doc(tmp_path, capsys):
    cache, _universe_ = _universe(tmp_path)
    base = ["--idea", "turn_of_month", "--cache-dir", str(cache),
            "--membership", str(tmp_path / "membership.csv"),
            "--ledger", str(tmp_path / "ledger.jsonl"),
            "--results-dir", str(tmp_path / "results"), "--date", "2026-11-06", "--dry-run"]
    assert screen_idea.main(base) == 0
    plain = capsys.readouterr().out
    assert screen_idea.main(base + ["--checkpoint-dir", str(tmp_path / "ckpt")]) == 0
    first = capsys.readouterr().out
    assert screen_idea.main(base + ["--checkpoint-dir", str(tmp_path / "ckpt")]) == 0
    resumed = capsys.readouterr().out
    doc = [line for line in plain.splitlines() if not line.startswith("[turn_of_month]")]
    for out in (first, resumed):
        assert [line for line in out.splitlines()
                if not line.startswith("[turn_of_month]")] == doc
