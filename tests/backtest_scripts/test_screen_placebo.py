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


def _argv(tmp_path, *extra):
    return ["--source-cache", str(_source(tmp_path)), "--work-dir", str(tmp_path / "work"),
            "--json-dir", str(tmp_path / "json"), "--results-dir", str(tmp_path / "results"),
            "--date", "2026-11-20", "--gbm-tickers", "3", *extra]


def test_latest_cells_and_the_inclusive_v1_gate():
    cells = [_cell("gbm-200", 0.30), _cell("gbm-400", 0.01), _cell("shuffled-c1", -0.02),
             _cell("gbm-200", 0.50, null="v2")]
    latest = {(c.universe, c.null) for c in screen_placebo.latest_cells(cells)}
    assert latest == {("gbm-400", "v1"), ("shuffled-c1", "v1"), ("gbm-200", "v2")}
    assert screen_placebo.v1_gate(cells) == "NO-BIAS"
    assert screen_placebo.v1_gate(cells + [_cell("shuffled-c1", 0.0201, trigger="x")]) == "BIAS"
    assert screen_placebo.v1_gate([_cell("gbm-200", 0.5, null="v2")]) is None


def test_main_writes_cells_and_doc_then_a_restart_skips(tmp_path, monkeypatch, capsys):
    argv = _argv(tmp_path, "--triggers", "p_high20", "p_month_turn")
    assert screen_placebo.main(argv) == 0
    cells = screen_placebo.load_cells(tmp_path / "json" / "placebo-v1.json")
    assert sorted((c.universe, c.trigger) for c in cells) == [
        ("gbm-3", "p_high20"), ("gbm-3", "p_month_turn"),
        ("shuffled-c1", "p_high20"), ("shuffled-c1", "p_month_turn")]
    assert (tmp_path / "work" / "checkpoints" / "v1" / "gbm-3" / "p_high20"
            / "manifest.json").is_file()
    doc = (tmp_path / "results" / "2026-11-20-v230-null-placebo.md").read_text(encoding="utf-8")
    assert "## Stop gate 1 (v1)" in doc and "| gbm-3 | p_high20 | v1 |" in doc
    assert "| shuffled-c1 | shuffled | 3 |" in doc
    assert "gate: " in capsys.readouterr().out
    monkeypatch.setitem(screen_placebo.RUNNERS, "v1",
                        lambda *a, **k: pytest.fail("re-ran a finished cell"))
    assert screen_placebo.main(argv) == 0


def test_main_refuses_a_null_without_a_runner(tmp_path, monkeypatch, capsys):
    monkeypatch.delitem(screen_placebo.RUNNERS, "v2", raising=False)
    monkeypatch.setattr(screen_placebo, "build_universes",
                        lambda *a: pytest.fail("built universes before refusing"))
    assert screen_placebo.main(_argv(tmp_path, "--null", "v2")) == 2
    error = capsys.readouterr().err
    assert "refused" in error and "V234-8" in error
    assert not (tmp_path / "work").exists()


def test_render_doc_gate_hashes_planted_and_acceptance():
    manifests = {"shuffled-c1": {"kind": "shuffled", "seed": 42, "tickers": ["AAA"],
                                 "calendar_start": "2010-01-04", "calendar_end": "2019-12-31",
                                 "copies": 1, "source_sha256": {"AAA.csv": "ab" * 32}}}
    bias = screen_placebo.render_doc([_cell("shuffled-c1", 0.3)], date="2026-11-20",
                                     manifests=manifests)
    assert bias.startswith("# v230 null placebo — 2026-11-20\n")
    assert "Gate: **BIAS**" in bias and "shuffled-c1/p_high20 (+0.3000)" in bias
    assert "v234's prerequisite" in bias
    assert "| shuffled-c1 | shuffled | 1 |" in bias and "`AAA.csv` `" + "ab" * 32 in bias
    calm = screen_placebo.render_doc([_cell("gbm-200", 0.02)], date="d", manifests={})
    assert "Gate: **NO-BIAS**" in calm and "premise of spec v230 is wrong" in calm
    assert "v234 stops" in calm
    assert "V230-6" not in bias + calm
    assert "## Stop gate 2" not in calm and "## Planted edge" not in calm


def test_render_doc_planted_edge_and_acceptance():
    passing = _cell("gbm-200", 0.0, null="v2")
    planted = _cell("planted-gbm-200", 0.4, trigger="p_high20_planted", null="v2")
    verdict = placebo.acceptance([passing], planted, 0.4)
    doc = screen_placebo.render_doc([passing], date="d", manifests={}, planted=planted,
                                    acceptance=verdict)
    assert "## Planted edge" in doc and "p_high20_planted" in doc
    assert "Verdict: **ACCEPT**" in doc and "| gbm-200/p_high20 | PASS |" in doc
    assert "## Stop gate 1" not in doc
