"""v214 runner: an avoid idea's condition bars leave the null and the control
pools; the control arm draws from control_condition bars on its own seed; a
per-ticker IdeaError is counted and skipped; edge ideas are untouched."""
import functools
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402

from swingbot.core.backtesting.screen import null, verdict  # noqa: E402
from swingbot.core.backtesting.screen.errors import IdeaError  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS, Idea  # noqa: E402
from tests.backtesting.screen.helpers import random_walk  # noqa: E402

ALWAYS = [("2000-01-01", "9999-12-31")]
QUIET = {"out": lambda *a, **k: None}
AVOID_KEYS = {"control", "below_floor", "kept", "excluded", "population", "overnight"}


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    """500 week resamples instead of 10,000: same code path, test-speed."""
    monkeypatch.setattr(screen_idea.verdict, "decide",
                        functools.partial(verdict.decide, n_resamples=500))


def fake_states(df):
    """Cheap, deterministic avoid states. An event on every 40th bar from 300;
    the condition holds on each event bar and the two after it; control on
    every 7th bar outside the condition; bottom = Close + 1 on event bars."""
    pos = np.arange(len(df))
    event = (pos >= 300) & ((pos - 300) % 40 == 0)
    condition = event | np.roll(event, 1) | np.roll(event, 2)
    control = (pos % 7 == 3) & ~condition
    bottom = np.where(event, df["Close"].to_numpy(dtype=float) + 1.0, np.nan)
    return pd.DataFrame({"event": event, "control_condition": control,
                         "condition": condition, "bottom": bottom}, index=df.index)


def _avoid(name, states):
    return Idea(name=name, events=lambda df: states(df)["event"].rename(name),
                time_cap_bars=20, mode="avoid", states=states)


AVOID = _avoid("fake_avoid", fake_states)


def _no_control(df):
    out = fake_states(df)
    out["control_condition"] = False
    return out


def _fragile(df):
    if len(df) < 2000:
        raise IdeaError("detector failed on a short frame")
    return fake_states(df)


def _write_csv(path, df):
    df.rename_axis("Date").to_csv(path)


def _universe(tmp_path, frames):
    for ticker, df in frames.items():
        _write_csv(tmp_path / f"{ticker}.csv", df)
    names = list(frames)
    return screen_idea.Universe(intervals={t: ALWAYS for t in names}, members=names,
                                cached=names, missing=[])


def _spy_matched_null(monkeypatch):
    seen = []
    real = null.matched_null

    def spy(df, event_pos, eligible, k, seed, **kwargs):
        seen.append((np.asarray(eligible, dtype=bool).copy(), seed))
        return real(df, event_pos, eligible, k, seed, **kwargs)

    monkeypatch.setattr(null, "matched_null", spy)
    return seen


def test_condition_bars_leave_both_pools_and_the_control_has_its_own_seed(monkeypatch):
    seen = _spy_matched_null(monkeypatch)
    df = random_walk(2600)
    states = fake_states(df)
    screen_idea.screen_ticker(AVOID, "AAA", df, ALWAYS)
    (pool, seed), (control_pool, control_seed) = seen          # the null, then the control arm
    condition = states["condition"].to_numpy()
    assert condition.any() and not pool[condition].any() and not control_pool[condition].any()
    assert not control_pool[~states["control_condition"].to_numpy()].any()
    assert control_pool.any() and (control_pool <= pool).all()
    assert seed == null.null_seed("fake_avoid", "AAA")
    assert control_seed == null.null_seed("fake_avoid" + screen_idea.CONTROL_SEED_SUFFIX, "AAA")
    assert screen_idea.CONTROL_SEED_SUFFIX == ":control"


def test_the_avoid_block_pairs_kept_events_with_their_control_mean():
    df = random_walk(2600)
    out = screen_idea.screen_ticker(AVOID, "AAA", df, ALWAYS)
    block = out.avoid
    assert set(block) == AVOID_KEYS
    assert block["kept"] == len(out.events) > 0
    assert len(block["control"]) + block["below_floor"] == block["kept"]
    by_date = {row["entry_date"]: row for row in out.events}
    assert all(row["r_event"] == by_date[row["entry_date"]]["r_event"]
               for row in block["control"])
    dates = [row["entry_date"] for row in block["control"]]
    assert dates == sorted(dates) and set(dates) <= set(by_date)


