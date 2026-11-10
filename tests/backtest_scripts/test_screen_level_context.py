"""v211 CONTEXT_KIND = "level": the idea field, the level load path that
skips only the z-coverage floor, and --pin-context (never rewrites a pin)."""
import functools
import json
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402

from swingbot.core.backtesting.screen import context as pit  # noqa: E402
from swingbot.core.backtesting.screen import verdict  # noqa: E402
from swingbot.core.backtesting.screen import ideas as ideas_pkg  # noqa: E402
from swingbot.core.backtesting.screen.ideas import CONTEXT_KINDS, IDEAS, Idea  # noqa: E402
from tests.backtesting.screen.helpers import frame, random_walk  # noqa: E402

CONTEXT_FROM = "2009-06-01"
LEVEL = ("BREADTH_ATR1", "^VIX")
SHOCK_PARAMS = {"breadth": "BREADTH_ATR1", "vix": "^VIX", "enter": 0.40,
                "release": 0.10, "side": "short"}


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    """500 week resamples instead of 10,000: same code path, test-speed."""
    monkeypatch.setattr(screen_idea.verdict, "decide",
                        functools.partial(verdict.decide, n_resamples=500))


def _write_csv(path, df):
    df.rename_axis("Date").to_csv(path)


def _breadth(index) -> pd.DataFrame:
    """A breadth fraction that is exactly 0.0 on most sessions: 0.50 every
    40th session, 0.05 on the three after it (the z floor cannot pass it)."""
    values = np.zeros(len(index))
    values[::40] = 0.50
    for k in (1, 2, 3):
        values[k::40] = 0.05
    return frame(values, index=index, opens=values, highs=values, lows=values,
                 volumes=np.full(len(index), 400.0))


def _level_cache(tmp_path, *, tickers=("AAA", "BBB")) -> Path:
    """Stocks from 2010-01-04; SPY, TLT, UUP, ^VIX, ^VIX3M and BREADTH_ATR1 on one
    business-day calendar from 2009-06-01 (TLT/UUP/^VIX3M because _hash_records
    spans the whole registered union); tmp_path/membership.csv."""
    cache = tmp_path / "cache"
    cache.mkdir()
    for seed, ticker in enumerate(tickers, start=1):
        _write_csv(cache / f"{ticker}.csv", random_walk(2700, seed=seed))
    spy = random_walk(2800, seed=50, start=CONTEXT_FROM)
    _write_csv(cache / "SPY.csv", spy)
    for seed, ticker in enumerate(("TLT", "UUP", "^VIX", "^VIX3M"), start=51):
        _write_csv(cache / f"{ticker}.csv", random_walk(2800, seed=seed, start=CONTEXT_FROM))
    _write_csv(cache / "BREADTH_ATR1.csv", _breadth(spy.index))
    (tmp_path / "membership.csv").write_text(
        "ticker,start_date,end_date\n" + "".join(f"{t},2000-01-01,\n" for t in tickers),
        encoding="utf-8")
    return cache


def _level_events(df, context):
    gate = context["BREADTH_ATR1"]["Close"] >= 0.40
    return pit.context_on(df.index, gate).rename("fake_level")


def _fake_level_idea(**overrides) -> Idea:
    fields = dict(name="fake_level", events=_level_events, time_cap_bars=10,
                  direction="short", params=SHOCK_PARAMS, summary="breadth >= 0.40",
                  source="test", context=LEVEL, context_kind="level")
    fields.update(overrides)
    return Idea(**fields)


@pytest.fixture
def level_registered(monkeypatch):
    idea = _fake_level_idea()
    monkeypatch.setitem(screen_idea.IDEAS, idea.name, idea)
    return idea


def _quiet(*_args, **_kwargs):
    return None


# --- the idea field -----------------------------------------------------------

def test_context_kinds_and_the_default():
    assert CONTEXT_KINDS == ("z", "level")
    assert Idea(name="x", events=lambda df: df["Close"] > 0, time_cap_bars=5).context_kind == "z"
    assert {idea.context_kind for idea in IDEAS.values()} == {"z"}


def test_a_level_idea_needs_context_and_a_known_kind():
    with pytest.raises(ValueError, match="a level context idea needs CONTEXT"):
        _fake_level_idea(context=())
    with pytest.raises(ValueError, match="context kind 'zz' is not one of"):
        _fake_level_idea(context_kind="zz")


