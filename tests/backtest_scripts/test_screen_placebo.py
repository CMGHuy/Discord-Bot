"""v230 A1: screen_idea's window parameters (defaults byte-identical) and the
placebo CLI -- universes built once, cells upserted, a restart skips, the doc."""
import functools
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402
import screen_placebo  # noqa: E402

from swingbot.core.backtesting.screen import placebo  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS  # noqa: E402
from swingbot.core.backtesting.screen.placebo import Cell  # noqa: E402
from tests.backtesting.screen.helpers import random_walk  # noqa: E402

ALWAYS = [("2000-01-01", "9999-12-31")]
IDEA = IDEAS["turn_of_month"]
EARLY = "2010-06-01"


def _quiet(*_args, **_kwargs):
    return None


@pytest.fixture(autouse=True)
def fast_cells(monkeypatch):
    monkeypatch.setattr(placebo, "cell_from_rows",
                        functools.partial(placebo.cell_from_rows, n_resamples=200))


def _write_csv(path, df):
    df.rename_axis("Date").to_csv(path)


def _source(tmp_path):
    """SPY plus three tickers on one calendar from 2010-01-04 as the source cache."""
    src = tmp_path / "src"
    if not src.exists():
        src.mkdir()
        for seed, ticker in enumerate(("SPY", "AAA", "BBB", "CCC"), start=1):
            _write_csv(src / f"{ticker}.csv", random_walk(520, seed=seed))
    return src


def _cell(universe, delta, *, trigger="p_high20", null="v1", low=None, high=None):
    low = delta - 0.01 if low is None else low
    high = delta + 0.01 if high is None else high
    return Cell(universe, trigger, null, 400, 0.1 + delta, 0.1, delta, low, high)


@pytest.mark.parametrize("fn, name, default", [
    ("ticker_context", "event_start", "EVENT_START"),
    ("screen_ticker", "event_start", "EVENT_START"),
    ("screen_universe", "event_start", "EVENT_START"),
    ("_spy_calendar", "start", "CONTEXT_START"),
    ("load_context", "context_start", "CONTEXT_START")])
def test_window_parameters_default_to_the_module_constants(fn, name, default):
    param = inspect.signature(getattr(screen_idea, fn)).parameters[name]
    assert param.default == getattr(screen_idea, default)


def test_ticker_context_default_is_byte_identical_and_event_start_moves_warm():
    df = random_walk(700, seed=3)
    default = screen_idea.ticker_context(IDEA, df, ALWAYS)
    explicit = screen_idea.ticker_context(IDEA, df, ALWAYS, event_start=screen_idea.EVENT_START)
    for key in ("raw", "member", "warm", "trend"):
        assert np.array_equal(default[key], explicit[key])
    early = screen_idea.ticker_context(IDEA, df, ALWAYS, event_start=EARLY)
    assert early["warm"].sum() > default["warm"].sum()
    assert not early["warm"][df.index < pd.Timestamp(EARLY)].any()


def test_screen_universe_threads_event_start_and_marks_only_a_changed_manifest(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    for seed, ticker in enumerate(("AAA", "BBB"), start=1):
        _write_csv(cache / f"{ticker}.csv", random_walk(700, seed=seed))
    (tmp_path / "m.csv").write_text("ticker,start_date,end_date\nAAA,2000-01-01,\n"
                                    "BBB,2000-01-01,\n", encoding="utf-8")
    universe = screen_idea.load_universe(cache, tmp_path / "m.csv")
    screen_idea.screen_universe(IDEA, universe, cache, out=_quiet, checkpoint_dir=tmp_path / "a")
    assert "event_start" not in json.loads((tmp_path / "a" / "manifest.json").read_text())
    screens, _ = screen_idea.screen_universe(IDEA, universe, cache, out=_quiet,
                                             checkpoint_dir=tmp_path / "b", event_start=EARLY)
    assert json.loads((tmp_path / "b" / "manifest.json").read_text())["event_start"] == EARLY
    first = min(row["entry_date"] for s in screens for row in s.events)
    assert EARLY <= first < screen_idea.EVENT_START


def test_spy_calendar_and_load_context_take_a_start(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    _write_csv(cache / "SPY.csv", random_walk(400, seed=1, start="2009-01-02"))
    assert screen_idea._spy_calendar(cache, "2010-06-30").index[0] >= \
        pd.Timestamp(screen_idea.CONTEXT_START)
    data = screen_idea.load_context(cache, (), end="2010-06-30", context_start="2009-03-02")
    assert data.frames == {} and data.calendar.index[0] == pd.Timestamp("2009-03-02")


def test_universe_labels():
    assert screen_placebo.universe_label("gbm", 200) == "gbm-200"
    assert screen_placebo.universe_label("shuffled", 2) == "shuffled-c2"


def test_save_cell_upserts_atomically(tmp_path):
    path = tmp_path / "json" / "placebo-v1.json"
    assert screen_placebo.load_cells(path) == []
    for cell in (_cell("gbm-200", 0.30), _cell("gbm-200", 0.01, trigger="p_gap_up"),
                 _cell("gbm-200", 0.05)):
        screen_placebo.save_cell(path, cell)
    cells = screen_placebo.load_cells(path)
    assert sorted((c.trigger, c.delta) for c in cells) == [("p_gap_up", 0.01), ("p_high20", 0.05)]
    assert [p.name for p in path.parent.iterdir()] == ["placebo-v1.json"]


def test_build_universes_once_and_run_cell_v1(tmp_path, monkeypatch):
    args = SimpleNamespace(source_cache=_source(tmp_path), work_dir=tmp_path / "work",
                           universes=["gbm", "shuffled"], gbm_tickers=3, shuffled_copies=1)
    built = screen_placebo.build_universes(args)
    assert sorted(built) == ["gbm-3", "shuffled-c1"]
    manifest = json.loads((built["gbm-3"] / placebo.MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest["kind"] == "gbm" and len(manifest["tickers"]) == 3
    monkeypatch.setattr(placebo, "gbm_universe", lambda *a, **k: pytest.fail("rebuilt"))
    monkeypatch.setattr(placebo, "shuffled_universe", lambda *a, **k: pytest.fail("rebuilt"))
    assert screen_placebo.build_universes(args) == built
    rows = screen_placebo.run_cell_v1(built["gbm-3"], placebo.TRIGGERS["p_high20"],
                                      checkpoint_dir=tmp_path / "ckpt")
    assert rows and {"ticker", "entry_date", "r_event", "r_null"} <= set(rows[0])
    assert min(r["entry_date"] for r in rows) >= screen_idea.EVENT_START
    assert {r["ticker"] for r in rows} <= {"G000", "G001", "G002"}
    assert (tmp_path / "ckpt" / "manifest.json").is_file()