def test_the_read_out_counts_match_the_masks():
    df = random_walk(2600)
    ctx = screen_idea.ticker_context(AVOID, df, ALWAYS)
    out = screen_idea.screen_ticker(AVOID, "AAA", df, ALWAYS)
    population = ctx["member"] & ctx["warm"]
    assert out.avoid["population"] == int(population.sum())
    assert out.avoid["excluded"] == int((ctx["condition"] & population).sum())
    signal = [df.index.get_loc(pd.Timestamp(row["entry_date"])) - 1 for row in out.events]
    opens, bottom = df["Open"].to_numpy(), ctx["bottom"]
    assert out.avoid["overnight"] == sum(int(opens[t + 1] >= bottom[t]) for t in signal)


def test_events_below_the_control_floor_still_count_in_n():
    """Review Focus 1: no control bar anywhere -> every event is below the
    floor, yet every event stays in the null-paired book."""
    out = screen_idea.screen_ticker(_avoid("no_control", _no_control), "AAA",
                                    random_walk(2600), ALWAYS)
    assert out.events and out.avoid["control"] == []
    assert out.avoid["below_floor"] == out.avoid["kept"] == len(out.events)


def test_states_is_read_once_per_ticker():
    calls = []

    def counting(df):
        calls.append(len(df))
        return fake_states(df)

    screen_idea.screen_ticker(_avoid("counting", counting), "AAA", random_walk(2600), ALWAYS)
    assert calls == [2600]


def test_an_edge_idea_is_untouched():
    df = random_walk(2600)
    idea = IDEAS["turn_of_month"]
    ctx = screen_idea.ticker_context(idea, df, ALWAYS)
    assert not {"condition", "control_condition", "bottom"} & set(ctx)
    assert screen_idea.screen_ticker(idea, "AAA", df, ALWAYS).avoid is None


def test_an_idea_error_skips_only_that_ticker(tmp_path):
    uni = _universe(tmp_path, {"AAA": random_walk(2600), "BAD": random_walk(1500, seed=3),
                               "CCC": random_walk(2600, seed=5)})
    lines = []
    screens, skipped = screen_idea.screen_universe(
        _avoid("fragile", _fragile), uni, tmp_path,
        out=lambda *a, **k: lines.append(a[0]))
    assert [s.ticker for s in screens] == ["AAA", "CCC"]
    assert skipped == Counter({"idea_error": 1, "idea_error:BAD": 1})
    assert "[fragile] BAD: idea error: detector failed on a short frame" in lines


def test_an_idea_error_is_never_checkpointed(tmp_path):
    uni = _universe(tmp_path, {"AAA": random_walk(2600), "BAD": random_walk(1500, seed=3)})
    directory = tmp_path / "ck"
    screen_idea.screen_universe(_avoid("fragile", _fragile), uni, tmp_path,
                                checkpoint_dir=directory, **QUIET)
    assert (directory / "AAA.pkl").exists() and not (directory / "BAD.pkl").exists()


def test_an_edge_idea_error_is_not_swallowed(tmp_path):
    def boom(df):
        raise IdeaError("edge ideas get no guard")

    uni = _universe(tmp_path, {"AAA": random_walk(2600)})
    edge = Idea(name="edge_boom", events=boom, time_cap_bars=20)
    with pytest.raises(IdeaError, match="no guard"):
        screen_idea.screen_universe(edge, uni, tmp_path, **QUIET)


def test_count_only_shares_the_pool_and_the_guard(tmp_path, monkeypatch):
    seen = []
    real = null.draw_groups

    def spy(df, event_pos, eligible, *args, **kwargs):
        seen.append(np.asarray(eligible, dtype=bool).copy())
        return real(df, event_pos, eligible, *args, **kwargs)

    monkeypatch.setattr(null, "draw_groups", spy)
    df = random_walk(2600)
    screen_idea.count_ticker(AVOID, "AAA", df, ALWAYS)
    assert not seen[0][fake_states(df)["condition"].to_numpy()].any()
    uni = _universe(tmp_path, {"AAA": df, "BAD": random_walk(1500, seed=3)})
    total = screen_idea.count_universe(_avoid("fragile", _fragile), uni, tmp_path, **QUIET)
    assert total["tickers"] == 1
    assert total["skipped"] == Counter({"idea_error": 1, "idea_error:BAD": 1})


@pytest.mark.slow
def test_the_real_idea_screens_one_ticker_deterministically():
    df = random_walk(700)
    idea = IDEAS["fvg_overhead_aged"]
    a = screen_idea.screen_ticker(idea, "AAA", df, ALWAYS)
    b = screen_idea.screen_ticker(idea, "AAA", df, ALWAYS)
    assert set(a.avoid) == AVOID_KEYS
    assert (a.events, a.avoid) == (b.events, b.avoid)