def test_load_reads_the_module_attribute(monkeypatch):
    module = types.ModuleType("fake_level_mod")
    module.CAP, module.PARAMS, module.SUMMARY, module.SOURCE = 10, SHOCK_PARAMS, "s", "src"
    module.events, module.CONTEXT, module.CONTEXT_KIND = _level_events, LEVEL, "level"
    module.DIRECTION = "short"
    monkeypatch.setitem(sys.modules, f"{ideas_pkg.__name__}.fake_level_mod", module)
    idea = ideas_pkg._load("fake_level_mod")
    assert idea.context_kind == "level" and idea.context == LEVEL


# --- the level load path ------------------------------------------------------

def test_level_load_skips_only_the_z_coverage_floor(tmp_path):
    cache = _level_cache(tmp_path)
    with pytest.raises(pit.ContextError, match="defined z covers"):
        screen_idea.load_context(cache, ("BREADTH_ATR1",))
    data = screen_idea.load_context(cache, LEVEL, kind="level")
    assert list(data.frames) == list(LEVEL)
    breadth = data.frames["BREADTH_ATR1"]
    assert breadth.index.equals(data.calendar.index)
    assert (breadth["Close"] == 0.0).mean() > 0.5
    assert set(data.records) == set(LEVEL)


def test_level_load_keeps_the_session_check(tmp_path):
    cache = _level_cache(tmp_path)
    path = cache / "BREADTH_ATR1.csv"
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    _write_csv(path, df.drop(df.index[300]))
    with pytest.raises(pit.ContextError, match="SPY session"):
        screen_idea.load_context(cache, LEVEL, kind="level")


def test_level_load_keeps_the_raw_index_check(tmp_path):
    cache = _level_cache(tmp_path)
    path = cache / "^VIX.csv"
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df.index = df.index.tz_localize("UTC")
    _write_csv(path, df)
    with pytest.raises(pit.ContextError, match="tz-aware"):
        screen_idea.load_context(cache, LEVEL, kind="level")


def test_both_load_sites_pass_the_idea_kind(tmp_path, monkeypatch, level_registered):
    cache = _level_cache(tmp_path)
    kinds, real = [], screen_idea.load_context

    def spy(*args, **kwargs):
        kinds.append(kwargs.get("kind", "z"))
        return real(*args, **kwargs)

    monkeypatch.setattr(screen_idea, "load_context", spy)
    screen_idea._universe_context(level_registered, cache, "2019-12-31", None)
    args = types.SimpleNamespace(cache_dir=cache, end="2019-12-31",
                                 context_hashes=tmp_path / "hashes.json")
    data, reason = screen_idea._context_step(args, level_registered)
    assert reason is None and set(data.frames) == set(LEVEL)
    screen_idea._universe_context(IDEAS["bond_spike_rebound"], cache, "2019-12-31", None)
    assert kinds == ["level", "level", "z"]


# --- the pin file -------------------------------------------------------------

def _rec(sha):
    return {"sha256": sha}


def test_add_context_hashes_adds_only_the_missing_names(tmp_path):
    path = tmp_path / "hashes.json"
    path.write_text(json.dumps({"TLT": "a" * 64, "UUP": "b" * 64}, indent=2,
                               sort_keys=True) + "\n", encoding="utf-8")
    records = {"TLT": _rec("a" * 64), "UUP": _rec("b" * 64),
               "^VIX": _rec("c" * 64), "BREADTH_ATR1": _rec("d" * 64)}
    assert screen_idea.add_context_hashes(records, path) == ["BREADTH_ATR1", "^VIX"]
    expected = {"TLT": "a" * 64, "UUP": "b" * 64, "^VIX": "c" * 64, "BREADTH_ATR1": "d" * 64}
    assert path.read_text(encoding="utf-8") == json.dumps(expected, indent=2,
                                                          sort_keys=True) + "\n"


