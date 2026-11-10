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


# --- V214-7: mode-threaded verdicts ---------------------------------------

import re  # noqa: E402
from datetime import date, timedelta  # noqa: E402

from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.backtesting.screen import forward  # noqa: E402
from swingbot.core.backtesting.screen import ideas as ideas_module  # noqa: E402

CLAUSES_AVOID = {"exp_r", "ci", "years", "n", "control_exp_r", "control_ci", "control_n"}


def _rows(n, r_event, r_null=0.0):
    """n rows, one per ISO week, cycling through 2011-2019."""
    out = []
    for i in range(n):
        day = date(verdict.YEARS[i % len(verdict.YEARS)], 1, 4) + timedelta(weeks=i // 9)
        out.append({"ticker": "AAA", "entry_date": day.isoformat(),
                    "exit_date": day.isoformat(), "r_event": r_event, "r_null": r_null,
                    "outcome": "stop"})
    return out


def _screen(events, arm=None, **fields):
    rank = pd.DataFrame(columns=["year", "event"] + [f"fwd_{h}" for h in forward.HORIZONS])
    avoid = None if arm is None else {"control": arm, "below_floor": 0, "kept": len(events),
                                      "excluded": 0, "population": 0, "overnight": 0}
    return screen_idea.TickerScreen(ticker="AAA", counters=Counter(), events=events,
                                    null_outcomes=Counter(),
                                    excess={h: [] for h in forward.HORIZONS}, rank=rank,
                                    avoid=avoid, **fields)


def _avoid_summary():
    """N = 400 at d = -0.5; N_c = 350 at d_c = -0.4: every avoid clause holds."""
    return screen_idea.summarise([_screen(_rows(400, -0.5), _rows(350, -0.5, -0.1))],
                                 mode="avoid")


def test_the_mode_vocabularies_agree():
    assert verdict.MODES == ideas_module.MODES == ("edge", "avoid")
    assert verdict.SCREEN_AVOID_PASS == stats.VERDICTS[-1] == "SCREEN-AVOID-PASS"


def test_an_avoid_summary_pairs_the_null_and_the_control_arm():
    v = _avoid_summary()["verdict"]
    assert (v.mode, v.verdict, v.n) == ("avoid", "SCREEN-AVOID-PASS", 400)
    assert set(v.clauses) == CLAUSES_AVOID and all(v.clauses.values())
    assert v.delta_exp_r == pytest.approx(-0.5)
    assert v.control.n == 350 and v.control.delta_exp_r == pytest.approx(-0.4)


def test_avoid_pairs_pool_every_screens_control_rows_in_order():
    first, last = _rows(3, -0.2, 0.1), _rows(2, 0.4, 0.5)
    pairs = screen_idea._avoid_pairs([_screen(_rows(3, 0.0), first),
                                      _screen(_rows(1, 0.0)), _screen(_rows(2, 0.0), last)])
    assert [p.d for p in pairs] == pytest.approx([-0.3, -0.3, -0.3, -0.1, -0.1])
    assert [p.entry_date for p in pairs] == [r["entry_date"] for r in first + last]


def test_an_edge_summary_is_unchanged():
    screens = [_screen(_rows(320, 0.3))]
    default, edge = screen_idea.summarise(screens), screen_idea.summarise(screens, mode="edge")
    assert default["verdict"] == edge["verdict"]
    v = default["verdict"]
    assert (v.mode, v.control, v.years_negative) == ("edge", None, None)
    assert set(v.clauses) == {"exp_r", "ci", "years", "n"}


def test_stress_and_decide_carry_the_mode():
    rows = _rows(50, -0.3)
    screens = [_screen(rows, stressed=rows)]
    assert screen_idea._stress(screens).mode == "edge"
    assert screen_idea._stress(screens, mode="avoid").mode == "avoid"
    assert screen_idea._decide(rows, "avoid").mode == "avoid"
    assert screen_idea._decide(None, "avoid") is None


def test_short_blocks_carry_the_mode():
    idea = Idea(name="short_avoid", events=lambda df: fake_states(df)["event"],
                time_cap_bars=20, direction="short", mode="avoid", states=fake_states)
    rows = _rows(40, -0.2)
    block = screen_idea.with_short_blocks({"events": rows}, [_screen(rows, control=rows)],
                                          idea, None)["short"]
    assert block["control"].mode == "avoid"


def test_the_avoid_verdict_table_states_the_avoid_rules():
    text = "\n".join(screen_idea._render_verdict(_avoid_summary()["verdict"]))
    assert text.startswith("## Verdict: SCREEN-AVOID-PASS")
    for row in ("| ΔExpR = mean(R_event − mean R_null) | -0.5000R | ≤ -0.10R | yes |",
                "| years with mean(d) < 0 | 9 of 9 | ≥ 7 | yes |",
                "| kept events N | 400 | ≥ 300 | yes |",
                "| control arm ΔExpR = mean(R_event − mean R_control) | -0.4000R | ≤ -0.10R | yes |",
                "| control arm events N_c | 350 | ≥ 300 | yes |",
                "One-sided bootstrap p (share of resamples ≥ 0): "):
        assert row in text
    assert "| upper 95% bound, week-clustered bootstrap | -0.5000R (lower -0.5000R) | < 0 | yes |" in text
    assert "| control arm upper 95% bound | -0.4000R (lower -0.4000R) | < 0 | yes |" in text
    assert "mean(d) > 0" not in text and "share of resamples ≤ 0" not in text


def test_years_text_per_mode():
    assert screen_idea._years_text(_avoid_summary()["verdict"]) == "9/9 years negative"
    edge = verdict.Verdict("SCREEN-FAIL", 412, 0.03, -0.01, 0.07, 0.23, 4, {}, {})
    assert screen_idea._years_text(edge) == "4/9 years"


def test_an_avoid_run_never_prints_an_edge_label(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(screen_idea.IDEAS, "fake_avoid", AVOID)
    cache = tmp_path / "cache"
    cache.mkdir()
    for seed, ticker in enumerate(("AAA", "BBB"), start=1):
        _write_csv(cache / f"{ticker}.csv", random_walk(2700, seed=seed))
    membership = tmp_path / "membership.csv"
    membership.write_text("ticker,start_date,end_date\nAAA,2000-01-01,\nBBB,2000-01-01,\n",
                          encoding="utf-8")
    argv = ["--idea", "fake_avoid", "--cache-dir", str(cache), "--membership", str(membership),
            "--ledger", str(tmp_path / "ledger.jsonl"), "--results-dir", str(tmp_path / "r"),
            "--date", "2026-11-06", "--dry-run"]
    assert screen_idea.main(argv) == 0
    text = capsys.readouterr().out
    assert "## Verdict: SCREEN-" in text and "years with mean(d) < 0" in text
    assert re.search(r"(?<!AVOID-)SCREEN-PASS", text) is None
    assert "years with mean(d) > 0" not in text