def test_add_context_hashes_never_rewrites_a_pin(tmp_path):
    path = tmp_path / "hashes.json"
    path.write_text(json.dumps({"TLT": "a" * 64}), encoding="utf-8")   # compact on purpose
    before = path.read_bytes()
    with pytest.raises(pit.ContextError, match="differs"):
        screen_idea.add_context_hashes({"TLT": _rec("f" * 64), "^VIX": _rec("c" * 64)}, path)
    assert path.read_bytes() == before
    assert screen_idea.add_context_hashes({"TLT": _rec("a" * 64)}, path) == []
    assert path.read_bytes() == before            # nothing to add: not even reformatted


def test_add_context_hashes_creates_an_absent_file(tmp_path):
    path = tmp_path / "sub" / "hashes.json"
    assert screen_idea.add_context_hashes({"UUP": _rec("b" * 64), "TLT": _rec("a" * 64)},
                                          path) == ["TLT", "UUP"]
    assert json.loads(path.read_text(encoding="utf-8")) == {"TLT": "a" * 64, "UUP": "b" * 64}


def _pin_argv(tmp_path, cache, *extra):
    return ["--idea", "fake_level", "--cache-dir", str(cache),
            "--membership", str(tmp_path / "membership.csv"),
            "--ledger", str(tmp_path / "ledger.jsonl"),
            "--results-dir", str(tmp_path / "results"),
            "--context-hashes", str(tmp_path / "hashes.json"), "--pin-context", *extra]


def _pin_existing(tmp_path, cache, names=("TLT", "UUP")):
    pinned = {t: pit.file_record(cache / f"{t}.csv")["sha256"] for t in names}
    (tmp_path / "hashes.json").write_text(json.dumps(pinned, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
    return pinned


def test_pin_context_adds_the_new_files_and_screens_nothing(tmp_path, monkeypatch, capsys,
                                                            level_registered):
    cache = _level_cache(tmp_path)
    pinned = _pin_existing(tmp_path, cache)
    monkeypatch.setattr(screen_idea, "screen_universe",
                        lambda *a, **k: pytest.fail("--pin-context screened"))
    assert screen_idea.main(_pin_argv(tmp_path, cache)) == 0
    out = capsys.readouterr().out
    assert "pinned BREADTH_ATR1 " in out and "pinned ^VIX " in out and "pinned TLT" not in out
    now = json.loads((tmp_path / "hashes.json").read_text(encoding="utf-8"))
    assert set(now) == {"TLT", "UUP", "BREADTH_ATR1", "^VIX", "^VIX3M"}
    assert {t: now[t] for t in pinned} == pinned
    assert now["^VIX"] == pit.file_record(cache / "^VIX.csv")["sha256"]
    assert not (tmp_path / "ledger.jsonl").exists() and not (tmp_path / "results").exists()
    assert screen_idea.main(_pin_argv(tmp_path, cache)) == 0
    assert "nothing to pin" in capsys.readouterr().out


def test_pin_context_refuses_a_changed_pinned_file(tmp_path, capsys, level_registered):
    cache = _level_cache(tmp_path)
    _pin_existing(tmp_path, cache)
    before = (tmp_path / "hashes.json").read_bytes()
    path = cache / "TLT.csv"
    path.write_bytes(path.read_bytes() + b"\n")
    assert screen_idea.main(_pin_argv(tmp_path, cache)) == 2
    err = capsys.readouterr().err
    assert err.startswith("refused: ") and "TLT.csv SHA-256" in err
    assert (tmp_path / "hashes.json").read_bytes() == before


def test_pin_context_refuses_a_missing_file(tmp_path, capsys, level_registered):
    cache = _level_cache(tmp_path)
    (cache / "^VIX.csv").unlink()
    assert screen_idea.main(_pin_argv(tmp_path, cache)) == 2
    assert "missing" in capsys.readouterr().err
    assert not (tmp_path / "hashes.json").exists()


def test_pin_context_excludes_the_other_modes():
    with pytest.raises(SystemExit) as exc:
        screen_idea.build_parser().parse_args(["--idea", "high52w", "--pin-context",
                                               "--dry-run"])
    assert exc.value.code == 2


def test_mode_runner_dispatch():
    parse = screen_idea.build_parser().parse_args
    assert screen_idea._mode_runner(parse(["--idea", "high52w"])) is None
    assert screen_idea._mode_runner(parse(["--idea", "high52w", "--count-only"])) \
        is screen_idea.run_count
    assert screen_idea._mode_runner(parse(["--idea", "high52w", "--pin-context"])) \
        is screen_idea.run_pin_context
